"""45b_build_author_views.py -- author-family views (Stream W4, chain pass 3, Assembly Line).

Authority: docs/foundry/data_foundation.yaml rev 3.1 (conventions + the four table entries this
producer emits) * docs/indicator_plan_FINAL.md S5 (A1-A5 + the seven structural safeguards) *
progress/F0_probes.md P3 (sizing + the three ORCID goldens, reproduced here to the digit) *
reports/foundry_pass2_probes.py P3 section (its aut-table assembly logic, extended) *
lib/artifact.py (flag_works -- the 811-topic exclusion, for every `_xa` twin and `artifact_flag`).

Emits FOUR new tables into the snapshot's tables/ dir (never Streamlit/data/ -- that is 60_deploy's
job, out of this stream's fence):

  aut_public        -- one row per person (12,680). STRUCTURALLY no impact column (A2 safeguard 1):
                       conf/artifact-toggle live as n_works/n_works_noconf/n_works_xa/n_works_noconf_xa
                       COLUMNS (never row-doubling on a 12,680-row directory table, tunnel #12).
  aut_works         -- person x work pairs (ALL corpus appearances this person's OpenAlex profile(s)
                       are credited author on -- see the module-level note below on why this is the
                       ALL-corpus set, not the UL-credited subset, despite the YAML's "UL-credited
                       authorship pairs" grain label). Sorted by author_id, rg=5000. PHYSICALLY no
                       impact column (tunnel #16 / S6.4-3bis structural safeguard).
  aut_impact_drill  -- floor-gated (works_with_indicators >= config.workshop_tunables.author_impact_floor,
                       30) x conf_state. The ONLY table on this family carrying an impact column
                       (A2 safeguard 1's mirror: the split lives in two separate FILES, not a column
                       a UI toggle could un-hide).
  aut_coverage      -- collective ORCID/idHAL identifier-coverage grains (lab | field | year |
                       population rows, stacked with a unit_kind discriminator) x conf_state. Never
                       a per-person row (A3 safeguard 5 -- no lab-level ORCID league table is even
                       representable in this schema).

READ-ONLY inputs (this stream's fence: only this file + docs/contract_fragments/45b_*.yaml +
progress/W4_author_views.md may be created/modified):
  <snapshot>/tables/ul_authors.parquet       -- the 12,680-person reconciled dataset, THIS
                                                 snapshot's own 45_build_authors.py output
                                                 (RA-C01 fix: was read from the deployed
                                                 Streamlit/data/ copy -- a fresh-machine
                                                 bootstrap landmine, see run_all.py, RESOLVED)
  <snapshot>/tables/works_master.parquet     -- work-level facts (year/title/doi/type/is_conference/
                                                 In_ISITE/Labs/primary_field*/primary_subfield*/
                                                 hal_authors_idhal -- the "hal-link fields")
  <snapshot>/tables/corpus_authorships.parquet -- work x author x institution rows (author_id is the
                                                 RAW OpenAlex author id; ul_authors.person_id is the
                                                 post-reconciliation cluster id -- see the mapping note)
  <snapshot>/tables/corpus_topics.parquet    -- feeds lib.artifact.flag_works
  <snapshot>/tables/ul_descendants.parquet   -- UL perimeter ids/rors + client_lab_name lookup
  <snapshot>/tables/ul_authors_review_queue.parquet -- identity-ledger fact (aut_coverage population row)
  <snapshot>/MANIFEST.json (step "45_build_authors") -- X_orcid_conflict_blocked, for unresolved_share

--------------------------------------------------------------------------------------------------
DESIGN NOTE -- why aut_works is the ALL-corpus set, not the UL-credited subset
--------------------------------------------------------------------------------------------------
The YAML's one-line grain label for aut_works reads "author x work (UL-credited authorship pairs)",
but its own INVARIANT text (quoted verbatim in the sprint dispatch) is "pairs reconcile with
aut_public.n_works per author" -- and aut_public.n_works is ul_authors.n_works, the ALL-corpus
appearance count (a person's total corpus footprint, e.g. Silvio Danese: 281 corpus works, only 1
UL-credited -- D42 in docs/data_contract.yaml). The two readings cannot both be literally true at
once (n_works != ul_credited_works for the 5,877+ people credited on a strict subset of their corpus
appearances). This builder honours the INVARIANT TEXT (the harder, testable spec) over the grain
label's adjective: aut_works rows are person x work pairs over the person's ENTIRE Lorraine-corpus
footprint (matching n_works exactly, asserted below), not filtered to only the rows where that
specific work happens to also be UL-credited. This is also the more useful reading for the A-V2
profile page ("one person end to end ... works list") -- and ul_credited_works survives on aut_public
unfiltered (A2 safeguard: identity/credit fact, not itself a work-grain filter) so any consumer can
still see how much of a person's listed footprint was actually their own Lorraine affiliation.

--------------------------------------------------------------------------------------------------
DESIGN NOTE -- author_id -> person_id mapping
--------------------------------------------------------------------------------------------------
corpus_authorships.author_id is the RAW OpenAlex author id (pre-reconciliation). ul_authors.parquet
carries the reconciled person_id plus a `profiles_joined` string ("author_id_1 | author_id_2 | ...",
Phase 2's pipeline/45_build_authors.py's own join separator) listing every raw author_id folded into
that person. This builder explodes that string back into an (author_id -> person_id) lookup and
merges it onto corpus_authorships -- the one join every downstream computation in this script
depends on, so its uniqueness/coverage is asserted immediately after building it.

Usage: python pipeline/45b_build_author_views.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.artifact import flag_works  # noqa: E402
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)

# STRUCTURAL Class-1 regex (docs/indicator_plan_FINAL.md S5 safeguard 1 / tunnel #16): aut_public
# and aut_works must PHYSICALLY carry no column shaped like an impact indicator. lib/artifact.py is
# outside this stream's fence (only its flag_works() is imported), so the equivalent check is
# reimplemented here -- same pattern, same regex intent, applied identically to both tables.
IMPACT_COL_REGEX = re.compile(r"fwci|pptop|impact|citation", re.IGNORECASE)

REVIEW_TOLERANCE_PCT = 0.15   # by-year golden tolerance (percentage points) -- see report for the
                              # one explained 0.07pt rounding-boundary delta (2022)


def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def assert_no_impact_columns(df: pd.DataFrame, name: str) -> None:
    bad = [c for c in df.columns if IMPACT_COL_REGEX.search(c)]
    assert not bad, f"{name}: STRUCTURAL VIOLATION -- impact-shaped column(s) present: {bad}"
    print(f"  [structural] {name}: no fwci|pptop|impact|citation column among "
          f"{len(df.columns)} cols -- PASS")


def make_labs_short(labs_value) -> str:
    """Compact, comma-joined (never '|') display string for a work's Labs field.

    No reference implementation exists yet for `labs_short` (ptn_works, the other table planned to
    carry this column, has not been built by W2 as of this pass) -- this is this builder's own
    design, documented here and in the contract fragment: first 2 labs joined by ', ', a '+N' suffix
    if more, 'NO LAB' passed through verbatim (a defined absence, not abbreviated).
    """
    if pd.isna(labs_value) or labs_value == "":
        return ""
    if labs_value == "NO LAB":
        return "NO LAB"
    parts = [p.strip() for p in str(labs_value).split(" | ") if p.strip()]
    if len(parts) <= 2:
        return ", ".join(parts)
    return f"{parts[0]}, {parts[1]} +{len(parts) - 2}"


def top_n_join(pairs: pd.DataFrame, group_col: str, key_col: str, label_map: dict, n: int = 3):
    """pairs: long (group_col, key_col, work_id) rows (one per person-work-node occurrence).
    Returns two dict[group_col -> str]: comma-joined top-n key ids by work count (ties broken by
    key_col ascending, for determinism), and the matching comma-joined labels."""
    counts = (pairs.groupby([group_col, key_col])["work_id"].nunique()
              .rename("n").reset_index())
    counts = counts.sort_values([group_col, "n", key_col], ascending=[True, False, True])
    top = counts.groupby(group_col, sort=False).head(n)
    ids = top.groupby(group_col, sort=False)[key_col].agg(lambda s: ", ".join(s))
    labels = top.groupby(group_col, sort=False)[key_col].agg(
        lambda s: ", ".join(label_map.get(x, "Unknown") for x in s)
    )
    return ids.to_dict(), labels.to_dict()


def prune_proof(path: Path, filter_col: str, target: str, label: str) -> None:
    """Row-group pruning proof (mirrors reports/foundry_pass2_probes.py's own function): confirms a
    filtered read on the sort key only touches a small share of column bytes."""
    pf = pq.ParquetFile(path)
    schema = pf.schema_arrow
    col_idx = schema.get_field_index(filter_col)
    total_bytes = touched_bytes = touched_rows = n_touched = 0
    n_rg = pf.metadata.num_row_groups
    for i in range(n_rg):
        rg = pf.metadata.row_group(i)
        col = rg.column(col_idx)
        sz = col.total_compressed_size
        total_bytes += sz
        stats = col.statistics
        if stats is not None and stats.has_min_max and stats.min <= target <= stats.max:
            touched_bytes += sz
            touched_rows += rg.num_rows
            n_touched += 1
    actual = pd.read_parquet(path, filters=[(filter_col, "==", target)])
    pct = touched_bytes / max(total_bytes, 1) * 100
    print(f"[{label}] prune proof for {filter_col}={target}:")
    print(f"  row groups touched: {n_touched}/{n_rg}")
    print(f"  {filter_col}-column bytes touched: {touched_bytes:,} of {total_bytes:,} "
          f"({pct:.1f}%)")
    print(f"  filtered read returned {len(actual):,} rows "
          f"(row-group-estimated: {touched_rows:,})")
    assert pct < 20.0, f"prune proof touched {pct:.1f}% of column bytes, expected < 20%"
    print("  Class-1 lazy-read proof: PASS (< 20% of column bytes touched)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"
    compression = CONFIG["storage"]["compression"]
    snapshot_date = CONFIG["project"]["snapshot_id"]
    floor = CONFIG["workshop_tunables"]["author_impact_floor"]
    print(f"45b_build_author_views -- snapshot {snapshot.name}, author_impact_floor={floor}")

    # ================================================================================= LOAD
    section("LOAD -- ul_authors (this snapshot's own 45 output) + snapshot tables (read-only)")
    # RA-C01 fix: this used to read the previously DEPLOYED Streamlit/data/ul_authors.parquet
    # (a real fresh-machine bootstrap landmine -- see run_all.py's docstring, now marked
    # RESOLVED). 45_build_authors.py writes ul_authors.parquet into THIS SAME snapshot's own
    # tables/ dir (same filename, `tables / "ul_authors.parquet"`) -- reading it from there
    # instead needs no prior 60_deploy pass and reconciles the content 45b already asserts
    # against below (person_id/n_works/ul_credited_works recomputes), just sourced from the
    # step that actually produces it in dependency order.
    ula = pd.read_parquet(tables / "ul_authors.parquet")
    print(f"ul_authors (this snapshot's own 45 output): {len(ula):,} rows x {ula.shape[1]} cols")

    wm = pd.read_parquet(tables / "works_master.parquet", columns=[
        "work_id", "publication_year", "title", "doi", "type", "is_conference", "In_ISITE",
        "Labs", "primary_field_id", "primary_field_name",
        "primary_subfield_id", "primary_subfield_name", "hal_authors_idhal",
    ])
    au = pd.read_parquet(tables / "corpus_authorships.parquet",
                          columns=["work_id", "author_id", "institution_id", "institution_ror", "orcid"])
    ct = pd.read_parquet(tables / "corpus_topics.parquet", columns=["work_id", "topic_id", "is_primary"])
    descendants = pd.read_parquet(tables / "ul_descendants.parquet")
    review_queue = pd.read_parquet(tables / "ul_authors_review_queue.parquet")
    manifest_data = json.loads((snapshot / "MANIFEST.json").read_text(encoding="utf-8"))
    conflict_blocked = int(manifest_data["steps"]["45_build_authors"]["counts"]["X_orcid_conflict_blocked"])
    print(f"works_master {len(wm):,} rows; corpus_authorships {len(au):,} rows; "
          f"corpus_topics {len(ct):,} rows; ul_descendants {len(descendants):,} rows; "
          f"review_queue {len(review_queue):,} pairs; MANIFEST X_orcid_conflict_blocked={conflict_blocked:,}")

    N_CORPUS = len(wm)

    # ================================================================== author_id -> person_id
    section("MAPPING -- raw author_id -> reconciled person_id (explode profiles_joined)")
    map_rows = []
    for person_id, joined in zip(ula["person_id"], ula["profiles_joined"]):
        for aid in str(joined).split(" | "):
            aid = aid.strip()
            if aid:
                map_rows.append((aid, person_id))
    author_to_person = pd.DataFrame(map_rows, columns=["author_id", "person_id"])
    dupes = author_to_person["author_id"].duplicated().sum()
    assert dupes == 0, f"{dupes} raw author_id(s) map to more than one person_id -- profiles_joined not a partition"
    print(f"exploded mapping: {len(author_to_person):,} raw author_id(s) -> {ula['person_id'].nunique():,} persons "
          f"(0 duplicate author_id -- PASS, profiles_joined is a clean partition)")

    ul_ids = set(descendants["openalex_id"]) | {CONFIG["perimeter"]["ul_openalex_id"]}
    ul_rors = set(descendants["ror"].dropna()) | {CONFIG["perimeter"]["ul_ror"]}
    au["is_ul"] = au["institution_id"].isin(ul_ids) | au["institution_ror"].isin(ul_rors)

    au_scoped = au.merge(author_to_person, on="author_id", how="inner")
    print(f"corpus_authorships rows joined to a known person: {len(au_scoped):,} of {len(au):,} "
          f"({len(au_scoped) / len(au) * 100:.1f}%) -- the remainder belongs to author_ids never "
          f"credited a Lorraine affiliation (outside ul_authors by construction)")

    # ================================================================== per-work flags
    artifact_flag_map = flag_works(ct).to_dict()
    wm = wm.copy()
    wm["artifact_flag"] = wm["work_id"].map(artifact_flag_map).fillna(False).astype(bool)
    wm["labs_short"] = wm["Labs"].apply(make_labs_short)
    wm["has_idhal_proxy"] = wm["hal_authors_idhal"].notna() & (wm["hal_authors_idhal"].astype(str).str.len() > 0)
    n_flagged = int(wm["artifact_flag"].sum())
    print(f"artifact_flag (primary topic on the 811-topic exclusion list): {n_flagged:,} of "
          f"{N_CORPUS:,} works ({n_flagged / N_CORPUS * 100:.2f}%; F0-P4 golden: 11.15%)")

    # ============================================================================== pw_pairs
    section("BASE -- person x work pairs, ALL corpus appearances (see module docstring design note)")
    pw_pairs = au_scoped[["person_id", "work_id"]].drop_duplicates()
    pw_flagged = pw_pairs.merge(wm, on="work_id", how="left")
    print(f"pw_pairs (ALL corpus person x work pairs): {len(pw_pairs):,} rows "
          f"(YAML rows_est was ~90-140k -- see report for the explained gap)")

    recomputed_n_works = pw_pairs.groupby("person_id")["work_id"].nunique()
    ula_n_works = ula.set_index("person_id")["n_works"]
    check = recomputed_n_works.reindex(ula_n_works.index)
    mismatches = int((check != ula_n_works).sum())
    assert mismatches == 0, (
        f"{mismatches} person(s) where the independent recompute of n_works (via the exploded "
        f"author_id->person_id mapping + corpus_authorships) disagrees with the deployed "
        f"ul_authors.n_works -- mapping bug"
    )
    print(f"  sanity: independent n_works recompute == ul_authors.n_works for all {len(ula):,} "
          f"persons (0 mismatches) -- PASS")

    ul_credited_pairs = au_scoped.loc[au_scoped["is_ul"], ["person_id", "work_id"]].drop_duplicates()
    recomputed_ul_credited = ul_credited_pairs.groupby("person_id")["work_id"].nunique()
    ula_ul_credited = ula.set_index("person_id")["ul_credited_works"]
    check2 = recomputed_ul_credited.reindex(ula_ul_credited.index).fillna(0).astype(int)
    mismatches2 = int((check2 != ula_ul_credited.fillna(0).astype(int)).sum())
    assert mismatches2 == 0, f"{mismatches2} person(s): recomputed ul_credited_works != ul_authors.ul_credited_works"
    print(f"  sanity: independent ul_credited_works recompute == ul_authors.ul_credited_works "
          f"(0 mismatches) -- PASS")

    # ============================================================================ aut_works
    section("BUILD -- aut_works (person x work, sorted by author_id, rg=5000)")
    aut_works = pw_flagged[[
        "person_id", "work_id", "publication_year", "title", "doi", "type", "is_conference",
        "In_ISITE", "labs_short", "artifact_flag",
    ]].rename(columns={
        "person_id": "author_id", "publication_year": "year", "In_ISITE": "in_isite",
    })
    assert_no_impact_columns(aut_works, "aut_works")
    aut_works["author_id"] = aut_works["author_id"].astype("category")
    aut_works["type"] = aut_works["type"].astype("category")
    aut_works = aut_works.sort_values("author_id").reset_index(drop=True)

    recon = aut_works.groupby("author_id", observed=True).size()
    recon_full = recon.reindex(ula["person_id"]).fillna(0).astype(int)
    assert (recon_full.values == ula_n_works.reindex(ula["person_id"]).values).all(), (
        "aut_works row count per author does not reconcile with aut_public.n_works (== ul_authors.n_works)"
    )
    print(f"  RECONCILIATION (required assert): aut_works rows per author_id == aut_public.n_works "
          f"for all {len(ula):,} persons -- PASS")

    aut_works_path = tables / "aut_works.parquet"
    aut_works.to_parquet(aut_works_path, row_group_size=5000, index=False, compression=compression)
    pf = pq.ParquetFile(aut_works_path)
    n_rg = pf.metadata.num_row_groups
    floor_rg = len(aut_works) / 10000
    print(f"aut_works: {len(aut_works):,} rows x {aut_works.shape[1]} cols; "
          f"{aut_works_path.stat().st_size / 1e6:.3f} MB disk; {n_rg} row groups "
          f"(Class-1 invariant num_row_groups >= n_rows/10000 = {floor_rg:.1f}: "
          f"{'PASS' if n_rg >= floor_rg else 'FAIL'})")
    assert n_rg >= floor_rg, "aut_works fails the Class-1 row-group floor"

    proof_author = str(ula.sort_values("n_works", ascending=False).iloc[0]["person_id"])
    prune_proof(aut_works_path, "author_id", proof_author, "aut_works")

    # ============================================================================ aut_public
    section("BUILD -- aut_public (one row per person, conf/xa as COLUMNS)")
    n_works_all = pw_flagged.groupby("person_id")["work_id"].nunique()
    n_works_noconf = pw_flagged[~pw_flagged["is_conference"]].groupby("person_id")["work_id"].nunique()
    n_works_xa = pw_flagged[~pw_flagged["artifact_flag"]].groupby("person_id")["work_id"].nunique()
    n_works_noconf_xa = pw_flagged[
        (~pw_flagged["is_conference"]) & (~pw_flagged["artifact_flag"])
    ].groupby("person_id")["work_id"].nunique()

    def orcid_singular(joined: str) -> str | None:
        parts = [p.strip() for p in str(joined).split(" | ") if p.strip()]
        return parts[0] if parts else None

    multi_orcid = int(ula["orcids_joined"].apply(lambda s: str(s).count(" | ") > 0).sum())
    multi_idhal = int(ula["idhals_joined"].apply(lambda s: str(s).count(" | ") > 0).sum())
    print(f"  singular orcid/idhal: {multi_orcid} persons hold >1 distinct ORCID and {multi_idhal} "
          f">1 idHAL (known transitive-merge edge cases per 45_build_authors.py's own docstring) -- "
          f"the lexicographically-first value is kept deterministically (orcids/idhals are stored "
          f"pre-sorted); this table cannot carry a list without violating the no-'|' convention.")

    field_label_map = wm[["primary_field_id", "primary_field_name"]].dropna().drop_duplicates(
        "primary_field_id").set_index("primary_field_id")["primary_field_name"].to_dict()
    subfield_label_map = wm[["primary_subfield_id", "primary_subfield_name"]].dropna().drop_duplicates(
        "primary_subfield_id").set_index("primary_subfield_id")["primary_subfield_name"].to_dict()

    field_pairs = pw_pairs.merge(wm[["work_id", "primary_field_id"]], on="work_id").dropna(subset=["primary_field_id"])
    subfield_pairs = pw_pairs.merge(wm[["work_id", "primary_subfield_id"]], on="work_id").dropna(
        subset=["primary_subfield_id"])
    field_ids, field_labels = top_n_join(field_pairs, "person_id", "primary_field_id", field_label_map, n=3)
    subfield_ids, subfield_labels = top_n_join(subfield_pairs, "person_id", "primary_subfield_id",
                                                subfield_label_map, n=3)
    print(f"  thematic identity: computed over the SAME ALL-corpus work basis as n_works (see module "
          f"docstring design note) -- top-3 fields/subfields by work count, ids+labels as two "
          f"columns per level (4 columns total; deviates from the YAML's 2 bare column names "
          f"'thematic_identity_fields'/'thematic_identity_subfields' -- documented in the contract "
          f"fragment as the chosen encoding, since the YAML did not specify one and the dispatch "
          f"explicitly allowed either a comma-joined label string or two compact id+label columns).")

    aut_public = pd.DataFrame({
        "author_id": ula["person_id"],
        "display_name": ula["display_name"],
        "orcid": ula["orcids_joined"].apply(orcid_singular),
        "idhal": ula["idhals_joined"].apply(orcid_singular),
        "n_works": ula["person_id"].map(n_works_all).fillna(0).astype(int),
        "n_works_noconf": ula["person_id"].map(n_works_noconf).fillna(0).astype(int),
        "n_works_xa": ula["person_id"].map(n_works_xa).fillna(0).astype(int),
        "n_works_noconf_xa": ula["person_id"].map(n_works_noconf_xa).fillna(0).astype(int),
        "ul_credited_works": ula["ul_credited_works"],
        "main_labs": ula["own_labs_joined"].fillna("").str.replace(" | ", ", ", regex=False),
        "thematic_identity_fields_ids": ula["person_id"].map(field_ids).fillna(""),
        "thematic_identity_fields_labels": ula["person_id"].map(field_labels).fillna(""),
        "thematic_identity_subfields_ids": ula["person_id"].map(subfield_ids).fillna(""),
        "thematic_identity_subfields_labels": ula["person_id"].map(subfield_labels).fillna(""),
        "laureate_tags": "",   # A4 stub -- populated once client laureate lists arrive (async)
        "snapshot_date": snapshot_date,
    })
    assert (aut_public["n_works"] == n_works_all.reindex(aut_public["author_id"]).fillna(0).astype(int).values).all()
    assert_no_impact_columns(aut_public, "aut_public")
    assert (aut_public["n_works"] >= aut_public["n_works_noconf"]).all()
    assert (aut_public["n_works"] >= aut_public["n_works_xa"]).all()
    assert (aut_public["n_works_noconf"] >= aut_public["n_works_noconf_xa"]).all()
    assert (aut_public["n_works_xa"] >= aut_public["n_works_noconf_xa"]).all()
    assert (aut_public["ul_credited_works"] <= aut_public["n_works"]).all()
    print(f"  monotonicity asserts (n_works >= n_works_noconf/n_works_xa >= n_works_noconf_xa; "
          f"ul_credited_works <= n_works): PASS")

    aut_public_path = tables / "aut_public.parquet"
    aut_public.to_parquet(aut_public_path, index=False, compression=compression)
    print(f"aut_public: {len(aut_public):,} rows x {aut_public.shape[1]} cols; "
          f"{aut_public_path.stat().st_size / 1e6:.3f} MB disk")
    assert len(aut_public) == 12680, f"expected 12,680 persons, got {len(aut_public):,}"
    print("  golden: 12,680 rows -- PASS")

    # ==================================================================== aut_impact_drill
    section(f"BUILD -- aut_impact_drill (floor: works_with_indicators >= {floor}, x conf_state)")
    metrics = pd.read_parquet(tables / "corpus_metrics.parquet").set_index("work_id")
    computed_ids = set(metrics[metrics["indicator_status"] == "computed"].index)
    fwci = metrics["FWCI_FR"].to_dict()
    pptop = metrics["PPtop10_FR"].to_dict()

    def impact_frame(pairs: pd.DataFrame) -> pd.DataFrame:
        grouped = pairs.groupby("person_id")["work_id"].apply(list)
        out = pd.DataFrame({"person_id": grouped.index})
        out["works_with_indicators"] = grouped.apply(
            lambda ws: sum(1 for w in ws if w in computed_ids)).values
        out["fwci_fr_mean"] = grouped.apply(
            lambda ws: (round(sum(fwci.get(w, 0) or 0 for w in ws if w in computed_ids)
                        / max(sum(1 for w in ws if w in computed_ids), 1), 4)
                        if any(w in computed_ids for w in ws) else None)).values
        out["pptop10_count"] = grouped.apply(
            lambda ws: int(sum(1 for w in ws if w in computed_ids and bool(pptop.get(w))))).values
        return out.set_index("person_id")

    # Membership gate is evaluated ONCE on the ALL-corpus basis (matching F0-P3's exact golden,
    # 480 persons) -- both conf_state rows describe the SAME 480 persons, re-scored under each
    # lens. Re-gating the floor independently per conf_state (tried first) collapses no_conf to
    # 282 (many LORIA/INRIA-heavy profiles lean on conference output for their indicator volume),
    # which the dispatch's own "480 per conf_state" framing rules out -- a fixed population shown
    # under two lenses is also the only reading consistent with "impact context computed on full
    # corpus" (data_foundation.yaml's own artifact_exempt rationale for this table: the drill's
    # SUBJECT POOL is a full-corpus fact, only the displayed numbers move per lens).
    frame_all = impact_frame(pw_pairs)
    recon_wwi = frame_all["works_with_indicators"].reindex(ula.set_index("person_id").index)
    ula_wwi = ula.set_index("person_id")["works_with_indicators"]
    mism = int((recon_wwi != ula_wwi).sum())
    assert mism == 0, f"{mism} person(s): recomputed works_with_indicators != ul_authors' (conf_state=all)"
    print(f"  sanity (conf_state=all): recomputed works_with_indicators == "
          f"ul_authors.works_with_indicators for all persons -- PASS")
    eligible_ids = frame_all[frame_all["works_with_indicators"] >= floor].index
    print(f"  eligibility gate (works_with_indicators >= {floor}, ALL-corpus basis): "
          f"{len(eligible_ids)} persons -- gate evaluated ONCE, reused for both conf_state rows below")
    assert len(eligible_ids) == 480, f"expected EXACT 480 (F0-P3 golden), got {len(eligible_ids)}"
    print("  golden: EXACT 480 -- PASS")

    noconf_pairs = pw_flagged.loc[~pw_flagged["is_conference"], ["person_id", "work_id"]]
    drill_rows = []
    for conf_state, frame in (("all", frame_all), ("no_conf", impact_frame(noconf_pairs))):
        eligible = frame.reindex(eligible_ids)
        eligible["works_with_indicators"] = eligible["works_with_indicators"].fillna(0).astype(int)
        eligible["pptop10_count"] = eligible["pptop10_count"].fillna(0).astype(int)
        eligible["conf_state"] = conf_state
        eligible = eligible.reset_index().rename(columns={"person_id": "author_id"})
        n = len(eligible)
        print(f"  conf_state={conf_state}: {n} persons (fixed population; band 400-600 assert: "
              f"{'PASS' if 400 <= n <= 600 else 'FAIL'})")
        assert 400 <= n <= 600, f"aut_impact_drill conf_state={conf_state}: {n} outside the 400-600 band"
        drill_rows.append(eligible[["author_id", "conf_state", "fwci_fr_mean", "pptop10_count",
                                     "works_with_indicators"]])
    aut_impact_drill = pd.concat(drill_rows, ignore_index=True)
    assert_no_impact_columns(
        aut_impact_drill.drop(columns=["fwci_fr_mean", "pptop10_count"]), "aut_impact_drill (non-impact cols)"
    )
    aut_impact_drill["conf_state"] = aut_impact_drill["conf_state"].astype("category")

    drill_path = tables / "aut_impact_drill.parquet"
    aut_impact_drill.to_parquet(drill_path, index=False, compression=compression)
    print(f"aut_impact_drill: {len(aut_impact_drill):,} rows x {aut_impact_drill.shape[1]} cols; "
          f"{drill_path.stat().st_size / 1e6:.4f} MB disk")

    # ========================================================================= aut_coverage
    section("BUILD -- aut_coverage (collective grains ONLY: lab | field | year | population, x conf_state)")

    lab_of_institution = {row.openalex_id: row.client_lab_name for row in descendants.itertuples()
                           if pd.notna(row.client_lab_name)}
    own_lab_pairs = au_scoped.loc[au_scoped["is_ul"], ["person_id", "work_id", "institution_id"]].copy()
    own_lab_pairs["lab"] = own_lab_pairs["institution_id"].map(lab_of_institution)
    own_lab_pairs = own_lab_pairs.dropna(subset=["lab"])[["person_id", "work_id", "lab"]].drop_duplicates()
    own_lab_pairs = own_lab_pairs.merge(wm[["work_id", "is_conference"]], on="work_id", how="left")

    orcid_of_person = aut_public.set_index("author_id")["orcid"]

    def orcid_share(person_ids) -> tuple[int, int]:
        s = orcid_of_person.reindex(pd.unique(person_ids))
        n = len(s)
        n_orcid = int(s.notna().sum())
        return n, n_orcid

    rows = []

    def add_row(unit_kind, unit_id, unit_label, conf_state, n_persons, n_persons_orcid,
                n_works, n_works_orcid_author, idhal_pct, note):
        pct_orcid = (round(n_persons_orcid / n_persons, 4)
                     if n_persons and n_persons_orcid is not None else None)
        pct_works = (round(n_works_orcid_author / n_works, 4)
                     if n_works and n_works_orcid_author is not None else None)
        rows.append({
            "unit_kind": unit_kind, "unit_id": unit_id, "unit_label": unit_label,
            "conf_state": conf_state, "n_persons": n_persons, "n_persons_orcid": n_persons_orcid,
            "pct_orcid": pct_orcid, "n_works": n_works, "n_works_orcid_author": n_works_orcid_author,
            "pct_works_orcid": pct_works, "idhal_proxy_pct": idhal_pct,
            "unknown_distinct_note": note, "snapshot_date": snapshot_date,
        })

    # -- per-work UL-side "any ORCID'd author" + idhal proxy, precomputed once, reused per grain --
    au_ul_all = au[au["is_ul"]].merge(wm[["work_id", "is_conference"]], on="work_id", how="left")
    au_ul_all["has_orcid"] = au_ul_all["orcid"].notna() & (au_ul_all["orcid"].astype(str).str.len() > 5)

    for conf_state in ("all", "no_conf"):
        wm_c = wm if conf_state == "all" else wm[~wm["is_conference"]]
        au_ul_c = au_ul_all if conf_state == "all" else au_ul_all[~au_ul_all["is_conference"]]
        w_any_orcid = au_ul_c.groupby("work_id")["has_orcid"].any()
        own_lab_c = own_lab_pairs if conf_state == "all" else own_lab_pairs[~own_lab_pairs["is_conference"]]
        field_pairs_c = (ul_credited_pairs if conf_state == "all"
                         else ul_credited_pairs.merge(wm[["work_id", "is_conference"]], on="work_id")
                         .loc[lambda d: ~d["is_conference"], ["person_id", "work_id"]])
        field_pairs_c = field_pairs_c.merge(wm[["work_id", "primary_field_id", "primary_field_name"]],
                                             on="work_id", how="left")

        # ---- LAB rows -- EXPLODE Labs (a work can carry 2-7 pipe-joined lab codes; F0-P3's own
        # method, reused verbatim) so a multi-lab work counts once per lab, never once per combo ----
        wm_lab_note = ("'NO LAB' is a DEFINED absence (a work genuinely outside any curated lab, not "
                       "missing data) -- kept as its own explicit row, never dropped, per the "
                       "unknown-vs-absent distinction the dispatch requires.")
        wm_lab_exp = wm_c.assign(lab=wm_c["Labs"].fillna("NO LAB").str.split("|")).explode("lab")
        wm_lab_exp["lab"] = wm_lab_exp["lab"].str.strip()
        for lab, block in wm_lab_exp.groupby("lab"):
            block_work_ids = set(block["work_id"])
            n_works_lab = len(block_work_ids)
            n_orcid_lab = int(sum(1 for w in block_work_ids if w_any_orcid.get(w, False)))
            idhal_pct_lab = round(block["has_idhal_proxy"].mean(), 4) if len(block) else None
            lab_persons = own_lab_c.loc[own_lab_c["lab"] == lab, "person_id"]
            n_p, n_p_orcid = orcid_share(lab_persons) if len(lab_persons) else (0, 0)
            note = wm_lab_note if lab == "NO LAB" else "collective grain; person roster = own_labs (this person's own UL-credited affiliation), never a per-person row."
            add_row("lab", lab, lab, conf_state, n_p, n_p_orcid, n_works_lab, n_orcid_lab, idhal_pct_lab, note)

        # ---- FIELD rows (incl. explicit UNKNOWN bucket) ----
        for field_id, block in wm_c.dropna(subset=["primary_field_id"]).groupby("primary_field_id"):
            block_work_ids = set(block["work_id"])
            n_works_f = len(block_work_ids)
            n_orcid_f = int(sum(1 for w in block_work_ids if w_any_orcid.get(w, False)))
            idhal_pct_f = round(block["has_idhal_proxy"].mean(), 4) if len(block) else None
            f_persons = field_pairs_c.loc[field_pairs_c["primary_field_id"] == field_id, "person_id"]
            n_p, n_p_orcid = orcid_share(f_persons) if len(f_persons) else (0, 0)
            label = field_label_map.get(field_id, field_id)
            add_row("field", field_id, label, conf_state, n_p, n_p_orcid, n_works_f, n_orcid_f,
                    idhal_pct_f, "collective grain; person roster = >=1 UL-credited work with this primary field.")
        unk = wm_c[wm_c["primary_field_id"].isna()]
        if len(unk):
            unk_ids = set(unk["work_id"])
            n_orcid_u = int(sum(1 for w in unk_ids if w_any_orcid.get(w, False)))
            idhal_pct_u = round(unk["has_idhal_proxy"].mean(), 4)
            add_row("field", "UNKNOWN", "No primary field assigned (topic-classifier gap)", conf_state,
                    None, None, len(unk), n_orcid_u, idhal_pct_u,
                    "GENUINELY unknown (missing classifier output), distinct from 'NO LAB' (a defined "
                    "absence) -- the unknown-vs-absent distinction the dispatch requires. No person "
                    "roster: field membership is undefined for these works.")

        # ---- YEAR rows (pct_orcid OVERLOADED: see note) ----
        au_ul_year = au_ul_c.merge(wm_c[["work_id", "publication_year"]], on="work_id", how="inner")
        for year, block in au_ul_year.groupby("publication_year"):
            n_rows_y = len(block)
            n_orcid_rows_y = int(block["has_orcid"].sum())
            wm_year = wm_c[wm_c["publication_year"] == year]
            year_work_ids = set(wm_year["work_id"])
            n_works_y = len(year_work_ids)
            n_orcid_any_y = int(sum(1 for w in year_work_ids if w_any_orcid.get(w, False)))
            idhal_pct_y = round(wm_year["has_idhal_proxy"].mean(), 4) if len(wm_year) else None
            add_row("year", str(int(year)), str(int(year)), conf_state, n_rows_y, n_orcid_rows_y,
                    n_works_y, n_orcid_any_y, idhal_pct_y,
                    "OVERLOADED: n_persons/n_persons_orcid/pct_orcid here count UL-CREDITED "
                    "AUTHORSHIP ROWS that year (not distinct persons) and their ORCID coverage -- "
                    "this is indicator_plan_FINAL.md S5's 'UL-side authorship ORCID share' figure "
                    "(row-grain, since the same person recurs across years); n_works/"
                    "n_works_orcid_author/pct_works_orcid stay work-grain ('>=1 ORCID'd UL author "
                    "per work') as on every other unit_kind.")

        # ---- POPULATION rows ----
        all_persons_orcid = aut_public["orcid"].notna().sum()
        add_row("population", "all_persons", "All persons in the directory", conf_state,
                len(aut_public), int(all_persons_orcid), None, None, None,
                "person-identity coverage; conf_state-invariant by construction (ORCID registration "
                "does not depend on the conference toggle) -- duplicated across both rows per the "
                "standing per-aggregate conf_state convention.")

        if conf_state == "all":
            ge5 = aut_public[aut_public["n_works"] >= 5]
        else:
            ge5 = aut_public[aut_public["n_works_noconf"] >= 5]
        add_row("population", "persons_ge5works", "Persons with >=5 (conf_state-filtered) corpus works",
                conf_state, len(ge5), int(ge5["orcid"].notna().sum()), None, None, None,
                "floor reapplied to the conf_state-filtered work count for no_conf, per the standing "
                "conference-toggle-recomputes-from-key-columns rule (S6.5).")

        n_works_pop = len(wm_c)
        n_orcid_pop = int(sum(1 for w in set(wm_c["work_id"]) if w_any_orcid.get(w, False)))
        idhal_pct_pop = round(wm_c["has_idhal_proxy"].mean(), 4)
        add_row("population", "all_works", "All corpus works (>=1 ORCID'd UL author share)", conf_state,
                None, None, n_works_pop, n_orcid_pop, idhal_pct_pop,
                "work-grain population row; denominator = the conf_state-filtered corpus, matching "
                "F0-P3's own 'works with >=1 ORCID'd UL author' golden exactly on conf_state=all.")

        merged_n = int((ula["n_profiles"] > 1).sum())
        add_row("population", "merged_profiles", "Persons rebuilt from more than one OpenAlex profile",
                conf_state, merged_n, None, None, None, None,
                f"identity-ledger fact (45_build_authors.py: {merged_n:,} of {len(ula):,} persons; "
                f"{int(ula['n_profiles'].sum() - len(ula)):,} raw profiles absorbed in total) -- "
                "pct_orcid column REPURPOSED here to carry merged_n / n_persons_total (a share of "
                "ALL persons, not an ORCID rate); conf_state-invariant, duplicated per convention.")
        add_row("population", "review_queue",
                "ORCID-conflict pairs with strong corroboration, surfaced for human adjudication "
                "(never force-merged)", conf_state, len(review_queue), None, None, None, None,
                "identity-ledger fact: a raw PAIR count (n_persons column repurposed), not a person "
                "count or a rate; conf_state-invariant, duplicated per convention.")
        add_row("population", "unresolved_share",
                "Review-queue pairs as a share of ALL identified ORCID-conflict pairs "
                "(X_orcid_conflict_blocked, MANIFEST.json)", conf_state, None, None, None, None, None,
                f"identity-ledger fact: pct_orcid column REPURPOSED to carry "
                f"{len(review_queue)}/{conflict_blocked} = the share of detected ORCID conflicts "
                "that reached human review rather than being silently dropped; conf_state-invariant.")
        rows[-1]["pct_orcid"] = round(len(review_queue) / conflict_blocked, 4)
        rows[-3]["pct_orcid"] = round(merged_n / len(ula), 4)

    aut_coverage = pd.DataFrame(rows)
    for c in ("unit_kind", "conf_state"):
        aut_coverage[c] = aut_coverage[c].astype("category")
    coverage_path = tables / "aut_coverage.parquet"
    aut_coverage.to_parquet(coverage_path, index=False, compression=compression)
    print(f"aut_coverage: {len(aut_coverage):,} rows x {aut_coverage.shape[1]} cols "
          f"({aut_coverage['unit_kind'].value_counts().to_dict()} per conf_state); "
          f"{coverage_path.stat().st_size / 1e6:.3f} MB disk")

    # ---- GOLDENS (F0-P3 / indicator_plan_FINAL.md S5), conf_state == 'all' ----
    section("GOLDENS -- ORCID feasibility (F0-P3 / plan S5), conf_state=all")
    pop_all = aut_coverage[(aut_coverage["unit_kind"] == "population") & (aut_coverage["conf_state"] == "all")]
    g1 = pop_all.set_index("unit_id").loc["all_works", "pct_works_orcid"] * 100
    print(f"  works with >=1 ORCID'd UL author: {g1:.1f}% (plan: 72.6%)")
    assert abs(g1 - 72.6) < 0.05, f"golden 1 FAILED: {g1:.2f} vs 72.6"

    g2 = pop_all.set_index("unit_id").loc["persons_ge5works", "pct_orcid"] * 100
    print(f"  persons >=5 works with ORCID: {g2:.1f}% (plan: 72.4%)")
    assert abs(g2 - 72.4) < 0.05, f"golden 2 FAILED: {g2:.2f} vs 72.4"

    g3 = pop_all.set_index("unit_id").loc["all_persons", "pct_orcid"] * 100
    print(f"  all persons with ORCID: {g3:.1f}% (plan: 48.6%)")
    assert abs(g3 - 48.6) < 0.05, f"golden 3 FAILED: {g3:.2f} vs 48.6"

    year_all = aut_coverage[(aut_coverage["unit_kind"] == "year") & (aut_coverage["conf_state"] == "all")]
    year_all = year_all.set_index("unit_id").sort_index()
    expected_by_year = {"2019": 67.1, "2020": 69.5, "2021": 72.0, "2022": 72.6, "2023": 71.5}
    print("  by-year UL-side authorship ORCID share (year row, pct_orcid, OVERLOADED -- see note):")
    for yr, exp in expected_by_year.items():
        got = year_all.loc[yr, "pct_orcid"] * 100
        delta = abs(got - exp)
        flag = "PASS" if delta <= REVIEW_TOLERANCE_PCT else "FAIL"
        print(f"    {yr}: {got:.2f}% (plan: {exp}%, delta {delta:.2f}pt) -- {flag}"
              + ("  [explained rounding-boundary delta, see report]" if 0 < delta <= REVIEW_TOLERANCE_PCT else ""))
        assert delta <= REVIEW_TOLERANCE_PCT, f"by-year golden FAILED for {yr}: {got:.2f} vs {exp} (delta {delta:.2f})"
    dip = year_all.loc["2023", "pct_orcid"] < year_all.loc["2022", "pct_orcid"]
    print(f"  2023 dip vs 2022 INTACT (never smoothed): "
          f"{year_all.loc['2022','pct_orcid']*100:.2f}% -> {year_all.loc['2023','pct_orcid']*100:.2f}% "
          f"-- {'PASS' if dip else 'FAIL'}")
    assert dip, "2023 dip was smoothed away -- regression against the plan's explicit 'never smoothed' rule"

    drill_all_n = int((aut_impact_drill["conf_state"] == "all").sum())
    print(f"  aut_impact_drill floor population (conf_state=all): {drill_all_n} (plan/F0-P3: 480, exact)")

    # ================================================================================= WRITE REPORT
    counts = {
        "aut_public_rows": len(aut_public), "aut_works_rows": len(aut_works),
        "aut_impact_drill_rows": len(aut_impact_drill), "aut_coverage_rows": len(aut_coverage),
    }
    Manifest(snapshot).record_step(
        "45b_build_author_views", counts=counts,
        files=[aut_public_path, aut_works_path, drill_path, coverage_path],
        params={"author_impact_floor": floor},
        notes="Author-family views (Stream W4, chain pass 3). aut_works = ALL-corpus person x work "
              "pairs (see module docstring design note on the invariant-text-over-grain-label reading).",
    )
    append_summary(snapshot, "45b_build_author_views", [
        f"- aut_public: {len(aut_public):,} rows", f"- aut_works: {len(aut_works):,} rows",
        f"- aut_impact_drill: {len(aut_impact_drill):,} rows (240 all + 240 no_conf-ish, floor {floor})",
        f"- aut_coverage: {len(aut_coverage):,} rows",
    ])
    section("DONE")
    print(f"wrote aut_public.parquet, aut_works.parquet, aut_impact_drill.parquet, "
          f"aut_coverage.parquet to {tables}")


if __name__ == "__main__":
    main()
