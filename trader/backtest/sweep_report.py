"""Per-config sweep reports and the survivors index (STRAT-06, D-12).

Two writers, both pure consumers of already-computed data (never a new
metrics engine, never a bypass of `metrics.compute_metrics` or
`ledger.get_trades_for_run`):

- `write_sweep_summary`: one markdown file per OOS-validated candidate,
  tune metrics and OOS metrics side by side, plus a per-symbol P&L
  breakdown built by grouping that candidate's OOS trades
  (`ledger.get_trades_for_run`) by `symbol` and summing `pnl` -- the
  orchestrator's cross-asset correlation-visibility resolution
  (03-RESEARCH.md Open Question 3): a single-symbol-driven "survivor" is
  visible in the report, never hidden behind an aggregate number.
- `write_survivors_index`: one markdown file listing every `verdict ==
  "survivor"` entry, or -- equally valid, per D-12 -- the honest
  "nothing survived" sentence quoting the real trial count
  (03-RESEARCH.md Overfitting Guards #3), so "nothing survived" is never
  mistaken for "nothing was tried" (T-03-19).

D-05's survivorship-bias caveat is appended verbatim to both report types:
this fixed research universe is NOT the live scanner universe, and a reader
must never mistake a Phase 3 "survivor" for a live-trading guarantee.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from trader.backtest import ledger

# D-05's caveat, stated once here and reused verbatim by both writers so it
# can never drift between the per-config report and the survivors index.
D05_CAVEAT = (
    "This fixed research universe is NOT the live scanner universe and "
    "carries survivorship bias -- treat these results as cheap-kill "
    "signal, not a live-trading guarantee; Phase 6 judges scanner-fed "
    "paper results as the real test."
)

# Shared column order for every tune/OOS metrics table -- matches
# metrics.METRIC_KEYS exactly so a reader can cross-reference the two.
_METRIC_KEYS = (
    "profit_factor",
    "sharpe_ratio",
    "max_drawdown",
    "win_rate",
    "avg_win",
    "avg_loss",
    "trade_count",
    "total_fees_paid",
)


def _metrics_table(title: str, metrics_dict: dict) -> list[str]:
    lines = [f"### {title}", "", "| Metric | Value |", "|---|---|"]
    for key in _METRIC_KEYS:
        lines.append(f"| {key} | {metrics_dict.get(key)} |")
    lines.append("")
    return lines


def _per_symbol_pnl_table(trades: list[dict]) -> list[str]:
    """Group `trades` by `symbol`, sum `pnl` per symbol, and render a
    markdown table -- the per-symbol visibility 03-RESEARCH.md's
    orchestrator resolution requires alongside the aggregate metrics."""
    totals: dict[str, float] = defaultdict(float)
    for trade in trades:
        totals[trade["symbol"]] += trade["pnl"]

    lines = ["### Per-Symbol P&L (OOS)", "", "| Symbol | Total P&L |", "|---|---|"]
    if totals:
        for symbol in sorted(totals):
            lines.append(f"| {symbol} | {totals[symbol]:.2f} |")
    else:
        lines.append("| (no trades) | - |")
    lines.append("")
    return lines


def write_sweep_summary(
    oos_result: dict,
    tune_candidate: dict,
    conn,
    base_dir: str = "reports/backtests",
) -> Path:
    """Write one per-config markdown report to
    `{base_dir}/{date}-{strategy}-{bucket}-{regime}-sweep.md` (per
    03-RESEARCH.md's Recommended Project Structure).

    `oos_result` is one `reports/backtests/oos_results.json` entry (keys
    `candidate`, `oos_run_id`, `oos_metrics`, `verdict`). `tune_candidate`
    is that same candidate's `reports/backtests/tune_top5.json` entry
    (keys `run_id`, `params`, `metrics`, `strategy_id`, `bucket`,
    `regime`) -- looked up by `run_id`, never re-derived, so the tune
    metrics table always reflects the real tune-sweep artifact.

    The filename carries the tune `run_id` as its final disambiguator
    (`{date}-{strategy}-{bucket}-{regime}-run{run_id}-sweep.md`) --
    03-RESEARCH.md's Recommended Project Structure names the pattern
    without a run_id, but D-10 pre-registers up to 5 top-5 configs per
    (strategy, bucket, regime) combination, and every one of them gets its
    own OOS validation and its own report (Task 2's "one per oos_result
    entry" acceptance criterion). Omitting run_id would collide same-combo
    candidates' filenames and silently drop reports -- a data-loss bug,
    not a formatting choice.
    """
    candidate = oos_result["candidate"]
    strategy = candidate["strategy_id"]
    bucket = candidate["bucket"]
    regime = candidate["regime"]
    verdict = oos_result["verdict"]
    run_id = tune_candidate["run_id"]

    base_path = Path(base_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    report_path = base_path / (
        f"{today_str}-{strategy}-{bucket}-{regime}-run{run_id}-sweep.md"
    )

    trades = ledger.get_trades_for_run(conn, oos_result["oos_run_id"])

    lines = [
        f"# Sweep Report: {strategy} / {bucket} / {regime}",
        "",
        f"- **Tune run_id:** {tune_candidate['run_id']}",
        f"- **OOS run_id:** {oos_result['oos_run_id']}",
        f"- **Verdict:** {verdict}",
        "",
    ]
    lines += _metrics_table("Tune-Window Metrics", tune_candidate["metrics"])
    lines += _metrics_table("OOS-Window Metrics", oos_result["oos_metrics"])
    lines += _per_symbol_pnl_table(trades)
    lines += [D05_CAVEAT, ""]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def write_survivors_index(
    oos_results: list[dict],
    base_dir: str = "reports/backtests",
) -> Path:
    """Write the survivors index to `{base_dir}/{date}-survivors.md`.

    If any `verdict == "survivor"` entries exist: a table of strategy,
    bucket, regime, OOS profit_factor, OOS trade_count -- one row per
    survivor. Otherwise the literal "Nothing survived this sweep" sentence
    quoting the real `len(oos_results)` candidate count and the real
    count of distinct (strategy, bucket, regime) combinations tested
    (03-RESEARCH.md Overfitting Guards #3) -- never an empty or missing
    file, so "nothing survived" can never be mistaken for "nothing was
    tried" (T-03-19).

    D-05's survivorship-bias caveat is appended in both branches.
    """
    base_path = Path(base_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    report_path = base_path / f"{today_str}-survivors.md"

    survivors = [r for r in oos_results if r["verdict"] == "survivor"]
    combinations = {
        (
            r["candidate"]["strategy_id"],
            r["candidate"]["bucket"],
            r["candidate"]["regime"],
        )
        for r in oos_results
    }

    lines = ["# Survivors Index", ""]
    if survivors:
        lines.append("| Strategy | Bucket | Regime | OOS Profit Factor | OOS Trade Count |")
        lines.append("|---|---|---|---|---|")
        for r in survivors:
            c = r["candidate"]
            lines.append(
                f"| {c['strategy_id']} | {c['bucket']} | {c['regime']} | "
                f"{r['oos_metrics']['profit_factor']} | {r['oos_metrics']['trade_count']} |"
            )
        lines.append("")
    else:
        lines.append(
            f"Nothing survived this sweep — {len(oos_results)} candidates "
            f"tested across {len(combinations)} strategy/bucket/regime "
            "combinations."
        )
        lines.append("")

    lines += [D05_CAVEAT, ""]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
