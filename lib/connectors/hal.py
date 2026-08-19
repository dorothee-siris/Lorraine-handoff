#!/usr/bin/env python3
"""
hal.py — HAL harvester (Solr search API, cursorMark deep-paging).

Canonical version of the connector proven in the Ifremer project. Scopes by a HAL
structure id + a publication-year range (HAL's publicationDateY_i is a real pub
year, unlike OAI datestamps), and deep-pages with cursorMark. No auth needed.

Reuse recipe:
  1. Copy common.py + hal.py into your project's scripts/.
  2. Edit CONFIG (struct_id, years, out_dir). Find struct_id on the lab's HAL page
     or via https://api.archives-ouvertes.fr/ref/structure/?q=<name>.
  3. Run:  python hal.py           (resumes if interrupted)

Wide `fl` so downstream never re-queries — notably abstract_s (full text, no
reconstruction), doiId_s (bare DOI), and the disambiguation fields authIdHal_s /
authORCIDIdExt_s. Doc-type policy is applied downstream on docType_s.
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from urllib.parse import urlencode

import common

CONFIG = {
    "api_endpoint": "https://api.archives-ouvertes.fr/search/",
    "struct_id": 300022,            # <-- Ifremer example; change per project
    "year_start": 2015,
    "year_end": 2025,
    "out_dir": "data/hal/raw",
    "rows_per_page": 1000,
    "req_per_sec": 3,
    "max_retries": 5,
    "request_timeout": 90,
}

# Wide field list — comparability + idHAL/ORCID disambiguation.
FL = ",".join([
    "docid", "halId_s", "uri_s", "doiId_s",
    "title_s", "subTitle_s", "abstract_s", "keyword_s",
    "authFullName_s", "authIdHal_s", "authIdHal_i", "authORCIDIdExt_s",
    "structId_i", "labStructId_i", "instStructId_i",
    "docType_s", "publicationDateY_i", "publicationDate_s", "producedDateY_i",
    "language_s", "journalTitle_s",
])

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] | %(message)s")
log = logging.getLogger("hal")


def harvest(cfg: dict, resume: bool) -> None:
    out_dir = Path(cfg["out_dir"]); out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "records.jsonl"
    ckpt = out_dir / ".cursor_mark.txt"
    manifest = out_dir / "_harvest_manifest.json"
    gz = out_file.with_suffix(out_file.suffix + ".gz")

    y0, y1 = cfg["year_start"], cfg["year_end"]
    delay = 1.0 / max(cfg["req_per_sec"], 0.1)
    session = common.make_session(max_retries=cfg["max_retries"], backoff_factor=2.0,
                                  user_agent=common.default_user_agent(
                                      common.get_secret("OPENALEX_MAILTO"), "SIRIS-connectors/hal"),
                                  pool=8)

    base = [
        ("q", "*:*"),
        ("fq", f"structId_i:{cfg['struct_id']}"),
        ("fq", f"publicationDateY_i:[{y0} TO {y1}]"),
        ("fl", FL),
        ("rows", str(cfg["rows_per_page"])),
        ("sort", "docid asc"),
        ("wt", "json"),
    ]

    cursor, mode, count = "*", "wb", 0
    saved = common.load_checkpoint(ckpt)
    if resume and saved == "DONE" and (out_file.exists() or gz.exists()):
        log.info("Harvest already complete (checkpoint DONE) — nothing to do.")
        return
    if resume and saved and saved != "DONE" and out_file.exists():
        cursor, mode = saved, "ab"
        count = common.count_lines(out_file)
        log.info(f"Resuming from saved cursorMark at {count} records")

    num_found, page = None, 0
    with open(out_file, mode) as f:
        while True:
            url = f"{cfg['api_endpoint']}?{urlencode(base + [('cursorMark', cursor)])}"
            r = session.get(url, timeout=cfg["request_timeout"]); r.raise_for_status()
            data = r.json()
            resp = data.get("response", {})
            if num_found is None:
                num_found = resp.get("numFound")
            docs = resp.get("docs", []) or []
            for d in docs:
                f.write(common.dumps(d)); f.write(b"\n"); count += 1
            f.flush()
            next_cursor = data.get("nextCursorMark")
            page += 1
            log.info(f"page {page}: +{len(docs)} -> {count}" + (f" / {num_found}" if num_found else ""))
            # HAL signals the end when the cursor stops advancing.
            if not next_cursor or next_cursor == cursor or not docs:
                common.save_checkpoint(ckpt, None)  # DONE
                break
            cursor = next_cursor
            common.save_checkpoint(ckpt, cursor)
            time.sleep(delay)

    common.write_manifest(manifest, {
        "source": "hal", "endpoint": cfg["api_endpoint"], "struct_id": cfg["struct_id"],
        "filter": f"structId_i:{cfg['struct_id']}, publicationDateY_i:[{y0} TO {y1}]",
        "num_found_reported": num_found, "total_records_written": count, "fields": FL,
    })
    log.info(f"Done: {count} records (reported numFound={num_found}) -> {out_file}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Harvest records from HAL (Solr, cursorMark).")
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args()
    harvest(CONFIG, resume=not args.no_resume)


if __name__ == "__main__":
    main()
