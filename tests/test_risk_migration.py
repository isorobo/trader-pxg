"""Tests for migrations/0004_risk_breakers.sql -- breaker_events append-only
event log + breaker_state_current view (D-04/D-05, 04-RESEARCH.md Q4).
"""

import sqlite3

import pytest

from trader.data import db


@pytest.fixture
def data_conn(tmp_db_path):
    """A live connection to a fresh temp DB, bootstrapped via trader.data.db.

    Mirrors tests/test_backtest_migration.py's data_conn fixture pattern --
    defined locally here rather than added to tests/conftest.py, per this
    plan's instruction not to modify conftest.py.
    """
    connection = db.get_connection(tmp_db_path)
    yield connection
    connection.close()


def _insert_event(conn, **overrides):
    row = {
        "breaker_type": "daily_loss",
        "action": "trip",
        "trigger_value": -0.05,
        "reason": "daily loss exceeded threshold",
        "actor": "system",
    }
    row.update(overrides)
    conn.execute(
        """
        INSERT INTO breaker_events
            (breaker_type, action, trigger_value, reason, actor)
        VALUES (:breaker_type, :action, :trigger_value, :reason, :actor)
        """,
        row,
    )
    conn.commit()


def test_migration_0004_reaches_schema_version_4(data_conn):
    # Checks migration 0004 has been applied, not that it is the highest
    # version present -- later phases (e.g. migrations/0005_paper_trading.sql)
    # add further migrations on top, so schema_version's max legitimately
    # grows beyond 4 without this test needing to change.
    applied_versions = {
        row[0] for row in data_conn.execute("SELECT version FROM schema_version").fetchall()
    }
    assert 4 in applied_versions


def test_migration_0004_creates_breaker_events_table(data_conn):
    rows = data_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {row[0] for row in rows}
    assert "breaker_events" in table_names


def test_migration_0004_creates_breaker_state_current_view(data_conn):
    rows = data_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view'"
    ).fetchall()
    view_names = {row[0] for row in rows}
    assert "breaker_state_current" in view_names


def test_breaker_events_columns(data_conn):
    columns = {row[1] for row in data_conn.execute("PRAGMA table_info(breaker_events)")}
    assert columns == {
        "event_id",
        "ts",
        "breaker_type",
        "action",
        "trigger_value",
        "reason",
        "actor",
    }


def test_breaker_events_breaker_type_check_constraint(data_conn):
    with pytest.raises(sqlite3.IntegrityError):
        _insert_event(data_conn, breaker_type="not_a_real_breaker")


def test_breaker_events_action_check_constraint(data_conn):
    with pytest.raises(sqlite3.IntegrityError):
        _insert_event(data_conn, action="not_a_real_action")


def test_breaker_events_actor_check_constraint(data_conn):
    with pytest.raises(sqlite3.IntegrityError):
        _insert_event(data_conn, actor="not_a_real_actor")


def test_breaker_events_valid_row_inserts_cleanly(data_conn):
    _insert_event(data_conn)
    row = data_conn.execute("SELECT * FROM breaker_events").fetchone()
    assert row is not None


def test_breaker_state_current_shows_only_latest_event_per_type(data_conn):
    # Trip then reset for daily_loss -- only the reset (latest) should show.
    _insert_event(data_conn, breaker_type="daily_loss", action="trip", reason="tripped")
    _insert_event(data_conn, breaker_type="daily_loss", action="reset", reason="new session")
    # A second breaker_type with only one event, so multiple types are
    # covered by the same query.
    _insert_event(data_conn, breaker_type="drawdown", action="trip", reason="drawdown breach")

    rows = data_conn.execute(
        "SELECT breaker_type, current_action, reason FROM breaker_state_current "
        "ORDER BY breaker_type"
    ).fetchall()

    assert len(rows) == 2
    by_type = {row[0]: (row[1], row[2]) for row in rows}
    assert by_type["daily_loss"] == ("reset", "new session")
    assert by_type["drawdown"] == ("trip", "drawdown breach")


def test_breaker_state_current_one_row_per_type_with_events(data_conn):
    _insert_event(data_conn, breaker_type="consecutive_loss", action="trip")
    _insert_event(data_conn, breaker_type="consecutive_loss", action="trip")
    _insert_event(data_conn, breaker_type="consecutive_loss", action="reset")

    rows = data_conn.execute(
        "SELECT breaker_type FROM breaker_state_current WHERE breaker_type = 'consecutive_loss'"
    ).fetchall()
    assert len(rows) == 1
