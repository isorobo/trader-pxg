---
phase: 03-strategy-lab
plan: 06
subsystem: backtest
tags: [reporting, kill-conditions, oos-validation, momentum, d09-verdict, d11, d12]

# Dependency graph
requires:
  - phase: 03-strategy-lab (Plan 03-04)
    provides: reports/backtests/tune_top5.json, the real 15-candidate D-10 top-5 list
  - phase: 03-strategy-lab (Plan 03-05)
    provides: reports/backtests/oos_results.json, the real per-candidate OOS verdict artifact (0 survivors)
provides:
  - trader/backtest/sweep_report.py's write_sweep_summary/write_survivors_index (per-config tune-vs-OOS reports + survivors index, D-12)
  - trader/backtest/write_kill_conditions.py's main() (the phase's terminal artifact writer, D-11, with a defence-in-depth frozen-config gate, T-03-20)
  - .planning/phases/03-strategy-lab/KILL-CONDITIONS.md, the real, committed, honest nothing-survived statement
  - 15 real reports/backtests/*-sweep.md files (one per oos_result entry) + 1 real reports/backtests/*-survivors.md index
affects: [04-risk-and-execution, 06-graduation-review]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sweep-report filenames carry the tune run_id as a final disambiguator ({date}-{strategy}-{bucket}-{regime}-run{run_id}-sweep.md) because D-10's top-5 rule can advance up to 5 candidates sharing the same (strategy, bucket, regime) combo -- a plain combo-only filename would collide and silently drop reports"
    - "write_kill_conditions.main() re-verifies frozen_config.verify_frozen() as its first statement, defence in depth on top of the same gate Plans 03-03/03-05 already enforce at their own entrypoints (T-03-20)"
    - "build_kill_conditions_text() is a pure formatting function separated from main()'s file I/O, so both the survivor-entry branch and the nothing-survived branch are unit-testable without touching the real committed file"

key-files:
  created:
    - trader/backtest/sweep_report.py
    - trader/backtest/write_kill_conditions.py
    - tests/test_sweep_report.py
    - tests/test_kill_conditions.py
    - .planning/phases/03-strategy-lab/KILL-CONDITIONS.md

key-decisions:
  - "Sweep-report filenames include run_id (Rule 1 bugfix, not in the plan's literal filename pattern) -- discovered while reading the real oos_results.json for Task 2 and confirming 5 candidates share each (strategy, bucket, regime) combo; fixed before Task 2 began so Task 2's 'one sweep.md per oos_result entry' acceptance criterion could actually be met"
  - "Max-drawdown kill trigger formula implemented literally as max(1.5 * observed_max_drawdown, -0.15) -- never fires on the real data (0 survivors), but unit-tested directly against both the floored and unfloored cases"
  - "write_kill_conditions.main() looks up each oos_result's matching tune_top5.json candidate by run_id (via a dict keyed on run_id) rather than trusting oos_result['candidate'] as authoritative, per the plan's literal action text, even though the embedded candidate dict is already a verbatim copy in this codebase's current wiring"

patterns-established:
  - "Real per-candidate sweep reports and the survivors index are produced in the same real script run that writes KILL-CONDITIONS.md (one execution, one source of truth, T-03-17)"

requirements-completed: [STRAT-06]

# Metrics
duration: ~25min
completed: 2026-07-26
---

# Phase 03 Plan 06: Sweep Reports + KILL-CONDITIONS.md Summary

**Phase 3's honest exit gate is now closed: KILL-CONDITIONS.md and 15 real per-config sweep reports (with per-symbol P&L) plainly state that zero of the 15 real tune-sweep candidates survived OOS validation -- a valid, cheap-kill result that sends work back to Phase 3, not forward.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-26T20:38Z (approx, following Plan 03-05's completion)
- **Completed:** 2026-07-26T20:47Z
- **Tasks:** 2 completed (plus one Rule-1 fix commit discovered before Task 2 began)
- **Files modified:** 5 (4 created, plus the real KILL-CONDITIONS.md artifact)

## Accomplishments

- `trader/backtest/sweep_report.py` gained `write_sweep_summary` and `write_survivors_index`: every OOS-validated candidate gets its own markdown report with tune-vs-OOS metrics tables side by side and a per-symbol P&L breakdown (grouped/summed from `ledger.get_trades_for_run`, never a new metrics engine) -- proven against both single-trade and zero-trade fixture runs.
- The survivors index renders the exact "Nothing survived this sweep — {N} candidates tested across {M} strategy/bucket/regime combinations" sentence when zero survivors exist, quoting the real trial count rather than producing an empty or missing file (T-03-19) -- proven against a 4-candidate/3-combination fixture matrix.
- Both report types append D-05's survivorship-bias caveat verbatim, proven present in every branch tested.
- `trader/backtest/write_kill_conditions.py`'s `main()` calls `frozen_config.verify_frozen()` as its literal first statement, before `oos_results.json` is even read -- proven by a fixture test that points `OOS_RESULTS_PATH` at a nonexistent file and confirms a tampered hash raises `RuntimeError` (not `FileNotFoundError`), meaning the gate fires before any read is attempted.
- `build_kill_conditions_text()` computes 3 concrete numeric kill triggers per survivor from that survivor's own OOS metrics (0.9 profit-factor floor, `max(1.5 * observed_max_drawdown, -0.15)` drawdown kill level, 8 consecutive-loss count) -- proven against both the floored and unfloored drawdown cases, and proven to produce exactly one header per survivor with zero leakage from non-survivor entries.
- The real run over the real 15-candidate `oos_results.json` produced 0 survivors, so `.planning/phases/03-strategy-lab/KILL-CONDITIONS.md` was committed with the exact "Nothing survived this sweep — no kill conditions to register; work returns to Phase 3, not forward (ROADMAP.md Phase 3 success criterion 3)" sentence -- the honest, sobering headline `03-05-SUMMARY.md` predicted, now made Phase 3's committed, permanent record.
- The same real run produced all 15 real `reports/backtests/*-sweep.md` files (one per `oos_result` entry, disambiguated by run_id) and the real `reports/backtests/2026-07-26-survivors.md` index, both gitignored per D-12 but verified present on disk by `tests/test_kill_conditions.py`.

## Task Commits

1. **Task 1: sweep_report.py — per-config summaries and survivors index** - `3791652` (feat)
2. **Rule 1 fix (found before Task 2): disambiguate sweep-report filenames with run_id** - `c8e2fa7` (fix)
3. **Task 2: write_kill_conditions.py — real run + phase-gate test** - `54f191f` (feat, includes the real committed KILL-CONDITIONS.md)

**Plan metadata:** (this commit, following SUMMARY.md — not created per this executor's instructions to skip STATE.md/ROADMAP.md updates)

## Files Created/Modified

- `trader/backtest/sweep_report.py` - `write_sweep_summary(oos_result, tune_candidate, conn, base_dir="reports/backtests") -> Path`, `write_survivors_index(oos_results, base_dir="reports/backtests") -> Path`
- `trader/backtest/write_kill_conditions.py` - `main(conn=None) -> Path`, `build_kill_conditions_text(oos_results) -> str` (pure formatting helper), `_max_drawdown_trigger(observed_max_drawdown) -> float`
- `tests/test_sweep_report.py` - 8 tests: filename disambiguation, tune/OOS tables, per-symbol P&L grouping/summing, zero-trade handling, survivors-index branches, D-05 caveat presence
- `tests/test_kill_conditions.py` - 7 tests: frozen-config gate ordering, both `build_kill_conditions_text` branches, the drawdown-trigger formula, and two real-artifact cross-checks against the committed `KILL-CONDITIONS.md`/`oos_results.json`
- `.planning/phases/03-strategy-lab/KILL-CONDITIONS.md` - The real, committed phase-exit artifact: honest nothing-survived statement
- `reports/backtests/*-sweep.md` (15 files, gitignored) and `reports/backtests/*-survivors.md` (1 file, gitignored) - Real report artifacts, not committed per D-12

## Decisions Made

- **Sweep-report filenames carry `run_id`** (`{date}-{strategy}-{bucket}-{regime}-run{run_id}-sweep.md`), diverging from the plan's literal `{date}-{strategy}-{bucket}-{regime}-sweep.md` pattern. Discovered while reading the real `oos_results.json` for Task 2: D-10's top-5 rule advances up to 5 candidates per (strategy, bucket, regime) combo, and the real data has exactly 5 per combo for two of the three combos. Without `run_id`, every later candidate in a combo would silently overwrite the previous candidate's report -- a data-loss bug, not a formatting preference. Fixed and committed (`c8e2fa7`) before Task 2 began, so Task 2's "one sweep.md per oos_result entry" acceptance criterion could be met for real.
- **`write_kill_conditions.main()` looks up each candidate's tune metrics from `tune_top5.json` by `run_id`** rather than trusting the `candidate` dict already embedded in `oos_results.json`, per the plan's literal action text -- both sources are currently identical byte-for-byte (the embedded candidate IS a verbatim copy per `run_oos_validation_all.py`'s own documented behavior), so this is a forward-looking correctness discipline rather than a behavior change today.
- **`build_kill_conditions_text()` is a pure function, separated from `main()`'s file I/O** -- lets both the survivor-entry branch and the nothing-survived branch be unit-tested directly against synthetic fixtures without ever touching the real committed `KILL-CONDITIONS.md`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Sweep-report filenames collided across same-combo candidates**
- **Found during:** Task 2 (reading the real `oos_results.json` to design `write_kill_conditions.main()`)
- **Issue:** The plan's literal filename pattern `{date}-{strategy}-{bucket}-{regime}-sweep.md` has no candidate-level disambiguator. The real 15-candidate `oos_results.json` has exactly 5 candidates sharing `momentum_stock/stock/trending`, 5 sharing `momentum_stock/stock/choppy`, and 5 sharing `momentum_crypto_major_legacy_meme/crypto_major_legacy_meme/trending` -- writing all 5 to the same filename would silently keep only the last-written report per combo, discarding 4 of every 5 (12 of 15 total).
- **Fix:** Added the tune `run_id` as a final filename component (`...-run{run_id}-sweep.md`), guaranteeing one distinct file per `oos_result` entry, matching Task 2's own acceptance criterion ("`reports/backtests/*-sweep.md` files exist, one per oos_result entry").
- **Files modified:** `trader/backtest/sweep_report.py`, `tests/test_sweep_report.py`
- **Verification:** The real run produced exactly 15 distinct `*-sweep.md` files (confirmed via directory listing) plus 1 `*-survivors.md` index; `tests/test_kill_conditions.py::test_real_sweep_reports_and_survivors_index_exist_on_disk` asserts `len(sweep_reports) >= len(oos_results)`.
- **Committed in:** `c8e2fa7` (separate fix commit, ahead of Task 2's feat commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary for correctness -- without this fix, 12 of the 15 real sweep reports required by Task 2's own acceptance criteria would never have existed on disk. No scope creep; the fix touches only the filename construction, not the report content or the kill-condition logic.

## Issues Encountered

None beyond the filename collision documented above. The real `write_kill_conditions` run completed in well under a second (offline, cache-hit reads of two small JSON files plus 15 `get_trades_for_run` DB queries).

## Real Phase-Exit Result (the plan's key output)

All 15 of Plan 03-04's real momentum tune-sweep candidates came back `insufficient_sample` in Plan 03-05's OOS validation (0 survivors, 0 killed). Plan 03-06's report and kill-condition logic treats this as the valid, reportable outcome D-12 and the phase context explicitly anticipate:

- `.planning/phases/03-strategy-lab/KILL-CONDITIONS.md` (committed): *"Nothing survived this sweep — no kill conditions to register; work returns to Phase 3, not forward (ROADMAP.md Phase 3 success criterion 3)."*
- `reports/backtests/2026-07-26-survivors.md` (real, gitignored): *"Nothing survived this sweep — 15 candidates tested across 3 strategy/bucket/regime combinations,"* followed by D-05's caveat.
- 15 real `reports/backtests/*-sweep.md` files, each with tune-vs-OOS metrics tables and a real per-symbol P&L breakdown (e.g. run165's OOS trades split across AMZN/NFLX/TSLA/WMT), each closing with D-05's caveat.

Phase 3's three success criteria (ROADMAP.md): (1) the honest "nothing survived" outcome is reported plainly, in both the survivors index and every per-config report — met; (2) "every survivor has a pre-registered kill condition" is vacuously met (zero survivors, zero conditions owed) and explicitly stated as such rather than silently skipped; (3) the frozen-before-results discipline (`frozen_config.verify_frozen()`) is enforced in code at the tune-sweep, OOS-validation, AND this final kill-condition entrypoint — three independent gate calls, not one shared assumption.

## User Setup Required

None - no external service configuration required (offline run against already-cached artifacts).

## Next Phase Readiness

- Phase 3 is DONE per its own exit gate: the honest "nothing survived" result is committed, not hidden. Per the phase context's own framing ("If NOTHING survives — that's a valid, cheap result. Go back to Phase 3, not forward"), the immediate next step is revisiting Phase 3's strategy/parameter scope (e.g. wider OOS windows, a longer-history universe, or reconsidering the 15-trade OOS floor's interaction with 4-6 month OOS windows) rather than proceeding to Phase 4 with strategies that were never proven profitable out-of-sample.
- `trader/backtest/sweep_report.py` and `trader/backtest/write_kill_conditions.py` are reusable as-is for any future re-run of Phase 3's sweep with a revised universe/grid/regime set -- neither module hardcodes the 15-candidate/3-combination shape of this particular run.
- Full test suite green: 217 passed (202 baseline + 8 sweep_report tests + 7 kill_conditions tests).

---
*Phase: 03-strategy-lab*
*Completed: 2026-07-26*

## Self-Check: PASSED

- FOUND: `trader/backtest/sweep_report.py`
- FOUND: `trader/backtest/write_kill_conditions.py`
- FOUND: `tests/test_sweep_report.py`
- FOUND: `tests/test_kill_conditions.py`
- FOUND: `.planning/phases/03-strategy-lab/KILL-CONDITIONS.md`
- FOUND: 15 real `reports/backtests/*-sweep.md` files + 1 `reports/backtests/*-survivors.md` file (gitignored, on-disk artifacts)
- FOUND: commit `3791652` (Task 1 feat)
- FOUND: commit `c8e2fa7` (Rule 1 fix)
- FOUND: commit `54f191f` (Task 2 feat)
