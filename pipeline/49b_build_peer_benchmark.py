"""49b_build_peer_benchmark.py -- bench_peers.parquet: UL + 9 peers benchmark table (T4b, G4).

Authority (read in full before editing): BUILD_PLAN.md Sec.G4 + Sec.1 (S4/S5/S9/S10);
docs/pass4_decision_memo.md Sec.3; docs/pass4_challenge_memo.md attacks #12-16; pipeline/49_pull_
peer_benchmark.py (the pull this builder consumes); pipeline/31_build_baseline.py (the stratum
join -- `usable_indicators()` below is a VERBATIM copy of its "usable & mean>0" logic, never
reimplemented, per S5 and challenge memo lens #14); pipeline/47_build_thematic_ext.py's
thm_specialisation section (the activity-LQ construction this table generalises to domain/all).

Grain: entity (UL + 9 peers) x node_level {all, domain, field, subfield} x node_id x
conf_state {all, no_conf}. entity_id is an OpenAlex institution id for every row, INCLUDING UL
(the config's own `perimeter.ul_openalex_id`) -- one uniform id space, no synthetic sentinel.

UL's row (S5): a LOCAL recompute from `works_master.parquet` filtered to `via_ul_direct` and the
5 corpus types -- the DIRECT-id perimeter (measured 28,464), NOT the 36,819 lineage corpus. This
is the peer-symmetric quantity: every peer pull used the exact same direct-id + 5-type recipe
(pipeline/49_pull_peer_benchmark.py), so UL's own row must go through the identical filter, not
the richer canonical corpus. The Sec.2a reconciliation (28,464 here vs 28,485 live-API vs 36,819
canonical vs 28,094 v1) is carried into METHODES.md and the page's method strip -- never silently
picked as "the" UL number without the other three named.

Indicators: EVERY entity (UL included) is run through `usable_indicators()`, the same stratum join
for everyone -- this is itself the golden proof (UL's own recompute must reproduce works_master's
already-stored FWCI_FR/PPtop10_FR, checked explicitly by the golden-500 assert below AND by
tests/test_bench_peers.py, which re-imports this function).

Activity LQ (generalises thm_specialisation's field/subfield-only construction to
{all, domain, field, subfield}): lq_vs_france = (entity's share of node, among its OWN topiced
works) / (France's share of node, among France's OWN topiced works, same conf_state) -- NULL
(never 0/inf, D53) when either side's denominator is 0. `share_of_entity` uses the SAME
topiced-only denominator (not the entity's grand total including untopiced works), which is what
lets shares sum to 1.000 +/-0.001 across nodes at a level (an explicit builder assert below) --
the untopiced remainder is disclosed separately (printed + carried in the manifest), never folded
into the share silently. France's own reference (fr_subfield/fr_field/fr_domain/fr_total) is
built ONCE from france_baseline_strata.parquet and reused unchanged for all 10 entities (the
France side is a fixed external population, identical across the whole table -- the same
"one denominator, not recomputed per subset" discipline the frontier baseline and thm_specialisation
already apply).

D53 floor discipline: fwci_fr_mean / fwci_fr_median / pptop10_fr_share are NULL whenever
works_with_indicators < config.metrics.min_stratum_n (30) for that cell -- never a fabricated
number on a thin cell, and never 0.

No _xa columns anywhere on this table (S9): peer corpora are pulled live from OpenAlex, not the
frozen local artifact-flagged snapshot, so there is no way to know which of a peer's works sit on
an excluded topic -- this table is EXEMPT BY CONSTRUCTION from the artifact toggle, the same
disclosed asymmetry 42b's reciprocity denominators already carry.

Usage: python pipeline/49b_build_peer_benchmark.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)
MIN_STRATUM_N = int(CONFIG["metrics"]["min_stratum_n"])   # 30, D53 floor
DOC_TYPES = CONFIG["corpus_filter"]["doc_types_keep"]      # 5 types, S5
UL_ID = CONFIG["perimeter"]["ul_openalex_id"]              # I90183372 -- UL's own entity_id
STRATUM = ["subfield_id", "publication_year", "type"]      # 31's stratum key, copied verbatim

REGISTRY_PATH = ROOT / "inputs" / "overlays" / "bench_peers.csv"
CONF_STATES = ["all", "no_conf"]


# ================================================================================= 31's join, copied
def usable_indicators(work: pd.DataFrame, strata: pd.DataFrame) -> pd.DataFrame:
    """VERBATIM copy of pipeline/31_build_baseline.py's join (lines ~116-126 of that script,
    2026-08-17 vintage) -- `usable = n not-null & not thin`; FWCI_FR NULL unless usable AND
    mean_citations > 0 (a stratum can be usable/thick with a zero mean if every French work in it
    is uncited); PPtop10_FR is a tie-aware `>=` against the STORED p90 threshold (D40 percentile-
    rank definition) -- never recomputed from a raw distribution, per lens #14's own finding that
    the stored threshold is sufficient for exact reproduction.

    `work` must carry work_id/subfield_id/publication_year/type/cited_by_count; subfield_id must
    be string-typed to match `strata.subfield_id`'s dtype (both sides of the merge key)."""
    joined = work.merge(strata, on=STRATUM, how="left")
    usable = joined["n"].notna() & (~joined["is_thin"].fillna(True))
    joined["FWCI_FR"] = np.where(
        usable & (joined["mean_citations"] > 0),
        joined["cited_by_count"] / joined["mean_citations"].replace(0, np.nan),
        np.nan,
    )
    joined["PPtop10_FR"] = np.where(usable, joined["cited_by_count"] >= joined["p90"], None)
    return joined


# ================================================================================= taxonomy + France
def load_taxonomy(tables: Path) -> pd.DataFrame:
    at = pd.read_parquet(tables / "all_topics.parquet")
    return at.assign(
        domain_id=at["domain_id"].astype(str),
        field_id=at["field_id"].astype(str),
        subfield_id=at["subfield_id"].astype(str),
    )


def build_france_reference(strata: pd.DataFrame, taxo: pd.DataFrame) -> dict:
    """France's own share reference, built ONCE, reused unchanged for every entity's LQ (fixed
    external population -- same discipline as thm_specialisation's fr_field/fr_subfield)."""
    fbs = strata.copy()
    fbs["subfield_id"] = fbs["subfield_id"].astype(str)

    subfield_to_field = taxo.drop_duplicates("subfield_id").set_index("subfield_id")["field_id"]
    field_to_domain = taxo.drop_duplicates("field_id").set_index("field_id")["domain_id"]

    subfield_ids = sorted(taxo["subfield_id"].unique(), key=int)
    field_ids = sorted(taxo["field_id"].unique(), key=int)
    domain_ids = sorted(taxo["domain_id"].unique(), key=int)

    fr_subfield, fr_field, fr_domain, fr_total = {}, {}, {}, {}
    for state in CONF_STATES:
        scoped = fbs if state == "all" else fbs[fbs["type"] != "conference-paper"]
        by_sub = scoped.groupby("subfield_id")["n"].sum()
        fr_subfield[state] = by_sub.reindex(subfield_ids, fill_value=0)
        by_field = fr_subfield[state].groupby(subfield_to_field.reindex(subfield_ids).values).sum()
        fr_field[state] = by_field.reindex(field_ids, fill_value=0)
        by_domain = fr_field[state].groupby(field_to_domain.reindex(field_ids).values).sum()
        fr_domain[state] = by_domain.reindex(domain_ids, fill_value=0)
        fr_total[state] = int(fr_subfield[state].sum())

    return {
        "subfield": fr_subfield, "field": fr_field, "domain": fr_domain, "total": fr_total,
        "subfield_ids": subfield_ids, "field_ids": field_ids, "domain_ids": domain_ids,
        "subfield_to_field": subfield_to_field, "field_to_domain": field_to_domain,
    }


def node_name_lookups(taxo: pd.DataFrame) -> dict:
    return {
        "domain": taxo.drop_duplicates("domain_id").set_index("domain_id")["domain_name"].to_dict(),
        "field": taxo.drop_duplicates("field_id").set_index("field_id")["field_name"].to_dict(),
        "subfield": taxo.drop_duplicates("subfield_id").set_index("subfield_id")["subfield_name"].to_dict(),
    }


# ================================================================================= entity loaders
def load_ul_frame(tables: Path) -> pd.DataFrame:
    """S5: works_master filtered to via_ul_direct & the 5 corpus types -- the direct-id perimeter,
    peer-symmetric with the OpenAlex pulls (NOT the 36,819 lineage corpus, Sec.2a)."""
    wm = pd.read_parquet(tables / "works_master.parquet", columns=[
        "work_id", "via_ul_direct", "type", "publication_year", "cited_by_count",
        "primary_subfield_id", "primary_field_id", "primary_domain_id",
        "FWCI_FR", "PPtop10_FR",
    ])
    ul = wm[wm["via_ul_direct"] & wm["type"].isin(DOC_TYPES)].copy()
    ul = ul.rename(columns={
        "primary_subfield_id": "subfield_id", "primary_field_id": "field_id",
        "primary_domain_id": "domain_id",
    })
    return ul


def load_peer_frame(tables: Path, peer_id: str, taxo: pd.DataFrame) -> pd.DataFrame:
    """A peer's pulled works (pipeline/49). domain_id is DERIVED from field_id via the taxonomy
    rollup (single-primary-topic identity, same reasoning as 42b's domain-derivation edit) --
    never pulled separately, since it is a deterministic function of field_id already in hand."""
    path = tables / f"peer_works_{peer_id}.parquet"
    if not path.exists():
        raise SystemExit(f"missing {path} -- run pipeline/49_pull_peer_benchmark.py first")
    pw = pd.read_parquet(path)
    pw["subfield_id"] = pw["subfield_id"].astype("string")
    pw["field_id"] = pw["field_id"].astype("string")
    field_to_domain = taxo.drop_duplicates("field_id").set_index("field_id")["domain_id"]
    pw["domain_id"] = pw["field_id"].map(field_to_domain)
    return pw


# ================================================================================= aggregation
def make_row(entity_id, entity_name, rung, country, level, node_id, node_name, conf_state,
             works, share, lq, fwci_mean, fwci_median, pptop10, works_with_indicators,
             snapshot_date) -> dict:
    return {
        "entity_id": entity_id, "entity_name": entity_name, "rung": rung, "country": country,
        "node_level": level, "node_id": node_id, "node_name": node_name, "conf_state": conf_state,
        "works": int(works), "share_of_entity": share, "lq_vs_france": lq,
        "fwci_fr_mean": fwci_mean, "fwci_fr_median": fwci_median, "pptop10_fr_share": pptop10,
        "works_with_indicators": int(works_with_indicators), "snapshot_date": snapshot_date,
    }


def aggregate_entity(entity_id: str, entity_name: str, rung: str, country: str,
                      frame: pd.DataFrame, strata: pd.DataFrame, fr: dict, names: dict,
                      snapshot_date: str) -> tuple[list[dict], dict]:
    """One entity's full set of (level, node_id, conf_state) rows. Returns (rows, coverage_report)
    where coverage_report = {'works': int, 'works_with_indicators': int, 'untopiced_all': int,
    'untopiced_no_conf': int} for the calibration/coverage disclosure (challenge memo lens #13)."""
    # UL's frame (load_ul_frame) also carries works_master's OWN stored FWCI_FR/PPtop10_FR (kept
    # there only for main()'s separate golden-recompute check) -- drop them here so this function's
    # OWN recompute (via usable_indicators) is what lands in `f`, for every entity uniformly.
    f = frame.drop(columns=["FWCI_FR", "PPtop10_FR"], errors="ignore").copy()
    f["subfield_id"] = f["subfield_id"].astype("string")
    f["field_id"] = f["field_id"].astype("string")
    f["domain_id"] = f["domain_id"].astype("string")

    ind = usable_indicators(
        f[["work_id", "subfield_id", "publication_year", "type", "cited_by_count"]], strata
    )
    f = f.merge(ind[["work_id", "FWCI_FR", "PPtop10_FR"]], on="work_id", how="left")
    f["PPtop10_FR_num"] = pd.to_numeric(f["PPtop10_FR"], errors="coerce")

    rows: list[dict] = []
    coverage = {}
    for state in CONF_STATES:
        sub = f if state == "all" else f[f["type"] != "conference-paper"]
        entity_total_all = len(sub)
        topiced = sub[sub["subfield_id"].notna()]
        entity_topiced_total = len(topiced)
        untopiced = entity_total_all - entity_topiced_total

        # ---- level = all (headline row; works = the RAW pulled/filtered total, incl. untopiced) ----
        wi_all = int(sub["FWCI_FR"].notna().sum())
        fm = float(sub["FWCI_FR"].mean()) if wi_all >= MIN_STRATUM_N else np.nan
        fmed = float(sub["FWCI_FR"].median()) if wi_all >= MIN_STRATUM_N else np.nan
        pp = float(sub["PPtop10_FR_num"].mean()) if wi_all >= MIN_STRATUM_N else np.nan
        rows.append(make_row(entity_id, entity_name, rung, country, "all", "all", "All fields",
                              state, entity_total_all, 1.0, 1.0, fm, fmed, pp, wi_all, snapshot_date))
        if state == "all":
            coverage = {"works": entity_total_all, "works_with_indicators": wi_all,
                        "untopiced_all": untopiced}
        else:
            coverage["untopiced_no_conf"] = untopiced

        for level, col, node_ids, fr_side in [
            ("domain", "domain_id", fr["domain_ids"], fr["domain"][state]),
            ("field", "field_id", fr["field_ids"], fr["field"][state]),
            ("subfield", "subfield_id", fr["subfield_ids"], fr["subfield"][state]),
        ]:
            grp = topiced.groupby(col, observed=True)
            counts = grp.size().reindex(node_ids, fill_value=0)
            wi_counts = grp["FWCI_FR"].apply(lambda s: int(s.notna().sum())).reindex(node_ids, fill_value=0)
            fwci_mean_s = grp["FWCI_FR"].mean().reindex(node_ids)
            fwci_median_s = grp["FWCI_FR"].median().reindex(node_ids)
            pptop10_s = grp["PPtop10_FR_num"].mean().reindex(node_ids)

            for node_id in node_ids:
                works_n = int(counts[node_id])
                share = (works_n / entity_topiced_total) if entity_topiced_total > 0 else np.nan
                france_works = int(fr_side.get(node_id, 0))
                if france_works > 0 and entity_topiced_total > 0:
                    lq = (works_n / entity_topiced_total) / (france_works / fr["total"][state])
                else:
                    lq = np.nan
                wi_n = int(wi_counts[node_id])
                fm_n = float(fwci_mean_s[node_id]) if wi_n >= MIN_STRATUM_N and pd.notna(fwci_mean_s[node_id]) else np.nan
                fmed_n = float(fwci_median_s[node_id]) if wi_n >= MIN_STRATUM_N and pd.notna(fwci_median_s[node_id]) else np.nan
                pp_n = float(pptop10_s[node_id]) if wi_n >= MIN_STRATUM_N and pd.notna(pptop10_s[node_id]) else np.nan
                rows.append(make_row(
                    entity_id, entity_name, rung, country, level, node_id,
                    names[level].get(node_id, node_id), state, works_n, share, lq,
                    fm_n, fmed_n, pp_n, wi_n, snapshot_date,
                ))
    return rows, coverage


# ================================================================================= main
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    print(f"snapshot {snapshot.name}: building bench_peers (T4b)")

    strata = pd.read_parquet(tables / "france_baseline_strata.parquet")
    strata["subfield_id"] = strata["subfield_id"].astype("string")
    taxo = load_taxonomy(tables)
    fr = build_france_reference(strata, taxo)
    names = node_name_lookups(taxo)

    registry = pd.read_csv(REGISTRY_PATH, encoding="utf-8", keep_default_na=False)
    ok = registry[registry["status"] == "ok"].reset_index(drop=True)
    print(f"registry: {len(ok)} status==ok peer(s)")

    all_rows: list[dict] = []
    coverage_rows: list[dict] = []

    # ---- UL (S5: direct-id perimeter, local recompute -- peer-symmetric) ----
    ul_frame = load_ul_frame(tables)
    print(f"  UL: {len(ul_frame):,} works (via_ul_direct & 5 types -- Sec.2a direct-id perimeter, "
          f"NOT the 36,819 lineage corpus)")
    ul_rows, ul_cov = aggregate_entity(UL_ID, "Universite de Lorraine", "FOCAL", "FR",
                                        ul_frame, strata, fr, names, snapshot.name)
    all_rows.extend(ul_rows)
    coverage_rows.append({"entity_id": UL_ID, "entity_name": "Universite de Lorraine", **ul_cov})

    # ---- 9 peers ----
    for _, row in ok.iterrows():
        peer_id, label, rung, country = row["peer_id"], row["display_name"], row["rung"], row["country"]
        peer_frame = load_peer_frame(tables, peer_id, taxo)
        print(f"  {label} ({peer_id}): {len(peer_frame):,} works pulled")
        rows, cov = aggregate_entity(peer_id, label, rung, country, peer_frame, strata, fr, names,
                                      snapshot.name)
        all_rows.extend(rows)
        coverage_rows.append({"entity_id": peer_id, "entity_name": label, **cov})

    # pass 6 (S-NC cross-stream request, NARRATIVE_CONTRACT_pass6.md sec.5): expose the peer PULL
    # date and the frozen-probe date as DATA -- page 14 currently hardcodes both as literal FR
    # strings (GOLDEN_PROBE_DATE_FR / PEER_PULL_DATE_FR, both "17/08/2026" this pass), which will
    # silently go stale on any future peer refresh. Both dates are read from evidence already on
    # disk, never re-typed: the pull date is this SAME snapshot's own MANIFEST.json record of when
    # step "49_pull_peer_benchmark" (the live OpenAlex peer pull) finished; the frozen-probe date is
    # the mtime of the frozen evidence file itself (reports/data/peer_candidate_probes.csv, the
    # Tampere-calibrated candidate probe this build's own drift band checks against).
    peer_pull_date = None
    manifest_path = tables.parent / "MANIFEST.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        finished = manifest.get("steps", {}).get("49_pull_peer_benchmark", {}).get("finished_utc")
        if finished:
            peer_pull_date = finished[:10]  # YYYY-MM-DD
    if peer_pull_date is None:
        print("  ! no MANIFEST.json record for step 49_pull_peer_benchmark -- peer_pull_date NULL")

    golden_probe_date = None
    probes_path = ROOT / "reports" / "data" / "peer_candidate_probes.csv"
    if probes_path.exists():
        golden_probe_date = dt.date.fromtimestamp(probes_path.stat().st_mtime).isoformat()
    else:
        print(f"  ! {probes_path} not found -- golden_probe_date NULL")
    print(f"  peer_pull_date={peer_pull_date}  golden_probe_date={golden_probe_date}")

    bench = pd.DataFrame(all_rows)
    bench["peer_pull_date"] = peer_pull_date
    bench["golden_probe_date"] = golden_probe_date
    bench = bench.astype({
        "entity_id": "string", "entity_name": "string", "rung": "string", "country": "string",
        "node_level": "string", "node_id": "string", "node_name": "string", "conf_state": "string",
        "works": "int64", "share_of_entity": "float64", "lq_vs_france": "float64",
        "fwci_fr_mean": "float64", "fwci_fr_median": "float64", "pptop10_fr_share": "float64",
        "works_with_indicators": "int64", "snapshot_date": "string",
        "peer_pull_date": "string", "golden_probe_date": "string",
    })
    print(f"\nbuilt bench_peers: {len(bench):,} rows x {len(bench.columns)} cols "
          f"({bench['entity_id'].nunique()} entities)")

    # =================================================================================== asserts
    print("\n" + "=" * 78)
    print("ACCEPTANCE ASSERTS")
    print("=" * 78)

    # ---- 1. shares sum to 1 +/-0.001 per entity x level x conf_state (domain/field/subfield only) ----
    for level in ("domain", "field", "subfield"):
        sums = bench[bench["node_level"] == level].groupby(["entity_id", "conf_state"])["share_of_entity"].sum()
        bad = sums[(sums - 1.0).abs() > 0.001]
        assert bad.empty, f"share_of_entity does not sum to 1 +/-0.001 for level={level}: {bad.to_dict()}"
    print("  shares-sum-to-1 (domain/field/subfield x entity x conf_state): PASS")

    # ---- 2. FK integrity: every domain/field/subfield node_id resolves in all_topics ----
    for level, valid_ids in [("domain", set(fr["domain_ids"])), ("field", set(fr["field_ids"])),
                              ("subfield", set(fr["subfield_ids"]))]:
        seen = set(bench.loc[bench["node_level"] == level, "node_id"].unique())
        assert seen <= valid_ids, f"level={level}: node_id(s) not in all_topics: {seen - valid_ids}"
    print("  FK integrity (node_id resolves in all_topics): PASS")

    # ---- 3. per-peer 'all'/'all' works == the pulled peer_works_<id>.parquet row count ----
    for _, row in ok.iterrows():
        peer_id = row["peer_id"]
        expected = pd.read_parquet(tables / f"peer_works_{peer_id}.parquet", columns=["work_id"]).shape[0]
        got = int(bench[(bench["entity_id"] == peer_id) & (bench["node_level"] == "all")
                         & (bench["conf_state"] == "all")]["works"].iloc[0])
        assert got == expected, f"{peer_id}: bench_peers 'all' works {got} != pulled parquet rows {expected}"
    print("  per-peer 'all' works == pulled parquet row count: PASS (9/9)")

    # ---- 4. indicator NULL discipline: works_with_indicators < 30 => the 3 indicator cols NULL ----
    thin = bench[bench["works_with_indicators"] < MIN_STRATUM_N]
    bad_thin = thin[thin[["fwci_fr_mean", "fwci_fr_median", "pptop10_fr_share"]].notna().any(axis=1)]
    assert bad_thin.empty, f"{len(bad_thin)} row(s) below the works_with_indicators floor still carry a non-null indicator"
    print(f"  D53 NULL discipline (works_with_indicators < {MIN_STRATUM_N} => NULL indicators): PASS "
          f"({len(thin):,} thin cells)")

    # ---- 5. no artifact/_xa columns (S9: exempt by construction) ----
    xa_cols = [c for c in bench.columns if c.endswith("_xa") or c == "artifact_flag"]
    assert not xa_cols, f"bench_peers carries artifact/_xa column(s), should be exempt by construction: {xa_cols}"
    print("  no artifact/_xa columns (S9 exempt-by-construction): PASS")

    # ---- 6. UL-path golden: 500 random UL works, MY join == works_master's own stored values ----
    rng = np.random.default_rng(42)
    ul_all = load_ul_frame(tables)
    sample_ids = rng.choice(ul_all["work_id"].to_numpy(), size=min(500, len(ul_all)), replace=False)
    sample = ul_all[ul_all["work_id"].isin(set(sample_ids))].copy()
    stored = sample[["work_id", "FWCI_FR", "PPtop10_FR"]].set_index("work_id")
    recompute_input = sample.rename(columns={})[["work_id", "subfield_id", "publication_year", "type", "cited_by_count"]]
    recompute_input["subfield_id"] = recompute_input["subfield_id"].astype("string")
    recomputed = usable_indicators(recompute_input, strata).set_index("work_id")

    fwci_diff = (stored["FWCI_FR"].astype(float) - recomputed["FWCI_FR"].astype(float)).abs()
    fwci_diff_ok = fwci_diff.fillna(0).max() < 1e-9  # both-NaN rows -> diff NaN -> filled 0
    both_nan_mismatch = stored["FWCI_FR"].isna() != recomputed["FWCI_FR"].isna()
    assert not both_nan_mismatch.any(), f"FWCI_FR NaN-pattern mismatch on {both_nan_mismatch.sum()} sampled work(s)"
    assert fwci_diff_ok, f"FWCI_FR golden mismatch: max abs diff {fwci_diff.max()}"

    pp_stored = stored["PPtop10_FR"]
    pp_recomputed = recomputed["PPtop10_FR"]
    pp_mismatch = ~(
        (pp_stored.isna() & pp_recomputed.isna())
        | (pp_stored.fillna(-1) == pp_recomputed.fillna(-1))
    )
    assert not pp_mismatch.any(), f"PPtop10_FR golden mismatch on {pp_mismatch.sum()} sampled work(s)"
    print(f"  UL-path golden (500 sampled UL works, seed 42): FWCI_FR + PPtop10_FR EXACT match "
          f"vs works_master's stored values -- PASS")

    # ---- 7. per-entity coverage report (challenge memo lens #13) ----
    print("\ncoverage (works_with_indicators / works, level=all/conf_state=all):")
    low_coverage = []
    for c in coverage_rows:
        pct = c["works_with_indicators"] / c["works"] * 100 if c["works"] else float("nan")
        flag = " <95%!" if pct < 95 else ""
        print(f"  {c['entity_name']} ({c['entity_id']}): {c['works_with_indicators']:,}/{c['works']:,} "
              f"= {pct:.1f}%{flag}  |  untopiced: all={c['untopiced_all']}, no_conf={c.get('untopiced_no_conf', 'n/a')}")
        if pct < 95:
            low_coverage.append((c["entity_name"], pct))

    # =================================================================================== write out
    out_path = tables / "bench_peers.parquet"
    bench.to_parquet(out_path, index=False, compression=CONFIG["storage"]["compression"])
    print(f"\nwrote {out_path.name}: {len(bench):,} rows x {len(bench.columns)} cols")

    lines = [
        f"- bench_peers: **{len(bench):,}** rows ({bench['entity_id'].nunique()} entities x "
        f"{bench['node_level'].nunique()} levels x {bench['conf_state'].nunique()} conf_states)",
        f"- UL row (Sec.2a direct-id perimeter): **{ul_cov['works']:,}** works "
        f"({ul_cov['works_with_indicators']:,} with indicators)",
        "- per-entity coverage (works_with_indicators/works, level=all/conf_state=all):",
    ] + [
        f"  - {c['entity_name']}: {c['works_with_indicators']:,}/{c['works']:,} "
        f"({c['works_with_indicators']/c['works']*100:.1f}%)" for c in coverage_rows
    ] + [
        f"- low-coverage (<95%) entities: {low_coverage if low_coverage else 'none'}",
        "- all acceptance asserts PASSED (shares-sum-to-1, FK integrity, per-peer 'all' works == "
        "pulled count, D53 NULL discipline, no _xa columns, UL-path golden 500-work recompute)",
    ]
    Manifest(snapshot).record_step(
        "49b_build_peer_benchmark",
        counts={"bench_peers_rows": len(bench), "entities": int(bench["entity_id"].nunique())},
        files=[out_path],
        params={"min_stratum_n": MIN_STRATUM_N, "stratum": STRATUM,
                "coverage": coverage_rows, "low_coverage_entities": low_coverage},
        notes="G4 (pass 4): UL + 9 peers, node_level {all,domain,field,subfield} x conf_state "
              "{all,no_conf}. UL-path golden (500-work recompute vs works_master) verified exact.",
    )
    append_summary(snapshot, "49b_build_peer_benchmark", lines)
    print("\n".join(lines))
    print("\ndone.")


if __name__ == "__main__":
    main()
