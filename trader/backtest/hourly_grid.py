"""The frozen HOURLY exit-profile grid and tune/OOS windows (intraday
track, owner directive 2026-08-04) -- pre-registered BEFORE any hourly
backtest result exists (standing rule 1).

UNIT SEMANTICS -- read this before touching anything: the engine's hold
counter counts BARS, so on 1h bars every EXIT_PROFILE.max_hold_days value
below is a maximum hold in HOURS (24 = one day, 168 = one week). The
field name is inherited from the daily grid's frozen dataclass; the daily
grid itself is untouched.

The grid is deliberately leaner than the daily one (24 cells vs 270):
hourly cells cost ~10x more compute, and hourly stops live in the
single-digit percent range -- a -30% stop on a 1h bar is not an exit
policy, it is a coma. Stops/targets sized to hourly crypto volatility.

Windows (one pair per bucket, >= 12-month OOS mirroring regimes_v2's
floor):
- crypto_major: tune 2023-01-01 .. 2025-06-30, OOS 2025-07-01 .. 2026-07-31
- new_memecoin: tune from listing .. 2025-09-30, OOS 2025-10-01 .. 2026-07-31

This module is one of frozen_config_hourly.py's FROZEN_FILES_HOURLY
entries.
"""

from __future__ import annotations

from trader.backtest.config import EXIT_PROFILE
from trader.backtest.regimes import Regime
from trader.backtest.universe import (
    BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
    BUCKET_NEW_MEMECOIN,
)

HOURLY_STOPS: tuple[float, ...] = (-0.03, -0.06)
HOURLY_TPS: tuple[float | None, ...] = (0.03, 0.06, None)
HOURLY_TRAILS: tuple[float | None, ...] = (None, 0.03)
HOURLY_MAX_HOLD_BARS: tuple[int, ...] = (24, 168)  # HOURS (see docstring)


def hourly_exit_profile_grid(bucket: str) -> list[EXIT_PROFILE]:
    """Every frozen hourly exit profile -- 2 stops x 3 tps x 2 trails x
    2 holds = 24 cells, identical for both crypto buckets (bucket accepted
    for signature parity with the daily grid)."""
    profiles = []
    for stop in HOURLY_STOPS:
        for tp in HOURLY_TPS:
            for trail in HOURLY_TRAILS:
                for hold in HOURLY_MAX_HOLD_BARS:
                    profiles.append(
                        EXIT_PROFILE(
                            stop_pct=stop,
                            tp_pct=tp,
                            scale_out=(),
                            trailing_pct=trail,
                            max_hold_days=hold,  # HOURS on 1h bars
                            eod_flat=False,
                        )
                    )
    return profiles


REGIMES_1H: tuple[Regime, ...] = (
    Regime(
        bucket=BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
        label="hourly_v1",
        tune_start="2023-01-01",
        tune_end="2025-06-30",
        oos_start="2025-07-01",
        oos_end="2026-07-31",
    ),
    Regime(
        bucket=BUCKET_NEW_MEMECOIN,
        label="hourly_v1",
        tune_start=None,  # symbol-relative listing start
        tune_end="2025-09-30",
        oos_start="2025-10-01",
        oos_end="2026-07-31",
    ),
)
