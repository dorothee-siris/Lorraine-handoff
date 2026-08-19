# lib/data_cache.py
"""
Centralized data loading with Streamlit caching.
All parquet files are loaded once and shared across views.

Every path is absolute (derived from __file__), so the app runs identically from
`streamlit run app.py` (cwd = Streamlit/) and `streamlit run Streamlit/app.py`
(cwd = repo root, which is what Streamlit Community Cloud does).

The deployed file set is `docs/data_contract.yaml`. Two v1 loads are gone:
`pubs.parquet` never existed (get_core_df now reads the deployed ul_pubs.parquet)
and the topic model's label dictionary died with it (D9).
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Work-level columns the app actually needs. ul_pubs.parquet is 17 MB mostly because
# of `abstract`; reading a column subset keeps the Community Cloud memory budget sane.
PUBS_SLIM_COLUMNS = [
    "work_id", "type", "is_conference", "publication_year",
    "Labs", "Poles",
    "In_ISITE", "Is_international", "Is_company",
    "PPtop10_FR", "PPtop1_FR", "FWCI_FR", "indicator_status",
    "primary_domain_id", "primary_field_id", "primary_subfield_id", "primary_topic_id",
]


@st.cache_resource
def get_topics_df() -> pd.DataFrame:
    """Taxonomy: domains, fields, subfields, topics (all_topics.parquet)."""
    return pd.read_parquet(DATA_DIR / "all_topics.parquet")


@st.cache_resource
def get_structures_df() -> pd.DataFrame:
    """All internal structures, curated AND hors-liste (D56). 100 rows."""
    return pd.read_parquet(DATA_DIR / "ul_labs.parquet")


@st.cache_resource
def get_labs_df() -> pd.DataFrame:
    """Laboratory structures only (Structure type == 'lab')."""
    df = get_structures_df()
    return df[df["Structure type"] == "lab"].copy()


@st.cache_resource
def get_partners_df() -> pd.DataFrame:
    """Full partners table (D55 seam: deployed, no page reads it yet)."""
    df = pd.read_parquet(DATA_DIR / "ul_partners.parquet")
    for col in ["institution_name", "country", "sector"]:
        if col in df.columns:
            df[col] = df[col].astype("category")
    return df


@st.cache_resource
def get_authors_df() -> pd.DataFrame:
    """Author dataset (D54 seam: deployed, no view)."""
    return pd.read_parquet(DATA_DIR / "ul_authors.parquet")


@st.cache_resource
def get_core_df() -> pd.DataFrame:
    """All UL publications, full width (ul_pubs.parquet). Heavy - prefer get_pubs_slim."""
    return pd.read_parquet(DATA_DIR / "ul_pubs.parquet")


@st.cache_data(ttl=900, max_entries=2)
def get_pubs_slim() -> pd.DataFrame:
    """
    Work-level table restricted to the columns the views need (D52 recomputation,
    D53 indicator_status). One row per work.

    Wave 0 (docs/foundry/DATA_FOUNDATION_draft.md sec.3): was `@st.cache_resource` with no TTL,
    which pinned the ~21.9 MB in-RAM slim frame for the life of the process the moment ANY page
    or toggle flip touched it. The corpus-level "N works excluded" disclosure that used to force
    this read on every render (pages 1/3/4, via `lib.thematic.excluded_counts`) now reads
    `dim_corpus_facts.parquet` instead (see `get_corpus_facts_df` below), so this function is only
    reached from the conference-toggle-OFF recompute paths. Bounded to `ttl=900` (15 min) /
    `max_entries=2` so a toggle flip no longer costs an eternal ~22 MB pin, while still avoiding a
    re-read on every widget rerun within the TTL window (this is a nullary function, so at most one
    cache slot is ever live -- `max_entries=2` is a small margin, not a real multi-key budget).
    """
    return pd.read_parquet(DATA_DIR / "ul_pubs.parquet", columns=PUBS_SLIM_COLUMNS)


@st.cache_data
def get_corpus_facts_df() -> pd.DataFrame:
    """
    dim_corpus_facts.parquet -- 2 rows keyed by conf_state ('all' | 'no_conf'), a few KB.

    Wave 0 replacement for the unconditional `ul_pubs` slim read that used to back the
    corpus-level "N works excluded (thin stratum)" disclosure on pages 1/3/4
    (`lib.thematic.excluded_counts_from_facts` reads this). Pipeline-computed
    (`pipeline/44g_build_corpus_facts.py`); the app never recomputes these numbers.
    """
    return pd.read_parquet(DATA_DIR / "dim_corpus_facts.parquet")


@st.cache_resource
def get_lookup_df() -> pd.DataFrame:
    """Corpus-level fact sheet (deployed, no view)."""
    return pd.read_parquet(DATA_DIR / "ul_lookup.parquet")


@st.cache_data
def load_thematic_overview():
    return pd.read_parquet(DATA_DIR / "thematic_overview.parquet")


@st.cache_data
def load_treemap_hierarchy():
    return pd.read_parquet(DATA_DIR / "treemap_hierarchy.parquet")


@st.cache_data
def load_thematic_sublevels():
    return pd.read_parquet(DATA_DIR / "thematic_detail_sublevels.parquet")


@st.cache_data
def load_thematic_contributions():
    return pd.read_parquet(DATA_DIR / "thematic_detail_contributions.parquet")


@st.cache_data
def load_thematic_partners():
    return pd.read_parquet(DATA_DIR / "thematic_detail_partners.parquet")


@st.cache_data
def load_thematic_authors():
    return pd.read_parquet(DATA_DIR / "thematic_detail_authors.parquet")


@st.cache_data
def load_sdg_three_way():
    """SDG assignments, three variants side by side (D51 config switch)."""
    return pd.read_parquet(DATA_DIR / "sdg_three_way.parquet")


@st.cache_data
def load_sdg_siris():
    """SIRIS (variant B) SDG assignments with their evidence: keyword_hits, text_basis."""
    return pd.read_parquet(DATA_DIR / "sdg_siris.parquet")


@st.cache_data
def load_lab_info():
    """{structure_key: {Structure name, Structure type}} for blob decoding."""
    try:
        df = get_structures_df()
        return df.set_index("structure_key")[["Structure name", "Structure type"]].to_dict("index")
    except Exception as e:
        st.warning(f"Could not load lab info: {e}")
        return {}


@st.cache_data
def load_partners_base():
    """
    Partner reciprocity denominators (D55 seam).

    Absent until the 42b OpenAlex pull lands; callers must tolerate an empty frame
    (the contract's degradation path renders "-" and hides the reciprocity section).
    """
    path = DATA_DIR / "ul_partners_base.parquet"
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception as e:
        st.warning(f"Could not load partners base: {e}")
        return pd.DataFrame()
