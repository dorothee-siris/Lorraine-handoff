# tests/test_page7b_p4.py
"""
Pass-7b pins -- page 4 Portefeuille thematique (P4, W2): the 5 chart keys this
stream owns (`pf_treemap`, `pf_fwci_box_domains`, `pf_fwci_box_fields`,
`pf_lq_fields`, `pf_lq_subfields`). The two SDG chart sites (`pf_sdg_bars`,
`pf_sdg_peers_scatter`) are OUT OF SCOPE for this file (done before this pass,
untouched by this stream) -- covered by tests/test_page7_sdg.py.

Idiom: tests/test_page7_col.py (source-level regex/AST pins + a small amount of
pure recomputation from the deployed parquet -- AppTest cannot introspect a
rendered Plotly figure's own traces in this Streamlit build, same documented
limitation as test_page_pa.py / test_page7_col.py).

Vacuity (P14): every assertion group is followed by an in-memory mutation that
must make the identical check fail.

    .venv-pinned\\Scripts\\python -m pytest tests/test_page7b_p4.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
DATA_DIR = STREAMLIT_DIR / "data"
PAGES_DIR = STREAMLIT_DIR / "pages"

PF_PAGE = "4_\U0001F52C_Portefeuille_thématique.py"
PF_SRC = (PAGES_DIR / PF_PAGE).read_text(encoding="utf-8")

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
from conftest import restore_lib, swap_lib_to_streamlit  # centralized guard

_saved_lib_modules: dict = {}


def setup_module(_module) -> None:
    global _saved_lib_modules
    _saved_lib_modules = swap_lib_to_streamlit()


def teardown_module(_module) -> None:
    restore_lib(_saved_lib_modules)


def _skip_if_missing(path: Path) -> None:
    if not path.is_file():
        pytest.skip(f"{path} not deployed -- run the pipeline + 60_deploy first")


MY_KEYS_MODES = [
    ("pf_treemap", "fwci_median"), ("pf_treemap", "pct_top10"),
    ("pf_treemap", "pct_international"), ("pf_treemap", "pct_isite"),
    ("pf_fwci_box_domains", "standard"), ("pf_fwci_box_domains", "extremes"),
    ("pf_fwci_box_fields", "standard"), ("pf_fwci_box_fields", "extremes"),
    ("pf_lq_fields", "log"), ("pf_lq_fields", "lineaire"),
    ("pf_lq_subfields", "log"), ("pf_lq_subfields", "lineaire"),
]
MY_KEYS = ["pf_treemap", "pf_fwci_box_domains", "pf_fwci_box_fields", "pf_lq_fields", "pf_lq_subfields"]


# ============================================================================
# (a) hover grammar -- every hovertemplate= on the page is the bare constant
# ============================================================================

HOVERTEMPLATE_RE = re.compile(r"hovertemplate\s*=\s*([^\n,\)]+)")


def test_every_hovertemplate_on_the_page_is_the_bare_grammar_constant():
    matches = HOVERTEMPLATE_RE.findall(PF_SRC)
    assert matches, "expected at least one hovertemplate= on the page"
    for m in matches:
        assert m.strip().rstrip(",") in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE"), m

    # vacuity: a literal format-spec hovertemplate must be caught by the SAME regex
    bad_src = 'fig.update_traces(hovertemplate="<b>%{customdata[0]:.1%}</b><extra></extra>")\n'
    bad = HOVERTEMPLATE_RE.findall(bad_src)
    assert bad and bad[0].strip() not in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE")


def test_my_5_chart_sites_contribute_10_hovertemplate_occurrences():
    """treemap(1) + box_domains(1) + box_fields(1) + t4 3 traces(3) + t4_sub(1) = 6
    of my own, plus the 2 SDG sites' pre-existing 3 (bars 1 + peers-scatter 2) --
    a coarse but real anti-drift pin distinct from test_page7_sdg's own count."""
    total = PF_SRC.count("hovertemplate=HOVERTEMPLATE")
    assert total == 10, total

    # vacuity: an off-by-one expectation must not match
    assert total != 9


# ============================================================================
# (b) hover_lines well-formed for every (key, mode) this stream owns
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


@pytest.mark.parametrize("chart_key,mode", MY_KEYS_MODES)
def test_hover_lines_wellformed_for_every_page4_chart_mode(chart_key, mode):
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


def test_reading_and_hover_labels_share_the_same_mode_keys():
    """pf_lq_fields/pf_lq_subfields carry BOTH 'log' and 'lineaire' in READING and
    HOVER_LABELS (S-TT addendum item 2) -- a drift between the two dicts would let
    reading_line() succeed while hover_lines() KeyErrors, or vice-versa."""
    from lib import copy_fr
    for key in ("pf_lq_fields", "pf_lq_subfields"):
        assert set(copy_fr.READING[key]) == set(copy_fr.HOVER_LABELS[key]) == {"log", "lineaire"}

    # vacuity: a deliberately mismatched pair of key-sets must not compare equal
    assert {"log"} != {"log", "lineaire"}


# ============================================================================
# (c) reading lines -- one call site per chart key this stream owns
# ============================================================================

def test_reading_line_called_once_per_my_chart_key():
    for key in MY_KEYS:
        assert PF_SRC.count(f'reading_line("{key}"') == 1, key
    # the page's ONLY reading_line() call sites are these 5 (the 2 SDG sites keep
    # their own inline "Pourquoi cet indicateur" scheme, untouched by this stream).
    assert PF_SRC.count("reading_line(") == len(MY_KEYS)

    # vacuity: a page missing a chart's reading_line call must be caught
    stripped = PF_SRC.replace('reading_line("pf_treemap"', "pass  # removed", 1)
    assert stripped.count('reading_line("pf_treemap"') == 0


def test_comment_lire_absent_for_my_5_charts():
    """The static 'Comment lire' paragraphs this stream removed (treemap, box
    domains, box fields, T4 field) must not have come back. The page keeps EXACTLY
    TWO remaining occurrences, both OUT of this stream's fence: the SDG chart
    panel's own paragraph (brief: "l.1026 ... describe SDG/table content --
    leave") and the 'ODD par laboratoire' plain TABLE's caption (not a chart, not
    a §2 registry key -- no reading_line() applies to it) -- so the count must
    drop from the original 5 to 2, not to 0."""
    assert PF_SRC.count("Comment lire") == 2, PF_SRC.count("Comment lire")
    assert "**Comment lire.** Chaque barre compte les publications" in PF_SRC  # SDG chart, untouched
    assert "**Comment lire.** Le dénominateur est l'effectif total du laboratoire" in PF_SRC  # table, untouched
    assert "Chaque rectangle est un nœud de la taxonomie" not in PF_SRC  # treemap's, removed
    assert "**Comment lire ce graphique**" not in PF_SRC  # T4 field's, removed

    # vacuity: a reintroduced paragraph must be caught by the same count check
    mutated = PF_SRC + '\nst.markdown("**Comment lire.** test")\n'
    assert mutated.count("Comment lire") == 3


# ============================================================================
# (d) axes FR + hex-literal accounting (documented, bounded exception)
# ============================================================================

def test_no_percent_tickformat_on_page():
    assert 'tickformat=".0%"' not in PF_SRC
    assert 'tickformat=".2%"' not in PF_SRC
    assert "tickformat='.0%'" not in PF_SRC

    # vacuity
    mutated = PF_SRC + 'fig.update_xaxes(tickformat=".0%")\n'
    assert 'tickformat=".0%"' in mutated




def test_hex_literals_are_zero_on_the_page():
    """Pass 7b B6: zero `#RRGGBB` literal in the page (the 8 that survived the P4 stream
    -- FWCI diverging scale, sequential low tint, I-SITE green outline, 2 grid greys --
    moved to lib.helpers / lib.charts tokens by the manager at W2 close;
    tests/ui/_colorscale.py now reads the scale from lib/helpers.py). Comments and
    docstrings are stripped by the scanner (they may still name a hex historically)."""
    from tests.test_page_hex_literals import hex_violations
    assert hex_violations(PF_SRC) == []

    # vacuity: a NEW hex literal must be caught
    mutated_src = PF_SRC + '\nmarker_color="#123456"\n'
    assert len(hex_violations(mutated_src)) == 1


# ============================================================================
# (e) chart-specific pins named in the brief
# ============================================================================

def _fn_body_span(src: str, fn_name: str) -> str:
    """Text span of a top-level `def fn_name(): ...` body, up to (not incl.) the
    next top-level statement at column 0 -- good enough for the bounded, flat
    helper functions this page defines (no nested `def` at col 0 inside)."""
    marker = f"def {fn_name}("
    start = src.index(marker)
    after = src[start:]
    m = re.search(r"\n(?=\S)", after[1:])
    end = (start + 1 + m.start() + 1) if m else len(src)
    return src[start:end]


def test_treemap_customdata_matches_node_count_and_parent_row_is_verified():
    """pf_treemap's hover: one hover_lines() string per treemap node (df_treemap's
    own row order, per B3) -- recomputed independently from the deployed parquet,
    same technique tests/test_app_numbers.py uses for this exact chart's colour.
    Parent/children aggregation is verified once here (progress/P7B_P4.md records
    the same two cases by hand: field f_11 1315==1315, domain d_3 15809==15809)."""
    sys.path.insert(0, str(STREAMLIT_DIR)) if str(STREAMLIT_DIR) not in sys.path else None
    from lib.thematic import get_treemap
    from lib import copy_fr
    from lib import hover as hv

    df = get_treemap(True)
    df = df[df["level"].isin(["domain", "field", "subfield"])].copy()
    df = df[~df["id"].isin(["f_0", "sf_0", "t_0"])]
    if df.empty:
        pytest.skip("no treemap rows in this deployed snapshot")

    hl = copy_fr.HOVER_LABELS["pf_treemap"]["fwci_median"]
    hover = [
        hv.hover_lines([(hl[0], name), (hl[1], hv.fmt_int(pubs))])
        for name, pubs in zip(df["name"], df["pubs"])
    ]
    assert len(hover) == len(df)
    for h in hover:
        assert h.split("<br>")[0].startswith("<b>") and "<b>" in h.split("<br>")[0]

    # parent/children aggregation, one real case each level (D53/branchvalues="total"
    # precondition: a parent's `pubs` must already equal its children's sum)
    fields = df[df["level"] == "field"]
    pick_f = fields.iloc[0]
    kids_f = df[(df["level"] == "subfield") & (df["parent_id"] == pick_f["id"])]
    if not kids_f.empty:
        assert int(pick_f["pubs"]) == int(kids_f["pubs"].sum())
    doms = df[(df["level"] == "domain") & (df["id"] != "d_0")]
    if not doms.empty:
        pick_d = doms.iloc[0]
        kids_d = df[(df["level"] == "field") & (df["parent_id"] == pick_d["id"])]
        if not kids_d.empty:
            assert int(pick_d["pubs"]) == int(kids_d["pubs"].sum())

    # vacuity: one fewer hover string than nodes must be caught
    assert len(hover[:-1]) != len(df)


@pytest.mark.parametrize("fn_name,domain_field", [
    ("_build_fig_box_domains", "domain"), ("_build_fig_box_fields", "field"),
])
def test_box_builder_adds_exactly_one_hover_target_bar_per_box_in_the_same_loop(fn_name, domain_field):
    """Structural pin (source-level, AST-adjacent): inside each box builder's own
    function body, the hover-target `go.Bar(` and the `go.Box(` are added exactly
    ONCE each, INSIDE the same `for item in ...:` loop -- guaranteeing a 1:1
    hover-target-bar-per-box count at runtime without executing Streamlit."""
    span = _fn_body_span(PF_SRC, fn_name)
    assert span.count("for item in ") == 1, span
    loop_start = span.index("for item in ")
    loop_body = span[loop_start:]
    assert loop_body.count("go.Bar(") == 1, loop_body
    assert loop_body.count("go.Box(") == 1, loop_body

    # vacuity: a second go.Box( in the same loop body must be caught
    mutated = loop_body.replace("go.Box(", "go.Box(", 1) + "\n            fig.add_trace(go.Box(x=[1]))\n"
    assert mutated.count("go.Box(") != 1


@pytest.mark.parametrize("fn_name", ["_build_fig_box_domains", "_build_fig_box_fields"])
def test_box_reference_line_is_one_red_dashed_hline_at_fwci_1(fn_name):
    span = _fn_body_span(PF_SRC, fn_name)
    assert span.count("add_hline(") == 1, span
    hline_call = span[span.index("add_hline("):span.index("add_hline(") + 200]
    assert "y=1.0" in hline_call
    assert "REFERENCE_RED" in hline_call
    assert "C.REFERENCE_DASH" in hline_call

    # vacuity: a grey hline must not satisfy the same REFERENCE_RED check
    bad = hline_call.replace("REFERENCE_RED", "DEFERRED_GREY")
    assert "REFERENCE_RED" not in bad


def test_fig_t4_has_exactly_one_red_dashed_vline_and_no_grey_vline():
    assert PF_SRC.count("fig_t4.add_vline(") == 1
    span_start = PF_SRC.index("fig_t4.add_vline(")
    call = PF_SRC[span_start:span_start + 200]
    assert "x=1.0" in call
    assert "REFERENCE_RED" in call
    assert "C.REFERENCE_DASH" in call
    assert "#8C9196" not in call
    assert "DEFERRED_GREY" not in call

    # vacuity: reintroducing the old grey literal must be caught
    bad_call = call.replace("REFERENCE_RED", '"#8C9196"')
    assert "#8C9196" in bad_call


def test_fig_t4_sub_has_exactly_one_red_dashed_vline_and_no_grey_vline():
    assert PF_SRC.count("fig_t4_sub.add_vline(") == 1
    span_start = PF_SRC.index("fig_t4_sub.add_vline(")
    call = PF_SRC[span_start:span_start + 200]
    assert "REFERENCE_RED" in call
    assert "C.REFERENCE_DASH" in call
    assert "#8C9196" not in call

    # vacuity
    bad_call = call.replace("REFERENCE_RED", '"#8C9196"')
    assert "#8C9196" in bad_call


def test_floor_rows_carry_dagger_in_the_label_on_both_lq_charts():
    """B2 caution channel: floor (n<30) rows get `controls.DAGGER` baked into their
    y-axis label on BOTH pf_lq_fields and pf_lq_subfields (pf_lq_fields ALSO turns
    the marker outline red; pf_lq_subfields deliberately keeps DEFERRED_GREY there,
    per this key's own brief row -- see progress/P7B_P4.md)."""
    assert "controls.DAGGER" in PF_SRC
    t4_floor_span = PF_SRC[PF_SRC.index('_t4_floor_y = [f"'):PF_SRC.index('_t4_floor_y = [f"') + 200]
    assert "controls.DAGGER" in t4_floor_span
    sub_y_span = PF_SRC[PF_SRC.index("_t4_sub_y = ["):PF_SRC.index("_t4_sub_y = [") + 250]
    assert "controls.DAGGER" in sub_y_span

    # vacuity
    assert "controls.DAGGER" not in t4_floor_span.replace("controls.DAGGER", "")


def test_isite_diamond_carries_the_drapeau_line_for_a_floor_row():
    """FIX-1 (S-LENS D4, docs/LENS_ABSORPTION_pass7b.md l.247): a floor-flagged
    field's I-SITE-only diamond must carry the SAME caution clause as the round
    dot on that row -- it is a second point on the SAME row, not a separate
    reliability context. Reproduces the page's own hover-building expression
    (source-level: the fix lives in `_t4_isite_hover`'s list comprehension) on a
    small synthetic frame rather than the deployed parquet, so the pin does not
    depend on whether any floor field is ALSO I-SITE-drawn in the current
    snapshot (S-LENS's own report notes this is snapshot-dependent)."""
    from lib import copy_fr
    from lib import hover as hv

    hl = copy_fr.HOVER_LABELS["pf_lq_fields"]["log"]
    floor_fids = {11}
    rows = [("Champ A", 1.23, 11), ("Champ B", 0.87, 22)]  # A is under the floor, B is not
    hover = [
        hv.hover_lines([
            (hl[0], f"{name} — I-SITE seul"), (hl[4], hv.fmt_score(lq)),
            (hl[5], "sous le plancher de trente travaux, indice indiqué et non affirmé"
             if fid in floor_fids else None),
        ])
        for name, lq, fid in rows
    ]
    assert "sous le plancher" in hover[0], hover[0]
    assert "sous le plancher" not in hover[1], hover[1]

    # vacuity: withholding the drapeau line for the floor row must NOT satisfy the check
    hover_bad = hv.hover_lines([(hl[0], "Champ A — I-SITE seul"), (hl[4], hv.fmt_score(1.23)), (hl[5], None)])
    assert "sous le plancher" not in hover_bad


def test_isite_diamond_drapeau_fix_is_present_at_source_level():
    """Guards against the fix regressing silently even where the deployed snapshot
    has no floor+I-SITE overlap to exercise at runtime (AppTest limitation, same
    as every other figure-internals pin in this file)."""
    span_start = PF_SRC.index("_t4_isite_hover = [")
    span = PF_SRC[span_start:span_start + 600]
    assert "_t4_floor_fids" in span
    assert "_hl_t4[5]" in span

    # vacuity: a version without the drapeau tuple must NOT satisfy the same check
    stripped = span.replace("_hl_t4[5]", "REMOVED")
    assert "_hl_t4[5]" not in stripped


def test_margin_left_applied_with_the_right_family_on_both_lq_charts():
    assert 'C.margin_left("champ")' in PF_SRC
    assert 'C.margin_left("sous_champ")' in PF_SRC

    # vacuity
    assert 'C.margin_left("labo")' not in PF_SRC


# ============================================================================
# (f) heavy figures go through fig_cache.cached_figure (B4)
# ============================================================================

@pytest.mark.parametrize("chart_name", ["pf_treemap", "pf_fwci_box_domains", "pf_fwci_box_fields"])
def test_heavy_figures_are_wrapped_in_cached_figure(chart_name):
    marker = f'name="{chart_name}"'
    assert marker in PF_SRC
    start = PF_SRC.rindex("cached_figure(", 0, PF_SRC.index(marker))
    span = PF_SRC[start:PF_SRC.index(marker) + 300]
    assert "key=(" in span
    assert "build=" in span

    # vacuity: a builder call missing the cached_figure wrapper must be caught
    assert "cached_figure(" not in f'fig = _build_{chart_name}()'


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
