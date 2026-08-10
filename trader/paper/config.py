"""Frozen Phase 5 constants: IBKR connection settings, cadences, and the
five live D-01 strategy configs (PAPER-03).

This module holds only config constants -- no engine logic, no I/O (mirrors
trader/risk/config.py's docstring convention).

LIVE_STRATEGY_CONFIGS is a one-time transcription of the five survivor
configs verified directly from reports/backtests/oos_results_v2.json and
.planning/phases/03-strategy-lab/KILL-CONDITIONS.md this session (standing
rule 1: never edit graduation/kill criteria while looking at results). Every
number below is copied verbatim -- none is invented, approximated, or
re-derived from a live/paper result (T-05-09).
"""

import os
from dataclasses import dataclass

from trader.backtest.config import EXIT_PROFILE

# --- IBKR connection (standing rule 6) -------------------------------------
IBKR_HOST_ENV = "IBKR_HOST"
IBKR_HOST_DEFAULT = "127.0.0.1"

# The ONLY port Phase 5 code is allowed to connect to (standing rule 6 --
# never 4001, IBKR's live-trading port). A hardcoded literal, never derived
# or referenced as a variable elsewhere in this file.
IBKR_PAPER_PORT = 4002

IBKR_CLIENT_ID_ENV = "IBKR_CLIENT_ID"
IBKR_CLIENT_ID_DEFAULT = 5

# Distinct API client ids per scheduled process (2026-08-03): the Gateway
# rejects two simultaneous connections sharing one id, and reconcile's
# minutely connect can overlap guardian's five-minutely one whenever the
# Gateway's startup sync runs slow (post-maintenance). Reconcile keeps the
# env-overridable default (5); the other processes get fixed distinct ids.
IBKR_CLIENT_ID_GUARDIAN = 6
IBKR_CLIENT_ID_ENTRY = 7

# --- Notification / read-only market data credentials ----------------------
TELEGRAM_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "TELEGRAM_CHAT_ID"

# D-04: read-only, optional, informational-only.
KRAKEN_API_KEY_ENV = "KRAKEN_API_KEY"
KRAKEN_API_SECRET_ENV = "KRAKEN_API_SECRET"

# --- Cadences ---------------------------------------------------------------
GUARDIAN_CADENCE_MINUTES = 5
RECONCILE_CADENCE_SECONDS = 60

# Claude's discretion (05-01-PLAN.md): the fake paper equity denominator the
# sizer's weight fractions are computed against, matching
# trader/backtest/config.py's DEFAULT_NOTIONAL/starting_equity convention
# for consistency. Assumption the owner may override once IBKR Gateway shows
# the real paper account's actual equity at the 05-08 ops checkpoint.
PAPER_ACCOUNT_EQUITY = 100_000.0

# Owner directive 2026-08-11: hard nightly budget for NEW entries, applied
# across the whole book per entry-pipeline run. Sizing weights still come
# from PAPER_ACCOUNT_EQUITY (whole-share US stocks are unbuyable against a
# $600 equity base); this cap bounds the DOLLARS actually deployed per
# night. Positions already open keep running under their locked exits.
PAPER_NIGHTLY_BUDGET = 600.0


def ibkr_host() -> str:
    """Read IBKR_HOST_ENV at call time, defaulting to IBKR_HOST_DEFAULT."""
    return os.environ.get(IBKR_HOST_ENV, IBKR_HOST_DEFAULT)


def ibkr_client_id() -> int:
    """Read IBKR_CLIENT_ID_ENV at call time, defaulting to IBKR_CLIENT_ID_DEFAULT."""
    return int(os.environ.get(IBKR_CLIENT_ID_ENV, IBKR_CLIENT_ID_DEFAULT))


@dataclass(frozen=True)
class LiveStrategyConfig:
    """One live D-01 strategy config: a locked EXIT_PROFILE plus its
    pre-registered kill triggers (transcribed verbatim from
    KILL-CONDITIONS.md, never recomputed -- T-05-09)."""

    strategy_id: str
    profile_name: str
    exit_profile: EXIT_PROFILE
    pf_floor: float
    max_dd_kill: float
    consecutive_loss_kill: int
    # Phase 7 (D-04/D-08): the registry row's tournament state --
    # 'probation' rows are sized at PROBATION_SIZE_MULTIPLIER by the entry
    # pipeline. Defaults to 'full' so this module's own literal tuple below
    # (the pre-Phase-7 transcription, kept as the seed reference) is
    # unchanged. The live loader is trader/paper/config_store.py.
    state: str = "full"
    # Multi-signal live book (owner-approved 2026-07-30): which frozen
    # entry variant this row trades, resolved by trader/paper/signals.py.
    # Defaults to 'loose' -- the variant Phase 5 hardcoded for the five
    # incumbent momentum rows from the start.
    entry_variant: str = "loose"


# The five real D-01 survivor configs (KILL-CONDITIONS.md / D-01
# /reports/backtests/oos_results_v2.json, verified verbatim -- all five
# share strategy="momentum_stock", entry_variant="loose", regime="choppy_v2",
# bucket="stock", tp_pct=0.2, trailing_pct=None, scale_out=(), eod_flat=False).
LIVE_STRATEGY_CONFIGS: tuple[LiveStrategyConfig, ...] = (
    LiveStrategyConfig(
        strategy_id="momentum_stock",
        profile_name="momentum_stock_stock_choppy_v2_loose_tune_stop-0.3_tp0.2_trailNone_holdNone",
        exit_profile=EXIT_PROFILE(
            stop_pct=-0.3,
            tp_pct=0.2,
            scale_out=(),
            trailing_pct=None,
            max_hold_days=None,
            eod_flat=False,
        ),
        pf_floor=0.9,
        max_dd_kill=-0.0096,
        consecutive_loss_kill=8,
    ),
    LiveStrategyConfig(
        strategy_id="momentum_stock",
        profile_name="momentum_stock_stock_choppy_v2_loose_tune_stop-0.25_tp0.2_trailNone_holdNone",
        exit_profile=EXIT_PROFILE(
            stop_pct=-0.25,
            tp_pct=0.2,
            scale_out=(),
            trailing_pct=None,
            max_hold_days=None,
            eod_flat=False,
        ),
        pf_floor=0.9,
        max_dd_kill=-0.0377,
        consecutive_loss_kill=8,
    ),
    LiveStrategyConfig(
        strategy_id="momentum_stock",
        profile_name="momentum_stock_stock_choppy_v2_loose_tune_stop-0.3_tp0.2_trailNone_hold30",
        exit_profile=EXIT_PROFILE(
            stop_pct=-0.3,
            tp_pct=0.2,
            scale_out=(),
            trailing_pct=None,
            max_hold_days=30,
            eod_flat=False,
        ),
        pf_floor=0.9,
        max_dd_kill=-0.0706,
        consecutive_loss_kill=8,
    ),
    LiveStrategyConfig(
        strategy_id="momentum_stock",
        profile_name="momentum_stock_stock_choppy_v2_loose_tune_stop-0.25_tp0.2_trailNone_hold30",
        exit_profile=EXIT_PROFILE(
            stop_pct=-0.25,
            tp_pct=0.2,
            scale_out=(),
            trailing_pct=None,
            max_hold_days=30,
            eod_flat=False,
        ),
        pf_floor=0.9,
        max_dd_kill=-0.0714,
        consecutive_loss_kill=8,
    ),
    LiveStrategyConfig(
        strategy_id="momentum_stock",
        profile_name="momentum_stock_stock_choppy_v2_loose_tune_stop-0.2_tp0.2_trailNone_hold30",
        exit_profile=EXIT_PROFILE(
            stop_pct=-0.2,
            tp_pct=0.2,
            scale_out=(),
            trailing_pct=None,
            max_hold_days=30,
            eod_flat=False,
        ),
        pf_floor=0.9,
        max_dd_kill=-0.0680,
        consecutive_loss_kill=8,
    ),
)

# O(1) lookup by profile_name.
LIVE_STRATEGY_CONFIGS_BY_PROFILE_NAME: dict[str, LiveStrategyConfig] = {
    cfg.profile_name: cfg for cfg in LIVE_STRATEGY_CONFIGS
}
