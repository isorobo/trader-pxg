# 18 — Volatility, Event & Breakout Systems (Category Library)

> Extends `03_breakout_trading.md`. These trade the transition from quiet to loud — compression → expansion, or scheduled catalysts. Slippage and spread widening are the hidden tax on everything in this file; model them brutally in backtests.

## Compression → Expansion

**1. ATR Expansion** — ATR grinds to multi-week lows, then a sharp move spikes it. Enter on the expansion candle close, stop 1.5× ATR, trail with ATR. Skip late-stage trends where volatility is already spent.

**2. Bollinger Squeeze** — Bands compress to their narrowest in N periods, then a candle closes outside on volume. Enter with the break, stop at the 20 SMA midline, target ~2× the bandwidth. Low-volume sessions produce head-fakes.

**3. TTM Squeeze (Bollinger-inside-Keltner)** — The quantified squeeze: BB inside KC = energy loading; dots flip = release. Enter on release with momentum-histogram alignment, stop at local pivot, exit on histogram peak. The most objective squeeze variant — good bot candidate.

**4. Consolidation Channel Break** — 10+ candles trapped in a tight box, then a full-bodied escape candle. Enter on the close outside, stop at range midpoint, target 1:2. Reject low-volume or long-wick "breakouts."

**5. Volume-Confirmed Breakout** — Any level break is only valid with volume 2–3× the 20-bar average. Not a standalone system — a mandatory filter for every other breakout here. One warning: a huge spike on a massive exhaustion wick is climax volume (a top), not confirmation.

**6. False-Breakout Trap (Bull/Bear Trap)** — The mirror trade: price breaks a key level, sucks in breakout traders, then closes back inside → fade it hard toward the far side of the range. Stop past the trap wick. This is the same behavior SMC calls a "liquidity sweep" (see file 14, #16) — one phenomenon, two vocabularies. Fading works in ranges; in genuine trend regimes the first breakout is usually real.

## Session & Gap Plays (equities-centric)

**7. Gap and Go** — Stock gaps 3%+ overnight on volume, holds the open, breaks pre-market high → momentum long. Stop below low-of-day, target 1:2 or trail VWAP. Avoid gapping straight into major HTF resistance.

**8. Gap Fill Fade** — Weak, catalyst-free gaps that stall at the open tend to retrace to yesterday's close. Enter against the gap on failure, stop beyond the gap extreme, target prior close. Never fade real-catalyst gaps (earnings beats, buyouts).

**9. Pre-Market High/Low Break** — The 04:00–09:30 EST range as the day's first structure. Enter on a close past it, stop inside the range, target 1.5× range width. Needs elevated relative volume to matter.

## Scheduled Events

**10. Earnings Breakout** — Trade the post-gap momentum ~5 minutes after the open in the gap's direction if the opening range holds. **Never hold through the actual release** — that's a coin flip with gap risk, not a strategy.

**11. News Straddle (CPI/NFP/rate decisions)** — Bracket stop orders ±10 pips around the pre-news coil, 2 minutes before release; one side fills, opposite order is the stop. ⚠ **Honest warning for a bot:** retail execution during news means spread blowouts, slippage, and requotes — many brokers effectively make this untradeable. Backtests will lie to you here because they can't model the fill quality. Treat as educational unless you have futures-grade execution.

## Automation Notes
Compression detectors (ATR percentile, BB-width percentile, TTM squeeze) are easy and genuinely useful — they tell the bot *when* to expect action, which also tells it when to disable mean-reversion strategies (file 17). Event strategies need a calendar feed (earnings dates, economic releases) wired into the bot so it can stand down or switch modes around them; an AI trader that doesn't know NFP exists will donate money every first Friday of the month.
