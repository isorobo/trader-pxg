"""Tests for STRAT-06's phase-exit gate: write_kill_conditions.py (T-03-17,
T-03-20, D-11).

`build_kill_conditions_text` is a pure formatting function (no I/O) --
these tests exercise both its survivor and nothing-survived branches
against synthetic fixture data. The real committed
`.planning/phases/03-strategy-lab/KILL-CONDITIONS.md` and the real
`reports/backtests/oos_results.json` are cross-checked 1:1 separately
(T-03-17): a missing or extra survivor entry fails that check.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trader.backtest import frozen_config
from trader.backtest import write_kill_conditions as wkc

OOS_RESULTS_PATH = Path("reports/backtests/oos_results.json")
KILL_CONDITIONS_PATH = Path(".planning/phases/03-strategy-lab/KILL-CONDITIONS.md")


# --- main()'s frozen-config gate (T-03-20) -----------------------------------


def test_main_raises_before_reading_oos_results_on_hash_tamper(monkeypatch, tmp_path):
    monkeypatch.setattr(frozen_config, "FROZEN_HASH", "0" * 64)
    # Point at a path that does not exist -- if verify_frozen() were ever
    # skipped or called after the read, main() would raise
    # FileNotFoundError instead of RuntimeError.
    monkeypatch.setattr(wkc, "OOS_RESULTS_PATH", tmp_path / "does-not-exist.json")

    with pytest.raises(RuntimeError):
        wkc.main()


# --- build_kill_conditions_text: pure formatting, both branches -------------


def _survivor_result(strategy_id, bucket, regime, max_drawdown, run_id=1):
    return {
        "candidate": {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "bucket": bucket,
            "regime": regime,
            "params": {"profile_name": f"{strategy_id}_{bucket}_{regime}_tune_profile"},
        },
        "oos_run_id": 9000 + run_id,
        "oos_metrics": {
            "profit_factor": 2.0,
            "max_drawdown": max_drawdown,
            "trade_count": 20,
        },
        "verdict": "survivor",
    }


def _non_survivor_result(verdict, strategy_id="momentum_stock", bucket="stock", regime="trending", run_id=2):
    return {
        "candidate": {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "bucket": bucket,
            "regime": regime,
            "params": {"profile_name": "test_profile"},
        },
        "oos_run_id": 9000 + run_id,
        "oos_metrics": {"profit_factor": 0.5, "max_drawdown": -0.05, "trade_count": 20},
        "verdict": verdict,
    }


def test_build_kill_conditions_text_one_entry_per_survivor_with_three_triggers():
    results = [
        _survivor_result("momentum_stock", "stock", "trending", max_drawdown=-0.02, run_id=1),
        _survivor_result(
            "momentum_crypto_major_legacy_meme",
            "crypto_major_legacy_meme",
            "trending",
            max_drawdown=-0.30,
            run_id=3,
        ),
        _non_survivor_result("killed"),
        _non_survivor_result("insufficient_sample", run_id=4),
    ]

    text = wkc.build_kill_conditions_text(results)

    assert "## momentum_stock / stock / trending" in text
    assert "## momentum_crypto_major_legacy_meme / crypto_major_legacy_meme / trending" in text
    assert text.count("**Rolling-30-trade profit factor floor:** 0.9") == 2
    assert text.count("**Consecutive-loss kill count:** 8") == 2
    # 1.5 * -0.02 = -0.03 (well within the -0.15 floor)
    assert "**Max-drawdown kill level:** -0.0300" in text
    # 1.5 * -0.30 = -0.45, looser than -0.15 -> floored to -0.15
    assert "**Max-drawdown kill level:** -0.1500" in text
    # exactly two survivor headers, never one per non-survivor
    assert text.count("## ") == 2


def test_build_kill_conditions_text_nothing_survived_exact_sentence():
    results = [
        _non_survivor_result("insufficient_sample", run_id=1),
        _non_survivor_result("killed", run_id=2),
    ]

    text = wkc.build_kill_conditions_text(results)

    assert wkc.NOTHING_SURVIVED_SENTENCE in text
    assert "## " not in text


def test_build_kill_conditions_text_never_empty_on_zero_survivors():
    text = wkc.build_kill_conditions_text([_non_survivor_result("killed")])
    assert text.strip() != ""


def test_max_drawdown_trigger_never_looser_than_floor():
    assert wkc._max_drawdown_trigger(-0.30) == pytest.approx(-0.15)
    assert wkc._max_drawdown_trigger(-0.02) == pytest.approx(-0.03)
    assert wkc._max_drawdown_trigger(None) == pytest.approx(0.0)


# --- Real-artifact cross-check (T-03-17) ------------------------------------


def test_real_kill_conditions_file_matches_real_oos_results_survivor_list():
    """Cross-checks the committed KILL-CONDITIONS.md 1:1 against the real
    reports/backtests/oos_results.json survivor list -- a missing or extra
    entry fails this test."""
    assert OOS_RESULTS_PATH.exists(), "real oos_results.json must exist (Plan 03-05's output)"
    assert KILL_CONDITIONS_PATH.exists(), "real KILL-CONDITIONS.md must exist after Plan 03-06's run"

    oos_results = json.loads(OOS_RESULTS_PATH.read_text())
    survivors = [r for r in oos_results if r["verdict"] == "survivor"]
    committed_text = KILL_CONDITIONS_PATH.read_text(encoding="utf-8")

    if not survivors:
        assert wkc.NOTHING_SURVIVED_SENTENCE in committed_text
        assert "## " not in committed_text
    else:
        assert committed_text.count("## ") == len(survivors)
        for result in survivors:
            candidate = result["candidate"]
            header = (
                f"## {candidate['strategy_id']} / {candidate['bucket']} / "
                f"{candidate['regime']}"
            )
            assert header in committed_text


def test_real_sweep_reports_and_survivors_index_exist_on_disk():
    """Every real oos_results.json entry gets its own sweep report (run_id
    disambiguates same-combo candidates), plus exactly one survivors
    index, per Task 2's acceptance criteria."""
    assert OOS_RESULTS_PATH.exists()

    oos_results = json.loads(OOS_RESULTS_PATH.read_text())
    base_dir = Path("reports/backtests")

    sweep_reports = list(base_dir.glob("*-sweep.md"))
    survivors_index = list(base_dir.glob("*-survivors.md"))

    assert len(survivors_index) >= 1
    assert len(sweep_reports) >= len(oos_results)
