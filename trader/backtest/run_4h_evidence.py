r"""4-hour evidence run (owner standing order: find a crypto strategy that
WORKS; daily and 1h entries both failed OOS -- 4h is the untested middle
where per-trade costs bite ~4x less than hourly).

Same frozen surface as the hourly track, byte-identical and verified by
the SAME gate: hourly_reversion + hourly_squeeze signals and the 24-cell
grid interpret their bar-count constants on 4h bars (BB(20) = 20 four-hour
bars; hold 24 bars = 4 days; hold 168 = 4 weeks). Bars are the cached 1h
candles resampled 4:1 on UTC boundaries -- no new fetching, no partial
buckets (a trailing incomplete 4h group is dropped).

Provenance sweep_id="4h_v1". Same registration gate: NEVER writes
strategy_registry.

    .venv\Scripts\python.exe -m trader.backtest.run_4h_evidence
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
from trader.backtest.run_hourly_evidence import (
    _cached_strategy_fn,
    _hourly_frame,
    _strip_strategy_fn,
)
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

EVIDENCE_PATH = Path("reports/backtests/4h_evidence.json")
CHECKPOINT_PATH = Path("reports/backtests/4h_tune.checkpoint.jsonl")

SWEEP_ID_4H = "4h_v1"

_STRATEGY_SPECS = (
    ("h4reversion", hourly_reversion.HOURLY_REVERSION_VARIANTS, hourly_reversion),
    ("h4squeeze", hourly_squeeze.HOURLY_SQUEEZE_VARIANTS, hourly_squeeze),
)

EXPECTED_TUNE_RUN_COUNT_4H = 192


def resample_1h_to_4h(frame: pd.DataFrame) -> pd.DataFrame:
    """OHLCV 1h -> 4h on UTC boundaries: open=first, high=max, low=min,
    close=last, volume=sum. Trailing INCOMPLETE 4h buckets are dropped (a
    partial bucket's close does not exist yet -- the system never lies to
    itself). Buckets with fewer than 4 source bars mid-history (exchange
    outages) are kept: their OHLCV is still real trade data."""
    grouped = frame.resample("4h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    grouped = grouped.dropna(subset=["open", "close"])
    if len(frame) and len(grouped):
        last_bucket_start = grouped.index[-1]
        source_in_last = frame[frame.index >= last_bucket_start]
        expected_last = min(4, len(source_in_last))
        if len(source_in_last) < 4 and expected_last < 4:
            grouped = grouped.iloc[:-1]
    return grouped


def _load_bucket_frames_4h(conn, bucket: str) -> dict[str, pd.DataFrame]:
    frames = {}
    for symbol in universe.UNIVERSE_BY_BUCKET[bucket]:
        rows = get_hourly_bars(conn, symbol)
        if rows:
            frames[symbol] = resample_1h_to_4h(_hourly_frame(rows))
    return frames


def main(conn=None) -> Path:
    """Run the full 4h evidence cycle and write EVIDENCE_PATH."""
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
                    frames_by_bucket[bucket] = _load_bucket_frames_4h(conn, bucket)

                sliced = _slice_bars(
                    frames_by_bucket[bucket], regime.tune_start, regime.tune_end
                )
                signal_cache: dict = {}
                results = []
                for profile in hourly_exit_profile_grid(bucket):
                    profile_name = (
                        f"{composite_strategy_id}_{regime.label}_{variant_name}_tune_"
                        f"stop{profile.stop_pct}_tp{profile.tp_pct}_"
                        f"trail{profile.trailing_pct}_hold{profile.max_hold_days}x4h"
                    )
                    params = {
                        "profile_name": profile_name,
                        "sweep_id": SWEEP_ID_4H,
                        "regime": regime.label,
                        "split": "tune",
                        "asset_class_bucket": bucket,
                        "strategy": composite_strategy_id,
                        "entry_variant": variant_name,
                        "timeframe": "4h",
                        "stop_pct": profile.stop_pct,
                        "tp_pct": profile.tp_pct,
                        "trailing_pct": profile.trailing_pct,
                        "max_hold_days": profile.max_hold_days,
                    }
                    run_id = runner.run_backtest(
                        _cached_strategy_fn(module.make_pick_entries(variant), signal_cache),
                        list(symbols), profile, sliced, 20260814, params,
                        composite_strategy_id, conn,
                    )
                    trades = bt_ledger.get_trades_for_run(conn, run_id)
                    results.append(
                        {"run_id": run_id, "params": params,
                         "metrics": metrics.compute_metrics(trades)}
                    )

                record = {
                    "strategy": strategy_name, "bucket": bucket,
                    "regime": regime.label, "variant": variant_name,
                    "results": results,
                }
                checkpointed[key] = record
                all_records.append(record)
                _write_checkpoint_atomic(CHECKPOINT_PATH, all_records)
                print(f"unit done: {key}", flush=True)

    groups: dict[tuple[str, str, str], list[dict]] = {}
    for record in checkpointed.values():
        groups.setdefault(
            (record["strategy"], record["bucket"], record["regime"]), []
        ).extend(record["results"])

    module_by_name = {n: (v, m) for n, v, m in _STRATEGY_SPECS}
    serialized_oos = []
    survivors = []
    candidates_out = []
    from trader.backtest.config import EXIT_PROFILE

    for (strategy_name, bucket, regime_label), combined in groups.items():
        regime = next(r for r in REGIMES_1H if r.bucket == bucket)
        if bucket not in frames_by_bucket:
            frames_by_bucket[bucket] = _load_bucket_frames_4h(conn, bucket)
        oos_sliced = _slice_bars(frames_by_bucket[bucket], regime.oos_start, regime.oos_end)

        for candidate in sweep.select_top5(combined):
            params = candidate["params"]
            candidates_out.append(candidate)
            variants, module = module_by_name[strategy_name]
            profile = EXIT_PROFILE(
                stop_pct=params["stop_pct"], tp_pct=params["tp_pct"], scale_out=(),
                trailing_pct=params["trailing_pct"],
                max_hold_days=params["max_hold_days"], eod_flat=False,
            )
            oos_run_id = runner.run_backtest(
                _cached_strategy_fn(
                    module.make_pick_entries(variants[params["entry_variant"]]), {}
                ),
                list(universe.UNIVERSE_BY_BUCKET[bucket]), profile, oos_sliced,
                20260814, {**params, "split": "oos", "sweep_id": SWEEP_ID_4H},
                f"{strategy_name}_{bucket}", conn,
            )
            oos_metrics = metrics.compute_metrics(bt_ledger.get_trades_for_run(conn, oos_run_id))
            verdict = sweep.determine_survivor(oos_metrics)
            serialized_oos.append(
                {"candidate": _strip_strategy_fn(candidate), "oos_run_id": oos_run_id,
                 "oos_metrics": oos_metrics, "verdict": verdict}
            )
            if verdict == "survivor":
                survivors.append(
                    {
                        "profile_name": params["profile_name"],
                        "strategy_id": f"{strategy_name}_{bucket}",
                        "bucket": bucket, "timeframe": "4h",
                        "entry_variant": params["entry_variant"],
                        "stop_pct": params["stop_pct"], "tp_pct": params["tp_pct"],
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
        "sweep_id": SWEEP_ID_4H,
        "frozen_hash_hourly": FROZEN_HASH_HOURLY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase_gate_note": (
            "A 4h survivor additionally needs a signals.py route (h4reversion/"
            "h4squeeze bases) and 4h-aware scan cadence in the crypto leg "
            "before trading -- built on registration, not before evidence."
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
