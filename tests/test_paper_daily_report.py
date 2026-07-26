"""Tests for trader.paper.daily_report -- the paper-trading section of the
daily ground-truth report (05-07-PLAN.md, D-12), plus trader.ground_truth
.report.py's degrade-safely-on-failure integration (T-05-12).

Uses the paper_conn fixture (tests/conftest.py, every migration applied).
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trader.backtest.config import EXIT_PROFILE
from trader.paper import clear_halt, config as paper_config, daily_report, ledger, reconcile
from trader.risk import breakers

_PROFILE_A = paper_config.LIVE_STRATEGY_CONFIGS[0].profile_name
_PROFILE_B = paper_config.LIVE_STRATEGY_CONFIGS[1].profile_name

_PROFILE = EXIT_PROFILE(
    stop_pct=-0.10, tp_pct=None, scale_out=(), trailing_pct=None,
    max_hold_days=None, eod_flat=False,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MIGRATIONS_DIR = str(_REPO_ROOT / "migrations")


def _apply_phase5_schema(db_path: str) -> None:
    """Apply every migration (including 0004/0005's Phase 5 tables) to
    db_path, resolving the migrations/ directory by an ABSOLUTE path rather
    than trader.data.db.get_connection's hardcoded cwd-relative default --
    these report.main() integration tests chdir into tmp_path, where a
    relative "migrations" lookup would silently find nothing."""
    from trader.data import db as trader_db

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        trader_db.apply_migrations(conn, migrations_dir=_MIGRATIONS_DIR)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# compute_paper_section -- positions / closed trades
# ---------------------------------------------------------------------------


def test_compute_paper_section_lists_open_positions(paper_conn):
    ledger.open_position(
        paper_conn, _PROFILE_A, "AAPL", "ibkr_paper", "stock", 10, 100.0,
        "2026-07-26T09:30:00", "ref1", _PROFILE,
    )
    ledger.open_position(
        paper_conn, _PROFILE_B, "MSFT", "ibkr_paper", "stock", 5, 200.0,
        "2026-07-26T09:31:00", "ref2", _PROFILE,
    )

    lines = daily_report.compute_paper_section(paper_conn)
    text = "\n".join(lines)

    assert "## Paper Trading" in text
    assert "### Open Positions" in text
    assert "AAPL" in text
    assert "MSFT" in text


def test_compute_paper_section_lists_closed_trade_pnl(paper_conn):
    position_id = ledger.open_position(
        paper_conn, _PROFILE_A, "TSLA", "ibkr_paper", "stock", 10, 100.0,
        "2026-07-20T09:30:00", "ref3", _PROFILE,
    )
    ledger.close_position(
        paper_conn, position_id, exit_ts="2026-07-21T09:30:00", exit_price=142.0,
        exit_reason="stop", exit_order_ref="ref3exit", fees=1.0, slippage_cost=0.5,
        pnl=42.0,
    )

    lines = daily_report.compute_paper_section(paper_conn)
    text = "\n".join(lines)

    assert "### Recent Closed Trades" in text
    assert "TSLA" in text
    assert "42.00" in text


def test_compute_paper_section_reports_no_positions_or_trades_when_none_exist(paper_conn):
    lines = daily_report.compute_paper_section(paper_conn)
    text = "\n".join(lines)

    assert "No open positions." in text
    assert "No closed trades." in text


# ---------------------------------------------------------------------------
# compute_paper_section -- breaker / halt state
# ---------------------------------------------------------------------------


def test_compute_paper_section_reports_halted_true_and_the_cause(paper_conn):
    breakers.append_breaker_event(
        paper_conn, "drawdown", "trip", trigger_value=-0.11, reason="dd breach"
    )

    lines = daily_report.compute_paper_section(paper_conn)
    text = "\n".join(lines)

    assert "### Breaker / Halt State" in text
    assert "drawdown: trip" in text
    assert "Entry halted: True" in text


def test_compute_paper_section_reports_halted_false_by_default(paper_conn):
    lines = daily_report.compute_paper_section(paper_conn)
    text = "\n".join(lines)

    assert "Entry halted: False" in text


# ---------------------------------------------------------------------------
# compute_paper_section -- retired strategies
# ---------------------------------------------------------------------------


def test_compute_paper_section_lists_retired_strategy(paper_conn):
    ledger.retire_strategy(paper_conn, _PROFILE_A, "max_drawdown", -0.5)

    lines = daily_report.compute_paper_section(paper_conn)
    text = "\n".join(lines)

    assert "### Retired Strategies" in text
    assert _PROFILE_A in text
    assert "max_drawdown" in text


def test_compute_paper_section_none_retired_when_empty(paper_conn):
    lines = daily_report.compute_paper_section(paper_conn)
    text = "\n".join(lines)

    assert "None retired" in text


# ---------------------------------------------------------------------------
# compute_paper_section -- Manual Interventions tally (NEW, W2)
# ---------------------------------------------------------------------------


def test_compute_paper_section_manual_interventions_tally_includes_human_clears(
    paper_conn, tmp_path
):
    now = datetime.now(timezone.utc)
    reconcile.record_reconciliation(paper_conn, "AAPL", "ibkr_paper", 0, 10, "unexplained")
    clear_halt.clear_entry_halt(
        paper_conn, "test: verified broker fill in Gateway",
        log_path=str(tmp_path / "ops.log"),
    )
    breakers.clear_manual_restart(paper_conn, "test: cleared drawdown breaker")

    lines = daily_report.compute_paper_section(paper_conn, as_of=now)
    text = "\n".join(lines)

    assert "### Manual Interventions (window)" in text
    assert "test: verified broker fill in Gateway" in text
    assert "test: cleared drawdown breaker" in text


def test_compute_paper_section_manual_interventions_none_this_window_when_empty(paper_conn):
    lines = daily_report.compute_paper_section(paper_conn)
    text = "\n".join(lines)

    assert "None this window" in text


def test_compute_paper_section_manual_interventions_excludes_scheduled_auth(
    paper_conn, tmp_path, monkeypatch
):
    """A weekly scheduled_auth ops-log entry never appears in the Manual
    Interventions tally -- it lives in the ops log file, not in
    reconciliation_log/breaker_events, so there is no code path that could
    conflate the two (W2/D-13)."""
    from trader.paper import ops_log

    log_path = str(tmp_path / "ops.log")
    monkeypatch.setattr(daily_report, "_OPS_LOG_PATH", log_path)
    ops_log.append_ops_log(
        "scheduled_auth", "weekly IBKR 2FA tap confirmed", log_path=log_path
    )
    clear_halt.clear_entry_halt(
        paper_conn, "test: real manual intervention", log_path=log_path
    )

    lines = daily_report.compute_paper_section(paper_conn, as_of=datetime.now(timezone.utc))
    text = "\n".join(lines)

    assert "weekly IBKR 2FA tap confirmed" not in text
    assert "test: real manual intervention" in text


def test_get_manual_reconciliation_events_only_returns_human_actor_rows(paper_conn):
    reconcile.record_reconciliation(paper_conn, "AAPL", "ibkr_paper", 0, 10, "unexplained")
    clear_halt.clear_entry_halt(paper_conn, "human clear", log_path="ops/does-not-matter.log")

    events = daily_report.get_manual_reconciliation_events(paper_conn, "2000-01-01 00:00:00")

    assert len(events) == 1
    assert events[0]["reason"] == "human clear"


def test_get_manual_breaker_events_only_returns_human_actor_rows(paper_conn):
    breakers.append_breaker_event(paper_conn, "daily_loss", "trip", reason="auto trip")
    breakers.clear_manual_restart(paper_conn, "human restart")

    events = daily_report.get_manual_breaker_events(paper_conn, "2000-01-01 00:00:00")

    assert len(events) == 1
    assert events[0]["reason"] == "human restart"


# ---------------------------------------------------------------------------
# compute_paper_section -- scheduled-run coverage line
# ---------------------------------------------------------------------------


def test_compute_paper_section_includes_coverage_line(paper_conn):
    lines = daily_report.compute_paper_section(paper_conn)
    text = "\n".join(lines)

    assert "### Scheduled-Run Coverage (24h)" in text
    assert "Coverage:" in text


# ---------------------------------------------------------------------------
# compute_paper_section -- never raises on a completely empty DB
# ---------------------------------------------------------------------------


def test_compute_paper_section_empty_db_never_raises_and_is_valid_markdown(paper_conn):
    lines = daily_report.compute_paper_section(paper_conn)

    assert isinstance(lines, list)
    assert all(isinstance(line, str) for line in lines)
    text = "\n".join(lines)
    assert "## Paper Trading" in text
    assert "None this window" in text


# ---------------------------------------------------------------------------
# trader.ground_truth.report.main() -- degrades safely on Phase 5 failure
# (T-05-12)
# ---------------------------------------------------------------------------


def test_ground_truth_report_main_still_writes_report_when_paper_section_import_fails(
    tmp_path, monkeypatch
):
    """Breaking trader.paper.daily_report's import path must never stop
    Phase 0's own report from being written -- proven end to end through
    report.main(). Setting sys.modules["trader.paper.daily_report"] to None
    forces the NEXT import of that dotted name to raise ImportError (a
    documented CPython mechanism) -- but only if that name is not already
    bound as an attribute on the `trader.paper` package object (Python's
    `from X import Y` resolves via getattr(X, "Y") first, only falling back
    to a fresh import of "X.Y" when that attribute is absent). Since this
    test suite's own module-level `from trader.paper import ... daily_report
    ...` import already ran earlier in the session, that attribute must be
    removed too, or report.py's own `from trader.paper import daily_report`
    would silently succeed via the cached attribute and never exercise the
    broken-import path at all."""
    import trader.paper as paper_pkg
    from trader.ground_truth import report

    monkeypatch.chdir(tmp_path)
    # Pre-create Phase 5's schema so the ONLY failure mode this test
    # exercises is the deliberately-broken import, not an incidentally
    # table-less fresh DB (that scenario is covered separately below).
    _apply_phase5_schema("data/trader.db")
    monkeypatch.delattr(paper_pkg, "daily_report", raising=False)
    monkeypatch.setitem(sys.modules, "trader.paper.daily_report", None)

    report.main(["--date", "2026-07-27"])

    out_path = tmp_path / "reports" / "2026-07-27.md"
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "Ground Truth Daily Report" in content
    assert "Paper Trading" not in content


def test_ground_truth_report_main_still_writes_report_when_paper_section_raises(
    tmp_path, monkeypatch
):
    from trader.ground_truth import report
    from trader.paper import daily_report as real_daily_report

    monkeypatch.chdir(tmp_path)
    _apply_phase5_schema("data/trader.db")

    def _boom(conn, as_of=None):
        raise RuntimeError("simulated Phase 5 failure")

    monkeypatch.setattr(real_daily_report, "compute_paper_section", _boom)

    report.main(["--date", "2026-07-27"])

    out_path = tmp_path / "reports" / "2026-07-27.md"
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "Ground Truth Daily Report" in content
    assert "Paper Trading" not in content


def test_ground_truth_report_main_appends_paper_section_on_success(tmp_path, monkeypatch):
    from trader.ground_truth import report

    monkeypatch.chdir(tmp_path)

    # Simulate Phase 5 having already run at least once against this same
    # data/trader.db file (entry_pipeline/guardian both connect via
    # trader.data.db's migration runner) -- without this, Phase 5's tables
    # genuinely do not exist yet, and report.main() must (correctly)
    # degrade to "no paper section this run" (T-05-12, proven by the two
    # tests above).
    _apply_phase5_schema("data/trader.db")

    report.main(["--date", "2026-07-27"])

    out_path = tmp_path / "reports" / "2026-07-27.md"
    content = out_path.read_text(encoding="utf-8")
    assert "Ground Truth Daily Report" in content
    assert "## Paper Trading" in content
    assert "None this window" in content
