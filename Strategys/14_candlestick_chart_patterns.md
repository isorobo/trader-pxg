# 14 — Candlestick & Chart Patterns (Category Library)

> Pattern reference for entries/confirmations. These are mostly **triggers**, not standalone systems — combine with a regime filter and the risk overlay (13). Duplicates removed: "Horizontal Range Rotation" → see `05_key_levels.md`.

## Single/Multi-Candle Reversal Signals

**1. Bullish/Bearish Engulfing** — Second candle's body fully covers the prior body. Use at key support/resistance after a mature trend or pullback; skip in low-vol chop where small candles constantly overlap. Enter at engulfing close, stop past pattern high/low, target next pivot or 1:2.

**2. Pinbar / Hammer** — Wick ≥ 2/3 of candle, small body at opposite end. Use at established levels or dynamic MAs showing rejection; useless mid-range with no level behind it. Enter on close or 50% wick retrace, stop beyond wick tip, target next swing.

**3. Inside Bar Breakout** — Candle fully contained within prior "mother bar." Use in strong momentum trends for continuation; fails often in low-volume ranges. Bracket orders above/below mother bar, stop at opposite side, target 1.5–2× mother bar size.

**4. Morning Star / Evening Star** — Big candle → small indecision candle → deep reversal candle back into candle 1's range. Use at macro trend extremes on 4H/Daily; skip flat intraday sessions. Enter on candle 3 close, stop beyond the star's shadow.

**5. Three White Soldiers / Black Crows** — Three consecutive full-bodied candles closing near their extremes. Use for high-volume structural reversals; if parabolic/overstretched, expect an immediate snapback instead. Enter on third close or 1-candle pullback, stop past candle 1's open.

## Classic Reversal Structures

**6. Head & Shoulders / Inverse H&S** — Three peaks (middle highest) over a neckline, or the mirror at bottoms. Use at the end of prolonged trends showing exhaustion; avoid fighting strong fundamental/news-driven trends. Enter on neckline break-and-close, stop beyond the right shoulder, target = head-to-neckline distance projected.

**7. Double / Triple Top & Bottom** — Two or three tests of the same level with rejection each time (M/W shapes). Use at major historic levels; in strong trends price slices straight through. Warning: rising volume on each successive test often signals breakout, not reversal. Enter on neckline break, stop beyond the extreme, target = range height.

**8. Rising / Falling Wedge** — Converging trendlines both sloping the same direction with fading momentum. Falling wedge → bullish reversal at bottoms; rising wedge → bearish at tops. Avoid in early-stage strong trends. Enter on break against the slope, stop at wedge extreme, target the wedge origin.

**9. Quasimodo (Over-Under)** — High, Low, Higher High, then Lower Low; entry on retest of the original left-shoulder level. Liquidity-sweep reversal for FX majors/indices, 15m–4H. Needs a clear structure break by the lower low. Limit at left shoulder, stop past the extreme, target the far swing.

## Continuation Structures

**10. Ascending / Descending Triangle** — Flat line on one side, sloping higher lows (or lower highs) pressing into it. Trade the break through the flat side in the pressure direction; avoid breaking into a bigger HTF level. Stop below last higher low (or above last lower high), target = triangle's widest height.

**11. Symmetrical Triangle** — Converging lower highs + higher lows into an apex; direction-agnostic volatility play. Bracket OCO orders both sides, stop inside the pattern, target = base width. Skip dead holiday sessions.

**12. Bull/Bear Flag & Pennant** — Sharp pole, then a tight counter-slope channel (flag) or tiny triangle (pennant). The go-to momentum continuation. Invalid if the flag drags past ~20–25 bars or retraces >61.8% of the pole. Enter on channel break, stop past flag extreme, target = pole length projected.

**13. Cup and Handle** — Rounded U-base plus a small downward-drifting handle at the rim. Daily/Weekly growth stocks building institutional bases; avoid V-recoveries with no handle. Enter on handle-rim break, stop below the handle, target = cup depth projected.

## SMC-Flavored Setups (⚠ read caveat)

> Caveat from the README still applies: these describe real price behaviors (stop clusters getting run, gaps filling) but the "institutional intent" framing is unfalsifiable and the setups are hard to define objectively in code. If AI TRADRR trades these, force strict mechanical definitions and backtest them like anything else.

**14. Order Block Re-entry** — Last opposing candle before an impulsive structure-breaking move; limit order at the block's open/50%, stop past the block, target the next liquidity pool. Only "valid" after a sweep + market structure shift — which is exactly the subjective part.

**15. Fair Value Gap Fill** — 3-candle sequence where candle 1's high and candle 3's low don't overlap, leaving a gap. Mid-trend continuation entry as price rebalances; needs HTF bias alignment. Enter in the gap, stop beyond the origin candle. (This one IS codeable — the gap is objectively defined.)

**16. Liquidity Sweep + Structure Shift** — Price runs a key swing high/low, rejects hard, then breaks the nearest structure the other way. Session opens (London/NY) on 1–15m. Enter on the structure shift, stop past the sweep wick, target the opposite pool. Essentially a formalized false-breakout trade — compare #79 in `18_volatility_event_breakout.md`.

## Automation Notes
Candle patterns are easy to code (engulfing, inside bar, pinbar are a few comparisons each); chart structures (H&S, cup-handle, wedges) need swing detection and are far harder to define without lookahead bias. Backtest patterns *with their context filter* (trend + level), never in isolation — raw pattern win rates hover near coin-flip.
