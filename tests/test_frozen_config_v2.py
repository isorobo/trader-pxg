"""Hash-based freeze-gate tests for frozen_config_v2.py (T-03-21).

Mirrors test_frozen_config.py's pattern exactly but scoped to v2's own
5-file frozen surface (universe.py, regimes_v2.py, exit_grid.py,
momentum_v2.py, breakout_v2.py). Asserts compute_hash_v2() is
self-consistent with the hard-coded FROZEN_HASH_V2 at commit time, that
verify_frozen_v2() raises RuntimeError the moment any one of those 5 files
differs by even a single byte, and that v1's own frozen_config.py gate
stays fully independent of this one.
"""

import shutil
from pathlib import Path

import pytest

from trader.backtest import frozen_config, frozen_config_v2


def test_compute_hash_v2_matches_frozen_hash_v2():
    assert frozen_config_v2.compute_hash_v2() == frozen_config_v2.FROZEN_HASH_V2


def test_verify_frozen_v2_passes_on_unmodified_repo():
    frozen_config_v2.verify_frozen_v2()  # must not raise


def test_frozen_files_v2_exact_five_entries_in_order():
    assert frozen_config_v2.FROZEN_FILES_V2 == (
        "trader/backtest/universe.py",
        "trader/backtest/regimes_v2.py",
        "trader/backtest/exit_grid.py",
        "trader/backtest/strategies/momentum_v2.py",
        "trader/backtest/strategies/breakout_v2.py",
    )


def test_verify_frozen_v2_raises_on_byte_level_tamper(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    for rel in frozen_config_v2.FROZEN_FILES_V2:
        src = repo_root / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)

    # Sanity: an untampered byte-for-byte copy still matches FROZEN_HASH_V2.
    assert frozen_config_v2.compute_hash_v2(tmp_path) == frozen_config_v2.FROZEN_HASH_V2
    frozen_config_v2.verify_frozen_v2(tmp_path)  # must not raise

    tampered_path = tmp_path / frozen_config_v2.FROZEN_FILES_V2[-1]
    tampered_path.write_bytes(tampered_path.read_bytes() + b"\n# tampered\n")

    assert frozen_config_v2.compute_hash_v2(tmp_path) != frozen_config_v2.FROZEN_HASH_V2
    with pytest.raises(RuntimeError):
        frozen_config_v2.verify_frozen_v2(tmp_path)


def test_v1_frozen_config_tamper_does_not_trip_v2_gate(tmp_path, monkeypatch):
    # The two freeze gates are fully independent: tampering v1's own
    # frozen_config.FROZEN_HASH (an unrelated module-level constant) must
    # never affect frozen_config_v2.verify_frozen_v2()'s outcome.
    monkeypatch.setattr(frozen_config, "FROZEN_HASH", "deadbeef" * 8)
    frozen_config_v2.verify_frozen_v2()  # must not raise despite v1 tamper
