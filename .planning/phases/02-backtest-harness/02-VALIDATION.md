---
phase: 2
slug: backtest-harness
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-26
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
| — | — | — | BACK-01…07 | — | — | — | — | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_iterator.py` — point-in-time slicing, lookahead impossibility (BACK-01)
- [ ] `tests/test_fees_slippage.py` — per-venue fee table + per-class slippage application (BACK-02, BACK-03)
- [ ] `tests/test_exit_engine.py` — profile immutability, evaluation order, entry-bar check, gap-through fills, stop-wins-tie (BACK-04)
- [ ] `tests/test_ledger.py` — per-fill rows, run reproducibility with pinned seed (BACK-05)
- [ ] `tests/test_metrics.py` — golden hand-computed fixture: PF, Sharpe, max DD, win rate, edge cases (BACK-06)
- [ ] `tests/test_sanity_random.py` — the exit-gate test: seeded random strategy loses ~ (fees+slippage) within the derived band; FAILS the suite if it profits (BACK-07)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| One real strategy end-to-end metrics report | BACK-06/exit gate | Human reads the report for sanity | Run the placeholder momentum strategy over the pinned universe; confirm `reports/backtests/` report renders with plausible numbers |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (fixture suite)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
