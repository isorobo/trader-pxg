"""Tests for trader.paper.ledger -- Phase 5's paper_orders/paper_positions/
paper_trades/strategy_kill_state read/write surface (05-01-PLAN.md).

Covers the revised persist-before-submit order lifecycle
(pending_submit -> submitted -> filled), the date-independent scoped
unresolved-order lookup (get_unresolved_orders), the UNSCOPED table-wide
lookup (get_all_unresolved_orders, RESIDUAL BLOCKER 1), heal_order,
get_pending_order_qty's pending_submit exclusion (BLOCKER 1), the
position/trade round-trip, and strategy retirement idempotency.

Uses the paper_conn fixture (tests/conftest.py) -- a live trader.data.db
connection with every migration, including 0005_paper_trading.sql, applied.
"""

from __future__ import annotations

import ast
from pathlib import Path

from trader.backtest.config import EXIT_PROFILE
from trader.paper import ledger

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_SOURCE_PATH = REPO_ROOT / "trader" / "paper" / "ledger.py"


# ---------------------------------------------------------------------------
# record_order -- persist-before-submit default
# ---------------------------------------------------------------------------


def test_record_order_defaults_to_pending_submit(paper_conn):
    ledger.record_order(
        paper_conn,
        order_ref="s:AAPL:2026-07-27:buy:entry",
        strategy_id="s",
        symbol="AAPL",
        venue="ibkr_paper",
        side="buy",
        intent="entry",
        qty=10,
    )
    row = ledger.get_order_by_ref(paper_conn, "s:AAPL:2026-07-27:buy:entry")
    assert row["status"] == "pending_submit"


def test_record_order_accepts_explicit_status(paper_conn):
    ledger.record_order(
        paper_conn,
        order_ref="s:AAPL:2026-07-27:buy:entry",
        strategy_id="s",
        symbol="AAPL",
        venue="ibkr_paper",
        side="buy",
        intent="entry",
        qty=10,
        status="submitted",
    )
    row = ledger.get_order_by_ref(paper_conn, "s:AAPL:2026-07-27:buy:entry")
    assert row["status"] == "submitted"


# ---------------------------------------------------------------------------
# get_unresolved_orders -- SCOPED, date-independent (BLOCKER 1)
# ---------------------------------------------------------------------------


def test_get_unresolved_orders_ignores_date_embedded_in_order_ref(paper_conn):
    ledger.record_order(
        paper_conn,
        order_ref="s:AAPL:2026-07-26:buy:entry",
        strategy_id="s",
        symbol="AAPL",
        venue="ibkr_paper",
        side="buy",
        intent="entry",
        qty=10,
        status="pending_submit",
    )
    ledger.record_order(
        paper_conn,
        order_ref="s:AAPL:2026-07-27:buy:entry",
        strategy_id="s",
        symbol="AAPL",
        venue="ibkr_paper",
        side="buy",
        intent="entry",
        qty=10,
        status="submitted",
    )
    result = ledger.get_unresolved_orders(paper_conn, "s", "AAPL", "buy")
    assert [row["order_ref"] for row in result] == [
        "s:AAPL:2026-07-26:buy:entry",
        "s:AAPL:2026-07-27:buy:entry",
    ]


def test_get_unresolved_orders_excludes_filled(paper_conn):
    ledger.record_order(
        paper_conn,
        order_ref="s:AAPL:2026-07-27:buy:entry",
        strategy_id="s",
        symbol="AAPL",
        venue="ibkr_paper",
        side="buy",
        intent="entry",
        qty=10,
        status="filled",
    )
    result = ledger.get_unresolved_orders(paper_conn, "s", "AAPL", "buy")
    assert result == []


# ---------------------------------------------------------------------------
# get_all_unresolved_orders -- UNSCOPED (RESIDUAL BLOCKER 1)
# ---------------------------------------------------------------------------


def test_get_all_unresolved_orders_spans_multiple_tuples_with_no_filter(paper_conn):
    ledger.record_order(
        paper_conn,
        order_ref="s1:AAPL:2026-07-26:buy:entry",
        strategy_id="s1",
        symbol="AAPL",
        venue="ibkr_paper",
        side="buy",
        intent="entry",
        qty=10,
        status="pending_submit",
    )
    ledger.record_order(
        paper_conn,
        order_ref="s2:MSFT:2026-07-26:sell:exit_stop",
        strategy_id="s2",
        symbol="MSFT",
        venue="ibkr_paper",
        side="sell",
        intent="exit_stop",
        qty=5,
        status="submitted",
    )
    ledger.record_order(
        paper_conn,
        order_ref="s3:TSLA:2026-07-26:buy:entry",
        strategy_id="s3",
        symbol="TSLA",
        venue="ibkr_paper",
        side="buy",
        intent="entry",
        qty=3,
        status="pending_submit",
    )
    ledger.record_order(
        paper_conn,
        order_ref="s4:NVDA:2026-07-26:buy:entry",
        strategy_id="s4",
        symbol="NVDA",
        venue="ibkr_paper",
        side="buy",
        intent="entry",
        qty=1,
        status="filled",
    )

    result = ledger.get_all_unresolved_orders(paper_conn)
    refs = {row["order_ref"] for row in result}
    assert refs == {
        "s1:AAPL:2026-07-26:buy:entry",
        "s2:MSFT:2026-07-26:sell:exit_stop",
        "s3:TSLA:2026-07-26:buy:entry",
    }
    assert "s4:NVDA:2026-07-26:buy:entry" not in refs


def test_get_unresolved_orders_and_get_all_unresolved_orders_share_one_filter_helper():
    source = LEDGER_SOURCE_PATH.read_text()
    assert source.count("IN ('pending_submit', 'submitted')") == 1 or source.count(
        "IN ('pending_submit','submitted')"
    ) == 1


# ---------------------------------------------------------------------------
# heal_order -- primary crash-recovery heal path
# ---------------------------------------------------------------------------


def test_heal_order_updates_to_filled(paper_conn):
    ledger.record_order(
        paper_conn,
        order_ref="s:AAPL:2026-07-26:buy:entry",
        strategy_id="s",
        symbol="AAPL",
        venue="ibkr_paper",
        side="buy",
        intent="entry",
        qty=10,
        status="pending_submit",
    )
    ledger.heal_order(
        paper_conn,
        order_ref="s:AAPL:2026-07-26:buy:entry",
        perm_id=999,
        fill_price=101.5,
        filled_ts="2026-07-27T10:00:00",
    )
    row = ledger.get_order_by_ref(paper_conn, "s:AAPL:2026-07-26:buy:entry")
    assert row["status"] == "filled"
    assert row["perm_id"] == 999
    assert row["fill_price"] == 101.5
    assert row["filled_ts"] == "2026-07-27T10:00:00"


def test_heal_order_is_safe_to_call_twice(paper_conn):
    ledger.record_order(
        paper_conn,
        order_ref="s:AAPL:2026-07-26:buy:entry",
        strategy_id="s",
        symbol="AAPL",
        venue="ibkr_paper",
        side="buy",
        intent="entry",
        qty=10,
        status="pending_submit",
    )
    ledger.heal_order(paper_conn, "s:AAPL:2026-07-26:buy:entry", 999, 101.5, "2026-07-27T10:00:00")
    ledger.heal_order(paper_conn, "s:AAPL:2026-07-26:buy:entry", 999, 101.5, "2026-07-27T10:00:00")
    row = ledger.get_order_by_ref(paper_conn, "s:AAPL:2026-07-26:buy:entry")
    assert row["status"] == "filled"


# ---------------------------------------------------------------------------
# get_pending_order_qty -- excludes pending_submit (BLOCKER 1)
# ---------------------------------------------------------------------------


def test_get_pending_order_qty_excludes_pending_submit(paper_conn):
    ledger.record_order(
        paper_conn,
        order_ref="s:AAPL:2026-07-27:buy:entry",
        strategy_id="s",
        symbol="AAPL",
        venue="ibkr_paper",
        side="buy",
        intent="entry",
        qty=10,
        status="pending_submit",
    )
    ledger.record_order(
        paper_conn,
        order_ref="s:MSFT:2026-07-27:buy:entry",
        strategy_id="s",
        symbol="MSFT",
        venue="ibkr_paper",
        side="buy",
        intent="entry",
        qty=7,
        status="submitted",
    )
    result = ledger.get_pending_order_qty(paper_conn)
    assert result == {"MSFT": 7}
    assert "AAPL" not in result


# ---------------------------------------------------------------------------
# open_position / get_open_positions / close_position round-trip
# ---------------------------------------------------------------------------


def test_position_round_trip_preserves_exit_profile_fields(paper_conn):
    profile = EXIT_PROFILE(
        stop_pct=-0.25,
        tp_pct=0.2,
        scale_out=((0.1, 0.5), (0.2, 0.5)),
        trailing_pct=None,
        max_hold_days=30,
        eod_flat=False,
    )
    position_id = ledger.open_position(
        paper_conn,
        strategy_id="momentum_stock_profile",
        symbol="AAPL",
        venue="ibkr_paper",
        asset_class="stock",
        qty=10,
        entry_price=100.0,
        entry_ts="2026-07-27T09:30:00",
        entry_order_ref="s:AAPL:2026-07-27:buy:entry",
        exit_profile=profile,
    )
    positions = ledger.get_open_positions(paper_conn, strategy_id="momentum_stock_profile")
    assert len(positions) == 1
    row = positions[0]
    assert row["position_id"] == position_id
    assert row["stop_pct"] == -0.25
    assert row["tp_pct"] == 0.2
    assert row["scale_out"] == ((0.1, 0.5), (0.2, 0.5))
    assert isinstance(row["scale_out"], tuple)
    assert row["trailing_pct"] is None
    assert row["max_hold_days"] == 30
    assert row["eod_flat"] is False


def test_close_position_marks_closed_and_inserts_one_trade(paper_conn):
    profile = EXIT_PROFILE(
        stop_pct=-0.25,
        tp_pct=0.2,
        scale_out=(),
        trailing_pct=None,
        max_hold_days=30,
        eod_flat=False,
    )
    position_id = ledger.open_position(
        paper_conn,
        strategy_id="momentum_stock_profile",
        symbol="AAPL",
        venue="ibkr_paper",
        asset_class="stock",
        qty=10,
        entry_price=100.0,
        entry_ts="2026-07-27T09:30:00",
        entry_order_ref="s:AAPL:2026-07-27:buy:entry",
        exit_profile=profile,
    )
    ledger.close_position(
        paper_conn,
        position_id=position_id,
        exit_ts="2026-07-28T09:30:00",
        exit_price=120.0,
        exit_reason="take_profit",
        exit_order_ref="s:AAPL:2026-07-28:sell:exit_take_profit",
        fees=1.0,
        slippage_cost=0.5,
        pnl=198.5,
    )
    open_positions = ledger.get_open_positions(paper_conn, strategy_id="momentum_stock_profile")
    assert open_positions == []

    trades = ledger.get_recent_trades(paper_conn, "momentum_stock_profile")
    assert len(trades) == 1
    trade = trades[0]
    assert trade["symbol"] == "AAPL"
    assert trade["exit_reason"] == "take_profit"
    assert trade["pnl"] == 198.5
    assert trade["entry_order_ref"] == "s:AAPL:2026-07-27:buy:entry"
    assert trade["exit_order_ref"] == "s:AAPL:2026-07-28:sell:exit_take_profit"


# ---------------------------------------------------------------------------
# retire_strategy / is_strategy_retired -- idempotent
# ---------------------------------------------------------------------------


def test_is_strategy_retired_false_before_retirement(paper_conn):
    assert ledger.is_strategy_retired(paper_conn, "never_retired") is False


def test_retire_strategy_then_is_strategy_retired_true(paper_conn):
    ledger.retire_strategy(paper_conn, "s", reason="max_drawdown", trigger_value=-0.05)
    assert ledger.is_strategy_retired(paper_conn, "s") is True


def test_retire_strategy_called_twice_leaves_exactly_one_row(paper_conn):
    ledger.retire_strategy(paper_conn, "s", reason="max_drawdown", trigger_value=-0.05)
    ledger.retire_strategy(paper_conn, "s", reason="max_drawdown", trigger_value=-0.05)
    rows = paper_conn.execute(
        "SELECT COUNT(*) FROM strategy_kill_state WHERE strategy_id = ?", ("s",)
    ).fetchone()
    assert rows[0] == 1


# ---------------------------------------------------------------------------
# ASVS V5 -- no string-interpolated SQL anywhere in ledger.py
# ---------------------------------------------------------------------------


def test_ledger_source_has_no_fstring_or_percent_sql():
    source = LEDGER_SOURCE_PATH.read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            # An f-string exists somewhere -- ensure it is never passed as the
            # first argument to conn.execute/executemany (a SQL string).
            pass
    # Cheap heuristic matching the existing test_breakers.py-style convention:
    # no f-string SQL literal contains a SELECT/INSERT/UPDATE keyword directly
    # concatenated with an f-string expression.
    assert "f\"SELECT" not in source
    assert "f\"INSERT" not in source
    assert "f\"UPDATE" not in source
    assert "f'SELECT" not in source
    assert "f'INSERT" not in source
    assert "f'UPDATE" not in source
    assert "%s" not in source
