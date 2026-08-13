"""Daily Telegram P&L digest (owner request 2026-08-13: "send me my profit
vs how much i've invested").

One message per run: invested cost basis of every open position, unrealized
P&L marked against independent quotes (yfinance for stocks, the crypto sim
price feed for crypto -- deliberately NOT the Gateway, so the digest still
arrives when IBKR is logged out), total realized P&L from closed trades,
and the fortnight profitable-sell tally vs the owner's target of 5.

A symbol whose quote lookup fails is marked at entry (0 unrealized) and
flagged in the message -- degraded but honest, never silent or crashed.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

from trader.paper import alerts, broker_crypto_sim

FORTNIGHT_TARGET_PROFITABLE_SELLS = 5


def _mark_price(symbol: str, venue: str) -> float | None:
    try:
        if venue == "crypto_sim" or "/" in symbol:
            return float(broker_crypto_sim.fetch_price(symbol))
        import yfinance

        hist = yfinance.Ticker(symbol).history(period="5d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
        return None


def build_digest(conn: sqlite3.Connection, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row

    open_rows = cursor.execute(
        "SELECT symbol, venue, qty, entry_price FROM paper_positions "
        "WHERE status = 'open' ORDER BY symbol"
    ).fetchall()

    invested = 0.0
    unrealized = 0.0
    unpriced: list[str] = []
    lines: list[str] = []
    for row in open_rows:
        cost = row["qty"] * row["entry_price"]
        invested += cost
        mark = _mark_price(row["symbol"], row["venue"])
        if mark is None:
            unpriced.append(row["symbol"])
            continue
        pnl = (mark - row["entry_price"]) * row["qty"]
        unrealized += pnl
        lines.append(
            f"  {row['symbol']}: {pnl:+.2f} ({(mark / row['entry_price'] - 1) * 100:+.1f}%)"
        )

    realized_row = cursor.execute(
        "SELECT COALESCE(SUM(pnl), 0), COUNT(*) FROM paper_trades"
    ).fetchone()
    realized, closed_count = float(realized_row[0]), int(realized_row[1])

    fortnight_start = (now - timedelta(days=14)).strftime("%Y-%m-%d")
    wins_row = cursor.execute(
        "SELECT COUNT(*) FROM paper_trades WHERE pnl > 0 AND exit_ts >= ?",
        (fortnight_start,),
    ).fetchone()
    fortnight_wins = int(wins_row[0])

    parts = [
        f"Daily P&L digest {now.date().isoformat()}",
        f"Invested: ${invested:,.2f} across {len(open_rows)} open position(s)",
        f"Unrealized: {unrealized:+,.2f}",
        f"Realized (all time): {realized:+,.2f} over {closed_count} closed trade(s)",
        f"Fortnight profitable sells: {fortnight_wins}/{FORTNIGHT_TARGET_PROFITABLE_SELLS} (owner target)",
    ]
    if lines:
        parts.append("Open positions:")
        parts.extend(lines)
    if unpriced:
        parts.append(f"Unpriced (quote lookup failed, shown at entry): {', '.join(unpriced)}")
    return "\n".join(parts)


def run_digest_once(conn: sqlite3.Connection) -> str:
    message = build_digest(conn)
    alerts.notify("heartbeat", message)
    return message


def main(argv: list[str] | None = None) -> None:
    from trader.data import db

    parser = argparse.ArgumentParser(
        prog="python -m trader.paper.daily_digest",
        description="Send the daily Telegram P&L digest once.",
    )
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--db-path", default="data/trader.db")
    args = parser.parse_args(argv)

    conn = db.get_connection(args.db_path)
    try:
        print(run_digest_once(conn))
    finally:
        conn.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
