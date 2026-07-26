"""Sweep-engine tests for v2's variant-aware tune-sweep + OOS-validation
engine (Plan 03-08 Task 1, STRAT-03/04/05/06).

Mirrors tests/test_sweep_engine.py + tests/test_oos_validation.py's fixture
patterns exactly, extended for v2's own hash gate (frozen_config_v2), v2's
own regime registry (regimes_v2.REGIMES_V2), and the new entry_variant
provenance key -- proves sweep_v2's WIRING is correct against tiny fixture
grids/bars only. Plan 03-08 Task 2 drives the real 10,800-run sweep over
the real universe separately.
"""

from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from trader.backtest import config, frozen_config_v2, regimes_v2
from trader.data import db as data_db

try:
    from trader.backtest import sweep_v2
except ImportError:
    # trader.backtest.sweep_v2 does not exist yet (RED phase) -- collection
    # must still succeed so all tests are collected; each test then fails
    # with an AttributeError on `sweep_v2` (None) when it tries to call into
    # it. Matches tests/test_sweep_engine.py's RED-phase-safe pattern.
    sweep_v2 = None


@pytest.fixture
def data_conn(tmp_db_path):
    """A live connection to a fresh temp DB (mirrors
    tests/test_sweep_engine.py's data_conn fixture)."""
    connection = data_db.get_connection(tmp_db_path)
    yield connection
    connection.close()


def _make_bars(dates, opens, highs, lows, closes, volumes=None):
    index = pd.to_datetime(dates, utc=True)
    n = len(dates)
    if volumes is None:
        volumes = [1000.0] * n
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=index,
    )


def _fixture_bars():
    """Two symbols, 40 synthetic daily bars each -- identical shape to
    tests/test_sweep_engine.py's _fixture_bars, reused here for both the
    tune window (2023-01-01..2023-01-20) and OOS window
    (2023-01-21..2023-01-30)."""
    dates = pd.date_range("2023-01-01", periods=40, freq="D").strftime("%Y-%m-%d").tolist()
    n = len(dates)
    return {
        "AAA": _make_bars(
            dates,
            opens=[100.0 + i * 0.5 for i in range(n)],
            highs=[102.0 + i * 0.5 for i in range(n)],
            lows=[98.0 + i * 0.5 for i in range(n)],
            closes=[101.0 + i * 0.5 for i in range(n)],
        ),
        "BBB": _make_bars(
            dates,
            opens=[50.0 + i * 0.3 for i in range(n)],
            highs=[52.0 + i * 0.3 for i in range(n)],
            lows=[48.0 + i * 0.3 for i in range(n)],
            closes=[51.0 + i * 0.3 for i in range(n)],
        ),
    }


class _FixtureRegime:
    """A tiny stand-in matching regimes_v2.REGIMES_V2's Regime field
    contract, dated entirely inside _fixture_bars()'s 40-day window."""

    bucket = "stock"
    label = "fixture_trend_v2"
    tune_start = "2023-01-01"
    tune_end = "2023-01-20"
    oos_start = "2023-01-21"
    oos_end = "2023-01-30"


def _max_date_recording_strategy(max_date_holder: dict):
    """Deterministic stub: signals AAA exactly once (2023-01-05), records
    the max calendar date it was ever called with -- proves tune-window
    bar slicing."""

    def pick_entries(iterator, date, open_positions, rng):
        current = date.strftime("%Y-%m-%d")
        if max_date_holder.get("max") is None or current > max_date_holder["max"]:
            max_date_holder["max"] = current
        if "AAA" not in open_positions and current == "2023-01-05":
            return ["AAA"]
        return []

    return pick_entries


def _window_recording_strategy(date_holder: dict):
    """Deterministic stub: signals AAA exactly once (2023-01-22), records
    every calendar date it was ever called with -- proves OOS-window-only
    bar slicing."""

    def pick_entries(iterator, date, open_positions, rng):
        current = date.strftime("%Y-%m-%d")
        date_holder.setdefault("seen", []).append(current)
        if "AAA" not in open_positions and current == "2023-01-22":
            return ["AAA"]
        return []

    return pick_entries


def _tiny_grid(bucket):
    """A 2x2x1x1 = 4-cell injected grid standing in for the real 270/360-
    cell exit_profile_grid."""
    for stop_pct in (-0.05, -0.10):
        for tp_pct in (0.20, 0.40):
            yield config.EXIT_PROFILE(
                stop_pct=stop_pct,
                tp_pct=tp_pct,
                scale_out=(),
                trailing_pct=None,
                max_hold_days=10,
                eod_flat=False,
            )


# --- Task 1: run_tune_sweep_v2 ----------------------------------------------


def test_run_tune_sweep_v2_raises_and_never_calls_run_backtest_on_hash_tamper(
    data_conn, monkeypatch
):
    monkeypatch.setattr(frozen_config_v2, "FROZEN_HASH_V2", "0" * 64)

    call_count = {"n": 0}

    def _spy_run_backtest(*args, **kwargs):
        call_count["n"] += 1
        return 999

    monkeypatch.setattr(sweep_v2.runner, "run_backtest", _spy_run_backtest)
    monkeypatch.setattr(sweep_v2.exit_grid, "exit_profile_grid", _tiny_grid)

    bars = _fixture_bars()
    strategy_fn = _max_date_recording_strategy({})

    rows_before = data_conn.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0]

    with pytest.raises(RuntimeError):
        sweep_v2.run_tune_sweep_v2(
            strategy_fn=strategy_fn,
            strategy_id="test_strategy",
            bucket="stock",
            regime=_FixtureRegime(),
            entry_variant_name="base",
            bars_by_symbol=bars,
            universe=["AAA", "BBB"],
            conn=data_conn,
            sweep_id="test-sweep-v2",
        )

    assert call_count["n"] == 0, "run_backtest must never be called when the hash gate fails"
    rows_after = data_conn.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0]
    assert rows_after == rows_before, "zero DB writes must occur before the hash gate raises"


def test_run_tune_sweep_v2_returns_one_result_per_cell_with_six_provenance_keys(
    data_conn, monkeypatch
):
    monkeypatch.setattr(sweep_v2.exit_grid, "exit_profile_grid", _tiny_grid)

    bars = _fixture_bars()
    max_date_holder: dict = {}
    strategy_fn = _max_date_recording_strategy(max_date_holder)

    results = sweep_v2.run_tune_sweep_v2(
        strategy_fn=strategy_fn,
        strategy_id="test_strategy",
        bucket="stock",
        regime=_FixtureRegime(),
        entry_variant_name="strict",
        bars_by_symbol=bars,
        universe=["AAA", "BBB"],
        conn=data_conn,
        sweep_id="test-sweep-v2",
    )

    assert len(results) == 4  # 2x2x1x1 injected grid -- ONE variant per call

    seen_run_ids = set()
    for result in results:
        assert set(result.keys()) == {"run_id", "params", "metrics"}
        seen_run_ids.add(result["run_id"])

        row = data_conn.execute(
            "SELECT params_json FROM backtest_runs WHERE run_id = ?",
            (result["run_id"],),
        ).fetchone()
        assert row is not None
        persisted = json.loads(row[0])

        for key in (
            "sweep_id",
            "regime",
            "split",
            "asset_class_bucket",
            "strategy",
            "entry_variant",
        ):
            assert key in persisted, f"{key} missing from persisted params_json"

        assert persisted["sweep_id"] == "test-sweep-v2"
        assert persisted["regime"] == "fixture_trend_v2"
        assert persisted["split"] == "tune"
        assert persisted["asset_class_bucket"] == "stock"
        assert persisted["strategy"] == "test_strategy"
        assert persisted["entry_variant"] == "strict"

    assert len(seen_run_ids) == 4  # every cell got its own run_id

    assert max_date_holder["max"] is not None
    assert max_date_holder["max"] <= _FixtureRegime.tune_end


def test_run_tune_sweep_v2_reuses_slice_bars_from_v1_sweep_module():
    """D-15: _slice_bars is imported and reused verbatim from
    trader.backtest.sweep -- never a new slicing implementation."""
    from trader.backtest import sweep

    assert sweep_v2._slice_bars is sweep._slice_bars


# --- Task 1: run_oos_validation_v2 ------------------------------------------


def _fixture_candidate(strategy_fn):
    return {
        "strategy_id": "test_strategy_stock",
        "bucket": "stock",
        "regime": "fixture_trend_v2",
        "run_id": 1,
        "metrics": {"trade_count": 30, "profit_factor": 5.0},
        "params": {
            "profile_name": "test_strategy_stock_fixture_trend_v2_strict_tune",
            "sweep_id": "test-tune-sweep-v2",
            "regime": "fixture_trend_v2",
            "split": "tune",
            "asset_class_bucket": "stock",
            "strategy": "test_strategy_stock",
            "entry_variant": "strict",
            "stop_pct": -0.10,
            "tp_pct": 0.20,
            "trailing_pct": None,
            "max_hold_days": 3,
        },
        "strategy_fn": strategy_fn,
    }


def test_run_oos_validation_v2_raises_and_never_calls_run_backtest_on_hash_tamper(
    data_conn, monkeypatch
):
    monkeypatch.setattr(frozen_config_v2, "FROZEN_HASH_V2", "0" * 64)

    call_count = {"n": 0}

    def _spy_run_backtest(*args, **kwargs):
        call_count["n"] += 1
        return 999

    monkeypatch.setattr(sweep_v2.runner, "run_backtest", _spy_run_backtest)
    monkeypatch.setattr(
        sweep_v2.regimes_v2, "REGIMES_V2", (_FixtureRegime(),)
    )
    monkeypatch.setattr(sweep_v2.universe, "UNIVERSE_BY_BUCKET", {"stock": ["AAA", "BBB"]})

    candidate = _fixture_candidate(_window_recording_strategy({}))
    bars_by_symbol_by_bucket = {"stock": _fixture_bars()}

    rows_before = data_conn.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0]

    with pytest.raises(RuntimeError):
        sweep_v2.run_oos_validation_v2(
            candidates=[candidate],
            bars_by_symbol_by_bucket=bars_by_symbol_by_bucket,
            conn=data_conn,
            sweep_id="test-oos-sweep-v2",
        )

    assert call_count["n"] == 0, "run_backtest must never be called when the hash gate fails"
    rows_after = data_conn.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0]
    assert rows_after == rows_before, "zero DB writes must occur before the hash gate raises"


def test_run_oos_validation_v2_slices_bars_to_oos_window_and_uses_regimes_v2(
    data_conn, monkeypatch
):
    monkeypatch.setattr(sweep_v2.regimes_v2, "REGIMES_V2", (_FixtureRegime(),))
    monkeypatch.setattr(sweep_v2.universe, "UNIVERSE_BY_BUCKET", {"stock": ["AAA", "BBB"]})

    date_holder: dict = {}
    candidate = _fixture_candidate(_window_recording_strategy(date_holder))
    bars_by_symbol_by_bucket = {"stock": _fixture_bars()}

    results = sweep_v2.run_oos_validation_v2(
        candidates=[candidate],
        bars_by_symbol_by_bucket=bars_by_symbol_by_bucket,
        conn=data_conn,
        sweep_id="test-oos-sweep-v2",
    )

    assert len(results) == 1
    result = results[0]
    assert set(result.keys()) == {"candidate", "oos_run_id", "oos_metrics"}
    assert result["candidate"] is candidate
    assert result["oos_metrics"]["trade_count"] >= 1

    seen_dates = date_holder["seen"]
    assert seen_dates, "strategy_fn was never called"
    assert min(seen_dates) >= _FixtureRegime.oos_start
    assert max(seen_dates) <= _FixtureRegime.oos_end

    row = data_conn.execute(
        "SELECT params_json FROM backtest_runs WHERE run_id = ?",
        (result["oos_run_id"],),
    ).fetchone()
    assert row is not None
    persisted = json.loads(row[0])
    assert persisted["split"] == "oos"
    assert persisted["sweep_id"] == "test-oos-sweep-v2"
    assert persisted["entry_variant"] == "strict"  # carried through from candidate params


def test_run_oos_validation_v2_looks_up_regime_from_regimes_v2_not_v1_regimes(
    data_conn, monkeypatch
):
    """A regime label that exists ONLY in regimes_v2.REGIMES_V2 (never in
    v1's regimes.REGIMES) must resolve correctly -- proves this module
    never falls back to v1's regime registry."""
    v2_only_regime = _FixtureRegime()
    v2_only_regime.label = "v2_only_label_never_in_v1"

    monkeypatch.setattr(sweep_v2.regimes_v2, "REGIMES_V2", (v2_only_regime,))
    monkeypatch.setattr(sweep_v2.universe, "UNIVERSE_BY_BUCKET", {"stock": ["AAA", "BBB"]})

    candidate = _fixture_candidate(_window_recording_strategy({}))
    candidate["regime"] = "v2_only_label_never_in_v1"
    candidate["params"]["regime"] = "v2_only_label_never_in_v1"

    results = sweep_v2.run_oos_validation_v2(
        candidates=[candidate],
        bars_by_symbol_by_bucket={"stock": _fixture_bars()},
        conn=data_conn,
        sweep_id="test-oos-sweep-v2",
    )

    assert len(results) == 1


# --- Task 1: select_top5 / determine_survivor reused unchanged (D-15) ------


def test_select_top5_and_determine_survivor_are_the_same_v1_functions():
    """D-15: sweep_v2 never redefines select_top5/determine_survivor -- it
    imports and calls the real trader.backtest.sweep functions directly."""
    from trader.backtest import sweep

    assert sweep_v2.select_top5 is sweep.select_top5
    assert sweep_v2.determine_survivor is sweep.determine_survivor


def test_select_top5_behaves_identically_on_v2_shaped_cell_results():
    """v1-shaped and v2-shaped (extra entry_variant key) cell-result dicts
    produce identical selection behavior through the same imported
    select_top5 -- the extra key is inert to the ranking rule."""
    v1_shaped = [
        {"run_id": 1, "params": {}, "metrics": {"trade_count": 40, "profit_factor": 3.0}},
        {"run_id": 2, "params": {}, "metrics": {"trade_count": 50, "profit_factor": 5.0}},
    ]
    v2_shaped = [
        {
            "run_id": 1,
            "params": {"entry_variant": "base"},
            "metrics": {"trade_count": 40, "profit_factor": 3.0},
        },
        {
            "run_id": 2,
            "params": {"entry_variant": "base"},
            "metrics": {"trade_count": 50, "profit_factor": 5.0},
        },
    ]

    top5_v1 = sweep_v2.select_top5(v1_shaped)
    top5_v2 = sweep_v2.select_top5(v2_shaped)

    assert [r["run_id"] for r in top5_v1] == [r["run_id"] for r in top5_v2] == [2, 1]


def test_determine_survivor_behaves_identically_regardless_of_shape():
    assert sweep_v2.determine_survivor({"trade_count": 20, "profit_factor": 2.0}) == "survivor"
    assert sweep_v2.determine_survivor({"trade_count": 20, "profit_factor": math.inf}) == "survivor"
    assert sweep_v2.determine_survivor({"trade_count": 5, "profit_factor": 100.0}) == "insufficient_sample"
