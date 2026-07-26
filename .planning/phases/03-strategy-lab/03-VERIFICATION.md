---
phase: 03-strategy-lab
verified: 2026-07-26T21:30:00Z
status: human_needed
score: 8/8 must-haves verified (build); 0/1 outcome criteria met (owner iteration decision required)
human_verification:
  - test: "Owner reviews the honest 'nothing survived' result and decides how Phase 3 iterates (wider OOS windows, longer-history universe, revisit the 15-trade OOS floor vs 4-6 month OOS windows, or additional strategies/regimes) before the sweep is re-run"
    expected: "Owner either accepts the cheap-kill result and directs a specific Phase 3 revision, or explicitly overrides to advance despite zero OOS survivors (would contradict ROADMAP.md's own success criterion 1 and standing rule 5, 'it'll probably be fine = it goes back a phase')"
    why_human: "This is the phase's own explicitly human decision point (03-CONTEXT.md, 03-VALIDATION.md Manual-Only Verifications: '\"Nothing survived\" branch ... Human decision to loop back to Phase 3 rather than advance'). No code check can substitute for the owner's judgment on which direction Phase 3 iterates."
---

# Phase 3: Strategy Lab Verification Report

**Phase Goal:** Find configs worth paper trading; kill the rest cheaply.
**Verified:** 2026-07-26T21:30:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

This phase has two independent things to verify: (1) whether the BUILD (agents,
frozen config, sweep engine, OOS discipline, reports, kill gate) is complete,
honest, and unmodified after results were visible, and (2) whether the
phase's OUTCOME (2-3 OOS-profitable configs) was achieved. The build passes
in full. The outcome did not happen — and per the phase's own explicit rules,
that is a valid, cheap result, not a build defect. The phase cannot close and
cannot advance to Phase 4 without an owner decision, which is why status is
`human_needed` rather than `passed`.

### Observable Truths (BUILD — must all be true for an honest kill decision)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Momentum agent (RSI+volume surge) implemented as pure function over bars (STRAT-01) | VERIFIED | `trader/backtest/strategies/momentum.py` (97 lines): RSI(14)>=60 AND volume>2x 20-day baseline AND close>prior 20-day high, baseline/high windows excl. today's own bar. 7 fixture tests in `tests/test_strategy_momentum.py`, all passing. |
| 2 | Breakout agent (20-day high after volatility contraction) implemented (STRAT-02) | VERIFIED | `trader/backtest/strategies/breakout.py` (90 lines): NR7 + 20-day-high break + 1.5x volume confirm, no-retest documented as deliberate scope. 7 fixture tests in `tests/test_strategy_breakout.py`, all passing. |
| 3 | Exit-parameter sweep per asset class implemented and frozen before results (STRAT-03) | VERIFIED | `trader/backtest/exit_grid.py` yields 270/270/360 cells (stock/crypto_major_legacy_meme/new_memecoin), confirmed by direct execution. `frozen_config.py` hard-codes `FROZEN_HASH`; `compute_hash()` recomputed independently in this verification matches `FROZEN_HASH` exactly (both 64-char sha256 hex) and `verify_frozen()` does not raise against the current on-disk files. |
| 4 | Configs tested across at least two regimes per asset class (STRAT-04) | VERIFIED | `regimes.py` REGIMES: stock (trending, choppy), crypto_major_legacy_meme (trending, bear), new_memecoin (mania, correction) — 6 regimes, 2 per bucket, confirmed by direct execution; every regime's `tune_end < oos_start`. |
| 5 | Out-of-sample rule enforced — tune on A, validate on B never seen in tuning (STRAT-05) | VERIFIED | `sweep.py`'s `run_tune_sweep` slices bars to `[tune_start, tune_end]`; `run_oos_validation` independently slices to `[oos_start, oos_end]` via the same `_slice_bars` helper. `determine_survivor` enforces a 15-trade OOS floor before consulting profit_factor (proven insufficient_sample even at profit_factor=inf on thin samples, `tests/test_oos_validation.py`). DB query confirms 3600 tune rows + 30 oos rows (15 candidates x 2 reproducibility runs) tagged with `split=tune`/`split=oos` respectively. |
| 6 | Pre-registered kill condition written for every surviving config before Phase 4 (STRAT-06) | VERIFIED (vacuously — 0 survivors) | `write_kill_conditions.py`'s `build_kill_conditions_text()` writes one `## ` header + 3 numeric triggers per survivor, or the exact nothing-survived sentence when zero survivors. `tests/test_kill_conditions.py::test_real_kill_conditions_file_matches_real_oos_results_survivor_list` cross-checks the real committed `KILL-CONDITIONS.md` 1:1 against real `oos_results.json` — passes. |
| 7 | Frozen-before-results discipline (standing rule 1) enforced in code, not convention, at every gate | VERIFIED | `frozen_config.verify_frozen()` is called as the literal first statement in `run_tune_sweep` (sweep.py:121), `run_oos_validation` (sweep.py:235), and `write_kill_conditions.main()` (write_kill_conditions.py:135) — three independent call sites, confirmed by direct source read. Hash-tamper tests for all three exist and pass (`test_sweep_engine.py`, `test_oos_validation.py`, `test_kill_conditions.py`). |
| 8 | Real sweep executed fully (not a fixture-only claim) | VERIFIED | Direct sqlite query against `data/trader.db`: exactly 3600 rows tagged `sweep_id=2026-07-26-strategy-lab-v1, split=tune` across all 12 (strategy x bucket x regime) combos — matches the exact expected count (2 strategies x 3 buckets x 2 regimes x cell-counts). `reports/backtests/tune_top5.json` (15 candidates) and `oos_results.json` (15 verdicts) independently verified against the DB: every candidate's trade_count clears its respective floor. |

**Score:** 8/8 build truths verified.

### Observable Truths (OUTCOME — the phase's actual success gate)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 9 | 2-3 strategy + exit-profile configs are profitable out-of-sample after fees/slippage (ROADMAP.md Success Criterion 1) | NOT MET | `oos_results.json`: 15/15 candidates verdict `insufficient_sample` (0 survivors, 0 killed). Confirmed by direct file read and DB cross-check. This is the honest, reproducible output of a real run against real cached market data — not a build gap. |
| 10 | "If nothing survives, that result is accepted and work returns to Phase 3 — not forward" (ROADMAP.md Success Criterion 3) | MET (as a reporting truth) — but requires owner action | `KILL-CONDITIONS.md` and `reports/backtests/*-survivors.md` both carry the honest nothing-survived sentence. The report is accepted and honest. Whether work **actually returns to Phase 3** with a specific revision is an owner decision this verification cannot make — hence `human_needed`. |

### Anti-Tampering Check (scrutiny requested by orchestrator)

Checked whether frozen thresholds, windows, or floors were edited after results became visible:

- **Hash match:** Independently recomputed `frozen_config.compute_hash()` in this verification session; it matches the hard-coded `FROZEN_HASH` exactly. The three frozen files (`universe.py`, `regimes.py`, `exit_grid.py`) are byte-identical to what the hash was computed against.
- **File mtime ordering:** `universe.py` (19:39:25) and `regimes.py` (19:39:39) and `exit_grid.py` (19:41:03) were all last modified *before* `frozen_config.py` (19:41:40, the hash freeze point), which was in turn modified *before* `tune_top5.json` was produced (20:17:07), which was *before* `oos_results.json` (20:31:33), which was *before* `KILL-CONDITIONS.md` (20:44:53). This chronology is consistent with "freeze config, then run sweep, then view results, then report" — no evidence of a frozen file being touched after results existed.
- **Floor values:** The 30-trade tune floor (`select_top5`, sweep.py:167) and 15-trade OOS floor (`determine_survivor`, sweep.py:294) are hard-coded defaults in the same commit history as the engine itself (Plans 03-03/03-05), not post-hoc edits made after the 0-survivor result was seen — both floors are directly unit-tested against synthetic fixtures independent of the real run's outcome.
- **No loosening found:** No grep hits for edited thresholds, no diff between `params_json` provenance and the frozen grid definitions, no divergent `FROZEN_HASH` value anywhere in the codebase.

**Conclusion: no evidence of criteria-editing after results were visible. The nothing-survived outcome is honest.**

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `trader/backtest/strategies/momentum.py` | STRAT-01 pure function | VERIFIED | 97 lines, real RSI/volume/breakout logic, no stubs |
| `trader/backtest/strategies/breakout.py` | STRAT-02 pure function | VERIFIED | 90 lines, real NR7/breakout/volume logic, no stubs |
| `trader/backtest/universe.py` | Frozen 25-symbol universe | VERIFIED | 18/4/3 split confirmed by direct execution |
| `trader/backtest/regimes.py` | 6 frozen regime windows | VERIFIED | tune_end < oos_start for all 6, confirmed |
| `trader/backtest/exit_grid.py` | 270/270/360-cell grid | VERIFIED | Exact cell counts confirmed by direct execution |
| `trader/backtest/frozen_config.py` | Hash gate | VERIFIED | Hash recomputed and matches; verify_frozen() passes |
| `trader/backtest/sweep.py` | Sweep + OOS engine | VERIFIED | run_tune_sweep, select_top5, run_oos_validation, determine_survivor all present, gated, provenance-tagged |
| `trader/backtest/run_tune_sweep_all.py` | Real tune-sweep driver | VERIFIED | Drove the real 3600-row sweep (DB-confirmed) |
| `trader/backtest/run_oos_validation_all.py` | Real OOS driver | VERIFIED | Drove the real 30-row (15x2) OOS run (DB-confirmed) |
| `trader/backtest/sweep_report.py` | Per-config reports | VERIFIED | 196 lines; real reports on disk (gitignored per D-12, confirmed present) |
| `trader/backtest/write_kill_conditions.py` | Kill-condition gate | VERIFIED | Defence-in-depth verify_frozen() first; produced the real committed KILL-CONDITIONS.md |
| `.planning/phases/03-strategy-lab/KILL-CONDITIONS.md` | Honest kill-condition record | VERIFIED | Exact nothing-survived sentence, cross-check test passes |
| `reports/backtests/tune_top5.json` | Real 15-candidate tune output | VERIFIED (on disk, gitignored per D-12) | 15 candidates, all clear 30-trade floor |
| `reports/backtests/oos_results.json` | Real 15-verdict OOS output | VERIFIED (on disk, gitignored per D-12) | 15 verdicts, all insufficient_sample |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `run_tune_sweep_all.py` | `sweep.run_tune_sweep` | direct call | WIRED | Real 3600-row DB result confirms execution |
| `run_tune_sweep` | `frozen_config.verify_frozen()` | first statement | WIRED | sweep.py:121, confirmed by source read |
| `run_oos_validation_all.py` | `sweep.run_oos_validation` | direct call | WIRED | Real 30-row DB result confirms execution |
| `run_oos_validation` | `frozen_config.verify_frozen()` | first statement | WIRED | sweep.py:235, confirmed by source read |
| `write_kill_conditions.main()` | `frozen_config.verify_frozen()` | first statement | WIRED | write_kill_conditions.py:135, confirmed by source read |
| `write_kill_conditions.main()` | `oos_results.json` -> `KILL-CONDITIONS.md` | read + build_kill_conditions_text + write | WIRED | Real file cross-check test passes; committed file matches real oos_results.json 1:1 |
| `sweep.run_tune_sweep`/`run_oos_validation` | `runner.run_backtest` (Phase 2 engine) | unmodified call | WIRED | No bypass path found in sweep.py; both functions call `runner.run_backtest` directly with real fees/slippage config |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `tune_top5.json` | `select_top5` output | `run_tune_sweep` over real `data/trader.db` bars | Yes — 3600 real DB rows confirmed | FLOWING |
| `oos_results.json` | `run_oos_validation` output | Real candidates x real OOS-window bars | Yes — 30 real DB rows confirmed, trade counts match DB | FLOWING |
| `KILL-CONDITIONS.md` | `build_kill_conditions_text(oos_results)` | Real `oos_results.json` (0 survivors) | Yes — content cross-checked 1:1 against real file | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite passes | `.venv/Scripts/python.exe -m pytest tests/ -q` | 217 passed in 64.44s | PASS (matches expected 217, ~75s budget) |
| Frozen hash matches on-disk files | `compute_hash()` vs `FROZEN_HASH` | Identical 64-char sha256 | PASS |
| `verify_frozen()` does not raise against current files | direct call | No exception | PASS |
| Tune-sweep row count matches expected total | sqlite `COUNT(*)` filtered by sweep_id/split=tune | 3600 | PASS |
| OOS row count / verdict distribution | sqlite + JSON read | 30 rows (15 candidates x 2 runs); all 15 unique candidates `insufficient_sample` | PASS |
| Exit-grid cell counts | direct `exit_profile_grid()` call per bucket | 270/270/360 | PASS |
| Regime tune/OOS ordering | direct `REGIMES` iteration | tune_end < oos_start for all 6 | PASS |
| Universe symbol counts | direct `UNIVERSE_BY_BUCKET` read | 18/4/3 = 25 | PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` convention exists in this repository; no PLAN/SUMMARY declares probe-based verification. This phase's real acceptance runs (`run_tune_sweep_all`, `run_oos_validation_all`, `write_kill_conditions`) are the phase's own equivalent, and their outputs were independently cross-checked against the live database above rather than re-executed (re-running would append new rows to the append-only ledger and was excluded per the read-only constraint of this verification).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| STRAT-01 | 03-01 | Momentum agent (RSI+volume surge) as pure function | SATISFIED | momentum.py, 7 passing tests |
| STRAT-02 | 03-01 | Breakout agent (20-day high after vol. contraction) | SATISFIED | breakout.py, 7 passing tests |
| STRAT-03 | 03-02, 03-03, 03-04 | Exit-parameter sweep per asset class | SATISFIED | exit_grid.py + sweep.py + real 3600-row run |
| STRAT-04 | 03-02, 03-04, 03-05 | Configs tested across >=2 regimes | SATISFIED | regimes.py (6 regimes, 2/bucket), real sweep spans all |
| STRAT-05 | 03-02, 03-04, 03-05 | OOS rule enforced (tune A, validate B) | SATISFIED | run_oos_validation + determine_survivor, real 15-candidate run |
| STRAT-06 | 03-06 | Pre-registered kill condition per surviving config | SATISFIED (vacuous — 0 survivors, explicitly stated) | KILL-CONDITIONS.md, cross-check test |

No orphaned requirements — REQUIREMENTS.md maps only STRAT-01…06 to Phase 3, and all six appear across the six plans' `requirements` frontmatter fields.

### Anti-Patterns Found

None. Grep for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER|not yet implemented|not available|coming soon` (case-insensitive) across all phase source files (`momentum.py`, `breakout.py`, `universe.py`, `regimes.py`, `exit_grid.py`, `frozen_config.py`, `sweep.py`, `run_tune_sweep_all.py`, `run_oos_validation_all.py`, `sweep_report.py`, `write_kill_conditions.py`) returned zero matches.

### Human Verification Required

### 1. Owner's Phase 3 iteration decision

**Test:** Review the sweep's honest result — 3,600 tune-sweep cells, 15 momentum candidates cleared the 30-trade tune floor (breakout cleared zero), all 15 came back `insufficient_sample` against their 15-trade OOS floor (0 survivors, 0 killed) — and decide how Phase 3 proceeds.

**Expected:** One of: (a) accept the cheap-kill result and specify a concrete revision (e.g., widen OOS windows beyond 4-6 months, extend the universe's cached history, reconsider the 15-trade OOS floor's interaction with short OOS windows, add strategies/regimes) and loop back within Phase 3; or (b) explicitly override via VERIFICATION.md frontmatter if there is a reason to advance despite zero OOS survivors (would need to be reconciled against ROADMAP.md's Success Criterion 1 and standing rule 5).

**Why human:** This is the exact decision point the phase document, ROADMAP.md, and 03-CONTEXT.md all reserve for the owner ("If NOTHING survives — that's a valid, cheap result. Go back to Phase 3, not forward"). No grep or test can make this call; it is a strategy/business judgment, not a code-correctness question.

### Gaps Summary

No build gaps found. All STRAT-01…06 requirements are satisfied by real, wired, tested, non-stub code. The frozen-before-results discipline is enforced at three independent gate call sites and verified un-tampered via independent hash recomputation and file-mtime chronology. The full 217-test suite passes. The real sweep executed to completion with exact expected row counts (3600 tune rows, 12 combos, 15 OOS candidates, 30 OOS rows across two reproducibility runs) confirmed directly against `data/trader.db`, not merely SUMMARY.md narration.

The phase's outcome — 2-3 OOS-profitable configs — did not occur. Per ROADMAP.md's own Success Criterion 3 and the phase document's explicit framing, this is a valid, cheap result rather than a defect, but it means the phase cannot close on Success Criterion 1 and cannot advance to Phase 4. Status is `human_needed`: the owner must make the iteration call described above.

---

_Verified: 2026-07-26T21:30:00Z_
_Verifier: Claude (gsd-verifier)_
