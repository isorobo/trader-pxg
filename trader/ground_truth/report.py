"""Daily report generator for the ground-truth snapshot logger (D-10/D-11/D-12).

Reads snapshot rows written by the poller and answers the phase's exit-criterion
question directly: of everything flagged this week, what % ended the day up vs
dumped from where the scanner first saw it?

D-11: closes are fetched directly via yfinance/CoinGecko until Phase 1's
get_daily_bars exists — migrating to that API is a noted follow-up, not a Phase 0
blocker.
"""

import argparse
import logging
import os
from datetime import date, datetime, timedelta, timezone

import requests
import yfinance
from dotenv import load_dotenv

from trader.ground_truth import db

log = logging.getLogger(__name__)

COINGECKO_HISTORY_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/history"


def format_coingecko_date(d: date) -> str:
    """Format d as DD-MM-YYYY — the format CoinGecko's history endpoint requires.

    Pitfall 6 (00-RESEARCH.md): passing ISO format here silently returns the
    wrong day or an error response.
    """
    return d.strftime("%d-%m-%Y")


def fetch_stock_close(symbol: str, on_date: date) -> float | None:
    """Fetch symbol's close price on on_date via yfinance, or None if unavailable."""
    hist = yfinance.Ticker(symbol).history(
        start=on_date.isoformat(),
        end=(on_date + timedelta(days=1)).isoformat(),
    )
    if hist.empty:
        return None
    return float(hist["Close"].iloc[0])


def fetch_crypto_close(coingecko_id: str, on_date: date, api_key: str) -> float | None:
    """Fetch coingecko_id's close price on on_date via CoinGecko history.

    Returns None on a missing price or any error response — the report must
    never crash on a single ticker's failed lookup.
    """
    try:
        response = requests.get(
            COINGECKO_HISTORY_URL.format(coin_id=coingecko_id),
            params={"date": format_coingecko_date(on_date), "localization": "false"},
            headers={"x-cg-demo-api-key": api_key},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        # Never log the API key itself (T-00-08) — log the failure only.
        log.warning(
            "CoinGecko history call failed for %s (%s: %s)",
            coingecko_id,
            type(error).__name__,
            error,
        )
        return None

    market_data = data.get("market_data") or {}
    current_price = market_data.get("current_price") or {}
    return current_price.get("usd")


def _pct_return(first_price: float, close: float | None) -> float | None:
    if close is None:
        return None
    return (close - first_price) / first_price * 100


def compute_report_rows(conn, week_start: date) -> list[dict]:
    """Join flagged tickers since week_start with same-day/next-day closes.

    Returns an empty list without raising when zero snapshots exist yet
    (pre-collection empty state).
    """
    flagged = db.query_flagged_tickers_since(conn, week_start.isoformat())
    if not flagged:
        return []

    load_dotenv()
    api_key = os.environ.get("COINGECKO_API_KEY", "")

    rows = []
    for flag in flagged:
        first_seen_ts = flag["first_seen_ts"]
        flag_date = datetime.fromisoformat(first_seen_ts).date()
        next_date = flag_date + timedelta(days=1)

        if flag["source"] == "crypto":
            same_day_close = fetch_crypto_close(flag["coingecko_id"], flag_date, api_key)
            next_day_close = fetch_crypto_close(flag["coingecko_id"], next_date, api_key)
        else:
            same_day_close = fetch_stock_close(flag["ticker"], flag_date)
            next_day_close = fetch_stock_close(flag["ticker"], next_date)

        first_price = flag["first_price"]
        rows.append(
            {
                "source": flag["source"],
                "ticker": flag["ticker"],
                "first_seen_ts": first_seen_ts,
                "first_price": first_price,
                "first_pct_gain": flag["first_pct_gain"],
                "same_day_close": same_day_close,
                "next_day_close": next_day_close,
                "pct_return_same_day": _pct_return(first_price, same_day_close),
                "pct_return_next_day": _pct_return(first_price, next_day_close),
            }
        )
    return rows


def compute_coverage_stat(conn, week_start: date) -> dict:
    """Delegate directly to db.query_poll_run_coverage (D-06)."""
    return db.query_poll_run_coverage(conn, week_start.isoformat())


def _fmt(value) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def write_report_markdown(rows: list[dict], coverage: dict, out_path: str) -> None:
    """Write the dated markdown report: table, coverage stat, up/down summary.

    The summary line directly answers the phase's exit-criterion sentence: of
    everything flagged this week, what % ended the day up vs dumped from where
    the scanner first saw it.
    """
    up_count = sum(1 for row in rows if (row["pct_return_same_day"] or 0) > 0)
    down_count = len(rows) - up_count if rows else 0

    lines = [
        "# Ground Truth Daily Report",
        "",
        (
            "| Ticker | First Seen | First Price | First % Gain | Same-Day Close "
            "| Next-Day Close | Return (Same-Day) | Return (Next-Day) |"
        ),
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {ticker} | {first_seen_ts} | {first_price} | {first_pct_gain} | "
            "{same_day_close} | {next_day_close} | {pct_return_same_day} | "
            "{pct_return_next_day} |".format(
                ticker=row["ticker"],
                first_seen_ts=row["first_seen_ts"],
                first_price=_fmt(row["first_price"]),
                first_pct_gain=_fmt(row["first_pct_gain"]),
                same_day_close=_fmt(row["same_day_close"]),
                next_day_close=_fmt(row["next_day_close"]),
                pct_return_same_day=_fmt(row["pct_return_same_day"]),
                pct_return_next_day=_fmt(row["pct_return_next_day"]),
            )
        )

    lines.append("")
    lines.append(
        "Coverage: {completed}/{expected} polls ({pct:.1f}%)".format(**coverage)
    )
    lines.append("")
    if rows:
        lines.append(
            f"Of {len(rows)} tickers flagged, {up_count} ended the day up and "
            f"{down_count} dumped from where the scanner first saw them."
        )
    else:
        lines.append("0 tickers flagged in this window — no snapshots collected yet.")

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None) -> None:
    """CLI entry point: python -m trader.ground_truth.report [--date YYYY-MM-DD]."""
    parser = argparse.ArgumentParser(
        description="Generate the daily ground-truth report (D-12)."
    )
    parser.add_argument(
        "--date", type=str, default=None, help="YYYY-MM-DD, defaults to today"
    )
    args = parser.parse_args(argv)

    if args.date:
        parsed_date = (
            datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc).date()
        )
    else:
        parsed_date = datetime.now(timezone.utc).date()
    week_start = parsed_date - timedelta(days=7)

    os.makedirs("data", exist_ok=True)
    conn = db.get_connection("data/trader.db")
    try:
        rows = compute_report_rows(conn, week_start)
        coverage = compute_coverage_stat(conn, week_start)
    finally:
        conn.close()

    out_path = os.path.join("reports", f"{parsed_date.isoformat()}.md")
    write_report_markdown(rows, coverage, out_path)

    up_count = sum(1 for row in rows if (row["pct_return_same_day"] or 0) > 0)
    down_count = len(rows) - up_count if rows else 0
    print(f"Ground truth report written to {out_path}")
    print(f"Tickers flagged: {len(rows)}")
    print(
        "Coverage: {completed}/{expected} polls ({pct:.1f}%)".format(**coverage)
    )
    if rows:
        print(f"Up: {up_count}  Down: {down_count}")


if __name__ == "__main__":
    main()
