---
phase: 3
slug: strategy-lab
status: planned
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-26
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (150 tests green entering the phase; suite ~40s including the sanity gate) |
| **Config file** | pyproject.toml (exists) |
| **Quick run command** | `python -m pytest tests/ -q -x --deselect tests/test_backtest_sanity.py` (fast loop) |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | fast loop ~15s; full suite ~40-60s (v1); v2 adds a handful of fast fixture tests only, no material change to full-suite runtime |

---

## Sampling Rate

- **After every task commit:** fast loop
- **After every plan wave:** full suite (sanity gate included)
- **Before `/gsd:verify-work`:** full suite green
- **Max feedback latency:** 30 seconds (fast loop)

**Live/manual command exemption:** the one-time universe backfill (Plan 03-02 Task 3 — new stock tickers + SHIB/PEPE/BONK/WIF) makes live calls; not repeated for v2, since v2's regime windows all fall within that same already-completed full-history cache. The v1 real tune sweep (Plan 03-04 Task 2, ~16-30 min) and v1 real OOS validation (Plan 03-05 Task 2, <1 min) run offline on cache and are per-plan acceptance runs, not per-commit checks. The v2 real tune sweep (Plan 03-08 Task 2, ~10,800 runs, ~4-5h, detached/checkpoint-resumable) and v2 real OOS validation (Plan 03-08 Task 2, <1 min) are likewise per-plan acceptance runs, exempt from the fast loop.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|------------------|-----------|--------------------|-------------|--------|
| 03-01-T1 | 03-01 | 1 | STRAT-01 | T-03-01, T-03-02, T-03-04 | Momentum signal fires only on RSI(14)>=60 + 2x volume surge + 20-day-high break; never on truncated/insufficient history; baseline excludes today's own bar | unit | `python -m pytest tests/test_strategy_momentum.py -q -x` | new (Wave 1) | done |
| 03-01-T2 | 03-01 | 1 | STRAT-02 | T-03-01, T-03-02, T-03-04 | Breakout signal fires only on NR7 + 20-day-high break + 1.5x volume confirm, no-retest; never on truncated history | unit | `python -m pytest tests/test_strategy_breakout.py -q -x` | new (Wave 1) | done |
| 03-02-T1 | 03-02 | 1 | STRAT-04, STRAT-05 | T-03-07 | 6 frozen regimes, tune_end < oos_start for every regime, mania regime's symbol-relative tune_start | unit | `python -m pytest tests/test_regime_config.py -q -x` | new (Wave 1) | done |
| 03-02-T2 | 03-02 | 1 | STRAT-03 | T-03-06 | Grid cell counts exactly 270/270/360; frozen-hash self-consistency; verify_frozen raises on tamper | unit | `python -m pytest tests/test_exit_grid.py tests/test_frozen_config.py -q -x` | new (Wave 1) | done |
| 03-02-T3 | 03-02 | 1 | STRAT-04, STRAT-05 | T-03-05 | One-time live backfill of 25 universe symbols; RuntimeError on any zero-row symbol | integration (live, exempt from fast loop) | `python -m trader.backtest.backfill_universe` | new (Wave 1) | done |
| 03-03-T1 | 03-03 | 2 | STRAT-03 | T-03-08, T-03-09, T-03-10 | Hash gate blocks every cell before any DB write on tamper; every cell's params_json carries full provenance; every cell runs through unmodified run_backtest | unit | `python -m pytest tests/test_sweep_engine.py -k "tune or hash" -q -x` | new (Wave 2) | done |
| 03-03-T2 | 03-03 | 2 | STRAT-03 | T-03-11 | select_top5 enforces the >=30-trade floor before ranking; never returns more than 5 | unit | `python -m pytest tests/test_sweep_engine.py -k select_top5 -q -x` | new (Wave 2) | done |
| 03-04-T1 | 03-04 | 3 | STRAT-03, STRAT-04, STRAT-05 | T-03-13 | run_tune_sweep_all.py fast-fixture smoke: schema-valid tune_top5.json, <=60 entries, strategy_id tagged as exact f"{strategy_id}_{bucket}" composite | unit (fast fixture) | `python -m pytest tests/test_run_tune_sweep_all.py -q -x` | new (Wave 3) | done |
| 03-04-T2 | 03-04 | 3 | STRAT-03, STRAT-04, STRAT-05 | T-03-12 | Real tune sweep executes across all 12 strategy/bucket/regime combos; exact expected backtest_runs row-count delta (3600) verified | integration (real, offline, ~16-30 min, per-plan acceptance) | `python -m trader.backtest.run_tune_sweep_all` | new (Wave 3) | done |
| 03-05-T1 | 03-05 | 4 | STRAT-05 | T-03-14, T-03-15 | frozen_config.verify_frozen() called first in run_oos_validation, before any regime lookup or run_backtest call — tampered hash raises RuntimeError with ZERO run_backtest calls (mirrors 03-03's tune-sweep hash-gate test); OOS bars restricted to regime.oos_start/oos_end only; determine_survivor's 3-way branch (survivor/insufficient_sample/killed) with the 15-trade floor | unit | `python -m pytest tests/test_oos_validation.py -q -x` (includes the hash-gate fixture test, call-count spy on run_backtest) | new (Wave 4) | done |
| 03-05-T2 | 03-05 | 4 | STRAT-04, STRAT-05 | T-03-16 | Real OOS validation over every candidate; oos_results.json records every verdict, not only survivors; reproducible on re-run | integration (real, offline, <1 min, per-plan acceptance) | `python -m trader.backtest.run_oos_validation_all` | new (Wave 4) | done |
| 03-06-T1 | 03-06 | 5 | STRAT-06 | T-03-19 | sweep_report renders both "some survivors" and "nothing survived" branches, quoting the real trial count, always carrying D-05's survivorship-bias caveat | unit | `python -m pytest tests/test_sweep_report.py -q -x` | new (Wave 5) | done |
| 03-06-T2 | 03-06 | 5 | STRAT-06 | T-03-17, T-03-18, T-03-20 | KILL-CONDITIONS.md gate: 1:1 survivor coverage with 3 numeric triggers each, or the exact nothing-survived sentence; write_kill_conditions.main() calls verify_frozen() first as defence in depth; committed before Phase 4 | integration/gate (real run + parse) | `python -m pytest tests/test_kill_conditions.py -q -x` | new (Wave 5) | done — v1 concluded 0 survivors / 15 insufficient_sample |
| 03-07-T1 | 03-07 | 6 | STRAT-04, STRAT-05 | T-03-22 | regimes_v2.REGIMES_V2: 6 entries, 2 per bucket, every OOS window >= 365 days, tune_end < oos_start for all 6, mania_recovery_v2's symbol-relative tune_start | unit | `python -m pytest tests/test_regime_config_v2.py -q -x` | new (Wave 6) | planned |
| 03-07-T2 | 03-07 | 6 | STRAT-03, STRAT-04, STRAT-05 | T-03-23 | 3 momentum + 3 breakout entry variants pinned; "base" variant reproduces v1's real momentum.pick_entries/breakout.pick_entries output byte-for-byte on v1's own fixtures; monotonic strict<loose signal-count ordering; neither module imports v1's strategy files | unit | `python -m pytest tests/test_entry_variants_v2.py -q -x` | new (Wave 6) | planned |
| 03-07-T3 | 03-07 | 6 | STRAT-03 | T-03-21, T-03-24 | frozen_config_v2 hashes exactly 5 files (universe.py, regimes_v2.py, exit_grid.py, momentum_v2.py, breakout_v2.py); verify_frozen_v2 raises on tamper; v1's frozen_config.py/FROZEN_HASH untouched | unit | `python -m pytest tests/test_frozen_config_v2.py -q -x` | new (Wave 6) | planned |
| 03-08-T1 | 03-08 | 7 | STRAT-03 | T-03-25 | run_tune_sweep_v2/run_oos_validation_v2 both call verify_frozen_v2() first — tampered hash raises RuntimeError with ZERO run_backtest calls; every v2 cell's params_json carries all 6 provenance keys (5 shared + entry_variant); select_top5/determine_survivor reused unchanged from v1 (D-15) | unit | `python -m pytest tests/test_sweep_engine_v2.py -q -x` | new (Wave 7) | planned |
| 03-08-T2 | 03-08 | 7 | STRAT-03, STRAT-04, STRAT-05 | T-03-26, T-03-27 | Checkpoint-resume fixture proves an interrupted run never re-executes an already-checkpointed (strategy,bucket,regime,variant) unit; strategy_id/entry_variant tagging correct; 10,800-run arithmetic (3,240+3,240+4,320) matches the pre-registered D-14 estimate exactly | unit (fast fixture) + integration (real, offline, ~4-5h, detached/checkpoint-resumable, per-plan acceptance) | `python -m pytest tests/test_run_tune_sweep_all_v2.py tests/test_oos_validation_v2.py -q -x` then `python -m trader.backtest.run_tune_sweep_all_v2` (detached) then `python -m trader.backtest.run_oos_validation_all_v2` | new (Wave 7) | planned |
| 03-08-T3 | 03-08 | 7 | STRAT-06 | T-03-28, T-03-29 | KILL-CONDITIONS.md regenerated from real oos_results_v2.json only (1:1 survivor coverage or nothing-survived sentence); write_kill_conditions_v2.main() calls verify_frozen_v2() first as defence in depth; every pre-existing v1-dated report/data file verified byte-unmodified | integration/gate (real run + parse) | `python -m pytest tests/test_kill_conditions_v2.py -q -x` | new (Wave 7) | planned |

---

## Wave 0 Requirements

All Wave 0 gaps identified in 03-RESEARCH.md are now assigned to concrete planned tasks (no dangling gaps):

- [x] `tests/test_strategy_momentum.py` — assigned to 03-01-T1 (STRAT-01)
- [x] `tests/test_strategy_breakout.py` — assigned to 03-01-T2 (STRAT-02)
- [x] `tests/test_sweep_engine.py` — assigned to 03-03-T1/T2 (STRAT-03)
- [x] `tests/test_regime_config.py` — assigned to 03-02-T1 (STRAT-04, STRAT-05)
- [x] `tests/test_exit_grid.py`, `tests/test_frozen_config.py` — assigned to 03-02-T2 (STRAT-03, frozen-before-results gate)
- [x] `tests/test_oos_validation.py` — assigned to 03-05-T1 (STRAT-05, including the hash-gate fixture test)
- [x] Kill-conditions gate (`tests/test_kill_conditions.py`) — assigned to 03-06-T2 (STRAT-06)
- [x] v2 gaps (`tests/test_regime_config_v2.py`, `tests/test_entry_variants_v2.py`, `tests/test_frozen_config_v2.py`, `tests/test_sweep_engine_v2.py`, `tests/test_run_tune_sweep_all_v2.py`, `tests/test_oos_validation_v2.py`, `tests/test_kill_conditions_v2.py`) — assigned to 03-07-T1/T2/T3 and 03-08-T1/T2/T3

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| v1 survivors report sanity | STRAT-03…05 | Human judges plausibility of the sweep's own honest results | Read `reports/backtests/*-sweep.md` (tune vs OOS side by side, per-symbol P&L) and `reports/backtests/*-survivors.md` after Plan 03-06 |
| v1 "nothing survived" branch | Phase exit gate | Human decision to loop back to Phase 3 rather than advance | v1 concluded 0 survivors / 15 insufficient_sample — the owner reviewed this and approved the v2 iteration (03-CONTEXT.md D-13…D-16) rather than looping back further |
| v2 survivors report sanity | STRAT-03…05 | Human judges plausibility of v2's own honest results | Read v2's per-config `reports/backtests/*-run{run_id}-sweep.md` files and `reports/backtests/*-survivors-v2.md` after Plan 03-08 |
| v2 "nothing survived" branch | Phase exit gate | Human decision to loop back to Phase 3 rather than advance | If `reports/backtests/*-survivors-v2.md` states "Nothing survived", confirm the regenerated KILL-CONDITIONS.md's matching statement and do not advance to Phase 4 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify (no MISSING references remain — every Wave 0 gap, including v2's, is covered by a planned task)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (see Wave 0 Requirements above)
- [x] No watch-mode flags
- [x] Feedback latency < 30s (fast loop; live/real-run tasks explicitly exempted per Sampling Rate section)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** plans created 2026-07-26 by `/gsd:plan-phase 3`; revised 2026-07-26 per plan-checker feedback (v1 frozen-config hash gate enforced at both tune-sweep and OOS-validation entrypoints, plus a defence-in-depth check at the terminal kill-conditions gate). v1 (Plans 03-01…03-06) executed and concluded honestly: 0 survivors / 15 insufficient_sample. Owner approved the v2 iteration 2026-07-26 ("run it as recommended") per 03-CONTEXT.md D-13…D-16; Plans 03-07 (Wave 6) and 03-08 (Wave 7) added 2026-07-26 to extend OOS windows to >=12 months and sweep entry-gate strictness as a new dimension, with zero modification to any v1 artifact. Pending execution via `/gsd:execute-phase 3`.
