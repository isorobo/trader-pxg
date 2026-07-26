"""Tests for trader.backtest.config — fee table, slippage table, and
EXIT_PROFILE dataclass contracts (D-06 through D-09).
"""

import dataclasses

import pytest

try:
    from trader.backtest import config
except ImportError:
    # trader.backtest.config does not exist yet (RED phase) — collection must
    # still succeed so all tests are collected; each test then fails with an
    # AttributeError on `config` (None) when it tries to call into the
    # contract. Matches tests/test_data_api.py's RED-phase-safe pattern.
    config = None


def test_fee_table_stock():
    assert config.FEE_TABLE["stock"] == {
        "kind": "per_share",
        "rate": 0.005,
        "minimum": 1.00,
    }


def test_fee_table_crypto_major():
    assert config.FEE_TABLE["crypto_major"] == {"kind": "taker_pct", "rate": 0.0026}


def test_fee_table_memecoin():
    assert config.FEE_TABLE["memecoin"] == {"kind": "taker_pct", "rate": 0.0026}


def test_slippage_pct_mapping():
    # ORCHESTRATOR REVISION (locked): crypto_major is 0.10%, NOT the phase
    # document's small-cap-runner 1-3% tier.
    assert config.SLIPPAGE_PCT == {
        "stock": 0.05,
        "crypto_major": 0.10,
        "memecoin": 4.0,
    }


def test_slippage_small_cap_runner_hook_unwired():
    # Documented hook for Phase 3 — a separate named constant, not part of
    # SLIPPAGE_PCT's asset_class map.
    assert config.SLIPPAGE_SMALL_CAP_RUNNER == 2.0
    assert "small_cap_runner" not in config.SLIPPAGE_PCT
    assert 2.0 not in config.SLIPPAGE_PCT.values()


def test_default_notional():
    assert config.DEFAULT_NOTIONAL == 10_000.0


def test_exit_profile_is_frozen():
    profile = config.EXIT_PROFILE(
        stop_pct=-0.05,
        tp_pct=0.10,
        scale_out=(),
        trailing_pct=None,
        max_hold_days=5,
        eod_flat=False,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        profile.stop_pct = -0.10


def test_exit_profile_scale_out_rejects_list():
    with pytest.raises(TypeError):
        config.EXIT_PROFILE(
            stop_pct=-0.05,
            tp_pct=0.10,
            scale_out=[(0.05, 0.5)],
            trailing_pct=None,
            max_hold_days=5,
            eod_flat=False,
        )


def test_exit_profile_scale_out_accepts_tuple():
    profile = config.EXIT_PROFILE(
        stop_pct=-0.05,
        tp_pct=0.10,
        scale_out=((0.05, 0.5), (0.10, 0.5)),
        trailing_pct=None,
        max_hold_days=5,
        eod_flat=False,
    )
    assert profile.scale_out == ((0.05, 0.5), (0.10, 0.5))
    with pytest.raises(dataclasses.FrozenInstanceError):
        profile.scale_out = ()


def test_profile_time_stop_1d():
    assert config.PROFILE_TIME_STOP_1D == config.EXIT_PROFILE(
        stop_pct=None,
        tp_pct=None,
        scale_out=(),
        trailing_pct=None,
        max_hold_days=1,
        eod_flat=False,
    )


def test_profile_momentum_placeholder_is_concrete():
    profile = config.PROFILE_MOMENTUM_PLACEHOLDER
    assert isinstance(profile, config.EXIT_PROFILE)
    assert profile.stop_pct is not None
    assert profile.tp_pct is not None
    assert profile.max_hold_days is not None
