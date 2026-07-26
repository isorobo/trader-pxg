"""Tests for trader.data.db — migration runner, instruments, and bars cache."""

import sqlite3

import pytest

try:
    from trader.data import db
except ImportError:
    # trader.data.db does not exist yet (RED phase) — collection must still
    # succeed so all 5 tests are collected; each test then fails with an
    # AttributeError on `db` (None) when it tries to call into the contract.
    db = None


@pytest.fixture
def data_conn(tmp_db_path):
    """A live connection to a fresh temp DB, bootstrapped via trader.data.db."""
    connection = db.get_connection(tmp_db_path)
    yield connection
    connection.close()


def test_migration_0002_creates_instruments_and_bars(data_conn):
    rows = data_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {row[0] for row in rows}
    assert "instruments" in table_names
    assert "bars" in table_names
    assert "schema_version" in table_names
    assert "snapshots" in table_names
    assert "poll_runs" in table_names

    max_version = data_conn.execute(
        "SELECT MAX(version) FROM schema_version"
    ).fetchone()[0]
    assert max_version == 2


def test_bars_unique_constraint(data_conn):
    row = {
        "ts": "2026-07-20",
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 103.0,
        "volume": 1000.0,
    }
    db.write_bars_cache(data_conn, "binance", "BTC/USDT", "daily", [row])
    db.write_bars_cache(data_conn, "binance", "BTC/USDT", "daily", [row])

    bars = db.read_bars_cache(data_conn, "binance", "BTC/USDT", "daily")
    assert len(bars) == 1


def test_upsert_and_get_instrument_round_trip(data_conn):
    db.upsert_instrument(
        data_conn,
        symbol="BTC/USDT",
        venue="binance",
        asset_class="crypto_major",
        coingecko_id="bitcoin",
        override=None,
    )

    instrument = db.get_instrument(data_conn, "BTC/USDT", "binance")
    assert instrument is not None
    assert set(instrument.keys()) == {
        "symbol",
        "venue",
        "asset_class",
        "coingecko_id",
        "override",
    }
    assert instrument["symbol"] == "BTC/USDT"
    assert instrument["venue"] == "binance"
    assert instrument["asset_class"] == "crypto_major"
    assert instrument["coingecko_id"] == "bitcoin"
    assert instrument["override"] is None


def test_read_bars_cache_filters_by_range(data_conn):
    rows = [
        {
            "ts": f"2026-07-{20 + i:02d}",
            "open": 100.0 + i,
            "high": 105.0 + i,
            "low": 99.0 + i,
            "close": 103.0 + i,
            "volume": 1000.0 + i,
        }
        for i in range(5)
    ]
    db.write_bars_cache(data_conn, "binance", "BTC/USDT", "daily", rows)

    result = db.read_bars_cache(
        data_conn,
        "binance",
        "BTC/USDT",
        "daily",
        start="2026-07-21",
        end="2026-07-23",
    )

    assert [r["ts"] for r in result] == ["2026-07-21", "2026-07-22", "2026-07-23"]
    assert result == sorted(result, key=lambda r: r["ts"])


def test_instruments_asset_class_check_constraint(data_conn):
    with pytest.raises(sqlite3.IntegrityError):
        data_conn.execute(
            "INSERT INTO instruments (symbol, venue, asset_class) VALUES (?, ?, ?)",
            ("BADCOIN", "binance", "not_a_real_class"),
        )
