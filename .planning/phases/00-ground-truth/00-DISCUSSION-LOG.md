# Phase 0: Ground Truth - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-26
**Phase:** 0-ground-truth
**Areas discussed:** Stock gainers feed, Crypto movers feed, Scheduler & runtime model, Snapshot schema, Daily report
**Mode:** Auto-selected recommended defaults (non-interactive session). Every selection is overridable before planning.

---

## Stock Gainers Feed

| Option | Description | Selected |
|--------|-------------|----------|
| Yahoo Finance day-gainers screener | Free, no key, JSON; fragile to endpoint changes — fallback required | ✓ |
| Finviz gainers page scrape | Free but HTML scraping; kept as fallback | |
| Alpaca movers API | Free key but adds an account dependency Phase 0 does not need | |

**Choice:** Yahoo day-gainers with a researcher-validated fallback; capture top ~50 raw, filter at analysis time.

---

## Crypto Movers Feed

| Option | Description | Selected |
|--------|-------------|----------|
| CoinGecko /coins/markets by 24h change | Free demo key; one call per poll fits limits; stable coin ids | ✓ |
| CoinGecko trending endpoint | Popularity-based, not % gain — wrong signal | |
| CoinMarketCap API | Free tier tighter; second provider without benefit | |

**Choice:** CoinGecko markets endpoint, top ~50 by 24h change, coin id recorded as the stable key.

---

## Scheduler & Runtime Model

| Option | Description | Selected |
|--------|-------------|----------|
| Windows Task Scheduler, one-shot script | Survives reboots; no daemon; gaps visible and acceptable | ✓ |
| Long-running APScheduler daemon | Dies silently on reboot/sleep; worse on a laptop | |
| VPS from day one | Cost and setup before the data proves worth it | |

**Choice:** Task Scheduler every 15 minutes; missed polls logged as gaps; coverage reported daily; VPS deferred until gap stats justify it.

---

## Snapshot Schema

| Option | Description | Selected |
|--------|-------------|----------|
| Append-only raw rows per poll | One row per (ts, source, ticker); dedupe in reports | ✓ |
| First-appearance-only logging | Loses the time series of how gainers evolve intra-day | |

**Choice:** Append-only capture into the shared `snapshots` table in `data/trader.db`.

---

## Daily Report

| Option | Description | Selected |
|--------|-------------|----------|
| Markdown report + stdout stats, direct close fetch | Answers the exit question now; migrates to get_daily_bars after Phase 1 | ✓ |
| Wait for Phase 1 data API | Blocks Phase 0 on Phase 1 — phases are meant to run in parallel | |
| HTML dashboard | Phase 7 owns dashboards | |

**Choice:** Dated markdown in `reports/`; per-ticker first-seen vs same-day and next-day close; weekly % up vs dumped summary.

---

## Claude's Discretion

- Table DDL, feed retry/timeout handling, report formatting, log layout.

## Deferred Ideas

- Report migration to `get_daily_bars` (after Phase 1)
- Always-on hosting if laptop coverage gaps are too lossy
- Sub-15-minute snapshot resolution
