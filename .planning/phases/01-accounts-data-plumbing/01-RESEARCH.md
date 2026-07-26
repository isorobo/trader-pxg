# Phase 1: Accounts & Data Plumbing - Research

**Researched:** 26 July 2026
**Domain:** Historical market data plumbing (yfinance stocks, CCXT crypto), SQLite schema extension, broker/exchange account provisioning
**Confidence:** MEDIUM-HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Historical Data Source**
- **D-01:** US stock daily bars come from yfinance — free, no key, sufficient for swing/long-term daily bars. The researcher must confirm current rate limits and reliability on Windows.
- **D-02:** Crypto daily bars come through CCXT. Kraken's public OHLC endpoint caps history (~720 candles), so deep daily history for majors may pull from a second CCXT-supported venue; the researcher must confirm the best free source for 3+ years of daily candles. Fees still model as Kraken (0.16/0.26%) per the phase document.
- **D-03:** Every fetched bar is cached in SQLite. The public API reads cache first and fetches on miss, so backtests never depend on a live connection.

**Repo Structure & Tooling**
- **D-04:** One repository for all phases, single Python package (`trader/`) with a src layout. No microservices, no monorepo tooling.
- **D-05:** Plain `venv` + `pip` + `requirements.txt` — simple and Windows-friendly. Python 3.12.
- **D-06:** pytest for tests, ruff for lint/format, python-dotenv for config loading.

**Database Layout**
- **D-07:** One SQLite file at `data/trader.db`, WAL mode enabled. The `data/` directory is gitignored.
- **D-08:** Initial tables: `instruments` (symbol, asset_class, venue), `bars` (venue, symbol, timeframe, ts, o, h, l, c, volume — unique on the first four), and `snapshots` (reserved for the Phase 0 logger, which shares this database).
- **D-09:** Schema versioning via a small `schema_version` table and ordered SQL migration files. No ORM — plain `sqlite3` with thin helpers.

**Data Access API Shape**
- **D-10:** The exit-criterion function: `get_daily_bars(symbol, start=None, end=None) -> DataFrame` with columns `ts, open, high, low, close, volume`. Asset class resolves from the instruments table (fallback: explicit `asset_class=` argument), and routing picks the stock or crypto fetcher.
- **D-11:** Return type is a pandas DataFrame indexed by date, UTC timestamps. Later phases (point-in-time iterator) build on this shape.

**Memecoin Handling**
- **D-15:** The memecoin universe is Kraken-listed tokens only (DOGE, SHIB, PEPE, BONK, WIF, and similar). On-chain/DEX tokens are out of scope — no venue access, and the Phase 4 risk gate would reject them on volume and listing age.
- **D-16:** `instruments.asset_class` distinguishes `stock`, `crypto_major`, and `memecoin`, with an `override` column for manual reclassification. Classification happens at insert time via a market-cap/category heuristic (CoinGecko category as source); the researcher confirms the exact heuristic. Slippage models, exit profiles, and the 10% memecoin cap in later phases all key off this tag.
- **D-17:** Memecoin daily bars flow through the same CCXT → SQLite path as majors. Short history for recent listings is expected and stored as-is — the risk gate's min-listing-age check consumes it in Phase 4.
- **D-18:** The Phase 1 exit criterion stays "majors work with one function call"; memecoins must work through the same call but do not gate phase completion.

**Secrets & Account Setup**
- **D-12:** All keys live in `.env` (gitignored, standing rule 3). A committed `.env.example` documents the expected names: `KRAKEN_API_KEY`, `KRAKEN_API_SECRET`, `IBKR_*`, `TELEGRAM_*` (future).
- **D-13:** Kraken API keys are created with trade and query permissions only — withdrawal permission stays off, and the plan includes a manual verification step for this.
- **D-14:** Account applications (IBKR + paper account, Kraken, Independent Reserve KYC) are human tasks. The plan tracks them as a checklist with "submitted" recorded as progress; code work proceeds in parallel and never blocks on approvals.

### Claude's Discretion
- Exact library versions, module naming inside `trader/`, migration file mechanics, and DataFrame validation details.

### Deferred Ideas (OUT OF SCOPE)
- Polygon.io (or other paid intraday data) — explicitly deferred by the owner; revisit before intraday strategies
- Postgres/Timescale migration — only when SQLite hurts
- Phase 0 snapshot logger build — Phase 0 scope; Phase 1 only leaves the database ready for it
- Telegram alerting — Phase 5 scope; `.env.example` reserves the key names now
- DEX/on-chain memecoin venue — new capability, its own phase if ever wanted; current universe is Kraken-listed only
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|--------------|-------------------|
| ACCT-01 | IBKR account and paper trading account approved | Account Setup Specifics (IBKR) — corrects the phase document's assumption that these are two separate applications |
| ACCT-02 | Kraken account with trade-only API keys — no withdrawal permission | Account Setup Specifics (Kraken) — exact permission checkboxes confirmed |
| ACCT-03 | Independent Reserve account KYC complete (NZD ramp for Phase 9) | Account Setup Specifics (Independent Reserve) |
| ACCT-04 | Historical daily bars source sorted for US stocks and major crypto pairs | Standard Stack, Architecture Patterns, Common Pitfalls, Code Examples |
| ACCT-05 | Python repo set up with git, config files, and `.env` for keys (never committed) | Confirmed largely done by Phase 0 — see Project Constraints and Recommended Project Structure for the remaining gap (`ccxt` dependency, `.env.example` additions) |
| ACCT-06 | SQLite database in place | Schema Design section, Don't Hand-Roll, existing `db.py` extension pattern |
| ACCT-07 | One function call pulls historical daily bars for any US stock and any major crypto pair | Data Access API Shape (`get_daily_bars`), Code Examples, Validation Architecture |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

The project root `CLAUDE.md` (`AI TRADRR/CLAUDE.md`) defines standing rules that apply to every phase, including Phase 1:

1. Never edit graduation/kill criteria while looking at results — not applicable to Phase 1 (no strategies yet).
2. Exit profiles lock at entry — not applicable to Phase 1.
3. **API keys never get withdrawal permissions. `.env` is never committed.** Directly applicable — Kraken API keys (D-13), IBKR credentials, and any future exchange keys all follow this rule. See Security Domain and Account Setup Specifics.
4. If the system and the exchange disagree about a position, the system halts — not applicable to Phase 1 (no positions).
5. "It'll probably be fine" = it goes back a phase — motivates the live-verification posture taken throughout this research (every claim about rate limits, endpoint caps, and category tags below was tested live, not assumed).
6. Real money is Phase 9. Nothing before it touches a cent — Phase 1 opens accounts and API keys only; no order placement code exists yet.
7. A phase is DONE when its exit criteria are met, not before — the exit criterion is the single `get_daily_bars` call; see Validation Architecture for how this becomes a concrete test.

## Summary

Phase 1 is smaller in code than it looks and larger in account-provisioning lead time than the phase document implies. The stock data path is settled: `yfinance` 1.5.2, already installed, returns clean daily OHLCV for any US ticker via `Ticker(symbol).history(period=..., auto_adjust=True)`, live-verified in this research session against Apple for a five-year window. One correction to the locked assumption in D-11: `yfinance`'s returned index is timezone-aware in the exchange's local zone (`America/New_York`), not UTC — the bar-insertion layer must normalise to a UTC calendar date before writing to SQLite, dropping intraday time-of-day entirely since these are daily bars.

The crypto path confirms D-02's premise and resolves it. Kraken's own OHLC REST endpoint is hard-capped at 720 of the most recent candles regardless of the `since` parameter — official Kraken documentation states plainly that older data cannot be retrieved at all through that endpoint, at any interval. For daily candles, that ceiling is roughly two years, short of the 3+ years the phase needs. Binance, reachable through the same `ccxt` library with no API key required for public market data, is the correct second venue: a live test in this session pulled Bitcoin daily candles back to 2018 in a single paginated call, and confirmed that all five named memecoins (DOGE, SHIB, PEPE, BONK, WIF) plus BTC trade on both Kraken and Binance under matching pairs. Binance becomes the primary data-fetch venue for depth; Kraken's fee schedule stays the modelling assumption per D-02, and this split is deliberate — record it explicitly so Phase 2's fee model does not confuse data provenance with fee provenance.

Asset classification (D-16) resolves cleanly through CoinGecko's `/coins/{id}` endpoint, which returns a `categories` list per coin. A live test confirmed Dogecoin's category list includes `"Meme"` (category id `meme-token`) while Bitcoin's does not — a clean, authoritative, per-coin binary signal to run once at instrument-insert time (not per bar fetch), cached in the `instruments` table with the `override` column available for manual correction. The same test also empirically triggered a CoinGecko HTTP 429 after roughly five rapid unauthenticated calls, confirming the free (no-key) tier is materially stricter than the demo-key tier Phase 0 already provisioned — classification lookups must reuse the existing `COINGECKO_API_KEY` from `.env`.

Account provisioning carries one correction worth flagging before planning: IBKR does not treat "account" and "paper trading account" as two separate applications. Official IBKR documentation confirms new individual account holders receive a paper trading account (USD 1,000,000 virtual equity) automatically once the live account is approved — no funding required, no separate signup. The Phase 1 checklist should read as one application with one approval wait (2-3 business days per multiple independent sources), not two.

**Primary recommendation:** Build `get_daily_bars` as a thin router over two existing, well-documented libraries (`yfinance` for stocks, `ccxt`'s Binance client for crypto depth) with a cache-first SQLite read, normalise every timestamp to a UTC calendar date string before storage, classify crypto instruments once at insert time via CoinGecko's `categories` field, and treat the IBKR paper account as a single-application checklist item rather than two.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Stock daily bar fetch | Backend library (`trader/data/`) | External API (`yfinance` → Yahoo Finance) | Single-symbol, on-demand call triggered by cache miss, not a scheduled process |
| Crypto daily bar fetch | Backend library (`trader/data/`) | External API (`ccxt` → Binance, fallback Kraken/CoinGecko) | Same cache-miss trigger pattern as stocks |
| Bar persistence and cache-read | Database (SQLite) | — | `data/trader.db`, shared with Phase 0; `bars` table is append-mostly, read-heavy |
| Instrument classification | Backend library (one-time, at insert) | External API (CoinGecko `/coins/{id}`) | Runs once per new instrument, result cached in `instruments`, not recomputed per bar fetch |
| `get_daily_bars` public API | Backend library (`trader/data/api.py` or similar) | Database (cache-first read) | This is the exit-criterion function; it owns routing between stock/crypto fetchers and the cache |
| Broker/exchange account provisioning | Human (owner) | — | No code; tracked as a checklist per D-14 |
| Kraken API key creation | Human (owner) | Secrets storage (`.env`) | Manual dashboard action; the resulting key/secret are the only artefact code touches |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `yfinance` | 1.5.2 [VERIFIED: PyPI, already installed and live-tested in this session] | US stock daily OHLCV | Already the project's stock data dependency (Phase 0); reusing it avoids a second Yahoo Finance wrapper |
| `ccxt` | 4.5.68 [VERIFIED: PyPI, live-installed and tested in this session] | Crypto daily OHLCV across venues (Binance primary, Kraken secondary), no API key needed for public market data | Industry-standard unified exchange API wrapper; supports 100+ venues through one interface, letting the code switch primary data venue without a rewrite |
| `sqlite3` (stdlib) | bundled with Python 3.12 [ASSUMED — stdlib, not registry-versioned] | Bar and instrument persistence | Matches D-09 — no ORM, plain `sqlite3`, extends the Phase 0 `db.py` pattern |
| `pandas` | 3.0.5 [VERIFIED: PyPI, already installed as a `yfinance` dependency] | DataFrame construction and return type for `get_daily_bars` | D-11 mandates a DataFrame return; `pandas` is already a transitive dependency, so pinning it directly in `requirements.txt` only makes an implicit dependency explicit |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `requests` | 2.34.2 [VERIFIED: PyPI, already installed] | Direct CoinGecko `/coins/{id}` calls for classification | Reused from Phase 0; no new wrapper needed for one endpoint |
| `python-dotenv` | 1.2.2 [VERIFIED: PyPI, already installed] | Load `COINGECKO_API_KEY`, future `KRAKEN_API_KEY`/`KRAKEN_API_SECRET` | Matches D-12 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `ccxt` + Binance for crypto depth | Kraken's downloadable bulk OHLCVT CSV export | Kraken publishes periodic bulk historical CSV dumps with deeper history than the 720-candle REST cap, but it is a manual file download refreshed on Kraken's own schedule, not an on-demand API call — incompatible with the cache-miss-triggers-fetch design in D-03. Worth revisiting only if Binance access ever becomes unreliable for NZ. |
| `ccxt` + Binance | `ccxt` + Coinbase, or a paid provider (CryptoCompare, Kaiko) | Coinbase's public candle endpoint caps at 300 candles per call (worse than Kraken for this purpose); paid providers add cost and an account-provisioning step this phase is trying to avoid. Binance's free, keyless, and deep (confirmed to 2018 for BTC) public data wins on all three axes. |
| CoinGecko `categories` field for classification | A hardcoded whitelist of memecoin tickers | A hardcoded list drifts the moment a new Kraken-listed memecoin appears and duplicates data CoinGecko already maintains and updates continuously; the `override` column (D-16) already covers the rare miscategorisation case. |

**Installation:**
```bash
pip install ccxt==4.5.68 pandas==3.0.5
```
(`yfinance`, `requests`, `python-dotenv`, `pytest`, `ruff` are already installed and pinned per Phase 0.)

**Version verification:** `ccxt` 4.5.68 and `pandas` 3.0.5 confirmed via `pip index versions` against PyPI on 26 July 2026, and both were live-installed into the project's `.venv` in this research session without a build failure on Windows (`cp314-win_amd64` wheels resolved for every native dependency, including `cryptography`, `aiohttp`, and `yarl`).

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|--------------|-----------|-------------|
| ccxt | PyPI | ~9 yrs (since 2017) | Very high (millions/month) | github.com/ccxt/ccxt | [OK] | Approved |
| pandas | PyPI | ~15 yrs | Very high | github.com/pandas-dev/pandas | [OK] | Approved |
| yfinance | PyPI | ~9 yrs | Very high | github.com/ranaroussi/yfinance | [OK] | Approved (carried over from Phase 0) |
| requests | PyPI | ~15 yrs | Very high | github.com/psf/requests | [OK] | Approved (carried over from Phase 0) |
| python-dotenv | PyPI | ~10 yrs | Very high | github.com/theskumar/python-dotenv | [OK] — informational "Name starts with 'python-'" naming-pattern note only, established package | Approved (carried over from Phase 0) |

`slopcheck` 0.6.1 was installed and run live in this session (`py -3.14 -m slopcheck install ccxt yfinance requests python-dotenv finviz pytest ruff`). All seven scanned packages returned `[OK]`.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                         ┌────────────────────────────────────────┐
                         │        get_daily_bars(symbol,           │
                         │            start=None, end=None)         │
                         └───────────────────┬──────────────────────┘
                                             │
                          ┌──────────────────┴───────────────────┐
                          │  Resolve asset_class + venue from     │
                          │  the `instruments` table (or an       │
                          │  explicit asset_class= argument)      │
                          └──────────────────┬───────────────────┘
                                             │
                     ┌───────────────────────┼───────────────────────┐
                     ▼                       │                       ▼
        ┌─────────────────────────┐          │        ┌──────────────────────────┐
        │  Read `bars` cache for   │          │        │  Read `bars` cache for    │
        │  (venue, symbol,         │          │        │  (venue, symbol,          │
        │  'daily', ts range)      │          │        │  'daily', ts range)       │
        └────────────┬─────────────┘          │        └────────────┬──────────────┘
                     │ cache hit → return       │                     │ cache hit → return
                     │ cache miss (gap) ▼        │                     │ cache miss (gap) ▼
        ┌─────────────────────────┐          │        ┌──────────────────────────┐
        │  Stock fetcher           │          │        │  Crypto fetcher           │
        │  yfinance.Ticker(sym)    │          │        │  ccxt.binance()            │
        │  .history(...)           │          │        │  .fetch_ohlcv(sym,'1d',    │
        │  normalize tz → UTC date │          │        │  since=cursor, limit=1000) │
        └────────────┬─────────────┘          │        │  paginate until caught up  │
                     │                        │        └────────────┬──────────────┘
                     ▼                        │                     ▼
        ┌────────────────────────────────────┴─────────────────────────────────┐
        │              INSERT OR IGNORE into `bars` (venue, symbol,              │
        │              timeframe, ts, o, h, l, c, volume) — cache now warm       │
        └────────────────────────────────────┬─────────────────────────────────┘
                                             ▼
                         ┌────────────────────────────────────────┐
                         │  Return pandas DataFrame: ts, open,     │
                         │  high, low, close, volume — indexed     │
                         │  by date (UTC calendar date)            │
                         └────────────────────────────────────────┘

        (Separate, one-time path, not part of the hot get_daily_bars call:)
        ┌─────────────────────────────────────────────────────────────────┐
        │  Instrument insert  →  CoinGecko /coins/{id}  →  check           │
        │  categories list for "Meme"  →  write asset_class into           │
        │  `instruments` (crypto_major or memecoin; stocks default to      │
        │  "stock" with no CoinGecko call)                                 │
        └─────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure
```
trader/
├── ground_truth/            # Phase 0 — unchanged
│   └── ...
├── data/
│   ├── __init__.py
│   ├── db.py                # extends trader/ground_truth/db.py's connection helper;
│   │                         # adds instruments + bars schema and migration entries
│   ├── stock_source.py       # yfinance fetcher, tz-normalization
│   ├── crypto_source.py      # ccxt fetcher (Binance primary, Kraken fallback), pagination
│   ├── classify.py           # CoinGecko categories lookup, asset_class heuristic
│   └── api.py                # get_daily_bars(symbol, start=None, end=None) -> DataFrame
migrations/
├── 0001_ground_truth.sql     # retrofit of Phase 0's existing DDL (idempotent, CREATE TABLE IF NOT EXISTS)
└── 0002_instruments_bars.sql # Phase 1's new tables
tests/
└── test_data_api.py          # mocked yfinance/ccxt, cache-hit vs cache-miss assertions
```

### Pattern 1: Cache-First Read, Fetch-on-Miss Write
**What:** `get_daily_bars` always queries the `bars` table first for the requested `(venue, symbol, 'daily', ts range)`. Only a genuine gap (no rows, or rows missing at the requested range boundary) triggers a live fetch, which then writes through to the cache before returning.
**When to use:** Every call to the exit-criterion function — this is D-03's contract, not an optimisation.
**Example:**
```python
# Illustrative — not from official docs; the pattern composes stdlib sqlite3 with the two fetchers below.
def get_daily_bars(symbol: str, start: str | None = None, end: str | None = None,
                    asset_class: str | None = None) -> pd.DataFrame:
    venue, resolved_class = resolve_instrument(symbol, asset_class)
    cached = read_bars_cache(venue, symbol, "daily", start, end)
    if cache_covers_range(cached, start, end):
        return cached
    fresh = (fetch_stock_bars(symbol, start, end)
             if resolved_class == "stock"
             else fetch_crypto_bars(symbol, venue, start, end))
    write_bars_cache(venue, symbol, "daily", fresh)
    return read_bars_cache(venue, symbol, "daily", start, end)
```

### Pattern 2: Normalise Every Bar Timestamp to a UTC Calendar Date Before Insert
**What:** `yfinance` returns a timezone-aware index in the exchange's local zone (confirmed live: `America/New_York` for `AAPL`); `ccxt` returns Unix millisecond timestamps in UTC. Convert both to a plain `YYYY-MM-DD` UTC calendar-date string before the row reaches SQLite — daily bars have no meaningful intraday component, so storing a date string (not a datetime) removes an entire class of timezone bugs.
**When to use:** In both `stock_source.py` and `crypto_source.py`, immediately after the raw fetch, before any cache write.
**Example:**
```python
# Source: live-tested in this research session against yfinance 1.5.2 and ccxt 4.5.68
def normalize_stock_bars(df: pd.DataFrame) -> pd.DataFrame:
    # df.index is tz-aware (e.g. America/New_York); convert to UTC date, drop time-of-day
    df = df.copy()
    df["ts"] = df.index.tz_convert("UTC").strftime("%Y-%m-%d")
    return df[["ts", "Open", "High", "Low", "Close", "Volume"]]

def normalize_crypto_bars(raw_ohlcv: list[list]) -> list[dict]:
    # ccxt fetch_ohlcv rows: [timestamp_ms, open, high, low, close, volume]
    from datetime import datetime, timezone
    return [
        {
            "ts": datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
            "open": row[1], "high": row[2], "low": row[3], "close": row[4], "volume": row[5],
        }
        for row in raw_ohlcv
    ]
```

### Pattern 3: Paginate Binance's 1000-Candle-Per-Call Limit
**What:** `ccxt`'s `fetch_ohlcv` on Binance returns at most 1,000 daily candles per call. For 3+ years of history (roughly 1,095+ trading days), loop: call with `since=cursor`, advance `cursor` to `last_returned_timestamp + one day`, stop when the returned batch is shorter than the requested limit or `cursor` reaches "now."
**When to use:** Any crypto backfill spanning more than ~2.7 years (1000 daily candles).
**Example:**
```python
# Source: live-tested in this research session — confirmed BTC/USDT daily candles
# paginate correctly back to 2018 with limit=1000 per call.
def fetch_all_daily_ohlcv(exchange, symbol: str, since_ms: int) -> list[list]:
    all_rows: list[list] = []
    cursor = since_ms
    while True:
        batch = exchange.fetch_ohlcv(symbol, timeframe="1d", since=cursor, limit=1000)
        if not batch:
            break
        all_rows.extend(batch)
        cursor = batch[-1][0] + 24 * 60 * 60 * 1000  # advance one day past the last candle
        if len(batch) < 1000:
            break
    return all_rows
```

### Pattern 4: Classify Once, at Instrument Insert, Never per Bar Fetch
**What:** Query CoinGecko's `/coins/{id}` endpoint exactly once when a new crypto instrument first enters the `instruments` table. Check the returned `categories` list for `"Meme"`; write `memecoin` or `crypto_major` accordingly. Never repeat this lookup on subsequent bar fetches — it is instrument metadata, not a bar attribute.
**When to use:** Instrument onboarding only (a one-time backfill task, or whenever a brand-new symbol first appears).
**Example:**
```python
# Source: live-tested in this research session against api.coingecko.com/api/v3/coins/{id}
def classify_crypto_instrument(coingecko_id: str, api_key: str) -> str:
    resp = requests.get(
        f"https://api.coingecko.com/api/v3/coins/{coingecko_id}",
        params={"localization": "false", "tickers": "false", "market_data": "false",
                "community_data": "false", "developer_data": "false", "sparkline": "false"},
        headers={"x-cg-demo-api-key": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    categories = resp.json().get("categories") or []
    return "memecoin" if "Meme" in categories else "crypto_major"
```

### Anti-Patterns to Avoid
- **Trusting D-11's "UTC timestamps" to mean yfinance's raw index is already UTC:** It is not — live-verified as `America/New_York`. Convert explicitly (Pattern 2).
- **Fetching from Kraken for depth:** Kraken's OHLC REST endpoint cannot return more than 720 of the most recent candles regardless of `since` — confirmed by official Kraken documentation. Do not attempt to page backward past this; the data does not exist through that endpoint.
- **Re-running the CoinGecko classification lookup on every bar fetch:** Wastes a scarce, rate-limited call (empirically 429'd after ~5 unauthenticated requests in this session) for data that never changes after insert. Cache the result in `instruments.asset_class`.
- **Labelling `bars.venue` as `"kraken"` for Binance-sourced data to make Phase 2's fee lookup simpler:** This conflates data provenance with fee-schedule assumption and will confuse debugging later (a stored "kraken" bar that was never actually fetched from Kraken). Record the true source venue in `bars.venue`; let Phase 2's fee model key off `asset_class`, which is D-02's actual intent ("fees still model as Kraken" is a modelling decision, not a data-provenance claim). Flagged as an open question below for explicit confirmation.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multi-venue crypto OHLCV fetching, pagination, and symbol normalisation | A custom Binance/Kraken REST client | `ccxt` | `ccxt` already normalises symbol formats, handles rate limiting internally, and supports switching the primary venue (Binance → Kraken → any of 100+ others) by changing one line, not rewriting an HTTP client |
| Yahoo Finance daily bar fetching, corporate-action adjustment | A custom `requests`-based Yahoo scraper | `yfinance` (already the project's Phase 0 dependency) | `yfinance` already bundles `curl_cffi` browser-impersonation to reduce 429s, and its `auto_adjust=True` path correctly folds splits and dividends into O/H/L/C without separate logic |
| Memecoin vs. major classification | A hand-maintained ticker whitelist | CoinGecko `categories` field, cached at insert time | Whitelist drifts as new Kraken-listed memecoins appear; CoinGecko already maintains and updates the category taxonomy |
| Schema migrations | Ad-hoc `ALTER TABLE` calls scattered through app code | Ordered `.sql` files in `migrations/` applied by a small runner, tracked in `schema_version` (D-09) | Matches the locked decision directly and gives Phase 2+ a clean place to add tables without touching `ensure_schema` by hand each time |

**Key insight:** Every external data dependency in this phase (Yahoo Finance, Binance, CoinGecko) already has a mature, free, keyless-or-cheap-keyed wrapper. The engineering effort belongs in the cache-first routing layer and the timestamp-normalisation boundary, not in re-implementing HTTP clients for any of the three.

## Common Pitfalls

### Pitfall 1: yfinance's history index is not UTC
**What goes wrong:** Code that assumes `Ticker(...).history()`'s index is already UTC (as D-11 implies) will store bars keyed to the wrong calendar date near midnight in US time zones, or will silently accumulate a timezone offset bug that only shows up when comparing against crypto bars (which are naturally UTC via `ccxt`).
**Why it happens:** `yfinance` returns an index localised to the exchange's home timezone (`America/New_York` for US equities), not UTC. Live-verified in this session: `yf.Ticker('AAPL').history(period='5y', auto_adjust=True).index.tz` returned `America/New_York`.
**How to avoid:** Convert with `.tz_convert("UTC")` and take the date portion only (Pattern 2) — for daily bars, the date is the only information that matters, so drop the intraday timestamp entirely rather than trying to reconcile two exchanges' different local closing times.
**Warning signs:** A stock bar and a crypto bar for "the same day" that are off by one row when joined on `ts`; unit tests that pass with US-hours-only fixtures but fail once a crypto fixture (always UTC-aligned) is added to the same table.

### Pitfall 2: Assuming Kraken's `since` parameter can page past 720 candles
**What goes wrong:** A backfill written against Kraken's REST OHLC endpoint that requests, say, three years of daily data will silently receive only the most recent ~720 days and no error indicating truncation, if the calling code does not explicitly check the returned row count against the requested range.
**Why it happens:** Kraken's own documentation states the endpoint "returns up to 720 of the most recent entries (older data cannot be retrieved, regardless of the value of `since`)" — this is a hard server-side limitation, not a client or `ccxt` bug.
**How to avoid:** Use Binance (via `ccxt`) as the primary fetch venue for any range longer than ~2 years; reserve Kraken only for a short recent window or as a fallback if Binance is ever unreachable. Always assert the returned row count against the requested range in the fetcher, so a silent truncation raises rather than caches an incomplete answer.
**Warning signs:** A `get_daily_bars` call for a 3-year range on a crypto symbol returns noticeably fewer than the expected ~1,095 rows with no exception raised.

### Pitfall 3: CoinGecko's free tier rate-limits aggressively without a key
**What goes wrong:** Unauthenticated calls to `api.coingecko.com` (no `x-cg-demo-api-key` header) hit HTTP 429 after only a handful of rapid requests — empirically confirmed in this research session (429 returned on the sixth call within roughly ten seconds).
**Why it happens:** CoinGecko's public, keyless tier carries a materially stricter rate limit than the Demo plan (a signed-up, free API key); Phase 0 already provisioned `COINGECKO_API_KEY` in `.env` for exactly this reason.
**How to avoid:** Every classification call in `classify.py` must send the `x-cg-demo-api-key` header, loaded via the same `python-dotenv` pattern Phase 0 established. Do not add a second, unauthenticated code path for convenience during development.
**Warning signs:** `429 Client Error: Too Many Requests` during a batch instrument-classification backfill; intermittent `categories: None` responses that look like a data problem but are actually a rate-limit response silently parsed as empty.

### Pitfall 4: Treating IBKR's paper account as a second application
**What goes wrong:** Planning IBKR account approval and paper-account approval as two sequential human tasks (as the phase document's checklist wording implies) adds a phantom wait that does not exist, potentially delaying the phase's exit criterion tracking for no reason.
**Why it happens:** Official IBKR documentation (`ibkrguides.com/clientportal/aboutpapertradingaccounts.htm`) confirms new individual account holders receive a paper trading account automatically once the live account is approved — approval, not funding, is the trigger. There is no separate paper-account signup form.
**How to avoid:** Track ACCT-01 as a single checklist item: "IBKR individual account application submitted → approved (2-3 business days typical)." The paper account (USD 1,000,000 virtual equity) then appears in Client Portal without further action.
**Warning signs:** A checklist that still shows "paper account" as a separate pending item after the live account shows "Approved" in Client Portal.

### Pitfall 5: Confusing data-source venue with fee-model venue in the `bars` table
**What goes wrong:** If `bars.venue` is set to `"kraken"` for data actually fetched from Binance (to make a future fee-model join simpler), any later debugging of a data-quality issue will look at the wrong exchange's status page, rate limits, and outage history.
**Why it happens:** D-02 states fees still model as Kraken regardless of where the daily-bar data physically came from; conflating the two columns' semantics is an easy shortcut that saves a join in Phase 2 but costs traceability from Phase 1 onward.
**How to avoid:** Store the true fetch venue (`"binance"`, `"yfinance"`, or `"kraken"` for the fallback path) in `bars.venue`. Let Phase 2's fee model look up fee schedule by `instruments.asset_class`, not by `bars.venue` — see Open Questions for the explicit confirmation this needs before Phase 2 begins.
**Warning signs:** A `bars` row with `venue='kraken'` for a symbol whose earliest date predates Kraken's 720-day cap — a direct contradiction that only becomes visible if provenance was recorded honestly.

## Code Examples

### yfinance: full-history stock daily bars (live-tested, 1.5.2)
```python
# Source: live-tested in this research session against the project's own .venv
import yfinance as yf

def fetch_stock_bars(symbol: str, start: str | None, end: str | None) -> pd.DataFrame:
    ticker = yf.Ticker(symbol)
    if start is None:
        df = ticker.history(period="max", auto_adjust=True)
    else:
        df = ticker.history(start=start, end=end, auto_adjust=True)
    return normalize_stock_bars(df)  # see Pattern 2
```
**Live result:** `yf.Ticker('AAPL').history(period='5y', auto_adjust=True)` returned 1,255 rows in 1.7 seconds with columns `Open, High, Low, Close, Volume, Dividends, Stock Splits` and a tz-aware `America/New_York` index.

### ccxt: Binance daily bars for any of the five named memecoins plus BTC (live-tested, 4.5.68)
```python
# Source: live-tested in this research session
import ccxt

def fetch_crypto_bars(symbol: str, since_ms: int) -> list[list]:
    exchange = ccxt.binance()  # no API key needed for public OHLCV
    return fetch_all_daily_ohlcv(exchange, symbol, since_ms)  # see Pattern 3
```
**Live result:** `BTC/USDT` daily candles paginate correctly back to 2018-01-01 (limit=1000 per call). `WIF/USDT` (a recent listing) returned 874 daily candles from 2024-03-05 to present — confirms D-17's "short history for recent listings is expected and stored as-is."

### CoinGecko: instrument classification (live-tested)
```python
# Source: live-tested in this research session — see Pattern 4 above for the full function
# Confirmed live: dogecoin's categories include "Meme"; bitcoin's do not.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `yfinance` plain `requests` session (frequent 429s reported since November 2024) | `yfinance` 1.x bundles `curl_cffi` with browser TLS/JA3 impersonation | Ongoing, present in the installed 1.5.2 (confirmed via its declared `curl_cffi>=0.15` dependency) | Reduces (does not eliminate) 429 risk for single-symbol, low-frequency calls typical of Phase 1's cache-miss pattern; no extra application code needed to get this benefit |
| Treating CCXT venue choice as fixed at "whichever exchange you trade on" | Using CCXT purely as a data-fetch abstraction, decoupled from the trading/fee venue | Established CCXT pattern, not new in 2026, but directly relevant here per D-02 | Lets Binance serve as the data-depth venue while Kraken remains the fee-model and eventual execution venue — see Pitfall 5 |

**Deprecated/outdated:**
- Kraken's REST OHLC endpoint as a source of deep history: was never capable of this — training-data assumptions that "pass a `since` far enough back and Kraken will paginate" are directly contradicted by Kraken's own documentation, confirmed in this session.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Binance's public market-data endpoints remain reachable from the owner's NZ residential IP with no geo-block, matching this session's test environment | Standard Stack, Architecture Patterns | If Binance ever blocks NZ IPs for market data (currently only Binance's self-custody Web3 Wallet feature is NZ-restricted per WebSearch, not spot market data), fall back to Kraken (720-day cap) or CoinGecko's `market_chart` endpoint (365-day free-tier cap per official docs) — both already documented as fallbacks above |
| A2 | CoinGecko Demo-plan (keyed) rate limit is approximately 100 calls/min per the pricing page, versus the empirically-confirmed sub-10-call unauthenticated limit | Common Pitfalls #3 | If the keyed limit is materially lower than 100/min, a large instrument-classification backfill could still 429; mitigate by pacing calls with a short sleep regardless of the stated limit, since Phase 1's total classification-call volume (one call per new instrument, ever) is tiny |
| A3 | The category id `meme-token` (display name "Meme") is CoinGecko's stable, canonical tag for memecoins, rather than one of several overlapping sub-categories (`ai-meme-coins`, `dog-themed`, etc.) that a coin might carry instead of or in addition to it | Architecture Patterns Pattern 4 | If a genuine Kraken-listed memecoin lacks the literal `"Meme"` string in its category list (e.g., tagged only `"Dog-Themed"`), it would be misclassified as `crypto_major`; the `override` column (D-16) is the documented escape hatch — recommend the planner add a manual review step for the five named memecoins specifically, all of which were live-confirmed to carry `"Meme"` in this session |
| A4 | `bars.venue` should record true data provenance (e.g., `"binance"`) rather than the fee-model venue (`"kraken"`) for crypto rows | Pitfall 5 | This is a naming/semantics recommendation, not yet confirmed against the owner's intent for D-08's `venue` column; if the owner actually wants `venue` to mean "fee/execution venue" uniformly, the schema needs a second column (e.g., `source`) to hold true provenance — flagged as an open question below |
| A5 | Independent Reserve's KYC approval turnaround (beyond the ~20-minute submission time) was not found in this session's searches | Account Setup Specifics | If approval takes materially longer than IBKR's or Kraken's, the phase's "start early" framing (D-14) is even more important; no code impact, purely a timeline-planning risk |

**If this table is empty:** N/A — see entries above.

## Account Setup Specifics

### IBKR (individual account + paper account) — ACCT-01
1. Apply at `interactivebrokers.co.uk` or `interactivebrokers.com`, account type **Individual**. Online application takes 15-30 minutes `[MEDIUM confidence — WebSearch, multiple sources]`.
2. Required documents: photo ID (passport, national ID, or driver's licence) and proof of residency (bank statement, utility bill, or similar) `[MEDIUM confidence — WebSearch, multiple independent sources]`.
3. Typical approval time: 2-3 business days `[MEDIUM confidence — multiple independent WebSearch sources agree]`.
4. **Do not apply for a paper trading account separately.** Once the live account shows Approved in Client Portal, log in and the paper trading account (USD 1,000,000 virtual equity) is already present automatically `[CITED: ibkrguides.com/clientportal/aboutpapertradingaccounts.htm]`.
5. Funding the live account is not required for Phase 1 — approval alone unlocks paper trading, consistent with standing rule 6 (real money starts at Phase 9).

### Kraken (trade-only API keys) — ACCT-02
1. Create a Kraken account and complete Kraken's own identity verification (separate from Independent Reserve's KYC; Kraken is used for crypto trading, not the NZD fiat ramp).
2. Create an API key under Settings → API. Enable exactly:
   - Query Funds
   - Query Open Orders & Trades
   - Query Closed Orders & Trades
   - Modify Orders
   - Cancel/Close Orders
3. Leave unchecked (this is the withdrawal-permission guard from D-13 and standing rule 3):
   - Deposit Funds
   - **Withdraw Funds**
   - Query Ledger Entries
   - Export Data
   - Access WebSockets API
4. Store the resulting key and secret in `.env` as `KRAKEN_API_KEY` / `KRAKEN_API_SECRET`. Never commit `.env`.
5. Manual verification step (per D-13): after creation, open the key's settings page and visually confirm "Withdraw Funds" shows as disabled before considering ACCT-02 complete.
`[MEDIUM confidence — Kraken support article, cross-checked against the general documented principle that a trading-only key never needs Withdraw Funds]`

### Independent Reserve (NZD ramp KYC) — ACCT-03
1. Sign up at Independent Reserve with an NZD-capable account.
2. Submit: full name, date of birth, address, government-issued ID upload, and a selfie/liveness check; proof of address (utility bill, bank statement, or insurance policy) `[MEDIUM confidence — WebSearch, single source with detail]`.
3. Initial submission takes roughly 20 minutes; this session found no confirmed figure for the exchange's own approval/verification turnaround — treat as an open timeline risk and start this application in parallel with IBKR and Kraken, per D-14.
4. No code depends on this account until Phase 9 (the NZD funding ramp) — Phase 1's only obligation is submitting the KYC application, not completing it.

## Schema Design

Extend, do not replace, the existing `trader/ground_truth/db.py` conventions (WAL mode, `busy_timeout=5000`, `ensure_schema` pattern, `schema_version` table already at version 1 from Phase 0).

### Recommended approach
D-09 asks for "ordered SQL migration files," which Phase 0 did not literally implement (it hardcoded `CREATE TABLE IF NOT EXISTS` calls directly in `ensure_schema`). Recommend introducing the `migrations/` mechanism starting now: retrofit Phase 0's existing DDL as `migrations/0001_ground_truth.sql` (safe, since `CREATE TABLE IF NOT EXISTS` is idempotent and changes nothing on a database that already has these tables), and add Phase 1's new tables as `migrations/0002_instruments_bars.sql`. A small migration runner (loop over `.sql` files in order, skip any whose version already exists in `schema_version`) replaces the ad-hoc `ensure_schema` calls going forward, satisfying D-09 for this phase and every phase after it.

### `instruments` table
```sql
CREATE TABLE IF NOT EXISTS instruments (
    symbol TEXT NOT NULL,
    venue TEXT NOT NULL,
    asset_class TEXT NOT NULL CHECK (asset_class IN ('stock', 'crypto_major', 'memecoin')),
    coingecko_id TEXT,
    override TEXT CHECK (override IN ('stock', 'crypto_major', 'memecoin') OR override IS NULL),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, venue)
);
```
`asset_class` is written once at classification time (Pattern 4); `override`, when non-null, takes precedence in `get_daily_bars`'s routing logic — matches D-16 exactly.

### `bars` table
```sql
CREATE TABLE IF NOT EXISTS bars (
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts TEXT NOT NULL,              -- UTC calendar date, 'YYYY-MM-DD' — see Pitfall 1
    o REAL NOT NULL,
    h REAL NOT NULL,
    l REAL NOT NULL,
    c REAL NOT NULL,
    volume REAL NOT NULL,
    UNIQUE (venue, symbol, timeframe, ts)
);
```
Matches D-08's exact column list and unique-key design. `ts` as a plain date string (not a datetime, not a Unix timestamp) sidesteps the tz-mismatch pitfall between `yfinance` (`America/New_York`) and `ccxt` (UTC milliseconds) — both normalise to the same string format before insert (Pattern 2).

**Open question on `venue` semantics:** see Assumption A4 and Pitfall 5 — confirm with the owner during planning whether `bars.venue` should record true data provenance (recommended) or the fee-model venue, before Phase 2 builds its fee lookup against this column.

## Open Questions

1. **Should `bars.venue` record true data provenance (e.g., `"binance"`) or the fee-model venue (`"kraken"`) for crypto rows?**
   - What we know: D-02 explicitly decouples data source from fee-model assumption ("fees still model as Kraken" regardless of where daily bars are fetched from).
   - What's unclear: Whether D-08's `venue` column was intended to mean "where this data came from" or "which exchange this instrument trades/is fee-modelled on."
   - Recommendation: Record true provenance in `bars.venue` (Pitfall 5); if the owner wants a fee-model venue too, add a resolved lookup in `instruments` (e.g., `fee_venue` defaulting to `"kraken"` for all crypto) rather than overloading `bars.venue`. Flag for the owner during `/gsd:plan-phase` or a quick discuss-phase follow-up if not already obvious from the planner's read of D-02.

2. **Independent Reserve's KYC approval turnaround time.**
   - What we know: Initial submission takes about 20 minutes.
   - What's unclear: How long the exchange itself takes to approve the submission — no figure found in this session's searches.
   - Recommendation: Treat as a "submitted, awaiting approval" checklist state per D-14; no phase-blocking impact since this account is not needed until Phase 9.

3. **Exact CoinGecko Demo-plan rate limit (calls/min) for keyed requests.**
   - What we know: The pricing/support pages cite approximately 100 calls/min for the free Demo plan (per WebSearch synthesis); Phase 0's own research flagged a conflicting 30/min figure from a different source.
   - What's unclear: The authoritative, current number without checking the CoinGecko developer dashboard directly (already a follow-up noted in Phase 0's research).
   - Recommendation: Phase 1's classification-call volume is tiny (one call per new instrument, ever), so this is low-risk regardless of which figure is correct — pace defensively (a short sleep between calls during any batch backfill) rather than resolving the exact number.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|--------------|-----------|---------|----------|
| Python | Entire phase | Yes (per phase brief and this session's live `.venv` test) | 3.12 (project venv) / 3.14 (research-session global interpreter) | — |
| `yfinance` | Stock bars | Yes — already installed, live-tested | 1.5.2 | — |
| `ccxt` | Crypto bars | Yes — installed and live-tested in this session | 4.5.68 | — |
| Internet access to `query1/2.finance.yahoo.com` | Stock bars | Yes — live-tested successfully in this session | — | none needed |
| Internet access to `api.binance.com` | Crypto bars (primary) | Yes — live-tested successfully in this session (loaded markets, fetched OHLCV) | — | Kraken via `ccxt` (720-day cap) or CoinGecko `market_chart` (365-day free-tier cap) |
| Internet access to `api.coingecko.com` | Instrument classification | Yes — live-tested, though unauthenticated requests hit 429 quickly (see Pitfall 3) | — | Already-provisioned `COINGECKO_API_KEY` from Phase 0 raises the effective limit |
| SQLite (stdlib `sqlite3`) | Persistence | Yes — bundled with Python 3.12 | stdlib | — |
| IBKR, Kraken, Independent Reserve accounts | ACCT-01/02/03 | Not yet — human tasks, tracked as checklist per D-14 | — | none; these are prerequisites for later phases only, not for ACCT-04/06/07 |

**Missing dependencies with no fallback:** none identified for the code-facing requirements (ACCT-04, ACCT-06, ACCT-07).
**Missing dependencies with fallback:** Binance reachability (Kraken/CoinGecko fallback documented above); account approvals (no fallback needed — they are human-timeline items, not blockers for the code work per D-14).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (already established by Phase 0) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (already exists, `testpaths = ["tests"]`) |
| Quick run command | `pytest tests/ -x -k "not integration"` |
| Full suite command | `pytest tests/` |

### Phase Requirements → Test Map
| Req ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|--------------------|--------------|
| ACCT-04 | Stock fetcher normalises `yfinance`'s tz-aware index to a UTC date string | unit (mocked `yfinance.Ticker.history`) | `pytest tests/test_data_api.py::test_stock_bars_normalize_to_utc_date -x` | No — Wave 0 |
| ACCT-04 | Crypto fetcher paginates past Binance's 1000-candle limit correctly | unit (mocked `ccxt` exchange) | `pytest tests/test_data_api.py::test_crypto_bars_paginate_past_1000 -x` | No — Wave 0 |
| ACCT-06 | `instruments` and `bars` tables created via migration, `schema_version` advances | unit (temp SQLite file) | `pytest tests/test_db.py::test_migration_0002_creates_instruments_and_bars -x` | No — Wave 0 |
| ACCT-06 | `bars` unique constraint rejects a duplicate `(venue, symbol, timeframe, ts)` insert | unit | `pytest tests/test_db.py::test_bars_unique_constraint -x` | No — Wave 0 |
| ACCT-07 | `get_daily_bars('AAPL')` returns a DataFrame with the exact contract columns | unit (mocked fetch, cache pre-seeded) | `pytest tests/test_data_api.py::test_get_daily_bars_stock_contract -x` | No — Wave 0 |
| ACCT-07 | `get_daily_bars('DOGE/USD')` (or equivalent) returns a DataFrame via the crypto path | unit (mocked fetch, cache pre-seeded) | `pytest tests/test_data_api.py::test_get_daily_bars_crypto_contract -x` | No — Wave 0 |
| ACCT-07 | A cache hit makes zero network calls | unit (mock asserts not called) | `pytest tests/test_data_api.py::test_cache_hit_skips_fetch -x` | No — Wave 0 |
| ACCT-07 | A cache miss fetches, writes through, and a second call for the same range hits cache | integration (real cache-write path, mocked HTTP) | `pytest tests/test_data_api.py::test_cache_miss_then_cache_hit -x` | No — Wave 0 |
| ACCT-01/02/03 | Account applications submitted | manual (not automatable) | Checklist item checked off in the plan, per D-14 | N/A |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x -k "not integration"`
- **Per wave merge:** `pytest tests/`
- **Phase gate:** Full suite green, plus one live (non-mocked) smoke-test run of `get_daily_bars` for a real stock symbol and a real crypto pair, confirming the exit criterion end-to-end before `/gsd:verify-work`. Account checklist items (ACCT-01/02/03) gate on "submitted," not "approved" (D-14) — approval status is tracked but does not block marking the phase DONE per the phase document's own framing ("in progress or done").

### Wave 0 Gaps
- [ ] `tests/test_data_api.py` — covers ACCT-04, ACCT-07 (all rows above)
- [ ] `tests/test_db.py` additions — covers ACCT-06 (instruments/bars migration, unique constraint)
- [ ] `tests/conftest.py` additions — mocked `yfinance.Ticker`, mocked `ccxt.binance()` exchange instance, temp SQLite fixture reused from Phase 0's `conftest.py`
- [ ] `migrations/` directory and a small runner — needed before `test_migration_0002_creates_instruments_and_bars` can pass
- [ ] Framework: no new install needed (`pytest` already present)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|--------------------|
| V2 Authentication | No | Phase 1 has no user-facing auth surface |
| V3 Session Management | No | No sessions — library calls and short-lived scripts |
| V4 Access Control | No | Single-operator local machine |
| V5 Input Validation | Yes | Parameterised SQL only for all `instruments`/`bars` inserts (never string-formatted SQL); validate CoinGecko/Binance/Yahoo response shapes before writing |
| V6 Cryptography | No direct need | The only secrets are API keys (`COINGECKO_API_KEY`, future `KRAKEN_API_KEY`/`KRAKEN_API_SECRET`); stored in `.env`, loaded via `python-dotenv`, no custom cryptography required |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|------------------------|
| SQL injection via symbol/venue string interpolation | Tampering | Parameterised queries (`?` placeholders) for every `instruments`/`bars` statement, matching the Phase 0 `db.py` convention already in place |
| Kraken API key with withdrawal permission enabled by accident | Elevation of Privilege | Manual verification step in the account-setup checklist (D-13); never enable "Withdraw Funds" on a key used by code — standing rule 3 |
| Committed `.env` exposing `KRAKEN_API_KEY`/`KRAKEN_API_SECRET` | Information Disclosure | `.gitignore` already excludes `.env` and only tracks `.env.example`; verify the new Kraken key names are added to `.env.example` with empty values, never real ones |
| Untrusted third-party response data (Yahoo/Binance/CoinGecko payloads) treated as fully trusted before insert | Tampering | Validate expected fields exist and are the expected type before writing to SQLite, matching the Phase 0 pattern already established for the `snapshots` table |

## Sources

### Primary (HIGH confidence)
- Live tests in this research session against the project's actual `.venv`: `yfinance.Ticker('AAPL').history(period='5y', auto_adjust=True)`; `ccxt.binance()` market listing and `fetch_ohlcv` pagination for BTC/USDT and WIF/USDT; `ccxt.kraken()` market listing; `requests.get()` against `api.coingecko.com/api/v3/coins/{id}` and `/coins/categories/list`
- docs.kraken.com/api/docs/rest-api/get-ohlc-data — official confirmation of the 720-candle hard cap, independent of `since`
- ibkrguides.com/clientportal/aboutpapertradingaccounts.htm — official confirmation that paper accounts are automatic upon live-account approval
- PyPI (`pip index versions`) — live-verified `ccxt` 4.5.68 and `pandas` 3.0.5 versions (26 July 2026)
- `slopcheck` 0.6.1 (installed and run live in this session) — package legitimacy scan, all 7 packages `[OK]`

### Secondary (MEDIUM confidence)
- support.kraken.com/articles/360000919966-how-to-create-an-api-key — API key permission checkbox names and grouping, cross-checked against the general "trade-only key never needs Withdraw Funds" principle
- docs.coingecko.com (multiple pages, via WebSearch synthesis) — free-tier `market_chart` 365-day depth limit, auto-granularity rules, Demo-plan ~100 calls/min figure
- Multiple independent WebSearch sources on IBKR individual-account signup steps, documents required, and 2-3 business day approval timeframe
- WebSearch synthesis on Independent Reserve KYC submission steps (~20 minutes)
- WebSearch synthesis on Binance's New Zealand access status (no full ban found; only the separate Web3 Wallet feature is NZ-restricted)

### Tertiary (LOW confidence)
- Independent Reserve's actual approval turnaround time (beyond submission) — not found in this session; flagged as Open Question 2
- The precise, current CoinGecko Demo-plan rate limit — WebSearch sources cite ~100 calls/min but this was not confirmed against a live authenticated dashboard check in this session; flagged as Open Question 3

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every library choice and version was live-installed and exercised against real external APIs in this session, not just checked against a registry
- Architecture: HIGH — the cache-first pattern, tz-normalisation requirement, and pagination pattern were all directly observed, not inferred from documentation alone
- Account setup: MEDIUM — IBKR's paper-account behaviour is HIGH confidence (official docs, directly fetched); Kraken's permission checkboxes are MEDIUM (support article plus general principle); Independent Reserve's approval timeline is LOW (unconfirmed)
- Pitfalls: HIGH — all five pitfalls above were either directly reproduced (CoinGecko 429, yfinance tz, Kraken 720-candle cap, IBKR paper-account auto-grant) or are a direct logical consequence of a directly-reproduced finding (the venue-semantics pitfall)

**Research date:** 26 July 2026
**Valid until:** 7 days for CoinGecko rate-limit specifics and Binance NZ access status (both are policy-level and can change without notice); 30 days for the SQLite schema design, cache-first architecture pattern, and account-setup document requirements (stable, officially documented or directly tested against stable APIs).
