"""
Partner Drilldown (V2) -- docs/indicator_plan_FINAL.md §3 (I1,I5,I6,I7,I8,I9,I11) + §6.3 +
§6.6 / docs/studio/VIZ_SPEC.md §2.6. NEW page, chain pass 3, Assembly Line stream P2.

Pass-6 stream P-ZP (2026-08-19): grill items #40-#46 (docs/NARRATIVE_CONTRACT_pass6.md
section 2.10, docs/studio/VIZ_SPEC_pass6.md §1.5/§1.6/§7/§8, BUILD_PLAN.md P4/P5/P12):
(1) #40 remaining partner-metric families from ptn_denominators.parquet (share of UL's
whole corpus, of UL's international copubs, of UL's copubs with the partner's own
country); (2) #41 granularity parity vs pages 8/10 (country FR name, labs-involved count,
fractional count folded into the identity caption); (3) #42 the unanchored "part du
collaboratif UL" line chart is retired in favour of the two-window aggregate the header's
quantified momentum block already carries, plus a small zero-anchored two-bar comparison,
honestly labelled per the traced ratio (partner co-works / UL total collaborative
co-works, reports/pass6_probes.md probe 4); (4) #43 ergonomics -- primary-styled
descendre/remonter controls, the member-mask toggle and the topic search box removed
(useless below the ranked_table() N>=50 threshold), momentum quantified via
lib.helpers.momentum_display(), and a per-theme annual zoom (field/subfield/topic) built
straight from the already-lazy-loaded ptn_works rows so the I-SITE decomposition is real
even though ptn_yearly/ptn_topics carry no isite twin; (5) #44 the full pair worklist is
no longer rendered as an on-screen table -- a 5-row preview plus a lazy CSV download
(lib.helpers.lazy_slice_csv_bytes) carrying doi/year/type/in_isite/sdg_tags/artifact_flag;
(6) #45 portage depth raised to top 20 (10 shown, "afficher plus"), "Autres" in the
app-wide neutral grey (NEUTRAL_GREY); (7) #46 a per-field réciprocité scatter for this
partner vs the UL, built from ptn_fields' own baseline_ul_share/baseline_partner_share
(conf_state='all' only -- probe 7 confirmed the partner-side share already exists for the
42b-pulled partners, $0, no group_by top-up needed); partners outside that set get an
honest disclosure, never a fabricated point. Narrative sweep pastes
NARRATIVE_CONTRACT_pass6.md section 2.10 verbatim except where a later, more specific
ruling (the #42 root-cause fix) supersedes an earlier draft -- see progress/PZP.md.

Authority (binding): VIZ_SPEC §2.6 + §1.1-1.6 + §3 · indicator_plan_FINAL §3/§6.3/§6.6 ·
data_foundation.yaml rev 3.1 (ptn_yearly/ptn_fields/ptn_labs/ptn_works/ptn_topics) ·
data_contract.yaml (deployed schemas -- verified against the actual parquet) ·
docs/SPRINT_KICKOFF_pass5.md (R1/R5/R11/R12/R14/R19) · docs/OVERLAY_MATRIX.md §9. Every
shared behaviour goes through Streamlit/lib/{controls,exports,lazy,ranked,overlay,
helpers,countries_fr}.py -- `lib.links` was consulted (pass-3 audit) but is NOT imported:
nothing on this page maps onto its filter shape, so no icon is rendered anywhere (silence,
per its own "never invent filter grammar" contract).

Decision sentence (VIZ_SPEC 2.6): after this view a porteur can say what binds UL to
partner P -- which fields, which labs carry it, whether it is rising -- and pull the exact
publications behind any cell.

Composition (profile card, argument order):
  1. Header: identity + consortium tag + KPI row (co-works . share_UL . share_P . median
     FWCI_FR . ISITE) + the partner's weight in other comparison perimeters (ptn_denominators)
     + the quantified momentum block.
  2. Volume panel: yearly bars (left) + a zero-anchored two-window comparison of the
     partner's weight in UL's collaborative output (right) -- the #42 replacement for the
     unanchored per-year sparkline.
  3. Profil thématique -- the centre. Drill-in-place: field row -> subfield rows
     (floored) -> topic rows (I11, scoped to the selected subfield), plus a per-theme
     annual zoom at every level (built from the lazy partner-works rows, real I-SITE
     decomposition).
  4. Réciprocité stratégique par champ (item #46): per-field scatter, this partner vs UL,
     from ptn_fields' own two baselines.
  5. Portage (I7): top 20 labs' share of lab-attributed works (10 shown, "afficher plus")
     + "Autres" (neutral grey) + a NO-LAB disclosure line, never a league column.
  6. Publications: a 5-row preview + a lazy CSV download carrying enrichment metadata,
     never the full on-screen list (item #44).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import controls, exports, lazy, overlay, ranked
from lib.countries_fr import country_label
from lib.data_cache import DATA_DIR, get_corpus_facts_df, get_topics_df
from lib.helpers import (
    YEARS, DOMAIN_EMOJI, NEUTRAL_GREY,
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
NODE_BASE_COLOR = "#0072B2"
PORTAGE_DEFAULT_N = 10
PORTAGE_MAX_N = 20

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
YEARLY_ISITE_NA_FR = (
    ":grey[Pas de décomposition I-SITE sur ce panneau : les données annuelles de cette "
    "paire ne portent pas la distinction I-SITE.]"
)
PORTAGE_ISITE_NA_FR = (
    ":grey[Lecture structurelle : comme pour le filtre « hors référentiel », la surcouche "
    "I-SITE ne s'applique pas à ce panneau.]"
)
TOPIC_ISITE_NA_FR = (
    ":grey[Pas de décomposition I-SITE à ce niveau : le croisement partenaire × topic ne "
    "porte pas la distinction I-SITE.]"
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


# =============================================================================
# Data (eager, small tables -- cache_resource, whole-table load + in-app filter, matching
# the contract's own distinction: only ptn_works/ptn_topics carry `lazy: true`)
# =============================================================================
@st.cache_resource
def _load_ptn_summary() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "ptn_summary.parquet")


@st.cache_resource
def _load_ptn_yearly() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "ptn_yearly.parquet")


@st.cache_resource
def _load_ptn_fields() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "ptn_fields.parquet")


@st.cache_resource
def _load_ptn_labs() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "ptn_labs.parquet")


@st.cache_resource
def _load_ptn_mom_facts() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "ptn_mom_facts.parquet")


@st.cache_resource
def _load_ptn_denominators() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "ptn_denominators.parquet")


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

st.page_link("pages/8_🤝_Collaborations.py", label="← Retour à Collaborations")

# =============================================================================
# Section 1 -- header : identité, KPI, autres périmètres (#40), momentum quantifié (#43)
# =============================================================================
mom_facts_all = _load_ptn_mom_facts()
_mf_rows = mom_facts_all[mom_facts_all["conf_state"] == CONF_STATE]
mf_row = _mf_rows.iloc[0] if not _mf_rows.empty else None

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
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Co-publications", fr_int(int(partner_row[CO_COL])))
    k2.metric("Part UL", fr_pct(float(partner_row[controls.xa(base_rows, 'share_ul')]) * 100))
    # share_p (42b pull) is populated on this page's own base_rows (subset_id='all' always
    # here) whenever CONF_STATE=='all' -- render the value + its denominator when present,
    # an honest em-dash + reason when NULL by design (no_conf).
    _share_p = partner_row.get("share_p")
    if pd.notna(_share_p):
        _denom = int(partner_row["partner_total_windowed"])
        k3.metric("Part partenaire", fr_pct(float(_share_p) * 100), delta=f"/ {fr_int(_denom)}", delta_color="off")
    else:
        k3.metric("Part partenaire", "—")
    k4.metric("FWCI médian (réf. France)", _fr_float(partner_row[controls.xa(base_rows, "fwci_fr_median")]))
    # Header KPI identity tile -- deliberately NOT gated by the I-SITE overlay toggle (it is
    # a single-value identity fact about this ONE partner, not a decomposed volume bar).
    k5.metric("Co-pubs ISITE", fr_int(int(partner_row['isite_co_works'])), fr_pct(float(partner_row['isite_share']) * 100))
    if pd.isna(_share_p):
        st.caption(SHARE_P_NULL_BY_DESIGN_FR)

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

    # -- #43: momentum, quantified (VIZ_SPEC_pass6 §8.3) --
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
            f'<div style="font-size:13px;color:#5A5F66">'
            f'Part du collaboratif UL : {w1_pct} ({w1_lbl}) → {w2_pct} ({w2_lbl})<br>'
            f'Co-publications : {c1c2} &nbsp;&nbsp;&nbsp; Signification : p = {p_txt} '
            f'(seuil {sig_txt})</div>',
            unsafe_allow_html=True,
        )
    st.caption(MOMENTUM_METHOD_HELP_FR)

st.markdown("---")

# =============================================================================
# Section 2 -- volume panel: yearly bars + a zero-anchored two-window comparison (#42)
# =============================================================================
st.markdown("### Volume")
st.markdown(
    "**Comment lire.** À gauche, le nombre de co-publications par année avec ce "
    "partenaire, compté depuis zéro. À droite, la part de ce partenaire dans l'ensemble "
    "des co-publications de l'Université de Lorraine avec n'importe quel partenaire, "
    "comparée entre deux fenêtres : une part qui monte d'une fenêtre à l'autre signale un "
    "partenaire qui prend du poids relatif dans le collaboratif de l'UL, pas nécessairement "
    "un partenaire qui publie davantage en volume absolu."
)
yr = _load_ptn_yearly()
yr_p = yr[(yr["partner_id"] == partner_id) & (yr["conf_state"] == CONF_STATE)].sort_values("year")

col_bars, col_win = st.columns(2)
with col_bars:
    st.markdown("#### Volume annuel")
    co_col_y = controls.xa(yr_p, "co_works")
    fig_bars = go.Figure(go.Bar(x=yr_p["year"].astype(str), y=yr_p[co_col_y], marker_color="#0072B2"))
    fig_bars.update_layout(height=260, margin=dict(t=20, l=40, r=20, b=30), yaxis_title="Co-publications", xaxis_title="")
    st.plotly_chart(fig_bars, width="stretch")
with col_win:
    st.markdown("#### Poids dans le collaboratif annuel de l'UL")
    if mf_row is not None and pd.notna(_w1s) and pd.notna(_w2s):
        w1_lbl = str(mf_row.get("mom_w1_label", "—"))
        w2_lbl = str(mf_row.get("mom_w2_label", "—"))
        status_color = MOM_STATUS_COLOR.get(str(partner_row.get("mom_category")), MOMENTUM_NEUTRAL_COLOR)
        fig_win = go.Figure(go.Bar(
            x=[w1_lbl, w2_lbl], y=[float(_w1s) * 100, float(_w2s) * 100],
            marker_color=[MOMENTUM_NEUTRAL_COLOR, status_color],
        ))
        fig_win.update_layout(
            height=260, margin=dict(t=20, l=40, r=20, b=30),
            yaxis_title="Part du collaboratif UL (%)", xaxis_title="",
            yaxis=dict(rangemode="tozero"),
        )
        st.plotly_chart(fig_win, width="stretch")
    else:
        st.caption("—")
if isite_overlay_on:
    st.caption(YEARLY_ISITE_NA_FR)
st.markdown(
    "**Pourquoi cet indicateur.** Le volume dit si la relation grandit dans l'absolu ; le "
    "poids relatif dit si elle grandit plus vite ou plus lentement que l'ensemble des "
    "partenariats de l'UL. Un partenaire peut publier davantage chaque année tout en "
    "perdant du poids si le collaboratif de l'UL grandit plus vite encore."
)
exports.attach_download(st, yr_p, "v2-partner-drilldown", "yearly", _EXPORT_STATE, entity=("p", partner_id))

st.markdown("---")

# =============================================================================
# Section 3 -- Profil thématique : scoped-descent field -> subfield -> topic (I11)
# =============================================================================
st.markdown("### Profil thématique de la relation")
st.markdown(
    "**Comment lire.** Une ligne par champ, puis par sous-champ, puis par topic : la "
    "descente est cadrée, le fil d'Ariane remonte. « % de la paire » rapporte au total de "
    "la relation, « % de l'UL » situe le même champ dans le portefeuille lorrain entier : "
    "un champ peut peser beaucoup dans la relation et peu dans le portefeuille, et c'est "
    "le cas le plus intéressant."
)

# The full pair's works, lazy-keyed (Class-1 pruned read) -- feeds the per-theme annual
# zoom, the suppressed-count disclosures below, and the publications preview/download.
partner_works = lazy.read_keyed(PTN_WORKS_PATH, "partner_id", partner_id)

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

fld_all = _load_ptn_fields()
fld_p = fld_all[(fld_all["partner_id"] == partner_id) & (fld_all["conf_state"] == CONF_STATE)]

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

        chart_f = visible_f.head(FIELD_CHART_CAP).sort_values("co_works", ascending=True)
        if not chart_f.empty:
            st.markdown("###### Volume par champ")
            fig_f = overlay.overlay_bars(
                categories=chart_f["field_label"].tolist(), totals=chart_f["co_works"].tolist(),
                isite=chart_f["co_works_isite"].tolist(), colors=chart_f["domain_color"].tolist(),
                isite_on=isite_overlay_on, orientation="h",
            )
            fig_f.update_layout(height=max(200, 26 * len(chart_f)), margin=dict(t=10, l=10, r=20, b=30),
                                 xaxis_title="Co-publications", showlegend=isite_overlay_on)
            st.plotly_chart(fig_f, width="stretch")

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

        chart_s = visible_s.head(SUBFIELD_CHART_CAP).sort_values("co_works", ascending=True)
        if not chart_s.empty:
            st.markdown("###### Volume par sous-champ")
            fig_s = overlay.overlay_bars(
                categories=chart_s["subfield_label"].tolist(), totals=chart_s["co_works"].tolist(),
                isite=chart_s["co_works_isite"].tolist(), colors=chart_s["subfield_color"].tolist(),
                isite_on=isite_overlay_on, orientation="h",
            )
            fig_s.update_layout(height=max(200, 26 * len(chart_s)), margin=dict(t=10, l=10, r=20, b=30),
                                 xaxis_title="Co-publications", showlegend=isite_overlay_on)
            st.plotly_chart(fig_s, width="stretch")

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

    partner_topics = lazy.read_keyed(PTN_TOPICS_PATH, "partner_id", partner_id)
    # ptn_topics is conf-keyed (partner x topic x year x conf_state) -- filter on the
    # ACTIVE conf_state, same session key as every other table on this page.
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
# Section RÉCIPROCITÉ -- per-field scatter, this partner vs the UL (item #46)
# =============================================================================
st.markdown("### Réciprocité stratégique par champ")
st.markdown(
    "**Comment lire.** Chaque point est un champ disciplinaire. L'axe vertical donne le "
    "poids de ce champ dans le portefeuille propre de l'Université de Lorraine ; l'axe "
    f"horizontal donne le poids du même champ dans le portefeuille propre de "
    f"{partner_row['display_name']}. La taille du point suit le volume de "
    "co-publications entre les deux établissements dans ce champ. La diagonale marque un "
    "poids identique des deux côtés."
)
# baseline_partner_share only exists at conf_state='all' (probe 7) -- this panel is
# therefore always read on that basis, disclosed below, never approximated from a
# no_conf-scoped value that does not exist.
fld_recip = fld_all[
    (fld_all["partner_id"] == partner_id) & (fld_all["conf_state"] == "all")
    & (fld_all["node_level"] == "field")
].copy()
if fld_recip.empty or fld_recip["baseline_partner_share"].isna().all():
    st.info(
        f"Le poids de {partner_row['display_name']} dans son propre portefeuille n'est "
        "pas mesuré pour ce partenaire : aucune valeur n'est affichée plutôt qu'une "
        "valeur fabriquée."
    )
else:
    fld_recip = fld_recip[fld_recip["baseline_partner_share"].notna()].copy()
    fld_recip["field_id_int"] = fld_recip["node_id"].astype(int)
    fld_recip["field_name"] = fld_recip["field_id_int"].map(field_id2name)
    fld_recip["domain_id"] = fld_recip["field_id_int"].map(field_id2domain)
    fld_recip["domain_name"] = fld_recip["domain_id"].map(domain_id2name)

    sizeref = _area_sizeref(fld_recip["co_works"])
    fig_recip = go.Figure()
    for dom_name, d in fld_recip.groupby("domain_name"):
        color = get_domain_color(d["domain_id"].iloc[0])
        customdata = np.stack([
            d["field_name"].astype(str),
            [fr_pct(v * 100) for v in d["baseline_ul_share"]],
            [fr_pct(v * 100) for v in d["baseline_partner_share"]],
            [fr_int(int(v)) for v in d["co_works"]],
        ], axis=-1)
        fig_recip.add_trace(go.Scatter(
            x=d["baseline_partner_share"] * 100, y=d["baseline_ul_share"] * 100,
            mode="markers", name=str(dom_name),
            marker=dict(size=d["co_works"], sizemode="area", sizeref=sizeref, sizemin=4,
                        color=color, line=dict(width=0.5, color="white")),
            customdata=customdata,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>Poids UL : %{customdata[1]}<br>"
                "Poids partenaire : %{customdata[2]}<br>"
                "Co-publications : %{customdata[3]}<extra></extra>"
            ),
        ))
    max_val = float(max(fld_recip["baseline_ul_share"].max(), fld_recip["baseline_partner_share"].max())) * 100 * 1.1
    fig_recip.add_shape(type="line", x0=0, y0=0, x1=max_val, y1=max_val, line=dict(color="#B0B6BC", dash="dot"))
    fig_recip.update_layout(
        height=480, margin=dict(t=20, l=50, r=20, b=50),
        xaxis=dict(title=f"Poids du champ chez {partner_row['display_name']} (%)", range=[0, max_val]),
        yaxis=dict(title="Poids du champ à l'UL (%)", range=[0, max_val]),
        legend=dict(orientation="h", y=-0.2),
    )
    st.plotly_chart(fig_recip, width="stretch")
    st.caption(
        ":grey[Calculé sur le corpus entier, tous types de publication confondus, quel que "
        "soit l'état du filtre « papiers de conférence » : le poids du partenaire dans son "
        "propre portefeuille n'est mesuré qu'à cet état.]"
    )
    exports.attach_download(
        st, fld_recip.drop(columns=["field_id_int", "domain_id"], errors="ignore"),
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
# Section 4 -- Portage interne de la relation (I7), top 20 / 10 par défaut (#45)
# =============================================================================
st.markdown("### Portage interne de la relation")
st.markdown(
    "**Comment lire.** Part de chaque laboratoire lorrain dans les travaux de la relation "
    "qui sont attribués à une structure ; les structures suivantes sont regroupées sous "
    "« Autres », dans une couleur distincte. Les travaux sans laboratoire attribué sont "
    "comptés à part, hors de ce rapport."
)
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

    bar_names = shown["lab_name"].astype(str).tolist()
    bar_shares = (shown["share_of_lab_attributed"] * 100).tolist()
    bar_colors = ["#0072B2"] * len(bar_names)
    if not autres.empty:
        bar_names.append(f"Autres ({fr_int(len(autres))} laboratoires)")
        bar_shares.append(float(autres["share_of_lab_attributed"].sum()) * 100)
        bar_colors.append(NEUTRAL_GREY)

    fig_portage = go.Figure(go.Bar(y=bar_names, x=bar_shares, orientation="h", marker_color=bar_colors))
    fig_portage.update_layout(
        height=max(260, 26 * len(bar_names)), margin=dict(t=10, l=10, r=20, b=30),
        xaxis_title="% des travaux attribués à un labo (hors NO-LAB)",
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_portage, width="stretch")
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
# Section 5 -- publications : aperçu (5 lignes) + téléchargement lazy (item #44)
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
