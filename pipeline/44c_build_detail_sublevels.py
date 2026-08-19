"""44c_build_detail_sublevels.py -- thematic_detail_sublevels.parquet, page 4 (MISSING in v2).

One row per (parent, child) EDGE of the taxonomy, restricted to parents that have works. Required
parent levels are domain/field/subfield (child levels field/subfield/topic respectively); topic-level
parents are never required (a topic has no taxonomy children) and are not produced here.

page 4 reads `pubs_pct_of_parent` and `pct_isite` with NO null guard before feeding a ProgressColumn,
so both are forced to 0.0 rather than null when a block is empty (which cannot actually happen here,
since every child row is built FROM at least one work, but the invariant is asserted anyway).

Usage: python pipeline/44c_build_detail_sublevels.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402
import lib46_momentum as mom  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)
SDG_VARIANT_MAP = {"b_siris": "B_siris", "c_openalex": "C_openalex", "off": None}
EDGES = [
    ("domain", "primary_domain_id", "field", "primary_field_id", "primary_field_name"),
    ("field", "primary_field_id", "subfield", "primary_subfield_id", "primary_subfield_name"),
    ("subfield", "primary_subfield_id", "topic", "primary_topic_id", "primary_topic_name"),
]


def cagr(first: float, last: float, n_periods: int) -> float | None:
    if not first or first <= 0 or n_periods <= 0:
        return None
    return round((last / first) ** (1 / n_periods) - 1, 4)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    works = pd.read_parquet(tables / "works_master.parquet")
    app_cfg = CONFIG.get("app") or {}
    sdg_col = SDG_VARIANT_MAP.get(app_cfg.get("sdg_variant", "b_siris"), "B_siris")
    sdg_flag = pd.Series(dtype=bool)
    if sdg_col:
        sdg = pd.read_parquet(tables / "sdg_three_way.parquet")
        sdg_flag = sdg.set_index("work_id")[sdg_col].notna()

    years = list(range(CONFIG["window"]["year_from"], CONFIG["window"]["year_to"] + 1))
    print(f"snapshot {snapshot.name}: {len(works):,} works")

    rows = []
    for parent_level, parent_col, child_level, child_col, child_name_col in EDGES:
        scoped = works.dropna(subset=[parent_col, child_col]).copy()
        parent_totals = scoped.groupby(parent_col, observed=True).size()
        for (parent_id, child_id), block in scoped.groupby([parent_col, child_col], observed=True):
            computed = block[block["indicator_status"] == "computed"]
            year_counts = block["publication_year"].value_counts()
            first_val, last_val = int(year_counts.get(years[0], 0)), int(year_counts.get(years[-1], 0))
            pct_sdg = float(sdg_flag.reindex(block["work_id"]).fillna(False).mean()) if len(sdg_flag) else None
            mom_c1 = sum(int(year_counts.get(y, 0)) for y in mom.W1_YEARS)
            mom_c2 = sum(int(year_counts.get(y, 0)) for y in mom.W2_YEARS)
            rows.append({
                "parent_level": parent_level, "parent_id": str(parent_id),
                "child_level": child_level, "child_id": str(child_id),
                "child_name": block[child_name_col].iloc[0],
                "pubs_total": len(block),
                "pubs_pct_of_parent": round(len(block) / int(parent_totals[parent_id]), 6),
                "pubs_per_year": "|".join(f"{y}:{int(year_counts.get(y, 0))}" for y in years),
                "pct_isite": round(float(block["In_ISITE"].mean()), 4),
                "pct_top10": round(float(computed["PPtop10_FR"].astype(float).mean()), 4) if len(computed) else None,
                "pct_top1": round(float(computed["PPtop1_FR"].astype(float).mean()), 4) if len(computed) else None,
                "pct_international": round(float(block["Is_international"].mean()), 4),
                "pct_company": round(float(block["Is_company"].mean()), 4),
                "pct_sdg": round(pct_sdg, 4) if pct_sdg is not None else None,
                "fwci_median": round(float(computed["FWCI_FR"].median()), 4) if len(computed) else None,
                "fwci_mean": round(float(computed["FWCI_FR"].mean()), 4) if len(computed) else None,
                "cagr_2019_2023": cagr(first_val, last_val, len(years) - 1),
                "_mom_c1": mom_c1, "_mom_c2": mom_c2,
            })

    table = pd.DataFrame(rows)

    # pass 6 (#18): same frozen momentum family as 44_build_thematic.py's thematic_overview, same
    # field-level reference recomputed here (deterministic, no randomness -- cheap to recompute in
    # this separate pipeline step rather than persist a cross-script scalar).
    ref = mom.corpus_level_reference(works, "primary_field_id")
    print(f"  momentum reference (field-level, {mom.W1_YEARS} vs {mom.W2_YEARS}): "
          f"d1={ref['d1']:,} d2={ref['d2']:,} med={ref['med']:.4f} eligible_n={ref['eligible_n']}")
    rr, pv, elig = mom.cell_delta(table["_mom_c1"], table["_mom_c2"], ref["d1"], ref["d2"], ref["med"])
    table["mom_class"] = mom.classify(rr, pv)
    table["mom_p_value"] = pv
    table["mom_w1_share"] = (table["_mom_c1"] / ref["d1"]) if ref["d1"] else float("nan")
    table["mom_w2_share"] = (table["_mom_c2"] / ref["d2"]) if ref["d2"] else float("nan")
    table["mom_eligible_flag"] = elig.astype(bool)
    table = table.drop(columns=["_mom_c1", "_mom_c2"])
    assert not table[["pubs_pct_of_parent", "pct_isite"]].isna().any().any(), (
        "pubs_pct_of_parent / pct_isite must never be null — page 4 feeds them to a ProgressColumn "
        "with no null guard"
    )
    key_dupes = table.duplicated(["parent_level", "parent_id", "child_id"]).sum()
    assert key_dupes == 0, f"{key_dupes} duplicate (parent_level, parent_id, child_id) keys"

    out = tables / "thematic_detail_sublevels.parquet"
    table.to_parquet(out, index=False, compression=CONFIG["storage"]["compression"])

    lines = [
        f"- sublevel edges: **{len(table):,}** (domain->field {int((table['parent_level']=='domain').sum())}, "
        f"field->subfield {int((table['parent_level']=='field').sum())}, "
        f"subfield->topic {int((table['parent_level']=='subfield').sum())})",
        f"- pubs_pct_of_parent / pct_isite verified non-null on every row (page 4 has no null guard)",
    ]
    report = ROOT / CONFIG["paths"]["reports"] / "thematic_detail_sublevels.md"
    report.write_text("# thematic_detail_sublevels (page 4)\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    Manifest(snapshot).record_step(
        "44c_build_detail_sublevels",
        counts={"rows": len(table)},
        files=[out],
        params={"required_parent_levels": ["domain", "field", "subfield"]},
        notes="New builder (MISSING in v2 snapshot). One row per taxonomy (parent, child) edge.",
    )
    append_summary(snapshot, "44c_build_detail_sublevels", lines)
    print("\n".join(lines))
    print(f"\nwrote {out.name}")


if __name__ == "__main__":
    main()
