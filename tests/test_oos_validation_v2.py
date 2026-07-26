"""Fast-fixture test for trader.backtest.run_oos_validation_all_v2 (Plan
03-08 Task 2, STRAT-05).

Proves the real wiring -- v2 candidates' composite strategy_id resolved
back to a base strategy name, that base name's entry_variant resolved
through momentum_v2.MOMENTUM_VARIANTS/breakout_v2.BREAKOUT_VARIANTS via the
matching make_pick_entries factory, driven through the real
trader.backtest.sweep_v2.run_oos_validation_v2 -- using a tiny synthetic
universe/regime injected via monkeypatch. Mirrors
tests/test_run_tune_sweep_all.py's sibling pattern one layer down.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from trader.backtest import regimes_v2, run_oos_validation_all_v2, universe
from trader.data import db as data_db


@pytest.fixture
def data_conn(tmp_db_path):
    connection = data_db.get_connection(tmp_db_path)
    yield connection
    connection.close()


def _bars(closes, highs, lows, volumes, start="2023-01-01"):
    n = len(closes)
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
    """Fires momentum_v2's "base"/"loose" variants exactly once (2.5x
    volume spike, RSI=100) -- identical shape to
    tests/test_run_tune_sweep_all_v2.py's _riser_bars, reused here for the
    OOS window."""
    closes = [90.0] * 6 + [100.0 + i for i in range(14)] + [120.0]
    closes += [120.0 + (i + 1) for i in range(24)]
    highs = [c + 1.0 for c in closes]
    lows = [c - 2.0 for c in closes]
    volumes = [1000.0] * 20 + [2500.0] + [1000.0] * 24
    return _bars(closes, highs, lows, volumes)


_FIXTURE_REGIME = regimes_v2.Regime(
    bucket="bucketa",
    label="regime1",
    tune_start="2023-01-01",
    tune_end="2023-02-20",
    oos_start="2023-02-21",
    oos_end="2023-03-10",
)


def _fixture_candidate(run_id=1):
    return {
        "run_id": run_id,
        "strategy_id": "momentum_bucketa",
        "bucket": "bucketa",
        "regime": "regime1",
        "metrics": {"trade_count": 5, "profit_factor": 2.0},
        "params": {
            "profile_name": "momentum_bucketa_regime1_base_tune_profile",
            "sweep_id": "v2",
            "regime": "regime1",
            "split": "tune",
            "asset_class_bucket": "bucketa",
            "strategy": "momentum_bucketa",
            "entry_variant": "base",
            "stop_pct": -0.10,
            "tp_pct": 0.20,
            "trailing_pct": None,
            "max_hold_days": 15,
        },
    }


def test_run_oos_validation_all_v2_resolves_variant_and_writes_full_verdict_list(
    data_conn, monkeypatch, tmp_path
):
    input_path = tmp_path / "tune_top5_v2.json"
    output_path = tmp_path / "oos_results_v2.json"
    input_path.write_text(json.dumps([_fixture_candidate()]))

    def _fake_get_daily_bars(symbol, asset_class=None, conn=None):
        assert symbol == "RISER"
        return _riser_bars()

    monkeypatch.setattr(universe, "UNIVERSE_BY_BUCKET", {"bucketa": ["RISER"]})
    monkeypatch.setattr(regimes_v2, "REGIMES_V2", (_FIXTURE_REGIME,))
    monkeypatch.setattr(run_oos_validation_all_v2, "get_daily_bars", _fake_get_daily_bars)
    monkeypatch.setattr(run_oos_validation_all_v2, "INPUT_PATH", input_path)
    monkeypatch.setattr(run_oos_validation_all_v2, "OUTPUT_PATH", output_path)

    result_path = run_oos_validation_all_v2.main(conn=data_conn)

    assert result_path == output_path
    assert output_path.exists()

    oos_results = json.loads(output_path.read_text())
    assert len(oos_results) == 1

    entry = oos_results[0]
    assert set(entry.keys()) == {"candidate", "oos_run_id", "oos_metrics", "verdict"}
    assert "strategy_fn" not in entry["candidate"], "the non-serializable callable must never leak"
    assert entry["candidate"]["params"]["entry_variant"] == "base"
    assert entry["verdict"] in ("survivor", "killed", "insufficient_sample")


def test_base_strategy_id_strips_bucket_suffix():
    assert run_oos_validation_all_v2._base_strategy_id("momentum_bucketa", "bucketa") == "momentum"
    assert run_oos_validation_all_v2._base_strategy_id("breakout_stock", "stock") == "breakout"

    with pytest.raises(ValueError):
        run_oos_validation_all_v2._base_strategy_id("momentum_stock", "crypto_major_legacy_meme")
