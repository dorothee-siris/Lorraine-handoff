"""
Collaboration Overview (V1) -- docs/indicator_plan_FINAL.md §3 (I1-I4, I8, I9) /
docs/studio/VIZ_SPEC.md §2.5. NEW page, chain pass 3, Assembly Line stream P2.
Pass-5 stream P-F (2026-08-18): ranked_table conversion (R11/R14), I-SITE overlay bars
(R1, docs/OVERLAY_MATRIX.md), FR question-sentence opener + FR number formatting (R12/R19),
log/linear toggle on the momentum quadrant (R18/R17).
Pass-6 stream P-COL (2026-08-19, items #38-#40): "Part partenaire" (share_p) becomes the
hub table's ONE ProgressColumn (VIZ_SPEC_pass6 S7.2), every other share/volume an explicit
NumberColumn; "Momentum" is now the quantified re-expression (lib.helpers.momentum_display,
VIZ_SPEC_pass6 S8), windows named from ptn_mom_facts (mom_w1_label/mom_w2_label), never
hardcoded (docs/YEAR_UPDATE_DESIGN.md S5.3); new France-hors-site share column
(ptn_denominators, P4); FR country names (lib.countries_fr); narrative sweep per
docs/NARRATIVE_CONTRACT_pass6.md S2.9 (jargon, static conclusions and year literals out;
"Comment lire"/"Pourquoi cet indicateur" blocks in). #38a (consortium column reported
empty) re-verified live: renders correctly in the DEFAULT state (progress/PCOL.md has
the proof); the observation matches a pre-wave-3 vintage, per S-PRB probe 1.
FIX-1 pass-6 fix round (S-LENS D7): a REAL recurrence path for that same observation was
found in a non-default state -- "masquer les membres du site" ON removes every member
row (`mask_members()`) before the "Consortium" badge is computed on what's left, so the
column rendered fully empty (logically correct, visually the exact #38 symptom). Fixed in
`lib/ranked.py` (the shared component, not this page): the Consortium column is now
skipped entirely when the mask is on, rather than rendered empty.

Authority (binding): VIZ_SPEC §2.5 + §1.1-1.6 + §3 (cross-view rules) · indicator_plan_FINAL
§3 + §6.3 + §6.6 · data_foundation.yaml rev 3.1 (ptn_summary/ptn_mom_facts/consortium_weights) ·
data_contract.yaml (deployed schemas -- verified against the actual parquet, not guessed) ·
docs/SPRINT_KICKOFF_pass5.md (R1/R11/R12/R14/R17/R18/R19) · docs/OVERLAY_MATRIX.md §8.
Every shared behaviour (sidebar, banner/strips, xa() column selection, download buttons,
ranked table, overlay grammar, FR number formatting) goes through
Streamlit/lib/{controls,exports,lazy,ranked,overlay,helpers}.py -- nothing here re-implements it.

Decision sentence (VIZ_SPEC 2.5): after this view a porteur can name UL's main partners by
type, see which relationships are balanced or lopsided, and spot which are moving -- then
descend to any one of them.

Composition, above the fold -> down:
  1. KPI row: partners >=10 co-pubs . % international (+France anchor) . % with company .
     % collaborative.
  2. Partners hub table -- the claim, full width. lib.ranked.ranked_table() (consortium
     badge + local member-mask + text-query + "afficher plus" depth + median-first column
     order), fed the FULL type/floor-filtered population (site-level = deep, extension
     free, R11). A companion overlay bar chart (lib.overlay) shows the currently visible
     partners' volume with the I-SITE segment darker when the global toggle is on. Type
     filter + floor threshold stay page-level population filters (business rule, not a
     depth control). Row-click navigation is not available through ranked_table() (no
     on_select in its frozen API) -- replaced by a compact "ouvrir la fiche partenaire"
     picker sourced from the same visible rows (disclosed adaptation, see progress note).
  3. Reciprocity panel (half) + consortium panel (half). Reciprocity's underlying measure
     (share_p, this partner's own volume with the UL relation) is populated on the
     (conf_state='all', subset_id='all') rows only (NULL, never 0, elsewhere by design)
     and already renders in the hub table's "Part partenaire" column; the scatter chart
     itself is not built this pass either (Studio decision, no spec exists yet -- see
     progress note). Consortium = 7 external id-set members (consortium_weights ships 7,
     not the plan's rounded "8" -- see progress note), fixed order by ISITE share.
  4. Momentum quadrant, one TAB deep (`st.tabs`, per D5) -- x=mom_w1_share, y=mom_w2_share,
     log-log by default with a local "échelle linéaire" toggle (R18), recentred +/-25% band,
     shipped median on-chart (~1.0604, NOT the frozen 1.061 disclosure constant),
     colour=class (grey=ns always plotted), size=co-works (area-true). Momentum stays
     artifact- AND I-SITE-overlay-exempt (R17, extends the app-wide momentum ruling --
     docs/OVERLAY_MATRIX.md §8). New/dormant rendered as a separate small table below the
     quadrant, never merged into it.

Rejected alternatives (VIZ_SPEC 2.5): a map above the fold (geography is V3's job); a
network graph (hairball at N~2.3k -- LEGIBILITY_BUDGETS; a table wins at benchmarking N).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import controls, exports, overlay, ranked
from lib.countries_fr import country_label
from lib.data_cache import DATA_DIR, get_corpus_facts_df
from lib.helpers import fr_int, fr_pct, log_linear_toggle, momentum_display, window_label

# =============================================================================
# Page config
# =============================================================================
st.set_page_config(page_title="Collaborations | Bibliométrie UL", page_icon="🤝", layout="wide")

HUB_DEFAULT_FLOOR = 20        # config.yaml workshop_tunables.hub_default_floor
QUADRANT_DEFAULT_FLOOR = 50   # config.yaml workshop_tunables.quadrant_default_floor
HUB_CHART_CAP = 20            # legibility cap on the companion overlay bar chart

# FR-ready label / binding-string dictionary (VIZ_SPEC 1.6: new pages build EN-first; the
# strings below are the plan/spec's own verbatim French, kept as named constants).
QUESTION_FR = (
    "Qui sont les partenaires de l'Université de Lorraine, où la relation est-elle "
    "équilibrée, et laquelle progresse ?"
)
S10_BANNER_FR = (
    "Un **« outil d'animation scientifique »** : repérer les partenaires de l'UL, voir où "
    "la relation est équilibrée ou non, et descendre vers le détail -- jamais un palmarès "
    "des partenaires entre eux."
)
SHARE_P_NULL_BY_DESIGN_FR = (
    ":grey[La colonne « Part partenaire » n'est renseignée que sur le corpus entier, tous "
    "types de publication confondus : une part hors conférence rapportée à un total qui, "
    "lui, les inclut ne serait pas une part réelle. Dans cet état, la colonne affiche « — » "
    "plutôt qu'un zéro.]"
)
CONSORTIUM_CAPTION_FR = (
    "« Cette part reflète la structure des UMR co-portées avec le CNRS dans les grands "
    "laboratoires lorrains — une part de co-signature, pas une part de gouvernance ni de "
    "financement du label. »"
)
MOMENTUM_EXEMPT_CAPTION_FR = (
    ":grey[Momentum calculé sur le corpus entier -- famille exemptée du filtre référentiel "
    "actif (non recalculée sous le toggle « hors référentiel »).]"
)
MOMENTUM_ISITE_EXEMPT_FR = (
    ":grey[Le momentum n'a pas de variante I-SITE : c'est une famille de mesure figée, "
    "calculée une fois sur le corpus entier.]"
)
CONSORTIUM_ISITE_NOTE_FR = (
    ":grey[Ce panneau porte déjà la vue I-SITE seule : la surcouche n'a rien à y ajouter.]"
)
HUB_ISITE_HELP_FR = "Superposition I-SITE : segment plus sombre = part I-SITE du volume affiché."

# Item #38, "Blocs a ajouter" (NARRATIVE_CONTRACT_pass6.md S2.9), colle verbatim, + the
# VIZ_SPEC_pass6 S7.2 panel caption the "one bar" allocation rule requires, folded in.
HUB_TABLE_COMMENT_LIRE_FR = (
    "**Comment lire.** Une ligne par partenaire, triée par co-publications décroissantes, "
    "jamais par FWCI. Deux parts, deux dénominateurs différents : **« Part UL »** rapporte "
    "les co-publications au corpus de l'Université de Lorraine ; **« Part partenaire »** "
    "les rapporte à la production propre du partenaire. Une relation peut donc peser lourd "
    "d'un côté et peu de l'autre : c'est précisément ce que ces deux colonnes servent à "
    "voir. Le tableau reste trié par volume de co-publications ; seule la part partenaire "
    "porte une barre.  \n"
    "**Pourquoi cet indicateur.** Le volume dit avec qui l'on publie ; les deux parts "
    "disent ce que cette relation représente pour chacun. C'est la lecture qui distingue "
    "un partenaire structurant d'un partenaire de volume."
)
# Item #40: le reste (part par pays, part internationale, part du corpus complet) vit
# dans la fiche partenaire -- pas de duplication ici.
HUB_TABLE_ZOOM_POINTER_FR = (
    ":grey[Part par pays, part internationale et part du corpus complet de l'UL : "
    "disponibles pour ce partenaire dans sa fiche (« Ouvrir la fiche partenaire » "
    "ci-dessous).]"
)
# Infobulle "Consortium I-SITE" (item #38, "Blocs a ajouter"), colle verbatim -- pas de
# help= natif possible sur une colonne texte via ranked_table(), rendue en legende.
CONSORTIUM_COL_HELP_FR = (
    ":grey[**Consortium I-SITE.** « Membre du consortium signataire de l'I-SITE. Les huit "
    "signataires sont identifiés par leur liste d'identifiants, jamais par une "
    "correspondance de nom. »]"
)
# Infobulle "Momentum" (item #38, "Blocs a ajouter") + fenetres nommees depuis la donnee
# (mom_w1_label/mom_w2_label) -- meme limite que ci-dessus (legende, pas un help= natif).
MOMENTUM_COL_HELP_TEMPLATE_FR = (
    ":grey[**Momentum.** « Comparaison de la part du partenaire dans le corpus entre deux "
    "fenêtres, avec un test de significativité : « en hausse », « en retrait », « stable », "
    "ou « non significatif » quand l'écart ne se distingue pas du bruit. Mesure figée, "
    "calculée sur le corpus entier. » Fenêtres actuelles : {win_first} puis {win_second} "
    "(recentrage médiane {median}, bande ±{band}, seuil de significativité {sig}).]"
)
# Item #39 (P4) -- nouvelle colonne "Part France hors site" (ptn_denominators).
FRANCE_HORS_SITE_HELP_FR = (
    "Part des co-publications françaises de l'UL portée par ce partenaire, une fois "
    "retirés les signataires du consortium I-SITE et les structures internes de "
    "l'établissement -- ce que ce partenaire pèse réellement une fois écartés les "
    "candidats naturels du site. Calculée sur le corpus entier, tous types de publication "
    "confondus ; « — » pour les partenaires hors France et pour les signataires "
    "eux-mêmes, exclus de ce dénominateur par construction."
)
FRANCE_HORS_SITE_COL_LABEL_FR = "Part France hors site"

MOM_LABELS = {
    "up": ("en hausse", "↑"),
    "down": ("en retrait", "↓"),
    "stable": ("stable", "→"),
    "ns": ("non significatif", "—"),
    "new": ("nouveau partenaire", "＋"),
    "dormant": ("partenaire dormant", "◦"),
}
MOM_COLORS = {"up": "#009E73", "down": "#D55E00", "stable": "#5A5F66", "ns": "#8C9196"}

# Fixed order (indicator_plan_FINAL.md §0 decision summary), NOT the deployed table's own
# row order -- consortium_weights carries 7 EXTERNAL members (id_set_size 1/1/1/1/1/3/6),
# not the plan's rounded "8" (UL itself is excluded from this satellite by construction).
CONSORTIUM_ORDER = ["CNRS", "INRAE", "AgroParisTech", "Inserm", "CHRU Nancy", "Georgia Tech", "Inria"]

HUB_BASE_COLOR = "#0072B2"  # shared base hue for the hub's companion overlay bar chart


def _fr_float(val, decimals: int = 2) -> str:
    """Plain French-decimal number for a text column (comma, no bar) -- fr_int/fr_pct
    cover grouped integers and 0-100 percentages; this covers a plain ratio like FWCI."""
    if val is None or (isinstance(val, float) and np.isnan(val)) or pd.isna(val):
        return "—"
    return f"{float(val):.{decimals}f}".replace(".", ",")


# =============================================================================
# Data (this page reads ptn_summary / ptn_mom_facts / consortium_weights -- eager per
# data_contract.yaml: ptn_summary "eager pin", consortium_weights "eager_load: true")
# =============================================================================
@st.cache_resource
def _load_ptn_summary() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "ptn_summary.parquet")


@st.cache_resource
def _load_ptn_mom_facts() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "ptn_mom_facts.parquet")


@st.cache_resource
def _load_consortium_weights() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "consortium_weights.parquet")


@st.cache_resource
def _load_ptn_denominators() -> pd.DataFrame:
    """Item #39/P4 -- one row per partner_id, (all,all)-basis share families
    (docs/data_contract.yaml #49). Page 8 only reads the France-hors-site share; the
    other three families (country/intl/corpus) are Zoom partenaire's own (P4/P12)."""
    return pd.read_parquet(DATA_DIR / "ptn_denominators.parquet")


def _snapshot_date() -> str:
    # G2 (NARRATIVE_CONTRACT_pass6.md S2.0): a plausible-looking fallback date is worse
    # than an honest "?" -- it would mislabel fresh data with a stale snapshot date.
    try:
        return str(get_corpus_facts_df()["snapshot_date"].iloc[0])
    except Exception:
        return "?"


def _mom_copubs_display(arrow) -> str:
    """VIZ_SPEC_pass6 S8.3's "Co-pubs (P1 -> P2)" hidden column: FR thousands, real
    arrow, from the raw '{c1}->{c2}' mom_count_arrow blob."""
    if pd.isna(arrow):
        return "—"
    try:
        c1, c2 = str(arrow).split("->")
        return f"{fr_int(int(float(c1)))} → {fr_int(int(float(c2)))}"
    except Exception:
        return "—"


def _parse_inwin(arrow) -> float:
    """mom_count_arrow is '{c1}->{c2}' raw in-window counts (data_contract.yaml)."""
    if pd.isna(arrow):
        return np.nan
    try:
        c1, c2 = str(arrow).split("->")
        return float(c1) + float(c2)
    except Exception:
        return np.nan


def _area_sizeref(values, max_px: float = 46.0) -> float:
    vmax = float(np.nanmax(values)) if len(values) else 1.0
    vmax = vmax if vmax > 0 else 1.0
    return 2.0 * vmax / (max_px ** 2)


# =============================================================================
# Sidebar + banners
# =============================================================================
ctrl = controls.sidebar()
include_conference = ctrl["include_conference"]
artifact_on = ctrl[controls.ARTIFACT_TOGGLE_KEY]
isite_overlay_on = ctrl[controls.ISITE_OVERLAY_KEY]
CONF_STATE = "all" if include_conference else "no_conf"
active_subset = ctrl.get("perimeter_subset", "all")
# ptn_summary genuinely carries subset rows for {all, in_isite} (subset_row_matrix); a stub
# perimeter (programme/roster, not yet populated) has no partner rows -- fall back to 'all'.
effective_subset = active_subset if active_subset in ("all", "in_isite") else "all"

st.title("🤝 Collaborations")
st.markdown(f"##### {QUESTION_FR}")
st.info(S10_BANNER_FR)
controls.banner()
controls.filtered_by_strip(page="collaborations")
# NARRATIVE_CONTRACT_pass6.md S2.9 (L206-210): the global perimeter selector is retired
# (lib.controls.sidebar() now hardcodes perimeter_subset="all", R1) -- active_subset can
# no longer differ from effective_subset, so this branch was dead code. Removed rather
# than reworded.

facts = get_corpus_facts_df()
SNAPSHOT_DATE = _snapshot_date()

_EXPORT_STATE = exports.ExportState(
    snapshot=SNAPSHOT_DATE, conf=include_conference, artifact=artifact_on,
    subset=effective_subset, artifact_applied=bool(artifact_on),
)
# Momentum / consortium / portage families are artifact-EXEMPT (app-wide ruling): the
# toggle never recomputes them, so their export header must say artifact_applied=False.
_EXPORT_STATE_EXEMPT = exports.ExportState(
    snapshot=SNAPSHOT_DATE, conf=include_conference, artifact=artifact_on,
    subset=effective_subset, artifact_applied=False,
)

ptn_all = _load_ptn_summary()
ptn_active = ptn_all[(ptn_all["subset_id"] == effective_subset) & (ptn_all["conf_state"] == CONF_STATE)].copy()
CO_COL = controls.xa(ptn_active, "co_works_full")

# Momentum facts (ptn_mom_facts), loaded ONCE and shared by the hub table's quantified
# momentum column (S8.3) and the quadrant tab below -- mom_w1_label/mom_w2_label (S-DAT,
# pass 6) replace every hardcoded window literal this page used to carry (items #7/#38,
# docs/YEAR_UPDATE_DESIGN.md S5.3 "the worst site is yours: L573-574").
_mf_all = _load_ptn_mom_facts()
_mf_rows = _mf_all[_mf_all["conf_state"] == CONF_STATE]
mf_row = _mf_rows.iloc[0] if not _mf_rows.empty else None
mom_w1_label = str(mf_row["mom_w1_label"]) if mf_row is not None else "fenêtre 1"
mom_w2_label = str(mf_row["mom_w2_label"]) if mf_row is not None else "fenêtre 2"

# =============================================================================
# Section 1 -- KPI row
# =============================================================================
st.markdown("## Vue d'ensemble")

_frow = facts.set_index("conf_state").loc[CONF_STATE]


def _fv(base: str):
    return _frow[controls.xa(facts, base)]


n_partners_ge10 = int((ptn_active[CO_COL] >= 10).sum())
pct_intl = float(_fv("ul_intl_share")) * 100
pct_company = float(_fv("ul_company_share")) * 100
corpus_works = float(_fv("corpus_works"))
collab_works = float(_fv("corpus_collaborative_works"))
pct_collab = (collab_works / corpus_works * 100) if corpus_works else float("nan")
france_intl = float(_frow["france_intl_share"]) * 100

c1, c2, c3, c4 = st.columns(4)
c1.metric("Partenaires (≥10 co-publications)", fr_int(n_partners_ge10))
c2.metric("% travaux internationaux", fr_pct(pct_intl), help=f"Repère France : {fr_pct(france_intl)}")
c3.metric("% travaux avec une entreprise", fr_pct(pct_company))
c4.metric("% travaux collaboratifs", fr_pct(pct_collab) if not math.isnan(pct_collab) else "n/a")
if effective_subset != "all":
    st.caption(
        ":grey[Les trois dernières tuiles portent sur le corpus entier ; seul le nombre "
        f"de partenaires suit le périmètre affiché (« {effective_subset} »).]"
    )

st.markdown("---")

# =============================================================================
# Section 2 -- tbl-partners-hub -> lib.ranked.ranked_table() + overlay bar companion
# =============================================================================
st.markdown("## Partenaires du site")
st.caption(
    f"{fr_int(len(ptn_active))} partenaire(s) dans ce périmètre, "
    f"{fr_int(int(ptn_active[CO_COL].sum()))} co-publications au total. Tri par défaut : "
    "co-publications décroissantes -- jamais le FWCI."
)

col_f1, col_f2 = st.columns([2, 1])
with col_f1:
    types_present = sorted(ptn_active["type_openalex"].dropna().astype(str).unique().tolist())
    type_filter = st.multiselect("Filtrer par type", options=types_present, default=[], key="hub_type_filter")
with col_f2:
    floor = st.number_input(
        "Seuil (co-publications)", min_value=1, value=HUB_DEFAULT_FLOOR, step=5, key="hub_floor",
    )

_base = ptn_active[ptn_active["type_openalex"].astype(str).isin(type_filter)] if type_filter else ptn_active
_n_below_floor = int((_base[CO_COL] < floor).sum())
_base_sorted = _base[_base[CO_COL] >= floor].sort_values(CO_COL, ascending=False).reset_index(drop=True)
# Item #39/P4: France-hors-site share, merged in ONCE here so both the on-screen table
# AND the export below (built from this same frame) carry it -- never a second read.
_base_sorted = _base_sorted.merge(
    _load_ptn_denominators()[["partner_id", "share_of_ul_france_copubs_hors_site"]],
    on="partner_id", how="left",
)

if _n_below_floor:
    st.caption(
        f":grey[{fr_int(_n_below_floor)} partenaire(s) sous le seuil de {fr_int(floor)} "
        "co-publications ne sont pas affiché(s) -- accessibles en abaissant le seuil.]"
    )

if _base_sorted.empty:
    st.info("Aucun partenaire ne correspond à ces filtres.")
else:
    _facts_for_mom = mf_row if mf_row is not None else {"recentring_median": None}

    # Prepared, ranked_table()-ready frame: internal column names stay technical (R12:
    # English column names are fine, French display via ref_labels/progress_cols below).
    prepared = pd.DataFrame({
        "partner_id": _base_sorted["partner_id"],
        "display_name": _base_sorted["display_name"],
        # Item #8: FR country name via lib.countries_fr.country_label(). Check pd.isna()
        # BEFORE stringifying so a genuinely missing code never becomes the literal
        # string "nan" en route (same trap consortium_weights' own "member" column hits
        # below, on a Categorical dtype).
        "country_code": _base_sorted["country_code"].apply(
            lambda c: country_label(c) if pd.notna(c) else "—"
        ),
        "type_openalex": _base_sorted["type_openalex"].astype(str).replace("nan", "—"),
        "co_works": _base_sorted[CO_COL].astype(int),
        "co_works_fractional": _base_sorted["co_works_fractional"].round(2),
        "share_ul": (_base_sorted[controls.xa(ptn_active, "share_ul")] * 100).round(1),
        # Item #38b (VIZ_SPEC_pass6 S7.2): "Part partenaire" becomes the table's ONE
        # ProgressColumn, so it must be numeric (0-100, NaN preserved) rather than the
        # pre-formatted "--" string pass 5 shipped. A NULL value (share_p is NULL, never
        # 0, off the (all,all) basis) now reads as an EMPTY bar, never a zero-length one;
        # the column help below states the rule explicitly (honesty rule 3).
        "share_p_pct": (_base_sorted["share_p"] * 100).round(1),
        "fwci_median_text": _base_sorted[controls.xa(ptn_active, "fwci_fr_median")].apply(_fr_float),
        "fwci_mean_text": _base_sorted[controls.xa(ptn_active, "fwci_fr_mean")].apply(_fr_float),
        "n_ul_labs": _base_sorted["n_ul_labs"].astype(int),
        "isite_co_works": _base_sorted["isite_co_works"].astype(int),
        "isite_share": (_base_sorted["isite_share"] * 100).round(1),
        # Item #39/P4: NULL for non-FR partners AND for the consortium signatories
        # themselves (excluded from that population by definition, docs/data_contract.yaml
        # #49). A pre-formatted TEXT column, like share_p_pct's siblings used to be pass
        # 5 -- st.column_config.NumberColumn renders a NaN value as the literal string
        # "None" on this Streamlit build (confirmed live, progress/PCOL.md), which is
        # worse than a blank cell; "--" is the honest, human-readable form.
        "france_hors_site_text": _base_sorted["share_of_ul_france_copubs_hors_site"].apply(
            lambda v: fr_pct(float(v) * 100) if pd.notna(v) else "—"
        ),
        # Item #38c (VIZ_SPEC_pass6 S8): quantified re-expression of the frozen pass-3
        # momentum family via the ONE shared formatter (lib.helpers.momentum_display) --
        # zero recomputation, same text P-ZP/P-PF wire from the identical function.
        "mom_chip": [
            momentum_display(
                {"mom_category": c, "mom_w1_share": w1, "mom_w2_share": w2, "mom_count_arrow": a},
                _facts_for_mom,
            )[0]
            for c, w1, w2, a in zip(
                _base_sorted["mom_category"], _base_sorted["mom_w1_share"],
                _base_sorted["mom_w2_share"], _base_sorted["mom_count_arrow"],
            )
        ],
        # VIZ_SPEC_pass6 S8.3's hidden companion column: "Co-pubs (P1 -> P2)".
        "mom_copubs": _base_sorted["mom_count_arrow"].apply(_mom_copubs_display),
    })

    _hidden_cols = ["partner_id", "fwci_mean_text", "mom_copubs"]  # R14 mean-hidden + S8.3 pair
    if not isite_overlay_on:
        # R1 overlay-off neutrality: the ISITE decomposition columns disappear entirely
        # when the global toggle is off, same as the companion chart below.
        _hidden_cols += ["isite_co_works", "isite_share"]

    ref_labels = {
        "display_name": "Partenaire",
        "country_code": "Pays",
        "type_openalex": "Type",
        "co_works": "Co-publications",
        "co_works_fractional": f"Fractionnel{' †' if artifact_on else ''}",
        "share_ul": "Part UL",
        "share_p_pct": "Part partenaire",
        "fwci_median_text": "FWCI médian (réf. France)",
        "fwci_mean_text": "FWCI moyen (réf. France)",
        "n_ul_labs": "Labos UL",
        "isite_co_works": "Co-pubs I-SITE",
        "isite_share": "Part I-SITE",
        "france_hors_site_text": FRANCE_HORS_SITE_COL_LABEL_FR,
        "mom_chip": "Momentum",
        "mom_copubs": "Co-pubs (P1 → P2)",
        "Consortium": "Consortium I-SITE",
    }
    # Item #38b (VIZ_SPEC_pass6 S7.2): "one ProgressColumn per visible table. Never
    # two." -- "Part partenaire" is the ONE bar. S-LENS D6 fix (pass-6 fix round):
    # every other share/volume below is now an EXPLICIT `number_cols` entry rather
    # than a second `progress_cols` entry left to the lib's auto-demote fallback
    # (byte-identical render, no production warning).
    progress_cols = {
        "share_p_pct": {
            "format": "%.1f%%", "max_value": 100,
            "help": (
                "Part de ce partenaire dans le corpus entier de l'Université de "
                "Lorraine, rapportée au volume propre du partenaire hors périmètre "
                "lorrain (mesuré séparément). Renseignée uniquement sur le corpus "
                "entier, tous types de publication confondus ; « — » ailleurs."
            ),
        },
    }
    number_cols = {
        "co_works": {
            "format": "%d",
            "help": "Nombre de co-publications avec ce partenaire -- le tableau est trié par ce volume.",
        },
        "share_ul": {
            "format": "%.1f%%",
            "help": "Part de ces co-publications dans le corpus entier de l'Université de Lorraine.",
        },
    }
    if isite_overlay_on:
        number_cols["isite_share"] = {"format": "%.1f%%", "help": HUB_ISITE_HELP_FR}

    visible = ranked.ranked_table(
        prepared, key="hub", id_col="partner_id", search_cols=["display_name"],
        progress_cols=progress_cols, number_cols=number_cols, mean_cols=_hidden_cols, ref_labels=ref_labels,
    )
    if artifact_on:
        st.caption(":grey[† Fractionnel : famille de mesure figée (non recalculée sous le filtre référentiel actif).]")
    if CONF_STATE != "all" or effective_subset != "all":
        st.caption(SHARE_P_NULL_BY_DESIGN_FR)
    st.caption(HUB_TABLE_COMMENT_LIRE_FR)
    # Items #38/#39 "Blocs a ajouter": infobulles "Consortium I-SITE" / "Momentum" /
    # "Part France hors site" -- none of the three is a plain numeric ProgressColumn,
    # so lib.ranked.ranked_table()'s progress_cols help= passthrough (the only
    # per-column tooltip mechanism it exposes) does not reach them; rendered as a
    # collapsed expander instead (reported as a lib gap in progress/PCOL.md).
    with st.expander(
        "ℹ️ Colonnes « Consortium I-SITE », « Momentum » et « Part France hors site »",
        expanded=False,
    ):
        st.caption(CONSORTIUM_COL_HELP_FR)
        _mom_band_txt = fr_pct(float(mf_row["band_pct"]), 0) if mf_row is not None else "n/a"
        _mom_sig_txt = fr_pct(float(mf_row["significance_p"]) * 100, 0) if mf_row is not None else "n/a"
        _mom_median_txt = _fr_float(mf_row["recentring_median"], 2) if mf_row is not None else "n/a"
        st.caption(MOMENTUM_COL_HELP_TEMPLATE_FR.format(
            win_first=mom_w1_label, win_second=mom_w2_label, median=_mom_median_txt,
            band=_mom_band_txt, sig=_mom_sig_txt,
        ))
        st.caption(f":grey[**{FRANCE_HORS_SITE_COL_LABEL_FR}.** {FRANCE_HORS_SITE_HELP_FR}]")
    st.caption(HUB_TABLE_ZOOM_POINTER_FR)

    # -- Companion overlay bar chart (R1, docs/OVERLAY_MATRIX.md §8: ptn_summary.isite_co_works
    # is the reference "EXISTING (same-row)" case this whole pass generalises from) -- the
    # currently visible partners (mask + query + depth already applied by ranked_table()),
    # capped for legibility (LEGIBILITY_BUDGETS convention already used elsewhere on this page).
    chart_rows = visible.head(HUB_CHART_CAP).sort_values("co_works", ascending=True)
    if not chart_rows.empty:
        st.markdown("###### Volume des partenaires affichés")
        fig_hub = overlay.overlay_bars(
            categories=chart_rows["display_name"].tolist(),
            totals=chart_rows["co_works"].tolist(),
            isite=chart_rows["isite_co_works"].tolist(),
            colors=HUB_BASE_COLOR, isite_on=isite_overlay_on, orientation="h",
        )
        fig_hub.update_layout(
            height=max(220, 26 * len(chart_rows)), margin=dict(t=10, l=10, r=20, b=30),
            xaxis_title="Co-publications", showlegend=isite_overlay_on,
        )
        st.plotly_chart(fig_hub, width="stretch")
        if isite_overlay_on:
            st.caption(f":grey[{overlay.isite_share_caption(float(chart_rows['co_works'].sum()), float(chart_rows['isite_co_works'].sum()))} sur les partenaires affichés.]")

    # -- Compact navigator: ranked_table() has no on_select (frozen API), so the previous
    # row-click -> Partner Drilldown jump is replaced by a picker over the SAME visible
    # rows (disclosed adaptation, progress/PF_partners_geo.md).
    if not visible.empty:
        nav_col1, nav_col2 = st.columns([4, 1])
        nav_options = {f'{r["display_name"]} ({fr_int(int(r["co_works"]))} co-pubs)': r["partner_id"]
                       for _, r in visible.iterrows()}
        nav_pick = nav_col1.selectbox(
            "Ouvrir la fiche partenaire", options=list(nav_options.keys()), key="hub_nav_pick",
            label_visibility="collapsed", placeholder="Ouvrir la fiche partenaire...",
        )
        if nav_col2.button("→ Ouvrir", key="hub_nav_open") and nav_pick:
            pid = nav_options[nav_pick]
            st.session_state["nav_partner_id"] = pid
            st.query_params["partner_id"] = pid
            st.switch_page("pages/9_🔍_Zoom_partenaire.py")

    # -- Export: the type/floor-filtered population, re-applying the ranked_table()'s OWN
    # query/member-mask state (read back from its widget keys) so the export mirrors
    # exactly what is on screen, same "filtre courant" contract as before this pass.
    _query_val = st.session_state.get("hub_query", "")
    _hide_members_val = st.session_state.get("hub_hide_members", False)
    _export_pop = ranked.mask_members(_base_sorted, "partner_id", ranked.CONSORTIUM_IDS, _hide_members_val)
    _export_pop = ranked.filter_by_query(_export_pop, _query_val, ["display_name"])
    _export_cols = [
        "partner_id", "display_name", "country_code", "type_openalex", "consortium_member",
        CO_COL, "co_works_fractional", controls.xa(ptn_active, "share_ul"), "share_p",
        "share_of_ul_france_copubs_hors_site",
        controls.xa(ptn_active, "fwci_fr_median"), controls.xa(ptn_active, "fwci_fr_mean"),
        "n_ul_labs", "isite_co_works", "isite_share", "mom_class", "mom_category", "mom_count_arrow",
    ]
    _hub_state = exports.ExportState(
        snapshot=SNAPSHOT_DATE, conf=include_conference, artifact=artifact_on,
        subset=effective_subset, artifact_applied=bool(artifact_on),
        deferred_twins=["co_works_fractional"],
        filters={"type": ",".join(type_filter) or "all", "floor": floor, "search": _query_val or "",
                 "hide_members": _hide_members_val},
        method="Hub des partenaires (ptn_summary) -- filtre courant + médiane et moyenne FWCI (R14).",
    )
    exports.attach_download(st, _export_pop[_export_cols], "v1-collaboration", "partners-hub", _hub_state)

st.markdown("---")

# =============================================================================
# Section 3 -- reciprocity (half) + consortium (half)
# =============================================================================
col_recip, col_consort = st.columns(2)

with col_recip:
    st.markdown("### Réciprocité")
    st.caption(
        "Ce panneau ne porte pas encore de graphique : la mesure existe -- elle est "
        "visible dans la colonne « Part partenaire » du tableau ci-dessus -- mais sa "
        "représentation visuelle n'est pas encore construite."
    )
    if CONF_STATE == "all" and effective_subset == "all":
        _n_recip = int(ptn_active["share_p"].notna().sum())
        st.success(
            f"La part du partenaire est mesurée pour {fr_int(_n_recip)} des "
            f"{fr_int(len(ptn_active))} partenaires de ce périmètre : elle demande, pour "
            "chacun, le volume propre du partenaire hors périmètre lorrain. Les "
            "partenaires pour lesquels cette mesure n'existe pas affichent « — », "
            "jamais un zéro."
        )
    else:
        st.caption(SHARE_P_NULL_BY_DESIGN_FR)

with col_consort:
    st.markdown("### Consortium I-SITE")
    cw = _load_consortium_weights()
    cw_isite = cw[(cw["scope"] == "isite") & (cw["conf_state"] == CONF_STATE)].copy()
    # `member` is a category dtype (data_contract.yaml) -- .map() on a Categorical can
    # preserve categorical dtype, and .fillna(99) then raises "Cannot setitem on a
    # Categorical with a new category" if 99 isn't already one of its categories.
    # astype(str) first so the mapped result is a plain (non-categorical) Series.
    cw_isite["_order"] = cw_isite["member"].astype(str).map({m: i for i, m in enumerate(CONSORTIUM_ORDER)}).fillna(99)
    cw_isite = cw_isite.sort_values("_order")

    for _, r in cw_isite.iterrows():
        with st.container(border=True):
            cc1, cc2 = st.columns([3, 2])
            cc1.markdown(f"**{r['member_label']}** · membre du consortium I-SITE")
            cc2.metric("Part ISITE", fr_pct(float(r["share_of_scope"]) * 100))
            st.caption(
                f"{fr_int(int(r['co_works_distinct']))} co-publications distinctes (union sur "
                f"{fr_int(int(r['id_set_size']))} identifiant(s) OpenAlex)."
            )
            if pd.notna(r.get("incl_own_centre_variant_share")):
                st.caption(
                    ":grey[Variante incluant le centre Inria propre à l'Université de "
                    f"Lorraine : {fr_pct(float(r['incl_own_centre_variant_share']) * 100)}. "
                    "La variante de référence reste une décision de l'établissement.]"
                )
            _match = ptn_active[ptn_active["display_name"].str.lower() == str(r["member_label"]).lower()]
            if int(r["id_set_size"]) == 1 and not _match.empty:
                if st.button("→ Ouvrir la fiche partenaire", key=f"consort_open_{r['member']}"):
                    pid = _match.iloc[0]["partner_id"]
                    st.session_state["nav_partner_id"] = pid
                    st.query_params["partner_id"] = pid
                    st.switch_page("pages/9_🔍_Zoom_partenaire.py")
            else:
                st.caption(":grey[Regroupe plusieurs identifiants -- pas de fiche partenaire unique.]")

    st.caption(CONSORTIUM_CAPTION_FR)
    if artifact_on:
        st.caption(":grey[Poids structurels (id-sets) -- non recalculés sous le filtre référentiel actif.]")
    if isite_overlay_on:
        st.caption(CONSORTIUM_ISITE_NOTE_FR)
    exports.attach_download(
        st, cw_isite.drop(columns="_order"), "v1-collaboration", "consortium", _EXPORT_STATE_EXEMPT,
    )

st.markdown("---")

# =============================================================================
# Section 4 -- momentum quadrant, one TAB deep
# =============================================================================
st.markdown("## Dynamique des partenariats")
tab_note, tab_quadrant = st.tabs(["Repère", "📈 Dynamique (momentum)"])

with tab_note:
    # Item #7 / FEN (NARRATIVE_CONTRACT_pass6.md S2.9 L501-504): the windows are named
    # FROM DATA (ptn_mom_facts.mom_w1_label/mom_w2_label), never written by hand.
    st.markdown(
        f"Le quadrant de momentum compare deux fenêtres, {mom_w1_label} et {mom_w2_label}, "
        "selon une définition figée. Il vit dans l'onglet **Dynamique (momentum)**."
    )

with tab_quadrant:
    # mf_row/_mf_rows already loaded once, above Section 1, and shared with the hub
    # table's quantified momentum column (S8.3) -- no second read of ptn_mom_facts here.
    if _mf_rows.empty:
        st.warning("Constantes de momentum indisponibles pour cet état.")
    else:
        median = float(mf_row["recentring_median"])
        band_pct = float(mf_row["band_pct"]) / 100.0

        if artifact_on:
            st.caption(MOMENTUM_EXEMPT_CAPTION_FR)
        if isite_overlay_on:
            st.caption(MOMENTUM_ISITE_EXEMPT_FR)

        q_col1, q_col2 = st.columns([2, 1])
        with q_col1:
            q_floor = st.number_input(
                "Seuil (volume en fenêtre, c1+c2)", min_value=1, value=QUADRANT_DEFAULT_FLOOR,
                step=10, key="quadrant_floor",
            )
        with q_col2:
            axis_type = log_linear_toggle("quadrant_axis_toggle")  # R18

        dfq = ptn_all[(ptn_all["subset_id"] == "all") & (ptn_all["conf_state"] == CONF_STATE)].copy()
        dfq = dfq[dfq["mom_class"].notna()].copy()
        dfq["_inwin"] = dfq["mom_count_arrow"].map(_parse_inwin)
        dfq = dfq[dfq["_inwin"] >= q_floor].copy()
        dfq = dfq[(dfq["mom_w1_share"] > 0) & (dfq["mom_w2_share"] > 0)]

        fig = go.Figure()
        if not dfq.empty:
            sizeref = _area_sizeref(dfq["co_works_full"])
            for cls in ["ns", "stable", "down", "up"]:  # ns first: background, never hides others
                d = dfq[dfq["mom_class"] == cls]
                if d.empty:
                    continue
                label, sym = MOM_LABELS[cls]
                fig.add_trace(go.Scatter(
                    x=d["mom_w1_share"], y=d["mom_w2_share"], mode="markers",
                    marker=dict(
                        size=d["co_works_full"], sizemode="area", sizeref=sizeref, sizemin=3,
                        color=MOM_COLORS[cls], line=dict(width=0.5, color="white"),
                    ),
                    name=f"{sym} {label} ({len(d)})",
                    # VIZ_SPEC_pass6 S0.1: hovertemplate format specs are locale-blind
                    # (%{customdata:.3f} renders "0.030", an English decimal point in a
                    # FR UI) -- pre-format the p-value into customdata, bare %{} in the
                    # template, no format spec.
                    customdata=np.stack(
                        [
                            d["display_name"], d["mom_count_arrow"].fillna(""),
                            d["mom_p_value"].apply(lambda p: _fr_float(p, 3) if pd.notna(p) else "n/a"),
                        ],
                        axis=-1,
                    ),
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>Fenêtre 1→2 : %{customdata[1]}"
                        "<br>p=%{customdata[2]}<extra></extra>"
                    ),
                ))
            xmin = float(dfq["mom_w1_share"].min())
            xmax = float(dfq["mom_w1_share"].max())
            xs = np.geomspace(max(xmin, 1e-4), max(xmax, xmin * 1.01, 1e-3), 60)
            fig.add_trace(go.Scatter(
                x=xs, y=xs * median, mode="lines", line=dict(color="#333333", dash="dot"),
                name=f"médiane recentrée ({_fr_float(median, 4)})", hoverinfo="skip",
            ))
            band_x = list(xs) + list(xs[::-1])
            band_y = list(xs * median * (1 + band_pct)) + list(xs[::-1] * median * (1 - band_pct))
            fig.add_trace(go.Scatter(
                x=band_x, y=band_y, fill="toself", fillcolor="rgba(51,51,51,0.08)",
                line=dict(width=0), name=f"bande ±{band_pct * 100:.0f}%", hoverinfo="skip",
            ))
        # Item #7 (docs/YEAR_UPDATE_DESIGN.md S5.3: "the worst site is yours", L573-574):
        # axis titles named FROM DATA (mom_w1_label/mom_w2_label), never hardcoded --
        # after a period-window change the axes would otherwise state the wrong
        # periods while plotting the right data, the most dangerous failure mode.
        fig.update_xaxes(type=axis_type, title=f"Part fenêtre 1 ({mom_w1_label})")
        fig.update_yaxes(type=axis_type, title=f"Part fenêtre 2 ({mom_w2_label})")
        fig.update_layout(height=560, legend=dict(orientation="h", y=-0.15), margin=dict(t=20))
        st.plotly_chart(fig, width="stretch")

        _counts = {c: int((dfq["mom_class"] == c).sum()) for c in ["up", "down", "stable", "ns"]}
        st.caption(
            f"{fr_int(len(dfq))} partenaire(s) au seuil ≥{fr_int(q_floor)} co-publications en fenêtre -- "
            + ", ".join(f"{MOM_LABELS[c][0]} {fr_int(n)}" for c, n in _counts.items())
        )
        st.caption(
            "**Comment lire.** Échelle logarithmique par défaut ; la bascule « échelle "
            "linéaire » donne un rendu à écart absolu. La diagonale marque la médiane "
            "recentrée, la bande couvre le bruit normal attendu. « Non significatif » "
            "(gris) est une classe, pas une absence de donnée, et un partenaire situé à "
            "la marge du seuil peut changer de classe d'une mesure à l'autre. Une "
            "fenêtre qui recouvre une année atypique (arrêt d'activité, fusion "
            "d'établissement) déplace mécaniquement les deux parts : la classe se lit "
            "avec le calendrier du partenaire en tête."
        )

        dfnd = ptn_all[
            (ptn_all["subset_id"] == "all") & (ptn_all["conf_state"] == CONF_STATE)
            & (ptn_all["mom_category"].isin(["new", "dormant"]))
        ]
        if not dfnd.empty:
            st.markdown("**Nouveaux partenaires / partenaires dormants** (hors quadrant, par construction)")
            nd_table = dfnd[["display_name", "mom_category", "co_works_full"]].rename(columns={
                "display_name": "Partenaire", "mom_category": "Catégorie", "co_works_full": "Co-publications",
            }).sort_values("Co-publications", ascending=False)
            st.dataframe(nd_table, hide_index=True, width="stretch", height=min(250, 38 * (len(nd_table) + 1)))

        _quad_export_cols = [
            "partner_id", "display_name", "mom_class", "mom_category", "mom_w1_share",
            "mom_w2_share", "mom_p_value", "mom_count_arrow", "co_works_full",
        ]
        exports.attach_download(
            st, dfq[_quad_export_cols] if not dfq.empty else dfq,
            "v1-collaboration", "momentum-quadrant", _EXPORT_STATE_EXEMPT,
        )

st.markdown("---")
st.caption(f"Instantané : {SNAPSHOT_DATE} · fenêtre {window_label()}.")
