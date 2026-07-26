"""The frozen D-13 v2 regime windows and tune/OOS splits for Phase 3's v2
iteration.

v1 concluded honestly with 0 survivors / 15 insufficient_sample: v1's
4-6 month OOS windows (trader/backtest/regimes.py) were arithmetically
incompatible with the 15-trade OOS floor at observed trade frequency. This
module is the owner-approved (2026-07-26) fix -- every OOS window below is
at least 365 days (12 months), computed from real, verified bar history
(03-RESEARCH.md's Universe section), never eyeballed.

This module reuses v1's own `Regime` frozen dataclass (import, never
redefine) so v2's windows carry the exact same tune_start/tune_end/
oos_start/oos_end contract and the same immutability guarantee. It is one
of frozen_config_v2.FROZEN_FILES_V2's five entries: any byte-level edit
after FROZEN_HASH_V2 is locked (see trader/backtest/frozen_config_v2.py) is
detected by verify_frozen_v2() and blocks every downstream v2 sweep/OOS
entrypoint.

v1's regimes.py and its REGIMES tuple are never imported for mutation and
are never touched by this module -- v2 is an additive, standalone freeze
surface (D-16).
"""

from __future__ import annotations

from trader.backtest.regimes import Regime
from trader.backtest.universe import (
    BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
    BUCKET_NEW_MEMECOIN,
    BUCKET_STOCK,
)

REGIMES_V2: tuple[Regime, ...] = (
    # Stock: extends v1's trending tune window backward for more tune data,
    # and its OOS window forward using the real post-2024 history that has
    # since accumulated by the project's current date (2026-07-26) -- 729
    # days of OOS, well above the 365-day floor.
    Regime(
        bucket=BUCKET_STOCK,
        label="trending_v2",
        tune_start="2019-01-01",
        tune_end="2024-06-30",
        oos_start="2024-07-01",
        oos_end="2026-06-30",
    ),
    # Stock: tune window identical to v1's choppy tune; OOS extended from
    # v1's thin 6-month tail to 18 real months of the same SPY-era history.
    Regime(
        bucket=BUCKET_STOCK,
        label="choppy_v2",
        tune_start="2015-01-01",
        tune_end="2016-06-30",
        oos_start="2016-07-01",
        oos_end="2017-12-31",
    ),
    # Crypto major/legacy-meme: same tune window as v1's crypto trending
    # regime; OOS extended forward to 2026-06-30, matching the stock
    # trending_v2 window in length (729 days).
    Regime(
        bucket=BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
        label="trending_v2",
        tune_start="2023-01-01",
        tune_end="2024-06-30",
        oos_start="2024-07-01",
        oos_end="2026-06-30",
    ),
    # Crypto major/legacy-meme: the full 2022 bear year as tune (wider than
    # v1's 8-month tune), OOS covering the real 2023-2024 recovery/bull
    # period -- far denser trade counts than v1's thin 4-month 2022 tail.
    Regime(
        bucket=BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
        label="bear_recovery_v2",
        tune_start="2022-01-01",
        tune_end="2022-12-31",
        oos_start="2023-01-01",
        oos_end="2024-12-31",
    ),
    # New memecoin: tune_start is symbol-relative (None) -- PEPE/BONK/WIF
    # each list on Binance at a different date, mirroring v1's own mania
    # regime. oos_end is 2026-01-01 (not 2025-12-31) so the OOS window is
    # a full calendar year (365 days), clearing the 12-month floor exactly.
    Regime(
        bucket=BUCKET_NEW_MEMECOIN,
        label="mania_recovery_v2",
        tune_start=None,
        tune_end="2024-12-31",
        oos_start="2025-01-01",
        oos_end="2026-01-01",
    ),
    # New memecoin: uses WIF's full available history up to just before the
    # project's current date (2026-07-26), already covered by the existing
    # (v1) full-history cache -- no new backfill needed. oos_end is
    # 2026-07-01 (not 2026-06-30) so the OOS window is a full calendar year
    # (365 days), clearing the 12-month floor exactly.
    Regime(
        bucket=BUCKET_NEW_MEMECOIN,
        label="current_v2",
        tune_start="2025-01-01",
        tune_end="2025-06-30",
        oos_start="2025-07-01",
        oos_end="2026-07-01",
    ),
)
