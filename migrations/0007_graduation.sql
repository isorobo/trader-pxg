-- Phase 6's graduation review audit table (06-01-PLAN.md). Append-only:
-- one row per strategy per weekly review, carrying every check's value and
-- verdict plus the checklist hash in force -- the owner's graduation
-- decision (a human act, Phase 9 gate) is always traceable to a specific
-- reviewed row (standing rule 4's re-derivability discipline).
CREATE TABLE IF NOT EXISTS graduation_reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    profile_name TEXT NOT NULL,
    trade_count INTEGER NOT NULL,
    profit_factor REAL,
    pf_pass INTEGER NOT NULL DEFAULT 0,
    max_drawdown REAL,
    max_dd_pass INTEGER NOT NULL DEFAULT 0,
    profitable_conditions INTEGER,
    conditions_pass INTEGER NOT NULL DEFAULT 0,
    single_trade_share REAL,
    single_trade_pass INTEGER NOT NULL DEFAULT 0,
    adverse_fill_pnl REAL,
    adverse_fill_pass INTEGER NOT NULL DEFAULT 0,
    overall TEXT NOT NULL CHECK (overall IN ('pass', 'fail', 'not_enough_trades')),
    checklist_hash TEXT NOT NULL,
    report_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_graduation_reviews_profile
    ON graduation_reviews(profile_name);
