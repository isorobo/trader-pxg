---
phase: 02-backtest-harness
plan: 02
subsystem: backtest
tags: [pandas, numpy, two-pointer, point-in-time, backtesting]

# Dependency graph
requires:
  - phase: 01-accounts-data-plumbing
    provides: get_daily_bars (UTC tz-aware, sorted OHLCV DataFrame contract)
provides:
  - PointInTimeIterator (trader/backtest/iterator.py) with calendar, advance_to, history, bar_on
affects: [02-04-fills, 02-07-random-strategy, 02-08-runner, 02-10-momentum-placeholder]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-symbol two-pointer cursor over numpy arrays (O(1) amortized advance_to, no boolean-mask re-filtering)"
    - "history() returns a pointer-bounded numpy slice view -- lookahead structurally unreachable, not just untested"
    - "bar_on() is a pointer-unbound exact-date lookup, distinct from history()'s point-in-time-bound access"

key-files:
  created:
    - trader/backtest/iterator.py
    - tests/test_backtest_iterator.py
  modified: []

key-decisions:
  - "bar_on(symbol, date) intentionally does NOT respect the current simulation pointer -- fill logic (plan 02-04) needs a signal's next bar's open (D-04), which is a future date relative to the signal day; only history() enforces the point-in-time boundary"
  - "advance_to raises ValueError on any earlier date than already reached (pointers never move backwards); calling it again with the same date is a no-op"

patterns-established:
  - "Pattern 1 (02-RESEARCH.md): per-symbol two-pointer cursor built once at construction from pre-loaded DataFrames, never re-scanning from index zero"

requirements-completed: [BACK-01]

# Metrics
duration: 12min
completed: 2026-07-26
---

# Phase 2 Plan 02: Point-in-Time Bar Iterator Summary

**PointInTimeIterator: per-symbol two-pointer cursor over pre-loaded OHLCV DataFrames making lookahead structurally impossible, not just disciplined against**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-26T04:35:00Z
- **Completed:** 2026-07-26T04:47:45Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2 (1 created source, 1 created test)

## Accomplishments
- `PointInTimeIterator` built entirely from pre-loaded per-symbol DataFrames -- zero network/DB coupling, matching `get_daily_bars`' contract without calling it
- `history(symbol)` returns a numpy slice view bounded strictly by the last `advance_to` date -- proven unreachable-beyond-pointer even when a caller holds a stale reference across a later `advance_to` call (T-02-03)
- `advance_to` implemented as a per-symbol two-pointer walk (never re-scans from index zero), avoiding the O(n^2) boolean-mask re-filter anti-pattern flagged in 02-RESEARCH.md Pitfall 1 / T-02-04
- `bar_on(symbol, date)` proven to return `None` for a symbol's calendar gap via a two-symbol fixture with differing trading calendars

## Task Commits

Each task was committed atomically (TDD RED then GREEN):

1. **Task 1: Point-in-time iterator with two-pointer cursors** - `8895f3e` (test, RED) then `78cb500` (feat, GREEN)

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified
- `trader/backtest/iterator.py` - `PointInTimeIterator` and `_SymbolCursor`: calendar (sorted/deduplicated union of symbol dates), advance_to (monotonic per-symbol pointer advance), history (pointer-bounded slice view), bar_on (pointer-unbound exact-date lookup)
- `tests/test_backtest_iterator.py` - 9 tests: calendar construction, empty history pre-advance, pointer-bounded history slicing, no-op on repeated same-date advance, ValueError on backward advance, bar_on hit/miss paths, cross-call/cross-symbol lookahead-impossibility regression

## Decisions Made
- `bar_on` deliberately does not restrict itself to the current simulation pointer, since D-04's next-bar-open fill rule requires reading a bar dated after the signal day -- only `history()` is point-in-time-bound. This matches the plan's interface spec literally (bar_on's behavior clause carries no pointer-bound language, unlike history's).
- Acceptance-criteria grep gate against `df[df.index` initially flagged a docstring mention of the anti-pattern being avoided (not actual code); reworded the docstring to describe the anti-pattern without using the literal banned substring, keeping the explanation equally clear.

## Deviations from Plan

None - plan executed exactly as written. The docstring wording change above was a same-task adjustment to satisfy the plan's own automated acceptance criterion, not a deviation from the plan's intent.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `trader/backtest/iterator.py` is ready for plan 02-04 (fills), 02-07 (random strategy), 02-08 (runner), and 02-10 (momentum placeholder) to consume via `history(symbol)` for point-in-time signals and `bar_on(symbol, date)` for next-bar-open fills
- Full suite green: 80/80 tests passing (71 pre-existing + 9 new), no regressions

---
*Phase: 02-backtest-harness*
*Completed: 2026-07-26*

## Self-Check: PASSED

- FOUND: trader/backtest/iterator.py
- FOUND: tests/test_backtest_iterator.py
- FOUND: 8895f3e (test commit)
- FOUND: 78cb500 (feat commit)
