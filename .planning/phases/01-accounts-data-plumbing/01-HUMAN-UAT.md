---
status: partial
phase: 01-accounts-data-plumbing
source: [01-VERIFICATION.md]
started: 2026-07-26T02:30:00Z
updated: 2026-07-26T02:30:00Z
---

## Current Test

[awaiting human account actions]

## Tests

### 1. Independent Reserve KYC submitted (ACCT-03)

expected: Account created at independentreserve.com with NZ KYC submitted (ID + address). Submission counts; approval is a follow-up.
result: [pending — user deferred to later]

### 2. IBKR application submission confirmed (ACCT-01)

expected: IBKR portal shows the individual account application fully submitted (no pending-information banner). Paper account auto-grants on approval. User currently has portal access with paper-type account DUR285675.
result: [pending — submission unconfirmed]

### 3. Kraken verification + trade-only API keys (ACCT-02)

expected: Identity verification complete; API key created with Query Funds / Query Open Orders & Trades / Query Closed Orders & Trades / Modify Orders / Cancel-Close Orders ticked and Withdraw Funds visually confirmed DISABLED; KRAKEN_API_KEY and KRAKEN_API_SECRET present in .env only.
result: [pending — ID verification in progress]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
