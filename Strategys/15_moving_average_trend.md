# 15 — Moving Average & Trend Systems (Category Library)

> Extends `01_trend_following.md`. Duplicates removed: Donchian/Turtle → `10_donchian_breakout.md`; intraday VWAP hold → `06_vwap_trading.md`. All of these die in ranges — gate them behind a trend filter (ADX > 25 or equivalent).

## Crossover Systems

**1. 20/50 EMA Cross (Golden/Death Cross, fast)** — 20 EMA crossing 50 EMA. Medium-term trend initiation on 1H–Daily. Enter on cross, stop at recent pivot, exit on cross-back or trail the 50. Whipsaw city in ranges.

**2. 50/200 SMA Institutional Alignment** — Price > 50 SMA > 200 SMA = macro bullish. Swing/position trading on Daily/Weekly, not intraday. Buy pullbacks while alignment holds, stop below 200 SMA, open-ended trail.

**3. Triple EMA (8/21/55)** — 8 crosses 21 while both sit the right side of 55. Earlier entries with an extra false-signal filter. 15m–1H futures/FX. Stop beyond the 55, trail the 21.

**4. GMMA Compression/Expansion** — Six short EMAs compress then expand through six long EMAs. Macro trend-shift detector for 4H/Daily. Enter on full expansion, stop across the long-term ribbon, exit when the short group contracts.

**5. Multi-Timeframe Alignment** — Daily 50 EMA bias → 1H 20 EMA direction → 5m entry trigger. The highest-win-rate way to run any MA system: only trade with the macro tailwind. Stand aside when timeframes conflict.

## Dynamic Support Systems

**6. MA Bounce** — Price pulls back to a respected average (20 EMA / 50 SMA) and prints a reversal candle. Clean rhythmic trends only; by the 3rd–4th retest the trend is usually dying. Stop 0.5 ATR beyond the MA, target 1:2. (Same family as `04_pullback_trading.md`.)

**7. Keltner Channel Pullback** — Trending price returns to the 20 EMA midline of an ATR-based channel. Enter on midline touch in trend direction, stop past the outer band, target the outer band.

**8. MA Envelope Bounce** — MA shifted ±fixed % (e.g., 2%). Long at lower band, short at upper in stable large-caps/FX; news breaks it instantly. Target the middle line.

## Adaptive / Smoothed Systems

**9. Supertrend Flip** — ATR-based line flips sides of price. Simple, popular, objective. Enter on flip close, stop at the line, hold until it flips back. Chop = repeated whipsaw losses.

**10. Parabolic SAR** — Accelerating trailing dots. Best used as a *trailing stop* in parabolic moves rather than an entry engine. Skip consolidations entirely.

**11. KAMA (Kaufman Adaptive MA)** — Flattens in noise, slopes in clean trends; a built-in regime filter. Enter when KAMA turns with price aligned, stop 1.5 ATR, trail along KAMA.

**12. Hull MA Inflection** — Ultra-low-lag MA slope changes for short-term scalping (3–15m). Prone to single-bar fakeouts in low volume. Stop past recent swing, target ~1:1.5.

**13. Heikin-Ashi Trend Rider** — Hold through consecutive shadowless HA candles; exit on first color change/doji. Great for *holding* winners, terrible for precise entries/exits (HA prices are synthetic — compute stops on real candles!).

**14. Trailing-MA Exit** — Not an entry: stay in any trend trade until price closes past a chosen MA (e.g., 10 EMA). Simple, effective exit engine for runaway trends — pairs with 01 and 10.

## Ichimoku

**15. Kumo Cloud Breakout** — Close outside the cloud with Tenkan > Kijun and Chikou clear. Full-system trend confirmation, classically on JPY pairs, 4H/Daily. Stop at cloud far side/Kijun, exit on Kijun cross. Dead inside a thick flat cloud.

**16. Tenkan/Kijun Cross** — Conversion/base line cross while outside the cloud, as a re-entry inside an established trend. Never trade it inside the cloud.

## Statistical Trend Tools

**17. Linear Regression Slope** — Only trade when the 100-period regression slope exceeds a threshold; enter pullbacks to the channel midline, target the outer boundary. Objectifies "is this trending?" — useful as a filter for everything above.

## Automation Notes
Every strategy here is trivially codeable — that's both the appeal and the problem (edges are thin and widely known). The value for AI TRADRR: use one as the *regime filter* (KAMA slope, regression slope, 50/200 alignment) and another as the *trigger*, rather than stacking five redundant MAs that all say the same thing.
