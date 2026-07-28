"""Wave 4 tests: the weekly tournament judge (ATTR-02, D-03/D-04/D-05).

Fixture shapes come from paper_trade_factory (tests/conftest.py):
- [+10]*30 spread over 30 days -> strongly positive Sharpe ("clearly good")
- [-20]*30 -> negative Sharpe, PF 0.0 ("clearly bad")
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from trader.paper import config as paper_config
from trader.paper import config_store
from trader.tournament import frozen_config, judge, pipeline

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)

_SEEDS = sorted(cfg.profile_name for cfg in paper_config.LIVE_STRATEGY_CONFIGS)


@pytest.fixture(autouse=True)
def _mock_alerts(monkeypatch):
    mock = MagicMock(return_value=True)
    monkeypatch.setattr(judge.alerts, "notify", mock)
    return mock


@pytest.fixture
def run(tmp_path):
    def _run(conn, now=NOW):
        return judge.run_tournament_once(
            conn, now=now, report_base_dir=str(tmp_path / "tournament")
        )

    return _run


def _states(conn) -> dict[str, str]:
    return {
        row["profile_name"]: row["state"]
        for row in config_store.get_registry_rows(conn)
    }


# ---------------------------------------------------------------------------
# D-03: eligibility
# ---------------------------------------------------------------------------


def test_under_thirty_trades_all_held_never_judged(paper_conn, paper_trade_factory, run):
    paper_trade_factory(paper_conn, _SEEDS[0], [-500.0] * 29)  # terrible, but n<30

    result = run(paper_conn)

    assert result["counts"] == {"promote": 0, "retire": 0, "hold": 5, "enter": 0}
    for d in result["decisions"]:
        assert "D-03 eligibility" in d["rule_citation"]
    assert set(_states(paper_conn).values()) == {"full"}
    assert result["registry_hash_before"] == result["registry_hash_after"]


# ---------------------------------------------------------------------------
# D-04: probation -> full promotion
# ---------------------------------------------------------------------------


def _demote_to_probation(conn, name: str) -> None:
    conn.execute(
        "UPDATE strategy_registry SET state = 'probation' WHERE profile_name = ?",
        (name,),
    )
    conn.commit()


def test_probation_promoted_at_thirty_trades_above_floor(
    paper_conn, paper_trade_factory, run
):
    name = _SEEDS[0]
    _demote_to_probation(paper_conn, name)
    paper_trade_factory(paper_conn, name, [10.0] * 30)

    result = run(paper_conn)

    assert _states(paper_conn)[name] == "full"
    promote = next(d for d in result["decisions"] if d["decision"] == "promote")
    assert promote["profile_name"] == name
    assert "D-04 promotion" in promote["rule_citation"]
    assert "sharpe=" in promote["rule_citation"]
    # The paper-30 stamp landed as part of the promotion path (D-07).
    row = paper_conn.execute(
        "SELECT paper_30_confirmed_at FROM strategy_registry WHERE profile_name = ?",
        (name,),
    ).fetchone()
    assert row[0] is not None


def test_probation_below_floor_held(paper_conn, paper_trade_factory, run):
    name = _SEEDS[0]
    _demote_to_probation(paper_conn, name)
    paper_trade_factory(paper_conn, name, [-20.0] * 30)

    result = run(paper_conn)

    assert _states(paper_conn)[name] == "probation"
    held = next(d for d in result["decisions"] if d["profile_name"] == name)
    assert held["decision"] == "hold"
    assert "below promotion floor" in held["rule_citation"]


# ---------------------------------------------------------------------------
# D-04: compound demotion, sustained K evaluations
# ---------------------------------------------------------------------------


def _seed_cohort(conn, factory, bad: str) -> None:
    """Every seed gets 30 trades: four clearly good, `bad` clearly bad."""
    for name in _SEEDS:
        pnls = [-20.0] * 30 if name == bad else [10.0] * 30
        factory(conn, name, pnls)


def test_single_bad_run_is_a_strike_not_a_retirement(
    paper_conn, paper_trade_factory, run
):
    bad = _SEEDS[2]
    _seed_cohort(paper_conn, paper_trade_factory, bad)

    result = run(paper_conn)

    assert _states(paper_conn)[bad] == "full"
    strike = next(d for d in result["decisions"] if d["profile_name"] == bad)
    assert strike["decision"] == "hold"
    assert strike["demotion_strike"] == 1
    assert "strike 1/4" in strike["rule_citation"]


def test_sustained_strikes_retire_on_fourth_evaluation(
    paper_conn, paper_trade_factory, run
):
    bad = _SEEDS[2]
    _seed_cohort(paper_conn, paper_trade_factory, bad)

    for i in range(frozen_config.DEMOTION_SUSTAIN_EVALUATIONS - 1):
        run(paper_conn)
        assert _states(paper_conn)[bad] == "full", f"retired early at run {i + 1}"

    result = run(paper_conn)  # the K-th consecutive strike

    assert _states(paper_conn)[bad] == "retired"
    retire = next(d for d in result["decisions"] if d["decision"] == "retire")
    assert retire["profile_name"] == bad
    assert "sustained 4/4" in retire["rule_citation"]
    # D-08: the existing kill path fired too.
    kill = paper_conn.execute(
        "SELECT reason FROM strategy_kill_state WHERE strategy_id = ?", (bad,)
    ).fetchone()
    assert kill[0] == "tournament_demotion"


def test_recovery_resets_the_strike_streak(paper_conn, paper_trade_factory, run):
    """A strike-free evaluation breaks the streak: 2 strikes, then a good
    window, then 3 more strikes -- still not retired (needs 4 consecutive)."""
    bad = _SEEDS[2]
    _seed_cohort(paper_conn, paper_trade_factory, bad)
    run(paper_conn)
    run(paper_conn)  # 2 strikes

    # Recovery: 30 fresh winning trades push the bad strategy's rolling
    # window positive for one evaluation.
    paper_trade_factory(paper_conn, bad, [15.0] * 30, start="2026-03-01")
    run(paper_conn)  # strike-free

    # Relapse: 30 fresh losing trades, three more evaluations.
    paper_trade_factory(paper_conn, bad, [-20.0] * 30, start="2026-04-15")
    run(paper_conn)
    run(paper_conn)
    run(paper_conn)  # strikes 1..3 of the new streak

    assert _states(paper_conn)[bad] == "full"


def test_healthy_roster_never_retires_anyone(paper_conn, paper_trade_factory, run):
    """07-RESEARCH.md Pitfall 5: all-profitable cohort, K+2 evaluations --
    someone is always worst-ranked, but nobody is below the floor, so
    nobody is ever demoted."""
    for name in _SEEDS:
        paper_trade_factory(paper_conn, name, [10.0] * 30)

    for _ in range(frozen_config.DEMOTION_SUSTAIN_EVALUATIONS + 2):
        result = run(paper_conn)
        assert result["counts"]["retire"] == 0

    assert set(_states(paper_conn).values()) == {"full"}


# ---------------------------------------------------------------------------
# D-03: ranking tie-break
# ---------------------------------------------------------------------------


def test_rank_ties_broken_by_profit_factor():
    judged = {
        "a": {"sharpe_ratio": 1.0, "profit_factor": 2.0},
        "b": {"sharpe_ratio": 1.0, "profit_factor": 3.0},
        "c": {"sharpe_ratio": 2.0, "profit_factor": 1.1},
    }
    ranks = judge.rank_full_strategies(judged)
    assert ranks == {"c": 1, "b": 2, "a": 3}


def test_none_sharpe_ranks_worst():
    judged = {
        "a": {"sharpe_ratio": None, "profit_factor": 5.0},
        "b": {"sharpe_ratio": -1.0, "profit_factor": 0.5},
    }
    ranks = judge.rank_full_strategies(judged)
    assert ranks["a"] == 2


# ---------------------------------------------------------------------------
# D-05/D-07: candidate admission through the judge
# ---------------------------------------------------------------------------


def test_candidate_with_evidence_enters_when_slot_free(paper_conn, run):
    from trader.backtest.config import EXIT_PROFILE

    paper_conn.execute(
        "UPDATE strategy_registry SET state = 'retired' WHERE profile_name = ?",
        (_SEEDS[0],),
    )
    paper_conn.commit()
    pipeline.register_candidate(
        paper_conn, "donchian_v1", "donchian_breakout",
        EXIT_PROFILE(stop_pct=-0.1, tp_pct=0.2, scale_out=(), trailing_pct=None,
                     max_hold_days=None, eod_flat=False),
        pf_floor=0.9, max_dd_kill=-0.05, consecutive_loss_kill=8,
        reason="owner-approved entrant", now=NOW,
    )
    pipeline.stamp_backtest(paper_conn, "donchian_v1", run_id=101)
    pipeline.stamp_oos(paper_conn, "donchian_v1", "reports/backtests/oos_v3.json")

    result = run(paper_conn)

    assert _states(paper_conn)["donchian_v1"] == "probation"
    enter = next(d for d in result["decisions"] if d["decision"] == "enter")
    assert enter["profile_name"] == "donchian_v1"
    assert "D-07/D-05 entry" in enter["rule_citation"]


def test_candidate_without_evidence_stays_queued(paper_conn, run):
    from trader.backtest.config import EXIT_PROFILE

    pipeline.register_candidate(
        paper_conn, "rsi2_v1", "rsi2_mean_reversion",
        EXIT_PROFILE(stop_pct=-0.1, tp_pct=0.2, scale_out=(), trailing_pct=None,
                     max_hold_days=None, eod_flat=False),
        pf_floor=0.9, max_dd_kill=-0.05, consecutive_loss_kill=8,
        reason="owner-approved entrant", now=NOW,
    )

    result = run(paper_conn)

    assert _states(paper_conn)["rsi2_v1"] == "candidate"
    held = next(d for d in result["decisions"] if d["profile_name"] == "rsi2_v1")
    assert "evidence incomplete" in held["rule_citation"]


# ---------------------------------------------------------------------------
# D-06: the freeze gate aborts a tampered run before any write
# ---------------------------------------------------------------------------


def test_tampered_frozen_config_aborts_run_with_no_db_write(
    paper_conn, run, monkeypatch
):
    monkeypatch.setattr(judge.freeze_gate, "FROZEN_TOURNAMENT_HASH", "0" * 64)

    with pytest.raises(RuntimeError, match="integrity check failed"):
        run(paper_conn)

    assert paper_conn.execute("SELECT COUNT(*) FROM tournament_runs").fetchone()[0] == 0
    assert (
        paper_conn.execute("SELECT COUNT(*) FROM tournament_decisions").fetchone()[0]
        == 0
    )
