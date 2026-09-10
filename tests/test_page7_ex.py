# tests/test_page7_ex.py
"""
Pass-7a (worker P-EX) pins -- `Streamlit/pages/6_🔎_Exploration_thématique.py`, the two
partner sections ONLY ("Principaux partenaires" + "Réciprocité stratégique avec les
partenaires"; everything else on the page is out of this dispatch's fence).

Two layers, same house pattern as tests/test_page7_sdg.py / tests/test_page_pb.py:
  - SOURCE-TEXT pins (fast, no Streamlit runtime): the retired "Comment lire ce
    graphique" bullet block is gone; the shared builder/lib calls are wired in.
  - AppTest pins (real Streamlit runtime, Streamlit's own `lib` package): the partner
    tables carry a live OpenAlex ↗ link column scoped to the CURRENT element's node;
    the reciprocity chart renders on site_reciprocity_scatter's shared grammar with
    spec-shaped hover; the reading line changes with the type/scope toggles.

Figure-introspection idiom (identical to tests/test_page7_sdg.py::_all_chart_traces):
AppTest has no `.value` hook on a plain `st.plotly_chart` -- traces are read off
`app.get("plotly_chart")[i].proto.spec` (JSON).

    .venv-pinned\\Scripts\\python -m pytest tests\\test_page7_ex.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

import pytest
from streamlit.testing.v1 import AppTest

from conftest import restore_lib, swap_lib_to_streamlit  # centralized guard, see conftest.py

ROOT = Path(__file__).resolve().parent.parent
STREAMLIT_DIR = ROOT / "Streamlit"
PAGES_DIR = STREAMLIT_DIR / "pages"
MENU_PY = STREAMLIT_DIR / "Menu.py"
PAGE6 = "6_\U0001F50E_Exploration_thématique.py"
PAGE6_SRC = (PAGES_DIR / PAGE6).read_text(encoding="utf-8")
TIMEOUT = 120

_saved_lib_modules = None


def setup_module(_module) -> None:
    global _saved_lib_modules
    _saved_lib_modules = swap_lib_to_streamlit()


def teardown_module(_module) -> None:
    restore_lib(_saved_lib_modules)


def _exc_values(at: AppTest) -> list:
    return [e.value for e in at.exception]


def _goto(page_rel: str) -> AppTest:
    """Same fix as tests/test_page_pb.py::_goto / tests/test_page7_sdg.py::_goto: a bare
    pages/*.py AppTest raises KeyError('url_pathname') on lib.controls.sidebar()'s
    st.page_link -- boot Menu.py first (registers every page), then switch_page."""
    at = AppTest.from_file(str(MENU_PY))
    at.run(timeout=TIMEOUT)
    at.switch_page(page_rel)
    at.run(timeout=TIMEOUT)
    return at


def _select(at: AppTest, label: str, value) -> None:
    box = [s for s in at.selectbox if s.label == label][0]
    box.set_value(value)
    at.run(timeout=TIMEOUT)


def _all_chart_traces(app: AppTest) -> list[dict]:
    return [t for c in app.get("plotly_chart") for t in json.loads(c.proto.spec)["data"]]


def _assert_hover_lines_spec_shaped(customdata: list[str]) -> None:
    """docs/tooltip_spec.yaml "regles dures", enforced at the RENDERED string level
    (same check as tests/test_page7_sdg.py::_assert_hover_lines_spec_shaped): every
    hover string starts bold (line 0, the entity, no colon) and every OTHER line is
    exactly "<b>label</b> : value" (lib/hover.py::hover_lines' own contract)."""
    line_rx = re.compile(r"^<b>[^<]+</b> : .+$")
    for cd in customdata:
        assert cd.startswith("<b>"), cd
        for line in cd.split("<br>")[1:]:
            assert line_rx.match(line), line


@pytest.fixture()
def page6_field() -> AppTest:
    """Field level, first (highest-volume) option -- same fixture shape as
    test_page_pb.py's own depth-20 pin, certain to carry populated partner tables."""
    at = _goto(f"pages/{PAGE6}")
    assert not at.exception, f"page6 default load raised: {_exc_values(at)}"
    _select(at, "Choisir le niveau :", "field")
    element_box = [s for s in at.selectbox if s.label == "Choisir l'élément :"][0]
    _select(at, "Choisir l'élément :", element_box.options[0])
    assert not at.exception, f"page6 field element select raised: {_exc_values(at)}"
    return at


@pytest.fixture()
def page6_physical_sciences() -> AppTest:
    """Domain level, 'Physical Sciences' -- the SAME probe-verified fixture
    test_page_pb.py::test_page6_reciprocity_type_filter_defaults_to_education_only uses
    (carries reciprocity_partners data under the default education-only type filter)."""
    at = _goto(f"pages/{PAGE6}")
    assert not at.exception, f"page6 default load raised: {_exc_values(at)}"
    _select(at, "Choisir le niveau :", "domain")
    element_box = [s for s in at.selectbox if s.label == "Choisir l'élément :"][0]
    physical = [o for o in element_box.options if "Physical Sciences" in o][0]
    _select(at, "Choisir l'élément :", physical)
    assert not at.exception, f"page6 domain element select raised: {_exc_values(at)}"
    return at


# =============================================================================
# SOURCE-TEXT pins -- no Streamlit runtime needed
# =============================================================================

def test_comment_lire_bullet_block_is_retired():
    """P7-R6/BUILD_PLAN P3: the static bullet list is REPLACED by ONE reading line;
    'Pourquoi cet indicateur' stays (both asserted below)."""
    assert "Comment lire ce graphique" not in PAGE6_SRC
    assert "**Pourquoi cet indicateur.**" in PAGE6_SRC


def test_page_wires_the_shared_lib_contract():
    for needle in (
        "from lib.charts import site_reciprocity_scatter",
        "from lib import copy_fr",
        "from lib import hover as hv",
        "from lib import links",
        "from lib import reading",
        "site_reciprocity_scatter(plot_df, floor=0)",
        'reading.reading_line("ex_partner_reciprocity"',
        "link_cols={",
    ):
        assert needle in PAGE6_SRC, needle


def test_geo_colour_legend_html_is_retired():
    """The manual blue/red France/International legend described a colour encoding
    the shared grammar no longer uses (UL_COLOR uniformly) -- keeping it would mislead."""
    assert "background-color:blue" not in PAGE6_SRC
    assert "background-color:red;margin-right:4px" not in PAGE6_SRC


# =============================================================================
# AppTest pins -- Section 6, partner tables' link column (deliverable 2)
# =============================================================================

def test_partner_tables_gain_a_node_scoped_openalex_link_column(page6_field):
    element_box = [s for s in page6_field.selectbox if s.label == "Choisir l'élément :"][0]
    element_id = element_box.value

    tables_with_lien = [d.value for d in page6_field.dataframe if "Lien" in d.value.columns]
    assert tables_with_lien, "expected at least one partner table with a 'Lien' column"
    for t in tables_with_lien:
        assert "Partenaire" in t.columns, "the link column must be ADDED, not replace Partenaire"
        urls = t["Lien"].dropna().tolist()
        assert urls, "expected populated link cells"
        for url in urls:
            assert url.startswith("https://openalex.org/works?filter="), url
            assert f"authorships.institutions.id:" in unquote(url), url
            assert f"primary_topic.field.id:{element_id}" in unquote(url), url


def test_partner_tables_link_column_is_subfield_scoped_at_subfield_level():
    at = _goto(f"pages/{PAGE6}")
    _select(at, "Choisir le niveau :", "subfield")
    element_box = [s for s in at.selectbox if s.label == "Choisir l'élément :"][0]
    _select(at, "Choisir l'élément :", element_box.options[0])
    assert not at.exception, _exc_values(at)
    # Refetch AFTER the rerun -- a widget proxy captured before its own set_value()
    # call reports back whatever was FED to set_value (here, options[0]'s FORMATTED
    # label, per AppTest's own convention), not the resolved raw session value.
    element_id = [s for s in at.selectbox if s.label == "Choisir l'élément :"][0].value

    tables_with_lien = [d.value for d in at.dataframe if "Lien" in d.value.columns]
    if not tables_with_lien:
        pytest.skip("no partner data for the first subfield option (thin element)")
    url = tables_with_lien[0]["Lien"].dropna().iloc[0]
    assert f"primary_topic.subfield.id:{element_id}" in unquote(url), url


def test_vacuity_node_filter_check_catches_the_wrong_key():
    """The check above hinges on finding 'primary_topic.<level>.id:<id>' verbatim --
    proves it actually discriminates rather than passing on any string."""
    from lib.links import copubs_url

    good = unquote(copubs_url("I1294671590", node=("field", 17)))
    assert "primary_topic.field.id:17" in good
    mutated = good.replace("primary_topic.field.id:17", "primary_topic.subfield.id:17")
    assert "primary_topic.field.id:17" not in mutated, "mutation must actually change the string"


# =============================================================================
# AppTest pins -- Section 7, reciprocity chart (deliverables 1 + 3)
# =============================================================================

def _reciprocity_trace(app: AppTest) -> dict:
    from lib.helpers import UL_COLOR

    candidates = [
        t for t in _all_chart_traces(app)
        if t.get("mode") == "markers" and t.get("marker", {}).get("color") == UL_COLOR
    ]
    assert candidates, "expected a site_reciprocity_scatter-grammar trace (UL_COLOR markers)"
    return candidates[0]


def test_reciprocity_scatter_uses_shared_grammar_and_spec_hover(page6_physical_sciences):
    trace = _reciprocity_trace(page6_physical_sciences)

    assert trace.get("type") in ("scatter", "scattergl")
    assert trace["x"], "expected at least one placeable partner"
    symbols = trace.get("marker", {}).get("symbol")
    assert symbols and set(symbols) <= {"circle", "square"}

    customdata = [str(c) for c in trace["customdata"]]
    assert customdata
    _assert_hover_lines_spec_shaped(customdata)
    # At least one hover line must carry a REAL contract label (not ad hoc page prose).
    assert any("co-publications avec l'UL sur ce nœud" in cd for cd in customdata), customdata[:3]


def test_vacuity_hover_shape_check_catches_a_malformed_line():
    with pytest.raises(AssertionError):
        _assert_hover_lines_spec_shaped([
            "<b>Humanitas University</b>",
            "co-publications avec l'UL sur ce nœud 173",  # missing "<b>label</b> : "
        ])


def test_reciprocity_reading_line_present_and_changes_with_geo_scope(page6_physical_sciences):
    from lib.reading import reading_text

    at = page6_physical_sciences
    type_filters = [m for m in at.multiselect if m.label == "Filtrer par type d'institution"]
    assert type_filters and type_filters[0].value == ["education"], (
        "fixture assumption: default type filter is ['education'] (test_page_pb.py's own pin)")

    geo_scopes = [r for r in at.radio if r.label == "Portée géographique"][0]
    scope_to_mode = {
        "France et international": "fr_intl",
        "France uniquement": "fr",
        "International uniquement": "intl",
    }
    for scope_label, scope_mode in scope_to_mode.items():
        geo_scopes = [r for r in at.radio if r.label == "Portée géographique"][0]
        geo_scopes.set_value(scope_label)
        at.run(timeout=TIMEOUT)
        assert not at.exception, _exc_values(at)
        expected = reading_text("ex_partner_reciprocity", f"education|{scope_mode}")
        captions = [c.value for c in at.caption]
        assert expected in captions, (scope_label, captions)


def test_vacuity_reading_line_check_catches_the_wrong_mode():
    from lib.reading import reading_text

    fr_text = reading_text("ex_partner_reciprocity", "education|fr")
    intl_text = reading_text("ex_partner_reciprocity", "education|intl")
    assert fr_text != intl_text, "the two modes must render DIFFERENT text for the toggle test to bite"
