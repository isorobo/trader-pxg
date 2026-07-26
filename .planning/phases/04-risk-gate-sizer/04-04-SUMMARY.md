---
phase: 04-risk-gate-sizer
plan: 04
subsystem: risk
tags: [circuit-breakers, sqlite, event-sourcing, cli, security]

# Dependency graph
requires:
  - phase: 04-risk-gate-sizer (Plan 04-01)
    provides: "migrations/0004_risk_breakers.sql (breaker_events append-only log + breaker_state_current view), trader/risk/config.py's BREAKER_* thresholds"
provides:
  - "evaluate_breakers(equity_curve, trade_pnls, config) -- pure, incremental, no-lookahead evaluation of daily-loss/drawdown/consecutive-loss breakers"
  - "append_breaker_event/read_breaker_state/record_breaker_transitions -- thin, parameterized, append-only persistence over breaker_events"
  - "clear_manual_restart -- the sole function that can clear the drawdown breaker's halt"
  - "trader/risk/clear_breaker.py -- the sole human-invoked CLI entrypoint (python -m trader.risk.clear_breaker --reason \"<why>\")"
affects: [phase-05-paper-trading, risk-gate-sizer-verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Incremental HWM re-derivation: hwm = max(equity_curve) computed fresh on every call, never persisted -- safety depends entirely on the caller never passing future equity points (mirrors trader/backtest/metrics.py's peak-tracking pattern but applied incrementally, never retrospectively)"
    - "Human-only clear path enforced structurally: clear_manual_restart is the only function that ever writes action='manual_restart'; a literal-string-scope test (AST-based) fails the build if the string 'manual_restart' appears anywhere outside that one function"
    - "record_breaker_transitions re-derives justification from a fresh evaluate_breakers() call before writing any transition (standing rule 4: never silently drop a real transition, never trust a cached column)"

key-files:
  created:
    - trader/risk/breakers.py
    - trader/risk/clear_breaker.py
    - tests/test_breakers.py
  modified: []

key-decisions:
  - "Daily-loss and consecutive-loss breakers auto-clear (trip on normal->tripped, reset on tripped->normal); the drawdown breaker never auto-clears -- its only clear path is the human-run clear_breaker CLI (T-04-10)"
  - "evaluate_breakers takes trade_pnls as the chronological list of closed-trade pnls up to and including 'now', decoupled from equity_curve's date granularity -- consecutive-loss counting walks this list from the end, independent of the daily equity series"
  - "Persistence functions receive a caller-supplied sqlite3.Connection rather than opening their own -- breakers.py itself never imports sqlite3 or trader.data.db, keeping evaluate_breakers and the persistence helpers provably free of hidden I/O coupling"

patterns-established:
  - "AST-based source-scope tests for security invariants (confining a literal string to one function, confirming SQL args are plain string literals) rather than brittle text-grep, so refactors that don't change behavior don't trip false positives"

requirements-completed: [RISK-03]

# Metrics
duration: 35min
completed: 2026-07-26
---

# Phase 04 Plan 04: Circuit Breakers + Human-Only Clear CLI Summary

**Pure incremental no-lookahead breaker evaluation (daily-loss/drawdown/consecutive-loss) over a real Phase 2 harness equity curve, backed by an append-only parameterized event log, with `clear_manual_restart` as the sole human-gated path to clear the drawdown halt.**

## Performance

- **Duration:** 35 min
- **Tasks:** 2 completed (each as a RED/GREEN TDD pair)
- **Files modified:** 3 (2 created, 1 test file created)

## Accomplishments
- `evaluate_breakers` computes all three breakers from an equity curve and a trade-pnl list with zero DB/file I/O, HWM re-derived incrementally (`max(equity_curve)`) rather than retrospectively
- A dedicated no-lookahead regression test proves the drawdown breaker cannot "see" a future recovery when fed a truncated curve
- A day-by-day simulation stepping through a real `trader.backtest.metrics._build_daily_equity_curve` output confirms daily-loss trips at days 3 and 5, and drawdown trips at day 5, and no earlier
- `append_breaker_event`/`read_breaker_state`/`record_breaker_transitions` are thin, parameterized (ASVS V5), and append-only over `migrations/0004_risk_breakers.sql`'s schema
- `clear_manual_restart` is the only function in the module that can clear the drawdown breaker; an AST-based test confirms the literal string `"manual_restart"` never appears outside that function's own line range
- `trader/risk/clear_breaker.py` provides `python -m trader.risk.clear_breaker --reason "<why>"` as the sole human-run clear command; a test confirms it has no importer anywhere under `trader/` except as `__main__`/directly in tests

## Task Commits

Each task followed a RED (`test`) / GREEN (`feat`) TDD pair:

1. **Task 1: evaluate_breakers -- pure, incremental, no-lookahead**
   - `635973d` test(04-04): add failing tests for evaluate_breakers (RISK-03)
   - `e42f014` feat(04-04): implement evaluate_breakers -- pure, incremental, no-lookahead (RISK-03)
2. **Task 2: Persistence layer + human-only manual-restart clear path**
   - `8115225` test(04-04): add failing tests for breaker persistence + human-only clear path (RISK-03)
   - `871f25d` feat(04-04): implement breaker persistence + human-only clear path (RISK-03)

## Files Created/Modified
- `trader/risk/breakers.py` - `evaluate_breakers`, `append_breaker_event`, `read_breaker_state`, `record_breaker_transitions`, `_record_auto_clearing_breaker`, `clear_manual_restart`
- `trader/risk/clear_breaker.py` - `main(argv=None)`, the sole CLI entrypoint invoking `clear_manual_restart`
- `tests/test_breakers.py` - 27 tests: evaluate_breakers unit/regression/simulation coverage, persistence coverage, and the security invariants (T-04-09/T-04-10)

## Decisions Made
- Drawdown never auto-clears by design (locked in `record_breaker_transitions`); only `clear_manual_restart`, invoked only via the CLI, can clear it.
- `evaluate_breakers`'s `trade_pnls` argument is independent of `equity_curve`'s daily granularity -- it is the chronological closed-trade pnl list, letting consecutive-loss counting work correctly even when multiple trades close on the same day.
- Persistence functions accept a connection object rather than a db-path string, keeping `breakers.py` free of any sqlite3/trader.data.db import (verified by an AST-based purity test).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test bug] Purity test's string-ban was too broad**
- **Found during:** Task 1 GREEN phase
- **Issue:** `test_breakers_module_never_imports_sqlite_or_db` originally banned the literal substring `"trader.data.db"` anywhere in the file, which false-failed against the module's own docstring prose describing the lookahead-safety contract.
- **Fix:** Narrowed the test to an AST walk checking only actual `Import`/`ImportFrom` nodes, not docstring prose.
- **Files modified:** tests/test_breakers.py
- **Verification:** `pytest tests/test_breakers.py -k purity or never_imports` passes; docstring prose remains free to mention the module name.
- **Committed in:** e42f014 (Task 1 GREEN commit)

**2. [Rule 1 - Test bug] "No importer" check flagged docstring mentions, not real imports**
- **Found during:** Task 2 GREEN phase
- **Issue:** `test_clear_breaker_module_has_no_importers_under_trader` originally grepped for the raw substring `"clear_breaker"` anywhere in every `trader/*.py` file, which false-failed against `breakers.py`'s own docstring (which documents the CLI invocation in prose).
- **Fix:** Rewrote the check as an AST walk over `Import`/`ImportFrom` nodes only, so prose mentions no longer trip it while a real `import trader.risk.clear_breaker` anywhere still would.
- **Files modified:** tests/test_breakers.py
- **Verification:** `pytest tests/test_breakers.py -k clear_breaker` passes.
- **Committed in:** 871f25d (Task 2 GREEN commit)

**3. [Rule 1 - Test bug] SQL-parameterization test banned all f-strings, not just SQL**
- **Found during:** Task 2 GREEN phase
- **Issue:** `test_no_fstring_or_percent_format_sql_in_breakers_module` banned the substring `f"` anywhere in the file, which false-failed against an f-string used to build a human-readable `reason` value (e.g. `f"{breaker_type} threshold breached"`) -- not SQL at all.
- **Fix:** Replaced with `test_every_conn_execute_call_uses_a_parameterized_query_string`, an AST walk asserting every `conn.execute()`/`executemany()` call's SQL argument is a plain string literal (`ast.Constant`), which is the actual ASVS V5 requirement -- f-strings elsewhere in the module remain unconstrained.
- **Files modified:** tests/test_breakers.py
- **Verification:** `pytest tests/test_breakers.py` -- 27 passed.
- **Committed in:** 871f25d (Task 2 GREEN commit)

---

**Total deviations:** 3 auto-fixed (all Rule 1, test-only corrections discovered while turning RED tests GREEN -- no production-code behavior was changed by any of these fixes).
**Impact on plan:** All three fixes tightened the tests' precision (from brittle substring bans to AST-based structural checks) without weakening any of the security invariants they were written to enforce. No scope creep.

## Issues Encountered
None beyond the three test-precision fixes documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- RISK-03 is fully implemented: all three breakers fire correctly against a real Phase 2 harness equity curve, the no-lookahead HWM is proven by a dedicated regression test, and the drawdown breaker's manual restart has exactly one, human-only clear path.
- Full suite green: 345 tests passed (was 318 before this plan; this plan added 27).
- Phase 5's paper-trading loop can call `evaluate_breakers` per new equity point plus `record_breaker_transitions` to persist state, and use `python -m trader.risk.clear_breaker --reason "<why>"` as the operator's restart command after a drawdown halt.

---
*Phase: 04-risk-gate-sizer*
*Completed: 2026-07-26*

## Self-Check: PASSED

All created files confirmed on disk (`trader/risk/breakers.py`, `trader/risk/clear_breaker.py`, `tests/test_breakers.py`, this SUMMARY.md). All 4 task commit hashes (`635973d`, `e42f014`, `8115225`, `871f25d`) confirmed present in `git log`. Full suite re-run: 345 passed.
