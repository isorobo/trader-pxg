# Phase 0: Ground Truth - Research

**Researched:** 26 July 2026
**Domain:** Free-tier market data polling (Yahoo Finance stock screener, CoinGecko crypto movers), Windows Task Scheduler automation, SQLite append-only logging
**Confidence:** MEDIUM

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Stock Gainers Feed**
- **D-01:** Primary source is the Yahoo Finance day-gainers screener (free, no key, JSON). The researcher must confirm the current endpoint shape and rate behaviour, and propose one fallback (e.g. Finviz gainers page) in case Yahoo changes.
- **D-02:** Poll captures the top ~50 gainers per snapshot, not just those above a threshold. Filtering happens at analysis time, never at capture time.

**Crypto Movers Feed**
- **D-03:** CoinGecko `/coins/markets` sorted by 24-hour price change, using a free demo API key (rate limits are generous at one call per 15 minutes). Capture the top ~50 movers per snapshot.
- **D-04:** Record the CoinGecko coin id alongside the symbol — symbols collide on CoinGecko and the id is the stable key.

**Scheduler & Runtime Model**
- **D-05:** Windows Task Scheduler triggers a one-shot poll script every 15 minutes. No long-running daemon — each run opens the DB, polls, writes, exits. Survives reboots without babysitting.
- **D-06:** Missed polls are acceptable and expected (laptop asleep, network down). Each run logs its own timestamp; gaps are visible in the data rather than hidden. The daily report notes coverage (polls completed vs expected).
- **D-07:** A `--once` flag on the script allows manual runs and testing. Task Scheduler setup is documented as a numbered manual step with the exact `schtasks` command.

**Snapshot Schema**
- **D-08:** Capture is append-only and raw: one row per (poll timestamp, source, ticker) with price, % gain, and rank at snapshot time. No deduplication at capture — first-appearance logic and per-ticker aggregation happen in the report layer.
- **D-09:** Rows go to the `snapshots` table in the shared `data/trader.db` (reserved by Phase 1 context D-08). Phase 0 owns the table's schema; Phase 1's database bootstrap must not conflict with it.

**Daily Report**
- **D-10:** The report script answers the exit-criterion question directly: for each ticker flagged this week — what % ended the day up vs dumped from where the scanner saw it? Core columns per ticker: first-seen time, price and % gain at first sight, same-day close, next-day close, return from first-sight to each close.
- **D-11:** Closes are fetched directly (yfinance for stocks, CoinGecko for crypto) until Phase 1's `get_daily_bars` exists; the report migrates to that API once available. The migration is a noted follow-up, not a Phase 0 blocker.
- **D-12:** Output is a dated markdown file in `reports/` plus the summary stats printed to stdout. No dashboards, no HTML — Phase 7 owns dashboards.

### Claude's Discretion
- Exact table DDL, retry/timeout handling on feed calls, report formatting details, log file layout.

### Deferred Ideas (OUT OF SCOPE)
- Report migration to `get_daily_bars` — after Phase 1 completes
- Hosting the logger on an always-on box (VPS/Raspberry Pi) if laptop gaps prove too lossy — revisit after the first two weeks of coverage stats
- Intraday resolution snapshots (more frequent than 15 min) — only if Phase 3 strategies need it
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|--------------|-------------------|
| DATA-01 | Snapshot logger polls a stock gainers feed and CoinGecko top movers every 15 minutes | Architecture Patterns (Pattern 1 adapter, Pattern 3 unconditional polling), Standard Stack (`yfinance` + `finviz` fallback, CoinGecko `/coins/markets`), Environment Availability, Common Pitfalls #1–#4 |
| DATA-02 | Every flagged ticker is logged to SQLite with timestamp, price, and % gain at snapshot time | Architecture Patterns (Pattern 2 WAL mode), Recommended Project Structure (`db.py`), Common Pitfalls #5 (CoinGecko id/symbol), Validation Architecture (DATA-02 test rows) |
| DATA-03 | Daily report shows, for each flagged ticker, the same-day close and next-day close | Code Examples (yfinance close, CoinGecko history), Common Pitfalls #6 (date format), Validation Architecture (DATA-03 test rows) |
| DATA-04 | Logger runs continuously for two weeks minimum and keeps running after that | Common Pitfalls #3–#4 (Task Scheduler reliability, sleep behavior), Validation Architecture (DATA-04 smoke test + coverage-stat phase gate) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

The project root `CLAUDE.md` (`AI TRADRR/CLAUDE.md`) defines standing rules that apply to every phase, including Phase 0:

1. Never edit graduation/kill criteria while looking at results — not applicable to Phase 0 (no strategies yet), included for completeness.
2. Exit profiles lock at entry — not applicable to Phase 0.
3. **API keys never get withdrawal permissions. `.env` is never committed.** Directly applicable: the CoinGecko demo key goes in `.env` (gitignored), never hardcoded or committed. See Security Domain.
4. If the system and the exchange disagree about a position, the system halts — not applicable to Phase 0 (no positions).
5. "It'll probably be fine" = it goes back a phase — applies generally; motivates the smoke-test-first posture for the Yahoo Finance screener (Open Question 1) rather than assuming it works.
6. Real money is Phase 9. Nothing before it touches a cent — Phase 0 has no capital exposure by design.
7. A phase is DONE when its exit criteria are met, not before — Phase 0's exit criterion (two weeks of coverage, real up/down numbers) is intentionally calendar-gated, not code-complete-gated; see Validation Architecture.

The project's GSD workflow section confirms TDD during execution and verification before marking a phase complete — reflected in the Validation Architecture section below.

## Summary

Phase 0 is a small, low-risk data-collection system: a one-shot Python script triggered every 15 minutes by Windows Task Scheduler, writing raw snapshot rows to SQLite, plus a daily report script. The two external dependencies — Yahoo Finance's unofficial day-gainers screener and CoinGecko's free/demo API — are both usable but carry real fragility. Yahoo Finance has no official public API; every access path (`yfinance`, `yahooquery`, raw `query1.finance.yahoo.com` calls) is a scrape wrapper subject to breakage, rate limiting, and cookie/crumb requirements that change without notice. CoinGecko's free Demo plan is stable and well-documented by contrast, with a confirmed base URL, header, and a monthly credit cap that comfortably covers 15-minute polling.

`yfinance` has moved to a 1.x major-version line (verified 1.5.2 on PyPI, 26 July 2026) that includes screener fixes not present in the widely-discussed 0.2.56 GET/POST bug. The safe posture for planning is: treat `yfinance.screen("day_gainers")` as the primary path, write a thin adapter so the fallback (`finviz` PyPI package, or `yahooquery`) can be swapped in without touching the schema, and add a manual smoke-test task early so a live breakage is caught in evening one, not two weeks in.

The scheduler, SQLite, and market-hours questions all have well-established, low-risk answers: wrap the script in a `.bat` launcher that sets the working directory and activates the venv (Task Scheduler's own working-directory handling is unreliable), enable WAL mode with a `busy_timeout` pragma for safe concurrent access between the poller and the report script, and poll unconditionally on a fixed 15-minute cadence with a stored `market_open` flag rather than gating the poll itself — this matches decision D-06 (gaps are visible, not hidden) and avoids a market-calendar dependency Phase 0 does not need.

**Primary recommendation:** Build the poller around `yfinance` (stock) + CoinGecko Demo API (crypto) with a swappable-source adapter pattern, WAL-mode SQLite via plain `sqlite3`, a `.bat`-wrapped Task Scheduler trigger every 15 minutes, and a stored `market_open` boolean rather than market-hours gating.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Stock gainers polling | Backend script (scheduled) | — | One-shot process, no server; Task Scheduler is the orchestrator |
| Crypto movers polling | Backend script (scheduled) | — | Same process/run as stock poll, or a second scheduled task sharing the DB |
| Snapshot persistence | Database (SQLite) | — | `data/trader.db`, shared with Phase 1; append-only writes |
| Daily report generation | Backend script (manual/scheduled) | — | Reads SQLite, fetches closes, writes markdown to `reports/` |
| Close-price lookups (report) | Backend script | External API (yfinance/CoinGecko) | Report script calls out; no caching layer required yet (Phase 1 owns that) |
| Scheduling/orchestration | OS (Windows Task Scheduler) | — | No daemon; D-05 explicitly rejects a long-running process |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `yfinance` | 1.5.2 [VERIFIED: PyPI] | Stock gainers screener + close-price history | Most widely used free Yahoo Finance wrapper; already the Phase 1 D-01 default, so reusing it in Phase 0 avoids a second stock data dependency |
| `requests` | 2.34.2 [VERIFIED: PyPI] | Direct CoinGecko HTTP calls | Simplest, most transparent way to call a documented REST API; no wrapper needed for two endpoints |
| `python-dotenv` | 1.2.2 [VERIFIED: PyPI] | Load `COINGECKO_API_KEY` from `.env` | Matches Phase 1 D-12/D-06 tooling convention |
| `sqlite3` (stdlib) | bundled with Python 3.12 [ASSUMED — stdlib, not registry-versioned] | Snapshot storage | Matches Phase 1 D-09 — no ORM, plain `sqlite3` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `finviz` | 2.0.0 [VERIFIED: PyPI] | Fallback stock gainers source if Yahoo Finance screener breaks | Only invoked by the adapter's fallback path; keep it installed but idle |
| `pytest` | 9.1.1 [VERIFIED: PyPI] | Unit tests for the adapter, schema, and report math | Matches Phase 1 D-06 tooling convention |
| `ruff` | 0.16.0 [VERIFIED: PyPI] | Lint/format | Matches Phase 1 D-06 tooling convention |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `yfinance` screener | `yahooquery.Screener` | Cleaner API surface (350+ predefined screen IDs including `day_gainers`), but it is a second, less-maintained wrapper around the same undocumented Yahoo endpoint — no reliability advantage, adds a dependency. Use only if `yfinance`'s screener breaks and the `finviz` fallback also has gaps. |
| `finviz` scrape fallback | Apify-hosted Finviz scraper API | Apify options need an Apify account/token and are not genuinely free at volume; the `finviz` PyPI package requires no key and is sufficient for a 50-row top-gainers pull every 15 minutes. |
| Direct `requests` to CoinGecko | `pycoingecko` wrapper | `pycoingecko` is a thin wrapper with no material benefit over two direct `requests.get()` calls; adds a dependency for no reduction in complexity. |
| Hardcoded market-hours gate | `pandas_market_calendars` | Correctly handles NYSE holidays and early closes, but Phase 0's D-06 already accepts gaps as visible data — a full calendar library is unnecessary weight for a phase whose job is measuring the scanner, not trading around it. Revisit in Phase 3+ if strategies need exact session boundaries. |

**Installation:**
```bash
pip install yfinance requests python-dotenv finviz pytest ruff
```

**Version verification:** Verified via `pip index versions <pkg>` against PyPI on 26 July 2026 (see table above). `yfinance` is on a 1.x line, not the 0.2.x line commonly discussed in older Stack Overflow / GitHub threads — training data referencing "yfinance 0.2.x screener bugs" is stale; confirm behavior against the installed 1.5.2 before assuming any 0.2.x-era bug report still applies.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|--------------|-----------|-------------|
| yfinance | PyPI | ~9 yrs (since 0.1.x, 2017) | Very high (millions/month) | github.com/ranaroussi/yfinance | [OK] | Approved |
| requests | PyPI | ~15 yrs | Very high | github.com/psf/requests | [OK] | Approved |
| python-dotenv | PyPI | ~10 yrs | Very high | github.com/theskumar/python-dotenv | [OK] — flagged "Name starts with 'python-' — classic LLM naming pattern" but noted as an established package | Approved |
| pandas | PyPI | ~15 yrs | Very high | github.com/pandas-dev/pandas | [OK] | Approved (used only if report formatting benefits from it; not required for Phase 0 core) |
| pytest | PyPI | ~15 yrs | Very high | github.com/pytest-dev/pytest | [OK] | Approved |
| ruff | PyPI | ~4 yrs | Very high | github.com/astral-sh/ruff | [OK] | Approved |
| finviz | PyPI | version history back to 1.0 (multi-year) | Moderate | github.com/mariostoev/finviz | [OK] | Approved — fallback only |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none — `python-dotenv` triggered an informational naming-pattern note, not a suspicion flag; slopcheck rated it [OK] with an explanatory annotation.

slopcheck 0.6.1 installed and ran successfully in this research session (`pip install slopcheck`, then `slopcheck install <pkgs>`). All packages listed above are `[VERIFIED: npm/PyPI registry]`-eligible per the package legitimacy gate for registry existence, but package *choice* (why these specific names, e.g. "use finviz not some other scraper") remains `[ASSUMED]` where sourced from WebSearch rather than official docs — see Assumptions Log.

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────┐
                    │   Windows Task Scheduler     │
                    │  (trigger every 15 minutes)  │
                    └──────────────┬───────────────┘
                                   │ launches
                                   ▼
                    ┌─────────────────────────────┐
                    │  poll.bat  (sets cwd, venv)  │
                    └──────────────┬───────────────┘
                                   │ runs
                                   ▼
                    ┌─────────────────────────────┐
                    │   poll.py --once             │
                    │                              │
                    │  ┌────────────┐ ┌───────────┐│
                    │  │Stock source│ │Crypto      ││
                    │  │adapter     │ │source      ││
                    │  │(yfinance-> │ │adapter     ││
                    │  │ finviz     │ │(CoinGecko  ││
                    │  │ fallback)  │ │ /coins/    ││
                    │  │            │ │ markets)   ││
                    │  └─────┬──────┘ └─────┬──────┘│
                    │        │  normalize    │       │
                    │        └──────┬────────┘       │
                    │               ▼                │
                    │     rows: (ts, source, ticker,  │
                    │     price, pct_gain, rank, ...) │
                    └───────────────┬─────────────────┘
                                    │ INSERT (append-only)
                                    ▼
                    ┌─────────────────────────────┐
                    │  data/trader.db              │
                    │  WAL mode, busy_timeout=5000 │
                    │  table: snapshots            │
                    └──────────────┬───────────────┘
                                   │ SELECT (read-only)
                                   ▼
                    ┌─────────────────────────────┐
                    │  report.py (manual/daily     │
                    │  scheduled run)              │
                    │  1. distinct tickers this wk │
                    │  2. fetch same-day close      │
                    │     (yfinance / CoinGecko     │
                    │      history endpoint)        │
                    │  3. fetch next-day close       │
                    │  4. compute up/down %, write   │
                    └──────────────┬───────────────┘
                                   ▼
                    ┌─────────────────────────────┐
                    │  reports/YYYY-MM-DD.md        │
                    │  + stdout summary stats        │
                    └─────────────────────────────┘
```

### Recommended Project Structure
```
trader/
├── ground_truth/
│   ├── __init__.py
│   ├── sources.py       # StockSource / CryptoSource adapter classes + fallback logic
│   ├── poll.py          # entry point: python -m trader.ground_truth.poll --once
│   ├── db.py            # connection helper, WAL pragma setup, schema DDL
│   └── report.py        # entry point: python -m trader.ground_truth.report [--date YYYY-MM-DD]
├── scripts/
│   └── poll.bat          # Task Scheduler target: cd, venv activate, run poll.py --once
data/
└── trader.db             # gitignored (Phase 1 D-07)
reports/
└── 2026-07-26.md         # gitignored or committed per owner preference — Claude's discretion
tests/
└── test_ground_truth.py
```

### Pattern 1: Source Adapter with Fallback
**What:** Each feed (stock, crypto) is wrapped in a small class exposing one method, e.g. `fetch_top_movers() -> list[dict]`, that internally tries the primary source and falls back on a documented exception type.
**When to use:** Any external scrape-based feed with known fragility (Yahoo Finance screener has no SLA).
**Example:**
```python
# Illustrative pattern, not from official docs — Yahoo Finance has no official API docs.
class StockGainersSource:
    def fetch_top_movers(self, count: int = 50) -> list[dict]:
        try:
            return self._fetch_yfinance(count)
        except Exception as e:
            log.warning("yfinance screener failed (%s), falling back to finviz", e)
            return self._fetch_finviz(count)

    def _fetch_yfinance(self, count):
        import yfinance as yf
        result = yf.screen("day_gainers", count=count)
        return self._normalize_yf(result)

    def _fetch_finviz(self, count):
        from finviz.screener import Screener
        rows = Screener(filters=[], order="Change", signal="Top Gainers")
        return self._normalize_finviz(rows[:count])
```

### Pattern 2: WAL-Mode SQLite for Short-Lived Writers
**What:** Every script opens a fresh connection, sets `journal_mode=WAL` and `busy_timeout` pragmas, writes, and closes.
**When to use:** Any time two independent short-lived processes (the 15-minute poll, the daily report) may touch the same file.
**Example:**
```python
# Source: sqlite.org/wal.html (official docs) + community best practice
import sqlite3

def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn
```

### Pattern 3: Poll Unconditionally, Tag Market State
**What:** The scheduled poll always runs every 15 minutes and always attempts both feeds. A `market_open` boolean (computed with stdlib `zoneinfo`, comparing US/Eastern time against a hardcoded 09:30–16:00 Mon–Fri window) is stored per stock-source row. No NYSE holiday calendar is consulted in Phase 0.
**When to use:** This phase only — a measurement phase where gaps and off-hours noise are acceptable data, per D-06.
**Example:**
```python
from datetime import datetime
from zoneinfo import ZoneInfo

def is_market_hours(now_utc: datetime) -> bool:
    eastern = now_utc.astimezone(ZoneInfo("America/New_York"))
    if eastern.weekday() >= 5:
        return False
    return (9, 30) <= (eastern.hour, eastern.minute) < (16, 0)
```

### Anti-Patterns to Avoid
- **Gating the poll on market hours:** Skipping the stock poll outside 9:30–16:00 ET hides exactly the gap data D-06 wants visible, and complicates the "run forever" requirement with a second failure mode (calendar drift, DST bugs). Poll always; tag instead.
- **Long-running daemon/loop:** D-05 explicitly rejects this. A `while True: sleep(900)` script will not survive reboots, sleep/wake cycles, or crashes as gracefully as a Task-Scheduler-triggered one-shot process.
- **Trusting Task Scheduler's own "Start in" field without a `.bat` wrapper:** Multiple sources confirm Task Scheduler's working-directory and interpreter resolution is inconsistent; a batch file that explicitly `cd /d`s and calls the venv's `python.exe` is the reliable pattern.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stock screener HTTP/auth (crumb, cookies, session) | A custom Yahoo Finance HTTP client | `yfinance` (with `finviz` as fallback) | Yahoo Finance has no official API; crumb/cookie handling is fiddly and changes without notice — let a maintained wrapper absorb that churn |
| Historical daily close lookups | Custom date-indexed CSV cache | `yfinance.Ticker(...).history()` / CoinGecko `/coins/{id}/history` (or `/market_chart/range`) | Both APIs already return exactly the OHLC-by-date shape needed; a hand-rolled cache duplicates Phase 1's planned `get_daily_bars` cache (D-03) |
| Concurrent SQLite access between poller and report | A file lock / mutex layer | SQLite WAL mode + `busy_timeout` | WAL is designed for exactly this reader/writer overlap; a hand-rolled lock adds a new failure mode for no benefit |
| Market-hours calendar | Hardcoded but "smart" holiday list | Nothing in Phase 0 (store `market_open` flag with simple weekday+time check; defer full calendar to a later phase if ever needed) | D-06 tolerates gaps; building holiday-awareness now is speculative complexity for a measurement-only phase |

**Key insight:** Phase 0's entire risk surface is external-API fragility, not algorithmic complexity. The right engineering investment is a swappable adapter and honest logging of failures — not defensive scheduling logic or a bespoke market calendar.

## Common Pitfalls

### Pitfall 1: Yahoo Finance screener silently returns wrong or truncated data
**What goes wrong:** A known `yfinance` issue (reported against 0.2.56, GitHub #2419) had the `Screener` class send GET requests where Yahoo's API expects POST, causing `size`/`offset` parameters to be silently ignored — requests for 250 rows returned only the default 25.
**Why it happens:** `yfinance` scrapes an undocumented internal Yahoo endpoint; Yahoo can change accepted HTTP methods, parameters, or response shape without notice, and the wrapper library lags behind.
**How to avoid:** After installing `yfinance` 1.5.2, write a manual smoke test that requests `count=50` and asserts the response actually contains ~50 rows before trusting the poller. If it silently truncates, switch the primary path to `finviz` or `yahooquery`.
**Warning signs:** Snapshot rows per poll consistently capped at 25 regardless of a `count=50` argument; identical row counts every single poll (suggests a static/fallback response).

### Pitfall 2: Rate limiting / IP blocking (429 errors) from Yahoo Finance
**What goes wrong:** Since November 2024, `yfinance` users have reported a marked increase in `YFRateLimitError` / HTTP 429 responses, especially under rapid/looped requests from a single IP — Yahoo has tightened anti-scraping defenses.
**Why it happens:** `yfinance` is not an official API; Yahoo can rate-limit or temporarily block IPs making frequent automated requests, and residential/laptop IPs are not exempt.
**How to avoid:** Keep the polling interval at 15 minutes (D-05) — this is well below the frequency that triggers most reported 429s. Wrap each Yahoo Finance call in a try/except that logs the failure and lets the poll continue (crypto data still gets logged). Do not add retry-with-backoff loops within a single 15-minute run — a missed poll is acceptable (D-06); a hung script blocking the next scheduled trigger is not.
**Warning signs:** Repeated `YFRateLimitError` in the log; the same error occurring at every single run regardless of time of day (suggests a sustained IP block, not transient rate limiting).

### Pitfall 3: Windows Task Scheduler resolves the wrong Python or working directory
**What goes wrong:** A task configured to run `python.exe script.py` directly often fails with `ModuleNotFoundError` (wrong interpreter — system Python instead of the venv) or `FileNotFoundError` for relative paths (wrong working directory), even though the same command works fine from an interactive terminal.
**Why it happens:** Task Scheduler does not reliably inherit the shell environment or "Start in" directory the way a manually opened terminal does.
**How to avoid:** Point the scheduled task at a `.bat` file that explicitly does `cd /d "C:\path\to\project"` and calls `"C:\path\to\project\.venv\Scripts\python.exe" -m trader.ground_truth.poll --once`, rather than pointing Task Scheduler directly at the interpreter with a relative script path.
**Warning signs:** The task shows "Last Run Result: 0x1" or similar non-zero exit code in Task Scheduler history; manual `.bat` double-click works but the scheduled run does not.

### Pitfall 4: Laptop sleep silently drops scheduled polls
**What goes wrong:** If the laptop is asleep at the trigger time, the poll simply does not run — Task Scheduler does not queue missed triggers by default.
**Why it happens:** Task Scheduler only wakes the computer for a trigger if "Wake the computer to run this task" is explicitly enabled on the Conditions tab, and even then, BIOS/UEFI wake-timer settings can override it.
**How to avoid:** This is expected and acceptable per D-06 ("missed polls are acceptable and expected... gaps are visible in the data rather than hidden"). Do not attempt to force wake-from-sleep — it adds power-management complexity and BIOS-dependent behavior for a benefit D-06 explicitly deems unnecessary. Instead, ensure the daily report's coverage statistic (polls completed vs. expected, per D-06) makes the gap visible and quantifiable.
**Warning signs:** Coverage percentage in the daily report consistently far below 100% during hours the laptop is normally suspended (e.g., overnight) — this is a signal the number is working as intended, not a bug.

### Pitfall 5: CoinGecko symbol collisions corrupt ticker identity
**What goes wrong:** Multiple distinct coins share the same ticker symbol on CoinGecko (e.g., many tokens use "SAFE", "MOON", or similar generic tickers); logging only the symbol makes two unrelated coins indistinguishable in the snapshots table.
**Why it happens:** CoinGecko's `id` field (a slug like `bitcoin`) is the actual unique key; `symbol` is a free-text field with no uniqueness guarantee across the ~15,000+ listed coins.
**How to avoid:** Per D-04, always store the CoinGecko `id` alongside `symbol` in every snapshot row, and use `id` (never `symbol` alone) as the join key when the daily report fetches historical closes via `/coins/{id}/history`.
**Warning signs:** A report row where the "same-day close" value is wildly inconsistent with the "price at snapshot" value for no plausible market reason — likely means the report script fetched the wrong coin's history by symbol.

### Pitfall 6: CoinGecko historical-price date format is DD-MM-YYYY, not ISO
**What goes wrong:** The `/coins/{id}/history` endpoint's `date` query parameter uses `DD-MM-YYYY` format, the reverse of the more common ISO `YYYY-MM-DD`. Passing an ISO-formatted date silently returns wrong-day or error results.
**Why it happens:** CoinGecko's API design predates common convention on this specific endpoint and has never been changed for backward compatibility.
**How to avoid:** When building the report script's crypto same-day/next-day close lookup, format the date explicitly as `DD-MM-YYYY` for this one endpoint (other CoinGecko endpoints, e.g. `market_chart/range`, use Unix timestamps instead — do not assume format consistency across endpoints).
**Warning signs:** Crypto close-price columns in the report are consistently off by one day, or the API returns a 404/empty response for a date that should have data.

## Code Examples

### CoinGecko top 24h crypto movers (Demo API key)
```python
# Source: docs.coingecko.com/v3.0.1/reference/authentication (official docs, confirmed base URL + header)
import requests

BASE_URL = "https://api.coingecko.com/api/v3"

def fetch_top_crypto_movers(api_key: str, count: int = 50) -> list[dict]:
    resp = requests.get(
        f"{BASE_URL}/coins/markets",
        params={
            "vs_currency": "usd",
            "order": "market_cap_desc",     # /coins/markets has no native "24h change desc" order —
            "per_page": 250,                # pull a wide page, then sort client-side by price_change_percentage_24h
            "page": 1,
            "price_change_percentage": "24h",
            "sparkline": "false",
        },
        headers={"x-cg-demo-api-key": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    coins = resp.json()
    coins.sort(key=lambda c: c.get("price_change_percentage_24h") or 0, reverse=True)
    return coins[:count]
```
**Note:** `[CITED: docs.coingecko.com]` confirms base URL, header name, and that `order` has no built-in 24h-change sort option — client-side sort after `price_change_percentage=24h` is the documented workaround pattern seen across multiple community examples `[MEDIUM confidence]`.

### CoinGecko historical price for a specific date (crypto same-day/next-day close)
```python
# Source: docs.coingecko.com/reference/coins-id-history (official docs)
def fetch_crypto_close(coin_id: str, date_ddmmyyyy: str, api_key: str) -> float | None:
    resp = requests.get(
        f"{BASE_URL}/coins/{coin_id}/history",
        params={"date": date_ddmmyyyy, "localization": "false"},  # date format is DD-MM-YYYY, not ISO
        headers={"x-cg-demo-api-key": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("market_data", {}).get("current_price", {}).get("usd")
```

### yfinance same-day / next-day stock close
```python
# Source: yfinance README / Ticker.history() — standard documented usage [CITED: github.com/ranaroussi/yfinance]
import yfinance as yf

def fetch_stock_close(symbol: str, on_date: str) -> float | None:
    # on_date: "YYYY-MM-DD"; yfinance's `end` is exclusive, so request a 1-day window
    hist = yf.Ticker(symbol).history(start=on_date, end=_next_day(on_date))
    if hist.empty:
        return None
    return float(hist["Close"].iloc[0])
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `yfinance` 0.2.x with GET-based Screener (broken size/offset) | `yfinance` 1.x line (verified 1.5.2) | Major version bump post-0.2.66 [VERIFIED: PyPI version history] | Training-data discussion of the GET/POST screener bug (issue #2419, reported against 0.2.56) may no longer apply — confirm on the installed 1.5.2, do not assume the bug is still present |
| `pytz` for timezone handling | stdlib `zoneinfo` (Python 3.9+) | Ongoing ecosystem shift; `pandas_market_calendars` v5+ dropped pytz for zoneinfo | Use `zoneinfo` for the `market_open` tag (Pattern 3) — no extra dependency needed, matches current ecosystem direction |

**Deprecated/outdated:**
- Assuming yfinance's screener is unusable due to the 0.2.56 GET/POST bug: unverified against the current 1.5.2 release; treat as **LOW confidence** until a manual smoke test confirms current behavior (see Pitfall 1).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `yfinance.screen("day_gainers")` works correctly (respects `count`) on the installed 1.5.2 without the GET/POST size-truncation bug reported against 0.2.56 | Common Pitfalls #1, Code Examples | If wrong, the poller silently logs only 25 gainers instead of ~50 (D-02) — must add the manual smoke test as a Wave 0 task, not discover this after two weeks of collection |
| A2 | CoinGecko Demo plan rate limit is approximately 30 calls/min (sources conflicted between 30 and 100 calls/min) | Standard Stack / Package research | If actual limit is lower than assumed, a burst of report-script calls (fetching many tickers' historical closes) could hit 429s — mitigate by checking the CoinGecko developer dashboard after signup, and having the report script pace calls modestly regardless |
| A3 | Windows Task Scheduler "Repeat task every 15 minutes" with `/sc minute /mo 15` reliably fires even through most sleep cycles when "Run task as soon as possible after a scheduled start is missed" is enabled, without needing "Wake the computer" | Common Pitfalls #4 | If wrong (task never catches up after wake), coverage percentage undercounts by more than expected; low risk since D-06 already tolerates gaps, but worth confirming empirically in the first days of running |
| A4 | `finviz` (PyPI, mariostoev/finviz) is the best free fallback for a Yahoo Finance screener outage, over `yahooquery` or an Apify-hosted scraper | Standard Stack / Alternatives Considered | If wrong, planner should budget slightly more time to wire up `yahooquery` instead — low risk, both are viable, this is a preference call not a hard blocker |
| A5 | Recommending unconditional 24/7 polling with a `market_open` tag (rather than gating the poll to market hours) best serves D-06's "gaps visible" intent | Architecture Patterns / Pattern 3 | If the owner actually wants off-hours polls suppressed to save API calls, this is a one-line change (add the gate) with no schema impact — low risk, flagged for confirmation during planning/discuss if not already locked |

**If this table is empty:** N/A — see entries above; all are moderate-to-low risk and none block Phase 0 from starting.

## Open Questions

1. **Does the Yahoo Finance screener actually return ~50 rows correctly on `yfinance` 1.5.2 right now?**
   - What we know: The library has moved past the 0.2.56 release where the GET/POST bug was reported; changelog references screener-related fixes in the 1.0 line.
   - What's unclear: No direct, dated confirmation the specific size-truncation bug is fixed, since Yahoo's endpoint behavior is undocumented and can regress.
   - Recommendation: Planner should include a first-task smoke test (`yf.screen("day_gainers", count=50)` and assert row count) before building the rest of the poller on top of it. If it fails, fall back to `finviz` immediately rather than debugging the wrapper.

2. **Exact CoinGecko Demo plan rate limit (calls/min).**
   - What we know: Multiple sources cite 30 calls/min as the Demo-plan stable rate; one page suggested 100 calls/min; official docs defer to the pricing page and dashboard for exact figures.
   - What's unclear: The authoritative per-minute number without a live dashboard check post-signup.
   - Recommendation: Confirm in the CoinGecko developer dashboard once the demo key is created (a Phase 0 setup task); design the report script to pace calls at well under 30/min regardless, since Phase 0's total call volume (≤ ~100 tickers/day for closes, 1 markets call per 15 min) is far below any plausible limit.

3. **Should the crypto poll also skip anything, or is 24/7 unconditional correct for CoinGecko?**
   - What we know: Crypto markets never close, so there is no equivalent "market hours" question for the CoinGecko leg — 24/7 polling is unambiguously correct there.
   - What's unclear: Nothing — this is settled, included for completeness since Q6 in the phase brief asked about "the stock poll" specifically.
   - Recommendation: No gating on the crypto side; only the stock side carries the market-hours design question (resolved in Pattern 3).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | Entire phase | ✓ (per phase brief: Windows 11, Python 3.12) | 3.12 | — |
| pip / PyPI access | Package install | ✓ (verified live in this research session) | — | — |
| Internet access to `query1/2.finance.yahoo.com` | Stock screener | Not directly testable in this research session (no live network probe run); assumed available on target laptop | — | `finviz` fallback if Yahoo endpoint is blocked/unreachable |
| Internet access to `api.coingecko.com` | Crypto movers | Assumed available; official docs confirm the base URL is publicly reachable | — | none needed — CoinGecko is the sole crypto source |
| Windows Task Scheduler | Scheduling | ✓ (built into Windows 11 per D-05) | OS-native | — |
| SQLite (via Python stdlib `sqlite3`) | Persistence | ✓ (bundled with Python 3.12) | stdlib | — |

**Missing dependencies with no fallback:** none identified.
**Missing dependencies with fallback:** Yahoo Finance screener reachability/reliability — `finviz` package is the documented fallback (see Standard Stack, Pitfall 1).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (matches Phase 1 D-06 convention — no test framework exists yet in this greenfield repo) |
| Config file | none yet — Wave 0 creates `pytest.ini` or `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/ -x -k "not integration"` |
| Full suite command | `pytest tests/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|--------------------|--------------|
| DATA-01 | Poller calls both the stock and crypto source adapters once per invocation | unit (mocked HTTP) | `pytest tests/test_poll.py::test_poll_calls_both_sources -x` | ❌ Wave 0 |
| DATA-02 | Every returned ticker row is written to `snapshots` with timestamp, price, % gain | unit (in-memory/temp SQLite) | `pytest tests/test_db.py::test_snapshot_insert_shape -x` | ❌ Wave 0 |
| DATA-02 | CoinGecko `id` is stored alongside `symbol` (D-04) | unit | `pytest tests/test_sources.py::test_crypto_row_has_coingecko_id -x` | ❌ Wave 0 |
| DATA-03 | Report script computes same-day and next-day close correctly for a known fixture ticker/date | unit (mocked close-price fetch) | `pytest tests/test_report.py::test_report_computes_closes -x` | ❌ Wave 0 |
| DATA-03 | Report output includes a coverage stat (polls completed vs. expected) per D-06 | unit | `pytest tests/test_report.py::test_report_includes_coverage -x` | ❌ Wave 0 |
| DATA-04 | Manual smoke test: `poll.py --once` runs end-to-end against live APIs and writes ≥1 row per source | smoke (manual, not part of `pytest tests/`) | `python -m trader.ground_truth.poll --once` then inspect `data/trader.db` | ❌ Wave 0 — this is the "does Yahoo's screener actually work today" check from Open Question 1 |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x -k "not integration"`
- **Per wave merge:** `pytest tests/`
- **Phase gate:** Full suite green, plus the live smoke test run manually at least once, before `/gsd:verify-work`. Because DATA-04's real exit criterion ("ran for 2+ weeks") cannot be automated-tested at plan time, the phase gate for that specific requirement is a calendar/log check, not a pytest run — the daily report's coverage stat over 14+ days is the evidence.

### Wave 0 Gaps
- [ ] `tests/test_poll.py` — covers DATA-01
- [ ] `tests/test_db.py` — covers DATA-02, includes WAL-mode + busy_timeout pragma assertions
- [ ] `tests/test_sources.py` — covers DATA-02 (CoinGecko id/symbol), and the Yahoo→finviz fallback path
- [ ] `tests/test_report.py` — covers DATA-03
- [ ] `tests/conftest.py` — shared fixtures: temp SQLite db, mocked yfinance/CoinGecko responses
- [ ] Framework install: `pip install pytest` (already in Standard Stack install command)
- [ ] Live smoke test procedure documented in the plan for DATA-01/DATA-04 (manual, not pytest — see above)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|-------------------|
| V2 Authentication | No | Phase 0 has no user-facing auth surface |
| V3 Session Management | No | No sessions — one-shot scripts |
| V4 Access Control | No | Single-operator local machine, no multi-user access model |
| V5 Input Validation | Yes | Validate API response shapes (row count, required fields present) before insert — see Pitfall 1; use parameterized SQL (`?` placeholders), never string-formatted SQL, for all `INSERT`/`SELECT` statements |
| V6 Cryptography | No direct need | The only secret is the CoinGecko Demo API key; store in `.env` (gitignored per standing rule 3), loaded via `python-dotenv` — no custom crypto required |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| SQL injection via ticker/coin-id string interpolation | Tampering | Always use parameterized queries (`cursor.execute("INSERT INTO snapshots (...) VALUES (?, ?, ...)", values)`), never f-string-built SQL, even though ticker symbols are not directly user-supplied — a compromised or malformed API response could otherwise inject SQL |
| API key leakage via committed `.env` or logged request headers | Information Disclosure | `.env` stays gitignored (standing rule 3, already established Phase 1 pattern); ensure log statements never print the full `x-cg-demo-api-key` header value — log "CoinGecko call failed" without dumping request headers |
| Untrusted third-party response data (Yahoo/CoinGecko payloads) treated as fully trusted | Tampering | Validate expected fields exist and are the expected type before writing to SQLite; a malformed/unexpected response should be logged and skipped, not partially inserted |

## Sources

### Primary (HIGH confidence)
- docs.coingecko.com/v3.0.1/reference/authentication — confirmed base URL (`https://api.coingecko.com/api/v3`) and demo-key header (`x-cg-demo-api-key`)
- docs.coingecko.com/reference/coins-id-history — confirmed `DD-MM-YYYY` date format quirk for the historical-price-by-date endpoint
- sqlite.org/wal.html — WAL mode mechanics and reader/writer concurrency guarantees
- PyPI (`pip index versions`) — live-verified current versions of yfinance, requests, python-dotenv, pandas, pytest, ruff, finviz (26 July 2026)
- slopcheck 0.6.1 (installed and run in this session) — package legitimacy scan, all packages [OK]

### Secondary (MEDIUM confidence)
- github.com/ranaroussi/yfinance issue #2419 — GET/POST screener bug, reported against 0.2.56, root cause and workaround documented; status against current 1.5.2 unconfirmed (see Open Question 1)
- yahooquery.dpguthrie.com/guide/screener — confirms `day_gainers` and 350+ predefined screener IDs exist as an alternative wrapper
- coingecko.com/en/api/pricing — Demo plan monthly cap (~10,000 calls) and rate limit (conflicting figures: 30 vs 100 calls/min cited across sources)
- Multiple WebSearch results on yfinance 429/rate-limiting reports since November 2024 (GitHub issues #2125, #2128, #2411, #2567, #2568) — consistent pattern across multiple independent issue reports
- pythontutorials.net, techbloat.com, and related how-to guides — Windows Task Scheduler `.bat`-wrapper pattern, cross-referenced across 3+ independent sources with consistent recommendation

### Tertiary (LOW confidence)
- Apify marketplace pages describing Finviz-scraper-as-a-service — not evaluated in depth since the free `finviz` PyPI package meets the need without a third-party account
- General "yfinance 1.0 changelog" WebSearch summary re: screener fixes — not independently confirmed against the actual CHANGELOG.rst text (fetch attempt would have required a follow-up call not made in this session); treat the "screener sector fixes in 1.0" claim as LOW confidence until the smoke test (Open Question 1) confirms behavior directly

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM — package choices and versions are verified against PyPI, but the core stock-data dependency (Yahoo Finance screener via yfinance) has a documented history of undocumented breakage; the safe pattern (adapter + fallback + smoke test) is HIGH confidence even though the underlying API's stability is not
- Architecture: HIGH — scheduler pattern, WAL-mode SQLite, and adapter pattern are all well-established, low-risk, cross-referenced across multiple independent sources
- Pitfalls: MEDIUM-HIGH — most pitfalls (Task Scheduler working directory, sleep behavior, CoinGecko id/symbol, date format) are confirmed via official docs or multiple independent community reports; the yfinance screener reliability pitfall carries residual uncertainty about current (1.5.2) behavior

**Research date:** 26 July 2026
**Valid until:** 7 days for the Yahoo Finance screener specifics (fast-moving, undocumented, history of breakage) — re-verify before implementation if planning is delayed. 30 days for CoinGecko, SQLite, and Task Scheduler findings (stable, officially documented).
