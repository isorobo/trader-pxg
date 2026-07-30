"""PAPER-04's reconciliation loop: a pure classification function, the
combined `is_entry_halted` gate the entry pipeline (05-06) consults before
every submit, and the `--once` CLI (D-05: no daemon mode).

`classify_divergence` mirrors `trader/risk/breakers.py`'s
evaluate_breakers purity guarantee exactly -- zero DB/file I/O, no
`sqlite3` import. It defaults conservatively (T-05-04): a delta is only
ever "explainable" when it exactly equals a known pending order quantity
(`pending_qty`, sourced unchanged from `trader.paper.ledger.get_pending_order_qty`
-- see that function's own docstring for why 'pending_submit' rows are
deliberately excluded from that dict, BLOCKER 1). Every other non-zero
delta is "unexplained" -- never a tolerance band, never the reverse
default.

Persistence (`record_reconciliation`) mirrors
`trader/risk/breakers.py`'s `append_breaker_event`'s shape: a single
parameterized INSERT into the append-only `reconciliation_log` table
(`migrations/0005_paper_trading.sql`). `is_entry_halted` re-derives its
answer from `reconciliation_halt_state` (a view over that log) and from
`trader.risk.breakers.read_breaker_state` on every single call -- standing
rule 4 ("if the system and the exchange disagree, the system halts") means
this file never caches a boolean anywhere at module scope.

The ONLY code path that can ever end a reconciliation halt is
`trader.paper.clear_halt.clear_entry_halt` -- no function in this module
ever writes the halt-ending action value (T-05-08); that literal string is
confined entirely to `trader/paper/clear_halt.py`.
"""

from __future__ import annotations

import argparse
import sys

from trader.paper import alerts, ledger
from trader.paper.broker_ibkr import IBKRBrokerAdapter
from trader.risk import breakers

_BREAKER_TYPES = ("daily_loss", "drawdown", "consecutive_loss")


def classify_divergence(
    local_positions: dict[str, float],
    broker_positions: dict[str, float],
    pending_qty: dict[str, float],
) -> list[dict]:
    """Pure classification, zero I/O (mirrors evaluate_breakers's purity).

    For every symbol in the union of both position dicts, compute
    ``delta = broker_positions.get(symbol, 0) - local_positions.get(symbol, 0)``;
    skip if ``delta == 0``. Classify "explainable" ONLY when
    ``pending_qty.get(symbol) == abs(delta)`` exactly -- never a tolerance
    band (T-05-04's conservative-default rule). Every other non-zero delta
    is "unexplained".
    """
    divergences: list[dict] = []
    symbols = sorted(set(local_positions) | set(broker_positions))
    for symbol in symbols:
        local_qty = local_positions.get(symbol, 0)
        broker_qty = broker_positions.get(symbol, 0)
        delta = broker_qty - local_qty
        if delta == 0:
            continue

        classification = (
            "explainable"
            if pending_qty.get(symbol) == abs(delta)
            else "unexplained"
        )
        divergences.append(
            {
                "symbol": symbol,
                "local_qty": local_qty,
                "broker_qty": broker_qty,
                "classification": classification,
            }
        )
    return divergences


def record_reconciliation(
    conn,
    symbol: str | None,
    venue: str,
    local_qty: float | None,
    broker_qty: float | None,
    classification: str,
    reason: str | None = None,
) -> None:
    """Insert exactly one parameterized row into ``reconciliation_log``
    (ASVS V5, mirrors ``trader.risk.breakers.append_breaker_event``).

    ``action`` is derived, never passed by the caller: "halt" iff
    ``classification == "unexplained"``, otherwise "log". This function
    never ends a halt -- ``trader.paper.clear_halt`` is the sole writer of
    that action (T-05-08).
    """
    action = "halt" if classification == "unexplained" else "log"
    conn.execute(
        """
        INSERT INTO reconciliation_log
            (symbol, venue, local_qty, broker_qty, classification, action, reason, actor)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'system')
        """,
        (symbol, venue, local_qty, broker_qty, classification, action, reason),
    )
    conn.commit()


def is_entry_halted(conn) -> bool:
    """True iff entries must not be submitted right now.

    Re-derived fresh on every call (standing rule 4) -- never a cached
    boolean. True whenever any Phase 4 breaker (daily_loss/drawdown/
    consecutive_loss) is currently tripped (D-07 "wired through Phase 4's
    breakers"), OR whenever ``reconciliation_halt_state``'s latest
    halt/clear row is a 'halt'.
    """
    breaker_state = breakers.read_breaker_state(conn)
    for breaker_type in _BREAKER_TYPES:
        if breaker_state[breaker_type]["current_action"] == "trip":
            return True

    row = conn.execute(
        "SELECT current_action FROM reconciliation_halt_state"
    ).fetchone()
    return row is not None and row[0] == "halt"


def run_reconcile_once(conn, ibkr_adapter, crypto_adapter=None) -> dict:
    """The ``--once`` CLI body (D-05, mirrors
    ``trader.ground_truth.poll.run_poll_once``'s shape).

    Builds ``local_positions`` from ``ledger.get_open_positions`` (summed
    per symbol, 'ibkr_paper' venue only), ``pending_qty`` from
    ``ledger.get_pending_order_qty`` (consumed unchanged, never redefined
    here -- BLOCKER 1), and ``broker_positions`` from
    ``ibkr_adapter.snapshot()``. Records every divergence via
    ``record_reconciliation`` and fires an "error" alert (fire and forget,
    D-11) for every "unexplained" entry -- the alert message names the
    symbol/deltas but never dumps raw broker credentials.

    ``crypto_adapter``'s Kraken read-only check (D-04, resolved
    informational-only default) is called if provided and its result is
    always recorded with ``venue='kraken_readonly'``,
    ``classification='informational'``, ``action='log'`` -- never 'halt'.
    """
    local_positions: dict[str, float] = {}
    for position in ledger.get_open_positions(conn):
        if position["venue"] != "ibkr_paper":
            continue
        symbol = position["symbol"]
        local_positions[symbol] = local_positions.get(symbol, 0) + position["qty"]

    pending_qty = ledger.get_pending_order_qty(conn)
    broker_positions = ibkr_adapter.snapshot()["positions"]

    divergences = classify_divergence(local_positions, broker_positions, pending_qty)
    for entry in divergences:
        record_reconciliation(
            conn,
            entry["symbol"],
            "ibkr_paper",
            entry["local_qty"],
            entry["broker_qty"],
            entry["classification"],
        )
        if entry["classification"] == "unexplained":
            alerts.notify(
                "error",
                f"Unexplained reconciliation divergence: {entry['symbol']} "
                f"local_qty={entry['local_qty']} broker_qty={entry['broker_qty']}",
            )

    if crypto_adapter is not None:
        crypto_result = crypto_adapter.check_readonly()
        record_reconciliation(
            conn,
            crypto_result.get("symbol"),
            "kraken_readonly",
            crypto_result.get("local_qty"),
            crypto_result.get("broker_qty"),
            "informational",
            reason=crypto_result.get("reason"),
        )

    return {"divergences": divergences, "halted": is_entry_halted(conn)}


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: ``python -m trader.paper.reconcile --once``.

    Phase 0's D-05 no-daemon convention: omitting ``--once`` is a usage
    error, not a silent no-op.
    """
    from trader.data import db

    parser = argparse.ArgumentParser(
        prog="python -m trader.paper.reconcile",
        description="Run the paper-trading reconciliation loop once (D-05/D-07).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        required=True,
        help="Run a single reconciliation pass and exit. Required: no daemon mode.",
    )
    parser.add_argument(
        "--db-path",
        default="data/trader.db",
        help="Path to the SQLite DB (default: data/trader.db).",
    )
    args = parser.parse_args(argv)

    if not args.once:
        print("Usage error: --once is required.", file=sys.stderr)
        sys.exit(2)

    conn = db.get_connection(args.db_path)
    try:
        ibkr_adapter = IBKRBrokerAdapter()
        # connect() was missing until the first real-Gateway run (05-08
        # checkpoint, 2026-07-30) -- snapshot() dereferences the lazily
        # created ib client, so an unconnected adapter crashed with
        # AttributeError: 'NoneType' has no attribute 'reqOpenOrders'.
        # entry_pipeline/guardian mains always connected; this one did not.
        ibkr_adapter.connect()
        try:
            summary = run_reconcile_once(conn, ibkr_adapter)
            print(summary)
        finally:
            # Without an explicit disconnect the live ib_async socket can
            # keep the interpreter alive after main() returns (observed on
            # the first real-Gateway run, 2026-07-30) -- fakes never showed
            # this because they hold no socket.
            ibkr_adapter.disconnect()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
