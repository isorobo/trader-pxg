"""Wires the live entry pipeline (05-06-PLAN.md, PAPER-01): on each trading
day shortly after US open, scan the frozen 18-symbol stock universe with the
momentum_stock/loose signal (D-01/D-02/D-14), run Phase 4's risk gate and
sizer completely unmodified (D-08 -- no bypass path exists), round the
sizer's dollar output down to whole shares (Pitfall 2), and assign each new
position one of the five live exit-profile configs via a hash keyed on
SYMBOL ALONE (RESIDUAL BLOCKER 1 -- no date component; see
``assign_exit_profile``'s own docstring for the full rationale).

Every invocation first runs an UNSCOPED STEP 0 heal pass over every
unresolved local order in the whole table (``ledger.get_all_unresolved_orders``,
no strategy_id/symbol filter) BEFORE candidate scanning, BEFORE the
trading-day check, and BEFORE the halt gate (RESIDUAL BLOCKER 1) -- a
crash-orphaned order is healed even when its own symbol never fires a
fresh signal again. The narrower per-candidate heal check (STEP 1) is kept
as a second, defensive layer for whatever fires fresh today. Only after
STEP 0, STEP 1 (per-candidate heal), STEP 2 (still-in-flight check), and
STEP 3 (the combined Phase-4-breaker + reconciliation halt gate,
``reconcile.is_entry_halted``) all resolve does STEP 4 persist a brand-new
``pending_submit`` order BEFORE STEP 5 ever calls the broker (BLOCKER 1).

Standing rule 6 (real money is Phase 9): this module only ever submits
through ``trader.paper.broker_ibkr.IBKRBrokerAdapter``, which itself refuses
to connect anywhere but the paper port.
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from trader.backtest.config import SLIPPAGE_PCT
from trader.backtest.iterator import PointInTimeIterator
from trader.backtest.strategies.momentum_v2 import (
    MOMENTUM_VARIANTS,
    _rsi_wilder,
    make_pick_entries,
)
from trader.backtest.universe import STOCK_UNIVERSE
from trader.data.api import get_daily_bars
from trader.paper import alerts, calendar_, config, config_store, idempotency, ledger, ops_log, reconcile
from trader.paper import broker_ibkr
from trader.risk import gate, sizer
from trader.tournament import frozen_config as tournament_frozen_config

_ENTRY_SIDE = "buy"
_ENTRY_INTENT = "entry"
_ENTRY_VENUE = "ibkr_paper"
_ROUTING_VENUE = "smart"  # IBKR's SMART routing venue string, not a DB venue value.
_ASSET_CLASS_STOCK = "stock"


# ---------------------------------------------------------------------------
# Task 1: candidate scan, score, gate, day-stable symbol-only profile assign
# ---------------------------------------------------------------------------


def _history_to_bar_dicts(history) -> list[dict]:
    """Convert a ``PointInTimeIterator.history(symbol)`` numpy array
    (columns open/high/low/close/volume, point-in-time bounded) into the
    ``list[dict]`` shape ``trader.risk.sizer.compute_volatility`` requires.
    No ``ts`` field -- ``compute_volatility`` only ever reads ``close``."""
    return [
        {
            "open": float(row[0]),
            "high": float(row[1]),
            "low": float(row[2]),
            "close": float(row[3]),
            "volume": float(row[4]),
        }
        for row in history
    ]


def _bars_as_dicts(conn, symbol: str, as_of_date: date) -> list[dict]:
    """Fetch ``symbol``'s bars up to (not including) ``as_of_date`` and
    shape them into the ``list[dict]`` (``ts``/``open``/``high``/``low``/
    ``close``/``volume``) contract ``trader.risk.gate.apply_risk_gate``
    requires for its correlation/liquidity checks -- unlike
    ``_history_to_bar_dicts``, this includes ``ts`` (needed for the gate's
    date-indexed correlation window)."""
    yesterday = as_of_date - timedelta(days=1)
    df = get_daily_bars(symbol, end=str(yesterday), asset_class=_ASSET_CLASS_STOCK, conn=conn)
    cutoff = pd.Timestamp(yesterday, tz="UTC")
    df = df[df.index <= cutoff]
    return [
        {
            "ts": ts.date().isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        for ts, row in df.iterrows()
    ]


def scan_candidates(conn, as_of_date: date) -> list[dict]:
    """Scan the frozen 18-symbol stock universe for a fresh loose-momentum
    entry signal (D-01/D-02/D-14), using only bars up to (not including)
    ``as_of_date`` (D-05: yesterday's close, since today's own close is not
    yet known shortly after today's open).

    Returns one candidate dict per fired symbol: ``{"symbol", "venue",
    "score", "volatility"}``. A symbol already in ``open_positions`` (any
    strategy_id) never re-fires as a new candidate this run --
    ``make_pick_entries``'s own ``pick_entries`` closure enforces this via
    its ``open_positions`` argument.
    """
    yesterday = as_of_date - timedelta(days=1)
    bars_by_symbol = {
        symbol: get_daily_bars(
            symbol, end=str(yesterday), asset_class=_ASSET_CLASS_STOCK, conn=conn
        )
        for symbol in STOCK_UNIVERSE
    }
    iterator = PointInTimeIterator(bars_by_symbol)
    iterator.advance_to(yesterday)

    open_symbols = {p["symbol"] for p in ledger.get_open_positions(conn)}
    pick_entries = make_pick_entries(MOMENTUM_VARIANTS["loose"])
    # rng is seeded deterministically -- the loose variant's own signal
    # logic never actually consumes rng, but the shared 4-arg
    # pick_entries(iterator, date, open_positions, rng) contract requires
    # passing one.
    fired = pick_entries(iterator, pd.Timestamp(yesterday), open_symbols, random.Random(0))

    candidates: list[dict] = []
    for symbol in fired:
        history = iterator.history(symbol)
        closes = history[:, 3]
        rsi = _rsi_wilder(closes)
        volatility = sizer.compute_volatility(_history_to_bar_dicts(history))
        candidates.append(
            {
                "symbol": symbol,
                "venue": _ROUTING_VENUE,
                "score": rsi,
                "volatility": volatility,
            }
        )
    return candidates


def assign_exit_profile(symbol: str, live_profile_names: list[str]) -> str:
    """Deterministic, SYMBOL-ONLY exit-profile assignment (REVISED,
    RESIDUAL BLOCKER 1 -- no ``as_of_date`` parameter at all).

    Heal correctness requires day-stable identity -- a crash-orphaned order
    is looked up on a LATER day by (strategy_id, symbol, side); if
    strategy_id were re-derived from a date-hash, the day-2 recomputation
    would pick a different one of the five live profiles 4 times out of 5,
    and get_unresolved_orders (filtered by strategy_id) would find nothing
    for the actual order that was placed. Hashing on symbol alone means the
    SAME strategy_id is always assigned to a given symbol, on any day, for
    as long as that profile stays live -- this is what the STEP 0 heal pass
    (and the narrower per-candidate check) depend on to ever find a match.
    Profile spread across the sizer's typically-small number of concurrent
    candidates is still preserved, because the hash spreads across the
    18-symbol STOCK_UNIVERSE, not across a single symbol repeated on
    different days -- there was never a meaningful "spread over time for
    one symbol" property to preserve, only "spread over symbols", and that
    survives removing the date term entirely.
    """
    names = sorted(live_profile_names)
    index = int(hashlib.sha256(symbol.encode()).hexdigest(), 16) % len(names)
    return names[index]


def _live_profile_names(conn) -> list[str]:
    """The profile_names of every live (non-retired) strategy_config, read
    from the strategy_registry via config_store (Phase 7, D-08 -- the
    registry already excludes retired/candidate rows; the
    is_strategy_retired check stays as defence in depth, both systems must
    agree a config is live).

    Raises RuntimeError, not a silent empty return, when no live config
    remains -- a T-05-11-shaped visibility gap otherwise (this process
    would silently enter zero positions forever without ever surfacing
    why).
    """
    names = [
        cfg.profile_name
        for cfg in config_store.get_live_configs(conn)
        if not ledger.is_strategy_retired(conn, cfg.profile_name)
    ]
    if not names:
        raise RuntimeError(
            "every live strategy config is retired -- nothing left to trade"
        )
    return names


# ---------------------------------------------------------------------------
# Task 2: STEP0 heal -> gate -> sizer -> round -> per-candidate heal ->
# halt-gate -> persist-then-submit -> ledger -> alert
# ---------------------------------------------------------------------------


def _has_open_position_for_order_ref(conn, order_ref: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM paper_positions WHERE entry_order_ref = ? AND status = 'open'",
        (order_ref,),
    ).fetchone()
    return row is not None


def _run_step0_heal_pass(conn, ibkr_adapter, broker_fills: list[dict]) -> list[str]:
    """STEP 0 (NEW, RESIDUAL BLOCKER 1): an UNSCOPED pass over EVERY
    unresolved local order, run once per invocation, before candidate
    scanning, before the trading-day check, and before the halt gate --
    the fix for "the heal only ran inside the fresh-candidate loop, so
    orphans whose signal does not re-fire were never checked."

    Only entry orders are healed here -- an orphaned EXIT order is the
    guardian's own concern (guardian.py's identical persist-before-submit +
    get_unresolved_orders sequence, Plan 05-05); this pipeline never calls
    close_position and must not try to.
    """
    healed_this_run: list[str] = []
    live_configs_by_name = config_store.get_live_configs_by_profile_name(conn)
    for local_order in ledger.get_all_unresolved_orders(conn):
        if local_order["intent"] != _ENTRY_INTENT:
            continue

        match = idempotency.find_unresolved_match([local_order], broker_fills)
        if match is None:
            # Still genuinely in flight, or the broker truly has no record
            # of it yet -- leave it for a later run.
            continue

        strategy_id = local_order["strategy_id"]
        symbol = local_order["symbol"]
        cfg = live_configs_by_name.get(strategy_id)
        if cfg is None:
            # A retired/unknown strategy_id -- do not open a position under
            # a config this process no longer recognizes.
            ops_log.append_ops_log(
                "error",
                f"STEP0: order {local_order['order_ref']} references unknown/retired "
                f"strategy_id {strategy_id!r} -- skipped, not opened as a position",
            )
            continue

        broker_fill = match["broker_fill"]
        if local_order["status"] != "filled":
            ledger.heal_order(
                conn,
                local_order["order_ref"],
                broker_fill.get("permId"),
                broker_fill.get("fill_price"),
                datetime.now(timezone.utc).isoformat(),
            )

        if not _has_open_position_for_order_ref(conn, local_order["order_ref"]):
            # STEP 0 has no "current candidate price" context the way the
            # per-candidate loop does -- fall back to the broker's own fill
            # price, or a live quote if the fill carried none.
            healing_price = broker_fill.get("fill_price")
            if healing_price is None:
                healing_price = ibkr_adapter.latest_price(symbol)
            ledger.open_position(
                conn,
                strategy_id,
                symbol,
                _ENTRY_VENUE,
                _ASSET_CLASS_STOCK,
                local_order["qty"],
                healing_price,
                datetime.now(timezone.utc).isoformat(),
                local_order["order_ref"],
                cfg.exit_profile,
            )

        alerts.notify(
            "fill",
            f"{symbol} healed via STEP 0 from a crash-orphaned fill under {strategy_id}",
        )
        healed_this_run.append(local_order["order_ref"])

    return healed_this_run


def run_entry_pipeline_once(conn, ibkr_adapter, as_of_date: date | None = None) -> dict:
    """The ``--once`` CLI body (D-05, no daemon mode).

    Fetches ``ibkr_adapter.snapshot()["fills"]`` exactly once, at the very
    top, before anything else -- reused by both STEP 0 and the
    per-candidate heal check (STEP 1) below.
    """
    as_of_date = as_of_date or date.today()
    broker_fills = ibkr_adapter.snapshot()["fills"]

    # STEP 0 -- unconditional, unscoped heal pass. Runs BEFORE the
    # trading-day check and BEFORE the halt gate: crash recovery must not
    # wait for the next trading day, and healing is never gated by a halt
    # (BLOCKER 1 / RESIDUAL BLOCKER 1).
    healed_this_run = _run_step0_heal_pass(conn, ibkr_adapter, broker_fills)

    if not calendar_.is_trading_day(as_of_date):
        ops_log.append_ops_log(
            "scheduled_run",
            f"entry pipeline {as_of_date}: not a trading day, "
            f"{len(healed_this_run)} healed via STEP 0",
        )
        return {"skipped": "not_a_trading_day", "healed": healed_this_run}

    candidates = scan_candidates(conn, as_of_date)
    if not candidates:
        ops_log.append_ops_log(
            "scheduled_run",
            f"entry pipeline {as_of_date}: 0 candidates, "
            f"{len(healed_this_run)} healed via STEP 0",
        )
        return {"candidates": 0, "healed": healed_this_run}

    market_data = {
        (c["symbol"], c["venue"]): {
            "bars": _bars_as_dicts(conn, c["symbol"], as_of_date),
            "asset_class": _ASSET_CLASS_STOCK,
            # Reuses the stock slippage constant as its spread proxy,
            # exactly as trader/risk/config.py's own MAX_SPREAD_PCT already
            # does -- never a new literal here.
            "spread_pct": SLIPPAGE_PCT[_ASSET_CLASS_STOCK],
        }
        for c in candidates
    }
    accepted, rejected = gate.apply_risk_gate(candidates, market_data)

    # Raises RuntimeError if every live config has been retired -- always
    # called once real candidates exist this run (T-05-11).
    live_profile_names = _live_profile_names(conn)
    live_configs_by_name = config_store.get_live_configs_by_profile_name(conn)

    open_positions_for_sizer = [
        {
            "symbol": p["symbol"],
            "venue": p["venue"],
            "asset_class": p["asset_class"],
            "weight": (p["qty"] * p["entry_price"]) / config.PAPER_ACCOUNT_EQUITY,
        }
        for p in ledger.get_open_positions(conn)
    ]
    sized = sizer.size_positions(accepted, config.PAPER_ACCOUNT_EQUITY, open_positions_for_sizer)

    submitted: list[str] = []

    # REVISED per-position sequence -- this exact order is load-bearing
    # and must not be reshuffled (D-08 no-bypass-path, BLOCKER 1).
    for position in sized["positions"]:
        # Phase 7 (D-04): profile_name/cfg resolve BEFORE dollar_amount so
        # probation-state configs can be sized at the frozen 25% multiplier.
        # assign_exit_profile needs only symbol + live_profile_names, both
        # already known here -- the symbol-only hash assignment is
        # unchanged. Heal paths (STEP 0 above, STEP 1 below) never apply
        # the multiplier: they reconstruct an already-placed order's qty
        # verbatim (07-RESEARCH.md Pitfall 3).
        profile_name = assign_exit_profile(position["symbol"], live_profile_names)
        cfg = live_configs_by_name[profile_name]
        multiplier = (
            tournament_frozen_config.PROBATION_SIZE_MULTIPLIER
            if cfg.state == "probation"
            else 1.0
        )
        dollar_amount = position["weight"] * config.PAPER_ACCOUNT_EQUITY * multiplier
        price = market_data[(position["symbol"], position["venue"])]["bars"][-1]["close"]
        qty = broker_ibkr.round_shares_down(dollar_amount, price)
        if qty <= 0:
            continue

        # STEP 1 (per-candidate heal check, defensive second layer): ANY
        # date, not just today -- nearly always a no-op for anything STEP 0
        # already healed (STEP 0 already flipped that order's status to
        # 'filled', and this SCOPED query only returns
        # 'pending_submit'/'submitted' rows).
        unresolved = ledger.get_unresolved_orders(
            conn, profile_name, position["symbol"], _ENTRY_SIDE
        )
        match = idempotency.find_unresolved_match(unresolved, broker_fills)
        if match is not None:
            local_order = match["local_order"]
            broker_fill = match["broker_fill"]
            fill_price = broker_fill.get("fill_price", price)
            if local_order["status"] != "filled":
                ledger.heal_order(
                    conn,
                    local_order["order_ref"],
                    broker_fill.get("permId"),
                    fill_price,
                    datetime.now(timezone.utc).isoformat(),
                )
            if not _has_open_position_for_order_ref(conn, local_order["order_ref"]):
                ledger.open_position(
                    conn,
                    profile_name,
                    position["symbol"],
                    _ENTRY_VENUE,
                    _ASSET_CLASS_STOCK,
                    local_order["qty"],
                    price,
                    datetime.now(timezone.utc).isoformat(),
                    local_order["order_ref"],
                    cfg.exit_profile,
                )
            alerts.notify(
                "fill",
                f"{position['symbol']} healed from a crash-orphaned fill under {profile_name}",
            )
            # Heal always proceeds, halted or not -- move to the next
            # position rather than falling through to the halt gate below.
            continue

        # STEP 2 (still-in-flight check): an order for this (strategy_id,
        # symbol, side) is already pending/submitted with no confirmed
        # broker fill yet -- skip creating ANOTHER order this run.
        if unresolved:
            continue

        # STEP 3 (halt gate -- ONLY reached when unresolved is empty, i.e.
        # no local trace of any order for this tuple exists yet). No NEW
        # submission while halted (D-07) -- but STEP 0 and STEP 1 above
        # already ran unconditionally before this check.
        if reconcile.is_entry_halted(conn):
            continue

        # STEP 4 (persist BEFORE submit, BLOCKER 1): written to the local
        # DB before the broker call, so ANY crash from this point forward
        # leaves a local trace a later run's get_unresolved_orders /
        # get_all_unresolved_orders will find.
        order_ref = idempotency.build_order_ref(
            profile_name, position["symbol"], as_of_date.isoformat(), _ENTRY_SIDE, _ENTRY_INTENT
        )
        ledger.record_order(
            conn,
            order_ref,
            profile_name,
            position["symbol"],
            _ENTRY_VENUE,
            _ENTRY_SIDE,
            _ENTRY_INTENT,
            qty,
            status="pending_submit",
        )

        # STEP 5 (the broker call + finalize).
        result = ibkr_adapter.place_order(position["symbol"], "BUY", qty, order_ref)
        ledger.update_order_status(
            conn, order_ref, status="submitted", perm_id=result["perm_id"]
        )
        ledger.open_position(
            conn,
            profile_name,
            position["symbol"],
            _ENTRY_VENUE,
            _ASSET_CLASS_STOCK,
            qty,
            price,
            datetime.now(timezone.utc).isoformat(),
            order_ref,
            cfg.exit_profile,
        )
        alerts.notify(
            "fill", f"{position['symbol']} entered {qty} shares under {profile_name}"
        )
        submitted.append(order_ref)

    halted_now = reconcile.is_entry_halted(conn)
    ops_log.append_ops_log(
        "scheduled_run",
        f"entry pipeline {as_of_date}: {len(candidates)} candidates, "
        f"{len(accepted)} accepted, {len(submitted)} submitted, "
        f"{len(healed_this_run)} healed via STEP 0, halted={halted_now}",
    )
    return {
        "candidates": len(candidates),
        "accepted": len(accepted),
        "submitted": submitted,
        "healed": healed_this_run,
        "halted": halted_now,
    }


def main(argv: list[str] | None = None) -> None:
    """``python -m trader.paper.entry_pipeline --once`` (D-05: no daemon
    mode)."""
    from trader.data import db
    from trader.paper.broker_ibkr import IBKRBrokerAdapter

    parser = argparse.ArgumentParser(
        prog="python -m trader.paper.entry_pipeline",
        description="Run the paper-trading entry pipeline once (D-05/PAPER-01).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        required=True,
        help="Run a single entry pass and exit. Required: no daemon mode.",
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
        summary = run_entry_pipeline_once(conn, ibkr_adapter)
        print(summary)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
