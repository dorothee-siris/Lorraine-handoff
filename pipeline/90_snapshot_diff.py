"""90_snapshot_diff.py -- compares two snapshots' tables, per drift-band family (BUILD_PLAN §10).

Families (thresholds read from config.yaml: audit.drift_bands / audit.pptop_share_per_year, so a
config edit changes the bands without touching this script):
  corpus_size        relative %      corpus.parquet row count
  works_per_lab      relative % + "any lab -> 0"   ul_labs.parquet (lab, works)
  abstract_coverage  points (pts)    corpus_abstracts.parquet (falls back to corpus.parquet)
  sdg_coverage       points (pts)    sdg_siris.parquet distinct work_id / corpus size
  fwci_fr_median     relative %      works_master.parquet.FWCI_FR (falls back to corpus_metrics)
  pptop10_per_year   points (pts)    works_master.parquet.PPtop10_FR by publication_year
  partner_count      relative %      ul_partners.parquet row count
  isite_flagged      relative %      works_master.parquet.In_ISITE sum

Every family is computed independently: a missing table in EITHER snapshot is reported as
"missing" for that family (old/new values shown as "n/a"), never a crash, per the D57/D59
handover requirement that 2026-08-10 (which predates the view builders) must diff gracefully
against 2026-08-11.

Usage
  python pipeline/90_snapshot_diff.py <id_old> <id_new>
  python pipeline/90_snapshot_diff.py --selftest        # band-logic self-check, no snapshots read
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
CONFIG = load_config(ROOT)
BANDS = CONFIG["audit"]["drift_bands"]
PPTOP_TOL_PTS = CONFIG["audit"]["pptop_share_per_year"]["tolerance_pts"]


# ---------------------------------------------------------------------------------------------
# Band-verdict primitives (self-tested below, no I/O)
# ---------------------------------------------------------------------------------------------
def verdict_relative(old: float, new: float, expected: float, investigate: float) -> tuple[float, str]:
    """Relative-change bands (corpus_size, works_per_lab, fwci_fr_median, partner_count, isite)."""
    if old in (0, None) or old != old:  # 0 or NaN -- avoid a divide-by-zero false "investigate"
        delta = float("nan")
        verdict = "investigate" if new not in (0, None) else "OK"
        return delta, verdict
    delta = (new - old) / old
    if abs(delta) <= expected:
        return delta, "OK"
    if abs(delta) <= investigate:
        return delta, "investigate"
    return delta, "investigate"  # beyond `investigate` is still "investigate" (§10 has no Class-1 auto-fail here)


def verdict_pts(old: float, new: float, expected_pts: float, investigate_pts: float) -> tuple[float, str]:
    """Point-change bands (abstract_coverage, sdg_coverage, pptop10_per_year)."""
    if old != old or new != new:  # NaN
        return float("nan"), "missing"
    delta = new - old
    if abs(delta) <= expected_pts:
        return delta, "OK"
    return delta, "investigate"


# ---------------------------------------------------------------------------------------------
# Table access -- never raises; a missing table is reported, not fatal
# ---------------------------------------------------------------------------------------------
def read_table(snapshot_dir: Path, *candidates: str) -> tuple[pd.DataFrame | None, str | None]:
    for name in candidates:
        path = snapshot_dir / "tables" / name
        if path.exists():
            return pd.read_parquet(path), name
    return None, None


class Missing(Exception):
    """Raised inside a family function when a required table is absent; caught by run_family."""

    def __init__(self, table: str, snapshot_label: str):
        super().__init__(f"{table} not found in the {snapshot_label} snapshot")


# ---------------------------------------------------------------------------------------------
# One function per family. Each returns a dict with old/new/delta/verdict/detail (markdown-ready).
# ---------------------------------------------------------------------------------------------
def family_corpus_size(old_dir: Path, new_dir: Path) -> dict:
    old_df, old_name = read_table(old_dir, "corpus.parquet")
    new_df, new_name = read_table(new_dir, "corpus.parquet")
    if old_df is None:
        raise Missing("corpus.parquet", "old")
    if new_df is None:
        raise Missing("corpus.parquet", "new")
    old_v, new_v = len(old_df), len(new_df)
    delta, verdict = verdict_relative(old_v, new_v, BANDS["corpus_size"]["expected"],
                                       BANDS["corpus_size"]["investigate"])
    return {"old": f"{old_v:,}", "new": f"{new_v:,}", "delta": f"{delta:+.1%}", "verdict": verdict,
            "detail": f"source: {old_name} / {new_name}"}


def family_works_per_lab(old_dir: Path, new_dir: Path) -> dict:
    old_df, old_name = read_table(old_dir, "ul_labs.parquet")
    new_df, new_name = read_table(new_dir, "ul_labs.parquet")
    if old_df is None:
        raise Missing("ul_labs.parquet", "old")
    if new_df is None:
        raise Missing("ul_labs.parquet", "new")
    merged = old_df[["lab", "works"]].merge(new_df[["lab", "works"]], on="lab", how="outer",
                                             suffixes=("_old", "_new")).fillna(0)
    flags = []
    for row in merged.itertuples():
        if row.works_old > 0 and row.works_new == 0:
            flags.append(f"{row.lab} -> 0 (was {int(row.works_old):,})")
            continue
        _, v = verdict_relative(row.works_old, row.works_new, BANDS["works_per_lab"]["expected"],
                                 BANDS["works_per_lab"]["investigate"])
        if v == "investigate":
            flags.append(f"{row.lab}: {int(row.works_old):,} -> {int(row.works_new):,}")
    old_total, new_total = int(merged["works_old"].sum()), int(merged["works_new"].sum())
    delta = (new_total - old_total) / old_total if old_total else float("nan")
    verdict = "investigate" if flags else "OK"
    detail = (f"{len(merged)} labs compared" + (f"; flagged: {'; '.join(flags[:8])}"
              + (" ..." if len(flags) > 8 else "") if flags else "; all within band"))
    return {"old": f"{old_total:,}", "new": f"{new_total:,}", "delta": f"{delta:+.1%}",
            "verdict": verdict, "detail": detail}


def family_abstract_coverage(old_dir: Path, new_dir: Path) -> dict:
    old_df, old_name = read_table(old_dir, "corpus_abstracts.parquet", "corpus.parquet")
    new_df, new_name = read_table(new_dir, "corpus_abstracts.parquet", "corpus.parquet")
    if old_df is None:
        raise Missing("corpus_abstracts.parquet / corpus.parquet", "old")
    if new_df is None:
        raise Missing("corpus_abstracts.parquet / corpus.parquet", "new")
    old_v = old_df["abstract"].notna().mean() * 100
    new_v = new_df["abstract"].notna().mean() * 100
    delta, verdict = verdict_pts(old_v, new_v, BANDS["abstract_coverage"]["expected_pts"],
                                  BANDS["abstract_coverage"]["investigate_pts"])
    note = "" if old_name == new_name else (f" (NOTE: old computed from {old_name}, new from "
                                             f"{new_name} -- methodology differs, e.g. pre- vs "
                                             f"post-backfill)")
    return {"old": f"{old_v:.1f} pts", "new": f"{new_v:.1f} pts", "delta": f"{delta:+.1f} pts",
            "verdict": verdict, "detail": f"source: {old_name} / {new_name}{note}"}


def family_sdg_coverage(old_dir: Path, new_dir: Path) -> dict:
    old_sdg, _ = read_table(old_dir, "sdg_siris.parquet")
    new_sdg, _ = read_table(new_dir, "sdg_siris.parquet")
    old_corpus, _ = read_table(old_dir, "corpus.parquet")
    new_corpus, _ = read_table(new_dir, "corpus.parquet")
    if old_sdg is None:
        raise Missing("sdg_siris.parquet", "old")
    if new_sdg is None:
        raise Missing("sdg_siris.parquet", "new")
    old_v = old_sdg["work_id"].nunique() / len(old_corpus) * 100
    new_v = new_sdg["work_id"].nunique() / len(new_corpus) * 100
    delta, verdict = verdict_pts(old_v, new_v, BANDS["sdg_coverage"]["expected_pts"],
                                  BANDS["sdg_coverage"]["investigate_pts"])
    return {"old": f"{old_v:.1f} pts", "new": f"{new_v:.1f} pts", "delta": f"{delta:+.1f} pts",
            "verdict": verdict, "detail": "sdg_siris.parquet distinct work_id / corpus.parquet rows"}


def family_fwci_fr_median(old_dir: Path, new_dir: Path) -> dict:
    old_df, old_name = read_table(old_dir, "works_master.parquet", "corpus_metrics.parquet")
    new_df, new_name = read_table(new_dir, "works_master.parquet", "corpus_metrics.parquet")
    if old_df is None:
        raise Missing("works_master.parquet / corpus_metrics.parquet", "old")
    if new_df is None:
        raise Missing("works_master.parquet / corpus_metrics.parquet", "new")
    old_v = old_df["FWCI_FR"].median()
    new_v = new_df["FWCI_FR"].median()
    delta, verdict = verdict_relative(old_v, new_v, BANDS["fwci_fr_median"]["expected"],
                                       BANDS["fwci_fr_median"]["investigate"])
    return {"old": f"{old_v:.3f}", "new": f"{new_v:.3f}", "delta": f"{delta:+.1%}",
            "verdict": verdict, "detail": f"source: {old_name} / {new_name}, computed-only rows"}


def family_pptop10_per_year(old_dir: Path, new_dir: Path) -> dict:
    old_df, old_name = read_table(old_dir, "works_master.parquet")
    new_df, new_name = read_table(new_dir, "works_master.parquet")
    if old_df is None:
        raise Missing("works_master.parquet", "old")
    if new_df is None:
        raise Missing("works_master.parquet", "new")
    years = range(CONFIG["window"]["year_from"], CONFIG["window"]["year_to"] + 1)

    def share_by_year(df: pd.DataFrame) -> dict[int, float]:
        computed = df[df["indicator_status"] == "computed"]
        out = {}
        for y in years:
            block = computed[computed["publication_year"] == y]
            out[y] = float(block["PPtop10_FR"].astype(float).mean() * 100) if len(block) else float("nan")
        return out

    old_share, new_share = share_by_year(old_df), share_by_year(new_df)
    per_year = []
    worst_verdict = "OK"
    for y in years:
        d, v = verdict_pts(old_share[y], new_share[y], PPTOP_TOL_PTS, PPTOP_TOL_PTS)
        per_year.append(f"{y}: {old_share[y]:.1f}->{new_share[y]:.1f} ({d:+.1f}pts, {v})")
        if v != "OK":
            worst_verdict = "investigate"
    old_str = "|".join(f"{y}:{old_share[y]:.1f}" for y in years)
    new_str = "|".join(f"{y}:{new_share[y]:.1f}" for y in years)
    max_delta = max(abs(new_share[y] - old_share[y]) for y in years)
    return {"old": old_str, "new": new_str, "delta": f"max {max_delta:+.1f} pts",
            "verdict": worst_verdict, "detail": "; ".join(per_year)}


def family_partner_count(old_dir: Path, new_dir: Path) -> dict:
    old_df, _ = read_table(old_dir, "ul_partners.parquet")
    new_df, _ = read_table(new_dir, "ul_partners.parquet")
    if old_df is None:
        raise Missing("ul_partners.parquet", "old")
    if new_df is None:
        raise Missing("ul_partners.parquet", "new")
    old_v, new_v = len(old_df), len(new_df)
    delta, verdict = verdict_relative(old_v, new_v, BANDS["partner_count"]["expected"],
                                       BANDS["partner_count"]["investigate"])
    return {"old": f"{old_v:,}", "new": f"{new_v:,}", "delta": f"{delta:+.1%}", "verdict": verdict,
            "detail": "ul_partners.parquet row count"}


def family_isite_flagged(old_dir: Path, new_dir: Path) -> dict:
    old_df, _ = read_table(old_dir, "works_master.parquet")
    new_df, _ = read_table(new_dir, "works_master.parquet")
    if old_df is None:
        raise Missing("works_master.parquet", "old")
    if new_df is None:
        raise Missing("works_master.parquet", "new")
    old_v, new_v = int(old_df["In_ISITE"].sum()), int(new_df["In_ISITE"].sum())
    delta, verdict = verdict_relative(old_v, new_v, BANDS["isite_flagged"]["expected"],
                                       BANDS["isite_flagged"]["investigate"])
    return {"old": f"{old_v:,}", "new": f"{new_v:,}", "delta": f"{delta:+.1%}", "verdict": verdict,
            "detail": "works_master.parquet In_ISITE sum"}


FAMILIES = [
    ("corpus_size", "Corpus size", family_corpus_size),
    ("works_per_lab", "Works per lab", family_works_per_lab),
    ("abstract_coverage", "Abstract coverage", family_abstract_coverage),
    ("sdg_coverage", "SDG coverage (B/SIRIS)", family_sdg_coverage),
    ("fwci_fr_median", "FWCI_FR median", family_fwci_fr_median),
    ("pptop10_per_year", "PPtop10 per year", family_pptop10_per_year),
    ("partner_count", "Partner count", family_partner_count),
    ("isite_flagged", "ISITE (In_ISITE) flagged works", family_isite_flagged),
]


def run_family(fn, old_dir: Path, new_dir: Path) -> dict:
    try:
        return fn(old_dir, new_dir)
    except Missing as exc:
        return {"old": "n/a", "new": "n/a", "delta": "n/a", "verdict": "missing table",
                "detail": str(exc)}
    except Exception as exc:  # any other read/compute failure is reported, never a crash
        return {"old": "n/a", "new": "n/a", "delta": "n/a", "verdict": "error",
                "detail": f"{type(exc).__name__}: {exc}"}


def write_report(old_id: str, new_id: str, results: list[tuple[str, str, dict]], out_path: Path) -> None:
    lines = [
        f"# Snapshot diff: {old_id} -> {new_id}",
        "",
        f"Bands from `config.yaml: audit.drift_bands` (+ `audit.pptop_share_per_year` for the "
        f"PPtop10 family). `OK` = within the expected band. `investigate` = beyond expected, "
        f"within or past the investigate band -- read `docs/BUILD_PLAN.md` §10 before acting. "
        f"`missing table` = one snapshot predates that table (reported, not a failure).",
        "",
        "| Family | Old | New | Delta | Verdict |",
        "|---|---|---|---|---|",
    ]
    for key, label, res in results:
        lines.append(f"| {label} | {res['old']} | {res['new']} | {res['delta']} | {res['verdict']} |")
    lines += ["", "## Detail", ""]
    for key, label, res in results:
        lines.append(f"**{label}** ({key}): {res['detail']}")
        lines.append("")
    n_investigate = sum(1 for _, _, r in results if r["verdict"] == "investigate")
    n_missing = sum(1 for _, _, r in results if r["verdict"] in ("missing table", "error"))
    lines.append(f"---\n{len(results)} families: "
                 f"{sum(1 for _, _, r in results if r['verdict'] == 'OK')} OK, "
                 f"{n_investigate} investigate, {n_missing} missing/error.")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_selftest() -> None:
    # verdict_relative
    d, v = verdict_relative(100, 105, 0.10, 0.25)
    assert v == "OK" and abs(d - 0.05) < 1e-9, (d, v)
    d, v = verdict_relative(100, 120, 0.10, 0.25)
    assert v == "investigate" and abs(d - 0.20) < 1e-9, (d, v)
    d, v = verdict_relative(100, 200, 0.10, 0.25)
    assert v == "investigate", (d, v)
    d, v = verdict_relative(0, 5, 0.10, 0.25)
    assert v == "investigate", "a lab appearing from zero must be flagged"
    d, v = verdict_relative(0, 0, 0.10, 0.25)
    assert v == "OK", "0 -> 0 is not a drift"
    # verdict_pts
    d, v = verdict_pts(80.0, 83.0, 5, 10)
    assert v == "OK" and abs(d - 3.0) < 1e-9, (d, v)
    d, v = verdict_pts(80.0, 91.0, 5, 10)
    assert v == "investigate", (d, v)
    d, v = verdict_pts(float("nan"), 91.0, 5, 10)
    assert v == "missing", (d, v)
    print("selftest OK -- 8/8 band-logic assertions passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_id", nargs="?")
    parser.add_argument("new_id", nargs="?")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        run_selftest()
        sys.exit(0)

    if not args.old_id or not args.new_id:
        parser.error("both <id_old> and <id_new> are required (or pass --selftest)")

    old_dir = resolve_snapshot(CONFIG, args.old_id, create=False)
    new_dir = resolve_snapshot(CONFIG, args.new_id, create=False)
    for label, d in (("old", old_dir), ("new", new_dir)):
        if not d.exists():
            print(f"ERROR: {label} snapshot '{d.name}' not found at {d}")
            sys.exit(1)

    print(f"comparing {old_dir.name} -> {new_dir.name}")
    results = []
    for key, label, fn in FAMILIES:
        res = run_family(fn, old_dir, new_dir)
        results.append((key, label, res))
        print(f"  {label:<28} old={res['old']:<10} new={res['new']:<10} delta={res['delta']:<12} "
              f"{res['verdict']}")

    out_path = ROOT / CONFIG["paths"]["reports"] / f"snapshot_diff_{old_dir.name}_vs_{new_dir.name}.md"
    write_report(old_dir.name, new_dir.name, results, out_path)
    print(f"\nwrote {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
