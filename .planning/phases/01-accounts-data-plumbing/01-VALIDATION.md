---
phase: 1
slug: accounts-data-plumbing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-26
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (already installed, 24 tests green from Phase 0) |
| **Config file** | pyproject.toml (exists) |
| **Quick run command** | `python -m pytest tests/ -q -x` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~10 seconds (mocked suite) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -q -x`
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds (mocked suite only — see exemption)

**Live/manual command exemption:** Live smoke checks against real Yahoo/Binance/CoinGecko endpoints and the exit-criterion acceptance run (`get_daily_bars` for a real stock and a real crypto pair) make real network calls and are exempt from the 30-second target. They run once per plan, not per task commit. Account signups (IBKR, Kraken, Independent Reserve) are human checklist items with no automated command.

---

## Per-Task Verification Map

*Populated by the planner — one row per task with its automated command.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| — | — | — | ACCT-01…07 | — | — | — | — | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_bars.py` — stubs for bars cache insert/read and (venue, symbol, timeframe, ts) uniqueness (ACCT-06)
- [ ] `tests/test_data_api.py` — stubs for get_daily_bars routing, cache-first behaviour, UTC normalisation (ACCT-04, ACCT-07)
- [ ] `tests/test_instruments.py` — stubs for asset-class classification and override column (D-16)
- [ ] Reuse existing `tests/conftest.py` fixtures (temp SQLite DB) — extend, do not duplicate

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| IBKR account + paper account approved | ACCT-01 | Third-party approval process | Check IBKR portal shows live account approved; paper account auto-granted with US$1,000,000 virtual equity |
| Kraken trade-only API keys | ACCT-02 | Human creates keys in Kraken UI | Verify key permissions show Query + Trade ticked, Withdrawal unticked; keys stored in .env only |
| Independent Reserve KYC | ACCT-03 | Third-party KYC process | Account shows verified status |
| Live exit-criterion run | ACCT-07 | Real network, real symbols | `get_daily_bars("AAPL")` and `get_daily_bars("BTC/USDT")` (or equivalent) return multi-year daily bars in one call |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (mocked suite)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
