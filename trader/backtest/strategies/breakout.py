"""Breakout agent (STRAT-02, D-01): NR7 volatility contraction + 20-day-high
close break + volume confirmation, matching Phase 2's shared strategy
contract:

    pick_entries(iterator, date, open_positions, rng) -> list[str]

Scope decision (03-RESEARCH.md Open Question 1, orchestrator-resolved): this
v1 ships NO-RETEST. The owner's reference spec (Strategys/03_breakout_
trading.md) prefers waiting for a retest of the broken level, but that
lowers trade frequency and would starve the thin OOS windows (2022 crypto
bear, WIF's mania tune window) below the sweep's minimum-trade-count floor.
A single qualifying bar fires immediately -- do not "fix" this by adding a
retest gate; it is a deliberate scope decision, not a missing feature.

Entry-rule parameters below are fixed module-level constants -- research
inputs, never sweep-grid inputs (only the exit-parameter grid varies, per
D-06/D-07). Long-only only, matching the inherited D-15 engine constraint
(03-RESEARCH.md Pitfall 4).

Signal rule (owner reference: Strategys/03_breakout_trading.md -- tight-
range/declining-ATR squeeze, close above resistance, volume > 1.5x 20-bar
average):

    Today's high-low range is the narrowest of the trailing 7 bars (NR7,
    inclusive of today)
    AND today's close > the prior 20-day high
    AND today's volume > 1.5x its trailing 20-day average volume

The prior-high and volume-baseline windows are computed EXCLUDING today's
own bar (`history[-(N+1):-1]`, never `history[-N:]`) -- including today
would let the breakout bar inflate its own trigger threshold (03-RESEARCH.md
Pitfall 2).
"""

from __future__ import annotations

import random

import pandas as pd

from trader.backtest.iterator import PointInTimeIterator

NR_WINDOW = 7
BREAKOUT_LOOKBACK = 20
VOLUME_CONFIRM_MULT = 1.5


def pick_entries(
    iterator: PointInTimeIterator,
    date: pd.Timestamp,
    open_positions: set[str],
    rng: random.Random,
) -> list[str]:
    """Return every universe symbol whose visible bars satisfy the NR7
    breakout rule above, skipping symbols already open and symbols with
    fewer than BREAKOUT_LOOKBACK + 1 bars of history.

    `date` and `rng` are accepted only to satisfy the shared pick_entries
    contract; neither is used here -- the signal depends only on
    iterator.history (deterministic given bars). No retest gate exists
    anywhere in this function (see module docstring).
    """
    entries: list[str] = []
    for symbol in iterator.symbols:
        if symbol in open_positions:
            continue
        history = iterator.history(symbol)
        if len(history) < BREAKOUT_LOOKBACK + 1:
            continue

        highs = history[:, 1]
        lows = history[:, 2]
        closes = history[:, 3]
        volumes = history[:, 4]

        ranges = highs - lows
        is_nr7 = ranges[-1] == ranges[-NR_WINDOW:].min()

        today_close = closes[-1]
        prior_high = highs[-(BREAKOUT_LOOKBACK + 1):-1].max()
        today_volume = volumes[-1]
        baseline_volume = volumes[-(BREAKOUT_LOOKBACK + 1):-1].mean()

        if (
            is_nr7
            and today_close > prior_high
            and today_volume > VOLUME_CONFIRM_MULT * baseline_volume
        ):
            entries.append(symbol)
    return entries
