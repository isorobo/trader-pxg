-- Phase 2's new tables: backtest_runs and backtest_trades (see
-- 02-CONTEXT.md D-11, 02-01-PLAN.md). One row per run in backtest_runs;
-- one row per FILL (entry or scale-out tranche or final exit) in
-- backtest_trades, sharing a position_id for multi-tranche positions.

CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    strategy_id TEXT NOT NULL,
    profile TEXT NOT NULL,
    params_json TEXT NOT NULL,
    seed INTEGER NOT NULL,
    code_version TEXT
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES backtest_runs(run_id),
    position_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    asset_class TEXT NOT NULL CHECK (asset_class IN ('stock', 'crypto_major', 'memecoin')),
    entry_ts TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_ts TEXT NOT NULL,
    exit_price REAL NOT NULL,
    qty REAL NOT NULL,
    fees REAL NOT NULL,
    slippage REAL NOT NULL,
    pnl REAL NOT NULL,
    exit_reason TEXT NOT NULL CHECK (exit_reason IN ('stop', 'take_profit', 'trailing_stop', 'scale_out', 'time_stop', 'eod_flat'))
);

CREATE INDEX IF NOT EXISTS idx_backtest_trades_run ON backtest_trades(run_id);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_strategy ON backtest_trades(strategy_id);
