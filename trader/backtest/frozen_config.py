"""The hash-based freeze gate for Phase 3's frozen universe/regime/grid
config (T-03-06).

This module is the code-level enforcement of standing rule 1 ("never edit
graduation/kill criteria while looking at results") applied to
universe.py, regimes.py, and exit_grid.py: FROZEN_HASH is computed once,
after those three files were finalized, and hard-coded below as the literal
freeze point -- not a comment, not a convention. Every later sweep or OOS
validation entrypoint (Plan 03-03's run_tune_sweep, Plan 03-05's
run_oos_validation) must call verify_frozen() first, before any grid
iteration, regime lookup, or DB write, so a post-hoc edit to any of the
three frozen files is a hard, uncatchable failure rather than a silent
change to results already viewed.

Run `python -c "from trader.backtest import frozen_config as f;
print(f.compute_hash())"` to recompute FROZEN_HASH after an intentional,
reviewed change to any FROZEN_FILES entry -- the only sanctioned way to
move the freeze point.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Relative paths, hashed in this exact order. Path(__file__).resolve()
# is .../trader/backtest/frozen_config.py; parents[0]=trader/backtest,
# parents[1]=trader, parents[2]=repo root.
FROZEN_FILES: tuple[str, ...] = (
    "trader/backtest/universe.py",
    "trader/backtest/regimes.py",
    "trader/backtest/exit_grid.py",
)


def compute_hash(repo_root: Path | None = None) -> str:
    """Return the sha256 hex digest over FROZEN_FILES' raw bytes, in order.

    `repo_root` defaults to this repo's root (three levels up from this
    file); tests pass a tmp_path copy to simulate tampering without
    touching the real committed files.
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]

    digest = hashlib.sha256()
    for rel_path in FROZEN_FILES:
        digest.update((repo_root / rel_path).read_bytes())
    return digest.hexdigest()


# The literal freeze point -- hard-coded from a one-time compute_hash() run
# against universe.py/regimes.py/exit_grid.py's finalized contents. Any
# later byte-level edit to any of the three files changes compute_hash()'s
# return value and trips verify_frozen() below.
FROZEN_HASH = "561f50acaab836d07332ade0945de5c6431f167ff26c964c604cee585ff868df"


def verify_frozen(repo_root: Path | None = None) -> None:
    """Raise RuntimeError if FROZEN_FILES no longer match FROZEN_HASH.

    Callers (sweep/OOS entrypoints) must invoke this before any grid
    iteration, regime lookup, or DB write -- it is the hard gate that
    enforces standing rule 1 for universe/regime/grid config specifically.
    """
    actual = compute_hash(repo_root)
    if actual != FROZEN_HASH:
        raise RuntimeError(
            "Frozen config integrity check failed: one or more of "
            f"{FROZEN_FILES} has changed since FROZEN_HASH was locked "
            f"(expected {FROZEN_HASH}, got {actual}). Standing rule 1 "
            "forbids editing graduation/kill criteria -- or the "
            "universe/regime/exit-grid definitions that gate them -- "
            "while looking at results. If this change was reviewed and "
            "intentional, recompute FROZEN_HASH via compute_hash() and "
            "commit the new value explicitly."
        )
