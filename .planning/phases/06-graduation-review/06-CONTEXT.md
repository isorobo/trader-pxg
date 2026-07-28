# Phase 6: Data Collection & Graduation Review - Context

**Gathered:** 2026-07-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Accumulate enough paper trades to judge (≥50 closed per strategy), review
weekly against pre-registered criteria only, and graduate or kill. The BUILD
half of this phase is small: a graduation checklist evaluator that runs the
five pre-registered checks mechanically, plus the weekly review artifact.
The RUNTIME half (1–3 months of unattended paper trading) cannot start until
the 05-08 ops checkpoint closes (IBKR paper user + Gateway on 4002).

Exit gate (phase doc verbatim): at least one strategy passes ALL graduation
checks. If none do after 3 months, iterate in Phase 3 — that outcome is the
system working, not failing.

</domain>

<decisions>
## Implementation Decisions

Auto-selected defaults under the owner's standing full-auto directive.
Override any before planning.

### Graduation Checklist (pre-registered, phase doc verbatim)
- **D-01:** The five checks are frozen as code constants, hash-gated like the
  tournament thresholds (standing rule 1):
  1. Profit factor > 1.3 after fees/slippage
  2. Max drawdown < 15%
  3. Profitable in ≥ 2 market conditions
  4. No single trade > 40% of total profit
  5. Still positive with fills assumed 1% worse
- **D-02:** ≥50 closed paper trades per strategy before any graduation
  evaluation (phase doc). Distinct from the tournament's 30-trade judging
  minimum — both windows co-exist; graduation is the stricter, later gate.
- **D-03:** "Profitable in ≥2 market conditions" is measured against the
  frozen regimes_v2 windows mapped onto live-paper trade dates: a strategy's
  closed trades are bucketed by the regime active at exit date, and per-bucket
  P&L must be positive in at least two buckets. If live dates fall outside
  every frozen v2 window, bucket by simple market condition (SPY above/below
  its 50-day mean) — a pre-registered fallback, never a judgment call at
  review time.
- **D-04:** "Fills assumed 1% worse": recompute total P&L with each trade's
  entry raised 1% and exit lowered 1% (long-only), fees unchanged. Positive
  total = pass.

### Review Cadence & Artifacts
- **D-05:** Weekly, folded into the tournament's Sunday slot: the graduation
  evaluator runs immediately after the tournament run in the same
  `run_tournament --once` invocation (one scheduled task, no new schtasks
  line). It writes its own markdown section into the tournament report
  directory and appends a `graduation_reviews` audit row.
- **D-06:** Kill conditions stay the guardian's job (already live, every
  tick). The graduation evaluator never re-implements kills — it only reads
  `strategy_kill_state` to report them (standing rule: kill = immediate, no
  appeals; graduation review is a separate, slower gate).

### Integration
- **D-07:** Evaluator reads paper_trades/strategy_registry/backtest machinery
  read-only (D-02 attribution discipline). Its verdicts are advisory records
  for the OWNER — graduation to Phase 9 real money is a human decision made
  on the evaluator's report, never an automated state change.

### Claude's Discretion
- Module layout (`trader/graduation/` vs `trader/tournament/graduation.py`),
  report formatting, migration numbering (0007) for the audit table.

</decisions>

<canonical_refs>
## Canonical References

- `# Trader AI — GSD Phases.md` — Phase 6 checklist verbatim
- `.planning/phases/03-strategy-lab/KILL-CONDITIONS.md`
- `trader/backtest/metrics.py`, `regimes_v2.py` (frozen) — math and windows
- `trader/tournament/` — judge/report conventions to mirror
- `reports/attribution/` dashboards — the review's supporting evidence

</canonical_refs>

<deferred>
## Deferred Ideas

- Automated graduation → Phase 9 sizing handoff — Phase 9 territory, human
  decision only
- New entrants' graduation — same evaluator applies automatically once
  Phase 8 entrants exist

</deferred>

---

*Phase: 6-Data Collection & Graduation Review*
*Context gathered: 2026-07-29 (auto-defaults; runtime blocked on 05-08 ops checkpoint)*
