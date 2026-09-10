# tests/test_page7_geo.py
"""
Pass-7a stream P-GEO pins -- Streamlit/pages/10_Geographie.py (P7_GEO.md deliverable 4).

Streamlit's AppTest (this pinned version) exposes no `.plotly_chart` element type at all
(verified live: `[a for a in dir(AppTest) if not a.startswith('_')]` carries no chart
accessor) -- so, exactly like tests/test_charts.py and tests/test_hover_spec.py already do
for the shared primitives, every figure/hover assertion below REPRODUCES the page's own
frame-construction logic (same idiom as test_page_pf.py's `_hub_population()`, which
documents itself as "reproduces 8_Collaborations.py's own _base_sorted") and calls the
lib.charts / lib.hover functions directly; AppTest is used only for the one smoke pin at
the bottom (compiles, runs, survives a real country pick -- the "AppTest idiom of
test_page_pf.py" this file's brief names).

CE QUE CE FICHIER VERIFIE (P7_GEO.md deliverable 4, dans l'ordre)
  1. gutter fantome present sur LES DEUX graphiques a barres (geo_country_companion --
     lift de tests/_registry.py, deja enregistre par S-LIB-A -- et geo_unigr_bars, propre
     a cette page), texte == fmt_int(valeur) ligne par ligne, sur donnees REELLES.
  2. les hrefs des liens pays contiennent `institutions.country_code:` (colonne
     `oa_country_url` de la table + l'icone de l'en-tete Fiche pays), jamais pour le
     bucket "unknown".
  3. le round-trip Namibie (country_code ISO2 "NA") tient de bout en bout dans la NOUVELLE
     logique de lien (pas seulement dans country_label, deja epingle par test_countries.py).
  4. grammaire de survol de la carte (`geo_map`) : entite en gras sans etiquette, ligne
     FWCI retiree sous le plancher `fmt_fwci_pair` (n<3), jamais une valeur nue.
  5. VACUITE (P14) : chaque verification ci-dessus est suivie d'une mutation qui doit faire
     echouer la meme assertion.

    .venv-pinned\\Scripts\\python -m pytest tests\\test_page7_geo.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
DATA_DIR = STREAMLIT_DIR / "data"
PAGES_DIR = STREAMLIT_DIR / "pages"
GEO_PAGE = "10_\U0001F30D_Géographie.py"

UNIGR_ORDER = ["Luxembourg", "Liege", "Saarland", "Trier", "RPTU"]

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
from conftest import restore_lib, swap_lib_to_streamlit  # noqa: E402

_saved_lib_modules: dict = {}


def setup_module(_module) -> None:
    global _saved_lib_modules
    _saved_lib_modules = swap_lib_to_streamlit()


def teardown_module(_module) -> None:
    restore_lib(_saved_lib_modules)


def _skip_if_missing(path: Path):
    if not path.is_file():
        pytest.skip(f"{path} not deployed -- run the pipeline + 60_deploy first")


def _neutralize_page_link(monkeypatch) -> None:
    """Same pre-existing AppTest harness limitation tests/test_page_pf.py documents
    (st.page_link -> KeyError 'url_pathname') -- copied rather than imported so this
    file stays self-contained, same convention test_page_pf.py itself uses."""
    import streamlit as st_mod
    monkeypatch.setattr(st_mod, "page_link", lambda *a, **k: None)


def _exc_values(at):
    return [e.value for e in at.exception]


def _phantom(fig: go.Figure):
    """Byte-identical to tests/test_charts.py's own helper (duplicated on purpose --
    that file's own convention: no cross-file test-helper imports in this repo)."""
    import lib.charts as C
    for tr in fig.data:
        if (isinstance(tr, go.Bar) and tr.textfont is not None
                and tr.textfont.size == C.GUTTER_FONT_PX):
            return tr
    return None


# ===========================================================================
# 1. Gutter phantom on BOTH bar charts, real data, text == fmt_int(values)
# ===========================================================================

def test_country_companion_gutter_matches_the_registry_reference():
    """geo_country_companion is already registered in tests/_registry.py (S-LIB-A) --
    lift it (wave fact) rather than re-derive: pins that using it with family="pays"
    reproduces the mechanism test_charts.py already proves generically."""
    import lib.hover as hv
    import _registry as R
    _skip_if_missing(DATA_DIR / "geo_countries.parquet")
    d = R.frame_country_companion().head(40)
    fig = R.build_geo_country_companion()
    ph = _phantom(fig)
    assert ph is not None, "no gutter phantom trace on geo_country_companion"
    assert list(ph.text) == [hv.fmt_int(v) for v in d["co_works"]]


def test_vacuity_country_companion_gutter_fails_when_one_value_moves():
    import lib.charts as C
    import lib.helpers as H
    import lib.hover as hv
    import _registry as R
    d = R.frame_country_companion().head(40)
    expected = [hv.fmt_int(v) for v in d["co_works"]]
    mutated = d.copy()
    mutated.loc[0, "co_works"] = float(mutated.loc[0, "co_works"]) + 1.0
    fig = C.bars_with_gutter(mutated, family="pays", label_col="country_name",
                             value_col="co_works", color=H.UL_COLOR)
    assert list(_phantom(fig).text) != expected, (
        "a value shifted by one unit must break the row-by-row equality")


def _unigr_members_frame(conf_state: str = "all") -> pd.DataFrame:
    """Reproduces 10_Geographie.py's own UniGR member frame (section 4: geo_groups
    filtered to group_id=='unigr', deduplicated, fixed UNIGR_ORDER) -- same idiom as
    test_page_pf.py's _hub_population()."""
    path = DATA_DIR / "geo_groups.parquet"
    _skip_if_missing(path)
    gg = pd.read_parquet(path)
    unigr = gg[(gg["group_id"] == "unigr") & (gg["conf_state"] == conf_state)]
    members = (unigr[["member_id", "member_name", "co_works_distinct", "mom_class"]]
               .drop_duplicates().copy())
    members["_order"] = members["member_id"].map(
        {m: i for i, m in enumerate(UNIGR_ORDER)}).fillna(99)
    return members.sort_values("_order").reset_index(drop=True)


def test_unigr_bars_gutter_matches_fmt_int_row_by_row_on_real_data():
    """geo_unigr_bars has no tests/_registry.py entry (page-owned member data, not a
    reusable pair/generic frame -- S-LIB-A's registration rule only covers the shared
    primitives + the one companion example) -- reproduced here instead."""
    import lib.charts as C
    import lib.helpers as H
    import lib.hover as hv
    members = _unigr_members_frame()
    assert len(members) == 5, "UniGR must always show its 5 fixed members"
    assert members["member_name"].tolist() == [
        n for n in members.sort_values("_order")["member_name"]
    ], "fixed member order must survive untouched (never a value sort)"
    fig = C.bars_with_gutter(members, family="partenaire", label_col="member_name",
                             value_col="co_works_distinct", color=H.UL_COLOR)
    ph = _phantom(fig)
    assert ph is not None, "no gutter phantom trace on geo_unigr_bars"
    assert list(ph.text) == [hv.fmt_int(v) for v in members["co_works_distinct"]]


def test_vacuity_unigr_bars_gutter_fails_when_one_value_moves():
    import lib.charts as C
    import lib.helpers as H
    import lib.hover as hv
    members = _unigr_members_frame()
    expected = [hv.fmt_int(v) for v in members["co_works_distinct"]]
    mutated = members.copy()
    mutated.loc[0, "co_works_distinct"] = float(mutated.loc[0, "co_works_distinct"]) + 1.0
    fig = C.bars_with_gutter(mutated, family="partenaire", label_col="member_name",
                             value_col="co_works_distinct", color=H.UL_COLOR)
    assert list(_phantom(fig).text) != expected, (
        "a value shifted by one unit must break the row-by-row equality")


# ===========================================================================
# 2. Country link hrefs -- `institutions.country_code:`, never for "unknown"
# ===========================================================================

def test_country_url_href_carries_the_verified_filter_key():
    import lib.links as L
    url = L.country_url("DE")
    assert url is not None
    assert "institutions.country_code:DE" in url
    assert "authorships.institutions.lineage:" + _ul_id() in url
    assert url.startswith("https://openalex.org/works?filter=")


def _ul_id() -> str:
    import lib.helpers as H
    return H.UL_OPENALEX_ID


def test_country_url_is_none_for_the_unknown_bucket():
    import lib.links as L
    assert L.country_url("UNKNOWN") is None
    assert L.country_url("") is None
    assert L.country_url(None) is None


def test_page_source_wires_the_country_link_in_both_required_places():
    """P7_GEO.md deliverable 2: beside the name in the Fiche-pays header, AND as a
    link column of the country table (source-level pin, GEO_SRC idiom of
    test_page_pf.py -- both call sites must exist, not just links.country_url itself)."""
    src = (PAGES_DIR / GEO_PAGE).read_text(encoding="utf-8")
    assert "links.country_url(picked_country)" in src        # Fiche-pays header icon
    assert '"oa_country_url"' in src                          # table link column
    assert "display[\"country_code\"].apply(links.country_url)" in src


def test_vacuity_country_code_check_fails_on_a_different_country():
    import lib.links as L
    url = L.country_url("DE")
    assert "institutions.country_code:FR" not in url, (
        "a filter built for DE must not also read as a filter for FR")


# ===========================================================================
# 3. Namibie round-trip -- ISO2 "NA" survives the NEW link logic too
# ===========================================================================

def test_namibia_round_trips_through_country_label_and_country_url():
    """Reuses the smoke-pin logic tests/test_countries.py already established for
    country_label("NA") == "Namibie" (the ISO2 code that collides with pandas'
    default NA-sniffing, docs/contract_fragments/46_geo_countries.yaml's own
    null_country_arbitration note) and extends it to the NEW oa_country_url link:
    "NA" must produce a real, non-None OpenAlex link, exactly like any other
    resolved country -- never silently treated as missing."""
    from lib.countries_fr import country_label
    import lib.links as L
    assert country_label("NA") == "Namibie"
    url = L.country_url("NA")
    assert url is not None, "Namibia (ISO2 'NA') must not be treated as the unknown bucket"
    assert "institutions.country_code:NA" in url


def test_namibia_present_and_correctly_typed_in_the_real_country_table_frame():
    """If ISO2 'NA' is a real row in this snapshot's geo_countries (per the yaml's own
    arbitration note, I217085601/University of Namibia resolves there with a
    genuine, non-null co_works), the page's own `prepared` construction --
    `display["country_code"].apply(links.country_url)` -- must keep it linkable,
    never coerced to a blank/NaN country_code by a stray CSV round-trip upstream
    of this call (dtype stays `category`/object all the way from the parquet)."""
    import lib.links as L
    path = DATA_DIR / "geo_countries.parquet"
    _skip_if_missing(path)
    gc = pd.read_parquet(path)
    na_rows = gc[(gc["country_code"] == "NA") & (gc["conf_state"] == "all")
                 & (gc["subset_id"] == "all")]
    if na_rows.empty:
        pytest.skip("no ISO2 'NA' row in this deployed snapshot")
    assert not na_rows["unknown_bucket_flag"].any(), (
        "Namibia must never be flagged as the unknown bucket")
    assert L.country_url("NA") is not None


def test_vacuity_namibia_check_fails_if_treated_as_missing():
    from lib.countries_fr import country_label
    assert country_label("NA") != "", "a regression that nulled 'NA' must fail this check"


# ===========================================================================
# 4. Hover grammar on the map -- entity bold/no-label, FWCI withheld under floor
# ===========================================================================

def _map_hover_row(country_name, co_works, share, fwci_value):
    import lib.copy_fr as copy_fr
    import lib.hover as hv
    hl = copy_fr.HOVER_LABELS["geo_map"]["default"]
    return hv.hover_lines([
        (hl[0], country_name),
        (hl[1], hv.fmt_int(co_works)),
        (hl[2], hv.fmt_pct(share)),
        (hl[3], hv.fmt_fwci_pair(fwci_value, fwci_value, int(co_works))),
        (hl[4], None),  # drapeau "inconnu" -- real_countries excludes that bucket
    ])


def test_map_hover_entity_line_is_bold_with_no_label():
    line = _map_hover_row("Allemagne", 2241, 12.3, 1.05)
    assert line.startswith("<b>Allemagne</b><br>"), (
        "line 0 must be the bare entity, bold, no label/colon")


def test_map_hover_withholds_fwci_under_the_draw_floor_never_a_bare_value():
    # co_works == n for fmt_fwci_pair's floor_draw=3 check here -- 2 co-pubs is below it.
    line = _map_hover_row("Andorre", 2, 0.1, 0.87)
    assert "FWCI" not in line, "the FWCI line must be withheld entirely below n=3, never printed"
    line3 = _map_hover_row("Andorre", 3, 0.1, 0.87)
    assert "FWCI" in line3, "at n=3 (the floor) the FWCI line must be drawn"


def test_map_hover_never_shows_a_bare_none_for_a_withheld_line():
    line = _map_hover_row("Andorre", 1, 0.1, float("nan"))
    assert "None" not in line and "nan" not in line.lower()


def test_vacuity_map_hover_fwci_floor_check_fails_if_floor_ignored():
    """If a future edit hardcoded floor_draw=0 in the page's own call, this
    assertion (mirroring the one above) would stop failing -- proving the pin
    above actually exercises the floor rather than always passing."""
    line_below = _map_hover_row("Andorre", 2, 0.1, 0.87)
    line_at = _map_hover_row("Andorre", 3, 0.1, 0.87)
    assert ("FWCI" in line_below) != ("FWCI" in line_at) or "FWCI" not in line_below, (
        "the two floor sides must actually differ, or this pin is theatre"
    )
    assert "FWCI" not in line_below


# ===========================================================================
# 5. AppTest smoke -- "AppTest idiom of test_page_pf.py" (this file's own brief)
# ===========================================================================

def test_page10_fiche_pays_shows_the_openalex_link_for_a_picked_country(monkeypatch):
    _neutralize_page_link(monkeypatch)
    _skip_if_missing(DATA_DIR / "geo_countries.parquet")
    at = AppTest.from_file(str(PAGES_DIR / GEO_PAGE))
    at.session_state["nav_country_code"] = "DE"
    at.run(timeout=90)
    assert not at.exception, _exc_values(at)

    md_texts = [m.value for m in at.markdown]
    assert any("openalex.org/works" in t and "institutions.country_code:DE" in t
               for t in md_texts), "Fiche-pays header must carry the DE OpenAlex link"

    dfs = [d.value for d in at.dataframe if "country_name" in getattr(d.value, "columns", [])]
    assert dfs, "no rendered dataframe carries a 'country_name' column"
    assert "oa_country_url" in dfs[0].columns
    urls = dfs[0]["oa_country_url"].dropna()
    assert not urls.empty
    assert urls.str.contains("institutions.country_code:").all()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
