# Project State

## Project Reference

See: .planning/PROJECT.md (updated 25 July 2026)

**Core value:** The system never lies to itself — every strategy must prove its edge on honest data before any capital is at risk.
**Current focus:** Phase 0 — Ground Truth (Phase 1 discussed, planning queued)

## Current Position

Phase: 0 of 0–10 (Ground Truth)
Plan: Phases 3 AND 4 CLOSED (verified passed 10/10 and 17/17). FIVE OOS SURVIVORS (momentum/stock/choppy/loose, PF 2.3-20.4). Phase 5 discussion next
Status: Phases 2, 3, 4 closed. Phase 5 (paper loop) opening — execution will checkpoint on user items: Kraken trade-only keys → .env, IBKR Gateway login, Telegram bot token. Phase 0 monitoring to 2026-08-09; Phase 1 accounts UAT open
Last activity: 2026-07-26 — v2: 10,800 runs, 5 survivors, kill conditions registered; Phase 4 safety layer verified

Progress: [█████░░░░░] 47%

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

### Pending Todos

- Phase 3 discussion MUST read `Strategys/` (owner-curated strategy library, added 2026-07-26) as a canonical ref — includes the phase-doc strategies (Momentum, Breakout) plus candidates (Donchian, RSI-2, TS-momentum) for the Phase 7 pipeline. Phase doc precedence rules on any conflict.
- Owner question pending: wire trader-pxg GitHub repo as remote? (currently public — recommend private first)

### Blockers/Concerns

- IBKR and Independent Reserve approvals take days — start applications before build work needs them
- US market hours run ~1:30am–8am NZ time; later phases must run unattended overnight

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-07-26
Stopped at: Phase 0 planned and verified; ready to execute
Resume file: .planning/phases/00-ground-truth/00-01-PLAN.md
