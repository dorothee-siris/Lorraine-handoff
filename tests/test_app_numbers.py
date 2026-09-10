"""
Stream E — Tier A eval suite (D48, BUILD_PLAN "Stream E — Eval suite").

The number each page DISPLAYS must equal an INDEPENDENT fresh groupby on
`works_master.parquet` / `corpus_authorships.parquet` -- never via the app's own
`lib/*.py` code, and never via a deployed AGGREGATE table (`ul_labs`, `ul_partners`,
`thematic_overview`, ...). Those are Stream B's job (`tests/test_contract_tables.py`
recomputes against the DEPLOYED tables); this file recomputes against the RAW
snapshot tables and compares against what a human read off the RENDERED page.

Golden sample: `tests/golden/app_numbers_golden.csv`, built once by
`tests/ui/build_golden.py` (a live Playwright session against the real running
app) and checked in. Its `displayed_value` column is frozen at that moment -- it
needed a browser to read. This file recomputes `recomputed_value` FRESH every run
from the raw tables and asserts it still equals the frozen `displayed_value`; if
the underlying data ever drifts, THIS is what catches it, not a comparison of two
numbers both baked into the CSV.

Two lookups are explicitly allowed and documented as lookups, never as the
metric's source of truth:
  * `ul_descendants.parquet`  -- resolves a hors-liste structure's display name to
    its OpenAlex institution id (a dictionary, like Stream B's use of `all_topics`).
  * `ul_partners.parquet` / `works_master.Labs` -- resolve a partner's display name
    and a lab's short name to work-level filters. The COUNTS themselves are always
    recomputed from `corpus_authorships` + `works_master`.

Run:  python -m pytest tests/test_app_numbers.py -v
"""
from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.snapshot import load_config, resolve_snapshot  # noqa: E402

CONFIG = load_config(ROOT)
SNAPSHOT = resolve_snapshot(CONFIG, create=False)
TABLES = SNAPSHOT / "tables"
# Overridable via env var ONLY so `tests/ui/seeded_failure_demo.py` (D48's
# "prove the suite can fail" requirement) can point a real subprocess pytest
# run at a corrupted TEMP COPY without ever touching the committed golden CSV.
GOLDEN_CSV = Path(os.environ.get("APP_NUMBERS_GOLDEN_CSV",
                                  ROOT / "tests" / "golden" / "app_numbers_golden.csv"))

NA_MARK = "n/a"  # lib/helpers.NA_MARK, duplicated as a literal: D53's contract, not an implementation detail


# =============================================================================
# raw data (module-scoped, loaded once)
# =============================================================================

def _read(name: str) -> pd.DataFrame:
    path = TABLES / name
    if not path.exists():
        pytest.skip(f"{name} not found in snapshot tables/ -- run the pipeline first")
    return pd.read_parquet(path)


_works_cache: dict = {}


def works_master() -> pd.DataFrame:
    if "wm" not in _works_cache:
        _works_cache["wm"] = _read("works_master.parquet")
    return _works_cache["wm"]


def corpus_authorships() -> pd.DataFrame:
    if "ca" not in _works_cache:
        _works_cache["ca"] = _read("corpus_authorships.parquet")
    return _works_cache["ca"]


def ul_descendants() -> pd.DataFrame:
    """Lookup only: resolves a hors-liste structure's OpenAlex id. Never the count source."""
    if "desc" not in _works_cache:
        _works_cache["desc"] = _read("ul_descendants.parquet")
    return _works_cache["desc"]


def own_institution_ids() -> set:
    """UL + every curated/hors-liste descendant -- used only to EXCLUDE self-affiliation
    rows when recomputing a partner's co-publication count (a partner is, by definition,
    an outside institution)."""
    desc = ul_descendants()
    ids = set(desc["openalex_id"].dropna())
    ids.add(CONFIG["perimeter"]["ul_openalex_id"])
    return ids


# =============================================================================
# independent recompute functions (raw tables only -- imported by
# tests/ui/build_golden.py too, so builder and test share one definition)
# =============================================================================

def recompute_lab_pubs_total(lab: str) -> int:
    """Curated structures / poles: `Labs`/`Poles` name them directly (D52's own
    per-work columns), so this is a straight membership count -- no aggregate read."""
    wm = works_master()
    if lab == "NO LAB":
        return int((wm["Labs"] == "NO LAB").sum())
    in_labs = wm["Labs"].fillna("").str.split(" | ", regex=False).apply(lambda ls: lab in ls)
    in_poles = wm["Poles"].fillna("").str.split(" | ", regex=False).apply(lambda ls: lab in ls)
    return int((in_labs | in_poles).sum())


def recompute_lab_international_count(lab: str) -> int:
    wm = works_master()
    in_labs = wm["Labs"].fillna("").str.split(" | ", regex=False).apply(lambda ls: lab in ls)
    return int(wm.loc[in_labs, "Is_international"].fillna(False).sum())


def recompute_hors_liste_pubs_total(openalex_id: str) -> int:
    """
    A D56 hors-liste structure is NOT named in `works_master.Labs` (Stream C
    finding #5, progress/C_app.md), so its count cannot come from the same
    membership filter as a curated lab. Recomputed instead straight from
    `corpus_authorships`, restricted to work_ids already in the corpus
    (`works_master`) -- i.e. the same two raw tables, just a different join key.
    """
    wm = works_master()
    ca = corpus_authorships()
    corpus_ids = set(wm["work_id"])
    matched = ca.loc[ca["institution_id"] == openalex_id, "work_id"]
    return int(len(set(matched) & corpus_ids))


def recompute_subfield_pubs_total(subfield_id: str) -> int:
    wm = works_master()
    return int((wm["primary_subfield_id"] == str(subfield_id)).sum())


def recompute_subfield_fwci_median(subfield_id: str) -> Optional[float]:
    """None (never 0) when no work in this subfield has `indicator_status == 'computed'` (D53)."""
    wm = works_master()
    block = wm[(wm["primary_subfield_id"] == str(subfield_id)) & (wm["indicator_status"] == "computed")]
    if block.empty:
        return None
    return round(float(block["FWCI_FR"].median()), 4)


def recompute_domain_fwci_median(domain_id: str) -> Optional[float]:
    wm = works_master()
    block = wm[(wm["primary_domain_id"] == str(domain_id)) & (wm["indicator_status"] == "computed")]
    if block.empty:
        return None
    return round(float(block["FWCI_FR"].median()), 4)


def recompute_partner_co_works(lab: str, partner_openalex_id: str) -> int:
    """
    Co-publication count between a lab and an outside partner, straight from
    `corpus_authorships` restricted to (a) that lab's own work_ids (from
    `works_master.Labs`, a per-work column, not an aggregate) and (b) the
    partner's institution_id. `own_institution_ids()` guards against ever
    counting a UL sub-structure as its own "partner" (self-affiliation rows are
    common because a multi-lab work lists every affiliated structure).
    """
    wm = works_master()
    ca = corpus_authorships()
    assert partner_openalex_id not in own_institution_ids(), (
        f"{partner_openalex_id} is a UL-family institution, not an outside partner"
    )
    lab_work_ids = set(wm.loc[wm["Labs"].fillna("").str.split(" | ", regex=False)
                              .apply(lambda ls: lab in ls), "work_id"])
    sub = ca[(ca["work_id"].isin(lab_work_ids)) & (ca["institution_id"] == partner_openalex_id)]
    return int(sub["work_id"].nunique())


def recompute_creat_thin_stratum_count() -> int:
    """
    CREAT's 'Works excluded (thin stratum)' count -- a real, non-zero D53
    disclosure case measured directly against works_master (19 computed + 1
    thin_stratum out of 20 works). Page-1's per-structure PPtop10%/PPtop1% KPI
    counts are NOT a valid D53 example here: they are legitimate zero COUNTS
    (0 of 19 computed works flagged top-10%), not a null aggregate -- confirmed
    by checking `ul_labs_wide.parquet` has no null KPI for any structure with
    pubs_total > 0 in this snapshot (the null path only fires for a
    zero-publication structure, which page 1 short-circuits before any KPI
    renders at all). The real, exercised D53 case in this app is at the
    subfield/domain level (see Horticulture / Unclassified below).
    """
    wm = works_master()
    in_labs = wm["Labs"].fillna("").str.split(" | ", regex=False).apply(lambda ls: "CREAT" in ls)
    block = wm[in_labs]
    return int((block["indicator_status"] != "computed").sum())


def recompute_pptop10_share_by_year() -> pd.Series:
    """
    D40: the percentile-RANK PPtop10 share, per publication year, over works whose
    `indicator_status == 'computed'` only (never a 0-filled denominator, D53).
    """
    wm = works_master()
    computed = wm[wm["indicator_status"] == "computed"]
    return computed.groupby("publication_year")["PPtop10_FR"].mean()


# =============================================================================
# golden CSV
# =============================================================================

def _num(s: str) -> float:
    """'2,188' / '2 188' (FR, pass 5) / '15.4%' / '0.938' -> float.
    Raises on genuinely non-numeric input."""
    return float(
        str(s).replace(" ", "").replace(" ", "").replace(" ", "")
        .replace(",", "").replace("%", "").strip()
    )


def load_golden() -> list[dict]:
    """
    Returns [] when the golden CSV does not exist yet, rather than failing --
    this module is imported by `tests/ui/build_golden.py` (to share the
    recompute functions) BEFORE that CSV is written on a first run, and a
    module-level `@pytest.mark.parametrize` call must not blow up at import
    time. Real absence is caught loudly by `test_golden_csv_exists_and_populated`
    below, which any live pytest run always collects.
    """
    if not GOLDEN_CSV.exists():
        return []
    with GOLDEN_CSV.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _rows(metric_prefix: str) -> list[dict]:
    return [r for r in load_golden() if r["metric"].startswith(metric_prefix)]


def test_golden_csv_exists_and_populated():
    """The one test that fails loudly (instead of silently collecting zero
    parametrized cases) when nobody has run `tests/ui/build_golden.py` yet."""
    assert GOLDEN_CSV.exists(), (
        f"{GOLDEN_CSV} does not exist -- run `python tests/ui/build_golden.py` "
        "once against the live app to create it"
    )
    all_rows = load_golden()
    assert len(all_rows) >= 30, f"expected >= 30 golden rows (15 entities x ~2 metrics + extras), found {len(all_rows)}"


# =============================================================================
# Tier A -- 5 labs x 5 subfields x 5 partners (D48)
# =============================================================================

@pytest.mark.parametrize("row", _rows("lab_pubs_total"), ids=lambda r: r["entity"])
def test_lab_pubs_total_matches_page(row):
    lab = row["entity"]
    if lab == "NO LAB":
        recomputed = recompute_lab_pubs_total("NO LAB")
    elif row["note"].startswith("hors-liste"):
        openalex_id = row["note"].split("openalex_id=")[-1].strip()
        recomputed = recompute_hors_liste_pubs_total(openalex_id)
    else:
        recomputed = recompute_lab_pubs_total(lab)
    displayed = int(_num(row["displayed_value"]))
    assert recomputed == displayed, (
        f"{lab}: page displayed {displayed:,} publications, independent recompute "
        f"from works_master/corpus_authorships gives {recomputed:,}"
    )


@pytest.mark.parametrize("row", _rows("lab_international_count"), ids=lambda r: r["entity"])
def test_lab_international_count_matches_page(row):
    lab = row["entity"]
    if row["note"].startswith("hors-liste") or lab == "NO LAB":
        pytest.skip(f"{lab}: international KPI not independently recomputable outside curated Labs/Poles columns")
    recomputed = recompute_lab_international_count(lab)
    displayed = int(_num(row["displayed_value"]))
    assert recomputed == displayed, (
        f"{lab}: page displayed {displayed:,} international publications, recompute gives {recomputed:,}"
    )


@pytest.mark.parametrize("row", _rows("subfield_pubs_total"), ids=lambda r: r["entity"])
def test_subfield_pubs_total_matches_page(row):
    subfield_id = row["entity"]
    recomputed = recompute_subfield_pubs_total(subfield_id)
    displayed = int(_num(row["displayed_value"]))
    assert recomputed == displayed, (
        f"subfield {subfield_id}: page displayed {displayed:,}, recompute gives {recomputed:,}"
    )


@pytest.mark.parametrize("row", _rows("subfield_fwci_median"), ids=lambda r: r["entity"])
def test_subfield_fwci_median_matches_page(row):
    subfield_id = row["entity"]
    recomputed = recompute_subfield_fwci_median(subfield_id)
    if row["displayed_value"].strip().lower() == NA_MARK:
        # D53: a subfield with NO computed-indicator work must show n/a, never 0 or 0.0.
        assert recomputed is None, (
            f"subfield {subfield_id}: page shows '{NA_MARK}' but an independent recompute "
            f"found a computable median ({recomputed}) -- the page is hiding real data"
        )
    else:
        displayed = _num(row["displayed_value"])
        assert recomputed is not None, (
            f"subfield {subfield_id}: page displays a numeric median ({displayed}) but "
            "recompute finds no computed-indicator work at all"
        )
        assert abs(recomputed - displayed) < 0.01, (
            f"subfield {subfield_id}: page displayed {displayed}, recompute gives {recomputed}"
        )


@pytest.mark.parametrize("row", _rows("partner_co_works"), ids=lambda r: r["entity"])
def test_partner_co_works_matches_page(row):
    lab, partner_id = row["entity"].split("|")
    recomputed = recompute_partner_co_works(lab, partner_id)
    displayed = int(_num(row["displayed_value"]))
    assert recomputed == displayed, (
        f"{lab} x {partner_id}: page displayed {displayed:,} co-publications, recompute gives {recomputed:,}"
    )


# =============================================================================
# D53 -- a null indicator renders "n/a", NEVER 0 (structure-level, page 1)
# =============================================================================

def test_d53_thin_stratum_structure_disclosure_matches_recompute():
    """
    CREAT (20 works, exactly 1 thin-stratum -- verified independently here) is
    the D48-mandated 'row with indicator_status != computed' example at
    structure level. D53 bans rendering a null aggregate as a fabricated 0; the
    concrete way that shows up on page 1 is the 'Works excluded' disclosure
    caption, which must name the true count -- never silently read 0 or vanish.
    (CREAT's PPtop10%/PPtop1% KPI counts are a real, computed 0 -- 0 of its 19
    *computed* works are top-10% -- not a D53 case; see
    `recompute_creat_thin_stratum_count`'s docstring.)
    """
    n_excluded = recompute_creat_thin_stratum_count()
    assert n_excluded > 0, "CREAT has no thin/no-stratum work -- pick a different D53 example"

    rows = [r for r in load_golden() if r["entity"] == "CREAT" and r["metric"] == "d53_excluded_disclosure"]
    assert rows, "golden CSV has no CREAT d53_excluded_disclosure row -- rerun build_golden.py"
    displayed = rows[0]["displayed_value"].strip()
    assert displayed != "MISSING", "CREAT's 'Works excluded' disclosure caption was not found on the page at all"
    assert displayed not in ("0", "0.0"), (
        f"CREAT's disclosure displayed {displayed!r} but the true excluded count is {n_excluded} -- "
        "a thin-stratum work is being silently absorbed as if it were 0"
    )
    assert int(displayed) == n_excluded, (
        f"CREAT's disclosure displayed {displayed!r}, independent recompute gives {n_excluded}"
    )


def test_d53_no_stratum_subfield_never_renders_zero():
    """Horticulture (subfield 1108): every single work is `no_stratum` (0 of N computed).
    This is the harder D53 case -- an ENTIRE subfield with nothing to average."""
    wm = works_master()
    block = wm[wm["primary_subfield_id"] == "1108"]
    assert not block.empty, "subfield 1108 (Horticulture) has no works in this snapshot -- pick another"
    assert (block["indicator_status"] != "computed").all(), (
        "Horticulture is expected to be a NO-computed-work subfield; the snapshot has drifted"
    )
    rows = [r for r in load_golden() if r["entity"] == "1108" and r["metric"] in
            ("subfield_fwci_median", "subfield_pct_top10_display")]
    assert rows, "golden CSV has no Horticulture null-indicator row -- rerun build_golden.py"
    for r in rows:
        assert r["displayed_value"].strip().lower() == NA_MARK, (
            f"Horticulture's {r['metric']} rendered {r['displayed_value']!r}, expected '{NA_MARK}'"
        )


# =============================================================================
# FWCI gradient -- rendered treemap colour vs the app's own declared colourscale
# =============================================================================

def test_fwci_gradient_colours_match_declared_scale():
    """
    For 5 points across the scale (4 domains + the null Unclassified domain),
    the treemap's ACTUAL rendered SVG fill (captured once via Playwright by
    build_golden.py, from `g.slice text` + `path.surface style`) must equal the
    colour a fresh interpolation of the app's OWN declared `color_continuous_scale`
    produces for an INDEPENDENTLY recomputed FWCI median -- not the value the page
    happened to use, a value recomputed here from works_master straight up.

    The 5th point, Unclassified (no computed work at all), is the D53 case for
    colour: it must NOT render as if fwci=0, which the scale maps to red
    (#EC8773) -- Plotly's null-marker default (dark grey) is what's expected.
    """
    ui_dir = str(ROOT / "tests" / "ui")
    if ui_dir not in sys.path:
        sys.path.insert(0, ui_dir)
    from _colorscale import read_declared_scale, expected_rgb, parse_rgb, rgb_close  # noqa: E402

    stops, value_range = read_declared_scale()
    rows = _rows("fwci_gradient_fill")
    assert len(rows) >= 5, f"expected >=5 fwci_gradient_fill golden rows, found {len(rows)}"

    for row in rows:
        domain_id = row["entity"]
        displayed_rgb = parse_rgb(row["displayed_value"])
        assert displayed_rgb is not None, f"domain {domain_id}: golden fill {row['displayed_value']!r} did not parse as rgb(...)"

        if domain_id == "0":
            # Unclassified: no computed work anywhere -- D53 colour ban.
            recomputed = recompute_domain_fwci_median("0")
            assert recomputed is None, "Unclassified domain unexpectedly has a computable FWCI median now"
            zero_rgb = expected_rgb(0.0, stops, value_range)  # what a fabricated fwci=0 WOULD look like
            assert not rgb_close(displayed_rgb, zero_rgb, tol=3), (
                f"Unclassified rendered {displayed_rgb}, which matches the scale's fwci=0 colour "
                f"{zero_rgb} -- a null indicator is being rendered as a measured zero (D53 breach)"
            )
            continue

        recomputed_fwci = recompute_domain_fwci_median(domain_id)
        assert recomputed_fwci is not None, f"domain {domain_id}: expected a computable FWCI median"
        expected = expected_rgb(recomputed_fwci, stops, value_range)
        assert rgb_close(displayed_rgb, expected, tol=2), (
            f"domain {domain_id} (recomputed median FWCI={recomputed_fwci}): page rendered "
            f"{displayed_rgb}, declared-scale interpolation expects {expected}"
        )


# =============================================================================
# PPtop10 per-year band + no monotone gradient (D40)
# =============================================================================

def test_pptop10_share_within_band_and_no_year_gradient():
    """
    D40: the percentile-RANK PPtop10 definition's actual point is that ~10% is a
    property of the REFERENCE population (France), not a target Lorraine itself
    must hit -- asserting Lorraine sits at exactly 10%+/-2pts would assert Lorraine
    cannot differ from the national average, which is the opposite of what a
    benchmark is for (see the project's own D40 note: Lorraine's real, correct,
    already-verified range is 7.2-8.6%, LOWER than OpenAlex's global ~13.5%,
    which is the harder comparator). The real invariant D40 fixes is the YEAR
    GRADIENT: v1 swung 15.4% -> 2.5% (12.9-pt monotone slide); v2 must not.

    So this test enforces two things straight from works_master (never a
    deployed aggregate): a wide sanity band (5-15%) that would catch a gross
    computation error without re-asserting "Lorraine = France", and the tight,
    real check -- max-min spread across the 5 years < 3 points, with no
    monotone trend.
    """
    shares = recompute_pptop10_share_by_year()
    assert len(shares) == 5, f"expected 5 years of data, got {len(shares)}: {shares.to_dict()}"
    for year, share in shares.items():
        pct = float(share) * 100
        assert 5.0 <= pct <= 15.0, f"{year}: PPtop10 share {pct:.2f}% outside the 5-15% sanity band"
    spread = (float(shares.max()) - float(shares.min())) * 100
    assert spread < 3.0, (
        f"PPtop10 share spreads {spread:.2f} points across years {shares.to_dict()} -- "
        "a year gradient this large is exactly v1's defect (D40)"
    )
    diffs = shares.diff().dropna()
    monotone = (diffs > 0).all() or (diffs < 0).all()
    assert not monotone or spread < 3.0, (
        f"PPtop10 share moves monotonically across years AND spans >=3pts: {shares.to_dict()} "
        "-- this is the v1 year-bias pattern D40 exists to catch"
    )


# =============================================================================
# SDG panel -- displayed counts == sdg_siris.parquet aggregation (D51)
# =============================================================================

def test_sdg_panel_counts_match_sdg_siris_table():
    siris = _read("sdg_siris.parquet")
    wm = works_master()
    expected_tagged = siris["work_id"].nunique()
    expected_corpus_total = len(wm)
    expected_coverage = expected_tagged / expected_corpus_total * 100
    expected_title_only = int((siris["text_basis"] == "title_only").sum())
    expected_total_assignments = len(siris)

    rows = {r["metric"]: r for r in load_golden() if r["page"] == "Thematic_Overview" and r["metric"].startswith("sdg_")}
    assert rows, "golden CSV has no sdg_* rows -- rerun build_golden.py"

    tagged = int(_num(rows["sdg_tagged_works"]["displayed_value"]))
    corpus_total = int(_num(rows["sdg_corpus_total"]["displayed_value"]))
    coverage_pct = _num(rows["sdg_coverage_pct"]["displayed_value"])
    title_only = int(_num(rows["sdg_title_only_count"]["displayed_value"]))

    assert tagged == expected_tagged, f"panel tagged={tagged}, sdg_siris.parquet nunique(work_id)={expected_tagged}"
    assert corpus_total == expected_corpus_total, f"panel corpus_total={corpus_total}, works_master rows={expected_corpus_total}"
    assert abs(coverage_pct - expected_coverage) < 0.15, f"panel coverage={coverage_pct}%, recompute={expected_coverage:.2f}%"
    assert title_only == expected_title_only, f"panel title_only={title_only}, sdg_siris.parquet count={expected_title_only}"

    # title-only works must be DISTINGUISHABLE in the data the panel exposes (not just counted):
    # the column exists and takes both values.
    assert set(siris["text_basis"].dropna().unique()) >= {"title_abstract", "title_only"}, (
        "sdg_siris.parquet's text_basis column no longer distinguishes title-only assignments"
    )
    assert 0 < expected_title_only < expected_total_assignments, (
        "title-only assignments should be a strict, non-trivial subset of all SDG assignments"
    )
