"""Phase 6's pre-registered graduation checklist (06-CONTEXT.md D-01,
phase doc verbatim), frozen behind trader/graduation/freeze_gate.py --
standing rule 1: never edit graduation criteria while looking at results.

This module holds only config constants -- no engine logic, no I/O.

The five checks (a strategy must pass ALL of them, on >=
MIN_TRADES_FOR_GRADUATION closed paper trades):

1. Profit factor > PF_GRADUATION_FLOOR after fees/slippage.
2. Max drawdown shallower than MAX_DD_GRADUATION (daily equity curve).
3. Profitable in >= MIN_PROFITABLE_CONDITIONS market conditions
   (frozen regimes_v2 windows by exit date; SPY-vs-50-day-mean fallback for
   dates outside every window -- pre-registered in 06-CONTEXT.md D-03,
   never a judgment call at review time).
4. No single trade contributing more than MAX_SINGLE_TRADE_PROFIT_SHARE of
   total profit.
5. Total P&L still positive with every fill assumed ADVERSE_FILL_PCT worse
   (entry raised, exit lowered; fees unchanged -- D-04).
"""

MIN_TRADES_FOR_GRADUATION = 50

PF_GRADUATION_FLOOR = 1.3

# Expressed as the max_drawdown metric's own negative-decimal convention:
# a curve must never lose more than 15% peak-to-trough.
MAX_DD_GRADUATION = -0.15

MIN_PROFITABLE_CONDITIONS = 2

MAX_SINGLE_TRADE_PROFIT_SHARE = 0.40

ADVERSE_FILL_PCT = 0.01
