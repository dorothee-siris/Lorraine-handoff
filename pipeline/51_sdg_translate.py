"""51_sdg_translate.py — FR->EN translation of the text that will be tagged.

Non-negotiable, and quantified: the JRC vocabulary is English, so French text tagged untranslated
loses most of its recall. On the §8.2 grid, French works scored **48% coverage translated vs 9%
untranslated** (v1-tagged French stratum: 92% -> 18%), while English works scored 49% either way —
exactly the null effect that validates the comparison.

**Must run under the `topic_modeling` interpreter**, not base: base torch raises a DLL error on this
box. See `config.yaml: interpreters.translation`.

    "C:/Users/Theodore/anaconda3/envs/topic_modeling/python.exe" pipeline/51_sdg_translate.py

Resumable in blocks: translations are appended to a JSONL cache keyed by work_id, so an interrupted
run re-translates nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent.parent.parent / "Tools" / "translate-mt"))
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

CONFIG = load_config(ROOT)
BLOCK = 500


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--limit", type=int, help="calibration: translate only this many")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    frame = pd.read_parquet(tables / "sdg_text.parquet")
    todo_all = frame[frame["needs_translation"] & frame["text"].str.len().gt(0)]
    print(f"snapshot {snapshot.name}: {len(frame):,} works · {len(todo_all):,} flagged for FR->EN")

    cache_path = ROOT / "cache" / "translation" / "fr_en.jsonl"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    done: dict[str, str] = {}
    if cache_path.exists():
        with cache_path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                done[record["work_id"]] = record["text_en"]
        print(f"  {len(done):,} translations already cached")

    todo = todo_all[~todo_all["work_id"].isin(done)]
    if args.limit:
        todo = todo.head(args.limit)
    print(f"  to translate now: {len(todo):,}")

    if len(todo):
        from translate import translate_texts

        with cache_path.open("a", encoding="utf-8") as handle:
            for start in range(0, len(todo), BLOCK):
                block = todo.iloc[start : start + BLOCK]
                translated = translate_texts(
                    block["text"].tolist(),
                    batch_size=32,
                    max_words=220,          # opus-mt truncates ~512 tokens; the module chunks internally
                    show_progress=False,
                )
                for work_id, text_en in zip(block["work_id"], translated):
                    handle.write(json.dumps({"work_id": work_id, "text_en": text_en},
                                            ensure_ascii=False) + "\n")
                    done[work_id] = text_en
                handle.flush()
                print(f"    {min(start + BLOCK, len(todo)):,} / {len(todo):,} translated", flush=True)

    # text_to_tag = the English text where we have one, the original otherwise
    frame["text_en"] = frame["work_id"].map(done)
    frame["translated"] = frame["text_en"].notna()
    frame["text_to_tag"] = frame["text_en"].where(frame["translated"], frame["text"])
    frame["text_to_tag_words"] = frame["text_to_tag"].fillna("").str.split().str.len()

    out = tables / "sdg_text_ready.parquet"
    frame.to_parquet(out, index=False, compression=CONFIG["storage"]["compression"])

    lines = [
        f"- works flagged French (posterior >= {CONFIG['sdg']['language_id']['french_threshold']}): "
        f"**{len(todo_all):,}** ({len(todo_all)/len(frame):.1%} of the corpus)",
        f"- translated: **{int(frame['translated'].sum()):,}** · left in the original language "
        f"{int((~frame['translated']).sum()):,}",
        f"- Phase 1 translated 5,743 works; this corpus needs **{len(todo_all):,}** because D36 added "
        f"conference papers, which are largely French HAL deposits",
        f"- mean text length to tag: {frame['text_to_tag_words'].mean():.0f} words",
    ]
    report = ROOT / CONFIG["paths"]["reports"] / "sdg_translation.md"
    report.write_text("# FR->EN translation for SDG tagging\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    Manifest(snapshot).record_step(
        "51_sdg_translate",
        counts={"flagged_french": len(todo_all), "translated": int(frame["translated"].sum())},
        files=[out],
        params={"model": CONFIG["sdg"]["translation"]["model"],
                "backend": CONFIG["sdg"]["translation"]["backend"],
                "max_words_per_chunk": 220, "batch_size": 32,
                "interpreter": CONFIG["interpreters"]["translation"]},
        notes="Worth 48% vs 9% SDG coverage on French works; cache is resumable per work_id.",
    )
    append_summary(snapshot, "51_sdg_translate", lines)
    print("\n".join(lines))
    print(f"\nwrote {out.name} and {report}")


if __name__ == "__main__":
    main()
