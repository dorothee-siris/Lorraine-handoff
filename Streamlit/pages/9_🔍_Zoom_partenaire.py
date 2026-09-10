"""
Partner Drilldown (V2) -- docs/indicator_plan_FINAL.md §3 (I1,I5,I6,I7,I8,I9,I11) + §6.3 +
§6.6 / docs/studio/VIZ_SPEC.md §2.6. NEW page, chain pass 3, Assembly Line stream P2.

Pass-6 stream P-ZP (2026-08-19): grill items #40-#46 (docs/NARRATIVE_CONTRACT_pass6.md
section 2.10, docs/studio/VIZ_SPEC_pass6.md §1.5/§1.6/§7/§8, BUILD_PLAN.md P4/P5/P12) --
see git history for the full pass-6 note; superseded in most particulars by pass 7a below.

Pass-7a stream P-ZOOM (2026-09-10, BUILD_PLAN.md P1-P22, docs/studio/VIZ_SPEC_pass7.md,
docs/contract_fragments/{chart_keys_pass7,lib_api_pass7}.md, docs/tooltip_spec.yaml,
docs/OVERLAY_MATRIX.md §0/§9): the BenchUp-signature partner views land on this page.
  1. Header KPI row gains « publications phares » (ptn_summary.n_phares) with a live
     OpenAlex deep-link (lib.links.phares_url) and `help=` text from every KPI_HELP key.
  2. Volume: the yearly bars keep the grouped I-SITE-overlay grammar (lib.overlay, same
     mechanism the per-theme zoom already used) with totals/I-SITE counts now computed
     PAGE-SIDE from partner_works (ptn_yearly carries no I-SITE twin, OVERLAY_MATRIX §9);
     the old two-window comparison bar is replaced by a share-of-UL-collaborative
     sparkline (ptn_yearly.share_of_ul_collab).
  3. Balance bars (NEW, P10): UL-only | joint | partner-only mirror per field/top-30
     subfield, three modes (volume / FWCI médian / publications phares), a linked
     "Co-pubs" column, via lib.charts.balance_bars.
  4. Topic planes (NEW, P9): impact (co-pubs × FWCI) and frontier (expansion ×
     accélération) scatters over pair×topic cells, four selector modes + N slider, via
     lib.charts.fig_plane_impact/fig_plane_frontier.
  5. Profil thématique (existing field->subfield->topic descent): unchanged mechanics
     (session-state keys preserved for the cross-page navigation test), hover grammar +
     reading lines added, per-theme zoom keeps its own real I-SITE decomposition.
  6. Réciprocité stratégique: same data (ptn_fields, conf_state='all' fixed -- baseline_
     partner_share is only measured there), now built through lib.charts.reciprocity_scatter
     (BenchUp form: squared axes, dotted diagonal) instead of a page-local go.Figure.
  7. Portage: same top-20/"afficher plus" pagination, now rendered through
     lib.charts.bars_with_gutter (family="labo_court", gutter = raw co-works per lab --
     tests/_registry.py::build_zoom_portage is the lifted, tested reference for this
     exact value_col choice; VIZ_SPEC's share-vs-gutter split is not mechanically
     expressible through the single-value_col builder contract).
  8. Hover grammar (lib.hover, tooltip_spec.yaml-sourced labels from lib.copy_fr.HOVER_
     LABELS) and reading lines (lib.reading) replace the old "**Comment lire.**"
     paragraphs wherever a chart_key now exists for that panel; the descent's own
     orientation paragraph (not tied to one chart) is kept, since removing it would
     leave that UX unexplained with no registered replacement text.
  9. Page workbook (P16, lib.exports.page_workbook) at the end of the changed sections:
     identité/KPI, volume annuel, équilibre, plans, profil thématique, réciprocité,
     portage, with a Lecture sheet naming every active toggle/level/mode/selector.
  Every existing number is unchanged (regression pins in tests/test_page_pa.py /
  test_page_pf.py stay green) -- pass-7a only adds columns/sections and swaps chart
  builders, it never re-derives a quantity pass-6 already computed.

Authority (binding): VIZ_SPEC §2.6 + §1.1-1.6 + §3 · VIZ_SPEC_pass7.md (all sections) ·
indicator_plan_FINAL §3/§6.3/§6.6 · data_foundation.yaml rev 3.1+pass7_delta ·
data_contract.yaml (deployed schemas) · docs/OVERLAY_MATRIX.md §0/§9 ·
docs/contract_fragments/{chart_keys_pass7,lib_api_pass7}.md · docs/tooltip_spec.yaml.
Every shared behaviour goes through Streamlit/lib/{controls,exports,lazy,ranked,overlay,
helpers,countries_fr,charts,hover,reading,links,fig_cache,copy_fr}.py.

Decision sentence (VIZ_SPEC 2.6): after this view a porteur can say what binds UL to
partner P -- which fields, which labs carry it, whether it is rising -- and pull the exact
publications behind any cell.

Composition (profile card, argument order -- pass-7a additions marked NEW):
  1. Header: identity + consortium tag + KPI row (co-works . share_UL . share_P . median
     FWCI_FR . ISITE . NEW publications phares) + other-perimeters weights + momentum.
  2. Volume: yearly bars (grouped I-SITE overlay) + NEW share-of-UL-collaborative sparkline.
  3. NEW Équilibre de la relation (balance bars, P10).
  4. NEW Plans thématiques (topic planes, P9).
  5. Profil thématique -- the centre. Drill-in-place: field row -> subfield rows
     (floored) -> topic rows (I11, scoped to the selected subfield), plus a per-theme
     annual zoom at every level (built from the lazy partner-works rows, real I-SITE
     decomposition).
  6. Réciprocité stratégique par champ/sous-champ (BenchUp form).
  7. Portage (I7): top 20 labs' share of lab-attributed works (10 shown, "afficher plus")
     + "Autres" (neutral grey) + a NO-LAB disclosure line, never a league column.
  8. NEW Export complet de la page (page workbook).
  9. Publications: a 5-row preview + a lazy CSV download carrying enrichment metadata,
     never the full on-screen list (item #44, unchanged this pass).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import charts as C, controls, copy_fr, exports, fig_cache, hover as hv, lazy, links, overlay, partner_frames as PF, ranked, reading
from lib.countries_fr import country_label
from lib.data_cache import DATA_DIR, get_corpus_facts_df, get_topics_df
from lib.helpers import (
    TEXT_SECONDARY,
    YEARS, DOMAIN_EMOJI, NEUTRAL_GREY, UL_COLOR,
    MOMENTUM_DOWN_COLOR, MOMENTUM_METHOD_HELP_FR, MOMENTUM_NEUTRAL_COLOR,
    MOMENTUM_STABLE_COLOR, MOMENTUM_UP_COLOR,
    fr_int, fr_pct, lazy_slice_csv_bytes, momentum_display, window_label,
    init_taxonomy, get_domain_id_to_name, get_domain_color, get_field_id_to_name,
    get_field_id_to_domain_id, get_subfield_id_to_name, get_subfield_color,
    get_subfields_for_field,
)

# =============================================================================
# Page config
# =============================================================================
st.set_page_config(page_title="Zoom partenaire | Bibliométrie UL", page_icon="🔍", layout="wide")

init_taxonomy(get_topics_df())

I11_SPARKLINE_FLOOR = 3    # config.yaml workshop_tunables.i11_sparkline_min_works
PTN_WORKS_PATH = str(DATA_DIR / "ptn_works.parquet")
PTN_TOPICS_PATH = str(DATA_DIR / "ptn_topics.parquet")
FIELD_CHART_CAP = 20
SUBFIELD_CHART_CAP = 20
NODE_BASE_COLOR = UL_COLOR  # B6/B8: page-local hex retired -- single-sourced token
PORTAGE_DEFAULT_N = 10
PORTAGE_MAX_N = 20

# Pass-7a (P-ZOOM) constants
JOINT_FLOOR = 5             # P8: under-floor relation, matches hv.fmt_joint_or_floor's default
PLANE_FLOOR = 5              # P9: pair x topic cell floor
PLANE_N_DEFAULT = 25
LEVEL_KEYS = ["field", "subfield"]     # copy_fr.LABELS["LEVEL_TOGGLE"] index order
# FIX-1 D7: bin labels are NEVER typed here -- read live from dim_frontier_components via
# PF.latest_and_previous_bin_labels() at the point of use (S-LENS A5/D7: a module constant
# passed as a reading_line kwarg is invisible to test_narrative's scanner).

QUESTION_FR = (
    "Qu'est-ce qui relie l'Université de Lorraine à ce partenaire -- quels champs, quels "
    "laboratoires -- et la relation progresse-t-elle ?"
)
S10_BANNER_FR = (
    "Un **« outil d'animation scientifique »** : comprendre ce qui relie l'UL à un "
    "partenaire donné et ouvrir les publications derrière chaque cellule, jamais un "
    "classement des partenaires entre eux."
)
NO_MATCH_MSG_FR = "Aucun partenaire ne correspond à cette recherche."
TOPIC_ISITE_NA_FR = (
    ":grey[Pas de décomposition I-SITE à ce niveau : le croisement partenaire × topic ne "
    "porte pas la distinction I-SITE.]"
)
PORTAGE_ISITE_NA_FR = (
    ":grey[Lecture structurelle : comme pour le filtre « hors référentiel », la surcouche "
    "I-SITE ne s'applique pas à ce panneau.]"
)
SHARE_P_NULL_BY_DESIGN_FR = (
    ":grey[La colonne « Part partenaire » n'est renseignée que sur le corpus entier, tous "
    "types de publication confondus : une part hors conférence rapportée à un total qui, "
    "lui, les inclut ne serait pas une part réelle. Dans cet état, la colonne affiche "
    "« — » plutôt qu'un zéro.]"
)
FIELD_SHARE_P_NULL_FR = (
    ":grey[La colonne « % du partenaire » n'est renseignée que sur le corpus entier, tous "
    "types de publication confondus ; dans cet état elle affiche « — » plutôt qu'un zéro.]"
)

MOM_LABELS = {
    "up": ("en hausse", "↑"), "down": ("en retrait", "↓"), "stable": ("stable", "→"),
    "ns": ("non significatif", "—"), "new": ("nouveau partenaire", "＋"),
    "dormant": ("partenaire dormant", "◦"),
}
MOM_STATUS_COLOR = {
    "up": MOMENTUM_UP_COLOR, "down": MOMENTUM_DOWN_COLOR, "stable": MOMENTUM_STABLE_COLOR,
}


def _mom_chip(category, arrow=None) -> str:
    """Field-grain momentum chip: ptn_fields carries a CLASS only (no mom_w1_share/
    mom_w2_share/mom_count_arrow at that grain), so lib.helpers.momentum_display() cannot
    be applied honestly here -- it needs those columns and would silently return "—" for
    every up/down/stable row. Kept as the class-only label this one grain still supports."""
    if pd.isna(category):
        return "—"
    label, sym = MOM_LABELS.get(str(category), (str(category), ""))
    suffix = f" ({arrow})" if arrow is not None and pd.notna(arrow) and str(arrow).strip() else ""
    return f"{sym} {label}{suffix}"


def _fr_float(val, decimals: int = 2) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)) or pd.isna(val):
        return "—"
    return f"{float(val):.{decimals}f}".replace(".", ",")


def _area_sizeref(values, max_px: float = 40.0) -> float:
    vmax = float(np.nanmax(values)) if len(values) else 1.0
    vmax = vmax if vmax > 0 else 1.0
    return 2.0 * vmax / (max_px ** 2)


def _kpi_help(key: str) -> str:
    """copy_fr.KPI_HELP[key] with its {window}/{max_ids} placeholders filled -- str.format
    ignores any kwarg a given template does not reference (copy_fr.KPI_PLACEHOLDERS says
    which ones each key actually needs), so passing both is safe for every KPI key."""
    return copy_fr.KPI_HELP[key].format(window=window_label(), max_ids=links.IDLIST_MAX)


def _caption(key: str) -> str:
    """copy_fr.CAPTIONS[key] with its {max_ids} placeholder filled where needed (FIX-1
    D14: `links.IDLIST_MAX` is the single source, never retyped as "cent")."""
    return copy_fr.CAPTIONS[key].format(max_ids=links.IDLIST_MAX)


# =============================================================================
# Data (eager, small tables -- cache_data w/ max_entries=2, S4/P12: identity-comparison
# grep-proof recorded in progress/P7_CACHE.md, no `is`/`is not` frame-identity check on
# any of these six anywhere on this page)
# =============================================================================
@st.cache_data(ttl=1800, max_entries=2)
def _load_ptn_summary() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "ptn_summary.parquet")


@st.cache_data(ttl=1800, max_entries=2)
def _load_ptn_yearly() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "ptn_yearly.parquet")


@st.cache_data(ttl=1800, max_entries=2)
def _load_ptn_fields() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "ptn_fields.parquet")


@st.cache_data(ttl=1800, max_entries=2)
def _load_ptn_labs() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "ptn_labs.parquet")


@st.cache_data(ttl=1800, max_entries=2)
def _load_ptn_mom_facts() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "ptn_mom_facts.parquet")


@st.cache_data(ttl=1800, max_entries=2)
def _load_ptn_denominators() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "ptn_denominators.parquet")


# Pass-7a (P-ZOOM) additions: same zero-argument, whole-small-table shape as the six
# loaders above, so the same S4 cache discipline applies even though P7_CACHE.md's own
# line list (written before these two sections existed) only names the pre-existing six.
@st.cache_data(ttl=1800, max_entries=2)
def _load_thematic_overview() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "thematic_overview.parquet")


@st.cache_data(ttl=1800, max_entries=2)
def _load_frontier_components() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "dim_frontier_components.parquet")


def _snapshot_date() -> str:
    try:
        return str(get_corpus_facts_df()["snapshot_date"].iloc[0])
    except Exception:
        return "?"


# =============================================================================
# Per-theme annual zoom (#43) -- built from the already lazy-loaded partner works, so the
# I-SITE decomposition is REAL here even though ptn_yearly/ptn_topics carry no isite twin.
# =============================================================================
def _theme_zoom_chart(
    works_df: pd.DataFrame, filter_col: str, filter_val, label: str,
    include_conference: bool, artifact_on: bool, isite_overlay_on: bool, color: str,
) -> None:
    scoped = works_df[works_df[filter_col].astype(str) == str(filter_val)]
    if not include_conference:
        scoped = scoped[~scoped["is_conference"].fillna(False)]
    if artifact_on:
        scoped = scoped[~scoped["artifact_flag"].fillna(False)]
    if scoped.empty:
        st.caption("—")
        return
    totals, isites = [], []
    for y in YEARS:
        yr_scoped = scoped[scoped["year"] == y]
        totals.append(float(len(yr_scoped)))
        isites.append(float(yr_scoped["in_isite"].fillna(False).sum()))
    fig = overlay.overlay_grouped_bars(
        groups=[str(y) for y in YEARS], series=["n"], labels={"n": label},
        colors={"n": color}, totals={"n": totals}, isite={"n": isites},
        isite_on=isite_overlay_on,
    )
    fig.update_layout(
        height=260, margin=dict(t=20, l=40, r=20, b=40),
        yaxis_title="Co-publications", xaxis_title="", showlegend=False,
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(overlay.GROUPED_BARS_HOWTOREAD_FR)
    reading.reading_line("zoom_theme_zoom")


def _theme_zoom_control(label_prefix: str, options: dict, session_key: str) -> int | None:
    st.markdown(f"###### Zoom annuel sur {label_prefix}")
    zc1, zc2 = st.columns([4, 1])
    pick = zc1.selectbox(
        f"Zoomer sur {label_prefix}", options=list(options.keys()), key=f"{session_key}_pick",
        label_visibility="collapsed", placeholder=f"Zoomer sur {label_prefix}...",
    )
    if zc2.button("🔍 Zoomer", key=f"{session_key}_go") and pick:
        st.session_state[session_key] = int(options[pick])
        st.rerun()
    return st.session_state.get(session_key)


def _yearly_scope(works_df: pd.DataFrame, include_conference: bool, artifact_on: bool) -> pd.DataFrame:
    scoped = works_df
    if not include_conference:
        scoped = scoped[~scoped["is_conference"].fillna(False)]
    if artifact_on:
        scoped = scoped[~scoped["artifact_flag"].fillna(False)]
    return scoped


def _share_spark_fig(yr_p_df: pd.DataFrame) -> go.Figure:
    """zoom_share_spark (VIZ_SPEC_pass7 §5.6): micro line, UL_COLOR, first/last value
    labels only, no y axis, no grid, x ticks only at the two ends."""
    share_col = controls.xa(yr_p_df, "share_of_ul_collab")
    co_col = controls.xa(yr_p_df, "co_works")
    xs = yr_p_df["year"].astype(str).tolist()
    ys = (yr_p_df[share_col].astype(float) * 100.0).tolist()
    labels_sp = copy_fr.HOVER_LABELS["zoom_share_spark"]["default"]
    hovers = [
        hv.hover_lines(list(zip(labels_sp, (x, hv.fmt_pct(y), hv.fmt_int(c)))))
        for x, y, c in zip(xs, ys, yr_p_df[co_col].tolist())
    ]
    fig = go.Figure(go.Scatter(
        x=xs, y=ys, mode="lines+markers", line=dict(color=UL_COLOR, width=1.5),
        marker=dict(size=[8] + [0] * max(0, len(xs) - 2) + ([8] if len(xs) > 1 else [])),
        customdata=hovers, hovertemplate=hv.HOVERTEMPLATE, showlegend=False,
    ))
    fig.add_annotation(x=xs[0], y=ys[0], text=hv.fmt_pct(ys[0]), showarrow=False,
                        yshift=16, font=dict(size=11, color=UL_COLOR))
    fig.add_annotation(x=xs[-1], y=ys[-1], text=hv.fmt_pct(ys[-1]), showarrow=False,
                        yshift=16, font=dict(size=11, color=UL_COLOR))
    fig.update_layout(
        height=260, margin=dict(t=20, l=40, r=20, b=40), showlegend=False,
        yaxis=dict(visible=False), xaxis=dict(tickmode="array", tickvals=[xs[0], xs[-1]], title=""),
    )
    return fig


def _pair_level_control(widget_key: str) -> str:
    """Shared level toggle for the balance bars AND reciprocity sections (P-ZOOM
    Addendum: "shared with the reciprocity section via one session key"). Streamlit
    forbids reusing one widget `key` twice within a single run, so each section renders
    its OWN radio, but both read their initial `index` from, and both write back to, the
    SAME `st.session_state["v2_pair_level"]` -- the two controls agree after any rerun,
    which is the practical meaning of "one session key" in this harness."""
    current = st.session_state.get("v2_pair_level", "field")
    idx = LEVEL_KEYS.index(current) if current in LEVEL_KEYS else 0
    pick_idx = st.radio(
        "Niveau", options=[0, 1], index=idx, horizontal=True,
        format_func=lambda i: copy_fr.LABELS["LEVEL_TOGGLE"][i],
        key=widget_key, label_visibility="collapsed",
    )
    level = LEVEL_KEYS[pick_idx]
    st.session_state["v2_pair_level"] = level
    return level


# =============================================================================
# Sidebar + banners
# =============================================================================
ctrl = controls.sidebar()
include_conference = ctrl["include_conference"]
artifact_on = ctrl[controls.ARTIFACT_TOGGLE_KEY]
isite_overlay_on = ctrl[controls.ISITE_OVERLAY_KEY]
CONF_STATE = "all" if include_conference else "no_conf"

st.title("🔍 Zoom partenaire")
st.markdown(f"##### {QUESTION_FR}")
st.info(S10_BANNER_FR)
controls.banner()
controls.filtered_by_strip(page="zoom_partenaire")

SNAPSHOT_DATE = _snapshot_date()
_EXPORT_STATE = exports.ExportState(
    snapshot=SNAPSHOT_DATE, conf=include_conference, artifact=artifact_on, artifact_applied=bool(artifact_on),
)
_EXPORT_STATE_EXEMPT = exports.ExportState(
    snapshot=SNAPSHOT_DATE, conf=include_conference, artifact=artifact_on, artifact_applied=False,
)

domain_id2name = get_domain_id_to_name()
field_id2name = get_field_id_to_name()
field_id2domain = get_field_id_to_domain_id()
subfield_id2name = get_subfield_id_to_name()
topic_id2name = dict(zip(get_topics_df()["topic_id"], get_topics_df()["topic_name"]))

ptn_all = _load_ptn_summary()
base_rows = ptn_all[(ptn_all["subset_id"] == "all") & (ptn_all["conf_state"] == CONF_STATE)]

# =============================================================================
# Resolve the target partner: session_state (Collaboration Overview's row click) ->
# query_params (deep-link/testable) -> a manual search picker (page must work standalone).
# =============================================================================
partner_id = st.session_state.get("nav_partner_id") or st.query_params.get("partner_id")
known_ids = set(base_rows["partner_id"])

if not partner_id or partner_id not in known_ids:
    st.page_link("pages/8_🤝_Collaborations.py", label="← Retour à Collaborations")
    st.markdown("Aucun partenaire sélectionné. Ouvrez-en un depuis **Collaborations**, ou cherchez ici :")
    pick_query = st.text_input("Rechercher un partenaire", "", key="drilldown_pick_query").strip()
    if pick_query:
        matches = base_rows[base_rows["display_name"].str.contains(pick_query, case=False, na=False, regex=False)]
        matches = matches.sort_values("co_works_full", ascending=False).head(25)
        if matches.empty:
            st.warning(NO_MATCH_MSG_FR)
        else:
            options = {
                f'{r["display_name"]} ({fr_int(int(r["co_works_full"]))} co-pubs)': r["partner_id"]
                for _, r in matches.iterrows()
            }
            picked_label = st.selectbox("Résultats", options=list(options.keys()), key="drilldown_pick_select")
            if st.button("Ouvrir la fiche", key="drilldown_pick_open"):
                chosen = options[picked_label]
                st.session_state["nav_partner_id"] = chosen
                st.query_params["partner_id"] = chosen
                st.rerun()
    st.stop()

st.query_params["partner_id"] = partner_id
if st.session_state.get("v2_last_partner") != partner_id:
    # Reset drill/zoom state on a partner switch: a stale field/subfield could belong to a
    # different pair and simply render empty otherwise (confusing, not honest-empty).
    st.session_state["v2_drill_field"] = None
    st.session_state["v2_drill_subfield"] = None
    st.session_state["v2_selected_topic"] = None
    st.session_state["v2_zoom_field"] = None
    st.session_state["v2_zoom_subfield"] = None
    st.session_state["v2_portage_expanded"] = False
    st.session_state["v2_last_partner"] = partner_id

partner_row = base_rows[base_rows["partner_id"] == partner_id].iloc[0]
CO_COL = controls.xa(base_rows, "co_works_full")

# Pass-7a (P-ZOOM): HOISTED above the header -- both are needed before section 3 now
# (partner_works for the header's phares-KPI deep link; partner_topics for the NEW
# balance-bars/topic-planes sections, which render before the old drill section).
partner_works = lazy.read_keyed(PTN_WORKS_PATH, "partner_id", partner_id)
partner_topics = lazy.read_keyed(PTN_TOPICS_PATH, "partner_id", partner_id)

st.page_link("pages/8_🤝_Collaborations.py", label="← Retour à Collaborations")

# Workbook-feeding placeholders (deliverable 9): always bound so the page_workbook call
# at the end of the page never NameErrors on a thin partner whose sections render an
# honest-empty state instead of a frame.
bb_frame = pd.DataFrame()
imp_frame = pd.DataFrame()
fr_frame = pd.DataFrame()
rc_frame = pd.DataFrame()
_workbook_thematic_df = pd.DataFrame()

# =============================================================================
# Section 1 -- header : identité, KPI (+ NEW publications phares), autres périmètres
# (#40), momentum quantifié (#43)
# =============================================================================
mom_facts_all = _load_ptn_mom_facts()
_mf_rows = mom_facts_all[mom_facts_all["conf_state"] == CONF_STATE]
mf_row = _mf_rows.iloc[0] if not _mf_rows.empty else None

# FIX-1 D8: the KPI count and the id-list the arrow opens must read the SAME filtered
# works set -- conference toggle (ptn_summary is conf_state-keyed, base_rows/partner_row
# already reflect it) AND the artifact toggle (n_phares_xa vs n_phares -- ptn_summary
# carries both, matching every neighbouring KPI's own controls.xa convention).
n_phares_val = partner_row.get("n_phares_xa") if artifact_on else partner_row.get("n_phares")
_phares_work_ids = PF.phares_work_ids(partner_works, include_conference=include_conference, artifact_on=artifact_on)
phares_url_val, phares_is_proxy = links.phares_url(_phares_work_ids, partner_id)

with st.container(border=True):
    tag = f" · **{ranked.CONSORTIUM_BADGE_LABEL}**" if bool(partner_row["consortium_member"]) else ""
    st.markdown(f"## {partner_row['display_name']}{tag}")
    country_code = partner_row.get("country_code")
    has_country = pd.notna(country_code) and str(country_code).strip() not in ("", "—")
    country_fr = country_label(country_code) if has_country else "—"
    st.caption(
        f"{country_fr} · "
        f"{partner_row['type_openalex'] if pd.notna(partner_row['type_openalex']) else '—'} · "
        f"{fr_int(int(partner_row['n_ul_labs']))} laboratoire(s) UL impliqué(s) · "
        f"décompte fractionnel {_fr_float(partner_row.get('co_works_fractional'), 1)}"
    )
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Co-publications", fr_int(int(partner_row[CO_COL])), help=_kpi_help("zoom_kpi_copubs"))
    k2.metric("Part UL", fr_pct(float(partner_row[controls.xa(base_rows, 'share_ul')]) * 100),
              help=_kpi_help("zoom_kpi_share_ul"))
    # share_p (42b pull) is populated on this page's own base_rows (subset_id='all' always
    # here) whenever CONF_STATE=='all' -- render the value + its denominator when present,
    # an honest em-dash + reason when NULL by design (no_conf).
    _share_p = partner_row.get("share_p")
    if pd.notna(_share_p):
        _denom = int(partner_row["partner_total_windowed"])
        k3.metric("Part partenaire", fr_pct(float(_share_p) * 100), delta=f"/ {fr_int(_denom)}",
                  delta_color="off", help=_kpi_help("zoom_kpi_share_p"))
    else:
        k3.metric("Part partenaire", "—", help=_kpi_help("zoom_kpi_share_p"))
    k4.metric("FWCI médian (réf. France)", _fr_float(partner_row[controls.xa(base_rows, "fwci_fr_median")]),
              help=_kpi_help("zoom_kpi_fwci"))
    # Header KPI identity tile -- deliberately NOT gated by the I-SITE overlay toggle (it is
    # a single-value identity fact about this ONE partner, not a decomposed volume bar).
    k5.metric("Co-pubs ISITE", fr_int(int(partner_row['isite_co_works'])), fr_pct(float(partner_row['isite_share']) * 100),
              help=_kpi_help("zoom_kpi_isite"))
    with k6:
        st.metric("Publications phares",
                  ("—" if pd.isna(n_phares_val) else fr_int(int(n_phares_val))),
                  help=_kpi_help("zoom_kpi_phares"))
        if phares_url_val:
            links.link_icon(phares_url_val, tooltip=links.LINK_TOOLTIP_FR)
    if pd.isna(_share_p):
        st.caption(SHARE_P_NULL_BY_DESIGN_FR)
    if phares_url_val and phares_is_proxy:
        st.caption(_caption("PHARES_PROXY"))

    st.divider()

    # -- #40: the remaining share families (ptn_denominators), always on the (all, all)
    # basis -- the same fixed reference ptn_denominators itself is derived from.
    st.markdown("##### Poids du partenaire dans d'autres périmètres")
    st.markdown(
        "**Comment lire.** Les parts ci-dessous rapportent les co-publications avec ce "
        "partenaire à des périmètres différents de ceux des indicateurs ci-dessus : le "
        "corpus international entier de l'UL, le corpus de l'UL avec le seul pays du "
        "partenaire, ou le corpus français de l'UL hors consortium I-SITE. Chacune répond "
        "à une question de comparaison différente ; aucune ne remplace « Part UL » ou "
        "« Part partenaire » ci-dessus."
    )
    denom_all = _load_ptn_denominators()
    den_rows = denom_all[denom_all["partner_id"] == partner_id]
    den_row = den_rows.iloc[0] if not den_rows.empty else None
    if den_row is None:
        st.caption("—")
    else:
        is_france = has_country and str(country_code).strip() == "FR"
        is_consortium = bool(partner_row.get("consortium_member"))
        tiles: list[tuple[str, object]] = [
            ("Part du corpus total de l'UL", den_row.get("share_of_ul_corpus")),
        ]
        if is_france:
            hors_site_val = None if is_consortium else den_row.get("share_of_ul_france_copubs_hors_site")
            tiles.append((
                "Part des co-publications françaises de l'UL, hors consortium I-SITE",
                hors_site_val,
            ))
        elif has_country:
            tiles.append(("Part des co-publications internationales de l'UL", den_row.get("share_of_ul_intl_copubs")))
            tiles.append((f"Part des co-publications de l'UL avec {country_fr}", den_row.get("share_of_ul_country_copubs")))
        cols_d = st.columns(len(tiles))
        for col, (label, val) in zip(cols_d, tiles):
            col.metric(label, fr_pct(float(val) * 100) if val is not None and pd.notna(val) else "—")
        if is_france and is_consortium:
            st.caption(
                ":grey[Signataire du consortium I-SITE : exclu par construction du "
                "dénominateur « hors consortium ».]"
            )
        st.caption(
            ":grey[Calculé sur le corpus entier, tous types de publication confondus, "
            "quel que soit l'état du filtre « papiers de conférence » ci-contre.]"
        )
    st.markdown(
        "**Pourquoi cet indicateur.** Un partenaire peut peser peu dans le corpus entier "
        "de l'UL tout en pesant beaucoup parmi les partenaires de son propre pays, ou "
        "l'inverse : ces parts situent la relation dans le bon groupe de comparaison "
        "plutôt que dans un seul totalisateur."
    )

    st.divider()

    # -- #43: momentum, quantified (VIZ_SPEC_pass6 §8.3) -- unchanged this pass --
    st.markdown("##### Momentum")
    mom_text, mom_color, _glyph = momentum_display(partner_row, mf_row if mf_row is not None else {})
    st.markdown(
        f'<span style="font-size:22px;font-weight:600;color:{mom_color}">{mom_text}</span>',
        unsafe_allow_html=True,
    )
    _w1s, _w2s = partner_row.get("mom_w1_share"), partner_row.get("mom_w2_share")
    if mf_row is not None and pd.notna(_w1s) and pd.notna(_w2s):
        w1_lbl = str(mf_row.get("mom_w1_label", "—"))
        w2_lbl = str(mf_row.get("mom_w2_label", "—"))
        w1_pct, w2_pct = fr_pct(float(_w1s) * 100), fr_pct(float(_w2s) * 100)
        _arrow_raw = str(partner_row.get("mom_count_arrow") or "")
        try:
            _c1, _c2 = _arrow_raw.split("->")
            c1c2 = f"{fr_int(int(float(_c1)))} → {fr_int(int(float(_c2)))}"
        except (ValueError, TypeError):
            c1c2 = "—"
        _p = partner_row.get("mom_p_value")
        p_txt = _fr_float(_p, 3)
        sig = mf_row.get("significance_p")
        sig_txt = _fr_float(sig, 2)
        st.markdown(
            f'<div style="font-size:13px;color:{TEXT_SECONDARY}">'
            f'Part du collaboratif UL : {w1_pct} ({w1_lbl}) → {w2_pct} ({w2_lbl})<br>'
            f'Co-publications : {c1c2} &nbsp;&nbsp;&nbsp; Signification : p = {p_txt} '
            f'(seuil {sig_txt})</div>',
            unsafe_allow_html=True,
        )
    st.caption(MOMENTUM_METHOD_HELP_FR)

st.markdown("---")

# =============================================================================
# Section 2 -- volume panel: yearly bars (grouped I-SITE overlay) + share-of-UL-collab
# sparkline (P-ZOOM #2 -- replaces the pass-6 two-window comparison bar)
# =============================================================================
st.markdown("### Volume")
yr = _load_ptn_yearly()
yr_p = yr[(yr["partner_id"] == partner_id) & (yr["conf_state"] == CONF_STATE)].sort_values("year")

_yscope = _yearly_scope(partner_works, include_conference, artifact_on)
_year_totals, _year_isite = [], []
for _y in YEARS:
    _yr_sc = _yscope[_yscope["year"] == _y]
    _year_totals.append(float(len(_yr_sc)))
    _year_isite.append(float(_yr_sc["in_isite"].fillna(False).sum()))

col_bars, col_spark = st.columns(2)
with col_bars:
    st.markdown("#### Volume annuel")
    fig_bars = overlay.overlay_grouped_bars(
        groups=[str(y) for y in YEARS], series=["n"], labels={"n": "Co-publications"},
        colors={"n": UL_COLOR}, totals={"n": _year_totals}, isite={"n": _year_isite},
        isite_on=isite_overlay_on,
    )
    _share_by_year = dict(zip(yr_p["year"], yr_p[controls.xa(yr_p, "share_of_ul_collab")]))
    _labels_zy = copy_fr.HOVER_LABELS["zoom_yearly"]["default"]
    _yearly_hover = []
    for _i, _y in enumerate(YEARS):
        _share_v = _share_by_year.get(_y)
        _vals = (str(_y), hv.fmt_int(_year_totals[_i]),
                 (hv.fmt_int(_year_isite[_i]) if isite_overlay_on else None),
                 (None if _share_v is None or pd.isna(_share_v) else hv.fmt_pct(float(_share_v) * 100.0)))
        _yearly_hover.append(hv.hover_lines(list(zip(_labels_zy, _vals))))
    for _trace in fig_bars.data:
        _trace.customdata = _yearly_hover
        _trace.hovertemplate = hv.HOVERTEMPLATE
    fig_bars.update_layout(height=260, margin=dict(t=20, l=40, r=20, b=40),
                            yaxis_title="Co-publications", xaxis_title="", showlegend=isite_overlay_on)
    st.plotly_chart(fig_bars, width="stretch")
    reading.reading_line("zoom_yearly", partenaire=partner_row["display_name"])
with col_spark:
    st.markdown("#### Part du collaboratif annuel de l'UL")
    if len(yr_p) >= 5:
        st.plotly_chart(_share_spark_fig(yr_p), width="stretch")
        reading.reading_line("zoom_share_spark", partenaire=partner_row["display_name"])
    else:
        st.caption("—")
        st.caption(":grey[Trop peu d'années observées pour une évolution lisible.]")
st.markdown(
    "**Pourquoi cet indicateur.** Le volume dit si la relation grandit dans l'absolu ; le "
    "poids relatif dit si elle grandit plus vite ou plus lentement que l'ensemble des "
    "partenariats de l'UL. Un partenaire peut publier davantage chaque année tout en "
    "perdant du poids si le collaboratif de l'UL grandit plus vite encore."
)
exports.attach_download(st, yr_p, "v2-partner-drilldown", "yearly", _EXPORT_STATE, entity=("p", partner_id))

st.markdown("---")

# =============================================================================
# Section 3 -- NEW Équilibre de la relation (balance bars, P10)
# =============================================================================
st.markdown("### Équilibre de la relation")

fld_all = _load_ptn_fields()
fld_p = fld_all[(fld_all["partner_id"] == partner_id) & (fld_all["conf_state"] == CONF_STATE)]


def _balance_frame(mode: str, level: str):
    """Thin page-side wrapper: FIX-1 D9 moved the real logic to
    lib/partner_frames.py::build_balance_frame (pure pandas, independently testable) --
    this only supplies the page's already-loaded frames/context."""
    return PF.build_balance_frame(
        fld_p, _load_thematic_overview(), partner_topics, get_topics_df(), partner_works,
        mode=mode, level=level, partner_id=partner_id, partner_name=partner_row["display_name"],
        conf_state=CONF_STATE, include_conference=include_conference, artifact_on=artifact_on,
        partner_total_windowed=partner_row.get("partner_total_windowed"),
        field_id2name=field_id2name, subfield_id2name=subfield_id2name,
    )


bb_c1, bb_c2 = st.columns(2)
with bb_c1:
    bb_level = _pair_level_control("v2_bb_level_radio")
with bb_c2:
    bb_mode = st.radio(
        "Mode", options=list(copy_fr.LABELS["BALANCE_MODES"].keys()),
        format_func=lambda k: copy_fr.LABELS["BALANCE_MODES"][k],
        horizontal=True, key="v2_balance_mode",
    )
bb_level_word = "champ" if bb_level == "field" else "sous_champ"
bb_frame, bb_n_hidden = _balance_frame(bb_mode, bb_level)
reading.reading_line("zoom_balance_bars", f"{bb_mode}|{bb_level_word}",
                      window=window_label(), partenaire=partner_row["display_name"],
                      n_hidden=fr_int(bb_n_hidden))
if bb_frame.empty:
    st.info(f"Aucun {'champ' if bb_level == 'field' else 'sous-champ'} mesuré pour ce partenaire.")
else:
    fig_bb = fig_cache.cached_figure(
        "zoom_balance_bars", (partner_id, CONF_STATE, bb_mode, bb_level),
        lambda: C.balance_bars(bb_frame, mode=bb_mode, level=bb_level_word, partner_name=partner_row["display_name"]),
    )
    # B8/D15: the mirror has no usable 390 px state (VIZ_SPEC_pass7 §5.7; P7_ST NOTE 5:
    # "~110 px of plot for two segments") -- below, a CSS media query (not a server-side
    # width guess Streamlit cannot make) swaps the mirror for its table companion, which
    # renders the SAME frame (no recompute): both live in the DOM, only one is visible.
    st.markdown(
        "<style>"
        "@media (max-width: 640px) { .st-key-zoom_mirror { display: none; } }"
        "@media (min-width: 641px) { .st-key-zoom_mirror_table { display: none; } }"
        "</style>",
        unsafe_allow_html=True,
    )
    with st.container(key="zoom_mirror"):
        st.plotly_chart(fig_bb, width="stretch")
    # FIX-1 D1: vol_partner_only now reads ptn_fields.partner_node_total DIRECTLY (exact,
    # from the 42b blob) -- it is no longer derived from a share, so DERIVED_PARTNER_VOLUME
    # no longer applies and is not shown. A NULL/absent partner_node_total row still shows
    # UL-only + joint with a dash on the partner side (disclosed, never a wrong number).
    if bb_n_hidden:
        # FIX-1 D4: bb_n_hidden is now EXACTLY the NULL-partner_node_total count among the
        # already-capped top-30 set (never the "beyond the cut" count) -- SUBFIELD_NULL_SHARE
        # fires whenever that count is nonzero, at EITHER level (a field row can be NULL too).
        st.caption(_caption("SUBFIELD_NULL_SHARE"))
    if bb_mode == "phares" and "phares_proxy" in bb_frame.columns and bool(bb_frame["phares_proxy"].any()):
        st.caption(_caption("PHARES_PROXY"))
    _bb_cols = {"node_name": "Nom", "vol_ul_only": "UL seule", "vol_joint": "Conjoint",
                "vol_partner_only": "Partenaire seul (dérivé)", "fwci_ul": "FWCI UL",
                "fwci_joint": "FWCI conjoint", "n_phares_ul": "Phares UL",
                "n_phares_joint": "Phares conjoints", "link_label": "Co-pubs"}
    _bb_display = bb_frame[[c for c in _bb_cols if c in bb_frame.columns]].rename(columns=_bb_cols)
    # Narrow-viewport default (<= 640 px, CSS-gated above): the same frame, always in the
    # DOM, no click needed. Above 640 px it is CSS-hidden and the collapsed expander below
    # (unchanged wide-screen behaviour) is the reading path.
    with st.container(key="zoom_mirror_table"):
        st.dataframe(_bb_display, hide_index=True, width="stretch")
    with st.expander("Voir en tableau (lecture recommandée sur petit écran)"):
        st.dataframe(_bb_display, hide_index=True, width="stretch")
    exports.attach_download(st, bb_frame.drop(columns=["hover", "url", "phares_proxy"], errors="ignore"),
                             "v2-partner-drilldown", "balance", _EXPORT_STATE, entity=("p", partner_id))

st.markdown("---")

# =============================================================================
# Section 4 -- NEW Plans thématiques de la relation (topic planes, P9)
# =============================================================================
st.markdown("### Plans thématiques de la relation")


def _cell_frame() -> pd.DataFrame:
    """Thin wrapper: FIX-1 D6/D9 moved this to lib/partner_frames.py::build_cell_frame,
    which reads the LATEST-BIN `frontier` component from dim_frontier_components (never
    ptn_topics.frontier_score_std, the all-period composite the manager ruled OFF page 9)."""
    return PF.build_cell_frame(partner_topics, get_topics_df(), _load_frontier_components(),
                                conf_state=CONF_STATE, floor=PLANE_FLOOR)


def _plane_impact_frame(cells: pd.DataFrame, mode: str, n: int):
    return PF.build_plane_impact_frame(cells, mode, n)


def _plane_frontier_frame(cells: pd.DataFrame, mode: str, n: int):
    return PF.build_plane_frontier_frame(cells, mode, n)


plane_cells = _cell_frame()
if len(plane_cells) < PLANE_FLOOR:
    st.caption(_caption("THIN_PARTNER"))
else:
    pl_c1, pl_c2 = st.columns([2, 1])
    with pl_c1:
        plane_mode = st.radio(
            "Topics affichés", options=list(copy_fr.LABELS["PLANE_SELECT"].keys()),
            format_func=lambda k: copy_fr.LABELS["PLANE_SELECT"][k],
            horizontal=True, key="v2_plane_select",
        )
    with pl_c2:
        plane_n = st.slider("N", min_value=10, max_value=50, value=PLANE_N_DEFAULT, step=5, key="v2_plane_n")

    imp_frame, imp_dropped = _plane_impact_frame(plane_cells, plane_mode, plane_n)
    fr_frame, fr_dropped = _plane_frontier_frame(plane_cells, plane_mode, plane_n)

    p_col1, p_col2 = st.columns(2)
    with p_col1:
        st.markdown("#### Volume × impact")
        if imp_frame.empty:
            st.caption("—")
        else:
            fig_imp = fig_cache.cached_figure(
                "zoom_plane_impact", (partner_id, CONF_STATE, plane_mode, plane_n),
                lambda: C.fig_plane_impact(imp_frame),
            )
            st.plotly_chart(fig_imp, width="stretch")
        reading.reading_line("zoom_plane_impact", plane_mode)
        if imp_dropped:
            st.caption(_caption("PLANE_UNSCORED"))
    with p_col2:
        st.markdown("#### Expansion × accélération")
        if fr_frame.empty:
            st.caption("—")
        else:
            fig_frt = fig_cache.cached_figure(
                "zoom_plane_frontier", (partner_id, CONF_STATE, plane_mode, plane_n),
                lambda: C.fig_plane_frontier(fr_frame),
            )
            st.plotly_chart(fig_frt, width="stretch")
        # FIX-1 D7: bin labels read live from the table, never typed as a page constant.
        _bin_last, _bin_prev = PF.latest_and_previous_bin_labels(_load_frontier_components())
        reading.reading_line("zoom_plane_frontier", plane_mode, bin_prev=_bin_prev, bin_last=_bin_last)
        if fr_dropped:
            st.caption(_caption("PLANE_UNSCORED"))
    st.caption(_caption("FRONTIER_VINTAGES"))
    exports.attach_download(st, imp_frame.drop(columns=["hover"], errors="ignore"),
                             "v2-partner-drilldown", "planes", _EXPORT_STATE, entity=("p", partner_id))

st.markdown("---")

# =============================================================================
# Section 5 -- Profil thématique : scoped-descent field -> subfield -> topic (I11)
# (existing pass-6 mechanics preserved verbatim -- session-state keys are exercised
# directly by tests/test_page_pf.py's cross-page navigation smoke test; only hover +
# reading-line + S4 additions land here)
# =============================================================================
st.markdown("### Profil thématique de la relation")
st.markdown(
    "**Comment lire.** Une ligne par champ, puis par sous-champ, puis par topic : la "
    "descente est cadrée, le fil d'Ariane remonte. « % de la paire » rapporte au total de "
    "la relation, « % de l'UL » situe le même champ dans le portefeuille lorrain entier : "
    "un champ peut peser beaucoup dans la relation et peu dans le portefeuille, et c'est "
    "le cas le plus intéressant."
)

drilled_field = st.session_state.get("v2_drill_field")
drilled_subfield = st.session_state.get("v2_drill_subfield")

crumbs = ["Champs"]
if drilled_field is not None:
    crumbs.append(field_id2name.get(int(drilled_field), str(drilled_field)))
if drilled_subfield is not None:
    crumbs.append(subfield_id2name.get(int(drilled_subfield), str(drilled_subfield)))
bc_col, up_col = st.columns([5, 1])
bc_col.markdown(f"**Niveau : {' ▸ '.join(crumbs)}**")
if drilled_field is not None:
    if up_col.button("⬆️ Remonter", key="v2_drill_up", type="primary", width="stretch"):
        if drilled_subfield is not None:
            st.session_state["v2_drill_subfield"] = None
            st.session_state["v2_selected_topic"] = None
        else:
            st.session_state["v2_drill_field"] = None
        st.rerun()

if drilled_field is None:
    # -------------------------------------------------------------------- FIELD level
    fld_fields = fld_p[fld_p["node_level"] == "field"]
    if fld_fields.empty:
        st.info("Aucun champ thématique mesuré pour ce partenaire.")
    else:
        co_col_f = controls.xa(fld_fields, "co_works")
        rows = []
        for _, r in fld_fields.sort_values(co_col_f, ascending=False).iterrows():
            fid = int(r["node_id"])
            dom_name = domain_id2name.get(field_id2domain.get(fid), "Other")
            mom_txt = "—"
            if bool(r["mom_eligible_flag"]) and pd.notna(r["mom_class"]):
                mom_txt = _mom_chip(r["mom_class"])
            # baseline_partner_share (42b) is populated on the 'tous types' rows only;
            # NULL, never 0, on no_conf rows by design.
            _partner_share_field = r.get("baseline_partner_share")
            rows.append({
                "node_id": fid,
                "field_label": f'{DOMAIN_EMOJI.get(dom_name, DOMAIN_EMOJI["Other"])} {field_id2name.get(fid, str(fid))}',
                "domain_color": get_domain_color(field_id2domain.get(fid, -1)),
                "co_works": int(r[co_col_f]),
                "share_of_pair": round(float(r[controls.xa(fld_fields, "share_of_pair")]) * 100, 1),
                "baseline_ul_share": round(float(r[controls.xa(fld_fields, "baseline_ul_share")]) * 100, 1),
                "partner_share_text": (fr_pct(float(_partner_share_field) * 100) if pd.notna(_partner_share_field) else "—"),
                "mom_text": mom_txt,
                "co_works_isite": int(r["co_works_isite"]),
                "share_of_pair_isite": round(float(r["share_of_pair_isite"]) * 100, 1),
            })
        field_disp = pd.DataFrame(rows)
        _workbook_thematic_df = field_disp
        if CONF_STATE != "all":
            st.caption(FIELD_SHARE_P_NULL_FR)

        _hidden = ["node_id", "domain_color"]
        if not isite_overlay_on:
            _hidden += ["co_works_isite", "share_of_pair_isite"]
        _ref_labels = {
            "field_label": "Champ", "co_works": "Co-publications", "share_of_pair": "% de la paire",
            "baseline_ul_share": "% de l'UL (repère)", "partner_share_text": "% du partenaire",
            "mom_text": "Momentum", "co_works_isite": "Co-pubs I-SITE",
            "share_of_pair_isite": "Part I-SITE de la paire",
        }
        _progress = {
            "co_works": {"format": "%d", "max_value": int(field_disp["co_works"].max())},
            "share_of_pair": {"format": "%.1f%%", "max_value": 100},
            "baseline_ul_share": {"format": "%.1f%%", "max_value": 100},
        }
        if isite_overlay_on:
            _progress["share_of_pair_isite"] = {"format": "%.1f%%", "max_value": 100}

        # #43: the member-mask toggle has no meaning on a table of THEMATIC FIELDS (there
        # is no "site member" among them) -- has_members=False removes the dead control.
        visible_f = ranked.ranked_table(
            field_disp, key="v2_field", id_col="node_id", search_cols=["field_label"],
            has_members=False, progress_cols=_progress, mean_cols=_hidden, ref_labels=_ref_labels,
        )

        chart_f = visible_f.sort_values("co_works", ascending=False).head(FIELD_CHART_CAP).reset_index(drop=True)
        if not chart_f.empty:
            st.markdown("###### Volume par champ")
            # FIX-1 D10 (S-LENS A17): the registry declares zoom_field_companion "bars
            # (gutter)" -- migrated from overlay.overlay_bars to charts.bars_with_gutter.
            chart_f["hover"] = [
                hv.hover_lines(list(zip(copy_fr.HOVER_LABELS["zoom_field_companion"]["default"], (
                    r["field_label"], hv.fmt_int(r["co_works"]), hv.fmt_pct(r["share_of_pair"]),
                    hv.fmt_pct(r["baseline_ul_share"]), (None if r["partner_share_text"] == "—" else r["partner_share_text"]),
                    None, (None if r["mom_text"] == "—" else r["mom_text"]),
                ))))
                for _, r in chart_f.iterrows()
            ]
            fig_f = fig_cache.cached_figure(
                "zoom_field_companion", (partner_id, CONF_STATE, isite_overlay_on, len(chart_f)),
                lambda: C.bars_with_gutter(
                    chart_f, family="champ", label_col="field_label", value_col="co_works",
                    color=chart_f["domain_color"].tolist(), isite_col="co_works_isite", isite_on=isite_overlay_on,
                ),
            )
            st.plotly_chart(fig_f, width="stretch")
            reading.reading_line("zoom_field_companion")

        st.caption("▸ choisir un champ ci-dessous pour voir ses sous-champs.")
        _opts = {r["field_label"]: r["node_id"] for _, r in visible_f.iterrows()}
        if not visible_f.empty:
            nav1, nav2 = st.columns([4, 1])
            _pick = nav1.selectbox("Descendre dans un champ", options=list(_opts.keys()), key="v2_field_nav",
                                    label_visibility="collapsed", placeholder="Descendre dans un champ...")
            if nav2.button("⬇️ Descendre", key="v2_field_nav_go", type="primary", width="stretch") and _pick:
                st.session_state["v2_drill_field"] = int(_opts[_pick])
                st.rerun()

            zoomed_fid = _theme_zoom_control("un champ", _opts, "v2_zoom_field")
            if zoomed_fid is not None:
                zoomed_label = field_id2name.get(zoomed_fid, str(zoomed_fid))
                with st.container(border=True):
                    zc_close = st.columns([4, 1])[1]
                    st.caption(f"Zoom : {zoomed_label}")
                    _theme_zoom_chart(
                        partner_works, "primary_field_id", zoomed_fid, zoomed_label,
                        include_conference, artifact_on, isite_overlay_on,
                        color=get_domain_color(field_id2domain.get(zoomed_fid, -1)),
                    )
                    if zc_close.button("✕ Fermer", key="v2_zoom_field_close"):
                        st.session_state["v2_zoom_field"] = None
                        st.rerun()

        exports.attach_download(
            st, fld_fields, "v2-partner-drilldown", "thematic-field", _EXPORT_STATE, entity=("p", partner_id),
        )

elif drilled_subfield is None:
    # ----------------------------------------------------------------- SUBFIELD level
    field_name = field_id2name.get(int(drilled_field), str(drilled_field))
    st.markdown(f"#### Sous-champs de « {field_name} »")
    valid_subs = set(get_subfields_for_field(int(drilled_field)))
    sub_rows = fld_p[(fld_p["node_level"] == "subfield") & (fld_p["node_id"].astype(int).isin(valid_subs))]

    pw_field = partner_works[partner_works["primary_field_id"].astype(str) == str(drilled_field)]
    n_present = pw_field["primary_subfield_id"].dropna().astype(str).nunique()
    n_suppressed = max(0, n_present - len(sub_rows))
    if n_suppressed:
        st.caption(f":grey[+ {fr_int(n_suppressed)} sous-champ(s) sous le seuil (< {I11_SPARKLINE_FLOOR} co-publications), non affiché(s).]")

    if sub_rows.empty:
        st.info("Aucun sous-champ au-dessus du seuil pour ce champ.")
    else:
        co_col_s = controls.xa(sub_rows, "co_works")
        rows = []
        for _, r in sub_rows.sort_values(co_col_s, ascending=False).iterrows():
            sid = int(r["node_id"])
            lq = r[controls.xa(sub_rows, "lq_vs_ul")]
            rows.append({
                "node_id": sid,
                "subfield_label": subfield_id2name.get(sid, str(sid)),
                "subfield_color": get_subfield_color(sid),
                "co_works": int(r[co_col_s]),
                "share_of_pair": round(float(r[controls.xa(sub_rows, "share_of_pair")]) * 100, 1),
                "baseline_ul_share": round(float(r[controls.xa(sub_rows, "baseline_ul_share")]) * 100, 1),
                "lq_text": _fr_float(lq),
                "co_works_isite": int(r["co_works_isite"]),
                "share_of_pair_isite": round(float(r["share_of_pair_isite"]) * 100, 1),
            })
        sub_disp = pd.DataFrame(rows)
        _workbook_thematic_df = sub_disp

        _hidden = ["node_id", "subfield_color"]
        if not isite_overlay_on:
            _hidden += ["co_works_isite", "share_of_pair_isite"]
        _ref_labels = {
            "subfield_label": "Sous-champ", "co_works": "Co-publications", "share_of_pair": "% de la paire",
            "baseline_ul_share": "% de l'UL (repère)", "lq_text": "LQ vs UL",
            "co_works_isite": "Co-pubs I-SITE", "share_of_pair_isite": "Part I-SITE de la paire",
        }
        _progress = {
            "co_works": {"format": "%d", "max_value": int(sub_disp["co_works"].max())},
            "share_of_pair": {"format": "%.1f%%", "max_value": 100},
            "baseline_ul_share": {"format": "%.1f%%", "max_value": 100},
        }
        if isite_overlay_on:
            _progress["share_of_pair_isite"] = {"format": "%.1f%%", "max_value": 100}

        visible_s = ranked.ranked_table(
            sub_disp, key="v2_subfield", id_col="node_id", search_cols=["subfield_label"],
            has_members=False, progress_cols=_progress, mean_cols=_hidden, ref_labels=_ref_labels,
        )

        chart_s = visible_s.sort_values("co_works", ascending=False).head(SUBFIELD_CHART_CAP).reset_index(drop=True)
        if not chart_s.empty:
            st.markdown("###### Volume par sous-champ")
            # FIX-1 D10 (S-LENS A17): migrated to charts.bars_with_gutter (was overlay_bars).
            chart_s["hover"] = [
                hv.hover_lines(list(zip(copy_fr.HOVER_LABELS["zoom_subfield_companion"]["default"], (
                    r["subfield_label"], field_name, hv.fmt_int(r["co_works"]), hv.fmt_pct(r["share_of_pair"]),
                    hv.fmt_pct(r["baseline_ul_share"]), None,
                    (None if r["mom_text"] == "—" else r["mom_text"]) if "mom_text" in r else None,
                ))))
                for _, r in chart_s.iterrows()
            ]
            fig_s = fig_cache.cached_figure(
                "zoom_subfield_companion", (partner_id, CONF_STATE, isite_overlay_on, drilled_field, len(chart_s)),
                lambda: C.bars_with_gutter(
                    chart_s, family="sous_champ", label_col="subfield_label", value_col="co_works",
                    color=chart_s["subfield_color"].tolist(), isite_col="co_works_isite", isite_on=isite_overlay_on,
                ),
            )
            st.plotly_chart(fig_s, width="stretch")
            reading.reading_line("zoom_subfield_companion")

        st.caption("▸ choisir un sous-champ ci-dessous pour descendre jusqu'aux topics.")
        _opts = {r["subfield_label"]: r["node_id"] for _, r in visible_s.iterrows()}
        if not visible_s.empty:
            nav1, nav2 = st.columns([4, 1])
            _pick = nav1.selectbox("Descendre dans un sous-champ", options=list(_opts.keys()), key="v2_subfield_nav",
                                    label_visibility="collapsed", placeholder="Descendre dans un sous-champ...")
            if nav2.button("⬇️ Descendre", key="v2_subfield_nav_go", type="primary", width="stretch") and _pick:
                st.session_state["v2_drill_subfield"] = int(_opts[_pick])
                st.session_state["v2_selected_topic"] = None
                st.rerun()

            zoomed_sid = _theme_zoom_control("un sous-champ", _opts, "v2_zoom_subfield")
            if zoomed_sid is not None:
                zoomed_label = subfield_id2name.get(zoomed_sid, str(zoomed_sid))
                with st.container(border=True):
                    zc_close = st.columns([4, 1])[1]
                    st.caption(f"Zoom : {zoomed_label}")
                    _theme_zoom_chart(
                        partner_works, "primary_subfield_id", zoomed_sid, zoomed_label,
                        include_conference, artifact_on, isite_overlay_on,
                        color=get_subfield_color(zoomed_sid),
                    )
                    if zc_close.button("✕ Fermer", key="v2_zoom_subfield_close"):
                        st.session_state["v2_zoom_subfield"] = None
                        st.rerun()

        exports.attach_download(
            st, sub_rows, "v2-partner-drilldown", "thematic-subfield", _EXPORT_STATE,
            entity=("p", partner_id), node=("f", drilled_field),
        )

else:
    # -------------------------------------------------------------------- TOPIC level (I11)
    sub_name = subfield_id2name.get(int(drilled_subfield), str(drilled_subfield))
    st.markdown(f"#### Topics de « {sub_name} »")
    if isite_overlay_on:
        st.caption(TOPIC_ISITE_NA_FR)

    # ptn_topics is conf-keyed (partner x topic x year x conf_state) -- filter on the
    # ACTIVE conf_state, same session key as every other table on this page. `partner_topics`
    # itself is the hoisted, page-top lazy read (shared with the topic-planes section).
    sub_topics = partner_topics[
        (partner_topics["subfield_id"].astype(str) == str(drilled_subfield))
        & (partner_topics["conf_state"] == CONF_STATE)
    ].copy()

    if sub_topics.empty:
        st.info("Aucun topic mesuré pour ce sous-champ x partenaire.")
    else:
        vol_col = "co_works_xa" if artifact_on else "co_works"
        agg = sub_topics.groupby("topic_id", observed=True).agg(
            co_works=("co_works", "sum"), co_works_xa=("co_works_xa", "sum"),
            fwci_fr_median_cell=("fwci_fr_median_cell", "first"),
            frontier_score_std=("frontier_score_std", "first"),
            artifact_flag=("artifact_flag", "first"),
            delta_value=("delta_value", "first"), delta_flag=("delta_flag", "first"),
        ).reset_index()

        n_present_topics = sub_topics["topic_id"].nunique()
        agg_shown = agg[agg[vol_col] >= I11_SPARKLINE_FLOOR].copy()
        n_suppressed = n_present_topics - len(agg_shown)
        if n_suppressed > 0:
            st.caption(f":grey[+ {fr_int(n_suppressed)} topic(s) sous le seuil (< {I11_SPARKLINE_FLOOR} co-publications), non affiché(s).]")

        if agg_shown.empty:
            st.info(f"Aucun topic au-dessus du seuil de {I11_SPARKLINE_FLOOR} co-publications pour ce sous-champ.")
        else:
            def _yearly_series(tid) -> list[float]:
                s = sub_topics.loc[sub_topics["topic_id"] == tid].set_index("year")[vol_col]
                return [float(s.get(y, 0)) for y in YEARS]

            agg_shown = agg_shown.assign(topic_name=agg_shown["topic_id"].map(topic_id2name)).sort_values(
                vol_col, ascending=False,
            )
            _workbook_thematic_df = agg_shown

            # #43: the topic search box is removed here (useless below the ranked_table()
            # N>=50 threshold) -- lib.ranked's PURE depth layer is kept (afficher plus).
            topic_expanded = st.session_state.get("v2_topic_expanded", False)
            agg_view = ranked.depth_slice(agg_shown, expanded=topic_expanded, default_n=10)

            rows = []
            for _, r in agg_view.iterrows():
                delta_txt = "—"
                if pd.notna(r["delta_value"]):
                    dv = float(r["delta_value"])
                    arrow = "↑" if dv > 1 else ("↓" if dv < 1 else "→")
                    sig = "" if bool(r["delta_flag"]) else " (ns)"
                    delta_txt = f"{arrow} x{_fr_float(dv)}{sig}"
                rows.append({
                    "Topic": r["topic_name"],
                    "_topic_id": r["topic_id"],
                    "Volume": int(r[vol_col]),
                    "Tendance": _yearly_series(r["topic_id"]),
                    "Δ (2 fenêtres)": delta_txt,
                    "FWCI médian (réf. France)": _fr_float(r["fwci_fr_median_cell"]),
                    "Frontière (std.)": _fr_float(r["frontier_score_std"]),
                    "Réf.": "†" if bool(r["artifact_flag"]) else "",
                })
            topic_disp = pd.DataFrame(rows)

            column_config = {
                "Volume": st.column_config.ProgressColumn(
                    "Volume", min_value=0, max_value=int(topic_disp["Volume"].max()), format="%d"),
                "Tendance": st.column_config.LineChartColumn(f"Tendance ({window_label()})", width="small"),
                "Δ (2 fenêtres)": st.column_config.TextColumn(
                    "Δ (2 fenêtres)",
                    help="Écart entre deux fenêtres, calculé uniquement pour les cellules ≥20 co-publications."),
                "Réf.": controls.marker_dagger_column_config(),
            }
            _deferred = ["Δ (2 fenêtres)", "FWCI médian (réf. France)"]
            if artifact_on:
                column_config = controls.grey_deferred(column_config, _deferred)

            event_t = st.dataframe(
                topic_disp.drop(columns="_topic_id"), hide_index=True, width="stretch",
                key="v2_topic_tbl", on_select="rerun", selection_mode="single-row",
                column_config=column_config,
            )
            if len(agg_shown) > 10 and not topic_expanded:
                if st.button("afficher plus", key="v2_topic_more_btn"):
                    st.session_state["v2_topic_expanded"] = True
                    st.rerun()
            st.caption(
                "▸ cliquer un topic ouvre ses publications ci-dessous. L'écart entre "
                "fenêtres n'est calculé que pour les cellules ≥20 co-publications ; à ce "
                "grain, aucune classe de momentum n'est produite, le nombre de travaux par "
                "cellule étant trop faible pour qu'un test soit concluant."
            )
            sel = event_t.selection.rows if event_t is not None and event_t.selection else []
            if sel:
                st.session_state["v2_selected_topic"] = topic_disp.iloc[sel[0]]["_topic_id"]

            exports.attach_download(
                st, agg_shown, "v2-partner-drilldown", "thematic-topic", _EXPORT_STATE,
                entity=("p", partner_id), node=("sf", drilled_subfield),
            )

            sel_topic = st.session_state.get("v2_selected_topic")
            if sel_topic and sel_topic in agg_shown["topic_id"].values:
                topic_name = topic_id2name.get(sel_topic, sel_topic)
                with st.container(border=True):
                    st.caption(f"Zoom : {topic_name}")
                    _theme_zoom_chart(
                        partner_works, "primary_topic_id", sel_topic, topic_name,
                        include_conference, artifact_on, isite_overlay_on, color=NODE_BASE_COLOR,
                    )
                cell_pubs = partner_works[partner_works["primary_topic_id"].astype(str) == str(sel_topic)]
                with st.expander(f"Publications -- {topic_name} ({fr_int(len(cell_pubs))})", expanded=True):
                    if not include_conference:
                        cell_pubs = cell_pubs[~cell_pubs["is_conference"].fillna(False)]
                    if artifact_on:
                        cell_pubs = cell_pubs[~cell_pubs["artifact_flag"].fillna(False)]
                    tbl = pd.DataFrame({
                        "Année": cell_pubs["year"], "Titre": cell_pubs["title"],
                        "Type": cell_pubs["type"].astype(str), "Labo(s)": cell_pubs["labs_short"],
                        "FWCI (FR)": cell_pubs["fwci_fr"],
                        "ISITE": cell_pubs["in_isite"].map({True: "★", False: ""}),
                        "Réf.": controls.marker_dagger_column(cell_pubs),
                    })
                    st.dataframe(
                        tbl.sort_values("Année", ascending=False), hide_index=True, width="stretch",
                        column_config={"Réf.": controls.marker_dagger_column_config()},
                    )
                    exports.attach_download(
                        st, cell_pubs, "v2-partner-drilldown", "topic-cell-publications", _EXPORT_STATE,
                        entity=("p", partner_id), node=("t", sel_topic), works=True,
                        label="⬇ Publications (xlsx)",
                    )

st.markdown("---")

# =============================================================================
# Section 6 -- Réciprocité stratégique (item #46 -> BenchUp form, P-ZOOM #6): SAME level
# toggle as the balance bars; conf_state='all' FIXED (baseline_partner_share only exists
# there -- pre-pass-7 behaviour kept, per the brief's "existing caption ... kept").
# =============================================================================
st.markdown("### Réciprocité stratégique")


def _recip_frame(level: str):
    """Thin wrapper: FIX-1 D2/D9/D13 moved this to
    lib/partner_frames.py::build_recip_frame (x axis is now the partner's OWN portfolio
    weight of the node, `partner_node_total / partner_total_windowed` -- never the
    involvement share `baseline_partner_share`; the top-30 cap runs BEFORE the NULL drop,
    matching the balance bars' own order, D4/D13)."""
    return PF.build_recip_frame(
        fld_all, get_topics_df(), partner_id=partner_id, level=level,
        partner_name=partner_row["display_name"],
        partner_total_windowed=partner_row.get("partner_total_windowed"),
        field_id2name=field_id2name, subfield_id2name=subfield_id2name,
        field_id2domain=field_id2domain, domain_id2name=domain_id2name,
    )


rc_level = _pair_level_control("v2_recip_level_radio")
rc_level_word = "champ" if rc_level == "field" else "sous_champ"
rc_frame, rc_n_hidden = _recip_frame(rc_level)
reading.reading_line("zoom_reciprocity", rc_level_word, partenaire=partner_row["display_name"],
                      n_hidden=fr_int(rc_n_hidden))
if rc_frame.empty:
    st.info(
        f"Le poids de {partner_row['display_name']} dans son propre portefeuille n'est "
        "pas mesuré pour ce partenaire : aucune valeur n'est affichée plutôt qu'une "
        "valeur fabriquée."
    )
else:
    fig_rc = fig_cache.cached_figure(
        "zoom_reciprocity", (partner_id, rc_level),
        lambda: C.reciprocity_scatter(rc_frame, level=rc_level_word, partner_name=partner_row["display_name"]),
    )
    st.plotly_chart(fig_rc, width="stretch")
    if rc_n_hidden:
        _unit = "sous-champ(s)" if rc_level == "subfield" else "champ(s)"
        st.caption(f":grey[{fr_int(rc_n_hidden)} {_unit} dont le poids propre du partenaire n'est pas mesuré, écarté(s) de la vue.]")
    st.caption(
        ":grey[Calculé sur le corpus entier, tous types de publication confondus, quel que "
        "soit l'état du filtre « papiers de conférence » : le poids du partenaire dans son "
        "propre portefeuille n'est mesuré qu'à cet état.]"
    )
    exports.attach_download(
        st, rc_frame.drop(columns=["hover"], errors="ignore"),
        "v2-partner-drilldown", "reciprocity-fields", _EXPORT_STATE_EXEMPT, entity=("p", partner_id),
    )
st.markdown(
    "**Pourquoi cet indicateur.** Un champ peut occuper une place centrale dans le "
    "portefeuille de l'un des deux établissements et une place marginale dans celui de "
    "l'autre : ce croisement montre où les deux portefeuilles thématiques se recouvrent, "
    "et où ils divergent, indépendamment du volume de la relation elle-même."
)

st.markdown("---")

# =============================================================================
# Section 7 -- Portage interne de la relation (I7), top 20 / 10 par défaut (#45) --
# same pagination as pass-6, chart rebuilt on lib.charts.bars_with_gutter (P-ZOOM #7)
# =============================================================================
st.markdown("### Portage interne de la relation")
labs_all = _load_ptn_labs()
labs_p = labs_all[(labs_all["partner_id"] == partner_id) & (labs_all["conf_state"] == CONF_STATE)]
labs_p = labs_p.sort_values("co_works", ascending=False).reset_index(drop=True)

if labs_p.empty:
    st.info("Aucun laboratoire attribué pour ce partenaire (toutes les publications sont sans labo attribué).")
else:
    top20 = labs_p.head(PORTAGE_MAX_N)
    portage_expanded = st.session_state.get("v2_portage_expanded", False)
    shown = ranked.depth_slice(top20, expanded=portage_expanded, default_n=PORTAGE_DEFAULT_N)
    autres = labs_p[~labs_p["lab_name"].isin(shown["lab_name"])]

    port_rows = shown.copy()
    port_rows["is_other"] = False
    if not autres.empty:
        autres_row = pd.DataFrame([{
            "lab_name": f"Autres ({fr_int(len(autres))} laboratoires)",
            "co_works": float(autres["co_works"].sum()),
            "share_of_lab_attributed": float(autres["share_of_lab_attributed"].sum()),
            "is_other": True,
        }])
        port_rows = pd.concat([port_rows, autres_row], ignore_index=True)
    _labels_pt = copy_fr.HOVER_LABELS["zoom_portage"]["default"]
    port_rows["hover"] = [
        hv.hover_lines(list(zip(_labels_pt, (r["lab_name"], hv.fmt_int(r["co_works"]),
                                              hv.fmt_pct(r["share_of_lab_attributed"] * 100.0)))))
        for _, r in port_rows.iterrows()
    ]
    _colors = [NEUTRAL_GREY if o else UL_COLOR for o in port_rows["is_other"]]
    # family="labo_court": ptn_labs.lab_name carries ACRONYMS (IJL/CRAN/LORIA/...), not the
    # ul_labs full-name universe the wider "labo" column (335px) was measured on -- that
    # column alone would exceed a 390px viewport (P7_LIBA.md NOTE 7/8; "labo_court" landed
    # to fix exactly this, 90px, confirmed present in charts.FAMILIES before writing this).
    fig_portage = fig_cache.cached_figure(
        "zoom_portage", (partner_id, CONF_STATE, len(port_rows), bool(portage_expanded)),
        lambda: C.bars_with_gutter(port_rows, family="labo_court", label_col="lab_name",
                                   value_col="co_works", color=_colors),
    )
    st.plotly_chart(fig_portage, width="stretch")
    reading.reading_line("zoom_portage")
    if not portage_expanded and len(top20) > PORTAGE_DEFAULT_N:
        if st.button("afficher plus", key="v2_portage_more_btn"):
            st.session_state["v2_portage_expanded"] = True
            st.rerun()

    nolab_share = float(labs_p["nolab_share"].iloc[0])
    nolab_works = int(labs_p["nolab_works"].iloc[0])
    st.caption(
        f"{fr_int(nolab_works)} travaux ({fr_pct(nolab_share * 100)}) sans laboratoire "
        "attribué, exclus du rapport ci-dessus, jamais une colonne de palmarès."
    )
    if artifact_on:
        st.caption(":grey[Lecture structurelle : non recalculée sous le filtre « hors référentiel » actif.]")
    if isite_overlay_on:
        st.caption(PORTAGE_ISITE_NA_FR)
    exports.attach_download(
        st, labs_p, "v2-partner-drilldown", "portage", _EXPORT_STATE_EXEMPT, entity=("p", partner_id),
    )
st.markdown(
    "**Pourquoi cet indicateur.** Une relation portée par une seule unité et une relation "
    "partagée entre plusieurs ne se pilotent pas de la même façon, en particulier au "
    "moment d'un départ ou d'un renouvellement."
)

st.markdown("---")

# =============================================================================
# Section 8 -- NEW Export complet de la page (page workbook, P16)
# =============================================================================
st.markdown("### Export complet de la page")
_lecture = [
    ("Partenaire", str(partner_row["display_name"])),
    ("Identifiant OpenAlex", partner_id),
    ("Filtre conférence", "avec conférence" if include_conference else "hors conférence"),
    ("Filtre hors référentiel", "actif" if artifact_on else "inactif"),
    ("Surcouche I-SITE", "active" if isite_overlay_on else "inactive"),
    ("Niveau (équilibre / réciprocité)",
     copy_fr.LABELS["LEVEL_TOGGLE"][LEVEL_KEYS.index(st.session_state.get("v2_pair_level", "field"))]),
    ("Mode (équilibre)", copy_fr.LABELS["BALANCE_MODES"].get(st.session_state.get("v2_balance_mode", "volume"), "—")),
    ("Sélecteur (plans)", copy_fr.LABELS["PLANE_SELECT"].get(st.session_state.get("v2_plane_select", "volume"), "—")),
    ("N (plans)", str(st.session_state.get("v2_plane_n", PLANE_N_DEFAULT))),
    ("Instantané", SNAPSHOT_DATE),
    ("Fenêtre", window_label()),
    ("URL", links.copubs_url(partner_id)),
]
_wb_identity = pd.DataFrame([{
    "Partenaire": partner_row["display_name"], "Co-publications": int(partner_row[CO_COL]),
    "Part UL": float(partner_row[controls.xa(base_rows, "share_ul")]),
    "Part partenaire": (None if pd.isna(_share_p) else float(_share_p)),
    "FWCI médian": float(partner_row[controls.xa(base_rows, "fwci_fr_median")]),
    "Co-pubs ISITE": int(partner_row["isite_co_works"]),
    "Publications phares": (None if pd.isna(n_phares_val) else int(n_phares_val)),
}])
_wb_sheets = {
    "Identité et KPI": _wb_identity,
    "Volume annuel": yr_p,
    "Équilibre": bb_frame.drop(columns=["hover", "url"], errors="ignore"),
    "Plans": imp_frame.drop(columns=["hover"], errors="ignore"),
    "Profil thématique": _workbook_thematic_df,
    "Réciprocité": rc_frame.drop(columns=["hover"], errors="ignore"),
    "Portage": labs_p,
}
_wb_bytes, _wb_filename = exports.page_workbook(_wb_sheets, _lecture, view="v2-partner-drilldown")
st.download_button(
    copy_fr.LABELS["PAGE_WORKBOOK"], data=_wb_bytes, file_name=_wb_filename,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    key="v2_page_workbook_dl",
)

st.markdown("---")

# =============================================================================
# Section 9 -- publications : aperçu (5 lignes) + téléchargement lazy (item #44,
# unchanged this pass)
# =============================================================================
st.markdown("### Publications de la relation")
st.markdown(
    "**Comment lire.** La liste complète n'est pas affichée à l'écran : un aperçu des "
    "co-publications les plus récentes figure ci-dessous, et le fichier téléchargé porte "
    "l'ensemble, avec ses indicateurs de qualité (type, DOI, part I-SITE, ODD, statut au "
    "regard du référentiel thématique)."
)
n_total_works = len(partner_works)
st.caption(
    f"{fr_int(n_total_works)} co-publications avec ce partenaire, tous types et "
    "indicateurs confondus (le nombre affiché ailleurs sur cette page peut différer selon "
    "les filtres actifs)."
)
if n_total_works:
    _preview_cols = {
        "year": "Année", "title": "Titre", "type": "Type", "doi": "DOI",
        "in_isite": "ISITE", "sdg_tags": "ODD",
    }
    _have = [c for c in _preview_cols if c in partner_works.columns]
    preview = partner_works.sort_values("year", ascending=False)[_have].head(5).rename(columns=_preview_cols)
    if "ISITE" in preview.columns:
        preview["ISITE"] = preview["ISITE"].map({True: "★", False: ""})
    st.dataframe(preview, hide_index=True, width="stretch")
    st.caption(":grey[Aperçu des co-publications les plus récentes ; le fichier téléchargé porte la liste complète.]")

_dl_cols = [c for c in [
    "work_id", "year", "title", "doi", "type", "is_conference", "in_isite", "fwci_fr",
    "labs_short", "artifact_flag", "sdg_tags", "primary_field_id", "primary_subfield_id",
    "primary_topic_id",
] if n_total_works == 0 or c in partner_works.columns]
csv_bytes = lazy_slice_csv_bytes(PTN_WORKS_PATH, "partner_id", partner_id, columns=_dl_cols or None)
_dl_filename = f"partner-{partner_id}-publications.csv"  # not prose: a download filename, not scanned as such
st.download_button(
    "⬇ Télécharger les publications (CSV, avec indicateurs de qualité)",
    data=csv_bytes, file_name=_dl_filename, mime="text/csv",
    key="v2_download_all_pubs",
)
st.markdown(
    "**Pourquoi cet indicateur.** Le fichier téléchargé porte, pour chaque publication, "
    "les indicateurs qui permettent de la filtrer soi-même : type de document, DOI, part "
    "I-SITE, ODD attribués et statut au regard du référentiel thématique."
)

st.markdown("---")
st.caption(f"Instantané : {SNAPSHOT_DATE} · fenêtre {window_label()}.")
