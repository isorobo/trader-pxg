---
phase: 4
slug: risk-gate-sizer
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-26
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
- **Max feedback latency:** 30 seconds (fast loop; hypothesis profiles capped for CI-speed)

**Exemptions:** none expected — Phase 4 is fully offline (bars already cached; no live calls).

---

## Per-Task Verification Map

*Populated by the planner.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| — | — | — | RISK-01…04 | — | — | — | — | ❌ W0 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/test_risk_gate.py` — liquidity/age/spread/correlation checks with reason codes (RISK-01)
- [ ] `tests/test_position_sizer.py` — deterministic order, worked-example fixture, hypothesis cap invariants: top-3, 50% single, 10% memecoin, 10% cash NEVER violated for any input (RISK-02)
- [ ] `tests/test_breakers.py` — event-log state machine, UTC day boundaries, incremental HWM (no lookahead), all three breakers fire in harness simulation (RISK-03)
- [ ] `tests/test_poisoned_list.py` — the committed poisoned fixture produces exactly the expected rejections with correct reason codes (RISK-04, exit gate)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Threshold sanity review | RISK-01/02 defaults | Numeric floors are pre-registered judgment calls | Owner may review `trader/risk/config.py` defaults; recalibration happens via pre-registered change in Phase 6, never mid-trade |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (fast loop)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
