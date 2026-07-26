"""EXIT_PROFILES evaluation in D-10's exact locked order (BACK-04).

``evaluate_exit`` is the single place a position's exit conditions are
checked, once per open position per bar, in this fixed order (D-10):

    1. eod_flat
    2. stop
    3. trailing stop
    4. scale-out / take-profit
    5. time stop

Every rule below is proven by a distinctly named test in
``tests/test_backtest_exits.py`` (T-02-09, T-02-10, T-02-11):

- **Entry-bar checking (Pitfall 2):** ``evaluate_exit`` must be called
  against the entry bar itself (``days_held=0``), using that bar's own
  high/low. There is no "grace period" -- a position can be stopped out
  on the day it was opened.
- **Stop-wins-tie (D-05):** if a bar's low breaches the stop AND its high
  breaches the take-profit, the stop is checked first in D-10's order and
  always wins.
- **Gap-through pricing (D-04):** this module reuses
  ``trader.backtest.fills.worse_of_fill`` for every stop/trailing/TP/
  scale-out raw price, rather than re-deriving the gap-through arithmetic
  inline -- there is exactly one place D-04's worse-case rule lives.
  ``side="sell"`` is used for stop and trailing exits (the fill can only
  get WORSE on an adverse gap, never better); ``side="sell_at_tp"`` is
  used for take-profit and scale-out exits (the fill is always capped at
  the trigger price, even on a favourable gap -- a profit-taking exit
  never improves past its target).
- **Trailing watermark, no lookahead (Pitfall 3):** the trailing level for
  THIS bar's check is derived only from the ``watermark`` parameter passed
  in (the watermark as of the END of the previous bar) -- never from this
  bar's own high. The watermark is only ever updated to include this bar's
  own close AFTER the check, for use starting the NEXT bar.
- **Daily-bars eod_flat/time_stop convention (Pitfall 5, A4):** on this
  daily-only iterator there is no intraday "end of day" event distinct
  from the bar itself, so both ``eod_flat`` and a fully-elapsed
  ``max_hold_days`` degrade to "exit at this bar's close" rather than
  carrying the position into the next bar's open.

Watermark contract (module-level convention): ``evaluate_exit``'s return
type is exactly ``ExitResult | None`` per this plan's interface, so the
``None`` branch cannot smuggle a second return value through. Every
``ExitResult`` this module returns carries ``new_watermark`` -- the value
the caller must pass back in on the NEXT bar's ``evaluate_exit`` call for
this position. When ``evaluate_exit`` returns ``None`` (nothing fired this
bar), the caller must call the sibling function ``next_watermark`` to
obtain that same next-bar watermark; it applies the identical
prior-close-only update rule, so a position with no ``trailing_pct`` set,
or one whose trailing level was not breached, still has its watermark
tracked correctly bar over bar. ``next_watermark`` and the trailing branch
below share one private helper (``_updated_watermark``) so there is
exactly one place the update rule is implemented.

Scale-out and ``tp_pct`` are mutually exclusive per-profile in practice
(D-09's field list does not forbid combining them, but Phase 2's concrete
profiles never do); both are checked here for completeness, with
scale-out's ascending-``gain_pct`` tranches checked first.
"""

from dataclasses import dataclass, field

from trader.backtest.config import EXIT_PROFILE
from trader.backtest.fills import worse_of_fill


@dataclass
class PositionState:
    """Mutable per-position state carried across bars.

    ``stop_price`` and ``tp_price`` are computed once, from the profile
    and entry price, at position-open time (standing rule 2: exit profiles
    lock at entry -- no mid-trade loosening) -- never recomputed
    afterwards. Use the ``open`` classmethod rather than constructing this
    directly, so that invariant cannot be bypassed by accident.
    """

    entry_price: float
    stop_price: float | None
    tp_price: float | None
    scale_out_triggered: set = field(default_factory=set)
    qty_remaining: float = 1.0

    @classmethod
    def open(
        cls,
        profile: EXIT_PROFILE,
        entry_price: float,
        qty_remaining: float = 1.0,
    ) -> "PositionState":
        """Open a new position under ``profile``, computing stop/TP prices
        once from ``entry_price`` (never recomputed for the life of the
        position).
        """
        stop_price = (
            entry_price * (1 + profile.stop_pct)
            if profile.stop_pct is not None
            else None
        )
        tp_price = (
            entry_price * (1 + profile.tp_pct) if profile.tp_pct is not None else None
        )
        return cls(
            entry_price=entry_price,
            stop_price=stop_price,
            tp_price=tp_price,
            qty_remaining=qty_remaining,
        )


@dataclass(frozen=True)
class ExitResult:
    """The outcome of one ``evaluate_exit`` call that fired.

    ``reason`` matches migrations/0003_backtest.sql's ``exit_reason`` CHECK
    constraint exactly: one of 'stop', 'take_profit', 'trailing_stop',
    'scale_out', 'time_stop', 'eod_flat'.
    """

    reason: str
    raw_price: float
    exit_fraction: float
    new_watermark: float | None


def _updated_watermark(
    position: PositionState, watermark: float | None, bar_close: float
) -> float:
    """Prior-close-only watermark update rule (Pitfall 3): the new
    watermark is the higher of the incoming watermark (or, if this
    position has never had one yet, its entry price) and THIS bar's
    close -- never this bar's own high.
    """
    base = watermark if watermark is not None else position.entry_price
    return max(base, bar_close)


def next_watermark(
    position: PositionState, watermark: float | None, bar: dict
) -> float:
    """Compute the watermark to pass into the NEXT bar's ``evaluate_exit``
    call, for use whenever this bar's call returned ``None`` (see the
    module docstring's "Watermark contract").
    """
    return _updated_watermark(position, watermark, bar["close"])


def evaluate_exit(
    profile: EXIT_PROFILE,
    position: PositionState,
    bar: dict,
    days_held: int,
    watermark: float | None,
) -> ExitResult | None:
    """Evaluate all of ``profile``'s exit conditions against ``bar`` in
    D-10's exact locked order. Returns the first condition that fires, or
    ``None`` if nothing fires this bar. See the module docstring for the
    watermark contract on the ``None`` path.
    """
    # 1. eod_flat -- degrades to "exit at this bar's close" on daily bars
    # (Pitfall 5, A4). Checked first per D-10; wins over every other
    # condition even when they are independently true on the same bar.
    if profile.eod_flat:
        return ExitResult("eod_flat", bar["close"], 1.0, watermark)

    # 2. stop -- entry-bar checked like any other bar (Pitfall 2); wins
    # the tie against take-profit/scale-out because it is checked first
    # in this order (D-05).
    if profile.stop_pct is not None and bar["low"] <= position.stop_price:
        raw = worse_of_fill(position.stop_price, bar["open"], side="sell")
        return ExitResult("stop", raw, 1.0, watermark)

    # 3. trailing stop -- the level for THIS bar's check comes only from
    # the incoming watermark parameter (the watermark as of the END of the
    # previous bar), never from this bar's own high (Pitfall 3). The
    # watermark is updated to include this bar's close only AFTER the
    # check, regardless of whether trailing_pct is even configured, so the
    # caller always has a correct value for next bar.
    new_watermark = _updated_watermark(position, watermark, bar["close"])
    if profile.trailing_pct is not None and watermark is not None:
        trailing_level = watermark * (1 - profile.trailing_pct)
        if bar["low"] <= trailing_level:
            raw = worse_of_fill(trailing_level, bar["open"], side="sell")
            return ExitResult("trailing_stop", raw, 1.0, new_watermark)

    # 4. scale-out / take-profit -- ascending gain_pct order, skipping
    # tranches already fired for this position.
    for gain_pct, fraction in profile.scale_out:
        if gain_pct in position.scale_out_triggered:
            continue
        target = position.entry_price * (1 + gain_pct)
        if bar["high"] >= target:
            raw = worse_of_fill(target, bar["open"], side="sell_at_tp")
            position.scale_out_triggered.add(gain_pct)
            return ExitResult("scale_out", raw, fraction, new_watermark)

    if profile.tp_pct is not None and bar["high"] >= position.tp_price:
        raw = worse_of_fill(position.tp_price, bar["open"], side="sell_at_tp")
        return ExitResult("take_profit", raw, 1.0, new_watermark)

    # 5. time stop -- fully-elapsed max_hold_days degrades to "exit at
    # this bar's close", same daily-bars convention as eod_flat.
    if profile.max_hold_days is not None and days_held >= profile.max_hold_days:
        return ExitResult("time_stop", bar["close"], 1.0, new_watermark)

    return None
