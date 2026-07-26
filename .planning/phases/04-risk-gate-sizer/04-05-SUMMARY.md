---
phase: 04-risk-gate-sizer
plan: 05
subsystem: testing
tags: [pytest, pandas, numpy, risk-gate, position-sizer, acceptance-test]

# Dependency graph
requires:
  - phase: 04-risk-gate-sizer
    provides: "trader/risk/gate.py's apply_risk_gate (Plan 04-02) and trader/risk/sizer.py's size_positions (Plan 04-03)"
provides:
  - "tests/test_poisoned_list.py -- the committed 7-entry poisoned candidate list (04-RESEARCH.md Q6) exercised as a gate+sizer two-stage pipeline"
  - "D-07/RISK-04's literal exit-gate acceptance test, self-verifying the fabricated correlated pair before asserting gate behavior"
affects: [05-execution-loop, verify-work]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fixture builder function (_build_poisoned_fixture) returns candidates + market_data + raw bars for reuse across the gate-stage and pipeline tests, avoiding duplicated fixture construction"
    - "Self-verifying fabricated fixture: correlation of the CORRA/CORRB pair is independently recomputed and asserted above threshold before any gate assertion depends on it"

key-files:
  created: [tests/test_poisoned_list.py]
  modified: []

key-decisions:
  - "Symbols with a slash (NEWTOK/USDT, MEMER/USDT) are used as the literal candidate symbol string, matching how the plan's fixture table names them"
  - "CLEAN1/CLEAN2/MEMER/USDT use flat (zero-variance) price series so their pairwise correlation with CORRA/CORRB and each other is NaN, which the gate's abs(corr) > threshold check safely treats as non-correlated rather than needing separate low-correlation fabrication"
  - "Task 2's expected CORRB/CLEAN1/cash weights are computed in-test via the same raw/normalize formula from 04-RESEARCH.md Q3, then asserted against the sizer's actual output with pytest.approx(rel=1e-3) -- self-verifying rather than copying hand-rounded numbers from the plan"

patterns-established: []

requirements-completed: [RISK-04, RISK-01, RISK-02]

# Metrics
duration: 21min
completed: 2026-07-26
---

# Phase 04 Plan 05: D-07 Poisoned-List Exit-Gate Acceptance Test Summary

**Committed 7-entry poisoned candidate fixture drives gate.apply_risk_gate then sizer.size_positions as one pipeline, asserting all four exact gate reason codes and the sizer's memecoin-cap clip to 0.10**

## Performance

- **Duration:** 21 min
- **Started:** 2026-07-26T10:29:00Z
- **Completed:** 2026-07-26T10:50:26Z
- **Tasks:** 2
- **Files modified:** 1 (created)

## Accomplishments
- Built the committed 7-entry poisoned candidate list from 04-RESEARCH.md Q6 exactly: ILLQ (illiquid stock), NEWTOK/USDT (5-day-old memecoin), WIDESPRD (wide-spread stock), a fabricated CORRA/CORRB correlated pair, MEMER/USDT (oversized memecoin allocation), and two clean survivors (CLEAN1, CLEAN2)
- Self-verified the fabricated CORRA/CORRB pair's actual Pearson correlation exceeds `config.CORRELATION_THRESHOLD` before asserting any gate behavior on it
- Asserted the gate's full accept/reject partition with exact reason codes for all four rejection paths (`REJECT_LIQUIDITY`, `REJECT_LISTING_AGE`, `REJECT_SPREAD`, `REJECT_CORRELATION`)
- Exercised the gate and sizer together as a two-stage pipeline: attached hardcoded per-candidate volatility to the gate's 4 accepted candidates, fed them into `size_positions`, and asserted the sizer selects exactly the top-3 by score (excluding CLEAN2), clips MEMER/USDT's raw weight to exactly the 10% memecoin cap, and that freed weight flows to cash rather than redistributing to CORRB/CLEAN1

## Task Commits

Each task was committed atomically:

1. **Task 1: Committed 7-entry poisoned fixture + gate-stage assertions** - `adb76b2` (test)
2. **Task 2: Two-stage pipeline -- sizer clips the memecoin allocation, full D-07 cross-check** - `616bb2d` (test)

_Note: This plan's tasks are execute-type (not tdd="true"), so each task is a single commit -- the file did not exist before Task 1, so there is no separate RED/GREEN split._

## Files Created/Modified
- `tests/test_poisoned_list.py` - The committed 7-entry poisoned fixture and the two-stage gate+sizer D-07 acceptance test (245 lines)

## Decisions Made
- Used flat (zero-variance) price series for CLEAN1, CLEAN2, and MEMER/USDT so their pairwise correlation against CORRA/CORRB and each other resolves to NaN inside the gate's `_pairwise_correlation`, which `abs(corr) > threshold` safely evaluates as `False` -- avoiding any risk of an accidental spurious correlation rejection among the "clean" fixture entries
- Symbol strings containing a slash (`NEWTOK/USDT`, `MEMER/USDT`) are used verbatim as the candidate's `symbol` field, matching the plan's fixture table naming
- Task 2's expected CORRB/CLEAN1/cash weights are derived in-test from the same `raw = score/volatility` -> normalize-to-0.90 formula the plan's worked arithmetic uses, then compared against the sizer's actual output via `pytest.approx(rel=1e-3)` -- this is self-verifying against the formula rather than copying the plan's hand-rounded decimal values

## Deviations from Plan

None - plan executed exactly as written. The `RuntimeWarning: invalid value encountered in divide` warnings seen during the test run are expected: they come from `pandas.Series.corr` computing `NaN` for the flat (zero-variance) CLEAN1/CLEAN2/MEMER series pairs, which is the intended, harmless "indeterminate correlation, skip this pair" behavior already covered by `gate.py`'s `if corr is not None` check.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- D-07/RISK-04's exit-gate acceptance test is real, committed, and passing -- Phase 4's literal exit criterion (ROADMAP.md success criterion 1) is met by this plan
- Combined with `tests/test_risk_gate.py`, `tests/test_position_sizer.py`, and `tests/test_breakers.py`, this plan completes the phase's full RISK-04 coverage (52 tests across the four Phase 4 test files, all green)
- Full repo suite: 347 tests passed (345 baseline + 2 new), no regressions
- No blockers for Phase 4 sign-off or Phase 5 planning

---
*Phase: 04-risk-gate-sizer*
*Completed: 2026-07-26*

## Self-Check: PASSED

- FOUND: tests/test_poisoned_list.py
- FOUND: .planning/phases/04-risk-gate-sizer/04-05-SUMMARY.md
- FOUND: adb76b2 (Task 1 commit)
- FOUND: 616bb2d (Task 2 commit)
