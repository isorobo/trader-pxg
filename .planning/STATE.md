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
- Donchian entrant (Strategys/10) built up to the Phase 8 gate: frozen sys1/sys2 variants, evidence driver (sweep_id=donchian_v1, 1,080 tune runs + OOS, checkpoint-resumable), human-only register CLI requiring --i-confirm-phase6-graduated. Evidence sweep launched 2026-07-29
- D-01 gap closed: daily report now regenerates the attribution dashboard (never-fail)
- Phase 0 poller: task healthy (result 0, 15-min repeat); low daily poll counts are machine-uptime gaps, not a poller fault
- GitHub remote: blocked, no gh CLI installed. Owner action: flip trader-pxg private in the web UI, then git remote add origin <url> && git push -u origin master

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
| Ops | Weekly tournament schtasks registration | Folded into 05-09 batch | 2026-07-28 |

## Session Continuity

Last session: 2026-07-28
Stopped at: Phase 7 executed and verified (572 tests); owner audit of the fixture decision record is the remaining exit check
Resume file: .planning/phases/07-attribution-tournament/07-VALIDATION.md
