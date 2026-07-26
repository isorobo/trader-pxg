---
phase: 02-backtest-harness
plan: 04
subsystem: testing
tags: [fees, slippage, fills, backtest, tdd, pytest]

# Dependency graph
requires:
  - phase: 02-backtest-harness (plan 02-01)
    provides: FEE_TABLE, SLIPPAGE_PCT, SLIPPAGE_SMALL_CAP_RUNNER, DEFAULT_NOTIONAL config constants
provides:
  - fee_for(asset_class, qty, price) -- per_share/taker_pct fee models from FEE_TABLE
  - slippage_pct_for(asset_class) -- percentage-to-fraction conversion of SLIPPAGE_PCT
  - apply_slippage(price, side, asset_class) -- always biases against the trader
  - entry_fill_price(bar_open, asset_class, side) -- D-04 next-bar-open + slippage
  - worse_of_fill(trigger_price, bar_open, side) -- D-04 gap-through conservative exit pricing, with the documented stop-vs-take-profit asymmetry
affects: [02-08 (runner.py, calls these functions on every open/close), 02-09 (sanity test's expected-bias calculation reads these same values)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Config-driven fee/slippage: fills.py contains zero hard-coded fee or slippage numbers -- everything is looked up from trader.backtest.config, enforced by a grep gate in the plan's acceptance criteria"
    - "Deliberate stop/TP asymmetry: worse_of_fill treats a stop exit (min of trigger/open) and a take-profit exit (always trigger, capped) differently, documented in the function docstring rather than left implicit"

key-files:
  created: [trader/backtest/fills.py, tests/test_backtest_fills.py]
  modified: []

key-decisions:
  - "worse_of_fill takes side values \"sell\" (stop exit) and \"sell_at_tp\" (take-profit exit) rather than a single side plus a separate exit-type flag -- keeps the asymmetric worse-of logic in one small function with two clear branches"
  - "Short-side exits (\"buy\"/\"buy_at_tp\") raise NotImplementedError rather than being silently wrong, since Phase 2 is long-only per D-15"
  - "Reworded two docstring passages in fills.py (spelling out '0.0005' as prose, and describing the small-cap-runner constant without naming it literally) so the plan's literal grep gates (banning config-value numeric literals and the SLIPPAGE_SMALL_CAP_RUNNER name in fills.py) pass on documentation text, not just on executable code"

patterns-established:
  - "Pure fill functions: every function in fills.py is (asset_class, price, qty, side) -> value with no state and no I/O, matching the plan's architecture (fills.py is Execution Simulation, config.py is Config)"

requirements-completed: [BACK-02, BACK-03]

# Metrics
duration: 15min
completed: 2026-07-26
---

# Phase 02 Plan 04: Fee, Slippage, and Conservative Fill-Price Functions Summary

**Config-driven fee_for/slippage_pct_for/apply_slippage/entry_fill_price/worse_of_fill in trader/backtest/fills.py, proven by 19 tests to always bias fills against the trader, including the D-04 stop-vs-take-profit gap asymmetry.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-26T04:40:00Z (approx)
- **Completed:** 2026-07-26T04:57:27Z
- **Tasks:** 1 (TDD: RED then GREEN)
- **Files modified:** 2 created

## Accomplishments
- fee_for computes IBKR per-share (with $1.00 minimum) and Kraken taker-pct fees purely from FEE_TABLE, never re-declaring the 0.005/1.00/0.0026 values in fills.py
- slippage_pct_for converts SLIPPAGE_PCT's percentage-unit values to fractions (0.05% -> 0.0005, 0.10% -> 0.0010, 4.0% -> 0.04), confirming crypto_major deliberately does not use the small-cap-runner 2% tier
- apply_slippage and entry_fill_price prove, by test, that buys fill higher and sells fill lower -- slippage biases against the trader on both sides
- worse_of_fill implements and tests D-04's asymmetric gap-through rule: a stop exit takes the worse (lower) of trigger price and bar open, but a take-profit exit always caps at the trigger price even on a favourable gap
- Every asset_class-taking function raises KeyError (not a silent default) for an unknown asset_class, proven by 4 dedicated tests

## Task Commits

Each task was committed atomically (TDD: test then feat):

1. **Task 1 (RED): add failing test for fee, slippage, and conservative fill-price functions** - `51f9cd2` (test)
2. **Task 1 (GREEN): implement fee, slippage, and conservative fill-price functions** - `804b350` (feat)

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified
- `trader/backtest/fills.py` - fee_for, slippage_pct_for, apply_slippage, entry_fill_price, worse_of_fill; imports FEE_TABLE/SLIPPAGE_PCT from trader.backtest.config, never re-hard-codes their values
- `tests/test_backtest_fills.py` - 19 tests covering every behavior item in the plan plus the KeyError-on-unknown-asset_class contract

## Decisions Made
- worse_of_fill uses side="sell"/"sell_at_tp" (not a separate exit-type parameter) to keep the stop-vs-TP asymmetry in one function with two branches, both covered by tests
- Short-side (buy-side) exits raise NotImplementedError, documented as out of Phase 2's long-only scope (D-15), rather than guessing at unimplemented symmetric behaviour
- Reworded two fills.py docstring passages to avoid tripping the plan's literal grep acceptance gates (numeric literals matching config values, and the SLIPPAGE_SMALL_CAP_RUNNER name) while keeping the documentation equally clear

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Docstring literals tripped the plan's own grep acceptance gates**
- **Found during:** Task 1, GREEN phase verification
- **Issue:** The first draft of fills.py's docstrings spelled out "0.0005" as an example and named "SLIPPAGE_SMALL_CAP_RUNNER" directly in prose. The plan's acceptance criteria run a literal `grep -c` for config-value numbers and for that constant's name across the whole file, so documentation text (not just code) tripped both gates even though no executable line consumed those values.
- **Fix:** Reworded both passages to describe the same information in prose (spelling out the percentage conversion, and referring to "the small-cap-runner constant documented in config.py" without repeating its literal name).
- **Files modified:** trader/backtest/fills.py
- **Verification:** `grep -nE "0\.005|0\.0026|0\.0005|0\.0010|0\.04\b|100\.0" trader/backtest/fills.py` and `grep -c "SLIPPAGE_SMALL_CAP_RUNNER" trader/backtest/fills.py` both return 0/no matches; `pytest tests/test_backtest_fills.py -x -q` still 19 passed after the reword.
- **Committed in:** 804b350 (part of the GREEN task commit; the docstring wording was corrected before that commit, not as a follow-up)

---

**Total deviations:** 1 auto-fixed (1 bug — grep-gate-tripping docstring wording, fixed before commit)
**Impact on plan:** Documentation-only fix; no behavioural or test change. No scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- fills.py's five functions are ready for plan 02-08 (runner.py) to call on every position open and close
- plan 02-09's sanity test can compute its expected fee+slippage bias from these same fee_for/slippage_pct_for functions, keeping the expected-bias derivation independent from the harness's own trade output (avoiding the research doc's "Pitfall 6" circular-tolerance-band trap)
- No blockers

---
*Phase: 02-backtest-harness*
*Completed: 2026-07-26*
