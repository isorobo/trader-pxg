"""Tests for trader.backtest.exits -- EXIT_PROFILES evaluation in D-10's
exact locked order (BACK-04).

Every subtlety flagged in 02-RESEARCH.md's Pitfalls 2, 3, and 5 gets its own
named regression test here, not just an implementation that happens to work
on the happy path: entry-bar stop checking (T-02-09), non-lookahead trailing
watermarks (T-02-10), and stop-wins-the-tie (T-02-11, D-05).
"""

import pytest

try:
    from trader.backtest import exits
    from trader.backtest.config import EXIT_PROFILE
except ImportError:
    # trader.backtest.exits does not exist yet (RED phase) -- collection
    # must still succeed so all tests are collected; each test then fails
    # with an AttributeError on `exits` (None). Matches
    # tests/test_backtest_config.py's RED-phase-safe pattern.
    exits = None
    EXIT_PROFILE = None


def _profile(
    stop_pct=None,
    tp_pct=None,
    scale_out=(),
    trailing_pct=None,
    max_hold_days=None,
    eod_flat=False,
):
    return EXIT_PROFILE(
        stop_pct=stop_pct,
        tp_pct=tp_pct,
        scale_out=scale_out,
        trailing_pct=trailing_pct,
        max_hold_days=max_hold_days,
        eod_flat=eod_flat,
    )


# --- entry-bar stop check (Pitfall 2, T-02-09) --------------------------


def test_entry_bar_stop_check():
    # A position entered THIS bar (days_held=0) whose own low breaches the
    # stop must exit on the entry bar itself -- not be skipped until later.
    profile = _profile(stop_pct=-0.05)
    position = exits.PositionState.open(profile, entry_price=100.0)
    bar = {"open": 100.0, "high": 101.0, "low": 94.0, "close": 96.0}

    result = exits.evaluate_exit(profile, position, bar, days_held=0, watermark=None)

    assert result is not None
    assert result.reason == "stop"
    assert result.exit_fraction == pytest.approx(1.0)


# --- stop-wins-tie (D-05, T-02-11) ---------------------------------------


def test_stop_wins_tie():
    # Same bar breaches both the stop AND the TP -- the stop always wins.
    profile = _profile(stop_pct=-0.05, tp_pct=0.05)
    position = exits.PositionState.open(profile, entry_price=100.0)
    bar = {"open": 100.0, "high": 106.0, "low": 94.0, "close": 100.0}

    result = exits.evaluate_exit(profile, position, bar, days_held=1, watermark=None)

    assert result.reason == "stop"


# --- gap-through pricing (D-04) ------------------------------------------


def test_gap_through_stop():
    # Bar opens below the stop price -- raw_price is the (worse) open, not
    # the stale stop price.
    profile = _profile(stop_pct=-0.05)
    position = exits.PositionState.open(profile, entry_price=100.0)
    bar = {"open": 90.0, "high": 91.0, "low": 88.0, "close": 89.0}

    result = exits.evaluate_exit(profile, position, bar, days_held=2, watermark=None)

    assert result.reason == "stop"
    assert result.raw_price == pytest.approx(90.0)


# --- trailing no-lookahead (Pitfall 3, T-02-10) --------------------------


def test_trailing_no_lookahead():
    # Prior watermark (as of the END of the previous bar) is 100.0. THIS
    # bar's own high (110.0) is a new high, but the watermark used for
    # THIS bar's check must reflect only the prior close, never this bar's
    # own high. If the watermark were wrongly bumped to 110.0 first, the
    # trailing level would be 104.5 and low=94.0 would NOT breach it. Using
    # the correct prior-close-only watermark of 100.0, the trailing level
    # is 95.0, and low=94.0 breaches it.
    profile = _profile(trailing_pct=0.05)
    position = exits.PositionState.open(profile, entry_price=90.0)
    bar = {"open": 100.0, "high": 110.0, "low": 94.0, "close": 105.0}

    result = exits.evaluate_exit(
        profile, position, bar, days_held=3, watermark=100.0
    )

    assert result is not None
    assert result.reason == "trailing_stop"
    assert result.raw_price == pytest.approx(95.0)
    # The watermark for the NEXT bar reflects this bar's own close, updated
    # only AFTER the check -- never before it.
    assert result.new_watermark == pytest.approx(105.0)


# --- D-10 evaluation order: eod_flat beats stop --------------------------


def test_eod_flat_beats_stop_in_order():
    # eod_flat=True AND a stop set; both independently true on this bar.
    # D-10's first-in-order item (eod_flat) wins over stop.
    profile = _profile(stop_pct=-0.05, eod_flat=True)
    position = exits.PositionState.open(profile, entry_price=100.0)
    bar = {"open": 100.0, "high": 101.0, "low": 90.0, "close": 98.0}

    result = exits.evaluate_exit(profile, position, bar, days_held=4, watermark=None)

    assert result.reason == "eod_flat"


def test_eod_flat_fills_at_close():
    # eod_flat exits at that bar's close (A4's daily-bars interpretation),
    # full size, and passes the incoming watermark straight through
    # unchanged (no trailing-related bar processing happens on this path).
    profile = _profile(eod_flat=True)
    position = exits.PositionState.open(profile, entry_price=100.0)
    bar = {"open": 100.0, "high": 103.0, "low": 99.0, "close": 102.5}

    result = exits.evaluate_exit(profile, position, bar, days_held=1, watermark=50.0)

    assert result.reason == "eod_flat"
    assert result.raw_price == pytest.approx(102.5)
    assert result.exit_fraction == pytest.approx(1.0)
    assert result.new_watermark == pytest.approx(50.0)


# --- time stop ------------------------------------------------------------


def test_time_stop_exits_at_close():
    # max_hold_days fully elapsed, no other condition true -- exits at that
    # bar's close (daily-bars convention, consistent with eod_flat).
    profile = _profile(max_hold_days=3)
    position = exits.PositionState.open(profile, entry_price=100.0)
    bar = {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5}

    result = exits.evaluate_exit(profile, position, bar, days_held=3, watermark=None)

    assert result.reason == "time_stop"
    assert result.raw_price == pytest.approx(100.5)
    assert result.exit_fraction == pytest.approx(1.0)


# --- scale-out accounting -------------------------------------------------


def test_scale_out_partial_fires_once():
    # First gain threshold hit -> partial exit fires and the fraction
    # matches the profile. A later bar's evaluate_exit call must NOT
    # re-fire the same already-triggered tranche.
    profile = _profile(scale_out=((0.10, 0.5),))
    position = exits.PositionState.open(profile, entry_price=100.0)
    bar_1 = {"open": 100.0, "high": 111.0, "low": 99.0, "close": 105.0}

    result_1 = exits.evaluate_exit(
        profile, position, bar_1, days_held=1, watermark=None
    )

    assert result_1 is not None
    assert result_1.reason == "scale_out"
    assert result_1.exit_fraction == pytest.approx(0.5)
    assert 0.10 in position.scale_out_triggered

    # Same threshold, still above target on a later bar -- must not re-fire.
    bar_2 = {"open": 106.0, "high": 115.0, "low": 104.0, "close": 108.0}
    result_2 = exits.evaluate_exit(
        profile, position, bar_2, days_held=2, watermark=result_1.new_watermark
    )

    assert result_2 is None


# --- no exit ---------------------------------------------------------------


def test_no_exit_returns_none():
    # No stop, no TP, no trailing, no scale-out, no time stop, no eod_flat
    # -- none of the profile's conditions are configured, so nothing can
    # fire on any bar.
    profile = _profile()
    position = exits.PositionState.open(profile, entry_price=100.0)
    bar = {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5}

    result = exits.evaluate_exit(profile, position, bar, days_held=1, watermark=None)

    assert result is None
