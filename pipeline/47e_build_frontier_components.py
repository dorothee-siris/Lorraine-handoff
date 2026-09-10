"""47e_build_frontier_components.py -- dim_frontier_components (pass 7, P6 D40).

WHY THIS EXISTS / WHY IT IS A SEPARATE TABLE FROM thm_frontier / thm_frontier_topics: those two
tables (47_build_thematic_ext.py / 47c_build_frontier_topics.py) carry the ACCORD **composite**
"Average frontierness" score -- one number per topic, built by 47's own construction from
`inputs/manual/frontierness_baseline.xlsx` (== `OA_bad_topics.xlsx`, byte-identical, see
`docs/FRONTIERNESS_METHOD.md`), whose bins are SIX 4-year windows. This builder reads a DIFFERENT
manual file, `inputs/manual/OA_frontier_scores.xlsx` (sheet `global`), which carries the frontier
score's own **components** (expansion, acceleration, and the resulting frontier score, plus each
topic's world RANK that year) across SEVEN 3-year bins. The two vintages are NEVER interchangeable
and NEVER mixed in one figure (docs/FRONTIERNESS_METHOD.md states the rule) -- this table exists so
a view can plot a topic's trajectory across bins (something the single composite score cannot show).

Grain: topic_id x bin_label (LONG). Sheet `global` = 3,706 topics x 7 bins = 25,942 rows.
`topic_id` here is a bare `T#####` id (the source column is the FULL `https://openalex.org/T#####`
url form -- stripped to match `all_topics.parquet.topic_id`'s own bare-string convention, verified
at build time below). The source file's OWN `Topic ID no url` column is present but 100% NaN in
this particular file (unlike frontierness_baseline.xlsx's, which IS populated) -- not used.

bin_label: derived from the column-name suffix (`2004-2006` -> `2004-06`, ..., `2022-2023` ->
`2022-23`) -- 7 values, `is_latest` True for the `2022-2023` bin (the most recent).

Reproduction: NOT reproducible via the OpenAlex API in this pass (per-topic per-year citation sums
2001-2023 unavailable through the API's own `counts_by_year`, which covers ~10 years, all types --
see docs/FRONTIERNESS_METHOD.md). This builder only RESHAPES the manual copy-in; it computes
nothing the source file didn't already compute.

Usage: python pipeline/47e_build_frontier_components.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot, sha256  # noqa: E402

ascii_safe_stdout()
CONFIG = load_config(ROOT)

SOURCE_REL = "inputs/manual/OA_frontier_scores.xlsx"
SHEET = "global"
BIN_SUFFIXES = ["2004-2006", "2007-2009", "2010-2012", "2013-2015", "2016-2018", "2019-2021",
                "2022-2023"]
LATEST_SUFFIX = "2022-2023"
N_TOPICS_EXPECTED = 3706
URL_PREFIX = "https://openalex.org/"


def bin_label_of(suffix: str) -> str:
    """'2004-2006' -> '2004-06'; '2022-2023' -> '2022-23' (drop the redundant leading digits of
    the end year -- both halves of every suffix here share the same century+decade lead pair)."""
    start, end = suffix.split("-")
    return f"{start}-{end[-2:]}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    print(f"snapshot {snapshot.name}: building dim_frontier_components (pass 7, P6 D40)")

    source_path = ROOT / SOURCE_REL
    if not source_path.is_file():
        raise FileNotFoundError(f"{source_path} missing -- expected the W1 copy-in (see "
                                 "progress/P7_DAT.md Deliverable 1)")
    source_hash = sha256(source_path)

    wide = pd.read_excel(source_path, sheet_name=SHEET)
    wide.columns = [c.strip() for c in wide.columns]
    print(f"  source: {source_path.relative_to(ROOT)} sheet={SHEET!r} -> {len(wide):,} rows x "
          f"{len(wide.columns)} cols (sha256 {source_hash[:12]}...)")
    assert len(wide) == N_TOPICS_EXPECTED, f"topic-row count drifted: {len(wide):,} != {N_TOPICS_EXPECTED:,}"

    # `Topic ID no url` is present in THIS file but measured 100% empty (unlike frontierness_
    # baseline.xlsx's own column of the same name) -- disclosed, not used; bare id comes from
    # stripping the URL prefix off the full `topic_id` column instead.
    n_no_url_populated = int(wide["Topic ID no url"].notna().sum()) if "Topic ID no url" in wide.columns else 0
    print(f"  'Topic ID no url' column populated rows: {n_no_url_populated:,} (expected 0 -- disclosed, unused)")

    wide["topic_id"] = wide["topic_id"].astype(str).str.strip().str.replace(URL_PREFIX, "", regex=False)
    assert wide["topic_id"].str.match(r"^T\d+$").all(), "a topic_id did not reduce to bare 'T#####' form"
    assert wide["topic_id"].is_unique, "duplicate topic_id in the source sheet"

    # ------------------------------------------------------------------------------------- melt
    frames = []
    for suffix in BIN_SUFFIXES:
        label = bin_label_of(suffix)
        frame = pd.DataFrame({
            "topic_id": wide["topic_id"],
            "bin_label": label,
            "expansion": wide[f"expansion_global_{suffix}"].astype("float32"),
            "acceleration": wide[f"acceleration_score_global_{suffix}"].astype("float32"),
            "frontier": wide[f"frontier_global_{suffix}"].astype("float32"),
            "rank": wide[f"rank_global_{suffix}"].astype("Int16"),
            "is_latest": suffix == LATEST_SUFFIX,
        })
        frames.append(frame)

    out = pd.concat(frames, ignore_index=True)
    out["source_file"] = SOURCE_REL
    out["source_sha256"] = source_hash
    out["snapshot_date"] = snapshot.name
    out["bin_label"] = out["bin_label"].astype("category")
    out = out.sort_values(["topic_id", "bin_label"], kind="stable").reset_index(drop=True)
    # sort_values on a category column orders by CATEGORY DEFINITION order, not chronology, unless
    # the categories are declared ordered in the chronological sequence -- do that explicitly so
    # "sorted by topic_id" (the brief's own acceptance wording) still yields chronological bins
    # within each topic, not alphabetical ('2004-06' < '2007-09' < ... is alphabetical here anyway,
    # but this makes the intent explicit rather than a coincidence of the label strings).
    ordered_labels = [bin_label_of(s) for s in BIN_SUFFIXES]
    out["bin_label"] = out["bin_label"].cat.set_categories(ordered_labels, ordered=True)
    out = out.sort_values(["topic_id", "bin_label"], kind="stable").reset_index(drop=True)

    print(f"  wrote {len(out):,} rows ({wide['topic_id'].nunique():,} topics x {len(BIN_SUFFIXES)} bins)")
    assert len(out) == N_TOPICS_EXPECTED * len(BIN_SUFFIXES) == 25942, (
        f"row count drifted: {len(out):,} != 25,942")

    # =================================================================================== asserts
    print("\n" + "=" * 78)
    print("ACCEPTANCE ASSERTS")
    print("=" * 78)

    n_is_latest = out.groupby("topic_id")["is_latest"].sum()
    assert (n_is_latest == 1).all(), "every topic must have EXACTLY one is_latest=True row"
    print(f"  exactly one is_latest row per topic: PASS ({int(n_is_latest.sum()):,} True rows)")

    latest = out[out["is_latest"]]
    desc = latest[["expansion", "acceleration"]].describe()
    exp_mean, exp_std = float(desc.loc["mean", "expansion"]), float(desc.loc["std", "expansion"])
    acc_mean, acc_std = float(desc.loc["mean", "acceleration"]), float(desc.loc["std", "acceleration"])
    print(f"  latest-bin describe(): expansion mean={exp_mean:.6f} std={exp_std:.4f}; "
          f"acceleration mean={acc_mean:.6f} std={acc_std:.4f}")
    assert abs(exp_mean) < 0.001, f"latest expansion mean {exp_mean} not ~0"
    assert abs(acc_mean) < 0.001, f"latest acceleration mean {acc_mean} not ~0"
    assert abs(exp_std - 0.674) < 0.005, f"latest expansion std {exp_std} != 0.674 +/- 0.005"
    assert abs(acc_std - 0.841) < 0.005, f"latest acceleration std {acc_std} != 0.841 +/- 0.005"
    print("  describe() targets (mean~0, std 0.674/0.841 +/-0.005): PASS")

    all_topics = pd.read_parquet(tables / "all_topics.parquet", columns=["topic_id"])
    all_topics_ids = set(all_topics["topic_id"].astype(str))
    component_ids = set(out["topic_id"])
    n_not_in_all_topics = len(component_ids - all_topics_ids)
    print(f"  component topic_ids NOT present in all_topics.parquet: {n_not_in_all_topics:,} "
          f"(disclosed, not a failure)")

    corr = np.corrcoef(0.7 * out["expansion"] + 0.3 * out["acceleration"], out["frontier"])[0, 1]
    print(f"  corr(0.7*expansion + 0.3*acceleration, frontier) = {corr:.6f}")
    assert corr > 0.999, f"composite correlation {corr:.6f} <= 0.999"

    ordered_cols = ["topic_id", "bin_label", "expansion", "acceleration", "frontier", "rank",
                    "is_latest", "source_file", "source_sha256", "snapshot_date"]
    out = out[ordered_cols]

    # ================================================================================= write out
    compression = CONFIG["storage"]["compression"]
    out_path = tables / "dim_frontier_components.parquet"
    out.to_parquet(out_path, index=False, compression=compression)
    size_kb = out_path.stat().st_size / 1024
    print(f"\nwrote dim_frontier_components.parquet: {len(out):,} rows x {len(out.columns)} cols, "
          f"{size_kb:,.1f} KB")

    Manifest(snapshot).record_step(
        "47e_build_frontier_components",
        counts={"dim_frontier_components": len(out)},
        files=[out_path],
        params={
            "n_topics": N_TOPICS_EXPECTED,
            "n_bins": len(BIN_SUFFIXES),
            "n_not_in_all_topics": n_not_in_all_topics,
            "composite_corr": round(float(corr), 6),
            "source_file": SOURCE_REL,
            "source_sha256": source_hash,
        },
        notes="Pass 7 (P6 D40): dim_frontier_components carries the frontierness COMPONENTS "
              "(expansion/acceleration/frontier/rank) across 7x 3-year bins, from a DIFFERENT "
              "manual file than thm_frontier's 6x 4-year composite -- never mixed in one figure "
              "(docs/FRONTIERNESS_METHOD.md). Reshape only, no scores computed here.",
    )
    append_summary(snapshot, "47e_build_frontier_components", [
        f"- `dim_frontier_components`: {len(out):,} rows ({N_TOPICS_EXPECTED:,} topics x "
        f"{len(BIN_SUFFIXES)} bins)",
        f"- latest-bin describe(): expansion mean={exp_mean:.6f} std={exp_std:.4f}; "
        f"acceleration mean={acc_mean:.6f} std={acc_std:.4f}",
        f"- composite check corr(0.7E+0.3A, frontier) = {corr:.6f} (> 0.999)",
        f"- topic_ids absent from all_topics.parquet: {n_not_in_all_topics:,}",
    ])
    print("\ndone.")


if __name__ == "__main__":
    main()
