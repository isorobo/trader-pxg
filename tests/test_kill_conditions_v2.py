"""Tests for Plan 03-08 Task 3's v2 phase-exit gate regeneration:
write_kill_conditions_v2.py and sweep_report_v2.py (T-03-29, D-11, D-16).

`build_kill_conditions_text` is a pure formatting function (no I/O) --
these tests exercise both its survivor and nothing-survived branches
against synthetic fixture data, mirroring tests/test_kill_conditions.py's
sibling pattern. The real committed KILL-CONDITIONS.md is regenerated from
the REAL reports/backtests/oos_results_v2.json only after Plan 03-08
Task 2's real ~10,800-run sweep and OOS validation complete -- this test
file proves the module's WIRING and formatting rules against fixtures
only; the real-artifact cross-check runs in a later session once
oos_results_v2.json exists on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trader.backtest import frozen_config_v2
from trader.backtest import sweep_report_v2
from trader.backtest import write_kill_conditions as wkc_v1
from trader.backtest import write_kill_conditions_v2 as wkc


# --- main()'s v2 frozen-config gate (T-03-29) --------------------------


def test_main_raises_before_reading_oos_results_on_hash_tamper(monkeypatch, tmp_path):
    monkeypatch.setattr(frozen_config_v2, "FROZEN_HASH_V2", "0" * 64)
    # Point at a path that does not exist -- if verify_frozen_v2() were
    # ever skipped or called after the read, main() would raise
    # FileNotFoundError instead of RuntimeError.
    monkeypatch.setattr(wkc, "OOS_RESULTS_PATH", tmp_path / "does-not-exist.json")

    with pytest.raises(RuntimeError):
        wkc.main()


# --- Constants/helpers reused verbatim from v1 (D-15's spirit) ----------


def test_kill_condition_constants_and_helper_are_the_same_v1_objects():
    assert wkc.PF_FLOOR is wkc_v1.PF_FLOOR
    assert wkc.MAX_DD_FLOOR is wkc_v1.MAX_DD_FLOOR
    assert wkc.MAX_DD_MULTIPLIER is wkc_v1.MAX_DD_MULTIPLIER
    assert wkc.CONSECUTIVE_LOSS_KILL is wkc_v1.CONSECUTIVE_LOSS_KILL
    assert wkc._max_drawdown_trigger is wkc_v1._max_drawdown_trigger
    assert wkc.NOTHING_SURVIVED_SENTENCE is wkc_v1.NOTHING_SURVIVED_SENTENCE


# --- build_kill_conditions_text: pure formatting, both branches --------


def _survivor_result(strategy_id, bucket, regime, max_drawdown, entry_variant="base", run_id=1):
    return {
        "candidate": {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "bucket": bucket,
            "regime": regime,
            "params": {
                "profile_name": f"{strategy_id}_{bucket}_{regime}_{entry_variant}_tune_profile",
                "entry_variant": entry_variant,
            },
        },
        "oos_run_id": 9000 + run_id,
        "oos_metrics": {
            "profit_factor": 2.0,
            "max_drawdown": max_drawdown,
            "trade_count": 20,
        },
        "verdict": "survivor",
    }


def _non_survivor_result(
    verdict, strategy_id="momentum_stock", bucket="stock", regime="trending_v2", run_id=2
):
    return {
        "candidate": {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "bucket": bucket,
            "regime": regime,
            "params": {"profile_name": "test_profile", "entry_variant": "base"},
        },
        "oos_run_id": 9000 + run_id,
        "oos_metrics": {"profit_factor": 0.5, "max_drawdown": -0.05, "trade_count": 20},
        "verdict": verdict,
    }


def test_build_kill_conditions_text_one_entry_per_survivor_with_three_triggers():
    results = [
        _survivor_result("momentum_stock", "stock", "trending_v2", max_drawdown=-0.02, run_id=1),
        _survivor_result(
            "momentum_crypto_major_legacy_meme",
            "crypto_major_legacy_meme",
            "bear_recovery_v2",
            max_drawdown=-0.30,
            entry_variant="loose",
            run_id=3,
        ),
        _non_survivor_result("killed"),
        _non_survivor_result("insufficient_sample", run_id=4),
    ]

    text = wkc.build_kill_conditions_text(results)

    assert "## momentum_stock / stock / trending_v2" in text
    assert (
        "## momentum_crypto_major_legacy_meme / crypto_major_legacy_meme / bear_recovery_v2"
        in text
    )
    assert text.count("**Rolling-30-trade profit factor floor:** 0.9") == 2
    assert text.count("**Consecutive-loss kill count:** 8") == 2
    # 1.5 * -0.02 = -0.03 (well within the -0.15 floor)
    assert "**Max-drawdown kill level:** -0.0300" in text
    # 1.5 * -0.30 = -0.45, looser than -0.15 -> floored to -0.15
    assert "**Max-drawdown kill level:** -0.1500" in text
    assert "**Entry variant:** loose" in text
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


# --- sweep_report_v2.write_survivors_index_v2 ----------------------------


def test_write_survivors_index_v2_writes_distinctly_named_file(tmp_path):
    from datetime import datetime

    # A pre-existing v1 survivors index in the same directory must never be
    # touched by v2's writer (T-03-28).
    today_str = datetime.now().strftime("%Y-%m-%d")
    v1_survivors_path = tmp_path / f"{today_str}-survivors.md"
    v1_survivors_path.write_text("v1 content -- must remain untouched", encoding="utf-8")

    oos_results = [_survivor_result("momentum_stock", "stock", "trending_v2", max_drawdown=-0.02)]

    written_path = sweep_report_v2.write_survivors_index_v2(oos_results, base_dir=str(tmp_path))

    assert written_path.name == f"{today_str}-survivors-v2.md"
    assert written_path.exists()
    assert v1_survivors_path.read_text(encoding="utf-8") == "v1 content -- must remain untouched"

    content = written_path.read_text(encoding="utf-8")
    assert "momentum_stock" in content


def test_write_survivors_index_v2_nothing_survived_sentence(tmp_path):
    oos_results = [_non_survivor_result("killed"), _non_survivor_result("insufficient_sample", run_id=2)]

    written_path = sweep_report_v2.write_survivors_index_v2(oos_results, base_dir=str(tmp_path))

    content = written_path.read_text(encoding="utf-8")
    assert "Nothing survived this sweep" in content
    assert "2 candidates" in content
