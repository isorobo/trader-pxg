"""Tests for trader.paper.guardian -- the 5-minute-cadence exit-monitoring
process (05-05-PLAN.md).

Uses the paper_conn fixture (tests/conftest.py, every migration applied) and
the fake_ib fixture (a MagicMock standing in for ib_async.IB). guardian.alerts
.notify is replaced with a no-op MagicMock by default in every test (see
`_mock_alerts_notify`) so this suite never writes into the real repo's ops/
directory as a side effect of alerts.notify's hard-coded default log path.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from trader.backtest.config import EXIT_PROFILE
from trader.paper import config as paper_config
from trader.paper import guardian, ledger
from trader.paper.broker_ibkr import IBKRBrokerAdapter

TRADING_DAY = datetime(2026, 7, 27, 15, 0, tzinfo=timezone.utc)  # a real NYSE Monday
TRADING_DAY_2 = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)

# Phase 7 identity fix: kill conditions key on profile_name (the identity
# paper_trades rows actually carry), never the shared family strategy_id.
_KILL_PROFILE = paper_config.LIVE_STRATEGY_CONFIGS[0].profile_name


# ---------------------------------------------------------------------------
# Fixtures / test doubles
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_alerts_notify(monkeypatch):
    """guardian.alerts.notify is replaced with a no-op MagicMock by default
    in every test -- alerts.notify's real fallback path hard-codes
    "ops/paper_trading.log" (relative to cwd), and this suite must never
    write into the real repo's ops/ directory as a side effect. Individual
    tests that need to assert on notify's call args/count re-monkeypatch
    this same attribute within their own test body -- pytest's monkeypatch
    fixture layers correctly on top of this autouse default."""
    monkeypatch.setattr(guardian.alerts, "notify", MagicMock(return_value=True))


class _FakeTicker:
    def __init__(self, market_price):
        self._market_price = market_price

    def marketPrice(self):
        return self._market_price


class _FakeCcxtClient:
    def __init__(self, last_price: float):
        self._last_price = last_price

    def fetch_ticker(self, symbol):
        return {"last": self._last_price}


class _FakeExecution:
    """Mirrors tests/test_broker_ibkr.py's _FakeExecution -- IBKRBrokerAdapter
    .snapshot() reads f.execution.orderRef/.permId/.shares, never a plain dict."""

    def __init__(self, order_ref: str, perm_id: int, shares: float):
        self.orderRef = order_ref
        self.permId = perm_id
        self.shares = shares


class _FakeContract:
    def __init__(self, symbol: str):
        self.symbol = symbol


class _FakeFill:
    def __init__(self, execution: _FakeExecution, contract: _FakeContract):
        self.execution = execution
        self.contract = contract


def _make_fake_fill(order_ref: str, perm_id: int, symbol: str, qty: float) -> _FakeFill:
    return _FakeFill(_FakeExecution(order_ref, perm_id, qty), _FakeContract(symbol))


def _ibkr_adapter(fake_ib, price: float | None = None) -> IBKRBrokerAdapter:
    if price is not None:
        fake_ib.reqMktData.return_value = _FakeTicker(price)
    return IBKRBrokerAdapter(host="127.0.0.1", port=4002, client_id=5, ib_client=fake_ib)


def _open_position(
    conn,
    strategy_id="momentum_stock",
    symbol="AAPL",
    venue="ibkr_paper",
    asset_class="stock",
    entry_price=100.0,
    qty=10.0,
    entry_ts="2026-07-20T09:30:00",
    stop_pct=-0.10,
    tp_pct=None,
    scale_out=(),
    trailing_pct=None,
    max_hold_days=None,
    eod_flat=False,
) -> int:
    profile = EXIT_PROFILE(
        stop_pct=stop_pct,
        tp_pct=tp_pct,
        scale_out=scale_out,
        trailing_pct=trailing_pct,
        max_hold_days=max_hold_days,
        eod_flat=eod_flat,
    )
    return ledger.open_position(
        conn,
        strategy_id=strategy_id,
        symbol=symbol,
        venue=venue,
        asset_class=asset_class,
        qty=qty,
        entry_price=entry_price,
        entry_ts=entry_ts,
        entry_order_ref=f"{strategy_id}:{symbol}:2026-07-20:buy:entry",
        exit_profile=profile,
    )


def _fetch_trades(conn) -> list[dict]:
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    rows = cursor.execute("SELECT * FROM paper_trades").fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Task 1 -- exit evaluation (D-10 order, single-price bar collapse)
# ---------------------------------------------------------------------------


def test_stop_exit_fires_on_first_tick(paper_conn, fake_ib):
    _open_position(paper_conn, stop_pct=-0.10, entry_price=100.0)
    fake_ib.placeOrder.return_value.order.permId = 111
    adapter = _ibkr_adapter(fake_ib, price=89.0)

    result = guardian.run_guardian_once(paper_conn, adapter, now=TRADING_DAY)

    assert len(result["exits"]) == 1
    assert result["exits"][0]["reason"] == "stop"
    trades = _fetch_trades(paper_conn)
    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "stop"
    assert ledger.get_open_positions(paper_conn) == []


def test_take_profit_exit_fires(paper_conn, fake_ib):
    _open_position(paper_conn, tp_pct=0.20, entry_price=100.0, stop_pct=None)
    fake_ib.placeOrder.return_value.order.permId = 222
    adapter = _ibkr_adapter(fake_ib, price=125.0)

    result = guardian.run_guardian_once(paper_conn, adapter, now=TRADING_DAY)

    assert len(result["exits"]) == 1
    assert result["exits"][0]["reason"] == "take_profit"
    trades = _fetch_trades(paper_conn)
    assert trades[0]["exit_reason"] == "take_profit"


def test_time_stop_exit_fires_even_when_price_flat(paper_conn, fake_ib):
    _open_position(
        paper_conn,
        stop_pct=None,
        tp_pct=None,
        max_hold_days=30,
        entry_price=100.0,
        entry_ts="2026-06-27T09:30:00",  # 30 days before TRADING_DAY
    )
    fake_ib.placeOrder.return_value.order.permId = 333
    adapter = _ibkr_adapter(fake_ib, price=100.0)  # flat

    result = guardian.run_guardian_once(paper_conn, adapter, now=TRADING_DAY)

    assert len(result["exits"]) == 1
    assert result["exits"][0]["reason"] == "time_stop"


def test_no_condition_met_advances_watermark_and_creates_no_trade(paper_conn, fake_ib):
    position_id = _open_position(paper_conn, stop_pct=-0.50, tp_pct=0.50, entry_price=100.0)
    adapter = _ibkr_adapter(fake_ib, price=101.0)

    result = guardian.run_guardian_once(paper_conn, adapter, now=TRADING_DAY)

    assert result["exits"] == []
    assert _fetch_trades(paper_conn) == []
    positions = ledger.get_open_positions(paper_conn)
    assert len(positions) == 1
    assert positions[0]["position_id"] == position_id
    assert positions[0]["watermark"] == 101.0
    fake_ib.placeOrder.assert_not_called()


# ---------------------------------------------------------------------------
# Task 1 -- persist-before-submit + idempotency
# ---------------------------------------------------------------------------


def test_exit_order_persisted_before_broker_call(paper_conn, fake_ib):
    _open_position(paper_conn, stop_pct=-0.10, entry_price=100.0)
    fake_ib.placeOrder.side_effect = RuntimeError("broker unreachable")
    adapter = _ibkr_adapter(fake_ib, price=89.0)

    with pytest.raises(RuntimeError):
        guardian.run_guardian_once(paper_conn, adapter, now=TRADING_DAY)

    rows = paper_conn.execute("SELECT status FROM paper_orders").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "pending_submit"
    assert _fetch_trades(paper_conn) == []


def test_second_run_never_creates_a_second_trade_row(paper_conn, fake_ib):
    _open_position(paper_conn, stop_pct=-0.10, entry_price=100.0)
    fake_ib.placeOrder.return_value.order.permId = 444
    adapter = _ibkr_adapter(fake_ib, price=89.0)

    guardian.run_guardian_once(paper_conn, adapter, now=TRADING_DAY)
    guardian.run_guardian_once(paper_conn, adapter, now=TRADING_DAY_2)

    assert len(_fetch_trades(paper_conn)) == 1
    assert fake_ib.placeOrder.call_count == 1


# ---------------------------------------------------------------------------
# Task 1 -- crash-orphaned exit heal (BLOCKER 1, date-independent)
# ---------------------------------------------------------------------------


def test_crash_orphaned_exit_is_healed_without_resubmitting(paper_conn, fake_ib):
    _open_position(paper_conn, stop_pct=-0.10, entry_price=100.0, symbol="AAPL")
    stale_order_ref = "momentum_stock:AAPL:2026-07-26:sell:exit_stop"
    ledger.record_order(
        paper_conn,
        order_ref=stale_order_ref,
        strategy_id="momentum_stock",
        symbol="AAPL",
        venue="ibkr_paper",
        side="sell",
        intent="exit_stop",
        qty=10.0,
        status="pending_submit",
    )
    fake_ib.fills.return_value = [
        _make_fake_fill(order_ref=stale_order_ref, perm_id=999, symbol="AAPL", qty=10)
    ]
    adapter = _ibkr_adapter(fake_ib, price=89.0)  # still below stop -- condition re-fires

    result = guardian.run_guardian_once(paper_conn, adapter, now=TRADING_DAY)

    fake_ib.placeOrder.assert_not_called()
    healed_order = ledger.get_order_by_ref(paper_conn, stale_order_ref)
    assert healed_order["status"] == "filled"

    trades = _fetch_trades(paper_conn)
    assert len(trades) == 1
    assert trades[0]["exit_order_ref"] == stale_order_ref
    assert trades[0]["exit_reason"] == "stop"
    assert ledger.get_open_positions(paper_conn) == []
    assert result["exits"][0]["healed"] is True


# ---------------------------------------------------------------------------
# Task 1 -- crypto_sim leg
# ---------------------------------------------------------------------------


def test_crypto_leg_exit_uses_crypto_sim_never_touches_broker_ibkr(paper_conn, fake_ib):
    _open_position(
        paper_conn,
        symbol="BTC/USDT",
        venue="crypto_sim",
        asset_class="crypto_major",
        entry_price=65000.0,
        stop_pct=-0.10,
        qty=0.1,
    )
    adapter = _ibkr_adapter(fake_ib)  # only used for snapshot()["fills"]
    crypto_adapter = _FakeCcxtClient(last_price=58000.0)  # below -10% stop

    result = guardian.run_guardian_once(
        paper_conn, adapter, crypto_adapter=crypto_adapter, now=TRADING_DAY
    )

    assert len(result["exits"]) == 1
    assert result["exits"][0]["reason"] == "stop"
    fake_ib.placeOrder.assert_not_called()
    trades = _fetch_trades(paper_conn)
    assert trades[0]["venue"] == "crypto_sim"
    assert trades[0]["symbol"] == "BTC/USDT"


def test_ibkr_leg_skipped_on_non_trading_day_crypto_still_processed(paper_conn, fake_ib):
    _open_position(paper_conn, symbol="AAPL", venue="ibkr_paper", stop_pct=-0.10, entry_price=100.0)
    _open_position(
        paper_conn,
        symbol="BTC/USDT",
        venue="crypto_sim",
        asset_class="crypto_major",
        entry_price=65000.0,
        stop_pct=-0.10,
        qty=0.1,
    )
    adapter = _ibkr_adapter(fake_ib, price=89.0)
    crypto_adapter = _FakeCcxtClient(last_price=58000.0)
    weekend = datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc)  # a Saturday

    result = guardian.run_guardian_once(
        paper_conn, adapter, crypto_adapter=crypto_adapter, now=weekend
    )

    assert len(result["exits"]) == 1
    assert result["exits"][0]["symbol"] == "BTC/USDT"
    open_symbols = {p["symbol"] for p in ledger.get_open_positions(paper_conn)}
    assert open_symbols == {"AAPL"}


# ---------------------------------------------------------------------------
# Task 2 -- rolling kill-condition evaluation + auto-retire
# ---------------------------------------------------------------------------


def _insert_trade(conn, strategy_id: str, pnl: float, exit_ts: str, symbol: str = "AAPL") -> None:
    conn.execute(
        """
        INSERT INTO paper_trades
            (strategy_id, profile_name, symbol, venue, asset_class, entry_ts,
             entry_price, exit_ts, exit_price, exit_reason, qty, fees,
             slippage_cost, pnl, entry_order_ref, exit_order_ref)
        VALUES (?, ?, ?, 'ibkr_paper', 'stock', '2026-01-01T09:30:00', 100.0,
                ?, 100.0, 'stop', 10, 1.0, 0.5, ?, 'entry_ref', 'exit_ref')
        """,
        (strategy_id, strategy_id, symbol, exit_ts, pnl),
    )
    conn.commit()


def test_profit_factor_floor_retires_strategy(paper_conn):
    strategy_id = _KILL_PROFILE
    for i in range(15):
        _insert_trade(paper_conn, strategy_id, pnl=1.0, exit_ts=f"2026-01-{i + 1:02d}T09:30:00")
    for i in range(15):
        _insert_trade(paper_conn, strategy_id, pnl=-2.0, exit_ts=f"2026-02-{i + 1:02d}T09:30:00")

    retired = guardian.evaluate_kill_conditions(paper_conn)

    assert len(retired) == 1
    assert retired[0]["strategy_id"] == strategy_id
    assert retired[0]["reason"] == "profit_factor_floor"
    assert ledger.is_strategy_retired(paper_conn, strategy_id) is True


def test_max_drawdown_retires_strategy(paper_conn):
    strategy_id = _KILL_PROFILE
    for i in range(10):
        _insert_trade(paper_conn, strategy_id, pnl=100.0, exit_ts=f"2026-01-{i + 1:02d}T09:30:00")
    _insert_trade(paper_conn, strategy_id, pnl=-50.0, exit_ts="2026-01-11T09:30:00")
    for i in range(19):
        _insert_trade(paper_conn, strategy_id, pnl=50.0, exit_ts=f"2026-02-{i + 1:02d}T09:30:00")

    retired = guardian.evaluate_kill_conditions(paper_conn)

    assert len(retired) == 1
    assert retired[0]["reason"] == "max_drawdown"


def test_consecutive_losses_retires_strategy(paper_conn):
    strategy_id = _KILL_PROFILE
    for i in range(22):
        _insert_trade(paper_conn, strategy_id, pnl=100.0, exit_ts=f"2026-01-{i + 1:02d}T09:30:00")
    for i in range(8):
        _insert_trade(paper_conn, strategy_id, pnl=-1.0, exit_ts=f"2026-02-{i + 1:02d}T09:30:00")

    retired = guardian.evaluate_kill_conditions(paper_conn)

    assert len(retired) == 1
    assert retired[0]["reason"] == "consecutive_losses"
    assert retired[0]["trigger_value"] == 8


def test_fewer_than_thirty_trades_never_retires(paper_conn):
    strategy_id = _KILL_PROFILE
    for i in range(10):
        _insert_trade(paper_conn, strategy_id, pnl=-100.0, exit_ts=f"2026-01-{i + 1:02d}T09:30:00")

    retired = guardian.evaluate_kill_conditions(paper_conn)

    assert retired == []
    assert ledger.is_strategy_retired(paper_conn, strategy_id) is False


def test_already_retired_strategy_never_re_evaluated_no_duplicate_alert(paper_conn, monkeypatch):
    strategy_id = _KILL_PROFILE
    for i in range(15):
        _insert_trade(paper_conn, strategy_id, pnl=1.0, exit_ts=f"2026-01-{i + 1:02d}T09:30:00")
    for i in range(15):
        _insert_trade(paper_conn, strategy_id, pnl=-2.0, exit_ts=f"2026-02-{i + 1:02d}T09:30:00")

    mock_notify = MagicMock(wraps=guardian.alerts.notify)
    monkeypatch.setattr(guardian.alerts, "notify", mock_notify)

    first = guardian.evaluate_kill_conditions(paper_conn)
    second = guardian.evaluate_kill_conditions(paper_conn)

    assert len(first) == 1
    assert second == []
    assert mock_notify.call_count == 1


# ---------------------------------------------------------------------------
# Task 3 -- account-level breaker evaluation with real-time alert
# ---------------------------------------------------------------------------


def test_evaluate_account_breakers_builds_equity_curve_from_all_trades(paper_conn):
    _insert_trade(paper_conn, "s1", pnl=1000.0, exit_ts="2026-01-01T09:30:00")
    _insert_trade(paper_conn, "s2", pnl=-500.0, exit_ts="2026-01-02T09:30:00")

    evaluation = guardian.evaluate_account_breakers(paper_conn)

    assert evaluation["daily_loss_tripped"] is False
    from trader.risk import breakers

    state = breakers.read_breaker_state(paper_conn)
    assert state["daily_loss"]["current_action"] == "normal"


def test_fresh_breaker_trip_fires_real_time_alert_exactly_once(paper_conn, monkeypatch):
    mock_notify = MagicMock(wraps=guardian.alerts.notify)
    monkeypatch.setattr(guardian.alerts, "notify", mock_notify)

    # A single -5% trade trips ONLY daily_loss (threshold -3%), not
    # drawdown (threshold -10%) or consecutive_loss (threshold 6) --
    # isolating the "exactly one alert per transition" assertion to one
    # breaker type.
    _insert_trade(paper_conn, "s1", pnl=-5_000.0, exit_ts="2026-01-01T09:30:00")

    guardian.evaluate_account_breakers(paper_conn)
    error_calls = [c for c in mock_notify.call_args_list if c.args[0] == "error"]
    assert len(error_calls) == 1

    # A second call with the SAME (still-tripped) data must not re-fire.
    guardian.evaluate_account_breakers(paper_conn)
    error_calls = [c for c in mock_notify.call_args_list if c.args[0] == "error"]
    assert len(error_calls) == 1

    from trader.risk import breakers

    state = breakers.read_breaker_state(paper_conn)
    assert state["daily_loss"]["current_action"] == "trip"


# ---------------------------------------------------------------------------
# Task 3 -- heartbeat (BLOCKER 4: no fourth scheduled task)
# ---------------------------------------------------------------------------


def test_heartbeat_due_true_on_missing_log(tmp_path):
    log_path = str(tmp_path / "does_not_exist.log")
    assert guardian._heartbeat_due(log_path, datetime.now(timezone.utc)) is True


def test_heartbeat_due_false_immediately_after_heartbeat_entry(tmp_path):
    log_path = str(tmp_path / "paper_trading.log")
    now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"{now.isoformat()}|heartbeat|guardian alive\n")

    assert guardian._heartbeat_due(log_path, now) is False
    assert guardian._heartbeat_due(log_path, now + timedelta(hours=11)) is False
    assert guardian._heartbeat_due(log_path, now + timedelta(hours=13)) is True


def test_run_guardian_once_heartbeat_fires_at_least_every_twelve_hours(
    paper_conn, fake_ib, tmp_path, monkeypatch
):
    """Integration-level: run_guardian_once's own _heartbeat_due gating,
    exercised end to end. alerts.notify is replaced with a fake that writes
    a heartbeat line stamped with the SAME injected `now` the test controls
    (never the real wall clock -- ops_log.append_ops_log always stamps with
    datetime.now(timezone.utc), which would make a real-file version of
    this test non-deterministic)."""
    adapter = _ibkr_adapter(fake_ib)
    log_path = str(tmp_path / "paper_trading.log")
    heartbeat_calls: list[str] = []
    current_now = {"value": None}

    def _fake_notify(entry_type, message):
        if entry_type == "heartbeat":
            heartbeat_calls.append(message)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{current_now['value'].isoformat()}|heartbeat|{message}\n")
        return True

    monkeypatch.setattr(guardian.alerts, "notify", _fake_notify)

    first = datetime(2026, 7, 27, 9, 0, tzinfo=timezone.utc)
    current_now["value"] = first
    guardian.run_guardian_once(paper_conn, adapter, now=first, log_path=log_path)
    assert len(heartbeat_calls) == 1

    five_min_later = first + timedelta(minutes=5)
    current_now["value"] = five_min_later
    guardian.run_guardian_once(paper_conn, adapter, now=five_min_later, log_path=log_path)
    assert len(heartbeat_calls) == 1

    thirteen_hours_later = first + timedelta(hours=13)
    current_now["value"] = thirteen_hours_later
    guardian.run_guardian_once(paper_conn, adapter, now=thirteen_hours_later, log_path=log_path)
    assert len(heartbeat_calls) == 2


def test_no_new_task_scheduler_xml_created_by_task_3():
    """BLOCKER 4's 'no fourth scheduled task' constraint: exactly the
    existing paper_guardian_task.xml (Task 1's own artifact), never a
    second/heartbeat-specific XML file."""
    from pathlib import Path

    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    xml_files = sorted(p.name for p in scripts_dir.glob("*guardian*task*.xml"))
    assert xml_files == ["paper_guardian_task.xml"]


# ---------------------------------------------------------------------------
# T-05-05 -- no resting STP/STP LMT order type anywhere in this file
# ---------------------------------------------------------------------------


def test_guardian_never_constructs_a_stop_order_type():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "trader" / "paper" / "guardian.py"
    ).read_text(encoding="utf-8")
    assert "StopOrder" not in source
    assert "STP" not in source
