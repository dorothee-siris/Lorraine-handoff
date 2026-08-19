#!/usr/bin/env python3
"""
openaire.py — OpenAIRE Graph API harvester (cursor pagination).

Canonical version of the connector proven in the Ifremer project. Scopes by an
OpenAIRE canonical organisation id + type + publication-date window, and cursor-
pages the Graph v1 API. Optional bearer token (OPENAIRE_TOKEN in ~/.siris/.env);
anonymous works for most pulls.

Reuse recipe:
  1. Copy common.py + openaire.py into your project's scripts/.
  2. Edit CONFIG (org_id, years, out_dir). Find org_id via
     https://api.openaire.eu/graph/v1/organizations?search=<name> (openorgs____:: id).
  3. Run:  python openaire.py       (resumes if interrupted)

OpenAIRE AGGREGATES Crossref/OpenAlex/HAL/DataCite/national repositories, so its
main use is the NET-NEW test (does it add DOIs beyond your other sources?) plus
abstract/ORCID coverage. Parsing helpers below mirror the Ifremer lib_openaire:
DOIs are NOT in the (often-null) `pids` field — they sit in instances[].urls.
"""
from __future__ import annotations

import argparse
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlencode

import common

CONFIG = {
    "api_endpoint": "https://api.openaire.eu/graph/v1/researchProducts",
    "org_id": "openorgs____::a6bfaa7b9934dd8459ca94deac34c127",  # <-- Ifremer example
    "type": "publication",
    "year_start": 2015,
    "year_end": 2025,
    "out_dir": "data/openaire/raw",
    "page_size": 100,
    "req_per_sec": 2,
    "max_retries": 5,
    "request_timeout": 120,
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] | %(message)s")
log = logging.getLogger("openaire")


def make_session(cfg: dict):
    headers = {"Accept": "application/json"}
    tok = common.get_secret("OPENAIRE_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    return common.make_session(max_retries=cfg["max_retries"], backoff_factor=2.0,
                               user_agent=common.default_user_agent(
                                   common.get_secret("OPENALEX_MAILTO"), "SIRIS-connectors/openaire"),
                               headers=headers, pool=8)


def harvest(cfg: dict, resume: bool) -> None:
    out_dir = Path(cfg["out_dir"]); out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "records.jsonl"
    ckpt = out_dir / ".cursor.txt"
    manifest = out_dir / "_harvest_manifest.json"
    gz = out_file.with_suffix(out_file.suffix + ".gz")

    y0, y1 = cfg["year_start"], cfg["year_end"]
    delay = 1.0 / max(cfg["req_per_sec"], 0.1)
    session = make_session(cfg)

    base = [
        ("relOrganizationId", cfg["org_id"]),
        ("type", cfg["type"]),
        ("fromPublicationDate", f"{y0}-01-01"),
        ("toPublicationDate", f"{y1}-12-31"),
        ("pageSize", str(cfg["page_size"])),
    ]

    cursor, mode, count = "*", "wb", 0
    saved = common.load_checkpoint(ckpt)
    if resume and saved == "DONE" and (out_file.exists() or gz.exists()):
        log.info("Harvest already complete (checkpoint DONE) — nothing to do.")
        return
    if resume and saved and saved != "DONE" and out_file.exists():
        cursor, mode = saved, "ab"
        count = common.count_lines(out_file)
        log.info(f"Resuming from saved cursor at {count} records")

    num_found, page = None, 0
    with open(out_file, mode) as f:
        while True:
            url = f"{cfg['api_endpoint']}?{urlencode(base + [('cursor', cursor)])}"
            r = session.get(url, timeout=cfg["request_timeout"]); r.raise_for_status()
            data = r.json()
            hdr = data.get("header", {})
            if num_found is None:
                num_found = hdr.get("numFound")
            results = data.get("results") or []
            for rec in results:
                f.write(common.dumps(rec)); f.write(b"\n"); count += 1
            f.flush()
            next_cursor = hdr.get("nextCursor")
            page += 1
            log.info(f"page {page}: +{len(results)} -> {count}" + (f" / {num_found}" if num_found else ""))
            if not results or not next_cursor or next_cursor == cursor:
                common.save_checkpoint(ckpt, None)  # DONE
                break
            cursor = next_cursor
            common.save_checkpoint(ckpt, cursor)
            time.sleep(delay)

    common.write_manifest(manifest, {
        "source": "openaire", "endpoint": cfg["api_endpoint"], "org_id": cfg["org_id"],
        "filter": f"relOrganizationId={cfg['org_id']}, type={cfg['type']}, {y0}-{y1}",
        "num_found_reported": num_found, "total_records_written": count,
    })
    log.info(f"Done: {count} records (reported numFound={num_found}) -> {out_file}")


# ---------------------------------------------------------------------------
# Parsing helpers (use at the format step, over common.read_jsonl(out_file))
# ---------------------------------------------------------------------------
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.I)


def extract_doi(rec: dict) -> str | None:
    """DOI from pids if present, else from instances[].urls (doi.org links)."""
    for p in rec.get("pids") or []:
        if str(p.get("scheme", "")).lower() == "doi" and p.get("value"):
            m = _DOI_RE.search(p["value"])
            if m:
                return m.group(0).rstrip(".").lower()
    for ins in rec.get("instances") or []:
        for u in ins.get("urls") or []:
            if "doi.org/" in u:
                m = _DOI_RE.search(u)
                if m:
                    return m.group(0).rstrip(".").lower()
    return None


def abstract_of(rec: dict) -> str | None:
    ds = [d for d in (rec.get("descriptions") or []) if isinstance(d, str) and d.strip()]
    return max(ds, key=len) if ds else None


def n_orcid_authors(rec: dict) -> int:
    n = 0
    for a in rec.get("authors") or []:
        pid = (a.get("pid") or {}).get("id") or {}
        if str(pid.get("scheme", "")).lower().startswith("orcid"):
            n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Harvest research products from OpenAIRE Graph.")
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args()
    harvest(CONFIG, resume=not args.no_resume)


if __name__ == "__main__":
    main()
