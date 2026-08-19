# lib/ranked.py
"""
Pass-5 shared DEPTH & QUERY ranked-table component (R11 + R14) -- authority:
docs/SPRINT_KICKOFF_pass5.md.

ONE generic ranked-table renderer every page stream wires instead of rolling its own
top-N/search/member-mask logic. Two layers:

  - PURE logic (no Streamlit dependency, unit-tested directly): `depth_slice()`,
    `mask_members()`, `filter_by_query()`, `build_column_order()`. These NEVER touch a
    data source -- every one of them slices/filters the MATERIALIZED frame the caller
    already built (never recomputes), which is the whole point of the "zero recompute"
    contract (S4 mission note) and what the test pins actually check.
  - `ranked_table()`: the Streamlit-facing composition (search box, "afficher plus",
    the local "masquer les membres du site" toggle, `st.dataframe` with progress
    columns + the median-first column order) that WIRES the pure functions together.
    No page calls this yet this pass -- future page streams wire it per-panel.

Consortium membership (badge + member-mask): `CONSORTIUM_IDS` is loaded ONCE from
`inputs/overlays/idset_consortium.csv` at import time and exposed as a frozenset --
never re-read, never re-derived by a page. NOTE (surprise, logged in
progress/S4_shared_layer.md): that file lists 8 DISTINCT members (CNRS, Inserm, INRAE,
CHRU Nancy, Georgia Tech, Inria, AgroParisTech, + UL itself as porteur/host) but 15
OpenAlex ids in total -- Georgia Tech resolves to 3 ids and Inria (external centres) to
6 (both curated multi-id proof cases per that file's own comments). `CONSORTIUM_IDS`
is the flat set of all 15 ids, taken verbatim from the file's `id` column: a partner-
grain ranked table will simply never see UL's own host id match a row (UL is the focal
institution, never its own partner), so including it is harmless, and loading the file
verbatim (no filtering logic of our own to get wrong) is the safest reading of "the 8
signatory OpenAlex ids from the consortium overlay input file". The mission's own
"top-(N+8)" padding convention already treats 8 as a safe upper bound on how many
member ROWS can appear in one ranked list, which holds either way.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import pandas as pd

_logger = logging.getLogger(__name__)

# Re-exported for convenience (S4 mission note groups fr_int/fr_pct under this module's
# own spec bullet even though their ONE implementation lives in lib.helpers, "one home,
# no duplicates") -- a page wiring ranked_table() can do
# `from lib.ranked import ranked_table, fr_int, fr_pct` without a second import.
from lib.helpers import fr_int, fr_pct  # noqa: F401

# ============================================================================
# CONSORTIUM MEMBERSHIP -- loaded once
# ============================================================================

_CONSORTIUM_CSV = Path(__file__).resolve().parent.parent.parent / "inputs" / "overlays" / "idset_consortium.csv"

CONSORTIUM_BADGE_LABEL = "consortium I-SITE"  # VIZ_SPEC 2.5 I2's own "type tag" wording, reused
HIDE_MEMBERS_LABEL = "masquer les membres du site"
MORE_LABEL = "afficher plus"


def _load_consortium_ids() -> frozenset:
    if not _CONSORTIUM_CSV.is_file():
        return frozenset()
    try:
        df = pd.read_csv(_CONSORTIUM_CSV)
    except Exception:
        return frozenset()
    if "id" not in df.columns:
        return frozenset()
    return frozenset(df["id"].astype(str).str.strip())


CONSORTIUM_IDS: frozenset = _load_consortium_ids()


# ============================================================================
# PURE LOGIC -- depth extension
# ============================================================================

DEFAULT_TOP_N = 10
MEMBER_PAD = 8  # consortium size upper bound; see module docstring
QUERY_MIN_N = 50  # P6-R6: the search box only earns its place at N >= 50


def depth_slice(df_topn: pd.DataFrame, expanded: bool, default_n: int = DEFAULT_TOP_N) -> pd.DataFrame:
    """
    Default = the first `default_n` rows of the MATERIALIZED top-N frame the
    caller already built (never recomputed); "afficher plus" (`expanded=True`)
    reveals the rest of that SAME frame, however far the caller materialized it.

    Kept exactly as pass-5 shipped it (existing pins in tests/test_ranked.py) --
    the boolean "reveal everything materialized in one click" case. Pass-6's
    `ranked_table()` generalises this to an incremental reveal count via
    `next_reveal_count()` below (P6-R6's +50-increment mode for the Annuaire);
    a caller that only ever needs the pass-5 binary behaviour can still call
    this function directly.
    """
    return df_topn if expanded else df_topn.head(default_n)


def next_reveal_count(current_shown: int, total: int, step: int | None) -> int:
    """
    Pass-6 depth mechanics (P6-R6): how many rows "afficher plus" reveals on
    the NEXT click. `step=None` reveals everything materialized in the SAME
    click (pass-5 default -- the 20/30-deep tops tables: one click is enough).
    `step=int` (plan P8, the Annuaire's +50-increment mode) advances by exactly
    `step` rows instead, capped at `total` so it never asks for more than the
    caller materialized. Pure, no Streamlit dependency -- directly testable.
    """
    if step is None:
        return total
    return min(current_shown + step, total)


def should_show_query_box(full_n: int, *, threshold: int = QUERY_MIN_N) -> bool:
    """
    P6-R6 / inventory #16-#22-#43: the query/search box only earns its place
    once the table's FULL materialized N reaches `threshold` -- below it,
    scanning the (short) list by eye is faster than typing, and the feedback
    round names these exact boxes "useless". `full_n` must be measured on the
    frame the caller handed `ranked_table()` BEFORE any query/mask filtering
    (gating the box on its own filtered output would be circular).
    """
    return full_n >= threshold


# ============================================================================
# PURE LOGIC -- member mask
# ============================================================================

def mask_members(df: pd.DataFrame, id_col: str, member_ids, hide: bool) -> pd.DataFrame:
    """
    Filter OUT rows whose `id_col` is in `member_ids` when `hide=True`; a
    pass-through otherwise. Pure filter on the frame already in hand -- no
    data-source read, "zero recompute" (S4 mission note).
    """
    if not hide:
        return df
    return df[~df[id_col].isin(member_ids)]


def visible_slice_with_member_mask(
    df_topn_plus_pad: pd.DataFrame,
    *,
    id_col: str,
    member_ids=CONSORTIUM_IDS,
    hide_members: bool,
    expanded: bool,
    default_n: int = DEFAULT_TOP_N,
) -> pd.DataFrame:
    """
    The combined depth + member-mask slice: mask first (on the padded frame
    the caller materialized as top-(N + MEMBER_PAD)), THEN take the depth
    slice of what's left. Re-slicing a mask on an already-padded frame is
    "zero recompute" by construction -- it never goes back to the data source,
    just narrows the same in-memory frame twice.
    """
    working = mask_members(df_topn_plus_pad, id_col, member_ids, hide_members)
    return depth_slice(working, expanded, default_n)


def consortium_badge_column(df: pd.DataFrame, id_col: str, label: str = CONSORTIUM_BADGE_LABEL) -> pd.Series:
    """
    « consortium I-SITE » badge values: `label` on member rows, blank
    otherwise (same disclose-only convention as controls.marker_dagger_column
    -- adds a column, never greys/hides/reorders a row).
    """
    if id_col not in df.columns:
        return pd.Series([""] * len(df), index=df.index, name="Consortium")
    is_member = df[id_col].astype(str).isin(CONSORTIUM_IDS)
    return is_member.map({True: label, False: ""}).rename("Consortium")


# ============================================================================
# PURE LOGIC -- text-query filter
# ============================================================================

def filter_by_query(df: pd.DataFrame, query: str, search_cols: Sequence[str]) -> pd.DataFrame:
    """
    Case-insensitive substring filter across `search_cols` (caller-named,
    e.g. topic name, partner name). Empty/blank query is a pass-through.
    """
    if not query or not str(query).strip():
        return df
    needle = str(query).strip().lower()
    cols = [c for c in search_cols if c in df.columns]
    if not cols:
        return df.iloc[0:0]
    mask = pd.Series(False, index=df.index)
    for col in cols:
        mask = mask | df[col].astype(str).str.lower().str.contains(needle, na=False, regex=False)
    return df[mask]


# ============================================================================
# PURE LOGIC -- median-first column order (R11 display contract)
# ============================================================================

def build_column_order(
    df_columns: Sequence[str],
    *,
    mean_cols: Sequence[str] = (),
    extra_hidden: Sequence[str] = (),
) -> list[str]:
    """
    Median-first display contract: median columns (any column NOT named here)
    are visible by default; `mean_cols` are omitted from the returned
    `column_order` -- Streamlit's own dataframe toolbar still lets a user add
    them back via its column-visibility menu (columns omitted from
    `column_order` are hidden by default but remain user-addable; this is a
    documented `st.dataframe` behaviour, not a custom mechanism). Exports
    always keep BOTH regardless of this (a page's export call passes the full
    frame to lib.exports, never this column_order).
    """
    hidden = set(mean_cols) | set(extra_hidden)
    return [c for c in df_columns if c not in hidden]


# ============================================================================
# PROGRESS-COLUMN HELPER
# ============================================================================

MAX_PROGRESS_COLS = 1  # VIZ_SPEC_pass6 S7.2: "one ProgressColumn per visible table. Never two."

# Table `key`s already warned about a demotion this process -- "logged once per
# table id", not once per rerun (Streamlit reruns the whole script on every
# interaction, so an un-throttled warning would spam the log on every click).
_DEMOTION_WARNED: set[str] = set()


def progress_column(label: str, *, help_text: str | None = None,
                     min_value: float = 0, max_value: float = 100,
                     format: str = "%.1f%%"):
    """`st.dataframe` column_config entry for a share/ratio column."""
    import streamlit as st
    return st.column_config.ProgressColumn(
        label, help=help_text, min_value=min_value, max_value=max_value, format=format,
    )


def resolve_progress_cols(progress_cols: dict[str, dict] | None) -> tuple[dict, dict]:
    """
    VIZ_SPEC_pass6 S7.2 mechanical mitigation, PURE (no logging, no Streamlit --
    directly testable): "one ProgressColumn per visible table. Never two."
    When `progress_cols` holds more than `MAX_PROGRESS_COLS` entries, the FIRST
    (insertion order -- the caller's own dict order, e.g. its sort key) is KEPT
    as the progress bar; the rest are returned separately for demotion to a
    plain NumberColumn. Never raises: pass-5 call sites (pages 2/6/8/9/10 --
    the live app, not yet migrated to the pass-6 one-bar rule) still pass 2+
    entries until their own wave-3 stream cleans the call site, and the suite
    must stay green at every instant between waves (plan P9). Returns
    `(kept, demoted)`; `kept` has at most one entry.
    """
    cols = dict(progress_cols or {})
    if len(cols) <= MAX_PROGRESS_COLS:
        return cols, {}
    items = list(cols.items())
    return dict(items[:MAX_PROGRESS_COLS]), dict(items[MAX_PROGRESS_COLS:])


def _demoted_number_column(label: str, opts: dict | None):
    """
    The demotion target (VIZ_SPEC_pass6 S7.2): a plain formatted NumberColumn,
    same `help`/`format` the caller gave the (would-be) ProgressColumn --
    "demote the rest to a NumberColumn (ref_labels + an explicit FR format)".
    """
    import streamlit as st
    opts = opts or {}
    return st.column_config.NumberColumn(label, help=opts.get("help"), format=opts.get("format", "%.1f%%"))


def sparkline_column(label: str, *, help_text: str | None = None,
                      y_min: float | None = None, y_max: float | None = None):
    """
    `st.dataframe` column_config entry for a per-row trend column (VIZ_BACKLOG
    #2 -- page 10 lost its sparkline when it moved onto the shared ranked-table
    API). The cell value must be a list/array of numbers (e.g. one entity's
    yearly counts) -- `ranked_table()` does not build that list, it only wires
    the column config for a column the caller's frame already carries.
    """
    import streamlit as st
    return st.column_config.LineChartColumn(label, help=help_text, y_min=y_min, y_max=y_max)


def link_column(label: str, *, help_text: str | None = None, display_text: str | None = None):
    """
    `st.dataframe` column_config entry for a clickable-URL column (VIZ_BACKLOG
    #2 -- page 10's lost click-through, e.g. to a country's OpenAlex works or
    the entity's own drill page). `display_text` lets the caller show a short
    label ("voir ↗") instead of the raw URL.
    """
    import streamlit as st
    return st.column_config.LinkColumn(label, help=help_text, display_text=display_text)


# ============================================================================
# STREAMLIT-FACING COMPOSITION
# ============================================================================

def ranked_table(
    df_topn_plus_pad: pd.DataFrame,
    *,
    key: str,
    id_col: str,
    search_cols: Sequence[str],
    default_n: int = DEFAULT_TOP_N,
    has_members: bool = True,
    member_ids=CONSORTIUM_IDS,
    progress_cols: dict[str, dict] | None = None,
    number_cols: dict[str, dict] | None = None,
    sparkline_cols: dict[str, dict] | None = None,
    link_cols: dict[str, dict] | None = None,
    mean_cols: Sequence[str] = (),
    extra_hidden: Sequence[str] = (),
    ref_labels: dict[str, str] | None = None,
    height: int | None = None,
    more_step: int | None = None,
    query_min_n: int = QUERY_MIN_N,
):
    """
    Wire the pure functions into one panel: search box (auto-hidden below
    `query_min_n`, P6-R6) -> member-mask toggle (if `has_members`) ->
    depth-extension ("afficher plus", single-reveal or +`more_step`-per-click,
    P6-R6/P8) -> `st.dataframe` with progress/sparkline/link columns and the
    median-first column order. Returns the currently VISIBLE slice (for a
    caller that also wants to wire `lib.exports` on the same rows).
    `df_topn_plus_pad` must already be materialized by the caller as at least
    top-(`default_n` + MEMBER_PAD) rows when `has_members=True`, so the
    member-mask re-slice never needs to go back to the data source.

    `progress_cols`: {column: {"help": str, "min_value":..., "max_value":...}}.
    VIZ_SPEC_pass6 S7.2 wants AT MOST ONE rendered as a bar -- a caller passing
    more (a pass-5 call site not yet migrated) never crashes: the FIRST entry
    (dict insertion order) is kept as the bar, the rest are silently DEMOTED to
    a plain NumberColumn (`resolve_progress_cols()`), logged once per table
    `key` (never raised -- the suite stays green between waves, plan P9).
    `number_cols`: {column: {"help": str, "format": str}} -- the FIRST-CLASS way
    to request a plain formatted `NumberColumn` (pass-6 fix round, S-LENS D6):
    every wave-3 call site that wants "one bar + several formatted numbers"
    used to stack them all into `progress_cols` and lean on the demotion
    fallback above to sort it out at render time -- functionally identical
    output, but the WARNING fired in production every time, and the intent
    ("this column was never meant to be a bar") lived only in a code comment.
    `number_cols` renders via the exact same `_demoted_number_column()` used
    for a demotion (byte-identical visual), through an explicit path that
    never touches `resolve_progress_cols` and never logs. The fallback itself
    stays in place unchanged -- it still catches an un-migrated call site
    that genuinely passes 2+ `progress_cols` entries by mistake.
    `sparkline_cols` / `link_cols`: same {column: {opts}} shape, rendered via
    `sparkline_column()` / `link_column()` (VIZ_BACKLOG #2 -- the trend/
    click-through columns page 10 lost). `extra_hidden`: columns hidden from
    `column_order` alongside `mean_cols` (passthrough to
    `build_column_order()`) without being demoted to a "mean" semantic --
    e.g. a raw id column a caller wants addressable but not shown by default.
    `ref_labels`: {column: display_label} passed straight to
    `st.column_config.Column(label=...)` for columns not already covered by
    progress/sparkline/link -- lets a caller say "FWCI (réf. France)" vs
    "FWCI (monde, OpenAlex)" explicitly rather than the raw column name.

    `more_step`: `None` (default) reveals everything materialized on the
    FIRST "afficher plus" click (pass-5 behaviour, fine for the <=30-deep
    tops tables); an int (plan P8, the Annuaire) reveals `more_step` more
    rows per click instead, however large the caller's materialized frame is.

    No `on_select` wiring: click-through/selection-on-row-click is a
    documented NON-GOAL of this component (backlog #2 is the sparkline/link
    columns above, not row selection) -- a page wanting it builds its own
    `st.dataframe(..., on_select=...)` call outside `ranked_table()`.
    """
    progress_cols, demoted_progress_cols = resolve_progress_cols(progress_cols)
    if demoted_progress_cols and key not in _DEMOTION_WARNED:
        _DEMOTION_WARNED.add(key)
        _logger.warning(
            "ranked_table(key=%r): keeping ProgressColumn %r, demoting %s to NumberColumn "
            "(VIZ_SPEC_pass6 S7.2 'one ProgressColumn per visible table. Never two.' -- "
            "migrate this call site to a single progress_cols entry)",
            key, next(iter(progress_cols), None), sorted(demoted_progress_cols),
        )

    import streamlit as st

    full_n = len(df_topn_plus_pad)
    query = ""
    if should_show_query_box(full_n, threshold=query_min_n):
        query = st.text_input("Rechercher :", "", key=f"{key}_query")
    hide_members = False
    if has_members:
        hide_members = st.toggle(HIDE_MEMBERS_LABEL, value=False, key=f"{key}_hide_members")

    working = df_topn_plus_pad
    if has_members:
        working = mask_members(working, id_col, member_ids, hide_members)
    working = filter_by_query(working, query, search_cols)

    shown_key = f"{key}_shown_n"
    shown_n = st.session_state.get(shown_key, default_n)
    visible = working.head(shown_n)

    display_df = visible.copy()
    # S-LENS D7 fix (pass-6 fix round, the reproducible #38 recurrence): masking
    # removes every member row FIRST (mask_members() above), so a badge column
    # computed on what's left is empty by construction whenever hide_members is
    # ON -- not a bug in the badge logic, but a column with zero information to
    # show. Skip adding it in that state rather than render a fully-empty column.
    if has_members and id_col in display_df.columns and not hide_members:
        display_df["Consortium"] = consortium_badge_column(display_df, id_col)

    column_config = {}
    for col, opts in (progress_cols or {}).items():
        column_config[col] = progress_column(
            ref_labels.get(col, col) if ref_labels else col,
            help_text=(opts or {}).get("help"),
            min_value=(opts or {}).get("min_value", 0),
            max_value=(opts or {}).get("max_value", 100),
            format=(opts or {}).get("format", "%.1f%%"),
        )
    for col, opts in (demoted_progress_cols or {}).items():
        column_config[col] = _demoted_number_column(
            ref_labels.get(col, col) if ref_labels else col, opts,
        )
    for col, opts in (number_cols or {}).items():
        column_config[col] = _demoted_number_column(
            ref_labels.get(col, col) if ref_labels else col, opts,
        )
    for col, opts in (sparkline_cols or {}).items():
        column_config[col] = sparkline_column(
            ref_labels.get(col, col) if ref_labels else col,
            help_text=(opts or {}).get("help"),
            y_min=(opts or {}).get("y_min"),
            y_max=(opts or {}).get("y_max"),
        )
    for col, opts in (link_cols or {}).items():
        column_config[col] = link_column(
            ref_labels.get(col, col) if ref_labels else col,
            help_text=(opts or {}).get("help"),
            display_text=(opts or {}).get("display_text"),
        )
    if ref_labels:
        for col, label in ref_labels.items():
            if col not in column_config:
                column_config[col] = st.column_config.Column(label=label)

    column_order = build_column_order(display_df.columns, mean_cols=mean_cols, extra_hidden=extra_hidden)

    # `height=None` is rejected outright by this Streamlit build (must be a positive
    # int, "stretch" or "content") -- omit the kwarg entirely rather than pass a
    # default it does not accept, so a caller that never asked for a fixed height
    # gets the normal auto-sized table instead of a crash.
    dataframe_kwargs = dict(
        use_container_width=True, hide_index=True,
        column_config=column_config, column_order=column_order,
    )
    if height is not None:
        dataframe_kwargs["height"] = height
    st.dataframe(display_df, **dataframe_kwargs)

    if len(working) > shown_n:
        if st.button(MORE_LABEL, key=f"{key}_more_btn"):
            st.session_state[shown_key] = next_reveal_count(shown_n, len(working), more_step)
            st.rerun()

    return visible
