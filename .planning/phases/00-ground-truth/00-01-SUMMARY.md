---
phase: 00-ground-truth
plan: 01
subsystem: infra
tags: [python, venv, pip, yfinance, coingecko, dotenv, pytest, ruff]

# Dependency graph
requires: []
provides:
  - trader/ src-layout package skeleton (trader/, trader/ground_truth/)
  - Pinned requirements.txt (yfinance 1.5.2, requests 2.34.2, python-dotenv 1.2.2, finviz 2.0.0, pytest 9.1.1, ruff 0.16.0)
  - pyproject.toml with pytest testpaths and ruff config
  - .env.example documenting COINGECKO_API_KEY
  - Working .venv/ with all six dependencies installed and importable
  - Real .env with a working CoinGecko Demo API key
  - data/, reports/, tests/, scripts/ directories
affects: [00-02, 00-03, 00-04, 00-05, 01-accounts-data-plumbing]

# Tech tracking
tech-stack:
  added: [yfinance, requests, python-dotenv, finviz, pytest, ruff]
  patterns: [src-layout trader/ package, pinned requirements.txt, pyproject.toml-based pytest/ruff config]

key-files:
  created:
    - requirements.txt
    - .env.example
    - pyproject.toml
    - trader/__init__.py
    - trader/ground_truth/__init__.py
  modified:
    - .gitignore

key-decisions:
  - "Fixed pre-existing .gitignore .env.* pattern with a !.env.example negation so the documented placeholder can be committed while real secrets stay excluded"
  - "Left the existing root .gitignore's broader Python/data coverage in place rather than overwriting it, since it already satisfied the plan's required literal lines (.env, data/, no reports/ line)"

patterns-established:
  - "Pattern 1: src-layout trader/ package with __init__.py markers per subsystem folder"
  - "Pattern 2: Secrets flow through .env (gitignored) with .env.example documenting variable names only"

requirements-completed: [DATA-01]

# Metrics
duration: 26min
completed: 2026-07-26
---

# Phase 0 Plan 01: Repo Skeleton and Config Summary

**Pinned six-package Python environment (yfinance, requests, python-dotenv, finviz, pytest, ruff) with src-layout trader/ package skeleton and a working CoinGecko demo API key in .env**

## Performance

- **Duration:** 26 min (excludes the human-action checkpoint wait for CoinGecko signup)
- **Started:** 2026-07-25T23:45:00Z
- **Completed:** 2026-07-26T00:10:59Z
- **Tasks:** 3
- **Files modified:** 6 (5 created, 1 modified)

## Accomplishments
- Created the `trader/` src-layout package skeleton (`trader/`, `trader/ground_truth/`) with pinned `requirements.txt`, `pyproject.toml` (pytest + ruff config), and `.env.example`
- Created `.venv/` and installed all six pinned dependencies (plus transitive dependencies) — all imports verified, `yfinance` confirmed at exactly 1.5.2
- Obtained a CoinGecko Demo API key and verified it loads correctly via `python-dotenv` from a gitignored `.env`

## Task Commits

Each task was committed atomically:

1. **Task 1: Create package skeleton, pinned dependency list, and config files** - `32a4c12` (chore)
2. **Task 2: Create the virtual environment and install pinned dependencies** - no commit (`.venv/` is gitignored by design; no trackable file changes)
3. **Task 3: Obtain a CoinGecko Demo API key and store it in .env** - no commit (`.env` is gitignored by design; no trackable file changes)

**Plan metadata:** (this commit, following SUMMARY.md write)

_Note: Tasks 2 and 3 are environment/secret setup steps whose outputs (`.venv/`, `.env`) are intentionally excluded from git — see files_modified in 00-01-PLAN.md frontmatter._

## Files Created/Modified
- `requirements.txt` - Six pinned dependencies matching 00-RESEARCH.md Standard Stack
- `.env.example` - Documents `COINGECKO_API_KEY` variable name, no real value
- `pyproject.toml` - `[tool.pytest.ini_options]` testpaths, `[tool.ruff]` line-length
- `trader/__init__.py` - Package marker (src layout)
- `trader/ground_truth/__init__.py` - Package marker (src layout, Phase 0 module)
- `.gitignore` - Added `!.env.example` negation (see Deviations below)
- `data/`, `reports/`, `tests/`, `scripts/` - Placeholder directories for later plans
- `.venv/` - Virtual environment, gitignored, not tracked
- `.env` - Real secrets file, gitignored, not tracked

## Decisions Made
- Kept the existing, more comprehensive root `.gitignore` rather than replacing it with the plan's minimal literal-line list, since it already satisfied every acceptance criterion (`.env`, `data/` present; no `reports/` line)
- Added a `!.env.example` negation line rather than removing the broader `.env.*` pattern, preserving the intent to exclude all other `.env.*` variants (e.g. `.env.local`, `.env.production`) while allowing the documented example file through

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed .gitignore pattern shadowing .env.example**
- **Found during:** Task 1 (Create package skeleton, pinned dependency list, and config files)
- **Issue:** The project's pre-existing root `.gitignore` contained a `.env.*` glob (line 3) intended to catch environment-variant files, but it also matched `.env.example`, which the plan requires to be committed as documentation. `git check-ignore .env.example` confirmed it was being silently ignored.
- **Fix:** Added `!.env.example` immediately after the `.env.*` line to negate the match for that one file, while `.env` and any other `.env.*` variant remain ignored.
- **Files modified:** `.gitignore`
- **Verification:** `git check-ignore .env.example` now exits non-zero (not ignored); `.env.example` appears as untracked/added in `git status`; `.env` and other `.env.*` patterns remain ignored per the plan's `<verification>` check.
- **Committed in:** `32a4c12` (Task 1 commit)

**2. [Mid-execution correction, orchestrator-handled] User initially pasted the CoinGecko key into .env.example instead of .env**
- **Found during:** Task 3 checkpoint resolution (reported by orchestrator, not discovered independently by this executor)
- **Issue:** The real API key was briefly present in `.env.example`, the file intended to be committed to git — a near-miss on the standing rule that secrets never reach git.
- **Fix:** Orchestrator moved the key to `.env` and restored `.env.example` to the placeholder line `COINGECKO_API_KEY=` before this executor resumed. Verified on resume: `.env.example` content is exactly `COINGECKO_API_KEY=`; `.env` is untracked (`git ls-files .env` empty) and gitignored (`git check-ignore .env` exits 0).
- **Files modified:** `.env`, `.env.example` (both corrected before this executor's verification step; no further action needed)
- **Verification:** Confirmed post-fix state directly — no secret ever entered git history (checked `git status`/`git ls-files` before any commit in this session touched these files).
- **Committed in:** N/A — `.env` is gitignored and never committed; `.env.example` content unchanged from the Task 1 commit

---

**Total deviations:** 2 (1 auto-fixed by this executor under Rule 3, 1 corrected by the orchestrator before resume and independently verified by this executor)
**Impact on plan:** Both fixes were necessary to satisfy the standing rule "secrets never reach git" and the plan's own acceptance criteria. No scope creep.

## Issues Encountered
None beyond the deviations documented above.

## User Setup Required

**External service required manual configuration — CoinGecko Demo API key.**
- User created a CoinGecko developer account and Demo API key via https://www.coingecko.com/en/developers/dashboard
- Key stored in `.env` at the project root as `COINGECKO_API_KEY=<key>`
- Verified: `.env` is gitignored and untracked, contains a non-empty value matching the expected `CG-...` prefix format, and loads correctly through `python-dotenv`'s `load_dotenv()`

## Next Phase Readiness
- `.venv/` is fully provisioned; downstream Phase 0 plans (source adapters, poller, report) can rely on all six pinned packages being importable
- `.env` holds a working `COINGECKO_API_KEY`; the CoinGecko `/coins/markets` and `/coins/{id}/history` calls planned in later tasks can authenticate immediately
- `trader/ground_truth/` package directory exists and is ready to receive `sources.py`, `poll.py`, `db.py`, `report.py` in subsequent plans
- No blockers identified for Plan 00-02

---
*Phase: 00-ground-truth*
*Completed: 2026-07-26*
