-- Phase 7's tournament substrate (07-01-PLAN.md, D-04/D-05/D-06/D-07/D-08/D-09).
--
-- strategy_registry is the DB-backed replacement for
-- trader/paper/config.py's LIVE_STRATEGY_CONFIGS tuple (D-08): the frozen
-- numeric columns are written ONCE at INSERT and never UPDATEd -- a changed
-- config is a NEW entrant (D-04), i.e. a new row with a new profile_name.
-- `state` is the one mutable column, and only via
-- trader/tournament/pipeline.py's single transition function, which appends
-- a strategy_registry_transitions row in the same transaction (standing
-- rule 4: state is always re-derivable from history).
--
-- States: 'candidate' (D-07 pipeline entrant, not live, includes D-05's
-- queue), 'probation' (live at 25% size), 'full' (live at full size),
-- 'retired' (terminal).
CREATE TABLE IF NOT EXISTS strategy_registry (
    profile_name TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    stop_pct REAL,
    tp_pct REAL,
    scale_out_json TEXT NOT NULL DEFAULT '[]',
    trailing_pct REAL,
    max_hold_days INTEGER,
    eod_flat INTEGER NOT NULL DEFAULT 0,
    pf_floor REAL NOT NULL,
    max_dd_kill REAL NOT NULL,
    consecutive_loss_kill INTEGER NOT NULL,
    -- D-07 evidence stamps -- each NULL until that pipeline stage passes.
    backtest_run_id INTEGER REFERENCES backtest_runs(run_id),
    oos_result_ref TEXT,
    paper_30_confirmed_at TEXT,
    entered_at TEXT NOT NULL DEFAULT (datetime('now')),
    state TEXT NOT NULL DEFAULT 'candidate' CHECK (state IN (
        'candidate', 'probation', 'full', 'retired'
    )),
    state_changed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_strategy_registry_state ON strategy_registry(state);

-- Append-only transition log, mirroring 0004's breaker_events /
-- 0005's reconciliation_log convention (standing rule 4).
CREATE TABLE IF NOT EXISTS strategy_registry_transitions (
    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    profile_name TEXT NOT NULL REFERENCES strategy_registry(profile_name),
    from_state TEXT,
    to_state TEXT NOT NULL CHECK (to_state IN (
        'candidate', 'probation', 'full', 'retired'
    )),
    reason TEXT NOT NULL,
    run_id INTEGER REFERENCES tournament_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_registry_transitions_profile
    ON strategy_registry_transitions(profile_name);

-- One row per weekly tournament evaluation (D-09). registry_hash_after is
-- NULL while a run is in flight and set by the run's own final UPDATE; a
-- completed run always has both hashes (tests/test_tournament_audit.py).
CREATE TABLE IF NOT EXISTS tournament_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    config_hash TEXT NOT NULL,
    registry_hash_before TEXT NOT NULL,
    registry_hash_after TEXT,
    inputs_snapshot_json TEXT NOT NULL,
    report_path TEXT
);

-- One row per strategy per run: the auditable decision record (D-09).
-- rule_citation quotes the pre-registered rule and the numbers that fired
-- it -- "decisions must be traceable to numbers" is the phase's exit gate.
-- demotion_strike marks a run where the D-04 compound demotion condition
-- (worst rank AND sharpe below the frozen floor) held; K consecutive
-- strikes retire the strategy.
CREATE TABLE IF NOT EXISTS tournament_decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES tournament_runs(run_id),
    profile_name TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('promote', 'retire', 'hold', 'enter')),
    prior_state TEXT,
    new_state TEXT,
    sharpe REAL,
    profit_factor REAL,
    trade_count INTEGER,
    rank INTEGER,
    demotion_strike INTEGER NOT NULL DEFAULT 0,
    rule_citation TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tournament_decisions_run ON tournament_decisions(run_id);
CREATE INDEX IF NOT EXISTS idx_tournament_decisions_profile
    ON tournament_decisions(profile_name);

-- Recreate strategy_kill_state with 'tournament_demotion' added to the
-- reason CHECK (07-RESEARCH.md Pitfall 2: SQLite cannot ALTER a CHECK, and
-- D-08's retire path calls ledger.retire_strategy with this new reason --
-- without the rebuild that call raises IntegrityError). Copy preserves any
-- existing retirements.
CREATE TABLE IF NOT EXISTS strategy_kill_state_v6 (
    strategy_id TEXT PRIMARY KEY,
    retired_at TEXT NOT NULL DEFAULT (datetime('now')),
    reason TEXT NOT NULL CHECK (reason IN (
        'profit_factor_floor', 'max_drawdown', 'consecutive_losses',
        'tournament_demotion'
    )),
    trigger_value REAL
);

INSERT OR IGNORE INTO strategy_kill_state_v6 (strategy_id, retired_at, reason, trigger_value)
SELECT strategy_id, retired_at, reason, trigger_value FROM strategy_kill_state;

DROP TABLE strategy_kill_state;

ALTER TABLE strategy_kill_state_v6 RENAME TO strategy_kill_state;

-- Seed: the five Phase 5 incumbent configs, transcribed verbatim from
-- trader/paper/config.py's LIVE_STRATEGY_CONFIGS (themselves transcribed
-- verbatim from KILL-CONDITIONS.md / oos_results_v2.json -- T-05-09, no
-- number here is new). Grandfathered at state='full': they pre-date the
-- D-07 pipeline, entered Phase 5 at full size, and Phase 6's graduation
-- data collection depends on that sizing staying unchanged. Their OOS
-- evidence stamp points at the Phase 3 artifact that admitted them.
INSERT OR IGNORE INTO strategy_registry
    (profile_name, strategy_id, stop_pct, tp_pct, scale_out_json, trailing_pct,
     max_hold_days, eod_flat, pf_floor, max_dd_kill, consecutive_loss_kill,
     oos_result_ref, state)
VALUES
    ('momentum_stock_stock_choppy_v2_loose_tune_stop-0.3_tp0.2_trailNone_holdNone',
     'momentum_stock', -0.3, 0.2, '[]', NULL, NULL, 0, 0.9, -0.0096, 8,
     'reports/backtests/oos_results_v2.json', 'full'),
    ('momentum_stock_stock_choppy_v2_loose_tune_stop-0.25_tp0.2_trailNone_holdNone',
     'momentum_stock', -0.25, 0.2, '[]', NULL, NULL, 0, 0.9, -0.0377, 8,
     'reports/backtests/oos_results_v2.json', 'full'),
    ('momentum_stock_stock_choppy_v2_loose_tune_stop-0.3_tp0.2_trailNone_hold30',
     'momentum_stock', -0.3, 0.2, '[]', NULL, 30, 0, 0.9, -0.0706, 8,
     'reports/backtests/oos_results_v2.json', 'full'),
    ('momentum_stock_stock_choppy_v2_loose_tune_stop-0.25_tp0.2_trailNone_hold30',
     'momentum_stock', -0.25, 0.2, '[]', NULL, 30, 0, 0.9, -0.0714, 8,
     'reports/backtests/oos_results_v2.json', 'full'),
    ('momentum_stock_stock_choppy_v2_loose_tune_stop-0.2_tp0.2_trailNone_hold30',
     'momentum_stock', -0.2, 0.2, '[]', NULL, 30, 0, 0.9, -0.0680, 8,
     'reports/backtests/oos_results_v2.json', 'full');

INSERT INTO strategy_registry_transitions (profile_name, from_state, to_state, reason)
SELECT profile_name, NULL, 'full',
       'seed: Phase 5 incumbent, grandfathered at full (backtest+OOS evidence: reports/backtests/oos_results_v2.json)'
FROM strategy_registry
WHERE state = 'full'
  AND profile_name NOT IN (SELECT profile_name FROM strategy_registry_transitions);
