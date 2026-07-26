"""Momentum agent (STRAT-01, D-01): RSI(14) + volume surge + 20-day-high
break, matching Phase 2's shared strategy contract:

    pick_entries(iterator, date, open_positions, rng) -> list[str]

Entry-rule parameters below are fixed module-level constants -- research
inputs, never sweep-grid inputs (03-RESEARCH.md Pitfall 1; only the
exit-parameter grid varies, per D-06/D-07). Long-only only: the engine's
`fills.worse_of_fill` raises NotImplementedError for any short-side exit
(inherited D-15 constraint) -- this module never constructs a short-side
signal path (03-RESEARCH.md Pitfall 4).

Signal rule (owner reference: Strategys/07_momentum_trading.md -- RVOL>2x is
"the key filter"; RSI "not for overbought fades, momentum lives above
60-70"; "break of recent highs"):

    RSI(14) >= 60
    AND today's volume > 2.0x its trailing 20-day average volume
    AND today's close > the prior 20-day high

Both the volume baseline and the prior high are computed EXCLUDING today's
own bar (`history[-(N+1):-1]`, never `history[-N:]`) -- including today would
let an extreme day inflate its own trigger threshold (03-RESEARCH.md
Pitfall 2).
"""

from __future__ import annotations

import random

import numpy as np
import pandas as pd

from trader.backtest.iterator import PointInTimeIterator

RSI_PERIOD = 14
RSI_MOMENTUM_FLOOR = 60
VOLUME_SURGE_MULT = 2.0
BREAK_LOOKBACK = 20


def _rsi_wilder(closes: np.ndarray, period: int = RSI_PERIOD) -> float:
    """Smoothed RSI over the LAST `period + 1` closes in `closes`.

    Caller must ensure len(closes) >= period + 1. Returns 100.0 for a
    zero-loss window (pure uptrend) rather than dividing by zero.
    """
    deltas = np.diff(closes[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains.mean()
    avg_loss = losses.mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def pick_entries(
    iterator: PointInTimeIterator,
    date: pd.Timestamp,
    open_positions: set[str],
    rng: random.Random,
) -> list[str]:
    """Return every universe symbol whose visible bars satisfy the momentum
    rule above, skipping symbols already open and symbols with fewer than
    BREAK_LOOKBACK + 1 bars of history.

    `date` and `rng` are accepted only to satisfy the shared pick_entries
    contract; neither is used here -- the signal depends only on
    iterator.history (deterministic given bars).
    """
    entries: list[str] = []
    for symbol in iterator.symbols:
        if symbol in open_positions:
            continue
        history = iterator.history(symbol)
        if len(history) < BREAK_LOOKBACK + 1:
            continue

        closes = history[:, 3]
        volumes = history[:, 4]
        highs = history[:, 1]

        rsi = _rsi_wilder(closes, RSI_PERIOD)
        today_volume = volumes[-1]
        baseline_volume = volumes[-(BREAK_LOOKBACK + 1):-1].mean()
        today_close = closes[-1]
        prior_high = highs[-(BREAK_LOOKBACK + 1):-1].max()

        if (
            rsi >= RSI_MOMENTUM_FLOOR
            and today_volume > VOLUME_SURGE_MULT * baseline_volume
            and today_close > prior_high
        ):
            entries.append(symbol)
    return entries
