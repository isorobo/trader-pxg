"""Live smoke test against real Yahoo Finance and CoinGecko endpoints.

Confirms Assumption A1 (yfinance's day_gainers screener returns ~50 rows on the
installed 1.5.2, not the 25-row truncation bug in Pitfall 1) and Assumption A2
(the CoinGecko demo key authenticates and returns rows). No mocks — this hits
live networks.

Run with: .venv\\Scripts\\python.exe -m trader.ground_truth.smoke
"""

import sys

from trader.ground_truth.sources import CryptoMoversSource, StockGainersSource


def main() -> int:
    stock_rows = StockGainersSource().fetch_top_movers(count=50)
    print(f"stock: {len(stock_rows)} rows, first ticker={stock_rows[0]['ticker'] if stock_rows else None}")

    crypto_rows = CryptoMoversSource().fetch_top_movers(count=50)
    print(f"crypto: {len(crypto_rows)} rows, first ticker={crypto_rows[0]['ticker'] if crypto_rows else None}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
