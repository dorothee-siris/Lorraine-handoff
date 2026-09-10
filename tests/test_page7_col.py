# tests/test_page7_col.py
"""
Pass-7a pins -- page 8 Collaborations (P-COL, W3): reciprocity scatter (NEW), hub/
consortium companion charts on `bars_with_gutter`, momentum-quadrant hover grammar,
reading lines, S4 cache decorators, page workbook.

AppTest cannot introspect a rendered Plotly figure's own traces in this Streamlit build
(documented limitation -- see tests/test_page_pa.py / tests/test_page_pf.py's own
docstrings: "AppTest has no queryable element for st.plotly_chart"). Numeric/figure
assertions below therefore either (a) recompute the expected value independently from the
deployed parquet -- same idiom as test_page_pf.py's own `_hub_population()` -- or (b) call
the SAME pure builder (`lib.charts.site_reciprocity_scatter`) the page itself calls, on a
frame built the same way the page builds it, exactly as tests/_registry.py's own
`build_col_reciprocity()` does for the generic registry check -- never a re-derivation of
the builder's own geometry. AppTest IS used for what it can see: st.metric values and
st.dataframe contents (rendered text/numbers), matching test_page_pa.py's convention.

Vacuity (P14): every assertion group below is followed by an in-memory mutation that
must make the identical check fail -- a pin that cannot fail is theater.

    python -m pytest tests/test_page7_col.py -q
"""
from __future__ import annotations

import ast
import io
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
DATA_DIR = STREAMLIT_DIR / "data"
PAGES_DIR = STREAMLIT_DIR / "pages"

COLLAB_PAGE = "8_\U0001F91D_Collaborations.py"
COLLAB_SRC = (PAGES_DIR / COLLAB_PAGE).read_text(encoding="utf-8")

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


def _skip_if_missing(path: Path) -> None:
    if not path.is_file():
        pytest.skip(f"{path} not deployed -- run the pipeline + 60_deploy first")


def _exc_values(at) -> list:
    return [e.value for e in at.exception]


def _neutralize_page_link(monkeypatch) -> None:
    """Pre-existing harness limitation, not caused by this stream (see
    tests/test_page_pf.py's own `_neutralize_page_link` docstring for the full story):
    lib.controls.sidebar()'s méthodo-expander calls st.page_link() unconditionally on
    every page's first render, which raises KeyError('url_pathname') under a direct
    AppTest.from_file() load. Neutralised so these tests exercise THIS page's own logic."""
    import streamlit as st_mod
    monkeypatch.setattr(st_mod, "page_link", lambda *a, **k: None)


# ============================================================================
# (1) col_reciprocity -- point count matches the page's OWN floor-gated population
# ============================================================================

def _reciprocity_population(floor: int) -> pd.DataFrame:
    """Reproduces 8_Collaborations.py's own reciprocity pool at (conf_state='all',
    subset_id='all'): co_works_full >= floor, share_p/share_ul both notna and > 0
    (identical filter to tests/_registry.py::frame_site_reciprocity, PLUS the floor
    gate that function omits -- this page's own p20/p10 toggle)."""
    path = DATA_DIR / "ptn_summary.parquet"
    _skip_if_missing(path)
    s = pd.read_parquet(path)
    d = s[(s["conf_state"] == "all") & (s["subset_id"] == "all")]
    d = d[d["co_works_full"] >= floor]
    return d[d["share_p"].notna() & d["share_ul"].notna()
             & (d["share_p"] > 0) & (d["share_ul"] > 0)].reset_index(drop=True)


def _as_scatter_frame(placeable: pd.DataFrame) -> pd.DataFrame:
    d = placeable.copy()
    d["share_ul"] = d["share_ul"] * 100.0
    d["share_p"] = d["share_p"] * 100.0
    d["hover"] = ["x"] * len(d)
    return d


@pytest.mark.parametrize("floor", [20, 10])
def test_reciprocity_scatter_point_count_matches_floor_gated_population_exact(floor):
    from lib import charts as C
    placeable = _reciprocity_population(floor)
    if placeable.empty:
        pytest.skip(f"no placeable partner at floor {floor} in this deployed snapshot")
    d = _as_scatter_frame(placeable)
    fig = C.site_reciprocity_scatter(d, floor=floor)
    assert len(fig.data) == 1
    assert len(fig.data[0].x) == len(placeable)

    # vacuity (P14): one fewer row -> the identical count check must now fail
    fig2 = C.site_reciprocity_scatter(d.iloc[:-1], floor=floor)
    assert len(fig2.data[0].x) != len(placeable)


def test_reciprocity_scatter_square_marker_iff_capped_flag():
    """`share_p_capped_flag` is all-False in the currently deployed snapshot (probed
    2026-09-10 -- 0/29244 rows) -- a real-data-only test would be vacuous by
    construction, so this pins the capped-iff-square contract on a small, controlled
    synthetic frame (the exact columns lib.charts.site_reciprocity_scatter requires)."""
    from lib import charts as C
    d = pd.DataFrame({
        "partner_id": ["A", "B", "C"], "display_name": ["A", "B", "C"],
        "share_ul": [1.0, 2.0, 3.0], "share_p": [1.0, 2.0, 3.0],
        "share_p_capped_flag": [True, False, False],
        "co_works_full": [10, 20, 30], "hover": ["h1", "h2", "h3"],
    })
    fig = C.site_reciprocity_scatter(d, floor=20)
    assert list(fig.data[0].marker.symbol) == ["square", "circle", "circle"]

    # vacuity: flip the flag off -> the square must disappear
    d2 = d.copy()
    d2["share_p_capped_flag"] = [False, False, False]
    fig2 = C.site_reciprocity_scatter(d2, floor=20)
    assert list(fig2.data[0].marker.symbol) == ["circle", "circle", "circle"]
    assert list(fig.data[0].marker.symbol) != list(fig2.data[0].marker.symbol)


# ============================================================================
# (2) three rendered numbers, recomputed from ptn_summary, EXACT
# ============================================================================

def test_kpi_partners_ge10_matches_ptn_summary_exact(monkeypatch):
    path = DATA_DIR / "ptn_summary.parquet"
    _skip_if_missing(path)
    s = pd.read_parquet(path)
    d = s[(s["conf_state"] == "all") & (s["subset_id"] == "all")]
    expected_n = int((d["co_works_full"] >= 10).sum())
    from lib.helpers import fr_int
    expected_str = fr_int(expected_n)

    _neutralize_page_link(monkeypatch)
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(PAGES_DIR / COLLAB_PAGE))
    at.run(timeout=90)
    assert not at.exception, _exc_values(at)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Partenaires (≥10 co-publications)") == expected_str

    # vacuity: an off-by-one expectation must NOT match the rendered value
    assert metrics.get("Partenaires (≥10 co-publications)") != fr_int(expected_n + 1)


def test_hub_top_row_copubs_matches_ptn_summary_exact(monkeypatch):
    path = DATA_DIR / "ptn_summary.parquet"
    _skip_if_missing(path)
    s = pd.read_parquet(path)
    d = s[(s["conf_state"] == "all") & (s["subset_id"] == "all")]
    d = d[d["co_works_full"] >= 20].sort_values("co_works_full", ascending=False)
    if d.empty:
        pytest.skip("no hub row at the default floor in this deployed snapshot")
    expected_top_copubs = int(d.iloc[0]["co_works_full"])

    _neutralize_page_link(monkeypatch)
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(PAGES_DIR / COLLAB_PAGE))
    at.run(timeout=90)
    assert not at.exception, _exc_values(at)
    # ranked_table()'s ref_labels only relabel the ST DISPLAY (column_config), not the
    # underlying frame AppTest hands back -- it still carries the internal column name
    # "co_works" (confirmed live: 2 `dataframe` elements render on this page, the hub
    # table with its 18 internal columns incl. "co_works"/"share_p_pct", and the
    # smaller new/dormant table which IS pre-renamed to "Co-publications" -- picking
    # "share_p_pct" as the filter disambiguates the hub table from that second one).
    dfs = [dl.value for dl in at.get("dataframe")
           if "share_p_pct" in getattr(dl.value, "columns", [])]
    assert dfs, "expected the hub table to render with a 'share_p_pct' column"
    hub_df = dfs[0]
    assert int(hub_df.iloc[0]["co_works"]) == expected_top_copubs

    # vacuity
    assert int(hub_df.iloc[0]["co_works"]) != expected_top_copubs + 1


def test_reciprocity_scatter_one_points_shares_match_ptn_summary_exact():
    from lib import charts as C
    placeable = _reciprocity_population(20)
    if placeable.empty:
        pytest.skip("no placeable partner at floor 20 in this deployed snapshot")
    ordered = placeable.sort_values("co_works_full", ascending=False).reset_index(drop=True)
    expected_x = float(ordered.iloc[0]["share_ul"]) * 100.0
    expected_y = float(ordered.iloc[0]["share_p"]) * 100.0
    d = _as_scatter_frame(ordered)
    fig = C.site_reciprocity_scatter(d, floor=20)
    assert abs(float(fig.data[0].x[0]) - expected_x) < 1e-6
    assert abs(float(fig.data[0].y[0]) - expected_y) < 1e-6

    # vacuity: a deliberately wrong expectation must NOT match within tolerance
    assert abs(float(fig.data[0].x[0]) - (expected_x + 1.0)) > 1e-6


# ============================================================================
# (3) hover grammar -- every hovertemplate on the page is the bare grammar constant
# ============================================================================

HOVERTEMPLATE_RE = re.compile(r"hovertemplate\s*=\s*([^\n,\)]+)")


def test_every_hovertemplate_on_the_page_is_the_bare_grammar_constant():
    matches = HOVERTEMPLATE_RE.findall(COLLAB_SRC)
    assert matches, "expected at least one hovertemplate= on the page"
    for m in matches:
        assert m.strip().rstrip(",") in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE"), m

    # vacuity: a literal format-spec hovertemplate must be caught by the SAME regex
    bad_src = 'fig.update_traces(hovertemplate="<b>%{customdata[0]:.1%}</b><extra></extra>")\n'
    bad = HOVERTEMPLATE_RE.findall(bad_src)
    assert bad and bad[0].strip() not in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE")


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


@pytest.mark.parametrize("chart_key,mode", [
    ("col_hub_companion", "default"), ("col_reciprocity", "p20"), ("col_reciprocity", "p10"),
    ("col_consortium_bars", "default"), ("col_momentum_quadrant", "log"),
    ("col_momentum_quadrant", "lineaire"),
])
def test_hover_lines_wellformed_for_every_page8_chart_mode(chart_key, mode):
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
# (4) reading lines -- one call site per chart key on the page
# ============================================================================

PAGE8_CHART_KEYS = [
    "col_hub_companion", "col_reciprocity", "col_consortium_bars", "col_momentum_quadrant",
]


def test_reading_line_called_once_per_chart_key():
    for key in PAGE8_CHART_KEYS:
        assert COLLAB_SRC.count(f'reading_line("{key}"') == 1, key
    assert COLLAB_SRC.count("reading_line(") == len(PAGE8_CHART_KEYS)

    # vacuity: a page missing a chart's reading_line call must be caught by the same check
    stripped = COLLAB_SRC.replace('reading_line("col_reciprocity"', "pass  # removed", 1)
    assert stripped.count('reading_line("col_reciprocity"') == 0


# ============================================================================
# (5) S4 cache decorators -- ttl=1800, max_entries=2, on all 4 loaders (AST)
# ============================================================================

S4_FUNCS = ("_load_ptn_summary", "_load_ptn_mom_facts", "_load_consortium_weights",
            "_load_ptn_denominators")


def _cache_data_kwargs(tree: ast.AST, func_name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call):
                    fn = dec.func
                    dotted = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                    if dotted == "cache_data":
                        return {kw.arg: ast.literal_eval(kw.value) for kw in dec.keywords if kw.arg}
    return None


def test_s4_decorators_carry_ttl_1800_max_entries_2():
    tree = ast.parse(COLLAB_SRC)
    for fn in S4_FUNCS:
        kwargs = _cache_data_kwargs(tree, fn)
        assert kwargs is not None, f"{fn} is not decorated with @st.cache_data(...)"
        assert kwargs.get("ttl") == 1800, (fn, kwargs)
        assert kwargs.get("max_entries") == 2, (fn, kwargs)

    # vacuity: a decorator missing max_entries must be caught by the same reader
    bad_tree = ast.parse(
        "import streamlit as st\n\n@st.cache_data(ttl=1800)\ndef _load_ptn_summary():\n    pass\n"
    )
    bad_kwargs = _cache_data_kwargs(bad_tree, "_load_ptn_summary")
    assert bad_kwargs.get("max_entries") != 2


# ============================================================================
# (6) page workbook -- opens with openpyxl, "Lecture" sheet first
# ============================================================================

def test_page_workbook_opens_with_openpyxl_and_lecture_sheet_first():
    import openpyxl
    from lib import exports
    sheets = {
        "hub": pd.DataFrame({"a": [1, 2]}), "réciprocité": pd.DataFrame({"b": [3]}),
        "consortium": pd.DataFrame({"c": [4]}), "quadrant": pd.DataFrame(),
    }
    lecture = [("clé1", "valeur1"), ("clé2", "valeur2")]
    xlsx_bytes, filename = exports.page_workbook(sheets, lecture, view="collaborations")
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    assert wb.sheetnames[0] == "Lecture"
    assert filename.endswith(".xlsx")

    # vacuity: a different sheet set must NOT produce the same sheetnames list
    xlsx_bytes2, _ = exports.page_workbook({}, lecture, view="collaborations")
    wb2 = openpyxl.load_workbook(io.BytesIO(xlsx_bytes2))
    assert wb2.sheetnames == ["Lecture"]
    assert wb2.sheetnames != wb.sheetnames


def test_page8_calls_page_workbook_with_four_named_sheets_and_lecture_rows():
    assert "exports.page_workbook(" in COLLAB_SRC
    block = COLLAB_SRC[COLLAB_SRC.index("_wb_bytes, _wb_name = exports.page_workbook("):
                        COLLAB_SRC.index("st.download_button(")]
    for sheet_key in ('"hub"', '"réciprocité"', '"consortium"', '"quadrant"'):
        assert sheet_key in block, sheet_key
    assert "_lecture_rows" in block

    # vacuity: removing one sheet key from this exact block must be caught
    mutated = block.replace('"consortium": _workbook_consortium_df,', "")
    assert '"consortium"' not in mutated


# ============================================================================
# (7) smoke -- page survives the NEW reciprocity floor toggle
# ============================================================================

def test_page8_survives_reciprocity_floor_toggle_switch(monkeypatch):
    _neutralize_page_link(monkeypatch)
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(PAGES_DIR / COLLAB_PAGE))
    at.run(timeout=90)
    assert not at.exception, _exc_values(at)
    recip_radio = next((r for r in at.get("radio") if r.key == "col_recip_floor"), None)
    if recip_radio is None:
        pytest.skip("reciprocity floor radio not rendered in this state (no placeable partner)")
    recip_radio.set_value("p10")
    at.run(timeout=90)
    assert not at.exception, _exc_values(at)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
