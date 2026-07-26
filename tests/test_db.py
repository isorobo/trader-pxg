"""Tests for trader.ground_truth.db — snapshot schema, inserts, and coverage queries."""

from datetime import datetime, timedelta, timezone

from trader.ground_truth import db


def test_get_connection_sets_wal_and_busy_timeout(conn):
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert journal_mode.lower() == "wal"
    assert busy_timeout == 5000


def test_ensure_schema_creates_three_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {row[0] for row in rows}
    assert "snapshots" in table_names
    assert "poll_runs" in table_names
    assert "schema_version" in table_names


def test_insert_snapshot_rows_persists_all_fields(conn):
    stock_row = {
        "poll_ts": "2026-07-26T10:00:00+00:00",
        "source": "stock",
        "ticker": "AAPL",
        "coingecko_id": None,
        "price": 210.50,
        "pct_gain": 12.3,
        "rank": 1,
        "market_open": 1,
    }
    crypto_row = {
        "poll_ts": "2026-07-26T10:00:00+00:00",
        "source": "crypto",
        "ticker": "BTC",
        "coingecko_id": "bitcoin",
        "price": 65000.0,
        "pct_gain": 5.5,
        "rank": 1,
        "market_open": 1,
    }
    db.insert_snapshot_rows(conn, [stock_row, crypto_row])

    persisted = conn.execute(
        "SELECT poll_ts, source, ticker, coingecko_id, price, pct_gain, rank, market_open "
        "FROM snapshots ORDER BY ticker"
    ).fetchall()

    assert len(persisted) == 2

    aapl = persisted[0]
    assert aapl[0] == stock_row["poll_ts"]
    assert aapl[1] == stock_row["source"]
    assert aapl[2] == stock_row["ticker"]
    assert aapl[3] == stock_row["coingecko_id"]
    assert aapl[4] == stock_row["price"]
    assert aapl[5] == stock_row["pct_gain"]
    assert aapl[6] == stock_row["rank"]
    assert aapl[7] == stock_row["market_open"]

    btc = persisted[1]
    assert btc[0] == crypto_row["poll_ts"]
    assert btc[1] == crypto_row["source"]
    assert btc[2] == crypto_row["ticker"]
    assert btc[3] == crypto_row["coingecko_id"]
    assert btc[4] == crypto_row["price"]
    assert btc[5] == crypto_row["pct_gain"]
    assert btc[6] == crypto_row["rank"]
    assert btc[7] == crypto_row["market_open"]


def test_record_poll_run_and_query_coverage(conn):
    now = datetime.now(timezone.utc)
    poll_timestamps = [now - timedelta(minutes=15 * i) for i in range(4)]

    for ts in poll_timestamps:
        db.record_poll_run(
            conn,
            poll_ts=ts.isoformat(),
            stock_success=1,
            crypto_success=1,
            stock_row_count=50,
            crypto_row_count=50,
        )

    since_ts = (now - timedelta(hours=1)).isoformat()
    coverage = db.query_poll_run_coverage(conn, since_ts=since_ts, now=now)

    assert coverage == {"completed": 4, "expected": 4, "pct": 100.0}


def test_query_flagged_tickers_since_returns_pinned_keys_and_first_seen(conn):
    earlier_ts = "2026-07-26T09:00:00+00:00"
    later_ts = "2026-07-26T09:15:00+00:00"

    db.insert_snapshot_rows(
        conn,
        [
            {
                "poll_ts": earlier_ts,
                "source": "stock",
                "ticker": "AAPL",
                "coingecko_id": None,
                "price": 200.0,
                "pct_gain": 10.0,
                "rank": 1,
                "market_open": 1,
            },
            {
                "poll_ts": later_ts,
                "source": "stock",
                "ticker": "AAPL",
                "coingecko_id": None,
                "price": 220.0,
                "pct_gain": 15.0,
                "rank": 2,
                "market_open": 1,
            },
        ],
    )

    since_ts = "2026-07-26T00:00:00+00:00"
    rows = db.query_flagged_tickers_since(conn, since_ts=since_ts)

    assert len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == {
        "source",
        "ticker",
        "coingecko_id",
        "first_seen_ts",
        "first_price",
        "first_pct_gain",
    }
    assert row["source"] == "stock"
    assert row["ticker"] == "AAPL"
    assert row["coingecko_id"] is None
    assert row["first_seen_ts"] == earlier_ts
    assert row["first_price"] == 200.0
    assert row["first_pct_gain"] == 10.0
