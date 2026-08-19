"""
Author Profile (A-V2) -- docs/indicator_plan_FINAL.md S5 / docs/studio/VIZ_SPEC.md S2.11.

One person end to end: header, yearly output, thematic identity, a lazy works list, and --
one deliberate click deep, never leaving the app -- an impact drill.

Structural safeguards this page must honour (docs/indicator_plan_FINAL.md S5):
  - safeguard 1 (table split): impact numbers live ONLY in `aut_impact_drill`, a file this
    page reads nowhere except inside the drill expander below. The works list reads
    `aut_works`, which PHYSICALLY carries no fwci/pptop/impact/citation column -- a UI
    bug here cannot leak impact through the works list even by accident.
  - safeguard 2 (no default sort by quantity): the works list defaults to reverse-
    chronological (a bibliography order, not a ranking of the person's OTHER works by
    volume/impact); nothing on this page ever defaults to a per-PERSON quantity sort.
  - safeguard 3 (author-scoped exports strip impact): the works export always calls
    `exports.works_xlsx(..., impact_strip=True)` -- defence-in-depth, since aut_works has
    no impact column to strip in the first place.
  - safeguard 3bis / S6.4 exception: the impact drill has NO export control anywhere in
    its code path (grep this file for "download"/"xlsx" between the drill's expander open
    and close -- there is none).
  - safeguard 6 (S10 audience banner, explicit).

Pass-6 stream P-GA (2026-08-19): narrative sweep (1 jargon, per NARRATIVE_CONTRACT_pass6.md
S2.13) -- title/caption reorder, "Réf." column renamed "Topics hors référentiel" (item #48,
copied from the contract's own framing), EN table labels -> FR (G10); VIZ_BACKLOG #6 -- the
"Identité thématique" 3-row subfield table gains a "Publications" count column, read from
lib.data_cache.get_pubs_slim() (the SAME bounded/TTL'd shared accessor pages 1/3/4 already
use for this exact "work_id -> primary_subfield_id" lookup -- aut_works carries no subfield
column of its own, and aut_public only ships the top-3 ids/labels, not their counts, so this
is the cheapest honest source, not a new heavy-load pattern).
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib.controls import (
    sidebar as controls_sidebar, banner as artifact_banner, filtered_by_strip,
    xa as xa_col, marker_dagger_column,
    ARTIFACT_TOGGLE_KEY, DEFERRED_GREY,
)
from lib.exports import attach_download, ExportState
from lib.lazy import read_keyed
from lib.data_cache import DATA_DIR, get_pubs_slim
from lib.helpers import (
    YEARS, get_field_id_to_name, get_field_id_to_domain_id, get_subfield_id_to_name,
    get_subfield_id_to_domain_id, get_domain_id_to_name, DOMAIN_EMOJI,
    fr_int, snapshot_date_label, window_label,
)

# =============================================================================
# Page config
# =============================================================================
st.set_page_config(page_title="Author Profile | UL Bibliometrics", page_icon="👤", layout="wide")

AUT_WORKS_PATH = str(DATA_DIR / "aut_works.parquet")

# ----------------------------------------------------------------------------
# FR-ready label dictionary + binding VERBATIM strings (VIZ_SPEC 1.6: new pages build
# EN-first; the two phrases below are exact quotes from indicator_plan_FINAL.md / VIZ_SPEC
# and are named constants for that reason, never translated or reworded).
# ----------------------------------------------------------------------------
IMPACT_DRILL_LABEL_FR = "contexte d'impact — consultation uniquement"
N_UNDER_FLOOR_MSG_FR = "indicateurs non affichés (n<30)"
EMPTY_RESULT_MSG_FR = (
    "Aucun profil apparié. Vérifiez l'orthographe du nom ou l'identifiant ORCID "
    "(format 0000-0002-1825-0097)."
)
S10_BANNER_FR = (
    "Un **« outil d'animation scientifique »** : suivre un parcours de recherche et ouvrir "
    "ses preuves pour engager la conversation -- jamais un classement des personnes entre elles."
)
LAUREATE_STUB_CAPTION_FR = (
    ":grey[Distinctions (ERC / IUF / HCR) : liste en attente (GT Indicateurs) -- "
    "aucune hypothèse dans l'intervalle.]"
)
IMPACT_EXEMPT_CAPTION_FR = (
    ":grey[Ces valeurs sont calculées sur le corpus entier -- elles ne se recalculent pas "
    "sous le filtre référentiel actif.]"
)
# item #48, copied from NARRATIVE_CONTRACT_pass6.md S2.12's own framing (the column lives
# here, on page 12 -- the feedback item's "K. Annuaire auteurs" heading names the module,
# not this exact file).
REF_COLUMN_LABEL_FR = "Topics hors référentiel"
REF_COLUMN_HELP_FR = (
    "Cette publication porte un topic que le classifieur mondial résout mal (souvent un "
    "sujet local ou national) : le repère est affiché, jamais retiré."
)


# =============================================================================
# Data
# =============================================================================
@st.cache_resource
def _load_aut_public() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "aut_public.parquet")


@st.cache_resource
def _load_aut_impact_drill() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "aut_impact_drill.parquet")


# IMPORTANT: field/subfield tags below are keyed on the `..._ids` columns (numeric,
# comma-joined), NEVER on the `..._labels` strings. Several OpenAlex field/subfield
# NAMES themselves contain an internal comma (e.g. "Biochemistry, Genetics and
# Molecular Biology", "Health, Toxicology and Mutagenesis") -- naive split(",") on a
# labels string silently mis-splits those into extra bogus tags AND can misalign a
# zipped ids/labels pair. IDs are pure digits and split unambiguously; names are
# resolved from the taxonomy dictionary instead of trusting the pre-joined string.
def _domain_emoji_for_field_id(fid: int) -> str:
    dom_id = get_field_id_to_domain_id().get(fid)
    dom_name = get_domain_id_to_name().get(dom_id, "Other") if dom_id is not None else "Other"
    return DOMAIN_EMOJI.get(dom_name, DOMAIN_EMOJI["Other"])


def _domain_emoji_for_subfield_id(sub_id: int) -> str:
    dom_id = get_subfield_id_to_domain_id().get(sub_id)
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


def _drill_tile(container, label: str, value: str, greyed: bool) -> None:
    color = f"color:{DEFERRED_GREY};" if greyed else ""
    container.markdown(
        f'<div style="{color}">'
        f'<div style="font-size:0.85rem;opacity:0.7;">{label}</div>'
        f'<div style="font-size:1.6rem;font-weight:600;">{value}</div></div>',
        unsafe_allow_html=True,
    )


# =============================================================================
# Sidebar + banners
# =============================================================================
ctrl = controls_sidebar()
include_conference = ctrl["include_conference"]
artifact_on = ctrl[ARTIFACT_TOGGLE_KEY]

# Pass-6 standardised order (NARRATIVE_CONTRACT_pass6.md S2.13): title, then a neutral
# question caption -- never a title-as-answer line ahead of the title.
st.title("👤 Profil auteur")
st.caption(
    "Cette page répond à : quel est le parcours de recherche de cette personne, et que dit "
    "son contexte d'impact ?"
)
st.info(S10_BANNER_FR)
artifact_banner()
filtered_by_strip(page="profil_auteur")

df_public = _load_aut_public()

# =============================================================================
# Resolve the target author: st.session_state (primary, set by the Directory's row
# click) -> st.query_params (secondary, deep-link/testable) -> a small manual picker
# (this page must also work when opened directly, e.g. from the sidebar).
# =============================================================================
author_id = st.session_state.get("nav_author_id") or st.query_params.get("author_id")
known_ids = set(df_public["author_id"])

if not author_id or author_id not in known_ids:
    st.markdown("Aucun profil sélectionné. Ouvrez-en un depuis l'**Annuaire des auteurs**, ou recherchez ici :")
    pick_query = st.text_input("Rechercher par nom", value="", key="profile_pick_query").strip()
    if pick_query:
        matches = df_public[df_public["display_name"].str.contains(pick_query, case=False, na=False, regex=False)]
        matches = matches.sort_values("display_name", key=lambda s: s.str.lower()).head(25)
        if matches.empty:
            st.warning(EMPTY_RESULT_MSG_FR)
        else:
            options = {f'{r["display_name"]} ({r["author_id"]})': r["author_id"] for _, r in matches.iterrows()}
            picked_label = st.selectbox("Résultats", options=list(options.keys()), key="profile_pick_select")
            if st.button("Ouvrir le profil", key="profile_pick_open"):
                chosen = options[picked_label]
                st.session_state["nav_author_id"] = chosen
                st.query_params["author_id"] = chosen
                st.rerun()
    st.stop()

# Keep the deep-link current for the resolved profile.
st.query_params["author_id"] = author_id
person = df_public[df_public["author_id"] == author_id].iloc[0]

# =============================================================================
# Header card
# =============================================================================
with st.container(border=True):
    st.markdown(f"## {person['display_name']}")
    c1, c2, c3 = st.columns(3)
    with c1:
        if pd.notna(person["orcid"]):
            st.markdown(f"ORCID : [{person['orcid']}](https://orcid.org/{person['orcid']})")
        else:
            st.caption("ORCID : non lié")
    with c2:
        if pd.notna(person["idhal"]):
            st.markdown(f"idHAL : **{person['idhal']}**")
        else:
            st.caption("idHAL : non lié")
    with c3:
        labs = person["main_labs"] if pd.notna(person["main_labs"]) else "Aucun laboratoire attribué"
        st.markdown(f"Laboratoires : **{labs}**")
    distinctions = str(person["laureate_tags"]).strip() if pd.notna(person["laureate_tags"]) else ""
    if distinctions:
        st.markdown(f"Distinctions : {distinctions}")
    else:
        st.caption(LAUREATE_STUB_CAPTION_FR)

st.page_link("pages/11_👥_Annuaire_auteurs.py", label="← Retour à l'annuaire des auteurs")

# =============================================================================
# This person's works slice (aut_works, lazy-keyed) -- feeds BOTH the yearly bars
# (declared bounded exception to the lazy-load convention, per data_foundation.yaml
# rev 3.1 drill_layer.paths.author_works) and the works-list expander below.
# =============================================================================
works_df = read_keyed(AUT_WORKS_PATH, "author_id", author_id)

w = works_df.copy()
if not include_conference:
    w = w[~w["is_conference"].fillna(False)]
if artifact_on:
    w = w[~w["artifact_flag"].fillna(False)]

st.markdown("### Production annuelle")
counts = w.groupby("year").size()
fig = go.Figure(go.Bar(
    x=[str(y) for y in YEARS], y=[int(counts.get(y, 0)) for y in YEARS],
    marker_color="#0072B2",
))
fig.update_layout(height=260, margin=dict(t=20, l=40, r=20, b=30), yaxis_title="Publications", xaxis_title="")
st.plotly_chart(fig, width="stretch")
active_bits = []
if not include_conference:
    active_bits.append("articles de conférence exclus")
if artifact_on:
    active_bits.append("topics hors référentiel exclus")
subtitle = f"{fr_int(len(w))} publication(s), {window_label()}" + (f" ({', '.join(active_bits)})" if active_bits else "")
st.caption(subtitle)

st.markdown("### Identité thématique")
st.markdown(thematic_tags(person["thematic_identity_fields_ids"]) or "—")

if person["n_works"] >= 5:
    sub_ids_raw = person["thematic_identity_subfields_ids"]
    if pd.notna(sub_ids_raw) and str(sub_ids_raw).strip():
        id2name = get_subfield_id_to_name()
        sub_tokens = [t.strip() for t in str(sub_ids_raw).split(",") if t.strip()]
        # VIZ_BACKLOG #6: the 3-row table lacked a count/% column. aut_works carries no
        # subfield id of its own and aut_public only ships the top-3 ids/labels (not their
        # counts), so the per-subfield tally is read from the SAME bounded/TTL'd shared
        # accessor pages 1/3/4 already use (lib.data_cache.get_pubs_slim(), NOT a fresh
        # heavy-load pattern) -- filtered locally to this person's own work_id set, on the
        # SAME ALL-corpus basis the identity ranking itself was computed on.
        _slim_subfields = get_pubs_slim()[["work_id", "primary_subfield_id"]]
        _own_counts = (
            _slim_subfields[_slim_subfields["work_id"].isin(works_df["work_id"])]
            ["primary_subfield_id"].value_counts()
        )
        sub_rows = []
        for tok in sub_tokens:
            try:
                sid = int(tok)
            except ValueError:
                continue
            name = id2name.get(sid, f"Sous-champ {sid}")
            sub_rows.append({
                "": _domain_emoji_for_subfield_id(sid),
                "Sous-champs principaux": name,
                "Publications": int(_own_counts.get(tok, 0)),
            })
        if sub_rows:
            st.dataframe(
                pd.DataFrame(sub_rows), hide_index=True, width="stretch", height=38 * len(sub_rows) + 38,
                column_config={
                    "Publications": st.column_config.NumberColumn(
                        "Publications", format="%d",
                        help="Nombre de publications de la personne portant ce sous-champ à titre principal.",
                    ),
                },
            )
            st.caption(
                ":grey[Publications : décompte sur l'ensemble du corpus de la personne, "
                "indépendant des filtres de la barre latérale.]"
            )
else:
    st.caption(
        "Moins de 5 travaux : seuls les histogrammes et l'identité thématique "
        "s'affichent (un détail par sous-domaine serait du bruit à ce volume)."
    )

# =============================================================================
# Works list -- lazy expander, exportable impact-stripped (aut_works has no impact
# column to strip in the first place -- defence-in-depth per S6.4-3bis).
# QA-02/RA-A01 fix: `w` (filtered by conference/artifact state above) is what
# both the drawer and its export must render -- this used to render/export the
# unfiltered `works_df` instead, so the yearly chart above filtered but the
# drawer/export below silently did not.
# =============================================================================
with st.expander(f"Publications ({fr_int(len(w))})", expanded=False):
    show_df = w.sort_values("year", ascending=False).reset_index(drop=True)
    table = pd.DataFrame({
        "Année": show_df["year"],
        "Titre": show_df["title"],
        "Type": show_df["type"].astype(str),
        "Laboratoires": show_df["labs_short"],
        "ISITE": show_df["in_isite"].map({True: "★", False: ""}),
        REF_COLUMN_LABEL_FR: marker_dagger_column(show_df),
    })
    st.dataframe(
        table, hide_index=True, width="stretch",
        column_config={
            REF_COLUMN_LABEL_FR: st.column_config.TextColumn(
                REF_COLUMN_LABEL_FR, help=REF_COLUMN_HELP_FR, width="small",
            ),
        },
    )
    attach_download(
        st, w, "a-v2", "works",
        ExportState(
            snapshot=snapshot_date_label(), conf=include_conference, artifact=artifact_on,
            method="Liste des publications de l'auteur (aut_works) : colonnes d'impact structurellement absentes.",
        ),
        entity=("a", author_id), impact_strip=True, works=True,
        label="⬇ Publications (xlsx)",
    )

# =============================================================================
# Impact drill -- NO export control anywhere in this block (safeguard 3bis / S6.4
# exception). Floor-gated: tiles render ONLY if the ACTIVE conf_state's
# works_with_indicators >= 30 (the per-state re-check the plan names as "your job", D53) --
# -----------------------------------------------------------------------------------
with st.expander(IMPACT_DRILL_LABEL_FR, expanded=False):
    conf_token = "all" if include_conference else "no_conf"
    drill_df = _load_aut_impact_drill()
    row = drill_df[(drill_df["author_id"] == author_id) & (drill_df["conf_state"] == conf_token)]
    eligible = (not row.empty) and (float(row.iloc[0]["works_with_indicators"]) >= 30)

    if not eligible:
        st.info(N_UNDER_FLOOR_MSG_FR)
    else:
        r = row.iloc[0]
        greyed = artifact_on
        t1, t2, t3 = st.columns(3)
        _drill_tile(t1, "FWCI (réf. France, moyenne)", f"{float(r['fwci_fr_mean']):.2f}", greyed)
        _drill_tile(t2, "PPtop10 % (nombre)", fr_int(r["pptop10_count"]), greyed)
        _drill_tile(t3, "Publications avec indicateurs", fr_int(r["works_with_indicators"]), greyed)
        if greyed:
            st.caption(IMPACT_EXEMPT_CAPTION_FR)

    st.caption(
        "Comment lire. Le FWCI et la part de travaux dans le top 10 % deviennent bruités "
        "sur de petits corpus individuels. Ils ne s'affichent qu'à partir de 30 travaux "
        "porteurs d'un indicateur, et se lisent comme un signal, jamais comme un score "
        "individuel exact. Consultation uniquement : aucun téléchargement ici."
    )
