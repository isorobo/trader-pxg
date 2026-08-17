"""The 2026-08-16 timezone-gate regression.

From New Zealand (UTC+12) the 01:45 entry scan happens 16 hours ahead of
New York, i.e. on the PREVIOUS US date. Gating on the local date therefore:
  - skipped every Friday US session   (Saturday in NZ -> "not a trading day")
  - traded every closed Sunday session (Monday in NZ -> "trading day")

One lost trading day in five, plus orders queued into a shut market. These
tests pin the market-date semantics so it cannot come back.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from trader.paper import calendar_

NZ = ZoneInfo("Pacific/Auckland")


def _nz_scan(day: date) -> datetime:
    """The 01:45 NZ moment the entry task fires on `day`."""
    return datetime(day.year, day.month, day.day, 1, 45, tzinfo=NZ)


def test_saturday_nz_scan_is_fridays_open_us_session():
    """The bug's worst half: a Saturday-NZ scan must see Friday's OPEN
    session, not skip because Saturday is not an NYSE day."""
    market_day = calendar_.market_date_now(_nz_scan(date(2026, 8, 22)))

    assert market_day == date(2026, 8, 21)          # Friday in New York
    assert market_day.strftime("%a") == "Fri"
    assert calendar_.is_trading_day(market_day) is True
    # ...whereas the old local-date logic would have gated on Saturday:
    assert calendar_.is_trading_day(date(2026, 8, 22)) is False


def test_monday_nz_scan_is_sundays_closed_us_session():
    """The bug's other half: a Monday-NZ scan must resolve to Sunday in
    New York and be correctly skipped."""
    market_day = calendar_.market_date_now(_nz_scan(date(2026, 8, 17)))

    assert market_day == date(2026, 8, 16)          # Sunday in New York
    assert calendar_.is_trading_day(market_day) is False
    # ...whereas the old local-date logic would have traded a shut market:
    assert calendar_.is_trading_day(date(2026, 8, 17)) is True


def test_midweek_nz_scans_map_back_one_us_day():
    for nz_day, expected_us in (
        (date(2026, 8, 18), date(2026, 8, 17)),     # Tue NZ -> Mon US
        (date(2026, 8, 19), date(2026, 8, 18)),     # Wed NZ -> Tue US
        (date(2026, 8, 21), date(2026, 8, 20)),     # Fri NZ -> Thu US
    ):
        market_day = calendar_.market_date_now(_nz_scan(nz_day))
        assert market_day == expected_us
        assert calendar_.is_trading_day(market_day) is True


def test_entry_pipeline_defaults_to_the_market_date():
    """The pipeline must take its default date from the market clock --
    never date.today() (the source of the bug)."""
    import inspect

    from trader.paper import entry_pipeline

    source = inspect.getsource(entry_pipeline.run_entry_pipeline_once)
    assert "as_of_date or calendar_.market_date_now()" in source
    # The banned pattern is the ASSIGNMENT, not the word -- the comment
    # above it deliberately names date.today() as the thing not to use.
    assert "as_of_date or date.today()" not in source


def test_market_date_now_is_tz_aware_and_matches_new_york():
    """A naive datetime must not silently be treated as market time."""
    utc_moment = datetime(2026, 8, 17, 13, 45, tzinfo=ZoneInfo("UTC"))
    assert calendar_.market_date_now(utc_moment) == date(2026, 8, 17)

    # 00:30 UTC is still the previous day in New York (20:30 EDT).
    late_utc = datetime(2026, 8, 18, 0, 30, tzinfo=ZoneInfo("UTC"))
    assert calendar_.market_date_now(late_utc) == date(2026, 8, 17)
