"""Fee, slippage, and exit-profile config for the backtest harness (D-06
through D-09).

This module holds only config constants — no engine logic. Everything here
is a pure, in-process value; there is no external input at this layer (see
the plan's threat model: config.py's trust boundary risk is accidental
mutation, not injection).

EXIT_PROFILE mutation policy (standing rule 2, T-02-01): EXIT_PROFILE is a
``@dataclass(frozen=True)``. Frozen alone stops attribute reassignment
(``profile.stop_pct = -0.05`` raises ``dataclasses.FrozenInstanceError``) but
does NOT stop a caller mutating a *mutable* field in place (e.g. appending to
a list-typed ``scale_out``). This module closes that gap by requiring
``scale_out`` to be a ``tuple`` of ``(gain_pct, fraction)`` pairs and
REJECTING (raising ``TypeError`` in ``__post_init__``) any non-tuple input,
rather than silently coercing a list to a tuple. Rejection was chosen over
coercion so that a caller who passes a list gets an immediate, loud signal
that their input violates the immutability contract, instead of the module
quietly fixing it for them and masking the mistake at the call site.

Slippage rationale (D-08, ORCHESTRATOR REVISION locked for Phase 2): the
phase document's original three slippage ranges are large-cap stock 0.05%,
small-cap runner 1-3%, and memecoin 3-5%. SLIPPAGE_PCT maps stock -> 0.05
(large-cap baseline, unchanged) and memecoin -> 4.0 (the memecoin range's
midpoint, unchanged). crypto_major (BTC/ETH) is deliberately set to 0.10% --
a little worse than the large-cap stock baseline to reflect real spread/
depth on liquid crypto majors -- and must NOT reuse the small-cap-runner
1-3% tier's midpoint (2.0). SLIPPAGE_SMALL_CAP_RUNNER holds that small-cap-
runner midpoint (2.0) as its own named module-level constant, kept separate
from SLIPPAGE_PCT's per-asset_class map. It is a documented hook for Phase 3,
which will apply it per-trade to scanner-flagged small-cap stock runners
(a category the instruments table's asset_class CHECK constraint --
'stock', 'crypto_major', 'memecoin' -- does not itself distinguish). It is
NOT wired into any Phase 2 lookup and is not consumed by fills.py in this
phase.
"""

from dataclasses import dataclass

# Per-venue fee model (D-06, D-07). Fees are parameters, not hard-coded in
# engine logic -- fills.py (plan 02-04) looks these up by asset_class.
FEE_TABLE = {
    # IBKR US stocks: $0.005/share, $1.00 minimum per order.
    "stock": {"kind": "per_share", "rate": 0.005, "minimum": 1.00},
    # Kraken taker fee, assumed on every fill (pessimistic). Crypto fees
    # model as Kraken (the trading venue) even though bar data provenance
    # is Binance -- decoupling locked in Phase 1 (D-07).
    "crypto_major": {"kind": "taker_pct", "rate": 0.0026},
    # Same venue as crypto_major; memecoin's extra cost lives in slippage
    # (SLIPPAGE_PCT["memecoin"]), not a separate fee model (D-06).
    "memecoin": {"kind": "taker_pct", "rate": 0.0026},
}

# Percentage-unit slippage penalty per asset_class (D-08), applied on every
# fill, both sides. Values are percentages, e.g. 0.05 means 0.05%. See the
# module docstring's "Slippage rationale" section for why crypto_major does
# not take the small-cap-runner's 2.0 value.
SLIPPAGE_PCT = {
    "stock": 0.05,
    "crypto_major": 0.10,
    "memecoin": 4.0,
}

# Documented Phase 3 hook (unwired in Phase 2) -- see module docstring's
# "Slippage rationale" section. Percentage-unit, the phase document's
# small-cap-runner midpoint of its 1-3% range.
SLIPPAGE_SMALL_CAP_RUNNER = 2.0

# Fixed per-trade notional Phase 2 uses for all strategies (Claude's
# discretion per 02-01-PLAN.md) -- Phase 4 owns real position sizing.
DEFAULT_NOTIONAL = 10_000.0


@dataclass(frozen=True)
class EXIT_PROFILE:
    """An immutable exit profile attached to a position at entry (D-09).

    Standing rule 2 ("exit profiles lock at entry -- no mid-trade
    loosening") is enforced by the type, not by convention: the dataclass is
    frozen (attribute reassignment raises FrozenInstanceError) and
    __post_init__ rejects a non-tuple scale_out (a list would otherwise
    stay mutable in place even though the dataclass itself is frozen).
    """

    stop_pct: float | None
    tp_pct: float | None
    scale_out: tuple[tuple[float, float], ...]
    trailing_pct: float | None
    max_hold_days: int | None
    eod_flat: bool

    def __post_init__(self) -> None:
        if not isinstance(self.scale_out, tuple):
            raise TypeError(
                "EXIT_PROFILE.scale_out must be a tuple of (gain_pct, "
                f"fraction) pairs, not {type(self.scale_out).__name__} -- "
                "standing rule 2 requires scale_out to be immutable, and a "
                "list would stay mutable in place even inside a frozen "
                "dataclass."
            )


# D-14's sanity strategy's "hold one day" profile: no stop/TP/trailing, no
# scale-out, exit purely on the one-day time stop.
PROFILE_TIME_STOP_1D = EXIT_PROFILE(
    stop_pct=None,
    tp_pct=None,
    scale_out=(),
    trailing_pct=None,
    max_hold_days=1,
    eod_flat=False,
)

# D-15's end-to-end proof strategy (plan 02-10): a concrete profile with a
# stop, a take-profit, and a time-stop backstop. Values are Claude's
# discretion, chosen to be plausible defaults, not tuned.
PROFILE_MOMENTUM_PLACEHOLDER = EXIT_PROFILE(
    stop_pct=-0.10,
    tp_pct=0.20,
    scale_out=(),
    trailing_pct=None,
    max_hold_days=30,
    eod_flat=False,
)
