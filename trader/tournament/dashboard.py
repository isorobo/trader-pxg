"""Per-strategy attribution dashboards (ATTR-01, D-01/D-02).

A static report generator: one markdown file + one self-contained HTML file
(no server, no JS, no external asset -- inline CSS and inline SVG only),
regenerated after each tournament run and alongside the daily report.

D-02: this module READS ONLY the ledgers (paper_trades) and the registry --
it never writes a table, and it keeps no bookkeeping of its own. All
metrics come from trader/backtest/metrics.py unmodified; the rolling-30
kill-proximity gauges recompute exactly what guardian.evaluate_kill_conditions
computes, against the same frozen per-config triggers.

Gauge status labels (SAFE/NEAR/TRIPPED) are display-only guidance: NEAR
means within 25% of the trigger's remaining headroom. The labels gate
nothing -- the guardian's own evaluation is the only kill authority.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from trader.backtest import metrics
from trader.paper import config, config_store, ledger
from trader.tournament import svg_chart

_NEAR_FRACTION = 0.25


def _all_trades(conn: sqlite3.Connection, profile_name: str) -> list[dict]:
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    rows = cursor.execute(
        "SELECT * FROM paper_trades WHERE strategy_id = ? ORDER BY exit_ts ASC",
        (profile_name,),
    ).fetchall()
    return [dict(row) for row in rows]


def _symbol_breakdown(conn: sqlite3.Connection, profile_name: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT symbol, COUNT(*) AS trade_count, SUM(pnl) AS total_pnl
        FROM paper_trades WHERE strategy_id = ?
        GROUP BY symbol ORDER BY total_pnl DESC
        """,
        (profile_name,),
    ).fetchall()
    return [
        {"symbol": symbol, "trade_count": count, "total_pnl": pnl}
        for symbol, count, pnl in rows
    ]


def _gauge(current: float | None, trigger: float, tripped: bool, near: bool) -> dict:
    status = "TRIPPED" if tripped else ("NEAR" if near else "SAFE")
    return {"current": current, "trigger": trigger, "status": status}


def compute_kill_proximity(conn: sqlite3.Connection, registry_row: dict) -> dict:
    """Distance from the rolling-30 window's current PF / max-DD /
    consecutive-loss values to the config's frozen kill triggers --
    guardian.evaluate_kill_conditions's exact math, re-run for display."""
    name = registry_row["profile_name"]
    trades = ledger.get_recent_trades(conn, name, limit=30)
    window_full = len(trades) >= 30
    pnls = [t["pnl"] for t in trades]  # DESC, most recent first

    pf = metrics.profit_factor(pnls)
    pf_floor = registry_row["pf_floor"]
    pf_gauge = _gauge(
        pf,
        pf_floor,
        tripped=window_full and pf is not None and pf < pf_floor,
        near=pf is not None and pf < pf_floor * (1 + _NEAR_FRACTION),
    )

    equity_curve: list[float] = []
    running = 0.0
    for pnl in reversed(pnls):  # chronological
        running += pnl
        equity_curve.append(running)
    dd = metrics.max_drawdown(equity_curve)
    dd_kill = registry_row["max_dd_kill"]
    dd_gauge = _gauge(
        dd,
        dd_kill,
        tripped=window_full and dd is not None and dd <= dd_kill,
        near=dd is not None and dd <= dd_kill * (1 - _NEAR_FRACTION),
    )

    consecutive_losses = 0
    for pnl in pnls:  # DESC -- leading run of losses
        if pnl < 0:
            consecutive_losses += 1
        else:
            break
    loss_kill = registry_row["consecutive_loss_kill"]
    loss_gauge = _gauge(
        consecutive_losses,
        loss_kill,
        tripped=window_full and consecutive_losses >= loss_kill,
        near=consecutive_losses >= loss_kill * (1 - _NEAR_FRACTION),
    )

    return {
        "window_full": window_full,
        "profit_factor": pf_gauge,
        "max_drawdown": dd_gauge,
        "consecutive_losses": loss_gauge,
    }


def compute_strategy_attribution(conn: sqlite3.Connection, registry_row: dict) -> dict:
    """Everything ATTR-01 shows for one strategy, from the ledger alone."""
    name = registry_row["profile_name"]
    trades = _all_trades(conn, name)
    return {
        "profile_name": name,
        "state": registry_row["state"],
        "metrics": metrics.compute_metrics(
            trades, starting_equity=config.PAPER_ACCOUNT_EQUITY
        ),
        "equity_curve": metrics._build_daily_equity_curve(
            trades, config.PAPER_ACCOUNT_EQUITY
        ),
        "symbols": _symbol_breakdown(conn, name),
        "kill_proximity": compute_kill_proximity(conn, registry_row),
    }


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


_METRIC_COLUMNS = (
    ("profit_factor", "PF"),
    ("sharpe_ratio", "Sharpe"),
    ("max_drawdown", "Max DD"),
    ("win_rate", "Win rate"),
    ("trade_count", "Trades"),
    ("total_fees_paid", "Fees"),
)


def render_markdown(attributions: list[dict], as_of: datetime) -> str:
    lines = [
        f"# Attribution Dashboard -- {as_of.date().isoformat()}",
        "",
        "Source: paper_trades ledger only (D-02). Judging/kill math: "
        "trader/backtest/metrics.py, unmodified.",
        "",
        "## Roster",
        "",
        "| Strategy | State | " + " | ".join(label for _, label in _METRIC_COLUMNS) + " |",
        "|---|---|" + "---|" * len(_METRIC_COLUMNS),
    ]
    for a in attributions:
        cells = " | ".join(_fmt(a["metrics"][key]) for key, _ in _METRIC_COLUMNS)
        lines.append(f"| {a['profile_name']} | {a['state']} | {cells} |")

    for a in attributions:
        prox = a["kill_proximity"]
        lines += [
            "",
            f"## {a['profile_name']} ({a['state']})",
            "",
            "### Kill-condition proximity (rolling 30 trades"
            + ("" if prox["window_full"] else ", window NOT yet full")
            + ")",
            "",
            "| Condition | Current | Trigger | Status |",
            "|---|---|---|---|",
        ]
        for key, label in (
            ("profit_factor", "PF floor"),
            ("max_drawdown", "Max drawdown"),
            ("consecutive_losses", "Consecutive losses"),
        ):
            g = prox[key]
            lines.append(
                f"| {label} | {_fmt(g['current'], 4)} | {_fmt(g['trigger'], 4)} "
                f"| {g['status']} |"
            )
        lines += ["", "### Per-symbol P&L", ""]
        if a["symbols"]:
            lines += ["| Symbol | Trades | P&L |", "|---|---|---|"]
            for s in a["symbols"]:
                lines.append(
                    f"| {s['symbol']} | {s['trade_count']} | {_fmt(s['total_pnl'])} |"
                )
        else:
            lines.append("No closed trades yet.")
    lines.append("")
    return "\n".join(lines)


def render_html(attributions: list[dict], as_of: datetime) -> str:
    """One self-contained HTML page: inline CSS, inline SVG, zero external
    references (D-01: no server, no JS frameworks)."""
    sections = []
    for a in attributions:
        m = a["metrics"]
        prox = a["kill_proximity"]
        metric_cells = "".join(
            f"<td>{_fmt(m[key])}</td>" for key, _ in _METRIC_COLUMNS
        )
        gauge_rows = "".join(
            f"<tr><td>{label}</td><td>{_fmt(prox[key]['current'], 4)}</td>"
            f"<td>{_fmt(prox[key]['trigger'], 4)}</td>"
            f"<td class='st-{prox[key]['status'].lower()}'>{prox[key]['status']}</td></tr>"
            for key, label in (
                ("profit_factor", "PF floor"),
                ("max_drawdown", "Max drawdown"),
                ("consecutive_losses", "Consecutive losses"),
            )
        )
        symbol_rows = (
            "".join(
                f"<tr><td>{s['symbol']}</td><td>{s['trade_count']}</td>"
                f"<td>{_fmt(s['total_pnl'])}</td></tr>"
                for s in a["symbols"]
            )
            or "<tr><td colspan='3'>No closed trades yet.</td></tr>"
        )
        sections.append(
            f"""
<section>
  <h2>{a['profile_name']} <em>({a['state']})</em></h2>
  {svg_chart.equity_curve_svg(a['equity_curve'])}
  <table>
    <tr>{''.join(f'<th>{label}</th>' for _, label in _METRIC_COLUMNS)}</tr>
    <tr>{metric_cells}</tr>
  </table>
  <h3>Kill-condition proximity (rolling 30{'' if prox['window_full'] else ', window not full'})</h3>
  <table>
    <tr><th>Condition</th><th>Current</th><th>Trigger</th><th>Status</th></tr>
    {gauge_rows}
  </table>
  <h3>Per-symbol P&amp;L</h3>
  <table>
    <tr><th>Symbol</th><th>Trades</th><th>P&amp;L</th></tr>
    {symbol_rows}
  </table>
</section>"""
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Attribution Dashboard -- {as_of.date().isoformat()}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 60rem; }}
  table {{ border-collapse: collapse; margin: 0.5rem 0 1.5rem; }}
  th, td {{ border: 1px solid #999; padding: 0.3rem 0.6rem; text-align: right; }}
  th:first-child, td:first-child {{ text-align: left; }}
  section {{ margin-bottom: 2.5rem; }}
  .st-safe {{ color: #2c7a2c; }}
  .st-near {{ color: #b8860b; font-weight: bold; }}
  .st-tripped {{ color: #b22222; font-weight: bold; }}
  svg {{ max-width: 100%; border: 1px solid #ccc; background: #fafafa; }}
</style>
</head>
<body>
<h1>Attribution Dashboard -- {as_of.date().isoformat()}</h1>
<p>Source: paper_trades ledger only (D-02). Generated by
trader/tournament/dashboard.py; metrics via trader/backtest/metrics.py,
unmodified.</p>
{''.join(sections)}
</body>
</html>
"""


def write_dashboard(
    conn: sqlite3.Connection,
    base_dir: str = "reports/attribution",
    as_of: datetime | None = None,
) -> dict:
    """Generate dashboard.md + dashboard.html for the full roster (all
    registry states -- retired strategies stay visible for audit). Returns
    the written paths."""
    as_of = as_of or datetime.now(timezone.utc)
    rows = config_store.get_registry_rows(conn)
    attributions = [compute_strategy_attribution(conn, row) for row in rows]

    base_path = Path(base_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    md_path = base_path / "dashboard.md"
    html_path = base_path / "dashboard.html"
    md_path.write_text(render_markdown(attributions, as_of), encoding="utf-8")
    html_path.write_text(render_html(attributions, as_of), encoding="utf-8")
    return {"markdown": str(md_path), "html": str(html_path)}
