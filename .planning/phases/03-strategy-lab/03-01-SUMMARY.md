---
phase: 03-strategy-lab
plan: 01
subsystem: backtest-strategy
tags: [python, numpy, pandas, backtesting, rsi, technical-indicators, tdd]

# Dependency graph
requires:
  - phase: 02-backtest-harness
    provides: "PointInTimeIterator (history/symbols/bar_on), run_backtest, shared pick_entries(iterator, date, open_positions, rng) strategy contract, momentum_placeholder.py's point-in-time discipline pattern"
provides:
  - "trader/backtest/strategies/momentum.py — RSI(14) + 2x-20-day-volume-surge + 20-day-high-break pure function (STRAT-01)"
  - "trader/backtest/strategies/breakout.py — NR7 volatility contraction + 20-day-high-break + 1.5x-volume-confirm pure function, no-retest (STRAT-02)"
  - "Fixture-bar test pattern with independently-controlled close/high/low/volume columns for isolating single signal components"
affects: [03-02-exit-parameter-sweep, 03-03-sweep-engine, phase-4-gate-sizer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Self-contained per-module indicator helpers (_rsi_wilder lives only in momentum.py) — no shared indicator-helper module across strategies"
    - "Fixed entry-rule constants as module-level literals, never sweep-grid inputs"
    - "Baseline/prior-high windows always sliced history[-(N+1):-1], today always history[-1] — off-by-one guard against a bar inflating its own baseline"
    - "Fixture builders with independently controllable OHLCV columns (decoupled from a single close-derived shape) to isolate one signal component per test"

key-files:
  created:
    - trader/backtest/strategies/__init__.py
    - trader/backtest/strategies/momentum.py
    - trader/backtest/strategies/breakout.py
    - tests/test_strategy_momentum.py
    - tests/test_strategy_breakout.py
  modified: []

key-decisions:
  - "RSI helper (_rsi_wilder) is private and local to momentum.py only, per D-03's pure-function/no-shared-state discipline — breakout.py does not import it"
  - "Breakout ships no-retest for v1 per 03-RESEARCH.md Open Question 1's orchestrator resolution — documented directly in breakout.py's module docstring so it is not later 'fixed' as a missing feature"
  - "Both agents are long-only only; no short-side code path exists anywhere, matching inherited D-15 engine constraint"

patterns-established:
  - "Pattern: per-strategy self-contained indicator helpers, no cross-module sharing"
  - "Pattern: fixture builder with independent close/high/low/volume lists, used for every future strategy test file"

requirements-completed: [STRAT-01, STRAT-02]

# Metrics
duration: 55min
completed: 2026-07-26
---

# Phase 3 Plan 1: Momentum + Breakout Strategy Agents Summary

**RSI(14)+volume-surge momentum agent and NR7+20-day-high breakout agent (no-retest), both pure functions over `iterator.history()` matching the shared `pick_entries` contract, each proven against 6 fixture-isolated signal conditions plus a signature check.**

## Performance

- **Duration:** 55 min
- **Started:** 2026-07-26T06:42:00Z (approx)
- **Completed:** 2026-07-26T07:37:00Z
- **Tasks:** 2 completed
- **Files modified:** 5 (3 created source, 2 created test)

## Accomplishments
- Momentum agent (`trader/backtest/strategies/momentum.py`): signals only when RSI(14) >= 60, today's volume exceeds 2.0x its trailing 20-day average, and today's close breaks the prior 20-day high — all three conditions independently pinned by fixture tests, including an off-by-one fixture proving the baseline excludes today's own bar.
- Breakout agent (`trader/backtest/strategies/breakout.py`): signals only when today's high-low range is the narrowest of the trailing 7 bars (NR7), today's close breaks the prior 20-day high, and today's volume exceeds 1.5x its trailing 20-day average — no retest gate, matching the orchestrator's locked scope resolution.
- Both agents proven to never re-signal an open position and never signal on fewer than lookback+1 bars of history, regardless of otherwise-qualifying price/volume shape.
- Full suite grew from 150 to 164 passing tests with zero regressions to Phase 2's harness.

## Task Commits

Each task followed RED -> GREEN:

1. **Task 1: Momentum agent** - `a570a19` (test, RED — 7 failing tests) -> `fde693e` (feat, GREEN — all 7 pass)
2. **Task 2: Breakout agent** - `ca1c555` (test, RED — 7 failing tests) -> `a99213e` (feat, GREEN — all 7 pass)

**Plan metadata:** (this commit, docs: complete plan)

_TDD gate sequence confirmed in git log: test(03-01) commits precede their feat(03-01) commits for both tasks._

## Files Created/Modified
- `trader/backtest/strategies/__init__.py` - empty package marker
- `trader/backtest/strategies/momentum.py` - RSI(14)+volume-surge+20-day-high momentum `pick_entries` (STRAT-01); exports `pick_entries`, `RSI_PERIOD`, `RSI_MOMENTUM_FLOOR`, `VOLUME_SURGE_MULT`, `BREAK_LOOKBACK`
- `trader/backtest/strategies/breakout.py` - NR7+20-day-high breakout `pick_entries`, no-retest (STRAT-02); exports `pick_entries`, `NR_WINDOW`, `BREAKOUT_LOOKBACK`, `VOLUME_CONFIRM_MULT`
- `tests/test_strategy_momentum.py` - 7 tests: fires, RSI-below-floor, volume-below-floor, insufficient-history, open-position-skip, off-by-one baseline, signature
- `tests/test_strategy_breakout.py` - 7 tests: fires, no-break, NR7-not-narrowest, volume-below-floor, insufficient-history, open-position-skip, signature

## Decisions Made
- Kept `_rsi_wilder` private to `momentum.py` rather than extracting a shared indicator module, per D-03's "pure functions, no state outside the ledger" and the plan's explicit instruction that each strategy module stay self-contained.
- Used the plan's exact "simple mean of gains/losses over the last period+1 closes" RSI formula (matching 03-RESEARCH.md's Code Examples section) rather than a recursively-smoothed true Wilder average — this is what the plan's `_rsi_wilder` action text specifies.
- Test fixtures decouple close/high/low/volume into independently controllable lists (rather than reusing the existing `_bars_with_closes`/`close+1` derived shape from `test_backtest_strategies.py`) so each test isolates exactly one signal component. This is a new fixture pattern introduced in this plan for future strategy test files to reuse.

## Deviations from Plan

None - plan executed exactly as written. Both tasks matched their `<action>` specifications verbatim; all `<behavior>` cases were covered by dedicated fixture tests.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- STRAT-01 and STRAT-02 are implemented and fixture-proven, ready for Plan 03-03's sweep engine to drive both agents through `run_backtest` unmodified.
- Full suite green (164/164) — no regressions to Phase 2's harness.
- No blockers.

---
*Phase: 03-strategy-lab*
*Completed: 2026-07-26*

## Self-Check: PASSED

All created files found on disk; all 4 task commit hashes (a570a19, fde693e, ca1c555, a99213e) confirmed present in git log.
