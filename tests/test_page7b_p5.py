# tests/test_page7b_p5.py
"""
Pass-7b pins -- page 5 "Positionnement" (P5, W2): the 5 registered chart keys
(pos_lq_frontier, pos_frontier_labs, pos_div_spark, pos_peer_frontier, pos_domain_heatmap)
move onto the shared pass-7 grammar (BUILD_PLAN.md B2/B3/B5/B6, docs/contract_fragments/
chart_keys_pass7.md, docs/tooltip_spec.yaml). Idiom copied from tests/test_page7_col.py
(hovertemplate regex pin, generic hover_lines wellformedness, reading_line count, S4-style
source-span extraction for figure geometry AppTest cannot introspect -- its own docstring:
"AppTest has no queryable element for st.plotly_chart").

Vacuity (P14): every assertion group is followed by an in-memory mutation that must make
the identical check fail -- a pin that cannot fail is theater.

    python -m pytest tests/test_page7b_p5.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
PAGES_DIR = STREAMLIT_DIR / "pages"
DATA_DIR = STREAMLIT_DIR / "data"

PAGE5 = "5_\U0001F4CD_Positionnement.py"
PAGE5_SRC = (PAGES_DIR / PAGE5).read_text(encoding="utf-8")
TIMEOUT = 180.0

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


def _exc_values(at) -> list:
    return [e.value for e in at.exception]


def _neutralize_page_link(monkeypatch) -> None:
    """Same pre-existing harness limitation as test_page7_col.py's own helper: sidebar()'s
    méthodo-expander calls st.page_link() unconditionally, which raises under a direct
    AppTest.from_file() load."""
    import streamlit as st_mod
    monkeypatch.setattr(st_mod, "page_link", lambda *a, **k: None)


MY_CHART_KEYS_MODES = [
    ("pos_lq_frontier", "log"), ("pos_lq_frontier", "lineaire"),
    ("pos_frontier_labs", "default"), ("pos_div_spark", "default"),
    ("pos_peer_frontier", "default"), ("pos_domain_heatmap", "default"),
]
MY_CHART_KEYS = ["pos_lq_frontier", "pos_frontier_labs", "pos_div_spark",
                 "pos_peer_frontier", "pos_domain_heatmap"]


# ============================================================================
# (a) hover grammar -- every hovertemplate= on the page is the bare grammar constant
# ============================================================================

HOVERTEMPLATE_RE = re.compile(r"hovertemplate\s*=\s*([^\n,\)]+)")


def test_every_hovertemplate_on_page5_is_the_bare_grammar_constant():
    matches = HOVERTEMPLATE_RE.findall(PAGE5_SRC)
    assert matches, "expected at least one hovertemplate= on page 5"
    assert len(matches) == 7, matches  # 3 (fig_t9) + 1 (spark) + 2 (fig_peer) + 1 (heatmap)
    for m in matches:
        assert m.strip().rstrip(",") in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE"), m

    # vacuity: a literal format-spec hovertemplate must be caught by the SAME regex
    bad_src = 'fig.update_traces(hovertemplate="<b>%{customdata[0]:.1%}</b><extra></extra>")\n'
    bad = HOVERTEMPLATE_RE.findall(bad_src)
    assert bad and bad[0].strip() not in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE")


# ============================================================================
# (b) hover grammar -- hover_lines well-formed for every (key, mode) on this page
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


@pytest.mark.parametrize("chart_key,mode", MY_CHART_KEYS_MODES)
def test_hover_lines_wellformed_for_every_page5_chart_mode(chart_key, mode):
    from lib import copy_fr
    from lib import hover as hv
    labels = copy_fr.HOVER_LABELS[chart_key][mode]
    assert len(labels) <= hv.MAX_LINES
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


def test_hover_labels_match_yaml_registry_for_all_five_keys():
    """docs/tooltip_spec.yaml is the source S-TT wrote the mode VALUES from -- a page-owned
    sanity check that copy_fr.HOVER_LABELS carries the exact same mode set per key (the
    generic tests/test_hover_spec.py already checks (a)-(c) completeness; this just pins
    MY five keys specifically so a drift on page 5 is caught here too)."""
    from lib import copy_fr
    expected_modes = {
        "pos_lq_frontier": {"log", "lineaire"}, "pos_frontier_labs": {"default"},
        "pos_div_spark": {"default"}, "pos_peer_frontier": {"default"},
        "pos_domain_heatmap": {"default"},
    }
    for key, modes in expected_modes.items():
        assert set(copy_fr.HOVER_LABELS[key].keys()) == modes, key

    # vacuity: an off-by-one expected mode set must NOT match
    assert set(copy_fr.HOVER_LABELS["pos_frontier_labs"].keys()) != {"default", "extra"}


# ============================================================================
# (c) reading lines -- one call site per chart key, "Comment lire" only on tables
# ============================================================================

def test_reading_line_called_once_per_my_chart_key():
    for key in MY_CHART_KEYS:
        assert PAGE5_SRC.count(f'reading_line("{key}"') == 1, key
    assert PAGE5_SRC.count("reading_line(") == len(MY_CHART_KEYS)

    # vacuity: a page missing a chart's reading_line call must be caught by the same check
    stripped = PAGE5_SRC.replace('reading_line("pos_div_spark")', "pass  # removed", 1)
    assert stripped.count('reading_line("pos_div_spark")') == 0


def test_comment_lire_survives_only_on_the_three_table_panels():
    """B2 removes the static 'Comment lire' paragraph for every CHART (my 5 keys); the
    3 panels that introduce a `ranked_table` (emerging topics, frontier-labs table,
    co-discipline pairs table) are TABLES, not one of my registered chart keys -- no
    copy_fr key exists for them (reading_line() would KeyError) -- so brief P7B_P5.md's
    own "leave them (say so)" instruction applies. Exactly 4 occurrences remain: the 3
    named table intros PLUS the emerging-topics panel (l.≈350 in the pre-migration
    file), which the brief's own line grouped with the "chart" set even though it has no
    registered key -- logged in progress/P7B_P5.md Step 1 as a deliberate, conservative
    reading (touching it would require inventing an unregistered key)."""
    n = PAGE5_SRC.count("Comment lire")
    assert n == 4, n
    for key in MY_CHART_KEYS:
        # none of the 5 chart READING sentences (copy_fr) open with the retired heading
        assert f'reading_line("{key}"' in PAGE5_SRC

    # vacuity: re-inserting one removed static block must raise the count
    mutated = PAGE5_SRC + '\nst.markdown("**Comment lire ce graphique** : injected")\n'
    assert mutated.count("Comment lire") == n + 1


# ============================================================================
# (d) axes/colours -- no percent tickformat, zero hex literal anywhere on the page
# ============================================================================

def test_no_percent_tickformat_and_zero_hex_literal():
    assert not re.search(r'tickformat\s*=\s*["\']\.\d*%', PAGE5_SRC)
    hex_hits = re.findall(r"#[0-9A-Fa-f]{6}", PAGE5_SRC)
    assert hex_hits == [], hex_hits

    # vacuity: an injected hex literal / percent tickformat must be CAUGHT
    bad = PAGE5_SRC + '\nX = "#123ABC"\nfig.update_xaxes(tickformat=".0%")\n'
    assert re.findall(r"#[0-9A-Fa-f]{6}", bad) == ["#123ABC"]
    assert re.search(r'tickformat\s*=\s*["\']\.\d*%', bad)


def test_focal_blue_constant_is_gone():
    assert "FOCAL_BLUE" not in PAGE5_SRC
    # vacuity
    assert "FOCAL_BLUE" in (PAGE5_SRC + "\nFOCAL_BLUE = 1\n")


# ============================================================================
# (e) pos_frontier_labs -- bars_with_gutter phantom-gutter text == fmt_int(values)
# ============================================================================

def test_pos_frontier_labs_gutter_text_matches_formatted_values():
    from lib import charts as C
    from lib import hover as hv
    d = pd.DataFrame({
        "lab": ["Labo A", "Labo B", "Labo C"],
        "Frontier works": [12, 340, 5],
        "hover": ["h1", "h2", "h3"],
        "_isite_frontier_n": [2, 10, 0],
    })
    fig = C.bars_with_gutter(
        d, family="labo", label_col="lab", value_col="Frontier works",
        color="rgb(0,114,178)", isite_col="_isite_frontier_n", isite_on=False, value_fmt=hv.fmt_int,
    )
    gutter_trace = next(t for t in fig.data if t.hoverinfo == "skip")
    assert list(gutter_trace.text) == [hv.fmt_int(v) for v in d["Frontier works"]]

    # vacuity: a wrong expected list must NOT match
    assert list(gutter_trace.text) != [hv.fmt_int(v + 1) for v in d["Frontier works"]]


def test_pos_frontier_labs_isite_overlay_uses_shared_hover_grammar():
    """B3: bars_with_gutter's own isite_on branch REPLACES lib.overlay's own hover with
    the shared grammar on every resulting trace (lib/charts.py L472-475) -- pinned here
    because pos_frontier_labs is the one chart on this page that goes through that
    branch."""
    from lib import charts as C
    from lib import hover as hv
    d = pd.DataFrame({
        "lab": ["Labo A", "Labo B"], "Frontier works": [10, 20],
        "hover": ["hover-A", "hover-B"], "_isite_frontier_n": [3, 4],
    })
    fig = C.bars_with_gutter(
        d, family="labo", label_col="lab", value_col="Frontier works",
        color="rgb(0,114,178)", isite_col="_isite_frontier_n", isite_on=True, value_fmt=hv.fmt_int,
    )
    bar_traces = [t for t in fig.data if t.hoverinfo != "skip"]
    assert bar_traces, "expected at least one non-gutter bar trace under isite_on=True"
    for t in bar_traces:
        assert t.hovertemplate == hv.HOVERTEMPLATE

    # vacuity: a trace NOT carrying the shared template must be caught by the same check
    assert not all(t.hovertemplate == "%{y}<extra></extra>" for t in bar_traces)


# ============================================================================
# (f) page-specific pins -- fig_t9 two red-dashed reference shapes; heatmap
#     customdata shape == z shape (real page source, execed on a controlled frame)
# ============================================================================

def _extract_span(marker_start: str, marker_end: str) -> str:
    start = PAGE5_SRC.index(marker_start)
    end = PAGE5_SRC.index(marker_end, start)
    return PAGE5_SRC[start:end]


def test_fig_t9_carries_exactly_two_red_dashed_reference_shapes_and_zero_grey():
    import plotly.graph_objects as go
    from lib import charts as C
    from lib.helpers import REFERENCE_RED

    snippet = _extract_span("fig_t9.add_vline(", "\nfor _xa_, _ya_, _txt_")
    fig_t9 = go.Figure()
    _neutral_point = 51.0
    exec(compile(snippet, "<fig_t9_reference_span>", "exec"),
         {"go": go, "C": C, "REFERENCE_RED": REFERENCE_RED, "fig_t9": fig_t9,
          "_neutral_point": _neutral_point})

    shapes = fig_t9.layout.shapes
    assert len(shapes) == 2, shapes
    for shp in shapes:
        assert shp.line.dash == "dash"
        assert shp.line.color == REFERENCE_RED
        assert shp.line.color != "#8C9196"

    # vacuity: the OLD grey literal must NOT satisfy the same check
    grey_snippet = snippet.replace("REFERENCE_RED", '"#8C9196"')
    fig_grey = go.Figure()
    exec(compile(grey_snippet, "<fig_t9_grey>", "exec"),
         {"go": go, "C": C, "REFERENCE_RED": REFERENCE_RED, "fig_t9": fig_grey,
          "_neutral_point": _neutral_point})
    assert any(shp.line.color != REFERENCE_RED for shp in fig_grey.layout.shapes)


def test_fig_peer_carries_one_red_dashed_reference_shape():
    import plotly.graph_objects as go
    from lib import charts as C
    from lib.helpers import REFERENCE_RED

    snippet = _extract_span("fig_peer.add_vline(", "\nfig_peer.update_layout(")
    fig_peer = go.Figure()
    _neutral_peer = 51.0
    exec(compile(snippet, "<fig_peer_reference_span>", "exec"),
         {"go": go, "C": C, "REFERENCE_RED": REFERENCE_RED, "fig_peer": fig_peer,
          "_neutral_peer": _neutral_peer})
    shapes = fig_peer.layout.shapes
    assert len(shapes) == 1
    assert shapes[0].line.dash == "dash"
    assert shapes[0].line.color == REFERENCE_RED

    # vacuity
    assert shapes[0].line.color != "#8C9196"


def test_heatmap_customdata_shape_matches_z_shape():
    """B3 platform note (treemap/heatmap): 2-D customdata, one hover string per cell.
    Execs the REAL page snippet (source-extracted, not a reimplementation) on a
    controlled 3x3 frame."""
    from lib import copy_fr
    from lib import hover as hv

    snippet = _extract_span("_z = _dom_matrix.values", "\nfig_dom = go.Figure(")
    ns = {
        "np": np, "hv": hv, "copy_fr": copy_fr,
        "_dom_matrix": pd.DataFrame(np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])),
        "_dom_names_order": ["Domaine A", "Domaine B", "Domaine C"],
    }
    exec(compile(snippet, "<heatmap_customdata_span>", "exec"), ns)

    z = ns["_z"]
    customdata = ns["_dom_customdata"]
    assert len(customdata) == z.shape[0]
    assert all(len(row) == z.shape[1] for row in customdata)
    _assert_hover_wellformed(customdata[0][0])
    assert "Domaine A × Domaine A" in customdata[0][0]
    assert "Domaine A × Domaine B" in customdata[0][1]

    # vacuity: a snippet using the WRONG inner range must produce a mismatched shape
    bad_snippet = snippet.replace(
        "for j in range(len(_dom_names_order))",
        "for j in range(len(_dom_names_order) - 1)",
    )
    ns_bad = dict(ns)
    exec(compile(bad_snippet, "<heatmap_customdata_bad>", "exec"), ns_bad)
    assert len(ns_bad["_dom_customdata"][0]) != z.shape[1]


# ============================================================================
# (g) smoke -- page survives default load and the I-SITE overlay toggle (the branch
#     that exercises _isite_lq_by_field / the isite scatter trace / the in_isite
#     co-discipline perimeter switch, all NEW or touched by this stream)
# ============================================================================

def test_page5_survives_default_load(monkeypatch):
    _neutralize_page_link(monkeypatch)
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(PAGES_DIR / PAGE5))
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)


def test_page5_survives_isite_overlay_toggle(monkeypatch):
    _neutralize_page_link(monkeypatch)
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(PAGES_DIR / PAGE5))
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)
    isite_toggle = next((t for t in at.toggle if t.key == "isite_overlay"), None)
    if isite_toggle is None:
        pytest.skip("I-SITE overlay toggle not rendered in this sidebar state")
    isite_toggle.set_value(True)
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
