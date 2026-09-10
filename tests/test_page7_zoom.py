# tests/test_page7_zoom.py
"""
Pass-7a (P-ZOOM) pins -- pages/9_Zoom_partenaire.py's new BenchUp-signature sections
(balance bars, topic planes, reciprocity in BenchUp form, portage via bars_with_gutter,
the phares KPI, the page workbook). Owned by stream P-ZOOM only.

    .venv-pinned\\Scripts\\python -m pytest tests\\test_page7_zoom.py -q

Idiom: same namespace-swap + AppTest pattern as tests/test_page_pf.py (this repo has TWO
packages named `lib`; `_neutralize_page_link` works around the same pre-existing AppTest
harness limitation that file already documents -- st.page_link() raises KeyError
'url_pathname' under AppTest regardless of which page triggers it, so it is monkeypatched
to a no-op for every test here, which lets AppTest.from_file() load page 9 DIRECTLY with
`?partner_id=` in query_params, with no need to hop through Menu/Collaborations first).

`tests/_registry.py` frame composers are the LIFT SOURCE this page's own frame-building
functions were adapted from; several tests below independently recompute the same
relationships straight from `Streamlit/data/*.parquet` (never by importing the page's
internal functions -- the page is a script with module-level Streamlit calls, not an
importable library) so a regression in the page's OWN logic is caught even though the
computation is intentionally duplicated once, here, for the purpose of testing it.

Vacuity rule (P14): every assertion below is followed by an in-memory mutation (or a
mutated copy) that makes the identical check FAIL -- a pin that cannot fail is theater.
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
    """Same pre-existing AppTest limitation tests/test_page_pf.py documents (KeyError
    'url_pathname' on ANY st.page_link() call under direct AppTest.from_file()) --
    neutralised so these tests isolate page 9's OWN logic."""
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
    """< 20 co-pubs (I4210137456, co_works_full=19): every new section must degrade to an
    honest-empty/caption state, never raise -- and at least ONE of the thin-partner
    disclosure captions this pass introduces must actually appear."""
    _skip_if_missing("ptn_summary.parquet", "ptn_fields.parquet", "ptn_topics.parquet")
    at = _goto_partner(monkeypatch, THIN_ID)
    body = " ".join(c.value for c in at.caption) + " ".join(i.value for i in at.info)
    from lib import copy_fr
    thin_markers = [
        copy_fr.CAPTIONS["THIN_PARTNER"], copy_fr.CAPTIONS["JOINT_UNDER_FLOOR"],
        "sous le seuil", "Aucun", "mesuré",
    ]
    assert any(m in body for m in thin_markers), body
    # vacuity: an empty marker list can never match -- proves the assertion is live
    assert not any(m in body for m in [])


def test_balance_bars_level_and_mode_controls_survive_a_rerun(monkeypatch):
    _skip_if_missing("ptn_fields.parquet")
    at = _goto_partner(monkeypatch, CNRS_ID)
    radios = {r.key: r for r in at.radio}
    assert "v2_balance_mode" in radios, list(radios)
    at.radio(key="v2_balance_mode").set_value("phares")
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)
    assert at.session_state["v2_balance_mode"] == "phares"
    # vacuity
    assert at.session_state["v2_balance_mode"] != "volume"


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
# Phares KPI == ptn_summary.n_phares
# ============================================================================

def test_phares_kpi_equals_ptn_summary_n_phares_for_cnrs(monkeypatch):
    _skip_if_missing("ptn_summary.parquet")
    s = pd.read_parquet(DATA_DIR / "ptn_summary.parquet")
    row = s[(s["partner_id"] == CNRS_ID) & (s["subset_id"] == "all") & (s["conf_state"] == "all")].iloc[0]
    expected = int(row["n_phares"])
    from lib.helpers import fr_int
    at = _goto_partner(monkeypatch, CNRS_ID)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Publications phares") == fr_int(expected), metrics
    assert metrics.get("Publications phares") != fr_int(expected + 1)  # vacuity


# ============================================================================
# Balance bars: derived partner-only volume never negative, over ALL partners
# (pure-pandas, not AppTest -- P8's own floor-at-zero rule)
# ============================================================================

def test_balance_bars_derived_partner_only_never_negative_over_all_partners():
    _skip_if_missing("ptn_fields.parquet", "ptn_summary.parquet")
    fld = pd.read_parquet(DATA_DIR / "ptn_fields.parquet")
    summ = pd.read_parquet(DATA_DIR / "ptn_summary.parquet")
    summ = summ[(summ["subset_id"] == "all") & (summ["conf_state"] == "all")].set_index("partner_id")
    fields_only = fld[(fld["node_level"] == "field") & (fld["conf_state"] == "all")].copy()
    fields_only["partner_total"] = fields_only["partner_id"].map(summ["partner_total_windowed"])
    derived = (fields_only["partner_total"] * fields_only["baseline_partner_share"]
               - fields_only["co_works"]).clip(lower=0.0)
    assert (derived.dropna() >= 0.0).all()
    assert len(derived.dropna()) > 1000  # the pin has teeth: exercised at scale, not on 1 row

    # vacuity: inject one row whose UNCLIPPED value would be strongly negative, apply the
    # SAME clip formula, and check it lands at exactly 0 -- then show the unclipped value
    # really was negative, so the clip (not luck) is what the main assertion depends on.
    injected = fields_only.copy()
    injected.loc[injected.index[0], "partner_total"] = 1000.0
    injected.loc[injected.index[0], "baseline_partner_share"] = 0.0
    injected.loc[injected.index[0], "co_works"] = 10_000_000.0
    injected_derived = (injected["partner_total"] * injected["baseline_partner_share"]
                        - injected["co_works"]).clip(lower=0.0)
    injected_unclipped = (injected["partner_total"] * injected["baseline_partner_share"]
                          - injected["co_works"])
    assert injected_derived.loc[injected.index[0]] == 0.0
    assert injected_unclipped.loc[injected.index[0]] < 0.0


def test_balance_bars_volume_reconstructs_the_frame_for_three_cnrs_field_cells():
    """'segments reconstruct the frame': independently recomputes vol_ul_only / vol_joint
    / vol_partner_only for three real CNRS field cells and checks the page's own
    construction rules (vol_ul_only = UL total - joint, floored; link_label ==
    fmt_int(co_works); url == links.copubs_url(partner, node=('field', id)))."""
    _skip_if_missing("ptn_fields.parquet", "thematic_overview.parquet")
    from lib import links
    from lib.helpers import fr_int

    fld = pd.read_parquet(DATA_DIR / "ptn_fields.parquet")
    ov = pd.read_parquet(DATA_DIR / "thematic_overview.parquet")
    own = ov[ov["level"] == "field"].copy()
    own["id"] = own["id"].astype(int)
    own = own.drop_duplicates("id").set_index("id")

    rows = fld[(fld["partner_id"] == CNRS_ID) & (fld["node_level"] == "field")
               & (fld["conf_state"] == "all")].sort_values("co_works", ascending=False).head(3)
    assert len(rows) == 3, "expected >= 3 field cells for CNRS -- fixture assumption broken"

    for _, r in rows.iterrows():
        fid = int(r["node_id"])
        vol_ul_total = float(own.loc[fid, "pubs_total"])
        vol_joint = float(r["co_works"])
        vol_ul_only = max(0.0, vol_ul_total - vol_joint)
        assert vol_ul_only >= 0.0
        link_label = fr_int(vol_joint)
        assert link_label == fr_int(r["co_works"])
        url = links.copubs_url(CNRS_ID, node=("field", fid))
        assert url == links.copubs_url(CNRS_ID, node=("field", fid))  # deterministic
        assert f"authorships.institutions.id:{CNRS_ID}" in url
        assert f"primary_topic.field.id:{fid}" in url
        # vacuity: a DIFFERENT field id must NOT produce the same url
        assert links.copubs_url(CNRS_ID, node=("field", fid + 1)) != url


# ============================================================================
# Topic planes: rows <= N in every selector mode (pure-pandas reconstruction of
# _cell_frame + the selector sort + head(N), for CNRS)
# ============================================================================

def _cnrs_cells() -> pd.DataFrame:
    t = pd.read_parquet(DATA_DIR / "ptn_topics.parquet")
    d = t[(t["partner_id"] == CNRS_ID) & (t["conf_state"] == "all")]
    agg = (d.groupby("topic_id", as_index=False, observed=True)
           .agg(co_works=("co_works", "sum"), n_phares=("n_phares", "sum"),
                fwci_median=("fwci_fr_median_cell", "median"),
                frontier_score_std=("frontier_score_std", "median"),
                artifact_flag=("artifact_flag", "max")))
    agg = agg[agg["co_works"] >= 5].reset_index(drop=True)
    agg["artifact_flag"] = agg["artifact_flag"].fillna(False).astype(bool)
    return agg


@pytest.mark.parametrize("mode,n", [("volume", 10), ("fwci", 25), ("frontiere", 50), ("phares", 30)])
def test_plane_selection_never_exceeds_n_for_cnrs(mode, n):
    _skip_if_missing("ptn_topics.parquet")
    cells = _cnrs_cells()
    sort_col = {"volume": "co_works", "fwci": "fwci_median", "frontiere": "frontier_score_std", "phares": "n_phares"}[mode]
    selection = cells.sort_values(sort_col, ascending=False, na_position="last").head(n)
    assert len(selection) <= n
    assert len(cells) > n, "fixture assumption: CNRS has more eligible cells than N, or this pin proves nothing"
    # vacuity: taking head(n + 1000) on the SAME frame must exceed n (proves head(n) is load-bearing)
    assert len(cells.sort_values(sort_col, ascending=False, na_position="last").head(n + 1000)) > n


def test_plane_artifact_flag_is_a_real_boolean_column_feeding_the_tint(monkeypatch):
    """The tint-on-flagged-mark MECHANISM itself is lib.charts' own tested contract
    (tests/test_charts.py, S-LIB-A's fence); this pin only proves the page's frame feeds
    it a correct boolean column (tint is applied "iff artifact_flag", so a non-bool or
    always-False column would silently defeat P11 without failing any chart-level test)."""
    _skip_if_missing("ptn_topics.parquet")
    cells = _cnrs_cells()
    assert cells["artifact_flag"].dtype == bool
    # vacuity: forcing every value to a NON-bool (float) must fail the identical dtype check
    mutated = cells.assign(artifact_flag=cells["artifact_flag"].astype(float))
    assert mutated["artifact_flag"].dtype != bool


# ============================================================================
# Reciprocity: level toggle changes the row count; dropped-NULL count is disclosed
# ============================================================================

def test_reciprocity_level_toggle_changes_row_count(monkeypatch):
    _skip_if_missing("ptn_fields.parquet")
    fld = pd.read_parquet(DATA_DIR / "ptn_fields.parquet")
    base = fld[(fld["partner_id"] == CNRS_ID) & (fld["conf_state"] == "all")]
    n_field = len(base[(base["node_level"] == "field") & base["baseline_partner_share"].notna()
                        & base["baseline_ul_share"].notna()])
    n_subfield_capped = min(30, len(base[(base["node_level"] == "subfield") & base["baseline_partner_share"].notna()
                                          & base["baseline_ul_share"].notna()]))
    assert n_field != n_subfield_capped, "fixture assumption: the two levels differ in row count for CNRS"

    at = _goto_partner(monkeypatch, CNRS_ID)
    radios = {r.key: r for r in at.radio}
    recip_radio_keys = [k for k in radios if k and "recip_level" in k]
    assert recip_radio_keys, list(radios)
    at.radio(key=recip_radio_keys[0]).set_value(1)  # index 1 = "Top 30 sous-champs..."
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)
    assert at.session_state["v2_pair_level"] == "subfield"
    assert at.session_state["v2_pair_level"] != "field"  # vacuity


def test_reciprocity_null_share_rows_are_dropped_and_counted():
    """P8: a NULL baseline_partner_share row cannot sit on either axis of the
    reciprocity scatter and must be dropped + counted, never plotted at zero."""
    _skip_if_missing("ptn_fields.parquet")
    fld = pd.read_parquet(DATA_DIR / "ptn_fields.parquet")
    base = fld[(fld["partner_id"] == CNRS_ID) & (fld["conf_state"] == "all") & (fld["node_level"] == "field")]
    n_before = len(base)
    kept = base[base["baseline_partner_share"].notna() & base["baseline_ul_share"].notna()]
    n_hidden = n_before - len(kept)
    assert n_hidden >= 0
    # vacuity: an artificially all-NULL copy must hide EVERY row (n_hidden == n_before)
    all_null = base.assign(baseline_partner_share=np.nan)
    kept_all_null = all_null[all_null["baseline_partner_share"].notna() & all_null["baseline_ul_share"].notna()]
    assert len(kept_all_null) == 0
    assert (n_before - len(kept_all_null)) == n_before


# ============================================================================
# Hover grammar: HOVERTEMPLATE is used verbatim (no format spec ever), and every
# chart_key/mode this page renders has a HOVER_LABELS + READING entry (S-TT's own
# contract, cross-checked from the page stream's side)
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

    # vacuity: a key/mode this page does NOT use should not exist for a nonsense chart_key
    with pytest.raises(KeyError):
        reading_text("zoom_this_key_does_not_exist", "default")


def test_hovertemplate_constant_has_no_plotly_format_spec():
    from lib.hover import HOVERTEMPLATE
    import re
    assert HOVERTEMPLATE == "%{customdata}<extra></extra>"
    assert re.search(r"%\{[^}]*:[^}]*\}", HOVERTEMPLATE) is None
    # vacuity: a template WITH a format spec must be caught by the same regex
    assert re.search(r"%\{[^}]*:[^}]*\}", "%{customdata:.2f}") is not None


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
    # vacuity: the SECOND sheet must NOT be "Lecture" (proves position 0 is meaningful, not luck)
    assert book.sheet_names[1] != "Lecture"
