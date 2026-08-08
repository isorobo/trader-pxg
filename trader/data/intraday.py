"""Hourly crypto bar ingestion (intraday track, owner directive 2026-08-04
"make it so its real": tested at the hour, traded at the hour).

Fetches 1h OHLCV from Binance via ccxt (public, no API key -- the exact
crypto_source.py pattern at a faster timeframe) into the existing bars
table under timeframe='1h'. Timestamps keep their FULL UTC hour
("YYYY-MM-DDTHH:00:00Z" ISO form) -- unlike daily bars, the intraday
component is the whole point.

Incremental by design: refresh_hourly_bars resumes from the last cached
hour per symbol, so the scheduled hourly loop fetches one or two new bars,
not years. Stock symbols are OUT OF SCOPE here -- free hourly stock data
deep enough for honest tune/OOS windows does not exist; the intraday track
is crypto-first (the phase doc's own Phase 9 PDT note points the same way).
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone

from trader.backtest.universe import (
    BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
    BUCKET_NEW_MEMECOIN,
    UNIVERSE_BY_BUCKET,
)
from trader.data import db
from trader.data.crypto_source import CRYPTO_VENUE

TIMEFRAME_1H = "1h"

# 2023-01-01T00:00:00Z -- the intraday backfill floor. Deep enough for a
# multi-year tune window on majors while keeping the first backfill to a
# few thousand candles per symbol; memecoins simply start at listing.
DEFAULT_SINCE_MS_1H = 1_672_531_200_000

_ONE_HOUR_MS = 60 * 60 * 1000
_EXPECTED_ROW_LENGTH = 6

INTRADAY_SYMBOLS: tuple[str, ...] = tuple(
    UNIVERSE_BY_BUCKET[BUCKET_CRYPTO_MAJOR_LEGACY_MEME]
) + tuple(UNIVERSE_BY_BUCKET[BUCKET_NEW_MEMECOIN])


def fetch_all_hourly_ohlcv(exchange, symbol: str, since_ms: int) -> list[list]:
    """Paginate past Binance's 1000-candle-per-call limit for 1h OHLCV --
    crypto_source.fetch_all_daily_ohlcv's exact loop at hour granularity,
    with a polite pause between pages (a full backfill is ~30 pages/symbol)."""
    all_rows: list[list] = []
    cursor = since_ms
    while True:
        batch = exchange.fetch_ohlcv(
            symbol, timeframe=TIMEFRAME_1H, since=cursor, limit=1000
        )
        if not batch:
            break
        all_rows.extend(batch)
        cursor = batch[-1][0] + _ONE_HOUR_MS
        if len(batch) < 1000:
            break
        time.sleep(0.25)
    return all_rows


def normalize_hourly_bars(raw_ohlcv: list[list]) -> list[dict]:
    """ccxt OHLCV rows -> ts/open/high/low/close/volume dicts with FULL
    UTC-hour ISO timestamps. Raises ValueError on short rows (T-01-10)."""
    normalized = []
    for row in raw_ohlcv:
        if len(row) < _EXPECTED_ROW_LENGTH:
            raise ValueError(
                f"hourly bar row has {len(row)} element(s), expected at least "
                f"{_EXPECTED_ROW_LENGTH}: {row!r}"
            )
        timestamp_ms, open_, high, low, close, volume = row[:6]
        normalized.append(
            {
                "ts": datetime.fromtimestamp(
                    timestamp_ms / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
    return normalized


def _last_cached_ms(conn: sqlite3.Connection, symbol: str) -> int | None:
    row = conn.execute(
        "SELECT MAX(ts) FROM bars WHERE venue = ? AND symbol = ? AND timeframe = ?",
        (CRYPTO_VENUE, symbol, TIMEFRAME_1H),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    dt = datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def refresh_hourly_bars(
    conn: sqlite3.Connection,
    symbols: tuple[str, ...] = INTRADAY_SYMBOLS,
    exchange=None,
) -> dict[str, int]:
    """Fetch-and-cache new 1h bars for every intraday symbol, resuming one
    hour after each symbol's last cached bar (full backfill from
    DEFAULT_SINCE_MS_1H on first run). The CURRENT, still-forming hour's
    candle is dropped -- a partial bar in the cache would let a backtest or
    scan see a close that does not exist yet (the system never lies to
    itself). Returns {symbol: rows_written}. A per-symbol fetch failure
    logs-and-continues via the returned -1 sentinel, never aborting the
    other symbols' refresh."""
    if exchange is None:
        import ccxt

        exchange = ccxt.binance()

    current_hour_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")
    written: dict[str, int] = {}
    for symbol in symbols:
        try:
            last_ms = _last_cached_ms(conn, symbol)
            since_ms = (
                DEFAULT_SINCE_MS_1H if last_ms is None else last_ms + _ONE_HOUR_MS
            )
            raw = fetch_all_hourly_ohlcv(exchange, symbol, since_ms)
            rows = [
                r for r in normalize_hourly_bars(raw) if r["ts"] < current_hour_ts
            ]
            written[symbol] = db.write_bars_cache(
                conn, CRYPTO_VENUE, symbol, TIMEFRAME_1H, rows
            )
        except Exception as error:  # noqa: BLE001 -- one symbol never kills the rest
            print(
                f"hourly refresh failed for {symbol} "
                f"({type(error).__name__}: {error})"
            )
            written[symbol] = -1
    return written


def get_hourly_bars(
    conn: sqlite3.Connection,
    symbol: str,
    start: str | None = None,
    end: str | None = None,
) -> list[dict]:
    """Cached 1h bars for symbol, ts ascending -- read-only, never fetches."""
    return db.read_bars_cache(
        conn, CRYPTO_VENUE, symbol, TIMEFRAME_1H, start=start, end=end
    )


def main() -> None:
    """CLI: python -m trader.data.intraday  (backfill/refresh all symbols)."""
    conn = db.get_connection()
    try:
        written = refresh_hourly_bars(conn)
        total = sum(v for v in written.values() if v > 0)
        failed = [s for s, v in written.items() if v < 0]
        print(f"hourly refresh: {total} new bars across {len(written)} symbols")
        if failed:
            print(f"failed symbols: {failed}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
