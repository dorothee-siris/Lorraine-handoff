"""
W5 shared chassis layer -- unit checks for Streamlit/lib/{exports,lazy,controls}.py.

    python -m pytest tests/test_shared_layer.py -q

Covers (per BUILD_PLAN W5 acceptance + docs/foundry/data_foundation.yaml rev 3.1
export_layer/drill_layer):
  - filename <-> state round-trip, all 8 combinations of {subset, entity, node} presence
  - header sheet carries every mandated field (rev 3.1 export_layer.header_sheet.fields)
  - impact_strip drops fwci/pptop/impact/citation columns (defence-in-depth, §6.4-3bis)
  - lib.lazy.read_keyed: returns only the keyed rows, touches < 20% of file bytes
    (F0 prune-proof style, reports/foundry_pass2_probes.py), and supports a list key
  - lib.lazy.assert_row_groups: Class-1 invariant (num_row_groups >= n_rows/10000)

Namespace note: tests/test_invariants.py and friends import the repo-ROOT `lib` package
(pipeline helpers: lib/snapshot.py etc.) via `sys.path.insert(0, ROOT)`. Streamlit/lib is
ALSO a package named `lib`, with its own `from lib.xxx import yyy` internal imports
(matching helpers.py's existing style). Importing both under the same pytest session
would collide -- whichever got bound into `sys.modules["lib"]` first wins, and the other
would silently resolve missing submodules against the wrong directory. `_import_streamlit_lib`
below swaps the `lib` binding to Streamlit/lib only for the moment it takes to import
exports/lazy/controls (so THEIR internal `from lib.*` imports resolve correctly), then
restores whatever was there before -- safe whether this file runs alone or as part of
`pytest tests/ -q` with test_invariants.py etc. collected in the same process.

F-SYSMOD fix (MINOR, pass-5 FIX-1 round): the actual save/delete/insert-path/restore
logic below now delegates to tests/conftest.py's centralized `swap_lib_to_streamlit`/
`restore_lib` (the same ONE implementation the 8 AppTest-based files' `setup_module`/
`teardown_module` hooks now call into) -- this file's own `_import_streamlit_lib` stays
as the one-shot-import call shape its 1 call site below already uses, it just no
longer re-implements the underlying guard.
"""
from __future__ import annotations

import importlib
import io
import itertools
import os
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    # F-SYSMOD fix: one-line fallback so `conftest` stays importable even if this
    # file is ever run as a standalone script, not just via pytest.
    sys.path.insert(0, str(_TESTS_DIR))
from conftest import restore_lib, swap_lib_to_streamlit  # centralized guard, see conftest.py


def _import_streamlit_lib(*names: str):
    saved = swap_lib_to_streamlit()
    try:
        mods = tuple(importlib.import_module(f"lib.{n}") for n in names)
    finally:
        restore_lib(saved)
    return mods


exports, lazy, controls, helpers = _import_streamlit_lib("exports", "lazy", "controls", "helpers")


# ============================================================================
# exports.py -- filename <-> state round-trip
# ============================================================================

@pytest.mark.parametrize(
    "has_subset,has_entity,has_node",
    list(itertools.product([False, True], repeat=3)),
)
def test_filename_roundtrip(has_subset, has_entity, has_node):
    state = exports.ExportState(
        snapshot="2026-08-11", conf="no_conf", artifact=True,
        subset="in-lue" if has_subset else None,
    )
    entity = ("p", "I157674565") if has_entity else None
    node = ("f", "11") if has_node else None

    fname = exports.build_filename("v2", "hub", state, entity=entity, node=node)
    assert fname.startswith("lorraine-explorer_v2_hub_2026-08-11_noconf_filtered")
    assert fname.endswith(".xlsx")

    parsed = exports.parse_filename(fname)
    assert parsed == {
        "view": "v2", "indicator": "hub", "snapshot": "2026-08-11",
        "conf": "noconf", "artifact": "filtered",
        "subset": "in-lue" if has_subset else None,
        "entity": entity, "node": node,
    }


def test_filename_roundtrip_via_panel_xlsx():
    """The same round-trip, exercised through the public panel_xlsx() entry point."""
    df = pd.DataFrame({"a": [1, 2]})
    state = exports.ExportState(snapshot="2026-08-11", conf="all", artifact="full", subset="all")
    _, fname = exports.panel_xlsx(df, "V1", "Hub Table", state, entity=("c", "fr"), node=("d", "2"))
    parsed = exports.parse_filename(fname)
    assert parsed["view"] == "v1"
    assert parsed["indicator"] == "hub-table"
    assert parsed["subset"] is None          # default 'all' -> omitted from filename
    assert parsed["entity"] == ("c", "fr")
    assert parsed["node"] == ("d", "2")


@pytest.mark.parametrize("value,expected", [
    (True, "all"), (False, "noconf"), ("all", "all"),
    ("no_conf", "noconf"), ("noconf", "noconf"), ("No_Conf", "noconf"),
])
def test_conf_normalisation(value, expected):
    assert exports.ExportState(snapshot="2026-08-11", conf=value).conf == expected


@pytest.mark.parametrize("value,expected", [
    (True, "filtered"), (False, "full"), ("full", "full"),
    ("off", "full"), ("filtered", "filtered"), ("on", "filtered"),
])
def test_artifact_normalisation(value, expected):
    assert exports.ExportState(snapshot="2026-08-11", artifact=value).artifact == expected


def test_conf_rejects_garbage():
    with pytest.raises(ValueError):
        exports.ExportState(snapshot="2026-08-11", conf="bogus")


def test_entity_rejects_unknown_kind():
    with pytest.raises(ValueError):
        exports.build_filename("v1", "hub", exports.ExportState(snapshot="2026-08-11"),
                                entity=("z", "X1"))


# ============================================================================
# exports.py -- header sheet + impact strip
# ============================================================================

def test_header_sheet_has_all_mandated_fields():
    df = pd.DataFrame({"work_id": ["W1", "W2"], "title": ["a", "b"]})
    state = exports.ExportState(
        snapshot="2026-08-11", conf=True, artifact=True, subset="in-lue",
        filters={"floor": 20}, artifact_applied=True,
        deferred_twins=["share_ul_direct", "co_works_intl"],
        method="Test method one-liner.",
    )
    xlsx_bytes, filename = exports.panel_xlsx(
        df, "v2", "hub", state, entity=("p", "I157674565"), node=("f", "11"),
    )
    assert filename == exports.build_filename("v2", "hub", state, entity=("p", "I157674565"), node=("f", "11"))

    header = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=exports.METHOD_SHEET_NAME)
    assert list(header["Champ"]) == exports.HEADER_FIELDS

    values = dict(zip(header["Champ"], header["Valeur"]))
    assert values["snapshot_date"] == "2026-08-11"
    assert values["method_one_liner"] == "Test method one-liner."
    assert values["conference_toggle_state"] == "all"
    assert values["artifact_toggle_state"] == "filtered"
    assert values["artifact_applied"] == "oui"
    assert values["artifact_banner_text_if_on"] == controls.ARTIFACT_BANNER_TEXT_FR
    assert "share_ul_direct" in values["deferred_twin_columns"]
    assert values["perimeter_subset"] == "in-lue"
    assert values["entity"] == "p-I157674565"
    assert values["drill_node"] == "f-11"
    assert values["generation_date"]  # non-empty, today's ISO date

    data = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=exports.DATA_SHEET_NAME)
    assert list(data["work_id"]) == ["W1", "W2"]


def test_header_sheet_banner_empty_when_artifact_off():
    df = pd.DataFrame({"a": [1]})
    state = exports.ExportState(snapshot="2026-08-11", artifact=False)
    xlsx_bytes, _ = exports.panel_xlsx(df, "v1", "kpi", state)
    header = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=exports.METHOD_SHEET_NAME)
    values = dict(zip(header["Champ"], header["Valeur"]))
    assert values["artifact_banner_text_if_on"] in ("", None) or pd.isna(values["artifact_banner_text_if_on"])


def test_impact_strip_drops_fwci_column():
    df = pd.DataFrame({
        "author_id": ["A1", "A2"], "work_id": ["W1", "W2"],
        "fwci_fr": [1.2, 0.8], "PPtop10_FR_count": [3, 1],
        "n_citations": [10, 4], "title": ["x", "y"],
    })
    state = exports.ExportState(snapshot="2026-08-11")
    xlsx_bytes, filename = exports.works_xlsx(df, "a-v2", "works", state, impact_strip=True)
    assert filename.endswith(".xlsx")
    data = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=exports.WORKS_SHEET_NAME)
    for dropped in ("fwci_fr", "PPtop10_FR_count", "n_citations"):
        assert dropped not in data.columns
    assert "title" in data.columns and "work_id" in data.columns and "author_id" in data.columns


def test_impact_strip_off_keeps_everything():
    df = pd.DataFrame({"work_id": ["W1"], "fwci_fr": [1.2]})
    state = exports.ExportState(snapshot="2026-08-11")
    xlsx_bytes, _ = exports.panel_xlsx(df, "v2", "profile", state, impact_strip=False)
    data = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=exports.DATA_SHEET_NAME)
    assert "fwci_fr" in data.columns


# ============================================================================
# lazy.py -- predicate pushdown + Class-1 row-group invariant
# ============================================================================

def _touched_bytes(path, key_col: str, target) -> tuple[int, int, int, int]:
    """
    F0-style prune proof (reports/foundry_pass2_probes.py:prune_proof), adapted
    to sum ALL columns' compressed bytes for each touched row group (not just
    the filter column) -- the closest local proxy for "file bytes touched" by
    a real predicate-pushdown read.
    """
    pf = pq.ParquetFile(path)
    col_idx = pf.schema_arrow.get_field_index(key_col)
    total_bytes = os.path.getsize(path)
    touched_bytes = 0
    n_touched = 0
    n_rg = pf.metadata.num_row_groups
    for i in range(n_rg):
        rg = pf.metadata.row_group(i)
        stats = rg.column(col_idx).statistics
        if stats is not None and stats.has_min_max and stats.min <= target <= stats.max:
            touched_bytes += sum(rg.column(j).total_compressed_size for j in range(rg.num_columns))
            n_touched += 1
    return touched_bytes, total_bytes, n_touched, n_rg


def test_read_keyed_scalar_key_touches_few_bytes(tmp_path):
    n_partners, rows_per_partner = 300, 100
    partner_ids = [f"P{p:04d}" for p in range(n_partners) for _ in range(rows_per_partner)]
    n = len(partner_ids)
    df = pd.DataFrame({
        "partner_id": partner_ids,
        "work_id": [f"W{i}" for i in range(n)],
        "year": [2019 + (i % 5) for i in range(n)],
        "co_works": list(range(n)),
    }).sort_values("partner_id").reset_index(drop=True)
    path = tmp_path / "ptn_works_scratch.parquet"
    df.to_parquet(path, row_group_size=5000, index=False)

    pf = pq.ParquetFile(path)
    assert pf.metadata.num_row_groups == n // 5000  # 30,000 rows / 5,000 = 6 groups

    target = "P0150"  # sorted + contiguous -> falls in exactly one row group
    touched_bytes, total_bytes, n_touched, n_rg = _touched_bytes(path, "partner_id", target)
    assert n_touched <= 2, f"expected the target to fall in <=2 of {n_rg} row groups, got {n_touched}"
    ratio = touched_bytes / total_bytes
    assert ratio < 0.20, f"touched {ratio:.1%} of file bytes, expected < 20%"

    out = lazy.read_keyed(str(path), "partner_id", target)
    assert len(out) == rows_per_partner
    assert (out["partner_id"] == target).all()


def test_read_keyed_list_key_in_filter(tmp_path):
    """The country-pubs path: key_value as a list -> an `in` filter."""
    df = pd.DataFrame({
        "partner_id": [f"P{p:04d}" for p in range(50) for _ in range(10)],
        "work_id": [f"W{i}" for i in range(500)],
    }).sort_values("partner_id").reset_index(drop=True)
    path = tmp_path / "ptn_works_list_scratch.parquet"
    df.to_parquet(path, row_group_size=100, index=False)

    keys = ["P0003", "P0007", "P0011"]
    out = lazy.read_keyed(str(path), "partner_id", keys)
    assert set(out["partner_id"].unique()) == set(keys)
    assert len(out) == 10 * len(keys)


def test_assert_row_groups_passes_on_properly_written_file(tmp_path):
    df = pd.DataFrame({"k": range(30000), "v": range(30000)})
    path = tmp_path / "ok.parquet"
    df.to_parquet(path, row_group_size=5000, index=False)
    lazy.assert_row_groups(path)  # must not raise


def test_assert_row_groups_fails_on_single_group_file(tmp_path):
    df = pd.DataFrame({"k": range(15000), "v": range(15000)})
    path = tmp_path / "bad.parquet"
    df.to_parquet(path, row_group_size=100_000, index=False)  # forced into 1 row group
    pf = pq.ParquetFile(path)
    assert pf.metadata.num_row_groups == 1
    with pytest.raises(AssertionError):
        lazy.assert_row_groups(path)


# ============================================================================
# controls.py -- pure-logic helpers (xa / marker_dagger / grey_deferred)
# ============================================================================

def test_xa_returns_twin_only_when_toggle_on_and_twin_exists():
    df = pd.DataFrame({"co_works": [1, 2], "co_works_xa": [1, 1]})
    controls_st = sys.modules.get("streamlit") or __import__("streamlit")
    controls_st.session_state[controls.ARTIFACT_TOGGLE_KEY] = False
    assert controls.xa(df, "co_works") == "co_works"
    controls_st.session_state[controls.ARTIFACT_TOGGLE_KEY] = True
    assert controls.xa(df, "co_works") == "co_works_xa"
    assert controls.xa(df, "share_p") == "share_p"  # no twin in df -> base name


def test_marker_dagger_column_disclose_never_demote():
    df = pd.DataFrame({"topic_id": [1, 2, 3], "artifact_flag": [True, False, True]})
    col = controls.marker_dagger_column(df)
    assert list(col) == [controls.DAGGER, "", controls.DAGGER]
    assert len(col) == len(df)  # no row dropped or reordered


def test_marker_dagger_column_no_flag_col_is_blank():
    df = pd.DataFrame({"topic_id": [1, 2]})
    col = controls.marker_dagger_column(df)
    assert list(col) == ["", ""]


def test_grey_deferred_dict_form_adds_dagger_and_disables():
    cfg = controls.grey_deferred({}, ["share_ul_direct"])
    assert "share_ul_direct" in cfg
    entry = cfg["share_ul_direct"]  # st.column_config.Column(...) returns a plain dict
    assert controls.DAGGER in entry["label"]
    assert entry["disabled"] is True


# ============================================================================
# controls.py / helpers.py -- F1/QA-01/RA-A03 cross-page persistence.
#
# First attempt (hand-rolled `_persist_<name>` write-through/seed helpers) looked
# right and passed an isolated unit test, but the Playwright journey proof
# (progress/CXFIX_codex_fixes.md) caught it failing on a SECOND page switch --
# Streamlit's keyed-widget remounts under a new per-page element id, so a plain
# session_state write-through does not reliably reattach across more than one
# hop. The ACTUAL fix uses this Streamlit build's own first-party
# `persist_state="session"` widget parameter (elements/widgets/selectbox.py /
# checkbox.py: "the value is preserved for the entire session, including across
# page switches"). A live widget cannot be exercised meaningfully without a
# running script context (no session -> no meaningful register_widget()), so
# this is a source-level pin (same idiom as test_theme_identity.py's grep
# sweep) that the three shared control widgets actually request it; the
# Playwright journey remains the BINDING proof of the cross-page behaviour.
# ============================================================================

CONTROLS_SRC = (STREAMLIT_DIR / "lib" / "controls.py").read_text(encoding="utf-8")
HELPERS_SRC = (STREAMLIT_DIR / "lib" / "helpers.py").read_text(encoding="utf-8")


def _widget_call_span(src: str, key_token: str) -> str:
    """The source text of the widget call instantiating `key=<key_token>` (the
    token as it literally appears in source -- a quoted string or a bare
    constant-name reference), from the call's opening `st.sidebar.` through its
    closing `)` -- a tolerant slice (not a real parser), good enough to check
    for a sibling kwarg on the SAME call rather than anywhere in the file."""
    idx = src.find(f"key={key_token}")
    assert idx != -1, f"key={key_token} not found in source"
    start = src.rfind("st.sidebar.", 0, idx)
    end = src.find(")", idx)
    assert start != -1 and end != -1
    return src[start:end]


def test_isite_overlay_toggle_widget_requests_session_persistence():
    """
    Pass 5 (R1, 2026-08-18): REPLACES the retired
    `test_perimeter_selector_widget_requests_session_persistence` pin --
    perimeter_selector() and its sidebar widget are gone (I-SITE is an overlay
    everywhere now, never a corpus filter), so there is nothing left to pin
    there. isite_overlay_toggle() is the NEW third widget needing the same
    persist_state="session" fix as artifact_toggle() and
    lib.helpers.conference_toggle() (see controls.py's CROSS-PAGE PERSISTENCE
    comment for the full history of why a source-level pin, not a live widget
    exercise, is what a unit test can check here).
    """
    assert controls.ISITE_OVERLAY_KEY == "isite_overlay"  # sanity: the token below
    span = _widget_call_span(CONTROLS_SRC, "ISITE_OVERLAY_KEY")
    assert 'persist_state="session"' in span


def test_artifact_toggle_widget_requests_session_persistence():
    assert controls.ARTIFACT_TOGGLE_KEY == "artifact_filter"  # sanity: the token below
    span = _widget_call_span(CONTROLS_SRC, "ARTIFACT_TOGGLE_KEY")
    assert 'persist_state="session"' in span


def test_isite_overlay_help_text_contains_no_hardcoded_vintage_date():
    """
    Pass-6 fix round (S-LENS D3): `ISITE_OVERLAY_HELP_FR` used to hardcode the
    DOI-list vintage date ("2026-08-10") -- a byte-identical-today literal
    that would silently lie the day the canonical list is refreshed (an OPEN
    client ask). It must now be COMPUTED from `dim_subsets.parquet`'s
    `in_isite` row's `vintage_date` column, the same field the I-SITE page's
    own KPI-row caveat reads live (`pages/7_🎯_I-SITE.py:334`).
    """
    deploy_dir = STREAMLIT_DIR / "data"
    path = deploy_dir / "dim_subsets.parquet"
    if not path.exists():
        pytest.skip("dim_subsets.parquet not deployed yet")
    subsets = pd.read_parquet(path, columns=["subset_id", "vintage_date"])
    row = subsets.loc[subsets["subset_id"] == "in_isite"].iloc[0]
    vintage = str(row["vintage_date"])
    assert f"datée du {vintage}" in controls.ISITE_OVERLAY_HELP_FR
    # source-level guard: no bare literal date sits in the constant's own
    # source span (would indicate a hardcoded fallback reintroduced later)
    assert "2026-08-10" not in CONTROLS_SRC.split("ISITE_OVERLAY_HELP_FR = (")[1].split(")\n")[0]


def test_conference_toggle_widget_requests_session_persistence():
    """conference_toggle() lives in lib.helpers (reused, never duplicated) --
    its OWN widget call must carry the fix, not a wrapper in controls.py."""
    span = _widget_call_span(HELPERS_SRC, '"include_conference"')
    assert 'persist_state="session"' in span


# ============================================================================
# F2 (QA-02/RA-A01) regression pin: a filtered frame handed to the shared exporter
# must come back out with the SAME row count -- the review's own repro (CNRS
# partner_id / a specific author_id, conferences OFF). Counts are recomputed FRESH
# from the deployed parquets every run (never pinned as a literal from the review's
# prompt), so a future snapshot refresh cannot silently go stale here.
# ============================================================================

DATA_DIR = STREAMLIT_DIR / "data"


def test_partner_works_export_row_count_matches_independently_filtered_count():
    """Page 7's Publications drawer/export must consume the conference-filtered frame,
    same as its on-screen headline (this WAS the QA-02 bug: unfiltered `partner_works` was
    exported while the filename/method sheet claimed the active conference state)."""
    path = DATA_DIR / "ptn_works.parquet"
    if not path.is_file():
        pytest.skip(f"{path} not deployed -- run the pipeline + 60_deploy first")
    partner_id = "I1294671590"  # CNRS -- the review's own repro entity (a stable OpenAlex id)
    full = lazy.read_keyed(str(path), "partner_id", partner_id)
    if full.empty:
        pytest.skip(f"partner_id={partner_id} not present in this deployed snapshot")
    filtered = full[~full["is_conference"].fillna(False)]
    assert len(filtered) < len(full), "fixture assumption broken: expected >=1 conference work"

    state = exports.ExportState(snapshot="2026-08-11", conf=False, artifact=False)
    xlsx_bytes, _ = exports.works_xlsx(
        filtered, "v2-partner-drilldown", "publications", state, entity=("p", partner_id),
    )
    data = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=exports.WORKS_SHEET_NAME)
    assert len(data) == len(filtered)
    assert len(data) != len(full)  # would still pass if a future edit reverts to the full frame


def test_author_works_export_row_count_matches_independently_filtered_count():
    """Same QA-02 pin, author family (page 10): `w` (filtered) must be what both the drawer
    and its export render, never the unfiltered `works_df`."""
    path = DATA_DIR / "aut_works.parquet"
    if not path.is_file():
        pytest.skip(f"{path} not deployed -- run the pipeline + 60_deploy first")
    author_id = "A5042884495"  # the review's own repro entity
    full = lazy.read_keyed(str(path), "author_id", author_id)
    if full.empty:
        pytest.skip(f"author_id={author_id} not present in this deployed snapshot")
    filtered = full[~full["is_conference"].fillna(False)]
    assert len(filtered) < len(full), "fixture assumption broken: expected >=1 conference work"

    state = exports.ExportState(snapshot="2026-08-11", conf=False, artifact=False)
    xlsx_bytes, _ = exports.works_xlsx(
        filtered, "a-v2", "works", state, entity=("a", author_id), impact_strip=True,
    )
    data = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=exports.WORKS_SHEET_NAME)
    assert len(data) == len(filtered)
    assert len(data) != len(full)


# ============================================================================
# helpers.py -- pass-5 additions: FR number formatting (R11/R14/R1) + log/linear
# axis toggle (R18). One home, no duplicates (S4 mission note) -- lib.overlay and
# lib.ranked re-export fr_int/fr_pct from here rather than re-implementing them.
# ============================================================================

def test_fr_int_uses_narrow_nbsp_thousands_grouping():
    assert helpers.fr_int(1839) == "1 839"
    assert helpers.fr_int(12345678) == "12 345 678"
    assert helpers.fr_int(0) == "0"


def test_fr_int_missing_is_na_mark_never_zero():
    assert helpers.fr_int(None) == helpers.NA_MARK
    assert helpers.fr_int(float("nan")) == helpers.NA_MARK
    assert helpers.fr_int(pd.NA) == helpers.NA_MARK


def test_fr_pct_decimal_comma_and_narrow_nbsp_before_percent():
    assert helpers.fr_pct(4.1) == "4,1 %"
    assert helpers.fr_pct(0) == "0,0 %"
    assert helpers.fr_pct(4.15, decimals=2) == "4,15 %"


def test_fr_pct_missing_is_na_mark():
    assert helpers.fr_pct(None) == helpers.NA_MARK
    assert helpers.fr_pct(float("nan")) == helpers.NA_MARK


def test_log_linear_axis_type_defaults_to_log():
    """R18: log stays the default; the local toggle can only ever ask for linear."""
    assert helpers.axis_type_for_toggle(False) == "log"
    assert helpers.axis_type_for_toggle(True) == "linear"
