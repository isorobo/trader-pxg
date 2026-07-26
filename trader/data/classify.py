"""Crypto instrument classification and onboarding (D-16).

classify_crypto_instrument queries CoinGecko's /coins/{id} endpoint exactly
once per instrument (never per bar fetch — see 01-RESEARCH.md Pattern 4/
Pitfall 3) and checks the returned categories list for "Meme". It is a pure
classification function; it never persists anything.

register_crypto_instrument is the one-time onboarding caller: it classifies
(unless an override is supplied) and persists the result to instruments via
trader.data.db.upsert_instrument in a single call, satisfying D-16's
"classification happens at insert time".
"""

import os

import requests
from dotenv import load_dotenv

from trader.data import db

COINGECKO_COIN_URL = "https://api.coingecko.com/api/v3/coins/{coingecko_id}"


def classify_crypto_instrument(coingecko_id: str, api_key: str) -> str:
    """Return "memecoin" or "crypto_major" from CoinGecko's category taxonomy.

    Never logs api_key. Propagates any HTTP error (e.g. a 429) rather than
    swallowing it (Pitfall 3) — callers must not treat a rate-limit response
    as a silent "crypto_major" default.
    """
    response = requests.get(
        COINGECKO_COIN_URL.format(coingecko_id=coingecko_id),
        params={
            "localization": "false",
            "tickers": "false",
            "market_data": "false",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "false",
        },
        headers={"x-cg-demo-api-key": api_key},
        timeout=10,
    )
    response.raise_for_status()
    categories = response.json().get("categories") or []
    return "memecoin" if "Meme" in categories else "crypto_major"


def register_crypto_instrument(
    conn,
    symbol: str,
    venue: str,
    coingecko_id: str,
    override: str | None = None,
) -> str:
    """Classify (unless overridden) and persist a new crypto instrument.

    If override is given, skip the CoinGecko call entirely — manual
    reclassification (D-16) takes precedence and never spends a
    rate-limited call. Otherwise classify via classify_crypto_instrument
    using COINGECKO_API_KEY loaded from .env. Either way, persists via
    db.upsert_instrument in the same call and returns the resulting
    asset_class.
    """
    if override is not None:
        asset_class = override
    else:
        load_dotenv()
        api_key = os.environ.get("COINGECKO_API_KEY", "")
        asset_class = classify_crypto_instrument(coingecko_id, api_key)

    db.upsert_instrument(
        conn,
        symbol,
        venue,
        asset_class,
        coingecko_id=coingecko_id,
        override=override,
    )
    return asset_class
