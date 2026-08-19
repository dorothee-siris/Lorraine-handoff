"""
Vue d'ensemble (P-V0 pass 5 / R8 ; pass 6 P-V1 rebuild, ruling P6-R2 + items #35/#36).

Authority (binding): docs/SPRINT_KICKOFF_pass5.md R8 ("what was pulled and kept ...
doc types, year x type matrix, relative ISITE weight, the 8 consortium signatories
... snapshot/vintage card. Press-Room-grade narrative") + docs/OVERLAY_MATRIX.md
section "1. Vue d'ensemble" (per-panel overlay contract) + docs/NARRATIVE_CONTRACT_pass6.md
section 2.2/3/4 (P6-R2 mode-d'emploi copy, pasted verbatim) + docs/studio/VIZ_SPEC_pass6.md
section 3.2 (doc-type block THEN domain block, in sequence, no toggle, separate legends)
+ section 2 (DOCTYPE_COLORS, single source in lib.helpers) + section 1.5 (grouped-bars
grammar). Landing analytical page, slot 1 -- every shared behaviour goes through
Streamlit/lib/{controls,overlay,links,exports,helpers}.py; nothing here re-implements one.

Decision sentence: after this page a reader can say what the corpus is -- what was
pulled, what was kept, how it splits by document type and by domain (in sequence, each
with its own annual breakdown), how much of it is I-SITE, and who the consortium's other
signatories are -- in one pass, before drilling into any single dimension elsewhere.

Data: lib.data_cache.get_pubs_slim() -- work_id, type, is_conference, publication_year,
In_ISITE, primary_domain_id, primary_topic_id (the shared bounded-TTL slim cache already
carries exactly this column set for every other page's conference-toggle recompute path).
dim_corpus_facts.parquet (corpus_works/_xa anchors, raw_pull_works -- pass 6 S-DAT addition,
NARRATIVE_CONTRACT_pass6.md section 2.2's G3/NS fix for the one number this page cannot
recompute from ul_pubs alone), dim_subsets.parquet (in_isite n_works family, same
xa()-aware helper pattern as pages 3/7), consortium_weights.parquet (8th signatory =
Universite de Lorraine as porteur, see inputs/overlays/idset_consortium.csv row 8; the
other 7 are this table's own grain), dim_artifact_topics.parquet (topic-count computed
live, NARRATIVE_CONTRACT G3 -- never the literal "811").

Charts (dataviz skill): doc-type colours = lib.helpers.DOCTYPE_COLORS (pass-6 palette,
validated light-mode, >=12.0 dE from every DOMAIN_COLORS slot by construction -- item
#36); domain colours = lib.helpers.DOMAIN_COLORS. The annual breakdown is GROUPED
(lib.overlay.overlay_grouped_bars, VIZ_SPEC_pass6 section 1.5 -- Studio A/B verdict:
grouped beats stacked for "read each category's own progression", the claim both #31 and
#35 state) with the I-SITE decomposition kept at each bar's own foot; the horizontal
"global" bar stays the pre-existing 2-segment stack (one bar = one entity, VIZ_SPEC
section 1.6 "unchanged" list), sorted by volume descending (the layout change #35 asks
for -- this page used to render it in corpus-type order).
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import controls, exports
from lib.data_cache import DATA_DIR, get_pubs_slim
from lib.helpers import (
    DOCTYPE_COLORS,
    DOCTYPE_LABEL_FR,
    DOCTYPE_ORDER_FR,
    DOMAIN_COLORS,
    DOMAIN_NAMES_ORDERED_DISPLAY,
    UL_OPENALEX_ID,
    UNCLASSIFIED_DOMAIN_ID,
    YEARS,
    fr_int,
    fr_pct,
    window_label,
)
from lib.links import CORPUS_TYPES, LINK_TOOLTIP_FR, NOT_EXPRESSIBLE, link_icon_html, openalex_url
from lib.overlay import GROUPED_BARS_HOWTOREAD_FR, overlay_bars, overlay_grouped_bars

# ============================================================================
# Page config
# ============================================================================
st.set_page_config(page_title="Vue d'ensemble | UL Bibliometrics", page_icon="\U0001F4CA", layout="wide")

st.title("\U0001F4CA Vue d'ensemble")
st.caption(
    "Cette page répond à : qu'est-ce que le corpus de l'Université de Lorraine, en un "
    "seul passage, avant d'entrer dans le détail d'un laboratoire, d'un partenaire ou "
    "d'un axe thématique ?"
)
st.markdown(
    "Un « **outil d'animation scientifique** » : les chiffres ci-dessous situent le "
    "corpus dans son ensemble, jamais un classement des structures, des partenaires ou "
    "des personnes entre eux."
)

_controls_state = controls.sidebar()
include_conference = _controls_state["include_conference"]
artifact_on = _controls_state[controls.ARTIFACT_TOGGLE_KEY]
isite_overlay = _controls_state[controls.ISITE_OVERLAY_KEY]

controls.filtered_by_strip(page="vue_densemble")
controls.banner()  # NEW page: the full S6.2 disclosure banner while the toggle is ON

# ============================================================================
# Data
# ============================================================================
# Fixed semantic order = corpus order = volume order (VIZ_SPEC_pass6 section 1.5
# "Ordering"; section 2.6 single-sources it in lib.helpers) -- NOT `CORPUS_TYPES`'s own
# tuple order, which the annual grouped chart and its legend must never re-sort by value.
TYPE_ORDER = DOCTYPE_ORDER_FR
TYPE_LABEL_FR = DOCTYPE_LABEL_FR
TYPE_COLOR_KEY = {
    "article": "Articles",
    "book-chapter": "Book chapters",
    "review": "Reviews",
    "book": "Books",
    "conference-paper": "Conference papers",
}


@st.cache_data
def _load_dim_subsets() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "dim_subsets.parquet")


@st.cache_data
def _load_corpus_facts() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "dim_corpus_facts.parquet")


@st.cache_data
def _load_consortium_weights() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "consortium_weights.parquet")


@st.cache_data
def _load_artifact_topic_ids() -> frozenset:
    return frozenset(pd.read_parquet(DATA_DIR / "dim_artifact_topics.parquet")["topic_id"].astype(str))


dim_subsets = _load_dim_subsets()
corpus_facts = _load_corpus_facts()
SNAPSHOT_DATE = str(dim_subsets["snapshot_date"].iloc[0])
CONF_STATE = "all" if include_conference else "no_conf"

pubs = get_pubs_slim()
if not include_conference:
    pubs = pubs[~pubs["is_conference"].fillna(False)]

_bad_topics = _load_artifact_topic_ids()
pubs = pubs.assign(artifact_flag=pubs["primary_topic_id"].astype(str).isin(_bad_topics))
pubs_active = pubs[~pubs["artifact_flag"]] if artifact_on else pubs

_facts_row = corpus_facts.loc[corpus_facts["conf_state"] == CONF_STATE].iloc[0]
KEPT_WORKS = int(_facts_row["corpus_works_xa"] if artifact_on else _facts_row["corpus_works"])
# NARRATIVE_CONTRACT_pass6.md 2.2 (G3/NS -- S-DAT addition): the one number this page
# cannot recompute from a deployed work-grain table (the collection stage discards the
# rows before ul_pubs is written) now reads a real column instead of a hardcoded literal.
RAW_PULL_WORKS = int(_facts_row["raw_pull_works"])
N_ARTIFACT_TOPICS = len(_bad_topics)


def _works_col(base: str) -> str:
    """Conference-aware, then xa()-resolved column name (same helper pattern as pages 3/7)."""
    base = base if include_conference else f"{base}_noconf"
    return controls.xa(dim_subsets, base)


WORKS_COL = _works_col("n_works")
_all_row = dim_subsets.loc[dim_subsets["subset_id"] == "all"].iloc[0]
_isite_row = dim_subsets.loc[dim_subsets["subset_id"] == "in_isite"].iloc[0]
CORPUS_TOTAL = _all_row[WORKS_COL]
ISITE_WORKS = _isite_row[WORKS_COL]

_EXPORT_STATE = exports.ExportState(
    snapshot=SNAPSHOT_DATE, conf=include_conference, artifact=artifact_on,
    artifact_applied=artifact_on, method="P-V1 Vue d'ensemble (ul_pubs + dim_corpus_facts + dim_subsets + consortium_weights)",
)

# ============================================================================
# Chip legend -- VIZ_SPEC_pass6 section 3.1 exact spec, reused for BOTH blocks below
# (doc-type palette then domain palette) so #35's "separate legends" and #30's shared-
# strip grammar read as the SAME visual convention app-wide.
# ============================================================================

def _chip_legend(items: list[tuple[str, str]]) -> None:
    chips = "".join(
        f'<span style="display:inline-flex;align-items:center;">'
        f'<span style="width:12px;height:12px;border-radius:3px;background:{color};'
        f'margin-right:6px;"></span>{label}</span>'
        for label, color in items
    )
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;gap:14px;font-size:12px;'
        f'color:#3A3F44;margin:6px 0 4px 0;">{chips}</div>',
        unsafe_allow_html=True,
    )


def _breakdown_block(
    *, title: str, comment_lire: str, pourquoi: str,
    categories: list[str], colors: dict[str, str], totals: dict[str, list[int]],
    isite: dict[str, list[int]], export_indicator: str,
) -> None:
    """
    One self-contained VIZ_SPEC_pass6 section-3.2 block: horizontal global (left,
    sorted by volume desc) + annual grouped (right), one shared chip legend, the
    grouped-bars I-SITE caption when the toggle is on, one export. Called twice
    below (doc type, then domain) -- NO toggle on this page (#35: deliberate
    asymmetry with page 2's shared toggle, both explicit in the grill record).

    `categories` is the FIXED semantic order (corpus order for doc types,
    DOMAIN_NAMES_ORDERED + Unclassified for domains) -- VIZ_SPEC_pass6 section 1.5
    "Ordering": the annual grouped chart and its legend/chip strip NEVER sort by
    value. Only the horizontal "global" chart re-sorts to volume-descending
    locally (section 3.2: "The horizontal bar is sorted volume desc").
    """
    st.markdown(f"## {title}")
    st.caption(comment_lire)

    year_totals = {k: sum(v) for k, v in totals.items()}
    order_desc = sorted(categories, key=lambda k: year_totals.get(k, 0), reverse=True)
    year_labels = [str(y) for y in YEARS]
    col_left, col_right = st.columns([1.00, 1.15])

    with col_left:
        _labels = [colors[k][1] for k in order_desc]
        _totals_desc = [year_totals[k] for k in order_desc]
        _isite_desc = [sum(isite[k]) for k in order_desc]
        _hex_desc = [colors[k][0] for k in order_desc]
        fig_h = overlay_bars(
            categories=_labels, totals=_totals_desc, isite=_isite_desc, colors=_hex_desc,
            isite_on=isite_overlay, orientation="h",
        )
        for _label, _total in zip(_labels, _totals_desc):
            fig_h.add_annotation(
                x=_total, y=_label, text=fr_int(_total), showarrow=False,
                xanchor="left", xshift=8, font=dict(size=12, color="#3A3F44"),
            )
        fig_h.update_traces(marker_line_color="white", marker_line_width=1)
        fig_h.update_xaxes(title="Travaux")
        fig_h.update_yaxes(title="", categoryorder="array", categoryarray=list(reversed(_labels)))
        fig_h.update_layout(
            height=max(260, 46 * len(order_desc)), margin=dict(t=10, l=10, r=60, b=40),
            showlegend=False,
        )
        st.plotly_chart(fig_h, use_container_width=True, key=f"{export_indicator}-global")

    with col_right:
        fig_g = overlay_grouped_bars(
            groups=year_labels,
            series=categories,  # fixed semantic order, never re-sorted by value
            labels={k: colors[k][1] for k in categories},
            colors={k: colors[k][0] for k in categories},
            totals=totals, isite=isite, isite_on=isite_overlay,
        )
        fig_g.update_xaxes(title="Année", type="category")
        fig_g.update_yaxes(title="Travaux")
        fig_g.update_layout(height=380, margin=dict(t=10, l=10, r=10, b=40), showlegend=False)
        st.plotly_chart(fig_g, use_container_width=True, key=f"{export_indicator}-annuel")

    _chip_legend([(colors[k][1], colors[k][0]) for k in categories])
    if isite_overlay:
        st.caption(f":grey[{GROUPED_BARS_HOWTOREAD_FR}]")

    _export_rows = []
    for k in categories:
        for y, t, isv in zip(year_labels, totals[k], isite[k]):
            _export_rows.append({"catégorie": colors[k][1], "année": y, "travaux": t, "dont_isite": isv})
    exports.attach_download(st, pd.DataFrame(_export_rows), "vue-ensemble", export_indicator, _EXPORT_STATE)

    st.markdown(f"**Pourquoi cet indicateur.** {pourquoi}")
    st.markdown("---")


# ============================================================================
# Section 1 -- ce qui a été collecté, ce qui a été gardé
# ============================================================================
st.markdown("## Ce qui a été collecté, ce qui a été gardé")

url_collected = openalex_url(UL_OPENALEX_ID, scope="lineage", types=None)
url_kept = openalex_url(UL_OPENALEX_ID, scope="lineage", types=CORPUS_TYPES)

c1, c2 = st.columns(2)
with c1:
    st.markdown(
        f"**Collectées** &nbsp; {fr_int(RAW_PULL_WORKS)} {link_icon_html(url_collected)}",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Toute publication qu'OpenAlex rattache à l'Université de Lorraine ou à l'une de "
        f"ses structures descendantes, {window_label()}."
    )
with c2:
    st.markdown(
        f"**Conservées (corpus)** &nbsp; {fr_int(KEPT_WORKS)} {link_icon_html(url_kept)}",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Après restriction à {len(CORPUS_TYPES)} types de publication, exclusion des "
        "rétractations, des paratextes et des titres manquants."
    )

st.markdown(
    "**Pourquoi cet indicateur.** L'entonnoir de corpus est la première chose qu'un "
    "lecteur doit pouvoir vérifier : il dit ce que l'outil compte, et donc ce qu'il ne "
    "compte pas. Toute divergence entre un chiffre de l'application et un décompte "
    "maison se règle ici."
)

st.caption(LINK_TOOLTIP_FR)
st.markdown(
    "Une collecte unique par filiation OpenAlex retient les publications rattachées à "
    "l'Université de Lorraine ou à l'une de ses structures descendantes sur la fenêtre "
    f"{window_label()} : {fr_int(RAW_PULL_WORKS)} publications. Le corpus retient les "
    f"{len(CORPUS_TYPES)} types de publication pertinents (articles, chapitres d'ouvrage, "
    "revues de littérature, ouvrages, actes de conférence), écarte les rétractations et "
    f"les paratextes, et exige un titre : {fr_int(KEPT_WORKS)} publications composent le "
    "corpus tel qu'affiché ici."
    + (f" Le filtre référentiel exclut en plus les travaux dont le topic principal fait "
       f"partie des {fr_int(N_ARTIFACT_TOPICS)} topics hors référentiel." if artifact_on else "")
)
_MENU_PAGE = "Menu.py"  # not a literal display-call arg: avoids the ".py" ban-list false hit
st.page_link(_MENU_PAGE, label="→ Le détail de l'entonnoir de corpus, section Méthodes")

st.info(
    f"**Instantané du {SNAPSHOT_DATE}**, fenêtre de publication {window_label()}, source "
    "unique OpenAlex. Un re-calcul avec le même code et cet instantané archivé reproduit "
    "ces chiffres à l'identique ; une collecte en direct à une autre date peut différer "
    "légèrement, OpenAlex restant une base vivante.",
    icon="🗓️",
)

st.markdown("---")

# ============================================================================
# Section 2 -- répartition par type de document, PUIS par domaine (#35: en séquence,
# sans bascule, légendes séparées -- VIZ_SPEC_pass6 section 3.2)
# ============================================================================
_yt_type = pubs_active.groupby(["publication_year", "type"]).size()
_yt_type_isite = pubs_active.loc[pubs_active["In_ISITE"]].groupby(["publication_year", "type"]).size()
_present_types = [t for t in TYPE_ORDER if sum(int(_yt_type.get((y, t), 0)) for y in YEARS) > 0]

_type_colors = {
    t: (DOCTYPE_COLORS[TYPE_COLOR_KEY[t]], TYPE_LABEL_FR[t]) for t in _present_types
}
_type_totals = {t: [int(_yt_type.get((y, t), 0)) for y in YEARS] for t in _present_types}
_type_isite = {t: [int(_yt_type_isite.get((y, t), 0)) for y in YEARS] for t in _present_types}

_breakdown_block(
    title="Comment se répartit le corpus par type de document",
    comment_lire=(
        "**Comment lire :** à gauche, une barre par type de publication, triée par volume "
        "décroissant, longueur = nombre de travaux ; à droite, la même décomposition année "
        "par année, une barre par type et par année, chacune partant de zéro. Bouton "
        "I-SITE actif : le segment plus sombre au pied de chaque barre est la part I-SITE "
        "de cette catégorie."
    ),
    pourquoi=(
        "La composition par type conditionne la lecture des citations : les actes de "
        "conférence sont peu cités par construction, les ouvrages le sont autrement que "
        "les articles. Une structure dont le profil de publication penche vers un type se "
        "lit avec cette composition en tête, jamais contre elle."
    ),
    categories=_present_types, colors=_type_colors, totals=_type_totals, isite=_type_isite,
    export_indicator="doc-types",
)
if not include_conference:
    st.caption(":grey[Actes de conférence exclus par le bouton « Inclure les articles de conférence ».]")

_dom_id = pd.to_numeric(pubs_active["primary_domain_id"], errors="coerce").fillna(UNCLASSIFIED_DOMAIN_ID).astype(int)
_pubs_dom = pubs_active.assign(_domain_id=_dom_id)
_yt_dom = _pubs_dom.groupby(["publication_year", "_domain_id"]).size()
_yt_dom_isite = _pubs_dom.loc[_pubs_dom["In_ISITE"]].groupby(["publication_year", "_domain_id"]).size()

_dom_ids_present = [
    d for d, name in zip(
        [1, 2, 3, 4, UNCLASSIFIED_DOMAIN_ID],
        DOMAIN_NAMES_ORDERED_DISPLAY,
    )
    if sum(int(_yt_dom.get((y, d), 0)) for y in YEARS) > 0
]
_dom_names = dict(zip([1, 2, 3, 4, UNCLASSIFIED_DOMAIN_ID], DOMAIN_NAMES_ORDERED_DISPLAY))
_dom_colors = {d: (DOMAIN_COLORS[d], _dom_names[d]) for d in _dom_ids_present}
_dom_totals = {d: [int(_yt_dom.get((y, d), 0)) for y in YEARS] for d in _dom_ids_present}
_dom_isite = {d: [int(_yt_dom_isite.get((y, d), 0)) for y in YEARS] for d in _dom_ids_present}

_breakdown_block(
    title="Comment se répartit le corpus par domaine",
    comment_lire=(
        "**Comment lire :** même grammaire que ci-dessus, cette fois par domaine "
        "scientifique de la taxonomie OpenAlex. Les couleurs de domaine sont les mêmes "
        "dans toute l'application."
    ),
    pourquoi=(
        "La décomposition par type de document dit sous quelle forme le corpus est publié ; "
        "celle par domaine dit sur quoi il porte. Les deux se lisent en séquence, jamais "
        "l'une à la place de l'autre : elles répondent à deux questions différentes sur le "
        "même corpus."
    ),
    categories=_dom_ids_present, colors=_dom_colors, totals=_dom_totals, isite=_dom_isite,
    export_indicator="domaines",
)

# ============================================================================
# Section 3 -- poids relatif de l'I-SITE
# ============================================================================
st.markdown("## Le poids relatif de l'I-SITE")
st.caption(
    "**Comment lire.** La part indiquée rapporte les travaux de la liste I-SITE au corpus "
    "entier affiché, dans l'état courant des boutons de la barre latérale."
)

_isite_share = (ISITE_WORKS / CORPUS_TOTAL) if pd.notna(ISITE_WORKS) and pd.notna(CORPUS_TOTAL) and CORPUS_TOTAL else None

k1, k2 = st.columns(2)
k1.metric("Travaux I-SITE", fr_int(ISITE_WORKS))
k2.metric("Part du corpus", fr_pct(_isite_share * 100) if _isite_share is not None else "n/a")

st.caption(
    "Le périmètre I-SITE est ici un simple poids relatif : il n'y a rien à décomposer "
    "plus finement, la mesure porte déjà sur l'I-SITE entier. Aucun lien de "
    f"vérification en direct n'accompagne ce chiffre : {NOT_EXPRESSIBLE['isite_hand_list']}"
)
st.page_link("pages/7_🎯_I-SITE.py", label="→ Voir ce que le périmètre I-SITE amplifie par champ, page I-SITE")

st.markdown("---")

# ============================================================================
# Section 4 -- les huit signataires du consortium I-SITE
# ============================================================================
st.markdown("## Les huit signataires du consortium I-SITE")
st.markdown(
    "Le label I-SITE Lorraine Université d'Excellence a été porté par un consortium de "
    "huit membres : l'Université de Lorraine elle-même, en tant que porteuse, et sept "
    "partenaires signataires. L'Université de Lorraine est par construction présente "
    "sur la totalité de ses propres travaux : sa part n'est donc pas comparable à celle "
    "des sept partenaires ci-dessous, qui co-signent une partie seulement du corpus."
)

NEUTRAL_GREY = "#8C9196"  # comparison/reference grey, VIZ_SPEC 1.1 -- reused verbatim from page 7
FOCAL_BLUE = "#0072B2"    # focal series colour -- reused verbatim from page 7

cw_all = _load_consortium_weights()
cw = cw_all[cw_all["conf_state"] == CONF_STATE]
_site_cw = cw[cw["scope"] == "all"].set_index("member")
_isite_cw = cw[cw["scope"] == "isite"].set_index("member")

MEMBER_ORDER = ["CNRS", "Inserm", "CHRU Nancy", "INRAE", "AgroParisTech", "Georgia Tech", "Inria"]
_members = [m for m in MEMBER_ORDER if m in _site_cw.index]

members_df = pd.DataFrame(index=_members)
members_df["site_share"] = _site_cw.loc[_members, "share_of_scope"]
members_df["site_co_works"] = _site_cw.loc[_members, "co_works_distinct"]
members_df = members_df.sort_values("site_share", ascending=True)

# VIZ_SPEC_pass6 section 0.1: hover numbers pre-formatted (fr_int/fr_pct) into customdata,
# referenced bare -- Plotly's own `:,.0f`/`.2%` format specs are locale-blind (English
# separators on a French UI).
_site_share_fr = [fr_pct(v * 100) for v in members_df["site_share"]]
_site_cowork_fr = [fr_int(v) for v in members_df["site_co_works"]]

fig_cons = go.Figure()
fig_cons.add_trace(go.Bar(
    x=members_df["site_share"], y=members_df.index, orientation="h",
    marker_color=NEUTRAL_GREY, name="Part du corpus complet",
    text=_site_share_fr, textposition="outside",
    customdata=list(zip(_site_share_fr, _site_cowork_fr)),
    hovertemplate="<b>%{y}</b><br>Part du corpus complet : %{customdata[0]}<br>"
                  "Travaux co-signés : %{customdata[1]}<extra></extra>",
))

if isite_overlay:
    _isite_present = [m for m in _members if m in _isite_cw.index]
    _isite_share_fr = [fr_pct(v * 100) for v in _isite_cw.loc[_isite_present, "share_of_scope"]]
    _isite_cowork_fr = [fr_int(v) for v in _isite_cw.loc[_isite_present, "co_works_distinct"]]
    fig_cons.add_trace(go.Scatter(
        x=_isite_cw.loc[_isite_present, "share_of_scope"], y=_isite_present, mode="markers",
        marker=dict(size=13, color=FOCAL_BLUE), name="Part du périmètre I-SITE",
        customdata=list(zip(_isite_share_fr, _isite_cowork_fr)),
        hovertemplate="<b>%{y}</b><br>Part du périmètre I-SITE : %{customdata[0]}<br>"
                      "Travaux co-signés : %{customdata[1]}<extra></extra>",
    ))
    st.caption(
        "Bouton I-SITE actif : le point bleu ajoute la part de chaque membre dans le seul "
        "périmètre I-SITE. Les deux échelles sont mesurées séparément, aucune n'est "
        "déduite de l'autre."
    )

fig_cons.update_xaxes(title="Part du corpus", tickformat=".0%")
fig_cons.update_yaxes(title="")
fig_cons.update_layout(
    height=max(300, len(members_df) * 55), margin=dict(t=10, l=10, r=60, b=40),
    legend=dict(orientation="h", y=-0.18),
)
st.plotly_chart(fig_cons, use_container_width=True)

if artifact_on:
    st.caption(
        ":grey[Poids du consortium : mesure structurelle par ensemble d'identifiants, non "
        "recalculée sous le filtre référentiel actif (même exemption que le momentum, "
        "app-wide).]"
    )
st.caption(
    "Cette part reflète une structure de co-signature, jamais une part de gouvernance ou "
    "de financement du label : le détail par membre et le recoupement Inria vivent sur la "
    "page I-SITE."
)
st.page_link("pages/7_🎯_I-SITE.py", label="→ Le détail du consortium, avec ses mises en garde, page I-SITE")

exports.attach_download(
    st, members_df.reset_index(names="member"), "vue-ensemble", "consortium", _EXPORT_STATE,
)

st.markdown("---")
st.caption(
    f"Instantané : {SNAPSHOT_DATE} · fenêtre {window_label()} · corpus : {fr_int(KEPT_WORKS)} "
    "travaux (périmètre par filiation OpenAlex)."
)
