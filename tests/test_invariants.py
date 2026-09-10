"""Class 1 structural invariants (plan §10). Any failure fails the run.

These are the scripted checks the cost & rigor protocol demands: no eval, no trust. They run against
whatever the active snapshot in `config.yaml` contains, so they are equally the pre-deploy gate and
the post-refresh regression suite the UL team will run after SIRIS is out of the loop.

    python -m pytest tests/ -v

Tests skip (rather than fail) when the table they check has not been built yet, so the suite is
useful mid-build.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.snapshot import load_config, resolve_snapshot  # noqa: E402

CONFIG = load_config(ROOT)
SNAPSHOT = resolve_snapshot(CONFIG, create=False)
TABLES = SNAPSHOT / "tables"


def table(name: str) -> pd.DataFrame:
    path = TABLES / f"{name}.parquet"
    if not path.exists():
        pytest.skip(f"{name}.parquet not built yet")
    return pd.read_parquet(path)


# --------------------------------------------------------------------------- snapshot integrity
def test_manifest_exists_and_covers_every_table():
    """A snapshot without its manifest is not a snapshot (§9)."""
    import json

    manifest_path = SNAPSHOT / "MANIFEST.json"
    assert manifest_path.exists(), f"no MANIFEST.json in {SNAPSHOT}"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded = {
        Path(entry["path"]).name
        for step in manifest["steps"].values()
        for entry in step.get("files", [])
    }
    on_disk = {p.name for p in TABLES.glob("*.parquet")}
    unrecorded = on_disk - recorded
    assert not unrecorded, f"tables on disk with no manifest entry: {sorted(unrecorded)}"


# --------------------------------------------------------------------------- the pull
def test_works_primary_key_unique():
    works = table("works")
    assert works["work_id"].is_unique
    assert works["work_id"].notna().all()


def test_perimeter_size_within_band():
    """§10: corpus size drift beyond 25% is 'investigate'. Measured expectation is 46,404."""
    works = table("works")
    expected = CONFIG["perimeter"]["expected_works_a"]
    drift = abs(len(works) - expected) / expected
    assert drift < 0.25, f"pull is {len(works):,} vs expected {expected:,} ({drift:.1%} drift)"


def test_every_work_has_a_provenance_flag():
    works = table("works")
    assert works["via_lineage"].all(), "a work entered the perimeter with no provenance route"


def test_authorship_truncation_is_repaired():
    """D34: no stored record may show fewer institutions than OpenAlex counted on the full record."""
    works = table("works")
    incomplete = works[works["institutions_incomplete"]]
    assert incomplete.empty, (
        f"{len(incomplete):,} works still carry the list-endpoint authorship cut, e.g. "
        f"{incomplete['work_id'].head(3).tolist()}"
    )


def test_every_work_has_at_least_one_authorship():
    works, authorships = table("works"), table("authorships")
    orphans = set(works["work_id"]) - set(authorships["work_id"])
    assert not orphans, f"{len(orphans):,} works have no authorship row"


def test_authorship_foreign_keys_resolve():
    works, authorships = table("works"), table("authorships")
    assert set(authorships["work_id"]) <= set(works["work_id"])


# --------------------------------------------------------------------------- the corpus
def test_no_preprints_survive():
    """D10: preprints are excluded entirely, with no manual dedup list."""
    corpus = table("corpus")
    assert not (corpus["type"] == "preprint").any()


def test_corpus_doc_types_match_config():
    corpus = table("corpus")
    assert set(corpus["type"].unique()) <= set(CONFIG["corpus_filter"]["doc_types_keep"])


def test_no_retracted_or_paratext_in_corpus():
    corpus = table("corpus")
    assert not corpus["is_retracted"].fillna(False).any()
    assert not corpus["is_paratext"].fillna(False).any()


def test_corpus_years_inside_window():
    corpus = table("corpus")
    assert corpus["publication_year"].between(
        CONFIG["window"]["year_from"], CONFIG["window"]["year_to"]
    ).all()


def test_corpus_is_a_subset_of_the_pull():
    assert set(table("corpus")["work_id"]) <= set(table("works")["work_id"])


# --------------------------------------------------------------------------- abstracts
def test_abstract_provenance_is_always_recorded():
    corpus = table("corpus_abstracts")
    with_text = corpus[corpus["abstract"].notna()]
    assert with_text["abstract_source"].notna().all(), "an abstract with no recorded source"
    allowed = {"openalex", "hal", "openaire", "hal_structure_doi", "hal_structure_title"}
    assert set(with_text["abstract_source"].unique()) <= allowed


def test_abstract_chars_matches_the_text():
    corpus = table("corpus_abstracts")
    recomputed = corpus["abstract"].str.len().fillna(0).astype(int)
    assert (corpus["abstract_chars"] == recomputed).all()


def test_abstract_coverage_did_not_fall_below_v1():
    """§10: a FALL in abstract coverage is always suspicious. v1's effective coverage was 80.1%."""
    corpus = table("corpus_abstracts")
    coverage = corpus["abstract"].notna().mean()
    assert coverage >= CONFIG["baselines_v1"]["abstract_coverage_v1_effective"], (
        f"coverage {coverage:.1%} is below v1's effective {CONFIG['baselines_v1']['abstract_coverage_v1_effective']:.1%}"
    )


# --------------------------------------------------------------------------- indicators
def test_baseline_reproduces_ten_percent_inside_france():
    """The threshold must select ~10% of the FRENCH population — that is its definition.

    Deliberately NOT a test on Lorraine's share. Measured 2026-08-11: Lorraine sits at 20.4% against
    the French baseline and 13.5% on OpenAlex's global one, because the French reference carries 207k
    largely uncited conference papers and HAL deposits. Testing Lorraine against 10% would assert
    that a research-intensive university cannot outperform its national baseline.
    """
    strata = table("france_baseline_strata")
    thick = strata[~strata["is_thin"]]
    band = CONFIG["audit"]["pptop_share_per_year"]
    tolerance = band["tolerance_pts"] / 100
    offenders = {}
    for year, block in thick.groupby("publication_year"):
        share = (block["fr_share_top10"] * block["n"]).sum() / block["n"].sum()
        if abs(share - band["target"]) > tolerance:
            offenders[int(year)] = round(float(share), 4)
    assert not offenders, (
        f"the top-10% threshold does not select {band['target']:.0%} +/- {tolerance:.0%} of French "
        f"works in {offenders} — the baseline itself is wrong"
    )


def test_pptop_has_no_year_gradient():
    """v1's actual defect was a monotone SLIDE across years (15.4% -> 2.5%), not its level."""
    metrics = table("corpus_metrics")
    computed = metrics[metrics["indicator_status"] == "computed"]
    shares = {
        int(year): float(block["PPtop10_FR"].astype(float).mean())
        for year, block in computed.groupby("publication_year")
    }
    spread = (max(shares.values()) - min(shares.values())) * 100
    limit = CONFIG["audit"]["pptop_year_spread_max_pts"]
    assert spread <= limit, (
        f"PPtop10 share spans {spread:.1f} pts across years ({shares}), above the {limit} pt limit — "
        f"v1's pooled-percentile gradient may have returned"
    )


def test_indicators_are_null_in_thin_strata():
    metrics = table("corpus_metrics")
    thin = metrics[metrics["indicator_status"] != "computed"]
    assert thin["FWCI_FR"].isna().all(), "an indicator was computed on a thin or missing stratum"


def test_no_impossible_indicator_values():
    metrics = table("corpus_metrics")
    assert (metrics["cited_by_count"] >= 0).all()
    assert (metrics["FWCI_FR"].dropna() >= 0).all()
    percentile = metrics["cnp_value"].dropna()
    assert percentile.between(0, 1).all(), "citation_normalized_percentile outside [0,1]"


# --------------------------------------------------------------------------- master table
def test_in_isite_is_a_subset_of_the_isite_doi_list():
    """§10: In_ISITE must never flag a work outside the canonical list (D21)."""
    works = table("works_master")
    isite = pd.read_excel(ROOT / CONFIG["paths"]["manual_inputs"] / CONFIG["isite"]["doi_list_file"])
    listed = {
        re.sub(r"^https?://(dx\.)?doi\.org/", "", str(d).strip().lower())
        for d in isite["doi"].dropna()
    }
    flagged = set(works.loc[works["In_ISITE"], "doi"].dropna())
    assert flagged <= listed, f"{len(flagged - listed):,} In_ISITE works are not in the ISITE list"


def test_every_lab_appears_or_is_reported_zero():
    """§6: a lab silently vanishing is the failure mode R3 warns about."""
    works = table("works_master")
    labs = pd.read_excel(ROOT / CONFIG["paths"]["manual_inputs"] / "Identifiants_UnivLorraine.xlsx")
    named = {n for cell in works["Labs"].dropna() for n in str(cell).split(" | ")}
    expected = {r.Laboratoire for r in labs.itertuples() if pd.notna(r.OpenAlex)}
    declared_empty = set(CONFIG["perimeter"].get("known_empty_labs") or [])
    missing = expected - named - declared_empty
    # A lab with genuinely no output is a fact about the client's list, not a pipeline error — but it
    # must be DECLARED in config.perimeter.known_empty_labs, so that a lab disappearing for any other
    # reason still fails loudly (risk R3).
    assert not missing, (
        f"{len(missing)} labs from the client list have zero works and are not declared as known-empty: "
        f"{sorted(missing)}"
    )


def test_lab_table_has_a_row_for_every_listed_lab():
    """Even a zero-work lab must appear in the table, so it is visibly zero rather than absent."""
    lab_table = table("ul_labs")
    labs = pd.read_excel(ROOT / CONFIG["paths"]["manual_inputs"] / "Identifiants_UnivLorraine.xlsx")
    expected = {r.Laboratoire for r in labs.itertuples() if pd.notna(r.OpenAlex)}
    assert expected <= set(lab_table["lab"]), f"missing lab rows: {sorted(expected - set(lab_table['lab']))}"


def test_no_topic_model_columns_remain():
    """D9 / §6: zero topic-model dependency anywhere in the pipeline output."""
    works = table("works_master")
    banned = re.compile(r"classic tm|research topic|objective \d|method \d|impact \d|tm_label", re.I)
    offenders = [c for c in works.columns if banned.search(c)]
    assert not offenders, f"topic-model columns survived: {offenders}"


def test_matched_lab_rors_uses_the_house_separator():
    """
    FIX-1 pass-6 fix round (S-LENS WATCH, docs/VIZ_BACKLOG_pass6.md #17):
    `matched_lab_rors` used to be `";"`-joined at pull time (pipeline/10_pull_lorraine.py),
    the one multi-value blob column in the house that did not follow the `" | "`
    convention every sibling (`Labs`, `Poles`) already uses. Zero consumers today, but the
    same landmine SHAPE as the 16.4% `ptn_labs` corruption (a naive separator mismatch under
    a split/zip) -- pinned so a future consumer never inherits the trap. The CURRENT snapshot
    was patched in place (lossless separator normalisation, verified row-by-row) rather than
    re-derived from a fresh pull; the pull-time source is fixed for every future snapshot."""
    works = table("works_master")
    col = works["matched_lab_rors"].dropna()
    assert not col.str.contains(";").any(), (
        "matched_lab_rors still carries a bare ';' -- the house separator is ' | '"
    )
    multi_valued = col[col.str.contains(r"\|", regex=True)]
    assert len(multi_valued) > 0, "expected >=1 multi-ROR row to exercise the separator"
    # round-trip: splitting on the house separator must reproduce a non-empty ROR list,
    # never an accidental empty string from a stray/duplicated separator.
    assert multi_valued.str.split(" | ", regex=False).apply(lambda v: all(s for s in v)).all()
