---
phase: 00-ground-truth
verified: 2026-07-26T13:10:00Z
status: human_needed
score: 8/8 must-haves verified (build-complete); 1 wall-clock item outstanding
overrides_applied: 0
human_verification:
  - test: "Confirm the two-week continuous-runtime window for DATA-04 has elapsed and the logger is still healthy"
    expected: "On or after 2026-08-09, `schtasks /query /tn \"TraderGroundTruthPoll\" /v /fo list` still reports `Scheduled Task State: Enabled` with recent `poll_runs` activity, and re-running `.venv\\Scripts\\python.exe -m trader.ground_truth.report` shows a coverage percentage well above the single-poll baseline and a real, multi-day up/down split (including populated Next-Day Close values, which require a second calendar day to exist)."
    why_human: "This is a wall-clock requirement (DATA-04: 'runs continuously for two weeks minimum'). The clock started 2026-07-26 and cannot complete before 2026-08-09 regardless of code state. No grep or test run can shortcut elapsed time; a human must check back on/after that date."
---

# Phase 0: Ground Truth Verification Report

**Phase Goal:** Find out what the "+400% gainers" actually resolve to, with real numbers.
**Verified:** 2026-07-26T13:10:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

Derived from ROADMAP/REQUIREMENTS DATA-01…04 and merged with each plan's `must_haves.truths`.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Snapshot logger polls a stock gainers feed and CoinGecko top movers every 15 minutes (DATA-01) | VERIFIED | `scripts/poll_task.xml` registers `TraderGroundTruthPoll` with `<Interval>PT15M</Interval>`. Live `schtasks /query` (run by this verifier) confirms `Scheduled Task State: Enabled`, `Repeat: Every: 0 Hour(s), 15 Minute(s)`, `Last Run Time: 26/07/2026 12:45:00 PM`, `Last Result: 0` (success — not just registered, actually fired once already and succeeded), `Next Run Time: 26/07/2026 1:00:00 PM`. |
| 2 | Every flagged ticker is logged to SQLite with timestamp, price, and % gain at snapshot time (DATA-02) | VERIFIED | Live query against `data/trader.db`: `snapshots` table has columns `poll_ts, source, ticker, coingecko_id, price, pct_gain, rank, market_open, created_at`; contains 100 stock rows + 100 crypto rows across 2 real poll runs, all crypto rows have non-null `coingecko_id`. |
| 3 | Daily report shows, for each flagged ticker, the same-day close and next-day close (DATA-03) | VERIFIED | `reports/2026-07-26.md` (real, non-fixture output) contains a `Same-Day Close` and `Next-Day Close` column for all 100 tickers, a `Coverage: 1/674 polls (0.1%)` line, and the exit-criterion sentence: "Of 100 tickers flagged, 18 ended the day up and 82 dumped from where the scanner first saw them." Next-Day Close is `N/A` for every row — expected, since only one calendar day has elapsed since the clock started today. |
| 4 | Logger runs continuously for two weeks minimum and keeps running after that (DATA-04) | UNCERTAIN (wall-clock gate) | Build is complete and live-verified: Task Scheduler is registered, Enabled, and has already fired at least once successfully outside of manual invocation (`Last Result: 0` at `12:45:00 PM`, distinct from the manual `--once` run at `00:39:45 UTC` used for Plan 00-05's live verification). The two-week minimum runtime (2026-07-26 → on/after 2026-08-09) has not elapsed as of this verification (2026-07-26). This is a wall-clock requirement, not a code gap — see Human Verification below. |

**Score:** 3/4 truths fully VERIFIED now; 1/4 (DATA-04) build-verified but gated on elapsed wall-clock time, routed to human verification.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `requirements.txt` | Six pinned deps matching 00-RESEARCH.md | VERIFIED | Exactly 6 lines: `yfinance==1.5.2`, `requests==2.34.2`, `python-dotenv==1.2.2`, `finviz==2.0.0`, `pytest==9.1.1`, `ruff==0.16.0`. `pip show` on all six confirms installed versions match exactly. |
| `.env.example` | Documents `COINGECKO_API_KEY` only | VERIFIED | Contains exactly `COINGECKO_API_KEY=` |
| `.env` (gitignored) | Real, working CoinGecko key | VERIFIED | Loads via `python-dotenv`; key present, 27 chars, `CG-` prefix (value not printed, per threat model). |
| `pyproject.toml` | pytest + ruff config | VERIFIED | `testpaths = ["tests"]` under `[tool.pytest.ini_options]`; `line-length = 100` under `[tool.ruff]`. |
| `.gitignore` | Excludes `.env`, `data/`; allows `.env.example`; `reports/` added at D-12 discretion | VERIFIED | Contains `.env`, `.env.*`, `!.env.example`, `data/`, `reports/` (reports/ addition documented and consistent with D-12 "Claude's discretion"). |
| `trader/ground_truth/__init__.py` | Package marker | VERIFIED | Exists. |
| `trader/ground_truth/db.py` | Connection, schema, insert, coverage-query helpers | VERIFIED | Exports `get_connection, ensure_schema, insert_snapshot_rows, record_poll_run, query_flagged_tickers_since, query_poll_run_coverage`. WAL mode confirmed live (`PRAGMA journal_mode` → `wal`). Three tables (`snapshots`, `poll_runs`, `schema_version`) confirmed present in the real `data/trader.db`. Parameterized-only inserts (read source, no f-string SQL). |
| `trader/ground_truth/sources.py` | Stock + crypto adapters with fallback | VERIFIED | `StockGainersSource`, `CryptoMoversSource`, `SourceUnavailableError` all present and substantive (read full source — real yfinance/finviz/CoinGecko HTTP logic, not stubs). |
| `trader/ground_truth/poll.py` | Orchestration entrypoint | VERIFIED | `run_poll_once`, `is_market_hours`, `main` all present, wired to both `sources.py` and `db.py`; independent try/except per source confirmed in source (read full file). |
| `scripts/poll.bat`, `scripts/poll_task.xml` | Task Scheduler launcher + task definition | VERIFIED | `.bat` sets cwd and calls the exact venv interpreter with `--once`; `.xml` contains `PT15M` interval, `StartWhenAvailable=true`, `P9999D` duration. Registered task confirmed live via `schtasks /query`. |
| `trader/ground_truth/report.py` | Daily report generator | VERIFIED | All 7 exported functions present; live output at `reports/2026-07-26.md` is real, non-fixture, non-empty, contains required columns and summary lines. |
| `data/trader.db` | First real snapshots + poll_runs rows | VERIFIED | 200 snapshot rows (100 stock + 100 crypto), 2 poll_runs rows, `schema_version` seeded. |
| `reports/{today}.md` | First real daily report, non-zero ticker count | VERIFIED | 100 ticker rows, real coverage stat, real up/down split. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `trader/ground_truth/sources.py` | `https://api.coingecko.com/api/v3/coins/markets` | `requests.get` + `x-cg-demo-api-key` header | WIRED | Confirmed in source; header value sourced from `os.environ.get("COINGECKO_API_KEY", "")`, never hardcoded. Live smoke test (Plan 00-02) and live poll runs (Plan 00-05, this verification) both returned real rows. |
| `trader/ground_truth/db.py` | `data/trader.db` | `sqlite3.connect` + `PRAGMA journal_mode=WAL` | WIRED | Live `PRAGMA journal_mode` query on the real db returns `wal`. |
| `trader/ground_truth/poll.py` | `trader/ground_truth/db.py` | `insert_snapshot_rows` + `record_poll_run` | WIRED | Confirmed in source; live db contains rows written this way. |
| Windows Task Scheduler | `scripts/poll.bat` | `schtasks /create /xml`, `PT15M` | WIRED | Confirmed live via `schtasks /query` — task fired automatically at least once (`Last Result: 0`) independent of any manual invocation. |
| `trader/ground_truth/report.py` | `trader/ground_truth/db.py` | `query_flagged_tickers_since` + `query_poll_run_coverage` | WIRED | Live report reflects real db contents (100 real tickers, real coverage denominator of 674 expected polls). |
| `trader/ground_truth/report.py` | `https://api.coingecko.com/api/v3/coins/{id}/history` | DD-MM-YYYY date param | WIRED | `grep "%d-%m-%Y"` confirms format used; live report shows real crypto same-day closes (e.g. `AVAX: 6.74 -> 6.77`). |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `reports/2026-07-26.md` | `rows` (ticker table) | `compute_report_rows` ← `query_flagged_tickers_since` ← real `snapshots` table | Yes — 100 real tickers with real prices/gains, real fetched closes for stocks/crypto not blocked by weekend/history gaps | FLOWING |
| `poll_runs` table | poll summary | `run_poll_once` → real HTTP calls to Yahoo Finance / CoinGecko | Yes — 2 real rows, one from manual `--once`, one from an actual Task Scheduler fire | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full pytest suite is green | `.venv\Scripts\python.exe -m pytest tests/ -q` | `24 passed in 2.12s` | PASS |
| Real snapshot rows exist with correct shape | sqlite query against `data/trader.db` | `[('crypto', 100), ('stock', 100)]`, 0 null `coingecko_id` on crypto rows | PASS |
| Task Scheduler is live and has actually fired (not just registered) | `schtasks /query /tn "TraderGroundTruthPoll" /v /fo list` | `Scheduled Task State: Enabled`, `Last Result: 0`, `Repeat: Every: 0 Hour(s), 15 Minute(s)` | PASS |
| Installed package versions match `requirements.txt` pins | `pip show` x6 | All six match exactly (`yfinance 1.5.2`, `requests 2.34.2`, `python-dotenv 1.2.2`, `finviz 2.0.0`, `pytest 9.1.1`, `ruff 0.16.0`) | PASS |
| Report answers the phase's exit-criterion sentence with real numbers | Read `reports/2026-07-26.md` | "Of 100 tickers flagged, 18 ended the day up and 82 dumped from where the scanner first saw them." | PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` convention exists in this project (Windows/pytest project, no bash probe scripts declared in any PLAN/SUMMARY). Skipped — no runnable probes to execute per Step 7c's discovery criteria.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|--------------|-------------|--------------|--------|----------|
| DATA-01 | 00-01, 00-02, 00-03 | Snapshot logger polls a stock gainers feed and CoinGecko top movers every 15 minutes | SATISFIED | Task Scheduler confirmed Enabled, 15-min interval, at least one successful automatic fire (`Last Result: 0`), independent of manual invocation. |
| DATA-02 | 00-02, 00-03 | Every flagged ticker logged to SQLite with timestamp, price, % gain at snapshot time | SATISFIED | Live db query confirms all required fields present and populated on 200 real rows. |
| DATA-03 | 00-04 | Daily report shows same-day close and next-day close for each flagged ticker | SATISFIED | Live report contains both columns for all 100 tickers; next-day is correctly `N/A` pending elapsed time, per the report's own error-tolerant contract, not a defect. |
| DATA-04 | 00-03, 00-05 | Logger runs continuously for two weeks minimum and keeps running after that | NEEDS HUMAN (wall-clock) | Build complete, registration live-confirmed, one automatic successful fire observed. The 2-week minimum (2026-07-26 → on/after 2026-08-09) has not elapsed; no code gap exists. |

No orphaned requirements found — DATA-01…04 are the full Phase 0 requirement set per `.planning/REQUIREMENTS.md`, and all four are claimed across the five plans' `requirements:` frontmatter.

### Anti-Patterns Found

None. Scanned `trader/ground_truth/*.py`, `scripts/*.bat`, `scripts/*.xml`, `tests/*.py` for `TODO|FIXME|XXX|TBD|HACK|PLACEHOLDER` and empty-implementation patterns. The single match (`db.py` line 66, "parameterized placeholders") is a docstring describing SQL parameter binding, not a debt marker — false positive from substring overlap ("placeholders" contains "placeholder"), reviewed and dismissed.

### Human Verification Required

### 1. Two-week continuous runtime (DATA-04)

**Test:** On or after 2026-08-09, run `schtasks /query /tn "TraderGroundTruthPoll" /v /fo list` and `.venv\Scripts\python.exe -m trader.ground_truth.report`.
**Expected:** Task Scheduler still reports `Scheduled Task State: Enabled` with recent `poll_runs` activity; the report's coverage percentage has climbed well above the current single-poll baseline (0.1%); the up-vs-dumped summary line reflects a real multi-day sample; `Next-Day Close` values are now populated for tickers flagged on days that have since closed.
**Why human:** DATA-04 is explicitly a wall-clock requirement ("runs continuously for two weeks minimum and keeps running after that"). No static check, test, or grep can verify elapsed time. This is the sole outstanding item — all code, scheduling, and live-run verification for this phase is otherwise complete as of 2026-07-26.

### Gaps Summary

No build gaps found. All must-haves from every plan's frontmatter (00-01 through 00-05) were checked against the live codebase and live system state — package installs, schema, source adapters, poll orchestration, Task Scheduler registration, and the report generator all exist, are substantive (not stubs), are wired together, and have been proven against real external services and real accumulated data, including one automatic (non-manual) Task Scheduler fire observed directly during this verification.

The only unmet item is DATA-04's two-week minimum runtime, which is a wall-clock gate, not a code or wiring defect. The clock opened 2026-07-26 and cannot complete before 2026-08-09 regardless of further code changes. Per plan 00-05's own SUMMARY.md, "Phase completion is gated on this clock" — this was anticipated and documented at execution time, not discovered as a surprise during verification.

**Recommendation:** Do not re-run this verification before 2026-08-09. When the window has elapsed, re-verify by running the two commands listed under Human Verification above and confirming their expected output; if both hold, this phase should move to `status: passed` without further plan work being required.

---

*Verified: 2026-07-26T13:10:00Z*
*Verifier: Claude (gsd-verifier)*
