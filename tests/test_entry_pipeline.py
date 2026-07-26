"""Tests for trader.paper.entry_pipeline -- the once-daily live entry
pipeline (05-06-PLAN.md, twice-revised: symbol-only assign_exit_profile,
unconditional STEP 0 heal pass before the trading-day/halt gates).

Uses the paper_conn fixture (tests/conftest.py, every migration applied) and
the fake_ib fixture (a MagicMock standing in for ib_async.IB), mirroring
tests/test_guardian.py's fixture shapes exactly. entry_pipeline.alerts.notify
and entry_pipeline.ops_log.append_ops_log are replaced with no-op MagicMocks
in every test (autouse) so this suite never writes into the real repo's
ops/ directory.
"""

from __future__ import annotations

import inspect
import re
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from trader.backtest.config import EXIT_PROFILE
from trader.backtest.universe import STOCK_UNIVERSE
from trader.paper import config as paper_config
from trader.paper import entry_pipeline, ledger
from trader.paper.broker_ibkr import IBKRBrokerAdapter

TRADING_DAY = date(2026, 7, 27)  # a real NYSE Monday
TRADING_DAY_2 = date(2026, 7, 28)
WEEKEND_DAY = date(2026, 8, 1)  # a Saturday

_LIVE_PROFILE_NAMES = [cfg.profile_name for cfg in paper_config.LIVE_STRATEGY_CONFIGS]


@pytest.fixture(autouse=True)
def _mock_side_effects(monkeypatch):
    """entry_pipeline.alerts.notify and entry_pipeline.ops_log.append_ops_log
    are replaced with no-op MagicMocks in every test -- the real
    implementations write into the repo's ops/ directory as a side effect,
    which this suite must never do (mirrors tests/test_guardian.py's
    _mock_alerts_notify convention, extended to ops_log since entry_pipeline
    calls it directly, not only via alerts.notify)."""
    monkeypatch.setattr(entry_pipeline.alerts, "notify", MagicMock(return_value=True))
    monkeypatch.setattr(entry_pipeline.ops_log, "append_ops_log", MagicMock())


# ---------------------------------------------------------------------------
# Fixtures / test doubles (mirrors tests/test_guardian.py's shapes exactly)
# ---------------------------------------------------------------------------


class _FakeTicker:
    def __init__(self, market_price):
        self._market_price = market_price

    def marketPrice(self):
        return self._market_price


class _FakeExecution:
    def __init__(self, order_ref: str, perm_id: int, shares: float):
        self.orderRef = order_ref
        self.permId = perm_id
        self.shares = shares


class _FakeContract:
    def __init__(self, symbol: str):
        self.symbol = symbol


class _FakeFill:
    def __init__(self, execution: _FakeExecution, contract: _FakeContract):
        self.execution = execution
        self.contract = contract


def _make_fake_fill(order_ref: str, perm_id: int, symbol: str, qty: float) -> _FakeFill:
    return _FakeFill(_FakeExecution(order_ref, perm_id, qty), _FakeContract(symbol))


def _ibkr_adapter(fake_ib, latest_price: float | None = None) -> IBKRBrokerAdapter:
    if latest_price is not None:
        fake_ib.reqMktData.return_value = _FakeTicker(latest_price)
    return IBKRBrokerAdapter(host="127.0.0.1", port=4002, client_id=5, ib_client=fake_ib)


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
    STOCK_UNIVERSE, and for a deliberately-orphaned symbol whose signal must
    NOT re-fire (RESIDUAL BLOCKER 1's exact scenario)."""
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
    trader.data.api.get_daily_bars's own cache-read truncation. Every
    symbol not explicitly listed gets `default` (a too-short, never-fires
    fixture) so only intentionally-configured symbols can ever fire."""
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


# ---------------------------------------------------------------------------
# Task 2 -- happy path: STEP0(no-op) -> gate -> sizer -> round -> submit
# ---------------------------------------------------------------------------


def test_full_happy_path_scans_gates_sizes_rounds_and_submits(paper_conn, fake_ib, monkeypatch):
    _patch_bars(monkeypatch, {"AAPL": _rising_bars_df()})
    fake_ib.placeOrder.return_value.order.permId = 555
    adapter = _ibkr_adapter(fake_ib)

    result = entry_pipeline.run_entry_pipeline_once(paper_conn, adapter, as_of_date=TRADING_DAY)

    assert result["candidates"] == 1
    assert result["accepted"] == 1
    assert len(result["submitted"]) == 1
    assert fake_ib.placeOrder.call_count == 1

    open_positions = ledger.get_open_positions(paper_conn)
    assert len(open_positions) == 1
    assert open_positions[0]["symbol"] == "AAPL"

    order = ledger.get_order_by_ref(paper_conn, result["submitted"][0])
    assert order["status"] == "submitted"
    assert order["side"] == "buy"
    assert order["intent"] == "entry"
    assert order["qty"] > 0


def test_qty_is_rounded_down_never_up(paper_conn, fake_ib, monkeypatch):
    _patch_bars(monkeypatch, {"AAPL": _rising_bars_df()})
    fake_ib.placeOrder.return_value.order.permId = 222
    adapter = _ibkr_adapter(fake_ib)

    result = entry_pipeline.run_entry_pipeline_once(paper_conn, adapter, as_of_date=TRADING_DAY)

    order = ledger.get_order_by_ref(paper_conn, result["submitted"][0])
    price = 100.0 * (1.01 ** 34)  # the fixture's last close (35 bars, i=0..34)
    # A single candidate against 0 open positions preliminary-weights to
    # 0.90 (1 - 0.10 cash reserve), which SIZER_SINGLE_POSITION_CAP (0.50)
    # binds down to -- an intentionally non-whole-share dollar allocation.
    dollar_amount = 0.50 * paper_config.PAPER_ACCOUNT_EQUITY
    expected_qty = entry_pipeline.broker_ibkr.round_shares_down(dollar_amount, price)

    assert order["qty"] == expected_qty
    assert expected_qty * price <= dollar_amount
    assert (expected_qty + 1) * price > dollar_amount


def test_rejected_candidate_never_reaches_sizer(paper_conn, fake_ib, monkeypatch):
    # 25 bars fires the loose signal (>= BREAK_LOOKBACK + 1 == 21) but
    # never clears the risk gate's MIN_LISTING_AGE_DAYS (30) floor.
    _patch_bars(monkeypatch, {"AAPL": _rising_bars_df(periods=25)})
    adapter = _ibkr_adapter(fake_ib)

    result = entry_pipeline.run_entry_pipeline_once(paper_conn, adapter, as_of_date=TRADING_DAY)

    assert result["candidates"] == 1
    assert result["accepted"] == 0
    assert result["submitted"] == []
    fake_ib.placeOrder.assert_not_called()
    assert ledger.get_open_positions(paper_conn) == []


# ---------------------------------------------------------------------------
# Task 2 -- STEP 0 (RESIDUAL BLOCKER 1): unscoped heal, non-refiring orphan
# ---------------------------------------------------------------------------


def test_step0_heals_orphan_whose_signal_never_refires(paper_conn, fake_ib, monkeypatch):
    """The exact RESIDUAL BLOCKER 1 scenario: an order is decided and
    persisted on one day for a symbol that will NOT fire again; the broker
    fills it, but the process crashes before update_order_status/
    open_position ever run. A LATER run -- where the symbol's fixture bars
    do NOT satisfy the loose momentum signal, so it never appears in
    scan_candidates's output at all -- still finds and heals the order via
    STEP 0, and does NOT call place_order for that symbol again."""
    _patch_bars(monkeypatch, {})  # MSFT (and every other symbol) never fires today

    stale_order_ref = f"{_LIVE_PROFILE_NAMES[0]}:MSFT:2026-07-20:buy:entry"
    ledger.record_order(
        paper_conn, stale_order_ref, _LIVE_PROFILE_NAMES[0], "MSFT", "ibkr_paper",
        "buy", "entry", 5, status="submitted",
    )
    fake_ib.fills.return_value = [_make_fake_fill(stale_order_ref, 321, "MSFT", 5)]
    adapter = _ibkr_adapter(fake_ib, latest_price=300.0)

    # Run on a DIFFERENT day than the one embedded in the stale order_ref --
    # proving the STEP 0 pass is genuinely date-independent, not merely
    # re-checking "today."
    result = entry_pipeline.run_entry_pipeline_once(paper_conn, adapter, as_of_date=TRADING_DAY_2)

    assert stale_order_ref in result["healed"]
    healed_order = ledger.get_order_by_ref(paper_conn, stale_order_ref)
    assert healed_order["status"] == "filled"

    open_positions = ledger.get_open_positions(paper_conn)
    assert len(open_positions) == 1
    assert open_positions[0]["symbol"] == "MSFT"
    assert open_positions[0]["qty"] == 5

    fake_ib.placeOrder.assert_not_called()


def test_step0_heals_even_when_both_halted_and_non_trading_day(paper_conn, fake_ib, monkeypatch):
    """BLOCKER 1 / RESIDUAL BLOCKER 1: healing never waits on the halt gate
    or on the next trading day."""
    stale_order_ref = f"{_LIVE_PROFILE_NAMES[1]}:AAPL:2026-07-24:buy:entry"
    ledger.record_order(
        paper_conn, stale_order_ref, _LIVE_PROFILE_NAMES[1], "AAPL", "ibkr_paper",
        "buy", "entry", 7, status="submitted",
    )
    fake_ib.fills.return_value = [_make_fake_fill(stale_order_ref, 55, "AAPL", 7)]
    adapter = _ibkr_adapter(fake_ib, latest_price=120.0)
    monkeypatch.setattr(entry_pipeline.reconcile, "is_entry_halted", lambda conn: True)
    monkeypatch.setattr(entry_pipeline.calendar_, "is_trading_day", lambda check_date: False)

    result = entry_pipeline.run_entry_pipeline_once(paper_conn, adapter, as_of_date=WEEKEND_DAY)

    assert result == {"skipped": "not_a_trading_day", "healed": [stale_order_ref]}
    assert ledger.get_order_by_ref(paper_conn, stale_order_ref)["status"] == "filled"
    assert len(ledger.get_open_positions(paper_conn)) == 1
    fake_ib.placeOrder.assert_not_called()


def test_halted_blocks_new_submission_but_not_step0_heal(paper_conn, fake_ib, monkeypatch):
    """A fresh AAPL candidate fires this run (passes gate + sizer + round)
    but is blocked at STEP 3 by is_entry_halted -- while an unrelated MSFT
    crash-orphan (no fresh signal this run) is healed via STEP 0
    regardless (BLOCKER 1: the heal check runs strictly before the halt
    check)."""
    _patch_bars(monkeypatch, {"AAPL": _rising_bars_df()})
    stale_order_ref = f"{_LIVE_PROFILE_NAMES[3]}:MSFT:2026-07-20:buy:entry"
    ledger.record_order(
        paper_conn, stale_order_ref, _LIVE_PROFILE_NAMES[3], "MSFT", "ibkr_paper",
        "buy", "entry", 5, status="submitted",
    )
    fake_ib.fills.return_value = [_make_fake_fill(stale_order_ref, 44, "MSFT", 5)]
    adapter = _ibkr_adapter(fake_ib, latest_price=300.0)
    monkeypatch.setattr(entry_pipeline.reconcile, "is_entry_halted", lambda conn: True)

    result = entry_pipeline.run_entry_pipeline_once(paper_conn, adapter, as_of_date=TRADING_DAY)

    assert stale_order_ref in result["healed"]
    assert result["candidates"] == 1
    assert result["accepted"] == 1
    assert result["submitted"] == []
    fake_ib.placeOrder.assert_not_called()

    symbols = {p["symbol"] for p in ledger.get_open_positions(paper_conn)}
    assert symbols == {"MSFT"}  # MSFT healed via STEP 0; AAPL blocked by the halt


# ---------------------------------------------------------------------------
# Task 2 -- resubmit safety (date-independent, same-day and cross-day)
# ---------------------------------------------------------------------------


def test_second_run_same_day_never_double_submits(paper_conn, fake_ib, monkeypatch):
    _patch_bars(monkeypatch, {"AAPL": _rising_bars_df()})
    fake_ib.placeOrder.return_value.order.permId = 111
    adapter = _ibkr_adapter(fake_ib)

    first = entry_pipeline.run_entry_pipeline_once(paper_conn, adapter, as_of_date=TRADING_DAY)
    order_ref = first["submitted"][0]

    # The broker now shows this run's own fill, as it would on the next tick.
    fake_ib.fills.return_value = [_make_fake_fill(order_ref, 111, "AAPL", 5)]

    second = entry_pipeline.run_entry_pipeline_once(paper_conn, adapter, as_of_date=TRADING_DAY)

    # AAPL is now an open position, so scan_candidates excludes it this run
    # -- STEP 0 still finds and heals the (now-filled) order via the
    # unscoped pass, but no candidates remain to size/submit.
    assert second.get("candidates") == 0
    assert order_ref in second["healed"]
    assert fake_ib.placeOrder.call_count == 1
    assert len(ledger.get_open_positions(paper_conn)) == 1


# ---------------------------------------------------------------------------
# Task 2 -- call-order proof (D-08 no-bypass path, BLOCKER 1)
# ---------------------------------------------------------------------------


def test_call_order_gate_then_sizer_then_halt_then_persist_then_submit(
    paper_conn, fake_ib, monkeypatch
):
    _patch_bars(monkeypatch, {"AAPL": _rising_bars_df()})
    fake_ib.placeOrder.return_value.order.permId = 777
    adapter = _ibkr_adapter(fake_ib)

    events: list[str] = []

    orig_gate = entry_pipeline.gate.apply_risk_gate

    def _gate_spy(*args, **kwargs):
        events.append("gate")
        return orig_gate(*args, **kwargs)

    orig_sizer = entry_pipeline.sizer.size_positions

    def _sizer_spy(*args, **kwargs):
        events.append("sizer")
        return orig_sizer(*args, **kwargs)

    orig_halted = entry_pipeline.reconcile.is_entry_halted

    def _halt_spy(conn):
        events.append("halt_check")
        return orig_halted(conn)

    orig_record_order = entry_pipeline.ledger.record_order

    def _record_order_spy(*args, **kwargs):
        events.append("record_order")
        return orig_record_order(*args, **kwargs)

    def _place_order_spy(symbol, action, quantity, order_ref):
        events.append("place_order")
        return {"order_ref": order_ref, "perm_id": 777, "status": "submitted"}

    monkeypatch.setattr(entry_pipeline.gate, "apply_risk_gate", _gate_spy)
    monkeypatch.setattr(entry_pipeline.sizer, "size_positions", _sizer_spy)
    monkeypatch.setattr(entry_pipeline.reconcile, "is_entry_halted", _halt_spy)
    monkeypatch.setattr(entry_pipeline.ledger, "record_order", _record_order_spy)
    monkeypatch.setattr(adapter, "place_order", _place_order_spy)

    entry_pipeline.run_entry_pipeline_once(paper_conn, adapter, as_of_date=TRADING_DAY)

    assert events.index("gate") < events.index("sizer")
    assert events.index("sizer") < events.index("halt_check")
    assert events.index("halt_check") < events.index("record_order")
    assert events.index("record_order") < events.index("place_order")


# ---------------------------------------------------------------------------
# Static source-shape assertions (acceptance criteria that must hold by
# construction, not merely by runtime behaviour on one fixture)
# ---------------------------------------------------------------------------


def _source() -> str:
    return Path(entry_pipeline.__file__).read_text(encoding="utf-8")


def test_exactly_one_place_order_call_site():
    assert _source().count("place_order(") == 1


def test_assign_exit_profile_call_site_has_exactly_two_positional_args():
    call_sites = re.findall(r"= assign_exit_profile\(([^)]*)\)", _source())
    assert len(call_sites) == 1
    args = [a.strip() for a in call_sites[0].split(",")]
    assert len(args) == 2


def test_no_rounding_up_function_used():
    source = _source()
    assert "round_shares_down" in source
    assert re.search(r"(?<!_)\bround\(", source) is None
    assert "math.ceil" not in source
    assert "ceil(" not in source


def test_record_order_default_status_is_pending_submit():
    assert 'status="pending_submit"' in _source()
