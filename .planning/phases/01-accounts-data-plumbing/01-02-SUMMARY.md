---
phase: 01-accounts-data-plumbing
plan: 02
subsystem: database
tags: [coingecko, classification, ccxt, sqlite, tdd]

# Dependency graph
requires:
  - phase: 01-accounts-data-plumbing
    provides: "trader/data/db.py's upsert_instrument/get_instrument contract and instruments table (Plan 01-01)"
provides:
  - "trader/data/classify.py contract: classify_crypto_instrument(coingecko_id, api_key) -> str, register_crypto_instrument(conn, symbol, venue, coingecko_id, override=None) -> str"
  - "Live-verified CoinGecko categories heuristic: dogecoin classifies memecoin, bitcoin classifies crypto_major"
  - "D-16 satisfied — classification happens at insert time via a real onboarding caller, not dead code"
affects: ["01-06 (get_daily_bars' crypto fetcher calls register_crypto_instrument for any new crypto symbol)"]

# Tech tracking
tech-stack:
  added: []
  patterns: ["classify-once-at-insert, never-per-bar-fetch (Pattern 4, 01-RESEARCH.md)", "override column bypasses classification entirely, never spending a rate-limited CoinGecko call"]

key-files:
  created:
    - trader/data/classify.py
    - trader/data/classify_smoke.py
    - tests/test_classify.py
  modified: []

key-decisions:
  - "register_crypto_instrument persists via db.upsert_instrument in the same call as classification — no code path classifies without persisting or persists without classifying, except the explicit override path"
  - "classify_crypto_instrument never logs or exposes api_key; only coingecko_id and HTTP status ever appear in any output"

patterns-established:
  - "Pattern: classify-then-persist onboarding functions live alongside their pure classification counterpart in the same module, wired together explicitly rather than left as separately-callable dead code"

requirements-completed: [ACCT-06]

# Metrics
duration: ~10min
completed: 2026-07-26
---

# Phase 1 Plan 02: CoinGecko Classification + Onboarding Summary

**CoinGecko-categories crypto classification (classify_crypto_instrument) wired to a real onboarding caller (register_crypto_instrument) that persists to instruments at insert time, live-verified against dogecoin (memecoin) and bitcoin (crypto_major)**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-07-26T13:37:48+12:00
- **Completed:** 2026-07-26T13:41:51+12:00
- **Tasks:** 5
- **Files modified:** 3 created (classify.py, classify_smoke.py, test_classify.py)

## Accomplishments
- `classify_crypto_instrument(coingecko_id, api_key)` queries CoinGecko's `/coins/{id}` endpoint with the authenticated `x-cg-demo-api-key` header, returns `"memecoin"` when `"Meme"` is in the response's `categories` list, else `"crypto_major"`, defends against a missing `categories` key, and propagates `HTTPError` on a 429 rather than swallowing it
- `register_crypto_instrument(conn, symbol, venue, coingecko_id, override=None)` classifies (unless `override` is given, which skips the CoinGecko call entirely) and persists the result via `db.upsert_instrument` in the same call — `classify_crypto_instrument` now has a real caller, satisfying D-16
- `trader/data/classify_smoke.py` live-verified against the real CoinGecko API: `dogecoin -> memecoin`, `bitcoin -> crypto_major`, exit 0
- 8 new tests in `tests/test_classify.py` (5 classify + 3 register), all green; full suite green at 37 passed (29 pre-existing + 8 new), no regression

## Task Commits

Each task was committed atomically, with an additional correction commit between Task 2 and Task 3 (see Deviations):

1. **Task 1: Write failing tests for CoinGecko classification (RED)** - `420fbb1` (test)
2. **Task 2: Implement CoinGecko classification (GREEN)** - `10f3329` (feat)
   - Correction: `3d43653` (fix) — removed `register_crypto_instrument` added prematurely in this commit, restoring correct RED→GREEN ordering ahead of Task 3
3. **Task 3: Write failing tests for register_crypto_instrument onboarding (RED)** - `5871c0f` (test)
4. **Task 4: Implement register_crypto_instrument — classify-then-persist onboarding (GREEN)** - `fdb93b1` (feat)
5. **Task 5: Live acceptance check against the real CoinGecko API** - `c1dce51` (test)

**Plan metadata:** (this commit, filed after this Summary — STATE.md/ROADMAP.md intentionally not updated per orchestrator instruction for this run)

_Note: TDD tasks produced the expected test → feat pairs for both functions; RED confirmed collection succeeds with zero errors while all new tests fail referencing the not-yet-implemented function, GREEN confirmed all new tests pass with no regression to the pre-existing suite._

## Files Created/Modified
- `trader/data/classify.py` - `classify_crypto_instrument` (pure CoinGecko categories lookup) and `register_crypto_instrument` (classify-then-persist onboarding, delegates to `trader.data.db.upsert_instrument`)
- `trader/data/classify_smoke.py` - live, no-mock entry point confirming dogecoin/bitcoin classification against the real API, mirroring `trader/ground_truth/smoke.py`'s pattern
- `tests/test_classify.py` - 8 tests: 5 for `classify_crypto_instrument` (memecoin/crypto_major from categories, authenticated header, HTTPError propagation on 429, defensive default on missing `categories` key) + 3 for `register_crypto_instrument` (classify-and-persist, override skips classification, idempotency); local `data_conn` fixture mirrors `tests/test_data_db.py`'s pattern, `conftest.py` untouched

## Decisions Made
- `register_crypto_instrument` always persists via `db.upsert_instrument` in the same call as classification (or override assignment) — no code path classifies without persisting, matching the plan's explicit "never left as dead code" requirement (D-16).
- `api_key` is never logged, printed, or included in any exception message — only `coingecko_id` and HTTP status appear in log-worthy output, matching CLAUDE.md's standing rule 3 and the threat model's T-01-06 disposition.

## Deviations from Plan

### Auto-fixed Issues

**1. [Self-correction, no rule category — TDD ordering] Removed register_crypto_instrument implemented prematurely in Task 2's commit**
- **Found during:** Immediately after Task 2's commit, before starting Task 3
- **Issue:** Task 2 (`10f3329`) was drafted with both `classify_crypto_instrument` and `register_crypto_instrument` implemented together, which would have made Task 3's RED tests pass immediately instead of failing with the expected `AttributeError`, violating the plan's explicit "RED → GREEN pairs for both classify_crypto_instrument and register_crypto_instrument" ordering requirement.
- **Fix:** Stripped `register_crypto_instrument` back out of `classify.py` in a dedicated correction commit before writing Task 3's tests, restoring genuine RED for the register function.
- **Files modified:** `trader/data/classify.py`
- **Verification:** Re-ran `tests/test_classify.py` (5 classify tests still green) before proceeding; Task 3's 3 new tests then correctly failed with `AttributeError: module 'trader.data.classify' has no attribute 'register_crypto_instrument'`.
- **Committed in:** `3d43653` (fix)

---

**Total deviations:** 1 self-correction (no auto-fix rule category applies — this was an executor sequencing correction, not a plan gap)
**Impact on plan:** No change to the plan's final code or test contract; the correction commit exists solely to preserve genuine RED→GREEN TDD discipline as explicitly required by the execution instructions. Final `classify.py` matches the plan's specification exactly.

## Issues Encountered
None beyond the self-correction documented above.

## User Setup Required

None - `COINGECKO_API_KEY` was already provisioned in `.env` by Phase 0; no new external service configuration required.

## Next Phase Readiness
- `trader/data/classify.py`'s contract (`classify_crypto_instrument`, `register_crypto_instrument`) is stable and ready for Plan 01-06's `get_daily_bars` crypto fetcher to call `register_crypto_instrument` for any crypto symbol not yet present in `instruments`.
- Live smoke test (`trader/data/classify_smoke.py`) is a repeatable manual re-verification tool if CoinGecko's category taxonomy ever changes.
- No blockers.

---
*Phase: 01-accounts-data-plumbing*
*Completed: 2026-07-26*

## Self-Check: PASSED

All created files verified present on disk (trader/data/classify.py, trader/data/classify_smoke.py, tests/test_classify.py, this SUMMARY.md). All 6 commits (420fbb1, 10f3329, 3d43653, 5871c0f, fdb93b1, c1dce51) verified present in git log.
