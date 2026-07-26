---
phase: 03-strategy-lab
plan: 07
subsystem: backtest
tags: [backtest, regimes, momentum, breakout, hash-gate, frozen-config, tdd]

# Dependency graph
requires:
  - phase: 03-strategy-lab (03-01, 03-02)
    provides: v1's Regime dataclass, universe buckets, exit_grid, momentum.py/breakout.py signal logic, frozen_config.py hashing pattern
provides:
  - regimes_v2.REGIMES_V2 -- 6 frozen v2 regime windows, OOS >= 12mo every bucket, tune_end < oos_start
  - momentum_v2.MOMENTUM_VARIANTS / make_pick_entries -- 3 pinned momentum entry-strictness variants, "base" == v1 exactly
  - breakout_v2.BREAKOUT_VARIANTS / make_pick_entries -- 3 pinned breakout entry-strictness variants, "base" == v1 exactly
  - frozen_config_v2.verify_frozen_v2/compute_hash_v2/FROZEN_HASH_V2 -- independent v2 hash gate over 5 frozen files
affects: [03-08 (v2 sweep/OOS execution)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "v2 config-only plans: reuse v1 classes/contracts (Regime, pick_entries signature), never import v1 modules where self-containment is required, verbatim-duplicate signal logic instead"
    - "Independent hash-gate modules per iteration (frozen_config.py / frozen_config_v2.py) rather than a shared/parameterized gate"

key-files:
  created:
    - trader/backtest/regimes_v2.py
    - trader/backtest/strategies/momentum_v2.py
    - trader/backtest/strategies/breakout_v2.py
    - trader/backtest/frozen_config_v2.py
    - tests/test_regime_config_v2.py
    - tests/test_entry_variants_v2.py
    - tests/test_frozen_config_v2.py
  modified: []

key-decisions:
  - "Fixed a 1-day arithmetic shortfall in the plan's literal new_memecoin OOS end dates (2025-12-31 and 2026-06-30 both yielded 364-day windows, one day under the 365-day floor); extended both to 2026-01-01 and 2026-07-01 respectively so the OOS window is a full calendar year, satisfying the plan's own acceptance criteria"
  - "Used the checker-corrected fixture (test_momentum_fires_on_rsi_volume_surge_and_breakout's RISER fixture) for the base-variant momentum parity proof, since the plan's cited test name does not exist"
  - "Entry-variant closures reimplement v1's signal logic verbatim rather than importing momentum.py/breakout.py, to satisfy the self-containment requirement (grep-verified in tests)"

patterns-established:
  - "v2 iteration modules (*_v2.py) live alongside v1 modules, never replace or modify them; a new, independent frozen_config_v2.py hash-gates only the v2 surface"

requirements-completed: [STRAT-03, STRAT-04, STRAT-05]

# Metrics
duration: 24min
completed: 2026-07-26
---

# Phase 3 Plan 07: v2 Frozen Config (regimes_v2, entry variants, frozen_config_v2) Summary

**Froze v2's 12-month-plus OOS regime windows and a 3-variant momentum/breakout entry-strictness registry behind a new, independent hash gate, with zero modification to any v1 file.**

## Performance

- **Duration:** 24 min
- **Started:** 2026-07-26T09:23:00Z
- **Completed:** 2026-07-26T09:47:14Z
- **Tasks:** 3
- **Files modified:** 7 (4 new source modules, 3 new test files)

## Accomplishments
- `regimes_v2.REGIMES_V2`: 6 frozen v2 regime windows (2 per bucket), every OOS window verified >= 365 days via real date arithmetic, every `tune_end < oos_start`, reusing v1's own `Regime` dataclass
- `momentum_v2`/`breakout_v2`: 3 pinned entry-strictness variants each (strict/base/loose); "base" proven byte-for-byte identical to v1's real `pick_entries` output on v1's own fixtures; neither module imports v1's strategy modules (grep-verified)
- `frozen_config_v2.py`: independent hash gate over the 5-file v2 frozen surface (universe.py, regimes_v2.py, exit_grid.py, momentum_v2.py, breakout_v2.py), with a tamper test proving `verify_frozen_v2()` raises `RuntimeError` on any byte-level change, and proven independent of v1's own `frozen_config.py` gate

## Task Commits

Each task followed RED -> GREEN TDD and was committed atomically:

1. **Task 1: Frozen v2 regime windows (D-13)**
   - `879d04b` test(03-07): add failing test for regimes_v2 (D-13 frozen windows)
   - `944563d` feat(03-07): freeze v2 regime windows with 12mo+ OOS (D-13)
2. **Task 2: Entry-variant registry (D-14)**
   - `bfcaf49` test(03-07): add failing test for momentum_v2/breakout_v2 entry variants (D-14)
   - `485a7b7` feat(03-07): add v2 momentum/breakout entry-variant registry (D-14)
3. **Task 3: v2 hash-based freeze gate**
   - `0baa197` test(03-07): add failing test for frozen_config_v2 hash gate (T-03-21)
   - `24be88f` feat(03-07): add v2 hash-based freeze gate (T-03-21)

**Plan metadata:** (this commit, following SUMMARY.md write)

## Files Created/Modified
- `trader/backtest/regimes_v2.py` - 6 frozen v2 Regime instances (stock/crypto_major_legacy_meme/new_memecoin x 2), OOS >= 12mo everywhere
- `trader/backtest/strategies/momentum_v2.py` - `MomentumVariant`, `MOMENTUM_VARIANTS` (strict/base/loose), `make_pick_entries` factory, self-contained RSI-Wilder reimplementation
- `trader/backtest/strategies/breakout_v2.py` - `BreakoutVariant`, `BREAKOUT_VARIANTS` (strict/base/loose), `make_pick_entries` factory, self-contained NR-window reimplementation
- `trader/backtest/frozen_config_v2.py` - `FROZEN_FILES_V2`, `compute_hash_v2`, `FROZEN_HASH_V2`, `verify_frozen_v2`
- `tests/test_regime_config_v2.py` - 8 tests: entry count/bucket split, Regime reuse, immutability, tune/OOS ordering, 365-day floor, null tune_start, exact window dates, v1 non-regression
- `tests/test_entry_variants_v2.py` - 12 tests: variant registry shape/values, base-variant v1 parity (momentum + breakout), monotonic strict-vs-loose fixtures, no-v1-import self-containment, signature contract
- `tests/test_frozen_config_v2.py` - 5 tests: hash self-consistency, unmodified-repo pass, exact FROZEN_FILES_V2 order, byte-level tamper detection, independence from v1's frozen_config gate

## Decisions Made
- Corrected a 1-day-short OOS window on both new_memecoin v2 regimes (plan's literal `2025-12-31`/`2026-06-30` end dates each produced a 364-day window, failing the plan's own >=365-day acceptance criterion by exactly one day); extended `oos_end` to `2026-01-01` and `2026-07-01` respectively so both clear the 12-month floor exactly. This is a Rule 1 (auto-fix bug) correction: the plan's stated behavior ("every OOS window >= 365 days") and its literal example dates were internally inconsistent, and the behavior spec (a testable acceptance criterion) takes precedence over the illustrative dates.
- Used `test_momentum_fires_on_rsi_volume_surge_and_breakout`'s RISER fixture (per the objective's checker correction) as the base-variant momentum parity proof input, since the plan's cited fixture name (`test_momentum_signals_on_rising_fixture`) does not exist in the repo.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a 1-day OOS-window shortfall in both new_memecoin v2 regimes**
- **Found during:** Task 1 (regime window authoring, before writing the test's exact-date assertions)
- **Issue:** The plan's literal dates for `mania_recovery_v2` (`oos_start=2025-01-01`, `oos_end=2025-12-31`) and `current_v2` (`oos_start=2025-07-01`, `oos_end=2026-06-30`) each compute to a 364-day OOS window under real date arithmetic (`date.fromisoformat(oos_end) - date.fromisoformat(oos_start)`), one day short of the plan's own "every OOS window >= 365 days" acceptance criterion.
- **Fix:** Extended `oos_end` to `2026-01-01` (mania_recovery_v2) and `2026-07-01` (current_v2), giving each a full 365-day calendar-year OOS window. Both dates remain safely in the past relative to the project's current date (2026-07-26) and within the existing v1 backfill cache per the plan's own assumption.
- **Files modified:** `trader/backtest/regimes_v2.py`
- **Verification:** `tests/test_regime_config_v2.py::test_every_regime_v2_oos_window_is_at_least_365_days` passes for all 6 regimes; exact-date test pins the corrected values explicitly.
- **Committed in:** `944563d` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Necessary to satisfy the plan's own stated behavior/acceptance criteria (D-13's 12-month OOS floor). No scope creep -- only the two new_memecoin end dates shifted by one day each; regime count, bucket structure, and every other date are unchanged from the plan's literal specification.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `regimes_v2.REGIMES_V2`, `momentum_v2`/`breakout_v2` entry-variant registries, and `frozen_config_v2.verify_frozen_v2()` are all committed and hash-locked, ready for Plan 03-08 to drive the real v2 sweep and OOS validation.
- Full test suite: 242 passed (217 v1 baseline + 25 new v2 tests), confirming zero regression to any v1 artifact.
- No blockers.

## Self-Check: PASSED

- FOUND: trader/backtest/regimes_v2.py
- FOUND: trader/backtest/strategies/momentum_v2.py
- FOUND: trader/backtest/strategies/breakout_v2.py
- FOUND: trader/backtest/frozen_config_v2.py
- FOUND: tests/test_regime_config_v2.py
- FOUND: tests/test_entry_variants_v2.py
- FOUND: tests/test_frozen_config_v2.py
- FOUND commit 879d04b, 944563d, bfcaf49, 485a7b7, 0baa197, 24be88f in `git log --oneline`
- Full suite: 242 passed, 0 failed

---
*Phase: 03-strategy-lab*
*Completed: 2026-07-26*
