"""The live book's family -> entry-signal registry (owner-approved
multi-signal book, 2026-07-30).

Each live strategy FAMILY (strategy_id) scans its own frozen entry signal;
the registry row's entry_variant picks the variant within that family's
frozen variant dict. Every referenced module is an existing frozen surface
(momentum_v2 under FROZEN_HASH_V2; donchian/rsi2 under their own gates) --
this module only ROUTES, it defines no signal logic and no new parameters.

Unknown family or variant raises KeyError loudly: a registry row that
cannot be routed must fail the run visibly, never silently trade someone
else's signal (the system never lies to itself).
"""

from __future__ import annotations

from trader.backtest.strategies import donchian, momentum_v2, rsi2

# family -> (variants dict, make_pick_entries factory). Families absent
# here cannot go live -- register_entrant refuses them up front.
FAMILY_SIGNALS: dict[str, tuple[dict, object]] = {
    "momentum_stock": (momentum_v2.MOMENTUM_VARIANTS, momentum_v2.make_pick_entries),
    "donchian_stock": (donchian.DONCHIAN_VARIANTS, donchian.make_pick_entries),
    "rsi2_stock": (rsi2.RSI2_VARIANTS, rsi2.make_pick_entries),
}


def pick_entries_for(strategy_id: str, entry_variant: str):
    """Return the frozen `pick_entries(iterator, date, open_positions, rng)`
    closure for one live family/variant pair. KeyError on anything
    unroutable -- loud, never silent."""
    variants, make_pick_entries = FAMILY_SIGNALS[strategy_id]
    return make_pick_entries(variants[entry_variant])


def is_routable(strategy_id: str, entry_variant: str) -> bool:
    """True when this family/variant pair can be routed to a frozen signal."""
    family = FAMILY_SIGNALS.get(strategy_id)
    return family is not None and entry_variant in family[0]
