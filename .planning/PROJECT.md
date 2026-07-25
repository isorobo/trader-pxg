# Trader AI

## What This Is

An automated trading research and execution system for one operator in New Zealand. It scans US stocks and crypto for momentum candidates, backtests strategies against honest history, paper trades the survivors, and graduates only proven configurations to small real-money probation. The build runs through eleven fixed phases (0–10), each gated by exit criteria.

## Core Value

The system never lies to itself: every strategy must prove its edge on honest data, after fees and slippage, before a single cent is at risk.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Phase 0 — Snapshot logger records what "+400% gainers" resolve to, with daily close reports
- [ ] Phase 1 — Accounts, API access, repo, and data plumbing sorted
- [ ] Phase 2 — Backtest harness with point-in-time data, fee and slippage models, and sanity tests
- [ ] Phase 3 — Strategy lab with out-of-sample validation and pre-registered kill conditions
- [ ] Phase 4 — Risk gate, position sizer, and circuit breakers with unit tests
- [ ] Phase 5 — Full paper trading loop running unattended overnight
- [ ] Phase 6 — Data collection and graduation review against pre-registered criteria
- [ ] Phase 7 — Attribution and tournament layer
- [ ] Phase 8 — Optional signal expansion (only if Phase 6 graduates a strategy)
- [ ] Phase 9 — Real money at probation size with NZD tax ledger
- [ ] Phase 10 — Full size and steady state

### Out of Scope

- Real money before Phase 9 — nothing earlier touches a cent
- API keys with withdrawal permission — trade-only keys, always
- Postgres/Timescale at the start — SQLite until it hurts
- Paid intraday data (Polygon.io) — decide later; daily bars first
- Editing graduation or kill criteria while looking at results — standing rule 1

## Context

- Operator is NZ-based. US market hours run roughly 1:30am–8am NZ time, so the paper and live loops must survive unattended overnight.
- Venues: IBKR (stocks, paper first), Kraken (crypto), Independent Reserve (NZD ramp, Phase 9 only).
- IBKR PDT rule: under US$25k margin allows 3 day trades per 5 days — cash account or crypto-first until then.
- CARF reporting means IRD sees exchange data; the NZD tax ledger must match from live trade #1.
- The full phase document lives at the repo root: "# Trader AI — GSD Phases.md". It is the source of truth for phase scope and exit criteria.

## Constraints

- **Capital**: Real money enters only at Phase 9, at a size whose total loss is acceptable — no negotiating up
- **Security**: API keys never carry withdrawal permission; `.env` never committed
- **Process**: A phase is done when its exit criteria are met, not before; failing forward is prohibited
- **Stack**: Python, git, SQLite to start; free daily bars before any paid data
- **Operations**: If the system and the exchange disagree about a position, the system halts
- **Tax**: NZD tax logging live from the first real trade (timestamp, qty, price, fees, NZD rate)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Phases 0–10 fixed by the owner with hard exit criteria | Prevents skipping ahead and vibes-based progression | — Pending |
| SQLite before Postgres/Timescale | Upgrade only when it hurts; keep plumbing simple | — Pending |
| IBKR paper for stocks, simulated ledger for crypto in Phase 5 | Kraken has no paper environment; simulate honestly | — Pending |
| Pre-registered kill and graduation criteria | Standing rule: never edit criteria while looking at results | — Pending |
| Exit profiles lock at entry | No mid-trade loosening | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 25 July 2026 after initialization*
