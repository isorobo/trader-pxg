"""The sole human-invoked CLI entrypoint that clears the drawdown circuit
breaker's halt (RISK-03, D-04/D-05, T-04-10).

This module is the ONLY caller of ``trader.risk.breakers.clear_manual_restart``
in the entire codebase -- there is no automated clear path anywhere else
(security requirement). Invoke it exactly like this, as an explicit
human-run command:

    python -m trader.risk.clear_breaker --reason "<why>"

``--db-path`` defaults to ``data/trader.db`` (the project's shared live DB);
pass ``--db-path`` explicitly to target a different database (e.g. tests).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from trader.data import db
from trader.risk import breakers


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m trader.risk.clear_breaker",
        description=(
            "Clear the drawdown circuit breaker's manual-restart halt. "
            "This is the ONLY way to clear it -- there is no automated "
            "clear path anywhere in the codebase."
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
    breakers.clear_manual_restart(conn, reason=args.reason)
    conn.close()

    timestamp = datetime.now(timezone.utc).isoformat()
    print(
        f"Drawdown breaker manual restart cleared at {timestamp} UTC. "
        f"Reason: {args.reason}"
    )


if __name__ == "__main__":
    main()
