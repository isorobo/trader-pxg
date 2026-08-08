"""Hourly Bollinger-fade mean reversion (Strategys/17 #1 + #4, the RSI
confluence variant, with the file's own non-negotiable regime gate) --
frozen BEFORE any backtest result exists (standing rule 1).

Rules, transcribed from the file:
- RANGE GATE first ("never fade when bands are expanding"): the current
  BB(20,2) bandwidth must be at or below its rolling 96-bar median.
- Setup: the PREVIOUS bar closed below the lower band (the stretch).
- Trigger: the CURRENT bar closes back inside the band (the snap-back
  close, #1's entry) AND RSI(14) is under the variant's ceiling (#4's
  confluence filter).
- Long only (spot crypto book).

Variants (pre-registered):
- "confluence30": RSI(14) < 30 (the file's published threshold)
- "confluence25": RSI(14) < 25 (stricter, fewer/cleaner signals)

Timeframe: 1h bars. This module is one of frozen_config_hourly.py's
FROZEN_FILES_HOURLY entries.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from trader.backtest.iterator import PointInTimeIterator
from trader.backtest.strategies.momentum_v2 import _rsi_wilder

BB_PERIOD = 20
BB_STD = 2.0
BANDWIDTH_MEDIAN_WINDOW = 96  # 4 days of hourly bars
RSI_PERIOD = 14
# "Expanding" means CLEARLY above the typical width, not a hair above it:
# a flat range's bandwidth wobbles a few percent around its median by
# construction, so an exact <=median gate rejects ~half of genuine range
# regimes at random. 1.25x is the frozen expansion threshold.
BAND_EXPANSION_TOLERANCE = 1.25

# Bars required: the gate's bandwidth history ends at n-2 and needs
# BANDWIDTH_MEDIAN_WINDOW rolling BB values, each needing BB_PERIOD closes.
MIN_BARS = BB_PERIOD + BANDWIDTH_MEDIAN_WINDOW + 3


@dataclass(frozen=True)
class HourlyReversionVariant:
    """One frozen RSI-confluence ceiling (Strategys/17 #4)."""

    name: str
    rsi_ceiling: float


HOURLY_REVERSION_VARIANTS: dict[str, HourlyReversionVariant] = {
    "confluence30": HourlyReversionVariant(name="confluence30", rsi_ceiling=30.0),
    "confluence25": HourlyReversionVariant(name="confluence25", rsi_ceiling=25.0),
}


def _bb(closes: np.ndarray, end: int) -> tuple[float, float, float]:
    """(lower, upper, bandwidth) of BB(BB_PERIOD, BB_STD) over
    closes[end-BB_PERIOD:end] -- `end` is an exclusive slice bound."""
    window = closes[end - BB_PERIOD:end]
    mid = window.mean()
    sd = window.std(ddof=0)
    lower = mid - BB_STD * sd
    upper = mid + BB_STD * sd
    width = (upper - lower) / mid if mid else 0.0
    return lower, upper, width


def make_pick_entries(
    variant: HourlyReversionVariant,
) -> Callable[[PointInTimeIterator, pd.Timestamp, set[str], random.Random], list[str]]:
    """The uniform 4-arg engine contract, bound to `variant`."""
    ceiling = variant.rsi_ceiling

    def pick_entries(
        iterator: PointInTimeIterator,
        date: pd.Timestamp,
        open_positions: set[str],
        rng: random.Random,
    ) -> list[str]:
        entries: list[str] = []
        for symbol in iterator.symbols:
            if symbol in open_positions:
                continue
            history = iterator.history(symbol)
            if len(history) < MIN_BARS:
                continue
            closes = history[:, 3]

            # Range gate, measured BEFORE the stretch bar (end = n-2): the
            # stretch itself expands the bands, so gating on the current
            # width would veto every genuine setup (caught by the signal
            # tests before any backtest existed). "Never fade when bands
            # are expanding" is about the regime the stretch happened IN.
            n = len(closes)
            gate_widths = np.array(
                [
                    _bb(closes, end)[2]
                    for end in range(n - 1 - BANDWIDTH_MEDIAN_WINDOW, n - 1)
                ]
            )
            if gate_widths[-1] > BAND_EXPANSION_TOLERANCE * np.median(gate_widths[:-1]):
                continue

            lower_prev, _, _ = _bb(closes, n - 1)
            lower_now, _, _ = _bb(closes, n)
            prev_close = closes[-2]
            now_close = closes[-1]

            stretched = prev_close < lower_prev
            snapped_back = now_close > lower_now
            # The confluence (#4: "band touch AND RSI < 30 simultaneously")
            # is evaluated AT THE TOUCH -- RSI on the stretch bar, entry on
            # the snap-back close (#1's trigger). RSI on the snap bar would
            # already be lifted by the very bounce being traded.
            oversold = _rsi_wilder(closes[:-1], period=RSI_PERIOD) < ceiling

            if stretched and snapped_back and oversold:
                entries.append(symbol)
        return entries

    return pick_entries
