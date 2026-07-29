"""The hash-based freeze gate for the RSI(2) entrant's frozen surface
(one standalone gate per frozen surface -- the established precedent).

Run `python -c "from trader.backtest import frozen_config_rsi2 as f;
print(f.compute_hash_rsi2())"` to recompute FROZEN_HASH_RSI2 after an
intentional, reviewed change -- never after results exist (standing
rule 1).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

FROZEN_FILES_RSI2: tuple[str, ...] = (
    "trader/backtest/strategies/rsi2.py",
)


def compute_hash_rsi2(repo_root: Path | None = None) -> str:
    """sha256 over FROZEN_FILES_RSI2's raw bytes, in order."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]

    digest = hashlib.sha256()
    for rel_path in FROZEN_FILES_RSI2:
        digest.update((repo_root / rel_path).read_bytes())
    return digest.hexdigest()


FROZEN_HASH_RSI2 = "1ac670bbb5030626bfce90ca95a908127b802f2ca619e08cd414f4a614f5425c"


def verify_frozen_rsi2(repo_root: Path | None = None) -> None:
    """Raise RuntimeError if the RSI(2) entry definitions no longer match
    FROZEN_HASH_RSI2."""
    actual = compute_hash_rsi2(repo_root)
    if actual != FROZEN_HASH_RSI2:
        raise RuntimeError(
            "RSI2 frozen config integrity check failed: "
            f"{FROZEN_FILES_RSI2} changed since FROZEN_HASH_RSI2 was locked "
            f"(expected {FROZEN_HASH_RSI2}, got {actual}). Standing rule 1 "
            "forbids editing entry definitions while looking at results. If "
            "this change was reviewed and intentional, recompute via "
            "compute_hash_rsi2() and commit the new value explicitly."
        )
