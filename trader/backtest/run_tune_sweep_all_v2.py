r"""Real, checkpoint-resumable v2 tune-sweep driver (Plan 03-08 Task 2,
STRAT-03/04): the ~4-5 hour offline acceptance run that executes
trader.backtest.sweep_v2.run_tune_sweep_v2 across every (strategy, bucket,
regime, entry_variant) unit in the frozen v2 universe, then persists each
(strategy, bucket, regime) group's D-10 top-5 candidates (concatenated
across all 3 entry variants) to reports/backtests/tune_top5_v2.json for
Task 2's own OOS validation.

This module is pure orchestration over Plan 03-08 Task 1's already-proven
sweep_v2 engine -- it never re-implements run_tune_sweep_v2 or select_top5
(D-15, imported from trader.backtest.sweep unchanged), and it never
bypasses frozen_config_v2.verify_frozen_v2() (that gate lives inside
run_tune_sweep_v2 itself and fires before this module's first grid cell of
the whole run).

Unit of work: (strategy_name, bucket, regime, entry_variant) -- 36 total
(2 strategies x [2 buckets x 2 regimes + 1 bucket x 2 regimes] x 3
variants = 12 (strategy, bucket, regime) combos x 3 variants). Each unit
runs bucket's full exit-profile grid (270 or 360 cells) for ONE
entry-variant-bound strategy_fn.

Checkpoint-resumability (T-03-26): every completed unit is appended to
reports/backtests/tune_v2.checkpoint.jsonl as one JSON-lines record
{"strategy", "bucket", "regime", "variant", "results"}. On startup, every
already-checkpointed unit is read back and REUSED verbatim -- its
cell-results are never recomputed, and `sweep_v2.run_tune_sweep_v2` is
never called for it again. The checkpoint file itself is rewritten via a
temp-file + os.replace atomic swap on every unit completion (never a
partial/torn write, even if the process is killed mid-write), and
`_read_checkpoint` silently skips any malformed trailing line rather than
raising -- a crash during the temp-file write can leave, at worst, the
PRIOR complete checkpoint state on disk (os.replace is atomic), so this
defensive skip is a second layer, not the primary crash-safety mechanism.

Crash-safe row accounting (T-03-26): because `run_tune_sweep_v2` persists
each grid cell to backtest_runs/backtest_trades AS IT GOES (Task 1's
engine), a crash PARTWAY through a unit can leave that unit's DB rows
already written even though its checkpoint line was never appended (the
checkpoint line is only written AFTER the unit's `run_tune_sweep_v2` call
returns in full). On resume, any unit not yet in the checkpoint is treated
as not-yet-done and is about to be re-run from scratch -- `_cleanup_orphan_rows`
is called FIRST, deleting any backtest_runs/backtest_trades rows already
present for that exact (strategy, bucket, regime, entry_variant, sweep_id)
provenance, so the re-run can never double-count cells. This keeps the
final invariant true: backtest_runs rows with sweep_id="v2" and split="tune"
equal exactly EXPECTED_TUNE_SWEEP_RUN_COUNT_V2 (10,800) once all 36 units
have completed -- never more, regardless of how many times a unit was
interrupted and retried.

Run for real with (Windows, from repo root, backgrounded so this ~4-5 hour
run does not block the calling shell):

    Start-Process -FilePath ".venv\Scripts\python.exe" `
        -ArgumentList "-m", "trader.backtest.run_tune_sweep_all_v2" `
        -RedirectStandardOutput "reports\backtests\tune_v2_run.log" `
        -RedirectStandardError "reports\backtests\tune_v2_run.err.log" `
        -NoNewWindow -PassThru

If interrupted for any reason, simply re-invoking this same command
resumes from the checkpoint -- no unit is ever run twice, and no completed
unit's results are ever lost.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from trader.backtest import exit_grid, regimes_v2, sweep, sweep_v2, universe
from trader.backtest.strategies import breakout_v2, momentum_v2
from trader.data import db as data_db
from trader.data.api import get_daily_bars

OUTPUT_PATH = Path("reports/backtests/tune_top5_v2.json")
CHECKPOINT_PATH = Path("reports/backtests/tune_v2.checkpoint.jsonl")

_SWEEP_ID_V2 = "v2"

# T-03-27: 2 strategies x 3 entry variants x 2 regimes x 270 cells = 3,240
# (stock) + 3,240 (crypto_major_legacy_meme) + 2 x 3 x 2 x 360 = 4,320
# (new_memecoin) = 10,800 total tune-sweep runs -- matches D-14's
# pre-registered estimate exactly. tests/test_run_tune_sweep_all_v2.py's
# arithmetic-check test recomputes this from the REAL exit_grid/universe/
# regimes_v2 sizes and asserts it equals this literal constant.
EXPECTED_TUNE_SWEEP_RUN_COUNT_V2 = 10_800

# (strategy_name, variants attribute name, module) -- resolved via getattr
# at call time (never captured once at import) so a test can monkeypatch
# either module's variants dict and have main() observe the patched value.
_STRATEGY_SPECS: tuple[tuple[str, str, object], ...] = (
    ("momentum", "MOMENTUM_VARIANTS", momentum_v2),
    ("breakout", "BREAKOUT_VARIANTS", breakout_v2),
)


def _checkpoint_key(strategy_name: str, bucket: str, regime_label: str, variant_name: str) -> tuple:
    return (strategy_name, bucket, regime_label, variant_name)


def _read_checkpoint(checkpoint_path: Path) -> dict:
    """Read every well-formed JSON line from checkpoint_path into a dict
    keyed by (strategy, bucket, regime, variant). A malformed trailing
    line (e.g. a partial write left by an interrupted process) is silently
    skipped, never raised -- resume must never crash on it."""
    checkpointed: dict = {}
    if not checkpoint_path.exists():
        return checkpointed

    for line in checkpoint_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue  # malformed trailing line -- ignore, never crash resume
        key = _checkpoint_key(
            record["strategy"], record["bucket"], record["regime"], record["variant"]
        )
        checkpointed[key] = record
    return checkpointed


def _write_checkpoint_atomic(checkpoint_path: Path, records: list[dict]) -> None:
    """Rewrite the ENTIRE checkpoint file from `records` via a temp-file +
    os.replace swap (T-03-26). The destination file is always either the
    prior complete state or the new complete state -- os.replace is atomic
    on both POSIX and Windows -- so a process kill mid-write can never
    leave a torn/partial checkpoint file on disk."""
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(checkpoint_path.parent), prefix=checkpoint_path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            for record in records:
                f.write(json.dumps(record, default=str))
                f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, checkpoint_path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def _cleanup_orphan_rows(
    conn, composite_strategy_id: str, bucket: str, regime_label: str, variant_name: str
) -> None:
    """Delete any backtest_runs/backtest_trades rows left over from an
    incomplete prior attempt at this exact (strategy, bucket, regime,
    variant) unit -- called BEFORE re-running any unit not already present
    in the checkpoint (T-03-26). Idempotent: deletes zero rows when no
    orphan exists, which is the common (non-crash) case."""
    rows = conn.execute(
        "SELECT run_id, params_json FROM backtest_runs WHERE strategy_id = ?",
        (composite_strategy_id,),
    ).fetchall()

    orphan_run_ids = []
    for run_id, params_json in rows:
        try:
            params = json.loads(params_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if (
            params.get("sweep_id") == _SWEEP_ID_V2
            and params.get("asset_class_bucket") == bucket
            and params.get("regime") == regime_label
            and params.get("entry_variant") == variant_name
        ):
            orphan_run_ids.append(run_id)

    if not orphan_run_ids:
        return

    placeholders = ",".join("?" for _ in orphan_run_ids)
    conn.execute(
        f"DELETE FROM backtest_trades WHERE run_id IN ({placeholders})", orphan_run_ids
    )
    conn.execute(
        f"DELETE FROM backtest_runs WHERE run_id IN ({placeholders})", orphan_run_ids
    )
    conn.commit()


def count_tune_sweep_runs_v2(conn, sweep_id: str = _SWEEP_ID_V2) -> int:
    """Count backtest_runs rows whose params_json records this v2 tune
    sweep_id and split=="tune" -- used both by the arithmetic self-check
    test and the real run's post-completion 10,800 acceptance assertion
    (T-03-27). A plain Python scan (not a json1 SQL filter) so this works
    regardless of whether the sqlite build has the JSON1 extension."""
    rows = conn.execute("SELECT params_json FROM backtest_runs").fetchall()
    count = 0
    for (params_json,) in rows:
        try:
            params = json.loads(params_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if params.get("sweep_id") == sweep_id and params.get("split") == "tune":
            count += 1
    return count


def main(conn=None, grid_fn=None) -> Path:
    """Run the full v2 tune sweep (36 checkpoint-resumable units) and write
    reports/backtests/tune_top5_v2.json.

    conn: an existing sqlite3.Connection, or None to resolve one real
        connection to the shared data/trader.db up front (matches
        run_tune_sweep_all.main's precedent for this phase's real
        acceptance runs).
    grid_fn: TEST-ONLY. See module docstring's v1 precedent -- defaults to
        the real frozen exit_grid.exit_profile_grid; production callers
        must never pass anything else.

    Returns the Path the candidate JSON was written to.
    """
    if conn is None:
        conn = data_db.get_connection()

    original_grid_fn = exit_grid.exit_profile_grid
    active_grid_fn = grid_fn if grid_fn is not None else original_grid_fn

    # Temporary swap of the shared exit_grid module's exit_profile_grid
    # attribute -- sweep_v2.run_tune_sweep_v2 calls
    # `exit_grid.exit_profile_grid` directly, with no injection parameter
    # of its own (same trick v1's run_tune_sweep_all.py uses). Restored in
    # `finally` regardless of outcome.
    sweep_v2.exit_grid.exit_profile_grid = active_grid_fn
    try:
        checkpointed = _read_checkpoint(CHECKPOINT_PATH)
        all_records = list(checkpointed.values())

        for strategy_name, variants_attr, module in _STRATEGY_SPECS:
            variants = getattr(module, variants_attr)
            make_pick_entries = module.make_pick_entries

            for bucket, symbols in universe.UNIVERSE_BY_BUCKET.items():
                composite_strategy_id = f"{strategy_name}_{bucket}"
                bucket_regimes = [r for r in regimes_v2.REGIMES_V2 if r.bucket == bucket]
                if not bucket_regimes:
                    continue

                # Lazily loaded ONLY if at least one of this (strategy,
                # bucket) pair's units still needs to run -- a fully
                # resumed bucket never re-fetches bars.
                bars_by_symbol = None

                for regime in bucket_regimes:
                    for variant_name, variant in variants.items():
                        key = _checkpoint_key(
                            strategy_name, bucket, regime.label, variant_name
                        )
                        if key in checkpointed:
                            continue  # already done -- reuse, never re-run

                        # Crash-safe accounting (T-03-26): remove any
                        # orphaned rows from an interrupted prior attempt
                        # at this exact unit before re-running it.
                        _cleanup_orphan_rows(
                            conn, composite_strategy_id, bucket, regime.label, variant_name
                        )

                        if bars_by_symbol is None:
                            bars_by_symbol = {
                                symbol: get_daily_bars(
                                    symbol,
                                    asset_class=None if "/" in symbol else "stock",
                                    conn=conn,
                                )
                                for symbol in symbols
                            }

                        pick_entries_fn = make_pick_entries(variant)
                        results = sweep_v2.run_tune_sweep_v2(
                            pick_entries_fn,
                            composite_strategy_id,
                            bucket,
                            regime,
                            variant_name,
                            bars_by_symbol,
                            symbols,
                            conn,
                            sweep_id=_SWEEP_ID_V2,
                        )

                        record = {
                            "strategy": strategy_name,
                            "bucket": bucket,
                            "regime": regime.label,
                            "variant": variant_name,
                            "results": results,
                        }
                        checkpointed[key] = record
                        all_records.append(record)
                        # Flushed to disk before moving to the next unit --
                        # a crash after unit N preserves units 1..N.
                        _write_checkpoint_atomic(CHECKPOINT_PATH, all_records)
    finally:
        sweep_v2.exit_grid.exit_profile_grid = original_grid_fn

    # All units present -- group by (strategy, bucket, regime),
    # concatenate each group's 3 variants' cell-results, select_top5
    # (D-10/D-15, unchanged) once per group.
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for record in checkpointed.values():
        group_key = (record["strategy"], record["bucket"], record["regime"])
        groups.setdefault(group_key, []).extend(record["results"])

    all_candidates: list[dict] = []
    for (strategy_name, bucket, regime_label), combined in groups.items():
        composite_strategy_id = f"{strategy_name}_{bucket}"
        top5 = sweep.select_top5(combined)
        for candidate in top5:
            candidate["strategy_id"] = composite_strategy_id
            candidate["bucket"] = bucket
            candidate["regime"] = regime_label
        all_candidates.extend(top5)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(all_candidates, indent=2, default=str))
    return OUTPUT_PATH


if __name__ == "__main__":
    written_path = main()
    print(f"Wrote {written_path}")
    sys.exit(0)
