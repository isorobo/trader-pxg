"""Tests for the two strategies Phase 2 needs to prove the harness honest
(BACK-07): trader.backtest.random_strategy (D-14's sanity-test engine) and
trader.backtest.momentum_placeholder (D-15's end-to-end proof).

Both implement the shared strategy_fn contract from
trader/backtest/iterator.py's module docstring / 02-07-PLAN.md's interfaces
block:

    pick_entries(iterator, date, open_positions, rng) -> list[str]

Fixtures reuse tests/test_backtest_iterator.py's hand-built OHLCV DataFrame
pattern, building real PointInTimeIterator instances rather than mocks
(iterator.py already exists from plan 02-02).
"""

import random

import pandas as pd

from trader.backtest import iterator

try:
    from trader.backtest import random_strategy
except ImportError:
    # trader.backtest.random_strategy does not exist yet (RED phase) --
    # collection must still succeed; each test then fails with an
    # AttributeError on `random_strategy` (None).
    random_strategy = None


def _bars_on_dates(dates: list[str], base: float = 100.0) -> pd.DataFrame:
    """Same fixture-DataFrame shape as test_backtest_iterator.py's
    _make_bars: a small hand-built OHLCV frame indexed by explicit calendar
    dates, used where symbol-to-symbol calendar gaps matter (the random
    strategy's availability filter)."""
    index = pd.to_datetime(dates, utc=True)
    n = len(dates)
    return pd.DataFrame(
        {
            "open": [base + i for i in range(n)],
            "high": [base + 5.0 + i for i in range(n)],
            "low": [base - 1.0 + i for i in range(n)],
            "close": [base + 3.0 + i for i in range(n)],
            "volume": [1000.0 + i for i in range(n)],
        },
        index=index,
    )


# --- random_strategy fixtures (D-14) ----------------------------------------

# 10-day calendar; DDD and EEE are missing 2026-01-06 -- only AAA, BBB, CCC
# have a bar on TARGET_DATE, exercising the availability filter (D-14's
# "never pick a symbol with no bar today").
FULL_DATES = [f"2026-01-{day:02d}" for day in range(1, 11)]
GAPPED_DATES = [d for d in FULL_DATES if d != "2026-01-06"]
TARGET_DATE = "2026-01-06"


def _random_universe():
    return iterator.PointInTimeIterator(
        {
            "AAA": _bars_on_dates(FULL_DATES, base=100.0),
            "BBB": _bars_on_dates(FULL_DATES, base=200.0),
            "CCC": _bars_on_dates(FULL_DATES, base=300.0),
            "DDD": _bars_on_dates(GAPPED_DATES, base=400.0),
            "EEE": _bars_on_dates(GAPPED_DATES, base=500.0),
        }
    )


def test_random_picks_one_symbol_from_available_only():
    it = _random_universe()

    picks = random_strategy.pick_entries(it, TARGET_DATE, set(), random.Random(42))

    assert len(picks) == 1
    assert picks[0] in {"AAA", "BBB", "CCC"}


def test_random_is_deterministic_given_fixed_seed():
    it = _random_universe()

    first = random_strategy.pick_entries(it, TARGET_DATE, set(), random.Random(42))
    second = random_strategy.pick_entries(it, TARGET_DATE, set(), random.Random(42))

    assert first == second


def test_random_never_repicks_open_position():
    it = _random_universe()
    already_open = random_strategy.pick_entries(
        it, TARGET_DATE, set(), random.Random(42)
    )[0]

    picks = random_strategy.pick_entries(
        it, TARGET_DATE, {already_open}, random.Random(42)
    )

    assert already_open not in picks
    assert picks[0] in ({"AAA", "BBB", "CCC"} - {already_open})


def test_random_returns_empty_when_no_symbols_have_a_bar_on_date():
    it = _random_universe()
    no_bar_date = "2026-02-01"  # outside every symbol's fixture date range

    picks = random_strategy.pick_entries(it, no_bar_date, set(), random.Random(42))

    assert picks == []
