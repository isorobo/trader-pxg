"""Tests for trader.risk.breakers -- RISK-03's circuit breakers (D-04/D-05,
04-RESEARCH.md Q4).

Covers the pure, incremental evaluate_breakers function (daily-loss,
drawdown+HWM, consecutive-loss trip conditions; the no-lookahead HWM
regression; a simulation against a REAL Phase 2 harness equity curve built
via trader.backtest.metrics._build_daily_equity_curve). Persistence and the
human-only manual-restart clear path are covered further down this file
(added alongside trader/risk/clear_breaker.py).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from trader.backtest.metrics import _build_daily_equity_curve
from trader.risk import config

REPO_ROOT = Path(__file__).resolve().parents[1]
BREAKERS_SOURCE_PATH = REPO_ROOT / "trader" / "risk" / "breakers.py"


# ---------------------------------------------------------------------------
# evaluate_breakers -- daily_loss
# ---------------------------------------------------------------------------


def test_daily_loss_trips_at_exact_threshold():
    from trader.risk import breakers

    equity_curve = [100_000.0, 97_000.0]  # exactly -3.0%
    result = breakers.evaluate_breakers(equity_curve, [], config)
    assert result["daily_loss_tripped"] is True
    assert result["daily_loss_value"] == pytest.approx(-0.03)


def test_daily_loss_does_not_trip_on_smaller_loss():
    from trader.risk import breakers

    equity_curve = [100_000.0, 98_000.0]  # -2.0%, smaller than threshold
    result = breakers.evaluate_breakers(equity_curve, [], config)
    assert result["daily_loss_tripped"] is False
    assert result["daily_loss_value"] == pytest.approx(-0.02)


def test_daily_loss_value_is_none_with_fewer_than_two_points():
    from trader.risk import breakers

    result = breakers.evaluate_breakers([100_000.0], [], config)
    assert result["daily_loss_tripped"] is False
    assert result["daily_loss_value"] is None


# ---------------------------------------------------------------------------
# evaluate_breakers -- drawdown (incremental HWM)
# ---------------------------------------------------------------------------


def test_drawdown_trips_at_exact_threshold():
    from trader.risk import breakers

    equity_curve = [100_000.0, 110_000.0, 99_000.0]  # HWM 110000, dd = -10%
    result = breakers.evaluate_breakers(equity_curve, [], config)
    assert result["drawdown_tripped"] is True
    assert result["drawdown_value"] == pytest.approx(-0.10)


def test_drawdown_does_not_trip_on_smaller_decline():
    from trader.risk import breakers

    equity_curve = [100_000.0, 110_000.0, 100_000.0]  # dd ~ -9.09%
    result = breakers.evaluate_breakers(equity_curve, [], config)
    assert result["drawdown_tripped"] is False


def test_drawdown_no_lookahead_regression():
    """A curve that dips below the drawdown threshold at index 2 then
    recovers above the prior peak by the final index -- calling
    evaluate_breakers with the curve truncated to [:3] must still report
    drawdown_tripped=True, proving the breaker cannot "see" the future
    recovery (04-RESEARCH.md Pitfall 2). This test would fail if
    evaluate_breakers ever regressed to a retrospective full-curve pattern.
    """
    from trader.risk import breakers

    full_curve = [100_000.0, 110_000.0, 98_000.0, 130_000.0]
    truncated = full_curve[:3]  # up to and including the dip

    result_truncated = breakers.evaluate_breakers(truncated, [], config)
    assert result_truncated["drawdown_tripped"] is True

    result_full = breakers.evaluate_breakers(full_curve, [], config)
    assert result_full["drawdown_tripped"] is False  # final point recovered


# ---------------------------------------------------------------------------
# evaluate_breakers -- consecutive_loss
# ---------------------------------------------------------------------------


def test_consecutive_loss_trips_at_exact_threshold():
    from trader.risk import breakers

    trade_pnls = [100.0, -10.0, -20.0, -30.0, -40.0, -50.0, -60.0]  # 6 trailing losses
    result = breakers.evaluate_breakers([100_000.0], trade_pnls, config)
    assert result["consecutive_loss_tripped"] is True
    assert result["consecutive_loss_count"] == 6


def test_consecutive_loss_does_not_trip_below_threshold():
    from trader.risk import breakers

    trade_pnls = [-10.0, -20.0, -30.0, -40.0, -50.0]  # 5 trailing losses
    result = breakers.evaluate_breakers([100_000.0], trade_pnls, config)
    assert result["consecutive_loss_tripped"] is False
    assert result["consecutive_loss_count"] == 5


def test_consecutive_loss_resets_after_a_win():
    from trader.risk import breakers

    trade_pnls = [-10.0, -20.0, -30.0, -40.0, -50.0, -60.0, 5.0, -10.0]
    result = breakers.evaluate_breakers([100_000.0], trade_pnls, config)
    assert result["consecutive_loss_tripped"] is False
    assert result["consecutive_loss_count"] == 1


def test_consecutive_loss_count_zero_when_no_trades():
    from trader.risk import breakers

    result = breakers.evaluate_breakers([100_000.0], [], config)
    assert result["consecutive_loss_count"] == 0
    assert result["consecutive_loss_tripped"] is False


# ---------------------------------------------------------------------------
# Simulation against a REAL Phase 2 harness equity curve
# ---------------------------------------------------------------------------


def test_harness_simulation_steps_trip_each_breaker_on_correct_day():
    """Synthetic trades (exit_ts + pnl) fed through the REAL Phase 2 harness
    curve builder, then evaluate_breakers is called once per day,
    chronologically, on the curve truncated to "as of that day" -- proving
    each breaker trips on the exact day its condition is first met and not
    before (04-RESEARCH.md Pitfall 2's stepping discipline)."""
    from trader.risk import breakers

    starting_equity = 100_000.0
    trades = [
        {"exit_ts": "2026-01-01", "pnl": 1_000.0},
        {"exit_ts": "2026-01-02", "pnl": -500.0},
        {"exit_ts": "2026-01-03", "pnl": -4_000.0},
        {"exit_ts": "2026-01-04", "pnl": 200.0},
        {"exit_ts": "2026-01-05", "pnl": -6_500.0},
        {"exit_ts": "2026-01-06", "pnl": 15_000.0},
    ]
    equity_curve = _build_daily_equity_curve(trades, starting_equity)
    trade_pnls = [trade["pnl"] for trade in trades]

    daily_loss_trip_days = set()
    drawdown_trip_days = set()
    for i in range(1, len(equity_curve)):
        result = breakers.evaluate_breakers(
            equity_curve[: i + 1], trade_pnls[:i], config
        )
        if result["daily_loss_tripped"]:
            daily_loss_trip_days.add(i)
        if result["drawdown_tripped"]:
            drawdown_trip_days.add(i)

    assert daily_loss_trip_days == {3, 5}
    assert drawdown_trip_days == {5}


# ---------------------------------------------------------------------------
# evaluate_breakers -- purity (zero DB/file I/O)
# ---------------------------------------------------------------------------


def test_breakers_module_never_imports_sqlite_or_db():
    """breakers.py may mention trader.data.db in prose (docstrings), but
    must never actually import sqlite3 or trader.data.db -- evaluate_breakers
    performs zero DB/file I/O."""
    source = BREAKERS_SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "sqlite3"
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module != "sqlite3"
            assert not module.startswith("trader.data")


# ---------------------------------------------------------------------------
# Persistence: append_breaker_event / read_breaker_state
# ---------------------------------------------------------------------------


@pytest.fixture
def data_conn(tmp_db_path):
    """A live connection to a fresh temp DB, bootstrapped via trader.data.db.

    Mirrors tests/test_risk_migration.py's data_conn fixture pattern --
    defined locally here rather than added to tests/conftest.py, per this
    plan's instruction not to modify conftest.py.
    """
    from trader.data import db

    connection = db.get_connection(tmp_db_path)
    yield connection
    connection.close()


def test_append_breaker_event_inserts_one_row(data_conn):
    from trader.risk import breakers

    breakers.append_breaker_event(
        data_conn, "daily_loss", "trip", trigger_value=-0.04, reason="test", actor="system"
    )
    row = data_conn.execute(
        "SELECT breaker_type, action, trigger_value, reason, actor FROM breaker_events"
    ).fetchone()
    assert row == ("daily_loss", "trip", -0.04, "test", "system")


def test_append_breaker_event_stores_sql_injection_shaped_reason_literally(data_conn):
    from trader.risk import breakers

    poison = "'); DROP TABLE breaker_events; --"
    breakers.append_breaker_event(data_conn, "daily_loss", "trip", reason=poison)

    row = data_conn.execute("SELECT reason FROM breaker_events").fetchone()
    assert row[0] == poison

    count = data_conn.execute("SELECT COUNT(*) FROM breaker_events").fetchone()[0]
    assert count == 1  # table still exists and holds exactly the one row


def test_read_breaker_state_defaults_all_three_types_to_normal(data_conn):
    from trader.risk import breakers

    state = breakers.read_breaker_state(data_conn)
    assert set(state.keys()) == {"daily_loss", "drawdown", "consecutive_loss"}
    for info in state.values():
        assert info == {"current_action": "normal", "since": None, "reason": None}


def test_read_breaker_state_reports_trip_and_clear(data_conn):
    from trader.risk import breakers

    breakers.append_breaker_event(
        data_conn, "drawdown", "trip", trigger_value=-0.11, reason="dd breach"
    )
    state = breakers.read_breaker_state(data_conn)
    assert state["drawdown"]["current_action"] == "trip"

    breakers.clear_manual_restart(data_conn, reason="operator verified position sizing")
    state = breakers.read_breaker_state(data_conn)
    assert state["drawdown"]["current_action"] == "manual_restart"

    row = data_conn.execute(
        "SELECT actor FROM breaker_events WHERE action = 'manual_restart'"
    ).fetchone()
    assert row[0] == "human"


# ---------------------------------------------------------------------------
# record_breaker_transitions
# ---------------------------------------------------------------------------


def _evaluation(**overrides) -> dict:
    base = {
        "daily_loss_tripped": False,
        "daily_loss_value": None,
        "drawdown_tripped": False,
        "drawdown_value": None,
        "consecutive_loss_tripped": False,
        "consecutive_loss_count": 0,
    }
    base.update(overrides)
    return base


def test_record_transitions_appends_trip_on_normal_to_tripped(data_conn):
    from trader.risk import breakers

    previous_state = breakers.read_breaker_state(data_conn)
    evaluation = _evaluation(daily_loss_tripped=True, daily_loss_value=-0.04)

    breakers.record_breaker_transitions(data_conn, previous_state, evaluation)

    state = breakers.read_breaker_state(data_conn)
    assert state["daily_loss"]["current_action"] == "trip"


def test_record_transitions_does_not_duplicate_trip_while_already_tripped(data_conn):
    from trader.risk import breakers

    breakers.append_breaker_event(data_conn, "daily_loss", "trip", trigger_value=-0.05)
    previous_state = breakers.read_breaker_state(data_conn)
    evaluation = _evaluation(daily_loss_tripped=True, daily_loss_value=-0.06)

    breakers.record_breaker_transitions(data_conn, previous_state, evaluation)

    count = data_conn.execute(
        "SELECT COUNT(*) FROM breaker_events WHERE breaker_type='daily_loss' AND action='trip'"
    ).fetchone()[0]
    assert count == 1


def test_record_transitions_appends_reset_for_daily_loss_on_tripped_to_normal(data_conn):
    from trader.risk import breakers

    breakers.append_breaker_event(data_conn, "daily_loss", "trip", trigger_value=-0.05)
    previous_state = breakers.read_breaker_state(data_conn)
    evaluation = _evaluation(daily_loss_tripped=False, daily_loss_value=0.01)

    breakers.record_breaker_transitions(data_conn, previous_state, evaluation)

    state = breakers.read_breaker_state(data_conn)
    assert state["daily_loss"]["current_action"] == "reset"


def test_record_transitions_appends_reset_for_consecutive_loss_on_tripped_to_normal(data_conn):
    from trader.risk import breakers

    breakers.append_breaker_event(data_conn, "consecutive_loss", "trip", trigger_value=6)
    previous_state = breakers.read_breaker_state(data_conn)
    evaluation = _evaluation(consecutive_loss_tripped=False, consecutive_loss_count=0)

    breakers.record_breaker_transitions(data_conn, previous_state, evaluation)

    state = breakers.read_breaker_state(data_conn)
    assert state["consecutive_loss"]["current_action"] == "reset"


def test_record_transitions_trips_drawdown_on_normal_to_tripped(data_conn):
    from trader.risk import breakers

    previous_state = breakers.read_breaker_state(data_conn)
    evaluation = _evaluation(drawdown_tripped=True, drawdown_value=-0.12)

    breakers.record_breaker_transitions(data_conn, previous_state, evaluation)

    state = breakers.read_breaker_state(data_conn)
    assert state["drawdown"]["current_action"] == "trip"


def test_record_transitions_never_auto_resets_drawdown(data_conn):
    """Even when the evaluation reports drawdown_tripped=False after a
    prior trip, record_breaker_transitions must NOT clear it -- the
    drawdown breaker has exactly one clear path (clear_manual_restart),
    invoked only as a human command."""
    from trader.risk import breakers

    breakers.append_breaker_event(data_conn, "drawdown", "trip", trigger_value=-0.11)
    previous_state = breakers.read_breaker_state(data_conn)
    evaluation = _evaluation(drawdown_tripped=False, drawdown_value=0.02)

    breakers.record_breaker_transitions(data_conn, previous_state, evaluation)

    state = breakers.read_breaker_state(data_conn)
    assert state["drawdown"]["current_action"] == "trip"  # still tripped


# ---------------------------------------------------------------------------
# Security invariants (T-04-09, T-04-10)
# ---------------------------------------------------------------------------


def test_no_fstring_or_percent_format_sql_in_breakers_module():
    """Every SQL statement in breakers.py must use parameterized
    placeholders (ASVS V5) -- zero f-string/.format()-interpolated SQL."""
    source = BREAKERS_SOURCE_PATH.read_text(encoding="utf-8")
    assert 'f"' not in source
    assert "f'" not in source
    assert ".format(" not in source


def test_manual_restart_literal_confined_to_clear_manual_restart():
    """Grepping breakers.py's source for the literal string 'manual_restart'
    must find it used in exactly one function (clear_manual_restart) --
    proving no auto-clear path exists anywhere in the module (T-04-10)."""
    source = BREAKERS_SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    target_range = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "clear_manual_restart":
            target_range = (node.lineno, node.end_lineno)
    assert target_range is not None, "clear_manual_restart function not found"
    start, end = target_range

    for i, line in enumerate(source.splitlines(), start=1):
        if "manual_restart" in line:
            assert start <= i <= end, (
                f"line {i} contains 'manual_restart' outside clear_manual_restart: {line!r}"
            )


def test_clear_breaker_module_has_no_importers_under_trader():
    """trader/risk/clear_breaker.py must have no importer anywhere under
    trader/ (source may mention it in prose/docstrings) -- never actually
    imported from evaluate_breakers, record_breaker_transitions, or any
    other automated path."""
    trader_dir = REPO_ROOT / "trader"
    offenders = []
    for path in trader_dir.rglob("*.py"):
        if path.name == "clear_breaker.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name.endswith("clear_breaker") for alias in node.names
            ):
                offenders.append(str(path))
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(
                "clear_breaker"
            ):
                offenders.append(str(path))
            if isinstance(node, ast.ImportFrom) and any(
                alias.name == "clear_breaker" for alias in node.names
            ):
                offenders.append(str(path))
    assert offenders == []


# ---------------------------------------------------------------------------
# clear_breaker.py CLI -- the sole human-invoked entrypoint
# ---------------------------------------------------------------------------


def test_clear_breaker_cli_clears_manual_restart(tmp_db_path, capsys):
    from trader.data import db
    from trader.risk import breakers, clear_breaker

    conn = db.get_connection(tmp_db_path)
    breakers.append_breaker_event(conn, "drawdown", "trip", trigger_value=-0.11, reason="dd breach")
    conn.close()

    clear_breaker.main(["--db-path", tmp_db_path, "--reason", "operator verified sizing"])

    conn = db.get_connection(tmp_db_path)
    row = conn.execute(
        "SELECT action, actor, reason FROM breaker_events ORDER BY event_id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row == ("manual_restart", "human", "operator verified sizing")

    captured = capsys.readouterr()
    assert "operator verified sizing" in captured.out


def test_clear_breaker_cli_requires_reason_argument(tmp_db_path):
    from trader.risk import clear_breaker

    with pytest.raises(SystemExit):
        clear_breaker.main(["--db-path", tmp_db_path])
