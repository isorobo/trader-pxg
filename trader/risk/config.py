"""Frozen threshold constants for Phase 4's risk gate, sizer, and circuit
breakers (RISK-01/02/03).

Every numeric default below is a pre-registered default per
04-RESEARCH.md -- Phases 5-6 may recalibrate them only via a pre-registered
change, never mid-trade (04-CONTEXT.md's standing rule: "All numeric
thresholds below are pre-registered defaults -- Phases 5-6 may recalibrate
them only via pre-registered change, never mid-trade"). Downstream plans
(04-02 gate, 04-03 sizer, 04-04 breakers) import these named constants
directly -- no re-derived thresholds, no inline magic numbers.

Candidate-dict contract seam: every candidate dict flowing into this
phase's gate/sizer requires a ``score: float`` field. Phase 4 owns and
defines this field, source-agnostic per D-06 (the gate/sizer consume scores
from any strategy -- Phase 3 v1/v2 survivors or future Phase 7 entrants --
with no coupling to specific strategies). Who computes that score in the
live pipeline (Phase 5's scanner -> gate -> ranker -> sizer order) is left
as Phase 5's decision (04-RESEARCH.md Q1/Open Question 1, Pitfall 4); Phase
4's own tests populate ``score`` directly in fixtures.
"""

from trader.backtest.config import SLIPPAGE_PCT

# --- Liquidity floors (04-RESEARCH.md Q1) ---------------------------------
# Trailing window lengths used to compute each asset class's liquidity
# floor (median dollar/quote volume over the window, not mean).
LIQUIDITY_WINDOW_STOCK_DAYS = 20
LIQUIDITY_WINDOW_CRYPTO_DAYS = 7

# Trailing-20-day median dollar volume floor for stocks.
MIN_DOLLAR_VOLUME_STOCK = 1_000_000.0
# Trailing-7-day median quote volume floor for major crypto (BTC/ETH-class).
MIN_QUOTE_VOLUME_CRYPTO_MAJOR = 5_000_000.0
# Trailing-7-day median quote volume floor for memecoins.
MIN_QUOTE_VOLUME_MEMECOIN = 250_000.0

# --- Listing age (04-RESEARCH.md Q1 / D-02) -------------------------------
MIN_LISTING_AGE_DAYS = 30

# --- Maximum spread (04-RESEARCH.md Open Question 3) ----------------------
# Static per-asset-class spread-ceiling proxy, reused directly from
# trader.backtest.config.SLIPPAGE_PCT (not re-typed as new literals) --
# spread and slippage are related but not identical concepts; this research
# recommends reuse for a single source of truth and lower maintenance
# surface (04-RESEARCH.md Open Question 3).
MAX_SPREAD_PCT = dict(SLIPPAGE_PCT)

# --- Correlation check (04-RESEARCH.md Q2 / D-02) -------------------------
CORRELATION_WINDOW_DAYS = 60
CORRELATION_MIN_OVERLAP = 30
CORRELATION_THRESHOLD = 0.8

# --- Position sizer (04-RESEARCH.md Q3 / D-03) ----------------------------
# SIZER_TOP_N: pre-registered recalibration 2026-08-08 (the docstring's
# sanctioned path -- owner-directed, zero closed trades on the books, and
# it changes only how FUTURE entries are sized, never an open position's
# locked exits): 3 -> 20 concurrent positions for the high-throughput
# paper-testing phase ("up to 20 at a time"). The 10% cash reserve, 50%
# single-position cap, and 10% memecoin aggregate cap all stay.
SIZER_TOP_N = 20
SIZER_VOLATILITY_WINDOW_DAYS = 20
SIZER_SINGLE_POSITION_CAP = 0.50
SIZER_MEMECOIN_CAP = 0.10
SIZER_CASH_RESERVE = 0.10

# --- Circuit breakers (04-RESEARCH.md Q4 / D-04) --------------------------
BREAKER_DAILY_LOSS_PCT = -0.03
BREAKER_DRAWDOWN_PCT = -0.10
BREAKER_CONSECUTIVE_LOSSES = 6
