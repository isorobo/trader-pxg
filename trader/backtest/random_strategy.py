"""Seeded random strategy (D-14, BACK-07) -- the sanity test's engine.

"Buy a random universe symbol, hold one day, repeat" (D-14). Genuinely
random-but-reproducible and genuinely price-blind by construction:
pick_entries never reads an OHLCV value anywhere -- only iterator.bar_on's
presence/absence and the caller-supplied rng decide the pick. If this
strategy ever profits, the harness (not the strategy) is broken; that is
the entire point of the sanity test (T-02-15).

Single-position assumption: the D-14 cadence holds at most one open
position at a time. pick_entries itself only guarantees it never re-picks
a symbol already in open_positions -- enforcing "at most one total
position" end to end is runner.py's (plan 02-08) responsibility, not
this module's.
"""

from __future__ import annotations

import random

import pandas as pd

from trader.backtest.iterator import PointInTimeIterator


def pick_entries(
    iterator: PointInTimeIterator,
    date: pd.Timestamp,
    open_positions: set[str],
    rng: random.Random,
) -> list[str]:
    """Return zero or one symbol to enter today.

    Draws uniformly at random (via rng.choice) from the universe symbols
    that have a bar on `date` (iterator.bar_on(symbol, date) is not None)
    and are not already open. Returns [] if no symbol qualifies.

    Two calls with the same date, universe, open_positions, and a
    freshly-seeded rng of the same seed return the identical pick --
    reproducibility is the caller's responsibility (pass a fresh
    random.Random(seed)), not something this function tracks itself.
    """
    available = [
        symbol
        for symbol in iterator.symbols
        if symbol not in open_positions and iterator.bar_on(symbol, date) is not None
    ]
    if not available:
        return []
    return [rng.choice(available)]
