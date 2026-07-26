---
status: partial
phase: 00-ground-truth
source: [00-VERIFICATION.md]
started: 2026-07-26T01:30:00Z
updated: 2026-07-26T01:30:00Z
---

## Current Test

[awaiting human testing — wall-clock gated]

## Tests

### 1. Two-week continuous collection window (DATA-04)

expected: On or after 9 August 2026 — (a) `.venv\Scripts\python.exe -m trader.ground_truth.report` shows the up-vs-dumped summary with two weeks of accumulated real numbers and a healthy coverage stat; (b) `schtasks /query /tn "TraderGroundTruthPoll"` still shows `Enabled` with recent successful runs; (c) `poll_runs` has recent rows.
result: [pending — window opened 2026-07-26, completes on/after 2026-08-09]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
