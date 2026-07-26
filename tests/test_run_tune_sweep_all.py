"""Fast-fixture test for trader.backtest.run_tune_sweep_all (Plan 03-04
Task 1).

Proves the real wiring -- both real strategy_fn agents
(momentum.pick_entries, breakout.pick_entries) driven through the real
trader.backtest.sweep engine, the composite `f"{strategy_id}_{bucket}"`
strategy_id tagging convention, and the written JSON artifact's schema --
using a tiny synthetic universe/grid injected via monkeypatch, never the
real 270/360-cell grid or real cached history. Plan 03-04 Task 2 drives the
real acceptance run separately (tests/test_run_tune_sweep_all.py is
deliberately never the thing that proves the real sweep ran; it only proves
this module's wiring is correct, matching tests/test_sweep_engine.py's
sibling pattern one layer down).
"""

from __future__ import annotations

import json
import time

import pandas as pd
import pytest

from trader.backtest import config, regimes, run_tune_sweep_all, sweep, universe
from trader.data import db as data_db


@pytest.fixture
def data_conn(tmp_db_path):
    """A live connection to a fresh temp DB (mirrors
    tests/test_sweep_engine.py's data_conn fixture)."""
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
    """45 daily bars tuned to fire momentum.pick_entries exactly once (day
    20: a single 2.5x volume spike breaking the prior 20-day high with
    RSI=100, matching tests/test_strategy_momentum.py's _FIRES_CLOSES
    shape), then a gentle continued uptrend at baseline volume so the
    signal never repeats -- one deterministic entry. Ranges (high-low) are
    held constant at 3.0 throughout, which trivially also satisfies
    breakout.pick_entries's NR7 check on day20 (deliberate -- proves both
    real agents wire through this module correctly against the same bars)."""
    closes = [90.0] * 6 + [100.0 + i for i in range(14)] + [120.0]
    closes += [120.0 + (i + 1) for i in range(24)]
    highs = [c + 1.0 for c in closes]
    lows = [c - 2.0 for c in closes]
    volumes = [1000.0] * 20 + [2500.0] + [1000.0] * 24
    return _bars(closes, highs, lows, volumes)


def _breaker_bars() -> pd.DataFrame:
    """45 daily bars tuned to fire breakout.pick_entries exactly once (day
    20: a narrow-range (NR7) day breaking the prior 20-day high on a 1.6x
    volume confirmation), then a gentle continued uptrend with normal
    (non-narrow) ranges at baseline volume so the signal never repeats.
    Volume never reaches momentum's 2.0x floor, so momentum.pick_entries
    never fires here -- isolates breakout's own signal."""
    trend_closes = [56.0 + (i + 1) * 0.5 for i in range(24)]
    closes = [50.0] * 20 + [56.0] + trend_closes
    highs = [52.0] * 20 + [56.3] + [c + 2.0 for c in trend_closes]
    lows = [48.0] * 20 + [55.7] + [c - 2.0 for c in trend_closes]
    volumes = [1000.0] * 20 + [1600.0] + [1000.0] * 24
    return _bars(closes, highs, lows, volumes)


def _tiny_grid(bucket):
    """A 2x2x1x1 = 4-cell injected grid standing in for the real 270/360-
    cell exit_profile_grid -- ignores `bucket` (the real signature's
    contract) since this fixture universe has only one bucket shape."""
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


_FIXTURE_BUCKETS = ("bucketa", "bucketb", "bucketc")


def test_run_tune_sweep_all_end_to_end_with_tiny_fixture(
    data_conn, monkeypatch, tmp_path
):
    fixture_universe = {bucket: ["RISER", "BREAKER"] for bucket in _FIXTURE_BUCKETS}
    fixture_regimes = tuple(
        regimes.Regime(
            bucket=bucket,
            label=label,
            tune_start="2023-01-01",
            tune_end="2023-02-20",
            oos_start="2023-02-21",
            oos_end="2023-03-01",
        )
        for bucket in _FIXTURE_BUCKETS
        for label in ("regime1", "regime2")
    )

    def _fake_get_daily_bars(symbol, asset_class=None, conn=None):
        if symbol == "RISER":
            return _riser_bars()
        if symbol == "BREAKER":
            return _breaker_bars()
        raise ValueError(f"unexpected fixture symbol {symbol!r}")

    output_path = tmp_path / "tune_top5.json"

    # min_trades is patched from D-10's real floor (30) down to 1 -- this
    # tiny 2-symbol/45-bar fixture cannot plausibly produce 30 real trades
    # per cell; the real 30-trade floor is proven separately by
    # tests/test_sweep_engine.py's select_top5 unit tests and by Task 2's
    # real acceptance run. This wraps the REAL select_top5 (never
    # reimplements its ranking logic), only loosening the floor for the
    # fixture's benefit.
    original_select_top5 = sweep.select_top5
    monkeypatch.setattr(
        sweep, "select_top5", lambda results: original_select_top5(results, min_trades=1)
    )
    monkeypatch.setattr(universe, "UNIVERSE_BY_BUCKET", fixture_universe)
    monkeypatch.setattr(regimes, "REGIMES", fixture_regimes)
    monkeypatch.setattr(run_tune_sweep_all, "get_daily_bars", _fake_get_daily_bars)
    monkeypatch.setattr(run_tune_sweep_all, "OUTPUT_PATH", output_path)

    start = time.perf_counter()
    result_path = run_tune_sweep_all.main(conn=data_conn, grid_fn=_tiny_grid)
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0, f"fixture sweep took {elapsed:.2f}s, expected under 5s"
    assert result_path == output_path
    assert output_path.exists()

    candidates = json.loads(output_path.read_text())
    assert isinstance(candidates, list)
    # 2 strategies x 3 fixture buckets x 2 regimes x <=5 candidates = 60 max.
    assert len(candidates) <= 60
    assert len(candidates) > 0, "fixture bars are tuned to guarantee real entries"

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
        assert candidate["regime"] in {"regime1", "regime2"}

        # The composite tagging convention, asserted directly rather than
        # merely implied by the loop structure.
        assert candidate["strategy_id"].startswith(("momentum_", "breakout_"))
        prefix = (
            "momentum" if candidate["strategy_id"].startswith("momentum_") else "breakout"
        )
        assert candidate["strategy_id"] == f"{prefix}_{candidate['bucket']}"
        # The same composite string persisted into params_json["strategy"]
        # by run_tune_sweep (Plan 03-03) -- never allowed to drift.
        assert candidate["strategy_id"] == candidate["params"]["strategy"]
