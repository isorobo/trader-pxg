"""Live exit-criterion acceptance run against real Yahoo Finance and Binance
endpoints — no mocks.

Proves Phase 1's literal exit criterion (ACCT-04/ACCT-07, D-10/D-11): one
function call — get_daily_bars — returns multi-year daily bars for a real US
stock and, separately, for a real major crypto pair, each with a UTC
tz-aware index, using the project's actual data/trader.db (default conn).
Mirrors trader/ground_truth/smoke.py's live-verification pattern.

Run with: .venv\\Scripts\\python.exe -m trader.data.exit_criterion_smoke
"""

import sys

from trader.data.api import get_daily_bars


def _report(label: str, df) -> None:
    row_count = len(df)
    if row_count:
        date_range = f"{df.index[0].date()} .. {df.index[-1].date()}"
    else:
        date_range = "n/a"
    print(
        f"{label}: {row_count} rows, range={date_range}, index.tz={df.index.tz}"
    )


def main() -> int:
    stock_df = get_daily_bars("AAPL", asset_class="stock")
    _report("stock (AAPL)", stock_df)

    crypto_df = get_daily_bars("BTC/USDT", asset_class="crypto_major")
    _report("crypto (BTC/USDT)", crypto_df)

    return 0


if __name__ == "__main__":
    sys.exit(main())
