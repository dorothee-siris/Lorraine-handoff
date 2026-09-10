"""tests/test_pass7_data.py -- Tier-A evals for S-DAT's pass-7 tables (P6 frontier components,
P7 D40 "publications phares").

Every golden here is recomputed INDEPENDENTLY from snapshot tables (works_master,
corpus_authorships, ul_partners_base) or by cross-checking two INDEPENDENTLY BUILT deployed tables
against each other -- never by importing or calling the pipeline builders. Same pattern as
tests/test_pass6_data.py. Per P14 (vacuity rule): every check here is followed, in the SAME test,
by a deliberate mutation on a copy of the data that makes the identical comparison FAIL -- a pin
that cannot fail is theater.

Run:  .venv-pinned\\Scripts\\python -m pytest tests/test_pass7_data.py -v
"""

from __future__ import annotations

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
DEPLOYED = ROOT / "Streamlit" / "data"
BASELINE = ROOT / "reports" / "pass7_data_baseline"

# the 3 tier-A hand-verify partners (P7 D40, BUILD_PLAN.md P7/S-DAT block): CNRS, CHRU Nancy, and
# the smallest partner clearing the >=10 co-works floor -- found by probing ptn_summary
# (conf_state='all', subset_id='all'), recorded here so the test is not order-dependent on a
# re-probe: I4387152967 "UMR QualiSud", co_works_full=10 (2026-08-11 snapshot).
CNRS = "I1294671590"
CHRU_NANCY = "I4210100260"
SMALLEST_GE10 = "I4387152967"
GOLDEN_PARTNERS = [CNRS, CHRU_NANCY, SMALLEST_GE10]


def table(name: str, base: Path = TABLES) -> pd.DataFrame:
    path = base / f"{name}.parquet"
    if not path.exists():
        pytest.skip(f"{name}.parquet not found at {path}")
    return pd.read_parquet(path)


# =================================================================================================
# (a) golden n_phares -- 3 partners, pair grain AND top-3 fields, EXACT vs ptn_summary/ptn_fields
# =================================================================================================

@pytest.fixture(scope="module")
def phare_works() -> pd.DataFrame:
    """work_id -> phare (bool, never null): independently derived from works_master's OWN
    PPtop10_FR + indicator_status -- NOT from ptn_works.pptop10_fr (a built/derived column)."""
    wm = pd.read_parquet(TABLES / "works_master.parquet",
                         columns=["work_id", "PPtop10_FR", "indicator_status", "primary_field_id"])
    wm["phare"] = (wm["indicator_status"] == "computed") & (wm["PPtop10_FR"] == True)  # noqa: E712
    return wm.set_index("work_id")


@pytest.fixture(scope="module")
def authorships() -> pd.DataFrame:
    return pd.read_parquet(TABLES / "corpus_authorships.parquet", columns=["work_id", "institution_id"])


def _recompute_n_phares(authorships: pd.DataFrame, phare_works: pd.DataFrame, partner_id: str,
                        field_id: str | None = None) -> int:
    work_ids = set(authorships.loc[authorships["institution_id"] == partner_id, "work_id"])
    sub = phare_works.loc[phare_works.index.isin(work_ids)]
    if field_id is not None:
        sub = sub[sub["primary_field_id"] == field_id]
    return int(sub["phare"].sum())


def test_golden_n_phares_three_partners_pair_and_top3_fields(phare_works, authorships):
    ptn_summary = table("ptn_summary")
    ptn_fields = table("ptn_fields")
    summary_all = ptn_summary[(ptn_summary["conf_state"] == "all") & (ptn_summary["subset_id"] == "all")]
    fields_all = ptn_fields[(ptn_fields["conf_state"] == "all") & (ptn_fields["node_level"] == "field")]

    for partner_id in GOLDEN_PARTNERS:
        # pre-check: my independent work-set construction must itself reproduce co_works_full --
        # a merge/alias mismatch would silently under/over-count and invalidate everything below.
        row = summary_all[summary_all["partner_id"] == partner_id]
        assert len(row) == 1, f"{partner_id}: expected exactly 1 ptn_summary (all,all) row"
        golden_co_works = int(row.iloc[0]["co_works_full"])
        recomputed_co_works = len(set(authorships.loc[authorships["institution_id"] == partner_id, "work_id"]))
        assert recomputed_co_works == golden_co_works, (
            f"{partner_id}: independent co_works_full recompute {recomputed_co_works} != "
            f"ptn_summary {golden_co_works} -- work-set construction is not reproducing the "
            f"builder's own universe (merge/alias?), the n_phares check below would be meaningless"
        )

        # pair grain
        built_pair = int(row.iloc[0]["n_phares"])
        golden_pair = _recompute_n_phares(authorships, phare_works, partner_id)
        assert built_pair == golden_pair, (
            f"{partner_id}: ptn_summary.n_phares {built_pair} != golden recompute {golden_pair}")

        # top-3 fields by co_works (which 3 fields to check is READ off the built table -- a
        # selection, not a value under test; the VALUE compared is independently recomputed)
        partner_fields = fields_all[fields_all["partner_id"] == partner_id].sort_values(
            "co_works", ascending=False)
        top3 = partner_fields.head(3)
        assert len(top3) >= 1, f"{partner_id}: no field rows found in ptn_fields"
        for _, frow in top3.iterrows():
            field_id = frow["node_id"]
            built_field = int(frow["n_phares"])
            golden_field = _recompute_n_phares(authorships, phare_works, partner_id, field_id)
            assert built_field == golden_field, (
                f"{partner_id} field {field_id}: ptn_fields.n_phares {built_field} != golden "
                f"recompute {golden_field}"
            )

    # ---- vacuity (P14): mutate the golden phare_works copy (flip one True->False among CNRS's
    # own phare works) and prove the SAME comparison now fails.
    cnrs_ids = set(authorships.loc[authorships["institution_id"] == CNRS, "work_id"])
    mutated = phare_works.copy()
    flip_candidates = mutated.index[mutated.index.isin(cnrs_ids) & mutated["phare"]]
    assert len(flip_candidates) > 0, "CNRS must have >=1 phare work for this mutation to be meaningful"
    mutated.loc[flip_candidates[0], "phare"] = False
    mutated_golden = _recompute_n_phares(authorships, mutated, CNRS)
    real_built = int(summary_all.loc[summary_all["partner_id"] == CNRS, "n_phares"].iloc[0])
    assert mutated_golden != real_built, "mutation did not change the recomputed value -- vacuous check"


# =================================================================================================
# (b) Sigma over ptn_fields field-rows == ptn_summary pair value, ALL partners, conf_state='all'
# =================================================================================================

def test_n_phares_sum_over_fields_equals_pair_value_all_partners():
    ptn_summary = table("ptn_summary")
    ptn_fields = table("ptn_fields")
    summary_all = ptn_summary[(ptn_summary["conf_state"] == "all") & (ptn_summary["subset_id"] == "all")]
    fields_all = ptn_fields[(ptn_fields["conf_state"] == "all") & (ptn_fields["node_level"] == "field")]

    field_sum = fields_all.groupby("partner_id")["n_phares"].sum()
    field_sum_xa = fields_all.groupby("partner_id")["n_phares_xa"].sum()
    pair = summary_all.set_index("partner_id")["n_phares"]
    pair_xa = summary_all.set_index("partner_id")["n_phares_xa"]

    cmp = pd.DataFrame({
        "field_sum": field_sum.reindex(pair.index).fillna(0).astype(int),
        "pair": pair,
        "field_sum_xa": field_sum_xa.reindex(pair_xa.index).fillna(0).astype(int),
        "pair_xa": pair_xa,
    })
    assert len(cmp) > 2000, f"expected thousands of partners, got {len(cmp)} -- wrong slice?"
    bad = cmp[(cmp["field_sum"] != cmp["pair"]) | (cmp["field_sum_xa"] != cmp["pair_xa"])]
    assert bad.empty, f"{len(bad)} partner(s) fail Sigma(field n_phares) == pair n_phares:\n{bad.head()}"

    # vacuity: corrupt one partner's pair value on a copy and prove the check now fails
    mutated_pair = pair.copy()
    some_id = mutated_pair.index[0]
    mutated_pair.loc[some_id] = mutated_pair.loc[some_id] + 1
    assert (field_sum.reindex(mutated_pair.index).fillna(0).astype(int) != mutated_pair).any(), (
        "mutation did not create a mismatch -- vacuous check")


# =================================================================================================
# (c) pptop10_fr NULL iff indicator not computed -- sample 1,000 ptn_works rows, EXACT
# =================================================================================================

def test_pptop10_fr_null_iff_indicator_not_computed():
    ptn_works = table("ptn_works")
    wm = pd.read_parquet(TABLES / "works_master.parquet", columns=["work_id", "indicator_status"])
    sample = ptn_works.sample(n=min(1000, len(ptn_works)), random_state=7)[["work_id", "pptop10_fr", "pptop1_fr"]]
    merged = sample.merge(wm, on="work_id", how="left")
    assert merged["indicator_status"].notna().all(), "sampled work_id(s) missing from works_master"

    not_computed = merged["indicator_status"] != "computed"
    assert merged.loc[not_computed, "pptop10_fr"].isna().all(), (
        "pptop10_fr must be NULL wherever indicator_status != 'computed'")
    assert merged.loc[not_computed, "pptop1_fr"].isna().all(), (
        "pptop1_fr must be NULL wherever indicator_status != 'computed'")
    assert merged.loc[~not_computed, "pptop10_fr"].isin([True, False]).all(), (
        "pptop10_fr must be a real True/False wherever indicator_status == 'computed'")
    n_not_computed = int(not_computed.sum())
    assert n_not_computed > 0, "sample contains no not-computed work -- re-seed, this proves nothing"

    # vacuity: flip a NULL to True on a copy where indicator_status != computed -- must now fail
    mutated = merged.copy()
    bad_idx = mutated.index[not_computed][0]
    mutated.loc[bad_idx, "pptop10_fr"] = True
    still_null = mutated.loc[mutated["indicator_status"] != "computed", "pptop10_fr"].isna().all()
    assert not still_null, "mutation did not break the invariant -- vacuous check"


# =================================================================================================
# (d) dim_frontier_components -- 25,942 rows, 3,706 topics, 7 bins, 1 is_latest/topic, describe()
# =================================================================================================

def test_dim_frontier_components_shape_and_describe():
    comp = table("dim_frontier_components")
    assert len(comp) == 25942, f"row count {len(comp):,} != 25,942"
    n_topics = comp["topic_id"].nunique()
    assert n_topics == 3706, f"topic count {n_topics:,} != 3,706"
    n_bins = comp["bin_label"].nunique()
    assert n_bins == 7, f"bin count {n_bins} != 7"

    n_latest = comp.groupby("topic_id")["is_latest"].sum()
    assert (n_latest == 1).all(), "every topic must have EXACTLY one is_latest=True row"

    latest = comp[comp["is_latest"]]
    exp_mean, exp_std = float(latest["expansion"].mean()), float(latest["expansion"].std())
    acc_mean, acc_std = float(latest["acceleration"].mean()), float(latest["acceleration"].std())
    assert abs(exp_mean) < 0.001, f"latest expansion mean {exp_mean} not ~0"
    assert abs(acc_mean) < 0.001, f"latest acceleration mean {acc_mean} not ~0"
    assert abs(exp_std - 0.674) < 0.005, f"latest expansion std {exp_std} != 0.674 +/- 0.005"
    assert abs(acc_std - 0.841) < 0.005, f"latest acceleration std {acc_std} != 0.841 +/- 0.005"

    corr = np.corrcoef(0.7 * comp["expansion"] + 0.3 * comp["acceleration"], comp["frontier"])[0, 1]
    assert corr > 0.999, f"composite correlation {corr:.6f} <= 0.999"

    # vacuity: on a copy, duplicate one topic's latest row into a second bin -- must break the
    # "exactly one is_latest per topic" invariant.
    mutated = comp.copy()
    one_latest_idx = mutated.index[mutated["is_latest"]][0]
    dup_row = mutated.loc[[one_latest_idx]].copy()
    dup_row["bin_label"] = "2004-06"  # same topic, now is_latest=True on TWO bins
    mutated = pd.concat([mutated, dup_row], ignore_index=True)
    n_latest_mutated = mutated.groupby("topic_id")["is_latest"].sum()
    assert not (n_latest_mutated == 1).all(), "mutation did not break the invariant -- vacuous check"


# =================================================================================================
# (e) pre-existing columns of the 4 changed tables == their baseline (pre-P7) copies
# =================================================================================================

CHANGED_TABLES = {
    "ptn_works": ["partner_id", "work_id"],
    "ptn_fields": ["partner_id", "node_level", "node_id", "conf_state"],
    "ptn_topics": ["partner_id", "topic_id", "year", "conf_state"],
    "ptn_summary": ["partner_id", "conf_state", "subset_id"],
}


@pytest.mark.parametrize("name,keys", list(CHANGED_TABLES.items()))
def test_pre_existing_columns_unchanged_vs_baseline(name, keys):
    baseline_path = BASELINE / f"{name}.parquet"
    if not baseline_path.exists():
        pytest.skip(f"no baseline copy at {baseline_path}")
    old = pd.read_parquet(baseline_path)
    new = table(name, base=DEPLOYED)
    shared_cols = [c for c in old.columns if c in new.columns]
    # ptn_topics' baseline predates the conf_state grain extension in some earlier histories, but
    # THIS pass's baseline (taken fresh, deliverable 0) already has conf_state -- keys as declared.
    old_s = old[shared_cols].sort_values(keys).reset_index(drop=True)
    new_s = new[shared_cols].sort_values(keys).reset_index(drop=True)
    for col in ("partner_id", "topic_id", "node_id", "subfield_id"):
        if col in old_s.columns:
            old_s[col] = old_s[col].astype(str)
            new_s[col] = new_s[col].astype(str)
    pd.testing.assert_frame_equal(old_s, new_s, check_dtype=False, check_categorical=False)

    # vacuity: corrupt one shared value on a copy, prove assert_frame_equal now raises
    mutated = new_s.copy()
    numeric_cols = [c for c in shared_cols if c not in keys and pd.api.types.is_numeric_dtype(new_s[c])
                    and str(new_s[c].dtype) not in ("bool", "boolean")]
    assert numeric_cols, f"{name}: no numeric shared column found to mutate"
    mcol = numeric_cols[0]
    mutated.loc[0, mcol] = (mutated.loc[0, mcol] if pd.notna(mutated.loc[0, mcol]) else 0) + 999
    with pytest.raises(AssertionError):
        pd.testing.assert_frame_equal(old_s, mutated, check_dtype=False, check_categorical=False)


# =================================================================================================
# (f) blob round-trip -- 42b subfield blobs of ul_partners_base.parquet, 10 partners
# =================================================================================================

def test_subfield_blob_round_trip_ten_partners():
    base = pd.read_parquet(TABLES / "ul_partners_base.parquet")
    subfield_cols = [c for c in base.columns if c.startswith('Pubs per subfield within "')]
    assert subfield_cols, "no 'Pubs per subfield within' blob columns found in ul_partners_base"
    col = subfield_cols[0]
    populated = base[base[col].notna()]
    assert len(populated) >= 10, f"fewer than 10 partners have a populated {col!r} blob"
    sample = populated.head(10)

    for _, row in sample.iterrows():
        blob = str(row[col])
        parsed = [v.strip() for v in blob.split(" | ")]
        assert all(v.lstrip("-").isdigit() for v in parsed), (
            f"partner {row['Partner ID']}: blob has a non-integer field: {blob[:120]}")
        reserialised = " | ".join(parsed)
        assert reserialised == blob, (
            f"partner {row['Partner ID']}: round-trip mismatch: {blob[:120]!r} != {reserialised[:120]!r}"
        )

    # vacuity: drop one field from the parse before re-serialising -- must now mismatch
    blob0 = str(sample.iloc[0][col])
    parsed0 = blob0.split(" | ")
    assert len(parsed0) > 1, "sample blob has <=1 field, mutation would be meaningless"
    mutated_reserialised = " | ".join(parsed0[:-1])  # drop the last field
    assert mutated_reserialised != blob0, "mutation did not change the blob -- vacuous check"
