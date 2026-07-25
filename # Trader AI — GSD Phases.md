# Trader AI — GSD Phases

Rule for the whole project: a phase is DONE when its exit criteria are met, not when you're bored of it. No skipping ahead. Real money is Phase 9 and nothing before it touches a cent.

---

## Phase 0 — Ground truth (start today, runs in background forever)
**Goal:** Find out what the "+400% gainers" actually resolve to.

- [ ] Build the snapshot logger: poll a stock gainers feed + CoinGecko top movers every 15 min
- [ ] Log every ticker that ever appears: timestamp, price, % gain at time of snapshot → SQLite
- [ ] Daily report script: for each ticker that appeared, where did it close? Where did it close next day?
- [ ] Run it for 2+ weeks minimum (keep it running forever — it's free data)

**Exit criteria:** You can answer "of everything the scanner flagged this week, what % ended the day up vs dumped?" with real numbers.
**Time:** 1 evening to build, 2 weeks to collect.

---

## Phase 1 — Accounts & data plumbing
**Goal:** All access sorted before you need it.

- [ ] IBKR account + paper trading account (approval takes days — start early)
- [ ] Kraken account + API keys (trade-only permissions, NO withdrawal permission on API keys)
- [ ] Independent Reserve account (NZD ramp — not needed until Phase 9, but KYC takes time)
- [ ] Historical data source sorted: daily bars (free) for swing/long-term; decide on Polygon.io later for intraday
- [ ] Repo set up: Python project, git, config files, `.env` for keys (never committed)
- [ ] Database: SQLite to start (upgrade to Postgres/Timescale only when it hurts)

**Exit criteria:** You can pull historical daily bars for any US stock and any major crypto pair with one function call.
**Time:** 1 weekend + waiting on approvals.

---

## Phase 2 — Backtest harness (the honest machine)
**Goal:** Test any strategy against history without lying to yourself.

- [ ] Point-in-time bar iterator — strategy code can only ever see bars ≤ current time
- [ ] Fee model: per-venue fees (IBKR commissions, Kraken 0.16/0.26%, memecoin spread estimates)
- [ ] Slippage model: % penalty scaled by asset class (large cap 0.05%, small cap runner 1–3%, memecoin 3–5%)
- [ ] Exit engine: implements EXIT_PROFILES (stop, TP, scale-out, trailing, time stop, eod_flat)
- [ ] Trade ledger: every simulated trade logged with strategy ID, profile, entry/exit, fees, P&L
- [ ] Metrics module: profit factor, Sharpe, max drawdown, win rate, avg win/loss, per-strategy attribution
- [ ] Sanity test: run a known-dumb strategy (buy random, hold 1 day) — it MUST lose ~fees. If it profits, the harness is broken

**Exit criteria:** The random-strategy sanity test loses money at roughly the fee rate. One real strategy runs end-to-end and produces a metrics report.
**Time:** 1–2 weeks of evenings.

---

## Phase 3 — Strategy lab (backtest everything)
**Goal:** Find configs worth paper trading. Kill the rest cheaply.

- [ ] Implement Momentum agent (RSI + volume surge) as pure functions over bars
- [ ] Implement Breakout agent (20-day high after volatility contraction)
- [ ] Sweep exit parameters per asset class: stop −5%…−30%, TP +20%…+100%, trail variants
- [ ] Test across at least 2 regimes (e.g. a trending year and a choppy year)
- [ ] Out-of-sample rule: tune on period A, validate on period B that tuning never saw
- [ ] Write down the pre-registered kill condition for every surviving config BEFORE Phase 4

**Exit criteria:** 2–3 strategy+exit-profile configs that are profitable out-of-sample after fees/slippage. If NOTHING survives — that's a valid, cheap result. Go back to Phase 3, not forward.
**Time:** 2–3 weeks.

---

## Phase 4 — Risk gate & sizer
**Goal:** The safety layer, built before anything can trade.

- [ ] Risk gate: min volume, max spread, min listing age, correlation check, asset-class classification → EXIT_PROFILE tag
- [ ] Position sizer: top-3 cap, score/volatility weighting, 50% single-position cap, memecoin 10% cap, 10% cash reserve
- [ ] Circuit breakers: daily loss limit → halt entries; drawdown limit → halt + manual restart; consecutive-loss halt
- [ ] Unit tests on all of it — this is the code that must never be wrong

**Exit criteria:** Feed the gate a poisoned candidate list (illiquid, brand-new token, correlated pair) and watch it delete the right ones. Breakers fire correctly in simulation.
**Time:** 1 week.

---

## Phase 5 — Paper trading loop (stocks via IBKR paper, crypto via simulated ledger)
**Goal:** The full pipeline running live on fake money.

- [ ] Scanner → gate → ranker → sizer → paper execution, running on schedule
- [ ] Guardian: live monitoring of paper positions, executes exits per profile
- [ ] Idempotent orders (client order IDs) even on paper — build the habit now
- [ ] Reconciliation: internal state vs broker state check every 60s
- [ ] Ledger: every paper trade logged exactly as a real one would be, tagged by strategy + profile
- [ ] Telegram (or similar) alerts: fills, stops, errors, heartbeat
- [ ] Runs unattended overnight (US market hours are ~1:30am–8am NZ time — it must survive without you)

**Exit criteria:** 2 consecutive weeks of unattended operation with zero manual interventions and zero unexplained state divergences.
**Time:** 2 weeks build + however long stability takes.

---

## Phase 6 — Data collection & graduation review
**Goal:** Accumulate enough paper trades to judge.

- [ ] Run until each strategy has ≥ 50 closed paper trades
- [ ] Weekly review against pre-registered criteria only (no vibes)
- [ ] Graduation checklist per strategy:
  - Profit factor > 1.3 after fees/slippage
  - Max drawdown < 15%
  - Profitable in ≥ 2 market conditions
  - No single trade > 40% of total profit
  - Still positive with fills assumed 1% worse
- [ ] Kill anything that hits its pre-registered kill condition — immediately, no appeals

**Exit criteria:** At least one strategy passes ALL graduation checks. (If none do after 3 months: the edge isn't there yet — iterate in Phase 3. This outcome is common and is the system working, not failing.)
**Time:** 1–3 months of runtime.

---

## Phase 7 — Attribution & tournament layer
**Goal:** The self-improvement loop, built while Phase 6 collects data.

- [ ] Per-strategy P&L dashboards (even a simple HTML report is fine to start)
- [ ] Tournament rules encoded: 30-trade minimum, Sharpe-based judging, probation sizing
- [ ] New-strategy pipeline: backtest → out-of-sample → paper (30 trades) → probation (25% size) → full
- [ ] Cap: max 5–6 active strategies, limited mutations per quarter

**Exit criteria:** Tournament runs automatically on schedule and produces retire/promote decisions you agree with when you audit them.
**Time:** 1–2 weeks (parallel with Phase 6).

---

## Phase 8 — Optional signal expansion (only if Phase 6 graduated something)
**Goal:** More signal sources on a proven foundation.

- [ ] Mean-reversion agent, social sentiment agent (LunarCrush)
- [ ] Trump/news agent — as confirmation tilt only, LLM in cold path
- [ ] Volatility regime detector as context input to ranker/sizer
- [ ] Every new agent enters through the Phase 7 pipeline like everyone else

**Exit criteria:** Each new agent independently passes probation.

---

## Phase 9 — Real money, probation size
**Goal:** First live capital, sized so total loss is genuinely fine.

- [ ] Decide the "I could lose all of this and shrug" amount — that's the bankroll, no negotiating up
- [ ] Fund via Independent Reserve → Kraken; small USD to IBKR (mind PDT: under US$25k margin = 3 day trades/5 days — cash account or crypto-first until then)
- [ ] Graduated strategies go live at 25% of intended size
- [ ] NZD tax logging live from trade #1: timestamp, qty, price, fees, NZD rate (CARF means IRD sees exchange data — your ledger must match)
- [ ] Compare live fills vs paper assumptions weekly — this measures your real slippage
- [ ] Kill switch tested: one command flattens everything

**Exit criteria:** 30 live trades per strategy with performance within tolerance of paper results.
**Time:** 1+ month.

---

## Phase 10 — Full size & steady state
- [ ] Promote strategies that survived live probation to full allocation
- [ ] Split capital buckets: short-term / swing / long-term bots, separate ledgers
- [ ] Monthly: tournament review, slippage model recalibration, tax ledger export
- [ ] Scale bankroll only after 3+ profitable months — and only with money you can lose

---

## Standing rules (all phases)
1. Never edit graduation/kill criteria while looking at results
2. Exit profiles lock at entry — no mid-trade loosening
3. API keys never get withdrawal permissions
4. If the system and the exchange disagree about a position, the system halts
5. "It'll probably be fine" = it goes back a phase