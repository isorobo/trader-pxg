# 02 — Mean Reversion

## Core Idea
Prices oscillate around an average. When they stretch too far, they tend to snap back — like a rubber band. You're selling panic and buying fear, in markets that aren't trending hard.

## Indicators
- RSI (14) — oversold/overbought
- Bollinger Bands (20, 2σ)
- VWAP
- Standard deviation from a moving average

## Rules (Long — mirror for short)
1. RSI(14) below 25–30
2. Price at/below the lower Bollinger Band
3. Price at a known support level (optional filter, improves quality)
4. Bullish reversal candle closes
5. Enter

**Stop loss:** below the reversal candle's low, or 1.5× ATR.
**Exit:** middle Bollinger Band (20 SMA) or VWAP. Don't get greedy — mean reversion targets the mean, not the moon.

## Best Conditions
- Low volatility, sideways/range-bound markets
- Indexes, blue-chip stocks, major FX pairs

## Avoid
- Strong trends (an "oversold" trending market gets more oversold)
- News events
- Crypto bull runs — RSI can pin above 80 for weeks

## Stats (rough)
- Win rate: 60–80%
- R:R: 1:1.2 to 1:2
- Failure mode: high win rate, but the rare loss is large if you don't respect the stop

## Notes for Automation
Easy to code. The critical component is a **regime filter**: only enable this strategy when ADX < 20–25 or when price is inside a defined range. Mean reversion without a trend filter is how bots blow up in trending markets. See also `11_rsi2_mean_reversion.md` for a stricter, well-studied variant.
