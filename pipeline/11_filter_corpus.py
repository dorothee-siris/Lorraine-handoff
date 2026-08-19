"""11_filter_corpus.py — apply the scope rules and quantify the doc-type shift (gate G2).

Doc types were deliberately not filtered at pull time, so this step can measure exactly how much of
the v1 -> v2 corpus change is OpenAlex's own doc-type reclassification rather than anything SIRIS did.
That comparison is the headline of the shift report and the thing most likely to be misread as
"SIRIS broke the tool" (plan R1).

Usage: python pipeline/11_filter_corpus.py [--snapshot 2026-08-10]
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
V1_PUBS = ROOT.parent / "Phase 1" / "pipeline" / "data" / "pubs_final.parquet"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()

    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables_dir = snapshot / "tables"
    works = pd.read_parquet(tables_dir / "works.parquet")
    rules = CONFIG["corpus_filter"]
    print(f"snapshot {snapshot.name}: {len(works):,} works pulled")

    # --- the funnel, counted at every stage so nothing disappears unexplained ---
    funnel: list[tuple[str, int, int]] = []
    kept = works
    stages = [
        ("doc type in " + ", ".join(rules["doc_types_keep"]), kept["type"].isin(rules["doc_types_keep"])),
        ("not retracted", ~kept["is_retracted"].fillna(False)),
        ("not paratext", ~kept["is_paratext"].fillna(False)),
        ("has a title", kept["title"].notna() & (kept["title"].astype(str).str.strip() != "")),
    ]
    for label, mask in stages:
        before = len(kept)
        kept = kept[mask.reindex(kept.index).fillna(False)]
        funnel.append((label, before, len(kept)))
        print(f"  {label}: {before:,} -> {len(kept):,} (dropped {before - len(kept):,})")

    assert not (kept["type"] == "preprint").any(), "a preprint survived the filter (D10)"
    assert kept["work_id"].is_unique, "duplicate work ids in the corpus"

    kept = kept.copy()
    kept["in_corpus"] = True
    if rules.get("flag_conference_papers"):
        # D36: conference papers are in the corpus but must stay separable — median 0 citations
        # and 78% zero-cited, so any view or indicator can include or exclude them explicitly.
        kept["is_conference"] = kept["type"] == "conference-paper"
    corpus_path = tables_dir / "corpus.parquet"
    kept.to_parquet(corpus_path, index=False, compression=CONFIG["storage"]["compression"])

    # child tables restricted to the corpus, so downstream steps cannot silently read out of scope
    corpus_ids = set(kept["work_id"])
    child_written = [corpus_path]
    for name in ("authorships", "topics", "sdg", "funding"):
        source = tables_dir / f"{name}.parquet"
        if not source.exists():
            continue
        frame = pd.read_parquet(source)
        subset = frame[frame["work_id"].isin(corpus_ids)]
        target = tables_dir / f"corpus_{name}.parquet"
        subset.to_parquet(target, index=False, compression=CONFIG["storage"]["compression"])
        child_written.append(target)
        print(f"  corpus_{name}: {len(subset):,} rows (from {len(frame):,})")

    # --- G2: the doc-type comparison against v1 ---
    v2_types = works["type"].value_counts()
    v2_kept_types = kept["type"].value_counts()
    lines = [
        f"- pulled: **{len(works):,}** works · **corpus after scope rules: {len(kept):,}**",
        f"- v1 final corpus: {CONFIG['baselines_v1']['corpus_final']:,} "
        f"({(len(kept) / CONFIG['baselines_v1']['corpus_final'] - 1):+.1%})",
        "",
        "| Stage | Before | After | Dropped |",
        "|---|---|---|---|",
    ]
    for label, before, after in funnel:
        lines.append(f"| {label} | {before:,} | {after:,} | {before - after:,} |")
    lines += [
        "",
        "| Doc type (all pulled) | Works | Kept in corpus |",
        "|---|---|---|",
    ]
    for doc_type, count in v2_types.items():
        lines.append(f"| {doc_type} | {count:,} | {v2_kept_types.get(doc_type, 0):,} |")

    if V1_PUBS.exists():
        v1 = pd.read_parquet(V1_PUBS, columns=["OpenAlex ID", "Publication Type"])
        v1_ids = {str(x).rsplit("/", 1)[-1] for x in v1["OpenAlex ID"]}
        v1_types = v1["Publication Type"].value_counts()
        lines += [
            "",
            "### v1 vs v2, doc type by doc type (the G2 table)",
            "",
            "| Doc type | v1 corpus | v2 corpus | delta |",
            "|---|---|---|---|",
        ]
        for doc_type in sorted(set(v1_types.index) | set(v2_kept_types.index)):
            a, b = int(v1_types.get(doc_type, 0)), int(v2_kept_types.get(doc_type, 0))
            lines.append(f"| {doc_type} | {a:,} | {b:,} | {b - a:+,} |")

        # Work-level continuity: what actually happened to v1's works in v2?
        pulled_ids = set(works["work_id"])
        in_v2_corpus = len(v1_ids & corpus_ids)
        pulled_not_corpus = v1_ids & pulled_ids - corpus_ids
        absent = v1_ids - pulled_ids
        reclassified = works[works["work_id"].isin(pulled_not_corpus)]["type"].value_counts()
        lines += [
            "",
            "### What became of v1's 28,094 works",
            "",
            f"- still in the v2 corpus: **{in_v2_corpus:,}** ({in_v2_corpus / len(v1_ids):.1%})",
            f"- pulled but filtered out (doc type reclassified upstream): **{len(pulled_not_corpus):,}**",
            f"- not in the v2 perimeter at all: **{len(absent):,}**",
            f"- new works in v2 not present in v1: **{len(corpus_ids - v1_ids):,}**",
            "",
            "| v1 work now typed as | Works |",
            "|---|---|",
        ]
        for doc_type, count in reclassified.items():
            lines.append(f"| {doc_type} | {count:,} |")

    report = ROOT / CONFIG["paths"]["reports"] / "g2_doctype_shift.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# G2 — corpus scope and doc-type shift\n\n" + "\n".join(lines) + "\n", encoding="utf-8")

    Manifest(snapshot).record_step(
        "11_filter_corpus",
        counts={"pulled": len(works), "corpus": len(kept)},
        files=child_written,
        params={
            "doc_types_keep": rules["doc_types_keep"],
            "exclude_preprints": rules["exclude_preprints"],
            "require_doi": rules["require_doi"],
            "apply_indexed_in_crossref": rules["apply_indexed_in_crossref"],
            "funnel": [{"stage": s, "before": b, "after": a} for s, b, a in funnel],
        },
        notes="Doc types filtered here, never at pull time, so G2 can attribute the shift.",
    )
    append_summary(snapshot, "11_filter_corpus", lines[:6])
    print("\n".join(lines))
    print(f"\nwrote {corpus_path.name} and {report}")


if __name__ == "__main__":
    main()
