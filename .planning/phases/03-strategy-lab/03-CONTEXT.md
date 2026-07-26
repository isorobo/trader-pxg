# Phase 3: Strategy Lab - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Backtest everything; keep survivors, kill the rest cheaply. Implement the two phase-document agents (Momentum: RSI + volume surge; Breakout: 20-day high after volatility contraction) as pure functions over Phase 2's iterator, sweep exit parameters per asset class, test across two regimes, validate out-of-sample, and pre-register a kill condition for every surviving config before Phase 4. Exit gate: 2–3 strategy + exit-profile configs profitable out-of-sample after fees/slippage — OR the honest finding that nothing survives, which loops back here, never forward.

</domain>

<decisions>
## Implementation Decisions

Auto-selected recommended defaults (owner's standing auto-advance directive). Override any before planning.

### Strategy Scope (phase-doc precedence)
- **D-01:** Phase 3 implements exactly the two phase-document agents: Momentum (RSI + volume surge) and Breakout (20-day high after volatility contraction). The owner's `Strategys/` library files `07_momentum_trading.md` and `03_breakout_trading.md` serve as reference specs for rule details; where library and phase document differ, the phase document wins.
- **D-02:** The library's other mechanical candidates (10 Donchian, 11 RSI-2, 12 TS-momentum) are NOT Phase 3 scope — they enter later through the Phase 7 pipeline like everyone else. `13_risk_management_overlay.md` informs Phase 4, not here.
- **D-03:** Strategies are pure functions matching Phase 2's `pick_entries(iterator, date, open_positions, rng)` convention — no state outside the ledger, no network, deterministic given bars + seed.

### Backtest Universe
- **D-04:** Fixed liquid universe for Phase 3 sweeps (the Phase 0 scanner has only collected since 2026-07-26 — too young to replay). Stocks: the sanity trio (AAPL, MSFT, GOOGL) plus a researcher-confirmed list of ~15–20 liquid mid/large caps with 10+ years of bars. Crypto: BTC/USDT, ETH/USDT + the named memecoin universe (DOGE, SHIB, PEPE, BONK, WIF vs USDT) as available on Binance history.
- **D-05:** Honesty caveat recorded now: this fixed universe is NOT the live scanner universe and carries survivorship bias — acceptable for killing bad configs cheaply, and flagged so Phase 6 judges paper results (scanner-fed) as the real test. When Phase 0's data matures, scanner-replay backtests become possible; deferred, not forgotten.

### Exit-Parameter Sweep
- **D-06:** Grid per phase document: stop −5% to −30% (step 5), TP +20% to +100% (step 20), trailing variants (off, 10%, 20%), time stop (off, 10, 30 days). Swept per asset class; memecoins additionally test eod_flat-style short holds. Grid definition frozen in code before any results are viewed.
- **D-07:** Every sweep cell runs through Phase 2's `run_backtest` unchanged — no bypassing fills/slippage/fees. Runs are seeded and ledgered; sweep results derive only from `backtest_trades` + `compute_metrics`.

### Regimes & Out-of-Sample
- **D-08:** Two regimes minimum per asset class, chosen by the researcher from data (e.g. a trending year and a choppy/bear year for stocks and crypto separately) and FROZEN before sweeps run.
- **D-09:** Out-of-sample rule: tune on period A, validate on period B that tuning never saw. Split dates frozen in a committed config file before the first sweep executes. A config "survives" only if profitable in B after costs.
- **D-10:** Selection discipline: from the tune-period sweep, at most the top 5 configs per strategy/asset class advance to OOS validation (pre-registered rule — prevents cherry-picking the OOS winner from hundreds of cells).

### Kill Conditions (standing rule 1)
- **D-11:** Every surviving config gets a pre-registered kill condition written to `.planning/phases/03-strategy-lab/KILL-CONDITIONS.md` BEFORE Phase 4 starts: concrete triggers (e.g. rolling-30-trade profit factor < 0.9; drawdown > X%; N consecutive losses) with numbers fixed per config. The file is committed and never edited while looking at live/paper results.

### Reporting
- **D-12:** Sweep outputs: a per-strategy/asset-class markdown summary under `reports/backtests/` (top configs, tune vs OOS metrics side by side) plus the survivors list. "Nothing survived" is a first-class, reportable outcome.

### Claude's Discretion
- RSI period/thresholds and volume-surge definition details (informed by library file 07), volatility-contraction measure for breakout (file 03), sweep parallelisation/runtime management, report formatting.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and rules
- `# Trader AI — GSD Phases.md` (repo root) — Phase 3 scope, sweep ranges, OOS rule, kill-condition requirement
- `.planning/REQUIREMENTS.md` — STRAT-01…06
- `Strategys/07_momentum_trading.md` and `Strategys/03_breakout_trading.md` — owner's reference specs for the two agents (phase doc wins on conflict)
- `Strategys/00_README.md` — library framing; win rates are priors, not promises

### Engine contracts (do not modify, only consume)
- `trader/backtest/runner.py` — run_backtest
- `trader/backtest/iterator.py` — PointInTimeIterator (+ .symbols)
- `trader/backtest/config.py` — EXIT_PROFILE, FEES, SLIPPAGE_PCT (and the SLIPPAGE_SMALL_CAP_RUNNER hook — Phase 3 decides per-trade application for scanner-style runners)
- `trader/backtest/metrics.py`, `trader/backtest/ledger.py`
- `trader/data/api.py` — get_daily_bars for universe backfill

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Full honest harness (150 tests): iterator, fills, exits, ledger, metrics, runner — Phase 3 writes strategies + sweep orchestration only
- momentum_placeholder.py — deliberately naive; Phase 3's real momentum agent replaces its logic, not its interface

### Established Patterns
- Pure-function strategies, RED→GREEN TDD, seeded reproducibility, config frozen before results, reports under reports/backtests/

### Integration Points
- Survivors + KILL-CONDITIONS.md feed Phase 4's gate/sizer and Phase 6's graduation review

</code_context>

<specifics>
## Specific Ideas

- "Kill the rest cheaply" — sweep breadth matters less than honest OOS discipline; the pre-registered top-5 rule is the anti-cherry-pick mechanism.
- "If NOTHING survives — that's a valid, cheap result. Go back to Phase 3, not forward."

</specifics>

<deferred>
## Deferred Ideas

- Donchian / RSI-2 / TS-momentum agents — Phase 7 pipeline entries (library files 10–12)
- Scanner-replay backtesting — once Phase 0 has months of data
- Walk-forward/Monte Carlo tooling — only if simple A/B OOS proves insufficient
- Risk overlay (library file 13) — Phase 4 input

</deferred>

---

*Phase: 3-Strategy Lab*
*Context gathered: 2026-07-26*
