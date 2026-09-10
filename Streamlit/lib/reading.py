# Streamlit/lib/reading.py
"""
Pass-7a reading-line renderer -- authority: docs/contract_fragments/lib_api_pass7.md,
lib/copy_fr.py section 1 (READING).

`READING[chart_key][mode or "default"]` holds the "how to read this" sentence(s) the
Studio places between a chart's own controls and `st.plotly_chart` (VIZ_SPEC.md) --
never a conclusion, never a literal data value or year (P6-R2, `copy_fr`'s own
docstring). This module only looks the string up, fills its `{placeholder}` slots
(declared per key in `copy_fr.READING_PLACEHOLDERS`) and renders it.

A missing `chart_key`/`mode` combination raises KeyError -- deliberately not caught or
defaulted here: a chart-spec/copy_fr drift is a bug to surface at the call site
(and at test time, by whatever enumerates `docs/contract_fragments/chart_keys_pass7.md`
against `copy_fr.READING`), never a silently blank caption.
"""
from __future__ import annotations

import streamlit as st

from lib import copy_fr


def reading_text(chart_key: str, mode: str | None = None, **fills) -> str:
    """`copy_fr.READING[chart_key][mode or "default"].format(**fills)`. KeyError
    propagates when the chart key or mode is not declared, or when `fills` is missing
    a placeholder the template needs (str.format's own KeyError) -- never swallowed."""
    template = copy_fr.READING[chart_key][mode or "default"]
    return template.format(**fills)


def reading_line(chart_key: str, mode: str | None = None, **fills) -> None:
    """Render `reading_text(...)` as the caption-styled line a chart's controls and
    its `st.plotly_chart` sit around (VIZ_SPEC.md) -- `st.caption` is the Studio's
    own styling choice here, nothing more elaborate needed."""
    st.caption(reading_text(chart_key, mode, **fills))
