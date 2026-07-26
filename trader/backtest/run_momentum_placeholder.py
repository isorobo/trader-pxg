"""End-to-end proof of the full backtest pipe (D-15, BACK-06, phase success
criterion 2): run the simplest-possible momentum placeholder strategy over
AAPL's real cached history, offline, and produce a real ledger, real
metrics, and a real markdown report on disk.

No strategy-development ambition here -- that is Phase 3's job. This module
exists only to wire run_backtest + compute_metrics + write_report together
for a single concrete strategy, proving BACK-01 through BACK-06 work
together as one pipe with no manual steps.

Run with: .venv\\Scripts\\python.exe -m trader.backtest.run_momentum_placeholder
"""

from __future__ import annotations

import sys
from pathlib import Path

from trader.backtest import config, ledger, momentum_placeholder
from trader.backtest.metrics import compute_metrics, write_report
from trader.backtest.runner import run_backtest
from trader.data import db as data_db
from trader.data.api import get_daily_bars

_SYMBOL = "AAPL"
_STRATEGY_ID = "momentum_placeholder"
# Fixed seed (D-12 reproducibility) -- pinned, not re-rolled per run. The
# momentum placeholder's pick_entries never actually consumes rng, but
# run_backtest's contract requires one regardless.
_SEED = 20260726


def main(conn=None) -> tuple[int, dict, Path]:
    """Run the momentum placeholder over AAPL's full cached history and
    return (run_id, metrics, report_path).

    conn=None (the default) opens a connection to the real, shared
    data/trader.db -- the same cache-hit-only, offline pattern
    tests/test_backtest_sanity.py already uses -- and closes it before
    returning. A caller-supplied conn (e.g. a test's own connection) is
    reused as-is and left open for the caller to close.
    """
    owns_conn = conn is None
    if conn is None:
        conn = data_db.get_connection()

    try:
        bars = get_daily_bars(_SYMBOL, asset_class="stock", conn=conn)
        bars_by_symbol = {_SYMBOL: bars}

        run_id = run_backtest(
            strategy_fn=momentum_placeholder.pick_entries,
            universe=[_SYMBOL],
            profile=config.PROFILE_MOMENTUM_PLACEHOLDER,
            bars_by_symbol=bars_by_symbol,
            seed=_SEED,
            params={"profile_name": "PROFILE_MOMENTUM_PLACEHOLDER"},
            strategy_id=_STRATEGY_ID,
            conn=conn,
        )

        trades = ledger.get_trades_for_run(conn, run_id)
        metrics = compute_metrics(trades)
        report_path = write_report(run_id, metrics, _STRATEGY_ID)

        return run_id, metrics, report_path
    finally:
        if owns_conn:
            conn.close()


if __name__ == "__main__":
    run_id, metrics, report_path = main()
    print(f"run_id: {run_id}")
    print(f"trade_count: {metrics['trade_count']}")
    print(f"profit_factor: {metrics['profit_factor']}")
    print(f"sharpe_ratio: {metrics['sharpe_ratio']}")
    print(f"report: {report_path}")
    sys.exit(0)
