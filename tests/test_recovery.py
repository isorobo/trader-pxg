"""Integration tests for the crash-recovery contract end to end across a
simulated MULTI-DAY process restart (05-07-PLAN.md, RESIDUAL BLOCKER 1 /
W4).

Test 1 (entry side, RESIDUAL BLOCKER 1): the realistic fixture -- all FIVE
real config.LIVE_STRATEGY_CONFIGS live (none retired, the default state of a
fresh DB), and a symbol whose fixture bars are engineered so it fires the
loose momentum signal on day 1 only, never again on day 2 -- proving the
day-2 heal can only succeed through entry_pipeline's STEP 0 standalone pass,
not through the per-candidate loop.

Test 2 (exit side, BLOCKER 1): the equivalent persist-before-submit +
date-independent heal shape around run_guardian_once and a 'sell' order_ref.

Test 3 (W4, composed breaker-trip -> zero orders): a real
trader.risk.breakers.evaluate_breakers + record_breaker_transitions call
(never via the guardian, to isolate the exact mechanism under test), then
run_entry_pipeline_once asserted to submit zero orders.

No new production code is expected here -- this is a pure integration test
over 05-01/05-04/05-05/05-06's already-implemented heal/halt/clear/STEP-0
branches (see each test's own docstring for the exact gap it proves closed).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from trader.paper import clear_halt, config as paper_config, entry_pipeline, guardian, ledger, reconcile
from trader.paper.broker_ibkr import IBKRBrokerAdapter
from trader.risk import breakers

TRADING_DAY = date(2026, 7, 27)  # a real NYSE Monday
TRADING_DAY_2 = date(2026, 7, 28)  # the very next real NYSE Tuesday

TRADING_DAY_DT = datetime(2026, 7, 27, 15, 0, tzinfo=timezone.utc)
TRADING_DAY_2_DT = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)

_LIVE_PROFILE_NAMES = [cfg.profile_name for cfg in paper_config.LIVE_STRATEGY_CONFIGS]


@pytest.fixture(autouse=True)
def _mock_side_effects(monkeypatch):
    """alerts.notify is a no-op MagicMock across the three modules under
    test -- the real implementation writes into the repo's ops/ directory
    as a side effect, which this suite must never do (mirrors
    tests/test_entry_pipeline.py's and tests/test_guardian.py's own
    conventions).

    trader.paper.ops_log.append_ops_log itself is deliberately left REAL
    (not mocked) -- entry_pipeline.ops_log and clear_halt's own `ops_log`
    reference are the SAME shared module object (both do `from trader.paper
    import ops_log`), so mocking one would silently swallow the other's
    calls too, including clear_halt.clear_entry_halt's own
    manual_restart_required line this suite asserts on directly (BLOCKER
    3). Each test instead chdir's into its own tmp_path itself, as the
    FIRST statement in its body (never here, at fixture-setup time) -- the
    paper_conn fixture's own trader.data.db.get_connection call resolves
    its "migrations" directory relative to cwd, so chdir'ing before that
    fixture has finished creating the schema would silently apply zero
    migrations. Every fixture (including paper_conn) is guaranteed fully
    set up before any line of a test's own body runs, so chdir'ing there
    is safe (mirrors tests/test_reconciliation.py's own convention)."""
    monkeypatch.setattr(entry_pipeline.alerts, "notify", MagicMock(return_value=True))
    monkeypatch.setattr(guardian.alerts, "notify", MagicMock(return_value=True))
    monkeypatch.setattr(reconcile.alerts, "notify", MagicMock(return_value=True))


# ---------------------------------------------------------------------------
# Test doubles (mirrors tests/test_entry_pipeline.py / tests/test_guardian.py
# / tests/test_reconciliation.py's shapes exactly)
# ---------------------------------------------------------------------------


class _FakeTicker:
    def __init__(self, market_price):
        self._market_price = market_price

    def marketPrice(self):
        return self._market_price


class _FakeExecution:
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


class _FakePosition:
    def __init__(self, symbol: str, qty: float):
        self.contract = _FakeContract(symbol)
        self.position = qty


def _make_fake_fill(order_ref: str, perm_id: int, symbol: str, qty: float) -> _FakeFill:
    return _FakeFill(_FakeExecution(order_ref, perm_id, qty), _FakeContract(symbol))


def _make_fake_position(symbol: str, qty: float) -> _FakePosition:
    return _FakePosition(symbol, qty)


def _ibkr_adapter(fake_ib, latest_price: float | None = None) -> IBKRBrokerAdapter:
    if latest_price is not None:
        fake_ib.reqMktData.return_value = _FakeTicker(latest_price)
    return IBKRBrokerAdapter(host="127.0.0.1", port=4002, client_id=5, ib_client=fake_ib)


def _flat_short_bars_df(
    end: str = "2026-07-24", periods: int = 5, price: float = 50.0, volume: float = 1_000_000.0
) -> pd.DataFrame:
    """Too short (< BREAK_LOOKBACK + 1 == 21) to ever fire the loose
    momentum signal -- the default fixture for every non-focal symbol in
    STOCK_UNIVERSE."""
    dates = pd.bdate_range(end=end, periods=periods, tz="UTC")
    return pd.DataFrame(
        {
            "open": [price] * periods,
            "high": [price] * periods,
            "low": [price] * periods,
            "close": [price] * periods,
            "volume": [volume] * periods,
        },
        index=dates,
    )


def _non_refiring_orphan_bars_df(
    fire_end: str = "2026-07-24",
    periods: int = 35,
    base_price: float = 100.0,
    base_volume: float = 2_000_000.0,
    daily_pct: float = 0.01,
    volume_surge_mult: float = 2.0,
) -> pd.DataFrame:
    """35 monotonically-rising bars ending `fire_end` (fires the loose
    signal on day 1, mirrors tests/test_entry_pipeline.py's
    `_rising_bars_df`) PLUS one extra real NYSE business day appended (the
    very next trading day after `fire_end`) that is FLAT (no new high) and
    NOT volume-surged -- so a day-2 scan whose own "yesterday" cutoff lands
    on that 36th bar does NOT re-fire the loose momentum signal for this
    symbol (RESIDUAL BLOCKER 1's exact non-re-firing fixture). Both the
    breakout condition (today_close > prior_high) and the volume-surge
    condition independently fail on that 36th bar, so this is not a
    borderline case."""
    dates = pd.bdate_range(end=fire_end, periods=periods, tz="UTC")
    closes = [base_price * (1 + daily_pct) ** i for i in range(periods)]
    highs = [c * 1.001 for c in closes]
    lows = [c * 0.999 for c in closes]
    volumes = [base_volume] * periods
    volumes[-1] = base_volume * volume_surge_mult

    next_day = pd.bdate_range(start=fire_end, periods=2, tz="UTC")[1]
    last_close = closes[-1]

    all_dates = list(dates) + [next_day]
    all_opens = closes + [last_close]
    all_highs = highs + [last_close * 1.001]
    all_lows = lows + [last_close * 0.999]
    all_closes = closes + [last_close]
    all_volumes = volumes + [base_volume]

    return pd.DataFrame(
        {"open": all_opens, "high": all_highs, "low": all_lows, "close": all_closes, "volume": all_volumes},
        index=all_dates,
    )


def _patch_bars(monkeypatch, bars_by_symbol: dict[str, pd.DataFrame], default=None) -> None:
    """Patch entry_pipeline.get_daily_bars so every call returns a pre-built
    DataFrame keyed by symbol (never touching the network/db), truncated to
    <= the requested `end` (mirrors tests/test_entry_pipeline.py's own
    `_patch_bars`)."""
    if default is None:
        default = _flat_short_bars_df()

    def _fake_get_daily_bars(symbol, start=None, end=None, asset_class=None, conn=None):
        df = bars_by_symbol.get(symbol, default)
        if end is not None:
            cutoff = pd.Timestamp(end, tz="UTC")
            df = df[df.index <= cutoff]
        return df

    monkeypatch.setattr(entry_pipeline, "get_daily_bars", _fake_get_daily_bars)


def _open_position(
    conn,
    strategy_id: str = "momentum_stock",
    symbol: str = "AAPL",
    entry_price: float = 100.0,
    qty: float = 10.0,
    entry_ts: str = "2026-07-20T09:30:00",
    stop_pct: float | None = -0.10,
) -> int:
    from trader.backtest.config import EXIT_PROFILE

    profile = EXIT_PROFILE(
        stop_pct=stop_pct, tp_pct=None, scale_out=(), trailing_pct=None,
        max_hold_days=None, eod_flat=False,
    )
    return ledger.open_position(
        conn, strategy_id, symbol, "ibkr_paper", "stock", qty, entry_price,
        entry_ts, f"{strategy_id}:{symbol}:2026-07-20:buy:entry", profile,
    )


# ---------------------------------------------------------------------------
# Test 1 -- RESIDUAL BLOCKER 1, entry side, realistic 5-profile, non-
# re-firing fixture
# ---------------------------------------------------------------------------


def test_multi_day_crash_halt_clear_heal_entry_side_non_refiring_symbol(
    paper_conn, fake_ib, tmp_path, monkeypatch
):
    """The exact RESIDUAL BLOCKER 1 scenario, end to end: DAY 1 fires and
    submits; the broker fills it but the process crashes before
    update_order_status/open_position run; reconciliation halts on the
    unexplained broker-side position; a human clears the halt; DAY 2's bars
    for the SAME symbol are engineered to NOT re-fire the signal (asserted
    directly before run_entry_pipeline_once is ever called for day 2) --
    proving the heal can only succeed via STEP 0's unscoped pass, never the
    per-candidate loop."""
    monkeypatch.chdir(tmp_path)
    symbol = "AAPL"
    orphan_bars = _non_refiring_orphan_bars_df()

    # All five real live configs remain live -- no retire_strategy call
    # anywhere in this test (the default state of a fresh paper_conn).
    assert len(entry_pipeline._live_profile_names(paper_conn)) == 5

    # --- DAY 1: fires, gates, sizes, submits -------------------------------
    _patch_bars(monkeypatch, {symbol: orphan_bars})
    fake_ib.placeOrder.return_value.order.permId = 999
    adapter = _ibkr_adapter(fake_ib)

    day1_result = entry_pipeline.run_entry_pipeline_once(
        paper_conn, adapter, as_of_date=TRADING_DAY
    )

    assert day1_result["candidates"] == 1
    assert len(day1_result["submitted"]) == 1
    order_ref = day1_result["submitted"][0]
    assert fake_ib.placeOrder.call_count == 1

    order = ledger.get_order_by_ref(paper_conn, order_ref)
    profile_name = order["strategy_id"]  # never assumed -- read back from the DB
    assert profile_name in _LIVE_PROFILE_NAMES
    qty = order["qty"]

    # --- Simulate the crash: broker filled it, but this process crashed
    # before update_order_status/open_position ever ran. -------------------
    paper_conn.execute(
        "UPDATE paper_orders SET status='pending_submit', perm_id=NULL, "
        "fill_price=NULL, filled_ts=NULL WHERE order_ref=?",
        (order_ref,),
    )
    paper_conn.execute(
        "DELETE FROM paper_positions WHERE entry_order_ref=?", (order_ref,)
    )
    paper_conn.commit()
    assert ledger.get_open_positions(paper_conn) == []

    # --- The broker's own state now reflects the fill. ---------------------
    broker_perm_id = 555
    fake_ib.positions.return_value = [_make_fake_position(symbol, qty)]
    fake_ib.fills.return_value = [_make_fake_fill(order_ref, broker_perm_id, symbol, qty)]

    reconcile_result = reconcile.run_reconcile_once(paper_conn, adapter)
    assert reconcile_result["halted"] is True
    assert reconcile.is_entry_halted(paper_conn) is True

    # --- A human clears the halt (also appends manual_restart_required, per
    # BLOCKER 3). -------------------------------------------------------------
    ops_log_path = str(tmp_path / "ops.log")
    clear_halt.clear_entry_halt(
        paper_conn, "test: verified broker fill in Gateway, healing next run",
        log_path=ops_log_path,
    )
    assert reconcile.is_entry_halted(paper_conn) is False
    ops_lines = [
        line for line in open(ops_log_path, encoding="utf-8").read().splitlines() if line
    ]
    assert len(ops_lines) == 1
    assert "manual_restart_required" in ops_lines[0]

    # --- DAY 2: the same symbol's bars are proven, BEFORE
    # run_entry_pipeline_once is ever called, to NOT re-fire. ----------------
    day2_candidates = entry_pipeline.scan_candidates(paper_conn, TRADING_DAY_2)
    assert symbol not in {c["symbol"] for c in day2_candidates}

    adapter_day2 = _ibkr_adapter(fake_ib, latest_price=150.0)
    day2_result = entry_pipeline.run_entry_pipeline_once(
        paper_conn, adapter_day2, as_of_date=TRADING_DAY_2
    )

    # No second broker submission across the ENTIRE two-day scenario.
    assert fake_ib.placeOrder.call_count == 1
    assert order_ref in day2_result["healed"]

    healed_order = ledger.get_order_by_ref(paper_conn, order_ref)
    assert healed_order["status"] == "filled"
    assert healed_order["perm_id"] == broker_perm_id

    open_positions = ledger.get_open_positions(paper_conn)
    assert len(open_positions) == 1
    assert open_positions[0]["symbol"] == symbol
    assert open_positions[0]["qty"] == qty


# ---------------------------------------------------------------------------
# Test 2 -- BLOCKER 1, exit side (guardian)
# ---------------------------------------------------------------------------


def test_multi_day_crash_heal_exit_side_no_second_sell_call(
    paper_conn, fake_ib, tmp_path, monkeypatch
):
    """The equivalent shape around run_guardian_once and a 'sell'
    order_ref: a guardian tick decides and persists an exit, the broker
    fills it, but the process "crashes" before update_order_status/
    close_position run; a LATER tick (a real calendar date later) finds and
    heals it via the identical persist-before-submit + date-independent
    get_unresolved_orders/find_unresolved_match sequence entry_pipeline uses
    -- never a second SELL call."""
    monkeypatch.chdir(tmp_path)
    symbol = "MSFT"
    _open_position(paper_conn, strategy_id="momentum_stock", symbol=symbol, entry_price=100.0, qty=10.0, stop_pct=-0.10)

    fake_ib.placeOrder.return_value.order.permId = 111
    adapter = _ibkr_adapter(fake_ib, latest_price=89.0)  # below the -10% stop

    day1_result = guardian.run_guardian_once(
        paper_conn, adapter, now=TRADING_DAY_DT, log_path=str(tmp_path / "ops.log")
    )
    assert len(day1_result["exits"]) == 1
    order_ref = day1_result["exits"][0]["order_ref"]
    assert fake_ib.placeOrder.call_count == 1

    position_row = paper_conn.execute(
        "SELECT position_id FROM paper_positions WHERE entry_order_ref = ?",
        (f"momentum_stock:{symbol}:2026-07-20:buy:entry",),
    ).fetchone()
    assert position_row is not None
    position_id = position_row[0]

    # --- Simulate the crash: the broker filled the SELL, but this process
    # crashed before update_order_status/close_position ever ran. ----------
    paper_conn.execute(
        "UPDATE paper_orders SET status='pending_submit', perm_id=NULL, "
        "fill_price=NULL, filled_ts=NULL WHERE order_ref=?",
        (order_ref,),
    )
    paper_conn.execute(
        "DELETE FROM paper_trades WHERE exit_order_ref=?", (order_ref,)
    )
    paper_conn.execute(
        "UPDATE paper_positions SET status='open' WHERE position_id=?", (position_id,)
    )
    paper_conn.commit()
    assert len(ledger.get_open_positions(paper_conn)) == 1

    broker_perm_id = 777
    fake_ib.fills.return_value = [_make_fake_fill(order_ref, broker_perm_id, symbol, 10.0)]

    # --- DAY 2 (a real later calendar date): the condition still holds
    # (same low price), so the exit re-evaluates and the heal branch of
    # _submit_exit fires -- never a second place_order/SELL call. ----------
    day2_result = guardian.run_guardian_once(
        paper_conn, adapter, now=TRADING_DAY_2_DT, log_path=str(tmp_path / "ops.log")
    )

    assert fake_ib.placeOrder.call_count == 1
    assert len(day2_result["exits"]) == 1
    assert day2_result["exits"][0]["healed"] is True
    assert day2_result["exits"][0]["order_ref"] == order_ref

    healed_order = ledger.get_order_by_ref(paper_conn, order_ref)
    assert healed_order["status"] == "filled"
    assert healed_order["perm_id"] == broker_perm_id

    assert ledger.get_open_positions(paper_conn) == []
    trades = paper_conn.execute(
        "SELECT COUNT(*) FROM paper_trades WHERE exit_order_ref = ?", (order_ref,)
    ).fetchone()[0]
    assert trades == 1


# ---------------------------------------------------------------------------
# Test 3 -- W4, composed real breaker-trip -> zero orders
# ---------------------------------------------------------------------------


def test_composed_breaker_trip_zeroes_out_new_entry_submissions(
    paper_conn, fake_ib, tmp_path, monkeypatch
):
    """A real drawdown breaker trip, persisted via
    trader.risk.breakers.evaluate_breakers + record_breaker_transitions
    directly (never via the guardian, to isolate the exact mechanism under
    test) -- the VERY NEXT run_entry_pipeline_once call submits ZERO orders,
    even with a fresh candidate that would otherwise clear gate/sizer."""
    monkeypatch.chdir(tmp_path)
    previous_state = breakers.read_breaker_state(paper_conn)
    evaluation = breakers.evaluate_breakers(
        equity_curve=[100_000.0, 89_000.0],  # -11% drawdown, breaches -10%
        trade_pnls=[-11_000.0],
    )
    assert evaluation["drawdown_tripped"] is True
    breakers.record_breaker_transitions(paper_conn, previous_state, evaluation)
    assert reconcile.is_entry_halted(paper_conn) is True

    def _rising_bars_df(
        end: str = "2026-07-24", periods: int = 35, base_price: float = 100.0,
        base_volume: float = 2_000_000.0, daily_pct: float = 0.01,
    ) -> pd.DataFrame:
        dates = pd.bdate_range(end=end, periods=periods, tz="UTC")
        closes = [base_price * (1 + daily_pct) ** i for i in range(periods)]
        highs = [c * 1.001 for c in closes]
        lows = [c * 0.999 for c in closes]
        volumes = [base_volume] * periods
        volumes[-1] = base_volume * 2.0
        return pd.DataFrame(
            {"open": closes, "high": highs, "low": lows, "close": closes, "volume": volumes},
            index=dates,
        )

    _patch_bars(monkeypatch, {"AAPL": _rising_bars_df()})
    adapter = _ibkr_adapter(fake_ib)

    result = entry_pipeline.run_entry_pipeline_once(paper_conn, adapter, as_of_date=TRADING_DAY)

    assert result["candidates"] == 1
    assert result["accepted"] == 1
    assert result["submitted"] == []
    assert result["halted"] is True
    fake_ib.placeOrder.assert_not_called()
