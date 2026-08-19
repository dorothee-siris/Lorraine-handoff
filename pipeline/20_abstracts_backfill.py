"""20_abstracts_backfill.py — recover missing abstracts from HAL, then OpenAIRE, by DOI.

Why this step carries more weight than it looks (plan §8): v1 tagged SDGs at 80.1% abstract coverage
because 6,311 abstracts had been recovered via BigQuery — but only the work_id list was ever archived,
never the text. That lost text is the measured dominant cause of the v1 vs re-tag SDG difference. This
step replaces that undocumented recovery with a reproducible one.

Rules (D6): only fill where OpenAlex has nothing; try HAL then OpenAIRE; KEEP THE LONGEST; never
replace a longer abstract with a shorter one; record the source, length and language of every value.

Both APIs are free. HAL is queried in batches (many DOIs per call); OpenAIRE is one call per DOI, so
it only sees what HAL could not resolve. Every response is cached to disk as JSONL, so an interrupted
run resumes without re-querying anything.

Usage
  python pipeline/20_abstracts_backfill.py --calibrate         # 25 works, no durable writes
  python pipeline/20_abstracts_backfill.py --snapshot 2026-08-10
  python pipeline/20_abstracts_backfill.py --limit 500         # partial run, still resumable
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.openalex import ascii_safe_stdout, load_env  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)
ABS = CONFIG["abstracts"]

HAL_BATCH = 50          # DOIs per HAL query; the URL stays well inside limits
HAL_PAUSE = 0.2
OPENAIRE_PAUSE = 0.15
# The HAL deposit notice that contaminates real abstracts (54 works = 0.19% in v1). Its presence is
# recorded, not silently trusted: it is also why English-titled works get detected as French.
HAL_BOILERPLATE = "emanant des etablissements"
MIN_USEFUL_CHARS = 20   # shorter than this is a fragment, not an abstract


def clean_text(raw: str | None) -> str | None:
    """Strip JATS/HTML markup and normalise whitespace. OpenAIRE returns <jats:p> wrappers."""
    if not raw or not isinstance(raw, str):
        return None
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def deaccent(text: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


class Cache:
    """Append-only JSONL cache keyed by DOI, so a resumed run re-queries nothing."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, dict] = {}
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # a torn last line from a killed run
                    self.data[record["doi"]] = record
        self.handle = path.open("a", encoding="utf-8")

    def __contains__(self, doi: str) -> bool:
        return doi in self.data

    def put(self, doi: str, abstract: str | None, lang: str | None = None, extra: dict | None = None) -> None:
        record = {"doi": doi, "abstract": abstract, "lang": lang, **(extra or {})}
        self.data[doi] = record
        self.handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.handle.flush()

    def close(self) -> None:
        self.handle.close()


def hal_lookup(session: requests.Session, dois: list[str], cache: Cache) -> None:
    """Batched HAL query. HAL matches DOIs case-insensitively, so results are mapped back lowercased."""
    todo = [d for d in dois if d not in cache]
    print(f"  HAL: {len(todo):,} DOIs to query in batches of {HAL_BATCH}")
    for start in range(0, len(todo), HAL_BATCH):
        batch = todo[start : start + HAL_BATCH]
        query = " OR ".join(f'"{doi}"' for doi in batch)
        try:
            response = session.get(
                f"{ABS['hal_base_url']}/search/",
                params={
                    "q": f"doiId_s:({query})",
                    "fl": "doiId_s,abstract_s,language_s",
                    "rows": HAL_BATCH * 2,
                    "wt": "json",
                },
                timeout=120,
            )
            found: dict[str, dict] = {}
            if response.ok:
                for doc in response.json()["response"]["docs"]:
                    doi = str(doc.get("doiId_s") or "").strip().lower()
                    if not doi:
                        continue
                    values = doc.get("abstract_s") or []
                    values = values if isinstance(values, list) else [values]
                    texts = [t for t in (clean_text(v) for v in values) if t]
                    best = max(texts, key=len) if texts else None
                    languages = doc.get("language_s") or []
                    found[doi] = {
                        "abstract": best if best and len(best) >= MIN_USEFUL_CHARS else None,
                        "lang": (languages[0] if isinstance(languages, list) and languages else None),
                    }
            else:
                print(f"    HAL HTTP {response.status_code} on batch {start // HAL_BATCH}")
        except requests.RequestException as exc:
            print(f"    HAL request failed on batch {start // HAL_BATCH}: {exc!r}")
            found = {}
        for doi in batch:
            hit = found.get(doi, {})
            cache.put(doi, hit.get("abstract"), hit.get("lang"), {"found_in_hal": doi in found})
        if (start // HAL_BATCH) % 20 == 0:
            resolved = sum(1 for d in cache.data.values() if d.get("abstract"))
            print(f"    {start + len(batch):,} / {len(todo):,} queried, {resolved:,} abstracts so far",
                  flush=True)
        time.sleep(HAL_PAUSE)


class OpenAireClient:
    """OpenAIRE Graph API v1. The stored access token expires (~1 h) — refresh it at runtime."""

    def __init__(self, env: dict[str, str]) -> None:
        self.refresh_token = env.get("OPENAIRE_REFRESH_TOKEN")
        self.session = requests.Session()
        self.token: str | None = None
        self.refresh()

    def refresh(self) -> None:
        response = self.session.get(
            "https://services.openaire.eu/uoa-user-management/api/users/getAccessToken",
            params={"refreshToken": self.refresh_token},
            timeout=60,
        )
        response.raise_for_status()
        self.token = response.json()["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        print("  OpenAIRE: access token refreshed")

    def abstract_for(self, doi: str, retried: bool = False) -> str | None:
        try:
            response = self.session.get(
                f"{ABS['openaire_base_url']}/graph/v1/researchProducts",
                params={"pid": doi, "pageSize": 5},  # NOTE: the parameter is `pid`, not `doi`
                timeout=90,
            )
        except requests.RequestException:
            return None
        if response.status_code in (401, 403) and not retried:
            self.refresh()
            return self.abstract_for(doi, retried=True)
        if not response.ok:
            return None
        best = ""
        for result in response.json().get("results") or []:
            for description in result.get("descriptions") or []:
                text = clean_text(description if isinstance(description, str) else None)
                if text and len(text) > len(best):
                    best = text
        return best if len(best) >= MIN_USEFUL_CHARS else None


def detect_language(text: str) -> tuple[str | None, float | None]:
    """py3langid with norm_probs=True — the raw classify() score is a log-probability, not a confidence."""
    try:
        from py3langid.langid import MODEL_FILE, LanguageIdentifier

        global _IDENTIFIER
        try:
            identifier = _IDENTIFIER
        except NameError:
            identifier = _IDENTIFIER = LanguageIdentifier.from_pickled_model(MODEL_FILE, norm_probs=True)
        lang, probability = identifier.classify(text)
        return lang, float(probability)
    except Exception:
        return None, None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--skip-openaire", action="store_true", help="HAL only (the §11 fallback)")
    args = parser.parse_args()

    env = load_env(CONFIG["secrets"]["env_file"])
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    corpus_path = snapshot / "tables" / "corpus.parquet"
    corpus = pd.read_parquet(corpus_path)
    print(f"snapshot {snapshot.name}: corpus {len(corpus):,} works")

    missing = corpus[corpus["abstract"].isna()]
    targets = missing[missing["has_doi"]].copy()
    print(f"  with an OpenAlex abstract : {corpus['abstract'].notna().sum():,} "
          f"({corpus['abstract'].notna().mean():.1%})")
    print(f"  missing                   : {len(missing):,}")
    print(f"  missing WITH a DOI        : {len(targets):,}  <- backfill targets")
    print(f"  missing WITHOUT a DOI     : {len(missing) - len(targets):,}  <- unreachable by DOI")

    if args.limit:
        targets = targets.head(args.limit)
    if args.calibrate:
        targets = targets.head(25)
        print("\nCALIBRATION — 25 works, caches to a scratch dir, no durable writes\n")

    cache_dir = (ROOT / "cache" / "abstracts_calibration") if args.calibrate else (ROOT / ABS["cache_dir"])
    dois = [d for d in targets["doi"].dropna().unique().tolist()]

    hal_cache = Cache(cache_dir / "hal.jsonl")
    session = requests.Session()
    session.headers.update({"User-Agent": f"SIRIS-Lorraine-v2 ({env.get('OPENALEX_MAILTO','')})"})
    print(f"\nHAL pass over {len(dois):,} DOIs")
    hal_lookup(session, dois, hal_cache)
    hal_hits = {d: r for d, r in hal_cache.data.items() if r.get("abstract")}
    print(f"  HAL resolved {len(hal_hits):,} / {len(dois):,} ({len(hal_hits)/max(len(dois),1):.1%})")

    openaire_cache = Cache(cache_dir / "openaire.jsonl")
    openaire_hits: dict[str, dict] = {}
    if not args.skip_openaire:
        remaining = [d for d in dois if d not in hal_hits and d not in openaire_cache]
        print(f"\nOpenAIRE pass over {len(remaining):,} DOIs HAL could not resolve")
        client = OpenAireClient(env)
        for index, doi in enumerate(remaining, start=1):
            text = client.abstract_for(doi)
            openaire_cache.put(doi, text)
            if index % 250 == 0:
                got = sum(1 for r in openaire_cache.data.values() if r.get("abstract"))
                print(f"    {index:,} / {len(remaining):,} queried, {got:,} abstracts", flush=True)
            time.sleep(OPENAIRE_PAUSE)
        openaire_hits = {d: r for d, r in openaire_cache.data.items() if r.get("abstract")}
        if remaining:
            print(f"  OpenAIRE resolved {sum(1 for d in remaining if d in openaire_hits):,} of the "
                  f"{len(remaining):,} it was asked this run "
                  f"({sum(1 for d in remaining if d in openaire_hits)/len(remaining):.1%}); "
                  f"{len(openaire_hits):,} in cache overall")
        else:
            print(f"  OpenAIRE: nothing new to query — {len(openaire_hits):,} abstracts served "
                  f"from cache")
    else:
        print("\nOpenAIRE skipped (--skip-openaire)")

    # --- merge: keep the longest, never shorten ---
    rows: list[dict] = []
    for work_id, doi, existing in targets[["work_id", "doi", "abstract"]].itertuples(index=False):
        candidates: list[tuple[str, str]] = []
        if isinstance(existing, str) and existing.strip():
            candidates.append(("openalex", existing))
        for source, store in (("hal", hal_cache.data), ("openaire", openaire_cache.data)):
            text = (store.get(doi) or {}).get("abstract")
            if text:
                candidates.append((source, text))
        if not candidates:
            continue
        source, text = max(candidates, key=lambda pair: len(pair[1]))
        lang, probability = detect_language(text)
        rows.append(
            {
                "work_id": work_id,
                "abstract": text,
                "abstract_source": source,
                "abstract_chars": len(text),
                "abstract_lang": lang,
                "abstract_lang_prob": probability,
                "hal_boilerplate": HAL_BOILERPLATE in deaccent(text).lower(),
                "candidates_found": len(candidates),
            }
        )
    backfilled = pd.DataFrame(rows)
    print(f"\nbackfilled {len(backfilled):,} works "
          f"({len(backfilled)/max(len(targets),1):.1%} of the targets)")

    if args.calibrate:
        if not backfilled.empty:
            print(backfilled[["work_id", "abstract_source", "abstract_chars", "abstract_lang",
                              "abstract_lang_prob", "hal_boilerplate"]].to_string(index=False))
            sample = backfilled.iloc[0]
            print(f"\nsample {sample['work_id']} via {sample['abstract_source']}:")
            print("   ", sample["abstract"][:400])
        print("\ncalibration complete — review, then run the full pass.")
        hal_cache.close(), openaire_cache.close()
        return

    # --- write the enriched corpus, without mutating corpus.parquet ---
    enriched = corpus.merge(
        backfilled.rename(columns={c: f"bf_{c}" for c in backfilled.columns if c != "work_id"}),
        on="work_id",
        how="left",
    )
    filled = enriched["bf_abstract"].notna()
    # never replace a longer abstract with a shorter one (D6) — targets had none, so this is a guard
    longer = filled & (enriched["bf_abstract"].str.len().fillna(0) < enriched["abstract"].str.len().fillna(0))
    assert not longer.any(), f"{int(longer.sum())} works would have been given a SHORTER abstract"
    enriched["abstract"] = enriched["bf_abstract"].where(filled, enriched["abstract"])
    enriched["abstract_source"] = enriched["bf_abstract_source"].where(filled, enriched["abstract_source"])
    enriched["abstract_chars"] = enriched["abstract"].str.len().fillna(0).astype(int)
    enriched["abstract_lang"] = enriched["bf_abstract_lang"]
    enriched["hal_boilerplate"] = enriched["bf_hal_boilerplate"].fillna(False)
    enriched = enriched.drop(columns=[c for c in enriched.columns if c.startswith("bf_")])

    out_corpus = snapshot / "tables" / "corpus_abstracts.parquet"
    out_provenance = snapshot / "tables" / "abstracts_backfill.parquet"
    enriched.to_parquet(out_corpus, index=False, compression=CONFIG["storage"]["compression"])
    backfilled.to_parquet(out_provenance, index=False, compression=CONFIG["storage"]["compression"])

    # --- report: coverage before/after, per source and per year ---
    before = corpus["abstract"].notna()
    after = enriched["abstract"].notna()
    v1 = CONFIG["baselines_v1"]
    lines = [
        f"- corpus: **{len(corpus):,}** works",
        f"- abstract coverage **before: {before.mean():.1%}** ({before.sum():,})",
        f"- abstract coverage **after : {after.mean():.1%}** ({after.sum():,})",
        f"- v1 comparison: text present {v1['abstract_coverage_text_present']:.1%} · "
        f"v1 effective (incl. the lost BigQuery text) {v1['abstract_coverage_v1_effective']:.1%}",
        f"- recovered by HAL: {(backfilled['abstract_source'] == 'hal').sum():,} · "
        f"by OpenAIRE: {(backfilled['abstract_source'] == 'openaire').sum():,}",
        f"- still missing: **{(~after).sum():,}** "
        f"(of which {int((~after & ~enriched['has_doi']).sum()):,} have no DOI at all)",
        f"- HAL deposit boilerplate detected in {int(backfilled['hal_boilerplate'].sum()):,} recovered "
        f"abstracts (v1: 54 works)",
        "",
        "| Year | Before | After | Recovered |",
        "|---|---|---|---|",
    ]
    for year in sorted(corpus["publication_year"].dropna().unique()):
        mask_before = before & (corpus["publication_year"] == year)
        mask_after = after & (enriched["publication_year"] == year)
        total = int((corpus["publication_year"] == year).sum())
        lines.append(
            f"| {int(year)} | {mask_before.sum()/total:.1%} | {mask_after.sum()/total:.1%} | "
            f"{int(mask_after.sum() - mask_before.sum()):,} |"
        )
    lines += ["", "| Doc type | Before | After |", "|---|---|---|"]
    for doc_type in corpus["type"].value_counts().index:
        total = int((corpus["type"] == doc_type).sum())
        lines.append(
            f"| {doc_type} | {(before & (corpus['type'] == doc_type)).sum()/total:.1%} | "
            f"{(after & (enriched['type'] == doc_type)).sum()/total:.1%} |"
        )
    if "abstract_lang" in enriched:
        counts = enriched.loc[after, "abstract_lang"].value_counts().head(8)
        lines += ["", "Detected language of recovered abstracts: "
                  + " · ".join(f"{k} {v:,}" for k, v in counts.items())]

    report = ROOT / CONFIG["paths"]["reports"] / "abstract_backfill.md"
    report.write_text("# Abstract backfill — HAL then OpenAIRE\n\n" + "\n".join(lines) + "\n",
                      encoding="utf-8")
    Manifest(snapshot).record_step(
        "20_abstracts_backfill",
        counts={
            "corpus": len(corpus),
            "targets": len(targets),
            "backfilled": len(backfilled),
            "coverage_before": round(float(before.mean()), 4),
            "coverage_after": round(float(after.mean()), 4),
        },
        files=[out_corpus, out_provenance],
        params={
            "order": ABS["backfill_order"],
            "selection": "longest",
            "hal_batch": HAL_BATCH,
            "min_useful_chars": MIN_USEFUL_CHARS,
            "openaire_endpoint": "graph/v1/researchProducts?pid=",
        },
        notes="HAL batched by DOI, OpenAIRE per DOI with runtime token refresh; markup stripped.",
    )
    append_summary(snapshot, "20_abstracts_backfill", lines[:8])
    print("\n".join(lines))
    hal_cache.close(), openaire_cache.close()
    print(f"\nwrote {out_corpus.name}, {out_provenance.name} and {report}")


if __name__ == "__main__":
    main()
