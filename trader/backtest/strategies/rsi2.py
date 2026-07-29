"""RSI(2) mean-reversion entry-variant registry (Strategys/
11_rsi2_mean_reversion.md, Connors-style -- the owner's second queued
Phase 8 entrant).

Two pre-registered variants, straight from the published rules -- defined
in code BEFORE any backtest result exists (standing rule 1):

- "connors10": RSI(2) closes below 10 (the standard published threshold)
- "connors5":  RSI(2) closes below 5 (the published stricter variant)

Both require close above the 200-day SMA -- the spec's "non-negotiable"
long-term uptrend filter. Long only (the spec: "famously weak on the short
side"; the paper book is long-only anyway).

Exits: the spec's own automation note prefers a time stop plus a wide
disaster stop over tight price stops ("tight stops destroy the edge") --
exactly the shape the frozen exit-profile grid already sweeps
(max_hold_days cells + wide stop_pct cells), so exits come from the grid
like every other entrant. The RSI>65 / 5-day-SMA discretionary exit is
deliberately NOT hardcoded: this project's design gives the grid the
exits, and adding an unswept exit path would bypass the machinery every
incumbent was judged by.

RSI math is imported from the frozen momentum_v2 module (period
parameterised at 2) -- reused, never reimplemented (the same Wilder
zero-loss contract applies: an all-gain window reads 100.0).

This module is the frozen surface of trader/backtest/frozen_config_rsi2.py.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from trader.backtest.iterator import PointInTimeIterator
from trader.backtest.strategies.momentum_v2 import _rsi_wilder

SMA_FILTER_DAYS = 200
RSI_PERIOD = 2


@dataclass(frozen=True)
class Rsi2Variant:
    """One frozen RSI(2) oversold threshold (Connors 10 or 5)."""

    name: str
    rsi_entry_ceiling: float


RSI2_VARIANTS: dict[str, Rsi2Variant] = {
    "connors10": Rsi2Variant(name="connors10", rsi_entry_ceiling=10.0),
    "connors5": Rsi2Variant(name="connors5", rsi_entry_ceiling=5.0),
}


def make_pick_entries(
    variant: Rsi2Variant,
) -> Callable[[PointInTimeIterator, pd.Timestamp, set[str], random.Random], list[str]]:
    """Return a `pick_entries(iterator, date, open_positions, rng)` closure
    bound to `variant`'s RSI ceiling -- the uniform 4-arg engine contract."""
    ceiling = variant.rsi_entry_ceiling

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
            if len(history) < SMA_FILTER_DAYS:
                continue

            closes = history[:, 3]
            today_close = closes[-1]
            sma_200 = closes[-SMA_FILTER_DAYS:].mean()
            if today_close <= sma_200:
                continue  # the non-negotiable uptrend filter

            rsi_2 = _rsi_wilder(closes, period=RSI_PERIOD)
            if rsi_2 < ceiling:
                entries.append(symbol)
        return entries

    return pick_entries
