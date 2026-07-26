# AI TRADRR — Strategy Library

Curated strategy reference for the AI TRADRR project. Files 01–13 are full single-strategy specs; files 14–20 are category libraries (condensed multi-strategy references) built from the 100-strategy guide, deduplicated and edited.

## Structure

**Core strategies (full specs):**
- `01_trend_following.md`
- `02_mean_reversion.md`
- `03_breakout_trading.md`
- `04_pullback_trading.md`
- `05_key_levels.md` (Support/Resistance + Supply/Demand, merged)
- `06_vwap_trading.md`
- `07_momentum_trading.md`
- `08_opening_range_breakout.md`
- `09_statistical_pairs_trading.md`
- `10_donchian_breakout.md` ⭐
- `11_rsi2_mean_reversion.md` ⭐
- `12_time_series_momentum.md` ⭐
- `13_risk_management_overlay.md` ⭐ **read first**

**Category libraries (from the 100-strategy guide):**
- `14_candlestick_chart_patterns.md` — engulfing, pinbar, H&S, triangles, flags, cup & handle, SMC setups (with caveats)
- `15_moving_average_trend.md` — crossovers, GMMA, Supertrend, Ichimoku, KAMA, multi-timeframe alignment
- `16_oscillator_momentum.md` — RSI/MACD divergence, stochastics, threshold systems (redundant clones compressed)
- `17_mean_reversion_range.md` — Bollinger/Keltner fades, Z-score, pivots, Camarilla, Initial Balance, Value Area, fibs
- `18_volatility_event_breakout.md` — squeezes, gaps, earnings, news straddles, false-breakout traps
- `19_options_strategies.md` — covered calls, spreads, condors, straddles (reference-only for v1)
- `20_quant_arbitrage_structure.md` — grid, seasonality, carry, funding arb; honest labels on what's closed to retail

## Deduplication log (100-strategy guide → this library)
- #27 Donchian/Turtle → already `10_donchian_breakout.md`
- #35 VWAP trend hold → already `06_vwap_trading.md`
- #61 Horizontal range rotation → already `05_key_levels.md`
- #68 Opening Range Breakout → already `08_opening_range_breakout.md`
- #91 Stat-arb pairs/cointegration → already `09_statistical_pairs_trading.md`
- RVI + Ultimate Oscillator → cut as redundant clones of other oscillator systems
- Williams %R / StochRSI / CMO → kept but flagged as interchangeable with Stochastic (implement one)
- False-breakout trap and SMC "liquidity sweep" → cross-referenced as the same phenomenon in two vocabularies

## Editorial stance
- SMC setups are included (file 14) but flagged: real behaviors, unfalsifiable narrative, mostly hard to code objectively. FVGs are the codeable exception.
- Options (file 19) and HFT arbitrage (file 20) are labeled reference-only — wrong infrastructure tier for a v1 retail bot.
- Every published win rate in this library is an optimistic prior. Your backtests are the only numbers that count.

## Comparison Table (core strategies)

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

\* Approximate historical tendencies — verify with your own backtests; costs, slippage, and regime changes eat theoretical edges.

## Regime routing map (ties everything together — full version in file 13)
- **Trending (ADX > 25):** 01, 04, 10, 12, file 15 systems
- **Ranging (ADX < 20):** 02, 05, 11, file 17 systems
- **Compression/catalyst days:** 03, 07, 08, file 18 systems
- **Always-on overlays:** 12, seasonality (file 20), risk rules (file 13)

## Disclaimer
Educational reference material for a software project — not financial advice. Backtest everything, paper trade before live money, and assume published stats are optimistic.
