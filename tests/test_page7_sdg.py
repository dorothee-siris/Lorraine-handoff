# tests/test_page7_sdg.py
"""
Pass-7a (worker S-SDG) pins: SDG colour identity (P17) on Streamlit/pages/2_*.py
(lab_sdg_bars) and Streamlit/pages/4_*.py (pf_sdg_bars, pf_sdg_peers_scatter), plus the
two page-2 S1 cache-line decorators (BUILD_PLAN.md P12).

Two layers, same house pattern as tests/test_page_pg.py / tests/test_page_pb.py:
  - SOURCE-TEXT / AST pins (fast, no Streamlit runtime): the two decorators literally
    carry max_entries=64, and the page-local SDG_NAMES/SDG_BAR_COLOR duplicates are gone
    (single source of truth = lib.helpers, landed by S-LIB-B).
  - AppTest pins (real Streamlit runtime, same `lib` package as the app): the SDG figures
    actually render with per-goal SDG_COLORS marker fills, numbered "ODD " labels, and
    spec-shaped hover (customdata + HOVERTEMPLATE -- never a live "%{...:...}" format
    spec baked into the template, VIZ_SPEC_pass6 §0.1 / BUILD_PLAN P2/P14, the same rule
    tests/test_hover_tripwire.py polices app-wide).

Namespace note (same collision as test_page_pg.py/test_page_pb.py's own docstrings): this
repo has TWO packages named `lib` -- setup_module/teardown_module swap
sys.modules['lib'*] to the Streamlit one for this file's run via tests/conftest.py's
centralized guard.

Figure-introspection idiom: AppTest has NO `.value` hook on a plain `st.plotly_chart`
(verified empirically by tests/test_page_pa.py and tests/test_page_pe.py, both already
shipped) -- traces are read off `app.get("plotly_chart")[i].proto.spec` (JSON), same as
tests/test_page_pe.py::_chart_traces. Charts are found by CONTENT signature (a trace
whose first y-value starts with the numbered "ODD " label), never a hardcoded index --
page 2's panel count depends on which structure is selected, page 4's on the active
sdg_variant().

    python -m pytest tests/test_page7_sdg.py -q
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from conftest import restore_lib, swap_lib_to_streamlit  # centralized guard, see conftest.py

ROOT = Path(__file__).resolve().parent.parent
STREAMLIT_DIR = ROOT / "Streamlit"
PAGES_DIR = STREAMLIT_DIR / "pages"
DATA_DIR = STREAMLIT_DIR / "data"
MENU_PY = STREAMLIT_DIR / "Menu.py"
TIMEOUT = 120

LAB_PAGE = next(PAGES_DIR.glob("2_*.py")).name
PF_PAGE = next(PAGES_DIR.glob("4_*.py")).name
LAB_SRC = (PAGES_DIR / LAB_PAGE).read_text(encoding="utf-8")
PF_SRC = (PAGES_DIR / PF_PAGE).read_text(encoding="utf-8")

_saved_lib_modules = None


def setup_module(_module) -> None:
    global _saved_lib_modules
    _saved_lib_modules = swap_lib_to_streamlit()


def teardown_module(_module) -> None:
    restore_lib(_saved_lib_modules)


def _exc_values(at: AppTest) -> list:
    return [e.value for e in at.exception]


def _goto(page_rel: str) -> AppTest:
    """Same fix as tests/test_page_pb.py::_goto: a bare pages/*.py AppTest raises
    KeyError('url_pathname') on lib.controls.sidebar()'s st.page_link -- start from
    Menu.py (which populates the multipage registry) and switch_page into the target."""
    at = AppTest.from_file(str(MENU_PY))
    at.run(timeout=TIMEOUT)
    at.switch_page(page_rel)
    at.run(timeout=TIMEOUT)
    return at


def _a_well_covered_lab() -> str:
    """A curated lab-type structure with the most (sdg x conf_state) rows in
    sdg_lab_methods.parquet -- a cheap proxy for "will have >=1 goal above the
    reliability floor for whichever method/conf_state the sidebar defaults to", read
    straight off the deployed data so this pin does not depend on selectbox ordering
    (the mini-fiche's default index=0 structure is NOT guaranteed to be covered -- it
    may be a Pole/hors-liste row, out of this table's scope, lib.helpers.helpers's own
    _lab_set() docstring)."""
    df = pd.read_parquet(DATA_DIR / "sdg_lab_methods.parquet")
    return df.groupby("lab").size().sort_values(ascending=False).index[0]


def _all_chart_traces(app: AppTest) -> list[dict]:
    return [t for c in app.get("plotly_chart") for t in json.loads(c.proto.spec)["data"]]


def _y0_starts_with_odd(t: dict) -> bool:
    y = t.get("y")
    return bool(y) and isinstance(y[0], str) and y[0].startswith("ODD ")


def _assert_hover_lines_spec_shaped(customdata: list[str]) -> None:
    """docs/tooltip_spec.yaml "regles dures", enforced at the RENDERED string level:
    every hover string starts bold (line 0, the entity, no colon) and every OTHER line
    is exactly "<b>label</b> : value" (lib/hover.py::hover_lines' own contract)."""
    line_rx = re.compile(r"^<b>[^<]+</b> : .+$")
    for cd in customdata:
        assert cd.startswith("<b>"), cd
        for line in cd.split("<br>")[1:]:
            assert line_rx.match(line), line


# =============================================================================
# AST / SOURCE-TEXT pins -- no Streamlit runtime needed
# =============================================================================

def _decorator_max_entries(src: str, func_name: str):
    """`max_entries=` kwarg value of func_name's @st.cache_data(...) decorator, or
    None if absent/bare -- same AST idiom as tests/test_cache_rules.py."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "attr", None) == "cache_data":
                    for kw in dec.keywords:
                        if kw.arg == "max_entries":
                            return ast.literal_eval(kw.value)
            return None
    raise AssertionError(f"{func_name} not found in source")


def test_page2_s1_decorators_carry_max_entries_64():
    assert _decorator_max_entries(LAB_SRC, "_lab_works_slice") == 64
    assert _decorator_max_entries(LAB_SRC, "_lab_wordcloud_slice") == 64


def test_vacuity_decorator_max_entries_check_catches_the_old_bare_decorator():
    bare = "@st.cache_data\ndef _lab_works_slice(lab_key):\n    pass\n"
    assert _decorator_max_entries(bare, "_lab_works_slice") is None


def test_page2_and_page4_sdg_identity_is_single_sourced_from_helpers():
    """The page-local SDG_NAMES/SDG_BAR_COLOR duplicates (pre-P17) are gone; both
    pages now import the shared SDG_LABELS_FR/sdg_color (lib.helpers, S-LIB-B)."""
    for src in (LAB_SRC, PF_SRC):
        assert "SDG_NAMES = {" not in src
        assert "SDG_LABELS_FR" in src and "sdg_color" in src
    assert "SDG_BAR_COLOR" not in PF_SRC


def test_sdg_chart_sites_use_the_shared_hover_grammar():
    """The 3 SDG chart sites build customdata + HOVERTEMPLATE -- never a live
    "%{...:...}" format spec baked into hovertemplate (the app-wide rule
    tests/test_hover_tripwire.py polices; pinned locally too since pages 2/4 stay in
    EXEMPT_PAGES this pass for their OTHER, untouched charts)."""
    assert LAB_SRC.count("hovertemplate=HOVERTEMPLATE") == 1
    # pf_sdg_bars (1) + pf_sdg_peers_scatter's two traces (peers, UL) = 3.
    assert PF_SRC.count("hovertemplate=HOVERTEMPLATE") == 3


def test_vacuity_hover_shape_check_catches_a_malformed_line():
    with pytest.raises(AssertionError):
        _assert_hover_lines_spec_shaped(["<b>ODD 3 · Bonne santé et bien-être</b>",
                                          "part du corpus 12,0 %"])  # missing "<b>label</b> : "


def test_vacuity_odd_label_check_catches_an_unnumbered_label():
    """The historical bug this pins against: page 4 used to emit "SDG {i} · ..."
    (English prefix, pre-P17) instead of the numbered FR "ODD {i} · ..." label."""
    labels = ["ODD 3 · Bonne santé et bien-être", "SDG 4 · Éducation de qualité"]
    assert not all(lab.startswith("ODD ") for lab in labels)


# =============================================================================
# AppTest pins -- page 2, lab_sdg_bars
# =============================================================================

@pytest.fixture()
def lab_app() -> AppTest:
    at = _goto(f"pages/{LAB_PAGE}")
    assert not at.exception, f"page2 default load raised: {_exc_values(at)}"
    box = [s for s in at.selectbox if s.label == "Sélectionner une structure"][0]
    box.set_value(_a_well_covered_lab())
    at.run(timeout=TIMEOUT)
    assert not at.exception, f"page2 structure select raised: {_exc_values(at)}"
    return at


def test_lab_sdg_bars_colour_label_and_hover(lab_app):
    from lib.helpers import SDG_COLORS

    bar_traces = [t for t in _all_chart_traces(lab_app)
                  if t.get("type") == "bar" and _y0_starts_with_odd(t)]
    assert bar_traces, "no SDG bar trace found on the lab mini-fiche"
    trace = bar_traces[0]

    labels = trace["y"]
    assert all(lab.startswith("ODD ") for lab in labels), labels
    goals = [int(re.match(r"ODD (\d+)", lab).group(1)) for lab in labels]

    assert list(trace["marker"]["color"]) == [SDG_COLORS[g] for g in goals], (
        "bar fill must be the goal's own SDG_COLORS hex, not a flat colour")
    assert [SDG_COLORS[g] for g in goals] != ["#3E7CB1"] * len(goals)  # P14 vacuity

    _assert_hover_lines_spec_shaped(trace["customdata"])


# =============================================================================
# AppTest pins -- page 4, pf_sdg_bars + pf_sdg_peers_scatter
# =============================================================================

@pytest.fixture()
def pf_app() -> AppTest:
    at = _goto(f"pages/{PF_PAGE}")
    assert not at.exception, f"page4 default load raised: {_exc_values(at)}"
    return at


def test_pf_sdg_bars_and_peers_scatter_colour_label_and_hover(pf_app):
    from lib.helpers import SDG_COLORS

    traces = _all_chart_traces(pf_app)

    bar_traces = [t for t in traces if t.get("type") == "bar" and _y0_starts_with_odd(t)]
    assert bar_traces, "no SDG bar trace found on the portfolio page"
    bar = bar_traces[0]
    bar_goals = [int(re.match(r"ODD (\d+)", y).group(1)) for y in bar["y"]]
    assert list(bar["marker"]["color"]) == [SDG_COLORS[g] for g in bar_goals]
    assert [SDG_COLORS[g] for g in bar_goals] != ["#3E7CB1"] * len(bar_goals)  # P14 vacuity
    _assert_hover_lines_spec_shaped(bar["customdata"])

    scatter_traces = [t for t in traces
                       if t.get("type") == "scatter" and t.get("mode") == "markers"
                       and _y0_starts_with_odd(t)]
    assert len(scatter_traces) >= 2, "expected a peers trace and a UL (diamond) trace"
    ul = next(t for t in scatter_traces if t.get("marker", {}).get("symbol") == "diamond")
    peers = next(t for t in scatter_traces if t is not ul)

    for trace in (ul, peers):
        goals = [int(re.match(r"ODD (\d+)", y).group(1)) for y in trace["y"]]
        assert list(trace["marker"]["color"]) == [SDG_COLORS[g] for g in goals], (
            "each mark's colour must be its OWN goal's SDG_COLORS hex, never a flat "
            "entity colour (P17 recolour: colour now encodes the goal, shape encodes "
            "the entity)")
        _assert_hover_lines_spec_shaped(trace["customdata"])

    # Entity line comes from the `entity_name` FIELD (tooltip_spec.yaml
    # pf_sdg_peers_scatter), not a hardcoded string -- bench_sdg.parquet's FOCAL row
    # happens to carry "Universite de Lorraine" (no accent, a data-layer quirk outside
    # this dispatch's scope), so the pin reads the same source rather than assume the
    # prettier hardcoded spelling the pre-P17 chart used.
    _ul_name = pd.read_parquet(DATA_DIR / "bench_sdg.parquet").query("rung == 'FOCAL'")["entity_name"].iloc[0]
    assert any(cd.startswith(f"<b>{_ul_name}</b>") for cd in ul["customdata"])
    # P14 vacuity: the per-point checks above WOULD catch the pre-P17 flat entity fills
    # (grey for peers, focal blue for UL) that used to stand in for a goal colour.
    assert list(ul["marker"]["color"]) != ["#0072B2"] * len(ul["y"])
    assert list(peers["marker"]["color"]) != [peers["marker"]["color"][0]] * len(peers["y"]) \
        or len(set(peers["y"])) <= 1
