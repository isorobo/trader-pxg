"""Tests for the Phase 3 momentum agent (STRAT-01): RSI(14) + 2x-20-day
volume surge + 20-day-high close break, implemented as a pure function over
trader.backtest.iterator.PointInTimeIterator matching the shared strategy
contract:

    pick_entries(iterator, date, open_positions, rng) -> list[str]

Every fixture below decouples close/high/volume columns explicitly (rather
than reusing test_backtest_strategies.py's close+1/close-1 derived-column
shape) so each test isolates exactly one signal component -- the RSI window,
the breakout-high window, or the volume-surge window -- while holding the
other two constant. All fixtures use BREAK_LOOKBACK(20) + 1 = 21 bars unless
the test is specifically exercising the short-history guard.
"""

import random

import pandas as pd

from trader.backtest import iterator

try:
    from trader.backtest.strategies import momentum
except ImportError:
    # trader.backtest.strategies.momentum does not exist yet (RED phase) --
    # collection must still succeed; each test then fails with an
    # AttributeError on `momentum` (None).
    momentum = None


def _bars(closes: list[float], highs: list[float], volumes: list[float],
          start: str = "2026-01-01") -> pd.DataFrame:
    """Fixture DataFrame with independently controllable close/high/volume
    columns -- open/low are derived (irrelevant to the momentum signal)."""
    n = len(closes)
    assert len(highs) == n and len(volumes) == n
    index = pd.date_range(start, periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": [c - 1.0 for c in closes],
            "high": highs,
            "low": [c - 2.0 for c in closes],
            "close": closes,
            "volume": volumes,
        },
        index=index,
    )


def _universe(symbol_frames: dict[str, pd.DataFrame]):
    it = iterator.PointInTimeIterator(symbol_frames)
    it.advance_to(it.calendar[-1])
    return it


# --- Shared fixture shapes ---------------------------------------------------

# 21 bars: idx0-5 filler (irrelevant to RSI/breakout math), idx6-19 rising by
# 1/day (feeds the last-15-close RSI window with all-gains -> RSI=100),
# idx20 = today, closing at 114 -- above the flat 100 prior-20-day high.
_FIRES_CLOSES = [90.0] * 6 + [100.0 + i for i in range(14)] + [114.0]
_FIRES_HIGHS = [100.0] * 20 + [115.0]
_FIRES_VOLUMES = [1000.0] * 20 + [2500.0]  # 2.5x the flat 1000 baseline

# Same highs/volumes (prior_high=100, baseline_volume=1000, today_volume
# surges 2.5x) but closes decline steeply through the RSI window before a
# small today-uptick -- isolates "RSI below floor" from breakout/volume.
_CHOPPY_CLOSES = (
    [90.0] * 6
    + [130.0, 128.0, 126.0, 124.0, 122.0, 120.0, 118.0, 116.0, 114.0, 112.0,
       110.0, 108.0, 106.0, 104.0]
    + [105.0]
)


def test_momentum_fires_on_rsi_volume_surge_and_breakout():
    it = _universe({"RISER": _bars(_FIRES_CLOSES, _FIRES_HIGHS, _FIRES_VOLUMES)})

    picks = momentum.pick_entries(it, it.calendar[-1], set(), random.Random(0))

    assert picks == ["RISER"]


def test_momentum_no_signal_when_rsi_below_floor():
    # Breakout (105 > prior_high 100) and volume surge (2500 > 2x1000) both
    # hold -- only the choppy/declining close sequence keeps RSI < 60.
    it = _universe({"CHOPPY": _bars(_CHOPPY_CLOSES, _FIRES_HIGHS, _FIRES_VOLUMES)})

    picks = momentum.pick_entries(it, it.calendar[-1], set(), random.Random(0))

    assert picks == []


def test_momentum_no_signal_when_volume_surge_below_floor():
    # RSI=100 and breakout both hold (fires-shape closes/highs); today's
    # volume is only 1.5x the trailing baseline -- below the 2.0x floor.
    below_floor_volumes = [1000.0] * 20 + [1500.0]
    it = _universe(
        {"WEAKVOL": _bars(_FIRES_CLOSES, _FIRES_HIGHS, below_floor_volumes)}
    )

    picks = momentum.pick_entries(it, it.calendar[-1], set(), random.Random(0))

    assert picks == []


def test_momentum_no_signal_with_insufficient_history():
    # Only 10 bars -- fewer than BREAK_LOOKBACK(20) + 1 -- must never signal
    # regardless of the (otherwise qualifying) fires-shape price/volume data.
    short_closes = _FIRES_CLOSES[:10]
    short_highs = _FIRES_HIGHS[:10]
    short_volumes = _FIRES_VOLUMES[:10]
    it = _universe(
        {"SHORT": _bars(short_closes, short_highs, short_volumes)}
    )

    picks = momentum.pick_entries(it, it.calendar[-1], set(), random.Random(0))

    assert picks == []


def test_momentum_never_repicks_open_position():
    it = _universe({"RISER": _bars(_FIRES_CLOSES, _FIRES_HIGHS, _FIRES_VOLUMES)})

    picks = momentum.pick_entries(it, it.calendar[-1], {"RISER"}, random.Random(0))

    assert picks == []


def test_momentum_off_by_one_baseline_excludes_todays_volume():
    # today_volume=2100 against the correct baseline (mean of the 20 PRIOR
    # bars' flat 1000 volume) gives a true 2.1x surge -- fires. A naive
    # baseline that wrongly folds today's own volume into its 20-bar window
    # (mean of volumes[1:20] + [2100]) would compute ~1055, understating the
    # ratio to ~1.99x and wrongly suppressing the signal. This fixture proves
    # the correct (excluding-today) baseline is used.
    off_by_one_volumes = [1000.0] * 20 + [2100.0]
    it = _universe(
        {"EDGE": _bars(_FIRES_CLOSES, _FIRES_HIGHS, off_by_one_volumes)}
    )

    picks = momentum.pick_entries(it, it.calendar[-1], set(), random.Random(0))

    assert picks == ["EDGE"]


def test_momentum_pick_entries_signature():
    import inspect

    sig = inspect.signature(momentum.pick_entries)
    assert list(sig.parameters) == ["iterator", "date", "open_positions", "rng"]
