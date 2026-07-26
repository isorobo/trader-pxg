---
phase: 02-backtest-harness
plan: 07
subsystem: backtest
tags: [strategies, random-strategy, momentum, seeded-rng, point-in-time]

# Dependency graph
requires:
  - phase: 02-backtest-harness (plan 02)
    provides: PointInTimeIterator (calendar, advance_to, history, bar_on)
provides:
  - random_strategy.pick_entries -- D-14's seeded, price-blind sanity-test engine
  - momentum_placeholder.pick_entries -- D-15's simplest-possible end-to-end proof strategy
  - PointInTimeIterator.symbols property (universe discovery for any pick_entries-shaped strategy)
affects: [02-08-runner, 02-09-sanity-test]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared pick_entries(iterator, date, open_positions, rng) -> list[str] contract lets runner.py (02-08) call any strategy polymorphically"
    - "Price-blind strategy by construction: random_strategy never reads an OHLCV value, only bar_on's presence/absence"

key-files:
  created:
    - trader/backtest/random_strategy.py
    - trader/backtest/momentum_placeholder.py
    - tests/test_backtest_strategies.py
  modified:
    - trader/backtest/iterator.py

key-decisions:
  - "Added PointInTimeIterator.symbols (Rule 2 deviation) since the iterator exposed no public universe listing and the shared pick_entries contract has no separate universe argument"
  - "LOOKBACK_DAYS = 20 for the momentum placeholder -- roughly a trading month, simple enough to audit by eye"

patterns-established:
  - "Strategy modules take iterator.symbols as the universe source of truth, never a separately-threaded list"

requirements-completed: [BACK-07]

# Metrics
duration: 15min
completed: 2026-07-26
---

# Phase 2 Plan 07: Seeded Random Strategy and Momentum Placeholder Summary

**Seeded, price-blind random strategy (D-14's sanity-test engine) plus a 20-day-lookback momentum placeholder (D-15), both sharing one pick_entries(iterator, date, open_positions, rng) contract**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-26T17:38:00+12:00
- **Completed:** 2026-07-26T17:54:51+12:00
- **Tasks:** 2 (TDD: RED + GREEN each)
- **Files modified:** 4 (2 source created, 1 test created, 1 source modified)

## Accomplishments
- `random_strategy.pick_entries` picks exactly one symbol per call, drawn only from symbols with a bar on `date` and not already open, provably reproducible given a fresh seeded `random.Random` and provably price-blind (no OHLCV value is ever read in the module)
- `momentum_placeholder.pick_entries` signals on every symbol whose latest visible close exceeds its close 20 bars earlier, and only once at least 21 bars of history exist -- proven against short-history, rising, flat, and falling fixtures
- Both strategies share the exact same `pick_entries(iterator, date, open_positions, rng) -> list[str]` signature so `runner.py` (plan 02-08) can call either polymorphically

## Task Commits

Each task was committed atomically (TDD RED then GREEN):

1. **Task 1: Seeded random strategy (D-14)** - `7857870` (test, RED) then `455e2d3` (feat, GREEN)
2. **Task 2: Momentum placeholder (D-15)** - `d5c8d4c` (test, RED) then `09500d3` (feat, GREEN)

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified
- `trader/backtest/random_strategy.py` - `pick_entries`: filters `iterator.symbols` to those with `bar_on(symbol, date) is not None` and not in `open_positions`, then `rng.choice` picks one; returns `[]` if none qualify
- `trader/backtest/momentum_placeholder.py` - `LOOKBACK_DAYS = 20`; `pick_entries` iterates `iterator.symbols`, skips already-open and insufficient-history symbols, appends any symbol whose latest close beats its close 20 bars earlier
- `tests/test_backtest_strategies.py` - 8 tests: random-strategy availability filter, seed-42 determinism, no-repick-of-open-position, empty-on-no-bar; momentum short-history-never-signals, rising-signals, flat/falling-no-signal, skip-already-open
- `trader/backtest/iterator.py` - added `PointInTimeIterator.symbols` read-only property (list of universe symbol names in construction order)

## Decisions Made
- `PointInTimeIterator.symbols` added as a minimal, additive property (Rule 2 -- missing critical functionality) rather than threading a separate `universe: list[str]` argument through `pick_entries`, since the plan's own interfaces block fixes the shared signature at four parameters (`iterator, date, open_positions, rng`) for runner.py's polymorphic dispatch in plan 02-08. No existing behavior changed; only an additive read-only property was introduced.
- `LOOKBACK_DAYS = 20` (Claude's discretion per the plan): roughly a trading month, long enough to be a real signal, short enough to keep the fixture/test math easy to audit by eye.
- Momentum's `rng` and `date` parameters are accepted but unused, purely to satisfy the shared contract signature -- documented explicitly in the module docstring so a future reader does not mistake this for an oversight.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Added `PointInTimeIterator.symbols` property**
- **Found during:** Task 1 (seeded random strategy)
- **Issue:** `PointInTimeIterator` (plan 02-02) exposed no public way to discover its universe of symbol names; only the private `_cursors` dict held them. The plan's shared `pick_entries` signature has no separate `universe` argument, so strategies need the iterator itself to expose the universe.
- **Fix:** Added a minimal `symbols` read-only property returning `list(self._cursors.keys())`, in construction order. No existing method or test changed.
- **Files modified:** `trader/backtest/iterator.py`
- **Verification:** Full suite green (143/143); existing 9 iterator tests unaffected (still passing); new tests exercise `.symbols` via both strategies.
- **Committed in:** `7857870` (Task 1 RED commit, alongside the new failing tests since the tests exercise the property through the strategy)

---

**Total deviations:** 1 auto-fixed (1 missing critical functionality)
**Impact on plan:** Necessary and additive only -- no existing behavior changed, no scope creep beyond what the plan's own interface contract required.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `trader/backtest/random_strategy.py` and `trader/backtest/momentum_placeholder.py` are ready for plan 02-08 (runner) to call polymorphically via `pick_entries(iterator, date, open_positions, rng)`, and for plan 02-09 (sanity test) to drive the random strategy against cached bars
- Full suite green: 143/143 tests passing (135 pre-existing + 8 new), no regressions

---
*Phase: 02-backtest-harness*
*Completed: 2026-07-26*

## Self-Check: PASSED

- FOUND: trader/backtest/random_strategy.py
- FOUND: trader/backtest/momentum_placeholder.py
- FOUND: tests/test_backtest_strategies.py
- FOUND: 7857870 (test, RED - random strategy)
- FOUND: 455e2d3 (feat, GREEN - random strategy)
- FOUND: d5c8d4c (test, RED - momentum placeholder)
- FOUND: 09500d3 (feat, GREEN - momentum placeholder)
