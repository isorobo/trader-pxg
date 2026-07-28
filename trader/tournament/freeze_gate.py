"""The hash-based freeze gate for Phase 7's tournament thresholds (D-06).

Mirrors trader/backtest/frozen_config_v2.py's exact hashing/verify pattern --
a NEW, standalone gate, following the Phase 3 precedent of adding an
independent gate per frozen surface rather than extending an existing one.
The gated surface is trader/tournament/frozen_config.py alone.

Run `python -c "from trader.tournament import freeze_gate as f;
print(f.compute_tournament_hash())"` to recompute FROZEN_TOURNAMENT_HASH
after an intentional, reviewed change -- the only sanctioned way to move the
tournament freeze point, and per D-06 never after the first real (non-
fixture) tournament run without an explicit owner decision recorded in
.planning/.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Relative paths, hashed in this exact order. Path(__file__).resolve() is
# .../trader/tournament/freeze_gate.py; parents[2] = repo root.
FROZEN_TOURNAMENT_FILES: tuple[str, ...] = (
    "trader/tournament/frozen_config.py",
)


def compute_tournament_hash(repo_root: Path | None = None) -> str:
    """Return the sha256 hex digest over FROZEN_TOURNAMENT_FILES' raw bytes,
    in order. `repo_root` defaults to this repo's root; tests pass a
    tmp_path copy to simulate tampering without touching the committed
    file."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]

    digest = hashlib.sha256()
    for rel_path in FROZEN_TOURNAMENT_FILES:
        digest.update((repo_root / rel_path).read_bytes())
    return digest.hexdigest()


# The literal freeze point -- hard-coded from a one-time
# compute_tournament_hash() run against frozen_config.py's finalized
# contents. Any later byte-level edit trips verify_frozen_tournament().
FROZEN_TOURNAMENT_HASH = "d5df6e82a825e91b8814450c017859fe1686838f92bd44d414a3d8cf6be023c2"


def verify_frozen_tournament(repo_root: Path | None = None) -> None:
    """Raise RuntimeError if the tournament thresholds no longer match
    FROZEN_TOURNAMENT_HASH. run_tournament_once calls this before any
    judging, decision, or DB write -- the hard gate that enforces standing
    rule 1 for the tournament's own rules."""
    actual = compute_tournament_hash(repo_root)
    if actual != FROZEN_TOURNAMENT_HASH:
        raise RuntimeError(
            "tournament frozen config integrity check failed: "
            f"{FROZEN_TOURNAMENT_FILES} changed since FROZEN_TOURNAMENT_HASH "
            f"was locked (expected {FROZEN_TOURNAMENT_HASH}, got {actual}). "
            "Standing rule 1 forbids editing tournament thresholds while "
            "looking at results (D-06). If this change was reviewed and "
            "intentional, recompute via compute_tournament_hash() and commit "
            "the new value explicitly."
        )
