# Phase 0: Ground Truth - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning

<domain>
## Phase Boundary

A snapshot logger that polls a stock gainers feed and CoinGecko top movers every 15 minutes, logs every flagged ticker to SQLite, and produces a daily report showing where each flagged ticker closed that day and the next. It runs for two weeks minimum and then keeps running forever. No trading, no signals, no strategy logic — this phase only measures what the scanner universe actually does.

</domain>

<decisions>
## Implementation Decisions

Decisions below were auto-selected (recommended defaults) because this session ran non-interactively. Each is a default, not a lock — override any before planning.

### Stock Gainers Feed
- **D-01:** Primary source is the Yahoo Finance day-gainers screener (free, no key, JSON). The researcher must confirm the current endpoint shape and rate behaviour, and propose one fallback (e.g. Finviz gainers page) in case Yahoo changes.
- **D-02:** Poll captures the top ~50 gainers per snapshot, not just those above a threshold. Filtering happens at analysis time, never at capture time.

### Crypto Movers Feed
- **D-03:** CoinGecko `/coins/markets` sorted by 24-hour price change, using a free demo API key (rate limits are generous at one call per 15 minutes). Capture the top ~50 movers per snapshot.
- **D-04:** Record the CoinGecko coin id alongside the symbol — symbols collide on CoinGecko and the id is the stable key.

### Scheduler & Runtime Model
- **D-05:** Windows Task Scheduler triggers a one-shot poll script every 15 minutes. No long-running daemon — each run opens the DB, polls, writes, exits. Survives reboots without babysitting.
- **D-06:** Missed polls are acceptable and expected (laptop asleep, network down). Each run logs its own timestamp; gaps are visible in the data rather than hidden. The daily report notes coverage (polls completed vs expected).
- **D-07:** A `--once` flag on the script allows manual runs and testing. Task Scheduler setup is documented as a numbered manual step with the exact `schtasks` command.

### Snapshot Schema
- **D-08:** Capture is append-only and raw: one row per (poll timestamp, source, ticker) with price, % gain, and rank at snapshot time. No deduplication at capture — first-appearance logic and per-ticker aggregation happen in the report layer.
- **D-09:** Rows go to the `snapshots` table in the shared `data/trader.db` (reserved by Phase 1 context D-08). Phase 0 owns the table's schema; Phase 1's database bootstrap must not conflict with it.

### Daily Report
- **D-10:** The report script answers the exit-criterion question directly: for each ticker flagged this week — what % ended the day up vs dumped from where the scanner saw it? Core columns per ticker: first-seen time, price and % gain at first sight, same-day close, next-day close, return from first-sight to each close.
- **D-11:** Closes are fetched directly (yfinance for stocks, CoinGecko for crypto) until Phase 1's `get_daily_bars` exists; the report migrates to that API once available. The migration is a noted follow-up, not a Phase 0 blocker.
- **D-12:** Output is a dated markdown file in `reports/` plus the summary stats printed to stdout. No dashboards, no HTML — Phase 7 owns dashboards.

### Claude's Discretion
- Exact table DDL, retry/timeout handling on feed calls, report formatting details, log file layout.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and rules
- `# Trader AI — GSD Phases.md` (repo root) — source of truth for Phase 0 scope and exit criteria
- `.planning/REQUIREMENTS.md` — DATA-01…04 requirement definitions
- `.planning/phases/01-accounts-data-plumbing/01-CONTEXT.md` — shared decisions Phase 0 must respect: single `data/trader.db` (D-07/D-08), repo layout and tooling (D-04…D-06), asset-class tagging (D-16)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield. Phase 0 writes the first code in the repo.

### Established Patterns
- Phase 1 context sets the patterns Phase 0 must follow: `trader/` src layout, plain `sqlite3` with WAL, `.env` + python-dotenv, pytest.

### Integration Points
- Shares `data/trader.db` with everything downstream. The `snapshots` table is the first table created; the schema_version/migration mechanism from Phase 1 D-09 should be established here since Phase 0 ships first.
- The daily report is the first consumer of close-price data and later migrates to Phase 1's `get_daily_bars`.

</code_context>

<specifics>
## Specific Ideas

- The owner's framing: "of everything the scanner flagged this week, what % ended the day up vs dumped?" — the report must answer that sentence with real numbers.
- "Keep it running forever — it's free data." Durability beats elegance: append-only writes, tolerate gaps, never lose collected history.
- Phase 0 and Phase 1 run in parallel; Phase 0 must not wait for broker approvals or the data API.

</specifics>

<deferred>
## Deferred Ideas

- Report migration to `get_daily_bars` — after Phase 1 completes
- Hosting the logger on an always-on box (VPS/Raspberry Pi) if laptop gaps prove too lossy — revisit after the first two weeks of coverage stats
- Intraday resolution snapshots (more frequent than 15 min) — only if Phase 3 strategies need it

</deferred>

---

*Phase: 0-Ground Truth*
*Context gathered: 2026-07-26*
