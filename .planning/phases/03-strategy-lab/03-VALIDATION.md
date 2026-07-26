---
phase: 3
slug: strategy-lab
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| **Estimated runtime** | fast loop ~15s; full suite ~40-60s |

---

## Sampling Rate

- **After every task commit:** fast loop
- **After every plan wave:** full suite (sanity gate included)
- **Before `/gsd:verify-work`:** full suite green
- **Max feedback latency:** 30 seconds (fast loop)

**Live/manual command exemption:** one-time universe backfill (new stock tickers + SHIB/PEPE/BONK/WIF) makes live calls. Full sweeps (~17 min per strategy/asset-class family) run offline on cache and are per-plan acceptance runs, not per-commit checks.

---

## Per-Task Verification Map

*Populated by the planner.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| — | — | — | STRAT-01…06 | — | — | — | — | ❌ W0 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/test_strategy_momentum.py` — RSI + volume-surge entry rules on fixture bars (STRAT-01)
- [ ] `tests/test_strategy_breakout.py` — 20-day-high + contraction gate rules on fixture bars (STRAT-02)
- [ ] `tests/test_sweep.py` — tiny-grid sweep smoke: provenance (sweep_id in params_json), frozen-grid integrity, min-trade-count floor (STRAT-03)
- [ ] `tests/test_regimes.py` — frozen regime/split config committed before results; tune/OOS separation enforced (STRAT-04, STRAT-05)
- [ ] Kill-conditions gate: KILL-CONDITIONS.md must exist with per-config numeric triggers before phase verification passes (STRAT-06)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Survivors report sanity | STRAT-03…05 | Human judges plausibility | Read the sweep summary under `reports/backtests/`; tune vs OOS side by side; per-symbol P&L present |
| "Nothing survived" branch | exit gate | Human decision to loop | If zero configs pass OOS, phase loops back per phase doc — report states it plainly |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (fast loop)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
