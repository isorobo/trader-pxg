---
phase: 05-paper-trading-loop
plan: 02
subsystem: infra
tags: [pandas-market-calendars, ib_async, telegram, requests, logging, argparse, ops-log]

requires:
  - phase: 05-paper-trading-loop
    provides: "05-01's migration 0005 (paper_orders/positions/trades/strategy_kill_state) and idempotency/ledger surface, plus frozen trader/paper/config.py (TELEGRAM_BOT_TOKEN_ENV/TELEGRAM_CHAT_ID_ENV)"
provides:
  - "trader/paper/calendar_.py: is_trading_day(date) / session_window(date) NYSE gate via pandas-market-calendars"
  - "trader/paper/alerts.py: send_telegram_alert (fire-and-forget, never raises, never logs secrets) and notify() (ops-log-durable alert wrapper)"
  - "trader/paper/ops_log.py: append_ops_log, compute_run_coverage, and a runnable CLI (python -m trader.paper.ops_log) for scheduled_auth/manual_restart_required entries"
  - "ib_async==2.1.0 and pandas-market-calendars==5.4.0 installed in .venv and pinned in requirements.txt"
affects: [05-06-entry-pipeline, 05-04-reconcile, 05-07-daily-report, 05-08-telegram-checkpoint, 05-09-runbook]

tech-stack:
  added: [pandas-market-calendars==5.4.0, ib_async==2.1.0]
  patterns:
    - "Fire-and-forget alerting: catch every Exception, always return bool, never raise into trading logic (D-11)"
    - "Never log a secret's raw value, even the exception's own message string, when that message could itself embed the secret (e.g. requests.HTTPError embedding the request URL) -- log only type(error).__name__ and the alert text"
    - "Pipe-delimited rotating ops log (iso_ts|entry_type|message), one dedicated module-level logger cached per log_path, entry_type validated against a fixed known-set before write"
    - "argparse choices= as the CLI-level validation gate, so an invalid --entry-type never reaches the append function's ValueError path"

key-files:
  created:
    - trader/paper/calendar_.py
    - trader/paper/alerts.py
    - trader/paper/ops_log.py
    - tests/test_calendar.py
    - tests/test_alerts.py
  modified:
    - requirements.txt

key-decisions:
  - "Followed the plan's explicit override of 05-RESEARCH.md's Telegram code sample: the failure log line omits str(error) entirely (only type(error).__name__ + the alert text), because requests.exceptions.HTTPError's own message can embed the request URL -- which contains the bearer token. Verified with a dedicated test that mocks raise_for_status() to raise an HTTPError whose message contains the token, confirming it never reaches the log."
  - "ops_log entry_type validation lives at two layers: argparse choices= at the CLI boundary (clean usage error, no traceback) and a plain ValueError guard inside append_ops_log for any non-CLI caller -- matching the plan's explicit 'not a DB CHECK constraint' guidance."
  - "One dedicated logger per log_path, cached module-level, rather than a single fixed-path logger -- needed so tests can point at independent tmp_path log files without cross-test handler collisions, while still matching the plan's 'configured once' intent per path."

requirements-completed: [PAPER-06, PAPER-07]

duration: ~20min
completed: 2026-07-26
---

# Phase 5 Plan 2: NYSE Calendar, Telegram Alerts, and Ops Log with CLI Summary

**NYSE trading-day gate via pandas-market-calendars, a token-safe Telegram fire-and-forget alerter with ops-log fallback, and a rotating ops log exposing a `python -m trader.paper.ops_log` CLI so D-13's weekly IBKR 2FA tap is logged as `scheduled_auth`, distinct from `manual_restart_required`.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-26
- **Tasks:** 2
- **Files modified:** 6 (3 created source modules, 2 created test files, 1 modified requirements.txt)

## Accomplishments
- `trader/paper/calendar_.py` correctly gates a real NYSE holiday (New Year's Day 2026) and a weekend, returns UTC-aware `session_window` bounds, and never raises on `is_trading_day` for any date input.
- `trader/paper/alerts.py` never raises on a Telegram failure (including a mocked `Timeout` and a mocked `HTTPError` whose own message embeds the token in the URL) and never logs the token/chat_id in any code path.
- `trader/paper/ops_log.py` distinguishes `scheduled_auth` from `manual_restart_required`, computes `scheduled_run`-only coverage stats (mirrors `trader.ground_truth.db.query_poll_run_coverage`'s shape), and ships a runnable CLI producer for BLOCKER 2.
- `ib_async==2.1.0` and `pandas-market-calendars==5.4.0` installed into the project `.venv` and pinned in `requirements.txt`, unblocking Wave 2's offline-fast startup.

## Task Commits

Each task was committed atomically (TDD RED -> GREEN per task):

1. **Task 1: NYSE trading calendar wrapper**
   - `e1bab3c` test(05-02): add failing tests for NYSE trading calendar wrapper
   - `2f4ea21` feat(05-02): implement NYSE trading calendar wrapper
2. **Task 2: Telegram alerts + rotating ops log + CLI producer**
   - `a6ed48b` test(05-02): add failing tests for Telegram alerts + ops log + CLI
   - `fe24f7c` feat(05-02): implement Telegram alerts, rotating ops log, and ops_log CLI

**Plan metadata:** (this commit) docs(05-02): complete NYSE calendar / alerts / ops log plan

_TDD gate sequence verified: each task has a `test(...)` commit (RED, confirmed failing via ImportError before commit) followed by a `feat(...)` commit (GREEN, confirmed passing after commit)._

## Files Created/Modified
- `trader/paper/calendar_.py` - `is_trading_day(date) -> bool`, `session_window(date) -> (open_utc, close_utc)` via `pandas_market_calendars.get_calendar("NYSE")`
- `trader/paper/alerts.py` - `send_telegram_alert(token, chat_id, text) -> bool` (fire-and-forget) and `notify(entry_type, message) -> bool` (ops-log-durable wrapper)
- `trader/paper/ops_log.py` - `append_ops_log`, `compute_run_coverage`, `main(argv=None)` CLI, `_KNOWN_ENTRY_TYPES`
- `tests/test_calendar.py` - 6 tests covering Task 1's `<behavior>` list
- `tests/test_alerts.py` - 12 tests covering Task 2's `<behavior>` list, including two dedicated token-leak guards
- `requirements.txt` - added `ib_async==2.1.0` and `pandas-market-calendars==5.4.0`

## Decisions Made
- The failure-path log call in `send_telegram_alert` omits `str(error)` entirely, deviating from 05-RESEARCH.md's illustrative code sample (which does interpolate the exception's message). This follows the PLAN's more specific, revised action text ("log.warning with type(error).__name__ and the message text only -- never token or chat_id") and the threat model's T-05-02 mitigation. Added a dedicated test (`test_failed_send_via_http_error_never_logs_the_token`) proving this holds even when `raise_for_status()`'s own `HTTPError` message embeds the token in the request URL -- the worst-case leak vector the research example's naive `%s`, `error` interpolation would have exposed.
- `ops_log`'s dedicated logger is cached per `log_path` (a small dict keyed on path) rather than a single fixed-path module logger, so tests using independent `tmp_path` files never collide on a shared handler while still matching the plan's "module-level, configured once" intent.

## Deviations from Plan

None - plan executed exactly as written. The one detail worth flagging explicitly (not a deviation, a clarification): the Telegram failure-log wording follows the PLAN's `<action>` text rather than 05-RESEARCH.md's `<Code Examples>` sample, since the plan's text is the more specific and more recently revised instruction and the research sample would have leaked the token via `HTTPError`'s message on certain failure paths.

## Issues Encountered
None. Both new dependencies (`ib_async==2.1.0`, `pandas-market-calendars==5.4.0`) installed cleanly into the existing `.venv` with no version conflicts affecting the full test suite (the transitive `tzdata` downgrade from 2025->2026 pinned range via `exchange-calendars` did not break any test).

## User Setup Required
None - no external service configuration required for this plan. (Telegram bot token/chat ID remain a Plan 05-08 human checkpoint; `alerts.notify()` already degrades gracefully to the ops log alone when they are unset, verified by test.)

## Next Phase Readiness
- `trader/paper/calendar_.py` is ready for 05-06's entry-pipeline trading-day gate.
- `trader/paper/alerts.py`/`ops_log.py` are ready for every Phase 5 process (entry pipeline, guardian, reconcile) to call `notify()`/`append_ops_log()` for fills, errors, heartbeats, and halts.
- The owner now has a concrete CLI (`python -m trader.paper.ops_log --entry-type scheduled_auth --message "..."`) to run after every weekly IBKR 2FA tap (D-13) and after every `clear_breaker` invocation (BLOCKER 2/3) -- both Plan 05-07's daily-report tally and Plan 05-09's runbook can rely on this being the durable record.
- `ib_async` is installed and pinned, so Wave 2 (broker adapter, entry pipeline) can start without a fresh install step.
- Full test suite: 389 passed (371 pre-existing + 6 calendar + 12 alerts/ops_log), 0 failed.

---
*Phase: 05-paper-trading-loop*
*Completed: 2026-07-26*

## Self-Check: PASSED

All created files confirmed present on disk; all four task commit hashes (e1bab3c, 2f4ea21, a6ed48b, fe24f7c) confirmed present in git log.
