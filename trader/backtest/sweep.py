"""Tune-sweep grid orchestration for STRAT-03, plus D-10's pre-registered
top-5 selection rule with a minimum-trade-count floor.

This module is pure orchestration, not a new engine: every cell's trades
flow through the unmodified Phase 2 loop (`trader.backtest.runner.run_backtest`,
D-07) -- there is no bypass path here for fills, fees, or slippage. What this
module adds on top is:

1. The frozen-config hash gate (T-03-06/T-03-08) as a hard runtime check,
   called before any grid iteration or DB write -- standing rule 1 ("never
   edit graduation/kill criteria while looking at results") enforced in
   code, not by convention. `frozen_config.verify_frozen()`'s RuntimeError
   is allowed to propagate uncaught; this module never wraps it in a
   try/except that could silently swallow a tamper signal.
2. Sweep provenance (T-03-09): every cell's `params` dict carries
   `sweep_id`, `regime`, `split`, `asset_class_bucket`, and `strategy` keys,
   forwarded verbatim into `ledger.record_run`'s free-form `params_json`
   column (03-RESEARCH.md Pattern 3) -- no migration needed, and every
   cell's provenance is recoverable from the DB alone, not from in-memory
   state.
3. Tune-window bar slicing: `_slice_bars` bounds every symbol's bars to the
   regime's own `[tune_start, tune_end]` closed interval before any cell
   runs, so a strategy_fn can never see -- let alone trade on -- a bar dated
   after the tune window closes.
4. `select_top5` (D-10): the ONLY code path that selects OOS candidates.
   Ranks by post-cost profit_factor (never raw return, since
   `compute_metrics` already reflects fees/slippage) among cells that clear
   a minimum-trade floor -- a lucky small-N cell can never reach the top-5
   list regardless of how good its profit_factor looks (T-03-11).

Plan 03-04 drives this module against the real 270/360-cell grid and the
real frozen universe; this module is proven correct here against tiny
fixture grids only (tests/test_sweep_engine.py).
"""

from __future__ import annotations

from trader.backtest import exit_grid, frozen_config, ledger, metrics, runner

# Reused by later plans/scripts that drive the real sweep (Plan 03-04) so
# every script shares one literal sweep_id rather than re-deriving it.
DEFAULT_SWEEP_ID = "2026-07-26-strategy-lab-v1"


def _slice_bars(bars_by_symbol: dict, start: str | None, end: str) -> dict:
    """Return a new dict of per-symbol DataFrames, each filtered to the
    closed UTC date interval [start, end].

    `start=None` means "from the symbol's own first row" (`df.index[0]`) --
    the only case this occurs is new_memecoin's "mania" regime, where each
    symbol lists on Binance at a different date and there is no single
    shared calendar tune-start across the bucket (regimes.py's own
    docstring). `end` is always a concrete date string (every Regime in
    regimes.py sets tune_end explicitly).

    Never mutates the input DataFrames -- `.loc[...]` on a boolean mask
    returns a new (view-backed) frame, not an in-place filter.
    """
    import pandas as pd

    end_ts = pd.Timestamp(end, tz="UTC")

    sliced: dict = {}
    for symbol, df in bars_by_symbol.items():
        start_ts = pd.Timestamp(start, tz="UTC") if start is not None else df.index[0]
        sliced[symbol] = df.loc[(df.index >= start_ts) & (df.index <= end_ts)]
    return sliced


def run_tune_sweep(
    strategy_fn,
    strategy_id: str,
    bucket: str,
    regime,
    bars_by_symbol: dict,
    universe: list[str],
    conn,
    sweep_id: str,
    seed: int = 20260726,
) -> list[dict]:
    """Run every cell of `bucket`'s frozen exit-profile grid across
    `regime`'s tune window and return one result dict per cell.

    Each returned dict is `{"run_id": int, "params": dict, "metrics": dict}`
    -- `params` is exactly what was persisted to `backtest_runs.params_json`
    for that cell (T-03-09), and `metrics` is `compute_metrics`'s output
    over that cell's trades (post-fees/slippage, D-10's ranking basis).

    `frozen_config.verify_frozen()` is called FIRST, before any grid
    iteration, regime lookup, or DB write (T-03-06/T-03-08) -- its
    RuntimeError propagates uncaught on a hash mismatch, guaranteeing zero
    `run_backtest` calls and zero DB writes for a tampered config.

    `regime` is any object exposing `.label`, `.tune_start`, `.tune_end`
    (matching `regimes.Regime`'s field contract) -- this module never
    imports `regimes.py` directly, so tests can hand it a lightweight stand-
    in without touching the real frozen regime windows.
    """
    frozen_config.verify_frozen()

    sliced_bars = _slice_bars(bars_by_symbol, regime.tune_start, regime.tune_end)

    results: list[dict] = []
    for profile in exit_grid.exit_profile_grid(bucket):
        profile_name = (
            f"{strategy_id}_{bucket}_{regime.label}_tune_"
            f"stop{profile.stop_pct}_tp{profile.tp_pct}_"
            f"trail{profile.trailing_pct}_hold{profile.max_hold_days}"
        )
        params = {
            "profile_name": profile_name,
            "sweep_id": sweep_id,
            "regime": regime.label,
            "split": "tune",
            "asset_class_bucket": bucket,
            "strategy": strategy_id,
            "stop_pct": profile.stop_pct,
            "tp_pct": profile.tp_pct,
            "trailing_pct": profile.trailing_pct,
            "max_hold_days": profile.max_hold_days,
        }

        run_id = runner.run_backtest(
            strategy_fn,
            universe,
            profile,
            sliced_bars,
            seed,
            params,
            strategy_id,
            conn,
        )

        trades = ledger.get_trades_for_run(conn, run_id)
        cell_metrics = metrics.compute_metrics(trades)
        results.append({"run_id": run_id, "params": params, "metrics": cell_metrics})

    return results
