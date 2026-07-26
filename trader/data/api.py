"""Phase 1's exit-criterion public API: get_daily_bars.

One function call returns multi-year daily bars for a US stock or a major
crypto pair (D-10/D-11), cache-first over the fetchers built in Plans 01-04
(stock_source) and 01-05 (crypto_source), backed by Plan 01-01's db.py schema
and cache helpers. resolve_instrument wires Plan 01-02's classification
onboarding (classify.register_crypto_instrument) so an unresolved crypto
symbol in D-15's named universe is classified via CoinGecko before routing —
never silently defaulted to crypto_major (D-16).
"""

import logging

import pandas as pd

from trader.data import classify, crypto_source, db, stock_source

logger = logging.getLogger(__name__)

# Base-asset ticker -> CoinGecko id, for D-15's named crypto universe.
# This is a symbol-to-id lookup, not a classification whitelist — the
# classification itself always comes from CoinGecko's live categories field
# (classify.classify_crypto_instrument), never from this map.
CRYPTO_COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "DOGE": "dogecoin",
    "SHIB": "shiba-inu",
    "PEPE": "pepe",
    "BONK": "bonk",
    "WIF": "dogwifcoin",
}

_TIMEFRAME = "daily"


def _venue_for_asset_class(asset_class: str) -> str:
    """Map asset_class to its true fetch-provenance venue.

    stock -> yahoo; crypto_major/memecoin -> crypto_source.CRYPTO_VENUE
    ("binance"). This is data provenance, never the Kraken fee-model venue
    (01-RESEARCH.md Pitfall 5 / orchestrator's locked decision).
    """
    if asset_class == "stock":
        return "yahoo"
    return crypto_source.CRYPTO_VENUE


def resolve_instrument(
    conn, symbol: str, asset_class: str | None = None
) -> tuple[str, str]:
    """Resolve (asset_class, venue) for symbol, classifying unresolved crypto.

    Resolution order:
    1. An explicit asset_class argument is treated as already-known truth —
       used directly, no classification call.
    2. An existing instruments row for symbol (its override if set, else its
       asset_class) — Phase 1 does not yet support one symbol under two
       asset classes simultaneously.
    3. No row and no explicit argument: if the symbol shape indicates crypto
       (contains "/"), derive the base asset and look it up in
       CRYPTO_COINGECKO_IDS. If found, classify and persist via
       classify.register_crypto_instrument (D-16's real classification
       path). If not found (a symbol outside the researched universe),
       persist directly as "crypto_major" with no coingecko_id — a
       documented degraded fallback — and log a warning.
    4. Otherwise (not crypto-shaped), resolve as "stock" with no
       classification call.
    """
    if asset_class is not None:
        return asset_class, _venue_for_asset_class(asset_class)

    row = conn.execute(
        "SELECT asset_class, override FROM instruments WHERE symbol = ? LIMIT 1",
        (symbol,),
    ).fetchone()
    if row is not None:
        resolved = row[1] if row[1] is not None else row[0]
        return resolved, _venue_for_asset_class(resolved)

    if "/" in symbol:
        venue = crypto_source.CRYPTO_VENUE
        base_asset = symbol.split("/")[0].upper()
        coingecko_id = CRYPTO_COINGECKO_IDS.get(base_asset)
        if coingecko_id is not None:
            resolved = classify.register_crypto_instrument(
                conn, symbol, venue, coingecko_id
            )
        else:
            logger.warning(
                "%s's base asset %s is outside the known crypto universe "
                "(CRYPTO_COINGECKO_IDS) — falling back to crypto_major "
                "with no CoinGecko classification call",
                symbol,
                base_asset,
            )
            db.upsert_instrument(conn, symbol, venue, "crypto_major", coingecko_id=None)
            resolved = "crypto_major"
        return resolved, venue

    return "stock", _venue_for_asset_class("stock")


def _is_cache_hit(cached: list[dict], start: str | None) -> bool:
    if not cached:
        return False
    if start is None:
        return True
    return cached[0]["ts"] <= start


def get_daily_bars(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    asset_class: str | None = None,
    conn=None,
) -> pd.DataFrame:
    """Return multi-year daily bars for symbol as a UTC tz-aware DataFrame.

    Cache-first: reads trader/data/db.py's bars cache before ever calling a
    live fetcher. On a cache miss, dispatches to stock_source.fetch_stock_bars
    or crypto_source.fetch_crypto_bars per the resolved asset_class, writes
    the fresh rows through the cache, then re-reads. The returned DataFrame's
    index is explicitly UTC tz-aware (never a naive date), so later phases'
    point-in-time iterator inherits an unambiguous contract (D-11).
    """
    if conn is None:
        conn = db.get_connection()

    resolved_asset_class, venue = resolve_instrument(conn, symbol, asset_class)

    cached = db.read_bars_cache(conn, venue, symbol, _TIMEFRAME, start, end)
    if not _is_cache_hit(cached, start):
        if resolved_asset_class == "stock":
            fresh_rows = stock_source.fetch_stock_bars(symbol, start, end)
        else:
            fresh_rows = crypto_source.fetch_crypto_bars(symbol)
        db.write_bars_cache(conn, venue, symbol, _TIMEFRAME, fresh_rows)
        cached = db.read_bars_cache(conn, venue, symbol, _TIMEFRAME, start, end)

    df = pd.DataFrame(cached, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize("UTC")
    df = df.set_index("ts").sort_index()
    df.index.name = None
    return df
