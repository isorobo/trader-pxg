"""Phase 5's paper_orders/paper_positions/paper_trades/strategy_kill_state
read/write surface (05-01-PLAN.md) -- every function is parameterized SQL
only (ASVS V5, T-05-01), mirroring trader/data/db.py's
upsert_instrument/trader/risk/breakers.py's append_breaker_event pattern.

REVISED order lifecycle (plan-checker BLOCKER 1, crash-recovery hardening):
paper_orders.status has three meaningful states, in this order:
  'pending_submit' -- the caller (entry_pipeline/guardian) has DECIDED to
      submit this order_ref and persisted it locally BEFORE calling the
      broker (record_order's default). If the process crashes here, the
      broker may or may not have actually received the order.
  'submitted' -- the caller's broker call returned successfully and the
      broker acknowledged the order_ref (update_order_status). This is the
      ONLY status get_pending_order_qty counts as an "explainable pending"
      quantity -- a 'pending_submit' row is a weaker signal and must not
      pre-excuse an unexplained broker-side position via reconciliation.
  'filled' -- the broker confirmed a fill, whether discovered same-tick
      (update_order_status) or healed later via get_unresolved_orders /
      get_all_unresolved_orders + idempotency.find_unresolved_match
      (heal_order, the crash-recovery path).

get_unresolved_orders (SCOPED by strategy_id/symbol/side) and
get_all_unresolved_orders (UNSCOPED, RESIDUAL BLOCKER 1 -- the mandatory
STEP 0 standalone heal pass 05-06 runs before it even knows today's
candidates) share ONE private status-filter helper
(_UNRESOLVED_STATUS_FILTER) so the two queries can never silently drift
apart.
"""

from __future__ import annotations

import json
import sqlite3

# Shared by get_unresolved_orders and get_all_unresolved_orders -- defined
# exactly once so the two queries cannot silently drift apart.
_UNRESOLVED_STATUS_FILTER = "status IN ('pending_submit', 'submitted')"


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def record_order(
    conn: sqlite3.Connection,
    order_ref: str,
    strategy_id: str,
    symbol: str,
    venue: str,
    side: str,
    intent: str,
    qty: float,
    perm_id: int | None = None,
    status: str = "pending_submit",
) -> None:
    """Persist a decided order BEFORE any broker call (BLOCKER 1 -- callers
    call this first, then update_order_status once the broker call itself
    succeeds)."""
    conn.execute(
        """
        INSERT INTO paper_orders
            (order_ref, strategy_id, symbol, venue, side, intent, qty, perm_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (order_ref, strategy_id, symbol, venue, side, intent, qty, perm_id, status),
    )
    conn.commit()


def record_from_live_fill(
    conn: sqlite3.Connection,
    order_ref: str,
    strategy_id: str,
    symbol: str,
    venue: str,
    side: str,
    intent: str,
    qty: float,
    perm_id: int | None,
    fill_price: float,
    filled_ts: str,
) -> None:
    """Fallback path for the rare case where NO local row exists at all
    (e.g. the local DB itself was unavailable at decision time). The
    PRIMARY heal path for an existing 'pending_submit'/'submitted' row is
    heal_order, not this function."""
    conn.execute(
        """
        INSERT OR IGNORE INTO paper_orders
            (order_ref, strategy_id, symbol, venue, side, intent, qty, perm_id,
             status, filled_ts, fill_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'filled', ?, ?)
        """,
        (order_ref, strategy_id, symbol, venue, side, intent, qty, perm_id, filled_ts, fill_price),
    )
    conn.commit()


def heal_order(
    conn: sqlite3.Connection,
    order_ref: str,
    perm_id: int | None,
    fill_price: float,
    filled_ts: str,
) -> None:
    """The primary crash-recovery heal path (BLOCKER 1): update an existing
    'pending_submit'/'submitted' row to 'filled' once
    idempotency.find_unresolved_match has found its matching broker fill.
    A no-op-safe UPDATE -- never raises if called twice."""
    conn.execute(
        """
        UPDATE paper_orders
        SET status = 'filled', perm_id = ?, fill_price = ?, filled_ts = ?
        WHERE order_ref = ?
        """,
        (perm_id, fill_price, filled_ts, order_ref),
    )
    conn.commit()


def update_order_status(
    conn: sqlite3.Connection,
    order_ref: str,
    status: str,
    filled_ts: str | None = None,
    fill_price: float | None = None,
    perm_id: int | None = None,
) -> None:
    """Advance an order's status (e.g. pending_submit -> submitted, or
    submitted -> filled on the normal same-tick path). Any of
    filled_ts/fill_price/perm_id left as None preserves the existing
    stored value rather than overwriting it with NULL."""
    conn.execute(
        """
        UPDATE paper_orders
        SET status = ?,
            filled_ts = COALESCE(?, filled_ts),
            fill_price = COALESCE(?, fill_price),
            perm_id = COALESCE(?, perm_id)
        WHERE order_ref = ?
        """,
        (status, filled_ts, fill_price, perm_id, order_ref),
    )
    conn.commit()


def get_order_by_ref(conn: sqlite3.Connection, order_ref: str) -> dict | None:
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    row = cursor.execute(
        "SELECT * FROM paper_orders WHERE order_ref = ?", (order_ref,)
    ).fetchone()
    return _row_to_dict(row) if row is not None else None


def get_unresolved_orders(
    conn: sqlite3.Connection, strategy_id: str, symbol: str, side: str
) -> list[dict]:
    """SCOPED (by strategy_id/symbol/side) unresolved-order lookup -- the
    fast, per-candidate check. Explicitly NEVER filters by the date embedded
    in order_ref (BLOCKER 1): a crash-orphaned order from yesterday is found
    by today's run."""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    rows = cursor.execute(
        f"""
        SELECT * FROM paper_orders
        WHERE strategy_id = ? AND symbol = ? AND side = ? AND {_UNRESOLVED_STATUS_FILTER}
        ORDER BY submitted_ts ASC
        """,
        (strategy_id, symbol, side),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_all_unresolved_orders(conn: sqlite3.Connection) -> list[dict]:
    """UNSCOPED unresolved-order lookup -- NO strategy_id/symbol/side filter
    at all (RESIDUAL BLOCKER 1). The standalone STEP 0 heal pass (05-06)
    uses this to catch an orphan whose own symbol never re-fires a fresh
    signal, which the scoped get_unresolved_orders alone could never reach.
    Shares _UNRESOLVED_STATUS_FILTER with get_unresolved_orders so the two
    queries cannot silently drift apart."""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    rows = cursor.execute(
        f"""
        SELECT * FROM paper_orders
        WHERE {_UNRESOLVED_STATUS_FILTER}
        ORDER BY submitted_ts ASC
        """
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_pending_order_qty(conn: sqlite3.Connection) -> dict[str, float]:
    """Sums qty grouped by symbol for status='submitted' rows ONLY --
    deliberately excludes 'pending_submit' (BLOCKER 1): a decision that was
    persisted locally but never confirmed sent to the broker must not
    silently pre-excuse a broker-side position via reconciliation."""
    cursor = conn.cursor()
    rows = cursor.execute(
        """
        SELECT symbol, SUM(qty) AS total_qty
        FROM paper_orders
        WHERE status = 'submitted' AND venue = 'ibkr_paper'
        GROUP BY symbol
        """
    ).fetchall()
    return {symbol: total_qty for symbol, total_qty in rows}


def open_position(
    conn: sqlite3.Connection,
    strategy_id: str,
    symbol: str,
    venue: str,
    asset_class: str,
    qty: float,
    entry_price: float,
    entry_ts: str,
    entry_order_ref: str,
    exit_profile,
) -> int:
    """Insert a new open position, serializing the locked EXIT_PROFILE
    (standing rule 2) so the guardian can rebuild it later without ever
    re-deriving it from anywhere else."""
    cursor = conn.execute(
        """
        INSERT INTO paper_positions
            (strategy_id, symbol, venue, asset_class, qty, entry_price, entry_ts,
             entry_order_ref, stop_pct, tp_pct, scale_out_json, trailing_pct,
             max_hold_days, eod_flat)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            strategy_id,
            symbol,
            venue,
            asset_class,
            qty,
            entry_price,
            entry_ts,
            entry_order_ref,
            exit_profile.stop_pct,
            exit_profile.tp_pct,
            json.dumps(list(exit_profile.scale_out)),
            exit_profile.trailing_pct,
            exit_profile.max_hold_days,
            int(exit_profile.eod_flat),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_open_positions(conn: sqlite3.Connection, strategy_id: str | None = None) -> list[dict]:
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    if strategy_id is None:
        rows = cursor.execute(
            "SELECT * FROM paper_positions WHERE status = 'open'"
        ).fetchall()
    else:
        rows = cursor.execute(
            "SELECT * FROM paper_positions WHERE status = 'open' AND strategy_id = ?",
            (strategy_id,),
        ).fetchall()

    positions = []
    for row in rows:
        position = _row_to_dict(row)
        position["scale_out"] = tuple(
            tuple(pair) for pair in json.loads(position["scale_out_json"])
        )
        position["eod_flat"] = bool(position["eod_flat"])
        positions.append(position)
    return positions


def close_position(
    conn: sqlite3.Connection,
    position_id: int,
    exit_ts: str,
    exit_price: float,
    exit_reason: str,
    exit_order_ref: str,
    fees: float,
    slippage_cost: float,
    pnl: float,
) -> None:
    """Marks the position 'closed', then inserts exactly one paper_trades
    row -- reading strategy_id/symbol/venue/asset_class/entry_ts/
    entry_price/qty off the paper_positions row itself so the caller never
    re-passes duplicate data."""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    position = cursor.execute(
        "SELECT * FROM paper_positions WHERE position_id = ?", (position_id,)
    ).fetchone()
    if position is None:
        raise ValueError(f"No paper_positions row for position_id={position_id}")

    conn.execute(
        "UPDATE paper_positions SET status = 'closed' WHERE position_id = ?",
        (position_id,),
    )
    conn.execute(
        """
        INSERT INTO paper_trades
            (strategy_id, profile_name, symbol, venue, asset_class, entry_ts,
             entry_price, exit_ts, exit_price, exit_reason, qty, fees,
             slippage_cost, pnl, entry_order_ref, exit_order_ref)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            position["strategy_id"],
            position["strategy_id"],
            position["symbol"],
            position["venue"],
            position["asset_class"],
            position["entry_ts"],
            position["entry_price"],
            exit_ts,
            exit_price,
            exit_reason,
            position["qty"],
            fees,
            slippage_cost,
            pnl,
            position["entry_order_ref"],
            exit_order_ref,
        ),
    )
    conn.commit()


def update_watermark(conn: sqlite3.Connection, position_id: int, watermark: float) -> None:
    conn.execute(
        "UPDATE paper_positions SET watermark = ? WHERE position_id = ?",
        (watermark, position_id),
    )
    conn.commit()


def get_recent_trades(conn: sqlite3.Connection, strategy_id: str, limit: int = 30) -> list[dict]:
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    rows = cursor.execute(
        """
        SELECT * FROM paper_trades
        WHERE strategy_id = ?
        ORDER BY exit_ts DESC
        LIMIT ?
        """,
        (strategy_id, limit),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def is_strategy_retired(conn: sqlite3.Connection, strategy_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM strategy_kill_state WHERE strategy_id = ?", (strategy_id,)
    ).fetchone()
    return row is not None


def retire_strategy(
    conn: sqlite3.Connection, strategy_id: str, reason: str, trigger_value: float | None
) -> None:
    """Idempotent: PK on strategy_id makes a second call a no-op, matching
    trader/risk/breakers.py's "never silently drops a real transition, but
    never double-fires either" discipline."""
    conn.execute(
        """
        INSERT OR IGNORE INTO strategy_kill_state (strategy_id, reason, trigger_value)
        VALUES (?, ?, ?)
        """,
        (strategy_id, reason, trigger_value),
    )
    conn.commit()


def get_kill_state(conn: sqlite3.Connection) -> dict[str, dict]:
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    rows = cursor.execute("SELECT * FROM strategy_kill_state").fetchall()
    return {row["strategy_id"]: _row_to_dict(row) for row in rows}
