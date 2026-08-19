# pages/2_🏭_Laboratoires.py
"""
Laboratoires — vue d'ensemble par structure interne et fiche détaillée par structure.

Pass 6 (worker P-LAB, BUILD_PLAN.md §3): mini-fiche rebuild (P7/VIZ_SPEC_pass6 §6),
#25 "In list" empty-column fix, #26/#30 doctype/domaine side-by-side pair with ONE
shared legend and ONE toggle (VIZ_SPEC_pass6 §1.5/§3.1), #29 wordcloud 3-variant +
zoom, #33 FWCI pair rebuild (VIZ_SPEC_pass6 §3.3), #34 lab tops (30-deep, 4 tables),
#8/#9 "Profil ODD d'un laboratoire" moved in from Portefeuille thématique (P11 method
comparison), narrative sweep per docs/NARRATIVE_CONTRACT_pass6.md §2.3.

Sections:
1. Vue d'ensemble par structure interne (table, type filter, hors-liste checkbox).
2. Analyse d'une structure : mini-fiche (identité / indicateurs clés / nuage de mots),
   répartition globale + annuelle (doctype ↔ domaine), distribution du FWCI par champ,
   détail par sous-champ, profil ODD, tops laboratoire (partenaires + auteur·es).
"""
from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# Local imports
from lib.data_cache import get_structures_df, get_topics_df, get_pubs_slim, get_corpus_facts_df, DATA_DIR
from lib.app_config import get_app_config
from lib.thematic import excluded_counts_from_facts
from lib import controls, exports
from lib.overlay import overlay_bars, overlay_grouped_bars, GROUPED_BARS_HOWTOREAD_FR
from lib.ranked import ranked_table
from lib.lazy import read_keyed
from lib.links import openalex_url, link_icon_html
from lib.countries_fr import country_label
from lib.helpers import (
    # Constants
    YEARS, DOMAIN_ORDER_DISPLAY, DOMAIN_EMOJI,
    UNCLASSIFIED_DOMAIN_ID,
    DOCTYPE_COLORS, DOCTYPE_ORDER_FR, DOCTYPE_LABEL_FR, NEUTRAL_GREY, NA_MARK,
    conference_blob_caveat, render_excluded_disclosure,
    window_label,
    # Taxonomy
    init_taxonomy, get_domain_id_to_name, get_field_id_to_name,
    get_field_order_by_domain, get_subfields_for_field,
    get_subfield_id_to_name, get_subfield_id_to_domain_id,
    get_field_id_to_domain_id,
    # Colors
    get_domain_color, get_field_color,
    # Parsers
    safe_int, safe_float,
    parse_pipe_int_list, parse_pipe_float_list,
    parse_positional_field_counts,
    parse_fwci_boxplot_blob, parse_year_domain_blob,
    # Utilities
    pad_dataframe, fr_int, fr_pct, lazy_slice_csv_bytes,
)

# ============================================================================
# PAGE CONFIG
# ============================================================================

st.set_page_config(page_title="Lab View", page_icon="🏭", layout="wide")

# Initialize taxonomy cache
init_taxonomy(get_topics_df())

# ============================================================================
# CONSTANTS
# ============================================================================

# D56 — structures OpenAlex reports under UL that are absent from the client's
# curated list. Selectable and inspectable, but flagged and out of the aggregates.
HORS_LISTE_FLAG = "⚠ hors liste"

# Bridges lib.helpers' TWO doctype vocabularies: the raw ul_pubs.type / DOCTYPE_ORDER_FR
# keys used by the work-level recompute below, and the EN blob-positional keys
# DOCTYPE_COLORS (and the legacy "Pubs per type" blob) are keyed by. Both already exist
# in lib.helpers (S-LIB, pass 6) -- this is the lookup between them, never a new colour.
_RAW_TYPE_TO_BLOB_LABEL = {
    "article": "Articles", "conference-paper": "Conference papers",
    "book-chapter": "Book chapters", "book": "Books", "review": "Reviews",
}

# Page-local FR labels for a handful of Structure-type codes shown on the mini-fiche
# identity card (small, closed vocabulary -- ul_labs.parquet's own `allowed:` list).
_STRUCTURE_TYPE_FR = {
    "lab": "Laboratoire", "other": "Autre", "experimental": "Expérimental", "department": "Pôle",
}

# Official UN French SDG titles (a controlled, published vocabulary — same list used
# verbatim on pages/4_*.py's own ODD panel; duplicated here rather than imported
# because importing another PAGE module would re-execute its whole Streamlit script).
SDG_NAMES = {
    1: "Pas de pauvreté", 2: "Faim « zéro »", 3: "Bonne santé et bien-être",
    4: "Éducation de qualité", 5: "Égalité entre les sexes",
    6: "Eau propre et assainissement", 7: "Énergie propre et d'un coût abordable",
    8: "Travail décent et croissance économique",
    9: "Industrie, innovation et infrastructure", 10: "Inégalités réduites",
    11: "Villes et communautés durables", 12: "Consommation et production responsables",
    13: "Mesures relatives à la lutte contre les changements climatiques",
    14: "Vie aquatique", 15: "Vie terrestre",
    16: "Paix, justice et institutions efficaces",
}

# ============================================================================
# DATA LOADING
# ============================================================================

df_all_structures = get_structures_df()
structure_types = df_all_structures["Structure type"].dropna().unique().tolist()

if df_all_structures.empty:
    st.error("Aucune structure trouvée dans les données.")
    st.stop()

# `in_client_list` is a nullable boolean; a missing value means curated (v1 shape).
IS_CURATED = df_all_structures["in_client_list"].fillna(True).astype(bool)


def is_curated(row: pd.Series) -> bool:
    val = row.get("in_client_list", True)
    return True if pd.isna(val) else bool(val)


def structure_label(row: pd.Series) -> str:
    """Selector label: hors-liste structures carry a visible flag (D56)."""
    name = str(row["Structure name"])
    return name if is_curated(row) else f"{name}  [{HORS_LISTE_FLAG}]"


def _field(value) -> str:
    """Never print pandas' <NA> at the client."""
    return "—" if pd.isna(value) or str(value).strip() in ("", "<NA>", "None") else str(value)


# ============================================================================
# PASS 6 -- generic cached loader for the new lab-grain tables (page-local, same
# pattern as pages/4_*.py's own _load_table: fence = pages/ + lib.{controls,exports,
# lazy} only, no lib/data_cache.py edit).
# ============================================================================

@st.cache_data
def _load_table(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / f"{name}.parquet")


@st.cache_data
def _lab_set(table_name: str) -> frozenset:
    """Which `lab` keys a pass-6 lab-grain table actually covers. These NEW tables
    (sdg_lab_methods, lab_top_partners, lab_top_authors, lab_wordcloud, lab_works)
    are built over the 69 curated 'lab'-type structures + NO LAB only (data_contract.yaml
    row_grain note) -- Pole/hors-liste rows are out of scope. Checked before rendering a
    panel so an unsupported structure gets an honest disclosure, never a crash or a
    fabricated row."""
    df = _load_table(table_name)
    return frozenset(df["lab"].unique()) if "lab" in df.columns else frozenset()


@st.cache_data
def _lab_works_slice(lab_key: str) -> pd.DataFrame:
    """Per-lab lazy slice of lab_works.parquet (predicate pushdown via
    lib.lazy.read_keyed) -- the source for every per-indicator download on the
    mini-fiche (#32) and the FWCI-médian tile. Empty frame when the structure is
    outside the pass-6 lab_works universe (Pole/hors-liste rows) -- the global file
    is never loaded resident just to serve one structure."""
    path = DATA_DIR / "lab_works.parquet"
    if not path.exists():
        return pd.DataFrame()
    return read_keyed(path, "lab", lab_key)


# ============================================================================
# D52 — RECOMPUTE PER-STRUCTURE COUNTS WITHOUT CONFERENCE PAPERS
# ============================================================================
# `ul_labs` is a table of pre-aggregated blobs and cannot be re-filtered by
# document type. The work-level file can: `ul_pubs.Labs` / `.Poles` name the
# structures crediting each work, and a straight recomputation on it reproduces
# the deployed `Pubs total` exactly for every curated structure (verified: 0
# mismatches over 79 rows). Hors-liste structures are NOT named in those columns,
# so their counts stay blob-based and the caption says so.

RECOMPUTED_COLUMNS = [
    "Pubs total", "Pubs PPtop10% (subfield)", "Pubs PPtop1% (subfield)",
    "Pubs ISITE (In_ISITE)", "Pubs international", "Pubs with company",
    "Works excluded (thin stratum)",
]


@st.cache_data
def structure_work_index() -> pd.DataFrame:
    """(source, structure, work_id) — one row per structure crediting a work."""
    pubs = get_pubs_slim()
    frames = []
    for source, column in (("labs", "Labs"), ("poles", "Poles")):
        part = pubs[["work_id", column, "is_conference"]].copy()
        part["structure"] = part[column].fillna("").str.split(" | ", regex=False)
        part = part.explode("structure")
        part["structure"] = part["structure"].str.strip()
        part = part[part["structure"] != ""]
        part["source"] = source
        frames.append(part[["source", "structure", "work_id", "is_conference"]])
    return pd.concat(frames, ignore_index=True)


@st.cache_data
def recomputed_structure_counts(include_conference: bool) -> pd.DataFrame:
    """
    Per-structure headline counts recomputed from the work-level table.
    Indexed by (source, structure). D53: citation counts skip works whose
    indicator_status != 'computed' (their PPtop flags are null, never False).
    """
    index = structure_work_index()
    if not include_conference:
        index = index[~index["is_conference"].fillna(False)]
    flags = ["In_ISITE", "Is_international", "Is_company",
             "PPtop10_FR", "PPtop1_FR", "indicator_status"]
    pubs = get_pubs_slim().set_index("work_id")[flags]
    joined = index.join(pubs, on="work_id")
    joined["_computed"] = joined["indicator_status"].eq("computed")
    grouped = joined.groupby(["source", "structure"])
    out = pd.DataFrame({
        "Pubs total": grouped.size(),
        "Pubs PPtop10% (subfield)": grouped["PPtop10_FR"].sum(min_count=0),
        "Pubs PPtop1% (subfield)": grouped["PPtop1_FR"].sum(min_count=0),
        "Pubs ISITE (In_ISITE)": grouped["In_ISITE"].sum(min_count=0),
        "Pubs international": grouped["Is_international"].sum(min_count=0),
        "Pubs with company": grouped["Is_company"].sum(min_count=0),
        "Works excluded (thin stratum)": grouped.size() - grouped["_computed"].sum(),
    })
    return out.astype(float)


def structure_source(row: pd.Series) -> str:
    """Which work-level column names this structure."""
    return "poles" if row.get("Structure type") == "department" else "labs"


def apply_conference_filter(df: pd.DataFrame, include_conference: bool) -> tuple[pd.DataFrame, int]:
    """
    Return (structures with recomputed counts, number of rows left untouched).
    Untouched rows are the hors-liste structures the work-level table cannot name.
    """
    if include_conference:
        return df, 0
    counts = recomputed_structure_counts(False)
    out = df.copy()
    untouched = 0
    for idx, row in out.iterrows():
        key = (structure_source(row), row["Structure name"])
        if key in counts.index:
            out.loc[idx, RECOMPUTED_COLUMNS] = counts.loc[key, RECOMPUTED_COLUMNS].values
        else:
            untouched += 1
    return out, untouched


# ============================================================================
# PASS 6 (#26/#30/#31) -- per-year x per-doctype / per-domain breakdown, from
# the SAME work-level index the D52 recompute already uses. Root-cause fix for
# #25's sibling gap (no "Pubs per year per type" blob ever existed): rather than
# add a new precomputed column (pipeline/data — outside this stream's fence),
# the page recomputes it live from data it already loads, honouring the
# conference toggle EXACTLY (no "cannot recompute" caveat needed for this panel).
# ============================================================================

def structure_year_breakdown(source: str, structure: str, include_conference: bool) -> pd.DataFrame | None:
    """
    Per-work (publication_year, type, primary_domain_id, In_ISITE) rows for one
    structure. Returns None when the structure's name is not found in the
    Labs/Poles blob columns (hors-liste structures the work-level table cannot
    name — the SAME gap apply_conference_filter() already discloses).
    """
    index = structure_work_index()
    subset = index[(index["source"] == source) & (index["structure"] == structure)]
    if subset.empty:
        return None
    if not include_conference:
        subset = subset[~subset["is_conference"].fillna(False)]
    pubs = get_pubs_slim().set_index("work_id")[
        ["type", "publication_year", "primary_domain_id", "In_ISITE"]
    ]
    joined = subset.join(pubs, on="work_id")
    joined["primary_domain_id"] = pd.to_numeric(
        joined["primary_domain_id"], errors="coerce"
    ).fillna(UNCLASSIFIED_DOMAIN_ID).astype(int)
    return joined


def _series_totals_by_year(joined: pd.DataFrame, key_col: str, keys) -> tuple[dict, dict]:
    """{key: [total per year]}, {key: [isite total per year]} — one pass per key."""
    totals, isite = {}, {}
    for key in keys:
        sub = joined[joined[key_col] == key]
        by_year = sub.groupby("publication_year").size()
        isite_by_year = sub.groupby("publication_year")["In_ISITE"].sum()
        totals[key] = [int(by_year.get(y, 0)) for y in YEARS]
        isite[key] = [int(isite_by_year.get(y, 0)) for y in YEARS]
    return totals, isite


# ============================================================================
# LAB-SPECIFIC TABLE BUILDERS
# ============================================================================

def build_field_distribution_table(row: pd.Series, pubs_total: int) -> pd.DataFrame:
    """
    Build table for field distribution bar chart with ISITE overlay.
    Returns DataFrame ordered by domain.
    """
    df_total = parse_positional_field_counts(row.get("Pubs per field", ""))
    df_isite = parse_positional_field_counts(row.get("ISITE pubs per field", ""))

    if df_total.empty:
        return pd.DataFrame()

    df = df_total.copy()
    if not df_isite.empty:
        df = df.merge(
            df_isite[["field_id", "count"]].rename(columns={"count": "isite_count"}),
            on="field_id", how="left"
        )
    else:
        df["isite_count"] = 0

    df["isite_count"] = df["isite_count"].fillna(0).astype(int)
    pubs_total = max(1, pubs_total)
    df["share"] = df["count"] / pubs_total
    df["isite_share"] = df["isite_count"] / pubs_total

    return df


def build_fwci_whisker_table(row: pd.Series) -> pd.DataFrame:
    """
    Build table for FWCI whisker plot with counts.
    Returns DataFrame ordered by domain, including ALL fields (PF-3: every field
    must enter the axis regardless of count, VIZ_SPEC_pass6 §3.3).
    """
    df = parse_fwci_boxplot_blob(row.get("FWCI boxplot per field id (centiles 0,10,25,50,75,90,100)", ""))

    if df.empty:
        field_order = get_field_order_by_domain()
        id2name = get_field_id_to_name()
        id2dom = get_field_id_to_domain_id()
        dom2name = get_domain_id_to_name()
        rows = []
        for field_id in field_order:
            if field_id not in id2name:
                continue
            dom_id = id2dom.get(field_id, 0)
            rows.append({
                "field_id": field_id,
                "field_name": id2name[field_id],
                "p0": np.nan, "p10": np.nan, "p25": np.nan, "p50": np.nan,
                "p75": np.nan, "p90": np.nan, "p100": np.nan,
                "count": 0,
                "domain_id": dom_id,
                "domain_name": dom2name.get(dom_id, "Other"),
                "color": get_field_color(field_id),
            })
        df = pd.DataFrame(rows)

    # Add counts from Pubs per field (raw work count — independent of whether an
    # indicator was computed; #33 root cause was conflating this with p50==NaN).
    df_counts = parse_positional_field_counts(row.get("Pubs per field", ""))
    if not df_counts.empty:
        count_map = dict(zip(df_counts["field_id"], df_counts["count"]))
        df["count"] = df["field_id"].map(count_map).fillna(0).astype(int)
    else:
        if "count" not in df.columns:
            df["count"] = 0

    return df


def build_subfield_table(row: pd.Series, pubs_total: int) -> pd.DataFrame:
    """
    Build detailed subfield table with counts, ratios vs UL, and FWCI.
    Returns DataFrame with all subfields that have count > 0.
    """
    sub2name = get_subfield_id_to_name()
    sub2dom = get_subfield_id_to_domain_id()
    field2name = get_field_id_to_name()
    dom2name = get_domain_id_to_name()

    all_rows = []

    for field_id in range(11, 37):
        count_pattern = f'Pubs per subfield within .* \\(id: {field_id}\\)'
        ratio_pattern = f'Ratio against UL.*\\(id: {field_id}\\)'
        fwci_pattern = f'FWCI per subfield within .* \\(id: {field_id}\\)'

        count_cols = [c for c in row.index if re.match(count_pattern, c)]
        ratio_cols = [c for c in row.index if re.match(ratio_pattern, c)]
        fwci_cols = [c for c in row.index if re.match(fwci_pattern, c)]

        if not count_cols:
            continue

        counts = parse_pipe_int_list(row.get(count_cols[0], ""))
        ratios = parse_pipe_float_list(row.get(ratio_cols[0], "")) if ratio_cols else []
        fwcis = parse_pipe_float_list(row.get(fwci_cols[0], "")) if fwci_cols else []

        subfields = get_subfields_for_field(field_id)

        for i, sub_id in enumerate(subfields):
            count = counts[i] if i < len(counts) else 0
            if count <= 0:
                continue

            dom_id = sub2dom.get(sub_id, 0)
            dom_name = dom2name.get(dom_id, "Other")

            ratio_val = ratios[i] if i < len(ratios) else np.nan
            fwci_val = fwcis[i] if i < len(fwcis) else np.nan

            all_rows.append({
                "subfield_id": sub_id,
                "Sous-champ": sub2name.get(sub_id, f"Subfield {sub_id}"),
                "Champ": field2name.get(field_id, f"Field {field_id}"),
                "Domaine": dom_name,
                "Domain marker": f"{DOMAIN_EMOJI.get(dom_name, '⬜')} {dom_name}",
                "count": count,
                "share_of_lab": count / max(1, pubs_total),
                "ratio_vs_ul": ratio_val,
                "fwci": fwci_val,
            })

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    return df.sort_values("count", ascending=False).reset_index(drop=True)


def parse_internal_collabs_blob(blob: str) -> pd.DataFrame:
    """
    Parse 'Top 10 internal lab/other collabs (type,count,ratio,FWCI)' blob.
    Format: 'Name (type, count ; ratio ; fwci) | ...'

    Items are found by regex and the inner values accept ';' or '|', so the blob
    cannot be shredded by a builder that changes the inner separator (that is
    exactly what emptied the FWCI whisker plot).
    """
    if pd.isna(blob) or not str(blob).strip() or str(blob).strip().lower() == "none":
        return pd.DataFrame(columns=["name", "type", "count", "ratio", "fwci"])

    rows = []
    pattern = re.compile(
        r"([^|()]+?)\s*\((lab|other),\s*(\d+)\s*[;|]\s*([\d.]+)\s*[;|]\s*([\d.]+)\)",
        re.IGNORECASE,
    )

    for m in pattern.finditer(str(blob)):
        rows.append({
            "name": m.group(1).strip(),
            "type": m.group(2).lower(),
            "count": safe_int(m.group(3)),
            "ratio": safe_float(m.group(4)),
            "fwci": safe_float(m.group(5)),
        })

    return pd.DataFrame(rows)


# ============================================================================
# PASS 6 (#29) -- wordcloud: 3 variants, domain-coloured, cached PNG bytes
# ============================================================================

@st.cache_data
def _term_domain_map() -> dict:
    """subfield_name / topic_name / keyword -> domain_id, built once from the
    taxonomy (all_topics.parquet) for the wordcloud's colour-by-domain rule
    (VIZ_SPEC_pass6 §5.2). A keyword can appear under several topics/domains; it
    is coloured by whichever domain its most frequent parent topic carries —
    colour-only, never a claim of a single true domain for a keyword."""
    tdf = get_topics_df()
    mapping: dict = {}
    for _, r in tdf[["subfield_name", "domain_id"]].dropna().drop_duplicates("subfield_name").iterrows():
        mapping[r["subfield_name"]] = int(r["domain_id"])
    for _, r in tdf[["topic_name", "domain_id"]].dropna().drop_duplicates("topic_name").iterrows():
        mapping.setdefault(r["topic_name"], int(r["domain_id"]))
    kw = tdf[["keywords", "domain_id"]].dropna(subset=["keywords"]).copy()
    kw["keyword"] = kw["keywords"].str.split("|")
    kw = kw.explode("keyword")
    kw["keyword"] = kw["keyword"].str.strip()
    kw = kw[kw["keyword"] != ""]
    counts = kw.groupby(["keyword", "domain_id"]).size().reset_index(name="n")
    top = counts.sort_values("n", ascending=False).drop_duplicates("keyword")
    for _, r in top.iterrows():
        mapping.setdefault(r["keyword"], int(r["domain_id"]))
    return mapping


@st.cache_data
def _lab_wordcloud_slice(lab_key: str, level: str) -> pd.DataFrame:
    df = _load_table("lab_wordcloud")
    out = df[(df["lab"] == lab_key) & (df["level"] == level)]
    return out.sort_values("weight", ascending=False)


@st.cache_data(show_spinner=False, max_entries=64)
def render_lab_wordcloud_png(lab_key: str, level: str, width: int, height: int, max_words: int) -> bytes | None:
    """
    VIZ_SPEC_pass6 §5.4 fix: cached (keyed by every rendering parameter), returns
    PNG BYTES (never a resident matplotlib figure — the pass-5 leak this replaces
    never called plt.close(), pinning one figure per render for the session).
    """
    df = _lab_wordcloud_slice(lab_key, level)
    if df.empty:
        return None
    try:
        from wordcloud import WordCloud
        from PIL import Image
    except ImportError:
        return None

    freqs = dict(zip(df["term"], df["weight"]))
    domain_map = _term_domain_map()

    def color_func(word, *args, **kwargs):
        dom = domain_map.get(word)
        return get_domain_color(dom) if dom is not None else NEUTRAL_GREY

    wc = WordCloud(
        width=width, height=height, max_words=max_words, background_color="white",
        prefer_horizontal=0.9, relative_scaling=0.5, min_font_size=9,
    )
    wc.generate_from_frequencies(freqs)
    wc.recolor(color_func=color_func)

    buf = io.BytesIO()
    Image.fromarray(wc.to_array()).save(buf, format="PNG")
    return buf.getvalue()


# ============================================================================
# PLOTLY CHART BUILDERS
# ============================================================================

def plot_global_breakdown_h(categories, totals, isite, colors, isite_on: bool) -> go.Figure:
    """
    LEFT panel of the #26/#30 pair: one horizontal bar per category, sorted by
    volume desc, direct end labels, NO legend (the y-axis labels name the
    categories) — VIZ_SPEC_pass6 §3.1. Uses the UNCHANGED `overlay_bars()`
    (one bar = one entity, §1.6).
    """
    order = sorted(range(len(categories)), key=lambda i: totals[i], reverse=True)
    cats = [categories[i] for i in order]
    tot = [totals[i] for i in order]
    ist = [isite[i] for i in order]
    cols = [colors[i] for i in order]

    fig = overlay_bars(
        categories=cats, totals=tot, isite=ist, colors=cols,
        isite_on=isite_on, orientation="h", value_mode="counts",
    )
    for cat, t in zip(cats, tot):
        fig.add_annotation(
            x=t, y=cat, text=fr_int(t), showarrow=False,
            xanchor="left", xshift=8, yanchor="middle",
            font=dict(size=12, color="#3A3F44"),
        )
    max_t = max(tot) if tot else 1
    fig.update_layout(
        showlegend=False,
        xaxis=dict(title="", showgrid=True, gridcolor="#D9DDE2", range=[0, max_t * 1.18]),
        yaxis=dict(autorange="reversed", title=""),
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        margin=dict(t=34, l=10, r=70, b=44), bargap=0.35,
        height=max(260, 46 * len(cats)),
    )
    return fig


def plot_annual_breakdown_grouped(groups, series, labels, colors, totals, isite, isite_on: bool) -> go.Figure:
    """RIGHT panel of the #26/#30 pair: the grouped grammar (VIZ_SPEC_pass6 §1.5),
    with its OWN Plotly legend hidden — the shared HTML chip strip is the ONE
    legend for the pair."""
    fig = overlay_grouped_bars(
        groups=groups, series=series, labels=labels, colors=colors,
        totals=totals, isite=isite, isite_on=isite_on,
    )
    fig.update_layout(
        showlegend=False, height=380, margin=dict(t=30, l=10, r=10, b=40),
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        yaxis=dict(title="Publications (nombre)"),
    )
    return fig


def render_chip_legend(items: list[tuple[str, str]]) -> None:
    """Shared HTML chip-strip legend for the #26/#30 pair (VIZ_SPEC_pass6 §3.1) —
    ONE legend for TWO figures, both rendered with showlegend=False."""
    chips = "".join(
        f'<span style="display:inline-flex;align-items:center;margin-right:14px;">'
        f'<span style="width:12px;height:12px;background:{hexcol};border-radius:3px;'
        f'margin-right:6px;"></span>'
        f'<span style="font-size:12px;color:#3A3F44;">{label}</span></span>'
        for label, hexcol in items
    )
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;gap:2px;margin:6px 0 4px 0;">{chips}</div>',
        unsafe_allow_html=True,
    )


def render_breakdown_pair(row: pd.Series, selected_structure: str, source_key: str,
                           include_conference: bool, isite_overlay_on: bool) -> None:
    """
    The #26/#30/#31 side-by-side pair: ONE toggle switches BOTH the global
    (left) and annual (right) charts between type-de-document and domaine.
    Primary path: recomputed live from the work-level index (structure_year_
    breakdown), honouring the conference toggle exactly. Fallback (hors-liste /
    Pole structures the work-level table cannot name): the pre-aggregated
    blobs, domain-only, no ISITE-by-year decomposition — disclosed, not hidden.
    """
    breakdown_pick = st.segmented_control(
        "Découpage", ["Types de document", "Domaines"],
        default="Types de document", required=True, key="lab_breakdown_dim",
    )
    is_doctype = breakdown_pick == "Types de document"

    joined = structure_year_breakdown(source_key, selected_structure, include_conference)
    years_str = [str(y) for y in YEARS]

    col_left, col_right = st.columns([1.00, 1.15])

    if joined is not None:
        if is_doctype:
            keys = DOCTYPE_ORDER_FR
            labels = DOCTYPE_LABEL_FR
            colors = {k: DOCTYPE_COLORS[_RAW_TYPE_TO_BLOB_LABEL[k]] for k in keys}
            totals, isite = _series_totals_by_year(joined, "type", keys)
        else:
            keys = DOMAIN_ORDER_DISPLAY
            dom_names = get_domain_id_to_name()
            labels = {k: dom_names.get(k, str(k)) for k in keys}
            colors = {k: get_domain_color(k) for k in keys}
            totals, isite = _series_totals_by_year(joined, "primary_domain_id", keys)

        global_totals = [sum(totals[k]) for k in keys]
        global_isite = [sum(isite[k]) for k in keys]
        global_labels = [labels[k] for k in keys]
        global_colors = [colors[k] for k in keys]

        with col_left:
            st.markdown("**Répartition globale**")
            fig_left = plot_global_breakdown_h(global_labels, global_totals, global_isite,
                                                global_colors, isite_overlay_on)
            st.plotly_chart(fig_left, use_container_width=True)
        with col_right:
            st.markdown("**Répartition annuelle**")
            fig_right = plot_annual_breakdown_grouped(years_str, keys, labels, colors,
                                                        totals, isite, isite_overlay_on)
            st.plotly_chart(fig_right, use_container_width=True)

        render_chip_legend(list(zip(global_labels, global_colors)))
        if isite_overlay_on:
            st.caption(f":grey[{GROUPED_BARS_HOWTOREAD_FR}]")

        _export_df = pd.DataFrame({
            "Catégorie": [labels[k] for k in keys for _ in YEARS],
            "Année": years_str * len(keys),
            "Publications": [v for k in keys for v in totals[k]],
            "dont I-SITE": [v for k in keys for v in isite[k]],
        })
        exports.attach_download(
            st, _export_df, "lab-overview", "breakdown-annuel", _EXPORT_STATE,
            entity=("l", selected_structure),
        )
        return

    # --- Fallback: structure absent from the work-level Labs/Poles columns -----
    st.caption(
        ":grey[La table au niveau des travaux ne nomme pas cette structure : la "
        "répartition ci-dessous vient des totaux pré-agrégés, sans décomposition "
        "I-SITE par année, toujours articles de conférence inclus.]"
    )
    if is_doctype:
        doctype_counts = parse_pipe_int_list(
            row.get("Pubs per type (articles | book chapters | books | reviews | preprints)", "")
        )
        blob_labels = ["Articles", "Book chapters", "Books", "Reviews", "Preprints", "Conference papers"]
        pairs = [(lbl, cnt) for lbl, cnt in zip(blob_labels, doctype_counts) if lbl != "Preprints"]
        cats = [DOCTYPE_LABEL_FR.get(
            {v: k for k, v in _RAW_TYPE_TO_BLOB_LABEL.items()}.get(lbl, lbl), lbl) for lbl, _ in pairs]
        tots = [cnt for _, cnt in pairs]
        cols = [DOCTYPE_COLORS.get(lbl, NEUTRAL_GREY) for lbl, _ in pairs]
        with col_left:
            st.markdown("**Répartition globale**")
            fig_left = plot_global_breakdown_h(cats, tots, [0] * len(tots), cols, False)
            st.plotly_chart(fig_left, use_container_width=True)
        with col_right:
            st.info("Répartition annuelle par type indisponible pour cette structure.", icon="ℹ️")
        render_chip_legend(list(zip(cats, cols)))
    else:
        df_fields = build_field_distribution_table(row, safe_int(row.get("Pubs total", 0)))
        if not df_fields.empty:
            dom_rollup = df_fields.groupby("domain_id").agg(
                count=("count", "sum"), isite_count=("isite_count", "sum"),
            ).reset_index()
            dom_names = get_domain_id_to_name()
            cats = [dom_names.get(d, str(d)) for d in dom_rollup["domain_id"]]
            cols = [get_domain_color(d) for d in dom_rollup["domain_id"]]
            with col_left:
                st.markdown("**Répartition globale**")
                fig_left = plot_global_breakdown_h(
                    cats, dom_rollup["count"].tolist(), dom_rollup["isite_count"].tolist(),
                    cols, isite_overlay_on,
                )
                st.plotly_chart(fig_left, use_container_width=True)
            render_chip_legend(list(zip(cats, cols)))
        df_year_dom = parse_year_domain_blob(row.get("Pubs per year per domain", ""))
        with col_right:
            st.markdown("**Répartition annuelle**")
            if df_year_dom.empty:
                st.info("Répartition annuelle indisponible pour cette structure.", icon="ℹ️")
            else:
                keys = DOMAIN_ORDER_DISPLAY
                dom_names = get_domain_id_to_name()
                labels = {k: dom_names.get(k, str(k)) for k in keys}
                colors = {k: get_domain_color(k) for k in keys}
                totals = {k: [] for k in keys}
                for y in YEARS:
                    for k in keys:
                        sub = df_year_dom[(df_year_dom["year"] == y) & (df_year_dom["domain_id"] == k)]
                        totals[k].append(int(sub["count"].sum()) if not sub.empty else 0)
                isite_zero = {k: [0] * len(YEARS) for k in keys}
                fig_right = plot_annual_breakdown_grouped(years_str, keys, labels, colors,
                                                            totals, isite_zero, False)
                st.plotly_chart(fig_right, use_container_width=True)


def _fr_float(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v):
        return NA_MARK
    return f"{float(v):.2f}".replace(".", ",")


_FWCI_PAIR_MARGIN_LEFT = dict(t=34, l=10, r=70, b=56)
_FWCI_PAIR_MARGIN_RIGHT = dict(t=34, l=10, r=20, b=56)


def plot_field_share_pair_left(df_fields: pd.DataFrame, isite_on: bool) -> go.Figure:
    """LEFT half of the #33 FWCI pair: 'Part de la production de la structure'.
    Same geometry as plot_fwci_whiskers's right half (PF-4 alignment); the
    gutter count is fixed to sit right next to the bar start, not at the far
    edge of the gutter (#33 'gutter volume too far from the bar start')."""
    n = len(df_fields)
    if n == 0:
        fig = go.Figure()
        fig.add_annotation(text="Aucune donnée", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    field_names = df_fields["field_name"].tolist()
    max_share = float(df_fields["share"].max() or 0.0) or 0.01
    gutter = max_share * 0.16

    fig = overlay_bars(
        categories=field_names, totals=df_fields["share"].tolist(),
        isite=df_fields["isite_share"].tolist(), colors=df_fields["color"].tolist(),
        isite_on=isite_on, orientation="h", value_mode="shares",
    )
    for field_name, cnt in zip(field_names, df_fields["count"]):
        fig.add_annotation(
            x=-gutter * 0.10, y=field_name, text=fr_int(cnt), showarrow=False,
            xanchor="right", yanchor="middle",
            font=dict(size=11, color="#3A3F44" if cnt else "#8C9196"),
        )

    fig.update_layout(
        title="Part de la production de la structure",
        xaxis=dict(title="% des publications de la structure", tickformat=".0%",
                    range=[-gutter, max_share * 1.10], showgrid=True, gridcolor="#D9DDE2",
                    automargin=False),
        yaxis=dict(title="", tickfont=dict(size=12),
                    categoryorder="array", categoryarray=field_names,
                    range=[n - 0.5, -0.5]),
        showlegend=False, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        margin=_FWCI_PAIR_MARGIN_LEFT, height=max(460, 22 * n + 130),
    )
    return fig


def plot_fwci_whiskers(df_fwci: pd.DataFrame) -> go.Figure:
    """
    RIGHT half of the #33 FWCI pair: box+whisker per field, SAME field order as
    the left panel, y tick labels hidden (drawn once, on the left). Whisker =
    interdecile p10–p90 (#33: a single outlier field flattens all rows on a
    p0–p100 whisker); p0/p100 stay in the tooltip. Root-cause gate for #33's
    "fields with 0 pubs display bug": drawn iff p50 is a real value — a field
    with zero COMPUTED-indicator works has p50 == NaN (pipeline fix, S-DAT),
    never a fabricated flat "0.00" box.
    """
    field_names = df_fwci["field_name"].tolist()
    n = len(field_names)
    if n == 0:
        fig = go.Figure()
        fig.add_annotation(text="Aucune donnée", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    valid_p90 = df_fwci.loc[df_fwci["p50"].notna(), "p90"].dropna()
    xmax = float(valid_p90.max()) if not valid_p90.empty and valid_p90.max() > 0 else 5.0

    fig = go.Figure()
    # PF-3 anchor trace: every field enters the y axis regardless of whether it
    # has a computed indicator (VIZ_SPEC_pass6 §3.3, mechanic 1).
    fig.add_trace(go.Bar(
        x=[0] * n, y=field_names, orientation="h",
        marker_color="rgba(0,0,0,0)", showlegend=False, hoverinfo="skip", width=0.8,
    ))

    for _, row in df_fwci.iterrows():
        y = row["field_name"]
        color = row["color"]
        if pd.isna(row["p50"]):
            text = f"n = {fr_int(row['count'])} — indicateur non calculé"
            fig.add_annotation(
                x=0, y=y, text=text, showarrow=False, xanchor="left", xshift=6,
                yanchor="middle", font=dict(size=10, color="#8C9196"),
            )
            continue

        tooltip = (
            f"<b>{y}</b><br>n = {fr_int(row['count'])}<br>"
            f"Médiane : {_fr_float(row['p50'])}<br>"
            f"Q1–Q3 : {_fr_float(row['p25'])} – {_fr_float(row['p75'])}<br>"
            f"Interdécile p10–p90 : {_fr_float(row['p10'])} – {_fr_float(row['p90'])}<br>"
            f"Extrêmes (p0–p100) : {_fr_float(row['p0'])} – {_fr_float(row['p100'])}"
            "<extra></extra>"
        )
        if pd.notna(row["p10"]) and pd.notna(row["p90"]):
            fig.add_trace(go.Scatter(
                x=[row["p10"], row["p90"]], y=[y, y], mode="lines",
                line=dict(color=color, width=2), showlegend=False,
                hovertemplate=tooltip,
            ))
        if pd.notna(row["p25"]) and pd.notna(row["p75"]) and row["p75"] >= row["p25"]:
            fig.add_trace(go.Bar(
                x=[row["p75"] - row["p25"]], y=[y], base=row["p25"], orientation="h",
                marker=dict(color=color, opacity=0.3), width=0.6, showlegend=False,
                hovertemplate=tooltip,
            ))
        fig.add_trace(go.Scatter(
            x=[row["p50"]], y=[y], mode="markers",
            marker=dict(color=color, size=10, symbol="line-ns", line=dict(width=3, color=color)),
            showlegend=False, hovertemplate=tooltip,
        ))

    fig.add_vline(x=1, line_dash="dot", line_color="#B0B6BC")
    fig.update_layout(
        title="Distribution du FWCI (réf. France = 1)",
        xaxis=dict(title="FWCI (réf. France), interdécile p10–p90",
                    range=[0, xmax * 1.08], showgrid=True, gridcolor="#D9DDE2",
                    automargin=False),
        yaxis=dict(title="", showticklabels=False,
                    categoryorder="array", categoryarray=field_names,
                    range=[n - 0.5, -0.5]),
        showlegend=False, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        margin=_FWCI_PAIR_MARGIN_RIGHT, height=max(460, 22 * n + 130),
        barmode="overlay",
    )
    return fig


# ============================================================================
# PAGE LAYOUT
# ============================================================================

st.title("🏭 Laboratoires")
st.caption(
    "Cette page répond à : que porte chaque structure interne du site, en volume, "
    "en partenaires, en profil de citation et en thématiques ?"
)

# W5 chassis adoption (VIZ_SPEC 1.5 / 2.1 P-V1 inheritance): controls.sidebar() is a
# drop-in superset of the D52 toggle this page already rendered -- it calls the SAME
# lib.helpers.conference_toggle() under the SAME "include_conference" session-state
# key (see lib/controls.py's sidebar()), then wraps it with the perimeter selector,
# the artifact toggle and the snapshot badge. Parity-bound: the toggle's key, label
# and semantics are byte-for-byte unchanged.
_controls_state = controls.sidebar()
include_conference = _controls_state["include_conference"]
isite_overlay_on = _controls_state[controls.ISITE_OVERLAY_KEY]

# Disclosure strips (rev 3.1 R-A/R-B). No artifact markers on this page (entity-grain
# rows; VIZ_SPEC 2.1 says state is carried by these strips + export headers only).
controls.filtered_by_strip(page="laboratoires")
controls.ships_v2_strip()  # ships-v2 honest strip while the artifact toggle is ON
if _controls_state.get("perimeter_subset", "all") != "all":
    controls.perimeter_disclosure_strip()  # R-B: non-subset page, non-default perimeter

# Shared export state (W5 lib/exports.py, VIZ_SPEC 1.3): every panel button below reuses
# this one state -- current toggles + artifact_applied=False always (ships-v2: the
# toggle never actually recomputes this page's numbers, so the standard "applied" flag
# would lie in the export header -- rev 3.1 R-A).
_facts = get_corpus_facts_df()
_SNAPSHOT_DATE = str(_facts["snapshot_date"].iloc[0]) if len(_facts) else "?"
_EXPORT_STATE = exports.ExportState(
    snapshot=_SNAPSHOT_DATE,
    conf=include_conference,
    artifact=_controls_state[controls.ARTIFACT_TOGGLE_KEY],
    subset=_controls_state.get("perimeter_subset", "all"),
    artifact_applied=False,
)

# -----------------------------------------------------------------------------
# Section 1: Overview Table with Type Filter
# -----------------------------------------------------------------------------

st.subheader(f"Vue d'ensemble par structure interne ({window_label()})")

col_types, col_hors = st.columns([3, 2])

with col_types:
    selected_types = st.multiselect(
        "Filtrer par type de structure",
        options=structure_types,
        default=structure_types,
        key="structure_type_filter"
    )

with col_hors:
    # D56 — hors-liste structures are out of the aggregates and rankings by default.
    show_hors_liste = st.checkbox(
        f"Inclure les structures {HORS_LISTE_FLAG} dans ce tableau",
        value=bool(get_app_config()["show_hors_liste"]),
        key="show_hors_liste",
        help=(
            "Structures rattachées à l'Université de Lorraine par OpenAlex mais "
            "absentes de la liste curée du client. Elles restent toujours "
            "sélectionnables ci-dessous, mais recoupent le périmètre curé : elles "
            "sont exclues du classement par défaut."
        ),
    )

# Filter data
df_filtered = df_all_structures[df_all_structures["Structure type"].isin(selected_types)].copy()
n_hors_liste = int((~df_filtered["in_client_list"].fillna(True)).sum())
if not show_hors_liste:
    df_filtered = df_filtered[df_filtered["in_client_list"].fillna(True)]

if df_filtered.empty:
    st.warning("Aucune structure ne correspond aux filtres sélectionnés.")
else:
    df_filtered, n_untouched = apply_conference_filter(df_filtered, include_conference)

    summary = df_filtered[[
        "Structure name", "Structure type", "Pole", "Pubs total",
        "Pubs PPtop10% (subfield)", "Pubs PPtop1% (subfield)",
        "Pubs ISITE (In_ISITE)", "Pubs international", "Pubs with company",
        "in_client_list", "Works excluded (thin stratum)",
    ]].copy()

    summary["In list"] = np.where(
        summary["in_client_list"].fillna(True).astype(bool), "", HORS_LISTE_FLAG)

    summary = summary.rename(columns={
        "Structure name": "Structure",
        "Structure type": "Type",
        "Pubs total": "Publications",
        "Pubs PPtop10% (subfield)": "Top 10%",
        "Pubs PPtop1% (subfield)": "Top 1%",
        "Pubs ISITE (In_ISITE)": "Pubs ISITE",
    })

    # Percentages on a 0-100 scale.
    denominator = summary["Publications"].replace(0, np.nan)
    summary["% ISITE"] = summary["Pubs ISITE"] / denominator * 100
    summary["% international"] = summary["Pubs international"] / denominator * 100
    summary["% avec une entreprise"] = summary["Pubs with company"] / denominator * 100

    summary = summary.sort_values("Publications", ascending=False)

    # #25 fix (root cause, probe 2): "In list" is ONLY non-blank when hors-liste
    # rows are actually in the table -- with the checkbox OFF (default), every
    # visible row is curated and the column would render permanently empty. Drop
    # it from the rendered columns rather than ship an always-blank column; the
    # caption just below already discloses the excluded count.
    _column_order = [
        "Structure", "Type", "Pole", "Publications", "Top 10%", "Top 1%",
        "Pubs ISITE", "% ISITE", "% international", "% avec une entreprise",
    ]
    _column_config = {
        "Structure": st.column_config.TextColumn("Structure"),
        "Type": st.column_config.TextColumn("Type"),
        "Pole": st.column_config.TextColumn("Pôle"),
        "Publications": st.column_config.NumberColumn("Publications", format="%.0f"),
        "Top 10%": st.column_config.NumberColumn("Top 10%", format="%.0f"),
        "Top 1%": st.column_config.NumberColumn("Top 1%", format="%.0f"),
        "Pubs ISITE": st.column_config.NumberColumn("Pubs ISITE", format="%.0f"),
        "% ISITE": st.column_config.ProgressColumn("% ISITE", format="%.1f%%", min_value=0, max_value=100),
        "% international": st.column_config.NumberColumn("% international", format="%.1f%%"),
        "% avec une entreprise": st.column_config.NumberColumn("% avec une entreprise", format="%.1f%%"),
    }
    if show_hors_liste:
        _column_order.insert(1, "In list")
        _column_config["In list"] = st.column_config.TextColumn(
            "", help="⚠ hors liste : structure qu'OpenAlex rattache à l'Université "
                     "de Lorraine, absente de la liste tenue par l'établissement.")

    st.dataframe(
        summary, use_container_width=True, hide_index=True,
        column_order=_column_order, column_config=_column_config,
    )
    st.caption(
        "**Comment lire.** Une ligne par structure interne, triée par volume décroissant. "
        "Les colonnes en pourcentage rapportent chaque compte au total de la structure, "
        "jamais au total du site : deux structures de tailles très différentes s'y "
        "comparent donc sur leur profil, pas sur leur poids.  \n"
        "**Pourquoi cet indicateur.** C'est la vue d'entrée pour situer une structure "
        "avant d'ouvrir sa fiche : volume, part I-SITE, ouverture internationale et "
        "partenariats d'entreprise dans le même écran."
    )
    # Export-attach (VIZ_SPEC 1.3): the same `summary` dataframe the table above renders,
    # at the current filter state -- no single structure selected here, so no entity.
    exports.attach_download(st, summary, "lab-overview", "ranking-table", _EXPORT_STATE)

    if not show_hors_liste and n_hors_liste:
        st.caption(
            f":grey[{fr_int(n_hors_liste)} structure(s) {HORS_LISTE_FLAG} exclue(s) de "
            "ce classement — sélectionnables dans l'analyse ci-dessous.]"
        )
    if not include_conference:
        st.caption(
            ":grey[Effectifs recalculés **hors articles de conférence** à partir de la "
            "table au niveau des travaux."
            + (f" {fr_int(n_untouched)} structure(s) {HORS_LISTE_FLAG} n'ont pas pu être "
               "recalculées (la table au niveau des travaux ne les nomme pas) et "
               "restent donc avec conférences incluses.]"
               if n_untouched else "]")
        )
    # Corpus-level, NOT the sum over structures: a work credited to three labs
    # would otherwise be counted three times in the disclosure.
    render_excluded_disclosure(*excluded_counts_from_facts(include_conference))

st.divider()

# -----------------------------------------------------------------------------
# Section 2: Single Lab Analysis
# -----------------------------------------------------------------------------

st.subheader("Analyse d'une structure")

# D56 — curated structures first (alphabetical), flagged hors-liste ones after.
_curated = df_all_structures[IS_CURATED].sort_values("Structure name")
_hors_liste = df_all_structures[~IS_CURATED].sort_values("Structure name")
_options = pd.concat([_curated, _hors_liste])
_labels = {structure_label(r): r["Structure name"] for _, r in _options.iterrows()}

selected_label = st.selectbox("Sélectionner une structure", list(_labels), index=0)
selected_structure = _labels[selected_label]
row = df_all_structures.loc[df_all_structures["Structure name"] == selected_structure].iloc[0]
source_key = structure_source(row)

# D52 — the profile below reads the same recomputed counts as the table above.
_recomputable = True
if not include_conference:
    _counts = recomputed_structure_counts(False)
    _key = (source_key, selected_structure)
    if _key in _counts.index:
        row = row.copy()
        row[RECOMPUTED_COLUMNS] = _counts.loc[_key, RECOMPUTED_COLUMNS].values
    else:
        _recomputable = False

pubs_total = safe_int(row.get("Pubs total", 0))

if not is_curated(row):
    st.warning(
        f"**{HORS_LISTE_FLAG}** — cette structure est rattachée à l'Université de "
        "Lorraine par OpenAlex mais absente de la liste curée du client. Son "
        "périmètre est montré pour inspection ; elle est exclue des classements "
        "ci-dessus et ses travaux sont déjà comptés dans les structures curées "
        "auxquelles elle appartient aussi.",
        icon="⚠️",
    )

# =============================================================================
# MINI-FICHE (P7/#28, VIZ_SPEC_pass6 §6) — 3 content zones in 2 rows, ≈640 px.
# =============================================================================
st.markdown("---")

# --- Zone 1 : identité | indicateurs clés | nuage de mots (aperçu) ----------
col_identity, col_metrics, col_wc = st.columns([1.15, 1.00, 1.35])

with col_identity:
    ror_val = row.get("ROR")
    if pd.notna(ror_val) and str(ror_val).strip():
        ror_id = str(ror_val).strip()
        ror_html = (f"ROR : {ror_id} "
                     f"{link_icon_html(f'https://ror.org/{ror_id}', tooltip='Fiche ROR de la structure')}")
    else:
        ror_html = "ROR : —"

    oa_id = row.get("OpenAlex ID")
    oa_html = ""
    if pd.notna(oa_id) and str(oa_id).strip():
        oa_url = openalex_url(str(oa_id).strip(), scope="direct")
        oa_html = f"Voir dans OpenAlex {link_icon_html(oa_url)}"

    type_fr = _STRUCTURE_TYPE_FR.get(row.get("Structure type"), _field(row.get("Structure type")))
    st.markdown(
        f"""<div style="border:1px solid #E3E6EA;border-radius:8px;padding:12px 14px;">
        <div style="font-size:20px;font-weight:700;color:#3A3F44;">{selected_structure}</div>
        <div style="font-size:15px;color:#3A3F44;margin:2px 0 6px 0;">{_field(row.get('nom_complet'))}</div>
        <div style="font-size:14px;color:#5A5F66;">Pôle scientifique : {_field(row.get('Pole'))}
        &nbsp;&middot;&nbsp; Type : {type_fr}</div>
        <div style="font-size:14px;color:#5A5F66;margin-top:6px;">{ror_html}</div>
        <div style="font-size:14px;color:#5A5F66;margin-top:2px;">{oa_html}</div>
        </div>""",
        unsafe_allow_html=True,
    )
    st.caption(
        "**Comment lire.** L'identité de la structure telle que les sources la "
        "portent : sigle, nom complet, pôle scientifique, identifiant ROR, et le "
        "lien qui rouvre le décompte vivant dans OpenAlex. Un champ vide signale "
        "une information absente des fichiers sources, jamais une valeur nulle."
    )

_lw = _lab_works_slice(selected_structure)
_lw_available = not _lw.empty

with col_metrics:
    isite_count = safe_int(row.get("Pubs ISITE (In_ISITE)", 0))
    intl_count = safe_int(row.get("Pubs international", 0))
    pct_isite = (isite_count / pubs_total * 100) if pubs_total else np.nan
    pct_intl = (intl_count / pubs_total * 100) if pubs_total else np.nan

    if _lw_available:
        _fwci_vals = _lw.loc[_lw["indicator_status"] == "computed", "fwci_fr"].dropna()
        fwci_median = float(_fwci_vals.median()) if len(_fwci_vals) else np.nan
        fwci_n = int(len(_fwci_vals))
        _dl_pubs = lazy_slice_csv_bytes(DATA_DIR / "lab_works.parquet", "lab", selected_structure)
        _dl_isite = _lw[_lw["in_isite"].fillna(False)].to_csv(index=False).encode("utf-8-sig")
        _dl_fwci = _lw[_lw["indicator_status"] == "computed"].to_csv(index=False).encode("utf-8-sig")
        try:
            _intl_flags = get_pubs_slim().set_index("work_id")["Is_international"]
            _lw_intl = _lw.join(_intl_flags, on="work_id")
            _dl_intl = _lw_intl[_lw_intl["Is_international"].fillna(False)].to_csv(index=False).encode("utf-8-sig")
        except Exception:
            _dl_intl = None
    else:
        fwci_median, fwci_n = np.nan, 0
        _dl_pubs = _dl_isite = _dl_fwci = _dl_intl = None

    def _kpi_tile(col, label: str, value: str, subline: str, dl_bytes, fname: str) -> None:
        with col:
            with st.container(border=True):
                st.markdown(
                    f"<div style='font-size:22px;font-weight:700;color:#3A3F44;'>{value}</div>"
                    f"<div style='font-size:12px;color:#5A5F66;'>{label}</div>"
                    f"<div style='font-size:12px;color:#5A5F66;'>{subline}</div>",
                    unsafe_allow_html=True,
                )
                if dl_bytes is not None:
                    st.download_button(
                        "⬇", data=dl_bytes, file_name=fname, key=f"kpi_dl_{fname}",
                        help="Télécharger la liste de publications correspondante",
                    )

    st.markdown("**Indicateurs clés**")
    _slug = re.sub(r"[^A-Za-z0-9_-]+", "-", selected_structure).strip("-").lower() or "structure"
    r1c1, r1c2 = st.columns(2)
    _kpi_tile(r1c1, "Publications", fr_int(pubs_total), window_label(),
              _dl_pubs, f"{_slug}-publications.csv")
    _kpi_tile(r1c2, "Part I-SITE", fr_pct(pct_isite), f"{fr_int(isite_count)} travaux",
              _dl_isite, f"{_slug}-isite.csv")
    r2c1, r2c2 = st.columns(2)
    _kpi_tile(r2c1, "FWCI médian (réf. France)", _fr_float(fwci_median),
              f"n = {fr_int(fwci_n)}" if _lw_available else NA_MARK,
              _dl_fwci, f"{_slug}-fwci.csv")
    _kpi_tile(r2c2, "International", fr_pct(pct_intl), f"{fr_int(intl_count)} travaux",
              _dl_intl, f"{_slug}-international.csv")
    if not _lw_available:
        st.caption(
            ":grey[Téléchargements par indicateur indisponibles pour cette structure "
            "(hors périmètre des laboratoires curés).]"
        )

with col_wc:
    st.markdown("**Nuage de mots**")
    wc_level_pick = st.segmented_control(
        "Niveau", ["Sous-champs", "Topics", "Mots-clés"],
        default="Sous-champs", required=True, key=f"wc_level_{selected_structure}",
    )
    _wc_level_map = {"Sous-champs": "subfield", "Topics": "topic", "Mots-clés": "keyword"}
    _wc_level = _wc_level_map[wc_level_pick]
    _wc_png = render_lab_wordcloud_png(selected_structure, _wc_level, 560, 280, 60)
    if _wc_png is None:
        st.info("Aucune donnée disponible pour ce niveau et cette structure.", icon="ℹ️")
    else:
        st.image(_wc_png, use_container_width=True)
        st.caption("Taille = nombre de travaux ; couleur = domaine. Cliquez pour agrandir.")
        if st.button("⤢ Agrandir", key=f"wc_zoom_btn_{selected_structure}_{_wc_level}"):
            st.session_state[f"_wc_zoom_open_{selected_structure}"] = _wc_level

    _zoom_level = st.session_state.get(f"_wc_zoom_open_{selected_structure}")
    if _zoom_level:
        @st.dialog(f"Nuage de mots — {selected_structure}", width="large")
        def _wc_zoom_dialog(level=_zoom_level):
            big_png = render_lab_wordcloud_png(selected_structure, level, 1100, 550, 150)
            if big_png is None:
                st.info("Aucune donnée disponible pour ce niveau.")
            else:
                st.image(big_png, use_container_width=True)
            df_full = _lab_wordcloud_slice(selected_structure, level)
            if not df_full.empty:
                total_w = df_full["weight"].sum()
                disp = df_full[["term", "weight"]].rename(columns={"term": "Terme", "weight": "Travaux"})
                disp["Part"] = disp["Travaux"] / total_w * 100
                st.dataframe(
                    disp, use_container_width=True, hide_index=True,
                    column_config={
                        "Part": st.column_config.ProgressColumn("Part", format="%.1f%%", min_value=0, max_value=100),
                    },
                )
                exports.attach_download(
                    st, disp, "lab-overview", f"wordcloud-{level}", _EXPORT_STATE,
                    entity=("l", selected_structure),
                )
            if st.button("Fermer", key=f"wc_zoom_close_{selected_structure}"):
                st.session_state.pop(f"_wc_zoom_open_{selected_structure}", None)
                st.rerun()
        _wc_zoom_dialog()

if not include_conference:
    conference_blob_caveat("Ce nuage de mots")

render_excluded_disclosure(row.get("Works excluded (thin stratum)"), pubs_total)

st.markdown("---")

# --- Declared-empty structures: an explicit empty state beats five empty charts ---
if pubs_total <= 0:
    st.info(
        f"**{selected_structure}** n'a aucune publication dans le corpus ({window_label()}) : "
        "les graphiques ci-dessous n'ont donc rien à montrer. C'est un constat sur "
        "l'empreinte OpenAlex de la structure, pas une erreur de données.",
        icon="ℹ️",
    )
    st.stop()

# --- Zone 2 : répartition globale + annuelle (#26/#30/#31) ------------------
render_breakdown_pair(row, selected_structure, source_key, include_conference, isite_overlay_on)
st.caption(
    "**Comment lire.** Une barre par année. Le bouton bascule la décomposition entre "
    "type de document et domaine scientifique ; la légende suit la bascule. Teinte plus "
    "sombre : la part relevant du périmètre I-SITE.  \n"
    "**Pourquoi cet indicateur.** Une inflexion de volume se lit rarement seule : la "
    "même courbe peut venir d'un changement de pratique de publication, d'un "
    "recrutement ou de la fin d'un programme. La décomposition sépare ces lectures "
    "avant d'en tirer une conversation."
)

st.markdown("---")

# -----------------------------------------------------------------------------
# #33 FWCI pair -- share-of-structure (left) + FWCI distribution (right)
# -----------------------------------------------------------------------------
st.markdown("#### Distribution du FWCI par champ (réf. France)")
if not include_conference:
    conference_blob_caveat("Ce panneau")

df_fields = build_field_distribution_table(row, pubs_total)
df_fwci = build_fwci_whisker_table(row)

_pair_left, _pair_right = st.columns([1.05, 0.95])
with _pair_left:
    fig_share = plot_field_share_pair_left(df_fields, isite_overlay_on)
    st.plotly_chart(fig_share, use_container_width=True)
with _pair_right:
    fig_fwci = plot_fwci_whiskers(df_fwci)
    st.plotly_chart(fig_fwci, use_container_width=True)

st.caption(
    "**Comment lire.** Une boîte par champ : la barre centrale est la médiane, la "
    "boîte couvre les quartiles, les moustaches l'interdécile. Un travail est comparé "
    "aux travaux français du même sous-champ, de la même année et du même type. Un "
    "champ sans effectif suffisant n'affiche pas de boîte : l'indicateur n'est pas "
    "calculé, il n'est pas nul.  \n"
    "**Pourquoi cet indicateur.** Une moyenne de citations ne dit rien hors de sa "
    "discipline. La distribution montre à la fois le niveau habituel et la dispersion, "
    "c'est-à-dire la différence entre un profil régulier et un profil porté par "
    "quelques travaux."
)
exports.attach_download(
    st, df_fields, "lab-overview", "field-distribution", _EXPORT_STATE,
    entity=("l", selected_structure),
)
exports.attach_download(
    st, df_fwci, "lab-overview", "fwci-whiskers", _EXPORT_STATE,
    entity=("l", selected_structure),
)

st.markdown("---")

# --- Subfield Detail Table ---
st.markdown("#### Détail par sous-champ")

df_subfield_table = build_subfield_table(row, pubs_total)

if df_subfield_table.empty:
    st.info("Aucune donnée au niveau sous-champ pour cette structure.")
else:
    df_sub_display = df_subfield_table[[
        "Domain marker", "Champ", "Sous-champ", "count", "share_of_lab", "ratio_vs_ul", "fwci"
    ]].rename(columns={
        "Domain marker": "Domaine",
        "count": "Publications",
        "share_of_lab": "% du total de la structure",
        "ratio_vs_ul": "% de l'UL dans ce sous-champ",
        "fwci": "FWCI (réf. France)",
    })
    df_sub_display["% du total de la structure"] = df_sub_display["% du total de la structure"] * 100
    df_sub_display["% de l'UL dans ce sous-champ"] = df_sub_display["% de l'UL dans ce sous-champ"] * 100

    st.dataframe(
        df_sub_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Domaine": st.column_config.TextColumn("Domaine"),
            "Champ": st.column_config.TextColumn("Champ"),
            "Sous-champ": st.column_config.TextColumn("Sous-champ"),
            "Publications": st.column_config.NumberColumn("Publications", format="%d"),
            "% du total de la structure": st.column_config.ProgressColumn(
                "% du total de la structure", min_value=0.0, max_value=100.0, format="%.1f%%",
                help="Part des publications de cette structure relevant de ce sous-champ.",
            ),
            "% de l'UL dans ce sous-champ": st.column_config.NumberColumn(
                "% de l'UL dans ce sous-champ", format="%.1f%%",
                help="Part du total UL sur ce sous-champ qui provient de cette structure.",
            ),
            "FWCI (réf. France)": st.column_config.NumberColumn("FWCI (réf. France)", format="%.2f"),
        },
    )
    if not include_conference:
        conference_blob_caveat("Ce tableau")
    exports.attach_download(
        st, df_sub_display, "lab-overview", "subfield-detail", _EXPORT_STATE,
        entity=("l", selected_structure),
    )

st.markdown("---")

# -----------------------------------------------------------------------------
# #8/#9 -- Profil ODD de la structure (moved in from Portefeuille thématique;
# SIRIS/Aurora method toggle per P11 -- a METHOD comparison, never a peer one)
# -----------------------------------------------------------------------------
st.markdown("#### Profil ODD de la structure")

_sdg_covered = _lab_set("sdg_lab_methods")
if selected_structure not in _sdg_covered:
    st.info(
        "Cette donnée ne couvre que les laboratoires curés de la liste cliente : "
        "elle n'existe pas pour cette structure.", icon="ℹ️",
    )
else:
    _conf_state = "all" if include_conference else "no_conf"
    _sdg_all = _load_table("sdg_lab_methods")
    _sdg_row = _sdg_all[
        (_sdg_all["lab"] == selected_structure) & (_sdg_all["conf_state"] == _conf_state)
    ].sort_values("sdg")

    _method_pick = st.radio(
        "Méthode d'attribution :", ["SIRIS (VocTagger)", "Aurora (OpenAlex)"],
        horizontal=True, key=f"lab_sdg_method_{selected_structure}",
    )
    _is_siris = _method_pick.startswith("SIRIS")
    _share_col = "share_lab_corpus_siris" if _is_siris else "share_lab_corpus_aurora"

    _valid = _sdg_row.dropna(subset=[_share_col])
    if _valid.empty:
        st.info(f"{selected_structure} : aucun ODD au-dessus du seuil de fiabilité pour cette méthode.")
    else:
        _labels_sdg = [f"ODD {int(i)} · {SDG_NAMES.get(int(i), '')}" for i in _valid["sdg"]]
        fig_sdg = go.Figure(go.Bar(
            y=_labels_sdg, x=(_valid[_share_col] * 100).round(1), orientation="h",
            marker_color="#3E7CB1",
            text=[fr_pct(v) for v in (_valid[_share_col] * 100)],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Part : %{x:.1f}%<extra></extra>",
        ))
        fig_sdg.update_layout(
            height=max(320, len(_valid) * 28 + 80), margin=dict(t=10, l=10, r=60, b=10),
            xaxis=dict(title="Part du corpus de la structure (%)", showgrid=True, gridcolor="#D9DDE2"),
            yaxis=dict(autorange="reversed", title=""),
            plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF", showlegend=False,
        )
        st.plotly_chart(fig_sdg, use_container_width=True)
        _n_floor = int(_sdg_row[_share_col].isna().sum())
        if _n_floor:
            st.caption(
                f":grey[{fr_int(_n_floor)} ODD sous le seuil de fiabilité pour cette "
                "structure — masqués, jamais à 0 %.]"
            )
        exports.attach_download(
            st, _sdg_row, "lab-overview", "sdg-profile", _EXPORT_STATE,
            entity=("l", selected_structure),
        )
    st.caption(
        "**Comparaison de méthode.** SIRIS (vocabulaire contrôlé, méthode maison) et "
        "Aurora (champ natif OpenAlex, seuillé) attribuent chacune, à leur façon, un "
        "Objectif de développement durable au même travail. Chaque part rapporte les "
        "travaux de cet ODD au **corpus entier de la structure**, jamais à sa seule "
        "part déjà taguée. Ce n'est jamais une comparaison à un pair."
    )

st.markdown("---")

# -----------------------------------------------------------------------------
# Lab tops -- internes (inchangé, 10) + internationaux/français/auteur·es
# (#34, 30-deep, "afficher plus", NO search box below N=50)
# -----------------------------------------------------------------------------
st.caption(
    "**Comment lire.** Les premières lignes s'affichent par défaut ; « afficher "
    "plus » déploie la liste. Le tri par défaut suit le volume de "
    "co-publications, jamais le FWCI.  \n"
    "**Pourquoi cet indicateur.** Ces listes servent à préparer une conversation : "
    "reconnaître les partenariats installés, repérer une collaboration inattendue, "
    "retrouver qui porte un sujet dans la structure."
)

# --- Partenaires internes (unchanged: shallow, blob-based, has_members=False) ---
st.markdown("#### Partenaires internes")
df_collabs = parse_internal_collabs_blob(row.get("Top 10 internal lab/other collabs (type,count,ratio,FWCI)", ""))
df_collabs = pad_dataframe(df_collabs.head(10), 10, numeric_cols=["count", "ratio", "fwci"])
df_collabs["% of structure pubs"] = df_collabs["ratio"] * 100
df_collabs = df_collabs.drop(columns=["ratio"]).rename(columns={"fwci": "FWCI (réf. France)"})
df_collabs = df_collabs[["name", "type", "count", "% of structure pubs", "FWCI (réf. France)"]]
df_collabs["count"] = df_collabs["count"].astype("Int64")
df_collabs["FWCI (réf. France)"] = pd.to_numeric(df_collabs["FWCI (réf. France)"], errors="coerce").round(2)

visible_collabs = ranked_table(
    df_collabs, key=f"lab2_internal_{selected_structure}", id_col="name",
    search_cols=["name", "type"], has_members=False,
    progress_cols={"% of structure pubs": {"min_value": 0, "max_value": 100}},
    ref_labels={"name": "Partenaire", "type": "Type", "count": "Co-publications"},
)
exports.attach_download(
    st, visible_collabs, "lab-overview", "internal-partners", _EXPORT_STATE,
    entity=("l", selected_structure),
)

st.markdown("---")

_tops_covered = _lab_set("lab_top_partners")

# --- Partenaires internationaux (#34, 30-deep, real partner_id) --------------
st.markdown("#### Partenaires internationaux")
if selected_structure not in _tops_covered:
    st.info(
        "Cette donnée ne couvre que les laboratoires curés de la liste cliente : "
        "elle n'existe pas pour cette structure.", icon="ℹ️",
    )
else:
    _ltp = _load_table("lab_top_partners")
    df_intl = _ltp[(_ltp["lab"] == selected_structure) & (_ltp["scope"] == "international")].copy()
    df_intl = df_intl.sort_values("rank")
    df_intl["Pays"] = df_intl["country"].apply(country_label)
    df_intl = df_intl.rename(columns={"partner_name": "Partenaire", "copubs": "Co-publications"})

    visible_intl = ranked_table(
        df_intl, key=f"lab2_intl_{selected_structure}", id_col="partner_id",
        search_cols=["Partenaire", "Pays"], has_members=True,
        extra_hidden=["rank", "country", "is_consortium_member", "scope", "lab", "snapshot_date"],
        ref_labels={"Partenaire": "Partenaire", "Co-publications": "Co-publications", "Pays": "Pays"},
    )
    st.caption(
        ":grey[Masquer les membres du consortium peut réduire l'affichage : les "
        "lignes retirées ne sont pas remplacées, la liste reste celle des "
        "partenaires déjà calculés pour cette structure.]"
    )
    exports.attach_download(
        st, visible_intl, "lab-overview", "top-international-partners", _EXPORT_STATE,
        entity=("l", selected_structure),
    )

st.markdown("---")

# --- Partenaires français (#34, 30-deep) -------------------------------------
st.markdown("#### Partenaires français")
if selected_structure not in _tops_covered:
    st.info(
        "Cette donnée ne couvre que les laboratoires curés de la liste cliente : "
        "elle n'existe pas pour cette structure.", icon="ℹ️",
    )
else:
    _ltp = _load_table("lab_top_partners")
    df_fr = _ltp[(_ltp["lab"] == selected_structure) & (_ltp["scope"] == "france")].copy()
    df_fr = df_fr.sort_values("rank")
    df_fr = df_fr.rename(columns={"partner_name": "Partenaire", "copubs": "Co-publications"})

    visible_fr = ranked_table(
        df_fr, key=f"lab2_fr_{selected_structure}", id_col="partner_id",
        search_cols=["Partenaire"], has_members=True,
        extra_hidden=["rank", "country", "is_consortium_member", "scope", "lab", "snapshot_date"],
        ref_labels={"Partenaire": "Partenaire", "Co-publications": "Co-publications"},
    )
    st.caption(
        ":grey[Masquer les membres du consortium peut réduire l'affichage : les "
        "lignes retirées ne sont pas remplacées, la liste reste celle des "
        "partenaires déjà calculés pour cette structure.]"
    )
    exports.attach_download(
        st, visible_fr, "lab-overview", "top-french-partners", _EXPORT_STATE,
        entity=("l", selected_structure),
    )

st.markdown("---")

# --- Auteur·es les plus présent·es (#34, 30-deep, maison<->ORCID-only toggle) ---
st.markdown("#### Auteur·es les plus présent·es")
_authors_covered = _lab_set("lab_top_authors")
if selected_structure not in _authors_covered:
    st.info(
        "Cette donnée ne couvre que les laboratoires curés de la liste cliente : "
        "elle n'existe pas pour cette structure.", icon="ℹ️",
    )
else:
    _method_pick_auth = st.segmented_control(
        "Méthode", ["Réconciliation maison", "ORCID uniquement"],
        default="Réconciliation maison", required=True, key=f"lab_authors_method_{selected_structure}",
    )
    _auth_method = "maison" if _method_pick_auth == "Réconciliation maison" else "orcid_only"

    _lta = _load_table("lab_top_authors")
    df_authors = _lta[(_lta["lab"] == selected_structure) & (_lta["method"] == _auth_method)].copy()
    df_authors = df_authors.sort_values("rank")
    df_authors = df_authors.rename(columns={
        "display_name": "Auteur·e", "pubs": "Publications", "fwci_mean": "FWCI (réf. France)",
    })
    df_authors["FWCI (réf. France)"] = pd.to_numeric(df_authors["FWCI (réf. France)"], errors="coerce").round(3)

    _extra_hidden = ["rank", "author_key", "method", "lab", "snapshot_date"]
    if _auth_method == "maison":
        _extra_hidden.append("orcid")

    visible_authors = ranked_table(
        df_authors, key=f"lab2_authors_{selected_structure}", id_col="author_key",
        search_cols=["Auteur·e"], has_members=False,
        extra_hidden=_extra_hidden,
        ref_labels={"Auteur·e": "Auteur·e", "Publications": "Publications", "orcid": "ORCID"},
    )
    st.caption(
        ":grey[« ORCID uniquement » regroupe par identifiant ORCID brut, sans "
        "réconciliation de nom — à comparer avec la réconciliation maison, jamais "
        "à lui substituer par défaut.]"
    )
    exports.attach_download(
        st, visible_authors, "lab-overview", "top-authors", _EXPORT_STATE,
        entity=("l", selected_structure),
    )
