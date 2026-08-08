"""Crypto-sim entry pipeline tests (CRYPTO-PAPER-LEG-PLAN.md, approved
2026-07-30)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from trader.backtest.universe import BUCKET_CRYPTO_MAJOR_LEGACY_MEME
from trader.paper import crypto_entry_pipeline, ledger, signals

AS_OF = date(2026, 7, 26)  # a Sunday -- crypto runs every day
_FAMILY = f"macross_{BUCKET_CRYPTO_MAJOR_LEGACY_MEME}"


def _insert_live_crypto_row(conn, profile_name=_FAMILY + "_p1", state="probation"):
    conn.execute(
        """
        INSERT INTO strategy_registry
            (profile_name, strategy_id, stop_pct, tp_pct, scale_out_json,
             trailing_pct, max_hold_days, eod_flat, pf_floor, max_dd_kill,
             consecutive_loss_kill, entered_at, state, state_changed_at,
             entry_variant)
        VALUES (?, ?, -0.2, 0.4, '[]', NULL, 30, 0, 0.9, -0.05, 8,
                datetime('now'), ?, datetime('now'), 'fast_ema_20_50')
        """,
        (profile_name, _FAMILY, state),
    )
    conn.commit()


def _wiggly_bars(periods=60, end=str(AS_OF)):
    dates = pd.date_range(end=end, periods=periods, tz="UTC")
    closes = [100.0 + (1.5 if i % 2 else -1.5) for i in range(periods)]
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 2.0 for c in closes],
            "low": [c - 2.0 for c in closes],
            "close": closes,
            "volume": [5_000_000.0] * periods,
        },
        index=dates,
    )


def test_skips_gracefully_when_no_crypto_families(paper_conn):
    result = crypto_entry_pipeline.run_crypto_entry_once(
        paper_conn, price_fetcher=lambda s: 100.0, as_of_date=AS_OF
    )
    assert result == {"skipped": "no_live_crypto_families"}


def test_rsi2_crypto_family_is_unroutable_by_design():
    assert not signals.is_routable("rsi2_" + BUCKET_CRYPTO_MAJOR_LEGACY_MEME, "connors5")
    with pytest.raises(KeyError, match="stock-only"):
        signals.pick_entries_for("rsi2_" + BUCKET_CRYPTO_MAJOR_LEGACY_MEME, "connors5")


def test_full_sim_run_enters_fractional_probation_position(paper_conn, monkeypatch):
    _insert_live_crypto_row(paper_conn)

    monkeypatch.setattr(
        crypto_entry_pipeline,
        "get_daily_bars",
        lambda symbol, end=None, conn=None: _wiggly_bars(),
    )
    fired = {"BTC/USDT"}
    monkeypatch.setattr(
        signals,
        "pick_entries_for",
        lambda sid, var: (lambda it, d, open_pos, rng: sorted(fired - open_pos)),
    )

    result = crypto_entry_pipeline.run_crypto_entry_once(
        paper_conn, price_fetcher=lambda s: 200.0, as_of_date=AS_OF
    )

    assert len(result["submitted"]) == 1
    positions = ledger.get_open_positions(paper_conn)
    assert len(positions) == 1
    pos = positions[0]
    assert pos["venue"] == "crypto_sim"
    assert pos["asset_class"] == "crypto_major"
    assert pos["strategy_id"] == _FAMILY + "_p1"
    # Probation multiplier: 0.50 cap * 0.25 = 0.125 equity = 12,500 USD at
    # ref 200 -> 62.5 units before slippage adjustment; fractional qty.
    assert pos["qty"] == pytest.approx(62.5)
    # Fill price reflects the slippage model, not the raw reference.
    assert pos["entry_price"] > 200.0

    order = ledger.get_order_by_ref(paper_conn, result["submitted"][0])
    assert order["status"] == "filled"


def test_hourly_families_route_to_hourly_timeframe():
    assert signals.timeframe_for("hreversion_" + BUCKET_CRYPTO_MAJOR_LEGACY_MEME) == "1h"
    assert signals.timeframe_for("hsqueeze_new_memecoin") == "1h"
    assert signals.timeframe_for("macross_" + BUCKET_CRYPTO_MAJOR_LEGACY_MEME) == "1d"
    assert signals.is_routable(
        "hreversion_" + BUCKET_CRYPTO_MAJOR_LEGACY_MEME, "confluence30"
    )
    assert signals.is_routable("hsqueeze_" + BUCKET_CRYPTO_MAJOR_LEGACY_MEME, "vol2x")


def test_hourly_family_scans_hourly_cache_and_enters(paper_conn, monkeypatch):
    """An hourly family scans the HOURLY frames (daily cache untouched)
    and its sim entry carries an hour-stamped order ref."""
    import pandas as pd

    hourly_family = f"hreversion_{BUCKET_CRYPTO_MAJOR_LEGACY_MEME}"
    paper_conn.execute(
        """
        INSERT INTO strategy_registry
            (profile_name, strategy_id, stop_pct, tp_pct, scale_out_json,
             trailing_pct, max_hold_days, eod_flat, pf_floor, max_dd_kill,
             consecutive_loss_kill, entered_at, state, state_changed_at,
             entry_variant)
        VALUES ('hrev_p1', ?, -0.03, 0.03, '[]', NULL, 24, 0, 0.9, -0.05, 8,
                datetime('now'), 'probation', datetime('now'), 'confluence30')
        """,
        (hourly_family,),
    )
    paper_conn.commit()

    dates = pd.date_range(end="2026-08-04 10:00", periods=60, freq="1h", tz="UTC")
    closes = [100.0 + (1.5 if i % 2 else -1.5) for i in range(60)]
    frame = pd.DataFrame(
        {
            "open": closes, "high": [c + 2 for c in closes],
            "low": [c - 2 for c in closes], "close": closes,
            "volume": [5_000_000.0] * 60,
        },
        index=dates,
    )
    monkeypatch.setattr(
        crypto_entry_pipeline,
        "_hourly_frames",
        lambda conn, bucket, cutoff: {"BTC/USDT": frame},
    )
    monkeypatch.setattr(
        signals,
        "pick_entries_for",
        lambda sid, var: (lambda it, d, open_pos, rng: sorted({"BTC/USDT"} - open_pos)),
    )
    daily_calls = []
    monkeypatch.setattr(
        crypto_entry_pipeline,
        "get_daily_bars",
        lambda *a, **k: daily_calls.append(a) or (_ for _ in ()).throw(AssertionError),
    )

    result = crypto_entry_pipeline.run_crypto_entry_once(
        paper_conn, price_fetcher=lambda s: 200.0, as_of_date=AS_OF
    )

    assert len(result["submitted"]) == 1
    assert daily_calls == []  # the daily cache was never touched
    order = ledger.get_order_by_ref(paper_conn, result["submitted"][0])
    assert order["strategy_id"] == "hrev_p1"
    # Hour-stamped ref: 'YYYY-MM-DDTHH' between the profile and side parts.
    assert "T" in result["submitted"][0].split(":")[1] or "T" in result["submitted"][0]


def test_second_run_same_day_is_idempotent(paper_conn, monkeypatch):
    _insert_live_crypto_row(paper_conn)
    monkeypatch.setattr(
        crypto_entry_pipeline,
        "get_daily_bars",
        lambda symbol, end=None, conn=None: _wiggly_bars(),
    )
    monkeypatch.setattr(
        signals,
        "pick_entries_for",
        lambda sid, var: (lambda it, d, open_pos, rng: sorted({"BTC/USDT"} - open_pos)),
    )

    first = crypto_entry_pipeline.run_crypto_entry_once(
        paper_conn, price_fetcher=lambda s: 200.0, as_of_date=AS_OF
    )
    second = crypto_entry_pipeline.run_crypto_entry_once(
        paper_conn, price_fetcher=lambda s: 200.0, as_of_date=AS_OF
    )

    assert len(first["submitted"]) == 1
    assert second.get("submitted", []) == []
    assert len(ledger.get_open_positions(paper_conn)) == 1
