"""SQLite connection, migration runner, and instruments/bars cache helpers.

Shares data/trader.db with Phase 0's trader/ground_truth/db.py (see
01-CONTEXT.md D-07/D-08/D-09). Schema creation here goes through
apply_migrations, reading ordered *.sql files from migrations/, rather than a
hardcoded ensure_schema — this is Phase 1's D-09 migration mechanism, which
Phase 0's snapshots/poll_runs/schema_version DDL is retrofitted into as
migrations/0001_ground_truth.sql.
"""

import re
import sqlite3
from pathlib import Path

_MIGRATION_FILENAME_RE = re.compile(r"^(\d{4})_")


def get_connection(db_path: str = "data/trader.db") -> sqlite3.Connection:
    """Open a WAL-mode connection to db_path and apply any pending migrations."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    apply_migrations(conn, migrations_dir="migrations")
    return conn


def apply_migrations(conn: sqlite3.Connection, migrations_dir: str = "migrations") -> None:
    """Apply any *.sql files under migrations_dir not yet recorded in schema_version.

    Files are sorted by filename; each filename's leading 4-digit number is its
    version. Already-applied versions are skipped. Applying a migration runs its
    full script and records the version with an applied_at timestamp, all inside
    one short transaction per file.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()

    applied_versions = {
        row[0] for row in conn.execute("SELECT version FROM schema_version").fetchall()
    }

    migration_files = sorted(Path(migrations_dir).glob("*.sql"), key=lambda p: p.name)
    for migration_file in migration_files:
        match = _MIGRATION_FILENAME_RE.match(migration_file.name)
        if not match:
            continue
        version = int(match.group(1))
        if version in applied_versions:
            continue

        conn.executescript(migration_file.read_text())
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
        conn.commit()
        applied_versions.add(version)


def upsert_instrument(
    conn: sqlite3.Connection,
    symbol: str,
    venue: str,
    asset_class: str,
    coingecko_id: str | None = None,
    override: str | None = None,
) -> None:
    """Idempotently register or update an instrument (parameterized, ASVS V5)."""
    conn.execute(
        """
        INSERT INTO instruments (symbol, venue, asset_class, coingecko_id, override)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(symbol, venue) DO UPDATE SET
            asset_class = excluded.asset_class,
            coingecko_id = excluded.coingecko_id,
            override = excluded.override
        """,
        (symbol, venue, asset_class, coingecko_id, override),
    )
    conn.commit()


def get_instrument(conn: sqlite3.Connection, symbol: str, venue: str) -> dict | None:
    """Return {symbol, venue, asset_class, coingecko_id, override} or None."""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    row = cursor.execute(
        "SELECT symbol, venue, asset_class, coingecko_id, override "
        "FROM instruments WHERE symbol = ? AND venue = ?",
        (symbol, venue),
    ).fetchone()
    if row is None:
        return None
    return {
        "symbol": row["symbol"],
        "venue": row["venue"],
        "asset_class": row["asset_class"],
        "coingecko_id": row["coingecko_id"],
        "override": row["override"],
    }


def read_bars_cache(
    conn: sqlite3.Connection,
    venue: str,
    symbol: str,
    timeframe: str,
    start: str | None = None,
    end: str | None = None,
) -> list[dict]:
    """Return cached bars as dicts with keys ts/open/high/low/close/volume, ts ascending."""
    query = (
        "SELECT ts, o, h, l, c, volume FROM bars "
        "WHERE venue = ? AND symbol = ? AND timeframe = ?"
    )
    params: list = [venue, symbol, timeframe]

    if start is not None:
        query += " AND ts >= ?"
        params.append(start)
    if end is not None:
        query += " AND ts <= ?"
        params.append(end)

    query += " ORDER BY ts ASC"

    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    rows = cursor.execute(query, params).fetchall()
    return [
        {
            "ts": row["ts"],
            "open": row["o"],
            "high": row["h"],
            "low": row["l"],
            "close": row["c"],
            "volume": row["volume"],
        }
        for row in rows
    ]


def write_bars_cache(
    conn: sqlite3.Connection,
    venue: str,
    symbol: str,
    timeframe: str,
    rows: list[dict],
) -> int:
    """Insert bar rows, silently ignoring duplicates on (venue, symbol, timeframe, ts).

    rows are shaped {"ts", "open", "high", "low", "close", "volume"}. Parameterized
    placeholders only — never string-interpolated SQL (ASVS V5, matches
    trader/ground_truth/db.py's established convention).
    """
    query = (
        "INSERT OR IGNORE INTO bars (venue, symbol, timeframe, ts, o, h, l, c, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    values = [
        (
            venue,
            symbol,
            timeframe,
            row["ts"],
            row["open"],
            row["high"],
            row["low"],
            row["close"],
            row["volume"],
        )
        for row in rows
    ]
    cursor = conn.executemany(query, values)
    conn.commit()
    return cursor.rowcount
