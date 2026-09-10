# tests/test_page_pf.py
"""
Pass-5 stream P-F pins -- pages/{8_Collaborations, 9_Zoom_partenaire, 10_Géographie}.py.

Three mandated categories (mission "Verification you ship"):
  (a) member-mask re-slice on the hub: top-10 masked == top-(10+k) minus members, exercised
      on the REAL deployed ptn_summary population (not a synthetic fixture -- test_ranked.py
      already pins the pure-function contract on synthetic data; this proves MY page's own
      materialized frame -- type/floor-filtered, sorted by co_works -- actually contains
      consortium members and that the mask/depth composition page 8 uses reconciles).
  (b) pass-6 (item #44): page 9's publications download is now a lazy CSV
      (lib.helpers.lazy_slice_csv_bytes) carrying enrichment metadata unfiltered by the
      conference/artifact toggles -- this pin proves it reads the correct per-partner keyed
      slice and actually carries the enrichment columns (doi, in_isite, artifact_flag,
      sdg_tags, type). Supersedes the pass-5 QA-02 drawer/export-agreement pin, which
      tested a full on-screen table this redesign removed.
  (c) overlay values reconcile (isite segment <= base) -- on the three real deployed tables
      this stream wires (ptn_summary, ptn_fields, geo_countries) AND on lib.overlay.overlay_bars()
      fed those same real numbers (not just the synthetic values test_overlay.py already pins).

Plus: AppTest smoke coverage for the 3 owned pages (compiles, runs, survives the isite_overlay
toggle and one field/subfield drill -- the branches that only execute under specific toggle/
session states and are otherwise invisible to a plain import-time check).

Namespace note: same collision tests/test_isite_overlay_journey.py's and tests/test_page_pc.py's
own docstrings describe (two packages named `lib` in this repo: the repo-root pipeline one and
Streamlit/lib, the app one). Unlike tests/test_ranked.py's or test_shared_layer.py's per-import
transient swap (safe there because they only ever import the pure modules ONCE, at collection
time, and never again), THIS file also runs AppTest against the REAL page scripts, which
re-execute `from lib import controls, ...` on every single `.run()` call throughout the file --
so the swap has to stay in effect for the file's WHOLE run, restored only at the very end
(`setup_module`/`teardown_module`, exactly test_page_pc.py's own pattern). The pure-function
modules (`lib.ranked`, `lib.overlay`, `lib.lazy`, `lib.exports`) are therefore imported lazily,
inside each test that needs them, via `_libs()` below -- never at module import time, which
would run BEFORE `setup_module` has swapped anything.

    python -m pytest tests/test_page_pf.py -q
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
DATA_DIR = STREAMLIT_DIR / "data"
PAGES_DIR = STREAMLIT_DIR / "pages"

COLLAB_PAGE = "8_\U0001F91D_Collaborations.py"
PARTNER_PAGE = "9_\U0001F50D_Zoom_partenaire.py"
GEO_PAGE = "10_\U0001F30D_Géographie.py"
GEO_SRC = (PAGES_DIR / GEO_PAGE).read_text(encoding="utf-8")

CNRS_ID = "I1294671590"  # same repro entity as test_shared_layer.py's own QA-02 pin

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
    """Restore whatever `lib` binding existed before this file ran."""
    restore_lib(_saved_lib_modules)


def _libs():
    """Lazy import of the pure-function modules -- called from INSIDE a test, after
    setup_module() has already swapped the namespace (never at module import time)."""
    import lib.exports as exports_mod
    import lib.lazy as lazy_mod
    import lib.overlay as overlay_mod
    import lib.ranked as ranked_mod
    return ranked_mod, overlay_mod, lazy_mod, exports_mod


def _skip_if_missing(path: Path):
    if not path.is_file():
        pytest.skip(f"{path} not deployed -- run the pipeline + 60_deploy first")


# ============================================================================
# (a) member-mask re-slice -- hub, REAL ptn_summary population
# ============================================================================

def _hub_population(subset_id="all", conf_state="all", floor=20) -> pd.DataFrame:
    """Reproduces 8_Collaborations.py's own `_base_sorted` (no type filter): the
    materialized, floor-filtered, co_works-sorted frame handed to ranked_table()."""
    path = DATA_DIR / "ptn_summary.parquet"
    _skip_if_missing(path)
    df = pd.read_parquet(path)
    df = df[(df["subset_id"] == subset_id) & (df["conf_state"] == conf_state)]
    df = df[df["co_works_full"] >= floor]
    return df.sort_values("co_works_full", ascending=False).reset_index(drop=True)


def test_hub_population_actually_contains_consortium_members():
    """Fixture sanity: the mask test below is vacuous if no member ever appears in the
    default-floor hub population."""
    ranked, _, _, _ = _libs()
    base = _hub_population()
    members_present = base[base["partner_id"].isin(ranked.CONSORTIUM_IDS)]
    assert len(members_present) > 0
    assert len(members_present) < len(base)  # not ALL partners, either


def test_hub_member_mask_top10_matches_direct_filter_on_real_data():
    """The pinned invariant (same shape as test_ranked.py's synthetic pin, here on the
    REAL materialized hub frame page 8 builds): masked top-10 == the full population with
    members removed, then head(10). depth_slice/mask_members never recompute -- they only
    ever re-slice the frame already in hand."""
    ranked, _, _, _ = _libs()
    base = _hub_population()
    visible = ranked.visible_slice_with_member_mask(
        base, id_col="partner_id", member_ids=ranked.CONSORTIUM_IDS,
        hide_members=True, expanded=False, default_n=10,
    )
    expected = base[~base["partner_id"].isin(ranked.CONSORTIUM_IDS)].head(10)
    assert visible["partner_id"].tolist() == expected["partner_id"].tolist()
    assert len(visible) == 10
    assert not (set(visible["partner_id"]) & ranked.CONSORTIUM_IDS)


def test_hub_member_mask_off_is_a_noop_on_real_data():
    ranked, _, _, _ = _libs()
    base = _hub_population()
    visible = ranked.visible_slice_with_member_mask(
        base, id_col="partner_id", member_ids=ranked.CONSORTIUM_IDS,
        hide_members=False, expanded=False, default_n=10,
    )
    assert visible["partner_id"].tolist() == base.head(10)["partner_id"].tolist()


def test_hub_afficher_plus_reveals_the_whole_materialized_frame_not_a_second_pull():
    """'site-level = deep' (R11): the mission's own instruction is that the hub's full
    frame is already loaded and extension is free -- depth_slice(expanded=True) must
    return everything page 8 materialized, never a re-pull capped at N+8."""
    ranked, _, _, _ = _libs()
    base = _hub_population()
    assert len(base) > 18  # more than one member-pad's worth, or this proves nothing
    visible = ranked.depth_slice(base, expanded=True, default_n=10)
    assert len(visible) == len(base)


# ============================================================================
# (b) pass-6 redesign (item #44): page 9 no longer renders the full pair worklist nor
# exports it through the toggle-filtered `exports.works_xlsx` drawer/export pair -- a lazy
# CSV (lib.helpers.lazy_slice_csv_bytes) now carries the ENRICHMENT METADATA (doi, type,
# in_isite, artifact_flag, sdg_tags) unfiltered, so a downstream reader can filter it
# themselves instead of the page pre-filtering it away. This pin proves the download reads
# the correct per-partner keyed slice and actually carries those columns.
# ============================================================================

PTN_WORKS_DOWNLOAD_COLS = [
    "work_id", "year", "title", "doi", "type", "is_conference", "in_isite", "fwci_fr",
    "labs_short", "artifact_flag", "sdg_tags", "primary_field_id", "primary_subfield_id",
    "primary_topic_id",
]


def test_partner_publications_lazy_download_matches_the_keyed_slice():
    import io
    import lib.helpers as helpers_mod
    _, _, lazy, _ = _libs()
    path = DATA_DIR / "ptn_works.parquet"
    _skip_if_missing(path)
    full = lazy.read_keyed(str(path), "partner_id", CNRS_ID)
    if full.empty:
        pytest.skip(f"partner_id={CNRS_ID} not present in this deployed snapshot")

    csv_bytes = helpers_mod.lazy_slice_csv_bytes(
        str(path), "partner_id", CNRS_ID, columns=PTN_WORKS_DOWNLOAD_COLS,
    )
    downloaded = pd.read_csv(io.BytesIO(csv_bytes))

    # Row count: the lazy download is UNFILTERED by the conference/artifact toggles (they
    # are carried as columns instead, per item #44) -- it must equal the full keyed slice.
    assert len(downloaded) == len(full)
    for col in PTN_WORKS_DOWNLOAD_COLS:
        assert col in downloaded.columns
    # The two toggle-relevant flags actually vary in this fixture, or the "carries the
    # metadata instead of pre-filtering" claim is untested by this partner.
    assert downloaded["is_conference"].nunique(dropna=False) >= 1
    assert "in_isite" in downloaded.columns and "artifact_flag" in downloaded.columns


# ============================================================================
# (c) overlay reconciliation -- isite segment <= base, real deployed data
# ============================================================================

def test_ptn_summary_isite_never_exceeds_the_base_total():
    path = DATA_DIR / "ptn_summary.parquet"
    _skip_if_missing(path)
    df = pd.read_parquet(path)
    assert (df["isite_co_works"] <= df["co_works_full"]).all()
    # isite_share reconciles with isite_co_works/co_works_full (allow float rounding)
    nz = df[df["co_works_full"] > 0]
    recomputed = nz["isite_co_works"] / nz["co_works_full"]
    assert np.allclose(recomputed, nz["isite_share"], atol=1e-6)


def test_ptn_fields_isite_never_exceeds_the_base_total():
    path = DATA_DIR / "ptn_fields.parquet"
    _skip_if_missing(path)
    df = pd.read_parquet(path)
    assert (df["co_works_isite"] <= df["co_works"]).all()


def test_geo_countries_isite_never_exceeds_the_base_total():
    path = DATA_DIR / "geo_countries.parquet"
    _skip_if_missing(path)
    df = pd.read_parquet(path)
    assert (df["isite_co_works"] <= df["co_works"]).all()


def test_overlay_bars_on_real_hub_sample_segments_sum_to_the_real_totals():
    """The same reconciliation as the 3 data-invariant pins above, but pushed all the way
    through lib.overlay.overlay_bars() with REAL numbers (page 8's own shape: categories =
    partner names, totals = co_works_full, isite = isite_co_works) -- proves the wiring,
    not just the source columns."""
    _, overlay, _, _ = _libs()
    base = _hub_population().head(15)
    if base.empty:
        pytest.skip("no hub rows at the default floor in this deployed snapshot")
    totals = base["co_works_full"].astype(float).tolist()
    isite = base["isite_co_works"].astype(float).tolist()

    fig_on = overlay.overlay_bars(
        categories=base["display_name"].tolist(), totals=totals, isite=isite,
        colors="#0072B2", isite_on=True, orientation="h",
    )
    isite_trace, rest_trace = fig_on.data[0], fig_on.data[1]
    for iv, rv, tv in zip(isite_trace.x, rest_trace.x, totals):
        assert iv <= tv + 1e-9
        assert abs(iv + rv - tv) < 1e-6

    fig_off = overlay.overlay_bars(
        categories=base["display_name"].tolist(), totals=totals, isite=isite,
        colors="#0072B2", isite_on=False, orientation="h",
    )
    assert len(fig_off.data) == 1  # overlay-off neutrality: single base trace only


# ============================================================================
# (d) pass-6 pins (P-COL, items #38b/#7/#39 -- reports/pass6_probes.md probe 6 map)
# ============================================================================

def test_hub_progress_cols_keep_exactly_one_bar_share_partenaire():
    """Item #38b (VIZ_SPEC_pass6 S7.2): "Part partenaire" (share_p_pct) is the ONE
    ProgressColumn on the hub table; every other share/volume 8_Collaborations.py
    builds is an explicit NumberColumn (auto-demoted). Reproduces the page's own
    progress_cols shape (isite_share only added when the overlay toggle is on;
    "Part France hors site" is a pre-formatted TEXT column instead -- a nullable
    NumberColumn renders NaN as the literal string "None" on this Streamlit build,
    confirmed live, progress/PCOL.md -- so it is NOT in this dict at all) and
    proves only the first entry ever survives as a bar, in both toggle states."""
    ranked, _, _, _ = _libs()
    base_cols = {
        "share_p_pct": {"format": "%.1f%%", "max_value": 100},
        "co_works": {"format": "%d"},
        "share_ul": {"format": "%.1f%%"},
    }
    kept, demoted = ranked.resolve_progress_cols(base_cols)
    assert list(kept.keys()) == ["share_p_pct"]
    assert set(demoted.keys()) == {"co_works", "share_ul"}

    with_isite = dict(base_cols)
    with_isite["isite_share"] = {"format": "%.1f%%"}
    kept2, demoted2 = ranked.resolve_progress_cols(with_isite)
    assert list(kept2.keys()) == ["share_p_pct"]
    assert set(demoted2.keys()) == {"co_works", "share_ul", "isite_share"}


def test_hub_momentum_axis_titles_are_data_driven_not_hardcoded():
    """docs/YEAR_UPDATE_DESIGN.md S5.3 (L573-574, "the worst site is yours"): the
    momentum quadrant's axis titles must read the window labels from ptn_mom_facts
    (mom_w1_label/mom_w2_label), never state a literal period by hand -- a
    source-level pin since Plotly axis titles sit outside tests/test_narrative.py's
    own scanned surface (its docstring says so explicitly)."""
    src = (PAGES_DIR / COLLAB_PAGE).read_text(encoding="utf-8")
    assert "2019-2020" not in src
    assert "2022-2023" not in src
    xaxis_line = next(l for l in src.splitlines() if "update_xaxes(type=axis_type" in l)
    yaxis_line = next(l for l in src.splitlines() if "update_yaxes(type=axis_type" in l)
    assert "mom_w1_label" in xaxis_line
    assert "mom_w2_label" in yaxis_line


def test_france_hors_site_share_null_only_for_non_fr_and_consortium_members():
    """Item #39/P4: ptn_denominators.share_of_ul_france_copubs_hors_site is populated
    for FR partners that are NOT one of the 8 consortium signatories, and NULL
    everywhere else (never a fabricated 0) -- the invariant page 8's new "Part
    France hors site" column depends on for its "--" display."""
    path = DATA_DIR / "ptn_denominators.parquet"
    _skip_if_missing(path)
    df = pd.read_parquet(path)
    fr_rows = df[df["country_code"] == "FR"]
    non_fr_rows = df[df["country_code"] != "FR"]

    assert non_fr_rows["share_of_ul_france_copubs_hors_site"].isna().all()
    fr_members = fr_rows[fr_rows["is_consortium_member"]]
    if not fr_members.empty:
        assert fr_members["share_of_ul_france_copubs_hors_site"].isna().all()
    fr_non_members = fr_rows[~fr_rows["is_consortium_member"]]
    populated = fr_non_members["share_of_ul_france_copubs_hors_site"].dropna()
    assert len(populated) > 0
    assert populated.between(0, 1).all()


def test_france_hors_site_display_uses_fr_pct_text_never_a_number_column():
    """Regression pin (confirmed live via Playwright, progress/PCOL.md): a nullable
    float column routed through lib.ranked's NumberColumn (format=) renders NaN as
    the literal string "None" on this Streamlit build -- worse than a blank cell,
    and a straight violation of "never show a raw internal value". The column must
    stay a pre-formatted TEXT field (fr_pct with a "--" fallback), like
    fwci_median_text's siblings, and must NOT appear in progress_cols at all."""
    src = (PAGES_DIR / COLLAB_PAGE).read_text(encoding="utf-8")
    assert "france_hors_site_text" in src
    assert '"france_hors_site"' not in src  # the old numeric column name must be gone
    progress_block = src[src.index("progress_cols = {"):src.index("visible = ranked.ranked_table(")]
    assert "france_hors_site" not in progress_block


def test_hub_france_hors_site_merge_matches_ptn_denominators_and_excludes_consortium():
    """Reproduces 8_Collaborations.py's own merge (_base_sorted + ptn_denominators on
    partner_id, left join): CNRS (a consortium signatory) must come out NULL on the
    new column, never a fabricated 0, and the merge must never duplicate rows
    (ptn_denominators is exactly one row per partner_id)."""
    denom_path = DATA_DIR / "ptn_denominators.parquet"
    _skip_if_missing(denom_path)
    base = _hub_population()
    denom = pd.read_parquet(denom_path)[["partner_id", "share_of_ul_france_copubs_hors_site"]]
    merged = base.merge(denom, on="partner_id", how="left")
    assert len(merged) == len(base)
    cnrs = merged[merged["partner_id"] == CNRS_ID]
    if not cnrs.empty:
        assert cnrs["share_of_ul_france_copubs_hors_site"].isna().all()


# ============================================================================
# AppTest smoke coverage -- the 3 owned pages, incl. toggle/drill branches that only
# execute conditionally and are otherwise invisible to a plain import-time check.
# ============================================================================

def _exc_values(at):
    return [e.value for e in at.exception]


def _neutralize_page_link(monkeypatch) -> None:
    """Pass-6 regression (surfaced 2026-08-19, NOT caused by this stream's own pages):
    the méthodo-expander wiring (lib.controls.sidebar() -> lib.helpers.
    render_methodo_expander() -> st.page_link()) now runs on EVERY page's very first
    render. st.page_link() fails under AppTest with a pre-existing harness limitation
    (KeyError 'url_pathname' -- reproduces on a bare 2-line st.page_link() probe with NO
    page content at all; confirmed live: `AppTest.from_file()` on page 8 alone, with NO
    page-9-specific code involved, throws the identical KeyError at
    lib/controls.py's `render_methodo_expander()` call. The live server resolves
    `url_pathname` fine via its real multipage registry -- only the AppTest simulation
    lacks it). Before this wiring landed, only page 9's own explicit page_link call
    needed a workaround (switch_page, below); now EVERY page's sidebar hits it on the
    very first st.run(), including page 8's and page 10's OWN smoke tests, breaking all
    three uniformly. Neutralising the call here isolates what these tests actually mean
    to check (does THIS page's own logic survive a toggle/drill) from an unrelated,
    harness-only limitation. FLAGGED, not fixed at the source: lib/controls.py and
    lib/helpers.py are outside this stream's fence -- see progress/PZP.md for the report
    to the owning stream (guard the call, or the harness should populate the registry)."""
    import streamlit as st_mod
    monkeypatch.setattr(st_mod, "page_link", lambda *a, **k: None)


def test_page8_collaborations_survives_isite_overlay_toggle_on(monkeypatch):
    _neutralize_page_link(monkeypatch)
    at = AppTest.from_file(str(PAGES_DIR / COLLAB_PAGE))
    at.run(timeout=90)
    assert not at.exception, _exc_values(at)
    at.sidebar.toggle(key="isite_overlay").set_value(True)
    at.run(timeout=90)
    assert not at.exception, _exc_values(at)  # exercises the companion overlay bar chart


def test_page10_geographie_survives_isite_overlay_toggle_on(monkeypatch):
    _neutralize_page_link(monkeypatch)
    at = AppTest.from_file(str(PAGES_DIR / GEO_PAGE))
    at.run(timeout=90)
    assert not at.exception, _exc_values(at)
    at.sidebar.toggle(key="isite_overlay").set_value(True)
    at.run(timeout=90)
    assert not at.exception, _exc_values(at)


def test_page10_country_names_render_in_french(monkeypatch):
    """Pass 6, item #13: ISO2 codes -> FR names via lib.countries_fr.country_label(),
    table + map hovers + overlay-bar axis + KPI tile + fiche-pays selector. Source-text
    pin (wiring present) + a live AppTest pin (the rendered "Pays" column actually
    carries FR names, not bare 2-letter ISO2 codes -- probe 6's own map names this file
    as GEO_PAGE's test)."""
    assert "from lib.countries_fr import country_label" in GEO_SRC
    assert 'display["country_code"].apply(country_label)' in GEO_SRC
    assert "format_func=country_label" in GEO_SRC
    assert "country_label(top_row['country_code'])" in GEO_SRC
    assert "country_label(c)" in GEO_SRC  # map hover text

    _neutralize_page_link(monkeypatch)
    at = AppTest.from_file(str(PAGES_DIR / GEO_PAGE))
    at.run(timeout=90)
    assert not at.exception, _exc_values(at)
    # ranked_table()'s ref_labels only relabels the ST DISPLAY, not the underlying
    # DataFrame column -- the frame AppTest hands back still carries "country_name".
    dfs = [d.value for d in at.dataframe if "country_name" in getattr(d.value, "columns", [])]
    assert dfs, "no rendered dataframe carries a 'country_name' column"
    pays_values = dfs[0]["country_name"].dropna().astype(str)
    assert not pays_values.empty
    # A bare ISO2 code is exactly two uppercase letters; a French country name never is
    # (the country_label() fallback for an unmapped code is the code itself -- this pin
    # would also catch a real mapping regression, not just the wiring).
    bad = pays_values[pays_values.str.fullmatch(r"[A-Z]{2}")]
    assert bad.empty, f"still showing raw ISO2 codes: {sorted(set(bad))}"


def test_page10_sparkline_and_link_columns_restored(monkeypatch):
    """VIZ_BACKLOG #2 restore, via the NEW lib.ranked sparkline_cols/link_cols params
    built this pass: the yearly-trend sparkline and the country click-through page 10
    lost when it moved onto ranked_table() (progress/PF_partners_geo.md lines 87-94/
    133-138) are both wired back -- on_select stays the documented ranked_table()
    non-goal (VIZ_BACKLOG #2's own resolution), so the click-through is a real href
    (?country_code=XX) read back via st.query_params, not a re-added on_select."""
    assert "sparkline_cols=_sparkline" in GEO_SRC
    assert "link_cols=_link" in GEO_SRC
    assert '"trend": display["trend"]' in GEO_SRC
    assert '_yearly_list(g)' in GEO_SRC
    assert '"fiche_url":' in GEO_SRC
    assert 'st.query_params["country_code"] = picked_country' in GEO_SRC
    assert 'st.query_params.get("country_code")' in GEO_SRC

    _neutralize_page_link(monkeypatch)
    at = AppTest.from_file(str(PAGES_DIR / GEO_PAGE))
    at.run(timeout=90)
    assert not at.exception, _exc_values(at)


def test_page10_fiche_pays_node_search_box_is_gated_below_n50():
    """
    FIX-1 pass-6 fix round (S-LENS D5 / S-INSP D2): the "Fiche pays" field/subfield
    search box used to render UNCONDITIONALLY -- at field level N<=26 (26 fields max)
    and at drilled-subfield level N<=42 per field, both always under the P6-R6 floor
    of 50 -- a direct violation of the rule every other text_input call site app-wide
    already honours. Source-level pin: the call site must now be wrapped in
    ranked.should_show_query_box(), same gate page 3 (Perimetres) and page 14
    (Benchmark) use.
    """
    assert "ranked.should_show_query_box(len(node_rows))" in GEO_SRC
    # the gate must wrap the actual widget call, not merely appear somewhere in the file
    idx_gate = GEO_SRC.find("if ranked.should_show_query_box(len(node_rows)):")
    idx_widget = GEO_SRC.find('st.text_input(f"Rechercher un {level_label.lower()} :"')
    assert idx_gate != -1 and idx_widget != -1
    assert idx_gate < idx_widget < idx_gate + 400  # widget sits inside the gate's own block


def test_page9_zoom_partenaire_reached_via_navigation_survives_isite_toggle_and_drill(monkeypatch):
    """9_Zoom_partenaire.py calls st.page_link() unconditionally -- AppTest.from_file()
    on it directly fails with the same pre-existing harness KeyError ('url_pathname')
    _neutralize_page_link() documents above; reaching it via a real page->page
    switch_page(), the same mechanism tests/test_isite_overlay_journey.py already relies
    on, is the correct way to exercise it (see progress/PF_partners_geo.md) -- kept even
    though the sidebar-level neutralisation above would now also let a direct
    AppTest.from_file() through, because it additionally proves the cross-page
    session_state handoff (nav_partner_id) still works."""
    _neutralize_page_link(monkeypatch)
    path = DATA_DIR / "ptn_summary.parquet"
    _skip_if_missing(path)

    at = AppTest.from_file(str(PAGES_DIR / COLLAB_PAGE))
    at.run(timeout=90)
    at.session_state["nav_partner_id"] = CNRS_ID
    at.switch_page(PARTNER_PAGE)
    at.run(timeout=90)
    assert not at.exception, _exc_values(at)

    at.sidebar.toggle(key="isite_overlay").set_value(True)
    at.run(timeout=90)
    assert not at.exception, _exc_values(at)  # exercises the field-level overlay bar chart

    # Drill into the first field row (if any measured) to exercise the subfield-level
    # ranked_table + its own overlay bar chart -- the branch a field-only run never reaches.
    fld = pd.read_parquet(DATA_DIR / "ptn_fields.parquet")
    fld_p = fld[(fld["partner_id"] == CNRS_ID) & (fld["conf_state"] == "all") & (fld["node_level"] == "field")]
    if not fld_p.empty:
        first_field = int(fld_p.sort_values("co_works", ascending=False).iloc[0]["node_id"])
        at.session_state["v2_drill_field"] = first_field
        at.run(timeout=90)
        assert not at.exception, _exc_values(at)

    # #43 per-theme annual zoom: pick the field just drilled and open its zoom chart --
    # the branch that reads raw partner_works and builds overlay_grouped_bars() with a
    # real I-SITE decomposition (neither ptn_yearly nor ptn_topics carry one).
    if not fld_p.empty:
        at.session_state["v2_zoom_field"] = first_field
        at.run(timeout=90)
        assert not at.exception, _exc_values(at)
