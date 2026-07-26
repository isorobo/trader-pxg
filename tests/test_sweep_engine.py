"""Sweep-engine tests for STRAT-03's tune-sweep orchestration and D-10 top-5
selection (T-03-08, T-03-09, T-03-10, T-03-11).

These tests exercise trader.backtest.sweep against tiny fixture grids and a
tiny fixture bar universe -- Plan 03-04 drives the real 270/360-cell grid
against the real universe; this plan proves the engine's WIRING is correct
first (hash gate before any cell, provenance round-tripping through the DB,
tune-window bar slicing, and the min-trade-floored top-5 rule), matching
tests/test_backtest_runner.py's sibling pattern of proving integration
correctness against small deterministic fixtures rather than real data.
"""

from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from trader.backtest import config, frozen_config
from trader.data import db as data_db

try:
    from trader.backtest import sweep
except ImportError:
    # trader.backtest.sweep does not exist yet (RED phase) -- collection
    # must still succeed so all tests are collected; each test then fails
    # with an AttributeError on `sweep` (None) when it tries to call into
    # it. Matches tests/test_backtest_runner.py's RED-phase-safe pattern.
    sweep = None


@pytest.fixture
def data_conn(tmp_db_path):
    """A live connection to a fresh temp DB, bootstrapped via trader.data.db
    (mirrors tests/test_backtest_runner.py's data_conn fixture)."""
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
    """Two symbols, 40 synthetic daily bars each (2023-01-01..2023-02-09),
    steadily trending up so a simple "buy once, hold" stub strategy always
    produces at least one closed trade."""
    dates = pd.date_range("2023-01-01", periods=40, freq="D").strftime("%Y-%m-%d").tolist()
    n = len(dates)
    bars = {
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
    return bars


class _FixtureRegime:
    """A tiny stand-in matching regimes.Regime's field contract (bucket,
    label, tune_start, tune_end, oos_start, oos_end), dated entirely inside
    _fixture_bars()'s 40-day window -- proves the tune-window bar slice
    without touching the real frozen regimes.py (which run_tune_sweep never
    imports directly; it only reads whatever Regime-shaped object it is
    handed)."""

    bucket = "stock"
    label = "fixture_trend"
    tune_start = "2023-01-01"
    tune_end = "2023-01-20"
    oos_start = "2023-01-21"
    oos_end = "2023-01-30"


def _max_date_recording_strategy(max_date_holder: dict):
    """A deterministic stub strategy_fn that signals AAA exactly once (on
    2023-01-05) and records the maximum calendar date it was ever called
    with -- proves bars are sliced to the tune window (never beyond
    regime.tune_end), per Task 1's behavior spec."""

    def pick_entries(iterator, date, open_positions, rng):
        current = date.strftime("%Y-%m-%d")
        if max_date_holder.get("max") is None or current > max_date_holder["max"]:
            max_date_holder["max"] = current
        if "AAA" not in open_positions and current == "2023-01-05":
            return ["AAA"]
        return []

    return pick_entries


def _tiny_grid(bucket):
    """A 2x2x1x1 = 4-cell injected grid standing in for the real 270-cell
    exit_profile_grid, per 03-03-PLAN.md Task 1's "or an injected 2x2x1x1
    grid" allowance -- keeps these tests fast regardless of `bucket`."""
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


# --- Task 1: run_tune_sweep -------------------------------------------------


def test_run_tune_sweep_raises_and_never_calls_run_backtest_on_hash_tamper(
    data_conn, monkeypatch
):
    monkeypatch.setattr(frozen_config, "FROZEN_HASH", "0" * 64)

    call_count = {"n": 0}

    def _spy_run_backtest(*args, **kwargs):
        call_count["n"] += 1
        return 999

    monkeypatch.setattr(sweep.runner, "run_backtest", _spy_run_backtest)
    monkeypatch.setattr(sweep.exit_grid, "exit_profile_grid", _tiny_grid)

    bars = _fixture_bars()
    strategy_fn = _max_date_recording_strategy({})

    rows_before = data_conn.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0]

    with pytest.raises(RuntimeError):
        sweep.run_tune_sweep(
            strategy_fn=strategy_fn,
            strategy_id="test_strategy",
            bucket="stock",
            regime=_FixtureRegime(),
            bars_by_symbol=bars,
            universe=["AAA", "BBB"],
            conn=data_conn,
            sweep_id="test-sweep",
        )

    assert call_count["n"] == 0, "run_backtest must never be called when the hash gate fails"
    rows_after = data_conn.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0]
    assert rows_after == rows_before, "zero DB writes must occur before the hash gate raises"


def test_run_tune_sweep_returns_one_result_per_cell_with_full_provenance(
    data_conn, monkeypatch
):
    monkeypatch.setattr(sweep.exit_grid, "exit_profile_grid", _tiny_grid)

    bars = _fixture_bars()
    max_date_holder: dict = {}
    strategy_fn = _max_date_recording_strategy(max_date_holder)

    results = sweep.run_tune_sweep(
        strategy_fn=strategy_fn,
        strategy_id="test_strategy",
        bucket="stock",
        regime=_FixtureRegime(),
        bars_by_symbol=bars,
        universe=["AAA", "BBB"],
        conn=data_conn,
        sweep_id="test-sweep",
    )

    assert len(results) == 4  # 2x2x1x1 injected grid

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

        for key in ("sweep_id", "regime", "split", "asset_class_bucket", "strategy"):
            assert key in persisted, f"{key} missing from persisted params_json"

        assert persisted["sweep_id"] == "test-sweep"
        assert persisted["regime"] == "fixture_trend"
        assert persisted["split"] == "tune"
        assert persisted["asset_class_bucket"] == "stock"
        assert persisted["strategy"] == "test_strategy"

    assert len(seen_run_ids) == 4  # every cell got its own run_id

    # Bars-sliced-to-tune-window proof: the stub strategy_fn's own recorded
    # max call date never exceeds regime.tune_end.
    assert max_date_holder["max"] is not None
    assert max_date_holder["max"] <= _FixtureRegime.tune_end


def test_slice_bars_bounds_to_closed_tune_interval():
    bars = _fixture_bars()
    sliced = sweep._slice_bars(bars, "2023-01-05", "2023-01-10")

    for symbol, df in sliced.items():
        assert df.index.min() >= pd.Timestamp("2023-01-05", tz="UTC")
        assert df.index.max() <= pd.Timestamp("2023-01-10", tz="UTC")
        assert len(df) == 6  # 01-05 .. 01-10 inclusive


def test_slice_bars_none_start_uses_symbols_own_first_row():
    bars = _fixture_bars()
    sliced = sweep._slice_bars(bars, None, "2023-01-10")

    for symbol, df in sliced.items():
        assert df.index.min() == bars[symbol].index[0]
        assert df.index.max() <= pd.Timestamp("2023-01-10", tz="UTC")


# --- Task 2: select_top5 -----------------------------------------------------


def _cell(trade_count, profit_factor):
    return {
        "run_id": 0,
        "params": {},
        "metrics": {"trade_count": trade_count, "profit_factor": profit_factor},
    }


def test_select_top5_excludes_cells_below_the_min_trade_floor():
    results = [
        _cell(50, 5.0),
        _cell(10, 100.0),  # high profit_factor but below the floor -- excluded
        _cell(29, 50.0),  # one below the floor -- excluded
        _cell(5, 1000.0),  # far below the floor -- excluded
        _cell(40, 3.0),
        _cell(35, 8.0),
        _cell(60, 1.5),
        _cell(30, 2.0),  # exactly at the floor -- eligible
    ]

    top5 = sweep.select_top5(results)

    assert len(top5) == 5
    for cell in top5:
        assert cell["metrics"]["trade_count"] >= 30
    assert all(cell["metrics"]["profit_factor"] != 100.0 for cell in top5)
    assert all(cell["metrics"]["profit_factor"] != 1000.0 for cell in top5)
    assert all(cell["metrics"]["profit_factor"] != 50.0 for cell in top5)


def test_select_top5_ranks_descending_by_profit_factor_among_eligible():
    results = [
        _cell(50, 5.0),
        _cell(40, 3.0),
        _cell(35, 8.0),
        _cell(60, 1.5),
        _cell(30, 2.0),
    ]

    top5 = sweep.select_top5(results)

    profit_factors = [cell["metrics"]["profit_factor"] for cell in top5]
    assert profit_factors == sorted(profit_factors, reverse=True)
    assert profit_factors[0] == 8.0


def test_select_top5_ranks_inf_profit_factor_above_all_finite_values():
    results = [
        _cell(30, 2.0),
        _cell(30, math.inf),  # zero losing trades
        _cell(30, 9.0),
    ]

    top5 = sweep.select_top5(results)

    assert top5[0]["metrics"]["profit_factor"] == math.inf


def test_select_top5_returns_fewer_than_5_without_padding_when_only_some_eligible():
    results = [_cell(50, 5.0), _cell(10, 100.0), _cell(40, 3.0)]

    top5 = sweep.select_top5(results)

    assert len(top5) == 2
    assert top5[0]["metrics"]["profit_factor"] == 5.0
    assert top5[1]["metrics"]["profit_factor"] == 3.0


def test_select_top5_returns_empty_list_when_zero_cells_meet_the_floor():
    results = [_cell(5, 10.0), _cell(29, 20.0)]

    assert sweep.select_top5(results) == []
