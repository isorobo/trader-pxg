# 19 — Options Strategies (Category Library)

> ⚠ **Scope note:** these are a different sport. They need an options-approved broker account, an options-chain data feed, and Greeks math (Delta/Theta/Vega) — none of which a spot/candle trading bot has. Kept in the library for completeness and future phases, but AI TRADRR v1 should treat this file as read-only reference. Also: NZ retail access to US options is possible but adds tax/broker friction worth researching first.

## Income (selling premium)

**1. Covered Call** — Own 100 shares, sell 1 OTM call (~0.30 delta, 30–45 DTE) against them. Neutral-to-mildly-bullish yield on stock you'd hold anyway; caps your upside, so don't run it on names you expect to rip. Target 80–100% premium decay.

**2. Cash-Secured Put** — Sell an OTM put (~0.20–0.30 delta) with cash reserved to buy 100 shares if assigned. Either keep the premium or buy a stock you wanted at a discount. Bad in crashes — you'll be assigned far above market.

**3. Poor Man's Covered Call (Diagonal)** — Replace the 100 shares with a deep-ITM long-dated call (80+ delta, 60–90+ DTE) and sell short-dated OTM calls against it. Covered-call economics at a fraction of the capital; avoid names prone to sudden collapse since your "stock" is leveraged.

**4. Calendar Spread** — Sell a ~20 DTE option, buy a ~50 DTE option at the same strike. Harvests faster short-term theta decay in quiet markets; a big fast move wrecks it. Target ~25–30% on debit.

## Defined-Risk Directional

**5. Bull Put Spread** — Sell ~0.30 delta put, buy ~0.15 delta put, same expiry, net credit. Moderately bullish with capped risk. Manage at 50% max profit; stop at ~2× credit.

**6. Bear Call Spread** — Mirror image for moderately bearish. Same management rules.

## Volatility Plays

**7. Long Straddle** — Buy ATM call + ATM put, same expiry (30–60 DTE), before a big catalyst. Profits on a large move EITHER way + IV expansion. The killer: **IV crush** — if the event is already priced in, both legs deflate even when price moves. Stop at 25–30% of debit.

**8. Long Strangle** — Same idea with OTM call + OTM put (~0.30 delta each); cheaper entry, needs an even bigger move. Dead money in quiet ranges.

**9. Iron Condor** — Sell an OTM call spread AND an OTM put spread (sell ~0.20 delta, buy ~0.10 delta wings), 30–45 DTE, on index options with IV Rank > 50%. Profits if price stays inside the range. Manage at 50% max profit; stop at 2× credit. Avoid ahead of obvious breakout setups.

**10. Iron Butterfly** — Sell ATM call + ATM put with OTM protective wings. Tighter, higher-premium condor for price pinning near spot in high IV. Manage at 25–50%.

**11. Delta-Neutral Hedging** — Hold offsetting stock/futures + options so net portfolio delta ≈ 0, isolating Vega/Theta P&L from direction. This is how vol traders and market makers operate; requires continuous rebalancing. Reference-level for now.

## Automation Notes
If AI TRADRR ever gets here, the mechanical premium-selling systems (condors and credit spreads with fixed delta/DTE/profit-taking rules) are the most bot-friendly — they're rule-based portfolio management, not chart reading. Skip long straddles as a bot strategy: modeling IV crush correctly is genuinely hard.
