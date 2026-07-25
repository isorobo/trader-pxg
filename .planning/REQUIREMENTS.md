# Requirements: Trader AI

**Defined:** 25 July 2026
**Core Value:** The system never lies to itself — every strategy must prove its edge on honest data, after fees and slippage, before a single cent is at risk.

## v1 Requirements

Requirements map one-to-one onto the owner's phase document. Each phase's checklist items are the requirements; each phase's exit criteria are the success gate.

### Ground Truth (Phase 0)

- [ ] **DATA-01**: Snapshot logger polls a stock gainers feed and CoinGecko top movers every 15 minutes
- [ ] **DATA-02**: Every flagged ticker is logged to SQLite with timestamp, price, and % gain at snapshot time
- [ ] **DATA-03**: Daily report shows, for each flagged ticker, the same-day close and next-day close
- [ ] **DATA-04**: Logger runs continuously for two weeks minimum and keeps running after that

### Accounts & Data Plumbing (Phase 1)

- [ ] **ACCT-01**: IBKR account and paper trading account approved
- [ ] **ACCT-02**: Kraken account with trade-only API keys — no withdrawal permission
- [ ] **ACCT-03**: Independent Reserve account KYC complete (NZD ramp for Phase 9)
- [ ] **ACCT-04**: Historical daily bars source sorted for US stocks and major crypto pairs
- [ ] **ACCT-05**: Python repo set up with git, config files, and `.env` for keys (never committed)
- [ ] **ACCT-06**: SQLite database in place
- [ ] **ACCT-07**: One function call pulls historical daily bars for any US stock and any major crypto pair

### Backtest Harness (Phase 2)

- [ ] **BACK-01**: Point-in-time bar iterator — strategy code only ever sees bars ≤ current time
- [ ] **BACK-02**: Per-venue fee model (IBKR commissions, Kraken 0.16/0.26%, memecoin spread estimates)
- [ ] **BACK-03**: Slippage model scaled by asset class (large cap 0.05%, small cap runner 1–3%, memecoin 3–5%)
- [ ] **BACK-04**: Exit engine implements EXIT_PROFILES (stop, TP, scale-out, trailing, time stop, eod_flat)
- [ ] **BACK-05**: Trade ledger logs every simulated trade with strategy ID, profile, entry/exit, fees, P&L
- [ ] **BACK-06**: Metrics module reports profit factor, Sharpe, max drawdown, win rate, avg win/loss, per-strategy attribution
- [ ] **BACK-07**: Random-strategy sanity test loses roughly the fee rate — if it profits, the harness is broken

### Strategy Lab (Phase 3)

- [ ] **STRAT-01**: Momentum agent (RSI + volume surge) implemented as pure functions over bars
- [ ] **STRAT-02**: Breakout agent (20-day high after volatility contraction) implemented
- [ ] **STRAT-03**: Exit-parameter sweep per asset class (stop −5%…−30%, TP +20%…+100%, trail variants)
- [ ] **STRAT-04**: Configs tested across at least two regimes (trending year, choppy year)
- [ ] **STRAT-05**: Out-of-sample rule enforced — tune on period A, validate on period B that tuning never saw
- [ ] **STRAT-06**: Pre-registered kill condition written for every surviving config before Phase 4

### Risk Gate & Sizer (Phase 4)

- [ ] **RISK-01**: Risk gate checks min volume, max spread, min listing age, correlation, and tags asset class → EXIT_PROFILE
- [ ] **RISK-02**: Position sizer enforces top-3 cap, score/volatility weighting, 50% single-position cap, memecoin 10% cap, 10% cash reserve
- [ ] **RISK-03**: Circuit breakers — daily loss halt, drawdown halt with manual restart, consecutive-loss halt
- [ ] **RISK-04**: Unit tests cover the gate, sizer, and breakers; poisoned candidate list is rejected correctly

### Paper Trading Loop (Phase 5)

- [ ] **PAPER-01**: Scanner → gate → ranker → sizer → paper execution runs on schedule
- [ ] **PAPER-02**: Guardian monitors paper positions live and executes exits per profile
- [ ] **PAPER-03**: Orders are idempotent via client order IDs, even on paper
- [ ] **PAPER-04**: Reconciliation checks internal state against broker state every 60 seconds
- [ ] **PAPER-05**: Ledger logs every paper trade exactly as a real one, tagged by strategy and profile
- [ ] **PAPER-06**: Telegram (or similar) alerts on fills, stops, errors, and heartbeat
- [ ] **PAPER-07**: Loop runs unattended overnight through US market hours (~1:30am–8am NZ time)

### Graduation Review (Phase 6)

- [ ] **GRAD-01**: Each strategy accumulates ≥ 50 closed paper trades
- [ ] **GRAD-02**: Weekly review runs against pre-registered criteria only
- [ ] **GRAD-03**: Graduation checklist enforced (profit factor > 1.3 after costs, max drawdown < 15%, profitable in ≥ 2 conditions, no single trade > 40% of profit, positive with fills 1% worse)
- [ ] **GRAD-04**: Any strategy hitting its pre-registered kill condition is killed immediately

### Attribution & Tournament (Phase 7)

- [ ] **ATTR-01**: Per-strategy P&L dashboards (simple HTML report acceptable)
- [ ] **ATTR-02**: Tournament rules encoded — 30-trade minimum, Sharpe-based judging, probation sizing
- [ ] **ATTR-03**: New-strategy pipeline — backtest → out-of-sample → paper (30 trades) → probation (25% size) → full
- [ ] **ATTR-04**: Cap of 5–6 active strategies with limited mutations per quarter

### Signal Expansion (Phase 8 — conditional on Phase 6 graduating a strategy)

- [ ] **SIG-01**: Mean-reversion agent and social sentiment agent (LunarCrush)
- [ ] **SIG-02**: News agent as confirmation tilt only, LLM in cold path
- [ ] **SIG-03**: Volatility regime detector feeds ranker/sizer as context
- [ ] **SIG-04**: Every new agent enters through the Phase 7 pipeline and passes probation independently

### Real Money Probation (Phase 9)

- [ ] **LIVE-01**: Bankroll set at the "lose it all and shrug" amount — no negotiating up
- [ ] **LIVE-02**: Funding path — Independent Reserve → Kraken; small USD to IBKR mindful of PDT
- [ ] **LIVE-03**: Graduated strategies go live at 25% of intended size
- [ ] **LIVE-04**: NZD tax logging live from trade #1 (timestamp, qty, price, fees, NZD rate)
- [ ] **LIVE-05**: Weekly comparison of live fills against paper assumptions
- [ ] **LIVE-06**: Kill switch tested — one command flattens everything

### Full Size & Steady State (Phase 10)

- [ ] **SCALE-01**: Strategies surviving live probation promoted to full allocation
- [ ] **SCALE-02**: Capital split into short-term / swing / long-term buckets with separate ledgers
- [ ] **SCALE-03**: Monthly routine — tournament review, slippage recalibration, tax ledger export
- [ ] **SCALE-04**: Bankroll scales only after 3+ profitable months, only with money the owner can lose

## v2 Requirements

(None — the owner's phase document defines the full scope. Phase 8 is conditional, not deferred.)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real money before Phase 9 | Standing project rule — nothing earlier touches a cent |
| Withdrawal permission on any API key | Standing rule 3 — trade-only keys, always |
| Postgres/Timescale at the start | SQLite until it hurts |
| Paid intraday data (Polygon.io) | Daily bars first; decide later for intraday |
| Editing graduation/kill criteria while viewing results | Standing rule 1 |
| Mid-trade exit-profile loosening | Standing rule 2 — profiles lock at entry |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01…04 | Phase 0 | Pending |
| ACCT-01…07 | Phase 1 | Pending |
| BACK-01…07 | Phase 2 | Pending |
| STRAT-01…06 | Phase 3 | Pending |
| RISK-01…04 | Phase 4 | Pending |
| PAPER-01…07 | Phase 5 | Pending |
| GRAD-01…04 | Phase 6 | Pending |
| ATTR-01…04 | Phase 7 | Pending |
| SIG-01…04 | Phase 8 | Pending (conditional) |
| LIVE-01…06 | Phase 9 | Pending |
| SCALE-01…04 | Phase 10 | Pending |

**Coverage:**
- v1 requirements: 57 total
- Mapped to phases: 57
- Unmapped: 0 ✓

---
*Requirements defined: 25 July 2026*
*Last updated: 25 July 2026 after initial definition*
