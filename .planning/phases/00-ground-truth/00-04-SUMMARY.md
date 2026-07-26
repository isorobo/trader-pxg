---
phase: 00-ground-truth
plan: 04
subsystem: reporting
tags: [pytest, tdd, yfinance, coingecko, sqlite, markdown]

# Dependency graph
requires:
  - phase: 00-ground-truth (plan 02)
    provides: trader/ground_truth/db.py — query_flagged_tickers_since, query_poll_run_coverage pinned contracts
provides:
  - trader/ground_truth/report.py — daily report generator (format_coingecko_date, fetch_stock_close, fetch_crypto_close, compute_report_rows, compute_coverage_stat, write_report_markdown, main)
  - Dated markdown report at reports/{date}.md plus stdout summary, answering "what % ended the day up vs dumped"
affects: [00-05]

# Tech tracking
tech-stack:
  added: []
  patterns: [DD-MM-YYYY date formatting isolated to a single named function (format_coingecko_date) rather than inlined at call sites, empty-list early-return guard before any network/env lookups]

key-files:
  created:
    - trader/ground_truth/report.py
    - tests/test_report.py
  modified:
    - .gitignore

key-decisions:
  - "compute_report_rows returns [] immediately when query_flagged_tickers_since is empty, before touching dotenv or making any network call — the empty-state guard costs nothing and needs no mocks to test"
  - "reports/ added to .gitignore alongside data/ — daily-generated markdown files are regenerated artifacts, not tracked source, matching the existing data/*.db convention (D-12 left this to Claude's discretion)"
  - "fetch_crypto_close catches all errors and returns None per-ticker rather than raising, so one bad CoinGecko lookup never crashes the whole report — consistent with sources.py's existing single-failure-point pattern"

patterns-established:
  - "Pattern: close-price fetch functions (fetch_stock_close, fetch_crypto_close) return None on any missing/error data rather than raising, keeping compute_report_rows crash-free by construction"

requirements-completed: [DATA-03]

# Metrics
duration: 3min
completed: 2026-07-26
---

# Phase 0 Plan 04: Daily Report Generator Summary

**Daily markdown report joining snapshot first-sight data with yfinance/CoinGecko same-day and next-day closes, computing the up/down split the owner asked for, built test-first and verified against the real empty database**

## Performance

- **Duration:** 3 min
- **Started:** 2026-07-26T00:25:00Z
- **Completed:** 2026-07-26T00:28:33Z
- **Tasks:** 3
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments
- Wrote 7 failing tests against `trader.ground_truth.report` before the module existed (RED) — covering CoinGecko's DD-MM-YYYY date quirk, yfinance's 1-day history window, the compute/join logic, coverage delegation, markdown writing, and the pre-collection empty-state guard
- Implemented `report.py`: all 7 exported functions from the plan's `must_haves.artifacts`, all 7 tests green (GREEN), full suite (17 tests including Plans 00-02's 10) green
- Ran `python -m trader.ground_truth.report` against the real (previously non-existent) `data/trader.db` — exit code 0, produced `reports/2026-07-26.md` stating "0 tickers flagged in this window" and "0/673 polls (0.0%)" coverage, proving the empty-state guard holds against the real database path, not just the fixture path

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for report computation (RED)** - `01e4240` (test)
2. **Task 2: Implement the daily report generator (GREEN)** - `d02c24f` (feat)
3. **Task 3: Empty-state dry run against the real (pre-collection) database** - `9abcb09` (chore)

**Plan metadata:** (this commit, following SUMMARY.md write)

## Files Created/Modified
- `tests/test_report.py` - 7 tests: DD-MM-YYYY formatting, yfinance 1-day window, CoinGecko history date param, row computation/join, coverage delegation, markdown output, empty-snapshot guard
- `trader/ground_truth/report.py` - `format_coingecko_date`, `fetch_stock_close`, `fetch_crypto_close`, `compute_report_rows`, `compute_coverage_stat`, `write_report_markdown`, `main` CLI (`--date`, defaults to today)
- `.gitignore` - added `reports/` alongside the existing `data/` exclusion

## Decisions Made
- Isolated the CoinGecko `DD-MM-YYYY` quirk (Pitfall 6) into a single `format_coingecko_date` function so it is tested once and never re-derived inline at a call site
- Kept `fetch_crypto_close`/`fetch_stock_close` returning `None` on any missing or errored data rather than raising, so a single bad ticker lookup never takes down the whole report run
- Added `reports/` to `.gitignore` (Claude's discretion per D-12) — daily reports are regenerated, not source

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] Added directory creation before DB connect and file write**
- **Found during:** Task 2/3
- **Issue:** `db.get_connection` does not create the parent directory for `db_path`, and no `data/` or `reports/` directory existed yet in this fresh repo. Running `main()` against the real database would have raised `sqlite3.OperationalError: unable to open database file`.
- **Fix:** `main()` calls `os.makedirs("data", exist_ok=True)` before opening the connection; `write_report_markdown` calls `os.makedirs(out_dir, exist_ok=True)` before writing the file.
- **Files modified:** `trader/ground_truth/report.py`
- **Commit:** `d02c24f`

**2. [Rule 2 - missing critical functionality] gitignored the generated reports/ directory**
- **Found during:** Task 3
- **Issue:** After the dry run, `reports/2026-07-26.md` showed as an untracked file with no `.gitignore` rule covering it, which would otherwise let regenerated daily reports accumulate as untracked noise or get accidentally committed one at a time.
- **Fix:** Added `reports/` to `.gitignore`, matching the existing `data/` convention for regenerated local artifacts.
- **Files modified:** `.gitignore`
- **Commit:** `9abcb09`

## Issues Encountered
None.

## User Setup Required
None — reused the existing `COINGECKO_API_KEY` from `.env` (Plan 00-01), consistent with `sources.py`'s loading pattern. No new external service configuration.

## Next Phase Readiness
- `report.py` exports the exact functions listed in this plan's `must_haves.artifacts`, tested against both a fixture dataset and the real (empty) database
- The empty-state guard is proven twice: once via the mocked `test_compute_report_rows_handles_empty_snapshots` test, once via the live dry run against `data/trader.db` — Plan 00-05 can rely on this not crashing on day one
- No blockers identified for Plan 00-05

---
*Phase: 00-ground-truth*
*Completed: 2026-07-26*

## Self-Check: PASSED

All files created in this plan verified present on disk (`trader/ground_truth/report.py`, `tests/test_report.py`, this SUMMARY.md). All 3 task commit hashes (`01e4240`, `d02c24f`, `9abcb09`) verified present in `git log`.
