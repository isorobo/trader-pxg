"""The crypto-sim entry pipeline (CRYPTO-PAPER-LEG-PLAN.md, owner-approved
2026-07-30).

Mirrors the stock entry pipeline's decide -> persist -> fill -> ledger
sequence with the crypto differences the plan pre-registered:

- Runs EVERY day (crypto trades 24/7) -- no trading-day gate.
- Fills are SIMULATED (broker_crypto_sim.simulate_fill, D-04: the crypto
  leg never places a real order) and synchronous, so there is no broker to
  diverge from and no STEP 0/1 heal pass -- the order row is persisted
  'pending_submit' BEFORE the fill is simulated (crash between the two
  leaves a visible pending row, surfaced by ops, never a silent gap).
- Gracefully SKIPS (with an ops-log line) when the registry has no live
  crypto-bucket families -- the expected state until a crypto survivor is
  registered; never the stock pipeline's all-retired RuntimeError.
- Shares the same gate, sizer, halt gate, PAPER_ACCOUNT_EQUITY budget, and
  probation multiplier as the stock leg; open positions from BOTH venues
  count against the shared budget.

Family -> bucket resolution: a live strategy_id "{base}_{bucket}" whose
bucket suffix names a crypto universe bucket belongs to this leg.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from trader.backtest.config import SLIPPAGE_PCT
from trader.backtest.iterator import PointInTimeIterator
from trader.backtest.strategies.momentum_v2 import _rsi_wilder
from trader.backtest.universe import (
    BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
    BUCKET_NEW_MEMECOIN,
    UNIVERSE_BY_BUCKET,
)
from trader.data.api import get_daily_bars
from trader.paper import (
    alerts,
    broker_crypto_sim,
    config,
    config_store,
    idempotency,
    ledger,
    ops_log,
    reconcile,
    signals,
)
from trader.paper.entry_pipeline import assign_exit_profile
from trader.risk import gate, sizer
from trader.tournament import frozen_config as tournament_frozen_config

_ENTRY_SIDE = "buy"
_ENTRY_INTENT = "entry"
_ENTRY_VENUE = "crypto_sim"

_CRYPTO_BUCKETS = (BUCKET_CRYPTO_MAJOR_LEGACY_MEME, BUCKET_NEW_MEMECOIN)

# bucket -> paper_positions/paper_trades asset_class value (mirrors the
# fee/slippage tables' own keys).
_BUCKET_ASSET_CLASS = {
    BUCKET_CRYPTO_MAJOR_LEGACY_MEME: "crypto_major",
    BUCKET_NEW_MEMECOIN: "memecoin",
}


def _bucket_of(strategy_id: str) -> str | None:
    for bucket in _CRYPTO_BUCKETS:
        if strategy_id.endswith(f"_{bucket}"):
            return bucket
    return None


def _live_crypto_families(conn) -> dict[str, dict]:
    """Live crypto-bucket families: strategy_id -> {"bucket", "variants":
    {entry_variant}, "profiles": [profile_name, ...]}."""
    families: dict[str, dict] = {}
    for cfg in config_store.get_live_configs(conn):
        bucket = _bucket_of(cfg.strategy_id)
        if bucket is None:
            continue
        if ledger.is_strategy_retired(conn, cfg.profile_name):
            continue
        entry = families.setdefault(
            cfg.strategy_id,
            {"bucket": bucket, "variants": set(), "profiles": []},
        )
        entry["variants"].add(cfg.entry_variant)
        entry["profiles"].append(cfg.profile_name)
    return families


def scan_crypto_candidates(conn, families: dict[str, dict], as_of_date: date) -> list[dict]:
    """One scan per (family, variant), bars bounded to yesterday (same
    D-05 discipline as stock). Sorted-family first-claim dedupe, RSI(14)
    score -- both identical to the stock leg's pre-registered rules."""
    yesterday = as_of_date - timedelta(days=1)
    open_symbols = {p["symbol"] for p in ledger.get_open_positions(conn)}

    candidates: list[dict] = []
    claimed: set[str] = set()
    bars_by_bucket: dict[str, dict] = {}
    for strategy_id in sorted(families):
        info = families[strategy_id]
        bucket = info["bucket"]
        if bucket not in bars_by_bucket:
            bars_by_bucket[bucket] = {
                symbol: get_daily_bars(symbol, end=str(yesterday), conn=conn)
                for symbol in UNIVERSE_BY_BUCKET[bucket]
            }
        iterator = PointInTimeIterator(bars_by_bucket[bucket])
        iterator.advance_to(yesterday)

        for entry_variant in sorted(info["variants"]):
            pick_entries = signals.pick_entries_for(strategy_id, entry_variant)
            import random as _random

            fired = pick_entries(
                iterator, pd.Timestamp(yesterday), open_symbols, _random.Random(0)
            )
            for symbol in fired:
                if symbol in claimed:
                    continue
                claimed.add(symbol)
                df = bars_by_bucket[bucket][symbol]
                # ts-bearing bar dicts: the risk gate's correlation window
                # is date-indexed (same shape the stock leg feeds it).
                bars_dicts = [
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
                candidates.append(
                    {
                        "symbol": symbol,
                        "venue": _ENTRY_VENUE,
                        "score": _rsi_wilder(df["close"].to_numpy()),
                        "volatility": sizer.compute_volatility(bars_dicts),
                        "family": strategy_id,
                        "bucket": bucket,
                        "bars_dicts": bars_dicts,
                    }
                )
    return candidates


def run_crypto_entry_once(conn, price_fetcher=None, as_of_date: date | None = None) -> dict:
    """The ``--once`` CLI body. ``price_fetcher(symbol) -> float`` is the
    test seam; production resolves broker_crypto_sim.fetch_price."""
    as_of_date = as_of_date or date.today()
    if price_fetcher is None:
        price_fetcher = broker_crypto_sim.fetch_price

    families = _live_crypto_families(conn)
    if not families:
        ops_log.append_ops_log(
            "scheduled_run",
            f"crypto entry {as_of_date}: no live crypto families -- skipped",
        )
        return {"skipped": "no_live_crypto_families"}

    candidates = scan_crypto_candidates(conn, families, as_of_date)
    if not candidates:
        ops_log.append_ops_log(
            "scheduled_run", f"crypto entry {as_of_date}: 0 candidates"
        )
        return {"candidates": 0, "submitted": []}

    market_data = {
        (c["symbol"], c["venue"]): {
            "bars": c["bars_dicts"],
            "asset_class": _BUCKET_ASSET_CLASS[c["bucket"]],
            "spread_pct": SLIPPAGE_PCT[_BUCKET_ASSET_CLASS[c["bucket"]]],
        }
        for c in candidates
    }
    accepted, _rejected = gate.apply_risk_gate(
        [{k: v for k, v in c.items() if k != "bars_dicts"} for c in candidates],
        market_data,
    )

    live_configs_by_name = config_store.get_live_configs_by_profile_name(conn)
    family_by_symbol = {c["symbol"]: c["family"] for c in candidates}
    bucket_by_symbol = {c["symbol"]: c["bucket"] for c in candidates}

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
    for position in sized["positions"]:
        symbol = position["symbol"]
        family = family_by_symbol[symbol]
        profile_name = assign_exit_profile(symbol, families[family]["profiles"])
        cfg = live_configs_by_name[profile_name]
        multiplier = (
            tournament_frozen_config.PROBATION_SIZE_MULTIPLIER
            if cfg.state == "probation"
            else 1.0
        )
        dollar_amount = position["weight"] * config.PAPER_ACCOUNT_EQUITY * multiplier

        # Still-in-flight / already-entered-today guard (idempotent refs).
        unresolved = ledger.get_unresolved_orders(conn, profile_name, symbol, _ENTRY_SIDE)
        if unresolved:
            continue
        if reconcile.is_entry_halted(conn):
            continue

        reference_price = price_fetcher(symbol)
        # Crypto supports fractional quantities -- no whole-share rounding.
        qty = dollar_amount / reference_price
        if qty <= 0:
            continue

        asset_class = _BUCKET_ASSET_CLASS[bucket_by_symbol[symbol]]
        order_ref = idempotency.build_order_ref(
            profile_name, symbol, as_of_date.isoformat(), _ENTRY_SIDE, _ENTRY_INTENT
        )
        ledger.record_order(
            conn, order_ref, profile_name, symbol, _ENTRY_VENUE, _ENTRY_SIDE,
            _ENTRY_INTENT, qty, status="pending_submit",
        )
        fill = broker_crypto_sim.simulate_fill(
            symbol, _ENTRY_SIDE, qty, reference_price, asset_class
        )
        ledger.update_order_status(conn, order_ref, status="filled")
        ledger.open_position(
            conn, profile_name, symbol, _ENTRY_VENUE, asset_class, qty,
            fill["fill_price"], datetime.now(timezone.utc).isoformat(),
            order_ref, cfg.exit_profile,
        )
        alerts.notify(
            "fill", f"{symbol} crypto-sim entered {qty:.6f} under {profile_name}"
        )
        submitted.append(order_ref)

    ops_log.append_ops_log(
        "scheduled_run",
        f"crypto entry {as_of_date}: {len(candidates)} candidates, "
        f"{len(accepted)} accepted, {len(submitted)} filled(sim)",
    )
    return {"candidates": len(candidates), "accepted": len(accepted), "submitted": submitted}


def main(argv: list[str] | None = None) -> None:
    from trader.data import db

    parser = argparse.ArgumentParser(
        prog="python -m trader.paper.crypto_entry_pipeline",
        description="Run the crypto-sim entry pipeline once.",
    )
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--db-path", default="data/trader.db")
    args = parser.parse_args(argv)
    if not args.once:
        print("Usage error: --once is required.", file=sys.stderr)
        sys.exit(2)

    conn = db.get_connection(args.db_path)
    try:
        print(run_crypto_entry_once(conn))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
