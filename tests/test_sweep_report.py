"""Tests for STRAT-06's sweep-report writers (T-03-19): per-config markdown
summaries and the survivors index, both consuming already-computed tune/OOS
metrics and real ledger trades -- no new metrics engine, no bypass of
`metrics.compute_metrics` or `ledger.get_trades_for_run`.
"""

from __future__ import annotations

import math

import pytest

from trader.backtest import ledger, sweep_report
from trader.data import db as data_db


@pytest.fixture
def data_conn(tmp_db_path):
    """A live connection to a fresh temp DB (mirrors
    tests/test_sweep_engine.py's data_conn fixture)."""
    connection = data_db.get_connection(tmp_db_path)
    yield connection
    connection.close()


def _seed_run_with_trades(conn, strategy_id="momentum_stock"):
    run_id = ledger.record_run(
        conn,
        strategy_id=strategy_id,
        profile_name="test_profile",
        params={"split": "oos"},
        seed=1,
    )
    ledger.record_trade(
        conn,
        run_id=run_id,
        position_id="p1",
        strategy_id=strategy_id,
        symbol="AAA",
        asset_class="stock",
        entry_ts="2023-01-02T00:00:00",
        entry_price=100.0,
        exit_ts="2023-01-05T00:00:00",
        exit_price=110.0,
        qty=10,
        fees=1.0,
        slippage=0.0,
        pnl=100.0,
        exit_reason="take_profit",
    )
    ledger.record_trade(
        conn,
        run_id=run_id,
        position_id="p2",
        strategy_id=strategy_id,
        symbol="BBB",
        asset_class="stock",
        entry_ts="2023-01-03T00:00:00",
        entry_price=50.0,
        exit_ts="2023-01-06T00:00:00",
        exit_price=45.0,
        qty=10,
        fees=1.0,
        slippage=0.0,
        pnl=-50.0,
        exit_reason="stop",
    )
    ledger.record_trade(
        conn,
        run_id=run_id,
        position_id="p3",
        strategy_id=strategy_id,
        symbol="AAA",
        asset_class="stock",
        entry_ts="2023-01-07T00:00:00",
        entry_price=105.0,
        exit_ts="2023-01-10T00:00:00",
        exit_price=120.0,
        qty=10,
        fees=1.0,
        slippage=0.0,
        pnl=150.0,
        exit_reason="take_profit",
    )
    return run_id


def _tune_candidate(run_id=1, strategy_id="momentum_stock", bucket="stock", regime="trending"):
    return {
        "run_id": run_id,
        "params": {
            "profile_name": "momentum_stock_stock_trending_tune",
            "sweep_id": "test-sweep",
            "regime": regime,
            "split": "tune",
            "asset_class_bucket": bucket,
            "strategy": strategy_id,
            "stop_pct": -0.15,
            "tp_pct": 0.2,
            "trailing_pct": None,
            "max_hold_days": None,
        },
        "metrics": {
            "profit_factor": 5.0,
            "sharpe_ratio": 2.0,
            "max_drawdown": -0.02,
            "win_rate": 0.8,
            "avg_win": 1000.0,
            "avg_loss": -500.0,
            "trade_count": 30,
            "total_fees_paid": 60.0,
        },
        "strategy_id": strategy_id,
        "bucket": bucket,
        "regime": regime,
    }


def _oos_result(oos_run_id, verdict, strategy_id="momentum_stock", bucket="stock", regime="trending", run_id=1):
    return {
        "candidate": {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "bucket": bucket,
            "regime": regime,
        },
        "oos_run_id": oos_run_id,
        "oos_metrics": {
            "profit_factor": 3.0,
            "sharpe_ratio": 1.5,
            "max_drawdown": -0.03,
            "win_rate": 0.66,
            "avg_win": 125.0,
            "avg_loss": -50.0,
            "trade_count": 3,
            "total_fees_paid": 3.0,
        },
        "verdict": verdict,
    }


# --- write_sweep_summary -----------------------------------------------------


def test_write_sweep_summary_writes_expected_filename(tmp_path, data_conn):
    run_id = _seed_run_with_trades(data_conn)
    result = _oos_result(run_id, "insufficient_sample")
    tune_candidate = _tune_candidate(run_id=run_id)

    report_path = sweep_report.write_sweep_summary(
        result, tune_candidate, data_conn, base_dir=str(tmp_path)
    )

    assert report_path.exists()
    assert report_path.name.endswith(f"-momentum_stock-stock-trending-run{run_id}-sweep.md")


def test_write_sweep_summary_includes_tune_and_oos_tables_and_verdict(tmp_path, data_conn):
    run_id = _seed_run_with_trades(data_conn)
    result = _oos_result(run_id, "killed")
    tune_candidate = _tune_candidate(run_id=run_id)

    report_path = sweep_report.write_sweep_summary(
        result, tune_candidate, data_conn, base_dir=str(tmp_path)
    )
    text = report_path.read_text(encoding="utf-8")

    assert "Tune-Window Metrics" in text
    assert "OOS-Window Metrics" in text
    assert "**Verdict:** killed" in text
    assert "profit_factor" in text


def test_write_sweep_summary_includes_per_symbol_pnl_grouped_and_summed(tmp_path, data_conn):
    run_id = _seed_run_with_trades(data_conn)
    result = _oos_result(run_id, "survivor")
    tune_candidate = _tune_candidate(run_id=run_id)

    report_path = sweep_report.write_sweep_summary(
        result, tune_candidate, data_conn, base_dir=str(tmp_path)
    )
    text = report_path.read_text(encoding="utf-8")

    # AAA: 100.0 + 150.0 = 250.00; BBB: -50.00
    assert "| AAA | 250.00 |" in text
    assert "| BBB | -50.00 |" in text


def test_write_sweep_summary_handles_zero_trades_run(tmp_path, data_conn):
    empty_run_id = ledger.record_run(
        data_conn,
        strategy_id="momentum_stock",
        profile_name="empty_profile",
        params={"split": "oos"},
        seed=1,
    )
    result = _oos_result(empty_run_id, "insufficient_sample")
    tune_candidate = _tune_candidate(run_id=empty_run_id)

    report_path = sweep_report.write_sweep_summary(
        result, tune_candidate, data_conn, base_dir=str(tmp_path)
    )
    text = report_path.read_text(encoding="utf-8")

    assert "(no trades)" in text


# --- write_survivors_index ---------------------------------------------------


def test_write_survivors_index_lists_every_survivor(tmp_path):
    results = [
        _oos_result(1, "survivor", strategy_id="momentum_stock", regime="trending"),
        _oos_result(2, "killed", strategy_id="momentum_stock", regime="choppy"),
        _oos_result(3, "survivor", strategy_id="momentum_crypto", bucket="crypto_major_legacy_meme", regime="trending"),
    ]

    report_path = sweep_report.write_survivors_index(results, base_dir=str(tmp_path))
    text = report_path.read_text(encoding="utf-8")

    assert "momentum_stock" in text
    assert "momentum_crypto" in text
    # killed candidate must not appear as a survivor row
    assert text.count("| momentum_stock |") == 1


def test_write_survivors_index_carries_d05_caveat(tmp_path):
    results = [_oos_result(1, "survivor")]
    report_path = sweep_report.write_survivors_index(results, base_dir=str(tmp_path))
    text = report_path.read_text(encoding="utf-8")

    assert sweep_report.D05_CAVEAT in text


def test_write_survivors_index_nothing_survived_quotes_real_trial_count(tmp_path):
    results = [
        _oos_result(1, "insufficient_sample", strategy_id="momentum_stock", bucket="stock", regime="trending"),
        _oos_result(2, "insufficient_sample", strategy_id="momentum_stock", bucket="stock", regime="trending"),
        _oos_result(3, "insufficient_sample", strategy_id="momentum_stock", bucket="stock", regime="choppy"),
        _oos_result(4, "killed", strategy_id="momentum_crypto", bucket="crypto_major_legacy_meme", regime="trending"),
    ]

    report_path = sweep_report.write_survivors_index(results, base_dir=str(tmp_path))
    text = report_path.read_text(encoding="utf-8")

    assert "Nothing survived this sweep" in text
    assert "4 candidates" in text
    assert "3 strategy/bucket/regime combinations" in text
    assert sweep_report.D05_CAVEAT in text


def test_write_survivors_index_never_produces_empty_file_on_zero_survivors(tmp_path):
    results = [_oos_result(1, "insufficient_sample")]
    report_path = sweep_report.write_survivors_index(results, base_dir=str(tmp_path))

    assert report_path.exists()
    assert report_path.read_text(encoding="utf-8").strip() != ""
