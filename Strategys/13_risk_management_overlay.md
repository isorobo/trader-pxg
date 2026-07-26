# 13 — Risk Management Overlay ⭐ Added (read this first)

> Not a strategy — the layer that sits on top of every strategy in this folder. Strategy choice determines *whether* you have an edge; risk management determines *whether you survive long enough to collect it*. Most bots don't die from bad entries. They die from position sizing.

## Position Sizing
- **Fixed fractional:** risk 0.5–1% of equity per trade. Position size = (equity × risk%) ÷ (entry − stop distance).
- **Volatility-adjusted:** size inversely to ATR so volatile assets get smaller positions. This is what the Turtles did and what CTAs still do.
- Never size up because you "feel confident." The bot doesn't feel things — keep it that way.

## Portfolio Rules
- Max total open risk: 3–5% of equity across all positions
- Max correlated exposure: treat 3 longs in the same sector as ~1 big position
- Daily loss limit: bot stops trading for the day after −2 to −3%
- Max drawdown circuit breaker: bot halts entirely and alerts you at −10 to −15%

## Per-Trade Rules
- Stop loss defined *before* entry, always, no exceptions in code
- Never average down on losers
- Never move a stop further away
- If the entry thesis dies (e.g., price re-enters the range on a breakout trade), exit — don't wait for the stop

## Regime Switching (ties the library together)
Route strategies by market condition instead of running everything always:
- ADX > 25 & trending → enable 01, 04, 10
- ADX < 20 & range-bound → enable 02, 05, 11
- High RVOL / catalyst days → enable 03, 07, 08
- Always-on backbone → 12
This is a simplified version of the "Regime-Based Adaptive Trading" concept from the advanced doc, and it's very buildable.

## Backtesting Honesty Checklist
- [ ] Include commissions AND slippage (pessimistically)
- [ ] No lookahead bias (signals use only data available at decision time)
- [ ] No survivorship bias in the asset universe
- [ ] Out-of-sample test: tune on one period, validate on an untouched one
- [ ] Walk-forward if possible
- [ ] Assume real results will be ~half as good as the backtest

## Reality Check
The published win rates in these files are optimistic priors, not guarantees. Most retail algo traders lose money; the ones who don't are the ones who size small, test honestly, and survive their own learning curve. Paper trade AI TRADRR for months before any real money is involved — and this whole library is educational material for a coding project, not financial advice.
