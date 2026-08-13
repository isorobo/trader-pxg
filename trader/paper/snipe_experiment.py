"""OWNER SNIPE EXPERIMENT (2026-08-14 direct order: "BUY SOME MEMECOINS
THERE BEING MADE EVERY HOUR BUY AND SELL AT LEAST 1").

A live paper demonstration of the owner's snipe rule, run at experiment
size. The pre-run study (snipe_study.py, 245 measured snipes) predicts
about -8% per trade; the owner ordered it live regardless, which is
exactly what paper money is for. Every trade books under the segregated
strategy_id 'owner_snipe_experiment' -- it never touches the tournament
registry, so real strategies' records stay clean, and the daily digest
carries its running score automatically.

Per hourly run:
1. SELL: sim-close every open snipe older than MIN_HOLD_MINUTES at the
   coin's freshest scanner price (memecoin fees+slippage, honest fills).
   A coin with no snapshot in the last EXIT_STALE_LIMIT_MINUTES exits at
   its last known price and the trade is flagged in the alert -- vanished
   coins usually vanished DOWN, so this is kind to the experiment.
2. BUY: sim-buy NOTIONAL_PER_SNIPE of the newest first-seen crypto ticker
   from the ground-truth log (fresh within FRESH_LIMIT_MINUTES, never
   re-sniped) -- "as soon as we can see it".

Sized so a full 24-snipe day risks ~$600 of PAPER money, matching the
owner's nightly budget scale.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

from trader.backtest.config import EXIT_PROFILE
from trader.paper import alerts, broker_crypto_sim, idempotency, ledger

STRATEGY_ID = "owner_snipe_experiment"
NOTIONAL_PER_SNIPE = 25.0
MIN_HOLD_MINUTES = 30
FRESH_LIMIT_MINUTES = 20
EXIT_STALE_LIMIT_MINUTES = 45

_PROFILE = EXIT_PROFILE(
    stop_pct=None, tp_pct=None, scale_out=(), trailing_pct=None,
    max_hold_days=1, eod_flat=False,
)


def _latest_price(conn: sqlite3.Connection, ticker: str) -> tuple[float, str] | None:
    row = conn.execute(
        "SELECT price, poll_ts FROM snapshots WHERE source='crypto' AND ticker=? "
        "AND price IS NOT NULL AND price > 0 ORDER BY poll_ts DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    return (float(row[0]), row[1]) if row else None


def _close_ripe_snipes(conn: sqlite3.Connection, now: datetime) -> list[dict]:
    closed = []
    for position in ledger.get_open_positions(conn):
        if position["strategy_id"] != STRATEGY_ID:
            continue
        entry_ts = datetime.fromisoformat(position["entry_ts"])
        if now - entry_ts < timedelta(minutes=MIN_HOLD_MINUTES):
            continue

        ticker = position["symbol"]
        quote = _latest_price(conn, ticker)
        if quote is None:
            continue
        raw_price, quote_ts = quote
        stale = (now - datetime.fromisoformat(quote_ts)) > timedelta(
            minutes=EXIT_STALE_LIMIT_MINUTES
        )

        qty = position["qty"]
        fill = broker_crypto_sim.simulate_fill(ticker, "sell", qty, raw_price, "memecoin")
        order_ref = idempotency.build_order_ref(
            STRATEGY_ID, ticker, now.strftime("%Y-%m-%dT%H"), "sell", "exit_time_stop"
        )
        ledger.record_order(
            conn, order_ref, STRATEGY_ID, ticker, "crypto_sim", "sell",
            "exit_time_stop", qty, status="pending_submit",
        )
        ledger.update_order_status(conn, order_ref, status="filled", fill_price=fill["fill_price"])
        pnl = (fill["fill_price"] - position["entry_price"]) * qty - fill["fee"]
        ledger.close_position(
            conn, position["position_id"], exit_ts=now.isoformat(),
            exit_price=fill["fill_price"], exit_reason="time_stop",
            exit_order_ref=order_ref, fees=fill["fee"],
            slippage_cost=abs(fill["fill_price"] - raw_price) * qty, pnl=pnl,
        )
        closed.append({"ticker": ticker, "pnl": pnl, "stale_quote": stale})
    return closed


def _pick_fresh_target(conn: sqlite3.Connection, now: datetime) -> str | None:
    """Newest first-seen crypto ticker, fresh within FRESH_LIMIT_MINUTES,
    never sniped before (order history is the dedupe)."""
    cutoff = (now - timedelta(minutes=FRESH_LIMIT_MINUTES)).isoformat()
    rows = conn.execute(
        """
        SELECT ticker, MIN(poll_ts) AS first_seen FROM snapshots
        WHERE source='crypto' AND price IS NOT NULL AND price > 0
        GROUP BY ticker HAVING first_seen >= ? ORDER BY first_seen DESC
        """,
        (cutoff,),
    ).fetchall()
    for ticker, _first_seen in rows:
        sniped = conn.execute(
            "SELECT 1 FROM paper_orders WHERE strategy_id=? AND symbol=? LIMIT 1",
            (STRATEGY_ID, ticker),
        ).fetchone()
        if sniped is None:
            return ticker
    return None


def run_snipe_once(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    closed = _close_ripe_snipes(conn, now)

    bought = None
    target = _pick_fresh_target(conn, now)
    if target is not None:
        quote = _latest_price(conn, target)
        if quote is not None:
            raw_price, _ts = quote
            fill = broker_crypto_sim.simulate_fill(
                target, "buy", NOTIONAL_PER_SNIPE / raw_price, raw_price, "memecoin"
            )
            qty = fill["qty"]
            order_ref = idempotency.build_order_ref(
                STRATEGY_ID, target, now.strftime("%Y-%m-%dT%H"), "buy", "entry"
            )
            ledger.record_order(
                conn, order_ref, STRATEGY_ID, target, "crypto_sim", "buy",
                "entry", qty, status="pending_submit",
            )
            ledger.update_order_status(
                conn, order_ref, status="filled", fill_price=fill["fill_price"]
            )
            ledger.open_position(
                conn, STRATEGY_ID, target, "crypto_sim", "memecoin", qty,
                fill["fill_price"], now.isoformat(), order_ref, _PROFILE,
            )
            bought = target

    if closed or bought:
        parts = []
        if bought:
            parts.append(f"sniped {bought} (${NOTIONAL_PER_SNIPE:g})")
        for c in closed:
            flag = " [stale quote]" if c["stale_quote"] else ""
            parts.append(f"sold {c['ticker']} pnl {c['pnl']:+.2f}{flag}")
        alerts.notify("fill", "OWNER SNIPE EXPERIMENT: " + "; ".join(parts))

    return {"bought": bought, "closed": closed}


def main(argv: list[str] | None = None) -> None:
    from trader.data import db

    parser = argparse.ArgumentParser(
        prog="python -m trader.paper.snipe_experiment",
        description="One hourly pass of the owner snipe experiment (paper only).",
    )
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--db-path", default="data/trader.db")
    args = parser.parse_args(argv)

    conn = db.get_connection(args.db_path)
    try:
        print(run_snipe_once(conn))
    finally:
        conn.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
