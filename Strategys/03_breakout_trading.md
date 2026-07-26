# 03 — Breakout Trading

## Core Idea
Price consolidates, pressure builds, then price escapes the range with force. Trade the escape, not the range. Volatility contraction often precedes volatility expansion.

## Rules (Long — mirror for short)
1. Identify a clear consolidation (tight range, declining ATR/Bollinger squeeze)
2. Price closes above resistance
3. Volume on the breakout bar is well above average (e.g., > 1.5× 20-bar average)
4. Preferred: wait for a retest of the broken level that holds
5. Enter

**Stop loss:** just below the broken level (now support), or below the retest low.
**Exit:** measured move (height of the range projected from the breakout), or trailing stop.

## Best Conditions
- Earnings releases, economic news, market opens
- High-volatility sessions; crypto around session overlaps

## Avoid
- Low-volume breakouts (most fail)
- Midday/lunch chop
- Breakouts against the higher-timeframe trend

## Stats (rough)
- Win rate: 45–55%
- R:R: 1:2 to 1:4
- Failure mode: false breakouts. The volume filter and retest requirement exist purely to fight this.

## Notes for Automation
Medium difficulty — "clear consolidation" needs an objective definition. Good options: N-bar high/low (see `10_donchian_breakout.md` for the fully mechanical version), Bollinger Band width percentile, or ATR percentile. The retest entry lowers trade frequency but meaningfully improves quality in backtests.
