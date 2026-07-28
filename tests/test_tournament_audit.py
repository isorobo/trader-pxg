"""Wave 4 tests: D-09 audit-record completeness -- the phase's exit gate is
an owner who can trace every decision to numbers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from trader.paper import config as paper_config
from trader.tournament import freeze_gate, judge

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)

_SEEDS = sorted(cfg.profile_name for cfg in paper_config.LIVE_STRATEGY_CONFIGS)


@pytest.fixture(autouse=True)
def _mock_alerts(monkeypatch):
    mock = MagicMock(return_value=True)
    monkeypatch.setattr(judge.alerts, "notify", mock)
    return mock


def _run(conn, tmp_path, now=NOW):
    return judge.run_tournament_once(
        conn, now=now, report_base_dir=str(tmp_path / "tournament")
    )


def _cohort(conn, factory, bad: str | None = None) -> None:
    for name in _SEEDS:
        pnls = [-20.0] * 30 if name == bad else [10.0] * 30
        factory(conn, name, pnls)


def test_run_row_complete_after_a_run(paper_conn, paper_trade_factory, tmp_path):
    _cohort(paper_conn, paper_trade_factory)

    result = _run(paper_conn, tmp_path)

    row = paper_conn.execute(
        "SELECT config_hash, registry_hash_before, registry_hash_after, "
        "inputs_snapshot_json, report_path FROM tournament_runs WHERE run_id = ?",
        (result["run_id"],),
    ).fetchone()
    config_hash, before, after, snapshot_json, report_path = row

    assert config_hash == freeze_gate.FROZEN_TOURNAMENT_HASH
    assert before and after  # both hashes set on a completed run
    snapshot = json.loads(snapshot_json)
    assert set(snapshot) == set(_SEEDS)
    for snap in snapshot.values():
        assert {"state", "trade_count", "sharpe", "profit_factor"} <= set(snap)
    assert report_path is not None


def test_every_decision_row_has_citation_and_metrics(
    paper_conn, paper_trade_factory, tmp_path
):
    _cohort(paper_conn, paper_trade_factory, bad=_SEEDS[1])

    result = _run(paper_conn, tmp_path)

    rows = paper_conn.execute(
        "SELECT profile_name, decision, prior_state, new_state, sharpe, "
        "profit_factor, trade_count, rule_citation FROM tournament_decisions "
        "WHERE run_id = ?",
        (result["run_id"],),
    ).fetchall()
    assert len(rows) == len(_SEEDS)
    for name, decision, prior, new, sharpe, pf, n, citation in rows:
        assert decision in ("promote", "retire", "hold", "enter")
        assert prior is not None and new is not None
        assert citation and "D-0" in citation  # cites a pre-registered rule
        assert n == 30
        assert sharpe is not None


def test_registry_hash_changes_iff_roster_changed(
    paper_conn, paper_trade_factory, tmp_path
):
    _cohort(paper_conn, paper_trade_factory, bad=_SEEDS[1])

    # Three strike runs: roster unchanged, hashes equal.
    for _ in range(3):
        result = _run(paper_conn, tmp_path)
        assert result["registry_hash_before"] == result["registry_hash_after"]

    # Fourth run retires the bad seed: hash must change.
    result = _run(paper_conn, tmp_path)
    assert result["counts"]["retire"] == 1
    assert result["registry_hash_before"] != result["registry_hash_after"]


def test_markdown_decision_record_written_and_traceable(
    paper_conn, paper_trade_factory, tmp_path
):
    _cohort(paper_conn, paper_trade_factory, bad=_SEEDS[1])

    result = _run(paper_conn, tmp_path)

    report = Path(result["report_path"])
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert freeze_gate.FROZEN_TOURNAMENT_HASH in text
    assert result["registry_hash_before"] in text
    assert result["registry_hash_after"] in text
    for name in _SEEDS:
        assert name in text
    assert "strike 1/4" in text  # the demotion citation is in the human record


def test_retire_path_end_to_end_without_integrity_error(
    paper_conn, paper_trade_factory, tmp_path
):
    """07-RESEARCH.md Pitfall 2 regression at the full-stack level: four
    sustained strike runs end in ledger.retire_strategy('tournament_demotion')
    against the rebuilt CHECK -- no IntegrityError anywhere."""
    _cohort(paper_conn, paper_trade_factory, bad=_SEEDS[1])

    for _ in range(4):
        result = _run(paper_conn, tmp_path)

    assert result["counts"]["retire"] == 1
    kill = paper_conn.execute(
        "SELECT reason, trigger_value FROM strategy_kill_state WHERE strategy_id = ?",
        (_SEEDS[1],),
    ).fetchone()
    assert kill[0] == "tournament_demotion"
    assert kill[1] is not None  # the judging sharpe, traceable


def test_telegram_summary_sent_once_per_run(
    paper_conn, paper_trade_factory, tmp_path, _mock_alerts
):
    _cohort(paper_conn, paper_trade_factory)

    _run(paper_conn, tmp_path)

    assert _mock_alerts.call_count == 1
    entry_type, message = _mock_alerts.call_args.args
    assert entry_type == "tournament"
    assert "tournament run" in message
    assert "report" in message


def test_transitions_reference_the_run(paper_conn, paper_trade_factory, tmp_path):
    """Every state change the judge makes carries the run_id, so the audit
    can join decision -> transition -> run."""
    _cohort(paper_conn, paper_trade_factory, bad=_SEEDS[1])
    for _ in range(4):
        result = _run(paper_conn, tmp_path)

    transition = paper_conn.execute(
        "SELECT run_id, to_state FROM strategy_registry_transitions "
        "WHERE profile_name = ? AND to_state = 'retired'",
        (_SEEDS[1],),
    ).fetchone()
    assert transition == (result["run_id"], "retired")
