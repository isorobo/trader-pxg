"""Wires the live entry pipeline (05-06-PLAN.md, PAPER-01): on each trading
day shortly after US open, scan the frozen 18-symbol stock universe with the
momentum_stock/loose signal (D-01/D-02/D-14), run Phase 4's risk gate and
sizer completely unmodified (D-08 -- no bypass path exists), round the
sizer's dollar output down to whole shares (Pitfall 2), and assign each new
position one of the five live exit-profile configs via a hash keyed on
SYMBOL ALONE (RESIDUAL BLOCKER 1 -- no date component; see
``assign_exit_profile``'s own docstring for the full rationale).

Every invocation first runs an UNSCOPED STEP 0 heal pass over every
unresolved local order in the whole table (``ledger.get_all_unresolved_orders``,
no strategy_id/symbol filter) BEFORE candidate scanning, BEFORE the
trading-day check, and BEFORE the halt gate (RESIDUAL BLOCKER 1) -- a
crash-orphaned order is healed even when its own symbol never fires a
fresh signal again. The narrower per-candidate heal check (STEP 1) is kept
as a second, defensive layer for whatever fires fresh today. Only after
STEP 0, STEP 1 (per-candidate heal), STEP 2 (still-in-flight check), and
STEP 3 (the combined Phase-4-breaker + reconciliation halt gate,
``reconcile.is_entry_halted``) all resolve does STEP 4 persist a brand-new
``pending_submit`` order BEFORE STEP 5 ever calls the broker (BLOCKER 1).

Standing rule 6 (real money is Phase 9): this module only ever submits
through ``trader.paper.broker_ibkr.IBKRBrokerAdapter``, which itself refuses
to connect anywhere but the paper port.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta

import pandas as pd

from trader.backtest.iterator import PointInTimeIterator
from trader.backtest.strategies.momentum_v2 import (
    MOMENTUM_VARIANTS,
    _rsi_wilder,
    make_pick_entries,
)
from trader.backtest.universe import STOCK_UNIVERSE
from trader.data.api import get_daily_bars
from trader.paper import config, ledger
from trader.risk import sizer

_ASSET_CLASS_STOCK = "stock"
_ROUTING_VENUE = "smart"  # IBKR's SMART routing venue string, not a DB venue value.


# ---------------------------------------------------------------------------
# Task 1: candidate scan, score, gate, day-stable symbol-only profile assign
# ---------------------------------------------------------------------------


def _history_to_bar_dicts(history) -> list[dict]:
    """Convert a ``PointInTimeIterator.history(symbol)`` numpy array
    (columns open/high/low/close/volume, point-in-time bounded) into the
    ``list[dict]`` shape ``trader.risk.sizer.compute_volatility`` requires.
    No ``ts`` field -- ``compute_volatility`` only ever reads ``close``."""
    return [
        {
            "open": float(row[0]),
            "high": float(row[1]),
            "low": float(row[2]),
            "close": float(row[3]),
            "volume": float(row[4]),
        }
        for row in history
    ]


def scan_candidates(conn, as_of_date: date) -> list[dict]:
    """Scan the frozen 18-symbol stock universe for a fresh loose-momentum
    entry signal (D-01/D-02/D-14), using only bars up to (not including)
    ``as_of_date`` (D-05: yesterday's close, since today's own close is not
    yet known shortly after today's open).

    Returns one candidate dict per fired symbol: ``{"symbol", "venue",
    "score", "volatility"}``. A symbol already in ``open_positions`` (any
    strategy_id) never re-fires as a new candidate this run --
    ``make_pick_entries``'s own ``pick_entries`` closure enforces this via
    its ``open_positions`` argument.
    """
    yesterday = as_of_date - timedelta(days=1)
    bars_by_symbol = {
        symbol: get_daily_bars(
            symbol, end=str(yesterday), asset_class=_ASSET_CLASS_STOCK, conn=conn
        )
        for symbol in STOCK_UNIVERSE
    }
    iterator = PointInTimeIterator(bars_by_symbol)
    iterator.advance_to(yesterday)

    open_symbols = {p["symbol"] for p in ledger.get_open_positions(conn)}
    pick_entries = make_pick_entries(MOMENTUM_VARIANTS["loose"])
    # rng is seeded deterministically -- the loose variant's own signal
    # logic never actually consumes rng, but the shared 4-arg
    # pick_entries(iterator, date, open_positions, rng) contract requires
    # passing one.
    fired = pick_entries(iterator, pd.Timestamp(yesterday), open_symbols, random.Random(0))

    candidates: list[dict] = []
    for symbol in fired:
        history = iterator.history(symbol)
        closes = history[:, 3]
        rsi = _rsi_wilder(closes)
        volatility = sizer.compute_volatility(_history_to_bar_dicts(history))
        candidates.append(
            {
                "symbol": symbol,
                "venue": _ROUTING_VENUE,
                "score": rsi,
                "volatility": volatility,
            }
        )
    return candidates


def assign_exit_profile(symbol: str, live_profile_names: list[str]) -> str:
    """Deterministic, SYMBOL-ONLY exit-profile assignment (REVISED,
    RESIDUAL BLOCKER 1 -- no ``as_of_date`` parameter at all).

    Heal correctness requires day-stable identity -- a crash-orphaned order
    is looked up on a LATER day by (strategy_id, symbol, side); if
    strategy_id were re-derived from a date-hash, the day-2 recomputation
    would pick a different one of the five live profiles 4 times out of 5,
    and get_unresolved_orders (filtered by strategy_id) would find nothing
    for the actual order that was placed. Hashing on symbol alone means the
    SAME strategy_id is always assigned to a given symbol, on any day, for
    as long as that profile stays live -- this is what the STEP 0 heal pass
    (and the narrower per-candidate check) depend on to ever find a match.
    Profile spread across the sizer's typically-small number of concurrent
    candidates is still preserved, because the hash spreads across the
    18-symbol STOCK_UNIVERSE, not across a single symbol repeated on
    different days -- there was never a meaningful "spread over time for
    one symbol" property to preserve, only "spread over symbols", and that
    survives removing the date term entirely.
    """
    names = sorted(live_profile_names)
    index = int(hashlib.sha256(symbol.encode()).hexdigest(), 16) % len(names)
    return names[index]


def _live_profile_names(conn) -> list[str]:
    """The profile_names of every live (non-retired) strategy_config.

    Raises RuntimeError, not a silent empty return, when all five configs
    are retired -- a T-05-11-shaped visibility gap otherwise (this process
    would silently enter zero positions forever without ever surfacing
    why).
    """
    names = [
        cfg.profile_name
        for cfg in config.LIVE_STRATEGY_CONFIGS
        if not ledger.is_strategy_retired(conn, cfg.profile_name)
    ]
    if not names:
        raise RuntimeError(
            "all five live strategy configs are retired -- nothing left to trade"
        )
    return names
