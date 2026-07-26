"""One-shot poll orchestration entrypoint (D-05/D-06/D-07).

Wires sources.py's StockGainersSource/CryptoMoversSource into db.py's
insert_snapshot_rows/record_poll_run. Each invocation opens the DB, polls
both feeds independently, writes whatever rows succeeded, always records
a poll_runs row (even on a total miss), and exits — no daemon (D-05).
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from trader.ground_truth import db
from trader.ground_truth.sources import (
    CryptoMoversSource,
    SourceUnavailableError,
    StockGainersSource,
)

log = logging.getLogger(__name__)


def is_market_hours(now_utc: datetime) -> bool:
    """True iff now_utc falls within the Mon-Fri 09:30-16:00 US/Eastern window.

    No NYSE holiday calendar (Pattern 3, 00-RESEARCH.md) — D-06 tolerates
    gaps rather than gating the poll on market hours.
    """
    eastern = now_utc.astimezone(ZoneInfo("America/New_York"))
    if eastern.weekday() >= 5:
        return False
    return (9, 30) <= (eastern.hour, eastern.minute) < (16, 0)


def run_poll_once(db_path: str = "data/trader.db") -> dict:
    """Poll both sources once, write whichever rows succeeded, record the run.

    A stock-side failure never skips the crypto call, and vice versa (D-06) —
    each source is wrapped in its own try/except so one hanging/failing feed
    never blocks the other or the 15-minute cadence (T-00-07).
    """
    conn = db.get_connection(db_path)
    try:
        poll_ts = datetime.now(timezone.utc).isoformat()

        stock_rows: list[dict] = []
        stock_success = True
        try:
            stock_rows = StockGainersSource().fetch_top_movers(count=50)
            market_open = int(is_market_hours(datetime.now(timezone.utc)))
            for row in stock_rows:
                row["market_open"] = market_open
                row["poll_ts"] = poll_ts
        except SourceUnavailableError as error:
            log.warning(
                "Stock source failed for this poll (%s: %s)",
                type(error).__name__,
                error,
            )
            stock_rows = []
            stock_success = False

        crypto_rows: list[dict] = []
        crypto_success = True
        try:
            crypto_rows = CryptoMoversSource().fetch_top_movers(count=50)
            for row in crypto_rows:
                # Crypto never closes: market_open is always 1, independent
                # of the stock-side market hours result (Open Question 3).
                row["market_open"] = 1
                row["poll_ts"] = poll_ts
        except SourceUnavailableError as error:
            log.warning(
                "Crypto source failed for this poll (%s: %s)",
                type(error).__name__,
                error,
            )
            crypto_rows = []
            crypto_success = False

        if stock_rows:
            db.insert_snapshot_rows(conn, stock_rows)
        if crypto_rows:
            db.insert_snapshot_rows(conn, crypto_rows)

        # Always record the poll run, even on a total miss, so gaps are
        # visible in the data rather than hidden (D-06).
        db.record_poll_run(
            conn,
            poll_ts,
            int(stock_success),
            int(crypto_success),
            len(stock_rows),
            len(crypto_rows),
        )

        return {
            "stock_rows": len(stock_rows),
            "crypto_rows": len(crypto_rows),
            "stock_success": stock_success,
            "crypto_success": crypto_success,
        }
    finally:
        conn.close()


def main(argv=None) -> None:
    """CLI entry point: python -m trader.ground_truth.poll --once.

    Phase 0 has no daemon mode (D-05) — omitting --once is a usage error,
    not a silent no-op.
    """
    parser = argparse.ArgumentParser(
        description="Run the ground-truth poller once (D-05/D-07)."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        required=True,
        help="Run a single poll and exit. Required: Phase 0 has no daemon mode.",
    )
    args = parser.parse_args(argv)

    if not args.once:
        print("Usage error: --once is required.", file=sys.stderr)
        sys.exit(2)

    summary = run_poll_once()
    print(summary)


if __name__ == "__main__":
    main()
