---
phase: 02-backtest-harness
plan: 03
subsystem: testing
tags: [metrics, sharpe, profit-factor, drawdown, markdown-report]

# Dependency graph
requires:
  - phase: 02-backtest-harness (plan 01)
    provides: "trader/backtest/config.py conventions and migration-based backtest_trades row shape (pnl, fees, exit_ts) that compute_metrics consumes"
provides:
  - "trader/backtest/metrics.py: profit_factor(pnls), sharpe_ratio(daily_returns), max_drawdown(equity_curve), compute_metrics(trades, starting_equity) -> dict, write_report(run_id, metrics, strategy_id, base_dir) -> Path"
affects: [02-06, 02-08, 02-10]

# Tech tracking
tech-stack:
  added: []
  patterns: ["hand-worked golden fixture as the primary correctness oracle for finance math (no empyrical dependency)", "explicit None/inf edge-case policy documented in the module docstring, each case proven by a named test"]

key-files:
  created:
    - trader/backtest/metrics.py
    - tests/test_backtest_metrics.py
  modified: []

key-decisions:
  - "Daily equity curve is built from raw pnl per exit_ts date (not net of fees), matching the plan's hand-worked golden fixture exactly; fees are reported separately via total_fees_paid"
  - "compute_metrics([]) sets every metric to None except trade_count=0 and total_fees_paid=0.0 (a defined empty sum, not an undefined ratio)"
  - "ddof=1 pinned explicitly (statistics.stdev default) per Assumption A3, not left implicit"
  - "compute_metrics signature kept as (list[dict], starting_equity) -> dict per the key_link requirement, ready for 02-06's compute_metrics_by_strategy to wrap verbatim"

patterns-established:
  - "Golden-fixture-first TDD for quantitative modules: literal hand-worked trade lists pinned directly in the test file, not loaded from fixtures, so the arithmetic is auditable inline"

requirements-completed: [BACK-06]

# Metrics
duration: ~12min
completed: 2026-07-26
---

# Phase 2 Plan 3: Backtest Metrics Module Summary

**compute_metrics(trades) and write_report() implementing profit factor, Sharpe, max drawdown, win rate, avg win/loss, trade count, and total fees, each formula cross-checked against a hand-worked golden fixture rather than trusted on sight.**

## Performance

- **Duration:** ~12 min
- **Completed:** 2026-07-26
- **Tasks:** 1 completed (TDD: RED -> GREEN)
- **Files modified:** 2 (both created)

## Accomplishments
- `trader/backtest/metrics.py` implements `profit_factor`, `sharpe_ratio` (`ddof=1` pinned explicitly), `max_drawdown`, `compute_metrics`, and `write_report`, matching two independent hand-worked golden fixtures (profit factor/win rate/avg win-loss/max drawdown/fees, and Sharpe) to `pytest.approx` tolerance
- Every documented edge case (zero losing trades -> `math.inf`, zero trades -> `None` everywhere except `trade_count`/`total_fees_paid`, fewer than two return observations -> `None`) is covered by a named, passing test rather than left to accidental `ZeroDivisionError`/`NaN`
- `write_report` creates the base directory if missing and writes a real markdown file with a `# Backtest Report` heading and every metric key rendered in the body, verified against a `tmp_path` fixture
- Full 97-test suite green (80 pre-existing + 17 new), no regressions

## Task Commits

Each task was committed atomically (TDD RED -> GREEN):

1. **Task 1: compute_metrics with golden fixture and edge cases (BACK-06, D-13)** - `7a4a85e` (test), `444edad` (feat)

_Single TDD task; no refactor commit was needed — GREEN implementation required no cleanup pass._

## Files Created/Modified
- `trader/backtest/metrics.py` - profit_factor, sharpe_ratio, max_drawdown, _build_daily_equity_curve, compute_metrics, write_report
- `tests/test_backtest_metrics.py` - 17 tests: golden fixture A (6 assertions + exact-key-set check), golden fixture B (Sharpe), 5 edge-case tests, 3 write_report tests

## Decisions Made
- Equity curve sums raw `pnl` per `exit_ts` date (not `pnl - fees`) so the curve matches the plan's literal expected values `[1000, 1100, 1050, 1250, 1220, 1200]`; fees remain a separate reported total rather than folded into drawdown math
- `total_fees_paid` on zero trades returns `0.0` rather than `None` — an empty sum is a defined answer, distinguishing it from the genuinely undefined ratios (profit factor, Sharpe, drawdown, win rate, avg win/loss)
- Kept `compute_metrics`'s signature exactly `(trades: list[dict], starting_equity: float = 100_000.0) -> dict` per the plan's key_link note, so 02-06's `ledger.compute_metrics_by_strategy` can wrap it verbatim per strategy_id group without a breaking change

## Deviations from Plan

None - plan executed exactly as written. All golden-fixture values, edge-case policies, and the write_report contract matched the plan's `<behavior>` block without needing reinterpretation.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `trader.backtest.metrics.compute_metrics` and `write_report` are import-ready for plan 02-06 (`ledger.compute_metrics_by_strategy`), plan 02-08 (`runner.py`), and plan 02-10 (`run_momentum_placeholder.py`)
- No blockers for subsequent waves

---
*Phase: 02-backtest-harness*
*Completed: 2026-07-26*

## Self-Check: PASSED

`trader/backtest/metrics.py` and `tests/test_backtest_metrics.py` verified present on disk; commit hashes `7a4a85e` and `444edad` verified in `git log --oneline`.
