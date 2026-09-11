# tests/test_page7b_p6.py
"""
Pass-7b (worker P6, W3) pins -- `Streamlit/pages/6_🔎_Exploration_thématique.py`, the
NON-partner sections ONLY: time-series ("Évolution temporelle", `ex_time_abs` /
`ex_time_share`) and structure ("Analyse des contributions", `ex_dept_bars` /
`ex_lab_bars`). The partner sections (`ex_partner_reciprocity` and friends, P-EX 7a) and
the KPI tiles (backlog #4) are OUT OF FENCE and untouched by this stream -- checks below
are scoped to MY_FENCE_SRC (the source slice between the time-evolution heading and the
Section-6 partner-tables marker) wherever a whole-page check would otherwise trip on
pre-existing, explicitly-kept, out-of-scope text (the drill-selector's own "Comment lire"
at ~L344).

Idiom: tests/test_page7_col.py (hover/reading source-text pins, vacuity twins) +
tests/test_page7_ex.py (SAME page, AppTest figure introspection via
`app.get("plotly_chart")[i].proto.spec` -- this Streamlit build has no `.value` hook on a
plain st.plotly_chart).

Vacuity (P14): every assertion group is followed by an in-memory mutation that must make
the identical check fail.

    .venv-pinned\\Scripts\\python -m pytest tests\\test_page7b_p6.py -q
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
STREAMLIT_DIR = ROOT / "Streamlit"
DATA_DIR = STREAMLIT_DIR / "data"
PAGES_DIR = STREAMLIT_DIR / "pages"
MENU_PY = STREAMLIT_DIR / "Menu.py"
PAGE6 = "6_\U0001F50E_Exploration_thématique.py"
PAGE6_SRC = (PAGES_DIR / PAGE6).read_text(encoding="utf-8")
TIMEOUT = 120

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
# My fence, as a source-text slice (time-evolution heading -> Section 6 marker)
# ============================================================================
_FENCE_START = "### \U0001F4C8 Évolution temporelle par "
_FENCE_END = "# Section 6: Partner Tables"
assert _FENCE_START in PAGE6_SRC and _FENCE_END in PAGE6_SRC, "fence markers moved -- update this test"
MY_FENCE_SRC = PAGE6_SRC[PAGE6_SRC.index(_FENCE_START): PAGE6_SRC.index(_FENCE_END)]

P6_CHART_KEYS = ["ex_time_abs", "ex_time_share", "ex_dept_bars", "ex_lab_bars"]


def _exc_values(at: AppTest) -> list:
    return [e.value for e in at.exception]


def _goto(page_rel: str) -> AppTest:
    """Same fix as tests/test_page7_ex.py::_goto: a bare pages/*.py AppTest raises
    KeyError('url_pathname') on lib.controls.sidebar()'s st.page_link -- boot Menu.py
    first (registers every page), then switch_page."""
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


@pytest.fixture()
def page6_physical_sciences() -> AppTest:
    """Domain level, 'Physical Sciences' -- the SAME probe-verified, populated fixture
    tests/test_page_pb.py and tests/test_page7_ex.py already rely on."""
    at = _goto(f"pages/{PAGE6}")
    assert not at.exception, f"page6 default load raised: {_exc_values(at)}"
    _select(at, "Choisir le niveau :", "domain")
    element_box = [s for s in at.selectbox if s.label == "Choisir l'élément :"][0]
    physical = [o for o in element_box.options if "Physical Sciences" in o][0]
    _select(at, "Choisir l'élément :", physical)
    assert not at.exception, f"page6 domain element select raised: {_exc_values(at)}"
    return at


# ============================================================================
# (a) hover grammar -- every hovertemplate on the page is the bare constant
# ============================================================================
HOVERTEMPLATE_RE = re.compile(r"hovertemplate\s*=\s*([^\n,\)]+)")


def test_every_hovertemplate_on_the_page_is_the_bare_grammar_constant():
    matches = HOVERTEMPLATE_RE.findall(PAGE6_SRC)
    assert matches, "expected at least one hovertemplate= on the page"
    for m in matches:
        assert m.strip().rstrip(",") in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE"), m

    # vacuity: a literal format-spec hovertemplate must be caught by the SAME regex
    bad_src = 'fig.update_traces(hovertemplate="<b>%{customdata[0]:.1%}</b><extra></extra>")\n'
    bad = HOVERTEMPLATE_RE.findall(bad_src)
    assert bad and bad[0].strip() not in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE")


# ============================================================================
# (b) hover_lines well-formed for every (key, mode) of MY four charts
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


@pytest.mark.parametrize("chart_key", P6_CHART_KEYS)
def test_hover_lines_wellformed_for_every_my_chart(chart_key):
    from lib import copy_fr
    from lib import hover as hv
    labels = copy_fr.HOVER_LABELS[chart_key]["default"]
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
# (c) reading lines -- one call site per MY chart key; "Comment lire" gone from MY fence
#     but the out-of-scope drill-selector caption (~L344) is explicitly kept
# ============================================================================
def test_reading_line_called_once_per_my_chart_key():
    for key in P6_CHART_KEYS:
        assert PAGE6_SRC.count(f'reading_line("{key}"') == 1, key

    # vacuity: a page missing a chart's reading_line call must be caught by the same check
    stripped = PAGE6_SRC.replace('reading_line("ex_dept_bars"', "pass  # removed", 1)
    assert stripped.count('reading_line("ex_dept_bars"') == 0


def test_comment_lire_retired_from_my_fence_but_out_of_scope_one_survives():
    assert "Comment lire" not in MY_FENCE_SRC
    # P6-R2/brief carve-out: the drill-UX caption at ~L344 is explicitly NOT a chart
    # and must stay -- this is a real property of the (untouched) whole page, not a
    # regression to fix, so the page as a whole is NOT "Comment lire"-free.
    assert "Comment lire" in PAGE6_SRC

    # vacuity: reinserting a literal INSIDE the fence must be caught by the fence check
    mutated_fence = MY_FENCE_SRC + "\nst.caption(':grey[**Comment lire.** x]')\n"
    assert "Comment lire" in mutated_fence


# ============================================================================
# (d) no percent tickformat, no hex literal
# ============================================================================
PCT_TICKFORMAT_RE = re.compile(r'tickformat\s*=\s*["\'][.\d]*%')
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}")


def test_no_percent_tickformat_in_my_fence():
    assert not PCT_TICKFORMAT_RE.search(MY_FENCE_SRC)
    # vacuity
    assert PCT_TICKFORMAT_RE.search('fig.update_yaxes(tickformat=".0%")')


def test_no_hex_literal_anywhere_on_the_page():
    """B6/hex ratchet: page 6 is EXEMPT_PAGES-listed today for having hex; this stream
    removed the last 4 (STRUCTURE_TYPE_COLORS dict + the dept-bar green) -- report
    ratchet: remove pages/6_... once this is green."""
    assert not HEX_RE.search(PAGE6_SRC)
    # vacuity
    assert HEX_RE.search('colors="#59a14f"')


# ============================================================================
# (e)/(f) bars: phantom gutter trace text == fmt_int of the REAL totals
# ============================================================================
def _parse_blob(blob, fields: list[str]) -> list[dict]:
    """Mirrors the page's OWN parse_top_items() -- reimplemented here (not imported:
    the page is a Streamlit script with top-level st.* calls, unsafe to import
    directly), same idiom as tests/test_page7_col.py's _reciprocity_population."""
    if pd.isna(blob) or not str(blob).strip():
        return []
    out = []
    for item in str(blob).split("|"):
        parts = item.split(":")
        if len(parts) >= len(fields):
            out.append({f: parts[i] for i, f in enumerate(fields)})
    return out


def _contrib_row(domain_id: str = "3") -> pd.Series:
    path = DATA_DIR / "thematic_detail_contributions.parquet"
    if not path.is_file():
        pytest.skip(f"{path} not deployed -- run the pipeline + 60_deploy first")
    df = pd.read_parquet(path)
    row = df[(df["level"] == "domain") & (df["id"] == domain_id)]
    if row.empty:
        pytest.skip(f"no contribution row for domain {domain_id} in this snapshot")
    return row.iloc[0]


def test_dept_and_lab_bars_gutter_text_matches_fmt_int_of_real_totals():
    from lib import hover as hv

    row = _contrib_row("3")
    dept_items = _parse_blob(row.get("department_breakdown", ""), ["dept", "count", "pct"])
    lab_items = _parse_blob(row.get("top_labs", ""), ["ror", "name", "type", "count", "pct"])
    if not dept_items or not lab_items:
        pytest.skip("thin fixture: need both dept and lab contribution data at domain 3")

    # bars_with_gutter puts frame row 0 at the TOP (Streamlit/lib/charts.py::_bar_layout,
    # range=[n-0.5, -0.5]) -- the page sorts DESCENDING so the largest value is row 0,
    # matching this chart's own reading line ("la plus fournie en haut").
    dept_counts = sorted((int(i["count"]) for i in dept_items), reverse=True)
    lab_df = pd.DataFrame(lab_items)
    lab_df["count"] = lab_df["count"].astype(int)
    lab_counts = lab_df.sort_values("count", ascending=False).head(10)["count"].tolist()

    expected_dept_texts = tuple(hv.fmt_int(c) for c in dept_counts)
    expected_lab_texts = tuple(hv.fmt_int(c) for c in lab_counts)

    at = _goto(f"pages/{PAGE6}")
    _select(at, "Choisir le niveau :", "domain")
    element_box = [s for s in at.selectbox if s.label == "Choisir l'élément :"][0]
    physical = [o for o in element_box.options if "Physical Sciences" in o][0]
    _select(at, "Choisir l'élément :", physical)
    assert not at.exception, _exc_values(at)

    traces = _all_chart_traces(at)
    gutter_texts = [tuple(t["text"]) for t in traces if t.get("hoverinfo") == "skip" and t.get("text")]
    assert expected_dept_texts in gutter_texts, (expected_dept_texts, gutter_texts)
    assert expected_lab_texts in gutter_texts, (expected_lab_texts, gutter_texts)

    # vacuity: an off-by-one count must NOT match any rendered gutter text
    bad_dept_texts = tuple(hv.fmt_int(c + 1) for c in dept_counts)
    assert bad_dept_texts not in gutter_texts


# ============================================================================
# (f) FR percent formatting in hover customdata app-wide on this page (no english
#     decimal point glued to a raw "%", every "%" preceded by the narrow no-break space)
# ============================================================================
def test_hover_percent_values_on_the_page_are_fr_formatted(page6_physical_sciences):
    from lib.helpers import FR_THIN_SPACE

    traces = _all_chart_traces(page6_physical_sciences)
    cds: list[str] = []
    for t in traces:
        cd = t.get("customdata")
        if not cd:
            continue
        for row in cd:
            cds.extend(str(x) for x in row) if isinstance(row, list) else cds.append(str(row))
    pct_strings = [s for s in cds if "%" in s]
    assert pct_strings, "expected at least one percent value among this page's hover strings"
    for s in pct_strings:
        for m in re.finditer("%", s):
            assert s[m.start() - 1] == FR_THIN_SPACE, f"'%' not preceded by the FR narrow space: {s!r}"
        assert not re.search(r"\.\d+" + re.escape(FR_THIN_SPACE) + "%", s), f"english decimal point: {s!r}"

    # vacuity: an un-FR-formatted percent must fail the narrow-space check above
    bad = "12.34%"
    assert not (bad[bad.index("%") - 1] == FR_THIN_SPACE)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
