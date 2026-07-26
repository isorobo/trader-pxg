"""Tests for trader.risk.gate -- RISK-01's pure risk-gate function.

Covers liquidity, listing-age, spread, and correlation checks (04-RESEARCH.md
Q1/Q2), the exact reason-code contract, and the date-aligned N-way
correlation-cluster elimination.
"""

from __future__ import annotations

import pandas as pd
import pytest

from trader.risk import config
from trader.risk import gate


def _bars(n, start_close=100.0, daily_volume=50_000.0, start="2026-01-01"):
    """n ascending daily bars with a flat close/volume, ts as ISO dates."""
    dates = pd.date_range(start=start, periods=n, freq="D")
    return [
        {
            "ts": d.strftime("%Y-%m-%d"),
            "open": start_close,
            "high": start_close,
            "low": start_close,
            "close": start_close,
            "volume": daily_volume,
        }
        for d in dates
    ]


def _bars_with_returns(n, closes, start="2026-01-01"):
    """n ascending daily bars with an explicit close-price sequence."""
    dates = pd.date_range(start=start, periods=n, freq="D")
    return [
        {
            "ts": d.strftime("%Y-%m-%d"),
            "open": c,
            "high": c,
            "low": c,
            "close": c,
            "volume": 100_000.0,
        }
        for d, c in zip(dates, closes)
    ]


def _candidate(symbol, venue, score):
    return {"symbol": symbol, "venue": venue, "score": score}


def _entry(bars, asset_class, spread_pct):
    return {"bars": bars, "asset_class": asset_class, "spread_pct": spread_pct}


# --------------------------------------------------------------------------
# Liquidity
# --------------------------------------------------------------------------


def test_stock_below_min_dollar_volume_rejected_liquidity():
    # $1000/day dollar volume (10.0 close * 100 volume) << $1M floor.
    bars = _bars(25, start_close=10.0, daily_volume=100.0)
    candidates = [_candidate("ILLQ", "nasdaq", 0.5)]
    market_data = {("ILLQ", "nasdaq"): _entry(bars, "stock", 0.01)}

    accepted, rejected = gate.apply_risk_gate(candidates, market_data)

    assert accepted == []
    assert len(rejected) == 1
    assert rejected[0]["symbol"] == "ILLQ"
    assert rejected[0]["reason_code"] == gate.REJECT_LIQUIDITY


def test_memecoin_below_min_quote_volume_rejected_liquidity():
    # $1000/day quote volume << $250k memecoin floor.
    bars = _bars(35, start_close=0.01, daily_volume=100_000.0)
    candidates = [_candidate("DEADCOIN", "binance", 0.5)]
    market_data = {("DEADCOIN", "binance"): _entry(bars, "memecoin", 0.01)}

    accepted, rejected = gate.apply_risk_gate(candidates, market_data)

    assert rejected[0]["reason_code"] == gate.REJECT_LIQUIDITY


def test_crypto_major_below_min_quote_volume_rejected_liquidity():
    # $10,000/day quote volume << $5M crypto_major floor.
    bars = _bars(35, start_close=1.0, daily_volume=10_000.0)
    candidates = [_candidate("WEAKCOIN", "binance", 0.5)]
    market_data = {("WEAKCOIN", "binance"): _entry(bars, "crypto_major", 0.01)}

    accepted, rejected = gate.apply_risk_gate(candidates, market_data)

    assert rejected[0]["reason_code"] == gate.REJECT_LIQUIDITY


def test_liquidity_uses_median_not_mean():
    # 19 low-volume days + 1 huge-volume outlier day. Mean would clear the
    # $1M floor; the median (per 04-RESEARCH.md Q1) must not.
    low_bars = _bars(19, start_close=10.0, daily_volume=1_000.0)  # $10k/day
    spike = [
        {
            "ts": "2026-02-01",
            "open": 10.0,
            "high": 10.0,
            "low": 10.0,
            "close": 10.0,
            "volume": 10_000_000.0,  # $100M spike day
        }
    ]
    bars = low_bars + spike
    candidates = [_candidate("SPIKY", "nasdaq", 0.5)]
    market_data = {("SPIKY", "nasdaq"): _entry(bars, "stock", 0.01)}

    accepted, rejected = gate.apply_risk_gate(candidates, market_data)

    assert rejected[0]["reason_code"] == gate.REJECT_LIQUIDITY


# --------------------------------------------------------------------------
# Listing age
# --------------------------------------------------------------------------


def test_below_min_listing_age_rejected():
    # Only 5 bars, well below MIN_LISTING_AGE_DAYS=30. High volume/tight
    # spread so listing age is the only failing check.
    bars = _bars(5, start_close=100.0, daily_volume=1_000_000.0)
    candidates = [_candidate("NEWTOK", "binance", 0.5)]
    market_data = {("NEWTOK", "binance"): _entry(bars, "crypto_major", 0.01)}

    accepted, rejected = gate.apply_risk_gate(candidates, market_data)

    assert accepted == []
    assert rejected[0]["reason_code"] == gate.REJECT_LISTING_AGE


# --------------------------------------------------------------------------
# Spread
# --------------------------------------------------------------------------


def test_spread_exceeding_max_for_asset_class_rejected():
    # Ample volume + listing age so only spread fails.
    bars = _bars(40, start_close=100.0, daily_volume=1_000_000.0)
    candidates = [_candidate("WIDESPRD", "nasdaq", 0.5)]
    # stock ceiling is 0.05 (config.MAX_SPREAD_PCT["stock"])
    market_data = {("WIDESPRD", "nasdaq"): _entry(bars, "stock", 1.0)}

    accepted, rejected = gate.apply_risk_gate(candidates, market_data)

    assert accepted == []
    assert rejected[0]["reason_code"] == gate.REJECT_SPREAD


# --------------------------------------------------------------------------
# Check order: liquidity -> listing_age -> spread (first failure only)
# --------------------------------------------------------------------------


def test_first_failing_check_reports_liquidity_over_others():
    # Fails liquidity AND listing age AND spread -- only REJECT_LIQUIDITY
    # should surface.
    bars = _bars(5, start_close=1.0, daily_volume=10.0)
    candidates = [_candidate("TRIPLEFAIL", "nasdaq", 0.5)]
    market_data = {("TRIPLEFAIL", "nasdaq"): _entry(bars, "stock", 10.0)}

    accepted, rejected = gate.apply_risk_gate(candidates, market_data)

    assert rejected[0]["reason_code"] == gate.REJECT_LIQUIDITY


def test_first_failing_check_reports_listing_age_over_spread():
    # Passes liquidity, fails listing age AND spread -- only
    # REJECT_LISTING_AGE should surface.
    bars = _bars(5, start_close=100.0, daily_volume=1_000_000.0)
    candidates = [_candidate("AGEOVERSPREAD", "nasdaq", 0.5)]
    market_data = {("AGEOVERSPREAD", "nasdaq"): _entry(bars, "stock", 10.0)}

    accepted, rejected = gate.apply_risk_gate(candidates, market_data)

    assert rejected[0]["reason_code"] == gate.REJECT_LISTING_AGE


# --------------------------------------------------------------------------
# Accept path: tagging
# --------------------------------------------------------------------------


def test_passing_all_checks_is_accepted_and_tagged():
    bars = _bars(40, start_close=100.0, daily_volume=1_000_000.0)
    candidates = [_candidate("CLEAN1", "nasdaq", 0.5)]
    market_data = {("CLEAN1", "nasdaq"): _entry(bars, "stock", 0.01)}

    accepted, rejected = gate.apply_risk_gate(candidates, market_data)

    assert rejected == []
    assert len(accepted) == 1
    assert accepted[0]["symbol"] == "CLEAN1"
    assert accepted[0]["asset_class"] == "stock"
    assert accepted[0]["exit_profile_tag"] == "stock"


# --------------------------------------------------------------------------
# Correlation: pairwise
# --------------------------------------------------------------------------


def test_correlation_pair_rejects_lower_scored_member():
    # Two candidates whose closes move in perfect lockstep -> correlation 1.0.
    closes = [100.0 + i for i in range(70)]
    bars_a = _bars_with_returns(70, closes)
    bars_b = _bars_with_returns(70, [c * 2 for c in closes])

    candidates = [
        _candidate("CORRA", "nasdaq", 0.6),
        _candidate("CORRB", "nasdaq", 0.9),
    ]
    market_data = {
        ("CORRA", "nasdaq"): _entry(bars_a, "stock", 0.01),
        ("CORRB", "nasdaq"): _entry(bars_b, "stock", 0.01),
    }

    accepted, rejected = gate.apply_risk_gate(candidates, market_data)

    assert len(accepted) == 1
    assert accepted[0]["symbol"] == "CORRB"
    assert len(rejected) == 1
    assert rejected[0]["symbol"] == "CORRA"
    assert rejected[0]["reason_code"] == gate.REJECT_CORRELATION


def test_correlation_uncorrelated_pair_both_accepted():
    closes_a = [100.0 + i for i in range(70)]
    # Alternating up/down -- should not correlate with a steady uptrend.
    closes_b = [100.0 + (5 if i % 2 == 0 else -5) for i in range(70)]
    bars_a = _bars_with_returns(70, closes_a)
    bars_b = _bars_with_returns(70, closes_b)

    candidates = [
        _candidate("STEADY", "nasdaq", 0.6),
        _candidate("CHOPPY", "nasdaq", 0.9),
    ]
    market_data = {
        ("STEADY", "nasdaq"): _entry(bars_a, "stock", 0.01),
        ("CHOPPY", "nasdaq"): _entry(bars_b, "stock", 0.01),
    }

    accepted, rejected = gate.apply_risk_gate(candidates, market_data)

    assert rejected == []
    assert len(accepted) == 2


def test_correlation_below_min_overlap_is_indeterminate_not_rejected():
    # Two candidates that barely clear the 30-bar listing-age floor but whose
    # calendars only share a few dates once misaligned -- overlap below
    # CORRELATION_MIN_OVERLAP (30), so neither is rejected on this pair.
    closes = [100.0 + i for i in range(31)]
    bars_a = _bars_with_returns(31, closes, start="2026-01-01")
    bars_b = _bars_with_returns(31, [c * 2 for c in closes], start="2026-03-01")

    candidates = [
        _candidate("SPARSEA", "nasdaq", 0.6),
        _candidate("SPARSEB", "nasdaq", 0.9),
    ]
    market_data = {
        ("SPARSEA", "nasdaq"): _entry(bars_a, "stock", 0.01),
        ("SPARSEB", "nasdaq"): _entry(bars_b, "stock", 0.01),
    }

    accepted, rejected = gate.apply_risk_gate(candidates, market_data)

    assert rejected == []
    assert len(accepted) == 2


def test_correlation_date_aligned_stock_crypto_calendar_mismatch():
    # Pitfall 1 regression: crypto bars include weekend dates the stock bars
    # lack. Positional zip would misalign returns; date-aligned inner join
    # must still detect the correlation correctly.
    dates = pd.date_range(start="2026-01-01", periods=100, freq="D")
    # Stock: business days only (drop weekends).
    stock_dates = [d for d in dates if d.weekday() < 5]
    closes_stock = [100.0 + i for i in range(len(stock_dates))]
    bars_stock = [
        {
            "ts": d.strftime("%Y-%m-%d"),
            "open": c,
            "high": c,
            "low": c,
            "close": c,
            "volume": 1_000_000.0,
        }
        for d, c in zip(stock_dates, closes_stock)
    ]
    # Crypto: every calendar day, tracking the same underlying trend as the
    # stock on shared dates (correlated), with extra weekend data points.
    close_by_date = {d.strftime("%Y-%m-%d"): c for d, c in zip(stock_dates, closes_stock)}
    running = closes_stock[0]
    bars_crypto = []
    for d in dates:
        key = d.strftime("%Y-%m-%d")
        if key in close_by_date:
            running = close_by_date[key] * 3
        else:
            running = running  # flat on weekends the stock doesn't trade
        bars_crypto.append(
            {
                "ts": key,
                "open": running,
                "high": running,
                "low": running,
                "close": running,
                "volume": 1_000_000.0,
            }
        )

    candidates = [
        _candidate("STK", "nasdaq", 0.6),
        _candidate("CRY", "binance", 0.9),
    ]
    market_data = {
        ("STK", "nasdaq"): _entry(bars_stock, "stock", 0.01),
        ("CRY", "binance"): _entry(bars_crypto, "crypto_major", 0.01),
    }

    accepted, rejected = gate.apply_risk_gate(candidates, market_data)

    # STK and CRY move together on shared trading dates -> correlated ->
    # lower-scored STK rejected, higher-scored CRY survives.
    assert len(rejected) == 1
    assert rejected[0]["symbol"] == "STK"
    assert rejected[0]["reason_code"] == gate.REJECT_CORRELATION
    assert len(accepted) == 1
    assert accepted[0]["symbol"] == "CRY"


# --------------------------------------------------------------------------
# Correlation: N-way cluster (greedy elimination)
# --------------------------------------------------------------------------


def test_correlation_three_way_fully_connected_cluster_resolves_to_one_survivor():
    # A, B, C all move in lockstep (fully-connected cluster, corr ~1.0 for
    # every pair). Highest-scored (C) should be the sole survivor.
    closes = [100.0 + i for i in range(70)]
    bars_a = _bars_with_returns(70, closes)
    bars_b = _bars_with_returns(70, [c * 2 for c in closes])
    bars_c = _bars_with_returns(70, [c * 3 for c in closes])

    candidates = [
        _candidate("CLUSTA", "nasdaq", 0.5),
        _candidate("CLUSTB", "nasdaq", 0.7),
        _candidate("CLUSTC", "nasdaq", 0.9),
    ]
    market_data = {
        ("CLUSTA", "nasdaq"): _entry(bars_a, "stock", 0.01),
        ("CLUSTB", "nasdaq"): _entry(bars_b, "stock", 0.01),
        ("CLUSTC", "nasdaq"): _entry(bars_c, "stock", 0.01),
    }

    accepted, rejected = gate.apply_risk_gate(candidates, market_data)

    assert len(accepted) == 1
    assert accepted[0]["symbol"] == "CLUSTC"
    assert len(rejected) == 2
    rejected_symbols = {r["symbol"] for r in rejected}
    assert rejected_symbols == {"CLUSTA", "CLUSTB"}
    for r in rejected:
        assert r["reason_code"] == gate.REJECT_CORRELATION


# --------------------------------------------------------------------------
# Contract / hygiene
# --------------------------------------------------------------------------


def test_gate_module_has_no_strategies_import():
    import inspect

    source = inspect.getsource(gate)
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            assert "trader.backtest.strategies" not in stripped


def test_gate_module_has_no_inline_thresholds():
    import inspect

    source = inspect.getsource(gate)
    # Spot-check: the pinned numeric defaults must not appear as bare
    # literals anywhere outside config.py imports/usages.
    for literal in ["1_000_000.0", "5_000_000.0", "250_000.0", "0.8"]:
        assert literal not in source, f"found inline magic number {literal}"
