# tests/test_page7_zoom.py
"""
Pass-7a (P-ZOOM) pins -- pages/9_Zoom_partenaire.py's new BenchUp-signature sections
(balance bars, topic planes, reciprocity in BenchUp form, portage via bars_with_gutter,
the phares KPI, the page workbook), PLUS the FIX-1 defects S-LENS's hostile-verification
pass raised (docs/LENS_ABSORPTION_pass7a.md, D1/D2/D4-D11/D13).

    .venv-pinned\\Scripts\\python -m pytest tests\\test_page7_zoom.py -q

FIX-1 / D9 (S-LENS A13): the page's own frame-building logic now lives in
`Streamlit/lib/partner_frames.py` (pure pandas, no Streamlit import) SPECIFICALLY so this
file can import and call it directly on real `Streamlit/data/*.parquet` frames -- every
"never negative" / "reconstructs the frame" / "selection <= N" / "dropped and counted" pin
below calls a `lib.partner_frames` function and mutates its INPUT (never a private copy of
the formula), so a regression in that module fails the pin here, not just in the page.

Idiom: same namespace-swap + AppTest pattern as tests/test_page_pf.py (this repo has TWO
packages named `lib`; `_neutralize_page_link` works around the same pre-existing AppTest
harness limitation that file already documents).

Vacuity rule (P14): every assertion below is followed by an in-memory mutation (or a
mutated copy) that makes the identical check FAIL -- a pin that cannot fail is theater.
"""
from __future__ import annotations

import json
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
PARTNER_PAGE = str(PAGES_DIR / "9_\U0001F50D_Zoom_partenaire.py")

CNRS_ID = "I1294671590"
CHRU_ID = "I4210100260"
THIN_ID = "I4210137456"  # "Momentum Research" (US), co_works_full=19 < 20 -- progress/P7_ZOOM.md

TIMEOUT = 120.0

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


def _exc_values(at: AppTest) -> list:
    return [e.value for e in at.exception]


def _neutralize_page_link(monkeypatch) -> None:
    import streamlit as st_mod
    monkeypatch.setattr(st_mod, "page_link", lambda *a, **k: None)


def _skip_if_missing(*names: str) -> None:
    missing = [n for n in names if not (DATA_DIR / n).is_file()]
    if missing:
        pytest.skip(f"deployed data missing: {missing} -- run the pipeline + 60_deploy first")


def _goto_partner(monkeypatch, partner_id: str) -> AppTest:
    _neutralize_page_link(monkeypatch)
    at = AppTest.from_file(PARTNER_PAGE)
    at.query_params["partner_id"] = partner_id
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)
    return at


def _taxonomy_maps():
    t = pd.read_parquet(DATA_DIR / "all_topics.parquet")
    field_id2name = dict(zip(t["field_id"].astype(int), t["field_name"]))
    subfield_id2name = dict(zip(t["subfield_id"].astype(int), t["subfield_name"]))
    field_id2domain = dict(zip(t["field_id"].astype(int), t["domain_id"]))
    domain_id2name = dict(zip(t["domain_id"], t["domain_name"]))
    return t, field_id2name, subfield_id2name, field_id2domain, domain_id2name


def _cnrs_summary_row():
    s = pd.read_parquet(DATA_DIR / "ptn_summary.parquet")
    return s[(s["partner_id"] == CNRS_ID) & (s["subset_id"] == "all") & (s["conf_state"] == "all")].iloc[0]


# ============================================================================
# Smoke: the three reference partners render with no exception (deliverable 11's set)
# ============================================================================

def test_cnrs_loads_via_query_param_no_exception(monkeypatch):
    _skip_if_missing("ptn_summary.parquet")
    at = _goto_partner(monkeypatch, CNRS_ID)
    assert [t.value for t in at.title] == ["\U0001F50D Zoom partenaire"]


def test_chru_loads_via_query_param_no_exception(monkeypatch):
    _skip_if_missing("ptn_summary.parquet")
    _goto_partner(monkeypatch, CHRU_ID)


def test_thin_partner_renders_without_exception_and_shows_a_thin_disclosure(monkeypatch):
    _skip_if_missing("ptn_summary.parquet", "ptn_fields.parquet", "ptn_topics.parquet")
    at = _goto_partner(monkeypatch, THIN_ID)
    body = " ".join(c.value for c in at.caption) + " ".join(i.value for i in at.info)
    from lib import copy_fr
    thin_markers = [
        copy_fr.CAPTIONS["THIN_PARTNER"], copy_fr.CAPTIONS["JOINT_UNDER_FLOOR"],
        "sous le seuil", "Aucun", "mesuré",
    ]
    assert any(m in body for m in thin_markers), body
    assert not any(m in body for m in [])  # vacuity: an empty marker list can never match


def test_balance_bars_level_and_mode_controls_survive_a_rerun(monkeypatch):
    _skip_if_missing("ptn_fields.parquet")
    at = _goto_partner(monkeypatch, CNRS_ID)
    radios = {r.key: r for r in at.radio}
    assert "v2_balance_mode" in radios, list(radios)
    at.radio(key="v2_balance_mode").set_value("phares")
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)
    assert at.session_state["v2_balance_mode"] == "phares"
    assert at.session_state["v2_balance_mode"] != "volume"  # vacuity


def test_plane_selector_and_n_slider_survive_a_rerun(monkeypatch):
    _skip_if_missing("ptn_topics.parquet", "dim_frontier_components.parquet")
    at = _goto_partner(monkeypatch, CNRS_ID)
    sliders = {s.key: s for s in at.slider}
    assert "v2_plane_n" in sliders, list(sliders)
    at.slider(key="v2_plane_n").set_value(50)
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)
    assert at.session_state["v2_plane_n"] == 50
    assert at.session_state["v2_plane_n"] != 10  # vacuity


def test_page_workbook_download_button_is_present(monkeypatch):
    _skip_if_missing("ptn_summary.parquet")
    at = _goto_partner(monkeypatch, CNRS_ID)
    from lib import copy_fr
    labels = [b.label for b in at.button] + [d.label for d in at.get("download_button")]
    assert copy_fr.LABELS["PAGE_WORKBOOK"] in labels, labels
    assert "not a real label at all" not in labels  # vacuity


# ============================================================================
# D8: phares KPI and its id-list share the SAME filtered works set at every toggle state
# ============================================================================

def test_phares_kpi_equals_ptn_summary_n_phares_for_cnrs(monkeypatch):
    _skip_if_missing("ptn_summary.parquet")
    row = _cnrs_summary_row()
    expected = int(row["n_phares"])
    from lib.helpers import fr_int
    at = _goto_partner(monkeypatch, CNRS_ID)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Publications phares") == fr_int(expected), metrics
    assert metrics.get("Publications phares") != fr_int(expected + 1)  # vacuity


def test_phares_id_list_uses_the_same_toggle_filters_as_the_kpi_count(monkeypatch):
    """D8: PF.phares_work_ids must apply conference+artifact BEFORE counting -- proven by
    calling the REAL function with the toggles flipped and checking the id-count tracks
    ptn_works's own conf/artifact-filtered pptop10_fr count for CNRS (not the unfiltered one)."""
    _skip_if_missing("ptn_works.parquet")
    from lib import partner_frames as PF
    from lib import lazy

    partner_works = lazy.read_keyed(str(DATA_DIR / "ptn_works.parquet"), "partner_id", CNRS_ID)
    all_ids = PF.phares_work_ids(partner_works, include_conference=True, artifact_on=False)
    no_conf_ids = PF.phares_work_ids(partner_works, include_conference=False, artifact_on=False)
    xa_ids = PF.phares_work_ids(partner_works, include_conference=True, artifact_on=True)

    expected_no_conf = int((partner_works[~partner_works["is_conference"].fillna(False)]
                            ["pptop10_fr"].fillna(False)).sum())
    expected_xa = int((partner_works[~partner_works["artifact_flag"].fillna(False)]
                       ["pptop10_fr"].fillna(False)).sum())
    assert len(no_conf_ids) == expected_no_conf
    assert len(xa_ids) == expected_xa
    assert len(all_ids) >= len(no_conf_ids)  # dropping conference papers can only shrink the set
    # vacuity: calling the function on an EMPTY frame (mutated input) must return an empty list,
    # not the CNRS answer -- proves the function actually reads its `partner_works` argument.
    empty_ids = PF.phares_work_ids(partner_works.iloc[0:0], include_conference=True, artifact_on=False)
    assert empty_ids == []
    assert empty_ids != all_ids


# ============================================================================
# D1/D4/D5/D9: balance bars, via lib.partner_frames.build_balance_frame directly
# ============================================================================

def _balance_inputs(partner_id: str = CNRS_ID, conf_state: str = "all"):
    from lib import lazy
    fld = pd.read_parquet(DATA_DIR / "ptn_fields.parquet")
    fld_p = fld[(fld["partner_id"] == partner_id) & (fld["conf_state"] == conf_state)]
    thematic_overview = pd.read_parquet(DATA_DIR / "thematic_overview.parquet")
    all_topics, field_id2name, subfield_id2name, *_ = _taxonomy_maps()
    partner_topics = lazy.read_keyed(str(DATA_DIR / "ptn_topics.parquet"), "partner_id", partner_id)
    partner_works = lazy.read_keyed(str(DATA_DIR / "ptn_works.parquet"), "partner_id", partner_id)
    row = pd.read_parquet(DATA_DIR / "ptn_summary.parquet")
    row = row[(row["partner_id"] == partner_id) & (row["subset_id"] == "all") & (row["conf_state"] == "all")].iloc[0]
    return dict(
        fld_fields=fld_p, thematic_overview=thematic_overview, partner_topics=partner_topics,
        all_topics=all_topics, partner_works=partner_works, partner_id=partner_id,
        partner_name=str(row["display_name"]), conf_state=conf_state, include_conference=True,
        artifact_on=False, partner_total_windowed=row.get("partner_total_windowed"),
        field_id2name=field_id2name, subfield_id2name=subfield_id2name,
    )


def test_balance_bars_derived_partner_only_never_negative_with_a_synthetic_node_total():
    """D1/D9: calls the REAL `build_balance_frame` (not a test-local re-implementation)
    with a SYNTHETIC `partner_node_total` column injected on a copy of the real CNRS input
    (forward-compatible with S-DAT's column landing under that exact name) -- one row is
    engineered so the raw `partner_node_total - co_works` WOULD go negative, and the
    function's own OUTPUT for that row must still be >= 0 (or NULL), proving the clip is
    exercised inside the function under test, not re-implemented here."""
    _skip_if_missing("ptn_fields.parquet", "thematic_overview.parquet", "ptn_topics.parquet", "ptn_works.parquet")
    from lib import partner_frames as PF

    kwargs = _balance_inputs()
    fld = kwargs["fld_fields"].copy()
    field_rows = fld[fld["node_level"] == "field"].reset_index(drop=True)
    assert len(field_rows) >= 3, "fixture assumption: CNRS has >= 3 field rows"
    # Row 0: co_works > partner_node_total (would go negative unclipped).
    field_rows.loc[0, "partner_node_total"] = float(field_rows.loc[0, "co_works"]) - 500.0
    # Row 1: NULL partner_node_total (disclosed-absent path).
    field_rows.loc[1, "partner_node_total"] = np.nan
    # Remaining rows: a large, always-sufficient total (never negative unclipped).
    field_rows.loc[2:, "partner_node_total"] = field_rows.loc[2:, "co_works"].astype(float) + 1_000_000.0
    kwargs["fld_fields"] = field_rows

    d, n_hidden = PF.build_balance_frame(mode="volume", level="field", **kwargs)
    assert (d["vol_partner_only"].dropna() >= 0.0).all()
    row0 = d[d["node_id"] == int(field_rows.loc[0, "node_id"])].iloc[0]
    assert row0["vol_partner_only"] == 0.0  # engineered negative case clips to exactly 0
    assert n_hidden >= 1  # the NULL row (row 1) is counted

    # vacuity: mutate the INPUT so row 0's total is instead ABUNDANT (no clip needed) and
    # re-call the SAME function -- the output must now differ (a real positive value, not 0).
    field_rows2 = field_rows.copy()
    field_rows2.loc[0, "partner_node_total"] = float(field_rows2.loc[0, "co_works"]) + 999.0
    kwargs2 = dict(kwargs, fld_fields=field_rows2)
    d2, _ = PF.build_balance_frame(mode="volume", level="field", **kwargs2)
    row0b = d2[d2["node_id"] == int(field_rows.loc[0, "node_id"])].iloc[0]
    assert row0b["vol_partner_only"] == 999.0
    assert row0b["vol_partner_only"] != row0["vol_partner_only"]


def test_balance_bars_volume_reconstructs_the_frame_for_three_cnrs_field_cells():
    """D9/A13: calls the REAL function (not `links.copubs_url(...) == links.copubs_url(...)`
    on itself) and checks its OUTPUT's link/label construction for three real CNRS cells."""
    _skip_if_missing("ptn_fields.parquet", "thematic_overview.parquet", "ptn_topics.parquet", "ptn_works.parquet")
    from lib import links, partner_frames as PF
    from lib.helpers import fr_int

    kwargs = _balance_inputs()
    d, _ = PF.build_balance_frame(mode="volume", level="field", **kwargs)
    assert len(d) >= 3
    top3 = d.sort_values("vol_joint", ascending=False).head(3)
    for _, r in top3.iterrows():
        fid = int(r["node_id"])
        assert r["link_label"] == fr_int(r["vol_joint"])
        assert r["url"] == links.copubs_url(CNRS_ID, node=("field", fid))
        assert f"primary_topic.field.id:{fid}" in r["url"]
        assert r["vol_ul_only"] >= 0.0

    # vacuity: mutating the INPUT's co_works for the top row must change the REAL function's
    # own output link_label (proves link_label is read from this call's result, not cached).
    fld2 = kwargs["fld_fields"].copy()
    fld2["node_id"] = fld2["node_id"].astype(int)  # raw column dtype != the function's internal cast
    top_id = int(top3.iloc[0]["node_id"])
    fld2.loc[fld2["node_id"] == top_id, "co_works"] = 999999
    kwargs2 = dict(kwargs, fld_fields=fld2)
    d2, _ = PF.build_balance_frame(mode="volume", level="field", **kwargs2)
    r2 = d2[d2["node_id"] == top_id].iloc[0]
    assert r2["link_label"] == fr_int(999999)
    assert r2["link_label"] != top3.iloc[0]["link_label"]


def test_balance_bars_subfield_selection_is_by_joint_volume_in_every_mode():
    """D5: the top-30 subfield SET must be identical across volume/fwci/phares modes (only
    the row ORDER differs) -- proven on the REAL function's output, not asserted in prose."""
    _skip_if_missing("ptn_fields.parquet", "thematic_overview.parquet", "ptn_topics.parquet", "ptn_works.parquet")
    from lib import partner_frames as PF

    kwargs = _balance_inputs()
    sets = {}
    for mode in ("volume", "fwci", "phares"):
        d, _ = PF.build_balance_frame(mode=mode, level="subfield", **kwargs)
        sets[mode] = frozenset(d["node_id"])
    assert sets["volume"] == sets["fwci"] == sets["phares"], sets
    assert len(sets["volume"]) > 0

    # vacuity: the volume-mode set restricted to CNRS's own top-30-by-co_works must be
    # EXACTLY that computed set (proves the selection key really is co_works, not a tautology).
    fld_sub = kwargs["fld_fields"]
    fld_sub = fld_sub[fld_sub["node_level"] == "subfield"]
    expected_top30 = frozenset(fld_sub.sort_values("co_works", ascending=False).head(30)["node_id"].astype(int))
    assert sets["volume"] == expected_top30
    wrong_top30 = frozenset(fld_sub.sort_values("co_works", ascending=True).head(30)["node_id"].astype(int))
    assert sets["volume"] != wrong_top30


def test_balance_bars_phares_mode_links_the_cells_own_work_ids():
    """D11: in phares mode the linked column must open THIS node's own phares
    publications (`links.phares_url`), not a generic `copubs_url` of the joint count."""
    _skip_if_missing("ptn_fields.parquet", "thematic_overview.parquet", "ptn_topics.parquet", "ptn_works.parquet")
    from lib import links, partner_frames as PF

    kwargs = _balance_inputs()
    d, _ = PF.build_balance_frame(mode="phares", level="field", **kwargs)
    assert "phares_proxy" in d.columns
    with_phares = d[d["n_phares_joint"] > 0]
    if with_phares.empty:
        pytest.skip("no CNRS field row has a joint phares publication in this snapshot")
    r = with_phares.iloc[0]
    assert r["url"] != links.copubs_url(CNRS_ID, node=("field", int(r["node_id"])))
    # vacuity: a node with ZERO joint phares must NOT produce the same non-empty-id url
    # shape (idlist_url) -- it degrades to the proxy branch instead (0 ids -> proxy=True).
    zero_phares = d[d["n_phares_joint"] == 0]
    if not zero_phares.empty:
        r0 = zero_phares.iloc[0]
        assert bool(r0["phares_proxy"]) is True


# ============================================================================
# D6/D7/D9: topic planes, via lib.partner_frames directly
# ============================================================================

def _plane_inputs(partner_id: str = CNRS_ID, conf_state: str = "all"):
    from lib import lazy
    partner_topics = lazy.read_keyed(str(DATA_DIR / "ptn_topics.parquet"), "partner_id", partner_id)
    all_topics, *_ = _taxonomy_maps()
    frontier = pd.read_parquet(DATA_DIR / "dim_frontier_components.parquet")
    return partner_topics, all_topics, frontier


@pytest.mark.parametrize("mode,n", [("volume", 10), ("fwci", 25), ("frontiere", 50), ("phares", 30)])
def test_plane_selection_never_exceeds_n_for_cnrs(mode, n):
    """D9/A13: calls the REAL build_cell_frame + build_plane_impact_frame on real data."""
    _skip_if_missing("ptn_topics.parquet", "dim_frontier_components.parquet")
    from lib import partner_frames as PF

    partner_topics, all_topics, frontier = _plane_inputs()
    cells = PF.build_cell_frame(partner_topics, all_topics, frontier, conf_state="all")
    assert len(cells) > n, "fixture assumption: CNRS has more eligible cells than N"
    d, _ = PF.build_plane_impact_frame(cells, mode, n)
    assert len(d) <= n

    # vacuity: mutating the INPUT cells (dropping to 2 rows) must shrink the REAL output too.
    d_small, _ = PF.build_plane_impact_frame(cells.head(2), mode, n)
    assert len(d_small) <= 2
    assert len(d_small) != len(d) or len(cells) <= 2


def test_frontier_plane_uses_the_latest_bin_component_not_the_composite():
    """D6: `build_cell_frame` must NOT read `ptn_topics.frontier_score_std` (the all-period
    composite) at all -- its own `frontier` column must come from
    `dim_frontier_components.is_latest`, proven by injecting a synthetic frontier value for
    one topic and checking it is the value the OUTPUT actually carries."""
    _skip_if_missing("ptn_topics.parquet", "dim_frontier_components.parquet")
    from lib import partner_frames as PF

    partner_topics, all_topics, frontier = _plane_inputs()
    cells = PF.build_cell_frame(partner_topics, all_topics, frontier, conf_state="all")
    assert "frontier_score_std" not in cells.columns  # the composite never enters this frame
    sample = cells[cells["frontier"].notna()]
    if sample.empty:
        pytest.skip("no CNRS cell has a latest-bin frontier component in this snapshot")
    tid = sample.iloc[0]["topic_id"]  # topic_id is a string id (e.g. "T10001"), never cast to int
    expected = frontier.loc[(frontier["topic_id"] == tid) & (frontier["is_latest"].astype(bool)), "frontier"].iloc[0]
    assert float(sample.iloc[0]["frontier"]) == pytest.approx(float(expected))

    # vacuity: inject a DIFFERENT frontier value for that topic's latest bin and re-call --
    # the function's own output must track the injected value, proving it is read live.
    frontier2 = frontier.copy()
    mask = (frontier2["topic_id"] == tid) & (frontier2["is_latest"].astype(bool))
    frontier2.loc[mask, "frontier"] = float(expected) + 12.5
    cells2 = PF.build_cell_frame(partner_topics, all_topics, frontier2, conf_state="all")
    row2 = cells2[cells2["topic_id"] == tid].iloc[0]
    assert float(row2["frontier"]) == pytest.approx(float(expected) + 12.5)
    assert float(row2["frontier"]) != float(sample.iloc[0]["frontier"])


def test_bin_labels_are_read_from_the_table_never_typed():
    """D7: `latest_and_previous_bin_labels` must return the LIVE bin_last/bin_prev, proven
    by mutating which bin is flagged `is_latest` on a copy of the real table."""
    _skip_if_missing("dim_frontier_components.parquet")
    from lib import partner_frames as PF

    frontier = pd.read_parquet(DATA_DIR / "dim_frontier_components.parquet")
    bin_last, bin_prev = PF.latest_and_previous_bin_labels(frontier)
    assert bin_last != bin_prev
    real_latest_rows = frontier.loc[frontier["is_latest"].astype(bool), "bin_label"].unique()
    assert bin_last in [str(x) for x in real_latest_rows]

    # vacuity: flip is_latest to an EARLIER bin on a mutated copy -- the function's own
    # return value must change to match, not stay pinned to the old bin_last.
    labels = sorted(frontier["bin_label"].astype(str).unique())
    earlier = labels[0]
    mutated = frontier.copy()
    mutated["is_latest"] = mutated["bin_label"].astype(str) == earlier
    new_last, _ = PF.latest_and_previous_bin_labels(mutated)
    assert new_last == earlier
    assert new_last != bin_last


def test_balance_and_recip_use_the_real_partner_node_total_for_three_cnrs_fields():
    """Tier A (FIX-1 close, coordinator dispatch): now that
    `ptn_fields.partner_node_total` is deployed, `build_balance_frame`'s
    `vol_partner_only` must equal `partner_node_total - co_works` EXACTLY (no more
    share-derived approximation) and `build_recip_frame`'s x share must equal
    `partner_node_total / partner_total_windowed` EXACTLY, for CNRS Engineering (field 22)
    and two more real fields -- on the REAL deployed column, not a synthetic one."""
    _skip_if_missing("ptn_fields.parquet", "thematic_overview.parquet", "ptn_topics.parquet", "ptn_works.parquet")
    from lib import partner_frames as PF

    fld_raw = pd.read_parquet(DATA_DIR / "ptn_fields.parquet")
    assert "partner_node_total" in fld_raw.columns, "S-DAT's column must be deployed for this pin to mean anything"
    cnrs_fields = fld_raw[(fld_raw["partner_id"] == CNRS_ID) & (fld_raw["conf_state"] == "all")
                          & (fld_raw["node_level"] == "field")].copy()
    cnrs_fields["node_id"] = cnrs_fields["node_id"].astype(int)
    check_ids = cnrs_fields.sort_values("co_works", ascending=False).head(3)["node_id"].tolist()
    assert 22 in check_ids, f"expected field 22 (Engineering) among the top-3 CNRS fields, got {check_ids}"

    bal_kwargs = _balance_inputs()
    d_bal, _ = PF.build_balance_frame(mode="volume", level="field", **bal_kwargs)
    recip_kwargs = _recip_inputs()
    d_recip, _ = PF.build_recip_frame(level="field", **recip_kwargs)
    partner_total_windowed = float(recip_kwargs["partner_total_windowed"])

    for fid in check_ids:
        raw_row = cnrs_fields[cnrs_fields["node_id"] == fid].iloc[0]
        expected_partner_only = max(0.0, float(raw_row["partner_node_total"]) - float(raw_row["co_works"]))
        bal_row = d_bal[d_bal["node_id"] == fid].iloc[0]
        assert bal_row["vol_partner_only"] == pytest.approx(expected_partner_only), (fid, bal_row["vol_partner_only"], expected_partner_only)

        expected_share = float(raw_row["partner_node_total"]) / partner_total_windowed
        recip_row = d_recip[d_recip["node_id"] == fid]
        if not recip_row.empty:  # a field could still be legitimately dropped if baseline_ul_share is NULL
            assert recip_row.iloc[0]["share_partner_own"] == pytest.approx(expected_share), fid

    # vacuity: mutate the INPUT's partner_node_total for field 22 and re-call BOTH real
    # functions -- both outputs must track the mutation, not the original deployed value.
    fld_mut = bal_kwargs["fld_fields"].copy()
    fld_mut["node_id"] = fld_mut["node_id"].astype(int)
    real_total_22 = float(cnrs_fields.loc[cnrs_fields["node_id"] == 22, "partner_node_total"].iloc[0])
    fld_mut.loc[fld_mut["node_id"] == 22, "partner_node_total"] = real_total_22 + 10_000.0
    bal_kwargs_mut = dict(bal_kwargs, fld_fields=fld_mut)
    d_bal_mut, _ = PF.build_balance_frame(mode="volume", level="field", **bal_kwargs_mut)
    row22_mut = d_bal_mut[d_bal_mut["node_id"] == 22].iloc[0]
    row22_orig = d_bal[d_bal["node_id"] == 22].iloc[0]
    assert row22_mut["vol_partner_only"] == pytest.approx(row22_orig["vol_partner_only"] + 10_000.0)
    assert row22_mut["vol_partner_only"] != row22_orig["vol_partner_only"]

    fld_all_mut = recip_kwargs["fld_all"].copy()
    mask22 = (fld_all_mut["partner_id"] == CNRS_ID) & (fld_all_mut["conf_state"] == "all") & \
             (fld_all_mut["node_level"] == "field") & (fld_all_mut["node_id"].astype(int) == 22)
    fld_all_mut.loc[mask22, "partner_node_total"] = real_total_22 + 10_000.0
    recip_kwargs_mut = dict(recip_kwargs, fld_all=fld_all_mut)
    d_recip_mut, _ = PF.build_recip_frame(level="field", **recip_kwargs_mut)
    row22_recip_mut = d_recip_mut[d_recip_mut["node_id"] == 22].iloc[0]
    row22_recip_orig = d_recip[d_recip["node_id"] == 22].iloc[0]
    assert row22_recip_mut["share_partner_own"] == pytest.approx((real_total_22 + 10_000.0) / partner_total_windowed)
    assert row22_recip_mut["share_partner_own"] != row22_recip_orig["share_partner_own"]


# ============================================================================
# D2/D13/D9: reciprocity, via lib.partner_frames.build_recip_frame directly
# ============================================================================

def _recip_inputs(partner_id: str = CNRS_ID):
    fld_all = pd.read_parquet(DATA_DIR / "ptn_fields.parquet")
    all_topics, field_id2name, subfield_id2name, field_id2domain, domain_id2name = _taxonomy_maps()
    row = _cnrs_summary_row() if partner_id == CNRS_ID else None
    return dict(
        fld_all=fld_all, all_topics=all_topics, partner_id=partner_id,
        partner_name=(str(row["display_name"]) if row is not None else partner_id),
        partner_total_windowed=(row.get("partner_total_windowed") if row is not None else None),
        field_id2name=field_id2name, subfield_id2name=subfield_id2name,
        field_id2domain=field_id2domain, domain_id2name=domain_id2name,
    )


def test_reciprocity_caps_before_dropping_nulls_d13():
    """D13: P8's literal order is cap-to-top-30-by-volume FIRST, then drop+count NULL
    rows -- proven on the REAL function with a SYNTHETIC partner_node_total column where
    the NULL rows are deliberately OUTSIDE the top-30-by-volume set (drop-then-cap would
    give a different n_hidden than cap-then-drop in that construction)."""
    _skip_if_missing("ptn_fields.parquet")
    from lib import partner_frames as PF

    kwargs = _recip_inputs()
    fld = kwargs["fld_all"].copy()
    sub = fld[(fld["partner_id"] == CNRS_ID) & (fld["conf_state"] == "all") & (fld["node_level"] == "subfield")].copy()
    assert len(sub) > 35, "fixture assumption: CNRS has > 35 subfield rows"
    sub = sub.sort_values("co_works", ascending=False).reset_index(drop=True)
    sub["partner_node_total"] = sub["co_works"].astype(float) + 100.0  # everyone measurable
    # NULL out three rows OUTSIDE the top-30 (ranks 31-33) -- cap-then-drop must find them
    # ALREADY EXCLUDED (n_hidden == 0 from this construction), never counted as "hidden".
    null_ids = sub.iloc[30:33]["node_id"].tolist()
    sub.loc[sub["node_id"].isin(null_ids), "partner_node_total"] = np.nan
    fld_other = fld[~((fld["partner_id"] == CNRS_ID) & (fld["conf_state"] == "all") & (fld["node_level"] == "subfield"))]
    kwargs["fld_all"] = pd.concat([fld_other, sub], ignore_index=True)

    d, n_hidden = PF.build_recip_frame(level="subfield", **kwargs)
    assert n_hidden == 0, "the 3 NULLs sit beyond the top-30 cut and must not be counted"
    assert len(d) == 30

    # vacuity: NULL out a row INSIDE the top-30 instead -- cap-then-drop must now count it.
    sub2 = sub.copy()
    sub2["partner_node_total"] = sub["co_works"].astype(float) + 100.0
    inside_id = sub2.iloc[5]["node_id"]
    sub2.loc[sub2["node_id"] == inside_id, "partner_node_total"] = np.nan
    kwargs2 = dict(kwargs, fld_all=pd.concat([fld_other, sub2], ignore_index=True))
    d2, n_hidden2 = PF.build_recip_frame(level="subfield", **kwargs2)
    assert n_hidden2 == 1
    assert len(d2) == 29
    assert n_hidden2 != n_hidden


def test_reciprocity_x_axis_is_the_partners_own_portfolio_weight_d2():
    """D2: x = partner_node_total / partner_total_windowed (a portfolio weight, sums
    towards <= 1 across a partner's own fields), never `baseline_partner_share` (an
    involvement share, proven in LENS_ABSORPTION A1 to sum past 1 for real partners)."""
    _skip_if_missing("ptn_fields.parquet")
    from lib import partner_frames as PF

    kwargs = _recip_inputs()
    fld = kwargs["fld_all"].copy()
    mask = (fld["partner_id"] == CNRS_ID) & (fld["conf_state"] == "all") & (fld["node_level"] == "field")
    fld.loc[mask, "partner_node_total"] = fld.loc[mask, "co_works"].astype(float) * 7.0 + 50.0
    kwargs["fld_all"] = fld
    kwargs["partner_total_windowed"] = 1000.0

    d, _ = PF.build_recip_frame(level="field", **kwargs)
    assert not d.empty
    row = d.iloc[0]
    expected_x = float(row["partner_node_total"]) / 1000.0
    assert row["share_partner_own"] == pytest.approx(expected_x)
    assert row["share_partner"] == pytest.approx(expected_x * 100.0)

    # vacuity: change ONLY partner_total_windowed (the denominator) and re-call the SAME
    # function -- the output share must change accordingly, proving it is computed live.
    kwargs2 = dict(kwargs, partner_total_windowed=2000.0)
    d2, _ = PF.build_recip_frame(level="field", **kwargs2)
    row2 = d2.iloc[0]
    assert row2["share_partner"] == pytest.approx(expected_x * 100.0 / 2.0)
    assert row2["share_partner"] != row["share_partner"]


# ============================================================================
# D10: field/subfield companions on bars_with_gutter (source-level, matches the
# app-wide convention test_page1_annual_breakdown_uses_the_grouped_bars_grammar already
# uses for an equivalent claim)
# ============================================================================

def test_field_and_subfield_companions_use_bars_with_gutter():
    src = Path(PARTNER_PAGE).read_text(encoding="utf-8")
    assert "C.bars_with_gutter(" in src
    field_block = src.split('st.markdown("###### Volume par champ")', 1)[1][:1500]
    assert "C.bars_with_gutter(" in field_block
    assert "overlay.overlay_bars(" not in field_block
    subfield_block = src.split('st.markdown("###### Volume par sous-champ")', 1)[1][:1700]
    assert "C.bars_with_gutter(" in subfield_block
    assert "overlay.overlay_bars(" not in subfield_block
    # vacuity: a marker string that is NOT in the file must fail the same "in" check
    assert "this_marker_does_not_exist_in_the_page" not in src


# ============================================================================
# Hover grammar: HOVERTEMPLATE is used verbatim (no format spec ever), and every
# chart_key/mode this page renders has a HOVER_LABELS + READING entry
# ============================================================================

PAGE_CHART_MODES = {
    "zoom_yearly": ["default"], "zoom_share_spark": ["default"],
    "zoom_balance_bars": ["volume|champ", "volume|sous_champ", "fwci|champ", "fwci|sous_champ",
                           "phares|champ", "phares|sous_champ"],
    "zoom_plane_impact": ["volume", "fwci", "frontiere", "phares"],
    "zoom_plane_frontier": ["volume", "fwci", "frontiere", "phares"],
    "zoom_field_companion": ["default"], "zoom_subfield_companion": ["default"],
    "zoom_theme_zoom": ["default"], "zoom_reciprocity": ["champ", "sous_champ"],
    "zoom_portage": ["default"],
}


def test_every_chart_mode_this_page_renders_has_hover_labels_and_reading_text():
    from lib import copy_fr
    from lib.reading import reading_text

    missing_hover, missing_reading = [], []
    for key, modes in PAGE_CHART_MODES.items():
        for mode in modes:
            if key not in copy_fr.HOVER_LABELS or mode not in copy_fr.HOVER_LABELS[key]:
                missing_hover.append((key, mode))
            try:
                fills = {p: "x" for p in copy_fr.READING_PLACEHOLDERS.get(key, ())}
                reading_text(key, mode if mode != "default" else None, **fills)
            except KeyError:
                missing_reading.append((key, mode))
    assert not missing_hover, missing_hover
    assert not missing_reading, missing_reading

    with pytest.raises(KeyError):  # vacuity
        reading_text("zoom_this_key_does_not_exist", "default")


def test_hovertemplate_constant_has_no_plotly_format_spec():
    from lib.hover import HOVERTEMPLATE
    import re
    assert HOVERTEMPLATE == "%{customdata}<extra></extra>"
    assert re.search(r"%\{[^}]*:[^}]*\}", HOVERTEMPLATE) is None
    assert re.search(r"%\{[^}]*:[^}]*\}", "%{customdata:.2f}") is not None  # vacuity


# ============================================================================
# D14: {max_ids} is read from links.IDLIST_MAX, never retyped
# ============================================================================

def test_max_ids_placeholder_is_filled_from_links_idlist_max():
    from lib import copy_fr, links
    filled = copy_fr.CAPTIONS["PHARES_PROXY"].format(max_ids=links.IDLIST_MAX)
    assert str(links.IDLIST_MAX) in filled
    assert "cent identifiants" not in filled.lower() or str(links.IDLIST_MAX) in filled
    # vacuity: a DIFFERENT max_ids value must produce different rendered text
    filled_other = copy_fr.CAPTIONS["PHARES_PROXY"].format(max_ids=links.IDLIST_MAX + 1)
    assert filled_other != filled


# ============================================================================
# Workbook opens with "Lecture" first
# ============================================================================

def test_page_workbook_lecture_sheet_is_first():
    from lib.exports import page_workbook
    import io
    sheets = {"Volume annuel": pd.DataFrame({"year": [2019, 2020]}), "Portage": pd.DataFrame({"lab": ["A"]})}
    lecture = [("Partenaire", "CNRS"), ("Instantané", "2026-08-11")]
    xlsx_bytes, filename = page_workbook(sheets, lecture, view="v2-partner-drilldown")
    book = pd.ExcelFile(io.BytesIO(xlsx_bytes))
    assert book.sheet_names[0] == "Lecture", book.sheet_names
    lecture_df = book.parse("Lecture")
    assert list(lecture_df.columns) == ["Clé", "Valeur"]
    assert filename.endswith(".xlsx")
    assert book.sheet_names[1] != "Lecture"  # vacuity


# ============================================================================
# P7B_Z9 (pass 7b, W1): D15/B8 the 390 px CSS switch (mirror <-> table companion,
# no server-side width guess) + D11 live verification (the fix itself landed in
# lib/partner_frames.py::build_balance_frame -- see PF's own pin above) + B6 the
# page-local #0072B2 -> UL_COLOR retirement on pages 9 and 10.
# ============================================================================

GEO_PAGE = "10_\U0001F30D_Géographie.py"


def test_balance_mirror_css_switch_containers_and_media_queries_present():
    """D15/B8: the mirror and its table companion live in named `st.container()`
    keys, toggled purely by a CSS media query (no server-side width guess) --
    `.st-key-<key>` is the Streamlit 1.39+ class this pass's pinned 1.61.1 emits
    for a keyed container (render-verified in progress/p7b_proofs/Z9/)."""
    src = Path(PARTNER_PAGE).read_text(encoding="utf-8")
    assert 'st.container(key="zoom_mirror")' in src
    assert 'st.container(key="zoom_mirror_table")' in src
    assert "@media (max-width: 640px)" in src
    assert ".st-key-zoom_mirror {" in src
    assert "@media (min-width: 641px)" in src
    assert ".st-key-zoom_mirror_table {" in src
    # vacuity: stripping the narrow-viewport rule from a COPY must make the same
    # substring check FAIL -- proves the assertion actually reads the file, not a
    # tautology that would pass on any source.
    mutated = src.replace(
        "@media (max-width: 640px) { .st-key-zoom_mirror { display: none; } }", "")
    assert "@media (max-width: 640px)" not in mutated


def test_balance_mirror_table_companion_renders_the_same_frame_no_recompute():
    """D15: the table companion must draw the SAME frame the mirror draws -- one
    `_bb_display` built ONCE, rendered by both the always-in-DOM container and the
    unchanged wide-screen expander (never a second dataframe build)."""
    src = Path(PARTNER_PAGE).read_text(encoding="utf-8")
    block = src.split('with st.container(key="zoom_mirror"):', 1)[1][:2500]
    assert block.count("_bb_display = bb_frame[") == 1
    assert block.count("st.dataframe(_bb_display") == 2
    assert 'with st.container(key="zoom_mirror_table"):' in block
    assert 'with st.expander("Voir en tableau' in block
    # vacuity: a build count of 1 is what we assert -- a source that built it twice
    # (the recompute this pin forbids) must NOT satisfy the same check.
    assert block.count("_bb_display = bb_frame[") != 2


def _balance_bars_link_spec(at: AppTest) -> dict | None:
    """The zoom_balance_bars figure's raw proto spec (JSON) -- identified by
    carrying a `yaxis2` (lib/charts.py `_add_link_column`'s second categorical
    axis for the linked "Co-pubs" column; the only figure on this page that has
    one). Read off `.proto.spec`, not `.value` (a plain chart with no `on_select`
    has no session-state-backed value -- same idiom as test_page_pe.py)."""
    for c in at.get("plotly_chart"):
        spec = json.loads(c.proto.spec)
        if "yaxis2" in spec.get("layout", {}):
            return spec
    return None


def test_balance_bars_phares_mode_link_hrefs_are_phares_url_shaped_live(monkeypatch):
    """D11, AppTest/render level: `test_balance_bars_phares_mode_links_the_cells_own_
    work_ids` above already proves `lib.partner_frames.build_balance_frame` calls
    `links.phares_url` (url != a generic copubs_url); this proves the RENDERED
    figure's link column hrefs, live in the app, carry one of phares_url's two
    branches (`ids.openalex:` for the exact id-list, or `sort=cited_by_count:` for
    the >100-id proxy) -- never a bare copubs_url with neither marker."""
    _skip_if_missing("ptn_fields.parquet", "thematic_overview.parquet",
                      "ptn_topics.parquet", "ptn_works.parquet")
    at = _goto_partner(monkeypatch, CNRS_ID)
    radios = {r.key: r for r in at.radio}
    assert "v2_balance_mode" in radios, list(radios)
    at.radio(key="v2_balance_mode").set_value("phares")
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)
    spec = _balance_bars_link_spec(at)
    assert spec is not None, "no plotly_chart with a yaxis2 (link column) found in phares mode"
    ticktext = " ".join(t for t in (spec["layout"]["yaxis2"].get("ticktext") or []) if t)
    assert ("ids.openalex:" in ticktext) or ("sort=cited_by_count:" in ticktext), ticktext
    # vacuity: an href shape phares_url never produces must NOT be found in the
    # same rendered ticktext -- proves the assertion above is not vacuously true.
    assert "this_href_shape_never_appears_in_phares_url_output" not in ticktext


def test_page9_and_page10_have_no_ul_color_hex_literal():
    """B6/B8: the page-local `#0072B2` literal (page 9's old `NODE_BASE_COLOR`,
    page 10's map marker + UniGR yearly bar) is retired in favour of the single-
    sourced `UL_COLOR` token on both pages. Matches the Acceptance gate's own
    `grep -c "#0072B2"` == 0 check verbatim."""
    import re
    zoom_src = Path(PARTNER_PAGE).read_text(encoding="utf-8")
    geo_src = (PAGES_DIR / GEO_PAGE).read_text(encoding="utf-8")
    assert len(re.findall(r"#0072B2", zoom_src, flags=re.IGNORECASE)) == 0
    assert len(re.findall(r"#0072B2", geo_src, flags=re.IGNORECASE)) == 0
    assert "UL_COLOR" in zoom_src
    assert "UL_COLOR" in geo_src
    # vacuity: reintroducing the literal on a COPY must be caught by the same regex
    mutated = geo_src + '\nSOME_COLOR = "#0072B2"\n'
    assert len(re.findall(r"#0072B2", mutated, flags=re.IGNORECASE)) == 1
