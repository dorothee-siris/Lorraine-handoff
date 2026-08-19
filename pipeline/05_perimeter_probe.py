"""05_perimeter_probe.py — gate G1: measure the perimeter before pulling anything.

Computes the two canonical queries of plan section 5, their exact set difference, and which
institutions are responsible for each side of it. Writes a markdown report plus a JSON payload.

This is a probe, not a pull: it requests `select=id` only, so it is cheap (~470 list calls, ~$0.05)
and it is the evidence gate G1 needs before 10_pull_lorraine.py runs.

Usage:  python pipeline/05_perimeter_probe.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import requests
import yaml

sys.stdout.reconfigure(encoding="utf-8")  # the console here is cp1252

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def load_env(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in Path(os.path.expanduser(path)).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


ENV = load_env(CONFIG["secrets"]["env_file"])
for required in CONFIG["secrets"]["required"]:
    if required not in ENV:
        sys.exit(f"missing secret {required} in {CONFIG['secrets']['env_file']}")

BASE = CONFIG["openalex"]["base_url"]
SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"Bearer {ENV['OPENALEX_API_KEY']}"})
MAILTO = ENV["OPENALEX_MAILTO"]
PER_PAGE = CONFIG["openalex"]["per_page"]
MIN_INTERVAL = 1.0 / CONFIG["openalex"]["max_requests_per_second"]

_calls = 0
_last_call = 0.0


def api(path: str, **params):
    """One rate-limited, retrying OpenAlex request. Counts calls for the cost ledger."""
    global _calls, _last_call
    params["mailto"] = MAILTO
    retry = CONFIG["openalex"]["retry"]
    for attempt in range(retry["attempts"]):
        wait = MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        response = SESSION.get(f"{BASE}{path}", params=params, timeout=120)
        _last_call = time.monotonic()
        _calls += 1
        if response.status_code < 400:
            return response.json()
        if response.status_code not in retry["retry_on"]:
            sys.exit(f"HTTP {response.status_code} on {response.url}\n{response.text[:400]}")
        time.sleep(retry["backoff_base_seconds"] ** (attempt + 1))
    sys.exit(f"gave up after {retry['attempts']} attempts on {path} {params}")


def crawl_ids(filter_string: str, label: str) -> set[str]:
    """Cursor-paginate a works filter, returning the bare OpenAlex work ids."""
    ids: set[str] = set()
    cursor = "*"
    pages = 0
    while cursor:
        page = api("/works", filter=filter_string, per_page=PER_PAGE, cursor=cursor, select="id")
        for work in page["results"]:
            ids.add(work["id"].rsplit("/", 1)[-1])
        cursor = page["meta"].get("next_cursor")
        if not page["results"]:
            break
        pages += 1
        if pages % 25 == 0:  # a logged batch, not a redrawn line: this runs under a pipe
            print(f"  {label}: {len(ids):,} / {page['meta']['count']:,}", flush=True)
    print(f"  {label}: {len(ids):,} ids collected")
    return ids


def fetch_details(work_ids: list[str], batch: int = 50) -> list[dict]:
    """Detail records for a small id set, used to explain a set difference."""
    out: list[dict] = []
    for start in range(0, len(work_ids), batch):
        chunk = work_ids[start : start + batch]
        page = api(
            "/works",
            filter="openalex:" + "|".join(chunk),
            per_page=batch,
            select="id,doi,title,publication_year,type,authorships",
        )
        out.extend(page["results"])
    return out


def responsible_institutions(works: list[dict]) -> Counter:
    """Which institutions appear on these works — the co-tutelle early-warning signal."""
    tally: Counter = Counter()
    for work in works:
        seen = set()
        for authorship in work.get("authorships") or []:
            for institution in authorship.get("institutions") or []:
                iid = (institution.get("id") or "").rsplit("/", 1)[-1]
                if iid and iid not in seen:
                    seen.add(iid)
                    tally[(iid, institution.get("display_name"), institution.get("country_code"))] += 1
    return tally


def main() -> None:
    perimeter = CONFIG["perimeter"]
    years = f"{CONFIG['window']['year_from']}-{CONFIG['window']['year_to']}"

    lab_list = pd.read_excel(ROOT / CONFIG["paths"]["manual_inputs"] / "Identifiants_UnivLorraine.xlsx")
    repairs: dict[str, str] = perimeter.get("openalex_id_repairs") or {}
    curated_raw = [str(x).strip() for x in lab_list["OpenAlex"].dropna() if str(x).startswith("I")]
    curated = sorted({repairs.get(i, i) for i in curated_raw})
    applied = {i: repairs[i] for i in curated_raw if i in repairs}
    query_b_ids = sorted({perimeter["ul_openalex_id"], *curated})

    print(f"lab list rows: {len(lab_list)} | curated OpenAlex ids: {len(curated)} | repairs applied: {applied}")
    print(f"query B institution ids (incl. UL): {len(query_b_ids)}")

    filter_a = f"{perimeter['query_a_lineage_filter']},publication_year:{years}"
    filter_b = "authorships.institutions.id:" + "|".join(query_b_ids) + f",publication_year:{years}"

    print("\ncrawling query A (lineage)...")
    set_a = crawl_ids(filter_a, "A lineage")
    print("crawling query B (curated direct)...")
    set_b = crawl_ids(filter_b, "B curated")

    only_a, only_b = sorted(set_a - set_b), sorted(set_b - set_a)
    union, both = set_a | set_b, set_a & set_b
    print(
        f"\n|A| = {len(set_a):,}  |B| = {len(set_b):,}  |A n B| = {len(both):,}  "
        f"|A u B| = {len(union):,}\n|A \\ B| = {len(only_a):,}  |B \\ A| = {len(only_b):,}"
    )

    print("\nfetching details for the set differences...")
    details_a = fetch_details(only_a)
    details_b = fetch_details(only_b)
    inst_a = responsible_institutions(details_a)
    inst_b = responsible_institutions(details_b)
    ul_related = set(query_b_ids)

    def top(tally: Counter, n: int = 15) -> list[tuple]:
        return [(iid, name, cc, count) for (iid, name, cc), count in tally.most_common(n)]

    payload = {
        "probe_date": pd.Timestamp.utcnow().isoformat(),
        "window": years,
        "counts": {
            "A_lineage": len(set_a),
            "B_curated": len(set_b),
            "intersection": len(both),
            "union": len(union),
            "A_minus_B": len(only_a),
            "B_minus_A": len(only_b),
        },
        "query_b_institution_ids": query_b_ids,
        "id_repairs_applied": applied,
        "api_calls": _calls,
        "top_institutions_A_minus_B": top(inst_a, 40),
        "top_institutions_B_minus_A": top(inst_b, 40),
        "A_minus_B_ids": only_a,
        "B_minus_A_ids": only_b,
    }
    reports = ROOT / CONFIG["paths"]["reports"]
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "g1_perimeter_probe.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    lines = [
        "# G1 — perimeter probe",
        "",
        f"Probe run {payload['probe_date']} · window {years} · {_calls} OpenAlex list calls.",
        "",
        "| Set | Works |",
        "|---|---|",
        f"| A — `authorships.institutions.lineage:{perimeter['ul_openalex_id']}` | {len(set_a):,} |",
        f"| B — curated direct ({len(query_b_ids)} institution ids) | {len(set_b):,} |",
        f"| A n B | {len(both):,} |",
        f"| **A u B — canonical perimeter** | **{len(union):,}** |",
        f"| A \\ B (lineage-only) | {len(only_a):,} |",
        f"| B \\ A (curated-only) | {len(only_b):,} |",
        "",
        "## Institutions on the lineage-only works (A \\ B)",
        "",
        "Co-tutelle early warning: if one non-UL institution dominates this list, the pathology the root",
        "CLAUDE.md documents has appeared for Lorraine and the perimeter falls back to query B alone.",
        "",
        "| OpenAlex id | Institution | Country | Works | In query B? |",
        "|---|---|---|---|---|",
    ]
    for iid, name, cc, count in top(inst_a, 25):
        lines.append(f"| `{iid}` | {name} | {cc} | {count} | {'yes' if iid in ul_related else 'no'} |")
    lines += [
        "",
        "## Institutions on the curated-only works (B \\ A)",
        "",
        "| OpenAlex id | Institution | Country | Works | In query B? |",
        "|---|---|---|---|---|",
    ]
    for iid, name, cc, count in top(inst_b, 25):
        lines.append(f"| `{iid}` | {name} | {cc} | {count} | {'yes' if iid in ul_related else 'no'} |")
    lines += ["", f"Id repairs applied (D20): `{applied or 'none'}`", ""]
    (reports / "g1_perimeter_probe.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"\nwrote {reports / 'g1_perimeter_probe.md'} and .json  ({_calls} API calls)")


if __name__ == "__main__":
    main()
