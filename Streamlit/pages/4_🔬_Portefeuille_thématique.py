"""
Portefeuille thématique — forme, spécialisation et empreinte ODD du portefeuille de
recherche de l'Université de Lorraine (pass-5 split, ruling R9).

Sections :
1. Carte du portefeuille (treemap domaine -> champ -> sous-champ)
2. Domaines (table + boxplots FWCI, sous panneau repliable)
3. Champs (table + boxplots FWCI, sous panneau repliable)
4. Sous-champs (table pleine profondeur, zero-fill -- pass 6 #20)
5. Topics OpenAlex (table pleine profondeur, zero-fill -- pass 6 #20)
6. Objectifs de développement durable (panneau principal, méthode SIRIS/voctagger)
7. ODD par laboratoire (croisement sdg_lab_methods -- pass 6 #7/#12: part du corpus
   du labo étiquetée + colonnes méthode SIRIS/Aurora ; le profil ODD d'un labo
   individuel est parti sur la page Laboratoires, #8)
8. ODD, l'UL face à ses pairs (bench_sdg, méthode OpenAlex/Aurora)
9. Spécialisation vs France (position -- avec surcouche I-SITE en row-swap)

Le positionnement frontière, la diversité disciplinaire (Rao-Stirling) et la matrice
de co-discipline sont traités sur la page « Positionnement » ; le panneau de
financement a été retiré de l'interface (voir docs/METHODES.md §9.13) -- la table et
le constructeur restent dans le pipeline.

Pass 6 (#18) : le momentum (deux fenêtres de publication, méthode figée
lib46_momentum) remplace le CAGR comme indicateur de dynamique partout sur cette
page. La colonne CAGR reste calculée dans les tables déployées (consommateurs gelés)
mais n'est plus jamais rendue ici.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from lib.app_config import sdg_column, sdg_label, sdg_variant
from lib.data_cache import (
    load_sdg_siris, load_sdg_three_way, get_pubs_slim, DATA_DIR, get_corpus_facts_df,
)
from lib.thematic import excluded_counts_from_facts, get_overview, get_treemap
from lib import controls, exports
from lib.overlay import darken
from lib.links import openalex_url
from lib.ranked import ranked_table, fr_int, fr_pct
from lib.helpers import (
    DOMAIN_ORDER,
    DOMAIN_ORDER_DISPLAY,
    DOMAIN_COLORS,
    DOMAIN_EMOJI,
    UNCLASSIFIED_DOMAIN_NAME,
    get_domain_id_to_name,
    get_field_id_to_name,
    get_field_id_to_domain_id,
    get_subfield_id_to_name,
    get_subfield_id_to_domain_id,
    get_subfield_id_to_field_id,
    get_field_order_by_domain,
    get_domain_color,
    DOMAIN_NAMES_ORDERED,
    parse_pipe_float_list,
    render_domain_legend,
    render_excluded_disclosure,
    log_linear_toggle,
    UL_OPENALEX_ID,
    window_label,
    FR_THIN_SPACE,
    MOMENTUM_GLYPHS,
)

# =============================================================================
# Page config
# =============================================================================
st.set_page_config(
    page_title="Portefeuille thématique | Université de Lorraine",
    page_icon="🔬",
    layout="wide",
)

st.title("🔬 Portefeuille thématique")
st.markdown(
    "**Quelle est la forme du portefeuille de recherche de l'Université de Lorraine — "
    "volumes, spécialisation par rapport à la France, empreinte sur les Objectifs de "
    "développement durable — et quelle part l'I-SITE y représente ?** Domaines, champs, "
    "sous-champs et topics de la taxonomie OpenAlex ; les questions de positionnement "
    "frontière, diversité disciplinaire et co-discipline sont traitées sur la page "
    "**🧭 Positionnement**."
)

# W5 chassis adoption (VIZ_SPEC 1.5 / 2.8 inheritance, chain pass 3 P3) -- same pattern as
# P5 on page 1 (progress/P5_home_lab.md): controls.sidebar() is a drop-in superset of the
# D52 toggle this page already rendered (same lib.helpers.conference_toggle(), same
# "include_conference" session-state key), wrapped with the perimeter selector, the
# artifact toggle and the snapshot badge.
_controls_state = controls.sidebar()
include_conference = _controls_state["include_conference"]
_ARTIFACT_ON = _controls_state[controls.ARTIFACT_TOGGLE_KEY]

# Disclosure strips (rev 3.1 R-A/R-B).
controls.filtered_by_strip(page="portefeuille_thematique")
controls.ships_v2_strip()  # ships-v2 honest strip for the shipped content below, while ON
if _controls_state.get("perimeter_subset", "all") != "all":
    controls.perimeter_disclosure_strip()  # R-B: the shipped panels carry no subset rows

# Export state for the PARITY panels below (treemap/domain/field/subfield/topic/SDG):
# artifact_applied is ALWAYS False -- ships-v2, nothing recomputes under the toggle
# (rev 3.1 R-A). The 5 NEW panels further down build their OWN per-panel export state
# (they DO recompute, via the _xa twin columns).
_facts = get_corpus_facts_df()
_SNAPSHOT_DATE = str(_facts["snapshot_date"].iloc[0]) if len(_facts) else "?"
_EXPORT_STATE_PARITY = exports.ExportState(
    snapshot=_SNAPSHOT_DATE,
    conf=include_conference,
    artifact=_ARTIFACT_ON,
    subset=_controls_state.get("perimeter_subset", "all"),
    artifact_applied=False,
)

# =============================================================================
# Load data
# =============================================================================
df_overview = get_overview(include_conference)
df_treemap_raw = get_treemap(include_conference)

# Lookups
domain_id2name = get_domain_id_to_name()
field_id2name = get_field_id_to_name()
field_id2domain = get_field_id_to_domain_id()
subfield_id2name = get_subfield_id_to_name()
subfield_id2domain = get_subfield_id_to_domain_id()
subfield_id2field = get_subfield_id_to_field_id()


# =============================================================================
# P3 (chain pass 3) -- shared loaders + resolver for the thematic-extension tables
# =============================================================================
@st.cache_data
def _load_table(name: str) -> pd.DataFrame:
    """
    Generic cached parquet loader for the 5 thm_* tables this pass adds, plus
    dim_artifact_topics. Local to this page (fence: pages/lib.{controls,exports,lazy}
    only -- no lib/data_cache.py edit) -- one cached function per (name) key.
    """
    return pd.read_parquet(DATA_DIR / f"{name}.parquet")


@st.cache_data
def _artifact_topic_ids() -> frozenset:
    """The 811 flagged topic_ids (dim_artifact_topics), for the † marker + filter."""
    return frozenset(_load_table("dim_artifact_topics")["topic_id"])


def _conf_state_value(include_conf: bool) -> str:
    """pipeline conf_state column value ('all'/'no_conf') -- NOT the export filename token."""
    return "all" if include_conf else "no_conf"


# _resolve_subset() (pre-pass-5: resolved the sidebar perimeter selector's active
# subset_id) is RETIRED (R1) -- the global perimeter selector no longer exists, so
# `perimeter_subset` is the hardcoded constant "all" everywhere (lib.controls.sidebar()
# docstring). The thm_specialisation table's own "in_isite" row is read directly, by
# name, wherever this page wants the ISITE row-swap comparator (T4 below) -- gated by
# the NEW isite_overlay toggle instead of a dead session-state read.


def _new_panel_state(subset_used: str, deferred: list | None = None) -> exports.ExportState:
    """Shared export-state builder for the 5 NEW panels: they DO honour the toggle."""
    return exports.ExportState(
        snapshot=_SNAPSHOT_DATE, conf=include_conference, artifact=_ARTIFACT_ON,
        subset=subset_used, artifact_applied=_ARTIFACT_ON, deferred_twins=deferred or [],
    )


_CONF_STATE_VALUE = _conf_state_value(include_conference)

# =============================================================================
# Helper functions
# =============================================================================
def get_domain_name_from_id(dom_id):
    try:
        return domain_id2name.get(int(dom_id), "Other")
    except (ValueError, TypeError):
        return "Other"

def get_domain_emoji(dom_name):
    return DOMAIN_EMOJI.get(dom_name, "⬜")

def format_pct(val):
    if pd.isna(val):
        return "—"
    try:
        return f"{float(val)*100:.1f}%"
    except (ValueError, TypeError):
        return "—"

MOMENTUM_COL_HELP_FR = (
    "Momentum : comparaison de deux fenêtres de publication (méthode figée, "
    "testée au seuil de signification usuel, bande de stabilité ±25 % sur le "
    "ratio recentré de part de corpus). L'écart affiché est la différence de "
    "part entre les deux fenêtres, en points de pourcentage -- jamais un taux "
    "de croissance."
)


def format_momentum(mom_class, w1_share, w2_share) -> str:
    """
    #18 -- momentum replaces CAGR, thematic grain (mom_class/mom_w1_share/
    mom_w2_share: thematic_overview, thematic_detail_sublevels, topics_zero_fill,
    subfields_zero_fill). NOT lib.helpers.momentum_display(): that formatter's
    quantified delta needs a recentring_median which the thematic-grain builders
    (pipeline/44_build_thematic.py, /44c_build_detail_sublevels.py) print to their
    own build log but never persist to a deployed table -- calling it here would
    silently collapse every real up/down/stable class to "--". docs/data_contract.
    yaml's own thematic_overview.mom_w1_share entry names the intended reading
    instead ("lets a consumer compute a signed pp difference vs mom_w2_share"): a
    plain percentage-point gap between the two window shares, computed here at
    render time (P6-R2 b). Same glyph family as the partner-grain chips
    (lib.helpers.MOMENTUM_GLYPHS) for one visual language app-wide; text only --
    st.dataframe TextColumn carries no per-cell colour (same constraint the
    retired format_cagr() lived with).
    """
    if pd.isna(mom_class):
        return "—"
    mom_class = str(mom_class)
    if mom_class == "ns":
        return "non significatif"
    glyph = MOMENTUM_GLYPHS.get(mom_class)
    if glyph is None:
        return "—"
    if pd.isna(w1_share) or pd.isna(w2_share):
        return glyph
    try:
        delta_pp = (float(w2_share) - float(w1_share)) * 100
    except (ValueError, TypeError):
        return glyph
    sign = "+" if delta_pp >= 0 else "−"
    val = f"{abs(delta_pp):.2f}".replace(".", ",")
    return f"{glyph} {sign}{val}{FR_THIN_SPACE}pt"


def fr_fwci(val) -> str:
    """FR-formatted FWCI value (comma decimal, 2 places) -- D53: missing -> '—'."""
    if pd.isna(val):
        return "—"
    try:
        return f"{float(val):.2f}".replace(".", ",")
    except (ValueError, TypeError):
        return "—"


def fwci_hover_text(cat_label: str, n, p10, p25, p50, p75, p90, extreme: bool) -> str:
    """
    VIZ_SPEC_pass6 S4.2 -- the whole 5-row FR tooltip pre-built as ONE string
    (PF-2: go.Box ignores hovertemplate; the transparent hover-target bar reads
    this back via customdata, S0.1: no locale-blind format spec in the template).
    `p10`/`p90` are already the pair the caller means to show (p0/p100 when the
    "valeurs extrêmes" toggle is on) -- only the row LABEL changes with the toggle.
    """
    lo_label = "min–max" if extreme else "interdécile p10–p90"
    return (
        f"<b>{cat_label}</b><br>n = {fr_int(n)}<br>"
        f"médiane : {fr_fwci(p50)}<br>"
        f"Q1–Q3 : {fr_fwci(p25)} – {fr_fwci(p75)}<br>"
        f"{lo_label} : {fr_fwci(p10)} – {fr_fwci(p90)}"
    )

def parse_fwci_boxplot(blob):
    if pd.isna(blob) or not str(blob).strip():
        return None
    vals = parse_pipe_float_list(blob)
    if len(vals) < 7:
        return None
    return {"p0": vals[0], "p10": vals[1], "p25": vals[2], "p50": vals[3],
            "p75": vals[4], "p90": vals[5], "p100": vals[6]}

def to_pct(val):
    """
    Convert 0-1 float to rounded 0-100 float for ProgressColumn, or None.

    D53: a missing indicator returns None, which renders as an empty cell — never
    as 0, which would be a silent lie about a thin stratum.
    """
    if pd.isna(val):
        return None
    try:
        return round(float(val) * 100, 1)
    except (ValueError, TypeError):
        return None

def isite_col(row) -> dict:
    """
    « Contribution ISITE » dict entry -- present only while the global I-SITE overlay
    toggle is ON (pass-5 R1). Toggle OFF -> the level tables below read exactly as they
    did before the overlay concept existed (byte-identical column set); toggle ON ->
    the SAME precomputed pct_isite column (EXISTING same-row twin, docs/OVERLAY_MATRIX.md)
    appears, zero recomputation either way.
    """
    return {"Contribution ISITE": to_pct(row["pct_isite"])} if _ISITE_OVERLAY_ON else {}


def isite_col_keys(*keys: str) -> list[str]:
    """The percent-column key list for a table's column_config, with 'Contribution
    ISITE' included only while the overlay toggle is ON (see isite_col() above)."""
    return [k for k in keys if k != "Contribution ISITE" or _ISITE_OVERLAY_ON]


# G10 (NARRATIVE_CONTRACT_pass6 sec.2.5): libellés anglais -> FR. La colonne CAGR
# disparaît entièrement (P5/#18, momentum) -- plus d'entrée ici, jamais rendue.
_D53_HELP_FR = "Vide : indicateur non calculé (strate insuffisante), jamais zéro."
PERCENT_COL_CONFIG = {
    "% du total": st.column_config.ProgressColumn("% du total", min_value=0, max_value=100, format="%.1f%%"),
    "Contribution ISITE": st.column_config.ProgressColumn("Contribution ISITE", min_value=0, max_value=100, format="%.1f%%"),
    "% Top 10 %": st.column_config.ProgressColumn("% Top 10 %", min_value=0, max_value=100, format="%.1f%%", help=_D53_HELP_FR),
    "% Top 1 %": st.column_config.ProgressColumn("% Top 1 %", min_value=0, max_value=100, format="%.1f%%", help=_D53_HELP_FR),
    "% international": st.column_config.ProgressColumn("% international", min_value=0, max_value=100, format="%.1f%%"),
    "% avec une entreprise": st.column_config.ProgressColumn("% avec une entreprise", min_value=0, max_value=100, format="%.1f%%"),
    "% avec un ODD": st.column_config.ProgressColumn("% avec un ODD", min_value=0, max_value=100, format="%.1f%%"),
    "Momentum": st.column_config.TextColumn("Momentum", help=MOMENTUM_COL_HELP_FR),
}

# =============================================================================
# Section 1: Interactive Treemap
# =============================================================================
_ISITE_OVERLAY_ON = _controls_state[controls.ISITE_OVERLAY_KEY]

st.markdown("---")
st.markdown("## 📊 Carte du portefeuille de recherche")

st.markdown(
    "**Comment lire.** Chaque rectangle est un nœud de la taxonomie ; sa taille suit "
    "le volume de publications. Cliquer descend du domaine au champ puis au "
    "sous-champ, le fil d'Ariane remonte. Le sélecteur change ce que la couleur "
    "encode, jamais la taille."
)

# Prepare treemap data with additional count columns
# Filter to exclude topic level (keep only domain, field, subfield)
df_treemap = df_treemap_raw[df_treemap_raw["level"].isin(["domain", "field", "subfield"])].copy()

# The untopiced works have no field and no subfield, so the hierarchy carries them
# as three separate ROOT nodes (d_0, f_0, sf_0) holding the same 51 works. Keeping
# all three would triple-count them against every real domain. Show the domain node
# only.
df_treemap = df_treemap[~df_treemap["id"].isin(["f_0", "sf_0", "t_0"])]

# D53: a level with no computed work must not display a 0% top-10 share.
_no_indicator = df_treemap["fwci_median"].isna()
df_treemap.loc[_no_indicator, "pct_top10"] = np.nan

# Color metric selector. The "Contribution I-SITE" choice only appears once the
# I-SITE overlay toggle is ON (pass-5 R1): toggle OFF -> this selector is byte-identical
# to the pre-pass-5 3-option version, no I-SITE concept visible anywhere on the chart.
_color_options = ["fwci_median", "pct_top10", "pct_international"]
_color_labels = {
    "fwci_median": "FWCI médian (impact citationnel)",
    "pct_top10": "% de publications Top 10 %",
    "pct_international": "% de collaborations internationales",
}
if _ISITE_OVERLAY_ON:
    _color_options.append("pct_isite")
    _color_labels["pct_isite"] = "Contribution I-SITE (%)"

color_metric = st.selectbox(
    "Colorer par :",
    _color_options,
    format_func=lambda x: _color_labels.get(x, x),
)

# Build treemap with custom color scale for FWCI
if color_metric == "fwci_median":
    # Diverging scale: red (0, below the France reference) -> neutral grey (1, the
    # reference point itself) -> green (2+, above reference). The dataviz skill's own
    # rule for a diverging scale is explicit: "two hues + a NEUTRAL GRAY midpoint...
    # never a hue at the diverging midpoint" -- the previous #F4D570 yellow midpoint
    # (RA-B02, a past fix that only corrected the CODE COMMENT, not the colour itself)
    # violated that rule. Fixed here to controls.DEFERRED_GREY (#8C9196), the SAME
    # neutral-reference grey this app already uses everywhere else a "reference point"
    # needs marking (the France=1 dashed line on the T4 chart below, the floor-flagged
    # dot outline) -- reusing an existing token rather than inventing a new grey.
    # Validated: `node scripts/validate_palette.js "#EC8773,#8C9196,#60CCAA" --mode
    # light` (dataviz skill) -- the categorical checks it runs do not fit a 3-stop
    # DIVERGING scale exactly (its own printed scope note says so: "for a sequential
    # ramp, lightness monotonicity" is the closer check), but its chroma-floor check
    # on #8C9196 reports "reads gray" (chroma 0.009) -- exactly the property a neutral
    # midpoint needs. Red/green endpoints are the pre-existing, unchanged house colours.
    fig_treemap = px.treemap(
        df_treemap,
        ids="id",
        names="name",
        parents="parent_id",
        values="pubs",
        color="fwci_median",
        # Literal hex stops (not `controls.DEFERRED_GREY` the symbolic reference,
        # even though that constant IS this exact value): tests/ui/_colorscale.py's
        # read_declared_scale() parses this list by regex, matching ONLY quoted
        # "#RRGGBB" literals -- a bare identifier here would silently drop this stop
        # from that shared parser's read (2 stops instead of 3), not merely change
        # its colour. Value is controls.DEFERRED_GREY's, kept identical on purpose
        # (see the comment block above) -- provenance noted here in prose instead.
        color_continuous_scale=[
            [0.0, "#EC8773"],   # Rouge : FWCI = 0
            [0.5, "#8C9196"],   # Gris neutre (= controls.DEFERRED_GREY) : FWCI = 1 (référence France)
            [1.0, "#60CCAA"],   # Vert : FWCI = 2+
        ],
        range_color=[0, 2],
    )
elif color_metric == "pct_isite":
    # I-SITE overlay applied to the treemap: a sequential scale in the SAME darker
    # shade family lib.overlay.darken() uses for bar charts (one hue, light -> dark,
    # per the dataviz "sequential = magnitude" rule) -- the closest treemap-native
    # equivalent to "a darker shade of the same colour marks the I-SITE share" when a
    # single darker SEGMENT inside a treemap tile has no direct Plotly equivalent.
    fig_treemap = px.treemap(
        df_treemap,
        ids="id",
        names="name",
        parents="parent_id",
        values="pubs",
        color="pct_isite",
        color_continuous_scale=[[0.0, "#EAF3F1"], [1.0, darken("#60CCAA", 0.5)]],
    )
else:
    fig_treemap = px.treemap(
        df_treemap,
        ids="id",
        names="name",
        parents="parent_id",
        values="pubs",
        color=color_metric,
        color_continuous_scale="Blues",
    )

fig_treemap.update_traces(branchvalues="total")

# Hover template: the I-SITE line only appears once the overlay toggle is ON (R1 --
# toggle OFF must read exactly as it did before the overlay concept existed).
_hover_customdata = [
    df_treemap["pubs"],
    df_treemap["fwci_median"],
    df_treemap["pct_top10"] * 100,
    df_treemap["pct_international"] * 100,
]
_hover_template = (
    "<b>%{label}</b><br>Publications : %{customdata[0]:,}<br>"
    "FWCI médian : %{customdata[1]:.2f}<br>Top 10 %% : %{customdata[2]:.1f}%<br>"
    "International : %{customdata[3]:.1f}%<br>"
)
if _ISITE_OVERLAY_ON:
    _hover_customdata.append(df_treemap["pct_isite"] * 100)
    _hover_template += "dont I-SITE : %{customdata[4]:.1f}%<br>"
_hover_template += "<extra></extra>"

fig_treemap.update_traces(
    customdata=np.stack(_hover_customdata, axis=-1),
    hovertemplate=_hover_template,
)

fig_treemap.update_layout(
    margin=dict(t=30, l=10, r=10, b=10),
    height=600,
)

fig_treemap.update_traces(
    maxdepth=3,  # Show only 2 levels at a time (current + one level of children)
    tiling=dict(pad=0),
)

st.plotly_chart(fig_treemap, use_container_width=True)

# P6-R2 (a): a static caption never asserts a data value or a conclusion -- the
# emblematic violation this stream exists to fix (NARRATIVE_CONTRACT_pass6 sec.2.5,
# lines 398-403). Colour and size now read without an accompanying text conclusion.
st.caption(
    "**Pourquoi cet indicateur.** La carte répond à une question de forme : de quoi "
    "le portefeuille est-il fait, et dans quelles proportions. La couleur ajoute une "
    "seconde dimension au choix, de sorte que volume et position citationnelle se "
    "lisent ensemble : un domaine peut porter l'essentiel des publications sans "
    "porter la même part des travaux les plus cités, et l'inverse se rencontre tout "
    "autant."
)
exports.attach_download(st, df_treemap, "thematic-overview", "treemap-data", _EXPORT_STATE_PARITY)

# =============================================================================
# Section 2: Domains
# =============================================================================
st.markdown("---")
st.markdown("## 🌐 Domaines")
st.markdown(
    "**Pourquoi ces quatre niveaux.** La taxonomie OpenAlex descend du domaine au "
    "topic. Chaque publication porte un topic principal unique, donc chaque niveau "
    "se somme exactement au corpus, sans double compte. C'est ce qui permet de "
    "passer d'un niveau à l'autre sans changer de dénominateur."
)
st.markdown("""
Les domaines forment le niveau le plus agrégé de la taxonomie OpenAlex. L'ensemble de
la production se répartit sur quatre grands domaines : *Life Sciences*, *Social
Sciences*, *Physical Sciences* et *Health Sciences*. Une cinquième ligne grise, *Unclassified*,
regroupe les travaux qu'OpenAlex n'a rattachés à aucun topic.
""")
render_domain_legend(include_unclassified=True)

df_domains = df_overview[df_overview["level"] == "domain"].copy()
# `id` is a string here and the 5th entity is "0" (Unclassified) — int-castable on
# purpose, and ordered LAST by DOMAIN_ORDER_DISPLAY.
df_domains["domain_id"] = df_domains["id"].astype(int)
df_domains = df_domains.sort_values(
    "domain_id",
    key=lambda x: x.map({d: i for i, d in enumerate(DOMAIN_ORDER_DISPLAY)}),
)

st.markdown("### Aperçu par domaine")

# Build display table
domain_table = []
for _, row in df_domains.iterrows():
    dom_name = row["name"]
    domain_table.append({
        "Domaine": f"{get_domain_emoji(dom_name)} {dom_name}",
        "Pubs": int(row["pubs_total"]),
        "% du total": to_pct(row["pubs_pct_of_ul"]),
        **isite_col(row),
        "% Top 10 %": to_pct(row["pct_top10"]),
        "% Top 1 %": to_pct(row["pct_top1"]),
        "% international": to_pct(row["pct_international"]),
        "% avec une entreprise": to_pct(row["pct_company"]),
        "% avec un ODD": to_pct(row["pct_sdg"]),
        "Momentum": format_momentum(row.get("mom_class"), row.get("mom_w1_share"), row.get("mom_w2_share")),
    })

df_domain_display = pd.DataFrame(domain_table)
st.dataframe(
    df_domain_display,
    use_container_width=True,
    hide_index=True,
    column_config={k: PERCENT_COL_CONFIG[k] for k in isite_col_keys(
        "% du total", "Contribution ISITE", "% Top 10 %", "% Top 1 %",
        "% international", "% avec une entreprise", "% avec un ODD", "Momentum",
    )},
)
exports.attach_download(st, df_domain_display, "thematic-overview", "domains-table", _EXPORT_STATE_PARITY)
render_excluded_disclosure(*excluded_counts_from_facts(include_conference))

# FWCI Distribution boxplots -- VIZ_SPEC_pass6 S4: collapsible, CLOSED by default
# (#19); tooltip rebuilt per S4.2 (PF-2: go.Box ignores hovertemplate -- a
# transparent hover-target bar carries the FR tooltip instead).
boxplot_data = []
for _, row in df_domains.iterrows():
    bp = parse_fwci_boxplot(row["fwci_boxplot"])
    # A domain with no computed work has no distribution to draw (D53).
    if bp and pd.notna(row["fwci_median"]):
        dom_name = row["name"]
        boxplot_data.append({
            "domain": dom_name,
            "domain_id": row["domain_id"],
            "color": DOMAIN_COLORS.get(dom_name, "#7f7f7f"),
            "count": int(row["pubs_total"]),
            **bp
        })
boxplot_data = sorted(
    boxplot_data,
    key=lambda x: DOMAIN_ORDER_DISPLAY.index(x["domain_id"]) if x["domain_id"] in DOMAIN_ORDER_DISPLAY else 99,
)

with st.expander(
    f"Distribution du FWCI par domaine (réf. France) — {fr_int(len(boxplot_data))} domaines",
    expanded=False,
):
    st.markdown(
        "**Comment lire.** Chaque boîte résume la distribution du FWCI (réf. France, "
        "un travail comparé aux travaux français de même sous-champ, année et type) "
        "des travaux du domaine avec indicateur calculé : médiane, quartiles et, en "
        "option, les valeurs extrêmes."
    )
    use_extreme = st.toggle("Inclure les valeurs extrêmes (p0, p100)", value=False, key="domain_extreme")

    if boxplot_data:
        _y_max = max((it["p100"] if use_extreme else it["p90"]) for it in boxplot_data) * 1.15 or 1.0
        fig_box = go.Figure()
        for item in boxplot_data:
            lower, upper = (item["p0"], item["p100"]) if use_extreme else (item["p10"], item["p90"])
            tooltip = fwci_hover_text(
                item["domain"], item["count"], item["p10"], item["p25"], item["p50"],
                item["p75"], item["p90"], use_extreme,
            )
            fig_box.add_trace(go.Bar(
                x=[item["domain"]], y=[_y_max], width=0.72,
                marker_color="rgba(0,0,0,0)", showlegend=False,
                customdata=[tooltip], hovertemplate="%{customdata[0]}<extra></extra>",
            ))
            fig_box.add_trace(go.Box(
                x=[item["domain"]],
                lowerfence=[lower],
                q1=[item["p25"]],
                median=[item["p50"]],
                q3=[item["p75"]],
                upperfence=[upper],
                width=0.45,
                marker_color=item["color"],
                fillcolor=item["color"],
                line=dict(color=item["color"]),
                boxpoints=False,
                hoverinfo="skip",
                name=item["domain"],
                showlegend=False,
            ))
            fig_box.add_annotation(
                x=item["domain"],
                y=-0.15,
                yref="paper",
                text=f"n = {fr_int(item['count'])}",
                showarrow=False,
                font=dict(size=11, color="#666"),
            )

        fig_box.update_layout(
            height=350,
            margin=dict(t=30, l=50, r=30, b=60),
            yaxis=dict(title="FWCI", range=[0, _y_max]),
            xaxis_title="",
            barmode="overlay",
            bargap=0.1,
        )
        st.plotly_chart(fig_box, use_container_width=True)
        st.caption(
            "**Pourquoi cet indicateur.** La distribution complète, plutôt qu'une "
            "seule moyenne, montre si la position citationnelle est portée par "
            "l'ensemble des travaux du domaine ou par quelques publications isolées."
        )
        exports.attach_download(
            st, pd.DataFrame(boxplot_data)[["domain", "count", "p0", "p10", "p25", "p50", "p75", "p90", "p100"]],
            "thematic-overview", "fwci-domain-boxplot", _EXPORT_STATE_PARITY,
        )
    else:
        st.info("Aucune distribution de FWCI disponible à ce niveau.")

# =============================================================================
# Section 3: Fields
# =============================================================================
st.markdown("---")
st.markdown("## 📚 Champs")
df_fields = df_overview[df_overview["level"] == "field"].copy()
# Drop the Unclassified placeholder: it duplicates the domain-level row.
df_fields = df_fields[df_fields["id"] != "0"]
df_fields["field_id"] = df_fields["id"].astype(int)
df_fields["domain_id"] = pd.to_numeric(df_fields["parent_id"], errors="coerce").astype("Int64")
df_fields["domain_name"] = df_fields["domain_id"].map(domain_id2name)

# Sort by pubs descending for table
df_fields_table = df_fields.sort_values("pubs_total", ascending=False)

st.markdown(
    f"Les champs forment le deuxième niveau de la taxonomie OpenAlex, regroupant des "
    f"disciplines apparentées au sein de chaque domaine. Cette vue met en évidence les "
    f"forces disciplinaires de l'établissement et sa performance citationnelle sur les "
    f"{fr_int(len(df_fields_table))} champs que porte le corpus."
)
render_domain_legend()

st.markdown("### Aperçu par champ")
st.caption(
    f":grey[↗ à côté du nom d'un champ : rouvrir ce décompte dans OpenAlex "
    f"(décompte vivant, différent de l'instantané du {_SNAPSHOT_DATE}).]"
)

field_table = []
for _, row in df_fields_table.iterrows():
    dom_name = row["domain_name"] if pd.notna(row["domain_name"]) else "Other"
    _field_url = openalex_url(UL_OPENALEX_ID, scope="lineage", node=("field", int(row["field_id"])))
    field_table.append({
        "": get_domain_emoji(dom_name),
        "Champ": row["name"],
        "↗": _field_url,
        "Pubs": int(row["pubs_total"]),
        "% du total": to_pct(row["pubs_pct_of_ul"]),
        **isite_col(row),
        "% Top 10 %": to_pct(row["pct_top10"]),
        "% Top 1 %": to_pct(row["pct_top1"]),
        "% international": to_pct(row["pct_international"]),
        "% avec une entreprise": to_pct(row["pct_company"]),
        "% avec un ODD": to_pct(row["pct_sdg"]),
        "Momentum": format_momentum(row.get("mom_class"), row.get("mom_w1_share"), row.get("mom_w2_share")),
    })

df_field_display = pd.DataFrame(field_table)
st.dataframe(
    df_field_display,
    use_container_width=True,
    hide_index=True,
    height=500,
    column_config={
        "↗": st.column_config.LinkColumn("↗", display_text="↗", help="Rouvrir ce décompte dans OpenAlex"),
        **{k: PERCENT_COL_CONFIG[k] for k in isite_col_keys(
            "% du total", "Contribution ISITE", "% Top 10 %", "% Top 1 %",
            "% international", "% avec une entreprise", "% avec un ODD", "Momentum",
        )},
    },
)
exports.attach_download(st, df_field_display, "thematic-overview", "fields-table", _EXPORT_STATE_PARITY)

# =============================================================================
# FWCI Distribution by Field -- VIZ_SPEC_pass6 S4: collapsible, CLOSED by default
# (#19); same S4.2 tooltip fix as the domain panel above.
# =============================================================================
field_order = get_field_order_by_domain()
df_fields_sorted = df_fields.copy()
df_fields_sorted["sort_order"] = df_fields_sorted["field_id"].map({fid: i for i, fid in enumerate(field_order)})
df_fields_sorted = df_fields_sorted.sort_values("sort_order")

boxplot_data_fields = []
for _, row in df_fields_sorted.iterrows():
    bp = parse_fwci_boxplot(row["fwci_boxplot"])
    if bp and row["pubs_total"] > 0 and pd.notna(row["fwci_median"]):
        field_id = row["field_id"]
        dom_id = field_id2domain.get(field_id, 0)
        dom_name = domain_id2name.get(dom_id, "Other")
        boxplot_data_fields.append({
            "field": row["name"],
            "field_id": field_id,
            "color": DOMAIN_COLORS.get(dom_name, "#7f7f7f"),
            "count": int(row["pubs_total"]),
            **bp
        })

with st.expander(
    f"Distribution du FWCI par champ (réf. France) — {fr_int(len(boxplot_data_fields))} champs",
    expanded=False,
):
    st.markdown(
        "**Comment lire.** Chaque boîte résume la distribution du FWCI (réf. France) "
        "des travaux du champ avec indicateur calculé. Par défaut, les valeurs "
        "extrêmes sont masquées (percentiles 10-90) pour faciliter la comparaison "
        "entre champs ; l'option ci-dessous affiche l'étendue complète (minimum à "
        "maximum)."
    )
    use_extreme_fields = st.toggle("Inclure les valeurs extrêmes (p0, p100)", value=False, key="field_extreme")

    if boxplot_data_fields:
        _y_max_f = max((it["p100"] if use_extreme_fields else it["p90"]) for it in boxplot_data_fields) * 1.15 or 1.0
        fig_box_fields = go.Figure()
        for item in boxplot_data_fields:
            lower, upper = (item["p0"], item["p100"]) if use_extreme_fields else (item["p10"], item["p90"])
            tooltip = fwci_hover_text(
                item["field"], item["count"], item["p10"], item["p25"], item["p50"],
                item["p75"], item["p90"], use_extreme_fields,
            )
            fig_box_fields.add_trace(go.Bar(
                x=[item["field"]], y=[_y_max_f], width=0.72,
                marker_color="rgba(0,0,0,0)", showlegend=False,
                customdata=[tooltip], hovertemplate="%{customdata[0]}<extra></extra>",
            ))
            fig_box_fields.add_trace(go.Box(
                x=[item["field"]],
                lowerfence=[lower],
                q1=[item["p25"]],
                median=[item["p50"]],
                q3=[item["p75"]],
                upperfence=[upper],
                width=0.45,
                marker_color=item["color"],
                fillcolor=item["color"],
                line=dict(color=item["color"]),
                boxpoints=False,
                hoverinfo="skip",
                name=item["field"],
                showlegend=False,
            ))
            fig_box_fields.add_annotation(
                x=item["field"],
                y=-0.03,
                yref="paper",
                text=fr_int(item["count"]),
                showarrow=False,
                font=dict(size=9, color="#666"),
                textangle=0,
            )

        fig_box_fields.update_layout(
            height=500,
            margin=dict(t=30, l=50, r=30, b=160),
            yaxis=dict(title="FWCI", range=[0, _y_max_f]),
            xaxis_title="",
            xaxis_tickangle=-45,
            xaxis_tickfont=dict(size=10),
            barmode="overlay",
            bargap=0.1,
            hoverlabel=dict(bgcolor="white", font_size=12, font_family="Arial"),
        )
        st.plotly_chart(fig_box_fields, use_container_width=True)
        st.caption(
            "**Pourquoi cet indicateur.** La distribution complète, plutôt qu'une "
            "seule moyenne, montre si la position citationnelle est portée par "
            "l'ensemble des travaux du champ ou par quelques publications isolées."
        )
        exports.attach_download(
            st, pd.DataFrame(boxplot_data_fields)[["field", "count", "p0", "p10", "p25", "p50", "p75", "p90", "p100"]],
            "thematic-overview", "fwci-field-boxplot", _EXPORT_STATE_PARITY,
        )
    else:
        st.info("Aucune distribution de FWCI disponible à ce niveau.")

# =============================================================================
# Section 4: Subfields -- #20 full-vocab, zero-fill (subfields_zero_fill.parquet,
# 252 rows = the WHOLE OpenAlex subfield vocabulary, incl. the 6 the UL corpus
# never touches). Wired through the shared ranked_table (lazy afficher-plus,
# search box auto-shown at N >= 50 -- 252 >= 50, so it always shows here).
# =============================================================================
st.markdown("---")
st.markdown("## 📖 Sous-champs")
st.markdown(
    "Les sous-champs offrent un grain plus fin, décomposant chaque champ en domaines "
    "de recherche plus spécifiques. Le tableau porte tous les sous-champs du "
    "référentiel, y compris ceux que le corpus ne documente pas encore : filtrer par "
    "domaine ou rechercher un sous-champ les fait tous apparaître, à zéro "
    "publication comme à plusieurs centaines."
)
render_domain_legend()

df_subfields_zf = _load_table("subfields_zero_fill")
domain_filter = st.multiselect(
    "Filtrer par domaine :",
    options=DOMAIN_NAMES_ORDERED,
    default=[],
    key="subfield_domain_filter",
)
df_subfields_filtered = df_subfields_zf
if domain_filter:
    df_subfields_filtered = df_subfields_filtered[df_subfields_filtered["domain_name"].isin(domain_filter)]
df_subfields_filtered = df_subfields_filtered.sort_values("pubs_total", ascending=False)

subfield_table = []
for _, row in df_subfields_filtered.iterrows():
    dom_name = row["domain_name"] if pd.notna(row["domain_name"]) else "Other"
    subfield_table.append({
        "": get_domain_emoji(dom_name),
        "Sous-champ": row["subfield_name"],
        "Champ": row["field_name"] if pd.notna(row["field_name"]) else "",
        "Pubs": int(row["pubs_total"]),
        "% du total": to_pct(row["pubs_pct_of_ul"]),
        **isite_col(row),
        "% Top 10 %": to_pct(row["pct_top10"]),
        "% Top 1 %": to_pct(row["pct_top1"]),
        "% international": to_pct(row["pct_international"]),
        "% avec un ODD": to_pct(row["pct_sdg"]),
        "Momentum": format_momentum(row.get("mom_class"), row.get("mom_w1_share"), row.get("mom_w2_share")),
    })

df_subfield_display = pd.DataFrame(subfield_table)
if df_subfield_display.empty:
    st.info("Aucun sous-champ ne correspond à ces filtres.")
else:
    # S-LENS D6 fix (pass-6 fix round): same explicit one-bar/rest-number_cols split
    # as the Topics table above -- "% du total" is the bar, the rest are explicit
    # NumberColumns, never a second progress_cols entry relying on auto-demote.
    _sf_pct_cols = isite_col_keys(
        "% du total", "Contribution ISITE", "% Top 10 %", "% Top 1 %",
        "% international", "% avec un ODD",
    )
    _sf_visible = ranked_table(
        df_subfield_display,
        key="subfields_zero_fill",
        id_col="Sous-champ",
        search_cols=["Sous-champ", "Champ"],
        default_n=10,
        has_members=False,
        progress_cols={_sf_pct_cols[0]: {}},
        number_cols={k: ({"help": _D53_HELP_FR} if k in ("% Top 10 %", "% Top 1 %") else {}) for k in _sf_pct_cols[1:]},
        height=400,
    )
    exports.attach_download(st, _sf_visible, "thematic-overview", "subfields-table", _EXPORT_STATE_PARITY)
    st.caption(f":grey[{MOMENTUM_COL_HELP_FR}]")
if not include_conference:
    st.caption(
        ":grey[Ce tableau (comme celui des topics ci-dessous) reflète le corpus "
        "avec articles de conférence inclus, quel que soit ce filtre : la version "
        "pleine profondeur n'a pas de variante hors conférence.]"
    )

# =============================================================================
# Section 5: Topics (OpenAlex) -- #20 full-vocab, zero-fill (topics_zero_fill.
# parquet, 4 516 rows = the WHOLE OpenAlex topic vocabulary). No cap: a search
# such as "quantum" returns every matching topic, including the ones at zero UL
# publication (the exact case a corpus-derived table would silently drop).
# =============================================================================
st.markdown("---")
st.markdown("## 🏷️ Topics (OpenAlex)")
st.markdown(
    "Les topics forment le niveau le plus fin de la taxonomie OpenAlex, "
    "correspondant à des domaines de recherche précis au sein d'un sous-champ. "
    "Chaque publication reçoit un seul topic principal selon son contenu. Le "
    "tableau porte **tous** les topics du référentiel, y compris ceux que le "
    "corpus ne documente pas encore : une recherche par mot-clé les fait tous "
    "apparaître, à zéro publication comme à plusieurs centaines."
)
render_domain_legend()

df_topics_zf = _load_table("topics_zero_fill")
df_topics_zf = df_topics_zf.assign(
    artifact_flag=df_topics_zf["topic_id"].isin(_artifact_topic_ids())
)

domain_filter_topics = st.multiselect(
    "Filtrer par domaine :",
    options=DOMAIN_NAMES_ORDERED,
    default=[],
    key="topic_domain_filter",
)
df_topics_filtered = df_topics_zf
if domain_filter_topics:
    df_topics_filtered = df_topics_filtered[df_topics_filtered["domain_name"].isin(domain_filter_topics)]

# ARTIFACT-FLAG toggle ON: drop flagged topic ROWS (topic-grain semantics) -- a
# real filter on this list, distinct from the ships-v2 "nothing recomputes" strip
# above (no pubs_total/etc. value on the surviving rows is recomputed, only the
# row's presence changes).
_n_topics_before_artifact = len(df_topics_filtered)
if _ARTIFACT_ON:
    df_topics_filtered = df_topics_filtered[~df_topics_filtered["artifact_flag"]]
_n_topics_dropped_artifact = _n_topics_before_artifact - len(df_topics_filtered)

df_topics_filtered = df_topics_filtered.sort_values("pubs_total", ascending=False)

topic_table = []
for _, row in df_topics_filtered.iterrows():
    dom_name = row["domain_name"] if pd.notna(row["domain_name"]) else "Other"
    _topic_url = openalex_url(UL_OPENALEX_ID, scope="lineage", node=("topic", row["topic_id"]))
    topic_table.append({
        "": get_domain_emoji(dom_name),
        "Topic": row["topic_name"],
        "↗": _topic_url,
        "Réf.": controls.DAGGER if row["artifact_flag"] else "",
        "Sous-champ": row["subfield_name"] if pd.notna(row["subfield_name"]) else "",
        "Pubs": int(row["pubs_total"]),
        "% du total": to_pct(row["pubs_pct_of_ul"]),
        **isite_col(row),
        "% Top 10 %": to_pct(row["pct_top10"]),
        "% international": to_pct(row["pct_international"]),
        "% avec un ODD": to_pct(row["pct_sdg"]),
        "Momentum": format_momentum(row.get("mom_class"), row.get("mom_w1_share"), row.get("mom_w2_share")),
    })

df_topic_display = pd.DataFrame(topic_table)
if df_topic_display.empty:
    st.info("Aucun topic ne correspond à ces filtres.")
else:
    # S-LENS D6 fix (pass-6 fix round): "% du total" is the ONE bar (VIZ_SPEC_pass6
    # S7.2, first entry) -- every other percent column below is now an EXPLICIT
    # `number_cols` entry rather than a second `progress_cols` entry left to the
    # lib's auto-demote fallback (byte-identical render, no production warning).
    _topic_pct_cols = isite_col_keys(
        "% du total", "Contribution ISITE", "% Top 10 %", "% international", "% avec un ODD",
    )
    _topic_visible = ranked_table(
        df_topic_display,
        key="topics_zero_fill",
        id_col="Topic",
        search_cols=["Topic", "Sous-champ"],
        default_n=10,
        has_members=False,
        progress_cols={_topic_pct_cols[0]: {}},
        number_cols={k: ({"help": _D53_HELP_FR} if k == "% Top 10 %" else {}) for k in _topic_pct_cols[1:]},
        link_cols={"↗": {"help": "Rouvrir ce décompte dans OpenAlex", "display_text": "↗"}},
        height=400,
    )
    exports.attach_download(
        st, _topic_visible, "thematic-overview", "topics-table",
        exports.ExportState(
            snapshot=_SNAPSHOT_DATE, conf=include_conference, artifact=_ARTIFACT_ON,
            subset=_controls_state.get("perimeter_subset", "all"),
            artifact_applied=_ARTIFACT_ON,  # honest here: the row SET is genuinely filtered
        ),
    )
    st.caption(f":grey[{MOMENTUM_COL_HELP_FR}]")
if _ARTIFACT_ON and _n_topics_dropped_artifact:
    st.caption(
        f":grey[{fr_int(_n_topics_dropped_artifact)} topic(s) hors référentiel exclus de "
        "cette liste (filtre référentiel actif) — la valeur affichée sur les lignes "
        "restantes n'est pas recalculée, seule la présence de la ligne change.]"
    )

# =============================================================================
# Section 6: Sustainable Development Goals (D51)
# =============================================================================
# R12: presentational text -> FR. Official UN French SDG titles (a controlled,
# published vocabulary with a standard FR translation -- unlike the OpenAlex
# taxonomy names elsewhere on this page, which stay English per R12's own named
# exception because no such standard FR form exists for them).
SDG_NAMES = {
    1: "Pas de pauvreté",
    2: "Faim « zéro »",
    3: "Bonne santé et bien-être",
    4: "Éducation de qualité",
    5: "Égalité entre les sexes",
    6: "Eau propre et assainissement",
    7: "Énergie propre et d'un coût abordable",
    8: "Travail décent et croissance économique",
    9: "Industrie, innovation et infrastructure",
    10: "Inégalités réduites",
    11: "Villes et communautés durables",
    12: "Consommation et production responsables",
    13: "Mesures relatives à la lutte contre les changements climatiques",
    14: "Vie aquatique",
    15: "Vie terrestre",
    16: "Paix, justice et institutions efficaces",
    17: "Partenariats pour la réalisation des objectifs",
}

# One flat hue: this is one series (publications per goal), so identity is carried
# by the axis labels, not by colour. Sequential-by-value would encode rank twice.
SDG_BAR_COLOR = "#3E7CB1"


@st.cache_data
def sdg_assignments(variant_column: str, include_conference: bool) -> pd.DataFrame:
    """
    Explode the active variant column of sdg_three_way into (work_id, sdg) rows.
    A work absent from the file, or null in the active column, is UNTAGGED — it is
    not "0 SDGs".
    """
    sdg = load_sdg_three_way()[["work_id", variant_column]].dropna(subset=[variant_column])
    if not include_conference:
        pubs = get_pubs_slim()
        keep = set(pubs.loc[~pubs["is_conference"].fillna(False), "work_id"])
        sdg = sdg[sdg["work_id"].isin(keep)]
    # Multi-goal values are SPACE-separated in the deployed file ("5 8 10 16"),
    # not pipe-separated as the contract text says. Split on any non-digit so both
    # conventions decode - a wrong separator silently halves the coverage
    # (5,447 tagged works read as 3,906).
    sdg = sdg.assign(
        sdg=sdg[variant_column].astype(str).str.split(r"[^0-9]+")
    ).explode("sdg")
    sdg["sdg"] = pd.to_numeric(sdg["sdg"], errors="coerce")
    return sdg.dropna(subset=["sdg"]).astype({"sdg": int})[["work_id", "sdg"]]


if sdg_variant() != "off":
    st.markdown("---")
    st.markdown("## 🌱 Objectifs de développement durable")

    _column = sdg_column()
    df_sdg = sdg_assignments(_column, include_conference)

    corpus_total = int(df_overview.loc[df_overview["level"] == "domain", "pubs_total"].sum())
    tagged = df_sdg["work_id"].nunique()
    coverage = tagged / corpus_total if corpus_total else 0.0
    per_work = len(df_sdg) / tagged if tagged else 0.0

    st.markdown("### Empreinte du portefeuille sur les Objectifs de développement durable")
    st.markdown(
        f"""
**Comment lire.** Chaque barre compte les publications auxquelles la méthode
d'attribution associe cet objectif. Une publication peut en porter plusieurs : les
barres ne se somment donc pas au corpus. Attribution active : **{sdg_label()}**, sur
**{fr_int(tagged)}** publications du corpus, soit **{fr_pct(coverage*100)}**.

**Pourquoi cet indicateur.** La couverture est une propriété de la méthode de
classification, pas une mesure de la part de la recherche lorraine tournée vers les
grands défis : une publication non taguée est *inconnue*, jamais *hors sujet*. Ce
panneau sert donc à comparer des objectifs entre eux à l'intérieur du portefeuille,
jamais à établir un taux d'engagement.

*(La méthode d'attribution retenue, ses variantes et leurs écarts sont décrits dans
la section « Méthodes et guide de lecture ». Le changement de méthode est un réglage
de configuration, il ne demande aucune reconstruction.)*
"""
    )
    st.caption(
        ":grey[Un indice de spécialisation vs France (part ODD de l'UL rapportée à "
        "la part ODD de la France, méthode identique des deux côtés) répondrait à "
        "une question différente de la part ci-dessus : il n'existe pas dans les "
        "données disponibles (aucune référence France taguée avec la même "
        "méthode). Ce panneau reste donc une lecture de poids interne — jamais une "
        "comparaison externe.]"
    )

    if sdg_variant() == "b_siris":
        siris = load_sdg_siris()
        title_only = int((siris["text_basis"] == "title_only").sum())
        st.caption(
            f":grey[{fr_int(title_only)} attributions sur {fr_int(len(siris))} ont été "
            "faites sur le seul titre (résumé indisponible) — preuve plus faible que "
            "les attributions titre + résumé.]"
        )
    if _ISITE_OVERLAY_ON:
        st.caption(
            ":grey[Cette décomposition n'existe pas pour ce panneau : les données "
            "affichées ici ne portent pas la distinction I-SITE, l'attribution des "
            "ODD étant calculée sur le corpus entier. Le croisement laboratoire × "
            "ODD, plus bas, descend d'un grain.]"
        )

    counts = (
        df_sdg.groupby("sdg")["work_id"].nunique()
        .reindex(range(1, 18), fill_value=0)
    )
    counts = counts[counts > 0]

    if counts.empty:
        st.info("Aucune attribution ODD avec la méthode sélectionnée.")
    else:
        labels = [f"SDG {i} · {SDG_NAMES.get(i, '')}" for i in counts.index]
        fig_sdg = go.Figure(go.Bar(
            y=labels,
            x=counts.values,
            orientation="h",
            marker_color=SDG_BAR_COLOR,
            text=[f"{v:,}" for v in counts.values],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Publications : %{x:,}<extra></extra>",
        ))
        fig_sdg.update_layout(
            height=max(400, len(counts) * 28 + 120),
            margin=dict(t=20, l=10, r=60, b=40),
            xaxis=dict(title="Publications", showgrid=True, gridcolor="#e0e0e0"),
            yaxis=dict(autorange="reversed", title="", tickfont=dict(size=12)),
            template="plotly_white",
            showlegend=False,
            bargap=0.35,
        )
        st.plotly_chart(fig_sdg, use_container_width=True)

        df_sdg_table = pd.DataFrame({
            "Objectif": labels,
            "Publications": counts.values,
            "% des travaux tagués": (counts.values / tagged * 100).round(1),
            "% du corpus": (counts.values / corpus_total * 100).round(1),
        })
        st.dataframe(
            df_sdg_table,
            use_container_width=True,
            hide_index=True,
            column_config={
                # VIZ_SPEC_pass6 S7.2: one ProgressColumn per table. "% du corpus"
                # (poids interne, #10's own framing) carries the bar; the tagged-
                # share reading is demoted to a plain formatted number.
                "% du corpus": st.column_config.ProgressColumn(
                    "% du corpus", min_value=0, max_value=100, format="%.1f%%",
                    help="Part du corpus TOTAL portant cet objectif (poids interne)."),
                "% des travaux tagués": st.column_config.NumberColumn(
                    "% des travaux tagués", format="%.1f%%",
                    help="Part des travaux TAGUÉS (un travail peut porter plusieurs objectifs)."),
            },
        )
        exports.attach_download(st, df_sdg_table, "thematic-overview", "sdg-panel", _EXPORT_STATE_PARITY)

# =============================================================================
# NEW thematic panels (pass 5, P-B): specialisation (position) stays on THIS page
# (R9); the SDG family groups the shipped SDG panel above with two NEW panels below
# it (lab-grain crossing R16, peer context R6) so the whole "challenge-oriented"
# story reads together, then specialisation (T4) + its peer pointer (T4b), then the
# FR pointer to the new page 5 « Positionnement » for what moved off this page
# (T9 frontier cross + emerging topics, T3/T3c diversity, T3b co-discipline). This
# groups content by TOPIC rather than repeating R9's literal listing order --
# a deliberate, disclosed judgement call (progress/PB_portefeuille.md), not a
# silent reshuffle: every one of R9's three families (shape, specialisation, SDG)
# is still fully present on this page, nothing is lost.
#
# Domain colour note: VIZ_SPEC 1.1 computes a SEPARATE app-wide identity set
# (#0072B2/#009E73/#D55E00/#CC79A7) for new Studio work. This page already carries
# its own shipped domain palette (DOMAIN_COLORS, green/yellow/blue/red) across the
# treemap, tables and legends above. Shipping a SECOND, different domain palette in
# the panels below -- on the SAME page, same 4 domains -- would violate the spec's
# own cross-view rule #1 ("same read, same form... a reader learns each form once")
# more than it honours 1.1's letter. Deliberate call: the new panels reuse
# DOMAIN_COLORS/get_domain_color for domain identity, for continuity with the
# content already on this page. Flagged in progress/P3_thematic_ext.md.
# =============================================================================

# -----------------------------------------------------------------------------
# ODD par laboratoire (croisement labo x ODD) -- pass 6 #7 (part du corpus du
# labo étiquetée + effectif total) / #12 (colonnes méthode SIRIS vs Aurora).
# Source: sdg_lab_methods.parquet (lab x sdg x conf_state), which replaces
# thm_sdg_labs for THIS panel because it alone carries lab_total_pubs (the #7
# denominator) and the Aurora route side by side with SIRIS (the #12 ask).
# #8: the per-laboratory ODD PROFILE (one lab, all 16 goals) moves to the
# Laboratoires page mini-fiche -- this panel keeps only the per-ODD overview.
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("## 🏷️ ODD par laboratoire")

df_sdg_methods = _load_table("sdg_lab_methods")
_sdg_methods_state = df_sdg_methods[df_sdg_methods["conf_state"] == _CONF_STATE_VALUE].copy()
_n_labs_sdg = _sdg_methods_state["lab"].nunique()

st.markdown(
    f"Grain laboratoire ({fr_int(_n_labs_sdg)} structures, dont la catégorie « sans "
    "laboratoire »), deux méthodes de classification côte à côte : **SIRIS "
    "(VocTagger)**, la méthode contrôlée du panneau ODD principal ci-dessus, et "
    "**Aurora (OpenAlex)**, la méthode native du fournisseur. **Un croisement n'est "
    "pas une comparaison** : ce panneau ne porte aucun point de repère externe -- "
    "voir le panneau pairs ci-dessous pour une lecture comparative sur un terrain "
    "différent."
)

_sdg_pick_labs = st.selectbox(
    "Objectif de développement durable :",
    list(range(1, 17)),
    format_func=lambda i: f"ODD {i} · {SDG_NAMES.get(i, '')}",
    key="sdg_labs_pick",
)
_sdg_labs_rows = _sdg_methods_state[_sdg_methods_state["sdg"] == _sdg_pick_labs].copy()
_sdg_labs_rows = _sdg_labs_rows.sort_values("n_siris", ascending=False, na_position="last")
_sdg_labs_rows["Laboratoire"] = _sdg_labs_rows["lab"]
_sdg_labs_rows["Travaux ODD (SIRIS)"] = _sdg_labs_rows["n_siris"]
_sdg_labs_rows["Travaux ODD (Aurora)"] = _sdg_labs_rows["n_aurora"]
_sdg_labs_rows["Travaux du laboratoire"] = _sdg_labs_rows["lab_total_pubs"]
_sdg_labs_rows["Part du corpus du labo étiquetée (SIRIS)"] = (_sdg_labs_rows["share_lab_corpus_siris"] * 100).round(1)
_sdg_labs_rows["Part du corpus du labo étiquetée (Aurora)"] = (_sdg_labs_rows["share_lab_corpus_aurora"] * 100).round(1)

_sdg_labs_visible = ranked_table(
    _sdg_labs_rows[[
        "Laboratoire", "Travaux ODD (SIRIS)", "Travaux ODD (Aurora)", "Travaux du laboratoire",
        "Part du corpus du labo étiquetée (SIRIS)", "Part du corpus du labo étiquetée (Aurora)",
    ]],
    key="sdg_labs", id_col="Laboratoire", search_cols=["Laboratoire"], has_members=False,
    default_n=10,
    # VIZ_SPEC_pass6 S7.2 binding allocation for this table: the ONE bar is
    # "Part du corpus du labo étiquetée" (#7); "Travaux ODD" is demoted to a
    # plain number (build_column_order's own default NumberColumn covers it,
    # nothing to declare here). The Aurora share is an EXPLICIT NumberColumn
    # (#12), never a second progress_cols entry left to auto-demote (S-LENS D6).
    progress_cols={
        "Part du corpus du labo étiquetée (SIRIS)": {
            "help": "Part de l'EFFECTIF TOTAL du laboratoire (tagué ou non) portant cet ODD, méthode SIRIS.",
        },
    },
    number_cols={
        "Part du corpus du labo étiquetée (Aurora)": {"format": "%.1f%%"},
    },
)
st.caption(
    "**Comment lire.** Le dénominateur est l'effectif total du laboratoire (tous "
    "travaux, tagués ou non), pour les deux méthodes -- pas seulement sa part "
    "tagué ODD. Un même travail peut porter plusieurs ODD : les parts d'un "
    "laboratoire peuvent donc dépasser 100 % cumulées. Sous 30 travaux au total, la "
    "part n'est pas affichée (jamais 0 %). La catégorie « sans laboratoire » reste "
    "affichée : c'est une part réelle et mesurable du corpus."
)
st.caption(
    "➡ Le profil ODD détaillé d'un laboratoire (répartition par objectif) est "
    "présenté sur la page **🏭 Laboratoires**, dans sa fiche."
)
exports.attach_download(
    st, _sdg_labs_rows[[
        "lab", "n_siris", "n_aurora", "lab_total_pubs",
        "share_lab_corpus_siris", "share_lab_corpus_aurora",
    ]],
    "thematic-overview", f"sdg-{_sdg_pick_labs}-by-lab", _new_panel_state("all"),
)

# -----------------------------------------------------------------------------
# ODD, l'UL face à ses pairs (bench_sdg, méthode OpenAlex/Aurora)
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("## 🌍 ODD, l'UL face à ses pairs")
st.markdown(
    "**Comment le profil ODD de l'UL se situe-t-il face à ses pairs, sur un terrain "
    "où la méthode est rigoureusement identique des deux côtés ?** Méthode "
    "OpenAlex/Aurora des deux côtés (seuil 0,40) — jamais la méthode SIRIS/voctagger "
    "du panneau ODD principal ci-dessus."
)

df_bench_sdg = _load_table("bench_sdg")
_bsdg = df_bench_sdg[df_bench_sdg["conf_state"] == _CONF_STATE_VALUE].copy()
_n_peers_sdg = _bsdg.loc[_bsdg["rung"] != "FOCAL", "entity_id"].nunique()

st.error(
    "**Point de méthode ouvert (décision d'atelier).** Cette comparaison utilise la "
    "méthode native OpenAlex/Aurora sur les deux bords — pas la méthode SIRIS/"
    "voctagger (vocabulaire contrôlé) qui porte le panneau ODD principal de cette "
    "page. **Une comparaison pairs cohérente avec la méthode voctagger est une "
    "exigence importante, non résolue** : elle suppose de classifier les corpus des "
    f"{fr_int(_n_peers_sdg)} pairs avec le même vocabulaire contrôlé SIRIS — un "
    "chantier délibérément hors périmètre ici (décision d'atelier). Ne pas lire ce "
    "panneau comme équivalent au panneau ODD principal ci-dessus.",
    icon="🚩",
)

_ul_row_sdg = _bsdg[_bsdg["rung"] == "FOCAL"]
_ul_total_direct = int(_ul_row_sdg["entity_total_works"].iloc[0]) if not _ul_row_sdg.empty else None
_corpus_total_sdg = int(df_overview.loc[df_overview["level"] == "domain", "pubs_total"].sum())
st.caption(
    f":grey[Côté UL, le périmètre est l'identifiant OpenAlex **direct** de "
    f"l'établissement ({fr_int(_ul_total_direct)} travaux), et non le corpus par "
    f"filiation du reste de l'application ({fr_int(_corpus_total_sdg)} travaux) : "
    "c'est la seule perspective qui traite l'Université de Lorraine exactement "
    "comme chaque pair. Le filtre « hors référentiel » ne s'applique pas ici : les "
    "corpus des pairs sont tirés en direct d'OpenAlex, hors de l'instantané local "
    "qui porte la liste des topics exclus.]"
)

_FOCAL_BLUE_SDG = "#0072B2"
_sdg_label_order = [f"ODD {i} · {SDG_NAMES.get(i, '')}" for i in range(1, 18)]
_bsdg["sdg_label"] = _bsdg["sdg"].map(lambda i: f"ODD {int(i)} · {SDG_NAMES.get(int(i), '')}")
# Re-sliced AFTER sdg_label is added -- _ul_row_sdg above was captured for the caption
# only, before this column existed, and must not be reused for the chart traces.
_ul_row_sdg = _bsdg[_bsdg["rung"] == "FOCAL"]

fig_bsdg = go.Figure()
_peer_rows_sdg = _bsdg[_bsdg["rung"] != "FOCAL"]
fig_bsdg.add_trace(go.Scatter(
    x=_peer_rows_sdg["share_of_entity_works"] * 100, y=_peer_rows_sdg["sdg_label"], mode="markers",
    marker=dict(color=controls.DEFERRED_GREY, size=8, line=dict(width=0.5, color="white")),
    customdata=_peer_rows_sdg["entity_name"],
    hovertemplate="<b>%{customdata}</b><br>Part : %{x:.1f}%<extra></extra>",
    name=f"Pairs ({fr_int(_peer_rows_sdg['entity_id'].nunique())})",
))
fig_bsdg.add_trace(go.Scatter(
    x=_ul_row_sdg["share_of_entity_works"] * 100, y=_ul_row_sdg["sdg_label"], mode="markers",
    marker=dict(color=_FOCAL_BLUE_SDG, size=11, symbol="diamond", line=dict(width=0.5, color="white")),
    hovertemplate="<b>Université de Lorraine</b><br>Part : %{x:.1f}%<extra></extra>",
    name="Université de Lorraine",
))
fig_bsdg.update_layout(
    xaxis=dict(title="Part du total de l'entité (%)", showgrid=True, gridcolor="#e0e0e0"),
    yaxis=dict(title="", categoryorder="array", categoryarray=list(reversed(_sdg_label_order))),
    height=640, margin=dict(t=10, l=10, r=10, b=40), template="plotly_white",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
)
st.plotly_chart(fig_bsdg, use_container_width=True)
exports.attach_download(
    st, _bsdg[["entity_id", "entity_name", "rung", "sdg", "share_of_entity_works", "entity_total_works"]],
    "thematic-overview", "sdg-peers", _new_panel_state("all"),
)

# -----------------------------------------------------------------------------
# T4 -- Specialisation vs France (position)
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("## 🧭 Spécialisation par rapport à la France")

df_special = _load_table("thm_specialisation")

df_t4_field = df_special[
    (df_special["level"] == "field")
    & (df_special["conf_state"] == _CONF_STATE_VALUE)
    & (df_special["subset_id"] == "all")
].copy()
_lq_col = controls.xa(df_t4_field, "activity_index_lq")
_ulw_col = controls.xa(df_t4_field, "ul_works")
df_t4_field["field_id_int"] = df_t4_field["node_id"].astype(int)
df_t4_field["field_name"] = df_t4_field["field_id_int"].map(field_id2name)
df_t4_field["domain_name_t4"] = df_t4_field["field_id_int"].map(field_id2domain).map(domain_id2name)
df_t4_field = df_t4_field.dropna(subset=[_lq_col]).sort_values(_lq_col, ascending=True)

# I-SITE overlay (row-swap, per docs/OVERLAY_MATRIX.md): the Location Quotient is a
# ratio, non-additive -- there is no "I-SITE part of an LQ", only the SAME statistic
# recomputed on the in_isite sub-population, which is exactly the thm_specialisation
# "in_isite" row already carries. Rendered as a SECOND point per field (outline
# diamond), never a stacked segment -- toggle OFF -> byte-identical to before.
df_t4_isite = pd.DataFrame()
if _ISITE_OVERLAY_ON:
    df_t4_isite = df_special[
        (df_special["level"] == "field") & (df_special["conf_state"] == _CONF_STATE_VALUE)
        & (df_special["subset_id"] == "in_isite")
    ].copy()
    df_t4_isite["field_id_int"] = df_t4_isite["node_id"].astype(int)
    df_t4_isite["field_name"] = df_t4_isite["field_id_int"].map(field_id2name)
    df_t4_isite = df_t4_isite.dropna(subset=[_lq_col])

st.markdown("""
**Comment lire ce graphique** — chaque point est un champ. x = quotient de
localisation (LQ) vs la population française de référence (échelle log ; la ligne
pointillée à **France = 1** est le point neutre — à droite = sur-représenté à l'UL
par rapport à la France, à gauche = sous-représenté). Taille du point = publications
UL ; couleur = domaine. Les points en creux sont sous le seuil de fiabilité
(< 30 travaux UL dans le champ).
""")
_t4_axis_type = log_linear_toggle("t4_field_axis")

if df_t4_field.empty:
    st.info("Aucune ligne de spécialisation pour cet état de conférence.")
else:
    _t4_normal = df_t4_field[~df_t4_field["floor_flag"]]
    _t4_floor = df_t4_field[df_t4_field["floor_flag"]]
    fig_t4 = go.Figure()
    if not _t4_normal.empty:
        fig_t4.add_trace(go.Scatter(
            x=_t4_normal[_lq_col], y=_t4_normal["field_name"], mode="markers",
            marker=dict(
                size=(_t4_normal[_ulw_col].astype(float).clip(lower=1) ** 0.5) * 1.6,
                color=[DOMAIN_COLORS.get(d, "#7f7f7f") for d in _t4_normal["domain_name_t4"]],
                line=dict(width=0.5, color="white"),
            ),
            customdata=np.stack([_t4_normal[_ulw_col].astype(float), _t4_normal["france_works"].astype(float)], axis=-1),
            hovertemplate="<b>%{y}</b><br>LQ : %{x:.2f}<br>Travaux UL : %{customdata[0]:,.0f}<br>Travaux France : %{customdata[1]:,.0f}<extra></extra>",
            showlegend=False, name="",
        ))
    if not _t4_floor.empty:
        fig_t4.add_trace(go.Scatter(
            x=_t4_floor[_lq_col], y=_t4_floor["field_name"], mode="markers",
            marker=dict(
                size=(_t4_floor[_ulw_col].astype(float).clip(lower=1) ** 0.5) * 1.6,
                # "Thin strata -> hollow grey" (VIZ_SPEC 2.8 T4 row): hollow fill AND
                # grey outline, not domain-coloured -- distinct from the reliable dots.
                color="rgba(255,255,255,0)",
                line=dict(width=2, color=controls.DEFERRED_GREY),
            ),
            customdata=np.stack([_t4_floor[_ulw_col].astype(float), _t4_floor["france_works"].astype(float)], axis=-1),
            hovertemplate="<b>%{y}</b> (n<30)<br>LQ : %{x:.2f}<br>Travaux UL : %{customdata[0]:,.0f}<br>Travaux France : %{customdata[1]:,.0f}<extra></extra>",
            showlegend=False, name="",
        ))
    if not df_t4_isite.empty:
        fig_t4.add_trace(go.Scatter(
            x=df_t4_isite[_lq_col], y=df_t4_isite["field_name"], mode="markers",
            marker=dict(
                size=9, symbol="diamond-open",
                line=dict(width=2, color=darken("#60CCAA", 0.55)),
            ),
            hovertemplate="<b>%{y}</b> — I-SITE seul<br>LQ (I-SITE) : %{x:.2f}<extra></extra>",
            showlegend=True, name="dont I-SITE (LQ recalculé sur le sous-corpus)",
        ))
    fig_t4.add_vline(x=1.0, line_dash="dash", line_color="#8C9196",
                      annotation_text="France = 1", annotation_position="top")
    fig_t4.update_layout(
        xaxis=dict(type=_t4_axis_type, title=f"LQ vs France ({'linéaire' if _t4_axis_type == 'linear' else 'log'})"),
        yaxis=dict(title=""),
        height=max(420, len(df_t4_field) * 26 + 100),
        margin=dict(t=30, l=10, r=10, b=40),
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0) if not df_t4_isite.empty else None,
    )
    st.plotly_chart(fig_t4, use_container_width=True)
    if not df_t4_isite.empty:
        st.caption(
            ":grey[Losange évidé : quotient de localisation recalculé sur le seul "
            "sous-corpus I-SITE. C'est une seconde série, jamais une part de la "
            "même barre : un quotient est un rapport, pas une grandeur qui "
            "s'additionne.]"
        )

    # Scoped-descent drill (VIZ_SPEC 1.4/plan §6.6): field -> its subfields only,
    # never a flat multi-hundred list. A selectbox stands in for "field click" here
    # (no click-event library is on the pinned stack, D63) -- same scoped-children
    # outcome, lower engineering risk.
    _t4_field_options = ["— (vue par champ)"] + df_t4_field.sort_values("field_name")["field_name"].tolist()
    _t4_pick = st.selectbox("Zoomer sur un champ (ses sous-champs) :", _t4_field_options, key="t4_field_drill")
    if _t4_pick != _t4_field_options[0]:
        _t4_picked_id = int(df_t4_field.loc[df_t4_field["field_name"] == _t4_pick, "field_id_int"].iloc[0])
        df_t4_sub = df_special[
            (df_special["level"] == "subfield")
            & (df_special["conf_state"] == _CONF_STATE_VALUE)
            & (df_special["subset_id"] == "all")
        ].copy()
        df_t4_sub["subfield_id_int"] = df_t4_sub["node_id"].astype(int)
        df_t4_sub["parent_field_id"] = df_t4_sub["subfield_id_int"].map(subfield_id2field)
        df_t4_sub = df_t4_sub[df_t4_sub["parent_field_id"] == _t4_picked_id]
        df_t4_sub["subfield_name"] = df_t4_sub["subfield_id_int"].map(subfield_id2name)
        _lq_col_sub = controls.xa(df_t4_sub, "activity_index_lq")
        _ulw_col_sub = controls.xa(df_t4_sub, "ul_works")
        df_t4_sub = df_t4_sub.dropna(subset=[_lq_col_sub]).sort_values(_lq_col_sub, ascending=True)
        if df_t4_sub.empty:
            st.info(f"Aucun sous-champ sous {_t4_pick} pour cet état de conférence.")
        else:
            n_thin = int(df_t4_sub["floor_flag"].sum())
            _t4_sub_axis_type = log_linear_toggle("t4_subfield_axis")
            fig_t4_sub = go.Figure(go.Scatter(
                x=df_t4_sub[_lq_col_sub], y=df_t4_sub["subfield_name"], mode="markers",
                marker=dict(
                    size=(df_t4_sub[_ulw_col_sub].astype(float).clip(lower=1) ** 0.5) * 1.6,
                    # Same "hollow grey" floor convention as the field-level chart above.
                    color=np.where(df_t4_sub["floor_flag"], "rgba(255,255,255,0)", "#0072B2"),
                    line=dict(width=np.where(df_t4_sub["floor_flag"], 2, 0.5),
                              color=np.where(df_t4_sub["floor_flag"], controls.DEFERRED_GREY, "#0072B2")),
                ),
                hovertemplate="<b>%{y}</b><br>LQ : %{x:.2f}<extra></extra>",
            ))
            fig_t4_sub.add_vline(x=1.0, line_dash="dash", line_color="#8C9196")
            fig_t4_sub.update_layout(
                xaxis=dict(type=_t4_sub_axis_type, title=f"LQ vs France ({'linéaire' if _t4_sub_axis_type == 'linear' else 'log'})"),
                yaxis=dict(title=""),
                height=max(320, len(df_t4_sub) * 24 + 80), margin=dict(t=20, l=10, r=10, b=30),
                template="plotly_white",
            )
            st.plotly_chart(fig_t4_sub, use_container_width=True)
            if n_thin:
                st.caption(f":grey[{n_thin} sous-champ(s) sous le seuil (n<30) -- affichés en creux.]")

    exports.attach_download(
        st, df_t4_field[["field_name", "domain_name_t4", _lq_col, _ulw_col, "france_works", "floor_flag"]],
        "thematic-overview", "specialisation-field", _new_panel_state("all"),
    )

st.caption(
    "**Pourquoi cet indicateur.** Le quotient de localisation compare la "
    "composition du portefeuille lorrain à celle de la production française : il "
    "répond à « sur quoi ce site pèse-t-il plus que la moyenne nationale », pas à "
    "« où est-il bon ». Un champ sur-représenté et peu cité, ou l'inverse, sont deux "
    "situations lisibles, et ce sont deux conversations différentes."
)

st.info(
    "**Le jeu de pairs est arrêté en atelier et modifiable par l'établissement.** "
    "La comparaison par champ vis-à-vis de ces pairs vit sur la page "
    "**🧭 Benchmark** (barre latérale).",
    icon="🧩",
)

st.markdown("---")
st.markdown(
    "**➡ Le positionnement frontière, la diversité disciplinaire et les "
    "croisements entre champs** sont traités sur la page **📍 Positionnement**. "
    "Cette page reste centrée sur la forme du portefeuille, la spécialisation et "
    "l'empreinte ODD."
)

# =============================================================================
# Footer
# =============================================================================
st.markdown("---")
st.caption(f"Données : publications de l'Université de Lorraine {window_label()} | Taxonomie OpenAlex")
