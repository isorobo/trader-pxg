"""Donchian entrant tests: the frozen entry signal, its freeze gate, the
evidence driver's arithmetic, and the register CLI's Phase 8 gate."""

from __future__ import annotations

import json
import random

import numpy as np
import pandas as pd
import pytest

from trader.backtest.frozen_config_donchian import (
    FROZEN_HASH_DONCHIAN,
    compute_hash_donchian,
    verify_frozen_donchian,
)
from trader.backtest.iterator import PointInTimeIterator
from trader.backtest.strategies import donchian


def _bars(closes_highs: list[tuple[float, float]], end="2020-06-30") -> pd.DataFrame:
    """Build an OHLCV frame from (close, high) pairs; low/open/volume flat."""
    periods = len(closes_highs)
    dates = pd.bdate_range(end=end, periods=periods, tz="UTC")
    closes = [c for c, _ in closes_highs]
    highs = [h for _, h in closes_highs]
    return pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": [min(c, h) - 1.0 for c, h in closes_highs],
            "close": closes,
            "volume": [1_000_000.0] * periods,
        },
        index=dates,
    )


def _fire(variant_name: str, bars_by_symbol: dict[str, pd.DataFrame]) -> list[str]:
    iterator = PointInTimeIterator(bars_by_symbol)
    last_date = max(df.index[-1] for df in bars_by_symbol.values())
    iterator.advance_to(last_date.date())
    pick = donchian.make_pick_entries(donchian.DONCHIAN_VARIANTS[variant_name])
    return pick(iterator, last_date, set(), random.Random(0))


# ---------------------------------------------------------------------------
# Signal semantics
# ---------------------------------------------------------------------------


def test_sys1_fires_on_break_of_20_day_high():
    # 20 flat days with highs at 100, then a close above them.
    rows = [(95.0, 100.0)] * 20 + [(101.0, 101.5)]
    assert _fire("sys1", {"AAPL": _bars(rows)}) == ["AAPL"]


def test_sys1_never_fires_at_or_below_the_channel():
    rows_at = [(95.0, 100.0)] * 20 + [(100.0, 100.0)]  # equal, not above
    rows_below = [(95.0, 100.0)] * 20 + [(99.0, 99.5)]
    assert _fire("sys1", {"AAPL": _bars(rows_at)}) == []
    assert _fire("sys1", {"AAPL": _bars(rows_below)}) == []


def test_sys2_needs_55_days_of_history():
    rows = [(95.0, 100.0)] * 40 + [(101.0, 101.5)]  # only 41 bars
    assert _fire("sys2", {"AAPL": _bars(rows)}) == []


def test_sys2_fires_on_break_of_55_day_high():
    rows = [(95.0, 100.0)] * 55 + [(101.0, 101.5)]
    assert _fire("sys2", {"AAPL": _bars(rows)}) == ["AAPL"]
    # A 20-day-high break that is NOT a 55-day-high break: sys1-only.
    rows_mixed = [(95.0, 110.0)] * 35 + [(95.0, 100.0)] * 20 + [(105.0, 105.5)]
    assert _fire("sys2", {"AAPL": _bars(rows_mixed)}) == []
    assert _fire("sys1", {"AAPL": _bars(rows_mixed)}) == ["AAPL"]


def test_open_positions_never_refire():
    rows = [(95.0, 100.0)] * 20 + [(101.0, 101.5)]
    iterator = PointInTimeIterator({"AAPL": _bars(rows)})
    last_date = _bars(rows).index[-1]
    iterator.advance_to(last_date.date())
    pick = donchian.make_pick_entries(donchian.DONCHIAN_VARIANTS["sys1"])
    assert pick(iterator, last_date, {"AAPL"}, random.Random(0)) == []


def test_variants_are_the_published_turtle_systems():
    assert donchian.DONCHIAN_VARIANTS["sys1"].entry_lookback == 20
    assert donchian.DONCHIAN_VARIANTS["sys2"].entry_lookback == 55
    assert set(donchian.DONCHIAN_VARIANTS) == {"sys1", "sys2"}


# ---------------------------------------------------------------------------
# Freeze gate
# ---------------------------------------------------------------------------


def test_committed_donchian_hash_matches_file():
    assert compute_hash_donchian() == FROZEN_HASH_DONCHIAN


def test_tampered_donchian_file_raises(tmp_path):
    src = compute_hash_donchian.__module__  # noqa: F841 (documentation only)
    from pathlib import Path

    from trader.backtest import frozen_config_donchian as gate

    repo_root = Path(gate.__file__).resolve().parents[2]
    for rel in gate.FROZEN_FILES_DONCHIAN:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((repo_root / rel).read_bytes() + b"# tampered\n")

    with pytest.raises(RuntimeError, match="integrity check failed"):
        verify_frozen_donchian(repo_root=tmp_path)


# ---------------------------------------------------------------------------
# Evidence driver arithmetic + gate placement
# ---------------------------------------------------------------------------


def test_expected_tune_run_count_matches_real_grid_and_regimes():
    from trader.backtest import exit_grid, regimes_v2, universe
    from trader.backtest.run_donchian_evidence import (
        EXPECTED_TUNE_RUN_COUNT_DONCHIAN,
    )

    stock_regimes = [
        r for r in regimes_v2.REGIMES_V2 if r.bucket == universe.BUCKET_STOCK
    ]
    grid_size = len(list(exit_grid.exit_profile_grid(universe.BUCKET_STOCK)))
    expected = len(donchian.DONCHIAN_VARIANTS) * len(stock_regimes) * grid_size
    assert expected == EXPECTED_TUNE_RUN_COUNT_DONCHIAN


def test_evidence_driver_verifies_donchian_gate_before_any_work(monkeypatch):
    from trader.backtest import run_donchian_evidence

    monkeypatch.setattr(
        run_donchian_evidence,
        "verify_frozen_donchian",
        lambda: (_ for _ in ()).throw(RuntimeError("integrity check failed")),
    )

    with pytest.raises(RuntimeError, match="integrity check failed"):
        run_donchian_evidence.main(conn=object())


def test_crypto_expected_tune_run_count_matches_real_grid_and_regimes():
    from trader.backtest import exit_grid, regimes_v2, universe
    from trader.backtest.run_donchian_crypto_evidence import (
        CRYPTO_BUCKETS,
        EXPECTED_TUNE_RUN_COUNT_DONCHIAN_CRYPTO,
    )

    expected = 0
    for bucket in CRYPTO_BUCKETS:
        regimes = [r for r in regimes_v2.REGIMES_V2 if r.bucket == bucket]
        grid_size = len(list(exit_grid.exit_profile_grid(bucket)))
        expected += len(donchian.DONCHIAN_VARIANTS) * len(regimes) * grid_size
    assert expected == EXPECTED_TUNE_RUN_COUNT_DONCHIAN_CRYPTO


def test_crypto_evidence_driver_verifies_gate_before_any_work(monkeypatch):
    from trader.backtest import run_donchian_crypto_evidence

    monkeypatch.setattr(
        run_donchian_crypto_evidence,
        "verify_frozen_donchian",
        lambda: (_ for _ in ()).throw(RuntimeError("integrity check failed")),
    )

    with pytest.raises(RuntimeError, match="integrity check failed"):
        run_donchian_crypto_evidence.main(conn=object())


# ---------------------------------------------------------------------------
# The Phase 8 gate on registration
# ---------------------------------------------------------------------------


def _evidence_file(tmp_path) -> str:
    payload = {
        "survivors": [
            {
                "profile_name": "donchian_stock_x",
                "strategy_id": "donchian_stock",
                "entry_variant": "sys1",
                "stop_pct": -0.1,
                "tp_pct": 0.2,
                "trailing_pct": None,
                "max_hold_days": 30,
                "pf_floor": 0.9,
                "max_dd_kill": -0.05,
                "consecutive_loss_kill": 8,
                "backtest_run_id": 42,
                "oos_run_id": 43,
                "oos_result_ref": "reports/backtests/donchian_evidence.json",
            }
        ]
    }
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_register_entrant_refuses_without_owner_approval(tmp_path, capsys):
    from trader.tournament import register_entrant

    with pytest.raises(SystemExit) as excinfo:
        register_entrant.main(
            ["--evidence", _evidence_file(tmp_path), "--profile", "donchian_stock_x"]
        )

    assert excinfo.value.code == 2
    assert "human-approved" in capsys.readouterr().err


def test_register_entrant_registers_with_gate_flag(tmp_path, paper_conn, monkeypatch):
    from trader.data import db as trader_db
    from trader.tournament import register_entrant

    class _NoClose:
        """main() closes the connection it opens; the test still needs to
        query paper_conn afterwards, so close is absorbed here."""

        def __init__(self, conn):
            self._conn = conn

        def close(self):
            pass

        def __getattr__(self, name):
            return getattr(self._conn, name)

    monkeypatch.setattr(
        trader_db, "get_connection", lambda path=None: _NoClose(paper_conn)
    )

    register_entrant.main(
        [
            "--evidence", _evidence_file(tmp_path),
            "--profile", "donchian_stock_x",
            "--owner-approval", "test authorisation",
        ]
    )

    row = paper_conn.execute(
        "SELECT state, backtest_run_id, oos_result_ref, entry_variant "
        "FROM strategy_registry WHERE profile_name = 'donchian_stock_x'"
    ).fetchone()
    assert row == ("candidate", 42, "reports/backtests/donchian_evidence.json", "sys1")
    reason = paper_conn.execute(
        "SELECT reason FROM strategy_registry_transitions "
        "WHERE profile_name = 'donchian_stock_x'"
    ).fetchone()[0]
    assert "test authorisation" in reason


def test_register_entrant_unknown_profile_exits(tmp_path, capsys):
    from trader.tournament import register_entrant

    with pytest.raises(SystemExit) as excinfo:
        register_entrant.main(
            [
                "--evidence", _evidence_file(tmp_path),
                "--profile", "nope",
                "--owner-approval", "test authorisation",
            ]
        )

    assert excinfo.value.code == 2
    assert "Survivors present" in capsys.readouterr().err
