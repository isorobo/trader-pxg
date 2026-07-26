"""Tests for trader.paper.entry_pipeline -- the once-daily live entry
pipeline (05-06-PLAN.md, twice-revised: symbol-only assign_exit_profile,
unconditional STEP 0 heal pass before the trading-day/halt gates).

Uses the paper_conn fixture (tests/conftest.py, every migration applied),
mirroring tests/test_guardian.py's fixture shapes.
"""

from __future__ import annotations

import inspect
from datetime import date

import pandas as pd
import pytest

from trader.backtest.config import EXIT_PROFILE
from trader.backtest.universe import STOCK_UNIVERSE
from trader.paper import config as paper_config
from trader.paper import entry_pipeline, ledger

TRADING_DAY = date(2026, 7, 27)  # a real NYSE Monday

_LIVE_PROFILE_NAMES = [cfg.profile_name for cfg in paper_config.LIVE_STRATEGY_CONFIGS]


# ---------------------------------------------------------------------------
# Fixtures / test doubles
# ---------------------------------------------------------------------------


def _rising_bars_df(
    end: str = "2026-07-24",
    periods: int = 35,
    base_price: float = 100.0,
    base_volume: float = 2_000_000.0,
    daily_pct: float = 0.01,
    volume_surge_mult: float = 2.0,
) -> pd.DataFrame:
    """A monotonically-rising OHLCV fixture guaranteed to fire the loose
    momentum signal on its last bar: every delta is a gain (RSI == 100.0,
    clearing loose's 50.0 floor), every day's close is a new high (today's
    close beats the trailing high), and the final day's volume surges 2x
    over the flat baseline (clearing loose's 1.5x multiplier). >=30 bars
    also clears the risk gate's MIN_LISTING_AGE_DAYS floor by default."""
    dates = pd.bdate_range(end=end, periods=periods, tz="UTC")
    closes = [base_price * (1 + daily_pct) ** i for i in range(periods)]
    highs = [c * 1.001 for c in closes]
    lows = [c * 0.999 for c in closes]
    volumes = [base_volume] * periods
    volumes[-1] = base_volume * volume_surge_mult
    return pd.DataFrame(
        {"open": list(closes), "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=dates,
    )


def _flat_short_bars_df(
    end: str = "2026-07-24", periods: int = 5, price: float = 50.0, volume: float = 1_000_000.0
) -> pd.DataFrame:
    """Too short (< BREAK_LOOKBACK + 1 == 21) to ever fire the loose
    momentum signal -- the default fixture for every non-focal symbol in
    STOCK_UNIVERSE."""
    dates = pd.bdate_range(end=end, periods=periods, tz="UTC")
    return pd.DataFrame(
        {
            "open": [price] * periods,
            "high": [price] * periods,
            "low": [price] * periods,
            "close": [price] * periods,
            "volume": [volume] * periods,
        },
        index=dates,
    )


def _patch_bars(monkeypatch, bars_by_symbol: dict[str, pd.DataFrame], default=None) -> None:
    """Patch entry_pipeline.get_daily_bars so every call returns a
    pre-built DataFrame keyed by symbol (never touching the network/db),
    truncated to <= the requested `end` -- mirroring
    trader.data.api.get_daily_bars's own cache-read truncation."""
    if default is None:
        default = _flat_short_bars_df()

    def _fake_get_daily_bars(symbol, start=None, end=None, asset_class=None, conn=None):
        df = bars_by_symbol.get(symbol, default)
        if end is not None:
            cutoff = pd.Timestamp(end, tz="UTC")
            df = df[df.index <= cutoff]
        return df

    monkeypatch.setattr(entry_pipeline, "get_daily_bars", _fake_get_daily_bars)


def _open_position(conn, strategy_id: str, symbol: str, entry_order_ref: str) -> int:
    profile = EXIT_PROFILE(
        stop_pct=-0.10, tp_pct=None, scale_out=(), trailing_pct=None,
        max_hold_days=None, eod_flat=False,
    )
    return ledger.open_position(
        conn, strategy_id, symbol, "ibkr_paper", "stock", 10.0, 100.0,
        "2026-07-01T09:30:00", entry_order_ref, profile,
    )


# ---------------------------------------------------------------------------
# Task 1 -- scan_candidates
# ---------------------------------------------------------------------------


def test_scan_candidates_returns_fired_symbol_with_rsi_score_and_volatility(paper_conn, monkeypatch):
    _patch_bars(monkeypatch, {"AAPL": _rising_bars_df()})

    candidates = entry_pipeline.scan_candidates(paper_conn, TRADING_DAY)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["symbol"] == "AAPL"
    assert candidate["venue"] == "smart"
    assert candidate["score"] == pytest.approx(100.0)  # monotonic uptrend -> RSI 100
    assert candidate["volatility"] > 0


def test_scan_candidates_never_includes_a_symbol_already_open(paper_conn, monkeypatch):
    _patch_bars(monkeypatch, {"AAPL": _rising_bars_df()})
    _open_position(paper_conn, "some_other_strategy", "AAPL", "some_other_ref")

    candidates = entry_pipeline.scan_candidates(paper_conn, TRADING_DAY)

    assert candidates == []


def test_scan_candidates_none_fire_when_all_bars_too_short(paper_conn, monkeypatch):
    _patch_bars(monkeypatch, {})  # every universe symbol gets the default short fixture

    assert entry_pipeline.scan_candidates(paper_conn, TRADING_DAY) == []


# ---------------------------------------------------------------------------
# Task 1 -- assign_exit_profile (RESIDUAL BLOCKER 1: symbol-only, no date)
# ---------------------------------------------------------------------------


def test_assign_exit_profile_signature_has_no_date_param():
    sig = inspect.signature(entry_pipeline.assign_exit_profile)
    assert list(sig.parameters) == ["symbol", "live_profile_names"]


def test_assign_exit_profile_deterministic_across_simulated_days():
    """No date parameter exists at all -- two independent calls (standing
    in for "day 1" and "day 2", since the function itself can never see a
    date) return the identical profile_name."""
    day1_result = entry_pipeline.assign_exit_profile("AAPL", _LIVE_PROFILE_NAMES)
    day2_result = entry_pipeline.assign_exit_profile("AAPL", _LIVE_PROFILE_NAMES)
    assert day1_result == day2_result

    # A third, independent call with a differently-ordered but
    # value-identical list also agrees (sorted() internally).
    reordered = list(reversed(_LIVE_PROFILE_NAMES))
    assert entry_pipeline.assign_exit_profile("AAPL", reordered) == day1_result


def test_assign_exit_profile_never_returns_a_name_outside_the_live_list():
    live_subset = [_LIVE_PROFILE_NAMES[0], _LIVE_PROFILE_NAMES[2]]
    for symbol in STOCK_UNIVERSE:
        assert entry_pipeline.assign_exit_profile(symbol, live_subset) in live_subset


def test_assign_exit_profile_distribution_not_skewed_across_symbols():
    assignments = {
        entry_pipeline.assign_exit_profile(symbol, _LIVE_PROFILE_NAMES)
        for symbol in STOCK_UNIVERSE
    }
    # Coarse fairness check across the 18-symbol universe: not every symbol
    # funnels into the same one or two profiles.
    assert len(assignments) >= 3


def test_live_profile_names_raises_when_all_five_retired(paper_conn):
    for cfg in paper_config.LIVE_STRATEGY_CONFIGS:
        ledger.retire_strategy(paper_conn, cfg.profile_name, "max_drawdown", -0.5)

    with pytest.raises(RuntimeError):
        entry_pipeline._live_profile_names(paper_conn)


def test_live_profile_names_excludes_only_retired_configs(paper_conn):
    retired_name = _LIVE_PROFILE_NAMES[0]
    ledger.retire_strategy(paper_conn, retired_name, "consecutive_losses", 8)

    names = entry_pipeline._live_profile_names(paper_conn)

    assert retired_name not in names
    assert len(names) == len(_LIVE_PROFILE_NAMES) - 1
