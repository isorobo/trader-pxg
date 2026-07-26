# Account Provisioning Checklist — Phase 1

Tracks IBKR, Kraken, and Independent Reserve account provisioning per ACCT-01/02/03.
Per D-14, "submitted" is sufficient progress to unblock this checkpoint — code waves in
the other Phase 1 plans do not wait on approval. This file records status only; it never
holds a real secret value (standing rule 3).

---

## 1. IBKR (ACCT-01)

Apply at interactivebrokers.com as an **Individual** account. Per 01-RESEARCH.md Pitfall 4,
this is one application — the paper trading account (USD 1,000,000 virtual equity) is
auto-granted once the live account shows Approved in Client Portal. Do not apply for a paper
account separately.

**Status: In progress (application started) — 26 July 2026**

- [x] Individual account application started at interactivebrokers.com
- [ ] Photo ID uploaded
- [ ] Proof of residency uploaded
- [ ] Application submission confirmed complete (all sections filed)
- [ ] Live account shows Approved in Client Portal
- [ ] Paper trading account (USD 1,000,000 virtual equity) confirmed present — no separate signup needed

---

## 2. Kraken (ACCT-02)

Create a Kraken account, complete Kraken's own identity verification, then create an API
key under Settings -> API with trade-only permissions.

**Status: In progress (account created, verification and API key pending) — 26 July 2026**

- [x] Kraken account created
- [ ] Kraken identity verification submitted
- [ ] Kraken identity verification approved
- [ ] API key created under Settings -> API with exactly these ticked:
      Query Funds, Query Open Orders & Trades, Query Closed Orders & Trades,
      Modify Orders, Cancel/Close Orders
- [ ] These left unticked: Deposit Funds, Withdraw Funds, Query Ledger Entries,
      Export Data, Access WebSockets API
- [ ] **Withdraw Funds visually confirmed disabled** on the key's settings page (D-13,
      standing rule 3 — required before this item counts as complete)
- [ ] KRAKEN_API_KEY and KRAKEN_API_SECRET entered into `.env` (never into this file,
      never into `.env.example`, never into a commit)

---

## 3. Independent Reserve (ACCT-03)

Sign up with an NZD-capable account and submit KYC (government ID, selfie/liveness check,
proof of address). No code depends on this account until Phase 9. Approval turnaround is
an open question (01-RESEARCH.md Open Question 2) — non-blocking regardless of the answer.

**Status: Not started — 26 July 2026**

- [ ] Account created
- [ ] Government ID submitted
- [ ] Selfie/liveness check submitted
- [ ] Proof of address submitted
- [ ] KYC submission confirmed complete

---

## Summary

| Account | Status | Date |
|---------|--------|------|
| IBKR (ACCT-01) | In progress — application started | 26 July 2026 |
| Kraken (ACCT-02) | In progress — account created, verification + API key pending | 26 July 2026 |
| Independent Reserve (ACCT-03) | Not started | 26 July 2026 |

This checklist carries forward as a Pending Todo for STATE.md tracking until all three
items reach "approved." No secret values live in this file — see `.env` (gitignored) for
Kraken credentials once created.
