# Phase 5: Paper Trading Loop - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning

<domain>
## Phase Boundary

The full pipeline running live on fake money: scanner → risk gate → ranker → sizer → paper execution on schedule, with a guardian executing exits per profile, idempotent orders, 60-second reconciliation, a real-format ledger, Telegram alerts, and unattended overnight operation through US market hours (~1:30am–8am NZ). Stocks trade against the IBKR paper account; crypto trades against a simulated ledger fed by live prices. Exit gate: two consecutive weeks unattended, zero manual interventions, zero unexplained state divergences.

</domain>

<decisions>
## Implementation Decisions

Auto-selected defaults under the owner's full-auto directive. Override any before planning.

### What Trades
- **D-01:** The five verified v2 survivors deploy (momentum_stock / choppy_v2 / loose entry variant, five exit-profile configs), each tagged with its own EXIT_PROFILE from its surviving config, locked at entry (standing rule 2). Kill conditions from KILL-CONDITIONS.md are LIVE: the loop evaluates them on rolling paper results and auto-retires a strategy that trips one (standing rule: immediately, no appeals).
- **D-02:** Stocks only for strategy entries in this first paper deployment (all survivors are stock configs). The crypto simulated-ledger leg still ships and is exercised by the guardian/reconciliation machinery (so the plumbing is proven), but no crypto strategy trades until one graduates through the Phase 7 pipeline.

### Execution Legs
- **D-03:** Stocks: IBKR paper account via the current maintained Python API library (researcher pins: ib_async vs ib_insync successor state) connecting through IB Gateway in paper mode. Gateway install + login is a HUMAN checkpoint (owner has paper account DUR285675).
- **D-04:** Crypto: simulated ledger — fills modelled from live prices with Phase 2's fee/slippage config (Kraken taker + per-class slippage). No Kraken order API calls in Phase 5 at all; Kraken keys are wired read-only for price/balance sanity only if present.

### Loop Architecture
- **D-05:** Windows Task Scheduler tasks (the proven Phase 0 pattern), not a daemon: an entry pipeline run once per trading day shortly after US open (daily-bar strategies decide on yesterday's close, enter at open per the Phase 2 fill convention), and a guardian task every 5 minutes during US market hours (+ 24/7 for the crypto sim) that checks stops/TPs/trails/time-stops and executes exits.
- **D-06:** Idempotency: every order carries a deterministic client order ID derived from (strategy_id, symbol, date, side, intent); resubmission after a crash can never double-order (pinned by tests).
- **D-07:** Reconciliation every 60s while the guardian runs: internal state vs IBKR paper state. ANY unexplained divergence → halt entries + Telegram alert + `manual_restart_required` (standing rule 4, wired through Phase 4's breakers).
- **D-08:** Phase 4 gate/sizer/breakers are mandatory in-line stages — no bypass path exists in the code.

### State & Ledger
- **D-09:** Migration 0005: `paper_orders`, `paper_positions`, `paper_trades` (real-trade format: strategy_id, profile, entry/exit ts+price, qty, fees, slippage, NZD-ready columns), `reconciliation_log`. Same shared DB, WAL.
- **D-10:** The ledger is written exactly as a real one would be (phase doc requirement) — Phase 9's tax logger extends, never rewrites.

### Alerts & Ops
- **D-11:** Telegram bot (token via .env, HUMAN checkpoint): fills, stops, breaker trips, reconciliation failures, and a twice-daily heartbeat. Alert failure never blocks trading logic (fire-and-forget with local log fallback).
- **D-12:** Every run appends to a rotating operations log; the daily report gains a paper-trading section (positions, P&L, breaker state, coverage of scheduled runs) so the two-week unattended window is auditable from disk.

### Claude's Discretion
- Module layout under `trader/paper/`, exact scheduler cadences within the decisions above, retry/backoff details, log formats.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `# Trader AI — GSD Phases.md` (repo root) — Phase 5 scope + exit criteria
- `.planning/REQUIREMENTS.md` — PAPER-01…07
- `.planning/phases/03-strategy-lab/KILL-CONDITIONS.md` — the five survivors' live kill triggers
- `reports/backtests/oos_results_v2.json` + `tune_top5_v2.json` — survivor configs (exit profiles, variants)
- `trader/risk/gate.py`, `sizer.py`, `breakers.py`, `config.py` — mandatory pipeline stages
- `trader/backtest/config.py` — fee/slippage for the crypto sim leg
- `trader/data/api.py` — bars; `trader/ground_truth/` — scanner sources + Task Scheduler pattern
- `Strategys/13_risk_management_overlay.md` — owner risk reference

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 0's Task Scheduler + .bat pattern (proven unattended); Phase 4 safety stack; Phase 2 fill conventions for the sim leg; 347-test suite

### Established Patterns
- Pure logic + thin persistence, reason codes, TDD, frozen configs, no secrets in logs

### Integration Points
- Phase 6 reads paper_trades for graduation review; Phase 7 tournament reads per-strategy attribution; Phase 9 extends the ledger with NZD tax columns

</code_context>

<specifics>
## Specific Ideas

- "It must survive without you" — the two-week clock only counts unattended operation; any manual intervention resets nothing but must be logged and explained.
- Idempotent orders "even on paper — build the habit now" (phase doc verbatim).

</specifics>

<deferred>
## Deferred Ideas

- Crypto strategy deployment — via Phase 7 pipeline graduation
- Kraken live order API — Phase 9
- Intraday strategy support — needs paid intraday data (owner-deferred)
- Web dashboard — Phase 7 (simple HTML acceptable there)

</deferred>

---

*Phase: 5-Paper Trading Loop*
*Context gathered: 2026-07-26*
