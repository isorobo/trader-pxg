# 08 — Opening Range Breakout (ORB)

## Core Idea
The first minutes of the session set the battleground. Mark the high and low of the first 5–30 minutes (the "opening range"), then trade the break of it — the open concentrates volume and often sets the day's direction.

## Rules
1. Record the high and low of the first N minutes (test 5, 15, and 30 — 15 is the common default)
2. **Long:** price breaks above the range high with strong volume
3. **Short:** price breaks below the range low with strong volume
4. Optional filter: only trade in the direction of the overnight/pre-market trend or gap

**Stop loss:** opposite side of the opening range (or range midpoint for a tighter stop).
**Exit:** fixed R multiple (1:2+), measured move (range height projected), or trail into the close.

## Best Markets
- Stocks with a catalyst/gap
- Index futures (ES, NQ)

## Avoid
- Low-volume days (holidays, summer doldrums)
- Choppy opens with no direction — if both sides of the range get broken, stand down for the day
- Taking more than 1–2 ORB signals per day (whipsaw protection)

## Stats (rough)
- Win rate: 40–55%
- R:R: 1:2 to 1:4

## Notes for Automation
One of the easiest intraday strategies to code — completely rule-based with a natural daily reset. Key backtest variables: range duration (5/15/30 min), volume filter threshold, and a "one attempt per direction per day" rule. Widely studied, so expect a thin edge that depends heavily on execution costs.
