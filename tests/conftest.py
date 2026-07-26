"""Shared pytest fixtures for the ground_truth test suite."""

import pytest

from trader.ground_truth import db


@pytest.fixture
def tmp_db_path(tmp_path):
    """Path to a fresh, non-existent SQLite file inside pytest's tmp_path."""
    return str(tmp_path / "trader.db")


@pytest.fixture
def conn(tmp_db_path):
    """A live connection to a fresh temp DB, closed after the test."""
    connection = db.get_connection(tmp_db_path)
    yield connection
    connection.close()


@pytest.fixture
def mock_yf_screen_result():
    """Shape of yfinance's yf.screen("day_gainers") response: {"quotes": [...]}."""
    quotes = [
        {
            "symbol": f"TICK{i}",
            "regularMarketPrice": 10.0 + i,
            "regularMarketChangePercent": 50.0 - i * 0.1,
        }
        for i in range(50)
    ]
    return {"quotes": quotes}


@pytest.fixture
def mock_finviz_rows():
    """Shape of finviz.screener.Screener rows: string Price/Change fields."""
    return [
        {
            "Ticker": f"FTICK{i}",
            "Price": f"{20.0 + i:.2f}",
            "Change": f"{45.20 - i * 0.1:.2f}%",
        }
        for i in range(50)
    ]


@pytest.fixture
def mock_coingecko_markets_response():
    """Shape of CoinGecko /coins/markets response rows."""
    return [
        {
            "id": f"coin-{i}",
            "symbol": f"c{i}",
            "current_price": 1.0 + i,
            "price_change_percentage_24h": 30.0 - i * 0.2,
        }
        for i in range(50)
    ]
