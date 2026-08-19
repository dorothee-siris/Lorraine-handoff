"""42_build_partners.py — collaborating institutions, ROR-identified.

The offer's co-design section is explicitly about exploring "les collaborations de l'I-SITE Lorraine,
telles que reconnues dans OpenAlex, c'est-à-dire les structures identifiées par un ROR", so this table
is the substrate the workshop will design views on: every non-UL institution appearing on a corpus
work, with volume, impact, sector and the Lorraine labs it actually works with.

Built as a set union over the native `corpus_authorships` rows. v1 derived the equivalent from
`[n]`-indexed strings; that parsing shifted per-author values on 51.4% of works and, while set-union
consumers were provably immune, there is no reason to reintroduce the format.

UL's own structures are excluded from the partner list (they are the subject, not a partner) but the
count of works involving them is kept for reconciliation.

Usage: python pipeline/42_build_partners.py [--snapshot 2026-08-11]
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
MIN_WORKS = 1
TOP_N = 10


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--min-works", type=int, default=MIN_WORKS)
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    works = pd.read_parquet(tables / "works_master.parquet")
    authorships = pd.read_parquet(tables / "corpus_authorships.parquet")
    labs_list = pd.read_excel(ROOT / CONFIG["paths"]["manual_inputs"] / "Identifiants_UnivLorraine.xlsx")
    print(f"snapshot {snapshot.name}: {len(works):,} works · {len(authorships):,} authorship rows")

    # UL itself plus every curated structure, and the OpenAlex descendants of UL, are "us" not "them"
    repairs = CONFIG["perimeter"].get("openalex_id_repairs") or {}
    own_ids = {CONFIG["perimeter"]["ul_openalex_id"]} | {
        repairs.get(str(x).strip(), str(x).strip()) for x in labs_list["OpenAlex"].dropna()
    }
    own_rors = {str(x).strip().lower() for x in labs_list["ROR"].dropna()} | {CONFIG["perimeter"]["ul_ror"]}

    # Everything OpenAlex places under UL is internal, not a partner — including the 22 structures the
    # client's list does not name (D20). Without this, UL collaborates with itself: the first run had
    # "Laboratoire Lorrain de Sciences Sociales" in the top 15 partners with 690 co-works.
    descendants_path = tables / "ul_descendants.parquet"
    if descendants_path.exists():
        descendants = pd.read_parquet(descendants_path)
        own_ids |= set(descendants["openalex_id"])
        own_rors |= {r for r in descendants["ror"].dropna()}
        print(f"  UL structures treated as internal: {len(own_ids)} ids "
              f"({int((~descendants['in_client_list']).sum())} of them absent from the client list)")
    else:
        print("  ! ul_descendants.parquet missing — run 12_ul_descendants.py first, or UL's own "
              "unmapped structures will be counted as external partners")

    inst = authorships.dropna(subset=["institution_id"])[
        ["work_id", "institution_id", "institution_ror", "institution_display_name",
         "institution_country", "institution_type"]
    ].drop_duplicates(["work_id", "institution_id"])
    own_mask = inst["institution_id"].isin(own_ids) | inst["institution_ror"].isin(own_rors)
    partners = inst[~own_mask]
    print(f"  institution-work pairs: {len(inst):,} · own structures {int(own_mask.sum()):,} · "
          f"partner pairs {len(partners):,}")
    # A ROR is what makes a partner addressable; those without one are counted but not listed.
    no_ror = partners["institution_ror"].isna().sum()
    partners = partners[partners["institution_ror"].notna()]
    print(f"  partner pairs without a ROR (excluded from the table, reported here): {no_ror:,}")

    work_meta = works.set_index("work_id")
    lab_of_work = work_meta["Labs"].to_dict()
    joined = partners.join(
        work_meta[["publication_year", "cited_by_count", "In_ISITE", "FWCI_FR", "PPtop10_FR",
                   "indicator_status", "primary_subfield_name", "is_conference"]],
        on="work_id",
    )

    rows = []
    for (institution_id, name), block in joined.groupby(
        ["institution_id", "institution_display_name"], observed=True
    ):
        if len(block) < args.min_works:
            continue
        computed = block[block["indicator_status"] == "computed"]
        lab_names: dict[str, int] = {}
        for work_id in block["work_id"]:
            for lab in str(lab_of_work.get(work_id, "")).split(" | "):
                if lab and lab != "NO LAB":
                    lab_names[lab] = lab_names.get(lab, 0) + 1
        top_labs = sorted(lab_names.items(), key=lambda kv: -kv[1])[:TOP_N]
        rows.append({
            "institution_id": institution_id,
            "institution_name": name,
            "ror": block["institution_ror"].iloc[0],
            "country": block["institution_country"].iloc[0],
            "sector": block["institution_type"].iloc[0],
            "co_works": len(block),
            "citations": int(block["cited_by_count"].fillna(0).sum()),
            "co_works_with_indicators": len(computed),
            "FWCI_FR_mean": round(float(computed["FWCI_FR"].mean()), 4) if len(computed) else None,
            "PPtop10_FR_share": round(float(computed["PPtop10_FR"].astype(float).mean()), 4) if len(computed) else None,
            "in_isite_co_works": int(block["In_ISITE"].sum()),
            "conference_share": round(float(block["is_conference"].mean()), 4) if "is_conference" in block else None,
            "first_year": int(block["publication_year"].min()),
            "last_year": int(block["publication_year"].max()),
            "n_lorraine_labs": len(lab_names),
            "top_lorraine_labs": " | ".join(f"{lab} ({n})" for lab, n in top_labs),
            "top_subfields": " | ".join(
                f"{s} ({n})" for s, n in block["primary_subfield_name"].value_counts().head(5).items()
            ),
        })

    table = pd.DataFrame(rows).sort_values("co_works", ascending=False)
    out = tables / "ul_partners.parquet"
    table.to_parquet(out, index=False, compression=CONFIG["storage"]["compression"])

    foreign = table[table["country"] != "FR"]
    companies = table[table["sector"] == "company"]
    lines = [
        f"- partner institutions (ROR-identified, UL's own structures excluded): **{len(table):,}**",
        f"- of which foreign: **{len(foreign):,}** ({len(foreign)/max(len(table),1):.1%}) across "
        f"**{table['country'].nunique()}** countries · companies: **{len(companies):,}**",
        f"- partner-work pairs without a ROR, excluded from the table: **{no_ror:,}**",
        f"- sectors: " + " · ".join(f"{k} {v:,}" for k, v in table["sector"].value_counts().head(8).items()),
        "",
        "| Partner | Country | Sector | Co-works | mean FWCI_FR | Lorraine labs |",
        "|---|---|---|---|---|---|",
    ]
    for row in table.head(15).itertuples():
        lines.append(f"| {row.institution_name} | {row.country} | {row.sector} | {row.co_works:,} | "
                     f"{'' if pd.isna(row.FWCI_FR_mean) else f'{row.FWCI_FR_mean:.2f}'} | "
                     f"{row.n_lorraine_labs} |")

    report = ROOT / CONFIG["paths"]["reports"] / "ul_partners.md"
    report.write_text("# Partner institutions\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    Manifest(snapshot).record_step(
        "42_build_partners",
        counts={"partners": len(table), "foreign": len(foreign), "companies": len(companies),
                "pairs_without_ror": int(no_ror)},
        files=[out],
        params={"min_works": args.min_works, "top_n_labs": TOP_N,
                "own_structures_excluded": len(own_ids)},
        notes="Set union over native authorship rows; ROR-identified partners only.",
    )
    append_summary(snapshot, "42_build_partners", lines[:4])
    print("\n".join(lines))
    print(f"\nwrote {out.name} and {report}")


if __name__ == "__main__":
    main()
