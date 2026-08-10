"""Wave 1 tests: the D-06 tournament freeze gate (mirrors
tests/test_frozen_config_v2.py's tamper-simulation shape)."""

from pathlib import Path

import pytest

from trader.tournament import freeze_gate, frozen_config


def _copy_frozen_surface(tmp_path: Path) -> Path:
    """Copy the gated file into a tmp repo-root skeleton so tamper tests
    never touch the real committed file."""
    repo_root = Path(freeze_gate.__file__).resolve().parents[2]
    for rel in freeze_gate.FROZEN_TOURNAMENT_FILES:
        src = repo_root / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    return tmp_path


def test_committed_hash_matches_current_file():
    assert freeze_gate.compute_tournament_hash() == freeze_gate.FROZEN_TOURNAMENT_HASH


def test_verify_passes_on_untampered_copy(tmp_path):
    root = _copy_frozen_surface(tmp_path)
    freeze_gate.verify_frozen_tournament(repo_root=root)


def test_verify_raises_on_byte_level_tamper(tmp_path):
    root = _copy_frozen_surface(tmp_path)
    target = root / freeze_gate.FROZEN_TOURNAMENT_FILES[0]
    # A results-flattering edit: loosen the demotion floor by one byte.
    target.write_bytes(target.read_bytes().replace(
        b"SHARPE_DEMOTION_FLOOR = 0.0", b"SHARPE_DEMOTION_FLOOR = -9.9"
    ))

    with pytest.raises(RuntimeError, match="integrity check failed"):
        freeze_gate.verify_frozen_tournament(repo_root=root)


def test_frozen_values_are_the_preregistered_ones():
    """The D-06 numbers themselves, asserted literally: a change here must
    be a deliberate two-place edit (constant + this test + rehash), never a
    drive-by."""
    assert frozen_config.MIN_TRADES_FOR_JUDGING == 30
    assert frozen_config.JUDGING_WINDOW_TRADES == 30
    assert frozen_config.SHARPE_PROMOTION_FLOOR == 0.0
    assert frozen_config.SHARPE_DEMOTION_FLOOR == 0.0
    assert frozen_config.DEMOTION_SUSTAIN_EVALUATIONS == 4
    assert frozen_config.PROBATION_SIZE_MULTIPLIER == 0.25
    # Sanctioned owner capacity revision 2026-08-08 (zero closed trades on
    # the books; see frozen_config.py's revision note) -- the deliberate
    # two-place edit this test exists to force.
    assert frozen_config.MAX_ACTIVE_STRATEGIES == 20
    assert frozen_config.MAX_NEW_ENTRANTS_PER_QUARTER == 12
