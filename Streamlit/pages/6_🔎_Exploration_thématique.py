"""
Exploration thématique — descente scopée (domaine → champ → sous-champ → topic) sur
un élément de la taxonomie OpenAlex : volume, impact, collaborations, contributeurs,
partenaires et auteurs pour CET élément précis.

Le quatrième niveau du sélecteur est le `topic` OpenAlex (3 275 au total) ; il
remplace l'axe topic-model de v1, retiré par D9. Mécanique de descente scopée =
implémentation de référence (pass-5 mission) — formulaire/sélecteurs non restructurés
cette passe ; seul le wrapper FR, la surcouche I-SITE (grammaire lib.overlay) et le
contrat DEPTH & QUERY (lib.ranked, profondeur SHALLOW à ce grain de taxon) changent.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from lib.helpers import (
    NA_MARK,
    get_domain_id_to_name,
    get_field_id_to_name,
    get_field_id_to_domain_id,
    get_subfield_id_to_name,
    get_subfield_id_to_domain_id,
    safe_float,
    safe_int,
    na_metric,
    conference_blob_caveat,
    render_excluded_disclosure,
    window_label,
    MOMENTUM_GLYPHS,
)

from lib.data_cache import (
    load_thematic_contributions,
    load_thematic_partners,
    load_thematic_authors,
    DATA_DIR,
    get_corpus_facts_df,
)
from lib.thematic import excluded_counts_from_facts, get_overview, get_sublevels
from lib import controls, exports
from lib.ranked import (
    ranked_table, fr_int, fr_pct, mask_members, CONSORTIUM_IDS, HIDE_MEMBERS_LABEL, link_column,
)

# Pass 7a (P-EX, BUILD_PLAN P3/P4/P5) -- partner sections only: reading line, hover
# grammar, OpenAlex deep links and the site_reciprocity_scatter chart grammar.
from lib import copy_fr
from lib import fig_cache
from lib import hover as hv
from lib import links
from lib import reading
from lib.charts import site_reciprocity_scatter

# Pass 7b (P6, BUILD_PLAN B2/B6, non-partner sections): bars_with_gutter + colour
# tokens for the time-series and structure charts.
from lib import charts
from lib import helpers as H

# =============================================================================
# Page config
# =============================================================================
st.set_page_config(
    page_title="Exploration thématique | Université de Lorraine",
    page_icon="🔎",
    layout="wide",
)

st.title("🔎 Exploration thématique")
st.markdown(
    "**Pour un domaine, un champ, un sous-champ ou un topic donné : quel volume, "
    "quel impact citationnel, quelles collaborations et quels contributeurs ?** "
    "Descendre dans la taxonomie OpenAlex jusqu'au grain souhaité, puis lire le "
    "détail (contributeurs, partenaires, auteurs) de cet élément précis."
)

# W5 chassis adoption (VIZ_SPEC 1.5 / 2.9 inheritance, chain pass 3 P3) -- same pattern as
# P5 on page 1 / P3 on page 3: controls.sidebar() is a drop-in superset of the D52 toggle
# this page already rendered (same lib.helpers.conference_toggle(), same
# "include_conference" session-state key), wrapped with the perimeter selector, the
# artifact toggle and the snapshot badge.
_controls_state = controls.sidebar()
include_conference = _controls_state["include_conference"]
_ARTIFACT_ON = _controls_state[controls.ARTIFACT_TOGGLE_KEY]
_ISITE_OVERLAY_ON = _controls_state[controls.ISITE_OVERLAY_KEY]

controls.filtered_by_strip(page="exploration_thematique")
controls.ships_v2_strip()  # ships-v2 honest strip -- this page is parity + inheritance only
if _controls_state.get("perimeter_subset", "all") != "all":
    controls.perimeter_disclosure_strip()  # R-B: this page carries no subset rows of its own

_facts = get_corpus_facts_df()
_SNAPSHOT_DATE = str(_facts["snapshot_date"].iloc[0]) if len(_facts) else "?"
_EXPORT_STATE = exports.ExportState(
    snapshot=_SNAPSHOT_DATE,
    conf=include_conference,
    artifact=_ARTIFACT_ON,
    subset=_controls_state.get("perimeter_subset", "all"),
    artifact_applied=False,  # ships-v2: nothing on this page recomputes under the toggle,
                              # except the topic-grain row DROP handled locally, below
)

NODE_LEVEL_PREFIX = {"domain": "d", "field": "f", "subfield": "sf", "topic": "t"}


def _link_node(level, element_id):
    """
    `lib.links._NODE_FILTER_KEY` only expresses field/subfield/topic (OpenAlex has
    no `primary_topic.domain.id` filter) -- a domain-level view omits the node
    filter rather than guessing one or skipping the link entirely: `copubs_url`
    still returns a correct, live UL x partner link, just not node-scoped.
    """
    if level in ("field", "subfield", "topic"):
        return (level, element_id)
    return None


def _fwci_pair_or_na(fwci, n):
    """
    `hv.fmt_fwci_pair` reused with the SAME scalar as median and mean: the
    partner-node blobs (top_int_partners / top_fr_partners / reciprocity_partners)
    carry exactly ONE fwci value per row, never a separate mean or sample size --
    fabricating either would be a fabricated denominator (house rule). `n` (the
    co-publication count, already on every row) stands in for the sample size,
    same substitution S-LIB-A's tests/_registry.py::frame_country_companion uses
    for the analogous single-scalar case. NA_MARK, never a bare dash, below the
    three-work floor (VIZ_SPEC_pass7 SS5.15: "NA_MARK for a missing indicator").
    """
    return hv.fmt_fwci_pair(fwci, fwci, n, floor_draw=3, floor_dagger=10) or NA_MARK


@st.cache_data
def _artifact_topic_ids() -> frozenset:
    """The 811 flagged topic_ids (dim_artifact_topics), for the † marker + row drop."""
    return frozenset(pd.read_parquet(DATA_DIR / "dim_artifact_topics.parquet")["topic_id"])


# =============================================================================
# Constants
# =============================================================================
LEVEL_LABELS = {
    "domain": "domaine",
    "field": "champ",
    "subfield": "sous-champ",
    "topic": "topic",
}

CHILD_LEVEL_LABELS = {
    "domain": "Field",
    "field": "Subfield",
    "subfield": "Topic",
}

# =============================================================================
# Load data
# =============================================================================
df_overview = get_overview(include_conference)
df_sublevels = get_sublevels(include_conference)
df_contributions = load_thematic_contributions()
df_partners = load_thematic_partners()
df_authors = load_thematic_authors()

# Lookups
domain_id2name = get_domain_id_to_name()
field_id2name = get_field_id_to_name()
field_id2domain = get_field_id_to_domain_id()
subfield_id2name = get_subfield_id_to_name()
subfield_id2domain = get_subfield_id_to_domain_id()

# =============================================================================
# Helper functions
# =============================================================================
def format_pct(val):
    if pd.isna(val):
        return "—"
    return f"{val*100:.1f}%"

def format_indicator_pct(val):
    """D53: a citation indicator with no computed stratum reads 'n/a', never 0."""
    if pd.isna(val):
        return NA_MARK
    return f"{val*100:.1f}%"

def format_momentum(row) -> str:
    """
    P5: momentum replaces CAGR everywhere. `row` (a pandas Series or dict-like)
    carries the frozen mom_class/mom_w1_share/mom_w2_share/mom_eligible_flag
    triple S-DAT built at THIS table's thematic grain -- the same up/down/
    stable/ns classification lib46 already computes for partners, without the
    corpus-drift recentring step: a topic's or field's share of the corpus is
    already a share of the SAME total, so no separate facts table is needed
    (unlike lib.helpers.momentum_display(), built for the partner grain's
    mom_category/mom_count_arrow/recentring_median shape, which this table
    does not carry -- see progress/PEX.md for the schema note).

    `.get()` (safe on a missing key/column, unlike `row["..."]`) also covers
    the conference-toggle-OFF path: `lib.thematic._recompute_overview/
    _recompute_sublevels` never add these columns at all (frozen family, not
    recomputed under a filter, same convention as every other 'disclosed, not
    recomputed' surface on this page) -- momentum then reads "—", honestly.
    """
    cat = row.get("mom_class") if hasattr(row, "get") else None
    eligible = row.get("mom_eligible_flag") if hasattr(row, "get") else None
    try:
        cat_is_null = cat is None or pd.isna(cat)
    except (TypeError, ValueError):
        cat_is_null = cat is None
    if cat_is_null or eligible is not True:
        return "—"
    cat = str(cat)
    if cat == "ns":
        return "non significatif"
    if cat not in MOMENTUM_GLYPHS:
        return "—"
    glyph = MOMENTUM_GLYPHS[cat]
    w1, w2 = row.get("mom_w1_share"), row.get("mom_w2_share")
    try:
        if w1 is None or w2 is None or pd.isna(w1) or pd.isna(w2):
            return glyph
        # Reconciliation pass 6: ecart en POINTS de pourcentage (w2 - w1), la
        # meme quantification que la page 4 (#18 "difference entre periode") --
        # jamais le ratio relatif, qui donnait un autre nombre pour le meme taxon.
        delta_pp = (float(w2) - float(w1)) * 100
    except (TypeError, ValueError):
        return glyph
    sign = "+" if delta_pp >= 0 else "−"
    val = f"{abs(delta_pp):.2f}".replace(".", ",")
    return f"{glyph} {sign}{val} pt"

def parse_year_counts(blob):
    """Parse '2019:120|2020:135|...' into dict {year: count}."""
    if pd.isna(blob) or not str(blob).strip():
        return {}
    result = {}
    for part in str(blob).split("|"):
        if ":" in part:
            k, v = part.split(":", 1)
            try:
                result[int(k)] = int(v)
            except ValueError:
                pass
    return result

def parse_top_items(blob, expected_fields):
    """
    Parse pipe-separated items with colon-separated fields.

    Requires len(parts) >= len(expected_fields) and silently drops shorter items,
    so every field value must be sanitised of ':' and '|' by the builder
    (data_contract.yaml invariant `blob_separator_safety`).
    """
    if pd.isna(blob) or not str(blob).strip():
        return []
    results = []
    for item in str(blob).split("|"):
        parts = item.split(":")
        if len(parts) >= len(expected_fields):
            row = {field: parts[i] for i, field in enumerate(expected_fields)}
            results.append(row)
    return results

def get_element_options(level):
    """Get available elements for a given level."""
    df_level = df_overview[df_overview["level"] == level].copy()
    df_level = df_level.sort_values("pubs_total", ascending=False)
    options = []
    for _, row in df_level.iterrows():
        label = f"{row['name']} ({int(row['pubs_total']):,} pubs)"
        options.append((row["id"], label))
    return options

def get_element_data(level, element_id):
    """Get overview data for a specific element."""
    mask = (df_overview["level"] == level) & (df_overview["id"] == str(element_id))
    rows = df_overview[mask]
    if rows.empty:
        return None
    return rows.iloc[0]

def get_sublevel_data(parent_level, parent_id):
    """Get sublevel breakdown data."""
    mask = (df_sublevels["parent_level"] == parent_level) & (df_sublevels["parent_id"] == str(parent_id))
    return df_sublevels[mask].copy()

def get_contribution_data(level, element_id):
    """Get contribution data (poles, labs)."""
    mask = (df_contributions["level"] == level) & (df_contributions["id"] == str(element_id))
    rows = df_contributions[mask]
    if rows.empty:
        return None
    return rows.iloc[0]

def find_column(row_or_df, pattern):
    """
    Find a column whose name CONTAINS `pattern`.

    v1 encoded the blob format in the column name ("top_labs 'ror:name:...'");
    v2 uses clean names and this still matches, so no page change was needed.
    A DataFrame also has `.index`, so test for it explicitly — otherwise the
    positional index (ints) is searched and `pattern in col` raises.
    """
    cols = row_or_df.columns if isinstance(row_or_df, pd.DataFrame) else row_or_df.index

    for col in cols:
        if pattern in col:
            return col
    return None

def get_partner_data(level, element_id):
    """Get partner data."""
    mask = (df_partners["level"] == level) & (df_partners["id"] == str(element_id))
    rows = df_partners[mask]
    if rows.empty:
        return None
    return rows.iloc[0]

def get_author_data(level, element_id):
    """Get author data."""
    mask = (df_authors["level"] == level) & (df_authors["id"] == str(element_id))
    rows = df_authors[mask]
    if rows.empty:
        return None
    return rows.iloc[0]

# =============================================================================
# Section 1: Selector
# =============================================================================
st.markdown("---")
st.caption(
    ":grey[**Comment lire.** Choisir un niveau puis un élément descend l'analyse "
    "sur ce seul nœud de la taxonomie : tous les panneaux qui suivent portent "
    "alors sur lui, jamais sur le corpus entier.]"
)

col1, col2 = st.columns(2)

with col1:
    level = st.selectbox(
        "Choisir le niveau :",
        ["domain", "field", "subfield", "topic"],
        format_func=lambda x: {
            "domain": "🌐 Domaine",
            "field": "📚 Champ",
            "subfield": "📖 Sous-champ",
            "topic": "🏷️ Topic",
        }.get(x, x)
    )

with col2:
    element_options = get_element_options(level)
    if element_options:
        # subfield and topic levels have hundreds/thousands of options: search first
        if level in ("subfield", "topic"):
            _level_label_fr = {"subfield": "un sous-champ", "topic": "un topic"}[level]
            search_term = st.text_input(
                f"Rechercher {_level_label_fr} :", "", key=f"{level}_search_drilldown")
            if search_term:
                element_options = [
                    (eid, label) for eid, label in element_options
                    if search_term.lower() in label.lower()
                ]
            if not element_options:
                st.warning("Aucun résultat pour cette recherche.")
                st.stop()

        element_id = st.selectbox(
            "Choisir l'élément :",
            options=[opt[0] for opt in element_options],
            format_func=lambda x: dict(element_options).get(x, x)
        )
    else:
        st.warning("Aucun élément trouvé pour ce niveau.")
        st.stop()

# Get element data
element_data = get_element_data(level, element_id)
if element_data is None:
    st.error("Données introuvables pour cet élément.")
    st.stop()

element_name = element_data['name']
level_label = LEVEL_LABELS.get(level, level.title())

# Display element name as header
st.markdown(f"## {element_name}")

# Show hierarchy
if level == "field":
    parent_domain = element_data.get('parent_name', '')
    if parent_domain:
        st.markdown(f"**Domaine :** {parent_domain}")

elif level in ("subfield", "topic"):
    parent_id = element_data.get('parent_id')
    parent_name = element_data.get('parent_name', '')
    parent_label = "Champ" if level == "subfield" else "Sous-champ"
    if parent_id:
        try:
            if level == "subfield":
                domain_id = field_id2domain.get(int(parent_id))
            else:
                domain_id = subfield_id2domain.get(int(parent_id))
            domain_name = domain_id2name.get(domain_id, '')
            if parent_name and domain_name:
                st.markdown(f"**{parent_label} :** {parent_name} · **Domaine :** {domain_name}")
            elif parent_name:
                st.markdown(f"**{parent_label} :** {parent_name}")
        except (ValueError, TypeError):
            if parent_name:
                st.markdown(f"**{parent_label} :** {parent_name}")

if str(element_id) == "0":
    st.info(
        f"Ces publications ne portent aucun topic OpenAlex "
        f"({fr_int(element_data['pubs_total'])} travaux, "
        f"{fr_pct(element_data['pubs_pct_of_ul'] * 100)} du corpus). Elles "
        "restent visibles, sous une entité « sans thématique », plutôt que "
        "d'être escamotées des vues thématiques.",
        icon="ℹ️",
    )

# =============================================================================
# Section 2: Topline KPIs
# =============================================================================
st.markdown("---")

st.markdown("#### 📊 Volume et croissance")
kpi_cols1 = st.columns(4)
with kpi_cols1[0]:
    st.metric("Publications", fr_int(element_data['pubs_total']))
with kpi_cols1[1]:
    st.metric("% du total UL", format_pct(element_data['pubs_pct_of_ul']))
with kpi_cols1[2]:
    st.metric(
        "Momentum", format_momentum(element_data),
        help=(
            "Comparaison de deux fenêtres temporelles consécutives de la part "
            "de cet élément dans le corpus de l'Université de Lorraine. Un "
            "écart n'est affiché comme hausse ou repli que lorsqu'il est "
            "statistiquement significatif ; sinon « non significatif ». "
            "Famille de mesure figée : elle n'est pas recalculée sous le "
            "filtre référentiel ni sous la bascule des actes de conférence."
        ),
    )

st.markdown("#### 🎯 Impact citationnel")
st.caption(":grey[FWCI — chaque travail est comparé aux travaux français de même sous-domaine, année et type (réf. France). Médiane d'abord, moyenne en complément.]")
kpi_cols2 = st.columns(4)
with kpi_cols2[0]:
    st.metric("FWCI médian (réf. France)", na_metric(element_data['fwci_median']))
with kpi_cols2[1]:
    st.metric("FWCI moyen (réf. France)", na_metric(element_data['fwci_mean']))
with kpi_cols2[2]:
    st.metric("% Top 10 %", format_indicator_pct(element_data['pct_top10']))
with kpi_cols2[3]:
    st.metric("% Top 1 %", format_indicator_pct(element_data['pct_top1']))
render_excluded_disclosure(*excluded_counts_from_facts(include_conference))

st.markdown("#### 🤝 Collaborations")
kpi_cols3 = st.columns(4)
with kpi_cols3[0]:
    st.metric("🌍 % International", format_pct(element_data['pct_international']))
with kpi_cols3[1]:
    st.metric("🏢 % Entreprise", format_pct(element_data['pct_company']))

st.markdown("#### 🌱 Grands défis sociétaux")
kpi_cols4 = st.columns(4)
with kpi_cols4[0]:
    st.metric("% en lien avec les ODD", format_pct(element_data['pct_sdg']))
with kpi_cols4[1]:
    st.metric("% I-SITE", format_pct(element_data['pct_isite']))

# =============================================================================
# Section 3: Sublevel Breakdown
# =============================================================================
if level in ["domain", "field", "subfield"]:
    st.markdown("---")

    child_level_label = CHILD_LEVEL_LABELS.get(level, "Sub-element")
    _child_label_fr = {"Field": "champs", "Subfield": "sous-champs", "Topic": "topics"}.get(child_level_label, "sous-éléments")
    st.markdown(f"### 📊 Répartition par {_child_label_fr} au sein de {element_name}")

    df_sub = get_sublevel_data(level, element_id)

    # ARTIFACT-FLAG (VIZ_SPEC 1.2 / plan §6.2): this sublevel table is topic-grain
    # exactly when its children are topics (level == 'subfield'). Toggle ON drops the
    # flagged topic rows (§6.2(ii)); the pubs_total etc. of the surviving rows are
    # untouched (ships-v2, no recompute) -- only row presence changes.
    _is_topic_grain = (child_level_label == "Topic")
    _n_dropped_artifact = 0
    if _is_topic_grain and not df_sub.empty:
        df_sub = df_sub.copy()
        df_sub["artifact_flag"] = df_sub["child_id"].isin(_artifact_topic_ids())
        if _ARTIFACT_ON:
            _n_before = len(df_sub)
            df_sub = df_sub[~df_sub["artifact_flag"]]
            _n_dropped_artifact = _n_before - len(df_sub)

    if df_sub.empty:
        st.info(f"Aucune répartition par {_child_label_fr} disponible pour {element_name}.")
    else:
        df_sub = df_sub.sort_values("pubs_total", ascending=False)

        sub_table = []
        for _, row in df_sub.iterrows():
            entry = {"Nom": row["child_name"]}
            if _is_topic_grain:
                # VIZ_SPEC 1.2: the "Réf." marker column sits right beside the row's own
                # identifying label -- never buried past the metric columns.
                entry["Réf."] = controls.DAGGER if row["artifact_flag"] else ""
            entry.update({
                "Publications": int(row["pubs_total"]),
                f"Part du {level_label}": row["pubs_pct_of_parent"] * 100,
                # I-SITE overlay (R1): same-row twin (pct_isite), gated by the global
                # toggle -- toggle OFF -> this column is absent, byte-identical to the
                # pre-pass-5 table; toggle ON -> the precomputed share appears.
                **({"Contribution I-SITE": row["pct_isite"] * 100} if _ISITE_OVERLAY_ON else {}),
                "Top 10 %": format_indicator_pct(row["pct_top10"]),
                "Top 1 %": format_indicator_pct(row["pct_top1"]),
                "% International": format_pct(row["pct_international"]),
                "FWCI médian (réf. France)": na_metric(row['fwci_median']),
                "FWCI moyen (réf. France)": na_metric(row['fwci_mean']),
                "Momentum": format_momentum(row),
            })
            sub_table.append(entry)

        df_sub_display = pd.DataFrame(sub_table)
        _sub_col_config = {
            f"Part du {level_label}": st.column_config.ProgressColumn(
                f"Part du {level_label}",
                min_value=0,
                max_value=100,
                format="%.1f%%",
            ),
        }
        if _ISITE_OVERLAY_ON:
            _sub_col_config["Contribution I-SITE"] = st.column_config.ProgressColumn(
                "Contribution I-SITE", min_value=0, max_value=100, format="%.1f%%",
            )
        if _is_topic_grain:
            _sub_col_config["Réf."] = controls.marker_dagger_column_config()
        st.dataframe(
            df_sub_display,
            use_container_width=True,
            hide_index=True,
            height=min(400, 35 + len(sub_table) * 35),
            column_config=_sub_col_config,
        )
        exports.attach_download(
            st, df_sub_display, "thematic-drilldown", f"{child_level_label.lower()}-mix",
            exports.ExportState(
                snapshot=_SNAPSHOT_DATE, conf=include_conference, artifact=_ARTIFACT_ON,
                subset=_controls_state.get("perimeter_subset", "all"),
                artifact_applied=(_ARTIFACT_ON if _is_topic_grain else False),
            ),
            node=(NODE_LEVEL_PREFIX[level], element_id),
        )
        if _is_topic_grain and _ARTIFACT_ON and _n_dropped_artifact:
            st.caption(
                f":grey[{_n_dropped_artifact:,} topic(s) hors référentiel exclus de cette "
                "liste (filtre référentiel actif).]"
            )

        # Time Evolution Charts
        st.markdown(f"### 📈 Évolution temporelle par {_child_label_fr}")

        time_data = []
        for _, row in df_sub.iterrows():
            year_counts = parse_year_counts(row["pubs_per_year"])
            for year, count in year_counts.items():
                time_data.append({
                    "Year": year,
                    "Name": row["child_name"],
                    "Count": count,
                })

        df_time = pd.DataFrame(time_data)

        if not df_time.empty:
            top_names = df_sub.nlargest(10, "pubs_total")["child_name"].tolist()
            df_time_top = df_time[df_time["Name"].isin(top_names)]

            df_time_other = df_time[~df_time["Name"].isin(top_names)].groupby("Year")["Count"].sum().reset_index()
            df_time_other["Name"] = "Autres"

            df_time_plot = pd.concat([df_time_top, df_time_other], ignore_index=True)

            # Colour follows the entity in a FIXED order, so filtering or a change of
            # level never repaints the survivors. FOLLOW-UP 1 (manager, post-render):
            # VIZ_SPEC S1.1 -- the DOMAIN set is never cycled onto an unrelated series
            # axis (these entities are labs/subfields, not domains); H.DOMAIN_COLORS'
            # dual id/name keying also silently repeated every 5 slots. H.SERIES_COLORS
            # (7 Okabe-Ito hues) is the correct token for a ranked, arbitrary-length
            # series axis -- past 7 entries the line is DASHED so no two series ever
            # share hue+dash; never px.colors.*; "Autres" stays H.NEUTRAL_GREY, off
            # the cycle and always solid.
            _series_colors = H.SERIES_COLORS
            color_map = {name: _series_colors[i % len(_series_colors)] for i, name in enumerate(top_names)}
            color_map["Autres"] = H.NEUTRAL_GREY
            _dash_map = {name: ("dash" if i >= len(_series_colors) else "solid") for i, name in enumerate(top_names)}
            _dash_map["Autres"] = "solid"

            st.markdown("**Valeurs absolues**")
            _hl_abs = copy_fr.HOVER_LABELS["ex_time_abs"]["default"]
            _hover_abs = {
                (r["Name"], int(r["Year"])): hv.hover_lines([
                    (_hl_abs[0], r["Name"]),
                    (_hl_abs[1], str(int(r["Year"]))),
                    (_hl_abs[2], hv.fmt_int(r["Count"])),
                ])
                for _, r in df_time_plot.iterrows()
            }
            fig_abs = px.line(
                df_time_plot,
                x="Year",
                y="Count",
                color="Name",
                color_discrete_map=color_map,
                markers=True,
            )
            for _trace in fig_abs.data:
                _trace.customdata = [_hover_abs[(_trace.name, int(x))] for x in _trace.x]
                _trace.hovertemplate = hv.HOVERTEMPLATE
                _trace.line.dash = _dash_map.get(_trace.name, "solid")
            fig_abs.update_layout(
                height=400,
                margin=dict(t=30, l=50, r=30, b=50),
                xaxis=dict(
                    dtick=1,
                    showgrid=True,
                    gridcolor="lightgrey",
                    gridwidth=0.5,
                ),
                xaxis_title="Année",
                yaxis_title="Publications",
                legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
                legend_title_text="",
            )
            reading.reading_line("ex_time_abs")
            st.plotly_chart(fig_abs, use_container_width=True)

            st.markdown("**Part relative (empilement 100 %)**")
            df_time_pct = df_time_plot.copy()
            year_totals = df_time_pct.groupby("Year")["Count"].transform("sum")
            df_time_pct["Share"] = (df_time_pct["Count"] / year_totals * 100).fillna(0)

            _hl_share = copy_fr.HOVER_LABELS["ex_time_share"]["default"]
            _hover_share = {
                (r["Name"], int(r["Year"])): hv.hover_lines([
                    (_hl_share[0], r["Name"]),
                    (_hl_share[1], str(int(r["Year"]))),
                    (_hl_share[2], hv.fmt_pct(r["Share"])),
                    (_hl_share[3], hv.fmt_int(r["Count"])),
                ])
                for _, r in df_time_pct.iterrows()
            }
            fig_stack = px.area(
                df_time_pct,
                x="Year",
                y="Share",
                color="Name",
                color_discrete_map=color_map,
                groupnorm="percent",
            )
            for _trace in fig_stack.data:
                _trace.customdata = [_hover_share[(_trace.name, int(x))] for x in _trace.x]
                _trace.hovertemplate = hv.HOVERTEMPLATE
                _trace.line.dash = _dash_map.get(_trace.name, "solid")
            fig_stack.update_layout(
                height=400,
                margin=dict(t=30, l=50, r=30, b=50),
                xaxis=dict(
                    dtick=1,
                    showgrid=True,
                    gridcolor="lightgrey",
                    gridwidth=0.5,
                ),
                xaxis_title="Année",
                yaxis=dict(title="Part (%)", range=[0, 100]),
                legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
                legend_title_text="",
            )
            _share_ticks = [0, 20, 40, 60, 80, 100]
            fig_stack.update_yaxes(
                tickmode="array", tickvals=_share_ticks,
                ticktext=[H.fr_pct(v, 0) for v in _share_ticks],
            )
            reading.reading_line("ex_time_share")
            st.plotly_chart(fig_stack, use_container_width=True)

# =============================================================================
# Section 5: Contribution Analysis
# =============================================================================
st.markdown("---")
st.markdown("### 🏗️ Analyse des contributions")

contrib_data = get_contribution_data(level, element_id)

if contrib_data is None:
    st.info("Aucune répartition des contributions publiée pour ce niveau.")
else:
    if not include_conference:
        conference_blob_caveat("Les graphiques de contribution")

    st.markdown("**Départements contributeurs**")
    dept_col = find_column(contrib_data, "department_breakdown")
    dept_items = []
    if dept_col:
        dept_items = parse_top_items(
            contrib_data.get(dept_col, ""),
            ["dept", "count", "pct"]
        )
    # I-SITE overlay (R1): department_breakdown_isite is a same-row twin, same order/
    # keys, built this pass (docs/OVERLAY_MATRIX.md) -- read by EXACT column name
    # (never via find_column's substring match, to never accidentally pick up the
    # twin instead of the base blob) and merged by "dept" key, not position, as a
    # defensive safeguard against any future reordering.
    dept_isite_items = parse_top_items(contrib_data.get("department_breakdown_isite", ""), ["dept", "count", "pct"])
    _dept_isite_map = {it["dept"]: safe_int(it["count"]) for it in dept_isite_items}
    if dept_items:
        dept_df = pd.DataFrame(dept_items)
        dept_df["count"] = dept_df["count"].apply(safe_int)
        dept_df["pct"] = dept_df["pct"].apply(safe_float)
        dept_df["isite_count"] = dept_df["dept"].map(_dept_isite_map).fillna(0)
        # Pass 7b (B2/render-check catch): bars_with_gutter's fixed y-axis convention
        # (Streamlit/lib/charts.py::_bar_layout, range=[n-0.5, -0.5]) puts FRAME ROW 0
        # at the TOP -- the opposite of the old overlay_bars() call this replaced, which
        # wanted ascending order for that same visual result. Descending here is what
        # makes "la plus fournie en haut" (this chart's own reading line) true.
        dept_df = dept_df.sort_values("count", ascending=False)

        _hl_dept = copy_fr.HOVER_LABELS["ex_dept_bars"]["default"]
        dept_df["hover"] = [
            hv.hover_lines([
                (_hl_dept[0], r["dept"]),
                (_hl_dept[1], hv.fmt_int(r["count"])),
                (_hl_dept[2], hv.fmt_int(r["isite_count"]) if _ISITE_OVERLAY_ON else None),
            ])
            for _, r in dept_df.iterrows()
        ]
        fig_dept = charts.bars_with_gutter(
            dept_df, family="labo", label_col="dept", value_col="count",
            color=H.UL_COLOR, hover_col="hover",
            isite_col="isite_count", isite_on=_ISITE_OVERLAY_ON,
            value_fmt=hv.fmt_int,
        )
        reading.reading_line("ex_dept_bars")
        st.plotly_chart(fig_dept, use_container_width=True)
        if _ISITE_OVERLAY_ON:
            st.caption(":grey[Segment plus sombre = part I-SITE du département (même ligne, aucun recalcul).]")
        exports.attach_download(
            st, dept_df, "thematic-drilldown", "contributing-departments", _EXPORT_STATE,
            node=(NODE_LEVEL_PREFIX[level], element_id),
        )
    else:
        st.info("Aucune donnée de département.")

    st.markdown("**Top 10 laboratoires / structures internes contributeurs**")

    lab_col = find_column(contrib_data, "top_labs")
    lab_items = []
    if lab_col:
        lab_items = parse_top_items(
            contrib_data.get(lab_col, ""),
            ["ror", "name", "type", "count", "pct"]
        )
    # Same I-SITE overlay treatment as the department chart above, merged by "ror"
    # (the stable identifying key) rather than position.
    # PASS-6 FIX (probe 5, #21a): top_labs_isite is a 4-field blob
    # ("ror:name:count:pct" -- pipeline/44d_build_detail_contributions.py:121-122,
    # "isite_count is not repeated" -- no "type" field, unlike the base top_labs
    # blob it sits beside). Asking parse_top_items() for the base 5-field schema
    # made `len(parts) >= len(expected_fields)` (4 >= 5) always False, so every
    # item was silently dropped and the overlay drew a permanently zero-width
    # dark segment -- no exception, no visible failure. See
    # tests/test_page_pb.py::test_page6_top_labs_isite_schema_matches_the_four_field_blob
    # for the regression pin.
    lab_isite_items = parse_top_items(contrib_data.get("top_labs_isite", ""), ["ror", "name", "count", "pct"])
    _lab_isite_map = {it["ror"]: safe_int(it["count"]) for it in lab_isite_items}
    if lab_items:
        lab_df = pd.DataFrame(lab_items)
        lab_df["count"] = lab_df["count"].apply(safe_int)
        lab_df["pct"] = lab_df["pct"].apply(safe_float)
        lab_df["isite_count"] = lab_df["ror"].map(_lab_isite_map).fillna(0)

        # Same bars_with_gutter axis convention as ex_dept_bars above: row 0 -> top,
        # so the top-10 must be selected AND ordered descending in one pass.
        lab_df = lab_df.sort_values("count", ascending=False).head(10)

        _hl_lab = copy_fr.HOVER_LABELS["ex_lab_bars"]["default"]
        lab_df["hover"] = [
            hv.hover_lines([
                (_hl_lab[0], r["name"]),
                (_hl_lab[1], hv.fmt_int(r["count"])),
                (_hl_lab[2], r["type"]),
                (_hl_lab[3], hv.fmt_int(r["isite_count"]) if _ISITE_OVERLAY_ON else None),
            ])
            for _, r in lab_df.iterrows()
        ]
        fig_lab = charts.bars_with_gutter(
            lab_df, family="labo", label_col="name", value_col="count",
            color=H.UL_COLOR, hover_col="hover",
            isite_col="isite_count", isite_on=_ISITE_OVERLAY_ON,
            value_fmt=hv.fmt_int,
        )
        reading.reading_line("ex_lab_bars")
        st.plotly_chart(fig_lab, use_container_width=True)
        if _ISITE_OVERLAY_ON:
            st.caption(":grey[Segment plus sombre = part I-SITE du laboratoire (même ligne, aucun recalcul).]")
        exports.attach_download(
            st, lab_df, "thematic-drilldown", "contributing-labs", _EXPORT_STATE,
            node=(NODE_LEVEL_PREFIX[level], element_id),
        )
    else:
        st.info("Aucune donnée de laboratoire.")

# =============================================================================
# Section 6: Partner Tables
# =============================================================================
st.markdown("---")
st.markdown("### 🤝 Principaux partenaires")

partner_data = get_partner_data(level, element_id)


def _has_partner_denominator(items, field="share_partner"):
    """
    True when at least one item carries the partner's own output.

    `share_partner` / `partner_total` come from `ul_partners_base.parquet`, an
    OpenAlex pull outside the UL corpus. When it is missing, the builder emits the
    empty string — never 0, which would be a fabricated denominator — and the app
    renders "—" and hides the reciprocity chart.
    """
    return any(str(item.get(field, "")).strip() not in ("", "nan") for item in items)


if partner_data is None:
    st.info("Aucune répartition de partenaires publiée pour ce niveau.")
else:
    if not include_conference:
        conference_blob_caveat("Les tableaux partenaires")

    st.markdown("**Principaux partenaires internationaux**")
    st.caption(
        ":grey[Les premières lignes s'affichent par défaut ; « afficher plus » "
        "déploie la liste jusqu'à la profondeur disponible pour cet élément, et "
        "la recherche atteint n'importe quelle ligne.]"
    )
    int_col = find_column(df_partners, "top_int_partners")
    # Format: id:name:country:type:copubs:share_ul:share_int:share_partner:fwci (9 fields)
    int_items = parse_top_items(
        partner_data.get(int_col, ""),
        ["id", "name", "country", "type", "copubs", "share_ul", "share_int", "share_partner", "fwci"]
    ) if int_col else []
    if int_items:
        int_df = pd.DataFrame(int_items)
        int_df["copubs"] = int_df["copubs"].apply(safe_int)
        for c in ("share_ul", "share_int", "share_partner", "fwci"):
            int_df[c] = int_df[c].apply(safe_float)

        _pct_ul_col = f"% du {level_label} à l'UL"
        _pct_partner_col = f"% du {level_label} chez le partenaire"
        int_display = int_df[["id", "name", "country", "type", "copubs", "share_ul", "share_partner", "share_int", "fwci"]].copy()
        int_display.columns = [
            "id", "Partenaire", "Pays", "Type", "Co-publications",
            _pct_ul_col,
            _pct_partner_col,
            "% des collaborations",
            "FWCI (réf. France)",
        ]
        int_display[_pct_ul_col] = int_display[_pct_ul_col] * 100
        int_display["% des collaborations"] = int_display["% des collaborations"] * 100
        int_display[_pct_partner_col] = int_display[_pct_partner_col] * 100
        # P7-R6/VIZ_SPEC_pass7 SS5.15 fwci_paire_2d convention (see _fwci_pair_or_na).
        int_display["FWCI (réf. France)"] = [
            _fwci_pair_or_na(fw, cp) for fw, cp in zip(int_df["fwci"], int_df["copubs"])
        ]
        # P7-R4/BUILD_PLAN P4: live OpenAlex link, ADDED alongside the existing columns
        # (never replacing "Partenaire" -- test_page6_partner_ranked_table_defaults_to_top_ten
        # keys off that column's presence).
        int_display["Lien"] = [
            links.copubs_url(pid, node=_link_node(level, element_id)) for pid in int_display["id"]
        ]

        _visible_int = ranked_table(
            int_display,
            key=f"int_partners_{level}_{element_id}",
            id_col="id",
            search_cols=["Partenaire"],
            # #23: the member-mask toggle only helps where the consortium's
            # signatories can actually show up crowding a national list --
            # this is the international-only surface, so it stays off here
            # (kept on the French table just below).
            has_members=False,
            progress_cols={
                _pct_ul_col: {},
                "% des collaborations": {"help": "Part de toutes les co-publications de l'UL avec ce partenaire"},
                _pct_partner_col: {"help": "Part de la production propre du partenaire à ce niveau qui implique l'UL"},
            },
            # "id" is the raw OpenAlex identifier, needed for the member-mask/badge --
            # hidden from the visible column order via the SAME documented st.dataframe
            # mechanism lib.ranked.build_column_order already uses for mean_cols
            # (omitted from column_order, still user-addable), reused here to hide an
            # id column rather than a mean -- both are "hidden by default" cases.
            mean_cols=["id"],
            # P7-R4: the ↗ link column (deliverable 2) -- kwarg appended LAST so the
            # has_members=False pin above stays at its original character offset
            # (test_page6_international_partners_table_has_no_member_mask_toggle).
            link_cols={"Lien": {"help": links.LINK_TOOLTIP_FR, "display_text": links.LINK_ICON_GLYPH}},
        )
        exports.attach_download(
            st, _visible_int.drop(columns=["id"]), "thematic-drilldown", "international-partners", _EXPORT_STATE,
            node=(NODE_LEVEL_PREFIX[level], element_id),
        )
        if not _has_partner_denominator(int_items):
            st.caption(
                f":grey[**{_pct_partner_col}** est vide : elle demande le volume "
                "propre du partenaire à ce niveau, mesuré séparément du corpus "
                "lorrain. Aucune valeur n'est affichée plutôt qu'une valeur "
                "fabriquée.]"
            )
    else:
        st.info("Aucune donnée de partenaire international.")

    st.markdown("**Principaux partenaires français**")
    st.caption(
        ":grey[Les premières lignes s'affichent par défaut ; « afficher plus » "
        "déploie la liste jusqu'à la profondeur disponible pour cet élément, et "
        "la recherche atteint n'importe quelle ligne. Le bouton « masquer les "
        "membres du site » retire les signataires du consortium I-SITE de la "
        "liste visible.]"
    )
    fr_col = find_column(df_partners, "top_fr_partners")
    # Format: id:name:type:copubs:share_ul:share_int:share_partner:fwci (8 fields, no country)
    fr_items = parse_top_items(
        partner_data.get(fr_col, ""),
        ["id", "name", "type", "copubs", "share_ul", "share_int", "share_partner", "fwci"]
    ) if fr_col else []
    if fr_items:
        fr_df = pd.DataFrame(fr_items)
        fr_df["copubs"] = fr_df["copubs"].apply(safe_int)
        for c in ("share_ul", "share_int", "share_partner", "fwci"):
            fr_df[c] = fr_df[c].apply(safe_float)

        _pct_ul_col = f"% du {level_label} à l'UL"
        _pct_partner_col = f"% du {level_label} chez le partenaire"
        fr_display = fr_df[["id", "name", "type", "copubs", "share_ul", "share_partner", "share_int", "fwci"]].copy()
        fr_display.columns = [
            "id", "Partenaire", "Type", "Co-publications",
            _pct_ul_col,
            _pct_partner_col,
            "% des collaborations",
            "FWCI (réf. France)",
        ]
        fr_display[_pct_ul_col] = fr_display[_pct_ul_col] * 100
        fr_display["% des collaborations"] = fr_display["% des collaborations"] * 100
        fr_display[_pct_partner_col] = fr_display[_pct_partner_col] * 100
        # P7-R6/VIZ_SPEC_pass7 SS5.15 fwci_paire_2d convention (see _fwci_pair_or_na).
        fr_display["FWCI (réf. France)"] = [
            _fwci_pair_or_na(fw, cp) for fw, cp in zip(fr_df["fwci"], fr_df["copubs"])
        ]
        # P7-R4/BUILD_PLAN P4: live OpenAlex link (deliverable 2).
        fr_display["Lien"] = [
            links.copubs_url(pid, node=_link_node(level, element_id)) for pid in fr_display["id"]
        ]

        _visible_fr = ranked_table(
            fr_display,
            key=f"fr_partners_{level}_{element_id}",
            id_col="id",
            search_cols=["Partenaire"],
            has_members=True,
            progress_cols={
                _pct_ul_col: {},
                "% des collaborations": {"help": "Part de toutes les co-publications de l'UL avec ce partenaire"},
                _pct_partner_col: {"help": "Part de la production propre du partenaire à ce niveau qui implique l'UL"},
            },
            mean_cols=["id"],
            # kwarg appended LAST -- keeps has_members=True at its original offset
            # (test_page6_international_partners_table_has_no_member_mask_toggle checks
            # the FR call too, within [:300] of the key= literal).
            link_cols={"Lien": {"help": links.LINK_TOOLTIP_FR, "display_text": links.LINK_ICON_GLYPH}},
        )
        exports.attach_download(
            st, _visible_fr.drop(columns=["id"]), "thematic-drilldown", "french-partners", _EXPORT_STATE,
            node=(NODE_LEVEL_PREFIX[level], element_id),
        )
        if not _has_partner_denominator(fr_items):
            st.caption(
                f":grey[**{_pct_partner_col}** est vide : elle demande le volume "
                "propre du partenaire à ce niveau, mesuré séparément du corpus "
                "lorrain. Aucune valeur n'est affichée plutôt qu'une valeur "
                "fabriquée.]"
            )
    else:
        st.info("Aucune donnée de partenaire français.")

# =============================================================================
# Section 7: Strategic Reciprocity Chart
# =============================================================================
if level in ["domain", "field", "subfield"] and partner_data is not None:
    st.markdown("---")
    st.markdown("### ⚖️ Réciprocité stratégique avec les partenaires")

    recip_col = find_column(df_partners, "reciprocity_partners")
    # Format: id:name:country:type:copubs:share_ul:share_int:share_partner:partner_total:fwci (10 fields)
    recip_items = parse_top_items(
        partner_data.get(recip_col, ""),
        ["id", "name", "country", "type", "copubs", "share_ul", "share_int", "share_partner", "partner_total", "fwci"]
    ) if recip_col else []

    if not _has_partner_denominator(recip_items, "partner_total"):
        # Contract degradation path: the chart's x-axis IS the partner's own output.
        # Without it there is no chart to draw, and no honest way to fake one.
        st.info(
            "Ce graphique compare la part de l'UL dans le volume propre d'un "
            "partenaire à la part du partenaire dans le volume de l'UL. Le "
            "dénominateur côté partenaire n'est pas disponible pour cet élément : "
            "le graphique est masqué plutôt que tracé sur un axe fabriqué.",
            icon="ℹ️",
        )
    else:
        # P7-R6/BUILD_PLAN P3: the static "Comment lire" bullet list is REPLACED by
        # ONE mode-aware reading line (built once the mode is known, below, right
        # above the figure) -- "Pourquoi cet indicateur" STAYS, unmoved in wording.
        st.caption(
            ":grey[**Pourquoi cet indicateur.** Une relation peut être décisive "
            "pour l'un des deux partenaires et marginale pour l'autre. Croiser "
            "les deux parts sépare les partenariats structurants des "
            "partenariats de volume, et c'est la lecture qui prépare une "
            "discussion d'accord-cadre.]"
        )

        recip_df = pd.DataFrame(recip_items)
        recip_df["copubs"] = recip_df["copubs"].apply(safe_int)
        for c in ("share_ul", "share_int", "share_partner", "fwci"):
            recip_df[c] = recip_df[c].apply(safe_float)
        recip_df["partner_total"] = recip_df["partner_total"].apply(safe_int)

        # Filter out rows with no meaningful data
        recip_df = recip_df[(recip_df["share_ul"] > 0) | (recip_df["share_partner"] > 0)]
        recip_df = recip_df[recip_df["partner_total"] > 0]

        def geo_category(country):
            # BUGFIX (P-EX, found while wiring the mode-aware reading line): the
            # `reciprocity_partners` blob's country field is an ISO-2 CODE ("FR"),
            # never the literal string "France" -- verified against
            # thematic_detail_partners.parquet at domain/subfield grain (probe:
            # progress/P7_EX.md). The old `== "France"` comparison never matched,
            # so "France uniquement" always emptied and "International uniquement"
            # silently included French partners too -- pre-existing, in-fence,
            # fixed here (both toggles are named in deliverable 1's "keep the
            # existing filters", which means keep them WORKING, not silently inert).
            if country == "FR":
                return "France"
            if pd.isna(country) or country in ["", "None"]:
                return "Pays inconnu"
            return "International"

        recip_df["geo"] = recip_df["country"].apply(geo_category)

        # -----------------------------------------------------------------
        # #24 -- institution-TYPE filter (default: education only) + geographic
        # scope + member mask. Without this, administrative subdivisions of a
        # large organisation (a research-council regional office, say) can
        # show a near-total share of their own small output co-signed with
        # the site -- a real number, but not a partner comparable to a
        # university -- and crowd out the readings that are.
        # -----------------------------------------------------------------
        _recip_key = f"recip_{level}_{element_id}"
        _types_present = sorted({
            str(it.get("type", "")).strip() for it in recip_items if str(it.get("type", "")).strip()
        })
        _default_types = ["education"] if "education" in _types_present else _types_present
        recip_filter_cols = st.columns([2, 2, 1])
        with recip_filter_cols[0]:
            type_filter = st.multiselect(
                "Filtrer par type d'institution",
                options=_types_present,
                default=_default_types,
                key=f"{_recip_key}_type",
                help=(
                    "Certains types d'institutions (délégation régionale d'un "
                    "grand organisme, structure administrative) peuvent "
                    "afficher une part quasi totale de leur propre volume avec "
                    "le site sans être des partenaires scientifiques "
                    "comparables aux universités ou écoles. Sélection vide = "
                    "tous les types."
                ),
            )
        with recip_filter_cols[1]:
            geo_scope = st.radio(
                "Portée géographique",
                options=["France et international", "France uniquement", "International uniquement"],
                index=0,
                key=f"{_recip_key}_geo",
                horizontal=True,
            )
        with recip_filter_cols[2]:
            recip_hide_members = st.toggle(
                HIDE_MEMBERS_LABEL, value=False, key=f"{_recip_key}_hide_members",
            )

        if type_filter:
            recip_df = recip_df[recip_df["type"].isin(type_filter)]
        if geo_scope == "France uniquement":
            recip_df = recip_df[recip_df["geo"] == "France"]
        elif geo_scope == "International uniquement":
            recip_df = recip_df[recip_df["geo"] == "International"]
        recip_df = mask_members(recip_df, "id", CONSORTIUM_IDS, recip_hide_members)

        # Outlier toggle
        remove_outliers = st.checkbox(
            "Exclure les valeurs aberrantes (part partenaire > 100 %)",
            value=False,
            help="Certains partenaires peuvent afficher une part > 100 % (dérive de données). Cocher pour les exclure."
        )
        if remove_outliers:
            recip_df = recip_df[(recip_df["share_partner"] <= 1.0) & (recip_df["share_ul"] <= 1.0)]
        st.caption(
            ":grey[Les parts supérieures à 100 % sont plafonnées à 100 % et "
            "signalées : elles viennent de l'écart entre l'instantané figé du "
            "corpus et le décompte du partenaire mesuré en direct, jamais "
            "d'une part réellement supérieure au total.]"
        )

        # site_reciprocity_scatter is log-log (P7-R3(a)): a share of exactly zero
        # cannot be placed on either axis -- dropped and counted here (VIZ_SPEC_pass7
        # SS5.14 "Empty/thin"), rather than left to plotly's own silent log-axis drop.
        _n_before_log_drop = len(recip_df)
        recip_df = recip_df[(recip_df["share_ul"] > 0) & (recip_df["share_partner"] > 0)]
        _n_hidden_log = _n_before_log_drop - len(recip_df)

        if recip_df.empty:
            st.info("Aucun partenaire ne correspond à ces filtres.")
        else:
            max_partners = min(50, len(recip_df))
            n_partners = st.slider(
                "Nombre de partenaires à afficher :",
                min_value=min(5, max_partners),
                max_value=max(max_partners, min(5, max_partners) + 1),
                value=min(30, max_partners),
            )

            recip_df = recip_df.nlargest(n_partners, "copubs").reset_index(drop=True)

            # -------------------------------------------------------------
            # P7-R3(a) / VIZ_SPEC_pass7 SS5.14: onto site_reciprocity_scatter's
            # shared grammar -- log-log, UL_COLOR at 60% opacity, area = co-pub
            # volume (NOT partner_total: copy_fr's own reading text says "L'aire
            # suit le volume de co-publications"), square marker on a capped
            # share. No hub/search selection exists on this page (unlike page 8's
            # hub table), so no highlight_ids -- every mark keeps the builder's
            # uniform base opacity.
            # -------------------------------------------------------------
            plot_df = recip_df.copy()
            # Cap BOTH shares at 100 % -- the caption above already discloses this
            # generically (snapshot-vs-live drift can push either ratio over 1.0);
            # the flag catches either side, and the PLOTTED/hover value is the
            # capped one so the visual and the hover never disagree.
            plot_df["share_p_capped_flag"] = (
                (plot_df["share_partner"] > 1.0) | (plot_df["share_ul"] > 1.0)
            )
            plot_df["share_ul"] = plot_df["share_ul"].clip(upper=1.0)
            plot_df["share_p"] = plot_df["share_partner"].clip(upper=1.0)
            plot_df["co_works_full"] = plot_df["copubs"]

            _type_mode = "education" if sorted(type_filter) == ["education"] else "tous"
            _scope_mode = {
                "France et international": "fr_intl",
                "France uniquement": "fr",
                "International uniquement": "intl",
            }[geo_scope]
            _recip_mode = f"{_type_mode}|{_scope_mode}"
            _recip_labels = copy_fr.HOVER_LABELS["ex_partner_reciprocity"][_recip_mode]

            _hover_rows = []
            for _, r in plot_df.iterrows():
                _share_p_val = (
                    None if pd.isna(r["share_p"])
                    else hv.fmt_pct_dagger(r["share_p"] * 100.0, int(r["partner_total"]))
                )
                # "when: perimetre international" read at the ROW's own geography
                # (share_int is structurally ~0/meaningless for a French partner --
                # progress/P7_EX.md decision 9): shown whenever THIS bubble is
                # international, independent of the page's own scope-toggle state.
                _share_int_val = (
                    hv.fmt_pct(r["share_int"] * 100.0)
                    if r["geo"] == "International" and pd.notna(r["share_int"]) else None
                )
                _fwci_val = hv.fmt_fwci_pair(r["fwci"], r["fwci"], int(r["copubs"]))
                _hover_rows.append(hv.hover_lines(list(zip(_recip_labels, [
                    r["name"],
                    hv.fmt_int(r["copubs"]),
                    hv.fmt_pct(r["share_ul"] * 100.0),
                    _share_p_val,
                    _share_int_val,
                    _fwci_val,
                    str(r["country"]),
                    str(r["type"]),
                ]))))
            plot_df["hover"] = _hover_rows

            reading.reading_line("ex_partner_reciprocity", _recip_mode)
            if _n_hidden_log:
                st.caption(
                    f":grey[{fr_int(_n_hidden_log)} partenaire(s) sans part mesurable "
                    "sur l'un des deux axes ne sont pas représentés ici.]"
                )

            # fig_cache keyed on (element, toggles) -- P7_EX deliverable 1 / P12:
            # every control value that shapes the figure, never the frame itself.
            fig_recip = fig_cache.cached_figure(
                name="ex_partner_reciprocity",
                key=(level, element_id, tuple(sorted(type_filter)), geo_scope,
                     recip_hide_members, remove_outliers, n_partners),
                build=lambda: site_reciprocity_scatter(plot_df, floor=0),
            )
            st.plotly_chart(fig_recip, use_container_width=True)
            exports.attach_download(
                st, recip_df, "thematic-drilldown", "reciprocity", _EXPORT_STATE,
                node=(NODE_LEVEL_PREFIX[level], element_id),
            )

# =============================================================================
# Section 8: Top Authors
# =============================================================================
st.markdown("---")
st.markdown("### 👩‍🔬 Principaux auteurs")

author_data = get_author_data(level, element_id)

if author_data is not None:
    auth_col = find_column(df_authors, "top_authors")
    auth_items = parse_top_items(
        author_data.get(auth_col, ""),
        ["id", "name", "orcid", "pubs", "pct", "fwci", "is_lorraine", "labs"]
    ) if auth_col else []

    if auth_items:
        if not include_conference:
            conference_blob_caveat("Ce classement d'auteur·es")
        auth_df = pd.DataFrame(auth_items)
        auth_df["pubs"] = auth_df["pubs"].apply(safe_int)
        auth_df["pct"] = auth_df["pct"].apply(safe_float)
        auth_df["fwci"] = auth_df["fwci"].apply(safe_float)
        auth_df["is_lorraine"] = auth_df["is_lorraine"].apply(lambda x: str(x).lower() == "true")

        fwci_col_name = f"FWCI (réf. France) — {level_label}"
        share_col_name = f"Part du {level_label}"

        auth_display = auth_df[["name", "orcid", "pubs", "pct", "fwci", "is_lorraine", "labs"]].copy()
        auth_display.columns = ["Auteur·e", "ORCID", "Publications", share_col_name, fwci_col_name, "Affiliation UL", "Laboratoires"]
        auth_display[share_col_name] = auth_display[share_col_name].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "—")
        auth_display[fwci_col_name] = auth_display[fwci_col_name].apply(lambda x: f"{x:.2f}" if pd.notna(x) else NA_MARK)
        auth_display["Affiliation UL"] = auth_display["Affiliation UL"].apply(lambda x: "✅" if x else "")
        auth_display["Laboratoires"] = auth_display["Laboratoires"].apply(lambda x: x.replace("/", " | ") if x else "")

        st.caption(
            ":grey[Les premières lignes s'affichent par défaut ; « afficher plus » "
            "déploie la liste jusqu'à la profondeur disponible pour cet élément, "
            "et la recherche atteint n'importe quelle ligne. Pas de bascule "
            "membres ici : ce sont des personnes, pas des organisations "
            "partenaires.]"
        )
        _visible_auth = ranked_table(
            auth_display, key=f"authors_{level}_{element_id}", id_col="Auteur·e",
            search_cols=["Auteur·e"], has_members=False, height=500,
        )
        exports.attach_download(
            st, _visible_auth, "thematic-drilldown", "top-authors", _EXPORT_STATE,
            node=(NODE_LEVEL_PREFIX[level], element_id),
        )
    else:
        st.info("Aucune donnée d'auteur disponible.")
else:
    st.info("Aucune donnée d'auteur disponible.")

# =============================================================================
# Footer
# =============================================================================
st.markdown("---")
st.caption(f"Données : publications de l'Université de Lorraine, fenêtre {window_label()} | Taxonomie OpenAlex")
