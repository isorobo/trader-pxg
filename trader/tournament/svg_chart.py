"""Hand-rolled inline-SVG equity curves (ATTR-01, 07-RESEARCH.md Q5).

No plotting library exists in this venv (verified: pip list) and D-01
requires a single self-contained HTML file with no server and no JS -- a
pure-stdlib polyline string satisfies both. Never add matplotlib for this.
"""

from __future__ import annotations


def equity_curve_svg(
    values: list[float],
    width: int = 400,
    height: int = 100,
    stroke: str = "#2c7a2c",
) -> str:
    """An inline SVG polyline of `values`, x scaled by index, y normalised
    to [0, height]. Fewer than two points has no line to draw -> an empty
    svg element, never a crash (metrics.py's own never-crash edge policy)."""
    if len(values) < 2:
        return "<svg></svg>"
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    step = width / (len(values) - 1)
    points = " ".join(
        f"{i * step:.1f},{height - ((v - lo) / span) * height:.1f}"
        for i, v in enumerate(values)
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="equity curve">'
        f'<polyline points="{points}" fill="none" stroke="{stroke}" '
        f'stroke-width="1.5"/></svg>'
    )
