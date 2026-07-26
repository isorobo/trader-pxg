---
phase: 1
slug: accounts-data-plumbing
status: planned
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-26
updated: 2026-07-26
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x/9.x (already installed, 24 tests green from Phase 0) |
| **Config file** | pyproject.toml (exists) |
| **Quick run command** | `python -m pytest tests/ -q -x` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~10-15 seconds (mocked suite) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -q -x`
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green, plus the live acceptance runs below
- **Max feedback latency:** 30 seconds (mocked suite only — see exemption)

**Live/manual command exemption:** Live smoke checks against real Yahoo/Binance/CoinGecko endpoints (`trader/data/classify_smoke.py`, `trader/data/exit_criterion_smoke.py`) make real network calls and are exempt from the 30-second target. They run once per plan, not per task commit. Account signups (IBKR, Kraken, Independent Reserve) are a human checklist item with no automated command (Plan 01-03).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|--------------------|-------------|--------|
| 01-01/T1 | 01-01 | 1 | ACCT-05 | T-01-02, T-01-13 | .env.example documents new secrets with empty values only; .gitignore self-healed if .env/data/ exclusions are missing | config check | `python -m pip show ccxt pandas` | N/A | ⬜ pending |
| 01-01/T2 | 01-01 | 1 | ACCT-06 | T-01-01 | Migration runner + instruments/bars schema contract (RED) | unit | `pytest tests/test_data_db.py -q` | ❌ W0 → created this plan | ⬜ pending |
| 01-01/T3 | 01-01 | 1 | ACCT-06 | T-01-01 | Migration runner + instruments/bars schema (GREEN) | unit | `pytest tests/test_data_db.py tests/ -q` | ✅ after T2 | ⬜ pending |
| 01-02/T1 | 01-02 | 2 | ACCT-06 | T-01-04, T-01-05 | CoinGecko classification contract (RED) | unit (mocked requests) | `pytest tests/test_classify.py -q` | ❌ W0 → created this plan | ⬜ pending |
| 01-02/T2 | 01-02 | 2 | ACCT-06 | T-01-04, T-01-05, T-01-06 | CoinGecko classification (GREEN) | unit (mocked requests) | `pytest tests/test_classify.py -q` | ✅ after T1 | ⬜ pending |
| 01-02/T3 | 01-02 | 2 | ACCT-06 | T-01-14 | register_crypto_instrument onboarding contract — classify-then-persist (RED) | unit (mocked classify, real temp db) | `pytest tests/test_classify.py -q` | ❌ W0 → created this plan | ⬜ pending |
| 01-02/T4 | 01-02 | 2 | ACCT-06 | T-01-05, T-01-14 | register_crypto_instrument onboarding (GREEN) — D-16 "classification at insert time" now has a real caller | unit (mocked classify, real temp db) | `pytest tests/test_classify.py tests/ -q` | ✅ after T3 | ⬜ pending |
| 01-02/T5 | 01-02 | 2 | ACCT-06 | T-01-05 | Live classification against real CoinGecko API | live (manual command) | `python -m trader.data.classify_smoke` | N/A | ⬜ pending |
| 01-03/T1 | 01-03 | 1 | ACCT-01, ACCT-02, ACCT-03 | T-01-07, T-01-08 | Account applications submitted; Kraken withdrawal disabled confirmed | manual (not automatable) | Checklist item in ACCOUNT-CHECKLIST.md | N/A | ⬜ pending |
| 01-04/T1 | 01-04 | 2 | ACCT-04 | T-01-04 | Stock bar tz-normalization + fetch contract (RED) | unit (mocked yfinance) | `pytest tests/test_stock_source.py -q` | ❌ W0 → created this plan | ⬜ pending |
| 01-04/T2 | 01-04 | 2 | ACCT-04 | T-01-04 | Stock bar tz-normalization + fetch (GREEN) | unit (mocked yfinance) | `pytest tests/test_stock_source.py tests/ -q` | ✅ after T1 | ⬜ pending |
| 01-05/T1 | 01-05 | 2 | ACCT-04 | T-01-02, T-01-10 | Binance pagination + UTC normalization contract (RED) | unit (mocked ccxt) | `pytest tests/test_crypto_source.py -q` | ❌ W0 → created this plan | ⬜ pending |
| 01-05/T2 | 01-05 | 2 | ACCT-04 | T-01-02, T-01-10 | Binance pagination + UTC normalization (GREEN) | unit (mocked ccxt) | `pytest tests/test_crypto_source.py tests/ -q` | ✅ after T1 | ⬜ pending |
| 01-06/T1 | 01-06 | 3 | ACCT-04, ACCT-07 | T-01-11 | get_daily_bars routing/cache/classification-wiring/tz-aware-index contract (RED) | unit (mocked fetchers + mocked register_crypto_instrument) | `pytest tests/test_data_api.py -q` | ❌ W0 → created this plan | ⬜ pending |
| 01-06/T2 | 01-06 | 3 | ACCT-04, ACCT-07 | T-01-01, T-01-11, T-01-15 | get_daily_bars routing/cache (GREEN) — resolve_instrument now calls classify.register_crypto_instrument for D-15's named universe; DataFrame index is pd.to_datetime(...).tz_localize("UTC") | unit (mocked fetchers + mocked register_crypto_instrument) | `pytest tests/test_data_api.py tests/ -q` | ✅ after T1 | ⬜ pending |
| 01-06/T3 | 01-06 | 3 | ACCT-07 | T-01-12 | Live exit-criterion run: one function call, real stock + real crypto pair, UTC tz-aware index | live (manual command) | `python -m trader.data.exit_criterion_smoke` | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_data_db.py` — stubs for migration runner + instruments/bars cache insert/read/uniqueness (ACCT-06) — created by Plan 01-01 Task 2
- [x] `tests/test_classify.py` — stubs for CoinGecko asset-class classification AND register_crypto_instrument onboarding (classify-then-persist, D-16) — created by Plan 01-02 Tasks 1 and 3
- [x] `tests/test_stock_source.py` — stubs for stock fetch + UTC normalization (ACCT-04) — created by Plan 01-04 Task 1
- [x] `tests/test_crypto_source.py` — stubs for crypto fetch + pagination (ACCT-04) — created by Plan 01-05 Task 1
- [x] `tests/test_data_api.py` — stubs for get_daily_bars routing, cache-first behavior, classification wiring, and tz-aware UTC index (ACCT-04, ACCT-07, D-16) — created by Plan 01-06 Task 1
- [x] Reuse existing `tests/conftest.py` `tmp_db_path` fixture — extended locally per-test-file, `conftest.py` itself is NOT modified by any Phase 1 plan (avoids cross-plan file contention across waves)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| IBKR account + paper account approved | ACCT-01 | Third-party approval process | Check IBKR portal shows live account approved; paper account auto-granted with US$1,000,000 virtual equity |
| Kraken trade-only API keys | ACCT-02 | Human creates keys in Kraken UI | Verify key permissions show Query + Trade ticked, Withdrawal unticked; keys stored in .env only |
| Independent Reserve KYC | ACCT-03 | Third-party KYC process | Account shows verified status |
| Live exit-criterion run | ACCT-07 | Real network, real symbols | `get_daily_bars("AAPL", asset_class="stock")` and `get_daily_bars("BTC/USDT", asset_class="crypto_major")` return multi-year daily bars, each with a UTC tz-aware index, in one function call (Plan 01-06 Task 3) |
| Live classification check | (supports D-16) | Real network, real CoinGecko categories | `classify_crypto_instrument("dogecoin", key)` returns "memecoin"; `classify_crypto_instrument("bitcoin", key)` returns "crypto_major" (Plan 01-02 Task 5) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s (mocked suite)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned — six plans created (01-01 through 01-06) across 3 waves (01-02 moved from wave 1 to wave 2, now depending on 01-01 for `db.upsert_instrument`); awaiting `/gsd:execute-phase 1`.

**Revision note (post plan-check):** Fixed a BLOCKER — `classify_crypto_instrument` had no caller, violating D-16. Plan 01-02 now adds `register_crypto_instrument` (classify-then-persist onboarding), and Plan 01-06's `resolve_instrument` routes unresolved crypto symbols in D-15's named universe through it instead of silently defaulting to `crypto_major`. Also addressed 3 WARNINGs: 01-RESEARCH.md's Open Questions are now marked (RESOLVED) with inline notes; 01-06's DataFrame index is explicitly `tz_localize("UTC")`; 01-01's `.gitignore` check is now self-healing.
