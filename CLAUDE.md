# Trader AI

<!-- GSD:project-start source:PROJECT.md -->
## Project

An automated trading research and execution system for one NZ-based operator. Eleven fixed phases (0–10) run from free data logging through backtesting, paper trading, and graduation review to small real-money probation. Full context: `.planning/PROJECT.md`. Phase source of truth: `# Trader AI — GSD Phases.md` at the repo root.

**Core value:** The system never lies to itself — every strategy must prove its edge on honest data, after fees and slippage, before any capital is at risk.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->
## Technology Stack

Python, git, SQLite to start. Free daily bars before paid data. Upgrade to Postgres/Timescale only when SQLite hurts. Stack details will firm up during Phase 1.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

## Standing Rules (all phases — non-negotiable)

1. Never edit graduation/kill criteria while looking at results.
2. Exit profiles lock at entry — no mid-trade loosening.
3. API keys never get withdrawal permissions. `.env` is never committed.
4. If the system and the exchange disagree about a position, the system halts.
5. "It'll probably be fine" = it goes back a phase.
6. Real money is Phase 9. Nothing before it touches a cent.
7. A phase is DONE when its exit criteria are met, not before.

<!-- GSD:workflow-start -->
## GSD Workflow

This project uses GSD. State lives in `.planning/`. Typical loop per phase:

1. `/gsd:discuss-phase N` — gather context, settle gray areas → `.planning/phases/NN/CONTEXT.md`
2. `/gsd:plan-phase N` — research and plan → `.planning/phases/NN/*-PLAN.md`
3. `/gsd:execute-phase N` — execute with atomic commits
4. Verify against the phase's exit criteria before marking DONE

Use TDD while executing. Run verification before reporting any phase complete.
<!-- GSD:workflow-end -->
