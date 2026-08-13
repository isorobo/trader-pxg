"""Owner hypothesis study (2026-08-14): "buy memecoins as soon as they are
made, sell 30 minutes later" -- tested at our real detection latency.

Honest framing: this system's earliest sight of a new coin is its FIRST
appearance in the CoinGecko trending log (the 15-min ground-truth poller),
minutes-to-hours after on-chain creation. True launch-sniping needs
on-chain infra we do not have; this study measures the owner's rule at
the latency we actually possess, on OUR OWN logged snapshots -- which
include the coins that died (no survivorship bias).

Rule simulated per first-seen crypto ticker:
- ENTRY at the first-seen snapshot price.
- EXIT at the first later snapshot of the same coin >= 30 minutes after
  entry (the poller's 15-min cadence makes this typically the 30-45 min
  mark). Memecoin fees+slippage applied on both sides via the Phase 2
  fill model -- the same costs every other strategy pays.
- A coin that VANISHES from trending before an exit snapshot exists is
  reported separately as unmeasurable -- vanishing is itself usually the
  dump, so the measurable set is, if anything, biased KINDLY toward the
  strategy.

Research artifact only: writes reports/backtests/snipe_study.json and
prints the verdict. Registers nothing.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from trader.backtest.fills import apply_slippage, fee_for

OUT_PATH = Path("reports/backtests/snipe_study.json")
HOLD_MINUTES = 30
NOTIONAL = 100.0  # dollars per snipe, for fee math


def run_study(conn: sqlite3.Connection) -> dict:
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    rows = cursor.execute(
        """
        SELECT ticker, coingecko_id, poll_ts, price
        FROM snapshots
        WHERE source = 'crypto' AND price IS NOT NULL AND price > 0
        ORDER BY ticker, poll_ts
        """
    ).fetchall()

    by_ticker: dict[str, list] = {}
    for row in rows:
        by_ticker.setdefault(row["ticker"], []).append(row)

    results = []
    unmeasurable = 0
    for ticker, snaps in by_ticker.items():
        first = snaps[0]
        entry_ts = datetime.fromisoformat(first["poll_ts"])
        exit_snap = next(
            (
                s
                for s in snaps[1:]
                if datetime.fromisoformat(s["poll_ts"])
                >= entry_ts + timedelta(minutes=HOLD_MINUTES)
            ),
            None,
        )
        if exit_snap is None:
            unmeasurable += 1
            continue

        raw_entry, raw_exit = first["price"], exit_snap["price"]
        entry_price = apply_slippage(raw_entry, "buy", "memecoin")
        exit_price = apply_slippage(raw_exit, "sell", "memecoin")
        qty = NOTIONAL / entry_price
        fees = fee_for("memecoin", qty, entry_price) + fee_for("memecoin", qty, exit_price)
        pnl = (exit_price - entry_price) * qty - fees
        results.append(
            {
                "ticker": ticker,
                "entry_ts": first["poll_ts"],
                "exit_ts": exit_snap["poll_ts"],
                "raw_move_pct": (raw_exit / raw_entry - 1) * 100,
                "net_pnl_per_100": pnl,
            }
        )

    total = sum(r["net_pnl_per_100"] for r in results)
    winners = [r for r in results if r["net_pnl_per_100"] > 0]
    summary = {
        "hold_minutes": HOLD_MINUTES,
        "measurable_snipes": len(results),
        "unmeasurable_vanished_first": unmeasurable,
        "win_rate_pct": round(100 * len(winners) / len(results), 1) if results else None,
        "net_pnl_per_100_each_total": round(total, 2),
        "avg_net_pnl_per_100": round(total / len(results), 3) if results else None,
        "best": max(results, key=lambda r: r["net_pnl_per_100"], default=None),
        "worst": min(results, key=lambda r: r["net_pnl_per_100"], default=None),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps({"summary": summary, "results": results}, indent=2, default=str)
    )
    return summary


def main() -> None:
    conn = sqlite3.connect("data/trader.db")
    try:
        summary = run_study(conn)
    finally:
        conn.close()
    print(json.dumps(summary, indent=2, default=str))
    sys.exit(0)


if __name__ == "__main__":
    main()
