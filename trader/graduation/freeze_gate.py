"""The hash-based freeze gate for Phase 6's graduation checklist (standing
rule 1) -- the fourth independent gate, following the v1 -> v2 -> tournament
precedent (one standalone gate per frozen surface, never an extension of an
existing gate's scope).

Run `python -c "from trader.graduation import freeze_gate as f;
print(f.compute_graduation_hash())"` to recompute FROZEN_GRADUATION_HASH
after an intentional, reviewed change -- the only sanctioned way to move
the graduation freeze point, and never while looking at live paper results.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

FROZEN_GRADUATION_FILES: tuple[str, ...] = (
    "trader/graduation/frozen_checklist.py",
)


def compute_graduation_hash(repo_root: Path | None = None) -> str:
    """sha256 over FROZEN_GRADUATION_FILES' raw bytes, in order."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]

    digest = hashlib.sha256()
    for rel_path in FROZEN_GRADUATION_FILES:
        digest.update((repo_root / rel_path).read_bytes())
    return digest.hexdigest()


FROZEN_GRADUATION_HASH = "da3da573d0b2bcf2dcb451a861556284bde692838b444edbf9b69dd8ec297406"


def verify_frozen_graduation(repo_root: Path | None = None) -> None:
    """Raise RuntimeError if the checklist no longer matches its committed
    hash. run_graduation_review calls this before evaluating anything."""
    actual = compute_graduation_hash(repo_root)
    if actual != FROZEN_GRADUATION_HASH:
        raise RuntimeError(
            "graduation checklist integrity check failed: "
            f"{FROZEN_GRADUATION_FILES} changed since FROZEN_GRADUATION_HASH "
            f"was locked (expected {FROZEN_GRADUATION_HASH}, got {actual}). "
            "Standing rule 1 forbids editing graduation criteria while "
            "looking at results. If this change was reviewed and "
            "intentional, recompute via compute_graduation_hash() and "
            "commit the new value explicitly."
        )
