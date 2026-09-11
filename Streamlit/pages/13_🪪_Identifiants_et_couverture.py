"""
Identifiers & Coverage (A-V3) -- docs/indicator_plan_FINAL.md S5 / docs/studio/VIZ_SPEC.md S2.12.

The A3 evidence-quality panel: how far the ORCID strategy has carried collectively, read at
lab / field / year / population grain -- NEVER at person grain (the schema itself makes a
lab-level "ORCID league table" unrepresentable, safeguard 5).

Structural safeguards this page must honour (docs/indicator_plan_FINAL.md S5):
  - safeguard 5 (never a compliance scoreboard): the lab table is ALPHABETICAL by
    construction, never sorted by coverage by default, and carries the collective caption
    verbatim. `aut_coverage` itself has no per-person row (unit_kind in
    {lab, field, year, population}) -- there is no person-level column to rank by even if
    a future edit tried to.
  - unknown-vs-absent kept distinct: "NO LAB" (a defined absence -- a work genuinely
    outside any curated lab) vs the field-level "UNKNOWN" bucket (a genuine classifier gap,
    51 works) are never conflated.
  - the 2023 dip (docs/indicator_plan_FINAL.md S5, measured feasibility paragraph) is shown
    raw and named, never smoothed.
  - safeguard 6 (S10 audience banner, explicit; animation AND pilotage audience per the plan).
  - export = collective grains only (this table has no person rows to leak in the first place).

Pass-6 stream P-GA (2026-08-19): narrative sweep (1 digit, per NARRATIVE_CONTRACT_pass6.md
S2.14) -- title/caption reorder, the "51 travaux" hardcode replaced by a value computed
from the UNKNOWN field-level row (so it also stays correct under the conference toggle),
EN table labels -> FR (G10); no country code renders on this page (item #13 N/A here).
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib.controls import sidebar as controls_sidebar, filtered_by_strip, ARTIFACT_TOGGLE_KEY, DAGGER
from lib.exports import attach_download, ExportState
from lib.data_cache import DATA_DIR
from lib import charts as C
from lib import copy_fr
from lib import helpers as H
from lib import hover as hv
from lib.reading import reading_line
from lib.helpers import (
    get_field_order_by_domain, get_field_id_to_domain_id, get_domain_color, fr_int, fr_pct,
    snapshot_date_label,
)

# =============================================================================
# Page config
# =============================================================================
st.set_page_config(page_title="Identifiers & Coverage | UL Bibliometrics", page_icon="🪪", layout="wide")

# ----------------------------------------------------------------------------
# FR-ready label dictionary + binding VERBATIM strings (VIZ_SPEC 1.6: new pages build
# EN-first; the phrase below is safeguard 5's exact quote, indicator_plan_FINAL.md S5).
# ----------------------------------------------------------------------------
S10_BANNER_FR = (
    "Un **« outil d'animation scientifique »** (et de pilotage de la stratégie ORCID) : "
    "mesurer une dynamique collective pour engager la conversation -- jamais un classement "
    "des laboratoires entre eux."
)
COLLECTIVE_CAPTION_FR = (
    "**Lecture collective : « où en est-on collectivement »** -- ce tableau ne classe aucun "
    "laboratoire ; il informe une dynamique partagée. Colonnes triables sur simple clic, "
    "mais l'ordre par défaut reste alphabétique."
)
def unknown_field_note_fr(n_unknown: int) -> str:
    """NARRATIVE_CONTRACT_pass6.md S2.14, verbatim replacement -- computed at render
    (P6-R2 b) so the count stays correct under the conference toggle instead of a
    hardcoded "51"."""
    return (
        f":grey[« Inconnu » : travaux sans champ principal assigné (limite du classifieur, "
        f"{fr_int(n_unknown)} travaux), à distinguer de « sans laboratoire », qui est une "
        "absence définie et non une donnée manquante.]"
    )


NO_LAB_NOTE_FR = "absence définie (aucun laboratoire porteur)"
# id_orcid_yearly / id_orcid_fields drapeau phrases -- docs/tooltip_spec.yaml notes, verbatim
# (pass 7b B2): fixed sentences, no data value or year, so a page-authored FR constant is the
# same idiom as S10_BANNER_FR/COLLECTIVE_CAPTION_FR above, not a P6-R2 violation.
COVERAGE_BREAK_FLAG_FR = (
    "la liaison des identifiants est plus tardive que les travaux, ce recul tient au retard "
    "de liaison et non à une baisse de pratique"
)
UNKNOWN_BUCKET_FLAG_FR = "seau des travaux sans champ renseigné, ce n'est pas un champ"
ARTIFACT_EXEMPT_PAGE_CAPTION_FR = (
    ":grey[Le filtre « hors référentiel » ne s'applique pas à cette page : la couverture "
    "d'identifiants porte sur les personnes, pas sur les topics -- valeurs inchangées.]"
)


# =============================================================================
# Data
# =============================================================================
@st.cache_resource
def _load_aut_coverage() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "aut_coverage.parquet")


def _pct(v) -> str:
    """R12: French percentage formatting (comma decimal, narrow space) via fr_pct."""
    return "—" if pd.isna(v) else fr_pct(float(v) * 100)


def _kpi_tile(container, label: str, pct, num, den) -> None:
    container.metric(label, _pct(pct))
    if pd.notna(num) and pd.notna(den):
        container.caption(f"{fr_int(num)} / {fr_int(den)}")


# =============================================================================
# Sidebar + banners
# =============================================================================
ctrl = controls_sidebar()
include_conference = ctrl["include_conference"]
artifact_on = ctrl[ARTIFACT_TOGGLE_KEY]
conf_token = "all" if include_conference else "no_conf"

# Pass-6 standardised order (NARRATIVE_CONTRACT_pass6.md S2.14): title, then a neutral
# question caption -- never a title-as-answer line ahead of the title.
st.title("🪪 Identifiants et couverture")
st.caption(
    "Cette page répond à : où en est, collectivement, la couverture des identifiants "
    "d'auteur sur le site ?"
)
st.info(S10_BANNER_FR)
# aut_coverage is artifact_exempt (identifier coverage is about persons, not topics) --
# the standard §6.2 banner would misstate what this specific page recomputes, so a
# distinct honest caption stands in for it (same idiom as controls.ships_v2_strip(),
# authored here because this exemption is table-specific, not page-class-specific).
if artifact_on:
    st.caption(ARTIFACT_EXEMPT_PAGE_CAPTION_FR)
filtered_by_strip(page="identifiants_couverture")  # not an overlay surface (structural N/A, matrix §13)

st.markdown(
    "**Pourquoi cet indicateur.** La couverture des identifiants conditionne tout ce que "
    "l'outil peut dire au grain des personnes : sans ORCID, deux homonymes restent deux "
    "profils, et un parcours se coupe en deux. Elle se lit collectivement, laboratoire par "
    "laboratoire, jamais personne par personne : c'est une dynamique partagée, pas un score "
    "de conformité."
)

cov = _load_aut_coverage()
cov_c = cov[cov["conf_state"] == conf_token]

# =============================================================================
# (1) KPI tiles with denominators
# =============================================================================
pop = cov_c[cov_c["unit_kind"] == "population"].set_index("unit_id")

st.markdown("### Couverture ORCID collective")
k1, k2, k3 = st.columns(3)
if "all_works" in pop.index:
    r = pop.loc["all_works"]
    _kpi_tile(k1, "Travaux avec ≥1 auteur UL lié ORCID", r["pct_works_orcid"], r["n_works_orcid_author"], r["n_works"])
if "persons_ge5works" in pop.index:
    r = pop.loc["persons_ge5works"]
    _kpi_tile(k2, "Auteurs actifs (≥5 travaux) liés ORCID", r["pct_orcid"], r["n_persons_orcid"], r["n_persons"])
if "all_persons" in pop.index:
    r = pop.loc["all_persons"]
    _kpi_tile(k3, "Toutes les personnes de l'annuaire liées ORCID", r["pct_orcid"], r["n_persons_orcid"], r["n_persons"])

# =============================================================================
# (2) By-year bars -- raw, the dip named, NEVER smoothed
# =============================================================================
st.markdown("### Couverture par année")
years_df = cov_c[cov_c["unit_kind"] == "year"].copy()
years_df["year_int"] = years_df["unit_id"].astype(int)
years_df = years_df.sort_values("year_int")

_n_year_rows = len(years_df)
_year_break_flags = [False] * _n_year_rows
if _n_year_rows >= 2:
    _prev_pct = float(years_df["pct_orcid"].iloc[-2])
    _last_pct = float(years_df["pct_orcid"].iloc[-1])
    _year_break_flags[-1] = _last_pct < _prev_pct

_hl_year = copy_fr.HOVER_LABELS["id_orcid_yearly"]["default"]
_year_hover = [
    hv.hover_lines([
        (_hl_year[0], str(int(row["year_int"]))),
        (_hl_year[1], hv.fmt_pct(row["pct_orcid"] * 100)),
        (_hl_year[2], hv.fmt_int(row["n_works_orcid_author"])),
        (_hl_year[3], hv.fmt_int(row["n_works"])),
        (_hl_year[4], COVERAGE_BREAK_FLAG_FR if flagged else None),
    ])
    for (_, row), flagged in zip(years_df.iterrows(), _year_break_flags)
]
_year_pct_vals = (years_df["pct_orcid"] * 100).round(1)
_year_text = [
    f"{hv.fmt_pct(v)} {DAGGER}" if flagged else hv.fmt_pct(v)
    for v, flagged in zip(_year_pct_vals, _year_break_flags)
]
_year_text_ink = [H.REFERENCE_RED if flagged else H.TEXT_PRIMARY for flagged in _year_break_flags]

fig_year = go.Figure(go.Bar(
    x=years_df["year_int"].astype(str),
    y=_year_pct_vals,
    marker_color=H.UL_COLOR,
    text=_year_text, textposition="outside", textfont=dict(color=_year_text_ink),
    customdata=_year_hover, hovertemplate=hv.HOVERTEMPLATE,
))
_year_pct_ticks = [0, 20, 40, 60, 80, 100]
fig_year.update_yaxes(tickmode="array", tickvals=_year_pct_ticks,
                       ticktext=[fr_pct(v, 0) for v in _year_pct_ticks])
reading_line("id_orcid_yearly")
st.plotly_chart(fig_year, width="stretch")
st.caption(
    "Rattachements d'auteurs UL comportant un ORCID, par année : valeurs brutes, jamais "
    "lissées. Un creux est montré et nommé, jamais moyenné pour disparaître."
)
attach_download(
    st, years_df.drop(columns=["year_int"]), "a-v3", "coverage-by-year",
    ExportState(snapshot=snapshot_date_label(), conf=include_conference, artifact=artifact_on,
                method="Couverture des identifiants par année (aut_coverage, unit_kind=year) : maille collective."),
    label="⬇ Données (xlsx)",
)

# =============================================================================
# (3) Coverage by field -- domain colours, UNKNOWN kept explicit
# =============================================================================
st.markdown("### Couverture par champ")
fields_df = cov_c[cov_c["unit_kind"] == "field"].copy()
known = fields_df[fields_df["unit_id"] != "UNKNOWN"].copy()
known["field_id"] = known["unit_id"].astype(int)
order = get_field_order_by_domain()
known["sort_order"] = known["field_id"].map({fid: i for i, fid in enumerate(order)})
known = known.sort_values("sort_order")
unknown_row = fields_df[fields_df["unit_id"] == "UNKNOWN"]

known["pct_pct"] = known["pct_works_orcid"].apply(lambda v: round(v * 100, 1) if pd.notna(v) else 0.0)
known["color"] = known["field_id"].map(lambda fid: get_domain_color(get_field_id_to_domain_id().get(fid, 0)))
field_rows = known[["unit_label", "pct_pct", "n_works", "color"]].rename(columns={"unit_label": "label"})
field_rows["is_unknown"] = False

if not unknown_row.empty:
    u = unknown_row.iloc[0]
    _unknown_pct = round(float(u["pct_works_orcid"]) * 100, 1) if pd.notna(u["pct_works_orcid"]) else 0.0
    field_rows = pd.concat([field_rows, pd.DataFrame([{
        "label": "Inconnu", "pct_pct": _unknown_pct, "n_works": u["n_works"],
        "color": H.NEUTRAL_GREY, "is_unknown": True,
    }])], ignore_index=True)

_hl_field = copy_fr.HOVER_LABELS["id_orcid_fields"]["default"]
field_rows["hover"] = [
    hv.hover_lines([
        (_hl_field[0], r["label"]),
        (_hl_field[1], hv.fmt_pct(r["pct_pct"])),
        (_hl_field[2], hv.fmt_int(r["n_works"]) if pd.notna(r["n_works"]) else hv.fmt_int(0)),
        (_hl_field[3], UNKNOWN_BUCKET_FLAG_FR if r["is_unknown"] else None),
    ])
    for _, r in field_rows.iterrows()
]

fig_field = C.bars_with_gutter(
    field_rows, family="champ", label_col="label", value_col="pct_pct",
    color=field_rows["color"].tolist(), hover_col="hover", value_fmt=hv.fmt_pct,
)
fig_field.update_xaxes(ticktext=[fr_pct(v, 0) for v in fig_field.layout.xaxis.tickvals])
reading_line("id_orcid_fields")
st.plotly_chart(fig_field, width="stretch")
n_unknown = int(unknown_row.iloc[0]["n_works"]) if not unknown_row.empty and pd.notna(unknown_row.iloc[0]["n_works"]) else 0
st.caption(unknown_field_note_fr(n_unknown))
attach_download(
    st, fields_df, "a-v3", "coverage-by-field",
    ExportState(snapshot=snapshot_date_label(), conf=include_conference, artifact=artifact_on,
                method="Couverture des identifiants par champ (aut_coverage, unit_kind=field) : maille collective."),
    label="⬇ Données (xlsx)",
)

# =============================================================================
# (4) Lab table -- ALPHABETICAL, never default-sorted by coverage (safeguard 5)
# =============================================================================
st.markdown("### Couverture par laboratoire")
labs_df = cov_c[cov_c["unit_kind"] == "lab"].copy().sort_values(
    "unit_id", key=lambda s: s.str.lower()
)

lab_rows = []
for _, r in labs_df.iterrows():
    n_persons = r["n_persons"]
    small = pd.notna(n_persons) and n_persons < 10
    lab_rows.append({
        "Laboratoire": r["unit_id"],
        "Personnes": int(n_persons) if pd.notna(n_persons) else 0,
        "% de personnes avec ORCID": "" if small else _pct(r["pct_orcid"]),
        "Publications": int(r["n_works"]) if pd.notna(r["n_works"]) else 0,
        "% de publications avec un auteur ORCID": _pct(r["pct_works_orcid"]),
        "Remarque": NO_LAB_NOTE_FR if r["unit_id"] == "NO LAB" else ("petit effectif (n<10) : % masqué" if small else ""),
    })
lab_table_df = pd.DataFrame(lab_rows)
st.dataframe(lab_table_df, hide_index=True, width="stretch", height=460)
st.caption(COLLECTIVE_CAPTION_FR)
attach_download(
    st, labs_df, "a-v3", "coverage-by-lab",
    ExportState(snapshot=snapshot_date_label(), conf=include_conference, artifact=artifact_on,
                method="Couverture des identifiants par laboratoire (aut_coverage, unit_kind=lab) : "
                       "maille collective, sans ligne par personne : le schéma ne peut pas porter "
                       "un palmarès individuel."),
    label="⬇ Données (xlsx)",
)

# =============================================================================
# (5) Identity-ledger tiles (conf-invariant identity facts -> always the 'all' row)
# =============================================================================
st.markdown("### Registre d'identité")
pop_all = cov[(cov["unit_kind"] == "population") & (cov["conf_state"] == "all")].set_index("unit_id")
l1, l2, l3 = st.columns(3)
if "merged_profiles" in pop_all.index:
    r = pop_all.loc["merged_profiles"]
    l1.metric("Profils fusionnés", fr_int(r["n_persons"]))
    l1.caption(f"{_pct(r['pct_orcid'])} de l'ensemble des {fr_int(pop_all.loc['all_persons', 'n_persons'])} personnes")
if "review_queue" in pop_all.index:
    r = pop_all.loc["review_queue"]
    l2.metric("File de révision (paires)", fr_int(r["n_persons"]))
    l2.caption("Conflits ORCID à forte corroboration en attente d'arbitrage humain -- jamais fusionnés de force.")
if "unresolved_share" in pop_all.index:
    r = pop_all.loc["unresolved_share"]
    l3.metric("Part non résolue", _pct(r["pct_orcid"]))
    l3.caption("Part de TOUS les conflits ORCID détectés ayant atteint la révision humaine.")
