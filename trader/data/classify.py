"""Crypto instrument classification (D-16).

classify_crypto_instrument queries CoinGecko's /coins/{id} endpoint exactly
once per instrument (never per bar fetch — see 01-RESEARCH.md Pattern 4/
Pitfall 3) and checks the returned categories list for "Meme". It is a pure
classification function; it never persists anything.

The companion register_crypto_instrument onboarding function (classify-then-
persist, satisfying D-16's "classification happens at insert time") is added
in its own RED/GREEN cycle — see Task 3/4 of 01-02-PLAN.md.
"""

import requests

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
