# 16 — Oscillator & Momentum Signals (Category Library)

> ⚠ **Editor's note:** the original list had ~15 oscillators, and most are mathematical cousins measuring the same thing (price velocity). Redundant near-clones are compressed below — pick ONE per job, don't stack five correlated oscillators and call it "confluence." Extends `07_momentum_trading.md`.

## Divergence (the highest-value oscillator concept)

**1. RSI Divergence (Regular & Hidden)** — Regular: price higher high, RSI lower high → reversal warning. Hidden: price higher low, RSI lower low → continuation. Enter only after price confirmation (trendline/structure break), never on divergence alone; stop beyond the price extreme. Useless against vertical news-driven rallies.

**2. MACD Histogram Divergence** — Shrinking histogram peaks against new price highs = fading thrust. Early-warning tool on 1H/4H; too noisy below 5m. Enter on signal-line cross after the divergence.

**3. MFI Divergence (volume-weighted)** — Same logic but volume-weighted, so it can reveal accumulation/distribution ordinary RSI misses. Needs reliable volume data — fine for equities/futures, unreliable for spot FX.

**4. Awesome Oscillator Twin Peaks** — Two same-side AO peaks, second one weaker → exhaustion. Enter on histogram color confirmation, target the zero cross. Don't fight strong HTF trends with it.

## Centerline / Threshold Momentum

**5. RSI 50-Cross** — RSI crossing 50 marks a directional shift out of quiet accumulation. Clean and simple on 15m/1H; worthless when RSI just hovers around 50 in flat markets.

**6. MACD Zero-Line Cross** — Both MACD lines crossing zero = systemic momentum shift on 1H–Daily. Enter on breach, exit on signal-line back-cross.

**7. CCI ±100 Surge** — CCI punching through +100/−100 for cyclical momentum bursts (commodities/FX). Exit when it falls back inside the bounds.

**8. ROC Spike** — Rate-of-change past historical extremes for aggressive impulse trades on high-beta names, 5–15m. Fast in, fast out (~1:1.5–1:2).

**9. TRIX Zero-Cross** — Triple-smoothed; nearly all noise removed and heavily lagged. Position trading on Daily/Weekly only.

*(Cut as redundant: RVI breakout and Ultimate Oscillator — both duplicate jobs already covered by #5–6 with no distinct edge.)*

## Overbought/Oversold Reversion (range markets ONLY)

**10. Stochastic Cross in Extremes** — %K/%D cross below 20 or above 80, enter as it exits the zone, target the opposite band. The classic range tool. In trends, stochastics pin at extremes for weeks — the #1 way beginners get destroyed.

**11. Williams %R Snapback** — Functionally a faster stochastic (−80/−20 zones) for 5–15m scalps back to the −50 midline. Same trend warning applies.

**12. StochRSI 0/1 Extreme** — Hypersensitive; fires constantly. Only meaningful at a key price level — never as a standalone signal.

**13. CMO ±50 Reversion** — Unsmoothed momentum extreme snapbacks. Same family; same rules.

> These four are ~interchangeable. Implement ONE (stochastic is the standard), gate it behind a range-regime filter (ADX < 20), and see `02_mean_reversion.md` / `11_rsi2_mean_reversion.md` for the researched versions of this idea.

## Automation Notes
Oscillators are one-liners with any TA library (`ta`, `pandas-ta`, TA-Lib). Divergence detection is the exception — it needs swing-point logic and is easy to code with hindsight bias, so validate it bar-by-bar. Rule of thumb for AI TRADRR: oscillators are *filters and timers*, not systems; every entry still needs structure (level/trend) behind it.
