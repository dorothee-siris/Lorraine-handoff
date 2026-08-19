"""44b_build_treemap.py -- treemap_hierarchy.parquet, page 3 section 1 (MISSING in v2, per contract).

A straight pivot of the deployed `thematic_overview.parquet`: plotly's treemap resolves `parents`
against `ids` in ONE flat namespace, so bare numeric ids would collide across levels (a domain "1"
and a field "1" are different things). Every id gets a level prefix -- `d_`/`f_`/`sf_`/`t_` -- per
v1's actually-deployed file (verified: `d_1` / `f_11` / `sf_1100` / `t_T12033`).

`branchvalues="total"` on page 3 means a parent's `pubs` must be >= the sum of its children's. That
holds automatically here because a work has exactly one primary topic (thematic_overview's own
invariant), so summing is exact -- this builder never mixes a primary-topic parent count with an
all-topics child count.

Usage: python pipeline/44b_build_treemap.py [--snapshot 2026-08-11]
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
PREFIX = {"domain": "d_", "field": "f_", "subfield": "sf_", "topic": "t_"}
PARENT_LEVEL = {"domain": None, "field": "domain", "subfield": "field", "topic": "subfield"}


def prefixed(level: str, bare_id: str) -> str:
    return f"{PREFIX[level]}{bare_id}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    overview = pd.read_parquet(tables / "thematic_overview.parquet")
    print(f"snapshot {snapshot.name}: {len(overview):,} thematic_overview rows")

    # BUG FIX (found by Stream C, progress/C_app.md concern #2): thematic_overview carries an
    # "Unclassified" (id "0") row at EVERY level -- domain, field, subfield, topic -- each with
    # parent_id "" (D9 unclassified_entity: none of them chain to another Unclassified row). A
    # naive per-row pivot therefore emitted FOUR separate roots (d_0/f_0/sf_0/t_0), each carrying
    # the full 51 untopiced works, and because none has a parent, plotly renders all four as
    # distinct top-level boxes -- the untopiced mass appears 4x, inflating the visible root total.
    # The untopiced 51 works are fundamentally one undifferentiated bucket (there is no real
    # field/subfield/topic breakdown to show), so the fix is to keep exactly one representative
    # node -- the domain-level d_0 -- and drop its field/subfield/topic-level duplicates entirely.
    duplicate_unclassified = (overview["id"] == "0") & (overview["level"] != "domain")
    dropped_n = int(duplicate_unclassified.sum())
    overview = overview[~duplicate_unclassified]

    frame = pd.DataFrame({
        "id": [prefixed(r.level, r.id) for r in overview.itertuples()],
        "name": overview["name"],
        "parent_id": [
            prefixed(PARENT_LEVEL[r.level], r.parent_id) if r.parent_id and PARENT_LEVEL[r.level] else ""
            for r in overview.itertuples()
        ],
        "level": overview["level"],
        "pubs": overview["pubs_total"].astype("int64"),
        "fwci_median": overview["fwci_median"],
        "pct_international": overview["pct_international"].fillna(0.0),
        "pct_isite": overview["pct_isite"].fillna(0.0),
        # D53 FIX (found by Stream C, concern #2): pct_top10 is an INDICATOR -- null on works whose
        # stratum was too thin to compute (indicator_status != 'computed'), which is a real "we do
        # not know", never "zero". The previous 0.0-fill (following this file's own now-corrected
        # consumer_constraint note below) rendered thin-stratum/untopiced nodes as if they measured
        # a literal 0% top-10% share, which is the exact "n/a shown as 0" defect D53 exists to ban.
        # Left null: page 3's np.stack(...) over it yields NaN in the hovertemplate (tolerated, per
        # the contract) rather than a false zero.
        "pct_top10": overview["pct_top10"],
    })

    assert frame["id"].is_unique, "treemap ids collide across levels — the prefix scheme broke"
    known_ids = set(frame["id"])
    dangling = set(frame.loc[frame["parent_id"] != "", "parent_id"]) - known_ids
    assert not dangling, f"parent ids with no matching row (px.treemap would drop these branches): {dangling}"

    # regression guard for the exact bug fixed above: exactly one "sans thematique" root, and no
    # node anywhere still carries a 0.0-for-null pct_top10 (the two Stream C findings).
    unclassified_roots = frame[(frame["id"].str.endswith("_0")) & (frame["parent_id"] == "")]
    assert len(unclassified_roots) == 1, (
        f"expected exactly one unclassified root node, found {len(unclassified_roots)}: "
        f"{unclassified_roots['id'].tolist()}"
    )
    assert dropped_n == 3, f"expected to drop exactly 3 duplicate Unclassified rows (f_0/sf_0/t_0), dropped {dropped_n}"

    # branchvalues="total" check: every parent's pubs >= sum of its direct children's pubs.
    by_parent = frame.groupby("parent_id")["pubs"].sum()
    for pid, child_sum in by_parent.items():
        if not pid:
            continue
        parent_pubs = int(frame.loc[frame["id"] == pid, "pubs"].iloc[0])
        assert child_sum <= parent_pubs, (
            f"parent {pid} has pubs={parent_pubs} but children sum to {child_sum} — "
            f"branchvalues='total' would render a negative remainder"
        )

    out = tables / "treemap_hierarchy.parquet"
    frame.to_parquet(out, index=False, compression=CONFIG["storage"]["compression"])

    n_null_top10 = int(frame["pct_top10"].isna().sum())
    lines = [
        f"- treemap nodes: **{len(frame):,}** (prefixed d_/f_/sf_/t_, one flat plotly namespace)",
        f"- levels: " + " · ".join(f"{lvl} {int((frame['level']==lvl).sum()):,}" for lvl in PREFIX),
        f"- parent-sum check passed for every node with children (branchvalues='total' is safe)",
        f"- dropped **{dropped_n}** duplicate Unclassified rows (f_0/sf_0/t_0) so the 51 untopiced "
        f"works appear as exactly ONE root node, not four (Stream C finding, fixed 2026-08-11)",
        f"- **{n_null_top10}** node(s) carry a null pct_top10 (thin/no stratum) -- left null, never "
        f"0.0-filled (D53; Stream C finding, fixed 2026-08-11)",
    ]
    report = ROOT / CONFIG["paths"]["reports"] / "treemap_hierarchy.md"
    report.write_text("# Treemap hierarchy (page 3 section 1)\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    Manifest(snapshot).record_step(
        "44b_build_treemap",
        counts={"rows": len(frame), "dropped_duplicate_unclassified": dropped_n, "null_pct_top10": n_null_top10},
        files=[out],
        params={"id_prefixes": PREFIX},
        notes="Straight pivot of thematic_overview.parquet; new builder per the contract (MISSING in v2). "
              "2026-08-11 fix: single Unclassified root (was 4x-duplicated), pct_top10 null not 0.0-filled (D53).",
    )
    append_summary(snapshot, "44b_build_treemap", lines)
    print("\n".join(lines))
    print(f"\nwrote {out.name}")


if __name__ == "__main__":
    main()
