"""Real v2 OOS validation driver (Plan 03-08 Task 2, STRAT-05): the offline
acceptance run that validates every real v2 top-5 candidate
(reports/backtests/tune_top5_v2.json, Task 2's tune-sweep driver) against
its regime's held-out OOS window via
trader.backtest.sweep_v2.run_oos_validation_v2, then determines each
candidate's verdict via sweep_v2.determine_survivor (reused unchanged from
v1's sweep.determine_survivor, D-15) and persists the FULL list -- every
verdict, not only survivors (D-12) -- to reports/backtests/oos_results_v2.json.

This module is pure orchestration over Task 1's already-proven
sweep_v2.run_oos_validation_v2 -- it never re-implements it, and it never
bypasses frozen_config_v2.verify_frozen_v2() (that gate lives inside
run_oos_validation_v2 itself and fires before this module's first
candidate of the whole run).

Composite strategy_id + entry_variant resolution: every candidate in
reports/backtests/tune_top5_v2.json carries `strategy_id` as the exact
`f"{strategy_id}_{bucket}"` composite Task 2's tune-sweep driver tagged
onto it, PLUS `params["entry_variant"]` (one of "strict"/"base"/"loose").
This module recovers the base strategy_id by stripping the trailing
`_{bucket}` suffix (never re-deriving the composite convention, only
reversing it, same as v1's run_oos_validation_all.py), looks up that base
strategy's variant registry (MOMENTUM_VARIANTS/BREAKOUT_VARIANTS), resolves
the exact variant object by `entry_variant`, and binds `strategy_fn` via
that base strategy's `make_pick_entries(variant)` factory -- attached to a
COPY of the candidate, so the original tune_top5_v2.json candidate dict
(destined for cross-referencing) is never mutated and the non-serializable
callable never leaks into the written output artifact.

Run for real with:
    .venv\\Scripts\\python.exe -m trader.backtest.run_oos_validation_all_v2
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from trader.backtest import sweep_v2, universe
from trader.backtest.strategies import breakout_v2, momentum_v2
from trader.data import db as data_db
from trader.data.api import get_daily_bars

INPUT_PATH = Path("reports/backtests/tune_top5_v2.json")
OUTPUT_PATH = Path("reports/backtests/oos_results_v2.json")

# base_strategy_id -> (variants dict, make_pick_entries factory) -- the
# same shared pick_entries(iterator, date, open_positions, rng) -> list[str]
# contract both v2 agents implement (Plan 03-07).
_VARIANT_REGISTRIES: dict[str, tuple[dict, object]] = {
    "momentum": (momentum_v2.MOMENTUM_VARIANTS, momentum_v2.make_pick_entries),
    "breakout": (breakout_v2.BREAKOUT_VARIANTS, breakout_v2.make_pick_entries),
}


def _base_strategy_id(composite_strategy_id: str, bucket: str) -> str:
    """Recover the base strategy_id (e.g. "momentum") from a composite
    `f"{strategy_id}_{bucket}"` string by stripping the trailing
    `_{bucket}` suffix -- reversing Task 2's tune-sweep driver's tagging
    convention, never re-deriving it (same convention as v1's
    run_oos_validation_all.py)."""
    suffix = f"_{bucket}"
    if not composite_strategy_id.endswith(suffix):
        raise ValueError(
            f"strategy_id {composite_strategy_id!r} does not end with "
            f"expected suffix {suffix!r} for bucket {bucket!r}"
        )
    return composite_strategy_id[: -len(suffix)]


def main(conn=None) -> Path:
    """Run OOS validation over every candidate in
    reports/backtests/tune_top5_v2.json and write
    reports/backtests/oos_results_v2.json.

    conn: an existing sqlite3.Connection, or None to resolve one real
        connection to the shared data/trader.db up front (matches
        run_tune_sweep_all_v2.main's precedent).

    Returns the Path the OOS results JSON was written to.
    """
    if conn is None:
        conn = data_db.get_connection()

    candidates = json.loads(INPUT_PATH.read_text())

    # Group by bucket so each bucket's universe bars are loaded exactly
    # once, regardless of how many candidates share that bucket (cache-hit
    # only, same pattern as run_tune_sweep_all_v2.main).
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
        variants, make_pick_entries = _VARIANT_REGISTRIES[base_id]
        variant = variants[candidate["params"]["entry_variant"]]
        strategy_fn = make_pick_entries(variant)
        augmented_candidates.append({**candidate, "strategy_fn": strategy_fn})

    results = sweep_v2.run_oos_validation_v2(
        candidates=augmented_candidates,
        bars_by_symbol_by_bucket=bars_by_symbol_by_bucket,
        conn=conn,
        sweep_id=sweep_v2.DEFAULT_SWEEP_ID_V2,
    )

    oos_results: list[dict] = []
    for result in results:
        verdict = sweep_v2.determine_survivor(result["oos_metrics"])
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
