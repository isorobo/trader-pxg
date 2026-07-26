"""Point-in-time bar iterator (BACK-01, D-01/D-02/D-03).

PointInTimeIterator wraps pre-loaded per-symbol OHLCV DataFrames -- Phase 1's
trader.data.api.get_daily_bars is the harness's only intended data source
(D-01), but this module never calls it directly. Construction takes plain
DataFrames so the class itself has zero network/DB coupling; whichever
runner assembles bars_by_symbol owns the one-time get_daily_bars call per
symbol (02-RESEARCH.md's architecture map).

Lookahead is impossible by construction, not by discipline (D-02):
history(symbol) always returns a slice bounded by the last date passed to
advance_to, never a boolean-mask re-filter of the full frame (the
02-RESEARCH.md Pattern 1 two-pointer design, chosen over re-filtering the
whole index against the current date on every call, which would incur
Pitfall 1's O(n^2) cost on AAPL's 11,000+ cached rows). advance_to only
ever moves pointers forward,
matching D-03's daily UTC clock -- calling it with an earlier date than
already reached raises ValueError rather than silently rewinding.

bar_on(symbol, date) is a raw, pointer-unbound exact-date lookup, not a
point-in-time-restricted query: fee/fill logic (plan 02-04) needs to read a
signal's *next* bar's open to fill an entry (D-04), which is necessarily a
date beyond the day the signal fired on. history() is the only method that
enforces the point-in-time boundary; bar_on() is a plain calendar lookup
used by code that already knows which date it is allowed to look at.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


class _SymbolCursor:
    """Per-symbol two-pointer cursor over one symbol's sorted OHLCV bars.

    Stores the symbol's sorted dates array and OHLCV numpy array once at
    construction plus an integer pointer -- the count of bars currently
    visible. advance_to only ever walks the pointer forward from its
    current position; it never re-scans from zero (Pitfall 1).
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self.dates: np.ndarray = df.index.values
        self.ohlcv: np.ndarray = df[_OHLCV_COLUMNS].to_numpy()
        self.pointer = 0
        # Exact-date -> row index, built once, for bar_on's O(1) lookup.
        self._date_to_row = {date: i for i, date in enumerate(self.dates)}

    def advance_to(self, current_date: pd.Timestamp) -> None:
        target = current_date.to_datetime64()
        while self.pointer < len(self.dates) and self.dates[self.pointer] <= target:
            self.pointer += 1

    def history(self) -> np.ndarray:
        # A numpy slice view bounded at the CURRENT pointer value -- later
        # pointer advances do not retroactively extend an already-returned
        # slice (T-02-03's leaked-full-length-view threat is structurally
        # unreachable, not just untested).
        return self.ohlcv[: self.pointer]

    def bar_on(self, date: pd.Timestamp) -> dict | None:
        row = self._date_to_row.get(date.to_datetime64())
        if row is None:
            return None
        open_, high, low, close, volume = self.ohlcv[row]
        return {
            "open": float(open_),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": float(volume),
        }


class PointInTimeIterator:
    """Point-in-time access to a pre-loaded multi-symbol bar universe (D-02).

    Strategy code driven by this iterator can never observe a bar dated
    after the current simulation date -- history() returns a slice
    physically bounded by the pointer, not a filtered view of the whole
    series.
    """

    def __init__(self, bars_by_symbol: dict[str, pd.DataFrame]) -> None:
        self._cursors = {
            symbol: _SymbolCursor(df) for symbol, df in bars_by_symbol.items()
        }
        all_dates = sorted(
            {date for cursor in self._cursors.values() for date in cursor.dates}
        )
        self.calendar: list[pd.Timestamp] = [pd.Timestamp(date) for date in all_dates]
        self._current_date: pd.Timestamp | None = None

    def advance_to(self, date) -> None:
        """Move every symbol's pointer forward to include bars <= date.

        A no-op if called again with the same date. Raises ValueError if
        date is earlier than the date already reached -- the simulation
        clock never runs backward (D-03).
        """
        date = pd.Timestamp(date)
        if self._current_date is not None and date < self._current_date:
            raise ValueError(
                f"advance_to({date}) moves the simulation clock backward from "
                f"the current date {self._current_date} -- pointers never move "
                "backwards (D-03)."
            )
        for cursor in self._cursors.values():
            cursor.advance_to(date)
        self._current_date = date

    def history(self, symbol: str) -> np.ndarray:
        """Bars for symbol with index <= the date last passed to advance_to.

        Empty (length 0) if advance_to has never been called.
        """
        return self._cursors[symbol].history()

    def bar_on(self, symbol: str, date) -> dict | None:
        """The exact-date bar for symbol, or None if it has no bar on date.

        Unbound by the current simulation pointer -- see the module
        docstring for why fill logic needs this.
        """
        return self._cursors[symbol].bar_on(pd.Timestamp(date))

    @property
    def symbols(self) -> list[str]:
        """The universe's symbol names, in construction order.

        Added for plan 02-07's shared pick_entries(iterator, date,
        open_positions, rng) strategy contract: strategies need to discover
        the tradable universe from the iterator itself so runner.py (plan
        02-08) can call any strategy uniformly without an extra
        universe argument.
        """
        return list(self._cursors.keys())
