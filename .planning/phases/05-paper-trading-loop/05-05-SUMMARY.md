---
phase: 05-paper-trading-loop
plan: 05
subsystem: trading-engine
tags: [paper-trading, exit-management, circuit-breakers, kill-conditions, ibkr, ccxt, telegram]

# Dependency graph
requires:
  - phase: 05-01
    provides: paper_orders/paper_positions/paper_trades/strategy_kill_state ledger surface, persist-before-submit order lifecycle, date-independent get_unresolved_orders/heal_order
  - phase: 05-02
    provides: alerts.notify (Telegram + ops-log fallback), ops_log's pipe-delimited entry format
  - phase: 05-03
    provides: IBKRBrokerAdapter (place_order/snapshot/latest_price), broker_crypto_sim (fetch_price/simulate_fill)
provides:
  - "guardian.py: re-evaluates every open position's locked EXIT_PROFILE every tick via trader.backtest.exits.evaluate_exit"
  - "self-computed marketable exit order submission (never a resting broker stop), persist-before-submit + date-independent crash-recovery heal"
  - "evaluate_kill_conditions: D-01's five live kill conditions, auto-retire via strategy_kill_state"
  - "evaluate_account_breakers: the first Phase 5 caller to feed Phase 4's circuit breakers real paper-equity data, with a real-time alert on any new trip"
  - "_heartbeat_due: D-11's twice-daily heartbeat folded into the existing 5-minute tick, no fourth scheduled task"
affects: [05-06-entry-pipeline, 05-07-daily-report, 05-08-ops-checkpoint, 05-09-registration-checkpoint]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Exit conditions are always re-derived from trader.backtest.exits.evaluate_exit against a collapsed single-price OHLC bar -- never a second exit-math implementation"
    - "Exit order submission mirrors entry_pipeline's persist-before-submit + date-independent get_unresolved_orders/find_unresolved_match crash-recovery sequence exactly (BLOCKER 1)"
    - "Account-level breaker evaluation and kill-condition auto-retire both run unconditionally every tick, independent of whether an exit fired"

key-files:
  created:
    - trader/paper/guardian.py
    - tests/test_guardian.py
    - scripts/paper_guardian.bat
    - scripts/paper_guardian_task.xml
  modified: []

key-decisions:
  - "Added an optional now/log_path parameter to run_guardian_once (not in the plan's literal signature) purely for deterministic testability -- production callers via main() still default to real wall-clock time and the fixed ops/paper_trading.log path"
  - "Healed crash-orphaned exits derive exit_reason by mapping the stale order's own recorded intent back through a reason<->intent lookup, rather than trusting the current tick's freshly-fired ExitResult.reason (which may legitimately differ tick to tick)"
  - "Added a lightweight calendar_.is_trading_day gate for the IBKR stock leg only (crypto_sim always processes) per the plan's Task 1 rationale for why the Task Scheduler XML needs no market-hours predicate"
  - "ibkr_adapter.connect() is called explicitly in main() before run_guardian_once, unlike reconcile.py's main() which omits this call"

requirements-completed: [PAPER-02]

# Metrics
duration: 45min
completed: 2026-07-27
---

# Phase 05 Plan 05: Guardian (exits, kill-conditions, breakers, heartbeat) Summary

**Guardian process re-evaluating locked EXIT_PROFILEs every tick against live IBKR/ccxt prices, auto-retiring strategy_configs on D-01's kill conditions, feeding Phase 4's circuit breakers real paper-equity data with real-time alerting, and folding a twice-daily heartbeat into the existing 5-minute cadence.**

## Performance

- **Duration:** 45 min
- **Tasks:** 3
- **Files modified:** 4 (all new)

## Accomplishments

- `evaluate_position_exit`/`_submit_exit`: every open position's locked EXIT_PROFILE is rebuilt fresh from `paper_positions` columns each tick and checked via `trader.backtest.exits.evaluate_exit` against a collapsed single-price bar, covering stop/take_profit/time_stop/no-condition-fires paths for both the IBKR stock leg and the crypto_sim leg.
- Exit submission never rests a native broker stop order -- it self-computes the trigger price and submits a marketable order only when a condition fires, using the identical persist-before-submit + date-independent `get_unresolved_orders`/`idempotency.find_unresolved_match` crash-recovery sequence entry_pipeline uses (BLOCKER 1). A crash-orphaned exit order (yesterday's date embedded in its `order_ref`) is healed on the next tick without a second `place_order` call.
- `evaluate_kill_conditions`: D-01's five live kill conditions (profit_factor_floor, max_drawdown, consecutive_losses) are read from the frozen `config.LIVE_STRATEGY_CONFIGS` every tick and auto-retire via `ledger.retire_strategy`; a retired `strategy_id` is never re-evaluated, so a repeat trip never double-fires an alert.
- `evaluate_account_breakers`: the first Phase 5 caller to feed `trader.risk.breakers.evaluate_breakers`/`record_breaker_transitions` real, chronologically-ordered paper-equity data -- a fresh normal->trip transition fires a real-time `alerts.notify("error", ...)` call before persistence, and an already-tripped breaker never re-fires while it stays tripped.
- `_heartbeat_due`: reads `ops/paper_trading.log`'s own pipe-delimited format directly to decide if 12 hours have elapsed since the last heartbeat entry, folding D-11's twice-daily heartbeat into the existing 5-minute guardian tick with no fourth scheduled task.

## Task Commits

Each task was committed atomically:

1. **Task 1: Exit evaluation + self-computed MKT exit submission** - `60ca4e1` (feat)
2. **Task 2: Rolling kill-condition evaluation + auto-retire** - `3a01b59` (feat)
3. **Task 3: Account-level breaker evaluation with real-time alert + twice-daily heartbeat** - `d1f9384` (feat)

**Plan metadata:** (this commit, docs)

## Files Created/Modified

- `trader/paper/guardian.py` - The guardian: `evaluate_position_exit`, `_submit_exit`, `evaluate_kill_conditions`, `evaluate_account_breakers`, `_heartbeat_due`, `run_guardian_once`, `main`
- `tests/test_guardian.py` - 21 tests covering exit evaluation (D-10 order), persist-before-submit + idempotency, crash-orphan heal, crypto_sim leg, kill-condition auto-retire (all three trigger types + retired-skip), breaker evaluation + real-time alert dedup, heartbeat gating
- `scripts/paper_guardian.bat` - `python -m trader.paper.guardian --once` launcher
- `scripts/paper_guardian_task.xml` - Task Scheduler definition, PT5M interval, registration deferred to 05-09

## Decisions Made

- `run_guardian_once` gained an optional `now`/`log_path` parameter beyond the plan's literal `(conn, ibkr_adapter, crypto_adapter=None)` signature, strictly for deterministic testability of date-embedded order_refs and the 12-hour heartbeat cadence. Production defaults (`main()`) are unaffected: `now` defaults to real UTC wall-clock time, `log_path` defaults to the fixed `ops/paper_trading.log` contract path.
- The crash-orphan heal path derives `exit_reason` from the stale order's own recorded `intent` column (mapped back through a reason<->intent lookup table), not from whatever the current tick's fresh `ExitResult.reason` happens to be -- these could differ tick to tick in principle, and the healed trade record should reflect what was actually decided at original submission time.
- Added a small `calendar_.is_trading_day` gate for IBKR-venue positions only (crypto_sim always processes regardless), matching the plan's stated rationale for why `paper_guardian_task.xml`'s TimeTrigger needs no market-hours predicate of its own.
- `main()` explicitly calls `ibkr_adapter.connect()` before `run_guardian_once` (reconcile.py's equivalent `main()` omits this call) -- new code, not a fix to existing 05-04 code, so no deviation entry.

## Deviations from Plan

None - plan executed as written, with the three additions above documented as reasonable implementation discretion (none required Rule 4 architectural sign-off: no new tables, no schema changes, no new library, no changed API surface).

## Issues Encountered

- Initial test design chdir'd into `tmp_path` to isolate `alerts.notify`'s hard-coded `ops/paper_trading.log` default from the real repo. This broke `trader.data.db.get_connection`'s relative `migrations/` directory lookup (used by the `paper_conn` fixture), which resolves relative to cwd. Fixed by mocking `guardian.alerts.notify` directly (autouse `MagicMock`) instead of changing cwd, with individual tests re-monkeypatching it (wrapped or fully synthetic) where call-count/heartbeat-file assertions are needed.
- The heartbeat integration test could not rely on real `ops_log.append_ops_log` writes for its precise 5-minute/13-hour timing assertions, because that function always timestamps with the real wall clock (`datetime.now(timezone.utc)`), not any injected simulated `now`. Resolved by replacing `guardian.alerts.notify` with a synthetic fake that writes heartbeat lines stamped with the test's own controlled `now` value.

## User Setup Required

None - no external service configuration required. `scripts/paper_guardian_task.xml` registration is explicitly deferred to the 05-09 human checkpoint per the plan.

## Next Phase Readiness

- `evaluate_kill_conditions`, `evaluate_account_breakers`, and the exit-submission crash-recovery sequence are all available for 05-06's entry_pipeline to reuse the identical idempotency pattern from.
- 05-07's daily report can read `strategy_kill_state` and `breaker_events`/`breaker_state_current` knowing both are now populated from live (paper) data, not just Phase 4's own unit tests.
- No blockers identified for 05-06/05-07/05-08/05-09.

---
*Phase: 05-paper-trading-loop*
*Completed: 2026-07-27*
