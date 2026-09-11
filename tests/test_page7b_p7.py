# tests/test_page7b_p7.py
"""
Pass-7b P7 pins -- Streamlit/pages/7_🎯_I-SITE.py (`isite_ratio_dots` dot chart with its
live `on_select="rerun"` selection, `isite_consortium_dumbbell`). Idiom copied from
tests/test_page7_col.py (page 8, W3 precedent named in the recipe): source-level regex/AST
pins for what AppTest cannot introspect on a rendered Plotly figure (this suite's own
documented limitation -- see test_page7_col.py's module docstring), plus AppTest for what
it CAN see (markdown/caption text, session_state, toggle values).

Vacuity (P14): every assertion group below is followed by an in-memory mutation that must
make the identical check fail -- a pin that cannot fail is theater.

    .venv-pinned\\Scripts\\python -m pytest tests\\test_page7b_p7.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
PAGES_DIR = STREAMLIT_DIR / "pages"

PAGE = "7_\U0001F3AF_I-SITE.py"
PAGE_SRC = (PAGES_DIR / PAGE).read_text(encoding="utf-8")
TIMEOUT = 90.0

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    # F-SYSMOD fix (matches every other page test file in this suite): one-line fallback
    # so `conftest` stays importable even if this file is ever run standalone.
    sys.path.insert(0, str(_TESTS_DIR))
from conftest import restore_lib, swap_lib_to_streamlit  # centralized guard, see conftest.py

_saved_lib_modules: dict = {}


def setup_module(_module) -> None:
    global _saved_lib_modules
    _saved_lib_modules = swap_lib_to_streamlit()


def teardown_module(_module) -> None:
    restore_lib(_saved_lib_modules)


def _exc_values(at) -> list:
    return [e.value for e in at.exception]


def _neutralize_page_link(monkeypatch) -> None:
    """Pre-existing harness limitation, not caused by this stream (see
    tests/test_page7_col.py / tests/test_page_pf.py's own `_neutralize_page_link`
    docstring for the full story): lib.controls.sidebar()'s méthodo-expander calls
    st.page_link() unconditionally on every page's first render, which raises
    KeyError('url_pathname') under a direct AppTest.from_file() load -- this page's OWN
    drill-down st.page_link() call (Section 3, on a click) hits the exact same limitation.
    Neutralised so these tests exercise this page's own logic, not the harness gap."""
    import streamlit as st_mod
    monkeypatch.setattr(st_mod, "page_link", lambda *a, **k: None)


# ============================================================================
# (a) hover grammar -- every hovertemplate on the page is the bare grammar constant
# ============================================================================

HOVERTEMPLATE_RE = re.compile(r"hovertemplate\s*=\s*([^\n,\)]+)")


def test_every_hovertemplate_on_the_page_is_the_bare_grammar_constant():
    matches = HOVERTEMPLATE_RE.findall(PAGE_SRC)
    assert matches, "expected at least one hovertemplate= on the page"
    assert len(matches) == 4, matches  # below-floor, above-floor, site-share, isite-share
    for m in matches:
        assert m.strip().rstrip(",") in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE"), m

    # vacuity: a literal format-spec hovertemplate must be caught by the SAME regex
    bad_src = 'fig.update_traces(hovertemplate="<b>%{customdata[0]:.1%}</b><extra></extra>")\n'
    bad = HOVERTEMPLATE_RE.findall(bad_src)
    assert bad and bad[0].strip() not in ("hv.HOVERTEMPLATE", "HOVERTEMPLATE")


# ============================================================================
# (b) hover_lines well-formed for every (chart_key, mode) on this page
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


@pytest.mark.parametrize("chart_key,mode", [
    ("isite_ratio_dots", "log"), ("isite_ratio_dots", "lineaire"),
    ("isite_consortium_dumbbell", "default"),
])
def test_hover_lines_wellformed_for_every_page7_chart_mode(chart_key, mode):
    from lib import copy_fr
    from lib import hover as hv
    labels = copy_fr.HOVER_LABELS[chart_key][mode]
    assert len(labels) <= 8, (chart_key, mode)
    values = ["Entité X"] + [f"valeur {i}" for i in range(1, len(labels))]
    _assert_hover_wellformed(hv.hover_lines(list(zip(labels, values))))

    # a false `when` withholds every non-entity line -> still wellformed (entity only)
    withheld = ["Entité X"] + [None] * (len(labels) - 1)
    hover_withheld = hv.hover_lines(list(zip(labels, withheld)))
    _assert_hover_wellformed(hover_withheld)
    assert hover_withheld == "<b>Entité X</b>"

    # vacuity: a malformed line (label present, value glued with no "<b>...</b> : ")
    # must be CAUGHT by _assert_hover_wellformed
    with pytest.raises(AssertionError):
        _assert_hover_wellformed("<b>Entité X</b><br>libellé sans mise en forme : 3")


def test_isite_ratio_dots_labels_match_registry_order_both_modes():
    """The registry (`docs/tooltip_spec.yaml` L821-836) declares 6 lines in a fixed
    order for BOTH modes, identical between them -- source of truth is HOVER_LABELS,
    equality-checked against the yaml elsewhere (test_hover_spec.py); this pin only
    guards that this page's TWO modes stay in sync with each other."""
    from lib import copy_fr
    log_labels = list(copy_fr.HOVER_LABELS["isite_ratio_dots"]["log"])
    lin_labels = list(copy_fr.HOVER_LABELS["isite_ratio_dots"]["lineaire"])
    assert log_labels == lin_labels
    assert len(log_labels) == 6

    # vacuity
    assert log_labels != lin_labels + ["extra"]


# ============================================================================
# (c) reading lines -- one call site per chart key, "Comment lire" fully retired
# ============================================================================

PAGE7_CHART_KEYS = ["isite_ratio_dots", "isite_consortium_dumbbell"]


def test_reading_line_called_once_per_chart_key():
    for key in PAGE7_CHART_KEYS:
        assert PAGE_SRC.count(f'reading_line("{key}"') == 1, key
    assert PAGE_SRC.count("reading_line(") == len(PAGE7_CHART_KEYS)

    # vacuity: a page missing a chart's reading_line call must be caught by the same check
    stripped = PAGE_SRC.replace('reading_line("isite_ratio_dots"', "pass  # removed", 1)
    assert stripped.count('reading_line("isite_ratio_dots"') == 0


def test_comment_lire_paragraph_is_fully_retired():
    assert "Comment lire" not in PAGE_SRC

    # vacuity
    assert "Comment lire" in PAGE_SRC + "Comment lire ce graphique."


# ============================================================================
# (d) axes/colours -- no percent tickformat literal, zero hex literal in the page
# ============================================================================

def test_no_percent_tickformat_on_the_page():
    assert "tickformat=" not in PAGE_SRC

    # vacuity
    assert "tickformat=" in PAGE_SRC + 'fig.update_xaxes(tickformat=".0%")'


def test_page_has_zero_hex_literal_offenders():
    from tests.test_page_hex_literals import hex_violations
    offenders = hex_violations(PAGE_SRC)
    assert offenders == [], offenders

    # vacuity: the SAME scanner catches a live literal
    assert hex_violations('marker_color="#0072B2"\n') != []


def test_page_has_zero_hover_tripwire_offenders():
    from tests.test_hover_tripwire import scan_source_for_violations
    offenders = scan_source_for_violations(PAGE_SRC)
    assert offenders == [], offenders

    # vacuity
    assert scan_source_for_violations('hovertemplate="%{y:.2f}<extra></extra>"\n') != []


# ============================================================================
# (e) form -- margin_left/wrap_label_px on both families, red dashed reference at x=1
#     for isite_ratio_dots (isite_consortium_dumbbell has NO reference, per addendum
#     item 4 -- a paired-dot/dumbbell chart, absent from the yaml's own entry too)
# ============================================================================

def test_both_chart_families_use_margin_left_and_wrap_label_px():
    assert 'C.margin_left("champ")' in PAGE_SRC
    assert 'C.margin_left("partenaire")' in PAGE_SRC
    assert 'C.wrap_label_px(v, "champ")' in PAGE_SRC
    assert 'C.wrap_label_px(m, "partenaire")' in PAGE_SRC

    # vacuity
    stripped = PAGE_SRC.replace('C.margin_left("champ")', "10", 1)
    assert 'C.margin_left("champ")' not in stripped


def test_ratio_reference_vline_is_red_dashed_at_one_via_tokens():
    """Source-level mechanism pin (AppTest cannot introspect a rendered figure's own
    shapes -- same documented limitation as test_page_pd.py's own axis-type test):
    the parity reference line must use the token trio, never a hardcoded colour/dash."""
    assert "fig_ratio.add_vline(x=1, line_dash=C.REFERENCE_DASH, line_color=H.REFERENCE_RED" in PAGE_SRC
    assert 'fig_ratio.add_vline(x=1, line_dash="dash"' not in PAGE_SRC
    assert "#5A5F66" not in PAGE_SRC

    # vacuity
    stripped = PAGE_SRC.replace(
        "fig_ratio.add_vline(x=1, line_dash=C.REFERENCE_DASH, line_color=H.REFERENCE_RED",
        'fig_ratio.add_vline(x=1, line_dash="dot", line_color="#123456"', 1,
    )
    assert "fig_ratio.add_vline(x=1, line_dash=C.REFERENCE_DASH, line_color=H.REFERENCE_RED" not in stripped


def test_isite_consortium_dumbbell_has_no_reference_line():
    """Addendum item 4: paired-dot charts carry NO référence line -- follow the yaml
    (isite_consortium_dumbbell has no reference entry), not a generic B2 assumption."""
    dumbbell_block = PAGE_SRC[PAGE_SRC.index("fig_dumb = go.Figure()"):PAGE_SRC.index('reading_line("isite_consortium_dumbbell")')]
    assert "add_vline" not in dumbbell_block
    assert "add_hline" not in dumbbell_block

    # vacuity
    assert "add_vline" in dumbbell_block + "fig_dumb.add_vline(x=1)"


# ============================================================================
# (f) page-specific (B7): on_select="rerun" preserved + the drill handler is driven
#     by the seeded selection state (AppTest), never by customdata
# ============================================================================

def test_on_select_rerun_kwarg_present_on_the_ratio_chart():
    assert 'fig_ratio, use_container_width=True, on_select="rerun",' in PAGE_SRC
    assert 'key="dot_ratio_chart"' in PAGE_SRC

    # vacuity
    stripped = PAGE_SRC.replace('on_select="rerun"', 'on_select="ignore"', 1)
    assert 'on_select="rerun"' not in stripped


def test_seeding_the_dot_ratio_chart_selection_changes_the_drill_output(monkeypatch):
    """The ONE app-wide chart with a live selection event (B7). The handler reads
    `point["y"]` (the categorical field-name string bound to the trace's own y-array),
    never `customdata` -- confirmed by probing both paths: seeding session_state under
    the widget's own `key` drives `_dot_event`/`_sel_points`/`_clicked_field` exactly as
    a real frontend click would, with zero dependency on what customdata now holds
    (the pre-formatted hover string, post pass-7b)."""
    _neutralize_page_link(monkeypatch)
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PAGES_DIR / PAGE))
    at.session_state["dot_ratio_chart"] = {"selection": {"points": [{"y": "Chemistry"}]}}
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)
    blob = "\n".join(m.value for m in at.markdown) + "\n" + "\n".join(c.value for c in at.caption)
    assert "Sélectionné" in blob and "Chemistry" in blob

    # vacuity: an UNSEEDED baseline run must NOT show the drill caption
    at_baseline = AppTest.from_file(str(PAGES_DIR / PAGE))
    at_baseline.run(timeout=TIMEOUT)
    assert not at_baseline.exception, _exc_values(at_baseline)
    blob_baseline = "\n".join(m.value for m in at_baseline.markdown) + "\n" + "\n".join(
        c.value for c in at_baseline.caption
    )
    assert "Sélectionné" not in blob_baseline


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
