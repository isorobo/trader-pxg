---
phase: 05-paper-trading-loop
plan: 01
subsystem: database
tags: [sqlite, migrations, tdd, idempotency, paper-trading]

# Dependency graph
requires:
  - phase: 04-risk-management
    provides: trader/backtest/config.py's EXIT_PROFILE (frozen dataclass every position uses), migrations/0004_risk_breakers.sql's append-only/re-derive-state convention
  - phase: 03-strategy-lab
    provides: KILL-CONDITIONS.md's five pre-registered survivor configs and kill triggers
provides:
  - migrations/0005_paper_trading.sql (paper_orders, paper_positions, paper_trades, reconciliation_log + reconciliation_halt_state view, strategy_kill_state)
  - trader/paper/config.py (IBKR_PAPER_PORT=4002, cadences, LIVE_STRATEGY_CONFIGS -- the five live D-01 strategy configs)
  - trader/paper/idempotency.py (build_order_ref, find_existing_order, find_unresolved_match)
  - trader/paper/ledger.py (full read/write surface incl. pending_submit->submitted->filled lifecycle, scoped + unscoped unresolved-order queries)
  - tests/conftest.py's paper_conn fixture
affects: [05-02, 05-03, 05-04, 05-05, 05-06, 05-07, 05-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Append-only event log + re-derived-state view (reconciliation_log/reconciliation_halt_state) mirroring migrations/0004's breaker_events/breaker_state_current"
    - "Persist-before-submit order lifecycle: pending_submit (decided, before broker call) -> submitted (broker confirmed) -> filled (fill confirmed or healed)"
    - "Scoped vs. unscoped unresolved-order queries sharing one private status-filter helper so they cannot drift apart"

key-files:
  created:
    - migrations/0005_paper_trading.sql
    - trader/paper/__init__.py
    - trader/paper/config.py
    - trader/paper/idempotency.py
    - trader/paper/ledger.py
    - tests/test_idempotency.py
    - tests/test_paper_ledger.py
  modified:
    - tests/conftest.py
    - tests/test_risk_migration.py

key-decisions:
  - "PAPER_ACCOUNT_EQUITY=100_000.0 is Claude's discretion per the plan, matching trader/backtest/config.py's DEFAULT_NOTIONAL convention -- flagged as an assumption the owner may override once IBKR Gateway shows the real paper account's equity at the 05-08 ops checkpoint"
  - "get_unresolved_orders and get_all_unresolved_orders share one private module-level constant (_UNRESOLVED_STATUS_FILTER) so the status IN ('pending_submit','submitted') filter cannot silently drift between the scoped and unscoped queries"
  - "close_position derives profile_name for paper_trades from the paper_positions row's own strategy_id, so callers never re-pass duplicate data"

patterns-established:
  - "Pattern 1: Every paper/*.py DB function takes conn as its first argument, uses only ? placeholders, and commits before returning (matches trader/data/db.py and trader/risk/breakers.py exactly)"
  - "Pattern 2: Idempotency matchers (idempotency.py) stay pure/zero-I/O; ledger.py owns all I/O and is the only module that imports sqlite3 in trader/paper/"

requirements-completed: [PAPER-03, PAPER-05]

# Metrics
duration: 25min
completed: 2026-07-27
---

# Phase 05 Plan 01: Migration 0005 + Idempotency + Ledger Summary

**Migration 0005's five paper-trading tables, the five frozen live D-01 strategy configs, and a crash-safe pending_submit->submitted->filled order ledger with both scoped and unscoped date-independent unresolved-order lookups.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-26T23:55:00Z (approx.)
- **Completed:** 2026-07-27T00:29:00Z
- **Tasks:** 2 (Task 2 executed as a TDD RED -> GREEN pair)
- **Files modified:** 9 (7 created, 2 modified)

## Accomplishments
- migrations/0005_paper_trading.sql: paper_orders (with the revised three-state pending_submit/submitted/filled lifecycle), paper_positions, paper_trades, reconciliation_log + reconciliation_halt_state view, strategy_kill_state -- verified to apply cleanly on a fresh DB and accept real-trade-format inserts
- trader/paper/config.py: IBKR_PAPER_PORT=4002 (hardcoded literal, standing rule 6), cadences, and exactly five LIVE_STRATEGY_CONFIGS entries transcribed verbatim from KILL-CONDITIONS.md (kill triggers) and reports/backtests/oos_results_v2.json (exit-profile parameters), cross-checked directly against oos_results_v2.json this session
- trader/paper/idempotency.py: build_order_ref (deterministic key), find_existing_order (fast same-day/same-tick path), find_unresolved_match (BLOCKER 1's crash-recovery matcher, keyed on the unresolved order's own order_ref rather than any freshly-computed "today" ref)
- trader/paper/ledger.py: full read/write surface, including record_order's persist-before-submit default, heal_order (primary crash-recovery heal path), get_unresolved_orders (scoped, date-independent) and get_all_unresolved_orders (unscoped, RESIDUAL BLOCKER 1) sharing one private status-filter helper, get_pending_order_qty (excludes pending_submit), open_position/get_open_positions/close_position (exit-profile round-trip), retire_strategy/is_strategy_retired (idempotent)

## Task Commits

Each task was committed atomically:

1. **Task 1: Migration 0005 + frozen config.py (contracts)** - `8506304` (feat)
2. **Task 2: Idempotency + ledger surface (TDD)**
   - RED: `b716217` (test) - failing tests for idempotency.py and ledger.py, plus the paper_conn conftest fixture
   - GREEN: `7617373` (feat) - idempotency.py + ledger.py implementations, plus a Rule 1 fix to tests/test_risk_migration.py

_Note: Task 2 is a TDD task with a separate test -> feat commit pair, per plan._

## Files Created/Modified
- `migrations/0005_paper_trading.sql` - Five new tables + reconciliation_halt_state view
- `trader/paper/__init__.py` - Empty package marker
- `trader/paper/config.py` - Frozen IBKR/cadence constants + LIVE_STRATEGY_CONFIGS
- `trader/paper/idempotency.py` - build_order_ref, find_existing_order, find_unresolved_match
- `trader/paper/ledger.py` - Full paper_orders/paper_positions/paper_trades/strategy_kill_state surface
- `tests/conftest.py` - Added paper_conn fixture (additive only, per instructions)
- `tests/test_idempotency.py` - 9 tests for the pure matcher functions
- `tests/test_paper_ledger.py` - 15 tests for the ledger surface
- `tests/test_risk_migration.py` - Fixed a version-drift-fragile assertion (see Deviations)

## Decisions Made
- PAPER_ACCOUNT_EQUITY=100,000.0 chosen per plan's explicit "Claude's discretion" instruction, documented as an assumption pending the 05-08 ops checkpoint
- Added `ibkr_host()`/`ibkr_client_id()` helper functions in config.py as thin env-var readers (not engine logic) for downstream plans' convenience -- pure, zero side effects beyond `os.environ.get`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a schema-version test that hardcoded the migration count**
- **Found during:** Task 2 full-suite verification
- **Issue:** `tests/test_risk_migration.py::test_migration_0004_reaches_schema_version_4` asserted `MAX(version) == 4`. Adding `migrations/0005_paper_trading.sql` legitimately advances `schema_version`'s max to 5, so this assertion would fail for any future phase that adds a migration, not just this one.
- **Fix:** Changed the assertion to check that version 4 is among the applied versions (`4 in applied_versions`), rather than that it is the maximum. The test's actual intent -- confirming migration 0004 applied -- is preserved; the fragile "is the latest" assumption is removed.
- **Files modified:** tests/test_risk_migration.py
- **Verification:** Full suite passes (370 passed, 1 deselected)
- **Committed in:** `7617373` (part of Task 2's GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug fix)
**Impact on plan:** Necessary correctness fix triggered directly by this plan's own migration file; no scope creep, no other pre-existing test files touched.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. IBKR/Kraken/Telegram credentials are read from environment variables at call time by later plans (05-02+); this plan only defines the env var names as constants.

## Next Phase Readiness
- trader/paper/config.py, idempotency.py, and ledger.py provide a stable, pre-tested Interface-First contract: 05-02 (broker adapter), 05-05 (guardian), and 05-06 (entry pipeline / STEP 0 standalone heal pass) can all be built and TDD'd against a mocked broker without exploring this module's internals
- get_all_unresolved_orders and find_unresolved_match together close the plan-checker's RESIDUAL BLOCKER 1 -- 05-06 can now implement its mandatory STEP 0 heal pass directly against get_all_unresolved_orders
- No blockers for the next plan in this phase

---
*Phase: 05-paper-trading-loop*
*Completed: 2026-07-27*

## Self-Check: PASSED

All created files verified present on disk; all three task commit hashes (8506304, b716217, 7617373) verified present in git log.
