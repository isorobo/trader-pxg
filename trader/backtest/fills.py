"""Fee, slippage, and conservative fill-price functions for the backtest
harness (BACK-02, BACK-03, D-04, D-06, D-07, D-08).

Every function here is a pure function of (asset_class, price, qty, side).
Fee and slippage numbers themselves live only in trader.backtest.config
(D-06's "fees are parameters, not hard-coded in engine logic"); this module
never re-declares them, so a config change here always requires touching
config.py, not this file. Every function that takes an asset_class raises
KeyError (not a silent default) for an asset_class outside
{"stock", "crypto_major", "memecoin"} -- callers must extend config.py,
never fall through to a made-up value.
"""

from trader.backtest.config import FEE_TABLE, SLIPPAGE_PCT


def fee_for(asset_class: str, qty: float, price: float) -> float:
    """Commission fee for a single fill, per D-06/D-07's venue-static fee
    table.

    ``FEE_TABLE[asset_class]["kind"]`` selects the model:
    - "per_share": ``max(rate * qty, minimum)`` (IBKR US stocks).
    - "taker_pct": ``rate * qty * price`` (Kraken taker, crypto_major and
      memecoin alike -- memecoin's extra cost lives in slippage, not fees).

    Raises KeyError if asset_class is not in FEE_TABLE.
    """
    spec = FEE_TABLE[asset_class]
    if spec["kind"] == "per_share":
        return max(spec["rate"] * qty, spec["minimum"])
    if spec["kind"] == "taker_pct":
        return spec["rate"] * qty * price
    raise ValueError(f"Unknown fee kind {spec['kind']!r} for asset_class {asset_class!r}")


def slippage_pct_for(asset_class: str) -> float:
    """Fractional slippage multiplier for asset_class (D-08).

    SLIPPAGE_PCT stores percentage-unit values (a stock value of five
    hundredths of one percent, for example); this function converts each
    value to the fraction the other functions in this module actually
    need. Never reads the small-cap-runner constant documented in
    config.py's module docstring under "Slippage rationale" -- that
    constant is an unwired Phase 3 hook, not part of this per-asset_class
    lookup.

    Raises KeyError if asset_class is not in SLIPPAGE_PCT.
    """
    return SLIPPAGE_PCT[asset_class] / 100


def apply_slippage(price: float, side: str, asset_class: str) -> float:
    """Apply D-08 slippage to price, always against the trader.

    side="buy" fills at a higher price (worse for a buyer);
    side="sell" fills at a lower price (worse for a seller). Raises
    KeyError (via slippage_pct_for) if asset_class is unknown.
    """
    pct = slippage_pct_for(asset_class)
    if side == "buy":
        return price * (1 + pct)
    if side == "sell":
        return price * (1 - pct)
    raise ValueError(f"Unknown side {side!r}; expected 'buy' or 'sell'")


def entry_fill_price(bar_open: float, asset_class: str, side: str) -> float:
    """Entry fill price: always the bar's open (D-04), with slippage
    layered on top (D-08). Raises KeyError if asset_class is unknown.
    """
    return apply_slippage(bar_open, side, asset_class)


def worse_of_fill(trigger_price: float, bar_open: float, side: str) -> float:
    """Conservative gap-through fill price for a stop or take-profit exit
    on a long position (D-04).

    The stop and take-profit cases are deliberately asymmetric:

    - side="sell" (a stop exit closing a long): the WORSE of trigger_price
      and bar_open applies, i.e. the lower of the two. If the bar gapped
      down through the stop, the fill is priced at that worse open, never
      at the stale (better) stop price.
    - side="sell_at_tp" (a take-profit exit closing a long): the fill is
      ALWAYS capped at trigger_price, even if the bar gapped favourably
      past the target. A take-profit fill never improves past the target
      -- unlike a stop, which can only get worse on a gap, a TP can only
      ever get the trader the price they asked for, never more.

    Phase 2 is long-only (D-15); short-side exits ("buy"/"buy_at_tp") are
    out of scope and raise NotImplementedError rather than silently
    returning a wrong-signed result.
    """
    if side == "sell":
        return min(trigger_price, bar_open)
    if side == "sell_at_tp":
        return trigger_price
    if side in ("buy", "buy_at_tp"):
        raise NotImplementedError(
            f"worse_of_fill side={side!r} (short-side exit) is out of "
            "Phase 2's long-only scope (D-15)"
        )
    raise ValueError(f"Unknown side {side!r}")
