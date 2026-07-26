# Phase 3: Strategy Lab - Research

**Researched:** 2026-07-26
**Domain:** Systematic trading strategy backtesting — signal generation (momentum, breakout), exit-parameter grid sweeps, regime-based out-of-sample validation, pre-registered kill conditions
**Confidence:** MEDIUM-HIGH (engine contracts and data-availability facts VERIFIED by direct tool execution against this repo's own venv and data sources; entry-rule parameterisation and regime-window boundaries are reasoned recommendations built on verified data, tagged ASSUMED per the provenance rule)

## Summary

Phase 3 adds two pure-function strategy agents and a sweep/validation harness on top of Phase 2's already-complete, already-tested (150 passing tests) backtest engine. The engine is long-only by construction (`fills.worse_of_fill` raises `NotImplementedError` for any short-side exit) — both the owner's momentum and breakout reference specs describe "mirror for short," but that half is structurally out of scope for this phase and must not be attempted.

Direct verification against this repo's venv (not training-data recall) produced four load-bearing facts that reshape the plan from what the phase document implies at face value: (1) all 15 proposed additional stock tickers have 10+ years of yfinance history, confirmed by live fetch; (2) Binance's actual first-candle dates for PEPE (2023-05-05), BONK (2023-12-15), and WIF (2024-03-05) are now more than two years in the past given the current date (2026-07-26), which means — contrary to the phase document's framing of memecoins as "too short-lived for regime splits" — these three coins now have enough history to receive their OWN two-regime pair (a 2023-2024 mania regime and a 2025 correction regime), rather than being excluded from D-08's "two regimes minimum" requirement; (3) a live `run_backtest` timing benchmark against real cached data shows the full D-06 grid (270 cells) is inexpensive — roughly 16-17 minutes single-threaded for the entire tune-sweep across all three asset-class buckets — so no pruning, fractional-factorial design, or parallelisation is needed; (4) `backtest_runs.params_json` is an unconstrained JSON blob already, so sweep provenance (`sweep_id`, `regime`, `split`) needs zero schema migration.

**Primary recommendation:** Implement momentum (RSI(14) + 2x-20-day-volume-surge + N-day-high break) and breakout (NR7 volatility contraction + 20-day-high break) as long-only pure functions matching `pick_entries(iterator, date, open_positions, rng)`, fix their entry-rule parameters (not swept), sweep only the D-06 exit grid per the three asset-class buckets (stock / crypto_major+legacy-memecoin / new-memecoin) against the six regime windows below, tag every `backtest_runs` row with a `sweep_id`/`regime`/`split` triple in `params_json`, enforce a minimum-trade-count floor alongside D-10's top-5 rule, and run the whole sweep sequentially in one process (do not parallelise — SQLite single-writer semantics make it a net negative at this scale).

## Architectural Responsibility Map

This is a single-process research pipeline, not a multi-tier application — "tiers" here are pipeline stages, not client/server boundaries.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Entry signal generation (RSI, volume surge, NR7, N-day high) | Strategy layer (new `trader/backtest/strategies/`) | — | Pure functions over `iterator.history()`, no engine knowledge needed |
| Fills, exits, fees, slippage, ledger writes | Execution engine (existing Phase 2 `runner.py`/`exits.py`/`fills.py`/`ledger.py`) | — | Already built and tested; Phase 3 consumes, never modifies |
| Exit-parameter grid definition & iteration | Sweep orchestration (new `trader/backtest/sweep.py`) | Strategy layer (supplies which strategies to sweep) | Owns `itertools.product` over D-06's grid, calls `run_backtest` once per cell |
| Regime/date-range freezing, tune/OOS split | Config layer (new `trader/backtest/regimes.py` or a committed JSON/YAML) | Sweep orchestration (reads it) | Must be committed BEFORE results are viewed (D-08/D-09) — belongs in its own file so freezing is auditable via git-style diff review even without git in this env |
| Universe list | Config layer (new `trader/backtest/universe.py`) | Data layer (`trader/data/api.get_daily_bars` backfills it) | Fixed list is a Phase-3-only decision (D-04); data fetch reuses Phase 1 exactly |
| Survivor selection (top-5 tune → OOS) | Sweep orchestration | Reporting | Selection rule is pre-registered per D-10, applied mechanically after tune sweep completes |
| Reporting (markdown summaries) | Reporting layer (extends existing `trader/backtest/metrics.write_report`) | — | Reuses `compute_metrics` verbatim; Phase 3 adds a multi-config comparison table, not new metric math |
| Kill-condition registry | Governance (`.planning/phases/03-strategy-lab/KILL-CONDITIONS.md`, hand/script-authored) | — | Explicitly a planning-doc artifact per D-11, not application code |

## Standard Stack

### Core
No new external packages are required. `pandas` 3.0.5 and `numpy` 2.5.1 [VERIFIED: `pip show`, this repo's venv] are already installed and sufficient for every indicator this phase needs (RSI, rolling volume mean, rolling high/low, ATR, Bollinger width).

### Supporting
None needed. `pandas_ta`, `talib`, and `ta` are all absent from the venv [VERIFIED: `python -c "import ..."` against this repo's venv] — do not add any of them (see Don't Hand-Roll below for why hand-rolling is the *correct* choice here, not a shortcut).

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled pandas RSI/ATR/BB-width | `pandas-ta` or `TA-Lib` | TA-Lib requires a compiled C extension that is a known Windows install pain point (the project's own platform); `pandas-ta` is a maintenance-lapsed dependency as of recent years. Neither buys anything a 5-10 line pandas rolling computation doesn't already give, and hand-rolled code is directly unit-testable against hand-built fixture bars the same way `momentum_placeholder.py` already is. |
| Sequential single-process sweep | `multiprocessing.Pool` sweep (matches project's `parallelization: true` config default) | At ~16-17 min total measured cost (see Sweep Engineering below), parallelising buys little wall-clock time but introduces SQLite "database is locked" risk from concurrent `conn.commit()` calls in `ledger.record_run`/`record_trade` unless every worker opens its own connection in WAL mode — added complexity not justified by the measured runtime. Recommend overriding the project default for this phase specifically; flagged in Open Questions for owner sign-off. |

**Installation:** None required — no new packages.

**Version verification:** `pandas` 3.0.5, `numpy` 2.5.1 confirmed installed via `pip show` in this repo's `.venv` [VERIFIED].

## Package Legitimacy Audit

Not applicable — this phase introduces zero new external package dependencies. All required computation (RSI, rolling volume average, rolling high/low, ATR, Bollinger Band width, NR7) is implementable with the already-installed `pandas`/`numpy`. If a future phase revisits this decision, re-run the full Package Legitimacy Gate before adding any TA library.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STRAT-01 | Momentum agent (RSI + volume surge) implemented as pure functions over bars | RSI(14)/volume-surge(2x-20d) concrete parameterisation below (Code Examples); must follow `pick_entries` contract and long-only constraint |
| STRAT-02 | Breakout agent (20-day high after volatility contraction) implemented | NR7 primary + ATR-ratio variant contraction gate below (Code Examples) |
| STRAT-03 | Exit-parameter sweep per asset class (stop -5%...-30%, TP +20%...+100%, trail variants) | Sweep Engineering section: 270-cell grid, verified per-run timing, three asset-class buckets |
| STRAT-04 | Configs tested across at least two regimes (trending year, choppy year) | Regime Windows section: six frozen windows across three buckets, each with real verified return/drawdown stats |
| STRAT-05 | Out-of-sample rule enforced — tune on period A, validate on period B | Tune/OOS split dates given per regime; frozen-config integrity test in Validation Architecture |
| STRAT-06 | Pre-registered kill condition written for every surviving config before Phase 4 | Common Pitfalls + Validation Architecture: `KILL-CONDITIONS.md` existence/content gate |
</phase_requirements>

## Architecture Patterns

### System Architecture Diagram

```
                 ┌─────────────────────────┐
                 │  universe.py (config)   │  fixed symbol lists per
                 │  regimes.py (config)    │  asset class; frozen dates
                 └────────────┬────────────┘
                              │ read at sweep start (before any result is viewed)
                              ▼
 strategies/momentum.py ──┐   ┌──────────────────────────┐
 strategies/breakout.py ──┼──▶│   sweep.py (new)         │
   pick_entries(iterator,  │  │  for regime in regimes:  │
   date, open_positions,   │  │    for cell in grid(270):│
   rng) -> list[str]       │  │      run_backtest(...)   │──▶ backtest_runs / backtest_trades (SQLite)
                           │  │        [params_json:      │         │
                           │  │         sweep_id, regime, │         │ compute_metrics_by_strategy
                           │  │         split, cell]      │         ▼
                           │  └──────────┬───────────────┘   metrics.py (existing, unchanged)
                           │             │ top-5 by tune metric per (strategy, asset_class)
                           │             ▼
                           │     OOS validation runs (same run_backtest, split="oos")
                           │             │
                           │             ▼
                           │     survivors (profitable OOS after costs)
                           │             │
                           │             ▼
                           │   reports/backtests/*.md  +  KILL-CONDITIONS.md
                           └──────────────────────────────────────────────────
```
A reader trace: universe/regime config is frozen first → sweep.py drives entry signals from the two new strategy modules through the UNCHANGED `run_backtest` → every cell's trades land in the existing ledger tables tagged with sweep provenance → top-5 tune survivors get one OOS run each → anything still profitable after costs becomes a report row and gets a kill condition before Phase 4 starts.

### Recommended Project Structure
```
trader/backtest/
├── strategies/
│   ├── __init__.py
│   ├── momentum.py       # STRAT-01: RSI(14) + volume surge + N-day high
│   └── breakout.py       # STRAT-02: NR7 contraction + 20-day high
├── universe.py           # D-04 fixed universe lists (stock / crypto_major / memecoin)
├── regimes.py            # D-08/D-09 frozen regime + tune/OOS split dates
├── sweep.py              # D-06/D-07 grid iteration + sweep_id provenance
└── (existing: runner.py, config.py, exits.py, fills.py, ledger.py, metrics.py — unchanged)
tests/
├── test_strategy_momentum.py       # new
├── test_strategy_breakout.py       # new
├── test_sweep_engine.py            # new (tiny-grid smoke)
├── test_regime_config.py           # new (frozen-split integrity)
└── test_kill_conditions.py         # new (existence/content gate)
reports/backtests/
└── {date}-{strategy}-{asset_class}-{regime}-sweep.md   # per D-12
.planning/phases/03-strategy-lab/
└── KILL-CONDITIONS.md   # per D-11, committed before Phase 4
```

### Pattern 1: Point-in-time indicator computation over `iterator.history()`
**What:** Every indicator reads only `iterator.history(symbol)` — a numpy array of `[open, high, low, close, volume]` rows bounded at the current pointer (verified in `trader/backtest/iterator.py`). The array's last row IS today's bar (the runner already calls `advance_to(date)` before invoking `strategy_fn`), so "today's close/volume" is `history[-1]`.
**When to use:** Both momentum and breakout entry signals.
**Example:**
```python
# Source: pattern derived from trader/backtest/momentum_placeholder.py (existing D-15 code)
import numpy as np

def _rsi_wilder(closes: np.ndarray, period: int = 14) -> float:
    """Wilder's smoothed RSI over the LAST `period+1` closes in `closes`.
    Caller must ensure len(closes) >= period + 1."""
    deltas = np.diff(closes[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains.mean()
    avg_loss = losses.mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))
```

### Pattern 2: Fixed entry-rule constants, swept exit-profile grid
**What:** RSI period/threshold, volume-surge multiplier, NR7 window, and ATR-ratio threshold are constants chosen once by research (not swept) — only the D-06 exit-profile grid (stop/TP/trailing/time-stop) varies per cell. This keeps the grid at exactly 270 cells rather than multiplying by entry-parameter variants.
**When to use:** `sweep.py`'s grid construction.
**Example:**
```python
# Source: derived from trader/backtest/config.py's EXIT_PROFILE + D-06's stated ranges
import itertools

STOPS = (-0.05, -0.10, -0.15, -0.20, -0.25, -0.30)
TPS = (0.20, 0.40, 0.60, 0.80, 1.00)
TRAILS = (None, 0.10, 0.20)
TIME_STOPS = (None, 10, 30)

def exit_profile_grid():
    for stop_pct, tp_pct, trailing_pct, max_hold_days in itertools.product(
        STOPS, TPS, TRAILS, TIME_STOPS
    ):
        yield config.EXIT_PROFILE(
            stop_pct=stop_pct, tp_pct=tp_pct, scale_out=(),
            trailing_pct=trailing_pct, max_hold_days=max_hold_days,
            eod_flat=False,
        )
```

### Pattern 3: Sweep provenance via free-form `params_json`
**What:** `ledger.record_run` accepts an arbitrary `params: dict` forwarded verbatim to `params_json` — no migration needed to add sweep metadata.
**When to use:** Every `run_backtest` call inside the sweep.
**Example:**
```python
# Source: trader/backtest/runner.py run_backtest() + trader/backtest/ledger.py record_run()
# (existing signatures, unchanged)
params = {
    "profile_name": f"{strategy_id}_{asset_class}_{regime}_{split}_s{stop_pct}_tp{tp_pct}",
    "sweep_id": "2026-07-26-strategy-lab-v1",
    "regime": "trend",        # or "chop" / "bear" / "mania" / "correction"
    "split": "tune",          # or "oos"
    "asset_class": "stock",
    "strategy": "momentum",
    "stop_pct": stop_pct, "tp_pct": tp_pct,
    "trailing_pct": trailing_pct, "max_hold_days": max_hold_days,
}
run_backtest(pick_entries, universe, profile, bars, seed=42, params=params,
             strategy_id="momentum_stock", conn=conn)
```

### Anti-Patterns to Avoid
- **Building short-side logic:** `fills.worse_of_fill` raises `NotImplementedError` for `side in ("buy", "buy_at_tp")` [VERIFIED: `trader/backtest/fills.py` source, docstring cites D-15]. Both reference specs say "mirror for short" — do not implement it; the engine cannot execute it this phase.
- **Sweeping entry-rule parameters alongside exit parameters:** would silently balloon the grid past D-06's specified size and make "which parameter caused this result" ambiguous. Keep entry rules fixed constants.
- **Computing a rolling average that includes today's own volume/price in its own baseline:** inflates the surge/breakout signal's own trigger threshold. Always slice `history[-(N+1):-1]` for the baseline and `history[-1]` for "today."
- **Running sweep cells through anything but `run_backtest`:** D-07 requires every cell go through the unmodified engine — no bypassing fills/slippage/fees for speed.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| RSI / ATR / Bollinger Band width computation | A new TA library wrapper, or install TA-Lib | Hand-rolled pandas/numpy rolling functions (5-10 lines each, see Code Examples) | No new dependency, fully unit-testable against fixture bars exactly like the existing `momentum_placeholder.py`; TA-Lib's C-extension install is a documented Windows pain point this project has so far avoided entirely |
| Multiple-comparison / overfitting correction | A from-scratch statistical significance framework (e.g. implementing the full Deflated Sharpe Ratio machinery) | D-10's pre-registered top-5 rule + a minimum-trade-count floor + reporting the raw trial count | The Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014) is the rigorous academic answer but requires estimating return skewness/kurtosis and a benchmark Sharpe variance across trials — disproportionate for a phase whose own exit criterion is "2-3 survivors profitable OOS, or honestly nothing." The pre-registered top-5 rule already prevents the single worst failure mode (cherry-picking the OOS winner from hundreds of cells) at near-zero engineering cost. |
| Grid iteration / combinatorics | Custom nested-loop grid builder | `itertools.product` | Standard library, zero risk of an off-by-one cell count, directly testable (`len(list(exit_profile_grid())) == 270`) |
| Regime/date-range storage | A new database table | A single committed Python module or JSON file (`trader/backtest/regimes.py`) | D-08/D-09 require the dates frozen and reviewable before any sweep runs; a plain file diff serves that audit purpose without new schema |

**Key insight:** In this domain the temptation to reach for a heavyweight TA or stats library is worse than hand-rolling — the indicators are simple, well-documented formulas, and this project's own honesty discipline (point-in-time provable in unit tests, per Phase 2's threat model) is easier to guarantee over code you wrote and can read than over a third-party library's internal windowing behaviour.

## Universe

**Method:** All symbols below were confirmed fetchable with 10+ years of history via a live call to `trader.data.stock_source`/`get_daily_bars`'s underlying `yfinance` client, and all crypto first-candle dates were confirmed via a live call to this project's own `ccxt.binance()` client (the same client `trader/data/crypto_source.py` uses) — not training-data recall [VERIFIED: direct tool execution against this repo's venv, 2026-07-26].

### Stocks (18 total: sanity trio + 15 additional)
| Symbol | First bar (yfinance) | Rows | Sector flavour |
|--------|----------------------|------|-----------------|
| AAPL, MSFT, GOOGL | (already cached, sanity trio, D-04) | — | mega-cap tech |
| NVDA | 1999-01-22 | 6,918 | high-beta growth/tech — strong momentum character |
| AMD | 1980-03-17 | 11,683 | high-beta growth/tech |
| TSLA | 2010-06-29 | 4,042 | high-beta growth |
| AMZN | 1997-05-15 | 7,343 | mega-cap growth |
| META | 2012-05-18 | 3,565 | mega-cap growth |
| NFLX | 2002-05-23 | 6,081 | growth/momentum-prone |
| CRM | 2004-06-23 | 5,557 | growth/software |
| ADBE | 1986-08-13 | 10,063 | growth/software |
| COST | 1986-07-09 | 10,088 | steady large-cap (regime diversity) |
| JPM | 1980-03-17 | 11,683 | financials (regime diversity) |
| XOM | 1962-01-02 | 16,248 | energy (regime diversity) |
| UNH | 1984-10-17 | 10,522 | healthcare (regime diversity) |
| WMT | 1972-08-25 | 13,589 | consumer staples (regime diversity) |
| HD | 1981-09-22 | 11,300 | consumer discretionary |
| DIS | 1962-01-02 | 16,248 | media/consumer |

*All row/date figures VERIFIED by live `yfinance.Ticker(t).history(period="max")` call, 2026-07-26.* The 8 growth names give the momentum/breakout agents names with real trending character; the 7 steadier names (COST/JPM/XOM/UNH/WMT/HD/DIS) give regime contrast so a "survivor" isn't just riding one correlated tech cluster (see Open Questions #3).

### Crypto (7 total)
| Symbol | Asset class (CoinGecko category routing) | First Binance candle | Confirmed history depth as of 2026-07-26 |
|--------|-------------------------------------------|----------------------|--------------------------------------------|
| BTC/USDT | crypto_major | 2017-08-17 | ~9 years |
| ETH/USDT | crypto_major | 2017-08-17 | ~9 years |
| DOGE/USDT | memecoin (CoinGecko "Meme" category) | 2019-07-05 | ~7 years |
| SHIB/USDT | memecoin | 2021-05-10 | ~5 years |
| PEPE/USDT | memecoin | 2023-05-05 | ~3.2 years |
| BONK/USDT | memecoin | 2023-12-15 | ~2.6 years |
| WIF/USDT | memecoin | 2024-03-05 | ~2.4 years |

*All first-candle dates VERIFIED via a direct `ccxt.binance().fetch_ohlcv(...)` call in this repo's venv, 2026-07-26 — not web search or training recall, though independently cross-checked against Binance's own listing announcements [CITED: binance.com support announcements, see Sources].* DOGE and SHIB classify as `memecoin` (not `crypto_major`) via CoinGecko's category API [CITED: `trader/data/classify.py` source] because their CoinGecko categories include "Meme" — this matches D-04's own framing of DOGE/SHIB/PEPE/BONK/WIF as one "named memecoin universe," distinct from BTC/ETH.

**Important correction to the phase context's framing:** D-04/D-05 describe the memecoins as too short-lived to receive "two regimes minimum." That was true as of the phase document's original drafting relative to an earlier "today," but is no longer true: PEPE, BONK, and WIF each now have 2+ years of history (current date 2026-07-26), which is enough to define a mania regime (2023-2024) AND a correction regime (2025) for them specifically — see Regime Windows below. This is an ASSUMED interpretation resting on VERIFIED underlying dates; flag for owner confirmation since it changes phase scope slightly (memecoins get real OOS testing, not a documented gap).

## Regime Windows

**Method:** Every return/drawdown figure below was computed directly from real cached/live bar data (`SPY` via yfinance as a market-level proxy for the stock regime call; `BTC/USDT`, `DOGE/USDT`, `SHIB/USDT`, `PEPE/USDT`, `BONK/USDT`, `WIF/USDT` via this repo's own `ccxt.binance()` client) [VERIFIED: direct tool execution, 2026-07-26]. This satisfies STRAT-04's "justify choices with drawdown/trend stats" instruction with real numbers, not assumed ones.

### Stocks
| Regime | Window | Evidence (SPY, verified) |
|--------|--------|---------------------------|
| Trending | 2023-01-01 → 2024-12-31 | 2023: +26.7% (max DD -10.0%); 2024: +25.6% (max DD -8.4%) — two clean up years, low realized drawdown |
| Choppy | 2015-01-01 → 2016-12-31 | 2015: +1.3% (max DD -11.9%, essentially flat with a sharp August selloff); 2016: +13.6% (max DD -9.2%, mild-up year with an early-year correction) — genuinely range-bound/non-trending character |

**Tune/OOS split:**
- Trending — Tune: 2023-01-01 → 2024-06-30 (18mo) | OOS: 2024-07-01 → 2024-12-31 (6mo)
- Choppy — Tune: 2015-01-01 → 2016-06-30 (18mo) | OOS: 2016-07-01 → 2016-12-31 (6mo)

### Crypto major + legacy memecoins (BTC, ETH, DOGE, SHIB — full history predates both windows)
| Regime | Window | Evidence (verified) |
|--------|--------|-----------------------|
| Trending | 2023-01-01 → 2024-12-31 | BTC: +154.5% / +111.8%; DOGE: +27.5% / +243.5%; SHIB: +27.6% / +98.3% — same calendar window as the stock trending regime, deliberately aligned for cross-asset comparability |
| Bear/Choppy | 2022-01-01 → 2022-12-31 | BTC: -65.3% (max DD -66.9%); DOGE: -59.4%; SHIB: -76.3% — the 2022 "crypto winter," a clean full-year bear |

**Tune/OOS split:**
- Trending — Tune: 2023-01-01 → 2024-06-30 | OOS: 2024-07-01 → 2024-12-31
- Bear — Tune: 2022-01-01 → 2022-08-31 (8mo) | OOS: 2022-09-01 → 2022-12-31 (4mo) — **thin OOS window, see Common Pitfalls and minimum-trade-count floor below**

### New memecoins (PEPE, BONK, WIF — insufficient history for the 2022 bear window)
| Regime | Window | Evidence (verified) |
|--------|--------|-----------------------|
| Mania | symbol's first candle → 2024-12-31 | PEPE 2024: +1315.6% (after a -65.1% 2023, i.e. mixed character within the window — see caveat below); BONK 2024: +104.1%; WIF 2024: +20.4% |
| Correction | 2025-01-01 → 2025-12-31 | PEPE: -79.2% (max DD -82.8%); BONK: -74.9% (max DD -80.7%); WIF: -85.5% (max DD -87.6%) — uniformly severe, a clean second regime |

**Tune/OOS split:**
- Mania — Tune: symbol's first candle → 2024-08-31 | OOS: 2024-09-01 → 2024-12-31 — **WIF's tune window is only ~6 months (Mar-Aug 2024); flag as thin-sample risk**
- Correction — Tune: 2025-01-01 → 2025-08-31 | OOS: 2025-09-01 → 2025-12-31

**Caveat on "Mania" labelling:** PEPE's own 2023 trajectory (-65.1%) was actually choppy-down before its 2024 explosion, so the single "mania" label is an approximation of the aggregate window's character, not a claim that every included symbol trended smoothly throughout. Report per-symbol contribution alongside the aggregate regime label (see Open Questions #3).

## Sweep Engineering

**Grid size:** 6 stops × 5 TPs × 3 trailing variants × 3 time-stop variants = **270 cells** per (strategy × asset-class-bucket × regime-tune-window), matching D-06 exactly.

**Runtime — VERIFIED by direct benchmark** (not estimated): a live timed loop of `run_backtest` against real cached bars in this repo's own `data/trader.db`, 2026-07-26:
| Bucket | Universe size | 2-year window cost per run | Tune-sweep cost (2 strategies × 2 regimes × 270 cells = 1,080 runs) |
|--------|----------------|------------------------------|--------------------------------------------------------------------|
| Stock | 18 symbols | 425.6 ms | ≈ 460s ≈ 7.7 min |
| Crypto major + legacy memecoin | 4 symbols (matches BTC/ETH/DOGE/SHIB) | 245.7 ms | ≈ 266s ≈ 4.4 min |
| New memecoin | 3 symbols | ≤ 245.7 ms (conservative, fewer symbols than the benchmark) | ≈ 266s ≈ 4.4 min (upper bound) |

**Grand total tune-sweep estimate: ≈ 16-17 minutes, single-threaded.** OOS validation is top-5 × 2 strategies × 3 buckets × 2 regimes = 60 runs against shorter (~6mo) windows — well under a minute. [VERIFIED: benchmark used the existing `momentum_placeholder.pick_entries` as a timing proxy, not the real momentum/breakout agents — see Assumptions Log A4 for why this is a floor, not a ceiling.]

**Recommendation: do not prune, do not parallelise.** At ~17 minutes total, a fractional-factorial design or coarse-then-fine search adds engineering risk (a wrongly-pruned region could hide the actual survivor) for a time saving that doesn't matter. Parallelising across processes risks SQLite "database is locked" errors from concurrent `conn.commit()` calls in `ledger.record_run`/`record_trade` unless each worker opens an independent connection in WAL mode — added complexity not justified here. This deviates from the project's `config.json` `"parallelization": true` default; flagged in Open Questions for explicit owner sign-off since it overrides a stated preference.

**Provenance:** tag every sweep run's `params` dict with `sweep_id`, `regime`, `split` (`"tune"`/`"oos"`), `asset_class`, and `strategy` keys — `ledger.record_run` already accepts and stores an arbitrary dict as `params_json` with zero schema change required [VERIFIED: `migrations/0003_backtest.sql` — `params_json TEXT NOT NULL`, no fixed schema].

## Overfitting Guards (D-10 discipline)

D-10 already locks the primary anti-cherry-pick control: at most the top 5 tune-sweep configs per (strategy, asset-class bucket) advance to OOS. Proportionate additions, given the project's own philosophy of "kill cheaply, don't over-engineer the safety net":

1. **Minimum trade-count floor.** Recommend requiring ≥30 trades in a cell's tune-period result before that cell is even eligible for the top-5 ranking (excludes small-N flukes), and ≥15 trades in the OOS window for a "survivor" verdict to count as meaningful (below that, report "insufficient sample — inconclusive," not pass/fail). The 2022 bear OOS window (4 months) and WIF's mania tune window (~6 months) are the most likely to hit this floor — document any cell that fails it rather than silently dropping it.
2. **Rank by post-cost profit factor, not raw return**, during tune-sweep ranking — the whole point of this harness is never lying about costs, so the ranking metric that selects the top 5 must already reflect them.
2. **Report the trial count.** State "N cells tested" in every sweep report (`270 × regimes × buckets`), a low-cost nod to the core lesson of the Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014) [CITED: pm-research.com/SSRN, see Sources] — "the most important piece of information missing from most published backtests is the number of trials attempted" — without implementing the full DSR statistic, which requires skewness/kurtosis/benchmark-variance assumptions disproportionate to this phase's binary exit criterion.
3. **Do not implement White's Reality Check or the full Deflated Sharpe Ratio.** Both are legitimate, rigorous tools, but the pre-registered top-5 rule plus a trade-count floor already close the specific failure mode this phase cares about (cherry-picking a lucky OOS winner) at a fraction of the engineering cost, matching D-05's proportionality.

## Common Pitfalls

### Pitfall 1: Sweeping entry-rule parameters by accident
**What goes wrong:** Someone parameterises `pick_entries` itself (RSI threshold, RVOL multiplier) and folds it into the exit-profile grid, silently multiplying cell count past 270 and making the D-10 top-5 selection ambiguous about which axis drove the result.
**Why it happens:** It's tempting to sweep "everything" once the grid infrastructure exists.
**How to avoid:** Keep entry-rule constants as literal module-level constants in `strategies/momentum.py`/`breakout.py`, not sweep-grid inputs.
**Warning signs:** `exit_profile_grid()` yielding more than 270 items for a bucket that shouldn't have the extra memecoin time-stop variant (see Open Questions #2).

### Pitfall 2: Volume/price baseline includes "today"
**What goes wrong:** A rolling 20-day volume average computed over `history[-20:]` (including today's own bar) makes an extreme volume day partially inflate its own baseline, understating the true surge ratio.
**Why it happens:** Off-by-one slicing is the single easiest mistake in this kind of indicator code.
**How to avoid:** Baseline window is always `history[-(N+1):-1]`; "today" is always `history[-1]`.
**Warning signs:** A fixture test where a single huge-volume day should surge past 2x but computes just under threshold.

### Pitfall 3: Thin OOS samples treated as clean pass/fail
**What goes wrong:** The 2022 crypto bear OOS window (4 months) or WIF's mania tune window (~6 months) produces a handful of trades; a "profitable" verdict on 6 trades looks like a survivor but is statistically meaningless.
**Why it happens:** The mechanical top-5-then-OOS rule doesn't itself check sample size.
**How to avoid:** Apply the minimum-trade-count floor (Overfitting Guards, above) as a hard gate before any pass/fail label is assigned.
**Warning signs:** A "survivor" whose OOS trade count is in single digits.

### Pitfall 4: Attempting short-side signals
**What goes wrong:** Following the reference specs' "mirror for short" literally produces a `pick_entries` that (implicitly or explicitly) tries to open a short position; the engine's `worse_of_fill` raises `NotImplementedError` the first time such a position needs a stop/TP exit evaluated.
**Why it happens:** Both `07_momentum_trading.md` and `03_breakout_trading.md` describe symmetric long/short rules as if both are always in scope.
**How to avoid:** Implement long-only; treat "mirror for short" as explicitly out of Phase 3 scope (inherited constraint from Phase 2's D-15, not a Phase 3 decision).
**Warning signs:** Any code path constructing a negative `total_qty` or calling `fills.entry_fill_price(..., side="sell")` at entry time.

### Pitfall 5: Regime label mistaken for per-symbol truth
**What goes wrong:** The "2023-2024 mania" and "trending" labels are aggregate/window-level characterisations; individual symbols (especially PEPE, whose 2023 was actually down -65%) don't uniformly match the label throughout the window.
**Why it happens:** A single regime name is a convenient shorthand that hides intra-window variation.
**How to avoid:** Report per-symbol contribution to a survivor's P&L alongside the aggregate regime label (see Open Questions #3).
**Warning signs:** A "trending regime" survivor whose entire edge comes from one symbol's late-window rally.

## Code Examples

### RSI(14), volume surge, N-day-high signal (momentum agent)
```python
# Source: derived pattern, following trader/backtest/momentum_placeholder.py's
# existing point-in-time discipline (D-15) and library file 07's stated
# indicators (RVOL > 2x is "the key filter"; RSI "not for overbought fades
# -- strong momentum lives above 70"; "break of recent highs").
RSI_PERIOD = 14          # [ASSUMED] standard daily-bar RSI period
RSI_MOMENTUM_FLOOR = 60  # [ASSUMED] "momentum lives above 60-70" per library file 07
VOLUME_SURGE_MULT = 2.0  # [ASSUMED] library file 07's stated RVOL > 2x filter
BREAK_LOOKBACK = 20      # [ASSUMED] "break of recent highs" -- 20d matches the
                         # existing momentum_placeholder's LOOKBACK_DAYS convention

def pick_entries(iterator, date, open_positions, rng):
    entries = []
    for symbol in iterator.symbols:
        if symbol in open_positions:
            continue
        history = iterator.history(symbol)
        if len(history) < BREAK_LOOKBACK + 1:
            continue
        closes = history[:, 3]
        volumes = history[:, 4]
        highs = history[:, 1]

        rsi = _rsi_wilder(closes, RSI_PERIOD)
        today_volume = volumes[-1]
        baseline_volume = volumes[-(BREAK_LOOKBACK + 1):-1].mean()
        today_close = closes[-1]
        prior_high = highs[-(BREAK_LOOKBACK + 1):-1].max()

        if (
            rsi >= RSI_MOMENTUM_FLOOR
            and today_volume > VOLUME_SURGE_MULT * baseline_volume
            and today_close > prior_high
        ):
            entries.append(symbol)
    return entries
```

### NR7 volatility contraction + 20-day-high breakout (breakout agent)
```python
# Source: derived pattern, following library file 03's stated rules
# ("tight range, declining ATR/Bollinger squeeze", "close above resistance",
# "volume ... > 1.5x 20-bar average") and its own Notes for Automation
# ("N-bar high/low ... Bollinger Band width percentile ... or ATR percentile").
NR_WINDOW = 7             # [ASSUMED] NR7, the standard named pattern
BREAKOUT_LOOKBACK = 20    # per phase document's "20-day high"
VOLUME_CONFIRM_MULT = 1.5 # [ASSUMED] library file 03's stated 1.5x 20-bar average
ATR_RATIO_VARIANT_THRESHOLD = 0.7  # [ASSUMED] variant contraction measure

def _true_range(high, low, prior_close):
    return max(high - low, abs(high - prior_close), abs(low - prior_close))

def pick_entries(iterator, date, open_positions, rng):
    entries = []
    for symbol in iterator.symbols:
        if symbol in open_positions:
            continue
        history = iterator.history(symbol)
        if len(history) < BREAKOUT_LOOKBACK + 1:
            continue
        highs, lows, closes, volumes = (
            history[:, 1], history[:, 2], history[:, 3], history[:, 4]
        )
        ranges = highs - lows  # simplified NR check on raw H-L range
        is_nr7 = ranges[-1] == ranges[-NR_WINDOW:].min()

        today_close = closes[-1]
        prior_high = highs[-(BREAKOUT_LOOKBACK + 1):-1].max()
        today_volume = volumes[-1]
        baseline_volume = volumes[-(BREAKOUT_LOOKBACK + 1):-1].mean()

        if (
            is_nr7
            and today_close > prior_high
            and today_volume > VOLUME_CONFIRM_MULT * baseline_volume
        ):
            entries.append(symbol)
    return entries
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|-------------------|---------------|--------|
| Treat PEPE/BONK/WIF as too new for regime splitting (phase document's original framing) | Treat them as having a full two-regime pair (mania 2023-2024, correction 2025) | As of "today" (2026-07-26) — 2+ years have passed since each coin's listing | Memecoin survivors get real OOS validation instead of a documented scope gap; changes what STRAT-04/05 can honestly claim for this asset class |

**Deprecated/outdated:** None specific to this domain beyond the above — RSI/volume-surge/volatility-contraction techniques described in the owner's reference specs remain standard practice, not deprecated methodology.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The 15 additional stock tickers were chosen for "reasonable momentum character" via judgment, not a formal factor screen (their existence/history-depth IS verified, but the selection rationale is not) | Universe | A less momentum-prone universe could understate the strategies' true edge; low risk since the sweep itself will show weak signal counts if the universe is a poor fit |
| A2 | RSI(14)/RVOL-2x/N-day-high(20) for momentum; NR7/20-day-high/1.5x-volume for breakout; ATR-ratio-0.7 as breakout's variant contraction measure | Code Examples | These are reasonable, library-informed defaults but not independently back-tested prior to this recommendation; if wrong, the sweep may show weak or zero signal counts across the board, which is itself informative (kill cheaply) |
| A3 | "Trending"/"Choppy"/"Bear"/"Mania"/"Correction" regime LABELS and exact date boundaries are a judgment call built on VERIFIED return/drawdown numbers | Regime Windows | A mislabelled regime doesn't invalidate the OOS discipline (the tune/OOS split is still honest) but could mischaracterise what "passing in 2 conditions" (a later Phase 6 gate) actually proved |
| A4 | The sweep runtime benchmark (16-17 min) used `momentum_placeholder.pick_entries`, not the real momentum/breakout agents, which do more per-call computation | Sweep Engineering | Real runtime could be modestly higher (more rolling-window math per call); treat 17 min as a floor, budget up to ~30 min as a safe upper bound — still well within a single working session either way |
| A5 | Recommending sequential (non-parallel) execution overrides the project's `config.json` `"parallelization": true` default | Sweep Engineering | If the owner strongly prefers parallel execution regardless of the small time saving, the planner should add a WAL-mode/per-worker-connection task rather than skip parallelisation silently |
| A6 | Memecoins (PEPE/BONK/WIF) now have enough history for two real regimes, reversing the phase document's original "too short for regime splits" framing | Universe / Regime Windows | If the owner intended memecoins to stay a documented gap regardless of elapsed time, this expands Phase 3 scope beyond what was originally discussed — flagged explicitly for confirmation |

## Open Questions (RESOLVED)

1. **Breakout retest-entry variant.** The owner's library file 03 recommends waiting for a retest of the broken level ("lowers trade frequency but meaningfully improves quality"). Should Phase 3 sweep both with-retest and without-retest as an entry variant?
   - What we know: retest is described as strictly optional/preferred, not mandatory, in the reference spec.
   - What's unclear: whether the resulting frequency drop would starve the already-thin crypto-bear and WIF-mania OOS windows below the minimum-trade-count floor.
   - Recommendation: fix to no-retest for v1 (maximises trade count for statistical power in the thin windows); revisit only if false-breakout rate looks like the dominant failure mode in the tune-sweep results.
   - **RESOLVED (orchestrator):** Breakout v1 ships no-retest, matching the recommendation exactly — maximises OOS trade count. Retest variant deferred, not built this phase (see 03-01-PLAN.md Task 2, breakout.py module docstring).

2. **Memecoin-specific time-stop variant.** D-06 says "memecoins additionally test eod_flat-style short holds" — is this a 4th `TIME_STOPS` value added ONLY to the memecoin bucket's grid (270→360 cells, +~1.5 min), or a replacement of one of the existing three values?
   - Recommendation: additive (superset), since it's cheap and doesn't reduce coverage of the existing three variants.
   - **RESOLVED (orchestrator):** Additive, exactly as recommended — the memecoin bucket's grid grows to 360 cells (6x5x3x4), never replacing the base three TIME_STOPS values (see 03-02-PLAN.md Task 2, exit_grid.py's MEMECOIN_SHORT_HOLD_DAYS).

3. **Correlation risk within the stock universe.** Several of the 15 additional names (NVDA, AMD, TSLA, AMZN, META, NFLX, CRM, ADBE) are all AI/growth-tech names that likely moved together during 2023-2024's AI-driven rally.
   - What we know: the momentum/breakout survivors could reflect one correlated cluster's move, not broad-based strategy edge.
   - What's unclear: exact pairwise correlation over the regime windows (not computed in this research pass).
   - Recommendation: report per-symbol P&L contribution for every survivor alongside the aggregate metrics (D-12's report), so a single-cluster-driven "survivor" is visible, not hidden. Full correlation gating remains Phase 4's job (RISK-01), not Phase 3's.
   - **RESOLVED (orchestrator):** Per-symbol P&L is reported alongside aggregates in every sweep summary, exactly as recommended (see 03-06-PLAN.md's sweep_report.write_sweep_summary). Full correlation gating stays out of scope, deferred to Phase 4 (RISK-01).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pandas | Indicator computation | ✓ | 3.0.5 | — |
| numpy | Indicator computation | ✓ | 2.5.1 | — |
| yfinance (via `trader.data.stock_source`) | Stock universe backfill | ✓ | already in use by Phase 1/2 | — |
| ccxt / Binance (via `trader.data.crypto_source`) | Crypto universe backfill | ✓ | already in use by Phase 1/2 | — |
| SQLite (`data/trader.db`) | Ledger writes | ✓ | stdlib `sqlite3` | — |
| pytest | Test suite | ✓ | 150 tests collected, 33.45s full run [VERIFIED] | — |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None — no new dependencies needed this phase.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest [VERIFIED: `pyproject.toml` `[tool.pytest.ini_options] testpaths = ["tests"]`] |
| Config file | `pyproject.toml` |
| Quick run command | `.venv\Scripts\python.exe -m pytest tests/test_strategy_momentum.py tests/test_strategy_breakout.py -q` |
| Full suite command | `.venv\Scripts\python.exe -m pytest -q` — **VERIFIED: 150 passed in 33.45s on this repo, 2026-07-26, before Phase 3 adds any tests** |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|-------------|
| STRAT-01 | Momentum signal fires on RSI+volume-surge+break fixture, stays silent otherwise, never re-picks an open position | unit | `pytest tests/test_strategy_momentum.py -x` | ❌ Wave 0 |
| STRAT-02 | Breakout signal fires on NR7+volume-confirmed break fixture, stays silent on non-contracted ranges | unit | `pytest tests/test_strategy_breakout.py -x` | ❌ Wave 0 |
| STRAT-03 | Sweep grid yields exactly 270 cells (or 360 for the memecoin bucket if Open Question #2 resolves additive); a tiny 2x2x1x1 sweep smoke-runs end-to-end through unmodified `run_backtest` | unit + smoke | `pytest tests/test_sweep_engine.py -x` | ❌ Wave 0 |
| STRAT-04 | Regime windows load from the frozen config, six windows present (2 per bucket), dates match this research doc | unit | `pytest tests/test_regime_config.py -x` | ❌ Wave 0 |
| STRAT-05 | For every regime, tune-end date < OOS-start date (no overlap), and the config file has a fixed pre-sweep freeze point (e.g. a checksum or committed-before-results convention) | unit | `pytest tests/test_regime_config.py -x` | ❌ Wave 0 (same file as STRAT-04) |
| STRAT-06 | `KILL-CONDITIONS.md` exists and contains one entry per reported survivor, each with a concrete numeric trigger | integration/gate | `pytest tests/test_kill_conditions.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** quick run command above (momentum/breakout unit tests, <2s)
- **Per wave merge:** full suite command (`pytest -q`, ~33-40s expected once Phase 3 tests are added)
- **Phase gate:** Full suite green before `/gsd:verify-work`, plus a manual/scripted check that `KILL-CONDITIONS.md` exists and is non-empty if any survivor is reported

### Wave 0 Gaps
- [ ] `tests/test_strategy_momentum.py` — covers STRAT-01, needs a new fixture-bar builder with a controllable volume column (existing `_bars_with_closes` in `test_backtest_strategies.py` fixes volume at a flat 1000.0 — momentum needs a volume-surge fixture variant)
- [ ] `tests/test_strategy_breakout.py` — covers STRAT-02, needs a fixture builder producing a genuine NR7 contraction (narrowing daily ranges) followed by a breakout bar
- [ ] `tests/test_sweep_engine.py` — covers STRAT-03, tiny-grid smoke test asserting cell count and that every cell reaches `ledger.record_run` with the sweep-provenance keys present in `params_json`
- [ ] `tests/test_regime_config.py` — covers STRAT-04/STRAT-05, asserts the six frozen windows match this document's dates and that no tune/OOS pair overlaps
- [ ] `tests/test_kill_conditions.py` — covers STRAT-06, parses `KILL-CONDITIONS.md` structure and asserts one entry per survivor named in the sweep report
- [ ] Framework install: none — pytest already configured and passing (150/150, 33.45s)

## Security Domain

`security_enforcement` is absent from `.planning/config.json`'s workflow block, so treat as enabled per the default-on rule, but this phase's ASVS surface is minimal — pure functions over historical bars, no user input, no network calls beyond the existing (unmodified) Phase 1 data-fetch path, no auth/session concerns.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | no | N/A — no auth surface in this phase |
| V3 Session Management | no | N/A |
| V4 Access Control | no | N/A |
| V5 Input Validation | marginal | Regime/universe config is developer-authored (not user/network input); still validate at load time that tune-end < OOS-start and that grid cell count matches expectation, so a malformed frozen-config file fails loudly rather than silently running a wrong sweep |
| V6 Cryptography | no | N/A — no secrets or crypto handled in this phase (API keys remain Phase 1's `.env` concern, untouched here) |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| Look-ahead bias reintroduced by a new strategy reading beyond `iterator.history()`'s bound (e.g. calling `iterator.bar_on` for a future date) | Tampering (with the honesty guarantee, not an external attacker) | Unit tests must assert a strategy given a truncated history never signals on data it can't see yet — mirrors Phase 2's own threat model (T-02-16/17/18) applied to the new strategy modules |
| Sweep provenance silently missing (a cell's `params_json` lacks `sweep_id`/`regime`/`split`) leading to un-auditable survivor claims | Repudiation | `test_sweep_engine.py` asserts every cell's persisted `params_json` contains the provenance keys before Phase 4 trusts any survivor |

## Sources

### Primary (HIGH confidence — VERIFIED via direct tool execution against this repo)
- `trader/backtest/runner.py`, `iterator.py`, `config.py`, `exits.py`, `fills.py`, `ledger.py`, `metrics.py`, `momentum_placeholder.py`, `sanity_universe.py` — read directly, 2026-07-26
- `migrations/0003_backtest.sql` — schema confirmed, `params_json` unconstrained TEXT
- Live `yfinance.Ticker(...).history(period="max")` calls for 22 stock symbols, this repo's venv, 2026-07-26
- Live `ccxt.binance().fetch_ohlcv(...)` calls for BTC/ETH/DOGE/SHIB/PEPE/BONK/WIF, this repo's venv, 2026-07-26
- Live timed `run_backtest` benchmark against cached `data/trader.db` bars, this repo's venv, 2026-07-26
- `pytest -q` full-suite run against this repo, 150 passed in 33.45s, 2026-07-26
- `pip show pandas numpy` / `import pandas_ta, talib, ta` checks, this repo's venv, 2026-07-26

### Secondary (MEDIUM confidence — WebSearch cross-checked against official announcements)
- [Binance will list Bonk (BONK) with Seed Tag Applied](https://www.binance.com/en/support/announcement/binance-will-list-bonk-bonk-with-seed-tag-applied-1592b7a6ec9a408daf4b778f50ab1ca6) — cross-checked against the live ccxt fetch (2023-12-15), dates match exactly
- [Pepe (PEPE) New Listing on Binance](https://www.coincarp.com/events/pepe-new-listing-on-binance/) — cross-checked against live ccxt fetch (2023-05-05), matches
- [Binance Will List Dogwifhat (WIF) with Seed Tag Applied](https://www.binance.com/en/support/announcement/binance-will-list-dogwifhat-wif-with-seed-tag-applied-90ad67fe5be7483ea058191bfde677e4) — cross-checked against live ccxt fetch (2024-03-05), matches
- [Binance Will List SHIBA INU (SHIB) in the Innovation Zone](https://www.binance.com/en/support/announcement/binance-will-list-shiba-inu-shib-in-the-innovation-zone-f1fe616e688b452f9d736753cb2d947a) — cross-checked against live ccxt fetch (2021-05-10), matches
- [The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality (Bailey & Lopez de Prado)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551) — informs the Overfitting Guards section's proportionality argument
- [NR7 / Narrow Range Day, StockCharts ChartSchool](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/narrow-range-day-nr7) — standard NR7 definition
- [Bollinger Band Width Percentile indicator description, TradingView](https://www.tradingview.com/script/tqitSsyG-Bollinger-Band-Width-Percentile/) — BBWP as a contraction-measure alternative

### Tertiary (LOW confidence — general TA/RSI practice, not independently verified beyond training-data recall, tagged ASSUMED throughout Code Examples)
- General RSI-period/momentum-strategy search results (QuantifiedStrategies.com, LuxAlgo) — used only to corroborate that RSI(14-21) and RVOL-based volume filters are standard practice, not as a source for this phase's exact numeric thresholds

## Metadata

**Confidence breakdown:**
- Engine contracts / long-only constraint / universe data-availability / runtime benchmark: HIGH — all VERIFIED by direct tool execution against this repo
- Regime window boundaries and labels: MEDIUM — underlying return/drawdown numbers VERIFIED; the "trending"/"choppy"/"mania"/"correction" labels and exact split dates are a reasoned judgment call
- Entry-rule parameterisation (RSI thresholds, volume-surge multiplier, NR7/ATR-ratio thresholds): LOW-MEDIUM — informed by the owner's reference specs and general TA practice, not independently back-tested; explicitly tagged ASSUMED and listed for the planner to treat as needing eventual empirical confirmation from the sweep's own results

**Research date:** 2026-07-26
**Valid until:** 2026-08-25 (30 days — stock/crypto history facts are stable; if "today" advances significantly, the memecoin regime-availability argument in A6 should be re-checked, since it depends on elapsed time since listing)
