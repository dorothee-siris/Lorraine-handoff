"""41_build_lookups.py — the global aggregates the app reads for its headline figures.

Deliberately free of topic-model breakdowns (D9): where v1's lookup table carried "Classic TM" and
"Research Topic" dimensions, v2 carries the OpenAlex taxonomy, which every work has and the client
can regenerate.

One long table, `ul_lookup`, keyed by (dimension, entity, year) with `year = 'all'` for the window
total, so the app can read one file and filter rather than joining several.

Usage: python pipeline/41_build_lookups.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)


def summarise(block: pd.DataFrame) -> dict:
    computed = block[block["indicator_status"] == "computed"] if "indicator_status" in block else block.iloc[0:0]
    out = {
        "works": len(block),
        "citations": int(block["cited_by_count"].fillna(0).sum()),
        "citations_per_work": round(float(block["cited_by_count"].fillna(0).mean()), 3),
        "in_isite_works": int(block["In_ISITE"].sum()),
        "international_share": round(float(block["Is_international"].mean()), 4),
        "company_collab_works": int(block["Is_company"].sum()),
        "abstract_coverage": round(float(block["abstract"].notna().mean()), 4),
        "with_doi_share": round(float(block["has_doi"].mean()), 4),
    }
    if block["is_oa"].notna().any():
        out["oa_share"] = round(float(block["is_oa"].astype("boolean").mean()), 4)
    if len(computed):
        out["works_with_indicators"] = len(computed)
        out["FWCI_FR_mean"] = round(float(computed["FWCI_FR"].mean()), 4)
        out["FWCI_FR_median"] = round(float(computed["FWCI_FR"].median()), 4)
        out["PPtop10_FR_share"] = round(float(computed["PPtop10_FR"].astype(float).mean()), 4)
        out["PPtop1_FR_share"] = round(float(computed["PPtop1_FR"].astype(float).mean()), 4)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    works = pd.read_parquet(tables / "works_master.parquet")
    print(f"snapshot {snapshot.name}: {len(works):,} works")

    rows: list[dict] = []

    def add(dimension: str, entity: str, block: pd.DataFrame, by_year: bool = True) -> None:
        rows.append({"dimension": dimension, "entity": str(entity), "year": "all", **summarise(block)})
        if by_year:
            for year, chunk in block.groupby("publication_year", observed=True):
                rows.append({"dimension": dimension, "entity": str(entity), "year": str(int(year)),
                             **summarise(chunk)})

    add("total", "Universite de Lorraine", works)
    for column, dimension in [("type", "doc_type"), ("language", "language"),
                              ("oa_status", "oa_status"), ("primary_domain_name", "domain"),
                              ("abstract_source", "abstract_source")]:
        for entity, block in works.assign(**{column: works[column].fillna("(inconnu)")}) \
                                  .groupby(column, observed=True):
            add(dimension, entity, block)
    for entity, block in works[works["In_ISITE"]].groupby("publication_year", observed=True):
        rows.append({"dimension": "isite", "entity": "In_ISITE", "year": str(int(entity)), **summarise(block)})
    rows.append({"dimension": "isite", "entity": "In_ISITE", "year": "all",
                 **summarise(works[works["In_ISITE"]])})

    # top sources (journals / proceedings), useful on the landing page and cheap to precompute
    top_sources = works["primary_source_name"].value_counts().head(50)
    for entity in top_sources.index:
        add("source", entity, works[works["primary_source_name"] == entity], by_year=False)

    lookup = pd.DataFrame(rows)
    out = tables / "ul_lookup.parquet"
    lookup.to_parquet(out, index=False, compression=CONFIG["storage"]["compression"])

    # invariant: the doc_type dimension must account for the whole corpus in the 'all' rows
    total_by_type = lookup[(lookup["dimension"] == "doc_type") & (lookup["year"] == "all")]["works"].sum()
    assert total_by_type == len(works), f"doc_type rows sum to {total_by_type:,}, expected {len(works):,}"

    banned = ("Classic TM", "Research Topic", "TM_labels", "Objective", "Method", "Impact")
    assert not any(b.lower() in str(e).lower() for e in lookup["entity"] for b in banned), \
        "a topic-model entity leaked into the lookup table (D9)"

    headline = summarise(works)
    lines = [
        f"- lookup table: **{len(lookup):,}** rows across {lookup['dimension'].nunique()} dimensions "
        f"({', '.join(sorted(lookup['dimension'].unique()))})",
        f"- corpus: **{headline['works']:,}** works · {headline['citations']:,} citations "
        f"({headline['citations_per_work']} per work)",
        f"- mean `FWCI_FR` **{headline.get('FWCI_FR_mean')}** · `PPtop10_FR` share "
        f"**{headline.get('PPtop10_FR_share', 0):.1%}** · `PPtop1_FR` "
        f"**{headline.get('PPtop1_FR_share', 0):.1%}**",
        f"- open access **{headline.get('oa_share', 0):.1%}** · international **{headline['international_share']:.1%}** "
        f"· with a company **{headline['company_collab_works']:,}**",
        f"- I-SITE flagged **{headline['in_isite_works']:,}** · abstracts **{headline['abstract_coverage']:.1%}** "
        f"· with a DOI **{headline['with_doi_share']:.1%}**",
        "- **zero topic-model dimensions** (D9)",
        "",
        "| Year | Works | Citations/work | mean FWCI_FR | PPtop10 | OA |",
        "|---|---|---|---|---|---|",
    ]
    for row in lookup[(lookup["dimension"] == "total") & (lookup["year"] != "all")].itertuples():
        lines.append(f"| {row.year} | {row.works:,} | {row.citations_per_work} | "
                     f"{getattr(row, 'FWCI_FR_mean', '')} | "
                     f"{getattr(row, 'PPtop10_FR_share', 0):.1%} | {getattr(row, 'oa_share', 0):.1%} |")

    report = ROOT / CONFIG["paths"]["reports"] / "ul_lookup.md"
    report.write_text("# Global lookups\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    Manifest(snapshot).record_step(
        "41_build_lookups",
        counts={"rows": len(lookup), "dimensions": int(lookup["dimension"].nunique())},
        files=[out],
        params={"topic_model_dimensions": False},
        notes="D9: OpenAlex taxonomy replaces the TM dimensions v1 carried here.",
    )
    append_summary(snapshot, "41_build_lookups", lines[:6])
    print("\n".join(lines))
    print(f"\nwrote {out.name} and {report}")


if __name__ == "__main__":
    main()
