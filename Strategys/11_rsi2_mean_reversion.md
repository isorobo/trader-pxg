# 11 — RSI(2) Mean Reversion (Connors-Style) ⭐ Added

## Core Idea
A stricter, well-studied cousin of standard mean reversion, popularized by Larry Connors. Use an ultra-short RSI (2-period instead of 14) to buy brief panics *within a long-term uptrend*. The long-term filter is the whole trick: you only buy dips in things that are structurally going up.

## Rules (Long only — this strategy is famously weak on the short side)
1. Price above the 200-day SMA (long-term uptrend filter — non-negotiable)
2. RSI(2) closes below 10 (stricter variant: below 5)
3. Buy at the close (or next open)
4. **Exit:** price closes above the 5-day SMA, or RSI(2) closes above 65
5. Optional scaling: add a second unit if RSI(2) drops below 5 after entry

**Stop loss:** this is the controversial part — the original research uses a time stop (exit after N days) rather than a price stop, because tight stops destroy the edge. For a bot, use a wide disaster stop (e.g., 3–4× ATR) plus a 5–10 day time stop.

## Best Markets
- Stock index ETFs (where it was researched: S&P 500 and constituents)
- Liquid large-cap stocks

## Avoid
- Anything below its 200-day SMA (buying dips in downtrends is how accounts die)
- Crypto and commodities — the research doesn't transfer cleanly
- Bear markets: the 200 SMA filter will correctly keep you flat; let it

## Stats (rough)
- Win rate: 65–80%
- R:R: 1:0.8 to 1:1.5 (small average wins, high frequency — the opposite profile to trend following)

## Notes for Automation
Trivial to code and heavily documented, so it's ideal for validating your backtester (your numbers should roughly match published results). Pairs beautifully with `10_donchian_breakout.md` as a portfolio: one thrives in chop, the other in trends, and their equity curves offset.
