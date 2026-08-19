"""
Positionnement -- frontier positioning, emerging topics, disciplinary diversity and
co-discipline structure of Universite de Lorraine's research portfolio, in the site's
own terms and against nine peers.

Pass 5, stream P-C (rulings R9, R16, R6/R7-context, R19; docs/SPRINT_KICKOFF_pass5.md,
BUILD_PLAN.md). NEW page: moves T9 / emerging topics / T3-T3c / T3b off page 4 (the
panel list docs/OVERLAY_MATRIX.md's own "5. Positionnement" section names) and adds the
frontier x labs crossing (R16) plus the peer-context panels (R6/R7) that page 4 only
stubbed. Six panels, argument order:

  1. Strategic cross (T9)            -- frontier positioning x specialisation, by field
  2. Emerging topics                 -- topic-grain frontier "texture", query-able (R11)
  3. Frontier x labs crossing (R16)  -- lab-grain breakdown, NO peer context (a crossing
                                         is not a comparison)
  4. Diversity (T3 / T3c)            -- Rao-Stirling/DIV tiles + the frozen momentum chip
  5. Peer context (R6/R7)            -- bench_positioning + bench_diversity, UL vs 9 peers
  6. Co-discipline (T3b) REDESIGN    -- the old 26x26 viridis heatmap (ruled unreadable)
                                         replaced by a query-able top-pairs table + a
                                         domain-block heatmap that actually carries the
                                         block structure

Shared modules only (S4 API, progress/S4_shared_layer.md sec.9): lib.overlay (the ONE
I-SITE overlay grammar), lib.links (OpenAlex deep links, silence when NOT_EXPRESSIBLE),
lib.ranked (the DEPTH & QUERY component -- top-10 default, "afficher plus", text query),
lib.helpers (fr_int/fr_pct, log/linear toggle, domain palette). lib/* is frozen: every
panel below composes those, never re-implements the grammar.

Full design rationale, recomputed numbers and the T3b redesign justification:
progress/PC_positionnement.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import controls, exports, links
from lib import overlay as ov
from lib.controls import ARTIFACT_TOGGLE_KEY, DAGGER, ISITE_OVERLAY_KEY
from lib.data_cache import DATA_DIR, get_corpus_facts_df
from lib.helpers import (
    DOMAIN_COLORS,
    DOMAIN_ORDER,
    UL_OPENALEX_ID,
    artifact_topics_count,
    fr_int,
    fr_pct,
    get_domain_id_to_name,
    get_field_id_to_domain_id,
    get_field_id_to_name,
    get_field_order_by_domain,
    log_linear_toggle,
    na_metric,
    window_label,
)
from lib.ranked import ranked_table

# =============================================================================
# Page config
# =============================================================================
st.set_page_config(
    page_title="Positionnement | UL Bibliometrics",
    page_icon="📍",
    layout="wide",
)

st.title("📍 Positionnement")
st.caption(
    "Cette page répond à : où la recherche lorraine se distingue-t-elle, comment son "
    "portefeuille évolue-t-il, et comment se situe-t-il face à la France et à un panel "
    "de pairs ?"
)
st.caption(
    f"Frontière scientifique, sujets émergents, diversité disciplinaire et structure "
    f"co-disciplinaire du portefeuille ({window_label()})."
)

# W5/S4 chassis: 3 sidebar toggles (conference, artifact, I-SITE overlay) + snapshot badge.
_controls_state = controls.sidebar()
include_conference = _controls_state["include_conference"]
_ARTIFACT_ON = _controls_state[ARTIFACT_TOGGLE_KEY]
_ISITE_ON = _controls_state[ISITE_OVERLAY_KEY]

# This page's content is entirely NEW (post-split) and every panel that recomputes under
# the artifact toggle does so by swapping to a pre-built _xa twin COLUMN (controls.xa),
# never by dropping a row on this page (the one row-dropping candidate, the emerging-
# topics texture grain, never carries a True artifact_flag by construction -- the top-20
# list is already built from the KEPT-topic population). Neither controls.banner() ("ON
# really drops rows") nor controls.ships_v2_strip() ("nothing is recomputed") describes
# that shape honestly, so -- matching page 4's own choice for its post-split NEW panels
# -- this page skips the blanket strip and discloses the artifact state inline, per
# panel, where it actually changes a number. Logged in progress/PC_positionnement.md.
controls.filtered_by_strip(page="positionnement")

_facts = get_corpus_facts_df()
_SNAPSHOT_DATE = str(_facts["snapshot_date"].iloc[0]) if len(_facts) else "?"
_CONF_STATE_VALUE = "all" if include_conference else "no_conf"


@st.cache_data
def _load_table(name: str) -> pd.DataFrame:
    """Generic cached parquet loader, local to this page (fence: page 5 only)."""
    return pd.read_parquet(DATA_DIR / f"{name}.parquet")


def _state(subset: str = "all", deferred: list | None = None) -> exports.ExportState:
    return exports.ExportState(
        snapshot=_SNAPSHOT_DATE, conf=include_conference, artifact=_ARTIFACT_ON,
        subset=subset, artifact_applied=_ARTIFACT_ON, deferred_twins=deferred or [],
    )


# Taxonomy lookups (shared across panels)
domain_id2name = get_domain_id_to_name()
field_id2name = get_field_id_to_name()
field_id2domain = get_field_id_to_domain_id()
field_order = get_field_order_by_domain()

FOCAL_BLUE = "#0072B2"

# =============================================================================
# Panel 1 -- Strategic cross (T9): frontier positioning x specialisation, by field
# Carried over from page 4's own T9 (BUILD_PLAN P-C), re-based on the isite_overlay
# toggle instead of the retired global perimeter selector.
# =============================================================================
st.markdown("---")
st.markdown("## Spécialisation et positionnement frontière, champ par champ")

df_frontier = _load_table("thm_frontier")
df_special = _load_table("thm_specialisation")

_panel_all = df_frontier[
    (df_frontier["row_kind"] == "panel") & (df_frontier["perimeter_id"] == "all")
    & (df_frontier["conf_state"] == _CONF_STATE_VALUE)
].copy()
_neutral_point = float(_panel_all["neutral_point"].iloc[0]) if not _panel_all.empty else 51.0
_baseline_vintage = str(_panel_all["baseline_vintage"].iloc[0]) if not _panel_all.empty else "?"

_spec_all = df_special[
    (df_special["level"] == "field") & (df_special["conf_state"] == _CONF_STATE_VALUE)
    & (df_special["subset_id"] == "all")
].copy()

_raw_col = controls.xa(_panel_all, "raw_frontier_share")
_std_col = controls.xa(_panel_all, "field_standardised_share")
_lq_col = controls.xa(_spec_all, "activity_index_lq")
_ulw_col = controls.xa(_spec_all, "ul_works")

_panel_all["field_id_int"] = _panel_all["field_id"].astype(int)
_panel_all["field_name"] = _panel_all["field_id_int"].map(field_id2name)
_panel_all["domain_name"] = _panel_all["field_id_int"].map(field_id2domain).map(domain_id2name)
_spec_all["field_id_int"] = _spec_all["node_id"].astype(int)

_cross = _panel_all.merge(
    _spec_all[["field_id_int", _lq_col, _ulw_col, "france_works", "floor_flag"]].rename(
        columns={_lq_col: "lq", _ulw_col: "works", "floor_flag": "floor_flag_spec"}),
    on="field_id_int", how="left",
)
_cross = _cross.dropna(subset=["lq", _std_col]).copy()
_cross["works"] = _cross["works"].astype(float)
_cross["floor_flag_spec"] = _cross["floor_flag_spec"].fillna(False)

# I-SITE second series (OVERLAY_MATRIX: T9 panel rows are a ROW-SWAP twin, not a
# same-row column -- render as a second, darker-hued series, never a stacked segment).
_panel_isite = df_frontier[
    (df_frontier["row_kind"] == "panel") & (df_frontier["perimeter_id"] == "in_isite")
    & (df_frontier["conf_state"] == _CONF_STATE_VALUE)
].copy()
_spec_isite = df_special[
    (df_special["level"] == "field") & (df_special["conf_state"] == _CONF_STATE_VALUE)
    & (df_special["subset_id"] == "in_isite")
].copy()
_panel_isite["field_id_int"] = _panel_isite["field_id"].astype(int)
_spec_isite["field_id_int"] = _spec_isite["node_id"].astype(int)
_std_col_i = controls.xa(_panel_isite, "field_standardised_share")
_lq_col_i = controls.xa(_spec_isite, "activity_index_lq")
_ulw_col_i = controls.xa(_spec_isite, "ul_works")

_cross_isite = _panel_isite.merge(
    _spec_isite[["field_id_int", _lq_col_i, _ulw_col_i, "floor_flag"]].rename(
        columns={_lq_col_i: "lq_i", _ulw_col_i: "works_i", "floor_flag": "floor_i"}),
    on="field_id_int", how="left",
)
_cross_isite = _cross_isite[
    _cross_isite["lq_i"].notna() & _cross_isite[_std_col_i].notna()
    & (~_cross_isite["floor_i"].fillna(True))
].copy()
_cross_isite["domain_name"] = _cross_isite["field_id_int"].map(field_id2domain).map(domain_id2name)
_cross_isite["field_name"] = _cross_isite["field_id_int"].map(field_id2name)

_t9_axis_type = log_linear_toggle("t9_axis_linear", label="échelle linéaire (LQ)")

st.markdown(
    "**Comment lire ce graphique** : chaque point est un champ ; l'axe horizontal donne la "
    "spécialisation (LQ vs France, point neutre = 1) et l'axe vertical, la part frontière "
    "standardisée par champ (point neutre = attendu mondial). La taille du point suit le "
    "nombre de travaux lorrains ; les points creux sont sous le seuil de fiabilité (moins de "
    "30 travaux)."
)

fig_t9 = go.Figure()
_normal = _cross[~_cross["floor_flag_spec"]]
_floor = _cross[_cross["floor_flag_spec"]]

if not _normal.empty:
    fig_t9.add_trace(go.Scatter(
        x=_normal["lq"], y=_normal[_std_col], mode="markers", name="Corpus entier",
        marker=dict(
            size=(_normal["works"].clip(lower=1) ** 0.5) * 1.4,
            color=[DOMAIN_COLORS.get(d, "#7f7f7f") for d in _normal["domain_name"]],
            line=dict(width=0.5, color="white"),
        ),
        text=_normal["field_name"],
        customdata=np.stack([_normal[_raw_col].astype(float), _normal["works"]], axis=-1),
        hovertemplate=(
            "<b>%{text}</b><br>LQ : %{x:.2f}<br>Frontière standardisée : %{y:.1f}<br>"
            "Frontière brute (info) : %{customdata[0]:.1f}<br>Travaux UL : "
            "%{customdata[1]:,.0f}<extra></extra>"
        ),
    ))
if not _floor.empty:
    fig_t9.add_trace(go.Scatter(
        x=_floor["lq"], y=_floor[_std_col], mode="markers", name="Sous le seuil (n<30)",
        marker=dict(
            size=(_floor["works"].clip(lower=1) ** 0.5) * 1.4,
            color="rgba(255,255,255,0)", line=dict(width=2, color=controls.DEFERRED_GREY),
        ),
        text=_floor["field_name"],
        hovertemplate="<b>%{text}</b> (n<30)<br>LQ : %{x:.2f}<br>Frontière standardisée : %{y:.1f}<extra></extra>",
    ))
if _ISITE_ON and not _cross_isite.empty:
    fig_t9.add_trace(go.Scatter(
        x=_cross_isite["lq_i"], y=_cross_isite[_std_col_i], mode="markers",
        name="dont I-SITE (n≥30)",
        marker=dict(
            size=(_cross_isite["works_i"].astype(float).clip(lower=1) ** 0.5) * 1.4,
            symbol="diamond",
            color=[ov.darken(DOMAIN_COLORS.get(d, "#7f7f7f")) for d in _cross_isite["domain_name"]],
            line=dict(width=1, color="white"),
        ),
        text=_cross_isite["field_name"],
        hovertemplate=(
            "<b>%{text}</b> (I-SITE)<br>LQ I-SITE : %{x:.2f}<br>"
            "Frontière standardisée I-SITE : %{y:.1f}<extra></extra>"
        ),
    ))

fig_t9.add_vline(x=1.0, line_dash="dash", line_color="#8C9196",
                  annotation_text="France = 1", annotation_position="top")
fig_t9.add_hline(y=_neutral_point, line_dash="dash", line_color="#8C9196",
                  annotation_text=f"Point neutre ({_neutral_point:.0f})", annotation_position="right")
for _xa_, _ya_, _txt_ in [(0.98, 0.98, "Forces établies"), (0.02, 0.98, "Paris"),
                          (0.98, 0.02, "Bases solides"), (0.02, 0.02, "Périphérie")]:
    fig_t9.add_annotation(
        x=_xa_, y=_ya_, xref="paper", yref="paper", text=_txt_, showarrow=False,
        font=dict(size=11, color="#5A5F66"),
        xanchor="right" if _xa_ > 0.5 else "left", yanchor="top" if _ya_ > 0.5 else "bottom",
    )
fig_t9.update_layout(
    xaxis=dict(type=_t9_axis_type, title="LQ vs France"),
    yaxis=dict(title="Frontière standardisée par champ (0-100)"),
    height=560, template="plotly_white", margin=dict(t=30, l=10, r=10, b=10),
)
st.plotly_chart(fig_t9, width="stretch")

if _ISITE_ON:
    st.caption(
        f":grey[{len(_cross_isite)} champ(s) sur {len(_cross)} disposent d'un point I-SITE "
        "fiable (quotient de localisation et part frontière calculés sur au moins 30 travaux "
        "I-SITE) ; les autres restent sous le seuil et ne sont pas tracés, jamais remplacés "
        "par une valeur fabriquée.]"
    )
st.caption(
    f":grey[Base frontière : {_baseline_vintage}. Le score brut ne figure qu'en infobulle, "
    "jamais en axe : un score standardisé plus bas ne signifie pas « moins important », "
    "potentiellement un champ plus fondamental ou plus établi.]"
)

st.markdown("**Explorer un champ sur OpenAlex**")
_t9_field_options = sorted(_cross["field_name"].dropna().unique().tolist())
if _t9_field_options:
    _t9_pick = st.selectbox("Champ :", _t9_field_options, key="t9_field_pick")
    _t9_row = _cross.loc[_cross["field_name"] == _t9_pick].iloc[0]
    _t9_fid = int(_t9_row["field_id_int"])
    _t9_url = links.openalex_url(UL_OPENALEX_ID, scope="lineage", node=("field", _t9_fid))
    _c1, _c2 = st.columns([6, 1])
    _c1.metric(f"Travaux lorrains — {_t9_pick}", fr_int(_t9_row["works"]))
    with _c2:
        st.markdown("&nbsp;")
        links.link_icon(_t9_url)

exports.attach_download(
    st, _cross[["field_name", "domain_name", "lq", _std_col, _raw_col, "works", "floor_flag_spec"]],
    "positionnement", "cross-frontiere-specialisation", _state("all"),
)

# =============================================================================
# Panel 2 -- Emerging topics, topic grain, query-able (R11 FULL DEPTH)
# Ruling R11 (2026-08-18): materialized depth = FULL at site level -- the owner's own named
# acceptance example is "type 'quantum' -> see the position of ALL topics containing quantum".
# Data source is now `thm_frontier_topics` (ALL ~3,274 UL topics x conf_state), not
# thm_frontier's own 20-row global top-slice (df_frontier, still used unchanged by Panel 1
# above): every topic the corpus actually uses is present, in or out of the frontier catalog.
# =============================================================================
st.markdown("---")
st.markdown("## Position frontière des sujets du corpus")

df_frontier_topics = _load_table("thm_frontier_topics")
_topics_all = df_frontier_topics[
    df_frontier_topics["conf_state"] == _CONF_STATE_VALUE
].copy()

_ulw_t = controls.xa(_topics_all, "ul_works")
_isw_t = controls.xa(_topics_all, "isite_works")

_topics_all["UL works"] = _topics_all[_ulw_t].fillna(0).astype(int)
_topics_all["Réf."] = controls.marker_dagger_column(_topics_all, "artifact_flag")

_topics_display_cols = ["topic_name", "Standardised score", "UL works", "Réf."]
_progress_cols_topics: dict = {}
if _ISITE_ON:
    _topics_all["I-SITE share"] = np.where(
        _topics_all["UL works"] > 0,
        (_topics_all[_isw_t].astype(float) / _topics_all["UL works"].astype(float) * 100).round(1),
        np.nan,
    )
    _topics_display_cols.append("I-SITE share")
    _progress_cols_topics["I-SITE share"] = {
        "help": "Part des travaux du sujet relevant du périmètre I-SITE (dont I-SITE).",
        "min_value": 0, "max_value": 100,
    }

# Rank on the RAW numeric score first (NaN sorts last by construction) -- only AFTER sorting is
# the display value built, so a score-NULL topic never fabricates a position: it renders its own
# works below every scored topic, with an honest "hors référentiel de score" state, never a 0 and
# never silently omitted from the query.
_topics_all = _topics_all.sort_values(
    "frontier_score_std", ascending=False, na_position="last",
).reset_index(drop=True)
_topics_all["Standardised score"] = _topics_all["frontier_score_std"].apply(
    lambda v: round(float(v), 2) if pd.notna(v) else "hors référentiel de score"
)

_texture_display = _topics_all[_topics_display_cols].reset_index(drop=True)

st.markdown(
    "**Comment lire.** Le score de frontière situe un sujet par rapport à l'ensemble des "
    "sujets du référentiel mondial : il mesure à quel point un sujet est jeune et en "
    "émergence dans la littérature, **jamais** la croissance du volume lorrain sur ce sujet. "
    "Les premières lignes s'affichent par défaut ; la recherche par mot-clé fait apparaître "
    "tous les sujets correspondants, y compris ceux hors du référentiel de score, qui gardent "
    "leurs travaux lorrains et une raison explicite plutôt qu'une position fabriquée."
)
st.caption(
    "**Pourquoi cet indicateur.** Un score bas ne se lit jamais comme une absence de "
    "frontière : il peut désigner une recherche fondationnelle, établie plutôt qu'émergente. "
    "L'intérêt du panneau est de repérer où le site est déjà présent sur des sujets que la "
    "littérature mondiale commence tout juste à structurer."
)

_visible_topics = ranked_table(
    _texture_display, key="emerging_topics", id_col="topic_name",
    search_cols=["topic_name"], has_members=False,
    progress_cols=_progress_cols_topics,
    ref_labels={
        "topic_name": "Topic", "UL works": "Travaux UL",
        "Standardised score": "Score standardisé", "I-SITE share": "Part I-SITE",
    },
)
_n_artifact_topics = artifact_topics_count()
st.caption(
    f":grey[Les topics hors référentiel mondial ({fr_int(_n_artifact_topics)} au total, "
    "marqués † en colonne « Réf. ») restent dans cette liste avec leurs travaux lorrains : "
    "seul leur score de frontière est absent, jamais remplacé par une position fabriquée.]"
)
st.caption(
    ":grey[Ce tableau porte les sujets déjà documentés par le corpus lorrain (au moins un "
    "travail) ; le catalogue complet du référentiel, y compris les sujets à zéro publication, "
    "est consultable sur la page **🔬 Portefeuille thématique**.]"
)
exports.attach_download(st, _visible_topics, "positionnement", "sujets-emergents", _state("all"))

# =============================================================================
# Panel 3 -- Frontier x labs crossing (R16): lab grain, NO peer context
# =============================================================================
st.markdown("---")
st.markdown("## Comment la position frontière varie d'un laboratoire lorrain à l'autre")

df_labs_fr = _load_table("thm_frontier_labs")
_labs = df_labs_fr[df_labs_fr["conf_state"] == _CONF_STATE_VALUE].copy()
st.caption(
    f"Un croisement n'est pas une comparaison : cette vue décrit la variation interne au "
    f"site, sans aucun point de repère externe ({fr_int(len(_labs))} structures, dont la "
    "catégorie « sans laboratoire »)."
)

_wn_c = controls.xa(_labs, "works_n")
_fwn_c = controls.xa(_labs, "frontier_works_n")
_fs_c = controls.xa(_labs, "frontier_share")
_fss_c = controls.xa(_labs, "field_standardised_share")
_iwn_c = controls.xa(_labs, "isite_works_n")
_ifwn_c = controls.xa(_labs, "isite_frontier_works_n")

_labs["Works"] = _labs[_wn_c].astype(int)
_labs["Frontier works"] = _labs[_fwn_c].astype(int)
_labs["Frontier share (%)"] = (_labs[_fs_c] * 100).round(1)
_labs["Standardised share (%)"] = (_labs[_fss_c] * 100).round(1)
_labs["_isite_frontier_n"] = _labs[_ifwn_c]

_ranked_labs = _labs.dropna(subset=["Standardised share (%)"]).sort_values(
    "Standardised share (%)", ascending=False,
)
_top15 = _ranked_labs.head(15).sort_values("Standardised share (%)")

st.markdown(
    f"**Comment lire ce graphique** : les {len(_top15)} laboratoires à la part frontière la "
    "plus élevée une fois ramenée au même mélange disciplinaire que le corpus entier (barre "
    "= travaux « frontière », teinte foncée = ceux relevant du périmètre I-SITE)."
)
st.caption(
    "Une cellule laboratoire × champ portant moins de trois travaux est exclue du calcul "
    "pour ce laboratoire : sans ce plancher, un travail isolé dans un champ lourdement "
    "pondéré suffirait à multiplier la part standardisée d'une structure."
)

fig_labs = ov.overlay_bars(
    categories=_top15["lab"].tolist(),
    totals=_top15["Frontier works"].tolist(),
    isite=_top15["_isite_frontier_n"].tolist(),
    colors=FOCAL_BLUE,
    isite_on=_ISITE_ON,
    orientation="h",
)
fig_labs.update_layout(
    height=max(420, len(_top15) * 32 + 100),
    xaxis=dict(title="Travaux « frontière »"), yaxis=dict(title=""),
    template="plotly_white", margin=dict(t=20, l=10, r=10, b=10),
)
st.plotly_chart(fig_labs, width="stretch")

_labs_display = _ranked_labs[
    ["lab", "Works", "Frontier works", "Frontier share (%)", "Standardised share (%)"]
].copy()
_progress_cols_labs = {
    "Frontier share (%)": {
        "help": "Part des travaux du laboratoire dans le décile supérieur des topics retenus.",
        "min_value": 0, "max_value": 100,
    },
    "Standardised share (%)": {
        "help": "Même construction, ramenée au mélange disciplinaire du corpus entier — "
                "seule colonne comparable ENTRE laboratoires.",
        "min_value": 0, "max_value": 100,
    },
}
if _ISITE_ON:
    _ranked_labs = _ranked_labs.copy()
    _ranked_labs["I-SITE share of frontier works (%)"] = np.where(
        _ranked_labs["Frontier works"] > 0,
        (_ranked_labs["_isite_frontier_n"] / _ranked_labs["Frontier works"] * 100).round(1),
        np.nan,
    )
    _labs_display["I-SITE share of frontier works (%)"] = _ranked_labs["I-SITE share of frontier works (%)"]
    _progress_cols_labs["I-SITE share of frontier works (%)"] = {"min_value": 0, "max_value": 100}

st.markdown(
    f"**Comment lire ce tableau** : les {fr_int(len(_labs_display))} structures, triées par "
    "part standardisée (seule colonne comparable entre laboratoires de mélange disciplinaire "
    "différent). Rechercher un nom de laboratoire fait apparaître sa position, même hors du "
    "top 10."
)
_visible_labs = ranked_table(
    _labs_display, key="frontier_labs", id_col="lab",
    search_cols=["lab"], has_members=False,
    progress_cols=_progress_cols_labs,
    ref_labels={
        "lab": "Laboratoire", "Works": "Publications", "Frontier works": "Travaux frontière",
        "Frontier share (%)": "Part frontière (%)",
        "Standardised share (%)": "Part standardisée (%)",
    },
)
_n_below_floor_labs = int(_labs["Standardised share (%)"].isna().sum())
if _n_below_floor_labs:
    st.caption(
        f":grey[{_n_below_floor_labs} structure(s) sous 30 travaux exploitables : part non "
        "affichée (jamais 0 %).]"
    )
exports.attach_download(st, _visible_labs, "positionnement", "frontiere-labos", _state("all"))

# =============================================================================
# Panel 4 -- Diversity (T3 / T3c): Rao-Stirling/DIV tiles + frozen momentum chip
# =============================================================================
st.markdown("---")
st.markdown("## Diversité disciplinaire du portefeuille")
st.caption(
    "Indice calculé au grain sous-champ : une mesure de forme du portefeuille, jamais un "
    "classement."
)
st.markdown(
    "**Comment lire.** Trois composantes et leur synthèse : la variété compte les "
    "sous-champs présents, l'équilibre mesure la répartition entre eux, la disparité la "
    "distance intellectuelle entre les sous-champs mobilisés. L'indice de synthèse combine "
    "les trois."
)

df_div = _load_table("thm_diversity")
_mom_facts = _load_table("ptn_mom_facts")
_mom_row = _mom_facts.loc[_mom_facts["conf_state"] == "all"]
_mom_w1_label = str(_mom_row["mom_w1_label"].iloc[0]) if len(_mom_row) else "?"
_mom_w2_label = str(_mom_row["mom_w2_label"].iloc[0]) if len(_mom_row) else "?"
_div_all = df_div[
    (df_div["perimeter_id"] == "all") & (df_div["conf_state"] == _CONF_STATE_VALUE)
].sort_values("year").copy()

_var_c = controls.xa(_div_all, "variety")
_bal_c = controls.xa(_div_all, "balance")
_disp_c = controls.xa(_div_all, "disparity")
_rs_c = controls.xa(_div_all, "rao_stirling")
_nw_c = controls.xa(_div_all, "n_works")

if _div_all.empty:
    st.info("Aucune ligne de diversité pour cet état de conférence.")
else:
    _latest = _div_all.iloc[-1]
    _tiles = st.columns(4)
    _tiles[0].metric("Variety", na_metric(_latest[_var_c], "{:.3f}"))
    _tiles[1].metric("Balance", na_metric(_latest[_bal_c], "{:.3f}"))
    _tiles[2].metric("Disparity", na_metric(_latest[_disp_c], "{:.3f}"))
    _tiles[3].metric("Rao-Stirling (DIV)", na_metric(_latest[_rs_c], "{:.3f}"))
    st.caption(
        f":grey[Dernière année disponible : {int(_latest['year'])} — n = "
        f"{fr_int(_latest[_nw_c])} publications.]"
    )
    st.caption(
        "**Pourquoi cet indicateur.** Un portefeuille peut couvrir beaucoup de sujets tout "
        "en restant concentré, ou couvrir peu de sujets très éloignés les uns des autres. La "
        "diversité mesure la forme, jamais la qualité : elle sert à discuter d'un équilibre, "
        "pas à le noter."
    )

    col_spark, col_delta = st.columns([3, 1])
    with col_spark:
        st.markdown("**Évolution annuelle (Rao-Stirling / DIV)**")
        _spark = _div_all.copy()
        _spark["rs_display"] = np.where(_spark["floor_flag"], np.nan, _spark[_rs_c])
        fig_spark = go.Figure(go.Scatter(
            x=_spark["year"], y=_spark["rs_display"], mode="lines+markers",
            line=dict(color=FOCAL_BLUE), marker=dict(size=7), connectgaps=False,
        ))
        fig_spark.update_layout(
            height=220, margin=dict(t=10, l=10, r=10, b=10),
            xaxis=dict(dtick=1, title=""), yaxis=dict(title="DIV"), template="plotly_white",
        )
        st.plotly_chart(fig_spark, width="stretch")
        _n_floor_years = int(_spark["floor_flag"].sum())
        if _n_floor_years:
            st.caption(
                f":grey[{_n_floor_years} année(s) sous le seuil (n<30) : point absent, "
                "jamais fabriqué.]"
            )
    with col_delta:
        st.markdown("**Évolution de la diversité**")
        st.caption(f":grey[Comparaison de deux fenêtres : {_mom_w1_label} et {_mom_w2_label}.]")
        _delta_class = _latest["delta_class"]
        _delta_map = {"up": ("en hausse", "#009E73"), "down": ("en retrait", "#D55E00"),
                      "stable": ("stable", "#5A5F66")}
        if _ARTIFACT_ON:
            st.markdown(
                f"<span style='color:{controls.DEFERRED_GREY};font-weight:600;'>Δ figé {DAGGER}</span>",
                unsafe_allow_html=True,
            )
            st.caption(
                ":grey[Famille de mesure figée sous le filtre « hors référentiel » : elle "
                "reste affichée telle quelle plutôt que recalculée sur un sous-ensemble, ce "
                "qui produirait quatre variantes de la même mesure sans référence stable "
                "pour aucune.]"
            )
        elif _delta_class in _delta_map:
            _label, _color = _delta_map[_delta_class]
            st.markdown(f"<span style='color:{_color};font-weight:700;'>● {_label}</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span style='color:#B9B9B9;'>— non significatif</span>", unsafe_allow_html=True)

    if _ISITE_ON:
        st.markdown("**Le même indice, calculé sur le seul périmètre I-SITE**")
        st.caption(
            ":grey[Un indice composite ne se décompose pas en « part I-SITE » : ce second "
            "jeu de tuiles est un calcul indépendant sur le sous-corpus I-SITE, jamais une "
            "part du premier.]"
        )
        _div_isite = df_div[
            (df_div["perimeter_id"] == "in_isite") & (df_div["conf_state"] == _CONF_STATE_VALUE)
        ].sort_values("year").copy()
        if _div_isite.empty:
            st.caption(":grey[Aucune ligne I-SITE disponible pour cet état de conférence.]")
        else:
            _latest_i = _div_isite.iloc[-1]
            _var_ci = controls.xa(_div_isite, "variety")
            _bal_ci = controls.xa(_div_isite, "balance")
            _disp_ci = controls.xa(_div_isite, "disparity")
            _rs_ci = controls.xa(_div_isite, "rao_stirling")
            _nw_ci = controls.xa(_div_isite, "n_works")
            _tiles_i = st.columns(4)
            _tiles_i[0].metric("Variety (I-SITE)", na_metric(_latest_i[_var_ci], "{:.3f}"))
            _tiles_i[1].metric("Balance (I-SITE)", na_metric(_latest_i[_bal_ci], "{:.3f}"))
            _tiles_i[2].metric("Disparity (I-SITE)", na_metric(_latest_i[_disp_ci], "{:.3f}"))
            _tiles_i[3].metric("Rao-Stirling (I-SITE)", na_metric(_latest_i[_rs_ci], "{:.3f}"))
            st.caption(
                f":grey[n = {fr_int(_latest_i[_nw_ci])} publications, année "
                f"{int(_latest_i['year'])}.]"
            )

    # Pass-6 fix round (S-LENS D1): this forward cross-reference used to name a section
    # title REPLACED this pass (was "Comment Lorraine se situe face a la France et a neuf
    # pairs", now "Position face a la France et aux pairs retenus", see markdown a few
    # dozen lines below) and hardcoded the peer count in words. Both repaired here: the
    # title now matches verbatim, and the count is computed from bench_peers.parquet (the
    # canonical peer registry -- distinct entity_id whose rung is not the focal "FOCAL"
    # row), not a duplicated literal that could drift from panel 5's own count.
    _n_peers_xref = int(
        _load_table("bench_peers").pipe(lambda d: d.loc[d["rung"] != "FOCAL", "entity_id"].nunique())
    )
    st.caption(
        f"Mise en contexte face aux pairs : voir plus bas, « Position face à la France et "
        f"aux pairs retenus » ({fr_int(_n_peers_xref)} pairs)."
    )
    exports.attach_download(
        st, _div_all[["year", _var_c, _bal_c, _disp_c, _rs_c, _nw_c, "delta_class", "delta_p_value", "floor_flag"]],
        "positionnement", "diversite",
        _state("all", deferred=(["delta_class", "delta_p_value"] if _ARTIFACT_ON else [])),
    )

# =============================================================================
# Panel 5 -- Peer context (R6/R7): bench_positioning + bench_diversity, UL vs 9 peers
# Site-level totals of isolated indicators DO need peer context (R16's own rule) --
# unlike panel 3's lab crossing.
# =============================================================================
st.markdown("---")

df_pos = _load_table("bench_positioning")
df_bdiv = _load_table("bench_diversity")

_pos = df_pos[df_pos["conf_state"] == _CONF_STATE_VALUE].copy()
_pos["field_id_int"] = _pos["field_id"].astype(int)
_pos["field_name"] = _pos["field_id_int"].map(field_id2name)
_pos["is_ul"] = _pos["entity_id"] == UL_OPENALEX_ID
_neutral_peer = float(_pos["neutral_point"].iloc[0]) if not _pos.empty else _neutral_point
_n_peers = int(_pos.loc[~_pos["is_ul"], "entity_id"].nunique())

st.markdown("## Position face à la France et aux pairs retenus")
st.caption(
    f"{fr_int(_n_peers)} établissements comparables, arrêtés en atelier, et l'Université de "
    "Lorraine, tous mesurés à l'identifiant OpenAlex direct, sur la même fenêtre et les mêmes "
    "types de publication : une méthode symétrique par construction, jamais un aménagement "
    "pour l'un des deux côtés."
)

st.markdown(
    "**Comment lire ce graphique** : chaque ligne est un champ OpenAlex ; le point bleu situe "
    f"l'université de Lorraine, les points gris les {fr_int(_n_peers)} pairs (les pairs n'ont pas de "
    "périmètre I-SITE, la comparaison porte sur le corpus entier des deux côtés)."
)

_field_order_names = [field_id2name[f] for f in field_order if f in field_id2name]

fig_peer = go.Figure()
_peer_rows = _pos[~_pos["is_ul"]]
fig_peer.add_trace(go.Scatter(
    x=_peer_rows["field_standardised_share"], y=_peer_rows["field_name"], mode="markers",
    name=f"{fr_int(_n_peers)} pairs", marker=dict(size=7, color=controls.DEFERRED_GREY, opacity=0.75),
    customdata=_peer_rows[["entity_name", "rung"]],
    hovertemplate="<b>%{customdata[0]}</b> (%{customdata[1]})<br>%{y}<br>Part standardisée : %{x:.1f}<extra></extra>",
))
_ul_rows = _pos[_pos["is_ul"]]
fig_peer.add_trace(go.Scatter(
    x=_ul_rows["field_standardised_share"], y=_ul_rows["field_name"], mode="markers",
    name="Université de Lorraine",
    marker=dict(size=11, color=FOCAL_BLUE, line=dict(width=1, color="white")),
    hovertemplate="<b>Université de Lorraine</b><br>%{y}<br>Part standardisée : %{x:.1f}<extra></extra>",
))
fig_peer.add_vline(x=_neutral_peer, line_dash="dash", line_color="#8C9196",
                    annotation_text=f"Point neutre ({_neutral_peer:.0f})", annotation_position="top")
fig_peer.update_layout(
    xaxis=dict(title="Frontière standardisée par champ (0-100)"),
    yaxis=dict(title="", categoryarray=_field_order_names, categoryorder="array"),
    height=760, template="plotly_white", margin=dict(t=30, l=10, r=10, b=10),
)
st.plotly_chart(fig_peer, width="stretch")
st.caption(
    "**Pourquoi cet indicateur.** Le même écart se lit différemment selon le groupe de "
    "comparaison retenu : un panel de parité, un panel d'aspiration et des voisins "
    "transfrontaliers ne racontent pas la même chose. Le choix du groupe est une décision "
    "de l'établissement, jamais un résultat de l'outil."
)

_min_cov = _pos["join_coverage_pct"].min()
_max_cov = _pos["join_coverage_pct"].max()
st.caption(
    f":grey[Couverture de correspondance entre le topic principal et la base frontière : "
    f"entre {fr_pct(_min_cov)} et {fr_pct(_max_cov)} selon l'entité. Cette table n'est pas "
    "filtrable par le bouton « hors référentiel » : les corpus des pairs sont tirés en "
    "direct d'OpenAlex, hors de l'instantané local qui porte la liste des topics exclus.]"
)

_peer_roster = _pos.loc[~_pos["is_ul"], ["entity_id", "entity_name", "rung", "country"]].drop_duplicates()
_peer_roster = _peer_roster.copy()
_peer_roster["OpenAlex"] = _peer_roster["entity_id"].map(lambda eid: links.openalex_url(eid, scope="direct"))
st.dataframe(
    _peer_roster[["entity_name", "rung", "country", "OpenAlex"]],
    width="stretch", hide_index=True,
    column_config={
        "entity_name": "Entité", "rung": "Groupe", "country": "Pays",
        "OpenAlex": st.column_config.LinkColumn("OpenAlex", display_text="↗"),
    },
)
exports.attach_download(st, _pos, "positionnement", "contexte-pairs-frontiere", _state("all"))

st.markdown("### Diversité disciplinaire face aux pairs")
_bdiv_state = df_bdiv[df_bdiv["conf_state"] == _CONF_STATE_VALUE].copy()
_bdiv_state["OpenAlex"] = _bdiv_state["entity_id"].map(lambda eid: links.openalex_url(eid, scope="direct"))
_bdiv_display = _bdiv_state[
    ["entity_name", "rung", "country", "n_works", "variety", "balance", "disparity", "rao_stirling", "OpenAlex"]
].sort_values("rao_stirling", ascending=False).round(
    {"variety": 3, "balance": 3, "disparity": 3, "rao_stirling": 3}
)
st.dataframe(
    _bdiv_display, width="stretch", hide_index=True,
    column_config={
        "entity_name": "Entité", "rung": "Groupe", "country": "Pays", "n_works": "Publications",
        "variety": "Variété", "balance": "Équilibre", "disparity": "Disparité",
        "rao_stirling": "Rao-Stirling (DIV)",
        "OpenAlex": st.column_config.LinkColumn("OpenAlex", display_text="↗"),
    },
)

_ul_bdiv = _bdiv_state.loc[_bdiv_state["entity_id"] == UL_OPENALEX_ID, "rao_stirling"]
_ul_bdiv_val = float(_ul_bdiv.iloc[0]) if len(_ul_bdiv) else float("nan")
_ul_thm_div = _div_all.loc[_div_all["year"] == 2019, _rs_c] if not _div_all.empty else pd.Series(dtype=float)
_ul_thm_div_val = float(_ul_thm_div.iloc[0]) if len(_ul_thm_div) else float("nan")
st.caption(
    f":grey[Méthode : topic principal des deux côtés ; la matrice de disparité entre "
    "sous-champs est construite une seule fois sur le corpus lorrain complet et réutilisée "
    f"sans changement pour les dix entités. La ligne Lorraine de ce tableau "
    f"({na_metric(_ul_bdiv_val, '{:.4f}')}) et la valeur publiée plus haut "
    f"({na_metric(_ul_thm_div_val, '{:.4f}')}) portent sur deux périmètres et deux fenêtres "
    "différents : les deux sont nommées ensemble, jamais l'une à la place de l'autre.]"
)
exports.attach_download(st, _bdiv_display, "positionnement", "contexte-pairs-diversite", _state("all"))

# =============================================================================
# Panel 6 -- Co-discipline (T3b) REDESIGN
# The old 26x26 viridis heatmap is ruled unreadable (colour, size, no explanation).
# Replaced by: (a) a query-able top-pairs ranked table (field grain, R11), and
# (b) a 4x4 domain-block heatmap that carries the block structure the 676-cell version
# drowned. Full justification: progress/PC_positionnement.md.
# =============================================================================
st.markdown("---")
st.markdown("## Quels champs travaillent le plus souvent ensemble")
st.markdown(
    "**Comment lire.** Chaque ligne du tableau est une paire de champs partagée par au moins "
    "un travail (tout topic assigné, pas seulement le principal) ; la carte agrégée par "
    "domaine, plus bas, en donne la structure d'ensemble."
)

df_cd = _load_table("thm_codiscipline")
_cd_perimeter = "in_isite" if _ISITE_ON else "all"
_cd = df_cd[
    (df_cd["perimeter_id"] == _cd_perimeter) & (df_cd["conf_state"] == _CONF_STATE_VALUE)
].copy()
_cw_c = controls.xa(_cd, "co_works")

_cd["field_a_int"] = _cd["field_a"].astype(int)
_cd["field_b_int"] = _cd["field_b"].astype(int)
_cd["name_a"] = _cd["field_a_int"].map(field_id2name)
_cd["name_b"] = _cd["field_b_int"].map(field_id2name)
_cd["domain_a"] = _cd["field_a_int"].map(field_id2domain)
_cd["domain_b"] = _cd["field_b_int"].map(field_id2domain)

if _ISITE_ON:
    st.caption(
        ":grey[Vue basculée sur le seul périmètre I-SITE : les décomptes sont beaucoup plus "
        "petits — c'est la structure co-disciplinaire du sous-corpus I-SITE lui-même, jamais "
        "une part du corpus entier ci-dessous.]"
    )

st.markdown("**Paires de champs les plus actives**")
st.markdown(
    "**Comment lire ce tableau** : chaque ligne est une paire de champs distincts partagée "
    "par au moins un travail (tout topic assigné, pas seulement le principal). Rechercher un "
    "nom de champ affiche toutes ses paires, même hors du top 10 par défaut."
)

_off = _cd[_cd["field_a_int"] < _cd["field_b_int"]].copy()
_total_inter = float(_off[_cw_c].sum())
_off["Field A"] = _off["name_a"]
_off["Field B"] = _off["name_b"]
_off["Co-works"] = _off[_cw_c].astype(int)
_off["Share of inter-field volume (%)"] = np.where(
    _total_inter > 0, (_off[_cw_c] / _total_inter * 100).round(2), np.nan,
)
_off_display = _off[
    ["Field A", "Field B", "Co-works", "Share of inter-field volume (%)"]
].sort_values("Co-works", ascending=False).reset_index(drop=True)

_max_share_val = _off_display["Share of inter-field volume (%)"].max()
_max_share_val = round(float(_max_share_val), 2) if pd.notna(_max_share_val) else 1.0

_visible_pairs = ranked_table(
    _off_display, key="codiscipline_pairs", id_col="Field A",
    search_cols=["Field A", "Field B"], has_members=False,
    progress_cols={
        "Share of inter-field volume (%)": {
            "help": "Part de cette paire dans le total des co-publications inter-champs "
                    "(paires distinctes, champ = champ exclu).",
            "min_value": 0, "max_value": _max_share_val, "format": "%.2f%%",
        },
    },
    ref_labels={
        "Field A": "Champ A", "Field B": "Champ B", "Co-works": "Co-publications",
        "Share of inter-field volume (%)": "Part du volume inter-champs (%)",
    },
)
_n_floor_pairs = int(_off["floor_flag"].sum())
st.caption(
    f":grey[{_n_floor_pairs} paire(s) sur {len(_off)} sous le seuil (moins de 30 "
    "co-travaux) : elles restent dans la liste, cherchables, jamais masquées.]"
)
exports.attach_download(st, _visible_pairs, "positionnement", "codiscipline-paires", _state(_cd_perimeter))

st.markdown("**Structure par domaine (vue d'ensemble)**")
st.markdown(
    "**Comment lire cette carte.** Chaque cellule agrège toutes les paires de champs des "
    "deux domaines croisés ; la diagonale compte les travaux qui restent dans un seul "
    "domaine."
)

_dom_names_order = [domain_id2name[d] for d in DOMAIN_ORDER if d in domain_id2name]
_cd["domain_a_name"] = _cd["domain_a"].map(domain_id2name)
_cd["domain_b_name"] = _cd["domain_b"].map(domain_id2name)
# groupby-sum over the FULL symmetric matrix (not a hand-reduced half): this is a straight
# aggregation of the SAME 676 rows into a coarser (domain_a, domain_b) key, so the two
# totals reconcile by construction -- verified below (acceptance pin in test_page_pc.py).
_dom_pivot = _cd.groupby(["domain_a_name", "domain_b_name"])[_cw_c].sum().unstack(fill_value=0)
_dom_matrix = _dom_pivot.reindex(index=_dom_names_order, columns=_dom_names_order, fill_value=0)

_z = _dom_matrix.values
_z_max = float(np.nanmax(_z)) if _z.size else 1.0
fig_dom = go.Figure(go.Heatmap(
    z=_z, x=_dom_names_order, y=_dom_names_order, colorscale="Viridis",
    hovertemplate="%{y} × %{x}<br>Co-publications : %{z:,.0f}<extra></extra>",
    colorbar=dict(title="Co-works"),
))
_dom_annotations = [
    dict(
        x=_dom_names_order[j], y=_dom_names_order[i], text=fr_int(_z[i, j]), showarrow=False,
        font=dict(size=13, color="white" if _z[i, j] > _z_max * 0.5 else "black"),
    )
    for i in range(len(_dom_names_order)) for j in range(len(_dom_names_order))
]
fig_dom.update_layout(
    annotations=_dom_annotations, height=460,
    xaxis=dict(tickfont=dict(size=12)), yaxis=dict(tickfont=dict(size=12), autorange="reversed"),
    margin=dict(t=20, l=10, r=10, b=40),
)
st.plotly_chart(fig_dom, width="stretch")
_dom_export = _dom_matrix.copy()
_dom_export.index.name = "Domain"
exports.attach_download(
    st, _dom_export.reset_index(),
    "positionnement", "codiscipline-domaines", _state(_cd_perimeter),
)

# =============================================================================
# Footer
# =============================================================================
st.markdown("---")
st.caption(f"Données : Université de Lorraine, corpus {window_label()} (OpenAlex, snapshot {_SNAPSHOT_DATE}).")
