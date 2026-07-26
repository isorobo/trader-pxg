"""ccxt Binance crypto daily bar fetch, pagination, and UTC-date normalization.

D-02 requires 3+ years of daily crypto history; Kraken's own OHLC REST endpoint
hard-caps at 720 of the most recent candles regardless of `since`
(01-RESEARCH.md Pitfall 2). This module implements ONLY the Binance fetch path
for Phase 1 — no Kraken data-fetch code exists here, which eliminates the
silent-truncation risk by construction rather than a runtime row-count check.

CRYPTO_VENUE is the true data-provenance value Plan 01-06 writes into
`bars.venue` for every crypto row — Kraken remains only the fee-model venue
(01-RESEARCH.md Open Questions #1, RESOLVED).
"""

from datetime import datetime, timezone

import ccxt

CRYPTO_VENUE = "binance"

# 2017-01-01T00:00:00Z in milliseconds — a fixed early-epoch default for
# fetch_crypto_bars when no since_ms is given, deep enough to precede any
# Binance-listed pair's actual listing date.
_DEFAULT_SINCE_MS = 1_483_228_800_000

_ONE_DAY_MS = 24 * 60 * 60 * 1000

_EXPECTED_ROW_LENGTH = 6


def fetch_all_daily_ohlcv(exchange, symbol: str, since_ms: int) -> list[list]:
    """Paginate past Binance's 1000-candle-per-call limit for daily OHLCV.

    Loops calling exchange.fetch_ohlcv(symbol, timeframe="1d", since=cursor,
    limit=1000), accumulating rows across calls. Advances cursor to one day
    past the last row's timestamp between calls. Stops as soon as a batch is
    empty or shorter than limit=1000 (01-RESEARCH.md Pattern 3).
    """
    all_rows: list[list] = []
    cursor = since_ms
    while True:
        batch = exchange.fetch_ohlcv(symbol, timeframe="1d", since=cursor, limit=1000)
        if not batch:
            break
        all_rows.extend(batch)
        cursor = batch[-1][0] + _ONE_DAY_MS
        if len(batch) < 1000:
            break
    return all_rows


def normalize_crypto_bars(raw_ohlcv: list[list]) -> list[dict]:
    """Convert raw ccxt OHLCV rows into ts/open/high/low/close/volume dicts.

    Each row's Unix-millisecond timestamp converts to a plain UTC calendar-date
    string — daily bars have no meaningful intraday component. Raises a clear
    ValueError, not an opaque IndexError, if a row has fewer than 6 elements
    (01-RESEARCH.md Pitfall 2 threat register T-01-10).
    """
    normalized = []
    for row in raw_ohlcv:
        if len(row) < _EXPECTED_ROW_LENGTH:
            raise ValueError(
                f"crypto bar row has {len(row)} element(s), expected at least "
                f"{_EXPECTED_ROW_LENGTH}: {row!r}"
            )
        timestamp_ms, open_, high, low, close, volume = row[:6]
        normalized.append(
            {
                "ts": datetime.fromtimestamp(
                    timestamp_ms / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d"),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
    return normalized


def fetch_crypto_bars(symbol: str, since_ms: int | None = None) -> list[dict]:
    """Fetch daily bars for symbol via Binance (ccxt) and normalize them.

    Constructs ccxt.binance() with no API key — public market data only.
    With no since_ms given, defaults to a fixed early epoch (2017-01-01) so
    full available history is requested, not a truncated default window.
    """
    exchange = ccxt.binance()
    effective_since_ms = _DEFAULT_SINCE_MS if since_ms is None else since_ms
    raw_ohlcv = fetch_all_daily_ohlcv(exchange, symbol, effective_since_ms)
    return normalize_crypto_bars(raw_ohlcv)
