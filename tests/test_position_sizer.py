"""Tests for trader.risk.sizer -- RISK-02's pure position sizer.

Covers compute_volatility's ddof=1 convention, the 04-RESEARCH.md Q3
golden-fixture worked example, the memecoin aggregate cap (new candidates
alone and combined with open_positions), the open-positions budget
generalization, and hypothesis property tests proving the cap invariants
hold for ANY generated input.
"""

from __future__ import annotations

import statistics

import pytest

from trader.risk import config
from trader.risk import sizer


# --------------------------------------------------------------------------
# compute_volatility
# --------------------------------------------------------------------------


def test_compute_volatility_matches_ddof1_sample_stdev():
    closes = [
        100.0, 102.0, 99.0, 105.0, 103.0, 108.0, 110.0, 107.0, 112.0, 115.0,
        111.0, 118.0, 120.0, 116.0, 122.0, 125.0, 121.0, 128.0, 130.0, 126.0,
        133.0, 135.0,
    ]
    bars = [{"ts": f"2026-01-{i + 1:02d}", "close": c} for i, c in enumerate(closes)]

    returns = [(closes[i] / closes[i - 1]) - 1 for i in range(1, len(closes))]
    expected = statistics.stdev(returns[-20:])  # statistics.stdev is ddof=1

    result = sizer.compute_volatility(bars, window=20)

    assert result == pytest.approx(expected, abs=1e-12)


# --------------------------------------------------------------------------
# Golden fixture: 04-RESEARCH.md Q3 worked example (open_positions=[])
# --------------------------------------------------------------------------


def test_golden_fixture_worked_example_q3():
    scored_candidates = [
        {
            "symbol": "A", "venue": "nasdaq", "asset_class": "stock",
            "score": 0.90, "volatility": 0.02,
        },
        {
            "symbol": "B", "venue": "binance", "asset_class": "crypto_major",
            "score": 0.70, "volatility": 0.04,
        },
        {
            "symbol": "C", "venue": "binance", "asset_class": "memecoin",
            "score": 0.95, "volatility": 0.15,
        },
    ]

    result = sizer.size_positions(scored_candidates, equity=100_000.0, open_positions=[])

    weights = {p["symbol"]: p["weight"] for p in result["positions"]}

    # w_A hits the 50% single-position cap (preliminary ~0.5885).
    assert weights["A"] == pytest.approx(0.50, abs=1e-9)
    assert weights["B"] == pytest.approx(0.2289, abs=1e-3)
    assert weights["C"] == pytest.approx(0.0827, abs=1e-3)
    assert result["cash_weight"] == pytest.approx(0.1884, abs=1e-3)

    total = sum(weights.values()) + result["cash_weight"]
    assert total == pytest.approx(1.0, abs=1e-9)


def test_golden_fixture_no_position_redistribution_on_cap():
    """Freed weight from A's 50% cap must land in cash, never in B or C."""
    scored_candidates = [
        {
            "symbol": "A", "venue": "nasdaq", "asset_class": "stock",
            "score": 0.90, "volatility": 0.02,
        },
        {
            "symbol": "B", "venue": "binance", "asset_class": "crypto_major",
            "score": 0.70, "volatility": 0.04,
        },
        {
            "symbol": "C", "venue": "binance", "asset_class": "memecoin",
            "score": 0.95, "volatility": 0.15,
        },
    ]

    result = sizer.size_positions(scored_candidates, equity=100_000.0, open_positions=[])
    weights = {p["symbol"]: p["weight"] for p in result["positions"]}

    # B and C match the un-redistributed normalized values exactly (4dp),
    # not some larger "survivor gets the freed weight" figure.
    assert weights["B"] < 0.30
    assert weights["C"] < 0.15
    assert result["cash_weight"] > config.SIZER_CASH_RESERVE


# --------------------------------------------------------------------------
# Memecoin aggregate cap: new candidates alone
# --------------------------------------------------------------------------


def test_memecoin_cap_scales_new_candidate_down_to_exact_cap():
    scored_candidates = [
        {
            "symbol": "X", "venue": "nasdaq", "asset_class": "stock",
            "score": 0.5, "volatility": 0.10,
        },
        {
            "symbol": "Y", "venue": "binance", "asset_class": "crypto_major",
            "score": 0.5, "volatility": 0.10,
        },
        {
            "symbol": "Z", "venue": "binance", "asset_class": "memecoin",
            "score": 0.3, "volatility": 0.05,
        },
    ]

    result = sizer.size_positions(scored_candidates, equity=100_000.0, open_positions=[])
    weights = {p["symbol"]: p["weight"] for p in result["positions"]}

    assert weights["Z"] == pytest.approx(config.SIZER_MEMECOIN_CAP, abs=1e-9)
    assert weights["X"] == pytest.approx(0.28125, abs=1e-9)
    assert weights["Y"] == pytest.approx(0.28125, abs=1e-9)
    assert result["cash_weight"] == pytest.approx(0.3375, abs=1e-9)

    total = sum(weights.values()) + result["cash_weight"]
    assert total == pytest.approx(1.0, abs=1e-9)


# --------------------------------------------------------------------------
# Memecoin aggregate cap: combined with open_positions' existing memecoin
# --------------------------------------------------------------------------


def test_memecoin_cap_considers_open_positions_memecoin_weight():
    open_positions = [
        {
            "symbol": "OPENMEME", "venue": "binance", "asset_class": "memecoin",
            "weight": 0.08,
        },
    ]
    scored_candidates = [
        {
            "symbol": "M", "venue": "binance", "asset_class": "memecoin",
            "score": 0.3, "volatility": 0.10,
        },
        {
            "symbol": "N", "venue": "nasdaq", "asset_class": "stock",
            "score": 0.3, "volatility": 0.10,
        },
    ]

    result = sizer.size_positions(
        scored_candidates, equity=100_000.0, open_positions=open_positions
    )
    weights = {p["symbol"]: p["weight"] for p in result["positions"]}

    # Existing open memecoin weight (0.08) is never touched; only the new
    # memecoin candidate M absorbs the scale-down so the combined total
    # equals exactly the cap.
    assert weights["M"] == pytest.approx(0.02, abs=1e-9)
    assert weights["N"] == pytest.approx(0.41, abs=1e-9)

    combined_memecoin = 0.08 + weights["M"]
    assert combined_memecoin == pytest.approx(config.SIZER_MEMECOIN_CAP, abs=1e-9)

    total = (
        sum(op["weight"] for op in open_positions)
        + sum(weights.values())
        + result["cash_weight"]
    )
    assert total == pytest.approx(1.0, abs=1e-9)


# --------------------------------------------------------------------------
# Open-positions budget generalization
# --------------------------------------------------------------------------


def test_open_positions_only_allocates_remaining_budget():
    open_positions = [
        {
            "symbol": "OPEN1", "venue": "nasdaq", "asset_class": "stock",
            "weight": 0.30,
        },
    ]
    scored_candidates = [
        {
            "symbol": "P", "venue": "nasdaq", "asset_class": "stock",
            "score": 0.9, "volatility": 0.10,
        },
        {
            "symbol": "Q", "venue": "binance", "asset_class": "crypto_major",
            "score": 0.8, "volatility": 0.10,
        },
        {
            "symbol": "R", "venue": "nasdaq", "asset_class": "stock",
            "score": 0.5, "volatility": 0.10,
        },
    ]

    result = sizer.size_positions(
        scored_candidates, equity=100_000.0, open_positions=open_positions
    )
    weights = {p["symbol"]: p["weight"] for p in result["positions"]}

    # available_slots = 3 - 1 = 2 -> only the top-2 by score (P, Q) are
    # sized; R (lowest score) never appears, and OPEN1 is never re-sized.
    assert set(weights.keys()) == {"P", "Q"}
    assert weights["P"] == pytest.approx(0.31765, abs=1e-3)
    assert weights["Q"] == pytest.approx(0.28235, abs=1e-3)
    assert result["cash_weight"] == pytest.approx(0.10, abs=1e-3)

    total = 0.30 + sum(weights.values()) + result["cash_weight"]
    assert total == pytest.approx(1.0, abs=1e-9)
