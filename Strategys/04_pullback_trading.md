# 04 — Pullback Trading

## Core Idea
Don't chase extended moves — wait for the trend to breathe. Trend → pullback → continuation. You get a better price, a tighter stop, and a higher-probability entry than buying the high.

## Indicators
- 20 EMA / 50 EMA (dynamic pullback zones)
- Fibonacci retracement (38.2%–50% is the sweet spot)
- Volume (should shrink on the pullback, return on continuation)

## Rules (Long — mirror for short)
1. Strong established uptrend (higher highs/lows, price above 50 EMA)
2. Price retraces 38–50% of the last impulse leg (or tags 20/50 EMA)
3. Volume dries up during the retrace (healthy pullback, not distribution)
4. Bullish reversal candle with volume returning
5. Enter

**Stop loss:** below the pullback swing low.
**Exit:** prior high (conservative), or trail for the continuation leg.

## Best Conditions
- Clean trending markets, any asset class
- Works on all timeframes; higher timeframes = more reliable

## Avoid
- Sideways markets (every "pullback" is just range chop)
- Retracements deeper than 61.8% — the trend may be over, that's reversal territory

## Stats (rough)
- Win rate: 55–65%
- R:R: 1:2 to 1:4

## Notes for Automation
Define "strong trend" objectively (e.g., ADX > 25 plus EMA alignment) and "impulse leg" via swing detection (ZigZag or fractal logic). This pairs naturally with `01_trend_following.md` — same regime, better entry timing.
