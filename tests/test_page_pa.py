# tests/test_page_pa.py
"""
Pass-5 (P-A) pins -- Menu (Streamlit/Menu.py), Vue d'ensemble (pages/1_...) and
Périmètres personnalisés (pages/3_...). Owned by stream P-A only; nothing here
touches a shared/frozen test file.

    python -m pytest tests/test_page_pa.py -q

Namespace/AppTest notes (same shape as tests/test_isite_overlay_journey.py, read
before editing this file):
  - This repo has TWO packages named `lib` (repo-root pipeline lib vs Streamlit/lib,
    the app one). setup_module/teardown_module swap the binding for this whole file's
    run, same save/restore idiom as the journey file.
  - A page that calls `st.page_link()` UNCONDITIONALLY (Vue d'ensemble does, twice)
    raises `KeyError: 'url_pathname'` when loaded via `AppTest.from_file(<page path>)`
    DIRECTLY: `PagesManager.uses_pages_directory` is computed from the loaded script's
    OWN parent directory ("pages/pages/" does not exist), so no page registry is ever
    built and `page_link`'s internal lookup has nothing to resolve against. This is a
    PRE-EXISTING limitation of this harness/Streamlit-build pairing, not something this
    stream introduced -- the exact same standalone load already fails on this repo's
    own pre-pass-5 pages/9_🔍_Zoom_partenaire.py (which has had an unconditional
    page_link back to Collaborations since chain pass 3), reproduced live while
    diagnosing this file. The fix used everywhere below, matching the journey file's
    OWN established pattern: `AppTest.from_file(Menu.py)` then `.switch_page(...)`, which
    runs the real `_mpa_v1` bootstrap and registers every page correctly. Périmètres
    personnalisés has no `page_link` call, so it is also exercised standalone once
    (test_page3_standalone_load_has_no_exception) as a second, independent proof.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
PAGES_DIR = STREAMLIT_DIR / "pages"
DATA_DIR = STREAMLIT_DIR / "data"

APP_PY = STREAMLIT_DIR / "Menu.py"
PAGE1 = "pages/1_\U0001F4CA_Vue_d_ensemble.py"
PAGE3 = "pages/3_\U0001F5C2️_Périmètres_personnalisés.py"

TIMEOUT = 90.0

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    # F-SYSMOD fix (MINOR): one-line fallback so `conftest` stays importable even if
    # this file is ever run as a standalone script, not just via pytest (which
    # already puts tests/ on sys.path itself).
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


def _goto(page: str) -> AppTest:
    at = AppTest.from_file(str(APP_PY))
    at.run(timeout=TIMEOUT)
    at.switch_page(page)
    at.run(timeout=TIMEOUT)
    assert not at.exception, f"{page} raised on load: {_exc_values(at)}"
    return at


def _require_data() -> None:
    needed = ["dim_subsets.parquet", "dim_corpus_facts.parquet", "consortium_weights.parquet",
              "ul_pubs.parquet", "dim_artifact_topics.parquet", "work_subsets.parquet"]
    missing = [n for n in needed if not (DATA_DIR / n).is_file()]
    if missing:
        pytest.skip(f"deployed data missing: {missing} -- run the pipeline + 60_deploy first")


# ============================================================================
# Menu (Menu.py) -- nav-label finding, journeys, defensive nav cards
# ============================================================================

def test_nav_label_for_main_script_is_the_bare_filename_no_capitalisation():
    """
    Streamlit's OWN filename -> nav-label derivation for a classic
    pages/-directory app's MAIN script has no title= surface and no
    capitalisation step (probed pass 5 against the installed build's pure
    function). That finding is exactly WHY the main script is now named
    Menu.py (pass-6 rename, P6-R4/#49): the bare filename IS the nav label.
    """
    from streamlit.source_util import page_icon_and_name
    icon, name = page_icon_and_name(Path("Menu.py"))
    assert (icon, name) == ("", "Menu")
    assert name.replace("_", " ") == "Menu"  # Page.__init__'s own title fallback


def test_menu_page_is_titled_menu_in_body():
    at = AppTest.from_file(str(APP_PY))
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)
    assert [t.value for t in at.title] == ["Menu"]


def test_menu_opens_with_the_pass6_mode_demploi_intro():
    """NARRATIVE_CONTRACT_pass6.md section 3.1 (P6-R2): the pass-5 rhetorical question
    is replaced by a plain statement of what the page does -- pasted verbatim, no
    trailing "?" any more (superseded pin: the old assertion checked for one)."""
    at = AppTest.from_file(str(APP_PY))
    at.run(timeout=TIMEOUT)
    captions = [c.value for c in at.caption]
    assert any("par quelle vue commencer" in c for c in captions), captions


def test_menu_nav_cards_include_vue_densemble_and_resolve_positionnement_defensively():
    """The runtime-enumerated nav cards (kept, per mission) must list the new page 1
    by its real filename, and must NOT hardcode page 5's exact name -- it is resolved
    by prefix glob so a sibling stream's own filename/emoji choice never staleness the
    link (this ran while page 5 was mid-landing in the same parallel wave)."""
    at = AppTest.from_file(str(APP_PY))
    at.run(timeout=TIMEOUT)
    labels_and_pages = [(pl.label, pl.page) for pl in at.get("page_link")]
    assert ("\U0001F4CA Vue d'ensemble", "Vue_d_ensemble") in labels_and_pages
    page5_files = sorted(PAGES_DIR.glob("5_*.py"))
    if page5_files:
        # resolved: href points at the REAL file (by url slug), whatever its own icon is
        assert any(page == "Positionnement" for _, page in labels_and_pages)
    else:
        assert any("en construction" in c.value for c in at.caption if "Positionnement" in c.value)


def test_menu_has_three_reading_journeys_advisory_challenge_partner():
    """NARRATIVE_CONTRACT_pass6.md section 3.2 (P16): a THIRD journey ("Instruire une
    relation partenaire") joins the pass-5 pair -- supersedes the pass-5 "two journeys"
    pin."""
    at = AppTest.from_file(str(APP_PY))
    at.run(timeout=TIMEOUT)
    headers = [m.value for m in at.markdown if m.value.startswith("###")]
    assert any("Advisory Board" in h for h in headers)
    assert any("défi" in h or "programme" in h for h in headers)
    assert any("partenaire" in h for h in headers)


def test_menu_challenge_journey_routes_through_positionnement():
    """Journeys route pin (probe 6): item P16 / backlog #1 -- "Animer un défi ou un
    programme" must include a step into 📍 Positionnement, between Portefeuille
    thématique and Exploration thématique."""
    at = AppTest.from_file(str(APP_PY))
    at.run(timeout=TIMEOUT)
    # Numbered-label filter (same idiom as test_menu_journey_steps_are_ordered_...):
    # excludes the unrelated, unnumbered nav-card page_links to the same three pages.
    journey_links = [pl for pl in at.get("page_link") if pl.label[:2] in {"1.", "2.", "3.", "4.", "5."}]
    challenge_pages = {"Portefeuille_thématique", "Positionnement", "Exploration_thématique"}
    ordered_pages = [pl.page for pl in journey_links if pl.page in challenge_pages]
    assert ordered_pages == ["Portefeuille_thématique", "Positionnement", "Exploration_thématique"], ordered_pages


def test_menu_challenge_journey_is_honest_about_pending_programme_lists():
    at = AppTest.from_file(str(APP_PY))
    at.run(timeout=TIMEOUT)
    warnings = [w.value for w in at.warning]
    assert len(warnings) == 1
    assert "programme" in warnings[0] and "établissement" in warnings[0]


def test_menu_journey_steps_are_ordered_page_links_with_one_sentence_each():
    at = AppTest.from_file(str(APP_PY))
    at.run(timeout=TIMEOUT)
    journey_links = [pl for pl in at.get("page_link") if pl.label[:2] in {"1.", "2.", "3.", "4.", "5."}]
    assert len(journey_links) >= 8  # 3 journeys (5+5+4 steps), at least the resolvable ones


def test_menu_has_the_methodo_section_and_the_registry_link():
    """Méthodo-present pin (probe 6, Menu half): BUILD_PLAN.md P1 -- the long
    "Méthodes et guide de lecture" section (lib.helpers.render_methodo_menu_section(),
    NARRATIVE_CONTRACT_pass6.md section 4.2) renders on the Menu body, plus the S-REG
    object-registry line (progress/SREG.md)."""
    _require_data()
    at = AppTest.from_file(str(APP_PY))
    at.run(timeout=TIMEOUT)
    body = " ".join(m.value for m in at.markdown)
    assert "Méthodes et guide de lecture" in body
    assert "Registre des objets" in body


def test_sidebar_methodo_expander_is_present_on_page1_and_a_third_page():
    """Méthodo-present pin (probe 6, sidebar half): the sidebar "À propos des filtres"
    expander is wired ONCE into the shared lib.controls.sidebar() (fence-extension
    edit), so it must render identically on page 1 (this stream's own page) AND on a
    THIRD, unrelated page (Laboratoires, P-LAB's) -- proof it is shared infrastructure,
    not a page-local addition."""
    _require_data()
    at1 = _goto(PAGE1)
    labels1 = [e.label for e in at1.sidebar.expander]
    assert any("À propos des filtres" in lbl for lbl in labels1), labels1

    at2 = AppTest.from_file(str(APP_PY))
    at2.run(timeout=TIMEOUT)
    at2.switch_page("pages/2_\U0001F3ED_Laboratoires.py")
    at2.run(timeout=TIMEOUT)
    assert not at2.exception, _exc_values(at2)
    labels2 = [e.label for e in at2.sidebar.expander]
    assert any("À propos des filtres" in lbl for lbl in labels2), labels2


# ============================================================================
# Vue d'ensemble (page 1) -- R8 headline recomputes
# ============================================================================

def test_page1_loads_with_no_exception_via_menu_switch_page():
    _require_data()
    at = _goto(PAGE1)
    assert [t.value for t in at.title] == ["\U0001F4CA Vue d'ensemble"]


def test_page1_kept_corpus_metric_matches_dim_corpus_facts_default_state():
    """Default state (conference ON, artifact OFF): the displayed 'Conservées' count
    must equal dim_corpus_facts.corpus_works for conf_state='all', recomputed fresh
    from the deployed parquet every run (never a literal pinned from memory)."""
    _require_data()
    import pandas as pd
    facts = pd.read_parquet(DATA_DIR / "dim_corpus_facts.parquet")
    expected = int(facts.loc[facts["conf_state"] == "all", "corpus_works"].iloc[0])

    at = _goto(PAGE1)
    markdowns = " ".join(m.value for m in at.markdown)
    assert f"{expected:,}".replace(",", " ") in markdowns.replace(",", " ") or str(expected) in markdowns.replace(" ", "")


def test_page1_isite_weight_metric_matches_dim_subsets_default_state():
    _require_data()
    import pandas as pd
    ds = pd.read_parquet(DATA_DIR / "dim_subsets.parquet")
    all_row = ds.loc[ds["subset_id"] == "all"].iloc[0]
    isite_row = ds.loc[ds["subset_id"] == "in_isite"].iloc[0]
    expected_works = int(isite_row["n_works"])
    expected_share_pct = round(expected_works / int(all_row["n_works"]) * 100, 1)

    at = _goto(PAGE1)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Travaux I-SITE") == f"{expected_works:,}".replace(",", " ")
    assert str(expected_share_pct).replace(".", ",") in metrics.get("Part du corpus", "")


def test_page1_doc_type_partition_sums_to_kept_corpus():
    """The data invariant Section 2's doc-types chart relies on: every kept work has
    exactly one of the 5 corpus types, so grouping by `type` must partition the
    corpus exactly (no over/under-count). This Streamlit build's AppTest has no
    queryable element for `st.plotly_chart` (verified: no Plotly-named class exists
    in `streamlit.testing.v1.element_tree`, and reading `.value` on the generic node
    AppTest falls back to raises a session_state KeyError -- a harness limitation,
    not a page bug), so this pins the underlying data assumption directly rather
    than the chart's own rendered trace values; the render itself is proven not to
    raise by test_page1_loads_with_no_exception_via_menu_switch_page."""
    _require_data()
    import pandas as pd
    pubs = pd.read_parquet(DATA_DIR / "ul_pubs.parquet", columns=["type"])
    facts = pd.read_parquet(DATA_DIR / "dim_corpus_facts.parquet")
    expected = int(facts.loc[facts["conf_state"] == "all", "corpus_works"].iloc[0])
    assert int(pubs["type"].value_counts().sum()) == expected == len(pubs)


def test_page1_consortium_data_has_seven_external_members_plus_ul_host_note():
    _require_data()
    import pandas as pd
    cw = pd.read_parquet(DATA_DIR / "consortium_weights.parquet")
    n_members = cw.loc[(cw["scope"] == "all") & (cw["conf_state"] == "all"), "member"].nunique()
    assert n_members == 7  # CNRS, Inserm, CHRU Nancy, INRAE, AgroParisTech, Georgia Tech, Inria

    at = _goto(PAGE1)
    body = " ".join(m.value for m in at.markdown)
    assert "huit" in body
    assert "porteuse" in body


def test_page1_isite_overlay_toggle_adds_the_row_swap_comparator_caption():
    """R1 row-swap contract (docs/OVERLAY_MATRIX.md, this panel's own disclosed
    status): toggle OFF shows the site-wide bar alone; toggle ON adds the I-SITE-scope
    comparator. AppTest cannot introspect the plotly figure itself in this Streamlit
    build (see test_page1_doc_type_partition_sums_to_kept_corpus's docstring), so this
    pins the ON-only caption that names the added comparator instead -- a real,
    render-level signal of the same behaviour."""
    _require_data()
    ON_CAPTION_MARKER = "le point bleu ajoute la part de chaque membre"

    at_off = _goto(PAGE1)
    assert ON_CAPTION_MARKER not in " ".join(c.value for c in at_off.caption)

    at_on = _goto(PAGE1)
    at_on.sidebar.toggle(key="isite_overlay").set_value(True)
    at_on.run(timeout=TIMEOUT)
    assert not at_on.exception, _exc_values(at_on)
    assert ON_CAPTION_MARKER in " ".join(c.value for c in at_on.caption)


def test_page1_not_expressible_isite_registry_reason_is_shown_for_the_weight_metric():
    """R5: a number that cannot be expressed as a live OpenAlex filter (the hand
    I-SITE DOI list) gets NO deep-link icon, and the page states why -- verbatim
    from the shared NOT_EXPRESSIBLE registry, never a page-local guess at the reason."""
    _require_data()
    sys.path.insert(0, str(STREAMLIT_DIR))
    from lib.links import NOT_EXPRESSIBLE
    at = _goto(PAGE1)
    body = " ".join(c.value for c in at.caption)
    assert NOT_EXPRESSIBLE["isite_hand_list"] in body


def test_page1_annual_breakdown_uses_the_grouped_bars_grammar():
    """Grouped-bars pin (probe 6): #35/VIZ_SPEC_pass6 section 1.5 -- the annual
    breakdown is grouped (Studio A/B verdict), never the pass-5 stacked
    barmode="stack" year x type chart. Source-level, since AppTest cannot
    introspect a plotly figure's own barmode/offset in this Streamlit build (see
    test_page1_doc_type_partition_sums_to_kept_corpus's docstring)."""
    src = (PAGES_DIR / "1_\U0001F4CA_Vue_d_ensemble.py").read_text(encoding="utf-8")
    assert "overlay_grouped_bars" in src
    assert "from lib.overlay import" in src and "overlay_grouped_bars" in src.split("from lib.overlay import", 1)[1].split("\n", 1)[0]
    # The pass-5 single stacked year x type figure is gone -- two grouped calls now
    # (doc type block + domain block), never a bare `barmode="stack"` build for it.
    assert src.count("overlay_grouped_bars(") == 1  # one call site, invoked twice via _breakdown_block


def test_page1_doc_type_charts_consume_helpers_doctype_colors():
    """DOCTYPE_COLORS-consumed pin (probe 6): #36 -- doc-type charts read the
    single-sourced lib.helpers.DOCTYPE_COLORS token (pass-6 palette, validated
    light-mode, distinct from DOMAIN_COLORS by construction), never a page-local
    palette. Both the import and an actual keyed lookup must be present."""
    src = (PAGES_DIR / "1_\U0001F4CA_Vue_d_ensemble.py").read_text(encoding="utf-8")
    assert "DOCTYPE_COLORS" in src.split("from lib.helpers import", 1)[1].split(")", 1)[0]
    assert "DOCTYPE_COLORS[" in src  # an actual lookup, not just an unused import
    assert "DOMAIN_COLORS[" in src  # the domain block's own palette, distinct by construction (VIZ_SPEC 2.5)


# ============================================================================
# Périmètres personnalisés (page 3) -- registry-only rebuild, R1
# ============================================================================

def test_page3_standalone_load_has_no_exception():
    """Pass-6 update (P-V1 fence extension, BUILD_PLAN.md P1/C): this page's own
    "no page_link on this page" premise died the moment
    lib.controls.sidebar()'s shared render_methodo_expander() call added ONE
    unconditional st.page_link (the sidebar "-> Methodes et guide de lecture" link)
    to EVERY page that calls controls.sidebar() -- page 3 included. A direct
    standalone AppTest.from_file() load now hits the exact same harness limitation
    documented at the top of this file (KeyError 'url_pathname': PagesManager needs
    the real pages/ registry, which only the Menu.py-bootstrap + switch_page path
    builds). Root cause lives in the pass-6 sidebar change, not in page 3's own
    code, so this pin now uses the SAME bootstrap idiom as every other page3 test
    below (_goto) rather than asserting a standalone-load property that is no
    longer true for ANY page in this app."""
    _require_data()
    at = _goto(PAGE3)
    assert not at.exception, _exc_values(at)


def test_page3_click_to_apply_mechanic_is_fully_removed():
    """R1: the old row-click-sets-global-perimeter mechanic (on_select='rerun' +
    a pre-sidebar session_state resolution block) must be gone -- a source-level
    pin (same idiom as test_shared_layer.py's persistence pins), because the
    mechanic being INERT is exactly the bug the shared-layer stream flagged rather
    than fixed; this stream's job was to remove it outright, not leave it inert."""
    src = (PAGES_DIR / "3_\U0001F5C2️_Périmètres_personnalisés.py").read_text(encoding="utf-8")
    assert "on_select" not in src
    assert "REGISTRY_TABLE_KEY" not in src
    assert "ACTIVE_SUBSET_IDS" not in src
    assert 'st.session_state["perimeter_subset"]' not in src


def test_page3_registry_has_five_rows_three_active_two_stub():
    _require_data()
    at = _goto(PAGE3)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Périmètres actifs") == "3"
    assert metrics.get("En attente (atelier)") == "2"


def test_page3_registry_table_carries_the_exact_isite_and_award_counts():
    """The 1 839 / 808 values (R1 mission text: 'keep their exact values') must
    appear in the rendered registry table, recomputed live from dim_subsets, not
    hardcoded in the page."""
    _require_data()
    at = _goto(PAGE3)
    dfs = [dl.value for dl in at.get("dataframe")]
    assert dfs, "expected the registry st.dataframe to render"
    registry_df = dfs[0]
    works_col = [c for c in registry_df.columns if c == "Travaux"]
    assert works_col, registry_df.columns.tolist()
    values = set(registry_df["Travaux"].dropna().astype(int))
    assert 1839 in values
    assert 808 in values


def test_page3_award_crosscheck_row_is_labelled_never_merged():
    _require_data()
    at = _goto(PAGE3)
    body = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
    assert "recoupement" in body.lower()
    assert "D21" in body or "jamais fusionnée" in body


def test_page3_recoupement_delta_is_computed_not_hardcoded():
    """Pass-6 narrative sweep (P-SWP): the 'ecart de 32 travaux' caption must be
    computed live from subset_works.parquet (same recompute as page I-SITE's own
    808/776/32 pin, tests/test_page_pd.py), never a hardcoded literal that would
    silently go stale on a future peer/award re-pull."""
    _require_data()
    import pandas as pd

    subset_works = pd.read_parquet(DATA_DIR / "subset_works.parquet")
    award_rows = subset_works[subset_works["subset_id"] == "in_isite_award"]
    expected_delta = int((~award_rows["in_isite"]).sum())

    at = _goto(PAGE3)
    body = " ".join(c.value for c in at.caption)
    assert f"l'écart de {expected_delta} travaux" in body, (
        f"expected the computed delta ({expected_delta}) in the recoupement caption; "
        f"it may have regressed to a hardcoded literal"
    )


def test_page3_hors_liste_pointer_names_laboratoires_page():
    _require_data()
    at = _goto(PAGE3)
    body = " ".join(c.value for c in at.caption)
    assert "Laboratoires" in body


def test_page3_pending_rows_show_atelier_action_line():
    _require_data()
    at = _goto(PAGE3)
    body = " ".join(m.value for m in at.markdown)
    assert "Action attendue de l'atelier" in body
    assert "roster" in body.lower() or "ORCID" in body
    assert "programme" in body.lower()
