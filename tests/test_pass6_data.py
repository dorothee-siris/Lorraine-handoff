"""tests/test_pass6_data.py -- Tier-A evals for S-DAT's pass-6 tables (BUILD_PLAN.md sec.4 eval
plan row "S-DAT sdg_lab_methods / lab tops / zero-fill / partner denominators").

Every golden here is recomputed INDEPENDENTLY from snapshot tables (works_master,
corpus_authorships, sdg_siris, corpus_sdg, all_topics, ptn_summary, idset_consortium.csv) -- never
by importing or calling the pipeline builders -- and compared against the BUILT tables. Reads the
snapshot's own tables/ dir, same pattern as tests/test_contract_tables.py.

Run:  python -m pytest tests/test_pass6_data.py -v
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
MIN_STRATUM_N = int(CONFIG["metrics"]["min_stratum_n"])
AURORA_THRESHOLD = float(CONFIG["sdg"]["openalex_metadata"]["threshold"])
NO_LAB = "NO LAB"


def table(name: str) -> pd.DataFrame:
    path = TABLES / f"{name}.parquet"
    if not path.exists():
        pytest.skip(f"{name}.parquet not built yet")
    return pd.read_parquet(path)


def sdg_number(label) -> int | None:
    match = re.search(r"(\d{1,2})", str(label))
    if not match:
        return None
    n = int(match.group(1))
    return n if 1 <= n <= 17 else None


@pytest.fixture(scope="module")
def works_labs():
    """One groupby, ALL 69 lab work-id sets at once (efficient -- avoids 69 separate
    str.split/apply passes over the 36,819-row corpus)."""
    works = pd.read_parquet(TABLES / "works_master.parquet",
                            columns=["work_id", "Labs", "is_conference"])
    exploded = works.assign(lab=works["Labs"].fillna(NO_LAB).str.split(" | ", regex=False)).explode("lab")
    lab_sets = exploded.groupby("lab")["work_id"].apply(set).to_dict()
    return works, lab_sets


# =================================================================================================
# sdg_lab_methods (P11) -- golden re-derive 10 labs x 2 methods + site-totals reconciliation
# =================================================================================================

@pytest.fixture(scope="module")
def sdg_sources():
    siris = pd.read_parquet(TABLES / "sdg_siris.parquet", columns=["work_id", "sdg"])
    aurora_raw = pd.read_parquet(TABLES / "corpus_sdg.parquet", columns=["work_id", "sdg_id", "score"])
    aurora_raw = aurora_raw[aurora_raw["score"].fillna(0) >= AURORA_THRESHOLD].copy()
    aurora_raw["sdg"] = aurora_raw["sdg_id"].map(sdg_number)
    aurora = aurora_raw[aurora_raw["sdg"].between(1, 16)][["work_id", "sdg"]].drop_duplicates()
    return siris, aurora


def test_sdg_lab_methods_golden_recompute_10_labs(works_labs, sdg_sources):
    built = table("sdg_lab_methods")
    _, lab_sets = works_labs
    siris, aurora = sdg_sources

    labs_all = sorted(lab_sets)
    sample_labs = labs_all[:5] + labs_all[-5:]  # 10 labs, both ends of the alphabetic spread
    assert len(set(sample_labs)) == 10

    built_all = built[built["conf_state"] == "all"].set_index(["lab", "sdg"])
    for lab in sample_labs:
        work_ids = lab_sets.get(lab, set())
        lab_total = len(work_ids)
        siris_lab = siris[siris["work_id"].isin(work_ids)]
        aurora_lab = aurora[aurora["work_id"].isin(work_ids)]
        n_siris_by_sdg = siris_lab.groupby("sdg")["work_id"].nunique()
        n_aurora_by_sdg = aurora_lab.groupby("sdg")["work_id"].nunique()
        for sdg in range(1, 17):
            row = built_all.loc[(lab, sdg)]
            assert int(row["lab_total_pubs"]) == lab_total, f"{lab}: lab_total_pubs mismatch"
            expected_siris = int(n_siris_by_sdg.get(sdg, 0))
            expected_aurora = int(n_aurora_by_sdg.get(sdg, 0))
            assert int(row["n_siris"]) == expected_siris, (
                f"{lab} sdg{sdg}: n_siris {row['n_siris']} != golden {expected_siris}"
            )
            assert int(row["n_aurora"]) == expected_aurora, (
                f"{lab} sdg{sdg}: n_aurora {row['n_aurora']} != golden {expected_aurora}"
            )


def test_sdg_lab_methods_site_totals_reconcile(works_labs, sdg_sources):
    """Site totals (union of all 69 labs' tagged work-sets) must reconcile with the shipped
    page-4 site panel's own source (sdg_three_way.B_siris -- the default D51 variant every SDG
    panel on the app reads)."""
    _, lab_sets = works_labs
    siris, aurora = sdg_sources
    sdg_three_way = pd.read_parquet(TABLES / "sdg_three_way.parquet", columns=["work_id", "B_siris"])

    exploded = sdg_three_way.dropna(subset=["B_siris"]).assign(
        sdg=sdg_three_way["B_siris"].str.split()
    ).explode("sdg")
    exploded["sdg"] = pd.to_numeric(exploded["sdg"], errors="coerce")
    exploded = exploded.dropna(subset=["sdg"]).astype({"sdg": int})
    site_totals_siris = exploded.groupby("sdg")["work_id"].nunique()

    for sdg in range(1, 17):
        tagged = set(siris.loc[siris["sdg"] == sdg, "work_id"])
        union_labs = set()
        for ids in lab_sets.values():
            union_labs |= (ids & tagged)
        assert union_labs == tagged, f"sdg{sdg}: union-of-labs != SIRIS's own tagged set"
        assert len(tagged) == int(site_totals_siris.get(sdg, 0)), (
            f"sdg{sdg}: sdg_siris tagged count {len(tagged)} != sdg_three_way.B_siris panel "
            f"source {int(site_totals_siris.get(sdg, 0))}"
        )

    for sdg in range(1, 17):
        tagged = set(aurora.loc[aurora["sdg"] == sdg, "work_id"])
        union_labs = set()
        for ids in lab_sets.values():
            union_labs |= (ids & tagged)
        assert union_labs == tagged, f"Aurora sdg{sdg}: union-of-labs != Aurora's own tagged set"


# =================================================================================================
# lab tops (P6-R6/#34) -- 3 labs hand-verified incl. one big-team-paper lab
# =================================================================================================

def test_lab_top_partners_hand_verify_3_labs(works_labs):
    """Recompute top-3 international partners for 3 labs independently from corpus_authorships,
    compare to the deployed lab_top_partners rows 1-3."""
    built = table("lab_top_partners")
    works, lab_sets = works_labs
    authorships = pd.read_parquet(TABLES / "corpus_authorships.parquet",
                                  columns=["work_id", "institution_id", "institution_ror",
                                          "institution_country"])
    descendants = pd.read_parquet(TABLES / "ul_descendants.parquet")
    labs_list = pd.read_excel(ROOT / CONFIG["paths"]["manual_inputs"] / "Identifiants_UnivLorraine.xlsx")
    labs_list = labs_list.rename(columns={labs_list.columns[0]: "Pole"})
    repairs = CONFIG["perimeter"].get("openalex_id_repairs") or {}
    curated_ids = {repairs.get(str(x).strip(), str(x).strip()) for x in labs_list["OpenAlex"].dropna()}
    curated_rors = {str(x).strip().lower() for x in labs_list["ROR"].dropna()}
    partner_own_ids = curated_ids | set(descendants["openalex_id"]) | {CONFIG["perimeter"]["ul_openalex_id"]}
    partner_own_rors = curated_rors | {r for r in descendants["ror"].dropna()} | {CONFIG["perimeter"]["ul_ror"]}

    biggest_lab = max((l for l in lab_sets if l != NO_LAB), key=lambda l: len(lab_sets[l]))
    check_labs = [biggest_lab, NO_LAB, sorted(lab_sets)[len(lab_sets) // 3]]

    for lab in check_labs:
        work_ids = lab_sets[lab]
        partner_auth = authorships[
            authorships["work_id"].isin(work_ids)
            & authorships["institution_id"].notna() & authorships["institution_ror"].notna()
            & ~authorships["institution_id"].isin(partner_own_ids)
            & ~authorships["institution_ror"].isin(partner_own_rors)
        ].drop_duplicates(["work_id", "institution_id"])
        intl = partner_auth[partner_auth["institution_country"] != "FR"]
        # P7 fix: a bare sort_values(ascending=False) has no secondary key, so a genuine tie in
        # copubs resolves by whatever the pandas/numpy quicksort happens to do -- NOT stable across
        # versions (reproduced: pandas 2.1.4 vs 2.3.3 disagree on Georessources rank 1, both counts
        # =18). Deterministic tie-break, matching the same fix in
        # pipeline/43c_build_lab_tops.py::build_lab_top_partners: count desc, then institution_id asc.
        counts = intl.groupby("institution_id").size().rename("copubs").reset_index()
        top3 = (counts.sort_values(["copubs", "institution_id"], ascending=[False, True], kind="stable")
                      .head(3).set_index("institution_id")["copubs"])

        built_rows = built[(built["lab"] == lab) & (built["scope"] == "international")
                          & (built["rank"] <= 3)].sort_values("rank")
        assert len(built_rows) == len(top3), f"{lab}: top-3 international row count mismatch"
        for (inst_id, copubs), (_, row) in zip(top3.items(), built_rows.iterrows()):
            assert row["partner_id"] == inst_id, f"{lab} rank {row['rank']}: partner_id mismatch"
            assert int(row["copubs"]) == int(copubs), f"{lab} rank {row['rank']}: copubs mismatch"


def test_lab_top_authors_big_team_work_lands_correctly(works_labs):
    """The corpus's largest-author-count work (D34-class hand-check): its lab attribution and its
    contribution to that lab's author ranking must be internally consistent -- no author dropped,
    none duplicated, matching the native long-table structure (no v1-style positional parsing)."""
    authorships = pd.read_parquet(TABLES / "corpus_authorships.parquet",
                                  columns=["work_id", "author_id", "orcid", "institution_id"])
    counts = authorships.groupby("work_id")["author_id"].nunique().sort_values(ascending=False)
    big_work, n_authors = counts.index[0], int(counts.iloc[0])
    assert n_authors >= 400, f"expected a 400+-author work at the top, got {n_authors}"

    block = authorships[authorships["work_id"] == big_work]
    assert block["author_id"].nunique() == n_authors, "author count drifted between passes"
    with_orcid = block.dropna(subset=["orcid"])
    per_author_orcid_count = with_orcid.groupby("author_id")["orcid"].nunique()
    assert (per_author_orcid_count <= 1).all(), (
        f"{big_work}: an author_id carries >1 distinct orcid -- D34-class misalignment"
    )

    works = pd.read_parquet(TABLES / "works_master.parquet", columns=["work_id", "Labs"])
    big_work_labs = str(works.set_index("work_id").loc[big_work, "Labs"] or "")
    lab_works = table("lab_works")
    for lab in (big_work_labs.split(" | ") if big_work_labs else [NO_LAB]):
        lab = lab if lab else NO_LAB
        assert ((lab_works["lab"] == lab) & (lab_works["work_id"] == big_work)).any(), (
            f"{big_work} missing from lab_works for lab {lab!r}"
        )


# =================================================================================================
# zero-fill (#20) -- vocab-count + quantum-incl-0 invariants
# =================================================================================================

def test_zero_fill_row_count_equals_vocab_count():
    all_topics = pd.read_parquet(TABLES / "all_topics.parquet")
    topics_zf = table("topics_zero_fill")
    subfields_zf = table("subfields_zero_fill")
    assert len(topics_zf) == all_topics["topic_id"].nunique()
    assert len(subfields_zf) == all_topics["subfield_id"].nunique()
    assert topics_zf["topic_id"].is_unique
    assert subfields_zf["subfield_id"].is_unique


def test_zero_fill_quantum_query_includes_zero_pub_topics():
    topics_zf = table("topics_zero_fill")
    matches = topics_zf[topics_zf["topic_name"].str.contains("quantum", case=False, na=False)]
    assert len(matches) > 0, "expected >=1 'quantum' topic in the full OpenAlex vocabulary"
    zero_pub = matches[~matches["has_corpus_works"]]
    assert len(zero_pub) > 0, (
        "expected >=1 zero-UL-work 'quantum' topic to still be present (the #20 acceptance case)"
    )
    # D53: rate columns NULL, not 0, on the zero-pub rows
    assert zero_pub["pct_isite"].isna().all()
    assert (zero_pub["pubs_total"] == 0).all()
    assert (zero_pub["pubs_pct_of_ul"] == 0.0).all()


# =================================================================================================
# partner denominators (P4/#39/#40) -- bounds + exclusion + spot-check
# =================================================================================================

def test_ptn_denominators_bounds_and_exclusions():
    den = table("ptn_denominators")
    for col in ("share_of_ul_corpus", "share_of_ul_france_copubs_hors_site",
               "share_of_ul_intl_copubs", "share_of_ul_country_copubs"):
        vals = den[col].dropna()
        assert (vals >= 0).all() and (vals <= 1.0000001).all(), f"{col} out of [0,1]"

    consortium = pd.read_csv(ROOT / "inputs" / "overlays" / "idset_consortium.csv",
                             encoding="utf-8", keep_default_na=False)
    consortium_ids = set(consortium["id"])
    is_consortium = den["partner_id"].isin(consortium_ids)
    assert den.loc[is_consortium, "share_of_ul_france_copubs_hors_site"].isna().all(), (
        "consortium signatories must carry a NULL france-hors-site share"
    )
    fr_rows = den[den["country_code"] == "FR"]
    assert fr_rows["share_of_ul_intl_copubs"].isna().all()
    assert fr_rows["share_of_ul_country_copubs"].isna().all()
    intl_rows = den[den["country_code"].notna() & (den["country_code"] != "FR")]
    assert intl_rows["share_of_ul_france_copubs_hors_site"].isna().all()


def test_ptn_denominators_spot_check_independent_recompute():
    """One partner's share_of_ul_country_copubs, recomputed via an INDEPENDENT pandas path from
    ptn_summary directly (not from ptn_denominators' own construction), must match exactly."""
    den = table("ptn_denominators")
    ptn_summary = pd.read_parquet(TABLES / "ptn_summary.parquet")
    base = ptn_summary[(ptn_summary["conf_state"] == "all") & (ptn_summary["subset_id"] == "all")]

    intl = den[den["country_code"].notna() & (den["country_code"] != "FR")]
    top_country = intl["country_code"].value_counts().index[0]
    country_partner_ids = base.loc[base["country_code"] == top_country, "partner_id"]
    denom = int(base.loc[base["partner_id"].isin(country_partner_ids), "co_works_full"].sum())

    spot = intl[intl["country_code"] == top_country].iloc[0]
    expected_share = round(spot["co_works_full"] / denom, 6)
    assert abs(float(spot["share_of_ul_country_copubs"]) - expected_share) < 1e-9, (
        f"spot-check FAILED for {spot['display_name']} ({top_country}): table "
        f"{spot['share_of_ul_country_copubs']} != independent recompute {expected_share}"
    )


def test_ptn_denominators_share_of_ul_corpus_matches_corpus_size():
    den = table("ptn_denominators")
    n_corpus = pd.read_parquet(TABLES / "works_master.parquet", columns=["work_id"]).shape[0]
    sample = den.sample(min(20, len(den)), random_state=42)
    for _, row in sample.iterrows():
        expected = round(row["co_works_full"] / n_corpus, 6)
        assert abs(row["share_of_ul_corpus"] - expected) < 1e-9
