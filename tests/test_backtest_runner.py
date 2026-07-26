"""Integration tests for trader.backtest.runner.run_backtest -- the single
orchestration loop wiring the point-in-time iterator (plan 02-02), fills
(02-04), exits (02-05), and ledger (02-06) together (BACK-01, BACK-04,
BACK-05).

Every module's own unit tests already prove its isolated behaviour; these
tests prove the WIRING does not silently reintroduce a mistake at the
integration layer -- the exact failure mode each of T-02-16, T-02-17, and
T-02-18 describes in 02-08-PLAN.md's threat model.
"""

import json

import pandas as pd
import pytest

from trader.backtest import config, fills, ledger
from trader.data import db as data_db

try:
    from trader.backtest import runner
except ImportError:
    # trader.backtest.runner does not exist yet (RED phase) -- collection
    # must still succeed so all tests are collected; each test then fails
    # with an AttributeError on `runner` (None) when it tries to call
    # run_backtest. Matches the sibling backtest test files' RED-phase-safe
    # import pattern.
    runner = None


@pytest.fixture
def data_conn(tmp_db_path):
    """A live connection to a fresh temp DB, bootstrapped via trader.data.db
    (mirrors tests/test_backtest_ledger.py's data_conn fixture)."""
    connection = data_db.get_connection(tmp_db_path)
    yield connection
    connection.close()


def _make_bars(dates, opens, highs, lows, closes, volumes=None):
    index = pd.to_datetime(dates, utc=True)
    n = len(dates)
    if volumes is None:
        volumes = [1000.0] * n
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=index,
    )


def _signal_once_strategy(signal_date: str, symbol: str):
    """A deterministic stub strategy_fn: signals `symbol` exactly once, on
    the calendar date matching `signal_date`, and never again."""

    def pick_entries(iterator, date, open_positions, rng):
        if date.strftime("%Y-%m-%d") == signal_date and symbol not in open_positions:
            return [symbol]
        return []

    return pick_entries


def _fixed_schedule_strategy(schedule: dict[str, list[str]]):
    """A deterministic stub strategy_fn driven by a fixed date -> symbols
    schedule, skipping any symbol already open or pending."""

    def pick_entries(iterator, date, open_positions, rng):
        symbols = schedule.get(date.strftime("%Y-%m-%d"), [])
        return [s for s in symbols if s not in open_positions]

    return pick_entries


# --- Signal-then-fill-lag test (T-02-16, D-04) ---------------------------


def test_entry_lags_signal_by_exactly_one_bar_never_the_signal_bars_close(data_conn):
    dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
    bars = {
        "AAA": _make_bars(
            dates,
            opens=[100.0, 110.0, 120.0, 130.0],
            highs=[105.0, 115.0, 125.0, 135.0],
            lows=[95.0, 105.0, 115.0, 125.0],
            closes=[103.0, 113.0, 125.0, 133.0],
        )
    }
    strategy_fn = _signal_once_strategy("2026-01-05", "AAA")

    run_id = runner.run_backtest(
        strategy_fn=strategy_fn,
        universe=["AAA"],
        profile=config.PROFILE_TIME_STOP_1D,
        bars_by_symbol=bars,
        seed=1,
        params={"profile_name": "PROFILE_TIME_STOP_1D"},
        strategy_id="test_lag_strategy",
        conn=data_conn,
    )

    trades = ledger.get_trades_for_run(data_conn, run_id)
    assert len(trades) == 1
    trade = trades[0]

    expected_entry_price = fills.entry_fill_price(110.0, "stock", "buy")
    assert trade["entry_ts"] == "2026-01-06"  # never the signal bar (01-05) itself
    assert trade["entry_price"] == pytest.approx(expected_entry_price)
    assert trade["exit_ts"] == "2026-01-07"
    assert trade["exit_reason"] == "time_stop"


# --- Entry-bar exit test (T-02-17, Pitfall 2) -----------------------------


def test_entry_bar_check_fires_stop_on_the_same_bar_as_the_fill(data_conn):
    dates = ["2026-01-05", "2026-01-06", "2026-01-07"]
    bars = {
        "BBB": _make_bars(
            dates,
            opens=[100.0, 100.0, 100.0],
            highs=[105.0, 105.0, 105.0],
            lows=[95.0, 85.0, 95.0],  # day2 (fill bar)'s own low breaches the stop
            closes=[103.0, 90.0, 103.0],
        )
    }
    strategy_fn = _signal_once_strategy("2026-01-05", "BBB")

    run_id = runner.run_backtest(
        strategy_fn=strategy_fn,
        universe=["BBB"],
        profile=config.PROFILE_MOMENTUM_PLACEHOLDER,
        bars_by_symbol=bars,
        seed=2,
        params={"profile_name": "PROFILE_MOMENTUM_PLACEHOLDER"},
        strategy_id="test_entry_bar_strategy",
        conn=data_conn,
    )

    trades = ledger.get_trades_for_run(data_conn, run_id)
    assert len(trades) == 1
    trade = trades[0]

    entry_price = fills.entry_fill_price(100.0, "stock", "buy")
    stop_price = entry_price * (1 + config.PROFILE_MOMENTUM_PLACEHOLDER.stop_pct)
    raw_price = fills.worse_of_fill(stop_price, 100.0, side="sell")
    expected_exit_price = fills.apply_slippage(raw_price, "sell", "stock")

    assert trade["entry_ts"] == "2026-01-06"
    assert trade["exit_ts"] == "2026-01-06"  # the SAME bar as entry, not a later one
    assert trade["exit_reason"] == "stop"
    assert trade["entry_price"] == pytest.approx(entry_price)
    assert trade["exit_price"] == pytest.approx(expected_exit_price)


# --- Full pipe test --------------------------------------------------------


def _two_symbol_fixture():
    dates = [f"2026-02-{day:02d}" for day in range(1, 13)]  # 12 days
    n = len(dates)
    bars = {
        "EEE": _make_bars(
            dates,
            opens=[100.0 + i for i in range(n)],
            highs=[105.0 + i for i in range(n)],
            lows=[95.0 + i for i in range(n)],
            closes=[102.0 + i for i in range(n)],
        ),
        "FFF": _make_bars(
            dates,
            opens=[50.0 + i for i in range(n)],
            highs=[55.0 + i for i in range(n)],
            lows=[45.0 + i for i in range(n)],
            closes=[52.0 + i for i in range(n)],
        ),
    }
    schedule = {"2026-02-02": ["EEE"], "2026-02-06": ["FFF"]}
    return bars, schedule


def test_full_pipe_produces_internally_consistent_ledger_rows(data_conn):
    bars, schedule = _two_symbol_fixture()
    strategy_fn = _fixed_schedule_strategy(schedule)

    run_id = runner.run_backtest(
        strategy_fn=strategy_fn,
        universe=["EEE", "FFF"],
        profile=config.PROFILE_TIME_STOP_1D,
        bars_by_symbol=bars,
        seed=3,
        params={"profile_name": "PROFILE_TIME_STOP_1D"},
        strategy_id="test_full_pipe_strategy",
        conn=data_conn,
    )

    trades = ledger.get_trades_for_run(data_conn, run_id)
    assert len(trades) >= 1

    for trade in trades:
        assert trade["entry_ts"] is not None
        assert trade["entry_price"] is not None
        assert trade["exit_ts"] is not None
        assert trade["exit_price"] is not None
        assert trade["qty"] > 0
        assert trade["fees"] >= 0
        assert trade["slippage"] >= 0
        assert trade["exit_reason"] is not None

        expected_pnl = (
            trade["exit_price"] - trade["entry_price"]
        ) * trade["qty"] - trade["fees"]
        assert trade["pnl"] == pytest.approx(expected_pnl)


# --- Reproducibility test (T-02-18, D-12) ---------------------------------


def test_run_backtest_is_reproducible_across_separate_fresh_dbs(tmp_path):
    bars, schedule = _two_symbol_fixture()

    def run_once(db_path):
        conn = data_db.get_connection(str(db_path))
        strategy_fn = _fixed_schedule_strategy(schedule)
        run_id = runner.run_backtest(
            strategy_fn=strategy_fn,
            universe=["EEE", "FFF"],
            profile=config.PROFILE_TIME_STOP_1D,
            bars_by_symbol=bars,
            seed=42,
            params={"profile_name": "PROFILE_TIME_STOP_1D"},
            strategy_id="test_reproducibility_strategy",
            conn=conn,
        )
        trades = ledger.get_trades_for_run(conn, run_id)
        conn.close()
        return trades

    trades_a = run_once(tmp_path / "db_a.sqlite")
    trades_b = run_once(tmp_path / "db_b.sqlite")

    ignore_keys = {"run_id", "trade_id"}

    def normalize(trades):
        return sorted(
            tuple(sorted((k, v) for k, v in t.items() if k not in ignore_keys))
            for t in trades
        )

    assert len(trades_a) >= 1
    assert normalize(trades_a) == normalize(trades_b)


# --- run_id / params_json test ---------------------------------------------


def test_run_backtest_returns_run_id_and_persists_matching_params(data_conn):
    bars, schedule = _two_symbol_fixture()
    strategy_fn = _fixed_schedule_strategy(schedule)
    params = {"profile_name": "PROFILE_TIME_STOP_1D", "lookback": 20}

    run_id = runner.run_backtest(
        strategy_fn=strategy_fn,
        universe=["EEE", "FFF"],
        profile=config.PROFILE_TIME_STOP_1D,
        bars_by_symbol=bars,
        seed=5,
        params=params,
        strategy_id="test_params_strategy",
        conn=data_conn,
    )

    assert isinstance(run_id, int)

    row = data_conn.execute(
        "SELECT params_json FROM backtest_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    assert row is not None
    assert json.loads(row[0]) == params
