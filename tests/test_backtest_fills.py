"""Tests for trader.backtest.fills -- fee, slippage, and conservative
fill-price functions (BACK-02, BACK-03, D-04, D-06, D-07, D-08).

Every fill must bias against the trader, on both entries and exits, gapped
or not -- this is the property T-02-08 in the plan's threat model requires
be proven by test, not just documented.
"""

import pytest

try:
    from trader.backtest import fills
except ImportError:
    # trader.backtest.fills does not exist yet (RED phase) -- collection
    # must still succeed so all tests are collected; each test then fails
    # with an AttributeError on `fills` (None). Matches
    # tests/test_backtest_config.py's RED-phase-safe pattern.
    fills = None


# --- fee_for ---------------------------------------------------------


def test_fee_for_stock_below_minimum():
    # Per-share cost 0.005*100=0.50 loses to the $1.00 IBKR minimum.
    assert fills.fee_for("stock", qty=100, price=50.0) == pytest.approx(1.00)


def test_fee_for_stock_above_minimum():
    # Per-share cost 0.005*1000=5.00 now wins over the $1.00 minimum.
    assert fills.fee_for("stock", qty=1000, price=50.0) == pytest.approx(5.00)


def test_fee_for_crypto_major():
    assert fills.fee_for("crypto_major", qty=1.0, price=50000.0) == pytest.approx(
        0.0026 * 50000.0
    )


def test_fee_for_memecoin():
    assert fills.fee_for("memecoin", qty=1000.0, price=0.10) == pytest.approx(
        0.0026 * 100.0
    )


def test_fee_for_unknown_asset_class_raises_keyerror():
    with pytest.raises(KeyError):
        fills.fee_for("unknown_asset_class", qty=1.0, price=1.0)


# --- slippage_pct_for --------------------------------------------------


def test_slippage_pct_for_stock():
    # SLIPPAGE_PCT["stock"] = 0.05 (percent) -> fraction 0.05/100.
    assert fills.slippage_pct_for("stock") == pytest.approx(0.0005)


def test_slippage_pct_for_crypto_major():
    # SLIPPAGE_PCT["crypto_major"] = 0.10 (percent) -> fraction 0.10/100.
    # Deliberately NOT the small-cap-runner 2% tier per the orchestrator's
    # locked revision.
    assert fills.slippage_pct_for("crypto_major") == pytest.approx(0.0010)


def test_slippage_pct_for_memecoin():
    # SLIPPAGE_PCT["memecoin"] = 4.0 (percent) -> fraction 4.0/100.
    assert fills.slippage_pct_for("memecoin") == pytest.approx(0.04)


def test_slippage_pct_for_unknown_asset_class_raises_keyerror():
    with pytest.raises(KeyError):
        fills.slippage_pct_for("unknown_asset_class")


# --- apply_slippage -----------------------------------------------------


def test_apply_slippage_buy_stock_fills_higher():
    assert fills.apply_slippage(
        price=100.0, side="buy", asset_class="stock"
    ) == pytest.approx(100.0 * 1.0005)


def test_apply_slippage_sell_stock_fills_lower():
    assert fills.apply_slippage(
        price=100.0, side="sell", asset_class="stock"
    ) == pytest.approx(100.0 * 0.9995)


def test_apply_slippage_buy_crypto_major_uses_010_pct_not_small_cap_tier():
    assert fills.apply_slippage(
        price=100.0, side="buy", asset_class="crypto_major"
    ) == pytest.approx(100.0 * 1.0010)


def test_apply_slippage_unknown_asset_class_raises_keyerror():
    with pytest.raises(KeyError):
        fills.apply_slippage(price=100.0, side="buy", asset_class="unknown_asset_class")


# --- entry_fill_price -----------------------------------------------------


def test_entry_fill_price_matches_apply_slippage_on_bar_open():
    # Entries always fill at the bar's open (D-04), then slippage layers on.
    assert fills.entry_fill_price(
        bar_open=100.0, asset_class="crypto_major", side="buy"
    ) == fills.apply_slippage(100.0, "buy", "crypto_major")


def test_entry_fill_price_unknown_asset_class_raises_keyerror():
    with pytest.raises(KeyError):
        fills.entry_fill_price(
            bar_open=100.0, asset_class="unknown_asset_class", side="buy"
        )


# --- worse_of_fill -----------------------------------------------------


def test_worse_of_fill_stop_no_gap_trigger_price_stands():
    # Bar opened above the stop -- no gap -- the trigger price stands.
    assert (
        fills.worse_of_fill(trigger_price=90.0, bar_open=95.0, side="sell") == 90.0
    )


def test_worse_of_fill_stop_gap_through_uses_worse_open():
    # Bar gapped down through the stop -- the worse, lower open price
    # applies, per D-04's gap-through rule.
    assert (
        fills.worse_of_fill(trigger_price=90.0, bar_open=80.0, side="sell") == 80.0
    )


def test_worse_of_fill_take_profit_caps_at_trigger_never_improves():
    # A favourable gap past a take-profit still fills at the TP price,
    # never better -- TP fills never improve past the target. This is the
    # deliberate asymmetry vs. the stop case above (T-02-08).
    assert (
        fills.worse_of_fill(trigger_price=110.0, bar_open=115.0, side="sell_at_tp")
        == 110.0
    )


def test_worse_of_fill_short_side_not_implemented():
    # Phase 2 is long-only (D-15); short-side exits are documented as
    # unimplemented rather than silently wrong.
    with pytest.raises(NotImplementedError):
        fills.worse_of_fill(trigger_price=90.0, bar_open=95.0, side="buy")
