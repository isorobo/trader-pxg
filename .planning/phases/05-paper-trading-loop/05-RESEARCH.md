# Phase 5: Paper Trading Loop - Research

**Researched:** 26 July 2026
**Domain:** IBKR paper-trading API integration, unattended Windows Task Scheduler execution, order idempotency/reconciliation, Telegram alerting
**Confidence:** MEDIUM (HIGH on library/API mechanics verified against official docs; MEDIUM-LOW on IBKR account-specific behaviour that only the owner's live paper account can confirm — see Assumptions Log)

## Summary

Phase 5 wires the existing scanner -> gate -> sizer -> paper-execution pipeline against a real broker connection (IBKR paper account, via IB Gateway) and a simulated crypto ledger, running unattended overnight through Windows Task Scheduler — the same proven pattern as Phase 0's poller. The single hardest constraint this research surfaces: **IBKR paper accounts cannot disable two-factor authentication**, and IBKR expires all session credentials weekly (Sunday ~01:00 ET), so a fully hands-off two-week run is not literally achievable — a five-second mobile-app tap is required once per week. Daily restarts, by contrast, are fully unattended via TWS/Gateway's own built-in auto-restart feature (no re-auth needed except the first login of the week). This must be surfaced to the owner and the planner as a locked assumption, not silently designed around.

The maintained IBKR Python client is `ib_async` (`pip install ib_async`, version 2.1.0), the community-continued successor to the now-inactive `ib_insync` following its original author's death in early 2024. IBKR itself provides no duplicate-order protection — Phase 5 must build idempotency in the application layer using a deterministic `orderRef` string plus a pre-submit check against `reqOpenOrders()`/`fills()`/`executions()` on every guardian and entry-pipeline startup, exactly as D-06 already specifies. `permId` (not `orderId`, which is a per-session sequence, and not `clientId`, which is per-connection) is IBKR's durable, reconnect-and-crash-surviving identifier and is the right join key for reconciliation against local state; `orderRef` is the human-auditable string that should carry the deterministic key.

IBKR's Python API does not support fractional shares for US stocks (only crypto/forex) — the sizer's dollar-based output must be rounded to whole shares before an order is built, a real pitfall given Phase 4's sizer works in dollar/percentage terms. Paper accounts get free 15-20 minute delayed data by default; this is acceptable for daily-bar strategies whose entries fire once at/after the open and whose guardian only needs 5-minute-cadence stop/TP checks, not tick-precision fills. For the crypto simulated leg, reuse the already-installed `ccxt.binance()` public client (no API key, no new dependency) at guardian cadence — it is both the existing data-provenance venue (per `trader/data/crypto_source.py`) and has materially looser rate limits than CoinGecko's free tier, which is already used at a slower 15-minute cadence for the Phase 0 poller.

**Primary recommendation:** Build `trader/paper/` as a thin, testable layer around `ib_async` (mockable `IB` client), with all four Phase 5 loops (entry pipeline, guardian, reconciliation, alerts) as pure-logic functions plus thin I/O adapters — matching the codebase's existing Phase 3/4 style — and treat the weekly IBKR mobile 2FA tap as a pre-accepted, logged exception to the "zero manual interventions" exit criterion rather than a design problem to solve.

## Architectural Responsibility Map

This phase is a desktop automation system, not a client/server web app; tiers are adapted accordingly.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Trading-day/session scheduling | OS Scheduler (Windows Task Scheduler) | Application (calendar helper) | Task Scheduler fires the process; the process itself decides whether today is a live session |
| Entry pipeline (scan->gate->rank->size->order) | Application process (Python, one-shot) | Broker API (IBKR) | Pure logic through Phase 4's gate/sizer, then a thin I/O call to place the order |
| Guardian (exit monitoring) | Application process (Python, one-shot per 5-min tick) | Broker API (IBKR) / ccxt (crypto sim) | Same one-shot-and-exit pattern as Phase 0's poller — no daemon |
| Order idempotency | Application process (deterministic key derivation) | Database (dedupe check) + Broker API (confirm check) | The broker has no dedupe; the app must derive the key and check both local and broker state before submitting |
| Reconciliation | Application process (classification logic) | Database (state) + Broker API (ground truth) | Pure comparison function over two already-fetched snapshots (D-07) |
| Ledger persistence | Database (SQLite WAL) | — | Same shared DB as all prior phases; append-only per existing convention |
| Alerting | External service (Telegram Bot API) | Local log (fallback) | Fire-and-forget; alert failure must never block trading logic (D-11) |
| Gateway session/auth | External process (IB Gateway) + Human | — | D-03 already locks this as a human checkpoint; Phase 5 code only detects and alerts on disconnection, never automates 2FA |

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PAPER-01 | Scanner -> gate -> ranker -> sizer -> paper execution runs on schedule | Task Scheduler pattern (Phase 0 proven); `ib_async.placeOrder`; fractional-share rounding pitfall; RTH-default order behaviour |
| PAPER-02 | Guardian monitors paper positions live and executes exits per profile | Guardian design (self-computed triggers + MKT exit, not resting broker stop orders); 5-min cadence; ccxt crypto price source |
| PAPER-03 | Orders are idempotent via client order IDs, even on paper | `orderRef`/`permId` semantics; no broker-side dedupe; deterministic key + pre-submit check design |
| PAPER-04 | Reconciliation checks internal state against broker state every 60 seconds | `positions()`/`openTrades()`/`fills()` snapshot calls; explainable-vs-unexplained classification rules |
| PAPER-05 | Ledger logs every paper trade exactly as a real one, tagged by strategy and profile | Migration 0005 schema design; reuse of Phase 2's `EXIT_PROFILE`/ledger conventions |
| PAPER-06 | Telegram (or similar) alerts on fills, stops, errors, and heartbeat | Telegram Bot API `sendMessage` shape, rate limits, BotFather token steps |
| PAPER-07 | Loop runs unattended overnight through US market hours (~1:30am-8am NZ) | Weekly 2FA / daily auto-restart mechanics; trading-calendar recommendation; two-week wall-clock gate |

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** The five verified v2 survivors deploy (momentum_stock / choppy_v2 / loose entry variant, five exit-profile configs), each tagged with its own EXIT_PROFILE from its surviving config, locked at entry (standing rule 2). Kill conditions from KILL-CONDITIONS.md are LIVE: the loop evaluates them on rolling paper results and auto-retires a strategy that trips one (standing rule: immediately, no appeals).
- **D-02:** Stocks only for strategy entries in this first paper deployment (all survivors are stock configs). The crypto simulated-ledger leg still ships and is exercised by the guardian/reconciliation machinery (so the plumbing is proven), but no crypto strategy trades until one graduates through the Phase 7 pipeline.
- **D-03:** Stocks: IBKR paper account via the current maintained Python API library (researcher pins: ib_async vs ib_insync successor state) connecting through IB Gateway in paper mode. Gateway install + login is a HUMAN checkpoint (owner has paper account DUR285675).
- **D-04:** Crypto: simulated ledger — fills modelled from live prices with Phase 2's fee/slippage config (Kraken taker + per-class slippage). No Kraken order API calls in Phase 5 at all; Kraken keys are wired read-only for price/balance sanity only if present.
- **D-05:** Windows Task Scheduler tasks (the proven Phase 0 pattern), not a daemon: an entry pipeline run once per trading day shortly after US open (daily-bar strategies decide on yesterday's close, enter at open per the Phase 2 fill convention), and a guardian task every 5 minutes during US market hours (+ 24/7 for the crypto sim) that checks stops/TPs/trails/time-stops and executes exits.
- **D-06:** Idempotency: every order carries a deterministic client order ID derived from (strategy_id, symbol, date, side, intent); resubmission after a crash can never double-order (pinned by tests).
- **D-07:** Reconciliation every 60s while the guardian runs: internal state vs IBKR paper state. ANY unexplained divergence -> halt entries + Telegram alert + `manual_restart_required` (standing rule 4, wired through Phase 4's breakers).
- **D-08:** Phase 4 gate/sizer/breakers are mandatory in-line stages -- no bypass path exists in the code.
- **D-09:** Migration 0005: `paper_orders`, `paper_positions`, `paper_trades` (real-trade format: strategy_id, profile, entry/exit ts+price, qty, fees, slippage, NZD-ready columns), `reconciliation_log`. Same shared DB, WAL.
- **D-10:** The ledger is written exactly as a real one would be (phase doc requirement) -- Phase 9's tax logger extends, never rewrites.
- **D-11:** Telegram bot (token via .env, HUMAN checkpoint): fills, stops, breaker trips, reconciliation failures, and a twice-daily heartbeat. Alert failure never blocks trading logic (fire-and-forget with local log fallback).
- **D-12:** Every run appends to a rotating operations log; the daily report gains a paper-trading section (positions, P&L, breaker state, coverage of scheduled runs) so the two-week unattended window is auditable from disk.

### Claude's Discretion

- Module layout under `trader/paper/`, exact scheduler cadences within the decisions above, retry/backoff details, log formats.

### Deferred Ideas (OUT OF SCOPE)

- Crypto strategy deployment -- via Phase 7 pipeline graduation
- Kraken live order API -- Phase 9
- Intraday strategy support -- needs paid intraday data (owner-deferred)
- Web dashboard -- Phase 7 (simple HTML acceptable there)

## Project Constraints (from CLAUDE.md)

- Standing rule 3: API keys never get withdrawal permissions; `.env` is never committed. Applies to both the Telegram token and any Kraken read-only keys.
- Standing rule 4: If the system and the exchange disagree about a position, the system halts. This is D-07's reconciliation halt, already the locked design.
- Standing rule 6: Real money is Phase 9. Nothing in Phase 5 touches a cent — IBKR connection MUST be paper-mode (port 4002 default, `TradingMode=paper` if IBC is used), never live (4001).
- Standing rule 7: A phase is DONE only when its exit criteria (two consecutive weeks unattended, zero unexplained divergences) are met, not before.
- Existing codebase convention (drafting-style.md does not apply to code, but the codebase's own established pattern, confirmed by reading `trader/risk/gate.py`/`breakers.py`/`trader/ground_truth/poll.py`): pure logic functions with zero I/O, thin persistence/adapter layers, reason codes on rejection, `--once`-and-exit CLI entrypoints (no daemons), frozen config modules, parameterized SQL only.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `ib_async` | 2.1.0 (verified on PyPI, 26 Jul 2026) | IBKR TWS/Gateway API client (connect, place orders, positions, executions) | Community-maintained successor to `ib_insync` after its author's 2024 death; `ib_insync` has had no PyPI release in 12+ months and is inactive [VERIFIED: PyPI + official docs ib-api-reloaded.github.io/ib_async] |
| `ccxt` | 4.5.68 (already pinned in `requirements.txt`) | Live crypto ticker prices for the simulated ledger's fills | Already the project's crypto data-provenance library (`trader/data/crypto_source.py` uses `ccxt.binance()`); no new dependency needed [VERIFIED: existing codebase] |
| `requests` | 2.34.2 (already pinned) | Telegram Bot API `sendMessage` calls | Already a project dependency; Telegram's Bot API is plain HTTPS POST/GET — no SDK needed [CITED: core.telegram.org/bots/api] |
| `python-dotenv` | 1.2.2 (already pinned) | Loads Telegram token / IBKR host-port / optional Kraken keys from `.env` | Already the project's established secrets-loading pattern (`trader/ground_truth/sources.py`) [VERIFIED: existing codebase] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pandas-market-calendars` | 5.4.0 (verified on PyPI, transitively pins `exchange-calendars>=3.3`, pandas-3.0-compatible) | NYSE trading-day/session-time source for scheduling decisions (is today a trading day, what are today's open/close times) | Use to decide whether the entry-pipeline Task Scheduler run should act at all, and to compute the guardian's "US market hours" window precisely (including early-close days) rather than a fixed 09:30-16:00 assumption [CITED: pandas-market-calendars/exchange-calendars official docs + changelog, surfaced via WebSearch, slopcheck OK] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pandas-market-calendars` | Hand-rolled static NYSE holiday list | Zero new dependency, but requires manual annual maintenance (floating holidays: MLK, Washington's, Memorial, Labor Day Mondays; Good Friday) and misses early-close days entirely — a correctness gap for a money-adjacent (even paper) system |
| `pandas-market-calendars` | `ib_async`'s own `reqContractDetails` `tradingHours`/`liquidHours` fields | Authoritative (IBKR's own session data, confirmed via official TWS API docs) and needs no extra dependency, but requires an active Gateway connection to answer "is today a trading day" — a chicken-and-egg problem for the scheduling decision itself. Recommend using this as a **second, live gate** immediately before any order submits, in addition to (not instead of) the calendar package |
| `ib_async` | `ibapi` (IBKR's own raw low-level Python API) | Officially supported by IBKR directly, but far more boilerplate (manual callback wiring, no Pythonic `async`/sync convenience layer); `ib_async` wraps it and is what the retail-algo community actually uses |
| Resting native IBKR `STP` stop orders at the broker | Guardian self-computes trigger conditions and sends a marketable `MKT` order on trigger | Native stop orders can fill between reconciliation polls with the guardian never having decided anything — a legitimate "explainable divergence" case, but a needless one when the guardian already polls every 5 minutes. Self-computed triggers keep the guardian as the single source of truth for every exit, matching Phase 2's backtest exit-engine logic exactly and simplifying reconciliation to "did my own last submitted order fill," not "did the broker do something I didn't initiate" [ASSUMED — architectural recommendation, not sourced from IBKR docs; grounded in D-07's reconciliation model] |

**Installation:**
```bash
pip install ib_async pandas-market-calendars
```

**Version verification:** Confirmed via `pip index versions ib_async` (2.1.0 latest, 26 Jul 2026) and `pip index versions pandas-market-calendars` (5.4.0 latest). Neither package is currently installed in the project's own `.venv` (`AI TRADRR/.venv`) — both must be added to `requirements.txt` during Phase 5 execution. `ccxt`, `requests`, `python-dotenv` are already installed and pinned; no action needed for those three.

## Package Legitimacy Audit

`slopcheck` 0.6.1 was available and ran successfully (`slopcheck install <pkg>` — note: this project's `slopcheck` build does not support a `--json` flag; plain-text output used instead).

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `ib_async` | PyPI | Forked from `ib_insync` (2017 origin) under new org in 2024; actively released through 2026 (2.1.0) | Not machine-verified this session (slopcheck does not surface a download count in this build); GitHub org `ib-api-reloaded` is the community-recognized successor, corroborated by multiple independent sources | github.com/ib-api-reloaded/ib_async | OK | Approved |
| `pandas-market-calendars` | PyPI | Long-established (`rsheftel/pandas_market_calendars`, active since ~2016) | Not machine-verified this session | github.com/rsheftel/pandas_market_calendars | OK | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

Both packages passed `slopcheck install <pkg>` with an `[OK]` verdict and installed cleanly from PyPI in a scratch check. Per the package-name-provenance rule, `ib_async`'s identity as the correct/intended package (not a slopsquat of a similarly-named package) is additionally corroborated by directly fetching its own official documentation site (`ib-api-reloaded.github.io/ib_async`), so it is tagged `[VERIFIED: PyPI + official docs]` above rather than merely `[ASSUMED]`. `pandas-market-calendars`'s official-docs corroboration in this session came via WebSearch snippets that quoted its readthedocs/changelog content rather than a direct `WebFetch` of the primary docs page — tagged `[CITED]` rather than fully `[VERIFIED]` to reflect that shallower verification depth.

## Architecture Patterns

### System Architecture Diagram

```
[Windows Task Scheduler]
        |
        |--(once/trading day, ~shortly after US open)--> [entry_pipeline.py --once]
        |                                                       |
        |                                                       v
        |                                        [pandas-market-calendars: is today
        |                                         a trading day? if not -> exit 0]
        |                                                       |
        |                                                       v
        |                                    [scanner (existing sources)] --candidates-->
        |                                    [Phase 4 risk gate] --accepted-->
        |                                    [ranker] --ranked--> [Phase 4 sizer] --sized-->
        |                                                       |
        |                                                       v
        |                                    [idempotency: build deterministic orderRef;
        |                                     check local DB + ib_async reqOpenOrders()/
        |                                     fills() for an existing match]
        |                                                       |
        |                                    no match found -----+----- match found
        |                                           |                        |
        |                                           v                        v
        |                              [ib_async.placeOrder, MKT/paper,   [skip; log
        |                               RTH-default, whole shares only]    already-submitted]
        |                                           |
        |                                           v
        |                              [migration 0005: paper_orders row]
        |                                           |
        |                                           v
        |                              [Telegram alert: fill/error] (fire-and-forget)
        |
        |--(every 5 min, market hours + 24/7 crypto sim)--> [guardian.py --once]
        |                                                       |
        |                                                       v
        |                              [read open paper_positions from DB]
        |                                                       |
        |                          +----------------------------+----------------------------+
        |                          v                                                         v
        |             [stocks: ib_async positions()/                          [crypto sim: ccxt.binance()
        |              latest price via delayed data]                          fetch_ticker() live price]
        |                          |                                                         |
        |                          v                                                         v
        |             [evaluate exit conditions vs locked EXIT_PROFILE:                      |
        |              stop / TP / trail / time-stop / eod_flat] <------------------------------
        |                          |
        |            trigger? --no--> done                 trigger? --yes--> [submit MKT exit
        |                                                                     order via idempotency
        |                                                                     gate, same as entry]
        |                                                                              |
        |                                                                              v
        |                                                          [paper_trades row: entry+exit,
        |                                                           fees, slippage, P&L]
        |
        |--(every 60s during guardian run window)--> [reconcile.py]
        |                                                       |
        |                                                       v
        |                              [snapshot A: local DB open orders/positions]
        |                              [snapshot B: ib_async positions()/openTrades()/fills()]
        |                                                       |
        |                                                       v
        |                              [classify divergence: explainable (fill landed between
        |                               polls, matches a known orderRef) vs unexplained
        |                               (position/order the system never initiated)]
        |                                                       |
        |                          explainable --> reconciliation_log row, continue
        |                          unexplained --> halt entries (Phase 4 breaker) +
        |                                          Telegram alert + manual_restart_required
        |
        +--(twice daily)--> [heartbeat Telegram message + ops log append (D-12)]
```

### Recommended Project Structure

```
trader/paper/
├── __init__.py
├── config.py            # ports (4002 paper), cadences, .env var names -- frozen, no secrets
├── calendar_.py          # pandas-market-calendars wrapper: is_trading_day(), session_window()
├── broker_ibkr.py        # thin ib_async adapter: connect/disconnect, place_order, snapshot()
├── broker_crypto_sim.py  # ccxt.binance() price fetch + Phase 2 fee/slippage fill model
├── idempotency.py        # pure: build_order_ref(strategy_id, symbol, date, side, intent)
├── entry_pipeline.py     # orchestrates scanner->gate->ranker->sizer->submit, --once CLI
├── guardian.py           # orchestrates exit-condition eval + submit, --once CLI
├── reconcile.py          # pure: classify(local_snapshot, broker_snapshot) -> divergences
├── ledger.py             # migration-0005 table writers (paper_orders/positions/trades)
├── alerts.py             # Telegram fire-and-forget sender + local-log fallback
└── ops_log.py            # rotating operations log appenders (D-12)

migrations/
└── 0005_paper_trading.sql   # paper_orders, paper_positions, paper_trades, reconciliation_log

scripts/
├── paper_entry.bat / paper_entry_task.xml    # Task Scheduler wiring, Phase 0 pattern
└── paper_guardian.bat / paper_guardian_task.xml
```

### Pattern 1: Deterministic idempotency key, checked in two places before every submit

**What:** Build `orderRef` as a fixed-format string from `(strategy_id, symbol, date, side, intent)` — e.g. `f"{strategy_id}:{symbol}:{date}:{side}:{intent}"`. Before calling `placeOrder`, check (a) the local `paper_orders` table for an existing row with this key, and (b) a live `ib.reqOpenOrders()` / `ib.fills()` call for a matching `orderRef` — because a crash could have submitted the order to IBKR before the local DB write committed.

**When to use:** Every entry and every guardian-triggered exit, no exceptions (D-06's "even on paper — build the habit now").

**Example:**
```python
# Source: interactivebrokers.github.io/tws-api/open_orders.html (permId/orderRef
# both persist across reconnects and processes; orderId does not).
order_ref = f"{strategy_id}:{symbol}:{date}:{side}:{intent}"

existing_local = ledger.find_by_order_ref(conn, order_ref)
if existing_local is not None:
    return existing_local  # already handled this key locally

ib.reqOpenOrders()  # populate ib.openTrades() / ib.fills() for this session
matching_live = [t for t in ib.fills() if t.execution.orderRef == order_ref]
if matching_live:
    ledger.record_from_live_fill(conn, matching_live[0])  # heal local state
    return matching_live[0]

order = MarketOrder(action, quantity)
order.orderRef = order_ref
trade = ib.placeOrder(contract, order)
```

### Pattern 2: Guardian is the single source of truth for exits (no resting broker stop orders)

**What:** The guardian, on each 5-minute tick, re-evaluates the position's locked `EXIT_PROFILE` (stop/TP/trail/time-stop/eod_flat — the same dataclass and logic Phase 2's exit engine already implements) against the latest available price, and only then submits a marketable order. No `STP`/`STP LMT` order is ever left resting at IBKR.

**When to use:** All guardian-driven exits, both the IBKR stock leg and the crypto sim leg.

**Example:**
```python
# Source: reuse of trader/backtest/config.py's EXIT_PROFILE (already frozen,
# already the exit-profile locking mechanism per standing rule 2).
from trader.backtest.config import EXIT_PROFILE

def check_exit(position: dict, profile: EXIT_PROFILE, current_price: float, today: date) -> str | None:
    """Returns a reason code ('stop', 'tp', 'trail', 'time_stop', 'eod_flat') or None."""
    pnl_pct = (current_price - position["entry_price"]) / position["entry_price"]
    if profile.stop_pct is not None and pnl_pct <= profile.stop_pct:
        return "stop"
    if profile.tp_pct is not None and pnl_pct >= profile.tp_pct:
        return "tp"
    if profile.max_hold_days is not None:
        held_days = (today - position["entry_date"]).days
        if held_days >= profile.max_hold_days:
            return "time_stop"
    return None
```

### Pattern 3: Reconciliation as a pure classification function over two snapshots

**What:** Fetch local DB state and broker state independently, then feed both into a pure function that returns a classification per position/order — never mutate state as a side effect of fetching.

**When to use:** Every 60-second reconciliation tick (D-07), matching the existing `evaluate_breakers`/`apply_risk_gate` pure-function style already established in `trader/risk/`.

**Example:**
```python
# Pattern mirrors trader/risk/breakers.py's evaluate_breakers: pure function,
# caller supplies pre-fetched snapshots, no I/O inside.
def classify_divergence(local_positions: dict, broker_positions: dict, known_order_refs: set) -> list[dict]:
    divergences = []
    for symbol, broker_qty in broker_positions.items():
        local_qty = local_positions.get(symbol, 0)
        if broker_qty == local_qty:
            continue
        # Explainable only if the delta corresponds to a fill this system
        # itself submitted and is still catching up on recording.
        if _delta_matches_a_known_order_ref(symbol, broker_qty, local_qty, known_order_refs):
            divergences.append({"symbol": symbol, "class": "explainable", "action": "log"})
        else:
            divergences.append({"symbol": symbol, "class": "unexplained", "action": "halt"})
    return divergences
```

### Anti-Patterns to Avoid

- **Automating IBKR 2FA:** Do not attempt to script around IBKR's mobile-app two-factor approval. It is a per-account security control that cannot be disabled on paper accounts, and IBC/any automation tool explicitly cannot complete it — the human must tap approve on their phone. Design the weekly restart around this, don't fight it.
- **Trusting a cached "current position" column:** Mirror `trader/risk/breakers.py`'s discipline — always re-derive reconciliation state from a fresh snapshot pair, never trust a previous poll's cached row (the same lookahead-adjacent trap the module docstring already warns about for the breaker's high-water mark).
- **Dollar-sizing straight into an IBKR order without rounding:** Phase 4's sizer outputs dollar/percentage amounts; IBKR's API does not support fractional US-stock shares. Round down to whole shares before constructing the order, and re-verify the resulting notional still respects the sizer's caps (a rounded-down share count under-uses the allocated cash, which is safe; never round up).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Talking to IBKR's TWS/Gateway socket protocol | A custom socket client for the IB API wire protocol | `ib_async` | Community-maintained wrapper around IBKR's official `ibapi`; handles the full callback/event machinery, reconnect helpers, and typed Order/Contract/Execution objects |
| NYSE trading-day/holiday/early-close determination | A hand-maintained holiday date list | `pandas-market-calendars` (`get_calendar("NYSE")`) | Correctly handles floating holidays and early closes without annual manual upkeep; pandas-3.0-compatible as of `exchange-calendars>=3.3` |
| Duplicate-order prevention | A custom distributed lock or sequence-number scheme | Deterministic `orderRef` + pre-submit dual check (local DB + live `reqOpenOrders()`/`fills()`) | IBKR provides no dedupe of its own; the two-check pattern above is the minimum needed to survive a crash mid-submit, and matches the codebase's existing "re-derive from source of truth, never trust a cache" discipline |
| Telegram bot messaging | A Telegram SDK/wrapper library | Plain `requests.post` to `https://api.telegram.org/bot<token>/sendMessage` | The Bot API is a simple HTTPS endpoint; the project already depends on `requests` and this avoids an extra dependency for ~10 lines of code |

**Key insight:** Every "don't hand-roll" item above already has a project-internal precedent for the *pattern* even where the specific tool is new: Phase 0 already solved unattended-Windows-Task-Scheduler-execution; Phase 4 already solved pure-function-plus-thin-persistence; Phase 1/2 already solved fee/slippage-aware fill modelling. Phase 5's job is to extend those patterns to a live (paper) broker connection, not invent new ones.

## Common Pitfalls

### Pitfall 1: Treating the weekly IBKR 2FA requirement as a bug to fix

**What goes wrong:** Time is spent trying to find a way to fully automate IBKR Gateway login for a paper account, including researching IBC/Docker-based "headless" setups, on the assumption that 2FA can be bypassed.
**Why it happens:** IBKR live accounts *can* disable 2FA in some configurations, and this gets conflated with paper accounts, which as of the most recent published guidance cannot.
**How to avoid:** Design the two-week unattended window around one required weekly human touchpoint (Sunday ~01:00 ET credential reset -> a mobile approval, most likely landing NZ Sunday afternoon/evening given the ~17-19hr offset from ET). Log this touchpoint explicitly in the ops log (D-12) as a pre-accepted exception, distinct from an unplanned manual intervention.
**Warning signs:** Planning tasks that mention "IBC config for zero-touch weekly login" without a corresponding note that 2FA itself still needs a human tap.

### Pitfall 2: Fractional-share sizing silently truncated or rejected by IBKR

**What goes wrong:** The sizer computes a dollar allocation (e.g. `$3,412.50 / $87.30 = 39.09` shares); passed straight to `ib_async`'s `Order.totalQuantity` as a float, IBKR's API either rejects the order or (for a handful of specific IBKR fractional-eligible symbols only) silently fills a fractional amount that then doesn't match the sizer's caps math.
**Why it happens:** IBKR's fractional-share support is real but narrow — cryptocurrencies and forex only, per official IBKR documentation; equities are excluded from API-driven fractional trading.
**How to avoid:** Round the sizer's share count down to the nearest whole share before constructing any stock order; re-check the resulting notional still clears Phase 4's position-cap checks (a smaller actual notional than sized never violates a cap; only an upward rounding could).
**Warning signs:** A stock order rejected with an IBKR error mentioning "fractional" or "size increment"; a paper fill quantity that doesn't match the local `paper_orders` row's requested quantity.

### Pitfall 3: Native broker stop orders creating unexplained-looking divergences

**What goes wrong:** If a native IBKR `STP` order is left resting at the broker (instead of the guardian self-computing and submitting exits), it can fill between two 60-second reconciliation polls without the guardian ever having "decided" anything — the reconciliation function then sees a position change with no matching local order-submission event and classifies it `unexplained`, tripping a halt for a benign, correctly-functioning stop.
**Why it happens:** Conflating "the exit logic is defined" (Phase 2's `EXIT_PROFILE`) with "the exit is executed by the broker automatically" — these are different design choices, and only the second one creates this specific reconciliation ambiguity.
**How to avoid:** Never rest native stop/TP orders at IBKR for guardian-managed positions (Pattern 2 above); the guardian is the sole decision-maker and sole order-submitter for every exit.
**Warning signs:** A reconciliation `unexplained` classification whose broker-side position change exactly matches a stop/TP level the guardian's own `EXIT_PROFILE` would have triggered on the next tick anyway.

### Pitfall 4: Delayed market data mistaken for real-time, then blamed for "wrong" fills

**What goes wrong:** IBKR paper accounts receive free 15-20 minute delayed data by default (not real-time) unless the owner's live account already carries a market-data subscription that paper trading is permitted to share. A guardian evaluating stop/TP levels against a 15-20-minute-stale price will occasionally "trigger late" relative to the true current price.
**Why it happens:** `reqMarketDataType(3)` (delayed) is the silent default for an unsubscribed paper account; nothing errors, it just quietly returns stale-by-construction quotes.
**How to avoid:** For daily-bar strategies with 5-minute-cadence guardian checks and stop/TP thresholds on the order of multiple percent (not sub-1% scalping), a 15-20 minute data lag is immaterial — accept delayed data explicitly (log it as a known characteristic, not silently), rather than paying for a live data subscription this phase doesn't need. Revisit only if Phase 8's intraday signal expansion ever ships (explicitly out of scope for Phase 5).
**Warning signs:** A guardian exit price in the ledger that looks "off" versus what a live quote would have shown at the same wall-clock timestamp — check whether this is explained by delayed-data lag before treating it as a bug.

### Pitfall 5: `orderId`/`clientId` reused as the idempotency key instead of `orderRef`/`permId`

**What goes wrong:** `orderId` is a per-session sequence number (obtained via `nextValidId`/`reqIds`) and `clientId` identifies a *connection*, not an *order* — neither is guaranteed to be reproducible or matchable across a crash-and-restart of the Phase 5 process, even though both persist in some sense within a single continuous session.
**Why it happens:** `orderId` "looks like" the natural unique key because it's the first identifier a new integrator encounters in the placeOrder flow.
**How to avoid:** Use the deterministic, self-derived `orderRef` string as the cross-process/cross-crash idempotency key (it round-trips through `Execution.orderRef` and `openOrder` callbacks), and `permId` as the durable IBKR-assigned account-wide identifier for reconciliation joins — never `orderId` alone for either purpose.
**Warning signs:** Idempotency tests that pass within a single test-process run but would silently double-order if the process restarted mid-flight (i.e., tests that never simulate a fresh `ib_async.IB()` connection object).

## Code Examples

### Telegram fire-and-forget alert

```python
# Source: core.telegram.org/bots/api (sendMessage method) + rate-limit
# guidance (avoid >1 msg/sec per chat; respect 429 retry_after).
import logging
import requests

log = logging.getLogger(__name__)

def send_telegram_alert(token: str, chat_id: str, text: str) -> bool:
    """Fire-and-forget: never raises. Returns False (and logs) on any failure
    so the caller's trading logic is never blocked by an alert failure (D-11)."""
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5,
        )
        response.raise_for_status()
        return True
    except Exception as error:
        log.warning("Telegram alert failed (%s: %s): %s", type(error).__name__, error, text)
        return False
```

### NYSE trading-day check for the entry pipeline gate

```python
# Source: pandas-market-calendars official docs (rsheftel/pandas_market_calendars).
import pandas_market_calendars as mcal

def is_us_trading_day(check_date) -> bool:
    nyse = mcal.get_calendar("NYSE")
    schedule = nyse.schedule(start_date=check_date, end_date=check_date)
    return not schedule.empty
```

### IBKR paper connection (port 4002, never 4001)

```python
# Source: interactivebrokers.github.io general Gateway port convention;
# ib_async docs confirm default Gateway port 4001 for LIVE -- paper mode
# uses 4002 (owner-facing checkpoint: confirm in Gateway's own Configure
# > API > Settings dialog at install time, since this is a HUMAN checkpoint
# per D-03, not something Phase 5 code can verify unattended).
from ib_async import IB

PAPER_PORT = 4002  # standing rule 6: never 4001 (live) in this phase

ib = IB()
ib.connect("127.0.0.1", PAPER_PORT, clientId=5)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `ib_insync` (erdewit) | `ib_async` (ib-api-reloaded org) | Renamed/continued after erdewit's death, early 2024 | Any Phase 5 code, tutorials, or Stack Overflow answers referencing `ib_insync` should be read as applying to `ib_async` with import-name and (rarely) minor API changes — `ib_insync` itself will not receive further updates |

**Deprecated/outdated:**
- `ib_insync`: inactive, no PyPI release in the past 12+ months per registry inspection; do not add as a new dependency even though far more existing tutorials reference it by name.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | IBKR paper accounts cannot disable 2FA (as of the most recent published guidance found) | Summary, Pitfall 1 | If the owner's specific account configuration differs, the "one weekly human tap" design constraint may be unnecessary — but designing for it is a safe over-approximation, not a functional risk, since the code that "detects and alerts on Gateway disconnection" is needed regardless |
| A2 | The guardian should self-compute exit triggers and submit MKT orders rather than resting native IBKR stop orders at the broker | Pattern 2, Pitfall 3 | This is an architectural recommendation grounded in reconciliation-simplicity reasoning, not sourced from IBKR docs. If the owner prefers native resting stops for latency reasons, the reconciliation classifier's "explainable" rule set must be widened accordingly — a real design fork the planner should confirm |
| A3 | 15-20 minute delayed market data is acceptable for this phase's guardian cadence and strategy profiles | Pitfall 4 | If a future exit-profile ever uses a sub-1%-band stop or the owner wants live data for peace of mind, delayed data could produce a materially late exit; low risk given current survivor configs' stop/TP magnitudes (multi-percent per KILL-CONDITIONS.md's drawdown levels) |
| A4 | `pandas-market-calendars` is the right weight/complexity tradeoff over a hand-rolled holiday list | Standard Stack, Alternatives Considered | If the owner prefers zero new dependencies over correctness on early-close days, a lightweight hardcoded list is a legitimate fallback — flagged for planner/owner confirmation, not unilaterally decided here |
| A5 | IBKR's weekly credential reset timing (~01:00 ET Sunday) maps to a specific NZ wall-clock window that the owner can reliably be awake for | Pitfall 1 | Timing math (ET to NZT offset, which shifts with each hemisphere's independent DST calendar) was not independently re-verified this session against a live calendar tool; if wrong, the "one weekly tap" could land at an inconvenient NZ hour, which is an ops-scheduling problem for the owner, not a code risk |

## Open Questions

1. **Does the weekly IBKR mobile 2FA approval count against the phase's "zero manual interventions" exit criterion?**
   - What we know: The exit criterion (05-CONTEXT.md) says "two consecutive weeks unattended, zero manual interventions, zero unexplained state divergences," and IBKR paper accounts cannot avoid a weekly re-auth tap.
   - What's unclear: Whether the owner intends "manual intervention" to mean "any human action" (in which case the criterion is currently unachievable as literally worded) or "any human action taken to fix a problem" (in which case a scheduled, expected, logged weekly tap is not an intervention in the relevant sense).
   - Recommendation: Planner should make this an explicit, named exception in the phase plan's exit-criteria wording, logged via D-12's ops log with a distinct `scheduled_auth` action type separate from `manual_restart_required`, and confirm the reading with the owner before treating a two-week run as passed or failed on this technicality.

2. **Should Kraken's read-only wiring (D-04) participate in reconciliation at all, or purely as a balance sanity check with no effect on halts?**
   - What we know: D-04 says Kraken keys are wired "read-only for price/balance sanity only if present" and crypto never places real orders in Phase 5.
   - What's unclear: Whether a Kraken balance mismatch (e.g., the owner manually moves funds) should ever trigger the same halt-and-alert path as an IBKR divergence, or whether it is purely informational.
   - Recommendation: Default to informational-only (log to `reconciliation_log` with a `venue="kraken_readonly"` tag, never trigger a breaker), since D-04 explicitly scopes Kraken out of order-affecting logic this phase; confirm with the owner if this default is wrong.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `ib_async` | PAPER-01, 02, 03, 04 (IBKR connection) | ✗ (not in project `.venv`) | — (2.1.0 on PyPI) | Install during Phase 5 execution; no viable fallback library for this project's chosen broker |
| `pandas-market-calendars` | PAPER-01, 07 (scheduling) | ✗ (not in project `.venv`) | — (5.4.0 on PyPI) | Hand-rolled static holiday list (Alternatives Considered) |
| `ccxt` | PAPER-02 (crypto sim prices) | ✓ | 4.5.68 | — |
| `requests` | PAPER-06 (Telegram) | ✓ | 2.34.2 | — |
| `python-dotenv` | Secrets loading (Telegram token, IBKR host/port, optional Kraken keys) | ✓ | 1.2.2 | — |
| IB Gateway (paper mode) | PAPER-01 through 04 (the actual broker connection) | ✗ (not yet installed per 05-CONTEXT.md D-03) | — | None — this is a HUMAN checkpoint (D-03); Phase 5 code cannot substitute for it. Blocks any live-against-paper-account testing until installed and logged in |
| Telegram bot token | PAPER-06 | ✗ (no bot created yet) | — | HUMAN checkpoint (D-11); code can be built and unit-tested with a mocked `requests.post` in the meantime |
| Kraken API keys | D-04's read-only sanity check | Pending (per additional_context: "Kraken keys pending") | — | If absent at execution time, the read-only Kraken sanity check is simply skipped/logged as unavailable — never a hard blocker, since D-04 already scopes it as optional ("if present") |

**Missing dependencies with no fallback:**
- IB Gateway install + paper-mode login (D-03's human checkpoint) — blocks all live-connection testing/execution of PAPER-01 through 04 until complete.
- Telegram bot token (D-11's human checkpoint) — blocks live alert delivery (PAPER-06) until complete; does not block building/testing the alert code itself.

**Missing dependencies with fallback:**
- `ib_async`, `pandas-market-calendars`: both installable via `pip install` at execution time, already verified available on PyPI and slopcheck-clean.
- Kraken API keys: optional per D-04; absence degrades gracefully.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (already pinned in `requirements.txt`) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`) |
| Quick run command | `pytest -x -q tests/paper/` (once the directory exists) |
| Full suite command | `pytest` (currently 347 tests; Phase 5 adds `tests/paper/*` alongside) |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PAPER-01 | Pipeline runs scanner->gate->ranker->sizer->execution in order, whole-share rounding applied | integration (mocked `ib_async.IB`) | `pytest tests/paper/test_entry_pipeline.py -x` | ❌ Wave 0 |
| PAPER-02 | Guardian evaluates locked `EXIT_PROFILE` correctly per profile type (stop/tp/trail/time_stop/eod_flat) against a mocked price feed | unit | `pytest tests/paper/test_guardian.py -x` | ❌ Wave 0 |
| PAPER-03 | Same `(strategy_id, symbol, date, side, intent)` always yields the same `orderRef`; a simulated crash-and-resubmit never double-orders | unit | `pytest tests/paper/test_idempotency.py -x` | ❌ Wave 0 |
| PAPER-04 | `classify_divergence` correctly labels explainable vs unexplained cases across a fixture matrix of snapshot pairs | unit | `pytest tests/paper/test_reconcile.py -x` | ❌ Wave 0 |
| PAPER-05 | Migration 0005 tables accept inserts matching a real-trade-format row shape; round-trip read matches write | integration (DB) | `pytest tests/paper/test_paper_migration.py -x` | ❌ Wave 0 |
| PAPER-06 | `send_telegram_alert` posts the expected payload shape; failure path logs and returns `False` without raising | unit (mocked `requests.post`) | `pytest tests/paper/test_alerts.py -x` | ❌ Wave 0 |
| PAPER-07 | Ops-log coverage report correctly flags a missed scheduled run; trading-day gate correctly skips a holiday fixture date | unit | `pytest tests/paper/test_calendar.py -x` | ❌ Wave 0 |

**Manual/live-only (not automatable):** IB Gateway paper login itself; the first live paper order round-trip against the owner's actual DUR285675 account; the two-consecutive-week unattended wall-clock gate (this phase's equivalent of Phase 0's two-week gate) — these are checkpoints, not unit tests, and must appear as explicit `checkpoint:human-verify` gates in the plan.

### Sampling Rate

- **Per task commit:** `pytest -x -q tests/paper/`
- **Per wave merge:** `pytest` (full 347+ suite)
- **Phase gate:** Full suite green, plus the two-week live/manual clock, before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/paper/__init__.py` + `tests/paper/conftest.py` — shared fixtures, including a fake/mock `ib_async.IB` object (no real network/Gateway connection in any automated test)
- [ ] `tests/paper/test_entry_pipeline.py` — covers PAPER-01
- [ ] `tests/paper/test_guardian.py` — covers PAPER-02
- [ ] `tests/paper/test_idempotency.py` — covers PAPER-03
- [ ] `tests/paper/test_reconcile.py` — covers PAPER-04
- [ ] `tests/paper/test_paper_migration.py` — covers PAPER-05
- [ ] `tests/paper/test_alerts.py` — covers PAPER-06
- [ ] `tests/paper/test_calendar.py` — covers PAPER-07
- [ ] Framework install: `pip install ib_async pandas-market-calendars` — required before any of the above can import real (mocked-at-the-boundary) client types

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes (indirectly) | IB Gateway login/2FA is IBKR's own control surface, not this codebase's; Phase 5 code never stores or handles IBKR credentials itself (Gateway holds the session, API connects to localhost only) |
| V3 Session Management | yes | `ib_async` connection objects should be explicitly disconnected/reconnected on error, never left in an ambiguous half-open state; reconnect logic must re-run the idempotency pre-submit check (Pattern 1) before resuming any pending action |
| V4 Access Control | no | Single-operator system, no multi-user access control surface in this phase |
| V5 Input Validation | yes | Reuse `trader/risk/config.py`-style frozen constants and parameterized SQL (already the established pattern in `trader/risk/breakers.py`'s `append_breaker_event`); never string-format a symbol/order-ref into a SQL statement |
| V6 Cryptography | no | No new cryptographic operations in this phase; `.env`-sourced secrets (Telegram token, Kraken keys) are used only as opaque bearer values passed to `requests`/`ccxt`, never logged (standing rule 3) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| Secret leakage via logs (Telegram token, Kraken key printed in an exception traceback) | Information Disclosure | Never interpolate raw `.env` values into log messages or Telegram alert text; log only symbolic references (e.g. "Telegram send failed") per the existing codebase convention of "no secrets in logs" |
| Replay/double-submission of an order after a crash | Tampering (of internal state, not the broker) | Pattern 1's dual pre-submit check (local DB + live broker query) is the mitigation; this is the entire point of D-06 |
| Reconciliation false-negative (a real unexplained divergence misclassified as explainable, masking a live problem) | Repudiation / Tampering | Keep the classification rule set narrow and conservative — default to `unexplained` (halt) unless a divergence positively matches a known local `orderRef`/`permId`, never the reverse default |
| SQL injection via a symbol/reason string sourced from an external feed (scanner tickers, Telegram-relayed text) | Tampering | Parameterized queries only, exactly as `trader/risk/breakers.py`'s `append_breaker_event` already demonstrates project-wide |

## Sources

### Primary (HIGH confidence)
- `ib-api-reloaded.github.io/ib_async/` — ib_async's own official docs site, fetched directly: version 2.1.0, connection API, Order/Execution/Trade/Position class fields, `positions()`/`openTrades()`/`fills()`/`executions()` methods
- `interactivebrokers.github.io/tws-api/order_submission.html` — orderId/nextValidId/clientId semantics, persistence between TWS sessions
- `interactivebrokers.github.io/tws-api/open_orders.html` — reqOpenOrders/reqAllOpenOrders/reqAutoOpenOrders, permId as the durable cross-reconnect identifier
- `interactivebrokers.github.io/tws-api/order_limitations.html` — confirms no documented duplicate-order protection exists in the API itself
- `pip index versions ib_async` / `pip index versions pandas-market-calendars` (registry checks, run directly) — 2.1.0 and 5.4.0 confirmed current
- `slopcheck install ib_async pandas-market-calendars` — both `[OK]`, run directly this session
- `core.telegram.org/bots/api` (surfaced and cross-referenced) — Bot API `sendMessage` shape, rate limits (30 msg/sec global, ~1/sec/chat, 429 + `retry_after`)

### Secondary (MEDIUM confidence)
- WebSearch cross-referencing ib_async/ib_insync succession story (multiple independent sources: PyPI project page, GitHub discussion, Snyk advisor) — author's 2024 death, community continuation under `ib-api-reloaded` org
- WebSearch on IBKR paper-account 2FA (cannot be disabled) and IBC's documented inability to automate 2FA approval — cross-referenced across `github.com/IbcAlpha/IBC` userguide (fetched directly) and multiple community sources agreeing on the weekly-reset/daily-auto-restart split
- WebSearch on IBKR fractional-share API limitation (equities excluded, crypto/forex only) — IBKR's own `interactivebrokers.com/en/trading/fractional-trading.php` referenced in search results, corroborated by community discussion (`ib_insync` GitHub discussions)
- WebSearch on `pandas-market-calendars`/`exchange-calendars` pandas-3.0 compatibility — official changelog content surfaced via search, not independently re-fetched

### Tertiary (LOW confidence)
- ET-to-NZT weekly-reset timing window (Open Question / A5) — not independently re-verified against a live timezone calculation this session; flagged for planner/owner confirmation rather than stated as fact

## Metadata

**Confidence breakdown:**
- Standard stack (ib_async, pandas-market-calendars, ccxt/requests/dotenv reuse): HIGH — direct registry checks, slopcheck, and official-docs fetches for the two new packages
- Architecture (idempotency, reconciliation, guardian-as-sole-decision-maker): MEDIUM — the IBKR field semantics (orderRef/permId/orderId) are HIGH confidence (official docs), but the guardian-vs-native-stop-order design choice (A2) is an internal architectural recommendation, not an externally sourced fact
- Pitfalls (2FA, fractional shares, delayed data): MEDIUM-HIGH — each corroborated by IBKR's own documentation or multiple independent community sources, but none independently verified against the owner's specific DUR285675 paper account behaviour

**Research date:** 26 July 2026
**Valid until:** ~30 days for library versions (IBKR/ib_async release cadence is moderate); the IBKR account-behaviour findings (2FA, delayed data, fractional shares) are policy-level and change rarely, but should be re-confirmed directly against the owner's account once Gateway is installed (the D-03 human checkpoint is also the natural point to re-verify these assumptions empirically)
