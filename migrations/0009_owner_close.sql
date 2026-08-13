-- Owner-ordered position close (2026-08-13: "sell it tonight no
-- exceptions"). The ledger must record the sale as what it IS -- an owner
-- decision, not a rule exit -- so 'owner_close' joins paper_trades'
-- exit_reason CHECK and 'exit_owner_close' joins paper_orders' intent
-- CHECK. SQLite cannot ALTER a CHECK: recreate-copy-drop-rename (the
-- 0006 strategy_kill_state pattern).

CREATE TABLE IF NOT EXISTS paper_trades_new (
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
        'stop', 'take_profit', 'trailing_stop', 'scale_out', 'time_stop',
        'eod_flat', 'owner_close'
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
INSERT INTO paper_trades_new SELECT * FROM paper_trades;
DROP TABLE paper_trades;
ALTER TABLE paper_trades_new RENAME TO paper_trades;
CREATE INDEX IF NOT EXISTS idx_paper_trades_strategy_exit ON paper_trades(strategy_id, exit_ts);

CREATE TABLE IF NOT EXISTS paper_orders_new (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_ref TEXT NOT NULL UNIQUE,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    venue TEXT NOT NULL CHECK (venue IN ('ibkr_paper', 'crypto_sim')),
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    intent TEXT NOT NULL CHECK (intent IN (
        'entry', 'exit_stop', 'exit_take_profit', 'exit_trailing_stop',
        'exit_scale_out', 'exit_time_stop', 'exit_eod_flat',
        'exit_owner_close'
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
INSERT INTO paper_orders_new (order_id, order_ref, strategy_id, symbol, venue,
    side, intent, qty, status, perm_id, submitted_ts, filled_ts, fill_price)
SELECT order_id, order_ref, strategy_id, symbol, venue, side, intent, qty,
    status, perm_id, submitted_ts, filled_ts, fill_price FROM paper_orders;
DROP TABLE paper_orders;
ALTER TABLE paper_orders_new RENAME TO paper_orders;
CREATE INDEX IF NOT EXISTS idx_paper_orders_order_ref ON paper_orders(order_ref);
CREATE INDEX IF NOT EXISTS idx_paper_orders_symbol ON paper_orders(symbol);
