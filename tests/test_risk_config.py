"""Tests for trader.risk.config -- frozen threshold constants for the gate,
sizer, and breakers (RISK-01/02/03 pre-registered defaults, 04-RESEARCH.md).
"""

try:
    from trader.backtest import config as backtest_config
    from trader.risk import config
except ImportError:
    # trader.risk.config does not exist yet (RED phase) -- collection must
    # still succeed so all tests are collected; each test then fails with an
    # AttributeError on `config` (None) when it tries to call into the
    # contract. Matches tests/test_backtest_config.py's RED-phase-safe
    # pattern.
    config = None
    backtest_config = None


def test_liquidity_window_stock_days():
    assert config.LIQUIDITY_WINDOW_STOCK_DAYS == 20


def test_liquidity_window_crypto_days():
    assert config.LIQUIDITY_WINDOW_CRYPTO_DAYS == 7


def test_min_dollar_volume_stock():
    assert config.MIN_DOLLAR_VOLUME_STOCK == 1_000_000.0


def test_min_quote_volume_crypto_major():
    assert config.MIN_QUOTE_VOLUME_CRYPTO_MAJOR == 5_000_000.0


def test_min_quote_volume_memecoin():
    assert config.MIN_QUOTE_VOLUME_MEMECOIN == 250_000.0


def test_min_listing_age_days():
    assert config.MIN_LISTING_AGE_DAYS == 30


def test_max_spread_pct_matches_backtest_slippage_pct():
    # MAX_SPREAD_PCT is a reuse of trader.backtest.config.SLIPPAGE_PCT as the
    # spread-ceiling proxy (04-RESEARCH.md Open Question 3) -- not a new set
    # of hand-typed literals. No `SLIPPAGE_PCT` name exists in
    # trader.risk.config; assert value-for-value equality against the
    # upstream source of truth instead.
    assert config.MAX_SPREAD_PCT == {
        "stock": 0.05,
        "crypto_major": 0.10,
        "memecoin": 4.0,
    }
    assert config.MAX_SPREAD_PCT == backtest_config.SLIPPAGE_PCT


def test_correlation_window_days():
    assert config.CORRELATION_WINDOW_DAYS == 60


def test_correlation_min_overlap():
    assert config.CORRELATION_MIN_OVERLAP == 30


def test_correlation_threshold():
    assert config.CORRELATION_THRESHOLD == 0.8


def test_sizer_top_n():
    # Sanctioned owner recalibration 2026-08-10 (3 -> 20 concurrent
    # positions for the high-throughput paper-testing phase, zero closed
    # trades on the books at the time). This assertion is deliberately
    # literal so the change stays a two-place edit, never a drive-by.
    assert config.SIZER_TOP_N == 20


def test_sizer_volatility_window_days():
    assert config.SIZER_VOLATILITY_WINDOW_DAYS == 20


def test_sizer_single_position_cap():
    assert config.SIZER_SINGLE_POSITION_CAP == 0.50


def test_sizer_memecoin_cap():
    assert config.SIZER_MEMECOIN_CAP == 0.10


def test_sizer_cash_reserve():
    assert config.SIZER_CASH_RESERVE == 0.10


def test_breaker_daily_loss_pct():
    assert config.BREAKER_DAILY_LOSS_PCT == -0.03


def test_breaker_drawdown_pct():
    assert config.BREAKER_DRAWDOWN_PCT == -0.10


def test_breaker_consecutive_losses():
    assert config.BREAKER_CONSECUTIVE_LOSSES == 6


def test_all_frontmatter_exports_are_importable():
    # Mirrors this plan's frontmatter `artifacts.exports` list exactly --
    # every constant listed there must be importable from trader.risk.config.
    exports = [
        "MIN_DOLLAR_VOLUME_STOCK",
        "MIN_QUOTE_VOLUME_CRYPTO_MAJOR",
        "MIN_QUOTE_VOLUME_MEMECOIN",
        "MIN_LISTING_AGE_DAYS",
        "MAX_SPREAD_PCT",
        "CORRELATION_WINDOW_DAYS",
        "CORRELATION_THRESHOLD",
        "CORRELATION_MIN_OVERLAP",
        "SIZER_TOP_N",
        "SIZER_VOLATILITY_WINDOW_DAYS",
        "SIZER_SINGLE_POSITION_CAP",
        "SIZER_MEMECOIN_CAP",
        "SIZER_CASH_RESERVE",
        "BREAKER_DAILY_LOSS_PCT",
        "BREAKER_DRAWDOWN_PCT",
        "BREAKER_CONSECUTIVE_LOSSES",
    ]
    for name in exports:
        assert hasattr(config, name), f"trader.risk.config is missing {name}"
