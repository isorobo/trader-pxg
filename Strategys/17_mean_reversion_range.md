# 17 — Mean Reversion & Range Systems (Category Library)

> Extends `02_mean_reversion.md` and `11_rsi2_mean_reversion.md`. Duplicates removed: ORB → `08_opening_range_breakout.md` (it was miscategorized here anyway — it's a breakout strategy); plain horizontal-range rotation → `05_key_levels.md`. Everything below assumes a RANGE regime — run these in trends and they will bleed.

## Band Reversion

**1. Bollinger Fade** — Price stretches outside a band in a sideways market, prints a rejection candle, snaps back. Enter on the close back inside the band, stop past the extreme, target the 20 SMA midline. **Never fade when bands are expanding** ("band walking" = trend, not stretch).

**2. Double Bollinger Filter (1SD + 2SD)** — Two band sets; the 1SD–2SD gap acts as the trend zone. Price living in the upper zone = trend (don't fade); price oscillating across the midline = range (fade away). A neat objective trend/range classifier.

**3. Keltner Reversion** — Same fade logic but ATR-based outer bands, popular on indices/commodities. Stop 0.5 ATR beyond the band, target the center EMA.

**4. RSI + Bollinger Confluence** — Band touch AND RSI < 30 (or > 70) simultaneously. Higher quality, fewer signals. Skip during genuine panics — "oversold" is not a floor in a crash.

## Statistical Reversion

**5. Z-Score Reversion** — Short at Z > +2, long at Z < −2 versus a rolling mean; exit at Z ≈ 0, hard stop at |Z| = 3. The quant formalization of everything above. Breaks when the asset undergoes real structural change — the mean itself moves.

**6. Standard Deviation Channel** — Linear regression line ± 2SD; fade the boundaries back to the regression line inside a steady channel. Stop at 2.5SD.

**7. VWAP Band Reversion** — Fade ±2.5SD deviations from session VWAP back to the VWAP line, 1–5m equities/futures. Stop past 3SD. Do NOT run on trend days — add a trend-day detector (e.g., skip if price hasn't crossed VWAP by mid-morning). Complements `06_vwap_trading.md` (which trades WITH VWAP; this fades stretches FROM it).

## Level-Based Intraday Rotation

**8. Floor Pivot Bounce** — Daily pivots (PP, S1–S3, R1–R3) as intraday magnets; fade rejections at a pivot toward the next one. Dies on trend days that slice every level.

**9. Camarilla Pivots** — Fade the H3/L3 levels in-range; H4/L4 breaks flip you to breakout mode. Needs a clear open — skip choppy no-range mornings.

**10. Initial Balance Fade** — First-hour high/low fails to break and sweeps back inside → fade toward the opposite IB boundary. Index futures (ES/NQ) specialty. Avoid conviction news days.

**11. Value Area Reversion (Volume Profile)** — Price pokes outside yesterday's Value Area, fails, re-enters → target the POC or the far VA boundary. Auction-theory logic: rejection of new value. Trend days that ACCEPT value outside the range invalidate it.

## Fibonacci

**12. Fib Retracement Bounce (38.2/50/61.8)** — Reversal candle at a golden-ratio pullback within a trend. Technically a *trend* entry (see `04_pullback_trading.md`) but listed here as levels-reversion. Past 78.6% = structure failed, stand down.

**13. Fib Extension Targets (127.2/161.8/261.8)** — Not an entry system — an exit framework. Park take-profits at extensions during price discovery; move stop to breakeven once the prior high breaks.

## Automation Notes
Everything here is objectively codeable (pivots and fibs are pure arithmetic; volume profile needs tick/volume-at-price data). The make-or-break component is the **regime gate**: build one range-detector (ADX < 20, Double-Bollinger zone test, or IB-width percentile) and require it to be green before ANY strategy in this file may fire. That single gate matters more than which reversion flavor you pick.
