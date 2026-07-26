# Phase 4: Risk Gate & Sizer - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning

<domain>
## Phase Boundary

The safety layer, built before anything can trade: a risk gate that deletes unsafe candidates (illiquid, too new, correlated), a position sizer enforcing the phase document's hard caps, and circuit breakers that halt trading on loss limits. Exit gate: a poisoned candidate list is filtered correctly, breakers fire correctly in simulation, and unit tests cover all of it. Pure code — no live trading, no network. Runs in parallel with Phase 3 v2 (this layer does not depend on which strategies survive).

</domain>

<decisions>
## Implementation Decisions

Auto-selected recommended defaults under the owner's standing full-auto directive. Override any before planning. All numeric thresholds below are pre-registered defaults — Phases 5–6 may recalibrate them only via pre-registered change, never mid-trade.

### Risk Gate
- **D-01:** Pure function: `apply_risk_gate(candidates, market_data, config) -> (accepted, rejected)` where every rejection carries a machine-readable reason code. Thresholds live in a frozen-style config module, not inline.
- **D-02:** Gate checks per phase doc: minimum liquidity (stocks: trailing-20-day median dollar volume floor; crypto: trailing-7-day median quote volume floor — researcher pins defaults), minimum listing age (default 30 days of bars), maximum spread (static per-asset-class estimates for now — live spread checks are a Phase 5 concern, noted explicitly), pairwise correlation check (trailing 60-day daily-return correlation; if a pair exceeds 0.8, reject the lower-scored candidate), and asset-class classification → EXIT_PROFILE tag via the existing instruments table.

### Position Sizer
- **D-03:** Pure function over (scored candidates, current equity, open positions): top-3 concurrent positions cap; score × inverse-volatility weighting; 50% single-position cap; 10% total memecoin cap; 10% cash reserve always held back. All from the phase document verbatim; deterministic and unit-testable.

### Circuit Breakers
- **D-04:** Breaker state machine persisted in the shared DB (new migration): daily-loss breaker (default −3% of equity in a day → halt new entries until next session), drawdown breaker (default −10% from equity high-water mark → halt everything + `manual_restart_required` flag cleared only by explicit human command), consecutive-loss breaker (default 6 consecutive losing closed trades → halt entries). Breakers fire in simulation via the Phase 2 harness in tests.
- **D-05:** Breaker checks are pure functions over ledger/equity series; persistence layer thin. If the system and any external state ever disagree, halt (standing rule 4 baked into the state machine's design).

### Reference & Scope
- **D-06:** `Strategys/13_risk_management_overlay.md` is the owner's reference doc; the phase document wins on conflict. The gate/sizer consume candidate scores from any strategy (Phase 3 v1/v2 survivors or future Phase 7 entrants) — no coupling to specific strategies.
- **D-07:** Exit-gate acceptance test: a committed poisoned candidate list (illiquid stock, 5-day-old token, correlated pair, oversized memecoin allocation) must produce exactly the expected rejections with correct reason codes.

### Claude's Discretion
- Module layout under `trader/risk/`, exact reason-code enum, breaker table DDL, correlation computation details.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `# Trader AI — GSD Phases.md` (repo root) — Phase 4 scope and caps (top-3, 50%, 10% memecoin, 10% cash)
- `.planning/REQUIREMENTS.md` — RISK-01…04
- `Strategys/13_risk_management_overlay.md` — owner's risk overlay reference (phase doc wins)
- `trader/data/db.py` + `migrations/` — migration mechanism for the breaker state table
- `trader/data/api.py` — bars access for volume/correlation/volatility inputs
- `trader/backtest/config.py` — EXIT_PROFILE contract the gate tags candidates with

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- instruments table (asset-class tags), bars cache (volume/returns inputs), Phase 2 harness (breaker simulation in tests), 217-test suite conventions

### Established Patterns
- Pure functions + frozen config + TDD; reason-coded rejections mirror the gate philosophy; migrations numbered (next: 0004)

### Integration Points
- Phase 5's paper loop wires scanner → gate → ranker → sizer → execution; breakers guard that loop
- Phase 3 survivors' EXIT_PROFILEs attach at entry via the gate's tagging

</code_context>

<specifics>
## Specific Ideas

- "This is the code that must never be wrong" — highest test bar in the project so far; property-style tests welcome (caps never exceeded under any input).
- Poisoned-list test is the phase's soul, mirroring Phase 2's sanity gate.

</specifics>

<deferred>
## Deferred Ideas

- Live spread measurement — Phase 5 (needs quotes)
- Threshold recalibration from paper data — Phase 6, pre-registered changes only
- Portfolio-level VaR/exposure analytics — Phase 7 dashboards if wanted

</deferred>

---

*Phase: 4-Risk Gate & Sizer*
*Context gathered: 2026-07-26*
