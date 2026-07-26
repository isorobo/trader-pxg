"""The hash-based freeze gate for Phase 3's v2 frozen surface (T-03-21).

Mirrors trader/backtest/frozen_config.py's exact hashing/verify pattern --
a NEW, standalone module, not an extension of v1's frozen_config.py, whose
own FROZEN_FILES/FROZEN_HASH/verify_frozen() are never modified and never
called from here. The two gates are fully independent: v1's sweep/OOS
entrypoints stay hash-gated by v1's own frozen_config.py; v2's entrypoints
(Plan 03-08) call verify_frozen_v2() instead.

v2's frozen input surface (D-13/D-14/D-15) is 5 files: universe.py and
exit_grid.py are included even though their content is unchanged from v1 --
D-13/D-15 keep them as part of what v2 sweeps depend on -- alongside the
two new v2-only modules (regimes_v2.py) and the two new entry-variant
registries (momentum_v2.py, breakout_v2.py).

Run `python -c "from trader.backtest import frozen_config_v2 as f;
print(f.compute_hash_v2())"` to recompute FROZEN_HASH_V2 after an
intentional, reviewed change to any FROZEN_FILES_V2 entry -- the only
sanctioned way to move the v2 freeze point.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Relative paths, hashed in this exact order. Path(__file__).resolve() is
# .../trader/backtest/frozen_config_v2.py; parents[0]=trader/backtest,
# parents[1]=trader, parents[2]=repo root.
FROZEN_FILES_V2: tuple[str, ...] = (
    "trader/backtest/universe.py",
    "trader/backtest/regimes_v2.py",
    "trader/backtest/exit_grid.py",
    "trader/backtest/strategies/momentum_v2.py",
    "trader/backtest/strategies/breakout_v2.py",
)


def compute_hash_v2(repo_root: Path | None = None) -> str:
    """Return the sha256 hex digest over FROZEN_FILES_V2's raw bytes, in
    order.

    `repo_root` defaults to this repo's root (three levels up from this
    file); tests pass a tmp_path copy to simulate tampering without
    touching the real committed files. This is a fresh, small
    implementation -- not a call into frozen_config.compute_hash, since
    that function's FROZEN_FILES is module-scoped to v1's own 3-file list
    with no override parameter.
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]

    digest = hashlib.sha256()
    for rel_path in FROZEN_FILES_V2:
        digest.update((repo_root / rel_path).read_bytes())
    return digest.hexdigest()


# The literal v2 freeze point -- hard-coded from a one-time
# compute_hash_v2() run against universe.py/regimes_v2.py/exit_grid.py/
# momentum_v2.py/breakout_v2.py's finalized contents. Any later byte-level
# edit to any of the five files changes compute_hash_v2()'s return value
# and trips verify_frozen_v2() below.
FROZEN_HASH_V2 = "0fba0822e0d10db491c87b439884dfd0cb31ad6cbc830caae3434754e556089f"


def verify_frozen_v2(repo_root: Path | None = None) -> None:
    """Raise RuntimeError if FROZEN_FILES_V2 no longer match FROZEN_HASH_V2.

    Callers (v2 sweep/OOS entrypoints, Plan 03-08) must invoke this before
    any grid iteration, regime lookup, or DB write -- the hard, uncatchable
    gate that enforces standing rule 1 for v2's regime windows and entry
    variants specifically, fully independent of v1's own
    frozen_config.verify_frozen().
    """
    actual = compute_hash_v2(repo_root)
    if actual != FROZEN_HASH_V2:
        raise RuntimeError(
            "v2 frozen config integrity check failed: one or more of "
            f"{FROZEN_FILES_V2} has changed since FROZEN_HASH_V2 was locked "
            f"(expected {FROZEN_HASH_V2}, got {actual}). Standing rule 1 "
            "forbids editing graduation/kill criteria -- or the v2 regime/"
            "entry-variant definitions that gate them -- while looking at "
            "results (D-13's v2 pre-registration). If this change was "
            "reviewed and intentional, recompute FROZEN_HASH_V2 via "
            "compute_hash_v2() and commit the new value explicitly."
        )
