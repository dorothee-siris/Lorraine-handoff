"""47c_build_frontier_topics.py -- thm_frontier_topics (pass 5, S3b, ruling R11 full-depth
materialization; docs/foundry/data_foundation.yaml entry `thm_frontier_topics`).

WHY THIS EXISTS: ruling R11 (locked 2026-08-18) says ranked tables default to top-10 with
"afficher plus" plus a text query, and for frontierness the owner's own named acceptance example
is "type 'quantum' -> see the position of ALL topics containing quantum" -- materialized depth =
FULL at site level. `thm_frontier.parquet`'s texture rows (built by
`47_build_thematic_ext.py`) only ever cover the top-20 emerging (kept) topics GLOBALLY -- a query
for any topic ranked below #20, or excluded, or absent from the baseline file, had nothing to
find. This builder extends the SAME frontier construction to every topic the UL corpus actually
uses as a PRIMARY topic (~3,274), so the page-5 emerging-topics panel can search/rank the full
universe honestly.

PLACEMENT DECISION (documented per the dispatch's own ask): a NEW standalone file, not a 6th
section inside `47_build_thematic_ext.py`. Two builders already sit in this codebase doing exactly
this kind of extension -- `47b_build_crossings.py` is the direct precedent: its own module
docstring says outright "construction copied from 47_build_thematic_ext.py's frontier section
(module read in full before writing this file)" and it duplicates the baseline-loading block
verbatim rather than importing from 47 (47 exposes no reusable functions -- every step lives
inline inside its own `main()`). Extending 47 in place would mean inserting a 6th section into an
833-line file that already carries four hand-verified golden asserts (join coverage, neutral
point, raw/standardised amplification) plus 47's own W3 funding disclosures -- a real regression
surface for a change that has nothing to do with any of those. A standalone file matching 47b's
own precedent is the smaller, cleaner diff: it duplicates ~15 lines of baseline-loading
boilerplate (the same duplication 47b already accepted) and touches zero lines of 47 itself.

CONSTRUCTION (reused verbatim, never reimplemented -- see 47's own module docstring for the
original derivation): same `inputs/manual/frontierness_baseline.xlsx` copy-in, same
`lib.artifact.load_bad_topics()` 811-topic exclusion set, same "Average frontierness" (ACCORD
composite: 0.7 Expansion + 0.3 Acceleration, z-scored within bin) score column, same
primary-topic bare-id join `works_master.primary_topic_id` already uses for thm_frontier's own
texture rows. Because the counting method is byte-for-byte the same, the 20 topics thm_frontier's
texture rows already materialized reproduce IDENTICAL frontier_score_std/ul_works/isite_works
here -- asserted at BUILD time below by reading this SAME snapshot's own `tables/thm_frontier.parquet`
(written earlier in the same run by step 47; this is why `run_all.py` places 47c right after 47,
not by numbering coincidence).

CATALOG MEMBERSHIP vs SCORE FLOOR (two distinct NULL-causing conditions, per the dispatch's own
wording "outside the frontier catalog OR under the score's floor"):
  - `frontier_catalog_flag`: True iff the topic matches a baseline row AND is NOT on the
    811-exclusion list (47's own "kept" population) -- "in the catalog" independent of whether a
    numeric score happens to be defined.
  - the score's own "floor": 47's existing frontier code already gates on
    `wf["Average frontierness"].notna()` before calling a topic "scoreable" -- that exact gate is
    reused here, not invented. Measured on this snapshot: the world baseline carries exactly 2
    topics with a NaN Average frontierness, and BOTH are already on the 811-exclusion list, so
    among UL's 3,274-topic universe this floor currently binds on ZERO rows -- kept as a live
    guard (not assumed impossible on a future snapshot), never silently dropped.
`score_reason` names whichever condition actually caused a NULL score: 'excluded_811' /
'unmatched_baseline' (topic id absent from the baseline file entirely -- also measured ZERO this
snapshot) / 'no_baseline_score' (matched, kept, but the baseline's own score cell is NaN).

Usage: python pipeline/47c_build_frontier_topics.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.artifact import flag_works, load_bad_topics  # noqa: E402
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
CONFIG = load_config(ROOT)
CONF_STATES = ["all", "no_conf"]

TAXONOMY_COLS = ["topic_id", "topic_name", "subfield_id", "subfield_name",
                 "field_id", "field_name", "domain_id", "domain_name"]


def conf_mask(works: pd.DataFrame, state: str) -> pd.Series:
    return pd.Series(True, index=works.index) if state == "all" else ~works["is_conference"].fillna(False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    print(f"snapshot {snapshot.name}: building thm_frontier_topics (pass 5, S3b, ruling R11)")

    # =============================================================================== load inputs
    works = pd.read_parquet(tables / "works_master.parquet", columns=[
        "work_id", "primary_topic_id", "In_ISITE", "is_conference",
    ])
    corpus_topics = pd.read_parquet(tables / "corpus_topics.parquet",
                                    columns=["work_id", "topic_id", "is_primary"])
    all_topics = pd.read_parquet(tables / "all_topics.parquet", columns=TAXONOMY_COLS)

    n_corpus = len(works)
    print(f"  corpus works: {n_corpus:,}")

    flag_series = flag_works(corpus_topics, root=ROOT)
    works["work_artifact_flag"] = works["work_id"].map(flag_series).fillna(False).astype(bool)
    n_flagged = int(works["work_artifact_flag"].sum())
    print(f"  work-level artifact-flag (primary-topic exclusion): {n_flagged:,} works")
    assert n_flagged == 4106, f"artifact-flag count drifted: {n_flagged} != 4,106 (F0-P4 golden)"

    works["tid"] = works["primary_topic_id"].astype(str).str.replace(
        "https://openalex.org/", "", regex=False).str.strip()
    # Filter on the ORIGINAL column's own .notna(), never on a stringified sentinel: a nullable
    # ("string"-backend) column stringifies a missing value as the literal "<NA>", while a plain
    # object column stringifies it as "None" -- a "!= 'None'" check silently miscounts under the
    # other dtype (caught live: ul_pubs.parquet's DEPLOYED copy uses the nullable dtype and gave
    # 3,275 "topics" this way, one bogus entry for the 51 works with no primary topic at all).
    _has_primary = works["primary_topic_id"].notna()

    topic_universe = sorted(works.loc[_has_primary, "tid"].unique().tolist())
    n_topics = len(topic_universe)
    print(f"  UL topic universe (>=1 corpus PRIMARY-topic work): {n_topics:,}")
    assert n_topics == 3274, f"UL primary-topic universe drifted: {n_topics} != 3,274"

    # ============================================================================== baseline load
    # SAME file, SAME exclusion set, SAME score column as 47_build_thematic_ext.py's own frontier
    # section and 47b_build_crossings.py's own copy of it -- read again here rather than imported
    # (47 exposes no reusable function; this duplication matches 47b's own established precedent).
    baseline_path = ROOT / "inputs" / "manual" / "frontierness_baseline.xlsx"
    base = pd.read_excel(baseline_path, sheet_name="FILTERING OUT TOPICS")
    base.columns = [c.strip() for c in base.columns]
    KEY = "Topic ID no url"
    base[KEY] = base[KEY].astype(str).str.strip()

    bad_ids = load_bad_topics(ROOT)
    n_excluded_world = int(base[KEY].isin(bad_ids).sum())
    print(f"  baseline: {len(base):,} world topics, {n_excluded_world} on the 811-exclusion list")
    assert n_excluded_world == 811, f"exclusion count drifted: {n_excluded_world} != 811"

    baseline_vintage = (f"{dt.date.fromtimestamp(baseline_path.stat().st_mtime).isoformat()} copy-in "
                         f"date; source vintage: mid-2025 GBQ build (catalog card "
                         f"enr-frontierness-baseline trap #4 -- id-level drift vs the 2026-08-11 "
                         f"corpus pull measured ZERO)")
    score_column_used = "Average frontierness (ACCORD composite: 0.7 Expansion + 0.3 Acceleration, " \
                         "z-scored within bin -- catalog card enr-frontierness-baseline)"

    # ======================================================================== per-topic catalog
    topics_df = pd.DataFrame({"topic_id": topic_universe})
    topics_df["artifact_flag"] = topics_df["topic_id"].isin(bad_ids)
    matched_ids = set(base[KEY])
    topics_df["_matched"] = topics_df["topic_id"].isin(matched_ids)
    topics_df = topics_df.merge(
        base[[KEY, "Average frontierness"]].rename(columns={KEY: "topic_id"}),
        on="topic_id", how="left",
    )
    topics_df["frontier_catalog_flag"] = topics_df["_matched"] & ~topics_df["artifact_flag"]
    _score_defined = topics_df["frontier_catalog_flag"] & topics_df["Average frontierness"].notna()
    topics_df["frontier_score_std"] = np.where(_score_defined, topics_df["Average frontierness"], np.nan)

    # score_reason: NULL exactly when frontier_score_std is populated. Layered so the highest-
    # priority condition is applied last (score-defined always wins, regardless of the others).
    reason = pd.Series("no_baseline_score", index=topics_df.index, dtype="object")
    reason = reason.mask(topics_df["artifact_flag"], "excluded_811")
    reason = reason.mask(~topics_df["_matched"], "unmatched_baseline")
    reason = reason.mask(_score_defined, None)
    topics_df["score_reason"] = reason

    n_catalog_excluded = int(topics_df["artifact_flag"].sum())
    n_unmatched = int((~topics_df["_matched"]).sum())
    n_no_score = int((topics_df["frontier_catalog_flag"] & ~topics_df["Average frontierness"].notna()).sum())
    print(f"  UL topics on the 811-exclusion list: {n_catalog_excluded:,} (measured, not guessed)")
    print(f"  UL topics unmatched in the baseline file: {n_unmatched:,} (guard, measured zero)")
    print(f"  UL topics kept but with an undefined baseline score: {n_no_score:,} (guard, measured zero)")
    assert n_catalog_excluded == 297, f"excluded-topic count drifted: {n_catalog_excluded} != 297"

    topics_df = topics_df.drop(columns=["_matched", "Average frontierness"])

    # ---------------------------------------------------------------------------- taxonomy join
    all_topics_str = all_topics.copy()
    for col in ("subfield_id", "field_id", "domain_id"):
        all_topics_str[col] = all_topics_str[col].astype(str)
    topics_df = topics_df.merge(all_topics_str, on="topic_id", how="left")
    n_missing_tax = int(topics_df["topic_name"].isna().sum())
    assert n_missing_tax == 0, f"{n_missing_tax} UL topic(s) missing from all_topics.parquet taxonomy"

    # =============================================================================== per conf_state
    frames = []
    for state in CONF_STATES:
        m = conf_mask(works, state)
        sub = works[m]
        sub_xa = sub[~sub["work_artifact_flag"]]

        ul_counts = sub.groupby("tid")["work_id"].size().reindex(topic_universe, fill_value=0)
        ul_counts_xa = sub_xa.groupby("tid")["work_id"].size().reindex(topic_universe, fill_value=0)
        isite_counts = sub.loc[sub["In_ISITE"]].groupby("tid")["work_id"].size().reindex(
            topic_universe, fill_value=0)
        isite_counts_xa = sub_xa.loc[sub_xa["In_ISITE"]].groupby("tid")["work_id"].size().reindex(
            topic_universe, fill_value=0)

        frame = topics_df.copy()
        frame["conf_state"] = state
        frame["ul_works"] = frame["topic_id"].map(ul_counts).astype("int64")
        frame["ul_works_xa"] = frame["topic_id"].map(ul_counts_xa).astype("int64")
        frame["isite_works"] = frame["topic_id"].map(isite_counts).astype("int64")
        frame["isite_works_xa"] = frame["topic_id"].map(isite_counts_xa).astype("int64")
        frames.append(frame)
        print(f"  conf_state={state:8s} total ul_works={int(frame['ul_works'].sum()):,}  "
              f"total isite_works={int(frame['isite_works'].sum()):,}")

    out = pd.concat(frames, ignore_index=True)
    out["baseline_vintage"] = baseline_vintage
    out["score_column_used"] = score_column_used
    out["snapshot_date"] = snapshot.name

    ordered_cols = [
        "topic_id", "topic_name", "domain_id", "domain_name", "field_id", "field_name",
        "subfield_id", "subfield_name", "conf_state", "ul_works", "ul_works_xa",
        "isite_works", "isite_works_xa", "frontier_catalog_flag", "frontier_score_std",
        "score_reason", "artifact_flag", "baseline_vintage", "score_column_used", "snapshot_date",
    ]
    out = out[ordered_cols]
    out = out.astype({
        "topic_id": "string", "topic_name": "string", "domain_id": "string",
        "domain_name": "string", "field_id": "string", "field_name": "string",
        "subfield_id": "string", "subfield_name": "string", "conf_state": "string",
        "ul_works": "int64", "ul_works_xa": "int64", "isite_works": "int64",
        "isite_works_xa": "int64", "frontier_catalog_flag": "bool",
        "score_reason": "string", "artifact_flag": "bool", "baseline_vintage": "string",
        "score_column_used": "string", "snapshot_date": "string",
    })
    print(f"\n  wrote {len(out):,} rows x {len(out.columns)} cols "
          f"({n_topics:,} topics x {len(CONF_STATES)} conf_states)")
    assert len(out) == n_topics * len(CONF_STATES) == 6548, f"row count drifted: {len(out):,} != 6,548"

    # =================================================================================== asserts
    print("\n" + "=" * 78)
    print("ACCEPTANCE ASSERTS")
    print("=" * 78)

    assert (out["isite_works"] <= out["ul_works"]).all(), "isite_works must never exceed ul_works"
    assert (out["isite_works_xa"] <= out["ul_works_xa"]).all(), (
        "isite_works_xa must never exceed ul_works_xa")
    assert (out["ul_works_xa"] <= out["ul_works"]).all(), "ul_works_xa must never exceed ul_works"

    _score_null = out["frontier_score_std"].isna()
    _reason_null = out["score_reason"].isna()
    assert (_score_null == ~_reason_null).all(), (
        "frontier_score_std NULL must be exactly equivalent to score_reason non-null")
    print("  score/reason mutual-exclusion check: PASS")

    # ---- GOLDEN CONTINUITY: the 20 topics thm_frontier's own texture rows already materialized
    # must reproduce IDENTICAL scores + counts here. Requires 47 to have already run THIS
    # snapshot (run_all.py places 47c right after 47) -- read the just-written table, never the
    # deployed copy (that would be the 45b/49w-style bootstrap landmine this codebase already
    # knows to avoid).
    frontier_path = tables / "thm_frontier.parquet"
    if not frontier_path.is_file():
        raise FileNotFoundError(
            f"{frontier_path} missing -- 47_build_thematic_ext.py must run BEFORE 47c in this "
            "same snapshot (run_all.py's own step order); the golden-continuity cross-check below "
            "has nothing to compare against without it."
        )
    tf = pd.read_parquet(frontier_path)
    texture = tf[tf["row_kind"] == "texture"]
    n_texture_topics = texture["topic_id"].nunique()
    print(f"\n  golden continuity: cross-checking against thm_frontier's {len(texture)} texture "
          f"rows ({n_texture_topics} distinct topics x {len(CONF_STATES)} conf_states)")
    merged = texture.merge(
        out, on=["topic_id", "conf_state"], how="left", suffixes=("_old", "_new"),
    )
    assert len(merged) == len(texture), "golden-continuity join dropped or duplicated a row"
    assert merged["frontier_score_std_new"].notna().all(), (
        "a texture topic is missing a score in thm_frontier_topics -- golden continuity broken")
    _score_mismatch = merged[~np.isclose(
        merged["frontier_score_std_old"].astype(float), merged["frontier_score_std_new"].astype(float),
    )]
    assert _score_mismatch.empty, (
        f"{len(_score_mismatch)} texture topic(s) reproduce a DIFFERENT frontier_score_std: "
        f"{_score_mismatch[['topic_id', 'conf_state']].to_dict('records')}"
    )
    for col in ("ul_works", "ul_works_xa", "isite_works", "isite_works_xa"):
        _count_mismatch = merged[merged[f"{col}_old"] != merged[f"{col}_new"]]
        assert _count_mismatch.empty, (
            f"{len(_count_mismatch)} texture topic(s) reproduce a DIFFERENT {col}: "
            f"{_count_mismatch[['topic_id', 'conf_state']].to_dict('records')}"
        )
    print(f"  GOLDEN CONTINUITY: all {len(merged)} texture rows reproduce IDENTICAL "
          f"frontier_score_std/ul_works/ul_works_xa/isite_works/isite_works_xa -- PASS")

    # =================================================================================== write out
    compression = CONFIG["storage"]["compression"]
    out_path = tables / "thm_frontier_topics.parquet"
    out.to_parquet(out_path, index=False, compression=compression)
    size_kb = out_path.stat().st_size / 1024
    print(f"\nwrote thm_frontier_topics.parquet: {len(out):,} rows x {len(out.columns)} cols, "
          f"{size_kb:,.1f} KB")

    Manifest(snapshot).record_step(
        "47c_build_frontier_topics",
        counts={"thm_frontier_topics": len(out)},
        files=[out_path],
        params={
            "topic_universe": n_topics,
            "n_catalog_excluded": n_catalog_excluded,
            "n_unmatched_baseline": n_unmatched,
            "n_no_baseline_score": n_no_score,
            "frontier_baseline": "inputs/manual/frontierness_baseline.xlsx (SAME copy-in "
                                  "thm_frontier.parquet reads)",
        },
        notes="Pass 5 (S3b), ruling R11 (full-depth materialization): thm_frontier_topics extends "
              "47's frontier construction from the 20-row global top-slice to ALL 3,274 UL "
              "primary topics. Golden continuity (20 old texture topics x 2 conf_states) "
              "reproduces IDENTICAL scores and counts -- see progress/S3b_frontier_depth.md.",
    )
    append_summary(snapshot, "47c_build_frontier_topics", [
        f"- `thm_frontier_topics`: {len(out):,} rows ({n_topics:,} topics x "
        f"{len(CONF_STATES)} conf_states)",
        f"- catalog: {n_catalog_excluded:,} topics on the 811-exclusion list, {n_unmatched:,} "
        f"unmatched in the baseline file, {n_no_score:,} kept-but-undefined-score",
        f"- golden continuity vs thm_frontier's own 20-topic texture rows: PASS "
        f"({len(merged)} rows, exact reproduction of score + all 4 count columns)",
    ])
    print("\ndone.")


if __name__ == "__main__":
    main()
