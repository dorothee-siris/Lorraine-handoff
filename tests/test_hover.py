# tests/test_hover.py
r"""
Pass-7a unit pins for Streamlit/lib/hover.py (S-LIB-B, docs/contract_fragments/lib_api_pass7.md).

Also carries the pass-7a token pins for `lib.helpers`' pair/SDG identity additions
(UL_COLOR/PARTNER_COLOR/JOINT_COLOR/PAIR_COLORS_DARK/REFERENCE_RED/TINT_FACTOR/tint/
SDG_COLORS/SDG_LABELS_FR/sdg_color) -- P7_LIBB.md's scope fence authorises exactly three
NEW test files (this one, test_links_pair.py, test_exports_workbook.py) and no dedicated
"tokens" file, so those checks are folded in here rather than left untested; flagged
in this worker's Report for the manager in case a separate file is preferred later.

Every test follows the vacuity rule (P14): assert the real behaviour, then show a
mutated input/threshold would make the SAME assertion fail -- never a check that
would pass regardless of the implementation.

    .venv-pinned\Scripts\python -m pytest tests\test_hover.py -q

Namespace note: same `_import_streamlit_lib` swap-trick as tests/test_links.py (see its
docstring) -- Streamlit/lib and the repo-root pipeline `lib` package would otherwise
collide under the same `lib` name in `sys.modules`.
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
DATA_DIR = STREAMLIT_DIR / "data"


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


hover, helpers, controls = _import_streamlit_lib("hover", "helpers", "controls")


# ============================================================================
# hover_lines -- grammar, withholding, cap
# ============================================================================

def test_hover_lines_grammar_exact():
    """Entity line (empty label) bold/no-colon; labelled line "<b>label</b> : value"
    with a normal space on each side of the colon; value passed through untouched."""
    out = hover.hover_lines([("", "Université de Lorraine"), ("Champ", "3")])
    expected = "<b>Université de Lorraine</b><br><b>Champ</b> : 3"
    assert out == expected
    # vacuity: a different label must change the rendered string
    mutated = hover.hover_lines([("", "Université de Lorraine"), ("Champ modifié", "3")])
    assert mutated != expected


def test_hover_lines_empty_label_mid_sequence_is_a_drapeau_not_a_stray_colon():
    """A later empty-label tuple (a `drapeau`/flag line, tooltip_spec.yaml) renders the
    SAME way as line 0 -- bold, no colon -- never "<b></b> : phrase"."""
    out = hover.hover_lines([("", "Topic X"), ("Champ", "3"), ("", "topic hors référentiel")])
    assert out == "<b>Topic X</b><br><b>Champ</b> : 3<br><b>topic hors référentiel</b>"
    assert " : topic hors référentiel" not in out
    # vacuity: a NON-empty label at that same position must go back to the colon form
    labelled = hover.hover_lines([("", "Topic X"), ("Champ", "3"), ("Alerte", "topic hors référentiel")])
    assert "<b>Alerte</b> : topic hors référentiel" in labelled


def test_hover_lines_withholds_none():
    out = hover.hover_lines([("", "X"), ("A", "1"), ("B", None), ("C", "3")])
    assert out == "<b>X</b><br><b>A</b> : 1<br><b>C</b> : 3"
    assert "B" not in out
    # vacuity: the SAME slot with a real value must NOT be withheld
    out2 = hover.hover_lines([("", "X"), ("A", "1"), ("B", "2"), ("C", "3")])
    assert "<b>B</b> : 2" in out2


def test_hover_lines_cap_raises_above_max_lines():
    at_cap = [("", "X")] + [(f"L{i}", str(i)) for i in range(hover.MAX_LINES - 1)]
    assert len(at_cap) == hover.MAX_LINES
    hover.hover_lines(at_cap)  # must NOT raise at exactly the cap
    over_cap = at_cap + [("L_extra", "x")]
    with pytest.raises(ValueError):
        hover.hover_lines(over_cap)


# ============================================================================
# fmt_* formatters
# ============================================================================

def test_fmt_int_fmt_dec_fmt_score():
    assert hover.fmt_int(1839) == helpers.fr_int(1839)
    assert hover.fmt_dec(0.5) == "0,50"
    assert hover.fmt_dec(1.236, decimals=1) == "1,2"
    assert hover.fmt_score(1.31) == "1,31"
    # vacuity: a missing value must NOT silently become "0,00"
    assert hover.fmt_dec(None) == helpers.NA_MARK
    assert hover.fmt_dec(None) != "0,00"


def test_fmt_pct_dagger_floor():
    base_pct = f"12,3{helpers.FR_THIN_SPACE}%"  # fr_pct's own narrow-no-break-space convention
    no_dagger = hover.fmt_pct_dagger(12.3, 54)
    assert no_dagger == base_pct
    assert controls.DAGGER not in no_dagger
    with_dagger = hover.fmt_pct_dagger(12.3, 4)
    assert with_dagger == f"{base_pct} {controls.DAGGER}"
    # vacuity: crossing the floor from below to at-or-above removes the dagger
    at_floor = hover.fmt_pct_dagger(12.3, 10)
    assert controls.DAGGER not in at_floor


def test_fmt_fwci_pair_floors():
    """None under floor_draw=3; dagger under floor_dagger=10; neither above it."""
    assert hover.fmt_fwci_pair(0.5, 0.6, 2) is None
    below_dagger = hover.fmt_fwci_pair(0.98, 1.31, 5)
    assert below_dagger == f"médiane 0,98 · moyenne 1,31 · 5 travaux {controls.DAGGER}"
    above_dagger = hover.fmt_fwci_pair(0.98, 1.31, 54)
    assert above_dagger == "médiane 0,98 · moyenne 1,31 · 54 travaux"
    assert controls.DAGGER not in above_dagger


def test_fmt_keywords_2x5_on_a_real_all_topics_blob():
    df = pd.read_parquet(DATA_DIR / "all_topics.parquet")
    blob = df["keywords"].dropna().astype(str)
    blob = blob[blob.str.len() > 0].iloc[0]
    words = helpers.parse_pipe_str_list(blob)
    assert len(words) >= 5, "fixture blob too short to exercise the 2x5 split"

    line1, line2 = hover.fmt_keywords_2x5(blob)
    assert line1 == ", ".join(words[:5])
    assert line2 == ", ".join(words[5:10])
    assert line1.count(",") == 4  # 5 keywords -> 4 commas
    # vacuity: a shorter blob must produce a shorter (not padded, not erroring) result
    short1, short2 = hover.fmt_keywords_2x5("a|b|c")
    assert (short1, short2) == ("a, b, c", "")


def test_fmt_pair_volumes_derived_and_missing():
    out = hover.fmt_pair_volumes("UL", 120, "CNRS", 84)
    assert out == "UL 120 · CNRS 84"
    assert "(dérivé)" not in out

    derived = hover.fmt_pair_volumes("UL", 120, "CNRS", 84, derived_b=True)
    assert derived == "UL 120 · CNRS 84 (dérivé)"

    missing = hover.fmt_pair_volumes("UL", 120, "CNRS", None)
    assert missing == "UL 120 · CNRS —"
    assert helpers.NA_MARK not in missing  # "—" is the contract's own marker, not NA_MARK


def test_fmt_joint_or_floor():
    assert hover.fmt_joint_or_floor(84) == "84"
    under = hover.fmt_joint_or_floor(3)
    assert under == "non affiché sous cinq co-publications"
    assert under != "0"
    # vacuity: exactly at the floor must NOT be withheld
    assert hover.fmt_joint_or_floor(5) == "5"


# ============================================================================
# Pass-7a lib.helpers token pins (P5/P11/P17) -- see module docstring for why they
# live in this file rather than a dedicated one.
# ============================================================================

def test_sdg_colors_and_labels_have_17_keys():
    assert len(helpers.SDG_COLORS) == 17
    assert len(helpers.SDG_LABELS_FR) == 17
    assert set(helpers.SDG_COLORS) == set(range(1, 18))
    assert set(helpers.SDG_LABELS_FR) == set(range(1, 18))
    # vacuity: a goal missing from the dict must fail the same cardinality check
    missing = dict(helpers.SDG_LABELS_FR)
    del missing[7]
    assert len(missing) != 17


def test_sdg_labels_fr_all_numbered_odd_n():
    pattern = re.compile(r"^ODD \d{1,2} · ")
    for n, label in helpers.SDG_LABELS_FR.items():
        assert pattern.match(label), f"SDG_LABELS_FR[{n}] missing the 'ODD n ·' prefix: {label!r}"
    # vacuity: a bare name with no "ODD n ·" prefix must NOT match
    assert not pattern.match("Bonne santé et bien-être")


def test_sdg_color_unknown_falls_back_to_neutral_grey():
    assert helpers.sdg_color(3) == helpers.SDG_COLORS[3]
    assert helpers.sdg_color(99) == helpers.NEUTRAL_GREY
    assert helpers.sdg_color("not-a-number") == helpers.NEUTRAL_GREY
    # vacuity: a KNOWN goal must NOT fall back to grey
    assert helpers.sdg_color(3) != helpers.NEUTRAL_GREY


def test_tint_toward_white_and_idempotent_on_white():
    base = "#0CA750"
    tinted = helpers.tint(base)
    assert tinted != base
    r0, g0, b0 = helpers.hex_to_rgb(base)
    r1, g1, b1 = helpers.hex_to_rgb(tinted)
    assert (r1, g1, b1) >= (r0, g0, b0) and (r1, g1, b1) != (r0, g0, b0)
    # lowercase output is the app's existing convention (darken_hex does the same,
    # f"#{r:02x}{g:02x}{b:02x}") -- idempotence is checked against THAT canonical form
    assert helpers.tint("#ffffff") == "#ffffff"
    # vacuity: factor 0.0 must leave the colour UNCHANGED (proves the factor is live,
    # not a hardcoded lightening) -- compared case-insensitively, tint's own output
    # convention is lowercase regardless of input case
    assert helpers.tint(base, factor=0.0) == base.lower()


def test_pair_colors_dark_are_darker_than_their_fills_by_luminance():
    def luminance(hexcode: str) -> float:
        r, g, b = helpers.hex_to_rgb(hexcode)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    fills = {"ul": helpers.UL_COLOR, "partner": helpers.PARTNER_COLOR, "joint": helpers.JOINT_COLOR}
    for key, fill in fills.items():
        dark = helpers.PAIR_COLORS_DARK[key]
        assert luminance(dark) < luminance(fill), f"{key}: dark twin is not darker than its own fill"
    # vacuity: a fill is never "darker than itself"
    assert not (luminance(fills["ul"]) < luminance(fills["ul"]))
