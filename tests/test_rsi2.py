"""RSI(2) entrant tests: the frozen entry signal (200-day SMA filter +
RSI(2) oversold), its freeze gate, and the evidence driver's arithmetic."""

from __future__ import annotations

import random

import pandas as pd
import pytest

from trader.backtest.frozen_config_rsi2 import (
    FROZEN_HASH_RSI2,
    compute_hash_rsi2,
    verify_frozen_rsi2,
)
from trader.backtest.iterator import PointInTimeIterator
from trader.backtest.strategies import rsi2


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


def _fire(variant_name: str, bars_by_symbol: dict[str, pd.DataFrame]) -> list[str]:
    iterator = PointInTimeIterator(bars_by_symbol)
    last_date = max(df.index[-1] for df in bars_by_symbol.values())
    iterator.advance_to(last_date.date())
    pick = rsi2.make_pick_entries(rsi2.RSI2_VARIANTS[variant_name])
    return pick(iterator, last_date, set(), random.Random(0))


def _uptrend_with_dip(dip_days: int = 3, dip_step: float = 3.0) -> list[float]:
    """A long rise (close well above its 200-day SMA) ending in a sharp
    multi-day dip: RSI(2) pinned at 0 (all recent deltas negative), price
    still above the SMA."""
    rise = [100.0 + 0.5 * i for i in range(220)]
    top = rise[-1]
    return rise + [top - dip_step * (i + 1) for i in range(dip_days)]


# ---------------------------------------------------------------------------
# Signal semantics
# ---------------------------------------------------------------------------


def test_fires_on_oversold_dip_within_uptrend():
    assert _fire("connors10", {"AAPL": _bars(_uptrend_with_dip())}) == ["AAPL"]
    assert _fire("connors5", {"AAPL": _bars(_uptrend_with_dip())}) == ["AAPL"]


def test_never_fires_below_the_200_day_sma():
    """The same oversold dip, but in a downtrend: the non-negotiable filter
    keeps it flat."""
    fall = [300.0 - 0.5 * i for i in range(220)]
    dip = [fall[-1] - 3.0 * (i + 1) for i in range(3)]
    assert _fire("connors10", {"AAPL": _bars(fall + dip)}) == []


def test_never_fires_without_oversold_rsi():
    """A clean uptrend with a rising last bar: RSI(2) is 100, no entry."""
    rise = [100.0 + 0.5 * i for i in range(223)]
    assert _fire("connors10", {"AAPL": _bars(rise)}) == []


def test_connors5_is_stricter_than_connors10():
    """A mild two-day pullback with one recent gain leaves RSI(2) between
    5 and 10: connors10 fires, connors5 does not."""
    rise = [100.0 + 0.5 * i for i in range(220)]
    top = rise[-1]
    # deltas: +0.5 ... then -3.0, +0.2, -3.0 -> small gain vs large losses
    tail = [top - 3.0, top - 2.8, top - 5.8]
    closes = rise + tail
    assert _fire("connors10", {"AAPL": _bars(closes)}) == ["AAPL"]
    assert _fire("connors5", {"AAPL": _bars(closes)}) == []


def test_needs_200_days_of_history():
    short = _uptrend_with_dip()[-150:]
    assert _fire("connors10", {"AAPL": _bars(short)}) == []


def test_open_positions_never_refire():
    bars = _bars(_uptrend_with_dip())
    iterator = PointInTimeIterator({"AAPL": bars})
    last_date = bars.index[-1]
    iterator.advance_to(last_date.date())
    pick = rsi2.make_pick_entries(rsi2.RSI2_VARIANTS["connors10"])
    assert pick(iterator, last_date, {"AAPL"}, random.Random(0)) == []


def test_variants_are_the_published_connors_thresholds():
    assert rsi2.RSI2_VARIANTS["connors10"].rsi_entry_ceiling == 10.0
    assert rsi2.RSI2_VARIANTS["connors5"].rsi_entry_ceiling == 5.0
    assert set(rsi2.RSI2_VARIANTS) == {"connors10", "connors5"}
    assert rsi2.SMA_FILTER_DAYS == 200
    assert rsi2.RSI_PERIOD == 2


# ---------------------------------------------------------------------------
# Freeze gate + driver arithmetic
# ---------------------------------------------------------------------------


def test_committed_rsi2_hash_matches_file():
    assert compute_hash_rsi2() == FROZEN_HASH_RSI2


def test_tampered_rsi2_file_raises(tmp_path):
    from pathlib import Path

    from trader.backtest import frozen_config_rsi2 as gate

    repo_root = Path(gate.__file__).resolve().parents[2]
    for rel in gate.FROZEN_FILES_RSI2:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((repo_root / rel).read_bytes() + b"# tampered\n")

    with pytest.raises(RuntimeError, match="integrity check failed"):
        verify_frozen_rsi2(repo_root=tmp_path)


def test_expected_tune_run_count_matches_real_grid_and_regimes():
    from trader.backtest import exit_grid, regimes_v2, universe
    from trader.backtest.run_rsi2_evidence import EXPECTED_TUNE_RUN_COUNT_RSI2

    stock_regimes = [
        r for r in regimes_v2.REGIMES_V2 if r.bucket == universe.BUCKET_STOCK
    ]
    grid_size = len(list(exit_grid.exit_profile_grid(universe.BUCKET_STOCK)))
    expected = len(rsi2.RSI2_VARIANTS) * len(stock_regimes) * grid_size
    assert expected == EXPECTED_TUNE_RUN_COUNT_RSI2


def test_evidence_driver_verifies_rsi2_gate_before_any_work(monkeypatch):
    from trader.backtest import run_rsi2_evidence

    monkeypatch.setattr(
        run_rsi2_evidence,
        "verify_frozen_rsi2",
        lambda: (_ for _ in ()).throw(RuntimeError("integrity check failed")),
    )

    with pytest.raises(RuntimeError, match="integrity check failed"):
        run_rsi2_evidence.main(conn=object())
