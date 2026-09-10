# tests/test_page_pd.py
"""
Pass-5 P-D pins -- Streamlit/pages/7_🎯_I-SITE.py (the I-SITE identity/synthesis
redesign, R2). Independent-recompute pins for the numbers the page renders (KPI row,
award reconciliation panel per S-INV §4, PM3 amplification caption), a smoke pin that
the page loads with no exception under AppTest, and structural pins (dead perimeter
plumbing is gone; the identity-block vocabulary from CLIENT_BRIEF.md §2 is present; no
funding figure or stray em dash slipped into the new FR prose).

Namespace note: same `lib`-package collision every other AppTest-based file in this
suite documents (Streamlit/lib vs the repo-root pipeline `lib`) -- setup_module/
teardown_module swap sys.modules for this file's run and restore afterwards (same
shape as tests/test_isite_overlay_journey.py's own docstring).

    python -m pytest tests/test_page_pd.py -q
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

PAGE = "7_\U0001F3AF_I-SITE.py"
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
    guard (AppTest's page execution needs Streamlit's own lib package correctly bound)
    instead of this file's own copy of the save/delete/insert-path dance."""
    global _saved_lib_modules
    _saved_lib_modules = swap_lib_to_streamlit()


def teardown_module(_module) -> None:
    """Restore whatever `lib` binding existed before this file ran."""
    restore_lib(_saved_lib_modules)


def _exc_values(at: AppTest) -> list:
    return [e.value for e in at.exception]


@pytest.fixture(scope="module")
def page() -> AppTest:
    """One AppTest run of the I-SITE page, default sidebar state (all 3 toggles at
    their coded default: conference ON, artifact OFF, isite_overlay OFF). Shared
    across every test in this file that needs it (module-scoped, computed once)."""
    at = AppTest.from_file(str(PAGES_DIR / PAGE))
    at.run(timeout=TIMEOUT)
    assert not at.exception, f"page load raised: {_exc_values(at)}"
    return at


def _all_markdown(at: AppTest) -> str:
    return "\n".join(md.value for md in at.markdown)


def _all_text(at: AppTest) -> str:
    return "\n".join(md.value for md in at.markdown) + "\n" + "\n".join(c.value for c in at.caption)


# ---------------------------------------------------------------------------
# Independent recompute -- straight pandas off the deployed parquets, no page code,
# no Streamlit import. These are the SAME shapes the page itself computes, reproduced
# here from scratch so a future page edit that silently drifts the numbers is caught
# even if it drifts the page's OWN computation the same wrong way.
# ---------------------------------------------------------------------------

def _award_reconciliation_numbers() -> tuple[int, int, int]:
    """(total, in_canon, hors_liste) for subset_id=='in_isite_award' -- the S-INV §4
    BROAD-family numbers (808/776/32 this snapshot)."""
    sw = pd.read_parquet(DATA_DIR / "subset_works.parquet")
    award = sw[sw["subset_id"] == "in_isite_award"]
    total = len(award)
    hors_liste = int((~award["in_isite"]).sum())
    return total, total - hors_liste, hors_liste


def _kpi_numbers() -> tuple[int, float]:
    """(isite_works, pct_of_corpus) off dim_subsets.parquet, default toggle state
    (conference included, artifact filter off -> the base 'n_works' column)."""
    ds = pd.read_parquet(DATA_DIR / "dim_subsets.parquet")
    isite_works = int(ds.loc[ds["subset_id"] == "in_isite", "n_works"].iloc[0])
    corpus_total = int(ds.loc[ds["subset_id"] == "all", "n_works"].iloc[0])
    return isite_works, isite_works / corpus_total * 100


def _fr_ratio(value: float, decimals: int = 2) -> str:
    """Byte-identical copy of the page's own local formatter (module docstring: a
    plain decimal, not fr_int/fr_pct's shape) -- reproduced here so this test file
    never imports page-module globals, same discipline as every other pin above."""
    return f"{value:.{decimals}f}".replace(".", ",")


def _fr_int(value: int) -> str:
    """Local reproduction of lib.helpers.fr_int's grouping (narrow no-break space
    thousands separator) -- this test file hardcodes formatted strings rather than
    importing the Streamlit lib package (see existing "1 839"/"5,0 %" pins above),
    so a helper is reproduced locally rather than imported, same as `_fr_ratio`."""
    return f"{int(round(value)):,}".replace(",", " ")


def _award_panel_all_types_numbers() -> tuple[int, int, int]:
    """(canon_all_types, award_in_canon, award_no_trace) -- I2-02/I2-08 fix: the
    canonical-list total the award panel compares against must be the ALL-TYPES
    dim_subsets figure (1 839), never the conference-toggle-following one (1 729
    with the toggle off), and the "no award trace" reading is the plain subtraction."""
    ds = pd.read_parquet(DATA_DIR / "dim_subsets.parquet")
    canon_all_types = int(ds.loc[ds["subset_id"] == "in_isite", "n_works"].iloc[0])
    _, award_in_canon, _ = _award_reconciliation_numbers()
    return canon_all_types, award_in_canon, canon_all_types - award_in_canon


def _static_impact_numbers() -> dict:
    """Independent recompute of the I2-03 static impact block -- FWCI_FR median/mean
    and PPtop10_FR share, In_ISITE vs the rest of the site, D53-floored
    (indicator_status == 'computed' only), straight off ul_pubs.parquet (never the
    page's own get_pubs_slim() cache)."""
    pubs = pd.read_parquet(
        DATA_DIR / "ul_pubs.parquet",
        columns=["work_id", "In_ISITE", "FWCI_FR", "PPtop10_FR", "indicator_status"],
    )
    has_ind = pubs["indicator_status"] == "computed"
    isite = pubs[pubs["In_ISITE"] & has_ind]
    rest = pubs[(~pubs["In_ISITE"]) & has_ind]
    return {
        "n_isite": len(isite), "n_rest": len(rest),
        "isite_median": isite["FWCI_FR"].median(), "rest_median": rest["FWCI_FR"].median(),
        "isite_mean": isite["FWCI_FR"].mean(), "rest_mean": rest["FWCI_FR"].mean(),
        "isite_pptop10": isite["PPtop10_FR"].mean() * 100, "rest_pptop10": rest["PPtop10_FR"].mean() * 100,
    }


def _top2_fields_by_ratio() -> tuple[str, str]:
    """The two field names the PM3 amplification title must name, recomputed the same
    way the page does (thm_specialisation, level=field, conf_state=all, subset all vs
    in_isite, ul_works) -- this pin tracks the DATA, not a hardcoded field name. The
    ranking already moved once this pass (a prior Codex draft named Materials Science
    first; this snapshot leads with Agricultural and Biological Sciences) -- see
    progress/PD_isite.md for the full recompute trail."""
    ts = pd.read_parquet(DATA_DIR / "thm_specialisation.parquet")
    all_topics = pd.read_parquet(DATA_DIR / "all_topics.parquet")
    field_id2name = (
        all_topics[["field_id", "field_name"]].drop_duplicates()
        .set_index("field_id")["field_name"].to_dict()
    )
    fr = ts[(ts["level"] == "field") & (ts["conf_state"] == "all")]
    site = fr[fr["subset_id"] == "all"].set_index("node_id")
    isite = fr[fr["subset_id"] == "in_isite"].set_index("node_id")
    site_total = site["ul_works"].sum()
    isite_total = isite.reindex(site.index)["ul_works"].sum()
    site_share = site["ul_works"] / site_total
    isite_share = isite.reindex(site.index)["ul_works"] / isite_total
    ratio = (isite_share / site_share).sort_values(ascending=False)
    names = [field_id2name[int(fid)] for fid in ratio.index[:2]]
    return names[0], names[1]


# ---------------------------------------------------------------------------
# Data pins
# ---------------------------------------------------------------------------

def test_award_reconciliation_numbers_are_808_776_32():
    total, in_canon, hors_liste = _award_reconciliation_numbers()
    assert (total, in_canon, hors_liste) == (808, 776, 32), (
        "S-INV §4 BROAD-family reconciliation drifted from the frozen 2026-08-11 "
        f"snapshot values -- got total={total}, in_canon={in_canon}, hors_liste={hors_liste}"
    )


def test_kpi_numbers_match_dim_subsets():
    isite_works, pct = _kpi_numbers()
    assert isite_works == 1839
    assert round(pct, 1) == 5.0


# ---------------------------------------------------------------------------
# Render pins (require the `page` AppTest fixture)
# ---------------------------------------------------------------------------

def test_page_renders_the_award_panel_numbers(page):
    total, in_canon, hors_liste = _award_reconciliation_numbers()
    blob = _all_markdown(page)
    assert f"**{total}**" in blob
    assert f"**{in_canon}**" in blob
    assert f"**{hors_liste}**" in blob


def test_713_and_749_never_render_as_headline_numbers(page):
    """S-INV §4's own display recommendation: never surface the superseded EXACT/749
    or the n_works_noconf/713 bookkeeping figure as headline quantities on this page --
    only the BROAD-family trio (808/776/32) is shown."""
    blob = _all_text(page)
    assert "749" not in blob, "the superseded EXACT/749 award figure leaked onto the page"
    assert "713" not in blob, "the n_works_noconf/713 bookkeeping figure leaked onto the page"


def test_page_metrics_show_the_kpi_numbers(page):
    labels_values = {m.label: m.value for m in page.metric}
    assert labels_values.get("Travaux I-SITE") == "1 839"
    assert labels_values.get("Part du corpus complet") == "5,0 %"


def test_amplification_section_title_is_neutral(page):
    """Pass-6 narrative sweep (NARRATIVE_CONTRACT_pass6.md 2.8, row 358-361): the PM3
    section title used to name the live top-2 fields itself (a title-as-answer); it is
    now a neutral, static question, and the field names moved to the caption below it."""
    titles = [
        line for line in _all_markdown(page).split("\n")
        if line.startswith("## Ce que le périmètre I-SITE amplifie")
    ]
    assert titles, "neutral amplification section title not found"


def test_amplification_caption_names_the_actual_top2_fields(page):
    """The PM3 caption is built from a live recompute every render (never a hardcoded
    field-name pair) -- pin the MECHANISM: the caption must agree with an independent
    recompute of the same ranking, whatever it currently is."""
    top1, top2 = _top2_fields_by_ratio()
    captions = [c.value for c in page.caption if "Champs les plus amplifiés" in c.value]
    assert captions, "amplification caption not found"
    assert top1 in captions[0] and top2 in captions[0], (
        f"caption {captions[0]!r} does not name the live top-2 fields {top1!r}/{top2!r}"
    )


def test_no_dead_perimeter_plumbing_in_source():
    """R1 killed the global perimeter filter; this page's own panels were always
    I-SITE-fixed by construction, so the old `active_subset`/`perimeter_disclosure_strip`
    branch (permanently unreachable since perimeter_subset is now the hardcoded
    constant "all") must be REMOVED, not merely unreachable. Regex on the actual
    assignment/call, not a bare substring, so the module docstring's own prose
    documenting the removal (naming both identifiers on purpose) doesn't self-trigger."""
    import re

    text = (PAGES_DIR / PAGE).read_text(encoding="utf-8")
    assert not re.search(r"\bactive_subset\s*=", text), "active_subset assignment still present"
    assert not re.search(r"perimeter_disclosure_strip\s*\(", text), "perimeter_disclosure_strip() call still present"


def test_identity_block_names_all_six_defis(page):
    blob = _all_markdown(page)
    for name in [
        "Les matériaux au XXIe siècle",
        "Transition écologique (One Earth)",
        "Transition énergétique",
        "Transition numérique de l'industrie et de la société",
        "Défis mondiaux de la santé",
        "Transitions dans la société",
    ]:
        assert name in blob, f"défi {name!r} missing from the identity block"


def test_identity_block_names_all_eight_consortium_members(page):
    blob = _all_markdown(page)
    for name in [
        "Université de Lorraine", "CNRS", "CHRU Nancy", "Georgia Tech Europe",
        "Inria", "INRAE", "Inserm", "AgroParisTech",
    ]:
        assert name in blob, f"consortium member {name!r} missing from the identity block"


def test_identity_block_names_the_three_instrument_families(page):
    blob = _all_markdown(page)
    for name in ["Programmes Interdisciplinaires (PI)", "Projets IMPACT", "CRET"]:
        assert name in blob, f"instrument family {name!r} missing from the identity block"


def test_no_funding_figures_on_this_page(page):
    """R2 instruction: this page states no funding figure at all (several circulating
    figures are flagged UNVERIFIED in CLIENT_BRIEF.md §2.1) -- guard against a future
    edit reintroducing one via a euro sign."""
    assert "€" not in _all_text(page)


def test_no_em_dash_outside_the_verbatim_r2_caption(page):
    """voix-siris-fr firm rule: no em dash in FR prose. The ONE exception is the R2
    co-tutelle caption, frozen VERBATIM (indicator_plan_FINAL.md R2) and already
    carrying one -- excluded by content, not by position, so this pin survives a
    future section reorder."""
    verbatim_r2 = "Cette part reflète la structure des UMR co-portées"
    offenders = [
        md.value for md in page.markdown
        if "—" in md.value and verbatim_r2 not in md.value
    ]
    assert not offenders, f"em dash found outside the verbatim R2 caption: {offenders}"


def test_award_panel_states_one_explicit_all_types_basis(page):
    """I2-02 fix: the panel must state the 776/808 pair and the canonical total on
    ONE explicit, all-types basis -- never mix a conf-filtered canonical total (1 729)
    with the unfiltered award numbers (808/776/32) in the same sentence. Pass-6 narrative
    sweep (NARRATIVE_CONTRACT_pass6.md 2.8, row 671-676) rewords the basis caption; the
    invariant under test is the BASIS statement, not its exact prior wording."""
    canon, in_canon, _ = _award_panel_all_types_numbers()
    blob = _all_markdown(page)
    assert f"({_fr_int(canon)} travaux)" in blob
    basis_caption = _all_text(page)
    assert "tous les types de publication" in basis_caption
    assert "indépendamment du bouton" in basis_caption


def _award_sentence(blob: str) -> str:
    """Extract just the award-reconciliation sentence (the one I2-02 caught mixing
    bases) rather than the whole page -- the KPI headline a few lines above it DOES
    legitimately change with the conference toggle (it states the toggle-following
    count on purpose), so comparing the FULL page text before/after would be the
    wrong invariant; only this one sentence must be frozen. End marker updated pass-6
    (NARRATIVE_CONTRACT_pass6.md 2.8, row 664): the "(D21)" jargon reference was removed
    from the displayed sentence, so anchor on the sentence's own closing words instead."""
    start = blob.find("Croisement prix/financement OpenAlex")
    end = blob.find("périmètre canonique.", start)
    assert start != -1 and end != -1, "award reconciliation sentence not found"
    return blob[start:end]


def test_award_panel_basis_is_unchanged_with_conference_toggle_off(page):
    """The three BROAD-family numbers AND the canonical total they are compared
    against must be identical with the conference toggle OFF -- if they drifted,
    the panel would silently mix bases again (the exact I2-02 defect)."""
    canon, _, _ = _award_panel_all_types_numbers()
    off_sentence = _award_sentence(_all_markdown(page))
    assert _fr_int(canon) in off_sentence

    page.sidebar.toggle(key="include_conference").set_value(False)
    page.run(timeout=TIMEOUT)
    assert not page.exception, _exc_values(page)
    on_sentence = _award_sentence(_all_markdown(page))
    assert _fr_int(canon) in on_sentence
    assert off_sentence == on_sentence, "award panel sentence changed when the conference toggle flipped"

    # restore default state for any test running after this one in the module-scoped fixture
    page.sidebar.toggle(key="include_conference").set_value(True)
    page.run(timeout=TIMEOUT)


def test_award_panel_disarming_sentence_present(page):
    """I2-08 fix: the 1 063-works-with-no-award-trace reading must be disarmed ADJACENT
    to the award panel -- pre-empted rather than left for a reader to discover unaided.
    Pass-6 narrative sweep (NARRATIVE_CONTRACT_pass6.md 2.8, row 677-684) drops the
    corpus-wide 21,3 % acknowledgment-coverage comparison (a static data value with no
    live source on this page) in favour of a plain "this is expected" disclosure -- the
    invariant under test is the disarming statement itself, not the dropped comparison."""
    _, _, no_trace = _award_panel_all_types_numbers()
    blob = _all_text(page)
    assert f"{_fr_int(no_trace)}" in blob
    assert "C'est attendu" in blob
    assert "aucune trace" in blob or "aucun" in blob.lower() and "trace" in blob.lower()


def test_static_impact_block_matches_independent_recompute(page):
    """I2-03 fix: the new synthesis-level impact block (FWCI_FR médiane, In_ISITE vs
    the rest of the site) must match an independent D53-floored recompute off
    ul_pubs.parquet exactly -- this is the restored 'is the I-SITE better cited?'
    answer the R1 overlay redesign had removed from the whole app."""
    numbers = _static_impact_numbers()
    labels_values = {m.label: m.value for m in page.metric}
    assert labels_values.get("FWCI (réf. France), médiane -- I-SITE") == _fr_ratio(numbers["isite_median"])
    assert labels_values.get("FWCI (réf. France), médiane -- reste du site") == _fr_ratio(numbers["rest_median"])
    blob = _all_text(page)
    assert _fr_ratio(numbers["isite_mean"]) in blob
    assert _fr_ratio(numbers["rest_mean"]) in blob
    assert _fr_int(numbers["n_isite"]) in blob
    assert _fr_int(numbers["n_rest"]) in blob


def test_static_impact_block_shows_isite_more_cited_than_rest(page):
    """Sanity check on the DIRECTION of the restored answer: this snapshot's I-SITE
    median and PPtop10 share must both read above the rest of the site's -- if a
    future data refresh flips this, the test should fail loudly, not pass silently
    on a hardcoded expectation."""
    numbers = _static_impact_numbers()
    assert numbers["isite_median"] > numbers["rest_median"]
    assert numbers["isite_pptop10"] > numbers["rest_pptop10"]


def test_isite_overlay_toggle_has_no_effect_on_this_page(page):
    """OVERLAY_MATRIX.md's own row for page 7: 'the whole page IS the ISITE lens', so
    turning the global overlay toggle ON must change nothing this page renders (the
    page-local disclosure caption is the ONLY thing that should differ)."""
    off_metrics = {m.label: m.value for m in page.metric}
    off_award_blob = _all_markdown(page)

    page.sidebar.toggle(key="isite_overlay").set_value(True)
    page.run(timeout=TIMEOUT)
    assert not page.exception, _exc_values(page)

    on_metrics = {m.label: m.value for m in page.metric}
    assert on_metrics == off_metrics
    # the disclosure text is rendered via st.caption, never st.markdown, so the
    # markdown stream (every data-bearing number on this page) must be byte-identical.
    on_blob = _all_markdown(page)
    assert on_blob == off_award_blob


# ---------------------------------------------------------------------------
# Pass-6 narrative sweep pins (item #37 recall block, R18 log/linear toggle)
# ---------------------------------------------------------------------------

def _canonical_recall_numbers() -> tuple[int, int, int, int]:
    """(n_doi, n_matched, n_award, n_award_only) for the item #37 recall block --
    n_doi is the pipeline config constant (config.yaml isite.expected_unique_dois,
    mirrored page-locally per the same workshop-tunable convention pages 8/9 already
    use for their own config-sourced constants); the other three are independent
    re-derivations off the deployed parquets, same as `_award_reconciliation_numbers`."""
    n_doi = 3776
    ds = pd.read_parquet(DATA_DIR / "dim_subsets.parquet")
    n_matched = int(ds.loc[ds["subset_id"] == "in_isite", "n_works"].iloc[0])
    total, _, hors_liste = _award_reconciliation_numbers()
    return n_doi, n_matched, total, hors_liste


def test_canonical_list_recall_block_present_with_computed_numbers(page):
    """Item #37 (NARRATIVE_CONTRACT_pass6.md S4.3): the canonical-list construction
    recall block is a closed-by-default expander, placed under the KPI tiles, with
    every {n} placeholder filled from a computed value -- no number hardcoded."""
    expanders = [e for e in page.expander if e.label == "Comment la liste I-SITE a été construite"]
    assert expanders, "canonical-list construction recall expander not found"
    assert expanders[0].proto.expanded is False, "recall block must be closed by default"

    n_doi, n_matched, n_award, n_award_only = _canonical_recall_numbers()
    blob = _all_markdown(page)
    assert _fr_int(n_doi) in blob
    assert _fr_int(n_matched) in blob
    assert _fr_int(n_award) in blob
    assert _fr_int(n_award_only) in blob


def test_ratio_axis_log_linear_toggle_present_and_off_by_default(page):
    """R18 (pass6_probes.md probe 9): the amplification dot-ratio chart gets a local
    linear-scale toggle, log by default -- the same shared `lib.helpers.log_linear_toggle`
    pattern already pinned on pages 4/5/8, closing the one page-7 gap the probe found."""
    assert page.toggle(key="isite_ratio_axis_toggle").value is False


def test_ratio_axis_toggle_flips_with_no_exception(page):
    """Flipping the toggle must re-run the page cleanly (AppTest does not expose the
    Plotly figure's own axis-type spec for a deep assertion here; the render-verified
    proof that the axis actually switches to linear is the Playwright screenshot,
    per this stream's acceptance criteria)."""
    page.toggle(key="isite_ratio_axis_toggle").set_value(True)
    page.run(timeout=TIMEOUT)
    assert not page.exception, _exc_values(page)

    # restore default state for any test running after this one in the module-scoped fixture
    page.toggle(key="isite_ratio_axis_toggle").set_value(False)
    page.run(timeout=TIMEOUT)


def test_ratio_axis_type_is_wired_to_the_toggle_in_source():
    """Source-level mechanism pin: the dot-ratio chart's x-axis type must come from the
    resolved toggle value, never a hardcoded `type=\"log\"` literal (the exact R18 gap
    pass6_probes.md probe 9 found on this page)."""
    text = (PAGES_DIR / PAGE).read_text(encoding="utf-8")
    assert "from lib.helpers import" in text and "log_linear_toggle" in text
    assert 'type="log"' not in text, "hardcoded log axis type still present"
    assert "_ratio_axis_type" in text
