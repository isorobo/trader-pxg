# Crypto Paper-Trading Leg — Prepared Plan (NOT armed)

**Drafted:** 2026-07-30, during the owner's autonomous-work directive.
**Status:** Awaiting owner review. Nothing in the live system references
this plan; no crypto entry pipeline exists or is scheduled.

## Why it is a plan and not a build

The stock paper loop went live TODAY after a checkpoint that surfaced
three real-broker bugs. Wiring a second live trading leg into that
system overnight, unreviewed, is exactly the "it'll probably be fine"
standing rule 5 forbids. The evidence side is also honest about demand:
the first crypto sweep (Donchian, 2,520 tune runs) produced ZERO OOS
survivors — there is currently no crypto strategy with evidence worth
trading. The leg becomes worth building when a crypto survivor exists.

## What exists already

- `trader/paper/broker_crypto_sim.py` — the Phase 5 crypto sim adapter.
- `paper_orders`/`paper_positions`/`paper_trades` schema already accepts
  `venue='crypto_sim'` rows; guardian and reconcile handle the venue.
- Kraken read-only reconciliation hook (`kraken_readonly`, informational).
- The multi-signal scan (2026-07-30) makes per-family signal routing
  generic — a crypto family is one `signals.py` entry once live.

## The build, when approved

1. **Universe + data**: reuse `UNIVERSE_BY_BUCKET` crypto buckets and the
   existing bar cache/fetchers; crypto trades 24/7 so `calendar_` gets a
   venue-aware trading-day rule (crypto: every day).
2. **Entry pipeline**: a `--venue crypto_sim` variant of the existing
   pipeline (same STEP 0–5 skeleton, same gate/sizer, crypto slippage
   constants already in `SLIPPAGE_PCT`), or a venue loop inside the
   existing `--once` body — planner's choice at build time.
3. **Sizing**: same PAPER_ACCOUNT_EQUITY base; the sizer's 10% memecoin
   aggregate cap already exists and applies.
4. **Scheduling**: one more Task Scheduler pair; crypto runs daily
   including weekends.
5. **Gate**: only strategies with a crypto-bucket OOS survivor payload
   enter, via the same register_entrant + tournament caps path.

## Exit criteria for arming it

- At least one crypto-bucket OOS survivor exists in an evidence file.
- Owner has read this plan and said go.
- Full suite green after the build, and a supervised first `--once` run
  (the 05-08 lesson: real-broker/first-run bugs are found live, on
  purpose, before scheduling).
