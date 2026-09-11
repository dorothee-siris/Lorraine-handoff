# tests/test_page7b_p2.py
"""
Pass-7b pins -- page 2 Laboratoires (P2, W2/W3): the 4 non-SDG chart keys migrate onto
the pass-7 grammar (BUILD_PLAN.md B2/B3/B5/B6, §2 table, `docs/tooltip_spec.yaml`):
`lab_breakdown_bars` + `lab_field_share` (h-bars -> `charts.bars_with_gutter`, family
`champ`), `lab_breakdown_annual` (kept grouped-overlay form, per-trace hover), and
`lab_fwci_whiskers` (kept whisker form, red-dashed reference at FWCI = 1, height/margin
mirrored from its `bars_with_gutter` sibling for row-for-row alignment). The SDG chart
(`lab_sdg_bars`, ~L1420-1435) and the S1 cache lines are OUT OF SCOPE (done, untouched)
-- covered by `tests/test_page7_sdg.py` / `tests/test_page_pg.py`, not here.

Idiom: `tests/test_page7_col.py` (AppTest cannot introspect a rendered Plotly figure's
traces in this Streamlit build -- pure-function/source-regex pins instead). Vacuity
(P14): every assertion group is followed by an in-memory mutation that must make the
identical check fail.

    .venv-pinned\\Scripts\\python -m pytest tests\\test_page7b_p2.py -q
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
PAGES_DIR = STREAMLIT_DIR / "pages"

LAB_PAGE = "2_\U0001F3ED_Laboratoires.py"
LAB_SRC = (PAGES_DIR / LAB_PAGE).read_text(encoding="utf-8")

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
from conftest import restore_lib, swap_lib_to_streamlit  # centralized guard, see conftest.py

_saved_lib_modules: dict = {}


def setup_module(_module) -> None:
    global _saved_lib_modules
    _saved_lib_modules = swap_lib_to_streamlit()


def teardown_module(_module) -> None:
    restore_lib(_saved_lib_modules)


# ============================================================================
# (a) hover grammar -- every hovertemplate on the page is the bare constant
# ============================================================================

HOVERTEMPLATE_RE = re.compile(r"hovertemplate\s*=\s*([^\n,\)]+)")


def test_every_hovertemplate_on_the_page_is_the_bare_grammar_constant():
    matches = HOVERTEMPLATE_RE.findall(LAB_SRC)
    assert matches, "expected at least one hovertemplate= on the page"
    for m in matches:
        assert m.strip().rstrip(",") in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE"), m

    # vacuity: a literal format-spec hovertemplate must be caught by the SAME regex
    bad_src = 'fig.update_traces(hovertemplate="<b>%{customdata[0]:.1%}</b><extra></extra>")\n'
    bad = HOVERTEMPLATE_RE.findall(bad_src)
    assert bad and bad[0].strip() not in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE")


# ============================================================================
# (b) hover_lines well-formed for every (key, mode) on this page
# ============================================================================

BOLD_ONLY_RE = re.compile(r"^<b>[^<]+</b>$")
BOLD_COLON_RE = re.compile(r"^<b>[^<]+</b> : .+$")


def _assert_hover_wellformed(hover_str: str) -> None:
    lines = hover_str.split("<br>")
    assert lines[0].startswith("<b>"), f"line 1 must start with <b>: {lines[0]!r}"
    assert BOLD_ONLY_RE.match(lines[0]), f"line 1 must be bold-only (the entity): {lines[0]!r}"
    for line in lines[1:]:
        assert BOLD_ONLY_RE.match(line) or BOLD_COLON_RE.match(line), (
            f"line 2+ must be '<b>label</b> : value' or a bold-only flag line, got: {line!r}"
        )
    assert len(lines) <= 8


@pytest.mark.parametrize("chart_key,mode", [
    ("lab_breakdown_bars", "types_document"), ("lab_breakdown_bars", "domaines"),
    ("lab_breakdown_annual", "types_document"), ("lab_breakdown_annual", "domaines"),
    ("lab_field_share", "default"), ("lab_fwci_whiskers", "default"),
])
def test_hover_lines_wellformed_for_every_page2_chart_mode(chart_key, mode):
    from lib import copy_fr
    from lib import hover as hv
    labels = copy_fr.HOVER_LABELS[chart_key][mode]
    values = ["Entité X"] + [f"valeur {i}" for i in range(1, len(labels))]
    _assert_hover_wellformed(hv.hover_lines(list(zip(labels, values))))

    # a false `when` withholds every non-entity line -> still wellformed (entity only)
    withheld = ["Entité X"] + [None] * (len(labels) - 1)
    hover_withheld = hv.hover_lines(list(zip(labels, withheld)))
    _assert_hover_wellformed(hover_withheld)
    assert hover_withheld == "<b>Entité X</b>"

    # vacuity: a malformed line must be CAUGHT by _assert_hover_wellformed
    with pytest.raises(AssertionError):
        _assert_hover_wellformed("<b>Entité X</b><br>libellé sans mise en forme : 3")


# ============================================================================
# (c) reading lines -- exactly once per chart key; the 3 non-chart "Comment
#     lire" blocks (overview table, identity card, lab-tops lists) stay by
#     explicit page-brief dispensation (P7B_P2.md "Specifics") -- pinned here
#     at the count the brief actually calls for, not a blanket zero.
# ============================================================================

PAGE2_CHART_KEYS = [
    "lab_breakdown_bars", "lab_breakdown_annual", "lab_field_share", "lab_fwci_whiskers",
]


def test_reading_line_called_once_per_chart_key():
    for key in PAGE2_CHART_KEYS:
        assert LAB_SRC.count(f'reading_line("{key}"') == 1, key
    assert LAB_SRC.count("reading_line(") == len(PAGE2_CHART_KEYS)

    # vacuity: a page missing a chart's reading_line call must be caught by the same check
    stripped = LAB_SRC.replace('reading_line("lab_field_share")', "pass  # removed", 1)
    assert stripped.count('reading_line("lab_field_share"') == 0


def test_comment_lire_survives_only_on_the_3_non_chart_blocks():
    """The 2 chart-describing "Comment lire" blocks (breakdown pair, FWCI pair) are
    gone; the table/identity/lab-tops ones are NOT chart captions and stay (brief
    "Specifics" clause)."""
    assert LAB_SRC.count("Comment lire") == 3
    assert "Une barre par année. Le bouton bascule la décomposition" not in LAB_SRC
    assert "Une boîte par champ : la barre centrale est la médiane" not in LAB_SRC

    # vacuity: re-inserting a 4th "Comment lire" block must move the count off 3
    mutated = LAB_SRC + '\nst.caption("**Comment lire.** injected")\n'
    assert mutated.count("Comment lire") == 4


# ============================================================================
# (d) no percent tickformat / no hex literal INSIDE the 4 converted chart
#     functions (whole-page hex count stays > 0 -- identity-card/KPI-tile HTML
#     and the untouched SDG chart are out of this stream's fence, page 2 is a
#     real `test_page_hex_literals.py` EXEMPT_PAGES entry per the S-TT addendum)
# ============================================================================

CHART_FUNCS = (
    "plot_global_breakdown_h", "plot_annual_breakdown_grouped",
    "plot_field_share_pair_left", "plot_fwci_whiskers",
)
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}")


def _func_source(name: str) -> str:
    tree = ast.parse(LAB_SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            seg = ast.get_source_segment(LAB_SRC, node)
            assert seg is not None
            return seg
    raise AssertionError(f"function {name!r} not found in {LAB_PAGE}")


def test_no_percent_tickformat_or_hex_in_the_converted_chart_functions():
    combined = "\n".join(_func_source(fn) for fn in CHART_FUNCS)
    assert "tickformat=" not in combined
    offenders = HEX_RE.findall(combined)
    assert not offenders, offenders

    # vacuity: a hex literal spliced into the SAME combined text must be caught
    mutated = combined + '\ncolor="#123ABC"\n'
    assert HEX_RE.findall(mutated)


# ============================================================================
# (e)/(f) page-specific pins -- gutter phantom text == value_fmt(values);
#         exactly one red-dashed reference at FWCI = 1
# ============================================================================

def test_lab_breakdown_bars_gutter_text_matches_fmt_int():
    from lib import charts as C
    from lib import hover as hv
    df = pd.DataFrame({
        "label": ["Articles", "Chapitres"], "value": [123.0, 7.0],
        "isite": [10.0, 1.0], "hover": ["h1", "h2"],
    })
    fig = C.bars_with_gutter(
        df, family="champ", label_col="label", value_col="value",
        color=["#000000", "#111111"], hover_col="hover",
    )
    gutter_trace = fig.data[-1]
    assert list(gutter_trace.text) == [hv.fmt_int(123.0), hv.fmt_int(7.0)]

    # vacuity: a wrong expected value must NOT match
    assert list(gutter_trace.text) != [hv.fmt_int(999.0), hv.fmt_int(7.0)]


def test_lab_field_share_gutter_text_matches_fmt_pct_of_the_shares():
    """Page-specific pin (P7B_P2.md): the migration deliberately changes the gutter's
    MEANING from the raw count (pass-6) to the % share the bar itself draws (B2's
    'gutter = the value the bars show')."""
    from lib import charts as C
    from lib import hover as hv
    df = pd.DataFrame({
        "field_name": ["Physique", "Chimie"], "share_pct": [42.7, 3.1],
        "isite_share_pct": [5.0, 0.0], "count": [50, 4],
        "color": ["#000000", "#111111"], "hover": ["h1", "h2"],
    })
    fig = C.bars_with_gutter(
        df, family="champ", label_col="field_name", value_col="share_pct",
        color=df["color"].tolist(), hover_col="hover", value_fmt=hv.fmt_pct,
    )
    gutter_trace = fig.data[-1]
    assert list(gutter_trace.text) == [hv.fmt_pct(42.7), hv.fmt_pct(3.1)]
    # never the raw count formatted as an integer (the pass-6 behaviour this replaces)
    assert list(gutter_trace.text) != [hv.fmt_int(50), hv.fmt_int(4)]

    # vacuity
    assert list(gutter_trace.text) != [hv.fmt_pct(0.0), hv.fmt_pct(0.0)]


def test_lab_fwci_whiskers_has_exactly_one_red_dashed_reference_at_fwci_1():
    """Importing the page module directly triggers heavy Streamlit/data side effects
    at import time (S1 caches, `st.set_page_config`, etc. -- not worth an AppTest run
    just for one `add_vline` call), so this pins the SOURCE-LEVEL contract instead:
    the vline call site uses the token + dash + width, never a literal grey hex."""
    from lib.helpers import REFERENCE_RED

    span = _func_source("plot_fwci_whiskers")
    assert span.count("fig.add_vline(") == 1
    assert "line_color=REFERENCE_RED" in span
    assert "line_dash=C.REFERENCE_DASH" in span
    assert REFERENCE_RED == "#821D13"  # sanity: the token IS red, not the old grey

    # vacuity: the old grey-dotted call must NOT satisfy the same check
    old_call = 'fig.add_vline(x=1, line_dash="dot", line_color="#B0B6BC")'
    assert "line_color=REFERENCE_RED" not in old_call


# ============================================================================
# alignment -- plot_fwci_whiskers mirrors its sibling's height/left-margin
# (PF-4: the pair must line up row-for-row now that fig_share's height
# formula changed from the old ad hoc 22*n+130 to bars_with_gutter's own)
# ============================================================================

def test_fwci_pair_panels_share_height_and_left_margin():
    from lib import charts as C
    df_share = pd.DataFrame({
        "field_name": ["A", "B", "C"], "share_pct": [50.0, 30.0, 20.0],
        "isite_share_pct": [0.0, 0.0, 0.0], "count": [10, 5, 2],
        "color": ["#000000", "#111111", "#222222"], "hover": ["h", "h", "h"],
    })
    fig_share = C.bars_with_gutter(
        df_share, family="champ", label_col="field_name", value_col="share_pct",
        color=df_share["color"].tolist(), hover_col="hover",
    )
    assert fig_share.layout.margin.l == C.margin_left("champ")

    # the page's own plot_fwci_whiskers signature must accept layout_ref (source pin --
    # constructing df_fwci + calling it needs full Streamlit context we avoid here)
    span = _func_source("plot_fwci_whiskers")
    assert "layout_ref: go.Figure" in span
    assert "height=layout_ref.layout.height" in span
    assert "l=C.margin_left(\"champ\")" in span

    # vacuity: a signature without layout_ref must NOT satisfy the same check
    assert "layout_ref: go.Figure" not in _func_source("plot_global_breakdown_h")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
