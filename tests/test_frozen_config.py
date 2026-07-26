"""Hash-based freeze-gate tests for frozen_config.py (T-03-06).

Asserts compute_hash() is self-consistent with the hard-coded FROZEN_HASH
at commit time, and that verify_frozen() raises RuntimeError the moment any
one of the three frozen files (universe.py, regimes.py, exit_grid.py)
differs by even a single byte from what FROZEN_HASH was computed from --
the code-level enforcement of standing rule 1 ("never edit graduation/kill
criteria while looking at results").
"""

import shutil
from pathlib import Path

import pytest

from trader.backtest import frozen_config


def test_compute_hash_matches_frozen_hash():
    assert frozen_config.compute_hash() == frozen_config.FROZEN_HASH


def test_verify_frozen_passes_on_unmodified_repo():
    frozen_config.verify_frozen()  # must not raise


def test_verify_frozen_raises_on_byte_level_tamper(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    for rel in frozen_config.FROZEN_FILES:
        src = repo_root / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)

    # Sanity: an untampered byte-for-byte copy still matches FROZEN_HASH.
    assert frozen_config.compute_hash(tmp_path) == frozen_config.FROZEN_HASH
    frozen_config.verify_frozen(tmp_path)  # must not raise

    tampered_path = tmp_path / frozen_config.FROZEN_FILES[-1]
    tampered_path.write_bytes(tampered_path.read_bytes() + b"\n# tampered\n")

    assert frozen_config.compute_hash(tmp_path) != frozen_config.FROZEN_HASH
    with pytest.raises(RuntimeError):
        frozen_config.verify_frozen(tmp_path)
