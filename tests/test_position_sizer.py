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
from hypothesis import given, settings
from hypothesis import strategies as st

from trader.risk import config, sizer

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

    # Pin TOP_N=3 for this scenario so the slot-exclusion MATH stays
    # tested regardless of the live SIZER_TOP_N (raised to 20 by the
    # 2026-08-08 sanctioned recalibration).
    from types import SimpleNamespace

    from trader.risk import config as risk_config

    top3_config = SimpleNamespace(**{
        name: getattr(risk_config, name)
        for name in dir(risk_config)
        if name.startswith("SIZER_") or name.startswith("MIN_")
        or name.startswith("MAX_") or name.startswith("CORRELATION_")
        or name.startswith("LIQUIDITY_")
    })
    top3_config.SIZER_TOP_N = 3

    result = sizer.size_positions(
        scored_candidates, equity=100_000.0, open_positions=open_positions,
        config=top3_config,
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


# --------------------------------------------------------------------------
# hypothesis property tests: cap invariants for ANY generated input
# (04-RESEARCH.md Q5 -- CI-speed profile scoped locally per test, no
# conftest.py or pyproject.toml change)
# --------------------------------------------------------------------------

_SCORE = st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False)
_VOLATILITY = st.floats(min_value=0.001, max_value=1.0, allow_nan=False, allow_infinity=False)
_ASSET_CLASS = st.sampled_from(["stock", "crypto_major", "memecoin"])


@st.composite
def _scored_candidates(draw):
    n = draw(st.integers(min_value=1, max_value=3))
    return [
        {
            "symbol": f"C{i}",
            "venue": "test-venue",
            "asset_class": draw(_ASSET_CLASS),
            "score": draw(_SCORE),
            "volatility": draw(_VOLATILITY),
        }
        for i in range(n)
    ]


@st.composite
def _open_positions(draw):
    """Existing open positions must already respect the caps that would
    have applied when each was originally sized -- an open memecoin
    position that already violates SIZER_MEMECOIN_CAP on its own is not a
    realistic input, since the sizer never re-sizes an open position and
    could not have produced such a position itself.
    """
    n = draw(st.integers(min_value=0, max_value=2))
    positions = []
    remaining = 0.8  # weights sum to at most 0.8, leaving room per the plan
    memecoin_remaining = config.SIZER_MEMECOIN_CAP
    for i in range(n):
        asset_class = draw(_ASSET_CLASS)
        max_weight = remaining
        if asset_class == "memecoin":
            max_weight = min(max_weight, memecoin_remaining)
        weight = draw(
            st.floats(min_value=0.0, max_value=max_weight, allow_nan=False, allow_infinity=False)
        )
        positions.append(
            {
                "symbol": f"OPEN{i}",
                "venue": "test-venue",
                "asset_class": asset_class,
                "weight": weight,
            }
        )
        remaining -= weight
        if asset_class == "memecoin":
            memecoin_remaining -= weight
    return positions


@settings(max_examples=50, deadline=None)
@given(scored_candidates=_scored_candidates(), open_positions=_open_positions())
def test_cap_invariants_hold_for_any_generated_input(scored_candidates, open_positions):
    result = sizer.size_positions(
        scored_candidates, equity=100_000.0, open_positions=open_positions
    )

    # No returned position weight exceeds the 50% single-position cap.
    for position in result["positions"]:
        assert position["weight"] <= config.SIZER_SINGLE_POSITION_CAP + 1e-9

    # Total memecoin weight (open + new) never exceeds the 10% cap.
    open_memecoin = sum(
        op["weight"] for op in open_positions if op["asset_class"] == "memecoin"
    )
    new_memecoin = sum(
        p["weight"] for p in result["positions"] if p["asset_class"] == "memecoin"
    )
    assert open_memecoin + new_memecoin <= config.SIZER_MEMECOIN_CAP + 1e-9

    # cash_weight is never negative.
    assert result["cash_weight"] >= -1e-9

    # sum(all weights) + cash_weight == 1.0 within a tight tolerance.
    total = (
        sum(op["weight"] for op in open_positions)
        + sum(p["weight"] for p in result["positions"])
        + result["cash_weight"]
    )
    assert total == pytest.approx(1.0, abs=1e-6)
