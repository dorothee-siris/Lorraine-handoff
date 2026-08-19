# lib/helpers.py
"""
Shared helpers for Université de Lorraine bibliometric dashboard.
Includes: taxonomy lookups, color palettes, blob parsers, utilities.

View-specific table builders should remain in their respective view files.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd
import streamlit as st

# ============================================================================
# CONSTANTS
# ============================================================================

YEAR_START, YEAR_END = 2019, 2023
YEARS = list(range(YEAR_START, YEAR_END + 1))

# Domain order (by ID) - CORRECT ORDER
# Domain 1 = Life Sciences
# Domain 2 = Social Sciences
# Domain 3 = Physical Sciences
# Domain 4 = Health Sciences
#
# DOMAIN_ORDER stays [1,2,3,4]: it is also the POSITIONAL decoder for the
# `Pubs per domain` / `Pubs per year per domain` blobs, which carry exactly four
# slots. The 5th taxonomy entity (`Unclassified`, domain id 0 — the 51 untopiced
# works) is a display-only row; use DOMAIN_ORDER_DISPLAY for ordering tables and
# charts built from thematic_overview.
DOMAIN_ORDER = [1, 2, 3, 4]
DOMAIN_NAMES_ORDERED = ["Life Sciences", "Social Sciences", "Physical Sciences", "Health Sciences"]

# The 5th domain-level entity of thematic_overview: works OpenAlex left untopiced.
UNCLASSIFIED_DOMAIN_ID = 0
UNCLASSIFIED_DOMAIN_NAME = "Unclassified"
DOMAIN_ORDER_DISPLAY = DOMAIN_ORDER + [UNCLASSIFIED_DOMAIN_ID]
DOMAIN_NAMES_ORDERED_DISPLAY = DOMAIN_NAMES_ORDERED + [UNCLASSIFIED_DOMAIN_NAME]

# Domain colors - mapped correctly by ID
DOMAIN_COLORS = {
    # By ID
    0: "#B9B9B9",   # Unclassified (grey)
    1: "#0CA750",   # Life Sciences (green)
    2: "#FFCB3A",   # Social Sciences (yellow)
    3: "#8190FF",   # Physical Sciences (blue)
    4: "#F85C32",   # Health Sciences (red/orange)
    # By name
    "Unclassified": "#B9B9B9",
    "Life Sciences": "#0CA750",
    "Social Sciences": "#FFCB3A",
    "Physical Sciences": "#8190FF",
    "Health Sciences": "#F85C32",
    # Fallback
    "Other": "#7f7f7f",
}

DOMAIN_EMOJI = {
    "Health Sciences": "🟥",
    "Life Sciences": "🟩",
    "Physical Sciences": "🟦",
    "Social Sciences": "🟨",
    "Unclassified": "⬜",
    "Other": "⬜",
}

# Document types. v1 hard-coded five; D36/D52 added conference papers, so the
# `Pubs per type` blob carries six positional slots (the column name still lists
# the v1 five - it is the contract's declared name, decoded positionally).
DOCTYPE_LABELS = ["Articles", "Book chapters", "Books", "Reviews", "Preprints", "Conference papers"]

# Pass-6 palette (VIZ_SPEC_pass6 S2, S-LIB owns the single-source token, S0.2):
# replaces the v1/v5 set, which was a near-clone of DOMAIN_COLORS hue-for-hue
# (worst pair Revues<->Life Sciences DE 1.6 -- indistinguishable to a full-colour
# reader) and failed the light-mode validator outright. This set PASSES the
# validator (all-pairs, --mode light --surface #FFFFFF) and clears >=12.0 DE
# (normal vision) from every DOMAIN_COLORS slot (S2.5, worst pair 13.1). Keys are
# UNCHANGED (DOCTYPE_LABELS, the EN blob-positional decoder) -- only the hex
# values move, so `parse_doctype_blob` (Streamlit/pages/2_..._Laboratoires.py)
# and every existing caller keep working with zero code change.
DOCTYPE_COLORS = {
    "Articles": "#22A2BD",
    "Book chapters": "#7838B6",
    "Books": "#667900",
    "Reviews": "#A55F8F",
    "Preprints": "#8C9196",   # neutral grey, not an identity (never in the corpus -- collection rule)
    "Conference papers": "#A10A4E",
}

# Pass-6 (VIZ_SPEC_pass6 S2.6): FR order/label constants keyed by the RAW
# `ul_pubs.type` column values (distinct from DOCTYPE_LABELS' EN blob-positional
# keys above) -- for a caller working with the type column directly rather than
# through `parse_doctype_blob`'s positional decode. Fixed order = corpus order =
# volume order (never a data-dependent sort, VIZ_SPEC S1.5 "Ordering").
DOCTYPE_ORDER_FR = ["article", "conference-paper", "book-chapter", "book", "review"]
DOCTYPE_LABEL_FR = {
    "article": "Articles",
    "conference-paper": "Actes de conférence",
    "book-chapter": "Chapitres d'ouvrage",
    "book": "Ouvrages",
    "review": "Revues de littérature",
}
NEUTRAL_GREY = "#8C9196"   # « Autres », comparaison, non-identité (VIZ_SPEC_pass6 S7.4)

# D53: a missing indicator is "n/a", never 0.
NA_MARK = "n/a"

# RA-C05 fix: the focal institution's OpenAlex id, single-sourced here (mirrors
# config.yaml: perimeter.ul_openalex_id) instead of being re-typed page-locally with a
# comment claiming provenance it didn't have (page 12's former UL_ENTITY_ID literal).
UL_OPENALEX_ID = "I90183372"

# ============================================================================
# SAFE CONVERTERS
# ============================================================================

def safe_int(val: Any) -> int:
    """Convert value to int, return 0 on failure."""
    if pd.isna(val):
        return 0
    try:
        return int(float(str(val).strip().replace(",", "")))
    except (ValueError, TypeError):
        return 0


def safe_float(val: Any) -> float:
    """Convert value to float, return NaN on failure."""
    if pd.isna(val):
        return np.nan
    try:
        return float(str(val).strip().replace(",", "."))
    except (ValueError, TypeError):
        return np.nan


# ============================================================================
# TAXONOMY LOOKUPS
# ============================================================================
from lib.data_cache import get_topics_df
_TAXONOMY_CACHE: Dict[str, Any] = {}


def _ensure_taxonomy_loaded(topics_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Ensure taxonomy is loaded. Pass topics_df or it will try to import from data_cache."""
    if "df" not in _TAXONOMY_CACHE:
        if topics_df is not None:
            _TAXONOMY_CACHE["df"] = topics_df
        else:
            _TAXONOMY_CACHE["df"] = get_topics_df()
    return _TAXONOMY_CACHE["df"]


def init_taxonomy(topics_df: pd.DataFrame) -> None:
    """Initialize taxonomy cache with provided DataFrame. Call once at app start."""
    _TAXONOMY_CACHE.clear()
    _TAXONOMY_CACHE["df"] = topics_df


def get_domain_id_to_name() -> Dict[int, str]:
    """
    Return {domain_id: domain_name} mapping.

    all_topics is the OpenAlex dictionary and carries no domain 0, so the
    `Unclassified` entity of thematic_overview is injected here — otherwise every
    domain chart silently drops the untopiced works (0.1%, and the coverage jump
    from the v1 topic model's 79% is a headline).
    """
    if "domain_id_to_name" not in _TAXONOMY_CACHE:
        df = _ensure_taxonomy_loaded()
        mapping = (
            df[["domain_id", "domain_name"]]
            .drop_duplicates()
            .set_index("domain_id")["domain_name"]
            .to_dict()
        )
        mapping = {int(k): v for k, v in mapping.items()}
        mapping.setdefault(UNCLASSIFIED_DOMAIN_ID, UNCLASSIFIED_DOMAIN_NAME)
        _TAXONOMY_CACHE["domain_id_to_name"] = mapping
    return _TAXONOMY_CACHE["domain_id_to_name"]


def get_domain_name_to_id() -> Dict[str, int]:
    """Return {domain_name: domain_id} mapping."""
    if "domain_name_to_id" not in _TAXONOMY_CACHE:
        _TAXONOMY_CACHE["domain_name_to_id"] = {v: k for k, v in get_domain_id_to_name().items()}
    return _TAXONOMY_CACHE["domain_name_to_id"]


def get_field_id_to_name() -> Dict[int, str]:
    """Return {field_id: field_name} mapping."""
    if "field_id_to_name" not in _TAXONOMY_CACHE:
        df = _ensure_taxonomy_loaded()
        _TAXONOMY_CACHE["field_id_to_name"] = (
            df[["field_id", "field_name"]]
            .drop_duplicates()
            .set_index("field_id")["field_name"]
            .to_dict()
        )
    return _TAXONOMY_CACHE["field_id_to_name"]


def get_field_name_to_id() -> Dict[str, int]:
    """Return {field_name: field_id} mapping."""
    if "field_name_to_id" not in _TAXONOMY_CACHE:
        _TAXONOMY_CACHE["field_name_to_id"] = {v: k for k, v in get_field_id_to_name().items()}
    return _TAXONOMY_CACHE["field_name_to_id"]


def get_field_id_to_domain_id() -> Dict[int, int]:
    """Return {field_id: domain_id} mapping."""
    if "field_id_to_domain_id" not in _TAXONOMY_CACHE:
        df = _ensure_taxonomy_loaded()
        _TAXONOMY_CACHE["field_id_to_domain_id"] = (
            df[["field_id", "domain_id"]]
            .drop_duplicates()
            .set_index("field_id")["domain_id"]
            .to_dict()
        )
    return _TAXONOMY_CACHE["field_id_to_domain_id"]


def get_subfield_id_to_name() -> Dict[int, str]:
    """Return {subfield_id: subfield_name} mapping."""
    if "subfield_id_to_name" not in _TAXONOMY_CACHE:
        df = _ensure_taxonomy_loaded()
        _TAXONOMY_CACHE["subfield_id_to_name"] = (
            df[["subfield_id", "subfield_name"]]
            .drop_duplicates()
            .set_index("subfield_id")["subfield_name"]
            .to_dict()
        )
    return _TAXONOMY_CACHE["subfield_id_to_name"]


def get_subfield_id_to_field_id() -> Dict[int, int]:
    """Return {subfield_id: field_id} mapping."""
    if "subfield_id_to_field_id" not in _TAXONOMY_CACHE:
        df = _ensure_taxonomy_loaded()
        _TAXONOMY_CACHE["subfield_id_to_field_id"] = (
            df[["subfield_id", "field_id"]]
            .drop_duplicates()
            .set_index("subfield_id")["field_id"]
            .to_dict()
        )
    return _TAXONOMY_CACHE["subfield_id_to_field_id"]


def get_subfield_id_to_domain_id() -> Dict[int, int]:
    """Return {subfield_id: domain_id} mapping."""
    if "subfield_id_to_domain_id" not in _TAXONOMY_CACHE:
        df = _ensure_taxonomy_loaded()
        _TAXONOMY_CACHE["subfield_id_to_domain_id"] = (
            df[["subfield_id", "domain_id"]]
            .drop_duplicates()
            .set_index("subfield_id")["domain_id"]
            .to_dict()
        )
    return _TAXONOMY_CACHE["subfield_id_to_domain_id"]


def get_field_order_by_domain() -> List[int]:
    """
    Return field IDs ordered by: domain order first (1,2,3,4), then field ID ascending within domain.
    """
    if "field_order_by_domain" not in _TAXONOMY_CACHE:
        df = _ensure_taxonomy_loaded()[["domain_id", "field_id"]].drop_duplicates()
        ordered = []
        for dom_id in DOMAIN_ORDER:
            fields = df.loc[df["domain_id"] == dom_id, "field_id"].tolist()
            ordered.extend(sorted(fields))
        _TAXONOMY_CACHE["field_order_by_domain"] = ordered
    return _TAXONOMY_CACHE["field_order_by_domain"]


def get_field_names_ordered() -> List[str]:
    """Return field names in domain-grouped order."""
    if "field_names_ordered" not in _TAXONOMY_CACHE:
        id2name = get_field_id_to_name()
        _TAXONOMY_CACHE["field_names_ordered"] = [id2name[fid] for fid in get_field_order_by_domain()]
    return _TAXONOMY_CACHE["field_names_ordered"]


def get_subfields_for_field(field_id: int) -> List[int]:
    """Return ordered list of subfield IDs belonging to a field."""
    df = _ensure_taxonomy_loaded()
    return sorted(df.loc[df["field_id"] == field_id, "subfield_id"].drop_duplicates().tolist())


def get_all_field_subfield_map() -> Dict[int, List[int]]:
    """Return {field_id: [subfield_ids]} for all fields."""
    if "field_subfield_map" not in _TAXONOMY_CACHE:
        df = _ensure_taxonomy_loaded()[["field_id", "subfield_id"]].drop_duplicates()
        result = {}
        for fid in df["field_id"].unique():
            result[int(fid)] = sorted(df.loc[df["field_id"] == fid, "subfield_id"].tolist())
        _TAXONOMY_CACHE["field_subfield_map"] = result
    return _TAXONOMY_CACHE["field_subfield_map"]


# ============================================================================
# COLOR FUNCTIONS
# ============================================================================

def get_domain_color(domain: int | str) -> str:
    """Get color for a domain by ID or name."""
    return DOMAIN_COLORS.get(domain, DOMAIN_COLORS["Other"])


def get_field_color(field: int | str) -> str:
    """Get color for a field (based on its parent domain)."""
    if isinstance(field, str):
        field = get_field_name_to_id().get(field, -1)
    dom_id = get_field_id_to_domain_id().get(field, -1)
    return get_domain_color(dom_id)


def get_subfield_color(subfield_id: int) -> str:
    """Get color for a subfield (based on its grandparent domain)."""
    dom_id = get_subfield_id_to_domain_id().get(int(subfield_id), -1)
    return get_domain_color(dom_id)


def darken_hex(hex_color: str, factor: float = 0.65) -> str:
    """Darken a hex color by a factor (0-1). Used for ISITE overlay bars."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join([c * 2 for c in h])
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return "#5a5a5a"
    r, g, b = int(r * factor), int(g * factor), int(b * factor)
    r, g, b = max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple (for WordCloud)."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join([c * 2 for c in h])
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return (127, 127, 127)


# ============================================================================
# BLOB PARSERS — BASIC
# ============================================================================

def parse_pipe_int_list(blob: str) -> List[int]:
    """Parse '101 | 86 | 118' -> [101, 86, 118]."""
    if pd.isna(blob) or not str(blob).strip():
        return []
    return [safe_int(x) for x in str(blob).split("|")]


def parse_pipe_float_list(blob: str) -> List[float]:
    """Parse '1.5 | 0.8 | 2.1' -> [1.5, 0.8, 2.1]."""
    if pd.isna(blob) or not str(blob).strip():
        return []
    return [safe_float(x) for x in str(blob).split("|")]


def parse_pipe_str_list(blob: str) -> List[str]:
    """Parse 'Name1 | Name2 | Name3' -> ['Name1', 'Name2', 'Name3']."""
    if pd.isna(blob) or not str(blob).strip():
        return []
    return [x.strip() for x in str(blob).split("|")]


def parse_pipe_bool_list(blob: str) -> List[bool]:
    """Parse 'True | False | True' -> [True, False, True]."""
    if pd.isna(blob) or not str(blob).strip():
        return []
    return [x.strip().lower() in ("true", "1", "yes") for x in str(blob).split("|")]


def parse_parallel_lists(cols_config: Dict[str, Tuple[str, str]]) -> pd.DataFrame:
    """
    Parse multiple parallel pipe-separated lists into a DataFrame.
    
    Args:
        cols_config: {output_col_name: (blob_value, type)} where type is 'str', 'int', 'float', 'bool'
    """
    parsed = {}
    max_len = 0
    
    for col_name, (blob, dtype) in cols_config.items():
        if dtype == "int":
            values = parse_pipe_int_list(blob)
        elif dtype == "float":
            values = parse_pipe_float_list(blob)
        elif dtype == "bool":
            values = parse_pipe_bool_list(blob)
        else:
            values = parse_pipe_str_list(blob)
        parsed[col_name] = values
        max_len = max(max_len, len(values))
    
    for col_name, (blob, dtype) in cols_config.items():
        fill = 0 if dtype == "int" else (np.nan if dtype == "float" else (False if dtype == "bool" else ""))
        while len(parsed[col_name]) < max_len:
            parsed[col_name].append(fill)
    
    return pd.DataFrame(parsed)


# ============================================================================
# BLOB PARSERS — STRUCTURED
# ============================================================================

def parse_year_domain_blob(blob: str) -> pd.DataFrame:
    """
    Parse 'Pubs per year per domain' blob.
    Format: '2019 (14 ; 19 ; 0 ; 68) | 2020 (12 ; 25 ; 1 ; 55) | ...'
    Domain order in parentheses: 1, 2, 3, 4 (Life, Social, Physical, Health)
    
    Returns DataFrame[year, domain_id, domain_name, count, color].

    Separator-agnostic for the same reason as parse_fwci_boxplot_blob: items are
    found by regex instead of splitting on '|', so a builder that writes the inner
    values with '|' cannot silently empty the chart.
    """
    if pd.isna(blob) or not str(blob).strip():
        return pd.DataFrame(columns=["year", "domain_id", "domain_name", "count", "color"])

    rows = []
    dom_id2name = get_domain_id_to_name()

    for year_str, values_str in re.findall(r"(\d{4})\s*\(([^()]*)\)", str(blob)):
        year = int(year_str)
        values = [safe_int(x) for x in re.split(r"[;|]", values_str)]

        for i, dom_id in enumerate(DOMAIN_ORDER):
            count = values[i] if i < len(values) else 0
            rows.append({
                "year": year,
                "domain_id": dom_id,
                "domain_name": dom_id2name.get(dom_id, f"Domain {dom_id}"),
                "count": count,
                "color": get_domain_color(dom_id),
            })
    
    return pd.DataFrame(rows)


def parse_positional_field_counts(blob: str) -> pd.DataFrame:
    """
    Parse 'Pubs per field' blob (positional, IDs 11-36).
    Format: '3 | 3 | 15 | 2 | 0 | ...' (26 values)
    
    Returns DataFrame[field_id, field_name, count, domain_id, domain_name, color].
    Ordered by domain grouping.
    """
    values = parse_pipe_int_list(blob)
    id2name = get_field_id_to_name()
    id2dom = get_field_id_to_domain_id()
    dom2name = get_domain_id_to_name()
    field_order = get_field_order_by_domain()
    
    # Build lookup: field_id -> count (data is stored in ID order 11-36)
    field_counts = {}
    for i, count in enumerate(values):
        field_id = 11 + i
        if field_id in id2name:
            field_counts[field_id] = count
    
    # Build rows in domain-grouped order
    rows = []
    for field_id in field_order:
        if field_id not in id2name:
            continue
        dom_id = id2dom.get(field_id, 0)
        rows.append({
            "field_id": field_id,
            "field_name": id2name[field_id],
            "count": field_counts.get(field_id, 0),
            "domain_id": dom_id,
            "domain_name": dom2name.get(dom_id, "Other"),
            "color": get_field_color(field_id),
        })
    
    return pd.DataFrame(rows)


def parse_positional_domain_counts(blob: str) -> pd.DataFrame:
    """
    Parse 'Pubs per domain' blob (positional, IDs 1-4).
    Format: '70 | 198 | 8 | 286' (4 values)
    
    Returns DataFrame[domain_id, domain_name, count, color].
    """
    values = parse_pipe_int_list(blob)
    dom2name = get_domain_id_to_name()
    
    rows = []
    for i, dom_id in enumerate(DOMAIN_ORDER):
        count = values[i] if i < len(values) else 0
        rows.append({
            "domain_id": dom_id,
            "domain_name": dom2name.get(dom_id, f"Domain {dom_id}"),
            "count": count,
            "color": get_domain_color(dom_id),
        })
    
    return pd.DataFrame(rows)


def parse_fwci_boxplot_blob(blob: str) -> pd.DataFrame:
    """
    Parse 'FWCI boxplot per field id (centiles 0,10,25,50,75,90,100)' blob.
    Format: '11 (0.00 ; 0.10 ; 0.32 ; 0.92 ; 1.44 ; 5.40 ; 12.5) | 12 (...) | ...'
    
    Returns DataFrame[field_id, field_name, p0, p10, p25, p50, p75, p90, p100, domain_id, domain_name, color].
    Ordered by domain grouping.

    SEPARATOR-AGNOSTIC ON PURPOSE. v1 separated the seven centiles with ';' inside
    each item; v2's builder uses '|', which is ALSO the item separator — splitting
    on '|' first therefore shredded every item, the per-field regex matched
    nothing, and the whisker plot rendered as an empty frame with no error at all.
    Items are now found by regex and the values split on either separator, so both
    encodings decode.
    """
    id2name = get_field_id_to_name()
    id2dom = get_field_id_to_domain_id()
    dom2name = get_domain_id_to_name()
    field_order = get_field_order_by_domain()

    # Parse blob into dict
    field_data = {}
    if not pd.isna(blob) and str(blob).strip():
        for field_id, values_str in re.findall(r"(\d+)\s*\(([^()]*)\)", str(blob)):
            values = [safe_float(x) for x in re.split(r"[;|]", values_str)]
            if len(values) < 7:
                values.extend([np.nan] * (7 - len(values)))
            field_data[int(field_id)] = values
    
    # Build rows for ALL fields in domain-grouped order
    rows = []
    for field_id in field_order:
        if field_id not in id2name:
            continue
        dom_id = id2dom.get(field_id, 0)
        
        if field_id in field_data:
            values = field_data[field_id]
        else:
            values = [np.nan] * 7
        
        rows.append({
            "field_id": field_id,
            "field_name": id2name.get(field_id, f"Field {field_id}"),
            "p0": values[0],
            "p10": values[1],
            "p25": values[2],
            "p50": values[3],
            "p75": values[4],
            "p90": values[5],
            "p100": values[6],
            "domain_id": dom_id,
            "domain_name": dom2name.get(dom_id, "Other"),
            "color": get_field_color(field_id),
        })
    
    return pd.DataFrame(rows)


def parse_subfield_column(blob: str, field_id: int) -> pd.DataFrame:
    """
    Parse a single 'Pubs per subfield within "X" (id: Y)' column.
    Format: '0 | 5 | 12 | ...' (positional by subfield ID within that field)
    
    Returns DataFrame[subfield_id, subfield_name, count, color].
    """
    values = parse_pipe_int_list(blob)
    subfields = get_subfields_for_field(field_id)
    sub2name = get_subfield_id_to_name()
    
    rows = []
    for i, count in enumerate(values):
        if i >= len(subfields):
            break
        sub_id = subfields[i]
        rows.append({
            "subfield_id": sub_id,
            "subfield_name": sub2name.get(sub_id, f"Subfield {sub_id}"),
            "count": count,
            "color": get_subfield_color(sub_id),
        })
    
    return pd.DataFrame(rows)


# ============================================================================
# UTILITIES
# ============================================================================

def pad_dataframe(df: pd.DataFrame, n_rows: int, numeric_cols: List[str] | None = None) -> pd.DataFrame:
    """
    Ensure DataFrame has exactly n_rows. Truncate if more, pad with blanks if fewer.
    Numeric columns get NaN, text columns get empty string.
    """
    if len(df) >= n_rows:
        return df.head(n_rows).reset_index(drop=True)
    
    numeric_cols = set(numeric_cols or [])
    missing = n_rows - len(df)
    
    filler = {col: (np.nan if col in numeric_cols else "") for col in df.columns}
    filler_df = pd.DataFrame([filler] * missing)
    return pd.concat([df, filler_df], ignore_index=True)


def build_openalex_url(openalex_id: str) -> str:
    """Build OpenAlex URL from ID."""
    if pd.isna(openalex_id) or not str(openalex_id).strip():
        return ""
    oid = str(openalex_id).strip()
    if not oid.startswith("http"):
        return f"https://openalex.org/{oid}"
    return oid

def render_domain_legend(include_unclassified: bool = False):
    """
    Render inline domain color legend.

    `include_unclassified=True` adds the grey 5th entity, for the views built on
    thematic_overview (which carries it). Blob-driven charts have four slots only.
    """
    names = DOMAIN_NAMES_ORDERED_DISPLAY if include_unclassified else DOMAIN_NAMES_ORDERED
    items = "".join(
        f'<span style="display:inline-flex;align-items:center;margin-right:16px;">'
        f'<span style="width:14px;height:14px;background:{get_domain_color(d)};border-radius:3px;margin-right:6px;"></span>'
        f'{d}</span>'
        for d in names
    )
    st.markdown(f'<div style="margin:8px 0 16px 0;">{items}</div>', unsafe_allow_html=True)


# ============================================================================
# D52 — CONFERENCE PAPERS TOGGLE
# ============================================================================

CONFERENCE_HELP = (
    "OpenAlex retyped part of the corpus as `conference-paper` (9,061 works, +31.1% "
    "vs v1). They are in by default. Switch off to isolate the document-type effect; "
    "charts built on pre-aggregated blobs say so in their caption."
)


def conference_toggle() -> bool:
    """
    Prominent sidebar toggle (D52). Returns True when conference papers are included.

    Rendered on every page that counts works, with a shared key so the choice
    follows the user across pages -- `persist_state="session"` (F1/QA-01/RA-A03 fix)
    is what actually makes that true: without it, Streamlit drops a widget's value
    the moment a sidebar page switch stops rendering it, even with the same key.
    """
    from lib.app_config import get_app_config

    default = bool(get_app_config()["include_conference"])
    st.sidebar.markdown("### Corpus")
    included = st.sidebar.toggle(
        "Inclure les articles de conférence",
        value=default,
        key="include_conference",
        persist_state="session",
        help=CONFERENCE_HELP,
    )
    if included:
        st.sidebar.caption("Articles de conférence **inclus** (corpus complet, 36 819 travaux).")
    else:
        st.sidebar.caption("Articles de conférence **exclus** (27 758 travaux).")
    return included


def conference_blob_caveat(what: str = "Ce graphique") -> None:
    """
    D52 honesty clause: pre-aggregated blobs cannot be re-filtered, so say it
    rather than pretending the filter applied. (FR wording per R12, pass 5 —
    meaning verbatim from the EN original.)
    """
    st.caption(
        f":grey[{what} est construit sur une table pré-agrégée et **inclut** "
        "toujours les articles de conférence — il ne peut pas être recalculé "
        "par type de document à partir des données déployées.]"
    )


# ============================================================================
# D53 — NULL INDICATORS RENDER "n/a", NEVER 0
# ============================================================================

def na_metric(val: Any, fmt: str = "{:.2f}") -> str:
    """Format a scalar indicator, or the greyed n/a mark when it is missing."""
    if val is None or (isinstance(val, float) and np.isnan(val)) or pd.isna(val):
        return NA_MARK
    try:
        return fmt.format(float(val))
    except (ValueError, TypeError):
        return NA_MARK


# ============================================================================
# PASS 5 (R1/R11/R14) -- FR NUMBER FORMATTING, ONE HOME
#
# Every pass-5 module that renders a number on an FR surface (lib.overlay's tooltip,
# lib.ranked's table columns, and any future page) imports these from here rather than
# re-implementing French grouping/decimal conventions locally -- "one home, no
# duplicates" (S4 mission note). French typography: U+202F NARROW NO-BREAK SPACE as the
# thousands separator AND before a trailing "%" (never a plain space or NBSP U+00A0,
# and never a comma for grouping); "," as the decimal separator.
# ============================================================================

FR_THIN_SPACE = " "  # NARROW NO-BREAK SPACE


def fr_int(val: Any) -> str:
    """
    French-grouped integer: 1839 -> "1 839" (thousands separator = narrow
    no-break space, per SIRIS FR typography convention). D53: a missing value
    renders as NA_MARK, never 0 or a blank string.
    """
    if val is None or (isinstance(val, float) and np.isnan(val)) or pd.isna(val):
        return NA_MARK
    try:
        n = int(round(float(val)))
    except (ValueError, TypeError):
        return NA_MARK
    return f"{n:,}".replace(",", FR_THIN_SPACE)


def fr_pct(val: Any, decimals: int = 1) -> str:
    """
    French-formatted percentage on the 0-100 SCALE (matching this codebase's
    existing convention -- e.g. page 1's "% ISITE" column is already *100
    before display, never a 0-1 fraction): 4.1 -> "4,1 %" (decimal comma,
    narrow no-break space before the sign). D53: missing -> NA_MARK.
    """
    if val is None or (isinstance(val, float) and np.isnan(val)) or pd.isna(val):
        return NA_MARK
    try:
        s = f"{float(val):.{decimals}f}"
    except (ValueError, TypeError):
        return NA_MARK
    return s.replace(".", ",") + FR_THIN_SPACE + "%"


# ============================================================================
# PASS 5 (R18) -- LOCAL LOG/LINEAR AXIS TOGGLE
# ============================================================================

LOG_LINEAR_TOGGLE_LABEL = "échelle linéaire"


def axis_type_for_toggle(linear_on: bool) -> str:
    """
    Pure logic (no Streamlit dependency, directly unit-testable): log is the
    default axis type (R18) -- the local toggle can only ever ASK for linear.
    """
    return "linear" if linear_on else "log"


def log_linear_toggle(key: str, *, label: str = LOG_LINEAR_TOGGLE_LABEL) -> str:
    """
    Local toggle beside any log-scale chart (R18): renders OFF by default (log
    stays the default axis), returns the resolved Plotly axis type ("log" or
    "linear") for the caller to pass straight to `update_xaxes`/`update_yaxes`
    (`type=...`). One toggle per chart -- pass a chart-specific `key`.
    """
    linear_on = st.toggle(label, value=False, key=key)
    return axis_type_for_toggle(linear_on)


def render_excluded_disclosure(n_excluded: Any, total: Any = None) -> None:
    """
    Disclose how many works are outside the indicator denominator (D53).
    Silent when nothing is excluded.
    """
    n = safe_int(n_excluded)
    if n <= 0:
        return
    suffix = ""
    if total is not None:
        t = safe_int(total)
        if t > 0:
            suffix = f" ({fr_pct(100 * n / t)})"
    st.caption(
        f":grey[Les indicateurs de citation excluent **{fr_int(n)}** publication(s){suffix} — "
        "strate insuffisante. Elles restent comptées dans les totaux de "
        "publications, jamais comme un score nul.]"
    )


# ============================================================================
# PASS 6 (P1 / NARRATIVE_CONTRACT_pass6.md S4) -- METHODO CONTENT, SINGLE SOURCE
#
# "Source unique : lib/helpers.py, rendu à deux endroits. La version courte est
# l'encadré de la barre latérale, sous les trois boutons ; la version longue est la
# section « Méthodes et guide de lecture » du Menu. Les deux lisent les mêmes
# valeurs, calculées." (NARRATIVE_CONTRACT_pass6.md S4, verbatim). The two FR
# templates below are PASTED VERBATIM from that document's S4.1 (short) and S4.2
# (long) -- arbitrage rule for this pass: NARRATIVE_CONTRACT wins wording, this
# module is the single legal source for WHERE it renders from. `{n_topics}` /
# `{window}` / `{snapshot}` are resolved at render time (P6-R2: never a static
# number) -- the ASCII placeholder names are an internal implementation detail,
# never shown; the FR copy itself is unchanged from the source document.
# ============================================================================

from lib.data_cache import DATA_DIR, get_corpus_facts_df  # noqa: E402


@st.cache_data(show_spinner=False)
def artifact_topics_count() -> int:
    """
    Row count of the 811-topic 'hors référentiel' exclusion registry --
    computed at render time, never a hardcoded literal (P6-R2). Returns 0 (never
    raises) if the table is not deployed yet, so the méthodo blocks stay
    renderable even mid-pass. Public (pass-6 re-open): `lib.controls`'s
    artifact-toggle label/help/banner also read this, instead of each
    hardcoding its own "811" literal.
    """
    try:
        return len(pd.read_parquet(DATA_DIR / "dim_artifact_topics.parquet", columns=["topic_id"]))
    except Exception:
        return 0


@st.cache_data(show_spinner=False)
def artifact_topics_share_pct() -> float | None:
    """
    Share (0-100 scale) of the FULL reference corpus (dim_corpus_facts'
    conf_state='all' row -- the pre-existing "11,15 %" was always this fixed
    all-corpus number, independent of the user's own conference-toggle state)
    whose PRIMARY topic is on the 811-topic exclusion list:
    `(corpus_works - corpus_works_xa) / corpus_works * 100`. Computed from the
    already-loaded `dim_corpus_facts` (`_xa` = artifact-excluded twin, the same
    convention as every other `_xa` column in this app) -- no extra I/O beyond
    what `get_corpus_facts_df()` already caches. `None` (never a fabricated
    0, D53) if the facts table lacks the columns/row -- callers drop the
    share from their sentence entirely rather than guess (manager ruling,
    pass-6 re-open).
    """
    try:
        facts = get_corpus_facts_df()
        row = facts.loc[facts["conf_state"] == "all"].iloc[0]
        corpus_works = float(row["corpus_works"])
        corpus_works_xa = float(row["corpus_works_xa"])
        if corpus_works <= 0:
            return None
        return (corpus_works - corpus_works_xa) / corpus_works * 100
    except Exception:
        return None


def window_label() -> str:
    """
    The corpus year window as FR-formatted text ("2019–2023") -- ONE place
    every page reads it from instead of hardcoding the years (NARRATIVE_CONTRACT
    motif G1). Mirrors config.yaml's perimeter.year_from/year_to via this
    module's own YEAR_START/YEAR_END constants (same "computed, single-sourced"
    pattern as UL_OPENALEX_ID above).
    """
    return f"{YEAR_START}–{YEAR_END}"


def snapshot_date_label() -> str:
    """
    The deployed snapshot date, read from dim_corpus_facts.parquet -- never a
    hardcoded literal (P6-R2). "?" (never a crash) if the table is unavailable.
    """
    try:
        facts = get_corpus_facts_df()
        if len(facts):
            return str(facts["snapshot_date"].iloc[0])
    except Exception:
        pass
    return "?"


METHODO_EXPANDER_LABEL = "ℹ️ À propos des filtres"
METHODO_MENU_LINK_LABEL = "Méthodes et guide de lecture"
METHODO_MENU_PAGE = "Menu.py"

# NARRATIVE_CONTRACT_pass6.md S4.1, verbatim (the leading "> " blockquote markers
# of the source document are its own quoting convention, not part of the copy).
_METHODO_SIDEBAR_FR = """\
**Types de publication.** Le corpus retient cinq types : articles, chapitres d'ouvrage, revues \
de littérature, ouvrages et actes de conférence. Les préprints sont exclus, pour une raison de \
dédoublonnage : un préprint et sa version publiée sont deux enregistrements distincts. Les \
thèses, résumés de conférence, rapports, jeux de données, éditoriaux, errata et évaluations par \
les pairs sont hors périmètre.

**Topics hors référentiel.** {n_topics} topics d'OpenAlex sont signalés à la main par SIRIS : ce \
ne sont pas de « mauvais » sujets, ce sont des sujets que le classifieur mondial rattache mal, \
souvent des objets locaux ou nationaux (histoire de France, études urbaines françaises). Ils \
restent affichés et marqués partout ; le bouton permet de les exclure, il est désactivé par \
défaut.

**Contribution I-SITE.** Le bouton assombrit, sur les graphiques qui portent cette \
décomposition, la part relevant du périmètre I-SITE. Il ne retire jamais de travaux. Le \
périmètre est défini par la liste de DOI validée par l'établissement.

**Articles de conférence.** Inclus par défaut : OpenAlex a reclassé en actes de conférence une \
part notable du corpus, et les exclure ferait disparaître une production réelle, en particulier \
en informatique. Le bouton permet d'isoler cet effet de type de document.\
"""

# NARRATIVE_CONTRACT_pass6.md S4.2, verbatim.
_METHODO_MENU_FR = """\
## Méthodes et guide de lecture

### Ce que l'outil compte

Les publications proviennent d'**OpenAlex**, sur la fenêtre {window}, à la date d'instantané \
{snapshot}. Le périmètre est défini par une requête unique : toute publication qu'OpenAlex \
rattache à l'Université de Lorraine ou à l'une de ses structures descendantes. Les résumés \
manquants sont complétés par HAL puis par OpenAIRE, en conservant la source sur chaque ligne. \
Deux entrées sont maintenues à la main par l'établissement : la liste des structures et la liste \
des DOI de l'I-SITE.

Un instantané est une photographie datée : relancer le même code sur le même instantané \
reproduit les mêmes chiffres, tandis qu'une interrogation en direct d'OpenAlex peut différer \
légèrement, la base étant vivante.

### Pourquoi ces types de publication

Le corpus retient cinq types : **articles, chapitres d'ouvrage, revues de littérature, ouvrages \
et actes de conférence**. Trois exclusions méritent d'être expliquées.

Les **préprints** sont écartés intégralement, pour une raison de dédoublonnage : dans OpenAlex, \
un préprint et sa version publiée sont deux enregistrements distincts, et les compter tous les \
deux gonflerait le volume sans ajouter de recherche. Cette exclusion a une conséquence assumée : \
elle sous-représente les disciplines qui déposent massivement en préprint, sciences humaines et \
sociales comprises.

Les **jeux de données, paratextes et évaluations par les pairs** sont écartés parce qu'ils ne \
sont pas des contributions scientifiques au sens où les indicateurs de citation les entendent : \
les compter fausserait tous les dénominateurs.

Les **actes de conférence** sont, eux, **inclus**, et un bouton permet de les isoler. La raison \
est factuelle : OpenAlex a reclassé en actes de conférence une part notable de la production du \
site, et les exclure ferait disparaître des publications que l'établissement voit dans ses \
propres outils, en sous-représentant fortement l'informatique. La conséquence se lit du côté des \
citations : les actes sont peu cités par construction, ce que la stratification par type de \
document traite automatiquement.

### Les topics « hors référentiel »

**Ce ne sont pas de mauvais sujets.** Ce sont des sujets qu'un classifieur entraîné sur une \
littérature majoritairement anglophone résout mal, et qu'il est donc difficile de rattacher à \
une référence thématique mondiale. Ils recouvrent souvent des objets locaux ou nationaux : \
histoire de France, études urbaines françaises, droit national, patrimoine régional.

{n_topics} topics sont signalés ainsi. Le repérage a été fait **à la main par SIRIS**, sujet par \
sujet, et il est visible partout dans l'application : chaque ligne, chaque cellule et chaque \
point concerné porte un marqueur †, et l'en-tête de chaque export indique si le filtre était \
actif. Un bouton unique, **désactivé par défaut**, permet de les exclure ; l'affichage complet \
reste le comportement normal.

La sémantique du bouton dépend du grain de la table, et c'est voulu. Au grain publication, \
l'activer retire les travaux dont le **topic principal** est marqué. Au grain topic, il retire \
en plus les lignes de topic elles-mêmes marquées, une population plus large puisqu'elle compte \
aussi les topics secondaires d'une publication. Deux familles échappent au bouton par \
construction : le **momentum**, mesure figée qu'un recalcul par sous-ensemble rendrait \
incomparable à elle-même, et les **corpus des pairs**, tirés en direct d'OpenAlex, hors de \
l'instantané local qui porte la liste.

### La contribution I-SITE

Le bouton « Afficher la contribution I-SITE » **ne filtre rien** : là où une décomposition \
existe, il assombrit la part relevant du périmètre I-SITE sur la barre déjà affichée. Environ la \
moitié des graphiques de l'outil ne portent pas cette décomposition : sur ceux-là, le bouton \
n'a aucun effet, et le panneau le dit.

Le périmètre I-SITE est défini par la **liste de DOI validée par l'établissement**, jamais par \
un mot-clé ni par un rattachement automatique. Cette liste porte une date : les années les plus \
récentes sont donc sous-couvertes, et un recul apparent de l'I-SITE sur la dernière année tient \
au retard de mise à jour de la liste, jamais à un recul réel de la production.

### Les indicateurs de citation

Les indicateurs sont normalisés contre une **référence française** collectée sur la même \
fenêtre et les mêmes types de publication que le corpus lorrain. La strate de normalisation est \
unique : sous-champ × année de publication × type de document. Sous 30 publications dans une \
strate, l'indicateur n'est **pas calculé** : il s'affiche « n/a », en grisé, et n'entre dans \
aucun dénominateur. Un indicateur absent et un indicateur nul ne disent pas la même chose.

Le FWCI affiché rapporte les citations d'une publication à la moyenne de sa strate française. \
Une valeur de 1 signifie « cité comme la moyenne française des publications du même sous-champ, \
de la même année et du même type ». Ce n'est pas le FWCI natif d'OpenAlex, qui se normalise \
contre la production mondiale sur une fenêtre fixe.

### Les Objectifs de développement durable

Trois routes d'attribution ont été calculées et sont livrées ; le choix entre elles est un \
arbitrage d'atelier, pas une décision technique déjà prise. La route active se lit sur le \
panneau ODD, et en changer est un réglage de configuration, jamais une reconstruction. Les \
écarts entre routes mesurent un **accord** entre méthodes, jamais une exactitude : aucune \
vérité terrain n'existe.

### Ce que cette méthode ne fait pas

Elle ne mesure pas la production « réelle » de l'établissement, mais ce qu'OpenAlex lui \
rattache à une date donnée : le rattachement institutionnel est un choix, et OpenAlex retraite \
l'historique des affiliations des années après une collecte. Elle ne fournit aucune vérité \
terrain sur les ODD. Et elle distingue soigneusement deux exercices : **croiser** deux \
dimensions internes (laboratoire × ODD, laboratoire × frontière) n'est pas **comparer** à des \
pairs, et l'outil ne mélange jamais les deux.\
"""


def methodo_values() -> dict:
    """The three computed values both templates interpolate -- exposed so a
    caller (or a test) can read them without re-rendering the widgets."""
    return {
        "n_topics": fr_int(artifact_topics_count()),
        "window": window_label(),
        "snapshot": snapshot_date_label(),
    }


def render_methodo_expander() -> None:
    """
    Sidebar « ℹ️ À propos des filtres » expander (P1 placement: directly under
    the 3 filter toggles) -- the SHORT méthodo copy, NARRATIVE_CONTRACT_pass6.md
    S4.1 verbatim, plus a link to the long Menu section.
    """
    values = methodo_values()
    with st.sidebar.expander(METHODO_EXPANDER_LABEL, expanded=False):
        st.markdown(_METHODO_SIDEBAR_FR.format(**values))
        st.page_link(METHODO_MENU_PAGE, label=f"→ {METHODO_MENU_LINK_LABEL}")


def render_methodo_menu_section() -> None:
    """
    The full « Méthodes et guide de lecture » section of the Menu -- the LONG
    méthodo copy, NARRATIVE_CONTRACT_pass6.md S4.2 verbatim.
    """
    values = methodo_values()
    st.markdown(_METHODO_MENU_FR.format(**values))


# ============================================================================
# PASS 6 (S-LIB build 4c, P6-R3 / grill Q3) -- LAZY PER-SLICE DOWNLOAD BYTES
#
# "the global works file must NEVER be loaded resident" -- every download button
# built on a work-grain file goes through this (or lib.lazy.read_keyed directly),
# never a bare pd.read_parquet(full_path) followed by an in-memory filter.
# ============================================================================

def lazy_slice_csv_bytes(path, key_col: str, key_value, columns: List[str] | None = None) -> bytes:
    """
    Read ONLY the row groups matching `key_value` on `key_col` (predicate
    pushdown via `lib.lazy.read_keyed` -- same file must be sorted by
    `key_col` with a small row_group_size, per lib/lazy.py's own convention)
    and return UTF-8 CSV bytes ready for `st.download_button`. `key_value` may
    be a scalar or a list (an `IN` filter, e.g. every partner in one country).

    This is the one path a page-level "download this slice" button should
    call for a lazy work/cell-grain file (ptn_works, aut_works, subset_works,
    ...) -- it never reads the file in full, so the global works table is
    never resident just to serve one entity's download.
    """
    from lib.lazy import read_keyed

    df = read_keyed(path, key_col, key_value, columns=columns)
    return df.to_csv(index=False).encode("utf-8-sig")


# ============================================================================
# PASS 6 (S-LIB build 4d, VIZ_SPEC_pass6 S8) -- MOMENTUM: QUANTIFIED DISPLAY
#
# Zero recomputation of the frozen pass-3 momentum family (ptn_summary.mom_class/
# mom_category, ptn_mom_facts.recentring_median): `momentum_display()` only
# RE-EXPRESSES the ratio the classification was already made from, as the
# signed-pp text VIZ_SPEC_pass6 S8.2 specifies -- the ONE formatter P-COL, P-ZP
# and P-PF all wire instead of drifting apart (VIZ_SPEC_pass6 S8.3: "S-LIB ships
# the one formatter ... so the four pages cannot drift apart").
# ============================================================================

MOMENTUM_UP_COLOR = "#009E73"
MOMENTUM_DOWN_COLOR = "#D55E00"
MOMENTUM_STABLE_COLOR = "#5A5F66"
MOMENTUM_NEUTRAL_COLOR = "#8C9196"
MOMENTUM_GLYPHS = {"up": "↗", "down": "↘", "stable": "→"}  # ↗ ↘ →
MOMENTUM_MIN_W1_COUNT = 5   # RULES S2 "growth ratios at tiny baselines" guard
MOMENTUM_CLAMP_PCT = 999    # down is bounded at -100% by construction; up is not


def _momentum_window_labels() -> tuple[str, str, str]:
    """
    Pass-6 re-open (P6-R2, P-ZP flag): the two window labels used to be typed
    literally ("2019-2021 vs 2022-2023") into `MOMENTUM_METHOD_HELP_FR` below
    -- and that literal was ALSO WRONG (the frozen method's real windows are
    2019-2020 vs 2022-2023, 2021 is a buffer year, per
    pipeline/lib46_momentum.py's own W1_YEARS/W2_YEARS -- see
    progress/SREG.md's independent verification). S-DAT now exposes
    `mom_w1_label`/`mom_w2_label` on `ptn_mom_facts.parquet` (`conf_state='all'`
    row -- the fixed reference variant, same convention as
    `artifact_topics_share_pct()` above); read here ONCE at import time (same
    "computed once per process" pattern as `lib.controls`'s artifact-topics
    fix) so `MOMENTUM_METHOD_HELP_FR` stays a PLAIN STRING constant --
    page 9 already imports and renders it as a bare attribute
    (`st.caption(MOMENTUM_METHOD_HELP_FR)`), so turning it into a callable
    would break a live call site outside this fence. Falls back to "?" / "?"
    (never a crash, never a guessed year) if the table/columns are missing.

    Pass-6 re-open (S-LENS D4, 3rd strike on this same sentence): the
    recentring median was ALSO hardcoded ("médiane 1,06") right next to the
    window labels this function already fixed -- same failure mode, same
    table. Read `recentring_median` in this one call too and return its FR
    string (2 decimals, comma separator -- the house convention for ratio
    values, see page 2/6/7's `_fr_ratio`-style formatters) so the whole
    sentence is computed from one read. Falls back to "?" on any failure,
    same discipline as the window labels.
    """
    try:
        facts = pd.read_parquet(
            DATA_DIR / "ptn_mom_facts.parquet",
            columns=["conf_state", "mom_w1_label", "mom_w2_label", "recentring_median"],
        )
        row = facts.loc[facts["conf_state"] == "all"].iloc[0]
        w1 = str(row["mom_w1_label"])
        w2 = str(row["mom_w2_label"])
        median_str = "?"
        median_val = row["recentring_median"]
        if median_val is not None and not pd.isna(median_val):
            median_str = f"{float(median_val):.2f}".replace(".", ",")
        if w1 and w2 and w1 != "nan" and w2 != "nan":
            return w1, w2, median_str
    except Exception:
        pass
    return "?", "?", "?"


_MOM_W1_LABEL, _MOM_W2_LABEL, _MOM_RECENTRING_MEDIAN = _momentum_window_labels()

# VIZ_SPEC_pass6 S8.3 wording, pass-6 re-open (window years + recentring
# median now computed, P6-R2 / S-LENS D4) -- the column `help=` (P-COL) AND
# the paragraph reused by the Zoom partenaire quantified block (P-ZP), same
# text both places. The ±25% stability band and the 5% significance
# threshold below are FROZEN METHOD CONSTANTS (parameters of the pass-3
# method, not data readings) -- legal to leave literal, per S-LENS D4 note.
MOMENTUM_METHOD_HELP_FR = (
    f"Momentum : comparaison de deux fenêtres ({_MOM_W1_LABEL} vs {_MOM_W2_LABEL}) de la part "
    "annualisée du partenaire dans la production collaborative de l'UL, recentrée "
    f"sur la dérive du corpus (médiane {_MOM_RECENTRING_MEDIAN}) pour ne pas confondre la croissance du "
    "partenariat avec celle du corpus. Bande de stabilité ±25 %. Un écart hors "
    "bande n'est affiché comme hausse ou retrait que s'il est significatif au "
    "seuil de 5 % ; sinon « non significatif ». Famille d'indicateurs figée : non "
    "recalculée sous les filtres référentiel ou I-SITE."
)


def _field(obj: Any, name: str, default: Any = None) -> Any:
    """dict / pandas.Series / attribute access, uniformly -- `row`/`facts`
    arguments below may be any of the three."""
    if hasattr(obj, "get"):
        try:
            return obj.get(name, default)
        except TypeError:
            pass
    return getattr(obj, name, default)


def _momentum_w1_count(count_arrow: Any) -> float | None:
    """First (window-1) raw count out of the '{c1}->{c2}' mom_count_arrow blob
    (data_contract.yaml). None when unparseable -- callers treat that as
    "cannot verify the base", never as a crash."""
    if count_arrow is None:
        return None
    try:
        if pd.isna(count_arrow):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(str(count_arrow).split("->")[0])
    except (ValueError, TypeError, IndexError):
        return None


def _signed_pct_no_decimal(delta_pct: float) -> str:
    """Signed FR percentage, no decimals (VIZ_SPEC_pass6 S8.2: "a decimal is
    false precision" -- the input is a ratio of two annualised shares).
    Clamped above +999% (S8.2: the eligible set reaches +4 102% on a 1->20
    base) -- down deltas are bounded at -100% by construction, so only the up
    side needs the clamp."""
    if delta_pct > MOMENTUM_CLAMP_PCT:
        return f"> +{MOMENTUM_CLAMP_PCT}{FR_THIN_SPACE}%"
    sign = "+" if delta_pct >= 0 else "−"
    return f"{sign}{fr_int(round(abs(delta_pct)))}{FR_THIN_SPACE}%"


def momentum_display_values(
    *,
    category: Any,
    w1_share: Any,
    w2_share: Any,
    recentring_median: Any = None,
    count_arrow: Any = None,
) -> tuple[str, str, str | None]:
    """
    VIZ_SPEC_pass6 S8 -- the CORE, grain-agnostic momentum formatter (pass-6
    re-open: generalised out of `momentum_display()` below so a second grain
    never needs its own copy -- pass-5 post-mortem's "F27 drift class").
    Takes the raw values directly rather than a ptn_summary-shaped `row`/
    `ptn_mom_facts`-shaped `facts` pair, so ANY table carrying the same
    semantic fields under its own column names can call it: the partner grain
    (`ptn_summary.mom_category` + `ptn_mom_facts.recentring_median`) via the
    `momentum_display()` wrapper below, and the taxon/topic/thematic grain
    (`topics_zero_fill`/`subfields_zero_fill`: mom_class, mom_p_value,
    mom_w1_share, mom_w2_share -- the four REQUIRED fields at that grain) by
    calling this directly.

    `category` accepts EITHER vocabulary: ptn_summary's `mom_category`
    (up/down/stable/ns/new/dormant) or the narrower `mom_class`
    (up/down/stable/ns only, no new/dormant screens) -- the two are
    compatible subsets, same string values. `count_arrow` is OPTIONAL: grains
    without a raw per-window count column (topics/subfields zero-fill) simply
    never trigger the W1-count guard (`count_arrow=None` -- indistinguishable
    from "cannot verify the base", never a crash, never a fabricated guard).

    `recentring_median` is also OPTIONAL (pass-6 re-open, P-PF: the thematic
    grain has NO persisted recentring_median at all -- unlike `count_arrow`,
    which merely narrows a guard, the median is load-bearing for the
    quantified DELTA ITSELF: `(w2/w1)/median - 1`. Silently defaulting it to
    1 would IMPLY the same corpus-drift correction the partner-grain figure
    carries, which would be false -- so when it is absent, the quantified
    clause is OMITTED entirely rather than computed on a fabricated median or
    the call failing: the classification is still real (mom_class/mom_p_value
    already decided it), so the glyph and its status colour still render;
    only the "{signed pp}" clause does not.

    Returns `(text, hex_color, glyph)` -- `glyph` is `None` when the case has
    no directional arrow (ns/new/dormant/not-eligible).

    Case order (S8.2, evaluated top to bottom):
      1. category null/missing -> "—" (not eligible)
      2. "new" / "dormant" -> the fixed FR label, no arrow
      3. "ns" -> "non significatif", no arrow (never a numeric delta)
      4. up/down/stable, W1 count < 5 -> "{arrow} base trop faible" (RULES S2
         growth-at-tiny-baseline guard) -- the arrow for the category that
         WOULD have been shown, so the direction is not simply hidden
      5. up/down/stable, recentring_median absent -> "{arrow}" alone (the
         quantified clause omitted, never fabricated -- P-PF, thematic grain)
      6. up/down/stable, otherwise -> "{arrow} {signed pp}", the category's
         status colour
    """
    try:
        is_null = category is None or pd.isna(category)
    except (TypeError, ValueError):
        is_null = category is None
    if is_null:
        return "—", MOMENTUM_NEUTRAL_COLOR, None
    category = str(category)

    if category == "new":
        return "nouveau partenaire", MOMENTUM_NEUTRAL_COLOR, None
    if category == "dormant":
        return "partenaire dormant", MOMENTUM_NEUTRAL_COLOR, None
    if category == "ns":
        return "non significatif", MOMENTUM_NEUTRAL_COLOR, None
    if category not in MOMENTUM_GLYPHS:
        return "—", MOMENTUM_NEUTRAL_COLOR, None  # unrecognised value, never crash

    glyph = MOMENTUM_GLYPHS[category]
    color = {
        "up": MOMENTUM_UP_COLOR, "down": MOMENTUM_DOWN_COLOR, "stable": MOMENTUM_STABLE_COLOR,
    }[category]

    w1_count = _momentum_w1_count(count_arrow)
    if w1_count is not None and w1_count < MOMENTUM_MIN_W1_COUNT:
        return f"{glyph} base trop faible", MOMENTUM_NEUTRAL_COLOR, glyph

    try:
        median_missing = recentring_median is None or pd.isna(recentring_median)
    except (TypeError, ValueError):
        median_missing = recentring_median is None
    if median_missing:
        # The quantified clause depends entirely on the median (corpus-drift
        # correction) -- omit it rather than fail or imply a correction that
        # was never applied. The classification (glyph/colour) is still real.
        return glyph, color, glyph

    try:
        incomplete = any(
            v is None or pd.isna(v) for v in (w1_share, w2_share, recentring_median)
        )
    except (TypeError, ValueError):
        incomplete = True
    if incomplete or float(w1_share) == 0 or float(recentring_median) == 0:
        return "—", MOMENTUM_NEUTRAL_COLOR, None

    delta_pct = (float(w2_share) / float(w1_share) / float(recentring_median) - 1) * 100
    return f"{glyph} {_signed_pct_no_decimal(delta_pct)}", color, glyph


def momentum_display(row: Any, facts: Any) -> tuple[str, str, str | None]:
    """
    Thin wrapper over `momentum_display_values()` for the PARTNER grain --
    UNCHANGED SIGNATURE (pass-6 re-open: page 9 already calls
    `momentum_display(partner_row, mf_row)` positionally; this must keep
    working with zero page edits). `row` carries mom_category (falls back to
    mom_class if a caller ever hands this the narrower shape) /
    mom_w1_share / mom_w2_share / mom_count_arrow (one ptn_summary row: dict,
    pandas Series, or anything attribute-accessible); `facts` carries
    recentring_median (one ptn_mom_facts row, same shapes).

    A NEW caller at a different grain (topics_zero_fill / subfields_zero_fill
    -- no mom_category/mom_count_arrow columns there) should call
    `momentum_display_values()` directly instead of building a fake
    ptn_summary-shaped `row` just to reach this wrapper.
    """
    category = _field(row, "mom_category")
    try:
        if category is None or pd.isna(category):
            category = _field(row, "mom_class")
    except (TypeError, ValueError):
        pass
    return momentum_display_values(
        category=category,
        w1_share=_field(row, "mom_w1_share"),
        w2_share=_field(row, "mom_w2_share"),
        recentring_median=_field(facts, "recentring_median"),
        count_arrow=_field(row, "mom_count_arrow"),
    )