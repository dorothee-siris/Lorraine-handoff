"""
Read the app's DECLARED FWCI colourscale straight out of its own source, and
compute the colour a given FWCI value should render as.

Why parse the source instead of hand-copying the three stops: a hand-copied
constant silently drifts from the app the day someone tweaks the palette, and the
test would keep "passing" against a scale the app no longer uses. Regexing the
exact block out of the Thematic Overview page means a real change trips this
test, not just a future manual edit -- the failure mode `docs/data_contract.yaml`
exists to avoid elsewhere (drift no one re-checks) is exactly what this guards
against here.

Pass-5 rename (P1 map): Thematic Overview moved from slot 3 to slot 4
("4_..._Portefeuille_thematique.py") -- located by number glob, not a hardcoded
filename, so it survives future emoji/spelling churn too.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[2]
PAGES_DIR = ROOT / "Streamlit" / "pages"


def _find_page3() -> Path:
    candidates = sorted(PAGES_DIR.glob("4_*.py"))
    if not candidates:
        raise AssertionError("Thematic Overview page (slot 4) not found under Streamlit/pages/")
    return candidates[0]


PAGE3 = _find_page3()


def read_declared_scale() -> Tuple[List[Tuple[float, str]], Tuple[float, float]]:
    """
    Parse the declared FWCI colour scale feeding the treemap's `fwci_median` colouring.
    Since pass 7b the stops live in `Streamlit/lib/helpers.py::FWCI_DIVERGING_SCALE`
    (zero hex literal in any page file, BUILD_PLAN 7b B6) and the page keeps only
    `range_color=[lo, hi]`. Both are read as SOURCE TEXT by regex -- never imported --
    so the root `lib` package stays bound in tests/test_app_numbers.py (F-SYSMOD).
    Returns (stops, (lo, hi)).
    """
    helpers_src = (PAGE3.parent.parent / "lib" / "helpers.py").read_text(encoding="utf-8")
    scale_m = re.search(r'FWCI_DIVERGING_SCALE\s*=\s*\[(.*?)\]\s*(?:#[^\n]*)?\n', helpers_src, flags=re.S)
    if not scale_m:
        raise AssertionError(
            "could not find FWCI_DIVERGING_SCALE in Streamlit/lib/helpers.py -- has the FWCI "
            "treemap colouring been refactored?"
        )
    stops = [
        (float(pos), color)
        for pos, color in re.findall(r'\[\s*([\d.]+)\s*,\s*"(#[0-9A-Fa-f]{6})"\s*\]', scale_m.group(1))
    ]
    src = PAGE3.read_text(encoding="utf-8")
    range_m = re.search(r'color_continuous_scale\s*=\s*FWCI_DIVERGING_SCALE\s*,[^\n]*\n\s*range_color\s*=\s*\[([^\]]+)\]', src)
    if not range_m:
        raise AssertionError(
            "could not find the color_continuous_scale=FWCI_DIVERGING_SCALE / range_color block "
            "in pages/4_*.py -- has the FWCI treemap colouring been refactored?"
        )
    lo, hi = (float(x.strip()) for x in range_m.group(1).split(","))
    if len(stops) < 2:
        raise AssertionError(f"parsed fewer than 2 colour stops from lib/helpers.py: {stops}")
    return stops, (lo, hi)


def _hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def expected_rgb(value: float, stops: List[Tuple[float, str]], value_range: Tuple[float, float]) -> Tuple[int, int, int]:
    """
    Linear-RGB interpolation of `value` against the declared stops, exactly as
    Plotly.js renders a continuous marker colourscale (verified empirically: the
    app's real rendered SVG fill matches this formula to within +/-1 per channel,
    8-bit rounding -- see tests/ui/build_golden.py's provenance notes).
    """
    lo, hi = value_range
    t = 0.0 if hi <= lo else (value - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if p0 <= t <= p1:
            frac = 0.0 if p1 <= p0 else (t - p0) / (p1 - p0)
            r0, g0, b0 = _hex_to_rgb(c0)
            r1, g1, b1 = _hex_to_rgb(c1)
            return (
                round(r0 + (r1 - r0) * frac),
                round(g0 + (g1 - g0) * frac),
                round(b0 + (b1 - b0) * frac),
            )
    # t outside every segment only if stops don't span [0,1] -- clamp to nearest end
    return _hex_to_rgb(stops[0][1] if t <= stops[0][0] else stops[-1][1])


def parse_rgb(fill: str) -> Tuple[int, int, int] | None:
    """'rgb(236, 135, 115)' -> (236, 135, 115); None for anything else (e.g. the
    dark-grey null/no-colour default Plotly uses for a NaN marker value)."""
    m = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", fill or "")
    return tuple(int(x) for x in m.groups()) if m else None  # type: ignore[return-value]


def rgb_close(a: Tuple[int, int, int], b: Tuple[int, int, int], tol: int = 2) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))
