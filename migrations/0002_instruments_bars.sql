-- Phase 1's new tables: instruments and bars (see 01-RESEARCH.md Schema Design,
-- 01-CONTEXT.md D-08/D-16).

CREATE TABLE IF NOT EXISTS instruments (
    symbol TEXT NOT NULL,
    venue TEXT NOT NULL,
    asset_class TEXT NOT NULL CHECK (asset_class IN ('stock', 'crypto_major', 'memecoin')),
    coingecko_id TEXT,
    override TEXT CHECK (override IN ('stock', 'crypto_major', 'memecoin') OR override IS NULL),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, venue)
);

CREATE TABLE IF NOT EXISTS bars (
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts TEXT NOT NULL,
    o REAL NOT NULL,
    h REAL NOT NULL,
    l REAL NOT NULL,
    c REAL NOT NULL,
    volume REAL NOT NULL,
    UNIQUE (venue, symbol, timeframe, ts)
);
