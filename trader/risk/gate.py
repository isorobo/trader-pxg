"""RISK-01's risk gate: a pure function that deletes unsafe candidates.

``apply_risk_gate`` never touches the network or a live DB connection -- it
is a pure function over a caller-supplied ``candidates`` list plus a
prebuilt ``market_data`` dict. All thresholds live in
``trader.risk.config`` (frozen, pre-registered defaults per
04-RESEARCH.md); this module contains zero inline numeric thresholds.

Candidate-dict contract (input, per element of ``candidates``):
    ``list[dict]``, each requiring:
        - ``symbol: str``
        - ``venue: str``
        - ``score: float`` -- Phase 4's own required field (see
          ``trader/risk/config.py``'s module docstring). Populated by
          whatever upstream caller invokes the gate; decoupled from Phase
          3's ``pick_entries`` output per D-06/04-RESEARCH.md Pitfall 4/
          Assumption A9. This module never imports anything under
          ``trader.backtest.strategies``.

market_data contract (input):
    ``dict`` keyed by ``(symbol, venue)`` tuple. Each value is a dict:
        - ``"bars": list[dict]`` -- ``ts``/``open``/``high``/``low``/
          ``close``/``volume`` per bar, ``ts`` ascending ISO date strings.
          This is the exact shape ``trader.data.db.read_bars_cache``
          returns; a caller may pass that function's output straight
          through.
        - ``"asset_class": str`` -- already override-resolved by the
          caller (``"stock"``, ``"crypto_major"``, or ``"memecoin"``).
        - ``"spread_pct": float`` -- a static per-candidate spread
          estimate, in the same percentage units as
          ``trader.backtest.config.SLIPPAGE_PCT`` (e.g. ``0.05`` means
          0.05%, not 5%).

Output contract:
    ``apply_risk_gate(...) -> (accepted, rejected)``.
    - Each accepted candidate dict is spread with ``asset_class`` and
      ``exit_profile_tag`` (both equal to the market_data entry's
      ``asset_class``). ``exit_profile_tag`` is a CATEGORY PLACEHOLDER
      here -- it is the raw asset-class string, not a Phase 2
      ``EXIT_PROFILE`` dataclass instance. Phase 5 is responsible for
      resolving this placeholder tag into an actual ``EXIT_PROFILE``
      selection; Phase 4 only tags candidates with the category so that
      resolution has something to key off later.
    - Each rejected candidate dict is spread with exactly one
      ``reason_code``, one of ``REJECT_LIQUIDITY``, ``REJECT_LISTING_AGE``,
      ``REJECT_SPREAD``, ``REJECT_CORRELATION``.
"""

from __future__ import annotations

import pandas as pd

from trader.risk import config as risk_config

REJECT_LIQUIDITY = "REJECT_LIQUIDITY"
REJECT_LISTING_AGE = "REJECT_LISTING_AGE"
REJECT_SPREAD = "REJECT_SPREAD"
REJECT_CORRELATION = "REJECT_CORRELATION"

# Asset-class -> liquidity floor constant name, keyed off market_data's
# already-resolved asset_class string.
_LIQUIDITY_FLOOR_ATTR = {
    "stock": "MIN_DOLLAR_VOLUME_STOCK",
    "crypto_major": "MIN_QUOTE_VOLUME_CRYPTO_MAJOR",
    "memecoin": "MIN_QUOTE_VOLUME_MEMECOIN",
}


def _liquidity_window_days(asset_class: str, config) -> int:
    """Trailing window length (days) for the liquidity median, per class."""
    if asset_class == "stock":
        return config.LIQUIDITY_WINDOW_STOCK_DAYS
    return config.LIQUIDITY_WINDOW_CRYPTO_DAYS


def _trailing_median_volume(bars: list[dict], asset_class: str, config) -> float:
    """Median dollar/quote volume (close * volume per bar) over the
    asset class's trailing window (04-RESEARCH.md Q1: median, not mean, to
    avoid a single outlier day qualifying an otherwise illiquid asset).
    """
    window = _liquidity_window_days(asset_class, config)
    closes = pd.Series([bar["close"] for bar in bars])
    volumes = pd.Series([bar["volume"] for bar in bars])
    dollar_volume = closes * volumes
    return dollar_volume.tail(window).median()


def _first_failing_check(entry: dict, config) -> str | None:
    """Liquidity -> listing_age -> spread, in that fixed order. Returns the
    first matching reason code, or None if all three checks pass.
    """
    bars = entry["bars"]
    asset_class = entry["asset_class"]

    floor_attr = _LIQUIDITY_FLOOR_ATTR[asset_class]
    floor = getattr(config, floor_attr)
    median_volume = _trailing_median_volume(bars, asset_class, config)
    if median_volume < floor:
        return REJECT_LIQUIDITY

    if len(bars) < config.MIN_LISTING_AGE_DAYS:
        return REJECT_LISTING_AGE

    if entry["spread_pct"] > config.MAX_SPREAD_PCT[asset_class]:
        return REJECT_SPREAD

    return None


def apply_risk_gate(
    candidates: list[dict],
    market_data: dict,
    config=risk_config,
) -> tuple[list[dict], list[dict]]:
    """Pure risk-gate function (D-01): liquidity/listing-age/spread checks
    per candidate, then a correlation pass across the survivors.

    Returns ``(accepted, rejected)``.
    """
    accepted: list[dict] = []
    rejected: list[dict] = []

    for candidate in candidates:
        key = (candidate["symbol"], candidate["venue"])
        entry = market_data[key]
        reason = _first_failing_check(entry, config)
        if reason is not None:
            rejected.append({**candidate, "reason_code": reason})
        else:
            accepted.append(
                {
                    **candidate,
                    "asset_class": entry["asset_class"],
                    "exit_profile_tag": entry["asset_class"],
                }
            )

    return accepted, rejected
