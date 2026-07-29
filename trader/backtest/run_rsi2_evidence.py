r"""RSI(2) entrant evidence run -- the exact shape of
run_donchian_evidence.py with the RSI(2) variant registry and its own
freeze gate, provenance sweep_id="rsi2_v1".

Same Phase 8 gate: this module NEVER writes strategy_registry.
Registration stays a human-run register_entrant.py command, after Phase 6
graduates an incumbent.

Scope: stock bucket only, 2 variants x 2 stock regimes x 270 grid cells =
1,080 tune runs + up to 10 OOS runs.

Run for real (from repo root; resumable if interrupted):

    .venv\Scripts\python.exe -m trader.backtest.run_rsi2_evidence
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from trader.backtest import regimes_v2, sweep, sweep_v2, universe
from trader.backtest.frozen_config_rsi2 import (
    FROZEN_HASH_RSI2,
    verify_frozen_rsi2,
)
from trader.backtest.run_tune_sweep_all_v2 import (
    _checkpoint_key,
    _cleanup_orphan_rows,
    _read_checkpoint,
    _write_checkpoint_atomic,
)
from trader.backtest.strategies import rsi2
from trader.backtest.write_kill_conditions import (
    CONSECUTIVE_LOSS_KILL,
    PF_FLOOR,
    _max_drawdown_trigger,
)
from trader.data import db as data_db
from trader.data.api import get_daily_bars

EVIDENCE_PATH = Path("reports/backtests/rsi2_evidence.json")
CHECKPOINT_PATH = Path("reports/backtests/rsi2_tune.checkpoint.jsonl")

SWEEP_ID_RSI2 = "rsi2_v1"
_STRATEGY_NAME = "rsi2"

EXPECTED_TUNE_RUN_COUNT_RSI2 = 1_080


def _strip_strategy_fn(candidate: dict) -> dict:
    return {k: v for k, v in candidate.items() if k != "strategy_fn"}


def main(conn=None, grid_fn=None) -> Path:
    """Run the full RSI(2) evidence cycle and write EVIDENCE_PATH."""
    verify_frozen_rsi2()

    if conn is None:
        conn = data_db.get_connection()

    from trader.backtest import exit_grid

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
            for variant_name, variant in rsi2.RSI2_VARIANTS.items():
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
                    rsi2.make_pick_entries(variant),
                    composite_strategy_id,
                    bucket,
                    regime,
                    variant_name,
                    bars_by_symbol,
                    symbols,
                    conn,
                    sweep_id=SWEEP_ID_RSI2,
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
                candidate["strategy_fn"] = rsi2.make_pick_entries(
                    rsi2.RSI2_VARIANTS[candidate["params"]["entry_variant"]]
                )
            candidates.extend(top5)

        if bars_by_symbol is None:
            bars_by_symbol = {
                symbol: get_daily_bars(symbol, asset_class="stock", conn=conn)
                for symbol in symbols
            }

        oos_results = sweep_v2.run_oos_validation_v2(
            candidates, {bucket: bars_by_symbol}, conn, sweep_id=SWEEP_ID_RSI2
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
        "sweep_id": SWEEP_ID_RSI2,
        "frozen_hash_rsi2": FROZEN_HASH_RSI2,
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
