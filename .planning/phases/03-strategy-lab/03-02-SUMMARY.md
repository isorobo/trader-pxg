---
phase: 03-strategy-lab
plan: 02
subsystem: backtesting
tags: [python, sqlite, yfinance, ccxt, hashlib, frozen-config, tdd]

# Dependency graph
requires:
  - phase: 03-strategy-lab (plan 01)
    provides: momentum.py/breakout.py pure-function strategy agents (STRAT-01/02)
provides:
  - Frozen D-04 universe lists (universe.py, 25 symbols across 3 buckets)
  - Frozen D-08/D-09 regime windows with tune/OOS splits (regimes.py, 6 regimes)
  - Frozen D-06 exit-parameter grid (exit_grid.py, 270/270/360 cells)
  - Hash-based freeze gate (frozen_config.py, verify_frozen()/FROZEN_HASH)
  - Live-backfilled 25-symbol universe cache in data/trader.db
affects: [03-03, 03-04, 03-05, 03-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Hash-based freeze gate: sha256 over committed config files, hard-coded FROZEN_HASH, verify_frozen() as a hard RuntimeError gate every sweep/OOS entrypoint must call first"
    - "Frozen dataclass config modules (Regime) mirroring config.py's EXIT_PROFILE immutability discipline"
    - "Bucket constants (BUCKET_STOCK/BUCKET_CRYPTO_MAJOR_LEGACY_MEME/BUCKET_NEW_MEMECOIN) kept distinct from per-symbol asset_class values to avoid conflating sweep-grouping with fills/ledger asset_class"

key-files:
  created:
    - trader/backtest/universe.py
    - trader/backtest/regimes.py
    - trader/backtest/exit_grid.py
    - trader/backtest/frozen_config.py
    - trader/backtest/backfill_universe.py
    - tests/test_regime_config.py
    - tests/test_exit_grid.py
    - tests/test_frozen_config.py
  modified: []

key-decisions:
  - "MEMECOIN_SHORT_HOLD_DAYS=3 chosen as Claude's discretion per D-06's additive memecoin time-stop, matching the orchestrator's resolved Open Question 2 (360-cell additive grid, not a replacement of the base three TIME_STOPS)"
  - "backfill_universe.py passes an explicit ancient start date (1900-01-01) for stock symbols, not start=None, to work around a pre-existing api.py._is_cache_hit gap that treated partial 2023-2024-only cache (left over from 03-RESEARCH.md's benchmark) as a full hit"
  - "SLIPPAGE_SMALL_CAP_RUNNER stays unwired and out of scope this phase, per the plan's explicit scope note -- D-04's fixed universe has no scanner-flagged small-cap-runner category to apply it to"

patterns-established:
  - "Frozen-before-results as a code gate: FROZEN_HASH is a hard-coded sha256 digest, not a convention; verify_frozen() raises RuntimeError (uncatchable by accident) if any of the three frozen files differ by even one byte"

requirements-completed: [STRAT-03, STRAT-04, STRAT-05]

# Metrics
duration: 35min
completed: 2026-07-26
---

# Phase 3 Plan 02: Frozen Universe, Regimes, Exit Grid, and Live Backfill Summary

**Hash-gated frozen config (25-symbol universe, 6 regime windows, 270/360-cell exit grid) plus a one-time live backfill populating all 25 symbols with full available history in data/trader.db.**

## Performance

- **Duration:** 35 min
- **Started:** 2026-07-26T00:00:00Z (approx, per plan start)
- **Completed:** 2026-07-26
- **Tasks:** 3
- **Files modified:** 8 (5 created source modules, 3 created test modules)

## Accomplishments
- Froze the D-04 universe (18 stock / 4 crypto-major+legacy-meme / 3 new-memecoin) and D-08/D-09 regime windows (6 regimes, tune_end < oos_start proven for all) in committed, immutable-dataclass code
- Froze the D-06 exit-parameter grid (270 cells for stock and crypto-major/legacy-meme buckets, 360 additive cells for new-memecoin) behind a hard-coded sha256 hash gate that raises RuntimeError on any byte-level post-hoc edit
- Ran the one-time live backfill: all 25 universe symbols now cached in data/trader.db with full available history, matching 03-RESEARCH.md's verified per-symbol row/date figures exactly (e.g. NVDA 6,918 rows back to 1999-01-22, XOM/DIS 16,248 rows back to 1962-01-02)

## Task Commits

Each task was committed atomically (TDD tasks split RED/GREEN):

1. **Task 1: Frozen universe and regime windows**
   - `a619070` test(03-02): add failing tests for frozen universe/regime config (RED)
   - `074c129` feat(03-02): freeze D-04 universe and D-08/D-09 regime windows (GREEN)
2. **Task 2: Frozen exit grid + hash-based freeze gate**
   - `09e759d` test(03-02): add failing tests for exit grid and frozen-hash gate (RED)
   - `0f5586f` feat(03-02): freeze D-06 exit grid and add hash-based freeze gate (GREEN)
3. **Task 3: One-time live universe backfill**
   - `8c5937f` feat(03-02): live backfill of the 25-symbol frozen universe

## Files Created/Modified
- `trader/backtest/universe.py` - Frozen 18/4/3 symbol lists, bucket constants, UNIVERSE_BY_BUCKET
- `trader/backtest/regimes.py` - Frozen `Regime` dataclass, 6-entry `REGIMES` tuple with verbatim tune/OOS dates
- `trader/backtest/exit_grid.py` - `exit_profile_grid(bucket)` yielding 270 (stock/crypto-major-legacy-meme) or 360 (new-memecoin) `EXIT_PROFILE` cells
- `trader/backtest/frozen_config.py` - `compute_hash()`/`verify_frozen()`/hard-coded `FROZEN_HASH` over the three frozen files
- `trader/backtest/backfill_universe.py` - One-time live backfill script, mirrors `sanity_universe.py`'s shape
- `tests/test_regime_config.py` - 10 tests: universe list exactness, regime count/split honesty, frozen-instance immutability
- `tests/test_exit_grid.py` - 6 tests: grid cell counts, EXIT_PROFILE shape, additive memecoin time-stop
- `tests/test_frozen_config.py` - 3 tests: hash self-consistency, pass-on-unmodified, RuntimeError-on-tamper via tmp_path copy

## Decisions Made
- `MEMECOIN_SHORT_HOLD_DAYS=3` (Claude's discretion, additive per D-06 and the orchestrator's resolved Open Question 2)
- Explicit ancient `start` date for stock backfill to force full-history refetch around a pre-existing `api.py` cache-hit gap (see Deviations below)
- `frozen_config.compute_hash()` computed once via a throwaway shell command after `exit_grid.py` was finalized, then hard-coded as `FROZEN_HASH` -- the literal freeze point per the plan's action step

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Forced full-history stock backfill around a pre-existing cache-hit gap**
- **Found during:** Task 3 (live universe backfill)
- **Issue:** The plan's literal call shape (`get_daily_bars(symbol, asset_class=..., conn=None)` with no start/end) relies on `trader/data/api.py`'s `_is_cache_hit` treating `start=None` as "full history requested." That function actually returns a hit for `start=None` the moment ANY cached row exists, regardless of range covered. 15 of the 18 stock symbols already had a partial 2023-2024-only cache in `data/trader.db` left over from 03-RESEARCH.md's live sweep-runtime benchmark. A literal no-start call silently left those 15 symbols with only ~2 years of history -- short of the stock choppy regime's 2015-01-01 tune_start, which would have failed the plan's own acceptance criteria.
- **Fix:** `backfill_universe.py` passes an explicit, deliberately ancient `start="1900-01-01"` for every stock symbol (crypto symbols keep `start=None`, since `crypto_source.fetch_crypto_bars` ignores the start argument entirely and already returned full-range data). This makes `_is_cache_hit` correctly detect a miss and re-fetch; `yfinance.Ticker.history(start=...)` clips to each ticker's actual first bar, verified directly against this repo's venv to produce identical results to `period="max"`.
- **Files modified:** `trader/backtest/backfill_universe.py`
- **Verification:** Re-ran the backfill script; all 18 stock symbols now show full history matching 03-RESEARCH.md's verified row/date figures exactly (AAPL 11,495 rows to 1980-12-12, NVDA 6,918 rows to 1999-01-22, XOM/DIS 16,248 rows to 1962-01-02, etc.). `trader/data/api.py` itself was NOT modified, per the plan's "unchanged, consume only" interface note.
- **Committed in:** `8c5937f` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary for the plan's own acceptance criteria (history depth back to each regime's earliest tune_start). No scope creep -- `api.py` untouched, fix confined to the new `backfill_universe.py` module.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required. The live backfill used existing yfinance/ccxt/CoinGecko paths already configured in Phase 1.

## Next Phase Readiness
- `trader/backtest/frozen_config.verify_frozen()` is ready for Plan 03-03's `run_tune_sweep` and Plan 03-05's `run_oos_validation` to call as their first line, before any grid iteration or DB write
- `data/trader.db` now holds full-history cached bars for all 25 universe symbols -- later sweep waves run with zero further network calls
- No blockers for Wave 1's tune-sweep implementation

## Backfill Report (all 25 symbols, nonzero rows)

| Symbol | Rows | Range |
|--------|------|-------|
| AAPL | 11,495 | 1980-12-12 .. 2026-07-24 |
| MSFT | 10,169 | 1986-03-13 .. 2026-07-24 |
| GOOGL | 5,517 | 2004-08-19 .. 2026-07-24 |
| NVDA | 6,918 | 1999-01-22 .. 2026-07-24 |
| AMD | 11,683 | 1980-03-17 .. 2026-07-24 |
| TSLA | 4,042 | 2010-06-29 .. 2026-07-24 |
| AMZN | 7,343 | 1997-05-15 .. 2026-07-24 |
| META | 3,565 | 2012-05-18 .. 2026-07-24 |
| NFLX | 6,081 | 2002-05-23 .. 2026-07-24 |
| CRM | 5,557 | 2004-06-23 .. 2026-07-24 |
| ADBE | 10,063 | 1986-08-13 .. 2026-07-24 |
| COST | 10,088 | 1986-07-09 .. 2026-07-24 |
| JPM | 11,683 | 1980-03-17 .. 2026-07-24 |
| XOM | 16,248 | 1962-01-02 .. 2026-07-24 |
| UNH | 10,522 | 1984-10-17 .. 2026-07-24 |
| WMT | 13,589 | 1972-08-25 .. 2026-07-24 |
| HD | 11,300 | 1981-09-22 .. 2026-07-24 |
| DIS | 16,248 | 1962-01-02 .. 2026-07-24 |
| BTC/USDT | 3,266 | 2017-08-17 .. 2026-07-26 |
| ETH/USDT | 3,266 | 2017-08-17 .. 2026-07-26 |
| DOGE/USDT | 2,579 | 2019-07-05 .. 2026-07-26 |
| SHIB/USDT | 1,904 | 2021-05-10 .. 2026-07-26 |
| PEPE/USDT | 1,179 | 2023-05-05 .. 2026-07-26 |
| BONK/USDT | 955 | 2023-12-15 .. 2026-07-26 |
| WIF/USDT | 874 | 2024-03-05 .. 2026-07-26 |

## Verification

- `python -m pytest tests/test_regime_config.py tests/test_exit_grid.py tests/test_frozen_config.py -q` -> 19 passed
- `python -m trader.backtest.backfill_universe` -> exits 0, all 25 symbols nonzero rows
- Full suite: `python -m pytest -q` -> **183 passed** in 48.08s

## Self-Check: PASSED

- FOUND: trader/backtest/universe.py
- FOUND: trader/backtest/regimes.py
- FOUND: trader/backtest/exit_grid.py
- FOUND: trader/backtest/frozen_config.py
- FOUND: trader/backtest/backfill_universe.py
- FOUND: tests/test_regime_config.py
- FOUND: tests/test_exit_grid.py
- FOUND: tests/test_frozen_config.py
- FOUND commit a619070, 074c129, 09e759d, 0f5586f, 8c5937f in git log

---
*Phase: 03-strategy-lab*
*Completed: 2026-07-26*
