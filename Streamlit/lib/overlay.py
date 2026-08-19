# lib/overlay.py
"""
Pass-5 shared overlay grammar (R1, plan P10) -- authority: docs/SPRINT_KICKOFF_pass5.md +
docs/studio/VIZ_SPEC.md §1.1 ("In_LUE overlay = darker step of the same hue as its base
bar -- shipped v2 convention, kept -- never a new hue").

ONE module every page that wants an I-SITE overlay calls; no page may roll its own (S4
mission note). The sidebar toggle itself (`isite_overlay`, default OFF) lives in
lib.controls.isite_overlay_toggle() -- this module only owns the RENDERING grammar, given
an explicit `isite_on` flag the caller resolves however it likes (normally
`st.session_state.get(lib.controls.ISITE_OVERLAY_KEY, False)`).

Convention (matches the pre-existing page-1 pattern, `helpers.darken_hex` /
"ISITE overlay bars" -- generalised here so every future page reuses the SAME grammar):
  - `darken()`      : deterministic darker step of a base hex colour (thin wrapper on
                       `lib.helpers.darken_hex` -- reused, never duplicated).
  - `overlay_bars()`: one STACKED two-segment bar per category -- the I-SITE portion
                       first (darker shade, from 0) then the "rest" on top (base colour),
                       so the outer bar still reads as the base total, full-length, in
                       the base colour, with the I-SITE share inset as a darker cap at
                       its foot. Toggle OFF -> a single base-colour trace only, byte-
                       identical to a plain bar chart (no page currently calls this yet,
                       so "today" == "no overlay ever existed").
  - table-column variant: SKIPPED, not trivial (see the "TABLE-COLUMN VARIANT" section
                       below) -- a text-based companion formatter is provided instead.
"""
from __future__ import annotations

from typing import Sequence

import plotly.graph_objects as go

from lib.helpers import darken_hex, fr_int, fr_pct

# ============================================================================
# COLOUR
# ============================================================================

DEFAULT_DARKEN_FACTOR = 0.65  # matches the pre-existing page-1 convention verbatim


def darken(hex_color: str, factor: float = DEFAULT_DARKEN_FACTOR) -> str:
    """
    Deterministic darker step of the same hue -- thin wrapper on
    `lib.helpers.darken_hex` (reused, never duplicated: that function already
    ships the exact algorithm page 1 uses for its ISITE overlay bars, and this
    module's whole point is that every OTHER page reuses the same one).
    Deterministic: same input always yields the same output (pure function,
    no randomness, no state).
    """
    return darken_hex(hex_color, factor)


# ============================================================================
# BAR OVERLAY
# ============================================================================

ISITE_TRACE_NAME = "dont I-SITE"
BASE_TRACE_NAME = "Total"

# I2-01 fix: `overlay_bars()` is called with two different kinds of `totals`/`isite`
# series across the app -- most callers pass raw WORK COUNTS (page 1, 5, 6, 8, 9, 10:
# integers like `co_works`), one caller (page 2's field-distribution panel) passes
# 0-1 SHARES (`count / pubs_total`). Formatting a share with `fr_int()` silently
# rounds every value to "0" (`fr_int(0.231)` == "0") -- the exact defect the hostile
# lens caught on the overlay's own reference panel. `value_mode` makes the caller
# state which kind of series it is passing, so the tooltip formatter matches the
# data instead of assuming counts everywhere.
VALUE_MODES = ("counts", "shares")


def _tooltip_total(total: float, value_mode: str = "counts") -> str:
    if value_mode == "shares":
        return fr_pct(total * 100)
    return fr_int(total)


def _tooltip_isite(total: float, isite: float, value_mode: str = "counts") -> str:
    pct = (isite / total * 100) if total else 0.0
    if value_mode == "shares":
        # `isite` is itself a 0-1 share here (not a count) -- showing the raw
        # value would be as meaningless as fr_int() was; the ratio is the only
        # number that means anything, so the tooltip states ONLY the ratio.
        return f"dont I-SITE : {fr_pct(pct)}"
    return f"dont I-SITE : {fr_int(isite)} ({fr_pct(pct)})"


def overlay_bars(
    *,
    categories: Sequence,
    totals: Sequence[float],
    isite: Sequence[float],
    colors: Sequence[str] | str,
    isite_on: bool,
    orientation: str = "v",
    darken_factor: float = DEFAULT_DARKEN_FACTOR,
    base_name: str = BASE_TRACE_NAME,
    isite_name: str = ISITE_TRACE_NAME,
    value_mode: str = "counts",
    fig: go.Figure | None = None,
) -> go.Figure:
    """
    Render (or add traces to) a bar chart with the shared I-SITE overlay grammar.

    `colors` is either one hex string (applied to every bar) or a per-category
    sequence (e.g. domain colours) -- either way the I-SITE segment's colour is
    the SAME hue, darkened (`darken()`), never a new colour (VIZ_SPEC 1.1).

    Toggle OFF (`isite_on=False`): renders ONE trace, the totals, in the base
    colour(s) -- byte-identical to a plain bar chart that never knew about
    I-SITE at all (S4 acceptance #4: overlay-off neutrality).

    Toggle ON: renders TWO stacked traces (`barmode="stack"`) per category --
    the I-SITE segment first (darker, from 0) then the "rest" (base colour,
    on top) -- so the visible outer length still equals `totals` and the I-SITE
    share reads as a darker cap at the foot of each bar. The two segments
    always sum to `totals` by construction (`rest = total - isite`), which is
    the shape the unit tests pin ("segment sum == base value").

    Handles both orientations: `orientation="v"` puts `categories` on x and
    values on y; `orientation="h"` puts `categories` on y and values on x
    (matching `go.Bar`'s own `orientation` semantics).

    `value_mode` (I2-01 fix): `"counts"` (default) formats tooltips with
    `fr_int()` -- use this when `totals`/`isite` are raw work counts (the
    common case). `"shares"` formats them with `fr_pct()` instead -- use this
    when `totals`/`isite` are 0-1 fractions (page 2's field-distribution
    panel): the base tooltip becomes a percentage of structure, and the
    I-SITE tooltip drops the meaningless raw share and states only the ratio
    (« dont I-SITE : 35,9 % »), never a count-formatted share.
    """
    if value_mode not in VALUE_MODES:
        raise ValueError(f"value_mode must be one of {VALUE_MODES}, got {value_mode!r}")

    n = len(categories)
    totals = list(totals)
    isite = list(isite) if isite is not None else [0] * n
    if len(totals) != n or len(isite) != n:
        raise ValueError("categories, totals and isite must be the same length")

    color_list = [colors] * n if isinstance(colors, str) else list(colors)
    if len(color_list) != n:
        raise ValueError("colors must be one hex string or one per category")

    fig = fig if fig is not None else go.Figure()

    def _xy(values):
        return (values, categories) if orientation == "h" else (categories, values)

    if not isite_on:
        x, y = _xy(totals)
        fig.add_trace(go.Bar(
            x=x, y=y, orientation=orientation,
            marker_color=color_list, name=base_name,
            hovertemplate="%{customdata}<extra></extra>",
            customdata=[_tooltip_total(t, value_mode) for t in totals],
        ))
        return fig

    isite_clamped = [min(max(0.0, float(v)), float(t)) for v, t in zip(isite, totals)]
    rest = [float(t) - v for t, v in zip(totals, isite_clamped)]
    dark_colors = [darken(c, darken_factor) for c in color_list]

    x_isite, y_isite = _xy(isite_clamped)
    x_rest, y_rest = _xy(rest)

    fig.add_trace(go.Bar(
        x=x_isite, y=y_isite, orientation=orientation,
        marker_color=dark_colors, name=isite_name,
        hovertemplate="%{customdata}<extra></extra>",
        customdata=[_tooltip_isite(t, v, value_mode) for t, v in zip(totals, isite_clamped)],
    ))
    fig.add_trace(go.Bar(
        x=x_rest, y=y_rest, orientation=orientation,
        marker_color=color_list, name=base_name,
        hovertemplate="%{customdata}<extra></extra>",
        customdata=[_tooltip_total(t, value_mode) for t in totals],
    ))
    fig.update_layout(barmode="stack")
    return fig


# ============================================================================
# TABLE-COLUMN VARIANT -- SKIPPED (not trivial), text companion instead
# ============================================================================
#
# A true two-tone overlay inside an `st.dataframe` ProgressColumn was considered and
# SKIPPED: `st.column_config.ProgressColumn` renders exactly one fraction per cell (a
# single bar, one colour) -- there is no supported way to stack a second, darker
# segment inside it without a custom component, which is out of scope for a "trivial"
# helper (S4 mission note: "skip if not trivial, say so"). `isite_share_caption()` below
# is the companion instead: the same numbers as `overlay_bars()`'s tooltip, as plain FR
# text a page can put in a column's `help=` or next to a ProgressColumn showing the
# plain total.

def isite_share_caption(total: float, isite: float) -> str:
    """
    The FR-formatted "dont I-SITE : n (p %)" text (same wording/format as the
    bar-chart tooltip) for a page that wants the number, not the chart -- e.g.
    a `help=` string on a plain `ProgressColumn`, or inline next to a table cell.
    """
    return _tooltip_isite(total, isite)


# ============================================================================
# GROUPED BARS -- category x time, VIZ_SPEC_pass6 S1.5 grammar extension
# ============================================================================
#
# THE RULE (VIZ_SPEC_pass6 S1.5, verbatim): "A stacked bar may carry the I-SITE
# decomposition and nothing else. One bar = one entity, two segments (dark I-SITE
# from the baseline, base colour on top). A bar chart may never stack a second
# categorical dimension. When a panel crosses a category set with time (or with any
# second dimension), the categories are grouped side by side, and each grouped bar
# carries its own two-segment I-SITE decomposition from its own baseline."
#
# `overlay_bars()` above is UNCHANGED by this section -- it remains the one bar =
# one entity case (page 1 doc-type horizontal bars, page 8 hub companion, page 6
# top-10, page 10 countries, page 9 portage: S1.6 "unchanged" list). This is the
# OTHER case: a category set crossed with a second dimension (year), where Studio's
# measured A/B (S1.2-1.4) picked grouped over stacked. No page rolls its own -- S-LIB
# implements the geometry once.

GROUPED_BARS_HOWTOREAD_FR = (
    "Comment lire : une barre par catégorie et par année, chacune partant de zéro. "
    "Bouton I-SITE actif : le segment plus foncé au pied de chaque barre est la part "
    "I-SITE de cette catégorie cette année-là. Double-cliquez une entrée de légende "
    "pour isoler une catégorie."
)

DEFAULT_GROUP_SPAN = 0.82  # share of a category slot the whole group occupies
DEFAULT_GROUP_FILL = 0.90  # share of each sub-slot a bar fills (rest = surface gap)
GROUPED_BAR_LINE_COLOR = "white"
GROUPED_BAR_LINE_WIDTH = 1
GROUPED_LEGEND_INK = "#3A3F44"
GROUPED_GRID_COLOR = "#D9DDE2"
GROUPED_ZERO_LINE_COLOR = "#B0B6BC"


def _tooltip_grouped(label: str, group: str, total: float, isite: float,
                      isite_on: bool, value_mode: str) -> str:
    """
    THE tooltip shape (VIZ_SPEC_pass6 S1.5, "one shape, everywhere"), reusing
    `_tooltip_total`/`_tooltip_isite` (already FR-formatted, S0.1) rather than
    re-deriving the numbers -- the same two helpers `overlay_bars()` uses.
    """
    lines = [f"<b>{label}</b> {group}", f"Travaux : {_tooltip_total(total, value_mode)}"]
    if isite_on:
        lines.append(_tooltip_isite(total, isite, value_mode))
    return "<br>".join(lines)


def _series_offset_width(n: int, k: int, group_span: float, group_fill: float) -> tuple[float, float]:
    """
    VIZ_SPEC_pass6 S1.5 geometry, literal (PF-1: `offsetgroup` is broken under
    the pinned Streamlit's plotly, everywhere else it also stacks/overlaps --
    every grouped bar here is positioned with an EXPLICIT `offset`/`width`
    instead, under `barmode="overlay"`).
    """
    slot = group_span / n
    bar_w = slot * group_fill
    offset = -group_span / 2 + k * slot + (slot - bar_w) / 2
    return offset, bar_w


def overlay_grouped_bars(
    *,
    groups: Sequence[str],
    series: Sequence,
    labels: dict,
    colors: dict,
    totals: dict,
    isite: dict,
    isite_on: bool,
    darken_factor: float = DEFAULT_DARKEN_FACTOR,
    group_span: float = DEFAULT_GROUP_SPAN,
    group_fill: float = DEFAULT_GROUP_FILL,
    value_mode: str = "counts",
) -> go.Figure:
    """
    Category x time grouped bars with a per-bar I-SITE decomposition
    (VIZ_SPEC_pass6 S1.5 -- Studio A/B verdict: GROUPED WINS over stacked for
    this claim, S1.3). One trace pair per `series` entry, positioned across
    `groups` with an explicit `offset`/`width` (PF-1) under
    `barmode="overlay"` -- never `offsetgroup`, which the pinned plotly gets
    wrong under every `barmode`.

    `groups`: x categories, STRINGS (e.g. "2019".."2023"), never ints -- a
    numeric x-axis would autorange/tick differently from every other chart in
    the app. `series`: the FIXED semantic order (never sorted by value --
    corpus order for doc types, `DOMAIN_NAMES_ORDERED` + Unclassified for
    domains); every key must appear in `labels`, `colors`, `totals`, `isite`.
    `totals`/`isite`: {series_key: [value per group]}, each list the same
    length as `groups`.

    Toggle OFF (`isite_on=False`): ONE trace per series, the totals, at the
    SAME offset/width -- byte-identical to a grouped bar chart that never
    knew about I-SITE (R1 overlay-off neutrality, unchanged).

    Toggle ON: TWO traces per series -- the I-SITE segment first (darker,
    `base=0`), then the "rest" (base colour, `base=isite`) -- so the visible
    bar length is always `total` by construction (`isite` clamped to
    `[0, total]` first, matching `overlay_bars()`). Both traces of a series
    share `legendgroup=series_key`; only the "rest" trace is in the legend
    (`showlegend=False` on the I-SITE trace) -- the dark shade is named by
    `GROUPED_BARS_HOWTOREAD_FR` instead (S1.5: "the dark shade gets no legend
    entry").

    A series that is 0 across every group is KEPT, never dropped (S1.5
    "empty and thin states") -- the caller passes the full `series` list every
    time, this function never filters it.
    """
    if value_mode not in VALUE_MODES:
        raise ValueError(f"value_mode must be one of {VALUE_MODES}, got {value_mode!r}")
    if not all(isinstance(g, str) for g in groups):
        raise ValueError("groups must be strings (VIZ_SPEC_pass6 S1.5: 'STRINGS, never ints')")

    n_groups = len(groups)
    n_series = len(series)
    if n_series == 0:
        raise ValueError("series must not be empty")

    missing = [
        key for key in series
        if key not in labels or key not in colors or key not in totals or key not in isite
    ]
    if missing:
        raise ValueError(f"series key(s) missing from labels/colors/totals/isite: {missing}")
    for key in series:
        if len(totals[key]) != n_groups or len(isite[key]) != n_groups:
            raise ValueError(
                f"totals[{key!r}] and isite[{key!r}] must each have one value per group "
                f"({n_groups} groups)"
            )

    fig = go.Figure()

    for k, key in enumerate(series):
        offset, bar_w = _series_offset_width(n_series, k, group_span, group_fill)
        label = labels[key]
        color = colors[key]
        series_totals = list(totals[key])
        series_isite = list(isite[key])
        tooltips_off = [
            _tooltip_grouped(label, g, t, 0, False, value_mode)
            for g, t in zip(groups, series_totals)
        ]

        if not isite_on:
            fig.add_trace(go.Bar(
                x=list(groups), y=series_totals, offset=offset, width=bar_w,
                marker_color=color,
                marker_line_color=GROUPED_BAR_LINE_COLOR, marker_line_width=GROUPED_BAR_LINE_WIDTH,
                name=label, legendgroup=key,
                hovertemplate="%{customdata}<extra></extra>", customdata=tooltips_off,
            ))
            continue

        isite_clamped = [min(max(0.0, float(v)), float(t)) for v, t in zip(series_isite, series_totals)]
        rest = [float(t) - v for t, v in zip(series_totals, isite_clamped)]
        dark_color = darken(color, darken_factor)
        tooltips_on = [
            _tooltip_grouped(label, g, t, v, True, value_mode)
            for g, t, v in zip(groups, series_totals, isite_clamped)
        ]

        fig.add_trace(go.Bar(
            x=list(groups), y=isite_clamped, base=0, offset=offset, width=bar_w,
            marker_color=dark_color,
            marker_line_color=GROUPED_BAR_LINE_COLOR, marker_line_width=GROUPED_BAR_LINE_WIDTH,
            name=f"{ISITE_TRACE_NAME} ({label})", showlegend=False, legendgroup=key,
            hovertemplate="%{customdata}<extra></extra>", customdata=tooltips_on,
        ))
        fig.add_trace(go.Bar(
            x=list(groups), y=rest, base=isite_clamped, offset=offset, width=bar_w,
            marker_color=color,
            marker_line_color=GROUPED_BAR_LINE_COLOR, marker_line_width=GROUPED_BAR_LINE_WIDTH,
            name=label, legendgroup=key,
            hovertemplate="%{customdata}<extra></extra>", customdata=tooltips_on,
        ))

    fig.update_layout(
        barmode="overlay", bargap=0,
        legend=dict(orientation="h", y=-0.18, font=dict(color=GROUPED_LEGEND_INK, size=12)),
    )
    fig.update_yaxes(gridcolor=GROUPED_GRID_COLOR, zerolinecolor=GROUPED_ZERO_LINE_COLOR)
    return fig
