---
phase: 05-paper-trading-loop
plan: 04
subsystem: risk
tags: [sqlite, reconciliation, circuit-breaker, cli, ibkr]

# Dependency graph
requires:
  - phase: 05-paper-trading-loop (05-01)
    provides: paper_orders/paper_positions ledger, get_pending_order_qty, reconciliation_log schema
  - phase: 05-paper-trading-loop (05-02)
    provides: ops_log.append_ops_log, alerts.notify
  - phase: 05-paper-trading-loop (05-03)
    provides: IBKRBrokerAdapter.snapshot()
  - phase: 04-risk-management
    provides: trader.risk.breakers.read_breaker_state
provides:
  - classify_divergence pure classification function (conservative T-05-04 default)
  - is_entry_halted combined gate (Phase 4 breakers + Phase 5 reconciliation halt)
  - run_reconcile_once / trader.paper.reconcile --once CLI
  - clear_halt.py, the sole human-invoked CLI that clears a reconciliation halt
    and pairs it with a manual_restart_required ops-log entry
affects: [05-05-guardian, 05-06-entry-pipeline, 05-07-recovery, 05-09-runbook]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure classification function + thin parameterized event-log writer + re-derived state gate (mirrors trader/risk/breakers.py exactly)"
    - "Human-only clear CLI that is the sole writer of one specific action value, verified by a grep-shaped test"

key-files:
  created:
    - trader/paper/reconcile.py
    - trader/paper/clear_halt.py
    - scripts/paper_reconcile.bat
    - scripts/paper_reconcile_task.xml
    - tests/test_reconciliation.py
  modified:
    - .gitignore

key-decisions:
  - "classify_divergence classifies explainable only on an EXACT pending-qty match to abs(delta) -- never a tolerance band (T-05-04)"
  - "clear_entry_halt gained an optional log_path parameter (not exposed on the CLI, which stays --reason/--db-path only) so tests can assert the ops-log write without touching the real ops/ directory"
  - "gitignored ops/ (trader.paper.ops_log's runtime output) since a reconciliation test's real alerts.notify() fallback path writes there when Telegram env vars are unset"

patterns-established:
  - "Pattern: reconciliation as pure classification, mirroring trader/risk/breakers.py's evaluate_breakers/append_breaker_event/read_breaker_state split"
  - "Pattern: sole human-clear CLI (clear_halt.py) that is the only writer of a specific action literal, enforced by an AST/grep test scanning the rest of the package"

requirements-completed: [PAPER-04]

# Metrics
duration: 45min
completed: 2026-07-27
---

# Phase 5 Plan 4: Reconciliation Classification + Halt Gate + clear_halt CLI Summary

**Conservative broker/local reconciliation classifier feeding a combined Phase 4 + Phase 5 entry-halt gate, with the sole human-invoked CLI to clear it always logging the intervention.**

## Performance

- **Duration:** ~45 min
- **Tasks:** 2
- **Files modified:** 6 (5 created, 1 modified)

## Accomplishments
- `classify_divergence` classifies a broker/local qty delta "explainable" only when it exactly equals a known pending order quantity (never a tolerance band, T-05-04's conservative default) -- proven by a dedicated partial-mismatch test case.
- `is_entry_halted` re-derives its answer fresh on every call from both `trader.risk.breakers.read_breaker_state` (Phase 4's daily_loss/drawdown/consecutive_loss) and Phase 5's `reconciliation_halt_state` view -- no cached boolean anywhere in the module (standing rule 4).
- `run_reconcile_once` wires `ledger.get_open_positions`/`get_pending_order_qty` (consumed unchanged, never redefined) and `IBKRBrokerAdapter.snapshot()` into the classifier, fires `alerts.notify("error", ...)` for every unexplained divergence, and records an optional crypto Kraken read-only check as informational/log-only, never halting.
- `clear_halt.py`'s `clear_entry_halt` is the sole function in the codebase permitted to end a reconciliation halt, and always appends a `manual_restart_required` ops-log entry with the same reason as its last step in the same call (BLOCKER 3) -- the two-week zero-manual-interventions audit reads entirely from the ops log.
- `scripts/paper_reconcile.bat` + `scripts/paper_reconcile_task.xml` (PT1M/60-second cadence) authored, cloned from `scripts/poll.bat`/`poll_task.xml`'s shape; `schtasks` registration deferred to the 05-09 human checkpoint.

## Task Commits

Each task was committed atomically:

1. **Task 1: classify_divergence + is_entry_halted + --once CLI**
   - `1a2ea17` (test) - add failing tests
   - `5853f09` (feat) - implement reconcile.py + scripts
2. **Task 2: Human-only halt clear CLI + manual_restart_required ops-log producer**
   - `319ed83` (feat) - implement clear_halt.py (includes its tests)

_Note: Task 1 is `tdd="true"` per the plan (RED then GREEN commits); Task 2 has no `tdd` attribute in the plan, so its tests and implementation landed in one commit._

## Files Created/Modified
- `trader/paper/reconcile.py` - classify_divergence, record_reconciliation, is_entry_halted, run_reconcile_once, `--once` CLI
- `trader/paper/clear_halt.py` - clear_entry_halt (sole halt-clearing writer + ops-log pairing) and its CLI
- `scripts/paper_reconcile.bat` - Task Scheduler action target for the reconciliation loop
- `scripts/paper_reconcile_task.xml` - Task Scheduler definition, PT1M cadence, IgnoreNew/LeastPrivilege, cloned from `poll_task.xml`
- `tests/test_reconciliation.py` - 36 tests covering classification, persistence, the halt gate, `run_reconcile_once`, and `clear_halt.py`
- `.gitignore` - added `ops/` (see Deviations)

## Decisions Made
- `classify_divergence` uses an exact-match rule (`pending_qty.get(symbol) == abs(delta)`) rather than any tolerance band, per T-05-04 -- a partial mismatch (e.g. local=10, broker=7, pending=10) is always "unexplained".
- `clear_entry_halt(conn, reason, log_path=...)` exposes an optional `log_path` parameter defaulting to `ops/paper_trading.log`, not surfaced on the CLI (which stays `--reason`/`--db-path` only, identical to `clear_breaker.py`'s shape) -- this keeps the function unit-testable without writing into the real project `ops/` directory, while production behavior via `main()` is unchanged.
- Kraken read-only check's exact adapter interface is duck-typed as `crypto_adapter.check_readonly() -> {"symbol", "local_qty", "broker_qty", "reason"}` since no concrete Kraken adapter module exists yet in this codebase; `run_reconcile_once` only calls it if `crypto_adapter` is provided (default `None`), and always records the result as `venue='kraken_readonly'`/`classification='informational'`/`action='log'`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing hygiene] Gitignored `ops/`, the ops-log's runtime output directory**
- **Found during:** Task 1 (writing `test_run_reconcile_once_records_unexplained_and_halts`)
- **Issue:** `run_reconcile_once`'s real `alerts.notify("error", ...)` call falls back to `ops_log.append_ops_log` at its default relative path (`ops/paper_trading.log`) whenever Telegram env vars are unset -- a first test run left an untracked `ops/paper_trading.log` in the actual project working tree.
- **Fix:** Added `monkeypatch.chdir(tmp_path)` (plus clearing the Telegram env vars) to the affected test so it never touches the real project directory, deleted the accidentally-generated `ops/` directory, and added `ops/` to `.gitignore` (mirrors the existing `reports/` D-12 convention for other generated runtime output).
- **Files modified:** `tests/test_reconciliation.py`, `.gitignore`
- **Verification:** Full suite re-run confirms no untracked files after any test run (`git status --short` clean).
- **Committed in:** `5853f09` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 hygiene/Rule 2)
**Impact on plan:** No scope creep -- both fixes were needed to keep the test suite from polluting the working tree, a correctness requirement for a repeatable CI/local test run.

## Issues Encountered
- `trader.paper.ops_log`'s module-level `_LOGGERS` cache is keyed by the literal log-path string, not a resolved absolute path -- a test that `chdir`s and re-uses the module's default relative path can silently reuse a handler opened against an earlier test's `tmp_path`. Rather than modify `ops_log.py` (out of this plan's file scope, already shipped in 05-02), the `clear_halt` end-to-end CLI test was written to assert the `ops_log.append_ops_log` call via `unittest.mock.patch` (matching `tests/test_alerts.py`'s own established convention for `notify()`-level assertions) instead of reading a real log file across a `chdir` boundary.

## User Setup Required

None - no external service configuration required. `schtasks` registration of `scripts/paper_reconcile_task.xml` is deferred to the 05-09 human checkpoint per this phase's structure.

## Next Phase Readiness
- `trader.paper.reconcile.is_entry_halted` is ready for 05-06's entry pipeline to consult before every submit.
- `trader.paper.clear_halt` is ready to be documented in 05-09's runbook alongside the existing `trader.risk.clear_breaker` companion-step note already embedded in its module docstring.
- 05-07's recovery test can exercise the `'pending_submit'`-only-trace-is-unexplained path directly against `classify_divergence`/`run_reconcile_once` as already proven here at the classifier level.

---
*Phase: 05-paper-trading-loop*
*Completed: 2026-07-27*

## Self-Check: PASSED

All created files found on disk; all three task commit hashes (`1a2ea17`, `5853f09`, `319ed83`) found in `git log`.
