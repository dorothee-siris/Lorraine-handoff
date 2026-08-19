# lib/exports.py
"""
W5 shared export layer -- authority: docs/foundry/data_foundation.yaml rev 3.1
`export_layer` block + docs/indicator_plan_FINAL.md §6.4 + docs/studio/VIZ_SPEC.md §1.3.

Filename grammar (rev 3.1, verbatim):
    lorraine-explorer_<view>_<indicator>_<snapshot>_<conf>_<artifact>
        [_<subset>][_<entity>][_<node>].xlsx

`<conf>` in {all, noconf} and `<artifact>` in {full, filtered} -- these are the FILENAME
tokens, distinct from the pipeline's own `conf_state` column values ("all"/"no_conf"):
the underscore in "no_conf" cannot survive as a filename segment (underscore is the
segment separator), so the slug drops it. `state.conf`/`state.artifact` store the
filename token directly (see `_norm_conf`/`_norm_artifact` for the bool/legacy-string
inputs a page is likely to pass instead).

`<entity>` is kind-prefixed (p-<partner_id>, a-<author_id>, c-<country_code>,
l-<structure_key>) and `<node>` is level-prefixed (d-<domain>, f-<field>, sf-<subfield>,
t-<topic>) -- disjoint prefix alphabets by design, so `parse_filename` can tell them
apart unambiguously regardless of which optional segments are present. Entity/node VALUES
keep their original case (OpenAlex ids are case-sensitive, e.g. p-I157674565) -- only
free-text labels (view/indicator/subset) go through the lower-cased ascii-kebab `slug()`.
"""
from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from lib.controls import ARTIFACT_BANNER_TEXT_FR

# ============================================================================
# CONSTANTS
# ============================================================================

IMPACT_COL_RE = re.compile(r"fwci|pptop|impact|citation", re.IGNORECASE)

CONF_TOKENS = {"all", "noconf"}
ARTIFACT_TOKENS = {"full", "filtered"}
ENTITY_KINDS = {"p", "a", "c", "l"}   # partner, author, country, lab/structure
NODE_LEVELS = {"d", "f", "sf", "t"}   # domain, field, subfield, topic

METHOD_SHEET_NAME = "A lire — méthode"
DATA_SHEET_NAME = "Données"
WORKS_SHEET_NAME = "Publications"

# docs/foundry/data_foundation.yaml rev 3.1, export_layer.header_sheet.fields (order kept).
HEADER_FIELDS = [
    "method_one_liner", "snapshot_date", "active_filters", "conference_toggle_state",
    "artifact_toggle_state", "artifact_applied", "artifact_banner_text_if_on",
    "deferred_twin_columns", "perimeter_subset", "entity", "drill_node", "generation_date",
]


# ============================================================================
# STATE
# ============================================================================

@dataclass
class ExportState:
    """
    The small state bundle every export call needs (rev 3.1 export_layer).
    `conf`/`artifact` are normalised to the filename-slug tokens on
    construction, so building a filename and parsing one back agree on the
    same vocabulary. `filters`/`method`/`deferred_twins`/`artifact_applied`
    are header-sheet-only (round_trip_scope, tunnel #15b): they are stated
    there, never encoded in the filename.
    """
    snapshot: str
    conf: Any = "all"
    artifact: Any = "full"
    subset: str | None = None
    filters: Any = field(default_factory=dict)
    artifact_applied: bool = False
    deferred_twins: list = field(default_factory=list)
    method: str = ""

    def __post_init__(self) -> None:
        self.conf = _norm_conf(self.conf)
        self.artifact = _norm_artifact(self.artifact)


def _norm_conf(value: Any) -> str:
    if isinstance(value, bool):
        return "all" if value else "noconf"
    v = str(value).strip().lower().replace("_", "").replace("-", "")
    if v == "all":
        return "all"
    if v == "noconf":
        return "noconf"
    raise ValueError(f"conf must be a bool or in {sorted(CONF_TOKENS)} (incl. 'no_conf'); got {value!r}")


def _norm_artifact(value: Any) -> str:
    if isinstance(value, bool):
        return "filtered" if value else "full"
    v = str(value).strip().lower()
    if v in ("full", "off"):
        return "full"
    if v in ("filtered", "on"):
        return "filtered"
    raise ValueError(f"artifact must be a bool or in {sorted(ARTIFACT_TOKENS)}; got {value!r}")


def _as_state(state: Any) -> ExportState:
    """Accept an ExportState, a plain dict, or any object exposing the same attributes."""
    if isinstance(state, ExportState):
        return state
    fields_ = ExportState.__dataclass_fields__
    if isinstance(state, dict):
        return ExportState(**{k: v for k, v in state.items() if k in fields_})
    return ExportState(**{k: getattr(state, k) for k in fields_ if hasattr(state, k)})


# ============================================================================
# SLUGS / TOKENS
# ============================================================================

def slug(value: Any) -> str:
    """ascii-kebab a free-text label: 'Île-de-France name' -> 'ile-de-france-name'."""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text or "x"


def _safe_token(value: Any) -> str:
    """
    Filename-safe an identifier WITHOUT lower-casing it (OpenAlex ids and
    structure keys are case-sensitive: p-I157674565, not p-i157674565).
    """
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9-]+", "-", text).strip("-")
    return text or "x"


ENTITY_RE = re.compile(r"^(p|a|c|l)-(.+)$")
NODE_RE = re.compile(r"^(d|f|sf|t)-(.+)$")


def _encode_entity(entity) -> str | None:
    if entity is None:
        return None
    kind, value = entity
    kind = str(kind).strip().lower()
    if kind not in ENTITY_KINDS:
        raise ValueError(f"entity kind must be one of {sorted(ENTITY_KINDS)}; got {kind!r}")
    return f"{kind}-{_safe_token(value)}"


def _encode_node(node) -> str | None:
    if node is None:
        return None
    level, value = node
    level = str(level).strip().lower()
    if level not in NODE_LEVELS:
        raise ValueError(f"node level must be one of {sorted(NODE_LEVELS)}; got {level!r}")
    return f"{level}-{_safe_token(value)}"


# ============================================================================
# FILENAME GRAMMAR (rev 3.1)
# ============================================================================

def build_filename(view: str, indicator: str, state: Any, *, entity=None, node=None) -> str:
    """
    lorraine-explorer_<view>_<indicator>_<snapshot>_<conf>_<artifact>
        [_<subset>][_<entity>][_<node>].xlsx
    """
    st_ = _as_state(state)
    parts = [
        "lorraine-explorer", slug(view), slug(indicator), slug(st_.snapshot),
        st_.conf, st_.artifact,
    ]
    if st_.subset and st_.subset != "all":
        parts.append(slug(st_.subset))
    enc_entity = _encode_entity(entity)
    if enc_entity:
        parts.append(enc_entity)
    enc_node = _encode_node(node)
    if enc_node:
        parts.append(enc_node)
    return "_".join(parts) + ".xlsx"


def parse_filename(name: str) -> dict:
    """
    Inverse of `build_filename` over the round-trip scope: {view, indicator,
    snapshot, conf, artifact, subset, entity, node} (rev 3.1
    round_trip_scope). `entity`/`node` come back as (kind, value) tuples,
    exactly what `build_filename` accepts.
    """
    stem = name[:-5] if name.lower().endswith(".xlsx") else name
    segs = stem.split("_")
    if len(segs) < 6 or segs[0] != "lorraine-explorer":
        raise ValueError(f"not a lorraine-explorer export filename: {name!r}")
    view, indicator, snapshot, conf, artifact = segs[1], segs[2], segs[3], segs[4], segs[5]
    if conf not in CONF_TOKENS:
        raise ValueError(f"unrecognised conf token {conf!r} in {name!r}")
    if artifact not in ARTIFACT_TOKENS:
        raise ValueError(f"unrecognised artifact token {artifact!r} in {name!r}")

    tail = segs[6:]
    node = None
    if tail and NODE_RE.match(tail[-1]):
        m = NODE_RE.match(tail.pop())
        node = (m.group(1), m.group(2))
    entity = None
    if tail and ENTITY_RE.match(tail[-1]):
        m = ENTITY_RE.match(tail.pop())
        entity = (m.group(1), m.group(2))
    subset = tail[0] if tail else None

    return {
        "view": view, "indicator": indicator, "snapshot": snapshot,
        "conf": conf, "artifact": artifact, "subset": subset,
        "entity": entity, "node": node,
    }


# ============================================================================
# HEADER SHEET
# ============================================================================

def _format_filters(filters: Any) -> str:
    if not filters:
        return ""
    if isinstance(filters, dict):
        return "; ".join(f"{k}={v}" for k, v in filters.items())
    if isinstance(filters, (list, tuple, set)):
        return "; ".join(str(x) for x in filters)
    return str(filters)


def _header_rows(view: str, indicator: str, st_: ExportState, entity, node) -> list:
    banner_text = ARTIFACT_BANNER_TEXT_FR if st_.artifact == "filtered" else ""
    values = {
        "method_one_liner": st_.method or f"{view} / {indicator}",
        "snapshot_date": st_.snapshot,
        "active_filters": _format_filters(st_.filters),
        "conference_toggle_state": st_.conf,
        "artifact_toggle_state": st_.artifact,
        "artifact_applied": "oui" if st_.artifact_applied else "non",
        "artifact_banner_text_if_on": banner_text,
        "deferred_twin_columns": ", ".join(st_.deferred_twins) if st_.deferred_twins else "",
        "perimeter_subset": st_.subset or "all",
        "entity": _encode_entity(entity) or "",
        "drill_node": _encode_node(node) or "",
        "generation_date": date.today().isoformat(),
    }
    return [(f, values[f]) for f in HEADER_FIELDS]


# ============================================================================
# WORKBOOK BUILD
# ============================================================================

def _strip_impact(df: pd.DataFrame) -> pd.DataFrame:
    keep = [c for c in df.columns if not IMPACT_COL_RE.search(str(c))]
    return df[keep]


def _write_workbook(header_rows: list, df: pd.DataFrame, data_sheet_name: str) -> bytes:
    buf = io.BytesIO()
    header_df = pd.DataFrame(header_rows, columns=["Champ", "Valeur"])
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        header_df.to_excel(writer, sheet_name=METHOD_SHEET_NAME, index=False)
        df.to_excel(writer, sheet_name=data_sheet_name[:31], index=False)
    return buf.getvalue()


def _export(df: pd.DataFrame, view: str, indicator: str, state: Any, *, entity, node,
            impact_strip: bool, data_sheet_name: str) -> tuple[bytes, str]:
    st_ = _as_state(state)
    out = _strip_impact(df) if impact_strip else df
    header_rows = _header_rows(view, indicator, st_, entity, node)
    filename = build_filename(view, indicator, st_, entity=entity, node=node)
    xlsx_bytes = _write_workbook(header_rows, out, data_sheet_name)
    return xlsx_bytes, filename


def panel_xlsx(df: pd.DataFrame, view: str, indicator: str, state: Any, *,
               entity=None, node=None, impact_strip: bool = False) -> tuple[bytes, str]:
    """
    Panel-level export: the panel's own aggregated grain + the mandatory
    method sheet. Returns (xlsx_bytes, filename) per the rev 3.1 contract.
    """
    return _export(df, view, indicator, state, entity=entity, node=node,
                    impact_strip=impact_strip, data_sheet_name=DATA_SHEET_NAME)


def works_xlsx(df: pd.DataFrame, view: str, indicator: str, state: Any, *,
               entity=None, node=None, impact_strip: bool = False) -> tuple[bytes, str]:
    """
    Same as `panel_xlsx`, for drill (publications) exports -- lazy sources
    only (plan §6.4.2): `df` must already be the predicate-pushdown slice from
    `lib.lazy.read_keyed`, never the full corpus. Author-scoped drills should
    pass `impact_strip=True` (§6.4-3bis); `aut_works` itself is structurally
    impact-free, so this is defence-in-depth, not the primary control.
    """
    return _export(df, view, indicator, state, entity=entity, node=node,
                    impact_strip=impact_strip, data_sheet_name=WORKS_SHEET_NAME)


def attach_download(st_container, df: pd.DataFrame, view: str, indicator: str, state: Any, *,
                     entity=None, node=None, impact_strip: bool = False,
                     works: bool = False, label: str = "⬇ Données (xlsx)") -> None:
    """
    Render the panel's `⬇ Données (xlsx)` download button, bottom-right of the
    panel (VIZ_SPEC 1.3). Pass `works=True` for a drill/publications export
    (routes to `works_xlsx` instead of `panel_xlsx`).
    """
    builder = works_xlsx if works else panel_xlsx
    xlsx_bytes, filename = builder(df, view, indicator, state, entity=entity, node=node,
                                    impact_strip=impact_strip)
    _, right = st_container.columns([4, 1])
    right.download_button(
        label, data=xlsx_bytes, file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"dl_{filename}",
    )
