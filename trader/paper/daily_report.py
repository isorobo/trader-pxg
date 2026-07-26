"""The paper-trading section of the daily ground-truth report (05-07-PLAN.md,
D-12), appended by trader/ground_truth/report.py's main() after Phase 0's own
section is already written to disk.

`compute_paper_section` never raises on a completely empty (but
schema-present) database -- see the module's own tests. It CAN raise on a DB
that is missing Phase 5's tables entirely (an older DB, or a fresh checkout
where entry_pipeline/guardian/reconcile have never yet run against
data/trader.db) -- that failure mode is Phase 0 report.py's problem to guard
against (T-05-12: wrapped in try/except there, degrading to "no paper
section this run", never a missing Phase 0 report), not this module's.

Manual Interventions tally (NEW, W2): reads reconciliation_log/breaker_events
rows with actor='human' directly -- 'scheduled_auth' ops-log lines are NEVER
included here, since they live in a different store entirely (the ops log
file, not these two SQL tables) and D-13 treats them as a pre-registered
exception, never a manual intervention.

Timestamp note: reconciliation_log.ts/breaker_events.ts both default to
SQLite's `datetime('now')`, which renders as "YYYY-MM-DD HH:MM:SS" (a space
separator, no 'T', no UTC offset) -- NOT Python's `datetime.isoformat()`
shape ("...THH:MM:SS+00:00"). Comparing those two string shapes with a plain
">=" would silently misorder rows (ASCII ' ' < 'T', so an isoformat() window
bound would incorrectly exclude same-day rows) -- `_sql_ts` below renders the
window bound in the exact format the DEFAULT clause itself produces, so the
">=" comparison stays a correct, format-matched string comparison.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from trader.paper import config, ledger, ops_log, reconcile
from trader.risk import breakers

_OPS_LOG_PATH = "ops/paper_trading.log"


def _sql_ts(dt: datetime) -> str:
    """Render dt in SQLite's own `datetime('now')` string shape (UTC,
    space-separated, no offset) -- see module docstring's timestamp note."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def get_manual_reconciliation_events(conn: sqlite3.Connection, since: str) -> list[dict]:
    """`reconciliation_log` rows with actor='human' (clear_halt.py's clears)
    at or after `since` (a `_sql_ts`-formatted string). Parameterized
    (ASVS V5)."""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    rows = cursor.execute(
        "SELECT ts, reason FROM reconciliation_log WHERE actor = 'human' AND ts >= ?",
        (since,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_manual_breaker_events(conn: sqlite3.Connection, since: str) -> list[dict]:
    """`breaker_events` rows with actor='human' (trader.risk.clear_breaker's
    clears) at or after `since` (a `_sql_ts`-formatted string). Parameterized
    (ASVS V5)."""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    rows = cursor.execute(
        "SELECT ts, reason FROM breaker_events WHERE actor = 'human' AND ts >= ?",
        (since,),
    ).fetchall()
    return [dict(row) for row in rows]


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def compute_paper_section(conn: sqlite3.Connection, as_of: datetime | None = None) -> list[str]:
    """Build the "## Paper Trading" markdown section: open positions,
    recent closed trades, breaker/halt state, retired strategies, the
    Manual Interventions tally (W2), and scheduled-run coverage. Returns the
    list of markdown lines -- never writes a file itself (that stays
    report.py's job, matching the existing separation of concerns).
    """
    as_of = as_of or datetime.now(timezone.utc)
    window_start = as_of - timedelta(days=1)
    since = _sql_ts(window_start)

    positions = ledger.get_open_positions(conn)

    recent_trades: list[dict] = []
    for cfg in config.LIVE_STRATEGY_CONFIGS:
        recent_trades.extend(ledger.get_recent_trades(conn, cfg.profile_name, limit=5))

    breaker_state = breakers.read_breaker_state(conn)
    halted = reconcile.is_entry_halted(conn)
    kill_state = ledger.get_kill_state(conn)

    # Guardian's cadence (the tightest of the three scheduled processes) as
    # the representative one -- reconcile's 60s cadence would report a huge
    # expected count on a daily window, not useful for a human skim.
    coverage_entry = ops_log.compute_run_coverage(
        _OPS_LOG_PATH, window_start, as_of, config.GUARDIAN_CADENCE_MINUTES
    )

    manual_events = get_manual_reconciliation_events(conn, since)
    manual_events += get_manual_breaker_events(conn, since)
    manual_events.sort(key=lambda event: event["ts"])

    lines: list[str] = ["", "## Paper Trading", ""]

    lines.append("### Open Positions")
    lines.append("")
    if positions:
        lines.append("| Symbol | Strategy | Qty | Entry Price | Entry Ts |")
        lines.append("|---|---|---|---|---|")
        for position in positions:
            lines.append(
                "| {symbol} | {strategy_id} | {qty} | {entry_price} | {entry_ts} |".format(
                    symbol=position["symbol"],
                    strategy_id=position["strategy_id"],
                    qty=position["qty"],
                    entry_price=_fmt(position["entry_price"]),
                    entry_ts=position["entry_ts"],
                )
            )
    else:
        lines.append("No open positions.")
    lines.append("")

    lines.append("### Recent Closed Trades")
    lines.append("")
    if recent_trades:
        lines.append("| Symbol | Strategy | Exit Reason | P&L | Exit Ts |")
        lines.append("|---|---|---|---|---|")
        for trade in recent_trades:
            lines.append(
                "| {symbol} | {strategy_id} | {exit_reason} | {pnl} | {exit_ts} |".format(
                    symbol=trade["symbol"],
                    strategy_id=trade["strategy_id"],
                    exit_reason=trade["exit_reason"],
                    pnl=_fmt(trade["pnl"]),
                    exit_ts=trade["exit_ts"],
                )
            )
    else:
        lines.append("No closed trades.")
    lines.append("")

    lines.append("### Breaker / Halt State")
    lines.append("")
    for breaker_type, state in breaker_state.items():
        lines.append(f"- {breaker_type}: {state['current_action']}")
    lines.append(f"- Entry halted: {halted}")
    lines.append("")

    lines.append("### Retired Strategies")
    lines.append("")
    if kill_state:
        for strategy_id, row in kill_state.items():
            lines.append(f"- {strategy_id}: {row['reason']} (trigger={row['trigger_value']})")
    else:
        lines.append("None retired")
    lines.append("")

    lines.append("### Manual Interventions (window)")
    lines.append("")
    if manual_events:
        for event in manual_events:
            lines.append(f"- {event['ts']}: {event['reason']}")
    else:
        lines.append("None this window")
    lines.append("")

    lines.append("### Scheduled-Run Coverage (24h)")
    lines.append("")
    lines.append(
        "Coverage: {completed}/{expected} ({pct:.1f}%)".format(**coverage_entry)
    )
    lines.append("")

    return lines
