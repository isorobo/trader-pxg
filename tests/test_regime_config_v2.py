"""Frozen-config integrity tests for regimes_v2.py (STRAT-04/05, D-13).

Asserts the v2 regime windows fix v1's root cause -- OOS windows too short
to clear the 15-trade floor -- by requiring every regime's OOS window to be
at least 365 days, computed via real date arithmetic, not eyeballed. Also
proves regimes_v2 reuses v1's own `Regime` dataclass (never redefines it)
and never touches v1's regimes.py in the process.
"""

import dataclasses
from datetime import date

import pytest

from trader.backtest import regimes, universe
from trader.backtest import regimes_v2


def test_regimes_v2_is_six_entries_two_per_bucket():
    assert len(regimes_v2.REGIMES_V2) == 6
    for bucket in (
        universe.BUCKET_STOCK,
        universe.BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
        universe.BUCKET_NEW_MEMECOIN,
    ):
        assert sum(1 for r in regimes_v2.REGIMES_V2 if r.bucket == bucket) == 2


def test_regimes_v2_entries_are_v1_regime_instances():
    # Proves this module reuses trader.backtest.regimes.Regime rather than
    # defining a parallel dataclass.
    for entry in regimes_v2.REGIMES_V2:
        assert isinstance(entry, regimes.Regime)


def test_regimes_v2_entries_are_frozen():
    sample = regimes_v2.REGIMES_V2[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        sample.tune_end = "2099-01-01"


def test_every_regime_v2_tune_end_before_oos_start():
    for regime in regimes_v2.REGIMES_V2:
        assert regime.tune_end < regime.oos_start
        assert regime.oos_start <= regime.oos_end


def test_every_regime_v2_oos_window_is_at_least_365_days():
    for regime in regimes_v2.REGIMES_V2:
        start = date.fromisoformat(regime.oos_start)
        end = date.fromisoformat(regime.oos_end)
        assert (end - start).days >= 365, (
            f"{regime.bucket}/{regime.label}: OOS window is only "
            f"{(end - start).days} days, below the 365-day (12mo) floor"
        )


def test_only_new_memecoin_mania_recovery_v2_has_null_tune_start():
    null_tune_start_regimes = [r for r in regimes_v2.REGIMES_V2 if r.tune_start is None]
    assert len(null_tune_start_regimes) == 1
    only = null_tune_start_regimes[0]
    assert only.bucket == universe.BUCKET_NEW_MEMECOIN
    assert only.label == "mania_recovery_v2"

    for regime in regimes_v2.REGIMES_V2:
        if regime is only:
            continue
        assert isinstance(regime.tune_start, str)


def test_regime_v2_window_dates_exact():
    expected = {
        (universe.BUCKET_STOCK, "trending_v2"): (
            "2019-01-01", "2024-06-30", "2024-07-01", "2026-06-30",
        ),
        (universe.BUCKET_STOCK, "choppy_v2"): (
            "2015-01-01", "2016-06-30", "2016-07-01", "2017-12-31",
        ),
        (universe.BUCKET_CRYPTO_MAJOR_LEGACY_MEME, "trending_v2"): (
            "2023-01-01", "2024-06-30", "2024-07-01", "2026-06-30",
        ),
        (universe.BUCKET_CRYPTO_MAJOR_LEGACY_MEME, "bear_recovery_v2"): (
            "2022-01-01", "2022-12-31", "2023-01-01", "2024-12-31",
        ),
        (universe.BUCKET_NEW_MEMECOIN, "mania_recovery_v2"): (
            None, "2024-12-31", "2025-01-01", "2026-01-01",
        ),
        (universe.BUCKET_NEW_MEMECOIN, "current_v2"): (
            "2025-01-01", "2025-06-30", "2025-07-01", "2026-07-01",
        ),
    }
    actual = {
        (r.bucket, r.label): (r.tune_start, r.tune_end, r.oos_start, r.oos_end)
        for r in regimes_v2.REGIMES_V2
    }
    assert actual == expected


def test_v1_regimes_module_untouched():
    # Defensive re-check (T-03-24): v1's REGIMES tuple must still be exactly
    # what regimes.py froze in Plan 03-01 -- this plan never edits it.
    assert len(regimes.REGIMES) == 6
    assert regimes.REGIMES[0].bucket == universe.BUCKET_STOCK
    assert regimes.REGIMES[0].label == "trending"
    assert regimes.REGIMES[0].tune_start == "2023-01-01"
    assert regimes.REGIMES[0].oos_end == "2024-12-31"
