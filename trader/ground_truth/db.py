"""SQLite connection, schema, and query helpers for the ground-truth snapshot logger.

Shares data/trader.db with Phase 1 (see 01-CONTEXT.md D-07/D-08/D-09). Phase 0 owns the
`snapshots` and `poll_runs` table schemas defined here; Phase 1's bootstrap must not
conflict with them.
"""

import sqlite3
from datetime import datetime, timedelta, timezone


def get_connection(db_path: str = "data/trader.db") -> sqlite3.Connection:
    """Open a WAL-mode connection to db_path and ensure the schema exists."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the snapshots, poll_runs, and schema_version tables if absent."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_ts TEXT NOT NULL,
            source TEXT NOT NULL,
            ticker TEXT NOT NULL,
            coingecko_id TEXT,
            price REAL NOT NULL,
            pct_gain REAL NOT NULL,
            rank INTEGER NOT NULL,
            market_open INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS poll_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_ts TEXT NOT NULL,
            stock_success INTEGER NOT NULL,
            crypto_success INTEGER NOT NULL,
            stock_row_count INTEGER NOT NULL,
            crypto_row_count INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (1, datetime('now'))"
    )
    conn.commit()


def insert_snapshot_rows(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Insert snapshot rows using parameterized placeholders only (ASVS V5)."""
    query = (
        "INSERT INTO snapshots "
        "(poll_ts, source, ticker, coingecko_id, price, pct_gain, rank, market_open) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    )
    values = [
        (
            row["poll_ts"],
            row["source"],
            row["ticker"],
            row.get("coingecko_id"),
            row["price"],
            row["pct_gain"],
            row["rank"],
            row["market_open"],
        )
        for row in rows
    ]
    cursor = conn.executemany(query, values)
    conn.commit()
    return cursor.rowcount


def record_poll_run(
    conn: sqlite3.Connection,
    poll_ts: str,
    stock_success: int,
    crypto_success: int,
    stock_row_count: int,
    crypto_row_count: int,
) -> None:
    """Record one poll run's outcome for later coverage-stat reporting."""
    conn.execute(
        "INSERT INTO poll_runs "
        "(poll_ts, stock_success, crypto_success, stock_row_count, crypto_row_count) "
        "VALUES (?, ?, ?, ?, ?)",
        (poll_ts, stock_success, crypto_success, stock_row_count, crypto_row_count),
    )
    conn.commit()


def query_flagged_tickers_since(conn: sqlite3.Connection, since_ts: str) -> list[dict]:
    """Return one row per distinct (source, ticker, coingecko_id) seen since since_ts.

    Pinned contract for Plan 00-04's report.py: each returned dict has exactly these
    keys — source, ticker, coingecko_id, first_seen_ts, first_price, first_pct_gain —
    where first_* values come from the earliest poll_ts for that ticker, never the
    latest.
    """
    query = """
        SELECT s.source AS source,
               s.ticker AS ticker,
               s.coingecko_id AS coingecko_id,
               s.poll_ts AS first_seen_ts,
               s.price AS first_price,
               s.pct_gain AS first_pct_gain
        FROM snapshots s
        INNER JOIN (
            SELECT source, ticker, coingecko_id, MIN(poll_ts) AS min_ts
            FROM snapshots
            WHERE poll_ts >= ?
            GROUP BY source, ticker, coingecko_id
        ) grouped
        ON s.source = grouped.source
           AND s.ticker = grouped.ticker
           AND (s.coingecko_id IS grouped.coingecko_id)
           AND s.poll_ts = grouped.min_ts
        WHERE s.poll_ts >= ?
    """
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    result_rows = cursor.execute(query, (since_ts, since_ts)).fetchall()
    return [
        {
            "source": row["source"],
            "ticker": row["ticker"],
            "coingecko_id": row["coingecko_id"],
            "first_seen_ts": row["first_seen_ts"],
            "first_price": row["first_price"],
            "first_pct_gain": row["first_pct_gain"],
        }
        for row in result_rows
    ]


def query_poll_run_coverage(
    conn: sqlite3.Connection, since_ts: str, now: datetime | None = None
) -> dict:
    """Return {"completed", "expected", "pct"} coverage stats for polls since since_ts.

    now defaults to datetime.now(timezone.utc) so production call sites never need to
    pass it; tests pin it explicitly to remove any wall-clock dependency.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    since_dt = datetime.fromisoformat(since_ts)
    if since_dt.tzinfo is None:
        since_dt = since_dt.replace(tzinfo=timezone.utc)

    expected = int((now - since_dt) // timedelta(minutes=15))
    completed = conn.execute(
        "SELECT COUNT(*) FROM poll_runs WHERE poll_ts >= ?", (since_ts,)
    ).fetchone()[0]
    pct = (completed / expected * 100.0) if expected > 0 else 0.0

    return {"completed": completed, "expected": expected, "pct": pct}
