---
phase: 04-risk-gate-sizer
plan: 01
subsystem: risk
tags: [sqlite, migrations, config, pytest]

# Dependency graph
requires:
  - phase: 02-backtest-harness
    provides: "trader/backtest/config.py's SLIPPAGE_PCT (reused as MAX_SPREAD_PCT proxy)"
  - phase: 01-data-foundation
    provides: "trader/data/db.py's apply_migrations/get_connection migration mechanism"
provides:
  - "trader/risk/config.py -- every RISK-01/02/03 pinned threshold as a named constant"
  - "migrations/0004_risk_breakers.sql -- breaker_events append-only log + breaker_state_current view"
  - "tests/test_risk_config.py, tests/test_risk_migration.py -- contract regression tests"
affects: [04-02-risk-gate, 04-03-position-sizer, 04-04-circuit-breakers]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Frozen-style config module (named module-level constants, no inline magic numbers) mirroring trader/backtest/config.py"
    - "Event-log + latest-row view for re-derivable state (breaker_state_current), never a mutable cached column"

key-files:
  created:
    - trader/risk/__init__.py
    - trader/risk/config.py
    - migrations/0004_risk_breakers.sql
    - tests/test_risk_config.py
    - tests/test_risk_migration.py
  modified:
    - tests/test_backtest_migration.py
    - .planning/phases/04-risk-gate-sizer/04-RESEARCH.md

key-decisions:
  - "MAX_SPREAD_PCT = dict(SLIPPAGE_PCT) imported from trader.backtest.config, not retyped as new literals -- single source of truth for the spread-ceiling proxy"
  - "breaker_events is an append-only event log with a breaker_state_current view resolving MAX(event_id) per breaker_type, not a mutable single-row table -- keeps state re-derivable per standing rule 4"

patterns-established:
  - "Every numeric threshold for Phase 4's gate/sizer/breakers lives in trader/risk/config.py; downstream plans (04-02/03/04) import constants by name, never re-derive or inline them"

requirements-completed: [RISK-01, RISK-02, RISK-03]

# Metrics
duration: 15min
completed: 2026-07-26
---

# Phase 4 Plan 01: Frozen Risk Config + Breaker Migration Summary

**trader/risk/config.py pins all 16 gate/sizer/breaker thresholds from 04-RESEARCH.md as named constants, and migrations/0004_risk_breakers.sql adds an append-only breaker_events log with a breaker_state_current view that re-derives current state from the latest event per breaker_type.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-26T10:14:07Z
- **Tasks:** 2 completed
- **Files modified:** 7 (5 created, 2 modified)

## Accomplishments
- `trader/risk/config.py` created with all 16 frontmatter-listed exports at their exact researched values, including `MAX_SPREAD_PCT` reused directly from `trader.backtest.config.SLIPPAGE_PCT`
- `migrations/0004_risk_breakers.sql` created: `breaker_events` append-only table (three CHECK constraints on `breaker_type`/`action`/`actor`) plus `breaker_state_current` view resolving each type's latest event by `MAX(event_id)`
- Full 295-test suite green after the change (was 294 before this plan's tests were added, then +19 +10 new tests, -1 obsolete cross-plan test count assumption fixed)

## Task Commits

Each task was committed atomically:

1. **Task 1: trader/risk/config.py -- frozen threshold constants** - `4c530c2` (feat)
2. **Task 2: migrations/0004_risk_breakers.sql -- append-only event log + current-state view** - `717d70c` (feat)
3. **Deviation fix: test_backtest_migration.py schema_version assumption** - `ce3ada0` (fix)

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified
- `trader/risk/__init__.py` - package marker with one-line docstring
- `trader/risk/config.py` - frozen threshold constants for the gate, sizer, and breakers (RISK-01/02/03)
- `migrations/0004_risk_breakers.sql` - breaker_events table + breaker_state_current view
- `tests/test_risk_config.py` - one test per constant + export-completeness check
- `tests/test_risk_migration.py` - schema/CHECK-constraint/view-resolution tests
- `tests/test_backtest_migration.py` - fixed a schema_version assumption broken by adding migration 0004
- `.planning/phases/04-risk-gate-sizer/04-RESEARCH.md` - Open Questions marked RESOLVED with inline markers (checker warning W1)

## Decisions Made
- Reused `trader.backtest.config.SLIPPAGE_PCT` as `MAX_SPREAD_PCT` verbatim (import, not retype) per 04-RESEARCH.md Open Question 3, now resolved.
- Breaker state persists as an append-only event log with a computed current-state view, never a mutable single row, per D-05/standing rule 4.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_backtest_migration.py's schema_version==3 assumption**
- **Found during:** Post-task full suite run
- **Issue:** `test_migration_0003_reaches_schema_version_3` asserted `MAX(version) == 3`, which broke the instant migration 0004 existed, since a fresh DB's `apply_migrations()` applies every migration file present, not just 0003.
- **Fix:** Changed the assertion to check that version 3 is among the applied versions, rather than asserting it is the maximum -- preserves the test's real contract (0003 applied cleanly) without coupling it to total migration count.
- **Files modified:** `tests/test_backtest_migration.py`
- **Verification:** Full suite re-run, 295 passed.
- **Committed in:** `ce3ada0`

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary fix for correctness; a pre-existing test's implicit assumption about migration count could not survive adding migration 0004. No scope creep.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `trader/risk/config.py` and `migrations/0004_risk_breakers.sql` exist as committed, tested contracts.
- Plans 04-02 (gate), 04-03 (sizer), and 04-04 (breakers) can import these constants and the breaker schema directly -- no re-derived thresholds, no duplicated DDL.
- Full suite green at 295 tests.

## Self-Check: PASSED

All created files verified present on disk; all three task/deviation commit hashes (`4c530c2`, `717d70c`, `ce3ada0`) verified present in git log.

---
*Phase: 04-risk-gate-sizer*
*Completed: 2026-07-26*
