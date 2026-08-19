"""44h_build_zero_fill.py -- topics_zero_fill.parquet / subfields_zero_fill.parquet (pass 6, #20).

`thematic_overview.parquet` (44_build_thematic.py) only carries a row for a taxonomy node the
Lorraine corpus actually USES (3,275 of 4,516 topics; 246 of 252 subfields per the OpenAlex
taxonomy dictionary all_topics.parquet) -- so a query for e.g. "quantum" against page 4's topics
table (today capped at head(200) too, #20's other half) can miss a real quantum topic entirely if
UL has zero works on it. These two tables are the FULL-VOCAB display twins: one row per topic/
subfield the taxonomy defines, PERIOD -- volumes zero-filled, rates left NULL (D53: a ratio over
zero works is unknown, never a fabricated 0), joined against `thematic_overview`'s own already-
computed columns (incl. the pass-6 momentum columns, #18 -- see 44_build_thematic.py) wherever a
row exists there.

Must run AFTER 44_build_thematic.py (reads its thematic_overview.parquet output, mom_* included).

Usage: python pipeline/44h_build_zero_fill.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
CONFIG = load_config(ROOT)

# columns carried over from thematic_overview verbatim (rate/stat columns: stay NULL when the
# node has 0 works -- never fabricated as 0, D53); pubs_total/pubs_pct_of_ul are the two exceptions
# genuinely well-defined at n=0 (a count of 0 IS 0; 0/corpus IS 0.0).
RATE_COLUMNS = [
    "pct_isite", "pct_top10", "pct_top1", "pct_international", "pct_company", "pct_sdg",
    "cagr_2019_2023", "fwci_median", "fwci_mean", "fwci_boxplot",
    "mom_class", "mom_p_value", "mom_w1_share", "mom_w2_share", "mom_eligible_flag",
]


def build_zero_fill(dictionary: pd.DataFrame, overview_level: pd.DataFrame, id_col: str,
                    name_col: str) -> pd.DataFrame:
    overview_cols = ["id", "pubs_total", "pubs_pct_of_ul"] + [
        c for c in RATE_COLUMNS if c in overview_level.columns
    ]
    ov = overview_level[overview_cols].rename(columns={"id": id_col})
    ov[id_col] = ov[id_col].astype(str)
    merged = dictionary.merge(ov, on=id_col, how="left")
    merged["pubs_total"] = merged["pubs_total"].fillna(0).astype("int64")
    merged["pubs_pct_of_ul"] = merged["pubs_pct_of_ul"].fillna(0.0).astype("float64")
    merged["has_corpus_works"] = merged["pubs_total"] > 0
    return merged


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    all_topics = pd.read_parquet(tables / "all_topics.parquet")
    overview = pd.read_parquet(tables / "thematic_overview.parquet")
    print(f"snapshot {snapshot.name}: all_topics {len(all_topics):,} topics, "
          f"{all_topics['subfield_id'].nunique()} subfields; thematic_overview {len(overview):,} rows")

    at = all_topics.assign(
        domain_id=all_topics["domain_id"].astype(str), field_id=all_topics["field_id"].astype(str),
        subfield_id=all_topics["subfield_id"].astype(str), topic_id=all_topics["topic_id"].astype(str),
    )

    # ---- topics_zero_fill: one row per topic_id in the FULL OpenAlex vocabulary ----------------
    topic_dict = at[["topic_id", "topic_name", "subfield_id", "subfield_name", "field_id",
                     "field_name", "domain_id", "domain_name"]].drop_duplicates("topic_id")
    topics_overview = overview[overview["level"] == "topic"]
    topics_zero_fill = build_zero_fill(topic_dict, topics_overview, "topic_id", "topic_name")
    topics_zero_fill["snapshot_date"] = snapshot.name

    n_topics_vocab = topic_dict["topic_id"].nunique()
    assert len(topics_zero_fill) == n_topics_vocab, (
        f"topics_zero_fill row count {len(topics_zero_fill)} != vocab count {n_topics_vocab}"
    )
    n_quantum = int(topics_zero_fill["topic_name"].str.contains("quantum", case=False, na=False).sum())
    n_quantum_zero = int((topics_zero_fill["topic_name"].str.contains("quantum", case=False, na=False)
                          & ~topics_zero_fill["has_corpus_works"]).sum())
    print(f"  topics_zero_fill: {len(topics_zero_fill):,} rows (vocab {n_topics_vocab:,}); "
          f"'quantum' substring matches {n_quantum} topics, {n_quantum_zero} of them at 0 UL works "
          f"(all still present -- the #20 invariant)")

    # ---- subfields_zero_fill: one row per subfield_id in the FULL OpenAlex vocabulary -----------
    subfield_dict = at[["subfield_id", "subfield_name", "field_id", "field_name", "domain_id",
                        "domain_name"]].drop_duplicates("subfield_id")
    subfields_overview = overview[overview["level"] == "subfield"]
    subfields_zero_fill = build_zero_fill(subfield_dict, subfields_overview, "subfield_id",
                                          "subfield_name")
    subfields_zero_fill["snapshot_date"] = snapshot.name

    n_subfields_vocab = subfield_dict["subfield_id"].nunique()
    assert len(subfields_zero_fill) == n_subfields_vocab, (
        f"subfields_zero_fill row count {len(subfields_zero_fill)} != vocab count {n_subfields_vocab}"
    )
    print(f"  subfields_zero_fill: {len(subfields_zero_fill):,} rows (vocab {n_subfields_vocab:,})")

    for frame, name in ((topics_zero_fill, "topics_zero_fill"), (subfields_zero_fill, "subfields_zero_fill")):
        key = "topic_id" if name == "topics_zero_fill" else "subfield_id"
        dupes = int(frame.duplicated(key).sum())
        assert dupes == 0, f"{name}: {dupes} duplicate {key} rows"

    compression = CONFIG["storage"]["compression"]
    out_topics = tables / "topics_zero_fill.parquet"
    out_subfields = tables / "subfields_zero_fill.parquet"
    topics_zero_fill.to_parquet(out_topics, index=False, compression=compression)
    subfields_zero_fill.to_parquet(out_subfields, index=False, compression=compression)

    lines = [
        f"- `topics_zero_fill`: **{len(topics_zero_fill):,}** rows == full OpenAlex topic vocab "
        f"({n_topics_vocab:,}); **{int(topics_zero_fill['has_corpus_works'].sum()):,}** have "
        f">=1 UL work",
        f"- `subfields_zero_fill`: **{len(subfields_zero_fill):,}** rows == full subfield vocab "
        f"({n_subfields_vocab:,}); **{int(subfields_zero_fill['has_corpus_works'].sum()):,}** have "
        f">=1 UL work",
        f"- invariant check: 'quantum' substring matches **{n_quantum}** topics, ALL present "
        f"(incl. **{n_quantum_zero}** at 0 UL works) -- the exact #20 acceptance example",
        "- rate/stat columns (pct_*, cagr, fwci_*, mom_*) stay NULL on zero-work rows (D53); "
        "pubs_total=0 and pubs_pct_of_ul=0.0 are the two well-defined exceptions",
    ]
    report = ROOT / CONFIG["paths"]["reports"] / "zero_fill.md"
    report.write_text("# topics_zero_fill / subfields_zero_fill (pass 6, #20)\n\n"
                      + "\n".join(lines) + "\n", encoding="utf-8")
    Manifest(snapshot).record_step(
        "44h_build_zero_fill",
        counts={"topics_zero_fill_rows": len(topics_zero_fill), "topics_vocab": n_topics_vocab,
                "subfields_zero_fill_rows": len(subfields_zero_fill), "subfields_vocab": n_subfields_vocab,
                "quantum_topics": n_quantum, "quantum_topics_at_zero": n_quantum_zero},
        files=[out_topics, out_subfields],
        notes="Pass 6, #20: full-vocabulary display twins of thematic_overview's topic/subfield "
              "rows -- no top-200 cap possible on the data side any more (row count == vocab "
              "count, asserted).",
    )
    append_summary(snapshot, "44h_build_zero_fill", lines)
    print("\n".join(lines))
    print(f"\nwrote {out_topics.name}, {out_subfields.name}")


if __name__ == "__main__":
    main()
