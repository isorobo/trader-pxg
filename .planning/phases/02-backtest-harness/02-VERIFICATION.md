---
phase: 02-backtest-harness
verified: 2026-07-26T00:00:00Z
status: passed
score: 7/7 must-haves verified
overrides_applied: 0
---

# Phase 2: Backtest Harness Verification Report

**Phase Goal:** Test any strategy against history without lying to yourself.
**Verified:** 2026-07-26
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth (BACK-0X) | Status | Evidence |
|---|---|---|---|
| 1 | BACK-01: Point-in-time bar iterator — strategy code only ever sees bars ≤ current time | VERIFIED | `trader/backtest/iterator.py` (140 lines): per-symbol two-pointer cursor, `history()` returns a pointer-bounded slice, never a boolean-mask re-filter (`grep "df\[df.index"` → 0 matches). 9 dedicated tests including lookahead/backward-pointer regressions. Wired into `runner.py` (`from trader.backtest.iterator import PointInTimeIterator`). |
| 2 | BACK-02: Per-venue fee model (IBKR commissions, Kraken taker) | VERIFIED | `trader/backtest/config.py` FEE_TABLE (stock: per-share $0.005/$1 min; crypto_major/memecoin: 0.26% taker). `fills.fee_for` branches on `FEE_TABLE[asset_class]["kind"]`, reads values only from config (no re-hard-coded numbers, confirmed by direct read). Kraken maker tier (0.16%) intentionally not modeled — taker-only is a documented, locked pessimistic simplification (D-06), not a gap. |
| 3 | BACK-03: Slippage model scaled by asset class | VERIFIED | `SLIPPAGE_PCT = {"stock": 0.05, "crypto_major": 0.10, "memecoin": 4.0}`; `fills.slippage_pct_for`/`apply_slippage` always bias against the trader (buy fills higher, sell fills lower), proven by 19 tests in `test_backtest_fills.py`. The phase document's "small-cap-runner 1-3%" tier is exposed as `SLIPPAGE_SMALL_CAP_RUNNER=2.0`, explicitly documented as an **unwired Phase 3 hook** — a deliberate, orchestrator-locked scope decision recorded in 02-CONTEXT.md D-08, not an omission. |
| 4 | BACK-04: Exit engine implements EXIT_PROFILES (stop, TP, scale-out, trailing, time stop, eod_flat) | VERIFIED | `trader/backtest/exits.py` `evaluate_exit()` (read directly, lines 149-207): implements D-10's exact order — eod_flat → stop → trailing → scale-out/TP → time_stop. Entry-bar checking, stop-wins-tie, gap-through pricing (reuses `fills.worse_of_fill`), non-lookahead trailing watermark (`_updated_watermark` reads prior watermark/entry price + this bar's close only, never this bar's high) all present and each covered by a distinctly named test (9 tests). |
| 5 | BACK-05: Trade ledger logs every simulated trade with strategy ID, profile, entry/exit, fees, P&L | VERIFIED | `trader/backtest/ledger.py`: `record_run`/`record_trade` write via parameterized `?` SQL only (`grep "f\"INSERT` → 0 matches) into `backtest_runs`/`backtest_trades` (schema confirmed live in `data/trader.db`, exact column match to migration). Reproducibility (D-12) proven by a dedicated test. Wired into `runner.py`. |
| 6 | BACK-06: Metrics module reports profit factor, Sharpe, max drawdown, win rate, avg win/loss, per-strategy attribution | VERIFIED | `trader/backtest/metrics.py` `compute_metrics`/`write_report` matched to two hand-worked golden fixtures (profit factor, Sharpe, max DD, win rate, avg win/loss, fees) plus 5 documented edge cases (zero losses → inf, zero trades → None, <2 return obs → None). `ledger.compute_metrics_by_strategy` reuses `compute_metrics` per strategy_id group, proven not to leak trades across strategies. `write_report` produces a real file — confirmed 5 report files exist on disk under `reports/backtests/`. |
| 7 | BACK-07: Random-strategy sanity test loses roughly the fee rate — if it profits, the harness is broken | VERIFIED | `tests/test_backtest_sanity.py` is a permanent, always-collected pytest (no `pytest.skip`, no markers excluding it, no `-m` filters in `pyproject.toml`). Independently re-ran the full suite: 150/150 passed. Queried `data/trader.db` directly: 8 `sanity_random_strategy` runs recorded, 94,792 cumulative sanity trades logged — proving the test executes for real on every suite run, not once. Scrutinized the drift-term derivation personally (see below) — non-circular. |

**Score:** 7/7 truths verified

### Sanity-Test Circularity Audit (BACK-07 deep check)

Per the task instructions, the drift-adjustment term was scrutinized directly in `tests/test_backtest_sanity.py`:

- `expected_bias = mean(cost_pct + symbol_drift)` where:
  - `cost_pct` reads only `trade["fees"]` and `trade["slippage"]` (recorded, config-derived quantities) — never `trade["pnl"]`.
  - `symbol_drift[symbol]` comes from `_symbol_average_daily_return(df)`, computed from `df = get_daily_bars(symbol, ...)` — **raw OHLCV price history fetched independently of `run_backtest` and `backtest_trades`**, before the run executes.
- The band's **width** uses the run's own empirical standard error of `pnl_pct` (expected and legitimate — a band's width is allowed to depend on this run's variance; only the **center** must be non-circular, which it is).
- A hard fail-safe `assert observed_mean < 0` is independent of the band and cannot be bypassed by a wide band.
- Confirmed no line assigns `expected_bias` from `statistics.mean(pnl...)` or any `backtest_trades.pnl`-derived quantity.
- **Conclusion: genuinely non-circular.** The original cost-only band failed seed-robustly (7 seeds) due to real survivorship drift in the pinned universe (AAPL/MSFT/GOOGL/BTC/ETH/DOGE all have large positive historical mean daily returns); the fix adds an exogenous, pre-computed market-drift term rather than loosening `k` or re-centering on the observed outcome. This matches the orchestrator-cited root cause exactly.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `trader/backtest/config.py` | FEE_TABLE, SLIPPAGE_PCT, EXIT_PROFILE, profile constants | VERIFIED | 124 lines, all constants present, frozen dataclass with `__post_init__` tuple-rejection |
| `migrations/0003_backtest.sql` | backtest_runs/backtest_trades DDL + CHECK constraints | VERIFIED | Confirmed live schema in `data/trader.db` matches exactly |
| `trader/backtest/iterator.py` | PointInTimeIterator (calendar, advance_to, history, bar_on) | VERIFIED | 140 lines, two-pointer, no re-filter idiom |
| `trader/backtest/metrics.py` | compute_metrics, write_report | VERIFIED | 210 lines, golden-fixture-tested |
| `trader/backtest/fills.py` | fee_for, slippage_pct_for, apply_slippage, entry_fill_price, worse_of_fill | VERIFIED | 103 lines, config-driven only, no hard-coded numbers |
| `trader/backtest/exits.py` | evaluate_exit, PositionState, ExitResult | VERIFIED | 207 lines, D-10 order confirmed by direct read |
| `trader/backtest/ledger.py` | record_run, record_trade, get_trades_for_run/strategy, compute_metrics_by_strategy | VERIFIED | 193 lines, parameterized SQL only |
| `trader/backtest/random_strategy.py`, `momentum_placeholder.py` | pick_entries contract | VERIFIED | 50/51 lines, shared signature |
| `trader/backtest/runner.py` | run_backtest orchestration | VERIFIED | 269 lines, imports/wires all of config, exits, fills, ledger, iterator |
| `trader/backtest/sanity_universe.py` | SANITY_UNIVERSE + backfill | VERIFIED | 68 lines; 6 symbols confirmed cached in `data/trader.db` |
| `tests/test_backtest_sanity.py` | permanent BACK-07 exit gate | VERIFIED | 214 lines, no skip, N=11,849 trades this run |
| `trader/backtest/run_momentum_placeholder.py` | e2e main() | VERIFIED | 79 lines; run 29 (and 4 others: 28, 30, 32, 34) produced real reports on disk |
| `reports/backtests/*.md` | dated report with plausible numbers | VERIFIED | 5 report files on disk, e.g. run29: 409 trades, PF 0.834, Sharpe 0.064, maxDD −98.3%, fees $133,533 |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `fills.py` | `config.py` | `from trader.backtest.config import FEE_TABLE, SLIPPAGE_PCT` | WIRED | Confirmed by direct read |
| `exits.py` | `config.py`, `fills.py` | `from trader.backtest.config import EXIT_PROFILE`, `from trader.backtest.fills import worse_of_fill` | WIRED | Confirmed by direct read |
| `runner.py` | `config, exits, fills, ledger, iterator` | orchestration imports | WIRED | Confirmed by direct read — all five modules imported |
| `ledger.py` | `metrics.py` | `from trader.backtest import metrics` | WIRED | `compute_metrics_by_strategy` reuses `metrics.compute_metrics` |
| `iterator.py` | `get_daily_bars` | NOT called directly by iterator (by design — bars pre-loaded by caller) | WIRED (correct architecture) | `runner.py`/tests load bars via `get_daily_bars` and pass `bars_by_symbol` dict into `PointInTimeIterator` |
| `sanity_universe.py` | `get_daily_bars` | one-time backfill | WIRED | Confirmed 6 symbols cached (AAPL 11,495 rows, MSFT 10,168, GOOGL 5,516, BTC/USDT 3,266, ETH/USDT 3,266, DOGE/USDT 2,579) |
| `test_backtest_sanity.py` | `runner.run_backtest`, `random_strategy.pick_entries` | direct calls | WIRED | Test executes; DB shows 8 accumulated `sanity_random_strategy` runs |
| `run_momentum_placeholder.py` | `runner.run_backtest`, `metrics.compute_metrics/write_report` | sequential calls | WIRED | 5 report files produced on disk across runs |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| BACK-01 | 02-02, 02-08 | Point-in-time bar iterator | SATISFIED | iterator.py + runner.py wiring |
| BACK-02 | 02-01, 02-04 | Per-venue fee model | SATISFIED | config.py FEE_TABLE + fills.fee_for |
| BACK-03 | 02-01, 02-04 | Slippage model scaled by asset class | SATISFIED | config.py SLIPPAGE_PCT + fills.apply_slippage |
| BACK-04 | 02-01, 02-05, 02-08 | Exit engine EXIT_PROFILES | SATISFIED | exits.py evaluate_exit, D-10 order confirmed |
| BACK-05 | 02-06, 02-08 | Trade ledger | SATISFIED | ledger.py record_run/record_trade |
| BACK-06 | 02-03, 02-06, 02-10 | Metrics module + per-strategy attribution | SATISFIED | metrics.py + ledger.compute_metrics_by_strategy + real report on disk |
| BACK-07 | 02-07, 02-09 | Random-strategy sanity test | SATISFIED | tests/test_backtest_sanity.py, permanent, non-circular, N=11,849, DB shows repeated real runs |

No orphaned requirements — all BACK-01…07 declared across the ten plans' `requirements:` frontmatter, matching REQUIREMENTS.md's Phase 2 section exactly.

### Behavioral Spot-Checks / Full Suite

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full test suite | `.venv/Scripts/python.exe -m pytest tests/ -q` | `150 passed in 33.71s` | PASS |
| Sanity test not silently skippable | `grep -n "skip\|xfail" tests/test_backtest_sanity.py`, `grep "markers\|addopts" pyproject.toml` | no matches | PASS |
| Sanity test executes for real, repeatedly | sqlite query on `backtest_runs`/`backtest_trades` | 8 `sanity_random_strategy` runs, 94,792 cumulative trades | PASS |
| Schema matches migration exactly | sqlite `sqlite_master` query | CHECK constraints on `asset_class` and `exit_reason` present, column list matches 02-01-PLAN.md exactly | PASS |
| E2E report artefact | `cat reports/backtests/2026-07-26-momentum_placeholder-run29.md` | 409 trades, PF 0.834, Sharpe 0.064, maxDD −98.3%, fees $133,533 — matches orchestrator-cited evidence exactly | PASS |
| No debt markers in phase-modified files | `grep -n "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` across `trader/backtest/*.py` | Only benign matches (`PROFILE_MOMENTUM_PLACEHOLDER` constant name) | PASS |

### Probe Execution

Not applicable — Phase 2 has no `scripts/*/tests/probe-*.sh` convention; verification is pytest-suite based per 02-VALIDATION.md. No probes declared in PLAN/SUMMARY files.

### Anti-Patterns Found

None. No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER debt markers, no stub returns (`return null`/`return {}`/`return []` patterns), no hardcoded fee/slippage numbers duplicated outside config.py, no `pytest.skip` on the exit-gate test.

### Human Verification Required

None. Plan 02-10 explicitly automated 02-VALIDATION.md's one manual-only verification item ("one real strategy end-to-end metrics report") via `tests/test_backtest_momentum_e2e.py`, which asserts `trade_count >= 1`, all metric keys finite, and the report file's existence/contents programmatically. No wall-clock or visual/UX checks apply to this phase (backend-only harness, no UI).

### Gaps Summary

No gaps. All 7 BACK-0X requirements are implemented, tested, and wired together into a working end-to-end pipeline. The full 150-test suite passes independently of the orchestrator's prior run. The sanity test's non-circular tolerance-band derivation was independently audited and confirmed sound — the drift term is computed exclusively from raw price history, never from backtest outcomes. The one real strategy (momentum placeholder) produces a genuine, non-trivial report on disk. Two deliberate, explicitly-documented scope decisions (Kraken maker-fee tier not modeled; small-cap-runner slippage tier left as an unwired Phase 3 hook) are locked orchestrator decisions recorded in 02-CONTEXT.md, not implementation gaps.

---

*Verified: 2026-07-26*
*Verifier: Claude (gsd-verifier)*
