"""47b_build_crossings.py -- thm_frontier_labs / thm_sdg_labs (pass 5, S3, ruling R16 / plan P3).

Two lab-grain CROSSING tables for the "5 Positionnement" page's "frontier x labs" panel and the SDG
panel's lab cut. Owner's rule, restated here because it drives the whole design of this file:
**crossing != comparing** -- neither table carries a peer column, a peer row, or a peer-shaped
denominator anywhere. Peer comparison lives entirely in `pipeline/49c_build_peer_context.py`'s
bench_* family; this file never reads a peer table.

Grain: BOTH tables key on `lab`, the same 69-value vocabulary `pipeline/47_build_thematic_ext.py`
already uses for thm_diversity's perimeter_id expansion (docs/data_contract.yaml thm_diversity:
"71 perimeters == 2 (all, in_isite) + 69 (ul_labs.lab)") -- read from `ul_labs.parquet`'s own `lab`
column (NOT thematic_detail_contributions' department/lab blobs, which deliberately DROP the
"NO LAB" pseudo-category for a different reason -- a taxonomy-node contributor list should not
show "no lab" as a contributor). This file's grain follows 47's own precedent and KEEPS "NO LAB",
exactly like thm_diversity does: NO LAB's 4,568 works are a real, measurable slice of the corpus,
and keeping it makes the union-of-69-lab-work-sets reconciliation below exact with no special case
(every work carries either >=1 curated lab or the literal "NO LAB" value in works_master.Labs).

thm_frontier_labs -- construction copied from 47_build_thematic_ext.py's frontier section (module
read in full before writing this file): same baseline file
(`inputs/manual/frontierness_baseline.xlsx`), same `lib.artifact.load_bad_topics` 811-topic
exclusion, same primary-topic join. "frontier work" here uses 47's own AMPLIFICATION-GOLDEN cut
(`Average frontierness >= kept["Average frontierness"].quantile(0.90)`, the identical threshold 47
uses for its own raw x1.37 golden) rather than 47's PANEL construction (a continuous mean-percentile,
which has no natural "frontier works n" COUNT) -- the plan's own column list ("works n, **frontier
works n**, frontier share") names a count, which only the binary cut produces.

field_standardised_share GENERALISATION (plan instruction: "if standardisation needs field mixes,
compute per lab"): 47's own two-GROUP direct standardisation (ISITE vs rest, both evaluated against
ISITE's own field mix) does not generalise unchanged to a 69-LAB comparison -- there is no single
"the other group" to borrow a mix from. The natural N-group generalisation (the standard
epidemiological move: standardise every group onto ONE shared reference population, never onto each
other pairwise) is applied instead: ONE reference field-mix, the WHOLE CORPUS's own scoreable-works
field distribution (computed once per conf_state -- the same "fixed, built once, reused unchanged
for every subset" discipline this codebase already applies to the disparity matrix and to the
frontier baseline itself), replaces ISITE's field mix as the shared weighting distribution. Every
lab's OWN per-field in-cut rate is reweighted onto that one shared reference, so every lab's
field_standardised_share is directly comparable to every other lab's -- which raw frontier_share
alone is not (a lab concentrated in a naturally frontier-heavy field reads high on the raw share for
a COMPOSITIONAL reason, not a within-field behavioural one -- trap #0 already named in 47's own
module docstring). A lab's own weights are RESTRICTED to the fields it actually has scoreable works
in and RENORMALISED to sum to 1 over that restricted set -- a lab with zero scoreable works in a
field contributes nothing to that field's cell rather than being scored on a field it has no
presence in. Both raw and standardised shares use the SAME denominator basis (a lab's own SCOREABLE
work count, matching 47's own panel convention where raw_frontier_share is itself computed over
`scoreable`, never over the raw corpus) -- "standardised beside raw, same basis" is the discipline
S6.1 already names for 47 itself; the non-scoreable remainder is disclosed, never silently folded
into either denominator.

thm_sdg_labs -- SIRIS-B route (`sdg_siris.parquet`, the same table the shipped SDG panel's default
`app.sdg_variant='b_siris'` reads through `sdg_three_way.B_siris`; read directly here since it is
already the long work x sdg grain this table needs, no space-separated string parsing required).
"share of lab's SDG-tagged works" (plan wording, verbatim): the denominator is the lab's OWN
SDG-TAGGED work count, NOT its whole work count -- the same "untagged is not evidence of 0 SDG
relevance" discipline already carried in docs/data_contract.yaml's sdg_three_way.parquet
consumer_constraint (14.8% corpus coverage is a keyword-method floor, not a finding). A lab's shares
across its 16 SDG rows can sum above 1.0 (a work can carry several SDGs, corpus-wide average 1.445
per tagged work per METHODES S5) -- this is expected, not a bug. No ISITE decomposition on this
table this pass (the plan names it for thm_frontier_labs only; a lab x SDG x ISITE 3-way cross would
sit on cells thinner than the 30-work floor almost everywhere at 14.8% corpus-wide SDG coverage --
documented in docs/OVERLAY_MATRIX.md as a cheap, not-built-this-pass follow-up, never silently
promised).

D53 floors (both tables): a lab's SHARE/RATE columns (frontier_share*, field_standardised_share*,
share_of_lab_sdg_tagged*) are NULL, never 0, whenever their own denominator is below
config.metrics.min_stratum_n (30). Raw counts (works_n, frontier_works_n, works_tagged_n) are NEVER
floored -- a count is a fact, not a rate, and D53 only ever protects a RATIO from a thin denominator.

conf_state {all, no_conf}: added on both tables per data_foundation.yaml's standing convention
("conf_state on EVERY new aggregate, or an explicit exemption with reason") -- no exemption applies
here (both tables have a real is_conference dimension to split on), so both carry it as a normal row
key, the same is_conference mask used everywhere else in this pipeline.

ARTIFACT-FLAG (_xa twins, R-A convention): every measure column on both tables is twinned with its
`_xa` variant (primary-flagged works dropped), computed with `lib.artifact.flag_works` exactly as
every other work-grain aggregate in this pipeline does.

Usage: python pipeline/47b_build_crossings.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.artifact import flag_works, load_bad_topics  # noqa: E402
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
CONFIG = load_config(ROOT)
MIN_STRATUM_N = int(CONFIG["metrics"]["min_stratum_n"])   # 30, D53 floor
FIELD_CELL_MIN_WORKS = int(CONFIG["workshop_tunables"]["i11_sparkline_min_works"])  # 3, reused guard
CONF_STATES = ["all", "no_conf"]
SDG_NUMBERS = list(range(1, 17))   # no SDG17 sheet, per pipeline/55_sdg_three_way.py convention


def conf_mask(works: pd.DataFrame, state: str) -> pd.Series:
    return pd.Series(True, index=works.index) if state == "all" else ~works["is_conference"].fillna(False)


def lab_masks(works: pd.DataFrame, lab_names: list[str]) -> dict[str, pd.Series]:
    """One boolean mask per lab name, over `works`'s own index -- works_master.Labs is a
    ' | '-delimited multi-value string (a work can carry >1 lab), same split convention as
    47_build_thematic_ext.py's `_lab_mask` helper and 44d's department/lab blob explode."""
    split = works["Labs"].fillna("").str.split(" | ", regex=False)
    return {lab: split.apply(lambda ls: lab in ls) for lab in lab_names}


# ================================================================================ thm_frontier_labs
def build_thm_frontier_labs(works: pd.DataFrame, lab_names: list[str], masks: dict[str, pd.Series],
                            all_topics: pd.DataFrame, snapshot_name: str) -> pd.DataFrame:
    print("\n[1/2] thm_frontier_labs")
    baseline_path = ROOT / "inputs" / "manual" / "frontierness_baseline.xlsx"
    base = pd.read_excel(baseline_path, sheet_name="FILTERING OUT TOPICS")
    base.columns = [c.strip() for c in base.columns]
    KEY = "Topic ID no url"
    base[KEY] = base[KEY].astype(str).str.strip()

    bad_ids = load_bad_topics(ROOT)
    base["excluded"] = base[KEY].isin(bad_ids)
    n_excluded = int(base["excluded"].sum())
    assert n_excluded == 811, f"exclusion count drifted: {n_excluded} != 811 (F0-P4 golden)"
    kept = base[~base["excluded"]].copy()

    field_name_to_id = all_topics.drop_duplicates("field_name").set_index("field_name")["field_id"] \
        .astype("string")
    kept["field_id_baseline"] = kept["OA field"].map(field_name_to_id)
    assert kept["field_id_baseline"].isna().sum() == 0, "OA field values not resolving to all_topics.field_id"

    thr10_raw = kept["Average frontierness"].quantile(0.90)
    print(f"  frontier cut (top decile of kept-topic Average frontierness): >= {thr10_raw:.4f} "
          f"(same threshold as 47's own raw x1.37 amplification golden)")

    wf = works[["work_id", "primary_topic_id", "In_ISITE", "artifact_flag"]].copy()
    wf["tid"] = wf["primary_topic_id"].astype(str).str.replace(
        "https://openalex.org/", "", regex=False).str.strip()
    wf = wf.merge(base[[KEY, "Average frontierness", "excluded"]], left_on="tid", right_on=KEY, how="left")
    wf = wf.merge(kept[[KEY, "field_id_baseline"]], on=KEY, how="left")

    matched = wf[KEY].notna()
    join_coverage = matched.sum() / len(works)
    print(f"  join coverage (primary topic -> baseline): {matched.sum():,}/{len(works):,} = "
          f"{join_coverage*100:.2f}% (golden ~99.9%)")
    assert join_coverage > 0.995, f"join coverage drifted: {join_coverage*100:.2f}%"

    scoreable = wf[matched & (wf["excluded"] == False) & wf["Average frontierness"].notna()].copy()  # noqa: E712
    scoreable["in_cut_raw"] = scoreable["Average frontierness"] >= thr10_raw
    print(f"  scoreable (kept-topic) works corpus-wide: {len(scoreable):,}/{len(works):,} "
          f"= {len(scoreable)/len(works)*100:.1f}%")

    rows = []
    for conf_state in CONF_STATES:
        cm = conf_mask(works, conf_state)
        state_work_ids = set(works.loc[cm, "work_id"])
        sc_state = scoreable[scoreable["work_id"].isin(state_work_ids)]
        # ONE reference field-mix per conf_state -- the whole-corpus scoreable-works field
        # distribution, fixed and reused unchanged for every one of the 69 labs below.
        ref_weights = sc_state["field_id_baseline"].value_counts(normalize=True)

        for lab in lab_names:
            m = masks[lab] & cm
            m_xa = m & ~works["artifact_flag"]
            lab_ids = set(works.loc[m, "work_id"])
            lab_ids_xa = set(works.loc[m_xa, "work_id"])
            works_n = len(lab_ids)
            works_n_xa = len(lab_ids_xa)
            isite_works_n = int((works.loc[m, "In_ISITE"]).sum())
            isite_works_n_xa = int((works.loc[m_xa, "In_ISITE"]).sum())

            sub = sc_state[sc_state["work_id"].isin(lab_ids)]
            sub_xa = sub[sub["work_id"].isin(lab_ids_xa)]
            n_scoreable = len(sub)
            n_scoreable_xa = len(sub_xa)

            frontier_n = int(sub["in_cut_raw"].sum())
            frontier_n_xa = int(sub_xa["in_cut_raw"].sum())
            isite_frontier_n = int((sub["in_cut_raw"] & sub["In_ISITE"]).sum())
            isite_frontier_n_xa = int((sub_xa["in_cut_raw"] & sub_xa["In_ISITE"]).sum())

            frontier_share = (frontier_n / n_scoreable) if n_scoreable >= MIN_STRATUM_N else np.nan
            frontier_share_xa = (frontier_n_xa / n_scoreable_xa) if n_scoreable_xa >= MIN_STRATUM_N else np.nan

            def standardised(sub_lab: pd.DataFrame, n_lab_scoreable: int) -> float:
                # SMALL-CELL GUARD (found live, not theoretical: e.g. lab "Crem" has exactly 1
                # scoreable work in field 22, which the reference gives a 17% corpus-wide weight --
                # that single work's trivial 0/1 rate would then dominate the whole weighted sum,
                # the textbook instability of direct standardisation on sparse subgroups. Fields
                # where the LAB itself has fewer than FIELD_CELL_MIN_WORKS scoreable works are
                # dropped from the lab's own restricted set before renormalising -- the same
                # >=3-works sparkline floor `workshop_tunables.i11_sparkline_min_works` already
                # applies elsewhere in this pipeline, reused here rather than inventing a new
                # constant. Documented as a trap in docs/METHODES.md, same "fix the grain, disclose
                # it" discipline the diversity catalog card already applies to disparity instability.
                if n_lab_scoreable < MIN_STRATUM_N or n_lab_scoreable == 0:
                    return np.nan
                per_field_rate = sub_lab.groupby("field_id_baseline")["in_cut_raw"].mean()
                lab_field_counts = sub_lab["field_id_baseline"].value_counts()
                lab_field_counts = lab_field_counts[lab_field_counts >= FIELD_CELL_MIN_WORKS]
                w = ref_weights.reindex(lab_field_counts.index).fillna(0.0)
                if w.sum() <= 0:
                    return np.nan
                w = w / w.sum()
                return float((per_field_rate.reindex(w.index) * w).sum())

            field_std_share = standardised(sub, n_scoreable)
            field_std_share_xa = standardised(sub_xa, n_scoreable_xa)

            rows.append({
                "lab": lab, "conf_state": conf_state,
                "works_n": works_n, "works_n_xa": works_n_xa,
                "works_n_scoreable": n_scoreable, "works_n_scoreable_xa": n_scoreable_xa,
                "frontier_works_n": frontier_n, "frontier_works_n_xa": frontier_n_xa,
                "frontier_share": frontier_share, "frontier_share_xa": frontier_share_xa,
                "field_standardised_share": field_std_share,
                "field_standardised_share_xa": field_std_share_xa,
                "isite_works_n": isite_works_n, "isite_works_n_xa": isite_works_n_xa,
                "isite_frontier_works_n": isite_frontier_n, "isite_frontier_works_n_xa": isite_frontier_n_xa,
                "frontier_cut_threshold": float(thr10_raw),
            })

    out = pd.DataFrame(rows)
    out["snapshot_date"] = snapshot_name
    out = out.astype({
        "lab": "string", "conf_state": "string",
        "works_n": "int64", "works_n_xa": "int64",
        "works_n_scoreable": "int64", "works_n_scoreable_xa": "int64",
        "frontier_works_n": "int64", "frontier_works_n_xa": "int64",
        "frontier_share": "float64", "frontier_share_xa": "float64",
        "field_standardised_share": "float64", "field_standardised_share_xa": "float64",
        "isite_works_n": "int64", "isite_works_n_xa": "int64",
        "isite_frontier_works_n": "int64", "isite_frontier_works_n_xa": "int64",
        "frontier_cut_threshold": "float64", "snapshot_date": "string",
    })
    print(f"  wrote {len(out):,} rows ({len(lab_names)} labs x {len(CONF_STATES)} conf_states)")
    return out


# ==================================================================================== thm_sdg_labs
def build_thm_sdg_labs(works: pd.DataFrame, lab_names: list[str], masks: dict[str, pd.Series],
                       tables: Path, snapshot_name: str) -> pd.DataFrame:
    print("\n[2/2] thm_sdg_labs")
    sdg = pd.read_parquet(tables / "sdg_siris.parquet", columns=["work_id", "sdg"])
    tagged_ids_global = set(sdg["work_id"].unique())
    print(f"  sdg_siris.parquet (SIRIS-B route): {len(sdg):,} work x sdg rows, "
          f"{len(tagged_ids_global):,} distinct tagged works corpus-wide")

    rows = []
    for conf_state in CONF_STATES:
        cm = conf_mask(works, conf_state)
        for lab in lab_names:
            m = masks[lab] & cm
            m_xa = m & ~works["artifact_flag"]
            lab_ids = set(works.loc[m, "work_id"])
            lab_ids_xa = set(works.loc[m_xa, "work_id"])
            works_n = len(lab_ids)
            works_n_xa = len(lab_ids_xa)

            lab_sdg = sdg[sdg["work_id"].isin(lab_ids)]
            lab_sdg_xa = lab_sdg[lab_sdg["work_id"].isin(lab_ids_xa)]
            tagged_n = lab_sdg["work_id"].nunique()
            tagged_n_xa = lab_sdg_xa["work_id"].nunique()

            per_sdg_n = lab_sdg.groupby("sdg")["work_id"].nunique()
            per_sdg_n_xa = lab_sdg_xa.groupby("sdg")["work_id"].nunique()

            for sdg_num in SDG_NUMBERS:
                wsdg = int(per_sdg_n.get(sdg_num, 0))
                wsdg_xa = int(per_sdg_n_xa.get(sdg_num, 0))
                share = (wsdg / tagged_n) if tagged_n >= MIN_STRATUM_N else np.nan
                share_xa = (wsdg_xa / tagged_n_xa) if tagged_n_xa >= MIN_STRATUM_N else np.nan
                rows.append({
                    "lab": lab, "sdg": sdg_num, "conf_state": conf_state,
                    "works_n": works_n, "works_n_xa": works_n_xa,
                    "works_tagged_n": tagged_n, "works_tagged_n_xa": tagged_n_xa,
                    "works_this_sdg_n": wsdg, "works_this_sdg_n_xa": wsdg_xa,
                    "share_of_lab_sdg_tagged": share, "share_of_lab_sdg_tagged_xa": share_xa,
                })

    out = pd.DataFrame(rows)
    out["snapshot_date"] = snapshot_name
    out = out.astype({
        "lab": "string", "sdg": "int64", "conf_state": "string",
        "works_n": "int64", "works_n_xa": "int64",
        "works_tagged_n": "int64", "works_tagged_n_xa": "int64",
        "works_this_sdg_n": "int64", "works_this_sdg_n_xa": "int64",
        "share_of_lab_sdg_tagged": "float64", "share_of_lab_sdg_tagged_xa": "float64",
        "snapshot_date": "string",
    })
    print(f"  wrote {len(out):,} rows ({len(lab_names)} labs x {len(SDG_NUMBERS)} SDGs x "
          f"{len(CONF_STATES)} conf_states)")
    return out, tagged_ids_global


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    print(f"snapshot {snapshot.name}: building thm_frontier_labs / thm_sdg_labs (pass 5, S3, R16/P3)")

    works = pd.read_parquet(tables / "works_master.parquet", columns=[
        "work_id", "primary_topic_id", "In_ISITE", "is_conference", "Labs",
    ])
    corpus_topics = pd.read_parquet(tables / "corpus_topics.parquet",
                                    columns=["work_id", "topic_id", "is_primary"])
    all_topics = pd.read_parquet(tables / "all_topics.parquet", columns=["field_id", "field_name"])
    ul_labs = pd.read_parquet(tables / "ul_labs.parquet", columns=["lab", "works"])
    lab_names = ul_labs["lab"].tolist()
    assert len(lab_names) == 69, f"ul_labs.lab universe drifted: {len(lab_names)} != 69"
    print(f"  corpus works: {len(works):,}; lab universe: {len(lab_names)} (incl. NO LAB, per "
          f"47_build_thematic_ext.py's thm_diversity precedent)")

    flag_series = flag_works(corpus_topics, root=ROOT)
    works["artifact_flag"] = works["work_id"].map(flag_series).fillna(False).astype(bool)
    n_flagged = int(works["artifact_flag"].sum())
    assert n_flagged == 4106, f"artifact-flag count drifted: {n_flagged} != 4,106 (F0-P4 golden)"

    masks = lab_masks(works, lab_names)

    thm_frontier_labs = build_thm_frontier_labs(works, lab_names, masks, all_topics, snapshot.name)
    thm_sdg_labs, tagged_ids_global = build_thm_sdg_labs(works, lab_names, masks, tables, snapshot.name)

    # ============================================================================= RECONCILIATION
    print("\n" + "=" * 78)
    print("RECONCILIATION (acceptance #1)")
    print("=" * 78)

    # (1) thm_frontier_labs.works_n (conf_state='all') == ul_labs.works, per lab, EXACT.
    ul_labs_lookup = ul_labs.set_index("lab")["works"]
    frl_all = thm_frontier_labs[thm_frontier_labs["conf_state"] == "all"].set_index("lab")
    bad_labs = []
    for lab in lab_names:
        if int(frl_all.loc[lab, "works_n"]) != int(ul_labs_lookup[lab]):
            bad_labs.append((lab, int(frl_all.loc[lab, "works_n"]), int(ul_labs_lookup[lab])))
    identity_1 = ("thm_frontier_labs[conf_state='all'].works_n(lab) == ul_labs.works(lab), "
                  "for every one of the 69 lab rows (exact per-lab equality, incl. NO LAB)")
    print(f"IDENTITY 1: {identity_1}")
    print(f"  mismatches: {len(bad_labs)}/69" + (f" -- {bad_labs[:5]}" if bad_labs else " -- PASS"))
    assert not bad_labs, f"thm_frontier_labs works_n vs ul_labs.works mismatch on {len(bad_labs)} lab(s)"

    # (2) thm_sdg_labs: the UNION (deduplicated) of every lab's (conf_state='all') tagged-work set,
    # across all 69 lab rows (incl. NO LAB), equals sdg_siris.parquet's own full distinct-tagged-work
    # set EXACTLY -- every work carries either >=1 curated lab or the literal "NO LAB" value, so the
    # 69-way union recovers the whole corpus's tagged set with no remainder and no need for a
    # separate "plus NO LAB" clause.
    sdg_raw = pd.read_parquet(tables / "sdg_siris.parquet", columns=["work_id"])
    union_tagged: set = set()
    for lab in lab_names:
        lab_ids = set(works.loc[masks[lab], "work_id"])
        union_tagged |= (lab_ids & tagged_ids_global)
    identity_2 = ("UNION over all 69 lab work-sets (incl. NO LAB) of (lab's works) INTERSECT "
                  "(sdg_siris.parquet tagged works) == sdg_siris.parquet's full distinct-tagged-work "
                  "set, exactly (a partition-by-union check, not a sum -- multi-lab works are not "
                  "double-counted by a set union)")
    print(f"\nIDENTITY 2: {identity_2}")
    print(f"  union size: {len(union_tagged):,}  vs  sdg_siris distinct tagged: {len(tagged_ids_global):,}")
    assert union_tagged == tagged_ids_global, (
        f"thm_sdg_labs union-of-labs reconciliation FAILED: "
        f"{len(tagged_ids_global - union_tagged)} tagged work(s) not covered by any of the 69 labs, "
        f"{len(union_tagged - tagged_ids_global)} extra work(s) in the union not in sdg_siris"
    )
    print("  PASS (exact set equality)")

    # =================================================================================== write out
    compression = CONFIG["storage"]["compression"]
    outputs = {"thm_frontier_labs": thm_frontier_labs, "thm_sdg_labs": thm_sdg_labs}
    written_files = []
    for name, df in outputs.items():
        out_path = tables / f"{name}.parquet"
        df.to_parquet(out_path, index=False, compression=compression)
        written_files.append(out_path)
        print(f"\nwrote {name}.parquet: {len(df):,} rows x {len(df.columns)} cols, "
              f"{out_path.stat().st_size/1024:,.1f} KB")

    Manifest(snapshot).record_step(
        "47b_build_crossings",
        counts={name: len(df) for name, df in outputs.items()},
        files=written_files,
        params={
            "min_stratum_n": MIN_STRATUM_N,
            "frontier_cut_threshold": float(thm_frontier_labs["frontier_cut_threshold"].iloc[0]),
            "lab_universe": lab_names,
            "sdg_route": "B_siris (sdg_siris.parquet)",
        },
        notes="Pass 5 (S3), ruling R16/plan P3: thm_frontier_labs (lab x frontier context, field-"
              "standardised via a single whole-corpus reference field-mix) and thm_sdg_labs "
              "(lab x SDG, SIRIS-B route). No peer context on either (crossing != comparing, owner's "
              "rule). Both reconciliation identities verified exactly -- see module docstring + "
              "progress/S3_data_ext.md.",
    )
    append_summary(snapshot, "47b_build_crossings", [
        f"- `thm_frontier_labs`: {len(thm_frontier_labs):,} rows (69 labs x 2 conf_states)",
        f"- `thm_sdg_labs`: {len(thm_sdg_labs):,} rows (69 labs x 16 SDGs x 2 conf_states)",
        f"- reconciliation 1 (works_n vs ul_labs.works, per lab): PASS, 69/69",
        f"- reconciliation 2 (union-of-labs tagged set vs sdg_siris distinct tagged): PASS, "
        f"{len(union_tagged):,} == {len(tagged_ids_global):,}",
    ])
    print("\ndone.")


if __name__ == "__main__":
    main()
