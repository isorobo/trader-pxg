-- Phase 5's new tables: paper_orders, paper_positions, paper_trades,
-- reconciliation_log, strategy_kill_state (see 05-CONTEXT.md, 05-01-PLAN.md
-- D-09). Follows migrations/0004_risk_breakers.sql's append-only
-- event-log + re-derived-state-view convention exactly where state
-- matters (reconciliation_log, strategy_kill_state): no mutable "current
-- state" column is trusted directly (standing rule 4).

-- paper_orders: one row per order this system has decided to submit, or has
-- discovered was filled at the broker. status now has three meaningful
-- states -- 'pending_submit' (decided locally, broker call not yet
-- confirmed), 'submitted' (broker call confirmed), 'filled' (broker
-- confirmed a fill, same-tick or healed later) -- plus 'rejected'. See
-- 05-01-PLAN.md's "REVISED order lifecycle" note (plan-checker BLOCKER 1):
-- 'pending_submit' is persisted BEFORE any broker call, so a crash between
-- decision and broker confirmation always leaves a local trace.
CREATE TABLE IF NOT EXISTS paper_orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_ref TEXT NOT NULL UNIQUE,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    venue TEXT NOT NULL CHECK (venue IN ('ibkr_paper', 'crypto_sim')),
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    intent TEXT NOT NULL CHECK (intent IN (
        'entry', 'exit_stop', 'exit_take_profit', 'exit_trailing_stop',
        'exit_scale_out', 'exit_time_stop', 'exit_eod_flat'
    )),
    qty REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_submit' CHECK (status IN (
        'pending_submit', 'submitted', 'filled', 'rejected'
    )),
    perm_id INTEGER,
    submitted_ts TEXT NOT NULL DEFAULT (datetime('now')),
    filled_ts TEXT,
    fill_price REAL
);

CREATE INDEX IF NOT EXISTS idx_paper_orders_order_ref ON paper_orders(order_ref);
CREATE INDEX IF NOT EXISTS idx_paper_orders_symbol ON paper_orders(symbol);

-- paper_positions: one row per open (or closed) position. exit_profile is
-- locked at entry (standing rule 2) and serialized here so the guardian can
-- rebuild it later without ever re-deriving it from anywhere else.
CREATE TABLE IF NOT EXISTS paper_positions (
    position_id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    venue TEXT NOT NULL CHECK (venue IN ('ibkr_paper', 'crypto_sim')),
    asset_class TEXT NOT NULL,
    qty REAL NOT NULL,
    entry_price REAL NOT NULL,
    entry_ts TEXT NOT NULL,
    entry_order_ref TEXT NOT NULL,
    stop_pct REAL,
    tp_pct REAL,
    scale_out_json TEXT NOT NULL DEFAULT '[]',
    trailing_pct REAL,
    max_hold_days INTEGER,
    eod_flat INTEGER NOT NULL DEFAULT 0,
    watermark REAL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed'))
);

CREATE INDEX IF NOT EXISTS idx_paper_positions_status ON paper_positions(status);
CREATE INDEX IF NOT EXISTS idx_paper_positions_strategy ON paper_positions(strategy_id);

-- paper_trades: one row per closed position (matches migrations/0003_backtest.sql's
-- exit_reason values verbatim).
CREATE TABLE IF NOT EXISTS paper_trades (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    profile_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    venue TEXT NOT NULL CHECK (venue IN ('ibkr_paper', 'crypto_sim')),
    asset_class TEXT NOT NULL,
    entry_ts TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_ts TEXT NOT NULL,
    exit_price REAL NOT NULL,
    exit_reason TEXT NOT NULL CHECK (exit_reason IN (
        'stop', 'take_profit', 'trailing_stop', 'scale_out', 'time_stop', 'eod_flat'
    )),
    qty REAL NOT NULL,
    fees REAL NOT NULL,
    slippage_cost REAL NOT NULL,
    pnl REAL NOT NULL,
    nzd_rate REAL,
    nzd_pnl REAL,
    entry_order_ref TEXT NOT NULL,
    exit_order_ref TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_paper_trades_strategy_exit ON paper_trades(strategy_id, exit_ts);

-- reconciliation_log: append-only event log, mirroring migrations/0004's
-- breaker_events/breaker_state_current pattern exactly (standing rule 4).
CREATE TABLE IF NOT EXISTS reconciliation_log (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    symbol TEXT,
    venue TEXT NOT NULL CHECK (venue IN ('ibkr_paper', 'crypto_sim', 'kraken_readonly')),
    local_qty REAL,
    broker_qty REAL,
    classification TEXT NOT NULL CHECK (classification IN ('explainable', 'unexplained', 'informational')),
    action TEXT NOT NULL CHECK (action IN ('log', 'halt', 'clear')),
    reason TEXT,
    actor TEXT NOT NULL DEFAULT 'system' CHECK (actor IN ('system', 'human'))
);

CREATE INDEX IF NOT EXISTS idx_reconciliation_log_action ON reconciliation_log(action);

-- Current halt state: re-derived every read (standing rule 4, exact mirror
-- of migrations/0004's breaker_state_current view). Entries are halted iff
-- this view's current_action = 'halt'.
CREATE VIEW IF NOT EXISTS reconciliation_halt_state AS
SELECT action AS current_action, ts AS since, reason
FROM reconciliation_log
WHERE action IN ('halt', 'clear')
ORDER BY event_id DESC
LIMIT 1;

-- strategy_kill_state: one row per retired strategy_id (a profile_name).
-- PK on strategy_id makes a second retirement call a no-op (idempotent).
CREATE TABLE IF NOT EXISTS strategy_kill_state (
    strategy_id TEXT PRIMARY KEY,
    retired_at TEXT NOT NULL DEFAULT (datetime('now')),
    reason TEXT NOT NULL CHECK (reason IN (
        'profit_factor_floor', 'max_drawdown', 'consecutive_losses'
    )),
    trigger_value REAL
);
