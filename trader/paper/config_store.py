"""The DB-backed live-strategy-config loader (Phase 7, D-08).

strategy_registry (migrations/0006_tournament.sql) is the source of truth
for which strategy configs are live; this module rebuilds the same frozen
`LiveStrategyConfig` shape trader/paper/config.py's LIVE_STRATEGY_CONFIGS
tuple used to hardcode, so guardian/entry_pipeline/daily_report swap their
data source with zero signature changes. Tournament promote/retire decisions
UPDATE the registry's `state` column (via trader/tournament/pipeline.py's
transition function only) and take effect at each consumer's next run.

DB I/O lives HERE, never in config.py -- that module's docstring is an
explicit "no engine logic, no I/O" contract (07-RESEARCH.md Pitfall 1).

Every query is parameterized or parameter-free static SQL (ASVS V5).
"""

from __future__ import annotations

import json
import sqlite3

from trader.backtest.config import EXIT_PROFILE
from trader.paper.config import LiveStrategyConfig

# The registry states whose rows are live/tradeable -- 'candidate' rows are
# pipeline entrants not yet admitted (D-07), 'retired' is terminal (D-04).
_LIVE_STATES = ("probation", "full")


def _row_to_live_config(row: sqlite3.Row) -> LiveStrategyConfig:
    return LiveStrategyConfig(
        strategy_id=row["strategy_id"],
        profile_name=row["profile_name"],
        exit_profile=EXIT_PROFILE(
            stop_pct=row["stop_pct"],
            tp_pct=row["tp_pct"],
            scale_out=tuple(tuple(pair) for pair in json.loads(row["scale_out_json"])),
            trailing_pct=row["trailing_pct"],
            max_hold_days=row["max_hold_days"],
            eod_flat=bool(row["eod_flat"]),
        ),
        pf_floor=row["pf_floor"],
        max_dd_kill=row["max_dd_kill"],
        consecutive_loss_kill=row["consecutive_loss_kill"],
        state=row["state"],
    )


def get_live_configs(conn: sqlite3.Connection) -> tuple[LiveStrategyConfig, ...]:
    """Rows with state IN ('probation', 'full') only, ordered by
    profile_name -- retired and candidate rows never appear, so callers get
    the same "only tradeable configs" shape LIVE_STRATEGY_CONFIGS used to
    hardcode."""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    rows = cursor.execute(
        "SELECT * FROM strategy_registry WHERE state IN (?, ?) ORDER BY profile_name",
        _LIVE_STATES,
    ).fetchall()
    return tuple(_row_to_live_config(row) for row in rows)


def get_live_configs_by_profile_name(
    conn: sqlite3.Connection,
) -> dict[str, LiveStrategyConfig]:
    """O(1) lookup by profile_name, live rows only."""
    return {cfg.profile_name: cfg for cfg in get_live_configs(conn)}


def get_registry_rows(conn: sqlite3.Connection) -> list[dict]:
    """Every strategy_registry row as a plain dict, all states -- the
    judge's and dashboard's full-roster view (retired rows stay visible for
    attribution and audit)."""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    rows = cursor.execute(
        "SELECT * FROM strategy_registry ORDER BY profile_name"
    ).fetchall()
    return [dict(row) for row in rows]
