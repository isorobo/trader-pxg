"""v2 momentum entry-variant registry (STRAT-03, D-14): entry-gate
strictness becomes a SWEPT dimension -- 3 pre-registered variants
(strict/base/loose) on RSI threshold + volume-surge multiplier, defined in
code before any v2 result exists.

This module is fully self-contained: it never imports v1's
trader.backtest.strategies.momentum. The RSI-Wilder/volume-surge/break
signal logic below is an intentional, verbatim duplication of momentum.py's
own logic (mirrored, not modified) -- momentum.py itself is never touched.
"base" reproduces v1's exact constants (RSI_MOMENTUM_FLOOR=60,
VOLUME_SURGE_MULT=2.0) so v2 adds a new swept dimension without silently
changing what v1 already proved (tests/test_entry_variants_v2.py's
behavioral-parity test enforces this).

RSI_PERIOD and BREAK_LOOKBACK stay fixed across all three variants per
D-14 -- only the RSI floor and volume-surge multiplier vary.

This module is one of frozen_config_v2.FROZEN_FILES_V2's five entries: any
byte-level edit after FROZEN_HASH_V2 is locked is detected by
verify_frozen_v2() and blocks every downstream v2 sweep entrypoint.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from trader.backtest.iterator import PointInTimeIterator

RSI_PERIOD = 14
BREAK_LOOKBACK = 20


@dataclass(frozen=True)
class MomentumVariant:
    """One frozen momentum entry-gate strictness setting (D-14)."""

    name: str
    rsi_floor: float
    volume_surge_mult: float


MOMENTUM_VARIANTS: dict[str, MomentumVariant] = {
    "strict": MomentumVariant(name="strict", rsi_floor=70.0, volume_surge_mult=3.0),
    "base": MomentumVariant(name="base", rsi_floor=60.0, volume_surge_mult=2.0),
    "loose": MomentumVariant(name="loose", rsi_floor=50.0, volume_surge_mult=1.5),
}


def _rsi_wilder(closes: np.ndarray, period: int = RSI_PERIOD) -> float:
    """Smoothed RSI over the LAST `period + 1` closes in `closes`.

    Verbatim duplication of momentum.py's own `_rsi_wilder` -- see that
    module for the full contract note (zero-loss window returns 100.0
    rather than dividing by zero).
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


def make_pick_entries(
    variant: MomentumVariant,
) -> Callable[[PointInTimeIterator, pd.Timestamp, set[str], random.Random], list[str]]:
    """Return a `pick_entries(iterator, date, open_positions, rng)` closure
    bound to `variant`'s RSI floor and volume-surge multiplier.

    The variant is bound via closure, not a 5th positional argument, since
    `runner.run_backtest` calls every strategy_fn uniformly with exactly 4
    args (that engine contract is never modified). Body is byte-for-byte
    momentum.py's own signal logic, with `variant.rsi_floor`/
    `variant.volume_surge_mult` replacing the hardcoded
    RSI_MOMENTUM_FLOOR/VOLUME_SURGE_MULT constants.
    """

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
                rsi >= variant.rsi_floor
                and today_volume > variant.volume_surge_mult * baseline_volume
                and today_close > prior_high
            ):
                entries.append(symbol)
        return entries

    return pick_entries
