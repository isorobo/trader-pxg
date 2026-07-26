"""Tests for trader.data.stock_source — yfinance fetch + UTC-date normalization."""

from unittest.mock import Mock, patch

import pandas as pd
import pytest

try:
    from trader.data import stock_source
except ImportError:
    # trader.data.stock_source does not exist yet (RED phase) — collection must
    # still succeed so all 4 tests are collected; each test then fails with an
    # AttributeError referencing the missing trader.data.stock_source contract.
    stock_source = None


def _tz_aware_fixture_df() -> pd.DataFrame:
    """A tz-aware (America/New_York) DataFrame shaped like yfinance's live output."""
    index = pd.date_range(
        "2026-07-20", periods=3, freq="D", tz="America/New_York"
    )
    return pd.DataFrame(
        {
            "Open": [210.5, 211.0, 212.2],
            "High": [212.0, 213.5, 214.0],
            "Low": [209.8, 210.5, 211.0],
            "Close": [211.9, 212.8, 213.1],
            "Volume": [51234000.0, 48000000.0, 52000000.0],
            "Dividends": [0.0, 0.0, 0.0],
            "Stock Splits": [0.0, 0.0, 0.0],
        },
        index=index,
    )


def test_stock_bars_normalize_to_utc_date():
    df = _tz_aware_fixture_df()

    rows = stock_source.normalize_stock_bars(df)

    assert len(rows) == 3
    for row in rows:
        assert set(row.keys()) == {"ts", "open", "high", "low", "close", "volume"}
        assert isinstance(row["ts"], str)
        assert len(row["ts"]) == 10  # YYYY-MM-DD, no time-of-day component
        # Confirm it parses as a plain calendar date with no offset suffix.
        assert row["ts"][4] == "-" and row["ts"][7] == "-"


def test_fetch_stock_bars_uses_period_max_when_no_start():
    mock_ticker = Mock()
    mock_ticker.history.return_value = _tz_aware_fixture_df()

    with patch("trader.data.stock_source.yfinance.Ticker", return_value=mock_ticker) as mock_ticker_cls:
        stock_source.fetch_stock_bars("AAPL")

    mock_ticker_cls.assert_called_once_with("AAPL")
    mock_ticker.history.assert_called_once_with(period="max", auto_adjust=True)


def test_fetch_stock_bars_uses_start_end_when_given():
    mock_ticker = Mock()
    mock_ticker.history.return_value = _tz_aware_fixture_df()

    with patch("trader.data.stock_source.yfinance.Ticker", return_value=mock_ticker):
        stock_source.fetch_stock_bars("AAPL", start="2024-01-01", end="2024-06-01")

    mock_ticker.history.assert_called_once_with(
        start="2024-01-01", end="2024-06-01", auto_adjust=True
    )


def test_normalize_stock_bars_raises_on_missing_columns():
    df = _tz_aware_fixture_df().drop(columns=["Volume"])

    with pytest.raises(ValueError):
        stock_source.normalize_stock_bars(df)
