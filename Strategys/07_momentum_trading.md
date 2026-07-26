# 07 — Momentum Trading

## Core Idea
Strength begets strength. Find assets already moving hard on unusual volume and capture the middle of the move. You're not first in and not last out — you're riding the crowd while it's stampeding.

## Indicators
- Relative Volume (RVOL) — the key filter; you want > 2× normal
- MACD (momentum confirmation)
- RSI (not for overbought fades — strong momentum lives above 70)
- Break of recent highs

## Rules (Long — mirror for short)
1. Catalyst present (earnings, news, sector theme) or unusual RVOL spike
2. Strong directional move already underway
3. Price breaks above a recent high with RVOL > 2
4. Enter

**Stop loss:** below the breakout bar low or 1.5–2× ATR.
**Exit:** momentum fades (MACD cross, RVOL collapsing) or trailing stop hit. Momentum dies fast — don't marry the position.

## Best Conditions
- Earnings season, strong market themes, high-volatility regimes
- Stocks and crypto especially

## Avoid
- Quiet, low-liquidity markets
- Chasing after the move is already extended (late entries have terrible R:R)
- Illiquid small caps where spread eats the edge

## Stats (rough)
- Win rate: 40–60%
- R:R: 1:2 to 1:5

## Notes for Automation
Medium difficulty. The scanner matters more than the entry logic: your bot needs to rank the whole universe by RVOL + % change and only trade the top names. Slippage is a real cost here — model it pessimistically in backtests.
