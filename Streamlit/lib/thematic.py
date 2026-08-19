# lib/thematic.py
"""
Thematic aggregates, with the D52 conference-paper switch.

Conference papers ON (the default) -> the deployed, contract-validated tables are
served verbatim, so the app is at v1 parity and shows exactly the numbers the
pipeline computed.

Conference papers OFF -> the same shapes are recomputed from `ul_pubs.parquet`
(one row per work, carries `is_conference`). Recomputation is exact for everything
the work-level table can express; blob-encoded tables (partners, authors,
contributions, the per-structure blobs of `ul_labs`) cannot be re-filtered and say
so in a caption instead of faking a number (D52).

D53 is enforced here: citation shares divide by the count of works with
`indicator_status == 'computed'`, never by the whole group, and a level with no
computed work gets NaN — never 0. Every returned frame carries
`works_excluded` so the views can disclose the count.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd
import streamlit as st

from lib.app_config import sdg_column
from lib.data_cache import (
    get_corpus_facts_df,
    get_pubs_slim,
    get_topics_df,
    load_sdg_three_way,
    load_thematic_overview,
    load_thematic_sublevels,
    load_treemap_hierarchy,
)

YEARS = list(range(2019, 2024))

LEVEL_ID_COL: Dict[str, str] = {
    "domain": "primary_domain_id",
    "field": "primary_field_id",
    "subfield": "primary_subfield_id",
    "topic": "primary_topic_id",
}

CHILD_OF = {"domain": "field", "field": "subfield", "subfield": "topic"}

UNCLASSIFIED_ID = "0"
UNCLASSIFIED_NAME = "Unclassified"

# id prefixes page 3's treemap needs (plotly resolves parents in one flat namespace)
TREEMAP_PREFIX = {"domain": "d_", "field": "f_", "subfield": "sf_", "topic": "t_"}

CENTILES = [0, 10, 25, 50, 75, 90, 100]


# ---------------------------------------------------------------------------
# taxonomy helpers
# ---------------------------------------------------------------------------

@st.cache_data
def _taxonomy_names() -> Dict[str, pd.DataFrame]:
    """{level: DataFrame[id, name, parent_id, domain_id]} from the OpenAlex dictionary."""
    t = get_topics_df()
    out = {}
    out["domain"] = (
        t[["domain_id", "domain_name"]].drop_duplicates()
        .assign(id=lambda d: d["domain_id"].astype(str), name=lambda d: d["domain_name"],
                parent_id="", domain_id_s=lambda d: d["domain_id"].astype(str))
        [["id", "name", "parent_id", "domain_id_s"]]
    )
    out["field"] = (
        t[["field_id", "field_name", "domain_id"]].drop_duplicates()
        .assign(id=lambda d: d["field_id"].astype(str), name=lambda d: d["field_name"],
                parent_id=lambda d: d["domain_id"].astype(str),
                domain_id_s=lambda d: d["domain_id"].astype(str))
        [["id", "name", "parent_id", "domain_id_s"]]
    )
    out["subfield"] = (
        t[["subfield_id", "subfield_name", "field_id", "domain_id"]].drop_duplicates()
        .assign(id=lambda d: d["subfield_id"].astype(str), name=lambda d: d["subfield_name"],
                parent_id=lambda d: d["field_id"].astype(str),
                domain_id_s=lambda d: d["domain_id"].astype(str))
        [["id", "name", "parent_id", "domain_id_s"]]
    )
    out["topic"] = (
        t[["topic_id", "topic_name", "subfield_id", "domain_id"]].drop_duplicates()
        .assign(id=lambda d: d["topic_id"].astype(str), name=lambda d: d["topic_name"],
                parent_id=lambda d: d["subfield_id"].astype(str),
                domain_id_s=lambda d: d["domain_id"].astype(str))
        [["id", "name", "parent_id", "domain_id_s"]]
    )
    for level, df in out.items():
        out[level] = df.rename(columns={"domain_id_s": "domain_id"}).reset_index(drop=True)
    return out


@st.cache_data
def _sdg_tagged_work_ids(column: str | None) -> frozenset:
    """work_ids carrying at least one SDG under the active variant (D51)."""
    if not column:
        return frozenset()
    sdg = load_sdg_three_way()
    if column not in sdg.columns:
        return frozenset()
    return frozenset(sdg.loc[sdg[column].notna(), "work_id"].astype(str))


# ---------------------------------------------------------------------------
# the one aggregation used everywhere
# ---------------------------------------------------------------------------

def _pubs(include_conference: bool) -> pd.DataFrame:
    df = get_pubs_slim()
    if not include_conference:
        df = df[~df["is_conference"].fillna(False)]
    return df


def _year_blob(years: pd.Series) -> str:
    counts = years.value_counts()
    return "|".join(f"{y}:{int(counts.get(y, 0))}" for y in YEARS)


def _cagr(years: pd.Series) -> float:
    counts = years.value_counts()
    first, last = counts.get(YEARS[0], 0), counts.get(YEARS[-1], 0)
    if first <= 0 or last <= 0:
        return np.nan
    return (last / first) ** (1 / (len(YEARS) - 1)) - 1


def _boxplot(fwci: pd.Series) -> str:
    vals = fwci.dropna()
    if vals.empty:
        return ""
    return "|".join(f"{np.percentile(vals, c):.2f}" for c in CENTILES)


def _aggregate(df: pd.DataFrame, key: pd.Series, sdg_ids: frozenset) -> pd.DataFrame:
    """
    Aggregate work-level rows by `key`. Returns one row per key with the
    thematic_overview metric columns (ids/names are attached by the caller).
    """
    work = df.assign(_key=key.values)
    work = work[work["_key"].notna()]
    if work.empty:
        return pd.DataFrame()
    work["_computed"] = work["indicator_status"].eq("computed")
    work["_sdg"] = work["work_id"].isin(sdg_ids)

    rows = []
    for key_value, g in work.groupby("_key", sort=False):
        n = len(g)
        comp = g[g["_computed"]]
        n_comp = len(comp)
        rows.append({
            "_key": key_value,
            "pubs_total": n,
            "pubs_per_year": _year_blob(g["publication_year"]),
            "pct_isite": float(g["In_ISITE"].fillna(False).mean()),
            "pct_top10": float(comp["PPtop10_FR"].fillna(False).mean()) if n_comp else np.nan,
            "pct_top1": float(comp["PPtop1_FR"].fillna(False).mean()) if n_comp else np.nan,
            "pct_international": float(g["Is_international"].fillna(False).mean()),
            "pct_company": float(g["Is_company"].fillna(False).mean()),
            "pct_sdg": float(g["_sdg"].mean()),
            "cagr_2019_2023": _cagr(g["publication_year"]),
            "fwci_median": float(comp["FWCI_FR"].median()) if n_comp else np.nan,
            "fwci_mean": float(comp["FWCI_FR"].mean()) if n_comp else np.nan,
            "fwci_boxplot": _boxplot(comp["FWCI_FR"]),
            "works_with_indicators": n_comp,
            "works_excluded": n - n_comp,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# public API — the three shapes the pages consume
# ---------------------------------------------------------------------------

@st.cache_data
def _recompute_overview(include_conference: bool) -> pd.DataFrame:
    df = _pubs(include_conference)
    sdg_ids = _sdg_tagged_work_ids(sdg_column())
    total = len(df)
    tax = _taxonomy_names()

    frames = []
    for level, col in LEVEL_ID_COL.items():
        # Untopiced works get id "0" at EVERY level, matching the deployed table:
        # OpenAlex assigned them no topic at all, so they are unclassified all the
        # way up. Hiding them would hide the 0.1%-untopiced headline.
        keys = df[col].astype("string").fillna(UNCLASSIFIED_ID)
        agg = _aggregate(df, keys, sdg_ids)
        if agg.empty:
            continue
        names = pd.concat([tax[level], pd.DataFrame([{
            "id": UNCLASSIFIED_ID, "name": UNCLASSIFIED_NAME,
            "parent_id": "", "domain_id": UNCLASSIFIED_ID}])], ignore_index=True)
        agg = agg.rename(columns={"_key": "id"}).merge(names, on="id", how="left")
        agg["level"] = level
        parents = tax[{"field": "domain", "subfield": "field", "topic": "subfield"}[level]] \
            if level != "domain" else None
        if parents is not None:
            agg = agg.merge(parents[["id", "name"]].rename(
                columns={"id": "parent_id", "name": "parent_name"}), on="parent_id", how="left")
        else:
            agg["parent_name"] = ""
        frames.append(agg)

    out = pd.concat(frames, ignore_index=True)
    out["pubs_pct_of_ul"] = out["pubs_total"] / max(1, total)
    out["name"] = out["name"].fillna(out["id"])
    out["parent_id"] = out["parent_id"].fillna("")
    out["parent_name"] = out["parent_name"].fillna("")
    out["domain_id"] = out["domain_id"].fillna(UNCLASSIFIED_ID)
    return out


@st.cache_data
def excluded_counts(include_conference: bool) -> tuple[int, int]:
    """
    (works excluded from the citation indicators, corpus total) for the active
    conference setting — the D53 disclosure denominator. Works with
    indicator_status != 'computed' sit in a stratum too thin to rank against.
    """
    df = _pubs(include_conference)
    return int((df["indicator_status"] != "computed").sum()), int(len(df))


def excluded_counts_from_facts(include_conference: bool) -> tuple[int, int]:
    """
    (works excluded from the citation indicators, corpus total) for the active conference
    setting -- sourced from the pipeline-computed `dim_corpus_facts` footer (wave 0), never
    from a work-level `ul_pubs` read.

    Byte-identical to `excluded_counts(include_conference)` above (same numbers, cross-checked
    at build time in `pipeline/44g_build_corpus_facts.py`), but replaces its 3 unconditional call
    sites (pages 1/3/4's corpus-level "N works excluded" disclosure) so a cold visit no longer
    pins the ~21.9 MB `ul_pubs` slim frame just to show this caption. `excluded_counts` itself is
    left in place (unused elsewhere, but no other stream depends on removing it).
    """
    facts = get_corpus_facts_df()
    conf_state = "all" if include_conference else "no_conf"
    row = facts.loc[facts["conf_state"] == conf_state].iloc[0]
    return int(row["works_excluded_thin_stratum"]), int(row["corpus_works"])


def get_overview(include_conference: bool) -> pd.DataFrame:
    """thematic_overview shape. Deployed table when conference papers are in."""
    if include_conference:
        df = load_thematic_overview().copy()
        if "works_excluded" not in df.columns:
            df["works_excluded"] = np.nan
        return df
    return _recompute_overview(False)


@st.cache_data
def _recompute_sublevels(include_conference: bool) -> pd.DataFrame:
    df = _pubs(include_conference)
    sdg_ids = _sdg_tagged_work_ids(sdg_column())
    tax = _taxonomy_names()

    frames = []
    for parent_level, child_level in CHILD_OF.items():
        parent_col = LEVEL_ID_COL[parent_level]
        child_col = LEVEL_ID_COL[child_level]
        sub = df[df[parent_col].notna() & df[child_col].notna()]
        if sub.empty:
            continue
        key = sub[parent_col].astype(str) + "␟" + sub[child_col].astype(str)
        agg = _aggregate(sub, key, sdg_ids)
        if agg.empty:
            continue
        agg[["parent_id", "child_id"]] = agg["_key"].str.split("␟", expand=True)
        agg["parent_level"] = parent_level
        agg["child_level"] = child_level
        agg = agg.merge(
            tax[child_level][["id", "name"]].rename(columns={"id": "child_id", "name": "child_name"}),
            on="child_id", how="left")
        parent_totals = agg.groupby("parent_id")["pubs_total"].transform("sum")
        agg["pubs_pct_of_parent"] = agg["pubs_total"] / parent_totals.replace(0, np.nan)
        frames.append(agg.drop(columns=["_key"]))

    out = pd.concat(frames, ignore_index=True)
    out["child_name"] = out["child_name"].fillna(out["child_id"])
    out["pubs_pct_of_parent"] = out["pubs_pct_of_parent"].fillna(0.0)
    out["pct_isite"] = out["pct_isite"].fillna(0.0)
    return out


def get_sublevels(include_conference: bool) -> pd.DataFrame:
    """thematic_detail_sublevels shape."""
    if include_conference:
        df = load_thematic_sublevels().copy()
        if "works_excluded" not in df.columns:
            df["works_excluded"] = np.nan
        return df
    return _recompute_sublevels(False)


def get_treemap(include_conference: bool) -> pd.DataFrame:
    """treemap_hierarchy shape (prefixed ids so plotly can resolve parents)."""
    if include_conference:
        return load_treemap_hierarchy()
    ov = _recompute_overview(False)
    out = pd.DataFrame({
        "id": ov["level"].map(TREEMAP_PREFIX) + ov["id"].astype(str),
        "name": ov["name"],
        "parent_id": np.where(
            ov["parent_id"].astype(str) == "",
            "",
            ov["level"].map({"field": "d_", "subfield": "f_", "topic": "sf_"}).fillna("")
            + ov["parent_id"].astype(str),
        ),
        "level": ov["level"],
        "pubs": ov["pubs_total"].astype(int),
        "fwci_median": ov["fwci_median"],
        "pct_top10": ov["pct_top10"],
        "pct_international": ov["pct_international"],
        "pct_isite": ov["pct_isite"],
    })
    return out.reset_index(drop=True)
