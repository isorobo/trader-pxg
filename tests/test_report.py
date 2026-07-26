"""Tests for trader.ground_truth.report — daily report generator (D-10/D-11/D-12)."""

from datetime import date
from unittest.mock import patch

import pandas as pd

from trader.ground_truth import db, report


def test_format_coingecko_date_returns_dd_mm_yyyy():
    assert report.format_coingecko_date(date(2026, 7, 26)) == "26-07-2026"


def test_fetch_stock_close_uses_one_day_window():
    mock_history = pd.DataFrame({"Close": [123.45]})
    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.history.return_value = mock_history
        result = report.fetch_stock_close("AAA", date(2026, 7, 26))

    mock_ticker_cls.assert_called_once_with("AAA")
    mock_ticker_cls.return_value.history.assert_called_once_with(
        start="2026-07-26", end="2026-07-27"
    )
    assert result == 123.45


def test_fetch_crypto_close_uses_ddmmyyyy_param():
    mock_response_json = {"market_data": {"current_price": {"usd": 65000.0}}}
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_response_json
        mock_get.return_value.raise_for_status.return_value = None
        result = report.fetch_crypto_close("bitcoin", date(2026, 7, 26), api_key="testkey")

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["date"] == "26-07-2026"
    assert result == 65000.0


def test_compute_report_rows_joins_snapshot_and_closes(conn):
    week_start = date(2026, 7, 19)
    poll_ts = "2026-07-26T09:15:00+00:00"
    db.insert_snapshot_rows(
        conn,
        [
            {
                "poll_ts": poll_ts,
                "source": "stock",
                "ticker": "AAA",
                "coingecko_id": None,
                "price": 100.0,
                "pct_gain": 10.0,
                "rank": 1,
                "market_open": 1,
            },
            {
                "poll_ts": poll_ts,
                "source": "crypto",
                "ticker": "BTC",
                "coingecko_id": "bitcoin",
                "price": 65000.0,
                "pct_gain": 5.0,
                "rank": 1,
                "market_open": 1,
            },
        ],
    )

    with patch.object(report, "fetch_stock_close", return_value=110.0), patch.object(
        report, "fetch_crypto_close", return_value=68000.0
    ):
        rows = report.compute_report_rows(conn, week_start)

    assert len(rows) == 2
    for row in rows:
        assert "first_seen_ts" in row
        assert "first_price" in row
        assert "first_pct_gain" in row
        assert "same_day_close" in row
        assert "next_day_close" in row
        assert "pct_return_same_day" in row
        assert "pct_return_next_day" in row


def test_compute_coverage_stat_matches_db_query(conn):
    week_start = date(2026, 7, 19)
    with patch.object(
        db,
        "query_poll_run_coverage",
        return_value={"completed": 4, "expected": 8, "pct": 50.0},
    ) as mock_query:
        result = report.compute_coverage_stat(conn, week_start)

    mock_query.assert_called_once_with(conn, week_start.isoformat())
    assert result == {"completed": 4, "expected": 8, "pct": 50.0}


def test_write_report_markdown_creates_dated_file(tmp_path):
    rows = [
        {
            "source": "stock",
            "ticker": "AAA",
            "first_seen_ts": "2026-07-26T09:15:00+00:00",
            "first_price": 100.0,
            "first_pct_gain": 10.0,
            "same_day_close": 110.0,
            "next_day_close": 108.0,
            "pct_return_same_day": 10.0,
            "pct_return_next_day": 8.0,
        }
    ]
    coverage = {"completed": 4, "expected": 8, "pct": 50.0}
    out_path = tmp_path / "2026-07-26.md"

    report.write_report_markdown(rows, coverage, str(out_path))

    content = out_path.read_text(encoding="utf-8")
    assert "Ticker" in content
    assert "50.0" in content


def test_compute_report_rows_handles_empty_snapshots(conn):
    week_start = date(2026, 7, 19)
    rows = report.compute_report_rows(conn, week_start)
    assert rows == []
