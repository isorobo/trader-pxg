"""Tests for migrations/0003_backtest.sql -- backtest_runs/backtest_trades
schema and CHECK constraints (D-11).
"""

import sqlite3

import pytest

from trader.data import db


@pytest.fixture
def data_conn(tmp_db_path):
    """A live connection to a fresh temp DB, bootstrapped via trader.data.db.

    Mirrors tests/test_data_db.py's data_conn fixture pattern -- defined
    locally here rather than added to tests/conftest.py, per this plan's
    instruction not to modify conftest.py.
    """
    connection = db.get_connection(tmp_db_path)
    yield connection
    connection.close()


def _insert_run(conn, run_id=1):
    conn.execute(
        """
        INSERT INTO backtest_runs
            (run_id, strategy_id, profile, params_json, seed, code_version)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, "random_strategy", "PROFILE_TIME_STOP_1D", "{}", 42, "abc123"),
    )
    conn.commit()


def _insert_trade(conn, **overrides):
    row = {
        "run_id": 1,
        "position_id": "pos-1",
        "strategy_id": "random_strategy",
        "symbol": "AAPL",
        "asset_class": "stock",
        "entry_ts": "2026-07-01",
        "entry_price": 100.0,
        "exit_ts": "2026-07-02",
        "exit_price": 101.0,
        "qty": 10.0,
        "fees": 1.0,
        "slippage": 0.05,
        "pnl": 8.95,
        "exit_reason": "time_stop",
    }
    row.update(overrides)
    conn.execute(
        """
        INSERT INTO backtest_trades
            (run_id, position_id, strategy_id, symbol, asset_class, entry_ts,
             entry_price, exit_ts, exit_price, qty, fees, slippage, pnl,
             exit_reason)
        VALUES (:run_id, :position_id, :strategy_id, :symbol, :asset_class,
                :entry_ts, :entry_price, :exit_ts, :exit_price, :qty, :fees,
                :slippage, :pnl, :exit_reason)
        """,
        row,
    )
    conn.commit()


def test_migration_0003_reaches_schema_version_3(data_conn):
    # Assert version 3 was applied (not that it is the MAX) -- later
    # migrations (e.g. 0004_risk_breakers.sql) apply on top of a fresh DB
    # via the same apply_migrations() call, so MAX(version) grows over time
    # as new migrations land; this test's contract is only that 0003 itself
    # was applied cleanly.
    applied_versions = {
        row[0] for row in data_conn.execute("SELECT version FROM schema_version").fetchall()
    }
    assert 3 in applied_versions


def test_migration_0003_creates_backtest_tables(data_conn):
    rows = data_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {row[0] for row in rows}
    assert "backtest_runs" in table_names
    assert "backtest_trades" in table_names


def test_backtest_runs_columns(data_conn):
    columns = {row[1] for row in data_conn.execute("PRAGMA table_info(backtest_runs)")}
    assert columns == {
        "run_id",
        "started_at",
        "strategy_id",
        "profile",
        "params_json",
        "seed",
        "code_version",
    }


def test_backtest_trades_columns(data_conn):
    columns = {row[1] for row in data_conn.execute("PRAGMA table_info(backtest_trades)")}
    assert columns == {
        "trade_id",
        "run_id",
        "position_id",
        "strategy_id",
        "symbol",
        "asset_class",
        "entry_ts",
        "entry_price",
        "exit_ts",
        "exit_price",
        "qty",
        "fees",
        "slippage",
        "pnl",
        "exit_reason",
    }


def test_backtest_trades_asset_class_check_constraint(data_conn):
    _insert_run(data_conn)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_trade(data_conn, asset_class="not_a_real_class")


def test_backtest_trades_exit_reason_check_constraint(data_conn):
    _insert_run(data_conn)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_trade(data_conn, exit_reason="not_a_real_reason")


def test_backtest_trades_valid_row_inserts_cleanly(data_conn):
    _insert_run(data_conn)
    _insert_trade(data_conn)
    row = data_conn.execute("SELECT * FROM backtest_trades").fetchone()
    assert row is not None
