---
phase: 02-backtest-harness
plan: 01
subsystem: backtest
tags: [sqlite, dataclasses, migrations, fees, slippage, exit-profiles]

# Dependency graph
requires:
  - phase: 01-accounts-data-plumbing
    provides: "trader/data/db.py migration mechanism (apply_migrations), instruments.asset_class CHECK values (stock/crypto_major/memecoin)"
provides:
  - "trader/backtest/config.py: FEE_TABLE, SLIPPAGE_PCT, SLIPPAGE_SMALL_CAP_RUNNER, DEFAULT_NOTIONAL, EXIT_PROFILE (frozen dataclass), PROFILE_TIME_STOP_1D, PROFILE_MOMENTUM_PLACEHOLDER"
  - "migrations/0003_backtest.sql: backtest_runs and backtest_trades tables with CHECK constraints and indices, schema_version=3"
affects: [02-02, 02-03, 02-04, 02-05, 02-06, 02-07, 02-08, 02-09, 02-10]

# Tech tracking
tech-stack:
  added: []
  patterns: ["frozen dataclass + __post_init__ type rejection for standing-rule-2 immutability", "RED-phase-safe try/except ImportError test imports", "migration-runner-compatible ordered *.sql files"]

key-files:
  created:
    - trader/backtest/__init__.py
    - trader/backtest/config.py
    - migrations/0003_backtest.sql
    - tests/test_backtest_config.py
    - tests/test_backtest_migration.py
  modified:
    - tests/test_data_db.py

key-decisions:
  - "EXIT_PROFILE rejects (raises TypeError) a non-tuple scale_out in __post_init__ rather than silently coercing a list, per standing rule 2"
  - "SLIPPAGE_PCT crypto_major locked at 0.10% (orchestrator revision), kept distinct from the unwired SLIPPAGE_SMALL_CAP_RUNNER=2.0 Phase 3 hook"
  - "backtest_trades is one row per fill (entry, scale-out tranche, or final exit), sharing position_id for multi-tranche positions, per 02-RESEARCH.md's resolved open question"

patterns-established:
  - "Config constants module: pure in-process values, no I/O, documented rationale inline for numeric choices that could otherwise look arbitrary"
  - "Immutability enforced by frozen dataclass + explicit type check on mutable-typed fields, not just @dataclass(frozen=True) alone"

requirements-completed: [BACK-02, BACK-03, BACK-04]

# Metrics
duration: ~15min
completed: 2026-07-26
---

# Phase 2 Plan 1: Backtest Config and Schema Foundation Summary

**Fee/slippage/exit-profile config module plus backtest_runs/backtest_trades migration, both TDD-proven, giving Wave 2-3 modules a fixed contract to build against.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-26T04:41:28Z
- **Tasks:** 2 completed
- **Files modified:** 6 (5 created, 1 modified)

## Accomplishments
- `trader/backtest/config.py` exports FEE_TABLE (D-06/D-07), SLIPPAGE_PCT with the orchestrator-revised crypto_major=0.10% mapping, the unwired SLIPPAGE_SMALL_CAP_RUNNER=2.0 Phase 3 hook, DEFAULT_NOTIONAL, and a frozen EXIT_PROFILE dataclass whose immutability (including scale_out's tuple-only contract) is proven by a failing-mutation test, not asserted by comment
- `migrations/0003_backtest.sql` adds backtest_runs/backtest_trades with CHECK constraints on asset_class and exit_reason, applied through the existing filename-prefix migration runner (schema_version reaches 3)
- Full 71-test suite green with no regressions beyond one deliberately relaxed pre-existing assertion (see Deviations)

## Task Commits

Each task was committed atomically (TDD RED -> GREEN):

1. **Task 1: Fee/slippage/exit-profile config module** - `83f620e` (test), `f97ac24` (feat)
2. **Task 2: backtest_runs/backtest_trades migration** - `6d755ba` (test), `b3ed4d6` (feat, includes the test_data_db.py fix)

_TDD tasks produced two commits each (test -> feat); no refactor commit was needed._

## Files Created/Modified
- `trader/backtest/__init__.py` - empty package marker
- `trader/backtest/config.py` - FEE_TABLE, SLIPPAGE_PCT, SLIPPAGE_SMALL_CAP_RUNNER, DEFAULT_NOTIONAL, EXIT_PROFILE, PROFILE_TIME_STOP_1D, PROFILE_MOMENTUM_PLACEHOLDER
- `migrations/0003_backtest.sql` - backtest_runs/backtest_trades DDL, CHECK constraints, indices
- `tests/test_backtest_config.py` - 11 tests covering every behavior item in the plan
- `tests/test_backtest_migration.py` - 7 tests covering schema_version, columns, and CHECK-constraint IntegrityErrors
- `tests/test_data_db.py` - relaxed a hardcoded `max_version == 2` assertion to `>= 2` (see Deviations)

## Decisions Made
- Chose rejection over coercion for EXIT_PROFILE.scale_out: a list input raises TypeError in `__post_init__` instead of being silently converted to a tuple, so a caller violating the immutability contract gets an immediate, loud signal
- PROFILE_MOMENTUM_PLACEHOLDER values (stop_pct=-0.10, tp_pct=0.20, max_hold_days=30) are Claude's-discretion placeholders per the plan, not tuned strategy parameters
- backtest_trades follows the "one row per fill" schema resolution already locked in 02-RESEARCH.md's Open Question 2, applied here at the DDL level

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Relaxed test_data_db.py's hardcoded schema_version assertion**
- **Found during:** Task 2 (backtest_runs/backtest_trades migration)
- **Issue:** `test_migration_0002_creates_instruments_and_bars` asserted `max_version == 2`. Adding `migrations/0003_backtest.sql` makes `apply_migrations` (which globs and applies every `migrations/*.sql` file, by design) bring every fresh connection to `schema_version` 3, breaking this pre-existing assertion — a direct, foreseeable consequence of this task's own migration file, not a pre-existing unrelated failure.
- **Fix:** Changed the assertion from `== 2` to `>= 2`, preserving the test's original intent (0002's tables/columns exist) without hardcoding a total migration count that will keep changing as later phases add more migrations.
- **Files modified:** tests/test_data_db.py
- **Verification:** `pytest tests/ -q` — 71 passed, 0 failed
- **Committed in:** b3ed4d6 (part of Task 2's feat commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Necessary correctness fix directly caused by this plan's own migration; no scope creep beyond the one assertion.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `trader.backtest.config` is import-ready for plans 02-04 (fills.py) and 02-05 (exits.py)
- `migrations/0003_backtest.sql` is apply-ready for plan 02-06 (ledger.py)
- No blockers for Wave 2

---
*Phase: 02-backtest-harness*
*Completed: 2026-07-26*

## Self-Check: PASSED

All created files verified present on disk; all task/summary commit hashes (83f620e, f97ac24, 6d755ba, b3ed4d6) verified in git log.
