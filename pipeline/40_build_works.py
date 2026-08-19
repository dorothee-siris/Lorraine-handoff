"""40_build_works.py — the master works table every view is built from.

Joins, for each corpus work: the abstract and its provenance (20/20b), the French-baselined
indicators (31), the ISITE flag (D21), lab and pôle attribution from the client's list, the OpenAlex
taxonomy that replaces the topic model (D9), and the HAL identifiers (20b).

Two things this step deliberately does NOT do:
  * it does not reintroduce v1's `[n]`-indexed multi-value strings — lab and department lists are
    built as set unions from the native `corpus_authorships` long table, which is immune to the
    positional-shift defect that hit 51.4% of v1's works;
  * it does not merge the OpenAlex I-SITE award into `In_ISITE` (D21) — the hand-built DOI list stays
    canonical and the award is carried beside it as a cross-check.

Usage: python pipeline/40_build_works.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)
NO_LAB = "NO LAB"


def normalise_doi(doi: str | None) -> str | None:
    if not isinstance(doi, str):
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip().lower()) or None


def load_lab_list() -> pd.DataFrame:
    """The client's subperimeter file, with the D20 id repairs applied. Never edited in place."""
    labs = pd.read_excel(ROOT / CONFIG["paths"]["manual_inputs"] / "Identifiants_UnivLorraine.xlsx")
    repairs = CONFIG["perimeter"].get("openalex_id_repairs") or {}
    labs["OpenAlex"] = labs["OpenAlex"].map(lambda x: repairs.get(str(x).strip(), x) if pd.notna(x) else x)
    labs["ROR"] = labs["ROR"].map(lambda x: str(x).strip().lower() if pd.notna(x) else x)
    return labs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    corpus = pd.read_parquet(tables / "corpus_abstracts.parquet")
    authorships = pd.read_parquet(tables / "corpus_authorships.parquet")
    topics = pd.read_parquet(tables / "corpus_topics.parquet")
    print(f"snapshot {snapshot.name}: corpus {len(corpus):,} · authorships {len(authorships):,}")

    works = corpus.copy()

    # --- indicators from 31 (optional: allows 40 to run before the France pull finishes) ---
    metrics_path = tables / "corpus_metrics.parquet"
    if metrics_path.exists():
        metrics = pd.read_parquet(metrics_path)[
            ["work_id", "FWCI_FR", "PPtop10_FR", "PPtop1_FR", "indicator_status", "n"]
        ].rename(columns={"n": "stratum_n"})
        works = works.merge(metrics, on="work_id", how="left")
        print(f"  indicators joined: {works['indicator_status'].value_counts().to_dict()}")
    else:
        print("  ! corpus_metrics.parquet absent — run 31_build_baseline.py; "
              "FWCI_FR / PPtop columns will be missing")

    # --- ISITE flag (D21): hand list canonical, award as a separate cross-check column ---
    isite = pd.read_excel(ROOT / CONFIG["paths"]["manual_inputs"] / CONFIG["isite"]["doi_list_file"])
    isite_dois = {normalise_doi(x) for x in isite["doi"]} - {None}
    expected = CONFIG["isite"]["expected_unique_dois"]
    assert len(isite_dois) == expected, f"ISITE list has {len(isite_dois)} unique DOIs, expected {expected}"
    works[CONFIG["isite"]["flag_column"]] = works["doi"].isin(isite_dois)
    works[CONFIG["isite"]["award_flag_column"]] = works["has_isite_award"]
    both = int((works["In_ISITE"] & works["has_isite_award"]).sum())
    award_only = int((~works["In_ISITE"] & works["has_isite_award"]).sum())
    print(f"  In_ISITE (hand list): {int(works['In_ISITE'].sum()):,} · award flag: "
          f"{int(works['has_isite_award'].sum()):,} · both: {both:,} · award-only: {award_only:,} "
          f"(reported, NOT merged — D21)")

    # --- lab and pôle attribution, as set unions over the native authorship rows ---
    labs = load_lab_list()
    id_to_lab = {str(r.OpenAlex).strip(): r.Laboratoire for r in labs.itertuples() if pd.notna(r.OpenAlex)}
    ror_to_lab = {str(r.ROR).strip(): r.Laboratoire for r in labs.itertuples() if pd.notna(r.ROR)}
    lab_to_pole = {r.Laboratoire: r.Pôle for r in labs.itertuples()}

    inst = authorships[["work_id", "institution_id", "institution_ror"]].dropna(
        subset=["institution_id", "institution_ror"], how="all"
    )
    inst["lab"] = inst["institution_id"].map(id_to_lab)
    inst["lab"] = inst["lab"].fillna(inst["institution_ror"].map(ror_to_lab))
    hits = inst[inst["lab"].notna()]
    per_work = hits.groupby("work_id")["lab"].apply(lambda s: sorted(set(s)))
    works["labs"] = works["work_id"].map(per_work).apply(lambda v: v if isinstance(v, list) else [])
    works["poles"] = works["labs"].apply(
        lambda names: sorted({lab_to_pole.get(n) for n in names if pd.notna(lab_to_pole.get(n))})
    )
    works["n_labs"] = works["labs"].apply(len)
    works["Labs"] = works["labs"].apply(lambda v: " | ".join(v) if v else NO_LAB)
    works["Poles"] = works["poles"].apply(lambda v: " | ".join(v) if v else NO_LAB)
    unattributed = int((works["n_labs"] == 0).sum())
    print(f"  lab attribution: {len(works) - unattributed:,} works mapped to >=1 lab · "
          f"{unattributed:,} in the '{NO_LAB}' bucket ({unattributed/len(works):.1%})")

    # every lab in the client's list must appear, or be explicitly reported as zero (§6 test)
    seen = {name for names in works["labs"] for name in names}
    missing_labs = [r.Laboratoire for r in labs.itertuples()
                    if pd.notna(r.OpenAlex) and r.Laboratoire not in seen]
    if missing_labs:
        print(f"  ! {len(missing_labs)} labs from the list have ZERO works: {missing_labs}")

    # --- OpenAlex taxonomy names, replacing the topic model (D9) ---
    primary = topics[topics["is_primary"]].drop_duplicates("work_id")[
        ["work_id", "topic_name", "subfield_name", "field_name", "domain_name"]
    ].rename(columns={"topic_name": "primary_topic_name", "subfield_name": "primary_subfield_name",
                      "field_name": "primary_field_name", "domain_name": "primary_domain_name"})
    works = works.merge(primary, on="work_id", how="left")
    print(f"  taxonomy: {works['primary_subfield_name'].notna().sum():,} works carry a primary subfield "
          f"({works['primary_subfield_name'].isna().sum():,} untopiced)")

    # --- HAL identifiers from 20b, for the author stage ---
    # Post-D41, hal_work_links.parquet no longer carries hal_authors_idhal / hal_authors_orcid
    # directly -- it carries the aligned `hal_author_idhal_pairs` ("Name_FacetSep_idhal", "||"-
    # joined) plus work-level counts. ul_pubs (docs/data_contract.yaml) still declares both
    # hal_authors_idhal and hal_authors_orcid as nullable string columns, so both are reconstructed
    # here rather than dropped:
    #   * hal_authors_idhal is recovered exactly: the pairs field preserves the same per-author
    #     order HAL's (sparse) authIdHal_s array always had, so extracting the idhal half and
    #     dropping empties reproduces the pre-D41 column byte-for-byte (checked against the
    #     canonical 2026-08-11 snapshot: identical 28-element ";"-joined list, same order, for
    #     W2983606184).
    #   * hal_authors_orcid cannot be recovered at all: HAL publishes no aligned name<->ORCID field
    #     (see 20b), so the D41 rewrite dropped the raw sparse authORCIDIdExt_s array from
    #     hal_work_links and kept only hal_n_authors_with_orcid (a work-level count, not
    #     attributable to an author). Faking a per-author list from that would repeat the exact
    #     positional-misalignment defect D41 removed, so this column is carried through all-null.
    links_path = tables / "hal_work_links.parquet"
    if links_path.exists():
        links = pd.read_parquet(links_path)[["work_id", "hal_id", "hal_author_idhal_pairs"]].copy()

        def idhal_list(pairs: str | None) -> str | None:
            if not isinstance(pairs, str) or not pairs:
                return None
            ids = [p.split("_FacetSep_", 1)[1] for p in pairs.split("||") if "_FacetSep_" in p]
            ids = [i for i in ids if i]
            return ";".join(ids) if ids else None

        links["hal_authors_idhal"] = links["hal_author_idhal_pairs"].map(idhal_list)
        links["hal_authors_orcid"] = None
        links = links.drop(columns=["hal_author_idhal_pairs"])
        works = works.merge(links, on="work_id", how="left")
        print(f"  HAL ids joined on {works['hal_id'].notna().sum():,} works")

    # --- collaboration flags (v1 had Is_international / Is_company) ---
    countries = authorships.groupby("work_id")["institution_country"].apply(lambda s: set(s.dropna()))
    works["countries"] = works["work_id"].map(countries).apply(lambda v: v if isinstance(v, set) else set())
    works["n_countries"] = works["countries"].apply(len)
    works["Is_international"] = works["countries"].apply(lambda c: len(c - {"FR"}) > 0)
    company = authorships[authorships["institution_type"] == "company"].groupby("work_id").size()
    works["Is_company"] = works["work_id"].isin(company.index)
    works = works.drop(columns=["countries", "labs", "poles"])

    out = tables / "works_master.parquet"
    works.to_parquet(out, index=False, compression=CONFIG["storage"]["compression"])

    lines = [
        f"- master table: **{len(works):,}** works x {works.shape[1]} columns",
        f"- `In_ISITE` (canonical hand list): **{int(works['In_ISITE'].sum()):,}** "
        f"(v1: {CONFIG['baselines_v1']['isite_flagged_works']:,})",
        f"- OpenAlex I-SITE award flag: {int(works['has_isite_award'].sum()):,}, of which "
        f"**{award_only:,} are not in the hand list** (reported per D21, never merged)",
        f"- lab attribution: {len(works) - unattributed:,} works to >=1 lab, "
        f"{unattributed:,} in `{NO_LAB}` ({unattributed/len(works):.1%})",
        f"- labs from the client list with zero works: {len(missing_labs)}"
        + (f" — {', '.join(map(str, missing_labs))}" if missing_labs else ""),
        f"- international collaborations: {int(works['Is_international'].sum()):,} "
        f"({works['Is_international'].mean():.1%}) · with a company: {int(works['Is_company'].sum()):,}",
        f"- abstract coverage: {works['abstract'].notna().mean():.1%}",
    ]
    if "indicator_status" in works:
        lines.append(f"- indicators computed on {int((works['indicator_status'] == 'computed').sum()):,} "
                     f"works; median FWCI_FR {works['FWCI_FR'].median():.3f}")

    # structural invariants (§10 Class 1)
    assert works["work_id"].is_unique, "duplicate work ids in the master table"
    assert works["publication_year"].between(CONFIG["window"]["year_from"],
                                             CONFIG["window"]["year_to"]).all(), "year outside window"
    assert works.loc[works["In_ISITE"], "doi"].notna().all(), "In_ISITE set on a work without a DOI"

    report = ROOT / CONFIG["paths"]["reports"] / "works_master.md"
    report.write_text("# Master works table\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    Manifest(snapshot).record_step(
        "40_build_works",
        counts={"works": len(works), "columns": works.shape[1],
                "in_isite": int(works["In_ISITE"].sum()), "no_lab": unattributed},
        files=[out],
        params={"isite_dois": len(isite_dois), "labs_with_zero_works": missing_labs,
                "merge_award_into_flag": CONFIG["isite"]["merge_award_into_flag"]},
        notes="Set-union lab attribution over native authorship rows; no [n] strings anywhere.",
    )
    append_summary(snapshot, "40_build_works", lines)
    print("\n".join(lines))
    print(f"\nwrote {out.name} and {report}")


if __name__ == "__main__":
    main()
