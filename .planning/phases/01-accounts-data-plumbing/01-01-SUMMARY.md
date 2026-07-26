---
phase: 01-accounts-data-plumbing
plan: 01
subsystem: database
tags: [sqlite, migrations, ccxt, pandas, schema-versioning, cache-first]

# Dependency graph
requires:
  - phase: 00-ground-truth
    provides: trader/ground_truth/db.py's WAL/busy_timeout connection pattern and existing snapshots/poll_runs/schema_version DDL
provides:
  - trader/data/db.py contract (get_connection, apply_migrations, upsert_instrument, get_instrument, read_bars_cache, write_bars_cache)
  - migrations/ mechanism (ordered *.sql files, schema_version-tracked) for all future schema changes
  - instruments and bars tables with the (venue, symbol, timeframe, ts) uniqueness contract
  - ccxt and pandas pinned and installed in the project .venv
affects: [01-02, 01-04, 01-05, 01-06, "any later Phase 1 plan that fetches or caches a bar"]

# Tech tracking
tech-stack:
  added: ["ccxt==4.5.68", "pandas==3.0.5 (pinned explicitly; was already a transitive yfinance dependency)"]
  patterns: ["ordered SQL migration files tracked in schema_version, replacing ad-hoc ensure_schema edits (D-09)", "cache-first bars table, INSERT OR IGNORE keyed on (venue, symbol, timeframe, ts)"]

key-files:
  created:
    - migrations/0001_ground_truth.sql
    - migrations/0002_instruments_bars.sql
    - trader/data/__init__.py
    - trader/data/db.py
    - tests/test_data_db.py
  modified:
    - requirements.txt
    - .env.example
    - .gitignore

key-decisions:
  - "migrations/0001_ground_truth.sql retrofits Phase 0's DDL verbatim (idempotent CREATE TABLE IF NOT EXISTS), never altering Phase 0's table shape"
  - "apply_migrations owns recording schema_version entries; migration .sql files themselves never write to schema_version directly"
  - "trader.data.db.get_connection default migrations_dir is the cwd-relative 'migrations/' folder, matching trader/ground_truth/db.py's existing cwd-relative data/trader.db convention"

patterns-established:
  - "Pattern: ordered *.sql migration files under migrations/, version parsed from the filename's leading 4 digits, applied once and recorded in schema_version"
  - "Pattern: cache-first read/write helpers (read_bars_cache/write_bars_cache) using only parameterized (?) SQL placeholders, never f-string SQL"

requirements-completed: [ACCT-05, ACCT-06]

# Metrics
duration: ~18min
completed: 2026-07-26
---

# Phase 1 Plan 01: Data Plumbing Foundation Summary

**Migration-runner + instruments/bars SQLite schema with cache-first read/write helpers, ccxt/pandas pinned, Phase 1 secrets documented in .env.example**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-07-26T13:26:38+12:00
- **Completed:** 2026-07-26T13:31:55+12:00
- **Tasks:** 3
- **Files modified:** 8 (3 modified, 5 created)

## Accomplishments
- `ccxt==4.5.68` and `pandas==3.0.5` pinned in requirements.txt and installed into the project `.venv`
- `.env.example` documents all five new Phase 1 secret names (`KRAKEN_API_KEY`, `KRAKEN_API_SECRET`, `IBKR_ACCOUNT_ID`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) with no values
- `migrations/` mechanism introduced per D-09: `0001_ground_truth.sql` retrofits Phase 0's DDL, `0002_instruments_bars.sql` adds `instruments` and `bars`
- `trader/data/db.py` implements the full contract: `get_connection`, `apply_migrations`, `upsert_instrument`, `get_instrument`, `read_bars_cache`, `write_bars_cache`
- 5 new tests (`tests/test_data_db.py`) written RED-first, all GREEN; full suite green at 29 passed (24 pre-existing + 5 new), no regression

## Task Commits

Each task was committed atomically:

1. **Task 1: Pin new dependencies, document new secret names, self-heal .gitignore** - `94ec62e` (chore)
2. **Task 2: Write failing tests for the migration runner and instruments/bars schema (RED)** - `95e362c` (test)
3. **Task 3: Implement migrations and trader.data.db cache/instrument helpers (GREEN)** - `73bc5c7` (feat) — includes the `.gitignore` blocking-bug fix (Rule 3)

**Plan metadata:** (this commit, filed after this Summary)

## Files Created/Modified
- `requirements.txt` - added `ccxt==4.5.68`, `pandas==3.0.5`
- `.env.example` - added five empty Phase 1 secret-name lines
- `.gitignore` - anchored `data/` to `/data/` (Rule 3 fix, see Deviations)
- `migrations/0001_ground_truth.sql` - verbatim idempotent retrofit of Phase 0's snapshots/poll_runs/schema_version DDL
- `migrations/0002_instruments_bars.sql` - `instruments` (asset_class CHECK constraint, PK symbol+venue) and `bars` (UNIQUE venue/symbol/timeframe/ts) tables
- `trader/data/__init__.py` - empty package marker
- `trader/data/db.py` - migration runner + instrument/bars cache helpers (184 lines)
- `tests/test_data_db.py` - 5 tests against the new contract, local `data_conn` fixture (conftest.py untouched)

## Decisions Made
- `apply_migrations` owns writing to `schema_version`; the `.sql` migration files contain only `CREATE TABLE IF NOT EXISTS` DDL, never a self-inserted version row, keeping version bookkeeping in exactly one place.
- Followed the plan's exact instruments/bars DDL from 01-RESEARCH.md's Schema Design section with no alterations.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] .gitignore's bare `data/` pattern silently excluded the new `trader/data/` source package**
- **Found during:** Task 3, when staging `trader/data/db.py` for commit
- **Issue:** `.gitignore` had a line reading `data/` (no leading slash), which in gitignore syntax matches any directory named `data` at any depth, not just the repo-root SQLite data directory. This silently blocked `git add trader/data/__init__.py` and `trader/data/db.py`.
- **Fix:** Anchored the pattern to `/data/` so only the repo-root data directory (where `trader.db` lives) is excluded; verified with `git check-ignore -v` that `data/trader.db` is still ignored and `trader/data/*` is no longer matched.
- **Files modified:** `.gitignore`
- **Verification:** `git check-ignore -v trader/data trader/data/db.py data/trader.db` confirmed only `data/trader.db` matches; `git add` on `trader/data/` files succeeded afterward.
- **Committed in:** `73bc5c7` (part of Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary to complete Task 3 as specified; no scope creep, no change to intended `.gitignore` behaviour for the repo-root `data/` directory.

## Issues Encountered
- The acceptance criteria for Task 2 required both zero collection errors on `--collect-only` and every test failing with `ModuleNotFoundError`/`AttributeError` on execution — these are only simultaneously satisfiable if the top-level import doesn't itself abort collection. Resolved by guarding the import (`try/except ImportError: db = None`), which collects all 5 tests cleanly while every test still fails with `AttributeError` referencing the missing `trader.data.db` contract, matching the plan's explicit "not a silent skip or collection error" instruction.

## User Setup Required

None - no external service configuration required. (Kraken/IBKR account provisioning is tracked separately in Plan 01-03 per D-14; no code in this plan depends on it.)

## Next Phase Readiness
- `trader/data/db.py`'s contract is stable and ready for Plan 01-02 (instrument classification/onboarding) and Plans 01-04/01-05/01-06 (stock/crypto fetchers) to build on.
- Migration mechanism in place — future schema changes are new ordered `.sql` files, not `ensure_schema` edits.
- No blockers.

---
*Phase: 01-accounts-data-plumbing*
*Completed: 2026-07-26*

## Self-Check: PASSED

All created files verified present on disk (requirements.txt, .env.example, .gitignore, migrations/0001_ground_truth.sql, migrations/0002_instruments_bars.sql, trader/data/__init__.py, trader/data/db.py, tests/test_data_db.py, this SUMMARY.md). All 3 task commits (94ec62e, 95e362c, 73bc5c7) verified present in git log.
