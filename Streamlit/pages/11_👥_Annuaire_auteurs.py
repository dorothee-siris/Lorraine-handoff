"""
Authors Directory (A-V1) -- docs/indicator_plan_FINAL.md S5 / docs/studio/VIZ_SPEC.md S2.10.

A search-first directory over `aut_public` (12,680 persons). This is a LOOKUP page, not a
comparison page: no charts, no default ranking. The three structural safeguards this page
must honour (docs/indicator_plan_FINAL.md S5, "Binding safeguards"):

  - safeguard 1 (table split): this page reads `aut_public` ONLY -- it never imports or
    touches `aut_impact_drill`. A UI toggle cannot un-hide a column that lives in a
    different file; this page cannot leak impact even by accident, because the file it
    reads physically carries no fwci/pptop/impact/citation column.
  - safeguard 2 (no default sort by quantity): the results table is ALWAYS pre-sorted
    alphabetically by name. `st.dataframe` still lets a user click "Works" to sort by
    volume -- that is the user's own query, not a default the page hands them.
  - safeguard 6 (S10 audience banner, explicit on every author page): rendered below.

Row click -> Author Profile: no cross-page pattern exists yet elsewhere in this app (grepped
before writing this), so this establishes one: `st.session_state["nav_author_id"]` (primary,
survives a `st.switch_page` within the running session) mirrored into `st.query_params`
(secondary, makes the target page shareable/deep-linkable and trivially testable headlessly).

Pass-6 stream P-GA (2026-08-19): #47 page-flip pagination ("Page" number_input) replaced by
an "afficher plus" +50 incremental reveal (lib.ranked.next_reveal_count, P6-R6/plan P8) --
the search box stays unconditionally (N = 12,680 profiles, always >> the N>=50 threshold);
narrative sweep (page already clean, 0 jargon/0 digit per NARRATIVE_CONTRACT_pass6.md
S2.12) -- title/caption reorder + the page-level "Comment lire"/"Pourquoi cette page" blocks.
"""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from lib import ranked
from lib.controls import sidebar as controls_sidebar, banner as artifact_banner, \
    filtered_by_strip, xa as xa_col, ARTIFACT_TOGGLE_KEY
from lib.exports import attach_download, ExportState
from lib.data_cache import DATA_DIR
from lib.helpers import (
    get_field_id_to_name, get_field_id_to_domain_id, get_domain_id_to_name, DOMAIN_EMOJI,
    fr_int, fr_pct, snapshot_date_label,
)

# =============================================================================
# Page config
# =============================================================================
st.set_page_config(page_title="Authors Directory | UL Bibliometrics", page_icon="👥", layout="wide")

PAGE_SIZE = 25  # initial "afficher plus" reveal count (P6-R6/P8)
REVEAL_STEP = 50  # +50 rows per "afficher plus" click, item #47

# ----------------------------------------------------------------------------
# FR-ready label dictionary (VIZ_SPEC 1.6: new pages build EN-first; a few phrases are
# binding VERBATIM French text from the plan/spec and are named constants for that reason,
# not translated).
# ----------------------------------------------------------------------------
LABELS = {
    "search_prompt": "Rechercher par nom, ORCID ou idHAL",
    "search_hint": "Saisissez un nom, un ORCID ou un idHAL ci-dessus pour interroger l'annuaire.",
    # Dataframe column names (R12: EN allowed here) -- unchanged.
    "col_name": "Name",
    "col_orcid": "ORCID",
    "col_idhal": "idHAL",
    "col_labs": "Labs",
    "col_works": "Works",
    "col_identity": "Thematic identity",
    "col_distinctions": "Distinctions",
    "export_button": "⬇ Données (xlsx)",
}

# indicator_plan_FINAL.md S5 point 4 / VIZ_SPEC 2.10, exact quote:
EMPTY_RESULT_MSG_FR = (
    "Aucun profil apparié. Vérifiez l'orthographe du nom ou l'identifiant ORCID "
    "(format 0000-0002-1825-0097)."
)
# S10 (indicator_plan_FINAL.md S5 safeguard 6), same register as app.py's Home framing.
S10_BANNER_FR = (
    "Un **« outil d'animation scientifique »** : retrouver un profil et ouvrir ses preuves "
    "pour engager la conversation -- jamais un classement des personnes entre elles."
)
# A4 stub (docs/indicator_plan_FINAL.md S5, A4): no placeholder guesses.
LAUREATE_STUB_CAPTION_FR = (
    ":grey[Distinctions (ERC / IUF / HCR) : liste en attente (GT Indicateurs) -- "
    "la colonne s'activera dès réception, sans hypothèse dans l'intervalle.]"
)


# =============================================================================
# Data (this page reads aut_public ONLY -- safeguard 1)
# =============================================================================
@st.cache_resource
def _load_aut_public() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "aut_public.parquet")


# =============================================================================
# Thematic identity tags (domain colour via emoji + text, VIZ_SPEC A1 row)
#
# IMPORTANT: keyed on `thematic_identity_fields_ids` (numeric, comma-joined), NEVER on
# the `..._labels` string. Four of the 26 OpenAlex field names themselves contain an
# internal comma (e.g. "Biochemistry, Genetics and Molecular Biology", "Business,
# Management and Accounting") -- a naive split(",") on the labels string silently
# mis-splits those into extra bogus tags. IDs are pure digits and split unambiguously;
# names are resolved from the taxonomy dictionary instead of the pre-joined string.
# =============================================================================
def _domain_emoji_for_field_id(fid: int) -> str:
    dom_id = get_field_id_to_domain_id().get(fid)
    dom_name = get_domain_id_to_name().get(dom_id, "Other") if dom_id is not None else "Other"
    return DOMAIN_EMOJI.get(dom_name, DOMAIN_EMOJI["Other"])


def thematic_tags(ids_csv) -> str:
    if pd.isna(ids_csv) or not str(ids_csv).strip():
        return ""
    id2name = get_field_id_to_name()
    tags = []
    for tok in str(ids_csv).split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            fid = int(tok)
        except ValueError:
            continue
        name = id2name.get(fid)
        if name is None:
            continue
        tags.append(f"{_domain_emoji_for_field_id(fid)} {name}")
    return " · ".join(tags)


# =============================================================================
# Page
# =============================================================================
ctrl = controls_sidebar()
include_conference = ctrl["include_conference"]
artifact_on = ctrl[ARTIFACT_TOGGLE_KEY]

# Pass-6 standardised order (NARRATIVE_CONTRACT_pass6.md S2.12): title, then a neutral
# question caption -- never a title-as-answer line ahead of the title.
st.title("👥 Annuaire des auteurs")
st.caption(
    "Cette page répond à : comment retrouver une personne de l'annuaire, et ouvrir les "
    "publications qui la documentent ?"
)
st.info(S10_BANNER_FR)
artifact_banner()

df = _load_aut_public()
total_persons = len(df)
pct_orcid_all = float(df["orcid"].notna().mean() * 100)

filtered_by_strip(page="annuaire_auteurs")  # not an overlay surface (author safeguard, matrix §11)

st.markdown(
    "**Comment lire.** L'annuaire est un outil de recherche : saisir un nom, un ORCID ou un "
    "idHAL. Rien ne s'affiche tant qu'aucune recherche n'est lancée, et l'ordre des résultats "
    "est alphabétique, jamais un classement par volume.  \n"
    "**Pourquoi cette page.** Elle sert à retrouver une personne et à ouvrir les publications "
    "qui la documentent, jamais à comparer des personnes entre elles : aucune colonne "
    "d'impact n'existe dans les données que cette page lit."
)

# -----------------------------------------------------------------------
# Hero: search box. Default state = empty prompt + population stats line,
# NEVER a full listing (indicator_plan_FINAL.md S5: "search-first ... default
# order alphabetical/search -- never a quantity").
# -----------------------------------------------------------------------
query = st.text_input(
    LABELS["search_prompt"], value="", placeholder="ex. Dupont, ou 0000-0002-...",
    key="authdir_query",
).strip()

if st.session_state.get("authdir_last_query") != query:
    st.session_state["authdir_shown_n"] = PAGE_SIZE
    st.session_state["authdir_last_query"] = query

st.markdown(f"**{fr_int(total_persons)} profils** · **{fr_pct(pct_orcid_all)} avec ORCID lié**")

if not query:
    st.caption(LABELS["search_hint"])
else:
    norm_query_alnum = re.sub(r"[^0-9A-Za-z]", "", query).lower()
    name_mask = df["display_name"].str.contains(query, case=False, na=False, regex=False)
    idhal_mask = df["idhal"].fillna("").str.lower().str.contains(query.lower(), na=False)
    if norm_query_alnum:
        orcid_norm = df["orcid"].fillna("").str.replace("-", "", regex=False).str.lower()
        orcid_mask = orcid_norm.str.contains(norm_query_alnum, na=False)
    else:
        orcid_mask = pd.Series(False, index=df.index)
    mask = name_mask | idhal_mask | orcid_mask
    results = df[mask].sort_values("display_name", key=lambda s: s.str.lower())

    if results.empty:
        st.warning(EMPTY_RESULT_MSG_FR)
    else:
        total_results = len(results)
        shown_n = st.session_state.get("authdir_shown_n", PAGE_SIZE)
        page_slice = results.iloc[:shown_n].reset_index(drop=True)

        base_col = "n_works" if include_conference else "n_works_noconf"
        work_col = xa_col(df, base_col)

        display_rows = []
        for _, row in page_slice.iterrows():
            distinctions = str(row["laureate_tags"]).strip() if pd.notna(row["laureate_tags"]) else ""
            display_rows.append({
                LABELS["col_name"]: row["display_name"],
                # R12 chip wording: "✓ lié" / "— absent" -- never a bare symbol,
                # never colour-coded red/green.
                LABELS["col_orcid"]: "✓ lié" if pd.notna(row["orcid"]) else "— absent",
                LABELS["col_idhal"]: "✓ lié" if pd.notna(row["idhal"]) else "— absent",
                LABELS["col_labs"]: row["main_labs"] if pd.notna(row["main_labs"]) else "—",
                LABELS["col_works"]: int(row[work_col]) if pd.notna(row[work_col]) else 0,
                LABELS["col_identity"]: thematic_tags(row["thematic_identity_fields_ids"]),
                LABELS["col_distinctions"]: distinctions if distinctions else "—",
            })
        display_df = pd.DataFrame(display_rows)

        # ALPHABETICAL default; user-sortable (click any header) but NEVER
        # default-sorted by a quantity (safeguard 2).
        event = st.dataframe(
            display_df,
            hide_index=True,
            width="stretch",
            column_config={
                LABELS["col_orcid"]: st.column_config.TextColumn(
                    LABELS["col_orcid"], help="Lié (✓ lié) / absent (— absent) -- jamais colorié en rouge/vert."),
                LABELS["col_works"]: st.column_config.NumberColumn(
                    LABELS["col_works"], help="Cliquer l'en-tête pour trier par volume -- ce n'est jamais l'ordre par défaut."),
            },
            on_select="rerun",
            selection_mode="single-row",
            key="authdir_table",
        )
        sel_rows = event.selection.rows if event is not None and event.selection else []
        if sel_rows:
            picked = page_slice.iloc[sel_rows[0]]
            st.session_state["nav_author_id"] = picked["author_id"]
            st.query_params["author_id"] = picked["author_id"]
            st.switch_page("pages/12_👤_Profil_auteur.py")

        st.caption(
            f"{fr_int(len(page_slice))} profil(s) affiché(s) sur {fr_int(total_results)}. "
            "Cliquer une ligne ouvre son profil."
        )
        if total_results > shown_n:
            if st.button(ranked.MORE_LABEL, key="authdir_more_btn"):
                st.session_state["authdir_shown_n"] = ranked.next_reveal_count(
                    shown_n, total_results, REVEAL_STEP,
                )
                st.rerun()
        st.caption(LAUREATE_STUB_CAPTION_FR)

        # Export = aut_public xlsx ONLY (schema-guaranteed impact-free). Sources the
        # search-filtered rows, unmodified columns -- never joined with any impact table.
        attach_download(
            st, results, "a-v1", "directory",
            ExportState(
                snapshot=snapshot_date_label(), conf=include_conference, artifact=artifact_on,
                filters={"search": query},
                method="Annuaire des auteurs (aut_public) : filtre de recherche courant, ordre alphabétique.",
            ),
            label=LABELS["export_button"],
        )
