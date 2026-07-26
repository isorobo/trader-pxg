"""Trade ledger for the backtest harness (BACK-05, BACK-06, D-11, D-12).

Parameterized writes to ``backtest_runs``/``backtest_trades`` (migrations/
0003_backtest.sql, plan 02-01), one row per fill event — a position that
exits fully in one shot is one row; a position with scale-out tranches
produces one row per tranche, each sharing the same ``position_id``.
Per-position totals derive by ``SUM(pnl) ... GROUP BY position_id``.

Reproducibility (D-12): running the same seed + params against the same
data twice must produce identical trade content (excluding the
autoincrement/timestamp storage artifacts run_id/trade_id/started_at).

Per-strategy attribution (BACK-06): ``get_trades_for_strategy`` and
``compute_metrics_by_strategy`` group fills by strategy_id across every
run that strategy has ever produced. ``compute_metrics_by_strategy`` is a
thin wrapper that reuses ``trader.backtest.metrics.compute_metrics``
verbatim per strategy_id group — it does not reimplement any metric
formula.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from trader.backtest import metrics


def _code_version() -> str:
    """Resolve a short (8-char) git commit hash by reading .git/HEAD
    directly — avoids any shell-out surface entirely. Returns "unknown" on
    any failure (missing .git, detached ref file, unreadable file, etc.),
    per Assumption A5."""
    try:
        repo_root = Path(__file__).resolve().parents[2]
        git_dir = repo_root / ".git"
        head_text = (git_dir / "HEAD").read_text(encoding="utf-8").strip()

        if head_text.startswith("ref: "):
            ref_path = head_text[len("ref: ") :].strip()
            ref_file = git_dir / ref_path
            full_hash = ref_file.read_text(encoding="utf-8").strip()
        else:
            full_hash = head_text

        if not full_hash:
            return "unknown"
        return full_hash[:8]
    except Exception:
        return "unknown"


def record_run(
    conn: sqlite3.Connection,
    strategy_id: str,
    profile_name: str,
    params: dict,
    seed: int,
    code_version: str | None = None,
) -> int:
    """Insert one backtest_runs row and return its integer run_id."""
    if code_version is None:
        code_version = _code_version()

    cursor = conn.execute(
        """
        INSERT INTO backtest_runs (strategy_id, profile, params_json, seed, code_version)
        VALUES (?, ?, ?, ?, ?)
        """,
        (strategy_id, profile_name, json.dumps(params), seed, code_version),
    )
    conn.commit()
    return cursor.lastrowid


def record_trade(
    conn: sqlite3.Connection,
    run_id: int,
    position_id: str,
    strategy_id: str,
    symbol: str,
    asset_class: str,
    entry_ts: str,
    entry_price: float,
    exit_ts: str,
    exit_price: float,
    qty: float,
    fees: float,
    slippage: float,
    pnl: float,
    exit_reason: str,
) -> int:
    """Insert one backtest_trades row (one fill) and return its integer
    trade_id. CHECK-constraint violations (invalid asset_class/exit_reason)
    propagate uncaught as sqlite3.IntegrityError."""
    cursor = conn.execute(
        """
        INSERT INTO backtest_trades (
            run_id, position_id, strategy_id, symbol, asset_class,
            entry_ts, entry_price, exit_ts, exit_price, qty, fees,
            slippage, pnl, exit_reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            position_id,
            strategy_id,
            symbol,
            asset_class,
            entry_ts,
            entry_price,
            exit_ts,
            exit_price,
            qty,
            fees,
            slippage,
            pnl,
            exit_reason,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def _rows_to_dicts(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(row) for row in cursor.fetchall()]


def get_trades_for_run(conn: sqlite3.Connection, run_id: int) -> list[dict]:
    """Return every backtest_trades row for one run_id, ordered by
    trade_id ascending. Returns [] for a run_id with zero trades."""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    cursor.execute(
        "SELECT * FROM backtest_trades WHERE run_id = ? ORDER BY trade_id ASC",
        (run_id,),
    )
    return _rows_to_dicts(cursor)


def get_trades_for_strategy(conn: sqlite3.Connection, strategy_id: str) -> list[dict]:
    """Return every backtest_trades row for one strategy_id ACROSS ALL
    run_ids, ordered by trade_id ascending — the cross-run query
    get_trades_for_run deliberately does not provide."""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    cursor.execute(
        "SELECT * FROM backtest_trades WHERE strategy_id = ? ORDER BY trade_id ASC",
        (strategy_id,),
    )
    return _rows_to_dicts(cursor)


def compute_metrics_by_strategy(
    conn: sqlite3.Connection, run_ids: list[int] | None = None
) -> dict[str, dict]:
    """Group trades by strategy_id and compute metrics for each group via
    trader.backtest.metrics.compute_metrics. A thin grouping wrapper only —
    it reuses compute_metrics rather than reimplementing any formula.

    When run_ids is None, discovers every distinct strategy_id present in
    backtest_runs and uses each strategy's full trade history. When run_ids
    is given, scopes discovery and each strategy's trades to only those
    run_ids rather than that strategy's full history.
    """
    if run_ids is None:
        strategy_rows = conn.execute(
            "SELECT DISTINCT strategy_id FROM backtest_runs"
        ).fetchall()
        strategy_ids = [row[0] for row in strategy_rows]

        result: dict[str, dict] = {}
        for strategy_id in strategy_ids:
            trades = get_trades_for_strategy(conn, strategy_id)
            result[strategy_id] = metrics.compute_metrics(trades)
        return result

    placeholders = ",".join("?" for _ in run_ids)
    strategy_rows = conn.execute(
        f"SELECT DISTINCT strategy_id FROM backtest_runs WHERE run_id IN ({placeholders})",
        run_ids,
    ).fetchall()
    strategy_ids = [row[0] for row in strategy_rows]

    run_id_set = set(run_ids)
    result = {}
    for strategy_id in strategy_ids:
        all_trades = get_trades_for_strategy(conn, strategy_id)
        scoped_trades = [t for t in all_trades if t["run_id"] in run_id_set]
        result[strategy_id] = metrics.compute_metrics(scoped_trades)
    return result
