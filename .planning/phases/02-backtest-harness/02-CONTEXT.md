# Phase 2: Backtest Harness - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning

<domain>
## Phase Boundary

The honest machine: a backtest harness that replays history through a point-in-time bar iterator, applies per-venue fees and asset-class slippage, executes exits through EXIT_PROFILES, records every simulated trade in a ledger, and reports metrics. The exit gate is the sanity test — a known-dumb random strategy MUST lose roughly the fee rate, and one real strategy must run end-to-end producing a metrics report. Strategy development itself is Phase 3; portfolio sizing and risk gating are Phase 4.

</domain>

<decisions>
## Implementation Decisions

Auto-selected recommended defaults (non-interactive session). Override any before `/gsd:plan-phase 2`.

### Data & Point-in-Time Iterator
- **D-01:** The harness consumes Phase 1's `get_daily_bars` cache exclusively — daily bars only. Intraday backtesting is out of scope until the owner buys intraday data (deferred by the phase document).
- **D-02:** The iterator yields bars strictly ≤ current simulation time, per symbol, from a pre-loaded universe. Strategy code receives a view that physically cannot contain future bars (slice, not flag) — lookahead is impossible by construction, not by discipline.
- **D-03:** The simulation clock advances one trading day at a time in UTC calendar dates, matching the Phase 1 bar contract (tz-aware UTC index).

### Intraday Approximation on Daily Bars (honesty rules)
- **D-04:** Fills are conservative by default. Entries fill at next bar's open (never the signal bar's close). A stop is considered hit if the bar's low ≤ stop price; fill price is the stop price or the bar's open if the bar gapped through (whichever is worse for the trader). Take-profits mirror this: high ≥ TP → fill at TP or open-if-gapped-through, whichever is worse.
- **D-05:** If both stop and TP are hit inside the same daily bar, the STOP wins (pessimistic tie-break). This bias understates performance; that is the correct direction for an honest machine.

### Fee Model
- **D-06:** Per-venue static fee table in a config module: IBKR US stocks US$0.005/share with US$1.00 minimum per order (fixed tier); Kraken taker 0.26% (assume taker on every fill — pessimistic); memecoin trades add the slippage class below rather than a separate spread model. Fees are parameters, not hard-coded in engine logic.
- **D-07:** Crypto fees model as Kraken (the trading venue) even though bar data provenance is Binance — decoupling locked in Phase 1.

### Slippage Model
- **D-08:** Percentage penalty per asset class, applied on every fill, both sides: large-cap stock 0.05%, small-cap runner 2% (midpoint of the phase document's 1–3%), memecoin 4% (midpoint of 3–5%). Asset class comes from the instruments table (Phase 1 D-16 tagging). All three are config parameters swept later if needed.

### Exit Engine (EXIT_PROFILES)
- **D-09:** EXIT_PROFILES are frozen dataclasses: stop_pct, tp_pct, scale_out (list of (gain_pct, fraction)), trailing_pct, max_hold_days (time stop), eod_flat (bool). A profile is attached to a position at entry and immutable thereafter (standing rule 2 enforced by the type, not by convention).
- **D-10:** Profile evaluation order within a bar: eod_flat → stop → trailing stop → scale-out/TP → time stop. Documented and tested, since ordering changes results.

### Trade Ledger & Runs
- **D-11:** Backtests write to the shared `data/trader.db`: `backtest_runs` (run_id, started_at, strategy_id, profile, params_json, seed, code_version) and `backtest_trades` (run_id, strategy_id, symbol, asset_class, entry_ts/price, exit_ts/price, qty, fees, slippage, pnl, exit_reason). Every simulated trade is attributable to a run and a strategy.
- **D-12:** Runs are reproducible: RNG seed and parameters stored on the run row; same seed + params + data ⇒ identical ledger.

### Metrics Module
- **D-13:** Metrics per run and per strategy: profit factor, Sharpe (daily returns, rf = 0, annualised √252), max drawdown, win rate, avg win, avg loss, trade count, total fees paid. Output: a dict plus a dated markdown report under `reports/backtests/`.

### Sanity Test (exit gate)
- **D-14:** The random strategy (seeded RNG: buy a random universe symbol, hold one day, repeat) runs as an automated pytest against cached bars. Pass condition: mean per-trade P&L within a tolerance band of −(fees + slippage) — the band and universe are pinned in the test. If it profits, the harness is broken and the test FAILS the suite.
- **D-15:** One real strategy (simplest possible momentum placeholder — not a Phase 3 strategy) runs end-to-end producing the metrics report, proving the full pipe.

### Claude's Discretion
- Module layout under `trader/backtest/`, dataclass vs TypedDict details, report formatting, exact tolerance band derivation for D-14.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and rules
- `# Trader AI — GSD Phases.md` (repo root) — Phase 2 scope, EXIT_PROFILES list, fee/slippage ranges, sanity-test requirement
- `.planning/REQUIREMENTS.md` — BACK-01…07
- `.planning/phases/01-accounts-data-plumbing/01-CONTEXT.md` — Phase 1 decisions the harness inherits (UTC tz-aware bars, venue semantics, asset-class tagging)
- `trader/data/api.py` — get_daily_bars contract (the harness's only data source)
- `trader/data/db.py` — migration mechanism to extend for the new tables

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `get_daily_bars` — cache-first bars with UTC tz-aware index; the iterator wraps this
- `trader/data/db.py` migrations — add 0003 migration for backtest tables
- 53-test suite + conftest fixtures — extend, do not modify conftest

### Established Patterns
- src layout, plain sqlite3 WAL, frozen config constants, RED→GREEN TDD, live smoke exempt from fast-test target

### Integration Points
- Phase 3 strategies will be pure functions over the iterator's bar views
- Phase 4's sizer plugs between signal and fill later — keep the fill path composable

</code_context>

<specifics>
## Specific Ideas

- "Test any strategy against history without lying to yourself" — every default above biases against the trader when ambiguous.
- The sanity test is the phase's soul: "it MUST lose ~fees. If it profits, the harness is broken."

</specifics>

<deferred>
## Deferred Ideas

- Intraday bars / Polygon.io — owner's explicit deferral
- Maker-fee modelling and fee tiers — pessimistic taker-only is fine until live fills exist (Phase 9 compares)
- Monte Carlo / walk-forward tooling — Phase 3 concern if needed
- Portfolio-level position sizing — Phase 4 owns it

</deferred>

---

*Phase: 2-Backtest Harness*
*Context gathered: 2026-07-26*
