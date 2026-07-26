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


def _windowed_returns(bars: list[dict], window_days: int) -> pd.Series:
    """Simple daily returns, indexed by calendar date (ts), restricted to
    the trailing ``window_days`` calendar days of this bars list's own
    history (04-RESEARCH.md Q2: 60 calendar days of daily-return
    observations, not 60 bars).
    """
    ts = pd.to_datetime([bar["ts"] for bar in bars])
    closes = pd.Series([bar["close"] for bar in bars], index=ts).sort_index()
    if len(closes) == 0:
        return pd.Series(dtype=float)
    cutoff = closes.index.max() - pd.Timedelta(days=window_days - 1)
    windowed = closes[closes.index >= cutoff]
    return windowed.pct_change().dropna()


def _pairwise_correlation(
    bars_a: list[dict],
    bars_b: list[dict],
    config,
) -> float | None:
    """Pearson correlation of two candidates' daily returns, inner-joined
    on calendar date (never a positional index -- 04-RESEARCH.md Pitfall
    1). Returns None if the joined overlap is below
    ``config.CORRELATION_MIN_OVERLAP`` (indeterminate, not a rejection).
    """
    returns_a = _windowed_returns(bars_a, config.CORRELATION_WINDOW_DAYS)
    returns_b = _windowed_returns(bars_b, config.CORRELATION_WINDOW_DAYS)
    aligned = pd.concat([returns_a, returns_b], axis=1, join="inner")
    if len(aligned) < config.CORRELATION_MIN_OVERLAP:
        return None
    return aligned.iloc[:, 0].corr(aligned.iloc[:, 1])


def _apply_correlation_check(
    accepted: list[dict],
    market_data: dict,
    config,
) -> tuple[list[dict], list[dict]]:
    """Greedy sequential elimination over the accepted set's pairwise
    correlations (04-RESEARCH.md Q2): sort pairs exceeding
    ``config.CORRELATION_THRESHOLD`` by correlation magnitude descending,
    walk once, reject the lower-scored member of each still-live pair.

    Returns ``(survivors, correlation_rejections)``.
    """
    pairs = []
    for i in range(len(accepted)):
        for j in range(i + 1, len(accepted)):
            a, b = accepted[i], accepted[j]
            key_a = (a["symbol"], a["venue"])
            key_b = (b["symbol"], b["venue"])
            corr = _pairwise_correlation(
                market_data[key_a]["bars"], market_data[key_b]["bars"], config
            )
            if corr is not None and abs(corr) > config.CORRELATION_THRESHOLD:
                pairs.append((abs(corr), i, j))

    pairs.sort(key=lambda p: p[0], reverse=True)

    survivor_indices = set(range(len(accepted)))
    rejected: list[dict] = []
    for _corr, i, j in pairs:
        if i not in survivor_indices or j not in survivor_indices:
            continue
        loser = i if accepted[i]["score"] < accepted[j]["score"] else j
        survivor_indices.discard(loser)
        rejected.append({**accepted[loser], "reason_code": REJECT_CORRELATION})

    survivors = [accepted[i] for i in range(len(accepted)) if i in survivor_indices]
    return survivors, rejected


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

    accepted, correlation_rejections = _apply_correlation_check(
        accepted, market_data, config
    )
    rejected.extend(correlation_rejections)

    return accepted, rejected
