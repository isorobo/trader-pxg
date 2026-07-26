"""Tests for trader.data.classify — CoinGecko-categories classification and the
register_crypto_instrument onboarding function (D-16).
"""

from unittest.mock import patch

import pytest
import requests

from trader.data import db

try:
    from trader.data import classify
except ImportError:
    # trader.data.classify does not exist yet (RED phase) — collection must still
    # succeed so all tests are collected; each test then fails with an
    # AttributeError on `classify` (None) when it tries to call into the contract.
    classify = None


def _mock_response(json_data, raise_error=None):
    """Build a stand-in for requests.Response with the bits classify.py uses."""

    class _FakeResponse:
        def raise_for_status(self):
            if raise_error is not None:
                raise raise_error

        def json(self):
            return json_data

    return _FakeResponse()


def test_classify_memecoin_from_categories():
    fake_response = _mock_response({"categories": ["Meme", "Dog-Themed"]})
    with patch("trader.data.classify.requests.get", return_value=fake_response):
        result = classify.classify_crypto_instrument("dogecoin", "fake-key")
    assert result == "memecoin"


def test_classify_crypto_major_when_no_meme_category():
    fake_response = _mock_response({"categories": ["Smart Contract Platform"]})
    with patch("trader.data.classify.requests.get", return_value=fake_response):
        result = classify.classify_crypto_instrument("bitcoin", "fake-key")
    assert result == "crypto_major"


def test_classify_sends_authenticated_header():
    fake_response = _mock_response({"categories": []})
    with patch(
        "trader.data.classify.requests.get", return_value=fake_response
    ) as mock_get:
        classify.classify_crypto_instrument("bitcoin", "fake-key")
    _, kwargs = mock_get.call_args
    assert kwargs["headers"] == {"x-cg-demo-api-key": "fake-key"}


def test_classify_raises_on_http_error():
    fake_response = _mock_response(
        {}, raise_error=requests.HTTPError("429 Client Error")
    )
    with patch("trader.data.classify.requests.get", return_value=fake_response):
        with pytest.raises(requests.HTTPError):
            classify.classify_crypto_instrument("bitcoin", "fake-key")


def test_classify_handles_missing_categories_key():
    fake_response = _mock_response({})
    with patch("trader.data.classify.requests.get", return_value=fake_response):
        result = classify.classify_crypto_instrument("bitcoin", "fake-key")
    assert result == "crypto_major"


@pytest.fixture
def data_conn(tmp_db_path):
    """A live connection to a fresh temp DB, bootstrapped via trader.data.db."""
    connection = db.get_connection(tmp_db_path)
    yield connection
    connection.close()


def test_register_crypto_instrument_classifies_and_persists(data_conn):
    with patch(
        "trader.data.classify.classify_crypto_instrument", return_value="memecoin"
    ) as mock_classify:
        result = classify.register_crypto_instrument(
            data_conn, "DOGE/USDT", "binance", "dogecoin"
        )

    mock_classify.assert_called_once()
    call_args = mock_classify.call_args[0]
    assert call_args[0] == "dogecoin"

    assert result == "memecoin"
    instrument = db.get_instrument(data_conn, "DOGE/USDT", "binance")
    assert instrument is not None
    assert instrument["asset_class"] == "memecoin"
    assert instrument["coingecko_id"] == "dogecoin"


def test_register_crypto_instrument_override_skips_classification(data_conn):
    with patch(
        "trader.data.classify.classify_crypto_instrument",
        side_effect=AssertionError("classify_crypto_instrument should not be called"),
    ):
        result = classify.register_crypto_instrument(
            data_conn, "XYZ/USDT", "binance", "some-id", override="crypto_major"
        )

    assert result == "crypto_major"
    instrument = db.get_instrument(data_conn, "XYZ/USDT", "binance")
    assert instrument is not None
    assert instrument["asset_class"] == "crypto_major"
    assert instrument["override"] == "crypto_major"


def test_register_crypto_instrument_is_idempotent(data_conn):
    with patch(
        "trader.data.classify.classify_crypto_instrument", return_value="memecoin"
    ):
        classify.register_crypto_instrument(data_conn, "DOGE/USDT", "binance", "dogecoin")
        classify.register_crypto_instrument(data_conn, "DOGE/USDT", "binance", "dogecoin")

    rows = data_conn.execute(
        "SELECT COUNT(*) FROM instruments WHERE symbol = ? AND venue = ?",
        ("DOGE/USDT", "binance"),
    ).fetchone()
    assert rows[0] == 1
