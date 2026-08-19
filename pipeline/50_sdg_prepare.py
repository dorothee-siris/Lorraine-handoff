"""50_sdg_prepare.py — build the text to tag, detect its language, and size gate G5c.

Text composition is settled by the §8.2 grid: `title. abstract`, capped at 400 words, `min_keyword_hits
= 1`. Title+abstract beat abstract-only (Jaccard 0.941 vs 0.909); a >=2 keyword-hit rule is destructive
(coverage 48.5% -> 16.5%).

Language detection exists to decide what gets translated, and translation is worth **48% vs 9%**
coverage on French works — the single largest lever in the whole SDG stage. It uses `py3langid` with
`norm_probs=True`: `classify()` otherwise returns a **log-probability** (e.g. -201.4), and comparing
that to a 0.90 threshold is meaningless. In Phase 1 a percentile-rank workaround translated 387 of
5,792 French documents instead of 5,743.

Gate **G5c** is the eligibility of works whose only text is a title. This step measures it.

Usage: python pipeline/50_sdg_prepare.py [--snapshot 2026-08-11]
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
SDG = CONFIG["sdg"]
MAX_WORDS = SDG["text"]["max_words"]


def build_text(title: str | None, abstract: str | None) -> str:
    """`title. abstract`, capped. The cap matters: v1 measured mean 119 words, median 103."""
    parts = []
    if isinstance(title, str) and title.strip():
        parts.append(title.strip().rstrip("."))
    if isinstance(abstract, str) and abstract.strip():
        parts.append(abstract.strip())
    text = ". ".join(parts)
    words = text.split()
    return " ".join(words[:MAX_WORDS])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--sample-size", type=int, default=50)
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    works = pd.read_parquet(tables / "works_master.parquet")
    print(f"snapshot {snapshot.name}: {len(works):,} works")

    frame = works[["work_id", "title", "abstract", "abstract_source", "publication_year", "type",
                   "language", "primary_subfield_name"]].copy()
    frame["text"] = [build_text(t, a) for t, a in zip(frame["title"], frame["abstract"])]
    frame["n_words"] = frame["text"].str.split().str.len().fillna(0).astype(int)
    frame["has_abstract"] = frame["abstract"].notna()
    frame["title_only"] = ~frame["has_abstract"]

    # --- language detection ---------------------------------------------------------------------
    from py3langid.langid import MODEL_FILE, LanguageIdentifier

    identifier = LanguageIdentifier.from_pickled_model(MODEL_FILE, norm_probs=True)
    detected, probability = [], []
    for text in frame["text"]:
        if not text or len(text) < 20:
            detected.append(None)
            probability.append(None)
            continue
        lang, prob = identifier.classify(text)     # prob is a real 0..1 posterior, not a log-prob
        detected.append(lang)
        probability.append(float(prob))
    frame["lang_detected"] = detected
    frame["lang_prob"] = probability
    threshold = SDG["language_id"]["french_threshold"]
    frame["needs_translation"] = (frame["lang_detected"] == "fr") & (frame["lang_prob"] >= threshold)

    print(f"  language mix (detected): "
          + " · ".join(f"{k} {v:,}" for k, v in frame["lang_detected"].value_counts().head(8).items()))
    print(f"  to translate (fr at >= {threshold:.2f} posterior): "
          f"**{int(frame['needs_translation'].sum()):,}**")
    print(f"  text length: mean {frame['n_words'].mean():.0f} words · median "
          f"{frame['n_words'].median():.0f} · at the {MAX_WORDS}-word cap "
          f"{int((frame['n_words'] >= MAX_WORDS).sum()):,}")

    out = tables / "sdg_text.parquet"
    frame.to_parquet(out, index=False, compression=CONFIG["storage"]["compression"])

    # --- gate G5c ------------------------------------------------------------------------------
    title_only = frame[frame["title_only"]]
    floorless = frame[frame["n_words"] < 10]
    g5c = [
        f"- corpus: **{len(frame):,}** works · with an abstract **{int(frame['has_abstract'].sum()):,}** "
        f"({frame['has_abstract'].mean():.1%})",
        f"- **title-only works: {len(title_only):,}** ({len(title_only)/len(frame):.1%}) — v1's figure was "
        f"~11,895, so the abstract work (92.3% coverage) shrank this question by roughly three quarters",
        f"- works with fewer than 10 words of text at all: **{len(floorless):,}** "
        f"({len(floorless)/len(frame):.2%}) — the >=10-word floor is close to inert here",
        f"- title-only works by language: "
        + " · ".join(f"{k} {v:,}" for k, v in title_only["lang_detected"].value_counts().head(5).items()),
        f"- title-only works by type: "
        + " · ".join(f"{k} {v:,}" for k, v in title_only["type"].value_counts().head(5).items()),
        "",
        "**Measured expectation if title-only works ARE tagged** (§8.2 grid, 200 works): title-only "
        "coverage was **26%** on works v1 had tagged, **4%** on French ones, **7.5%** overall — a weak "
        "but non-zero signal. Tagging them adds recall and some noise; excluding them makes "
        f"{len(title_only)/len(frame):.1%} of the corpus structurally ineligible for an SDG.",
    ]

    # --- stratified sample for the golden set ---------------------------------------------------
    frame["stratum"] = (
        frame["has_abstract"].map({True: "abstract", False: "title_only"}) + "|"
        + frame["lang_detected"].fillna("??").where(frame["lang_detected"].isin(["en", "fr"]), "other") + "|"
        + pd.cut(frame["n_words"], [-1, 9, 100, 10_000], labels=["<10w", "10-100w", ">100w"]).astype(str)
        + "|" + frame["abstract_source"].fillna("none")
    )
    per_stratum = max(1, args.sample_size // max(frame["stratum"].nunique(), 1))
    sample = (frame.groupby("stratum", group_keys=False)
              .apply(lambda block: block.sample(min(len(block), per_stratum), random_state=42))
              .head(args.sample_size))
    golden_dir = ROOT / "tests" / "golden"
    golden_dir.mkdir(parents=True, exist_ok=True)
    golden = sample[["work_id", "stratum", "title", "abstract", "lang_detected", "n_words",
                     "abstract_source", "type", "publication_year", "primary_subfield_name"]].copy()
    for column in ("sdg_labels_human", "labeller", "label_date", "notes"):
        golden[column] = ""
    golden_path = golden_dir / "sdg_golden_sample.csv"
    golden.to_csv(golden_path, index=False, encoding="utf-8")

    lines = g5c + [
        "",
        f"- golden sample written to `tests/golden/sdg_golden_sample.csv`: **{len(golden)}** works across "
        f"**{sample['stratum'].nunique()}** strata (abstract presence x language x length band x abstract "
        f"source), `random_state=42` so it is reproducible.",
        "- **`sdg_labels_human` is intentionally empty.** Precision/recall against v1 is not ground "
        "truth (§8), and an LLM labelling its own evaluation set is not either. This file needs a "
        "domain reviewer, and until it has one the probe reports agreement between methods, never "
        "accuracy.",
    ]
    report = ROOT / CONFIG["paths"]["reports"] / "g5c_sdg_text_and_eligibility.md"
    report.write_text("# SDG text preparation and gate G5c\n\n" + "\n".join(lines) + "\n", encoding="utf-8")

    Manifest(snapshot).record_step(
        "50_sdg_prepare",
        counts={"works": len(frame), "with_abstract": int(frame["has_abstract"].sum()),
                "title_only": len(title_only), "needs_translation": int(frame["needs_translation"].sum()),
                "under_10_words": len(floorless)},
        files=[out],
        params={"max_words": MAX_WORDS, "composition": SDG["text"]["composition"],
                "min_keyword_hits": SDG["text"]["min_keyword_hits"],
                "french_threshold": threshold, "langid_norm_probs": True,
                "golden_sample": str(golden_path.relative_to(ROOT)), "sample_strata": int(sample["stratum"].nunique())},
        notes="py3langid with norm_probs=True; title. abstract capped at 400 words.",
    )
    append_summary(snapshot, "50_sdg_prepare", lines[:5])
    print("\n".join(lines))
    print(f"\nwrote {out.name}, {golden_path} and {report}")


if __name__ == "__main__":
    main()
