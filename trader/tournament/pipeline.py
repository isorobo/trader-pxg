"""The D-07 new-strategy pipeline as a checklist state machine (ATTR-03):

    candidate --(backtest + OOS evidence, caps allow)--> probation
    probation --(paper-30 stamp + Sharpe >= frozen floor)--> full
    probation/full --(kill trip or sustained demotion)--> retired (terminal)

No stage is skippable in code: every transition validates its evidence
stamps and raises otherwise, and every state change goes through ONE
private function that UPDATEs strategy_registry.state and appends a
strategy_registry_transitions row in the same transaction -- never a bare
UPDATE (standing rule 4: state is always re-derivable from history).

A retired profile_name is terminal (D-04): a changed config is a NEW
entrant under a NEW profile_name, never a resurrection.

Caps (D-05, frozen in trader/tournament/frozen_config.py): at most
MAX_ACTIVE_STRATEGIES rows in probation+full, at most
MAX_NEW_ENTRANTS_PER_QUARTER candidate->probation admissions per calendar
quarter. Candidates beyond either cap simply stay 'candidate' (the queue).

Every query is parameterized SQL (ASVS V5).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone

from trader.backtest.config import EXIT_PROFILE
from trader.paper import ledger
from trader.tournament import frozen_config

_ACTIVE_STATES = ("probation", "full")

# The only sanctioned state changes. Keyed (from_state, to_state);
# 'retired' never appears as a from_state -- terminal by construction.
_VALID_TRANSITIONS = {
    ("candidate", "probation"),
    ("probation", "full"),
    ("probation", "retired"),
    ("full", "retired"),
}


class MissingEvidence(ValueError):
    """A transition was attempted without its prerequisite evidence stamp."""


class CapExceeded(RuntimeError):
    """D-05: admitting this entrant would breach the active-roster cap or
    the quarterly new-entrant cap -- the candidate stays queued."""


class TerminalState(RuntimeError):
    """D-04: 'retired' is terminal for a profile_name."""


def _now_iso(now: datetime | None) -> str:
    now = now or datetime.now(timezone.utc)
    # SQLite's own datetime('now') string shape (space separator, UTC, no
    # offset) -- matches the tables' DEFAULT clauses so string comparisons
    # in windowed queries stay format-consistent (daily_report.py's
    # timestamp note).
    return now.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _get_row(conn: sqlite3.Connection, profile_name: str) -> dict:
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    row = cursor.execute(
        "SELECT * FROM strategy_registry WHERE profile_name = ?", (profile_name,)
    ).fetchone()
    if row is None:
        raise ValueError(f"no strategy_registry row for profile_name={profile_name!r}")
    return dict(row)


def _transition(
    conn: sqlite3.Connection,
    profile_name: str,
    to_state: str,
    reason: str,
    now: datetime | None = None,
    run_id: int | None = None,
) -> None:
    """The ONE place strategy_registry.state ever changes: validates the
    transition, UPDATEs state, and appends the audit transition row in the
    same transaction."""
    row = _get_row(conn, profile_name)
    from_state = row["state"]
    if from_state == "retired":
        raise TerminalState(
            f"{profile_name} is retired -- terminal (D-04); a changed config "
            "is a NEW entrant under a new profile_name"
        )
    if (from_state, to_state) not in _VALID_TRANSITIONS:
        raise ValueError(
            f"invalid transition {from_state!r} -> {to_state!r} for {profile_name}"
        )

    ts = _now_iso(now)
    conn.execute(
        "UPDATE strategy_registry SET state = ?, state_changed_at = ? WHERE profile_name = ?",
        (to_state, ts, profile_name),
    )
    conn.execute(
        """
        INSERT INTO strategy_registry_transitions
            (ts, profile_name, from_state, to_state, reason, run_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ts, profile_name, from_state, to_state, reason, run_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Stage 0: registration (a human-approved entrant enters the queue)
# ---------------------------------------------------------------------------


def register_candidate(
    conn: sqlite3.Connection,
    profile_name: str,
    strategy_id: str,
    exit_profile: EXIT_PROFILE,
    pf_floor: float,
    max_dd_kill: float,
    consecutive_loss_kill: int,
    reason: str,
    now: datetime | None = None,
    entry_variant: str = "loose",
) -> None:
    """Insert a new 'candidate' row (frozen numeric columns written once,
    never UPDATEd) plus its transition record. Raises ValueError on a
    duplicate profile_name -- including a retired one (terminal)."""
    existing = conn.execute(
        "SELECT 1 FROM strategy_registry WHERE profile_name = ?", (profile_name,)
    ).fetchone()
    if existing is not None:
        raise ValueError(
            f"profile_name {profile_name!r} already registered -- a changed "
            "config is a NEW entrant under a new profile_name (D-04)"
        )

    ts = _now_iso(now)
    conn.execute(
        """
        INSERT INTO strategy_registry
            (profile_name, strategy_id, stop_pct, tp_pct, scale_out_json,
             trailing_pct, max_hold_days, eod_flat, pf_floor, max_dd_kill,
             consecutive_loss_kill, entered_at, state, state_changed_at,
             entry_variant)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?, ?)
        """,
        (
            profile_name,
            strategy_id,
            exit_profile.stop_pct,
            exit_profile.tp_pct,
            json.dumps(list(exit_profile.scale_out)),
            exit_profile.trailing_pct,
            exit_profile.max_hold_days,
            int(exit_profile.eod_flat),
            pf_floor,
            max_dd_kill,
            consecutive_loss_kill,
            ts,
            ts,
            entry_variant,
        ),
    )
    conn.execute(
        """
        INSERT INTO strategy_registry_transitions
            (ts, profile_name, from_state, to_state, reason)
        VALUES (?, ?, NULL, 'candidate', ?)
        """,
        (ts, profile_name, reason),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Evidence stamps (write-once)
# ---------------------------------------------------------------------------


def stamp_backtest(conn: sqlite3.Connection, profile_name: str, run_id: int) -> None:
    """Stamp the backtest-passed evidence (a backtest_runs run_id, D-07).
    Write-once: re-stamping with a different value raises."""
    row = _get_row(conn, profile_name)
    if row["backtest_run_id"] is not None:
        if row["backtest_run_id"] != run_id:
            raise ValueError(
                f"{profile_name} backtest evidence already stamped as run "
                f"{row['backtest_run_id']} -- evidence stamps are write-once"
            )
        return
    conn.execute(
        "UPDATE strategy_registry SET backtest_run_id = ? WHERE profile_name = ?",
        (run_id, profile_name),
    )
    conn.commit()


def stamp_oos(conn: sqlite3.Connection, profile_name: str, result_ref: str) -> None:
    """Stamp the OOS-passed evidence (an oos_results artifact reference,
    D-07). Write-once, same policy as stamp_backtest."""
    row = _get_row(conn, profile_name)
    if row["oos_result_ref"] is not None:
        if row["oos_result_ref"] != result_ref:
            raise ValueError(
                f"{profile_name} OOS evidence already stamped as "
                f"{row['oos_result_ref']!r} -- evidence stamps are write-once"
            )
        return
    conn.execute(
        "UPDATE strategy_registry SET oos_result_ref = ? WHERE profile_name = ?",
        (result_ref, profile_name),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Caps (D-05)
# ---------------------------------------------------------------------------


def active_count(conn: sqlite3.Connection) -> int:
    (count,) = conn.execute(
        "SELECT COUNT(*) FROM strategy_registry WHERE state IN (?, ?)",
        _ACTIVE_STATES,
    ).fetchone()
    return count


def _quarter_start(now: datetime) -> str:
    quarter_month = 3 * ((now.month - 1) // 3) + 1
    return f"{date(now.year, quarter_month, 1).isoformat()} 00:00:00"


def entrants_this_quarter(conn: sqlite3.Connection, now: datetime | None = None) -> int:
    """Candidate->probation admissions in `now`'s calendar quarter, counted
    from the transition log (never a mutable counter -- standing rule 4)."""
    now = now or datetime.now(timezone.utc)
    (count,) = conn.execute(
        """
        SELECT COUNT(*) FROM strategy_registry_transitions
        WHERE from_state = 'candidate' AND to_state = 'probation' AND ts >= ?
        """,
        (_quarter_start(now),),
    ).fetchone()
    return count


# ---------------------------------------------------------------------------
# Transitions (each validates its own prerequisite evidence)
# ---------------------------------------------------------------------------


def promote_to_probation(
    conn: sqlite3.Connection,
    profile_name: str,
    now: datetime | None = None,
    run_id: int | None = None,
) -> None:
    """candidate -> probation: requires BOTH the backtest and OOS evidence
    stamps (D-07, no stage skippable) and room under both D-05 caps."""
    row = _get_row(conn, profile_name)
    missing = [
        stamp
        for stamp, value in (
            ("backtest_run_id", row["backtest_run_id"]),
            ("oos_result_ref", row["oos_result_ref"]),
        )
        if value is None
    ]
    if missing:
        raise MissingEvidence(
            f"{profile_name} cannot enter probation: missing evidence "
            f"stamp(s) {missing} (D-07: no stage skippable)"
        )

    active = active_count(conn)
    if active >= frozen_config.MAX_ACTIVE_STRATEGIES:
        raise CapExceeded(
            f"active roster is full ({active}/{frozen_config.MAX_ACTIVE_STRATEGIES}) "
            f"-- {profile_name} stays queued (D-05)"
        )
    entrants = entrants_this_quarter(conn, now)
    if entrants >= frozen_config.MAX_NEW_ENTRANTS_PER_QUARTER:
        raise CapExceeded(
            f"quarterly entrant cap reached ({entrants}/"
            f"{frozen_config.MAX_NEW_ENTRANTS_PER_QUARTER}) -- "
            f"{profile_name} stays queued (D-05)"
        )

    _transition(
        conn,
        profile_name,
        "probation",
        f"D-07 admission: backtest run {row['backtest_run_id']} + OOS "
        f"{row['oos_result_ref']!r} verified; active {active + 1}/"
        f"{frozen_config.MAX_ACTIVE_STRATEGIES}, quarter entrants "
        f"{entrants + 1}/{frozen_config.MAX_NEW_ENTRANTS_PER_QUARTER}",
        now=now,
        run_id=run_id,
    )


def confirm_paper_30(
    conn: sqlite3.Connection, profile_name: str, now: datetime | None = None
) -> bool:
    """Stamp paper_30_confirmed_at once >= MIN_TRADES_FOR_JUDGING closed
    paper trades exist for the profile (ledger count is the evidence --
    D-02, no parallel bookkeeping). Returns True iff the stamp is present
    after the call. Idempotent."""
    row = _get_row(conn, profile_name)
    if row["paper_30_confirmed_at"] is not None:
        return True

    (count,) = conn.execute(
        "SELECT COUNT(*) FROM paper_trades WHERE strategy_id = ?", (profile_name,)
    ).fetchone()
    if count < frozen_config.MIN_TRADES_FOR_JUDGING:
        return False

    conn.execute(
        "UPDATE strategy_registry SET paper_30_confirmed_at = ? WHERE profile_name = ?",
        (_now_iso(now), profile_name),
    )
    conn.commit()
    return True


def promote_to_full(
    conn: sqlite3.Connection,
    profile_name: str,
    sharpe: float | None,
    now: datetime | None = None,
    run_id: int | None = None,
) -> None:
    """probation -> full: requires the paper-30 stamp (D-07) and judging
    Sharpe at or above the frozen promotion floor (D-04)."""
    row = _get_row(conn, profile_name)
    if row["paper_30_confirmed_at"] is None:
        raise MissingEvidence(
            f"{profile_name} cannot go full: paper_30_confirmed_at is not "
            "stamped (D-07: no stage skippable)"
        )
    if sharpe is None or sharpe < frozen_config.SHARPE_PROMOTION_FLOOR:
        raise ValueError(
            f"{profile_name} cannot go full: sharpe={sharpe} is below the "
            f"frozen promotion floor {frozen_config.SHARPE_PROMOTION_FLOOR}"
        )
    _transition(
        conn,
        profile_name,
        "full",
        f"D-04 promotion: sharpe={sharpe:.4f} >= floor "
        f"{frozen_config.SHARPE_PROMOTION_FLOOR} with paper-30 confirmed "
        f"{row['paper_30_confirmed_at']}",
        now=now,
        run_id=run_id,
    )


def retire(
    conn: sqlite3.Connection,
    profile_name: str,
    reason: str,
    trigger_value: float | None,
    now: datetime | None = None,
    run_id: int | None = None,
) -> None:
    """probation/full -> retired (terminal), AND the existing kill path
    (D-08): ledger.retire_strategy writes strategy_kill_state with the
    'tournament_demotion' reason so guardian/entry_pipeline's own retired
    checks agree with the registry."""
    _transition(conn, profile_name, "retired", reason, now=now, run_id=run_id)
    ledger.retire_strategy(conn, profile_name, "tournament_demotion", trigger_value)
