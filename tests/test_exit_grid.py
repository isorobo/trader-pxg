"""Grid-size and cell-shape tests for the D-06 exit-parameter grid (STRAT-03).

Asserts the frozen grid yields exactly 270 cells for the stock and
crypto-major/legacy-memecoin buckets, 360 (additive) for new-memecoin per
the orchestrator's resolution of 03-RESEARCH.md Open Question 2, and that
every yielded cell is a locked config.EXIT_PROFILE (scale_out=(),
eod_flat=False) matching this plan's sweep-grid contract.
"""

from trader.backtest import config, exit_grid, universe


def test_stock_bucket_grid_has_270_cells():
    assert len(list(exit_grid.exit_profile_grid(universe.BUCKET_STOCK))) == 270


def test_crypto_major_legacy_meme_bucket_grid_has_270_cells():
    cells = list(
        exit_grid.exit_profile_grid(universe.BUCKET_CRYPTO_MAJOR_LEGACY_MEME)
    )
    assert len(cells) == 270


def test_new_memecoin_bucket_grid_has_360_cells():
    assert len(list(exit_grid.exit_profile_grid(universe.BUCKET_NEW_MEMECOIN))) == 360


def test_every_cell_is_exit_profile_with_locked_scale_out_and_eod_flat():
    for bucket in (
        universe.BUCKET_STOCK,
        universe.BUCKET_CRYPTO_MAJOR_LEGACY_MEME,
        universe.BUCKET_NEW_MEMECOIN,
    ):
        for profile in exit_grid.exit_profile_grid(bucket):
            assert isinstance(profile, config.EXIT_PROFILE)
            assert profile.scale_out == ()
            assert profile.eod_flat is False


def test_new_memecoin_grid_is_additive_superset_of_base_time_stops():
    base_time_stops = set(exit_grid.TIME_STOPS)
    memecoin_time_stops = {
        p.max_hold_days
        for p in exit_grid.exit_profile_grid(universe.BUCKET_NEW_MEMECOIN)
    }
    assert base_time_stops <= memecoin_time_stops
    assert exit_grid.MEMECOIN_SHORT_HOLD_DAYS in memecoin_time_stops


def test_non_memecoin_buckets_never_see_memecoin_short_hold_days():
    for bucket in (universe.BUCKET_STOCK, universe.BUCKET_CRYPTO_MAJOR_LEGACY_MEME):
        max_hold_days = {p.max_hold_days for p in exit_grid.exit_profile_grid(bucket)}
        assert max_hold_days == set(exit_grid.TIME_STOPS)
