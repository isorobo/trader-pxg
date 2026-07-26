---
phase: 01-accounts-data-plumbing
verified: 2026-07-26T00:00:00Z
status: human_needed
score: 20/20 must-haves verified (code); 2/3 human-owned account criteria still open
human_verification:
  - test: "Submit Independent Reserve (IR) KYC signup — government ID, selfie/liveness check, proof of address"
    expected: "IR account created and KYC application submitted (does not need to be approved to satisfy ACCT-03/D-14, but must be started)"
    why_human: "Third-party KYC signup requires the account owner's real identity documents; ACCOUNT-CHECKLIST.md currently shows IR as 'Not started'"
  - test: "Confirm IBKR live-account application has actually been submitted (all sections filed) in interactivebrokers.com Client Portal, not merely started"
    expected: "IBKR Client Portal shows the Individual account application in submitted/pending-review state (or Approved), with photo ID and proof of residency uploaded"
    why_human: "ACCOUNT-CHECKLIST.md records portal access with a paper-type account (DUR285675) but does not confirm the live-application submission step; only the account owner can complete/confirm this in the IBKR portal"
  - test: "Complete Kraken identity verification and create a trade-only API key (Query Funds, Query Open Orders & Trades, Query Closed Orders & Trades, Modify Orders, Cancel/Close Orders ticked; Withdraw Funds and the rest unticked), then visually confirm Withdraw Funds shows disabled before entering KRAKEN_API_KEY/KRAKEN_API_SECRET into .env"
    expected: "Kraken account verified, API key created with trade-only permissions, Withdraw Funds confirmed disabled, and both key values present in .env (never .env.example, never a committed file)"
    why_human: "Identity verification and API key permission selection happen entirely in Kraken's UI; .env currently contains only COINGECKO_API_KEY — no KRAKEN_API_KEY/KRAKEN_API_SECRET lines exist yet"
---

# Phase 1: Accounts & Data Plumbing Verification Report

**Phase Goal:** All access sorted before it is needed — brokers, exchanges, data, repo, database.
**Verified:** 2026-07-26
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth (Roadmap SC) | Status | Evidence |
|---|---|---|---|
| 1 | Historical daily bars for any US stock and any major crypto pair come back with one function call | VERIFIED | `get_daily_bars("AAPL", asset_class="stock")` returned 11,495 rows (1980-12-12..2026-07-24 UTC) live; `get_daily_bars("BTC/USDT", asset_class="crypto_major")` returned 3,266 rows (2017-08-17..2026-07-26 UTC) live (orchestrator-verified). Re-ran independently for `get_daily_bars("DOGE/USDT")` (no hint) during this verification: 2,579 rows, `index.tz=UTC`, 0.086s elapsed confirming cache-hit, no fresh network call needed. |
| 2 | IBKR paper account, Kraken API keys (trade-only), and Independent Reserve KYC are in progress or done | PARTIAL / HUMAN NEEDED | ACCOUNT-CHECKLIST.md: IBKR "In progress (application started)" — portal access with paper-type account DUR285675 exists but live-application submission is unconfirmed; Kraken "In progress" — account created, ID verification pending, API keys not yet created (`.env` contains only `COINGECKO_API_KEY=`, no `KRAKEN_API_KEY`/`KRAKEN_API_SECRET` lines); Independent Reserve "Not started" — this account has not begun, so this criterion is only partially satisfied |
| 3 | The Python repo exists with git, config files, and `.env` for keys that is never committed | VERIFIED | `.gitignore` contains `.env`, `.env.*` (with `!.env.example` carve-out) and `/data/`; `.env.example` documents `COINGECKO_API_KEY`, `KRAKEN_API_KEY`, `KRAKEN_API_SECRET`, `IBKR_ACCOUNT_ID`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` all with empty values; live `.env` inspected (values redacted) — no real secret committed anywhere in the repo |

### Observable Truths (Plan-level must_haves, by plan)

| # | Truth | Plan | Status | Evidence |
|---|---|---|---|---|
| 1 | `.env.example` documents every Phase 1 secret key name, no real values | 01-01 | VERIFIED | Read `.env.example` directly — 6 lines, all `KEY=` with nothing after `=` |
| 2 | Fresh SQLite file gains `instruments`/`bars` tables on first `get_connection` call | 01-01 | VERIFIED | Live `data/trader.db` query: tables = snapshots, poll_runs, schema_version, instruments, bars, sqlite_sequence; `schema_version` max = 2 |
| 3 | Duplicate `(venue, symbol, timeframe, ts)` bar insert silently ignored | 01-01 | VERIFIED | `write_bars_cache` uses `INSERT OR IGNORE INTO bars (...)` (grep-confirmed at db.py:165); covered by `test_bars_unique_constraint`, part of the green 53/53 suite |
| 4 | `ccxt`/`pandas` installed and pinned | 01-01 | VERIFIED | `requirements.txt` tail: `ccxt==4.5.68`, `pandas==3.0.5`; both importable in `.venv` (confirmed via `from trader.data import ... crypto_source, stock_source` import check) |
| 5 | `.gitignore` always excludes `.env` and `data/`, self-healing | 01-01 | VERIFIED | `.gitignore` contains `.env`, `.env.*`, `/data/` |
| 6 | Memecoin-vs-major determined from CoinGecko's category taxonomy, never a hand-maintained list | 01-02 | VERIFIED | `classify_crypto_instrument` reads `response.json().get("categories")`, checks for `"Meme"` — no hardcoded ticker list; live DB row for `DOGE/USDT` shows `asset_class='memecoin'`, `coingecko_id='dogecoin'`, proving the real classification path executed (D-16 live path, orchestrator-verified) |
| 7 | Every CoinGecko classification call sends the authenticated demo-key header | 01-02 | VERIFIED | `headers={"x-cg-demo-api-key": api_key}` grep-confirmed at classify.py:41; no alternate unauthenticated code path exists |
| 8 | `classify_crypto_instrument` has a real caller — classified AND persisted in one onboarding call | 01-02 | VERIFIED | `register_crypto_instrument` calls `classify_crypto_instrument` then `db.upsert_instrument` in the same function (classify.py:72); `api.py resolve_instrument` calls `classify.register_crypto_instrument` (api.py:86) — live DB row for DOGE/USDT is direct proof this path executed, not dead code |
| 9 | A stock symbol's daily bars come back with a plain UTC calendar-date string, never tz-aware NY timestamp | 01-04 | VERIFIED | `normalize_stock_bars` uses `.tz_convert("UTC").strftime("%Y-%m-%d")`; live AAPL call returned dates with `index.tz=UTC` |
| 10 | Requesting no start date fetches fully available history, not a truncated window | 01-04 | VERIFIED | `fetch_stock_bars` calls `.history(period="max", ...)` when `start is None`; live AAPL call returned 11,495 rows back to 1980-12-12 |
| 11 | Crypto bars fetch through Binance (via ccxt), never Kraken's 720-candle-capped endpoint | 01-05 | VERIFIED | `crypto_source.py` constructs only `ccxt.binance()`; no `ccxt.kraken()` reference anywhere in the module |
| 12 | Backfill spanning >1000 candles pages correctly, returns every row | 01-05 | VERIFIED | `fetch_all_daily_ohlcv` pagination loop (mocked test + live evidence: BTC/USDT 3,266 rows, DOGE/USDT 2,579 rows — both far exceed the 1000-candle single-call cap) |
| 13 | Every bar timestamp normalizes to a plain UTC calendar-date string | 01-05 | VERIFIED | `normalize_crypto_bars` uses `datetime.fromtimestamp(row[0]/1000, tz=timezone.utc).strftime("%Y-%m-%d")` |
| 14 | One function call returns multi-year daily bars for any US stock | 01-06 | VERIFIED | Live: `get_daily_bars("AAPL", asset_class="stock")` → 11,495 rows |
| 15 | Same call returns multi-year daily bars for any major crypto pair | 01-06 | VERIFIED | Live: `get_daily_bars("BTC/USDT", asset_class="crypto_major")` → 3,266 rows |
| 16 | A second call for an already-cached range makes zero network calls | 01-06 | VERIFIED | Orchestrator-confirmed cache-hit on re-run; independently re-verified in this session — `get_daily_bars("DOGE/USDT")` returned in 0.086s (consistent with a local SQLite read, not a live fetch) |
| 17 | `bars.venue` records true fetch provenance (`yahoo`/`binance`), never a fee-model venue | 01-06 | VERIFIED | `_venue_for_asset_class` hardcodes `stock -> "yahoo"`, else `crypto_source.CRYPTO_VENUE` ("binance"); live DB row confirms `venue='binance'` for DOGE/USDT |
| 18 | An unresolved crypto symbol in D-15's named universe is classified via CoinGecko and persisted before routing, never silently defaulted | 01-06 | VERIFIED | `resolve_instrument` calls `classify.register_crypto_instrument` before any fetch when no instruments row exists and no explicit `asset_class` is given; live DB proves this executed for DOGE/USDT (`instruments` row present with real `coingecko_id`, not a bare default) |
| 19 | `get_daily_bars`'s returned DataFrame index is explicitly UTC tz-aware, not naive | 01-06 | VERIFIED | Code: `pd.to_datetime(df["ts"]).dt.tz_localize("UTC")`; independently re-verified in this session — `df.index.tz == UTC` for the DOGE/USDT call |
| 20 | No real secret value appears in any committed file (01-03) | 01-03 | VERIFIED | `.env` inspected (values redacted): only `COINGECKO_API_KEY` present (already provisioned by Phase 0); no `KRAKEN_API_KEY`/`KRAKEN_API_SECRET` values exist yet to leak; `ACCOUNT-CHECKLIST.md` contains no secret values, only checkbox status |

**Code-verifiable score:** 20/20 truths verified.
**Human-owned score:** Roadmap SC #2 (accounts) is PARTIAL — IBKR and Kraken are in progress; Independent Reserve has not started. This is a human checkpoint gap, not a code gap.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `trader/data/db.py` | `get_connection, apply_migrations, upsert_instrument, get_instrument, read_bars_cache, write_bars_cache` | VERIFIED | All 6 functions present and grep-confirmed at their documented line numbers |
| `migrations/0001_ground_truth.sql` | idempotent retrofit of Phase 0 DDL | VERIFIED | File exists; live DB `schema_version` max=2 confirms both migrations applied |
| `migrations/0002_instruments_bars.sql` | instruments + bars DDL | VERIFIED | File exists; live DB has both tables with expected columns |
| `trader/data/classify.py` | `classify_crypto_instrument`, `register_crypto_instrument` | VERIFIED | Both present; wired into `api.py` |
| `trader/data/stock_source.py` | `fetch_stock_bars`, `normalize_stock_bars` | VERIFIED | Present; imported cleanly, used by `api.py` |
| `trader/data/crypto_source.py` | `fetch_crypto_bars`, `fetch_all_daily_ohlcv`, `normalize_crypto_bars`, `CRYPTO_VENUE` | VERIFIED | Present; imported cleanly, used by `api.py` |
| `trader/data/api.py` | `get_daily_bars`, `resolve_instrument`, `CRYPTO_COINGECKO_IDS` | VERIFIED | Present; live-run proven twice (orchestrator + this session) |
| `.planning/phases/01-accounts-data-plumbing/ACCOUNT-CHECKLIST.md` | tracked account status | VERIFIED (artifact exists) | Exists with 3 sections; content shows 2 of 3 accounts in progress, 1 not started — see human_verification |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `db.py get_connection` | `migrations/*.sql` | `apply_migrations` | WIRED | `get_connection` calls `apply_migrations(conn, migrations_dir="migrations")` (db.py:24) |
| `db.py write_bars_cache` | `bars` UNIQUE constraint | `INSERT OR IGNORE` | WIRED | Confirmed at db.py:165 |
| `classify.py classify_crypto_instrument` | `api.coingecko.com/api/v3/coins/{id}` | `x-cg-demo-api-key` header | WIRED | Confirmed at classify.py:41 |
| `classify.py register_crypto_instrument` | `db.py upsert_instrument` | persisted at onboarding time | WIRED | Confirmed at classify.py:72 |
| `api.py get_daily_bars` | `db.py read_bars_cache`/`write_bars_cache` | cache-first read, fetch-on-miss write-through | WIRED | Confirmed at api.py:133/139/140 |
| `api.py get_daily_bars` | `stock_source.py`/`crypto_source.py` | asset_class-routed dispatch | WIRED | Confirmed at api.py:136/138 |
| `api.py resolve_instrument` | `classify.py register_crypto_instrument` | base-asset -> coingecko_id lookup | WIRED | Confirmed at api.py:86; live DB row for DOGE/USDT is functional proof, not just static wiring |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `get_daily_bars` DataFrame | `df` (open/high/low/close/volume, UTC index) | `db.read_bars_cache` <- `write_bars_cache` <- live Yahoo/Binance fetch on miss | Yes — live DB holds 17,340 real bar rows (AAPL, BTC/USDT, DOGE/USDT) | FLOWING |
| `instruments` table | `asset_class`, `coingecko_id` | `register_crypto_instrument` <- `classify_crypto_instrument` <- live CoinGecko categories | Yes — DOGE/USDT row has real `coingecko_id='dogecoin'`, `asset_class='memecoin'`, not a static default | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full test suite green | `.venv/Scripts/python.exe -m pytest tests/ -q` | `53 passed in 8.50s` | PASS |
| DB schema at expected version | sqlite query on `data/trader.db` | `schema_version` max=2, tables include instruments+bars | PASS |
| Cache-hit is genuinely fast (no live fetch) | `get_daily_bars("DOGE/USDT")` timed | 2,579 rows, UTC tz, 0.086s | PASS |
| No real secret committed | inspect `.env` (redacted), `.gitignore` | Only `COINGECKO_API_KEY` present; `.gitignore` excludes `.env`/`data/` | PASS |
| Module import surface resolves | `from trader.data import db, classify, api, stock_source, crypto_source` | Imports clean, signatures match plan contracts | PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` convention exists in this project and no PLAN/SUMMARY references a probe script. SKIPPED (no probe-based verification declared for this phase — this phase uses live smoke scripts (`classify_smoke.py`, `exit_criterion_smoke.py`) instead, both cited above with live evidence).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| ACCT-01 | 01-03 | IBKR account and paper trading account approved | NEEDS HUMAN | Application "in progress," live-submission unconfirmed |
| ACCT-02 | 01-03 | Kraken account with trade-only API keys, no withdrawal permission | NEEDS HUMAN | Account created; verification and API key creation still pending |
| ACCT-03 | 01-03 | Independent Reserve KYC complete | NEEDS HUMAN / BLOCKED for this criterion | Not started |
| ACCT-04 | 01-04, 01-05, 01-06 | Historical daily bars source sorted for US stocks and major crypto pairs | SATISFIED | Live evidence: AAPL 11,495 rows, BTC/USDT 3,266 rows, DOGE/USDT 2,579 rows |
| ACCT-05 | 01-01 | Python repo set up with git, config files, `.env` for keys (never committed) | SATISFIED | `.gitignore`/`.env.example` verified; no secret committed |
| ACCT-06 | 01-01, 01-02 | SQLite database in place | SATISFIED | Live DB has `instruments`/`bars`/`schema_version` etc., version 2 |
| ACCT-07 | 01-06 | One function call pulls historical daily bars for any US stock and any major crypto pair | SATISFIED | `get_daily_bars` proven live for both asset classes, one function, one call each |

No orphaned requirements — all 7 ACCT-IDs are claimed by a plan's `requirements` frontmatter field and each maps to verified evidence or a clearly scoped human item.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `trader/data/db.py` | 161 | Docstring text "placeholders only" (matched a `PLACEHOLDER`-style grep) | None (false positive) | This is prose describing parameterized SQL `?` placeholders, not a stub marker — no code impact |

No TBD/FIXME/XXX/TODO/HACK debt markers, no empty `return null`/`return {}` stub implementations, no hardcoded-empty state feeding a render path found in any Phase 1 file.

### Human Verification Required

### 1. Independent Reserve KYC signup

**Test:** Sign up for an NZD-capable Independent Reserve account and submit government ID, selfie/liveness check, and proof of address.
**Expected:** IR account created, KYC application submitted (approval not required to unblock this checkpoint per D-14, but the application must be started — ACCOUNT-CHECKLIST.md currently shows "Not started").
**Why human:** Requires the account owner's real identity documents; cannot be automated or verified from the codebase.

### 2. IBKR live-application submission confirmation

**Test:** Confirm in interactivebrokers.com Client Portal that the Individual account application (photo ID + proof of residency) has actually been submitted, not merely started.
**Expected:** Client Portal shows the application in submitted/pending-review or Approved state.
**Why human:** ACCOUNT-CHECKLIST.md notes portal access exists with a paper-type account (DUR285675), but live-application submission is unconfirmed — only the account owner can verify this in the IBKR portal.

### 3. Kraken identity verification + trade-only API key creation

**Test:** Complete Kraken's identity verification, create an API key with exactly Query Funds / Query Open Orders & Trades / Query Closed Orders & Trades / Modify Orders / Cancel-Close Orders ticked (Withdraw Funds and the rest unticked), visually confirm Withdraw Funds shows disabled, then enter `KRAKEN_API_KEY`/`KRAKEN_API_SECRET` into `.env` only.
**Expected:** Kraken account verified; API key exists with trade-only permissions; Withdraw Funds confirmed disabled; both key values present in `.env` (never `.env.example`, never a committed file).
**Why human:** Identity verification and permission-checkbox selection happen entirely in Kraken's UI. Confirmed via direct inspection: `.env` currently contains only `COINGECKO_API_KEY=`, with no `KRAKEN_API_KEY`/`KRAKEN_API_SECRET` lines yet.

### Gaps Summary

No code gaps found. All 20 code-level must-haves across Plans 01-01, 01-02, 01-04, 01-05, and 01-06 are verified at all three-to-four levels (exist, substantive, wired, and — for `get_daily_bars`/`resolve_instrument` — data actually flowing through a live SQLite database with 17,340 real bar rows and a real CoinGecko-classified `instruments` row). The full test suite is green at 53/53 with no regressions across the phase's five waves of code work.

The phase's Roadmap Success Criterion #2 — "IBKR paper account, Kraken API keys (trade-only), and Independent Reserve KYC are in progress or done" — is only partially met. Two of three (IBKR, Kraken) are genuinely in progress per D-14's "submitted is sufficient" bar, but Independent Reserve has not started at all, and neither IBKR's live-application submission nor Kraken's trade-only key creation is complete. These are exclusively human/third-party account actions (Plan 01-03 is explicitly `autonomous: false`, a `checkpoint:human-action` task) — no code exists to build or fix here. Routing to `human_needed` rather than `gaps_found` per the phase's own design (Plan 01-03 batches these into a non-blocking human checkpoint that was never meant to gate the code waves) and per the explicit account-item instructions for this verification pass.

---

*Verified: 2026-07-26*
*Verifier: Claude (gsd-verifier)*
