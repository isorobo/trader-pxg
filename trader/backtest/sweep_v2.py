"""v2 variant-aware tune-sweep and OOS-validation engine (Plan 03-08,
STRAT-03/04/05/06).

Mirrors trader/backtest/sweep.py's exact orchestration pattern one-for-one,
extended with a single new swept dimension -- entry-gate strictness
(D-14's momentum_v2/breakout_v2 variants: strict/base/loose) -- while
reusing v1's grid/floor/selection machinery verbatim, never redefining it
(D-15):

- `_slice_bars`, `select_top5`, `determine_survivor` are imported directly
  from `trader.backtest.sweep` and used AS-IS. This module never
  reimplements bar slicing, the top-5 ranking rule, or the OOS survivor
  verdict rule.
- `exit_grid.exit_profile_grid` (the frozen D-06 exit grid, unchanged) and
  `config.EXIT_PROFILE` are consumed exactly as v1's sweep.py consumes
  them.
- The ONLY new provenance key is `entry_variant`: every persisted v2 cell's
  `params_json` carries the same 5 keys v1's `run_tune_sweep` already
  persists (`sweep_id`, `regime`, `split`, `asset_class_bucket`,
  `strategy`) PLUS `entry_variant`.

`run_tune_sweep_v2` itself does not loop over entry variants -- it runs the
exit-profile grid for ONE caller-supplied variant. Plan 03-08 Task 2's
driver (`run_tune_sweep_all_v2.py`) is the caller that loops over all 3
variants per (strategy, bucket, regime) unit and concatenates the results.

`run_oos_validation_v2` mirrors v1's `run_oos_validation` exactly, except
it is gated by v2's own `frozen_config_v2.verify_frozen_v2()` (never v1's
`frozen_config.verify_frozen`) and looks each candidate's regime up from
`regimes_v2.REGIMES_V2` (never v1's `regimes.REGIMES`) by
`(bucket, label)`.

Both entrypoints call their respective hash gate FIRST, before any grid
iteration, regime lookup, or DB write (T-03-25) -- the RuntimeError
propagates uncaught on a hash mismatch, guaranteeing zero `run_backtest`
calls and zero DB writes for a tampered v2 config, exactly mirroring v1's
own gate placement in `sweep.py`.
"""

from __future__ import annotations

from trader.backtest import config, exit_grid, ledger, metrics, regimes_v2, runner, universe
from trader.backtest.frozen_config_v2 import verify_frozen_v2
from trader.backtest.sweep import _slice_bars, determine_survivor, select_top5

# Reused by Plan 03-08's real drivers so every v2 script shares one literal
# sweep_id rather than re-deriving it -- mirrors sweep.DEFAULT_SWEEP_ID's
# role for v1.
DEFAULT_SWEEP_ID_V2 = "v2"


def run_tune_sweep_v2(
    strategy_fn,
    strategy_id: str,
    bucket: str,
    regime,
    entry_variant_name: str,
    bars_by_symbol: dict,
    universe: list[str],
    conn,
    sweep_id: str = DEFAULT_SWEEP_ID_V2,
    seed: int = 20260726,
) -> list[dict]:
    """Run every cell of `bucket`'s frozen exit-profile grid, for ONE
    entry-variant, across `regime`'s tune window, and return one result
    dict per cell.

    Each returned dict is `{"run_id": int, "params": dict, "metrics": dict}`
    -- identical shape to v1's `sweep.run_tune_sweep`, with one addition:
    `params["entry_variant"]` records which of momentum_v2/breakout_v2's
    strict/base/loose variants produced this cell (the caller binds
    `strategy_fn` to that variant via `make_pick_entries` before calling
    this function; this module itself is variant-agnostic and only records
    the caller-supplied label for provenance).

    `frozen_config_v2.verify_frozen_v2()` is called FIRST, before any grid
    iteration, regime lookup, or DB write (T-03-25) -- its RuntimeError
    propagates uncaught on a hash mismatch.

    `regime` is any object exposing `.label`, `.tune_start`, `.tune_end`
    (matching `regimes_v2.Regime`'s field contract, itself reused from
    v1's `regimes.Regime`) -- this module never imports `regimes_v2.py`
    for tune-sweep purposes, so tests can hand it a lightweight stand-in.
    """
    verify_frozen_v2()

    sliced_bars = _slice_bars(bars_by_symbol, regime.tune_start, regime.tune_end)

    results: list[dict] = []
    for profile in exit_grid.exit_profile_grid(bucket):
        profile_name = (
            f"{strategy_id}_{bucket}_{regime.label}_{entry_variant_name}_tune_"
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
            "entry_variant": entry_variant_name,
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


def run_oos_validation_v2(
    candidates: list[dict],
    bars_by_symbol_by_bucket: dict[str, dict],
    conn,
    sweep_id: str = DEFAULT_SWEEP_ID_V2,
    seed: int = 20260726,
) -> list[dict]:
    """Validate every v2 top-5 candidate against its regime's held-out OOS
    window and return one result dict per candidate.

    Mirrors v1's `sweep.run_oos_validation` exactly (same
    `{"candidate": dict, "oos_run_id": int, "oos_metrics": dict}` return
    shape, same EXIT_PROFILE reconstruction from `candidate["params"]`,
    same `_slice_bars` call bounded to `[regime.oos_start, regime.oos_end]`,
    same `run_backtest` call with `split="oos"`), except:

    - Gated by `frozen_config_v2.verify_frozen_v2()` (T-03-25), never v1's
      `frozen_config.verify_frozen()`.
    - Looks each candidate's regime up from `regimes_v2.REGIMES_V2`
      (never v1's `regimes.REGIMES`) by `(bucket, label)`.

    `candidates` carries the same caller-injected `strategy_fn` key v1's
    `run_oos_validation` expects -- the caller script
    (`run_oos_validation_all_v2.py`) resolves it from
    `candidate["params"]["entry_variant"]` bound through the matching
    `make_pick_entries` before calling this function.
    """
    verify_frozen_v2()

    results: list[dict] = []
    for candidate in candidates:
        bucket = candidate["bucket"]
        regime_label = candidate["regime"]
        regime = next(
            r
            for r in regimes_v2.REGIMES_V2
            if r.bucket == bucket and r.label == regime_label
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
