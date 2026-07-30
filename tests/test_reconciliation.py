"""Tests for trader.paper.reconcile / trader.paper.clear_halt -- PAPER-04's
reconciliation classification, the combined entry-halt gate, and the sole
human-invoked CLI that can ever clear a reconciliation halt (05-04-PLAN.md).

classify_divergence is pure (zero I/O) -- covered first, standalone.
Persistence (record_reconciliation/is_entry_halted/run_reconcile_once) uses
the `paper_conn` fixture (tests/conftest.py, trader.data.db's migration
runner with migrations/0005_paper_trading.sql already applied) and the
`fake_ib` fixture (a MagicMock standing in for ib_async.IB) -- never a real
Gateway connection.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RECONCILE_SOURCE_PATH = REPO_ROOT / "trader" / "paper" / "reconcile.py"
CLEAR_HALT_SOURCE_PATH = REPO_ROOT / "trader" / "paper" / "clear_halt.py"


# ---------------------------------------------------------------------------
# Test doubles (plain objects, mirroring tests/test_broker_ibkr.py's
# convention -- never MagicMock, so attribute-shape mistakes surface as
# AttributeError instead of silently passing)
# ---------------------------------------------------------------------------


class _FakeContract:
    def __init__(self, symbol: str):
        self.symbol = symbol


class _FakePosition:
    def __init__(self, symbol: str, qty: float):
        self.contract = _FakeContract(symbol)
        self.position = qty


def _make_fake_position(symbol: str, qty: float) -> _FakePosition:
    return _FakePosition(symbol, qty)


# ---------------------------------------------------------------------------
# classify_divergence -- pure classification (T-05-04, conservative default)
# ---------------------------------------------------------------------------


def test_classify_divergence_no_divergence_returns_empty_list():
    from trader.paper import reconcile

    result = reconcile.classify_divergence(
        local_positions={"AAPL": 10}, broker_positions={"AAPL": 10}, pending_qty={}
    )
    assert result == []


def test_classify_divergence_exact_pending_match_is_explainable():
    from trader.paper import reconcile

    result = reconcile.classify_divergence(
        local_positions={"AAPL": 0},
        broker_positions={"AAPL": 10},
        pending_qty={"AAPL": 10},
    )
    assert len(result) == 1
    assert result[0] == {
        "symbol": "AAPL",
        "local_qty": 0,
        "broker_qty": 10,
        "classification": "explainable",
    }


def test_classify_divergence_no_pending_order_is_unexplained():
    from trader.paper import reconcile

    result = reconcile.classify_divergence(
        local_positions={"AAPL": 0}, broker_positions={"AAPL": 10}, pending_qty={}
    )
    assert len(result) == 1
    assert result[0]["classification"] == "unexplained"


def test_classify_divergence_partial_mismatch_is_unexplained_conservative_default():
    """A pending qty exists for the symbol but does not exactly equal the
    delta -- never assumed explainable (T-05-04, no tolerance band)."""
    from trader.paper import reconcile

    result = reconcile.classify_divergence(
        local_positions={"AAPL": 10},
        broker_positions={"AAPL": 7},
        pending_qty={"AAPL": 10},
    )
    assert len(result) == 1
    assert result[0]["classification"] == "unexplained"


def test_classify_divergence_pending_submit_only_qty_excluded_is_unexplained():
    """pending_qty here simulates ledger.get_pending_order_qty's real
    exclusion of 'pending_submit' rows (05-01's BLOCKER 1) -- a broker-side
    position whose only local trace is 'pending_submit' never appears in
    pending_qty and must classify unexplained (05-07's recovery test
    exercises this end to end)."""
    from trader.paper import reconcile

    result = reconcile.classify_divergence(
        local_positions={}, broker_positions={"AAPL": 5}, pending_qty={}
    )
    assert len(result) == 1
    assert result[0]["classification"] == "unexplained"


def test_classify_divergence_multiple_symbols_classified_independently():
    from trader.paper import reconcile

    result = reconcile.classify_divergence(
        local_positions={"AAPL": 0, "MSFT": 10},
        broker_positions={"AAPL": 10, "MSFT": 10},
        pending_qty={"AAPL": 10},
    )
    assert len(result) == 1
    assert result[0]["symbol"] == "AAPL"
    assert result[0]["classification"] == "explainable"


def test_classify_divergence_never_imports_sqlite_or_db():
    """classify_divergence is pure -- zero I/O -- mirrors
    trader/risk/breakers.py's evaluate_breakers purity guarantee."""
    source = RECONCILE_SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "sqlite3"


def test_reconcile_never_redefines_get_pending_order_qty():
    """get_pending_order_qty is consumed unchanged from ledger.py -- never
    redefined here (BLOCKER 1 consistency)."""
    source = RECONCILE_SOURCE_PATH.read_text(encoding="utf-8")
    assert "def get_pending_order_qty" not in source


def test_reconcile_module_never_writes_clear_action():
    """action='clear' must never be written from reconcile.py -- clear_halt.py
    is the sole writer of that action (T-05-08)."""
    source = RECONCILE_SOURCE_PATH.read_text(encoding="utf-8")
    assert "'clear'" not in source
    assert '"clear"' not in source


def test_reconcile_has_no_module_level_cached_boolean():
    """is_entry_halted must never cache -- re-derived on every call
    (standing rule 4). No module-level boolean constant anywhere in the
    file."""
    source = RECONCILE_SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, bool):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                pytest.fail(f"module-level cached boolean found: {names}")


# ---------------------------------------------------------------------------
# record_reconciliation -- thin, parameterized append-only writer
# ---------------------------------------------------------------------------


def test_record_reconciliation_action_halt_for_unexplained(paper_conn):
    from trader.paper import reconcile

    reconcile.record_reconciliation(
        paper_conn, "AAPL", "ibkr_paper", 0, 10, "unexplained"
    )
    row = paper_conn.execute(
        "SELECT symbol, venue, local_qty, broker_qty, classification, action, actor "
        "FROM reconciliation_log"
    ).fetchone()
    assert row == ("AAPL", "ibkr_paper", 0, 10, "unexplained", "halt", "system")


def test_record_reconciliation_action_log_for_explainable(paper_conn):
    from trader.paper import reconcile

    reconcile.record_reconciliation(
        paper_conn, "AAPL", "ibkr_paper", 0, 10, "explainable"
    )
    row = paper_conn.execute("SELECT action FROM reconciliation_log").fetchone()
    assert row[0] == "log"


def test_record_reconciliation_stores_sql_injection_shaped_reason_literally(paper_conn):
    from trader.paper import reconcile

    poison = "'); DROP TABLE reconciliation_log; --"
    reconcile.record_reconciliation(
        paper_conn, "AAPL", "ibkr_paper", 0, 10, "unexplained", reason=poison
    )
    row = paper_conn.execute("SELECT reason FROM reconciliation_log").fetchone()
    assert row[0] == poison
    count = paper_conn.execute("SELECT COUNT(*) FROM reconciliation_log").fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# is_entry_halted -- combined gate (D-07: Phase 4 breakers + Phase 5 halt)
# ---------------------------------------------------------------------------


def test_is_entry_halted_false_with_no_events_at_all(paper_conn):
    from trader.paper import reconcile

    assert reconcile.is_entry_halted(paper_conn) is False


def test_is_entry_halted_true_when_a_phase4_breaker_is_tripped(paper_conn):
    from trader.paper import reconcile
    from trader.risk import breakers

    breakers.append_breaker_event(
        paper_conn, "drawdown", "trip", trigger_value=-0.11, reason="dd breach"
    )
    assert reconcile.is_entry_halted(paper_conn) is True


def test_is_entry_halted_true_for_daily_loss_trip(paper_conn):
    from trader.paper import reconcile
    from trader.risk import breakers

    breakers.append_breaker_event(paper_conn, "daily_loss", "trip", trigger_value=-0.05)
    assert reconcile.is_entry_halted(paper_conn) is True


def test_is_entry_halted_true_for_consecutive_loss_trip(paper_conn):
    from trader.paper import reconcile
    from trader.risk import breakers

    breakers.append_breaker_event(paper_conn, "consecutive_loss", "trip", trigger_value=6)
    assert reconcile.is_entry_halted(paper_conn) is True


def test_is_entry_halted_true_after_unexplained_reconciliation_halt(paper_conn):
    from trader.paper import reconcile

    reconcile.record_reconciliation(
        paper_conn, "AAPL", "ibkr_paper", 0, 10, "unexplained"
    )
    assert reconcile.is_entry_halted(paper_conn) is True


def test_is_entry_halted_false_for_explainable_or_informational(paper_conn):
    from trader.paper import reconcile

    reconcile.record_reconciliation(
        paper_conn, "AAPL", "ibkr_paper", 0, 10, "explainable"
    )
    reconcile.record_reconciliation(
        paper_conn, "BTC", "kraken_readonly", 1, 1, "informational"
    )
    assert reconcile.is_entry_halted(paper_conn) is False


def test_is_entry_halted_false_again_only_after_clear_entry_halt(paper_conn, tmp_path):
    from trader.paper import clear_halt, reconcile

    reconcile.record_reconciliation(
        paper_conn, "AAPL", "ibkr_paper", 0, 10, "unexplained"
    )
    assert reconcile.is_entry_halted(paper_conn) is True

    clear_halt.clear_entry_halt(
        paper_conn,
        "false alarm, verified in Gateway",
        log_path=str(tmp_path / "ops.log"),
    )
    assert reconcile.is_entry_halted(paper_conn) is False


# ---------------------------------------------------------------------------
# run_reconcile_once -- the --once CLI body
# ---------------------------------------------------------------------------


def test_run_reconcile_once_records_unexplained_and_halts(
    paper_conn, fake_ib, tmp_path, monkeypatch
):
    from trader.paper import broker_ibkr, reconcile

    # alerts.notify() falls back to ops_log.append_ops_log at its default
    # relative path when Telegram isn't configured -- chdir into tmp_path so
    # this test never writes into the real project's ops/ directory.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    fake_ib.positions.return_value = [_make_fake_position("AAPL", 10)]
    adapter = broker_ibkr.IBKRBrokerAdapter(ib_client=fake_ib)

    summary = reconcile.run_reconcile_once(paper_conn, adapter)

    assert summary["halted"] is True
    assert len(summary["divergences"]) == 1
    assert summary["divergences"][0]["symbol"] == "AAPL"
    assert summary["divergences"][0]["classification"] == "unexplained"

    row = paper_conn.execute(
        "SELECT symbol, venue, classification, action FROM reconciliation_log"
    ).fetchone()
    assert row == ("AAPL", "ibkr_paper", "unexplained", "halt")


def test_run_reconcile_once_no_divergence_when_positions_match(paper_conn, fake_ib):
    from trader.paper import broker_ibkr, ledger, reconcile
    from trader.backtest.config import PROFILE_TIME_STOP_1D

    ledger.record_order(
        paper_conn, "s:AAPL:2026-07-27:buy:entry", "strat_a", "AAPL",
        "ibkr_paper", "buy", "entry", 10,
    )
    ledger.open_position(
        paper_conn, "strat_a", "AAPL", "ibkr_paper", "equity", 10, 190.0,
        "2026-07-27T00:00:00Z", "s:AAPL:2026-07-27:buy:entry", PROFILE_TIME_STOP_1D,
    )
    fake_ib.positions.return_value = [_make_fake_position("AAPL", 10)]
    adapter = broker_ibkr.IBKRBrokerAdapter(ib_client=fake_ib)

    summary = reconcile.run_reconcile_once(paper_conn, adapter)

    assert summary["divergences"] == []
    assert summary["halted"] is False


def test_run_reconcile_once_calls_alerts_notify_on_unexplained(paper_conn, fake_ib, monkeypatch):
    from trader.paper import broker_ibkr, reconcile

    notified = []
    monkeypatch.setattr(
        reconcile.alerts,
        "notify",
        lambda entry_type, message: notified.append((entry_type, message)) or True,
    )

    fake_ib.positions.return_value = [_make_fake_position("AAPL", 10)]
    adapter = broker_ibkr.IBKRBrokerAdapter(ib_client=fake_ib)
    reconcile.run_reconcile_once(paper_conn, adapter)

    assert len(notified) == 1
    assert notified[0][0] == "error"
    assert "AAPL" in notified[0][1]


def test_run_reconcile_once_never_calls_alerts_notify_when_no_unexplained(
    paper_conn, fake_ib, monkeypatch
):
    from trader.paper import broker_ibkr, reconcile

    notified = []
    monkeypatch.setattr(
        reconcile.alerts,
        "notify",
        lambda entry_type, message: notified.append((entry_type, message)) or True,
    )

    adapter = broker_ibkr.IBKRBrokerAdapter(ib_client=fake_ib)
    reconcile.run_reconcile_once(paper_conn, adapter)

    assert notified == []


class _FakeCryptoAdapter:
    def __init__(self, result):
        self._result = result

    def check_readonly(self):
        return self._result


def test_run_reconcile_once_records_crypto_check_as_informational_never_halts(
    paper_conn, fake_ib
):
    from trader.paper import broker_ibkr, reconcile

    adapter = broker_ibkr.IBKRBrokerAdapter(ib_client=fake_ib)
    crypto_adapter = _FakeCryptoAdapter(
        {"symbol": "BTC", "local_qty": 1.0, "broker_qty": 1.0, "reason": "matched"}
    )

    summary = reconcile.run_reconcile_once(paper_conn, adapter, crypto_adapter=crypto_adapter)

    row = paper_conn.execute(
        "SELECT venue, classification, action FROM reconciliation_log "
        "WHERE venue = 'kraken_readonly'"
    ).fetchone()
    assert row == ("kraken_readonly", "informational", "log")
    assert summary["halted"] is False


def test_run_reconcile_once_skips_crypto_check_when_none(paper_conn, fake_ib):
    from trader.paper import broker_ibkr, reconcile

    adapter = broker_ibkr.IBKRBrokerAdapter(ib_client=fake_ib)
    reconcile.run_reconcile_once(paper_conn, adapter, crypto_adapter=None)

    count = paper_conn.execute(
        "SELECT COUNT(*) FROM reconciliation_log WHERE venue = 'kraken_readonly'"
    ).fetchone()[0]
    assert count == 0


# ---------------------------------------------------------------------------
# main -- --once CLI entrypoint (D-05: no daemon)
# ---------------------------------------------------------------------------


def test_reconcile_main_requires_once(tmp_path):
    from trader.paper import reconcile

    with pytest.raises(SystemExit):
        reconcile.main(["--db-path", str(tmp_path / "trader.db")])


def test_reconcile_main_runs_once_and_prints_summary(tmp_path, capsys, monkeypatch):
    from trader.paper import reconcile

    db_path = str(tmp_path / "trader.db")

    class _FakeAdapter:
        def __init__(self):
            self.connected = False

        def connect(self):
            self.connected = True

        def disconnect(self):
            self.connected = False

        def snapshot(self):
            # Real-Gateway regression (2026-07-30): snapshot() dereferences
            # the ib client, which only exists after connect() -- main()
            # forgot to call it and every fake silently tolerated that.
            assert self.connected, "main() must call connect() before snapshot()"
            return {"positions": {}, "open_orders": [], "fills": []}

    monkeypatch.setattr(reconcile, "IBKRBrokerAdapter", lambda *a, **k: _FakeAdapter())
    reconcile.main(["--once", "--db-path", db_path])

    captured = capsys.readouterr()
    assert "divergences" in captured.out
    assert "halted" in captured.out


# ---------------------------------------------------------------------------
# Task Scheduler artifacts (D-07: 60-second cadence)
# ---------------------------------------------------------------------------


def test_paper_reconcile_bat_and_task_xml_exist():
    bat_path = REPO_ROOT / "scripts" / "paper_reconcile.bat"
    xml_path = REPO_ROOT / "scripts" / "paper_reconcile_task.xml"
    assert bat_path.exists()
    assert xml_path.exists()
    assert "trader.paper.reconcile" in bat_path.read_text(encoding="utf-8")
    assert "PT1M" in xml_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# clear_halt.py -- the sole human-invoked CLI (T-05-08, BLOCKER 3)
# ---------------------------------------------------------------------------


def test_clear_entry_halt_inserts_clear_row_with_human_actor(paper_conn, tmp_path):
    from trader.paper import clear_halt

    clear_halt.clear_entry_halt(
        paper_conn,
        "false alarm, verified in Gateway",
        log_path=str(tmp_path / "ops.log"),
    )
    row = paper_conn.execute(
        "SELECT classification, action, reason, actor FROM reconciliation_log"
    ).fetchone()
    assert row == (
        "informational",
        "clear",
        "false alarm, verified in Gateway",
        "human",
    )


def test_clear_entry_halt_appends_manual_restart_required_ops_log_entry(
    paper_conn, tmp_path
):
    from trader.paper import clear_halt

    log_path = str(tmp_path / "ops.log")
    clear_halt.clear_entry_halt(
        paper_conn, "false alarm, verified in Gateway", log_path=log_path
    )

    lines = [
        line for line in open(log_path, encoding="utf-8").read().splitlines() if line
    ]
    assert len(lines) == 1
    assert "manual_restart_required" in lines[0]
    assert "false alarm, verified in Gateway" in lines[0]

    row = paper_conn.execute(
        "SELECT action FROM reconciliation_log"
    ).fetchone()
    assert row[0] == "clear"


def test_clear_entry_halt_flips_is_entry_halted_false(paper_conn, tmp_path):
    from trader.paper import clear_halt, reconcile

    reconcile.record_reconciliation(
        paper_conn, "AAPL", "ibkr_paper", 0, 10, "unexplained"
    )
    assert reconcile.is_entry_halted(paper_conn) is True

    clear_halt.clear_entry_halt(
        paper_conn, "verified", log_path=str(tmp_path / "ops.log")
    )
    assert reconcile.is_entry_halted(paper_conn) is False


def test_clear_halt_module_is_sole_writer_of_action_clear():
    """Grepping across trader/paper for the literal action='clear' write
    must find it only in clear_halt.py (T-05-08)."""
    paper_dir = REPO_ROOT / "trader" / "paper"
    offenders = []
    for path in paper_dir.rglob("*.py"):
        if path.name == "clear_halt.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "'clear'" in source or '"clear"' in source:
            offenders.append(str(path))
    assert offenders == []


def test_clear_halt_cli_end_to_end_clears_halt_and_logs_intervention(
    paper_conn, tmp_path
):
    """main()'s CLI shape is --reason/--db-path only (identical to
    clear_breaker.py's CLI) -- it never exposes --log-path, so it always
    calls ops_log.append_ops_log through clear_entry_halt's default
    parameter. trader.paper.ops_log caches one logger per log_path string
    at module scope (tests/test_alerts.py's own convention already relies
    on this), so this test asserts the ops-log call was made with the
    right args via a mock rather than reading a real file -- avoiding any
    cross-test file-handle collision on the shared default relative path.
    """
    from unittest.mock import patch

    from trader.data import db
    from trader.paper import clear_halt, reconcile

    db_path = str(tmp_path / "trader.db")
    conn = db.get_connection(db_path)
    reconcile.record_reconciliation(conn, "AAPL", "ibkr_paper", 0, 10, "unexplained")
    conn.close()

    with patch("trader.paper.ops_log.append_ops_log") as mock_append:
        clear_halt.main(["--reason", "verified in Gateway", "--db-path", db_path])

    mock_append.assert_called_once_with(
        "manual_restart_required", "verified in Gateway", clear_halt._DEFAULT_LOG_PATH
    )

    conn = db.get_connection(db_path)
    assert reconcile.is_entry_halted(conn) is False
    conn.close()


def test_clear_halt_cli_requires_reason_argument(tmp_path):
    from trader.paper import clear_halt

    with pytest.raises(SystemExit):
        clear_halt.main(["--db-path", str(tmp_path / "trader.db")])


def test_clear_halt_every_conn_execute_call_uses_a_parameterized_query_string():
    source = CLEAR_HALT_SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    execute_calls = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("execute", "executemany")
            and node.args
        ):
            execute_calls += 1
            sql_arg = node.args[0]
            assert isinstance(sql_arg, ast.Constant) and isinstance(sql_arg.value, str)
    assert execute_calls > 0
