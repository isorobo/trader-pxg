---
phase: 03-strategy-lab
plan: 05
subsystem: backtest
tags: [sweep, sqlite, oos-validation, momentum, d09-verdict]

# Dependency graph
requires:
  - phase: 03-strategy-lab (Plan 03-03)
    provides: trader.backtest.sweep's run_tune_sweep/select_top5 engine, hash-gated and provenance-tagged, and the _slice_bars helper reused here
  - phase: 03-strategy-lab (Plan 03-04)
    provides: reports/backtests/tune_top5.json, the real 15-candidate D-10 top-5 list this plan validates
provides:
  - trader/backtest/sweep.py's run_oos_validation + determine_survivor (STRAT-05's OOS rule as executable code)
  - trader/backtest/run_oos_validation_all.py, the real driver over every tune-sweep candidate
  - reports/backtests/oos_results.json, the real (non-fixture) per-candidate OOS verdict artifact
affects: [03-06-kill-conditions-and-reporting]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "OOS entrypoints look regimes up directly from regimes.REGIMES by (bucket, label), unlike run_tune_sweep which never imports regimes.py -- a candidate dict only carries the regime's label string, not the frozen window itself"
    - "strategy_fn resolution via composite-strategy_id-suffix-stripping onto a COPY of each candidate dict, so the non-JSON-serializable callable never reaches the written output artifact"

key-files:
  created:
    - trader/backtest/run_oos_validation_all.py
    - tests/test_oos_validation.py
  modified:
    - trader/backtest/sweep.py

key-decisions:
  - "run_oos_validation's params dict for the OOS run_backtest call is exactly {**candidate[\"params\"], \"split\": \"oos\", \"sweep_id\": sweep_id} per the plan's literal action spec -- profile_name and other provenance fields are reused verbatim from the tune-stage params rather than re-derived for the OOS stage"
  - "seed is a literal 20260726 default on run_oos_validation (matching run_tune_sweep's own default), not threaded through as a required caller argument, since neither the plan's declared signature nor run_oos_validation_all.py has any reason to vary it"

patterns-established:
  - "OOS validation drivers resolve their own DB connection eagerly (conn=None -> data_db.get_connection()), matching run_tune_sweep_all.py's precedent"

requirements-completed: [STRAT-04, STRAT-05]

# Metrics
duration: ~11min (Task 1 RED+GREEN ~6min; Task 2 real OOS run under 1 min wall time, well under 03-RESEARCH.md's estimate since only 15 candidates)
completed: 2026-07-26
---

# Phase 03 Plan 05: OOS Validation Engine Summary

**Every one of Plan 03-04's 15 real momentum tune-sweep candidates ran for real against its regime's held-out OOS window and came back "insufficient_sample" -- an honest D-09 result, not a bug, driven by OOS windows (4-6 months) producing far fewer trades than the 18-month tune windows that seeded the candidate list.**

## Performance

- **Duration:** ~11 min total (RED/GREEN authoring ~6 min; real OOS run itself under 1 min wall time)
- **Started:** 2026-07-26T20:22Z (session start, following Plan 03-04's completion)
- **Completed:** 2026-07-26T20:33Z
- **Tasks:** 2 completed
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments

- `trader/backtest/sweep.py` gained `run_oos_validation` and `determine_survivor`: the frozen-config hash gate (`frozen_config.verify_frozen()`) is now enforced at the OOS-validation entrypoint exactly as it already was at the tune-sweep entrypoint, proven by a dedicated fixture test with a call-count spy on `runner.run_backtest` showing zero calls on a tampered hash.
- OOS bars are provably restricted to `[regime.oos_start, regime.oos_end]` only, reusing `_slice_bars` (never duplicated) -- proven by a date-recording spy `strategy_fn` whose every recorded call date falls inside the OOS window, never the tune window.
- `determine_survivor`'s three-way rule (survivor / insufficient_sample / killed) enforces the 15-trade OOS floor before `profit_factor` is ever consulted -- a synthetic 4-trade window with `profit_factor=100.0` still returns `"insufficient_sample"`, proving Common Pitfall 3's guard holds at the OOS stage exactly as `select_top5`'s 30-trade floor already holds at the tune stage.
- `trader/backtest/run_oos_validation_all.py` drove the real OOS validation run over all 15 real candidates from `reports/backtests/tune_top5.json`, resolving each candidate's `strategy_fn` by stripping the `_{bucket}` suffix from its composite `strategy_id` and consuming `sweep.run_oos_validation`/`determine_survivor` without reimplementing either.
- `reports/backtests/oos_results.json` records every one of the 15 candidates' OOS metrics and verdict -- not filtered to survivors -- and re-running the script against the same `tune_top5.json` and cached data reproduces byte-identical `oos_metrics`/`verdict` content (only the autoincrement `run_id` differs between runs, as expected for an append-only ledger).

## Task Commits

Each task was committed atomically, following the plan's `type="tdd"` RED -> GREEN gate sequence:

1. **Task 1 (RED): failing tests for run_oos_validation + determine_survivor** - `bf14999` (test)
2. **Task 1 (GREEN): implement run_oos_validation + determine_survivor** - `f75c62d` (feat)
3. **Task 2: run_oos_validation_all.py + real acceptance run** - `c636a21` (feat)

**Plan metadata:** (this commit, following SUMMARY.md)

_Note: Task 2's real run itself (`python -m trader.backtest.run_oos_validation_all`) is an offline execution step, not a separate code change -- no bugfix was required this time (unlike Plan 03-04's Task 2), so there is exactly one commit for Task 2. `reports/backtests/oos_results.json` lives under the gitignored `reports/` directory (D-12) and is intentionally never committed._

## TDD Gate Compliance

- RED gate: `bf14999` (`test(03-05): add failing tests...`) -- 8 of 9 new tests failed with `AttributeError` (the missing `run_oos_validation`/`determine_survivor` attributes); the 9th (`test_slice_bars_reused_bounds_oos_window_to_closed_interval`) passed immediately since it only exercises the already-implemented `_slice_bars` helper, not new code.
- GREEN gate: `f75c62d` (`feat(03-05): implement run_oos_validation...`) -- all 9 new tests pass; full suite 202/202.
- No REFACTOR commit was needed; the GREEN implementation required no follow-up cleanup.

## Files Created/Modified

- `trader/backtest/sweep.py` - Added `run_oos_validation(candidates, bars_by_symbol_by_bucket, conn, sweep_id, seed=20260726) -> list[dict]` and `determine_survivor(oos_metrics, min_trades=15) -> str`
- `trader/backtest/run_oos_validation_all.py` - Real OOS validation driver; `main(conn=None) -> Path`
- `tests/test_oos_validation.py` - 9 tests: hash-gate fixture test, OOS-window-slicing proof, and the full `determine_survivor` three-way branch matrix including the Pitfall-3 thin-sample guard
- `reports/backtests/oos_results.json` (gitignored, not committed) - Real 15-candidate OOS verdict output

## Decisions Made

- **`run_oos_validation`'s OOS `params` dict is exactly `{**candidate["params"], "split": "oos", "sweep_id": sweep_id}`**, per the plan's literal action text -- this reuses the tune-stage's `profile_name`/`regime`/`asset_class_bucket`/`strategy` fields verbatim rather than constructing a fresh OOS-specific profile name. The persisted `params_json` for an OOS run therefore still shows a `_tune_` profile-name string even though `split` correctly reads `"oos"` -- a minor label artifact, not a correctness issue, since `split` is the authoritative field Plan 03-06 will filter on.
- **`seed` defaults to the literal `20260726`** on `run_oos_validation`, matching `run_tune_sweep`'s own default -- the plan's declared signature (`run_oos_validation(candidates, bars_by_symbol_by_bucket, conn, sweep_id) -> list[dict]`) does not list `seed` as a required parameter, and no caller (fixture tests or the real driver) needs to vary it.
- **`run_oos_validation_all.py` builds `strategy_fn`-augmented candidates onto copies, never mutating the originals** -- the output JSON strips `strategy_fn` back out per result before writing, so the non-serializable callable never reaches `json.dumps`.

## Deviations from Plan

None - plan executed exactly as written. Both tasks completed without any Rule 1-4 auto-fixes; the real acceptance run required no bugfix (unlike Plan 03-04's Task 2, whose `conn=None` crash was fixed on first attempt there and is therefore already resolved via the same `conn is None -> data_db.get_connection()` pattern reused here).

## Issues Encountered

None. The real OOS run completed in under a minute (15 candidates against 4-6 month windows), well under 03-RESEARCH.md's estimate.

## Per-Candidate OOS Verdict Table (the phase's key result)

All 15 real Plan 03-04 candidates -- every one momentum, split across `stock`/trending, `stock`/choppy, and `crypto_major_legacy_meme`/trending -- came back `insufficient_sample`. Zero survivors. Zero killed. This is D-09's 15-trade OOS floor working exactly as designed: none of the 15 candidates' OOS windows (4-6 calendar months) produced enough closed trades to clear the floor, even though most of them show a superficially strong `profit_factor` on the trades they did produce.

| # | Strategy (composite) | Bucket | Regime | OOS run_id | OOS trades | OOS profit_factor | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | momentum_stock | stock | trending | 3696 | 5 | inf | insufficient_sample |
| 2 | momentum_stock | stock | trending | 3697 | 5 | inf | insufficient_sample |
| 3 | momentum_stock | stock | trending | 3698 | 5 | inf | insufficient_sample |
| 4 | momentum_stock | stock | trending | 3699 | 5 | inf | insufficient_sample |
| 5 | momentum_stock | stock | trending | 3700 | 5 | inf | insufficient_sample |
| 6 | momentum_stock | stock | choppy | 3701 | 11 | 3.3039 | insufficient_sample |
| 7 | momentum_stock | stock | choppy | 3702 | 11 | 3.2920 | insufficient_sample |
| 8 | momentum_stock | stock | choppy | 3703 | 11 | 3.2920 | insufficient_sample |
| 9 | momentum_stock | stock | choppy | 3704 | 11 | 3.2920 | insufficient_sample |
| 10 | momentum_stock | stock | choppy | 3705 | 11 | 6.4873 | insufficient_sample |
| 11 | momentum_crypto_major_legacy_meme | crypto_major_legacy_meme | trending | 3706 | 11 | 0.0000 | insufficient_sample |
| 12 | momentum_crypto_major_legacy_meme | crypto_major_legacy_meme | trending | 3707 | 12 | 0.0965 | insufficient_sample |
| 13 | momentum_crypto_major_legacy_meme | crypto_major_legacy_meme | trending | 3708 | 13 | 3.5455 | insufficient_sample |
| 14 | momentum_crypto_major_legacy_meme | crypto_major_legacy_meme | trending | 3709 | 14 | 1.6750 | insufficient_sample |
| 15 | momentum_crypto_major_legacy_meme | crypto_major_legacy_meme | trending | 3710 | 13 | 0.8811 | insufficient_sample |

**Totals: 15 candidates validated, 15 insufficient_sample, 0 survivors, 0 killed.**

Note on run_id values: these are from the SECOND of two identical acceptance runs performed during this plan's execution (the first, `3681-3695`, was run to produce the initial artifact; the second, `3696-3710`, was run immediately after purely to prove reproducibility -- see "Decisions Made"/verification below). Both runs produced byte-identical `oos_metrics` and `verdict` values per candidate; only the autoincrement `run_id` differs, exactly as expected for an append-only ledger.

Reproducibility was verified directly: the two runs' `oos_metrics` and `verdict` dicts compared equal for all 15 candidates (zero mismatches), confirming D-07/D-12's reproducibility requirement holds at the OOS-validation stage.

## User Setup Required

None - no external service configuration required (offline, cache-hit-only run against the already-cached history Plan 03-04 confirmed was in place).

## Next Phase Readiness

- `reports/backtests/oos_results.json` is real, schema-valid, and records every candidate's verdict (not filtered to survivors) -- ready for Plan 03-06 to read and write kill conditions / the sweep reports.
- Plan 03-06 should expect an honest, sobering headline: zero of Phase 3's 15 real tune-sweep candidates cleared the OOS floor. This is not a code defect -- it is D-09's out-of-sample honesty mechanism doing exactly what STRAT-05 asked it to do, against real cached market data. Plan 03-06's kill-condition/report logic must handle an all-insufficient_sample outcome as a valid, reportable result, not as an error case to special-case around.
- Full test suite green: 202 passed (193 baseline + 9 new tests for this plan).

---
*Phase: 03-strategy-lab*
*Completed: 2026-07-26*

## Self-Check: PASSED

- FOUND: `trader/backtest/run_oos_validation_all.py`
- FOUND: `tests/test_oos_validation.py`
- FOUND: `reports/backtests/oos_results.json` (gitignored, on-disk artifact)
- FOUND: commit `bf14999` (Task 1 RED)
- FOUND: commit `f75c62d` (Task 1 GREEN)
- FOUND: commit `c636a21` (Task 2)
