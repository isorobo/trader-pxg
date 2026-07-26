# 01 — Trend Following

## Core Idea
Don't predict reversals — ride established moves. Buy strength, sell weakness, and let winners run. Like surfing: you don't create the wave, you ride it. The edge comes from a small number of huge winners paying for many small losses.

## Indicators
- 200 EMA (long-term trend filter)
- 50 EMA (medium-term direction)
- 20 EMA (pullback zone)
- ADX (trend strength — only trade when > 25)
- ATR (stop distance / position sizing)
- Volume (confirmation)

## Rules (Long — mirror for short)
1. Price above 200 EMA
2. 50 EMA above 200 EMA
3. ADX > 25
4. Price pulls back to the 20 EMA
5. Bullish engulfing candle (or close back above 20 EMA)
6. Enter on next bar open

**Stop loss:** below previous swing low, or 2× ATR below entry.
**Exit:** trailing stop (e.g., 3× ATR chandelier, or close below 50 EMA). Trend followers rarely use fixed targets — capping winners kills the whole edge.

## Best Conditions
- Strong bull/bear markets, sustained news-driven trends
- Forex, stocks, crypto, commodities with momentum

## Avoid
- Sideways/choppy ranges (ADX < 20)
- Low volatility regimes

## Stats (rough)
- Win rate: 35–50%
- R:R: 1:3 to 1:10+
- Psychology: long losing streaks are normal — the math still works if you don't abandon it

## Notes for Automation
Very easy to code — all conditions are objective. The hard part is the exit: test several trailing methods (ATR chandelier, EMA close, swing-low trail) and expect the exit rule to matter more than the entry. Risk 0.5–1% per trade. Never average down.
