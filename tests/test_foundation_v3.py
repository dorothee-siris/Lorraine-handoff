"""tests/test_foundation_v3.py -- E1b eval-layer extension (chain pass 3, Assembly Line).

Reads the DEPLOYED `Streamlit/data/*.parquet` tables ONLY -- never the raw snapshot `tables/`, never
a builder re-run. Purpose (per the E1b dispatch): `pipeline/46_build_partner_views.py` /
`47_build_thematic_ext.py` / `45b_build_author_views.py` (streams W2/W3/W4) already assert every
number below at BUILD time, against the snapshot they just wrote. Those asserts protect the FIRST
build. They say nothing about the SECOND, or about tomorrow's `pipeline/60_deploy.py` re-run, or
about a rollback to an older snapshot. This file re-asserts the same canonical facts against
whatever actually sits in `Streamlit/data/` right now -- so a build-time PASS that regresses at
deploy time, or silently drifts on a re-run, is caught here instead of by a client screenshot.

Authority: docs/foundry/data_foundation.yaml rev 3.1 (canonical_counts + every table's own
`invariants:`/`artifact_invariant_columns:`/`artifact_exempt*:` blocks) + docs/data_contract.yaml
(deployed schema, `keys:`, `columns:`) + progress/{W2_partner_views,W3_thematic_ext,W4_author_views,
E1a_integration,P1_perimeter_pages,P2_partner_pages,P3_thematic_ext}.md. Every number below was
independently re-probed against the DEPLOYED parquet before being pinned here (never copied from a
report without checking) -- see progress/E1b_evals.md for the one place a number in this file
deliberately does NOT match a dispatch-text digit (the no_conf >=50 momentum floor).

Run:  python -m pytest tests/test_foundation_v3.py -q
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "Streamlit" / "data"
SNAPSHOT_DATE = "2026-08-11"

IMPACT_COLUMN_REGEX = re.compile(r"fwci|pptop|impact|citation", re.IGNORECASE)


# =================================================================================================
# fixtures -- read each deployed parquet at most ONCE per test module, via a tiny cache
# =================================================================================================

class _TableCache:
    """Module-scoped cache: `tables("ptn_summary")` reads Streamlit/data/ptn_summary.parquet the
    FIRST time any test in this module asks for it, then serves every subsequent call (same name,
    same columns) from memory. Keeps the suite fast without every test hand-rolling its own read."""

    def __init__(self) -> None:
        self._cache: dict[tuple, pd.DataFrame] = {}

    def __call__(self, name: str, columns: list[str] | None = None) -> pd.DataFrame:
        key = (name, tuple(columns) if columns else None)
        if key not in self._cache:
            path = DATA_DIR / f"{name}.parquet"
            if not path.is_file():
                pytest.skip(f"Streamlit/data/{name}.parquet not deployed -- run pipeline/60_deploy.py")
            self._cache[key] = pd.read_parquet(path, columns=columns)
        return self._cache[key]


@pytest.fixture(scope="module")
def tables() -> _TableCache:
    return _TableCache()


def _parquet_file(name: str) -> pq.ParquetFile:
    path = DATA_DIR / f"{name}.parquet"
    if not path.is_file():
        pytest.skip(f"Streamlit/data/{name}.parquet not deployed -- run pipeline/60_deploy.py")
    return pq.ParquetFile(path)


def _inwin(mom_count_arrow: str) -> int:
    """mom_count_arrow is 'c1->c2' (e.g. '12->34'); the >=50 momentum floor is on c1+c2, the
    engine's own in-window volume -- NOT co_works_full, a different quantity (P2's own note,
    progress/P2_partner_pages.md)."""
    a, b = str(mom_count_arrow).split("->")
    return int(a) + int(b)


# =================================================================================================
# canonical_counts (data_foundation.yaml rev 3.1)
# =================================================================================================

def test_in_isite_and_in_isite_award_counts(tables):
    work_subsets = tables("work_subsets")
    counts = work_subsets["subset_id"].value_counts()
    assert int(counts.get("in_isite", 0)) == 1839
    assert int(counts.get("in_isite_award", 0)) == 808

    subset_works = tables("subset_works")
    sw_counts = subset_works["subset_id"].value_counts()
    assert int(sw_counts.get("in_isite", 0)) == 1839
    assert int(sw_counts.get("in_isite_award", 0)) == 808
    assert bool((subset_works.loc[subset_works["subset_id"] == "in_isite", "in_isite"] == True).all())  # noqa: E712
    award_delta = subset_works[(subset_works["subset_id"] == "in_isite_award") & (~subset_works["in_isite"])]
    assert len(award_delta) == 32, f"award-only delta (in_isite_award AND NOT in_isite) expected 32, got {len(award_delta)}"


def test_artifact_topics_and_primary_flag_counts(tables):
    dat = tables("dim_artifact_topics")
    assert len(dat) == 811, f"dim_artifact_topics rows: expected 811, got {len(dat)}"

    facts = tables("dim_corpus_facts")
    all_row = facts.set_index("conf_state").loc["all"]
    primary_flagged = int(all_row["corpus_works"]) - int(all_row["corpus_works_xa"])
    assert primary_flagged == 4106, (
        f"primary artifact-flagged works (corpus_works - corpus_works_xa, 'all' row): "
        f"{primary_flagged}, expected 4,106"
    )


def test_ptn_topics_all_slice_canonical_counts(tables):
    pt = tables("ptn_topics")
    all_slice = pt[pt["conf_state"] == "all"]
    assert len(all_slice) == 224396, f"ptn_topics 'all' rows: {len(all_slice)}, expected 224,396"

    cells = all_slice.drop_duplicates(["partner_id", "topic_id"])
    assert len(cells) == 156164, f"ptn_topics 'all' distinct cells: {len(cells)}, expected 156,164"

    cell_totals = all_slice.groupby(["partner_id", "topic_id"], observed=True)["co_works"].sum()
    assert int((cell_totals >= 3).sum()) == 25460
    assert int((cell_totals >= 20).sum()) == 1293


def test_ptn_works_canonical_count(tables):
    pw = tables("ptn_works")
    assert len(pw) == 116345, f"ptn_works rows: {len(pw)}, expected 116,345"


def test_partner_floors(tables):
    ptn_summary = tables("ptn_summary")
    base = ptn_summary[(ptn_summary["conf_state"] == "all") & (ptn_summary["subset_id"] == "all")]
    assert int((base["co_works_full"] >= 10).sum()) == 2309
    assert int((base["co_works_full"] >= 20).sum()) == 1279
    assert int((base["co_works_full"] >= 50).sum()) == 447


def test_null_country_and_countries_ge10(tables):
    ptn_summary = tables("ptn_summary")
    base = ptn_summary[(ptn_summary["conf_state"] == "all") & (ptn_summary["subset_id"] == "all")]
    assert int(base["country_code"].isna().sum()) == 346, (
        "null-country partner count: arbitrated at 346 (W2 FIX ROUND #4 -- the raw-materials "
        "342-vs-347-vs-346 story is in progress/W2_partner_views.md; 346 is the parquet-native "
        "construction, 347 traced to an ISO 'NA' = Namibia CSV-null-sniffing artifact upstream)"
    )

    geo_countries = tables("geo_countries")
    gc = geo_countries[
        (geo_countries["conf_state"] == "all") & (geo_countries["subset_id"] == "all")
        & (~geo_countries["unknown_bucket_flag"])
    ]
    totals = gc.groupby("country_code", observed=True)["co_works"].sum()
    assert int((totals >= 10).sum()) == 120, (
        f"countries with >=10 co-works (unknown bucket excluded): {int((totals >= 10).sum())}, expected 120"
    )


def test_aut_impact_drill_floors(tables):
    aid = tables("aut_impact_drill")
    counts = aid["conf_state"].value_counts()
    assert int(counts.get("all", 0)) == 480
    assert int(counts.get("no_conf", 0)) == 480
    assert aid["author_id"].nunique() == 480


def test_consortium_weights_golden(tables):
    cw = tables("consortium_weights")
    isite_all = cw[(cw["scope"] == "isite") & (cw["conf_state"] == "all")].set_index("member")
    targets = {
        "CNRS": 58.7, "INRAE": 21.5, "AgroParisTech": 9.9, "Inserm": 9.0,
        "CHRU Nancy": 2.6, "Georgia Tech": 1.1,
    }
    for member, pct in targets.items():
        got = round(float(isite_all.loc[member, "share_of_scope"]) * 100, 1)
        assert got == pct, f"consortium_weights {member} ISITE share: {got}, expected {pct}"
    inria_ext = round(float(isite_all.loc["Inria", "share_of_scope"]) * 100, 1)
    assert inria_ext == 0.1, f"Inria external ISITE share: {inria_ext}, expected 0.1"


def test_freiberg_union_count(tables):
    gg = tables("geo_groups")
    frei = gg[(gg["member_id"] == "Freiberg") & (gg["conf_state"] == "all")]
    assert frei["co_works_distinct"].nunique() == 1
    assert int(frei["co_works_distinct"].iloc[0]) == 15, (
        "Freiberg is a UNION of 2 ids (15), not the per-id row-sum (16) -- data_foundation.yaml "
        "supersessions block"
    )


# =================================================================================================
# momentum
# =================================================================================================

MOMENTUM_DISPLAY = {
    "all": {"total": 680, "up": 105, "down": 51, "stable": 276, "ns": 248},
    "no_conf": {"total": 562, "up": 90, "down": 44, "stable": 211, "ns": 217},
}

# >=50-floor sub-counts. NOTE (verified live, not copied): the dispatch text's parenthetical repeats
# "213 -> 46/16/102/49" for BOTH conf_state rows; the 'all' row is right, but the no_conf row's own
# figure -- both in progress/W2_partner_views.md's "Display counts (phantom excluded)" section AND
# independently re-derived here straight from the deployed ptn_summary.mom_count_arrow column -- is
# 172 -> 36/15/85/36, not 213 -> 46/16/102/49 (that would be identical to the 'all' row, which the
# no_conf corpus, being smaller, cannot reproduce). Pinned to the reproducible number, per the "probe,
# don't assume" rule; see progress/E1b_evals.md for the same note.
MOMENTUM_GE50 = {
    "all": {"total": 213, "up": 46, "down": 16, "stable": 102, "ns": 49},
    "no_conf": {"total": 172, "up": 36, "down": 15, "stable": 85, "ns": 36},
}


def test_ptn_summary_display_counts_match_mom_facts(tables):
    ptn_summary = tables("ptn_summary")
    ptn_mom_facts = tables("ptn_mom_facts").set_index("conf_state")

    for conf_state, expected in MOMENTUM_DISPLAY.items():
        base = ptn_summary[(ptn_summary["conf_state"] == conf_state) & (ptn_summary["subset_id"] == "all")]
        classified = base[base["mom_class"].notna()]
        assert len(classified) == expected["total"] == int(ptn_mom_facts.loc[conf_state, "display_eligible_n"]), (
            f"{conf_state}: ptn_summary classified rows {len(classified)} vs expected "
            f"{expected['total']} vs mom_facts.display_eligible_n "
            f"{int(ptn_mom_facts.loc[conf_state, 'display_eligible_n'])}"
        )
        got_classes = classified["mom_class"].value_counts().to_dict()
        for cls in ("up", "down", "stable", "ns"):
            assert int(got_classes.get(cls, 0)) == expected[cls], (
                f"{conf_state}/{cls}: got {got_classes.get(cls, 0)}, expected {expected[cls]}"
            )


def test_momentum_ge50_floor_breakdown(tables):
    ptn_summary = tables("ptn_summary")
    for conf_state, expected in MOMENTUM_GE50.items():
        base = ptn_summary[(ptn_summary["conf_state"] == conf_state) & (ptn_summary["subset_id"] == "all")]
        classified = base[base["mom_class"].notna()].copy()
        classified["inwin"] = classified["mom_count_arrow"].map(_inwin)
        big = classified[classified["inwin"] >= 50]
        assert len(big) == expected["total"], f"{conf_state} >=50 total: {len(big)}, expected {expected['total']}"
        got_classes = big["mom_class"].value_counts().to_dict()
        for cls in ("up", "down", "stable", "ns"):
            assert int(got_classes.get(cls, 0)) == expected[cls], (
                f"{conf_state}/{cls} (>=50 floor): got {got_classes.get(cls, 0)}, expected {expected[cls]}"
            )


def test_mom_facts_eligible_minus_display_eligible_is_one(tables):
    ptn_mom_facts = tables("ptn_mom_facts")
    diff = ptn_mom_facts["eligible_n"] - ptn_mom_facts["display_eligible_n"]
    assert (diff == 1).all(), (
        f"eligible_n - display_eligible_n must be exactly 1 on every row (the named phantom "
        f"pseudo-partner), got {diff.tolist()}"
    )


# =================================================================================================
# structural
# =================================================================================================

def test_aut_tables_carry_no_impact_column(tables):
    aut_public = tables("aut_public")
    aut_works = tables("aut_works")
    for name, df in (("aut_public", aut_public), ("aut_works", aut_works)):
        hits = [c for c in df.columns if IMPACT_COLUMN_REGEX.search(c)]
        assert not hits, f"{name}: found impact-shaped column(s) {hits} -- structural safeguard 1 breach"


def test_share_p_and_baseline_partner_share_populated_state(tables):
    """42b ran 2026-08-17 (pass-4 G3, snapshot 2026-08-11): pins the POPULATED state, replacing the
    pre-42b all-NULL pin. Challenge memo #8's rule -- share_p/baseline_partner_share populate ONLY
    on the (conf_state='all'[, subset_id='all']) rows, since 42b pulled a single all-types,
    all-corpus denominator per partner -- is asserted both ways: populated where it should be,
    NULL everywhere else. Never 0 (D53): a populated value is always in (0, 1]."""
    ptn_summary = tables("ptn_summary")
    is_all_all = (ptn_summary["conf_state"] == "all") & (ptn_summary["subset_id"] == "all")
    aa = ptn_summary[is_all_all]
    not_aa = ptn_summary[~is_all_all]

    # (a) share_p non-null EXACTLY on (all,all) rows whose partner was in the 42b pulled set
    n_populated = int(aa["share_p"].notna().sum())
    assert n_populated == 3613, (
        f"ptn_summary share_p populated rows (conf_state='all', subset_id='all'): {n_populated}, "
        f"expected 3,613 (of {len(aa):,} total (all,all) partners)"
    )

    # (b) NULL on every no_conf/in_isite row -- and NULL on the (all,all) rows outside (a)
    for col in ("share_p", "partner_total_windowed", "share_p_capped_flag"):
        assert not_aa[col].isna().all(), f"{col} must be NULL on every no_conf/in_isite row"

    # (c) 0 < share_p <= 1 wherever non-null; share_p_capped_flag True only where the pre-cap ratio
    # exceeded 1 (measured: 0 capped this pull -- snapshot and live pull landed 6 days apart with no
    # detected drift on any of the 3,613 partners; the invariant still holds vacuously)
    populated = aa["share_p"].dropna()
    assert (populated > 0).all() and (populated <= 1.0).all(), (
        "share_p must be in (0, 1] wherever non-null -- NEVER 0 (D53)"
    )
    n_capped = int(aa["share_p_capped_flag"].fillna(False).sum())
    assert n_capped == 0, f"share_p_capped_flag True count: {n_capped}, expected 0 (measured this pull)"
    capped_rows = aa[aa["share_p_capped_flag"].fillna(False)]
    assert (capped_rows["share_p"] == 1.0).all(), "every capped row must carry share_p == 1.0 exactly"

    # (e) the 3 merged canonical partners (challenge memo #9: successor_merges.csv status==ok) have
    # non-null share_p, sourced from the merged-union denominator (ul_partners_base_merged.parquet)
    merged_canonical_ids = ["I4210088668", "I198244214", "I4387152675"]  # INRAE, Clermont Auvergne, RPTU
    merged_rows = aa[aa["partner_id"].isin(merged_canonical_ids)]
    assert len(merged_rows) == 3, f"expected the 3 merged canonical partners in ptn_summary, found {len(merged_rows)}"
    assert merged_rows["share_p"].notna().all(), (
        f"merged canonical partners must have non-null share_p: "
        f"{merged_rows.loc[merged_rows['share_p'].isna(), 'partner_id'].tolist()}"
    )

    # (d) ptn_fields.baseline_partner_share: non-null count pinned, never 0 where non-null; NULL on
    # every no_conf cell (same single-denominator rule, applied symmetrically -- lens #8)
    ptn_fields = tables("ptn_fields")
    bps_all = ptn_fields.loc[ptn_fields["conf_state"] == "all", "baseline_partner_share"]
    bps_noconf = ptn_fields.loc[ptn_fields["conf_state"] == "no_conf", "baseline_partner_share"]
    n_bps_populated = int(bps_all.notna().sum())
    assert n_bps_populated == 27223, (
        f"ptn_fields baseline_partner_share populated cells (conf_state='all'): {n_bps_populated}, "
        f"expected 27,223 (of {len(bps_all):,} total conf_state='all' cells)"
    )
    assert bps_noconf.isna().all(), "baseline_partner_share must be NULL on every no_conf cell"
    bps_populated = bps_all.dropna()
    assert (bps_populated > 0).all() and (bps_populated <= 1.0).all(), (
        "baseline_partner_share must be in (0, 1] wherever non-null -- NEVER 0 (D53)"
    )


LAZY_FILES = ["ptn_works", "ptn_topics", "aut_works", "geo_fields", "subset_works"]


def test_lazy_files_class1_row_group_invariant():
    """Class-1 invariant (data_foundation.yaml rev 3.1 meta.lazy_file_rules): every lazy work/
    cell-grain file needs num_row_groups >= n_rows/10000, or lib.lazy.read_keyed's whole
    predicate-pushdown premise (F0-measured: ptn_topics 1/45 groups, ptn_works 1/24 groups) is
    defeated -- a "pruned" read would silently load the entire file.

    W2/W4 asserted this at BUILD time against the SNAPSHOT tables/ files (see progress/
    W2_partner_views.md: "86 row groups (Class-1 floor 86>=43.0: PASS)"; progress/W4_author_views.md:
    "17 row groups (floor 8.3, PASS)"). This test re-asserts the SAME invariant against the DEPLOYED
    Streamlit/data/ copies -- and, run live during E1b, found it FAILING for 3 of the 5 files.

    Root cause (confirmed, not this stream's fence to fix): pipeline/60_deploy.py's generic write
    path is `validated.to_parquet(out_path, index=False, compression="zstd")` -- no `row_group_size`
    argument, and no `spec.get("lazy")` special case at all. Every file, lazy-declared or not, is
    re-serialised into however many row groups pandas/pyarrow choose by default (observed: exactly 1
    per file at this size), regardless of how many row groups the SNAPSHOT builder wrote. geo_fields
    and subset_works currently still PASS only because they are small enough that even 1 row group
    clears their (sub-1) floor -- not because the deploy step preserved anything.

    Reported here, not silently weakened: this is real, previously-uncaught drift between what W2/W4
    verified at build time and what the app actually reads, and pipeline/60_deploy.py is outside this
    stream's scope fence (create/modify only test_foundation_v3.py, load_map_eval.py, this report).
    One-line fix for whoever owns 60_deploy.py: pass `row_group_size=5000` (or read it from a new
    contract field) whenever `spec.get("lazy")` is true. See progress/E1b_evals.md.
    """
    failures = []
    for name in LAZY_FILES:
        pf = _parquet_file(name)
        n_rows = pf.metadata.num_rows
        n_rg = pf.metadata.num_row_groups
        floor = n_rows / 10000
        if n_rg < floor:
            failures.append(f"{name}: {n_rg} row group(s) for {n_rows:,} rows (floor {floor:.2f})")
    assert not failures, (
        "Class-1 row-group invariant violated on the DEPLOYED copy (pipeline/60_deploy.py's "
        "to_parquet call has no row_group_size -- see this test's docstring for the confirmed root "
        "cause; out of this stream's fence to fix):\n" + "\n".join(failures)
    )


NEW_TABLES_SNAPSHOT_DATE_EXEMPT = {
    "work_subsets": "thin work x subset FK/evidence table -- contract declares no snapshot_date column",
    "subset_works": "same reasoning as work_subsets (its metadata-bearing sibling); contract confirms no column",
    "aut_works": "work-grain list table (structurally impact-free); contract's own column list has no snapshot_date",
    "aut_impact_drill": "contract's own column list has no snapshot_date (author_id/conf_state/fwci_fr_mean/"
                         "pptop10_count/works_with_indicators only)",
}

NEW_TABLES = [
    "dim_subsets", "work_subsets", "dim_artifact_topics", "subset_works",
    "ptn_summary", "ptn_mom_facts", "ptn_yearly", "ptn_fields", "ptn_labs", "ptn_works", "ptn_topics",
    "geo_countries", "geo_fields", "geo_groups", "consortium_weights",
    "thm_specialisation", "thm_diversity", "thm_codiscipline", "thm_funding", "thm_frontier",
    "aut_public", "aut_works", "aut_impact_drill", "aut_coverage",
]


def test_new_tables_snapshot_date_pinned(tables):
    assert len(NEW_TABLES) == 24, "the 4 producers (48/46/47/45b) emit 24 new tables -- list drifted"
    mismatches = []
    for name in NEW_TABLES:
        if name in NEW_TABLES_SNAPSHOT_DATE_EXEMPT:
            continue
        df = tables(name, columns=None)
        if "snapshot_date" not in df.columns:
            mismatches.append(f"{name}: no snapshot_date column and not a declared exemption")
            continue
        values = set(df["snapshot_date"].unique().tolist())
        if values != {SNAPSHOT_DATE}:
            mismatches.append(f"{name}: snapshot_date values {values}, expected {{'{SNAPSHOT_DATE}'}}")
    assert not mismatches, "\n".join(mismatches)


def test_ptn_summary_isite_reconciliation(tables):
    ptn_summary = tables("ptn_summary")
    for conf_state in ("all", "no_conf"):
        all_rows = ptn_summary[
            (ptn_summary["conf_state"] == conf_state) & (ptn_summary["subset_id"] == "all")
        ].set_index("partner_id")
        isite_rows = ptn_summary[
            (ptn_summary["conf_state"] == conf_state) & (ptn_summary["subset_id"] == "in_isite")
        ].set_index("partner_id")
        joined = all_rows[["isite_co_works"]].join(isite_rows[["co_works_full"]], how="inner")
        assert len(joined) > 0, f"{conf_state}: no partners with an in_isite subset row to reconcile"
        bad = joined[joined["isite_co_works"] != joined["co_works_full"]]
        assert bad.empty, (
            f"{conf_state}: {len(bad)} partner(s) where isite_co_works(all-row) != "
            f"co_works_full(in_isite-row):\n{bad.head()}"
        )


def test_work_subsets_fk_integrity_vs_dim_subsets(tables):
    work_subsets = tables("work_subsets")
    subset_works = tables("subset_works")
    dim_subsets = tables("dim_subsets")
    known_ids = set(dim_subsets["subset_id"])
    for name, df in (("work_subsets", work_subsets), ("subset_works", subset_works)):
        orphans = set(df["subset_id"].unique()) - known_ids
        assert not orphans, f"{name}: orphan subset_id(s) not present in dim_subsets: {orphans}"


def test_ptn_topics_conf_state_values_and_noconf_pinned_totals(tables):
    pt = tables("ptn_topics")
    assert set(pt["conf_state"].unique()) == {"all", "no_conf"}, (
        f"ptn_topics conf_state must be exactly {{'all', 'no_conf'}}, got {set(pt['conf_state'].unique())}"
    )
    no_conf = pt[pt["conf_state"] == "no_conf"]
    assert len(no_conf) == 205575, f"ptn_topics no_conf rows: {len(no_conf)}, expected 205,575 (pinned)"
    cells = no_conf.drop_duplicates(["partner_id", "topic_id"])
    assert len(cells) == 144096, f"ptn_topics no_conf cells: {len(cells)}, expected 144,096 (pinned)"
    cell_totals = no_conf.groupby(["partner_id", "topic_id"], observed=True)["co_works"].sum()
    assert int((cell_totals >= 3).sum()) == 22856
    assert int((cell_totals >= 20).sum()) == 1127


def test_thm_frontier_standardised_share_present_wherever_raw_present(tables):
    tf = tables("thm_frontier")
    panel = tf[tf["row_kind"] == "panel"]
    assert len(panel) > 0, "thm_frontier has no panel rows -- table shape drifted"
    has_raw = panel["raw_frontier_share"].notna()
    has_std = panel["field_standardised_share"].notna()
    assert has_raw.sum() > 0, "no panel row has a non-null raw_frontier_share -- pick a different check"
    missing_std = panel[has_raw & ~has_std]
    assert missing_std.empty, (
        f"{len(missing_std)} panel row(s) have raw_frontier_share but no field_standardised_share "
        f"(standardised must sit BESIDE raw everywhere, per the x1.37/x1.03 golden discipline)"
    )


def test_xa_discipline_corpus_facts_spot_check(tables):
    facts = tables("dim_corpus_facts").set_index("conf_state")
    all_row = facts.loc["all"]
    delta = int(all_row["corpus_works"]) - int(all_row["corpus_works_xa"])
    assert delta == 4106, (
        f"dim_corpus_facts 'all' row: corpus_works {int(all_row['corpus_works'])} - corpus_works_xa "
        f"{int(all_row['corpus_works_xa'])} = {delta}, expected exactly 4,106 (the primary "
        f"artifact-flag count) -- the xa discipline's own arithmetic must hold on the DEPLOYED facts"
    )


# =================================================================================================
# conf-sweep check (new, from the ptn_topics near-miss -- data_foundation.yaml rev 3.1 conventions:
# "conf_state in {all, no_conf} on EVERY new aggregate, or explicit conf_exempt/conf columns with
# reason"). ptn_topics itself shipped WITHOUT conf_state for two fix rounds before P2 caught that its
# parent ptn_fields is conf-keyed (progress/W2_partner_views.md, FIX ROUND 3) -- this check exists so
# the NEXT such gap is caught by a test, not by a reviewer noticing a visible inconsistency.
# =================================================================================================

# The dispatch's own parenthetical names 5 exemptions (aut_public, aut_works, ptn_works,
# dim_artifact_topics, subset_works) and separately notes "consortium_weights has conf_state" (i.e.
# NOT exempt, just confirmed covered normally -- verified above, its `conf_state` column is literal).
# Two more genuinely lack a conf_state column for the SAME already-ratified reasons the dispatch gives
# for aut_public/work-grain tables (verified against data_foundation.yaml's own grain lines): dim_subsets
# ("conf/xa as COLUMNS, not rows -- tunnel #14", same pattern as aut_public) and work_subsets (a thin
# FK/evidence table with no measure column at all, same class as dim_artifact_topics/subset_works).
# Both are added here, reasoned explicitly, rather than either silently failing the sweep on a
# false positive or silently omitting them from the walked table list.
CONF_STATE_EXEMPT = {
    "aut_public": "conf as COLUMNS (n_works vs n_works_noconf twins) -- tunnel #12 RAM ruling",
    "dim_subsets": "conf as COLUMNS (n_works vs n_works_noconf twins), same pattern -- tunnel #14",
    "aut_works": "work-grain list table; per-row is_conference IS the conference dimension",
    "ptn_works": "work-grain list table; per-row is_conference (same reasoning as aut_works)",
    "subset_works": "work-grain list table; per-row is_conference (same reasoning)",
    "dim_artifact_topics": "topic DICTIONARY (811 static rows); no conf grain applies",
    "work_subsets": "thin FK/evidence table, no measure column; no conf grain applies",
}


def test_conf_sweep_every_new_table_has_conf_state_or_declared_exemption(tables):
    violations = []
    for name in NEW_TABLES:
        df = tables(name)
        has_conf_state = "conf_state" in df.columns
        if name in CONF_STATE_EXEMPT:
            if has_conf_state:
                violations.append(f"{name}: declared exempt but NOW carries conf_state -- stale exemption")
            continue
        if not has_conf_state:
            violations.append(
                f"{name}: no conf_state column and not a declared exemption "
                f"(declared exemptions: {sorted(CONF_STATE_EXEMPT)})"
            )
    assert not violations, "conf-sweep violation(s):\n" + "\n".join(violations)


# =================================================================================================
# pass 5 (S3): thm_frontier_labs / thm_sdg_labs (47b_build_crossings.py, ruling R16/plan P3) and
# bench_sdg / bench_positioning / bench_diversity (49c_build_peer_context.py, rulings R6/R7/plan P5).
# Re-asserted against the DEPLOYED Streamlit/data/ copies, same discipline as every other test in
# this module -- full rationale + build-time asserts live in the two builder scripts themselves and
# in progress/S3_data_ext.md.
# =================================================================================================

PASS5_ROW_COUNTS = {
    "thm_frontier_labs": 138, "thm_sdg_labs": 2208,
    "bench_sdg": 340, "bench_positioning": 520, "bench_diversity": 20,
}


def test_pass5_tables_row_counts_and_snapshot_date(tables):
    mismatches = []
    for name, expected in PASS5_ROW_COUNTS.items():
        df = tables(name)
        if len(df) != expected:
            mismatches.append(f"{name}: {len(df):,} rows, expected {expected:,}")
        values = set(df["snapshot_date"].unique().tolist())
        if values != {SNAPSHOT_DATE}:
            mismatches.append(f"{name}: snapshot_date values {values}, expected {{'{SNAPSHOT_DATE}'}}")
    assert not mismatches, "\n".join(mismatches)


def test_thm_frontier_labs_works_n_reconciles_to_ul_labs(tables):
    """Acceptance #1, identity 1, re-asserted against the DEPLOYED copies (ul_labs.parquet is
    deployed in its WIDE D56+D60 shape -- 100 rows incl. 21 hors-liste + 10 poles; the 69 curated
    structures this table's lab universe matches are `in_client_list==True & Structure type !=
    'department'`)."""
    ul_labs = tables("ul_labs", columns=["Structure name", "Structure type", "in_client_list", "Pubs total"])
    curated = ul_labs[ul_labs["in_client_list"] & (ul_labs["Structure type"] != "department")]
    assert len(curated) == 69, f"curated lab universe on the deployed ul_labs: {len(curated)} != 69"

    frl = tables("thm_frontier_labs")
    assert set(frl["lab"].unique()) == set(curated["Structure name"].unique()), (
        "thm_frontier_labs.lab universe does not match the deployed ul_labs curated 69"
    )
    frl_all = frl[frl["conf_state"] == "all"].set_index("lab")["works_n"]
    curated_lookup = curated.set_index("Structure name")["Pubs total"]
    bad = [lab for lab in frl_all.index if int(frl_all[lab]) != int(curated_lookup[lab])]
    assert not bad, f"works_n vs ul_labs.'Pubs total' mismatch on {len(bad)} lab(s): {bad[:5]}"


def test_thm_sdg_labs_union_reconciles_to_sdg_siris(tables):
    """Acceptance #1, identity 2, re-asserted against the DEPLOYED copies: the UNION (deduplicated)
    of every lab's (incl. NO LAB) work set intersected with sdg_siris's tagged works must equal
    sdg_siris's own full distinct-tagged-work set exactly."""
    ul_pubs = tables("ul_pubs", columns=["work_id", "Labs"])
    sdg_siris = tables("sdg_siris", columns=["work_id"])
    tagged = set(sdg_siris["work_id"].unique())

    lab_names = set(tables("thm_sdg_labs")["lab"].unique())
    split = ul_pubs["Labs"].fillna("").str.split(" | ", regex=False)
    union_tagged: set = set()
    for lab in lab_names:
        mask = split.apply(lambda ls: lab in ls)
        union_tagged |= (set(ul_pubs.loc[mask, "work_id"]) & tagged)
    assert union_tagged == tagged, (
        f"thm_sdg_labs union-of-labs reconciliation FAILED on deployed copies: "
        f"{len(tagged - union_tagged)} tagged work(s) uncovered, "
        f"{len(union_tagged - tagged)} extra work(s)"
    )


def test_thm_frontier_labs_d53_floor_and_xa_discipline(tables):
    frl = tables("thm_frontier_labs")
    thin = frl[frl["works_n_scoreable"] < 30]
    bad_thin = thin[thin[["frontier_share", "field_standardised_share"]].notna().any(axis=1)]
    assert bad_thin.empty, (
        f"{len(bad_thin)} row(s) below the 30-scoreable-work floor still carry a non-null share"
    )
    assert (frl["works_n_xa"] <= frl["works_n"]).all(), "works_n_xa must never exceed works_n"
    assert (frl["frontier_works_n"] <= frl["works_n_scoreable"]).all(), (
        "frontier_works_n must never exceed works_n_scoreable"
    )
    assert (frl["isite_works_n"] <= frl["works_n"]).all(), "isite_works_n must never exceed works_n"
    assert (frl["isite_frontier_works_n"] <= frl["frontier_works_n"]).all(), (
        "isite_frontier_works_n must never exceed frontier_works_n"
    )


def test_thm_sdg_labs_d53_floor_and_xa_discipline(tables):
    sdgl = tables("thm_sdg_labs")
    thin = sdgl[sdgl["works_tagged_n"] < 30]
    bad_thin = thin[thin["share_of_lab_sdg_tagged"].notna()]
    assert bad_thin.empty, f"{len(bad_thin)} row(s) below the 30-tagged-work floor still carry a share"
    assert (sdgl["works_n_xa"] <= sdgl["works_n"]).all()
    assert (sdgl["works_this_sdg_n"] <= sdgl["works_tagged_n"]).all(), (
        "a per-SDG work count must never exceed the lab's own tagged-work total"
    )
    assert set(sdgl["sdg"].unique()) == set(range(1, 17)), "thm_sdg_labs must cover SDG 1-16 exactly (SIRIS-B, no SDG17 sheet)"


def test_bench_context_tables_exempt_by_construction(tables):
    """S9: bench_sdg / bench_positioning / bench_diversity carry NO _xa/artifact_flag column
    anywhere, on ANY row including UL's own -- same rule bench_peers itself is tested under
    (tests/test_bench_peers.py, out of this stream's fence, not duplicated here)."""
    for name in ("bench_sdg", "bench_positioning", "bench_diversity"):
        df = tables(name)
        xa_cols = [c for c in df.columns if c.endswith("_xa") or c == "artifact_flag"]
        assert not xa_cols, f"{name} carries artifact/_xa column(s), should be exempt: {xa_cols}"


def test_bench_sdg_covers_native_range_and_entities(tables):
    bs = tables("bench_sdg")
    assert set(bs["sdg"].unique()) == set(range(1, 18)), "bench_sdg must cover SDG 1-17 (native Aurora range)"
    assert bs["entity_id"].nunique() == 10, "bench_sdg must cover UL + 9 peers (10 entities)"
    assert "I90183372" in set(bs["entity_id"]), "bench_sdg must include UL's own entity_id"


def test_bench_positioning_join_coverage_floor(tables):
    bp = tables("bench_positioning")
    per_entity = bp.groupby("entity_id")["join_coverage_pct"].first()
    assert len(per_entity) == 10, "bench_positioning must cover 10 entities"
    low = per_entity[per_entity < 99.0]
    assert low.empty, f"entity/entities below the 99% join-coverage band: {low.to_dict()}"
    assert set(bp["method"].unique()) == {"primary_topic_both_sides"}


# =================================================================================================
# pass 5 (S3b): thm_frontier_topics (47c_build_frontier_topics.py, ruling R11 full-depth
# materialization). Re-asserted against the DEPLOYED Streamlit/data/ copy, same discipline as
# every other test in this module -- full rationale + the build-time golden-continuity assert live
# in the builder script itself and in progress/S3b_frontier_depth.md.
# =================================================================================================

def test_thm_frontier_topics_row_count_and_snapshot_date(tables):
    tft = tables("thm_frontier_topics")
    assert len(tft) == 6548, f"thm_frontier_topics rows: {len(tft):,}, expected 6,548"
    values = set(tft["snapshot_date"].unique().tolist())
    assert values == {SNAPSHOT_DATE}, f"thm_frontier_topics snapshot_date values {values}"


def test_thm_frontier_topics_row_coverage_matches_corpus_primary_topics(tables):
    """Row coverage == distinct topics in the corpus topic table. `corpus_topics.parquet` itself
    is a snapshot-only table (never deployed to Streamlit/data/, not in data_contract.yaml), so
    the DEPLOYED proxy for "distinct topics the corpus actually uses as its PRIMARY topic" is
    `ul_pubs.primary_topic_id` (works_master's own deployed rename) -- the SAME definition
    thm_frontier_topics's own grain is built on (its builder's docstring: "distinct topic_id
    carrying an is_primary==True row in corpus_topics.parquet", which is definitionally identical
    to "distinct non-null primary_topic_id across works_master/ul_pubs" -- a work's PRIMARY topic
    is by construction the one is_primary==True row it carries in corpus_topics). Read this way
    (not corpus_topics's own ANY-topic-assignment population, 3,966 on this snapshot) because the
    dispatch's own row-count estimate ("~3,275 x 2 -- tiny") matches the PRIMARY-topic population
    (3,274) and not the any-topic one -- probed, not assumed."""
    ul_pubs = tables("ul_pubs", columns=["primary_topic_id"])
    raw = ul_pubs["primary_topic_id"]
    # Filter on the ORIGINAL column's own .notna(), never on a stringified sentinel: ul_pubs's
    # nullable "string" dtype stringifies a missing value as the literal "<NA>" (not "None"), so a
    # post-cast "!= 'None'" check would silently miscount -- probed live, not assumed.
    tid = raw[raw.notna()].astype(str).str.replace("https://openalex.org/", "", regex=False).str.strip()
    n_primary_topics = tid.nunique()
    assert n_primary_topics == 3274, f"corpus primary-topic universe: {n_primary_topics}, expected 3,274"

    tft = tables("thm_frontier_topics")
    assert tft["topic_id"].nunique() == n_primary_topics, (
        f"thm_frontier_topics distinct topic_id ({tft['topic_id'].nunique()}) != corpus primary-"
        f"topic universe ({n_primary_topics})"
    )
    for conf_state in ("all", "no_conf"):
        n = int((tft["conf_state"] == conf_state).sum())
        assert n == n_primary_topics, (
            f"thm_frontier_topics conf_state={conf_state!r} row count {n} != {n_primary_topics}"
        )


def test_thm_frontier_topics_golden_continuity_vs_thm_frontier_texture(tables):
    """The 20 topics thm_frontier's own texture rows already materialized (pre-R11) must reproduce
    IDENTICAL scores AND counts on thm_frontier_topics, per topic_id x conf_state -- the golden-
    continuity acceptance criterion for this deliverable. Independently re-joined here against the
    DEPLOYED copies (not merely trusting the builder's own build-time assert)."""
    tf = tables("thm_frontier")
    texture = tf[tf["row_kind"] == "texture"]
    assert len(texture) == 40, f"thm_frontier texture rows: {len(texture)}, expected 40 (20 x 2 conf_states)"

    tft = tables("thm_frontier_topics")
    merged = texture.merge(tft, on=["topic_id", "conf_state"], how="left", suffixes=("_old", "_new"))
    assert len(merged) == 40
    assert merged["frontier_score_std_new"].notna().all(), (
        "a pre-existing texture topic has no score on thm_frontier_topics -- golden continuity broken"
    )
    mismatch = merged[~np.isclose(
        merged["frontier_score_std_old"].astype(float), merged["frontier_score_std_new"].astype(float),
    )]
    assert mismatch.empty, (
        f"{len(mismatch)} texture topic(s) reproduce a DIFFERENT frontier_score_std on "
        f"thm_frontier_topics: {mismatch[['topic_id', 'conf_state']].to_dict('records')}"
    )
    for col in ("ul_works", "ul_works_xa", "isite_works", "isite_works_xa"):
        bad = merged[merged[f"{col}_old"] != merged[f"{col}_new"]]
        assert bad.empty, f"{len(bad)} texture topic(s) reproduce a DIFFERENT {col} on thm_frontier_topics"


def test_thm_frontier_topics_isite_never_exceeds_ul_works(tables):
    tft = tables("thm_frontier_topics")
    assert (tft["isite_works"] <= tft["ul_works"]).all(), "isite_works must never exceed ul_works"
    assert (tft["isite_works_xa"] <= tft["ul_works_xa"]).all(), (
        "isite_works_xa must never exceed ul_works_xa")
    assert (tft["ul_works_xa"] <= tft["ul_works"]).all(), "ul_works_xa must never exceed ul_works"


def test_thm_frontier_topics_null_score_always_carries_a_reason_code(tables):
    """Honest NULL discipline: a topic outside the frontier catalog or under the score's own
    definedness floor gets NULL + a reason code, never a fake 0 and never a silent NULL."""
    tft = tables("thm_frontier_topics")
    score_null = tft["frontier_score_std"].isna()
    reason_null = tft["score_reason"].isna()
    assert (score_null == ~reason_null).all(), (
        "frontier_score_std NULL must be exactly equivalent to score_reason non-null"
    )
    assert score_null.sum() > 0, "the floor must actually bind on this table (0 NULL rows found)"
    valid_reasons = {"excluded_811", "unmatched_baseline", "no_baseline_score"}
    got_reasons = set(tft["score_reason"].dropna().unique().tolist())
    assert got_reasons <= valid_reasons, f"unexpected score_reason value(s): {got_reasons - valid_reasons}"


def test_bench_diversity_transfer_bar_and_ul_both_ways_pinned(tables):
    """Pins the two UL-both-ways numbers measured at build time (progress/S3_data_ext.md /
    docs/METHODES.md): the DEPLOYED thm_diversity's (all, 2019, all) rao_stirling, and
    bench_diversity's own shipped UL row (conf_state='all') -- re-asserted against whatever
    actually sits in Streamlit/data/ right now, catching drift on a re-deploy or rollback."""
    thm_diversity = tables("thm_diversity")
    stored = thm_diversity[(thm_diversity.perimeter_id == "all") & (thm_diversity.year == 2019)
                           & (thm_diversity.conf_state == "all")]
    assert len(stored) == 1
    assert abs(float(stored.iloc[0]["rao_stirling"]) - 0.321715) < 1e-5, (
        f"thm_diversity (all,2019,all) rao_stirling drifted: {float(stored.iloc[0]['rao_stirling'])}"
    )

    bd = tables("bench_diversity")
    ul_row = bd[(bd.entity_id == "I90183372") & (bd.conf_state == "all")]
    assert len(ul_row) == 1
    assert abs(float(ul_row.iloc[0]["rao_stirling"]) - 0.332703) < 1e-5, (
        f"bench_diversity UL row rao_stirling drifted: {float(ul_row.iloc[0]['rao_stirling'])}"
    )
    assert set(bd["method"].unique()) == {"primary_topic_both_sides"}
    assert bd["entity_id"].nunique() == 10
    rs = bd.loc[bd.conf_state == "all", "rao_stirling"].dropna()
    assert rs.between(0.25, 0.40).all(), f"rao_stirling out of the expected [0.25,0.40] sanity band: {rs.tolist()}"
