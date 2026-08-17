"""NYSE trading-day gate and session-window helper (D-05/PAPER-07).

Wraps pandas-market-calendars so the entry pipeline (05-06) and the guardian
can decide whether today is a trading day, and precisely when the session
opens/closes (including early-close days), without a hand-maintained holiday
list. Supersedes trader/ground_truth/poll.py's is_market_hours fixed-window
predecessor for Phase 5's precision needs -- that function stays untouched
(Phase 0 scope), this module is Phase 5's own.

Static calendar lookup only -- no network call, no broker connection.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

_NYSE = mcal.get_calendar("NYSE")

MARKET_TZ = ZoneInfo("America/New_York")


def market_date_now(now: datetime | None = None) -> date:
    """The NYSE calendar date at this instant, in MARKET time.

    Load-bearing for any caller that asks "is the market open today?"
    from New Zealand (2026-08-16 bug): NZ runs 16 hours ahead of New York,
    so the 01:45 NZ scan happens on the PREVIOUS US date. Using the local
    date silently skipped every Friday US session (Saturday in NZ) and
    tried to trade every Sunday US session (Monday in NZ) -- one lost
    trading day in five, plus orders queued into a closed market. Never
    use date.today() to gate a US-market decision.
    """
    return (now or datetime.now(MARKET_TZ)).astimezone(MARKET_TZ).date()


def is_trading_day(check_date: date) -> bool:
    """True iff check_date is an NYSE trading day. Never raises."""
    schedule = _NYSE.schedule(start_date=check_date, end_date=check_date)
    return not schedule.empty


def session_window(check_date: date) -> tuple[datetime, datetime]:
    """Return (open_utc, close_utc) for check_date's NYSE session.

    Both datetimes are UTC tz-aware per pandas-market-calendars' own
    convention -- never tz_localize'd again here. Raises ValueError if
    check_date is not an NYSE trading day (never a silent empty tuple).
    """
    schedule = _NYSE.schedule(start_date=check_date, end_date=check_date)
    if schedule.empty:
        raise ValueError(f"{check_date} is not an NYSE trading day")
    return (
        schedule.iloc[0]["market_open"].to_pydatetime(),
        schedule.iloc[0]["market_close"].to_pydatetime(),
    )
