---
phase: 01-accounts-data-plumbing
plan: 04
subsystem: data
tags: [yfinance, pandas, timezone-normalization, tdd]

# Dependency graph
requires:
  - phase: 01-accounts-data-plumbing
    provides: trader/data/db.py's write_bars_cache row contract (ts/open/high/low/close/volume) from Plan 01-01
provides:
  - trader/data/stock_source.py contract (fetch_stock_bars, normalize_stock_bars)
  - the stock half of D-01's get_daily_bars routing (Plan 01-06 consumes this directly)
affects: ["01-06 (get_daily_bars router calls fetch_stock_bars for asset_class='stock')"]

# Tech tracking
tech-stack:
  added: []
  patterns: ["tz-aware yfinance index normalized to a plain UTC calendar-date string before it ever reaches SQLite, dropping intraday time-of-day entirely for daily bars"]

key-files:
  created:
    - trader/data/stock_source.py
    - tests/test_stock_source.py
  modified: []

key-decisions:
  - "normalize_stock_bars raises ValueError (not a bare KeyError) on a missing expected OHLCV column, satisfying the T-01-04 threat-model mitigation"
  - "RED-phase tests guard the trader.data.stock_source import with try/except ImportError (module = None), matching Plan 01-01's precedent, so collect-only reports zero collection errors while every test still fails on execution"

patterns-established:
  - "Pattern: tz-aware pandas index -> .tz_convert('UTC').strftime('%Y-%m-%d') immediately after fetch, before any cache write (01-RESEARCH.md Pattern 2)"

requirements-completed: [ACCT-04]

# Metrics
duration: ~5min
completed: 2026-07-26
---

# Phase 1 Plan 04: Stock Bar Fetcher Summary

**yfinance-backed fetch_stock_bars/normalize_stock_bars converting the tz-aware America/New_York index to a plain UTC calendar-date string, matching db.py's cache row contract exactly**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-07-26T13:45:00+12:00
- **Completed:** 2026-07-26T13:46:28+12:00
- **Tasks:** 2
- **Files modified:** 2 (2 created)

## Accomplishments
- `tests/test_stock_source.py` pins the tz-normalization contract with 4 tests, written and confirmed RED before any implementation existed
- `trader/data/stock_source.py` implements `fetch_stock_bars(symbol, start=None, end=None)` and `normalize_stock_bars(df)`, correcting D-11's "UTC timestamps" assumption per 01-RESEARCH.md Pitfall 1
- Full suite green at 41 passed (37 pre-existing + 4 new), no regression

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for stock bar fetch and UTC normalization (RED)** - `bb4d5f0` (test)
2. **Task 2: Implement stock bar fetch and UTC-date normalization (GREEN)** - `9fdb1b6` (feat)

**Plan metadata:** (this commit, filed after this Summary)

## Files Created/Modified
- `tests/test_stock_source.py` - 4 tests: UTC-date normalization shape, period="max" default, explicit start/end, missing-column ValueError
- `trader/data/stock_source.py` - `fetch_stock_bars` (yfinance.Ticker wrapper) and `normalize_stock_bars` (tz_convert("UTC") + column rename/select)

## Decisions Made
- Followed 01-RESEARCH.md Pattern 2 exactly: `.tz_convert("UTC").strftime("%Y-%m-%d")` on the index, dropping Dividends/Stock Splits and any intraday time-of-day component.
- `normalize_stock_bars` raises `ValueError` (not a bare `KeyError`) when Open/High/Low/Close/Volume is missing, per the plan's T-01-04 mitigation requirement.
- Mirrored Plan 01-01's RED-phase import-guard pattern (`try/except ImportError: stock_source = None`) so `--collect-only` reports zero collection errors on all 4 tests while each still fails with an `AttributeError`/`ModuleNotFoundError` referencing the missing contract.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. Tests mock `yfinance.Ticker`; no live network call happens in this plan (the live acceptance check is Plan 01-06's job).

## Next Phase Readiness
- `trader/data/stock_source.py`'s contract is stable and matches `trader/data/db.py`'s `write_bars_cache` row shape exactly — no renaming needed at Plan 01-06's call site.
- No blockers.

---
*Phase: 01-accounts-data-plumbing*
*Completed: 2026-07-26*

## Self-Check: PASSED

Verified `trader/data/stock_source.py` and `tests/test_stock_source.py` present on disk. Verified commits `bb4d5f0` and `9fdb1b6` present in `git log --oneline`. Full suite re-run confirms 41 passed.
