"""Owner-ordered position close -- the human override CLI (2026-08-13:
"that increase in money sell it tonight no exceptions").

Mirrors the guardian's exact close sequence (persist order BEFORE the
broker call, real sell through the adapter, fees/slippage on the recorded
exit) and books the trade with exit_reason='owner_close' -- the ledger
records the sale as an owner decision, never disguised as a rule exit.
Human-invoked only; no scheduled task ever runs this module.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone

from trader.backtest.fills import fee_for
from trader.paper import alerts, broker_crypto_sim, broker_ibkr, config, idempotency, ledger

_INTENT = "exit_owner_close"
_REASON = "owner_close"


def close_position_by_symbol(conn, ibkr_adapter, symbol: str) -> dict:
    position = next(
        (p for p in ledger.get_open_positions(conn) if p["symbol"] == symbol), None
    )
    if position is None:
        raise SystemExit(f"no open position for {symbol!r}")

    qty = position["qty"]
    strategy_id = position["strategy_id"]
    venue = position["venue"]
    asset_class = position["asset_class"]
    entry_price = position["entry_price"]
    now_iso = datetime.now(timezone.utc).isoformat()

    order_ref = idempotency.build_order_ref(
        strategy_id, symbol, date.today().isoformat(), "sell", _INTENT
    )
    ledger.record_order(
        conn, order_ref, strategy_id, symbol, venue, "sell", _INTENT, qty,
        status="pending_submit",
    )

    if venue == "ibkr_paper":
        current_price = ibkr_adapter.latest_price(symbol)
        broker_result = ibkr_adapter.place_order(symbol, "SELL", qty, order_ref)
        ledger.update_order_status(
            conn, order_ref, status="submitted", perm_id=broker_result["perm_id"]
        )
        exit_price = current_price
    else:
        current_price = broker_crypto_sim.fetch_price(symbol)
        fill = broker_crypto_sim.simulate_fill(symbol, "sell", qty, current_price, asset_class)
        ledger.update_order_status(
            conn, order_ref, status="filled", fill_price=fill["fill_price"]
        )
        exit_price = fill["fill_price"]

    fees = fee_for(asset_class, qty, exit_price)
    slippage_cost = abs(exit_price - current_price) * qty
    pnl = (exit_price - entry_price) * qty - fees

    ledger.close_position(
        conn,
        position["position_id"],
        exit_ts=now_iso,
        exit_price=exit_price,
        exit_reason=_REASON,
        exit_order_ref=order_ref,
        fees=fees,
        slippage_cost=slippage_cost,
        pnl=pnl,
    )
    alerts.notify(
        "fill",
        f"OWNER CLOSE: {symbol} sold {qty:g} at {exit_price:.2f} -- "
        f"pnl {pnl:+.2f} (owner order, booked as owner_close)",
    )
    return {"symbol": symbol, "qty": qty, "exit_price": exit_price, "pnl": pnl,
            "order_ref": order_ref}


def main(argv: list[str] | None = None) -> None:
    from trader.data import db

    parser = argparse.ArgumentParser(
        prog="python -m trader.paper.owner_close",
        description="Owner-ordered close of one open position (human-only).",
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--db-path", default="data/trader.db")
    args = parser.parse_args(argv)

    conn = db.get_connection(args.db_path)
    try:
        adapter = broker_ibkr.IBKRBrokerAdapter(client_id=config.ibkr_client_id() + 10)
        adapter.connect()
        try:
            print(close_position_by_symbol(conn, adapter, args.symbol))
        finally:
            adapter.disconnect()
    finally:
        conn.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
