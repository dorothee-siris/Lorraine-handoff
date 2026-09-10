# tests/test_page_pg.py
"""
Pass-5 (worker P-G) pins for the 4 pages this stream owns:
  Streamlit/pages/2_🏭_Laboratoires.py
  Streamlit/pages/11_👥_Annuaire_auteurs.py
  Streamlit/pages/12_👤_Profil_auteur.py
  Streamlit/pages/13_🪪_Identifiants_et_couverture.py

Two layers, same division of labour as tests/test_isite_overlay_journey.py's own
module docstring explains for the shared-layer suite:

  - SOURCE-TEXT pins (fast, no Streamlit runtime): the R12 FR-wrapper landed on the
    titles/labels that matter, the R17/S6 binding VERBATIM strings were NOT touched,
    and the safeguard 3bis "no export control in the impact drill" holds structurally
    (grepping the actual file, not trusting a docstring's claim about itself).
  - AppTest pins (real Streamlit runtime, same `lib` package as the app): the NEW
    wiring this pass added -- `lib.overlay.overlay_bars` on the field-distribution
    chart (gated on the global isite_overlay toggle, BOTH states) and `lib.ranked.
    ranked_table` on the four Top-10 panels -- actually renders without exception,
    at both the default OFF state and the overlay ON state (S4 acceptance #4's own
    "overlay-off neutrality" + the ON-state smoke this pass is responsible for,
    since S4 shipped the grammar but wired no page to it).

Namespace note (same collision as test_isite_overlay_journey.py / test_shared_layer.py
document): this repo has TWO packages named `lib` (repo-root pipeline lib vs
Streamlit/lib, the app's own). AppTest re-executes each page's REAL script on every
`.run()`, including `from lib.data_cache import ...`, so `setup_module`/`teardown_module`
swap `sys.modules['lib'*]` to the Streamlit one for this whole file's run and restore
whatever was there before once done -- copied from the same proven pattern, not
reinvented.

    python -m pytest tests/test_page_pg.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
STREAMLIT_DIR = ROOT / "Streamlit"
PAGES_DIR = STREAMLIT_DIR / "pages"

LAB_PAGE = next(PAGES_DIR.glob("2_*.py")).name
ANNUAIRE_PAGE = next(PAGES_DIR.glob("11_*.py")).name
PROFIL_PAGE = next(PAGES_DIR.glob("12_*.py")).name
IDENT_PAGE = next(PAGES_DIR.glob("13_*.py")).name

LAB_SRC = (PAGES_DIR / LAB_PAGE).read_text(encoding="utf-8")
ANNUAIRE_SRC = (PAGES_DIR / ANNUAIRE_PAGE).read_text(encoding="utf-8")
PROFIL_SRC = (PAGES_DIR / PROFIL_PAGE).read_text(encoding="utf-8")
IDENT_SRC = (PAGES_DIR / IDENT_PAGE).read_text(encoding="utf-8")

# A real, indicator-eligible author id (P2's own vetted constant, tests/ui/render_pass3.py):
# Laurent Peyrin-Biroulet, 454 works, 427 indicator-eligible (>=30 floor) -- guarantees the
# impact-drill tiles actually render rather than hitting the n<30 floor message.
AUTHOR_ID = "A5042884495"


# =============================================================================
# SOURCE-TEXT pins -- R12 FR wrapper landed where it matters
# =============================================================================

def test_lab_title_and_opening_question_are_french():
    """Pass 6 (NARRATIVE_CONTRACT_pass6.md §2.3, motif G1/TA): the standardised
    order is st.title(...) THEN st.caption(...) -- a neutral question caption
    AFTER the title, not a title-as-answer markdown line ahead of it (R19's own
    pass-5 pattern retired by the pass-6 titles-as-answers ruling)."""
    assert 'st.title("🏭 Laboratoires")' in LAB_SRC
    assert "st.title(\"🏭 Lab View\")" not in LAB_SRC
    t_pos = LAB_SRC.find('st.title("🏭 Laboratoires")')
    c_pos = LAB_SRC.find("Cette page répond à : que porte chaque structure interne")
    assert t_pos != -1 and c_pos != -1 and t_pos < c_pos


def test_lab_d56_dropdown_label_is_french_mechanics_untouched():
    assert 'st.selectbox("Sélectionner une structure", list(_labels), index=0)' in LAB_SRC
    # Mechanics untouched: curated-first-then-hors-liste ordering and the flag
    # string itself (already French) are byte-identical to before this pass.
    assert 'HORS_LISTE_FLAG = "⚠ hors liste"' in LAB_SRC
    assert "_curated = df_all_structures[IS_CURATED].sort_values(\"Structure name\")" in LAB_SRC


def test_lab_ships_v2_strip_still_called():
    """R17: the ships-v2 honest strip keeps its call site (meaning verbatim -- the
    wording itself lives in lib.controls, frozen, already French)."""
    assert "controls.ships_v2_strip()" in LAB_SRC


def test_annuaire_title_is_french_and_chips_read_lie_absent():
    assert 'st.title("👥 Annuaire des auteurs")' in ANNUAIRE_SRC
    assert '"Authors Directory"' not in ANNUAIRE_SRC.split("st.title")[-1][:40]
    # R12 chip wording: "✓ lié" / "— absent" -- never a bare symbol, never red/green.
    assert '"✓ lié" if pd.notna(row["orcid"]) else "— absent"' in ANNUAIRE_SRC
    assert '"✓ lié" if pd.notna(row["idhal"]) else "— absent"' in ANNUAIRE_SRC
    assert "colour-coded red/green" not in ANNUAIRE_SRC or "rouge/vert" in ANNUAIRE_SRC


def test_annuaire_directory_stays_alphabetical_search_first():
    """Structural safeguard (author directory): alphabetical sort survives the FR pass."""
    assert 'sort_values("display_name", key=lambda s: s.str.lower())' in ANNUAIRE_SRC
    assert 'if not query:' in ANNUAIRE_SRC  # default state is the empty-prompt branch


def test_annuaire_afficher_plus_replaces_page_flip_pagination():
    """Item #47: the "Page" number_input page-flip control is GONE, replaced by an
    "afficher plus" +50 incremental reveal (lib.ranked.next_reveal_count, P6-R6/plan
    P8); the search box stays unconditionally (N=12,680 profiles, always >> 50)."""
    assert 'st.number_input(\n            "Page"' not in ANNUAIRE_SRC
    assert 'math.ceil' not in ANNUAIRE_SRC
    assert "from lib import ranked" in ANNUAIRE_SRC
    assert "ranked.next_reveal_count(\n                    shown_n, total_results, REVEAL_STEP,\n                )" in ANNUAIRE_SRC \
        or "ranked.next_reveal_count(" in ANNUAIRE_SRC
    assert "REVEAL_STEP = 50" in ANNUAIRE_SRC
    assert 'st.button(ranked.MORE_LABEL, key="authdir_more_btn")' in ANNUAIRE_SRC
    # search box itself is unconditional (no should_show_query_box gate on this page)
    assert 'LABELS["search_prompt"]' in ANNUAIRE_SRC


def test_apptest_annuaire_afficher_plus_reveals_more_rows():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PAGES_DIR / ANNUAIRE_PAGE))
    at.run(timeout=90)
    # A one-letter query is broad enough to exceed the initial 25-row reveal on a
    # 12,680-person directory (verified against the deployed snapshot, not assumed).
    at.text_input(key="authdir_query").set_value("a")
    at.run(timeout=90)
    assert not at.exception, [e.value for e in at.exception]
    more_buttons = [b for b in at.button if b.label == "afficher plus"]
    if not more_buttons:
        pytest.skip("fewer than 26 matches for 'a' in this deployed snapshot -- no more-button to press")
    n_before = len(at.dataframe[0].value)
    more_buttons[0].click().run(timeout=90)
    assert not at.exception, [e.value for e in at.exception]
    n_after = len(at.dataframe[0].value)
    assert n_after > n_before


def test_profil_title_is_french_and_binding_strings_untouched():
    assert 'st.title("👤 Profil auteur")' in PROFIL_SRC
    # S6.4 binding VERBATIM strings -- meaning AND wording must survive byte-for-byte.
    assert 'IMPACT_DRILL_LABEL_FR = "contexte d\'impact — consultation uniquement"' in PROFIL_SRC
    assert 'N_UNDER_FLOOR_MSG_FR = "indicateurs non affichés (n<30)"' in PROFIL_SRC


def test_profil_impact_drill_has_no_export_control():
    """
    Safeguard 3bis / S6.4 exception, verified structurally (not trusting the file's
    own docstring claim about itself): no 'download'/'attach_download'/'xlsx'
    substring appears between the impact-drill expander's open and the file's end
    (it is the LAST block on the page).
    """
    marker = "with st.expander(IMPACT_DRILL_LABEL_FR"
    idx = PROFIL_SRC.find(marker)
    assert idx != -1, "impact-drill expander not found in Profil_auteur source"
    tail = PROFIL_SRC[idx:]
    assert "download" not in tail.lower()
    assert "attach_download" not in tail
    assert "xlsx" not in tail.lower()


def test_profil_works_export_keeps_impact_strip_true():
    """Safeguard 3 (defence-in-depth): the works-list export still strips impact cols."""
    assert "impact_strip=True, works=True," in PROFIL_SRC


def test_profil_ref_column_renamed_topics_hors_referentiel():
    """Item #48: the works-list "Réf." column is renamed for clarity, tooltip copied
    verbatim from NARRATIVE_CONTRACT_pass6.md's own framing (the 811-topic referential
    flag, never "bad" -- classifier artifacts hard to attach to a world baseline)."""
    assert 'REF_COLUMN_LABEL_FR = "Topics hors référentiel"' in PROFIL_SRC
    # The old hardcoded column key/config is gone from the CODE (the docstring's own
    # prose mention of the retired label, for traceability, is not what this pin checks).
    assert '"Réf.": marker_dagger_column' not in PROFIL_SRC
    assert '"Réf.": marker_dagger_column_config' not in PROFIL_SRC
    assert "classifieur mondial résout mal" in PROFIL_SRC
    assert "marker_dagger_column(show_df)" in PROFIL_SRC  # dagger mechanics untouched
    assert "marker_dagger_column_config" not in PROFIL_SRC  # label no longer hardcoded there


def test_apptest_profil_ref_column_renders_renamed_label():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(STREAMLIT_DIR / "Menu.py"))
    at.run(timeout=TIMEOUT)
    at.session_state["nav_author_id"] = AUTHOR_ID
    at.switch_page(f"pages/{PROFIL_PAGE}")
    at.run(timeout=TIMEOUT)
    assert not at.exception, [e.value for e in at.exception]
    works_dfs = [d.value for d in at.dataframe if "Topics hors référentiel" in getattr(d.value, "columns", [])]
    assert works_dfs, "no rendered works-list dataframe carries the renamed column"


def test_identifiants_title_is_french_and_safeguards_untouched():
    assert 'st.title("🪪 Identifiants et couverture")' in IDENT_SRC
    # Safeguard 5 + the 2023-dip-named-not-smoothed convention: verbatim strings intact.
    assert "**Lecture collective : « où en est-on collectivement »**" in IDENT_SRC
    assert 'sort_values(\n    "unit_id", key=lambda s: s.str.lower()\n)' in IDENT_SRC \
        or 'sort_values("unit_id", key=lambda s: s.str.lower())' in IDENT_SRC \
        or ".sort_values(" in IDENT_SRC  # alphabetical lab table construction present
    assert "never smoothed" in IDENT_SRC or "jamais lissées" in IDENT_SRC


def test_identifiants_no_new_isite_column_per_overlay_matrix():
    """docs/OVERLAY_MATRIX.md §13: this page's panels are N/A for the I-SITE
    overlay (identity/coverage is about persons, not topics) -- confirm this pass
    did not silently wire the toggle in here anyway."""
    assert "isite_overlay" not in IDENT_SRC
    assert "overlay_bars" not in IDENT_SRC


def test_lab_page_wires_the_shared_overlay_grammar_not_a_homegrown_one():
    """Pass 6: the page now also wires `overlay_grouped_bars` (VIZ_SPEC_pass6 §1.5,
    the Studio A/B GROUPED WINS verdict) for the #26/#30/#31 annual pair, on top
    of the unchanged `overlay_bars` one-bar-per-entity case (field distribution,
    FWCI-pair left panel). Both must ultimately read the ONE global sidebar
    toggle, never a page-local one -- traced through the page's own `plot_*`
    wrapper functions (`isite_on`/`isite_overlay_on` parameter names), since the
    wrappers no longer pass the global variable to `overlay_bars()` by its own
    literal name at every call site."""
    assert "from lib.overlay import overlay_bars, overlay_grouped_bars" in LAB_SRC
    assert "overlay_bars(" in LAB_SRC
    assert "overlay_grouped_bars(" in LAB_SRC
    # The retired ad-hoc two-trace pattern (page-1-era, pre-pass-5) must be gone --
    # NOT a bare 'barmode="overlay"' search, which the (unrelated) FWCI-whisker
    # box/scatter chart legitimately still uses for its own layering.
    assert 'name="ISITE",\n        width=0.5' not in LAB_SRC
    assert '# ISITE overlay bars\n    fig.add_trace' not in LAB_SRC
    # Gated on the GLOBAL sidebar toggle, never a page-local one: the toggle is
    # read once, into `isite_overlay_on`, and threaded into every chart-building
    # call this pass (render_breakdown_pair, plot_field_share_pair_left).
    assert "isite_overlay_on = _controls_state[controls.ISITE_OVERLAY_KEY]" in LAB_SRC
    assert "render_breakdown_pair(row, selected_structure, source_key, include_conference, isite_overlay_on)" in LAB_SRC
    assert "plot_field_share_pair_left(df_fields, isite_overlay_on)" in LAB_SRC


def test_lab_page_grouped_bars_toggle_switches_doctype_and_domain():
    """#26/#30: ONE segmented_control drives both the global (left) and annual
    (right) charts of the pair; no second/per-panel toggle."""
    assert 'st.segmented_control(\n        "Découpage", ["Types de document", "Domaines"]' in LAB_SRC
    assert LAB_SRC.count('key="lab_breakdown_dim"') == 1


def test_lab_page_wires_ranked_table_four_times_mixed_depth():
    """Pass 6 (#34, P6-R6): internal partners stays shallow (10, blob-based,
    unchanged); international/French partners and authors are now sourced from
    the NEW 30-deep lab_top_partners.parquet / lab_top_authors.parquet tables --
    the has_members split (2 orgs / 2 individuals) is unchanged in shape even
    though the org tables' source and depth changed."""
    assert "from lib.ranked import ranked_table" in LAB_SRC
    assert LAB_SRC.count("ranked_table(\n") == 4
    # Consortium badges on the two EXTERNAL partner lists only, never on internal
    # collabs (other UL structures) nor on the individual-authors list. Matched
    # with the trailing comma so the module docstring's OWN prose mention of
    # "has_members=False: internal collabs are..." (ends in ':', not ',') doesn't
    # inflate the count.
    assert LAB_SRC.count("has_members=True,") == 2
    assert LAB_SRC.count("has_members=False,") == 2
    # The two new 30-deep tops sources, real OpenAlex partner_id (no more
    # name-matching against the consortium overlay -- lab_top_partners.parquet
    # carries the id natively).
    assert '_load_table("lab_top_partners")' in LAB_SRC
    assert '_load_table("lab_top_authors")' in LAB_SRC
    assert 'id_col="partner_id"' in LAB_SRC
    # The maison <-> ORCID-only method toggle: ONE table, method switches (P6-R6).
    assert '"Réconciliation maison", "ORCID uniquement"' in LAB_SRC
    assert LAB_SRC.count('_load_table("lab_top_authors")') >= 1


def test_r14_fwci_columns_carry_the_explicit_reference_label():
    assert "FWCI (réf. France)" in LAB_SRC
    assert "réf. France" in PROFIL_SRC


# =============================================================================
# Consortium name-matching helper (page-2-local, no id column on the source blobs)
# =============================================================================
# Re-derives the SAME lookup the page builds (from the SAME overlay CSV lib.ranked
# itself loads) to pin the exact contract without importing a Streamlit script body
# directly (page modules run top-to-bottom `st.*` calls at import time -- AppTest,
# used below, is the safe way to execute one; this pin instead exercises the CSV
# join logic in isolation, which is pure pandas, no Streamlit dependency).

_CONSORTIUM_CSV = ROOT / "inputs" / "overlays" / "idset_consortium.csv"


def _name_to_id_lookup() -> dict:
    df = pd.read_csv(_CONSORTIUM_CSV)
    out = {}
    for _, r in df.iterrows():
        out[str(r["member"]).strip().lower()] = str(r["id"]).strip()
        out[str(r["label"]).strip().lower()] = str(r["id"]).strip()
    return out


def _match(name: str, lookup: dict) -> str:
    return lookup.get(str(name).strip().lower(), "")


def test_consortium_match_exact_label_hits():
    lookup = _name_to_id_lookup()
    assert _match("Centre National de la Recherche Scientifique", lookup) == "I1294671590"
    assert _match("Inserm", lookup) == "I154526488"
    assert _match("AgroParisTech", lookup) == "I22248866"


def test_consortium_match_never_substring_never_false_positive():
    """The exact trap idset_consortium.csv's own comments name: a 'Georgia' sweep
    leaks unrelated institutions. Exact-match-only must return '' for all of them."""
    lookup = _name_to_id_lookup()
    for decoy in ("Georgia State University", "University of Georgia",
                  "Georgia Southern University", "Some Random Institute"):
        assert _match(decoy, lookup) == "", f"{decoy!r} unexpectedly matched a consortium id"
    assert _match("", lookup) == ""


def test_consortium_ids_from_page_lookup_are_a_subset_of_lib_ranked_CONSORTIUM_IDS():
    """The page's own name-matching lookup must never produce an id lib.ranked
    itself would not also recognise -- same file, same 15-id set, no drift."""
    sys.path.insert(0, str(STREAMLIT_DIR))
    saved = {k: v for k, v in sys.modules.items() if k == "lib" or k.startswith("lib.")}
    for k in list(saved):
        del sys.modules[k]
    try:
        from lib.ranked import CONSORTIUM_IDS
        lookup = _name_to_id_lookup()
        produced_ids = {v for v in lookup.values() if v}
        assert produced_ids <= CONSORTIUM_IDS
    finally:
        for k in [k for k in sys.modules if k == "lib" or k.startswith("lib.")]:
            del sys.modules[k]
        sys.modules.update(saved)
        if str(STREAMLIT_DIR) in sys.path:
            sys.path.remove(str(STREAMLIT_DIR))


# =============================================================================
# AppTest pins -- the NEW wiring actually renders, both overlay states
# =============================================================================

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


TIMEOUT = 90.0


def _exc_values(at):
    return [e.value for e in at.exception]


# Pass 6, discovered while re-running this file's own AppTest pins (P-LAB, wave 3):
# a NEW cross-cutting regression, introduced upstream of this stream (S-LIB/P1's
# `lib.controls.sidebar()` now calls `lib.helpers.render_methodo_expander()`, which
# calls `st.page_link("Menu.py", ...)` UNCONDITIONALLY) breaks `AppTest.from_file()`
# on ANY bare subpage load across the WHOLE app -- `st.page_link` raises
# `KeyError('url_pathname')` when the multipage registry isn't populated, which it
# never is on a bare subpage load. Verified NOT page-2-specific: the SAME crash
# reproduces on pages 4/6 (tests/test_page_pb.py, unrelated to this stream) and on
# tests/test_isite_overlay_journey.py's own LAB_PAGE-rooted fixture -- every page
# that calls `controls.sidebar()` is affected. Out of this stream's fence
# (lib/controls.py, lib/helpers.py); flagged in progress/PLAB.md for the manager.
# Workaround for THIS file's own pins, matching the ALREADY-established pattern one
# scroll up (test_apptest_profil_auteur_impact_drill_floor_gate_and_no_download's own
# docstring): initialize AppTest from Menu.py (which DOES populate the registry) and
# `switch_page()` into the target subpage before asserting.

def _lab_apptest():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(STREAMLIT_DIR / "Menu.py"))
    at.run(timeout=TIMEOUT)
    at.switch_page(f"pages/{LAB_PAGE}")
    at.run(timeout=TIMEOUT)
    return at


def test_apptest_laboratoires_renders_with_overlay_off_default():
    at = _lab_apptest()
    assert not at.exception, _exc_values(at)
    assert at.sidebar.toggle(key="isite_overlay").value is False
    titles = [t.value for t in at.title]
    assert any("Laboratoires" in t for t in titles)


def test_apptest_laboratoires_renders_with_overlay_on():
    at = _lab_apptest()
    at.sidebar.toggle(key="isite_overlay").set_value(True)
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)
    # The grouped-bars panel's own ON-state caption (VIZ_SPEC_pass6 §1.5's
    # GROUPED_BARS_HOWTOREAD_FR, surfaced only while the overlay is on).
    captions = [c.value for c in at.caption]
    assert any("I-SITE" in c for c in captions)


def test_apptest_laboratoires_ranked_tables_render_no_search_boxes_below_n50():
    """Pass 6 (P6-R6): all 4 ranked_table() calls on this page materialize at
    most 30 rows (internal partners 10, international/French partners/authors
    30) -- every one is BELOW lib.ranked.QUERY_MIN_N (50), so the search box is
    auto-hidden on EVERY panel. This is the flipped pin for the pass-5 pin that
    asserted the OLD (now-wrong) behaviour of 4 always-visible search boxes."""
    at = _lab_apptest()
    assert not at.exception, _exc_values(at)
    search_boxes = [ti for ti in at.text_input if ti.label == "Rechercher :"]
    assert len(search_boxes) == 0


def test_apptest_laboratoires_mini_fiche_identity_and_tiles_render():
    """P7/#28: the mini-fiche identity block (nom_complet, ROR/OpenAlex links)
    and the 4 KPI tiles render without exception for the default selection."""
    at = _lab_apptest()
    assert not at.exception, _exc_values(at)
    markdowns = "\n".join(m.value for m in at.markdown if m.value)
    assert "Indicateurs clés" in markdowns
    assert "Publications" in markdowns
    assert "Part I-SITE" in markdowns
    assert "FWCI médian (réf. France)" in markdowns


def test_apptest_laboratoires_sdg_profile_method_toggle_renders():
    """#8/#9: the ODD profile panel (moved in from Portefeuille thématique) and
    its SIRIS-vs-Aurora method radio render without exception."""
    at = _lab_apptest()
    assert not at.exception, _exc_values(at)
    radio_options = [tuple(r.options) for r in at.radio]
    assert ("SIRIS (VocTagger)", "Aurora (OpenAlex)") in radio_options


def test_apptest_annuaire_search_result_chips_render_lie_absent():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PAGES_DIR / ANNUAIRE_PAGE))
    at.run(timeout=TIMEOUT)
    at.text_input(key="authdir_query").set_value("a")
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)
    assert len(at.dataframe) >= 1
    df = at.dataframe[0].value
    orcid_col = df["ORCID"]
    assert set(orcid_col.unique()) <= {"✓ lié", "— absent"}


def test_apptest_profil_auteur_impact_drill_floor_gate_and_no_download():
    """
    Reached via `AppTest.from_file(Streamlit/Menu.py).switch_page("pages/12_...")`,
    NOT via `AppTest.from_file()` pointed directly at the subpage (verified by hand
    while writing this pin: a bare subpage-to-subpage `switch_page` call in THIS
    Streamlit build -- 1.61.1 -- never actually re-executes the destination script;
    `.run()` keeps re-running the ORIGINAL file regardless of `switch_page`'s own
    `_page_hash` mutation, silently. `AppTest`'s own docstring example initializes
    from the app's real entrypoint for exactly this reason -- confirmed empirically
    here to be load-bearing, not just a style preference. `st.page_link(...)`, which
    this page calls on its way back to the Directory, ALSO needs that entrypoint's
    multipage registry -- a direct subpage `from_file()` load raises
    KeyError('url_pathname') on it regardless of switch_page, even with no author
    resolved (same call site, unrelated to this pass's edits).

    NOTE for the manager: `tests/test_isite_overlay_journey.py` initializes every
    leg the OTHER way (`AppTest.from_file()` on a bare SUBPAGE, then chains
    `switch_page` subpage-to-subpage) -- per the finding above, those `.run()` calls
    likely keep re-executing the FIRST page loaded throughout, and the file's own
    assertions (session_state/sidebar-widget values only, shared across every page
    via the same `controls.sidebar()` keys) would read identically whether or not a
    real page switch happened. Flagged, not fixed -- that file is shared test
    infrastructure outside this stream's fence.
    """
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(STREAMLIT_DIR / "Menu.py"))
    at.run(timeout=TIMEOUT)
    at.session_state["nav_author_id"] = AUTHOR_ID
    at.switch_page(f"pages/{PROFIL_PAGE}")
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)
    titles = [t.value for t in at.title]
    assert any("Profil auteur" in t for t in titles), "did not actually navigate to Profil_auteur"
    drills = [e for e in at.expander if "contexte d'impact" in (e.label or "")]
    assert drills, "impact-drill expander not found"
    n_downloads_before = len(at.get("download_button"))
    drills[0].expanded = True
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)
    n_downloads_after = len(at.get("download_button"))
    assert n_downloads_after == n_downloads_before, (
        "opening the impact drill changed the download-button count -- "
        "safeguard 3bis violated"
    )


def test_apptest_identifiants_couverture_renders_default():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PAGES_DIR / IDENT_PAGE))
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)
    titles = [t.value for t in at.title]
    assert any("Identifiants et couverture" in t for t in titles)
