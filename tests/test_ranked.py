# tests/test_ranked.py
"""
Pass-5 unit pins for Streamlit/lib/ranked.py (R11 + R14) -- the shared DEPTH & QUERY
ranked-table component. Covers the PURE logic layer only (depth-extension, member-mask
re-slice, query filter, median-first column order) -- `ranked_table()` itself is the
Streamlit-facing composition, wired by future page streams, not exercised here.

    python -m pytest tests/test_ranked.py -q

Namespace note: same `_import_streamlit_lib` swap-trick as tests/test_shared_layer.py.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"


def _import_streamlit_lib(*names: str):
    saved = {k: v for k, v in sys.modules.items() if k == "lib" or k.startswith("lib.")}
    for k in saved:
        del sys.modules[k]
    sys.path.insert(0, str(STREAMLIT_DIR))
    try:
        mods = tuple(importlib.import_module(f"lib.{n}") for n in names)
    finally:
        sys.path.remove(str(STREAMLIT_DIR))
        for k in [k for k in sys.modules if k == "lib" or k.startswith("lib.")]:
            del sys.modules[k]
        sys.modules.update(saved)
    return mods


(ranked,) = _import_streamlit_lib("ranked")


def _sample_df(n: int) -> pd.DataFrame:
    """A MATERIALIZED, already-ranked frame -- exactly what a caller passes in
    (never recomputed by the pure functions under test)."""
    return pd.DataFrame({
        "id": [f"P{i:03d}" for i in range(n)],
        "name": [f"Partner {i}" for i in range(n)],
        "co_works": list(range(n, 0, -1)),
    })


# ============================================================================
# CONSORTIUM_IDS -- loaded once from inputs/overlays/idset_consortium.csv
# ============================================================================

def test_consortium_ids_loaded_and_nonempty():
    assert len(ranked.CONSORTIUM_IDS) > 0


def test_consortium_ids_include_the_known_members():
    """CNRS + UL-porteur ids, taken straight from idset_consortium.csv."""
    assert "I1294671590" in ranked.CONSORTIUM_IDS  # CNRS
    assert "I90183372" in ranked.CONSORTIUM_IDS    # UL itself, role=host


# ============================================================================
# depth_slice() -- depth-extension correctness
# ============================================================================

def test_depth_slice_default_equals_head_of_topn():
    df = _sample_df(30)
    assert ranked.depth_slice(df, expanded=False, default_n=10).equals(df.head(10))


def test_depth_slice_expanded_returns_the_whole_materialized_frame():
    df = _sample_df(30)
    assert ranked.depth_slice(df, expanded=True, default_n=10).equals(df)


def test_depth_slice_never_recomputes_just_slices():
    """Depth extension on an already-sorted frame changes nothing about row
    order/content -- it only changes how much of it is shown."""
    df = _sample_df(15)
    shown = ranked.depth_slice(df, expanded=True, default_n=10)
    assert list(shown["id"]) == list(df["id"])


# ============================================================================
# mask_members() / visible_slice_with_member_mask() -- member-mask re-slice
# ============================================================================

def test_mask_members_removes_only_matching_ids():
    df = _sample_df(10)
    out = ranked.mask_members(df, "id", {"P002", "P005"}, hide=True)
    assert len(out) == 8
    assert not ({"P002", "P005"} & set(out["id"]))


def test_mask_members_passthrough_when_hide_is_false():
    df = _sample_df(10)
    out = ranked.mask_members(df, "id", {"P002"}, hide=False)
    assert out.equals(df)


def test_member_mask_reslice_matches_direct_filter_on_same_padded_frame():
    """The pinned invariant: masked top-10 == top-(10+k) minus members, k = members
    inside the padded frame the caller materialized (S4 mission note)."""
    df = _sample_df(18)  # top-(10 + MEMBER_PAD=8) padded frame
    member_ids = {"P002", "P005", "P009"}  # k=3 members inside this padded frame
    visible = ranked.visible_slice_with_member_mask(
        df, id_col="id", member_ids=member_ids, hide_members=True,
        expanded=False, default_n=10,
    )
    expected = df[~df["id"].isin(member_ids)].head(10)
    assert visible.equals(expected)
    assert len(visible) == 10
    assert not (set(visible["id"]) & member_ids)


def test_member_mask_reslice_is_a_noop_when_toggle_off():
    df = _sample_df(18)
    visible = ranked.visible_slice_with_member_mask(
        df, id_col="id", member_ids={"P002"}, hide_members=False,
        expanded=False, default_n=10,
    )
    assert visible.equals(df.head(10))


def test_consortium_badge_column_marks_only_member_rows():
    df = _sample_df(5)
    a_member_id = next(iter(ranked.CONSORTIUM_IDS))
    df.loc[2, "id"] = a_member_id
    badge = ranked.consortium_badge_column(df, "id")
    assert badge.iloc[2] == ranked.CONSORTIUM_BADGE_LABEL
    assert (badge.drop(index=2) == "").all()


def test_consortium_badge_column_blank_when_id_col_missing():
    df = pd.DataFrame({"name": ["a", "b"]})
    badge = ranked.consortium_badge_column(df, "id")
    assert list(badge) == ["", ""]


# ============================================================================
# filter_by_query() -- text-query filter subset correctness
# ============================================================================

def test_query_filter_case_insensitive_substring():
    df = _sample_df(20)
    out = ranked.filter_by_query(df, "PARTNER 1", ["name"])
    # matches "Partner 1","10".."19" -- 11 rows
    assert len(out) == 11
    assert set(out["id"]) <= set(df["id"])  # subset correctness


def test_query_filter_blank_query_is_passthrough():
    df = _sample_df(5)
    assert ranked.filter_by_query(df, "", ["name"]).equals(df)
    assert ranked.filter_by_query(df, "   ", ["name"]).equals(df)


def test_query_filter_no_match_returns_empty_frame():
    df = _sample_df(5)
    out = ranked.filter_by_query(df, "zzz-no-such-partner", ["name"])
    assert out.empty


def test_query_filter_searches_every_named_column():
    df = _sample_df(5)
    df["country"] = ["FR", "DE", "FR", "US", "FR"]
    out = ranked.filter_by_query(df, "de", ["name", "country"])
    assert set(out["country"]) == {"DE"}


# ============================================================================
# build_column_order() -- median-first display contract
# ============================================================================

def test_build_column_order_hides_mean_columns():
    cols = ["id", "name", "fwci_median", "fwci_mean"]
    order = ranked.build_column_order(cols, mean_cols=["fwci_mean"])
    assert order == ["id", "name", "fwci_median"]
    assert "fwci_mean" not in order


def test_build_column_order_keeps_all_columns_when_no_mean_cols():
    cols = ["id", "name", "fwci_median"]
    assert ranked.build_column_order(cols) == cols


def test_build_column_order_extra_hidden_passthrough():
    """VIZ_BACKLOG #2: extra_hidden hides columns alongside mean_cols without
    being a 'mean' semantic (e.g. a raw id column, still addressable)."""
    cols = ["id", "raw_id", "name", "fwci_mean"]
    order = ranked.build_column_order(cols, mean_cols=["fwci_mean"], extra_hidden=["raw_id"])
    assert order == ["id", "name"]


# ============================================================================
# next_reveal_count() -- pass-6 depth mechanics (P6-R6 + Annuaire +50 mode, P8)
# ============================================================================

def test_next_reveal_count_none_step_reveals_everything_in_one_click():
    assert ranked.next_reveal_count(10, 30, step=None) == 30


def test_next_reveal_count_incremented_step_advances_by_exactly_step():
    assert ranked.next_reveal_count(10, 5000, step=50) == 60


def test_next_reveal_count_incremented_step_caps_at_total():
    assert ranked.next_reveal_count(4980, 5000, step=50) == 5000
    assert ranked.next_reveal_count(4999, 5000, step=50) == 5000


# ============================================================================
# should_show_query_box() -- P6-R6: search box auto-hidden below N=50
# ============================================================================

def test_query_box_hidden_below_threshold():
    assert ranked.should_show_query_box(12) is False
    assert ranked.should_show_query_box(49) is False


def test_query_box_shown_at_or_above_threshold():
    assert ranked.should_show_query_box(50) is True
    assert ranked.should_show_query_box(3616) is True


def test_query_box_threshold_is_overridable():
    assert ranked.should_show_query_box(20, threshold=10) is True


# ============================================================================
# sparkline_column() / link_column() -- VIZ_BACKLOG #2 column_config entries
# ============================================================================

def test_sparkline_column_is_a_line_chart_column():
    col = ranked.sparkline_column("Tendance", help_text="par an", y_min=0, y_max=100)
    assert col["label"] == "Tendance"
    assert col["help"] == "par an"
    assert col["type_config"]["type"] == "line_chart"
    assert col["type_config"]["y_min"] == 0
    assert col["type_config"]["y_max"] == 100


def test_link_column_is_a_link_column():
    col = ranked.link_column("Voir", display_text="ouvrir ↗")
    assert col["label"] == "Voir"
    assert col["type_config"]["type"] == "link"
    assert col["type_config"]["display_text"] == "ouvrir ↗"


# ============================================================================
# resolve_progress_cols() -- VIZ_SPEC_pass6 S7.2 mitigation, PURE (manager
# ruling: NEVER raise -- pass-5 call sites (pages 2/6/8/9/10) already pass 2+
# progress_cols and the suite must stay green at every instant between waves,
# plan P9; a ValueError here broke 6 live AppTest pages -- corrected).
# ============================================================================

def test_resolve_progress_cols_passthrough_when_zero_or_one():
    assert ranked.resolve_progress_cols(None) == ({}, {})
    assert ranked.resolve_progress_cols({}) == ({}, {})
    kept, demoted = ranked.resolve_progress_cols({"co_works": {"help": "h"}})
    assert kept == {"co_works": {"help": "h"}}
    assert demoted == {}


def test_resolve_progress_cols_keeps_first_demotes_the_rest():
    """Dict insertion order decides 'first' -- the caller's own order (e.g. its
    sort key), never re-sorted."""
    kept, demoted = ranked.resolve_progress_cols({
        "co_works": {"format": "%d"}, "share_ul": {"help": "a"}, "share_isite": {"help": "b"},
    })
    assert list(kept.keys()) == ["co_works"]
    assert kept["co_works"] == {"format": "%d"}
    assert set(demoted.keys()) == {"share_ul", "share_isite"}
    assert demoted["share_ul"] == {"help": "a"}


def test_resolve_progress_cols_never_raises():
    """The manager ruling verbatim: never raise, whatever the input shape."""
    kept, demoted = ranked.resolve_progress_cols({str(i): {} for i in range(10)})
    assert len(kept) == 1
    assert len(demoted) == 9


# ============================================================================
# ranked_table() -- the demotion is exercised end-to-end (no ScriptRunContext
# needed: Streamlit 1.61 tolerates a headless call, per the pre-existing pin).
# ============================================================================

def test_ranked_table_demotes_extra_progress_columns_to_number_columns(monkeypatch, caplog):
    import logging

    df = _sample_df(5)
    df["share_ul"] = [10.0, 20.0, 30.0, 40.0, 50.0]

    import streamlit as st
    captured = {}
    original_dataframe = st.dataframe

    def _capture(data, **kwargs):
        captured["column_config"] = kwargs.get("column_config")
        return original_dataframe(data, **kwargs)

    monkeypatch.setattr(st, "dataframe", _capture)

    with caplog.at_level(logging.WARNING, logger="lib.ranked"):
        ranked.ranked_table(
            df, key="demo_two_bars", id_col="id", search_cols=["name"],
            progress_cols={"co_works": {"format": "%d"}, "share_ul": {"help": "part UL"}},
        )

    cc = captured["column_config"]
    assert cc["co_works"]["type_config"]["type"] == "progress"
    assert cc["share_ul"]["type_config"]["type"] == "number"
    assert cc["share_ul"]["help"] == "part UL"
    warnings = [r for r in caplog.records if "demo_two_bars" in r.getMessage()]
    assert len(warnings) == 1


def test_ranked_table_demotion_warns_only_once_per_table_key(monkeypatch, caplog):
    import logging

    df = _sample_df(5)
    df["share_ul"] = [1.0, 2.0, 3.0, 4.0, 5.0]

    with caplog.at_level(logging.WARNING, logger="lib.ranked"):
        ranked.ranked_table(df, key="demo_repeat", id_col="id", search_cols=["name"],
                             progress_cols={"co_works": {}, "share_ul": {}})
        ranked.ranked_table(df, key="demo_repeat", id_col="id", search_cols=["name"],
                             progress_cols={"co_works": {}, "share_ul": {}})

    warnings = [r for r in caplog.records if "demo_repeat" in r.getMessage()]
    assert len(warnings) == 1, "expected exactly one warning across two reruns of the same table key"


def test_ranked_table_single_progress_column_never_demotes_or_warns(caplog):
    """Sanity: once a call site is down to one entry (the wave-3 end state),
    the guard never fires again."""
    import logging

    df = _sample_df(5)
    with caplog.at_level(logging.WARNING, logger="lib.ranked"):
        out = ranked.ranked_table(df, key="single_pc", id_col="id", search_cols=["name"],
                                   progress_cols={"co_works": {}})
    assert list(out["id"]) == list(df.head(ranked.DEFAULT_TOP_N)["id"])
    assert not [r for r in caplog.records if "single_pc" in r.getMessage()]


# ============================================================================
# number_cols -- explicit NumberColumn declaration (S-LENS D6, pass-6 fix round)
# ============================================================================
#
# Four pass-6 call sites (p4 topics_zero_fill/subfields_zero_fill/sdg_labs, p8 hub)
# used to stack every percent/volume column into `progress_cols` and lean on the
# demotion fallback above to render all but the first as a NumberColumn -- the
# VISUAL result was already correct, but the lib warning fired in production on
# every one of them. `number_cols` is the first-class way to ask for exactly that
# NumberColumn, through a path that never touches `resolve_progress_cols` and
# never logs -- these pins prove it renders identically AND stays silent.

def test_ranked_table_number_cols_renders_as_number_column_without_warning(monkeypatch, caplog):
    import logging

    df = _sample_df(5)
    df["share_ul"] = [10.0, 20.0, 30.0, 40.0, 50.0]

    import streamlit as st
    captured = {}
    original_dataframe = st.dataframe

    def _capture(data, **kwargs):
        captured["column_config"] = kwargs.get("column_config")
        return original_dataframe(data, **kwargs)

    monkeypatch.setattr(st, "dataframe", _capture)

    with caplog.at_level(logging.WARNING, logger="lib.ranked"):
        ranked.ranked_table(
            df, key="number_cols_site", id_col="id", search_cols=["name"],
            progress_cols={"co_works": {"format": "%d"}},
            number_cols={"share_ul": {"help": "part UL"}},
        )

    cc = captured["column_config"]
    assert cc["co_works"]["type_config"]["type"] == "progress"
    assert cc["share_ul"]["type_config"]["type"] == "number"
    assert cc["share_ul"]["help"] == "part UL"
    # the default format matches the demotion path's own default ("%.1f%%")
    assert cc["share_ul"]["type_config"]["format"] == "%.1f%%"
    assert not [r for r in caplog.records if "number_cols_site" in r.getMessage()]


def test_ranked_table_number_cols_matches_demotion_render_byte_for_byte(monkeypatch):
    """The whole point of `number_cols` is a drop-in replacement for "pass it into
    progress_cols and let the fallback demote it" -- same column_config output
    either way, just without the warning path."""
    import streamlit as st

    df = _sample_df(5)
    df["share_ul"] = [10.0, 20.0, 30.0, 40.0, 50.0]

    captured = {}
    original_dataframe = st.dataframe

    def _capture(data, **kwargs):
        captured["column_config"] = kwargs.get("column_config")
        return original_dataframe(data, **kwargs)

    monkeypatch.setattr(st, "dataframe", _capture)
    ranked.ranked_table(
        df, key="via_demotion", id_col="id", search_cols=["name"],
        progress_cols={"co_works": {"format": "%d"}, "share_ul": {"help": "part UL"}},
    )
    via_demotion = captured["column_config"]["share_ul"]

    captured.clear()
    ranked.ranked_table(
        df, key="via_number_cols", id_col="id", search_cols=["name"],
        progress_cols={"co_works": {"format": "%d"}},
        number_cols={"share_ul": {"help": "part UL"}},
    )
    via_number_cols = captured["column_config"]["share_ul"]

    assert via_demotion == via_number_cols


# ============================================================================
# Consortium column vs member-mask (S-LENS D7, pass-6 fix round -- the
# reproducible #38 recurrence: "masquer les membres" ON emptied the "Consortium"
# column, since mask_members() removes every member row BEFORE the badge column
# is computed on what's left. State-combination pin, not just the default state.
# ============================================================================

def _force_toggle(monkeypatch, value: bool):
    """Force every st.toggle() call inside ranked_table() to return `value`,
    regardless of session_state -- the headless-call path this file's other
    ranked_table() pins already rely on doesn't thread a real widget click."""
    import streamlit as st
    monkeypatch.setattr(st, "toggle", lambda *a, **k: value)


def _sample_df_with_a_consortium_member(n: int) -> pd.DataFrame:
    """Same shape as `_sample_df()`, but row 2's id is swapped for a REAL
    `ranked.CONSORTIUM_IDS` member -- `consortium_badge_column()` checks
    membership against that global registry directly (it takes no `member_ids`
    override, unlike `mask_members()`), so a pin proving the badge actually
    renders needs a genuine member id, not an arbitrary sample id."""
    df = _sample_df(n)
    df.loc[2, "id"] = next(iter(ranked.CONSORTIUM_IDS))
    return df


def test_ranked_table_drops_consortium_column_when_members_masked(monkeypatch):
    import streamlit as st

    df = _sample_df_with_a_consortium_member(10)
    _force_toggle(monkeypatch, True)  # "masquer les membres du site" ON

    captured = {}
    original_dataframe = st.dataframe

    def _capture(data, **kwargs):
        captured["data"] = data
        captured["column_config"] = kwargs.get("column_config")
        return original_dataframe(data, **kwargs)

    monkeypatch.setattr(st, "dataframe", _capture)
    ranked.ranked_table(
        df, key="mask_on", id_col="id", search_cols=["name"], has_members=True, default_n=10,
    )
    assert "Consortium" not in captured["data"].columns
    assert "Consortium" not in (captured["column_config"] or {})


def test_ranked_table_keeps_consortium_column_when_members_shown(monkeypatch):
    import streamlit as st

    df = _sample_df_with_a_consortium_member(10)
    member_id = df.loc[2, "id"]
    _force_toggle(monkeypatch, False)  # "masquer les membres du site" OFF (default)

    captured = {}
    original_dataframe = st.dataframe

    def _capture(data, **kwargs):
        captured["data"] = data
        return original_dataframe(data, **kwargs)

    monkeypatch.setattr(st, "dataframe", _capture)
    ranked.ranked_table(
        df, key="mask_off", id_col="id", search_cols=["name"], has_members=True, default_n=10,
    )
    assert "Consortium" in captured["data"].columns
    badges = captured["data"].set_index("id")["Consortium"]
    assert badges.loc[member_id] == ranked.CONSORTIUM_BADGE_LABEL
    assert not badges.drop(index=member_id).eq(ranked.CONSORTIUM_BADGE_LABEL).any()
