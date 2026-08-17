"""Phase 7 tests: D-04 probation sizing at the entry pipeline's one correct
insertion point (07-01-PLAN.md wave 2), and the D-07 entrant state machine
(07-02-PLAN.md wave 3, added in that wave)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from trader.paper import config as paper_config
from trader.paper import config_store, entry_pipeline, ledger
from trader.risk import config as risk_config
from trader.tournament import frozen_config


from tests.test_entry_pipeline import (  # reuse the established fixture kit
    TRADING_DAY,
    _ibkr_adapter,
    _make_fake_fill,
    _patch_bars,
    _rising_bars_df,
)


def _pin_top_n(monkeypatch, value: int) -> None:
    """Pin the sizer's concurrent-position cap for one test.

    The live SIZER_TOP_N is owner-tunable (raised 3 -> 20 on 2026-08-10 for
    high-throughput paper testing). Sizing-MATH tests must keep asserting
    the arithmetic they were written for, not track that dial.
    """
    monkeypatch.setattr(risk_config, "SIZER_TOP_N", value)


def _unconstrained_budget(monkeypatch) -> None:
    """Lift the nightly dollar cap for one test.

    The owner's $600/night budget (2026-08-11) clips a single position long
    before the 25% probation multiplier can change anything -- min(50_000,
    600) and min(12_500, 600) are both $600, so probation and full would
    look identical and these tests would prove nothing. The multiplier's
    arithmetic is what they exist to pin, so they run budget-unconstrained.
    """
    monkeypatch.setattr(paper_config, "PAPER_NIGHTLY_BUDGET", 10_000_000.0)


@pytest.fixture(autouse=True)
def _mock_side_effects(monkeypatch):
    monkeypatch.setattr(entry_pipeline.alerts, "notify", MagicMock(return_value=True))
    monkeypatch.setattr(entry_pipeline.ops_log, "append_ops_log", MagicMock())


def _demote_all_to_probation(conn) -> None:
    """Test-only direct poke -- production transitions go through
    trader/tournament/pipeline.py."""
    conn.execute("UPDATE strategy_registry SET state = 'probation'")
    conn.commit()


# ---------------------------------------------------------------------------
# D-04: probation sizing (25%) -- new-order path only, never heal paths
# ---------------------------------------------------------------------------


def test_probation_config_sized_at_quarter_of_full(paper_conn, fake_ib, monkeypatch):
    """Same fixture, same candidate: a probation-state registry cuts the
    submitted qty to what a 25%-scaled dollar amount rounds down to."""
    _pin_top_n(monkeypatch, 3)
    _unconstrained_budget(monkeypatch)
    _patch_bars(monkeypatch, {"AAPL": _rising_bars_df()})
    fake_ib.placeOrder.return_value.order.permId = 555
    adapter = _ibkr_adapter(fake_ib)

    full_run = entry_pipeline.run_entry_pipeline_once(
        paper_conn, adapter, as_of_date=TRADING_DAY
    )
    full_qty = ledger.get_order_by_ref(paper_conn, full_run["submitted"][0])["qty"]

    # Fresh scenario in the same schema: wipe the first run's artifacts,
    # then demote every registry row to probation.
    paper_conn.execute("DELETE FROM paper_orders")
    paper_conn.execute("DELETE FROM paper_positions")
    paper_conn.commit()
    _demote_all_to_probation(paper_conn)

    probation_run = entry_pipeline.run_entry_pipeline_once(
        paper_conn, adapter, as_of_date=TRADING_DAY
    )
    probation_qty = ledger.get_order_by_ref(paper_conn, probation_run["submitted"][0])["qty"]

    price = 100.0 * (1.01**34)  # the fixture's last close
    dollar_full = 0.50 * paper_config.PAPER_ACCOUNT_EQUITY
    expected_probation_qty = entry_pipeline.broker_ibkr.round_shares_down(
        dollar_full * frozen_config.PROBATION_SIZE_MULTIPLIER, price
    )

    assert probation_qty == expected_probation_qty
    assert probation_qty < full_qty
    # Whole-share rounding means the ratio is <= 0.25, never above it.
    assert probation_qty * price <= dollar_full * frozen_config.PROBATION_SIZE_MULTIPLIER


def test_full_state_config_never_scaled(paper_conn, fake_ib, monkeypatch):
    _pin_top_n(monkeypatch, 3)
    _unconstrained_budget(monkeypatch)
    _patch_bars(monkeypatch, {"AAPL": _rising_bars_df()})
    fake_ib.placeOrder.return_value.order.permId = 556
    adapter = _ibkr_adapter(fake_ib)

    result = entry_pipeline.run_entry_pipeline_once(
        paper_conn, adapter, as_of_date=TRADING_DAY
    )

    order = ledger.get_order_by_ref(paper_conn, result["submitted"][0])
    price = 100.0 * (1.01**34)
    expected_qty = entry_pipeline.broker_ibkr.round_shares_down(
        0.50 * paper_config.PAPER_ACCOUNT_EQUITY, price
    )
    assert order["qty"] == expected_qty


def test_step0_heal_never_applies_probation_multiplier(paper_conn, fake_ib, monkeypatch):
    """07-RESEARCH.md Pitfall 3: a healed fill's qty is history -- the
    position must open at the orphaned order's own qty verbatim, even when
    its config is now in probation."""
    _patch_bars(monkeypatch, {})  # nothing fires today
    _demote_all_to_probation(paper_conn)

    profile = config_store.get_live_configs(paper_conn)[0].profile_name
    stale_ref = f"{profile}:MSFT:2026-07-20:buy:entry"
    ledger.record_order(
        paper_conn, stale_ref, profile, "MSFT", "ibkr_paper",
        "buy", "entry", 8, status="submitted",
    )
    fake_ib.fills.return_value = [_make_fake_fill(stale_ref, 91, "MSFT", 8)]
    adapter = _ibkr_adapter(fake_ib, latest_price=300.0)

    result = entry_pipeline.run_entry_pipeline_once(
        paper_conn, adapter, as_of_date=TRADING_DAY
    )

    assert stale_ref in result["healed"]
    positions = ledger.get_open_positions(paper_conn)
    assert len(positions) == 1
    assert positions[0]["qty"] == 8  # verbatim -- never 8 * 0.25


# ---------------------------------------------------------------------------
# D-07 state machine (wave 3): candidate -> probation -> full -> retired
# ---------------------------------------------------------------------------

from datetime import datetime, timezone  # noqa: E402

from trader.backtest.config import EXIT_PROFILE  # noqa: E402
from trader.tournament import pipeline  # noqa: E402

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)

_ENTRANT_PROFILE = EXIT_PROFILE(
    stop_pct=-0.1, tp_pct=0.2, scale_out=(), trailing_pct=None,
    max_hold_days=None, eod_flat=False,
)


def _register(conn, name: str, strategy_id: str = "donchian_breakout") -> None:
    pipeline.register_candidate(
        conn, name, strategy_id, _ENTRANT_PROFILE,
        pf_floor=0.9, max_dd_kill=-0.05, consecutive_loss_kill=8,
        reason="owner-approved entrant (Strategys/10_donchian_breakout.md)",
        now=NOW,
    )


def _stamp_all(conn, name: str) -> None:
    pipeline.stamp_backtest(conn, name, run_id=101)
    pipeline.stamp_oos(conn, name, "reports/backtests/oos_results_v3.json")


def _retire_seeds(conn, count: int) -> None:
    """Free roster slots by retiring seed incumbents (test-only poke)."""
    names = [c.profile_name for c in config_store.get_live_configs(conn)][:count]
    for name in names:
        conn.execute(
            "UPDATE strategy_registry SET state = 'retired' WHERE profile_name = ?",
            (name,),
        )
    conn.commit()


def test_register_candidate_creates_row_and_transition(paper_conn):
    _register(paper_conn, "donchian_v1")

    row = paper_conn.execute(
        "SELECT state, backtest_run_id, oos_result_ref FROM strategy_registry "
        "WHERE profile_name = 'donchian_v1'"
    ).fetchone()
    assert row == ("candidate", None, None)

    transition = paper_conn.execute(
        "SELECT from_state, to_state FROM strategy_registry_transitions "
        "WHERE profile_name = 'donchian_v1'"
    ).fetchone()
    assert transition == (None, "candidate")


def test_duplicate_registration_rejected(paper_conn):
    _register(paper_conn, "donchian_v1")
    with pytest.raises(ValueError, match="already registered"):
        _register(paper_conn, "donchian_v1")


def test_candidate_never_appears_in_live_configs(paper_conn):
    _register(paper_conn, "donchian_v1")
    names = {c.profile_name for c in config_store.get_live_configs(paper_conn)}
    assert "donchian_v1" not in names


def test_promotion_without_evidence_raises(paper_conn):
    _register(paper_conn, "donchian_v1")
    _retire_seeds(paper_conn, 1)

    with pytest.raises(pipeline.MissingEvidence, match="backtest_run_id"):
        pipeline.promote_to_probation(paper_conn, "donchian_v1", now=NOW)

    pipeline.stamp_backtest(paper_conn, "donchian_v1", run_id=101)
    with pytest.raises(pipeline.MissingEvidence, match="oos_result_ref"):
        pipeline.promote_to_probation(paper_conn, "donchian_v1", now=NOW)


def test_full_evidence_promotes_to_probation_and_goes_live(paper_conn):
    _register(paper_conn, "donchian_v1")
    _stamp_all(paper_conn, "donchian_v1")
    _retire_seeds(paper_conn, 1)

    pipeline.promote_to_probation(paper_conn, "donchian_v1", now=NOW)

    live = config_store.get_live_configs_by_profile_name(paper_conn)
    assert live["donchian_v1"].state == "probation"


def test_evidence_stamps_are_write_once(paper_conn):
    _register(paper_conn, "donchian_v1")
    pipeline.stamp_backtest(paper_conn, "donchian_v1", run_id=101)
    pipeline.stamp_backtest(paper_conn, "donchian_v1", run_id=101)  # idempotent

    with pytest.raises(ValueError, match="write-once"):
        pipeline.stamp_backtest(paper_conn, "donchian_v1", run_id=999)


def test_promote_to_full_requires_paper_30_stamp(paper_conn):
    _register(paper_conn, "donchian_v1")
    _stamp_all(paper_conn, "donchian_v1")
    _retire_seeds(paper_conn, 1)
    pipeline.promote_to_probation(paper_conn, "donchian_v1", now=NOW)

    with pytest.raises(pipeline.MissingEvidence, match="paper_30"):
        pipeline.promote_to_full(paper_conn, "donchian_v1", sharpe=1.5, now=NOW)


def test_confirm_paper_30_stamps_only_at_thirty_trades(paper_conn, paper_trade_factory):
    _register(paper_conn, "donchian_v1")
    paper_trade_factory(paper_conn, "donchian_v1", [10.0] * 29)
    assert pipeline.confirm_paper_30(paper_conn, "donchian_v1", now=NOW) is False

    paper_trade_factory(paper_conn, "donchian_v1", [10.0], start="2026-02-01")
    assert pipeline.confirm_paper_30(paper_conn, "donchian_v1", now=NOW) is True

    row = paper_conn.execute(
        "SELECT paper_30_confirmed_at FROM strategy_registry WHERE profile_name = 'donchian_v1'"
    ).fetchone()
    assert row[0] is not None


def test_full_promotion_path_end_to_end(paper_conn, paper_trade_factory):
    _register(paper_conn, "donchian_v1")
    _stamp_all(paper_conn, "donchian_v1")
    _retire_seeds(paper_conn, 1)
    pipeline.promote_to_probation(paper_conn, "donchian_v1", now=NOW)
    paper_trade_factory(paper_conn, "donchian_v1", [10.0] * 30)
    assert pipeline.confirm_paper_30(paper_conn, "donchian_v1", now=NOW) is True

    pipeline.promote_to_full(paper_conn, "donchian_v1", sharpe=0.8, now=NOW)

    assert config_store.get_live_configs_by_profile_name(paper_conn)[
        "donchian_v1"
    ].state == "full"


def test_promote_to_full_below_floor_rejected(paper_conn, paper_trade_factory):
    _register(paper_conn, "donchian_v1")
    _stamp_all(paper_conn, "donchian_v1")
    _retire_seeds(paper_conn, 1)
    pipeline.promote_to_probation(paper_conn, "donchian_v1", now=NOW)
    paper_trade_factory(paper_conn, "donchian_v1", [10.0] * 30)
    pipeline.confirm_paper_30(paper_conn, "donchian_v1", now=NOW)

    with pytest.raises(ValueError, match="promotion floor"):
        pipeline.promote_to_full(paper_conn, "donchian_v1", sharpe=-0.2, now=NOW)


def test_retire_is_terminal_and_writes_kill_state(paper_conn):
    _register(paper_conn, "donchian_v1")
    _stamp_all(paper_conn, "donchian_v1")
    _retire_seeds(paper_conn, 1)
    pipeline.promote_to_probation(paper_conn, "donchian_v1", now=NOW)

    pipeline.retire(
        paper_conn, "donchian_v1", "D-04 demotion: sustained bottom rank",
        trigger_value=-0.9, now=NOW,
    )

    assert ledger.is_strategy_retired(paper_conn, "donchian_v1") is True
    kill_row = paper_conn.execute(
        "SELECT reason FROM strategy_kill_state WHERE strategy_id = 'donchian_v1'"
    ).fetchone()
    assert kill_row[0] == "tournament_demotion"

    with pytest.raises(pipeline.TerminalState):
        pipeline.promote_to_probation(paper_conn, "donchian_v1", now=NOW)
    with pytest.raises(ValueError, match="already registered"):
        _register(paper_conn, "donchian_v1")


def test_active_cap_queues_seventh_entrant(paper_conn, monkeypatch):
    """5 seeds + 1 admitted = 6 active (the cap); the next candidate stays
    queued. The cap NUMBER is owner-tunable (raised to 20 on 2026-08-10),
    so this pins 6 locally -- what must never regress is that SOME cap is
    enforced and the overflow entrant is queued rather than lost."""
    monkeypatch.setattr(pipeline.frozen_config, "MAX_ACTIVE_STRATEGIES", 6)
    for name in ("donchian_v1", "rsi2_v1"):
        _register(paper_conn, name)
        _stamp_all(paper_conn, name)

    pipeline.promote_to_probation(paper_conn, "donchian_v1", now=NOW)
    assert pipeline.active_count(paper_conn) == 6

    with pytest.raises(pipeline.CapExceeded, match="roster is full"):
        pipeline.promote_to_probation(paper_conn, "rsi2_v1", now=NOW)
    row = paper_conn.execute(
        "SELECT state FROM strategy_registry WHERE profile_name = 'rsi2_v1'"
    ).fetchone()
    assert row[0] == "candidate"  # queued, not lost


def test_quarterly_entrant_cap(paper_conn, monkeypatch):
    """Room on the roster, but only 2 admissions per calendar quarter.
    Pinned locally for the same reason as the roster cap (owner raised the
    live number to 12) -- the invariant under test is that the quarterly
    cap binds at all, and that a new quarter resets it."""
    monkeypatch.setattr(pipeline.frozen_config, "MAX_NEW_ENTRANTS_PER_QUARTER", 2)
    _retire_seeds(paper_conn, 3)
    for name in ("donchian_v1", "rsi2_v1", "tsmom_v1"):
        _register(paper_conn, name)
        _stamp_all(paper_conn, name)

    pipeline.promote_to_probation(paper_conn, "donchian_v1", now=NOW)
    pipeline.promote_to_probation(paper_conn, "rsi2_v1", now=NOW)

    with pytest.raises(pipeline.CapExceeded, match="quarterly entrant cap"):
        pipeline.promote_to_probation(paper_conn, "tsmom_v1", now=NOW)

    # A new quarter resets the count.
    next_quarter = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    pipeline.promote_to_probation(paper_conn, "tsmom_v1", now=next_quarter)
    assert config_store.get_live_configs_by_profile_name(paper_conn)[
        "tsmom_v1"
    ].state == "probation"


def test_every_transition_appends_audit_row(paper_conn, paper_trade_factory):
    _register(paper_conn, "donchian_v1")
    _stamp_all(paper_conn, "donchian_v1")
    _retire_seeds(paper_conn, 1)
    pipeline.promote_to_probation(paper_conn, "donchian_v1", now=NOW)
    paper_trade_factory(paper_conn, "donchian_v1", [10.0] * 30)
    pipeline.confirm_paper_30(paper_conn, "donchian_v1", now=NOW)
    pipeline.promote_to_full(paper_conn, "donchian_v1", sharpe=0.8, now=NOW)
    pipeline.retire(paper_conn, "donchian_v1", "kill trip", -0.9, now=NOW)

    rows = paper_conn.execute(
        "SELECT from_state, to_state FROM strategy_registry_transitions "
        "WHERE profile_name = 'donchian_v1' ORDER BY transition_id"
    ).fetchall()
    assert rows == [
        (None, "candidate"),
        ("candidate", "probation"),
        ("probation", "full"),
        ("full", "retired"),
    ]
