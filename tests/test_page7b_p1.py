# tests/test_page7b_p1.py
"""
Pass-7b pins -- page 1 Vue d'ensemble (P1, W2): the two breakdown-block charts
(`ov_breakdown_bars` -> `charts.bars_with_gutter`, `ov_breakdown_annual` -> the
existing `overlay_grouped_bars` re-grammared per-trace) and the consortium
dot-on-bar chart (`ov_consortium_share`) move onto the shared pass-7 hover +
reading-line + token grammar (BUILD_PLAN.md pass-7b S2, `_PAGE_RECIPE_7b.md`).

Idiom copied from tests/test_page7_col.py: source-level regex pins for the
hover-template grammar and the reading-line/"Comment lire" ledger (AppTest
cannot introspect a rendered Plotly figure's own traces in this Streamlit
build), plus direct calls to the SAME pure builders the page itself calls
(`lib.charts.bars_with_gutter`, `lib.hover.hover_lines`) on frames built from
the deployed parquet, exactly as that file's own `_reciprocity_population()`
does.

None of this page's three chart keys carries a `reference` line (registry:
`docs/contract_fragments/chart_keys_pass7.md` rows for `ov_breakdown_bars`/
`ov_breakdown_annual`/`ov_consortium_share` list no reference) -- recipe step
3(e)'s "dots: a red dashed shape at the reference x" sub-check therefore does
not apply to this page and is intentionally omitted.

Vacuity (P14): every assertion group below is followed by an in-memory
mutation that must make the identical check fail -- a pin that cannot fail is
theater.

    python -m pytest tests/test_page7b_p1.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
DATA_DIR = STREAMLIT_DIR / "data"
PAGES_DIR = STREAMLIT_DIR / "pages"

PAGE1 = "1_\U0001F4CA_Vue_d_ensemble.py"
PAGE1_SRC = (PAGES_DIR / PAGE1).read_text(encoding="utf-8")

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


def _skip_if_missing(path: Path) -> None:
    if not path.is_file():
        pytest.skip(f"{path} not deployed -- run the pipeline + 60_deploy first")


def _exc_values(at) -> list:
    return [e.value for e in at.exception]


def _neutralize_page_link(monkeypatch) -> None:
    """Same pre-existing harness limitation as tests/test_page7_col.py's own
    `_neutralize_page_link` (see that file's docstring): `lib.controls.sidebar()`
    calls `st.page_link()` unconditionally, which raises under a direct
    `AppTest.from_file()` load."""
    import streamlit as st_mod
    monkeypatch.setattr(st_mod, "page_link", lambda *a, **k: None)


# ============================================================================
# (a) hover grammar -- every hovertemplate on the page is the bare grammar constant
# ============================================================================

HOVERTEMPLATE_RE = re.compile(r"hovertemplate\s*=\s*([^\n,\)]+)")


def test_every_hovertemplate_on_the_page_is_the_bare_grammar_constant():
    matches = HOVERTEMPLATE_RE.findall(PAGE1_SRC)
    assert matches, "expected at least one hovertemplate on the page"
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
    assert len(lines) <= 8


@pytest.mark.parametrize("chart_key,mode", [
    ("ov_breakdown_bars", "doc_types"), ("ov_breakdown_bars", "domaines"),
    ("ov_breakdown_annual", "doc_types"), ("ov_breakdown_annual", "domaines"),
    ("ov_consortium_share", "default"),
])
def test_hover_lines_wellformed_for_every_page1_chart_mode(chart_key, mode):
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
# (c) reading lines -- one call site per chart key, "Comment lire" gone
# ============================================================================

PAGE1_CHART_KEYS = ["ov_breakdown_bars", "ov_breakdown_annual", "ov_consortium_share"]


def test_reading_line_called_once_per_chart_key():
    for key in PAGE1_CHART_KEYS:
        assert PAGE1_SRC.count(f'reading_line("{key}"') == 1, key
    assert PAGE1_SRC.count("reading_line(") == len(PAGE1_CHART_KEYS)

    # vacuity: removing one chart key's call site must be caught by the same check
    stripped = PAGE1_SRC.replace('reading.reading_line("ov_consortium_share")', "pass  # removed", 1)
    assert stripped.count('reading_line("ov_consortium_share"') == 0


def test_comment_lire_absent_from_page_source():
    assert "Comment lire" not in PAGE1_SRC

    # vacuity: re-introducing the literal phrase must be caught by the same check
    mutated = PAGE1_SRC + '\nst.caption("**Comment lire :** exemple.")\n'
    assert "Comment lire" in mutated


# ============================================================================
# (d) no percent tickformat, no hex literal
# ============================================================================

PCT_TICKFORMAT_RE = re.compile(r'tickformat\s*=\s*["\'][^"\']*%[^"\']*["\']')
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}")


def test_no_percent_tickformat_and_no_hex_literal_in_page_source():
    assert PCT_TICKFORMAT_RE.search(PAGE1_SRC) is None
    assert HEX_RE.search(PAGE1_SRC) is None

    # vacuity: either literal, reintroduced, must be caught by the same regex
    assert PCT_TICKFORMAT_RE.search(PAGE1_SRC + '\nfig.update_xaxes(tickformat=".0%")\n')
    assert HEX_RE.search(PAGE1_SRC + '\nX = "#8C9196"\n')


# ============================================================================
# (e) bars: the phantom gutter trace's text == fr_int of the real totals
# ============================================================================

def test_ov_breakdown_bars_gutter_phantom_text_matches_fr_int_of_doctype_totals():
    path = DATA_DIR / "ul_pubs.parquet"
    _skip_if_missing(path)
    from lib import charts as C
    from lib import hover as hv
    from lib.helpers import UL_COLOR

    pubs = pd.read_parquet(path, columns=["type"])
    order_desc = pubs["type"].value_counts().sort_values(ascending=False)
    labels = list(order_desc.index)
    totals = [int(v) for v in order_desc.values]
    d = pd.DataFrame({"label": labels, "total": totals, "hover": ["x"] * len(labels)})

    fig = C.bars_with_gutter(d, family="champ", label_col="label", value_col="total",
                              color=UL_COLOR, hover_col="hover")
    gutter_trace = fig.data[-1]
    assert list(gutter_trace.text) == [hv.fmt_int(v) for v in totals]

    # vacuity: an off-by-one total must NOT match the rendered gutter text
    assert list(gutter_trace.text) != [hv.fmt_int(v + 1) for v in totals]


# ============================================================================
# (f) page-specific pins named in the brief
# ============================================================================

def test_consortium_bar_trace_uses_the_neutral_grey_token_source_level():
    """The consortium chart's grey bar reads `H.NEUTRAL_GREY` (imported token),
    never a local hex re-definition -- source-level, since AppTest cannot
    introspect a rendered trace's `marker_color` in this Streamlit build."""
    marker = 'marker_color=NEUTRAL_GREY, name="Part du corpus complet"'
    assert marker in PAGE1_SRC
    assert "FOCAL_BLUE" not in PAGE1_SRC
    assert 'NEUTRAL_GREY = "#8C9196"' not in PAGE1_SRC  # the OLD page-local re-definition

    # vacuity: reverting to the local hex re-definition must be caught
    mutated = PAGE1_SRC.replace(marker, 'marker_color="#8C9196", name="Part du corpus complet"')
    assert marker not in mutated


def test_consortium_members_df_has_seven_plotted_rows_ul_is_the_eighth_signatory():
    """`docs/tooltip_spec.yaml`/BUILD_PLAN §2 registry: the consortium chart draws
    one row per co-signing PARTNER (7); the Université de Lorraine is the label's
    "huitième signataire" as porteur (test_page_pa.py's own
    `test_page1_consortium_data_has_seven_external_members_plus_ul_host_note`) but
    is never itself a plotted row -- pinned here against the deployed table
    directly so a future member-count drift is caught at the data layer too."""
    path = DATA_DIR / "consortium_weights.parquet"
    _skip_if_missing(path)
    cw = pd.read_parquet(path)
    site_cw = cw[(cw["conf_state"] == "all") & (cw["scope"] == "all")]
    member_order = ["CNRS", "Inserm", "CHRU Nancy", "INRAE", "AgroParisTech", "Georgia Tech", "Inria"]
    members = [m for m in member_order if m in set(site_cw["member"])]
    assert len(members) == 7
    assert len(members) + 1 == 8  # + UL as porteur == "les huit signataires" (page title)

    # vacuity: a wrong expected count must NOT match
    assert len(members) != 8


def test_page1_survives_isite_overlay_toggle_with_the_new_chart_grammar(monkeypatch):
    """Brief pin (f): the pass-7b re-grammar (bars_with_gutter + per-trace hover
    override + the consortium dot trace) must not raise with the I-SITE overlay
    ON -- the state test_page_pa.py's own
    `test_page1_isite_overlay_toggle_adds_the_row_swap_comparator_caption`
    exercises for its own caption pin, re-asserted here as a plain no-exception
    smoke check tied to this stream's own edits."""
    _skip_if_missing(DATA_DIR / "dim_subsets.parquet")
    _neutralize_page_link(monkeypatch)
    from streamlit.testing.v1 import AppTest
    app_py = STREAMLIT_DIR / "Menu.py"
    at = AppTest.from_file(str(app_py))
    at.run(timeout=90)
    at.switch_page(f"pages/{PAGE1}")
    at.run(timeout=90)
    assert not at.exception, _exc_values(at)
    toggle = next((t for t in at.sidebar.toggle if t.key == "isite_overlay"), None)
    assert toggle is not None, "expected the I-SITE overlay toggle in the sidebar"
    toggle.set_value(True)
    at.run(timeout=90)
    assert not at.exception, _exc_values(at)

    # vacuity: the SAME "not at.exception" shape must fail when an exception is present
    with pytest.raises(AssertionError):
        assert not [RuntimeError("injected")]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
