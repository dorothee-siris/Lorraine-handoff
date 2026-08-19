"""52_sdg_tag.py — SDG tagging: 16 separate per-SDG passes with VocTagger DEFAULTS (D19).

**Must run under the voctagger venv** (`config.yaml: interpreters.voctagger`), which has spaCy 3.7.2 +
`en_core_web_lg` + VocTagger:

    "../../Tools/voctagger/.venv/Scripts/python.exe" pipeline/52_sdg_tag.py --shard 0 --nshards 4

Why 16 passes and not one combined vocabulary, when combining is ~16x cheaper: under identical
parameters and text the combined 5,891-term vocabulary produced **188 keyword hits vs 194** — a strict
subset (6 lost, 0 gained, ~3%), and the loss is vocabulary-size dependent (a keyword found with 109,
692 and 1,699-term vocabularies is lost at 5,891; probable VocTagger bug, worth reporting upstream).
The best-agreeing method of ~40 measured is therefore the slow one. The project ruling stands: *"I don't
care about the time it takes now because I just want to reproduce a pipeline."* Do not "optimise"
this back to the combined vocabulary.

Runtime: ~1.445 s/work for the 16 passes => ~11.3 h single process, ~5-6 h over 4 shards (measured
sharding efficiency ~2x, not 4x: cores contend and each shard repays the spaCy init).

Resumable per (shard, SDG): each pass appends to its own parquet and is skipped if already complete,
so an interrupted overnight run costs nothing.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

CONFIG = load_config(ROOT)
SDG = CONFIG["sdg"]
N_SHEETS = SDG["n_sdg_sheets"]        # 16 — there is no SDG 17 sheet in the JRC vocabulary


def vocabulary_path(snapshot: Path) -> Path:
    """Archive the vocabulary into the snapshot on first use: reproducibility depends on its vintage."""
    archived = snapshot / SDG["vocabulary_archive_subdir"] / "vocabularies_sdgs.xlsx"
    if not archived.exists():
        archived.parent.mkdir(parents=True, exist_ok=True)
        source = (ROOT / SDG["vocabulary_source"]).resolve()
        shutil.copy2(source, archived)
        print(f"  archived the vocabulary to {archived.relative_to(snapshot)}")
    return archived


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--nshards", type=int, default=1)
    parser.add_argument("--limit", type=int, help="calibration: this many works only")
    parser.add_argument("--sdg", type=int, action="append", help="restrict to these SDG numbers")
    args = parser.parse_args()

    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"
    frame = pd.read_parquet(tables / "sdg_text_ready.parquet")
    frame = frame[frame["text_to_tag"].notna() & (frame["text_to_tag"].str.len() > 0)].copy()

    # G5c (project ruling, 2026-08-11): title-only works ARE tagged, but every row records what it was tagged on.
    frame["text_basis"] = frame["title_only"].map({True: "title_only", False: "title_abstract"})
    if args.limit:
        frame = frame.head(args.limit)
    shard = frame[frame.index % args.nshards == args.shard] if args.nshards > 1 else frame
    print(f"snapshot {snapshot.name}: shard {args.shard + 1}/{args.nshards} -> {len(shard):,} works "
          f"({int((shard['text_basis'] == 'title_only').sum()):,} title-only)")

    # The package exports the CLASS as `VocTagger` (package attrs: LanguageModel, VocTagger,
    # languageModels), so this name is the class itself, not the module — call it directly.
    from VocTagger import VocTagger  # noqa: E402  (only importable under the voctagger venv)

    vocab = vocabulary_path(snapshot)
    out_dir = snapshot / "tables" / "sdg_passes"
    out_dir.mkdir(parents=True, exist_ok=True)
    sdg_numbers = args.sdg or list(range(1, N_SHEETS + 1))
    tagger_params = SDG["tagger"]

    started = time.monotonic()
    for number in sdg_numbers:
        target = out_dir / f"sdg{number:02d}_shard{args.shard}.parquet"
        if target.exists():
            print(f"  SDG {number:>2}: already done ({target.name})")
            continue
        sheet = pd.read_excel(vocab, sheet_name=f"SDG {number}")[["ID", "keyword", "extra"]]
        tagger = VocTagger(
            sheet,
            lang=tagger_params["lang"],
            threshold=tagger_params["threshold"],
            lemmatize_vocabulary=tagger_params["lemmatize_vocabulary"],
            sentence_extras=tagger_params["sentence_extras"],
            interword_threshold=tagger_params["interword_threshold"],
        )
        pass_started = time.monotonic()
        tidy = tagger.tagTextCollection(
            shard[["work_id", "text_to_tag"]].rename(columns={"text_to_tag": "text"}),
            text_id="work_id",
            text_column="text",
            n_cores=tagger_params["n_cores"],     # spaCy MP is flaky on Windows; shard processes instead
        )
        # TRAP: tagTextCollection ends with .set_index(index_name), so the work id is the INDEX and the
        # columns are only ['ID','keyword','extra']. Without reset_index a rename is a no-op and
        # to_parquet(index=False) DISCARDS every work id, producing a table with correct row counts
        # and real keywords that joins to nothing.
        tidy = tidy.reset_index()
        assert "work_id" in tidy.columns, f"work id lost for SDG {number}: columns {list(tidy.columns)}"
        tidy["sdg"] = number
        tidy.to_parquet(target, index=False, compression=CONFIG["storage"]["compression"])
        elapsed = time.monotonic() - pass_started
        print(f"  SDG {number:>2}: {len(tidy):,} keyword hits on "
              f"{tidy['work_id'].nunique():,} works · {elapsed/60:.1f} min", flush=True)

    total = (time.monotonic() - started) / 60
    print(f"shard {args.shard} finished in {total:.1f} min "
          f"({total * 60 / max(len(shard), 1):.3f} s/work)")

    # The consolidation only runs when every shard x SDG file is present.
    expected = {f"sdg{n:02d}_shard{s}.parquet" for n in range(1, N_SHEETS + 1)
                for s in range(args.nshards)}
    present = {p.name for p in out_dir.glob("*.parquet")}
    if not expected <= present:
        print(f"  {len(expected - present)} of {len(expected)} pass files still missing — "
              f"run the other shards, then re-run any one of them to consolidate")
        return

    hits = pd.concat([pd.read_parquet(p) for p in sorted(out_dir.glob("*.parquet"))], ignore_index=True)
    basis = dict(zip(frame["work_id"], frame["text_basis"]))
    hits["text_basis"] = hits["work_id"].map(basis)
    per_work = (hits.groupby(["work_id", "sdg"]).size().reset_index(name="keyword_hits"))
    # min_keyword_hits = 1: >=2 is destructive (coverage 48.5% -> 16.5%, Jaccard 0.941 -> 0.619)
    per_work = per_work[per_work["keyword_hits"] >= SDG["text"]["min_keyword_hits"]]
    per_work["text_basis"] = per_work["work_id"].map(basis)

    out_hits = tables / "sdg_keyword_hits.parquet"
    out_works = tables / "sdg_siris.parquet"
    hits.to_parquet(out_hits, index=False, compression=CONFIG["storage"]["compression"])
    per_work.to_parquet(out_works, index=False, compression=CONFIG["storage"]["compression"])

    tagged = per_work["work_id"].nunique()
    title_only_tagged = per_work[per_work["text_basis"] == "title_only"]["work_id"].nunique()
    lines = [
        f"- method: **16 separate per-SDG passes, VocTagger defaults** "
        f"(`lemmatize_vocabulary={tagger_params['lemmatize_vocabulary']}`, "
        f"`sentence_extras={tagger_params['sentence_extras']}`, `threshold={tagger_params['threshold']}`, "
        f"`interword_threshold={tagger_params['interword_threshold']}`) — D19",
        f"- works tagged: **{tagged:,}** of {len(frame):,} (**{tagged/len(frame):.1%}**) · "
        f"v1 tagged 4,486 of 28,094 (16.0%)",
        f"- work-SDG pairs: **{len(per_work):,}** · mean **{len(per_work)/max(tagged,1):.2f}** SDGs per "
        f"tagged work (v1: 1.50)",
        f"- keyword hits: {len(hits):,}",
        f"- title-only works tagged: **{title_only_tagged:,}** of "
        f"{int((frame['text_basis'] == 'title_only').sum()):,} "
        f"({title_only_tagged/max(int((frame['text_basis'] == 'title_only').sum()),1):.1%}) — G5c keeps "
        f"them, flagged via `text_basis`",
        "",
        "| SDG | Works tagged |",
        "|---|---|",
    ]
    for number, count in per_work.groupby("sdg")["work_id"].nunique().sort_values(ascending=False).items():
        lines.append(f"| SDG {number} | {count:,} |")

    report = ROOT / CONFIG["paths"]["reports"] / "sdg_siris_tagging.md"
    report.write_text("# SDG tagging — SIRIS controlled vocabulary\n\n" + "\n".join(lines) + "\n",
                      encoding="utf-8")
    Manifest(snapshot).record_step(
        "52_sdg_tag",
        counts={"works_tagged": int(tagged), "work_sdg_pairs": len(per_work), "keyword_hits": len(hits),
                "title_only_tagged": int(title_only_tagged)},
        files=[out_hits, out_works, vocab],
        params={"method": "16_per_sdg_passes_defaults", **tagger_params,
                "min_keyword_hits": SDG["text"]["min_keyword_hits"], "nshards": args.nshards,
                "vocabulary_archived": str(vocab.relative_to(snapshot))},
        notes="D19: combined vocabulary is NOT equivalent (188 vs 194 hits, strict subset).",
    )
    append_summary(snapshot, "52_sdg_tag", lines[:5])
    print("\n".join(lines))
    print(f"\nwrote {out_hits.name}, {out_works.name} and {report}")


if __name__ == "__main__":
    main()
