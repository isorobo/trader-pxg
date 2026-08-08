"""Intraday (1h) track tests: frozen signals, the freeze gate, and the
engine proof -- run_backtest on hourly bars fills at the NEXT HOUR's open
and counts holds in bars/hours."""

from __future__ import annotations

import random

import numpy as np
import pandas as pd
import pytest

from trader.backtest import ledger
from trader.backtest.config import EXIT_PROFILE
from trader.backtest.frozen_config_hourly import (
    FROZEN_HASH_HOURLY,
    compute_hash_hourly,
    verify_frozen_hourly,
)
from trader.backtest.hourly_grid import (
    REGIMES_1H,
    hourly_exit_profile_grid,
)
from trader.backtest.iterator import PointInTimeIterator
from trader.backtest.runner import run_backtest
from trader.backtest.strategies import hourly_reversion, hourly_squeeze


def _hourly_df(closes, volumes=None, end="2026-08-01 12:00", spread=0.5):
    periods = len(closes)
    index = pd.date_range(end=end, periods=periods, freq="1h", tz="UTC")
    volumes = volumes if volumes is not None else [1_000.0] * periods
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + spread for c in closes],
            "low": [c - spread for c in closes],
            "close": closes,
            "volume": volumes,
        },
        index=index,
    )


def _fire(module, variant_name, df):
    iterator = PointInTimeIterator({"BTC/USDT": df})
    last_ts = df.index[-1]
    iterator.advance_to(last_ts)
    variants = (
        module.HOURLY_REVERSION_VARIANTS
        if module is hourly_reversion
        else module.HOURLY_SQUEEZE_VARIANTS
    )
    pick = module.make_pick_entries(variants[variant_name])
    return pick(iterator, last_ts, set(), random.Random(0))


# ---------------------------------------------------------------------------
# Reversion (Strategys/17 #1+#4): gate, stretch, snap-back, confluence
# ---------------------------------------------------------------------------


def _range_bound_closes(n=140, mid=100.0, amp=1.0):
    """A flat oscillating range: bands stay narrow and stable."""
    return [mid + amp * np.sin(i / 3.0) for i in range(n)]


def test_reversion_fires_on_snapback_after_stretch():
    closes = _range_bound_closes()
    closes[-2] = 90.0   # deep stretch below the lower band (RSI at touch ~14)
    closes[-1] = 99.0   # snap-back close inside the band
    assert _fire(hourly_reversion, "confluence30", _hourly_df(closes)) == ["BTC/USDT"]


def test_reversion_never_fires_without_the_stretch():
    closes = _range_bound_closes()
    assert _fire(hourly_reversion, "confluence30", _hourly_df(closes)) == []


def test_reversion_range_gate_blocks_expanding_bands():
    """Same stretch/snap-back shape, but placed at the end of a violent
    expansion -- widths blow out and the gate must veto the fade."""
    closes = _range_bound_closes(n=110)
    closes += [100 + ((-1) ** i) * (8 + i) for i in range(28)]  # expanding chop
    closes += [40.0, 95.0]  # stretch + snap-back inside wide bands
    assert _fire(hourly_reversion, "confluence30", _hourly_df(closes)) == []


# ---------------------------------------------------------------------------
# Squeeze (Strategys/18 #2+#5): compression, breakout close, volume confirm
# ---------------------------------------------------------------------------

def _squeeze_setup(break_volume: float):
    """Volatile early history, then a dead-flat coil (the squeeze), then a
    breakout candle on `break_volume`."""
    early = [100 + 3.0 * np.sin(i / 2.0) for i in range(80)]
    coil = [100.0 + 0.05 * np.sin(i) for i in range(60)]
    closes = early + coil + [103.0]
    volumes = [1_000.0] * (len(closes) - 1) + [break_volume]
    return _hourly_df(closes, volumes)


def test_squeeze_fires_on_volume_confirmed_break():
    assert _fire(hourly_squeeze, "vol2x", _squeeze_setup(2_500.0)) == ["BTC/USDT"]


def test_squeeze_rejects_low_volume_break():
    assert _fire(hourly_squeeze, "vol2x", _squeeze_setup(1_500.0)) == []


def test_vol3x_is_stricter_than_vol2x():
    df = _squeeze_setup(2_500.0)
    assert _fire(hourly_squeeze, "vol2x", df) == ["BTC/USDT"]
    assert _fire(hourly_squeeze, "vol3x", df) == []


# ---------------------------------------------------------------------------
# Freeze gate + grid shape
# ---------------------------------------------------------------------------


def test_committed_hourly_hash_matches_files():
    assert compute_hash_hourly() == FROZEN_HASH_HOURLY


def test_tampered_hourly_file_raises(tmp_path):
    from pathlib import Path

    from trader.backtest import frozen_config_hourly as gate

    repo_root = Path(gate.__file__).resolve().parents[2]
    for rel in gate.FROZEN_FILES_HOURLY:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((repo_root / rel).read_bytes() + b"# tampered\n")

    with pytest.raises(RuntimeError, match="integrity check failed"):
        verify_frozen_hourly(repo_root=tmp_path)


def test_hourly_grid_is_24_cells_with_hour_scale_exits():
    grid = hourly_exit_profile_grid("crypto_major_legacy_meme")
    assert len(grid) == 24
    assert all(-0.10 < p.stop_pct < 0 for p in grid)  # hourly-scale stops
    assert all(p.max_hold_days in (24, 168) for p in grid)  # HOURS
    assert len(REGIMES_1H) == 2
    for regime in REGIMES_1H:
        assert regime.oos_start > (regime.tune_end or "")


# ---------------------------------------------------------------------------
# THE ENGINE PROOF: hourly bars through run_backtest -- next-HOUR-open
# fills, hold counted in hours
# ---------------------------------------------------------------------------


def test_run_backtest_on_hourly_bars_fills_next_hour_open(tmp_path):
    """A signal at hour H must fill at hour H+1's OPEN (never H's close),
    and a 24-'day' hold must time-stop 24 HOURS later -- proving the daily
    engine's honesty rules transfer to 1h bars unchanged."""
    from trader.data import db as trader_db

    conn = trader_db.get_connection(str(tmp_path / "t.db"))

    # 60 bars: signal @5, fill @6, 24-hour time stop @30 -- comfortably
    # inside the data (30 bars would end before the stop could fire and
    # an unclosed position writes no trade row).
    closes = [100.0] * 60
    index = pd.date_range(
        start="2026-06-01 00:00", periods=len(closes), freq="1h", tz="UTC"
    )
    df = pd.DataFrame(
        {
            "open": [c + 1.0 for c in closes],  # opens differ from closes
            "high": [c + 2.0 for c in closes],
            "low": [c - 2.0 for c in closes],
            "close": closes,
            "volume": [1_000.0] * len(closes),
        },
        index=index,
    )

    # The runner's calendar carries tz-naive UTC Timestamps (numpy
    # datetime64 round-trip) -- compare against the naive form.
    signal_hour = index[5].tz_localize(None)

    def one_shot(iterator, date, open_positions, rng):
        return ["BTC/USDT"] if date == signal_hour else []

    profile = EXIT_PROFILE(
        stop_pct=-0.5, tp_pct=None, scale_out=(), trailing_pct=None,
        max_hold_days=24, eod_flat=False,  # 24 BARS = 24 HOURS on 1h data
    )
    run_id = run_backtest(
        one_shot, ["BTC/USDT"], profile, {"BTC/USDT": df}, 1,
        {"profile_name": "hourly_proof"}, "hourly_proof", conn,
    )

    trades = ledger.get_trades_for_run(conn, run_id)
    assert len(trades) == 1
    trade = trades[0]
    # Fill = next hour's open (101.0) + crypto slippage, never 100.0 close.
    assert trade["entry_price"] > 101.0
    assert trade["exit_reason"] == "time_stop"
    assert trade["fees"] > 0
    # 24-hour time stop: exit lands the same calendar day or the next --
    # never weeks later (which is what a DAY-counted hold would produce).
    entry_day = trade["entry_ts"][:10]
    exit_day = trade["exit_ts"][:10]
    assert (pd.Timestamp(exit_day) - pd.Timestamp(entry_day)).days <= 2
    conn.close()
