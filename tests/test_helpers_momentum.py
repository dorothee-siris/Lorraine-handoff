# tests/test_helpers_momentum.py
"""
Pass-6 re-open pins for Streamlit/lib/helpers.py's momentum formatter
(VIZ_SPEC_pass6 S8) -- manager-requested generalisation: P-EX/P-PF need the
SAME formatter at the taxon/topic grain (topics_zero_fill/subfields_zero_fill:
mom_class/mom_p_value/mom_w1_share/mom_w2_share, no mom_category/mom_count_arrow)
that `momentum_display()` was originally built only for the partner grain
(ptn_summary + ptn_mom_facts) -- the pass-5 post-mortem's "F27 drift class"
(two pages independently writing the same formatter). `momentum_display_values()`
is the grain-agnostic core; `momentum_display(row, facts)` is a thin,
SIGNATURE-UNCHANGED wrapper over it (page 9 already calls it positionally).

Also pins the `MOMENTUM_METHOD_HELP_FR` window-label fix (P-ZP flag): the
years used to be a hardcoded, and WRONG, literal ("2019-2021"); they now read
`ptn_mom_facts.mom_w1_label`/`mom_w2_label` (S-DAT-shipped) at import time.

Pass-6 fix round (S-LENS D4, 3rd strike on this same sentence): the
recentring median right next to those window labels was ALSO a hardcoded
literal ("médiane 1,06") -- now read from `ptn_mom_facts.recentring_median`
in the same `_momentum_window_labels()` call, which returns a 3-tuple
(w1, w2, median_str).

    python -m pytest tests/test_helpers_momentum.py -q

Namespace note: same `_import_streamlit_lib` swap-trick as tests/test_ranked.py.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
DEPLOY_DIR = STREAMLIT_DIR / "data"


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


(helpers,) = _import_streamlit_lib("helpers")


# ============================================================================
# MOMENTUM_METHOD_HELP_FR -- window labels computed, no year literal
# ============================================================================

def test_momentum_help_text_contains_no_hardcoded_2019_2021():
    """The literal this replaces was itself WRONG (real windows are
    2019-2020 vs 2022-2023, 2021 is a buffer year) -- pin that the old wrong
    literal cannot silently return."""
    assert "2019-2021" not in helpers.MOMENTUM_METHOD_HELP_FR
    assert "2019–2021" not in helpers.MOMENTUM_METHOD_HELP_FR


def test_momentum_help_text_matches_ptn_mom_facts_labels():
    path = DEPLOY_DIR / "ptn_mom_facts.parquet"
    if not path.exists():
        pytest.skip("ptn_mom_facts.parquet not deployed yet")
    facts = pd.read_parquet(path, columns=["conf_state", "mom_w1_label", "mom_w2_label"])
    row = facts.loc[facts["conf_state"] == "all"].iloc[0]
    w1, w2 = str(row["mom_w1_label"]), str(row["mom_w2_label"])
    assert w1 in helpers.MOMENTUM_METHOD_HELP_FR
    assert w2 in helpers.MOMENTUM_METHOD_HELP_FR
    assert f"({w1} vs {w2})" in helpers.MOMENTUM_METHOD_HELP_FR


def test_momentum_help_text_contains_no_hardcoded_median_1_06():
    """S-LENS D4: the median beside the window labels was ALSO a hardcoded
    literal ("médiane 1,06") -- pin that a byte-identical-today value cannot
    silently mean it is still a literal. Computed value must appear instead,
    read straight from the deployed table (never assumed)."""
    path = DEPLOY_DIR / "ptn_mom_facts.parquet"
    if not path.exists():
        pytest.skip("ptn_mom_facts.parquet not deployed yet")
    facts = pd.read_parquet(path, columns=["conf_state", "recentring_median"])
    row = facts.loc[facts["conf_state"] == "all"].iloc[0]
    median_str = f"{float(row['recentring_median']):.2f}".replace(".", ",")
    assert f"médiane {median_str}" in helpers.MOMENTUM_METHOD_HELP_FR


def test_momentum_window_labels_fall_back_gracefully_on_bad_path(monkeypatch):
    """Never a crash, never a guessed year/median, if the table is unreadable."""
    monkeypatch.setattr(helpers, "DATA_DIR", Path("Z:/does/not/exist"))
    assert helpers._momentum_window_labels() == ("?", "?", "?")


# ============================================================================
# momentum_display_values() -- grain-agnostic core
# ============================================================================

MEDIAN = 1.060434


def test_values_up_case_matches_wrapper_case():
    """Same inputs, same output whether reached via momentum_display_values()
    directly or via the momentum_display(row, facts) wrapper."""
    direct = helpers.momentum_display_values(
        category="up", w1_share=0.0035, w2_share=0.0068,
        recentring_median=MEDIAN, count_arrow="395->766",
    )
    via_wrapper = helpers.momentum_display(
        {"mom_category": "up", "mom_w1_share": 0.0035, "mom_w2_share": 0.0068,
         "mom_count_arrow": "395->766"},
        {"recentring_median": MEDIAN},
    )
    assert direct == via_wrapper
    assert direct[0] == "↗ +83\u202f%"
    assert direct[1] == helpers.MOMENTUM_UP_COLOR
    assert direct[2] == "↗"


def test_values_taxon_grain_call_shape_no_category_no_count_arrow():
    """The exact taxon-grain shape (topics_zero_fill): mom_class, mom_w1_share,
    mom_w2_share -- no mom_category, no mom_count_arrow column at all (passed
    as the default None, never crashes, guard simply never fires)."""
    text, color, glyph = helpers.momentum_display_values(
        category="ns", w1_share=0.000883, w2_share=0.000525, recentring_median=MEDIAN,
    )
    assert text == "non significatif"
    assert color == helpers.MOMENTUM_NEUTRAL_COLOR
    assert glyph is None


def test_values_taxon_grain_up_case_without_count_arrow_still_computes_delta():
    text, color, glyph = helpers.momentum_display_values(
        category="up", w1_share=0.0035, w2_share=0.0068, recentring_median=MEDIAN,
    )
    assert text == "↗ +83\u202f%"
    assert color == helpers.MOMENTUM_UP_COLOR
    assert glyph == "↗"


def test_values_mom_class_vocabulary_never_has_new_or_dormant():
    """mom_class (taxon grain) is a subset of mom_category -- up/down/stable/ns
    only, no new/dormant screens. Still handled identically via the shared
    glyph table."""
    down = helpers.momentum_display_values(
        category="down", w1_share=0.01, w2_share=0.003, recentring_median=MEDIAN,
    )
    assert down[0] == "↘ −72\u202f%"
    assert down[1] == helpers.MOMENTUM_DOWN_COLOR


def test_values_null_category_returns_dash_never_crashes():
    assert helpers.momentum_display_values(
        category=None, w1_share=None, w2_share=None, recentring_median=MEDIAN,
    ) == ("—", helpers.MOMENTUM_NEUTRAL_COLOR, None)


def test_values_recentring_median_is_optional_with_default_none():
    import inspect
    sig = inspect.signature(helpers.momentum_display_values)
    assert sig.parameters["recentring_median"].default is None


def test_values_thematic_grain_no_median_omits_quantified_clause():
    """P-PF re-open: the thematic grain (topics_zero_fill/subfields_zero_fill)
    has NO persisted recentring_median at all. Rather than fail or fabricate
    (e.g. defaulting median=1, which would silently IMPLY the same corpus-
    drift correction as the partner grain), the quantified clause is OMITTED
    -- only the glyph renders, with the category's real status colour."""
    text, color, glyph = helpers.momentum_display_values(
        category="up", w1_share=0.0035, w2_share=0.0068,
    )
    assert text == "↗"
    assert color == helpers.MOMENTUM_UP_COLOR
    assert glyph == "↗"
    assert "%" not in text


def test_values_thematic_grain_down_and_stable_also_omit_clause():
    down = helpers.momentum_display_values(category="down", w1_share=0.01, w2_share=0.003)
    assert down == ("↘", helpers.MOMENTUM_DOWN_COLOR, "↘")

    stable = helpers.momentum_display_values(category="stable", w1_share=0.01, w2_share=0.0102)
    assert stable == ("→", helpers.MOMENTUM_STABLE_COLOR, "→")


def test_values_explicit_none_median_same_as_default():
    default = helpers.momentum_display_values(category="up", w1_share=0.0035, w2_share=0.0068)
    explicit = helpers.momentum_display_values(
        category="up", w1_share=0.0035, w2_share=0.0068, recentring_median=None,
    )
    assert default == explicit


def test_values_nan_median_also_omits_clause_not_just_none():
    import numpy as np
    text, color, glyph = helpers.momentum_display_values(
        category="up", w1_share=0.0035, w2_share=0.0068, recentring_median=float("nan"),
    )
    assert text == "↗"
    assert color == helpers.MOMENTUM_UP_COLOR


def test_values_missing_median_does_not_mask_the_w1_guard():
    """The tiny-baseline guard still takes priority over the missing-median
    omission -- a guarded row shows 'base trop faible', not the bare glyph."""
    text, color, glyph = helpers.momentum_display_values(
        category="up", w1_share=0.0001, w2_share=0.002, count_arrow="1->20",
    )
    assert text == "↗ base trop faible"
    assert color == helpers.MOMENTUM_NEUTRAL_COLOR


def test_values_ns_new_dormant_null_unaffected_by_missing_median():
    """Cases that never reach the delta computation are identical whether or
    not a median is supplied."""
    assert helpers.momentum_display_values(category="ns", w1_share=1, w2_share=1)[0] == "non significatif"
    assert helpers.momentum_display_values(category="new", w1_share=None, w2_share=None)[0] == "nouveau partenaire"
    assert helpers.momentum_display_values(category=None, w1_share=None, w2_share=None)[0] == "—"


def test_wrapper_facts_without_recentring_median_now_shows_bare_glyph():
    """Documents the one behaviour change this re-open causes at the wrapper
    level: page 9's own defensive `mf_row if mf_row is not None else {}`
    fallback used to render '-' when facts was empty; it now renders the bare
    glyph instead, since the core formatter treats a missing median as
    'omit the clause', not 'fail'. mf_row is never actually {} in production
    (ptn_mom_facts always has exactly one row per conf_state), so this only
    changes a defensive edge case, never a real render."""
    text, color, glyph = helpers.momentum_display(
        {"mom_category": "up", "mom_w1_share": 0.0035, "mom_w2_share": 0.0068}, {},
    )
    assert text == "↗"
    assert glyph == "↗"


def test_values_w1_guard_fires_only_when_count_arrow_is_supplied():
    """The tiny-baseline guard needs a count_arrow to check -- absent (taxon
    grain), it never fires even on an extreme ratio; present and < 5, it
    does (partner grain)."""
    no_guard = helpers.momentum_display_values(
        category="up", w1_share=0.0001, w2_share=0.002, recentring_median=MEDIAN,
    )
    assert "base trop faible" not in no_guard[0]

    guarded = helpers.momentum_display_values(
        category="up", w1_share=0.0001, w2_share=0.002, recentring_median=MEDIAN,
        count_arrow="1->20",
    )
    assert guarded[0] == "↗ base trop faible"
    assert guarded[1] == helpers.MOMENTUM_NEUTRAL_COLOR
    assert guarded[2] == "↗"


# ============================================================================
# momentum_display() -- partner-grain wrapper, unchanged signature/behaviour
# ============================================================================

def test_wrapper_falls_back_to_mom_class_when_mom_category_absent():
    """Defensive: a caller handing this the narrower taxon-shaped row through
    the OLD wrapper (rather than calling momentum_display_values() directly)
    still gets a correct read via mom_class."""
    text, color, glyph = helpers.momentum_display(
        {"mom_class": "stable", "mom_w1_share": 0.01, "mom_w2_share": 0.0102},
        {"recentring_median": MEDIAN},
    )
    assert glyph == "→"
    assert color == helpers.MOMENTUM_STABLE_COLOR


def test_wrapper_new_dormant_ns_null_unchanged():
    facts = {"recentring_median": MEDIAN}
    assert helpers.momentum_display({"mom_category": "new"}, facts)[0] == "nouveau partenaire"
    assert helpers.momentum_display({"mom_category": "dormant"}, facts)[0] == "partenaire dormant"
    assert helpers.momentum_display({"mom_category": "ns"}, facts)[0] == "non significatif"
    assert helpers.momentum_display({"mom_category": None}, facts)[0] == "—"


def test_wrapper_accepts_pandas_series():
    row = pd.Series({"mom_category": "down", "mom_w1_share": 0.01, "mom_w2_share": 0.003,
                      "mom_count_arrow": "200->60"})
    facts = pd.Series({"recentring_median": MEDIAN})
    text, color, glyph = helpers.momentum_display(row, facts)
    assert text == "↘ −72\u202f%"
    assert color == helpers.MOMENTUM_DOWN_COLOR
    assert glyph == "↘"
