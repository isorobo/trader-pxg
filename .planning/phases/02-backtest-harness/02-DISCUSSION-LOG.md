# Phase 2: Backtest Harness - Discussion Log

> **Audit trail only.** Decisions live in CONTEXT.md.

**Date:** 2026-07-26
**Phase:** 2-backtest-harness
**Areas discussed:** Point-in-time iterator, Intraday approximation rules, Fee model, Slippage model, Exit engine, Ledger & reproducibility, Metrics, Sanity test
**Mode:** Auto-selected recommended defaults (non-interactive session, owner's standing auto-advance directive). Every selection overridable before planning.

---

## Point-in-Time Iterator

| Option | Selected |
|--------|----------|
| Physical slice ≤ t (lookahead impossible by construction) | ✓ |
| Flag-based "don't peek" convention | |

## Intraday Approximation (daily bars)

| Option | Selected |
|--------|----------|
| Conservative fills: next-bar-open entries, worse-of stop/gap fills, stop wins stop-vs-TP ties | ✓ |
| Optimistic close-fill model | |

## Fee Model

| Option | Selected |
|--------|----------|
| Static per-venue table; IBKR fixed tier; Kraken taker-only 0.26% (pessimistic) | ✓ |
| Tiered/maker-aware modelling | deferred until live fill data exists |

## Slippage Model

| Option | Selected |
|--------|----------|
| Per-asset-class % (0.05% / 2% / 4%), config parameters | ✓ |
| Volume-dependent impact model | over-engineering without intraday data |

## Exit Engine

| Option | Selected |
|--------|----------|
| Frozen dataclass profiles, immutability enforced by type; documented evaluation order | ✓ |
| Dict-based mutable profiles | violates standing rule 2 |

## Ledger & Reproducibility

| Option | Selected |
|--------|----------|
| backtest_runs + backtest_trades in shared data/trader.db, seeded reproducible runs | ✓ |
| Separate DB file per run | fragments later attribution queries |

## Metrics

| Option | Selected |
|--------|----------|
| PF, Sharpe (√252, rf=0), max DD, win rate, avg win/loss, fees; dict + markdown report | ✓ |

## Sanity Test

| Option | Selected |
|--------|----------|
| Seeded random strategy as a failing-if-profitable pytest with pinned tolerance band | ✓ |
| Manual one-off script | not a standing guarantee |

## Claude's Discretion

- Module layout, dataclass details, report formatting, tolerance band derivation.

## Deferred Ideas

- Intraday data, maker fees, walk-forward tooling, portfolio sizing (Phase 4).
