"""49w_pull_peers_wide.py -- R7 full peer corpora wide pull (pass 5, S2).

Authority: Lorraine\\CLAUDE.md pass-5 kickoff, R7 (locked 2026-08-18) -- "Full peer corpora, one
wide pull" replacing/extending the pass-4 narrow pull for the 9 peers. This is a NEW script; it
never imports from, nor modifies, `49_pull_peer_benchmark.py` or `49b_build_peer_benchmark.py` --
other streams depend on those two staying byte-identical.

Recipe (identical FILTER shape to pass 4, only the select list is wider):
  authorships.institutions.id:<peer_id>, publication_year:<window>,
  type:article|book-chapter|review|book|conference-paper, is_retracted:false, is_paratext:false
select = id, doi, title, abstract_inverted_index, publication_year, type, cited_by_count,
         primary_topic (FULL object -- id/display_name/score/subfield/field/domain, needed for
         frontierness), sustainable_development_goals, language.
NO authorships (payload-heavy, no consumer -- R7 explicit exclusion).

The filter string is built from the SAME config.yaml keys pass 4 reads
(`corpus_filter.doc_types_keep`, `window.year_from/year_to`) so both scripts drift together if
config ever changes; `verify_filter_matches_pass4()` below dynamically imports the actual
pass-4 module (read-only -- exec's its top-level code, never its `main()`) and diffs the two
functions' output on a dummy id, printed at the top of every run, per the pass-4 lens lesson
("the +/-3% band checks magnitude, not recipe correctness").

Golden comparison base: `Streamlit/data/bench_peers.parquet` (node_level=='all',
conf_state=='all' rows), i.e. pass 4's own ACTUAL pulled totals -- not the frozen G8 CSV probe
directly (the two were themselves within 0.04% of each other, so either is a valid base; the
parquet is what the mission specifies).

Calibration peer: the SMALLEST of the 9 by pass-4 golden total (picked dynamically, not
hardcoded) -- this lands on Universite Clermont Auvergne (I198244214, golden 13,155), not
Tampere (pass 4's calibration choice, picked instead for "smallest CLEAN id").

Spend guard (R7 hard guard): accumulates ACTUAL `meta.cost_usd` from every response across the
WHOLE run into a persisted file (`raw/peers/SPEND_GUARD_pass5.json`), so a resume keeps the
running total. Aborts cleanly at $0.60. A cost PROJECTION (works/200 * measured $/page) is
printed as a monitor line only after calibration -- it never drives the abort decision.

Resumable: per-peer done-marker = existence of `<peer_id>_wide.jsonl.zst` (mirrors pass 4's
parquet-existence marker). Mid-crawl checkpoint = `<peer_id>_wide.cursor` (OpenAlex cursor,
written every page like `lib.openalex.crawl`) + `<peer_id>_wide.checkpoint.json` (cumulative
pages/works/coverage-counters/cost, written every 100 pages and at crawl end) -- a re-run skips
completed peers outright and resumes a partial one from its saved cursor with 0 re-fetch.

Usage
  python pipeline/49w_pull_peers_wide.py --calibrate               # smallest peer only, vs golden
  python pipeline/49w_pull_peers_wide.py --calibrate --max-pages 5  # DEBUG: force an early stop,
                                                                     # for the resume demo only
  python pipeline/49w_pull_peers_wide.py                            # all 9 status==ok peers, resumable
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.openalex import OpenAlexClient, ascii_safe_stdout, load_env, reconstruct_abstract  # noqa: E402
from lib.snapshot import load_config, resolve_snapshot, sha256, utc_now  # noqa: E402

ascii_safe_stdout()

CONFIG = load_config(ROOT)
DOC_TYPES = CONFIG["corpus_filter"]["doc_types_keep"]
YEAR_FROM, YEAR_TO = CONFIG["window"]["year_from"], CONFIG["window"]["year_to"]

REGISTRY_PATH = ROOT / "inputs" / "overlays" / "bench_peers.csv"
GOLDEN_PARQUET = ROOT / "Streamlit" / "data" / "bench_peers.parquet"
PASS4_SCRIPT = ROOT / "pipeline" / "49_pull_peer_benchmark.py"

WIDE_SELECT_LIST = [
    "id", "doi", "title", "abstract_inverted_index", "publication_year",
    "type", "cited_by_count", "primary_topic",
    "sustainable_development_goals", "language",
]
WIDE_SELECT_STR = ",".join(WIDE_SELECT_LIST)

SPEND_LIMIT_USD = 0.60          # R7 hard guard, on ACTUAL accumulated meta.cost_usd
CHECKPOINT_EVERY_PAGES = 100    # persist cursor + running counts, R7 "same spirit as pass-4"
PROGRESS_EVERY_PAGES = 50       # console line cadence, batched (no \r spam, cp1252 console)


def peer_filter(peer_id: str) -> str:
    """The R7 filter -- SAME shape as pass 4's `peer_filter`, config-driven off the same keys."""
    types = "|".join(DOC_TYPES)
    return (
        f"authorships.institutions.id:{peer_id},"
        f"publication_year:{YEAR_FROM}-{YEAR_TO},"
        f"type:{types},is_retracted:false,is_paratext:false"
    )


def verify_filter_matches_pass4() -> tuple[str, str, bool]:
    """Dynamically import the ACTUAL pass-4 module (read-only: its top-level code just loads
    config and defines functions; `main()` is never called, guarded by its own __main__ check)
    and diff its `peer_filter` output against ours on a dummy id. Real diff, not an eyeball one."""
    spec = importlib.util.spec_from_file_location("pass4_bench_peer_pull", PASS4_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    dummy = "I000000000"
    mine, theirs = peer_filter(dummy), mod.peer_filter(dummy)
    return mine, theirs, mine == theirs


def load_registry() -> pd.DataFrame:
    if not REGISTRY_PATH.exists():
        raise SystemExit(f"missing registry {REGISTRY_PATH}")
    df = pd.read_csv(REGISTRY_PATH, encoding="utf-8", keep_default_na=False)
    return df[df["status"] == "ok"].reset_index(drop=True)


def load_golden() -> pd.DataFrame:
    """Pass-4's OWN pulled totals (all-fields, all-conference-states rows), per the mission's
    stated comparison base -- not the frozen probe CSV directly."""
    if not GOLDEN_PARQUET.exists():
        raise SystemExit(f"missing golden {GOLDEN_PARQUET} -- pass 4's bench_peers table")
    df = pd.read_parquet(GOLDEN_PARQUET)
    g = df[(df["node_level"] == "all") & (df["conf_state"] == "all")][
        ["entity_id", "entity_name", "works"]
    ].rename(columns={"works": "golden_works"})
    return g


def pick_calibration_peer(registry: pd.DataFrame, golden: pd.DataFrame) -> tuple[str, str, int]:
    merged = registry.merge(golden, left_on="peer_id", right_on="entity_id")
    row = merged.loc[merged["golden_works"].idxmin()]
    return row["peer_id"], row["display_name"], int(row["golden_works"])


class SpendGuard:
    """Persists ACTUAL accumulated `meta.cost_usd` across the whole run (and across resumes)."""

    def __init__(self, path: Path, limit: float) -> None:
        self.path = path
        self.limit = limit
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.total_cost_usd = float(data.get("total_cost_usd", 0.0))
        self.total_calls = int(data.get("total_calls", 0))

    def add(self, cost_usd: float, calls: int = 1) -> None:
        self.total_cost_usd += cost_usd
        self.total_calls += calls
        self._save()

    def over_limit(self) -> bool:
        return self.total_cost_usd >= self.limit

    def _save(self) -> None:
        self.path.write_text(json.dumps({
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_calls": self.total_calls,
            "updated_utc": utc_now(),
        }, indent=1), encoding="utf-8")


def load_checkpoint(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "pages_done": 0, "works_written": 0,
        "has_abstract": 0, "has_primary_topic": 0, "has_sdg": 0, "has_language": 0,
        "cost_usd": 0.0,
    }


def save_checkpoint(path: Path, cp: dict) -> None:
    out = dict(cp)
    out["updated_utc"] = utc_now()
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")


def compress_raw(path: Path, level: int) -> tuple[Path, str, float]:
    """Checksum BEFORE compression (matches pass-4's D38 discipline), then zstd-compress and
    drop the plain .jsonl. Returns (target_path, sha256_of_uncompressed, uncompressed_MB)."""
    import zstandard

    digest = sha256(path)
    raw_mb = path.stat().st_size / 1e6
    target = path.with_suffix(path.suffix + ".zst")
    compressor = zstandard.ZstdCompressor(level=level)
    with path.open("rb") as src, target.open("wb") as dst:
        compressor.copy_stream(src, dst)
    path.unlink()
    return target, digest, round(raw_mb, 1)


def crawl_peer_wide(
    client: OpenAlexClient, raw_dir: Path, peer_id: str, label: str,
    spend_guard: SpendGuard, max_pages: int | None = None,
) -> dict:
    """Pulls one peer's full wide corpus. `max_pages` is a DEBUG-only hook (never used in the
    real pull) that stops after N pages THIS invocation, to demonstrate checkpoint+resume."""
    out_path = raw_dir / f"{peer_id}_wide.jsonl"
    zst_path = raw_dir / f"{peer_id}_wide.jsonl.zst"
    cursor_path = raw_dir / f"{peer_id}_wide.cursor"
    checkpoint_path = raw_dir / f"{peer_id}_wide.checkpoint.json"
    filt = peer_filter(peer_id)

    if zst_path.exists():
        cp = load_checkpoint(checkpoint_path)
        print(f"  {label} ({peer_id}): already pulled ({cp['works_written']:,} works, "
              f"{cp['pages_done']} pages) -- skipping, no API touched")
        return {"peer_id": peer_id, "label": label, "works": cp["works_written"],
                "pages": cp["pages_done"], "skipped": True, "aborted": False, "checkpoint": cp}

    cp = load_checkpoint(checkpoint_path)
    saved_cursor = cursor_path.read_text(encoding="utf-8").strip() if cursor_path.exists() else ""
    if saved_cursor == "DONE":
        cursor = None  # crawl finished previously but never compressed/finalized -- finalize now
    elif saved_cursor:
        cursor = saved_cursor
        print(f"  {label} ({peer_id}): RESUMING from saved cursor -- already "
              f"{cp['works_written']:,} works / {cp['pages_done']} pages / "
              f"${cp['cost_usd']:.4f} on this peer, 0 re-fetch")
    else:
        cursor = "*"

    mode = "a" if out_path.exists() and saved_cursor not in ("", "*") else "w"
    aborted = False
    pages_this_call = 0
    with out_path.open(mode, encoding="utf-8") as handle:
        while cursor:
            page = client.get("/works", filter=filt, per_page=CONFIG["openalex"]["per_page"],
                               cursor=cursor, select=WIDE_SELECT_STR)
            cost = (page.get("meta") or {}).get("cost_usd")
            cost = cost if cost is not None else 0.0001
            spend_guard.add(cost)
            cp["cost_usd"] = cp.get("cost_usd", 0.0) + cost
            results = page["results"]
            if not results:
                cursor_path.write_text("DONE", encoding="utf-8")
                cursor = None
                break
            for work in results:
                handle.write(json.dumps(work, ensure_ascii=False) + "\n")
                if reconstruct_abstract(work.get("abstract_inverted_index")):
                    cp["has_abstract"] += 1
                if work.get("primary_topic"):
                    cp["has_primary_topic"] += 1
                if work.get("sustainable_development_goals"):
                    cp["has_sdg"] += 1
                if work.get("language"):
                    cp["has_language"] += 1
            cp["works_written"] += len(results)
            cp["pages_done"] += 1
            pages_this_call += 1
            cursor = page["meta"].get("next_cursor")
            cursor_path.write_text(cursor or "DONE", encoding="utf-8")

            if cp["pages_done"] % CHECKPOINT_EVERY_PAGES == 0 or not cursor:
                save_checkpoint(checkpoint_path, cp)
            if cp["pages_done"] % PROGRESS_EVERY_PAGES == 0:
                print(f"  {label}: {cp['works_written']:,} works, {cp['pages_done']} pages, "
                      f"run spend ${spend_guard.total_cost_usd:.4f}", flush=True)
            if spend_guard.over_limit():
                aborted = True
                save_checkpoint(checkpoint_path, cp)
                break
            if max_pages and pages_this_call >= max_pages:
                save_checkpoint(checkpoint_path, cp)
                print(f"  {label}: DEBUG STOP at max_pages={max_pages} ({cp['works_written']:,} "
                      f"works so far) -- cursor + checkpoint saved for the resume demo")
                return {"peer_id": peer_id, "label": label, "works": cp["works_written"],
                        "pages": cp["pages_done"], "skipped": False, "aborted": False,
                        "debug_stop": True, "checkpoint": cp}

    save_checkpoint(checkpoint_path, cp)
    if aborted:
        print(f"ABORT (spend guard): run spend ${spend_guard.total_cost_usd:.4f} >= "
              f"${SPEND_LIMIT_USD:.2f} mid-crawl on {label} ({peer_id}). Cursor + checkpoint "
              f"saved -- rerun this script to resume, no calls lost.")
        return {"peer_id": peer_id, "label": label, "works": cp["works_written"],
                "pages": cp["pages_done"], "skipped": False, "aborted": True, "checkpoint": cp}

    zst_final, digest, raw_mb = compress_raw(out_path, CONFIG["storage"].get("raw_compression_level", 10))
    return {"peer_id": peer_id, "label": label, "works": cp["works_written"],
            "pages": cp["pages_done"], "skipped": False, "aborted": False,
            "raw_mb": raw_mb, "raw_sha256": digest, "checkpoint": cp}


def record_manifest_entry(manifest: dict, result: dict, filter_string: str, this_pull_date: str) -> None:
    peer_id = result["peer_id"]
    cp = result.get("checkpoint", {})
    works = max(cp.get("works_written", 0), 1)
    entry = manifest["peers"].get(peer_id, {})
    entry.update({
        "display_name": result["label"],
        "pull_datetime_utc_last_touch": this_pull_date,
        "filter": filter_string,
        "select": WIDE_SELECT_LIST,
        "per_page": CONFIG["openalex"]["per_page"],
        "pages": result.get("pages", cp.get("pages_done")),
        "works_pulled": result.get("works", cp.get("works_written")),
        "cost_usd_cum_this_peer": round(cp.get("cost_usd", 0.0), 6),
        "status": ("aborted" if result.get("aborted") else
                    "debug_stop" if result.get("debug_stop") else
                    "skipped_already_done" if result.get("skipped") else "done"),
    })
    if result.get("raw_sha256"):
        entry["sha256_uncompressed"] = result["raw_sha256"]
        entry["raw_mb_uncompressed"] = result.get("raw_mb")
    if not result.get("skipped") and cp.get("works_written"):
        entry["coverage_pct"] = {
            "abstract_present": round(cp.get("has_abstract", 0) / works * 100, 1),
            "primary_topic_present": round(cp.get("has_primary_topic", 0) / works * 100, 1),
            "has_1plus_sdg": round(cp.get("has_sdg", 0) / works * 100, 1),
            "language_populated": round(cp.get("has_language", 0) / works * 100, 1),
        }
    manifest["peers"][peer_id] = entry
    manifest["updated_utc"] = this_pull_date


def golden_delta(peer_id: str, works: int, golden: pd.DataFrame) -> dict:
    row = golden[golden["entity_id"] == peer_id]
    if row.empty:
        return {"golden_works": None, "delta_pct": None, "within_band": None}
    gw = int(row["golden_works"].iloc[0])
    delta_pct = (works - gw) / gw * 100 if gw else float("nan")
    return {"golden_works": gw, "delta_pct": delta_pct, "within_band": abs(delta_pct) <= 3.0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--calibrate", action="store_true",
                         help="pull ONLY the smallest peer (by pass-4 golden total), report vs "
                              "golden + $/page + a 9-peer projection; does not touch the other 8")
    parser.add_argument("--max-pages", type=int, default=None,
                         help="DEBUG/demo only: stop the crawl after N pages this invocation, to "
                              "demonstrate checkpoint+resume. Never pass this for the real pull.")
    args = parser.parse_args()

    print("R7 wide-select filter recipe (config-driven -- must equal pass-4's shape):")
    print(f"  {peer_filter('<peer_id>')}")
    print(f"  select: {WIDE_SELECT_STR}")
    mine, theirs, identical = verify_filter_matches_pass4()
    print(f"  filter-diff vs pipeline/49_pull_peer_benchmark.py (dummy id): "
          f"{'IDENTICAL' if identical else 'DIFFERS -- STOP, review before pulling'}")
    if not identical:
        print(f"    mine:  {mine}")
        print(f"    pass4: {theirs}")
        sys.exit(1)

    registry = load_registry()
    golden = load_golden()
    print(f"registry: {len(registry)} peer(s) status==ok\n")

    env = load_env(CONFIG["secrets"]["env_file"], CONFIG["secrets"]["required"])
    client = OpenAlexClient(CONFIG, env)
    snapshot = resolve_snapshot(CONFIG, args.snapshot)
    raw_dir = snapshot / "raw" / "peers"
    raw_dir.mkdir(parents=True, exist_ok=True)
    spend_guard = SpendGuard(raw_dir / "SPEND_GUARD_pass5.json", SPEND_LIMIT_USD)
    manifest_path = raw_dir / "PULL_MANIFEST_pass5.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"peers": {}}
    this_pull_date = utc_now()

    if args.calibrate:
        peer_id, label, gw = pick_calibration_peer(registry, golden)
        print(f"CALIBRATION -- {label} ({peer_id}), pass-4 golden {gw:,} works "
              f"(smallest of the 9 by pass-4 total)\n")
        cost_before = spend_guard.total_cost_usd
        t0 = time.time()
        result = crawl_peer_wide(client, raw_dir, peer_id, label, spend_guard, max_pages=args.max_pages)
        elapsed = time.time() - t0
        record_manifest_entry(manifest, result, peer_filter(peer_id), this_pull_date)
        manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")

        if result.get("debug_stop"):
            print(f"\nDEBUG STOP demo only -- rerun WITHOUT --max-pages to resume and complete "
                  f"this peer. Cost so far this run: ${spend_guard.total_cost_usd - cost_before:.4f}")
            return
        if result["aborted"]:
            print("\nABORTED at calibration -- spend guard evidence in SPEND_GUARD_pass5.json.")
            sys.exit(2)

        n = result["works"]
        pages = result["pages"]
        cost_this_peer = result["checkpoint"].get("cost_usd", 0.0)
        cost_per_page = cost_this_peer / pages if pages else 0.0
        delta = golden_delta(peer_id, n, golden)
        total_golden_all9 = int(golden.merge(registry, left_on="entity_id", right_on="peer_id")["golden_works"].sum())
        projected_pages_all9 = -(-total_golden_all9 // CONFIG["openalex"]["per_page"])  # ceil
        projected_cost_all9 = projected_pages_all9 * cost_per_page

        print(f"\n{label} ({peer_id}): {n:,} works pulled, {pages} pages, {elapsed:.1f}s")
        print(f"  pass-4 golden (bench_peers.parquet): {delta['golden_works']:,} works")
        print(f"  delta: {delta['delta_pct']:+.2f}%  within +/-3% band: {delta['within_band']}")
        print(f"  actual cost this peer: ${cost_this_peer:.4f}  ({pages} calls, "
              f"${cost_per_page:.6f}/page)")
        print(f"  [MONITOR ONLY, not an abort trigger] projection for all 9 peers: "
              f"~{total_golden_all9:,} works / {CONFIG['openalex']['per_page']} "
              f"~= {projected_pages_all9:,} pages * ${cost_per_page:.6f}/page "
              f"= ${projected_cost_all9:.4f}")
        if not delta["within_band"]:
            print("\n!! CALIBRATION FAILED the +/-3% band -- do not proceed without reviewing "
                  "the filter string above.")
            sys.exit(1)
        if projected_cost_all9 > SPEND_LIMIT_USD:
            print(f"\n!! PROJECTED total ${projected_cost_all9:.4f} > guard ${SPEND_LIMIT_USD:.2f} "
                  f"-- STOP per mission instruction, do not proceed to the full pull.")
            sys.exit(3)
        print("\ncalibration OK -- proceed with the full pull: "
              "python pipeline/49w_pull_peers_wide.py")
        return

    measured: list[dict] = []
    aborted_run = False
    for _, row in registry.iterrows():
        peer_id, label = row["peer_id"], row["display_name"]
        if spend_guard.over_limit():
            aborted_run = True
            print(f"ABORT (spend guard): cumulative run spend ${spend_guard.total_cost_usd:.4f} "
                  f">= ${SPEND_LIMIT_USD:.2f} before starting {label} ({peer_id}) -- not started.")
            break
        result = crawl_peer_wide(client, raw_dir, peer_id, label, spend_guard, max_pages=args.max_pages)
        record_manifest_entry(manifest, result, peer_filter(peer_id), this_pull_date)
        manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
        delta = golden_delta(peer_id, result["works"], golden)
        measured.append({"peer_id": peer_id, "label": label, "works": result["works"],
                          "pages": result["pages"], "skipped": result.get("skipped", False),
                          "cost_usd": result["checkpoint"].get("cost_usd", 0.0), **delta})
        print(f"  {label} ({peer_id}): {result['works']:,} works | golden "
              f"{delta['golden_works']:,} | delta {delta['delta_pct']:+.2f}% | "
              f"within_band={delta['within_band']}")
        if result.get("aborted"):
            aborted_run = True
            break

    print(f"\nrun totals: {spend_guard.total_calls:,} calls this run, "
          f"${spend_guard.total_cost_usd:.4f} cumulative (persisted, guard=${SPEND_LIMIT_USD:.2f})")
    if aborted_run:
        print("!! ABORTED mid-run -- rerun this script to resume the remaining peer(s), "
              "0 calls lost.")
        sys.exit(2)
    print("ALL 9 peers complete (or already cached).")


if __name__ == "__main__":
    main()
