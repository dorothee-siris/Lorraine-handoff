# tests/test_page7b_p14.py
"""
Pass-7b pins -- page 14 Benchmark (P14, W2/W3): the pass-7 hover/reading/token grammar
on `bench_rung_forest` (4 small multiples, forest form) and `bench_dot_ratio` (3
drill-down panels, dot-ratio form). BUILD_PLAN.md SS2 (P14 rows) + docs/contract_fragments/
chart_keys_pass7.md L90-91 + docs/tooltip_spec.yaml (bench_rung_forest / bench_dot_ratio
blocks) are the spec of record; tests/test_page_pe.py (pass-5) stays the parity golden --
this file adds ONLY the new pass-7b contract, never re-pins a number test_page_pe.py
already covers (UL KPI, peer counts, drill-down defaults, the R18 axis-type toggle).

Idiom copied verbatim from tests/test_page7_col.py (page 8, pass 7a): a source-level
regex scan for the hover/reading/colour contract (cheap, exact) + `AppTest` reading a
rendered `st.plotly_chart` element's own JSON via `proto.spec` (this Streamlit build has
no queryable trace object -- test_page_pe.py's own docstring) for the two page-specific
geometry pins the recipe names (margin.l via the `partenaire` family token, the red
dashed reference vline).

Vacuity (P14): every assertion group below is followed by an in-memory mutation that
must make the identical check fail -- a pin that cannot fail is theater.

    python -m pytest tests/test_page7b_p14.py -q
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
PAGES_DIR = STREAMLIT_DIR / "pages"

BENCH_PAGE_NAME = "14_\U0001F9ED_Benchmark.py"
PAGE = PAGES_DIR / BENCH_PAGE_NAME
PAGE_SRC = PAGE.read_text(encoding="utf-8")

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    # F-SYSMOD fix (MINOR, matches every other page test file in this suite): one-line
    # fallback so `conftest` stays importable even if this file is run standalone.
    sys.path.insert(0, str(_TESTS_DIR))
from conftest import restore_lib, swap_lib_to_streamlit  # centralized guard, see conftest.py

_saved_lib_modules: dict = {}


def setup_module(_module) -> None:
    global _saved_lib_modules
    _saved_lib_modules = swap_lib_to_streamlit()


def teardown_module(_module) -> None:
    restore_lib(_saved_lib_modules)


def _fresh_app() -> AppTest:
    at = AppTest.from_file(str(PAGE), default_timeout=60)
    at.run()
    assert not at.exception, f"page raised on default render: {at.exception}"
    return at


def _chart_spec(app: AppTest, index: int) -> dict:
    charts = app.get("plotly_chart")
    return json.loads(charts[index].proto.spec)


# ============================================================================
# (a) hover grammar -- every hovertemplate on the page is the bare grammar constant
# ============================================================================

HOVERTEMPLATE_RE = re.compile(r"hovertemplate\s*=\s*([^\n,\)]+)")


def test_every_hovertemplate_on_the_page_is_the_bare_grammar_constant():
    matches = HOVERTEMPLATE_RE.findall(PAGE_SRC)
    assert matches, "expected at least one hovertemplate= on the page"
    for m in matches:
        assert m.strip().rstrip(",") in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE"), m

    # vacuity: a literal format-spec hovertemplate must be caught by the SAME regex
    bad_src = 'fig.update_traces(hovertemplate="<b>%{customdata[0]:.1%}</b><extra></extra>")\n'
    bad = HOVERTEMPLATE_RE.findall(bad_src)
    assert bad and bad[0].strip() not in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE")


# ============================================================================
# (b) hover_lines well-formed for every (key, mode) this page declares
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


PAGE14_CHART_MODES = [
    ("bench_rung_forest", "fwci_mean_on"), ("bench_rung_forest", "fwci_mean_off"),
    ("bench_dot_ratio", "lq_champ_log"), ("bench_dot_ratio", "lq_champ_lineaire"),
    ("bench_dot_ratio", "lq_sous_champ_log"), ("bench_dot_ratio", "lq_sous_champ_lineaire"),
    ("bench_dot_ratio", "pptop_champ"),
]


@pytest.mark.parametrize("chart_key,mode", PAGE14_CHART_MODES)
def test_hover_lines_wellformed_for_every_page14_chart_mode(chart_key, mode):
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

    # vacuity: a malformed line (label present, value glued with no "<b>...</b> : ")
    # must be CAUGHT by _assert_hover_wellformed
    with pytest.raises(AssertionError):
        _assert_hover_wellformed("<b>Entité X</b><br>libellé sans mise en forme : 3")


# ============================================================================
# (c) reading lines -- ONE call for the forest grid (not four), ONE per dot-ratio
#     panel/mode (three: A, B, C) -- BUILD_PLAN P14 row + brief override the generic
#     "once per key" recipe default with these exact counts.
# ============================================================================

def test_reading_line_called_expected_count_per_chart_key():
    assert PAGE_SRC.count('reading_line("bench_rung_forest"') == 1
    assert PAGE_SRC.count('reading_line("bench_dot_ratio"') == 3
    assert PAGE_SRC.count("reading_line(") == 4
    assert "Comment lire" not in PAGE_SRC

    # vacuity: removing one dot-ratio panel's call must be caught by the count check
    stripped = PAGE_SRC.replace('reading_line("bench_dot_ratio"', "pass  # removed", 1)
    assert stripped.count('reading_line("bench_dot_ratio"') == 2
    # vacuity: the forest grid's single call, removed, must drop the count to zero
    stripped2 = PAGE_SRC.replace('reading_line("bench_rung_forest"', "pass  # removed", 1)
    assert stripped2.count('reading_line("bench_rung_forest"') == 0
    # vacuity: a reintroduced static caption must be caught by the substring check
    assert "Comment lire" in (PAGE_SRC + "\n# Comment lire ce graphique -- reintroduit")


# ============================================================================
# (d) no percent tickformat, no hex literal anywhere on the page
# ============================================================================

TICKFORMAT_PCT_RE = re.compile(r"tickformat\s*=\s*[\"'][^\"']*%[^\"']*[\"']")
HEX_LITERAL_RE = re.compile(r"#[0-9A-Fa-f]{6}")


def test_no_percent_tickformat_and_no_hex_literal_in_source():
    assert not TICKFORMAT_PCT_RE.search(PAGE_SRC), "a Plotly percent tickformat= survives (B5)"
    assert not HEX_LITERAL_RE.search(PAGE_SRC), "a #RRGGBB literal survives (B6)"

    # vacuity: both regexes must catch a reintroduced offender
    assert TICKFORMAT_PCT_RE.search('fig.update_xaxes(tickformat=".0%")')
    assert HEX_LITERAL_RE.search('PEER_GREY = "#8C9196"')


# ============================================================================
# (e)/(f) page-specific pins (brief): forest margin.l uses the `partenaire` family
# token; every dot-ratio panel carries exactly one red dashed reference vline at its
# own ref_x, and every trace on it uses the bare hover grammar constant.
# ============================================================================

def test_rung_forest_margin_left_uses_partenaire_family_token():
    from lib import charts as C
    at = _fresh_app()
    spec = _chart_spec(at, 0)  # rung figures are chart indices 0-3 (test_page_pe.py)
    expected = C.margin_left("partenaire")
    assert spec["layout"]["margin"]["l"] == expected

    # vacuity: a wrong margin (any other family's budget) must be caught by the same check
    wrong = C.margin_left("champ")
    assert wrong != expected
    assert not (spec["layout"]["margin"]["l"] == wrong)


def _assert_single_red_dashed_vline(shapes: list[dict], expected_x: float) -> None:
    from lib import charts as C
    from lib import helpers as H
    line_shapes = [s for s in shapes if s.get("type") == "line"]
    assert len(line_shapes) == 1, f"expected exactly one reference line, got {len(line_shapes)}"
    shape = line_shapes[0]
    assert shape["line"]["dash"] == C.REFERENCE_DASH
    assert shape["line"]["color"] == H.REFERENCE_RED
    assert shape["line"]["width"] == C.REFERENCE_WIDTH_PX
    assert shape["x0"] == shape["x1"] == expected_x


def _assert_only_ul_trace_carries_text(traces: list[dict]) -> None:
    """
    FOLLOW-UP 1 (manager, post-render review): the per-point direct labels collided at
    1280px on every dot-ratio panel -- removed everywhere except the UL trace (one
    "UL" per row, `mode="markers+text"`); every peer trace is now `mode="markers"`
    with no `text` at all (the hover's own "établissement" line + the legend already
    carry the peer identity).
    """
    text_traces = [t for t in traces if t.get("mode") == "markers+text"]
    assert len(text_traces) == 1, f"expected exactly one text-bearing trace (UL), got {len(text_traces)}"
    ul_trace = text_traces[0]
    assert all(t == "UL" for t in ul_trace.get("text") or []), ul_trace.get("text")
    for t in traces:
        if t is ul_trace:
            continue
        assert t.get("mode") == "markers", f"peer trace must be mode=markers, got {t.get('mode')!r}"
        assert not t.get("text"), f"peer trace must carry no text label, got {t.get('text')!r}"


@pytest.mark.parametrize("chart_index", [4, 5, 6])
def test_dot_ratio_panels_show_ul_label_only_no_peer_text_collisions(chart_index):
    at = _fresh_app()
    spec = _chart_spec(at, chart_index)
    _assert_only_ul_trace_carries_text(spec["data"])

    # vacuity: a fabricated peer trace carrying text (the pre-fix behaviour) must be CAUGHT
    bad_traces = [dict(t) for t in spec["data"]]
    for t in bad_traces:
        if t.get("mode") != "markers+text":
            t["mode"] = "markers+text"
            t["text"] = ["Nantes"] * len(t.get("x") or [])
    with pytest.raises(AssertionError):
        _assert_only_ul_trace_carries_text(bad_traces)
    # vacuity: zero text-bearing traces (UL label silently dropped too) must be CAUGHT
    with pytest.raises(AssertionError):
        _assert_only_ul_trace_carries_text([{**t, "mode": "markers", "text": []} for t in spec["data"]])


@pytest.mark.parametrize("chart_index,expected_x", [(4, 1.0), (5, 1.0), (6, 10.0)])
def test_dot_ratio_panels_have_one_red_dashed_reference_vline(chart_index, expected_x):
    at = _fresh_app()
    spec = _chart_spec(at, chart_index)
    _assert_single_red_dashed_vline(spec["layout"].get("shapes", []), expected_x)
    for trace in spec["data"]:
        assert trace["hovertemplate"] == "%{customdata}<extra></extra>"

    # vacuity: a second (fabricated) line shape, or a wrong colour/x, must be CAUGHT
    real_shapes = spec["layout"].get("shapes", [])
    with pytest.raises(AssertionError):
        _assert_single_red_dashed_vline(real_shapes + [real_shapes[0]], expected_x)
    bad_shape = dict(real_shapes[0])
    bad_shape["line"] = dict(bad_shape["line"])
    bad_shape["line"]["color"] = "#8C9196"
    with pytest.raises(AssertionError):
        _assert_single_red_dashed_vline([bad_shape], expected_x)
    with pytest.raises(AssertionError):
        _assert_single_red_dashed_vline(real_shapes, expected_x + 1.0)
