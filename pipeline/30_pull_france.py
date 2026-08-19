"""30_pull_france.py — the French document-level citation corpus (FWCI/PPtop denominator).

Replaces v1's single largest manual dependency: `data_citations_france_19_23.parquet`, a
colleague-supplied dump this project could never regenerate. Pulling it from the API is what makes
the client autonomous (D5) — no BigQuery, which would reintroduce a dependency they cannot run.

Deliberately minimal `select` (5 fields): this table is only ever used to compute a stratum mean and
two percentiles, so anything else is dead weight at ~1.1 M rows.

Doc types MIRROR corpus_filter.doc_types_keep — including conference-paper per D36. If the two lists
ever diverge, the denominator is scoped differently from the numerator it normalises, which silently
biases every indicator. The run asserts they match.

Usage
  python pipeline/30_pull_france.py --calibrate      # gate G3: 2019 only, report count/size/time
  python pipeline/30_pull_france.py                  # all years, resumable per year
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.openalex import OpenAlexClient, ascii_safe_stdout, load_env, short_id  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot, sha256  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)
FB = CONFIG["france_baseline"]
SELECT = ",".join(FB["select"])


def year_filter(year: int) -> str:
    """Note: from/to_publication_date, not publication_year — the proven MESRE crawl pattern."""
    return (
        f"{FB['country_filter']},"
        f"type:{'|'.join(FB['doc_types'])},"
        f"from_publication_date:{year}-01-01,"
        f"to_publication_date:{year}-12-31"
    )


def parse_record(work: dict) -> dict:
    """Keep 5 scalars. `primary_topic` is requested whole because asking for nested ids is unreliable."""
    topic = work.get("primary_topic") or {}
    return {
        "work_id": short_id(work.get("id")),
        "cited_by_count": work.get("cited_by_count"),
        "publication_year": work.get("publication_year"),
        "type": work.get("type"),
        "subfield_id": short_id((topic.get("subfield") or {}).get("id")),
        "field_id": short_id((topic.get("field") or {}).get("id")),
    }


def iter_raw(path: Path):
    compressed = path.with_suffix(path.suffix + ".zst")
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)
    elif compressed.exists():
        import zstandard

        with compressed.open("rb") as raw, zstandard.ZstdDecompressor().stream_reader(raw) as stream:
            for line in io.TextIOWrapper(stream, encoding="utf-8"):
                if line.strip():
                    yield json.loads(line)
    else:
        raise SystemExit(f"missing France shard {path}")


def crawl_year(client: OpenAlexClient, snapshot: Path, year: int) -> tuple[Path, float, int]:
    out_path = snapshot / "raw" / f"france_{year}.jsonl"
    cursor_path = snapshot / "raw" / f"france_{year}.cursor"
    if cursor_path.exists() and cursor_path.read_text(encoding="utf-8").strip() == "DONE":
        print(f"  {year}: already complete")
        return out_path, 0.0, 0
    started = time.monotonic()
    mode = "a" if cursor_path.exists() and out_path.exists() else "w"
    written = 0
    with out_path.open(mode, encoding="utf-8") as handle:
        for page in client.crawl(year_filter(year), SELECT, cursor_file=cursor_path,
                                 label=f"FR {year}", log_every=50):
            for work in page:
                handle.write(json.dumps(work, ensure_ascii=False) + "\n")
                written += 1
    return out_path, time.monotonic() - started, written


def to_parquet(snapshot: Path, year: int) -> Path:
    """Convert one raw shard to zstd parquet immediately (D18), keeping only the 6 parsed columns."""
    raw_path = snapshot / "raw" / f"france_{year}.jsonl"
    rows = [parse_record(work) for work in iter_raw(raw_path)]
    frame = pd.DataFrame(rows).drop_duplicates("work_id")
    target = snapshot / "tables" / f"france_{year}.parquet"
    frame.to_parquet(target, index=False, compression=CONFIG["storage"]["compression"])
    return target


def compress_raw(path: Path) -> None:
    if not (CONFIG["storage"].get("compress_raw_jsonl") and path.exists()):
        return
    import zstandard

    target = path.with_suffix(path.suffix + ".zst")
    compressor = zstandard.ZstdCompressor(level=CONFIG["storage"].get("raw_compression_level", 10))
    with path.open("rb") as src, target.open("wb") as dst:
        compressor.copy_stream(src, dst)
    path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--calibrate", action="store_true", help="gate G3: the calibration year only")
    parser.add_argument("--year", type=int, action="append")
    args = parser.parse_args()

    # The scope-mirror invariant: denominator doc types must equal numerator doc types (D36).
    assert set(FB["doc_types"]) == set(CONFIG["corpus_filter"]["doc_types_keep"]), (
        f"France doc types {FB['doc_types']} != corpus doc types "
        f"{CONFIG['corpus_filter']['doc_types_keep']} — the baseline would be scoped differently "
        f"from the corpus it normalises"
    )
    assert not CONFIG["corpus_filter"]["apply_indexed_in_crossref"], "D25: no crossref filter"

    env = load_env(CONFIG["secrets"]["env_file"], CONFIG["secrets"]["required"])
    client = OpenAlexClient(CONFIG, env)
    snapshot = resolve_snapshot(CONFIG, args.snapshot)
    all_years = list(range(CONFIG["window"]["year_from"], CONFIG["window"]["year_to"] + 1))
    years = [FB["calibration_year"]] if args.calibrate else (args.year or all_years)
    print(f"snapshot {snapshot.name}: France baseline for {years}")
    print(f"  select: {SELECT}")
    print(f"  doc types (mirroring the corpus): {FB['doc_types']}")

    measured: list[dict] = []
    for year in years:
        raw_path, elapsed, written = crawl_year(client, snapshot, year)
        parquet = to_parquet(snapshot, year)
        raw_mb = raw_path.stat().st_size / 1e6 if raw_path.exists() else 0.0
        digest = sha256(raw_path) if raw_path.exists() else None
        compress_raw(raw_path)
        rows = pd.read_parquet(parquet, columns=["work_id"]).shape[0]
        measured.append({
            "year": year, "works": rows, "minutes": round(elapsed / 60, 1),
            "raw_mb": round(raw_mb, 1),
            "parquet_mb": round(parquet.stat().st_size / 1e6, 1),
            "raw_sha256": digest,
        })
        print(f"  {year}: {rows:,} works · {elapsed/60:.1f} min · raw {raw_mb:.0f} MB · "
              f"parquet {parquet.stat().st_size/1e6:.1f} MB")

    calls = client.calls
    cost = calls * 0.10 / 1000
    lines = [
        f"- years pulled this run: {', '.join(str(m['year']) for m in measured)}",
        f"- OpenAlex list calls: **{calls:,}** ⇒ **${cost:.3f}** at $0.10/1k",
        f"- expected total for the window (measured 2026-08-11): **{FB['expected_total_works']:,}** works",
        "",
        "| Year | Works | Minutes | Raw MB | Parquet MB |",
        "|---|---|---|---|---|",
    ]
    for m in measured:
        lines.append(f"| {m['year']} | {m['works']:,} | {m['minutes']} | {m['raw_mb']} | {m['parquet_mb']} |")

    if args.calibrate:
        one = measured[0]
        projected_calls = calls * len(all_years)
        lines += [
            "",
            "### Gate G3 projection from the calibration year",
            f"- projected calls for {len(all_years)} years: **~{projected_calls:,}** ⇒ "
            f"**~${projected_calls * 0.10 / 1000:.2f}**",
            f"- projected wall-clock: **~{one['minutes'] * len(all_years):.0f} min**",
            f"- projected parquet: **~{one['parquet_mb'] * len(all_years):.0f} MB** "
            f"(+ ~{one['raw_mb'] * len(all_years) / 10:.0f} MB of compressed raw)",
            "- gates: $1/day API, $50/step, 1M tokens — none approached.",
        ]

    report = ROOT / CONFIG["paths"]["reports"] / ("g3_france_calibration.md" if args.calibrate
                                                  else "france_pull.md")
    report.write_text("# France baseline pull\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    # One manifest entry PER SHARD. A shared key would let each parallel year-process overwrite the
    # previous one's entry, leaving the manifest describing only the last year to finish — which is
    # exactly what happened on the first sharded run and what the manifest-coverage test caught.
    Manifest(snapshot).record_step(
        "30_pull_france_" + "_".join(str(m["year"]) for m in measured),
        filters={str(m["year"]): year_filter(m["year"]) for m in measured},
        select=SELECT,
        api_base=CONFIG["openalex"]["base_url"],
        api_calls=calls,
        counts={str(m["year"]): m["works"] for m in measured},
        files=[snapshot / "tables" / f"france_{m['year']}.parquet" for m in measured],
        params={"doc_types": FB["doc_types"], "per_page": CONFIG["openalex"]["per_page"],
                "apply_indexed_in_crossref": False, "shards": measured},
        notes="Replaces v1's colleague-supplied France dump; minimal select by design.",
    )
    append_summary(snapshot, "30_pull_france", lines[:3])
    print("\n".join(lines))


if __name__ == "__main__":
    main()
