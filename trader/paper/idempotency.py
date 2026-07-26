"""D-06's idempotency key builder plus the pure existing-order/unresolved-
order matchers (05-01-PLAN.md).

Every function in this module is pure -- zero I/O, zero sqlite3 import. The
caller (trader.paper.ledger, entry_pipeline, guardian) fetches
local_orders/broker_fills first and passes them in.

Two matchers, two different jobs:

- find_existing_order: the fast same-day/same-tick path. Given the order_ref
  the caller just computed for TODAY's candidate, has this exact order
  already been recorded (locally or at the broker)?

- find_unresolved_match: the crash-recovery path (plan-checker BLOCKER 1).
  Given a list of local orders that are still unresolved (status
  'pending_submit' or 'submitted', fetched via
  trader.paper.ledger.get_unresolved_orders or get_all_unresolved_orders),
  has any ONE of THEM (by its own order_ref, which may carry yesterday's
  date, or belong to a symbol not even in today's candidate list) since
  shown up in a broker fill? This function does not care whether its input
  list came from the scoped or unscoped ledger query -- both share this one
  matcher.
"""

from __future__ import annotations


def build_order_ref(
    strategy_id: str, symbol: str, trade_date: str, side: str, intent: str
) -> str:
    """A deterministic idempotency key: identical for the same
    (strategy_id, symbol, trade_date, side, intent) tuple every call, and
    never collides across different tuples (D-06)."""
    return f"{strategy_id}:{symbol}:{trade_date}:{side}:{intent}"


def find_existing_order(
    order_ref: str, local_orders: dict[str, dict], broker_fills: list[dict]
) -> dict | None:
    """Fast same-day/same-tick lookup for a freshly-computed order_ref.

    Checks local_orders (a caller-supplied {order_ref: row} map) first; if
    absent, scans broker_fills for a dict whose "orderRef" key equals
    order_ref. Returns None if neither has it.
    """
    if order_ref in local_orders:
        return local_orders[order_ref]
    for fill in broker_fills:
        if fill.get("orderRef") == order_ref:
            return fill
    return None


def find_unresolved_match(
    unresolved_local_orders: list[dict], broker_fills: list[dict]
) -> dict | None:
    """The date-independent crash-recovery matcher (BLOCKER 1).

    For each local order in unresolved_local_orders (oldest first), scans
    broker_fills for a fill whose "orderRef" equals THAT local order's own
    "order_ref" -- never a freshly-computed "today" order_ref. Returns the
    first match as {"local_order": ..., "broker_fill": ...}, or None if no
    unresolved local order has a matching broker fill yet (still genuinely
    in flight, not a crash-orphan).
    """
    for local_order in unresolved_local_orders:
        own_ref = local_order["order_ref"]
        for fill in broker_fills:
            if fill.get("orderRef") == own_ref:
                return {"local_order": local_order, "broker_fill": fill}
    return None
