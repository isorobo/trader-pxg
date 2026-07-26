---
phase: 05-paper-trading-loop
plan: 03
subsystem: infra
tags: [ib_async, ccxt, ibkr, paper-trading, broker-adapter, mockable]

# Dependency graph
requires:
  - phase: 05-paper-trading-loop (05-01)
    provides: trader/paper/config.py (IBKR_HOST/IBKR_PAPER_PORT/IBKR_CLIENT_ID_ENV), trader/paper/idempotency.py, trader/paper/ledger.py
provides:
  - trader/paper/broker_ibkr.py -- mockable IBKRBrokerAdapter (connect/disconnect/place_order/snapshot/latest_price) + round_shares_down
  - trader/paper/broker_crypto_sim.py -- fetch_price/simulate_fill/kraken_balance_check
  - tests/conftest.py's fake_ib fixture, shared by every later Phase 5 plan needing a fake broker
affects: [05-05-guardian, 05-06-entry-pipeline, 05-04-reconciliation]

# Tech tracking
tech-stack:
  added: [ib_async==2.1.0 (already pinned in requirements.txt by an earlier plan)]
  patterns:
    - "Constructor-injected client (ib_client=/client=), production default lazily imports the real library only inside the I/O method (connect(), fetch_price(), kraken_balance_check()), never at module import time"
    - "Defence-in-depth guard checked at call time in addition to the constructor default (connect() re-asserts port==4002)"

key-files:
  created:
    - trader/paper/broker_ibkr.py
    - trader/paper/broker_crypto_sim.py
    - tests/test_broker_ibkr.py
    - tests/test_broker_crypto_sim.py
  modified:
    - tests/conftest.py

key-decisions:
  - "round_shares_down uses int(dollar_amount // price) floor division only -- never rounds up or to-nearest, so a rounded share count can never exceed the sizer's dollar allocation"
  - "IBKRBrokerAdapter.connect() raises ValueError for any port != 4002, checked at call time even though the constructor already defaults to and normally receives the paper port (standing rule 6, T-05-06, defence in depth)"
  - "kraken_balance_check(api_key=None, api_secret=None, client=None) resolves credentials from arguments first, falling back to config.KRAKEN_API_KEY_ENV/KRAKEN_API_SECRET_ENV read at call time -- returns None (never raises) if either is still unset, matching D-04's 'if present, never a hard blocker' rule"

patterns-established:
  - "fake_ib fixture (tests/conftest.py): a MagicMock stand-in for ib_async.IB with positions()/openTrades()/fills() defaulting to empty lists and placeOrder() returning a configurable fake Trade -- reused by guardian, entry_pipeline, and reconciliation tests in later plans"

requirements-completed: [PAPER-01, PAPER-02]

# Metrics
duration: 25min
completed: 2026-07-26
---

# Phase 05 Plan 03: IBKR Paper Broker + Crypto Sim Adapters Summary

**Mockable ib_async adapter pinned to port 4002 with whole-share flooring, plus a ccxt-based crypto sim adapter that is provably order-free.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-07-26
- **Tasks:** 2 completed
- **Files modified:** 5 (2 created source modules, 2 created test modules, 1 modified conftest)

## Accomplishments
- `trader/paper/broker_ibkr.py`: `IBKRBrokerAdapter` (connect/disconnect/place_order/snapshot/latest_price), constructor-injectable `ib_client`, lazy `ib_async` import confined to `connect()`/`place_order()`/`latest_price()` so importing the module never requires `ib_async` or a live Gateway.
- `round_shares_down(dollar_amount, price)`: pure floor-division helper -- `round_shares_down(3412.50, 87.30) == 39`, never 39.09 or 40; a dedicated test asserts the result times price never exceeds the dollar amount.
- `connect()` raises `ValueError` for any port other than 4002 (checked at call time, not just via the constructor default) -- proven by a dedicated test that also asserts `fake_ib.connect` was never called.
- `place_order` sets `order.orderRef` before submission and returns `perm_id` read from `trade.order.permId` (never `orderId`/`clientId`) -- pinned by a test that also inspects the real `ib_async` `Stock`/`MarketOrder` objects passed to the fake's `placeOrder`.
- `trader/paper/broker_crypto_sim.py`: `fetch_price` (injectable ccxt client), `simulate_fill` (pure, reuses `trader.backtest.fills.apply_slippage`/`fee_for` verbatim), `kraken_balance_check` (D-04's read-only, optional, never-a-hard-blocker sanity hook).
- `tests/conftest.py` gained a `fake_ib` fixture shared by this plan and reusable by every later Phase 5 plan (guardian, entry_pipeline, reconciliation) that needs a fake broker.

## Task Commits

Each task followed TDD (RED test commit, then GREEN implementation commit):

1. **Task 1: IBKR paper-broker adapter (mockable) + whole-share rounding**
   - `05c3096` - test(05-03): add failing test for IBKR paper-broker adapter
   - `83c7f34` - feat(05-03): implement IBKR paper-broker adapter + whole-share flooring
2. **Task 2: Crypto simulated-ledger price/fill adapter**
   - `df49702` - test(05-03): add failing test for crypto simulated-ledger price/fill adapter
   - `bbfe53d` - feat(05-03): implement crypto simulated-ledger price/fill adapter

_RED confirmed for both tasks: the test module was temporarily run against the implementation file moved aside, verifying an `ImportError` before the implementation was restored and re-verified green._

## Files Created/Modified
- `trader/paper/broker_ibkr.py` - `IBKRBrokerAdapter` + `round_shares_down`; mockable, port-4002-pinned, orderRef/permId capture
- `trader/paper/broker_crypto_sim.py` - `fetch_price`/`simulate_fill`/`kraken_balance_check`; price-only, never places a real order
- `tests/test_broker_ibkr.py` - 15 tests covering connect/disconnect/place_order/snapshot/latest_price/round_shares_down
- `tests/test_broker_crypto_sim.py` - 9 tests covering fetch_price/simulate_fill/kraken_balance_check and the no-order-placement grep-equivalent assertion
- `tests/conftest.py` - added the `fake_ib` fixture

## Decisions Made
- Used plain test-double classes (`_FakePosition`/`_FakeFill`/`_FakeTicker`/etc.) rather than `MagicMock` for `snapshot()`/`latest_price()` assertions in `test_broker_ibkr.py`, so an attribute-shape mistake in `broker_ibkr.py` (e.g. reading `.contract.symbol` on something that doesn't have it) surfaces as `AttributeError` instead of silently returning a `MagicMock`.
- `kraken_balance_check` accepts `api_key`/`api_secret` as optional arguments with an env-var fallback (rather than requiring the caller to always pass resolved values), so a future caller in `guardian.py`/`entry_pipeline.py` can call it with no arguments at all and get the D-04-mandated "skip silently if absent" behaviour for free.

## Deviations from Plan

None - plan executed exactly as written. `ib_async==2.1.0` was already present in `requirements.txt` from an earlier plan (05-01/05-02), so no change to that file was needed despite the plan listing it under `files_modified`.

## Issues Encountered

One self-caught issue during Task 2's GREEN run: the module's own docstring initially contained the literal substrings "createorder"/"placeorder" (in a comment describing the threat mitigation itself), which made `test_simulate_fill_never_imports_or_calls_order_placement`'s substring check fail against the intended target (real order-placement calls, not documentation prose). Fixed by rewording the docstring to describe the mitigation without using those literal method-name substrings, re-verified with the same test (Rule 1 - the check needed to test actual behavior, not accidentally flag its own documentation).

## User Setup Required

None - no external service configuration required. Both adapters are exercised entirely through injected fakes in this plan; live IB Gateway connection (D-03) and Kraken API keys (D-04) remain human checkpoints for later plans/phase gates, not required here.

## Next Phase Readiness

- `trader/paper/broker_ibkr.py` and `trader/paper/broker_crypto_sim.py` are ready for 05-05 (guardian) and 05-06 (entry_pipeline) to consume without ever touching `ib_async`/`ccxt` objects directly.
- The `fake_ib` fixture in `tests/conftest.py` is available for reuse by 05-04 (reconciliation), 05-05, and 05-06's test suites.
- Full suite: 413 passed (389 baseline + 24 new: 15 in `test_broker_ibkr.py`, 9 in `test_broker_crypto_sim.py`).

---
*Phase: 05-paper-trading-loop*
*Completed: 2026-07-26*
