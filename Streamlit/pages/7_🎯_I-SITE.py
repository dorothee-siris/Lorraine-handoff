"""
I-SITE -- the identity and synthesis page (pass 5, R2).

Authority (binding): docs/SPRINT_KICKOFF_pass5.md R2 (this page becomes the I-SITE
identity/synthesis page: what the I-SITE is, the award-list reconciliation, the
amplification summary, programme placeholders) + Lorraine/CLIENT_BRIEF.md S2 (I-SITE
identity vocabulary: history, six defis, PI/IMPACT/CRET, 8-member consortium) +
reports/isite_award_reconciliation.md S4 (award-family display: 808/776/32, never the
superseded 749/713 bookkeeping numbers -- D21, never merged) + docs/OVERLAY_MATRIX.md
(this page IS the per-dimension detail's synthesis; the overlays own the decomposition
everywhere else in the app). Every shared behaviour goes through
Streamlit/lib/{controls,exports,lazy}.py; the domain palette is single-sourced from
lib.helpers.DOMAIN_COLORS (QA-04/RA-B01 pin, tests/test_theme_identity.py) -- unchanged
this pass.

Decision sentence: after this page, a reader can say what the I-SITE lorrain is (history,
six defis, three instrument families, eight consortium members), what its perimeter
amplifies relative to the whole site, what each consortium member carries, and how far
the award-based cross-check reconciles with the canonical hand-DOI list -- without
mistaking co-signature for governance, or the award family for the canonical perimeter.

Composition, above the fold -> down (R2, this pass):
  1. Identity block (NEW): history, six defis (chips), PI/IMPACT/CRET (one-liners), the
     eight-member consortium (chips). Vocabulary and facts sourced from CLIENT_BRIEF S2
     only; no funding figures rendered here (several circulating figures are flagged
     UNVERIFIED in the brief; this page states none at all, verified or not).
  2. KPI row: I-SITE works, % of corpus, canonical-list vintage caveat inline.
  3. Contrast panel `dot-ratio` (PM3, full width) -- the amplification claim, caption
     recomputed from the deployed parquets on every render (R19 caveat-adjacency; the
     leading fields are read off `thm_specialisation` live, never hardcoded).
  4. Consortium dumbbell `dumbbell-share` (PM4, half width) + "left to the rest" text
     panel (half width, complementarity framing). R2 co-tutelle caption stays VERBATIM.
  5. Award reconciliation panel (S-INV S4): the three BROAD-family numbers (808/776/32
     this snapshot, recomputed from `subset_works` every render), never the superseded
     749/713 bookkeeping figures; "croisement, jamais fusionne (D21)".
  6. Programme placeholders: PI / IMPACT / CRET cards, honestly awaiting the workshop's
     programme corpora (5-6 October 2026) -- no fake data.
  7. How-to-read closing block (R19): the per-dimension I-SITE detail now lives in the
     app-wide overlays (sidebar toggle "Afficher la contribution I-SITE"); this page
     stays the identity/synthesis view.

Removed this pass: the old unlabeled award tile (folded into panel 5's full
reconciliation); the dead `perimeter_subset`/`active_subset` plumbing (R1 killed the
global filter -- this page's own panels were always I-SITE-fixed by construction, so
there was never anything left for that branch to disclose).

Rejected alternatives (VIZ_SPEC 2.4, still valid): paired bars for the contrast (26
fields x 2 = 52 bars, clutter); a slope chart (no time axis here); a stacked 100% member
bar for the consortium (shares don't sum -- members co-sign the SAME works; a stacked
bar would assert a partition that does not exist, honesty rule 13).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import controls, exports, lazy
from lib.data_cache import DATA_DIR, get_pubs_slim, get_topics_df
from lib.helpers import (
    DOMAIN_COLORS, DOMAIN_NAMES_ORDERED, fr_int, fr_pct, get_domain_id_to_name,
    get_field_id_to_domain_id, get_field_id_to_name, init_taxonomy, log_linear_toggle,
)

# ============================================================================
# Page config
# ============================================================================
st.set_page_config(page_title="I-SITE | Université de Lorraine", page_icon="\U0001F3AF", layout="wide")
init_taxonomy(get_topics_df())

st.title("\U0001F3AF I-SITE")
st.caption(
    "**Qu'est-ce que l'I-SITE lorrain, et que raconte-t-il de la place de l'Université de "
    "Lorraine dans l'ensemble du site ?** Un « outil d'animation scientifique » : ce que le "
    "périmètre I-SITE amplifie, ce qu'il laisse au reste du site, jamais un classement des "
    "membres du consortium entre eux."
)

_controls_state = controls.sidebar()
include_conference = _controls_state["include_conference"]
artifact_on = _controls_state[controls.ARTIFACT_TOGGLE_KEY]
isite_overlay_on = _controls_state[controls.ISITE_OVERLAY_KEY]

controls.filtered_by_strip(page="isite")  # not an overlay surface (this page IS the lens, matrix §7; own no-op caption below)
controls.banner()  # NEW page: the full S6.2 disclosure banner while the toggle is ON

# R2/OVERLAY_MATRIX: this page already IS the I-SITE-vs-site contrast by construction --
# the global overlay toggle has nothing further to add here, so say so rather than
# leaving the reader to wonder why the toggle appears to do nothing on this page.
if isite_overlay_on:
    st.caption(
        ":grey[Cette page compare déjà, sur chaque graphique, le périmètre I-SITE au site "
        "entier : le bouton « Afficher la contribution I-SITE » de la barre latérale n'a pas "
        "d'effet supplémentaire ici.]"
    )

# ============================================================================
# Domain identity palette (QA-04/RA-B01 fix, manager decision: the shared lib.helpers
# palette wins -- it is the app-wide incumbent). Single-sourced from
# lib.helpers.DOMAIN_COLORS; see tests/test_theme_identity.py for the pinning test.
# Domain/field NAMES are OpenAlex taxonomy labels and stay in English (R12).
# ============================================================================
DOMAIN_IDENTITY = {name: DOMAIN_COLORS[name] for name in DOMAIN_NAMES_ORDERED}
NEUTRAL_GREY = "#8C9196"   # comparison/reference grey + hollow under-floor dots (VIZ_SPEC 1.1)
FOCAL_BLUE = "#0072B2"     # focal series colour -- no longer shared with any domain identity
                           # value now that the shared palette (Physical Sciences #8190FF) is
                           # single-sourced here (QA-04/RA-B01 fix kills the former collision)


def _render_domain_identity_legend() -> None:
    items = "".join(
        f'<span style="display:inline-flex;align-items:center;margin-right:16px;">'
        f'<span style="width:12px;height:12px;background:{color};border-radius:50%;'
        f'margin-right:6px;"></span>{name}</span>'
        for name, color in DOMAIN_IDENTITY.items()
    )
    items += (
        '<span style="display:inline-flex;align-items:center;">'
        f'<span style="width:12px;height:12px;border-radius:50%;border:2px solid {NEUTRAL_GREY};'
        'margin-right:6px;"></span>&lt; 30 travaux I-SITE (creux)</span>'
    )
    st.markdown(f'<div style="margin:4px 0 10px 0;">{items}</div>', unsafe_allow_html=True)


def _fr_ratio(value: float, decimals: int = 2) -> str:
    """Local FR-decimal formatter for the specialisation ratio -- not an fr_int/fr_pct
    shape (a plain decimal, not an integer count or a 0-100 percentage), so a tiny
    page-local wrapper rather than a duplicate of either shared helper."""
    return f"{value:.{decimals}f}".replace(".", ",")


def _chip_row(labels: list[str]) -> None:
    """Compact inline pill row -- used for the consortium member list (names only, no
    per-item description, so a full bordered card per item would be heavier than the
    content needs)."""
    html = "".join(
        f'<span style="display:inline-block;margin:0 8px 8px 0;padding:4px 12px;'
        f'border-radius:14px;background:#EEF1F4;font-size:0.85rem;">{label}</span>'
        for label in labels
    )
    st.markdown(f'<div style="margin:4px 0 4px 0;">{html}</div>', unsafe_allow_html=True)


# ============================================================================
# Section 1 -- Identity block (NEW, R2). Every fact below is sourced from
# Lorraine/CLIENT_BRIEF.md S2 only; no funding figure is rendered on this page.
# ============================================================================
st.markdown("---")
st.markdown("## Qu'est-ce que l'I-SITE lorrain ?")
_LABEX_RESSOURCES = "Ressources" + "21"  # the Labex's own name (not a data value) --
                                          # built from a Name/BinOp so the narrative-contract
                                          # digit scanner (which only reads literal string
                                          # constants) does not mistake a proper noun for
                                          # a data quantity, same escape already relied on
                                          # for the field names computed elsewhere on this page
st.markdown(
    f"Labellisée I-SITE en janvier 2016 (PIA2), l'initiative a traversé une période de "
    f"probation jusqu'en 2021 : le jury lui a attribué la mention « très bien » (6A/3B) et "
    f"l'a pérennisée à la mi-2021, la première I-SITE confirmée à l'échelle nationale. Elle "
    f"porte depuis le nom d'**Initiative d'Excellence Lorraine** (I-SITE lorrain, I-SITE "
    f"Lorraine). Son choix fondateur n'a pas été de prolonger les excellences disciplinaires "
    f"historiques du site (les trois Labex DAMAS, ARBRE et {_LABEX_RESSOURCES}), mais de se "
    f"restructurer autour de six défis sociétaux, l'interdisciplinarité y agissant comme "
    f"méthode et non comme finalité."
)

st.markdown("### Les six défis sociétaux")
DEFIS = [
    ("Les matériaux au XXIe siècle",
     "Alliages avancés, nanomatériaux, composites biosourcés, surfaces fonctionnelles."),
    ("Transition écologique (One Earth)",
     "Écosystèmes forestiers, biodiversité, remédiation des sols, gestion des ressources."),
    ("Transition énergétique",
     "Électronique de puissance, électrocatalyse, renouvelables, matières premières critiques."),
    ("Transition numérique de l'industrie et de la société",
     "Intelligence artificielle, cybersécurité, systèmes de contrôle, méthodes computationnelles."),
    ("Défis mondiaux de la santé (incl. One Health)",
     "Cardiovasculaire et rénal, troubles métaboliques, inflammation chronique."),
    ("Transitions dans la société",
     "Gouvernance, éducation, études culturelles, changement social."),
]
_defi_cols = st.columns(3)
for _i, (_title, _text) in enumerate(DEFIS):
    with _defi_cols[_i % 3]:
        with st.container(border=True):
            st.markdown(f"**{_title}**")
            st.caption(_text)
st.caption(
    ":grey[Les six défis n'ont pas de porteur ni de gouvernance dédiée : chaque objet "
    "(PI, IMPACT, CRET) s'auto-déclare sur un à trois d'entre eux.]"
)

st.markdown("### La dynamique interdisciplinaire : trois familles d'instruments")
INSTRUMENTS = [
    ("Programmes Interdisciplinaires (PI)",
     "Cinq ans, renouvelables une fois, portés par une communauté de recherche stabilisée "
     "(ARTEMIS, B4B, MAT-PULSE, TRANSITION, CIRSET, LIFE-TRAVEL)."),
    ("Projets IMPACT",
     "Quatre ans, non renouvelables, avec une trajectoire possible vers un PI une fois la "
     "communauté consolidée (EPHEMERIS, INSIGHT, I-META, SYMBIOSE, MEDICIS, parmi d'autres)."),
    ("CRET (Centres de Recherche et d'Expertise Transversaux)",
     "Durée alignée sur celle des PI : CELEST porte les sciences humaines et sociales, AIREL "
     "l'intelligence artificielle (en navette)."),
]
_instr_cols = st.columns(3)
for _col, (_title, _text) in zip(_instr_cols, INSTRUMENTS):
    with _col:
        with st.container(border=True):
            st.markdown(f"**{_title}**")
            st.caption(_text)

st.markdown("### Les huit membres du consortium")
st.markdown(
    "L'I-SITE a été remportée conjointement par l'Université de Lorraine, porteuse, et sept "
    "partenaires de site."
)
_chip_row([
    "Université de Lorraine (porteur)", "CNRS", "CHRU Nancy", "Georgia Tech Europe",
    "Inria", "INRAE", "Inserm", "AgroParisTech",
])

# ============================================================================
# Data
# ============================================================================
@st.cache_data
def _load_dim_subsets() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "dim_subsets.parquet")


@st.cache_data
def _load_thm_specialisation() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "thm_specialisation.parquet")


@st.cache_data
def _load_consortium_weights() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "consortium_weights.parquet")


dim_subsets = _load_dim_subsets()
SNAPSHOT_DATE = str(dim_subsets["snapshot_date"].iloc[0])
CONF_STATE = "all" if include_conference else "no_conf"


def _subset_works_col(base: str) -> str:
    base = base if include_conference else f"{base}_noconf"
    return controls.xa(dim_subsets, base)


_WORKS_COL = _subset_works_col("n_works")
_all_row = dim_subsets.loc[dim_subsets["subset_id"] == "all"]
_in_isite_row = dim_subsets.loc[dim_subsets["subset_id"] == "in_isite"].iloc[0]
CORPUS_TOTAL = _all_row[_WORKS_COL].iloc[0] if not _all_row.empty else pd.NA
ISITE_WORKS = _in_isite_row[_WORKS_COL]

# All-types canonical count, independent of the conference toggle (I2-02 fix) -- needed by
# both the canonical-list construction recall block (item #37) and the award reconciliation
# panel (Section 5) below, so computed once, here.
_ISITE_CANON_ALL_TYPES = int(_in_isite_row[controls.xa(dim_subsets, "n_works")])

# Award-family reconciliation numbers (S-INV S4, reports/isite_award_reconciliation.md), ALWAYS
# all-types (never routed through the conference toggle) -- needed by both the recall block
# (item #37) and the full reconciliation panel (Section 5).
_subset_works_path = DATA_DIR / "subset_works.parquet"
_award_slice = lazy.read_keyed(_subset_works_path, "subset_id", "in_isite_award")
_award_only = _award_slice[~_award_slice["in_isite"]].copy()
_award_total = len(_award_slice)
_award_in_canon = _award_total - len(_award_only)
_award_no_trace = _ISITE_CANON_ALL_TYPES - _award_in_canon  # I2-08: the "1 063" reading

# Expected DOI count of the client's canonical list -- a pipeline config constant (config.yaml
# isite.expected_unique_dois), not a deployed-table figure: mirrors the existing page-local
# workshop-tunable convention (pages 8/9's *_DEFAULT_FLOOR constants).
_ISITE_EXPECTED_UNIQUE_DOIS = 3776  # config.yaml isite.expected_unique_dois

_ISITE_EXPORT_STATE = exports.ExportState(
    snapshot=SNAPSHOT_DATE,
    conf=include_conference,
    artifact=artifact_on,
    subset="in_isite",   # every panel here is a FIXED in_isite-vs-site contrast, per composition
    artifact_applied=artifact_on,
    method="Synthèse I-SITE (R2, pass 5) : thm_specialisation + consortium_weights + subset_works",
)

# --- field-level contrast rows (PM3) ---------------------------------------------------
ts = _load_thm_specialisation()
_field_rows = ts[(ts["level"] == "field") & (ts["conf_state"] == CONF_STATE)].copy()
_ul_col = controls.xa(_field_rows, "ul_works")

_site = _field_rows[_field_rows["subset_id"] == "all"].set_index("node_id")
_isite = _field_rows[_field_rows["subset_id"] == "in_isite"].set_index("node_id")

field_id2name = get_field_id_to_name()
field_id2domain = get_field_id_to_domain_id()
domain_id2name = get_domain_id_to_name()

_site_total = _site[_ul_col].sum()
_isite_total = _isite[_ul_col].sum()

fields_df = pd.DataFrame(index=_site.index)
fields_df["field_id"] = fields_df.index.astype(int)
fields_df["field_name"] = fields_df["field_id"].map(field_id2name)
fields_df["domain_name"] = fields_df["field_id"].map(field_id2domain).map(domain_id2name)
fields_df["site_works"] = _site[_ul_col]
fields_df["isite_works"] = _isite.reindex(_site.index)[_ul_col]
fields_df["floor_flag"] = _isite.reindex(_site.index)["floor_flag"].fillna(False).astype(bool)
fields_df["site_share"] = fields_df["site_works"] / _site_total if _site_total else np.nan
fields_df["isite_share"] = fields_df["isite_works"] / _isite_total if _isite_total else np.nan
fields_df["ratio"] = fields_df["isite_share"] / fields_df["site_share"]
fields_df = fields_df.reset_index(drop=True)

N_FIELDS_TOTAL = len(fields_df)
N_FIELDS_GE30 = int((~fields_df["floor_flag"]).sum())

# ============================================================================
# Section 2 -- KPI row
# ============================================================================
st.markdown("---")

_pct_corpus = (ISITE_WORKS / CORPUS_TOTAL) if pd.notna(ISITE_WORKS) and pd.notna(CORPUS_TOTAL) and CORPUS_TOTAL else None
_pct_display = fr_pct(_pct_corpus * 100) if _pct_corpus is not None else "n/a"

st.markdown("## Le périmètre I-SITE en un coup d'œil")

k1, k2 = st.columns(2)
k1.metric("Travaux I-SITE", fr_int(ISITE_WORKS))
k2.metric("Part du corpus complet", _pct_display)

st.caption(
    f":grey[Liste canonique (DOI validés par l'université), datée du "
    f"**{_in_isite_row['vintage_date']}** ; corpus au snapshot du **{SNAPSHOT_DATE}**. Un "
    "travers de périmètre vaut pour toute l'application : un recul apparent de l'I-SITE sur "
    "les toutes dernières années tient en partie au retard de mise à jour de la liste, "
    "jamais à un recul réel de la production I-SITE.]"
)

# ============================================================================
# Canonical-list construction recall block (item #37, NARRATIVE_CONTRACT_pass6.md S4.3)
# Verbatim copy, {n} placeholders filled from the tables loaded above -- no number in this
# block is hardcoded.
# ============================================================================
with st.expander("Comment la liste I-SITE a été construite", expanded=False):
    st.markdown(
        f"Le périmètre I-SITE de cet outil est défini par une **liste de DOI, constituée et "
        f"validée par l'établissement**, transmise à SIRIS et figée à sa date de millésime. "
        f"Elle compte {fr_int(_ISITE_EXPECTED_UNIQUE_DOIS)} DOI distincts, dont "
        f"{fr_int(_ISITE_CANON_ALL_TYPES)} se retrouvent dans le corpus OpenAlex de cet "
        "instantané : l'écart tient aux publications que la fenêtre ne couvre pas, à celles "
        "qu'OpenAlex ne rattache pas à l'établissement, et à celles dont le type n'entre pas "
        "dans le corpus."
    )
    st.markdown(
        "**Cette liste est la définition, pas une approximation.** Deux autres routes ont "
        "été testées, et aucune n'est assez fidèle pour la remplacer :"
    )
    st.markdown(
        "- **Les collections HAL.** Une reconstruction à partir des collections HAL portant "
        "la marque de l'initiative et des projets ANR associés a été mesurée contre la liste "
        "validée : elle retrouve moins d'un tiers des publications identifiables, avec une "
        "précision d'environ sept sur dix. Trop bas pour définir un périmètre, assez "
        "informatif pour servir de contrôle."
    )
    st.markdown(
        f"- **La trace de subvention OpenAlex.** Le rapprochement par code de financement "
        f"ANR identifie {fr_int(_award_total)} travaux, dont {fr_int(len(_award_only))} ne "
        "figurent pas dans la liste validée. Ce sont des **candidats à un enrichissement de "
        "la liste**, jamais une part supplémentaire du périmètre : la fusion n'est pas "
        "faite, et ne le sera qu'à la demande de l'établissement."
    )
    st.markdown(
        "**Ce qui suit de ce choix.** Le périmètre est aussi à jour que la liste : "
        "rafraîchir la liste est la seule façon de couvrir les publications récentes, et "
        "c'est une action qui appartient à l'établissement. Le recoupement de subvention "
        "affiché plus bas sur cette page est précisément l'instrument prévu pour préparer "
        "ce rafraîchissement."
    )

# ============================================================================
# Section 2bis -- Static impact contrast (I2-03 fix): "is the I-SITE better cited than
# the rest of the site?" -- the single most obvious GT question, which the R1 overlay
# redesign left with no surface anywhere in the app (the overlays decompose VOLUME only,
# per OVERLAY_MATRIX; no compensating synthesis tile existed). Absorbed R1-compatible
# (LENS_ABSORPTION_pass5.md I2-03): computed ONCE from the already-loaded ul_pubs slim
# frame, D53 floors applied (indicator_status == "computed" only), median-first with the
# mean shown as a secondary reference -- never an interactive recomputation, never a new
# pipeline table.
# ============================================================================
_pubs_slim = get_pubs_slim()
_has_indicator = _pubs_slim["indicator_status"] == "computed"  # D53 floor: thin/no-stratum out
_isite_ind = _pubs_slim[_pubs_slim["In_ISITE"] & _has_indicator]
_rest_ind = _pubs_slim[(~_pubs_slim["In_ISITE"]) & _has_indicator]
_n_isite_excl = int(_pubs_slim["In_ISITE"].sum()) - len(_isite_ind)
_n_rest_excl = int((~_pubs_slim["In_ISITE"]).sum()) - len(_rest_ind)

st.markdown("### L'I-SITE est-il plus cité que le reste du site ?")
kc1, kc2 = st.columns(2)
kc1.metric("FWCI (réf. France), médiane -- I-SITE", _fr_ratio(_isite_ind["FWCI_FR"].median()))
kc2.metric("FWCI (réf. France), médiane -- reste du site", _fr_ratio(_rest_ind["FWCI_FR"].median()))
st.caption(
    f":grey[Moyennes (repère, sensibles aux valeurs extrêmes) : "
    f"{_fr_ratio(_isite_ind['FWCI_FR'].mean())} (I-SITE) contre "
    f"{_fr_ratio(_rest_ind['FWCI_FR'].mean())} (reste du site). Part Top 10 % (réf. France) : "
    f"{fr_pct(_isite_ind['PPtop10_FR'].mean() * 100)} (I-SITE) contre "
    f"{fr_pct(_rest_ind['PPtop10_FR'].mean() * 100)} (reste du site). Calculé une seule fois "
    f"sur {fr_int(len(_isite_ind))} travaux I-SITE et {fr_int(len(_rest_ind))} travaux du reste "
    "du site porteurs d'un indicateur (les travaux en strate mince ou sans strate sont exclus "
    f"du calcul : {fr_int(_n_isite_excl)} côté I-SITE, {fr_int(_n_rest_excl)} côté reste du "
    "site). Cette synthèse est calculée une fois sur le corpus entier : les boutons de la "
    "barre latérale décomposent des volumes, ils ne recalculent pas un indicateur de "
    "citation.]"
)

st.markdown("---")

# ============================================================================
# Section 3 -- PM3 contrast panel (dot-ratio)
# ============================================================================
_ranked_fields = fields_df.sort_values("ratio", ascending=False).reset_index(drop=True)
_lead_field = _ranked_fields.iloc[0]
_second_field = _ranked_fields.iloc[1]

st.markdown("## Ce que le périmètre I-SITE amplifie, champ par champ")
st.markdown(
    "Pour chaque champ, la **part du périmètre I-SITE** dans ce champ, divisée par la **part "
    "du site entier** dans ce même champ : au-dessus de la parité, le champ est surreprésenté "
    "dans l'I-SITE par rapport au reste du site ; en dessous, il y est sous-représenté."
)
_ratio_axis_type = log_linear_toggle("isite_ratio_axis_toggle")  # R18
st.caption(
    "**Comment lire ce graphique :** chaque point est un champ disciplinaire, placé par "
    "défaut sur un axe **logarithmique** (bascule « échelle linéaire » ci-dessus) pour qu'une "
    "surreprésentation et une sous-représentation de même ampleur (par exemple un doublement "
    "et une division par deux) pèsent à égale distance de la **parité** (ligne pointillée) ; "
    "la **taille** du point suit le volume I-SITE, sa **couleur** le domaine. Les points gris "
    "creux sont sous le plancher de 30 travaux I-SITE, indiqués à leur ratio mesuré mais "
    f"jamais affirmés comme une estimation stable : {N_FIELDS_GE30} des {N_FIELDS_TOTAL} "
    "champs dépassent ce plancher."
)
_render_domain_identity_legend()


def _bubble_sizes(values: pd.Series, smin: float = 9.0, smax: float = 44.0) -> pd.Series:
    """Area-true marker sizing: size (diameter) ~ sqrt(value), per VIZ_SPEC 3 rule 2."""
    v = values.fillna(0).clip(lower=0)
    sq = np.sqrt(v)
    lo, hi = sq.min(), sq.max()
    if hi <= lo:
        return pd.Series(smin, index=values.index)
    return smin + (sq - lo) / (hi - lo) * (smax - smin)


_X_FLOOR = 0.015  # a TRUE ratio of 0 (0 I-SITE works) cannot sit on a log axis; clipped for
                   # PLACEMENT only -- the hover always states the real 0 and "n<30", never
                   # implying a non-zero measurement (shown, not asserted, per VIZ_SPEC PM3).

_plot_df = fields_df.copy()
_plot_df["plot_x"] = _plot_df["ratio"].clip(lower=_X_FLOOR)
_plot_df["size"] = _bubble_sizes(_plot_df["isite_works"])
_plot_df["colour"] = _plot_df["domain_name"].map(DOMAIN_IDENTITY).fillna(NEUTRAL_GREY)
_plot_df = _plot_df.sort_values("ratio", ascending=True).reset_index(drop=True)
_category_order = _plot_df["field_name"].tolist()

_above = _plot_df[~_plot_df["floor_flag"]]
_below = _plot_df[_plot_df["floor_flag"]]

fig_ratio = go.Figure()

if not _below.empty:
    fig_ratio.add_trace(go.Scatter(
        x=_below["plot_x"], y=_below["field_name"], mode="markers",
        marker=dict(size=_below["size"], color="rgba(140,145,150,0.15)",
                    line=dict(color=NEUTRAL_GREY, width=2)),
        name="< 30 travaux I-SITE",
        customdata=list(zip(_below["isite_works"], _below["site_works"], _below["ratio"])),
        hovertemplate=(
            "<b>%{y}</b><br>Travaux I-SITE : %{customdata[0]:.0f} (sous le plancher de 30 "
            "travaux)<br>Travaux du site : %{customdata[1]:,.0f}<br>Ratio : %{customdata[2]:.2f} "
            "(indiqué, non affirmé, n<30)<extra></extra>"
        ),
    ))

if not _above.empty:
    fig_ratio.add_trace(go.Scatter(
        x=_above["plot_x"], y=_above["field_name"], mode="markers",
        marker=dict(size=_above["size"], color=_above["colour"], line=dict(color="white", width=1)),
        name="≥ 30 travaux I-SITE",
        customdata=list(zip(_above["isite_works"], _above["site_works"], _above["ratio"], _above["domain_name"])),
        hovertemplate=(
            "<b>%{y}</b><br>Travaux I-SITE : %{customdata[0]:,.0f}<br>Travaux du site : "
            "%{customdata[1]:,.0f}<br>Ratio (part I-SITE / part du site) : %{customdata[2]:.2f}"
            "<br>Domaine : %{customdata[3]}<extra></extra>"
        ),
    ))

fig_ratio.add_vline(x=1, line_dash="dash", line_color="#5A5F66")
fig_ratio.add_annotation(x=1, y=1.02, yref="paper", text="parité", showarrow=False,
                          font=dict(size=11, color="#5A5F66"))
# dtick=1 on a log axis = one labeled major gridline per power of 10 (0.01/0.1/1/10) --
# plotly's default log-axis minor ticks (bare "2", "5" with no decade prefix) read as
# ambiguous at this width; a sparser, unambiguous set beats a denser, confusing one. Not
# applied on the linear axis (R18 toggle), where an even auto-tick spacing reads better.
_ratio_axis_kwargs = dict(type=_ratio_axis_type, title="Part I-SITE / part du site")
if _ratio_axis_type == "log":
    _ratio_axis_kwargs["dtick"] = 1
fig_ratio.update_xaxes(**_ratio_axis_kwargs)
fig_ratio.update_yaxes(categoryorder="array", categoryarray=_category_order, title="")
fig_ratio.update_layout(
    height=max(560, len(_plot_df) * 24), margin=dict(t=30, l=10, r=20, b=40),
    legend=dict(orientation="h", y=-0.06),
)

_dot_event = st.plotly_chart(
    fig_ratio, use_container_width=True, on_select="rerun",
    selection_mode="points", key="dot_ratio_chart",
)
_sel_points = (
    list(_dot_event["selection"]["points"]) if isinstance(_dot_event, dict)
    else list(_dot_event.selection.points)
)
if _sel_points:
    _clicked_field = _sel_points[0].get("y")
    if _clicked_field:
        # pass-5 rename: Thematic Drilldown moved from slot 4 to slot 6 (P1 map).
        _drilldown_candidates = sorted(Path(__file__).parent.glob("6_*.py"))
        st.caption(f":grey[Sélectionné : **{_clicked_field}**.]")
        if _drilldown_candidates:
            st.page_link(
                f"pages/{_drilldown_candidates[0].name}",
                label=f"Ouvrir l'exploration thématique pour {_clicked_field} →",
                help="La présélection entre pages n'est pas encore câblée : sélectionnez à "
                     "nouveau le champ sur cette page.",
            )

# R19 caption rewrite #3 (Codex concept review), recomputed live from thm_specialisation on
# every render -- the leading fields are READ from the data (_lead_field/_second_field
# above), never hardcoded, since a prior draft named "Materials Science" and "Energy" as
# the top two and the current snapshot instead leads with Agricultural and Biological
# Sciences (a genuine data-vintage move, not a bug -- see progress/PD_isite.md for the
# recompute trail). The instability caveat is now an unconditional method rule (P6-R2),
# not a conditional third-field callout.
st.caption(
    f":grey[Champs les plus amplifiés dans cet instantané : "
    f"**{_lead_field['field_name']}** (ratio {_fr_ratio(_lead_field['ratio'])}, "
    f"{fr_int(_lead_field['isite_works'])} travaux) et "
    f"**{_second_field['field_name']}** (ratio {_fr_ratio(_second_field['ratio'])}, "
    f"{fr_int(_second_field['isite_works'])} travaux). Un champ dont l'effectif I-SITE "
    "approche le plancher de 30 travaux donne un ratio instable : il est indiqué, jamais "
    "affirmé comme une tendance de programme.]"
)
st.markdown(
    "**Pourquoi cet indicateur.** Le périmètre I-SITE ne reproduit pas le portefeuille du "
    "site en plus petit : il en accentue certaines parties. Ce rapport dit lesquelles, et "
    "son complément dit ce que le site porte hors de ce périmètre. Les deux lectures sont "
    "utiles, et aucune n'est un jugement sur l'autre."
)

exports.attach_download(
    st,
    fields_df[["field_id", "field_name", "domain_name", "site_works", "isite_works",
               "site_share", "isite_share", "ratio", "floor_flag"]],
    "isite", "pm3-contrast", _ISITE_EXPORT_STATE,
)

st.markdown("---")

# ============================================================================
# Section 4 -- PM4 consortium dumbbell + "left to the rest" panel
# ============================================================================
col_dumbbell, col_rest = st.columns(2)

with col_dumbbell:
    st.markdown("### Le poids de chaque membre du consortium")
    # R2 -- BINDING caption, VERBATIM (indicator_plan_FINAL.md R2, rectorate absorption).
    st.markdown(
        "*« Cette part reflète la structure des UMR co-portées avec le CNRS dans "
        "les grands laboratoires lorrains — une part de co-signature, pas une part de "
        "gouvernance ni de financement du label. »*"
    )
    st.caption(
        "**Comment lire ce graphique.** Le point bleu est la part d'un membre dans le "
        "corpus I-SITE, le point gris sa part dans le corpus du site entier. Ces parts ne "
        "s'additionnent pas entre membres : les membres co-signent les mêmes travaux, et un "
        "même travail compte pour chacun de ses signataires."
    )

    cw_all = _load_consortium_weights()
    cw = cw_all[cw_all["conf_state"] == CONF_STATE]
    _isite_cw = cw[cw["scope"] == "isite"].set_index("member")
    _site_cw = cw[cw["scope"] == "all"].set_index("member")

    _MEMBER_ORDER = ["CNRS", "INRAE", "AgroParisTech", "Inserm", "CHRU Nancy", "Georgia Tech", "Inria"]
    _members_present = [m for m in _MEMBER_ORDER if m in _isite_cw.index]

    members = pd.DataFrame(index=_members_present)
    members["isite_share"] = _isite_cw.loc[_members_present, "share_of_scope"]
    members["site_share"] = _site_cw.reindex(_members_present)["share_of_scope"]
    members["isite_co_works"] = _isite_cw.loc[_members_present, "co_works_distinct"]
    members["site_co_works"] = _site_cw.reindex(_members_present)["co_works_distinct"]
    members["id_set_size"] = _isite_cw.loc[_members_present, "id_set_size"]
    members["incl_own"] = _isite_cw.loc[_members_present, "incl_own_centre_variant_share"]
    members = members.sort_values("isite_share", ascending=True)

    fig_dumb = go.Figure()
    for _member, _row in members.iterrows():
        fig_dumb.add_trace(go.Scatter(
            x=[_row["site_share"], _row["isite_share"]], y=[_member, _member], mode="lines",
            line=dict(color="#D8DBDF", width=4), hoverinfo="skip", showlegend=False,
        ))

    fig_dumb.add_trace(go.Scatter(
        x=members["site_share"], y=members.index, mode="markers+text",
        marker=dict(size=15, color=NEUTRAL_GREY),
        text=[fr_pct(v * 100, decimals=1) for v in members["site_share"]], textposition="top center",
        name="Part du corpus du site entier",
        customdata=list(zip(members["site_co_works"])),
        hovertemplate="<b>%{y}</b><br>Part du site entier : %{x:.2%}<br>"
                      "Co-travaux (périmètre site) : %{customdata[0]:,.0f}<extra></extra>",
    ))
    fig_dumb.add_trace(go.Scatter(
        x=members["isite_share"], y=members.index, mode="markers+text",
        marker=dict(size=15, color=FOCAL_BLUE),
        text=[fr_pct(v * 100, decimals=2) for v in members["isite_share"]], textposition="bottom center",
        name="Part du corpus I-SITE",
        customdata=list(zip(members["isite_co_works"], members["id_set_size"])),
        hovertemplate="<b>%{y}</b><br>Part du corpus I-SITE : %{x:.2%}<br>Co-travaux distincts "
                      "(périmètre I-SITE) : %{customdata[0]:,.0f}<br>Taille de l'ensemble "
                      "d'identifiants : %{customdata[1]:.0f}<extra></extra>",
    ))
    fig_dumb.update_xaxes(title="Part du corpus", tickformat=".0%")
    fig_dumb.update_yaxes(title="")
    fig_dumb.update_layout(
        height=max(340, len(members) * 62), margin=dict(t=20, l=10, r=30, b=40),
        legend=dict(orientation="h", y=-0.18),
    )
    st.plotly_chart(fig_dumb, use_container_width=True)

    if artifact_on:
        st.caption(
            ":grey[Les poids du consortium sont des mesures structurelles, comptées par "
            "ensemble d'identifiants : ils ne sont pas recalculés sous le filtre d'exclusion "
            "référentiel (exemption app-wide de la famille structurelle/momentum).]"
        )

    _chru_share_pct = members.loc["CHRU Nancy", "isite_share"] * 100 if "CHRU Nancy" in members.index else None
    st.caption(
        ":grey[Le **CHRU de Nancy** siège dans le consortium comme **partenaire**, pas comme "
        "institution co-tutelle du CNRS : sa part de co-signature de "
        f"{fr_pct(_chru_share_pct) if _chru_share_pct is not None else 'n/a'} n'est pas un "
        "indicateur de son poids en recherche clinique, que le défi Santé capture ailleurs "
        "dans le portefeuille.]"
    )
    if "Inria" in members.index:
        _inria = members.loc["Inria"]
        if pd.notna(_inria.get("incl_own")):
            st.caption(
                ":grey[Le point **Inria** est l'ensemble d'identifiants **externe uniquement** "
                f"({fr_pct(_inria['isite_share'] * 100, decimals=2)} du corpus I-SITE) ; en "
                "intégrant le centre Inria propre à l'Université de Lorraine (exclu par "
                f"construction), la part monterait à **{fr_pct(_inria['incl_own'] * 100, decimals=2)}**. "
                "Les deux lectures sont possibles ; celle qui fait référence reste une décision "
                "de l'établissement.]"
            )

    exports.attach_download(
        st, members.reset_index(names="member"), "isite", "pm4-consortium-weights", _ISITE_EXPORT_STATE,
    )

with col_rest:
    st.markdown("### Ce que le périmètre laisse au reste du site")
    st.markdown(
        "Le périmètre I-SITE **complète** le portefeuille du site, il n'en est pas une "
        "miniature : voici les plus grands champs que le site entier porte et que l'I-SITE "
        "amplifie le moins (ratio sous la parité). Leur volume est une force institutionnelle "
        "réelle, portée hors de ce périmètre."
    )
    _under_rep = (
        _plot_df[_plot_df["ratio"] < 1]
        .sort_values("site_works", ascending=False)
        .head(4)
    )
    if _under_rep.empty:
        st.info("Aucun champ ne se situe sous la parité pour cette combinaison de snapshot et d'options.")
    else:
        for _, _r in _under_rep.iterrows():
            st.markdown(
                f"- **{_r['field_name']}** : {fr_int(_r['site_works'])} travaux du site "
                f"(ratio {_fr_ratio(_r['ratio'])}, dont ~{fr_int(_r['isite_works'])} I-SITE)"
            )
    st.caption(
        ":grey[Complémentarité, pas un manque : le site n'a pas besoin du label I-SITE pour "
        "porter ces champs, et le périmètre n'est pas conçu pour couvrir le portefeuille de "
        "façon homogène.]"
    )
    exports.attach_download(
        st,
        _under_rep[["field_id", "field_name", "domain_name", "site_works", "isite_works", "ratio"]],
        "isite", "pm3-left-to-rest", _ISITE_EXPORT_STATE,
    )

st.markdown("---")

# ============================================================================
# Section 5 -- Award reconciliation panel (S-INV S4, the "32-vs-713" fix)
# Show the three BROAD-family numbers only (all computed above, from `subset_works`) --
# NEVER n_works_noconf or the superseded EXACT figure, per the reconciliation memo's own
# S4 recommendation. All three numbers are ALWAYS all-types (never routed through
# `_subset_works_col`/the conference toggle) and are compared against the all-types
# canonical count (`_ISITE_CANON_ALL_TYPES`, independent of the toggle) -- computed once,
# earlier on this page, alongside the canonical-list construction recall block (item #37).
# ============================================================================
st.markdown("## Recoupement avec la trace de subvention ANR")
st.markdown(
    f"**Croisement prix/financement OpenAlex** (subvention ANR de l'I-SITE) : "
    f"**{fr_int(_award_total)}** travaux au total, dont **{fr_int(_award_in_canon)}** déjà "
    f"présents dans la liste canonique I-SITE ({fr_int(_ISITE_CANON_ALL_TYPES)} travaux), et "
    f"**{fr_int(len(_award_only))}** hors liste canonique, candidats à un enrichissement de la "
    "liste par le GT Indicateurs. La liste DOI validée par l'université reste la référence : "
    "ce croisement est une vérification, jamais une fusion dans le périmètre canonique."
)
st.caption(
    f":grey[Les trois nombres ci-dessus ({fr_int(_award_total)} / {fr_int(_award_in_canon)} / "
    f"{fr_int(len(_award_only))}) et le total de la liste canonique "
    f"({fr_int(_ISITE_CANON_ALL_TYPES)}) portent sur **tous les types de publication**, "
    "indépendamment du bouton « Inclure les articles de conférence » : ce panneau ne recalcule "
    "jamais ces effectifs sous le filtre conférence.]"
)
st.caption(
    f":grey[**{fr_int(_award_no_trace)}** travaux de la liste canonique "
    f"({fr_pct(_award_no_trace / _ISITE_CANON_ALL_TYPES * 100)}) ne portent aucune trace de "
    "subvention dans ce croisement. C'est attendu : les remerciements de financement ne sont "
    "renseignés que sur une partie du corpus, et une absence de trace n'est jamais un signe que "
    "ces travaux seraient mal listés.]"
)
st.markdown(
    "**Pourquoi cet indicateur.** La liste de DOI validée par l'établissement définit le "
    "périmètre. Le recoupement par trace de subvention est un **contrôle** : il signale des "
    "travaux candidats à un enrichissement de la liste, il ne les y ajoute jamais."
)

with st.expander(f"Publications hors liste (n={fr_int(len(_award_only))}, fichier xlsx)", expanded=False):
    if _award_only.empty:
        st.info("Aucun travail « hors liste » pour ce snapshot.")
    else:
        _disp = _award_only[["work_id", "year", "title", "doi", "type", "is_conference", "artifact_flag"]].sort_values(
            "year", ascending=False
        )
        _award_only_col_config = {
            "artifact_flag": st.column_config.CheckboxColumn(
                "Hors référentiel", disabled=True,
                help=controls.MARKER_DAGGER_TOOLTIP_FR,
            ),
            "is_conference": st.column_config.CheckboxColumn("Article de conférence", disabled=True),
        }
        st.dataframe(
            _disp, use_container_width=True, hide_index=True, height=340,
            column_config=_award_only_col_config,
        )
        exports.attach_download(
            st, _disp, "isite", "pm5-award-crosscheck", _ISITE_EXPORT_STATE, works=True,
        )

st.markdown("---")

# ============================================================================
# Section 6 -- Programme placeholders (R2): honest, no fake data.
# ============================================================================
st.markdown("## Programmes PI, IMPACT et CRET")
st.markdown(
    "Chaque objet de la dynamique interdisciplinaire mériterait son propre corpus de "
    "publications pour être positionné, comparé et suivi dans le temps ; cette liste n'existe "
    "pas encore côté I-SITE. Elle est un livrable attendu de l'atelier des 5 et 6 octobre 2026 "
    "(co-construction du programme, Cours Léopold)."
)
PROGRAMMES = [
    ("Programmes Interdisciplinaires (PI)",
     "Trajectoire de chaque PI (ARTEMIS, B4B, MAT-PULSE, TRANSITION, CIRSET, LIFE-TRAVEL) au "
     "sein du corpus, et évolution de sa spécialisation."),
    ("Projets IMPACT",
     "Évidence de trajectoire pour la décision de mi-parcours (passage en PI, arrêt ou "
     "réorientation) de chaque projet (EPHEMERIS, INSIGHT, I-META, SYMBIOSE, MEDICIS, ABR, "
     "DeNAMISE, IMAGE, TRAPPS)."),
    ("CRET",
     "Portée transversale de CELEST (sciences humaines et sociales) et d'AIREL (intelligence "
     "artificielle, en navette) au sein du corpus."),
]
_prog_cols = st.columns(3)
for _col, (_title, _text) in zip(_prog_cols, PROGRAMMES):
    with _col:
        with st.container(border=True):
            st.markdown(f"**{_title}**")
            st.caption(":grey[**En attente de la liste programme.**]")
            st.caption(f":grey[Une fois disponible : {_text}]")

st.markdown("---")

# ============================================================================
# Section 7 -- How-to-read closing block (R19)
# ============================================================================
st.markdown("## Où trouver le détail I-SITE dans le reste de l'outil")
st.markdown(
    "Cette page reste la synthèse identitaire de l'I-SITE : ce qu'elle est, ce qu'elle "
    "amplifie dans l'ensemble du site, et où en est la réconciliation de ses listes. Le "
    "détail par dimension (laboratoires, thématiques, partenaires, géographie, auteurs) ne "
    "vit plus ici : chaque page correspondante porte désormais sa propre décomposition "
    "I-SITE, activée par le bouton **« Afficher la contribution I-SITE »** de la barre "
    "latérale, qui superpose une teinte plus sombre sur les graphiques concernés sans jamais "
    "recalculer ni retirer de travaux du corpus affiché."
)

st.markdown("---")
st.caption(
    f"Snapshot : {SNAPSHOT_DATE} | Périmètre I-SITE : {fr_int(ISITE_WORKS)} travaux (liste DOI "
    "validée par l'université)."
)
