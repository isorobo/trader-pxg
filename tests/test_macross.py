"""MA-crossover entrant tests: cross-event-only entries, both published
variants, the freeze gate, and the evidence driver's arithmetic."""

from __future__ import annotations

import random

import pandas as pd
import pytest

from trader.backtest.frozen_config_macross import (
    FROZEN_HASH_MACROSS,
    compute_hash_macross,
    verify_frozen_macross,
)
from trader.backtest.iterator import PointInTimeIterator
from trader.backtest.strategies import macross


def _bars(closes: list[float], end="2020-06-30") -> pd.DataFrame:
    periods = len(closes)
    dates = pd.bdate_range(end=end, periods=periods, tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.5 for c in closes],
            "low": [c - 0.5 for c in closes],
            "close": closes,
            "volume": [1_000_000.0] * periods,
        },
        index=dates,
    )


def _fire(variant_name: str, closes: list[float]) -> list[str]:
    bars = _bars(closes)
    iterator = PointInTimeIterator({"AAPL": bars})
    last_date = bars.index[-1]
    iterator.advance_to(last_date.date())
    pick = macross.make_pick_entries(macross.MACROSS_VARIANTS[variant_name])
    return pick(iterator, last_date, set(), random.Random(0))


def _v_shape(down_days: int, up_days: int, total: int = 260) -> list[float]:
    """A long decline then a sharp recovery -- the canonical cross-up
    setup. Pad the front with a flat plateau to reach `total` bars."""
    flat = [100.0] * (total - down_days - up_days)
    down = [100.0 - 0.5 * (i + 1) for i in range(down_days)]
    bottom = down[-1]
    up = [bottom + 2.0 * (i + 1) for i in range(up_days)]
    return flat + down + up


# ---------------------------------------------------------------------------
# Signal semantics
# ---------------------------------------------------------------------------


def test_fast_ema_cross_fires_exactly_on_the_cross_event():
    """Walk the recovery day by day: the variant fires on exactly ONE day
    (the cross), never before, never after -- alignment alone never
    re-fires."""
    down_days, total = 60, 260
    fire_days = [
        up_days
        for up_days in range(1, 40)
        if _fire("fast_ema_20_50", _v_shape(down_days, up_days, total)) == ["AAPL"]
    ]
    assert len(fire_days) == 1


def test_golden_cross_needs_201_bars():
    closes = _v_shape(30, 20, total=150)  # < 201 bars
    assert _fire("golden_sma_50_200", closes) == []


def test_golden_cross_fires_after_long_recovery():
    """A deep 120-day decline then a strong 90-day recovery drives the 50
    SMA up through the 200 SMA exactly once."""
    down_days, total = 120, 420
    fire_days = [
        up_days
        for up_days in range(30, 120)
        if _fire("golden_sma_50_200", _v_shape(down_days, up_days, total)) == ["AAPL"]
    ]
    assert len(fire_days) == 1


def test_steady_uptrend_never_fires_either_variant():
    """Fast stays above slow throughout a monotonic rise -- no cross event,
    no entry (the file's alignment-alone trap)."""
    rise = [100.0 + 0.5 * i for i in range(260)]
    assert _fire("fast_ema_20_50", rise) == []
    assert _fire("golden_sma_50_200", rise) == []


def test_open_positions_never_refire():
    down_days = 60
    fired_closes = next(
        _v_shape(down_days, up_days)
        for up_days in range(1, 40)
        if _fire("fast_ema_20_50", _v_shape(down_days, up_days)) == ["AAPL"]
    )
    bars = _bars(fired_closes)
    iterator = PointInTimeIterator({"AAPL": bars})
    last_date = bars.index[-1]
    iterator.advance_to(last_date.date())
    pick = macross.make_pick_entries(macross.MACROSS_VARIANTS["fast_ema_20_50"])
    assert pick(iterator, last_date, {"AAPL"}, random.Random(0)) == []


def test_variants_are_the_published_systems():
    fast = macross.MACROSS_VARIANTS["fast_ema_20_50"]
    golden = macross.MACROSS_VARIANTS["golden_sma_50_200"]
    assert (fast.kind, fast.fast, fast.slow) == ("ema", 20, 50)
    assert (golden.kind, golden.fast, golden.slow) == ("sma", 50, 200)
    assert set(macross.MACROSS_VARIANTS) == {"fast_ema_20_50", "golden_sma_50_200"}


# ---------------------------------------------------------------------------
# Freeze gate + driver arithmetic
# ---------------------------------------------------------------------------


def test_committed_macross_hash_matches_file():
    assert compute_hash_macross() == FROZEN_HASH_MACROSS


def test_tampered_macross_file_raises(tmp_path):
    from pathlib import Path

    from trader.backtest import frozen_config_macross as gate

    repo_root = Path(gate.__file__).resolve().parents[2]
    for rel in gate.FROZEN_FILES_MACROSS:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((repo_root / rel).read_bytes() + b"# tampered\n")

    with pytest.raises(RuntimeError, match="integrity check failed"):
        verify_frozen_macross(repo_root=tmp_path)


def test_expected_tune_run_count_matches_real_grid_and_regimes():
    from trader.backtest import exit_grid, regimes_v2, universe
    from trader.backtest.run_macross_evidence import (
        ALL_BUCKETS,
        EXPECTED_TUNE_RUN_COUNT_MACROSS,
    )

    expected = 0
    for bucket in ALL_BUCKETS:
        regimes = [r for r in regimes_v2.REGIMES_V2 if r.bucket == bucket]
        grid_size = len(list(exit_grid.exit_profile_grid(bucket)))
        expected += len(macross.MACROSS_VARIANTS) * len(regimes) * grid_size
    assert expected == EXPECTED_TUNE_RUN_COUNT_MACROSS


def test_evidence_driver_verifies_macross_gate_before_any_work(monkeypatch):
    from trader.backtest import run_macross_evidence

    monkeypatch.setattr(
        run_macross_evidence,
        "verify_frozen_macross",
        lambda: (_ for _ in ()).throw(RuntimeError("integrity check failed")),
    )

    with pytest.raises(RuntimeError, match="integrity check failed"):
        run_macross_evidence.main(conn=object())
