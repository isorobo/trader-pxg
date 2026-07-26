# Roadmap: Trader AI

## Overview

The journey runs from free data collection to full-size automated trading in eleven fixed phases. Phase 0 starts logging ground truth today and never stops. Phases 1–4 build the plumbing, the honest backtest harness, the strategy lab, and the safety layer. Phases 5–7 run the full pipeline on paper and judge it against pre-registered criteria. Phase 8 expands signals only on a proven foundation. Real money enters at Phase 9 at probation size, and Phase 10 reaches steady state. A phase is DONE when its exit criteria are met — no skipping ahead, and nothing before Phase 9 touches a cent.

## Phases

**Phase Numbering:**
- Integer phases (0–10): Planned milestone work, fixed by the owner
- Decimal phases (e.g. 2.1): Urgent insertions (marked with INSERTED)

- [ ] **Phase 0: Ground Truth** - Snapshot logger for gainers; runs in background forever
- [ ] **Phase 1: Accounts & Data Plumbing** - All access sorted before it is needed
- [x] **Phase 2: Backtest Harness** (completed 2026-07-26) - The honest machine: point-in-time data, fees, slippage, sanity tests
- [x] **Phase 3: Strategy Lab** (completed 2026-07-26 — 5 survivors via pre-registered v2) - Backtest everything; keep survivors, kill the rest cheaply
- [x] **Phase 4: Risk Gate & Sizer** (completed 2026-07-26) - The safety layer, built before anything can trade
- [ ] **Phase 5: Paper Trading Loop** - Full pipeline live on fake money, unattended overnight
- [ ] **Phase 6: Graduation Review** - Accumulate paper trades; judge against pre-registered criteria
- [ ] **Phase 7: Attribution & Tournament** - The self-improvement loop, built while Phase 6 collects data
- [ ] **Phase 8: Signal Expansion** - More signal sources, only if Phase 6 graduated something
- [ ] **Phase 9: Real Money Probation** - First live capital, sized so total loss is fine
- [ ] **Phase 10: Full Size & Steady State** - Promote survivors; monthly review cadence

## Phase Details

### Phase 0: Ground Truth
**Goal**: Find out what the "+400% gainers" actually resolve to, with real numbers.
**Depends on**: Nothing (starts today, runs forever)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04
**Success Criteria** (what must be TRUE):
  1. The scanner logs every flagged ticker with timestamp, price, and % gain to SQLite
  2. A daily report answers: of everything flagged this week, what % ended the day up vs dumped?
  3. The logger has run for two weeks minimum and keeps running
**Plans**: 5 plans

Plans:
- [x] 00-01-PLAN.md — Repo skeleton, pinned deps, .env + CoinGecko demo key
- [x] 00-02-PLAN.md — Snapshot schema (db.py) + stock/crypto source adapters (sources.py)
- [x] 00-03-PLAN.md — Poll orchestration (poll.py) + Task Scheduler registration
- [x] 00-04-PLAN.md — Daily report generator (report.py)
- [x] 00-05-PLAN.md — Live end-to-end verification + two-week monitoring checkpoint

### Phase 1: Accounts & Data Plumbing
**Goal**: All access sorted before it is needed — brokers, exchanges, data, repo, database.
**Depends on**: Nothing (runs in parallel with Phase 0; approvals take days, start early)
**Requirements**: ACCT-01, ACCT-02, ACCT-03, ACCT-04, ACCT-05, ACCT-06, ACCT-07
**Success Criteria** (what must be TRUE):
  1. Historical daily bars for any US stock and any major crypto pair come back with one function call
  2. IBKR paper account, Kraken API keys (trade-only), and Independent Reserve KYC are in progress or done
  3. The Python repo exists with git, config files, and `.env` for keys that is never committed
**Plans**: 6 plans

Plans:
- [x] 01-01-PLAN.md — Foundation: pin ccxt/pandas, migrations runner, instruments/bars schema, cache helpers (ACCT-05, ACCT-06)
- [x] 01-02-PLAN.md — CoinGecko asset classification (memecoin vs crypto_major heuristic)
- [ ] 01-03-PLAN.md — Human checkpoint: IBKR, Kraken, Independent Reserve account applications (ACCT-01, ACCT-02, ACCT-03)
- [x] 01-04-PLAN.md — Stock daily bars fetcher (yfinance) with UTC-date normalization (ACCT-04)
- [x] 01-05-PLAN.md — Crypto daily bars fetcher (ccxt/Binance) with pagination (ACCT-04)
- [x] 01-06-PLAN.md — get_daily_bars public API + live exit-criterion acceptance run (ACCT-04, ACCT-07)

### Phase 2: Backtest Harness
**Goal**: Test any strategy against history without lying to yourself.
**Depends on**: Phase 1
**Requirements**: BACK-01, BACK-02, BACK-03, BACK-04, BACK-05, BACK-06, BACK-07
**Success Criteria** (what must be TRUE):
  1. The random-strategy sanity test loses money at roughly the fee rate
  2. One real strategy runs end-to-end and produces a metrics report
**Plans**: 10 plans

Plans:
- [x] 02-01-PLAN.md — Fee/slippage/EXIT_PROFILES config + backtest_runs/backtest_trades migration (BACK-02, BACK-03, BACK-04)
- [x] 02-02-PLAN.md — Point-in-time bar iterator, two-pointer cursors (BACK-01)
- [x] 02-03-PLAN.md — Metrics module with hand-computed golden fixture (BACK-06)
- [x] 02-04-PLAN.md — Fee and slippage fill mechanics (BACK-02, BACK-03)
- [x] 02-05-PLAN.md — Exit engine: D-10 order, entry-bar check, stop-wins-tie, trailing, eod_flat (BACK-04)
- [x] 02-06-PLAN.md — Trade ledger: one row per fill, reproducibility (BACK-05)
- [x] 02-07-PLAN.md — Seeded random strategy + momentum placeholder strategy (BACK-07)
- [x] 02-08-PLAN.md — Runner: wires iterator+fills+exits+ledger, signal-to-fill lag (BACK-01, BACK-04, BACK-05)
- [x] 02-09-PLAN.md — Sanity universe backfill + permanent BACK-07 exit-gate test
- [x] 02-10-PLAN.md — End-to-end momentum placeholder run + metrics report (BACK-06)

### Phase 3: Strategy Lab
**Goal**: Find configs worth paper trading; kill the rest cheaply.
**Depends on**: Phase 2
**Requirements**: STRAT-01, STRAT-02, STRAT-03, STRAT-04, STRAT-05, STRAT-06
**Success Criteria** (what must be TRUE):
  1. 2–3 strategy + exit-profile configs are profitable out-of-sample after fees and slippage
  2. Every surviving config has a pre-registered kill condition written before Phase 4
  3. If nothing survives, that result is accepted and work returns to Phase 3 — not forward
**Plans**: 8 plans

Plans:
- [x] 03-01-PLAN.md — Momentum (RSI+volume surge) and breakout (NR7+20-day high, no-retest) agents as pure functions (STRAT-01, STRAT-02)
- [x] 03-02-PLAN.md — Frozen universe/regime/exit-grid config, hash-based freeze gate, one-time live universe backfill (STRAT-03, STRAT-04, STRAT-05)
- [x] 03-03-PLAN.md — Sweep engine: grid iteration, provenance tagging, frozen-config hash gate, D-10 top-5 selection with min-trade floor (STRAT-03)
- [x] 03-04-PLAN.md — Real tune-sweep execution across both strategies, all 3 buckets, all 6 regimes (STRAT-03, STRAT-04, STRAT-05)
- [x] 03-05-PLAN.md — OOS validation engine + real run against every top-5 candidate's held-out window (STRAT-04, STRAT-05)
- [x] 03-06-PLAN.md — Sweep reports (tune vs OOS, per-symbol P&L) + KILL-CONDITIONS.md phase-exit gate (STRAT-06) — v1 concluded honestly: 0 survivors / 15 insufficient_sample
- [x] 03-07-PLAN.md — v2 (owner-approved): frozen v2 regime windows (OOS >= 12mo per bucket) + 3 momentum/3 breakout entry-gate variants + v2 hash gate, zero v1 modification (STRAT-03, STRAT-04, STRAT-05)
- [x] 03-08-PLAN.md — v2 sweep + OOS validation (~10,800 runs, detached/checkpoint-resumable) + regenerated KILL-CONDITIONS.md from v2 results (STRAT-03, STRAT-04, STRAT-05, STRAT-06)

### Phase 4: Risk Gate & Sizer
**Goal**: The safety layer, built before anything can trade.
**Depends on**: Phase 3
**Requirements**: RISK-01, RISK-02, RISK-03, RISK-04
**Success Criteria** (what must be TRUE):
  1. A poisoned candidate list (illiquid, brand-new token, correlated pair) has the right entries deleted
  2. Circuit breakers fire correctly in simulation
  3. Unit tests pass on the gate, sizer, and breakers
**Plans**: 5 plans

Plans:
- [x] 04-01-PLAN.md — Frozen risk config (liquidity/spread/correlation/sizer/breaker constants) + breaker_events migration (RISK-01, RISK-02, RISK-03)
- [x] 04-02-PLAN.md — Risk gate: liquidity/listing-age/spread checks + correlation cluster elimination + reason codes (RISK-01)
- [x] 04-03-PLAN.md — Position sizer: deterministic cap order, golden fixture, hypothesis cap-invariant property tests (RISK-02)
- [x] 04-04-PLAN.md — Circuit breakers: incremental no-lookahead evaluation + append-only persistence + human-only manual-restart CLI (RISK-03)
- [x] 04-05-PLAN.md — Poisoned-list acceptance test: gate + sizer two-stage pipeline, D-07 exit gate (RISK-04, RISK-01, RISK-02)

### Phase 5: Paper Trading Loop
**Goal**: The full pipeline running live on fake money — stocks via IBKR paper, crypto via simulated ledger.
**Depends on**: Phase 4
**Requirements**: PAPER-01, PAPER-02, PAPER-03, PAPER-04, PAPER-05, PAPER-06, PAPER-07
**Success Criteria** (what must be TRUE):
  1. Two consecutive weeks of unattended operation with zero manual interventions
  2. Zero unexplained state divergences between internal state and broker state
**Plans**: 9 plans

Plans:
- [ ] 05-01-PLAN.md — Migration 0005 + frozen config.py (5 live strategy configs) + idempotency.py + ledger.py (PAPER-03, PAPER-05)
- [ ] 05-02-PLAN.md — NYSE trading calendar + Telegram alerts + rotating ops log (PAPER-06, PAPER-07)
- [ ] 05-03-PLAN.md — IBKR paper-broker adapter (mockable, whole-share rounding) + crypto sim adapter (PAPER-01, PAPER-02)
- [ ] 05-04-PLAN.md — Reconciliation classification + combined halt gate + human-only clear_halt CLI (PAPER-04)
- [ ] 05-05-PLAN.md — Guardian: exit evaluation both venues + D-01 rolling kill-condition auto-retire (PAPER-02)
- [ ] 05-06-PLAN.md — Entry pipeline: scan->gate->sizer->round->idempotency->submit->ledger->alert (PAPER-01)
- [ ] 05-07-PLAN.md — Daily report paper-trading section + crash-recovery integration proof + full-suite green (PAPER-07)
- [ ] 05-08-PLAN.md — Checkpoint: IB Gateway install/login/API-enable + Telegram bot setup (PAPER-01, PAPER-06)
- [ ] 05-09-PLAN.md — Checkpoint: Task Scheduler registration + first supervised paper order + open two-week monitoring window (PAPER-01, PAPER-03, PAPER-04, PAPER-07)

### Phase 6: Graduation Review
**Goal**: Accumulate enough paper trades to judge, then judge by pre-registered criteria only.
**Depends on**: Phase 5
**Requirements**: GRAD-01, GRAD-02, GRAD-03, GRAD-04
**Success Criteria** (what must be TRUE):
  1. At least one strategy passes ALL graduation checks
  2. Anything hitting its pre-registered kill condition dies immediately, no appeals
  3. If nothing graduates after 3 months, work returns to Phase 3 — that outcome is the system working
**Plans**: TBD

### Phase 7: Attribution & Tournament
**Goal**: The self-improvement loop, built while Phase 6 collects data.
**Depends on**: Phase 5 (runs in parallel with Phase 6)
**Requirements**: ATTR-01, ATTR-02, ATTR-03, ATTR-04
**Success Criteria** (what must be TRUE):
  1. The tournament runs automatically on schedule
  2. Retire/promote decisions hold up when the owner audits them
**Plans**: TBD

### Phase 8: Signal Expansion
**Goal**: More signal sources on a proven foundation — only if Phase 6 graduated something.
**Depends on**: Phase 6 (graduation), Phase 7 (pipeline)
**Requirements**: SIG-01, SIG-02, SIG-03, SIG-04
**Success Criteria** (what must be TRUE):
  1. Each new agent independently passes probation via the Phase 7 pipeline
**Plans**: TBD

### Phase 9: Real Money Probation
**Goal**: First live capital, sized so total loss is genuinely fine.
**Depends on**: Phase 6 (at least one graduated strategy)
**Requirements**: LIVE-01, LIVE-02, LIVE-03, LIVE-04, LIVE-05, LIVE-06
**Success Criteria** (what must be TRUE):
  1. 30 live trades per strategy with performance within tolerance of paper results
  2. NZD tax ledger matches from trade #1
  3. The kill switch has been tested and flattens everything with one command
**Plans**: TBD

### Phase 10: Full Size & Steady State
**Goal**: Promote survivors to full allocation and settle into a monthly review cadence.
**Depends on**: Phase 9
**Requirements**: SCALE-01, SCALE-02, SCALE-03, SCALE-04
**Success Criteria** (what must be TRUE):
  1. Capital buckets are split with separate ledgers
  2. Monthly tournament review, slippage recalibration, and tax export all run
  3. Bankroll scales only after 3+ profitable months
**Plans**: TBD

## Standing Rules (all phases)

1. Never edit graduation/kill criteria while looking at results
2. Exit profiles lock at entry — no mid-trade loosening
3. API keys never get withdrawal permissions
4. If the system and the exchange disagree about a position, the system halts
5. "It'll probably be fine" = it goes back a phase

## Progress

**Execution Order:**
Phases execute in numeric order; Phase 0 runs continuously in the background, Phase 1 starts in parallel, and Phase 7 builds while Phase 6 collects data.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. Ground Truth | 5/5 | Monitoring (DATA-04 window to 2026-08-09) | - |
| 1. Accounts & Data Plumbing | 0/6 | Planned | - |
| 2. Backtest Harness | 10/10 | Complete | 2026-07-26 |
| 3. Strategy Lab | 8/8 | Complete (5 survivors, kill conditions registered) | 2026-07-26 |
| 4. Risk Gate & Sizer | 5/5 | Complete | 2026-07-26 |
| 5. Paper Trading Loop | 0/9 | Planned | - |
| 6. Graduation Review | 0/TBD | Not started | - |
| 7. Attribution & Tournament | 0/TBD | Not started | - |
| 8. Signal Expansion | 0/TBD | Not started | - |
| 9. Real Money Probation | 0/TBD | Not started | - |
| 10. Full Size & Steady State | 0/TBD | Not started | - |
