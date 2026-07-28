r"""Donchian entrant evidence run: tune sweep + OOS validation + derived
kill conditions, producing reports/backtests/donchian_evidence.json --
everything the D-07 pipeline needs to admit the owner's first queued
entrant, STOPPING at the Phase 8 gate.

THE GATE (phase doc: "Phase 8 -- only if Phase 6 graduated something"):
this module NEVER writes strategy_registry. Registration is a separate,
human-run command (trader/tournament/register_entrant.py), to be run only
after Phase 6 graduates at least one incumbent.

Orchestration mirrors run_tune_sweep_all_v2.py: the same checkpoint-
resumable unit loop (its helpers are imported and reused, never
duplicated), the same variant-agnostic sweep_v2 engine (untouched, still
guarded by its own frozen_config_v2 gate), the same select_top5/
determine_survivor rules from sweep.py (D-15: ranking and verdict rules
are never redefined per strategy).

Scope: stock bucket only -- the live paper book is stock-only, and an
entrant must be judged on the book it would actually join. 2 variants x
2 stock regimes x 270 grid cells = 1,080 tune runs + up to 10 OOS runs,
provenance sweep_id="donchian_v1".

Run for real (from repo root; resumable if interrupted):

    .venv\Scripts\python.exe -m trader.backtest.run_donchian_evidence
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from trader.backtest import regimes_v2, sweep, sweep_v2, universe
from trader.backtest.frozen_config_donchian import (
    FROZEN_HASH_DONCHIAN,
    verify_frozen_donchian,
)
from trader.backtest.run_tune_sweep_all_v2 import (
    _checkpoint_key,
    _cleanup_orphan_rows,
    _read_checkpoint,
    _write_checkpoint_atomic,
)
from trader.backtest.strategies import donchian
from trader.backtest.write_kill_conditions import (
    CONSECUTIVE_LOSS_KILL,
    PF_FLOOR,
    _max_drawdown_trigger,
)
from trader.data import db as data_db
from trader.data.api import get_daily_bars

EVIDENCE_PATH = Path("reports/backtests/donchian_evidence.json")
CHECKPOINT_PATH = Path("reports/backtests/donchian_tune.checkpoint.jsonl")

SWEEP_ID_DONCHIAN = "donchian_v1"
_STRATEGY_NAME = "donchian"

# 2 variants x 2 stock regimes x 270 stock grid cells -- the acceptance
# count tests recompute from the real grid/regime sizes.
EXPECTED_TUNE_RUN_COUNT_DONCHIAN = 1_080


def _strip_strategy_fn(candidate: dict) -> dict:
    return {k: v for k, v in candidate.items() if k != "strategy_fn"}


def main(conn=None, grid_fn=None) -> Path:
    """Run the full Donchian evidence cycle and write EVIDENCE_PATH.

    conn: an existing sqlite3.Connection, or None for the real shared
        data/trader.db. grid_fn: TEST-ONLY exit-grid injection, exactly as
        run_tune_sweep_all_v2.main's precedent.
    """
    # The Donchian gate FIRST; sweep_v2's engine re-verifies the v2 gate
    # before every unit (defence in depth, both surfaces must be intact).
    verify_frozen_donchian()

    if conn is None:
        conn = data_db.get_connection()

    from trader.backtest import exit_grid  # for the same temporary-swap trick

    original_grid_fn = exit_grid.exit_profile_grid
    if grid_fn is not None:
        sweep_v2.exit_grid.exit_profile_grid = grid_fn

    bucket = universe.BUCKET_STOCK
    symbols = universe.UNIVERSE_BY_BUCKET[bucket]
    composite_strategy_id = f"{_STRATEGY_NAME}_{bucket}"
    bucket_regimes = [r for r in regimes_v2.REGIMES_V2 if r.bucket == bucket]

    try:
        checkpointed = _read_checkpoint(CHECKPOINT_PATH)
        all_records = list(checkpointed.values())
        bars_by_symbol = None

        for regime in bucket_regimes:
            for variant_name, variant in donchian.DONCHIAN_VARIANTS.items():
                key = _checkpoint_key(_STRATEGY_NAME, bucket, regime.label, variant_name)
                if key in checkpointed:
                    continue

                _cleanup_orphan_rows(
                    conn, composite_strategy_id, bucket, regime.label, variant_name
                )

                if bars_by_symbol is None:
                    bars_by_symbol = {
                        symbol: get_daily_bars(symbol, asset_class="stock", conn=conn)
                        for symbol in symbols
                    }

                results = sweep_v2.run_tune_sweep_v2(
                    donchian.make_pick_entries(variant),
                    composite_strategy_id,
                    bucket,
                    regime,
                    variant_name,
                    bars_by_symbol,
                    symbols,
                    conn,
                    sweep_id=SWEEP_ID_DONCHIAN,
                )

                record = {
                    "strategy": _STRATEGY_NAME,
                    "bucket": bucket,
                    "regime": regime.label,
                    "variant": variant_name,
                    "results": results,
                }
                checkpointed[key] = record
                all_records.append(record)
                _write_checkpoint_atomic(CHECKPOINT_PATH, all_records)

        # Top-5 per regime group (variants concatenated), D-10 rule reused.
        groups: dict[str, list[dict]] = {}
        for record in checkpointed.values():
            groups.setdefault(record["regime"], []).extend(record["results"])

        candidates: list[dict] = []
        for regime_label, combined in groups.items():
            top5 = sweep.select_top5(combined)
            for candidate in top5:
                candidate["strategy_id"] = composite_strategy_id
                candidate["bucket"] = bucket
                candidate["regime"] = regime_label
                candidate["strategy_fn"] = donchian.make_pick_entries(
                    donchian.DONCHIAN_VARIANTS[candidate["params"]["entry_variant"]]
                )
            candidates.extend(top5)

        if bars_by_symbol is None:
            bars_by_symbol = {
                symbol: get_daily_bars(symbol, asset_class="stock", conn=conn)
                for symbol in symbols
            }

        oos_results = sweep_v2.run_oos_validation_v2(
            candidates, {bucket: bars_by_symbol}, conn, sweep_id=SWEEP_ID_DONCHIAN
        )
    finally:
        sweep_v2.exit_grid.exit_profile_grid = original_grid_fn

    serialized_oos = []
    survivors = []
    for result in oos_results:
        verdict = sweep.determine_survivor(result["oos_metrics"])
        candidate = _strip_strategy_fn(result["candidate"])
        serialized_oos.append(
            {
                "candidate": candidate,
                "oos_run_id": result["oos_run_id"],
                "oos_metrics": result["oos_metrics"],
                "verdict": verdict,
            }
        )
        if verdict == "survivor":
            params = candidate["params"]
            survivors.append(
                {
                    # The registry payload, ready for register_entrant.py --
                    # kill triggers derived by the same rules as every
                    # incumbent (write_kill_conditions constants, reused).
                    "profile_name": params["profile_name"],
                    "strategy_id": composite_strategy_id,
                    "entry_variant": params["entry_variant"],
                    "stop_pct": params["stop_pct"],
                    "tp_pct": params["tp_pct"],
                    "trailing_pct": params["trailing_pct"],
                    "max_hold_days": params["max_hold_days"],
                    "pf_floor": PF_FLOOR,
                    "max_dd_kill": _max_drawdown_trigger(
                        result["oos_metrics"].get("max_drawdown")
                    ),
                    "consecutive_loss_kill": CONSECUTIVE_LOSS_KILL,
                    "backtest_run_id": candidate["run_id"],
                    "oos_run_id": result["oos_run_id"],
                    "oos_result_ref": str(EVIDENCE_PATH),
                }
            )

    evidence = {
        "sweep_id": SWEEP_ID_DONCHIAN,
        "frozen_hash_donchian": FROZEN_HASH_DONCHIAN,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase_gate_note": (
            "Registration is gated on Phase 6 graduating an incumbent "
            "(phase doc, Phase 8). Run trader/tournament/register_entrant.py "
            "manually after that gate opens."
        ),
        "tune_top5": [_strip_strategy_fn(c) for c in candidates],
        "oos_results": serialized_oos,
        "survivors": survivors,
    }
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, default=str))
    return EVIDENCE_PATH


if __name__ == "__main__":
    written_path = main()
    print(f"Wrote {written_path}")
    sys.exit(0)
