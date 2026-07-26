---
phase: 00-ground-truth
plan: 03
subsystem: scheduler
tags: [pytest, tdd, zoneinfo, sqlite, windows-task-scheduler, argparse]

# Dependency graph
requires:
  - phase: 00-ground-truth (plan 02)
    provides: trader/ground_truth/db.py (get_connection, insert_snapshot_rows, record_poll_run), trader/ground_truth/sources.py (StockGainersSource, CryptoMoversSource, SourceUnavailableError)
provides:
  - trader/ground_truth/poll.py — run_poll_once, is_market_hours, main (the CLI entrypoint that actually satisfies DATA-01)
  - scripts/poll.bat — Task Scheduler launcher (cd /d + explicit venv interpreter)
  - scripts/poll_task.xml — TraderGroundTruthPoll task definition, registered and verified Enabled
  - A live, registered, enabled Windows Task Scheduler task polling every 15 minutes (starts the DATA-04 clock)
affects: [00-04, 00-05]

# Tech tracking
tech-stack:
  added: []
  patterns: [independent try/except per source so one failing feed never blocks the other or the poll_runs write, zoneinfo-based market-hours tag instead of a market-calendar gate, .bat-wrapped Task Scheduler trigger with cd /d + explicit venv interpreter]

key-files:
  created:
    - trader/ground_truth/poll.py
    - tests/test_poll.py
    - scripts/poll.bat
    - scripts/poll_task.xml
  modified: []

key-decisions:
  - "argparse's own required=True on --once produces the D-05 usage-error behavior (exit code 2, stderr message referencing --once) for free — no need for a hand-rolled usage check"
  - "Task Scheduler XML uses P9999D repetition duration to run effectively forever without a daemon process (D-05), with StartWhenAvailable=true so missed triggers (sleep/wake, Pitfall 4) fire as soon as possible rather than being silently dropped"

patterns-established:
  - "Pattern: independent try/except per source adapter inside run_poll_once, so a stock-side SourceUnavailableError never skips the crypto call or the poll_runs write, and vice versa (D-06)"
  - "Pattern: crypto rows always get market_open=1 unconditionally; only stock rows call is_market_hours (crypto never closes)"

requirements-completed: [DATA-01, DATA-02, DATA-04]

# Metrics
duration: 16min
completed: 2026-07-26
---

# Phase 0 Plan 03: Poll Orchestration Entrypoint and Task Scheduler Registration Summary

**poll.py wires StockGainersSource/CryptoMoversSource into db.py behind independent try/except blocks so one missing feed never blocks the other, registered as an enabled 15-minute Windows Task Scheduler task (TraderGroundTruthPoll) with StartWhenAvailable**

## Performance

- **Duration:** 16 min
- **Started:** 2026-07-26T00:20:00Z
- **Completed:** 2026-07-26T00:36:00Z
- **Tasks:** 3
- **Files modified:** 4 (all created)

## Accomplishments
- Wrote 7 failing tests against `trader.ground_truth.poll` before it existed (RED) — collection failed with `ModuleNotFoundError`, confirming the contract was pinned before implementation
- Implemented `poll.py`: `is_market_hours` (stdlib `zoneinfo`, Mon-Fri 09:30-16:00 America/New_York), `run_poll_once` (independent try/except per source, always records a `poll_runs` row even on a total miss), and `main` (argparse `--once` required, D-05 usage-error semantics) — all 7 tests green (GREEN), full suite 24/24
- Built `scripts/poll.bat` (explicit `cd /d` + venv interpreter, Pitfall 3) and `scripts/poll_task.xml` (`TraderGroundTruthPoll`, `PT15M` repetition, `P9999D` duration, `StartWhenAvailable=true`, Assumption A3)
- User ran the D-07 manual registration step: `schtasks /create /tn "TraderGroundTruthPoll" /xml "...\scripts\poll_task.xml" /f`, then verified with `schtasks /query /tn "TraderGroundTruthPoll" /v /fo list` — confirmed `Scheduled Task State: Enabled`, `Repeat: Every: 0 Hour(s), 15 Minute(s)`, `Next Run Time: 26/07/2026 12:45:00 PM`, `Task To Run: ...\scripts\poll.bat`. `Last Result: 267011` is the standard "task has not yet run" sentinel — expected pre-first-run, not an error.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for the poll orchestration entrypoint (RED)** - `5f22187` (test)
2. **Task 2: Implement the poll orchestration entrypoint (GREEN)** - `36fb387` (feat)
3. **Task 3: Create the Task Scheduler launcher, then register it manually (D-07)** - `028bdb6` (feat) — file creation commit; registration itself was a manual `schtasks` step performed by the user, verified via pasted `/query` output, no code to commit for that step

**Plan metadata:** (this commit, following SUMMARY.md write)

## Files Created/Modified
- `tests/test_poll.py` - 7 tests: both-sources-called, stock-failure-doesn't-block-crypto, market-hours true/false, crypto always market_open=1, `--once` calls `run_poll_once` exactly once, missing `--once` exits nonzero
- `trader/ground_truth/poll.py` - `is_market_hours`, `run_poll_once`, `main` — the orchestration entrypoint wiring `sources.py` and `db.py`
- `scripts/poll.bat` - Task Scheduler launcher: `cd /d` to project root, then the venv `python.exe -m trader.ground_truth.poll --once`
- `scripts/poll_task.xml` - `TraderGroundTruthPoll` Task Scheduler definition, `TimeTrigger` + `PT15M` repetition + `StartWhenAvailable=true`

## Decisions Made
- Used argparse's native `required=True` on the `--once` store-true flag instead of a hand-rolled `if not args.once` check — argparse's own parser error already produces exit code 2 and a stderr message referencing `--once`, satisfying D-05's usage-error requirement with less code
- Set `poll_task.xml`'s `Duration` to `P9999D` (effectively unbounded) rather than omitting `Duration`, since Windows Task Scheduler XML requires an explicit duration alongside `Interval` for indefinite repetition

## Deviations from Plan

None - plan executed exactly as written. Task 3's checkpoint (D-07) resolved as designed: files were created and committed automatically, the `schtasks /create` and `schtasks /query` commands were run manually by the user, who confirmed `Scheduled Task State: Enabled` and a 15-minute repeat interval.

## Issues Encountered
None.

## User Setup Required
None beyond the completed D-07 checkpoint — the user has already registered `TraderGroundTruthPoll` and confirmed it is Enabled with a 15-minute repeat interval. No further action required.

## Next Phase Readiness
- `poll.py` is live and scheduled: `TraderGroundTruthPoll` fires every 15 minutes starting at the next quarter-hour, starting the DATA-04 "runs continuously" clock
- `report.py` (Plan 00-04, already executed ahead of this plan) can now be run against real accumulating data instead of an empty database
- No blockers identified for Plan 00-05

---
*Phase: 00-ground-truth*
*Completed: 2026-07-26*

## Self-Check: PASSED

All 4 files created in this plan verified present on disk (`tests/test_poll.py`, `trader/ground_truth/poll.py`, `scripts/poll.bat`, `scripts/poll_task.xml`). All 3 task commit hashes (`5f22187`, `36fb387`, `028bdb6`) verified present in `git log`. Full test suite: 24/24 passing (7 new `test_poll.py` + 17 existing). Task Scheduler registration verified Enabled via the user's pasted `schtasks /query` output (D-07 checkpoint resolved).
