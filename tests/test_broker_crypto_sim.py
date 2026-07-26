"""Tests for trader.paper.broker_crypto_sim -- the crypto simulated-ledger
price/fill adapter (05-03-PLAN.md, D-04).

No test performs a real network call -- every ccxt client is a fake/mock
passed via the constructor-injection-equivalent `client=` argument.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trader.paper import broker_crypto_sim
from trader.backtest.config import FEE_TABLE, SLIPPAGE_PCT

REPO_ROOT = Path(__file__).resolve().parents[1]
BROKER_CRYPTO_SIM_SOURCE_PATH = REPO_ROOT / "trader" / "paper" / "broker_crypto_sim.py"


class _FakeCcxtClient:
    def __init__(self, ticker_last: float):
        self._ticker_last = ticker_last
        self.fetch_ticker_calls = []

    def fetch_ticker(self, symbol):
        self.fetch_ticker_calls.append(symbol)
        return {"last": self._ticker_last}


class _FakeKrakenClient:
    def __init__(self, balance: dict):
        self._balance = balance
        self.fetch_balance_called = False

    def fetch_balance(self):
        self.fetch_balance_called = True
        return self._balance


# ---------------------------------------------------------------------------
# fetch_price
# ---------------------------------------------------------------------------


def test_fetch_price_returns_fake_client_ticker_last():
    fake_client = _FakeCcxtClient(ticker_last=65000.0)
    result = broker_crypto_sim.fetch_price("BTC/USDT", client=fake_client)
    assert result == 65000.0
    assert fake_client.fetch_ticker_calls == ["BTC/USDT"]


# ---------------------------------------------------------------------------
# simulate_fill -- reuses trader.backtest.fills verbatim
# ---------------------------------------------------------------------------


def test_simulate_fill_applies_slippage_and_fee_for_crypto_major():
    result = broker_crypto_sim.simulate_fill(
        "BTC/USDT", "buy", 0.01, 65000.0, "crypto_major"
    )
    expected_price = 65000.0 * (1 + SLIPPAGE_PCT["crypto_major"] / 100)
    expected_fee = FEE_TABLE["crypto_major"]["rate"] * 0.01 * expected_price
    assert result["fill_price"] == pytest.approx(expected_price)
    assert result["fee"] == pytest.approx(expected_fee)
    assert result["qty"] == 0.01


def test_simulate_fill_sell_side_applies_worse_price():
    buy_result = broker_crypto_sim.simulate_fill("BTC/USDT", "buy", 1.0, 100.0, "crypto_major")
    sell_result = broker_crypto_sim.simulate_fill("BTC/USDT", "sell", 1.0, 100.0, "crypto_major")
    assert sell_result["fill_price"] < 100.0
    assert buy_result["fill_price"] > 100.0


def test_simulate_fill_unknown_asset_class_raises_keyerror():
    with pytest.raises(KeyError):
        broker_crypto_sim.simulate_fill("XYZ/USDT", "buy", 1.0, 100.0, "unknown_class")


def test_simulate_fill_never_imports_or_calls_order_placement():
    source = BROKER_CRYPTO_SIM_SOURCE_PATH.read_text().lower()
    assert "createorder" not in source
    assert "placeorder" not in source


# ---------------------------------------------------------------------------
# kraken_balance_check -- read-only, optional, never a hard blocker (D-04)
# ---------------------------------------------------------------------------


def test_kraken_balance_check_returns_none_when_key_unset(monkeypatch):
    monkeypatch.delenv("KRAKEN_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_API_SECRET", raising=False)
    assert broker_crypto_sim.kraken_balance_check() is None


def test_kraken_balance_check_returns_none_when_only_secret_set(monkeypatch):
    monkeypatch.delenv("KRAKEN_API_KEY", raising=False)
    monkeypatch.setenv("KRAKEN_API_SECRET", "secret-value")
    assert broker_crypto_sim.kraken_balance_check() is None


def test_kraken_balance_check_calls_fetch_balance_when_both_credentials_present():
    fake_kraken = _FakeKrakenClient(balance={"USD": {"free": 100.0}})
    result = broker_crypto_sim.kraken_balance_check(
        api_key="key", api_secret="secret", client=fake_kraken
    )
    assert result == {"USD": {"free": 100.0}}
    assert fake_kraken.fetch_balance_called is True


def test_kraken_balance_check_falls_back_to_env_vars(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "env-key")
    monkeypatch.setenv("KRAKEN_API_SECRET", "env-secret")
    fake_kraken = _FakeKrakenClient(balance={"USD": {"free": 5.0}})
    result = broker_crypto_sim.kraken_balance_check(client=fake_kraken)
    assert result == {"USD": {"free": 5.0}}
