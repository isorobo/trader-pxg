"""Backtest orchestration loop -- wires the point-in-time iterator (plan
02-02), fills (02-04), exits (02-05), and ledger (02-06) into the single
entry point every strategy_fn calls uniformly: run_backtest (BACK-01,
BACK-04, BACK-05).

Each of those modules already proves its own honesty rule in isolation
(no lookahead, conservative fills, entry-bar checking, reproducible
writes); this module is pure integration, and every honesty rule those
plans proved must still hold true once wired together -- that is exactly
what 02-08-PLAN.md's threat model (T-02-16/17/18) and this module's sibling
tests/test_backtest_runner.py exist to prove.

Signal-to-fill lag (D-04, T-02-16): strategy_fn is called with `date` and
only ever reads iterator.history() -- point-in-time by construction. A
symbol it returns is NEVER opened on that same `date`; it is scheduled into
`pending_entries` and opened at the first LATER calendar date the symbol
actually has a bar (never a blind "next calendar index", since a symbol can
be missing bars on dates other symbols trade). The fill price is always
that later bar's OPEN, priced through fills.entry_fill_price.

Entry-bar exit checking (Pitfall 2, T-02-17): the moment a pending entry is
opened, evaluate_exit is called against that SAME fill bar with
days_held=0, in the SAME loop pass -- never deferred to the next date's
iteration. A position that gaps through its stop on the bar it was filled
on exits on that bar, not a later one.

Reproducibility (D-12, T-02-18): the only randomness is the caller-owned
`random.Random(seed)` instance handed to strategy_fn; iteration order over
open_positions/pending_entries never affects the ledger's CONTENT (each
position's own maths depends only on its own entry bar and exit bar, never
on sibling positions or dict ordering), so two runs with the same fixture,
seed, and params produce identical trade rows on every non-autoincrement
column.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import pandas as pd

from trader.backtest import config, exits, fills, ledger
from trader.backtest.iterator import PointInTimeIterator
from trader.data.api import resolve_instrument

_QTY_EPSILON = 1e-9


@dataclass
class _OpenPosition:
    """Runner-owned bookkeeping wrapped around exits.PositionState.

    exits.PositionState only tracks what evaluate_exit needs (stop/tp
    prices fixed at entry, scale-out tranches already fired, qty_remaining
    as a FRACTION of the original size). Everything else the runner needs
    across bars -- the actual share/coin quantity, the fees and slippage
    already paid at entry, the ledger position_id, and the running
    days_held counter -- lives here instead, so exits.py's own contract
    stays untouched by integration-only concerns.
    """

    position_id: str
    symbol: str
    asset_class: str
    state: "exits.PositionState"
    entry_ts: str
    entry_price: float
    total_qty: float
    entry_fee_total: float
    entry_slippage_total: float
    days_held: int = 0
    watermark: float | None = None


def _date_str(date) -> str:
    return pd.Timestamp(date).strftime("%Y-%m-%d")


def _next_bar_date(iterator: PointInTimeIterator, symbol: str, after_date):
    """The first date in iterator.calendar strictly after `after_date` where
    `symbol` actually has a bar (D-04's one-bar entry lag) -- skips forward
    over any dates the symbol has no bar on, rather than blindly using the
    next calendar index."""
    for date in iterator.calendar:
        if date > after_date and iterator.bar_on(symbol, date) is not None:
            return date
    return None


def _resolve_asset_class(conn, symbol: str, cache: dict) -> str:
    """Resolve and cache symbol's asset_class once per run via
    trader.data.api.resolve_instrument, the same instruments-table lookup
    Phase 1's get_daily_bars uses -- an unregistered non-crypto-shaped
    symbol (no "/") resolves to "stock" with no network call, which is the
    common case for this harness's own fixtures and tests."""
    if symbol not in cache:
        asset_class, _venue = resolve_instrument(conn, symbol)
        cache[symbol] = asset_class
    return cache[symbol]


def _open_position(
    conn, symbol: str, asset_class_cache: dict, profile, bar: dict, date
) -> _OpenPosition:
    asset_class = _resolve_asset_class(conn, symbol, asset_class_cache)
    entry_price = fills.entry_fill_price(bar["open"], asset_class, "buy")
    total_qty = config.DEFAULT_NOTIONAL / entry_price
    entry_fee_total = fills.fee_for(asset_class, total_qty, entry_price)
    # Dollar cost of entry slippage: the gap between the raw bar open and
    # the slippage-adjusted entry_price, over the full position size.
    entry_slippage_total = (entry_price - bar["open"]) * total_qty

    return _OpenPosition(
        position_id=f"{symbol}:{_date_str(date)}",
        symbol=symbol,
        asset_class=asset_class,
        state=exits.PositionState.open(profile, entry_price, qty_remaining=1.0),
        entry_ts=_date_str(date),
        entry_price=entry_price,
        total_qty=total_qty,
        entry_fee_total=entry_fee_total,
        entry_slippage_total=entry_slippage_total,
        days_held=0,
        watermark=entry_price,
    )


def _record_exit(conn, run_id: int, strategy_id: str, position: _OpenPosition, result, date) -> None:
    """Turn one ExitResult into a backtest_trades row.

    exits.py's raw_price already encodes D-04's worse-of/close convention
    (worse_of_fill for stop/trailing/scale_out/take_profit, the bar's own
    close for eod_flat/time_stop) -- this layers ONLY fills.apply_slippage
    and fills.fee_for on top of that raw_price; it never re-applies
    worse_of_fill, which would double-count the gap-through penalty.
    """
    qty_closed = position.total_qty * result.exit_fraction
    exit_price = fills.apply_slippage(result.raw_price, "sell", position.asset_class)
    exit_fee = fills.fee_for(position.asset_class, qty_closed, exit_price)
    exit_slippage = abs(result.raw_price - exit_price) * qty_closed

    entry_fee_prorated = position.entry_fee_total * result.exit_fraction
    entry_slippage_prorated = position.entry_slippage_total * result.exit_fraction

    fees_total = entry_fee_prorated + exit_fee
    slippage_total = entry_slippage_prorated + exit_slippage
    pnl = (exit_price - position.entry_price) * qty_closed - fees_total

    ledger.record_trade(
        conn,
        run_id=run_id,
        position_id=position.position_id,
        strategy_id=strategy_id,
        symbol=position.symbol,
        asset_class=position.asset_class,
        entry_ts=position.entry_ts,
        entry_price=position.entry_price,
        exit_ts=_date_str(date),
        exit_price=exit_price,
        qty=qty_closed,
        fees=fees_total,
        slippage=slippage_total,
        pnl=pnl,
        exit_reason=result.reason,
    )

    position.state.qty_remaining -= result.exit_fraction


def run_backtest(
    strategy_fn,
    universe: list[str],
    profile,
    bars_by_symbol: dict,
    seed: int,
    params: dict,
    strategy_id: str,
    conn,
) -> int:
    """Run one full backtest and return its integer run_id.

    strategy_fn: the shared pick_entries(iterator, date, open_positions,
        rng) -> list[str] contract (plan 02-07). Called once per calendar
        date with that date's point-in-time history only.
    universe: the tradable symbol set -- bars_by_symbol is filtered down to
        this set before building the iterator, so a caller can pass a
        superset of loaded bars and restrict the run without re-fetching.
    profile: an config.EXIT_PROFILE, locked at entry for every position
        this run opens (standing rule 2).
    params: forwarded verbatim to ledger.record_run's params_json; this
        function reads params.get("profile_name") for the run's profile
        label, defaulting to the profile's class name if absent (all Phase
        2 profiles share one EXIT_PROFILE class, so an explicit
        profile_name in params is how a caller names which locked instance
        this run used).
    """
    scoped_bars = {symbol: df for symbol, df in bars_by_symbol.items() if symbol in universe}
    iterator = PointInTimeIterator(scoped_bars)
    rng = random.Random(seed)

    profile_name = params.get("profile_name", type(profile).__name__)
    run_id = ledger.record_run(conn, strategy_id, profile_name, params, seed)

    open_positions: dict[str, _OpenPosition] = {}
    pending_entries: dict[str, "pd.Timestamp"] = {}
    asset_class_cache: dict = {}

    for date in iterator.calendar:
        iterator.advance_to(date)

        # 1. Open any entries scheduled from an earlier date's signal, and
        # immediately run the entry-bar exit check against that SAME fill
        # bar (D-10/Pitfall 2) -- never deferred to a later loop pass.
        opened_today: set[str] = set()
        for symbol in list(pending_entries.keys()):
            if pending_entries[symbol] != date:
                continue
            del pending_entries[symbol]
            bar = iterator.bar_on(symbol, date)
            position = _open_position(conn, symbol, asset_class_cache, profile, bar, date)
            opened_today.add(symbol)

            result = exits.evaluate_exit(profile, position.state, bar, 0, position.watermark)
            if result is not None:
                _record_exit(conn, run_id, strategy_id, position, result, date)
                position.watermark = result.new_watermark
                if position.state.qty_remaining > _QTY_EPSILON:
                    open_positions[symbol] = position
            else:
                position.watermark = exits.next_watermark(position.state, position.watermark, bar)
                open_positions[symbol] = position

        # 2. Evaluate exits for positions opened on an earlier date --
        # never symbols opened above in this same pass, which already got
        # their entry-bar check.
        for symbol in list(open_positions.keys()):
            if symbol in opened_today:
                continue
            position = open_positions[symbol]
            bar = iterator.bar_on(symbol, date)
            if bar is None:
                continue  # no bar today for this symbol -- wait for the next one
            position.days_held += 1
            result = exits.evaluate_exit(
                profile, position.state, bar, position.days_held, position.watermark
            )
            if result is not None:
                _record_exit(conn, run_id, strategy_id, position, result, date)
                position.watermark = result.new_watermark
                if position.state.qty_remaining <= _QTY_EPSILON:
                    del open_positions[symbol]
            else:
                position.watermark = exits.next_watermark(position.state, position.watermark, bar)

        # 3. Signal today (point-in-time by construction -- strategy_fn
        # only ever reads iterator.history()) and schedule any new entries
        # at the NEXT bar the symbol actually has, never today's own bar
        # (D-04's one-bar entry lag).
        committed = set(open_positions.keys()) | set(pending_entries.keys())
        for symbol in strategy_fn(iterator, date, committed, rng):
            if symbol in committed:
                continue
            fill_date = _next_bar_date(iterator, symbol, date)
            if fill_date is not None:
                pending_entries[symbol] = fill_date
                committed.add(symbol)

    return run_id
