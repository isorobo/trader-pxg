"""Tests for trader.backtest.metrics — profit factor, Sharpe, max drawdown,
win rate, avg win/loss, trade count, total fees paid, and the markdown
report writer (BACK-06, D-13).

Golden fixtures are hand-worked in 02-03-PLAN.md and reproduced here as
literal Python data (not loaded from any external file), so the arithmetic
can be checked by hand against the numbers pinned below.
"""

import math

import pytest

try:
    from trader.backtest import metrics
except ImportError:
    # trader.backtest.metrics does not exist yet (RED phase) — collection
    # must still succeed so all tests are collected; each test then fails
    # with an AttributeError on `metrics` (None) when it tries to call into
    # the contract. Matches tests/test_data_api.py's RED-phase-safe pattern.
    metrics = None


# ---------------------------------------------------------------------------
# Golden fixture A: profit factor, win rate, avg win/loss, max drawdown, fees
# ---------------------------------------------------------------------------

FIXTURE_A_TRADES = [
    {"pnl": 100, "fees": 5, "exit_ts": "2026-01-01"},
    {"pnl": -50, "fees": 5, "exit_ts": "2026-01-02"},
    {"pnl": 200, "fees": 5, "exit_ts": "2026-01-03"},
    {"pnl": -30, "fees": 5, "exit_ts": "2026-01-04"},
    {"pnl": -20, "fees": 5, "exit_ts": "2026-01-05"},
]
FIXTURE_A_STARTING_EQUITY = 1000.0


def test_golden_fixture_a_profit_factor():
    result = metrics.compute_metrics(FIXTURE_A_TRADES, starting_equity=FIXTURE_A_STARTING_EQUITY)
    assert result["profit_factor"] == pytest.approx(3.0)


def test_golden_fixture_a_win_rate():
    result = metrics.compute_metrics(FIXTURE_A_TRADES, starting_equity=FIXTURE_A_STARTING_EQUITY)
    assert result["win_rate"] == pytest.approx(0.4)


def test_golden_fixture_a_avg_win():
    result = metrics.compute_metrics(FIXTURE_A_TRADES, starting_equity=FIXTURE_A_STARTING_EQUITY)
    assert result["avg_win"] == pytest.approx(150.0)


def test_golden_fixture_a_avg_loss():
    result = metrics.compute_metrics(FIXTURE_A_TRADES, starting_equity=FIXTURE_A_STARTING_EQUITY)
    assert result["avg_loss"] == pytest.approx(-33.3333, rel=1e-3)


def test_golden_fixture_a_trade_count():
    result = metrics.compute_metrics(FIXTURE_A_TRADES, starting_equity=FIXTURE_A_STARTING_EQUITY)
    assert result["trade_count"] == 5


def test_golden_fixture_a_total_fees_paid():
    result = metrics.compute_metrics(FIXTURE_A_TRADES, starting_equity=FIXTURE_A_STARTING_EQUITY)
    assert result["total_fees_paid"] == pytest.approx(25.0)


def test_golden_fixture_a_max_drawdown():
    # Daily equity curve (sum pnl per exit_ts date, cumulate from starting
    # equity): [1000, 1100, 1050, 1250, 1220, 1200]. The -1100->1050 drawdown
    # (-0.045455) is larger in magnitude than the later -1250->1200 drawdown
    # (-0.04).
    result = metrics.compute_metrics(FIXTURE_A_TRADES, starting_equity=FIXTURE_A_STARTING_EQUITY)
    assert result["max_drawdown"] == pytest.approx(-50 / 1100, rel=1e-3)


def test_compute_metrics_returns_exact_key_set():
    result = metrics.compute_metrics(FIXTURE_A_TRADES, starting_equity=FIXTURE_A_STARTING_EQUITY)
    assert set(result.keys()) == {
        "profit_factor",
        "sharpe_ratio",
        "max_drawdown",
        "win_rate",
        "avg_win",
        "avg_loss",
        "trade_count",
        "total_fees_paid",
    }


# ---------------------------------------------------------------------------
# Golden fixture B: Sharpe ratio, kept independent for clean hand arithmetic
# ---------------------------------------------------------------------------

FIXTURE_B_DAILY_RETURNS = [0.02, -0.01, 0.03, 0.00, -0.02]


def test_golden_fixture_b_sharpe_ratio():
    # mean = 0.004, sample stdev (ddof=1) ~= 0.020736
    # sharpe = (mean / stdev) * sqrt(252) ~= 3.06
    result = metrics.sharpe_ratio(FIXTURE_B_DAILY_RETURNS)
    assert result == pytest.approx(3.06, abs=0.05)


# ---------------------------------------------------------------------------
# Edge cases (Pitfall 4): zero losses, <2 trades/observations, zero trades
# ---------------------------------------------------------------------------

def test_profit_factor_zero_losses_returns_inf():
    assert metrics.profit_factor([100.0, 200.0]) == math.inf


def test_profit_factor_zero_trades_returns_none():
    assert metrics.profit_factor([]) is None


def test_sharpe_ratio_fewer_than_two_observations_returns_none():
    assert metrics.sharpe_ratio([0.01]) is None
    assert metrics.sharpe_ratio([]) is None


def test_compute_metrics_zero_trades_never_raises():
    result = metrics.compute_metrics([])
    assert result["trade_count"] == 0
    for key in (
        "profit_factor",
        "sharpe_ratio",
        "max_drawdown",
        "win_rate",
        "avg_win",
        "avg_loss",
    ):
        assert result[key] is None
    # total_fees_paid with zero trades is defined as 0.0, not None — there
    # are simply no fees to sum.
    assert result["total_fees_paid"] in (0, 0.0)


def test_compute_metrics_single_trade_does_not_crash():
    # <2 trades: Sharpe must be None (fewer than 2 daily return observations)
    # rather than raising.
    single = [{"pnl": 50, "fees": 2, "exit_ts": "2026-02-01"}]
    result = metrics.compute_metrics(single, starting_equity=1000.0)
    assert result["sharpe_ratio"] is None
    assert result["trade_count"] == 1


# ---------------------------------------------------------------------------
# write_report
# ---------------------------------------------------------------------------

def test_write_report_creates_file_with_heading_and_metrics(tmp_path):
    sample_metrics = metrics.compute_metrics(
        FIXTURE_A_TRADES, starting_equity=FIXTURE_A_STARTING_EQUITY
    )
    result_path = metrics.write_report(
        run_id=42, metrics=sample_metrics, strategy_id="momentum_placeholder", base_dir=str(tmp_path)
    )
    assert result_path.exists()
    content = result_path.read_text(encoding="utf-8")
    assert "# Backtest Report" in content
    for key in sample_metrics:
        assert key in content


def test_write_report_returns_path_under_base_dir(tmp_path):
    sample_metrics = metrics.compute_metrics(
        FIXTURE_A_TRADES, starting_equity=FIXTURE_A_STARTING_EQUITY
    )
    result_path = metrics.write_report(
        run_id=7, metrics=sample_metrics, strategy_id="random_strategy", base_dir=str(tmp_path)
    )
    assert result_path.parent == tmp_path
    assert "random_strategy" in result_path.name
    assert "run7" in result_path.name


def test_write_report_creates_base_dir_if_missing(tmp_path):
    nested = tmp_path / "nested" / "reports"
    sample_metrics = metrics.compute_metrics(
        FIXTURE_A_TRADES, starting_equity=FIXTURE_A_STARTING_EQUITY
    )
    result_path = metrics.write_report(
        run_id=1, metrics=sample_metrics, strategy_id="s", base_dir=str(nested)
    )
    assert result_path.exists()
    assert nested.exists()
