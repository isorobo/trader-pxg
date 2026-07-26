"""Tests for trader.backtest.iterator -- the point-in-time bar iterator
(BACK-01, D-01/D-02/D-03).

Fixtures are small, hand-built OHLCV DataFrames mirroring the shape
tests/test_data_api.py's _fixture_bars() produces and the UTC tz-aware,
sorted-index contract trader/data/api.py's get_daily_bars guarantees. No
live get_daily_bars call and no network/DB coupling -- the iterator itself
never talks to Phase 1's cache directly (that wiring belongs to whichever
runner constructs bars_by_symbol, not to this module or its tests).
"""

import pandas as pd
import pytest

try:
    from trader.backtest import iterator
except ImportError:
    # trader.backtest.iterator does not exist yet (RED phase) -- collection
    # must still succeed so all tests are collected; each test then fails
    # with an AttributeError on `iterator` (None) when it tries to build a
    # PointInTimeIterator.
    iterator = None

# Symbol AAA: 10 consecutive daily bars, 2026-07-01 through 2026-07-10.
DAYS_AAA = [f"2026-07-{day:02d}" for day in range(1, 11)]

# Symbol BBB: same span as AAA but missing 2026-07-05 -- a different trading
# calendar, used to exercise bar_on's None path (D-01/D-02).
DAYS_BBB = [f"2026-07-{day:02d}" for day in range(1, 11) if day != 5]


def _make_bars(dates: list[str], base: float = 100.0) -> pd.DataFrame:
    index = pd.to_datetime(dates, utc=True)
    n = len(dates)
    return pd.DataFrame(
        {
            "open": [base + i for i in range(n)],
            "high": [base + 5.0 + i for i in range(n)],
            "low": [base - 1.0 + i for i in range(n)],
            "close": [base + 3.0 + i for i in range(n)],
            "volume": [1000.0 + i for i in range(n)],
        },
        index=index,
    )


def _new_iterator():
    return iterator.PointInTimeIterator(
        {"AAA": _make_bars(DAYS_AAA), "BBB": _make_bars(DAYS_BBB, base=50.0)}
    )


def test_calendar_is_sorted_deduplicated_union_of_symbol_dates():
    it = _new_iterator()

    assert it.calendar == sorted(it.calendar)
    assert len(it.calendar) == len(DAYS_AAA)  # AAA's day5 covers BBB's gap
    assert all(isinstance(date, pd.Timestamp) for date in it.calendar)


def test_history_before_any_advance_to_is_empty():
    it = _new_iterator()

    assert len(it.history("AAA")) == 0
    assert len(it.history("BBB")) == 0


def test_history_returns_bars_strictly_up_to_the_advance_to_date():
    it = _new_iterator()

    it.advance_to("2026-07-05")
    hist = it.history("AAA")

    assert len(hist) == 5
    last_row = hist[-1]
    bar_on_day5 = it.bar_on("AAA", "2026-07-05")
    assert last_row[0] == bar_on_day5["open"]
    assert last_row[3] == bar_on_day5["close"]


def test_advance_to_twice_with_same_date_is_a_noop():
    it = _new_iterator()

    it.advance_to("2026-07-05")
    length_before = len(it.history("AAA"))
    it.advance_to("2026-07-05")

    assert len(it.history("AAA")) == length_before == 5


def test_advance_to_raises_on_earlier_date_pointer_never_moves_backward():
    it = _new_iterator()

    it.advance_to("2026-07-05")
    with pytest.raises(ValueError):
        it.advance_to("2026-07-03")

    # The rejected call must not have moved the pointer at all.
    assert len(it.history("AAA")) == 5


def test_bar_on_returns_dict_for_an_exact_date_match():
    it = _new_iterator()

    bar = it.bar_on("AAA", "2026-07-03")

    assert bar is not None
    assert set(bar.keys()) == {"open", "high", "low", "close", "volume"}


def test_bar_on_returns_none_when_symbol_has_no_bar_on_that_date():
    it = _new_iterator()

    assert it.bar_on("BBB", "2026-07-05") is None
    assert it.bar_on("AAA", "2026-07-05") is not None


def test_history_reference_held_across_later_advance_to_cannot_see_lookahead_bars():
    it = _new_iterator()

    it.advance_to("2026-07-05")
    hist_a_at_day5 = it.history("AAA")
    assert len(hist_a_at_day5) == 5

    # Advancing further moves AAA's and BBB's pointers independently (BBB's
    # missing day5 means its pointer sits one bar behind AAA's for the same
    # calendar date) -- neither move retroactively extends a reference
    # already taken.
    it.advance_to("2026-07-08")

    assert len(it.history("AAA")) == 8
    assert len(hist_a_at_day5) == 5


def test_history_is_independent_per_symbol_pointer():
    it = _new_iterator()

    it.advance_to("2026-07-05")

    # AAA has a bar on day5 (5 bars visible); BBB is missing day5, so its
    # pointer stops at day4 (4 bars visible) -- pointers track their own
    # symbol's calendar, not a shared index position.
    assert len(it.history("AAA")) == 5
    assert len(it.history("BBB")) == 4
