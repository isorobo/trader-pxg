r"""Human-run entrant registration -- the Phase 8 gate command.

Reads a survivor payload from an evidence file (e.g.
reports/backtests/donchian_evidence.json, produced by
run_donchian_evidence.py) and registers it as a 'candidate' with both
evidence stamps. The next weekly tournament run admits it to probation
automatically when the D-05 caps allow.

THE GATE: the phase doc opens Phase 8 ("optional signal expansion") only
after Phase 6 has graduated at least one incumbent. This command is
deliberately manual and requires --i-confirm-phase6-graduated -- the
operator's explicit assertion that the gate is open. It is never called
from any scheduled task or automated path.

    .venv\Scripts\python.exe -m trader.tournament.register_entrant \
        --evidence reports/backtests/donchian_evidence.json \
        --profile <survivor profile_name> \
        --i-confirm-phase6-graduated
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trader.backtest.config import EXIT_PROFILE


def main(argv: list[str] | None = None) -> None:
    from trader.data import db
    from trader.tournament import pipeline

    parser = argparse.ArgumentParser(
        prog="python -m trader.tournament.register_entrant",
        description="Register one evidence-backed strategy as a tournament candidate (D-07).",
    )
    parser.add_argument("--evidence", required=True, help="Path to the evidence JSON.")
    parser.add_argument(
        "--profile", required=True, help="survivor profile_name from the evidence file."
    )
    parser.add_argument(
        "--i-confirm-phase6-graduated",
        action="store_true",
        help="Required: the operator's assertion that Phase 6 has graduated "
        "at least one incumbent (the phase doc's Phase 8 gate).",
    )
    parser.add_argument("--db-path", default="data/trader.db")
    args = parser.parse_args(argv)

    if not args.i_confirm_phase6_graduated:
        print(
            "Refusing: Phase 8 opens only after Phase 6 graduates a strategy "
            "(phase doc). Pass --i-confirm-phase6-graduated once that is true.",
            file=sys.stderr,
        )
        sys.exit(2)

    evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    survivor = next(
        (s for s in evidence.get("survivors", []) if s["profile_name"] == args.profile),
        None,
    )
    if survivor is None:
        names = [s["profile_name"] for s in evidence.get("survivors", [])]
        print(
            f"No survivor named {args.profile!r} in {args.evidence}. "
            f"Survivors present: {names}",
            file=sys.stderr,
        )
        sys.exit(2)

    profile = EXIT_PROFILE(
        stop_pct=survivor["stop_pct"],
        tp_pct=survivor["tp_pct"],
        scale_out=(),
        trailing_pct=survivor["trailing_pct"],
        max_hold_days=survivor["max_hold_days"],
        eod_flat=False,
    )

    conn = db.get_connection(args.db_path)
    try:
        pipeline.register_candidate(
            conn,
            survivor["profile_name"],
            survivor["strategy_id"],
            profile,
            pf_floor=survivor["pf_floor"],
            max_dd_kill=survivor["max_dd_kill"],
            consecutive_loss_kill=survivor["consecutive_loss_kill"],
            reason=(
                f"owner-approved entrant via {args.evidence} "
                f"(entry_variant={survivor['entry_variant']})"
            ),
        )
        pipeline.stamp_backtest(conn, survivor["profile_name"], survivor["backtest_run_id"])
        pipeline.stamp_oos(conn, survivor["profile_name"], survivor["oos_result_ref"])
        print(
            f"Registered {survivor['profile_name']} as candidate with both "
            "evidence stamps -- the next weekly tournament run admits it to "
            "probation when caps allow."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
