"""Tests for trader.data.api — get_daily_bars cache-first routing, tz-aware
UTC DataFrame contract, and classification-wired resolve_instrument (D-10/
D-11/D-16).
"""

from unittest.mock import patch

import pandas as pd
import pytest

from trader.data import db

try:
    from trader.data import api
except ImportError:
    # trader.data.api does not exist yet (RED phase) — collection must still
    # succeed so all tests are collected; each test then fails with an
    # AttributeError on `api` (None) when it tries to call into the contract.
    api = None


@pytest.fixture
def data_conn(tmp_db_path):
    """A live connection to a fresh temp DB, bootstrapped via trader.data.db."""
    connection = db.get_connection(tmp_db_path)
    yield connection
    connection.close()


def _fixture_bars(count=3, start_day=20):
    return [
        {
            "ts": f"2026-07-{start_day + i:02d}",
            "open": 100.0 + i,
            "high": 105.0 + i,
            "low": 99.0 + i,
            "close": 103.0 + i,
            "volume": 1000.0 + i,
        }
        for i in range(count)
    ]


def test_get_daily_bars_stock_contract(data_conn):
    fixture_rows = _fixture_bars()
    with patch(
        "trader.data.api.stock_source.fetch_stock_bars", return_value=fixture_rows
    ):
        df = api.get_daily_bars("AAPL", asset_class="stock", conn=data_conn)

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert len(df) == 3


def test_get_daily_bars_index_is_utc_tz_aware(data_conn):
    fixture_rows = _fixture_bars()
    with patch(
        "trader.data.api.stock_source.fetch_stock_bars", return_value=fixture_rows
    ):
        df = api.get_daily_bars("AAPL", asset_class="stock", conn=data_conn)

    assert df.index.tz is not None
    assert str(df.index.tz) == "UTC"


def test_get_daily_bars_crypto_contract(data_conn):
    fixture_rows = _fixture_bars()
    with patch(
        "trader.data.api.crypto_source.fetch_crypto_bars", return_value=fixture_rows
    ):
        df = api.get_daily_bars(
            "BTC/USDT", asset_class="crypto_major", conn=data_conn
        )

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]

    cached = db.read_bars_cache(data_conn, "binance", "BTC/USDT", "daily")
    assert len(cached) == 3


def test_cache_hit_skips_fetch(data_conn):
    fixture_rows = _fixture_bars()
    db.write_bars_cache(data_conn, "yahoo", "AAPL", "daily", fixture_rows)

    with patch("trader.data.api.stock_source.fetch_stock_bars") as mock_fetch:
        api.get_daily_bars("AAPL", asset_class="stock", conn=data_conn)

    mock_fetch.assert_not_called()


def test_cache_miss_then_cache_hit(data_conn):
    fixture_rows = _fixture_bars()

    with patch(
        "trader.data.api.stock_source.fetch_stock_bars", return_value=fixture_rows
    ) as mock_fetch:
        first_df = api.get_daily_bars("AAPL", asset_class="stock", conn=data_conn)

    mock_fetch.assert_called_once()

    with patch("trader.data.api.stock_source.fetch_stock_bars") as mock_fetch_again:
        second_df = api.get_daily_bars("AAPL", asset_class="stock", conn=data_conn)

    mock_fetch_again.assert_not_called()
    pd.testing.assert_frame_equal(first_df, second_df)


def test_get_daily_bars_resolves_asset_class_from_instruments_table(data_conn):
    db.upsert_instrument(data_conn, "MSFT", "yahoo", "stock")
    fixture_rows = _fixture_bars()

    with patch(
        "trader.data.api.stock_source.fetch_stock_bars", return_value=fixture_rows
    ) as mock_fetch:
        df = api.get_daily_bars("MSFT", conn=data_conn)

    mock_fetch.assert_called_once()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 3


def test_get_daily_bars_registers_new_crypto_instrument_via_coingecko(data_conn):
    fixture_rows = _fixture_bars()

    with patch(
        "trader.data.api.classify.register_crypto_instrument",
        return_value="crypto_major",
    ) as mock_register, patch(
        "trader.data.api.crypto_source.fetch_crypto_bars", return_value=fixture_rows
    ) as mock_fetch:
        api.get_daily_bars("DOGE/USDT", conn=data_conn)

    mock_register.assert_called_once_with(
        data_conn, "DOGE/USDT", "binance", "dogecoin"
    )
    mock_fetch.assert_called_once()


def test_get_daily_bars_falls_back_without_classification_for_unmapped_crypto_symbol(
    data_conn,
):
    fixture_rows = _fixture_bars()

    with patch(
        "trader.data.api.classify.register_crypto_instrument"
    ) as mock_register, patch(
        "trader.data.api.crypto_source.fetch_crypto_bars", return_value=fixture_rows
    ):
        api.get_daily_bars("ZZZ/USDT", conn=data_conn)

    mock_register.assert_not_called()
    instrument = db.get_instrument(data_conn, "ZZZ/USDT", "binance")
    assert instrument is not None
    assert instrument["asset_class"] == "crypto_major"
    assert instrument["coingecko_id"] is None
