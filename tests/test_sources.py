"""Tests for trader.ground_truth.sources — stock and crypto source adapters."""

from unittest.mock import patch

from trader.ground_truth.sources import (
    CryptoMoversSource,
    SourceUnavailableError,
    StockGainersSource,
)


def test_stock_source_returns_50_normalized_rows(mock_yf_screen_result):
    with patch("yfinance.screen", return_value=mock_yf_screen_result):
        rows = StockGainersSource().fetch_top_movers(count=50)

    assert len(rows) == 50
    for row in rows:
        assert "ticker" in row
        assert "price" in row
        assert "pct_gain" in row
        assert "rank" in row
        assert row["source"] == "stock"


def test_stock_source_falls_back_to_finviz_on_yfinance_exception(mock_finviz_rows):
    with patch("yfinance.screen", side_effect=RuntimeError("yfinance boom")), patch(
        "finviz.screener.Screener", return_value=mock_finviz_rows
    ):
        rows = StockGainersSource().fetch_top_movers(count=50)

    assert len(rows) == 50
    for row in rows:
        assert isinstance(row["pct_gain"], float)


def test_stock_source_raises_source_unavailable_when_both_fail():
    with patch("yfinance.screen", side_effect=RuntimeError("yfinance boom")), patch(
        "finviz.screener.Screener", side_effect=RuntimeError("finviz boom")
    ):
        try:
            StockGainersSource().fetch_top_movers(count=50)
            assert False, "expected SourceUnavailableError"
        except SourceUnavailableError:
            pass


def test_crypto_source_row_has_coingecko_id_and_symbol(mock_coingecko_markets_response):
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_coingecko_markets_response
        mock_get.return_value.raise_for_status.return_value = None
        rows = CryptoMoversSource().fetch_top_movers(count=50)

    assert len(rows) == 50
    for row, source_row in zip(rows, mock_coingecko_markets_response):
        assert "coingecko_id" in row
        assert "ticker" in row
        assert row["ticker"] == row["ticker"].upper()


def test_crypto_source_sorts_by_pct_change_desc(mock_coingecko_markets_response):
    unsorted = list(reversed(mock_coingecko_markets_response))
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = unsorted
        mock_get.return_value.raise_for_status.return_value = None
        rows = CryptoMoversSource().fetch_top_movers(count=10)

    assert len(rows) == 10
    pct_gains = [row["pct_gain"] for row in rows]
    assert pct_gains == sorted(pct_gains, reverse=True)
