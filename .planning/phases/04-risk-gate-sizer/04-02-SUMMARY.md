---
phase: 04-risk-gate-sizer
plan: 02
subsystem: risk
tags: [pandas, pytest, tdd]

# Dependency graph
requires:
  - phase: 04-risk-gate-sizer
    provides: "04-01's trader/risk/config.py frozen threshold constants (LIQUIDITY_WINDOW_*, MIN_DOLLAR_VOLUME_STOCK, MIN_QUOTE_VOLUME_*, MIN_LISTING_AGE_DAYS, MAX_SPREAD_PCT, CORRELATION_*)"
provides:
  - "trader/risk/gate.py -- apply_risk_gate pure function, reason-code constants (REJECT_LIQUIDITY, REJECT_LISTING_AGE, REJECT_SPREAD, REJECT_CORRELATION), correlation cluster resolution"
  - "tests/test_risk_gate.py -- unit coverage of every RISK-01 check plus the N-way correlation cluster and date-alignment regression"
affects: [04-05-acceptance-test]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Reason-coded rejection: every rejected candidate dict carries exactly one reason_code, never a free-text message"
    - "Date-aligned pairwise correlation via pandas inner join on a calendar-date index, never a positional zip"
    - "Greedy sequential elimination for N-way correlation clusters: sort surviving pairs above threshold by magnitude descending, walk once, reject the lower-scored member of each still-live pair"

key-files:
  created:
    - trader/risk/gate.py
    - tests/test_risk_gate.py
  modified: []

key-decisions:
  - "Correlation windowing measured as trailing CORRELATION_WINDOW_DAYS calendar days back from each candidate's own last bar date, not a shared global 'today' -- keeps the pure function free of any wall-clock dependency"
  - "exit_profile_tag documented explicitly in gate.py's module docstring as a Phase 5 category placeholder (the raw asset_class string), not a Phase 2 EXIT_PROFILE dataclass instance"

patterns-established:
  - "gate.py imports every threshold from trader.risk.config by name -- zero inline magic numbers, verified by a dedicated hygiene test"
  - "gate.py has no import of trader.backtest.strategies -- verified by a dedicated hygiene test enforcing D-06's no-strategy-coupling rule"

requirements-completed: [RISK-01]

# Metrics
duration: 4min
completed: 2026-07-26
---

# Phase 4 Plan 02: Risk Gate Summary

**Pure apply_risk_gate function rejecting illiquid, too-new, too-wide-spread, and over-correlated candidates with exact reason codes, resolving N-way correlated clusters via greedy sequential elimination.**

## Performance

- **Duration:** 4 min (commit span; RED/GREEN/GREEN cycle)
- **Started:** 2026-07-26T22:19:00+12:00
- **Completed:** 2026-07-26T22:23:00+12:00
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `trader/risk/gate.py` implements RISK-01 end to end: liquidity (median dollar/quote volume floor), listing age, spread, and pairwise/N-way correlation checks, each importing its threshold from `trader.risk.config` by name.
- A fabricated 3-way fully-connected correlated cluster resolves to exactly one survivor (its highest-scored member) via the greedy sequential elimination algorithm from 04-RESEARCH.md Q2.
- A date-alignment regression test (stock business-day calendar vs crypto's 7-day calendar) confirms correlation is computed on an inner-joined calendar-date index, never a positional zip.
- Every accepted candidate is tagged with `asset_class` and `exit_profile_tag`; the module docstring states explicitly that `exit_profile_tag` is a Phase 5 category placeholder, not a resolved Phase 2 `EXIT_PROFILE` instance.

## Task Commits

Each task was committed atomically (TDD: RED test commit, then GREEN implementation commit per task):

1. **RED: failing tests for liquidity/age/spread/correlation** - `437e194` (test)
2. **Task 1: liquidity/listing-age/spread checks** - `7a7ed16` (feat)
3. **Task 2: correlation check + full wiring** - `9835b04` (feat)

_Note: Task 1 and Task 2 each follow the plan's own RED-then-GREEN internal structure; the single `tests/test_risk_gate.py` file covers both tasks' behaviour, committed once in RED (`437e194`) and completed incrementally across the two GREEN commits._

## Files Created/Modified
- `trader/risk/gate.py` - `apply_risk_gate`, reason-code constants, `_first_failing_check`, `_trailing_median_volume`, `_pairwise_correlation`, `_apply_correlation_check`
- `tests/test_risk_gate.py` - 16 tests covering every RISK-01 check, check-order precedence, accept-path tagging, the 3-way cluster, the min-overlap indeterminate case, the date-alignment regression, and gate.py hygiene (no strategies import, no inline magic numbers)

## Decisions Made
- Correlation windowing is anchored to each candidate's own last bar date (trailing `CORRELATION_WINDOW_DAYS` calendar days back from there), not a shared "today" parameter, keeping `apply_risk_gate` free of wall-clock dependence and fully deterministic given fixed bar data.
- `exit_profile_tag` is the raw `asset_class` string at this phase, with an explicit docstring note that Phase 5 resolves it into an actual `EXIT_PROFILE` selection later.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected an over-broad hygiene test assertion**
- **Found during:** Task 1 (liquidity/listing-age/spread implementation)
- **Issue:** `test_gate_module_has_no_strategies_import` used a bare substring check against `inspect.getsource(gate)`, which also matched the module docstring's own prose description of the D-06 no-coupling rule (a false positive, not an actual import).
- **Fix:** Narrowed the check to inspect only lines starting with `import ` or `from `, so it verifies the absence of an actual import statement rather than any mention of the string in documentation.
- **Files modified:** `tests/test_risk_gate.py`
- **Verification:** `pytest tests/test_risk_gate.py -k "not correlation" -q` passes; the docstring's explanatory prose remains intact.
- **Committed in:** `7a7ed16` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test-only fix, no change to gate.py's behaviour or the plan's required contract. No scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `apply_risk_gate` is ready for Plan 04-05's D-07 poisoned-candidate-list acceptance test: reason codes (`REJECT_LIQUIDITY`, `REJECT_LISTING_AGE`, `REJECT_SPREAD`, `REJECT_CORRELATION`) match the fixture design in 04-RESEARCH.md Q6 exactly.
- Full suite green at 311 tests (295 baseline + 16 new).
- No blockers for Plan 04-03 (position sizer), which consumes this plan's `accepted` list shape (`asset_class`/`exit_profile_tag`-tagged candidate dicts).

---
*Phase: 04-risk-gate-sizer*
*Completed: 2026-07-26*

## Self-Check: PASSED

- FOUND: trader/risk/gate.py
- FOUND: tests/test_risk_gate.py
- FOUND: 437e194
- FOUND: 7a7ed16
- FOUND: 9835b04
