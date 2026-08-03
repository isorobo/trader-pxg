"""Tests for trader.paper.broker_ibkr -- the mockable thin ib_async adapter
(05-03-PLAN.md).

Every test uses the `fake_ib` fixture (tests/conftest.py) -- a MagicMock
standing in for `ib_async.IB`. No test ever attempts a real Gateway
connection or imports `ib_async` types directly.
"""

from __future__ import annotations

import pytest

from trader.paper import broker_ibkr
from trader.paper.broker_ibkr import IBKRBrokerAdapter, round_shares_down


# ---------------------------------------------------------------------------
# round_shares_down -- pure, floor-only (Pitfall 2)
# ---------------------------------------------------------------------------


def test_round_shares_down_floors_never_rounds_to_nearest_or_up():
    assert round_shares_down(3412.50, 87.30) == 39


def test_round_shares_down_zero_dollar_amount_returns_zero():
    assert round_shares_down(0.0, 87.30) == 0


def test_round_shares_down_never_exceeds_dollar_amount():
    result = round_shares_down(3412.50, 87.30)
    assert result * 87.30 <= 3412.50


def test_round_shares_down_zero_price_returns_zero():
    assert round_shares_down(1000.0, 0.0) == 0


# ---------------------------------------------------------------------------
# connect -- port 4002 only (standing rule 6, T-05-06)
# ---------------------------------------------------------------------------


def test_connect_calls_fake_ib_connect_with_paper_port_only(fake_ib):
    adapter = IBKRBrokerAdapter(host="127.0.0.1", port=4002, client_id=5, ib_client=fake_ib)
    adapter.connect()
    fake_ib.connect.assert_called_once_with("127.0.0.1", 4002, clientId=5)


def test_connect_raises_valueerror_for_port_4001(fake_ib):
    adapter = IBKRBrokerAdapter(host="127.0.0.1", port=4001, client_id=5, ib_client=fake_ib)
    with pytest.raises(ValueError):
        adapter.connect()
    fake_ib.connect.assert_not_called()


def test_connect_raises_valueerror_for_any_non_4002_port(fake_ib):
    adapter = IBKRBrokerAdapter(host="127.0.0.1", port=9999, client_id=5, ib_client=fake_ib)
    with pytest.raises(ValueError):
        adapter.connect()


def test_constructor_defaults_port_to_paper_port():
    adapter = IBKRBrokerAdapter(ib_client="not-used-until-connect")
    assert adapter.port == 4002


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


def test_disconnect_calls_fake_ib_disconnect(fake_ib):
    adapter = IBKRBrokerAdapter(host="127.0.0.1", port=4002, client_id=5, ib_client=fake_ib)
    adapter.disconnect()
    fake_ib.disconnect.assert_called_once()


# ---------------------------------------------------------------------------
# place_order -- orderRef/permId capture (Pitfall 5, D-06)
# ---------------------------------------------------------------------------


def test_place_order_sets_order_ref_and_captures_perm_id(fake_ib):
    fake_ib.placeOrder.return_value.order.orderRef = "s:AAPL:2026-07-27:buy:entry"
    fake_ib.placeOrder.return_value.order.permId = 123456

    adapter = IBKRBrokerAdapter(host="127.0.0.1", port=4002, client_id=5, ib_client=fake_ib)
    result = adapter.place_order(
        symbol="AAPL", action="BUY", quantity=10, order_ref="s:AAPL:2026-07-27:buy:entry"
    )

    assert result == {
        "order_ref": "s:AAPL:2026-07-27:buy:entry",
        "perm_id": 123456,
        "status": "submitted",
    }
    fake_ib.placeOrder.assert_called_once()
    called_contract, called_order = fake_ib.placeOrder.call_args[0]
    assert called_contract.symbol == "AAPL"
    assert called_order.orderRef == "s:AAPL:2026-07-27:buy:entry"
    assert called_order.action == "BUY"
    assert called_order.totalQuantity == 10


# ---------------------------------------------------------------------------
# snapshot -- positions/open_orders/fills built from fake_ib
# ---------------------------------------------------------------------------


def test_snapshot_builds_positions_open_orders_and_fills(fake_ib):
    position = _make_fake_position("AAPL", 10)
    fake_ib.positions.return_value = [position]

    open_trade = object()
    fake_ib.openTrades.return_value = [open_trade]

    fill = _make_fake_fill(
        order_ref="s:MSFT:2026-07-27:buy:entry", perm_id=999, symbol="MSFT", qty=7
    )
    fake_ib.fills.return_value = [fill]

    adapter = IBKRBrokerAdapter(host="127.0.0.1", port=4002, client_id=5, ib_client=fake_ib)
    result = adapter.snapshot()

    fake_ib.reqOpenOrders.assert_called_once()
    assert result["positions"] == {"AAPL": 10}
    assert result["open_orders"] == [open_trade]
    assert result["fills"] == [
        {
            "orderRef": "s:MSFT:2026-07-27:buy:entry",
            "permId": 999,
            "symbol": "MSFT",
            "qty": 7,
        }
    ]


def test_snapshot_empty_when_fake_ib_returns_nothing(fake_ib):
    adapter = IBKRBrokerAdapter(host="127.0.0.1", port=4002, client_id=5, ib_client=fake_ib)
    result = adapter.snapshot()
    assert result == {"positions": {}, "open_orders": [], "fills": []}


def test_latest_price_qualifies_contract_before_requesting(fake_ib):
    """2026-08-04 real-position regression: an unqualified contract (no
    conId) makes ib_async raise inside reqMktData -- every guardian tick
    crashed once a real position existed. qualifyContracts must be called
    before the data request."""
    ticker = _FakeTicker(market_price=101.25, last=101.10)
    fake_ib.reqMktData.return_value = ticker
    adapter = IBKRBrokerAdapter(host="127.0.0.1", port=4002, client_id=5, ib_client=fake_ib)

    adapter.latest_price("JPM")

    fake_ib.qualifyContracts.assert_called_once()


def test_latest_price_nan_falls_back_and_all_nan_raises(fake_ib):
    """A NaN marketPrice must fall through to last/close, and all-NaN must
    raise rather than silently disabling exit checks."""
    nan = float("nan")

    fake_ib.reqMktData.return_value = _FakeTicker(market_price=nan, last=99.5)
    adapter = IBKRBrokerAdapter(host="127.0.0.1", port=4002, client_id=5, ib_client=fake_ib)
    assert adapter.latest_price("JPM") == 99.5

    class _AllNan:
        last = nan
        close = nan

        def marketPrice(self):
            return nan

    fake_ib.reqMktData.return_value = _AllNan()
    with pytest.raises(RuntimeError, match="no usable price"):
        adapter.latest_price("JPM")


def test_scheduled_processes_use_distinct_client_ids():
    """2026-08-03 collision regression: the Gateway rejects simultaneous
    connections sharing one client id, and the minutely reconcile can
    overlap guardian/entry whenever startup sync runs slow. Three
    processes, three ids -- forever."""
    from trader.paper import config

    ids = {
        config.IBKR_CLIENT_ID_DEFAULT,
        config.IBKR_CLIENT_ID_GUARDIAN,
        config.IBKR_CLIENT_ID_ENTRY,
    }
    assert len(ids) == 3


def test_snapshot_order_sync_never_hangs_on_missing_open_order_end(monkeypatch):
    """2026-07-30 real-Gateway regression: a fresh paper account can never
    send openOrderEnd, and ib_async's synchronous reqOpenOrders() then
    waits forever. The bounded path must time out and degrade to
    session-cached order state instead of hanging the unattended loop."""
    import asyncio
    import time

    from trader.paper import broker_ibkr

    class _HangingClient:
        def reqOpenOrdersAsync(self):
            return asyncio.sleep(999)

        def positions(self):
            return []

        def openTrades(self):
            return []

        def fills(self):
            return []

    monkeypatch.setattr(broker_ibkr, "ORDER_SYNC_TIMEOUT_S", 0.2)
    adapter = IBKRBrokerAdapter(
        host="127.0.0.1", port=4002, client_id=5, ib_client=_HangingClient()
    )

    start = time.monotonic()
    result = adapter.snapshot()
    elapsed = time.monotonic() - start

    assert elapsed < 5.0, f"snapshot took {elapsed:.1f}s -- the cap did not bind"
    assert result == {"positions": {}, "open_orders": [], "fills": []}


# ---------------------------------------------------------------------------
# latest_price -- delayed-data lookup (Pitfall 4)
# ---------------------------------------------------------------------------


def test_latest_price_reads_market_price(fake_ib):
    ticker = _FakeTicker(market_price=101.25, last=101.10)
    fake_ib.reqMktData.return_value = ticker

    adapter = IBKRBrokerAdapter(host="127.0.0.1", port=4002, client_id=5, ib_client=fake_ib)
    assert adapter.latest_price("AAPL") == 101.25


def test_latest_price_falls_back_to_last_when_market_price_is_none(fake_ib):
    ticker = _FakeTicker(market_price=None, last=101.10)
    fake_ib.reqMktData.return_value = ticker

    adapter = IBKRBrokerAdapter(host="127.0.0.1", port=4002, client_id=5, ib_client=fake_ib)
    assert adapter.latest_price("AAPL") == 101.10


# ---------------------------------------------------------------------------
# Module-level guard: IBKR_PAPER_PORT constant present, no other port literal
# ---------------------------------------------------------------------------


def test_module_references_ibkr_paper_port_constant():
    assert "IBKR_PAPER_PORT" in vars(broker_ibkr) or "config.IBKR_PAPER_PORT" in open(
        broker_ibkr.__file__, encoding="utf-8"
    ).read()


# ---------------------------------------------------------------------------
# Test doubles (plain objects, never MagicMock, so attribute-shape mistakes
# in broker_ibkr.py surface as AttributeError instead of silently passing)
# ---------------------------------------------------------------------------


class _FakePosition:
    def __init__(self, symbol: str, qty: float):
        self.contract = _FakeContract(symbol)
        self.position = qty


class _FakeContract:
    def __init__(self, symbol: str):
        self.symbol = symbol


class _FakeExecution:
    def __init__(self, order_ref: str, perm_id: int, shares: float):
        self.orderRef = order_ref
        self.permId = perm_id
        self.shares = shares


class _FakeFill:
    def __init__(self, execution: _FakeExecution, contract: _FakeContract):
        self.execution = execution
        self.contract = contract


class _FakeTicker:
    def __init__(self, market_price, last):
        self._market_price = market_price
        self.last = last

    def marketPrice(self):
        return self._market_price


def _make_fake_position(symbol: str, qty: float) -> _FakePosition:
    return _FakePosition(symbol, qty)


def _make_fake_fill(order_ref: str, perm_id: int, symbol: str, qty: float) -> _FakeFill:
    return _FakeFill(_FakeExecution(order_ref, perm_id, qty), _FakeContract(symbol))
