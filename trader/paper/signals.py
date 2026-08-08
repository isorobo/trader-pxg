"""The live book's family -> entry-signal registry (owner-approved
multi-signal book, 2026-07-30; crypto leg approved same day).

A live family's strategy_id is "{base}_{bucket}" (e.g. "momentum_stock",
"donchian_stock", "macross_crypto_major_legacy_meme"). The BASE picks the
frozen signal module; the registry row's entry_variant picks the variant
within it. Every referenced module is an existing frozen surface -- this
module only ROUTES, it defines no signal logic and no new parameters.

Pre-registered exclusion: rsi2 routes for the stock bucket ONLY --
Strategys/11's own spec: "Avoid crypto and commodities -- the research
doesn't transfer cleanly". An rsi2 crypto family is unroutable by design.

Unknown base or variant raises KeyError loudly: a registry row that cannot
be routed must fail the run visibly, never silently trade someone else's
signal (the system never lies to itself).
"""

from __future__ import annotations

from trader.backtest.strategies import (
    donchian,
    hourly_reversion,
    hourly_squeeze,
    macross,
    momentum_v2,
    rsi2,
)

# base -> (variants dict, make_pick_entries factory).
_BASE_SIGNALS: dict[str, tuple[dict, object]] = {
    "momentum": (momentum_v2.MOMENTUM_VARIANTS, momentum_v2.make_pick_entries),
    "donchian": (donchian.DONCHIAN_VARIANTS, donchian.make_pick_entries),
    "rsi2": (rsi2.RSI2_VARIANTS, rsi2.make_pick_entries),
    "macross": (macross.MACROSS_VARIANTS, macross.make_pick_entries),
    "hreversion": (
        hourly_reversion.HOURLY_REVERSION_VARIANTS,
        hourly_reversion.make_pick_entries,
    ),
    "hsqueeze": (
        hourly_squeeze.HOURLY_SQUEEZE_VARIANTS,
        hourly_squeeze.make_pick_entries,
    ),
}

# Bases whose signals are defined on 1h bars -- the crypto pipeline scans
# them against the hourly cache, once per completed hour.
_HOURLY_BASES = ("hreversion", "hsqueeze")


def timeframe_for(strategy_id: str) -> str:
    """'1h' for hourly-bar families, '1d' otherwise."""
    return "1h" if _base_of(strategy_id) in _HOURLY_BASES else "1d"

# Bases whose published research is bucket-restricted (pre-registered).
_STOCK_ONLY_BASES = ("rsi2",)


def _base_of(strategy_id: str) -> str:
    return strategy_id.split("_", 1)[0]


def pick_entries_for(strategy_id: str, entry_variant: str):
    """Return the frozen `pick_entries(iterator, date, open_positions, rng)`
    closure for one live family/variant pair. KeyError on anything
    unroutable -- loud, never silent."""
    base = _base_of(strategy_id)
    if base in _STOCK_ONLY_BASES and strategy_id != f"{base}_stock":
        raise KeyError(
            f"{strategy_id!r} is unroutable: {base} is pre-registered as "
            "stock-only (its own spec excludes other buckets)"
        )
    variants, make_pick_entries = _BASE_SIGNALS[base]
    return make_pick_entries(variants[entry_variant])


def is_routable(strategy_id: str, entry_variant: str) -> bool:
    """True when this family/variant pair can be routed to a frozen signal."""
    base = _base_of(strategy_id)
    if base in _STOCK_ONLY_BASES and strategy_id != f"{base}_stock":
        return False
    family = _BASE_SIGNALS.get(base)
    return family is not None and entry_variant in family[0]
