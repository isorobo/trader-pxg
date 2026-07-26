"""Tests for trader.data.classify — CoinGecko-categories classification and the
register_crypto_instrument onboarding function (D-16).
"""

from unittest.mock import patch

import pytest
import requests

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
