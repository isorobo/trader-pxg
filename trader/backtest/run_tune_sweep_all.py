"""Real D-06/D-10 tune-sweep driver (STRAT-03/04/05): the ~16-30 minute
offline acceptance run that executes trader.backtest.sweep.run_tune_sweep
against every (strategy, bucket, regime) combination in the frozen universe,
then persists each combo's D-10 top-5 candidates to
reports/backtests/tune_top5.json for Plan 03-05's OOS validation.

This module is pure orchestration over Plan 03-03's already-proven sweep
engine (trader.backtest.sweep) -- it never re-implements run_tune_sweep or
select_top5, and it never bypasses frozen_config.verify_frozen() (that gate
lives inside run_tune_sweep itself and fires before this module's first grid
cell of the whole run).

`grid_fn` (main's second argument) is a TEST-ONLY injection point. When None
(every production call), the real frozen exit_grid.exit_profile_grid drives
every cell exactly as Plan 03-03 wired it -- production code never passes a
non-None grid_fn. tests/test_run_tune_sweep_all.py is the only caller that
ever does, and only to keep the fast fixture test's cell count tiny (an
injected 2x2x1x1 grid instead of the real 270/360-cell grid). Because
trader.backtest.sweep.run_tune_sweep has no grid-injection parameter of its
own (Plan 03-03 deliberately calls exit_grid.exit_profile_grid directly --
consume-only from here, never modified), the only way to substitute a tiny
grid without editing sweep.py is to temporarily replace the shared exit_grid
module's exit_profile_grid attribute for the duration of this call, then
restore the original in a `finally` block. That swap is documented here, in
the one production module that performs it, rather than silently monkey-
patched from a test file -- so this hook is never mistaken for a production
knob (T-03-13).

Composite strategy_id tagging (the single convention Plan 03-05's
run_oos_validation_all.py depends on): every persisted D-10 candidate's
`strategy_id` field is set to the exact `f"{strategy_id}_{bucket}"` composite
string -- built ONCE per (strategy_id, bucket) pair below, in exactly one
place (`composite_strategy_id`), and reused verbatim everywhere it is needed
in that iteration. This is the same composite string `run_tune_sweep` already
persisted into `params_json["strategy"]`; Plan 03-05 strips the trailing
`_{bucket}` suffix from this exact field to recover the base strategy name,
so it must never drift from this one convention.

Run for real with:
    .venv\\Scripts\\python.exe -m trader.backtest.run_tune_sweep_all
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from trader.backtest import exit_grid, regimes, sweep, universe
from trader.backtest.strategies import breakout, momentum
from trader.data.api import get_daily_bars

OUTPUT_PATH = Path("reports/backtests/tune_top5.json")

# (strategy_id, pick_entries) pairs driven through every bucket/regime combo
# below -- Plan 03-01's shared pick_entries(iterator, date, open_positions,
# rng) -> list[str] contract for both agents.
_STRATEGIES: tuple[tuple[str, object], ...] = (
    ("momentum", momentum.pick_entries),
    ("breakout", breakout.pick_entries),
)


def main(conn=None, grid_fn=None) -> Path:
    """Run the full D-06/D-10 tune sweep and write
    reports/backtests/tune_top5.json.

    conn: an existing sqlite3.Connection, or None to route every
        get_daily_bars/run_backtest call to the real shared data/trader.db
        (trader.data.db.get_connection's default path) -- matches
        backfill_universe.py's precedent for this phase's real acceptance
        runs.
    grid_fn: TEST-ONLY. See module docstring -- defaults to the real frozen
        exit_grid.exit_profile_grid; production callers must never pass
        anything else.

    Returns the Path the candidate JSON was written to.
    """
    original_grid_fn = exit_grid.exit_profile_grid
    active_grid_fn = grid_fn if grid_fn is not None else original_grid_fn

    # Temporary swap of the shared exit_grid module's exit_profile_grid
    # attribute -- sweep.run_tune_sweep calls `exit_grid.exit_profile_grid`
    # directly (Plan 03-03, consume-only here) with no injection parameter
    # of its own. Restored in `finally` regardless of outcome, including a
    # frozen_config.verify_frozen() failure raised from inside
    # run_tune_sweep.
    sweep.exit_grid.exit_profile_grid = active_grid_fn
    try:
        all_candidates: list[dict] = []

        for strategy_id, pick_entries in _STRATEGIES:
            for bucket, symbols in universe.UNIVERSE_BY_BUCKET.items():
                # Built exactly once per (strategy_id, bucket) pair -- the
                # single place this composite convention is spelled out.
                composite_strategy_id = f"{strategy_id}_{bucket}"

                bucket_regimes = [r for r in regimes.REGIMES if r.bucket == bucket]
                if not bucket_regimes:
                    continue

                bars_by_symbol = {
                    symbol: get_daily_bars(
                        symbol,
                        asset_class=None if "/" in symbol else "stock",
                        conn=conn,
                    )
                    for symbol in symbols
                }

                for regime in bucket_regimes:
                    results = sweep.run_tune_sweep(
                        pick_entries,
                        composite_strategy_id,
                        bucket,
                        regime,
                        bars_by_symbol,
                        symbols,
                        conn,
                        sweep_id=sweep.DEFAULT_SWEEP_ID,
                    )
                    top5 = sweep.select_top5(results)
                    for candidate in top5:
                        candidate["strategy_id"] = composite_strategy_id
                        candidate["bucket"] = bucket
                        candidate["regime"] = regime.label
                    all_candidates.extend(top5)
    finally:
        sweep.exit_grid.exit_profile_grid = original_grid_fn

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(all_candidates, indent=2, default=str))
    return OUTPUT_PATH


if __name__ == "__main__":
    written_path = main()
    print(f"Wrote {written_path}")
    sys.exit(0)
