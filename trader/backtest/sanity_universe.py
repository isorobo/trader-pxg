"""The pinned D-14 sanity universe and its one-time live backfill (BACK-07).

SANITY_UNIVERSE is a documented mix of large-cap US stocks and BTC/ETH
majors -- the orchestrator's locked resolution for 02-09-PLAN.md's Open
Question 1 (02-RESEARCH.md): AAPL, MSFT, GOOGL (large-cap stocks) plus
BTC/USDT, ETH/USDT, DOGE/USDT (crypto majors). AAPL, BTC/USDT, and
DOGE/USDT are already cached in the shared data/trader.db as of phase
planning; MSFT, GOOGL, and ETH/USDT need this module's one-time backfill.

This module deliberately calls ONLY trader.data.api.get_daily_bars for
every fetch -- never trader.data.stock_source or trader.data.crypto_source
directly -- so the cache-first/classify-then-route contract Phase 1
already built is reused exactly, not re-implemented here.

main() is the one live, network-making, exempt step in this phase (per
02-VALIDATION.md's "Live/manual command exemption" and this plan's threat
model T-02-SC): it populates data/trader.db once so that
tests/test_backtest_sanity.py (Task 2) can run entirely offline against
the cache afterward.

Run with: .venv\\Scripts\\python.exe -m trader.backtest.sanity_universe
"""

from __future__ import annotations

import sys

from trader.data.api import get_daily_bars

# The pinned D-14 sanity universe (BACK-07). Order is not meaningful; the
# split between "no slash" (stock) and "contains slash" (crypto) below is
# what actually drives asset_class resolution, not this list's ordering.
SANITY_UNIVERSE = ["AAPL", "MSFT", "GOOGL", "BTC/USDT", "ETH/USDT", "DOGE/USDT"]


def _report(label: str, df) -> None:
    """Print row count and date range for one symbol's cached bars, mirroring
    trader/data/exit_criterion_smoke.py's _report helper style."""
    row_count = len(df)
    if row_count:
        date_range = f"{df.index[0].date()} .. {df.index[-1].date()}"
    else:
        date_range = "n/a"
    print(f"{label}: {row_count} rows, range={date_range}")


def main() -> int:
    """Backfill every SANITY_UNIVERSE symbol into the real, shared
    data/trader.db (conn=None routes get_daily_bars to
    trader.data.db.get_connection()'s default path, deliberately, per the
    plan's interfaces note -- not the usual tmp_db_path test-isolation
    pattern).

    Stock symbols (no "/") pass asset_class="stock" explicitly (no
    classification call needed). Crypto symbols (contain "/") pass
    asset_class=None so resolve_instrument's live CoinGecko classification
    path runs for any symbol not yet registered in the instruments table.
    """
    for symbol in SANITY_UNIVERSE:
        asset_class = "stock" if "/" not in symbol else None
        df = get_daily_bars(symbol, asset_class=asset_class, conn=None)
        _report(symbol, df)

    return 0


if __name__ == "__main__":
    sys.exit(main())
