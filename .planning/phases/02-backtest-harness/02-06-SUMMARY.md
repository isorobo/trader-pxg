---
phase: 02-backtest-harness
plan: 06
subsystem: database
tags: [sqlite, backtest, ledger, reproducibility, attribution]

# Dependency graph
requires:
  - phase: 02-backtest-harness (02-01)
    provides: backtest_runs/backtest_trades schema (migrations/0003_backtest.sql)
  - phase: 02-backtest-harness (02-03)
    provides: trader.backtest.metrics.compute_metrics (stable list[dict] -> dict contract)
provides:
  - "trader/backtest/ledger.py: record_run, record_trade, get_trades_for_run, get_trades_for_strategy, compute_metrics_by_strategy"
  - "Reproducibility guarantee (D-12): identical seed+params+data yields identical trade content across separate DBs"
  - "Per-strategy attribution grouping (BACK-06), proven not to leak trades across strategy_id"
affects: [02-08 (runner.py wires record_run/record_trade per fill), 02-10 (report reads params_json), Phase 3, Phase 7]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "code_version stamped by reading .git/HEAD directly (no subprocess/shell-out)"
    - "row_factory = sqlite3.Row + dict(row) for list[dict] returns, matching trader/data/db.py"
    - "Grouping helper (compute_metrics_by_strategy) lives in the dependent module (ledger.py) rather than the dependency (metrics.py) to avoid wave/dependency inversion"

key-files:
  created:
    - trader/backtest/ledger.py
    - tests/test_backtest_ledger.py
  modified: []

key-decisions:
  - "Split Task 1 and Task 2 into two atomic feat commits against the same file (record_run/record_trade/get_trades_for_run first, then get_trades_for_strategy/compute_metrics_by_strategy), even though both tasks' tests were written together in one RED commit"
  - "compute_metrics_by_strategy scoped-by-run_ids path filters get_trades_for_strategy's full result in Python rather than adding a second SQL WHERE clause, keeping one query shape reused for both the unscoped and scoped cases"

patterns-established:
  - "code_version resolution helper (_code_version) reads .git/HEAD/refs directly, wrapped in try/except returning \"unknown\" on any failure - no subprocess dependency"

requirements-completed: [BACK-05, BACK-06]

# Metrics
duration: 40min
completed: 2026-07-26
---

# Phase 2 Plan 06: Trade Ledger and Per-Strategy Attribution Summary

**Parameterized trade ledger (record_run/record_trade) with .git/HEAD-based code_version stamping, proven seed+params+data reproducibility, and a per-strategy attribution grouping layer that reuses metrics.compute_metrics without leaking trades across strategy_id.**

## Performance

- **Duration:** 40 min
- **Started:** 2026-07-26T17:07:00+12:00 (approx, RED commit)
- **Completed:** 2026-07-26T17:46:54+12:00
- **Tasks:** 2 completed
- **Files modified:** 2 (1 created source file, 1 created test file)

## Accomplishments
- Every simulated trade lands in `backtest_trades` attributable to a `run_id` and `strategy_id`, written via parameterized `?` placeholders only (no f-string/interpolated SQL)
- Scale-out tranches proven to share `position_id` while each carrying its own fees/slippage/pnl, with per-position totals recoverable via `SUM(pnl)`
- Reproducibility (D-12) proven: identical seed+params+data sequence writes identical trade content (excluding autoincrement/timestamp storage artifacts) across two separate temp databases
- Per-strategy attribution (BACK-06) proven not to leak across `strategy_id`, both for raw trade retrieval and for `compute_metrics_by_strategy`'s grouped metrics dict, with an optional `run_ids` scoping path

## Task Commits

Each task was committed atomically (TDD: one shared RED commit covering both tasks' tests, then one GREEN feat commit per task):

1. **RED (both tasks): failing tests for ledger + per-strategy grouping** - `d276ffa` (test)
2. **Task 1: record_run/record_trade/get_trades_for_run with reproducibility (BACK-05, D-11, D-12)** - `bac779a` (feat)
3. **Task 2: per-strategy attribution grouping (BACK-06)** - `92c6ed7` (feat)

**Plan metadata:** (this commit, docs: complete plan)

_Note: both tasks' behaviors were captured in the single RED test file up front per the plan's action steps; GREEN was then delivered as two separate atomic feat commits, one per task, against the same file._

## Files Created/Modified
- `trader/backtest/ledger.py` - `_code_version` (.git/HEAD reader), `record_run`, `record_trade`, `get_trades_for_run`, `get_trades_for_strategy`, `compute_metrics_by_strategy`
- `tests/test_backtest_ledger.py` - 10 tests covering both tasks: insert/return-id behavior, scale-out tranche grouping, reproducibility, CHECK-constraint wiring, empty-run behavior, and per-strategy grouping/metrics pinning

## Decisions Made
- Read `.git/HEAD` directly (resolving the ref file under `.git/refs/...` when HEAD is symbolic, or using the raw hash for a detached HEAD) rather than shelling out via `subprocess`, per the plan's threat-model disposition (T-02-SC) — proven by a grep gate confirming zero occurrences of the literal string "subprocess" in `ledger.py` (a prose mention in an early docstring draft was reworded to avoid a false-positive against this literal gate)
- `compute_metrics_by_strategy`'s `run_ids`-scoped path discovers distinct `strategy_id`s via a parameterized `IN (...)` clause (placeholders built from `?` repeated per id, values passed as bound parameters — never string-joined), then filters each strategy's full trade list down to the given `run_ids` in Python before calling `compute_metrics`

## Deviations from Plan

None - plan executed exactly as written. One trivial wording adjustment to a docstring (replacing the word "subprocess" in a prose explanation with "shell-out surface") was made before the first commit to satisfy the plan's own acceptance-criteria grep gate; this was not a functional change and is not tracked as a numbered deviation.

## Issues Encountered

The Claude Code process restarted mid-execution after Task 1's GREEN commit (`bac779a`) landed but before Task 2's implementation was committed. On resume, the uncommitted `ledger.py` working-tree state (Task 1 functions already present) was inspected, the 3 then-failing per-strategy tests were confirmed as the expected gap, and Task 2's `get_trades_for_strategy`/`compute_metrics_by_strategy` functions were added and committed (`92c6ed7`) to complete the plan. No work was lost or redone.

## Next Phase Readiness
- `trader/backtest/ledger.py` is ready for plan 02-08's runner to call `record_run` once per backtest and `record_trade` once per fill event
- `compute_metrics_by_strategy` and `get_trades_for_strategy` are ready for Phase 3/7 cross-run reporting to build on, though that reporting layer itself remains out of scope for this plan
- Full test suite green: 135 passed, 0 failed (125 baseline + 10 new in `tests/test_backtest_ledger.py`)

---
*Phase: 02-backtest-harness*
*Completed: 2026-07-26*

## Self-Check: PASSED

- FOUND: trader/backtest/ledger.py
- FOUND: tests/test_backtest_ledger.py
- FOUND: .planning/phases/02-backtest-harness/02-06-SUMMARY.md
- FOUND: d276ffa (test commit)
- FOUND: bac779a (Task 1 feat commit)
- FOUND: 92c6ed7 (Task 2 feat commit)
