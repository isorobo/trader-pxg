"""Tests for the Phase 3 v2 entry-variant registry (STRAT-03/04/05, D-14):
3 momentum variants (strict/base/loose on RSI threshold + volume multiplier)
and 3 breakout variants (strict/base/loose on NR-window + volume-confirm
multiplier), each a parameterized `pick_entries` factory.

The "base" variant of each must reproduce v1's real strategy output
byte-for-byte on v1's own fixture-bar tests (v1's momentum.py/breakout.py
constants are unchanged, only re-expressed as a swept dimension) -- proving
v2 adds a new dimension without silently changing what v1 already proved.
Fixture arrays below are copied verbatim from tests/test_strategy_momentum.py
and tests/test_strategy_breakout.py's own module-level fixture shapes (the
checker-corrected base-variant parity fixture is
test_momentum_fires_on_rsi_volume_surge_and_breakout's RISER fixture, not
the nonexistent "test_momentum_signals_on_rising_fixture").
"""

import random

import pandas as pd

from trader.backtest import iterator
from trader.backtest.strategies import breakout, momentum
from trader.backtest.strategies import breakout_v2, momentum_v2


def _momentum_bars(closes: list[float], highs: list[float], volumes: list[float],
                    start: str = "2026-01-01") -> pd.DataFrame:
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


def _breakout_bars(closes: list[float], highs: list[float], lows: list[float],
                    volumes: list[float], start: str = "2026-01-01") -> pd.DataFrame:
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


# --- Verbatim copies of v1's own fixture shapes (parity proof inputs) -------

# From tests/test_strategy_momentum.py's test_momentum_fires_on_rsi_volume_
# surge_and_breakout (the real fire-test fixture; NOT the nonexistent
# "test_momentum_signals_on_rising_fixture").
_MOMENTUM_FIRES_CLOSES = [90.0] * 6 + [100.0 + i for i in range(14)] + [114.0]
_MOMENTUM_FIRES_HIGHS = [100.0] * 20 + [115.0]
_MOMENTUM_FIRES_VOLUMES = [1000.0] * 20 + [2500.0]

# From tests/test_strategy_breakout.py's test_breakout_fires_on_nr7_break_
# and_volume_confirm.
_BREAKOUT_FIRES_HIGHS = [100.0] * 20 + [104.0]
_BREAKOUT_FIRES_LOWS = [95.0] * 20 + [103.0]
_BREAKOUT_FIRES_CLOSES = [90.0] * 20 + [105.0]
_BREAKOUT_FIRES_VOLUMES = [1000.0] * 20 + [1600.0]


# --- Registry shape/value tests ----------------------------------------------


def test_momentum_variants_has_exactly_strict_base_loose():
    assert set(momentum_v2.MOMENTUM_VARIANTS.keys()) == {"strict", "base", "loose"}


def test_breakout_variants_has_exactly_strict_base_loose():
    assert set(breakout_v2.BREAKOUT_VARIANTS.keys()) == {"strict", "base", "loose"}


def test_momentum_variant_values_pinned():
    base = momentum_v2.MOMENTUM_VARIANTS["base"]
    strict = momentum_v2.MOMENTUM_VARIANTS["strict"]
    loose = momentum_v2.MOMENTUM_VARIANTS["loose"]

    assert base.rsi_floor == 60.0 and base.volume_surge_mult == 2.0
    assert strict.rsi_floor == 70.0 and strict.volume_surge_mult == 3.0
    assert loose.rsi_floor == 50.0 and loose.volume_surge_mult == 1.5


def test_breakout_variant_values_pinned():
    base = breakout_v2.BREAKOUT_VARIANTS["base"]
    strict = breakout_v2.BREAKOUT_VARIANTS["strict"]
    loose = breakout_v2.BREAKOUT_VARIANTS["loose"]

    assert base.nr_window == 7 and base.volume_confirm_mult == 1.5
    assert strict.nr_window == 10 and strict.volume_confirm_mult == 2.0
    assert loose.nr_window == 4 and loose.volume_confirm_mult == 1.2


# --- Behavioral parity: "base" reproduces v1 byte-for-byte -------------------


def test_momentum_base_variant_matches_v1_on_fires_fixture():
    it = _universe(
        {"RISER": _momentum_bars(_MOMENTUM_FIRES_CLOSES, _MOMENTUM_FIRES_HIGHS,
                                  _MOMENTUM_FIRES_VOLUMES)}
    )
    v1_picks = momentum.pick_entries(it, it.calendar[-1], set(), random.Random(0))
    v2_picks = momentum_v2.make_pick_entries(momentum_v2.MOMENTUM_VARIANTS["base"])(
        it, it.calendar[-1], set(), random.Random(0)
    )

    assert v2_picks == v1_picks == ["RISER"]


def test_breakout_base_variant_matches_v1_on_fires_fixture():
    it = _universe(
        {"NR7": _breakout_bars(_BREAKOUT_FIRES_CLOSES, _BREAKOUT_FIRES_HIGHS,
                                _BREAKOUT_FIRES_LOWS, _BREAKOUT_FIRES_VOLUMES)}
    )
    v1_picks = breakout.pick_entries(it, it.calendar[-1], set(), random.Random(0))
    v2_picks = breakout_v2.make_pick_entries(breakout_v2.BREAKOUT_VARIANTS["base"])(
        it, it.calendar[-1], set(), random.Random(0)
    )

    assert v2_picks == v1_picks == ["NR7"]


# --- Monotonic strictness sanity check ---------------------------------------


def test_momentum_loose_fires_strict_does_not():
    # RSI window mixes 8 gains + 6 losses of equal magnitude -> RSI ~= 57.14
    # (>= loose's 50.0 floor, < strict's 70.0 floor); today's volume is 2.5x
    # the flat baseline (> loose's 1.5x floor, NOT > strict's 3.0x floor).
    closes = (
        [90.0] * 6
        + [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0,
           107.0, 106.0, 105.0, 104.0, 103.0, 102.0]
    )
    highs = [100.0] * 20 + [103.0]
    volumes = [1000.0] * 20 + [2500.0]
    it = _universe({"MID": _momentum_bars(closes, highs, volumes)})

    loose_fn = momentum_v2.make_pick_entries(momentum_v2.MOMENTUM_VARIANTS["loose"])
    strict_fn = momentum_v2.make_pick_entries(momentum_v2.MOMENTUM_VARIANTS["strict"])

    assert loose_fn(it, it.calendar[-1], set(), random.Random(0)) == ["MID"]
    assert strict_fn(it, it.calendar[-1], set(), random.Random(0)) == []


def test_breakout_loose_fires_strict_does_not():
    # Today's range(1) is the narrowest of the trailing 4 bars (loose's
    # nr_window) but NOT the narrowest of the trailing 10 bars (strict's
    # nr_window) -- bar idx12 has an even narrower range(0.5) inside the
    # 10-bar window. Close-break and volume-confirm both hold regardless of
    # variant, isolating the difference to the contraction-gate window.
    highs = [100.0] * 20 + [103.0]
    lows = (
        [90.0] * 12 + [99.5] + [90.0] * 4 + [95.0] * 3 + [102.0]
    )
    closes = [90.0] * 20 + [103.0]
    volumes = [1000.0] * 20 + [2500.0]
    it = _universe({"MID": _breakout_bars(closes, highs, lows, volumes)})

    loose_fn = breakout_v2.make_pick_entries(breakout_v2.BREAKOUT_VARIANTS["loose"])
    strict_fn = breakout_v2.make_pick_entries(breakout_v2.BREAKOUT_VARIANTS["strict"])

    assert loose_fn(it, it.calendar[-1], set(), random.Random(0)) == ["MID"]
    assert strict_fn(it, it.calendar[-1], set(), random.Random(0)) == []


# --- Self-containment (no v1 strategy-module import) -------------------------


def test_momentum_v2_does_not_import_v1_momentum_module():
    import trader.backtest.strategies.momentum_v2 as mod

    source = open(mod.__file__, encoding="utf-8").read()
    assert "from trader.backtest.strategies import momentum" not in source
    assert "from trader.backtest.strategies.momentum import" not in source
    assert "import trader.backtest.strategies.momentum\n" not in source


def test_breakout_v2_does_not_import_v1_breakout_module():
    import trader.backtest.strategies.breakout_v2 as mod

    source = open(mod.__file__, encoding="utf-8").read()
    assert "from trader.backtest.strategies import breakout" not in source
    assert "from trader.backtest.strategies.breakout import" not in source
    assert "import trader.backtest.strategies.breakout\n" not in source


# --- Signature contract -------------------------------------------------------


def test_momentum_v2_pick_entries_signature():
    import inspect

    fn = momentum_v2.make_pick_entries(momentum_v2.MOMENTUM_VARIANTS["base"])
    sig = inspect.signature(fn)
    assert list(sig.parameters) == ["iterator", "date", "open_positions", "rng"]


def test_breakout_v2_pick_entries_signature():
    import inspect

    fn = breakout_v2.make_pick_entries(breakout_v2.BREAKOUT_VARIANTS["base"])
    sig = inspect.signature(fn)
    assert list(sig.parameters) == ["iterator", "date", "open_positions", "rng"]
