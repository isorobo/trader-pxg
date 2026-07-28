---
phase: 7
slug: attribution-tournament
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-28
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + hypothesis (installed; 511 tests green entering) |
| **Config file** | pyproject.toml |
| **Quick run command** | `python -m pytest tests/ -q -x --deselect tests/test_backtest_sanity.py` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | fast loop ~30s; full suite ~95s |

---

## Sampling Rate

- **After every task commit:** fast loop
- **After every plan wave:** full suite
- **Before `/gsd:verify-work`:** full suite green
- **Max feedback latency:** 30 seconds (fast loop)

**Exemptions:** the weekly tournament scheduler registration (one schtasks line, folded into the existing 05-09 go-live batch); the owner's audit of a generated decision record (the phase's human exit check).

---

## Per-Task Verification Map

*Populated by the planner.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| — | — | — | ATTR-01…04 | — | — | — | — | ❌ W0 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/test_config_store.py` — DB-backed registry loader; existing consumers unchanged in behaviour with registry mirroring current frozen configs (ATTR-04 substrate)
- [ ] `tests/test_attribution.py` — per-strategy dashboards from ledger fixtures; inline-SVG generation; kill-proximity gauges (ATTR-01)
- [ ] `tests/test_tournament.py` — every D-04 state transition, D-05 caps (6 active, 2 entrants/quarter), frozen-tournament-config hash gate, demotion rule (floor 0.0, K=4) (ATTR-02)
- [ ] `tests/test_entrant_pipeline.py` — D-07 evidence-stamped stages; no stage skippable; probation 25% sizing applied at entry only (never heal paths) (ATTR-03)
- [ ] `tests/test_tournament_audit.py` — audit record completeness: inputs snapshot, metrics, rule-cited decisions, config hash before/after; Telegram summary (exit-gate substrate)
- [ ] Migration 0006: strategy_registry + expanded kill-reason CHECK (the researcher-caught bug) + tournament audit tables

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Owner audits a decision record | exit gate | "Decisions you agree with when you audit them" | Generate a tournament run on fixture data; owner reads the markdown decision record and confirms every decision traces to numbers and pre-registered rules |
| Weekly scheduler line | ATTR-02 | Human-run schtasks per project precedent | One extra line in the 05-09 go-live registration batch |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (fast loop)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
