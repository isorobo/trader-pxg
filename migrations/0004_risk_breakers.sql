-- Phase 4's new table: breaker_events (see 04-CONTEXT.md D-04/D-05,
-- 04-RESEARCH.md Q4). An append-only event log -- rather than a single
-- mutable "current state" row -- gives an audit trail and makes standing
-- rule 4 ("if the system and any external state ever disagree, halt") easy
-- to implement: state is re-derived from the event log and compared,
-- rather than trusted from a cached column that could itself have
-- silently drifted.

CREATE TABLE IF NOT EXISTS breaker_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    breaker_type TEXT NOT NULL CHECK (breaker_type IN ('daily_loss', 'drawdown', 'consecutive_loss')),
    action TEXT NOT NULL CHECK (action IN ('trip', 'reset', 'manual_restart')),
    trigger_value REAL,
    reason TEXT,
    actor TEXT NOT NULL DEFAULT 'system' CHECK (actor IN ('system', 'human'))
);

CREATE INDEX IF NOT EXISTS idx_breaker_events_type ON breaker_events(breaker_type);

-- Current-state view: the latest event per breaker_type IS the current
-- state. A breaker is "tripped" iff its latest event's action is 'trip' (a
-- later 'reset' or 'manual_restart' clears it back to normal). This lets
-- state be re-derived instead of trusted from a cached column (standing
-- rule 4).
CREATE VIEW IF NOT EXISTS breaker_state_current AS
SELECT be.breaker_type, be.action AS current_action, be.ts AS since, be.reason
FROM breaker_events be
INNER JOIN (
    SELECT breaker_type, MAX(event_id) AS max_event_id
    FROM breaker_events
    GROUP BY breaker_type
) latest ON be.breaker_type = latest.breaker_type AND be.event_id = latest.max_event_id;
