# 20 — Quant, Arbitrage & Market-Structure Systems (Category Library)

> Duplicate removed: statistical pairs/cointegration → `09_statistical_pairs_trading.md` (already has the full spec). Honest difficulty labels added — several of these are listed everywhere online but are effectively closed to retail bots. Better to know that now than after building one.

## Realistic for a Retail Bot ✅

**1. Grid Trading** — A lattice of buy/sell limit orders at fixed intervals inside a defined range, harvesting oscillation. Works in sideways chop; **catastrophic in a runaway trend** (you accumulate a huge losing position one grid level at a time). Non-negotiable additions: hard range boundaries where the grid shuts off, and a max-inventory cap. Crypto/FX friendly, easy to code, popular for good reason — and blown up by trends for the same reason.

**2. Seasonality / Calendar Anomalies** — Turn-of-the-month effect, Santa rally, agricultural/energy seasonal cycles. Enter on fixed dates, hold for the historical window, fixed % stop. Real but small statistical edges; never trade them against an active macro regime (e.g., a hiking cycle). Trivial to code and backtest — a fine minor overlay for AI TRADRR.

**3. FX Carry Trade** — Long high-yield currency vs short low-yield (AUD/JPY, MXN/JPY), collecting the daily swap differential. A slow position strategy, not a signal system. Earns steadily in risk-on calm, then gives back years of carry in one risk-off liquidation cascade — size small and use a hard trailing risk limit.

**4. Funding-Rate Arbitrage (crypto)** — Long spot + short an equal perpetual position when annualized funding > ~15–20%; collect the funding payments, unwind when it normalizes. Genuinely market-neutral-ish and codeable. Real risks: exchange/counterparty failure and liquidation of the short leg during violent squeezes — keep the perp leg well-collateralized.

## Borderline — possible but the edge is thin ⚠

**5. Order-Book Imbalance Scalping** — Reading DOM/Level-2 for lopsided bid/ask stacks and scalping 2–4 ticks with the heavy side. Needs futures-grade data and fast execution; spoofed orders poison the signal. Manual-hybrid at best for retail; a naive bot version gets adversely selected.

**6. Value-Area / Volume-Profile plays** — Covered in `17_mean_reversion_range.md` #11; needs volume-at-price data but is retail-feasible.

## Effectively Closed to Retail ❌ (reference only)

**7. Triangular Arbitrage** — Exploiting mispricing across three currency pairs (EUR/USD × USD/GBP vs EUR/GBP). Pure HFT territory: opportunities last milliseconds and are gone before a retail API round-trip completes. Great programming exercise, not a live strategy.

**8. Cross-Exchange Arbitrage** — Buy on exchange A, sell on B when spreads exceed fees. In liquid crypto pairs, professional firms with colocated infrastructure compress these spreads instantly; transfer times and withdrawal fees eat what's left. Only quasi-viable in obscure illiquid pairs — where the liquidity risk replaces the price risk.

**9. Delta-Neutral Vol Trading / Market Making** — See `19_options_strategies.md` #11 and the advanced doc. Infrastructure businesses, not strategies.

## Automation Notes
Priority order if you build from this file: **grid (with kill-switches) → seasonality overlay → funding-rate arb** (if crypto is in scope). All three are honest, codeable, and testable with free data. The arbitrage strategies are worth *implementing in a paper simulator* purely for the education — watching your simulated triangular arb "profits" evaporate against realistic latency assumptions teaches more about market microstructure than any article.
