"""Frozen-config integrity tests for universe.py and regimes.py (STRAT-04/05).

Asserts the exact D-04 universe lists and D-08/D-09 regime windows are
present verbatim, that every regime's tune/OOS split is honest (no overlap),
and that Regime instances are immutable (standing rule 2's discipline
extended to regime config, not just exit profiles).
"""

import dataclasses

import pytest

from trader.backtest import regimes, universe


def test_stock_universe_has_18_unique_symbols():
    assert len(universe.STOCK_UNIVERSE) == 18
    assert len(set(universe.STOCK_UNIVERSE)) == 18
    for expected in [
        "AAPL", "MSFT", "GOOGL", "NVDA", "AMD", "TSLA", "AMZN", "META",
        "NFLX", "CRM", "ADBE", "COST", "JPM", "XOM", "UNH", "WMT", "HD", "DIS",
    ]:
        assert expected in universe.STOCK_UNIVERSE


def test_crypto_major_legacy_meme_universe_exact():
    assert universe.CRYPTO_MAJOR_LEGACY_MEME_UNIVERSE == [
        "BTC/USDT", "ETH/USDT", "DOGE/USDT", "SHIB/USDT",
    ]


def test_new_memecoin_universe_exact():
    assert universe.NEW_MEMECOIN_UNIVERSE == ["PEPE/USDT", "BONK/USDT", "WIF/USDT"]


def test_universe_by_bucket_maps_all_three_buckets():
    assert universe.UNIVERSE_BY_BUCKET[universe.BUCKET_STOCK] == universe.STOCK_UNIVERSE
    assert (
        universe.UNIVERSE_BY_BUCKET[universe.BUCKET_CRYPTO_MAJOR_LEGACY_MEME]
        == universe.CRYPTO_MAJOR_LEGACY_MEME_UNIVERSE
    )
    assert (
        universe.UNIVERSE_BY_BUCKET[universe.BUCKET_NEW_MEMECOIN]
        == universe.NEW_MEMECOIN_UNIVERSE
    )


def test_bucket_constants_distinct_from_asset_class_values():
    # These are sweep/regime GROUPING buckets, never per-symbol asset_class
    # values ("stock"/"crypto_major"/"memecoin") passed to fills.py/ledger.
    assert universe.BUCKET_STOCK == "stock"
    assert universe.BUCKET_CRYPTO_MAJOR_LEGACY_MEME == "crypto_major_legacy_meme"
    assert universe.BUCKET_NEW_MEMECOIN == "new_memecoin"


def test_regimes_is_six_entries_two_per_bucket():
    assert len(regimes.REGIMES) == 6
    for bucket in (
        universe.BUCKET_STOCK,
        universe.BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
        universe.BUCKET_NEW_MEMECOIN,
    ):
        assert sum(1 for r in regimes.REGIMES if r.bucket == bucket) == 2


def test_every_regime_tune_end_before_oos_start_and_oos_start_before_oos_end():
    for regime in regimes.REGIMES:
        assert regime.tune_end < regime.oos_start
        assert regime.oos_start <= regime.oos_end


def test_only_new_memecoin_mania_has_null_tune_start():
    null_tune_start_regimes = [r for r in regimes.REGIMES if r.tune_start is None]
    assert len(null_tune_start_regimes) == 1
    only = null_tune_start_regimes[0]
    assert only.bucket == universe.BUCKET_NEW_MEMECOIN
    assert only.label == "mania"

    for regime in regimes.REGIMES:
        if regime is only:
            continue
        assert isinstance(regime.tune_start, str)


def test_regime_instances_are_frozen():
    sample = regimes.REGIMES[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        sample.tune_end = "2099-01-01"


def test_regime_window_dates_match_research_doc():
    expected = {
        (universe.BUCKET_STOCK, "trending"): (
            "2023-01-01", "2024-06-30", "2024-07-01", "2024-12-31",
        ),
        (universe.BUCKET_STOCK, "choppy"): (
            "2015-01-01", "2016-06-30", "2016-07-01", "2016-12-31",
        ),
        (universe.BUCKET_CRYPTO_MAJOR_LEGACY_MEME, "trending"): (
            "2023-01-01", "2024-06-30", "2024-07-01", "2024-12-31",
        ),
        (universe.BUCKET_CRYPTO_MAJOR_LEGACY_MEME, "bear"): (
            "2022-01-01", "2022-08-31", "2022-09-01", "2022-12-31",
        ),
        (universe.BUCKET_NEW_MEMECOIN, "mania"): (
            None, "2024-08-31", "2024-09-01", "2024-12-31",
        ),
        (universe.BUCKET_NEW_MEMECOIN, "correction"): (
            "2025-01-01", "2025-08-31", "2025-09-01", "2025-12-31",
        ),
    }
    actual = {(r.bucket, r.label): (r.tune_start, r.tune_end, r.oos_start, r.oos_end)
              for r in regimes.REGIMES}
    assert actual == expected
