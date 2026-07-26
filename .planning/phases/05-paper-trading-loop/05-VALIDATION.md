---
phase: 5
slug: paper-trading-loop
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-26
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (347 green entering) + hypothesis (installed) |
| **Config file** | pyproject.toml |
| **Quick run command** | `python -m pytest tests/ -q -x --deselect tests/test_backtest_sanity.py` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | fast loop ~25s; full suite ~80s |

---

## Sampling Rate

- **After every task commit:** fast loop
- **After every plan wave:** full suite
- **Before `/gsd:verify-work`:** full suite green
- **Max feedback latency:** 30 seconds (fast loop)

**Live/manual exemptions:** IB Gateway install + login (human checkpoint), first live paper order round-trip (human-witnessed acceptance), Telegram token creation (human checkpoint), the two-week unattended window (wall-clock gate, like Phase 0's — auditable from the operations log + daily report).

---

## Per-Task Verification Map

*Populated by the planner.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| — | — | — | PAPER-01…07 | — | — | — | — | ❌ W0 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/test_paper_pipeline.py` — scanner→gate→ranker→sizer→execution wiring with a mocked broker; Phase 4 stages provably in-line with no bypass (PAPER-01)
- [ ] `tests/test_guardian.py` — exit-trigger evaluation per profile, whole-share rounding, kill-condition auto-retire (PAPER-02)
- [ ] `tests/test_idempotency.py` — deterministic client order IDs; crash-resubmit can never double-order (PAPER-03)
- [ ] `tests/test_reconciliation.py` — divergence classification rules (explainable vs unexplained), halt + manual_restart wiring on unexplained (PAPER-04)
- [ ] `tests/test_paper_ledger.py` — real-format trade rows, migration 0005 (PAPER-05)
- [ ] `tests/test_alerts.py` — Telegram fire-and-forget with local fallback, no token leakage in logs (PAPER-06)
- [ ] `tests/test_recovery.py` — startup order pinned: read DB → fetch broker → reconcile BEFORE any new action (PAPER-07/crash safety)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| IB Gateway paper login (port 4002) | PAPER-01 | Human credentials + 2FA | Owner installs Gateway, logs into paper account DUR285675, enables API |
| First paper order round-trip | PAPER-01/03 | Real broker interaction | One supervised entry order fills on paper; permId recorded; reconciliation matches |
| Telegram alerts arrive | PAPER-06 | Human phone | Owner receives test message, fill alert, heartbeat |
| Two-week unattended window | PAPER-07 / exit gate | Wall clock | Operations log + daily reports show zero unplanned interventions and zero unexplained divergences; weekly 2FA taps logged as pre-registered exceptions (D-13) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (fast loop)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
