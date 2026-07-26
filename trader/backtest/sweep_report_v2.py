"""v2's own survivors index writer (Plan 03-08 Task 3, STRAT-06, D-16).

A single new function, `write_survivors_index_v2`, mirroring
`trader.backtest.sweep_report.write_survivors_index`'s exact logic
(survivor table, or the "nothing survived" sentence quoting the real
trial count) but writing to a distinctly-named
`{base_dir}/{today_str}-survivors-v2.md` file so it can never collide with
or overwrite v1's already-committed `{today_str}-survivors.md` (T-03-28).

D-05's survivorship-bias caveat is appended verbatim -- imported directly
from `trader.backtest.sweep_report.D05_CAVEAT` rather than restated, so it
can never drift between the two survivors indexes.

`trader.backtest.sweep_report.write_sweep_summary` is reused UNCHANGED for
v2's own per-config reports (its filename already includes the tune
run_id, making it collision-safe for v2 reuse without modification) --
this module does not redefine or wrap it.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from trader.backtest.sweep_report import D05_CAVEAT


def write_survivors_index_v2(
    oos_results: list[dict],
    base_dir: str = "reports/backtests",
) -> Path:
    """Write v2's own survivors index to
    `{base_dir}/{today_str}-survivors-v2.md`.

    If any `verdict == "survivor"` entries exist: a table of strategy,
    bucket, regime, OOS profit_factor, OOS trade_count -- one row per
    survivor. Otherwise the literal "Nothing survived this sweep" sentence
    quoting the real `len(oos_results)` candidate count and the real
    count of distinct (strategy, bucket, regime) combinations tested --
    never an empty or missing file, so "nothing survived" can never be
    mistaken for "nothing was tried" (mirrors v1's T-03-19 guard).
    """
    base_path = Path(base_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    report_path = base_path / f"{today_str}-survivors-v2.md"

    survivors = [r for r in oos_results if r["verdict"] == "survivor"]
    combinations = {
        (
            r["candidate"]["strategy_id"],
            r["candidate"]["bucket"],
            r["candidate"]["regime"],
        )
        for r in oos_results
    }

    lines = ["# Survivors Index (v2)", ""]
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
