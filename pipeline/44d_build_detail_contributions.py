"""44d_build_detail_contributions.py -- thematic_detail_contributions.parquet, page 4 (MISSING in v2).

One row per (level, entity) for domain/field/subfield (required) plus topic (optional -- skipped
here: a top-20 lab list for a handful of topic-level works is noise, and page 4 already degrades to
an empty state when the row is absent, per the contract's Open risk 4).

Two blob columns, discovered by SUBSTRING on page 4 (`find_column(row, "department_breakdown")`),
so v1's format-in-the-name suffixes are dropped -- a rename, not a drop:
  * `department_breakdown` -- v1's ten DEPARTMENT names are, verified, the same value set as v2's
    ten UL POLES (A2F, AM2I, ...). Built from `works_master.Poles`.
  * `top_labs` -- built from `works_master.Labs` joined to `ul_labs` for (ror, type). BLOB HAZARD:
    8+ of the 21 D56 hors-liste structures contain ':' in their display name; every name entering
    this blob is sanitised per policy.blob_sanitise before joining.

Usage: python pipeline/44d_build_detail_contributions.py [--snapshot 2026-08-11]
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
LEVELS = [("domain", "primary_domain_id"), ("field", "primary_field_id"), ("subfield", "primary_subfield_id")]
NO_LAB = "NO LAB"
TOP_N_LABS = 10


def sanitize(value) -> str:
    return str(value).replace(":", " ").replace("|", " ").strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    works = pd.read_parquet(tables / "works_master.parquet")
    # ul_labs_wide.parquet, NOT ul_labs.parquet: the wide (D56+D60) shape carries "Structure name" /
    # "ROR" / "Structure type"; the narrow ul_labs.parquet (kept for tests/test_invariants.py) does
    # not. See 43_build_labs.py's module docstring for why the two shapes live in separate files.
    ul_labs = pd.read_parquet(tables / "ul_labs_wide.parquet")
    lab_meta = ul_labs.set_index("Structure name")[["ROR", "Structure type"]]
    print(f"snapshot {snapshot.name}: {len(works):,} works")

    rows = []
    for level, id_col in LEVELS:
        scoped = works.dropna(subset=[id_col])
        for entity_id, block in scoped.groupby(id_col, observed=True):
            n_total = len(block)
            block_isite = block[block["In_ISITE"]]

            dept = block.assign(_p=block["Poles"].str.split(" | ", regex=False)).explode("_p")
            dept = dept[dept["_p"] != NO_LAB]
            dept_counts = dept["_p"].value_counts()
            dept_blob = "|".join(
                f"{sanitize(p)}:{int(n)}:{n / n_total:.4f}" for p, n in dept_counts.items()
            )

            # OVERLAY_MATRIX EXTEND (pass 5, S3, additive): same-row ISITE twin of
            # department_breakdown -- per department, the count/share of ITS OWN bar (not of
            # n_total) that is In_ISITE, same darker-segment convention as ptn_summary's
            # isite_co_works/isite_share and the geo_countries/ptn_fields extensions in
            # pipeline/46_build_partner_views.py. Zero recomputation at render time.
            dept_isite = block_isite.assign(_p=block_isite["Poles"].str.split(" | ", regex=False)).explode("_p")
            dept_isite = dept_isite[dept_isite["_p"] != NO_LAB]
            dept_isite_counts = dept_isite["_p"].value_counts()
            dept_isite_blob = "|".join(
                f"{sanitize(p)}:{int(dept_isite_counts.get(p, 0))}:"
                f"{(dept_isite_counts.get(p, 0) / n):.4f}"
                for p, n in dept_counts.items()
            )

            labs = block.assign(_l=block["Labs"].str.split(" | ", regex=False)).explode("_l")
            labs = labs[labs["_l"] != NO_LAB]
            lab_counts = labs["_l"].value_counts().head(TOP_N_LABS)
            labs_isite = block_isite.assign(_l=block_isite["Labs"].str.split(" | ", regex=False)).explode("_l")
            labs_isite = labs_isite[labs_isite["_l"] != NO_LAB]
            lab_isite_counts = labs_isite["_l"].value_counts()
            lab_parts = []
            lab_isite_parts = []
            for lab_name, n in lab_counts.items():
                meta = lab_meta.loc[lab_name] if lab_name in lab_meta.index else None
                ror = sanitize(meta["ROR"]) if meta is not None and pd.notna(meta["ROR"]) else ""
                ltype = sanitize(meta["Structure type"]) if meta is not None and pd.notna(meta["Structure type"]) else "lab"
                lab_parts.append(f"{ror}:{sanitize(lab_name)}:{ltype}:{int(n)}:{n / n_total:.4f}")
                n_isite = int(lab_isite_counts.get(lab_name, 0))
                lab_isite_parts.append(f"{ror}:{sanitize(lab_name)}:{n_isite}:{(n_isite / n):.4f}")

            rows.append({
                "level": level, "id": str(entity_id),
                "department_breakdown": dept_blob,
                "department_breakdown_isite": dept_isite_blob,
                "top_labs": "|".join(lab_parts),
                "top_labs_isite": "|".join(lab_isite_parts),
            })

    table = pd.DataFrame(rows)
    # Class-1 blob_separator_safety check: no sanitised field should contain ':' or '|' beyond the
    # structural separators -- verify by re-parsing and checking exactly 5 fields per '|'-item.
    bad = 0
    for blob in table["top_labs"]:
        if not blob:
            continue
        for item in blob.split("|"):
            if item.count(":") != 4:
                bad += 1
    assert bad == 0, f"{bad} top_labs items do not have exactly 5 ':'-fields — sanitisation missed a name"

    # Same check, additive twins: top_labs_isite is "ror:name:isite_count:isite_share" (3 ':'-fields,
    # not 5 -- ltype is not repeated) and department_breakdown_isite is "dept:isite_count:isite_share"
    # (2 ':'-fields), same sanitize() guard against the parent blobs.
    bad_isite_labs = sum(
        1 for blob in table["top_labs_isite"] if blob for item in blob.split("|") if item.count(":") != 3
    )
    assert bad_isite_labs == 0, (
        f"{bad_isite_labs} top_labs_isite items do not have exactly 4 ':'-fields — sanitisation missed a name"
    )
    bad_isite_dept = sum(
        1 for blob in table["department_breakdown_isite"] if blob for item in blob.split("|") if item.count(":") != 2
    )
    assert bad_isite_dept == 0, (
        f"{bad_isite_dept} department_breakdown_isite items do not have exactly 3 ':'-fields"
    )
    # Consistency: every isite count is <= the parent (department/lab)'s own total count -- an
    # ISITE-restricted subset can never exceed its own superset.
    def _parse(blob: str) -> list[tuple]:
        return [tuple(item.split(":")) for item in blob.split("|") if item] if blob else []

    mismatches = 0
    for full_blob, isite_blob in zip(table["top_labs"], table["top_labs_isite"]):
        full = {p[1]: int(p[3]) for p in _parse(full_blob)}
        isite = {p[1]: int(p[2]) for p in _parse(isite_blob)}
        for name, n_isite in isite.items():
            if n_isite > full.get(name, 0):
                mismatches += 1
    assert mismatches == 0, f"{mismatches} top_labs_isite count(s) exceed their parent top_labs count"

    out = tables / "thematic_detail_contributions.parquet"
    table.to_parquet(out, index=False, compression=CONFIG["storage"]["compression"])

    lines = [
        f"- contribution rows: **{len(table):,}** (domain {int((table['level']=='domain').sum())}, "
        f"field {int((table['level']=='field').sum())}, subfield {int((table['level']=='subfield').sum())})",
        f"- blob_separator_safety: 0 malformed top_labs items across {len(table):,} rows",
        f"- OVERLAY_MATRIX EXTEND (pass 5, S3): department_breakdown_isite / top_labs_isite added "
        f"(additive, same-row ISITE twins, docs/OVERLAY_MATRIX.md) -- 0 malformed items, 0 "
        f"isite-count-exceeds-parent mismatches",
    ]
    report = ROOT / CONFIG["paths"]["reports"] / "thematic_detail_contributions.md"
    report.write_text("# thematic_detail_contributions (page 4)\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    Manifest(snapshot).record_step(
        "44d_build_detail_contributions",
        counts={"rows": len(table)},
        files=[out],
        params={"top_n_labs": TOP_N_LABS, "blob_sanitised": True},
        notes="New builder (MISSING in v2). department_breakdown built from Poles, top_labs from Labs; "
              "clean column names (page 4 finds them by substring, not literal name). Pass 5 (S3): "
              "+department_breakdown_isite/+top_labs_isite, additive ISITE overlay twins.",
    )
    append_summary(snapshot, "44d_build_detail_contributions", lines)
    print("\n".join(lines))
    print(f"\nwrote {out.name}")


if __name__ == "__main__":
    main()
