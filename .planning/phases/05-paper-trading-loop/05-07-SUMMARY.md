---
phase: 05-paper-trading-loop
plan: 07
subsystem: trading-engine
tags: [paper-trading, daily-report, crash-recovery, reconciliation, breakers, integration-test]

# Dependency graph
requires:
  - phase: 05-01
    provides: paper_orders/paper_positions/paper_trades/strategy_kill_state ledger surface, get_all_unresolved_orders, heal_order
  - phase: 05-02
    provides: ops_log.compute_run_coverage, ops-log entry-type vocabulary (scheduled_auth vs manual_restart_required)
  - phase: 05-04
    provides: reconcile.is_entry_halted/run_reconcile_once, clear_halt.clear_entry_halt
  - phase: 05-05
    provides: guardian.run_guardian_once's persist-before-submit exit sequence
  - phase: 05-06
    provides: entry_pipeline.run_entry_pipeline_once's STEP 0 unscoped heal pass, assign_exit_profile's symbol-only hash
provides:
  - "trader/paper/daily_report.py: compute_paper_section(conn, as_of=None) -> markdown lines (positions/trades/breaker+halt state/retired strategies/Manual Interventions tally/coverage)"
  - "trader/ground_truth/report.py's main(): appends the paper-trading section to the same reports/{date}.md file, degrading safely on any Phase 5 failure"
  - "tests/test_recovery.py: the end-to-end multi-day crash/halt/clear/heal proof (entry + exit sides) and the composed breaker-trip -> zero-orders proof"
affects: [05-08-ops-checkpoint, 05-09-registration-checkpoint]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "compute_paper_section never raises on a schema-present-but-empty DB; a genuinely missing-table DB (Phase 5 never executed) is Phase 0 report.py's problem to catch via try/except, not this module's (T-05-12)"
    - "reconciliation_log.ts/breaker_events.ts default to SQLite's datetime('now') string shape (space-separated, no offset) -- the Manual Interventions window bound is rendered in that exact shape (_sql_ts), never Python's isoformat() shape, to keep the '>=' comparison a correct string comparison"
    - "guardian's exit-side heal only runs when _submit_exit is actually invoked (i.e. the exit condition still evaluates true on the later tick) -- unlike entry_pipeline's unconditional STEP 0, there is no unscoped standalone exit-heal pass, so Test 2 relies on the condition re-firing on day 2, not a non-re-firing fixture"
    - "STEP 0's non-re-firing day-2 fixture independently breaks BOTH the volume-surge and the close-breakout conditions on its appended 36th bar, so the test is not a borderline case riding on a single condition"

key-files:
  created:
    - trader/paper/daily_report.py
    - tests/test_paper_daily_report.py
    - tests/test_recovery.py
  modified:
    - trader/ground_truth/report.py

key-decisions:
  - "get_manual_reconciliation_events/get_manual_breaker_events live in trader/paper/daily_report.py itself (Claude's discretion per the plan), not trader/paper/ledger.py -- both are single-purpose, report-only reads with no other caller, and keeping them here avoids growing ledger.py's surface for a Phase-5-reporting-only concern"
  - "report.py's main() opens its OWN fresh connection to data/trader.db for the paper section (via trader.ground_truth.db.get_connection, the same wrapper main() already uses elsewhere in the file) rather than reusing the connection already closed earlier in the function -- self-contained, and consistent with the lazy-import requirement"
  - "the Manual Interventions window-bound timestamp is rendered via a dedicated _sql_ts helper matching SQLite's datetime('now') output shape exactly, rather than Python's datetime.isoformat() -- an isoformat() bound would have silently mis-ordered every row (ASCII ' ' < 'T'), incorrectly excluding same-day human interventions from the tally (caught while writing tests/test_paper_daily_report.py, fixed before commit, Rule 1)"
  - "Test 2 (guardian exit-side) does not attempt RESIDUAL BLOCKER 1's non-re-firing shape -- guardian's heal is reached only through _submit_exit, which is only invoked when evaluate_position_exit still fires on the later tick (an architectural property of guardian.py, not a gap in this plan's scope); the plan's own acceptance criteria scope the non-re-firing/all-five-profile requirements to Test 1 only"

requirements-completed: [PAPER-07]

# Metrics
duration: 65min
completed: 2026-07-27
---

# Phase 05 Plan 07: Paper-Trading Daily Report + Crash-Recovery Integration Proof Summary

**Daily report gains an auditable Paper Trading section (positions, closed trades, breaker/halt state, retired strategies, a Manual Interventions tally excluding scheduled_auth, and scheduled-run coverage), and the crash-recovery contract is proven end to end across a simulated multi-day process restart with all five live strategy profiles and a symbol that genuinely never re-fires.**

## Performance

- **Duration:** 65 min
- **Tasks:** 2
- **Files modified:** 4 (3 new, 1 extended)

## Accomplishments

- `compute_paper_section(conn, as_of=None)`: builds "## Paper Trading" markdown with Open Positions, Recent Closed Trades (5 most recent per each of the five `LIVE_STRATEGY_CONFIGS` profiles, never a single global limit so no one hot config crowds out the others), Breaker/Halt State, Retired Strategies, a Manual Interventions tally (W2 — `reconciliation_log` + `breaker_events` rows with `actor='human'`, sorted by timestamp, `'scheduled_auth'` ops-log entries structurally unreachable since they live in a different store), and Scheduled-Run Coverage (guardian's 5-minute cadence, the tightest of the three, as the representative one). Never raises on a completely empty (but schema-present) database.
- `trader/ground_truth/report.py`'s `main()`: lazily imports `trader.paper.daily_report` (never at module level) after `write_report_markdown` runs, opens its own connection, appends the paper section to the same `reports/{date}.md` file, and degrades to "no paper section this run" on any exception (missing Phase 5 tables in an older/fresh DB) — proven by two dedicated tests (a deliberately-broken import path, and a `compute_paper_section` that raises).
- `tests/test_recovery.py` Test 1 (RESIDUAL BLOCKER 1, entry side): all five real `LIVE_STRATEGY_CONFIGS` live (no retirement anywhere in the test), a fixed symbol (AAPL) fires day 1 via the loose momentum signal and is submitted through the real gate → sizer → round → persist → broker sequence; the broker fill is simulated, but the process "crash" is simulated by reverting the order to `pending_submit` and deleting its `paper_positions` row; `run_reconcile_once` then correctly halts on the unexplained broker-side position; `clear_halt.clear_entry_halt` clears it and the `manual_restart_required` ops-log line is asserted directly; day 2's bars for the SAME symbol are proven — via a direct `scan_candidates` assertion executed BEFORE `run_entry_pipeline_once` is ever called for day 2 — to not re-fire (both the volume-surge and close-breakout conditions independently fail on the appended day-2 bar); the day-2 run's `"healed"` list, `placeOrder`'s call count (exactly 1 across both days), the healed order's `perm_id`, and the single resulting open position are all asserted.
- Test 2 (BLOCKER 1, exit side): the identical persist-before-submit + date-independent heal shape around `run_guardian_once` and a `'sell'` order_ref, advancing a real calendar date between the "crash" tick and the healing tick, asserting `placeOrder`'s call count stays at 1 and exactly one `paper_trades` row exists post-heal.
- Test 3 (W4, composed breaker-trip): a real `trader.risk.breakers.evaluate_breakers` + `record_breaker_transitions(conn, previous_state, evaluation)` call (never via the guardian, isolating the exact mechanism) trips `drawdown`; the very next `run_entry_pipeline_once` call submits zero orders and returns `"halted": True`, even with a fresh candidate that would otherwise clear gate and sizer.
- Full suite verification per the plan's explicit "no deselect" requirement: `python -m pytest tests/ -q` (no `--deselect`, unlike every prior Phase 5 plan's own quick-loop convention) — **511 passed, 0 deselected**, including `tests/test_backtest_sanity.py` (confirmed independently at 1 passed in ~32s).

## Task Commits

Each task was committed atomically:

1. **Task 1: Paper-trading daily report section, including Manual Interventions tally** - `d9479e5` (feat)
2. **Task 2: Realistic multi-day, non-re-firing crash-recovery integration test (RESIDUAL BLOCKER 1) + composed breaker-trip test (W4)** - `5ca9282` (test)

**Plan metadata:** (this commit, docs)

## Files Created/Modified

- `trader/paper/daily_report.py` (new) - `compute_paper_section`, `get_manual_reconciliation_events`, `get_manual_breaker_events`, `_sql_ts`, `_fmt`
- `trader/ground_truth/report.py` (modified) - `main()` extended with a lazily-imported, try/except-wrapped paper-section append after `write_report_markdown`
- `tests/test_paper_daily_report.py` (new) - 17 tests: positions/closed-trades listing, halted-state reporting (true/false + cause), retired-strategies listing, Manual Interventions tally (human clears + human breaker restarts, `scheduled_auth` exclusion), coverage line presence, empty-DB never-raises, and `report.main()`'s degrade-safely behavior (broken import, raising `compute_paper_section`, and the successful-append happy path)
- `tests/test_recovery.py` (new) - 3 integration tests: the realistic multi-day RESIDUAL BLOCKER 1 entry-side scenario, the equivalent guardian exit-side scenario, and the composed W4 breaker-trip proof
- `requirements.txt` - unchanged; `ib_async==2.1.0`/`pandas-market-calendars==5.4.0` verified already pinned (05-02/05-03), not re-added

## Decisions Made

See `key-decisions` in the frontmatter above (helper function placement in `daily_report.py` rather than `ledger.py`; report.py's own fresh connection for the paper section; the `_sql_ts` timestamp-format fix; Test 2's scope boundary relative to Test 1's non-re-firing requirement).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Manual Interventions window-bound timestamp format mismatch**
- **Found during:** writing `tests/test_paper_daily_report.py`'s manual-interventions tests
- **Issue:** `reconciliation_log.ts`/`breaker_events.ts` both default to SQLite's `datetime('now')`, which renders as `"YYYY-MM-DD HH:MM:SS"` (space separator, no UTC offset) — not Python's `datetime.isoformat()` shape (`"...THH:MM:SS+00:00"`). A naive `WHERE ts >= ?` comparison using an `isoformat()`-rendered window bound would silently misorder rows (ASCII `' '` (0x20) sorts before `'T'` (0x54)), incorrectly excluding same-day human interventions from the tally — a real, if subtle, correctness bug that would have made the two-week exit gate's "zero manual interventions" audit undercount.
- **Fix:** Added `_sql_ts(dt)`, which renders the window bound in SQLite's own `datetime('now')` shape before it is ever used as a bind parameter, keeping the `>=` comparison a correct string comparison.
- **Files modified:** `trader/paper/daily_report.py`
- **Commit:** `d9479e5`

## Issues Encountered

- The first draft of `tests/test_paper_daily_report.py`'s `report.main()` degrade-safely tests initially "succeeded" for the wrong reason: a fresh `tmp_path`'s `data/trader.db` genuinely has no Phase 5 tables yet (since `trader.ground_truth.db.get_connection` never runs the migration runner), so `compute_paper_section` would raise regardless of the deliberately-broken import — the test wasn't isolating the failure mode it claimed to prove. Fixed by pre-applying every migration (via a `_apply_phase5_schema` test helper resolving `migrations/` by an ABSOLUTE path, since these tests `chdir` into `tmp_path`) before each degrade-safely test, so the ONLY failure mode each test exercises is the one it names.
- Setting `sys.modules["trader.paper.daily_report"] = None` alone did not reliably force an `ImportError` once the module had already been imported earlier in the same test session — Python's `from X import Y` resolves via `getattr(X, "Y")` first, only falling back to a fresh submodule import when that attribute is absent. Fixed by also `monkeypatch.delattr`-ing the cached `daily_report` attribute off the `trader.paper` package object before setting the `sys.modules` entry to `None`.
- `tests/test_recovery.py`'s autouse fixture initially mocked `entry_pipeline.ops_log.append_ops_log` directly (mirroring `tests/test_entry_pipeline.py`'s own convention) — but `entry_pipeline.ops_log` and `clear_halt`'s own `ops_log` reference are the SAME shared module object, so this silently swallowed `clear_halt.clear_entry_halt`'s `manual_restart_required` ops-log write that Test 1 asserts on directly. Fixed by leaving `ops_log.append_ops_log` real and instead `chdir`-ing each test into its own `tmp_path` (as the first statement in the test body, after all fixtures — including `paper_conn`, whose migration-runner lookup is itself cwd-relative — have already finished setup), mirroring `tests/test_reconciliation.py`'s own established convention.

None of the above required Rule 4 architectural sign-off — all were test-construction corrections or a self-contained, single-function timestamp-format fix within the plan's own literal design.

## User Setup Required

None. No external service configuration required.

## Next Phase Readiness

- The daily report's Paper Trading section is live and will render real data from `reports/{date}.md` once 05-08/05-09 begin the actual overnight paper run.
- The crash-recovery contract (entry side STEP 0, exit side guardian heal, and the Phase-4-breaker-halt composed proof) is now proven end to end at the process-restart level, not just at the unit level — closing the plan-checker's residual review finding.
- This is the last autonomous plan before the two human checkpoints (05-08 ops, 05-09 registration) — no blockers identified.

---
*Phase: 05-paper-trading-loop*
*Completed: 2026-07-27*

## Self-Check: PASSED

- FOUND: trader/paper/daily_report.py
- FOUND: tests/test_paper_daily_report.py
- FOUND: tests/test_recovery.py
- FOUND: trader/ground_truth/report.py (modified)
- FOUND commit: d9479e5
- FOUND commit: 5ca9282
- Full suite: 511 passed, 0 deselected (test_backtest_sanity.py included and passing)
