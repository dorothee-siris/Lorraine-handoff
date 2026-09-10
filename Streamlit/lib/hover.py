# Streamlit/lib/hover.py
"""
Pass-7a shared hover-string builder -- authority: docs/contract_fragments/lib_api_pass7.md,
docs/tooltip_spec.yaml.

Pages build the frame's `hover` column by calling `hover_lines()` on a list of
`(label, value)` tuples: `label` comes from `lib.copy_fr.HOVER_LABELS[chart_key][mode]`
(source of truth, asserted equal to `docs/tooltip_spec.yaml` by tests/test_hover_spec.py --
not this module's job), and `value` is either `None` (the yaml's `when:` condition was
false -- withhold the line) or an already-formatted string built with one of the `fmt_*`
helpers below. Builders then read the resulting string through
`hovertemplate = HOVERTEMPLATE` on `customdata` -- NEVER a format specifier in the
template itself (every chart is pre-formatted server-side, once, in the page).

This module is PURE (no Streamlit import, no `st.*` call) -- it only assembles strings.

Rendering rule (docs/tooltip_spec.yaml "Regles dures"):
  * a line whose value is None is withheld entirely -- never a bare label, never a
    literal "None" (P6-R2);
  * a line with an EMPTY label renders bold, value only, no colon -- this is line 0
    (the entity the mark represents) and, later in the sequence, any `drapeau` (flag)
    line: a fixed sentence with no value of its own. The yaml allows an empty label in
    exactly those two places, and both read the same way: bold text, nothing else;
  * every other line renders "<b>{label}</b> : {value}" -- one normal (non-narrow)
    space on each side of the colon, per FR typographic convention here, and the value
    passed through UNTOUCHED (already formatted by the caller);
  * 8 lines maximum (MAX_LINES). A topic's keywords occupy 2 of those by the yaml's own
    convention even though they travel here as ONE (label, value) tuple -- see
    `fmt_keywords_2x5`; that accounting is the chart spec's concern, not this
    function's -- `hover_lines` itself simply caps the number of TUPLES it is given.

`fmt_*` formatters turn a raw data value into the display string a hover line's `value`
slot takes. They never touch `HOVER_LABELS` strings (that dict IS the `label` half
already) and never format a whole line -- only the value.
"""
from __future__ import annotations

from typing import Sequence

import pandas as pd

from lib import copy_fr
from lib.controls import DAGGER
from lib.helpers import NA_MARK, fr_int, fr_pct, parse_pipe_str_list

HOVERTEMPLATE = "%{customdata}<extra></extra>"
MAX_LINES = 8


def _is_na(val) -> bool:
    """Scalar missing-value check (mirrors lib.helpers.fr_int/fr_pct's own convention);
    guarded so a non-scalar accidentally passed here degrades to "not missing" rather
    than raising out of a formatter."""
    try:
        return val is None or bool(pd.isna(val))
    except (TypeError, ValueError):
        return False


# ============================================================================
# HOVER LINE ASSEMBLY
# ============================================================================

def hover_lines(lines: Sequence[tuple[str, str | None]]) -> str:
    """
    Assemble the pre-formatted hover string a builder passes as `customdata`
    (`hovertemplate=HOVERTEMPLATE`). `lines` is the FULL per-mode candidate list
    (in the chart spec's declared order) -- a tuple whose value is None is
    withheld, never rendered as a bare label. Raises ValueError when handed
    more than MAX_LINES tuples (a static contract check: the chart spec never
    declares more than 8 for one mode, so this only bites a caller error).
    """
    if len(lines) > MAX_LINES:
        raise ValueError(f"hover_lines: {len(lines)} lines exceeds MAX_LINES={MAX_LINES}")
    rendered: list[str] = []
    for label, value in lines:
        if value is None:
            continue
        if label == "":
            rendered.append(f"<b>{value}</b>")
        else:
            rendered.append(f"<b>{label}</b> : {value}")
    return "<br>".join(rendered)


# ============================================================================
# VALUE FORMATTERS
# ============================================================================

def fmt_int(v) -> str:
    """Thousands-grouped FR integer -- lib.helpers.fr_int, re-exported so a page
    building a `lines` list only ever imports from lib.hover."""
    return fr_int(v)


def fmt_dec(v, decimals: int = 2) -> str:
    """FR decimal (comma separator); missing -> NA_MARK, same convention as fr_int/fr_pct."""
    if _is_na(v):
        return NA_MARK
    try:
        s = f"{float(v):.{decimals}f}"
    except (TypeError, ValueError):
        return NA_MARK
    return s.replace(".", ",")


def fmt_pct(v, decimals: int = 1) -> str:
    """FR percentage on the 0-100 scale -- lib.helpers.fr_pct."""
    return fr_pct(v, decimals)


def fmt_pct_dagger(v, n: int, floor: int = 10) -> str:
    """`fmt_pct(v)`, with `controls.DAGGER` appended (one space before it) when the
    denominator `n` is below `floor` (reliability floor, tooltip_spec.yaml pct_1d_dague)."""
    base = fmt_pct(v)
    if not _is_na(n) and n < floor:
        return f"{base} {DAGGER}"
    return base


def fmt_score(v) -> str:
    """2-decimal FR score (expansion, acceleration, frontiere, intensite relative)."""
    return fmt_dec(v, 2)


def fmt_fwci_pair(median, mean, n: int, *, floor_draw: int = 3, floor_dagger: int = 10) -> str | None:
    """
    "médiane 0,98 · moyenne 1,31 · 54 travaux" (tooltip_spec.yaml fwci_paire_2d).
    Appends DAGGER when `n < floor_dagger`; returns None (withhold the line --
    never drawn) when `n < floor_draw`.
    """
    if _is_na(n) or n < floor_draw:
        return None
    text = f"médiane {fmt_dec(median)} · moyenne {fmt_dec(mean)} · {fmt_int(n)} travaux"
    if n < floor_dagger:
        text = f"{text} {DAGGER}"
    return text


def fmt_keywords_2x5(keywords_blob: str) -> tuple[str, str]:
    """
    Two lines of (up to) five keywords each, from an `all_topics.keywords` blob.
    The blob is PIPE-separated on disk (verified against Streamlit/data/all_topics.parquet,
    e.g. "Agroecology|Food Sovereignty|..." -- reuses lib.helpers.parse_pipe_str_list, the
    app's existing blob parser); the DISPLAY convention (tooltip_spec.yaml mots_cles_2x5)
    joins each line's words with ", ". Fewer than 10 keywords -> the second line is
    shorter (or empty), never padded or an error.
    """
    words = parse_pipe_str_list(keywords_blob)
    return ", ".join(words[:5]), ", ".join(words[5:10])


def fmt_pair_volumes(name_a: str, vol_a, name_b: str, vol_b, *, derived_b: bool = False) -> str:
    """
    "UL 120 · CNRS 84" (tooltip_spec.yaml paire_volumes). A missing volume renders
    "—" (em dash -- NOT NA_MARK: this is a display convention specific to this line,
    per the contract). `derived_b` appends " (dérivé)" after the second name's volume.
    """
    a_str = "—" if _is_na(vol_a) else fmt_int(vol_a)
    b_str = "—" if _is_na(vol_b) else fmt_int(vol_b)
    suffix = " (dérivé)" if derived_b else ""
    return f"{name_a} {a_str} · {name_b} {b_str}{suffix}"


def fmt_joint_or_floor(n, floor: int = 5) -> str:
    """The joint count, or `copy_fr.CAPTIONS["JOINT_UNDER_FLOOR"]` when `n < floor`
    (tooltip_spec.yaml conjoint_ou_seuil -- NEVER a bare zero, which would say something
    else: an under-floor relation is withheld, not empty)."""
    if _is_na(n) or n < floor:
        return copy_fr.CAPTIONS["JOINT_UNDER_FLOOR"]
    return fmt_int(n)
