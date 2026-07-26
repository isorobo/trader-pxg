---
phase: 01-accounts-data-plumbing
plan: 06
subsystem: data
tags: [api, get-daily-bars, cache, tdd, exit-criterion]

# Dependency graph
requires:
  - phase: 01-accounts-data-plumbing
    provides: "trader/data/db.py cache + instrument helpers (01-01)"
  - phase: 01-accounts-data-plumbing
    provides: "trader/data/classify.py register_crypto_instrument (01-02)"
  - phase: 01-accounts-data-plumbing
    provides: "trader/data/stock_source.py fetch_stock_bars (01-04)"
  - phase: 01-accounts-data-plumbing
    provides: "trader/data/crypto_source.py fetch_crypto_bars, CRYPTO_VENUE (01-05)"
provides:
  - "trader/data/api.py get_daily_bars(symbol, start=None, end=None, asset_class=None, conn=None) -> pandas.DataFrame"
  - "trader/data/api.py resolve_instrument(conn, symbol, asset_class=None) -> tuple[str, str]"
  - "trader/data/api.py CRYPTO_COINGECKO_IDS (D-15 named-universe symbol-to-id lookup)"
  - "trader/data/exit_criterion_smoke.py live acceptance script"
affects: [phase-2-point-in-time-iterator, backtesting]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cache-first router: read_bars_cache before any live fetcher call; write-through on miss then re-read for a single source of truth"
    - "resolve_instrument precedence: explicit asset_class arg > instruments table row (override then asset_class) > crypto-shape + CRYPTO_COINGECKO_IDS classification > stock default"
    - "DataFrame index built via pd.to_datetime(ts).dt.tz_localize('UTC') — explicit UTC tz-aware, never a naive date index"

key-files:
  created:
    - trader/data/api.py
    - trader/data/exit_criterion_smoke.py
    - tests/test_data_api.py
  modified: []

key-decisions:
  - "resolve_instrument queries instruments WHERE symbol = ? LIMIT 1 (not filtered by venue) per the plan's D-10 primary-resolution-path instruction, since Phase 1 does not yet support one symbol under two asset classes simultaneously"
  - "venue is derived purely from resolved asset_class via a hardcoded mapping (stock->yahoo, crypto_major/memecoin->crypto_source.CRYPTO_VENUE), never conflated with the Kraken fee-model venue (T-01-11 mitigation)"
  - "Cache-hit test wrote 8 tests instead of the plan's stated 'seven' — the plan's <behavior> block names 8 distinct tests (each mapping to a separate must_haves truth); the 'seven' count elsewhere in the plan prose is treated as the inconsistency and all 8 named tests are kept for full contract coverage"

requirements-completed: [ACCT-04, ACCT-07]

# Metrics
duration: 25min
completed: 2026-07-26
---

# Phase 01 Plan 06: get_daily_bars Public API + Live Exit-Criterion Acceptance Summary

**Cache-first get_daily_bars router wiring stock/crypto fetchers and CoinGecko classification behind one call, proven live against real Yahoo Finance and Binance data.**

## Performance

- **Duration:** 25 min
- **Tasks:** 3
- **Files modified:** 3 (all new)

## Accomplishments

- `get_daily_bars(symbol, start=None, end=None, asset_class=None, conn=None)` returns a `pandas.DataFrame` with an explicit UTC tz-aware `DatetimeIndex` and columns `open, high, low, close, volume` — the phase's literal ACCT-07 exit-criterion function
- `resolve_instrument` wires `classify.register_crypto_instrument` into the onboarding path: an unresolved crypto symbol whose base asset is in `CRYPTO_COINGECKO_IDS` (D-15's named universe — BTC, ETH, DOGE, SHIB, PEPE, BONK, WIF) is classified live via CoinGecko before routing, never silently defaulted (D-16)
- A crypto symbol outside the named universe falls back to a documented, logged `crypto_major` default with `coingecko_id=None`, persisted directly via `db.upsert_instrument` — no unhandled classification gap
- Cache-first behavior is provably correct: a full cache hit makes zero calls to either fetcher; a miss-then-hit sequence fetches once, writes through, and returns byte-identical DataFrame content on the second call
- Live acceptance run (`trader/data/exit_criterion_smoke.py`) proves the exit criterion end-to-end with no mocks: `get_daily_bars("AAPL", asset_class="stock")` returned **11,495 rows** spanning **1980-12-12 to 2026-07-24**; `get_daily_bars("BTC/USDT", asset_class="crypto_major")` returned **3,266 rows** spanning **2017-08-17 to 2026-07-26** — both with `index.tz=UTC`, both from the same function, script exited 0

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for get_daily_bars routing, cache-first behavior, classification wiring, and the tz-aware DataFrame contract (RED)** - `5c29dcd` (test)
2. **Task 2: Implement get_daily_bars — cache-first routing, classification-wired resolve_instrument, tz-aware UTC index (GREEN)** - `b833889` (feat)
3. **Task 3: Live exit-criterion acceptance run — real stock and real crypto pair, one function call each** - `398aee1` (feat)

_Note: TDD plan — test commit (RED) precedes feat commit (GREEN); Task 3 is the live, non-mocked acceptance run._

## Files Created/Modified

- `tests/test_data_api.py` - 8 tests: stock contract, UTC tz-aware index, crypto contract + venue provenance, cache-hit skips fetch, cache-miss-then-hit content equality, instruments-table resolution, CoinGecko classification wiring for the named universe, degraded fallback for an unmapped crypto symbol
- `trader/data/api.py` - `get_daily_bars`, `resolve_instrument`, `CRYPTO_COINGECKO_IDS`, `_venue_for_asset_class`, `_is_cache_hit`
- `trader/data/exit_criterion_smoke.py` - live, no-mock acceptance script calling `get_daily_bars` once per asset class against the project's real `data/trader.db`

## Decisions Made

- Followed the plan's locked venue-provenance decision exactly: `_venue_for_asset_class` hardcodes `stock -> "yahoo"` and everything else `-> crypto_source.CRYPTO_VENUE` ("binance"), so `bars.venue` never carries the Kraken fee-model label.
- Cache-hit detection treats `start=None` with a non-empty cache as a full hit, and otherwise checks the earliest cached row's `ts` against the requested `start`, per the plan's literal instruction — no additional end-date staleness check was added since the plan scoped that out for this phase.
- Wrote and kept all 8 tests named in the plan's `<behavior>` block rather than trimming to match the "seven" count stated in the plan's prose elsewhere (Task 1 `<action>`/`<acceptance_criteria>`), since each of the 8 named tests maps to a distinct `must_haves.truths` entry and dropping one would leave a truth unverified. Documented as a deviation below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - internal plan inconsistency] Kept 8 tests instead of the stated 7**
- **Found during:** Task 1
- **Issue:** The plan's `<behavior>` block for Task 1 lists 8 distinctly named tests (`test_get_daily_bars_stock_contract` through `test_get_daily_bars_falls_back_without_classification_for_unmapped_crypto_symbol`), but the `<action>` and `<acceptance_criteria>` sections both say "seven" / "exactly 7 test functions". This is an internal miscount in the plan document, not an ambiguity about which test to drop — every named test maps to a separate `must_haves.truths` line (routing, tz-awareness, cache-hit, cache-miss-then-hit, instruments-table resolution, named-universe classification, and the degraded fallback for an unmapped symbol are all distinct behaviors).
- **Fix:** Wrote all 8 tests exactly as named and described in `<behavior>`. Collection and RED/GREEN both ran cleanly against all 8.
- **Files modified:** `tests/test_data_api.py`
- **Commits:** `5c29dcd` (RED), `b833889` (GREEN, full suite verified against all 8)

## Issues Encountered

None — no auth gates, no blocking issues, no architectural questions.

## User Setup Required

None. `.env`'s `COINGECKO_API_KEY` (already configured in Plan 01-02) was reused for the crypto-classification path; no crypto symbol tested in this plan required a live CoinGecko call since both `get_daily_bars` calls in the live run used explicit `asset_class=` arguments, bypassing classification per `resolve_instrument`'s documented precedence.

## Next Phase Readiness

- `trader/data/api.py get_daily_bars` is the stable, tested public entry point Phase 2's point-in-time iterator will call — its UTC tz-aware `DatetimeIndex` contract is locked (D-11).
- Full test suite green at 53 tests (45 baseline + 8 new), no regressions to Phase 0 or earlier Phase 1 plans.
- Live exit-criterion proof recorded above satisfies ACCT-04 and ACCT-07 — Phase 1's data-plumbing exit criteria are met pending final phase-level sign-off.

---
*Phase: 01-accounts-data-plumbing*
*Completed: 2026-07-26*

## Self-Check: PASSED

- FOUND: trader/data/api.py
- FOUND: trader/data/exit_criterion_smoke.py
- FOUND: tests/test_data_api.py
- FOUND: 5c29dcd (test commit)
- FOUND: b833889 (feat commit)
- FOUND: 398aee1 (feat commit, live run)
