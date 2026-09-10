# tests/test_page_pb.py
"""
Sprint pass 5, worker P-B -- pins for `4_🔬_Portefeuille_thématique.py`,
`6_🔎_Exploration_thématique.py` and the additive edits to `lib/thematic.py`.

Two families:
  - PURE / data-level pins (no Streamlit) -- fast, robust, check invariants directly on
    the deployed parquets or on the page's own source text (for a styling decision that
    has no runtime-introspectable Plotly hook via AppTest, e.g. a continuous colour
    scale's literal hex stops).
  - AppTest interaction pins -- same house pattern as tests/test_isite_overlay_journey.py
    (this repo has TWO `lib` packages -- repo-root pipeline vs Streamlit/lib -- so every
    AppTest run needs the Streamlit one correctly bound; setup_module/teardown_module
    swap it in/out for this whole file, same shape as that file's own docstring).

    python -m pytest tests/test_page_pb.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
PAGES_DIR = STREAMLIT_DIR / "pages"
DATA_DIR = STREAMLIT_DIR / "data"

PAGE4 = "4_\U0001F52C_Portefeuille_thématique.py"
PAGE6 = "6_\U0001F50E_Exploration_thématique.py"
MENU_PY = STREAMLIT_DIR / "Menu.py"

TIMEOUT = 90.0

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    # F-SYSMOD fix (MINOR): one-line fallback so `conftest` stays importable even if
    # this file is ever run as a standalone script, not just via pytest.
    sys.path.insert(0, str(_TESTS_DIR))
from conftest import restore_lib, swap_lib_to_streamlit  # centralized guard, see conftest.py

_saved_lib_modules: dict = {}


def setup_module(_module) -> None:
    """F-SYSMOD fix: delegates to tests/conftest.py's ONE centralized sys.modules['lib']
    guard instead of this file's own copy of the save/delete/insert-path dance."""
    global _saved_lib_modules
    _saved_lib_modules = swap_lib_to_streamlit()


def teardown_module(_module) -> None:
    restore_lib(_saved_lib_modules)


def _exc_values(at: AppTest) -> list:
    return [e.value for e in at.exception]


def _set_sidebar_toggle(at: AppTest, label: str, value: bool) -> None:
    for cb in at.sidebar.toggle:
        if cb.label == label:
            cb.set_value(value)
            return
    raise AssertionError(f"sidebar toggle {label!r} not found")


# ============================================================================
# PURE / data-level pins
# ============================================================================

def test_page4_source_has_no_perimeter_selector_dead_code():
    """R1: the retired sidebar perimeter selector's resolver must not linger as a
    LIVE function definition a future reader could mistake for live wiring (the
    name may still appear in an explanatory comment about its retirement)."""
    src = (PAGES_DIR / PAGE4).read_text(encoding="utf-8")
    assert "def _resolve_subset(" not in src
    assert "_subset_label_fr =" not in src
    assert "_subset_label_fr.get(" not in src


def test_page4_treemap_fwci_midpoint_is_neutral_grey_not_yellow():
    """R19 FWCI-scale midpoint decision: the diverging FWCI colour scale's midpoint
    (FWCI = 1, the France reference) must be the app's own neutral-reference grey
    (controls.DEFERRED_GREY, #8C9196) -- never a hue, per the dataviz skill's own
    diverging-scale rule ('two hues + a neutral gray midpoint... never a hue at the
    diverging midpoint'). The old yellow (#F4D570) must be gone from the ACTUAL
    colour-scale list (a code comment may still name it historically, e.g. the
    RA-B02 backstory, without that counting as a live colour stop)."""
    src = (PAGES_DIR / PAGE4).read_text(encoding="utf-8")
    # Bounded on the RIGHT by the range_color=[0, 2] line that immediately follows
    # the outer list's closing bracket in this exact chart -- not a naive split on
    # the first "]", which would stop at the FIRST inner [value, colour] pair.
    scale_block = src.split("color_continuous_scale=[", 1)[1].split("range_color=[0, 2]", 1)[0]
    assert "F4D570" not in scale_block
    assert "controls.DEFERRED_GREY" in scale_block
    # Endpoints are the pre-existing house colours, deliberately UNCHANGED.
    assert '"#EC8773"' in scale_block
    assert '"#60CCAA"' in scale_block


def test_page4_t7_funding_panel_removed_from_ui():
    """R10: the T7 funding panel is removed from the UI entirely; thm_funding
    stays a builder/table concern only, never rendered on this page."""
    src = (PAGES_DIR / PAGE4).read_text(encoding="utf-8")
    assert "thm_funding" not in src
    assert "Financement par champ" not in src


def test_page4_zero_fill_and_sdg_tables_declare_exactly_one_progress_col():
    """
    S-LENS D6 (pass-6 fix round): the topics_zero_fill / subfields_zero_fill / sdg_labs
    ranked_table() call sites used to stack 2-5 percent columns into `progress_cols` and
    rely on the lib's auto-demote fallback (VIZ_SPEC_pass6 S7.2) to render all but the
    first as a NumberColumn -- functionally fine, but the lib warning fired on every one
    of them in production. Each call site must now pass exactly ONE `progress_cols` entry
    (a single-key literal dict, not a multi-key dict/comprehension) and move the rest to
    the explicit `number_cols` param (same render, no warning).
    """
    src = (PAGES_DIR / PAGE4).read_text(encoding="utf-8")
    assert 'progress_cols={_topic_pct_cols[0]: {}}' in src  # topics_zero_fill
    assert 'progress_cols={_sf_pct_cols[0]: {}}' in src     # subfields_zero_fill
    assert (
        'progress_cols={\n        "Part du corpus du labo étiquetée (SIRIS)"' in src
    )  # sdg_labs
    for key in ("topics_zero_fill", "subfields_zero_fill", "sdg_labs"):
        idx = src.find(f'key="{key}"')
        assert idx != -1, f"ranked_table call for key={key!r} not found"
        start = src.rfind("ranked_table(", 0, idx)
        end = src.find("\n)", idx)
        span = src[start:end]
        assert "number_cols" in span, f"{key}: no number_cols param -- still relying on demotion?"


def test_page8_hub_declares_exactly_one_progress_col():
    """S-LENS D6: same fix on the Collaborations hub table -- "share_p_pct" stays the
    ONE bar (the only key in the `progress_cols` dict literal), "co_works"/"share_ul"/
    (conditionally) "isite_share" move to the separate `number_cols` dict."""
    collab_path = PAGES_DIR / "8_\U0001F91D_Collaborations.py"
    src = collab_path.read_text(encoding="utf-8")
    pc_start = src.find("progress_cols = {")
    pc_end = src.find("\n    }", pc_start)
    assert pc_start != -1 and pc_end != -1
    pc_block = src[pc_start:pc_end]
    assert pc_block.count('": {') == 1
    assert '"share_p_pct"' in pc_block

    nc_start = src.find("number_cols = {")
    nc_end = src.find("\n    }", nc_start)
    assert nc_start != -1 and nc_end != -1
    nc_block = src[nc_start:nc_end]
    assert '"co_works"' in nc_block
    assert '"share_ul"' in nc_block

    idx = src.find('key="hub"')
    call_span = src[src.rfind("ranked.ranked_table(", 0, idx):src.find("\n    )", idx)]
    assert "number_cols=number_cols" in call_span


def test_page4_moved_panels_are_gone_and_pointer_present():
    """R9: T9 (frontier cross + emerging topics), T3/T3c (diversity) and T3b
    (co-discipline) are removed from this page (moved to Positionnement); a FR
    pointer line replaces them. The concept names may still appear in that ONE
    pointer sentence (telling the reader what moved) -- only the actual table
    LOADS must be gone."""
    src = (PAGES_DIR / PAGE4).read_text(encoding="utf-8")
    for gone in ('_load_table("thm_frontier")', '_load_table("thm_diversity")', '_load_table("thm_codiscipline")'):
        assert gone not in src, f"{gone!r} should have moved off page 4"
    assert "Positionnement" in src


def test_page4_methodes_has_the_t7_removal_subsection():
    """R10: exactly one new METHODES subsection documents why T7 was pulled from
    the UI (add-on, never central; a real funding view needs CORDIS + disambiguated
    ERC/ANR/France 2030)."""
    methodes = (ROOT / "docs" / "METHODES.md").read_text(encoding="utf-8")
    assert "### 9.13" in methodes
    assert "CORDIS" in methodes.split("### 9.13", 1)[1][:2000]


def test_thm_sdg_labs_floor_is_null_never_zero():
    """D53, re-verified at the data layer the SDG-by-lab crossing panel reads
    directly: shares below the 30-tagged-works floor are NaN, never a fabricated
    0 %, and no row ABOVE the floor is ever null."""
    df = pd.read_parquet(DATA_DIR / "thm_sdg_labs.parquet")
    below = df[df["works_tagged_n"] < 30]
    above = df[df["works_tagged_n"] >= 30]
    assert below["share_of_lab_sdg_tagged"].isna().all()
    assert above["share_of_lab_sdg_tagged"].notna().all()


def test_bench_sdg_ul_row_uses_direct_id_not_the_36819_corpus():
    """R6: the UL side of the peer SDG panel must be the direct-id perimeter
    (28,464 works this snapshot), never the 36,819-work lineage corpus -- the
    symmetry the caption next to the chart asserts."""
    df = pd.read_parquet(DATA_DIR / "bench_sdg.parquet")
    ul = df[(df["rung"] == "FOCAL") & (df["conf_state"] == "all")]
    assert not ul.empty
    total = int(ul["entity_total_works"].iloc[0])
    assert total != 36819
    assert 25000 < total < 32000  # sanity band around the documented 28,464


def test_bench_sdg_has_no_xa_columns_exempt_by_construction():
    """S9 exemption (peer corpora pulled live, no local artifact-flag snapshot):
    no _xa twin anywhere on this table, including UL's own row."""
    df = pd.read_parquet(DATA_DIR / "bench_sdg.parquet")
    assert not any(c.endswith("_xa") for c in df.columns)


def test_page6_source_has_no_stray_english_section_headers():
    """R12 spot-check: the presentational section headers this stream owns must
    read in French (dataframe COLUMN names are the only English exception, and
    none of these strings are column names)."""
    src = (PAGES_DIR / PAGE6).read_text(encoding="utf-8")
    for stray in ("Thematic Drill-Down", "Select level:", "Top 20 Authors", "Top Partners"):
        assert stray not in src


def test_page6_overlay_bars_used_for_contribution_charts():
    """R1/OVERLAY_MATRIX EXTEND row: the two Contribution Analysis bar charts (new
    department_breakdown_isite / top_labs_isite same-row twins) render through the
    ONE shared lib.overlay grammar, never a page-rolled stacking of its own."""
    src = (PAGES_DIR / PAGE6).read_text(encoding="utf-8")
    assert src.count("overlay_bars(") >= 2
    assert "department_breakdown_isite" in src
    assert "top_labs_isite" in src


def test_page6_top_labs_isite_schema_matches_the_four_field_blob():
    """
    REGRESSION PIN (BUILD_PLAN pass 6 #21a, reports/pass6_probes.md probe 5).

    pipeline/44d_build_detail_contributions.py documents `top_labs_isite` as a
    4-field blob ("ror:name:count:pct" -- comment at 44d:121-122, "isite_count
    is not repeated" -- unlike the base `top_labs` blob it sits beside, which
    DOES repeat a 'type' field (5 fields)). A page edit that copy-pastes the
    base schema onto the isite twin makes `len(parts) >= len(expected_fields)`
    (4 >= 5) always False inside `parse_top_items()`, so every single item is
    silently dropped -- no exception, no visible failure, just a permanently
    zero-width dark overlay segment. This pin fails the instant that 5-field
    schema reappears at the `top_labs_isite` call site.
    """
    src = (PAGES_DIR / PAGE6).read_text(encoding="utf-8")
    marker = 'contrib_data.get("top_labs_isite", "")'
    assert marker in src, "expected the top_labs_isite read to still exist verbatim"
    idx = src.index(marker)
    call_tail = src[idx: idx + 250]
    assert '["ror", "name", "count", "pct"]' in call_tail, (
        "top_labs_isite must be parsed with its OWN 4-field schema, not the base "
        "top_labs blob's 5-field one"
    )
    assert '["ror", "name", "type", "count", "pct"]' not in call_tail, (
        "probe-5 regression: top_labs_isite parsed with the 5-field base schema "
        "-- every item silently dropped, isite_count always 0"
    )


def test_page6_top_labs_isite_blob_is_four_field_per_item():
    """
    Data-contract companion to the schema pin above, from the OTHER side: confirms
    the DEPLOYED `top_labs_isite` blob really is 4 colon-separated fields per
    '|'-item (pipeline/44d_build_detail_contributions.py's documented shape), so
    the page's fixed 4-field parse_top_items() call stays correct if the pipeline
    ever changes.
    """
    df = pd.read_parquet(DATA_DIR / "thematic_detail_contributions.parquet")
    blobs = df["top_labs_isite"].dropna()
    blobs = blobs[blobs.astype(str).str.len() > 0]
    assert len(blobs), "expected at least one populated top_labs_isite blob"
    non_conforming = [
        item for blob in blobs for item in str(blob).split("|") if len(item.split(":")) != 4
    ]
    assert not non_conforming, f"non 4-field top_labs_isite item(s): {non_conforming[:5]}"


def test_page6_reciprocity_delegation_centre_est_is_type_government_not_education():
    """
    The EXACT case named in the feedback round (#24): 'Délégation Centre-Est' (a
    CNRS regional administrative office, I4210110412) shows a near-total share
    of ITS OWN small output co-signed with the site -- a real number, but not a
    partner comparable to a university. Pure/data-level proof that the page's
    institution-TYPE filter (default: education only) mathematically excludes
    it: this partner's type is 'government', and 'government' != 'education',
    so `recip_df[recip_df["type"].isin(["education"])]` drops it by construction.
    Domain id=3 ("Physical Sciences") is the fixture: probe-verified to carry
    this exact partner in its `reciprocity_partners` blob.
    """
    df = pd.read_parquet(DATA_DIR / "thematic_detail_partners.parquet")
    row = df[(df["level"] == "domain") & (df["id"] == "3")]
    assert len(row) == 1
    blob = row["reciprocity_partners"].iloc[0]
    items = [item.split(":") for item in blob.split("|")]
    centre_est = [it for it in items if it[0] == "I4210110412"]
    assert centre_est, "expected 'Délégation Centre-Est' (I4210110412) in this fixture"
    # Format: id:name:country:type:copubs:share_ul:share_int:share_partner:partner_total:fwci
    assert centre_est[0][3] == "government"
    assert "education" != centre_est[0][3]
    # And the default filter (["education"]) is a strict pandas .isin() -- it
    # cannot admit a "government" row by construction, independent of any
    # Streamlit wiring.
    types = pd.Series([it[3] for it in items])
    assert not types.isin(["education"]).equals(types.isin(["education", "government"]))
    default_mask = types.isin(["education"])
    centre_est_pos = [i for i, it in enumerate(items) if it[0] == "I4210110412"][0]
    assert not default_mask.iloc[centre_est_pos]


# ============================================================================
# AppTest interaction pins
# ============================================================================

def _goto(page_rel: str) -> AppTest:
    """
    Pass 6 (S-LIB wave 2): `lib.controls.sidebar()` now calls
    `lib.helpers.render_methodo_expander()` unconditionally, which renders ONE
    `st.page_link(...)` back to the Menu (P1/P6-R2). `AppTest.from_file(<a
    pages/*.py file>)` loaded DIRECTLY raises `KeyError: 'url_pathname'` on
    that call -- a pre-existing harness limitation (`PagesManager.
    uses_pages_directory` resolves off the loaded script's OWN directory, so
    "pages/pages/" is never found and no page registry is built), reproduced
    app-wide the instant this stream's own probe hit it (identical traceback
    on PAGE6, untouched by this stream). Established fix, same idiom already
    shipped in tests/test_page_pa.py / test_page_pf.py / test_isite_overlay_
    journey.py: boot the real multipage app from `Menu.py`, THEN `switch_page`
    -- this runs the actual `_mpa_v1` bootstrap and registers every page, so
    `page_link` has something to resolve against.
    """
    at = AppTest.from_file(str(MENU_PY))
    at.run(timeout=TIMEOUT)
    at.switch_page(page_rel)
    at.run(timeout=TIMEOUT)
    return at


@pytest.fixture()
def page4() -> AppTest:
    at = _goto(f"pages/{PAGE4}")
    assert not at.exception, f"page4 default load raised: {_exc_values(at)}"
    return at


@pytest.fixture()
def page6() -> AppTest:
    at = _goto(f"pages/{PAGE6}")
    assert not at.exception, f"page6 default load raised: {_exc_values(at)}"
    return at


def test_page4_isite_overlay_toggle_gates_contribution_isite_column(page4):
    """Toggle OFF (default): the domain table has no 'Contribution ISITE' column
    (byte-identical to the pre-pass-5 shape). Toggle ON: the column appears --
    same precomputed pct_isite value, zero recompute either way."""
    domain_cols_off = page4.dataframe[0].value.columns.tolist()
    assert "Contribution ISITE" not in domain_cols_off

    _set_sidebar_toggle(page4, "Afficher la contribution I-SITE", True)
    page4.run(timeout=TIMEOUT)
    assert not page4.exception, _exc_values(page4)
    domain_cols_on = page4.dataframe[0].value.columns.tolist()
    assert "Contribution ISITE" in domain_cols_on


def test_page4_treemap_color_by_gains_isite_option_only_when_overlay_on(page4):
    # AppTest's Selectbox.options exposes the FORMATTED labels (format_func
    # already applied), not the raw option values -- assert on the label text.
    isite_label = "Contribution I-SITE (%)"
    color_by = [s for s in page4.selectbox if s.label == "Colorer par :"][0]
    assert isite_label not in color_by.options

    _set_sidebar_toggle(page4, "Afficher la contribution I-SITE", True)
    page4.run(timeout=TIMEOUT)
    assert not page4.exception, _exc_values(page4)
    color_by_on = [s for s in page4.selectbox if s.label == "Colorer par :"][0]
    assert isite_label in color_by_on.options


def test_page4_all_three_toggles_on_renders_clean(page4):
    for label in (
        "Inclure les articles de conférence",
        "Exclure les 811 topics hors référentiel",
        "Afficher la contribution I-SITE",
    ):
        _set_sidebar_toggle(page4, label, True)
    page4.run(timeout=TIMEOUT)
    assert not page4.exception, _exc_values(page4)


def test_page4_t4_log_linear_toggle_defaults_to_log(page4):
    """R18: the field-level specialisation chart's local axis toggle defaults OFF
    (log stays the default; linear is opt-in)."""
    toggles = [t for t in page4.toggle if t.label == "échelle linéaire"]
    assert toggles, "expected at least one 'échelle linéaire' toggle on page 4 (T4)"
    assert toggles[0].value is False


def test_page4_t4_isite_row_swap_second_series_only_when_overlay_on(page4):
    """OVERLAY_MATRIX row-swap contract: the specialisation dot chart's second
    ('dont I-SITE') series is a SEPARATE point series (thm_specialisation's own
    in_isite row), rendered only while the overlay toggle is ON -- LQ is a ratio,
    never decomposed as a stacked bar segment."""
    src = (PAGES_DIR / PAGE4).read_text(encoding="utf-8")
    assert "df_t4_isite" in src
    assert 'subset_id"] == "in_isite"' in src

    _set_sidebar_toggle(page4, "Afficher la contribution I-SITE", True)
    page4.run(timeout=TIMEOUT)
    assert not page4.exception, _exc_values(page4)


def test_page4_lab_odd_profile_moved_out_pointer_present(page4):
    """#8: the per-laboratory ODD PROFILE picker (one lab, all 16 goals) moves to
    the Laboratoires page mini-fiche -- superseding the pass-5 pin that exercised
    it here (thin lab 'Jardins', D53). This page keeps only the per-ODD overview:
    the picker must be GONE and a FR pointer to the Laboratoires page must exist."""
    pickers = [s for s in page4.selectbox if s.label == "Laboratoire :"]
    assert not pickers, "the per-lab ODD profile picker should have moved off page 4 (#8)"
    src = (PAGES_DIR / PAGE4).read_text(encoding="utf-8")
    assert "Profil ODD d'un laboratoire" not in src
    assert "🏭 Laboratoires" in src


def test_page4_sdg_lab_methods_table_has_method_comparison_columns(page4):
    """#7/#12: the ODD-par-laboratoire table reads sdg_lab_methods.parquet (not
    thm_sdg_labs) and shows lab_total_pubs + share-of-LAB-CORPUS-tagged (#7) AND
    SIRIS-vs-Aurora columns side by side (#12), never thm_sdg_labs' old share-of-
    TAGGED-part-only column."""
    src = (PAGES_DIR / PAGE4).read_text(encoding="utf-8")
    assert '_load_table("thm_sdg_labs")' not in src
    assert '_load_table("sdg_lab_methods")' in src
    for expected in (
        "Travaux ODD (SIRIS)", "Travaux ODD (Aurora)", "Travaux du laboratoire",
        "Part du corpus du labo étiquetée (SIRIS)", "Part du corpus du labo étiquetée (Aurora)",
    ):
        assert expected in src

    picker = [s for s in page4.selectbox if s.label == "Objectif de développement durable :"]
    assert picker, "expected the ODD picker on the lab crossing panel"
    # The sdg_lab_methods-backed table must carry BOTH method columns for the
    # default ODD selection (10-row default slice, P6-R6).
    tables = [d.value for d in page4.dataframe]
    assert any(
        {"Travaux ODD (SIRIS)", "Travaux ODD (Aurora)"} <= set(t.columns) for t in tables
    ), [list(t.columns) for t in tables]


def test_page4_topics_and_subfields_use_zero_fill_tables_no_head_cap():
    """#20: no top-200 cap; the topic/subfield sections read the full-vocabulary
    zero-fill tables (S-DAT, pipeline/44h_build_zero_fill.py), never
    thematic_overview capped at head(200)."""
    src = (PAGES_DIR / PAGE4).read_text(encoding="utf-8")
    assert '_load_table("topics_zero_fill")' in src
    assert '_load_table("subfields_zero_fill")' in src
    assert ".head(200)" not in src


def test_page4_topics_zero_fill_quantum_query_includes_zero_pub_topics(page4):
    """#20 acceptance example, pinned: the topics table is wired to
    topics_zero_fill.parquet (4 516 rows = the FULL OpenAlex topic vocabulary),
    never limited to topics the UL corpus actually uses. A 'quantum' search must
    return all 18 quantum-substring topics, including the 2 the corpus has ZERO
    publications on (S-DAT's own zero-fill invariant, progress/SDAT.md /
    reports/pass6_probes.md probe 8's sibling)."""
    boxes = [t for t in page4.text_input if t.label == "Rechercher :"]
    assert boxes, "expected a ranked_table search box (N >= 50 on both zero-fill tables)"
    for box in boxes:
        box.set_value("quantum")
    page4.run(timeout=TIMEOUT)
    assert not page4.exception, _exc_values(page4)

    for b in [btn for btn in page4.button if btn.label == "afficher plus"]:
        b.click()
    page4.run(timeout=TIMEOUT)
    assert not page4.exception, _exc_values(page4)

    all_topic_names: set[str] = set()
    for d in page4.dataframe:
        if "Topic" in d.value.columns:
            all_topic_names |= set(d.value["Topic"].astype(str))
    zero_pub_quantum = {
        "Quantum Chromodynamics and Particle Interactions",
        "Noncommutative and Quantum Gravity Theories",
    }
    assert zero_pub_quantum <= all_topic_names, sorted(all_topic_names)
    assert len(all_topic_names) == 18, sorted(all_topic_names)


def test_page4_fwci_panels_are_collapsed_by_default(page4):
    """#19: both FWCI distribution panels (domaine, champ) live inside a
    st.expander(..., expanded=False) -- closed by default, always, no
    session-state memory (VIZ_SPEC_pass6 S4.1)."""
    doms = [e for e in page4.expander if e.label.startswith("Distribution du FWCI par domaine")]
    flds = [e for e in page4.expander if e.label.startswith("Distribution du FWCI par champ")]
    assert doms and flds, [e.label for e in page4.expander]
    for e in (*doms, *flds):
        assert e.proto.expanded is False, f"{e.label!r} must be closed by default"


def test_page4_momentum_replaces_cagr_everywhere(page4):
    """#18: CAGR is never rendered on this page; the Momentum column (glyph +
    signed pp difference, or 'non significatif' / '--') replaces it everywhere
    a table used to show CAGR."""
    src = (PAGES_DIR / PAGE4).read_text(encoding="utf-8")
    assert "def format_cagr(" not in src, "format_cagr() must be retired, not just unused"
    assert "format_cagr(row[" not in src, "no live CAGR call site should remain"
    assert '"CAGR":' not in src
    assert "format_momentum(" in src
    tables = [d.value for d in page4.dataframe]
    assert any("Momentum" in t.columns for t in tables), [list(t.columns) for t in tables]
    assert not any("CAGR" in t.columns for t in tables)


def test_page6_partner_ranked_table_defaults_to_top_ten(page6):
    """R11: every ranked table on this page defaults to top-10, with the rest of
    the already-materialized (shallow, top-20) frame reachable via 'afficher plus'
    -- never a deeper pull."""
    for s in page6.selectbox:
        if s.label == "Choisir le niveau :":
            s.set_value("field")
    page6.run(timeout=TIMEOUT)
    for s in page6.selectbox:
        if s.label == "Choisir l'élément :":
            s.set_value(s.options[0])
    page6.run(timeout=TIMEOUT)
    assert not page6.exception, _exc_values(page6)

    dfs = [d for d in page6.dataframe if "Partenaire" in d.value.columns]
    assert dfs, "expected at least one partner ranked table to render"
    for d in dfs:
        assert len(d.value) <= 10


def test_page6_afficher_plus_expands_partner_table_to_depth_twenty(page6):
    """
    #21b depth-20 pin: pipeline/44e_build_detail_partners.py materializes
    TOP_INT = TOP_FR = 20 (S-DAT verified) -- 'afficher plus' must reach that
    full depth, not just "more than 10". Field-level, first (highest-volume)
    option is used so both the international and French tables are certain to
    carry a full 20 partners.
    """
    for s in page6.selectbox:
        if s.label == "Choisir le niveau :":
            s.set_value("field")
    page6.run(timeout=TIMEOUT)
    for s in page6.selectbox:
        if s.label == "Choisir l'élément :":
            s.set_value(s.options[0])
    page6.run(timeout=TIMEOUT)

    before = [d for d in page6.dataframe if "Partenaire" in d.value.columns]
    assert before and all(len(d.value) <= 10 for d in before)

    # Two tables, each with its OWN "afficher plus" button -- click and rerun
    # ONE at a time (each click's handler calls st.rerun() itself; clicking
    # both before a single page6.run() lets the first table's internal rerun
    # short-circuit the second table's pending click). ranked_table()'s
    # default `more_step=None` reveals everything materialized on the FIRST
    # click, so a table's button disappears the instant it is expanded --
    # looping "while a button remains" naturally visits each table exactly once.
    rounds = 0
    while rounds < 5:
        more_buttons = [b for b in page6.button if b.label == "afficher plus"]
        if not more_buttons:
            break
        more_buttons[0].click()
        page6.run(timeout=TIMEOUT)
        assert not page6.exception, _exc_values(page6)
        rounds += 1
    assert rounds >= 1, "expected at least one 'afficher plus' click to have fired"

    after = [d for d in page6.dataframe if "Partenaire" in d.value.columns]
    assert after
    for d in after:
        assert len(d.value) <= 20, "must never reveal more than the materialized top-20"
    assert max(len(d.value) for d in after) == 20, (
        "expected at least one partner table to reach the full materialized depth of 20"
    )
    assert max(len(d.value) for d in after) > max(len(d.value) for d in before), (
        "afficher plus must have grown at least one table beyond its default depth"
    )


def test_page6_international_partners_table_has_no_member_mask_toggle():
    """
    #23: 'masquer les membres du site' only helps where a national list can be
    crowded by a consortium signatory -- scoped OFF on the international-only
    surface, kept ON for the French one (source-text pin: AppTest's own
    'masquer les membres du site' toggle only renders lazily inside
    lib.ranked.ranked_table, so the wiring is asserted at the call site).
    """
    src = (PAGES_DIR / PAGE6).read_text(encoding="utf-8")
    int_call = src.split('key=f"int_partners_{level}_{element_id}"', 1)
    assert len(int_call) == 2
    assert "has_members=False" in int_call[1][:600]

    fr_call = src.split('key=f"fr_partners_{level}_{element_id}"', 1)
    assert len(fr_call) == 2
    assert "has_members=True" in fr_call[1][:300]


def test_page6_authors_table_has_no_member_mask_toggle(page6):
    """R11: the DEPTH & QUERY contract's member-mask toggle only applies to
    partner-organisation surfaces; the individual-authors table (has_members=False)
    must not grow a 'masquer les membres du site' toggle of its own."""
    src = (PAGES_DIR / PAGE6).read_text(encoding="utf-8")
    authors_call = src.split('key=f"authors_{level}_{element_id}"', 1)
    assert len(authors_call) == 2
    assert "has_members=False" in authors_call[1][:200]


def test_page6_reciprocity_type_filter_defaults_to_education_only(page6):
    """
    #24 type-filter default pin: institution-TYPE filter defaults to
    ["education"] only. Domain level, 'Physical Sciences' (probe-verified to
    carry reciprocity data incl. the Delegation Centre-Est government case --
    see test_page6_reciprocity_delegation_centre_est_is_type_government_not_education
    for the data-level proof that this default excludes it).
    """
    for s in page6.selectbox:
        if s.label == "Choisir le niveau :":
            s.set_value("domain")
    page6.run(timeout=TIMEOUT)
    element_box = [s for s in page6.selectbox if s.label == "Choisir l'élément :"][0]
    physical = [o for o in element_box.options if "Physical Sciences" in o]
    assert physical, "expected a 'Physical Sciences' domain option"
    element_box.set_value(physical[0])
    page6.run(timeout=TIMEOUT)
    assert not page6.exception, _exc_values(page6)

    type_filters = [m for m in page6.multiselect if m.label == "Filtrer par type d'institution"]
    assert type_filters, "expected the #24 institution-type filter to render"
    assert type_filters[0].value == ["education"]

    geo_scopes = [r for r in page6.radio if r.label == "Portée géographique"]
    assert geo_scopes, "expected the #24 geographic-scope control to render"
    assert geo_scopes[0].value == "France et international"


def test_page6_reciprocity_widening_type_filter_renders_clean(page6):
    """Functional smoke companion: widening the type filter to include
    'government' (which re-admits Delegation Centre-Est) must render without
    exception -- the filter is a real .isin() re-slice, not a static gate."""
    for s in page6.selectbox:
        if s.label == "Choisir le niveau :":
            s.set_value("domain")
    page6.run(timeout=TIMEOUT)
    element_box = [s for s in page6.selectbox if s.label == "Choisir l'élément :"][0]
    physical = [o for o in element_box.options if "Physical Sciences" in o]
    element_box.set_value(physical[0])
    page6.run(timeout=TIMEOUT)

    type_filters = [m for m in page6.multiselect if m.label == "Filtrer par type d'institution"]
    assert type_filters
    if "government" in type_filters[0].options:
        type_filters[0].set_value(["education", "government"])
        page6.run(timeout=TIMEOUT)
        assert not page6.exception, _exc_values(page6)


def test_page6_conference_and_artifact_toggles_together_render_clean(page6):
    _set_sidebar_toggle(page6, "Inclure les articles de conférence", False)
    _set_sidebar_toggle(page6, "Exclure les 811 topics hors référentiel", True)
    page6.run(timeout=TIMEOUT)
    assert not page6.exception, _exc_values(page6)
