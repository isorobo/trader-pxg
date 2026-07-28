"""The Phase 6 graduation checklist evaluator (06-01-PLAN.md).

Runs the five frozen checks (trader/graduation/frozen_checklist.py) over a
strategy's FULL closed-trade history from the paper ledger -- read-only on
every table except its own append-only graduation_reviews audit log.

Verdicts are ADVISORY: graduation to real money (Phase 9) is a human
decision made on this module's report. Nothing here changes registry state,
sizing, or kill state (06-CONTEXT.md D-06/D-07).

Market-condition bucketing (D-03, pre-registered): a stock trade's exit
date is matched against the frozen regimes_v2 stock windows (tune or OOS)
first; dates outside every window bucket by SPY close vs its 50-day mean
("risk_on"/"risk_off"). Non-stock trades match the crypto windows; outside
them they bucket "unknown". "unknown" never counts toward the profitable-
conditions total -- missing data is never evidence.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from trader.backtest import metrics
from trader.backtest.regimes_v2 import REGIMES_V2
from trader.backtest.universe import (
    BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
    BUCKET_NEW_MEMECOIN,
    BUCKET_STOCK,
)
from trader.data.api import get_daily_bars
from trader.graduation import freeze_gate, frozen_checklist
from trader.paper import config, config_store

_ASSET_CLASS_TO_BUCKET = {
    "stock": BUCKET_STOCK,
    "crypto_major": BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
    "memecoin": BUCKET_NEW_MEMECOIN,
}


def _all_closed_trades(conn: sqlite3.Connection, profile_name: str) -> list[dict]:
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    rows = cursor.execute(
        "SELECT * FROM paper_trades WHERE strategy_id = ? ORDER BY exit_ts ASC",
        (profile_name,),
    ).fetchall()
    return [dict(row) for row in rows]


def _spy_condition(conn: sqlite3.Connection, exit_date: date) -> str:
    """SPY close vs its 50-day mean on exit_date -- the pre-registered
    fallback for dates outside every frozen window. Any data failure
    buckets 'unknown' (never counts as profitable-condition evidence)."""
    try:
        df = get_daily_bars(
            "SPY", end=exit_date.isoformat(), asset_class="stock", conn=conn
        )
        closes = df["close"].dropna()
        if len(closes) < 50:
            return "unknown"
        window = closes.iloc[-50:]
        return "risk_on" if float(closes.iloc[-1]) >= float(window.mean()) else "risk_off"
    except Exception:
        return "unknown"


def market_condition(conn: sqlite3.Connection, asset_class: str, exit_date: date) -> str:
    """D-03: frozen regime window first (tune or OOS, first match), SPY
    fallback for stock, 'unknown' otherwise."""
    bucket = _ASSET_CLASS_TO_BUCKET.get(asset_class)
    iso = exit_date.isoformat()
    for regime in REGIMES_V2:
        if regime.bucket != bucket:
            continue
        for start, end in (
            (regime.tune_start, regime.tune_end),
            (regime.oos_start, regime.oos_end),
        ):
            if start is not None and end is not None and start <= iso <= end:
                return regime.label
    if bucket == BUCKET_STOCK:
        return _spy_condition(conn, exit_date)
    return "unknown"


def _adverse_fill_pnl(trades: list[dict]) -> float:
    """Check 5 (D-04): every fill assumed ADVERSE_FILL_PCT worse -- entry
    raised, exit lowered (long-only book), fees unchanged."""
    p = frozen_checklist.ADVERSE_FILL_PCT
    total = 0.0
    for t in trades:
        total += (
            t["exit_price"] * (1 - p) - t["entry_price"] * (1 + p)
        ) * t["qty"] - t["fees"]
    return total


def evaluate_strategy(
    conn: sqlite3.Connection, profile_name: str
) -> dict:
    """All five checks for one strategy. Returns the full check record;
    overall is 'pass' / 'fail' / 'not_enough_trades'."""
    trades = _all_closed_trades(conn, profile_name)
    n = len(trades)
    result = {
        "profile_name": profile_name,
        "trade_count": n,
        "profit_factor": None,
        "pf_pass": False,
        "max_drawdown": None,
        "max_dd_pass": False,
        "profitable_conditions": None,
        "conditions_pass": False,
        "single_trade_share": None,
        "single_trade_pass": False,
        "adverse_fill_pnl": None,
        "adverse_fill_pass": False,
        "overall": "not_enough_trades",
    }
    if n < frozen_checklist.MIN_TRADES_FOR_GRADUATION:
        return result

    m = metrics.compute_metrics(trades, starting_equity=config.PAPER_ACCOUNT_EQUITY)

    pf = m["profit_factor"]
    result["profit_factor"] = pf
    result["pf_pass"] = pf is not None and pf > frozen_checklist.PF_GRADUATION_FLOOR

    dd = m["max_drawdown"]
    result["max_drawdown"] = dd
    result["max_dd_pass"] = dd is not None and dd > frozen_checklist.MAX_DD_GRADUATION

    bucket_pnl: dict[str, float] = {}
    for t in trades:
        exit_date = datetime.fromisoformat(t["exit_ts"]).date()
        condition = market_condition(conn, t["asset_class"], exit_date)
        bucket_pnl[condition] = bucket_pnl.get(condition, 0.0) + t["pnl"]
    profitable = sum(
        1 for cond, pnl in bucket_pnl.items() if cond != "unknown" and pnl > 0
    )
    result["profitable_conditions"] = profitable
    result["conditions_pass"] = (
        profitable >= frozen_checklist.MIN_PROFITABLE_CONDITIONS
    )

    pnls = [t["pnl"] for t in trades]
    total_pnl = sum(pnls)
    if total_pnl > 0:
        share = max(max(pnls), 0.0) / total_pnl
        result["single_trade_share"] = share
        result["single_trade_pass"] = (
            share <= frozen_checklist.MAX_SINGLE_TRADE_PROFIT_SHARE
        )

    adverse = _adverse_fill_pnl(trades)
    result["adverse_fill_pnl"] = adverse
    result["adverse_fill_pass"] = adverse > 0

    result["overall"] = (
        "pass"
        if all(
            result[key]
            for key in (
                "pf_pass",
                "max_dd_pass",
                "conditions_pass",
                "single_trade_pass",
                "adverse_fill_pass",
            )
        )
        else "fail"
    )
    return result


def _fmt(value) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


_CHECK_ROWS = (
    ("profit_factor", "pf_pass", "PF > 1.3"),
    ("max_drawdown", "max_dd_pass", "Max DD < 15%"),
    ("profitable_conditions", "conditions_pass", "Profitable in >= 2 conditions"),
    ("single_trade_share", "single_trade_pass", "No trade > 40% of profit"),
    ("adverse_fill_pnl", "adverse_fill_pass", "Positive with fills 1% worse"),
)


def run_graduation_review(
    conn: sqlite3.Connection,
    now: datetime | None = None,
    report_base_dir: str = "reports/tournament",
) -> dict:
    """Evaluate every active (probation/full) strategy, append one
    graduation_reviews row each, and write the weekly markdown record.
    Verifies the checklist freeze gate before evaluating anything."""
    freeze_gate.verify_frozen_graduation()
    now = now or datetime.now(timezone.utc)
    checklist_hash = freeze_gate.FROZEN_GRADUATION_HASH

    active = [
        r
        for r in config_store.get_registry_rows(conn)
        if r["state"] in ("probation", "full")
    ]
    results = [evaluate_strategy(conn, r["profile_name"]) for r in active]

    base_path = Path(report_base_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    report_path = base_path / f"{now.date().isoformat()}-graduation.md"

    lines = [
        f"# Graduation Review -- {now.date().isoformat()}",
        "",
        f"- **Checklist hash:** {checklist_hash}",
        f"- **Minimum trades:** {frozen_checklist.MIN_TRADES_FOR_GRADUATION}",
        "",
        "Verdicts are advisory (06-CONTEXT.md D-07): graduation to Phase 9 "
        "real money is the owner's decision, made on this record.",
        "",
    ]
    for res in results:
        lines += [
            f"## {res['profile_name']} -- **{res['overall'].upper()}** "
            f"({res['trade_count']} trades)",
            "",
        ]
        if res["overall"] == "not_enough_trades":
            lines += [
                f"Fewer than {frozen_checklist.MIN_TRADES_FOR_GRADUATION} closed "
                "trades -- checks not run.",
                "",
            ]
            continue
        lines += ["| Check | Value | Verdict |", "|---|---|---|"]
        for value_key, pass_key, label in _CHECK_ROWS:
            verdict = "PASS" if res[pass_key] else "FAIL"
            lines.append(f"| {label} | {_fmt(res[value_key])} | {verdict} |")
        lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")

    ts = now.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for res in results:
        conn.execute(
            """
            INSERT INTO graduation_reviews
                (ts, profile_name, trade_count, profit_factor, pf_pass,
                 max_drawdown, max_dd_pass, profitable_conditions,
                 conditions_pass, single_trade_share, single_trade_pass,
                 adverse_fill_pnl, adverse_fill_pass, overall,
                 checklist_hash, report_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                res["profile_name"],
                res["trade_count"],
                res["profit_factor"],
                int(res["pf_pass"]),
                res["max_drawdown"],
                int(res["max_dd_pass"]),
                res["profitable_conditions"],
                int(res["conditions_pass"]),
                res["single_trade_share"],
                int(res["single_trade_pass"]),
                res["adverse_fill_pnl"],
                int(res["adverse_fill_pass"]),
                res["overall"],
                checklist_hash,
                str(report_path),
            ),
        )
    conn.commit()

    passed = [r["profile_name"] for r in results if r["overall"] == "pass"]
    return {
        "results": results,
        "passed": passed,
        "report_path": str(report_path),
    }
