"""Tests for the Phase 3 breakout agent (STRAT-02): NR7 volatility
contraction + 20-day-high close break + volume confirmation, no-retest,
implemented as a pure function matching the shared strategy contract:

    pick_entries(iterator, date, open_positions, rng) -> list[str]

Every fixture controls high/low/close/volume columns independently so each
test isolates exactly one signal component -- the NR7 range window, the
breakout-high window, or the volume-confirmation window -- while holding the
other two constant. All fixtures use BREAKOUT_LOOKBACK(20) + 1 = 21 bars
unless the test is specifically exercising the short-history guard.
"""

import random

import pandas as pd

from trader.backtest import iterator

try:
    from trader.backtest.strategies import breakout
except ImportError:
    # trader.backtest.strategies.breakout does not exist yet (RED phase) --
    # collection must still succeed; each test then fails with an
    # AttributeError on `breakout` (None).
    breakout = None


def _bars(closes: list[float], highs: list[float], lows: list[float],
          volumes: list[float], start: str = "2026-01-01") -> pd.DataFrame:
    """Fixture DataFrame with independently controllable high/low/close/
    volume columns -- open is derived (irrelevant to the breakout signal)."""
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


def _universe(symbol_frames: dict[str, pd.DataFrame]):
    it = iterator.PointInTimeIterator(symbol_frames)
    it.advance_to(it.calendar[-1])
    return it


# --- Shared fixture shapes ---------------------------------------------------

# 21 bars: idx0-19 flat high=100/low=95 (range=5, prior 20-day high=100),
# idx20 = today with a narrow range=1 (104-103) -- the narrowest of the last
# 7 bars (NR7) -- closing at 105 (breaks the flat 100 prior high) on 1.6x
# the flat 1000 baseline volume.
_FIRES_HIGHS = [100.0] * 20 + [104.0]
_FIRES_LOWS = [95.0] * 20 + [103.0]
_FIRES_CLOSES = [90.0] * 20 + [105.0]
_FIRES_VOLUMES = [1000.0] * 20 + [1600.0]


def test_breakout_fires_on_nr7_break_and_volume_confirm():
    it = _universe(
        {"NR7": _bars(_FIRES_CLOSES, _FIRES_HIGHS, _FIRES_LOWS, _FIRES_VOLUMES)}
    )

    picks = breakout.pick_entries(it, it.calendar[-1], set(), random.Random(0))

    assert picks == ["NR7"]


def test_breakout_no_signal_when_close_does_not_break_prior_high():
    # NR7 contraction and volume confirmation both hold; today's close
    # (95) stays below the flat 100 prior 20-day high.
    no_break_closes = [90.0] * 20 + [95.0]
    it = _universe(
        {"NOBREAK": _bars(no_break_closes, _FIRES_HIGHS, _FIRES_LOWS, _FIRES_VOLUMES)}
    )

    picks = breakout.pick_entries(it, it.calendar[-1], set(), random.Random(0))

    assert picks == []


def test_breakout_no_signal_when_range_not_narrowest_of_last_7():
    # Close-break (105 > 100) and volume confirmation both hold. Bar idx19
    # is narrower (range=1) than today (range=6) -- today's range is not
    # the narrowest of the trailing 7, so NR7 is false.
    highs = [100.0] * 20 + [106.0]
    lows = [95.0] * 19 + [99.0] + [100.0]
    closes = [90.0] * 20 + [105.0]
    volumes = [1000.0] * 20 + [1600.0]
    it = _universe({"WIDE": _bars(closes, highs, lows, volumes)})

    picks = breakout.pick_entries(it, it.calendar[-1], set(), random.Random(0))

    assert picks == []


def test_breakout_no_signal_when_volume_confirm_below_floor():
    # NR7 + close-break both hold (fires-shape highs/lows/closes); today's
    # volume is only 1.2x the trailing baseline -- below the 1.5x floor.
    below_floor_volumes = [1000.0] * 20 + [1200.0]
    it = _universe(
        {"WEAKVOL": _bars(_FIRES_CLOSES, _FIRES_HIGHS, _FIRES_LOWS, below_floor_volumes)}
    )

    picks = breakout.pick_entries(it, it.calendar[-1], set(), random.Random(0))

    assert picks == []


def test_breakout_no_signal_with_insufficient_history():
    # Only 10 bars -- fewer than BREAKOUT_LOOKBACK(20) + 1 -- must never
    # signal regardless of the (otherwise qualifying) fires-shape data.
    it = _universe(
        {
            "SHORT": _bars(
                _FIRES_CLOSES[:10], _FIRES_HIGHS[:10], _FIRES_LOWS[:10],
                _FIRES_VOLUMES[:10],
            )
        }
    )

    picks = breakout.pick_entries(it, it.calendar[-1], set(), random.Random(0))

    assert picks == []


def test_breakout_never_repicks_open_position():
    it = _universe(
        {"NR7": _bars(_FIRES_CLOSES, _FIRES_HIGHS, _FIRES_LOWS, _FIRES_VOLUMES)}
    )

    picks = breakout.pick_entries(it, it.calendar[-1], {"NR7"}, random.Random(0))

    assert picks == []


def test_breakout_pick_entries_signature():
    import inspect

    sig = inspect.signature(breakout.pick_entries)
    assert list(sig.parameters) == ["iterator", "date", "open_positions", "rng"]
