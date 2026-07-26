"""OOS validation tests for STRAT-05's out-of-sample rule (T-03-14, T-03-15).

These tests exercise trader.backtest.sweep's run_oos_validation and
determine_survivor against tiny fixture grids/regimes -- Plan 03-05 Task 2
drives the real run over all 15 real tune-sweep candidates; this plan proves
the engine's WIRING is correct first (the same frozen-config hash gate
run_tune_sweep already enforces, OOS-window-only bar slicing, and the
three-way survivor/insufficient_sample/killed verdict rule with its 15-trade
floor), matching tests/test_sweep_engine.py's sibling pattern one layer
below.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from trader.backtest import config, frozen_config, regimes, universe
from trader.data import db as data_db

try:
    from trader.backtest import sweep
except ImportError:
    # trader.backtest.sweep already exists (Plan 03-03/03-04) -- this guard
    # only protects test collection if run_oos_validation itself is missing
    # (RED phase), matching tests/test_sweep_engine.py's RED-phase-safe
    # pattern.
    sweep = None


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
    """Two symbols, 40 synthetic daily bars each (2023-01-01..2023-02-09),
    steadily trending up so a simple stub strategy always produces at least
    one closed trade -- identical shape to test_sweep_engine.py's
    _fixture_bars, reused here for the OOS window (2023-01-21..2023-01-30)
    rather than the tune window."""
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


_FIXTURE_REGIME = regimes.Regime(
    bucket="stock",
    label="fixture_trend",
    tune_start="2023-01-01",
    tune_end="2023-01-20",
    oos_start="2023-01-21",
    oos_end="2023-01-30",
)


def _fixture_candidate(strategy_fn):
    return {
        "strategy_id": "test_strategy_stock",
        "bucket": "stock",
        "regime": "fixture_trend",
        "run_id": 1,
        "metrics": {"trade_count": 30, "profit_factor": 5.0},
        "params": {
            "profile_name": "test_strategy_stock_fixture_trend_tune",
            "sweep_id": "test-tune-sweep",
            "regime": "fixture_trend",
            "split": "tune",
            "asset_class_bucket": "stock",
            "strategy": "test_strategy_stock",
            "stop_pct": -0.10,
            "tp_pct": 0.20,
            "trailing_pct": None,
            "max_hold_days": 3,
        },
        "strategy_fn": strategy_fn,
    }


def _window_recording_strategy(date_holder: dict):
    """A deterministic stub strategy_fn that signals AAA exactly once (on
    2023-01-22) and records every calendar date it was ever called with --
    proves bars are sliced to the OOS window only (never the tune window or
    anything outside [oos_start, oos_end]), per Task 1's behavior spec."""

    def pick_entries(iterator, date, open_positions, rng):
        current = date.strftime("%Y-%m-%d")
        date_holder.setdefault("seen", []).append(current)
        if "AAA" not in open_positions and current == "2023-01-22":
            return ["AAA"]
        return []

    return pick_entries


# --- Task 1: run_oos_validation ---------------------------------------------


def test_run_oos_validation_raises_and_never_calls_run_backtest_on_hash_tamper(
    data_conn, monkeypatch
):
    monkeypatch.setattr(frozen_config, "FROZEN_HASH", "0" * 64)

    call_count = {"n": 0}

    def _spy_run_backtest(*args, **kwargs):
        call_count["n"] += 1
        return 999

    monkeypatch.setattr(sweep.runner, "run_backtest", _spy_run_backtest)
    monkeypatch.setattr(sweep.regimes, "REGIMES", (_FIXTURE_REGIME,))
    monkeypatch.setattr(sweep.universe, "UNIVERSE_BY_BUCKET", {"stock": ["AAA", "BBB"]})

    candidate = _fixture_candidate(_window_recording_strategy({}))
    bars_by_symbol_by_bucket = {"stock": _fixture_bars()}

    rows_before = data_conn.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0]

    with pytest.raises(RuntimeError):
        sweep.run_oos_validation(
            candidates=[candidate],
            bars_by_symbol_by_bucket=bars_by_symbol_by_bucket,
            conn=data_conn,
            sweep_id="test-oos-sweep",
        )

    assert call_count["n"] == 0, "run_backtest must never be called when the hash gate fails"
    rows_after = data_conn.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0]
    assert rows_after == rows_before, "zero DB writes must occur before the hash gate raises"


def test_run_oos_validation_slices_bars_to_oos_window_only(data_conn, monkeypatch):
    monkeypatch.setattr(sweep.regimes, "REGIMES", (_FIXTURE_REGIME,))
    monkeypatch.setattr(sweep.universe, "UNIVERSE_BY_BUCKET", {"stock": ["AAA", "BBB"]})

    date_holder: dict = {}
    candidate = _fixture_candidate(_window_recording_strategy(date_holder))
    bars_by_symbol_by_bucket = {"stock": _fixture_bars()}

    results = sweep.run_oos_validation(
        candidates=[candidate],
        bars_by_symbol_by_bucket=bars_by_symbol_by_bucket,
        conn=data_conn,
        sweep_id="test-oos-sweep",
    )

    assert len(results) == 1
    result = results[0]
    assert set(result.keys()) == {"candidate", "oos_run_id", "oos_metrics"}
    assert result["candidate"] is candidate
    assert result["oos_metrics"]["trade_count"] >= 1

    seen_dates = date_holder["seen"]
    assert seen_dates, "strategy_fn was never called"
    assert min(seen_dates) >= _FIXTURE_REGIME.oos_start
    assert max(seen_dates) <= _FIXTURE_REGIME.oos_end

    row = data_conn.execute(
        "SELECT params_json FROM backtest_runs WHERE run_id = ?",
        (result["oos_run_id"],),
    ).fetchone()
    assert row is not None
    import json as _json

    persisted = _json.loads(row[0])
    assert persisted["split"] == "oos"
    assert persisted["sweep_id"] == "test-oos-sweep"


def test_slice_bars_reused_bounds_oos_window_to_closed_interval():
    bars = _fixture_bars()
    sliced = sweep._slice_bars(bars, "2023-01-21", "2023-01-30")

    for symbol, df in sliced.items():
        assert df.index.min() >= pd.Timestamp("2023-01-21", tz="UTC")
        assert df.index.max() <= pd.Timestamp("2023-01-30", tz="UTC")
        assert len(df) == 10  # 01-21 .. 01-30 inclusive


# --- Task 1: determine_survivor ---------------------------------------------


def _metrics(trade_count, profit_factor):
    return {"trade_count": trade_count, "profit_factor": profit_factor}


def test_determine_survivor_returns_survivor_when_floor_cleared_and_profitable():
    assert sweep.determine_survivor(_metrics(15, 1.5)) == "survivor"
    assert sweep.determine_survivor(_metrics(50, 1.01)) == "survivor"


def test_determine_survivor_returns_survivor_for_inf_profit_factor():
    assert sweep.determine_survivor(_metrics(15, math.inf)) == "survivor"


def test_determine_survivor_returns_killed_when_floor_cleared_but_unprofitable():
    assert sweep.determine_survivor(_metrics(15, 1.0)) == "killed"
    assert sweep.determine_survivor(_metrics(100, 0.5)) == "killed"


def test_determine_survivor_returns_insufficient_sample_below_floor_regardless_of_profit_factor():
    assert sweep.determine_survivor(_metrics(14, 1.5)) == "insufficient_sample"
    assert sweep.determine_survivor(_metrics(0, None)) == "insufficient_sample"


def test_determine_survivor_thin_lucky_window_never_reported_as_survivor():
    """Pitfall 3 guard: a synthetic 4-trade OOS window with a very high
    profit_factor still returns insufficient_sample, never survivor."""
    assert sweep.determine_survivor(_metrics(4, 100.0)) == "insufficient_sample"


def test_determine_survivor_respects_custom_min_trades():
    assert sweep.determine_survivor(_metrics(20, 2.0), min_trades=15) == "survivor"
    assert sweep.determine_survivor(_metrics(20, 2.0), min_trades=25) == "insufficient_sample"
