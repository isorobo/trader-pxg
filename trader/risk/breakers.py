"""RISK-03's circuit breakers: a pure evaluation function plus a thin,
parameterized, append-only persistence layer (D-04/D-05, 04-RESEARCH.md Q4).

``evaluate_breakers`` is pure -- it performs zero DB/file I/O. It never
imports ``sqlite3`` or ``trader.data.db``. Its safety depends entirely on the
caller: ``equity_curve`` must already be truncated to "as of now" (one point
per UTC calendar day, matching
``trader.backtest.metrics._build_daily_equity_curve``'s daily granularity).
Passing a curve that includes any future point lets the high-water mark
"see" a future recovery and never trip -- a lookahead bug structurally
identical to the point-in-time bar iterator's own discipline
(04-RESEARCH.md Pitfall 2). The high-water mark is therefore never persisted
as its own stored value; it is re-derived as ``max(equity_curve)`` on every
call, which IS the incremental running maximum precisely because the caller
only ever passes points up to "now."

Persistence is an append-only event log (``breaker_events``,
``migrations/0004_risk_breakers.sql``) plus a derived current-state view
(``breaker_state_current``) -- standing rule 4 ("if the system and any
external state ever disagree, halt") is honoured by always re-deriving
state from the event log rather than trusting a cached column.
``record_breaker_transitions`` only ever writes a transition it can justify
from a fresh ``evaluate_breakers()`` call -- it never silently drops a real
transition.

The drawdown breaker's halt is the phase's one deliberately human-gated
control surface: no code path in this module other than the dedicated clear
function documented below ever appends an event that clears drawdown's
tripped state. The ``python -m trader.risk.clear_breaker --reason "<why>"``
CLI (``trader/risk/clear_breaker.py``) is the ONLY invoker of that clear
function in the entire codebase -- there is no auto-restart / auto-clear
path anywhere (security requirement, T-04-10).
"""

from __future__ import annotations

from trader.risk import config as risk_config

_BREAKER_TYPES = ("daily_loss", "drawdown", "consecutive_loss")


def evaluate_breakers(
    equity_curve: list[float],
    trade_pnls: list[float],
    config=risk_config,
) -> dict:
    """Pure, incremental evaluation of all three breakers (D-04).

    ``equity_curve`` must already be truncated by the caller to "as of now"
    -- see the module docstring's lookahead warning. ``trade_pnls`` is the
    chronological list of closed-trade pnls up to and including "now."

    Returns a dict:
        {"daily_loss_tripped": bool, "daily_loss_value": float | None,
         "drawdown_tripped": bool, "drawdown_value": float | None,
         "consecutive_loss_tripped": bool, "consecutive_loss_count": int}
    """
    daily_loss_value = None
    daily_loss_tripped = False
    if len(equity_curve) >= 2:
        prior, latest = equity_curve[-2], equity_curve[-1]
        daily_loss_value = (latest - prior) / prior
        daily_loss_tripped = daily_loss_value <= config.BREAKER_DAILY_LOSS_PCT

    drawdown_value = None
    drawdown_tripped = False
    if equity_curve:
        hwm = max(equity_curve)  # the incremental HWM -- safe only because
        # the caller never passes future points (see module docstring).
        drawdown_value = (equity_curve[-1] - hwm) / hwm
        drawdown_tripped = drawdown_value <= config.BREAKER_DRAWDOWN_PCT

    consecutive_loss_count = 0
    for pnl in reversed(trade_pnls):
        if pnl < 0:
            consecutive_loss_count += 1
        else:
            break
    consecutive_loss_tripped = (
        consecutive_loss_count >= config.BREAKER_CONSECUTIVE_LOSSES
    )

    return {
        "daily_loss_tripped": daily_loss_tripped,
        "daily_loss_value": daily_loss_value,
        "drawdown_tripped": drawdown_tripped,
        "drawdown_value": drawdown_value,
        "consecutive_loss_tripped": consecutive_loss_tripped,
        "consecutive_loss_count": consecutive_loss_count,
    }
