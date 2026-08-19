"""20b_hal_structure_harvest.py — bulk HAL harvest, then match to the corpus by DOI and by title.

Why this exists (D39). `20_abstracts_backfill.py` queries HAL and OpenAIRE **by DOI**, which
structurally cannot reach the 11,342 corpus works that have no DOI — and 10,372 of those are HAL
deposits. The SIRIS connector cookbook (`lib/connectors/hal.py`) harvests HAL the right way instead:
a bulk structure-scoped Solr crawl with cursorMark deep paging. One harvest of ~43 pages then serves
DOI matching, title matching, and later the idHAL/ORCID author work.

Matching is deliberately conservative. A DOI match is exact. A title match is accepted ONLY when the
normalised title is unique on both sides and the publication years agree within one — because a
wrong title match silently attributes another institution's abstract to a Lorraine work, which is the
same class of failure as v1's `[n]` misalignment.

Usage
  python pipeline/20b_hal_structure_harvest.py --calibrate     # 2 pages, match report only
  python pipeline/20b_hal_structure_harvest.py                 # full harvest + match + fill
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib" / "connectors"))
import common  # the vendored cookbook helper (make_session, checkpoints, dumps)  # noqa: E402

from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)

# UL in HAL: structure docid 413289 ("Universite de Lorraine", VALID, acronym UL) and the portal
# collection UNIV-LORRAINE. Measured 2026-08-11 for 2019-2023: structId 42,222 · collCode 42,914 ·
# union 42,933 — so the union is used, for recall.
HAL_STRUCT_ID = 413289
HAL_COLL_CODE = "UNIV-LORRAINE"
HAL_ENDPOINT = "https://api.archives-ouvertes.fr/search/"
ROWS_PER_PAGE = 1000
REQ_PER_SEC = 3

# Wide field list, from the cookbook: abstract_s is full text (no reconstruction needed), doiId_s is a
# bare DOI, and authIdHal_s / authORCIDIdExt_s feed 45_build_authors later.
FL = ",".join([
    "docid", "halId_s", "uri_s", "doiId_s",
    "title_s", "subTitle_s", "abstract_s", "keyword_s",
    "authFullName_s",
    # ALIGNED name<->idHAL pairs: one entry per author, empty after the separator when absent.
    # authIdHal_s and authORCIDIdExt_s are SPARSE (only authors who have the id), so pairing them
    # positionally with authFullName_s mis-attributes identifiers - the same failure class as v1's
    # [n] strings. HAL exposes NO aligned ORCID field, so per-author ORCID is not recoverable.
    "authFullNameIdHal_fs", "authIdHal_s", "authORCIDIdExt_s",
    "structId_i", "labStructId_i", "instStructId_i",
    "docType_s", "publicationDateY_i", "publicationDate_s",
    "language_s", "journalTitle_s",
])

MIN_TITLE_CHARS = 25   # below this a normalised title is too generic to match on safely
MIN_USEFUL_CHARS = 20


def first(value):
    """HAL returns most fields as single-element lists."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def normalise_title(title: str | None) -> str | None:
    if not title:
        return None
    text = unicodedata.normalize("NFD", str(title))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn").lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text or None


def normalise_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", str(doi).strip().lower()) or None


def is_title_echo(abstract: str | None, title: str | None) -> bool:
    """True when HAL's 'abstract' is really just the title repeated.

    Found in calibration: W2899308855 was offered a 137-char 'abstract' identical to its own title.
    Accepting those would feed the SDG tagger a title while labelling it an abstract — inflating
    measured coverage and quietly changing what the tagger sees. Reject anything whose text is the
    title plus less than ~30% extra.
    """
    a, t = normalise_title(abstract), normalise_title(title)
    if not a or not t:
        return False
    return a == t or (a.startswith(t) and len(a) < 1.3 * len(t))


def harvest(snapshot: Path, max_pages: int | None = None) -> Path:
    """cursorMark deep page over the UL structure + collection union, into raw/hal_lorraine.jsonl."""
    out_path = snapshot / "raw" / "hal_lorraine.jsonl"
    checkpoint = snapshot / "raw" / "hal_lorraine.cursor"
    if common.load_checkpoint(checkpoint) == "DONE" and (
        out_path.exists() or out_path.with_suffix(out_path.suffix + ".zst").exists()
    ):
        print("  HAL harvest already complete (checkpoint DONE)")
        return out_path

    years = f"[{CONFIG['window']['year_from']} TO {CONFIG['window']['year_to']}]"
    base = [
        ("q", "*:*"),
        ("fq", f"structId_i:{HAL_STRUCT_ID} OR collCode_s:{HAL_COLL_CODE}"),
        ("fq", f"publicationDateY_i:{years}"),
        ("fl", FL),
        ("rows", str(ROWS_PER_PAGE)),
        ("sort", "docid asc"),          # cursorMark requires a deterministic sort
        ("wt", "json"),
    ]
    session = common.make_session(
        max_retries=5,
        backoff_factor=2.0,
        user_agent=common.default_user_agent(common.get_secret("OPENALEX_MAILTO"), "SIRIS-Lorraine-v2/hal"),
    )
    delay = 1.0 / REQ_PER_SEC

    cursor, mode, count = "*", "w", 0
    saved = common.load_checkpoint(checkpoint)
    if saved and saved != "DONE" and out_path.exists():
        cursor, mode = saved, "a"
        count = common.count_lines(out_path)
        print(f"  resuming HAL harvest from saved cursorMark at {count:,} records")

    num_found, page = None, 0
    with out_path.open(mode, encoding="utf-8") as handle:
        while True:
            response = session.get(f"{HAL_ENDPOINT}?{urlencode(base + [('cursorMark', cursor)])}", timeout=120)
            response.raise_for_status()
            payload = response.json()
            block = payload.get("response", {})
            if num_found is None:
                num_found = block.get("numFound")
                print(f"  HAL reports {num_found:,} records for the window")
            docs = block.get("docs") or []
            for doc in docs:
                handle.write(json.dumps(doc, ensure_ascii=False) + "\n")
                count += 1
            handle.flush()
            next_cursor = payload.get("nextCursorMark")
            page += 1
            if page % 10 == 0:
                print(f"    page {page}: {count:,} / {num_found:,}", flush=True)
            # HAL signals the end by not advancing the cursor.
            if not next_cursor or next_cursor == cursor or not docs:
                common.save_checkpoint(checkpoint, None)  # DONE
                break
            cursor = next_cursor
            common.save_checkpoint(checkpoint, cursor)
            if max_pages and page >= max_pages:
                print(f"    stopping at calibration limit of {max_pages} pages")
                break
            time.sleep(delay)
    print(f"  harvested {count:,} HAL records (numFound {num_found:,}) -> {out_path.name}")
    return out_path


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
        raise SystemExit(f"no HAL raw file at {path}")


def build_hal_frame(path: Path) -> pd.DataFrame:
    rows = []
    for doc in iter_raw(path):
        abstracts = doc.get("abstract_s") or []
        abstracts = abstracts if isinstance(abstracts, list) else [abstracts]
        texts = [t for t in (str(a).strip() for a in abstracts if a) if len(t) >= MIN_USEFUL_CHARS]
        best = max(texts, key=len) if texts else None
        title = first(doc.get("title_s"))
        rows.append(
            {
                "hal_id": doc.get("halId_s"),
                "hal_docid": doc.get("docid"),
                "hal_doi": normalise_doi(doc.get("doiId_s")),
                "hal_title_norm": normalise_title(title),
                "hal_year": first(doc.get("publicationDateY_i")),
                "hal_doctype": doc.get("docType_s"),
                "hal_lang": first(doc.get("language_s")),
                "hal_abstract": best,
                "hal_abstract_chars": len(best) if best else 0,
                # aligned pairs, safe to attribute per author
                "hal_author_idhal_pairs": "||".join(str(x) for x in (doc.get("authFullNameIdHal_fs") or [])) or None,
                # sparse, NOT attributable to a given author - work-level counts only
                "hal_n_authors_with_idhal": len(doc.get("authIdHal_s") or []),
                "hal_n_authors_with_orcid": len(doc.get("authORCIDIdExt_s") or []),
                "hal_lab_struct_ids": ";".join(str(x) for x in (doc.get("labStructId_i") or [])) or None,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--calibrate", action="store_true")
    args = parser.parse_args()

    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=True)
    tables = snapshot / "tables"
    source = tables / "corpus_abstracts.parquet"
    if not source.exists():
        source = tables / "corpus.parquet"
    corpus = pd.read_parquet(source)
    print(f"snapshot {snapshot.name}: corpus {len(corpus):,} works from {source.name}")
    print(f"  abstract coverage now: {corpus['abstract'].notna().mean():.1%}")

    raw_path = harvest(snapshot, max_pages=2 if args.calibrate else None)
    hal = build_hal_frame(raw_path)
    print(f"  HAL frame: {len(hal):,} records · {hal['hal_abstract'].notna().sum():,} with an abstract "
          f"· {hal['hal_doi'].notna().sum():,} with a DOI")

    need = corpus[corpus["abstract"].isna()].copy()
    need["title_norm"] = need["title"].map(normalise_title)
    print(f"  works still lacking an abstract: {len(need):,}")

    # --- route 1: exact DOI ---
    hal_by_doi = (
        hal[hal["hal_doi"].notna() & hal["hal_abstract"].notna()]
        .sort_values("hal_abstract_chars", ascending=False)
        .drop_duplicates("hal_doi")
    )
    doi_match = need.merge(hal_by_doi, left_on="doi", right_on="hal_doi", how="inner")
    print(f"  matched by DOI  : {len(doi_match):,}")

    # --- route 2: unique normalised title, years agreeing within 1 ---
    # Conservative on purpose: a wrong title match attributes another institution's abstract to a
    # Lorraine work. Uniqueness on BOTH sides removes the ambiguous cases entirely.
    remaining = need[~need["work_id"].isin(doi_match["work_id"])]
    left = remaining[remaining["title_norm"].str.len().fillna(0) >= MIN_TITLE_CHARS]
    left_unique = left[~left["title_norm"].duplicated(keep=False)]
    hal_titled = hal[hal["hal_title_norm"].notna() & hal["hal_abstract"].notna()]
    hal_titled = hal_titled[hal_titled["hal_title_norm"].str.len() >= MIN_TITLE_CHARS]
    hal_unique = hal_titled[~hal_titled["hal_title_norm"].duplicated(keep=False)]
    title_match = left_unique.merge(hal_unique, left_on="title_norm", right_on="hal_title_norm", how="inner")
    year_ok = (title_match["hal_year"].astype("Float64") - title_match["publication_year"].astype("Float64")).abs() <= 1
    rejected_year = int((~year_ok).sum())
    title_match = title_match[year_ok.fillna(False)]
    print(f"  matched by title: {len(title_match):,} (rejected {rejected_year:,} on a year mismatch; "
          f"{len(left) - len(left_unique):,} corpus and {len(hal_titled) - len(hal_unique):,} HAL "
          f"records skipped as ambiguous duplicates)")

    matched = pd.concat([doi_match.assign(match_route="hal_doi"),
                         title_match.assign(match_route="hal_title")], ignore_index=True)
    matched = matched.drop_duplicates("work_id")

    # Drop title-echo "abstracts" before they are ever counted as coverage (see is_title_echo).
    echo = matched.apply(lambda r: is_title_echo(r["hal_abstract"], r["title"]), axis=1)
    if len(matched):
        print(f"  rejected {int(echo.sum()):,} matches whose HAL abstract is just the title echoed")
        matched = matched[~echo]

    if args.calibrate:
        print(f"\nCALIBRATION (2 HAL pages only): would fill {len(matched):,} abstracts")
        for row in matched.head(5).itertuples():
            print(f"  {row.work_id} <- {row.hal_id} via {row.match_route} "
                  f"({row.hal_abstract_chars} chars, {row.hal_lang})")
            print(f"     corpus title: {str(row.title)[:80]}")
            print(f"     HAL abstract: {str(row.hal_abstract)[:120]}")
        print("\ncalibration complete — review the match quality, then run the full harvest.")
        return

    # --- fill, then report ---
    fill = matched.set_index("work_id")
    enriched = corpus.copy()
    mask = enriched["work_id"].isin(fill.index)
    enriched.loc[mask, "abstract"] = enriched.loc[mask, "work_id"].map(fill["hal_abstract"])
    enriched.loc[mask, "abstract_source"] = enriched.loc[mask, "work_id"].map(
        fill["match_route"].map({"hal_doi": "hal_structure_doi", "hal_title": "hal_structure_title"})
    )
    enriched.loc[mask, "abstract_lang"] = enriched.loc[mask, "work_id"].map(fill["hal_lang"])
    enriched["abstract_chars"] = enriched["abstract"].str.len().fillna(0).astype(int)
    # Carry the HAL identifiers for every corpus work we could align, abstract or not — 45_build_authors
    # will want idHAL and ORCID, and the lab struct ids are a second attribution route.
    all_ids = pd.concat([
        corpus.merge(hal[hal["hal_doi"].notna()].drop_duplicates("hal_doi"),
                     left_on="doi", right_on="hal_doi", how="inner")[
            ["work_id", "hal_id", "hal_docid", "hal_doctype", "hal_author_idhal_pairs",
             "hal_n_authors_with_idhal", "hal_n_authors_with_orcid",
             "hal_lab_struct_ids"]].assign(match_route="hal_doi"),
        matched[["work_id", "hal_id", "hal_docid", "hal_doctype", "hal_author_idhal_pairs",
                 "hal_n_authors_with_idhal", "hal_n_authors_with_orcid", "hal_lab_struct_ids",
                 "match_route"]],
    ], ignore_index=True).drop_duplicates("work_id")

    out_corpus = tables / "corpus_abstracts.parquet"
    out_hal = tables / "hal_records.parquet"
    out_links = tables / "hal_work_links.parquet"
    enriched.to_parquet(out_corpus, index=False, compression=CONFIG["storage"]["compression"])
    hal.to_parquet(out_hal, index=False, compression=CONFIG["storage"]["compression"])
    all_ids.to_parquet(out_links, index=False, compression=CONFIG["storage"]["compression"])

    before = corpus["abstract"].notna()
    after = enriched["abstract"].notna()
    still = enriched[~after]
    lines = [
        f"- HAL harvest: **{len(hal):,}** records (structId {HAL_STRUCT_ID} OR collCode {HAL_COLL_CODE}, "
        f"{CONFIG['window']['year_from']}-{CONFIG['window']['year_to']}); "
        f"{hal['hal_abstract'].notna().sum():,} carry an abstract, only {hal['hal_doi'].notna().sum():,} a DOI",
        f"- abstract coverage **before this step: {before.mean():.1%}** ({before.sum():,})",
        f"- abstract coverage **after : {after.mean():.1%}** ({after.sum():,})",
        f"- filled here: **{int(mask.sum()):,}** "
        f"(DOI route {len(doi_match):,} · title route {len(title_match):,})",
        f"- HAL records linked to **{len(all_ids):,}** corpus works; "
        f"{int((all_ids['hal_n_authors_with_idhal'] > 0).sum()):,} have >=1 author with an idHAL "
        f"(attributable via the aligned `authFullNameIdHal_fs` pairs) and "
        f"{int((all_ids['hal_n_authors_with_orcid'] > 0).sum()):,} have >=1 author ORCID "
        f"(NOT attributable: HAL publishes no aligned name-to-ORCID field)",
        f"- still without an abstract: **{len(still):,}** "
        f"({int((~still['has_doi']).sum()):,} of them have no DOI)",
        "",
        "| Source of the stored abstract | Works |",
        "|---|---|",
    ]
    for source_name, count in enriched.loc[after, "abstract_source"].value_counts().items():
        lines.append(f"| {source_name} | {count:,} |")
    lines += ["", "| Doc type | Coverage before | Coverage after |", "|---|---|---|"]
    for doc_type in corpus["type"].value_counts().index:
        total = int((corpus["type"] == doc_type).sum())
        lines.append(f"| {doc_type} | {(before & (corpus['type'] == doc_type)).sum()/total:.1%} | "
                     f"{(after & (enriched['type'] == doc_type)).sum()/total:.1%} |")

    report = ROOT / CONFIG["paths"]["reports"] / "hal_structure_harvest.md"
    report.write_text("# HAL structure harvest (20b) — reaching the DOI-less works\n\n"
                      + "\n".join(lines) + "\n", encoding="utf-8")
    Manifest(snapshot).record_step(
        "20b_hal_structure_harvest",
        filters=f"structId_i:{HAL_STRUCT_ID} OR collCode_s:{HAL_COLL_CODE}, publicationDateY_i "
                f"[{CONFIG['window']['year_from']} TO {CONFIG['window']['year_to']}]",
        select=FL,
        api_base=HAL_ENDPOINT,
        counts={
            "hal_records": len(hal),
            "filled_doi_route": len(doi_match),
            "filled_title_route": len(title_match),
            "coverage_after": round(float(after.mean()), 4),
            "hal_links": len(all_ids),
        },
        files=[out_corpus, out_hal, out_links],
        params={
            "rows_per_page": ROWS_PER_PAGE,
            "title_match_rules": "unique normalised title on both sides, |year delta| <= 1, "
                                 f"min {MIN_TITLE_CHARS} chars",
        },
        notes="Bulk cursorMark harvest via the vendored cookbook connector (D39); conservative matching.",
    )
    append_summary(snapshot, "20b_hal_structure_harvest", lines[:6])

    # compress the harvest, per D38
    if CONFIG["storage"].get("compress_raw_jsonl") and raw_path.exists():
        import zstandard

        target = raw_path.with_suffix(raw_path.suffix + ".zst")
        compressor = zstandard.ZstdCompressor(level=CONFIG["storage"].get("raw_compression_level", 10))
        with raw_path.open("rb") as src, target.open("wb") as dst:
            compressor.copy_stream(src, dst)
        raw_path.unlink()
        print(f"  compressed HAL raw -> {target.name} ({target.stat().st_size/1e6:.1f} MB)")

    print("\n".join(lines))
    print(f"\nwrote {out_corpus.name}, {out_hal.name}, {out_links.name} and {report}")


if __name__ == "__main__":
    main()
