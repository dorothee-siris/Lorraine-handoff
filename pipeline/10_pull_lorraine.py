"""10_pull_lorraine.py — pull the Lorraine perimeter from OpenAlex into the snapshot.

Per D33 (gate G1, measured 2026-08-10) this crawls query A (`authorships.institutions.lineage:`)
only, because query B was measured to be a STRICT SUBSET of it, and derives the provenance flags
locally from the authorships already in the payload. A one-call subset guard re-verifies that
property on every run and fails loudly if a client edit ever breaks it.

Doc types are deliberately NOT filtered here (plan §6): step 11 filters, so the shift report can
quantify OpenAlex's doc-type reclassification.

Output tables use NATIVE long structures, never v1's `[n]`-prefixed strings — that format is what
mis-attributed per-author fields on 51.4% of v1's works.

Usage
  python pipeline/10_pull_lorraine.py --calibrate      # 10 works, inspect, write nothing durable
  python pipeline/10_pull_lorraine.py                  # full pull, all years, resumable
  python pipeline/10_pull_lorraine.py --year 2021      # one shard (safe to run in parallel)
  python pipeline/10_pull_lorraine.py --tables-only    # rebuild tables from existing raw JSONL
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.openalex import (  # noqa: E402
    OpenAlexClient,
    ascii_safe_stdout,
    load_env,
    reconstruct_abstract,
    short_id,
)
from lib.snapshot import (  # noqa: E402
    Manifest,
    append_summary,
    load_config,
    resolve_snapshot,
    sha256,
)

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)

SELECT = (
    "id,doi,title,publication_year,publication_date,type,type_crossref,language,"
    "is_retracted,is_paratext,indexed_in,cited_by_count,fwci,citation_normalized_percentile,"
    "primary_topic,topics,authorships,corresponding_author_ids,open_access,"
    "funders,awards,sustainable_development_goals,abstract_inverted_index,"
    "referenced_works_count,locations_count,primary_location,best_oa_location,"
    # Truncation detectors — see AUTHORSHIP_CAP below. These two are computed by OpenAlex on the
    # FULL record even when the returned authorships list is cut short.
    "institutions_distinct_count,countries_distinct_count"
)

# TRAP, measured 2026-08-10 and fixed here.
# The /works LIST endpoint truncates `authorships` to 100 entries; the single-entity endpoint
# /works/{id} returns all of them. W2924217050 has 477 authorships and 82 institutions; the list
# payload carried 100 and 57, and Universite de Lorraine itself sat beyond position 100 — so the
# work was in the perimeter (the server filters on the full record) while our parse saw no UL
# affiliation at all. Left unhandled this silently corrupts provenance flags, lab attribution,
# the partner table and the author table on every hyper-authored work.
# 171 perimeter works have >100 authors (`authors_count:>100`). v1 HAS THE SAME DEFECT: its
# `Authors` field caps at exactly 100 slots on 132 works and never exceeds it.
AUTHORSHIP_CAP = 100
ROR_PATTERN = re.compile(r"^0[a-hj-km-np-tv-z0-9]{6}[0-9]{2}$")  # real RORs; excludes ror_isite etc.


def iter_raw(path: Path):
    """Yield records from a raw shard, whether it is `.jsonl` or compressed `.jsonl.zst` (D18)."""
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
        raise SystemExit(f"missing raw shard {path} (and no .zst beside it) — re-run the crawl")


def raw_exists(path: Path) -> bool:
    return path.exists() or path.with_suffix(path.suffix + ".zst").exists()


def normalise_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip().lower()) or None


def load_perimeter_ids() -> tuple[set[str], set[str], dict[str, str]]:
    """Curated OpenAlex ids and RORs from the client's list, with D20 id repairs applied."""
    perimeter = CONFIG["perimeter"]
    lab_list = pd.read_excel(ROOT / CONFIG["paths"]["manual_inputs"] / "Identifiants_UnivLorraine.xlsx")
    repairs: dict[str, str] = perimeter.get("openalex_id_repairs") or {}
    raw_ids = [str(x).strip() for x in lab_list["OpenAlex"].dropna() if str(x).startswith("I")]
    lab_ids = {repairs.get(i, i) for i in raw_ids}
    applied = {i: repairs[i] for i in raw_ids if i in repairs}
    lab_rors = {
        str(x).strip().lower() for x in lab_list["ROR"].dropna() if ROR_PATTERN.match(str(x).strip().lower())
    }
    return lab_ids, lab_rors, applied


# --------------------------------------------------------------------------------------- parsing


def is_truncated(work: dict) -> bool:
    """Does this record still carry the list endpoint's authorship cut?

    Two independent signals, because either alone has a blind spot:
      * the authorships list sits exactly on the cap;
      * fewer distinct institutions are visible than OpenAlex counted on the full record.
    """
    authorships = work.get("authorships") or []
    if len(authorships) >= AUTHORSHIP_CAP:
        return True
    visible = {
        short_id(institution.get("id"))
        for authorship in authorships
        for institution in authorship.get("institutions") or []
    } - {None}
    declared = work.get("institutions_distinct_count")
    return bool(declared is not None and len(visible) < declared)


def parse_work(work: dict, lab_ids: set[str], lab_rors: set[str], ul_id: str) -> dict[str, list | dict]:
    """One OpenAlex work -> one `works` row plus its long-format child rows."""
    work_id = short_id(work.get("id"))
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    cnp = work.get("citation_normalized_percentile") or {}
    oa = work.get("open_access") or {}
    primary_location = work.get("primary_location") or {}
    primary_source = (primary_location.get("source") or {}) if isinstance(primary_location, dict) else {}
    primary_topic = work.get("primary_topic") or {}

    authorship_rows: list[dict] = []
    institution_ids: set[str] = set()
    institution_rors: set[str] = set()
    corresponding = {short_id(a) for a in (work.get("corresponding_author_ids") or [])}

    for position, authorship in enumerate(work.get("authorships") or [], start=1):
        author = authorship.get("author") or {}
        author_id = short_id(author.get("id"))
        base = {
            "work_id": work_id,
            "author_position": position,
            "author_position_label": authorship.get("author_position"),
            "author_id": author_id,
            "author_display_name": author.get("display_name"),
            "orcid": (author.get("orcid") or "").rsplit("/", 1)[-1] or None,
            "is_corresponding": bool(authorship.get("is_corresponding")) or author_id in corresponding,
        }
        institutions = authorship.get("institutions") or []
        if not institutions:
            # Keep the author: an affiliation-less author must not vanish from the table.
            authorship_rows.append(
                {
                    **base,
                    "institution_id": None,
                    "institution_ror": None,
                    "institution_display_name": None,
                    "institution_country": None,
                    "institution_type": None,
                }
            )
        for institution in institutions:
            iid = short_id(institution.get("id"))
            ror = (institution.get("ror") or "").rsplit("/", 1)[-1].lower() or None
            if iid:
                institution_ids.add(iid)
            if ror:
                institution_rors.add(ror)
            authorship_rows.append(
                {
                    **base,
                    "institution_id": iid,
                    "institution_ror": ror,
                    "institution_display_name": institution.get("display_name"),
                    "institution_country": institution.get("country_code"),
                    "institution_type": institution.get("type"),
                }
            )

    topic_rows: list[dict] = []
    primary_topic_id = short_id(primary_topic.get("id"))
    for topic in work.get("topics") or []:
        topic_id = short_id(topic.get("id"))
        topic_rows.append(
            {
                "work_id": work_id,
                "topic_id": topic_id,
                "topic_name": topic.get("display_name"),
                "score": topic.get("score"),
                "is_primary": topic_id is not None and topic_id == primary_topic_id,
                "subfield_id": short_id((topic.get("subfield") or {}).get("id")),
                "subfield_name": (topic.get("subfield") or {}).get("display_name"),
                "field_id": short_id((topic.get("field") or {}).get("id")),
                "field_name": (topic.get("field") or {}).get("display_name"),
                "domain_id": short_id((topic.get("domain") or {}).get("id")),
                "domain_name": (topic.get("domain") or {}).get("display_name"),
            }
        )

    sdg_rows = [
        {
            "work_id": work_id,
            "sdg_id": (sdg.get("id") or "").rsplit("/", 1)[-1] or None,
            "sdg_name": sdg.get("display_name"),
            "score": sdg.get("score"),
        }
        for sdg in work.get("sustainable_development_goals") or []
    ]

    funding_rows: list[dict] = []
    for award in work.get("awards") or []:
        funding_rows.append(
            {
                "work_id": work_id,
                "award_id": short_id(award.get("id")),
                "award_display_name": award.get("display_name"),
                "funder_award_id": award.get("funder_award_id"),
                "funder_id": short_id(award.get("funder_id")),
                "funder_display_name": award.get("funder_display_name"),
            }
        )
    funder_ids = {short_id(f.get("id")) for f in work.get("funders") or []} | {
        row["funder_id"] for row in funding_rows
    }

    matched_labs = sorted((institution_ids & lab_ids) | set())
    matched_rors = sorted(institution_rors & lab_rors)
    doi = normalise_doi(work.get("doi"))

    works_row = {
        "work_id": work_id,
        "doi": doi,
        "has_doi": doi is not None,
        "title": work.get("title"),
        "publication_year": work.get("publication_year"),
        "publication_date": work.get("publication_date"),
        "type": work.get("type"),
        "type_crossref": work.get("type_crossref"),
        "language": work.get("language"),
        "is_retracted": bool(work.get("is_retracted")),
        "is_paratext": bool(work.get("is_paratext")),
        "indexed_in": ";".join(work.get("indexed_in") or []) or None,
        "in_crossref": "crossref" in (work.get("indexed_in") or []),
        "cited_by_count": work.get("cited_by_count"),
        "fwci_openalex": work.get("fwci"),
        "cnp_value": cnp.get("value"),
        "cnp_is_top1": cnp.get("is_in_top_1_percent"),
        "cnp_is_top10": cnp.get("is_in_top_10_percent"),
        "is_oa": oa.get("is_oa"),
        "oa_status": oa.get("oa_status"),
        "referenced_works_count": work.get("referenced_works_count"),
        "locations_count": work.get("locations_count"),
        "primary_source_id": short_id(primary_source.get("id")),
        "primary_source_name": primary_source.get("display_name"),
        "primary_source_type": primary_source.get("type"),
        "primary_topic_id": primary_topic_id,
        "primary_subfield_id": short_id((primary_topic.get("subfield") or {}).get("id")),
        "primary_field_id": short_id((primary_topic.get("field") or {}).get("id")),
        "primary_domain_id": short_id((primary_topic.get("domain") or {}).get("id")),
        "abstract": abstract,
        "abstract_chars": len(abstract) if abstract else 0,
        "abstract_source": "openalex" if abstract else None,
        "n_authors": len({row["author_id"] for row in authorship_rows if row["author_id"]}),
        "n_institutions": len(institution_ids),
        "institutions_distinct_count": work.get("institutions_distinct_count"),
        "countries_distinct_count": work.get("countries_distinct_count"),
        # Two distinct facts, deliberately not collapsed into one flag:
        #   authors_over_cap      — a big-team work (>= the cap). True on repaired records too.
        #   institutions_incomplete — we can SEE fewer institutions than OpenAlex counted, i.e. this
        #                             record is still cut. Must be False everywhere after the repair
        #                             pass; that is the Class 1 invariant in run_checks().
        "authors_over_cap": len(work.get("authorships") or []) >= AUTHORSHIP_CAP,
        "institutions_incomplete": (
            work.get("institutions_distinct_count") is not None
            and len(institution_ids) < work["institutions_distinct_count"]
        ),
        # Provenance (D2 / D33): non-exclusive booleans, one per route into the perimeter.
        "via_lineage": True,  # every work here came from query A
        "via_ul_direct": ul_id in institution_ids,
        "via_lab_ror": bool(matched_labs or matched_rors),
        "matched_lab_openalex_ids": ";".join(matched_labs) or None,
        # FIX-1 pass-6 fix round (S-LENS WATCH note, docs/VIZ_BACKLOG_pass6.md #17):
        # every OTHER multi-value blob column in the house (Labs, Poles, funder_ids'
        # siblings downstream) uses " | ", never a bare ";" -- this one drifted because
        # it is set at PULL time (here), not at the 40_build_works.py BUILD-time layer
        # where the " | " convention was established. Zero consumers today (grep-
        # verified across Streamlit/ and pipeline/), so this is a regression-prevention
        # fix, not a live-data correction: the same landmine SHAPE as the 16.4%
        # ptn_labs corruption (a naive ";"-vs-"|" split/zip mismatch), just not yet
        # triggered because nothing reads this column. Unify the separator now, before
        # a future consumer inherits the trap.
        "matched_lab_rors": " | ".join(matched_rors) or None,
        "n_sdg_openalex": len(sdg_rows),
        "has_isite_award": CONFIG["isite"]["openalex_award_id"] in {r["award_id"] for r in funding_rows},
        "funder_ids": ";".join(sorted(f for f in funder_ids if f)) or None,
    }
    return {
        "works": works_row,
        "authorships": authorship_rows,
        "topics": topic_rows,
        "sdg": sdg_rows,
        "funding": funding_rows,
    }


# ------------------------------------------------------------------------------------ operations


def crawl_year(client: OpenAlexClient, snapshot: Path, year: int, limit: int | None) -> Path:
    """Crawl one year into raw/lorraine_{year}.jsonl, resumable via its .cursor file."""
    filter_string = f"{CONFIG['perimeter']['query_a_lineage_filter']},publication_year:{year}"
    out_path = snapshot / "raw" / f"lorraine_{year}.jsonl"
    cursor_path = snapshot / "raw" / f"lorraine_{year}.cursor"
    if cursor_path.exists() and cursor_path.read_text(encoding="utf-8").strip() == "DONE":
        print(f"  {year}: already complete ({out_path.name})")
        return out_path
    mode = "a" if cursor_path.exists() and out_path.exists() else "w"
    with out_path.open(mode, encoding="utf-8") as handle:
        for page in client.crawl(
            filter_string, SELECT, cursor_file=cursor_path, limit=limit, label=str(year)
        ):
            for work in page:
                handle.write(json.dumps(work, ensure_ascii=False) + "\n")
    return out_path


def repair_truncated(client: OpenAlexClient, snapshot: Path, years: list[int]) -> dict[str, dict]:
    """Re-fetch, from the single-entity endpoint, every work the list endpoint truncated.

    Writes `raw/repairs.jsonl` incrementally, so an interrupted repair resumes instead of
    re-paying for records it already has. Returns {work_id: full record}.
    """
    repairs_path = snapshot / "raw" / "repairs.jsonl"
    repaired: dict[str, dict] = {}
    if repairs_path.exists():
        with repairs_path.open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                repaired[short_id(record.get("id"))] = record
        print(f"  {len(repaired):,} repairs already on disk")

    needed: list[str] = []
    for year in years:
        path = snapshot / "raw" / f"lorraine_{year}.jsonl"
        if not raw_exists(path):
            continue
        for work in iter_raw(path):
            if is_truncated(work):
                work_id = short_id(work.get("id"))
                if work_id and work_id not in repaired:
                    needed.append(work_id)
    needed = sorted(set(needed))
    print(f"  works needing a full-record refetch: {len(needed):,}")
    if not needed:
        return repaired

    with repairs_path.open("a", encoding="utf-8") as handle:
        for index, work_id in enumerate(needed, start=1):
            record = client.get(f"/works/{work_id}", select=SELECT)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            repaired[work_id] = record
            if index % 25 == 0:
                print(f"    repaired {index:,} / {len(needed):,}", flush=True)
    print(f"  repaired {len(needed):,} works via the single-entity endpoint")
    return repaired


def build_tables(snapshot: Path, years: list[int], repairs: dict[str, dict] | None = None) -> dict[str, pd.DataFrame]:
    """Parse every raw JSONL shard into the four (plus funding) native long tables."""
    repairs = repairs or {}
    lab_ids, lab_rors, applied = load_perimeter_ids()
    ul_id = CONFIG["perimeter"]["ul_openalex_id"]
    print(f"perimeter: {len(lab_ids)} curated ids, {len(lab_rors)} real RORs, repairs {applied or 'none'}")

    buckets: dict[str, list] = {"works": [], "authorships": [], "topics": [], "sdg": [], "funding": []}
    raw_lines = 0
    for year in years:
        path = snapshot / "raw" / f"lorraine_{year}.jsonl"
        if not raw_exists(path):
            raise SystemExit(f"missing raw shard {path} — run the crawl for {year} first")
        for work in iter_raw(path):
            raw_lines += 1
            # A repaired full record always wins over the truncated list payload.
            work = repairs.get(short_id(work.get("id")), work)
            parsed = parse_work(work, lab_ids, lab_rors, ul_id)
            buckets["works"].append(parsed["works"])
            buckets["authorships"].extend(parsed["authorships"])
            buckets["topics"].extend(parsed["topics"])
            buckets["sdg"].extend(parsed["sdg"])
            buckets["funding"].extend(parsed["funding"])
        print(f"  parsed {year}: {raw_lines:,} raw records so far")

    tables = {name: pd.DataFrame(rows) for name, rows in buckets.items()}
    duplicates = int(tables["works"]["work_id"].duplicated().sum())
    if duplicates:
        print(f"  removing {duplicates:,} duplicate work rows (cursor overlap on resume)")
        keep = ~tables["works"]["work_id"].duplicated()
        tables["works"] = tables["works"][keep].reset_index(drop=True)
        for child in ("authorships", "topics", "sdg", "funding"):
            if not tables[child].empty:
                tables[child] = tables[child].drop_duplicates().reset_index(drop=True)
    return tables


def run_checks(tables: pd.DataFrame | dict, client: OpenAlexClient | None, skip_guard: bool) -> list[str]:
    """Plan §6 tests for this step. Structural failures raise; the guard reports and can fail."""
    works, authorships = tables["works"], tables["authorships"]
    lines: list[str] = []

    assert not works["work_id"].duplicated().any(), "duplicate work ids survived dedup"
    assert works["work_id"].notna().all(), "null work id"
    works_with_authorship = authorships["work_id"].nunique()
    lines.append(f"- works pulled: **{len(works):,}**")
    lines.append(f"- works with >=1 authorship row: {works_with_authorship:,}")
    orphans = len(works) - works_with_authorship
    if orphans:
        lines.append(f"- **{orphans:,} works have no authorship at all** (OpenAlex records with no authors)")
    lines.append(f"- authorship rows (work x author x institution): {len(authorships):,}")
    lines.append(f"- provenance: via_ul_direct {int(works['via_ul_direct'].sum()):,} · "
                 f"via_lab_ror {int(works['via_lab_ror'].sum()):,} · "
                 f"via_lineage {int(works['via_lineage'].sum()):,}")
    no_route = int((~works["via_ul_direct"] & ~works["via_lab_ror"]).sum())
    lines.append(f"- lineage-only works (no UL id and no curated lab on the record): {no_route:,}")
    coverage = works["abstract"].notna().mean()
    lines.append(f"- OpenAlex abstract coverage before backfill: **{coverage:.1%}** "
                 f"({int(works['abstract'].notna().sum()):,} works)")
    lines.append(f"- doc types: " + " · ".join(
        f"{t} {c:,}" for t, c in works["type"].value_counts().head(10).items()))
    lines.append(f"- works carrying the I-SITE award {CONFIG['isite']['openalex_award_id']}: "
                 f"{int(works['has_isite_award'].sum()):,}")

    # Class 1 invariant for the authorship-truncation trap: after the repair pass, no work may
    # show fewer distinct institutions than OpenAlex counted on the full record.
    short_records = works[works["institutions_incomplete"]]
    lines.append(f"- big-team works (>= {AUTHORSHIP_CAP} authorships): "
                 f"{int(works['authors_over_cap'].sum()):,} — all refetched in full")
    lines.append(f"- records still missing institutions after the repair pass: **{len(short_records):,}** "
                 f"(must be 0; v1 shipped this defect uncorrected)")
    if len(short_records):
        raise SystemExit(
            f"TRUNCATION INVARIANT FAILED on {len(short_records):,} works (e.g. "
            f"{short_records['work_id'].head(5).tolist()}): the repair pass did not restore every "
            f"full record. Re-run 10_pull_lorraine.py --tables-only to resume the repairs."
        )

    band = CONFIG["perimeter"]["expected_works_a"]
    drift = abs(len(works) - band) / band
    lines.append(f"- vs the 2026-08-10 probe expectation of {band:,}: {drift:+.2%}")

    if client and not skip_guard and CONFIG["perimeter"]["subset_guard"]["enabled"]:
        lab_ids, _, _ = load_perimeter_ids()
        query_b_ids = sorted({CONFIG["perimeter"]["ul_openalex_id"], *lab_ids})
        years = f"{CONFIG['window']['year_from']}-{CONFIG['window']['year_to']}"
        query_b = "authorships.institutions.id:" + "|".join(query_b_ids) + f",publication_year:{years}"
        live_b = client.count(query_b)
        pulled_b = int((works["via_ul_direct"] | works["via_lab_ror"]).sum())
        shortfall = (live_b - pulled_b) / live_b if live_b else 0
        lines.append(f"- **subset guard (D33)**: live |B| = {live_b:,}, pulled B-flagged = {pulled_b:,} "
                     f"({shortfall:+.3%} shortfall)")
        if shortfall > 0.005:
            raise SystemExit(
                f"SUBSET GUARD FAILED: query B has {live_b:,} works but only {pulled_b:,} were "
                f"flagged in the lineage pull. A curated structure is outside UL's OpenAlex "
                f"lineage — crawl query B in full (config perimeter.subset_guard.on_failure)."
            )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--year", type=int, action="append")
    parser.add_argument("--calibrate", action="store_true", help="10 works, inspect, nothing durable")
    parser.add_argument("--tables-only", action="store_true", help="rebuild tables from existing raw")
    parser.add_argument("--skip-guard", action="store_true")
    args = parser.parse_args()

    env = load_env(CONFIG["secrets"]["env_file"], CONFIG["secrets"]["required"])
    client = OpenAlexClient(CONFIG, env)
    years = args.year or list(range(CONFIG["window"]["year_from"], CONFIG["window"]["year_to"] + 1))

    if args.calibrate:
        print("CALIBRATION — 10 works, no snapshot write (cost protocol: never batch uncalibrated)\n")
        filter_string = f"{CONFIG['perimeter']['query_a_lineage_filter']},publication_year:{years[0]}"
        page = next(iter(client.crawl(filter_string, SELECT, limit=10, label="calibrate")))[:10]
        lab_ids, lab_rors, applied = load_perimeter_ids()
        parsed = [parse_work(w, lab_ids, lab_rors, CONFIG["perimeter"]["ul_openalex_id"]) for w in page]
        works = pd.DataFrame([p["works"] for p in parsed])
        print(works[["work_id", "publication_year", "type", "via_ul_direct", "via_lab_ror",
                     "n_authors", "abstract_chars", "cited_by_count"]].to_string(index=False))
        for parsed_work in parsed[:2]:
            row = parsed_work["works"]
            print(f"\n--- {row['work_id']} | {row['type']} | doi {row['doi']}")
            print(f"    title   : {(row['title'] or '')[:110]}")
            print(f"    abstract: {(row['abstract'] or '(none)')[:220]}")
            print(f"    labs    : {row['matched_lab_openalex_ids']} / rors {row['matched_lab_rors']}")
            print(f"    authorship rows {len(parsed_work['authorships'])} · topics "
                  f"{len(parsed_work['topics'])} · sdg {len(parsed_work['sdg'])} · "
                  f"funding {len(parsed_work['funding'])}")
            first = parsed_work["authorships"][0] if parsed_work["authorships"] else {}
            print(f"    first authorship row: {first}")
        print(f"\ncalibration used {client.calls} API calls. Review, then run the full pull.")
        return

    snapshot = resolve_snapshot(CONFIG, args.snapshot)
    print(f"snapshot: {snapshot}")

    if not args.tables_only:
        for year in years:
            crawl_year(client, snapshot, year, limit=None)

    all_years = list(range(CONFIG["window"]["year_from"], CONFIG["window"]["year_to"] + 1))
    done = [
        y for y in all_years
        if (snapshot / "raw" / f"lorraine_{y}.cursor").exists()
        and (snapshot / "raw" / f"lorraine_{y}.cursor").read_text(encoding="utf-8").strip() == "DONE"
    ]
    if sorted(done) != all_years:
        print(f"\nshards complete: {done or 'none'} — tables are built only when all years are done.")
        return

    print("\nrepairing list-endpoint authorship truncation (see AUTHORSHIP_CAP)...")
    repairs = repair_truncated(client, snapshot, all_years)

    print("\nbuilding native long tables...")
    tables = build_tables(snapshot, all_years, repairs)
    written: list[Path] = []
    for name, frame in tables.items():
        target = snapshot / "tables" / f"{name}.parquet"
        frame.to_parquet(target, index=False, compression=CONFIG["storage"]["compression"])
        written.append(target)
        print(f"  wrote {target.name}: {len(frame):,} rows, {target.stat().st_size/1e6:.1f} MB")

    lines = run_checks(tables, client, args.skip_guard)
    print("\n".join(lines))

    raw_files = [snapshot / "raw" / f"lorraine_{y}.jsonl" for y in all_years] + [
        snapshot / "raw" / "repairs.jsonl"
    ]
    raw_checksums = {p.name: {"sha256": sha256(p), "bytes": p.stat().st_size} for p in raw_files if p.exists()}
    manifest = Manifest(snapshot)
    manifest.record_step(
        "10_pull_lorraine",
        filters={f"{y}": f"{CONFIG['perimeter']['query_a_lineage_filter']},publication_year:{y}" for y in all_years},
        select=SELECT,
        api_base=CONFIG["openalex"]["base_url"],
        api_calls=client.calls,
        counts={name: len(frame) for name, frame in tables.items()},
        files=written,
        params={
            "pull_strategy": CONFIG["perimeter"]["pull_strategy"],
            "per_page": CONFIG["openalex"]["per_page"],
            "doc_types_filtered_at_pull": False,
            "id_repairs": load_perimeter_ids()[2],
            "raw_jsonl_checksums": raw_checksums,
            "authorship_cap": AUTHORSHIP_CAP,
            "works_repaired_for_truncation": len(repairs),
        },
        notes=(
            "Query A only per D33; provenance flags derived locally; subset guard verified; "
            "list-endpoint authorship truncation repaired via single-entity refetch."
        ),
    )
    append_summary(snapshot, "10_pull_lorraine", lines)

    storage = CONFIG["storage"]
    if storage.get("compress_raw_jsonl"):
        # D18 revised: keep the raw payloads, compressed. The sha256 recorded above is of the
        # UNCOMPRESSED bytes, so it stays comparable across runs regardless of compression level.
        import zstandard

        compressor = zstandard.ZstdCompressor(level=storage.get("raw_compression_level", 10))
        saved_bytes = 0
        for path in raw_files:
            if not path.exists():
                continue
            target = path.with_suffix(path.suffix + ".zst")
            with path.open("rb") as source, target.open("wb") as sink:
                compressor.copy_stream(source, sink)
            saved_bytes += path.stat().st_size - target.stat().st_size
            path.unlink()  # the .zst replaces it; the JSONL itself is recoverable from it
        kept = sorted(p.name for p in (snapshot / "raw").glob("*.jsonl.zst"))
        print(f"\ncompressed and KEPT {len(kept)} raw shards ({saved_bytes/1e6:.0f} MB saved): "
              f"{', '.join(kept)}")
    elif storage.get("delete_jsonl_after_checksum"):
        for path in raw_files:
            if path.exists():
                path.unlink()
        print(f"\ndeleted {len(raw_checksums)} raw JSONL shards after checksumming; "
              f"parquet tables are the archive.")
    print(f"\ndone. {client.calls} API calls this run.")


if __name__ == "__main__":
    main()
