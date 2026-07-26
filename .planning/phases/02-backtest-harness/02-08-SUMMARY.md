---
phase: 02-backtest-harness
plan: 08
subsystem: backtesting
tags: [python, sqlite, pandas, tdd, backtest-runner]

# Dependency graph
requires:
  - phase: 02-backtest-harness
    provides: PointInTimeIterator (02-02), fills (02-04), evaluate_exit/PositionState (02-05), ledger.record_run/record_trade (02-06), pick_entries strategy contract (02-07)
provides:
  - "run_backtest(strategy_fn, universe, profile, bars_by_symbol, seed, params, strategy_id, conn) -> run_id"
  - Full simulation loop orchestrating iterator/fills/exits/ledger with correct one-bar entry lag and entry-bar exit checking
affects: [02-09-sanity-test, 02-10-momentum-end-to-end]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Runner-owned _OpenPosition dataclass wraps exits.PositionState with position_id/qty/fees bookkeeping the exits module itself never needs to know about"
    - "pending_entries dict schedules a signalled symbol's fill at the first future calendar date it actually has a bar, never a blind next-index"
    - "asset_class resolved once per symbol per run via trader.data.api.resolve_instrument, cached in a dict"

key-files:
  created: [trader/backtest/runner.py, tests/test_backtest_runner.py]
  modified: []

key-decisions:
  - "asset_class resolution uses trader.data.api.resolve_instrument(conn, symbol) rather than a params-supplied mapping -- reuses Phase 1's instruments-table lookup, defaults unregistered non-crypto-shaped symbols to 'stock' with no network call"
  - "profile_name for ledger.record_run comes from params.get('profile_name', type(profile).__name__) since all Phase 2 profiles share one EXIT_PROFILE class -- callers must pass profile_name explicitly to get a meaningful label"
  - "position sizing uses config.DEFAULT_NOTIONAL / entry_price for qty (Phase 2 has no real position sizer yet, per D-note in config.py)"
  - "fees/slippage on a partial (scale-out) close prorate the entry-side cost by exit_fraction and add that tranche's own exit-side cost, so per-row pnl stays internally consistent without double-counting entry costs across tranches"

patterns-established:
  - "Exit-result raw_price (already worse-of/close priced by exits.py) is layered with ONLY apply_slippage + fee_for at the runner level -- never re-run through worse_of_fill, which would double-apply the gap-through penalty"

requirements-completed: [BACK-01, BACK-04, BACK-05]

duration: 26min
completed: 2026-07-26
---

# Phase 02 Plan 08: Backtest Runner Integration Summary

**run_backtest orchestration loop wiring PointInTimeIterator, fills, exits, and ledger with a provably correct one-bar signal-to-fill lag and same-bar entry exit checking**

## Performance

- **Duration:** 26 min
- **Started:** 2026-07-26T05:37:00Z
- **Completed:** 2026-07-26T06:03:00Z
- **Tasks:** 1
- **Files modified:** 2 (both created)

## Accomplishments
- `run_backtest` orchestrates the full per-day simulation loop: exits on open positions, opening scheduled entries with an immediate entry-bar exit check, then signalling and scheduling new entries at the first future bar a symbol actually has
- Entries never fill at the signal bar's close -- fill price is always the next available bar's open, priced through `fills.entry_fill_price`
- A position that gaps through its stop on the very bar it opened records `exit_reason='stop'` on that same bar (entry-bar check runs in the same loop pass, `days_held=0`)
- Ledger rows are byte-identical (excluding `run_id`/`trade_id`) across two separate fresh temp DBs run with the same seed, params, and fixture
- `asset_class` resolves once per symbol via `trader.data.api.resolve_instrument`, reusing Phase 1's instruments-table lookup instead of inventing a second resolution path

## Task Commits

Each task was committed atomically (RED -> GREEN, TDD):

1. **Task 1: run_backtest wiring** - `a851543` (test: failing integration tests, RED) -> `70879a8` (feat: implementation, GREEN)

**Plan metadata:** (this commit)

## Files Created/Modified
- `trader/backtest/runner.py` - `run_backtest` orchestration loop (269 lines): `_OpenPosition` bookkeeping dataclass, `_next_bar_date` (one-bar-lag scheduling helper), `_resolve_asset_class` (cached instruments lookup), `_open_position`/`_record_exit` (entry/exit fill + fee/slippage/pnl math), and the main per-date loop
- `tests/test_backtest_runner.py` - 5 integration tests: signal-to-fill lag, entry-bar stop check, full-pipe field consistency, cross-DB reproducibility, run_id/params_json persistence

## Decisions Made
- **asset_class source:** used `trader.data.api.resolve_instrument(conn, symbol)` (Phase 1's existing instruments-table lookup) rather than requiring callers to supply a symbol->asset_class mapping. This keeps `run_backtest`'s signature exactly as specified in the plan (no extra parameter) while giving every symbol a real resolution path; unregistered stock-shaped symbols default to `"stock"` with zero network calls, which is what the fixtures and future sanity/momentum tests need.
- **profile_name:** since all Phase 2 profiles are instances of the same frozen `EXIT_PROFILE` dataclass, `type(profile).__name__` alone can't distinguish `PROFILE_TIME_STOP_1D` from `PROFILE_MOMENTUM_PLACEHOLDER`. `run_backtest` reads `params.get("profile_name", ...)` so callers (02-09, 02-10) pass the profile's real name explicitly.
- **Position sizing:** `config.DEFAULT_NOTIONAL / entry_price` gives a plausible qty for Phase 2's honesty proof; Phase 4 owns real position sizing per the phase boundary.

## Deviations from Plan

None - plan executed exactly as written. The plan's `<action>` text explicitly flagged asset_class resolution and profile_name as "Claude's discretion, document which source" -- both are documented above, not treated as deviations from a locked requirement.

## Issues Encountered

None. All 5 integration tests passed on the first GREEN implementation attempt; no debugging iterations were needed on the lag/ordering logic the plan anticipated might require iteration.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

`run_backtest` is ready for both downstream consumers:
- Plan 02-09 (sanity test) can call it with `random_strategy.pick_entries` and `PROFILE_TIME_STOP_1D`/its own profile to prove the random strategy loses ~fees.
- Plan 02-10 (momentum end-to-end) can call it with `momentum_placeholder.pick_entries` and `PROFILE_MOMENTUM_PLACEHOLDER` to produce a full metrics report.

No blockers. Full suite green: 148 passed (143 baseline + 5 new runner tests).

---
*Phase: 02-backtest-harness*
*Completed: 2026-07-26*

## Self-Check: PASSED

- FOUND: trader/backtest/runner.py
- FOUND: tests/test_backtest_runner.py
- FOUND: a851543 (test commit)
- FOUND: 70879a8 (feat commit)
- Full suite: 148 passed, 0 failed
