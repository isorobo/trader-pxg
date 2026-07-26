"""v2 breakout entry-variant registry (STRAT-04, D-14): entry-gate
strictness becomes a SWEPT dimension -- 3 pre-registered variants
(strict/base/loose) on NR-window width + volume-confirm multiplier,
defined in code before any v2 result exists.

This module is fully self-contained: it never imports v1's
trader.backtest.strategies.breakout. The NR7-contraction/volume-confirm/
no-retest signal logic below is an intentional, verbatim duplication of
breakout.py's own logic (mirrored, not modified) -- breakout.py itself is
never touched. "base" reproduces v1's exact constants (NR_WINDOW=7,
VOLUME_CONFIRM_MULT=1.5) so v2 adds a new swept dimension without silently
changing what v1 already proved (tests/test_entry_variants_v2.py's
behavioral-parity test enforces this).

BREAKOUT_LOOKBACK stays fixed across all three variants, and no-retest
scope stays fixed too (unchanged from v1's orchestrator-resolved scope
decision) -- only NR-window width and the volume-confirm multiplier vary
per D-14.

This module is one of frozen_config_v2.FROZEN_FILES_V2's five entries: any
byte-level edit after FROZEN_HASH_V2 is locked is detected by
verify_frozen_v2() and blocks every downstream v2 sweep entrypoint.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from trader.backtest.iterator import PointInTimeIterator

BREAKOUT_LOOKBACK = 20


@dataclass(frozen=True)
class BreakoutVariant:
    """One frozen breakout contraction-gate strictness setting (D-14)."""

    name: str
    nr_window: int
    volume_confirm_mult: float


BREAKOUT_VARIANTS: dict[str, BreakoutVariant] = {
    "strict": BreakoutVariant(name="strict", nr_window=10, volume_confirm_mult=2.0),
    "base": BreakoutVariant(name="base", nr_window=7, volume_confirm_mult=1.5),
    "loose": BreakoutVariant(name="loose", nr_window=4, volume_confirm_mult=1.2),
}


def make_pick_entries(
    variant: BreakoutVariant,
) -> Callable[[PointInTimeIterator, pd.Timestamp, set[str], random.Random], list[str]]:
    """Return a `pick_entries(iterator, date, open_positions, rng)` closure
    bound to `variant`'s NR-window width and volume-confirm multiplier.

    The variant is bound via closure, not a 5th positional argument, since
    `runner.run_backtest` calls every strategy_fn uniformly with exactly 4
    args (that engine contract is never modified). Body is byte-for-byte
    breakout.py's own signal logic, with `variant.nr_window`/
    `variant.volume_confirm_mult` replacing the hardcoded NR_WINDOW/
    VOLUME_CONFIRM_MULT constants. No-retest scope stays fixed across all
    3 variants, unchanged from v1's orchestrator-resolved scope decision.
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
            if len(history) < BREAKOUT_LOOKBACK + 1:
                continue

            highs = history[:, 1]
            lows = history[:, 2]
            closes = history[:, 3]
            volumes = history[:, 4]

            ranges = highs - lows
            is_nr = ranges[-1] == ranges[-variant.nr_window:].min()

            today_close = closes[-1]
            prior_high = highs[-(BREAKOUT_LOOKBACK + 1):-1].max()
            today_volume = volumes[-1]
            baseline_volume = volumes[-(BREAKOUT_LOOKBACK + 1):-1].mean()

            if (
                is_nr
                and today_close > prior_high
                and today_volume > variant.volume_confirm_mult * baseline_volume
            ):
                entries.append(symbol)
        return entries

    return pick_entries
