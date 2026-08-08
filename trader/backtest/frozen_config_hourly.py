"""The hash-based freeze gate for the intraday (1h) track's frozen
surface: both hourly entry-signal modules AND the hourly exit grid +
windows -- one standalone gate per frozen surface, the established
precedent.

Run `python -c "from trader.backtest import frozen_config_hourly as f;
print(f.compute_hash_hourly())"` to recompute FROZEN_HASH_HOURLY after an
intentional, reviewed change -- never after results exist (standing
rule 1).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

FROZEN_FILES_HOURLY: tuple[str, ...] = (
    "trader/backtest/strategies/hourly_reversion.py",
    "trader/backtest/strategies/hourly_squeeze.py",
    "trader/backtest/hourly_grid.py",
)


def compute_hash_hourly(repo_root: Path | None = None) -> str:
    """sha256 over FROZEN_FILES_HOURLY's raw bytes, in order."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]

    digest = hashlib.sha256()
    for rel_path in FROZEN_FILES_HOURLY:
        digest.update((repo_root / rel_path).read_bytes())
    return digest.hexdigest()


FROZEN_HASH_HOURLY = "853d3e3fbc50e91eb87d0e400d029436f1c1a67898efef4f7e7d2e3f15b14d05"


def verify_frozen_hourly(repo_root: Path | None = None) -> None:
    """Raise RuntimeError if the hourly track's frozen surface no longer
    matches FROZEN_HASH_HOURLY."""
    actual = compute_hash_hourly(repo_root)
    if actual != FROZEN_HASH_HOURLY:
        raise RuntimeError(
            "hourly frozen config integrity check failed: "
            f"{FROZEN_FILES_HOURLY} changed since FROZEN_HASH_HOURLY was "
            f"locked (expected {FROZEN_HASH_HOURLY}, got {actual}). "
            "Standing rule 1 forbids editing entry/exit definitions while "
            "looking at results. If this change was reviewed and "
            "intentional, recompute via compute_hash_hourly() and commit "
            "the new value explicitly."
        )
