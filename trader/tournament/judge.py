"""The weekly tournament evaluation (ATTR-02, D-03/D-04/D-05/D-09).

One `--once`-shaped entry (`run_tournament_once`) that:

1. Verifies the D-06 freeze gate BEFORE any judging or DB write.
2. Snapshots the registry state hash, then judges every active strategy on
   its rolling JUDGING_WINDOW_TRADES closed paper trades via
   trader/backtest/metrics.py's compute_metrics -- reused unmodified, every
   strategy against the same PAPER_ACCOUNT_EQUITY base so Sharpe ranks are
   comparable (07-RESEARCH.md Q2/Pitfall 4).
3. Applies the pre-registered rules, writing one auditable
   tournament_decisions row per strategy whose rule_citation quotes the
   numbers that fired (D-09: "decisions must be traceable to numbers" is
   the phase's exit gate).
4. Attempts queued candidate admissions AFTER promote/retire decisions are
   applied, so slots freed this run open this run (D-05).
5. Stamps the after-hash, writes the markdown decision record, and sends a
   Telegram summary via the existing alerts.notify.

Demotion is the compound rule (D-04, frozen): worst rank among 'full'
strategies AND Sharpe below the frozen floor, sustained for
DEMOTION_SUSTAIN_EVALUATIONS consecutive runs -- never rank alone, so a
healthy roster is never emptied by attrition (07-RESEARCH.md Pitfall 5).
Strikes live on the decision rows themselves (demotion_strike), so the
sustain count is always re-derivable from the audit trail.
"""

from __future__ import annotations

import json
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from trader.backtest import metrics
from trader.paper import alerts, config, config_store, ledger
from trader.tournament import freeze_gate, frozen_config, pipeline

_NEG_INF = float("-inf")


def registry_state_hash(conn: sqlite3.Connection) -> str:
    """sha256 over sorted (profile_name, state) pairs -- the at-a-glance
    "did anything change" audit hash (D-09)."""
    rows = conn.execute(
        "SELECT profile_name, state FROM strategy_registry ORDER BY profile_name"
    ).fetchall()
    digest = hashlib.sha256()
    for profile_name, state in rows:
        digest.update(f"{profile_name}:{state}\n".encode())
    return digest.hexdigest()


def judge_strategy(conn: sqlite3.Connection, profile_name: str) -> dict:
    """Rolling-window judging metrics for one strategy: metrics.py reused
    unmodified, fixed starting-equity base for comparability."""
    trades = ledger.get_recent_trades(
        conn, profile_name, limit=frozen_config.JUDGING_WINDOW_TRADES
    )
    return metrics.compute_metrics(
        trades, starting_equity=config.PAPER_ACCOUNT_EQUITY
    )


def _rank_key(judged: dict) -> tuple:
    """Descending-sort key: Sharpe first, profit factor the tie-break
    (D-03). None sorts worst (an undefined Sharpe/PF is never evidence of
    edge)."""
    sharpe = judged.get("sharpe_ratio")
    pf = judged.get("profit_factor")
    return (
        sharpe if sharpe is not None else _NEG_INF,
        pf if pf is not None else _NEG_INF,
    )


def rank_full_strategies(judged_by_name: dict[str, dict]) -> dict[str, int]:
    """Rank 1 = best. Input: {profile_name: compute_metrics dict} for the
    eligible 'full' cohort."""
    ordered = sorted(
        judged_by_name, key=lambda name: _rank_key(judged_by_name[name]), reverse=True
    )
    return {name: i + 1 for i, name in enumerate(ordered)}


def _consecutive_prior_strikes(conn: sqlite3.Connection, profile_name: str) -> int:
    """Leading run of demotion_strike=1 decisions for this profile, most
    recent run first -- broken by any strike-free evaluation."""
    rows = conn.execute(
        """
        SELECT demotion_strike FROM tournament_decisions
        WHERE profile_name = ?
        ORDER BY run_id DESC
        """,
        (profile_name,),
    ).fetchall()
    streak = 0
    for (strike,) in rows:
        if strike:
            streak += 1
        else:
            break
    return streak


def _record_decision(conn: sqlite3.Connection, run_id: int, d: dict) -> None:
    conn.execute(
        """
        INSERT INTO tournament_decisions
            (run_id, profile_name, decision, prior_state, new_state, sharpe,
             profit_factor, trade_count, rank, demotion_strike, rule_citation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            d["profile_name"],
            d["decision"],
            d.get("prior_state"),
            d.get("new_state"),
            d.get("sharpe"),
            d.get("profit_factor"),
            d.get("trade_count"),
            d.get("rank"),
            int(d.get("demotion_strike", 0)),
            d["rule_citation"],
        ),
    )
    conn.commit()


def _fmt(value) -> str:
    if value is None:
        return "None"
    return f"{value:.4f}"


def _write_report(
    run_id: int,
    now: datetime,
    hash_before: str,
    hash_after: str,
    inputs: dict,
    decisions: list[dict],
    base_dir: str,
) -> Path:
    base_path = Path(base_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    report_path = base_path / f"{now.date().isoformat()}-run{run_id}.md"

    lines = [
        f"# Tournament Run {run_id} -- {now.date().isoformat()}",
        "",
        f"- **Frozen rules hash:** {freeze_gate.FROZEN_TOURNAMENT_HASH}",
        f"- **Registry hash before:** {hash_before}",
        f"- **Registry hash after:** {hash_after}",
        f"- **Roster changed:** {hash_before != hash_after}",
        "",
        "## Judging Inputs (rolling 30 closed paper trades each)",
        "",
        "| Strategy | State | Trades | Sharpe | PF |",
        "|---|---|---|---|---|",
    ]
    for name, snap in sorted(inputs.items()):
        lines.append(
            f"| {name} | {snap['state']} | {snap['trade_count']} "
            f"| {_fmt(snap['sharpe'])} | {_fmt(snap['profit_factor'])} |"
        )
    lines += ["", "## Decisions", ""]
    for d in decisions:
        lines.append(
            f"- **{d['profile_name']}** -- `{d['decision']}` "
            f"({d.get('prior_state')} -> {d.get('new_state')}): {d['rule_citation']}"
        )
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def run_tournament_once(
    conn: sqlite3.Connection,
    now: datetime | None = None,
    report_base_dir: str = "reports/tournament",
) -> dict:
    """One full tournament evaluation. Returns a summary dict; every
    decision it makes is also in tournament_decisions with a rule citation,
    and the run itself in tournament_runs with before/after hashes."""
    # 1. The hard D-06 gate -- before any judging, decision, or DB write.
    freeze_gate.verify_frozen_tournament()
    now = now or datetime.now(timezone.utc)

    hash_before = registry_state_hash(conn)
    rows = config_store.get_registry_rows(conn)
    active = [r for r in rows if r["state"] in ("probation", "full")]
    candidates = [r for r in rows if r["state"] == "candidate"]

    # 2. Judge every active strategy (metrics.py, unmodified).
    judged: dict[str, dict] = {
        r["profile_name"]: judge_strategy(conn, r["profile_name"]) for r in active
    }
    inputs_snapshot = {
        r["profile_name"]: {
            "state": r["state"],
            "trade_count": judged[r["profile_name"]]["trade_count"],
            "sharpe": judged[r["profile_name"]]["sharpe_ratio"],
            "profit_factor": judged[r["profile_name"]]["profit_factor"],
        }
        for r in active
    }

    cursor = conn.execute(
        """
        INSERT INTO tournament_runs
            (ts, config_hash, registry_hash_before, inputs_snapshot_json)
        VALUES (?, ?, ?, ?)
        """,
        (
            now.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            freeze_gate.FROZEN_TOURNAMENT_HASH,
            hash_before,
            json.dumps(inputs_snapshot),
        ),
    )
    run_id = cursor.lastrowid
    conn.commit()

    min_trades = frozen_config.MIN_TRADES_FOR_JUDGING
    decisions: list[dict] = []

    # 3a. Eligible 'full' cohort ranking (Sharpe, PF tie-break).
    full_eligible = {
        name: judged[name]
        for name, r in ((r["profile_name"], r) for r in active)
        if r["state"] == "full" and judged[name]["trade_count"] >= min_trades
    }
    ranks = rank_full_strategies(full_eligible)
    worst_rank = max(ranks.values()) if ranks else None

    for r in active:
        name = r["profile_name"]
        state = r["state"]
        m = judged[name]
        sharpe = m["sharpe_ratio"]
        pf = m["profit_factor"]
        n = m["trade_count"]
        base = {
            "profile_name": name,
            "prior_state": state,
            "sharpe": sharpe,
            "profit_factor": pf,
            "trade_count": n,
        }

        if n < min_trades:
            decisions.append(
                {
                    **base,
                    "decision": "hold",
                    "new_state": state,
                    "rule_citation": (
                        f"D-03 eligibility: trade_count={n} < {min_trades} -- "
                        "not judged this run"
                    ),
                }
            )
            continue

        if state == "probation":
            pipeline.confirm_paper_30(conn, name, now=now)
            floor = frozen_config.SHARPE_PROMOTION_FLOOR
            if sharpe is not None and sharpe >= floor:
                citation = (
                    f"D-04 promotion: sharpe={sharpe:.4f} >= floor {floor} "
                    f"@ {n} trades (PF={_fmt(pf)})"
                )
                pipeline.promote_to_full(conn, name, sharpe, now=now, run_id=run_id)
                decisions.append(
                    {
                        **base,
                        "decision": "promote",
                        "new_state": "full",
                        "rule_citation": citation,
                    }
                )
            else:
                decisions.append(
                    {
                        **base,
                        "decision": "hold",
                        "new_state": state,
                        "rule_citation": (
                            f"D-04 hold: sharpe={_fmt(sharpe)} below promotion "
                            f"floor {floor} @ {n} trades -- stays on probation"
                        ),
                    }
                )
            continue

        # state == 'full', eligible.
        rank = ranks[name]
        floor = frozen_config.SHARPE_DEMOTION_FLOOR
        below_floor = sharpe is None or sharpe < floor
        is_worst = rank == worst_rank and len(ranks) > 1
        if is_worst and below_floor:
            streak = _consecutive_prior_strikes(conn, name) + 1
            sustain = frozen_config.DEMOTION_SUSTAIN_EVALUATIONS
            if streak >= sustain:
                citation = (
                    f"D-04 demotion: worst rank ({rank}/{len(ranks)}) AND "
                    f"sharpe={_fmt(sharpe)} < floor {floor}, sustained "
                    f"{streak}/{sustain} consecutive weekly evaluations -- retired"
                )
                pipeline.retire(conn, name, citation, sharpe, now=now, run_id=run_id)
                decisions.append(
                    {
                        **base,
                        "decision": "retire",
                        "new_state": "retired",
                        "rank": rank,
                        "demotion_strike": 1,
                        "rule_citation": citation,
                    }
                )
            else:
                decisions.append(
                    {
                        **base,
                        "decision": "hold",
                        "new_state": state,
                        "rank": rank,
                        "demotion_strike": 1,
                        "rule_citation": (
                            f"D-04 demotion strike {streak}/{sustain}: worst rank "
                            f"({rank}/{len(ranks)}) AND sharpe={_fmt(sharpe)} < "
                            f"floor {floor} -- held pending sustain"
                        ),
                    }
                )
        else:
            decisions.append(
                {
                    **base,
                    "decision": "hold",
                    "new_state": state,
                    "rank": rank,
                    "rule_citation": (
                        f"D-04 hold: rank {rank}/{len(ranks)}, "
                        f"sharpe={_fmt(sharpe)} (PF={_fmt(pf)}) -- no "
                        "pre-registered rule fired"
                    ),
                }
            )

    # 3b. Candidate admissions AFTER promote/retire applied -- slots freed
    # this run open this run (D-05).
    for r in candidates:
        name = r["profile_name"]
        base = {"profile_name": name, "prior_state": "candidate"}
        if r["backtest_run_id"] is None or r["oos_result_ref"] is None:
            decisions.append(
                {
                    **base,
                    "decision": "hold",
                    "new_state": "candidate",
                    "rule_citation": (
                        "D-07 queue: evidence incomplete "
                        f"(backtest_run_id={r['backtest_run_id']}, "
                        f"oos_result_ref={r['oos_result_ref']!r}) -- not admitted"
                    ),
                }
            )
            continue
        try:
            pipeline.promote_to_probation(conn, name, now=now, run_id=run_id)
            decisions.append(
                {
                    **base,
                    "decision": "enter",
                    "new_state": "probation",
                    "rule_citation": (
                        f"D-07/D-05 entry: backtest run {r['backtest_run_id']} + "
                        f"OOS {r['oos_result_ref']!r} verified; admitted to "
                        "probation at "
                        f"{frozen_config.PROBATION_SIZE_MULTIPLIER:.0%} size"
                    ),
                }
            )
        except pipeline.CapExceeded as cap:
            decisions.append(
                {
                    **base,
                    "decision": "hold",
                    "new_state": "candidate",
                    "rule_citation": f"D-05 queue: {cap}",
                }
            )

    for d in decisions:
        _record_decision(conn, run_id, d)

    # 4. Close out the run: after-hash, report, Telegram summary.
    hash_after = registry_state_hash(conn)
    report_path = _write_report(
        run_id, now, hash_before, hash_after, inputs_snapshot, decisions,
        report_base_dir,
    )
    conn.execute(
        "UPDATE tournament_runs SET registry_hash_after = ?, report_path = ? "
        "WHERE run_id = ?",
        (hash_after, str(report_path), run_id),
    )
    conn.commit()

    counts = {kind: 0 for kind in ("promote", "retire", "hold", "enter")}
    for d in decisions:
        counts[d["decision"]] += 1
    alerts.notify(
        "tournament",
        f"tournament run {run_id}: {counts['promote']} promoted, "
        f"{counts['retire']} retired, {counts['enter']} entered, "
        f"{counts['hold']} held; roster changed={hash_before != hash_after}; "
        f"report {report_path}",
    )

    return {
        "run_id": run_id,
        "decisions": decisions,
        "counts": counts,
        "registry_hash_before": hash_before,
        "registry_hash_after": hash_after,
        "report_path": str(report_path),
    }
