-- Multi-signal live book (owner-approved 2026-07-30): each live strategy
-- family scans its OWN entry signal, so the registry must record which
-- frozen entry variant a row trades. Incumbent momentum rows backfill to
-- 'loose' -- the variant Phase 5 hardcoded for them from the start
-- (05-06-PLAN.md D-01/D-02/D-14); this is a transcription, not a change.
ALTER TABLE strategy_registry ADD COLUMN entry_variant TEXT;

UPDATE strategy_registry
SET entry_variant = 'loose'
WHERE strategy_id = 'momentum_stock' AND entry_variant IS NULL;
