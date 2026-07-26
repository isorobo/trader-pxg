# 09 — Statistical Pairs Trading

## Core Idea
Two historically correlated assets (e.g., two banks, two oil majors) usually move together. When they temporarily diverge without a fundamental reason, buy the laggard and short the leader, betting the spread converges. Market-neutral: you profit from the *relationship*, not market direction.

## Requirements
- Historical correlation + cointegration testing (correlation alone is not enough — cointegration is the statistically valid basis)
- Rolling spread calculation and z-score
- Ability to short (or use inverse instruments)

## Rules
1. Screen for cointegrated pairs (e.g., Engle-Granger or Johansen test on 1–2 years of data)
2. Compute the spread and its rolling z-score
3. **Entry:** z-score beyond ±2 → short the rich asset, long the cheap one
4. **Exit:** z-score returns to ~0
5. **Hard stop:** z-score beyond ±3.5–4, or cointegration test fails on re-check → the relationship may be broken; get out

## Best Markets
- Stocks in the same sector, ETFs, correlated futures

## Avoid
- Around company-specific news on either leg (divergence may be *justified* and permanent)
- Pairs whose relationship has structurally changed (merger, business pivot)

## Stats (rough)
- Win rate: 55–70%
- R:R: 1:1.5 to 1:3
- Lower volatility than directional strategies, but tail risk when relationships break

## Notes for Automation
The hardest strategy in this library, and the most genuinely "quant." Python stack: `statsmodels` for cointegration, rolling z-scores with pandas. Biggest failure mode is regime change — the pair that was cointegrated for 5 years stops being cointegrated the month you go live. Re-test relationships continuously and size small.
