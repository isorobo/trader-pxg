"""Rotating operations log appender + scheduled-run coverage computation +
a CLI producer for scheduled_auth/manual_restart_required entries (D-12,
BLOCKER 2).

Every run appends to a rotating ops log so the two-week unattended paper
run is auditable from disk. 'scheduled_auth' is D-13's weekly IBKR 2FA tap
-- a pre-registered, expected exception -- kept a distinct entry_type from
'manual_restart_required' so the exit gate's "zero manual interventions"
tally never conflates the two (must_haves.truths, 05-02-PLAN.md).

main() is the owner's actual command-line producer: no Python required to
log a scheduled_auth tap or a post-clear_breaker manual_restart_required
entry (BLOCKER 2/3).
"""

import argparse
import logging
import os
from datetime import datetime, timedelta, timezone
from logging.handlers import TimedRotatingFileHandler

log = logging.getLogger(__name__)

_KNOWN_ENTRY_TYPES = frozenset(
    {
        "scheduled_run",
        "scheduled_auth",
        "fill",
        "error",
        "heartbeat",
        "manual_restart_required",
    }
)

_DEFAULT_LOG_PATH = "ops/paper_trading.log"

# Module-level cache of one dedicated logger per log_path, configured once
# (a fresh TimedRotatingFileHandler per distinct path, never re-added on a
# repeat call -- avoids duplicate lines from a re-configured handler).
_LOGGERS: dict[str, logging.Logger] = {}


def _get_ops_logger(log_path: str) -> logging.Logger:
    if log_path in _LOGGERS:
        return _LOGGERS[log_path]

    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(f"trader.paper.ops_log.file.{log_path}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = TimedRotatingFileHandler(
        log_path, when="midnight", backupCount=30, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    _LOGGERS[log_path] = logger
    return logger


def append_ops_log(
    entry_type: str, message: str, log_path: str = _DEFAULT_LOG_PATH
) -> None:
    """Append one pipe-delimited line: "{iso_ts}|{entry_type}|{message}".

    Raises ValueError for any entry_type outside _KNOWN_ENTRY_TYPES -- a
    plain guard, not a DB CHECK constraint, since this is a file, not a
    table.
    """
    if entry_type not in _KNOWN_ENTRY_TYPES:
        raise ValueError(
            f"Unknown ops-log entry_type: {entry_type!r} "
            f"(expected one of {sorted(_KNOWN_ENTRY_TYPES)})"
        )

    iso_ts = datetime.now(timezone.utc).isoformat()
    logger = _get_ops_logger(log_path)
    logger.info("%s|%s|%s", iso_ts, entry_type, message)


def compute_run_coverage(
    log_path: str,
    window_start: datetime,
    window_end: datetime,
    expected_cadence_minutes: int,
) -> dict:
    """Return {"expected", "completed", "pct"} scheduled-run coverage stats.

    Parses every 'scheduled_run' line's timestamp within
    [window_start, window_end] -- 'scheduled_auth' and every other
    entry_type is never counted here, so D-13's weekly 2FA tap can never
    inflate (or, if missed, deflate) the scheduled-run coverage tally.
    Mirrors trader.ground_truth.db.query_poll_run_coverage's return shape
    exactly (same field names) so Plan 05-07's daily-report section can
    reuse the same rendering code Phase 0 already has.
    """
    completed = 0
    if os.path.exists(log_path):
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("|", 2)
                if len(parts) != 3:
                    continue
                ts_str, entry_type, _message = parts
                if entry_type != "scheduled_run":
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str)
                except ValueError:
                    continue
                if window_start <= ts <= window_end:
                    completed += 1

    expected = (window_end - window_start) / timedelta(minutes=expected_cadence_minutes)
    return {
        "expected": int(expected),
        "completed": completed,
        "pct": (completed / expected * 100.0) if expected else 0.0,
    }


def main(argv=None) -> None:
    """CLI entry point (BLOCKER 2): a human-runnable ops-log producer.

    python -m trader.paper.ops_log --entry-type scheduled_auth --message
    "weekly IBKR 2FA tap confirmed" -- run by the owner after every weekly
    2FA approval (D-13), and with --entry-type manual_restart_required
    after clearing a Phase 4 breaker via trader.risk.clear_breaker
    (clear_breaker.py itself stays unmodified -- this CLI is the missing
    ops-log half of that existing clear path, BLOCKER 3).

    argparse's own choices= validation rejects an unknown --entry-type
    before append_ops_log's ValueError path is ever reached -- a clean
    CLI-level error (argparse exits 2), never a raw traceback.
    """
    parser = argparse.ArgumentParser(
        description="Append an entry to the paper-trading ops log (D-12)."
    )
    parser.add_argument(
        "--entry-type",
        choices=sorted(_KNOWN_ENTRY_TYPES),
        required=True,
        help="One of the known ops-log entry types.",
    )
    parser.add_argument(
        "--message", required=True, type=str, help="Free-text log message."
    )
    parser.add_argument(
        "--log-path",
        default=_DEFAULT_LOG_PATH,
        help=f"Log file path (default: {_DEFAULT_LOG_PATH}).",
    )
    args = parser.parse_args(argv)

    append_ops_log(args.entry_type, args.message, args.log_path)
    print(f"Logged {args.entry_type} to {args.log_path}")


if __name__ == "__main__":
    main()
