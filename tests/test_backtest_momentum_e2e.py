"""End-to-end proof of the full backtest pipe (D-15, BACK-06, phase success
criterion 2): the momentum placeholder strategy, run over AAPL's real
cached history, offline, must produce a real ledger, real finite metrics,
and a real, readable markdown report on disk.

This is 02-VALIDATION.md's one Manual-Only Verification item, now
automated -- no strategy-development ambition here (Phase 3's job), only
proof that BACK-01 through BACK-06 wire together correctly end to end.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from trader.backtest import ledger
from trader.backtest.metrics import METRIC_KEYS
from trader.data import db as data_db

try:
    from trader.backtest import run_momentum_placeholder
except ImportError:
    # trader.backtest.run_momentum_placeholder does not exist yet (RED
    # phase) -- collection must still succeed; the test below fails on the
    # AttributeError when it tries to call main() on None.
    run_momentum_placeholder = None


def test_main_runs_full_pipe_and_produces_a_real_report():
    if run_momentum_placeholder is None:
        pytest.fail(
            "trader.backtest.run_momentum_placeholder does not exist yet"
        )

    run_id, metrics, report_path = run_momentum_placeholder.main(conn=None)

    assert isinstance(run_id, int)

    # T-02-21: a no-trade run silently "passing" proves nothing -- AAPL's
    # 45-year cached history with a 20-day momentum lookback must produce
    # at least a handful of signals.
    assert metrics["trade_count"] >= 1

    # T-02-22: every BACK-06 metrics key must be present and, where not
    # None, finite -- profit_factor may legitimately be math.inf only with
    # zero losing trades, checked explicitly below rather than
    # blanket-rejecting inf.
    for key in METRIC_KEYS:
        assert key in metrics
        value = metrics[key]
        if value is None:
            continue
        if key == "profit_factor" and value == math.inf:
            conn = data_db.get_connection()
            try:
                trades = ledger.get_trades_for_run(conn, run_id)
            finally:
                conn.close()
            losing_trades = [t for t in trades if t["pnl"] < 0]
            assert not losing_trades, (
                "profit_factor is math.inf but losing trades exist -- "
                "that combination should be impossible"
            )
            continue
        assert math.isfinite(value), f"{key} is not finite: {value!r}"

    assert isinstance(report_path, Path)
    assert report_path.exists()
    contents = report_path.read_text(encoding="utf-8")
    assert "momentum_placeholder" in contents
    assert "trade_count" in contents
