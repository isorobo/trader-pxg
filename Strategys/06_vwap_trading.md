# 06 — VWAP Trading

## Core Idea
VWAP (Volume Weighted Average Price) is the day's average price weighted by volume — the benchmark institutions measure their fills against. Intraday, price tends to respect it: above VWAP = buyers in control, below = sellers.

## Rules (Long — mirror for short)
1. Price opens/holds above VWAP (bullish intraday bias)
2. Price pulls back to VWAP
3. Buyers defend it — rejection wick or bullish candle at/near VWAP
4. Enter on confirmation

**Stop loss:** a small buffer below VWAP (e.g., 0.5× ATR) — if price accepts below, the thesis is dead.
**Exit:** prior high, fixed R multiple, or trail. Also valid: exit if price closes decisively below VWAP.

## Best Markets & Times
- Stocks, index futures, liquid ETFs
- First 2–3 hours after the open (VWAP is most meaningful early; it flattens late in the day)

## Avoid
- Overnight/24h charts without session resets (VWAP must anchor to session open)
- Low-volume assets
- Days that open with huge gaps and no follow-through

## Stats (rough)
- Win rate: 50–65%
- R:R: 1:2 to 1:3

## Notes for Automation
Very easy to code and fully objective — one of the best starter strategies for a bot. Make sure your VWAP resets at session open, and add a trend filter (e.g., only long when price is above opening range midpoint) to avoid fading strong trend days.
