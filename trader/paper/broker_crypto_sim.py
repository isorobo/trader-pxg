"""Crypto simulated-ledger price/fill adapter (05-03-PLAN.md, D-04).

The crypto leg never places a real order in Phase 5 -- this module's public
surface is price-only (`fetch_price`) and pure arithmetic
(`simulate_fill`, reusing `trader.backtest.fills` verbatim, never
re-deriving fee/slippage math here). `kraken_balance_check` is a read-only,
optional, informational-only sanity hook (D-04, Open Question 2's locked
default) -- it is never wired to any halt path.

T-05-10: this module never names or calls a ccxt order-submission method
-- pinned by tests/test_broker_crypto_sim.py.
"""

from __future__ import annotations

import os

from trader.backtest import fills
from trader.paper import config


def fetch_price(symbol: str, client=None) -> float:
    """Live last-traded price for symbol via ccxt.binance() (public,
    unauthenticated -- no API key), matching trader/data/crypto_source.py's
    existing lazy-import-inside-the-function pattern.

    `client` is the constructor-injection-equivalent test seam: production
    callers pass None and get a real `ccxt.binance()`; tests inject a fake
    with a `.fetch_ticker` method -- no real network call in any automated
    test.
    """
    if client is None:
        import ccxt

        client = ccxt.binance()
    return client.fetch_ticker(symbol)["last"]


def simulate_fill(
    symbol: str, side: str, qty: float, reference_price: float, asset_class: str
) -> dict:
    """Pure, zero-I/O simulated fill: Phase 2's fee/slippage model applied
    to a live reference price (D-04). Never submits a real order -- `symbol`
    is accepted only for the returned dict's shape parity with the IBKR
    adapter's fill records, and is not itself used to look anything up here.

    Raises KeyError (via fills.apply_slippage/fills.fee_for) for any
    asset_class outside {"stock", "crypto_major", "memecoin"} -- never
    silently defaults.
    """
    fill_price = fills.apply_slippage(reference_price, side, asset_class)
    fee = fills.fee_for(asset_class, qty, fill_price)
    return {"fill_price": fill_price, "fee": fee, "qty": qty}


def kraken_balance_check(
    api_key: str | None = None, api_secret: str | None = None, client=None
) -> dict | None:
    """Read-only Kraken balance sanity check (D-04) -- "if present", never
    a hard blocker.

    Resolves api_key/api_secret from the caller-supplied arguments, falling
    back to config.KRAKEN_API_KEY_ENV/KRAKEN_API_SECRET_ENV read at call
    time when either argument is None. Returns None (never raises) if
    either credential is still unset after that fallback -- informational
    only, never wired to any halt path (Open Question 2's locked default).
    """
    resolved_key = api_key if api_key is not None else os.environ.get(config.KRAKEN_API_KEY_ENV)
    resolved_secret = (
        api_secret if api_secret is not None else os.environ.get(config.KRAKEN_API_SECRET_ENV)
    )
    if not resolved_key or not resolved_secret:
        return None
    if client is None:
        import ccxt

        client = ccxt.kraken({"apiKey": resolved_key, "secret": resolved_secret})
    return client.fetch_balance()
