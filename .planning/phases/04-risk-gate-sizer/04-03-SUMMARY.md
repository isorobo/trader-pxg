---
phase: 04-risk-gate-sizer
plan: 03
subsystem: risk-sizer
tags: [position-sizing, hypothesis, property-testing, inverse-volatility]
dependency-graph:
  requires: ["trader/risk/config.py (04-01)"]
  provides: ["trader/risk/sizer.py: compute_volatility, size_positions"]
  affects: ["04-05 (D-07 acceptance test depends on this plan's exact clip behavior)"]
tech-stack:
  added: ["hypothesis==6.161.5 (dev dependency)"]
  patterns:
    - "Deterministic select->weight->normalize->cap->re-cap->cash-absorbs-remainder order (04-RESEARCH.md Q3)"
    - "Freed weight from a binding cap always flows to cash, never redistributed (Assumption A6)"
    - "hypothesis @settings(max_examples=50, deadline=None) scoped per-test, no global profile"
key-files:
  created:
    - trader/risk/sizer.py
    - tests/test_position_sizer.py
  modified:
    - requirements.txt
decisions:
  - "compute_volatility uses pandas .pct_change().tail(window).std(ddof=1), matching trader/backtest/metrics.py's sample-stdev convention"
  - "open_positions hypothesis generator constrains any generated open memecoin weight to <= SIZER_MEMECOIN_CAP on its own -- an open position that already violates the cap by itself is not a realistic input, since the sizer never re-sizes existing open positions and could not have produced such a position itself"
metrics:
  duration: "~35 minutes"
  completed: "2026-07-26"
---

# Phase 4 Plan 03: Position Sizer + Hypothesis Cap-Invariant Property Tests Summary

Deterministic position sizer (RISK-02) implementing score x inverse-volatility weighting with a fixed select->weight->normalize->cap->re-cap->cash order, proven correct by both a golden-fixture regression test reproducing 04-RESEARCH.md Q3's worked example and hypothesis property tests over generated inputs.

## What Was Built

`trader/risk/sizer.py` exports two pure functions:

- `compute_volatility(bars, window=SIZER_VOLATILITY_WINDOW_DAYS)` -- sample standard deviation (`ddof=1`) of trailing daily close-to-close returns, matching `trader/backtest/metrics.py`'s existing sample-stdev convention rather than population stdev.
- `size_positions(scored_candidates, equity, open_positions, config=risk_config)` -- the deterministic sizer. Selects the top `SIZER_TOP_N - len(open_positions)` candidates by score, computes `score / volatility` raw weights, normalizes to the remaining budget (`1 - SIZER_CASH_RESERVE - sum(open weights)`), applies the 50% single-position cap, then the 10% memecoin aggregate cap (considering both new candidates and existing open-position memecoin weight together, scaling down only the new candidates), and lets any capital freed by the two caps flow into `cash_weight` rather than back to surviving positions.

`tests/test_position_sizer.py` covers:

- `compute_volatility` against an independently computed `statistics.stdev` reference.
- The golden fixture: candidates A/B/C (scores 0.90/0.70/0.95, vols 0.02/0.04/0.15) reproduce `w_A=0.50` (capped), `w_B~0.2289`, `w_C~0.0827`, `cash~0.1884` to the precision the worked example implies.
- No-redistribution: freed weight from A's cap lands in cash, not B or C.
- Memecoin cap scaling down a new candidate alone to exactly the cap.
- Memecoin cap considering an existing open position's memecoin weight together with a new candidate's, scaling only the new one.
- Open-positions budget generalization: an existing 0.30-weight stock position leaves only 2 of 3 slots and a smaller remaining budget for new candidates; the lowest-scored new candidate is excluded and the open position is never re-sized.
- A hypothesis property test (`@settings(max_examples=50, deadline=None)`) generating 1-3 candidates and 0-2 open positions across `score`/`volatility`/`asset_class`, asserting for every generated input: no position weight exceeds 50%, combined memecoin weight (open + new) never exceeds 10%, `cash_weight` is never negative, and `sum(all weights) + cash_weight == 1.0` within a tight tolerance.

`hypothesis==6.161.5` was installed into the project's `.venv` and pinned in `requirements.txt`, per 04-RESEARCH.md's Package Legitimacy Audit (Approved -- no blocking human-verify checkpoint required).

## Verification

- `python -m pytest tests/test_position_sizer.py -q` -- 7 passed (golden fixture, memecoin-cap variants, open-positions generalization, hypothesis property test).
- `python -m pytest -q` (full suite) -- 318 passed (baseline 311 + 7 new).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed a self-defeating docstring-text assertion from my own draft test**
- **Found during:** Task 1, first test run.
- **Issue:** An initial test asserted the literal string `"redistribute"` never appeared in `sizer.py`'s source, but the module's own docstring legitimately describes the "never redistribute to survivors" design decision using that word -- the assertion was testing prose, not behavior, and always failed regardless of correctness.
- **Fix:** Removed the fragile source-text assertion. The no-redistribution behavior is already proven functionally by the golden-fixture and memecoin-cap tests' exact numeric assertions (capped/freed amounts land in `cash_weight`, not in surviving positions' weights).
- **Files modified:** tests/test_position_sizer.py
- **Commit:** 6e3d38e

**2. [Rule 1 - Bug] Constrained the hypothesis open_positions generator to respect the memecoin cap on its own**
- **Found during:** Task 2, first hypothesis run (found a failing case within the first example).
- **Issue:** The initial `open_positions` strategy could generate a single open memecoin position with weight up to 0.8 -- e.g. 0.5 -- which alone already exceeds `SIZER_MEMECOIN_CAP` (0.10) before any new candidate is considered. The property test's "combined memecoin <= 10%" invariant can only hold for inputs where existing open positions themselves already respect the caps that would have applied when they were originally sized; `size_positions` never re-sizes open positions and could not have produced such an input itself.
- **Fix:** Added a running `memecoin_remaining` budget to the `_open_positions` hypothesis strategy so any generated open memecoin position's weight is bounded to leave the combined open-memecoin total at or below `SIZER_MEMECOIN_CAP`.
- **Files modified:** tests/test_position_sizer.py
- **Commit:** fb562f8

## Known Stubs

None -- both `compute_volatility` and `size_positions` are fully wired, no placeholder returns or hardcoded stand-ins.

## Threat Flags

None -- `sizer.py` is a pure in-process function over caller-supplied data (no network/user input, no new trust boundary); `hypothesis` was already audited and approved in 04-RESEARCH.md's Package Legitimacy Audit.

## Self-Check: PASSED

- `trader/risk/sizer.py` exists.
- `tests/test_position_sizer.py` exists.
- Commit `6e3d38e` found in git log.
- Commit `fb562f8` found in git log.
- `requirements.txt` contains `hypothesis==6.161.5`.
- Full suite: 318 passed.
