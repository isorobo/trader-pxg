---
phase: 05-paper-trading-loop
plan: 06
subsystem: trading-engine
tags: [paper-trading, entry-pipeline, momentum, risk-gate, sizer, crash-recovery, ibkr]

# Dependency graph
requires:
  - phase: 05-01
    provides: paper_orders/paper_positions ledger surface, persist-before-submit order lifecycle, get_unresolved_orders/get_all_unresolved_orders/heal_order, LIVE_STRATEGY_CONFIGS
  - phase: 05-02
    provides: alerts.notify (Telegram + ops-log fallback), ops_log's pipe-delimited entry format
  - phase: 05-03
    provides: IBKRBrokerAdapter (place_order/snapshot/latest_price), round_shares_down
  - phase: 05-04
    provides: reconcile.is_entry_halted (Phase-4-breaker + reconciliation combined halt gate)
provides:
  - "entry_pipeline.py: scan_candidates (loose momentum_stock signal over the 18-symbol STOCK_UNIVERSE, RSI score, sizer volatility)"
  - "assign_exit_profile: sha256(symbol)-only, no date component -- day-stable strategy_id identity for crash-recovery healing"
  - "run_entry_pipeline_once: unconditional STEP 0 unscoped heal pass, then gate->sizer->round->per-candidate-heal->halt-gate->persist-before-submit->broker->ledger->alert"
  - "scripts/paper_entry.bat + scripts/paper_entry_task.xml (daily Task Scheduler artifact, registration deferred to 05-09)"
affects: [05-07-daily-report, 05-08-ops-checkpoint, 05-09-registration-checkpoint]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "STEP 0 (unscoped get_all_unresolved_orders heal pass) always runs first, before the trading-day check and before is_entry_halted -- healing is never gated by either"
    - "assign_exit_profile hashes on symbol alone (sorted(live_profile_names)[sha256(symbol) % len]), never a date component, so a crash-recovery lookup on a later day always resolves the same strategy_id"
    - "market_data for trader.risk.gate is rebuilt independently (via a dedicated _bars_as_dicts helper carrying ts) rather than reusing the PointInTimeIterator's numpy history array, since the gate's correlation window needs real calendar dates the iterator's bounded numpy slice does not expose"
    - "gate -> sizer -> round_shares_down -> per-candidate heal -> halt-gate -> persist -> broker call is one fixed, unreshuffled sequence with a single place_order call site (D-08 no-bypass-path)"

key-files:
  created:
    - trader/paper/entry_pipeline.py
    - tests/test_entry_pipeline.py
    - scripts/paper_entry.bat
    - scripts/paper_entry_task.xml
  modified: []

key-decisions:
  - "market_data's per-candidate bars are fetched via a dedicated _bars_as_dicts(conn, symbol, as_of_date) helper (a fresh get_daily_bars call carrying ts/open/high/low/close/volume), rather than converting the PointInTimeIterator's numpy history array used for scan_candidates's RSI/volatility computation -- trader.risk.gate.apply_risk_gate's correlation check requires real calendar-date-indexed bars (pd.to_datetime(bar['ts'])), which the iterator's bounded numpy slice does not expose. Both paths read from the same get_daily_bars source, so this is a shape choice, not a data-consistency risk."
  - "_live_profile_names(conn) is called unconditionally once real candidates exist this run (after the 'no candidates' early return), per the plan's literal text -- so a fully-retired live-config set surfaces its RuntimeError on the very first run with any candidate, not only when one would have been accepted."
  - "STEP 0's healing_price fallback (ibkr_adapter.latest_price(symbol)) is only invoked when the broker fill itself carries no fill_price -- IBKRBrokerAdapter.snapshot()'s fills never populate fill_price today, so this fallback path is exercised on every STEP 0 heal in practice, matching the plan's explicit fallback design."

requirements-completed: [PAPER-01]

# Metrics
duration: 50min
completed: 2026-07-27
---

# Phase 05 Plan 06: Entry Pipeline (STEP0 heal, scan, gate, sizer, submit) Summary

**Live entry pipeline scanning 18 stock symbols with the loose momentum signal, running Phase 4's risk gate and sizer unmodified, assigning exit profiles via a day-stable symbol-only hash, and healing crash-orphaned orders through an unconditional STEP 0 pass that runs before both the trading-day check and the halt gate.**

## Performance

- **Duration:** 50 min
- **Tasks:** 2
- **Files modified:** 4 (all new)

## Accomplishments

- `scan_candidates`: builds one `PointInTimeIterator` over the frozen 18-symbol `STOCK_UNIVERSE` using bars up to (not including) `as_of_date`, fires `momentum_v2`'s loose variant via `make_pick_entries`, and scores each fired symbol with the identical `_rsi_wilder` computation the signal itself used plus `sizer.compute_volatility` -- a symbol already open (any strategy_id) never re-fires, enforced by `pick_entries`'s own `open_positions` argument.
- `assign_exit_profile(symbol, live_profile_names)`: deterministic on symbol alone (`sha256(symbol) % len(sorted(live_profile_names))`), with no date parameter anywhere in its signature -- proven day-stable across simulated day-1/day-2 calls, and documented inline with the full RESIDUAL BLOCKER 1 rationale for why a date-hashed identity would have broken crash-recovery lookups 4 times out of 5.
- `run_entry_pipeline_once`: STEP 0 (`ledger.get_all_unresolved_orders`, unscoped) runs unconditionally at the very top of every invocation -- before the `calendar_.is_trading_day` check and before any `reconcile.is_entry_halted` call -- and is proven (by a dedicated test) to heal a crash-orphaned order for a symbol whose fixture bars deliberately do NOT satisfy the loose signal on the healing day, using a run date different from the one embedded in the stale order_ref. A second test proves STEP 0 heals even when both `is_entry_halted` is mocked `True` and `is_trading_day` is mocked `False` for the entire test.
- The full per-candidate sequence -- gate -> `_live_profile_names` -> sizer -> `round_shares_down` -> per-candidate heal check (STEP 1) -> still-in-flight check (STEP 2) -> halt gate (STEP 3) -> persist `pending_submit` (STEP 4) -> `place_order` (STEP 5) -> `open_position`/alert -- is proven both by direct behavioral tests (rejected candidates never reach the sizer, qty is floored via `round_shares_down` and never rounded up, resubmitting the same day never double-submits) and by a call-order spy test asserting `gate < sizer < halt_check < record_order < place_order` strictly, not merely equal call counts.
- `scripts/paper_entry.bat` + `scripts/paper_entry_task.xml`: a daily Task Scheduler trigger (`P1D` repetition) with its `StartBoundary` expressed in NZ local time (the July NZST/EDT ~16-hour offset equivalent of ~09:45 US Eastern), documenting inline that DST shifts this by an hour twice a year in each hemisphere and that `calendar_.is_trading_day`/`session_window` inside the code -- never the XML trigger alone -- is the real gate. Registration deferred to the 05-09 human checkpoint.

## Task Commits

Each task was committed atomically:

1. **Task 1: Candidate scan, score, gate, kill-filter, day-stable symbol-only profile assignment** - `a4dc513` (feat)
2. **Task 2: STEP0 heal pass -> gate -> sizer -> round -> per-candidate heal -> halt-gate -> persist-submit -> ledger -> alert** - `9d5f764` (feat)

**Plan metadata:** (this commit, docs)

## Files Created/Modified

- `trader/paper/entry_pipeline.py` - `scan_candidates`, `assign_exit_profile`, `_live_profile_names`, `_run_step0_heal_pass`, `run_entry_pipeline_once`, `main`
- `tests/test_entry_pipeline.py` - 21 tests: scan_candidates (fired-symbol scoring, open-position exclusion, no-fire path), assign_exit_profile (no-date signature, day-stable determinism, live-list containment, distribution fairness), `_live_profile_names` (raises when all retired, excludes only retired), full happy-path submit, whole-share rounding, gate-rejection-never-reaches-sizer, STEP 0 non-refiring-orphan heal (RESIDUAL BLOCKER 1's exact scenario, cross-day), STEP 0 heal under combined halt+non-trading-day, halt-blocks-new-submission-but-not-heal, same-day resubmit safety, and a call-order spy test plus static source-shape assertions (single `place_order` call site, two-arg `assign_exit_profile` call site, no rounding-up function, `pending_submit` default)
- `scripts/paper_entry.bat` - `python -m trader.paper.entry_pipeline --once` launcher
- `scripts/paper_entry_task.xml` - Task Scheduler definition, `P1D` interval, registration deferred to 05-09

## Decisions Made

See `key-decisions` in the frontmatter above (market_data's independent `_bars_as_dicts` fetch for gate-correctness reasons; unconditional `_live_profile_names` call once any candidate exists; STEP 0's `latest_price` fallback path).

## Deviations from Plan

None - plan executed as written. The three items in "Decisions Made" are implementation-shape choices within the plan's own literal pseudocode's degrees of freedom (none required Rule 4 architectural sign-off: no new tables, no schema changes, no new library, no changed public API surface).

## Issues Encountered

None - the twice-revised plan's pseudocode (STEP 0 unconditional, heal-before-halt ordering, persist-before-submit, symbol-only hashing) translated directly into working code and tests on the first pass; no rounds of test-driven correction were needed beyond one test-assertion fix (a same-day resubmit test's expected return shape, corrected to reflect that a now-open AAPL position is excluded from `scan_candidates` on the second run, so STEP 0 still heals but `candidates == 0`).

## User Setup Required

None - no external service configuration required. `scripts/paper_entry_task.xml` registration is explicitly deferred to the 05-09 human checkpoint per the plan.

## Next Phase Readiness

- `entry_pipeline.py`'s STEP 0 heal pass, `assign_exit_profile`, and the gate->sizer->round->persist->submit sequence are all available for 05-07's daily report to read `paper_orders`/`paper_positions`/`paper_trades` knowing entries are now populated from a live (paper) run, not just Phase 4's own unit tests.
- 05-08's ops checkpoint can point at `scripts/paper_entry.bat`/`scripts/paper_entry_task.xml` alongside the existing guardian/reconcile artifacts for the full daily cycle.
- No blockers identified for 05-07/05-08/05-09.

---
*Phase: 05-paper-trading-loop*
*Completed: 2026-07-27*

## Self-Check: PASSED

- FOUND: trader/paper/entry_pipeline.py
- FOUND: tests/test_entry_pipeline.py
- FOUND: scripts/paper_entry.bat
- FOUND: scripts/paper_entry_task.xml
- FOUND commit: a4dc513
- FOUND commit: 9d5f764
- Full suite: 490 passed, 1 deselected (test_backtest_sanity.py)
