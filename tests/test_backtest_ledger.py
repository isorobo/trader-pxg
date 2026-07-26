"""Tests for trader.backtest.ledger — trade ledger writes, reproducibility
(D-12), and per-strategy attribution grouping (BACK-06)."""

import json
import sqlite3

import pytest

from trader.data import db as data_db

try:
    from trader.backtest import ledger
except ImportError:
    # trader.backtest.ledger does not exist yet (RED phase) — collection must
    # still succeed so all tests are collected; each test then fails with an
    # AttributeError on `ledger` (None) when it tries to call into the contract.
    ledger = None


@pytest.fixture
def data_conn(tmp_db_path):
    """A live connection to a fresh temp DB, bootstrapped via trader.data.db."""
    connection = data_db.get_connection(tmp_db_path)
    yield connection
    connection.close()


def _make_run(conn, strategy_id="momentum_placeholder", seed=42):
    return ledger.record_run(
        conn,
        strategy_id=strategy_id,
        profile_name="PROFILE_MOMENTUM_PLACEHOLDER",
        params={"lookback": 20},
        seed=seed,
    )


def test_record_run_inserts_row_and_returns_int_run_id(data_conn):
    run_id = _make_run(data_conn)
    assert isinstance(run_id, int)

    row = data_conn.execute(
        "SELECT strategy_id, profile, params_json, seed, code_version "
        "FROM backtest_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    assert row is not None
    assert row[0] == "momentum_placeholder"
    assert row[1] == "PROFILE_MOMENTUM_PLACEHOLDER"
    assert json.loads(row[2]) == {"lookback": 20}
    assert row[3] == 42
    # code_version resolved internally (None was passed) — not the literal None
    assert row[4] is not None
    assert row[4] != "None"


def test_record_trade_inserts_row_and_returns_int_trade_id(data_conn):
    run_id = _make_run(data_conn)

    trade_id = ledger.record_trade(
        data_conn,
        run_id=run_id,
        position_id="AAPL:2026-01-05",
        strategy_id="momentum_placeholder",
        symbol="AAPL",
        asset_class="stock",
        entry_ts="2026-01-05",
        entry_price=150.0,
        exit_ts="2026-01-06",
        exit_price=148.0,
        qty=66.0,
        fees=1.0,
        slippage=0.15,
        pnl=-133.15,
        exit_reason="stop",
    )
    assert isinstance(trade_id, int)

    row = data_conn.execute(
        "SELECT run_id, position_id, strategy_id, symbol, asset_class, "
        "entry_ts, entry_price, exit_ts, exit_price, qty, fees, slippage, "
        "pnl, exit_reason FROM backtest_trades WHERE trade_id = ?",
        (trade_id,),
    ).fetchone()
    assert row is not None
    assert row[0] == run_id
    assert row[1] == "AAPL:2026-01-05"
    assert row[2] == "momentum_placeholder"
    assert row[3] == "AAPL"
    assert row[4] == "stock"
    assert row[5] == "2026-01-05"
    assert row[6] == 150.0
    assert row[7] == "2026-01-06"
    assert row[8] == 148.0
    assert row[9] == 66.0
    assert row[10] == 1.0
    assert row[11] == 0.15
    assert row[12] == -133.15
    assert row[13] == "stop"


def test_scale_out_tranches_share_position_id_and_sum_pnl(data_conn):
    run_id = _make_run(data_conn)
    position_id = "BTC/USDT:2026-02-01"

    ledger.record_trade(
        data_conn,
        run_id=run_id,
        position_id=position_id,
        strategy_id="momentum_placeholder",
        symbol="BTC/USDT",
        asset_class="crypto_major",
        entry_ts="2026-02-01",
        entry_price=40000.0,
        exit_ts="2026-02-02",
        exit_price=41000.0,
        qty=0.5,
        fees=5.0,
        slippage=2.0,
        pnl=493.0,
        exit_reason="scale_out",
    )
    ledger.record_trade(
        data_conn,
        run_id=run_id,
        position_id=position_id,
        strategy_id="momentum_placeholder",
        symbol="BTC/USDT",
        asset_class="crypto_major",
        entry_ts="2026-02-01",
        entry_price=40000.0,
        exit_ts="2026-02-05",
        exit_price=39500.0,
        qty=0.5,
        fees=5.0,
        slippage=2.0,
        pnl=-263.0,
        exit_reason="time_stop",
    )

    trades = ledger.get_trades_for_run(data_conn, run_id)
    assert len(trades) == 2
    position_trades = [t for t in trades if t["position_id"] == position_id]
    assert len(position_trades) == 2
    assert sum(t["pnl"] for t in position_trades) == pytest.approx(230.0)


def test_reproducibility_identical_seed_params_data_produces_identical_ledger(
    tmp_path,
):
    def run_sequence(db_path):
        conn = data_db.get_connection(str(db_path))
        run_id = ledger.record_run(
            conn,
            strategy_id="momentum_placeholder",
            profile_name="PROFILE_MOMENTUM_PLACEHOLDER",
            params={"lookback": 20},
            seed=7,
        )
        ledger.record_trade(
            conn,
            run_id=run_id,
            position_id="AAPL:2026-01-05",
            strategy_id="momentum_placeholder",
            symbol="AAPL",
            asset_class="stock",
            entry_ts="2026-01-05",
            entry_price=150.0,
            exit_ts="2026-01-06",
            exit_price=148.0,
            qty=66.0,
            fees=1.0,
            slippage=0.15,
            pnl=-133.15,
            exit_reason="stop",
        )
        ledger.record_trade(
            conn,
            run_id=run_id,
            position_id="MSFT:2026-01-07",
            strategy_id="momentum_placeholder",
            symbol="MSFT",
            asset_class="stock",
            entry_ts="2026-01-07",
            entry_price=300.0,
            exit_ts="2026-01-10",
            exit_price=310.0,
            qty=10.0,
            fees=1.0,
            slippage=0.3,
            pnl=98.7,
            exit_reason="take_profit",
        )
        trades = ledger.get_trades_for_run(conn, run_id)
        conn.close()
        return trades

    trades_a = run_sequence(tmp_path / "db_a.sqlite")
    trades_b = run_sequence(tmp_path / "db_b.sqlite")

    ignore_keys = {"run_id", "trade_id"}

    def normalize(trades):
        return sorted(
            tuple(sorted((k, v) for k, v in t.items() if k not in ignore_keys))
            for t in trades
        )

    assert normalize(trades_a) == normalize(trades_b)


def test_record_trade_invalid_exit_reason_raises_integrity_error(data_conn):
    run_id = _make_run(data_conn)
    with pytest.raises(sqlite3.IntegrityError):
        ledger.record_trade(
            data_conn,
            run_id=run_id,
            position_id="AAPL:2026-01-05",
            strategy_id="momentum_placeholder",
            symbol="AAPL",
            asset_class="stock",
            entry_ts="2026-01-05",
            entry_price=150.0,
            exit_ts="2026-01-06",
            exit_price=148.0,
            qty=66.0,
            fees=1.0,
            slippage=0.15,
            pnl=-133.15,
            exit_reason="not_a_real_reason",
        )


def test_record_trade_invalid_asset_class_raises_integrity_error(data_conn):
    run_id = _make_run(data_conn)
    with pytest.raises(sqlite3.IntegrityError):
        ledger.record_trade(
            data_conn,
            run_id=run_id,
            position_id="AAPL:2026-01-05",
            strategy_id="momentum_placeholder",
            symbol="AAPL",
            asset_class="not_a_real_class",
            entry_ts="2026-01-05",
            entry_price=150.0,
            exit_ts="2026-01-06",
            exit_price=148.0,
            qty=66.0,
            fees=1.0,
            slippage=0.15,
            pnl=-133.15,
            exit_reason="stop",
        )


def test_get_trades_for_run_returns_empty_list_for_unknown_run(data_conn):
    run_id = _make_run(data_conn)
    trades = ledger.get_trades_for_run(data_conn, run_id)
    assert trades == []


# --- Task 2: per-strategy attribution grouping (BACK-06) ---


def _seed_two_strategy_fixture(conn):
    """Two runs for strategy_a (3 trades total), one run for strategy_b (2
    trades), all in the same temp DB."""
    run_a1 = ledger.record_run(
        conn,
        strategy_id="strategy_a",
        profile_name="PROFILE_A",
        params={"lookback": 10},
        seed=1,
    )
    run_a2 = ledger.record_run(
        conn,
        strategy_id="strategy_a",
        profile_name="PROFILE_A",
        params={"lookback": 10},
        seed=2,
    )
    run_b1 = ledger.record_run(
        conn,
        strategy_id="strategy_b",
        profile_name="PROFILE_B",
        params={"lookback": 5},
        seed=3,
    )

    def trade(run_id, position_id, strategy_id, pnl, exit_reason="stop"):
        ledger.record_trade(
            conn,
            run_id=run_id,
            position_id=position_id,
            strategy_id=strategy_id,
            symbol="AAPL",
            asset_class="stock",
            entry_ts="2026-01-05",
            entry_price=150.0,
            exit_ts="2026-01-06",
            exit_price=148.0,
            qty=10.0,
            fees=1.0,
            slippage=0.1,
            pnl=pnl,
            exit_reason=exit_reason,
        )

    trade(run_a1, "a-pos-1", "strategy_a", 10.0)
    trade(run_a1, "a-pos-2", "strategy_a", -5.0)
    trade(run_a2, "a-pos-3", "strategy_a", 20.0)
    trade(run_b1, "b-pos-1", "strategy_b", 15.0)
    trade(run_b1, "b-pos-2", "strategy_b", -8.0)

    return {"run_a1": run_a1, "run_a2": run_a2, "run_b1": run_b1}


def test_get_trades_for_strategy_groups_across_runs_no_leakage(data_conn):
    _seed_two_strategy_fixture(data_conn)

    a_trades = ledger.get_trades_for_strategy(data_conn, "strategy_a")
    b_trades = ledger.get_trades_for_strategy(data_conn, "strategy_b")

    assert len(a_trades) == 3
    assert all(t["strategy_id"] == "strategy_a" for t in a_trades)
    assert len(b_trades) == 2
    assert all(t["strategy_id"] == "strategy_b" for t in b_trades)


def test_compute_metrics_by_strategy_pins_trade_counts_no_pooling(data_conn):
    _seed_two_strategy_fixture(data_conn)

    result = ledger.compute_metrics_by_strategy(data_conn)

    assert set(result.keys()) == {"strategy_a", "strategy_b"}
    assert result["strategy_a"]["trade_count"] == 3
    assert result["strategy_b"]["trade_count"] == 2


def test_compute_metrics_by_strategy_scopes_to_given_run_ids(data_conn):
    run_ids = _seed_two_strategy_fixture(data_conn)

    result = ledger.compute_metrics_by_strategy(
        data_conn, run_ids=[run_ids["run_a1"]]
    )

    assert set(result.keys()) == {"strategy_a"}
    assert result["strategy_a"]["trade_count"] == 2
