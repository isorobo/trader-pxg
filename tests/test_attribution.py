"""Wave 5 tests: ATTR-01 attribution dashboards (D-01/D-02) + inline SVG."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from trader.paper import config as paper_config
from trader.paper import config_store
from trader.tournament import dashboard, svg_chart

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)

_SEEDS = sorted(cfg.profile_name for cfg in paper_config.LIVE_STRATEGY_CONFIGS)


# ---------------------------------------------------------------------------
# svg_chart
# ---------------------------------------------------------------------------


def test_svg_fewer_than_two_points_is_empty_svg():
    assert svg_chart.equity_curve_svg([]) == "<svg></svg>"
    assert svg_chart.equity_curve_svg([100.0]) == "<svg></svg>"


def test_svg_polyline_has_one_point_per_value_within_viewbox():
    values = [100.0, 105.0, 95.0, 110.0, 108.0]
    svg = svg_chart.equity_curve_svg(values, width=400, height=100)

    points = re.search(r'points="([^"]+)"', svg).group(1).split()
    assert len(points) == len(values)
    for pair in points:
        x, y = (float(p) for p in pair.split(","))
        assert 0.0 <= x <= 400.0
        assert 0.0 <= y <= 100.0
    # min value maps to the bottom edge, max to the top edge.
    ys = [float(p.split(",")[1]) for p in points]
    assert ys[2] == 100.0  # 95.0 is the minimum
    assert ys[3] == 0.0  # 110.0 is the maximum


def test_svg_flat_series_never_divides_by_zero():
    svg = svg_chart.equity_curve_svg([100.0, 100.0, 100.0])
    assert "polyline" in svg
    assert "nan" not in svg.lower()


# ---------------------------------------------------------------------------
# kill-condition proximity gauges (guardian's math, re-run for display)
# ---------------------------------------------------------------------------


def _registry_row(conn, name: str) -> dict:
    return next(
        r for r in config_store.get_registry_rows(conn) if r["profile_name"] == name
    )


def test_proximity_all_safe_on_winning_window(paper_conn, paper_trade_factory):
    name = _SEEDS[0]
    paper_trade_factory(paper_conn, name, [10.0] * 30)

    prox = dashboard.compute_kill_proximity(paper_conn, _registry_row(paper_conn, name))

    assert prox["window_full"] is True
    assert prox["profit_factor"]["status"] == "SAFE"
    assert prox["consecutive_losses"]["status"] == "SAFE"
    assert prox["consecutive_losses"]["current"] == 0


def test_proximity_counts_leading_consecutive_losses(paper_conn, paper_trade_factory):
    name = _SEEDS[0]
    # 24 wins then 6 losses -- the 6 most-recent trades are losses; the
    # kill trigger is 8, and 6 >= 8 * 0.75 -> NEAR.
    paper_trade_factory(paper_conn, name, [10.0] * 24 + [-5.0] * 6)

    prox = dashboard.compute_kill_proximity(paper_conn, _registry_row(paper_conn, name))

    gauge = prox["consecutive_losses"]
    assert gauge["current"] == 6
    assert gauge["trigger"] == 8
    assert gauge["status"] == "NEAR"


def test_proximity_tripped_pf_floor(paper_conn, paper_trade_factory):
    name = _SEEDS[0]
    paper_trade_factory(paper_conn, name, [1.0] * 15 + [-2.0] * 15)  # PF 0.5 < 0.9

    prox = dashboard.compute_kill_proximity(paper_conn, _registry_row(paper_conn, name))

    assert prox["profit_factor"]["status"] == "TRIPPED"


def test_proximity_never_tripped_before_window_full(paper_conn, paper_trade_factory):
    """Mirrors guardian's own <30-trades rule: an awful partial window
    shows values but can never claim TRIPPED."""
    name = _SEEDS[0]
    paper_trade_factory(paper_conn, name, [-50.0] * 10)

    prox = dashboard.compute_kill_proximity(paper_conn, _registry_row(paper_conn, name))

    assert prox["window_full"] is False
    for key in ("profit_factor", "max_drawdown", "consecutive_losses"):
        assert prox[key]["status"] != "TRIPPED"


# ---------------------------------------------------------------------------
# write_dashboard (D-01: static markdown + self-contained HTML)
# ---------------------------------------------------------------------------


def test_write_dashboard_produces_both_files_with_all_strategies(
    paper_conn, paper_trade_factory, tmp_path
):
    paper_trade_factory(paper_conn, _SEEDS[0], [10.0, -5.0, 20.0, 7.0], symbol="AAPL")
    paper_trade_factory(paper_conn, _SEEDS[0], [3.0, -1.0], symbol="MSFT", start="2026-02-01")

    paths = dashboard.write_dashboard(paper_conn, base_dir=str(tmp_path), as_of=NOW)

    md = Path(paths["markdown"]).read_text(encoding="utf-8")
    html = Path(paths["html"]).read_text(encoding="utf-8")
    for name in _SEEDS:
        assert name in md
        assert name in html
    assert "AAPL" in md and "MSFT" in md
    assert "Kill-condition proximity" in md
    assert "<polyline" in html  # the traded strategy has a real curve


def test_html_is_fully_self_contained(paper_conn, paper_trade_factory, tmp_path):
    """D-01: no server, no JS, no external asset of any kind."""
    paper_trade_factory(paper_conn, _SEEDS[0], [10.0] * 5)

    paths = dashboard.write_dashboard(paper_conn, base_dir=str(tmp_path), as_of=NOW)
    html = Path(paths["html"]).read_text(encoding="utf-8")

    assert "<script" not in html
    # The SVG xmlns is a namespace IDENTIFIER (never fetched) -- the only
    # sanctioned URL-shaped string in the file.
    stripped = html.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "http://" not in stripped and "https://" not in stripped
    assert "src=" not in stripped and "href=" not in stripped


def test_dashboard_module_is_read_only_on_the_db():
    """D-02: attribution reads ONLY the ledgers -- no parallel bookkeeping,
    no writes. Asserted structurally against the module source."""
    source = Path(dashboard.__file__).read_text(encoding="utf-8")
    assert "INSERT INTO" not in source
    assert "UPDATE " not in source
    assert "DELETE FROM" not in source


def test_retired_strategies_stay_visible_for_audit(paper_conn, tmp_path):
    victim = _SEEDS[0]
    paper_conn.execute(
        "UPDATE strategy_registry SET state = 'retired' WHERE profile_name = ?",
        (victim,),
    )
    paper_conn.commit()

    paths = dashboard.write_dashboard(paper_conn, base_dir=str(tmp_path), as_of=NOW)
    md = Path(paths["markdown"]).read_text(encoding="utf-8")

    assert f"| {victim} | retired |" in md
