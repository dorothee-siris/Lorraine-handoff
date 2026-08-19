"""12b_pull_taxonomy.py -- pull the complete OpenAlex taxonomy dictionary (D59).

`all_topics.parquet` is the positional decoder for every per-subfield blob in `ul_labs`:
`lib/helpers.get_subfields_for_field()` returns `sorted(subfields of a field)` and every
"Pubs per subfield within X (id: N)" blob is decoded against that list, positionally. If the
dictionary were built from the corpus instead of pulled complete, any field whose subfields are
not all represented in the corpus would yield a SHORT list and shift every value after the gap --
exactly the indexed-field misalignment class that hit v1 on 51.4% of works (D34).

Stream A's contract (docs/data_contract.yaml) originally proposed freezing v1's deployed
`all_topics.parquet` as a third manual input (Open risk 2). The orchestrator's D59 ruling
supersedes that: a frozen third manual file would break the "only two manual inputs" framing,
and a fresh pull costs ~23 list calls (~$0.002) -- cheaper than the ambiguity. So this script pulls
OpenAlex's `/topics` list endpoint (each topic record carries its own subfield/field/domain), not
`/domains` + `/fields` + `/subfields` + `/topics` separately -- one endpoint has everything.

Archived to the snapshot's raw/ (compressed per config.storage), so a re-run is free and the pull
is auditable. Idempotent: reruns overwrite tables/all_topics.parquet and raw/topics.jsonl(.zst).

Usage
  python pipeline/12b_pull_taxonomy.py --calibrate      # 1 page, inspect, nothing durable
  python pipeline/12b_pull_taxonomy.py                  # full pull (~23 calls), writes the table
  python pipeline/12b_pull_taxonomy.py --snapshot 2026-08-11
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.openalex import OpenAlexClient, ascii_safe_stdout, load_env, short_id  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot, sha256  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)

SELECT = "id,display_name,domain,field,subfield,keywords"


def parse_topic(rec: dict) -> dict:
    domain = rec.get("domain") or {}
    field = rec.get("field") or {}
    subfield = rec.get("subfield") or {}
    return {
        "domain_id": int(short_id(domain.get("id")) or 0),
        "domain_name": domain.get("display_name"),
        "field_id": int(short_id(field.get("id")) or 0),
        "field_name": field.get("display_name"),
        "subfield_id": int(short_id(subfield.get("id")) or 0),
        "subfield_name": subfield.get("display_name"),
        "topic_id": short_id(rec.get("id")),
        "topic_name": rec.get("display_name"),
        "keywords": "|".join(rec.get("keywords") or []),
    }


def crawl_topics(client: OpenAlexClient, limit: int | None = None) -> list[dict]:
    """`/topics` has no per-institution filter -- it is the whole dictionary, always."""
    records: list[dict] = []
    cursor = "*"
    page_n = 0
    while cursor:
        page = client.get("/topics", per_page=CONFIG["openalex"]["per_page"], cursor=cursor, select=SELECT)
        results = page["results"]
        if not results:
            break
        records.extend(results)
        cursor = page["meta"].get("next_cursor")
        page_n += 1
        print(f"  page {page_n}: {len(records):,} / {page['meta']['count']:,} topics")
        if limit and len(records) >= limit:
            print(f"  stopping at calibration limit {limit}")
            return records[:limit]
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--calibrate", action="store_true", help="1 page, inspect, nothing durable")
    args = parser.parse_args()

    env = load_env(CONFIG["secrets"]["env_file"], CONFIG["secrets"]["required"])
    client = OpenAlexClient(CONFIG, env)

    if args.calibrate:
        print("CALIBRATION -- 1 page of /topics, no snapshot write\n")
        page = client.get("/topics", per_page=25, cursor="*", select=SELECT)
        print(f"meta.count (total topics in OpenAlex): {page['meta']['count']:,}")
        parsed = [parse_topic(r) for r in page["results"][:5]]
        for row in parsed:
            print(row)
        pages_needed = -(-page["meta"]["count"] // CONFIG["openalex"]["per_page"])
        print(f"\nfull pull projection: ~{pages_needed} calls at per_page={CONFIG['openalex']['per_page']}")
        print(f"calibration used {client.calls} API calls.")
        return

    snapshot = resolve_snapshot(CONFIG, args.snapshot)
    raw_path = snapshot / "raw" / "topics.jsonl"

    records = crawl_topics(client)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
    raw_sha = sha256(raw_path)
    raw_bytes = raw_path.stat().st_size

    frame = pd.DataFrame([parse_topic(r) for r in records]).drop_duplicates("topic_id")
    frame = frame.sort_values(["domain_id", "field_id", "subfield_id", "topic_id"]).reset_index(drop=True)

    out = snapshot / "tables" / "all_topics.parquet"
    frame.to_parquet(out, index=False, compression=CONFIG["storage"]["compression"])

    n_domains = frame["domain_id"].nunique()
    n_fields = frame["field_id"].nunique()
    n_subfields = frame["subfield_id"].nunique()
    lines = [
        f"- pulled the complete OpenAlex `/topics` dictionary: **{len(frame):,}** topics, "
        f"{n_domains} domains, {n_fields} fields, {n_subfields} subfields",
        f"- API calls: **{client.calls}**",
        f"- this is the positional decoder for every per-subfield blob (ul_labs, ul_partners_base): "
        f"a field's subfields must all be present or the blob shifts (the D34 defect class)",
    ]

    storage = CONFIG["storage"]
    if storage.get("compress_raw_jsonl"):
        import zstandard

        compressor = zstandard.ZstdCompressor(level=storage.get("raw_compression_level", 10))
        target = raw_path.with_suffix(raw_path.suffix + ".zst")
        with raw_path.open("rb") as source, target.open("wb") as sink:
            compressor.copy_stream(source, sink)
        raw_path.unlink()
        print(f"compressed raw -> {target.name} ({target.stat().st_size/1e6:.2f} MB, "
              f"was {raw_bytes/1e6:.2f} MB)")

    Manifest(snapshot).record_step(
        "12b_pull_taxonomy",
        select=SELECT,
        api_base=CONFIG["openalex"]["base_url"],
        api_calls=client.calls,
        counts={"topics": len(frame), "domains": n_domains, "fields": n_fields, "subfields": n_subfields},
        files=[out],
        params={"raw_jsonl_sha256_uncompressed": raw_sha, "raw_jsonl_bytes_uncompressed": raw_bytes},
        notes="D59: complete /topics dictionary, not a corpus aggregate; supersedes the "
              "frozen-v1-file plan in docs/data_contract.yaml Open risk 2.",
    )
    append_summary(snapshot, "12b_pull_taxonomy", lines)
    print("\n".join(lines))
    print(f"\nwrote {out.name}")


if __name__ == "__main__":
    main()
