# tests/test_overlay.py
"""
Pass-5 unit pins for Streamlit/lib/overlay.py (R1, plan P10) -- the shared
I-SITE overlay grammar every page will call instead of rolling its own.

    python -m pytest tests/test_overlay.py -q

Namespace note: same `_import_streamlit_lib` swap-trick as tests/test_shared_layer.py
(see its docstring) -- Streamlit/lib and the repo-root pipeline `lib` package would
otherwise collide under the same `lib` name in `sys.modules`.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

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


(overlay,) = _import_streamlit_lib("overlay")


def _rgb(hexcode: str) -> tuple[int, int, int]:
    h = hexcode.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ============================================================================
# darken() -- deterministic darker step of the same hue
# ============================================================================

def test_darken_is_deterministic():
    a = overlay.darken("#0072B2")
    b = overlay.darken("#0072B2")
    assert a == b


def test_darken_actually_darkens_every_channel():
    base = "#0072B2"
    dark = overlay.darken(base)
    r0, g0, b0 = _rgb(base)
    r1, g1, b1 = _rgb(dark)
    assert r1 <= r0 and g1 <= g0 and b1 <= b0
    assert (r1, g1, b1) != (r0, g0, b0)


def test_darken_matches_helpers_darken_hex_exactly():
    """Reused, never duplicated (module docstring): overlay.darken() must be the
    SAME algorithm lib.helpers.darken_hex() already ships for page 1's bars."""
    (helpers,) = _import_streamlit_lib("helpers")
    for hexcode in ("#0072B2", "#009E73", "#D55E00", "#CC79A7"):
        assert overlay.darken(hexcode) == helpers.darken_hex(hexcode)


# ============================================================================
# overlay_bars() -- trace composition
# ============================================================================

def test_overlay_off_renders_one_base_trace_only():
    """Toggle OFF -> byte-identical to a plain bar chart (S4 acceptance #4)."""
    fig = overlay.overlay_bars(
        categories=["A", "B"], totals=[100, 50], isite=[10, 5],
        colors="#0072B2", isite_on=False,
    )
    assert len(fig.data) == 1
    assert list(fig.data[0].x) == ["A", "B"]
    assert list(fig.data[0].y) == [100, 50]
    assert list(fig.data[0].marker.color) == ["#0072B2", "#0072B2"]


def test_overlay_on_segments_sum_to_totals():
    """The pinned shape: isite segment + rest segment == totals, every category."""
    totals = [100, 50, 0]
    isite = [10, 5, 0]
    fig = overlay.overlay_bars(
        categories=["A", "B", "C"], totals=totals, isite=isite,
        colors="#0072B2", isite_on=True,
    )
    assert len(fig.data) == 2
    isite_trace, rest_trace = fig.data
    for i_val, r_val, total in zip(isite_trace.y, rest_trace.y, totals):
        assert i_val + r_val == total


def test_overlay_on_colours_are_base_plus_darkened_base():
    fig = overlay.overlay_bars(
        categories=["A", "B"], totals=[100, 50], isite=[10, 5],
        colors="#0072B2", isite_on=True,
    )
    isite_trace, rest_trace = fig.data
    assert list(rest_trace.marker.color) == ["#0072B2", "#0072B2"]
    assert all(c == overlay.darken("#0072B2") for c in isite_trace.marker.color)


def test_overlay_per_category_colours_darken_individually():
    """Domain-coloured bars: each category's I-SITE segment darkens ITS OWN hue,
    never a shared/wrong hue (VIZ_SPEC 1.1: never a new colour)."""
    fig = overlay.overlay_bars(
        categories=["A", "B"], totals=[100, 50], isite=[10, 5],
        colors=["#0072B2", "#009E73"], isite_on=True,
    )
    isite_trace, rest_trace = fig.data
    assert list(rest_trace.marker.color) == ["#0072B2", "#009E73"]
    assert isite_trace.marker.color[0] == overlay.darken("#0072B2")
    assert isite_trace.marker.color[1] == overlay.darken("#009E73")


def test_overlay_handles_vertical_orientation():
    fig = overlay.overlay_bars(
        categories=["A", "B"], totals=[100, 50], isite=[10, 5],
        colors="#0072B2", isite_on=True, orientation="v",
    )
    for trace in fig.data:
        assert list(trace.x) == ["A", "B"]


def test_overlay_handles_horizontal_orientation():
    fig = overlay.overlay_bars(
        categories=["A", "B"], totals=[100, 50], isite=[10, 5],
        colors="#0072B2", isite_on=True, orientation="h",
    )
    for trace in fig.data:
        assert list(trace.y) == ["A", "B"]


def test_overlay_clamps_isite_above_total_rather_than_going_negative():
    """A data glitch (isite > total) must not produce a negative 'rest' segment."""
    fig = overlay.overlay_bars(
        categories=["A"], totals=[10], isite=[999], colors="#0072B2", isite_on=True,
    )
    isite_trace, rest_trace = fig.data
    assert isite_trace.y[0] == 10
    assert rest_trace.y[0] == 0


def test_overlay_mismatched_lengths_raise():
    import pytest
    with pytest.raises(ValueError):
        overlay.overlay_bars(
            categories=["A", "B"], totals=[100], isite=[10, 5],
            colors="#0072B2", isite_on=True,
        )


# ============================================================================
# isite_share_caption() -- FR tooltip text (table-column companion)
# ============================================================================

def test_isite_share_caption_fr_format():
    text = overlay.isite_share_caption(100, 10)
    assert "dont I-SITE" in text
    assert "10" in text
    assert "10,0" in text  # FR decimal comma
    assert "%" in text


def test_isite_share_caption_handles_zero_total():
    text = overlay.isite_share_caption(0, 0)
    assert "0" in text  # never raises a ZeroDivisionError


# ============================================================================
# value_mode="shares" -- I2-01 fix: page 2's field-distribution panel feeds
# 0-1 shares (not counts) into overlay_bars(); fr_int() silently rounds every
# share to "0" (fr_int(0.231) == "0"), which is the exact hostile-lens defect.
# These pins bind the fix, not just the pre-existing counts behaviour above.
# FR_NBSP: fr_pct() uses U+202F (narrow no-break space) before "%", never a
# plain space -- matching lib.helpers' own FR typography convention exactly.
# ============================================================================

FR_NBSP = " "


def test_overlay_shares_mode_off_base_tooltip_is_a_percentage_not_zero():
    """Toggle OFF, value_mode='shares': the base tooltip must read a FR percentage
    of the share (e.g. "23,1 %"), never fr_int's rounded-to-zero count."""
    fig = overlay.overlay_bars(
        categories=["Chemistry"], totals=[0.231], isite=[0.083],
        colors="#0072B2", isite_on=False, value_mode="shares",
    )
    assert len(fig.data) == 1
    tooltip = fig.data[0].customdata[0]
    assert tooltip == f"23,1{FR_NBSP}%"
    assert tooltip != "0"


def test_overlay_shares_mode_on_isite_tooltip_is_ratio_percentage_only():
    """Toggle ON, value_mode='shares': the I-SITE tooltip must read
    « dont I-SITE : 35,9 % » -- the isite/total RATIO, never a count-formatted
    share like "0 (35,9 %)" (I2-01's exact reproduced defect)."""
    fig = overlay.overlay_bars(
        categories=["Chemistry"], totals=[0.231], isite=[0.083],
        colors="#0072B2", isite_on=True, value_mode="shares",
    )
    isite_trace, rest_trace = fig.data
    tooltip = isite_trace.customdata[0]
    assert tooltip == f"dont I-SITE : 35,9{FR_NBSP}%"
    assert "0 (" not in tooltip  # the exact defect string, must never reappear
    assert rest_trace.customdata[0] == f"23,1{FR_NBSP}%"


def test_overlay_shares_mode_handles_zero_total_without_error():
    fig = overlay.overlay_bars(
        categories=["Empty"], totals=[0.0], isite=[0.0],
        colors="#0072B2", isite_on=True, value_mode="shares",
    )
    isite_trace, _ = fig.data
    assert isite_trace.customdata[0] == f"dont I-SITE : 0,0{FR_NBSP}%"


def test_overlay_counts_mode_is_still_the_default():
    """Default behaviour (value_mode omitted) must stay byte-identical to the
    pre-fix counts formatting -- no regression for the 6 counts-mode call sites."""
    fig = overlay.overlay_bars(
        categories=["A"], totals=[100], isite=[10], colors="#0072B2", isite_on=True,
    )
    isite_trace, rest_trace = fig.data
    assert isite_trace.customdata[0] == f"dont I-SITE : 10 (10,0{FR_NBSP}%)"
    assert rest_trace.customdata[0] == "100"


def test_overlay_invalid_value_mode_raises():
    import pytest
    with pytest.raises(ValueError):
        overlay.overlay_bars(
            categories=["A"], totals=[100], isite=[10], colors="#0072B2",
            isite_on=True, value_mode="percentages",
        )


# ============================================================================
# overlay_grouped_bars() -- VIZ_SPEC_pass6 S1.5, category x time grouped grammar
# (Studio A/B verdict: GROUPED WINS -- pass-6 grammar extension, S-LIB build)
# ============================================================================

def _grouped_fixture():
    groups = ["2019", "2020", "2021"]
    series = ["article", "book"]
    labels = {"article": "Articles", "book": "Ouvrages"}
    colors = {"article": "#22A2BD", "book": "#667900"}
    totals = {"article": [100, 120, 90], "book": [20, 15, 10]}
    isite = {"article": [10, 12, 9], "book": [2, 1, 0]}
    return groups, series, labels, colors, totals, isite


def test_grouped_bars_toggle_off_renders_exactly_one_trace_per_series():
    groups, series, labels, colors, totals, isite = _grouped_fixture()
    fig = overlay.overlay_grouped_bars(
        groups=groups, series=series, labels=labels, colors=colors,
        totals=totals, isite=isite, isite_on=False,
    )
    assert len(fig.data) == len(series)
    for trace, key in zip(fig.data, series):
        assert list(trace.y) == totals[key]
        assert trace.marker.color == colors[key]
        assert trace.legendgroup == key


def test_grouped_bars_toggle_on_renders_exactly_two_traces_per_series():
    """The pinned shape: dark I-SITE trace first (base=0), then the 'rest'
    trace (base=isite) -- so a series contributes exactly 2 traces."""
    groups, series, labels, colors, totals, isite = _grouped_fixture()
    fig = overlay.overlay_grouped_bars(
        groups=groups, series=series, labels=labels, colors=colors,
        totals=totals, isite=isite, isite_on=True,
    )
    assert len(fig.data) == 2 * len(series)
    isite_article, rest_article, isite_book, rest_book = fig.data
    assert list(isite_article.y) == isite["article"]
    assert isite_article.base == 0
    assert list(rest_article.base) == isite["article"]
    assert [i + r for i, r in zip(isite_article.y, rest_article.y)] == totals["article"]
    assert [i + r for i, r in zip(isite_book.y, rest_book.y)] == totals["book"]


def test_grouped_bars_isite_trace_hidden_from_legend_rest_trace_shown():
    groups, series, labels, colors, totals, isite = _grouped_fixture()
    fig = overlay.overlay_grouped_bars(
        groups=groups, series=series, labels=labels, colors=colors,
        totals=totals, isite=isite, isite_on=True,
    )
    isite_article, rest_article = fig.data[0], fig.data[1]
    assert isite_article.showlegend is False
    assert rest_article.showlegend is not False  # None (default True) or True
    assert rest_article.name == labels["article"]


def test_grouped_bars_legendgroup_shared_across_the_pair():
    groups, series, labels, colors, totals, isite = _grouped_fixture()
    fig = overlay.overlay_grouped_bars(
        groups=groups, series=series, labels=labels, colors=colors,
        totals=totals, isite=isite, isite_on=True,
    )
    isite_article, rest_article = fig.data[0], fig.data[1]
    assert isite_article.legendgroup == rest_article.legendgroup == "article"


def test_grouped_bars_isite_colour_is_darkened_base_colour():
    groups, series, labels, colors, totals, isite = _grouped_fixture()
    fig = overlay.overlay_grouped_bars(
        groups=groups, series=series, labels=labels, colors=colors,
        totals=totals, isite=isite, isite_on=True,
    )
    isite_article, rest_article = fig.data[0], fig.data[1]
    assert rest_article.marker.color == colors["article"]
    assert isite_article.marker.color == overlay.darken(colors["article"])


def test_grouped_bars_toggle_off_matches_a_grouped_chart_that_never_knew_about_isite():
    """R1 overlay-off neutrality, extended to the grouped grammar: OFF -> base
    colour only, no darken() ever computed, same offset/width as ON."""
    groups, series, labels, colors, totals, isite = _grouped_fixture()
    fig_off = overlay.overlay_grouped_bars(
        groups=groups, series=series, labels=labels, colors=colors,
        totals=totals, isite=isite, isite_on=False,
    )
    fig_on = overlay.overlay_grouped_bars(
        groups=groups, series=series, labels=labels, colors=colors,
        totals=totals, isite=isite, isite_on=True,
    )
    # OFF trace k's offset/width must match ON's rest-trace (2nd trace) of series k.
    for k in range(len(series)):
        off_trace = fig_off.data[k]
        on_rest_trace = fig_on.data[2 * k + 1]
        assert off_trace.offset == on_rest_trace.offset
        assert off_trace.width == on_rest_trace.width


def test_grouped_bars_offset_width_geometry_matches_the_spec_formula():
    """VIZ_SPEC_pass6 S1.5: slot = group_span/n; bar_w = slot*group_fill;
    offset_k = -group_span/2 + k*slot + (slot-bar_w)/2; width = bar_w.
    Independently re-derived here (not by importing the private helper) so the
    pin actually catches a formula regression."""
    groups, series, labels, colors, totals, isite = _grouped_fixture()
    group_span, group_fill = 0.82, 0.90
    fig = overlay.overlay_grouped_bars(
        groups=groups, series=series, labels=labels, colors=colors,
        totals=totals, isite=isite, isite_on=False,
        group_span=group_span, group_fill=group_fill,
    )
    n = len(series)
    slot = group_span / n
    bar_w = slot * group_fill
    for k, trace in enumerate(fig.data):
        expected_offset = -group_span / 2 + k * slot + (slot - bar_w) / 2
        assert trace.width == pytest.approx(bar_w)
        assert trace.offset == pytest.approx(expected_offset)


def test_grouped_bars_uses_barmode_overlay_never_offsetgroup():
    """PF-1: offsetgroup is broken under every barmode on the pinned plotly --
    the grammar is explicit offset/width under barmode='overlay'."""
    groups, series, labels, colors, totals, isite = _grouped_fixture()
    fig = overlay.overlay_grouped_bars(
        groups=groups, series=series, labels=labels, colors=colors,
        totals=totals, isite=isite, isite_on=True,
    )
    assert fig.layout.barmode == "overlay"
    assert fig.layout.bargap == 0
    for trace in fig.data:
        assert trace.offsetgroup is None


def test_grouped_bars_clamps_isite_above_total_rather_than_going_negative():
    groups = ["2019"]
    series = ["article"]
    labels = {"article": "Articles"}
    colors = {"article": "#22A2BD"}
    totals = {"article": [10]}
    isite = {"article": [999]}
    fig = overlay.overlay_grouped_bars(
        groups=groups, series=series, labels=labels, colors=colors,
        totals=totals, isite=isite, isite_on=True,
    )
    isite_trace, rest_trace = fig.data
    assert isite_trace.y[0] == 10
    assert rest_trace.y[0] == 0


def test_grouped_bars_keeps_an_all_zero_series():
    """S1.5 'empty and thin states': a series that is 0 across every group is
    KEPT (its own trace(s)), never silently dropped."""
    groups, series, labels, colors, totals, isite = _grouped_fixture()
    totals = dict(totals, book=[0, 0, 0])
    isite = dict(isite, book=[0, 0, 0])
    fig = overlay.overlay_grouped_bars(
        groups=groups, series=series, labels=labels, colors=colors,
        totals=totals, isite=isite, isite_on=True,
    )
    assert len(fig.data) == 2 * len(series)
    isite_book, rest_book = fig.data[2], fig.data[3]
    assert list(isite_book.y) == [0, 0, 0]
    assert list(rest_book.y) == [0, 0, 0]


def test_grouped_bars_rejects_non_string_groups():
    _, series, labels, colors, totals, isite = _grouped_fixture()
    with pytest.raises(ValueError, match="strings"):
        overlay.overlay_grouped_bars(
            groups=[2019, 2020, 2021], series=series, labels=labels, colors=colors,
            totals=totals, isite=isite, isite_on=False,
        )


def test_grouped_bars_rejects_mismatched_series_value_length():
    groups, series, labels, colors, totals, isite = _grouped_fixture()
    totals = dict(totals, article=[100, 120])  # 2 values for 3 groups
    with pytest.raises(ValueError):
        overlay.overlay_grouped_bars(
            groups=groups, series=series, labels=labels, colors=colors,
            totals=totals, isite=isite, isite_on=False,
        )


def test_grouped_bars_rejects_missing_series_key():
    groups, series, labels, colors, totals, isite = _grouped_fixture()
    del colors["book"]
    with pytest.raises(ValueError, match="book"):
        overlay.overlay_grouped_bars(
            groups=groups, series=series, labels=labels, colors=colors,
            totals=totals, isite=isite, isite_on=False,
        )


def test_grouped_bars_tooltip_omits_isite_line_when_toggle_off():
    groups, series, labels, colors, totals, isite = _grouped_fixture()
    fig = overlay.overlay_grouped_bars(
        groups=groups, series=series, labels=labels, colors=colors,
        totals=totals, isite=isite, isite_on=False,
    )
    tooltip = fig.data[0].customdata[0]
    assert "dont I-SITE" not in tooltip
    assert "Travaux" in tooltip


def test_grouped_bars_tooltip_includes_isite_line_when_toggle_on():
    groups, series, labels, colors, totals, isite = _grouped_fixture()
    fig = overlay.overlay_grouped_bars(
        groups=groups, series=series, labels=labels, colors=colors,
        totals=totals, isite=isite, isite_on=True,
    )
    isite_trace, rest_trace = fig.data[0], fig.data[1]
    assert "dont I-SITE" in isite_trace.customdata[0]
    assert isite_trace.customdata[0] == rest_trace.customdata[0]  # "one shape, everywhere"


def test_grouped_bars_series_order_is_never_resorted():
    """Fixed semantic order (S1.5 'Ordering'): series is never sorted by
    value, even when a later series has a bigger total."""
    groups = ["2019"]
    series = ["review", "article"]  # deliberately NOT volume order
    labels = {"review": "Revues", "article": "Articles"}
    colors = {"review": "#A55F8F", "article": "#22A2BD"}
    totals = {"review": [5], "article": [500]}
    isite = {"review": [0], "article": [50]}
    fig = overlay.overlay_grouped_bars(
        groups=groups, series=series, labels=labels, colors=colors,
        totals=totals, isite=isite, isite_on=False,
    )
    assert [trace.name for trace in fig.data] == ["Revues", "Articles"]


def test_grouped_bars_empty_series_list_raises():
    with pytest.raises(ValueError):
        overlay.overlay_grouped_bars(
            groups=["2019"], series=[], labels={}, colors={}, totals={}, isite={},
            isite_on=False,
        )
