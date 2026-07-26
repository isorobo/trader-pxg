"""Tests for trader.risk.breakers -- RISK-03's circuit breakers (D-04/D-05,
04-RESEARCH.md Q4).

Covers the pure, incremental evaluate_breakers function (daily-loss,
drawdown+HWM, consecutive-loss trip conditions; the no-lookahead HWM
regression; a simulation against a REAL Phase 2 harness equity curve built
via trader.backtest.metrics._build_daily_equity_curve). Persistence and the
human-only manual-restart clear path are covered further down this file
(added alongside trader/risk/clear_breaker.py).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from trader.backtest.metrics import _build_daily_equity_curve
from trader.risk import config

REPO_ROOT = Path(__file__).resolve().parents[1]
BREAKERS_SOURCE_PATH = REPO_ROOT / "trader" / "risk" / "breakers.py"


# ---------------------------------------------------------------------------
# evaluate_breakers -- daily_loss
# ---------------------------------------------------------------------------


def test_daily_loss_trips_at_exact_threshold():
    from trader.risk import breakers

    equity_curve = [100_000.0, 97_000.0]  # exactly -3.0%
    result = breakers.evaluate_breakers(equity_curve, [], config)
    assert result["daily_loss_tripped"] is True
    assert result["daily_loss_value"] == pytest.approx(-0.03)


def test_daily_loss_does_not_trip_on_smaller_loss():
    from trader.risk import breakers

    equity_curve = [100_000.0, 98_000.0]  # -2.0%, smaller than threshold
    result = breakers.evaluate_breakers(equity_curve, [], config)
    assert result["daily_loss_tripped"] is False
    assert result["daily_loss_value"] == pytest.approx(-0.02)


def test_daily_loss_value_is_none_with_fewer_than_two_points():
    from trader.risk import breakers

    result = breakers.evaluate_breakers([100_000.0], [], config)
    assert result["daily_loss_tripped"] is False
    assert result["daily_loss_value"] is None


# ---------------------------------------------------------------------------
# evaluate_breakers -- drawdown (incremental HWM)
# ---------------------------------------------------------------------------


def test_drawdown_trips_at_exact_threshold():
    from trader.risk import breakers

    equity_curve = [100_000.0, 110_000.0, 99_000.0]  # HWM 110000, dd = -10%
    result = breakers.evaluate_breakers(equity_curve, [], config)
    assert result["drawdown_tripped"] is True
    assert result["drawdown_value"] == pytest.approx(-0.10)


def test_drawdown_does_not_trip_on_smaller_decline():
    from trader.risk import breakers

    equity_curve = [100_000.0, 110_000.0, 100_000.0]  # dd ~ -9.09%
    result = breakers.evaluate_breakers(equity_curve, [], config)
    assert result["drawdown_tripped"] is False


def test_drawdown_no_lookahead_regression():
    """A curve that dips below the drawdown threshold at index 2 then
    recovers above the prior peak by the final index -- calling
    evaluate_breakers with the curve truncated to [:3] must still report
    drawdown_tripped=True, proving the breaker cannot "see" the future
    recovery (04-RESEARCH.md Pitfall 2). This test would fail if
    evaluate_breakers ever regressed to a retrospective full-curve pattern.
    """
    from trader.risk import breakers

    full_curve = [100_000.0, 110_000.0, 98_000.0, 130_000.0]
    truncated = full_curve[:3]  # up to and including the dip

    result_truncated = breakers.evaluate_breakers(truncated, [], config)
    assert result_truncated["drawdown_tripped"] is True

    result_full = breakers.evaluate_breakers(full_curve, [], config)
    assert result_full["drawdown_tripped"] is False  # final point recovered


# ---------------------------------------------------------------------------
# evaluate_breakers -- consecutive_loss
# ---------------------------------------------------------------------------


def test_consecutive_loss_trips_at_exact_threshold():
    from trader.risk import breakers

    trade_pnls = [100.0, -10.0, -20.0, -30.0, -40.0, -50.0, -60.0]  # 6 trailing losses
    result = breakers.evaluate_breakers([100_000.0], trade_pnls, config)
    assert result["consecutive_loss_tripped"] is True
    assert result["consecutive_loss_count"] == 6


def test_consecutive_loss_does_not_trip_below_threshold():
    from trader.risk import breakers

    trade_pnls = [-10.0, -20.0, -30.0, -40.0, -50.0]  # 5 trailing losses
    result = breakers.evaluate_breakers([100_000.0], trade_pnls, config)
    assert result["consecutive_loss_tripped"] is False
    assert result["consecutive_loss_count"] == 5


def test_consecutive_loss_resets_after_a_win():
    from trader.risk import breakers

    trade_pnls = [-10.0, -20.0, -30.0, -40.0, -50.0, -60.0, 5.0, -10.0]
    result = breakers.evaluate_breakers([100_000.0], trade_pnls, config)
    assert result["consecutive_loss_tripped"] is False
    assert result["consecutive_loss_count"] == 1


def test_consecutive_loss_count_zero_when_no_trades():
    from trader.risk import breakers

    result = breakers.evaluate_breakers([100_000.0], [], config)
    assert result["consecutive_loss_count"] == 0
    assert result["consecutive_loss_tripped"] is False


# ---------------------------------------------------------------------------
# Simulation against a REAL Phase 2 harness equity curve
# ---------------------------------------------------------------------------


def test_harness_simulation_steps_trip_each_breaker_on_correct_day():
    """Synthetic trades (exit_ts + pnl) fed through the REAL Phase 2 harness
    curve builder, then evaluate_breakers is called once per day,
    chronologically, on the curve truncated to "as of that day" -- proving
    each breaker trips on the exact day its condition is first met and not
    before (04-RESEARCH.md Pitfall 2's stepping discipline)."""
    from trader.risk import breakers

    starting_equity = 100_000.0
    trades = [
        {"exit_ts": "2026-01-01", "pnl": 1_000.0},
        {"exit_ts": "2026-01-02", "pnl": -500.0},
        {"exit_ts": "2026-01-03", "pnl": -4_000.0},
        {"exit_ts": "2026-01-04", "pnl": 200.0},
        {"exit_ts": "2026-01-05", "pnl": -6_500.0},
        {"exit_ts": "2026-01-06", "pnl": 15_000.0},
    ]
    equity_curve = _build_daily_equity_curve(trades, starting_equity)
    trade_pnls = [trade["pnl"] for trade in trades]

    daily_loss_trip_days = set()
    drawdown_trip_days = set()
    for i in range(1, len(equity_curve)):
        result = breakers.evaluate_breakers(
            equity_curve[: i + 1], trade_pnls[:i], config
        )
        if result["daily_loss_tripped"]:
            daily_loss_trip_days.add(i)
        if result["drawdown_tripped"]:
            drawdown_trip_days.add(i)

    assert daily_loss_trip_days == {3, 5}
    assert drawdown_trip_days == {5}


# ---------------------------------------------------------------------------
# evaluate_breakers -- purity (zero DB/file I/O)
# ---------------------------------------------------------------------------


def test_breakers_module_never_imports_sqlite_or_db():
    """breakers.py may mention trader.data.db in prose (docstrings), but
    must never actually import sqlite3 or trader.data.db -- evaluate_breakers
    performs zero DB/file I/O."""
    source = BREAKERS_SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "sqlite3"
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module != "sqlite3"
            assert not module.startswith("trader.data")
