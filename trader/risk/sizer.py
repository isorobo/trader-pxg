"""RISK-02's position sizer: a pure function over (scored candidates,
current equity, open positions) implementing D-03's top-3 concurrent cap,
score x inverse-volatility weighting, 50% single-position cap, 10% memecoin
aggregate cap, and 10% cash reserve.

Deterministic order (04-RESEARCH.md Q3, Pitfall 3 -- caps are not
commutative when normalization steps are mixed in between them, so the
exact order below is load-bearing):

    1. select   -- top ``available_slots`` scored_candidates by score
                   descending, where ``available_slots = SIZER_TOP_N -
                   len(open_positions)``.
    2. weight   -- ``raw_i = score_i / volatility_i`` for the selected set.
    3. normalize -- raw weights scaled to sum to
                    ``available_weight = 1 - SIZER_CASH_RESERVE -
                    sum(open position weights)`` (the worked example in
                    04-RESEARCH.md Q3 is the ``open_positions=[]`` special
                    case, where ``available_weight == 0.90`` exactly).
    4. cap      -- ``capped_i = min(preliminary_i, SIZER_SINGLE_POSITION_CAP)``.
    5. re-cap   -- if the combined memecoin weight (new capped candidates
                   PLUS any existing open-position memecoin weight) exceeds
                   ``SIZER_MEMECOIN_CAP``, scale every NEW memecoin
                   candidate's weight down proportionally so the combined
                   total equals exactly the cap. Existing open memecoin
                   positions are never touched -- only new candidates absorb
                   the scale-down.
    6. cash absorbs the remainder -- capital freed by steps 4-5 is never
       redistributed to a surviving position. This is the single
       highest-impact design decision in 04-RESEARCH.md (Assumption A6,
       orchestrator-locked): a "redistribute to survivors" rule would
       silently increase another position's risk beyond what its own
       score/volatility justified, so caps only ever REMOVE risk here. Cash
       ends up >= SIZER_CASH_RESERVE whenever a cap binds, never exactly
       the reserve in that case.

``equity`` is accepted per D-03's function signature (parity with the
gate/breaker pure-function shapes) but this module returns fractional
weights of equity, not dollar notionals -- ``equity`` is not itself an
input to the weight computation and is not used inside this function; a
caller multiplies the returned weights by ``equity`` to get dollar sizes.
"""

from __future__ import annotations

import pandas as pd

from trader.risk import config as risk_config


def compute_volatility(
    bars: list[dict], window: int = risk_config.SIZER_VOLATILITY_WINDOW_DAYS
) -> float:
    """Sample standard deviation (ddof=1) of the trailing ``window``-day
    daily close-to-close returns, matching ``trader.backtest.metrics``'s
    ``ddof=1`` (sample stdev) convention rather than population stdev.

    ``bars`` is a ``list[dict]`` ascending by ``ts``, the same shape
    ``trader.data.db.read_bars_cache`` returns.
    """
    closes = pd.Series([bar["close"] for bar in bars])
    return closes.pct_change().tail(window).std(ddof=1)


def size_positions(
    scored_candidates: list[dict],
    equity: float,
    open_positions: list[dict],
    config=risk_config,
) -> dict:
    """Pure position sizer (D-03). See module docstring for the exact
    deterministic select -> weight -> normalize -> cap -> re-cap ->
    cash-absorbs-remainder order.

    ``scored_candidates``: each entry requires ``symbol, venue,
    asset_class, score, volatility`` (``volatility`` > 0).
    ``open_positions``: each entry requires ``symbol, venue, asset_class,
    weight`` (fraction of equity already committed); these are never
    re-sized -- only the remaining budget is allocated among new
    candidates.

    Returns ``{"positions": [{"symbol", "venue", "asset_class", "weight"},
    ...], "cash_weight": float}`` where ``sum(position weights) +
    sum(open_positions weights) + cash_weight == 1.0`` exactly.
    """
    available_slots = max(0, config.SIZER_TOP_N - len(open_positions))
    selected = sorted(
        scored_candidates, key=lambda c: c["score"], reverse=True
    )[:available_slots]

    raw_weights = [c["score"] / c["volatility"] for c in selected]
    raw_sum = sum(raw_weights)

    open_weight_sum = sum(op["weight"] for op in open_positions)
    available_weight = max(0.0, 1.0 - config.SIZER_CASH_RESERVE - open_weight_sum)

    if raw_sum > 0:
        preliminary = [(w / raw_sum) * available_weight for w in raw_weights]
    else:
        preliminary = [0.0 for _ in raw_weights]

    capped = [min(w, config.SIZER_SINGLE_POSITION_CAP) for w in preliminary]

    open_memecoin_weight = sum(
        op["weight"] for op in open_positions if op["asset_class"] == "memecoin"
    )
    memecoin_indices = [
        i for i, c in enumerate(selected) if c["asset_class"] == "memecoin"
    ]
    new_memecoin_weight = sum(capped[i] for i in memecoin_indices)
    combined_memecoin_weight = open_memecoin_weight + new_memecoin_weight

    final = list(capped)
    if combined_memecoin_weight > config.SIZER_MEMECOIN_CAP and new_memecoin_weight > 0:
        allowed_new_memecoin = max(
            0.0, config.SIZER_MEMECOIN_CAP - open_memecoin_weight
        )
        scale = allowed_new_memecoin / new_memecoin_weight
        for i in memecoin_indices:
            final[i] = capped[i] * scale

    positions = [
        {
            "symbol": c["symbol"],
            "venue": c["venue"],
            "asset_class": c["asset_class"],
            "weight": final[i],
        }
        for i, c in enumerate(selected)
    ]

    cash_weight = 1.0 - open_weight_sum - sum(final)

    return {"positions": positions, "cash_weight": cash_weight}
