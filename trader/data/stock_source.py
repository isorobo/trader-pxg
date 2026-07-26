"""yfinance stock daily bar fetch and UTC-date normalization.

yfinance returns a tz-aware index localised to the exchange's home timezone
(America/New_York for US equities), not UTC (01-RESEARCH.md Pitfall 1).
normalize_stock_bars converts that index to a plain UTC calendar-date string
before any row reaches trader/data/db.py's write_bars_cache, matching its
{"ts", "open", "high", "low", "close", "volume"} row contract exactly.
"""

import pandas as pd
import yfinance

_EXPECTED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
_COLUMN_RENAME = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
}


def normalize_stock_bars(df: pd.DataFrame) -> list[dict]:
    """Convert a tz-aware yfinance DataFrame into ts/open/high/low/close/volume rows.

    df.index is converted to UTC and reduced to a plain YYYY-MM-DD date string —
    daily bars have no meaningful intraday component. Dividends and Stock Splits
    columns (if present) are dropped. Raises ValueError, not a bare KeyError, if
    an expected OHLCV column is missing.
    """
    missing = [column for column in _EXPECTED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(
            f"stock bars DataFrame missing expected column(s): {', '.join(missing)}"
        )

    normalized = df.copy()
    normalized["ts"] = normalized.index.tz_convert("UTC").strftime("%Y-%m-%d")
    normalized = normalized[["ts", *_EXPECTED_COLUMNS]].rename(columns=_COLUMN_RENAME)
    return normalized.to_dict(orient="records")


def fetch_stock_bars(
    symbol: str, start: str | None = None, end: str | None = None
) -> list[dict]:
    """Fetch daily bars for symbol via yfinance and normalize them.

    With no start given, requests the fully available history (period="max"),
    not a truncated default window.
    """
    ticker = yfinance.Ticker(symbol)
    if start is None:
        df = ticker.history(period="max", auto_adjust=True)
    else:
        df = ticker.history(start=start, end=end, auto_adjust=True)
    return normalize_stock_bars(df)
