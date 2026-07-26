"""Tests for trader.data.crypto_source — ccxt Binance fetch, pagination, and UTC-date normalization."""

from unittest.mock import Mock, patch

import pytest

try:
    from trader.data import crypto_source
except ImportError:
    # trader.data.crypto_source does not exist yet (RED phase) — collection must
    # still succeed so all 4 tests are collected; each test then fails with an
    # AttributeError referencing the missing trader.data.crypto_source contract.
    crypto_source = None


def _row(ts_ms: int, price: float = 100.0) -> list:
    return [ts_ms, price, price + 1, price - 1, price + 0.5, 10.0]


ONE_DAY_MS = 24 * 60 * 60 * 1000


def test_crypto_bars_paginate_past_1000():
    first_batch = [_row(1_000_000 + i * ONE_DAY_MS) for i in range(1000)]
    last_first_ts = first_batch[-1][0]
    second_batch = [_row(last_first_ts + ONE_DAY_MS + i * ONE_DAY_MS) for i in range(200)]

    exchange = Mock()
    exchange.fetch_ohlcv = Mock(side_effect=[first_batch, second_batch, []])

    result = crypto_source.fetch_all_daily_ohlcv(exchange, "BTC/USDT", since_ms=1_000_000)

    assert len(result) == 1200
    assert result == first_batch + second_batch
    # Only 2 calls should occur — the second batch (200 rows) is shorter than
    # limit=1000, so pagination stops without a third call.
    assert exchange.fetch_ohlcv.call_count == 2

    first_call_kwargs = exchange.fetch_ohlcv.call_args_list[0].kwargs
    second_call_kwargs = exchange.fetch_ohlcv.call_args_list[1].kwargs
    assert first_call_kwargs["since"] == 1_000_000
    assert first_call_kwargs["limit"] == 1000
    assert first_call_kwargs["timeframe"] == "1d"
    assert second_call_kwargs["since"] == last_first_ts + ONE_DAY_MS


def test_normalize_crypto_bars_converts_ms_to_utc_date():
    raw_ohlcv = [
        [1704067200000, 42000.0, 42500.0, 41800.0, 42300.0, 1234.5],  # 2024-01-01 UTC
    ]

    rows = crypto_source.normalize_crypto_bars(raw_ohlcv)

    assert len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == {"ts", "open", "high", "low", "close", "volume"}
    assert row["ts"] == "2024-01-01"
    assert row["open"] == 42000.0
    assert row["high"] == 42500.0
    assert row["low"] == 41800.0
    assert row["close"] == 42300.0
    assert row["volume"] == 1234.5


def test_fetch_crypto_bars_constructs_binance_with_no_api_key():
    mock_exchange = Mock()
    mock_exchange.fetch_ohlcv = Mock(return_value=[])

    with patch(
        "trader.data.crypto_source.ccxt.binance", return_value=mock_exchange
    ) as mock_binance_cls:
        crypto_source.fetch_crypto_bars("BTC/USDT")

    mock_binance_cls.assert_called_once_with()
    assert mock_exchange.fetch_ohlcv.call_args.kwargs["timeframe"] == "1d"


def test_normalize_crypto_bars_raises_on_malformed_row():
    raw_ohlcv = [[1704067200000, 42000.0, 42500.0]]  # only 3 elements, missing l/c/v

    with pytest.raises(ValueError):
        crypto_source.normalize_crypto_bars(raw_ohlcv)
