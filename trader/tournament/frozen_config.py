"""Phase 7's pre-registered tournament thresholds (D-06): frozen BEFORE the
first real tournament run, hash-gated by trader/tournament/freeze_gate.py
(standing rule 1 applied to the tournament itself -- never edit these while
looking at results).

This module holds only config constants -- no engine logic, no I/O
(trader/paper/config.py's docstring convention). It is a SEPARATE file from
freeze_gate.py because a file cannot contain its own hash.

Judging metric note (07-RESEARCH.md Q2): judging Sharpe reuses
trader/backtest/metrics.py's daily-marked equity curve convention -- trades
grouped by exit date, no-trade days 0-filled, sqrt(252) annualisation,
every strategy computed against the same PAPER_ACCOUNT_EQUITY base so ranks
are comparable. The 0-fill convention understates variance for low-frequency
strategies relative to high-frequency ones with the same profit factor;
profit factor is therefore the pre-registered tie-break (D-03), partially
compensating. This limitation is accepted and pre-registered here rather
than silently discovered later.

Demotion rule (D-04, pre-registered): a 'full' strategy is retired when, for
DEMOTION_SUSTAIN_EVALUATIONS consecutive weekly runs, it is BOTH (a) worst-
ranked among 'full' strategies by judging Sharpe (profit-factor tie-break)
AND (b) below SHARPE_DEMOTION_FLOOR. The compound condition means "worst of
a good bunch" is never demoted -- rank alone would empty a healthy roster
through pure attrition (07-RESEARCH.md Pitfall 5).
"""

# D-03: a strategy enters judging only after this many closed paper trades,
# and judging reads exactly this many most-recent trades -- one "recency
# window" concept shared with guardian.evaluate_kill_conditions's rolling-30
# kill window.
MIN_TRADES_FOR_JUDGING = 30
JUDGING_WINDOW_TRADES = 30

# D-04: probation -> full requires rolling-window judging Sharpe at or above
# this floor (net risk-adjusted-positive over the window).
SHARPE_PROMOTION_FLOOR = 0.0

# D-04: the absolute-floor half of the compound demotion condition,
# symmetric with the promotion floor.
SHARPE_DEMOTION_FLOOR = 0.0

# D-04: consecutive weekly evaluations the compound demotion condition must
# hold before a 'full' strategy is retired (one calendar month of weekly
# runs -- long enough to filter noise, short enough not to carry a failing
# strategy for a quarter).
DEMOTION_SUSTAIN_EVALUATIONS = 4

# D-04: probation-state sizing multiplier applied by the entry pipeline's
# new-order path (never the heal paths -- a healed fill's qty is history,
# not a fresh decision).
PROBATION_SIZE_MULTIPLIER = 0.25

# D-05: caps. Active = probation + full. Entrants beyond either cap stay
# 'candidate' (queued).
#
# SANCTIONED OWNER REVISION 2026-08-08 (the one deliberate adjustment,
# made with ZERO closed trades on the books -- a capacity decision, not a
# results-driven edit): the owner directed high-throughput parallel
# testing ("up to 20 at a time ... this is all testing at the moment but
# it is too slow"). Raised 6 -> 20 active and 2 -> 12 entrants/quarter.
# Hash re-locked in the same commit; these numbers are frozen again from
# here.
MAX_ACTIVE_STRATEGIES = 20
MAX_NEW_ENTRANTS_PER_QUARTER = 12
