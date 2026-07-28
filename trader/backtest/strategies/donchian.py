"""Donchian channel breakout entry-variant registry (Strategys/
10_donchian_breakout.md, the owner's first queued Phase 8 entrant).

Two pre-registered variants, straight from the published Turtle systems --
defined in code BEFORE any backtest result exists (standing rule 1):

- "sys1": entry on a break of the 20-day high (Turtle System 1)
- "sys2": entry on a break of the 55-day high (Turtle System 2)

Long-only (the project's paper book is long-only). The classic Turtle
channel EXIT (10/20-day low) is deliberately NOT implemented here: in this
project every strategy's exits come from the frozen exit-profile grid
(exit_grid.py, swept by the same machinery as every other entrant), where
the trailing-stop cells approximate the channel exit's let-winners-run
behaviour. Entries are trivial; the grid owns the exits -- the strategy
file's own "Notes for Automation" says exactly this.

No volume filter, no discretion -- the spec is "no discretion at all", and
adding an unpublished filter before the first honest backtest would be
tuning by another name.

This module is the frozen surface of trader/backtest/
frozen_config_donchian.py's hash gate: any byte-level edit after
FROZEN_HASH_DONCHIAN is locked blocks every Donchian evidence entrypoint.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from trader.backtest.iterator import PointInTimeIterator


@dataclass(frozen=True)
class DonchianVariant:
    """One frozen Donchian entry-channel width (Turtle System 1 or 2)."""

    name: str
    entry_lookback: int


DONCHIAN_VARIANTS: dict[str, DonchianVariant] = {
    "sys1": DonchianVariant(name="sys1", entry_lookback=20),
    "sys2": DonchianVariant(name="sys2", entry_lookback=55),
}


def make_pick_entries(
    variant: DonchianVariant,
) -> Callable[[PointInTimeIterator, pd.Timestamp, set[str], random.Random], list[str]]:
    """Return a `pick_entries(iterator, date, open_positions, rng)` closure
    bound to `variant`'s channel width -- the same 4-arg engine contract
    every other strategy module satisfies (runner.run_backtest calls every
    strategy_fn uniformly; the variant binds via closure exactly as
    momentum_v2/breakout_v2 do)."""
    lookback = variant.entry_lookback

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
            if len(history) < lookback + 1:
                continue

            highs = history[:, 1]
            today_close = history[-1, 3]
            prior_channel_high = highs[-(lookback + 1):-1].max()

            if today_close > prior_channel_high:
                entries.append(symbol)
        return entries

    return pick_entries
