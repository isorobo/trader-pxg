"""The sole human-invoked CLI entrypoint that clears a reconciliation halt
(PAPER-04, T-05-08), and the ops-log producer for that intervention
(BLOCKER 3).

This module is the ONLY writer of the reconciliation halt's ending action
in the entire codebase -- mirrors `trader/risk/clear_breaker.py`'s
sole-clear-path pattern exactly (same T-04-10 precedent, now T-05-08).
Invoke it exactly like this, as an explicit human-run command:

    python -m trader.paper.clear_halt --reason "<why>"

`clear_entry_halt` immediately appends a `manual_restart_required` ops-log
entry carrying the same reason text, in the same call (REVISED, BLOCKER 3):
every reconciliation-halt clear is now durably logged as a manual
intervention the instant it happens, so the two-week "zero manual
interventions" exit gate's audit reads entirely from the ops log rather
than relying on the operator remembering to log it separately.

Companion runbook note -- this module owns ONLY the reconciliation halt
path. Clearing a Phase 4 breaker (daily_loss/drawdown/consecutive_loss) via
the existing, unmodified `python -m trader.risk.clear_breaker --reason
"<why>"` CLI does NOT itself touch the ops log (that module is already
shipped and out of Phase 5's scope to modify) -- the owner must separately
run `python -m trader.paper.ops_log --entry-type manual_restart_required
--message "<why>"` (Plan 05-02's BLOCKER 2 CLI) right after; 05-09's
runbook states this explicitly.

`--db-path` defaults to `data/trader.db` (the project's shared live DB);
pass `--db-path` explicitly to target a different database (e.g. tests).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from trader.data import db
from trader.paper import ops_log

_DEFAULT_LOG_PATH = "ops/paper_trading.log"


def clear_entry_halt(
    conn, reason: str, log_path: str = _DEFAULT_LOG_PATH
) -> None:
    """The ONLY function permitted to end a reconciliation halt (T-05-08).

    Inserts one `reconciliation_log` row (symbol=None, venue='ibkr_paper',
    classification='informational', action is the halt-ending value,
    reason=reason, actor='human'), THEN calls
    `ops_log.append_ops_log("manual_restart_required", reason, log_path)`
    as its last step, in the same call (BLOCKER 3) -- never two separate
    steps an operator could forget to pair.
    """
    conn.execute(
        """
        INSERT INTO reconciliation_log
            (symbol, venue, local_qty, broker_qty, classification, action, reason, actor)
        VALUES (NULL, 'ibkr_paper', NULL, NULL, 'informational', ?, ?, 'human')
        """,
        ("clear", reason),
    )
    conn.commit()
    ops_log.append_ops_log("manual_restart_required", reason, log_path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m trader.paper.clear_halt",
        description=(
            "Clear a reconciliation halt. This is the ONLY way to clear it "
            "-- there is no automated clear path anywhere in the codebase. "
            "Also appends a manual_restart_required ops-log entry."
        ),
    )
    parser.add_argument(
        "--reason",
        required=True,
        help="Why the human is clearing the halt (stored in the audit log).",
    )
    parser.add_argument(
        "--db-path",
        default="data/trader.db",
        help="Path to the SQLite DB (default: data/trader.db).",
    )
    args = parser.parse_args(argv)

    conn = db.get_connection(args.db_path)
    clear_entry_halt(conn, reason=args.reason)
    conn.close()

    timestamp = datetime.now(timezone.utc).isoformat()
    print(
        f"Reconciliation halt cleared at {timestamp} UTC. "
        f"Reason: {args.reason}"
    )


if __name__ == "__main__":
    main()
