---
phase: 2
slug: backtest-harness
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-26
updated: 2026-07-26
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (installed; 53 tests green entering the phase) |
| **Config file** | pyproject.toml (exists) |
| **Quick run command** | `python -m pytest tests/ -q -x` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~15-30 seconds (mocked/fixture suite; the sanity test runs on cached bars, no network) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -q -x`
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite green, including the random-strategy sanity test
- **Max feedback latency:** 30 seconds (the sanity test must stay within this on cached data; if it cannot, mark it `slow` and run per-wave rather than per-commit — but it MUST run in the full suite)

**Live/manual command exemption:** Any one-off bar backfill for the pinned sanity universe (first population of the cache) makes live network calls and is exempt. All backtests themselves run offline on cached bars.

---

## Per-Task Verification Map

*Populated by the planner — one row per task with its automated command.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01 T1 | 02-01 | 1 | BACK-02, BACK-03, BACK-04 | T-02-01 | EXIT_PROFILE frozen + tuple scale_out | unit | `pytest tests/test_backtest_config.py -x -q` | Wave 0 | ⬜ pending |
| 02-01 T2 | 02-01 | 1 | BACK-02, BACK-03, BACK-04 | T-02-02 | CHECK constraints on exit_reason/asset_class | unit | `pytest tests/test_backtest_migration.py -x -q` | Wave 0 | ⬜ pending |
| 02-02 T1 | 02-02 | 1 | BACK-01 | T-02-03, T-02-04 | point-in-time slicing, no lookahead | unit | `pytest tests/test_backtest_iterator.py -x -q` | Wave 0 | ⬜ pending |
| 02-03 T1 | 02-03 | 1 | BACK-06 | T-02-05, T-02-06 | golden-fixture metrics, edge cases | unit | `pytest tests/test_backtest_metrics.py -x -q` | Wave 0 | ⬜ pending |
| 02-04 T1 | 02-04 | 2 | BACK-02, BACK-03 | T-02-07, T-02-08 | config-driven fee/slippage, always adverse | unit | `pytest tests/test_backtest_fills.py -x -q` | Wave 0 | ⬜ pending |
| 02-05 T1 | 02-05 | 2 | BACK-04 | T-02-09, T-02-10, T-02-11 | D-10 order, entry-bar check, stop-wins-tie, trailing no-lookahead | unit | `pytest tests/test_backtest_exits.py -x -q` | Wave 0 | ⬜ pending |
| 02-06 T1 | 02-06 | 2 | BACK-05 | T-02-12, T-02-13, T-02-SC | parameterized SQL, reproducibility, no subprocess | unit | `pytest tests/test_backtest_ledger.py -x -q` | Wave 0 | ⬜ pending |
| 02-06 T2 | 02-06 | 2 | BACK-06 | T-02-23 | per-strategy grouping, no cross-strategy leakage | unit | `pytest tests/test_backtest_ledger.py -k strategy -x -q` | Wave 0 | ⬜ pending |
| 02-07 T1 | 02-07 | 2 | BACK-07 | T-02-14, T-02-15 | seeded, reproducible, price-blind random strategy | unit | `pytest tests/test_backtest_strategies.py -k random -x -q` | Wave 0 | ⬜ pending |
| 02-07 T2 | 02-07 | 2 | BACK-07 | — | momentum placeholder, lookback-gated signal | unit | `pytest tests/test_backtest_strategies.py -k momentum -x -q` | Wave 0 | ⬜ pending |
| 02-08 T1 | 02-08 | 3 | BACK-01, BACK-04, BACK-05 | T-02-16, T-02-17, T-02-18 | signal-to-fill lag, entry-bar exit, reproducible ledger | integration | `pytest tests/test_backtest_runner.py -x -q` | Wave 0 | ⬜ pending |
| 02-09 T1 | 02-09 | 4 | BACK-07 | T-02-SC | one-time live backfill, offline thereafter | live/manual (exempt) | `python -m trader.backtest.sanity_universe` | Wave 0 | ⬜ pending |
| 02-09 T2 | 02-09 | 4 | BACK-07 | T-02-19, T-02-20 | non-circular tolerance band, N>=3000, no silent skip | acceptance (permanent) | `pytest tests/test_backtest_sanity.py -x -q` | Wave 0 | ⬜ pending |
| 02-10 T1 | 02-10 | 4 | BACK-06 | T-02-21, T-02-22 | end-to-end report, finite metrics, trade_count>=1 | integration | `pytest tests/test_backtest_momentum_e2e.py -x -q` | Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_backtest_config.py` — fee/slippage table values, EXIT_PROFILE immutability (BACK-02, BACK-03, BACK-04) — plan 02-01
- [ ] `tests/test_backtest_migration.py` — schema_version=3, CHECK constraints (BACK-02, BACK-03, BACK-04) — plan 02-01
- [ ] `tests/test_backtest_iterator.py` — point-in-time slicing, lookahead impossibility (BACK-01) — plan 02-02
- [ ] `tests/test_backtest_metrics.py` — golden hand-computed fixture: PF, Sharpe, max DD, win rate, edge cases (BACK-06) — plan 02-03
- [ ] `tests/test_backtest_fills.py` — per-venue fee table + per-class slippage application (BACK-02, BACK-03) — plan 02-04
- [ ] `tests/test_backtest_exits.py` — profile evaluation order, entry-bar check, gap-through fills, stop-wins-tie, trailing no-lookahead (BACK-04) — plan 02-05
- [ ] `tests/test_backtest_ledger.py` — per-fill rows, run reproducibility with pinned seed, per-strategy attribution grouping (BACK-05, BACK-06) — plan 02-06
- [ ] `tests/test_backtest_strategies.py` — seeded random strategy + momentum placeholder (BACK-07) — plan 02-07
- [ ] `tests/test_backtest_runner.py` — full-pipe integration: signal-to-fill lag, entry-bar exit, reproducibility (BACK-01, BACK-04, BACK-05) — plan 02-08
- [ ] `tests/test_backtest_sanity.py` — the exit-gate test: seeded random strategy loses ~ (fees+slippage) within the derived band; FAILS the suite if it profits (BACK-07) — plan 02-09
- [ ] `tests/test_backtest_momentum_e2e.py` — end-to-end placeholder strategy run + report (BACK-06) — plan 02-10

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| One real strategy end-to-end metrics report | BACK-06/exit gate | Human reads the report for sanity | Run the placeholder momentum strategy over the pinned universe; confirm `reports/backtests/` report renders with plausible numbers |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (11 test files across 10 plans)
- [x] No watch-mode flags
- [x] Feedback latency < 30s (fixture suite; sanity test runs offline against cached bars)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** plans created 2026-07-26; pending execution via `/gsd:execute-phase 2`
