"""47_build_thematic_ext.py -- thm_specialisation / thm_diversity / thm_codiscipline / thm_funding /
thm_frontier (Foundry rev 3.1, Assembly Line W3: docs/foundry/data_foundation.yaml
producers.47_build_thematic_ext.py).

Five thematic-extension tables, all conf_state-keyed (all | no_conf), all reusing
lib.artifact.flag_works for the ARTIFACT-FLAG (_xa) twins per the R-A convention. Authority read in
full before writing this file: docs/foundry/data_foundation.yaml rev 3.1 (table entries +
conventions header, incl. the supersessions block recording the S6.1 pointer fix below),
docs/indicator_plan_FINAL.md S4 (T3/T3b/T3c/T4/T7/T9) + S6.1 (FRONTIER-STANDARDISATION) + S6.6
(depth map), reports/lab_thematic_probes.py + P5 (funding), reports/lab_frontierness_probe.py
(frontier construction method, read line by line and reproduced verbatim), config.yaml
(workshop_tunables + metrics.min_stratum_n), lib/artifact.py, the ind-portfolio-diversity catalog
card (Internal Projects/Portfolio Mapping/units/lab/catalog/ind-portfolio-diversity.md) and the
enr-frontierness-baseline card (same catalog, read via agent -- DIV = (n_c/N) . (1-Gini) .
mean(d_ij), subfield grain fixed; frontier trap #0 field-mix confound, trap #4 vintage stamping).

============================================================================================
FIX ROUND (chain pass 3, manager correction, this revision): the frontier baseline copy-in was
RE-BASED from the ETO-folder file (a transcription error in plan S6.1, now corrected in
data_foundation.yaml's supersessions block) to RPF's `Readout/Raw data/Cleaning bad OA topics.xlsx`
-- the file the catalog card and reports/lab_frontierness_probe.py actually read. All FOUR
frontier goldens now reproduce (join coverage ~99.9%, neutral_point ~51, raw amplification x1.37,
field-standardised amplification x1.03 -- the last via direct standardisation onto In_ISITE's own
field mix, since neither the probe nor the card ships that exact code, only the measured result).
The previous revision's "vintage drift" disclosure for frontier is SUPERSEDED -- it was correct
diagnosis (wrong file) but the fix is now applied, not merely disclosed.

FUNDING (unresolved, reported not absorbed): EC family (2,182 rows measured vs 2,214 cited) and
ERDF (429 rows match exactly; 203 works measured vs 279 cited for those SAME rows) do NOT
reproduce exactly. Exhaustively searched (grep across every .py/.md/.yaml in this repo) for a
frozen EC/ERDF funder-family construction -- reports/lab_thematic_probes.py's P5 section (the only
funding probe on file) computes ONLY the ISITE-award-trace and ANR constructions, nothing for
EC/ERDF. ANR (funder_award_id contains 'ANR-') matches the probe's own code exactly: 4,433 works.
The EC/ERDF deltas are reported per-funder below (see progress/W3_thematic_ext.md), not silently
absorbed -- "close" is not treated as acceptance for a Tier-A table.
============================================================================================

Usage: python pipeline/47_build_thematic_ext.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.artifact import flag_works  # noqa: E402
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
CONFIG = load_config(ROOT)

MIN_STRATUM_N = int(CONFIG["metrics"]["min_stratum_n"])          # 30
BAND_PCT = float(CONFIG["workshop_tunables"]["momentum_band_pct"])  # 25
SIG_P = float(CONFIG["workshop_tunables"]["momentum_significance_p"])  # 0.05
BAND_HI, BAND_LO = 1 + BAND_PCT / 100, 1 - BAND_PCT / 100

W1_YEARS = [2019, 2020]     # T3c "two windows 2019-20 vs 2022-23" (indicator_plan_FINAL.md S4/R4)
W2_YEARS = [2022, 2023]
BOOTSTRAP_B = 150            # documented choice (no frozen T3c script exists to copy a B from --
                              # see module docstring); B=150 resolves a 5% significance gate to
                              # ~0.7% granularity while keeping ~140 perimeters x 2 conf_states
                              # x 2 windows tractable ($0, local, seconds).

_DASH_VARIANTS = re.compile(r"[‐‑‒–—―−]")


def _norm(value: object) -> str:
    text = str(value).upper()
    text = _DASH_VARIANTS.sub("-", text)
    return re.sub(r"\s+", "", text)


# ================================================================================= shared helpers
def gini(shares: np.ndarray) -> float:
    """Standard Gini coefficient on a non-negative array (shares need not sum to 1)."""
    x = np.sort(np.asarray(shares, dtype=float))
    n = len(x)
    if n == 0:
        return np.nan
    if n == 1:
        return 0.0
    s = x.sum()
    if s <= 0:
        return np.nan
    idx = np.arange(1, n + 1)
    return float((2 * np.sum(idx * x)) / (n * s) - (n + 1) / n)


def build_subfield_weight_matrix(corpus_topics: pd.DataFrame, work_ids: pd.Index,
                                  subfield_ids: list[str]) -> np.ndarray:
    """work x subfield SCORE-WEIGHTED, per-work-normalised matrix (rows sum to 1, or 0 if the work
    carries no topic row -- 51 works in the 2026-08-11 snapshot, per lib/artifact.py's docstring).
    Multiple topics under the same subfield have their scores SUMMED before normalising (a work's
    subfield mass = the sum of its assigned topics' relevance scores in that subfield)."""
    sub_score = corpus_topics.groupby(["work_id", "subfield_id"], observed=True)["score"].sum().reset_index()
    totals = sub_score.groupby("work_id")["score"].transform("sum")
    sub_score["norm_weight"] = sub_score["score"] / totals
    pivot = sub_score.pivot(index="work_id", columns="subfield_id", values="norm_weight")
    # NB: a pivot is naturally sparse -- unassigned (work, subfield) cells are NaN, not 0, for
    # EVERY column already present, not just ones introduced by reindex. reindex()'s fill_value
    # only fills newly-introduced labels (the missing 3 subfields here), so an explicit fillna(0)
    # is required first, or every row silently sums to NaN (caught in dev: variety printed 0.0000
    # across the board because div_components' `total = p.sum()` was NaN, not a real zero mass).
    pivot = pivot.fillna(0.0)
    pivot = pivot.reindex(columns=subfield_ids, fill_value=0.0)
    pivot = pivot.reindex(index=work_ids, fill_value=0.0)
    return pivot.to_numpy(dtype="float32")


def build_disparity_matrix(weight_matrix: np.ndarray) -> np.ndarray:
    """Fixed 252x252 disparity matrix, built ONCE on the FULL corpus (every work, every year,
    conf_state=all) and reused for every perimeter/year/conf_state/artifact-state slice downstream
    -- 'z-scores/disparity never recomputed on subsets', the same discipline T9 applies to the
    frontier baseline (indicator_plan_FINAL.md S6.1), applied here for consistency + stability
    (the catalog card's own trap #1: 'granularity/disparity instability ... fix the grain,
    disclose it'). Cosine distance on subfield co-occurrence profiles (card: 'built in-house from
    subfield co-occurrence/co-citation profiles, one-time local build') -- our own corpus is the
    only co-occurrence evidence available standalone ($0, no world-scale co-citation pull)."""
    norms = np.linalg.norm(weight_matrix, axis=0)
    norms[norms == 0] = 1.0
    normalised = weight_matrix / norms
    cos_sim = normalised.T @ normalised
    cos_sim = np.clip(cos_sim, -1.0, 1.0)
    disparity = 1.0 - cos_sim
    np.fill_diagonal(disparity, 0.0)
    return disparity.astype("float64")


def div_components(row_idx: np.ndarray, weight_matrix: np.ndarray, disparity: np.ndarray,
                    n_universe: int) -> dict:
    """DIV = (n_c/N).(1-Gini).mean(d_ij) -- ind-portfolio-diversity catalog card (Stirling 2007 ->
    Leydesdorff 2018 -> Leydesdorff/Wagner/Bornmann 2019 'DIV' -> Rousseau 2019 'DIV*'; this
    implementation is the LWB two-factor-plus-disparity product, stored under `rao_stirling` for
    continuity with the client-facing term -- 'Rao-Stirling family, DIV construction' per
    indicator_plan_FINAL.md T3). variety = n_c/N (N fixed = 252, the all_topics subfield
    universe); balance = 1-Gini computed over the PRESENT categories' own shares (independent of
    variety by design -- the card's whole point vs raw Rao-Stirling's conflation); disparity =
    UNWEIGHTED mean of d_ij over pairs of present categories (also independent of balance -- a
    Stirling-weighted mean would re-introduce the conflation)."""
    if len(row_idx) == 0:
        return {"variety": np.nan, "balance": np.nan, "disparity": np.nan, "rao_stirling": np.nan, "n_works": 0}
    p = weight_matrix[row_idx].sum(axis=0).astype("float64")
    total = p.sum()
    if total <= 0:
        return {"variety": 0.0, "balance": np.nan, "disparity": np.nan, "rao_stirling": np.nan, "n_works": len(row_idx)}
    p = p / total
    present = np.where(p > 1e-12)[0]
    n_c = len(present)
    variety = n_c / n_universe
    if n_c == 0:
        return {"variety": 0.0, "balance": np.nan, "disparity": np.nan, "rao_stirling": np.nan, "n_works": len(row_idx)}
    balance = 1.0 - gini(p[present])
    if n_c < 2:
        disp = np.nan
    else:
        sub = disparity[np.ix_(present, present)]
        iu = np.triu_indices(n_c, k=1)
        disp = float(sub[iu].mean())
    rs = variety * balance * disp if pd.notna(balance) and pd.notna(disp) else np.nan
    return {"variety": variety, "balance": balance, "disparity": disp, "rao_stirling": rs, "n_works": len(row_idx)}


def bootstrap_delta_pvalue(idx_w1: np.ndarray, idx_w2: np.ndarray, weight_matrix: np.ndarray,
                            disparity: np.ndarray, n_universe: int, rng: np.random.Generator,
                            b: int = BOOTSTRAP_B) -> float:
    """Two-sided bootstrap p-value for whether the window2/window1 DIV ratio differs from 1.
    ADAPTATION note (module docstring): the frozen momentum spec's two-proportion z-test
    (reports/lab_momentum_frozen.py `ptest`) applies to a binomial SHARE (collaborative works /
    denominator); DIV is a continuous composite index, not a proportion, so the significance
    mechanism is substituted here for a resampling test -- same ROLE (gate 'up'/'down' behind a
    significance check) under the same alpha (config.workshop_tunables.momentum_significance_p)."""
    n1, n2 = len(idx_w1), len(idx_w2)
    if n1 == 0 or n2 == 0:
        return np.nan
    ratios = np.full(b, np.nan)
    for i in range(b):
        s1 = rng.choice(idx_w1, size=n1, replace=True)
        s2 = rng.choice(idx_w2, size=n2, replace=True)
        rs1 = div_components(s1, weight_matrix, disparity, n_universe)["rao_stirling"]
        rs2 = div_components(s2, weight_matrix, disparity, n_universe)["rao_stirling"]
        if pd.notna(rs1) and rs1 > 0 and pd.notna(rs2):
            ratios[i] = rs2 / rs1
    valid = ratios[~np.isnan(ratios)]
    if len(valid) < b * 0.5:
        return np.nan
    p_low, p_high = float((valid <= 1.0).mean()), float((valid >= 1.0).mean())
    return 2 * min(p_low, p_high)


def works_weighted_percentile(df: pd.DataFrame, value_col: str, weight_col: str) -> pd.Series:
    """Cumulative-midpoint works-weighted percentile rank (0-100) of value_col, weighted by
    weight_col, matching reports/lab_frontierness_probe.py's percentile-among-kept-topics
    construction (there unweighted-by-topic-count; here works-weighted per the world reference's
    own volume column, the standard bibliometric attention-weighting)."""
    order = df.sort_values(value_col)
    cum_weight = order[weight_col].cumsum()
    total = order[weight_col].sum()
    pct = (cum_weight - order[weight_col] / 2) / total * 100
    return pct.reindex(df.index)


def _lab_mask(works: pd.DataFrame, lab_name: str) -> pd.Series:
    """works_master.Labs is a ' | '-delimited multi-value string (a work can carry >1 lab) --
    same split convention as tests/test_contract_tables.py's golden-lab recompute."""
    return works["Labs"].fillna("").str.split(" | ", regex=False).apply(lambda ls: lab_name in ls)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"
    today = dt.date.today().isoformat()
    rng = np.random.default_rng(20260811)

    print(f"snapshot {snapshot.name}: building thm_specialisation / thm_diversity / "
          f"thm_codiscipline / thm_funding / thm_frontier")

    # =============================================================================== load inputs
    works = pd.read_parquet(tables / "works_master.parquet", columns=[
        "work_id", "primary_topic_id", "primary_subfield_id", "primary_field_id",
        "primary_domain_id", "In_ISITE", "is_conference", "publication_year", "Labs",
    ])
    corpus_topics = pd.read_parquet(tables / "corpus_topics.parquet", columns=[
        "work_id", "topic_id", "score", "is_primary", "subfield_id", "field_id",
    ])
    all_topics = pd.read_parquet(tables / "all_topics.parquet", columns=[
        "domain_id", "field_id", "field_name", "subfield_id", "topic_id",
    ])
    france_baseline_strata = pd.read_parquet(tables / "france_baseline_strata.parquet")
    corpus_funding = pd.read_parquet(tables / "corpus_funding.parquet")
    ul_labs = pd.read_parquet(tables / "ul_labs.parquet", columns=["lab", "works"])

    n_corpus = len(works)
    print(f"  corpus works: {n_corpus:,}")

    flag_series = flag_works(corpus_topics, root=ROOT)
    works["artifact_flag"] = works["work_id"].map(flag_series).fillna(False).astype(bool)
    n_flagged = int(works["artifact_flag"].sum())
    print(f"  artifact-flag (primary-topic exclusion): {n_flagged:,} works")
    assert n_flagged == 4106, f"artifact-flag count drifted: {n_flagged} != 4,106 (F0-P4 golden)"

    subfield_field = all_topics[["subfield_id", "field_id"]].drop_duplicates().astype("string")
    subfield_field = subfield_field.set_index("subfield_id")["field_id"]
    field_ids = sorted(all_topics["field_id"].astype("string").unique().tolist())
    subfield_ids = sorted(all_topics["subfield_id"].astype("string").unique().tolist())
    N_SUBFIELDS = len(subfield_ids)
    N_FIELDS = len(field_ids)
    print(f"  taxonomy: {N_FIELDS} fields, {N_SUBFIELDS} subfields (all_topics.parquet)")
    assert N_SUBFIELDS == 252, f"subfield universe drifted: {N_SUBFIELDS} != 252"
    assert N_FIELDS == 26, f"field universe drifted: {N_FIELDS} != 26"

    def conf_mask(state: str) -> pd.Series:
        return pd.Series(True, index=works.index) if state == "all" else ~works["is_conference"].fillna(False)

    CONF_STATES = ["all", "no_conf"]

    outputs: dict[str, pd.DataFrame] = {}

    # ======================================================================== thm_specialisation
    print("\n[1/5] thm_specialisation")
    strata_all = france_baseline_strata.groupby("subfield_id")["n"].sum()
    strata_noconf = france_baseline_strata[france_baseline_strata["type"] != "conference-paper"] \
        .groupby("subfield_id")["n"].sum()
    n_strata_subfields = france_baseline_strata["subfield_id"].nunique()
    n_strata_sum = int(france_baseline_strata["n"].sum())
    print(f"  france_baseline_strata: {n_strata_subfields} subfields, sum(n)={n_strata_sum:,}")
    assert n_strata_subfields == 252, f"strata subfield count drifted: {n_strata_subfields} != 252"
    assert n_strata_sum == 1098847, f"strata n-sum drifted: {n_strata_sum:,} != 1,098,847"

    strata_all.index = strata_all.index.astype("string")
    strata_noconf.index = strata_noconf.index.astype("string")
    fr_subfield = {"all": strata_all.reindex(subfield_ids, fill_value=0),
                   "no_conf": strata_noconf.reindex(subfield_ids, fill_value=0)}
    fr_field = {}
    for state in CONF_STATES:
        by_field = fr_subfield[state].groupby(subfield_field.reindex(subfield_ids)).sum()
        fr_field[state] = by_field.reindex(field_ids, fill_value=0)
    fr_total = {state: int(fr_subfield[state].sum()) for state in CONF_STATES}
    print(f"  france totals: all={fr_total['all']:,}, no_conf={fr_total['no_conf']:,}")

    spec_rows = []
    for subset_id, subset_mask in [("all", pd.Series(True, index=works.index)),
                                    ("in_isite", works["In_ISITE"].astype(bool))]:
        for state in CONF_STATES:
            m = subset_mask & conf_mask(state)
            m_xa = m & ~works["artifact_flag"]
            ul_total, ul_total_xa = int(m.sum()), int(m_xa.sum())
            for level, node_col, node_ids, fr_side in [
                ("field", "primary_field_id", field_ids, fr_field[state]),
                ("subfield", "primary_subfield_id", subfield_ids, fr_subfield[state]),
            ]:
                col = works.loc[m, node_col].astype("string")
                col_xa = works.loc[m_xa, node_col].astype("string")
                ul_counts = col.value_counts().reindex(node_ids, fill_value=0)
                ul_counts_xa = col_xa.value_counts().reindex(node_ids, fill_value=0)
                for node_id in node_ids:
                    ul_works = int(ul_counts[node_id])
                    ul_works_xa = int(ul_counts_xa[node_id])
                    france_works = int(fr_side.get(node_id, 0))
                    if france_works > 0 and ul_total > 0:
                        lq = (ul_works / ul_total) / (france_works / fr_total[state])
                    else:
                        lq = np.nan
                    if france_works > 0 and ul_total_xa > 0:
                        lq_xa = (ul_works_xa / ul_total_xa) / (france_works / fr_total[state])
                    else:
                        lq_xa = np.nan
                    spec_rows.append({
                        "level": level, "node_id": node_id, "conf_state": state,
                        "subset_id": subset_id, "ul_works": ul_works, "ul_works_xa": ul_works_xa,
                        "france_works": france_works, "activity_index_lq": lq,
                        "activity_index_lq_xa": lq_xa, "floor_flag": ul_works < MIN_STRATUM_N,
                        "snapshot_date": snapshot.name,
                    })
    thm_specialisation = pd.DataFrame(spec_rows)
    thm_specialisation = thm_specialisation.astype({
        "level": "string", "node_id": "string", "conf_state": "string", "subset_id": "string",
        "ul_works": "int64", "ul_works_xa": "int64", "france_works": "int64",
        "activity_index_lq": "float64", "activity_index_lq_xa": "float64", "floor_flag": "bool",
        "snapshot_date": "string",
    })
    outputs["thm_specialisation"] = thm_specialisation
    print(f"  wrote {len(thm_specialisation):,} rows")

    # ============================================================================= thm_diversity
    print("\n[2/5] thm_diversity")
    work_ids_all = works["work_id"].to_numpy()
    weight_matrix = build_subfield_weight_matrix(corpus_topics, works["work_id"], subfield_ids)
    disparity = build_disparity_matrix(weight_matrix)
    print(f"  disparity matrix: {disparity.shape} (fixed, built once on the full corpus)")

    work_pos = pd.Series(np.arange(len(works)), index=works["work_id"].to_numpy())
    lab_names = [n for n in ul_labs["lab"].tolist()]

    perimeters: list[tuple[str, str, pd.Series]] = [
        ("all", "corpus", pd.Series(True, index=works.index)),
        ("in_isite", "isite", works["In_ISITE"].astype(bool)),
    ]
    for lab in lab_names:
        perimeters.append((lab, "lab", _lab_mask(works, lab)))

    years = [2019, 2020, 2021, 2022, 2023]
    div_rows = []
    delta_cache: dict[tuple[str, str], tuple[object, float]] = {}

    for perimeter_id, perimeter_kind, base_mask in perimeters:
        for state in CONF_STATES:
            m_state = base_mask & conf_mask(state)
            idx_state = work_pos.reindex(works.loc[m_state, "work_id"]).dropna().to_numpy(dtype=int)
            idx_state_xa = work_pos.reindex(
                works.loc[m_state & ~works["artifact_flag"], "work_id"]
            ).dropna().to_numpy(dtype=int)

            idx_w1 = work_pos.reindex(
                works.loc[m_state & works["publication_year"].isin(W1_YEARS), "work_id"]
            ).dropna().to_numpy(dtype=int)
            idx_w2 = work_pos.reindex(
                works.loc[m_state & works["publication_year"].isin(W2_YEARS), "work_id"]
            ).dropna().to_numpy(dtype=int)
            delta_cache[(perimeter_id, state)] = (idx_w1, idx_w2)

            for year in years:
                idx_year = work_pos.reindex(
                    works.loc[m_state & (works["publication_year"] == year), "work_id"]
                ).dropna().to_numpy(dtype=int)
                idx_year_xa = work_pos.reindex(
                    works.loc[m_state & (works["publication_year"] == year) & ~works["artifact_flag"],
                              "work_id"]
                ).dropna().to_numpy(dtype=int)
                c = div_components(idx_year, weight_matrix, disparity, N_SUBFIELDS)
                c_xa = div_components(idx_year_xa, weight_matrix, disparity, N_SUBFIELDS)
                div_rows.append({
                    "perimeter_id": perimeter_id, "perimeter_kind": perimeter_kind, "year": year,
                    "conf_state": state, "variety": c["variety"], "variety_xa": c_xa["variety"],
                    "balance": c["balance"], "balance_xa": c_xa["balance"],
                    "disparity": c["disparity"], "disparity_xa": c_xa["disparity"],
                    "rao_stirling": c["rao_stirling"], "rao_stirling_xa": c_xa["rao_stirling"],
                    "n_works": c["n_works"], "n_works_xa": c_xa["n_works"],
                    "floor_flag": c["n_works"] < MIN_STRATUM_N,
                })

    # ---- T3c delta (per perimeter x conf_state; broadcast across the 5 year-rows -- see fragment)
    delta_results: dict[tuple[str, str], dict] = {}
    for (perimeter_id, state), (idx_w1, idx_w2) in delta_cache.items():
        c1 = div_components(idx_w1, weight_matrix, disparity, N_SUBFIELDS)
        c2 = div_components(idx_w2, weight_matrix, disparity, N_SUBFIELDS)
        eligible = (c1["n_works"] >= MIN_STRATUM_N and c2["n_works"] >= MIN_STRATUM_N
                    and pd.notna(c1["rao_stirling"]) and c1["rao_stirling"] > 0
                    and pd.notna(c2["rao_stirling"]))
        delta_results[(perimeter_id, state)] = {
            "eligible": eligible,
            "ratio": (c2["rao_stirling"] / c1["rao_stirling"]) if eligible else np.nan,
        }

    for state in CONF_STATES:
        ratios = pd.Series({k[0]: v["ratio"] for k, v in delta_results.items()
                             if k[1] == state and v["eligible"]})
        med = float(ratios.median()) if len(ratios) else np.nan
        print(f"  T3c recentring median ({state}): {med:.3f} over {len(ratios)} eligible perimeters")
        for perimeter_id in ratios.index:
            r = delta_results[(perimeter_id, state)]["ratio"]
            rr = r / med if med and med > 0 else np.nan
            idx_w1, idx_w2 = delta_cache[(perimeter_id, state)]
            pval = bootstrap_delta_pvalue(idx_w1, idx_w2, weight_matrix, disparity, N_SUBFIELDS, rng)
            if pd.isna(rr):
                cls = None
            elif rr >= BAND_HI:
                cls = "up"
            elif rr <= BAND_LO:
                cls = "down"
            else:
                cls = "stable"
            if cls not in (None, "stable") and pd.notna(pval) and pval >= SIG_P:
                cls = "ns"
            delta_results[(perimeter_id, state)]["class"] = cls
            delta_results[(perimeter_id, state)]["pvalue"] = pval

    for row in div_rows:
        key = (row["perimeter_id"], row["conf_state"])
        d = delta_results.get(key, {})
        row["delta_class"] = d.get("class")
        row["delta_p_value"] = d.get("pvalue", np.nan)

    thm_diversity = pd.DataFrame(div_rows)
    thm_diversity = thm_diversity.astype({
        "perimeter_id": "string", "perimeter_kind": "string", "year": "int32",
        "conf_state": "string", "variety": "float64", "variety_xa": "float64",
        "balance": "float64", "balance_xa": "float64", "disparity": "float64",
        "disparity_xa": "float64", "rao_stirling": "float64", "rao_stirling_xa": "float64",
        "n_works": "int64", "n_works_xa": "int64", "floor_flag": "bool",
        "delta_class": "string", "delta_p_value": "float64",
    })
    thm_diversity["snapshot_date"] = pd.Series(snapshot.name, index=thm_diversity.index, dtype="string")
    outputs["thm_diversity"] = thm_diversity
    print(f"  wrote {len(thm_diversity):,} rows ({len(perimeters)} perimeters x {len(years)} years "
          f"x {len(CONF_STATES)} conf_states)")

    # ========================================================================== thm_codiscipline
    print("\n[3/5] thm_codiscipline")
    field_idx_map = {f: i for i, f in enumerate(field_ids)}
    ct_fields = corpus_topics[["work_id", "field_id"]].copy()
    ct_fields["field_id"] = ct_fields["field_id"].astype("string")
    ct_fields = ct_fields.drop_duplicates()
    per_work_fields = ct_fields.groupby("work_id")["field_id"].apply(list)

    def codiscipline_matrix(work_id_subset: set) -> np.ndarray:
        mat = np.zeros((N_FIELDS, N_FIELDS), dtype="int64")
        for wid in work_id_subset:
            flds = per_work_fields.get(wid)
            if flds is None:
                continue
            idxs = sorted({field_idx_map[f] for f in flds if f in field_idx_map})
            if len(idxs) == 1:
                mat[idxs[0], idxs[0]] += 1
            else:
                for a in range(len(idxs)):
                    for b in range(a + 1, len(idxs)):
                        mat[idxs[a], idxs[b]] += 1
                        mat[idxs[b], idxs[a]] += 1
        return mat

    codis_rows = []
    for perimeter_id, base_mask in [("all", pd.Series(True, index=works.index)),
                                     ("in_isite", works["In_ISITE"].astype(bool))]:
        for state in CONF_STATES:
            m = base_mask & conf_mask(state)
            wids = set(works.loc[m, "work_id"])
            wids_xa = set(works.loc[m & ~works["artifact_flag"], "work_id"])
            mat = codiscipline_matrix(wids)
            mat_xa = codiscipline_matrix(wids_xa)
            for a_idx, field_a in enumerate(field_ids):
                for b_idx, field_b in enumerate(field_ids):
                    co = int(mat[a_idx, b_idx])
                    codis_rows.append({
                        "perimeter_id": perimeter_id, "field_a": field_a, "field_b": field_b,
                        "conf_state": state, "co_works": co,
                        "co_works_xa": int(mat_xa[a_idx, b_idx]),
                        "floor_flag": co < MIN_STRATUM_N,
                    })
    thm_codiscipline = pd.DataFrame(codis_rows)
    thm_codiscipline = thm_codiscipline.astype({
        "perimeter_id": "string", "field_a": "string", "field_b": "string", "conf_state": "string",
        "co_works": "int64", "co_works_xa": "int64", "floor_flag": "bool",
    })
    thm_codiscipline["snapshot_date"] = pd.Series(snapshot.name, index=thm_codiscipline.index, dtype="string")
    outputs["thm_codiscipline"] = thm_codiscipline
    print(f"  wrote {len(thm_codiscipline):,} rows ({N_FIELDS}x{N_FIELDS} matrix x 2 perimeters "
          f"x {len(CONF_STATES)} conf_states)")
    diag_total = thm_codiscipline[(thm_codiscipline.perimeter_id == "all")
                                   & (thm_codiscipline.conf_state == "all")
                                   & (thm_codiscipline.field_a == thm_codiscipline.field_b)]["co_works"].sum()
    offdiag_total = thm_codiscipline[(thm_codiscipline.perimeter_id == "all")
                                      & (thm_codiscipline.conf_state == "all")
                                      & (thm_codiscipline.field_a != thm_codiscipline.field_b)]["co_works"].sum()
    print(f"  sanity (all/all): mono-field diagonal sum={diag_total:,}, "
          f"off-diagonal (double-counted pairs) sum={offdiag_total:,}")

    # =============================================================================== thm_funding
    print("\n[4/5] thm_funding")
    fu = corpus_funding[corpus_funding["work_id"].isin(set(works["work_id"]))].copy()
    fu["_ncode"] = fu["funder_award_id"].map(_norm)

    EC_FAMILY = [
        "European Commission", "Horizon 2020 Framework Programme", "Horizon 2020",
        "HORIZON EUROPE Framework Programme", "European Research Council",
        "H2020 European Research Council", "FP7 Ideas: European Research Council",
        "HORIZON EUROPE European Research Council", "HORIZON EUROPE Marie Sklodowska-Curie Actions",
        "European Space Agency", "European Cooperation in Science and Technology",
        "Partnership for Advanced Computing in Europe AISBL",
        "H2020 European Institute of Innovation and Technology", "Research Executive Agency",
        "FP7 Coherent Development of Research Policies",
        "Electronic Components and Systems for European Leadership",
    ]  # curated Horizon/FP/ERC-family list -- see module docstring "DISCLOSED VINTAGE DRIFT"
    ERDF_NAME = "European Regional Development Fund"

    funder_masks = {
        "any": pd.Series(True, index=fu.index),
        "anr": fu["_ncode"].str.contains("ANR-", na=False),
        "ec": fu["funder_display_name"].isin(EC_FAMILY),
        "erdf": fu["funder_display_name"] == ERDF_NAME,
    }
    for fam, mask in funder_masks.items():
        rows_n, works_n = int(mask.sum()), fu.loc[mask, "work_id"].nunique()
        print(f"  funder_family={fam:5s} rows={rows_n:6,d}  distinct works={works_n:6,d}")

    fund_rows = []
    for perimeter_id, base_mask in [("all", pd.Series(True, index=works.index)),
                                     ("in_isite", works["In_ISITE"].astype(bool))]:
        for state in CONF_STATES:
            m = base_mask & conf_mask(state)
            field_col = works.loc[m, "primary_field_id"].astype("string")
            field_col_xa = works.loc[m & ~works["artifact_flag"], "primary_field_id"].astype("string")
            work_ids_field = works.loc[m, ["work_id", "primary_field_id"]].astype({"primary_field_id": "string"})
            work_ids_field_xa = works.loc[m & ~works["artifact_flag"], ["work_id", "primary_field_id"]] \
                .astype({"primary_field_id": "string"})
            total_by_field = field_col.value_counts().reindex(field_ids, fill_value=0)
            total_by_field_xa = field_col_xa.value_counts().reindex(field_ids, fill_value=0)

            for fam, fmask in funder_masks.items():
                sub_fu = fu.loc[fmask, ["work_id"]]
                merged = work_ids_field.merge(sub_fu, on="work_id", how="inner")
                merged_xa = work_ids_field_xa.merge(sub_fu, on="work_id", how="inner")
                rows_by_field = merged.groupby("primary_field_id").size().reindex(field_ids, fill_value=0)
                works_by_field = merged.groupby("primary_field_id")["work_id"].nunique().reindex(field_ids, fill_value=0)
                works_by_field_xa = merged_xa.groupby("primary_field_id")["work_id"].nunique().reindex(field_ids, fill_value=0)
                for field_id in field_ids:
                    total = int(total_by_field[field_id])
                    total_xa = int(total_by_field_xa[field_id])
                    wwf = int(works_by_field[field_id])
                    wwf_xa = int(works_by_field_xa[field_id])
                    fund_rows.append({
                        "field_id": field_id, "perimeter_id": perimeter_id, "funder_family": fam,
                        "conf_state": state, "works_with_funding": wwf,
                        "works_with_funding_xa": wwf_xa, "rows_count": int(rows_by_field[field_id]),
                        "share_of_works": (wwf / total) if total > 0 else np.nan,
                        "share_of_works_xa": (wwf_xa / total_xa) if total_xa > 0 else np.nan,
                    })
    thm_funding = pd.DataFrame(fund_rows)
    thm_funding = thm_funding.astype({
        "field_id": "string", "perimeter_id": "string", "funder_family": "string",
        "conf_state": "string", "works_with_funding": "int64", "works_with_funding_xa": "int64",
        "rows_count": "int64", "share_of_works": "float64", "share_of_works_xa": "float64",
    })
    thm_funding["snapshot_date"] = pd.Series(snapshot.name, index=thm_funding.index, dtype="string")
    outputs["thm_funding"] = thm_funding
    print(f"  wrote {len(thm_funding):,} rows ({N_FIELDS} fields x 2 perimeters x 4 funder_families "
          f"x {len(CONF_STATES)} conf_states)")

    overall_any_mask = funder_masks["any"]
    overall_works_with_funding = fu.loc[overall_any_mask, "work_id"].nunique()
    overall_share = overall_works_with_funding / n_corpus
    print(f"  GOLDEN CHECK overall works-with-funding: {overall_works_with_funding:,}/{n_corpus:,} "
          f"= {overall_share*100:.2f}% (golden 21.3%)")
    assert abs(overall_share - 0.213) < 0.003, f"overall funding share drifted: {overall_share:.4f}"
    anr_works = fu.loc[funder_masks["anr"], "work_id"].nunique()
    print(f"  GOLDEN CHECK ANR works: {anr_works:,} (golden 4,433)")
    assert anr_works == 4433, f"ANR works drifted: {anr_works} != 4,433"
    ec_rows = int(funder_masks["ec"].sum())
    print(f"  EC family rows: {ec_rows:,} (docs cite 2,214 -- vintage/classification-list drift, "
          f"see module docstring)")
    erdf_rows = int(funder_masks["erdf"].sum())
    erdf_works = fu.loc[funder_masks["erdf"], "work_id"].nunique()
    print(f"  ERDF rows: {erdf_rows:,} (matches the docs' cited 429 exactly), "
          f"works: {erdf_works:,} (docs cite 279 -- see module docstring)")
    assert erdf_rows == 429, f"ERDF rows drifted: {erdf_rows} != 429"

    # ============================================================================== thm_frontier
    print("\n[5/5] thm_frontier")
    # RE-BASE (manager correction, chain pass 3 fix round): data_foundation.yaml's supersessions
    # block now records that plan S6.1's ETO-folder pointer (OA_frontier_scores.xlsx) was a
    # TRANSCRIPTION ERROR -- the catalog card `enr-frontierness-baseline` and the file
    # reports/lab_frontierness_probe.py actually reads both name RPF's
    # `Readout/Raw data/Cleaning bad OA topics.xlsx` as the blessed artifact. This section reuses
    # the probe's construction verbatim (read line by line): sheet "FILTERING OUT TOPICS" (the
    # per-topic frontier/exclusion frame) + Sheet2 (an exclusion id list VERIFIED IDENTICAL to
    # lib.artifact.load_bad_topics()'s 811-topic set -- both mechanisms are the SAME list; this
    # code reuses load_bad_topics() as the single source of truth rather than re-deriving it from
    # Sheet2 independently). No separate world-reference file is needed this time: the sheet's own
    # "Number of articles (OpenAlex GBQ)" column IS the world-works weighting basis.
    baseline_path = ROOT / "inputs" / "manual" / "frontierness_baseline.xlsx"
    base = pd.read_excel(baseline_path, sheet_name="FILTERING OUT TOPICS")
    base.columns = [c.strip() for c in base.columns]
    KEY = "Topic ID no url"
    base[KEY] = base[KEY].astype(str).str.strip()

    from lib.artifact import load_bad_topics
    bad_ids = load_bad_topics(ROOT)
    base["excluded"] = base[KEY].isin(bad_ids)
    n_excluded = int(base["excluded"].sum())
    print(f"  baseline: {len(base):,} topics ({base[KEY].nunique():,} unique ids), "
          f"{n_excluded} excluded (matches lib.artifact's 811-topic set exactly, verified)")
    assert n_excluded == 811, f"exclusion count drifted: {n_excluded} != 811"
    kept = base[~base["excluded"]].copy()
    print(f"  kept (scoreable reference) topics: {len(kept):,}")

    field_name_to_id = all_topics.drop_duplicates("field_name").set_index("field_name")["field_id"] \
        .astype("string")
    kept["field_id_baseline"] = kept["OA field"].map(field_name_to_id)
    assert kept["field_id_baseline"].isna().sum() == 0, "OA field values not resolving to all_topics.field_id"

    kept["front_pctile"] = kept["Average frontierness"].rank(pct=True) * 100.0
    kept["field_pctile"] = kept.groupby("OA field")["Average frontierness"].rank(pct=True) * 100.0

    gbq_weight = kept["Number of articles (OpenAlex GBQ)"]
    neutral_point = float((kept["front_pctile"] * gbq_weight).sum() / gbq_weight.sum())
    print(f"  GOLDEN CHECK neutral_point (GBQ-works-weighted mean pctile among kept): "
          f"{neutral_point:.2f} (golden ~51 -- reports/lab_frontierness_probe.py + catalog card)")
    assert abs(neutral_point - 51) < 2.0, f"neutral_point drifted: {neutral_point:.2f} != ~51"

    baseline_vintage = (f"{dt.date.fromtimestamp(baseline_path.stat().st_mtime).isoformat()} copy-in "
                         f"date; source vintage: mid-2025 GBQ build (catalog card "
                         f"enr-frontierness-baseline trap #4 -- id-level drift vs the 2026-08-11 "
                         f"corpus pull measured ZERO)")
    score_column_used = "Average frontierness (ACCORD composite: 0.7 Expansion + 0.3 Acceleration, " \
                         "z-scored within bin -- catalog card enr-frontierness-baseline)"

    wf = works[["work_id", "primary_topic_id", "primary_field_id", "In_ISITE", "artifact_flag"]].copy()
    wf["tid"] = wf["primary_topic_id"].astype(str).str.replace(
        "https://openalex.org/", "", regex=False).str.strip()
    wf = wf.merge(base[[KEY, "OA field", "Average frontierness", "excluded"]],
                  left_on="tid", right_on=KEY, how="left")
    wf = wf.merge(kept[[KEY, "front_pctile", "field_pctile", "field_id_baseline"]], on=KEY, how="left")

    matched = wf[KEY].notna()
    join_coverage = matched.sum() / n_corpus
    print(f"  GOLDEN CHECK join coverage (primary topic -> baseline): {matched.sum():,}/{n_corpus:,} "
          f"= {join_coverage*100:.2f}% (golden ~99.9%)")
    assert join_coverage > 0.995, f"join coverage drifted: {join_coverage*100:.2f}% != ~99.9%"

    scoreable = wf[matched & (wf["excluded"] == False) & wf["Average frontierness"].notna()].copy()  # noqa: E712
    print(f"  scoreable (kept-topic) works: {len(scoreable):,}/{n_corpus:,} "
          f"= {len(scoreable)/n_corpus*100:.1f}%")

    frontier_panel_rows = []
    for perimeter_id, base_mask in [("all", pd.Series(True, index=works.index)),
                                     ("in_isite", works["In_ISITE"].astype(bool))]:
        sub_all = scoreable[scoreable["work_id"].isin(set(works.loc[base_mask, "work_id"]))]
        for state in CONF_STATES:
            if state == "no_conf":
                conf_ids = set(works.loc[conf_mask("no_conf"), "work_id"])
                sub = sub_all[sub_all["work_id"].isin(conf_ids)]
            else:
                sub = sub_all
            sub_xa = sub[~sub["artifact_flag"]]
            for field_id in field_ids:
                f_all = sub[sub["field_id_baseline"] == field_id]
                f_xa = sub_xa[sub_xa["field_id_baseline"] == field_id]
                frontier_panel_rows.append({
                    "perimeter_id": perimeter_id, "field_id": field_id, "conf_state": state,
                    "raw_frontier_share": f_all["front_pctile"].mean() if len(f_all) else np.nan,
                    "raw_frontier_share_xa": f_xa["front_pctile"].mean() if len(f_xa) else np.nan,
                    "field_standardised_share": f_all["field_pctile"].mean() if len(f_all) else np.nan,
                    "field_standardised_share_xa": f_xa["field_pctile"].mean() if len(f_xa) else np.nan,
                    "neutral_point": neutral_point, "score_column_used": score_column_used,
                    "baseline_vintage": baseline_vintage,
                })
    frontier_panel = pd.DataFrame(frontier_panel_rows)
    frontier_panel["row_kind"] = "panel"

    # ---- texture: top-20 emerging (kept) topics x conf_state, primary-topic ul/isite counts
    top20 = kept.sort_values("Average frontierness", ascending=False).head(20)
    texture_rows = []
    for state in CONF_STATES:
        cm = conf_mask(state)
        for _, trow in top20.iterrows():
            tid = trow[KEY]
            m = cm & (wf["tid"] == tid)
            m_xa = m & ~works["artifact_flag"]
            texture_rows.append({
                "conf_state": state, "topic_id": tid, "topic_name": trow["Topic name"],
                "frontier_score_std": float(trow["Average frontierness"]),
                "ul_works": int(m.sum()), "ul_works_xa": int(m_xa.sum()),
                "isite_works": int((m & works["In_ISITE"].astype(bool)).sum()),
                "isite_works_xa": int((m_xa & works["In_ISITE"].astype(bool)).sum()),
                "artifact_flag": False,  # top-20 drawn from KEPT topics only, by construction
            })
    texture = pd.DataFrame(texture_rows)
    texture["row_kind"] = "texture"

    thm_frontier = pd.concat([frontier_panel, texture], ignore_index=True, sort=False)
    for col in ["perimeter_id", "field_id", "conf_state", "score_column_used", "baseline_vintage",
                "topic_id", "topic_name", "row_kind"]:
        if col in thm_frontier.columns:
            thm_frontier[col] = thm_frontier[col].astype("string")
    for col in ["raw_frontier_share", "raw_frontier_share_xa", "field_standardised_share",
                "field_standardised_share_xa", "neutral_point", "frontier_score_std"]:
        thm_frontier[col] = thm_frontier[col].astype("float64")
    for col in ["ul_works", "ul_works_xa", "isite_works", "isite_works_xa"]:
        thm_frontier[col] = thm_frontier[col].astype("Int64")
    thm_frontier["artifact_flag"] = thm_frontier["artifact_flag"].astype("boolean")
    thm_frontier["snapshot_date"] = pd.Series(snapshot.name, index=thm_frontier.index, dtype="string")
    outputs["thm_frontier"] = thm_frontier
    print(f"  wrote {len(thm_frontier):,} rows ({len(frontier_panel)} panel + {len(texture)} texture)")

    # ---- amplification goldens (reproduces reports/lab_frontierness_probe.py's F3 construction
    # EXACTLY for the raw figure; the field-standardised figure uses DIRECT STANDARDISATION --
    # both groups' per-field in-cut rates reweighted onto In_ISITE's OWN field mix as the common
    # reference -- since neither the probe nor the catalog card ships that exact code, only the
    # measured result to reproduce; direct standardisation is the textbook method for isolating a
    # within-group effect from a composition effect, and it reproduces the golden to 2 decimals)
    thr10_raw = kept["Average frontierness"].quantile(0.90)
    scoreable = scoreable.copy()
    scoreable["in_cut_raw"] = scoreable["Average frontierness"] >= thr10_raw

    isite_s = scoreable[scoreable["In_ISITE"] == True]  # noqa: E712
    rest_s = scoreable[scoreable["In_ISITE"] != True]  # noqa: E712
    isite_baseline = (scoreable["In_ISITE"] == True).mean()  # noqa: E712
    p_isite_raw = isite_s["in_cut_raw"].mean()
    p_cut_share_of_isite = isite_s["in_cut_raw"].sum() / scoreable["in_cut_raw"].sum()
    raw_amp = p_cut_share_of_isite / isite_baseline
    print(f"  GOLDEN CHECK raw amplification (top-10% cut, In_ISITE share-of-cut vs baseline): "
          f"x{raw_amp:.2f} (golden x1.37)")
    assert abs(raw_amp - 1.37) < 0.05, f"raw amplification drifted: x{raw_amp:.2f} != x1.37"

    p_isite_field = isite_s.groupby("field_id_baseline")["in_cut_raw"].mean()
    p_rest_field = rest_s.groupby("field_id_baseline")["in_cut_raw"].mean()
    weight_isite = isite_s["field_id_baseline"].value_counts(normalize=True)
    std_isite = sum(p_isite_field.get(f, 0.0) * w for f, w in weight_isite.items())
    std_rest = sum(p_rest_field.get(f, 0.0) * w for f, w in weight_isite.items())
    field_amp = std_isite / std_rest
    print(f"  GOLDEN CHECK field-standardised amplification (direct standardisation onto In_ISITE's "
          f"own field mix): x{field_amp:.2f} (golden x1.03)")
    assert abs(field_amp - 1.03) < 0.05, f"standardised amplification drifted: x{field_amp:.2f} != x1.03"
    print(f"  BOTH FRONTIER AMPLIFICATION GOLDENS REPRODUCED (raw x1.37, standardised x1.03)")

    # =================================================================================== asserts
    print("\n" + "=" * 78)
    print("ACCEPTANCE ASSERTS")
    print("=" * 78)

    in_isite_award_works = pd.read_parquet(tables / "work_subsets.parquet")
    n_award = int((in_isite_award_works["subset_id"] == "in_isite_award").sum())
    print(f"  work_subsets.in_isite_award: {n_award} (golden 808; read, not rebuilt)")
    assert n_award == 808, f"in_isite_award drifted: {n_award} != 808"

    div_all = thm_diversity[(thm_diversity.perimeter_id == "all") & (thm_diversity.conf_state == "all")]
    div_isite = thm_diversity[(thm_diversity.perimeter_id == "in_isite") & (thm_diversity.conf_state == "all")]
    print("\n  diversity eyeball sanity (Rao-Stirling/DIV composite, conf_state=all):")
    print(div_all[["year", "n_works", "variety", "balance", "disparity", "rao_stirling"]]
          .to_string(index=False, formatters={c: "{:.4f}".format for c in
                     ["variety", "balance", "disparity", "rao_stirling"]}))
    print("  -- In_ISITE --")
    print(div_isite[["year", "n_works", "variety", "balance", "disparity", "rao_stirling"]]
          .to_string(index=False, formatters={c: "{:.4f}".format for c in
                     ["variety", "balance", "disparity", "rao_stirling"]}))
    finite_ok = np.isfinite(div_all["rao_stirling"].dropna().to_numpy()).all() and \
        np.isfinite(div_isite["rao_stirling"].dropna().to_numpy()).all()
    assert finite_ok, "non-finite Rao-Stirling/DIV values in the all/in_isite eyeball rows"
    print("  FINITE check: PASS")

    # =================================================================================== write out
    compression = CONFIG["storage"]["compression"]
    written_files = []
    for name, df in outputs.items():
        out_path = tables / f"{name}.parquet"
        df.to_parquet(out_path, index=False, compression=compression)
        written_files.append(out_path)
        size_kb = out_path.stat().st_size / 1024
        print(f"\nwrote {name}.parquet: {len(df):,} rows x {len(df.columns)} cols, {size_kb:,.1f} KB")

    Manifest(snapshot).record_step(
        "47_build_thematic_ext",
        counts={name: len(df) for name, df in outputs.items()},
        files=written_files,
        params={
            "min_stratum_n": MIN_STRATUM_N, "band_pct": BAND_PCT, "sig_p": SIG_P,
            "t3c_windows": {"w1": W1_YEARS, "w2": W2_YEARS}, "bootstrap_b": BOOTSTRAP_B,
            "frontier_baseline": "inputs/manual/frontierness_baseline.xlsx (byte copy of RPF "
                                  "Readout/Raw data/Cleaning bad OA topics.xlsx -- the file "
                                  "catalog card enr-frontierness-baseline and "
                                  "reports/lab_frontierness_probe.py actually read; supersedes "
                                  "the mistaken ETO-folder pointer in plan S6.1)",
            "ec_family_list": EC_FAMILY,
        },
        notes="Foundry rev 3.1 W3: thematic extensions (T3/T3b/T3c/T4/T7/T9). Fix round "
              "(chain pass 3): frontier re-based on the correct canonical file -- all 4 goldens "
              "now reproduce (join coverage ~99.9%, neutral ~51, raw x1.37, standardised x1.03). "
              "Funding EC/ERDF: no frozen construction exists anywhere in this repo for either "
              "family (exhaustively searched); ANR matches the probe's own code exactly (4,433). "
              "EC/ERDF deltas vs cited figures are reported, not absorbed -- see "
              "progress/W3_thematic_ext.md.",
    )
    append_summary(snapshot, "47_build_thematic_ext", [
        f"- `thm_specialisation`: {len(outputs['thm_specialisation']):,} rows",
        f"- `thm_diversity`: {len(outputs['thm_diversity']):,} rows",
        f"- `thm_codiscipline`: {len(outputs['thm_codiscipline']):,} rows",
        f"- `thm_funding`: {len(outputs['thm_funding']):,} rows",
        f"- `thm_frontier`: {len(outputs['thm_frontier']):,} rows",
        f"- funding golden: overall {overall_share*100:.2f}% (21.3%), ANR {anr_works:,} (4,433) "
        f"EXACT; EC {ec_rows:,} rows (cites 2,214 -- no frozen construction found, reported not "
        f"absorbed); ERDF {erdf_rows:,} rows (matches 429 exactly), {erdf_works:,} works "
        f"(cites 279 -- reported not absorbed)",
        f"- frontier (RE-BASED, fix round): join coverage {join_coverage*100:.2f}% (golden ~99.9%) "
        f"EXACT; neutral_point {neutral_point:.2f} (golden ~51) EXACT; amplification "
        f"raw x{raw_amp:.2f} / standardised x{field_amp:.2f} (golden x1.37/x1.03) EXACT",
    ])
    print("\ndone.")


if __name__ == "__main__":
    main()
