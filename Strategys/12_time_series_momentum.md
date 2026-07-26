# 12 — Time-Series Momentum (12-Month) ⭐ Added

## Core Idea
The most academically documented anomaly in finance: assets that have gone up over the past ~12 months tend to keep going up over the next 1–12 months (and vice versa). Unlike everything else in this library, this is a slow, position-trading strategy — decisions monthly, not intraday.

## Rules (simplest robust version)
1. On the last trading day of each month, compute each asset's 12-month return (common refinement: skip the most recent month — "12-1 momentum")
2. **Long** assets with positive 12-month return (or above their 10-month SMA — nearly equivalent)
3. **Flat/cash** (or short, if aggressive) assets with negative 12-month return
4. Rebalance monthly. That's it.

**Stop loss:** none intra-month — the monthly rebalance *is* the exit mechanism.
**Sizing:** equal weight, or inverse-volatility weight across assets.

## Best Markets
- Diversified ETF universe: equities, bonds, gold, commodities, REITs
- Futures (this is essentially what CTA/managed-futures funds run at scale)

## Avoid
- Applying it to one single asset — the edge comes from running it across many
- Judging it on weeks or months — this strategy is measured in years
- Sharp V-shaped reversals (e.g., March 2020) are its known weak spot: it exits late and re-enters late

## Stats (rough)
- Win rate: 45–60% of monthly decisions
- Historically improved risk-adjusted returns vs buy-and-hold across ~a century of data and dozens of markets — but with multi-year stretches of underperformance

## Notes for Automation
Almost embarrassingly easy to code — one calculation per asset per month — which makes it a great "always on" backbone for AI TRADRR while faster strategies trade around it. Extremely well documented (Moskowitz/Ooi/Pedersen "Time Series Momentum"; Faber's 10-month SMA model), so you can verify your implementation against published results.
