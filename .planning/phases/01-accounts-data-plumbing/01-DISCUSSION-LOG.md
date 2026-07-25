# Phase 1: Accounts & Data Plumbing - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-26
**Phase:** 1-accounts-data-plumbing
**Areas discussed:** Historical data source, Repo structure & tooling, Database layout, Data access API shape, Secrets & account setup, Memecoin handling
**Mode:** Auto-selected recommended defaults (non-interactive session). Every selection below is overridable before planning.

---

## Historical Data Source

| Option | Description | Selected |
|--------|-------------|----------|
| yfinance + CCXT | Free, no keys, deep daily history for stocks; exchange-grade crypto candles | ✓ |
| Alpha Vantage | Free tier heavily rate-limited (25 req/day) | |
| Tiingo | Good free tier but requires a key and has symbol limits | |
| IBKR API for history | Ties data plumbing to broker approval timing | |

**Choice:** yfinance for US stocks, CCXT for crypto, all cached in SQLite.
**Notes:** Researcher must confirm current yfinance reliability and the best free CCXT venue for 3+ years of daily crypto candles (Kraken caps at ~720).

---

## Repo Structure & Tooling

| Option | Description | Selected |
|--------|-------------|----------|
| Single package, venv + pip | Simple, Windows-friendly, one requirements.txt | ✓ |
| uv-managed project | Faster, but adds a tool dependency on this machine | |
| Poetry | Heavier than the project needs | |

**Choice:** Single `trader/` package, src layout, venv + pip, Python 3.12, pytest, ruff, python-dotenv.

---

## Database Layout

| Option | Description | Selected |
|--------|-------------|----------|
| One SQLite file, WAL, plain sqlite3 | `data/trader.db`; shared by Phase 0 logger; migrations as ordered SQL | ✓ |
| SQLAlchemy ORM | Abstraction the project does not need yet | |
| One DB per concern | Splits data that later phases join | |

**Choice:** One database, `instruments` / `bars` / `snapshots` tables, `schema_version` migrations.

---

## Data Access API Shape

| Option | Description | Selected |
|--------|-------------|----------|
| `get_daily_bars(symbol, start, end)` → DataFrame | One unified call, asset-class routing, cache-first | ✓ |
| Separate stock/crypto functions | Fails the "one function call" exit criterion | |

**Choice:** Unified function returning a UTC, date-indexed DataFrame with `ts/open/high/low/close/volume`.

---

## Secrets & Account Setup

| Option | Description | Selected |
|--------|-------------|----------|
| `.env` + committed `.env.example`, human checklist for accounts | Keys gitignored; trade-only Kraken permissions manually verified; code never blocks on KYC | ✓ |
| OS keychain / secrets manager | Overkill for a single-operator local project at this phase | |

**Choice:** `.env` with standardized names; account applications tracked as a checklist and started early because approvals take days.

---

## Memecoin Handling (raised by owner)

| Option | Description | Selected |
|--------|-------------|----------|
| Kraken-listed memecoins via existing CCXT path, tagged in instruments | Same plumbing as majors; asset_class tag drives later slippage/caps/gates | ✓ |
| Include on-chain/DEX tokens | No venue access; risk gate would reject most on volume and listing age | |
| Exclude memecoins from Phase 1 entirely | Would force schema rework in Phase 2–4 when slippage classes and caps need the tag | |

**Choice:** Kraken-listed only; `asset_class` column (`stock` / `crypto_major` / `memecoin`) with manual override; classification heuristic from CoinGecko category, confirmed by researcher; exit criterion still gates on majors.
**Notes:** Owner asked "what about memecoins" after initial auto-pass. DEX venue support noted as a potential future phase, not current scope.

## Claude's Discretion

- Library versions, internal module naming, migration mechanics, DataFrame validation details.

## Deferred Ideas

- Polygon.io intraday data — decide later (owner's note in the phase document)
- Postgres/Timescale — only when SQLite hurts
- Phase 0 logger build — Phase 0 scope
- Telegram alerting — Phase 5 scope
