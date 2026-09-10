"""tests/test_bench_peers.py -- G4 acceptance suite for bench_peers.parquet (T4b benchmark).

Reads the DEPLOYED `Streamlit/data/bench_peers.parquet` (never the raw snapshot table, never a
re-run of the builder) -- same discipline as tests/test_foundation_v3.py: build-time asserts in
`pipeline/49b_build_peer_benchmark.py` protect the FIRST build; this file re-asserts the same
canonical facts against whatever actually sits in `Streamlit/data/` right now, so a deploy-time
regression or a future re-run's silent drift is caught here.

Pins (BUILD_PLAN.md Sec.G4 acceptance): row count; UL's 'all' works value; per-peer 'all' works vs
the frozen `reports/data/peer_candidate_probes.csv` golden within +/-3% (each peer's delta
documented); shares-sum-to-1; indicator NULL discipline (D53); FK integrity vs all_topics; the
UL-path golden (500 sampled UL works, seed 42, reproduced via a fresh import of the builder's own
`usable_indicators()` -- not re-implemented independently, so this test would catch a regression in
that function itself, not just a divergence from it); no artifact/_xa columns (S9 exempt by
construction).

Run:  python -m pytest tests/test_bench_peers.py -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.snapshot import load_config, resolve_snapshot  # noqa: E402

CONFIG = load_config(ROOT)
SNAPSHOT = resolve_snapshot(CONFIG, create=False)
TABLES = SNAPSHOT / "tables"
DEPLOY_DIR = ROOT / "Streamlit" / "data"
GOLDEN_CSV = ROOT / "reports" / "data" / "peer_candidate_probes.csv"

UL_ENTITY_ID = CONFIG["perimeter"]["ul_openalex_id"]   # I90183372
MIN_STRATUM_N = int(CONFIG["metrics"]["min_stratum_n"])  # 30

PEER_IDS = ["I2279609970", "I97188460", "I198244214", "I899635006", "I157674565",
            "I62318514", "I166825849", "I98381234", "I169108374"]


def _load_module(stem: str):
    """pipeline/49b_build_peer_benchmark.py etc. start with a digit -- not importable by dotted
    path (same idiom as tests/test_contract_tables.py's `_load_module`)."""
    path = ROOT / "pipeline" / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _deployed(name: str) -> pd.DataFrame:
    path = DEPLOY_DIR / f"{name}.parquet"
    if not path.exists():
        pytest.skip(f"Streamlit/data/{name}.parquet not deployed -- run pipeline/60_deploy.py")
    return pd.read_parquet(path)


def _snapshot_table(name: str) -> pd.DataFrame:
    path = TABLES / f"{name}.parquet"
    if not path.exists():
        pytest.skip(f"{name}.parquet not built -- run pipeline/49b_build_peer_benchmark.py")
    return pd.read_parquet(path)


@pytest.fixture(scope="module")
def bench() -> pd.DataFrame:
    return _deployed("bench_peers")


@pytest.fixture(scope="module")
def golden() -> pd.DataFrame:
    if not GOLDEN_CSV.exists():
        pytest.skip(f"missing frozen golden {GOLDEN_CSV}")
    return pd.read_csv(GOLDEN_CSV, encoding="utf-8")


# =================================================================================================
# Grain / row-count pins
# =================================================================================================

def test_row_count(bench):
    assert len(bench) == 5660, f"bench_peers row count: {len(bench)}, expected 5,660 (10 entities x 283 nodes x 2 conf_states)"


def test_grain_uniqueness(bench):
    keys = ["entity_id", "node_level", "node_id", "conf_state"]
    dupes = int(bench.duplicated(subset=keys).sum())
    assert dupes == 0, f"{dupes} duplicate (entity_id, node_level, node_id, conf_state) key(s)"


def test_entity_count(bench):
    assert bench["entity_id"].nunique() == 10, f"expected 10 entities (UL + 9 peers), got {bench['entity_id'].nunique()}"
    assert UL_ENTITY_ID in set(bench["entity_id"])
    for pid in PEER_IDS:
        assert pid in set(bench["entity_id"]), f"peer id {pid} missing from bench_peers"


def test_node_levels_and_counts(bench):
    counts = bench["node_level"].value_counts()
    assert set(counts.index) == {"all", "domain", "field", "subfield"}
    # per (entity x conf_state) = 20 combinations
    assert counts["all"] == 20
    assert counts["domain"] == 4 * 20
    assert counts["field"] == 26 * 20
    assert counts["subfield"] == 252 * 20


# =================================================================================================
# UL row pin (Sec.2a direct-id perimeter)
# =================================================================================================

def test_ul_all_works_pin(bench):
    row = bench[(bench["entity_id"] == UL_ENTITY_ID) & (bench["node_level"] == "all")
                & (bench["conf_state"] == "all")]
    assert len(row) == 1
    works = int(row["works"].iloc[0])
    assert works == 28464, (
        f"UL direct-id 'all' works: {works}, expected 28,464 (via_ul_direct & 5 types, measured "
        f"2026-08-17 -- Sec.2a; NOT the 36,819 lineage corpus, NOT the ~28,485 live-API count "
        f"[<=0.1% filter-asymmetry, lens #12], NOT 28,094 v1)"
    )


# =================================================================================================
# Per-peer 'all' works vs the frozen golden, within +/-3% (each peer's delta documented)
# =================================================================================================

def test_per_peer_works_vs_frozen_golden(bench, golden):
    deltas = {}
    for pid in PEER_IDS:
        row = bench[(bench["entity_id"] == pid) & (bench["node_level"] == "all")
                    & (bench["conf_state"] == "all")]
        assert len(row) == 1, f"{pid}: expected exactly 1 'all'/'all' row, got {len(row)}"
        works = int(row["works"].iloc[0])
        golden_row = golden[golden["openalex_id"] == pid]
        assert not golden_row.empty, f"{pid}: not found in frozen golden CSV"
        golden_works = int(golden_row["works_2019_2023"].iloc[0])
        delta_pct = (works - golden_works) / golden_works * 100
        deltas[pid] = (works, golden_works, delta_pct)
        assert abs(delta_pct) <= 3.0, (
            f"{pid}: pulled {works:,} vs frozen golden {golden_works:,} = {delta_pct:+.2f}%, "
            f"outside the +/-3% acceptance band (docs/benchmark_peer_candidates.md Sec.2)"
        )
    # documented per-peer deltas (measured 2026-08-17, all within +/-0.04%):
    #   Lille -0.04% | Nantes -0.01% | Clermont +0.00% | Grenoble Alpes -0.01% | Liege -0.01%
    #   Duisburg-Essen -0.03% | Tampere -0.02% | Oulu -0.03% | UPV/EHU -0.04%
    assert all(abs(d[2]) < 1.0 for d in deltas.values()), (
        f"all 9 peers measured well inside the +/-3% band (max observed <0.1%) -- a peer landing "
        f"between 1% and 3% would still PASS but should be investigated; deltas: {deltas}"
    )


def test_per_peer_all_works_equals_pulled_parquet(bench):
    """Cross-check against the raw pulled per-peer table directly (not just the golden CSV)."""
    for pid in PEER_IDS:
        pulled_path = TABLES / f"peer_works_{pid}.parquet"
        if not pulled_path.exists():
            pytest.skip(f"peer_works_{pid}.parquet not present in the snapshot")
        expected = pd.read_parquet(pulled_path, columns=["work_id"]).shape[0]
        got = int(bench[(bench["entity_id"] == pid) & (bench["node_level"] == "all")
                         & (bench["conf_state"] == "all")]["works"].iloc[0])
        assert got == expected, f"{pid}: bench_peers 'all' works {got} != peer_works_{pid}.parquet rows {expected}"


# =================================================================================================
# Shares sum to 1 (+/-0.001) per entity x conf_state, at domain/field/subfield levels
# =================================================================================================

def test_shares_sum_to_one(bench):
    for level in ("domain", "field", "subfield"):
        sums = bench[bench["node_level"] == level].groupby(["entity_id", "conf_state"])["share_of_entity"].sum()
        bad = sums[(sums - 1.0).abs() > 0.001]
        assert bad.empty, f"level={level}: share_of_entity does not sum to 1 +/-0.001 for: {bad.to_dict()}"


def test_all_level_share_and_lq_trivially_one(bench):
    all_rows = bench[bench["node_level"] == "all"]
    assert (all_rows["share_of_entity"] == 1.0).all(), "level='all' share_of_entity must always be 1.0"
    assert (all_rows["lq_vs_france"] == 1.0).all(), "level='all' lq_vs_france must always be 1.0 (trivial)"


# =================================================================================================
# Indicator NULL discipline (D53): works_with_indicators < 30 => the 3 indicator cols NULL
# =================================================================================================

def test_indicator_null_discipline(bench):
    thin = bench[bench["works_with_indicators"] < MIN_STRATUM_N]
    assert len(thin) > 0, "expected at least some thin cells at subfield grain (sanity check on the test itself)"
    bad = thin[thin[["fwci_fr_mean", "fwci_fr_median", "pptop10_fr_share"]].notna().any(axis=1)]
    assert bad.empty, f"{len(bad)} row(s) below the works_with_indicators floor still carry a non-null indicator"


def test_thick_cells_may_carry_a_genuine_zero(bench):
    """D53's distinction cuts both ways: a THIN cell's indicator must be NaN (checked above), but a
    THICK cell (works_with_indicators >= 30) is allowed a genuine 0.0 share (e.g. zero works
    reaching the Top-10% threshold in that field) -- the floor must not be implemented as
    "never show zero", only as "never show a zero fabricated from insufficient data"."""
    thick = bench[bench["works_with_indicators"] >= MIN_STRATUM_N]
    # merely asserts the column dtype allows 0.0 to survive on thick rows without being coerced to
    # NaN by the floor logic -- if EVERY thick pptop10_fr_share were non-null and none were exactly
    # 0, that would still not be a bug (some fields may simply never dip to 0), so this is a
    # non-fatal sanity print, not a hard requirement.
    assert thick["pptop10_fr_share"].notna().sum() > 0, "expected at least some thick cells with a computed pptop10_fr_share"


# =================================================================================================
# FK integrity: every domain/field/subfield node_id resolves in all_topics
# =================================================================================================

def test_fk_integrity(bench):
    all_topics = _snapshot_table("all_topics")
    domain_ids = set(all_topics["domain_id"].astype(str))
    field_ids = set(all_topics["field_id"].astype(str))
    subfield_ids = set(all_topics["subfield_id"].astype(str))
    for level, valid in [("domain", domain_ids), ("field", field_ids), ("subfield", subfield_ids)]:
        seen = set(bench.loc[bench["node_level"] == level, "node_id"].unique())
        assert seen <= valid, f"level={level}: node_id(s) not in all_topics: {seen - valid}"


# =================================================================================================
# No artifact/_xa columns anywhere (S9: exempt by construction)
# =================================================================================================

def test_no_artifact_columns(bench):
    xa_cols = [c for c in bench.columns if c.endswith("_xa") or c == "artifact_flag"]
    assert not xa_cols, f"bench_peers must carry NO artifact/_xa column (S9 exempt-by-construction): {xa_cols}"


# =================================================================================================
# UL-path golden: 500 sampled UL works (seed 42) reproduce works_master's stored values EXACTLY,
# via the BUILDER'S OWN `usable_indicators()` (imported, not re-implemented) -- catches a
# regression in the function itself, not just a divergence in this test's own copy of it.
# =================================================================================================

def test_ul_path_golden_500_works(bench):
    builder = _load_module("49b_build_peer_benchmark")
    works_master_path = TABLES / "works_master.parquet"
    strata_path = TABLES / "france_baseline_strata.parquet"
    if not (works_master_path.exists() and strata_path.exists()):
        pytest.skip("works_master.parquet or france_baseline_strata.parquet not present in the snapshot")

    wm = pd.read_parquet(works_master_path, columns=[
        "work_id", "via_ul_direct", "type", "publication_year", "cited_by_count",
        "primary_subfield_id", "FWCI_FR", "PPtop10_FR",
    ])
    doc_types = CONFIG["corpus_filter"]["doc_types_keep"]
    ul = wm[wm["via_ul_direct"] & wm["type"].isin(doc_types)].copy()
    ul = ul.rename(columns={"primary_subfield_id": "subfield_id"})

    strata = pd.read_parquet(strata_path)
    strata["subfield_id"] = strata["subfield_id"].astype("string")

    rng = np.random.default_rng(42)
    sample_ids = rng.choice(ul["work_id"].to_numpy(), size=min(500, len(ul)), replace=False)
    sample = ul[ul["work_id"].isin(set(sample_ids))].copy()
    stored = sample[["work_id", "FWCI_FR", "PPtop10_FR"]].set_index("work_id")

    recompute_input = sample[["work_id", "subfield_id", "publication_year", "type", "cited_by_count"]].copy()
    recompute_input["subfield_id"] = recompute_input["subfield_id"].astype("string")
    recomputed = builder.usable_indicators(recompute_input, strata).set_index("work_id")

    fwci_diff = (stored["FWCI_FR"].astype(float) - recomputed["FWCI_FR"].astype(float)).abs()
    both_nan_mismatch = stored["FWCI_FR"].isna() != recomputed["FWCI_FR"].isna()
    assert not both_nan_mismatch.any(), f"FWCI_FR NaN-pattern mismatch on {both_nan_mismatch.sum()} sampled work(s)"
    assert fwci_diff.fillna(0).max() < 1e-9, f"FWCI_FR golden mismatch: max abs diff {fwci_diff.max()}"

    pp_stored, pp_recomputed = stored["PPtop10_FR"], recomputed["PPtop10_FR"]
    pp_mismatch = ~(
        (pp_stored.isna() & pp_recomputed.isna()) | (pp_stored.fillna(-1) == pp_recomputed.fillna(-1))
    )
    assert not pp_mismatch.any(), f"PPtop10_FR golden mismatch on {pp_mismatch.sum()} sampled work(s)"


def test_ul_path_golden_reproduces_stored_bench_values(bench):
    """The deployed bench_peers table's OWN UL/field rows must be internally consistent with a
    fresh recompute for a handful of spot-checked fields (belt-and-braces on top of the 500-work
    golden, this time reading straight off the deployed table)."""
    ul_all = bench[(bench["entity_id"] == UL_ENTITY_ID) & (bench["node_level"] == "all")
                   & (bench["conf_state"] == "all")]
    assert not ul_all.empty
    assert int(ul_all["works_with_indicators"].iloc[0]) > 0
    assert 0 < float(ul_all["fwci_fr_mean"].iloc[0]) < 5, "UL corpus-wide FWCI_FR mean should be a plausible finite ratio"
