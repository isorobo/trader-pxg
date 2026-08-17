r"""Hourly (1h) evidence run: tune sweep + OOS validation over REAL cached
Binance hourly bars, producing reports/backtests/hourly_evidence.json --
provenance sweep_id="hourly_v1".

Engine: trader.backtest.runner.run_backtest UNCHANGED (the engine-proof
test in tests/test_hourly_track.py demonstrates next-HOUR-open fills,
per-fill fees/slippage, and hour-counted holds on 1h bars). The exit grid
is the frozen 24-cell hourly grid; windows are REGIMES_1H; both are under
frozen_config_hourly's gate, verified FIRST.

Signal caching: the 24 exit cells of one (strategy, variant, regime) unit
re-scan byte-identical signals, so each variant's fired-symbol list is
cached per bar timestamp on the first cell and replayed for the rest --
pick_entries is a pure function of point-in-time history, and the
open-position exclusion is re-applied OUTSIDE the cache, so results are
bit-identical to the uncached run at ~24x less signal compute.

Selection/verdict rules: sweep.select_top5 and sweep.determine_survivor,
reused unchanged (D-15 -- ranking and verdict rules are never redefined
per track).

Same registration gate as every entrant: this module NEVER writes
strategy_registry.

    .venv\Scripts\python.exe -m trader.backtest.run_hourly_evidence
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from trader.backtest import ledger as bt_ledger
from trader.backtest import metrics, runner, sweep, universe
from trader.backtest.frozen_config_hourly import (
    FROZEN_HASH_HOURLY,
    verify_frozen_hourly,
)
from trader.backtest.hourly_grid import REGIMES_1H, hourly_exit_profile_grid
from trader.backtest.run_tune_sweep_all_v2 import (
    _checkpoint_key,
    _cleanup_orphan_rows,
    _read_checkpoint,
    _write_checkpoint_atomic,
)
from trader.backtest.strategies import hourly_reversion, hourly_squeeze
from trader.backtest.sweep import _slice_bars
from trader.backtest.write_kill_conditions import (
    CONSECUTIVE_LOSS_KILL,
    PF_FLOOR,
    _max_drawdown_trigger,
)
from trader.data import db as data_db
from trader.data.intraday import get_hourly_bars

EVIDENCE_PATH = Path("reports/backtests/hourly_evidence.json")
CHECKPOINT_PATH = Path("reports/backtests/hourly_tune.checkpoint.jsonl")

SWEEP_ID_HOURLY = "hourly_v1"

_STRATEGY_SPECS: tuple[tuple[str, dict, object], ...] = (
    ("hreversion", hourly_reversion.HOURLY_REVERSION_VARIANTS, hourly_reversion),
    ("hsqueeze", hourly_squeeze.HOURLY_SQUEEZE_VARIANTS, hourly_squeeze),
)

# 2 strategies x 2 variants x 2 bucket-regimes x 24 cells.
EXPECTED_TUNE_RUN_COUNT_HOURLY = 192


def _hourly_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["ts"], utc=True)
    return df[["open", "high", "low", "close", "volume"]]


def _load_bucket_frames(conn, bucket: str) -> dict[str, pd.DataFrame]:
    frames = {}
    for symbol in universe.UNIVERSE_BY_BUCKET[bucket]:
        rows = get_hourly_bars(conn, symbol)
        if rows:
            frames[symbol] = _hourly_frame(rows)
    return frames


def _cached_strategy_fn(pick_entries, cache: dict):
    """Replay-cache wrapper: raw fired-symbols per bar timestamp, with the
    open-position exclusion re-applied OUTSIDE the cache (pick_entries only
    ever EXCLUDES open symbols, so filtering after is equivalent)."""

    def fn(iterator, date, open_positions, rng):
        if date not in cache:
            cache[date] = pick_entries(iterator, date, set(), rng)
        return [s for s in cache[date] if s not in open_positions]

    return fn


def _strip_strategy_fn(candidate: dict) -> dict:
    return {k: v for k, v in candidate.items() if k != "strategy_fn"}


def main(conn=None) -> Path:
    """Run the full hourly evidence cycle and write EVIDENCE_PATH."""
    verify_frozen_hourly()

    if conn is None:
        conn = data_db.get_connection()

    checkpointed = _read_checkpoint(CHECKPOINT_PATH)
    all_records = list(checkpointed.values())
    frames_by_bucket: dict[str, dict] = {}

    for strategy_name, variants, module in _STRATEGY_SPECS:
        for regime in REGIMES_1H:
            bucket = regime.bucket
            composite_strategy_id = f"{strategy_name}_{bucket}"
            symbols = universe.UNIVERSE_BY_BUCKET[bucket]

            for variant_name, variant in variants.items():
                key = _checkpoint_key(strategy_name, bucket, regime.label, variant_name)
                if key in checkpointed:
                    continue

                _cleanup_orphan_rows(
                    conn, composite_strategy_id, bucket, regime.label, variant_name
                )

                if bucket not in frames_by_bucket:
                    frames_by_bucket[bucket] = _load_bucket_frames(conn, bucket)

                sliced = _slice_bars(
                    frames_by_bucket[bucket], regime.tune_start, regime.tune_end
                )
                signal_cache: dict = {}
                results = []
                for profile in hourly_exit_profile_grid(bucket):
                    profile_name = (
                        f"{composite_strategy_id}_{regime.label}_{variant_name}_tune_"
                        f"stop{profile.stop_pct}_tp{profile.tp_pct}_"
                        f"trail{profile.trailing_pct}_hold{profile.max_hold_days}h"
                    )
                    params = {
                        "profile_name": profile_name,
                        "sweep_id": SWEEP_ID_HOURLY,
                        "regime": regime.label,
                        "split": "tune",
                        "asset_class_bucket": bucket,
                        "strategy": composite_strategy_id,
                        "entry_variant": variant_name,
                        "timeframe": "1h",
                        "stop_pct": profile.stop_pct,
                        "tp_pct": profile.tp_pct,
                        "trailing_pct": profile.trailing_pct,
                        "max_hold_days": profile.max_hold_days,
                    }
                    run_id = runner.run_backtest(
                        _cached_strategy_fn(module.make_pick_entries(variant), signal_cache),
                        list(symbols),
                        profile,
                        sliced,
                        20260804,
                        params,
                        composite_strategy_id,
                        conn,
                    )
                    trades = bt_ledger.get_trades_for_run(conn, run_id)
                    results.append(
                        {
                            "run_id": run_id,
                            "params": params,
                            "metrics": metrics.compute_metrics(trades),
                        }
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
                _write_checkpoint_atomic(CHECKPOINT_PATH, all_records)
                print(f"unit done: {key}", flush=True)

    # Top-5 per (strategy, bucket) group, variants concatenated (D-10).
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for record in checkpointed.values():
        groups.setdefault(
            (record["strategy"], record["bucket"], record["regime"]), []
        ).extend(record["results"])

    module_by_name = {name: (variants, module) for name, variants, module in _STRATEGY_SPECS}
    serialized_oos = []
    survivors = []
    candidates_out = []
    for (strategy_name, bucket, regime_label), combined in groups.items():
        regime = next(r for r in REGIMES_1H if r.bucket == bucket)
        if bucket not in frames_by_bucket:
            frames_by_bucket[bucket] = _load_bucket_frames(conn, bucket)
        oos_sliced = _slice_bars(frames_by_bucket[bucket], regime.oos_start, regime.oos_end)

        for candidate in sweep.select_top5(combined):
            params = candidate["params"]
            candidates_out.append(candidate)
            variants, module = module_by_name[strategy_name]
            from trader.backtest.config import EXIT_PROFILE

            profile = EXIT_PROFILE(
                stop_pct=params["stop_pct"],
                tp_pct=params["tp_pct"],
                scale_out=(),
                trailing_pct=params["trailing_pct"],
                max_hold_days=params["max_hold_days"],
                eod_flat=False,
            )
            oos_run_id = runner.run_backtest(
                _cached_strategy_fn(
                    module.make_pick_entries(variants[params["entry_variant"]]), {}
                ),
                list(universe.UNIVERSE_BY_BUCKET[bucket]),
                profile,
                oos_sliced,
                20260804,
                {**params, "split": "oos", "sweep_id": SWEEP_ID_HOURLY},
                f"{strategy_name}_{bucket}",
                conn,
            )
            oos_metrics = metrics.compute_metrics(bt_ledger.get_trades_for_run(conn, oos_run_id))
            verdict = sweep.determine_survivor(oos_metrics)
            serialized_oos.append(
                {
                    "candidate": _strip_strategy_fn(candidate),
                    "oos_run_id": oos_run_id,
                    "oos_metrics": oos_metrics,
                    "verdict": verdict,
                }
            )
            if verdict == "survivor":
                survivors.append(
                    {
                        "profile_name": params["profile_name"],
                        "strategy_id": f"{strategy_name}_{bucket}",
                        "bucket": bucket,
                        "timeframe": "1h",
                        "entry_variant": params["entry_variant"],
                        "stop_pct": params["stop_pct"],
                        "tp_pct": params["tp_pct"],
                        "trailing_pct": params["trailing_pct"],
                        "max_hold_days": params["max_hold_days"],
                        "pf_floor": PF_FLOOR,
                        "max_dd_kill": _max_drawdown_trigger(oos_metrics.get("max_drawdown")),
                        "consecutive_loss_kill": CONSECUTIVE_LOSS_KILL,
                        "backtest_run_id": candidate["run_id"],
                        "oos_run_id": oos_run_id,
                        "oos_result_ref": str(EVIDENCE_PATH),
                    }
                )

    evidence = {
        "sweep_id": SWEEP_ID_HOURLY,
        "frozen_hash_hourly": FROZEN_HASH_HOURLY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase_gate_note": (
            "Registration requires owner approval via register_entrant.py, a "
            "signals.py route for the hourly family, and the crypto leg on an "
            "HOURLY cadence before any survivor trades."
        ),
        "tune_top5": [_strip_strategy_fn(c) for c in candidates_out],
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
