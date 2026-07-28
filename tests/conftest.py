"""Shared pytest fixtures for the ground_truth test suite."""

from unittest.mock import MagicMock

import pytest

from trader.ground_truth import db
from trader.data import db as trader_db


@pytest.fixture(autouse=True)
def _no_real_telegram(monkeypatch):
    """Never let the test suite send real Telegram messages (Phase 7 fix).

    alerts.notify() calls load_dotenv() at call time, so once the owner's
    real TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID landed in .env (05-08 ops
    checkpoint, 2026-07-27) every test that reached alerts.notify -- kill
    retirements, breaker trips, fills -- fired a REAL message at the owner's
    phone and made token-unset tests flaky. Strip the env vars and neuter
    alerts' load_dotenv for every test; tests that need a configured
    Telegram set the env vars explicitly via monkeypatch.setenv.
    """
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr("trader.paper.alerts.load_dotenv", lambda *a, **k: None)


@pytest.fixture
def tmp_db_path(tmp_path):
    """Path to a fresh, non-existent SQLite file inside pytest's tmp_path."""
    return str(tmp_path / "trader.db")


@pytest.fixture
def conn(tmp_db_path):
    """A live connection to a fresh temp DB, closed after the test."""
    connection = db.get_connection(tmp_db_path)
    yield connection
    connection.close()


@pytest.fixture
def paper_conn(tmp_path):
    """A live connection to a fresh temp DB via trader.data.db's migration
    runner (applies every migration, including 0005_paper_trading.sql) --
    parallel to the ground_truth `conn` fixture above, but using the
    migration runner every Phase 1+ module shares, not trader.ground_truth.db.
    """
    connection = trader_db.get_connection(str(tmp_path / "trader.db"))
    yield connection
    connection.close()


@pytest.fixture
def paper_trade_factory():
    """Deterministic paper_trades row builder for tournament/attribution
    tests (07-RESEARCH.md Wave 0 gap): insert one closed trade per pnl
    value, exit dates one calendar day apart, so Sharpe/PF shapes are
    controllable per test ("clearly promotable", "clearly demotable",
    "borderline")."""
    from datetime import date, timedelta

    def _insert(conn, profile_name, pnls, start="2026-01-01", symbol="AAPL"):
        start_date = date.fromisoformat(start)
        for i, pnl in enumerate(pnls):
            exit_day = (start_date + timedelta(days=i)).isoformat()
            conn.execute(
                """
                INSERT INTO paper_trades
                    (strategy_id, profile_name, symbol, venue, asset_class,
                     entry_ts, entry_price, exit_ts, exit_price, exit_reason,
                     qty, fees, slippage_cost, pnl, entry_order_ref, exit_order_ref)
                VALUES (?, ?, ?, 'ibkr_paper', 'stock', ?, 100.0, ?, 100.0,
                        'stop', 10, 1.0, 0.5, ?, 'entry_ref', 'exit_ref')
                """,
                (
                    profile_name,
                    profile_name,
                    symbol,
                    f"{exit_day}T09:30:00",
                    f"{exit_day}T15:30:00",
                    pnl,
                ),
            )
        conn.commit()

    return _insert


@pytest.fixture
def mock_yf_screen_result():
    """Shape of yfinance's yf.screen("day_gainers") response: {"quotes": [...]}."""
    quotes = [
        {
            "symbol": f"TICK{i}",
            "regularMarketPrice": 10.0 + i,
            "regularMarketChangePercent": 50.0 - i * 0.1,
        }
        for i in range(50)
    ]
    return {"quotes": quotes}


@pytest.fixture
def mock_finviz_rows():
    """Shape of finviz.screener.Screener rows: string Price/Change fields."""
    return [
        {
            "Ticker": f"FTICK{i}",
            "Price": f"{20.0 + i:.2f}",
            "Change": f"{45.20 - i * 0.1:.2f}%",
        }
        for i in range(50)
    ]


@pytest.fixture
def fake_ib():
    """A fake `ib_async.IB` client for trader.paper.broker_ibkr (05-03-PLAN.md).

    A MagicMock so any method not explicitly configured below (e.g.
    connect/disconnect/reqOpenOrders/reqMktData) is a harmless no-op call
    recorder by default. positions()/openTrades()/fills() default to empty
    lists; placeOrder() defaults to a fake Trade whose .order.orderRef and
    .order.permId are settable per-test via
    `fake_ib.placeOrder.return_value.order.orderRef = "..."` etc. Shared by
    this plan's tests and every later plan (guardian, entry_pipeline,
    reconciliation) that needs a fake broker -- never a real network/Gateway
    connection.
    """
    client = MagicMock()
    client.positions.return_value = []
    client.openTrades.return_value = []
    client.fills.return_value = []
    client.placeOrder.return_value = MagicMock()
    return client


@pytest.fixture
def mock_coingecko_markets_response():
    """Shape of CoinGecko /coins/markets response rows."""
    return [
        {
            "id": f"coin-{i}",
            "symbol": f"c{i}",
            "current_price": 1.0 + i,
            "price_change_percentage_24h": 30.0 - i * 0.2,
        }
        for i in range(50)
    ]
