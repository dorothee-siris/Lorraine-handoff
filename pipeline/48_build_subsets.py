"""48_build_subsets.py -- dim_subsets / work_subsets / subset_works / dim_artifact_topics
(Foundry rev 3.1, Assembly Line W1: docs/foundry/data_foundation.yaml producers.48_build_subsets.py).

PM1 "curated corpus-subset mechanic": one small registry (dim_subsets) + a work x subset
membership table (work_subsets) + a metadata-bearing publications-drill source (subset_works),
plus the ARTIFACT-FLAG topic dictionary (dim_artifact_topics). Every other builder in this pass
(46/47/45b) imports `lib.artifact.flag_works`/`load_bad_topics` rather than re-deriving the flag.

THREE active perimeter subsets this run:
  all            -- the whole corpus (no work_subsets rows -- would just be every work, for no
                     benefit; dim_subsets.n_works carries the total instead).
  in_isite       -- the canonical I-SITE hand DOI list (config.isite.doi_list_file via
                     works_master.In_ISITE). 1,839 works (== works_master.In_ISITE.sum()).
  in_isite_award -- the OpenAlex-award cross-check family (NOT works_master.In_ISITE_openalex_award,
                     which is a narrower award_id==G3172997804 match worth only 749 -- see
                     "AWARD CONSTRUCTION" below). 808 works, of which 32 are NOT on the canonical
                     hand list (docs/indicator_plan_FINAL.md PM5: "award-trace cross-check column
                     ships now (808 works, 5 spelling variants)").
Plus two STUB rows (status=stub, no work_subsets rows) reserving the PM5 (programme corpora) and
PM6 (ORCID-roster) mechanic slots for the workshop-gated lists that do not exist yet.

AWARD CONSTRUCTION (must reproduce exactly -- 808, not 749 or 801)
  The three attempts on file, cheapest first:
    v1: match on the opaque `award_id` OpenAlex field -> 0 (wrong field; the human-readable code
        lives in `funder_award_id`).
    v2: regex `LUE|IDEX|ISITE` on funder_award_id -> 1,086 (wrong -- sweeps OTHER universities'
        IDEX grants, e.g. IDEX UGA, Paris-Saclay; caught by the Wind Tunnel).
    v3 (THIS ONE, verified against reports/lab_thematic_probes.py's P5 block -- the actual
        award-matching probe on file; the sprint dispatch names reports/lab_pass3_probes.py, which
        only carries P1-P4 in this repo, but lab_thematic_probes.py's P5 is the block that
        reproduces CHALLENGE_MEMO_pass2.md's #23 finding to the digit and is cited there verbatim
        ("funder_award_id OR display-name ISITELUE, upper-cased, unicode-dash-normalised") --
        cross-checked live against the 2026-08-11 snapshot before writing this file: 808 works,
        32-work delta): match `funder_award_id` (own-stem scoped to Lorraine's ANR code family,
        `15-IDEX-0004` / `15-IDEX-04-LUE`, never the generic `IDEX` token) OR `award_display_name`
        containing `ISITELUE`, both upper-cased and Unicode-hyphen-normalised first (award strings
        carry en/em-dashes and non-breaking variants on 1,300+ rows -- a naive `-` regex misses
        them and silently undercounts).
  `works_master.In_ISITE_openalex_award` (749) is the SUPERSEDED, narrower construction (exact
  award_id equality to config.isite.openalex_award_id only) -- data_foundation.yaml's own
  canonical_counts note says so; that column is NOT rebuilt here, this script computes its own
  cross-check set independently from corpus_funding.

Usage: python pipeline/48_build_subsets.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.artifact import flag_works, load_bad_topics_table  # noqa: E402
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
CONFIG = load_config(ROOT)

# ---- award-string normalisation (own-stem scoped -- see module docstring "AWARD CONSTRUCTION") --
_DASH_VARIANTS = re.compile(r"[‐‑‒–—―−]")
_WHITESPACE = re.compile(r"\s+")
# ANR-15-IDEX-0004 = "Isite LUE" (config.isite.openalex_award_id's own award code family). Scoped
# to Lorraine's OWN stem -- never the bare "IDEX" token, which is generic across every French
# I-SITE/IDEX site and would sweep other universities' grants (Wind Tunnel catch, v2 above).
_ISITE_AWARD_CODE = re.compile(r"15-IDEX-0004|15-IDEX-?04-?LUE")
_ISITE_DISPLAY_NAME = "ISITELUE"


def _norm(value: object) -> str:
    text = str(value).upper()
    text = _DASH_VARIANTS.sub("-", text)
    return _WHITESPACE.sub("", text)


def award_trace_works(corpus_funding: pd.DataFrame) -> set[str]:
    """The 808-work I-SITE award-trace cross-check set (module docstring "AWARD CONSTRUCTION")."""
    code_col = "funder_award_id"
    ncode = corpus_funding[code_col].map(_norm)
    ndisp = corpus_funding["award_display_name"].map(_norm)
    mask = ncode.str.contains(_ISITE_AWARD_CODE, na=False, regex=True) | ndisp.str.contains(_ISITE_DISPLAY_NAME, na=False)
    return set(corpus_funding.loc[mask, "work_id"])


def counts_for(mask: pd.Series, works: pd.DataFrame, flagged: pd.Series) -> dict:
    """n_works / n_works_noconf / n_works_xa / n_works_noconf_xa for one subset's work mask."""
    sub_conf = works.loc[mask, "is_conference"]
    sub_flag = flagged.loc[mask]
    return {
        "n_works": int(mask.sum()),
        "n_works_noconf": int((~sub_conf).sum()),
        "n_works_xa": int((~sub_flag).sum()),
        "n_works_noconf_xa": int((~sub_flag & ~sub_conf).sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    print(f"snapshot {snapshot.name}: building dim_subsets / work_subsets / subset_works / "
          f"dim_artifact_topics")

    # ---------------------------------------------------------------------------------- inputs
    works = pd.read_parquet(tables / "works_master.parquet", columns=[
        "work_id", "doi", "title", "publication_year", "type", "is_conference",
        "In_ISITE", "primary_topic_id",
    ])
    corpus_topics = pd.read_parquet(tables / "corpus_topics.parquet",
                                    columns=["work_id", "topic_id", "is_primary"])
    corpus_funding = pd.read_parquet(tables / "corpus_funding.parquet")
    n_corpus = len(works)
    print(f"  corpus works: {n_corpus:,}")

    # ---------------------------------------------------------------------- artifact flag (P4)
    flag_series = flag_works(corpus_topics, root=ROOT)
    flagged = works["work_id"].map(flag_series).fillna(False).astype(bool)
    flagged.index = works.index
    n_flagged = int(flagged.sum())
    print(f"  artifact-flag (primary topic on the 811-topic exclusion list): {n_flagged:,} works")
    assert n_flagged == 4106, f"flag_works primary-flag count drifted: {n_flagged} != 4,106 (F0-P4 golden)"

    # ----------------------------------------------------------------------- in_isite (doi_list)
    canon_mask = works["In_ISITE"].astype(bool)
    n_in_isite = int(canon_mask.sum())
    print(f"  in_isite (canonical hand DOI list): {n_in_isite:,} works")
    assert n_in_isite == 1839, f"works_master.In_ISITE count drifted: {n_in_isite} != 1,839 (canonical_counts.in_isite_works)"

    # --------------------------------------------------------------------- in_isite_award (award)
    award_works = award_trace_works(corpus_funding)
    award_mask = works["work_id"].isin(award_works)
    n_award = int(award_mask.sum())
    print(f"  in_isite_award (ANR award-trace cross-check): {n_award:,} works")
    assert n_award == 808, f"award-trace construction drifted: {n_award} != 808 (canonical_counts.isite_award_works)"
    assert n_award == len(award_works), "every award-trace work must resolve inside works_master (corpus_funding is corpus-scoped)"

    delta_works = award_works - set(works.loc[canon_mask, "work_id"])
    n_delta = len(delta_works)
    print(f"  in_isite_award minus canonical in_isite (award-only, not on the hand list): {n_delta}")
    assert n_delta == 32, f"award-minus-canonical delta drifted: {n_delta} != 32 (plan PM5 note)"

    # ---------------------------------------------------------------------------- dim_subsets
    all_counts = counts_for(pd.Series(True, index=works.index), works, flagged)
    in_isite_counts = counts_for(canon_mask, works, flagged)
    award_counts = counts_for(award_mask, works, flagged)
    today = dt.date.today().isoformat()

    dim_subsets_rows = [
        {
            "subset_id": "all", "label_fr": "Corpus complet", "label_en": "Full corpus",
            "kind": "baseline", "owner": "pipeline", "source_file": "works_master.parquet",
            "vintage_date": snapshot.name, **all_counts, "defi_rollup": pd.NA,
            "status": "active", "snapshot_date": snapshot.name,
        },
        {
            "subset_id": "in_isite", "label_fr": "Périmètre I-SITE (liste DOI)",
            "label_en": "I-SITE perimeter (DOI list)", "kind": "isite_list",
            "owner": "GT Indicateurs", "source_file": CONFIG["isite"]["doi_list_file"],
            "vintage_date": _file_vintage(CONFIG["isite"]["doi_list_file"]),
            **in_isite_counts, "defi_rollup": pd.NA, "status": "active",
            "snapshot_date": snapshot.name,
        },
        {
            "subset_id": "in_isite_award", "label_fr": "Périmètre I-SITE (trace subvention ANR)",
            "label_en": "I-SITE perimeter (ANR award cross-check)",
            "kind": "isite_award_crosscheck", "owner": "GT Indicateurs",
            "source_file": "corpus_funding.parquet", "vintage_date": snapshot.name,
            **award_counts, "defi_rollup": pd.NA, "status": "active",
            "snapshot_date": snapshot.name,
        },
        {
            "subset_id": "programme_pending", "label_fr": "Corpus par programme (liste à venir)",
            "label_en": "Programme corpora (list pending)", "kind": "programme",
            "owner": "workshop (client CODIR matrix)", "source_file": pd.NA,
            "vintage_date": pd.NA, "n_works": pd.NA, "n_works_noconf": pd.NA,
            "n_works_xa": pd.NA, "n_works_noconf_xa": pd.NA, "defi_rollup": pd.NA,
            "status": "stub", "snapshot_date": snapshot.name,
        },
        {
            "subset_id": "orcid_roster_pending", "label_fr": "Périmètre par roster ORCID (à venir)",
            "label_en": "ORCID-roster perimeter (pending)", "kind": "orcid_roster",
            "owner": "workshop (client roster upload)", "source_file": pd.NA,
            "vintage_date": pd.NA, "n_works": pd.NA, "n_works_noconf": pd.NA,
            "n_works_xa": pd.NA, "n_works_noconf_xa": pd.NA, "defi_rollup": pd.NA,
            "status": "stub", "snapshot_date": snapshot.name,
        },
    ]
    dim_subsets = pd.DataFrame(dim_subsets_rows)[[
        "subset_id", "label_fr", "label_en", "kind", "owner", "source_file", "vintage_date",
        "n_works", "n_works_noconf", "n_works_xa", "n_works_noconf_xa", "defi_rollup",
        "status", "snapshot_date",
    ]]
    for col in ("n_works", "n_works_noconf", "n_works_xa", "n_works_noconf_xa"):
        dim_subsets[col] = dim_subsets[col].astype("Int64")  # D53 NULL-never-0 on the stub rows
    for col in ("label_fr", "label_en", "kind", "owner", "source_file", "vintage_date",
                "defi_rollup", "status", "snapshot_date", "subset_id"):
        dim_subsets[col] = dim_subsets[col].astype("string")
    assert dim_subsets["subset_id"].is_unique, "dim_subsets.subset_id must be unique"

    # --------------------------------------------------------------------------- work_subsets
    work_subsets = pd.concat([
        pd.DataFrame({"work_id": works.loc[canon_mask, "work_id"].values,
                      "subset_id": "in_isite", "evidence": "doi_list"}),
        pd.DataFrame({"work_id": works.loc[award_mask, "work_id"].values,
                      "subset_id": "in_isite_award", "evidence": "award"}),
    ], ignore_index=True)
    work_subsets = work_subsets.astype({"work_id": "string", "subset_id": "string", "evidence": "string"})
    assert (work_subsets["subset_id"] == "in_isite").sum() == 1839
    assert (work_subsets["subset_id"] == "in_isite_award").sum() == 808
    orphans = set(work_subsets["subset_id"]) - set(dim_subsets["subset_id"])
    assert not orphans, f"work_subsets carries subset_id(s) absent from dim_subsets: {orphans}"

    # --------------------------------------------------------------------------- subset_works
    meta = works.set_index("work_id")[["publication_year", "title", "doi", "type", "is_conference"]]
    meta_flag = flagged.copy()
    meta_flag.index = works["work_id"].values
    subset_works = work_subsets[["subset_id", "work_id"]].copy()
    subset_works = subset_works.join(meta, on="work_id")
    subset_works = subset_works.rename(columns={"publication_year": "year"})
    subset_works["in_isite"] = subset_works["work_id"].isin(set(works.loc[canon_mask, "work_id"]))
    subset_works["artifact_flag"] = subset_works["work_id"].map(meta_flag).fillna(False).astype(bool)
    subset_works = subset_works[[
        "subset_id", "work_id", "year", "title", "doi", "type", "is_conference", "in_isite",
        "artifact_flag",
    ]]
    subset_works = subset_works.astype({
        "subset_id": "string", "work_id": "string", "year": "int32", "title": "string",
        "doi": "string", "type": "string", "is_conference": "bool", "in_isite": "bool",
        "artifact_flag": "bool",
    })
    subset_works = subset_works.sort_values("subset_id").reset_index(drop=True)

    orphans = set(subset_works["subset_id"]) - set(dim_subsets["subset_id"])
    assert not orphans, f"subset_works carries subset_id(s) absent from dim_subsets: {orphans}"
    award_rows = subset_works[subset_works["subset_id"] == "in_isite_award"]
    assert len(award_rows) == 808, f"subset_works in_isite_award rows: {len(award_rows)} != 808"
    n_delta_flagged = int((~award_rows["in_isite"]).sum())
    assert n_delta_flagged == 32, (
        f"subset_works in_isite_award rows with in_isite==False (the award-only delta): "
        f"{n_delta_flagged} != 32 -- P-V4's 32-work tile reads exactly this filtered count"
    )
    print(f"  subset_works: {len(subset_works):,} rows (in_isite {canon_mask.sum():,} + "
          f"in_isite_award {n_award:,}); in_isite_award rows with in_isite==False: {n_delta_flagged} "
          f"(the 32-work award-only delta, identifiable via the in_isite cross-flag)")

    # ------------------------------------------------------------------------ dim_artifact_topics
    dim_artifact_topics = load_bad_topics_table(ROOT)
    dim_artifact_topics["reason_label_fr"] = "hors référentiel mondial — limite du classifieur"
    dim_artifact_topics["snapshot_date"] = snapshot.name
    dim_artifact_topics = dim_artifact_topics[["topic_id", "topic_name", "reason_label_fr", "snapshot_date"]]
    dim_artifact_topics = dim_artifact_topics.astype({
        "topic_id": "string", "topic_name": "string", "reason_label_fr": "string",
        "snapshot_date": "string",
    })
    assert len(dim_artifact_topics) == 811, f"dim_artifact_topics: {len(dim_artifact_topics)} != 811"
    assert dim_artifact_topics["topic_id"].is_unique, "dim_artifact_topics.topic_id must be unique"

    # ------------------------------------------------------------------------------- write out
    compression = CONFIG["storage"]["compression"]
    out_dim_subsets = tables / "dim_subsets.parquet"
    out_work_subsets = tables / "work_subsets.parquet"
    out_subset_works = tables / "subset_works.parquet"
    out_dim_artifact_topics = tables / "dim_artifact_topics.parquet"

    dim_subsets.to_parquet(out_dim_subsets, index=False, compression=compression)
    work_subsets.to_parquet(out_work_subsets, index=False, compression=compression)
    # sorted by subset_id, rg=5000 (the Foundry lazy-file rule; trivially 1 group at this size --
    # the Class-1 row-group floor num_row_groups >= n_rows/10000 still holds: 1 >= 0.27).
    subset_works.to_parquet(out_subset_works, index=False, compression=compression, row_group_size=5000)
    dim_artifact_topics.to_parquet(out_dim_artifact_topics, index=False, compression=compression)

    print(f"\nwrote dim_subsets.parquet ({len(dim_subsets)} rows)")
    print(dim_subsets.drop(columns=["label_fr", "label_en"]).to_string(index=False))
    print(f"\nwrote work_subsets.parquet ({len(work_subsets):,} rows)")
    print(f"wrote subset_works.parquet ({len(subset_works):,} rows, "
          f"{_row_groups(out_subset_works)} row group(s))")
    print(f"wrote dim_artifact_topics.parquet ({len(dim_artifact_topics)} rows)")

    Manifest(snapshot).record_step(
        "48_build_subsets",
        counts={
            "dim_subsets_rows": len(dim_subsets),
            "work_subsets_rows": len(work_subsets),
            "subset_works_rows": len(subset_works),
            "dim_artifact_topics_rows": len(dim_artifact_topics),
            "in_isite_works": n_in_isite,
            "in_isite_award_works": n_award,
            "in_isite_award_minus_canonical": n_delta,
            "artifact_flag_primary_works": n_flagged,
        },
        files=[out_dim_subsets, out_work_subsets, out_subset_works, out_dim_artifact_topics],
        params={
            "award_construction": "funder_award_id own-stem (15-IDEX-0004 / 15-IDEX-04-LUE) OR "
                                   "award_display_name contains ISITELUE, both upper-cased + "
                                   "Unicode-dash-normalised (see module docstring)",
            "bad_topics_source": "inputs/manual/OA_bad_topics.xlsx (W1 copy-in, byte-identical to "
                                  "Research Portfolio Framework original)",
        },
        notes="Foundry rev 3.1 W1: foundation dims + shared lib.artifact (load_bad_topics/"
              "flag_works/check_completeness). W2/W3/W4 consume lib.artifact directly rather "
              "than re-deriving the flag.",
    )
    append_summary(snapshot, "48_build_subsets", [
        f"- `dim_subsets`: {len(dim_subsets)} rows (all/in_isite/in_isite_award active + 2 stub)",
        f"- `work_subsets`: {len(work_subsets):,} rows (in_isite {n_in_isite:,}, in_isite_award {n_award:,})",
        f"- `subset_works`: {len(subset_works):,} rows; in_isite_award award-only delta {n_delta_flagged}",
        f"- `dim_artifact_topics`: {len(dim_artifact_topics)} rows",
        f"- artifact-flag primary-topic works: {n_flagged:,} (11.15%)",
    ])
    print("\ndone.")


def _file_vintage(manual_filename: str) -> str:
    path = ROOT / CONFIG["paths"]["manual_inputs"] / manual_filename
    if not path.is_file():
        return pd.NA
    return dt.date.fromtimestamp(path.stat().st_mtime).isoformat()


def _row_groups(path: Path) -> int:
    import pyarrow.parquet as pq
    return pq.ParquetFile(path).num_row_groups


if __name__ == "__main__":
    main()
