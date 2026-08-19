"""44f_build_detail_authors.py -- thematic_detail_authors.parquet, page 4 section 8 (MISSING in v2).

One row per (level, entity) for domain/field/subfield (required; topic optional, not built here).
One blob column, `top_authors`, 20 items of 8 ':'-separated fields:
  id:name:orcid:pubs:pct:fwci:is_lorraine:labs

v1 defects fixed here (contract):
  (a) v1 stripped spaces from names ("LaurentPeyrin-Biroulet") -- v2's `ul_authors.display_name`
      carries real spacing (native OpenAlex display names via corpus_authorships, D34-class
      misalignment never applied), so `add_spaces_to_name()` on page 4 becomes a harmless no-op.
  (b) v1's `orcid` field held '/'-joined multi-ORCID values that could leak a co-author's ORCID onto
      the wrong person. v2 emits ONE ORCID (the author's own from `ul_authors.orcids_joined`, first
      value) or an empty string -- never a joined list.

Ranking scope: authors credited a Lorraine affiliation (any UL descendant, per D20) on works at this
taxonomy level, ranked by DISTINCT work count at that level -- consistent with `45_build_authors.py`'s
own definition of "Lorraine author".

Usage: python pipeline/44f_build_detail_authors.py [--snapshot 2026-08-11]
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
TOP_N = 20
SEP = " | "


def sanitize(value) -> str:
    return str(value).replace(":", " ").replace("|", " ").strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    works = pd.read_parquet(tables / "works_master.parquet")
    authorships = pd.read_parquet(tables / "corpus_authorships.parquet")
    descendants = pd.read_parquet(tables / "ul_descendants.parquet")
    ul_authors = pd.read_parquet(tables / "ul_authors.parquet")
    print(f"snapshot {snapshot.name}: {len(works):,} works")

    own_ids = set(descendants["openalex_id"]) | {CONFIG["perimeter"]["ul_openalex_id"]}
    own_rors = {r for r in descendants["ror"].dropna()} | {CONFIG["perimeter"]["ul_ror"]}

    author_to_person: dict[str, str] = {}
    for r in ul_authors.itertuples():
        for profile in str(r.profiles_joined or "").split(SEP):
            if profile:
                author_to_person[profile] = r.person_id

    own_auth = authorships.dropna(subset=["author_id"])
    own_auth = own_auth[
        own_auth["institution_id"].isin(own_ids) | own_auth["institution_ror"].isin(own_rors)
    ][["work_id", "author_id"]].drop_duplicates()
    own_auth = own_auth.assign(person_id=own_auth["author_id"].map(author_to_person)).dropna(subset=["person_id"])

    meta_cols = works.set_index("work_id")[["FWCI_FR", "indicator_status"]]
    own_auth = own_auth.join(meta_cols, on="work_id")

    people = ul_authors.set_index("person_id")
    known_people = set(ul_authors["person_id"])

    def first_orcid(joined: str | float) -> str:
        parts = [o for o in str(joined or "").split(SEP) if o]
        return parts[0] if parts else ""

    rows = []
    for level, id_col in LEVELS:
        scoped_works = works.dropna(subset=[id_col])
        level_totals = scoped_works.groupby(id_col, observed=True).size()
        work_to_entity = scoped_works.set_index("work_id")[id_col].to_dict()
        level_auth = own_auth.assign(_entity=own_auth["work_id"].map(work_to_entity)).dropna(subset=["_entity"])

        for entity_id, block in level_auth.groupby("_entity", observed=True):
            pubs_total = int(level_totals[entity_id])
            counts = block.groupby("person_id")["work_id"].nunique().sort_values(ascending=False).head(TOP_N)
            computed = block[block["indicator_status"] == "computed"]
            parts = []
            for person_id, n_pubs in counts.items():
                if person_id not in people.index:
                    continue
                person = people.loc[person_id]
                own_ws = set(block.loc[block["person_id"] == person_id, "work_id"])
                fwci_vals = computed.loc[
                    computed["person_id"] == person_id, "FWCI_FR"
                ].dropna() if "person_id" in computed else pd.Series(dtype=float)
                fwci = f"{fwci_vals.mean():.4f}" if len(fwci_vals) else ""
                labs = "/".join(
                    sanitize(l) for l in str(person.get("own_labs_joined") or "").split(SEP) if l
                )
                fields = [
                    person_id, sanitize(person["display_name"]),
                    first_orcid(person.get("orcids_joined")),
                    str(int(n_pubs)), f"{n_pubs / pubs_total:.4f}", fwci,
                    str(person_id in known_people), labs,
                ]
                parts.append(":".join(fields))
            rows.append({"level": level, "id": str(entity_id), "top_authors": "|".join(parts)})

    table = pd.DataFrame(rows)
    out = tables / "thematic_detail_authors.parquet"
    table.to_parquet(out, index=False, compression=CONFIG["storage"]["compression"])

    lines = [
        f"- author detail rows: **{len(table):,}** (domain {int((table['level']=='domain').sum())}, "
        f"field {int((table['level']=='field').sum())}, subfield {int((table['level']=='subfield').sum())})",
        f"- v1 defects fixed: real name spacing (no add_spaces_to_name() needed) and one ORCID per "
        f"author (never a leaked '/'-joined multi-ORCID list)",
    ]
    report = ROOT / CONFIG["paths"]["reports"] / "thematic_detail_authors.md"
    report.write_text("# thematic_detail_authors (page 4)\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    Manifest(snapshot).record_step(
        "44f_build_detail_authors",
        counts={"rows": len(table)},
        files=[out],
        params={"top_n": TOP_N},
        notes="New builder (MISSING in v2). Ranking scope matches 45_build_authors.py's Lorraine-author definition.",
    )
    append_summary(snapshot, "44f_build_detail_authors", lines)
    print("\n".join(lines))
    print(f"\nwrote {out.name}")


if __name__ == "__main__":
    main()
