# Phase 1: Accounts & Data Plumbing - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning

<domain>
## Phase Boundary

All access sorted before it is needed: broker and exchange accounts opened, trade-only API keys issued, a historical daily-bars source wired up, the Python repo initialized, and SQLite in place. The exit criterion is concrete: one function call returns historical daily bars for any US stock and any major crypto pair. Building scanners, backtests, or strategies belongs to later phases.

</domain>

<decisions>
## Implementation Decisions

Decisions below were auto-selected (recommended defaults) because this session ran non-interactively. Each is a default, not a lock — override any of them before `/gsd:plan-phase 1` and the planner will follow the edit.

### Historical Data Source
- **D-01:** US stock daily bars come from yfinance — free, no key, sufficient for swing/long-term daily bars. The researcher must confirm current rate limits and reliability on Windows.
- **D-02:** Crypto daily bars come through CCXT. Kraken's public OHLC endpoint caps history (~720 candles), so deep daily history for majors may pull from a second CCXT-supported venue; the researcher must confirm the best free source for 3+ years of daily candles. Fees still model as Kraken (0.16/0.26%) per the phase document.
- **D-03:** Every fetched bar is cached in SQLite. The public API reads cache first and fetches on miss, so backtests never depend on a live connection.

### Repo Structure & Tooling
- **D-04:** One repository for all phases, single Python package (`trader/`) with a src layout. No microservices, no monorepo tooling.
- **D-05:** Plain `venv` + `pip` + `requirements.txt` — simple and Windows-friendly. Python 3.12.
- **D-06:** pytest for tests, ruff for lint/format, python-dotenv for config loading.

### Database Layout
- **D-07:** One SQLite file at `data/trader.db`, WAL mode enabled. The `data/` directory is gitignored.
- **D-08:** Initial tables: `instruments` (symbol, asset_class, venue), `bars` (venue, symbol, timeframe, ts, o, h, l, c, volume — unique on the first four), and `snapshots` (reserved for the Phase 0 logger, which shares this database).
- **D-09:** Schema versioning via a small `schema_version` table and ordered SQL migration files. No ORM — plain `sqlite3` with thin helpers.

### Data Access API Shape
- **D-10:** The exit-criterion function: `get_daily_bars(symbol, start=None, end=None) -> DataFrame` with columns `ts, open, high, low, close, volume`. Asset class resolves from the instruments table (fallback: explicit `asset_class=` argument), and routing picks the stock or crypto fetcher.
- **D-11:** Return type is a pandas DataFrame indexed by date, UTC timestamps. Later phases (point-in-time iterator) build on this shape.

### Memecoin Handling
- **D-15:** The memecoin universe is Kraken-listed tokens only (DOGE, SHIB, PEPE, BONK, WIF, and similar). On-chain/DEX tokens are out of scope — no venue access, and the Phase 4 risk gate would reject them on volume and listing age.
- **D-16:** `instruments.asset_class` distinguishes `stock`, `crypto_major`, and `memecoin`, with an `override` column for manual reclassification. Classification happens at insert time via a market-cap/category heuristic (CoinGecko category as source); the researcher confirms the exact heuristic. Slippage models, exit profiles, and the 10% memecoin cap in later phases all key off this tag.
- **D-17:** Memecoin daily bars flow through the same CCXT → SQLite path as majors. Short history for recent listings is expected and stored as-is — the risk gate's min-listing-age check consumes it in Phase 4.
- **D-18:** The Phase 1 exit criterion stays "majors work with one function call"; memecoins must work through the same call but do not gate phase completion.

### Secrets & Account Setup
- **D-12:** All keys live in `.env` (gitignored, standing rule 3). A committed `.env.example` documents the expected names: `KRAKEN_API_KEY`, `KRAKEN_API_SECRET`, `IBKR_*`, `TELEGRAM_*` (future).
- **D-13:** Kraken API keys are created with trade and query permissions only — withdrawal permission stays off, and the plan includes a manual verification step for this.
- **D-14:** Account applications (IBKR + paper account, Kraken, Independent Reserve KYC) are human tasks. The plan tracks them as a checklist with "submitted" recorded as progress; code work proceeds in parallel and never blocks on approvals.

### Claude's Discretion
- Exact library versions, module naming inside `trader/`, migration file mechanics, and DataFrame validation details.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and rules
- `# Trader AI — GSD Phases.md` (repo root) — the owner's full phase document; source of truth for Phase 1 scope, exit criteria, and the standing rules
- `.planning/REQUIREMENTS.md` — ACCT-01…07 requirement definitions
- `.planning/PROJECT.md` — constraints (security, capital, tax) and key decisions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield repository. The only file is the phase document at the repo root.

### Established Patterns
- None yet. Phase 1 sets the patterns (src layout, plain sqlite3, cache-first data access) that later phases inherit.

### Integration Points
- The Phase 0 snapshot logger will share `data/trader.db` and the repo. Phase 1 must create the database bootstrap in a way Phase 0 can reuse (shared connection helper, shared migrations).

</code_context>

<specifics>
## Specific Ideas

- The phase document names the venues exactly: IBKR (paper first), Kraken (trade-only keys), Independent Reserve (NZD ramp, needed only at Phase 9 but KYC starts now).
- "Decide on Polygon.io later for intraday" — daily bars only in this phase.
- The exit criterion is a single function call; treat it as the acceptance test for the whole phase.

</specifics>

<deferred>
## Deferred Ideas

- Polygon.io (or other paid intraday data) — explicitly deferred by the owner; revisit before intraday strategies
- Postgres/Timescale migration — only when SQLite hurts
- Phase 0 snapshot logger build — Phase 0 scope; Phase 1 only leaves the database ready for it
- Telegram alerting — Phase 5 scope; `.env.example` reserves the key names now
- DEX/on-chain memecoin venue — new capability, its own phase if ever wanted; current universe is Kraken-listed only

</deferred>

---

*Phase: 1-Accounts & Data Plumbing*
*Context gathered: 2026-07-26*
