"""Mockable thin `ib_async` adapter for the IBKR paper account (05-03-PLAN.md).

Standing rule 6 (real money is Phase 9): this module only ever connects to
`config.IBKR_PAPER_PORT` (4002) -- `connect()` asserts this at call time too
(T-05-06, defence in depth even though the constructor already pins it via
`config.IBKR_PAPER_PORT`'s default).

`ib_async` is imported lazily, inside `connect()` only, never at module
import time -- so importing this module (and testing `round_shares_down` or
constructing `IBKRBrokerAdapter` with an injected fake) never requires
`ib_async` to be installed or a live Gateway connection to exist. Every
public method reads/writes only through `self._ib_client`, the constructor's
injection point: production callers pass `ib_client=None` and get a real
`ib_async.IB()` instance only inside `connect()`; tests inject a fake (see
`tests/conftest.py`'s `fake_ib` fixture).

D-06/Pitfall 5 (05-RESEARCH.md): `orderRef` (not `orderId`, a per-session
sequence, nor `clientId`, a per-connection id) is the durable idempotency
key threaded through every order; `permId` is IBKR's durable,
reconnect-and-crash-surviving account-wide identifier used for
reconciliation joins. Both are captured here and returned to the caller --
entry_pipeline (05-06) and guardian (05-05) never touch `ib_async` objects
directly (this module is the single seam).
"""

from __future__ import annotations

import inspect
import logging

from trader.paper import config

log = logging.getLogger(__name__)

# Bounded wait for the open-orders sync inside snapshot(). Discovered on
# the first real-Gateway session (05-08 checkpoint, 2026-07-30): a freshly
# provisioned paper account can fail to send openOrderEnd, and ib_async's
# synchronous reqOpenOrders() then waits on it FOREVER. An unattended
# system must degrade to session-cached order state instead of hanging --
# a missed heal on one tick is retried next tick; a hung guardian is not.
ORDER_SYNC_TIMEOUT_S = 15.0


def round_shares_down(dollar_amount: float, price: float) -> int:
    """Floor a dollar allocation to a whole share count (Pitfall 2).

    Never rounds up and never rounds to nearest -- IBKR's API does not
    support fractional shares for US stocks (crypto/forex only), and
    rounding UP or to-nearest could push the resulting notional over the
    sizer's dollar cap. Rounding DOWN can only under-use the allocated
    cash, never violate a cap.
    """
    if price <= 0:
        return 0
    return int(dollar_amount // price)


class IBKRBrokerAdapter:
    """Thin, testable adapter around `ib_async.IB` for the paper account."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
        ib_client=None,
    ) -> None:
        self.host = host if host is not None else config.ibkr_host()
        self.port = port if port is not None else config.IBKR_PAPER_PORT
        self.client_id = client_id if client_id is not None else config.ibkr_client_id()
        # Constructor injection point (tests pass a fake here). Production
        # callers pass None and get a lazily-imported real `IB()` only
        # inside connect() -- never at import time.
        self._ib_client = ib_client

    def connect(self) -> None:
        """Connect to IB Gateway/TWS, paper port ONLY.

        Standing rule 6 / T-05-06: raises ValueError if self.port is
        anything other than 4002, even though the constructor already
        defaults to (and normally receives) the paper port -- defence in
        depth against a caller explicitly passing the live port (4001).
        """
        if self.port != config.IBKR_PAPER_PORT:
            raise ValueError(
                f"IBKRBrokerAdapter refuses to connect to port {self.port!r} -- "
                f"only the paper port ({config.IBKR_PAPER_PORT}) is permitted "
                "(standing rule 6: real money is Phase 9)"
            )
        if self._ib_client is None:
            # Lazy import: ib_async is only required on an actual connect(),
            # never for pure-logic tests that inject a fake client.
            from ib_async import IB

            self._ib_client = IB()
        self._ib_client.connect(self.host, self.port, clientId=self.client_id)

    def disconnect(self) -> None:
        self._ib_client.disconnect()

    def place_order(self, symbol: str, action: str, quantity: int, order_ref: str) -> dict:
        """Submit a market order, tagging it with the deterministic
        `order_ref` (D-06) before submission.

        Returns {"order_ref": ..., "perm_id": ..., "status": "submitted"} --
        `perm_id` is read off the returned Trade's `.order.permId` (the
        durable IBKR-assigned identifier, Pitfall 5), never `.orderId`.
        """
        from ib_async import MarketOrder, Stock

        contract = Stock(symbol, "SMART", "USD")
        order = MarketOrder(action, quantity)
        order.orderRef = order_ref
        trade = self._ib_client.placeOrder(contract, order)
        return {
            "order_ref": order_ref,
            "perm_id": trade.order.permId,
            "status": "submitted",
        }

    def _request_open_orders_bounded(self) -> None:
        """reqOpenOrders with a hard ORDER_SYNC_TIMEOUT_S cap.

        Takes the bounded-async path only when the client's
        reqOpenOrdersAsync() returns a REAL coroutine (the live ib_async
        client); test fakes (MagicMocks or plain fakes) fall through to the
        plain synchronous reqOpenOrders() call they already implement. On
        timeout, degrades to session-cached order state with a warning --
        never a hang (2026-07-30 real-Gateway regression).
        """
        maybe_coro = None
        async_fn = getattr(self._ib_client, "reqOpenOrdersAsync", None)
        if async_fn is not None:
            maybe_coro = async_fn()
        if inspect.iscoroutine(maybe_coro):
            import asyncio

            from ib_async import util

            try:
                util.run(asyncio.wait_for(maybe_coro, timeout=ORDER_SYNC_TIMEOUT_S))
            except (TimeoutError, asyncio.TimeoutError):
                log.warning(
                    "reqOpenOrders timed out after %.0fs -- proceeding with "
                    "session-cached order state (heals retry next tick)",
                    ORDER_SYNC_TIMEOUT_S,
                )
        else:
            self._ib_client.reqOpenOrders()

    def snapshot(self) -> dict:
        """Fetch positions/open_orders/fills from the broker.

        Calls reqOpenOrders() first so openTrades()/fills() reflect the
        current session state, matching 05-RESEARCH.md Pattern 1's
        pre-submit dual-check convention.
        """
        self._request_open_orders_bounded()
        positions = self._ib_client.positions()
        open_orders = self._ib_client.openTrades()
        fills = self._ib_client.fills()
        return {
            "positions": {p.contract.symbol: p.position for p in positions},
            "open_orders": list(open_orders),
            "fills": [
                {
                    "orderRef": f.execution.orderRef,
                    "permId": f.execution.permId,
                    "symbol": f.contract.symbol,
                    "qty": f.execution.shares,
                }
                for f in fills
            ],
        }

    def latest_price(self, symbol: str) -> float:
        """Delayed-data price lookup (Pitfall 4).

        Paper accounts default to 15-20 minute delayed data unless the
        owner's live account carries a market-data subscription -- accepted
        explicitly (not silently treated as real-time) per 05-RESEARCH.md.

        2026-08-04 real-position regression: the contract MUST be qualified
        (conId populated) before reqMktData -- ib_async raises on hashing an
        unqualified contract, which crashed every guardian tick once a real
        position existed. After a short tick wait, the price resolves as
        marketPrice -> last -> close (delayed close covers out-of-session
        ticks); all-NaN raises RuntimeError -- a silent NaN would disable
        every exit check while looking healthy (the system never lies to
        itself).
        """
        from ib_async import Stock

        contract = Stock(symbol, "SMART", "USD")
        qualify = getattr(self._ib_client, "qualifyContracts", None)
        if callable(qualify):
            qualify(contract)
        # Type 4 = delayed-frozen: delayed ticks in session, the frozen
        # delayed close outside it. Without this, a paper account with no
        # market-data subscription gets NOTHING back from reqMktData
        # (2026-08-04, observed live).
        set_type = getattr(self._ib_client, "reqMarketDataType", None)
        if callable(set_type):
            set_type(4)
        ticker = self._ib_client.reqMktData(contract)
        sleep_fn = getattr(self._ib_client, "sleep", None)
        if callable(sleep_fn):
            sleep_fn(2.0)

        def _usable(value) -> bool:
            return value is not None and value == value  # rejects None/NaN

        if hasattr(ticker, "marketPrice"):
            price = ticker.marketPrice()
            if _usable(price):
                return price
        if _usable(getattr(ticker, "last", None)):
            return ticker.last
        if _usable(getattr(ticker, "close", None)):
            return ticker.close
        raise RuntimeError(
            f"no usable price for {symbol} (marketPrice/last/close all "
            "missing or NaN) -- refusing to tick exits on unknown prices"
        )
