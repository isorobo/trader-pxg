"""Tests for trader.paper.calendar_ -- the NYSE trading-day gate and
session-window helper (05-02-PLAN.md, Task 1).

Uses real pandas-market-calendars NYSE data (a static calendar lookup, not a
network call) -- no mocking needed.
"""

from datetime import date, datetime

import pytest

from trader.paper import calendar_


def test_is_trading_day_true_for_a_monday():
    assert calendar_.is_trading_day(date(2026, 7, 27)) is True


def test_is_trading_day_false_for_a_saturday():
    assert calendar_.is_trading_day(date(2026, 7, 25)) is False


def test_is_trading_day_false_for_new_years_day():
    assert calendar_.is_trading_day(date(2026, 1, 1)) is False


def test_is_trading_day_never_raises_for_any_date_input():
    # Far future / far past dates must not raise.
    calendar_.is_trading_day(date(1900, 1, 1))
    calendar_.is_trading_day(date(2999, 12, 31))


def test_session_window_returns_utc_aware_open_before_close():
    open_utc, close_utc = calendar_.session_window(date(2026, 7, 27))
    assert isinstance(open_utc, datetime)
    assert isinstance(close_utc, datetime)
    assert open_utc.tzinfo is not None
    assert close_utc.tzinfo is not None
    assert open_utc < close_utc


def test_session_window_raises_value_error_on_non_trading_day():
    with pytest.raises(ValueError):
        calendar_.session_window(date(2026, 1, 1))
