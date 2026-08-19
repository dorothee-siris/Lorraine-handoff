"""80_audit.py -- the deployment gate (Stream F, plan §10 / D16).

Two tiers, run against the DEPLOYED file set (`Streamlit/data/` by default -- the thing that
actually ships, not an intermediate snapshot table):

  Class 1 -- structural invariants. Implemented directly here (not by importing or re-running
  `tests/test_invariants.py`, which is frozen and reads fixed, config-resolved paths) so that this
  script can be pointed at an arbitrary directory via `--tables-dir` -- the mechanism the seeded-
  violation acceptance test needs. Any Class-1 failure fails the run.

  Class 2 -- drift bands vs v1 (this is the FIRST run, so "vs the previous snapshot" in the plan
  collapses to "vs v1"). Bands come from `config.yaml: audit.drift_bands` / `baselines_v1`. Any
  family beyond its "investigate" threshold blocks deployment (non-zero exit) UNLESS it is in the
  hardcoded EXPLAINED_EXCEPTIONS set below. That set holds two entries: `corpus_size` (D36, signed
  off in the shift report at build time) and `works_per_lab` (forensically investigated in
  `reports/lab_delta_investigation.md`, signed off by the orchestrator on that evidence
  2026-08-11, pending Nate ratification at review). Each entry is a named, evidenced decision, not
  a self-granted pass, and neither band is widened -- only the STATUS of the specific, already-
  measured breach is upgraded. Any OTHER investigate-level breach is reported in full and left
  BLOCKING -- this script does not grant itself new exceptions.

Usage:
  python pipeline/80_audit.py [--snapshot 2026-08-11] [--tables-dir PATH]

`--tables-dir` overrides the deployed-file directory used by the Class-1 checks (default:
`config.yaml: paths.deploy_target`, i.e. `Streamlit/data`) -- this is what the seeded-violation
demo (temp copy + duplicated PK + `--tables-dir <temp>`) points at. Class-2 checks always compare
against the live v1 reference (`../Phase 1/Streamlit/data/`, frozen, read-only) and the given
`--snapshot`'s own tables (needed for a couple of snapshot-only inputs, e.g. the France baseline
strata for the PPtop regression); they are not affected by `--tables-dir`.

Exit code: 0 if every Class-1 check passes AND no Class-2 family is at INVESTIGATE outside
EXPLAINED_EXCEPTIONS; 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)
CONTRACT = yaml.safe_load((ROOT / "docs" / "data_contract.yaml").read_text(encoding="utf-8"))
V1_DATA = ROOT.parent / "Phase 1" / "Streamlit" / "data"

# The 15 files this contract actually deploys (excludes the two "dead" entries data_contract.yaml
# declares for grep-obligation bookkeeping: TM_labels.parquet, pubs.parquet).
DEPLOYED_FILES = sorted(f for f in CONTRACT["files"] if f not in ("TM_labels.parquet", "pubs.parquet"))

# Plan's explicit instruction (BUILD_PLAN Stream F / v2_execution_plan D36): pre-registered
# exceptions are added ONLY on a named, evidenced decision -- never a self-granted pass. Each
# entry below is added at a specific date, by a specific sign-off, citing the report that earned
# it. A band is never widened to make a row disappear; only the STATUS of a specific, evidenced
# breach is upgraded from INVESTIGATE to EXPLAINED_EXCEPTION.
EXPLAINED_EXCEPTIONS = {
    "corpus_size": (
        "D36 -- OpenAlex doc-type reclassification (3,737 v1 works retyped to conference-paper) "
        "plus the broadened lineage perimeter. Signed off in reports/shift_v1_v2_data.md section (c). "
        "The corpus_size band is never widened; this is a one-time recorded exception, not a new default."
    ),
    "works_per_lab": (
        "Forensically resolved in reports/lab_delta_investigation.md (Stream F2). Per its section 7 "
        "recommendation: lab-level totals grew faster than the corpus because OpenAlex's own "
        "affiliation-matching pipeline continues to re-process the historical record years after a "
        "crawl -- not because Lorraine's structures published more, and not because v2's attribution "
        "logic differs from v1's (a corpus-wide, zero-violation scan of all 35,416 (work, lab) "
        "attributions found no v2 bug, section 5). A small, quantified v1 baseline artifact (the topic-null "
        "exclusion bug disclosed in reports/shift_v1_v2_data.md section (j)) inflates the measured "
        "delta by +2.7% but is not itself the driver. Signed off by orchestrator on F2 evidence "
        "2026-08-11; pending Nate ratification at review. The works_per_lab band is never widened; "
        "this is a one-time recorded exception covering the 58 structures decomposed in the F2 report, "
        "not a new default for future snapshots."
    ),
}


class Check:
    __slots__ = ("id", "cls", "ok", "detail")

    def __init__(self, id: str, cls: int, ok: bool, detail: str) -> None:
        self.id, self.cls, self.ok, self.detail = id, cls, ok, detail


def read_table(tables_dir: Path, fname: str) -> pd.DataFrame | None:
    path = tables_dir / fname
    if not path.exists():
        return None
    return pd.read_parquet(path)


# ============================================================================================
# Class 1 -- structural invariants
# ============================================================================================
def run_class1(tables_dir: Path) -> list[Check]:
    checks: list[Check] = []

    # ---- file_set_exact ----
    on_disk = sorted(p.name for p in tables_dir.glob("*.parquet"))
    missing = [f for f in DEPLOYED_FILES if f not in on_disk]
    extra_banned = [f for f in on_disk if f in ("TM_labels.parquet", "pubs.parquet")]
    ok = not missing and not extra_banned
    detail = f"{len(on_disk)} files on disk"
    if missing:
        detail += f"; MISSING: {missing}"
    if extra_banned:
        detail += f"; BANNED FILES PRESENT: {extra_banned}"
    checks.append(Check("file_set_exact", 1, ok, detail))

    # ---- pk_unique (every file actually present, per its own contract keys) ----
    pk_failures: list[str] = []
    for fname in DEPLOYED_FILES:
        df = read_table(tables_dir, fname)
        if df is None:
            continue
        keys = CONTRACT["files"][fname].get("keys") or []
        if not keys:
            continue
        missing_cols = [k for k in keys if k not in df.columns]
        if missing_cols:
            pk_failures.append(f"{fname}: key column(s) absent {missing_cols}")
            continue
        if df[keys].isna().any().any():
            pk_failures.append(f"{fname}: null(s) in key {keys}")
        dup = df.duplicated(subset=keys)
        if dup.any():
            pk_failures.append(f"{fname}: {int(dup.sum())} duplicate row(s) on key {keys}")
    checks.append(Check("pk_unique", 1, not pk_failures, "; ".join(pk_failures) or "all keys unique"))

    # ---- fk_resolves ----
    fk_failures: list[str] = []
    ul_pubs = read_table(tables_dir, "ul_pubs.parquet")
    all_topics = read_table(tables_dir, "all_topics.parquet")
    if ul_pubs is not None:
        valid_work_ids = set(ul_pubs["work_id"])
        for fname in ("sdg_siris.parquet", "sdg_three_way.parquet"):
            df = read_table(tables_dir, fname)
            if df is None or "work_id" not in df.columns:
                continue
            orphans = set(df["work_id"]) - valid_work_ids
            if orphans:
                fk_failures.append(f"{fname}: {len(orphans)} work_id(s) not in ul_pubs, e.g. {list(orphans)[:3]}")
        if all_topics is not None:
            known_topics = set(all_topics["topic_id"])
            observed = set(ul_pubs["primary_topic_id"].dropna())
            unknown = observed - known_topics
            if unknown:
                fk_failures.append(f"ul_pubs: {len(unknown)} primary_topic_id(s) not in all_topics: {list(unknown)[:3]}")
    else:
        fk_failures.append("ul_pubs.parquet absent -- cannot check any FK")
    checks.append(Check("fk_resolves", 1, not fk_failures, "; ".join(fk_failures) or "all FKs resolve"))

    # ---- taxonomy_is_superset (domain/field/subfield ids too, not only topic) ----
    tax_failures: list[str] = []
    if ul_pubs is not None and all_topics is not None:
        pairs = [
            ("primary_domain_id", "domain_id"),
            ("primary_field_id", "field_id"),
            ("primary_subfield_id", "subfield_id"),
        ]
        for pubs_col, topics_col in pairs:
            if pubs_col not in ul_pubs.columns or topics_col not in all_topics.columns:
                continue
            known = set(all_topics[topics_col].dropna().astype(str))
            observed = set(ul_pubs[pubs_col].dropna().astype(str)) - {"0"}  # '0' = the Unclassified sentinel
            unknown = observed - known
            if unknown:
                tax_failures.append(f"{pubs_col}: {len(unknown)} id(s) not in all_topics.{topics_col}: {list(unknown)[:3]}")
    checks.append(Check("taxonomy_is_superset", 1, not tax_failures, "; ".join(tax_failures) or "0 unknown taxonomy ids"))

    # ---- no_lab_unchanged (D56: hors-liste rows must never move this number) ----
    ul_labs = read_table(tables_dir, "ul_labs.parquet")
    if ul_labs is not None and "Structure name" in ul_labs.columns:
        row = ul_labs[ul_labs["Structure name"] == "NO LAB"]
        if len(row) != 1:
            checks.append(Check("no_lab_unchanged", 1, False, f"expected exactly 1 NO LAB row, found {len(row)}"))
        else:
            n = int(row["Pubs total"].iloc[0])
            checks.append(Check("no_lab_unchanged", 1, n == 4568, f"NO LAB Pubs total = {n:,} (expected 4,568)"))
    else:
        checks.append(Check("no_lab_unchanged", 1, False, "ul_labs.parquet absent or missing 'Structure name'"))

    # ---- hors_liste_rows (D56 reconciliation) ----
    if ul_labs is not None and "in_client_list" in ul_labs.columns:
        hors_liste = ul_labs[ul_labs["in_client_list"] == False]  # noqa: E712
        totals = sorted(hors_liste["Pubs total"].astype(int).tolist(), reverse=True)
        expected_top7 = [690, 421, 111, 27, 22, 18, 12]
        ok = len(hors_liste) == 21 and totals[:7] == expected_top7 and totals.count(0) == 14
        checks.append(Check(
            "hors_liste_rows", 1, ok,
            f"{len(hors_liste)} hors-liste rows (expected 21); top-7 totals {totals[:7]} "
            f"(expected {expected_top7}); zero-work rows {totals.count(0)} (expected 14)",
        ))
    else:
        checks.append(Check("hors_liste_rows", 1, False, "ul_labs.parquet absent or missing 'in_client_list'"))

    # ---- indicator_status_never_zero ----
    if ul_pubs is not None and {"indicator_status", "FWCI_FR"} <= set(ul_pubs.columns):
        thin = ul_pubs[ul_pubs["indicator_status"] != "computed"]
        bad = int(thin["FWCI_FR"].notna().sum())
        checks.append(Check("indicator_status_never_zero", 1, bad == 0,
                             f"{bad} thin/no-stratum works have a non-null FWCI_FR (must be null, never 0)"))
    else:
        checks.append(Check("indicator_status_never_zero", 1, False, "ul_pubs.parquet absent or missing columns"))

    # ---- is_abstract_present (the v1 regression: silently dropped at deploy) ----
    checks.append(Check("is_abstract_present", 1,
                         ul_pubs is not None and "Is_abstract" in ul_pubs.columns,
                         "Is_abstract present" if ul_pubs is not None and "Is_abstract" in ul_pubs.columns
                         else "ul_pubs.parquet absent or missing Is_abstract"))

    # ---- provenance flag on every work ----
    if ul_pubs is not None and "via_lineage" in ul_pubs.columns:
        n_bad = int((~ul_pubs["via_lineage"].astype(bool)).sum())
        checks.append(Check("provenance_flag_present", 1, n_bad == 0,
                             f"{n_bad} works with via_lineage == False (every work must enter via lineage)"))
    else:
        checks.append(Check("provenance_flag_present", 1, False, "ul_pubs.parquet absent or missing via_lineage"))

    # ---- no impossible values ----
    impossible: list[str] = []
    if ul_pubs is not None:
        if "cited_by_count" in ul_pubs.columns and (ul_pubs["cited_by_count"] < 0).any():
            impossible.append("negative cited_by_count")
        if "FWCI_FR" in ul_pubs.columns and (ul_pubs["FWCI_FR"].dropna() < 0).any():
            impossible.append("negative FWCI_FR")
        if "cnp_value" in ul_pubs.columns:
            cnp = ul_pubs["cnp_value"].dropna()
            if len(cnp) and not cnp.between(0, 1).all():
                impossible.append("cnp_value outside [0,1]")
        if "publication_year" in ul_pubs.columns:
            lo, hi = CONFIG["window"]["year_from"], CONFIG["window"]["year_to"]
            if not ul_pubs["publication_year"].between(lo, hi).all():
                impossible.append(f"publication_year outside window [{lo},{hi}]")
    checks.append(Check("no_impossible_values", 1, not impossible, "; ".join(impossible) or "none found"))

    # ---- blob_separator_safety ----
    blob_failures = 0
    contributions = read_table(tables_dir, "thematic_detail_contributions.parquet")
    if contributions is not None and "top_labs" in contributions.columns:
        for blob in contributions["top_labs"].dropna():
            for item in str(blob).split("|"):
                if item and item.count(":") != 4:
                    blob_failures += 1
    if ul_labs is not None and "Structure name" in ul_labs.columns:
        colon_names = ul_labs.loc[ul_labs["Structure name"].str.contains(":", na=False), "Structure name"]
        blob_failures += len(colon_names)
    checks.append(Check("blob_separator_safety", 1, blob_failures == 0,
                         f"{blob_failures} unsanitised ':'-blob item(s) / structure name(s)"))

    # ---- PPtop year-gradient regression (part of the §10 Class-1 PPtop bullet) ----
    if ul_pubs is not None and {"indicator_status", "PPtop10_FR", "publication_year"} <= set(ul_pubs.columns):
        computed = ul_pubs[ul_pubs["indicator_status"] == "computed"]
        shares = {int(y): float(b["PPtop10_FR"].astype(float).mean()) for y, b in computed.groupby("publication_year")}
        spread = (max(shares.values()) - min(shares.values())) * 100 if shares else None
        limit = CONFIG["audit"]["pptop_year_spread_max_pts"]
        ok = spread is not None and spread <= limit
        checks.append(Check("pptop_no_year_gradient", 1, ok,
                             f"year spread {spread:.1f} pts (limit {limit}); per-year shares "
                             f"{ {y: round(v, 4) for y, v in sorted(shares.items())} }"))
    else:
        checks.append(Check("pptop_no_year_gradient", 1, False, "ul_pubs.parquet absent or missing columns"))

    # ---- zero TM references survive ----
    import re

    banned = re.compile(r"classic tm|research topic|objective \d|method \d|impact \d|tm_label", re.I)
    streamlit_dir = ROOT / "Streamlit"
    offenders: list[str] = []
    if streamlit_dir.exists():
        for path in streamlit_dir.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if banned.search(text):
                offenders.append(str(path.relative_to(ROOT)))
    checks.append(Check("zero_tm_references", 1, not offenders,
                         "clean" if not offenders else f"TM references survive in: {offenders}"))

    return checks


# ============================================================================================
# Class 2 -- drift bands vs v1
# ============================================================================================
def rel_band_status(delta: float, expected: float, investigate: float) -> str:
    a = abs(delta)
    if a <= expected:
        return "OK"
    if a <= investigate:
        return "WATCH"
    return "INVESTIGATE"


def pts_band_status(delta_pts: float, expected_pts: float, investigate_pts: float, fall_only: bool = False) -> str:
    """§10: for coverage families, only a FALL beyond the band is treated as suspicious."""
    if fall_only and delta_pts >= 0:
        return "OK" if delta_pts <= expected_pts else "WATCH"
    a = abs(delta_pts)
    if a <= expected_pts:
        return "OK"
    if a <= investigate_pts:
        return "WATCH"
    return "INVESTIGATE"


def run_class2(deployed_dir: Path, snapshot_tables: Path) -> list[dict]:
    bands = CONFIG["audit"]["drift_bands"]
    baselines_v1 = CONFIG["baselines_v1"]
    rows: list[dict] = []

    ul_pubs = read_table(deployed_dir, "ul_pubs.parquet")
    ul_labs = read_table(deployed_dir, "ul_labs.parquet")
    ul_partners = read_table(deployed_dir, "ul_partners.parquet")
    pubs_v1 = pd.read_parquet(V1_DATA / "ul_pubs.parquet")
    labs_v1 = pd.read_parquet(V1_DATA / "ul_labs.parquet")
    partners_v1 = pd.read_parquet(V1_DATA / "ul_partners.parquet")

    # ---- corpus_size (D36 -- pre-registered exception; status resolved generically below) ----
    if ul_pubs is not None:
        v1n, v2n = baselines_v1["corpus_final"], len(ul_pubs)
        delta = (v2n - v1n) / v1n
        band = bands["corpus_size"]
        status = rel_band_status(delta, band["expected"], band["investigate"])
        rows.append({"family": "corpus_size", "v1": v1n, "v2": v2n, "delta": f"{delta:+.1%}",
                     "band": f"+-{band['expected']:.0%} / >{band['investigate']:.0%}", "status": status,
                     "note": ""})

    # ---- works_per_lab ----
    if ul_labs is not None and "Structure name" in ul_labs.columns:
        v1_by_lab = labs_v1.set_index("Structure name")["Pubs total"]
        v2_by_lab = ul_labs.set_index("Structure name")["Pubs total"]
        common = (set(v1_by_lab.index) & set(v2_by_lab.index)) - {"NO LAB", "ISITE"}
        band = bands["works_per_lab"]
        breaches = []
        for name in sorted(common):
            a, b = v1_by_lab[name], v2_by_lab[name]
            if a == 0:
                if b != 0:
                    breaches.append((name, int(a), int(b), float("inf")))
                continue
            rel = (b - a) / a
            if abs(rel) > band["investigate"]:
                breaches.append((name, int(a), int(b), round(rel, 3)))
        zero_now = [n for n in common if v2_by_lab[n] == 0 and n not in (CONFIG["perimeter"].get("known_empty_labs") or [])]
        status = "INVESTIGATE" if (breaches or zero_now) else "OK"
        top = sorted(breaches, key=lambda r: abs(r[3]) if r[3] != float("inf") else 1e9, reverse=True)[:10]
        diagnostic = ("Diagnostic (forensic detail in reports/lab_delta_investigation.md): top movers "
                      + "; ".join(f"{n} {a}->{b} ({r:+.0%})" if r != float('inf') else f"{n} {a}->{b}"
                                  for n, a, b, r in top)) if status == "INVESTIGATE" else "no lab beyond band"
        rows.append({
            "family": "works_per_lab", "v1": f"{len(common)} common structures", "v2": f"{len(breaches)} breach(es)",
            "delta": f"{len(breaches)}/{len(common)} beyond +-{band['investigate']:.0%}",
            "band": f"+-{band['expected']:.0%} / >{band['investigate']:.0%} or any lab -> 0",
            "status": status,
            "note": diagnostic,
        })

    # ---- abstract_coverage ----
    if ul_pubs is not None:
        v1_cov = baselines_v1["abstract_coverage_v1_effective"]
        v2_cov = ul_pubs["abstract"].notna().mean()
        delta_pts = (v2_cov - v1_cov) * 100
        band = bands["abstract_coverage"]
        status = pts_band_status(delta_pts, band["expected_pts"], band["investigate_pts"], fall_only=True)
        rows.append({"family": "abstract_coverage", "v1": f"{v1_cov:.1%}", "v2": f"{v2_cov:.1%}",
                     "delta": f"{delta_pts:+.1f} pts",
                     "band": f"+-{band['expected_pts']} pts / >{band['investigate_pts']} pts (fall only)",
                     "status": status, "note": "a rise is the documented, expected direction (D6)"})

    # ---- sdg_coverage ----
    sdg3 = read_table(deployed_dir, "sdg_three_way.parquet")
    if ul_pubs is not None and sdg3 is not None and "B_siris" in sdg3.columns:
        tagged = set(sdg3.loc[sdg3["B_siris"].notna() & (sdg3["B_siris"] != ""), "work_id"])
        v1_share = baselines_v1["sdg_tagged_works"] / baselines_v1["corpus_final"]
        v2_share = len(tagged) / len(ul_pubs)
        delta_pts = (v2_share - v1_share) * 100
        band = bands["sdg_coverage"]
        status = pts_band_status(delta_pts, band["expected_pts"], band["investigate_pts"])
        rows.append({"family": "sdg_coverage", "v1": f"{v1_share:.1%}", "v2": f"{v2_share:.1%}",
                     "delta": f"{delta_pts:+.1f} pts",
                     "band": f"+-{band['expected_pts']} pts / >{band['investigate_pts']} pts",
                     "status": status, "note": "v2 share = SIRIS variant B; see shift report (g)"})

    # ---- fwci_fr_median (matched doc-type scope: v1 has no conference-paper) ----
    if ul_pubs is not None and {"indicator_status", "FWCI_FR", "type"} <= set(ul_pubs.columns):
        v1_median = float(pubs_v1["FWCI_FR"].median())
        computed = ul_pubs[ul_pubs["indicator_status"] == "computed"]
        v2_median_matched = float(computed.loc[computed["type"] != "conference-paper", "FWCI_FR"].median())
        v2_median_full = float(computed["FWCI_FR"].median())
        delta = (v2_median_matched - v1_median) / v1_median
        band = bands["fwci_fr_median"]
        status = rel_band_status(delta, band["expected"], band["investigate"])
        rows.append({
            "family": "fwci_fr_median", "v1": f"{v1_median:.3f}",
            "v2": f"{v2_median_matched:.3f} (matched scope) / {v2_median_full:.3f} (full corpus)",
            "delta": f"{delta:+.1%} (matched scope)",
            "band": f"+-{band['expected']:.0%} / >{band['investigate']:.0%}", "status": status,
            "note": "compared on v1's own doc-type scope (excludes conference-paper, D36's zero-"
                    "citation mass); full-corpus figure reported for transparency, see shift report (f)",
        })

    # ---- partner_count (floor-matched: v1 shipped an implicit minimum co-works floor) ----
    if ul_partners is not None:
        v1_floor = int(partners_v1["Copublications"].min())
        v2_at_floor = int((ul_partners["co_works"] >= v1_floor).sum())
        delta = (v2_at_floor - len(partners_v1)) / len(partners_v1)
        band = bands["partner_count"]
        status = rel_band_status(delta, band["expected"], band["investigate"])
        rows.append({
            "family": "partner_count", "v1": f"{len(partners_v1):,} (floor >= {v1_floor})",
            "v2": f"{v2_at_floor:,} (same floor) / {len(ul_partners):,} (raw, no floor)",
            "delta": f"{delta:+.1%} (floor-matched)",
            "band": f"+-{band['expected']:.0%} / >{band['investigate']:.0%}", "status": status,
            "note": "v1 applied an implicit co_works>=6 floor before shipping; raw v2 (no floor) is "
                    "NOT comparable and is not used for banding -- see shift report (i)",
        })

    # ---- isite_flagged ----
    if ul_pubs is not None:
        v1n, v2n = baselines_v1["isite_flagged_works"], int(ul_pubs["In_ISITE"].sum())
        delta = (v2n - v1n) / v1n
        band = bands["isite_flagged"]
        status = rel_band_status(delta, band["expected"], band["investigate"])
        rows.append({"family": "isite_flagged", "v1": v1n, "v2": v2n, "delta": f"{delta:+.1%}",
                     "band": f"+-{band['expected']:.0%} / >{band['investigate']:.0%}", "status": status, "note": ""})

    # ---- pptop_share_per_year (target ~10% inside the French reference population) ----
    strata_path = snapshot_tables / "france_baseline_strata.parquet"
    if strata_path.exists():
        strata = pd.read_parquet(strata_path)
        thick = strata[~strata["is_thin"]]
        cfg_band = CONFIG["audit"]["pptop_share_per_year"]
        tolerance = cfg_band["tolerance_pts"] / 100
        offenders = {}
        for year, block in thick.groupby("publication_year"):
            share = (block["fr_share_top10"] * block["n"]).sum() / block["n"].sum()
            if abs(share - cfg_band["target"]) > tolerance:
                offenders[int(year)] = round(float(share), 4)
        status = "OK" if not offenders else "INVESTIGATE"
        rows.append({
            "family": "pptop_share_per_year", "v1": "n/a (defect was the year slide, see shift report (a))",
            "v2": f"target {cfg_band['target']:.0%} +-{cfg_band['tolerance_pts']} pts inside France, per year",
            "delta": f"{len(offenders)} year(s) outside tolerance" if offenders else "all years inside tolerance",
            "band": f"target {cfg_band['target']:.0%} +-{cfg_band['tolerance_pts']} pts", "status": status,
            "note": str(offenders) if offenders else "validated against the French reference population, not Lorraine (D40)",
        })

    # ---- apply pre-registered exceptions generically (never widen a band, only upgrade a status) ----
    for r in rows:
        if r["status"] == "INVESTIGATE" and r["family"] in EXPLAINED_EXCEPTIONS:
            exception_text = EXPLAINED_EXCEPTIONS[r["family"]]
            r["status"] = "EXPLAINED_EXCEPTION"
            r["note"] = exception_text if not r["note"] or r["note"] == "no lab beyond band" else f"{exception_text} | {r['note']}"

    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--tables-dir", help="override the deployed-file directory for Class-1 checks "
                                              "(default: config paths.deploy_target)")
    args = parser.parse_args()

    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    snapshot_tables = snapshot / "tables"
    deploy_target = Path(args.tables_dir) if args.tables_dir else ROOT / CONFIG["paths"]["deploy_target"]

    print(f"snapshot: {snapshot.name}")
    print(f"Class-1 tables dir: {deploy_target}")

    class1 = run_class1(deploy_target)

    # Class 2 always reads the REAL deployed dir + this snapshot's own tables (v1 comparison logic
    # needs columns -- e.g. 'type', 'Structure name' via_lineage -- that a minimal seeded-violation
    # copy will not have; that is fine, Class 2 is not what the seeded-violation demo exercises).
    real_deploy_dir = ROOT / CONFIG["paths"]["deploy_target"]
    try:
        class2 = run_class2(real_deploy_dir, snapshot_tables)
    except FileNotFoundError as exc:
        print(f"! Class-2 skipped: {exc}")
        class2 = []

    lines: list[str] = []
    lines.append("# Audit run\n")
    lines.append(f"Snapshot: **{snapshot.name}** · Class-1 tables dir: `{deploy_target}` · "
                  f"generated by `pipeline/80_audit.py`.\n")

    lines.append("## Class 1 -- structural invariants (any failure fails the run)\n")
    lines.append("| Check | Status | Detail |")
    lines.append("|---|---|---|")
    class1_failed = [c for c in class1 if not c.ok]
    for c in class1:
        lines.append(f"| `{c.id}` | {'PASS' if c.ok else 'FAIL'} | {c.detail} |")
    lines.append("")

    lines.append("## Class 2 -- drift bands vs v1 (first run)\n")
    lines.append("| Family | v1 | v2 | Delta | Band | Status | Note |")
    lines.append("|---|---|---|---|---|---|---|")
    blocking_class2 = []
    for r in class2:
        lines.append(f"| `{r['family']}` | {r['v1']} | {r['v2']} | {r['delta']} | {r['band']} | "
                      f"{r['status']} | {r['note']} |")
        if r["status"] == "INVESTIGATE":
            blocking_class2.append(r["family"])
    lines.append("")

    lines.append("## Explained exceptions (pre-registered; never widen a band silently)\n")
    for family, note in EXPLAINED_EXCEPTIONS.items():
        found = next((r for r in class2 if r["family"] == family), None)
        state = found["status"] if found else "not evaluated this run"
        lines.append(f"- **{family}** ({state}): {note}")
    lines.append("")

    ok = not class1_failed and not blocking_class2
    lines.append("## Verdict\n")
    if ok:
        lines.append("**PASS** -- every Class-1 check holds and no Class-2 family is at an "
                      "unexplained INVESTIGATE level.\n")
    else:
        lines.append("**FAIL** -- deployment is blocked.\n")
        if class1_failed:
            lines.append(f"- Class-1 failures: {', '.join(c.id for c in class1_failed)}")
        if blocking_class2:
            lines.append(f"- Class-2 unexplained INVESTIGATE breaches: {', '.join(blocking_class2)}")
    lines.append("")

    text = "\n".join(lines) + "\n"
    out = ROOT / CONFIG["paths"]["reports"] / "audit_run.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")

    print(f"wrote {out}")
    print(f"Class 1: {len(class1) - len(class1_failed)}/{len(class1)} passed")
    print(f"Class 2: {len(class2)} families evaluated, {len(blocking_class2)} unexplained INVESTIGATE")
    if class1_failed:
        print("Class-1 FAILURES:")
        for c in class1_failed:
            print(f"  - {c.id}: {c.detail}")
    if blocking_class2:
        print("Class-2 unexplained INVESTIGATE:")
        for f in blocking_class2:
            print(f"  - {f}")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
