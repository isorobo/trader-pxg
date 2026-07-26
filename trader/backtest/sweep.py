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

5. `run_oos_validation` (Plan 03-05, STRAT-05): validates every D-10 top-5
   candidate against its regime's held-out OOS window only -- the same
   `frozen_config.verify_frozen()` gate and the same `_slice_bars` helper
   as `run_tune_sweep`, but bounded to `[regime.oos_start, regime.oos_end]`
   instead of the tune window. Unlike `run_tune_sweep`, this function DOES
   import `regimes.py` directly (see the interface note in
   03-05-PLAN.md) to look candidates' regimes up by `(bucket, label)`,
   since a candidate dict only carries the regime's label, not the frozen
   window itself.
6. `determine_survivor` (D-09/T-03-15): the ONLY code path that turns OOS
   metrics into a verdict. A candidate below the minimum-trade floor is
   always "insufficient_sample" regardless of how good its profit_factor
   looks -- the same thin-lucky-window guard `select_top5` already applies
   at the tune stage, now applied again at the OOS stage (Common Pitfall 3).

Plan 03-05 drives `run_oos_validation` against the real 15 tune-sweep
candidates and the real frozen regime windows; this module is proven
correct here against tiny fixture regimes/candidates only
(tests/test_oos_validation.py).
"""

from __future__ import annotations

import math

import pandas as pd

from trader.backtest import config, exit_grid, frozen_config, ledger, metrics, regimes, runner, universe

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


def select_top5(cell_results: list[dict], min_trades: int = 30) -> list[dict]:
    """D-10's pre-registered top-5 rule: the only code path that selects
    which tune-sweep cells advance to OOS validation (T-03-11).

    Filters to cells whose `metrics.trade_count` clears `min_trades` (a
    cherry-picked lucky small-N cell is excluded from ranking entirely,
    regardless of how high its profit_factor is), then ranks the survivors
    descending by `metrics.profit_factor` -- deliberately post-cost profit
    factor, never raw return, per 03-RESEARCH.md's Overfitting Guards #2:
    `compute_metrics` already reflects fees and slippage, so ranking by it
    is the honest metric. `math.inf` (zero losing trades) sorts above every
    finite value naturally; a `None` profit_factor (zero trades) floors to
    0.0 for ranking purposes only -- it can only occur here if `min_trades`
    is passed as 0, since a real trade_count >= 1 always yields a non-None
    profit_factor.

    Returns at most 5 results, in descending profit_factor order. Fewer
    than 5 eligible cells returns all of them (no padding); zero eligible
    cells returns an empty list (not an error).
    """
    eligible = [r for r in cell_results if r["metrics"]["trade_count"] >= min_trades]
    eligible.sort(
        key=lambda r: (
            r["metrics"]["profit_factor"]
            if r["metrics"]["profit_factor"] is not None
            else 0.0
        ),
        reverse=True,
    )
    return eligible[:5]


def run_oos_validation(
    candidates: list[dict],
    bars_by_symbol_by_bucket: dict[str, dict],
    conn,
    sweep_id: str,
    seed: int = 20260726,
) -> list[dict]:
    """Validate every D-10 top-5 candidate against its regime's held-out OOS
    window and return one result dict per candidate.

    Each returned dict is `{"candidate": dict, "oos_run_id": int,
    "oos_metrics": dict}` -- `oos_metrics` is `compute_metrics`'s output over
    that candidate's OOS trades (post-fees/slippage, the same honest basis
    `run_tune_sweep`'s cells are ranked on).

    `frozen_config.verify_frozen()` is called FIRST, before any regime
    lookup, EXIT_PROFILE reconstruction, or run_backtest call
    (T-03-14) -- its RuntimeError propagates uncaught on a hash mismatch,
    guaranteeing zero `run_backtest` calls and zero DB writes for a
    tampered config, exactly mirroring `run_tune_sweep`'s gate placement.

    `candidates` is `reports/backtests/tune_top5.json`'s real schema (Plan
    03-04) plus one caller-injected key: `strategy_fn`, the actual
    pick_entries callable for that candidate's base strategy. This module
    holds no strategy-name registry of its own -- the caller script
    (`run_oos_validation_all.py`) resolves `strategy_fn` from
    `candidate["strategy_id"]` before calling this function.

    `bars_by_symbol_by_bucket` maps each candidate's `bucket` to that
    bucket's full (unsliced) `bars_by_symbol` dict -- this function slices
    to `[regime.oos_start, regime.oos_end]` itself via `_slice_bars`, the
    same helper `run_tune_sweep` uses for its own tune-window slice.

    Unlike `run_tune_sweep` (which never imports `regimes.py` directly so
    tests can hand it a lightweight stand-in), this function DOES look each
    candidate's regime up from `regimes.REGIMES` by `(bucket, label)` --
    a candidate dict only carries the regime's label string, not the frozen
    window itself, so there is no other way to recover `oos_start`/
    `oos_end`.
    """
    frozen_config.verify_frozen()

    results: list[dict] = []
    for candidate in candidates:
        bucket = candidate["bucket"]
        regime_label = candidate["regime"]
        regime = next(
            r for r in regimes.REGIMES if r.bucket == bucket and r.label == regime_label
        )

        params = candidate["params"]
        profile = config.EXIT_PROFILE(
            stop_pct=params["stop_pct"],
            tp_pct=params["tp_pct"],
            scale_out=(),
            trailing_pct=params["trailing_pct"],
            max_hold_days=params["max_hold_days"],
            eod_flat=False,
        )

        sliced_bars = _slice_bars(
            bars_by_symbol_by_bucket[bucket], regime.oos_start, regime.oos_end
        )

        run_id = runner.run_backtest(
            candidate["strategy_fn"],
            universe.UNIVERSE_BY_BUCKET[bucket],
            profile,
            sliced_bars,
            seed,
            params={**params, "split": "oos", "sweep_id": sweep_id},
            strategy_id=candidate["strategy_id"],
            conn=conn,
        )

        trades = ledger.get_trades_for_run(conn, run_id)
        oos_metrics = metrics.compute_metrics(trades)
        results.append(
            {"candidate": candidate, "oos_run_id": run_id, "oos_metrics": oos_metrics}
        )

    return results


def determine_survivor(oos_metrics: dict, min_trades: int = 15) -> str:
    """D-09's OOS verdict rule (T-03-15): the ONLY code path that turns a
    candidate's OOS metrics into a survivor/insufficient_sample/killed
    verdict.

    Returns "insufficient_sample" when `oos_metrics["trade_count"]` is below
    `min_trades` (15, D-09's OOS floor), REGARDLESS of `profit_factor` --
    Common Pitfall 3's guard: a synthetic 4-trade OOS window with a very
    high profit_factor still returns "insufficient_sample", never
    "survivor". A thin lucky window can never be reported as a survivor.

    Otherwise returns "survivor" when `profit_factor` is `math.inf` (zero
    losing trades) or strictly greater than 1.0 (post-cost profitability,
    since `compute_metrics` already reflects fees/slippage), else "killed".
    """
    if oos_metrics["trade_count"] < min_trades:
        return "insufficient_sample"

    profit_factor = oos_metrics["profit_factor"]
    if profit_factor is math.inf or (profit_factor or 0) > 1.0:
        return "survivor"
    return "killed"
