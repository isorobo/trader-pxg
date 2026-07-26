"""Metrics module for the backtest harness (BACK-06, D-13).

Computes profit factor, Sharpe ratio, max drawdown, win rate, avg win/loss,
trade count, and total fees paid from a list of completed trades, plus a
markdown report writer under ``reports/backtests/``.

Edge-case policy (Pitfall 4 in 02-RESEARCH.md, cross-checked against a
hand-worked golden fixture in tests/test_backtest_metrics.py — this module's
own honesty-scoring math must never crash or silently lie via NaN):

- ``profit_factor``: zero losing trades AND >=1 winning trade -> ``math.inf``.
  Zero trades (nothing to divide at all) -> ``None``.
- ``sharpe_ratio``: fewer than two daily-return observations -> ``None``
  (sample standard deviation is undefined with <2 points).
- ``compute_metrics([])``: every metric key is present and set to ``None``
  except ``trade_count`` (``0``) and ``total_fees_paid`` (``0.0`` — there are
  simply no fees to sum, which is a defined answer, not an undefined one).

``compute_metrics``'s signature (``list[dict]`` in, ``dict`` out) must stay
stable: plan 02-06's ``ledger.compute_metrics_by_strategy`` wraps this
function verbatim per strategy_id group.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

METRIC_KEYS = (
    "profit_factor",
    "sharpe_ratio",
    "max_drawdown",
    "win_rate",
    "avg_win",
    "avg_loss",
    "trade_count",
    "total_fees_paid",
)


def profit_factor(pnls: list[float]) -> float | None:
    """Gross gains / gross losses. See module docstring for the edge-case
    policy: zero trades -> None; zero losses with >=1 win -> math.inf."""
    if not pnls:
        return None
    gains = sum(p for p in pnls if p > 0)
    losses = sum(-p for p in pnls if p < 0)
    if losses == 0:
        return math.inf if gains > 0 else None
    return gains / losses


def _sharpe_from_returns(
    daily_returns: list[float], rf: float = 0.0, ddof: int = 1
) -> float | None:
    """Annualised Sharpe ratio (rf=0 default, sqrt(252) annualisation per
    D-13). ddof=1 (sample standard deviation) is pinned explicitly per
    Assumption A3 rather than left to an implicit default — matches Python's
    statistics.stdev."""
    if len(daily_returns) < 2:
        return None
    excess = [r - rf for r in daily_returns]
    mean_excess = statistics.mean(excess)
    std_excess = statistics.stdev(excess)  # ddof=1
    if std_excess == 0:
        return None
    return (mean_excess / std_excess) * math.sqrt(252)


def sharpe_ratio(daily_returns: list[float], rf: float = 0.0) -> float | None:
    """Public wrapper around the annualised Sharpe ratio helper."""
    return _sharpe_from_returns(daily_returns, rf=rf, ddof=1)


def max_drawdown(equity_curve: list[float]) -> float | None:
    """Largest peak-to-trough decline along the equity curve, expressed as a
    negative decimal (e.g. -0.18 for -18%). Returns None for an empty curve."""
    if not equity_curve:
        return None
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        drawdown = (value - peak) / peak
        max_dd = min(max_dd, drawdown)
    return max_dd


def _build_daily_equity_curve(
    trades: list[dict], starting_equity: float
) -> list[float]:
    """Group trades by exit_ts date, sum pnl per date, reindex across the
    full date range with 0-fill for no-trade days, and cumulate from
    starting_equity. Returns a curve starting with starting_equity itself
    followed by one cumulative point per date in range."""
    if not trades:
        return [starting_equity]

    daily_pnl: dict[date, float] = defaultdict(float)
    for trade in trades:
        exit_ts = trade["exit_ts"]
        if isinstance(exit_ts, str):
            trade_date = datetime.fromisoformat(exit_ts).date()
        elif isinstance(exit_ts, datetime):
            trade_date = exit_ts.date()
        elif isinstance(exit_ts, date):
            trade_date = exit_ts
        else:
            raise TypeError(f"Unsupported exit_ts type: {type(exit_ts)!r}")
        daily_pnl[trade_date] += trade["pnl"]

    all_dates = sorted(daily_pnl.keys())
    full_range = []
    if all_dates:
        current = all_dates[0]
        last = all_dates[-1]
        one_day = date.fromordinal(current.toordinal() + 1) - current
        while current <= last:
            full_range.append(current)
            current = current + one_day

    curve = [starting_equity]
    running = starting_equity
    for d in full_range:
        running += daily_pnl.get(d, 0.0)
        curve.append(running)
    return curve


def compute_metrics(
    trades: list[dict], starting_equity: float = 100_000.0
) -> dict:
    """Compute all BACK-06 metrics from a list of completed trades.

    Each trade dict is expected to carry at least ``pnl``, ``fees``, and
    ``exit_ts`` keys (matching backtest_trades ledger rows). Never raises —
    zero trades produces every metric key set to None (except trade_count=0
    and total_fees_paid=0.0), per the edge-case policy in the module
    docstring.
    """
    trade_count = len(trades)

    if trade_count == 0:
        result = {key: None for key in METRIC_KEYS}
        result["trade_count"] = 0
        result["total_fees_paid"] = 0.0
        return result

    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    win_rate = len(wins) / trade_count
    avg_win = statistics.mean(wins) if wins else None
    avg_loss = statistics.mean(losses) if losses else None
    total_fees_paid = sum(t.get("fees", 0.0) for t in trades)

    equity_curve = _build_daily_equity_curve(trades, starting_equity)
    daily_returns = [
        (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
        for i in range(1, len(equity_curve))
        if equity_curve[i - 1] != 0
    ]

    return {
        "profit_factor": profit_factor(pnls),
        "sharpe_ratio": sharpe_ratio(daily_returns),
        "max_drawdown": max_drawdown(equity_curve),
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "trade_count": trade_count,
        "total_fees_paid": total_fees_paid,
    }


def write_report(
    run_id: int,
    metrics: dict,
    strategy_id: str,
    base_dir: str = "reports/backtests",
) -> Path:
    """Write a markdown report for a single backtest run's metrics to
    ``{base_dir}/{YYYY-MM-DD}-{strategy_id}-run{run_id}.md``. Creates
    base_dir if missing. Returns the Path to the written file."""
    base_path = Path(base_dir)
    base_path.mkdir(parents=True, exist_ok=True)

    today_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{today_str}-{strategy_id}-run{run_id}.md"
    report_path = base_path / filename

    lines = [
        "# Backtest Report",
        "",
        f"- **Run ID:** {run_id}",
        f"- **Strategy:** {strategy_id}",
        f"- **Date:** {today_str}",
        "",
        "## Metrics",
        "",
    ]
    for key in METRIC_KEYS:
        lines.append(f"- **{key}:** {metrics.get(key)}")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path
