# tests/test_page7b_p1213.py
"""
Pass-7b pins -- pages 12 Profil auteur + 13 Identifiants et couverture (P12-13, W3): the 3
remaining chart keys migrate onto the pass-7 grammar (BUILD_PLAN.md B2/B3/B5/B6, SS2 table,
`docs/tooltip_spec.yaml`): `author_yearly_bars` (p12, year bars kept, hover+tokens added),
`id_orcid_yearly` (p13, year bars kept, the ad-hoc annotation becomes the P1 caution channel),
`id_orcid_fields` (p13, vertical bars -> `charts.bars_with_gutter`, family `champ`).

Idiom: `tests/test_page7_col.py` / `tests/test_page7b_p2.py` (AppTest cannot introspect a
rendered Plotly figure's own traces in this Streamlit build -- pure-function/source-regex
pins instead). Vacuity (P14): every assertion group is followed by an in-memory mutation
that must make the identical check fail.

    .venv-pinned\\Scripts\\python -m pytest tests\\test_page7b_p1213.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
PAGES_DIR = STREAMLIT_DIR / "pages"

PROFIL_PAGE = next(PAGES_DIR.glob("12_*.py")).name
IDENT_PAGE = next(PAGES_DIR.glob("13_*.py")).name
PROFIL_SRC = (PAGES_DIR / PROFIL_PAGE).read_text(encoding="utf-8")
IDENT_SRC = (PAGES_DIR / IDENT_PAGE).read_text(encoding="utf-8")

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


# ============================================================================
# (a) hover grammar -- every hovertemplate on both pages is the bare constant
# ============================================================================

HOVERTEMPLATE_RE = re.compile(r"hovertemplate\s*=\s*([^\n,\)]+)")


def test_every_hovertemplate_on_both_pages_is_the_bare_grammar_constant():
    for src in (PROFIL_SRC, IDENT_SRC):
        matches = HOVERTEMPLATE_RE.findall(src)
        assert matches, "expected at least one hovertemplate= on the page"
        for m in matches:
            assert m.strip().rstrip(",") in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE"), m

    # vacuity: a literal format-spec hovertemplate must be caught by the SAME regex
    bad_src = 'fig.update_traces(hovertemplate="<b>%{customdata[0]:.1%}</b><extra></extra>")\n'
    bad = HOVERTEMPLATE_RE.findall(bad_src)
    assert bad and bad[0].strip() not in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE")


# ============================================================================
# (b) hover_lines well-formed for every (key, mode) on the two pages
# ============================================================================

BOLD_ONLY_RE = re.compile(r"^<b>[^<]+</b>$")
BOLD_COLON_RE = re.compile(r"^<b>[^<]+</b> : .+$")


def _assert_hover_wellformed(hover_str: str) -> None:
    lines = hover_str.split("<br>")
    assert lines[0].startswith("<b>"), f"line 1 must start with <b>: {lines[0]!r}"
    assert BOLD_ONLY_RE.match(lines[0]), f"line 1 must be bold-only (the entity): {lines[0]!r}"
    for line in lines[1:]:
        assert BOLD_ONLY_RE.match(line) or BOLD_COLON_RE.match(line), (
            f"line 2+ must be '<b>label</b> : value' or a bold-only flag line, got: {line!r}"
        )
    assert len(lines) <= 8


@pytest.mark.parametrize("chart_key,mode", [
    ("author_yearly_bars", "default"), ("id_orcid_yearly", "default"), ("id_orcid_fields", "default"),
])
def test_hover_lines_wellformed_for_every_p1213_chart_mode(chart_key, mode):
    from lib import copy_fr
    from lib import hover as hv
    labels = copy_fr.HOVER_LABELS[chart_key][mode]
    values = ["Entité X"] + [f"valeur {i}" for i in range(1, len(labels))]
    _assert_hover_wellformed(hv.hover_lines(list(zip(labels, values))))

    # a false `when` withholds every non-entity line -> still wellformed (entity only)
    withheld = ["Entité X"] + [None] * (len(labels) - 1)
    hover_withheld = hv.hover_lines(list(zip(labels, withheld)))
    _assert_hover_wellformed(hover_withheld)
    assert hover_withheld == "<b>Entité X</b>"

    # vacuity: a malformed line must be CAUGHT by _assert_hover_wellformed
    with pytest.raises(AssertionError):
        _assert_hover_wellformed("<b>Entité X</b><br>libellé sans mise en forme : 3")


# ============================================================================
# (c) reading lines -- exactly once per chart key, on the right page; page 12's
#     ONE surviving "Comment lire" belongs to the impact-drill KPI tiles (brief
#     "leave it unless it describes this chart" -- it does not), page 13 has none.
# ============================================================================

def test_reading_line_called_once_per_chart_key():
    assert PROFIL_SRC.count('reading_line("author_yearly_bars"') == 1
    assert PROFIL_SRC.count("reading_line(") == 1

    assert IDENT_SRC.count('reading_line("id_orcid_yearly"') == 1
    assert IDENT_SRC.count('reading_line("id_orcid_fields"') == 1
    assert IDENT_SRC.count("reading_line(") == 2

    # vacuity: a page missing a chart's reading_line call must be caught by the same check
    stripped = IDENT_SRC.replace('reading_line("id_orcid_fields")', "pass  # removed", 1)
    assert stripped.count('reading_line("id_orcid_fields"') == 0


def test_comment_lire_survives_only_on_the_non_chart_profil_block():
    """Page 12 keeps its ONE "Comment lire." for the impact-drill KPI tiles (not a
    chart this stream owns); page 13 never had one."""
    assert PROFIL_SRC.count("Comment lire") == 1
    marker = "with st.expander(IMPACT_DRILL_LABEL_FR"
    idx = PROFIL_SRC.find(marker)
    assert idx != -1
    assert "Comment lire" in PROFIL_SRC[idx:], "the surviving occurrence must sit in the impact-drill block"
    assert IDENT_SRC.count("Comment lire") == 0

    # vacuity: re-inserting a chart-level "Comment lire" on page 13 must move the count off 0
    mutated = IDENT_SRC + '\nst.caption("**Comment lire.** injected")\n'
    assert mutated.count("Comment lire") == 1


# ============================================================================
# (d) no percent tickformat / no hex literal anywhere on either page (both
#     pages carry ONLY the 3 chart sites this stream owns -- whole-file scan)
# ============================================================================

HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}")


def test_no_percent_tickformat_or_hex_on_either_page():
    for src in (PROFIL_SRC, IDENT_SRC):
        assert "tickformat=" not in src
        offenders = HEX_RE.findall(src)
        assert not offenders, offenders

    # vacuity: a hex literal spliced into the SAME text must be caught
    mutated = IDENT_SRC + '\ncolor="#123ABC"\n'
    assert HEX_RE.findall(mutated)


# ============================================================================
# (e) page-specific pins (brief "Specifics")
# ============================================================================

def test_author_yearly_bars_uses_ul_color_not_a_hex_literal():
    """Page 12 pin (f): marker.color == H.UL_COLOR (source-level -- AppTest cannot
    introspect a rendered Plotly figure's own traces in this build, same
    limitation test_page_pg.py's own docstring names)."""
    assert "marker_color=H.UL_COLOR," in PROFIL_SRC
    assert '"#0072B2"' not in PROFIL_SRC

    # vacuity: the old literal must NOT satisfy the token check
    old_line = 'marker_color="#0072B2",'
    assert "marker_color=H.UL_COLOR," not in old_line


def test_id_orcid_yearly_caution_channel_replaces_the_ad_hoc_annotation():
    """Page 13 pin (f): no `#D55E00`, no `add_annotation` call, no typed-year
    annotation text -- the P1 caution channel (REFERENCE_RED ink + DAGGER on the
    affected bar's own text, reason in the hover drapeau line) replaces it entirely."""
    assert '"#D55E00"' not in IDENT_SRC
    assert "add_annotation" not in IDENT_SRC
    assert "_year_break_flags[-1] = _last_pct < _prev_pct" in IDENT_SRC
    assert "H.REFERENCE_RED if flagged else H.TEXT_PRIMARY" in IDENT_SRC
    assert "DAGGER" in IDENT_SRC.split("fig_year = go.Figure")[0][-800:] \
        or 'f"{hv.fmt_pct(v)} {DAGGER}"' in IDENT_SRC
    assert "COVERAGE_BREAK_FLAG_FR if flagged else None" in IDENT_SRC

    # vacuity: the OLD annotation-based source must fail every one of these checks
    old_src = (
        'fig_year.add_annotation(x=str(int(last_row["year_int"])), y=last_row["pct_orcid"] * 100,\n'
        '    text=f"{int(last_row[\'year_int\'])} : -{drop_pt_fr} pt vs {int(prev_row[\'year_int\'])}",\n'
        '    showarrow=True, arrowhead=2, ay=-45, font=dict(color="#D55E00"))\n'
    )
    assert "add_annotation" in old_src and '"#D55E00"' in old_src


def test_id_orcid_fields_gutter_text_matches_fmt_pct_of_the_shares():
    """Page 13 pin (f): the horizontal migration's phantom gutter trace text ==
    fmt_pct of the values (mirrors tests/test_page7b_p2.py's lab_field_share pin --
    same builder, same value_fmt convention)."""
    from lib import charts as C
    from lib import hover as hv

    df = pd.DataFrame({
        "label": ["Physique", "Inconnu"], "pct_pct": [82.4, 5.0],
        "n_works": [500, 12], "color": ["#000000", "#111111"],
        "hover": ["h1", "h2"],
    })
    fig = C.bars_with_gutter(
        df, family="champ", label_col="label", value_col="pct_pct",
        color=df["color"].tolist(), hover_col="hover", value_fmt=hv.fmt_pct,
    )
    gutter_trace = fig.data[-1]
    assert list(gutter_trace.text) == [hv.fmt_pct(82.4), hv.fmt_pct(5.0)]
    # never the raw count formatted as an integer (the pre-migration behaviour)
    assert list(gutter_trace.text) != [hv.fmt_int(500), hv.fmt_int(12)]

    # vacuity
    assert list(gutter_trace.text) != [hv.fmt_pct(0.0), hv.fmt_pct(0.0)]


def test_id_orcid_fields_fr_percent_axis_overrides_ticktext_only():
    """B5: `bars_with_gutter`'s own x-axis ticks are ALWAYS `H.fr_int` internally
    (lib/charts.py L503) -- the page must re-label them in FR percent AFTER the
    call, tickvals untouched (the exact idiom already shipped on page 2's
    `plot_field_share_pair_left`, tests/test_page7b_p2.py)."""
    assert "fig_field.update_xaxes(ticktext=[fr_pct(v, 0) for v in fig_field.layout.xaxis.tickvals])" \
        in IDENT_SRC

    from lib import charts as C
    from lib import hover as hv
    from lib.helpers import fr_pct

    df = pd.DataFrame({
        "label": ["A", "B"], "pct_pct": [42.0, 7.0], "n_works": [10, 2],
        "color": ["#000000", "#111111"], "hover": ["h1", "h2"],
    })
    fig = C.bars_with_gutter(
        df, family="champ", label_col="label", value_col="pct_pct",
        color=df["color"].tolist(), hover_col="hover", value_fmt=hv.fmt_pct,
    )
    raw_tickvals = list(fig.layout.xaxis.tickvals)
    fig.update_xaxes(ticktext=[fr_pct(v, 0) for v in fig.layout.xaxis.tickvals])
    assert list(fig.layout.xaxis.tickvals) == raw_tickvals, "tickvals must NOT change"
    assert all("%" in t for t in fig.layout.xaxis.ticktext)

    # vacuity: a page that left the default fr_int ticktext must NOT carry a "%" sign
    from lib.helpers import fr_int
    assert not all("%" in fr_int(v) for v in raw_tickvals)


# ============================================================================
# FIX-1 (hostile lens, docs/LENS_ABSORPTION_pass7b.md l.406-407)
# ============================================================================

_COVERAGE_PARQUET = STREAMLIT_DIR / "data" / "aut_coverage.parquet"


def test_d7_id_orcid_yearly_plots_the_work_level_share_not_the_person_level_one():
    """D7 (HIGH): the label/reading text is WORK-level ("part des travaux..."), so
    the plotted/hover'd share must be `pct_works_orcid` (n_works_orcid_author /
    n_works), never the PERSON-level `pct_orcid` the pre-fix page plotted -- the
    real aut_coverage rows show these genuinely differ (2019: 68,1 % vs 67,1 %),
    so this reconciles against the ACTUAL deployed data, not a synthetic stand-in."""
    assert 'hv.fmt_pct(row["pct_works_orcid"] * 100)' in IDENT_SRC
    assert '_year_pct_vals = (years_df["pct_works_orcid"] * 100).round(1)' in IDENT_SRC
    assert 'row["pct_orcid"] * 100' not in IDENT_SRC
    assert '(years_df["pct_orcid"] * 100)' not in IDENT_SRC

    df = pd.read_parquet(_COVERAGE_PARQUET)
    years = df[(df["unit_kind"] == "year") & (df["conf_state"] == "all")]
    assert len(years) >= 2, "need real year rows to reconcile against"
    for _, row in years.iterrows():
        displayed_pct = round(float(row["pct_works_orcid"]) * 100, 1)
        reconciled_from_counts = round(100 * float(row["n_works_orcid_author"]) / float(row["n_works"]), 1)
        assert displayed_pct == reconciled_from_counts, (
            row["unit_id"], displayed_pct, reconciled_from_counts,
        )
        # vacuity: the RETIRED person-level column must NOT reconcile the same way
        # (proves the pin is discriminating, not vacuously true for either column)
        person_level_pct = round(float(row["pct_orcid"]) * 100, 1)
        assert person_level_pct != reconciled_from_counts, (
            "pct_orcid coincidentally matches the work-level reconciliation for "
            f"{row['unit_id']} -- pin would not have caught the D7 bug this year"
        )


def test_d8_id_orcid_fields_sorted_by_coverage_share_descending_unknown_last():
    """D8 (MED): "le mieux couvert en haut" -- gutter values must be non-increasing
    top to bottom, EXCEPT the final "Inconnu" row, which is always last regardless
    of its own share. Reproduces the page's OWN transform on the REAL deployed
    aut_coverage rows (same idiom as tests/test_page7b_p2.py's cache-key
    reproduction: the SAME real builder, a frame built the same way the page
    builds it)."""
    assert 'known = known.sort_values("pct_pct", ascending=False)' in IDENT_SRC
    assert "get_field_order_by_domain" not in IDENT_SRC

    df = pd.read_parquet(_COVERAGE_PARQUET)
    fields_df = df[(df["unit_kind"] == "field") & (df["conf_state"] == "all")].copy()
    known = fields_df[fields_df["unit_id"] != "UNKNOWN"].copy()
    known["field_id"] = known["unit_id"].astype(int)
    known["pct_pct"] = known["pct_works_orcid"].apply(lambda v: round(v * 100, 1) if pd.notna(v) else 0.0)
    known_sorted = known.sort_values("pct_pct", ascending=False)
    unknown_row = fields_df[fields_df["unit_id"] == "UNKNOWN"]

    ordered_pct = list(known_sorted["pct_pct"])
    if not unknown_row.empty:
        u = unknown_row.iloc[0]
        ordered_pct.append(round(float(u["pct_works_orcid"]) * 100, 1) if pd.notna(u["pct_works_orcid"]) else 0.0)

    known_part = ordered_pct[:-1] if not unknown_row.empty else ordered_pct
    assert all(a >= b for a, b in zip(known_part, known_part[1:])), (
        "known-field rows are not sorted coverage-descending", known_part,
    )
    assert len(ordered_pct) > len(known_part), "expected an Inconnu row appended after the known fields"

    # vacuity: the OLD domain-order sort (get_field_order_by_domain, the exact
    # pre-fix code path) must NOT satisfy the same monotonicity check on this real
    # data -- proves the pin actually discriminates the D8 bug, not vacuously true.
    from lib.helpers import get_field_order_by_domain
    old_order = get_field_order_by_domain()
    known_old = known.copy()
    known_old["sort_order"] = known_old["field_id"].map({fid: i for i, fid in enumerate(old_order)})
    domain_order_pct = list(known_old.sort_values("sort_order")["pct_pct"])
    assert not all(a >= b for a, b in zip(domain_order_pct, domain_order_pct[1:])), (
        "domain order happened to already be coverage-descending on this data -- "
        "pin would not have caught the D8 bug"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
