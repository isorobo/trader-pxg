# 10 — Donchian Channel Breakout (Turtle-Style) ⭐ Added

## Core Idea
The purest mechanical trend-following system, made famous by the 1980s Turtle Traders experiment. No discretion at all: buy when price makes a new N-day high, sell/short when it makes a new N-day low. If a big trend happens, you are mathematically guaranteed to be in it.

## Rules (classic Turtle-style parameters)
**System 1 (faster):**
- **Entry long:** price breaks the 20-day high
- **Exit long:** price breaks the 10-day low
**System 2 (slower):**
- **Entry long:** price breaks the 55-day high
- **Exit long:** price breaks the 20-day low
(Shorts are the mirror image.)

**Stop loss:** 2× ATR(20) from entry.
**Position sizing:** volatility-based — risk a fixed % of equity per 1 ATR of movement, so every market gets equal risk weight.

## Best Markets
- Futures, crypto, FX — anything that trends and is liquid
- Designed to run across a *portfolio* of uncorrelated markets simultaneously; that diversification is half the edge

## Avoid
- Running it on a single choppy instrument (you'll get whipsawed to death)
- Overriding signals manually — the system only works if taken 100% mechanically

## Stats (rough)
- Win rate: 30–45% (yes, that low — and it's historically been profitable anyway)
- R:R: 1:3 to 1:15 on the big winners
- Expect deep drawdowns (20–30%+) and long flat periods

## Notes for Automation
The single easiest genuinely-credible strategy to code: `if close > max(high[-20:]): buy`. Perfect first strategy for AI TRADRR's backtesting engine because there's decades of published performance to sanity-check your implementation against. The lesson it teaches is the important part: entries are trivial, and all the money is in exits, sizing, and diversification.
