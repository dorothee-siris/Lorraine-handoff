"""49_pull_peer_benchmark.py -- peer direct-id corpus pull for the T4b benchmark (pass 4, G4).

Authority (read in full before editing): BUILD_PLAN.md Sec.G4 + Sec.1 (S4/S5/S9/S10);
docs/pass4_decision_memo.md Sec.3; docs/pass4_challenge_memo.md attacks #12-16 (this stream's
absorbed obligations); docs/benchmark_peer_candidates.md Sec.2a/2b/2c/5 (the recipe + the frozen
evidence + id caveats). Copies the PULL SHAPE of `pipeline/30_pull_france.py` exactly (cursor
crawl, 6-col select, raw zst archive, manifest) -- same select, same parse, same doc-type list --
because the peer/UL comparison is only fair if both sides went through an identical recipe
(G8 Sec.5, "peers-symmetry rule").

Recipe (S5, frozen): per status=='ok' row of `inputs/overlays/bench_peers.csv` --
  authorships.institutions.id:<peer_id>, publication_year:2019-2023,
  type:article|book-chapter|review|book|conference-paper, is_retracted:false, is_paratext:false
select=id,cited_by_count,publication_year,type,primary_topic (subfield.id + field.id kept, same
parse as 30). per_page=200 (config default). This is the DIRECT-id perimeter, not lineage
(Sec.2a): French peers' direct counts run 1.29-2.18x below their own lineage figure (co-tutelle
UMR grafting); foreign peers sit at ~1.00-1.08x. Never switch to lineage: for FR institutions
lineage is corrupted (root CLAUDE.md gotcha), and using it here would silently re-introduce the
exact pathology this project spent Phase 2 rooting out of the France baseline.

Calibration order (S5): Tampere (I166825849) first -- the smallest clean id on the list, verified
id-clean in the G8 probe (legacy TUT/UTA ids hold 0 works). `--calibrate` pulls ONLY Tampere and
reports count vs the frozen G8 CSV golden (must land within +/-3%) plus calls/$ -- gate before
pulling the other 8.

Spend guard (BUILD_PLAN acceptance): hard abort, resumable, if total calls THIS RUN exceed 10,000
(~$1, the G4 cap). Expected total for all 9 peers: frozen CSV sum ~200,875 works / per_page 200
~= 1,005 calls ~= $0.10 -- two orders of magnitude under the guard, which exists as a backstop,
not because it is expected to trip.

Resumable per peer (S4/G4 acceptance): a peer whose `peer_works_<id>.parquet` already exists in
the snapshot is skipped outright (no re-pull); a peer's own IN-PROGRESS crawl resumes from its own
`.cursor` file (same mechanism as 30_pull_france.py), so a mid-run interruption never re-spends
calls already paid for. No CLI flag needed for either -- both are automatic, matching 30's own
per-year auto-resume convention (NOT 42b's, which needs an explicit --resume: 42b's OUTPUT file is
a single append target across ALL partners, this script's output is naturally partitioned per peer).

Both pull dates disclosed (challenge memo lens #13/#15): the frozen G8 CSV was probed live
2026-08-17 (`docs/benchmark_peer_candidates.md` Sec.2, `reports/data/peer_candidate_probes.csv`);
THIS script's own pull date is stamped in the manifest and printed -- the +/-3% acceptance band
checks live-drift MAGNITUDE between the two dates, not recipe correctness (lens #15: the band
cannot by itself detect a direct-vs-lineage recipe swap on the five foreign peers, whose own
lineage/direct ratio sits at 1.00-1.08 -- immaterial-sized even if such an error existed; the
filter STRING itself is what must be reviewed, which is why it is quoted verbatim in this
docstring and printed at the top of every run).

Usage
  python pipeline/49_pull_peer_benchmark.py --calibrate     # Tampere only, vs the frozen golden
  python pipeline/49_pull_peer_benchmark.py                 # all status==ok peers, resumable
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
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot, sha256, utc_now  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)
FB = CONFIG["france_baseline"]
SELECT = ",".join(FB["select"])                       # id,cited_by_count,publication_year,type,primary_topic
DOC_TYPES = CONFIG["corpus_filter"]["doc_types_keep"]  # 5 types (S5) -- same list the corpus uses
YEAR_FROM, YEAR_TO = CONFIG["window"]["year_from"], CONFIG["window"]["year_to"]

REGISTRY_PATH = ROOT / "inputs" / "overlays" / "bench_peers.csv"
GOLDEN_CSV = ROOT / "reports" / "data" / "peer_candidate_probes.csv"
GOLDEN_PROBE_DATE = "2026-08-17"   # docs/benchmark_peer_candidates.md Sec.2 -- frozen evidence date

CALIBRATION_PEER_ID = "I166825849"   # Tampere -- smallest clean id (S5)
CALL_BUDGET = 10_000                # G4 hard guard (~$1); expected total ~1,005 calls (~$0.10)


def peer_filter(peer_id: str) -> str:
    """The frozen recipe string (S5), quoted here so any drift is a diffable one-liner."""
    types = "|".join(DOC_TYPES)
    return (
        f"authorships.institutions.id:{peer_id},"
        f"publication_year:{YEAR_FROM}-{YEAR_TO},"
        f"type:{types},is_retracted:false,is_paratext:false"
    )


def parse_record(work: dict) -> dict:
    """Verbatim mirror of 30_pull_france.py's parse_record -- same 6-column shape, same reasoning
    (this table is only ever joined into a stratum mean/threshold, nothing else is kept)."""
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
    """Verbatim mirror of 30_pull_france.py's iter_raw (reads plain .jsonl or the compressed
    .jsonl.zst archive, so `--tables-only` re-derivation works off either form, D18/D38)."""
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
        raise SystemExit(f"missing peer raw shard {path}")


def load_registry() -> pd.DataFrame:
    if not REGISTRY_PATH.exists():
        raise SystemExit(f"missing registry {REGISTRY_PATH}")
    return pd.read_csv(REGISTRY_PATH, encoding="utf-8", keep_default_na=False)


def load_golden() -> pd.DataFrame:
    if not GOLDEN_CSV.exists():
        raise SystemExit(f"missing frozen golden {GOLDEN_CSV} -- see docs/benchmark_peer_candidates.md")
    return pd.read_csv(GOLDEN_CSV, encoding="utf-8")


def compress_raw(path: Path) -> None:
    if not (CONFIG["storage"].get("compress_raw_jsonl") and path.exists()):
        return
    import zstandard

    target = path.with_suffix(path.suffix + ".zst")
    compressor = zstandard.ZstdCompressor(level=CONFIG["storage"].get("raw_compression_level", 10))
    with path.open("rb") as src, target.open("wb") as dst:
        compressor.copy_stream(src, dst)
    path.unlink()


def crawl_peer(client: OpenAlexClient, snapshot: Path, peer_id: str, label: str) -> tuple[Path, float, int, bool]:
    """Returns (raw_path, elapsed_seconds, written_this_call, aborted). `written_this_call` is -1
    when the peer's parquet already exists (skipped outright, no API touched at all)."""
    raw_dir = snapshot / "raw" / "peers"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = raw_dir / f"{peer_id}.jsonl"
    cursor_path = raw_dir / f"{peer_id}.cursor"
    parquet_path = snapshot / "tables" / f"peer_works_{peer_id}.parquet"

    if parquet_path.exists():
        print(f"  {label} ({peer_id}): peer_works_{peer_id}.parquet already exists -- skipping (resumable)")
        return out_path, 0.0, -1, False

    started = time.monotonic()
    mode = "a" if cursor_path.exists() and out_path.exists() else "w"
    written = 0
    aborted = False
    with out_path.open(mode, encoding="utf-8") as handle:
        for page in client.crawl(peer_filter(peer_id), SELECT, cursor_file=cursor_path,
                                  label=f"peer {label}", log_every=25):
            for work in page:
                handle.write(json.dumps(work, ensure_ascii=False) + "\n")
                written += 1
            if client.calls >= CALL_BUDGET:
                print(f"ABORT (spend guard): {client.calls:,} calls this run >= budget "
                      f"{CALL_BUDGET:,} (~${CALL_BUDGET * 0.0001:.2f}). Cursor checkpointed for "
                      f"{label} ({peer_id}) -- rerun this script to resume, no calls lost.")
                aborted = True
                break
    return out_path, time.monotonic() - started, written, aborted


def to_parquet(snapshot: Path, peer_id: str) -> Path:
    raw_path = snapshot / "raw" / "peers" / f"{peer_id}.jsonl"
    rows = [parse_record(work) for work in iter_raw(raw_path)]
    frame = pd.DataFrame(rows).drop_duplicates("work_id")
    target = snapshot / "tables" / f"peer_works_{peer_id}.parquet"
    frame.to_parquet(target, index=False, compression=CONFIG["storage"]["compression"])
    return target


def golden_delta(peer_id: str, works: int, golden: pd.DataFrame) -> dict:
    row = golden[golden["openalex_id"] == peer_id]
    if row.empty:
        return {"golden_works": None, "delta_pct": None, "within_band": None}
    golden_works = int(row["works_2019_2023"].iloc[0])
    delta_pct = (works - golden_works) / golden_works * 100 if golden_works else float("nan")
    return {"golden_works": golden_works, "delta_pct": delta_pct, "within_band": abs(delta_pct) <= 3.0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--calibrate", action="store_true",
                         help="pull ONLY Tampere (smallest clean id), report vs the frozen golden, no snapshot write side effects beyond that one peer")
    args = parser.parse_args()

    print(f"peer filter recipe (S5, frozen -- review this string, not just the +/-3% band):")
    print(f"  {peer_filter('<peer_id>')}")
    print(f"  select: {SELECT}")

    registry = load_registry()
    ok = registry[registry["status"] == "ok"].reset_index(drop=True)
    print(f"registry: {len(registry)} row(s), {len(ok)} status==ok\n")

    env = load_env(CONFIG["secrets"]["env_file"], CONFIG["secrets"]["required"])
    client = OpenAlexClient(CONFIG, env)
    snapshot = resolve_snapshot(CONFIG, args.snapshot)
    golden = load_golden()
    this_pull_date = utc_now()

    if args.calibrate:
        cal_row = ok[ok["peer_id"] == CALIBRATION_PEER_ID]
        if cal_row.empty:
            raise SystemExit(f"calibration peer {CALIBRATION_PEER_ID} not found (or not status==ok) in registry")
        peer_id, label = CALIBRATION_PEER_ID, cal_row.iloc[0]["display_name"]
        print(f"CALIBRATION -- {label} ({peer_id}) only\n")
        t0 = time.time()
        raw_path, elapsed, written, aborted = crawl_peer(client, snapshot, peer_id, label)
        if written == -1:
            n = pd.read_parquet(snapshot / "tables" / f"peer_works_{peer_id}.parquet", columns=["work_id"]).shape[0]
            print(f"already pulled: {n:,} works cached, no API calls this run")
        else:
            parquet = to_parquet(snapshot, peer_id)
            compress_raw(raw_path)
            n = pd.read_parquet(parquet, columns=["work_id"]).shape[0]
            delta = golden_delta(peer_id, n, golden)
            print(f"\n{label} ({peer_id}): {n:,} works pulled")
            print(f"  frozen golden (probed {GOLDEN_PROBE_DATE}): {delta['golden_works']:,} works")
            print(f"  delta: {delta['delta_pct']:+.2f}%  within +/-3% band: {delta['within_band']}")
            print(f"  API calls this run: {client.calls:,}  ~${client.calls * 0.0001:.4f}")
            print(f"  elapsed: {time.time() - t0:.1f}s")
            if not delta["within_band"]:
                print("\n!! CALIBRATION FAILED the +/-3% acceptance band -- do not proceed to the "
                      "full 9-peer pull without reviewing the filter string above.")
                sys.exit(1)
        print("\ncalibration OK -- proceed with the full pull: python pipeline/49_pull_peer_benchmark.py")
        return

    measured: list[dict] = []
    aborted_run = False
    for _, row in ok.iterrows():
        peer_id, label = row["peer_id"], row["display_name"]
        raw_path, elapsed, written, aborted = crawl_peer(client, snapshot, peer_id, label)
        if written == -1:
            n = pd.read_parquet(snapshot / "tables" / f"peer_works_{peer_id}.parquet", columns=["work_id"]).shape[0]
            measured.append({"peer_id": peer_id, "display_name": label, "works": n,
                              "skipped": True, **golden_delta(peer_id, n, golden)})
            continue
        parquet = to_parquet(snapshot, peer_id)
        raw_mb = raw_path.stat().st_size / 1e6 if raw_path.exists() else 0.0
        digest = sha256(raw_path) if raw_path.exists() else None
        compress_raw(raw_path)
        n = pd.read_parquet(parquet, columns=["work_id"]).shape[0]
        delta = golden_delta(peer_id, n, golden)
        measured.append({"peer_id": peer_id, "display_name": label, "works": n, "skipped": False,
                          "raw_mb": round(raw_mb, 1), "raw_sha256": digest, **delta})
        print(f"  {label} ({peer_id}): {n:,} works  |  golden {delta['golden_works']:,}  "
              f"delta {delta['delta_pct']:+.2f}%  within_band={delta['within_band']}")
        if aborted:
            aborted_run = True
            break

    lines = [
        f"- peers pulled this run: {len([m for m in measured if not m['skipped']])} "
        f"(skipped, already cached: {len([m for m in measured if m['skipped']])})",
        f"- OpenAlex list calls this run: **{client.calls:,}** => **${client.calls * 0.0001:.4f}**",
        f"- pull date this run: {this_pull_date}  |  frozen golden probe date: {GOLDEN_PROBE_DATE}",
        "",
        "| Peer | Works pulled | Golden (2026-08-17) | Delta % | Within +/-3% |",
        "|---|---|---|---|---|",
    ]
    for m in measured:
        gw = f"{m['golden_works']:,}" if m["golden_works"] is not None else "n/a"
        dp = f"{m['delta_pct']:+.2f}%" if m["delta_pct"] is not None else "n/a"
        wb = m["within_band"] if m["within_band"] is not None else "n/a"
        lines.append(f"| {m['display_name']} ({m['peer_id']}) | {m['works']:,} | {gw} | {dp} | {wb} |")
    if aborted_run:
        lines.append("\n!! ABORTED mid-run (spend guard) -- rerun this script to resume the remaining peer(s).")

    Manifest(snapshot).record_step(
        "49_pull_peer_benchmark",
        filters={"recipe": peer_filter("<peer_id>")},
        select=SELECT,
        api_base=CONFIG["openalex"]["base_url"],
        api_calls=client.calls,
        counts={m["peer_id"]: m["works"] for m in measured},
        files=[snapshot / "tables" / f"peer_works_{m['peer_id']}.parquet" for m in measured],
        params={"doc_types": DOC_TYPES, "per_page": CONFIG["openalex"]["per_page"],
                "year_from": YEAR_FROM, "year_to": YEAR_TO,
                "golden_probe_date": GOLDEN_PROBE_DATE, "this_pull_date": this_pull_date,
                "deltas_pct": {m["peer_id"]: m["delta_pct"] for m in measured},
                "aborted": aborted_run},
        notes="G4 (pass 4): peer direct-id pull, S5 recipe, per-peer resumable. Both pull dates "
              "(golden probe + this run) stamped per challenge memo lens #13/#15.",
    )
    append_summary(snapshot, "49_pull_peer_benchmark", lines)
    print("\n".join(lines))
    if aborted_run:
        sys.exit(2)


if __name__ == "__main__":
    main()
