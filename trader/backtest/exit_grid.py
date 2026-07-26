"""The frozen D-06 exit-parameter grid for Phase 3's sweep harness (STRAT-03).

Entry-rule parameters (RSI period/threshold, volume-surge multiplier, NR7
window) are fixed constants in strategies/momentum.py and strategies/
breakout.py -- NOT swept. Only this grid's stop/TP/trailing/time-stop
combination varies per cell, keeping the grid at exactly 270 cells for the
stock and crypto-major/legacy-memecoin buckets (03-RESEARCH.md's Sweep
Engineering section, Pitfall 1).

new_memecoin gets an ADDITIVE fourth time-stop value
(MEMECOIN_SHORT_HOLD_DAYS), per D-06's "memecoins additionally test
eod_flat-style short holds" and the orchestrator's resolution of
03-RESEARCH.md Open Question 2 -- the grid grows to 360 cells (6x5x3x4) for
that bucket only, never replacing the base three TIME_STOPS values, and no
other asset class gets a small-cap-runner-style variant this phase (see
03-02-PLAN.md's objective scope note on config.py's unwired
SLIPPAGE_SMALL_CAP_RUNNER).

This module is one of the three frozen_config.FROZEN_FILES entries: any
byte-level edit after FROZEN_HASH is locked (see
trader/backtest/frozen_config.py) is detected by verify_frozen() and blocks
every downstream sweep/OOS entrypoint.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator

from trader.backtest import config
from trader.backtest.universe import BUCKET_NEW_MEMECOIN

STOPS: tuple[float, ...] = (-0.05, -0.10, -0.15, -0.20, -0.25, -0.30)
TPS: tuple[float, ...] = (0.20, 0.40, 0.60, 0.80, 1.00)
TRAILS: tuple[float | None, ...] = (None, 0.10, 0.20)
TIME_STOPS: tuple[int | None, ...] = (None, 10, 30)

# Claude's discretion per D-06's "memecoins additionally test eod_flat-style
# short holds" -- a fourth, additive time-stop value used ONLY for the
# new_memecoin bucket.
MEMECOIN_SHORT_HOLD_DAYS = 3


def exit_profile_grid(bucket: str) -> Iterator[config.EXIT_PROFILE]:
    """Yield every EXIT_PROFILE cell in the frozen D-06 grid for `bucket`.

    270 cells (6 stops x 5 TPs x 3 trails x 3 time-stops) for every bucket
    except new_memecoin, which gets an additive fourth time-stop
    (MEMECOIN_SHORT_HOLD_DAYS) for 360 cells (6x5x3x4).
    """
    time_stops = TIME_STOPS
    if bucket == BUCKET_NEW_MEMECOIN:
        time_stops = TIME_STOPS + (MEMECOIN_SHORT_HOLD_DAYS,)

    for stop_pct, tp_pct, trailing_pct, max_hold_days in itertools.product(
        STOPS, TPS, TRAILS, time_stops
    ):
        yield config.EXIT_PROFILE(
            stop_pct=stop_pct,
            tp_pct=tp_pct,
            scale_out=(),
            trailing_pct=trailing_pct,
            max_hold_days=max_hold_days,
            eod_flat=False,
        )
