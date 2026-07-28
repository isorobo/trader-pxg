---
phase: 7
slug: attribution-tournament
status: executed
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-28
executed: 2026-07-28
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + hypothesis (572 tests green at phase close) |
| **Config file** | pyproject.toml |
| **Quick run command** | `python -m pytest tests/ -q -x --deselect tests/test_backtest_sanity.py` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | fast loop ~25s; full suite ~95s |

---

## Sampling Rate

- **After every task commit:** fast loop — HELD (every wave committed green)
- **After every plan wave:** full suite — HELD
- **Before `/gsd:verify-work`:** full suite green — HELD
- **Max feedback latency:** 30 seconds (fast loop)

**Exemptions:** the weekly tournament scheduler registration (one schtasks
line, folded into the existing 05-09 go-live batch); the owner's audit of a
generated decision record (the phase's human exit check — artifact at
`reports/tournament/fixture-demo/2026-07-28-run1.md`).

---

## Per-Task Verification Map

| Task | Wave | Requirement | Secure Behavior | Test File | Status |
|------|------|-------------|-----------------|-----------|--------|
| Migration 0006 + seeds | 1 | ATTR-04 substrate | Expanded kill CHECK; seeds match frozen configs verbatim | `tests/test_config_store.py` | PASS |
| Freeze gate | 1 | D-06 | Byte-tamper raises before any judging | `tests/test_tournament_frozen.py` | PASS |
| config_store loader | 1 | D-08 | Parameterized SQL; retired/candidate rows excluded | `tests/test_config_store.py` | PASS |
| Call-site swap + guardian identity fix | 2 | D-08 | Kill conditions key on profile_name (bug fix) | `tests/test_guardian.py` | PASS |
| Probation sizing | 2 | ATTR-02/D-04 | 25% at new-order path only; heal paths verbatim | `tests/test_entrant_pipeline.py` | PASS |
| D-07 state machine | 3 | ATTR-03 | No stage skippable; retired terminal; transitions logged | `tests/test_entrant_pipeline.py` | PASS |
| Caps | 3 | ATTR-04/D-05 | 6 active, 2 entrants/quarter; queue not loss | `tests/test_entrant_pipeline.py` | PASS |
| Tournament judge | 4 | ATTR-02/D-03/D-04 | Compound demotion, sustained K=4; healthy roster never empties | `tests/test_tournament.py` | PASS |
| Audit records | 4 | D-09 | Every decision rule-cited; hashes before/after; Telegram once | `tests/test_tournament_audit.py` | PASS |
| Dashboards + SVG | 5 | ATTR-01/D-01/D-02 | Ledger-read-only; self-contained HTML; guardian-math gauges | `tests/test_attribution.py` | PASS |
| Scheduler artifacts | 6 | D-10 | .bat/.xml pair only; registration deferred to 05-09 | manual (below) | DONE |

---

## Manual-Only Verifications

| Behavior | Requirement | Status | Test Instructions |
|----------|-------------|--------|-------------------|
| Owner audits a decision record | exit gate | **PENDING OWNER** | Read `reports/tournament/fixture-demo/2026-07-28-run1.md` (fixture data): confirm every decision traces to numbers and a pre-registered rule. Dashboard: `reports/attribution/fixture-demo/dashboard.html` |
| Weekly scheduler line | ATTR-02/D-10 | Deferred to 05-09 batch | `schtasks /Create /TN "TraderAI Tournament" /XML scripts\tournament_run_task.xml` |
| Frozen threshold review | D-06 | **PENDING OWNER** | 07-RESEARCH.md A1–A3: floors 0.0/0.0, K=4 are Claude-recommended defaults, frozen and hash-gated; one reviewed adjustment is sanctioned BEFORE the first real (non-fixture) tournament run, none after |

---

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (0006 migration, 7 new test files, trade factory)
- [x] No watch-mode flags
- [x] Feedback latency < 30s (fast loop)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** automated gates passed; owner audit of the fixture decision record is the remaining human exit check.
