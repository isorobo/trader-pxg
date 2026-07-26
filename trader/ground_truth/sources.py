"""Stock and crypto source adapters with fallback (Pattern 1, 00-RESEARCH.md).

D-01: yfinance is the primary stock gainers source; finviz is the fallback.
D-02: capture the top ~50 unfiltered — no threshold filtering at capture time.
D-04: crypto rows store the CoinGecko id, never just the symbol (symbols collide).
"""

import logging
import os

import finviz.screener
import requests
import yfinance
from dotenv import load_dotenv

log = logging.getLogger(__name__)

COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"


class SourceUnavailableError(Exception):
    """Raised when every available path for a source has failed."""


class StockGainersSource:
    """Yahoo Finance day-gainers screener, falling back to finviz on failure."""

    def fetch_top_movers(self, count: int = 50) -> list[dict]:
        try:
            return self._fetch_yfinance(count)
        except Exception as primary_error:
            log.warning(
                "yfinance screener failed (%s: %s), falling back to finviz",
                type(primary_error).__name__,
                primary_error,
            )
            try:
                return self._fetch_finviz(count)
            except Exception as fallback_error:
                log.warning(
                    "finviz fallback also failed (%s: %s)",
                    type(fallback_error).__name__,
                    fallback_error,
                )
                raise SourceUnavailableError(
                    "Both yfinance and finviz stock sources failed"
                ) from fallback_error

    def _fetch_yfinance(self, count: int) -> list[dict]:
        result = yfinance.screen("day_gainers", count=count)
        quotes = result["quotes"]
        rows = []
        for i, quote in enumerate(quotes[:count]):
            rows.append(
                {
                    "ticker": quote["symbol"],
                    "price": float(quote["regularMarketPrice"]),
                    "pct_gain": float(quote["regularMarketChangePercent"]),
                    "rank": i + 1,
                    "source": "stock",
                }
            )
        return rows

    def _fetch_finviz(self, count: int) -> list[dict]:
        raw_rows = finviz.screener.Screener(
            filters=[], order="Change", signal="Top Gainers"
        )
        rows = []
        for i, raw_row in enumerate(list(raw_rows)[:count]):
            change_str = str(raw_row["Change"]).rstrip("%")
            rows.append(
                {
                    "ticker": raw_row["Ticker"],
                    "price": float(raw_row["Price"]),
                    "pct_gain": float(change_str),
                    "rank": i + 1,
                    "source": "stock",
                }
            )
        return rows


class CryptoMoversSource:
    """CoinGecko /coins/markets top 24h movers, sorted client-side (D-03/D-04)."""

    def fetch_top_movers(self, count: int = 50) -> list[dict]:
        load_dotenv()
        api_key = os.environ.get("COINGECKO_API_KEY", "")

        try:
            response = requests.get(
                COINGECKO_MARKETS_URL,
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": 250,
                    "price_change_percentage": "24h",
                    "sparkline": "false",
                },
                headers={"x-cg-demo-api-key": api_key},
                timeout=10,
            )
            response.raise_for_status()
            coins = response.json()
        except Exception as error:
            log.warning(
                "CoinGecko markets call failed (%s: %s)",
                type(error).__name__,
                error,
            )
            raise SourceUnavailableError("CoinGecko crypto source failed") from error

        coins = sorted(
            coins,
            key=lambda coin: coin.get("price_change_percentage_24h") or 0,
            reverse=True,
        )

        rows = []
        for i, coin in enumerate(coins[:count]):
            rows.append(
                {
                    "coingecko_id": coin["id"],
                    "ticker": coin["symbol"].upper(),
                    "price": float(coin["current_price"]),
                    "pct_gain": float(coin["price_change_percentage_24h"]),
                    "rank": i + 1,
                    "source": "crypto",
                }
            )
        return rows
