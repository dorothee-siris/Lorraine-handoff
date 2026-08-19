"""
Geographic Focus (V3) -- docs/indicator_plan_FINAL.md §3 (I10) / docs/studio/VIZ_SPEC.md
§2.7. NEW page, chain pass 3, Assembly Line stream P2.
Pass-5 stream P-F (2026-08-18): country table converted to ranked_table (R11/R14: query,
progress bars, median-first) + I-SITE overlay bars (R1, geo_countries.isite_co_works/
.isite_share) with the "Inconnu" bucket pulled OUT of the ranked population and kept as an
always-visible caption instead (so it can never be pushed off-screen by depth/query/rank --
a stronger reading of "the unknown bucket stays visible" than a rank-dependent row would
give); country-focus field/subfield table gains lib.ranked's pure search/depth helpers
(on_select drill preserved -- ranked_table()'s frozen API has no on_select, see page 9's
own note for the same trade-off); FR question-sentence opener + FR number formatting
(R12/R19). The map is mechanically untouched (QA-05 ladder-cut disclosure stays).

Authority (binding): VIZ_SPEC §2.7 + §1.1-1.6 + §3 · indicator_plan_FINAL §3/§6.6 ·
data_foundation.yaml rev 3.1 (geo_countries/geo_fields/geo_groups) · data_contract.yaml
(deployed schemas -- verified against the actual parquet) · docs/SPRINT_KICKOFF_pass5.md
(R1/R11/R12/R14/R19) · docs/OVERLAY_MATRIX.md §10. Every shared behaviour goes through
Streamlit/lib/{controls,exports,lazy,ranked,overlay,helpers}.py.

Decision sentence (VIZ_SPEC 2.7): after this view the VP can say which countries are UL's
backbone, what the UniGR cross-border reality is, and where the alliance narrative
honestly stands.

Pass-6 stream P-GA (2026-08-19): #13 country display -> FR names everywhere ISO2 showed
(table, map hovers, overlay-bar axis, KPI tile, fiche-pays selector) via NEW
lib.countries_fr.country_label(); VIZ_BACKLOG #2 restore -- the yearly-trend sparkline
(sparkline_cols, wired onto the previously-unused `_yearly_list()` helper) and the
country click-through (link_cols: a "-> Fiche pays" LinkColumn href="?country_code=XX",
read back via st.query_params on load -- the on_select row-click stays a documented
ranked_table() non-goal, VIZ_BACKLOG #2's own resolution); narrative sweep (8 jargon) +
year-literal/snapshot-fallback fixes (window_label()/snapshot_date_label(), G1/G2).


Composition:
  1. KPI row: countries >=10 co-pubs (120, UNKNOWN excluded by construction) . %
     international . top country share.
  2. Country ranked table (left, 60%, lib.ranked.ranked_table() -- query by name, progress
     bars, median-first) + a companion I-SITE overlay bar chart (R1) + symbol map (right,
     ladder-cut #2 -- the table carries all content). `unknown` bucket = always-visible
     caption, excluded from the ranked population and from the map by construction.
  3. Country focus card: field profile vs UL baseline (geo_fields, lazy-keyed), drill
     field -> subfield per §6.6 (depth stops at subfield -- no topic grain here, so no
     "Réf." column: nothing to flag at this depth). No I-SITE decomposition here
     (`geo_fields` carries no isite twin, N/A-disclosed, docs/OVERLAY_MATRIX.md §10).
  4. UniGR card (5 members, fixed order, measured volumes + per-member momentum chips).
     A per-member I-SITE breakdown is feasible via a join to `ptn_summary` (every member
     is also a partner row) but not wired this pass -- disclosed follow-up, not built
     silently.
  5. EURECA-PRO honest-baseline card (Leoben 11, Freiberg UNION 15) -- deliberately
     un-charted.

Grain caveat (probed, not assumed): `geo_countries` carries per-YEAR fwci_fr_median rows
only (no whole-window aggregate row) -- the ranked table's FWCI column is therefore a
co-works-weighted average of the yearly medians, disclosed as an approximation rather than
silently presented as a true window median.
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
    YEARS, fr_int, fr_pct, window_label, snapshot_date_label,
    init_taxonomy, get_field_id_to_name, get_subfield_id_to_name, get_subfields_for_field,
)

# =============================================================================
# Page config
# =============================================================================
st.set_page_config(page_title="Géographie | Bibliométrie UL", page_icon="🌍", layout="wide")

init_taxonomy(get_topics_df())

GEO_FIELDS_PATH = str(DATA_DIR / "geo_fields.parquet")
SUBFIELD_FLOOR = 3  # geo_fields ships subfield rows floored, same discipline as ptn_fields
COUNTRY_CHART_CAP = 25
COUNTRY_BASE_COLOR = "#0072B2"

QUESTION_FR = (
    "Quels pays forment le socle international de l'UL, et où en est, concrètement, le "
    "récit d'alliance transfrontalière ?"
)
S10_BANNER_FR = (
    "Les chiffres de cette page sont des faits de corpus, destinés à situer les "
    "partenariats internationaux du site, jamais à classer les pays entre eux."
)
NODE_ISITE_NA_FR = (
    ":grey[Pas de décomposition I-SITE sur cette fiche : les données par pays ne portent "
    "pas la distinction I-SITE.]"
)
UNIGR_ISITE_NOTE_FR = (
    ":grey[Une décomposition I-SITE par membre est possible à partir des données "
    "partenaires ; elle n'est pas branchée sur ce panneau.]"
)

# Standard ISO 3166-1 alpha-2 -> alpha-3 table (static reference data, generated once from
# `pycountry` at authoring time and inlined here -- no new runtime dependency, requirements.txt
# stays pinned per BUILD_PLAN S4). Used ONLY to feed Plotly's built-in `locationmode="ISO-3"`
# geo engine (no hand-guessed centroid coordinates).
ISO2_TO_ISO3 = {
    "AD": "AND", "AE": "ARE", "AF": "AFG", "AG": "ATG", "AL": "ALB", "AM": "ARM", "AO": "AGO",
    "AR": "ARG", "AS": "ASM", "AT": "AUT", "AU": "AUS", "AZ": "AZE", "BA": "BIH", "BB": "BRB",
    "BD": "BGD", "BE": "BEL", "BF": "BFA", "BG": "BGR", "BH": "BHR", "BI": "BDI", "BJ": "BEN",
    "BN": "BRN", "BO": "BOL", "BR": "BRA", "BS": "BHS", "BW": "BWA", "BY": "BLR", "BZ": "BLZ",
    "CA": "CAN", "CD": "COD", "CF": "CAF", "CG": "COG", "CH": "CHE", "CI": "CIV", "CL": "CHL",
    "CM": "CMR", "CN": "CHN", "CO": "COL", "CR": "CRI", "CU": "CUB", "CV": "CPV", "CY": "CYP",
    "CZ": "CZE", "DE": "DEU", "DJ": "DJI", "DK": "DNK", "DO": "DOM", "DZ": "DZA", "EC": "ECU",
    "EE": "EST", "EG": "EGY", "ES": "ESP", "ET": "ETH", "FI": "FIN", "FJ": "FJI", "FR": "FRA",
    "GA": "GAB", "GB": "GBR", "GE": "GEO", "GF": "GUF", "GH": "GHA", "GM": "GMB", "GN": "GIN",
    "GP": "GLP", "GR": "GRC", "GT": "GTM", "GU": "GUM", "GY": "GUY", "HK": "HKG", "HR": "HRV",
    "HT": "HTI", "HU": "HUN", "ID": "IDN", "IE": "IRL", "IL": "ISR", "IN": "IND", "IQ": "IRQ",
    "IR": "IRN", "IS": "ISL", "IT": "ITA", "JM": "JAM", "JO": "JOR", "JP": "JPN", "KE": "KEN",
    "KG": "KGZ", "KH": "KHM", "KR": "KOR", "KW": "KWT", "KZ": "KAZ", "LA": "LAO", "LB": "LBN",
    "LK": "LKA", "LR": "LBR", "LT": "LTU", "LU": "LUX", "LV": "LVA", "LY": "LBY", "MA": "MAR",
    "MC": "MCO", "MD": "MDA", "ME": "MNE", "MG": "MDG", "MK": "MKD", "ML": "MLI", "MM": "MMR",
    "MN": "MNG", "MO": "MAC", "MQ": "MTQ", "MR": "MRT", "MT": "MLT", "MU": "MUS", "MV": "MDV",
    "MW": "MWI", "MX": "MEX", "MY": "MYS", "MZ": "MOZ", "NA": "NAM", "NC": "NCL", "NE": "NER",
    "NG": "NGA", "NI": "NIC", "NL": "NLD", "NO": "NOR", "NP": "NPL", "NZ": "NZL", "OM": "OMN",
    "PA": "PAN", "PE": "PER", "PF": "PYF", "PH": "PHL", "PK": "PAK", "PL": "POL", "PR": "PRI",
    "PS": "PSE", "PT": "PRT", "PY": "PRY", "QA": "QAT", "RE": "REU", "RO": "ROU", "RS": "SRB",
    "RU": "RUS", "RW": "RWA", "SA": "SAU", "SC": "SYC", "SD": "SDN", "SE": "SWE", "SG": "SGP",
    "SI": "SVN", "SK": "SVK", "SM": "SMR", "SN": "SEN", "SO": "SOM", "SR": "SUR", "SV": "SLV",
    "SY": "SYR", "TD": "TCD", "TG": "TGO", "TH": "THA", "TJ": "TJK", "TM": "TKM", "TN": "TUN",
    "TO": "TON", "TR": "TUR", "TW": "TWN", "TZ": "TZA", "UA": "UKR", "UG": "UGA", "US": "USA",
    "UY": "URY", "UZ": "UZB", "VE": "VEN", "VG": "VGB", "VN": "VNM", "WS": "WSM", "YE": "YEM",
    "ZA": "ZAF", "ZM": "ZMB", "ZW": "ZWE",
}

MOM_LABELS = {
    "up": ("en hausse", "↑"), "down": ("en retrait", "↓"), "stable": ("stable", "→"),
    "ns": ("non significatif", "—"),
}


def _mom_chip(cls) -> str:
    if pd.isna(cls):
        return "—"
    label, sym = MOM_LABELS.get(str(cls), (str(cls), ""))
    return f"{sym} {label}"


def _fr_float(val, decimals: int = 2) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)) or pd.isna(val):
        return "—"
    return f"{float(val):.{decimals}f}".replace(".", ",")


def _area_sizeref(values, max_px: float = 40.0) -> float:
    vmax = float(np.nanmax(values)) if len(values) else 1.0
    vmax = vmax if vmax > 0 else 1.0
    return 2.0 * vmax / (max_px ** 2)


# =============================================================================
# Data
# =============================================================================
@st.cache_resource
def _load_geo_countries() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "geo_countries.parquet")


@st.cache_resource
def _load_geo_groups() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "geo_groups.parquet")


# =============================================================================
# Sidebar + banners
# =============================================================================
ctrl = controls.sidebar()
include_conference = ctrl["include_conference"]
artifact_on = ctrl[controls.ARTIFACT_TOGGLE_KEY]
isite_overlay_on = ctrl[controls.ISITE_OVERLAY_KEY]
CONF_STATE = "all" if include_conference else "no_conf"
active_subset = ctrl.get("perimeter_subset", "all")
effective_subset = active_subset if active_subset in ("all", "in_isite") else "all"

st.title("🌍 Géographie")
st.markdown(f"##### {QUESTION_FR}")
st.info(S10_BANNER_FR)
controls.banner()
controls.filtered_by_strip(page="geographie")
if active_subset != effective_subset:
    st.caption(
        f":grey[Périmètre « {active_subset} » pas encore peuplé à ce grain -- affichage "
        "replié sur « all ».]"
    )

facts = get_corpus_facts_df()
SNAPSHOT_DATE = snapshot_date_label()
field_id2name = get_field_id_to_name()
subfield_id2name = get_subfield_id_to_name()

_EXPORT_STATE = exports.ExportState(
    snapshot=SNAPSHOT_DATE, conf=include_conference, artifact=artifact_on,
    subset=effective_subset, artifact_applied=bool(artifact_on),
)
_EXPORT_STATE_EXEMPT = exports.ExportState(
    snapshot=SNAPSHOT_DATE, conf=include_conference, artifact=artifact_on,
    subset=effective_subset, artifact_applied=False,
)

gc = _load_geo_countries()
gcs = gc[(gc["conf_state"] == CONF_STATE) & (gc["subset_id"] == effective_subset)].copy()
CO_COL_C = controls.xa(gcs, "co_works")
FWCI_COL_C = controls.xa(gcs, "fwci_fr_median")


def _weighted_fwci(group: pd.DataFrame) -> float:
    w = group[CO_COL_C].astype(float)
    v = group[FWCI_COL_C]
    mask = v.notna() & (w > 0)
    if not mask.any():
        return float("nan")
    return float((v[mask] * w[mask]).sum() / w[mask].sum())


def _yearly_list(group: pd.DataFrame) -> list[float]:
    s = group.set_index("year")[CO_COL_C]
    return [float(s.get(y, 0)) for y in YEARS]


agg_rows = []
for code, g in gcs.groupby("country_code", observed=True):
    agg_rows.append({
        "country_code": code,
        "co_works": float(g[CO_COL_C].sum()),
        "fwci_fr_median_approx": _weighted_fwci(g),
        "isite_co_works": float(g["isite_co_works"].sum()),
        "unknown": bool(g["unknown_bucket_flag"].iloc[0]),
        "trend": _yearly_list(g),  # VIZ_BACKLOG #2 restore -- the yearly sparkline
    })
agg_country = pd.DataFrame(agg_rows)
real_countries = agg_country[~agg_country["unknown"]].copy()

_facts_row = facts.set_index("conf_state").loc[CONF_STATE]
total_collab = float(_facts_row[controls.xa(facts, "corpus_collaborative_works")])
pct_intl = float(_facts_row[controls.xa(facts, "ul_intl_share")]) * 100

# =============================================================================
# Section 1 -- KPI row
# =============================================================================
st.markdown("## Vue d'ensemble")
n_ge10 = int((real_countries["co_works"] >= 10).sum())
top_row = real_countries.loc[real_countries["co_works"].idxmax()] if not real_countries.empty else None
top_share = (float(top_row["co_works"]) / total_collab * 100) if top_row is not None and total_collab else float("nan")
top_label = f"{country_label(top_row['country_code'])} -- {fr_pct(top_share)}" if top_row is not None else "n/a"

c1, c2, c3 = st.columns(3)
c1.metric("Pays (≥10 co-publications)", fr_int(n_ge10))
c2.metric("% travaux internationaux", fr_pct(pct_intl))
c3.metric("Premier pays partenaire", top_label)

st.markdown("---")

# =============================================================================
# Section 2 -- ranked table (left, 60%) + symbol map (right)
# =============================================================================
st.markdown("## Pays partenaires")
_unknown_total = float(agg_country.loc[agg_country["unknown"], "co_works"].sum()) if agg_country["unknown"].any() else 0.0
col_table, col_map = st.columns([3, 2])

with col_table:
    display = real_countries.copy()
    display["share"] = (display["co_works"] / total_collab * 100) if total_collab else np.nan
    display = display.sort_values("co_works", ascending=False).reset_index(drop=True)

    prepared = pd.DataFrame({
        "country_code": display["country_code"],
        "country_name": display["country_code"].apply(country_label),  # #13: FR display name
        "co_works": display["co_works"].astype(int),
        "share": display["share"].round(1),
        "trend": display["trend"],  # VIZ_BACKLOG #2 restore: yearly-trend sparkline
        "fwci_text": display["fwci_fr_median_approx"].apply(_fr_float),
        "isite_co_works": display["isite_co_works"].astype(int),
        "isite_share": (display["isite_co_works"] / display["co_works"].replace(0, np.nan) * 100).round(1),
        # VIZ_BACKLOG #2 restore: the dropped country click-through, via the NEW link_cols
        # API -- a relative href on THIS same page (?country_code=XX), read back by the
        # "Fiche pays" selectbox below via st.query_params (same session_state-or-
        # query_params idiom already used app-wide for author_id/partner_id deep links).
        "fiche_url": "?country_code=" + display["country_code"].astype(str),
    })

    _hidden = []
    if not isite_overlay_on:
        _hidden += ["isite_co_works", "isite_share"]
    _ref_labels = {
        "country_name": "Pays", "co_works": "Co-publications", "share": "Part",
        "trend": "Tendance annuelle", "fwci_text": "FWCI médian (approx., réf. France)",
        "isite_co_works": "Co-pubs I-SITE", "isite_share": "Part I-SITE",
        "fiche_url": "Fiche pays",
    }
    _progress = {
        "co_works": {"format": "%d", "max_value": int(prepared["co_works"].max()) if not prepared.empty else 1,
                     "help": "Barre à échelle commune sur le périmètre affiché."},
        "share": {"format": "%.1f%%", "max_value": 100,
                  "help": "Part du total des travaux collaboratifs du site."},
    }
    if isite_overlay_on:
        _progress["isite_share"] = {"format": "%.1f%%", "max_value": 100,
                                     "help": "Part I-SITE parmi les co-publications avec ce pays."}
    _sparkline = {
        "trend": {"help": f"Co-publications par année ({window_label()})."},
    }
    _link = {
        "fiche_url": {
            "help": "Ouvre la fiche pays ci-dessous, présélectionnée sur ce pays.",
            "display_text": "→ Fiche pays",
        },
    }

    visible = ranked.ranked_table(
        prepared, key="geo_country", id_col="country_code", has_members=False,
        search_cols=["country_code", "country_name"],
        progress_cols=_progress, sparkline_cols=_sparkline, link_cols=_link,
        mean_cols=_hidden, extra_hidden=["country_code"], ref_labels=_ref_labels,
    )
    st.caption(
        f"{fr_int(len(display))} pays réel(s) au-dessus de zéro co-publication. Bucket "
        f"« Inconnu » (pays non résolu) : {fr_int(int(_unknown_total))} co-publications -- "
        "toujours affiché ici, jamais sur la carte, jamais dans le tableau classé ci-dessus "
        "(ni masquable par la recherche, ni par la profondeur d'affichage). Tri par défaut : "
        "co-publications décroissantes ; le FWCI n'est jamais le tri par défaut."
    )

    exports.attach_download(st, agg_country, "v3-geographic", "countries", _EXPORT_STATE)

    chart_rows = visible.head(COUNTRY_CHART_CAP).sort_values("co_works", ascending=True)
    if not chart_rows.empty:
        st.markdown("###### Volume des pays affichés")
        fig_c = overlay.overlay_bars(
            categories=chart_rows["country_name"].tolist(), totals=chart_rows["co_works"].tolist(),
            isite=chart_rows["isite_co_works"].tolist(), colors=COUNTRY_BASE_COLOR,
            isite_on=isite_overlay_on, orientation="h",
        )
        fig_c.update_layout(height=max(220, 24 * len(chart_rows)), margin=dict(t=10, l=10, r=20, b=30),
                             xaxis_title="Co-publications", showlegend=isite_overlay_on)
        st.plotly_chart(fig_c, width="stretch")

with col_map:
    map_df = real_countries.copy()
    map_df["iso3"] = map_df["country_code"].map(ISO2_TO_ISO3)
    n_unmapped = int(map_df["iso3"].isna().sum())
    map_df = map_df.dropna(subset=["iso3"])
    if map_df.empty:
        st.info("Aucun pays cartographiable.")
    else:
        sizeref = _area_sizeref(map_df["co_works"])
        fig_map = go.Figure()
        fig_map.add_trace(go.Scattergeo(
            locations=map_df["iso3"], locationmode="ISO-3",
            marker=dict(
                size=map_df["co_works"], sizemode="area", sizeref=sizeref, sizemin=3,
                color="#0072B2", opacity=0.75, line=dict(width=0.5, color="white"),
            ),
            text=[f"{country_label(c)} : {fr_int(int(v))} co-pubs" for c, v in zip(map_df["country_code"], map_df["co_works"])],
            hovertemplate="%{text}<extra></extra>", mode="markers", showlegend=False,
        ))
        # Calibrated legend circles (2-3), plotted off the real data (Southern Ocean) using
        # the SAME sizeref -- comparable, not decorative.
        ref_vals = sorted({10, 100, int(map_df["co_works"].max())})
        for i, v in enumerate(ref_vals):
            fig_map.add_trace(go.Scattergeo(
                lon=[-25], lat=[-62 + i * 9], mode="markers",
                marker=dict(size=[v], sizemode="area", sizeref=sizeref, sizemin=3, color="#8C9196", opacity=0.6),
                name=f"{fr_int(v)} co-pubs", showlegend=True, hoverinfo="skip",
            ))
        fig_map.update_geos(
            showcountries=True, countrycolor="#c9cdd1", showcoastlines=True, coastlinecolor="#9aa0a6",
            projection_type="natural earth", showland=True, landcolor="#eef1f3",
            showocean=True, oceancolor="#f7fafc", showframe=False,
        )
        fig_map.update_layout(height=520, margin=dict(t=10, b=10, l=0, r=0), legend=dict(x=0, y=0))
        st.plotly_chart(fig_map, width="stretch")
        if n_unmapped:
            st.caption(f":grey[{fr_int(n_unmapped)} code(s) pays non cartographiable(s) (hors table ISO-3).]")
    st.caption(
        ":grey[La carte et le tableau ne sont pas liés : le tableau porte l'ensemble du "
        "contenu, et le sélecteur « Pays » ci-dessous pilote la fiche.]"
    )

st.markdown("---")

# =============================================================================
# Section 3 -- country focus card (dual-baseline, drill field -> subfield per §6.6)
# =============================================================================
st.markdown("## Fiche pays")
country_options = real_countries.sort_values("co_works", ascending=False)["country_code"].tolist()
if not country_options:
    st.info("Aucun pays disponible pour la fiche.")
else:
    _default = st.session_state.get("nav_country_code") or st.query_params.get("country_code")
    _default_idx = country_options.index(_default) if _default in country_options else 0
    picked_country = st.selectbox(
        "Pays", options=country_options, index=_default_idx, key="geo_country_pick",
        format_func=country_label,
    )
    st.query_params["country_code"] = picked_country  # keeps the "-> Fiche pays" link_cols

    if st.session_state.get("v3_last_country") != picked_country:
        st.session_state["v3_drill_field"] = None
        st.session_state["v3_last_country"] = picked_country

    country_fields = lazy.read_keyed(GEO_FIELDS_PATH, "country_code", picked_country)
    country_fields = country_fields[country_fields["conf_state"] == CONF_STATE]

    drilled = st.session_state.get("v3_drill_field")
    crumb_bits = ["Champs"]
    if drilled is not None:
        crumb_bits.append(field_id2name.get(int(drilled), str(drilled)))
    bc, up = st.columns([5, 1])
    bc.caption(" ▸ ".join(crumb_bits))
    if drilled is not None and up.button("← Remonter", key="v3_drill_up"):
        st.session_state["v3_drill_field"] = None
        st.rerun()

    if drilled is None:
        node_rows = country_fields[country_fields["node_level"] == "field"]
        level_label = "Champ"
        name_lookup = field_id2name
    else:
        valid_subs = set(get_subfields_for_field(int(drilled)))
        node_rows = country_fields[
            (country_fields["node_level"] == "subfield")
            & (country_fields["node_id"].astype(int).isin(valid_subs))
        ]
        level_label = "Sous-champ"
        name_lookup = subfield_id2name

    if node_rows.empty:
        st.info(f"Aucune donnée à ce niveau pour {picked_country}.")
    else:
        co_col_n = controls.xa(node_rows, "co_works")
        node_rows = node_rows.assign(_node_name=node_rows["node_id"].astype(int).map(name_lookup))

        # lib.ranked's PURE search/depth layer (R11 generalisation) -- on_select drill is
        # preserved (ranked_table()'s frozen API has no on_select, same trade-off as the
        # topic level on page 9).
        # S-LENS D5 / S-INSP D2 fix (pass-6 fix round): this box used to render
        # unconditionally -- at field level N<=26 (26 fields max) and at drilled-subfield
        # level N<=42 (both from all_topics.parquet), always under the P6-R6 floor of 50 --
        # a direct violation the other 10 text_input call sites app-wide already gate.
        # Wrapped in the same should_show_query_box() gate page 3/14 use.
        node_query = ""
        if ranked.should_show_query_box(len(node_rows)):
            node_query = st.text_input(f"Rechercher un {level_label.lower()} :", "", key="v3_node_query")
        node_queried = ranked.filter_by_query(node_rows, node_query, ["_node_name"])
        node_expanded = st.session_state.get("v3_node_expanded", False)
        node_view = node_queried.sort_values(co_col_n, ascending=False)
        node_view = ranked.depth_slice(node_view, expanded=node_expanded, default_n=10)

        rows = []
        for _, r in node_view.iterrows():
            nid = int(r["node_id"])
            rows.append({
                level_label: r["_node_name"],
                "_node_id": nid,
                "Co-publications": int(r[co_col_n]),
                "% de la paire pays": round(float(r[controls.xa(node_rows, "share_of_country_pair")]) * 100, 1),
                "% de l'UL (repère)": round(float(r["baseline_ul_share"]) * 100, 1),
                "FWCI médian (réf. France)": _fr_float(r["fwci_fr_median"]),
            })
        node_disp = pd.DataFrame(rows)
        col_cfg = {
            "Co-publications": st.column_config.ProgressColumn(
                "Co-publications", min_value=0, max_value=int(node_disp["Co-publications"].max()), format="%d"),
            "% de la paire pays": st.column_config.ProgressColumn("% de la paire pays", min_value=0, max_value=100, format="%.1f%%"),
            "% de l'UL (repère)": st.column_config.ProgressColumn("% de l'UL (repère)", min_value=0, max_value=100, format="%.1f%%"),
        }
        if artifact_on:
            col_cfg = controls.grey_deferred(col_cfg, ["% de l'UL (repère)", "FWCI médian (réf. France)"])
        event_g = st.dataframe(
            node_disp.drop(columns="_node_id"), hide_index=True, width="stretch",
            key=f"v3_node_tbl_{'field' if drilled is None else 'subfield'}",
            on_select="rerun", selection_mode="single-row", column_config=col_cfg,
        )
        if len(node_queried) > 10 and not node_expanded:
            if st.button("afficher plus", key="v3_node_more_btn"):
                st.session_state["v3_node_expanded"] = True
                st.rerun()
        if isite_overlay_on:
            st.caption(NODE_ISITE_NA_FR)
        if drilled is None:
            st.caption("▸ cliquer un champ pour voir ses sous-champs. La descente s'arrête au sous-champ.")
            sel_g = event_g.selection.rows if event_g is not None and event_g.selection else []
            if sel_g:
                st.session_state["v3_drill_field"] = int(node_disp.iloc[sel_g[0]]["_node_id"])
                st.rerun()
        exports.attach_download(
            st, node_rows, "v3-geographic", "country-focus", _EXPORT_STATE,
            entity=("c", picked_country), node=None if drilled is None else ("f", drilled),
        )

st.markdown("---")

# =============================================================================
# Section 4 -- UniGR card (5 members, fixed order)
# =============================================================================
st.markdown("## UniGR")
gg = _load_geo_groups()
unigr = gg[(gg["group_id"] == "unigr") & (gg["conf_state"] == CONF_STATE)]
UNIGR_ORDER = ["Luxembourg", "Liege", "Saarland", "Trier", "RPTU"]
unigr_members = unigr[["member_id", "member_name", "co_works_distinct", "mom_class"]].drop_duplicates().copy()
unigr_members["_order"] = unigr_members["member_id"].map({m: i for i, m in enumerate(UNIGR_ORDER)}).fillna(99)
unigr_members = unigr_members.sort_values("_order")

if unigr_members.empty:
    st.info("Données UniGR indisponibles.")
else:
    cols = st.columns(len(unigr_members))
    for col, (_, r) in zip(cols, unigr_members.iterrows()):
        with col:
            st.metric(r["member_name"], fr_int(int(r['co_works_distinct'])))
            chip = _mom_chip(r["mom_class"])
            st.caption(f"Momentum : {chip}" + (" :grey[(figé sous filtre)]" if artifact_on and pd.notna(r["mom_class"]) else ""))
    yearly = unigr.groupby("year")["co_works_year"].sum()
    fig_g = go.Figure(go.Bar(
        x=[str(y) for y in YEARS], y=[float(yearly.get(y, 0)) for y in YEARS], marker_color="#0072B2",
    ))
    fig_g.update_layout(
        height=220, margin=dict(t=10, l=40, r=20, b=30),
        yaxis_title=f"Co-publications ({fr_int(len(unigr_members))} membres)", xaxis_title="",
    )
    st.plotly_chart(fig_g, width="stretch")
    st.caption(
        "RPTU résulte de la fusion des universités de Kaiserslautern et de Landau : les "
        "travaux des deux établissements sont comptés une seule fois, comme pour tout "
        "partenaire portant plusieurs identifiants."
    )
    st.caption(f":grey[Liste des membres tenue par l'établissement, à jour de l'instantané du {SNAPSHOT_DATE}.]")
    if isite_overlay_on:
        st.caption(UNIGR_ISITE_NOTE_FR)
    exports.attach_download(st, unigr, "v3-geographic", "unigr-group", _EXPORT_STATE_EXEMPT)

st.markdown("---")

# =============================================================================
# Section 5 -- EURECA-PRO honest-baseline card
# =============================================================================
st.markdown("## EURECA-PRO")
eureca = gg[(gg["group_id"] == "eureca") & (gg["conf_state"] == CONF_STATE)][["member_id", "co_works_distinct"]].drop_duplicates()
if eureca.empty:
    st.info("Données EURECA-PRO indisponibles.")
else:
    with st.container(border=True):
        _leoben = eureca.loc[eureca["member_id"] == "Leoben", "co_works_distinct"]
        _freiberg = eureca.loc[eureca["member_id"] == "Freiberg", "co_works_distinct"]
        c1, c2 = st.columns(2)
        c1.metric("Leoben", fr_int(int(_leoben.iloc[0])) if not _leoben.empty else "n/a")
        c2.metric("Freiberg", fr_int(int(_freiberg.iloc[0])) if not _freiberg.empty else "n/a")
        st.caption(
            "Freiberg porte deux identifiants OpenAlex distincts (l'université technique et "
            "l'institut Helmholtz associé) : le compte affiché est l'union de leurs travaux, "
            "jamais la somme des deux compteurs, qui compterait deux fois les travaux "
            "communs. Ces volumes se lisent avec le décalage de publication propre à une "
            "alliance récente : c'est un point de départ, pas un signal de maturité. Deux "
            "nombres ne justifient pas un graphique, d'où leur affichage en tuiles."
        )
        if isite_overlay_on:
            st.caption(UNIGR_ISITE_NOTE_FR)
        exports.attach_download(st, eureca, "v3-geographic", "eureca-pro", _EXPORT_STATE_EXEMPT)

st.markdown("---")
st.caption(f"Instantané : {SNAPSHOT_DATE} · fenêtre {window_label()}.")
