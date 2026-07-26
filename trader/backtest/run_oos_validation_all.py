"""Real OOS validation driver (STRAT-04/STRAT-05): the offline acceptance
run that validates every Plan 03-04 D-10 top-5 candidate against its
regime's held-out OOS window via trader.backtest.sweep.run_oos_validation,
then determines each candidate's verdict via sweep.determine_survivor and
persists the FULL list -- every verdict, not only survivors (D-12) -- to
reports/backtests/oos_results.json.

This module is pure orchestration over Plan 03-05 Task 1's already-proven
sweep.run_oos_validation/determine_survivor -- it never re-implements either,
and it never bypasses frozen_config.verify_frozen() (that gate lives inside
run_oos_validation itself and fires before this module's first candidate of
the whole run).

Composite strategy_id resolution: every candidate in
reports/backtests/tune_top5.json carries `strategy_id` as the exact
`f"{strategy_id}_{bucket}"` composite Plan 03-04 tagged onto it. This module
recovers the base strategy_id by stripping the trailing `_{bucket}` suffix
(never re-deriving the composite convention, only reversing it) and resolves
the matching pick_entries callable from _STRATEGY_FNS, then attaches it to
a COPY of the candidate as `strategy_fn` -- the original tune_top5.json
candidate dict is never mutated, so the strategy_fn (not JSON-serializable)
never leaks into the written output artifact.

Run for real with:
    .venv\\Scripts\\python.exe -m trader.backtest.run_oos_validation_all
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from trader.backtest import sweep, universe
from trader.backtest.strategies import breakout, momentum
from trader.data import db as data_db
from trader.data.api import get_daily_bars

INPUT_PATH = Path("reports/backtests/tune_top5.json")
OUTPUT_PATH = Path("reports/backtests/oos_results.json")

# (strategy_id, pick_entries) lookup for resolving each candidate's
# strategy_fn from its composite strategy_id -- the same shared
# pick_entries(iterator, date, open_positions, rng) -> list[str] contract
# both agents already implement (Plan 03-01).
_STRATEGY_FNS: dict[str, object] = {
    "momentum": momentum.pick_entries,
    "breakout": breakout.pick_entries,
}


def _base_strategy_id(composite_strategy_id: str, bucket: str) -> str:
    """Recover the base strategy_id (e.g. "momentum") from a composite
    `f"{strategy_id}_{bucket}"` string (e.g. "momentum_stock") by stripping
    the trailing `_{bucket}` suffix -- reversing Plan 03-04's tagging
    convention, never re-deriving it."""
    suffix = f"_{bucket}"
    if not composite_strategy_id.endswith(suffix):
        raise ValueError(
            f"strategy_id {composite_strategy_id!r} does not end with "
            f"expected suffix {suffix!r} for bucket {bucket!r}"
        )
    return composite_strategy_id[: -len(suffix)]


def main(conn=None) -> Path:
    """Run OOS validation over every candidate in
    reports/backtests/tune_top5.json and write
    reports/backtests/oos_results.json.

    conn: an existing sqlite3.Connection, or None to resolve one real
        connection to the shared data/trader.db up front (matches
        run_tune_sweep_all.main's precedent for this phase's real
        acceptance runs -- get_daily_bars alone tolerates conn=None but
        runner.run_backtest/ledger.record_run require a live connection
        object).

    Returns the Path the OOS results JSON was written to.
    """
    if conn is None:
        conn = data_db.get_connection()

    candidates = json.loads(INPUT_PATH.read_text())

    # Group by bucket so each bucket's universe bars are loaded exactly
    # once, regardless of how many candidates share that bucket (cache-hit
    # only, same pattern as run_tune_sweep_all.main).
    buckets_needed = sorted({candidate["bucket"] for candidate in candidates})
    bars_by_symbol_by_bucket: dict[str, dict] = {}
    for bucket in buckets_needed:
        symbols = universe.UNIVERSE_BY_BUCKET[bucket]
        bars_by_symbol_by_bucket[bucket] = {
            symbol: get_daily_bars(
                symbol,
                asset_class=None if "/" in symbol else "stock",
                conn=conn,
            )
            for symbol in symbols
        }

    # Resolve strategy_fn per candidate onto a COPY -- the original
    # candidate dict (destined for the output artifact) is never mutated,
    # so the non-serializable callable never reaches json.dumps.
    augmented_candidates = []
    for candidate in candidates:
        base_id = _base_strategy_id(candidate["strategy_id"], candidate["bucket"])
        strategy_fn = _STRATEGY_FNS[base_id]
        augmented_candidates.append({**candidate, "strategy_fn": strategy_fn})

    results = sweep.run_oos_validation(
        candidates=augmented_candidates,
        bars_by_symbol_by_bucket=bars_by_symbol_by_bucket,
        conn=conn,
        sweep_id=sweep.DEFAULT_SWEEP_ID,
    )

    oos_results: list[dict] = []
    for result in results:
        verdict = sweep.determine_survivor(result["oos_metrics"])
        original_candidate = {
            key: value for key, value in result["candidate"].items() if key != "strategy_fn"
        }
        oos_results.append(
            {
                "candidate": original_candidate,
                "oos_run_id": result["oos_run_id"],
                "oos_metrics": result["oos_metrics"],
                "verdict": verdict,
            }
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(oos_results, indent=2, default=str))
    return OUTPUT_PATH


if __name__ == "__main__":
    written_path = main()
    print(f"Wrote {written_path}")
    sys.exit(0)
