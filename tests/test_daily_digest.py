"""Daily digest tests: invested/unrealized math, degraded pricing honesty,
fortnight tally, single Telegram send."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trader.backtest.config import EXIT_PROFILE
from trader.paper import daily_digest, ledger

NOW = datetime(2026, 8, 13, 20, 0, tzinfo=timezone.utc)

_PROFILE = EXIT_PROFILE(
    stop_pct=-0.10, tp_pct=None, scale_out=(), trailing_pct=None,
    max_hold_days=None, eod_flat=False,
)


def _open(conn, symbol, qty, price, venue="ibkr_paper"):
    ledger.open_position(
        conn, "strat", symbol, venue, "stock", qty, price,
        "2026-08-01T09:30:00", f"ref-{symbol}", _PROFILE,
    )


def test_digest_reports_invested_unrealized_realized(paper_conn, monkeypatch):
    _open(paper_conn, "AAA", 10.0, 100.0)   # cost 1000
    _open(paper_conn, "BBB", 5.0, 200.0)    # cost 1000
    monkeypatch.setattr(
        daily_digest, "_mark_price",
        lambda s, v: {"AAA": 110.0, "BBB": 190.0}[s],
    )
    paper_conn.execute(
        """
        INSERT INTO paper_trades
            (strategy_id, profile_name, symbol, venue, asset_class, entry_ts,
             entry_price, exit_ts, exit_price, exit_reason, qty, fees,
             slippage_cost, pnl, entry_order_ref, exit_order_ref)
        VALUES ('s', 's', 'CCC', 'ibkr_paper', 'stock', '2026-08-10T10:00:00',
                100.0, '2026-08-12T10:00:00', 105.0, 'take_profit', 10.0, 1.0,
                0.5, 49.0, 'e', 'x')
        """
    )
    paper_conn.commit()

    text = daily_digest.build_digest(paper_conn, now=NOW)

    assert "Invested: $2,000.00 across 2 open position(s)" in text
    assert "Unrealized: +50.00" in text          # +100 on AAA, -50 on BBB
    assert "Realized (all time): +49.00 over 1 closed trade(s)" in text
    assert "Fortnight profitable sells: 1/5" in text


def test_unpriced_symbol_flagged_never_crashes(paper_conn, monkeypatch):
    _open(paper_conn, "AAA", 10.0, 100.0)
    monkeypatch.setattr(daily_digest, "_mark_price", lambda s, v: None)

    text = daily_digest.build_digest(paper_conn, now=NOW)

    assert "Invested: $1,000.00" in text
    assert "Unpriced" in text and "AAA" in text


def test_run_digest_sends_exactly_one_telegram(paper_conn, monkeypatch):
    monkeypatch.setattr(daily_digest, "_mark_price", lambda s, v: 100.0)
    sent = []
    monkeypatch.setattr(daily_digest.alerts, "notify", lambda t, m: sent.append((t, m)))

    daily_digest.run_digest_once(paper_conn)

    assert len(sent) == 1
    assert "Daily P&L digest" in sent[0][1]
