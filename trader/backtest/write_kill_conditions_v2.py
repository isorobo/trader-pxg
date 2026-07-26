"""v2's phase-exit gate regeneration (Plan 03-08 Task 3, STRAT-06, D-11,
D-16): regenerates `.planning/phases/03-strategy-lab/KILL-CONDITIONS.md`
from v2's REAL `oos_results_v2.json` only, after the real v2 sweep/OOS
cycle (Task 2) completes.

`main()` calls `frozen_config_v2.verify_frozen_v2()` FIRST, before reading
`reports/backtests/oos_results_v2.json` or writing anything -- defence in
depth (T-03-29), mirroring v1's own `write_kill_conditions.py`'s T-03-20
pattern exactly. The upstream v2 tune-sweep and OOS-validation entrypoints
(Task 2) already enforce this same v2 hash check before producing the
data this module reads, but this module's own terminal gate must never
silently trust an unverified intermediate artifact.

`PF_FLOOR`, `MAX_DD_FLOOR`, `MAX_DD_MULTIPLIER`, `CONSECUTIVE_LOSS_KILL`,
`_max_drawdown_trigger`, and `NOTHING_SURVIVED_SENTENCE` are imported
directly from `trader.backtest.write_kill_conditions` and reused verbatim
-- D-15's "floors unchanged" spirit extends to these kill-condition
constants too, so the two definitions (v1's and v2's) can never silently
drift apart.

This module also drives `sweep_report.write_sweep_summary` (reused
unchanged -- run_id-disambiguated filenames make it collision-safe against
v1's already-committed reports) for every `oos_results_v2.json` entry, and
`sweep_report_v2.write_survivors_index_v2` for the full list, in this same
run -- D-16's intended fulfillment: `KILL-CONDITIONS.md` is the ONE file
this plan explicitly designates for v2 overwrite; every other v1 artifact
stays byte-unmodified (T-03-28).

Run for real with:
    .venv\\Scripts\\python.exe -m trader.backtest.write_kill_conditions_v2
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from trader.backtest import frozen_config_v2, sweep_report, sweep_report_v2
from trader.backtest.write_kill_conditions import (
    CONSECUTIVE_LOSS_KILL,
    MAX_DD_FLOOR,
    MAX_DD_MULTIPLIER,
    NOTHING_SURVIVED_SENTENCE,
    PF_FLOOR,
    _max_drawdown_trigger,
)
from trader.data import db as data_db

OOS_RESULTS_PATH = Path("reports/backtests/oos_results_v2.json")
TUNE_TOP5_PATH = Path("reports/backtests/tune_top5_v2.json")
KILL_CONDITIONS_PATH = Path(".planning/phases/03-strategy-lab/KILL-CONDITIONS.md")


def _survivor_entry_lines(result: dict) -> list[str]:
    candidate = result["candidate"]
    oos_metrics = result["oos_metrics"]
    dd_trigger = _max_drawdown_trigger(oos_metrics.get("max_drawdown"))
    params = candidate.get("params", {})
    exit_profile = params.get("profile_name", "unknown-exit-profile")
    entry_variant = params.get("entry_variant", "unknown-entry-variant")

    return [
        f"## {candidate['strategy_id']} / {candidate['bucket']} / {candidate['regime']}",
        "",
        f"- **Entry variant:** {entry_variant}",
        f"- **Exit profile:** {exit_profile}",
        f"- **Rolling-30-trade profit factor floor:** {PF_FLOOR}",
        f"- **Max-drawdown kill level:** {dd_trigger:.4f}",
        f"- **Consecutive-loss kill count:** {CONSECUTIVE_LOSS_KILL}",
        "",
    ]


def build_kill_conditions_text(oos_results: list[dict]) -> str:
    """Pure formatting function (no I/O) -- one entry per v2 survivor, or
    the honest "nothing survived" sentence when there are zero survivors.
    Kept separate from `main()`'s file I/O so tests can exercise both
    branches without touching the real committed file (mirrors v1's
    `write_kill_conditions.build_kill_conditions_text`'s separation)."""
    survivors = [r for r in oos_results if r["verdict"] == "survivor"]

    lines = [
        "# KILL-CONDITIONS.md",
        "",
        "Phase 3 Strategy Lab pre-registered kill conditions (D-11, STRAT-06),",
        "regenerated from v2's real OOS results (D-16). Committed once, before",
        "Phase 4 starts, and never edited while looking at live/paper results",
        "(standing rule 1).",
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
    """Run v2's real phase-exit gate: verify the v2 frozen-config hash,
    read the real `oos_results_v2.json`/`tune_top5_v2.json`, write every
    v2 `reports/backtests/*.md` artifact via `sweep_report`/
    `sweep_report_v2`, and write the real, regenerated
    `KILL-CONDITIONS.md`.

    conn: an existing sqlite3.Connection, or None to resolve one real
        connection to the shared data/trader.db up front (matches
        `run_oos_validation_all_v2.main`'s precedent).

    Returns the Path `KILL-CONDITIONS.md` was written to.
    """
    # Defence in depth (T-03-29): called FIRST, before oos_results_v2.json
    # is even read, even though Task 2's v2 tune-sweep/OOS entrypoints
    # already gated the runs that produced this data.
    frozen_config_v2.verify_frozen_v2()

    oos_results = json.loads(OOS_RESULTS_PATH.read_text())
    tune_top5 = json.loads(TUNE_TOP5_PATH.read_text())
    tune_by_run_id = {candidate["run_id"]: candidate for candidate in tune_top5}

    if conn is None:
        conn = data_db.get_connection()

    for result in oos_results:
        run_id = result["candidate"]["run_id"]
        tune_candidate = tune_by_run_id[run_id]
        sweep_report.write_sweep_summary(result, tune_candidate, conn)

    sweep_report_v2.write_survivors_index_v2(oos_results)

    KILL_CONDITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    KILL_CONDITIONS_PATH.write_text(
        build_kill_conditions_text(oos_results), encoding="utf-8"
    )
    return KILL_CONDITIONS_PATH


if __name__ == "__main__":
    written_path = main()
    print(f"Wrote {written_path}")
    sys.exit(0)
