r"""Donchian entrant evidence run over the CRYPTO buckets --
crypto_major_legacy_meme and new_memecoin -- with the exact machinery of
run_donchian_evidence.py (which covered stock). The spec's own "Best
Markets" line puts crypto first, so the crypto book gets the same honest
evidence pass, provenance sweep_id="donchian_crypto_v1".

The frozen surface is UNCHANGED: trader/backtest/strategies/donchian.py's
sys1/sys2 variants and FROZEN_HASH_DONCHIAN are byte-identical to the
stock run's -- one entry definition, every bucket (standing rule 1).

Same Phase 8 gate: NEVER writes strategy_registry. And note the live paper
book is currently stock-only -- a crypto survivor additionally needs the
crypto paper-trading leg (prepared as a plan for owner review, not armed)
before it could ever trade.

2 variants x (2 crypto_major regimes x 270 cells + 2 memecoin regimes x
360 cells) = 2,520 tune runs + up to 20 OOS runs.

Run for real (from repo root; resumable if interrupted):

    .venv\Scripts\python.exe -m trader.backtest.run_donchian_crypto_evidence
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

EVIDENCE_PATH = Path("reports/backtests/donchian_crypto_evidence.json")
CHECKPOINT_PATH = Path("reports/backtests/donchian_crypto_tune.checkpoint.jsonl")

SWEEP_ID_DONCHIAN_CRYPTO = "donchian_crypto_v1"
_STRATEGY_NAME = "donchian"

CRYPTO_BUCKETS: tuple[str, ...] = (
    universe.BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
    universe.BUCKET_NEW_MEMECOIN,
)

# 2 variants x (2 regimes x 270 crypto_major cells + 2 regimes x 360
# new_memecoin cells) -- the acceptance test recomputes from real sizes.
EXPECTED_TUNE_RUN_COUNT_DONCHIAN_CRYPTO = 2_520


def _strip_strategy_fn(candidate: dict) -> dict:
    return {k: v for k, v in candidate.items() if k != "strategy_fn"}


def _load_bucket_bars(conn, symbols: list[str]) -> dict:
    return {
        symbol: get_daily_bars(
            symbol, asset_class=None if "/" in symbol else "stock", conn=conn
        )
        for symbol in symbols
    }


def main(conn=None, grid_fn=None) -> Path:
    """Run the full crypto-bucket Donchian evidence cycle and write
    EVIDENCE_PATH."""
    verify_frozen_donchian()

    if conn is None:
        conn = data_db.get_connection()

    from trader.backtest import exit_grid

    original_grid_fn = exit_grid.exit_profile_grid
    if grid_fn is not None:
        sweep_v2.exit_grid.exit_profile_grid = grid_fn

    try:
        checkpointed = _read_checkpoint(CHECKPOINT_PATH)
        all_records = list(checkpointed.values())
        bars_by_bucket: dict[str, dict] = {}

        for bucket in CRYPTO_BUCKETS:
            symbols = universe.UNIVERSE_BY_BUCKET[bucket]
            composite_strategy_id = f"{_STRATEGY_NAME}_{bucket}"
            bucket_regimes = [r for r in regimes_v2.REGIMES_V2 if r.bucket == bucket]

            for regime in bucket_regimes:
                for variant_name, variant in donchian.DONCHIAN_VARIANTS.items():
                    key = _checkpoint_key(
                        _STRATEGY_NAME, bucket, regime.label, variant_name
                    )
                    if key in checkpointed:
                        continue

                    _cleanup_orphan_rows(
                        conn, composite_strategy_id, bucket, regime.label, variant_name
                    )

                    if bucket not in bars_by_bucket:
                        bars_by_bucket[bucket] = _load_bucket_bars(conn, symbols)

                    results = sweep_v2.run_tune_sweep_v2(
                        donchian.make_pick_entries(variant),
                        composite_strategy_id,
                        bucket,
                        regime,
                        variant_name,
                        bars_by_bucket[bucket],
                        symbols,
                        conn,
                        sweep_id=SWEEP_ID_DONCHIAN_CRYPTO,
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

        # Top-5 per (bucket, regime) group, variants concatenated (D-10).
        groups: dict[tuple[str, str], list[dict]] = {}
        for record in checkpointed.values():
            groups.setdefault((record["bucket"], record["regime"]), []).extend(
                record["results"]
            )

        candidates: list[dict] = []
        for (bucket, regime_label), combined in groups.items():
            top5 = sweep.select_top5(combined)
            for candidate in top5:
                candidate["strategy_id"] = f"{_STRATEGY_NAME}_{bucket}"
                candidate["bucket"] = bucket
                candidate["regime"] = regime_label
                candidate["strategy_fn"] = donchian.make_pick_entries(
                    donchian.DONCHIAN_VARIANTS[candidate["params"]["entry_variant"]]
                )
            candidates.extend(top5)

        for bucket in CRYPTO_BUCKETS:
            if bucket not in bars_by_bucket:
                bars_by_bucket[bucket] = _load_bucket_bars(
                    conn, universe.UNIVERSE_BY_BUCKET[bucket]
                )

        oos_results = sweep_v2.run_oos_validation_v2(
            candidates, bars_by_bucket, conn, sweep_id=SWEEP_ID_DONCHIAN_CRYPTO
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
                    "strategy_id": candidate["strategy_id"],
                    "bucket": candidate["bucket"],
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
        "sweep_id": SWEEP_ID_DONCHIAN_CRYPTO,
        "frozen_hash_donchian": FROZEN_HASH_DONCHIAN,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase_gate_note": (
            "Registration is gated on Phase 6 graduating an incumbent (phase "
            "doc, Phase 8) AND, for crypto survivors, on the crypto paper-"
            "trading leg being built and owner-approved -- the live paper "
            "book is stock-only today."
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
