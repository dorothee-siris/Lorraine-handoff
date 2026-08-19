"""47d_build_sdg_methods.py -- sdg_lab_methods.parquet (pass 6, P11 / P6-R7, inventory #7/#10/#12).

Per-lab SIRIS-vocabulary-vs-Aurora(OpenAlex) SDG METHOD COMPARISON, framed exactly as P6-R7 rules:
a method-comparison surface, never a peer/lab comparison (crossing != comparing, R16 untouched).

Grain: lab (69, incl. NO LAB -- same 47b_build_crossings.py precedent: a real, measurable slice,
keeps every reconciliation identity exact with no special case) x sdg (1-16, no SDG17 sheet -- the
SIRIS route never tags it, so the comparison stays on the SAME 16-number range for both methods)
x conf_state (all, no_conf -- app-wide convention, matches this table's sibling thm_sdg_labs).

Two independently-sourced tag sets, same lab-membership mask (works_master.Labs, ' | '-split,
identical convention to 47b_build_crossings.py / 43_build_labs.py):
  SIRIS  (VocTagger, b_siris)   -- sdg_siris.parquet, work x sdg long table, read directly (same
                                   source thm_sdg_labs and the shipped ODD panel's default
                                   app.sdg_variant='b_siris' both already use).
  Aurora (OpenAlex native)      -- corpus_sdg.parquet, thresholded at config.sdg.openalex_metadata
                                   .threshold (0.40, OurResearch's own floor -- same threshold
                                   pipeline/55_sdg_three_way.py's C-method and bench_sdg both use).

#7 (share of LAB CORPUS tagged, not only the tagged part): lab_total_pubs / lab_tagged_siris /
lab_tagged_aurora are the lab's own corpus/tagged-corpus sizes (denominators for the page's #7
sort-by-ODD-desc default and its "share of corpus" reading); n_siris / n_aurora are this lab x
ODD's own tagged-work count per method. share_lab_corpus_siris = n_siris / lab_total_pubs and
share_lab_corpus_aurora = n_aurora / lab_total_pubs answer #7 directly; D53 floor: NULL (never 0)
when lab_total_pubs < config.metrics.min_stratum_n (30) -- raw counts are NEVER floored (a count is
a fact, a rate is not).

Reconciliation (site totals must equal the shipped page-4 site panel's numbers, tier-A eval):
the UNION over all 69 lab work-sets (incl. NO LAB) of (lab's works) INTERSECT (tagged-by-method
works), per SDG, equals sdg_siris.parquet's / corpus_sdg.parquet's own full distinct-tagged-work
set for that SDG, EXACTLY -- the identical partition-by-union discipline
pipeline/47b_build_crossings.py's own thm_sdg_labs reconciliation already uses (a work belongs to
>=1 curated lab or the literal "NO LAB" value, never neither).

Usage: python pipeline/47d_build_sdg_methods.py [--snapshot 2026-08-11]
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
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
CONFIG = load_config(ROOT)
MIN_STRATUM_N = int(CONFIG["metrics"]["min_stratum_n"])  # 30, D53 floor
AURORA_THRESHOLD = float(CONFIG["sdg"]["openalex_metadata"]["threshold"])  # 0.40
CONF_STATES = ["all", "no_conf"]
SDG_NUMBERS = list(range(1, 17))  # no SDG17 sheet in the SIRIS route -- same range both methods


def sdg_number(label) -> int | None:
    """Same parse pipeline/55_sdg_three_way.py's sdg_number() uses -- corpus_sdg.sdg_id is a bare
    numeric string on this snapshot, but parsed defensively in case a future pull reformats it."""
    match = re.search(r"(\d{1,2})", str(label))
    if not match:
        return None
    number = int(match.group(1))
    return number if 1 <= number <= 17 else None


def conf_mask(works: pd.DataFrame, state: str) -> pd.Series:
    return pd.Series(True, index=works.index) if state == "all" else ~works["is_conference"].fillna(False)


def lab_masks(works: pd.DataFrame, lab_names: list[str]) -> dict[str, pd.Series]:
    split = works["Labs"].fillna("").str.split(" | ", regex=False)
    return {lab: split.apply(lambda ls: lab in ls) for lab in lab_names}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    print(f"snapshot {snapshot.name}: building sdg_lab_methods (pass 6, P11)")

    works = pd.read_parquet(tables / "works_master.parquet",
                            columns=["work_id", "is_conference", "Labs"])
    ul_labs = pd.read_parquet(tables / "ul_labs.parquet", columns=["lab", "works"])
    lab_names = ul_labs["lab"].tolist()
    assert len(lab_names) == 69, f"ul_labs.lab universe drifted: {len(lab_names)} != 69"
    masks = lab_masks(works, lab_names)

    siris = pd.read_parquet(tables / "sdg_siris.parquet", columns=["work_id", "sdg"])
    siris = siris[siris["sdg"].isin(SDG_NUMBERS)]
    siris_tagged_global = set(siris["work_id"].unique())
    print(f"  sdg_siris.parquet (SIRIS/VocTagger): {len(siris):,} work x sdg rows, "
          f"{len(siris_tagged_global):,} distinct tagged works")

    aurora_raw = pd.read_parquet(tables / "corpus_sdg.parquet", columns=["work_id", "sdg_id", "score"])
    aurora_raw = aurora_raw[aurora_raw["score"].fillna(0) >= AURORA_THRESHOLD]
    aurora_raw["sdg"] = aurora_raw["sdg_id"].map(sdg_number)
    aurora = aurora_raw[aurora_raw["sdg"].isin(SDG_NUMBERS)][["work_id", "sdg"]].drop_duplicates()
    aurora_tagged_global = set(aurora["work_id"].unique())
    print(f"  corpus_sdg.parquet (Aurora/OpenAlex, score>={AURORA_THRESHOLD}): {len(aurora):,} "
          f"work x sdg rows, {len(aurora_tagged_global):,} distinct tagged works")

    rows = []
    for conf_state in CONF_STATES:
        cm = conf_mask(works, conf_state)
        for lab in lab_names:
            m = masks[lab] & cm
            lab_ids = set(works.loc[m, "work_id"])
            lab_total_pubs = len(lab_ids)

            lab_siris = siris[siris["work_id"].isin(lab_ids)]
            lab_aurora = aurora[aurora["work_id"].isin(lab_ids)]
            lab_tagged_siris = lab_siris["work_id"].nunique()
            lab_tagged_aurora = lab_aurora["work_id"].nunique()

            per_sdg_siris = lab_siris.groupby("sdg")["work_id"].nunique()
            per_sdg_aurora = lab_aurora.groupby("sdg")["work_id"].nunique()

            for sdg in SDG_NUMBERS:
                n_siris = int(per_sdg_siris.get(sdg, 0))
                n_aurora = int(per_sdg_aurora.get(sdg, 0))
                share_siris = (n_siris / lab_total_pubs) if lab_total_pubs >= MIN_STRATUM_N else np.nan
                share_aurora = (n_aurora / lab_total_pubs) if lab_total_pubs >= MIN_STRATUM_N else np.nan
                rows.append({
                    "lab": lab, "sdg": sdg, "conf_state": conf_state,
                    "lab_total_pubs": lab_total_pubs,
                    "lab_tagged_siris": lab_tagged_siris, "lab_tagged_aurora": lab_tagged_aurora,
                    "n_siris": n_siris, "n_aurora": n_aurora,
                    "share_lab_corpus_siris": share_siris, "share_lab_corpus_aurora": share_aurora,
                })

    out = pd.DataFrame(rows)
    out["snapshot_date"] = snapshot.name
    out = out.astype({
        "lab": "string", "sdg": "int64", "conf_state": "string",
        "lab_total_pubs": "int64", "lab_tagged_siris": "int64", "lab_tagged_aurora": "int64",
        "n_siris": "int64", "n_aurora": "int64",
        "share_lab_corpus_siris": "float64", "share_lab_corpus_aurora": "float64",
        "snapshot_date": "string",
    })
    assert (out["share_lab_corpus_siris"].dropna() <= 1.0000001).all()
    assert (out["share_lab_corpus_aurora"].dropna() <= 1.0000001).all()
    print(f"  wrote {len(out):,} rows ({len(lab_names)} labs x {len(SDG_NUMBERS)} SDGs x "
          f"{len(CONF_STATES)} conf_states)")

    # ============================================================================= RECONCILIATION
    print("\n" + "=" * 78)
    print("RECONCILIATION (tier-A eval basis: site totals reconcile with the shipped panels)")
    print("=" * 78)

    for method, tagged_col, tagged_global in (
        ("SIRIS", siris, siris_tagged_global), ("Aurora", aurora, aurora_tagged_global),
    ):
        for sdg in SDG_NUMBERS:
            method_sdg_ids = set(tagged_col.loc[tagged_col["sdg"] == sdg, "work_id"])
            union_labs: set[str] = set()
            for lab in lab_names:
                union_labs |= (set(works.loc[masks[lab], "work_id"]) & method_sdg_ids)
            assert union_labs == method_sdg_ids, (
                f"{method} SDG {sdg}: union-of-69-labs ({len(union_labs)}) != the method's own "
                f"tagged set ({len(method_sdg_ids)}) -- a work is not covered by any lab or NO LAB"
            )
    print("  PASS: for every SDG and both methods, the union of the 69 lab work-sets (conf_state="
          "'all') exactly reproduces the method's own tagged-work set (no work missed, none extra).")

    # ============================================================================= write out
    out_path = tables / "sdg_lab_methods.parquet"
    out.to_parquet(out_path, index=False, compression=CONFIG["storage"]["compression"])

    lines = [
        f"- `sdg_lab_methods`: **{len(out):,}** rows (69 labs x 16 SDGs x 2 conf_states)",
        f"- SIRIS (VocTagger, b_siris) distinct tagged works corpus-wide: **{len(siris_tagged_global):,}**",
        f"- Aurora (OpenAlex, score>={AURORA_THRESHOLD}) distinct tagged works corpus-wide: "
        f"**{len(aurora_tagged_global):,}**",
        f"- reconciliation: union-of-69-labs == method's own tagged set, PASS for both methods, "
        f"all 16 SDGs (conf_state='all')",
        f"- share_lab_corpus_* floored at min_stratum_n={MIN_STRATUM_N} on lab_total_pubs (D53); "
        f"raw counts (n_siris/n_aurora/lab_total_pubs/lab_tagged_*) never floored",
    ]
    report = ROOT / CONFIG["paths"]["reports"] / "sdg_lab_methods.md"
    report.write_text("# sdg_lab_methods (pass 6, P11) -- SIRIS vs Aurora, per lab per ODD\n\n"
                      + "\n".join(lines) + "\n", encoding="utf-8")
    Manifest(snapshot).record_step(
        "47d_build_sdg_methods",
        counts={"rows": len(out), "siris_tagged_global": len(siris_tagged_global),
                "aurora_tagged_global": len(aurora_tagged_global)},
        files=[out_path],
        params={"min_stratum_n": MIN_STRATUM_N, "aurora_threshold": AURORA_THRESHOLD,
                "sdg_numbers": SDG_NUMBERS, "lab_universe": lab_names},
        notes="Pass 6, P11/P6-R7: per-lab SIRIS-vs-Aurora SDG method comparison + lab-corpus-share "
              "columns for #7. Method comparison only -- no peer context (R16 crossing != comparing "
              "untouched). Union-of-labs reconciliation verified exact for both methods.",
    )
    append_summary(snapshot, "47d_build_sdg_methods", lines)
    print("\n".join(lines))
    print(f"\nwrote {out_path.name}")


if __name__ == "__main__":
    main()
