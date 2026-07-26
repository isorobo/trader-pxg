"""Simplest-possible momentum placeholder (D-15) -- proves the harness runs
end to end, not a Phase 3 strategy.

Signal: the latest visible close is strictly greater than the close
LOOKBACK_DAYS bars earlier, given at least LOOKBACK_DAYS + 1 bars of
history. LOOKBACK_DAYS = 20 (Claude's discretion): roughly a trading
month, long enough to be a real (non-trivial) signal while staying simple
enough to audit by eye.

Unlike random_strategy's single pick, this placeholder can signal on
multiple symbols the same day -- it returns every qualifying symbol, not
just one (documented difference from random_strategy.pick_entries).
"""

from __future__ import annotations

import random

import pandas as pd

from trader.backtest.iterator import PointInTimeIterator

LOOKBACK_DAYS = 20


def pick_entries(
    iterator: PointInTimeIterator,
    date: pd.Timestamp,
    open_positions: set[str],
    rng: random.Random,
) -> list[str]:
    """Return every universe symbol whose visible close has risen over the
    last LOOKBACK_DAYS bars, skipping symbols already open and symbols with
    fewer than LOOKBACK_DAYS + 1 bars of history (D-15).

    `date` and `rng` are accepted only to satisfy the shared pick_entries
    contract (runner.py, plan 02-08, calls every strategy uniformly);
    neither is used here -- the signal depends only on iterator.history.
    """
    entries: list[str] = []
    for symbol in iterator.symbols:
        if symbol in open_positions:
            continue
        history = iterator.history(symbol)
        if len(history) < LOOKBACK_DAYS + 1:
            continue
        latest_close = history[-1][3]
        earlier_close = history[-(LOOKBACK_DAYS + 1)][3]
        if latest_close > earlier_close:
            entries.append(symbol)
    return entries
