"""55_sdg_three_way.py — the SDG method comparison the client decides on (gate G6).

Three methods over the v2 corpus:
  **A** v1's shipped `publications_SDG_pivot.csv` — historical reference, NOT ground truth. v1 has no
        archived builder, no recorded parameters and no vocabulary snapshot, and it tagged at 80.1%
        abstract coverage using BigQuery text that was never archived. Any A-vs-B difference is a
        *method* difference; it can never be read as a determinism test (`sdg_method_recovery.md`).
  **B** SIRIS vocabulary v2 — 16 per-SDG passes, VocTagger defaults (D19).
  **C** OpenAlex's Aurora BERT metadata, thresholded at 0.4 — which is OurResearch's own floor and
        also the *lowest possible* cut, since every published score is >= 0.40.

Because no hand-labelled ground truth exists yet (`tests/golden/sdg_golden_sample.csv` is unlabelled
by design), this script reports **agreement, never accuracy**. The deliverable for the workshop is the
disagreement-weighted review sample: works sampled deliberately where the methods disagree, with the
text and all three verdicts side by side and an empty `human_verdict` column.

Usage: python pipeline/55_sdg_three_way.py [--snapshot 2026-08-11]
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
V1_PIVOT = ROOT.parent / "Phase 1" / "pipeline" / "inputs" / "external" / "publications_SDG_pivot.csv"
PER_CLASS = 12          # works sampled per disagreement class


def sdg_number(label: str) -> int | None:
    match = re.search(r"(\d{1,2})", str(label))
    if not match:
        return None
    number = int(match.group(1))
    return number if 1 <= number <= 17 else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    works = pd.read_parquet(tables / "works_master.parquet")
    text = pd.read_parquet(tables / "sdg_text_ready.parquet")[
        ["work_id", "text_to_tag", "lang_detected", "translated", "title_only", "abstract_source"]
    ]
    corpus_ids = set(works["work_id"])

    # --- B: SIRIS v2 ---------------------------------------------------------------------------
    siris = pd.read_parquet(tables / "sdg_siris.parquet")
    b_sets = siris.groupby("work_id")["sdg"].apply(lambda s: frozenset(int(x) for x in s)).to_dict()

    # --- C: OpenAlex Aurora, at OurResearch's own 0.4 floor -------------------------------------
    oa = pd.read_parquet(tables / "corpus_sdg.parquet")
    threshold = CONFIG["sdg"]["openalex_metadata"]["threshold"]
    oa = oa[oa["score"].fillna(0) >= threshold]
    oa["sdg_num"] = oa["sdg_id"].map(sdg_number)
    oa = oa[oa["sdg_num"].notna()]
    c_sets = oa.groupby("work_id")["sdg_num"].apply(lambda s: frozenset(int(x) for x in s)).to_dict()

    # --- A: v1's shipped pivot, restricted to works present in the v2 corpus --------------------
    a_sets: dict[str, frozenset] = {}
    if V1_PIVOT.exists():
        v1 = pd.read_csv(V1_PIVOT)
        id_column = v1.columns[0]
        v1[id_column] = v1[id_column].astype(str).str.rsplit("/", n=1).str[-1]
        sdg_columns = {c: sdg_number(c) for c in v1.columns[1:]}
        sdg_columns = {c: n for c, n in sdg_columns.items() if n}
        for row in v1.itertuples(index=False):
            record = dict(zip(v1.columns, row))
            work_id = record[id_column]
            hits = frozenset(n for c, n in sdg_columns.items() if float(record.get(c) or 0) > 0)
            if hits:
                a_sets[work_id] = hits
        print(f"v1 pivot: {len(a_sets):,} tagged works ({len(set(a_sets) & corpus_ids):,} of them still "
              f"in the v2 corpus)")
    else:
        print(f"! v1 pivot not found at {V1_PIVOT} — the comparison runs on B vs C only")

    # --- coverage ------------------------------------------------------------------------------
    def coverage(sets: dict) -> tuple[int, int, float]:
        inside = {k: v for k, v in sets.items() if k in corpus_ids}
        pairs = sum(len(v) for v in inside.values())
        return len(inside), pairs, (pairs / len(inside) if inside else 0.0)

    rows = []
    for name, sets, note in (
        ("A — v1 shipped", a_sets, "reference only, not ground truth"),
        ("B — SIRIS v2 (16 passes, defaults)", b_sets, "D19"),
        (f"C — OpenAlex Aurora >= {threshold}", c_sets, "single-label by construction"),
    ):
        tagged, pairs, per_work = coverage(sets)
        rows.append({"method": name, "works_tagged": tagged,
                     "share_of_corpus": round(tagged / len(works), 4),
                     "work_sdg_pairs": pairs, "sdgs_per_tagged_work": round(per_work, 3), "note": note})
    summary = pd.DataFrame(rows)
    print(summary.to_string(index=False))

    # --- pairwise agreement --------------------------------------------------------------------
    def jaccard(x: frozenset, y: frozenset) -> float:
        if not x and not y:
            return 1.0
        return len(x & y) / len(x | y) if (x | y) else 0.0

    pair_rows = []
    for left_name, left, right_name, right in (
        ("A", a_sets, "B", b_sets), ("A", a_sets, "C", c_sets), ("B", b_sets, "C", c_sets),
    ):
        both = [w for w in corpus_ids if w in left and w in right]
        if not both:
            continue
        identical = sum(1 for w in both if left[w] == right[w])
        mean_j = sum(jaccard(left[w], right[w]) for w in both) / len(both)
        only_left = len([w for w in corpus_ids if w in left and w not in right])
        only_right = len([w for w in corpus_ids if w in right and w not in left])
        pair_rows.append({
            "pair": f"{left_name} vs {right_name}", "tagged_by_both": len(both),
            "identical_sdg_set": identical,
            "identical_share": round(identical / len(both), 4),
            "mean_jaccard": round(mean_j, 4),
            f"only_{left_name}": only_left, f"only_{right_name}": only_right,
        })
    pairwise = pd.DataFrame(pair_rows)
    print(pairwise.to_string(index=False))

    # --- per-SDG counts ------------------------------------------------------------------------
    per_sdg = []
    for number in range(1, 18):
        per_sdg.append({
            "sdg": number,
            "A_v1": sum(1 for w, s in a_sets.items() if w in corpus_ids and number in s),
            "B_siris": sum(1 for w, s in b_sets.items() if number in s),
            "C_openalex": sum(1 for w, s in c_sets.items() if w in corpus_ids and number in s),
        })
    per_sdg_frame = pd.DataFrame(per_sdg)

    # --- 3-way concordance on works any method tagged -------------------------------------------
    universe = sorted((set(a_sets) | set(b_sets) | set(c_sets)) & corpus_ids)
    concordance = {"all_three_identical": 0, "two_identical": 0, "all_differ": 0}
    classes: dict[str, list] = {"B_not_C": [], "C_not_B": [], "A_not_B": [], "B_not_A": [],
                                "all_agree": []}
    for work_id in universe:
        a, b, c = a_sets.get(work_id, frozenset()), b_sets.get(work_id, frozenset()), c_sets.get(work_id, frozenset())
        if a == b == c:
            concordance["all_three_identical"] += 1
        elif a == b or a == c or b == c:
            concordance["two_identical"] += 1
        else:
            concordance["all_differ"] += 1
        if b and not c:
            classes["B_not_C"].append(work_id)
        if c and not b:
            classes["C_not_B"].append(work_id)
        if a and not b:
            classes["A_not_B"].append(work_id)
        if b and not a:
            classes["B_not_A"].append(work_id)
        if a and b and c and a == b == c:
            classes["all_agree"].append(work_id)

    # Which combination of methods fires on each work. This is the informative view: a plain
    # "two of three agree" count is dominated by works where A and B are both empty and only C tagged,
    # which is agreement in name only.
    patterns: dict[str, int] = {}
    for work_id in universe:
        key = "+".join(
            name for name, sets in (("A", a_sets), ("B", b_sets), ("C", c_sets))
            if sets.get(work_id)
        ) or "none"
        patterns[key] = patterns.get(key, 0) + 1
    pattern_frame = (pd.DataFrame([{"methods_tagging": k, "works": v} for k, v in patterns.items()])
                     .sort_values("works", ascending=False))
    all_three = [w for w in universe if a_sets.get(w) and b_sets.get(w) and c_sets.get(w)]
    triple_identical = sum(1 for w in all_three if a_sets[w] == b_sets[w] == c_sets[w])

    # --- the review sample: stratified ON DISAGREEMENT, not at random ---------------------------
    review_rows = []
    for class_name, ids in classes.items():
        for work_id in ids[:PER_CLASS]:
            review_rows.append({
                "work_id": work_id,
                "disagreement_class": class_name,
                "A_v1": " ".join(f"SDG{n}" for n in sorted(a_sets.get(work_id, ()))),
                "B_siris": " ".join(f"SDG{n}" for n in sorted(b_sets.get(work_id, ()))),
                "C_openalex": " ".join(f"SDG{n}" for n in sorted(c_sets.get(work_id, ()))),
            })
    review = pd.DataFrame(review_rows).merge(
        works[["work_id", "title", "publication_year", "type", "Labs"]], on="work_id", how="left"
    ).merge(text, on="work_id", how="left")
    review["human_verdict"] = ""
    review["reviewer"] = ""
    review["text_to_tag"] = review["text_to_tag"].str.slice(0, 1200)

    out_xlsx = ROOT / CONFIG["paths"]["reports"] / "sdg_three_way_review_sample.xlsx"
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="coverage", index=False)
        pairwise.to_excel(writer, sheet_name="agreement", index=False)
        per_sdg_frame.to_excel(writer, sheet_name="per_sdg", index=False)
        pd.DataFrame([concordance]).to_excel(writer, sheet_name="concordance", index=False)
        pattern_frame.to_excel(writer, sheet_name="who_tags_what", index=False)
        review.to_excel(writer, sheet_name="review_sample", index=False)

    comparison = tables / "sdg_three_way.parquet"
    pd.DataFrame([{"work_id": w,
                   "A_v1": " ".join(map(str, sorted(a_sets.get(w, ())))) or None,
                   "B_siris": " ".join(map(str, sorted(b_sets.get(w, ())))) or None,
                   "C_openalex": " ".join(map(str, sorted(c_sets.get(w, ())))) or None}
                  for w in universe]).to_parquet(comparison, index=False,
                                                 compression=CONFIG["storage"]["compression"])

    lines = [
        "## Coverage", "", summary.to_markdown(index=False), "",
        "## Pairwise agreement", "", pairwise.to_markdown(index=False), "",
        f"## Which methods tag a work at all (on the {len(universe):,} works any method tagged)", "",
        pattern_frame.to_markdown(index=False), "",
        "> Read the pattern table, not a raw 'two of three agree' count: on a work only OpenAlex tags, A",
        "> and B are both the empty set, so they trivially 'agree'. Restricted to works **all three**",
        f"> tagged ({len(all_three):,}), the sets are identical on **{triple_identical:,}** "
        f"({triple_identical/max(len(all_three),1):.1%}).", "",
        "## Per-SDG counts", "", per_sdg_frame.to_markdown(index=False), "",
        "## What this can and cannot say", "",
        "- These are **agreement** figures, not accuracy. No hand-labelled ground truth exists yet:",
        "  `tests/golden/sdg_golden_sample.csv` is deliberately unlabelled, and v1 is a reference, not",
        "  truth — it has no archived builder, no recorded parameters, and it tagged on BigQuery text",
        "  that was never kept.",
        "- **OpenAlex Aurora is a different classifier, not a looser one.** It is strictly single-label",
        "  (exactly 1.00 SDG per tagged work) and its scores are floored at exactly 0.40, so 0.4 is",
        "  everything it publishes. It cannot express a multi-SDG work, where v1 averages 1.50 and the",
        "  vocabulary route 1.45.",
        f"- Review sample: **{len(review):,}** works, stratified deliberately on disagreement",
        f"  ({', '.join(classes)}), with text, all three verdicts and an empty `human_verdict` column →",
        f"  `reports/{out_xlsx.name}`. **This is the artefact to work through with I-SITE at the workshop.**",
    ]
    report = ROOT / CONFIG["paths"]["reports"] / "g6_sdg_three_way.md"
    report.write_text("# G6 — SDG method comparison (A: v1 · B: SIRIS v2 · C: OpenAlex Aurora)\n\n"
                      + "\n".join(lines) + "\n", encoding="utf-8")
    Manifest(snapshot).record_step(
        "55_sdg_three_way",
        counts={"universe": len(universe), **concordance,
                **{r["method"][:1] + "_tagged": r["works_tagged"] for r in rows}},
        files=[comparison],
        params={"openalex_threshold": threshold, "per_disagreement_class": PER_CLASS,
                "ground_truth_available": False},
        notes="Agreement only, never accuracy: no hand-labelled sample exists yet (D44).",
    )
    append_summary(snapshot, "55_sdg_three_way", lines[:6])
    print("\n".join(lines))
    print(f"\nwrote {comparison.name}, {out_xlsx.name} and {report}")


if __name__ == "__main__":
    main()
