"""Hourly ingestion tests (intraday track): full-hour timestamps,
incremental resume, partial-candle exclusion, per-symbol failure isolation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trader.data import db, intraday


@pytest.fixture
def conn(tmp_path):
    connection = db.get_connection(str(tmp_path / "trader.db"))
    yield connection
    connection.close()


def _ms(iso: str) -> int:
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


class _FakeExchange:
    def __init__(self, rows_by_since=None, rows=None, fail_symbols=()):
        self.rows = rows or []
        self.fail_symbols = set(fail_symbols)
        self.calls = []

    def fetch_ohlcv(self, symbol, timeframe=None, since=None, limit=None):
        if symbol in self.fail_symbols:
            raise ConnectionError("boom")
        self.calls.append((symbol, timeframe, since))
        return [r for r in self.rows if r[0] >= since]


def test_normalize_keeps_full_hour_timestamps():
    rows = intraday.normalize_hourly_bars(
        [[_ms("2026-08-03T14:00:00Z"), 1.0, 2.0, 0.5, 1.5, 100.0]]
    )
    assert rows[0]["ts"] == "2026-08-03T14:00:00Z"
    assert rows[0]["close"] == 1.5


def test_normalize_raises_on_short_row():
    with pytest.raises(ValueError, match="expected at least 6"):
        intraday.normalize_hourly_bars([[1, 2, 3]])


def test_refresh_backfills_then_resumes_incrementally(conn):
    t0, t1, t2 = (
        _ms("2026-08-03T10:00:00Z"),
        _ms("2026-08-03T11:00:00Z"),
        _ms("2026-08-03T12:00:00Z"),
    )
    exchange = _FakeExchange(rows=[
        [t0, 1, 2, 0.5, 1.5, 10],
        [t1, 1.5, 2.5, 1.0, 2.0, 11],
        [t2, 2.0, 3.0, 1.5, 2.5, 12],
    ])

    written = intraday.refresh_hourly_bars(conn, symbols=("BTC/USDT",), exchange=exchange)
    assert written["BTC/USDT"] == 3
    # First call started at the deep backfill floor.
    assert exchange.calls[0][2] == intraday.DEFAULT_SINCE_MS_1H

    # Second refresh resumes AFTER the last cached hour -- no re-fetch.
    exchange.calls.clear()
    written = intraday.refresh_hourly_bars(conn, symbols=("BTC/USDT",), exchange=exchange)
    assert written["BTC/USDT"] == 0
    assert exchange.calls[0][2] == t2 + 60 * 60 * 1000

    bars = intraday.get_hourly_bars(conn, "BTC/USDT")
    assert [b["ts"] for b in bars] == [
        "2026-08-03T10:00:00Z", "2026-08-03T11:00:00Z", "2026-08-03T12:00:00Z",
    ]


def test_refresh_drops_the_still_forming_current_hour(conn):
    now = datetime.now(timezone.utc)
    current_hour = now.strftime("%Y-%m-%dT%H:00:00Z")
    exchange = _FakeExchange(rows=[
        [_ms(current_hour), 1, 2, 0.5, 1.5, 10],  # partial candle -- must drop
    ])

    written = intraday.refresh_hourly_bars(conn, symbols=("BTC/USDT",), exchange=exchange)

    assert written["BTC/USDT"] == 0
    assert intraday.get_hourly_bars(conn, "BTC/USDT") == []


def test_one_failing_symbol_never_kills_the_rest(conn):
    t0 = _ms("2026-08-03T10:00:00Z")
    exchange = _FakeExchange(rows=[[t0, 1, 2, 0.5, 1.5, 10]], fail_symbols={"PEPE/USDT"})

    written = intraday.refresh_hourly_bars(
        conn, symbols=("PEPE/USDT", "BTC/USDT"), exchange=exchange
    )

    assert written["PEPE/USDT"] == -1
    assert written["BTC/USDT"] == 1
