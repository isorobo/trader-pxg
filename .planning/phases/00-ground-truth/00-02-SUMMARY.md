---
phase: 00-ground-truth
plan: 02
subsystem: database
tags: [sqlite, wal, yfinance, finviz, coingecko, pytest, tdd]

# Dependency graph
requires:
  - phase: 00-ground-truth (plan 01)
    provides: trader/ src-layout package skeleton, pinned .venv, .env with COINGECKO_API_KEY
provides:
  - trader/ground_truth/db.py — get_connection, ensure_schema, insert_snapshot_rows, record_poll_run, query_flagged_tickers_since, query_poll_run_coverage
  - trader/ground_truth/sources.py — StockGainersSource, CryptoMoversSource, SourceUnavailableError
  - trader/ground_truth/smoke.py — live smoke-test entry point
  - Pinned first-seen key contract for query_flagged_tickers_since (source, ticker, coingecko_id, first_seen_ts, first_price, first_pct_gain)
affects: [00-03, 00-04, 00-05]

# Tech tracking
tech-stack:
  added: []
  patterns: [WAL-mode SQLite connection helper, source adapter with primary/fallback, parameterized-SQL-only inserts, injectable now= for wall-clock-free tests]

key-files:
  created:
    - trader/ground_truth/db.py
    - trader/ground_truth/sources.py
    - trader/ground_truth/smoke.py
    - tests/conftest.py
    - tests/test_db.py
    - tests/test_sources.py
  modified: []

key-decisions:
  - "query_flagged_tickers_since pins an exact 6-key contract (source, ticker, coingecko_id, first_seen_ts, first_price, first_pct_gain) so Plan 00-04's report.py builds against a locked interface, not discovery"
  - "query_poll_run_coverage takes an injectable now: datetime | None so production call sites never pass it, while tests pin it to remove wall-clock dependency"
  - "Live smoke test confirmed yfinance 1.5.2's day_gainers screener returns 50 rows (no 25-row truncation bug) — no finviz primary/fallback swap needed"

patterns-established:
  - "Pattern: source adapter class with fetch_top_movers(count) trying primary then fallback, raising a single SourceUnavailableError only when both fail"
  - "Pattern: SQLite connections always set journal_mode=WAL and busy_timeout=5000 via get_connection before any write"

requirements-completed: [DATA-01, DATA-02]

# Metrics
duration: 9min
completed: 2026-07-26
---

# Phase 0 Plan 02: Snapshot Schema and Source Adapters Summary

**Snapshot schema (snapshots/poll_runs/schema_version tables, WAL mode) plus yfinance-primary/finviz-fallback stock adapter and CoinGecko crypto adapter, built test-first with a pinned query_flagged_tickers_since contract for Plan 00-04**

## Performance

- **Duration:** 9 min
- **Started:** 2026-07-26T00:10:59Z
- **Completed:** 2026-07-26T00:19:30Z
- **Tasks:** 3
- **Files modified:** 6 (all created)

## Accomplishments
- Wrote 10 failing tests against `trader.ground_truth.db` and `trader.ground_truth.sources` before either module existed (RED), pinning the schema and adapter contracts up front
- Implemented `db.py`: WAL-mode connection helper with `busy_timeout=5000`, three-table schema (`snapshots`, `poll_runs`, `schema_version`), parameterized insert/query helpers, and a coverage query with an injectable `now` for deterministic tests
- Implemented `sources.py`: `StockGainersSource` (yfinance `day_gainers` primary, finviz fallback, single `SourceUnavailableError` when both fail) and `CryptoMoversSource` (CoinGecko `/coins/markets`, coingecko_id + uppercased symbol, client-side sort by 24h % change) — all 10 tests green (GREEN)
- Ran the live smoke test against real Yahoo Finance and CoinGecko endpoints: both returned 50 rows (well above the 40-row threshold), confirming Assumption A1 (no yfinance screener truncation bug on 1.5.2) and A2 (CoinGecko demo key authenticates) — no adapter reordering needed

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for snapshot schema and source adapters (RED)** - `414afd7` (test)
2. **Task 2: Implement snapshot schema (db.py) and source adapters (sources.py) (GREEN)** - `0a2b1ae` (feat)
3. **Task 3: Live smoke test against real Yahoo Finance and CoinGecko endpoints** - `b47d2d0` (feat)

**Plan metadata:** (this commit, following SUMMARY.md write)

## Files Created/Modified
- `tests/conftest.py` - Fixtures: `tmp_db_path`, `conn`, `mock_yf_screen_result`, `mock_finviz_rows`, `mock_coingecko_markets_response`
- `tests/test_db.py` - 5 tests: WAL/busy_timeout pragmas, schema tables, insert round-trip, poll-run coverage (injected `now`), pinned `query_flagged_tickers_since` key contract
- `tests/test_sources.py` - 5 tests: stock adapter normalization, finviz fallback, `SourceUnavailableError` on double failure, crypto `coingecko_id`/symbol mapping, crypto sort-by-pct-change
- `trader/ground_truth/db.py` - Connection/schema/insert/query helpers, parameterized SQL only
- `trader/ground_truth/sources.py` - `StockGainersSource`, `CryptoMoversSource`, `SourceUnavailableError`
- `trader/ground_truth/smoke.py` - Live smoke-test `main()` entry point, no mocks

## Decisions Made
- Used SQLite's `IS` operator (NULL-safe equality) to join grouped-MIN rows back to their source row in `query_flagged_tickers_since`, since `coingecko_id` is `NULL` for stock rows and ordinary `=` does not match `NULL = NULL`
- Kept `smoke.py` free of any DB writes — it only exercises the two source adapters against live networks and prints counts, per the plan's stated scope

## Deviations from Plan

None - plan executed exactly as written. The live smoke test's contingency branch ("if stock source returns fewer than 40 rows, swap finviz to primary") was not triggered — yfinance returned 50 rows on the first live run.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. The CoinGecko demo key from Plan 00-01 was reused as-is.

## Next Phase Readiness
- `db.py` and `sources.py` export the exact functions/classes listed in this plan's `must_haves.artifacts`, ready for Plan 00-03's `poll.py` to import directly
- `query_flagged_tickers_since`'s exact 6-key return contract is locked and tested; Plan 00-04's `report.py` can build against it without re-discovering the shape
- Live endpoints confirmed reachable and returning full row counts as of 26 July 2026; no adapter reordering carried into Plan 00-03
- No blockers identified for Plan 00-03

---
*Phase: 00-ground-truth*
*Completed: 2026-07-26*

## Self-Check: PASSED

All 7 files created in this plan verified present on disk. All 3 task commit hashes (`414afd7`, `0a2b1ae`, `b47d2d0`) verified present in `git log`.
