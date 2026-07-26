"""The frozen D-08/D-09 regime windows and tune/OOS splits for Phase 3.

Every date below is committed verbatim from 03-RESEARCH.md's Regime Windows
section (real return/drawdown stats computed from live/cached bar data,
2026-07-26) -- not re-derived here. This module is one of the three
frozen_config.FROZEN_FILES entries: any byte-level edit after FROZEN_HASH is
locked (see trader/backtest/frozen_config.py) is detected by verify_frozen()
and blocks every downstream sweep/OOS entrypoint.

Standing rule 1 ("never edit graduation/kill criteria while looking at
results") applies here exactly as it does to exit profiles -- these regime
windows must be frozen and reviewable before any sweep cell runs, which is
why Regime is an immutable frozen dataclass, not a mutable config dict.
"""

from __future__ import annotations

from dataclasses import dataclass

from trader.backtest.universe import (
    BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
    BUCKET_NEW_MEMECOIN,
    BUCKET_STOCK,
)


@dataclass(frozen=True)
class Regime:
    """One frozen regime window with its tune/OOS split (D-08/D-09).

    tune_start is None only for new_memecoin's "mania" regime, where the
    tune window starts at the symbol's own first bar (symbol-relative,
    since PEPE/BONK/WIF each list on Binance at different dates) rather
    than a fixed calendar date shared across the bucket.
    """

    bucket: str
    label: str
    tune_start: str | None
    tune_end: str
    oos_start: str
    oos_end: str


REGIMES: tuple[Regime, ...] = (
    Regime(
        bucket=BUCKET_STOCK,
        label="trending",
        tune_start="2023-01-01",
        tune_end="2024-06-30",
        oos_start="2024-07-01",
        oos_end="2024-12-31",
    ),
    Regime(
        bucket=BUCKET_STOCK,
        label="choppy",
        tune_start="2015-01-01",
        tune_end="2016-06-30",
        oos_start="2016-07-01",
        oos_end="2016-12-31",
    ),
    Regime(
        bucket=BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
        label="trending",
        tune_start="2023-01-01",
        tune_end="2024-06-30",
        oos_start="2024-07-01",
        oos_end="2024-12-31",
    ),
    Regime(
        bucket=BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
        label="bear",
        tune_start="2022-01-01",
        tune_end="2022-08-31",
        oos_start="2022-09-01",
        oos_end="2022-12-31",
    ),
    Regime(
        bucket=BUCKET_NEW_MEMECOIN,
        label="mania",
        tune_start=None,
        tune_end="2024-08-31",
        oos_start="2024-09-01",
        oos_end="2024-12-31",
    ),
    Regime(
        bucket=BUCKET_NEW_MEMECOIN,
        label="correction",
        tune_start="2025-01-01",
        tune_end="2025-08-31",
        oos_start="2025-09-01",
        oos_end="2025-12-31",
    ),
)
