"""Phase 6 build-half tests: the graduation checklist evaluator
(06-01-PLAN.md). Each of the five frozen checks is exercised at pass, fail,
and boundary; the freeze gate and the append-only audit rows complete the
standing-rule coverage."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader.graduation import evaluator, freeze_gate, frozen_checklist
from trader.paper import config as paper_config

NOW = datetime(2026, 7, 29, 3, 0, tzinfo=timezone.utc)

_PROFILE = paper_config.LIVE_STRATEGY_CONFIGS[0].profile_name

# Frozen stock regime windows (regimes_v2): trending_v2 tune opens
# 2019-01-01, choppy_v2 tune opens 2015-01-01 -- two distinct conditions.
_TRENDING_DAY = "2019-03-01"
_CHOPPY_DAY = "2015-03-01"


@pytest.fixture(autouse=True)
def _no_spy_network(monkeypatch):
    """market_condition's SPY fallback must never hit the network in tests;
    default every out-of-window date to 'risk_on' unless a test overrides."""
    monkeypatch.setattr(evaluator, "_spy_condition", lambda conn, d: "risk_on")


def _insert_trade(
    conn,
    profile: str,
    pnl: float,
    exit_day: str,
    entry_price: float = 100.0,
    exit_price: float = 110.0,
    qty: float = 10.0,
    fees: float = 1.0,
    asset_class: str = "stock",
) -> None:
    conn.execute(
        """
        INSERT INTO paper_trades
            (strategy_id, profile_name, symbol, venue, asset_class, entry_ts,
             entry_price, exit_ts, exit_price, exit_reason, qty, fees,
             slippage_cost, pnl, entry_order_ref, exit_order_ref)
        VALUES (?, ?, 'AAPL', 'ibkr_paper', ?, ?, ?, ?, ?, 'stop', ?, ?, 0.5,
                ?, 'e', 'x')
        """,
        (
            profile, profile, asset_class, f"{exit_day}T09:30:00", entry_price,
            f"{exit_day}T15:30:00", exit_price, qty, fees, pnl,
        ),
    )
    conn.commit()


def _bulk(conn, profile, pnls, start_day, **kwargs) -> None:
    start = date.fromisoformat(start_day)
    for i, pnl in enumerate(pnls):
        _insert_trade(conn, profile, pnl, (start + timedelta(days=i)).isoformat(), **kwargs)


def _graduating_book(conn, profile) -> None:
    """A book that passes all five checks: 50 trades, wide win margin,
    spread over two frozen regime windows, no dominant single trade, real
    price edges that survive 1% adverse fills."""
    winners = [80.0] * 20 + [60.0] * 15  # varied, none dominant
    losers = [-30.0] * 15
    _bulk(conn, profile, winners[:25], _TRENDING_DAY, entry_price=100.0, exit_price=120.0)
    _bulk(conn, profile, winners[25:] + losers, _CHOPPY_DAY,
          entry_price=100.0, exit_price=115.0)


# ---------------------------------------------------------------------------
# Eligibility short-circuit
# ---------------------------------------------------------------------------


def test_under_fifty_trades_not_evaluated(paper_conn):
    _bulk(paper_conn, _PROFILE, [-100.0] * 49, _TRENDING_DAY)

    result = evaluator.evaluate_strategy(paper_conn, _PROFILE)

    assert result["overall"] == "not_enough_trades"
    assert result["trade_count"] == 49
    assert result["profit_factor"] is None


def test_full_pass_book_graduates(paper_conn):
    _graduating_book(paper_conn, _PROFILE)

    result = evaluator.evaluate_strategy(paper_conn, _PROFILE)

    assert result["overall"] == "pass"
    assert result["trade_count"] == 50
    for key in ("pf_pass", "max_dd_pass", "conditions_pass",
                "single_trade_pass", "adverse_fill_pass"):
        assert result[key] is True, key


# ---------------------------------------------------------------------------
# Check 1+2: PF floor and max-DD via metrics.py
# ---------------------------------------------------------------------------


def test_pf_at_or_below_floor_fails(paper_conn):
    # PF exactly 1.3: gains 26*15=390, losses 24*12.5=300 -> 1.3, NOT > 1.3.
    _bulk(paper_conn, _PROFILE, [15.0] * 26 + [-12.5] * 24, _TRENDING_DAY)

    result = evaluator.evaluate_strategy(paper_conn, _PROFILE)

    assert result["profit_factor"] == pytest.approx(1.3)
    assert result["pf_pass"] is False
    assert result["overall"] == "fail"


def test_deep_drawdown_fails(paper_conn):
    # 20k gained then 20k lost: -20k/120k = -16.7% peak-to-trough.
    _bulk(paper_conn, _PROFILE, [1000.0] * 20 + [-800.0] * 25 + [1000.0] * 5,
          _TRENDING_DAY)

    result = evaluator.evaluate_strategy(paper_conn, _PROFILE)

    assert result["max_drawdown"] < frozen_checklist.MAX_DD_GRADUATION
    assert result["max_dd_pass"] is False


# ---------------------------------------------------------------------------
# Check 3: profitable in >= 2 market conditions (D-03)
# ---------------------------------------------------------------------------


def test_single_condition_book_fails_conditions_check(paper_conn):
    _bulk(paper_conn, _PROFILE, [50.0] * 50, _TRENDING_DAY,
          entry_price=100.0, exit_price=120.0)

    result = evaluator.evaluate_strategy(paper_conn, _PROFILE)

    assert result["profitable_conditions"] == 1
    assert result["conditions_pass"] is False


def test_two_regime_windows_count_as_two_conditions(paper_conn):
    _bulk(paper_conn, _PROFILE, [50.0] * 25, _TRENDING_DAY,
          entry_price=100.0, exit_price=120.0)
    _bulk(paper_conn, _PROFILE, [50.0] * 25, _CHOPPY_DAY,
          entry_price=100.0, exit_price=120.0)

    result = evaluator.evaluate_strategy(paper_conn, _PROFILE)

    assert result["profitable_conditions"] == 2
    assert result["conditions_pass"] is True


def test_out_of_window_dates_use_spy_fallback(paper_conn, monkeypatch):
    """Live-paper dates (2026-08+) sit outside every frozen stock window --
    the SPY fallback buckets them, pre-registered, never a judgment call."""
    calls = []

    def _fake_spy(conn, d):
        calls.append(d)
        return "risk_on" if d.day % 2 == 0 else "risk_off"

    monkeypatch.setattr(evaluator, "_spy_condition", _fake_spy)
    _bulk(paper_conn, _PROFILE, [50.0] * 50, "2026-08-03",
          entry_price=100.0, exit_price=120.0)

    result = evaluator.evaluate_strategy(paper_conn, _PROFILE)

    assert calls  # fallback actually used
    assert result["profitable_conditions"] == 2  # risk_on + risk_off both positive
    assert result["conditions_pass"] is True


def test_unknown_condition_never_counts(paper_conn, monkeypatch):
    monkeypatch.setattr(evaluator, "_spy_condition", lambda conn, d: "unknown")
    _bulk(paper_conn, _PROFILE, [50.0] * 50, "2026-08-03",
          entry_price=100.0, exit_price=120.0)

    result = evaluator.evaluate_strategy(paper_conn, _PROFILE)

    assert result["profitable_conditions"] == 0
    assert result["conditions_pass"] is False


# ---------------------------------------------------------------------------
# Check 4: no single trade > 40% of total profit
# ---------------------------------------------------------------------------


def test_dominant_single_trade_fails(paper_conn):
    # One 900 win + 49 small wins totalling 100 -> share 0.9.
    _bulk(paper_conn, _PROFILE, [900.0] + [100.0 / 49] * 49, _TRENDING_DAY,
          entry_price=100.0, exit_price=120.0)

    result = evaluator.evaluate_strategy(paper_conn, _PROFILE)

    assert result["single_trade_share"] == pytest.approx(0.9)
    assert result["single_trade_pass"] is False


def test_share_exactly_forty_percent_passes(paper_conn):
    # 400 + 60 small wins summing 600 -> total 1000, share exactly 0.40.
    _bulk(paper_conn, _PROFILE, [400.0] + [600.0 / 49] * 49, _TRENDING_DAY,
          entry_price=100.0, exit_price=120.0)

    result = evaluator.evaluate_strategy(paper_conn, _PROFILE)

    assert result["single_trade_share"] == pytest.approx(0.40)
    assert result["single_trade_pass"] is True


# ---------------------------------------------------------------------------
# Check 5: adverse-fill recompute (D-04 golden case)
# ---------------------------------------------------------------------------


def test_adverse_fill_golden_case():
    trades = [
        {"entry_price": 100.0, "exit_price": 110.0, "qty": 10.0, "fees": 1.0}
    ]
    # (110*0.99 - 100*1.01) * 10 - 1 = (108.9 - 101.0) * 10 - 1 = 78.0
    assert evaluator._adverse_fill_pnl(trades) == pytest.approx(78.0)


def test_thin_edge_dies_under_adverse_fills(paper_conn):
    # Entry 100 -> exit 101: profitable raw, negative once 1% adverse
    # fills are applied ((101*0.99 - 100*1.01)*10 - 1 = -11.1 per trade).
    _bulk(paper_conn, _PROFILE, [9.0] * 50, _TRENDING_DAY,
          entry_price=100.0, exit_price=101.0)

    result = evaluator.evaluate_strategy(paper_conn, _PROFILE)

    assert result["adverse_fill_pnl"] < 0
    assert result["adverse_fill_pass"] is False
    assert result["overall"] == "fail"


# ---------------------------------------------------------------------------
# Freeze gate + review run + audit rows
# ---------------------------------------------------------------------------


def test_committed_hash_matches_checklist_file():
    assert (
        freeze_gate.compute_graduation_hash()
        == freeze_gate.FROZEN_GRADUATION_HASH
    )


def test_tampered_checklist_aborts_review(paper_conn, monkeypatch, tmp_path):
    monkeypatch.setattr(freeze_gate, "FROZEN_GRADUATION_HASH", "0" * 64)

    with pytest.raises(RuntimeError, match="integrity check failed"):
        evaluator.run_graduation_review(
            paper_conn, now=NOW, report_base_dir=str(tmp_path)
        )

    count = paper_conn.execute("SELECT COUNT(*) FROM graduation_reviews").fetchone()[0]
    assert count == 0


def test_review_writes_audit_rows_and_report(paper_conn, tmp_path):
    _graduating_book(paper_conn, _PROFILE)

    summary = evaluator.run_graduation_review(
        paper_conn, now=NOW, report_base_dir=str(tmp_path)
    )

    assert summary["passed"] == [_PROFILE]
    rows = paper_conn.execute(
        "SELECT profile_name, overall, checklist_hash FROM graduation_reviews"
    ).fetchall()
    assert len(rows) == len(paper_config.LIVE_STRATEGY_CONFIGS)
    by_name = {name: (overall, chash) for name, overall, chash in rows}
    assert by_name[_PROFILE][0] == "pass"
    for overall, chash in by_name.values():
        assert chash == freeze_gate.FROZEN_GRADUATION_HASH

    report = Path(summary["report_path"]).read_text(encoding="utf-8")
    assert "Graduation Review" in report
    assert "PASS" in report
    assert freeze_gate.FROZEN_GRADUATION_HASH in report
    assert "advisory" in report


def test_review_never_changes_registry_state(paper_conn, tmp_path):
    """D-07: verdicts are advisory -- the registry is untouched."""
    _graduating_book(paper_conn, _PROFILE)
    before = paper_conn.execute(
        "SELECT profile_name, state FROM strategy_registry ORDER BY profile_name"
    ).fetchall()

    evaluator.run_graduation_review(paper_conn, now=NOW, report_base_dir=str(tmp_path))

    after = paper_conn.execute(
        "SELECT profile_name, state FROM strategy_registry ORDER BY profile_name"
    ).fetchall()
    assert before == after
