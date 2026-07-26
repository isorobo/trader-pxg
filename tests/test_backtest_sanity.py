"""The permanent BACK-07 exit-gate sanity test (D-14) -- the phase's soul.

"Buy a random universe symbol, hold one day, repeat" must lose money at
roughly the fee+slippage rate. If it ever profits on average, the harness
(not the strategy) is broken, and this test fails the suite (D-14).

Runs the seeded random strategy (trader.backtest.random_strategy.pick_entries)
over the full pinned SANITY_UNIVERSE (trader.backtest.sanity_universe),
entirely offline against the real, already-populated shared data/trader.db
cache -- get_daily_bars(symbol, conn=None) is a cache-hit-only read here (no
mocks, no live network in this test itself); Task 1's one-time backfill is
what actually populated the cache.

Non-circular tolerance band (Pitfall 6, 02-RESEARCH.md Q4): the band's
CENTER (expected_bias) is the sum of two independently-derived, deterministic
terms -- NEVER the observed mean pnl itself, and never re-centered on it:

1. expected_cost_bias -- the mean, across all trades, of each trade's own
   -(fees + slippage), read directly from that trade row's own recorded
   fees/slippage columns (config-derived quantities fixed at fill time).

2. expected_drift_bias -- a documented, discovered addition (see "Deviation"
   note below): the mean, across all trades, of each trade's OWN SYMBOL's
   long-run average one-day price return, computed from that symbol's FULL
   cached raw OHLCV history (trader.data.api.get_daily_bars' own bars,
   independent of this run's strategy or its trades) via
   _symbol_average_daily_return. This is exogenous MARKET data, fixed before
   run_backtest is ever called -- it cannot be tuned to this run's outcome
   and is not derived from any trade's pnl column, so it does not reopen
   Pitfall 6's circularity hole; it only supplies the piece of "expected
   mean pnl" that pure fee/slippage accounting cannot ever capture (real
   price movement).

Only the band's WIDTH uses the run's own empirical standard error of
observed pnl_pct (unchanged by the deviation below). A hard fail-safe (mean
pnl_pct < 0) is asserted independently of the band, so a harness bug that
happens to land inside a wrongly-wide band still cannot silently pass.

Deviation from a literal cost-only expected_bias (documented, Rule 1 --
auto-fixed bug in the test's own statistical design, not the harness):
SANITY_UNIVERSE pins AAPL/MSFT/GOOGL/BTC/ETH/DOGE precisely because they are
famous, historically successful assets -- every one of them has a large,
genuinely positive average one-day return over its own full cached history
(measured directly, independent of any run: AAPL +0.109%/day, MSFT
+0.108%/day, GOOGL +0.107%/day, BTC/USDT +0.146%/day, ETH/USDT +0.161%/day,
DOGE/USDT +0.380%/day -- a well-known survivorship effect: assets picked as
a "known crypto/large-cap universe" are, almost definitionally, the ones
that went up a lot). A cost-only expected_bias implicitly assumes zero mean
daily price return, an assumption 02-RESEARCH.md's own Q4 method never
actually verified against this real universe (Assumption A2 flags exactly
this: "the planner/implementer must recompute this from the actual pinned
universe's realized volatility, not copy the example number verbatim").
Verified during implementation (multiple fixed seeds: 1, 7, 42, 555, 999,
12345, 20260726; N ranging 11,849-11,851 trades): with a cost-only
expected_bias, the observed mean pnl_pct sits OUTSIDE the k=3-SE band by a
small (~0.15-0.20 percentage point), seed-ROBUST margin every single time --
never inside it, never on the profitable side. Isolating and excluding the
pre-2000s sub-$1.00 split-adjusted AAPL/MSFT trades (a separate, also-real
per-share-fee degeneracy at penny-level historical prices) narrows but does
NOT close this gap, proving the residual is priced-in market drift, not a
fee-model artifact. Adding expected_drift_bias (computed once, up front,
from raw price history alone) closes the gap and passes cleanly and
robustly across all seven seeds tested -- this is the fix for a discovered
flaw in the ORIGINAL naive zero-drift assumption, not a loosening of the
band's width (k stays 3.0) and not a re-centering on this run's own observed
mean (drift is fixed before the run executes, from data the run never
touches).
"""

from __future__ import annotations

import math
import statistics

import pandas as pd
import pytest

from trader.backtest import config, ledger, runner
from trader.backtest.random_strategy import pick_entries
from trader.backtest.sanity_universe import SANITY_UNIVERSE
from trader.data import db as data_db
from trader.data.api import get_daily_bars

# Fixed seed (D-12 reproducibility) -- pinned, not re-rolled per run.
_SEED = 20260726

# Hard N floor (02-RESEARCH.md Q4): large enough that daily price-return
# noise does not swamp the fee/slippage signal this test targets.
_MIN_TRADES = 3000

# Number of standard errors of half-width for the tolerance band (Q4's
# recommended conservative default) -- unchanged by the drift deviation.
_STANDARD_ERROR_K = 3.0

_BACKFILL_HINT = (
    "run `python -m trader.backtest.sanity_universe` to backfill the "
    "pinned sanity universe before running this test."
)


def _notional(trade: dict) -> float:
    """A trade row's notional: its own entry_price * qty (never the config
    DEFAULT_NOTIONAL constant directly, since qty already varies per
    symbol's entry price)."""
    return trade["entry_price"] * trade["qty"]


def _pnl_pct(trade: dict) -> float:
    """This trade's pnl expressed as a fraction of its own notional."""
    return trade["pnl"] / _notional(trade)


def _cost_pct(trade: dict) -> float:
    """This trade's own recorded fees+slippage cost, expressed as a NEGATIVE
    fraction of its notional -- read directly from the trade row's fees/
    slippage columns (deterministic, config-derived quantities). NEVER
    derived from the trade's pnl column or the run's observed mean -- that
    would be Pitfall 6's circular tolerance-band derivation."""
    return -(trade["fees"] + trade["slippage"]) / _notional(trade)


def _symbol_average_daily_return(df: pd.DataFrame) -> float:
    """symbol's own mean close-to-close one-day return over its FULL cached
    history in df -- a fixed, exogenous market-data statistic computed
    before run_backtest is ever called, independent of which days any
    strategy happens to sample into trades. This is what makes
    expected_drift_bias (module docstring) non-circular: it never reads a
    single value from backtest_trades or from this run's own outcome."""
    closes = df["close"].tolist()
    daily_returns = [
        (closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))
    ]
    return statistics.mean(daily_returns)


def test_random_strategy_loses_roughly_fees_and_slippage():
    """BACK-07/D-14: over the full pinned SANITY_UNIVERSE, the seeded random
    strategy's mean per-trade P&L must fall within a standard-error-derived
    band around the run's own analytically-expected fee+slippage-and-drift
    total, and must be strictly negative -- proving the harness never
    profits from pure randomness.
    """
    bars_by_symbol = {}
    symbol_drift = {}
    for symbol in SANITY_UNIVERSE:
        asset_class = "stock" if "/" not in symbol else None
        df = get_daily_bars(symbol, asset_class=asset_class, conn=None)
        if df.empty:
            pytest.fail(f"{symbol} has no cached bars in data/trader.db -- {_BACKFILL_HINT}")
        bars_by_symbol[symbol] = df
        symbol_drift[symbol] = _symbol_average_daily_return(df)

    # A real connection to the same shared data/trader.db that Task 1's
    # backfill populated -- reused here so resolve_instrument finds the
    # crypto symbols already classified (no live CoinGecko call), and so
    # backtest_runs/backtest_trades land in the shared ledger per D-11.
    conn = data_db.get_connection()
    try:
        run_id = runner.run_backtest(
            strategy_fn=pick_entries,
            universe=SANITY_UNIVERSE,
            profile=config.PROFILE_TIME_STOP_1D,
            bars_by_symbol=bars_by_symbol,
            seed=_SEED,
            params={"profile_name": "PROFILE_TIME_STOP_1D", "sanity_test": True},
            strategy_id="sanity_random_strategy",
            conn=conn,
        )
        trades = ledger.get_trades_for_run(conn, run_id)
    finally:
        conn.close()

    if len(trades) < _MIN_TRADES:
        pytest.fail(
            f"Only {len(trades)} trades were produced against the pinned "
            f"sanity universe -- expected at least {_MIN_TRADES}. If this "
            f"is a fresh clone with an empty cache, {_BACKFILL_HINT} "
            "Otherwise the pinned universe's cached history is no longer "
            "sufficient to power this test at its required statistical "
            "power."
        )

    pnl_pct_list = [_pnl_pct(trade) for trade in trades]

    # Non-circular center: each trade's own recorded fees/slippage cost plus
    # its own symbol's pre-computed, run-independent average daily return
    # (module docstring's "Deviation" note) -- never the observed mean pnl
    # itself (Pitfall 6).
    expected_bias_list = [
        _cost_pct(trade) + symbol_drift[trade["symbol"]] for trade in trades
    ]
    expected_bias = statistics.mean(expected_bias_list)
    observed_mean = statistics.mean(pnl_pct_list)
    standard_error = statistics.stdev(pnl_pct_list) / math.sqrt(len(pnl_pct_list))

    lower_bound = expected_bias - _STANDARD_ERROR_K * standard_error
    upper_bound = expected_bias + _STANDARD_ERROR_K * standard_error

    # Hard fail-safe, independent of the band: a harness bug that happens to
    # land inside a wrongly-wide band still cannot silently pass this test.
    assert observed_mean < 0, (
        f"Random strategy's mean per-trade P&L ({observed_mean:.6f}) is not "
        f"negative over N={len(pnl_pct_list)} trades -- if this harness ever "
        "profits on average from pure random one-day holds, the harness "
        "(not the strategy) is broken (D-14)."
    )

    assert lower_bound <= observed_mean <= upper_bound, (
        f"Observed mean pnl_pct {observed_mean:.6f} (N={len(pnl_pct_list)}) "
        f"falls outside the derived tolerance band ({lower_bound:.6f}, "
        f"{upper_bound:.6f}) around expected_bias {expected_bias:.6f} "
        f"(k={_STANDARD_ERROR_K} standard errors, se={standard_error:.6f})."
    )
