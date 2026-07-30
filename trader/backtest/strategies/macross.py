"""Moving-average crossover entry-variant registry (Strategys/
15_moving_average_trend.md #1 and #2 -- the two published crossover
systems, pre-registered BEFORE any backtest result exists, standing
rule 1).

- "fast_ema_20_50":  20 EMA crosses above 50 EMA today (file 15's #1,
  "Golden/Death Cross, fast" -- the medium-term trend-initiation system).
- "golden_sma_50_200": 50 SMA crosses above 200 SMA today (file 15's #2's
  macro alignment expressed as its canonical cross event -- the classic
  golden cross).

Entry fires ONLY on the cross event itself (fast at-or-below slow
yesterday, fast above slow today) -- alignment alone never re-fires, so a
long-running trend produces one entry, not one per day. Long only. Exits
come from the frozen exit-profile grid like every entrant (the file's own
"exit on cross-back or trail" maps to the grid's trailing cells).

This module is the frozen surface of trader/backtest/frozen_config_macross.py.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from trader.backtest.iterator import PointInTimeIterator


@dataclass(frozen=True)
class MaCrossVariant:
    """One frozen MA-cross system: kind ('ema'|'sma'), fast and slow spans."""

    name: str
    kind: str
    fast: int
    slow: int


MACROSS_VARIANTS: dict[str, MaCrossVariant] = {
    "fast_ema_20_50": MaCrossVariant(name="fast_ema_20_50", kind="ema", fast=20, slow=50),
    "golden_sma_50_200": MaCrossVariant(
        name="golden_sma_50_200", kind="sma", fast=50, slow=200
    ),
}


def _ma_last_two(closes: np.ndarray, kind: str, span: int) -> tuple[float, float]:
    """The moving average's yesterday and today values.

    SMA: plain trailing mean of `span` closes. EMA: standard
    alpha=2/(span+1) recursion seeded with the first close -- computed over
    the full available history so today's and yesterday's values share one
    consistent series.
    """
    if kind == "sma":
        today = closes[-span:].mean()
        yesterday = closes[-(span + 1):-1].mean()
        return yesterday, today

    alpha = 2.0 / (span + 1.0)
    ema = closes[0]
    yesterday = ema
    for value in closes[1:]:
        yesterday = ema
        ema = alpha * value + (1.0 - alpha) * ema
    return yesterday, ema


def make_pick_entries(
    variant: MaCrossVariant,
) -> Callable[[PointInTimeIterator, pd.Timestamp, set[str], random.Random], list[str]]:
    """Return a `pick_entries(iterator, date, open_positions, rng)` closure
    bound to `variant` -- the uniform 4-arg engine contract."""

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
            if len(history) < variant.slow + 1:
                continue

            closes = history[:, 3]
            fast_prev, fast_now = _ma_last_two(closes, variant.kind, variant.fast)
            slow_prev, slow_now = _ma_last_two(closes, variant.kind, variant.slow)

            if fast_prev <= slow_prev and fast_now > slow_now:
                entries.append(symbol)
        return entries

    return pick_entries
