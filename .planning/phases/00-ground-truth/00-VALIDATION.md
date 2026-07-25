---
phase: 0
slug: ground-truth
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-26
---

# Phase 0 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | none — Wave 0 installs (`pyproject.toml` / `pytest.ini`) |
| **Quick run command** | `python -m pytest tests/ -q -x` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -q -x`
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

*Populated by the planner — one row per task with its automated command.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| — | — | — | DATA-01…04 | — | — | — | — | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_db.py` — stubs for snapshot insert/read (DATA-02)
- [ ] `tests/test_sources.py` — stubs for feed adapters with mocked HTTP (DATA-01)
- [ ] `tests/test_report.py` — stubs for report aggregation over fixture snapshots (DATA-03)
- [ ] `tests/conftest.py` — shared fixtures (temp SQLite DB, canned feed payloads)
- [ ] pytest install — no framework exists yet (greenfield)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Task Scheduler fires every 15 min and survives reboot | DATA-01, DATA-04 | Requires the real Windows scheduler and wall-clock time | Register task via documented `schtasks` command; check `data/` logs after 1 hour and after a reboot |
| Two-week continuous collection | DATA-04 | Wall-clock requirement | Weekly check of coverage stat in daily report |
| Live feed smoke test (yfinance screener, CoinGecko demo key) | DATA-01 | Depends on external services and a real API key | Run poll script with `--once`; confirm both sources insert rows |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
