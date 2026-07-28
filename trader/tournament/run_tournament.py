"""``python -m trader.tournament.run_tournament --once`` -- the weekly
scheduled entry point (D-03/D-10, mirrors entry_pipeline/guardian's --once
CLI shape exactly; no daemon mode).

Runs one tournament evaluation (freeze-gate verified inside
run_tournament_once), then regenerates the attribution dashboard (D-01)
so the static reports always reflect the post-run roster.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    from trader.data import db
    from trader.tournament import dashboard, judge

    parser = argparse.ArgumentParser(
        prog="python -m trader.tournament.run_tournament",
        description="Run one weekly tournament evaluation (ATTR-02, D-03).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        required=True,
        help="Run a single tournament evaluation and exit. Required: no daemon mode.",
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
        summary = judge.run_tournament_once(conn)
        paths = dashboard.write_dashboard(conn)
        print({"tournament": summary["counts"], "run_id": summary["run_id"],
               "report": summary["report_path"], "dashboard": paths})
    finally:
        conn.close()


if __name__ == "__main__":
    main()
