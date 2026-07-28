"""Wave 1 tests: migration 0006's seeded strategy_registry + the DB-backed
config loader (07-01-PLAN.md, D-08)."""

import pytest

from trader.paper import config, config_store, ledger


def _set_state(conn, profile_name: str, state: str) -> None:
    """Test-only direct state poke -- production code goes through
    trader/tournament/pipeline.py's transition function."""
    conn.execute(
        "UPDATE strategy_registry SET state = ? WHERE profile_name = ?",
        (state, profile_name),
    )
    conn.commit()


def test_seeded_registry_matches_frozen_config_tuple(paper_conn):
    """The 0006 seed reproduces config.LIVE_STRATEGY_CONFIGS exactly --
    the load-bearing claim that swapping the data source changes nothing
    (07-RESEARCH.md A5)."""
    loaded = config_store.get_live_configs(paper_conn)
    expected = tuple(sorted(config.LIVE_STRATEGY_CONFIGS, key=lambda c: c.profile_name))
    assert loaded == expected


def test_all_seeded_rows_are_full_state(paper_conn):
    for cfg in config_store.get_live_configs(paper_conn):
        assert cfg.state == "full"


def test_retired_rows_excluded(paper_conn):
    victim = config.LIVE_STRATEGY_CONFIGS[0].profile_name
    _set_state(paper_conn, victim, "retired")

    names = {cfg.profile_name for cfg in config_store.get_live_configs(paper_conn)}

    assert victim not in names
    assert len(names) == len(config.LIVE_STRATEGY_CONFIGS) - 1


def test_candidate_rows_excluded_probation_included(paper_conn):
    paper_conn.execute(
        """
        INSERT INTO strategy_registry
            (profile_name, strategy_id, stop_pct, tp_pct, pf_floor,
             max_dd_kill, consecutive_loss_kill, state)
        VALUES ('cand_x', 'donchian', -0.1, 0.2, 0.9, -0.05, 8, 'candidate'),
               ('prob_x', 'donchian', -0.1, 0.2, 0.9, -0.05, 8, 'probation')
        """
    )
    paper_conn.commit()

    by_name = config_store.get_live_configs_by_profile_name(paper_conn)

    assert "cand_x" not in by_name
    assert "prob_x" in by_name
    assert by_name["prob_x"].state == "probation"


def test_get_registry_rows_returns_all_states(paper_conn):
    victim = config.LIVE_STRATEGY_CONFIGS[0].profile_name
    _set_state(paper_conn, victim, "retired")

    rows = config_store.get_registry_rows(paper_conn)

    states = {row["profile_name"]: row["state"] for row in rows}
    assert states[victim] == "retired"
    assert len(rows) == len(config.LIVE_STRATEGY_CONFIGS)


def test_exit_profile_rebuilt_correctly(paper_conn):
    """Every reconstructed EXIT_PROFILE field survives the DB round trip,
    including NULL stop/hold and the tuple-typed scale_out."""
    by_name = config_store.get_live_configs_by_profile_name(paper_conn)
    for cfg in config.LIVE_STRATEGY_CONFIGS:
        assert by_name[cfg.profile_name].exit_profile == cfg.exit_profile


def test_kill_state_accepts_tournament_demotion_reason(paper_conn):
    """07-RESEARCH.md Pitfall 2 regression: the rebuilt strategy_kill_state
    CHECK must accept the tournament's retire reason without
    IntegrityError."""
    ledger.retire_strategy(paper_conn, "some_profile", "tournament_demotion", -0.5)
    assert ledger.is_strategy_retired(paper_conn, "some_profile") is True


def test_kill_state_still_accepts_original_reasons(paper_conn):
    for reason in ("profit_factor_floor", "max_drawdown", "consecutive_losses"):
        ledger.retire_strategy(paper_conn, f"p_{reason}", reason, 0.0)
        assert ledger.is_strategy_retired(paper_conn, f"p_{reason}") is True


def test_kill_state_rejects_unknown_reason(paper_conn):
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        paper_conn.execute(
            "INSERT INTO strategy_kill_state (strategy_id, reason) VALUES ('x', 'vibes')"
        )


def test_seed_transitions_logged(paper_conn):
    """Standing rule 4: even the seed states are re-derivable from the
    transition log."""
    rows = paper_conn.execute(
        "SELECT profile_name, from_state, to_state FROM strategy_registry_transitions"
    ).fetchall()
    assert len(rows) == len(config.LIVE_STRATEGY_CONFIGS)
    for _profile, from_state, to_state in rows:
        assert from_state is None
        assert to_state == "full"
