# Phase 4: Risk Gate & Sizer - Research

**Researched:** 26 July 2026
**Domain:** Deterministic risk filtering, position sizing, and circuit-breaker state machines for a mixed stock/crypto trading system (pure Python, SQLite, pandas/numpy — no live network calls in this phase)
**Confidence:** MEDIUM (mechanics and schema design are HIGH confidence; the specific numeric thresholds pinned below are ASSUMED project judgment calls, clearly flagged for owner confirmation)

## Summary

Phase 4 has no new external-service integration risk — it is pure computation over data the project already owns (`trader/data/db.py` bars cache, `trader/data/api.py` resolution, `trader/backtest/config.py`'s `EXIT_PROFILE`). The real risk in this phase is design-decision risk: getting the *order of operations* in the sizer wrong (cap-then-normalize vs normalize-then-cap changes the answer), getting the *correlation window's edge cases* wrong (short-history memecoins, mixed stock/crypto trading calendars), and getting the *breaker's day-boundary and HWM-source* definitions wrong in a way that silently diverges between Phase 4's tests and Phase 5's live paper loop.

This research pins concrete numeric defaults for the two decisions the owner explicitly deferred to the researcher (liquidity floors) and works through the four other research questions the owner asked about, with a fully worked numeric example for the sizer's deterministic weight→cap→renormalize order. It also surfaces one cross-phase contract gap that the planner needs to resolve explicitly: **Phase 3's strategy contract (`pick_entries(...) -> list[str]`) does not emit a numeric score**, yet D-02's correlation rule ("reject the lower-scored candidate") requires one to exist at gate-evaluation time. Phase 4 must define its own candidate-dict contract (a `score: float` field, source-agnostic per D-06) rather than importing Phase 3's or waiting for Phase 5's ranker.

**Primary recommendation:** Build `trader/risk/` as four independent pure-function modules (`gate.py`, `sizer.py`, `breakers.py`, `config.py`) over a plain `dict`/`list[dict]` candidate contract; persist breaker state as an **event log + computed current-state view** (not a mutable single row); pin liquidity floors deliberately lower than typical retail defaults (justified below) because this project's position sizes are small relative to typical retail account sizing; add `hypothesis` as a pinned dev-only dependency for the sizer's cap-invariant tests, since this is explicitly "the code that must never be wrong."

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Pure function: `apply_risk_gate(candidates, market_data, config) -> (accepted, rejected)` where every rejection carries a machine-readable reason code. Thresholds live in a frozen-style config module, not inline.
- **D-02:** Gate checks per phase doc: minimum liquidity (stocks: trailing-20-day median dollar volume floor; crypto: trailing-7-day median quote volume floor — researcher pins defaults), minimum listing age (default 30 days of bars), maximum spread (static per-asset-class estimates for now — live spread checks are a Phase 5 concern, noted explicitly), pairwise correlation check (trailing 60-day daily-return correlation; if a pair exceeds 0.8, reject the lower-scored candidate), and asset-class classification → EXIT_PROFILE tag via the existing instruments table.
- **D-03:** Pure function over (scored candidates, current equity, open positions): top-3 concurrent positions cap; score × inverse-volatility weighting; 50% single-position cap; 10% total memecoin cap; 10% cash reserve always held back. All from the phase document verbatim; deterministic and unit-testable.
- **D-04:** Breaker state machine persisted in the shared DB (new migration): daily-loss breaker (default −3% of equity in a day → halt new entries until next session), drawdown breaker (default −10% from equity high-water mark → halt everything + `manual_restart_required` flag cleared only by explicit human command), consecutive-loss breaker (default 6 consecutive losing closed trades → halt entries). Breakers fire in simulation via the Phase 2 harness in tests.
- **D-05:** Breaker checks are pure functions over ledger/equity series; persistence layer thin. If the system and any external state ever disagree, halt (standing rule 4 baked into the state machine's design).
- **D-06:** `Strategys/13_risk_management_overlay.md` is the owner's reference doc; the phase document wins on conflict. The gate/sizer consume candidate scores from any strategy (Phase 3 v1/v2 survivors or future Phase 7 entrants) — no coupling to specific strategies.
- **D-07:** Exit-gate acceptance test: a committed poisoned candidate list (illiquid stock, 5-day-old token, correlated pair, oversized memecoin allocation) must produce exactly the expected rejections with correct reason codes.

### Claude's Discretion

- Module layout under `trader/risk/`, exact reason-code enum, breaker table DDL, correlation computation details.

### Deferred Ideas (OUT OF SCOPE)

- Live spread measurement — Phase 5 (needs quotes)
- Threshold recalibration from paper data — Phase 6, pre-registered changes only
- Portfolio-level VaR/exposure analytics — Phase 7 dashboards if wanted
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RISK-01 | Risk gate checks min volume, max spread, min listing age, correlation, and tags asset class → EXIT_PROFILE | Q1 (liquidity floors), Q2 (correlation mechanics), Reason-code enum, EXIT_PROFILE tagging via existing `instruments` table (`trader/data/db.py get_instrument`) |
| RISK-02 | Position sizer enforces top-3 cap, score/volatility weighting, 50% single-position cap, memecoin 10% cap, 10% cash reserve | Q3 (inverse-vol weighting + deterministic cap order, worked example) |
| RISK-03 | Circuit breakers — daily loss halt, drawdown halt with manual restart, consecutive-loss halt | Q4 (breaker state machine schema, day boundary, HWM source) |
| RISK-04 | Unit tests cover the gate, sizer, and breakers; poisoned candidate list is rejected correctly | Q5 (hypothesis vs parameterized pytest), Q6 (poisoned-list fixture design), Validation Architecture section |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Liquidity / listing-age / spread / correlation filtering | API / Backend (pure logic layer) | Database (bars/instruments read) | Gate reads cached bars + instruments via `trader/data/api.py` and `db.py`, computes in-process, never touches network (D-01) |
| Asset-class → EXIT_PROFILE tagging | API / Backend | Database (`instruments` table) | Reuses Phase 1's `instruments.asset_class`/`override` columns; no new classification logic |
| Position sizing (weights, caps) | API / Backend (pure logic layer) | — | Pure function over in-memory candidate/equity data; no I/O (D-03) |
| Circuit breaker evaluation | API / Backend (pure logic layer) | Database (breaker event log) | D-05: evaluation is pure over ledger/equity series; persistence is a thin append-only writer, never the source of truth for a decision |
| Breaker state persistence | Database / Storage | — | New migration `0004_risk_breakers.sql`; event log + view, following the `schema_version`/migrations pattern in `trader/data/db.py` |

## Q1: Liquidity Floor Defaults

**Confidence: LOW-MEDIUM.** The general retail convention (WebSearch, multiple sources) is well-established; the *specific numbers pinned for this project* are a judgment call `[ASSUMED]` and should be confirmed or overridden by the owner before the config module is written.

### What the general market convention says

Retail swing-trading screens commonly use a minimum average dollar volume around **$20M/day** for a "safe" universe, with **$80M/day** cited for larger accounts wanting deep liquidity, and a lower bound around **500,000 shares/day** (not dollar volume) mentioned for smaller retail accounts `[CITED: morpheustrading.com/blog/minimum-trading-volume, trade-ideas.com/help/filter/DV]`. These thresholds are calibrated to protect *position sizes in the tens of thousands to low hundreds of thousands of dollars* — a materially larger check size than this project's near-term bankroll.

### Why this project can use much lower floors, and by how much

The phase document's owner-stated approach is "lose it and shrug" bankroll sizing for Phase 9's first live capital (LIVE-01), and Phase 4's own sizer caps any single position at 50% of equity with a further 10% cap on the highest-risk asset class (memecoins). Combined with `DEFAULT_NOTIONAL = $10,000` already used as Phase 2's fixed per-trade backtest notional (`trader/backtest/config.py`), a realistic single-position dollar size for this project's near-term operation is in the **low thousands to ~$10,000** range, not tens of thousands. A standard market-impact rule of thumb is to stay under roughly 5-10% of a security's average daily dollar volume for a single trade to avoid materially moving the price `[CITED: general market-microstructure convention, corroborated across the WebSearch sources above]`. At a $10,000 position size, a $1M/day floor keeps any single trade at ≤1% of ADV — an order of magnitude inside the usual 5-10% guideline, with room to spare as the bankroll grows through Phase 10.

### Pinned defaults `[ASSUMED — confirm before locking config]`

| Constant | Value | Basis |
|----------|-------|-------|
| `MIN_DOLLAR_VOLUME_STOCK` (trailing 20-day median) | **$1,000,000/day** | ~20x smaller than the standard $20M retail swing-trading floor, justified by this project's much smaller position sizes (see above); still high enough to exclude genuinely illiquid microcaps/penny stocks that the Phase 0 gainers scanner is likely to surface |
| `MIN_QUOTE_VOLUME_CRYPTO_MAJOR` (trailing 7-day median) | **$5,000,000/day** | BTC/ETH trade in the billions/day on any real venue; this floor is a sanity check against data errors, not a binding real-world constraint |
| `MIN_QUOTE_VOLUME_MEMECOIN` (trailing 7-day median) | **$250,000/day** | Deliberately looser than the stock floor's ratio-to-position-size, because the memecoin allocation is already hard-capped at 10% of equity by the sizer (D-03) — the liquidity floor's job here is only to filter dead/rug-pulled tokens, not to gate the momentum-driven volume spikes the scanner is designed to catch |

**Median, not mean:** use the *median* of the trailing window's daily dollar/quote volume, not the mean — a single outlier day (e.g. a listing-day spike) should not single-handedly qualify an otherwise illiquid asset. This matches the phase document's own wording ("median dollar volume floor") and is the more robust statistic for skewed volume distributions `[ASSUMED — standard practice, not separately verified for this project]`.

**Computation detail:** `dollar_volume[t] = close[t] * volume[t]` per bar (using bar close, not open, to match how the gate would evaluate "as of" the most recent available daily bar — consistent with `trader/data/api.py`'s point-in-time bar contract).

## Q2: Correlation Check Mechanics

**Confidence: MEDIUM.** The 0.8 threshold is corroborated by industry convention (0.7-0.85 commonly cited as the "acting as one risk unit" zone) `[CITED: multiple portfolio-management sources via WebSearch]`; the specific overlap-window and cluster-resolution rules below are `[ASSUMED]` engineering decisions consistent with the locked 0.8 threshold.

### Computation

- Trailing **60 calendar days of daily-return observations** (not 60 bars — see below), computed as simple returns `r_t = close[t]/close[t-1] - 1` from the cached daily bars (`trader/data/db.py read_bars_cache`).
- **Alignment is by calendar date, not positional index.** Stocks trade ~5 days/week (NYSE holidays/weekends absent from the bars table); crypto trades 7 days/week. A pairwise correlation between one stock and one crypto asset must inner-join on shared dates, not zip two equal-length arrays positionally — positional alignment would silently misalign a stock's Monday return against a crypto asset's Sunday return once a holiday is skipped.
- **Minimum overlap for a valid correlation:** because D-02's minimum listing age (30 days of bars) already gates any candidate individually before the correlation check runs, every candidate reaching the correlation step already has ≥30 days of its own history. Require the **inner-joined overlap between the two candidates in a pair to be ≥30 observations** before computing a correlation; if overlap is below 30 (only possible from a stock/crypto calendar mismatch stripping out enough shared dates, not from a genuinely new listing, since the listing-age gate already ran first), treat the correlation as **indeterminate** — do not reject either candidate on this pair, but flag it (e.g. a `correlation_indeterminate` note in `market_data` or a log line) so the condition is visible rather than silently ignored. This is a defensive edge case, not expected to trigger often in practice given the listing-age gate's ordering.
- Use `numpy.corrcoef` (Pearson) or `pandas.Series.corr` — both already project dependencies (`numpy==2.5.1`... actually confirm from requirements.txt: `pandas==3.0.5` is pinned; numpy ships as pandas's dependency). No new package needed for correlation itself.

### The "reject the lower-scored candidate" rule — 3-way and N-way clusters

D-02's rule is stated for a single pair. For three or more mutually correlated candidates (a "cluster"), resolve deterministically as a **greedy sequential elimination**:

1. Compute all pairwise correlations among the surviving candidate set (those not yet rejected by liquidity/age/spread).
2. Sort all pairs exceeding the 0.8 threshold by correlation magnitude, descending.
3. Walk the sorted list. For each pair, if **both** members are still in the surviving set, reject the lower-scored member immediately (remove it from the surviving set) and record the reason code against it. If one or both members were already removed by an earlier pair in this walk, skip this pair (already resolved).
4. Repeat until the sorted pair list is exhausted.

This is deterministic (fixed input → fixed output), resolves a fully-connected 3-way cluster down to exactly one survivor (its highest-scored member, since every pair in a fully-connected cluster eventually gets walked), and is simple enough to unit-test directly with a synthetic 3-way correlation matrix. `[ASSUMED — this specific algorithm was not found verbatim in any external source; it is a standard greedy-clustering approach adapted for this rule, and should be confirmed against the phase document's intent if the owner wants a different tie-break for partial (non-fully-connected) clusters.]`

## Q3: Inverse-Volatility Weighting and Deterministic Cap Order

**Confidence: MEDIUM-HIGH** for the general inverse-vol formula (well-established, corroborated across multiple quant-finance sources); **LOW-MEDIUM** for the specific cap-application order below, which is an engineering decision this research recommends rather than one verified externally, since the phase document does not specify an order.

### Formula

Standard inverse-volatility weighting: `raw_weight_i = score_i / σ_i`, where `σ_i` is a trailing realized volatility measure (daily-return standard deviation over a lookback window) `[CITED: alvarezquanttrading.com/blog/inverse-volatility-position-sizing, quantinsti.com/blog/risk-parity-portfolio]`. This is "optimal if markets have similar expected Sharpe ratios and similar expected pairwise correlations" — an assumption this project is not verifying, but the formula itself is the industry-standard starting point and matches the owner's reference doc's explicit endorsement ("Volatility-adjusted... This is what the Turtles did and what CTAs still do," `Strategys/13_risk_management_overlay.md`).

**Volatility window:** recommend a **20-day trailing daily-return standard deviation** for `σ_i` — deliberately shorter than the 60-day correlation window, because sizing should react to the *current* volatility regime (a recently-quiet-then-suddenly-volatile memecoin should get downsized quickly), while the correlation check benefits from a longer, more stable window to avoid two assets flickering in and out of "correlated" status day to day `[ASSUMED — reasonable engineering choice, not independently verified]`.

### Deterministic order: select → weight → normalize → cap → re-cap → cash absorbs remainder

Recommend this exact sequence, chosen because caps should only ever **remove** risk and never silently reallocate it into an uncapped position (simpler, more conservative, and trivially testable as an invariant):

1. **Select top 3** by score among gate-accepted candidates (top-3 concurrent cap applies here, before any weighting).
2. **Compute raw inverse-vol weights** only among the selected 3: `raw_i = score_i / σ_i`.
3. **Normalize** so the three raw weights sum to `(1 − cash_reserve)` = 0.90 (10% cash reserve held back per D-03) → `preliminary_w_i`.
4. **Apply the 50% single-position cap:** `capped_w_i = min(preliminary_w_i, 0.50)`.
5. **Apply the 10% memecoin aggregate cap:** if the sum of `capped_w_i` across memecoin-class positions exceeds 0.10, scale every memecoin weight down proportionally so the memecoin sum equals exactly 0.10.
6. **Any capital freed by steps 4-5 is not reallocated** to the remaining positions — it flows into cash, so cash ends up **≥10%** whenever a cap binds, never exactly 10% in that case. This keeps the invariant "sum(position weights) + cash = 1.0" trivially true without a second normalization pass that could re-trigger the caps it just enforced.

### Worked example

Three gate-accepted, top-3-selected candidates:

| Candidate | Asset class | Score | 20d vol (σ) | raw = score/σ |
|---|---|---|---|---|
| A | stock | 0.90 | 0.02 | 45.00 |
| B | crypto_major | 0.70 | 0.04 | 17.50 |
| C | memecoin | 0.95 | 0.15 | 6.33 |

Sum of raw = 68.83. Normalize to 0.90:
- `w_A = 45.00/68.83 × 0.90 = 0.5885`
- `w_B = 17.50/68.83 × 0.90 = 0.2289`
- `w_C = 6.33/68.83 × 0.90 = 0.0827`

Apply 50% cap: `w_A` exceeds 0.50 → capped to **0.50** (0.0885 freed to cash).
Apply memecoin 10% cap: `w_C = 0.0827 < 0.10` → unchanged.

**Final:** A = 0.50, B = 0.2289, C = 0.0827, cash = 1 − 0.50 − 0.2289 − 0.0827 = **0.1884** (18.84%, above the 10% floor because the single-position cap bound).

This worked example is the recommended basis for a golden-fixture unit test (mirrors the project's existing convention of hand-worked golden fixtures, e.g. `trader/backtest/metrics.py`'s docstring reference to `tests/test_backtest_metrics.py`).

## Q4: Breaker State Machine

**Confidence: MEDIUM** for the event-log schema pattern (well-established event-sourcing convention, corroborated by WebSearch); **LOW-MEDIUM** for the UTC-day-boundary recommendation specific to this project's mixed-asset scheduling, which is an engineering judgment call.

### Schema: event log + current-state view (recommended over a single mutable row)

An append-only event log — rather than a single mutable "current state" row — gives an audit trail (when did the daily-loss breaker actually trip, and why) and makes "if the system and external state disagree, halt" (standing rule 4) easy to implement: a disagreement is detected by *re-deriving* state from the event log and comparing, rather than trusting a cached column that could itself have silently drifted `[CITED: general event-sourcing pattern — sqliteforum.com/p/event-sourcing-with-sqlite, sqliteforum.com/p/building-event-sourcing-systems-with]`.

```sql
-- migrations/0004_risk_breakers.sql (next version after 0003_backtest.sql)

CREATE TABLE IF NOT EXISTS breaker_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    breaker_type TEXT NOT NULL CHECK (breaker_type IN ('daily_loss', 'drawdown', 'consecutive_loss')),
    action TEXT NOT NULL CHECK (action IN ('trip', 'reset', 'manual_restart')),
    trigger_value REAL,
    reason TEXT,
    actor TEXT NOT NULL DEFAULT 'system' CHECK (actor IN ('system', 'human'))
);

CREATE INDEX IF NOT EXISTS idx_breaker_events_type ON breaker_events(breaker_type);

-- Current-state view: the latest event per breaker_type IS the current state.
-- A breaker is "tripped" iff its latest event's action is 'trip' (a later
-- 'reset' or 'manual_restart' clears it back to normal).
CREATE VIEW IF NOT EXISTS breaker_state_current AS
SELECT be.breaker_type, be.action AS current_action, be.ts AS since, be.reason
FROM breaker_events be
INNER JOIN (
    SELECT breaker_type, MAX(event_id) AS max_event_id
    FROM breaker_events
    GROUP BY breaker_type
) latest ON be.breaker_type = latest.breaker_type AND be.event_id = latest.max_event_id;
```

`[ASSUMED — exact column names/DDL, per CONTEXT.md's "Claude's Discretion: breaker table DDL." Recommend this shape; planner/implementer may adjust column names to match the project's existing style (snake_case matches `backtest_trades`/`instruments`).]`

### Day boundary: UTC calendar day (with an explicit caveat)

Recommend **UTC calendar day (00:00-24:00 UTC)** as the daily-loss breaker's "day" boundary, for one reason: it is the only boundary definition that both asset classes share without inventing a dual-calendar concept. NYSE trading hours (roughly 14:30-21:00 UTC) and 24/7 crypto trading do not share a natural single "session" boundary otherwise.

**Explicit caveat:** UTC midnight does **not** align with the NYSE close. A large stock loss late in the NYSE session followed by continued crypto losses after UTC midnight could span what a stock-only system would consider "one trading day," splitting a single bad day's total loss across two UTC-day buckets. Given Phase 5's paper loop runs during US market hours (~1:30am-8am NZ time = ~13:30-20:00 UTC per the project's own phase document), UTC midnight (00:00 UTC = 1pm NZ time) falls **outside** the active trading window for the stock side of the book, making this edge case low-impact in practice — but it is a real simplification, not a non-issue, and should be revisited if intraday/24-hour scheduling is ever added. `[ASSUMED — Claude's discretion per CONTEXT.md, flagged for owner confirmation since standing rule 4 makes "if in doubt, halt" the safe default and this is exactly a case where two reasonable definitions exist.]`

### Equity high-water-mark (HWM) tracking

Per D-05 ("breaker checks are pure functions over ledger/equity series; persistence layer thin"), **do not persist the HWM as its own stored value.** Instead, recompute the running HWM from the equity series itself on every evaluation: `hwm = max(equity_curve[:t+1])` at each point in time, i.e. an incremental running maximum evaluated only over bars up to and including "now" — never over the full future curve. This mirrors `trader/backtest/metrics.py`'s existing `max_drawdown()` peak-tracking loop (`peak = max(peak, value)` per point), but that function computes drawdown *retrospectively* over an entire completed curve for reporting; the breaker must call the equivalent logic **incrementally**, evaluating only data available "as of now" each time a new equity point arrives. **Common mistake to avoid (see Pitfalls):** passing a test fixture's full equity curve (including future points) into a breaker check function would let the breaker "see" a future recovery and never trip — a lookahead bug structurally identical to the point-in-time bar iterator's own core discipline (`trader/backtest/iterator.py`'s `PointInTimeIterator`).

**Equity source in Phase 4's tests:** the Phase 2 harness's equity curve construction (`trader/backtest/metrics.py`'s `_build_daily_equity_curve`) is the natural source for breaker simulation tests — feed a synthetic or real backtest run's per-date equity series through the breaker's pure evaluation function bar-by-bar. In Phase 5, the equivalent source becomes the paper-trading ledger's live equity (out of scope for Phase 4, noted per D-04).

## Q5: Property-Based Testing (hypothesis) on Windows

**Confidence: HIGH** (package existence, current version, and purpose all confirmed via official docs + registry + slopcheck).

`hypothesis` is a mature, actively maintained property-based testing library for Python `[CITED: hypothesis.readthedocs.io — "write tests which should pass for all inputs in whatever range you describe, and let Hypothesis randomly choose which of those inputs to check"]`. Current version confirmed via `pip index versions hypothesis` → **6.161.5** `[VERIFIED: PyPI registry]`, and confirmed clean via `slopcheck install hypothesis` → **[OK]** (see Package Legitimacy Audit below). It is pure-Python and installs cleanly on Windows (no compiled extensions beyond its `sortedcontainers` dependency, which is also pure Python) — installation was exercised directly in this research session and succeeded without issue.

**Recommendation: add it, scoped narrowly.** The project's specifics explicitly call out this phase as needing property-style tests ("caps never exceeded under any input... this is the code that must never be wrong"). Parameterized pytest cases (`@pytest.mark.parametrize`) only cover hand-picked scenarios; a `hypothesis`-generated test over random `(score, volatility, asset_class)` tuples can assert the sizer's invariants — no weight > 0.50, memecoin sum ≤ 0.10, cash ≥ 0.10, sum of all weights == 1.0 — hold for inputs the author didn't think to write by hand. This is precisely the class of bug (an off-by-one in the cap-then-renormalize order, e.g.) that hand-picked examples are most likely to miss.

**Scope recommendation:** pin `hypothesis==6.161.5` in `requirements.txt` (or a new `requirements-dev.txt` if the project wants to separate dev-only deps — none exists yet, so adding directly to `requirements.txt` matches the current single-file convention) and use it **only** for the sizer's cap-invariant tests, not as a general replacement for the project's existing parameterized-pytest style elsewhere. This keeps the new dependency's footprint small and the justification tight.

## Q6: Poisoned-List Fixture Design

**Confidence: MEDIUM** — derived directly from D-07's explicit list plus the gate's full check surface (RISK-01); the exact reason-code strings are `[ASSUMED]`, Claude's discretion per CONTEXT.md.

D-07 requires exactly these four outcomes; RISK-01 additionally requires spread-check coverage, which D-07's list does not explicitly enumerate — recommend one additional fixture entry for that check, plus 2-3 clean survivors for contrast. **Important clarification:** the "oversized memecoin allocation" entry is a **sizer** behavior (D-03's 10% memecoin cap), not a **gate** rejection — the gate has no concept of position sizing. This fixture entry should therefore assert a *clip*, not a *rejection*, and the acceptance test (D-07) should exercise the gate and sizer as a two-stage pipeline to cover it correctly.

Recommended fixture (7 entries total):

| # | Candidate | Asset class | Property | Expected outcome | Reason code |
|---|---|---|---|---|---|
| 1 | `ILLQ` | stock | 20d median dollar volume $150,000 (below $1M floor) | **Gate-rejected** | `REJECT_LIQUIDITY` |
| 2 | `NEWTOK/USDT` | memecoin | 5 days of bars (below 30-day floor) | **Gate-rejected** | `REJECT_LISTING_AGE` |
| 3 | `WIDESPRD` | stock | static spread estimate exceeds the per-asset-class max | **Gate-rejected** | `REJECT_SPREAD` |
| 4a | `CORRA` | stock | fabricated 60d returns, score 0.6, correlation vs 4b = 0.85 | **Gate-rejected** (lower score) | `REJECT_CORRELATION` |
| 4b | `CORRB` | stock | fabricated 60d returns, score 0.9, correlation vs 4a = 0.85 | **Gate-accepted** | — |
| 5 | `MEMER/USDT` | memecoin | passes gate; sizer-computed raw weight would be ~25% | **Sizer-clipped** to memecoin 10% aggregate cap | (sizer note, not a gate reason code — e.g. `capped_memecoin_10pct`) |
| 6 | `CLEAN1` | stock | ample volume, 200+ days listed, low correlation, moderate score | **Gate-accepted, sizer-weighted normally** | — |
| 7 | `CLEAN2` | crypto_major | ample volume, old listing, low correlation to all others | **Gate-accepted, sizer-weighted normally** | — |

This gives the acceptance test full coverage of all four RISK-01 gate checks (liquidity, listing age, spread, correlation) plus RISK-02's memecoin cap, while staying a small, hand-auditable, committed fixture (matching the project's existing convention of committed fixtures cross-checked in tests, e.g. `tests/test_kill_conditions.py`'s real-artifact cross-check).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 3.0.5 (pinned, already installed) | Rolling window medians/std/correlation over cached bars | Already the project's dataframe library (`trader/data/api.py` returns a `pd.DataFrame`) `[VERIFIED: requirements.txt]` |
| numpy | ships with pandas 3.0.5, 2.5.1 confirmed installed | Vectorized correlation/volatility math | Already a transitive dependency; no new pin needed `[VERIFIED: pip list in project venv]` |
| sqlite3 (stdlib) | Python 3.14 stdlib | Breaker event log persistence | Matches `trader/data/db.py`'s existing migration/connection pattern exactly |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| hypothesis | 6.161.5 (new, pinned) | Property-based invariant tests for the sizer's cap logic | Only for RISK-04's cap-invariant tests, not a general test-style replacement |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| hypothesis | Hand-written parameterized pytest cases only | Simpler, zero new dependency, but only covers hand-picked scenarios — weaker guarantee for "must never be wrong" code; recommend hypothesis given the project's own stated bar for this phase |
| Event-log breaker schema | Single mutable `breaker_state` row (one row per breaker_type, updated in place) | Simpler to query, but loses the audit trail and makes standing-rule-4 "detect disagreement" harder — an `UPDATE` can silently overwrite prior state with no history to diff against |

**Installation:**
```bash
pip install hypothesis==6.161.5
```

**Version verification:** `pip index versions hypothesis` confirms 6.161.5 as latest `[VERIFIED: PyPI registry]`; official docs fetched from hypothesis.readthedocs.io confirm the library's purpose and active-maintenance status `[CITED: hypothesis.readthedocs.io]`.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| hypothesis | PyPI | 10+ years (long-established) | Very high (millions/month class library) | github.com/HypothesisWorks/hypothesis | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

slopcheck 0.6.1 was installed into the project's `.venv` and run directly (`python -m slopcheck install hypothesis`), returning `[OK]` against the live PyPI registry. `pip index versions hypothesis` was also run independently and returned the same current version (6.161.5), and official docs at hypothesis.readthedocs.io were fetched and confirm the package's identity and purpose — satisfying the stricter bar for `[VERIFIED]` status (official docs + slopcheck, not registry-existence alone).

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────────────────┐
                    │   candidates: list[dict]                │
                    │   {symbol, venue, asset_class, score}    │
                    └───────────────────┬───────────────────┘
                                        │
                                        ▼
   trader/data/api.py, db.py   ┌─────────────────────┐
   (bars cache, instruments) ─▶│  apply_risk_gate()   │──▶ rejected: list[(candidate, reason_code)]
                               │  trader/risk/gate.py │
                               └──────────┬───────────┘
                                        │ accepted (asset_class tagged → EXIT_PROFILE)
                                        ▼
                               ┌──────────────────────┐
   equity, open_positions ────▶│  size_positions()     │──▶ sized positions: list[dict] {symbol, weight}
                               │  trader/risk/sizer.py │       + cash_reserve
                               └──────────────────────┘

   (independent path, same phase, no data dependency on the above)

   ledger / equity series ────▶ ┌────────────────────────┐
   (Phase 2 harness in tests,  │  evaluate_breakers()     │──▶ BreakerState (per breaker_type: tripped/normal)
    Phase 5 paper equity later)│  trader/risk/breakers.py │        │
                               └────────────────────────┘        ▼
                                                          breaker_events table
                                                          (append-only; migrations/0004)
```

### Recommended Project Structure
```
trader/risk/
├── __init__.py
├── config.py        # frozen-style thresholds: liquidity floors, correlation threshold,
│                     # cap percentages, breaker defaults — all named constants, no inline magic numbers
├── gate.py           # apply_risk_gate(candidates, market_data, config) -> (accepted, rejected)
├── sizer.py           # size_positions(scored_candidates, equity, open_positions, config) -> sized positions
└── breakers.py       # evaluate_breakers(equity_curve, trade_history, config) -> BreakerState (pure)
                       # + thin persistence helpers (append_breaker_event, read_breaker_state) using
                       #   trader/data/db.py's existing connection/migration pattern
```

### Pattern 1: Reason-Coded Rejection (mirrors Phase 3's kill-condition philosophy)
**What:** Every rejected candidate carries a machine-readable enum reason code, never a free-text message alone.
**When to use:** Any gate check that can reject a candidate.
**Example:**
```python
# Recommended shape, consistent with the project's existing dict-based
# row conventions (trader/data/db.py returns plain dicts, not ORM objects)
REJECT_LIQUIDITY = "REJECT_LIQUIDITY"
REJECT_LISTING_AGE = "REJECT_LISTING_AGE"
REJECT_SPREAD = "REJECT_SPREAD"
REJECT_CORRELATION = "REJECT_CORRELATION"

def apply_risk_gate(candidates, market_data, config):
    accepted, rejected = [], []
    for candidate in candidates:
        reason = _first_failing_check(candidate, market_data, config)
        if reason is not None:
            rejected.append({**candidate, "reason_code": reason})
        else:
            accepted.append({**candidate, "exit_profile_tag": _resolve_exit_profile(candidate)})
    accepted, rejected = _apply_correlation_check(accepted, rejected, market_data, config)
    return accepted, rejected
```

### Pattern 2: Frozen-Style Config Module (matches `trader/backtest/config.py`'s existing convention)
**What:** All numeric thresholds as named module-level constants (or a `@dataclass(frozen=True)` if grouping is useful), never inline in gate/sizer/breaker logic.
**When to use:** Every threshold in D-02/D-03/D-04.
**Example:** follow `trader/backtest/config.py`'s existing `FEE_TABLE`/`SLIPPAGE_PCT` dict-of-constants style for consistency — this project already has an established pattern for exactly this kind of config module.

### Anti-Patterns to Avoid
- **Reallocating capped weight to other positions:** silently increases another position's risk beyond what its own score/volatility justified — breaks the "caps only remove risk" invariant this research recommends (see Q3).
- **Computing breaker HWM/drawdown over a full future-inclusive equity curve in tests:** identical in kind to a lookahead bug in the backtest iterator; always evaluate incrementally, "as of now" only.
- **Storing a single mutable `breaker_state` row:** loses the audit trail standing rule 4 depends on ("if the system and any external state ever disagree, halt" needs something to diff against).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pairwise/rolling correlation | A custom covariance-matrix loop | `pandas.Series.corr` / `numpy.corrcoef` on date-aligned return series | Already a project dependency; hand-rolled covariance math is a classic source of off-by-one and ddof bugs (the project's own `metrics.py` already pins `ddof=1` explicitly for exactly this reason) |
| Rolling median/std for liquidity and volatility windows | Manual loop over bar lists | `pandas.Series.rolling(window).median()` / `.std()` | Vectorized, tested, and consistent with how `trader/backtest/metrics.py` already builds equity curves from grouped/aggregated data |
| Cap-invariant verification | Hand-picking a dozen example scenarios and hoping they cover the space | `hypothesis` property-based tests | This is explicitly "the code that must never be wrong" per the phase's own specifics — property tests catch the input combinations a human wouldn't think to write |

**Key insight:** every "don't hand-roll" item above already has a working precedent inside this codebase (`trader/backtest/metrics.py`, `trader/backtest/config.py`) — Phase 4 should follow those existing patterns rather than introduce new ones.

## Common Pitfalls

### Pitfall 1: Positional (not date-aligned) correlation between stock and crypto return series
**What goes wrong:** Zipping two return arrays by index instead of by calendar date silently misaligns returns whenever the two assets' trading calendars differ (crypto trades weekends, stocks don't).
**Why it happens:** `numpy.corrcoef(a, b)` doesn't know about dates — it just takes two same-length arrays.
**How to avoid:** Always inner-join on date before computing correlation (see Q2).
**Warning signs:** A correlation test using only same-asset-class pairs (e.g. two stocks) will never catch this bug — the poisoned-list fixture should include a stock/crypto or crypto/crypto correlated pair, not only same-class pairs.

### Pitfall 2: Retrospective drawdown math reused as-is for a live/incremental breaker check
**What goes wrong:** `trader/backtest/metrics.py`'s `max_drawdown()` is correct for post-hoc reporting over a *complete* curve, but calling it with a curve that includes future points inside a breaker-simulation test would let the breaker "see" a future recovery and never trip.
**Why it happens:** The math (`peak = max(peak, value)` per point) is identical whether it is fed a complete curve after the fact or fed incrementally — the bug is entirely about *what data the test fixture hands it*, not the formula itself.
**How to avoid:** Breaker tests must call the evaluation function once per new equity point, in chronological order, never with the full future-inclusive curve in one call.
**Warning signs:** A breaker test that passes the entire equity curve as a single argument and asserts on the final state, rather than stepping through it — this pattern would hide the exact class of lookahead bug the point-in-time iterator (Phase 2) was built to prevent elsewhere in this project.

### Pitfall 3: Sizer's cap order producing a non-deterministic or over-100%-invested result
**What goes wrong:** Applying the memecoin 10% cap before the 50% single-position cap (or interleaving them without a fixed order) can produce different final weights for the same inputs depending on implementation order, or can push total invested weight above 90%.
**Why it happens:** Caps are not commutative when normalization steps are mixed in between them.
**How to avoid:** Follow the exact select→weight→normalize→cap→re-cap→cash-absorbs-remainder order from Q3, and unit-test the worked example verbatim as a golden fixture.
**Warning signs:** A property test (Q5) failing intermittently or only for specific score/volatility combinations is a strong signal the cap order has a hidden interaction bug.

### Pitfall 4: Gate correlation check depending on a `score` field that no upstream component yet produces
**What goes wrong:** D-02's correlation rule needs a numeric score to break ties, but Phase 3's actual strategy contract (`pick_entries(...) -> list[str]`, see `trader/backtest/strategies/momentum.py`) returns only symbol lists — no numeric score exists yet anywhere upstream, and Phase 5's documented pipeline order is "scanner → gate → ranker → sizer" (ranker *after* the gate), which appears to conflict with needing a score *at* gate time.
**Why it happens:** This is a genuine cross-phase contract gap, not an implementation bug — Phase 3 was never asked to produce a score, and Phase 5's ranker is designed to run after the gate.
**How to avoid:** Phase 4 should define `score: float` as a required field on its own candidate-dict input contract (source-agnostic per D-06), decoupled from however an upstream caller derives it — Phase 4's own tests populate it directly in fixtures. See Open Questions below; the planner should decide whether to document this contract gap explicitly for Phase 5 to resolve, or treat it as already resolved by Phase 4 owning the contract.
**Warning signs:** A plan task that imports anything from `trader/backtest/strategies/` directly into `trader/risk/` would violate D-06's "no coupling to specific strategies" and should be flagged in code review.

## Code Examples

### Date-aligned pairwise correlation
```python
# Source: pandas official docs pattern (Series.corr aligns on index automatically
# when both Series share a DatetimeIndex) — trader/data/api.py already returns
# a tz-aware DatetimeIndex DataFrame, so this alignment is "free" if both
# candidates' bars are read via db.read_bars_cache and indexed by ts.
import pandas as pd

def pairwise_correlation(returns_a: pd.Series, returns_b: pd.Series, min_overlap: int = 30) -> float | None:
    aligned = pd.concat([returns_a, returns_b], axis=1, join="inner")
    if len(aligned) < min_overlap:
        return None  # indeterminate — see Q2
    return aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
```

### Trailing median dollar volume (liquidity check)
```python
# Source: standard pandas rolling-window pattern
def trailing_median_dollar_volume(bars_df: pd.DataFrame, window: int) -> float:
    dollar_volume = bars_df["close"] * bars_df["volume"]
    return dollar_volume.tail(window).median()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| N/A — this is greenfield code within an existing project | N/A | N/A | N/A |

**Deprecated/outdated:** None applicable — no prior Phase 4 implementation exists to deprecate.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Stock liquidity floor: $1,000,000/day trailing-20-day median dollar volume | Q1 | If too low, the gate admits genuinely illiquid microcaps that can't be exited cleanly; if too high, it excludes legitimate small-cap runners the Phase 0/3 strategies are built to trade |
| A2 | Crypto-major floor: $5,000,000/day; memecoin floor: $250,000/day (trailing-7-day median quote volume) | Q1 | Memecoin floor especially is a judgment call between "filters dead tokens" and "excludes the exact high-volatility candidates the scanner targets" |
| A3 | Minimum 30-observation overlap for a valid correlation; below that, indeterminate (not rejected) | Q2 | If wrong, could either falsely reject on noisy short-overlap correlations or falsely admit a genuinely correlated pair |
| A4 | Greedy sequential elimination for N-way correlation clusters | Q2 | A different tie-break rule (e.g. reject all-but-the-single-highest-scored in one pass) would produce different accepted sets for 3+-way clusters; low risk since clusters of exactly 2 dominate in practice |
| A5 | 20-day volatility window for sizing, separate from the 60-day correlation window | Q3 | If wrong, sizing may be slower or faster to react to volatility regime shifts than intended; does not affect correctness of caps, only responsiveness |
| A6 | Capped/freed weight flows to cash, never redistributed to other positions | Q3 | This is the single highest-impact assumption in this document — the planner/owner should explicitly confirm this design choice before locking the sizer's algorithm, since a "redistribute to survivors" rule is an equally reasonable alternative reading of the phase document |
| A7 | UTC calendar day as the daily-loss breaker's day boundary | Q4 | Splits a single "bad trading day" across two UTC buckets in the specific edge case described in Q4; low practical impact given the project's NZ-time schedule, but is a real simplification |
| A8 | Breaker HWM recomputed incrementally from the equity series rather than persisted as its own stored value | Q4 | Low risk — this is the safer of the two designs per D-05/standing rule 4, but does mean every evaluation re-scans the equity history (fine at this project's scale) |
| A9 | `score: float` is Phase 4's own required candidate-dict field, populated by whatever upstream caller invokes the gate — decoupled from Phase 3's `pick_entries` output and Phase 5's future ranker | Pitfall 4 / Open Questions | If the planner instead assumes Phase 5's ranker already exists and will supply scores, task sequencing could create a dependency Phase 4 doesn't actually need |

## Open Questions (RESOLVED)

1. **Where does `score` come from at gate-evaluation time, given Phase 5's "scanner → gate → ranker → sizer" pipeline order?**
   - What we know: D-02's correlation rule needs a score to break ties at gate time; Phase 3's strategies don't emit one; Phase 5's own documented order places the ranker *after* the gate.
   - What's unclear: whether this is an intentional design (Phase 4 defines its own lightweight score input, decoupled from the "real" ranker) or a sequencing question Phase 5 needs to resolve later.
   - Recommendation: treat it as Phase 4's own contract (Assumption A9) — the gate/sizer's pure functions simply require a `score: float` field on each candidate dict, and Phase 4's tests populate it directly. Flag this for the owner/planner to confirm, since it has downstream implications for how Phase 5 wires its ranker.
   - **RESOLVED:** Implemented as Phase 4's own candidate-dict contract in `trader/risk/config.py`'s module docstring (source-agnostic `score: float` field, per D-06); no coupling to Phase 3's `pick_entries` or Phase 5's ranker.

2. **Should freed/capped sizer weight ever redistribute to other accepted positions, or always flow to cash?**
   - What we know: the phase document specifies the caps themselves but not an interaction order.
   - What's unclear: whether a "redistribute to survivors" design is what the owner actually intended when caps bind.
   - Recommendation: default to "flows to cash" (Q3/A6) for simplicity and conservatism; confirm with the owner before treating this as locked, since it's the highest-impact assumption in this document.
   - **RESOLVED:** Locked as "flows to cash, never redistributed" for Plan 04-03's sizer implementation, per Q3's select→weight→normalize→cap→re-cap→cash-absorbs-remainder order.

3. **Exact static per-asset-class spread estimates for the max-spread check (RISK-01).**
   - What we know: D-02 says "static per-asset-class estimates for now — live spread checks are a Phase 5 concern."
   - What's unclear: this research did not find or pin specific spread-percentage numbers (analogous to `SLIPPAGE_PCT` in `trader/backtest/config.py`) — the phase document's slippage numbers (stock 0.05%, crypto_major 0.10%, memecoin 4.0%) are a plausible proxy since spread and slippage are related but not identical concepts.
   - Recommendation: the planner should either reuse `trader/backtest/config.py`'s existing `SLIPPAGE_PCT` values directly as spread proxies (simplest, keeps one source of truth) or ask the owner for distinct spread-specific numbers — this research recommends the former for consistency and lower maintenance surface, flagged `[ASSUMED]`.
   - **RESOLVED:** Implemented in `trader/risk/config.py` as `MAX_SPREAD_PCT = dict(SLIPPAGE_PCT)`, importing `SLIPPAGE_PCT` from `trader.backtest.config` directly rather than retyping its values.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pandas | Correlation/volatility/liquidity math | ✓ | 3.0.5 (pinned) | — |
| numpy | Underlying array math | ✓ | 2.5.1 | — |
| sqlite3 (stdlib) | Breaker event log | ✓ | Python 3.14 stdlib | — |
| hypothesis | Sizer cap-invariant property tests | ✓ (installed during this research session; not yet in `requirements.txt`) | 6.161.5 | Fall back to parameterized pytest cases only if the owner declines the new dependency |
| pytest | Test runner | ✓ | 9.1.1 (pinned) | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** `hypothesis` — falls back cleanly to hand-written parameterized pytest cases if the owner prefers not to add a new pinned dependency for this phase.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (pinned in `requirements.txt`) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`) |
| Quick run command | `pytest tests/test_risk_gate.py tests/test_risk_sizer.py tests/test_risk_breakers.py -x` |
| Full suite command | `pytest` (currently 217 tests green; Phase 4 adds new files under `tests/`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RISK-01 | Gate rejects illiquid/new/wide-spread/correlated candidates, tags accepted ones with EXIT_PROFILE | unit | `pytest tests/test_risk_gate.py -x` | ❌ Wave 0 |
| RISK-02 | Sizer enforces top-3, inverse-vol weighting, 50%/10%/10% caps deterministically | unit + property | `pytest tests/test_risk_sizer.py -x` | ❌ Wave 0 |
| RISK-03 | Breakers trip/reset correctly (daily loss, drawdown+manual restart, consecutive loss) | unit + simulation (Phase 2 harness equity curves) | `pytest tests/test_risk_breakers.py -x` | ❌ Wave 0 |
| RISK-04 | Poisoned candidate list produces exactly the expected accept/reject/clip outcomes | acceptance (exit gate) | `pytest tests/test_risk_poisoned_list.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** the relevant single test file above (`-x`, fail-fast)
- **Per wave merge:** `pytest tests/test_risk_*.py`
- **Phase gate:** full `pytest` suite green (218+ tests) before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_risk_gate.py` — covers RISK-01
- [ ] `tests/test_risk_sizer.py` — covers RISK-02 (include `hypothesis`-based cap-invariant tests here if the dependency is approved)
- [ ] `tests/test_risk_breakers.py` — covers RISK-03
- [ ] `tests/test_risk_poisoned_list.py` — covers RISK-04, the D-07 exit-gate acceptance test, using the 7-entry fixture from Q6
- [ ] `migrations/0004_risk_breakers.sql` — new migration file, following the `apply_migrations` naming convention (`trader/data/db.py`)
- [ ] Framework install (if approved): `pip install hypothesis==6.161.5` and add to `requirements.txt`

## Project Constraints (from CLAUDE.md)

- GSD owns `.planning/` project state; this research file and the phase's plan are GSD artifacts — no superpowers-authored planning documents.
- Standing rule 4 ("if the system and the exchange disagree, halt") is directly relevant to the breaker design (Q4) — implemented here as "prefer re-derivable state over a cached mutable value."
- Standing rule 7 ("a phase is DONE when its exit criteria are met, not before") — the poisoned-list acceptance test (RISK-04/D-07) is this phase's literal exit criterion and must be a real, committed, passing test, not a placeholder.
- TDD is the project's stated workflow discipline (`CLAUDE.md`'s GSD workflow section: "Use TDD while executing").
- ASVS V5 (parameterized SQL, never string-interpolated) already established in `trader/data/db.py` — the new `breaker_events` migration/writer must follow the same parameterized-query convention.

## Sources

### Primary (HIGH confidence)
- hypothesis.readthedocs.io — library purpose, current maintenance status
- PyPI registry (`pip index versions hypothesis`) — version 6.161.5 confirmed current
- slopcheck 0.6.1 (installed and run in this session) — `hypothesis` returned `[OK]`
- Direct codebase inspection: `trader/data/db.py`, `trader/data/api.py`, `trader/backtest/config.py`, `trader/backtest/metrics.py`, `trader/backtest/ledger.py`, `trader/backtest/universe.py`, `trader/backtest/strategies/momentum.py`, `migrations/0002_instruments_bars.sql`, `migrations/0003_backtest.sql`, `tests/conftest.py`, `tests/test_frozen_config.py`, `tests/test_kill_conditions.py`, `pyproject.toml`, `requirements.txt`

### Secondary (MEDIUM confidence)
- morpheustrading.com/blog/minimum-trading-volume — retail swing-trading dollar-volume conventions
- trade-ideas.com/help/filter/DV — dollar volume filter definition
- alvarezquanttrading.com/blog/inverse-volatility-position-sizing — inverse-vol formula
- quantinsti.com/blog/risk-parity-portfolio — risk parity / inverse-vol weighting
- Correlation threshold sources (multiple, cross-verified): alphaexcapital.com, guardfolio.ai, portfolio-correlation WebSearch results converging on 0.7-0.85 as the "acting as one risk unit" range
- sqliteforum.com/p/event-sourcing-with-sqlite, sqliteforum.com/p/building-event-sourcing-systems-with — event-log schema pattern

### Tertiary (LOW confidence)
- The specific greedy N-way correlation-cluster elimination algorithm (Q2) — an engineering adaptation, not found verbatim in any external source; flagged in Assumptions Log (A4)
- The "freed weight flows to cash, never redistributed" cap-order design (Q3) — an engineering recommendation, not independently verified; flagged in Assumptions Log (A6, highest-impact assumption in this document)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pandas/numpy already in use; hypothesis verified via official docs + slopcheck + registry
- Architecture: MEDIUM-HIGH — schema/module-layout patterns follow this codebase's own established conventions closely
- Pitfalls: HIGH — each pitfall is either a documented existing project convention (point-in-time discipline, ddof=1 precedent) applied to new code, or a directly-reasoned consequence of the schema/algorithm choices above
- Numeric thresholds (liquidity floors, volatility window, cap-order/cash-absorption design): LOW-MEDIUM — genuine judgment calls flagged throughout for owner confirmation

**Research date:** 26 July 2026
**Valid until:** Stable — no fast-moving dependency in this phase (30+ days; hypothesis release cadence is frequent but the API surface used here, `@given`/`st.floats`, is long-stable)
