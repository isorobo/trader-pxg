"""Phase 7 tests: D-04 probation sizing at the entry pipeline's one correct
insertion point (07-01-PLAN.md wave 2), and the D-07 entrant state machine
(07-02-PLAN.md wave 3, added in that wave)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from trader.paper import config as paper_config
from trader.paper import config_store, entry_pipeline, ledger
from trader.tournament import frozen_config

from tests.test_entry_pipeline import (  # reuse the established fixture kit
    TRADING_DAY,
    _ibkr_adapter,
    _make_fake_fill,
    _patch_bars,
    _rising_bars_df,
)


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
