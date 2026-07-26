# AI TRADRR — Strategy Library

Curated strategy reference for the AI TRADRR project. Each file uses the same structure so strategies can be parsed/implemented consistently: **Core Idea → Rules (Entry/Exit/Stop) → Best Conditions → Avoid → Stats → Notes for Automation**.

## What was edited from the original list

**Cut / merged:**
- **Support & Resistance** and **Supply & Demand** were ~80% the same concept with different branding. Merged into one file: `05_key_levels.md`.
- Removed the vague filler and fixed the broken formatting in Mean Reversion and Breakout.
- Win rates and R:R kept, but treat them as *rough priors*, not promises — real numbers come from your own backtests.

**Kept (cleaned up):** Trend Following, Mean Reversion, Breakout, Pullback, Key Levels, VWAP, Momentum, Opening Range Breakout, Statistical Pairs.

**Added (good fits for an automated system):**
- `10_donchian_breakout.md` — Turtle-style channel breakout. Fully mechanical, famously backtestable.
- `11_rsi2_mean_reversion.md` — Connors-style short-term mean reversion. Simple, well-studied.
- `12_time_series_momentum.md` — 12-month momentum. Strong academic evidence, low maintenance.
- `13_risk_management_overlay.md` — Not a strategy, but the thing that decides whether any strategy survives. Read first.

**A note on the SMC / advanced doc:** Smart Money Concepts is popular on YouTube but is largely a rebranding of classic concepts (S/R zones, breakouts) with unfalsifiable storytelling about "institutions." Hard to code objectively, so it's not in this library. Market Profile, order flow, market making, and vol arb need data/infrastructure a retail AI bot won't have — skipped for now. Statistical arbitrage lives on in simplified form as Pairs Trading (`09`).

## Comparison Table

| # | Strategy | Best Market | Best Condition | Win Rate* | R:R* | Automation Difficulty |
|---|----------|-------------|----------------|-----------|------|----------------------|
| 01 | Trend Following | All | Strong trends | 35–50% | 1:3–1:10+ | Easy |
| 02 | Mean Reversion | Stocks, FX | Sideways/low vol | 60–80% | 1:1.2–1:2 | Easy |
| 03 | Breakout | All | High volatility | 45–55% | 1:2–1:4 | Medium |
| 04 | Pullback | All | Trending | 55–65% | 1:2–1:4 | Medium |
| 05 | Key Levels | All | Ranges | 50–65% | 1:1.5–1:3 | Hard (subjective) |
| 06 | VWAP | Stocks, Futures | Intraday | 50–65% | 1:2–1:3 | Easy |
| 07 | Momentum | Stocks, Crypto | High momentum | 40–60% | 1:2–1:5 | Medium |
| 08 | Opening Range Breakout | Stocks, Futures | Market open | 40–55% | 1:2–1:4 | Easy |
| 09 | Statistical Pairs | Stocks, ETFs | Stable correlation | 55–70% | 1:1.5–1:3 | Hard |
| 10 | Donchian Breakout | Futures, Crypto | Trends | 30–45% | 1:3–1:15 | Very Easy |
| 11 | RSI-2 Reversion | Stock indexes | Long-term uptrend | 65–80% | 1:0.8–1:1.5 | Very Easy |
| 12 | Time-Series Momentum | ETFs, Futures | Multi-month trends | 45–60% | varies | Very Easy |

\* Approximate historical tendencies. Verify with your own backtests — costs, slippage, and regime changes eat theoretical edges.

## Disclaimer
This is educational reference material for a software project, not financial advice. Backtest everything, paper trade before live, and assume published win rates are optimistic.
