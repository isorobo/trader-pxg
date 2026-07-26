---
phase: 01-accounts-data-plumbing
plan: 05
subsystem: data
tags: [ccxt, binance, crypto, pagination, tdd]

# Dependency graph
requires:
  - phase: 01-accounts-data-plumbing
    provides: "ccxt 4.5.68 dependency pinned in 01-01"
provides:
  - "trader/data/crypto_source.py with fetch_crypto_bars, fetch_all_daily_ohlcv, normalize_crypto_bars"
  - "CRYPTO_VENUE = \"binance\" true-provenance constant for bars.venue"
affects: [01-06, crypto-data-routing, get_daily_bars]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Binance-only crypto fetch path (no Kraken data-fetch code) eliminates the 720-candle silent-truncation risk by construction"
    - "Pagination loop advances cursor to last-row-timestamp + one day, stops on a short/empty batch"
    - "Row-shape validation raises ValueError before mis-unpacking, matching stock_source.py's convention"

key-files:
  created: [trader/data/crypto_source.py, tests/test_crypto_source.py]
  modified: []

key-decisions:
  - "No Kraken data-fetch code exists in this module — Binance is the sole crypto fetch venue for Phase 1, per 01-RESEARCH.md Pitfall 2"
  - "fetch_crypto_bars defaults since_ms to 2017-01-01 in ms when not given, requesting full available history rather than a truncated window"

patterns-established:
  - "Crypto fetcher mirrors stock_source.py's normalize_*_bars → fetch_*_bars structure so 01-06's router can call both fetchers uniformly"

requirements-completed: [ACCT-04]

# Metrics
duration: 15min
completed: 2026-07-26
---

# Phase 01 Plan 05: Crypto Fetcher (Binance via ccxt) Summary

**Binance-only ccxt crypto fetcher with 1000-candle pagination and UTC-date normalization, deliberately excluding Kraken's 720-candle-capped endpoint.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-26T01:35:00Z
- **Completed:** 2026-07-26T01:50:13Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `fetch_all_daily_ohlcv` correctly concatenates rows across paginated Binance calls and stops as soon as a batch is shorter than `limit=1000`
- `normalize_crypto_bars` converts Unix-millisecond timestamps to plain UTC `YYYY-MM-DD` date strings, matching Plan 01-04's stock row contract exactly
- `fetch_crypto_bars` constructs `ccxt.binance()` with no API key (public market data only) and exposes `CRYPTO_VENUE = "binance"` as the true data-provenance constant for Plan 01-06

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for Binance pagination and UTC normalization (RED)** - `2ba1245` (test)
2. **Task 2: Implement Binance fetch, pagination, and UTC-date normalization (GREEN)** - `272930a` (feat)

_Note: TDD plan — test commit (RED) precedes feat commit (GREEN)._

## Files Created/Modified
- `tests/test_crypto_source.py` - 4 tests: pagination past 1000 rows, UTC-date normalization, no-API-key Binance construction, malformed-row ValueError
- `trader/data/crypto_source.py` - `fetch_crypto_bars`, `fetch_all_daily_ohlcv`, `normalize_crypto_bars`, `CRYPTO_VENUE`

## Decisions Made
- Followed the plan's locked decision to implement only the Binance path — no Kraken fetch code was added, even as a fallback, so the 720-candle silent-truncation risk (01-RESEARCH.md Pitfall 2) is eliminated by construction rather than a runtime row-count assertion.
- Used a fixed 2017-01-01 epoch default for `since_ms` when the caller omits it, matching the plan's "default since_ms to a fixed early epoch" instruction and the research's confirmation that Binance's BTC/USDT history reaches back to 2018.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. Tests mock `ccxt`; no live network calls occur in this plan.

## Next Phase Readiness

- `trader/data/crypto_source.py` is ready for Plan 01-06's `get_daily_bars` router to call alongside `trader/data/stock_source.py`, using `CRYPTO_VENUE` as the true `bars.venue` value for crypto rows.
- Full test suite green at 45 tests (41 baseline + 4 new), no regressions to Phase 0 or earlier Phase 1 plans.

---
*Phase: 01-accounts-data-plumbing*
*Completed: 2026-07-26*

## Self-Check: PASSED

- FOUND: trader/data/crypto_source.py
- FOUND: tests/test_crypto_source.py
- FOUND: .planning/phases/01-accounts-data-plumbing/01-05-SUMMARY.md
- FOUND: 2ba1245 (test commit)
- FOUND: 272930a (feat commit)
