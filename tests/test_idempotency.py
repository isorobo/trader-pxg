"""Tests for trader.paper.idempotency -- the D-06 idempotency key builder
and the pure existing-order/unresolved-order matchers (05-01-PLAN.md).

build_order_ref and find_existing_order cover the fast same-day/same-tick
path. find_unresolved_match covers the crash-recovery path (plan-checker
BLOCKER 1): matching is keyed on the unresolved local order's OWN order_ref,
never a freshly-computed "today" order_ref, so a crash-orphaned order from
yesterday -- or for a symbol not even under consideration today -- is still
found.
"""

from __future__ import annotations

from trader.paper import idempotency


# ---------------------------------------------------------------------------
# build_order_ref
# ---------------------------------------------------------------------------


def test_build_order_ref_is_deterministic():
    ref1 = idempotency.build_order_ref(
        "momentum_stock_..._holdNone", "AAPL", "2026-07-27", "buy", "entry"
    )
    ref2 = idempotency.build_order_ref(
        "momentum_stock_..._holdNone", "AAPL", "2026-07-27", "buy", "entry"
    )
    assert ref1 == ref2


def test_build_order_ref_differs_by_symbol():
    ref1 = idempotency.build_order_ref(
        "momentum_stock_..._holdNone", "AAPL", "2026-07-27", "buy", "entry"
    )
    ref2 = idempotency.build_order_ref(
        "momentum_stock_..._holdNone", "MSFT", "2026-07-27", "buy", "entry"
    )
    assert ref1 != ref2


def test_build_order_ref_differs_by_date():
    ref1 = idempotency.build_order_ref(
        "momentum_stock_..._holdNone", "AAPL", "2026-07-27", "buy", "entry"
    )
    ref2 = idempotency.build_order_ref(
        "momentum_stock_..._holdNone", "AAPL", "2026-07-28", "buy", "entry"
    )
    assert ref1 != ref2


# ---------------------------------------------------------------------------
# find_existing_order -- fast same-day/same-tick path
# ---------------------------------------------------------------------------


def test_find_existing_order_returns_none_when_nothing_matches():
    order_ref = "s:AAPL:2026-07-27:buy:entry"
    result = idempotency.find_existing_order(order_ref, local_orders={}, broker_fills=[])
    assert result is None


def test_find_existing_order_prefers_local_orders_over_broker_fills():
    order_ref = "s:AAPL:2026-07-27:buy:entry"
    local_row = {"order_ref": order_ref, "status": "submitted"}
    result = idempotency.find_existing_order(
        order_ref,
        local_orders={order_ref: local_row},
        broker_fills=[{"orderRef": order_ref, "execId": "should-not-be-returned"}],
    )
    assert result is local_row


def test_find_existing_order_falls_back_to_broker_fills():
    order_ref = "s:AAPL:2026-07-27:buy:entry"
    fill = {"orderRef": order_ref, "execId": "x"}
    result = idempotency.find_existing_order(
        order_ref, local_orders={}, broker_fills=[fill]
    )
    assert result is fill


# ---------------------------------------------------------------------------
# find_unresolved_match -- crash-recovery path (BLOCKER 1)
# ---------------------------------------------------------------------------


def test_find_unresolved_match_matches_by_local_orders_own_ref_not_todays_ref():
    unresolved_local_orders = [{"order_ref": "yesterday-ref", "status": "pending_submit"}]
    broker_fills = [{"orderRef": "yesterday-ref", "execId": "y"}]
    result = idempotency.find_unresolved_match(unresolved_local_orders, broker_fills)
    assert result == {
        "local_order": unresolved_local_orders[0],
        "broker_fill": broker_fills[0],
    }


def test_find_unresolved_match_returns_none_when_still_genuinely_pending():
    unresolved_local_orders = [{"order_ref": "x", "status": "submitted"}]
    result = idempotency.find_unresolved_match(unresolved_local_orders, broker_fills=[])
    assert result is None


def test_find_unresolved_match_scans_oldest_first_and_skips_non_matches():
    unresolved_local_orders = [
        {"order_ref": "orphan-1", "status": "pending_submit"},
        {"order_ref": "orphan-2", "status": "submitted"},
    ]
    broker_fills = [{"orderRef": "orphan-2", "execId": "z"}]
    result = idempotency.find_unresolved_match(unresolved_local_orders, broker_fills)
    assert result["local_order"]["order_ref"] == "orphan-2"
    assert result["broker_fill"] is broker_fills[0]
