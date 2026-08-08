"""Hourly Bollinger-squeeze breakout (Strategys/18 #2, with #5's
MANDATORY volume-confirmation filter) -- frozen BEFORE any backtest result
exists (standing rule 1).

Rules, transcribed from the file:
- Squeeze: current BB(20,2) bandwidth is the NARROWEST of the trailing
  96 hourly bars (compression -- "energy loading").
- Break: the current bar CLOSES above the upper band (expansion, long
  only -- spot crypto book).
- Volume confirm (#5, "not a standalone system -- a mandatory filter"):
  current volume >= the variant's multiple of the 20-bar average.

Variants (pre-registered, straight from the file's "2-3x" range):
- "vol2x": volume >= 2.0x the 20-bar average
- "vol3x": volume >= 3.0x the 20-bar average

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
from trader.backtest.strategies.hourly_reversion import _bb

SQUEEZE_LOOKBACK = 96  # the "narrowest in N periods" window (4 days of 1h)
VOLUME_AVG_PERIOD = 20
# "Narrowest in N periods" with a frozen 10% tolerance: inside a long coil
# the bandwidth wobbles fractionally bar to bar, so demanding the EXACT
# minimum rejects genuine squeezes at random. Within 10% of the N-bar low
# still IS the compression the file describes.
SQUEEZE_TOLERANCE = 1.10

MIN_BARS = 20 + SQUEEZE_LOOKBACK + 1


@dataclass(frozen=True)
class HourlySqueezeVariant:
    """One frozen volume-confirmation multiple (Strategys/18 #5)."""

    name: str
    volume_confirm_mult: float


HOURLY_SQUEEZE_VARIANTS: dict[str, HourlySqueezeVariant] = {
    "vol2x": HourlySqueezeVariant(name="vol2x", volume_confirm_mult=2.0),
    "vol3x": HourlySqueezeVariant(name="vol3x", volume_confirm_mult=3.0),
}


def make_pick_entries(
    variant: HourlySqueezeVariant,
) -> Callable[[PointInTimeIterator, pd.Timestamp, set[str], random.Random], list[str]]:
    """The uniform 4-arg engine contract, bound to `variant`."""
    mult = variant.volume_confirm_mult

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
            volumes = history[:, 4]
            n = len(closes)

            # Compression is measured on the bar BEFORE the break: the
            # breakout candle itself blows the bands open, so including it
            # would un-squeeze every genuine setup (caught by the signal
            # tests before any backtest existed).
            widths = np.array(
                [_bb(closes, end)[2] for end in range(n - SQUEEZE_LOOKBACK, n)]
            )
            in_squeeze = widths[-1] <= SQUEEZE_TOLERANCE * widths.min()

            _, upper_now, _ = _bb(closes, n)
            broke_out = closes[-1] > upper_now

            baseline_volume = volumes[-(VOLUME_AVG_PERIOD + 1):-1].mean()
            volume_confirmed = volumes[-1] >= mult * baseline_volume

            if in_squeeze and broke_out and volume_confirmed:
                entries.append(symbol)
        return entries

    return pick_entries
