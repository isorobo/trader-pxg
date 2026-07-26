"""D-07/RISK-04's exit-gate acceptance test -- Phase 4's literal exit
criterion (ROADMAP.md success criterion 1).

A committed 7-entry poisoned candidate list (04-RESEARCH.md Q6 /
04-05-PLAN.md <fixture>) run through the gate and sizer as a two-stage
pipeline:

  1. ILLQ         (stock)      -- below the stock liquidity floor
  2. NEWTOK/USDT   (memecoin)   -- below the minimum listing age
  3. WIDESPRD      (stock)      -- above the stock spread ceiling
  4a. CORRA        (stock)      -- lower-scored half of a fabricated
                                    correlated pair (rejected)
  4b. CORRB        (stock)      -- higher-scored half of the pair (survives)
  5. MEMER/USDT    (memecoin)   -- gate-accepted, sizer-clipped to the
                                    memecoin aggregate cap
  6. CLEAN1        (stock)      -- gate-accepted, sized normally
  7. CLEAN2        (crypto_major) -- gate-accepted, excluded from the
                                      sizer's top-3 (4th by score)

Task 1 asserts the gate-stage partition (with exact reason codes). Task 2
attaches sizer volatility inputs to the gate's accepted set and asserts the
full two-stage pipeline, including the memecoin cap clip and the
"caps never redistribute, only cash absorbs" invariant.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trader.risk import config, gate, sizer


def _bars(n, close=100.0, volume=50_000.0, start="2026-01-01"):
    """n ascending daily bars with a flat close/volume, ts as ISO dates."""
    dates = pd.date_range(start=start, periods=n, freq="D")
    return [
        {
            "ts": d.strftime("%Y-%m-%d"),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": volume,
        }
        for d in dates
    ]


def _correlated_pair_bars(start="2026-01-01"):
    """CORRA/CORRB (04-RESEARCH.md Q6 #4a/#4b): 60 bars each, fabricated via
    ``numpy.random.default_rng(42)`` so CORRA's returns and a 90%-weighted
    copy of them (mixed with independent noise) correlate above the 0.8
    threshold. Price series are reconstructed from each return series via
    cumulative product from an arbitrary start price (100.0).
    """
    rng = np.random.default_rng(42)
    returns_a = rng.normal(loc=0.0, scale=0.01, size=60)
    independent_noise = rng.normal(loc=0.0, scale=0.01, size=60)
    returns_b = 0.9 * returns_a + 0.1 * independent_noise

    closes_a = 100.0 * np.cumprod(1.0 + returns_a)
    closes_b = 100.0 * np.cumprod(1.0 + returns_b)

    dates = pd.date_range(start=start, periods=60, freq="D")
    bars_a = [
        {
            "ts": d.strftime("%Y-%m-%d"),
            "open": c, "high": c, "low": c, "close": c,
            "volume": 50_000.0,
        }
        for d, c in zip(dates, closes_a)
    ]
    bars_b = [
        {
            "ts": d.strftime("%Y-%m-%d"),
            "open": c, "high": c, "low": c, "close": c,
            "volume": 50_000.0,
        }
        for d, c in zip(dates, closes_b)
    ]
    return bars_a, bars_b


def _actual_pair_correlation(bars_a, bars_b):
    """The same date-aligned daily-return Pearson correlation the gate's
    own ``_pairwise_correlation`` computes internally -- used here purely
    as a setup self-check, not as a substitute for calling the gate.
    """
    closes_a = pd.Series([b["close"] for b in bars_a])
    closes_b = pd.Series([b["close"] for b in bars_b])
    returns_a = closes_a.pct_change().dropna().reset_index(drop=True)
    returns_b = closes_b.pct_change().dropna().reset_index(drop=True)
    return returns_a.corr(returns_b)


def _build_poisoned_fixture():
    """The committed 7-entry poisoned candidate list. Returns
    ``(candidates, market_data, corra_bars, corrb_bars)`` -- the pair's
    raw bars are returned separately so tests can self-verify the
    fabricated correlation before invoking the gate.
    """
    illq_bars = _bars(25, close=10.0, volume=15_000.0)
    newtok_bars = _bars(5, close=1.0, volume=500_000.0)
    widesprd_bars = _bars(200, close=100.0, volume=50_000.0)
    corra_bars, corrb_bars = _correlated_pair_bars()
    memer_bars = _bars(40, close=1.0, volume=500_000.0)
    clean1_bars = _bars(40, close=100.0, volume=50_000.0)
    clean2_bars = _bars(40, close=100.0, volume=100_000.0)

    candidates = [
        {"symbol": "ILLQ", "venue": "nasdaq", "score": 0.5},
        {"symbol": "NEWTOK/USDT", "venue": "binance", "score": 0.5},
        {"symbol": "WIDESPRD", "venue": "nasdaq", "score": 0.5},
        {"symbol": "CORRA", "venue": "nasdaq", "score": 0.6},
        {"symbol": "CORRB", "venue": "nasdaq", "score": 0.9},
        {"symbol": "MEMER/USDT", "venue": "binance", "score": 0.95},
        {"symbol": "CLEAN1", "venue": "nasdaq", "score": 0.7},
        {"symbol": "CLEAN2", "venue": "binance", "score": 0.6},
    ]

    market_data = {
        ("ILLQ", "nasdaq"): {
            "bars": illq_bars, "asset_class": "stock", "spread_pct": 0.01,
        },
        ("NEWTOK/USDT", "binance"): {
            "bars": newtok_bars, "asset_class": "memecoin", "spread_pct": 0.01,
        },
        ("WIDESPRD", "nasdaq"): {
            "bars": widesprd_bars, "asset_class": "stock", "spread_pct": 0.5,
        },
        ("CORRA", "nasdaq"): {
            "bars": corra_bars, "asset_class": "stock", "spread_pct": 0.01,
        },
        ("CORRB", "nasdaq"): {
            "bars": corrb_bars, "asset_class": "stock", "spread_pct": 0.01,
        },
        ("MEMER/USDT", "binance"): {
            "bars": memer_bars, "asset_class": "memecoin", "spread_pct": 0.01,
        },
        ("CLEAN1", "nasdaq"): {
            "bars": clean1_bars, "asset_class": "stock", "spread_pct": 0.01,
        },
        ("CLEAN2", "binance"): {
            "bars": clean2_bars, "asset_class": "crypto_major", "spread_pct": 0.01,
        },
    }

    return candidates, market_data, corra_bars, corrb_bars


# --------------------------------------------------------------------------
# Task 1: gate-stage partition
# --------------------------------------------------------------------------


def test_gate_stage_poisoned_list_matches_research_q6():
    candidates, market_data, corra_bars, corrb_bars = _build_poisoned_fixture()

    # Self-verifying setup assertion (04-RESEARCH.md Q6 / Pitfall 1): the
    # fabricated CORRA/CORRB pair's actual computed correlation must exceed
    # the 0.8 threshold BEFORE any gate assertion depends on it, so this
    # fixture cannot silently drift below the threshold and pass for the
    # wrong reason.
    actual_correlation = _actual_pair_correlation(corra_bars, corrb_bars)
    assert abs(actual_correlation) > config.CORRELATION_THRESHOLD

    accepted, rejected = gate.apply_risk_gate(candidates, market_data, config)

    rejected_by_symbol = {r["symbol"]: r["reason_code"] for r in rejected}
    assert rejected_by_symbol == {
        "ILLQ": gate.REJECT_LIQUIDITY,
        "NEWTOK/USDT": gate.REJECT_LISTING_AGE,
        "WIDESPRD": gate.REJECT_SPREAD,
        "CORRA": gate.REJECT_CORRELATION,
    }

    accepted_symbols = {a["symbol"] for a in accepted}
    assert accepted_symbols == {"CORRB", "MEMER/USDT", "CLEAN1", "CLEAN2"}


# --------------------------------------------------------------------------
# Task 2: two-stage pipeline -- sizer clips the memecoin allocation
# --------------------------------------------------------------------------


def test_two_stage_pipeline_sizer_clips_memecoin_allocation():
    candidates, market_data, corra_bars, corrb_bars = _build_poisoned_fixture()

    accepted, rejected = gate.apply_risk_gate(candidates, market_data, config)
    assert {a["symbol"] for a in accepted} == {"CORRB", "MEMER/USDT", "CLEAN1", "CLEAN2"}

    # Sizer volatility is hardcoded per candidate here (04-05-PLAN.md Task
    # 2 <action>) -- this test exercises the gate+sizer reason-code/clip
    # contract, not compute_volatility's own math, which is already
    # unit-tested separately in tests/test_position_sizer.py.
    volatility_by_symbol = {
        "MEMER/USDT": 0.03,
        "CORRB": 0.04,
        "CLEAN1": 0.05,
        "CLEAN2": 0.06,
    }
    scored_candidates = [
        {**candidate, "volatility": volatility_by_symbol[candidate["symbol"]]}
        for candidate in accepted
    ]

    result = sizer.size_positions(
        scored_candidates=scored_candidates,
        equity=100_000.0,
        open_positions=[],
        config=config,
    )
    weights = {p["symbol"]: p["weight"] for p in result["positions"]}

    # Top-3 by score among the gate's 4 accepted candidates: MEMER/USDT
    # (0.95), CORRB (0.9), CLEAN1 (0.7). CLEAN2 (0.6) is 4th by score and
    # is excluded entirely.
    assert set(weights.keys()) == {"MEMER/USDT", "CORRB", "CLEAN1"}

    # Worked arithmetic (04-05-PLAN.md <fixture>): raw = score/volatility,
    # normalized to available_weight = 0.90 (open_positions=[]), single-
    # position cap (0.50) not triggered, memecoin cap (0.10) clips
    # MEMER/USDT's raw-normalized weight (~0.4181) down to exactly 0.10.
    raw = {
        "MEMER/USDT": 0.95 / 0.03,
        "CORRB": 0.9 / 0.04,
        "CLEAN1": 0.7 / 0.05,
    }
    raw_sum = sum(raw.values())
    available_weight = 1.0 - config.SIZER_CASH_RESERVE
    preliminary = {k: (v / raw_sum) * available_weight for k, v in raw.items()}

    assert weights["MEMER/USDT"] == pytest.approx(config.SIZER_MEMECOIN_CAP, abs=1e-9)
    assert weights["CORRB"] == pytest.approx(preliminary["CORRB"], rel=1e-3)
    assert weights["CLEAN1"] == pytest.approx(preliminary["CLEAN1"], rel=1e-3)

    # Freed weight (preliminary MEMER/USDT weight minus the 0.10 clip) flows
    # to cash, never redistributed to CORRB/CLEAN1 (04-RESEARCH.md Q3/A6).
    expected_cash = 1.0 - config.SIZER_MEMECOIN_CAP - preliminary["CORRB"] - preliminary["CLEAN1"]
    assert result["cash_weight"] == pytest.approx(expected_cash, rel=1e-3)

    total = sum(weights.values()) + result["cash_weight"]
    assert total == pytest.approx(1.0, abs=1e-9)
