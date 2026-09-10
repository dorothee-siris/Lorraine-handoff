# tests/test_page_pc.py
"""
Pass-5 stream P-C pins -- page 5 "Positionnement" (Streamlit/pages/5_\U0001F4CD_Positionnement.py).

Two layers, same split as the rest of this pass's page-stream tests:
  - AppTest pins against the REAL page script (proves the actual wired behaviour, not a
    reimplementation) -- the R11 "quantum" acceptance test lives here.
  - Pure data-level pins against the deployed parquets directly (no Streamlit import risk),
    proving the invariants the page's own logic leans on (D53 floors never fabricate a
    zero; the T3b domain-block aggregation reconciles to the full matrix it replaces).

Namespace note (same collision tests/test_isite_overlay_journey.py's own docstring
describes): this repo has TWO packages named `lib` (the repo-root pipeline one and
Streamlit/lib, the app one). `setup_module`/`teardown_module` swap the Streamlit one in
for this whole file's run and restore whatever was there before once every test here is
done.

    python -m pytest tests/test_page_pc.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
PAGES_DIR = STREAMLIT_DIR / "pages"
DATA_DIR = STREAMLIT_DIR / "data"

PAGE = "5_\U0001F4CD_Positionnement.py"
TIMEOUT = 180.0

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


def _fresh() -> AppTest:
    at = AppTest.from_file(str(PAGES_DIR / PAGE))
    at.run(timeout=TIMEOUT)
    assert not at.exception, f"initial load raised: {_exc_values(at)}"
    return at


# ============================================================================
# Load / toggle-combination smoke (AppTest)
# ============================================================================

def test_page_loads_with_default_toggles():
    at = _fresh()
    assert at.toggle(key="isite_overlay").value is False
    assert at.toggle(key="artifact_filter").value is False
    assert at.toggle(key="include_conference").value is True


@pytest.mark.parametrize("isite_on,artifact_on,conf_on", [
    (True, False, True),
    (False, True, True),
    (True, True, True),
    (True, True, False),
])
def test_toggle_combinations_do_not_crash(isite_on, artifact_on, conf_on):
    at = _fresh()
    at.toggle(key="isite_overlay").set_value(isite_on)
    at.toggle(key="artifact_filter").set_value(artifact_on)
    at.toggle(key="include_conference").set_value(conf_on)
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)


# ============================================================================
# Panel 2 -- emerging topics: the R11 DEPTH & QUERY acceptance contract
# ============================================================================

def _emerging_df(at: AppTest) -> pd.DataFrame:
    for d in at.dataframe:
        if "topic_name" in d.value.columns:
            return d.value
    raise AssertionError("emerging-topics dataframe not found on the page")


def test_emerging_topics_default_depth_is_ten():
    at = _fresh()
    assert len(_emerging_df(at)) == 10


def test_emerging_topics_quantum_query_returns_all_matching_topics_full_depth():
    """R11's OWN named acceptance example (ruling locked 2026-08-18): type "quantum" -> see the
    position of ALL topics containing quantum, not merely the one topic the OLD 20-row
    thm_frontier texture slice happened to cover (the pre-R11 pin here asserted `len(df) == 1`).
    Expected count independently recomputed from the deployed thm_frontier_topics.parquet -- never
    hardcoded -- and must exceed that old single-hit result.

    The query alone surfaces only the default top-10 OF THE MATCHES (lib.ranked's own frozen
    depth-then-query composition -- "afficher plus" always applies on top of a query, exactly
    like every other ranked_table panel in this app); "afficher plus" then reveals every one of
    them -- this is what "materialized depth = FULL" means under the frozen shared component: the
    full 3,274-topic universe is SEARCHABLE and, one click away, fully VISIBLE, never capped at
    the old 20-topic ceiling."""
    at = _fresh()
    at.text_input(key="emerging_topics_query").set_value("quantum")
    at.run(timeout=TIMEOUT)
    df_default = _emerging_df(at)
    assert len(df_default) == 10, "a query with >10 matches still shows the top-10 by default"

    at.button(key="emerging_topics_more_btn").click()
    at.run(timeout=TIMEOUT)
    df = _emerging_df(at)

    tft = pd.read_parquet(DATA_DIR / "thm_frontier_topics.parquet")
    expected = tft[
        (tft["conf_state"] == "all") & tft["topic_name"].str.contains("quantum", case=False, na=False)
    ]
    assert len(expected) > 1, "sanity: the full-depth universe must carry more than the old 1 hit"
    assert len(df) == len(expected), (
        f"page returned {len(df)} quantum-matching rows after 'afficher plus', "
        f"deployed data has {len(expected)}"
    )

    # golden continuity: the ONE topic the old texture slice already covered keeps its exact score.
    row = df.loc[df["topic_name"] == "Carbon and Quantum Dots Applications"].iloc[0]
    assert round(float(row["Standardised score"]), 2) == 2.23
    assert int(row["UL works"]) == 9

    # every other quantum topic -- newly visible under full depth -- carries EITHER a real
    # numeric score OR the explicit "hors référentiel de score" state, never a fabricated position.
    for _, r in df.iterrows():
        assert isinstance(r["Standardised score"], (int, float)) or r["Standardised score"] == (
            "hors référentiel de score"
        )


def test_emerging_topics_query_reaches_beyond_the_default_top_ten():
    """A query on topics ranked BELOW the default top-10 -- proves the search filters the FULL
    materialized universe (R11 full depth), not just the 10 rows initially on screen. Expected
    rows independently recomputed from the deployed parquet (5 "adaptation" topics on this
    snapshot, up from the pre-R11 single hit the old 20-row texture slice happened to carry)."""
    at = _fresh()
    at.text_input(key="emerging_topics_query").set_value("Adaptation")
    at.run(timeout=TIMEOUT)
    df = _emerging_df(at)

    tft = pd.read_parquet(DATA_DIR / "thm_frontier_topics.parquet")
    expected = tft[
        (tft["conf_state"] == "all") & tft["topic_name"].str.contains("adaptation", case=False, na=False)
    ]
    assert len(df) == len(expected)
    names = set(df["topic_name"])
    assert "Domain Adaptation and Few-Shot Learning" in names
    row = df.loc[df["topic_name"] == "Domain Adaptation and Few-Shot Learning"].iloc[0]
    assert round(float(row["Standardised score"]), 2) == 1.71


def test_emerging_topics_afficher_plus_reveals_the_full_materialized_universe():
    """R11 full-depth ruling: "afficher plus" now reveals the ENTIRE UL topic universe for this
    conf_state (thm_frontier_topics's fixed grain, 3,274 topics), not the old 20-row texture
    slice's own hard cap -- expected count independently recomputed from the deployed parquet."""
    at = _fresh()
    at.button(key="emerging_topics_more_btn").click()
    at.run(timeout=TIMEOUT)
    df = _emerging_df(at)

    tft = pd.read_parquet(DATA_DIR / "thm_frontier_topics.parquet")
    expected_n = int((tft["conf_state"] == "all").sum())
    assert expected_n == 3274, f"UL topic universe drifted: {expected_n} != 3,274"
    assert len(df) == expected_n


def test_emerging_topics_null_score_topic_shows_the_hors_referentiel_state_never_a_fabricated_zero():
    """A topic on the 811-exclusion list still appears in the FULL-depth list with its real UL
    works count and a dagger in "Réf.", but its score cell reads the explicit
    "hors référentiel de score" state -- never a fabricated 0 or a silently omitted row."""
    at = _fresh()
    at.text_input(key="emerging_topics_query").set_value("Sociology and Education Studies")
    at.run(timeout=TIMEOUT)
    df = _emerging_df(at)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["Standardised score"] == "hors référentiel de score"
    assert int(row["UL works"]) == 6
    assert row["Réf."] == "†"  # the dagger marker, per lib.controls.DAGGER


def test_emerging_topics_isite_share_column_only_present_when_toggle_on():
    """Structural overlay-wiring proof: the same-row I-SITE decomposition column exists
    on screen only while the global isite_overlay toggle is ON (toggle OFF => "as if the
    overlay never existed", per lib/overlay.py's own module docstring)."""
    at_off = _fresh()
    assert "I-SITE share" not in _emerging_df(at_off).columns

    at_on = _fresh()
    at_on.toggle(key="isite_overlay").set_value(True)
    at_on.run(timeout=TIMEOUT)
    assert "I-SITE share" in _emerging_df(at_on).columns


# ============================================================================
# Panel 3 -- frontier x labs crossing: depth default + query
# ============================================================================

def _labs_df(at: AppTest) -> pd.DataFrame:
    for d in at.dataframe:
        if "lab" in d.value.columns and "Standardised share (%)" in d.value.columns:
            return d.value
    raise AssertionError("frontier-labs dataframe not found on the page")


def test_frontier_labs_default_depth_is_ten():
    at = _fresh()
    assert len(_labs_df(at)) == 10


def test_frontier_labs_query_finds_a_lab_outside_the_default_top_ten():
    at = _fresh()
    at.text_input(key="frontier_labs_query").set_value("LORIA")
    at.run(timeout=TIMEOUT)
    df = _labs_df(at)
    assert len(df) == 1
    assert df.iloc[0]["lab"] == "LORIA"


# ============================================================================
# Panel 6 -- co-discipline top-pairs table: query across BOTH field columns
# ============================================================================

def _pairs_df(at: AppTest) -> pd.DataFrame:
    for d in at.dataframe:
        if {"Field A", "Field B", "Co-works"}.issubset(d.value.columns):
            return d.value
    raise AssertionError("co-discipline pairs dataframe not found on the page")


def test_codiscipline_pairs_default_depth_is_ten():
    at = _fresh()
    assert len(_pairs_df(at)) == 10


def test_codiscipline_pairs_query_matches_either_field_column():
    """filter_by_query ORs across search_cols -- a query matching ONLY "Field B" on some
    rows and ONLY "Field A" on others must surface both."""
    at = _fresh()
    at.text_input(key="codiscipline_pairs_query").set_value("Mathematics")
    at.run(timeout=TIMEOUT)
    df = _pairs_df(at)
    assert len(df) > 0
    assert all(
        ("Mathematics" in a) or ("Mathematics" in b)
        for a, b in zip(df["Field A"], df["Field B"])
    )


# ============================================================================
# Panel 5 -- peer context: LinkColumn uses the DIRECT scope, never lineage
# ============================================================================

def test_peer_diversity_table_has_ten_entities_with_direct_scope_links():
    at = _fresh()
    for d in at.dataframe:
        cols = d.value.columns
        if "rao_stirling" in cols or "Rao-Stirling (DIV)" in cols:
            df = d.value
            assert len(df) == 10
            assert "OpenAlex" in cols
            assert df["OpenAlex"].str.contains("authorships.institutions.id:").all()
            assert not df["OpenAlex"].str.contains("lineage").any()
            return
    raise AssertionError("peer diversity dataframe not found on the page")


# ============================================================================
# Panel 1 -- T9 cross: R18 local log/linear toggle is wired, log by default
# ============================================================================

def test_t9_log_linear_toggle_present_and_off_by_default():
    at = _fresh()
    assert at.toggle(key="t9_axis_linear").value is False


# ============================================================================
# Panel 3 -> Panel 5 cross-reference (S-LENS D1/D2, pass-6 fix round)
# ============================================================================

def test_forward_xref_points_at_the_current_panel5_title_with_computed_peer_count():
    """
    S-LENS D1: the panel-3 forward cross-reference used to name a section title that
    was REPLACED this pass ("Comment Lorraine se situe face a la France et a neuf
    pairs") and hardcode the peer count in words ("neuf pairs"). It must now name the
    CURRENT panel-5 title verbatim ("Position face a la France et aux pairs retenus")
    and carry a computed peer count, never the stale title or a static word count.
    """
    at = _fresh()
    captions = [c.value for c in at.caption]
    markdowns = [m.value for m in at.markdown]

    xref = next((c for c in captions if "Mise en contexte face aux pairs" in c), None)
    assert xref is not None, "forward cross-reference caption not found"
    assert "Position face à la France et aux pairs retenus" in xref
    assert "Comment Lorraine se situe" not in xref  # the replaced title must be gone
    assert "neuf pairs" not in xref  # no static word-count left

    peers = pd.read_parquet(DATA_DIR / "bench_peers.parquet", columns=["entity_id", "rung"])
    n_peers = int(peers.loc[peers["rung"] != "FOCAL", "entity_id"].nunique())
    assert f"{n_peers} pairs" in xref or f"{n_peers:,}".replace(",", " ") + " pairs" in xref

    # the panel-5 title itself must be exactly what the cross-reference now names
    assert any(m.strip() == "## Position face à la France et aux pairs retenus" for m in markdowns)


def test_how_to_read_block_computes_peer_count_not_a_static_word():
    """S-LENS D2: 'les points gris les neuf pairs' in the how-to-read block, three
    lines below a caption that already computes the count -- must now compute it too."""
    at = _fresh()
    markdowns = [m.value for m in at.markdown]
    # Several panels on this page share the "Comment lire ce graphique" opener --
    # target the ONE about the peer scatter specifically ("le point bleu situe
    # l'universite de Lorraine"), not panel 3's LQ-vs-France scatter.
    how_to_read = next((m for m in markdowns if "le point bleu situe" in m), None)
    assert how_to_read is not None
    assert "neuf pairs" not in how_to_read

    peers = pd.read_parquet(DATA_DIR / "bench_peers.parquet", columns=["entity_id", "rung"])
    n_peers = int(peers.loc[peers["rung"] != "FOCAL", "entity_id"].nunique())
    assert f"les {n_peers} pairs" in how_to_read


# ============================================================================
# Pure data-level pins (no Streamlit import) -- invariants the page leans on
# ============================================================================

def test_thm_frontier_labs_floor_never_fabricates_a_zero():
    """D53: labs below the min_stratum_n floor on scoreable works must show NaN (which the
    page renders as an empty/absent value), never a fabricated 0.0 share."""
    df = pd.read_parquet(DATA_DIR / "thm_frontier_labs.parquet")
    sub = df[df["conf_state"] == "all"]
    below_floor = sub[sub["works_n_scoreable"] < 30]
    assert len(below_floor) > 0  # the floor must actually bind on this table
    assert below_floor["field_standardised_share"].isna().all()
    assert below_floor["frontier_share"].isna().all()


def test_codiscipline_domain_block_matrix_reconciles_to_the_full_matrix_it_replaces():
    """The T3b redesign's domain-block heatmap must carry EXACTLY the same total volume as
    the 26x26 matrix it replaces (a straight re-aggregation of the same rows, never a
    different population) -- independently recomputed here, not imported from the page."""
    cd = pd.read_parquet(DATA_DIR / "thm_codiscipline.parquet")
    topics = pd.read_parquet(DATA_DIR / "all_topics.parquet")
    f2d = topics[["field_id", "domain_id"]].drop_duplicates().set_index("field_id")["domain_id"].to_dict()
    d2n = topics[["domain_id", "domain_name"]].drop_duplicates().set_index("domain_id")["domain_name"].to_dict()

    for perimeter in ("all", "in_isite"):
        sub = cd[(cd["perimeter_id"] == perimeter) & (cd["conf_state"] == "all")].copy()
        sub["domain_a_name"] = sub["field_a"].astype(int).map(f2d).map(d2n)
        sub["domain_b_name"] = sub["field_b"].astype(int).map(f2d).map(d2n)
        pivot = sub.groupby(["domain_a_name", "domain_b_name"])["co_works"].sum().unstack(fill_value=0)
        assert np.isclose(pivot.values.sum(), sub["co_works"].sum())
        assert np.allclose(pivot.values, pivot.values.T)  # symmetric, like the source matrix


def test_bench_diversity_ul_row_matches_the_methodes_disclosed_value():
    """METHODES.md §9.10's own pinned number: the bench_diversity UL row (direct-id,
    2019-2023) is 0.3327, distinct from the deployed thm_diversity value (0.3217,
    lineage, 2019 only) -- both are shown on the page, never one substituted for the
    other. This pin guards the SOURCE number the page's caption quotes."""
    bdiv = pd.read_parquet(DATA_DIR / "bench_diversity.parquet")
    ul_row = bdiv[(bdiv["entity_id"] == "I90183372") & (bdiv["conf_state"] == "all")]
    assert len(ul_row) == 1
    assert round(float(ul_row["rao_stirling"].iloc[0]), 4) == 0.3327

    div = pd.read_parquet(DATA_DIR / "thm_diversity.parquet")
    div_row = div[(div["perimeter_id"] == "all") & (div["conf_state"] == "all") & (div["year"] == 2019)]
    assert len(div_row) == 1
    assert round(float(div_row["rao_stirling"].iloc[0]), 4) == 0.3217
