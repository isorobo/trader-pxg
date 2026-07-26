"""Phase 3's terminal artifact: real end-to-end run producing
`.planning/phases/03-strategy-lab/KILL-CONDITIONS.md` and every
`reports/backtests/*.md` artifact (STRAT-06, D-11, D-12).

`main()` calls `frozen_config.verify_frozen()` FIRST, before reading
`reports/backtests/oos_results.json` or writing anything -- a defence-in-
depth gate (T-03-20). The upstream tune-sweep (Plan 03-03) and OOS-
validation (Plan 03-05) entrypoints already enforce this same hash check
before producing the data this module reads, but this phase's final gate
must never silently trust an unverified intermediate artifact.

For every survivor (`verdict == "survivor"` in `oos_results.json`), this
module computes three concrete, fixed numeric kill triggers from that
survivor's own OOS metrics -- never a re-tuned or looser number chosen
after seeing results (standing rule 1):

1. Rolling-30-trade profit factor floor: 0.9 (fixed constant, matches
   ROADMAP.md's GRAD-03 vocabulary).
2. Max-drawdown kill level: 1.5x the survivor's own observed OOS
   max_drawdown magnitude, floored at -15% -- i.e. `max(1.5 * observed_dd,
   -0.15)` -- so the trigger is never looser (never allows more drawdown)
   than -15%, regardless of how small the survivor's own observed OOS
   drawdown was.
3. Consecutive-loss kill count: 8 (fixed constant).

If zero survivors, the single required sentence is written instead --
"nothing survived" is an equally valid, explicitly-reported phase-exit
outcome (D-12), never hidden or silently reinterpreted as success.

This module also drives `sweep_report.write_sweep_summary` for every
`oos_results.json` entry (looking up each candidate's matching
`tune_top5.json` entry by `run_id`) and `sweep_report.write_survivors_index`
for the full list, in this same run, so every `reports/backtests/*.md`
artifact and `KILL-CONDITIONS.md` are produced from one real execution over
real data (T-03-17).

Run for real with:
    .venv\\Scripts\\python.exe -m trader.backtest.write_kill_conditions
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from trader.backtest import frozen_config, sweep_report
from trader.data import db as data_db

OOS_RESULTS_PATH = Path("reports/backtests/oos_results.json")
TUNE_TOP5_PATH = Path("reports/backtests/tune_top5.json")
KILL_CONDITIONS_PATH = Path(".planning/phases/03-strategy-lab/KILL-CONDITIONS.md")

# D-11's fixed numeric constants -- pre-registered here, before any Phase 4
# result is ever viewed, per standing rule 1.
PF_FLOOR = 0.9
MAX_DD_FLOOR = -0.15
MAX_DD_MULTIPLIER = 1.5
CONSECUTIVE_LOSS_KILL = 8

NOTHING_SURVIVED_SENTENCE = (
    "Nothing survived this sweep — no kill conditions to register; work "
    "returns to Phase 3, not forward (ROADMAP.md Phase 3 success "
    "criterion 3)."
)


def _max_drawdown_trigger(observed_max_drawdown: float | None) -> float:
    """1.5x the survivor's own observed OOS max_drawdown magnitude,
    floored at -15% -- `max(1.5 * observed_dd, -0.15)` -- so the trigger
    can never be looser (more negative, allowing more drawdown) than
    -15%, regardless of how tight the survivor's own OOS drawdown was."""
    observed = observed_max_drawdown or 0.0
    return max(MAX_DD_MULTIPLIER * observed, MAX_DD_FLOOR)


def _survivor_entry_lines(result: dict) -> list[str]:
    candidate = result["candidate"]
    oos_metrics = result["oos_metrics"]
    dd_trigger = _max_drawdown_trigger(oos_metrics.get("max_drawdown"))
    exit_profile = candidate.get("params", {}).get("profile_name", "unknown-exit-profile")

    return [
        f"## {candidate['strategy_id']} / {candidate['bucket']} / {candidate['regime']}",
        "",
        f"- **Exit profile:** {exit_profile}",
        f"- **Rolling-30-trade profit factor floor:** {PF_FLOOR}",
        f"- **Max-drawdown kill level:** {dd_trigger:.4f}",
        f"- **Consecutive-loss kill count:** {CONSECUTIVE_LOSS_KILL}",
        "",
    ]


def build_kill_conditions_text(oos_results: list[dict]) -> str:
    """Pure formatting function (no I/O) -- one entry per survivor, or the
    honest "nothing survived" sentence when there are zero survivors.
    Kept separate from `main()`'s file I/O so tests can exercise both
    branches without touching the real committed file."""
    survivors = [r for r in oos_results if r["verdict"] == "survivor"]

    lines = [
        "# KILL-CONDITIONS.md",
        "",
        "Phase 3 Strategy Lab pre-registered kill conditions (D-11, STRAT-06).",
        "Committed once, before Phase 4 starts, and never edited while looking",
        "at live/paper results (standing rule 1).",
        "",
    ]

    if survivors:
        for result in survivors:
            lines += _survivor_entry_lines(result)
    else:
        lines.append(NOTHING_SURVIVED_SENTENCE)
        lines.append("")

    return "\n".join(lines)


def main(conn=None) -> Path:
    """Run the real phase-exit gate: verify the frozen-config hash, read
    the real `oos_results.json`/`tune_top5.json`, write every
    `reports/backtests/*.md` artifact via `sweep_report`, and write the
    real `KILL-CONDITIONS.md`.

    `conn`: an existing sqlite3.Connection, or None to resolve one real
        connection to the shared data/trader.db up front (matches
        run_oos_validation_all.main's precedent).

    Returns the Path KILL-CONDITIONS.md was written to.
    """
    # Defence in depth (T-03-20): called FIRST, before oos_results.json is
    # even read, even though Plans 03-03/03-05 already gated the runs that
    # produced this data.
    frozen_config.verify_frozen()

    oos_results = json.loads(OOS_RESULTS_PATH.read_text())
    tune_top5 = json.loads(TUNE_TOP5_PATH.read_text())
    tune_by_run_id = {candidate["run_id"]: candidate for candidate in tune_top5}

    if conn is None:
        conn = data_db.get_connection()

    for result in oos_results:
        run_id = result["candidate"]["run_id"]
        tune_candidate = tune_by_run_id[run_id]
        sweep_report.write_sweep_summary(result, tune_candidate, conn)

    sweep_report.write_survivors_index(oos_results)

    KILL_CONDITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    KILL_CONDITIONS_PATH.write_text(
        build_kill_conditions_text(oos_results), encoding="utf-8"
    )
    return KILL_CONDITIONS_PATH


if __name__ == "__main__":
    written_path = main()
    print(f"Wrote {written_path}")
    sys.exit(0)
