"""Tests for trader.ground_truth.poll — the one-shot polling entrypoint (D-05/D-07).

Wires StockGainersSource and CryptoMoversSource (Plan 00-02) into db.py's
insert_snapshot_rows/record_poll_run (Plan 00-02). A missed source must never
block the other from being written (D-06).
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from trader.ground_truth import db
from trader.ground_truth.poll import is_market_hours, main, run_poll_once
from trader.ground_truth.sources import SourceUnavailableError


def _stock_rows(n=3):
    return [
        {
            "ticker": f"S{i}",
            "price": 10.0 + i,
            "pct_gain": 5.0 + i,
            "rank": i + 1,
            "source": "stock",
        }
        for i in range(n)
    ]


def _crypto_rows(n=3):
    return [
        {
            "ticker": f"C{i}",
            "coingecko_id": f"coin-{i}",
            "price": 1.0 + i,
            "pct_gain": 3.0 + i,
            "rank": i + 1,
            "source": "crypto",
        }
        for i in range(n)
    ]


def test_run_poll_once_calls_both_sources_and_inserts_rows(tmp_db_path):
    with (
        patch(
            "trader.ground_truth.poll.StockGainersSource.fetch_top_movers",
            return_value=_stock_rows(3),
        ) as mock_stock,
        patch(
            "trader.ground_truth.poll.CryptoMoversSource.fetch_top_movers",
            return_value=_crypto_rows(3),
        ) as mock_crypto,
    ):
        summary = run_poll_once(tmp_db_path)

    assert summary["stock_rows"] == 3
    assert summary["crypto_rows"] == 3
    mock_stock.assert_called_once()
    mock_crypto.assert_called_once()


def test_run_poll_once_continues_when_stock_source_raises(tmp_db_path):
    with (
        patch(
            "trader.ground_truth.poll.StockGainersSource.fetch_top_movers",
            side_effect=SourceUnavailableError("boom"),
        ),
        patch(
            "trader.ground_truth.poll.CryptoMoversSource.fetch_top_movers",
            return_value=_crypto_rows(3),
        ),
    ):
        summary = run_poll_once(tmp_db_path)

    assert summary["stock_success"] is False
    assert summary["crypto_success"] is True
    assert summary["crypto_rows"] == 3

    conn = db.get_connection(tmp_db_path)
    row = conn.execute("SELECT stock_success, crypto_success FROM poll_runs").fetchone()
    conn.close()
    assert row == (0, 1)


def test_is_market_hours_true_during_nyse_session():
    # 2026-07-27 14:30 UTC == 10:30am US/Eastern on a Monday.
    assert is_market_hours(datetime(2026, 7, 27, 14, 30, tzinfo=timezone.utc)) is True


def test_is_market_hours_false_on_weekend():
    # 2026-07-25 is a Saturday.
    assert is_market_hours(datetime(2026, 7, 25, 14, 30, tzinfo=timezone.utc)) is False


def test_crypto_rows_always_market_open_true(tmp_db_path):
    with (
        patch(
            "trader.ground_truth.poll.StockGainersSource.fetch_top_movers",
            return_value=_stock_rows(2),
        ),
        patch(
            "trader.ground_truth.poll.CryptoMoversSource.fetch_top_movers",
            return_value=_crypto_rows(2),
        ),
        patch("trader.ground_truth.poll.is_market_hours", return_value=False),
    ):
        run_poll_once(tmp_db_path)

    conn = db.get_connection(tmp_db_path)
    crypto_flags = [
        row[0]
        for row in conn.execute(
            "SELECT market_open FROM snapshots WHERE source = 'crypto'"
        ).fetchall()
    ]
    stock_flags = [
        row[0]
        for row in conn.execute(
            "SELECT market_open FROM snapshots WHERE source = 'stock'"
        ).fetchall()
    ]
    conn.close()

    # Crypto never closes: market_open is always 1, regardless of the
    # stock-side is_market_hours() result (Open Question 3).
    assert crypto_flags == [1, 1]
    assert stock_flags == [0, 0]


def test_once_flag_runs_exactly_one_poll():
    with patch("trader.ground_truth.poll.run_poll_once") as mock_run:
        mock_run.return_value = {
            "stock_rows": 0,
            "crypto_rows": 0,
            "stock_success": True,
            "crypto_success": True,
        }
        main(["--once"])
    mock_run.assert_called_once()


def test_main_without_once_flag_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "--once" in captured.err
