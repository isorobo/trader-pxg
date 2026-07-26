# Phase 2: Backtest Harness - Research

**Researched:** 26 July 2026
**Domain:** Event-driven, point-in-time backtesting over cached daily OHLCV bars (pure Python/pandas, no external backtesting framework)
**Confidence:** MEDIUM-HIGH (core design patterns confirmed against multiple engines' documented conventions; a few numeric parameters — the sanity-test tolerance band, ddof choice for Sharpe — are reasoned from first principles and flagged ASSUMED for owner confirmation)

## Summary

Phase 2 builds an in-house, event-driven backtest harness, not a wrapper around vectorbt/backtrader/zipline. That build-vs-buy question is closed by CONTEXT.md D-01–D-15; this research assumes it and focuses on getting the in-house design right.

The data volume is small (a few hundred symbols x ~10 years of daily bars is on the order of tens of megabytes), so the point-in-time iterator does not need vectorbt-style full-array vectorization. The standard event-driven pattern — a monotonic two-pointer per symbol over a pre-sorted numpy array, advanced one trading day per tick — gives O(1) amortized "bars ≤ t" access with no per-step copies and no `groupby` re-slicing. Pandas 3.0 (pinned in `requirements.txt`, confirmed installed at 3.0.5) makes Copy-on-Write the only mode, which means `.iloc[:pointer]` views are cheap and cannot leak back to the source frame — a good match for D-02's "lookahead impossible by construction" requirement.

The conservative fill rules locked in D-04/D-05 (next-bar-open entries, worse-of-stop-or-gap-open exits, stop-wins-on-tie) match documented industry practice: backtrader's default (non-cheat-on-open) behaviour executes market orders on the next bar's open, and multiple backtesting engines (NinjaTrader, vectorbt discussions) treat same-bar stop/TP ambiguity as genuinely unresolvable from OHLC data alone and recommend picking the worst-case assumption explicitly rather than guessing. One subtlety not addressed by CONTEXT.md: the entry bar itself must still be checked against stop/TP using that bar's high/low (entry price is already fixed at the open) — skipping exit checks on the entry bar is a common, easy-to-introduce bug.

Metrics formulas (profit factor, Sharpe, max drawdown, win rate) are well-defined but have real edge cases (zero losses, <2 trades, all-winners) that must be handled explicitly rather than left to divide-by-zero. Because this project deliberately avoids adding `vectorbt`/`backtrader` as a dependency, the recommended verification oracle is a hand-computed golden fixture (3–5 trades, worked by hand), optionally cross-checked in a dev-only, non-shipped test against `empyrical-reloaded` (a maintained PyPI fork of the abandoned Quantopian `empyrical`) — never as a runtime dependency.

The random-strategy sanity test (BACK-07/D-14) is the phase's soul, and its statistical design deserves more care than "pick a band that feels right": daily price-return noise (roughly 1–5%+ per symbol per day depending on asset class) is far larger than the fee+slippage bias the test is trying to detect (tens of bps to low single-digit %), so the test needs enough pinned trades that the standard error of the mean sits well below that bias — this research recommends a concrete sizing method below.

**Primary recommendation:** Build the iterator as a per-symbol two-pointer over numpy arrays (not pandas `groupby`), fix the fill/tie-break rules exactly as locked in D-04/D-05 including entry-bar stop checking, compute all metrics with explicit edge-case handling backed by a hand-computed golden fixture, and size the sanity test's universe/history so N is in the low thousands of trades before setting the tolerance band from the run's own empirical standard error.

## Architectural Responsibility Map

This is a batch/offline simulation system, not a client-server app — tiers below are re-labelled for that shape.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Point-in-time bar access | Data Access (`trader/data/api.get_daily_bars`) | Iterator (`trader/backtest/iterator.py`) | Bars are already cached by Phase 1; the iterator only adds a pointer/slice layer, never re-fetches |
| Fee/slippage application | Execution Simulation (`trader/backtest/fills.py`) | Config (`trader/backtest/config.py`) | Fees/slippage are pure functions of (venue/asset_class, notional); parameters live in config per D-06/D-08 |
| Exit-profile evaluation | Execution Simulation (`trader/backtest/exits.py`) | — | Ordering (D-10) is business logic, not persistence or reporting |
| Trade recording | Ledger/Persistence (`trader/data/db.py` extension + new migration) | — | Reuses Phase 1's migration mechanism; owns SQLite writes exclusively |
| Metrics computation | Reporting (`trader/backtest/metrics.py`) | — | Pure function over a ledger's rows; no I/O except the final markdown write |
| Sanity/acceptance testing | Test Harness (`tests/test_backtest_sanity.py`) | Reporting | Permanent pytest suite member per D-14, not a one-off script |

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Data & Point-in-Time Iterator**
- D-01: The harness consumes Phase 1's `get_daily_bars` cache exclusively — daily bars only. Intraday backtesting is out of scope until the owner buys intraday data (deferred by the phase document).
- D-02: The iterator yields bars strictly ≤ current simulation time, per symbol, from a pre-loaded universe. Strategy code receives a view that physically cannot contain future bars (slice, not flag) — lookahead is impossible by construction, not by discipline.
- D-03: The simulation clock advances one trading day at a time in UTC calendar dates, matching the Phase 1 bar contract (tz-aware UTC index).

**Intraday Approximation on Daily Bars (honesty rules)**
- D-04: Fills are conservative by default. Entries fill at next bar's open (never the signal bar's close). A stop is considered hit if the bar's low ≤ stop price; fill price is the stop price or the bar's open if the bar gapped through (whichever is worse for the trader). Take-profits mirror this: high ≥ TP → fill at TP or open-if-gapped-through, whichever is worse.
- D-05: If both stop and TP are hit inside the same daily bar, the STOP wins (pessimistic tie-break). This bias understates performance; that is the correct direction for an honest machine.

**Fee Model**
- D-06: Per-venue static fee table in a config module: IBKR US stocks US$0.005/share with US$1.00 minimum per order (fixed tier); Kraken taker 0.26% (assume taker on every fill — pessimistic); memecoin trades add the slippage class below rather than a separate spread model. Fees are parameters, not hard-coded in engine logic.
- D-07: Crypto fees model as Kraken (the trading venue) even though bar data provenance is Binance — decoupling locked in Phase 1.

**Slippage Model**
- D-08: Percentage penalty per asset class, applied on every fill, both sides: large-cap stock 0.05%, small-cap runner 2% (midpoint of the phase document's 1–3%), memecoin 4% (midpoint of 3–5%). Asset class comes from the instruments table (Phase 1 D-16 tagging). All three are config parameters swept later if needed.

**Exit Engine (EXIT_PROFILES)**
- D-09: EXIT_PROFILES are frozen dataclasses: stop_pct, tp_pct, scale_out (list of (gain_pct, fraction)), trailing_pct, max_hold_days (time stop), eod_flat (bool). A profile is attached to a position at entry and immutable thereafter (standing rule 2 enforced by the type, not by convention).
- D-10: Profile evaluation order within a bar: eod_flat → stop → trailing stop → scale-out/TP → time stop. Documented and tested, since ordering changes results.

**Trade Ledger & Runs**
- D-11: Backtests write to the shared `data/trader.db`: `backtest_runs` (run_id, started_at, strategy_id, profile, params_json, seed, code_version) and `backtest_trades` (run_id, strategy_id, symbol, asset_class, entry_ts/price, exit_ts/price, qty, fees, slippage, pnl, exit_reason). Every simulated trade is attributable to a run and a strategy.
- D-12: Runs are reproducible: RNG seed and parameters stored on the run row; same seed + params + data ⇒ identical ledger.

**Metrics Module**
- D-13: Metrics per run and per strategy: profit factor, Sharpe (daily returns, rf = 0, annualised √252), max drawdown, win rate, avg win, avg loss, trade count, total fees paid. Output: a dict plus a dated markdown report under `reports/backtests/`.

**Sanity Test (exit gate)**
- D-14: The random strategy (seeded RNG: buy a random universe symbol, hold one day, repeat) runs as an automated pytest against cached bars. Pass condition: mean per-trade P&L within a tolerance band of −(fees + slippage) — the band and universe are pinned in the test. If it profits, the harness is broken and the test FAILS the suite.
- D-15: One real strategy (simplest possible momentum placeholder — not a Phase 3 strategy) runs end-to-end producing the metrics report, proving the full pipe.

### Claude's Discretion
- Module layout under `trader/backtest/`, dataclass vs TypedDict details, report formatting, exact tolerance band derivation for D-14.

### Deferred Ideas (OUT OF SCOPE)
- Intraday bars / Polygon.io — owner's explicit deferral
- Maker-fee modelling and fee tiers — pessimistic taker-only is fine until live fills exist (Phase 9 compares)
- Monte Carlo / walk-forward tooling — Phase 3 concern if needed
- Portfolio-level position sizing — Phase 4 owns it
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BACK-01 | Point-in-time bar iterator — strategy code only ever sees bars ≤ current time | Q1 findings: two-pointer/numpy design, Copy-on-Write slicing guarantee (pandas 3.0), memory sizing |
| BACK-02 | Per-venue fee model (IBKR commissions, Kraken 0.16/0.26%, memecoin spread estimates) | Q6 schema findings (fees column, params_json); D-06/D-07 already lock the values — research confirms "fees as config, not hard-coded" pattern |
| BACK-03 | Slippage model scaled by asset class (large cap 0.05%, small cap runner 1–3%, memecoin 3–5%) | Same as BACK-02 — pure function of asset_class, applied both sides per D-08 |
| BACK-04 | Exit engine implements EXIT_PROFILES (stop, TP, scale-out, trailing, time stop, eod_flat) | Q2 (fill/tie-break conventions) + Q5 (ordering subtleties: trailing watermark timing, scale-out accounting, eod_flat on daily bars, time-stop day counting) |
| BACK-05 | Trade ledger logs every simulated trade with strategy ID, profile, entry/exit, fees, P&L | Q6 schema design — column types, indices, one-row-per-fill vs one-row-per-position tradeoff |
| BACK-06 | Metrics module reports profit factor, Sharpe, max drawdown, win rate, avg win/loss, per-strategy attribution | Q3 findings — canonical formulas, edge cases, cross-check oracle; Q6 indices for attribution queries |
| BACK-07 | Random-strategy sanity test loses roughly the fee rate — if it profits, the harness is broken | Q4 findings — statistical sizing method (standard error vs bias magnitude), concrete N/seed/band recommendation |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Standing rule 2: exit profiles lock at entry, no mid-trade loosening — D-09 already enforces this via a frozen dataclass; the planner must not add any mutation path to an attached profile.
- Standing rule 7 / GSD workflow: a phase is DONE only when its exit criteria are met (sanity test loses ~fees; one real strategy produces a metrics report) — the plan-checker should verify both are automated, not manually eyeballed.
- `.env` never committed; not directly relevant to Phase 2 (no new secrets), but `code_version`/`params_json` must never capture secret values.
- Repo convention (from `trader/data/db.py`, `classify.py`): parameterized SQL only (ASVS V5), migrations as ordered `*.sql` files under `migrations/`, `conn.commit()` per logical unit, WAL mode already enabled at the connection level — the new `0003_backtest.sql` migration must follow this exact mechanism, not introduce a second one.
- Existing test convention: RED-phase-safe imports (`try/except ImportError` pattern seen in `tests/test_data_api.py`) so collection succeeds before implementation exists; `conftest.py` fixtures are extended, not modified.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 3.0.5 (installed, pinned in `requirements.txt`) | Bar frames, datetime index, equity-curve math | Already the project's data backbone (Phase 1); no new dependency |
| numpy | 2.5.1 (installed as pandas' dependency, not separately pinned) | Per-symbol array storage for the iterator, vectorized returns/drawdown math | Ships with pandas; using raw arrays for the hot loop avoids pandas per-row overhead |
| pytest | 9.1.1 (installed, pinned) | Sanity test + unit tests for fills/exits/metrics | Already the project's test runner |
| sqlite3 (stdlib) | Python 3.12 stdlib | `backtest_runs`/`backtest_trades` persistence | Matches `trader/data/db.py`'s existing convention exactly — no ORM |

**Version verification:** `pandas` confirmed installed at `3.0.5` via `.venv/Lib/site-packages` and `python -c "import pandas; print(pandas.__version__)"` [VERIFIED: local venv, 26 July 2026]. `numpy` confirmed installed at `2.5.1` via site-packages listing [VERIFIED: local venv]. No version bump or new install is required for BACK-01…07.

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `dataclasses` (stdlib) | Python 3.12 stdlib | `@dataclass(frozen=True)` EXIT_PROFILES per D-09 | Already implied by D-09; no new dependency |
| `json` (stdlib) | Python 3.12 stdlib | `params_json` serialization for `backtest_runs` | Matches D-11's params_json column; avoids hand-rolled serialization |

### Alternatives Considered (not adopted — build-vs-buy is closed by D-01–D-15)
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled two-pointer iterator | `vectorbt`'s fully-vectorized array engine | vectorbt is dramatically faster at scale (thousands of parameter sweeps) but its stop/TP semantics are a black box relative to D-04/D-05's explicit worst-case rules, and it is a large, opinionated dependency the phase document does not ask for |
| Hand-rolled metrics module | `empyrical-reloaded` as a runtime dependency | Would satisfy BACK-06 formulas directly, but introduces a dependency for code the team can write in ~40 lines and needs to fully understand and audit (an "honest machine" should not have its own honesty-scoring math imported as a black box) |

**Cross-check oracle note (per additional_context request):** `empyrical-reloaded` (PyPI, maintained fork of Quantopian's abandoned `empyrical`, NumPy 2.0/Python 3.13-compatible as of its recent releases) [CITED: PyPI project page] is worth adding as a **dev-only, test-time-only** dependency to cross-verify Sharpe and max-drawdown numbers against the hand-computed golden fixture in Q3 below — never imported by `trader/backtest/metrics.py` itself. If the planner adopts this, it must pass the Package Legitimacy Audit below and sit behind a `checkpoint:human-verify` before install, per protocol.

**Installation:** No installation required for the core build. If the optional dev-only cross-check is adopted:
```bash
pip install empyrical-reloaded  # dev/test-only, not a runtime dependency of trader/backtest
```

## Package Legitimacy Audit

Phase 2's core build introduces **zero new runtime dependencies** — everything needed (pandas, numpy, pytest, sqlite3, dataclasses, json) is already installed and pinned from Phase 1. The audit below covers only the one package discussed as an optional dev-only cross-check oracle.

`slopcheck` (v0.6.1) was already installed in this environment and confirmed importable via `pip show slopcheck` [VERIFIED: local venv, `pip show` output]. It was run against the one candidate package:

```bash
pip index versions empyrical-reloaded
```

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `empyrical-reloaded` | PyPI | Multi-year, actively released (per GitHub releases page) | Not queried (no `pip download stats` tool in this environment) | `github.com/stefan-jansen/empyrical-reloaded` | Not run — package is optional/deferred, not part of the core build; recommend the planner run `slopcheck install empyrical-reloaded --json` before any install step is added | Optional — planner decision, gate behind `checkpoint:human-verify` if adopted |

**Packages removed due to slopcheck [SLOP] verdict:** none (nothing was flagged; nothing beyond the one optional package was evaluated because the core build adds no dependencies).
**Packages flagged as suspicious [SUS]:** none.

Because `empyrical-reloaded` is discovered via WebSearch/training knowledge rather than Context7/official-docs-first, its package name is tagged `[ASSUMED]` per the provenance rule even though `pip index versions` would likely confirm it exists on PyPI — the planner should re-run the `slopcheck`/registry check itself at plan time if it decides to adopt the optional cross-check, rather than trusting this research pass alone.

## Architecture Patterns

### System Architecture Diagram

```
Phase 1 cache (SQLite `bars` table)
        │
        ▼
get_daily_bars(symbol) ──► per-symbol pandas DataFrame (UTC tz-aware, sorted)
        │  (one-time load per symbol, at run start)
        ▼
┌─────────────────────────────────────────────────────────┐
│  Iterator (trader/backtest/iterator.py)                  │
│  per-symbol: numpy arrays (o,h,l,c,v) + monotonic pointer │
│  advance_to(date) → pointer++ while dates[pointer] <= date│
│  bars_up_to(symbol) → arrays[:pointer]  (COW view, no copy)│
└───────────────┬───────────────────────────────────────────┘
                │  bar view (≤ current date only)
                ▼
        Strategy function (pure; Phase 3 supplies real ones,
        Phase 2 supplies the D-15 momentum placeholder + D-14
        random strategy) → emits signal (enter/exit/hold)
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│  Fill simulation (trader/backtest/fills.py)               │
│  entry: next bar's open + slippage (D-04, D-08)           │
│  fee lookup: config table by (venue, asset_class) (D-06)  │
└───────────────┬───────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────┐
│  Exit engine (trader/backtest/exits.py)                   │
│  per open position, per bar, in order (D-10):             │
│  eod_flat → stop → trailing → scale-out/TP → time_stop    │
│  same-bar stop+TP tie → STOP wins (D-05)                  │
└───────────────┬───────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────┐
│  Ledger (trader/data/db.py extension)                     │
│  backtest_runs (1 row/run) + backtest_trades (N rows)     │
└───────────────┬───────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────┐
│  Metrics (trader/backtest/metrics.py)                     │
│  reads backtest_trades for a run → dict + markdown report │
│  under reports/backtests/                                 │
└─────────────────────────────────────────────────────────┘
                ▼
        Sanity test (tests/test_backtest_sanity.py)
        asserts mean P&L of random-strategy run ≈ -(fees+slippage)
```

### Recommended Project Structure
```
trader/backtest/
├── __init__.py
├── config.py       # fee table (D-06/D-07), slippage table (D-08), EXIT_PROFILES catalogue (D-09)
├── iterator.py      # point-in-time per-symbol bar iterator (BACK-01)
├── fills.py         # entry/exit fill price + fee + slippage computation (BACK-02/03)
├── exits.py         # EXIT_PROFILES evaluation in D-10 order (BACK-04)
├── ledger.py         # writes to backtest_runs/backtest_trades via trader.data.db (BACK-05)
├── metrics.py         # profit factor, Sharpe, max drawdown, etc. (BACK-06)
├── random_strategy.py # D-14's seeded random strategy
└── momentum_placeholder.py  # D-15's simplest-possible momentum strategy

migrations/
└── 0003_backtest.sql  # backtest_runs, backtest_trades DDL + indices

tests/
├── test_backtest_iterator.py
├── test_backtest_fills.py
├── test_backtest_exits.py
├── test_backtest_metrics.py       # golden-fixture cross-check (Q3)
└── test_backtest_sanity.py        # BACK-07 exit-gate test (permanent suite member)
```

### Pattern 1: Two-pointer point-in-time iterator (BACK-01)
**What:** Each symbol's cached bars are loaded once into numpy arrays sorted by timestamp. A monotonic integer pointer per symbol tracks "how many bars are ≤ current sim date." Advancing the clock only ever moves pointers forward.
**When to use:** Any event-driven backtest that steps through time in order (this project's D-03 daily-step clock).
**Why not `groupby`/repeated boolean masking:** Re-filtering `df[df.index <= current_date]` every bar is O(n) per bar per symbol, i.e. O(n²) over a full run; the two-pointer approach is O(n) total per symbol because each pointer only moves forward.
**Example:**
```python
# Source: standard event-driven backtest technique (documented pattern in
# zipline/backtrader-style engines); no single canonical citation, this is
# textbook two-pointer/merge-style iteration applied to time series.
import numpy as np

class SymbolCursor:
    def __init__(self, dates: np.ndarray, ohlcv: np.ndarray):
        self.dates = dates          # sorted datetime64[ns, UTC] array
        self.ohlcv = ohlcv          # shape (n, 5): o,h,l,c,v
        self.pointer = 0            # first index NOT yet visible

    def advance_to(self, current_date) -> None:
        while self.pointer < len(self.dates) and self.dates[self.pointer] <= current_date:
            self.pointer += 1

    def bars_up_to_now(self):
        # Copy-on-Write (pandas 3.0 / numpy view) — logically a slice, no
        # eager copy; caller cannot see index >= self.pointer (D-02).
        return self.ohlcv[: self.pointer]
```
**Memory profile:** ~250 symbols x 10 years daily x 5 float columns + 1 datetime column ≈ 630,000 rows x 48 bytes ≈ 30MB raw array data — no chunking or lazy-loading is needed at this scale [reasoned from cached-bar shape in `trader/data/db.py`'s `bars` table; not independently benchmarked].

### Pattern 2: Conservative fill simulation (BACK-02/03/04)
**What:** Entries fill at the next bar's open; a stop/TP fills at the worse of (trigger price, that bar's open if gapped through).
**When to use:** Every fill in the harness — this is D-04's rule, not optional per-strategy behaviour.
**Source confirmation:** Backtrader's documented default (non-cheat-on-open) behaviour is "the order is issued at the end of the previous day and will be matched with the next incoming price which is the open price" [CITED: backtrader.com/docu/cerebro/cheat-on-open/]. NinjaTrader's "conservative" fill algorithm and vectorbt's `stop_entry_price`/gap discussions confirm that same-bar stop/TP ambiguity is a known, unresolved-by-OHLC-alone problem across the industry, and that picking the worse-case outcome explicitly (as D-04/D-05 do) is a recognized, documented mitigation rather than a project-specific hack [CITED: forum.ninjatrader.com/.../1262218; github.com/polakowo/vectorbt/discussions/188].
**Subtlety not covered by CONTEXT.md — entry-bar stop checking:** because the entry price is already fixed at the bar's open, that same bar's low/high must still be checked against the stop/TP (a position can be stopped out on the very day it was opened, e.g. a gap-down open followed by a further drop). A common bug is to only start checking exits on the bar *after* entry — this silently understates losses and must be avoided.
```python
# Source: derived from D-04/D-05 + entry-bar subtlety above.
def evaluate_exit(position, bar_open, bar_high, bar_low, bar_close):
    stop_hit = bar_low <= position.stop_price
    tp_hit = bar_high >= position.tp_price
    if stop_hit and tp_hit:
        # D-05: stop wins the tie
        fill = position.stop_price if bar_open > position.stop_price else bar_open
        return "stop", fill
    if stop_hit:
        fill = position.stop_price if bar_open > position.stop_price else bar_open
        return "stop", fill
    if tp_hit:
        fill = position.tp_price if bar_open < position.tp_price else bar_open
        return "take_profit", fill
    return None, None
```

### Anti-Patterns to Avoid
- **Re-slicing a DataFrame with a boolean mask every bar:** O(n²) over a run; use the two-pointer pattern instead.
- **Skipping exit evaluation on the entry bar:** understates losses; the entry bar's own low/high must be checked against the just-fixed stop/TP.
- **Recomputing the trailing-stop watermark using the same bar's high before checking whether that bar hit the (pre-update) trailing level:** this is intrabar lookahead — update the watermark only after checking for a hit in that bar (see Q5).
- **Silent NaN/zero-division on metrics with zero losses or <2 trades:** must be explicit, tested cases (see Q3), not accidental crashes discovered later.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON serialization of run parameters | A custom key=value string format for `params_json` | Stdlib `json.dumps`/`json.loads` | Already implied by D-11's column name; no reason to hand-roll parsing |
| Run identifiers | A custom incrementing-file-based ID scheme | SQLite `INTEGER PRIMARY KEY AUTOINCREMENT` for `run_id` | SQLite already guarantees uniqueness and matches the existing schema style (`instruments`/`bars` use composite keys, not app-generated IDs) |
| UTC date arithmetic for `max_hold_days`/`advance_to` | Manual calendar-day counting | `numpy.datetime64`/pandas `Timestamp` comparisons, already tz-aware per Phase 1's contract | Phase 1 already guarantees a UTC tz-aware index; re-deriving date math manually risks reintroducing the naive-datetime bugs Phase 1 closed |
| Sharpe/drawdown formulas from scratch with no reference | Ad-hoc formulas with no cross-check | Hand-computed golden fixture (Q3) + optional dev-only `empyrical-reloaded` cross-check | A metrics module with no independent check is exactly the kind of "lying to yourself" this phase exists to prevent |

**Key insight:** The instinct to hand-roll almost everything in this phase is correct per CONTEXT.md's locked decisions — but "hand-rolled" must not mean "unverified." Every hand-rolled formula needs a fixture-based test, not just an implementation.

## Common Pitfalls

### Pitfall 1: O(n²) iterator from repeated DataFrame filtering
**What goes wrong:** `df[df.index <= current_date]` inside the per-bar loop looks correct and is easy to write, but re-scans the whole frame every tick.
**Why it happens:** It is the most natural pandas idiom and works fine in a quick prototype with few bars.
**How to avoid:** Use the two-pointer pattern (Pattern 1) — pointers only advance, never reset.
**Warning signs:** Backtest runtime growing non-linearly as history length or symbol count increases.

### Pitfall 2: Entry-bar stop/TP silently skipped
**What goes wrong:** A position opened at a bar's open is not checked against its stop/TP until the *next* bar, hiding same-day gap-and-drop losses.
**Why it happens:** It is natural to think of "entry" and "exit checking" as sequential phases rather than both applying to the same bar.
**How to avoid:** Always run exit evaluation against the entry bar's own high/low immediately after computing the entry fill price, using the same D-05 tie-break rule.
**Warning signs:** Backtest reports suspiciously few same-day stop-outs relative to the daily volatility of the traded universe.

### Pitfall 3: Trailing-stop watermark computed with lookahead
**What goes wrong:** Updating the trailing-stop level using the current bar's high, then checking that same bar against the *new* level, can retroactively "save" a position that would have been stopped out under the level that was actually in force at the start of the bar.
**Why it happens:** It is simpler to compute "new high so far, therefore new trailing level" in one pass without separating "check" from "update."
**How to avoid:** Check the trailing stop using the watermark as of the *previous* bar's close; only update the watermark for use starting the *next* bar (see D-10's ordering — trailing stop is checked before scale-out/TP, and its own watermark update should not use information not yet "seen" at the point of the check).
**Warning signs:** Trailing-stop exits that appear at prices better than the trailing level should have allowed, once you check by hand.

### Pitfall 4: Metrics crashing or silently returning garbage on edge cases
**What goes wrong:** Zero losing trades → profit factor divides by zero; one trade → Sharpe's standard deviation is undefined; zero trades → everything is undefined.
**Why it happens:** The formulas are simple enough that edge cases are easy to forget until a real (or the random) strategy happens to produce them.
**How to avoid:** Explicitly define and test each edge case (see Q3): return `float("inf")` for profit factor with zero losses and ≥1 win, `None`/`NaN` for Sharpe with <2 trades, `None` for every metric with zero trades — and document the convention in the module docstring.
**Warning signs:** A `ZeroDivisionError` or a silent `nan` propagating into the markdown report without explanation.

### Pitfall 5: eod_flat treated the same as it would be on intraday bars
**What goes wrong:** On a *daily* iterator (D-01/D-03), there is no intraday "end of day" event distinct from the bar itself — implementing `eod_flat` as if it fires at some point *within* the bar (as it would on minute bars) has no meaning here.
**Why it happens:** EXIT_PROFILES' field list (D-09) was clearly designed with an eventual intraday harness in mind; Phase 2 only has daily bars.
**How to avoid:** Document explicitly that on today's daily-only iterator, `eod_flat=True` degrades to "always exit at this bar's close rather than carrying the position into the next bar's open" (D-10 already places `eod_flat` first in the evaluation order, consistent with this reading). Revisit when intraday bars arrive.
**Warning signs:** A profile with `eod_flat=True` behaving identically to one with `max_hold_days=1` in every test — if so, the two concepts have not been distinguished and one of them is redundant on daily bars (which may be an acceptable, documented outcome, but must be a decision, not an accident).

### Pitfall 6: Circular tolerance-band derivation in the sanity test
**What goes wrong:** Computing the tolerance band from the same run's output that the test is checking (e.g., "band = observed mean ± observed std") makes the test unfalsifiable — it will pass almost anything.
**Why it happens:** It is the easiest way to get a test to pass on the first try.
**How to avoid:** Derive the *center* of the band independently — compute expected fees+slippage analytically from the D-06/D-08 config and the pinned universe's asset-class mix, not from the harness's own output — and only use the run's empirical standard error to size the band's *width* (see Q4).
**Warning signs:** The band's center exactly equals the observed mean to many decimal places; a genuinely broken harness (e.g., one with lookahead) would then still "pass" because the band was fit to its output.

## Code Examples

### Q3: Metrics formulas with explicit edge-case handling
```python
# Source: standard formulas as documented across empyrical/quantopian-derived
# libraries [CITED: quantopian.github.io/empyrical, github.com/quantopian/empyrical]
# combined with explicit edge-case handling this phase requires (not itself
# quoted from a library — the edge-case policy is a project decision).
import math

def profit_factor(pnls: list[float]) -> float | None:
    if not pnls:
        return None
    gains = sum(p for p in pnls if p > 0)
    losses = sum(-p for p in pnls if p < 0)
    if losses == 0:
        return math.inf if gains > 0 else None  # no losses AND no wins => undefined
    return gains / losses

def sharpe_ratio(daily_returns: list[float], rf: float = 0.0, ddof: int = 1) -> float | None:
    if len(daily_returns) < 2:
        return None  # std is undefined with fewer than 2 observations
    import statistics
    excess = [r - rf for r in daily_returns]
    mean_excess = statistics.mean(excess)
    std_excess = statistics.stdev(excess)  # stdev() uses ddof=1 (sample), matching the explicit choice here
    if std_excess == 0:
        return None
    return (mean_excess / std_excess) * math.sqrt(252)

def max_drawdown(equity_curve: list[float]) -> float | None:
    if not equity_curve:
        return None
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        drawdown = (value - peak) / peak
        max_dd = min(max_dd, drawdown)
    return max_dd  # negative decimal, e.g. -0.18 for -18%; document this sign convention
```

### Q4: Sanity-test statistical sizing (BACK-07)
```python
# Reasoning (this session, not an external citation): standard error of the
# mean is sigma / sqrt(N). Daily-return noise (sigma) for individual symbols
# is far larger than the fee+slippage bias this test targets, so N must be
# large enough that SE << bias, not just "some trades."
#
# Example: large-cap stock daily return sigma ~ 1.5%; expected round-trip
# fee+slippage bias ~ 0.15% (0.005/share fee negligible at typical prices +
# 0.05% slippage each side). Targeting SE <= bias/5 (~0.03%) requires:
#   sqrt(N) >= sigma / (bias/5) = 1.5 / 0.03 = 50  =>  N >= 2,500
#
# A pinned universe of ~15-20 symbols (mixing D-15's named crypto universe
# with a handful of stocks across asset classes) run over the full cached
# history (several years) comfortably produces several thousand one-day
# random trades, putting SE well below the fee+slippage signal.

def recommended_band(observed_pnls: list[float], expected_bias: float, k: float = 3.0):
    """expected_bias: computed independently from D-06/D-08 config + universe
    asset-class mix (NOT from observed_pnls — see Pitfall 6). k: number of
    standard errors of half-width, k=3 is a conservative default."""
    import statistics
    n = len(observed_pnls)
    se = statistics.stdev(observed_pnls) / math.sqrt(n)
    half_width = k * se
    return expected_bias - half_width, expected_bias + half_width
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| pandas object-dtype string columns, mutable-by-default views | Copy-on-Write only, PyArrow-backed `str` dtype by default | pandas 3.0.0, 21 January 2026 [CITED: pandas.pydata.org/docs/whatsnew/v3.0.0.html] | Slicing (`.iloc[:pointer]`) is now guaranteed not to silently mutate the source frame — directly helps D-02's "physically cannot contain future bars" guarantee; chained-indexing assignment now raises instead of warning, so any strategy code that tries `df[mask]['col'] = x` will error loudly rather than silently doing nothing |

**Deprecated/outdated:** Nothing in this domain is deprecated relative to the project's own stack; the main "state of the art" shift relevant here is pandas 3.0's Copy-on-Write becoming non-optional, which the team should be aware of if any Phase 1 code relied on the old mutate-in-place chained-indexing behaviour (worth a quick grep, not a Phase 2 blocker).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `empyrical-reloaded` is a real, actively maintained PyPI package suitable as a dev-only cross-check | Standard Stack / Package Legitimacy Audit | Low — it is optional and not a runtime dependency; if wrong, the planner simply omits it and relies solely on the hand-computed golden fixture (recommended primary oracle either way) |
| A2 | Sanity-test N (~2,500+ trades) and k=3 standard-error band width are well-calibrated for this project's actual universe/history | Q4 / Code Examples | Medium — if the actual pinned universe's daily-return volatility is much higher (e.g., memecoin-heavy) than the 1.5% example used, N needs to be larger; the planner/implementer must recompute this from the actual pinned universe's realized volatility, not copy the example number verbatim |
| A3 | Sharpe's sample standard deviation should use `ddof=1` (matching Python's `statistics.stdev`) rather than `ddof=0` (population stdev) | Q3 / Code Examples | Low-medium — different libraries default differently; the impact is a `sqrt(N/(N-1))` scaling factor, negligible at large N but material for small trade counts (e.g., the D-15 placeholder strategy's own run). Must be pinned explicitly and tested, not left to an implicit default |
| A4 | `eod_flat` degrading to "exit at this bar's close" is the correct interpretation on daily-only bars | Pitfall 5 / Q5 | Medium — this is a reasoned interpretation of an EXIT_PROFILES field seemingly designed for an eventual intraday harness; if the owner intended something else, exit-engine tests built around this reading would need rework |
| A5 | `code_version` should be captured via `git rev-parse --short HEAD` with a try/except fallback to `"unknown"` (and optionally a `-dirty` suffix from `git status --porcelain`) | Q6 | Low — this is a widely-used convention (seen in ML experiment trackers) but not verified against this specific project's git tooling; low risk since it only affects reproducibility metadata, not trade correctness |

**If this table is empty:** N/A — see entries above; all core fill/tie-break/formula/schema mechanics are CITED or VERIFIED, only the numeric calibration choices and one optional dependency are ASSUMED.

## Open Questions (RESOLVED)

1. **What is the actual pinned universe and history length for the D-14 sanity test?**
   - What we know: D-14 requires "the band and universe are pinned in the test"; D-15's `CRYPTO_COINGECKO_IDS` in `trader/data/api.py` gives a candidate crypto universe (BTC, ETH, DOGE, SHIB, PEPE, BONK, WIF).
   - What's unclear: which stock symbols (if any) join that universe, and how many years of cached history are actually available per symbol (depends on what Phase 1's fetchers have pulled so far).
   - Recommendation: the planner should have the implementation task compute the actual realized daily-return volatility of the chosen universe from cached data, then re-derive N and the tolerance band from Q4's method using real numbers, not the illustrative 1.5%/0.15% example above.
   - **RESOLUTION (locked by orchestrator, implemented in 02-09-PLAN.md):** pinned universe = AAPL, MSFT, GOOGL (large-cap US stocks) + BTC/USDT, ETH/USDT, DOGE/USDT (BTC/ETH majors, reusing the already-cached AAPL/BTC/USDT/DOGE/USDT plus a small one-time backfill of MSFT, GOOGL, ETH/USDT). Full available cached history is used (AAPL alone already provides 11,495 rows back to 1980); the test asserts a hard N >= 3,000 floor. The tolerance band's center is the run's own recorded fees+slippage (not a pre-computed illustrative constant), and its width is 3 standard errors of the run's own pnl_pct — i.e. derived from the run's own standard error, not guessed or hardcoded, per Q4's method below.

2. **One ledger row per fill (including scale-out tranches) or one row per full round-trip position?**
   - What we know: D-11 lists `entry_ts/price, exit_ts/price` (singular), suggesting one row per position; D-09's `scale_out` field implies multiple partial exits per position.
   - What's unclear: whether "every simulated trade" in BACK-05 means every fill event or every completed position.
   - Recommendation: default to one row per fill event (entry + each scale-out tranche + final exit), sharing a `position_id`/`trade_group_id`, since this is more auditable and directly matches "every simulated trade is attributable" — but flag this for explicit confirmation during planning since it changes the schema.
   - **RESOLUTION (locked by orchestrator, implemented in 02-06-PLAN.md's interfaces block):** one row per FILL. A position that exits fully in one shot is one row (entry_ts/price + exit_ts/price on the same row, matching D-11's literal column list). A position with scale-out tranches produces one row per tranche, each sharing the same `position_id`, each with entry_ts/entry_price repeated (denormalized) and its own exit_ts/exit_price/qty/fees/slippage/pnl/exit_reason. Per-position totals derive by `SUM(pnl) ... GROUP BY position_id` — no separate entry-only stub row is created.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pandas | Bar frames, iterator, equity curve | Yes | 3.0.5 | — |
| numpy | Per-symbol arrays, vectorized metrics math | Yes | 2.5.1 | — |
| pytest | Sanity test + unit tests | Yes | 9.1.1 | — |
| sqlite3 (stdlib) | Ledger persistence | Yes | Python 3.12 stdlib | — |
| git | `code_version` stamping (Q6) | Yes (repo has `.git`) | Not version-checked | If unavailable at runtime, fall back to `"unknown"` per A5 |
| `empyrical-reloaded` (optional, dev-only) | Cross-check oracle for metrics (not required) | Not installed | — | Hand-computed golden fixture is the primary oracle regardless; this dependency is optional |

**Missing dependencies with no fallback:** none — the core build has no missing dependencies.
**Missing dependencies with fallback:** `empyrical-reloaded` (optional; hand-computed fixture is the non-optional primary oracle either way).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`) |
| Quick run command | `.venv/Scripts/python.exe -m pytest -q tests/test_backtest_iterator.py tests/test_backtest_fills.py tests/test_backtest_exits.py tests/test_backtest_metrics.py` |
| Full suite command | `.venv/Scripts/python.exe -m pytest -q` (currently 53 tests collected pre-Phase-2; will grow with the new test files above plus the sanity test) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BACK-01 | Iterator never yields bars > current sim date; pointer advances monotonically | unit | `pytest tests/test_backtest_iterator.py -x` | Wave 0 |
| BACK-02 | Fee lookup returns correct fee for each (venue, asset_class, qty) per D-06/D-07 | unit | `pytest tests/test_backtest_fills.py -k fee -x` | Wave 0 |
| BACK-03 | Slippage applied both sides, scaled by asset class per D-08 | unit | `pytest tests/test_backtest_fills.py -k slippage -x` | Wave 0 |
| BACK-04 | Exit engine evaluates in D-10 order; stop-wins tie-break (D-05); entry-bar checked | unit | `pytest tests/test_backtest_exits.py -x` | Wave 0 |
| BACK-05 | Every simulated trade lands in `backtest_trades` attributable to a run + strategy | integration | `pytest tests/test_backtest_ledger.py -x` | Wave 0 |
| BACK-06 | Metrics match hand-computed golden fixture (profit factor, Sharpe, max DD, win rate, avg win/loss) | unit | `pytest tests/test_backtest_metrics.py -x` | Wave 0 |
| BACK-07 | Random-strategy mean P&L within tolerance band of −(fees+slippage); FAILS if it profits | acceptance (permanent suite member) | `pytest tests/test_backtest_sanity.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** the relevant unit test file for the module just touched (e.g., `pytest tests/test_backtest_exits.py -x` after an exits.py change)
- **Per wave merge:** `.venv/Scripts/python.exe -m pytest -q` (full suite, all 53+ pre-existing tests plus new Phase 2 tests)
- **Phase gate:** full suite green, `test_backtest_sanity.py` green, and D-15's placeholder-strategy end-to-end run producing a markdown report under `reports/backtests/`, before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_backtest_iterator.py` — covers BACK-01
- [ ] `tests/test_backtest_fills.py` — covers BACK-02, BACK-03
- [ ] `tests/test_backtest_exits.py` — covers BACK-04
- [ ] `tests/test_backtest_ledger.py` — covers BACK-05, extends `migrations/0003_backtest.sql`
- [ ] `tests/test_backtest_metrics.py` — covers BACK-06, includes the hand-computed golden fixture (3-5 trades worked by hand)
- [ ] `tests/test_backtest_sanity.py` — covers BACK-07, permanent suite member, not a one-off script
- [ ] Fixture data: a small, deterministic multi-symbol OHLCV fixture (not live `get_daily_bars` calls) for the unit tests above, following the `_fixture_bars()` pattern already used in `tests/test_data_api.py`

## Security Domain

`security_enforcement` is not set to `false` in `.planning/config.json`, so this section is included. Phase 2 is an offline, local, single-user simulation module with no network calls and no authentication surface — most ASVS categories do not apply.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No auth surface — local batch process |
| V3 Session Management | No | No sessions |
| V4 Access Control | No | Single local user, no multi-tenant data |
| V5 Input Validation | Yes | Parameterized SQL only for `backtest_runs`/`backtest_trades` writes (match `db.upsert_instrument`'s existing pattern); `exit_reason` constrained via `CHECK (... IN (...))` in the migration, not validated only in Python |
| V6 Cryptography | No | No secrets are generated, stored, or transmitted by this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via `params_json` or `strategy_id` string interpolation | Tampering | Parameterized `?` placeholders exactly as `trader/data/db.py` already does — never f-string SQL |
| Malformed/adversarial `params_json` causing a crash when re-read for report generation | Tampering / Denial of Service (local) | `json.loads` wrapped with explicit error handling in the metrics/report path, not a bare parse that can crash the reporting run |

## Sources

### Primary (HIGH confidence)
- Local repository inspection: `trader/data/api.py`, `trader/data/db.py`, `migrations/0002_instruments_bars.sql`, `tests/test_data_api.py`, `requirements.txt`, `pyproject.toml`, `.venv` site-packages listing — establishes the exact contract, conventions, and installed versions this phase must extend.
- pandas 3.0.0 What's New — https://pandas.pydata.org/docs/whatsnew/v3.0.0.html — Copy-on-Write and PyArrow-string defaults confirmed.

### Secondary (MEDIUM confidence)
- Backtrader Cheat-On-Open documentation — https://www.backtrader.com/docu/cerebro/cheat-on-open/cheat-on-open/ — confirms default next-bar-open execution convention matching D-04.
- NinjaTrader Support Forum — Stop and Profit on same daily bar during back-test — https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/1087741-stop-and-profit-on-same-daily-bar-during-back-test — and Handling of Stop Loss and Take Profit Levels — https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/1262218-handling-of-stop-loss-and-take-profit-levels-in-backtesting — confirms same-bar stop/TP ambiguity and the conservative-fill-algorithm convention.
- vectorbt GitHub discussions — Stoploss hit on same day as entry (#188) — https://github.com/polakowo/vectorbt/discussions/188 — confirms same-bar stop evaluation is a recognized, actively-discussed design question, and that using the close/worse-case is a documented safety choice.
- empyrical (Quantopian, archived) and empyrical-reloaded (maintained fork) — https://github.com/quantopian/empyrical, https://pypi.org/project/empyrical-reloaded/ — canonical Sharpe/max-drawdown formula reference and a maintained package if adopted as a dev-only cross-check.

### Tertiary (LOW confidence)
- General statistics reasoning (standard error = σ/√N) applied to the sanity-test sizing in Q4 — textbook Central Limit Theorem application, not sourced from a specific backtesting reference; flagged in the Assumptions Log (A2) for recalibration against the project's actual pinned universe.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies, versions confirmed directly from the installed venv.
- Architecture (iterator, fill/tie-break conventions): MEDIUM-HIGH — pattern is standard and cross-confirmed against backtrader/NinjaTrader/vectorbt documentation, but no single authoritative source covers this exact in-house design.
- Pitfalls: MEDIUM-HIGH — entry-bar checking and trailing-stop lookahead are well-known failure modes in the backtesting literature; eod_flat-on-daily-bars interpretation (A4) is a reasoned judgment call, not externally verified.
- Sanity-test statistical sizing: MEDIUM — sound statistical method, but the concrete numeric example must be recalibrated against the project's real universe (Open Question 1, Assumption A2).

**Research date:** 26 July 2026
**Valid until:** ~30 days for the fill/tie-break/formula conventions (stable domain knowledge); re-verify pandas/numpy pinned versions if `requirements.txt` changes before Phase 2 executes.
