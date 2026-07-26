---
phase: 5
slug: paper-trading-loop
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-26
updated: 2026-07-27
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (347 green entering) + hypothesis (installed) |
| **Config file** | pyproject.toml |
| **Quick run command** | `python -m pytest tests/ -q -x --deselect tests/test_backtest_sanity.py` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | fast loop ~25s; full suite ~85s (Phase 5 adds ~9 test files, expanded post plan-checker revision + residual fix) |

---

## Sampling Rate

- **After every task commit:** fast loop
- **After every plan wave:** full suite
- **Before `/gsd:verify-work`:** full suite green
- **Max feedback latency:** 30 seconds (fast loop)

**Live/manual exemptions:** IB Gateway install + login (05-08, human checkpoint), first live paper order round-trip (05-09, human-witnessed acceptance), Telegram token creation (05-08, human checkpoint), Task Scheduler registration (05-09, human-run schtasks per D-07 precedent), the two-week unattended window (05-09, wall-clock gate, like Phase 0's — auditable from the operations log + daily report).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01/T1 | 05-01 | 1 | PAPER-05 | T-05-01, T-05-09 | Migration 0005 (incl. pending_submit status) + frozen 5-config registry | integration (DB) | `python -m pytest tests/test_paper_ledger.py -x -q` | ❌ W0 | ⬜ pending |
| 05-01/T2 | 05-01 | 1 | PAPER-03, PAPER-05 | T-05-01, T-05-13, T-05-16 | Deterministic order_ref; persist-before-submit lifecycle; date-independent get_unresolved_orders (scoped) AND get_all_unresolved_orders (unscoped, RESIDUAL BLOCKER 1)/find_unresolved_match; get_pending_order_qty excludes pending_submit; retire idempotency | unit | `python -m pytest tests/test_idempotency.py tests/test_paper_ledger.py -x -q` | ❌ W0 | ⬜ pending |
| 05-02/T1 | 05-02 | 1 | PAPER-07 | — | NYSE trading-day gate | unit | `python -m pytest tests/test_calendar.py -x -q` | ❌ W0 | ⬜ pending |
| 05-02/T2 | 05-02 | 1 | PAPER-06 | T-05-02, T-05-07 | Telegram fire-and-forget, no secret leakage, scheduled_auth distinct entry type, CLI producer (BLOCKER 2) | unit (mocked requests) | `python -m pytest tests/test_alerts.py -x -q` | ❌ W0 | ⬜ pending |
| 05-03/T1 | 05-03 | 2 | PAPER-01, PAPER-02 | T-05-06 | Port 4002 only; whole-share rounding always floors | unit (mocked ib_async) | `python -m pytest tests/test_broker_ibkr.py -x -q` | ❌ W0 | ⬜ pending |
| 05-03/T2 | 05-03 | 2 | PAPER-02 | T-05-10 | Crypto sim never places a real order | unit (mocked ccxt) | `python -m pytest tests/test_broker_crypto_sim.py -x -q` | ❌ W0 | ⬜ pending |
| 05-04/T1 | 05-04 | 3 | PAPER-04 | T-05-04 | Conservative divergence classification (pending_submit excluded); combined halt gate | unit | `python -m pytest tests/test_reconciliation.py -x -q` | ❌ W0 | ⬜ pending |
| 05-04/T2 | 05-04 | 3 | PAPER-04 | T-05-08, T-05-14 | Only clear_halt.py can clear a halt; clear always appends manual_restart_required ops-log entry (BLOCKER 3) | unit | `python -m pytest tests/test_reconciliation.py -x -q -k clear_halt` | ❌ W0 | ⬜ pending |
| 05-05/T1 | 05-05 | 3 | PAPER-02 | T-05-05, T-05-13 | Self-computed MKT exits only; no resting stops; persist-before-submit + date-independent heal on exits | unit (mocked broker/ccxt) | `python -m pytest tests/test_guardian.py -x -q` | ❌ W0 | ⬜ pending |
| 05-05/T2 | 05-05 | 3 | PAPER-02 | T-05-09 | Rolling PF/drawdown/consecutive-loss auto-retire, frozen thresholds | unit | `python -m pytest tests/test_guardian.py -x -q -k kill_condition` | ❌ W0 | ⬜ pending |
| 05-05/T3 | 05-05 | 3 | PAPER-02 | T-05-15 | Real-time alert on new breaker trip (W1); twice-daily heartbeat with no 4th scheduled task (BLOCKER 4) | unit | `python -m pytest tests/test_guardian.py -x -q -k "breaker or heartbeat"` | ❌ W0 | ⬜ pending |
| 05-06/T1 | 05-06 | 4 | PAPER-01 | T-05-11, T-05-17 | Candidate scan/score; assign_exit_profile is DAY-STABLE, hashed on symbol alone, NO date component (RESIDUAL BLOCKER 1); no retired config assigned | unit | `python -m pytest tests/test_entry_pipeline.py -x -q -k "scan_candidates or assign_exit_profile"` | ❌ W0 | ⬜ pending |
| 05-06/T2 | 05-06 | 4 | PAPER-01 | T-05-03, T-05-05, T-05-13, T-05-16 | STEP0(unscoped heal, before scan/halt)->gate->sizer->round->per-candidate-heal->halt-gate->persist->submit, no bypass; STEP 0 proven to heal an orphan ABSENT from that run's candidates, not merely a re-firing one (RESIDUAL BLOCKER 1) | integration (mocked ib_async) | `python -m pytest tests/test_entry_pipeline.py -x -q` | ❌ W0 | ⬜ pending |
| 05-07/T1 | 05-07 | 5 | PAPER-07 | T-05-12 | Daily report paper-trading section incl. Manual Interventions tally (W2); never breaks Phase 0's report | unit | `python -m pytest tests/test_paper_daily_report.py -x -q` | ❌ W0 | ⬜ pending |
| 05-07/T2 | 05-07 | 5 | PAPER-07 | T-05-13, T-05-14, T-05-16 | REALISTIC multi-day heal scenario: all 5 live profiles, symbol proven NOT to re-fire on day 2, heal via STEP 0 only, crash->halt->clear->next-day heal (RESIDUAL BLOCKER 1); composed real-breaker-trip->zero-orders proof (W4); full suite green | integration + full suite | `python -m pytest -q` | ❌ W0 | ⬜ pending |
| 05-08/T1-T2 | 05-08 | 6 | PAPER-01, PAPER-06 | T-05-02, T-05-06 | Gateway install/login/API-enable; Telegram bot creation | manual | n/a — human checkpoint | n/a | ⬜ pending |
| 05-08/T3 | 05-08 | 6 | PAPER-01, PAPER-06 | — | Automated connect/disconnect + real Telegram send smoke test | manual verify of automated check | Claude-run connectivity smoke (not pytest) | n/a | ⬜ pending |
| 05-09/T1-T2 | 05-09 | 7 | PAPER-01, PAPER-03, PAPER-04, PAPER-07 | T-05-06 | Scheduler registration (3 tasks, no 4th for heartbeat); witnessed live paper order + reconciliation | manual | n/a — human checkpoint | n/a | ⬜ pending |
| 05-09/T3 | 05-09 | 7 | PAPER-07 | T-05-14 | Monitoring-window documentation + full ops runbook (scheduled_auth CLI, both halt-clear paths, heartbeat) | manual | n/a — human checkpoint | n/a | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — `paper_conn` fixture (05-01), `fake_ib` fixture (05-03)
- [ ] `tests/test_idempotency.py` — covers PAPER-03, incl. `find_unresolved_match` date-independent matching against both scoped and unscoped order lists (05-01, BLOCKER 1 / RESIDUAL BLOCKER 1)
- [ ] `tests/test_paper_ledger.py` — covers PAPER-05, incl. pending_submit lifecycle, `get_unresolved_orders` (scoped), `get_all_unresolved_orders` (unscoped, RESIDUAL BLOCKER 1), `heal_order`, `get_pending_order_qty` exclusion (05-01)
- [ ] `tests/test_calendar.py` — covers PAPER-07 trading-day gate (05-02)
- [ ] `tests/test_alerts.py` — covers PAPER-06, incl. the `ops_log --entry-type` CLI (05-02, BLOCKER 2)
- [ ] `tests/test_broker_ibkr.py` — covers PAPER-01/02 broker adapter, whole-share rounding (05-03)
- [ ] `tests/test_broker_crypto_sim.py` — covers PAPER-02 crypto sim leg (05-03)
- [ ] `tests/test_reconciliation.py` — covers PAPER-04, incl. clear_halt's manual_restart_required append (05-04, BLOCKER 3)
- [ ] `tests/test_guardian.py` — covers PAPER-02, D-01 kill-condition auto-retire, date-independent exit heal, real-time breaker alert, heartbeat (05-05, BLOCKER 1/4, W1)
- [ ] `tests/test_entry_pipeline.py` — covers PAPER-01, day-stable symbol-only profile assignment, STEP 0 unscoped heal pass proven against a NON-re-firing orphan, heal-before-halt ordering (05-06, RESIDUAL BLOCKER 1)
- [ ] `tests/test_paper_daily_report.py` — covers PAPER-07 daily report section incl. Manual Interventions tally (05-07, W2)
- [ ] `tests/test_recovery.py` — covers PAPER-07 REALISTIC multi-day crash-safety/heal with all 5 live profiles and a non-re-firing symbol (05-07, RESIDUAL BLOCKER 1), composed breaker-trip->zero-orders (05-07, W4)
- [ ] Framework install: `pip install ib_async pandas-market-calendars` (05-02/05-03)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| IB Gateway paper login (port 4002) | PAPER-01 | Human credentials + 2FA | 05-08: Owner installs Gateway, logs into paper account DUR285675, enables API |
| Telegram bot creation | PAPER-06 | Human's own Telegram account, BotFather conversation | 05-08: Owner creates bot, messages it once; Claude resolves chat_id and runs a real smoke send |
| Task Scheduler registration | PAPER-01/02/04/07 | Structure guidance defers registration to the human's own command (D-07 precedent) | 05-09: Owner runs the three `schtasks /create /xml` commands Claude provides verbatim (exactly three -- the heartbeat needs no fourth, BLOCKER 4) |
| First paper order round-trip | PAPER-01/03/04 | Real broker interaction | 05-09: One supervised entry order fills on paper; permId recorded; reconciliation matches |
| Weekly IBKR 2FA tap logging | PAPER-07 / exit gate | Human must run the CLI after each real-world tap | 05-09 runbook: `python -m trader.paper.ops_log --entry-type scheduled_auth --message "..."` (BLOCKER 2) |
| Phase 4 breaker-clear ops-log follow-up | PAPER-07 / exit gate | `trader.risk.clear_breaker` is unmodified and has no ops-log awareness | 05-09 runbook: run `trader.risk.clear_breaker` THEN separately `python -m trader.paper.ops_log --entry-type manual_restart_required --message "..."` (BLOCKER 3) |
| Two-week unattended window | PAPER-07 / exit gate | Wall clock | 05-09 opens it; verified later via `/gsd:verify-work`: operations log + daily reports (incl. the Manual Interventions tally, W2) show zero unplanned interventions and zero unexplained divergences; weekly 2FA taps logged as pre-registered `scheduled_auth` exceptions (D-13) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (checkpoint tasks in 05-08/05-09 use `<human-check>`/manual per the documented Live/manual exemptions)
- [x] Sampling continuity: no 3 consecutive autonomous tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s (fast loop)
- [x] `nyquist_compliant: true` set in frontmatter
- [x] Plan-checker BLOCKER 1-4 and W1-W4 revisions reflected in this map (planner-revision pass, 2026-07-27)
- [x] Residual BLOCKER 1 (day-stable symbol-only profile hash + STEP 0 unscoped heal pass + realistic non-re-firing test fixture) reflected in this map (planner-revision pass #2, 2026-07-27)

**Approval:** planned — pending execution
