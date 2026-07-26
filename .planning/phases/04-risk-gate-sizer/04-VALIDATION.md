---
phase: 4
slug: risk-gate-sizer
status: planned
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-26
updated: 2026-07-26
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (217 green entering; hypothesis 6.161.5 added as dev dep for cap-invariant property tests) |
| **Config file** | pyproject.toml |
| **Quick run command** | `python -m pytest tests/ -q -x --deselect tests/test_backtest_sanity.py` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | fast loop ~20s; full suite ~75s |

---

## Sampling Rate

- **After every task commit:** fast loop
- **After every plan wave:** full suite
- **Before `/gsd:verify-work`:** full suite green
- **Max feedback latency:** 30 seconds (fast loop; hypothesis profiles capped for CI-speed via per-test `@settings(max_examples=50, deadline=None)`)

**Exemptions:** none expected — Phase 4 is fully offline (bars already cached; no live calls).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-T1 | 04-01 | 1 | RISK-01, RISK-02, RISK-03 | T-04-02 | Frozen config constants, zero inline magic numbers, spread proxy reuses SLIPPAGE_PCT | unit | `python -m pytest tests/test_risk_config.py -q -x` | ❌ W0 | ⬜ pending |
| 04-01-T2 | 04-01 | 1 | RISK-03 | T-04-01 | Append-only breaker_events + breaker_state_current view, parameterized-ready schema | unit | `python -m pytest tests/test_risk_migration.py -q -x` | ❌ W0 | ⬜ pending |
| 04-02-T1 | 04-02 | 2 | RISK-01 | T-04-03, T-04-04, T-04-05 | Liquidity/listing-age/spread checks, reason-coded rejection, no strategies coupling | unit (tdd) | `python -m pytest tests/test_risk_gate.py -k "not correlation" -q -x` | ❌ W0 | ⬜ pending |
| 04-02-T2 | 04-02 | 2 | RISK-01 | T-04-05 | Date-aligned correlation, greedy N-way cluster elimination | unit (tdd) | `python -m pytest tests/test_risk_gate.py -q -x` | ❌ W0 | ⬜ pending |
| 04-03-T1 | 04-03 | 2 | RISK-02 | T-04-06 | Deterministic cap order, cash absorbs freed weight, golden fixture | unit (tdd) | `python -m pytest tests/test_position_sizer.py -k "not hypothesis" -q -x` | ❌ W0 | ⬜ pending |
| 04-03-T2 | 04-03 | 2 | RISK-02 | T-04-07, T-04-08 | Cap invariants proven for any generated input (property-based) | property (hypothesis) | `python -m pytest tests/test_position_sizer.py -q -x` | ❌ W0 | ⬜ pending |
| 04-04-T1 | 04-04 | 2 | RISK-03 | — | No-lookahead incremental HWM, pure evaluation, Phase 2 harness simulation | unit + simulation | `python -m pytest tests/test_breakers.py -k evaluate -q -x` | ❌ W0 | ⬜ pending |
| 04-04-T2 | 04-04 | 2 | RISK-03 | T-04-09, T-04-10, T-04-11 | Parameterized persistence, human-only manual-restart clear path | unit | `python -m pytest tests/test_breakers.py -q -x` | ❌ W0 | ⬜ pending |
| 04-05-T1 | 04-05 | 3 | RISK-01, RISK-04 | T-04-12, T-04-13 | Gate-stage poisoned-list rejections, self-verifying correlation fixture | acceptance | `python -m pytest tests/test_poisoned_list.py -k gate -q -x` | ❌ W0 | ⬜ pending |
| 04-05-T2 | 04-05 | 3 | RISK-02, RISK-04 | T-04-12 | Sizer-stage memecoin clip, full D-07 two-stage cross-check | acceptance | `python -m pytest tests/test_poisoned_list.py -q -x` | ❌ W0 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/test_risk_config.py` — Plan 04-01, Task 1
- [ ] `tests/test_risk_migration.py` — Plan 04-01, Task 2
- [ ] `tests/test_risk_gate.py` — Plan 04-02, covers RISK-01
- [ ] `tests/test_position_sizer.py` — Plan 04-03, covers RISK-02 (hypothesis cap-invariant tests included)
- [ ] `tests/test_breakers.py` — Plan 04-04, covers RISK-03
- [ ] `tests/test_poisoned_list.py` — Plan 04-05, covers RISK-04, the D-07 exit-gate acceptance test

All five files are created by their respective plan's own tasks in this phase — no cross-plan test-file dependency remains unresolved at planning time.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Threshold sanity review | RISK-01/02 defaults | Numeric floors are pre-registered judgment calls | Owner may review `trader/risk/config.py` defaults; recalibration happens via pre-registered change in Phase 6, never mid-trade |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (all 6 test files enumerated above)
- [x] No watch-mode flags
- [x] Feedback latency < 30s (fast loop)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending (execution not yet started; Phase 3's owner iteration decision does not block Phase 4 planning, per orchestrator instruction, but Phase 4 execution should confirm phase-order status before starting)
