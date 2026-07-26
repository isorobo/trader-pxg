---
phase: 03-strategy-lab
plan: 08
subsystem: backtest
tags: [backtest, sweep, oos-validation, kill-conditions, checkpoint-resume, hash-gate, tdd]

# Dependency graph
requires:
  - phase: 03-strategy-lab (03-07)
    provides: regimes_v2.REGIMES_V2, momentum_v2/breakout_v2 entry-variant registries, frozen_config_v2.verify_frozen_v2
provides:
  - sweep_v2.run_tune_sweep_v2/run_oos_validation_v2 -- variant-aware v2 engine, hash-gated, reuses sweep.select_top5/determine_survivor unchanged
  - run_tune_sweep_all_v2.py -- real, checkpoint-resumable v2 tune-sweep driver (10,800 real runs executed)
  - run_oos_validation_all_v2.py -- real v2 OOS validation driver (25 real candidates validated)
  - write_kill_conditions_v2.py / sweep_report_v2.py -- real KILL-CONDITIONS.md regeneration + survivors-v2 index
  - reports/backtests/tune_top5_v2.json, oos_results_v2.json -- real v2 sweep/OOS artifacts
  - .planning/phases/03-strategy-lab/KILL-CONDITIONS.md -- regenerated from v2's real results (5 survivors)
affects: [Phase 4 (paper-trading candidate selection reads KILL-CONDITIONS.md/oos_results_v2.json)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Checkpoint-resumable long-running sweep driver: JSON-lines checkpoint rewritten atomically (temp file + os.replace) per completed unit, keyed by (strategy, bucket, regime, variant); orphan DB rows from an interrupted unit are deleted before that unit is retried, keeping the final row-count invariant exact"
    - "v2 modules import and reuse v1's engine primitives verbatim (_slice_bars, select_top5, determine_survivor, kill-condition constants) rather than redefining them, so the two definitions can never drift (D-15)"
    - "v2 writes to distinctly-suffixed or run_id-disambiguated filenames everywhere except the one file (KILL-CONDITIONS.md) a decision (D-16) explicitly designates for v2 overwrite"

key-files:
  created:
    - trader/backtest/sweep_v2.py
    - trader/backtest/run_tune_sweep_all_v2.py
    - trader/backtest/run_oos_validation_all_v2.py
    - trader/backtest/sweep_report_v2.py
    - trader/backtest/write_kill_conditions_v2.py
    - tests/test_sweep_engine_v2.py
    - tests/test_run_tune_sweep_all_v2.py
    - tests/test_oos_validation_v2.py
    - tests/test_kill_conditions_v2.py
  modified:
    - .planning/phases/03-strategy-lab/KILL-CONDITIONS.md

key-decisions:
  - "Checkpoint atomicity implemented as a full-file temp+os.replace rewrite (not append-only) on every unit completion — with only 36 units total this is cheap and gives a stronger crash-safety guarantee than an append-only log, at the cost of O(n) rewrite per unit (negligible for n=36)"
  - "Orphan-row cleanup (T-03-26 hardening) scans backtest_runs by strategy_id and filters by params_json provenance (sweep_id/bucket/regime/entry_variant) in Python rather than relying on sqlite's JSON1 extension, so it works regardless of the sqlite build's compiled-in extensions"
  - "write_kill_conditions_v2.build_kill_conditions_text is a new, small formatting function (not a direct call into v1's build_kill_conditions_text) so v2's document preamble can note D-16 provenance and each survivor entry can carry its entry_variant field, while every numeric constant/helper (PF_FLOOR, MAX_DD_FLOOR, MAX_DD_MULTIPLIER, CONSECUTIVE_LOSS_KILL, _max_drawdown_trigger, NOTHING_SURVIVED_SENTENCE) is imported from v1's write_kill_conditions.py verbatim, never redefined"

patterns-established:
  - "Long-running (multi-hour) sweep drivers launch as detached OS processes (Windows: Start-Process with redirected stdout/stderr) so the executing agent can checkpoint and return control without blocking on the run"

requirements-completed: [STRAT-03, STRAT-04, STRAT-05, STRAT-06]

# Metrics
duration: 63min (12min build+test, ~40min real detached sweep, ~11min OOS validation + report regeneration)
completed: 2026-07-26
---

# Phase 3 Plan 08: v2 Sweep/OOS/Report Cycle Summary

**Ran the real, checkpoint-resumable v2 tune sweep (exactly 10,800 runs across 2 strategies x 3 entry variants x 12 bucket/regime combos), validated all 25 real top-5 candidates OOS, and regenerated KILL-CONDITIONS.md with 5 real survivors — all momentum/stock/choppy_v2/loose.**

## Performance

- **Duration:** ~63 min total (build+test 21:52-22:04, detached real sweep 22:05-22:45 — far faster than the 4-5h pre-registered estimate since all history was already cached and the machine is fast — then OOS validation + report regeneration 22:45-22:56)
- **Started:** 2026-07-26T09:52:36Z (UTC, first TDD commit)
- **Completed:** 2026-07-26T10:56:00Z (UTC)
- **Tasks:** 3 (build) + real-run execution (Task 2's real launch/completion, Task 3's real regeneration)
- **Files modified:** 9 new source/test files + 1 regenerated tracked artifact (KILL-CONDITIONS.md)

## Accomplishments
- `sweep_v2.py`: variant-aware tune-sweep + OOS engine, hash-gated by `frozen_config_v2.verify_frozen_v2()`, reusing `sweep._slice_bars`/`select_top5`/`determine_survivor` unchanged (D-15) — proven via 9 fixture tests including hash-tamper zero-call-count proofs for both entrypoints.
- `run_tune_sweep_all_v2.py`: checkpoint-resumable real driver. **The real ~10,800-run sweep was launched as a detached process and completed successfully**: checkpoint reached all 36 (strategy, bucket, regime, variant) units, `tune_top5_v2.json` written, and `count_tune_sweep_runs_v2(conn)` confirms **exactly 10,800** `backtest_runs` rows with `sweep_id="v2", split="tune"` — matching D-14's pre-registered estimate exactly.
- Checker-mandated hardening implemented and test-proven: checkpoint file rewritten atomically (temp file + `os.replace`) per completed unit; `_read_checkpoint` silently skips a malformed trailing line; `_cleanup_orphan_rows` deletes any `backtest_runs`/`backtest_trades` rows from an interrupted prior attempt at a unit before that unit is retried (fixture-proven via a simulated-interrupt test).
- `run_oos_validation_all_v2.py`: real OOS validation run over all 25 real top-5 candidates, resolving each candidate's entry-variant via `momentum_v2.MOMENTUM_VARIANTS`/`breakout_v2.BREAKOUT_VARIANTS`, writing the full 25-entry verdict list (never only survivors, D-12) to `oos_results_v2.json`.
- `write_kill_conditions_v2.py` + `sweep_report_v2.py`: real regeneration of `.planning/phases/03-strategy-lab/KILL-CONDITIONS.md` from v2's real `oos_results_v2.json` (D-16) — **5 real survivors**, each with the 3 pre-registered numeric kill triggers computed from that survivor's own real OOS metrics; `reports/backtests/2026-07-26-survivors-v2.md` and 25 per-config `*-run{run_id}-sweep.md` reports written; every pre-existing v1 report file, `tune_top5.json`, and `oos_results.json` confirmed byte-unmodified (mtimes predate this session).

## Real v2 Tune-Sweep Candidate Summary (25 total, from `tune_top5_v2.json`)

| Breakdown | Counts |
|---|---|
| By base strategy | momentum: 20, breakout: **5** (breakout DID produce candidates this run) |
| By bucket | stock: 15, crypto_major_legacy_meme: 5, new_memecoin: 5 |
| By regime | trending_v2: 15, choppy_v2: 5, mania_recovery_v2: 5 |
| By entry_variant | base: 2, loose: 23 (strict never appears — no strict-variant cell cleared the 30-trade floor anywhere) |

Of the 12 possible (strategy, bucket, regime) groups, **5 produced candidates** (all 5 reaching the max of 5 candidates each):
`breakout/stock/trending_v2`, `momentum/crypto_major_legacy_meme/trending_v2`, `momentum/new_memecoin/mania_recovery_v2`, `momentum/stock/choppy_v2`, `momentum/stock/trending_v2`.

The other 7 groups produced zero candidates (every cell across all 3 variants fell below `select_top5`'s 30-trade minimum): `breakout/crypto_major_legacy_meme/{trending_v2,bear_recovery_v2}`, `breakout/new_memecoin/{mania_recovery_v2,current_v2}`, `breakout/stock/choppy_v2`, `momentum/crypto_major_legacy_meme/bear_recovery_v2`, `momentum/new_memecoin/current_v2`.

## Real v2 OOS Verdict Table (25 total, from `oos_results_v2.json`)

**Verdict counts: 5 survivor / 8 killed / 12 insufficient_sample.**

| strategy_id | bucket | regime | variant | OOS profit_factor | OOS trades | verdict |
|---|---|---|---|---|---|---|
| momentum_stock | stock | choppy_v2 | loose | 20.434 | 32 | **survivor** |
| momentum_stock | stock | choppy_v2 | loose | 12.237 | 33 | **survivor** |
| momentum_stock | stock | choppy_v2 | loose | 2.543 | 85 | **survivor** |
| momentum_stock | stock | choppy_v2 | loose | 2.449 | 85 | **survivor** |
| momentum_stock | stock | choppy_v2 | loose | 2.348 | 85 | **survivor** |
| momentum_crypto_major_legacy_meme | crypto_major_legacy_meme | trending_v2 | loose | 0.987 | 35 | killed |
| momentum_crypto_major_legacy_meme | crypto_major_legacy_meme | trending_v2 | loose | 0.902 | 35 | killed |
| momentum_crypto_major_legacy_meme | crypto_major_legacy_meme | trending_v2 | loose | 0.782 | 37 | killed |
| momentum_crypto_major_legacy_meme | crypto_major_legacy_meme | trending_v2 | loose | 0.872 | 39 | killed |
| momentum_crypto_major_legacy_meme | crypto_major_legacy_meme | trending_v2 | loose | 0.808 | 39 | killed |
| momentum_stock | stock | trending_v2 | loose | 0.958 | 39 | killed |
| momentum_stock | stock | trending_v2 | loose | 0.971 | 39 | killed |
| momentum_stock | stock | trending_v2 | loose | 0.957 | 39 | killed |
| breakout_stock | stock | trending_v2 | loose | 0.662 | 11 | insufficient_sample |
| breakout_stock | stock | trending_v2 | loose | 0.000 | 10 | insufficient_sample |
| breakout_stock | stock | trending_v2 | loose | 1.326 | 9 | insufficient_sample |
| breakout_stock | stock | trending_v2 | loose | 0.000 | 10 | insufficient_sample |
| breakout_stock | stock | trending_v2 | loose | 0.752 | 10 | insufficient_sample |
| momentum_new_memecoin | new_memecoin | mania_recovery_v2 | loose | 1.143 | 14 | insufficient_sample |
| momentum_new_memecoin | new_memecoin | mania_recovery_v2 | loose | 1.205 | 14 | insufficient_sample |
| momentum_new_memecoin | new_memecoin | mania_recovery_v2 | loose | 1.205 | 14 | insufficient_sample |
| momentum_new_memecoin | new_memecoin | mania_recovery_v2 | loose | 1.143 | 14 | insufficient_sample |
| momentum_new_memecoin | new_memecoin | mania_recovery_v2 | loose | 1.532 | 13 | insufficient_sample |
| momentum_stock | stock | trending_v2 | base | 0.378 | 14 | insufficient_sample |
| momentum_stock | stock | trending_v2 | base | 2.481 | 7 | insufficient_sample |

All 5 survivors are `momentum_stock` in the `choppy_v2` regime under the `loose` entry variant, with strong OOS profit factors (2.3-20.4x) and adequate trade counts (32-85). `KILL-CONDITIONS.md` now lists these 5 survivors' exit profiles with their pre-registered numeric kill triggers (rolling-30-trade PF floor 0.9, max-drawdown kill level computed per-survivor via `1.5x` the observed OOS drawdown floored at -15%, consecutive-loss kill count 8).

## Task Commits

Each task followed RED -> GREEN TDD and was committed atomically:

1. **Task 1: sweep_v2.py variant-aware tune-sweep + OOS engine**
   - `f144bce` test(03-08): add failing test for sweep_v2 variant-aware engine
   - `639e69e` feat(03-08): add sweep_v2 variant-aware tune-sweep + OOS engine
2. **Task 2: Checkpoint-resumable v2 drivers (build) + real 10,800-run launch/completion**
   - `f31bc5a` test(03-08): add failing test for v2 checkpoint-resumable drivers
   - `07649a8` feat(03-08): add checkpoint-resumable v2 tune-sweep + OOS drivers
   - Real run: launched as a detached process; completed cleanly (checkpoint reached 36/36 units, `tune_top5_v2.json` written, exact 10,800-row DB count confirmed) — no code commit for this step (it produces gitignored `reports/backtests/*` data artifacts only)
3. **Task 3: v2 kill-conditions regeneration + survivors-v2 index (build) + real regeneration**
   - `2b74f5d` test(03-08): add failing test for v2 kill-conditions regeneration
   - `9b964c6` feat(03-08): add v2 kill-conditions regeneration + survivors-v2 index
   - Real run: `run_oos_validation_all_v2.main()` and `write_kill_conditions_v2.main()` executed for real, producing `oos_results_v2.json` and regenerating the tracked `.planning/phases/03-strategy-lab/KILL-CONDITIONS.md`

**Plan metadata:** (this commit, following SUMMARY.md write)

## Files Created/Modified
- `trader/backtest/sweep_v2.py` - variant-aware `run_tune_sweep_v2`/`run_oos_validation_v2`, hash-gated by `frozen_config_v2`, reusing v1's `_slice_bars`/`select_top5`/`determine_survivor` unchanged
- `trader/backtest/run_tune_sweep_all_v2.py` - checkpoint-resumable real driver; `EXPECTED_TUNE_SWEEP_RUN_COUNT_V2 = 10_800`, `count_tune_sweep_runs_v2`, atomic checkpoint write, orphan-row cleanup
- `trader/backtest/run_oos_validation_all_v2.py` - real OOS validation driver, resolves entry_variant via momentum_v2/breakout_v2 registries
- `trader/backtest/sweep_report_v2.py` - `write_survivors_index_v2` (distinctly `-v2`-suffixed filename)
- `trader/backtest/write_kill_conditions_v2.py` - `build_kill_conditions_text`, `main()` (v2's own hash-gated terminal gate)
- `tests/test_sweep_engine_v2.py` - 9 tests: hash gates (both entrypoints), 6-key provenance round-trip, `_slice_bars`/`select_top5`/`determine_survivor` reuse identity, `regimes_v2`-only regime lookup
- `tests/test_run_tune_sweep_all_v2.py` - 8 tests: end-to-end fixture wiring, checkpoint-resume skip proof, orphan-cleanup simulated-interrupt proof, checkpoint atomicity, malformed-line skip, real-grid arithmetic self-check (10,800)
- `tests/test_oos_validation_v2.py` - 2 tests: variant resolution + full verdict-list wiring, `_base_strategy_id` suffix-stripping
- `tests/test_kill_conditions_v2.py` - 7 tests: hash gate, constant/helper reuse identity, both formatting branches, distinctly-named survivors-v2 index (never colliding with v1's)
- `.planning/phases/03-strategy-lab/KILL-CONDITIONS.md` - regenerated from v2's real 25-candidate OOS results (5 survivors, D-16)

## Decisions Made
- Checkpoint file rewritten in full (temp+`os.replace`) per unit rather than append-only, for stronger crash-safety at negligible cost given only 36 units.
- Orphan-row cleanup implemented as a Python-side scan/filter over `params_json` rather than sqlite JSON1 `json_extract`, for portability across sqlite builds.
- `write_kill_conditions_v2.build_kill_conditions_text` is a new function (not a direct call into v1's), so the v2 document can note D-16 provenance and each survivor entry can show its `entry_variant`, while every numeric constant and the `_max_drawdown_trigger` helper are imported from v1's module verbatim (identity-checked in tests) so the two can never drift.

## Deviations from Plan

### Auto-fixed Issues

None required during Tasks 1-3's build (fixture TDD proceeded exactly as planned) or during the real run (10,800/10,800 units completed cleanly, no crash, no orphan-cleanup path exercised for real — only fixture-proven).

### Known, Expected Test Regression (not a v2 defect — documented, not auto-fixed)

**`tests/test_kill_conditions.py::test_real_kill_conditions_file_matches_real_oos_results_survivor_list` now fails.**

- **Cause:** This v1 test (Plan 03-06, commit `54f191f`) cross-checks the real, committed `.planning/phases/03-strategy-lab/KILL-CONDITIONS.md` 1:1 against v1's own `reports/backtests/oos_results.json` survivor list (which was 0 survivors / 15 insufficient_sample). D-16 explicitly designates `KILL-CONDITIONS.md` as the ONE file this plan (03-08) overwrites with v2's real results — this is the plan's stated, intended outcome (see Task 3's `<done>` criterion and the threat model's T-03-28 disposition), not a side effect. The moment `write_kill_conditions_v2.main()` regenerates the file from v2's 5 real survivors, v1's own real-artifact cross-check test — which hardcodes the assumption that the file still reflects v1's oos_results.json — necessarily stops passing.
- **Why not auto-fixed:** This session's explicit instructions state "Do NOT modify any v1 file or tests/conftest.py." `tests/test_kill_conditions.py` is a v1 test file (created in Plan 03-06, not in this plan's `files_modified` list), so it was left untouched rather than edited to reflect v2's results.
- **Verification:** Full suite run with this single expected failure isolated and confirmed to be exactly this one, pre-existing, now-obsolete assertion — no other regression, and no v2-introduced bug.
- **Recommendation for a future plan/decision:** Either retire/update this specific v1 test (it can no longer be satisfied once any v2/v3 iteration supersedes v1's KILL-CONDITIONS.md by design) or scope it to run only against a frozen v1-era snapshot rather than the live file.

---

**Total deviations:** 0 auto-fixed; 1 documented known test regression (expected consequence of D-16, not a code defect).
**Impact on plan:** No scope creep, no v1 file modified. The one failing test's premise is inherently incompatible with D-16's designated behavior and was already implicitly superseded the moment Plan 03-08 was written.

## Issues Encountered
- The real ~10,800-run sweep completed in ~40 minutes wall-clock, well under the 4-5h pre-registered D-14 estimate — likely because all required bar history was already fully cached (`data/trader.db`, no network fetches) and the sweep ran on capable hardware. No other issues.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `reports/backtests/tune_top5_v2.json` (25 real candidates) and `reports/backtests/oos_results_v2.json` (25 real verdicts, 5 survivors) are committed to disk (gitignored data artifacts, per this repo's `reports/` convention matching v1).
- `.planning/phases/03-strategy-lab/KILL-CONDITIONS.md` reflects v2's honest, real outcome: 5 concrete survivors (all `momentum_stock`/`choppy_v2`/`loose`) with pre-registered numeric kill triggers — ready for Phase 4's paper-trading candidate selection.
- Full test suite: 346 passed / 347 total (1 known, expected, pre-existing-test-obsolescence failure documented above — not a regression introduced by this plan's code).
- No blockers for Phase 4. One recommendation carried forward: retire or rescope `tests/test_kill_conditions.py`'s real-artifact cross-check now that D-16's designed KILL-CONDITIONS.md supersession has occurred.

## Self-Check: PASSED

- FOUND: trader/backtest/sweep_v2.py
- FOUND: trader/backtest/run_tune_sweep_all_v2.py
- FOUND: trader/backtest/run_oos_validation_all_v2.py
- FOUND: trader/backtest/sweep_report_v2.py
- FOUND: trader/backtest/write_kill_conditions_v2.py
- FOUND: tests/test_sweep_engine_v2.py
- FOUND: tests/test_run_tune_sweep_all_v2.py
- FOUND: tests/test_oos_validation_v2.py
- FOUND: tests/test_kill_conditions_v2.py
- FOUND: reports/backtests/tune_top5_v2.json (25 candidates)
- FOUND: reports/backtests/oos_results_v2.json (25 verdicts, 5 survivors)
- FOUND: .planning/phases/03-strategy-lab/KILL-CONDITIONS.md (regenerated, 5 survivor entries)
- FOUND commits f144bce, 639e69e, f31bc5a, 07649a8, 2b74f5d, 9b964c6 in `git log --oneline`
- CONFIRMED: `count_tune_sweep_runs_v2(conn) == 10_800` (exact)
- Full suite: 346 passed, 1 known/expected failure (documented above), 0 unexplained regressions

---
*Phase: 03-strategy-lab*
*Completed: 2026-07-26*
