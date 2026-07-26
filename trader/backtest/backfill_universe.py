"""Phase 3's one-time live backfill of the frozen 25-symbol universe
(STRAT-03/04/05's data dependency).

Mirrors trader/backtest/sanity_universe.py's shape exactly: this module
deliberately calls ONLY trader.data.api.get_daily_bars for every fetch --
never trader.data.stock_source or trader.data.crypto_source directly -- so
the cache-first/classify-then-route contract Phase 1 already built is
reused exactly, not re-implemented here.

Stock symbols pass asset_class="stock" explicit (no classification call
needed). Crypto symbols (crypto-major/legacy-memecoin and new-memecoin
buckets) pass asset_class=None so resolve_instrument's live CoinGecko
classification path runs for any symbol not yet registered in the
instruments table -- SHIB/PEPE/BONK/WIF are new registrations this phase;
BTC/ETH/DOGE are already registered from Phase 2's sanity universe.

Stock symbols pass an explicit, deliberately ancient `start` date
(_STOCK_BACKFILL_START, well before any US equity's real listing date)
rather than leaving start=None. This works around a real cache-hit gap in
trader/data/api.py's `_is_cache_hit` (an unchanged, consume-only Phase 1
interface per this plan): when start is None, any pre-existing cached row
for a symbol is treated as a full cache hit regardless of how little
history it actually covers. Several of this phase's 15 new stock symbols
already had a partial 2023-2024-only cache from 03-RESEARCH.md's live
sweep-runtime benchmark, so a plain start=None call would have silently
skipped the live fetch and left only ~2 years cached -- short of the stock
choppy regime's 2015-01-01 tune_start. Passing an old explicit start makes
`_is_cache_hit` correctly see a miss (cached[0]["ts"] > start) and
`stock_source.fetch_stock_bars` still requests full available history via
`ticker.history(start=..., end=None)`, which yfinance clips to each
ticker's actual first bar -- confirmed equivalent in effect to
`period="max"` by direct verification against this repo's venv.
Crypto symbols keep start=None: `crypto_source.fetch_crypto_bars` always
returns full history regardless of the start argument, and this phase's
crypto cache already came back with full-range data on the first run.

This is Phase 3's one-time live network step, exempted from the fast
pytest loop per 03-VALIDATION.md's "Live/manual command exemption" (see
also this plan's threat model, T-03-05: reuses Phase 1's already-tested
get_daily_bars cache-first fetch path verbatim, no new parsing/trust logic
added here).

Run with: .venv\\Scripts\\python.exe -m trader.backtest.backfill_universe
"""

from __future__ import annotations

import sys

from trader.data.api import get_daily_bars

from trader.backtest.universe import (
    CRYPTO_MAJOR_LEGACY_MEME_UNIVERSE,
    NEW_MEMECOIN_UNIVERSE,
    STOCK_UNIVERSE,
)

# Deliberately ancient -- before any US equity's real listing date -- so
# api.py's _is_cache_hit sees a miss for any symbol whose cache doesn't
# already reach this far back, forcing a full-history live fetch (see
# module docstring above for why this is needed despite start=None
# nominally meaning "full history").
_STOCK_BACKFILL_START = "1900-01-01"


def _report(label: str, df) -> None:
    """Print row count and date range for one symbol's cached bars, mirroring
    trader/backtest/sanity_universe.py's _report helper style."""
    row_count = len(df)
    if row_count:
        date_range = f"{df.index[0].date()} .. {df.index[-1].date()}"
    else:
        date_range = "n/a"
    print(f"{label}: {row_count} rows, range={date_range}")


def main() -> int:
    """Backfill every universe symbol into the real, shared data/trader.db
    (conn=None routes get_daily_bars to trader.data.db.get_connection()'s
    default path, deliberately, matching sanity_universe.py's precedent --
    not the usual tmp_db_path test-isolation pattern).

    Raises RuntimeError (does not silently continue) if any symbol
    backfills with zero rows -- a zero-row symbol would silently starve
    every regime window that depends on it.
    """
    for symbol in STOCK_UNIVERSE:
        df = get_daily_bars(
            symbol, start=_STOCK_BACKFILL_START, asset_class="stock", conn=None
        )
        _report(symbol, df)
        if len(df) == 0:
            raise RuntimeError(
                f"{symbol} backfilled with zero rows -- cannot proceed "
                "with an empty universe symbol."
            )

    for symbol in CRYPTO_MAJOR_LEGACY_MEME_UNIVERSE + NEW_MEMECOIN_UNIVERSE:
        df = get_daily_bars(symbol, asset_class=None, conn=None)
        _report(symbol, df)
        if len(df) == 0:
            raise RuntimeError(
                f"{symbol} backfilled with zero rows -- cannot proceed "
                "with an empty universe symbol."
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
