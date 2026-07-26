"""Fast-fixture tests for trader.backtest.run_tune_sweep_all_v2 (Plan 03-08
Task 2, STRAT-03/04).

Proves the real wiring -- both real strategy_fn agents' v2 variant
factories (momentum_v2.make_pick_entries, breakout_v2.make_pick_entries)
driven through the real trader.backtest.sweep_v2 engine, the composite
`f"{strategy_id}_{bucket}"` strategy_id tagging convention, the JSON-lines
checkpoint's crash-safe atomic-write + resume-skip behavior, and the
orphan-row cleanup path for an interrupted prior attempt (T-03-26) -- using
a tiny synthetic universe/grid injected via monkeypatch, never the real
270/360-cell grid or real cached history. Task 2's real acceptance run
drives the real ~10,800-run sweep separately.
"""

from __future__ import annotations

import json
import time

import pandas as pd
import pytest

from trader.backtest import config, ledger, regimes_v2, run_tune_sweep_all_v2, sweep, sweep_v2, universe
from trader.backtest.strategies import breakout_v2, momentum_v2
from trader.data import db as data_db


@pytest.fixture
def data_conn(tmp_db_path):
    """A live connection to a fresh temp DB (mirrors
    tests/test_run_tune_sweep_all.py's data_conn fixture)."""
    connection = data_db.get_connection(tmp_db_path)
    yield connection
    connection.close()


def _bars(closes, highs, lows, volumes, start="2023-01-01"):
    n = len(closes)
    assert len(highs) == n and len(lows) == n and len(volumes) == n
    index = pd.date_range(start, periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": [c - 1.0 for c in closes],
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        },
        index=index,
    )


def _riser_bars() -> pd.DataFrame:
    """Identical shape to tests/test_run_tune_sweep_all.py's _riser_bars --
    fires momentum_v2's "base" AND "loose" variants (2.5x volume spike
    clears both 2.0x and 1.5x floors, RSI=100 clears both 60/50 floors) but
    never "strict" (3.0x floor, 2.5x spike does not clear it) -- proves the
    real per-variant wiring without requiring every variant to fire."""
    closes = [90.0] * 6 + [100.0 + i for i in range(14)] + [120.0]
    closes += [120.0 + (i + 1) for i in range(24)]
    highs = [c + 1.0 for c in closes]
    lows = [c - 2.0 for c in closes]
    volumes = [1000.0] * 20 + [2500.0] + [1000.0] * 24
    return _bars(closes, highs, lows, volumes)


def _breaker_bars() -> pd.DataFrame:
    """Identical shape to tests/test_run_tune_sweep_all.py's _breaker_bars
    -- fires breakout_v2's "base" AND "loose" variants (1.6x volume
    confirm clears 1.5x/1.2x floors) but never "strict" (2.0x floor)."""
    trend_closes = [56.0 + (i + 1) * 0.5 for i in range(24)]
    closes = [50.0] * 20 + [56.0] + trend_closes
    highs = [52.0] * 20 + [56.3] + [c + 2.0 for c in trend_closes]
    lows = [48.0] * 20 + [55.7] + [c - 2.0 for c in trend_closes]
    volumes = [1000.0] * 20 + [1600.0] + [1000.0] * 24
    return _bars(closes, highs, lows, volumes)


def _tiny_grid(bucket):
    """A 2x2x1x1 = 4-cell injected grid standing in for the real 270/360-
    cell exit_profile_grid."""
    for stop_pct in (-0.05, -0.10):
        for tp_pct in (0.05, 0.10):
            yield config.EXIT_PROFILE(
                stop_pct=stop_pct,
                tp_pct=tp_pct,
                scale_out=(),
                trailing_pct=None,
                max_hold_days=15,
                eod_flat=False,
            )


def _fake_get_daily_bars(symbol, asset_class=None, conn=None):
    if symbol == "RISER":
        return _riser_bars()
    if symbol == "BREAKER":
        return _breaker_bars()
    raise ValueError(f"unexpected fixture symbol {symbol!r}")


_FIXTURE_BUCKETS = ("bucketa",)


def _fixture_regimes():
    return tuple(
        regimes_v2.Regime(
            bucket=bucket,
            label=label,
            tune_start="2023-01-01",
            tune_end="2023-02-20",
            oos_start="2023-02-21",
            oos_end="2023-03-01",
        )
        for bucket in _FIXTURE_BUCKETS
        for label in ("regime1",)
    )


def _patch_common(monkeypatch, tmp_path, output_name="tune_top5_v2.json", checkpoint_name="tune_v2.checkpoint.jsonl"):
    fixture_universe = {bucket: ["RISER", "BREAKER"] for bucket in _FIXTURE_BUCKETS}
    fixture_regimes = _fixture_regimes()

    output_path = tmp_path / output_name
    checkpoint_path = tmp_path / checkpoint_name

    original_select_top5 = sweep.select_top5
    monkeypatch.setattr(
        sweep, "select_top5", lambda results: original_select_top5(results, min_trades=1)
    )
    monkeypatch.setattr(universe, "UNIVERSE_BY_BUCKET", fixture_universe)
    monkeypatch.setattr(regimes_v2, "REGIMES_V2", fixture_regimes)
    monkeypatch.setattr(run_tune_sweep_all_v2, "get_daily_bars", _fake_get_daily_bars)
    monkeypatch.setattr(run_tune_sweep_all_v2, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(run_tune_sweep_all_v2, "CHECKPOINT_PATH", checkpoint_path)

    return output_path, checkpoint_path


# --- End-to-end fixture wiring ------------------------------------------


def test_run_tune_sweep_all_v2_end_to_end_with_tiny_fixture(data_conn, monkeypatch, tmp_path):
    output_path, checkpoint_path = _patch_common(monkeypatch, tmp_path)

    start = time.perf_counter()
    result_path = run_tune_sweep_all_v2.main(conn=data_conn, grid_fn=_tiny_grid)
    elapsed = time.perf_counter() - start

    assert elapsed < 10.0, f"fixture sweep took {elapsed:.2f}s, expected under 10s"
    assert result_path == output_path
    assert output_path.exists()
    assert checkpoint_path.exists()

    # 2 strategies x 1 bucket x 1 regime x 3 variants = 6 checkpointed units.
    checkpoint_lines = [l for l in checkpoint_path.read_text().splitlines() if l.strip()]
    assert len(checkpoint_lines) == 6

    candidates = json.loads(output_path.read_text())
    assert isinstance(candidates, list)
    assert len(candidates) > 0, "fixture bars are tuned to guarantee real entries (base/loose variants)"

    for candidate in candidates:
        assert set(candidate.keys()) == {
            "run_id",
            "params",
            "metrics",
            "strategy_id",
            "bucket",
            "regime",
        }
        assert candidate["bucket"] in _FIXTURE_BUCKETS
        assert candidate["regime"] == "regime1"

        prefix = (
            "momentum" if candidate["strategy_id"].startswith("momentum_") else "breakout"
        )
        assert candidate["strategy_id"] == f"{prefix}_{candidate['bucket']}"
        assert candidate["strategy_id"] == candidate["params"]["strategy"]
        assert candidate["params"]["entry_variant"] in ("strict", "base", "loose")


# --- Checkpoint-resume: only missing units re-executed -------------------


def test_run_tune_sweep_all_v2_resumes_and_skips_already_checkpointed_units(
    data_conn, monkeypatch, tmp_path
):
    output_path, checkpoint_path = _patch_common(monkeypatch, tmp_path)

    # Pre-populate ONE of the 6 units in the checkpoint file, simulating a
    # prior completed-but-interrupted run.
    pre_populated_record = {
        "strategy": "momentum",
        "bucket": "bucketa",
        "regime": "regime1",
        "variant": "base",
        "results": [
            {
                "run_id": 999999,
                "params": {
                    "profile_name": "precomputed",
                    "sweep_id": "v2",
                    "regime": "regime1",
                    "split": "tune",
                    "asset_class_bucket": "bucketa",
                    "strategy": "momentum_bucketa",
                    "entry_variant": "base",
                    "stop_pct": -0.05,
                    "tp_pct": 0.05,
                    "trailing_pct": None,
                    "max_hold_days": 15,
                },
                "metrics": {"trade_count": 40, "profit_factor": 3.5},
            }
        ],
    }
    checkpoint_path.write_text(json.dumps(pre_populated_record) + "\n")

    call_log: list[tuple] = []
    original_run_tune_sweep_v2 = sweep_v2.run_tune_sweep_v2

    def _spy_run_tune_sweep_v2(strategy_fn, strategy_id, bucket, regime, entry_variant_name, *args, **kwargs):
        call_log.append((strategy_id, bucket, regime.label, entry_variant_name))
        return original_run_tune_sweep_v2(
            strategy_fn, strategy_id, bucket, regime, entry_variant_name, *args, **kwargs
        )

    monkeypatch.setattr(sweep_v2, "run_tune_sweep_v2", _spy_run_tune_sweep_v2)

    run_tune_sweep_all_v2.main(conn=data_conn, grid_fn=_tiny_grid)

    # The pre-populated (momentum, bucketa, regime1, base) unit must NEVER
    # be re-executed -- only the 5 remaining units.
    assert ("momentum_bucketa", "bucketa", "regime1", "base") not in call_log
    assert len(call_log) == 5

    # Checkpoint now has all 6 units, and the pre-populated one's results
    # are reused verbatim (never overwritten with a freshly re-run result).
    checkpointed = run_tune_sweep_all_v2._read_checkpoint(checkpoint_path)
    reused = checkpointed[("momentum", "bucketa", "regime1", "base")]
    assert reused["results"][0]["run_id"] == 999999


# --- Crash-safe accounting: orphan rows cleaned up before re-run ---------


def test_run_tune_sweep_all_v2_deletes_orphan_rows_before_rerunning_incomplete_unit(
    data_conn, monkeypatch, tmp_path
):
    """Simulates a crash mid-unit: backtest_runs/backtest_trades rows exist
    for (momentum, bucketa, regime1, base) from an incomplete prior
    attempt, but the checkpoint file has NO entry for that unit (the crash
    happened before the checkpoint line was written). Re-running main()
    must delete the orphaned rows before re-running the unit, so the final
    row count for that unit matches the grid size exactly -- never double-
    counted."""
    output_path, checkpoint_path = _patch_common(monkeypatch, tmp_path)

    orphan_run_id = ledger.record_run(
        data_conn,
        strategy_id="momentum_bucketa",
        profile_name="orphan-from-interrupted-attempt",
        params={
            "sweep_id": "v2",
            "asset_class_bucket": "bucketa",
            "regime": "regime1",
            "entry_variant": "base",
            "split": "tune",
        },
        seed=1,
    )
    ledger.record_trade(
        data_conn,
        run_id=orphan_run_id,
        position_id="RISER:2023-01-05",
        strategy_id="momentum_bucketa",
        symbol="RISER",
        asset_class="stock",
        entry_ts="2023-01-05",
        entry_price=100.0,
        exit_ts="2023-01-10",
        exit_price=105.0,
        qty=100.0,
        fees=1.0,
        slippage=0.5,
        pnl=498.5,
        exit_reason="stop",
    )

    # No checkpoint entry exists for this unit -- checkpoint file is empty.
    assert not checkpoint_path.exists()

    run_tune_sweep_all_v2.main(conn=data_conn, grid_fn=_tiny_grid)

    # The orphan run_id must be gone -- deleted before the unit was re-run.
    orphan_row = data_conn.execute(
        "SELECT run_id FROM backtest_runs WHERE run_id = ?", (orphan_run_id,)
    ).fetchone()
    assert orphan_row is None, "orphan backtest_runs row must be deleted before rerun"

    orphan_trades = data_conn.execute(
        "SELECT trade_id FROM backtest_trades WHERE run_id = ?", (orphan_run_id,)
    ).fetchall()
    assert orphan_trades == [], "orphan backtest_trades rows must be deleted before rerun"

    # Exactly 4 (tiny grid size) backtest_runs rows now exist for this exact
    # unit's provenance -- no duplicates, no leftover orphan.
    rows = data_conn.execute(
        "SELECT params_json FROM backtest_runs WHERE strategy_id = ?", ("momentum_bucketa",)
    ).fetchall()
    matching = [
        r for (r,) in rows
        if json.loads(r).get("sweep_id") == "v2"
        and json.loads(r).get("regime") == "regime1"
        and json.loads(r).get("entry_variant") == "base"
    ]
    assert len(matching) == 4


# --- Checkpoint is written atomically -------------------------------------


def test_checkpoint_write_is_atomic_and_never_leaves_a_temp_file(
    data_conn, monkeypatch, tmp_path
):
    output_path, checkpoint_path = _patch_common(monkeypatch, tmp_path)

    run_tune_sweep_all_v2.main(conn=data_conn, grid_fn=_tiny_grid)

    assert checkpoint_path.exists()
    leftover_temp_files = list(tmp_path.glob(f"{checkpoint_path.name}.*.tmp"))
    assert leftover_temp_files == [], "no temp files should remain after an atomic checkpoint write"


def test_read_checkpoint_skips_malformed_trailing_line(tmp_path):
    checkpoint_path = tmp_path / "tune_v2.checkpoint.jsonl"
    good_record = {
        "strategy": "momentum",
        "bucket": "bucketa",
        "regime": "regime1",
        "variant": "base",
        "results": [],
    }
    checkpoint_path.write_text(
        json.dumps(good_record) + "\n" + '{"strategy": "breakout", "bucket": "bucketa"' # truncated/malformed
    )

    checkpointed = run_tune_sweep_all_v2._read_checkpoint(checkpoint_path)

    assert len(checkpointed) == 1
    assert ("momentum", "bucketa", "regime1", "base") in checkpointed


# --- Real run-count arithmetic self-check (T-03-27) -----------------------


def test_expected_tune_sweep_run_count_v2_matches_real_grid_and_universe_sizes():
    """D-14's pre-registered ~10,800-run estimate, computed from the REAL
    (non-fixture) exit_grid/universe/regimes_v2 sizes -- 2 strategies x 3
    entry variants x 2 regimes x 270 cells for stock and
    crypto_major_legacy_meme, plus 2 x 3 x 2 x 360 for new_memecoin."""
    from trader.backtest import exit_grid

    total = 0
    for bucket, symbols in universe.UNIVERSE_BY_BUCKET.items():
        grid_size = sum(1 for _ in exit_grid.exit_profile_grid(bucket))
        regime_count = len([r for r in regimes_v2.REGIMES_V2 if r.bucket == bucket])
        total += 2 * 3 * regime_count * grid_size  # 2 strategies x 3 variants

    assert total == run_tune_sweep_all_v2.EXPECTED_TUNE_SWEEP_RUN_COUNT_V2
    assert total == 10_800
