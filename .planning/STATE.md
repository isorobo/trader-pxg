# Project State

## Project Reference

See: .planning/PROJECT.md (updated 25 July 2026)

**Core value:** The system never lies to itself — every strategy must prove its edge on honest data before any capital is at risk.
**Current focus:** Phase 7 — Attribution & Tournament (built, owner audit pending) alongside Phase 0 monitoring

## Current Position

Phase: 7 of 0–10 (Attribution & Tournament) — BUILT, owner audit pending
Plan: Phase 7 executed 2026-07-28 (plans 07-01/07-02, waves 1–6, 572 tests green). Registry-backed live configs (D-08), D-07 entrant pipeline, weekly judge with frozen rules (hash d5df6e82...), attribution dashboards, weekly scheduler artifacts (registration deferred to 05-09 batch)
Status: Phases 2-4 closed; Phase 5 built (511→572 tests). Ops checkpoint: Telegram VERIFIED (2026-07-27); IBKR account APPROVED (2026-07-28, portal greets "Katherine Gaines" — owner to confirm number matches U27412777), next: fund → create paper user (~24h provisioning) → Gateway Paper Log In on 4002 → run one entry+guardian pass to close 05-08. Phase 0 monitoring to 2026-08-09. Phase 7 exit gate: owner audit of reports/tournament/fixture-demo/2026-07-28-run1.md + frozen-threshold review (floors 0.0/0.0, K=4 — one sanctioned adjustment allowed before first real run)
Last activity: 2026-07-29 — Autonomous work session (owner directive: everything possible without the Gateway):
- Phase 6 BUILD half done: graduation evaluator (5 frozen checks, hash-gated, advisory verdicts) folded into the weekly tournament invocation; migration 0007; 06-CONTEXT/06-01-PLAN written. Runtime half awaits 05-08
- Donchian entrant (Strategys/10) built up to the Phase 8 gate: frozen sys1/sys2 variants, evidence driver (sweep_id=donchian_v1), human-only register CLI requiring --i-confirm-phase6-graduated. Evidence sweep COMPLETE 2026-07-29: 1,080/1,080 tune runs + 10 OOS runs, EIGHT OOS SURVIVORS (7 sys1 + 1 sys2; choppy_v2 PF 2.9-11.9, trending_v2 PF 1.1-2.0), payloads with derived kill triggers in reports/backtests/donchian_evidence.json (local artifact, reports/ gitignored). Registration command documented in the evidence file, gated on Phase 6 graduation
- D-01 gap closed: daily report now regenerates the attribution dashboard (never-fail)
- Phase 0 poller: task healthy (result 0, 15-min repeat); low daily poll counts are machine-uptime gaps, not a poller fault
- GitHub: LIVE at github.com/isorobo/trader-pxg (owner chose public), branch renamed master→main, full history pushed 2026-07-29
- Weekly tournament task REGISTERED ("TraderAITournament", Sunday 15:00 NZ) and dry-run verified end to end against the real DB (runs 1-2: 5 holds, dashboard + graduation report + Telegram). Dry run caught+fixed a real bug: ops_log rejected entry_type 'tournament' (now 'scheduled_run')
- RSI-2 entrant (Strategys/11) evidence COMPLETE 2026-07-29: 1,080 tune + 10 OOS runs, FIVE OOS SURVIVORS (all choppy_v2, hold30, PF 4.0-4.6, Sharpe 3.0-3.3, n=75); trending_v2 all insufficient_sample (8-12 trades). Payloads in reports/backtests/rsi2_evidence.json, same Phase 8 gate
- TS-momentum (Strategys/12) deferred with reasoning (see Deferred Items)
- IBKR: account U27412777 FUNDED; paper user DUR380571 created (NZD 1,000,000 simulated) and Gateway LIVE on 4002
- 05-08 OPS CHECKPOINT CLOSED (2026-07-30): live verification passed — reconcile 0 divergences/no halt; entry pipeline 0 candidates (honest zero, no signal); guardian 0 positions. Three real-Gateway bugs found+fixed at the checkpoint (missing connect() in reconcile.main; no disconnect in any CLI main; unbounded reqOpenOrders hang on fresh paper accounts — now 15s-bounded). ALL FIVE scheduled tasks registered and Ready: GroundTruthPoll, PaperEntry (01:45), PaperGuardian (5-min), PaperReconcile (1-min), AITournament (Sun 15:00). THE SYSTEM NOW TRADES PAPER UNATTENDED; the Phase 6 graduation clock starts at the first live-paper fill
- Note for owner: paper account holds NZD 1,000,000; sizing uses the frozen PAPER_ACCOUNT_EQUITY=100,000 constant — deliberately conservative, weights are computed against 100k regardless of broker equity. Revisit only as a deliberate decision, never mid-flight

2026-07-30 (late session, owner directive: full-auto, "use a mix of all of them"):
- MULTI-SIGNAL LIVE BOOK: each live family scans its OWN frozen signal (signals.py routing, migration 0008 entry_variant, sorted-family dedupe, within-family profile assignment). 621→631 tests
- ENTRANTS ADMITTED per frozen rules: Donchian sys1 choppy (OOS PF 11.9) → PROBATION at 25% size (run 3 'enter' decision, roster at cap 6); RSI-2 connors5 (OOS PF 4.6) → QUEUED candidate, first in line when a retirement opens a slot. Owner approval quoted verbatim in the transition audit trail
- Donchian CRYPTO/MEMECOIN evidence: 2,520 tune + 10 OOS runs — ZERO survivors (PF 0.56-0.74 OOS, all killed). Honest result; no crypto entrant queued
- MA-crossover entrant built (20/50 EMA + 50/200 SMA cross events, frozen+gated); 3,600-run all-bucket evidence sweep launched 2026-07-30 late — results to be read next session if not this one
- Crypto paper-leg: PLAN drafted (.planning/phases/08-signal-expansion/CRYPTO-PAPER-LEG-PLAN.md), deliberately NOT armed — no crypto survivor exists and arming a second live leg unreviewed violates standing rule 5. Owner reviews before build
- Elimination cadence unchanged and pre-registered: kills immediate (guardian), sustained-worst full-state demotion after 4 consecutive weekly evals, graduation checklist at 50 trades. NOT re-tuned to "2 months" — standing rule 1

Progress: [██████░░░░] 64%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: -
- Total execution time: -

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: -
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Init]: Phases 0–10 fixed by the owner; exit criteria gate every transition
- [Init]: SQLite before Postgres; free daily bars before paid data
- [Init]: API keys trade-only, never withdrawal-enabled
- [Phase 7]: Incumbent five configs grandfathered at state='full' in strategy_registry (behaviour of live paper trading unchanged); a changed config is a NEW entrant
- [Phase 7]: Tournament thresholds frozen behind trader/tournament/freeze_gate.py (D-06); owner may make ONE reviewed adjustment before the first real run

### Pending Todos

- Owner: audit reports/tournament/fixture-demo/2026-07-28-run1.md (Phase 7 exit gate) and review frozen floors (0.0/0.0, K=4)
- 05-09 go-live batch gains one line: `schtasks /Create /TN "TraderAI Tournament" /XML scripts\tournament_run_task.xml`
- Phase 8 entrants queue: Strategys/ files 10–12 (Donchian, RSI-2, TS-momentum) enter via pipeline.register_candidate once their signal code exists
- Owner question pending: wire trader-pxg GitHub repo as remote? (currently public — recommend private first)

### Blockers/Concerns

- IBKR and Independent Reserve approvals take days — start applications before build work needs them
- US market hours run ~1:30am–8am NZ time; later phases must run unattended overnight
- Judging-Sharpe comparability: metrics.py 0-fills no-trade days, understating variance for low-frequency strategies; PF tie-break partially compensates (pre-registered in frozen_config.py docstring)

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Strategy | TS-momentum entrant (Strategys/12) | Deferred: a monthly-rebalance portfolio backbone with no stops — does not map to the daily entry-signal + exit-grid engine; forcing it through would test something other than the published strategy. Needs its own engine shape, designed properly in Phase 8 | 2026-07-29 |
| Ops | ~~Weekly tournament schtasks registration~~ | DONE 2026-07-29: task "TraderAITournament" registered (Sunday 15:00 NZ) and dry-run verified end to end against the real DB | 2026-07-28 |

## Session Continuity

Last session: 2026-07-28
Stopped at: Phase 7 executed and verified (572 tests); owner audit of the fixture decision record is the remaining exit check
Resume file: .planning/phases/07-attribution-tournament/07-VALIDATION.md

2026-07-30 (final autonomous wrap-up):
- Crypto paper leg BUILT + ARMED per the owner-accepted plan: crypto_entry_pipeline (daily incl weekends, sim fills, shared budget, probation sizing, graceful skip until a crypto survivor exists), TraderCryptoEntry task registered (12:10 NZ daily), supervised first run = clean skip. signals.py now routes base_bucket generically; rsi2 pre-registered stock-only per its spec. 635 tests
- MA-crossover evidence COMPLETE: 3,600 tune + 10 OOS runs. FIVE stock survivors (fast_ema_20_50 choppy_v2, PF 3.9-4.75, n=33); golden_sma_50_200 trending all insufficient_sample (10-11 trades); NO crypto/memecoin candidate reached OOS (tune 30-trade floor) -- crypto leg stays dormant, honestly
- Best MA-cross survivor (Sharpe 2.14) REGISTERED as candidate; entrant queue is now RSI-2 then MA-cross, both waiting on a roster slot (cap 6). Four strategy families total: momentum (5 full), donchian (probation 25%), rsi2 (queued), macross (queued)
- SIX scheduled tasks Ready: GroundTruthPoll, PaperEntry, CryptoEntry, PaperGuardian, PaperReconcile, AITournament
- Remaining gates need TIME (Phase 6: 1-3 months of trades) or MONEY (Phase 9-10: owner only). Nothing else is buildable without results accumulating

2026-08-02: Owner-requested 2h task pause (2026-08-01 22:45) silently became ~22h -- the 00:45 re-enable one-shot lacked StartWhenAvailable and the machine was off at its trigger time. Zero trading impact (market closed throughout) but the Sunday 15:00 tournament was missed; run 4 executed manually at ~21:00 on owner resume order (8 holds, no admissions, reports + Telegram sent). Lesson recorded: any future pause one-shot gets StartWhenAvailable + the resume is verified, not assumed. All six tasks re-enabled and Ready; owner directive: run continuously until told otherwise.
