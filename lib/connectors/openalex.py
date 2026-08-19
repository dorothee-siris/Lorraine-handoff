#!/usr/bin/env python3
"""
openalex.py — OpenAlex works downloader + quick-count helper.

Canonical version of the connector proven in the Ifremer and La Réunion projects.
Full-record download (raw JSONL, resumable, rate-limited, parallel) for building a
corpus, PLUS a lightweight count() / group_by helper for quick benchmarking.

Reuse recipe:
  1. Copy common.py + openalex.py into your project's scripts/.
  2. Edit the CONFIG block below (entities, years, output dir).
  3. Run:  python openalex.py            # full download
           python openalex.py --count    # just print counts, no download

Credentials (OPENALEX_API_KEY, OPENALEX_MAILTO) come from ~/.siris/.env via
common.get_secret — never hardcode them here.

============================ THE COUNTING GOTCHA ============================
Filter by  authorships.institutions.id:<ror-or-oaid>   (DIRECT) — this module's
default. NEVER filter by  lineage:  for French institutions: lineage traverses
OpenAlex's descendant graph and grafts entire partner portfolios (e.g. IRD's
whole output) onto a parent through a shared UMR/UAR — inflated 8x+. The
institution object's `works_count` field is a stale cache; ignore it. The direct
count is the reproducible, peer-symmetric benchmark denominator.
============================================================================
"""
from __future__ import annotations

import argparse
import logging
import re
import time
from itertools import product
from pathlib import Path
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed

import common

# ---------------------------------------------------------------------------
# CONFIG — edit this block per project
# ---------------------------------------------------------------------------
CONFIG = {
    # Entities to crawl. Each = {slug, name, ids:[...]}. Multiple ids are OR-ed.
    # Use OpenAlex institution IDs (I…) or ROR ids. Add peers as more entities.
    "entities": [
        {"slug": "example", "name": "Example Institution", "ids": ["I154202486"]},
    ],
    "year_start": 2015,
    "year_end": 2025,

    # DIRECT institutional filter (see gotcha above). Only change if you know why.
    "filter_field": "authorships.institutions.id",   # NOT "authorships.institutions.lineage"

    # Extra filter clauses appended verbatim, e.g. to restrict types at query time.
    # Leave empty for a BROAD pull (recommended: filter doc-types downstream).
    "extra_filters": [],   # e.g. ["type:article|review", "has_doi:true"]

    "out_dir": "data/openalex/raw",

    # Throughput. Polite pool is fine to ~20 req/s; with an API key you can go higher.
    "req_per_sec": 20,
    "workers": 16,
    "per_page": 200,
    "max_retries": 5,
    "request_timeout": 60,
}

# OpenAlex work fields — wide, so downstream never re-queries. Trim if you want
# smaller files, but abstract_inverted_index + authorships are usually essential.
SELECTED_FIELDS = [
    "id", "doi", "title",
    "publication_year", "publication_date", "language", "type",
    "open_access",
    "authorships",                     # authors, ORCID, institutions (id/ror/country/type)
    "primary_topic", "topics",
    "abstract_inverted_index",         # -> common.reconstruct_abstract()
    "fwci", "citation_normalized_percentile", "cited_by_count",
    "sustainable_development_goals",
    "is_retracted",
]

BASE_URL = "https://api.openalex.org/works"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(threadName)s | %(message)s")
log = logging.getLogger("openalex")


# ---------------------------------------------------------------------------
# Session / params
# ---------------------------------------------------------------------------
def make_session(cfg: dict):
    mailto = common.get_secret("OPENALEX_MAILTO")
    headers = {}
    key = common.get_secret("OPENALEX_API_KEY")
    if key and not key.startswith("PASTE_"):
        headers["Authorization"] = f"Bearer {key}"
    return common.make_session(
        max_retries=cfg["max_retries"],
        user_agent=common.default_user_agent(mailto, "SIRIS-connectors/openalex"),
        headers=headers,
        pool=64,
    )


def build_filter(entity_ids: list[str], year: int, cfg: dict) -> str:
    ids = "|".join(entity_ids)
    clauses = [
        f"{cfg['filter_field']}:{ids}",
        f"from_publication_date:{year}-01-01",
        f"to_publication_date:{year}-12-31",
    ]
    clauses += list(cfg.get("extra_filters") or [])
    return ",".join(clauses)


def _base_params(entity_ids: list[str], year: int, cfg: dict) -> dict:
    return {
        "filter": build_filter(entity_ids, year, cfg),
        "select": ",".join(SELECTED_FIELDS),
        "per_page": str(cfg["per_page"]),
        "mailto": common.get_secret("OPENALEX_MAILTO"),
    }


def fetch_page(session, bucket, cursor, base_params, timeout):
    params = dict(base_params, cursor=cursor)
    bucket.acquire()
    r = session.get(f"{BASE_URL}?{urlencode(params)}", timeout=timeout)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Quick counts (no download) — the fast benchmarking path
# ---------------------------------------------------------------------------
def count(filter_str: str) -> int:
    """Return meta.count for an arbitrary OpenAlex filter string."""
    s = make_session(CONFIG)
    params = {"filter": filter_str, "per_page": 1, "mailto": common.get_secret("OPENALEX_MAILTO")}
    r = s.get(f"{BASE_URL}?{urlencode(params)}", timeout=CONFIG["request_timeout"])
    r.raise_for_status()
    return r.json()["meta"]["count"]


def group_by(filter_str: str, key: str = "publication_year") -> list[dict]:
    """Server-side group_by (e.g. by year) without paging through records.

    per_page caps the number of GROUPS returned (not records), so request the max
    (200) — with per_page=1 OpenAlex returns only a single group.
    """
    s = make_session(CONFIG)
    params = {"filter": filter_str, "group_by": key, "per_page": 200,
              "mailto": common.get_secret("OPENALEX_MAILTO")}
    r = s.get(f"{BASE_URL}?{urlencode(params)}", timeout=CONFIG["request_timeout"])
    r.raise_for_status()
    return r.json().get("group_by", [])


# ---------------------------------------------------------------------------
# Download one (entity, year) unit, with resume
# ---------------------------------------------------------------------------
def download_unit(entity: dict, year: int, cfg: dict, bucket, resume: bool) -> int:
    out_dir = Path(cfg["out_dir"]) / entity["slug"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"pubs_{entity['slug']}_{year}.jsonl"
    ckpt_file = out_dir / f".cursor_{year}.txt"
    session = make_session(cfg)
    params = _base_params(entity["ids"], year, cfg)
    timeout = cfg["request_timeout"]

    cursor, mode, cnt = "*", "wb", 0
    if resume:
        saved = common.load_checkpoint(ckpt_file)
        if saved == "DONE" and out_file.exists():
            n = common.count_lines(out_file)
            log.info(f"[{entity['slug']} {year}] complete ({n}) — skip")
            return n
        if saved and saved != "DONE" and out_file.exists():
            cursor, mode, cnt = saved, "ab", common.count_lines(out_file)
            log.info(f"[{entity['slug']} {year}] resuming at {cnt} records")

    with open(out_file, mode) as f:
        while True:
            data = fetch_page(session, bucket, cursor, params, timeout)
            works = data.get("results", []) or []
            next_cursor = (data.get("meta") or {}).get("next_cursor")
            for w in works:
                f.write(common.dumps(w)); f.write(b"\n"); cnt += 1
            f.flush()
            common.save_checkpoint(ckpt_file, next_cursor)
            if not next_cursor:
                break
            cursor = next_cursor
    log.info(f"[{entity['slug']} {year}] saved {cnt} -> {out_file.name}")
    return cnt


def run(cfg: dict, years: list[int], resume: bool) -> dict:
    bucket = common.TokenBucket(rate_per_sec=cfg["req_per_sec"])
    units = list(product(cfg["entities"], years))
    log.info(f"{len(cfg['entities'])} entities x {len(years)} years = {len(units)} units; "
             f"{cfg['workers']} workers @ {cfg['req_per_sec']} req/s")
    results: dict = {}
    with ThreadPoolExecutor(max_workers=cfg["workers"], thread_name_prefix="dl") as ex:
        futs = {ex.submit(download_unit, e, y, cfg, bucket, resume): (e["slug"], y)
                for e, y in units}
        for fut in as_completed(futs):
            slug, y = futs[fut]
            try:
                results[f"{slug}_{y}"] = fut.result()
            except Exception as exc:  # noqa: BLE001
                log.exception(f"[{slug} {y}] FAILED: {exc}")
                results[f"{slug}_{y}"] = None
    return results


def write_manifest(cfg: dict, years: list[int], results: dict) -> None:
    common.write_manifest(Path(cfg["out_dir"]) / "_download_manifest.json", {
        "source": "openalex",
        "snapshot_note": "OpenAlex is a living DB; this JSONL is the archived snapshot for reproducibility.",
        "filter_field": cfg["filter_field"],
        "extra_filters": cfg.get("extra_filters") or [],
        "entities": cfg["entities"],
        "years": years,
        "selected_fields": SELECTED_FIELDS,
        "counts": results,
        "total_records": sum(v for v in results.values() if v),
    })


def main() -> None:
    ap = argparse.ArgumentParser(description="OpenAlex works downloader (direct id: filter).")
    ap.add_argument("--count", action="store_true", help="print per-entity counts, no download")
    ap.add_argument("--years", type=int, nargs="+", default=None, help="override config window")
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args()

    cfg = CONFIG
    years = args.years or list(range(cfg["year_start"], cfg["year_end"] + 1))

    if args.count:
        print(f"OpenAlex counts (filter_field={cfg['filter_field']}, {years[0]}-{years[-1]}):")
        for e in cfg["entities"]:
            ids = "|".join(e["ids"])
            f = ",".join([f"{cfg['filter_field']}:{ids}",
                          f"from_publication_date:{years[0]}-01-01",
                          f"to_publication_date:{years[-1]}-12-31",
                          *(cfg.get("extra_filters") or [])])
            print(f"  {e['name']:40} {count(f):>8,}")
        return

    results = run(cfg, years, resume=not args.no_resume)
    write_manifest(cfg, years, results)
    log.info("Done. " + ", ".join(f"{k}={v}" for k, v in sorted(results.items())))


if __name__ == "__main__":
    main()
