---
phase: 02-backtest-harness
plan: 05
subsystem: testing
tags: [backtest, exit-engine, dataclasses, tdd, python]

# Dependency graph
requires:
  - phase: 02-backtest-harness (02-01)
    provides: EXIT_PROFILE frozen dataclass (config.py)
  - phase: 02-backtest-harness (02-04)
    provides: fee/slippage/worse_of_fill fill-price helpers (fills.py)
provides:
  - "evaluate_exit(profile, position, bar, days_held, watermark) -> ExitResult | None implementing D-10's exact evaluation order"
  - "PositionState dataclass (entry-locked stop/tp prices, scale_out_triggered set, qty_remaining)"
  - "ExitResult dataclass matching migrations/0003_backtest.sql's exit_reason CHECK constraint"
  - "next_watermark() helper for watermark bookkeeping on the no-exit path"
affects: [02-08 (runner.py, consumes evaluate_exit per open position per bar)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Exit-condition evaluation as an ordered if/elif chain matching a locked decision (D-10), each branch proven by one named regression test"
    - "Reuse fills.worse_of_fill for all gap-through pricing instead of re-deriving conservative-fill arithmetic inline"

key-files:
  created:
    - trader/backtest/exits.py
    - tests/test_backtest_exits.py
  modified: []

key-decisions:
  - "Reused trader.backtest.fills.worse_of_fill for stop/trailing/TP/scale-out raw prices instead of the plan's inline conditional formulas, to keep D-04's gap-through rule in exactly one tested place and to fix a latent inconsistency in the plan's literal take-profit formula (see Deviations)"
  - "Watermark contract: ExitResult always carries new_watermark; on the None (no-exit) path, callers obtain the next-bar watermark via the sibling next_watermark() function, documented in the module docstring so runner.py (02-08) has one consistent contract"
  - "PositionState.open() classmethod computes stop_price/tp_price once at entry so standing rule 2 (exit profiles lock at entry) cannot be bypassed by direct construction"

patterns-established:
  - "Pattern: exit-condition ordering pinned by a named test per branch, not just an implementation that happens to pass the happy path"

requirements-completed: [BACK-04]

# Metrics
duration: 12min
completed: 2026-07-26
---

# Phase 2 Plan 05: EXIT_PROFILES Evaluation Engine Summary

**evaluate_exit() implements D-10's locked eod_flat -> stop -> trailing -> scale-out/TP -> time_stop order, with entry-bar checking, stop-wins-tie, and a non-lookahead trailing watermark, each pinned by a named test.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-26T04:52:00Z
- **Completed:** 2026-07-26T05:04:14Z
- **Tasks:** 1 (TDD: RED, GREEN)
- **Files modified:** 2 (both new)

## Accomplishments
- `trader/backtest/exits.py` implements `evaluate_exit`, `PositionState`, and `ExitResult` per the plan's interface, in D-10's exact locked order
- Every research-flagged pitfall (entry-bar check, trailing-watermark lookahead, eod_flat/time_stop daily-bars convention) has its own named regression test, not just happy-path coverage
- Reused `fills.worse_of_fill` for all gap-through pricing rather than duplicating D-04's conservative-fill arithmetic a second time in this module
- Full suite: 125 passed (116 pre-existing + 9 new), confirming no regressions

## Task Commits

Each task was committed atomically (TDD: RED then GREEN):

1. **Task 1 RED: failing tests for EXIT_PROFILES evaluation** - `0ebeeb9` (test)
2. **Task 1 GREEN: implement evaluate_exit in D-10 order** - `42560bc` (feat)

**Plan metadata:** (this commit) `docs(02-05): complete EXIT_PROFILES evaluation plan`

## Files Created/Modified
- `trader/backtest/exits.py` - `evaluate_exit`, `PositionState`, `ExitResult`, `next_watermark`; D-10's evaluation order, entry-bar checking, stop-wins-tie, non-lookahead trailing, daily-bars eod_flat/time_stop convention
- `tests/test_backtest_exits.py` - 9 named tests: `test_entry_bar_stop_check`, `test_stop_wins_tie`, `test_gap_through_stop`, `test_trailing_no_lookahead`, `test_eod_flat_beats_stop_in_order`, `test_eod_flat_fills_at_close`, `test_time_stop_exits_at_close`, `test_scale_out_partial_fires_once`, `test_no_exit_returns_none`

## Decisions Made
- **Reused `fills.worse_of_fill` instead of the plan's inline formulas** (see Deviations below) — keeps D-04's gap-through rule tested in exactly one place, per the executor's `files_to_read` note ("fill helpers from 02-04 — reuse, do not duplicate").
- **Watermark-on-None-path convention:** rather than changing `evaluate_exit`'s return type (which the plan's interface pins to `ExitResult | None`), added a sibling `next_watermark(position, watermark, bar)` function sharing the same private update helper, so callers have exactly one documented path to the next-bar watermark regardless of whether this bar's call fired.
- **`PositionState.open()` classmethod** computes `stop_price`/`tp_price` once at construction, rather than leaving callers to compute them ad hoc, so "computed once and never recomputed" (standing rule 2) is enforced by the type's only construction path.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Take-profit/scale-out gap-through formula in the plan's action text contradicted fills.py's tested D-04 contract**
- **Found during:** Task 1 implementation (writing the GREEN code for the scale-out/TP branch)
- **Issue:** The plan's action text spelled out take-profit's raw-price formula as `position.tp_price if bar['open'] < position.tp_price else bar['open']`. In the "bar gapped up through the target" branch (`bar['open'] >= tp_price`), this returns `bar['open']` — a price BETTER than the target. That directly contradicts `fills.worse_of_fill`'s already-implemented and tested D-04 contract (`side="sell_at_tp"` docstring: "the fill is ALWAYS capped at trigger_price, even if the bar gapped favourably past the target... a take-profit fill never improves past the target"). Re-deriving the formula inline in exits.py, slightly differently from fills.py, would have created two inconsistent implementations of the same rule and let a favourable-gap TP silently overstate returns.
- **Fix:** Called `fills.worse_of_fill(trigger, bar['open'], side="sell_at_tp")` for both take-profit and scale-out raw prices (both are profit-taking exits that should never improve past their target), and `fills.worse_of_fill(trigger, bar['open'], side="sell")` for stop and trailing-stop raw prices (both can only get worse on an adverse gap). This produces identical results to the plan's stop-price formula (verified: `min(trigger, open) if open > trigger else open` is exactly `worse_of_fill`'s `side="sell"` behaviour) while fixing the TP/scale-out asymmetry and eliminating duplicated gap-through logic.
- **Files modified:** `trader/backtest/exits.py`
- **Verification:** All 9 named tests pass; `test_scale_out_partial_fires_once` exercises the "sell_at_tp"-style capped pricing on a no-gap bar (target itself, `raw_price=110.0`); full suite green.
- **Committed in:** `42560bc` (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug fix / de-duplication)
**Impact on plan:** The fix corrects a latent same-bar-tie-style asymmetry the plan's literal text would have introduced for take-profit and scale-out fills, and it satisfies the executor's explicit reuse-don't-duplicate guidance for `fills.py`. No scope creep — the public interface (`evaluate_exit`, `PositionState`, `ExitResult`) matches the plan's `artifacts` spec exactly.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `evaluate_exit` is ready for `runner.py` (plan 02-08) to call once per open position per bar, including the entry bar
- The watermark contract (`ExitResult.new_watermark` when firing, `next_watermark()` when not) gives 02-08 one consistent, documented way to carry trailing-stop state across bars
- No blockers for downstream plans

---
*Phase: 02-backtest-harness*
*Completed: 2026-07-26*

## Self-Check: PASSED

- FOUND: trader/backtest/exits.py
- FOUND: tests/test_backtest_exits.py
- FOUND: 0ebeeb9 (test commit)
- FOUND: 42560bc (feat commit)
