r"""Human/owner-authorised entrant registration (D-07: "human-approved
entrants only").

Reads a survivor payload from an evidence file (produced by a
run_*_evidence.py driver) and registers it as a 'candidate' with both
evidence stamps and its entry_variant. The next weekly tournament run
admits it to probation automatically when the D-05 caps allow.

THE GATE: --owner-approval "<quoted authorisation>" is required. The text
is recorded verbatim in the strategy_registry_transitions reason -- every
entrant's admission is traceable to an explicit owner instruction
(originally a Phase-6-graduation self-gate; replaced 2026-07-30 by the
owner's direct instruction to run the new strategies in the live paper
mix: "use a mix of all of them use more that one at once if needded").
This command is never called from any scheduled task or automated path.

The entrant's (strategy_id, entry_variant) must be routable by
trader/paper/signals.py -- a live row whose signal the entry pipeline
cannot scan would trade someone else's signal, which the system never does.

    .venv\Scripts\python.exe -m trader.tournament.register_entrant \
        --evidence reports/backtests/donchian_evidence.json \
        --profile <survivor profile_name> \
        --owner-approval "<why/when the owner authorised this entrant>"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trader.backtest.config import EXIT_PROFILE


def main(argv: list[str] | None = None) -> None:
    from trader.data import db
    from trader.paper import signals
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
        "--owner-approval",
        default=None,
        help="Required: the owner's authorisation for this entrant, recorded "
        "verbatim in the transition audit trail.",
    )
    parser.add_argument("--db-path", default="data/trader.db")
    args = parser.parse_args(argv)

    if not args.owner_approval:
        print(
            "Refusing: entrants are human-approved only (D-07). Pass "
            '--owner-approval "<the owner\'s instruction>" so the admission '
            "is traceable in the audit trail.",
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

    if not signals.is_routable(survivor["strategy_id"], survivor["entry_variant"]):
        print(
            f"Refusing: ({survivor['strategy_id']!r}, "
            f"{survivor['entry_variant']!r}) has no route in "
            "trader/paper/signals.py -- wire the family's frozen signal "
            "there first, or this row would silently trade another "
            "family's signal.",
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
                f"(entry_variant={survivor['entry_variant']}); "
                f"owner approval: {args.owner_approval}"
            ),
            entry_variant=survivor["entry_variant"],
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
