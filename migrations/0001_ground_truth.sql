-- Retrofit of Phase 0's trader/ground_truth/db.py ensure_schema DDL.
-- Idempotent (CREATE TABLE IF NOT EXISTS) — safe to run against a database
-- that already has these tables. Do not alter Phase 0's existing table shape
-- or column list (see 01-CONTEXT.md D-07/D-08/D-09).

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_ts TEXT NOT NULL,
    source TEXT NOT NULL,
    ticker TEXT NOT NULL,
    coingecko_id TEXT,
    price REAL NOT NULL,
    pct_gain REAL NOT NULL,
    rank INTEGER NOT NULL,
    market_open INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS poll_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_ts TEXT NOT NULL,
    stock_success INTEGER NOT NULL,
    crypto_success INTEGER NOT NULL,
    stock_row_count INTEGER NOT NULL,
    crypto_row_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
