---
phase: 03-strategy-lab
verified: 2026-07-26T23:15:00Z
status: passed
score: 10/10 must-haves verified (build + outcome, v1+v2 combined)
re_verification:
  previous_status: human_needed
  previous_score: "8/8 build truths verified; 0/1 outcome criteria met (owner iteration decision required)"
  gaps_closed:
    - "2-3 OOS-profitable configs (ROADMAP Success Criterion 1) — v2 iteration produced 5 real OOS survivors, exceeding the 2-3 floor"
    - "Owner iteration decision — owner reviewed v1's honest 0-survivor result and approved the pre-registered v2 iteration (03-CONTEXT.md D-13...D-16), which has since been executed and verified"
  gaps_remaining: []
  regressions: []
---

# Phase 3: Strategy Lab Verification Report

**Phase Goal:** Find configs worth paper trading; kill the rest cheaply.
**Verified:** 2026-07-26T23:15:00Z
**Status:** passed
**Re-verification:** Yes — after v2 iteration (v1 was `human_needed`, now closed by owner-approved, pre-registered v2 cycle)

## Goal Achievement

Phase 3 ran two honest cycles. v1 (Plans 03-01..03-06) built the full harness
correctly and produced a genuine zero-survivor result — a valid, cheap kill,
not a defect. The owner reviewed that result and pre-registered a v2 iteration
(03-CONTEXT.md D-13...D-16) **before any v2 result existed**: wider OOS windows
(>=12 months) to fix an arithmetic mismatch between v1's 4-6 month windows and
the 15-trade OOS floor, and entry-gate strictness as a new swept dimension.
Plans 03-07/03-08 built and ran v2 for real. This verification re-examines the
whole chain end-to-end: build integrity, freeze-before-results chronology, the
real sweep/OOS numbers against the database and JSON artifacts, survivor trade
authenticity, kill-condition correctness, v1 artifact immutability, and the
full test suite.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | v1 build (agents, frozen config, sweep engine, OOS discipline, reports, kill gate) is complete and honest | VERIFIED (unchanged from prior verification) | `git diff` between v1's completion commit (`54f191f`) and HEAD across all v1 core files (momentum.py, breakout.py, regimes.py, frozen_config.py, sweep.py, universe.py, exit_grid.py, run_tune_sweep_all.py, run_oos_validation_all.py, sweep_report.py, write_kill_conditions.py) returns **0 lines** — byte-identical. v1's own hash gate (`frozen_config.verify_frozen()`) still passes against current disk state. |
| 2 | v2's regime windows and entry-variant registry were frozen (hash-locked) BEFORE any v2 result existed | VERIFIED | File mtimes, strictly increasing: `regimes_v2.py` 21:41:06 -> `momentum_v2.py` 21:44:14 -> `breakout_v2.py` 21:44:30 -> `frozen_config_v2.py` (freeze point) 21:46:00 -> `sweep_v2.py` (engine, consumes the freeze) 21:53:06 -> drivers 21:59-22:00 -> `tune_top5_v2.json` (results) 22:45:04 -> `oos_results_v2.json` 22:53:01 -> `KILL-CONDITIONS.md` 22:53:16. Commit timestamps corroborate the same order (`944563d`/`485a7b7`/`24be88f` all in the 21:41-21:46 window, before `639e69e`/`07649a8` at 21:54/22:00). No frozen file's mtime or commit falls after any result file's. |
| 3 | v2's frozen hash is still valid (no post-hoc loosening of windows/variants) | VERIFIED | Independently recomputed `frozen_config_v2.compute_hash_v2()` in this session — matches hard-coded `FROZEN_HASH_V2` exactly (`0fba0822...556089f`). `verify_frozen_v2()` raises nothing against current disk state. |
| 4 | The real v2 sweep executed the full pre-registered grid — exactly 10,800 tune-sweep runs | VERIFIED | Direct sqlite query against `data/trader.db`: `COUNT(*)` of `backtest_runs` rows with `sweep_id="v2", split="tune"` = **10,800** (exact match to D-14's pre-registered estimate and the SUMMARY's claim). |
| 5 | 25 tune candidates advanced to OOS; every OOS verdict is real, not narrated | VERIFIED | `reports/backtests/tune_top5_v2.json` has 25 entries; `reports/backtests/oos_results_v2.json` has 25 entries; DB confirms 25 rows with `sweep_id="v2", split="oos"`. Verdict counts: **5 survivor / 8 killed / 12 insufficient_sample** — matches the SUMMARY and the orchestrator's claim exactly. |
| 6 | Survivors genuinely cleared the pre-registered floors (>=15 OOS trades, profitable after costs) | VERIFIED | All 5 survivors: `momentum_stock/stock/choppy_v2/loose`, OOS profit_factor 2.348-20.434, trade_count 32-85 (all >=15). `determine_survivor()` (imported unchanged from v1's `sweep.py`, D-15) requires `trade_count >= 15` and `profit_factor > 1.0` post-fee/slippage. Spot-checked 3 of 5 survivors' `oos_run_id`s (14552, 14554, 14556) directly in `backtest_trades`: real trade rows (32/85/85, matching JSON exactly), real symbols (NFLX, NVDA, JPM, AMD, AMZN, META), real entry/exit dates entirely inside the choppy_v2 OOS window (2016-08-08 to 2017-12-29, safely after `tune_end=2016-06-30`, no leakage), real non-zero fees, mixed win/loss outcomes (not a fabricated all-win pattern). |
| 7 | KILL-CONDITIONS.md carries concrete numeric triggers per survivor, committed | VERIFIED | Regenerated file has 5 `##` entries (one per survivor), each with PF floor (0.9, shared v1 constant), a per-survivor max-drawdown kill level, and consecutive-loss count (8). Spot-checked survivor 1's drawdown trigger: `1.5 * -0.00638508 = -0.0096`, matches the file's `-0.0096` exactly — computed from real OOS metrics, not hand-entered. Committed in `35b42ee`. |
| 8 | v1 artifacts remain byte-unmodified after the v2 cycle | VERIFIED | `git diff 54f191f HEAD` on all v1 core source files = 0 lines. `reports/backtests/tune_top5.json` (mtime 20:17) and `oos_results.json` (mtime 20:31) both predate the v2 session start (21:41) by over an hour; `2026-07-26-survivors.md` mtime 20:44, also predates. v2 writes only to `-v2`-suffixed filenames or run_id-disambiguated report files, plus the one file (KILL-CONDITIONS.md) D-16 explicitly designates for overwrite. |
| 9 | Full test suite is green | VERIFIED | `pytest tests/ -q` -> **347 passed**, 0 failed (matches the expected count exactly; SUMMARY's documented 346/347-with-1-known-failure was resolved by a subsequent, legitimate rescope of `test_kill_conditions.py`'s hardcoded v1-only cross-check to check the latest OOS cycle per D-16 — commit `578dbf3` — not a floor/threshold edit). |
| 10 | 2-3 strategy + exit-profile configs are profitable OOS after fees/slippage (ROADMAP Success Criterion 1) | VERIFIED (exceeded) | 5 real OOS survivors exceed the 2-3 floor. This is the gap that made the prior verification `human_needed`; it is now closed by the owner-approved, pre-registered v2 iteration. |

**Score:** 10/10 truths verified.

### Anti-Tampering / Honest-Outcome Check (v1 -> v2 chain scrutiny)

- **No results-then-loosen pattern found.** v2's floors (30-trade tune, 15-trade OOS), fee/slippage models, and the exit grid itself are imported unchanged from v1 (`sweep.select_top5`, `sweep.determine_survivor` — identity-checked in `tests/test_sweep_engine_v2.py`), never redefined for v2. D-15 explicitly pre-registers this non-negotiable.
- **v2's diagnosis was written before v2 ran.** D-13/D-14 (03-CONTEXT.md) diagnose v1's root cause (window/floor arithmetic mismatch, breakout's single fixed gate) and prescribe the fix, dated in the same context file that records v1's actual 0-survivor outcome — the fix targets a structural gap, not a result.
- **One post-hoc test edit found and evaluated:** commit `578dbf3` (after v2's KILL-CONDITIONS.md was already regenerated) changed `test_kill_conditions.py`'s hardcoded v1-only cross-check to check whichever OOS results file is "latest" (v2's if present, else v1's). This is a mechanical fix to a test that hardcoded a file path assumption invalidated by D-16's designed KILL-CONDITIONS.md supersession — it does not touch any threshold, floor, fee model, or verdict logic, and was flagged as a known, expected consequence in 03-08-SUMMARY.md before being fixed. Not a criteria-loosening edit.
- **v1's own hash gate still holds** (`frozen_config.verify_frozen()` passes) and v2's hash gate holds (`frozen_config_v2.verify_frozen_v2()` passes) — no gate was disabled or bypassed to reach the 5-survivor outcome.

**Conclusion: the v2 iteration is a genuine, pre-registered, honest re-run — not a post-hoc adjustment to manufacture survivors.**

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `trader/backtest/regimes_v2.py` | 6 frozen v2 regime windows, OOS >= 12mo | VERIFIED | Hash-locked, confirmed unmodified since commit |
| `trader/backtest/strategies/momentum_v2.py` / `breakout_v2.py` | 3 entry variants each | VERIFIED | "loose" variant produced all 5 real survivors; hash-locked |
| `trader/backtest/frozen_config_v2.py` | v2 hash gate | VERIFIED | Recomputed hash matches `FROZEN_HASH_V2`; `verify_frozen_v2()` passes |
| `trader/backtest/sweep_v2.py` | Variant-aware sweep/OOS engine | VERIFIED | Reuses `_slice_bars`/`select_top5`/`determine_survivor` from v1 unchanged |
| `trader/backtest/run_tune_sweep_all_v2.py` / `run_oos_validation_all_v2.py` | Real v2 drivers | VERIFIED | Drove the real 10,800-row sweep + 25-row OOS run (DB-confirmed) |
| `trader/backtest/write_kill_conditions_v2.py` | v2 kill-condition gate | VERIFIED | Produced the real, committed, regenerated `KILL-CONDITIONS.md` |
| `reports/backtests/tune_top5_v2.json` | 25 real candidates | VERIFIED (on disk, gitignored per D-12) | 25 entries, matches DB |
| `reports/backtests/oos_results_v2.json` | 25 real verdicts | VERIFIED (on disk, gitignored per D-12) | 5 survivor / 8 killed / 12 insufficient_sample, matches DB and ledger |
| `.planning/phases/03-strategy-lab/KILL-CONDITIONS.md` | 5 concrete numeric-trigger entries | VERIFIED | Regenerated, committed (`35b42ee`), values cross-checked against real OOS metrics |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `run_tune_sweep_all_v2.py` | `sweep_v2.run_tune_sweep_v2` | direct call | WIRED | Real 10,800-row DB result confirms execution |
| `sweep_v2.run_tune_sweep_v2`/`run_oos_validation_v2` | `frozen_config_v2.verify_frozen_v2()` | first statement | WIRED | Confirmed by source read + passing hash-tamper tests |
| `sweep_v2.py` | `sweep.select_top5` / `sweep.determine_survivor` (v1) | imported, unchanged | WIRED | D-15 compliance confirmed; identity-checked in tests |
| `write_kill_conditions_v2.main()` | `oos_results_v2.json` -> `KILL-CONDITIONS.md` | read + build text + overwrite | WIRED | Real file cross-check; numeric triggers recomputed and matched independently in this verification |
| `oos_results_v2.json` survivors | `backtest_trades` ledger | `oos_run_id` | FLOWING | 3 of 5 survivors' trade rows spot-checked directly; counts, symbols, dates, fees all real |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `tune_top5_v2.json` | `select_top5` output over 10,800 real cells | `run_tune_sweep_v2` over real `data/trader.db` bars | Yes — 10,800 real DB rows confirmed | FLOWING |
| `oos_results_v2.json` | `run_oos_validation_v2` output | Real candidates x real OOS-window bars | Yes — 25 real DB rows, trade counts match ledger exactly | FLOWING |
| `KILL-CONDITIONS.md` | `build_kill_conditions_text(oos_results_v2)` | Real `oos_results_v2.json` (5 survivors) | Yes — drawdown trigger independently recomputed from real OOS metrics and matched | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite passes | `pytest tests/ -q` | 347 passed, 0 failed | PASS |
| v2 frozen hash matches on-disk files | `compute_hash_v2()` vs `FROZEN_HASH_V2` | Identical 64-char sha256 | PASS |
| v1 frozen hash still valid | `compute_hash()` vs `FROZEN_HASH` | Identical, `verify_frozen()` no exception | PASS |
| v2 tune-sweep row count | sqlite `COUNT(*)` filtered `sweep_id=v2,split=tune` | 10,800 | PASS |
| v2 OOS row count / verdict distribution | sqlite + JSON read | 25 rows; 5 survivor / 8 killed / 12 insufficient_sample | PASS |
| Survivor ledger spot-check (3 of 5) | sqlite `backtest_trades` by `oos_run_id` | Real trades, dates within OOS window, non-zero fees, mixed win/loss | PASS |
| v1 core files unmodified since v1 completion | `git diff 54f191f HEAD -- <11 v1 files>` | 0 lines | PASS |
| v1 data artifacts predate v2 session | mtimes: `tune_top5.json` 20:17, `oos_results.json` 20:31, `survivors.md` 20:44 vs v2 start 21:41 | All predate by 50min+ | PASS |
| KILL-CONDITIONS.md drawdown trigger recomputation | `1.5 * -0.00638508` vs file's `-0.0096` | Match | PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` convention exists in this repository. This phase's real acceptance runs (`run_tune_sweep_all_v2`, `run_oos_validation_all_v2`, `write_kill_conditions_v2`) are the phase's own equivalent; their outputs were cross-checked against the live database and ledger above rather than re-executed (re-running would append new rows to the append-only ledger and was excluded per the read-only constraint of this verification).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| STRAT-01 | 03-01 | Momentum agent (RSI+volume surge) as pure function | SATISFIED | Unchanged since prior verification; `git diff` confirms no regression |
| STRAT-02 | 03-01 | Breakout agent (20-day high after vol. contraction) | SATISFIED | Unchanged since prior verification |
| STRAT-03 | 03-02..04, 03-07, 03-08 | Exit-parameter sweep per asset class | SATISFIED | v1's 3,600-run sweep + v2's 10,800-run sweep, both DB-confirmed |
| STRAT-04 | 03-02, 03-04, 03-05, 03-07, 03-08 | Configs tested across >=2 regimes | SATISFIED | v1's 6 regimes + v2's 6 regimes (`regimes_v2.REGIMES_V2`, OOS >= 12mo each) |
| STRAT-05 | 03-02, 03-04, 03-05, 03-07, 03-08 | OOS rule enforced (tune A, validate B) | SATISFIED | v2's `run_oos_validation_v2` reuses v1's `_slice_bars`/verdict logic unchanged; ledger spot-check confirms no leakage |
| STRAT-06 | 03-06, 03-08 | Pre-registered kill condition per surviving config | SATISFIED (now non-vacuous — 5 real survivors) | `KILL-CONDITIONS.md` regenerated with 5 concrete numeric-trigger entries, cross-checked against real OOS metrics |

No orphaned requirements — REQUIREMENTS.md maps only STRAT-01...06 to Phase 3, and all six appear across the eight plans' `requirements` frontmatter fields.

### Anti-Patterns Found

None. Grep for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER|not yet implemented|coming soon` (case-insensitive) across all v2 phase source files (`sweep_v2.py`, `run_tune_sweep_all_v2.py`, `run_oos_validation_all_v2.py`, `sweep_report_v2.py`, `write_kill_conditions_v2.py`, `regimes_v2.py`, `frozen_config_v2.py`, `momentum_v2.py`, `breakout_v2.py`) returned zero true matches (one incidental hit — a SQL parameter variable literally named `placeholders`, unrelated to stub/debt markers).

### Human Verification Required

None. The single item that previously required human judgment (the owner's Phase 3 iteration decision) has been resolved: the owner reviewed v1's honest zero-survivor result and pre-registered the v2 iteration (03-CONTEXT.md D-13...D-16, dated "OWNER-APPROVED 2026-07-26"), which has since executed and produced a verified, non-vacuous result. No further human decision point remains open for this phase.

### Gaps Summary

None. Both v1 and v2 build components are complete, wired, tested, and non-stub.
The v1 -> v2 chronology shows no evidence of criteria being loosened after
results were visible: every frozen file's mtime and commit predates the result
files it gates, both hash gates (v1's and v2's) independently re-verify clean
in this session, and the one post-hoc test edit found is a mechanical file-path
rescope, not a threshold change. The real v2 sweep executed to the exact
pre-registered scale (10,800 runs), produced 25 real candidates with real OOS
verdicts (5 survivor / 8 killed / 12 insufficient_sample), and 3 of the 5
survivors' underlying trades were independently spot-checked directly against
the ledger — real symbols, real dates within the correct OOS window, real fees,
mixed win/loss outcomes. `KILL-CONDITIONS.md` carries 5 concrete, independently
recomputed numeric kill triggers. All three ROADMAP.md Success Criteria for
Phase 3 are now met: (1) 5 OOS-profitable configs exceed the 2-3 floor, (2)
pre-registered kill conditions are committed before Phase 4, and (3) the
honest-outcome discipline (v1's real zero-survivor result, accepted and looped
back rather than fudged) was demonstrably followed. The full 347-test suite is
green. Phase 3's goal — "find configs worth paper trading; kill the rest
cheaply" — is achieved. Ready to proceed to Phase 4.

---

_Verified: 2026-07-26T23:15:00Z_
_Verifier: Claude (gsd-verifier)_
