"""44e_build_detail_partners.py -- thematic_detail_partners.parquet, page 4 sections 6-7 (MISSING in v2).

One row per (level, entity) for domain/field/subfield (required; topic optional and not built here,
per the contract's Open risk 4 -- a top-20 partner list for a handful of topic-level works is noise
and page 4 already renders `st.info` on a missing row).

Three 	':'/'|'-blob columns, all built from `corpus_authorships` restricted to this level's works and
to non-UL institutions with a ROR:
  * top_int_partners  (20 items, 9 fields: id:name:country:type:copubs:share_ul:share_int:share_partner:fwci)
  * top_fr_partners   (20 items, 8 fields: id:name:type:copubs:share_ul:share_int:share_partner:fwci)
  * reciprocity_partners (50 items, 10 fields: ...:share_partner:partner_total:fwci)

Field semantics (contract):
  share_ul      = copubs / this level's pubs_total
  share_int     = copubs / ul_partners.co_works        (partner's total co-works with ALL of UL)
  share_partner = copubs / the PARTNER's OWN output at this level  (needs ul_partners_base)
  partner_total = the denominator itself (reciprocity only)

DEGRADATION PATH (contract, Open risk 1): if `ul_partners_base.parquet` is absent, or a specific
partner is not in it (only the partners referenced by a required-level top list were pulled, per
D58's cost-consciousness), `share_partner` / `partner_total` are emitted as the literal empty string
"" -- never 0 for an unknown denominator (D53) -- so page 4's `safe_float()` yields NaN and the
affected cells render "-".

Usage: python pipeline/44e_build_detail_partners.py [--snapshot 2026-08-11]
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
TOP_INT, TOP_FR, TOP_RECIPROCITY = 20, 20, 50


def sanitize(value) -> str:
    return str(value).replace(":", " ").replace("|", " ").strip()


class PartnerBase:
    """Wraps ul_partners_base.parquet, if present, to answer 'partner's own output at level X'."""

    def __init__(self, base: pd.DataFrame | None, all_topics: pd.DataFrame) -> None:
        self.base = base.set_index("Partner ID") if base is not None else None
        at = all_topics.assign(
            domain_id=all_topics["domain_id"].astype(str), field_id=all_topics["field_id"].astype(str).astype(int),
            subfield_id=all_topics["subfield_id"].astype(str).astype(int),
        )
        self.domain_ids = sorted(at["domain_id"].astype(int).unique())
        self.field_ids = sorted(at["field_id"].unique())
        self.field_of_subfield = at.drop_duplicates("subfield_id").set_index("subfield_id")["field_id"].to_dict()
        self.subfields_by_field = {
            f: sorted(at.loc[at["field_id"] == f, "subfield_id"].unique()) for f in self.field_ids
        }
        self.field_name = at.drop_duplicates("field_id").set_index("field_id")["field_name"].to_dict()

    def partner_total(self, partner_id: str, level: str, entity_id: str) -> int | None:
        if self.base is None or partner_id not in self.base.index:
            return None
        row = self.base.loc[partner_id]
        if level == "domain":
            parts = str(row["Pubs breakdown per domain (partner total)"] or "").split(" | ")
            idx_list = self.domain_ids
        elif level == "field":
            parts = str(row["Pubs breakdown per field (partner total)"] or "").split(" | ")
            idx_list = self.field_ids
        else:  # subfield
            field_id = self.field_of_subfield.get(int(entity_id))
            if field_id is None:
                return None
            col = f'Pubs per subfield within "{self.field_name[field_id]}" (id: {field_id}) (partner total)'
            if col not in row.index:
                return None
            parts = str(row[col] or "").split(" | ")
            idx_list = self.subfields_by_field[field_id]
        target = int(entity_id) if level != "domain" else int(entity_id)
        try:
            pos = idx_list.index(target)
            return int(parts[pos])
        except (ValueError, IndexError):
            return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    works = pd.read_parquet(tables / "works_master.parquet")
    authorships = pd.read_parquet(tables / "corpus_authorships.parquet")
    descendants = pd.read_parquet(tables / "ul_descendants.parquet")
    ul_partners = pd.read_parquet(tables / "ul_partners.parquet")
    all_topics = pd.read_parquet(tables / "all_topics.parquet")
    base_path = tables / "ul_partners_base.parquet"
    base = pd.read_parquet(base_path) if base_path.exists() else None
    pb = PartnerBase(base, all_topics)
    print(f"snapshot {snapshot.name}: {len(works):,} works · ul_partners_base "
          f"{'present (' + str(len(base)) + ' partners)' if base is not None else 'ABSENT (degradation path active)'}")

    own_ids = set(descendants["openalex_id"]) | {CONFIG["perimeter"]["ul_openalex_id"]}
    own_rors = {r for r in descendants["ror"].dropna()} | {CONFIG["perimeter"]["ul_ror"]}
    partner_meta = ul_partners.set_index("institution_id")

    inst = authorships.dropna(subset=["institution_id", "institution_ror"])[
        ["work_id", "institution_id", "institution_ror", "institution_country"]
    ].drop_duplicates(["work_id", "institution_id"])
    inst = inst[~inst["institution_id"].isin(own_ids) & ~inst["institution_ror"].isin(own_rors)]

    meta_cols = works.set_index("work_id")[["publication_year", "FWCI_FR", "indicator_status"]]
    inst = inst.join(meta_cols, on="work_id")
    fwci_computed = inst[inst["indicator_status"] == "computed"]

    degraded_count = 0
    capped_count = 0
    rows = []
    for level, id_col in LEVELS:
        scoped_works = works.dropna(subset=[id_col])
        level_totals = scoped_works.groupby(id_col, observed=True).size()
        scoped_ids = set(scoped_works["work_id"])
        level_inst = inst[inst["work_id"].isin(scoped_ids)]
        work_to_entity = scoped_works.set_index("work_id")[id_col].to_dict()
        level_inst = level_inst.assign(_entity=level_inst["work_id"].map(work_to_entity))

        for entity_id, block in level_inst.groupby("_entity", observed=True):
            pubs_total = int(level_totals[entity_id])

            def top_items(frame: pd.DataFrame, n: int, include_country: bool, reciprocity: bool):
                nonlocal degraded_count, capped_count
                counts = frame.groupby("institution_id").size().sort_values(ascending=False).head(n)
                parts = []
                for inst_id, copubs in counts.items():
                    if inst_id not in partner_meta.index:
                        continue
                    meta = partner_meta.loc[inst_id]
                    work_subset = frame.loc[frame["institution_id"] == inst_id, "work_id"]
                    fwci_vals = fwci_computed.loc[fwci_computed["work_id"].isin(set(work_subset)), "FWCI_FR"].dropna()
                    fwci = f"{fwci_vals.mean():.4f}" if len(fwci_vals) else ""
                    co_works = meta["co_works"] if pd.notna(meta["co_works"]) and meta["co_works"] else 0
                    share_ul = copubs / pubs_total if pubs_total else 0.0
                    share_int = copubs / co_works if co_works else 0.0
                    p_total = pb.partner_total(inst_id, level, str(entity_id))
                    if not p_total:
                        # None (partner not pulled) OR 0 (copubs >= 1 makes a 0 denominator a
                        # contradiction: snapshot-vs-live drift) -> degrade, never a false 0 (D53,
                        # pass-4 challenge memo #10).
                        degraded_count += 1
                        share_partner_s, p_total_s = "", ""
                    else:
                        share = copubs / p_total
                        if share > 1.0:
                            # snapshot numerator vs live denominator drift (retype/retraction/merge)
                            capped_count += 1
                            share = 1.0
                        share_partner_s = f"{share:.4f}"
                        p_total_s = str(p_total)
                    fields = [inst_id, sanitize(meta["institution_name"])]
                    if include_country:
                        fields.append(sanitize(meta["country"]) if pd.notna(meta["country"]) else "")
                    fields += [sanitize(meta["sector"]) if pd.notna(meta["sector"]) else "",
                               str(int(copubs)), f"{share_ul:.4f}", f"{share_int:.4f}", share_partner_s]
                    if reciprocity:
                        fields.append(p_total_s)
                    fields.append(fwci)
                    parts.append(":".join(fields))
                return "|".join(parts)

            int_frame = block[block["institution_country"] != "FR"]
            fr_frame = block[block["institution_country"] == "FR"]
            rows.append({
                "level": level, "id": str(entity_id),
                "top_int_partners": top_items(int_frame, TOP_INT, include_country=True, reciprocity=False),
                "top_fr_partners": top_items(fr_frame, TOP_FR, include_country=False, reciprocity=False),
                "reciprocity_partners": top_items(block, TOP_RECIPROCITY, include_country=True, reciprocity=True),
            })

    table = pd.DataFrame(rows)
    out = tables / "thematic_detail_partners.parquet"
    table.to_parquet(out, index=False, compression=CONFIG["storage"]["compression"])

    lines = [
        f"- partner detail rows: **{len(table):,}** (domain {int((table['level']=='domain').sum())}, "
        f"field {int((table['level']=='field').sum())}, subfield {int((table['level']=='subfield').sum())})",
        f"- ul_partners_base: {'present' if base is not None else 'ABSENT'} -> "
        f"**{degraded_count:,}** partner-level cells degraded to '' (share_partner/partner_total unknown)",
        f"- share_partner capped at 1.0 for **{capped_count:,}** cells (snapshot-vs-live drift; pass-4 memo #10)",
    ]
    report = ROOT / CONFIG["paths"]["reports"] / "thematic_detail_partners.md"
    report.write_text("# thematic_detail_partners (page 4)\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    Manifest(snapshot).record_step(
        "44e_build_detail_partners",
        counts={"rows": len(table), "degraded_cells": degraded_count, "capped_cells": capped_count},
        files=[out],
        params={"top_int": TOP_INT, "top_fr": TOP_FR, "top_reciprocity": TOP_RECIPROCITY,
                "ul_partners_base_present": base is not None},
        notes="New builder (MISSING in v2). Degradation path per contract Open risk 1: share_partner/"
              "partner_total = '' (never 0) when ul_partners_base lacks that partner.",
    )
    append_summary(snapshot, "44e_build_detail_partners", lines)
    print("\n".join(lines))
    print(f"\nwrote {out.name}")


if __name__ == "__main__":
    main()
