"""The hash-based freeze gate for the MA-crossover entrant's frozen surface
(one standalone gate per frozen surface -- the established precedent).

Run `python -c "from trader.backtest import frozen_config_macross as f;
print(f.compute_hash_macross())"` to recompute FROZEN_HASH_MACROSS after an
intentional, reviewed change -- never after results exist (standing rule 1).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

FROZEN_FILES_MACROSS: tuple[str, ...] = (
    "trader/backtest/strategies/macross.py",
)


def compute_hash_macross(repo_root: Path | None = None) -> str:
    """sha256 over FROZEN_FILES_MACROSS's raw bytes, in order."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]

    digest = hashlib.sha256()
    for rel_path in FROZEN_FILES_MACROSS:
        digest.update((repo_root / rel_path).read_bytes())
    return digest.hexdigest()


FROZEN_HASH_MACROSS = "68ca9f61cbf9bb1e0afa48ce8612be0d0b75205576c4bad2b8b2fdb9d35f8f5a"


def verify_frozen_macross(repo_root: Path | None = None) -> None:
    """Raise RuntimeError if the MA-cross entry definitions no longer match
    FROZEN_HASH_MACROSS."""
    actual = compute_hash_macross(repo_root)
    if actual != FROZEN_HASH_MACROSS:
        raise RuntimeError(
            "MA-cross frozen config integrity check failed: "
            f"{FROZEN_FILES_MACROSS} changed since FROZEN_HASH_MACROSS was "
            f"locked (expected {FROZEN_HASH_MACROSS}, got {actual}). "
            "Standing rule 1 forbids editing entry definitions while looking "
            "at results. If this change was reviewed and intentional, "
            "recompute via compute_hash_macross() and commit the new value "
            "explicitly."
        )
