"""Guardian resilience regressions (2026-08-17).

Two defects surfaced the same evening, both from the same family as the
entry pipeline's timezone bug:

1. The tick dated itself off UTC, which is already tomorrow relative to
   New York for most of the NZ day -- so weekend ticks passed the
   trading-day gate, tried to price a shut market, and died.
2. One unpriceable symbol raised out of the whole loop, so every OTHER
   position's stop-loss went unchecked as collateral damage.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from trader.backtest.config import EXIT_PROFILE
from trader.paper import guardian, ledger

_PROFILE = EXIT_PROFILE(
    stop_pct=-0.10, tp_pct=0.20, scale_out=(), trailing_pct=None,
    max_hold_days=None, eod_flat=False,
)


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(guardian.alerts, "notify", MagicMock(return_value=True))
    monkeypatch.setattr(guardian.ops_log, "append_ops_log", MagicMock())


def _open(conn, symbol: str, price: float = 100.0):
    return ledger.open_position(
        conn, "strat", symbol, "ibkr_paper", "stock", 10.0, price,
        "2026-08-10T09:30:00", f"ref-{symbol}", _PROFILE,
    )


class _Adapter:
    """Prices everything except the symbols in `broken`."""

    def __init__(self, broken=()):
        self.broken = set(broken)
        self.priced: list[str] = []

    def snapshot(self):
        return {"positions": {}, "open_orders": [], "fills": []}

    def latest_price(self, symbol):
        if symbol in self.broken:
            raise RuntimeError(f"no usable price for {symbol}")
        self.priced.append(symbol)
        return 100.0

    def place_order(self, *a, **k):
        return {"perm_id": 1}


def test_tick_dates_itself_off_the_market_clock_not_utc(paper_conn):
    """Monday 00:30 UTC is still SUNDAY in New York -- the tick must treat
    it as a non-trading day and never reach for a price."""
    _open(paper_conn, "JPM")
    adapter = _Adapter()
    monday_utc = datetime(2026, 8, 17, 0, 30, tzinfo=timezone.utc)

    result = guardian.run_guardian_once(paper_conn, adapter, now=monday_utc)

    assert adapter.priced == []          # never tried to price a shut market
    assert result["exits"] == []
    assert result["unpriced"] == []      # skipped by the gate, not by failure


def test_one_unpriceable_symbol_never_blinds_the_rest(paper_conn):
    """JPM cannot be priced; NVDA still must have its exits evaluated."""
    _open(paper_conn, "JPM")
    _open(paper_conn, "NVDA")
    adapter = _Adapter(broken={"JPM"})
    open_session = datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc)  # Tue, NYSE open

    result = guardian.run_guardian_once(paper_conn, adapter, now=open_session)

    assert result["unpriced"] == ["JPM"]
    assert "NVDA" in adapter.priced      # the rest of the book was checked
    assert result["ticked"] == 2


def test_market_date_is_used_for_the_trading_day_gate():
    """Tuesday 01:45 NZ is Monday in New York -- an OPEN session."""
    from zoneinfo import ZoneInfo

    from trader.paper import calendar_

    nz_tuesday = datetime(2026, 8, 18, 1, 45, tzinfo=ZoneInfo("Pacific/Auckland"))
    assert calendar_.market_date_now(nz_tuesday) == date(2026, 8, 17)
    assert calendar_.is_trading_day(calendar_.market_date_now(nz_tuesday)) is True
