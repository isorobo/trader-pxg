---
phase: 03-strategy-lab
plan: 03
subsystem: backtest
tags: [sweep, grid-search, provenance, overfitting-guards, sqlite, pandas]

# Dependency graph
requires:
  - phase: 03-strategy-lab (plan 03-02)
    provides: frozen_config.verify_frozen(), exit_grid.exit_profile_grid(), regimes.Regime
  - phase: 02-backtest-harness
    provides: runner.run_backtest(), ledger.get_trades_for_run(), metrics.compute_metrics()
provides:
  - run_tune_sweep(): grid iteration over the frozen exit-profile grid, hash-gated, provenance-tagged
  - select_top5(): D-10's pre-registered top-5 selection with a 30-trade minimum floor
  - DEFAULT_SWEEP_ID constant for later sweep-driving scripts to reuse
affects: [03-04 (real tune sweep), 03-05 (OOS validation, reuses the same hash-gate pattern)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Hard runtime hash-gate called first, before any grid iteration or DB write, RuntimeError uncaught"
    - "Free-form params_json provenance tagging (sweep_id/regime/split/asset_class_bucket/strategy) with zero migration"
    - "Bars sliced once per sweep call, not per cell, via a closed [start, end] UTC interval"

key-files:
  created:
    - trader/backtest/sweep.py
    - tests/test_sweep_engine.py
  modified: []

key-decisions:
  - "profile_name composed from strategy_id/bucket/regime.label/'tune'/stop_pct/tp_pct/trailing_pct/max_hold_days for human-readable run labeling, while the 5 provenance keys in params_json remain the machine-readable source of truth"
  - "select_top5's None-profit_factor floor (0.0) is unreachable in practice at min_trades>=1 since compute_metrics only returns None profit_factor at trade_count==0; documented inline as a defensive default, not exercised by design"
  - "_slice_bars takes bars_by_symbol once per sweep call (not per cell) since every cell in one run_tune_sweep call shares the same regime tune window"

patterns-established:
  - "Fixture-grid TDD: inject a tiny 2x2x1x1 grid via monkeypatch instead of running the real 270-cell grid in unit tests, keeping sweep-engine tests fast while proving the same code path Plan 03-04 will drive for real"

requirements-completed: [STRAT-03]

# Metrics
duration: ~15min
completed: 2026-07-26
---

# Phase 03 Plan 03: Sweep Engine Summary

**Hash-gated, provenance-tagged tune-sweep orchestration (`run_tune_sweep`) plus D-10's 30-trade-floored top-5 selection rule (`select_top5`), both proven against tiny fixture grids ahead of Plan 03-04's real 270/360-cell sweep.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2/2 completed
- **Files modified:** 2 (1 created source file, 1 created test file)

## Accomplishments
- `run_tune_sweep` calls `frozen_config.verify_frozen()` before any grid iteration or DB write; a hash-tamper test proves zero `run_backtest` calls and zero `backtest_runs` rows written when the gate trips
- Every tune-sweep cell's provenance (`sweep_id`, `regime`, `split`, `asset_class_bucket`, `strategy`) round-trips through `backtest_runs.params_json` read back from the DB, not in-memory state
- Bars are sliced once per sweep call to the regime's closed `[tune_start, tune_end]` interval (`tune_start=None` falling back to each symbol's own first row for new_memecoin's mania regime); a stub strategy_fn's recorded max call date never exceeds `tune_end`
- `select_top5` enforces the 30-trade minimum floor before ranking, ranks by post-cost `profit_factor` descending (`math.inf` naturally ranking above every finite value), returns at most 5 with no padding, and returns an empty list rather than erroring when zero cells qualify

## Task Commits

Each task was committed atomically, following RED -> GREEN per task (TDD plan):

1. **Task 1: run_tune_sweep — grid iteration, hash gate, provenance**
   - `df00302` test(03-03): add failing tests for run_tune_sweep hash gate and provenance
   - `808bca7` feat(03-03): implement run_tune_sweep with hash gate and provenance tagging
2. **Task 2: select_top5 — D-10 rule with min-trade floor**
   - `5d4ffa4` test(03-03): add failing tests for select_top5 min-trade floor and ranking
   - `449b12f` feat(03-03): implement select_top5 with D-10 min-trade-floor ranking
3. **Refactor (minor, no behavior change):**
   - `8713405` refactor(03-03): move pandas import to module top level in sweep.py

## Files Created/Modified
- `trader/backtest/sweep.py` - `run_tune_sweep`, `select_top5`, `_slice_bars`, `DEFAULT_SWEEP_ID`
- `tests/test_sweep_engine.py` - Hash-gate, provenance, bar-slicing, and top-5-selection fixture tests

## Decisions Made
- Provenance keys match the plan's must_haves exactly (`sweep_id`, `regime`, `split`, `asset_class_bucket`, `strategy`) rather than 03-RESEARCH.md's example dict's slightly different `asset_class` key — the plan's own frontmatter and threat model are the authoritative contract for this task.
- `regime` is accepted as any duck-typed object exposing `.label`/`.tune_start`/`.tune_end` rather than a hard `regimes.Regime` type-check, so tests exercise the real code path with a lightweight fixture stand-in without touching the frozen `regimes.py` module.
- Injected a 2x2x1x1 fixture grid (via monkeypatching `exit_grid.exit_profile_grid`) instead of running the real 270-cell stock grid in unit tests, per the plan's explicit "or an injected 2x2x1x1 grid" allowance — keeps the test suite fast; Plan 03-04 exercises the real grid size.

## Deviations from Plan

None - plan executed exactly as written. The one code-style refactor (moving a local `import pandas` to module top level) was a self-initiated cleanup, not a correctness fix, and is documented above rather than under Rule 1-3 since no bug or missing functionality was involved.

## Issues Encountered
None.

## Known Stubs
None. `sweep.py` has no stubbed data paths — every function is fully wired: `run_tune_sweep` calls the real `runner.run_backtest`/`ledger.get_trades_for_run`/`metrics.compute_metrics`, and `select_top5` operates purely on `run_tune_sweep`'s own output shape.

## Threat Flags
None. This plan's surface exactly matches the threat_model already declared in 03-03-PLAN.md (T-03-08 through T-03-11) — no new network endpoints, auth paths, or schema changes were introduced. `sweep.py` calls only in-process modules already covered by Phase 2's and Plan 03-02's own threat models.

## Next Phase Readiness
- `trader/backtest/sweep.py` exports `run_tune_sweep`, `select_top5`, and `DEFAULT_SWEEP_ID` exactly as Plan 03-04 expects.
- Full test suite: 192 passed (`python -m pytest -q`), including the 9 new tests in `tests/test_sweep_engine.py`.
- No blockers. Plan 03-04 can drive `run_tune_sweep` against the real frozen universe/regimes/exit-grid and pipe its output through `select_top5` unmodified.

---
*Phase: 03-strategy-lab*
*Completed: 2026-07-26*

## Self-Check: PASSED

- FOUND: trader/backtest/sweep.py
- FOUND: tests/test_sweep_engine.py
- FOUND: .planning/phases/03-strategy-lab/03-03-SUMMARY.md
- FOUND commit: df00302 (test)
- FOUND commit: 808bca7 (feat)
- FOUND commit: 5d4ffa4 (test)
- FOUND commit: 449b12f (feat)
- FOUND commit: 8713405 (refactor)
