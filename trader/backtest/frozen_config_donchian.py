"""The hash-based freeze gate for the Donchian entrant's frozen surface
(the fifth independent gate, following the v1 -> v2 -> tournament ->
graduation precedent: one standalone gate per frozen surface, never an
extension of an existing gate's scope).

The Donchian evidence driver (run_donchian_evidence.py) calls
verify_frozen_donchian() FIRST, before any grid iteration or DB write --
the v2 engine it delegates to additionally verifies frozen_config_v2's own
five files (universe/regimes_v2/exit_grid/momentum_v2/breakout_v2),
untouched by this work.

Run `python -c "from trader.backtest import frozen_config_donchian as f;
print(f.compute_hash_donchian())"` to recompute FROZEN_HASH_DONCHIAN after
an intentional, reviewed change -- never after results exist (standing
rule 1).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

FROZEN_FILES_DONCHIAN: tuple[str, ...] = (
    "trader/backtest/strategies/donchian.py",
)


def compute_hash_donchian(repo_root: Path | None = None) -> str:
    """sha256 over FROZEN_FILES_DONCHIAN's raw bytes, in order."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]

    digest = hashlib.sha256()
    for rel_path in FROZEN_FILES_DONCHIAN:
        digest.update((repo_root / rel_path).read_bytes())
    return digest.hexdigest()


FROZEN_HASH_DONCHIAN = "63bd54c3e8d2d306f5e63d225643aa6312d4adccd1203dcb556f4fd4cb68bc93"


def verify_frozen_donchian(repo_root: Path | None = None) -> None:
    """Raise RuntimeError if the Donchian entry definitions no longer match
    FROZEN_HASH_DONCHIAN."""
    actual = compute_hash_donchian(repo_root)
    if actual != FROZEN_HASH_DONCHIAN:
        raise RuntimeError(
            "Donchian frozen config integrity check failed: "
            f"{FROZEN_FILES_DONCHIAN} changed since FROZEN_HASH_DONCHIAN was "
            f"locked (expected {FROZEN_HASH_DONCHIAN}, got {actual}). "
            "Standing rule 1 forbids editing entry definitions while looking "
            "at results. If this change was reviewed and intentional, "
            "recompute via compute_hash_donchian() and commit the new value "
            "explicitly."
        )
