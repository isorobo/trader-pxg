"""The guardian: the 5-minute-cadence, one-shot exit-monitoring process
(05-05-PLAN.md).

Every open paper position's locked `EXIT_PROFILE` is re-evaluated every tick
against the latest live price via `trader.backtest.exits.evaluate_exit` --
never a re-derived or loosened copy (standing rule 2). The guardian never
rests a native broker stop order: it self-computes the trigger and submits a
marketable exit order only when a condition actually fires this tick
(T-05-05). Exit order submission uses the identical persist-before-submit +
date-independent `get_unresolved_orders`/`idempotency.find_unresolved_match`
crash-recovery sequence entry_pipeline (05-06) uses (BLOCKER 1 consistency,
T-05-13).

This module also evaluates D-01's five live kill conditions every tick,
auto-retiring any strategy_config that trips one (T-05-09 -- thresholds are
read only from the frozen `config.LIVE_STRATEGY_CONFIGS`, never recomputed
from live results), evaluates Phase 4's account-level circuit breakers
against the real paper equity curve and fires a real-time alert on any new
trip (W1/W4, T-05-15 -- this is the only Phase 5 caller that feeds Phase 4's
breaker evaluation live data), and folds D-11's twice-daily heartbeat
directly into the existing tick (BLOCKER 4) -- no fourth scheduled task.

The heartbeat-due check reads ops/paper_trading.log directly (the pipe-
delimited "{iso_ts}|{entry_type}|{message}" format Plan 05-02's
`trader.paper.ops_log.append_ops_log` already writes) rather than re-touching
that module.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone

from trader.backtest import metrics
from trader.backtest.config import EXIT_PROFILE
from trader.backtest.exits import ExitResult, PositionState, evaluate_exit, next_watermark
from trader.backtest.fills import fee_for
from trader.paper import alerts, broker_crypto_sim, calendar_, config, config_store, idempotency, ledger
from trader.paper.broker_ibkr import IBKRBrokerAdapter
from trader.risk import breakers

# The same ops-log path Plan 05-02's ops_log module defaults to (documented,
# stable contract) -- the heartbeat-due check reads this file directly
# rather than re-touching trader/paper/ops_log.py.
_OPS_LOG_PATH = "ops/paper_trading.log"

_BREAKER_TYPES = ("daily_loss", "drawdown", "consecutive_loss")

# migrations/0003_backtest.sql's exit_reason CHECK <-> migrations/0005's
# paper_orders.intent CHECK -- one place these two vocabularies are mapped,
# in both directions, so they cannot silently drift apart.
_REASON_TO_INTENT = {
    "stop": "exit_stop",
    "take_profit": "exit_take_profit",
    "trailing_stop": "exit_trailing_stop",
    "scale_out": "exit_scale_out",
    "time_stop": "exit_time_stop",
    "eod_flat": "exit_eod_flat",
}
_INTENT_TO_REASON = {intent: reason for reason, intent in _REASON_TO_INTENT.items()}


# ---------------------------------------------------------------------------
# Task 1: exit evaluation + self-computed MKT exit submission
# ---------------------------------------------------------------------------


def _rebuild_exit_profile(position: dict) -> EXIT_PROFILE:
    """Rebuild the locked EXIT_PROFILE fresh from paper_positions' own
    columns every tick -- never a second source of truth (standing rule 2)."""
    return EXIT_PROFILE(
        stop_pct=position["stop_pct"],
        tp_pct=position["tp_pct"],
        scale_out=position["scale_out"],
        trailing_pct=position["trailing_pct"],
        max_hold_days=position["max_hold_days"],
        eod_flat=bool(position["eod_flat"]),
    )


def _build_bar(current_price: float) -> dict:
    """Collapse one live single-price tick into the OHLC-shaped bar
    `evaluate_exit` expects (interfaces note: its stop/tp/trailing checks
    only compare against high/low/close, all equal here)."""
    return {
        "open": current_price,
        "high": current_price,
        "low": current_price,
        "close": current_price,
        "volume": 0,
    }


def _rebuild_position_state(position: dict) -> PositionState:
    profile = _rebuild_exit_profile(position)
    return PositionState.open(profile, position["entry_price"])


def evaluate_position_exit(
    position: dict, current_price: float, as_of_date: date
) -> ExitResult | None:
    """Re-evaluate one open position's locked EXIT_PROFILE against the
    latest live price, in `trader.backtest.exits.evaluate_exit`'s exact
    D-10 locked order -- never a re-derived or loosened copy."""
    profile = _rebuild_exit_profile(position)
    pos_state = PositionState.open(profile, position["entry_price"])
    bar = _build_bar(current_price)
    days_held = (as_of_date - date.fromisoformat(position["entry_ts"][:10])).days
    return evaluate_exit(profile, pos_state, bar, days_held, position["watermark"])


def _submit_exit(
    conn,
    position: dict,
    exit_result: ExitResult,
    current_price: float,
    as_of_date: date,
    now_iso: str,
    ibkr_adapter,
    crypto_adapter,
    broker_fills: list[dict],
) -> dict | None:
    """The REVISED order-submission sequence (BLOCKER 1, mirrors
    entry_pipeline's 05-06 revised sequence exactly)."""
    strategy_id = position["strategy_id"]
    symbol = position["symbol"]
    venue = position["venue"]
    asset_class = position["asset_class"]
    qty = position["qty"]
    position_id = position["position_id"]
    entry_price = position["entry_price"]
    intent = _REASON_TO_INTENT[exit_result.reason]

    # (1)+(2): ANY date, not just today -- the date-independent crash-
    # recovery matcher (BLOCKER 1).
    unresolved = ledger.get_unresolved_orders(conn, strategy_id, symbol, "sell")
    match = idempotency.find_unresolved_match(unresolved, broker_fills)

    if match is not None:
        # (3): heal always proceeds -- there is no halt gate on exits, only
        # on entries per D-07.
        local_order = match["local_order"]
        broker_fill = match["broker_fill"]
        fill_price = broker_fill.get("fill_price", current_price)
        if local_order["status"] != "filled":
            ledger.heal_order(
                conn,
                local_order["order_ref"],
                broker_fill.get("permId"),
                fill_price,
                now_iso,
            )
        row = conn.execute(
            "SELECT status FROM paper_positions WHERE position_id = ?", (position_id,)
        ).fetchone()
        if row is not None and row[0] == "open":
            healed_qty = local_order["qty"]
            healed_reason = _INTENT_TO_REASON.get(local_order["intent"], exit_result.reason)
            fees = fee_for(asset_class, healed_qty, fill_price)
            slippage_cost = abs(fill_price - current_price) * healed_qty
            pnl = (fill_price - entry_price) * healed_qty - fees
            ledger.close_position(
                conn,
                position_id,
                exit_ts=now_iso,
                exit_price=fill_price,
                exit_reason=healed_reason,
                exit_order_ref=local_order["order_ref"],
                fees=fees,
                slippage_cost=slippage_cost,
                pnl=pnl,
            )
            alerts.notify(
                "fill", f"{symbol} exited {healed_reason} at {fill_price} (healed)"
            )
            return {
                "position_id": position_id,
                "symbol": symbol,
                "reason": healed_reason,
                "order_ref": local_order["order_ref"],
                "healed": True,
            }
        return None

    if unresolved:
        # (4): an exit for this position is already in flight from a prior
        # tick -- skip submitting another one this tick.
        return None

    # (5): only if unresolved is empty -- persist BEFORE any broker call.
    order_ref = idempotency.build_order_ref(
        strategy_id, symbol, as_of_date.isoformat(), "sell", intent
    )
    ledger.record_order(
        conn, order_ref, strategy_id, symbol, venue, "sell", intent, qty,
        status="pending_submit",
    )

    if venue == "ibkr_paper":
        broker_result = ibkr_adapter.place_order(symbol, "SELL", qty, order_ref)
        ledger.update_order_status(
            conn, order_ref, status="submitted", perm_id=broker_result["perm_id"]
        )
    else:
        fill = broker_crypto_sim.simulate_fill(symbol, "sell", qty, current_price, asset_class)
        ledger.update_order_status(
            conn, order_ref, status="filled", fill_price=fill["fill_price"]
        )

    fees = fee_for(asset_class, qty, exit_result.raw_price)
    slippage_cost = abs(exit_result.raw_price - current_price) * qty
    pnl = (exit_result.raw_price - entry_price) * qty - fees

    ledger.close_position(
        conn,
        position_id,
        exit_ts=now_iso,
        exit_price=exit_result.raw_price,
        exit_reason=exit_result.reason,
        exit_order_ref=order_ref,
        fees=fees,
        slippage_cost=slippage_cost,
        pnl=pnl,
    )
    alerts.notify("fill", f"{symbol} exited {exit_result.reason} at {exit_result.raw_price}")
    return {
        "position_id": position_id,
        "symbol": symbol,
        "reason": exit_result.reason,
        "order_ref": order_ref,
        "healed": False,
    }


# ---------------------------------------------------------------------------
# Task 2: rolling kill-condition evaluation + auto-retire
# ---------------------------------------------------------------------------


def _retire(conn, strategy_id: str, reason: str, trigger_value, retired: list[dict]) -> None:
    ledger.retire_strategy(conn, strategy_id, reason, trigger_value)
    alerts.notify("error", f"{strategy_id} retired: {reason} (trigger={trigger_value})")
    retired.append({"strategy_id": strategy_id, "reason": reason, "trigger_value": trigger_value})


def evaluate_kill_conditions(conn) -> list[dict]:
    """D-01's live kill conditions, evaluated every tick. Thresholds are
    read only from the pre-registered registry rows (T-05-09, seeded
    verbatim from the frozen configs by migration 0006) -- never recomputed
    from live results. Retired strategy_configs are never re-evaluated
    (their open positions stay exit-managed regardless).

    Phase 7 identity fix: everything here keys on ``cfg.profile_name``, the
    identity trades and positions are actually recorded under
    (entry_pipeline passes profile_name to open_position; close_position
    copies it into paper_trades.strategy_id). The pre-Phase-7 code keyed on
    ``cfg.strategy_id`` ("momentum_stock", shared by all five configs),
    which matches zero paper_trades rows -- so the rolling-30 window never
    filled and no kill condition could ever trip. Plumbing fix only; every
    threshold is unchanged (standing rule 1 untouched).
    """
    retired: list[dict] = []
    for cfg in config_store.get_live_configs(conn):
        if ledger.is_strategy_retired(conn, cfg.profile_name):
            continue

        trades = ledger.get_recent_trades(conn, cfg.profile_name, limit=30)
        if len(trades) < 30:
            # KILL-CONDITIONS.md's rolling-30-trade window is not yet full.
            continue

        pnls = [t["pnl"] for t in trades]  # DESC order (most recent first)

        pf = metrics.profit_factor(pnls)
        if pf is not None and pf < cfg.pf_floor:
            _retire(conn, cfg.profile_name, "profit_factor_floor", pf, retired)
            continue

        chronological_pnls = list(reversed(pnls))
        equity_curve: list[float] = []
        running = 0.0
        for pnl in chronological_pnls:
            running += pnl
            equity_curve.append(running)
        dd = metrics.max_drawdown(equity_curve)
        if dd is not None and dd <= cfg.max_dd_kill:
            _retire(conn, cfg.profile_name, "max_drawdown", dd, retired)
            continue

        # Mirrors trader.risk.breakers.evaluate_breakers's exact
        # reversed-iteration-until-non-negative logic -- intentional
        # duplication (this counts per-strategy_config trades, not the
        # account-level trade_pnls breakers.py consumes). pnls is already
        # DESC (most-recent-first), so no further reversal is needed here.
        consecutive_losses = 0
        for pnl in pnls:
            if pnl < 0:
                consecutive_losses += 1
            else:
                break
        if consecutive_losses >= cfg.consecutive_loss_kill:
            _retire(conn, cfg.profile_name, "consecutive_losses", consecutive_losses, retired)
            continue

    return retired


# ---------------------------------------------------------------------------
# Task 3: account-level breaker evaluation with real-time alert + heartbeat
# ---------------------------------------------------------------------------


def _get_all_trades_chronological(conn) -> list[dict]:
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    rows = cursor.execute("SELECT * FROM paper_trades ORDER BY exit_ts ASC").fetchall()
    return [dict(row) for row in rows]


def evaluate_account_breakers(conn) -> dict:
    """W1/W4: the missing wiring that gives `is_entry_halted`'s Phase-4-
    breaker check real data to read. Fires a real-time alert on any fresh
    normal->trip transition -- not just an ops-log line."""
    trades = _get_all_trades_chronological(conn)
    pnls = [t["pnl"] for t in trades]

    equity_curve = [config.PAPER_ACCOUNT_EQUITY]
    running = config.PAPER_ACCOUNT_EQUITY
    for pnl in pnls:
        running += pnl
        equity_curve.append(running)

    previous_state = breakers.read_breaker_state(conn)
    evaluation = breakers.evaluate_breakers(equity_curve, pnls)

    for breaker_type in _BREAKER_TYPES:
        was_tripped = previous_state[breaker_type]["current_action"] == "trip"
        now_tripped = evaluation[f"{breaker_type}_tripped"]
        if not was_tripped and now_tripped:
            value = evaluation.get(f"{breaker_type}_value")
            if value is None:
                value = evaluation.get("consecutive_loss_count")
            alerts.notify("error", f"breaker {breaker_type} TRIPPED (value={value})")

    # The actual persistence -- called for the first time anywhere in
    # Phase 5, fired AFTER the alert above so the alert always reflects a
    # transition this exact call is about to persist, never a stale one.
    breakers.record_breaker_transitions(conn, previous_state, evaluation)
    return evaluation


def _heartbeat_due(log_path: str, now: datetime) -> bool:
    """True iff at least 12 hours have elapsed since the last 'heartbeat'
    ops-log entry (BLOCKER 4) -- a missing file is treated as "due"."""
    if not os.path.exists(log_path):
        return True

    latest: datetime | None = None
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("|", 2)
            if len(parts) != 3:
                continue
            ts_str, entry_type, _message = parts
            if entry_type != "heartbeat":
                continue
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                continue
            if latest is None or ts > latest:
                latest = ts

    if latest is None:
        return True
    return (now - latest) >= timedelta(hours=12)


def run_guardian_once(
    conn,
    ibkr_adapter,
    crypto_adapter=None,
    now: datetime | None = None,
    log_path: str = _OPS_LOG_PATH,
) -> dict:
    """One guardian tick (D-05, no daemon mode): re-evaluate every open
    position's exit, evaluate Phase 4's account-level breakers, evaluate
    D-01's kill conditions, and fire a heartbeat if due (BLOCKER 4)."""
    if now is None:
        now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    as_of_date = now.date()

    open_positions = ledger.get_open_positions(conn)

    if _heartbeat_due(log_path, now):
        alerts.notify(
            "heartbeat", f"guardian alive: {len(open_positions)} open positions"
        )

    # Fetched once per run, reused for both the same-tick fast path and the
    # crash-recovery path.
    broker_fills = ibkr_adapter.snapshot()["fills"]

    exits: list[dict] = []
    for position in open_positions:
        symbol = position["symbol"]
        venue = position["venue"]

        if venue == "ibkr_paper":
            if not calendar_.is_trading_day(as_of_date):
                # The stock leg only trades during NYSE sessions; the
                # crypto_sim leg below always processes regardless (D-05).
                continue
            current_price = ibkr_adapter.latest_price(symbol)
        else:
            current_price = broker_crypto_sim.fetch_price(symbol, crypto_adapter)

        exit_result = evaluate_position_exit(position, current_price, as_of_date)
        if exit_result is None:
            pos_state = _rebuild_position_state(position)
            bar = _build_bar(current_price)
            new_watermark = next_watermark(pos_state, position["watermark"], bar)
            ledger.update_watermark(conn, position["position_id"], new_watermark)
            continue

        outcome = _submit_exit(
            conn,
            position,
            exit_result,
            current_price,
            as_of_date,
            now_iso,
            ibkr_adapter,
            crypto_adapter,
            broker_fills,
        )
        if outcome is not None:
            exits.append(outcome)

    # Both run every tick regardless of whether any exit fired this tick
    # (order between the two is not load-bearing).
    evaluate_account_breakers(conn)
    evaluate_kill_conditions(conn)

    return {"exits": exits, "ticked": len(open_positions)}


def main(argv: list[str] | None = None) -> None:
    """``python -m trader.paper.guardian --once`` (D-05: no daemon mode)."""
    from trader.data import db

    parser = argparse.ArgumentParser(
        prog="python -m trader.paper.guardian",
        description="Run the paper-trading guardian's exit-monitoring tick once (D-05).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        required=True,
        help="Run a single guardian tick and exit. Required: no daemon mode.",
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
        ibkr_adapter = IBKRBrokerAdapter()
        ibkr_adapter.connect()
        try:
            summary = run_guardian_once(conn, ibkr_adapter)
            print(summary)
        finally:
            # Explicit disconnect so the live socket never keeps the
            # interpreter alive after the --once pass (2026-07-30).
            ibkr_adapter.disconnect()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
