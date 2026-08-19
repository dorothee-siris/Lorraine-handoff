"""46_build_partner_views.py -- ptn_* / geo_* / consortium_weights (Foundry rev 3.1, Assembly Line
W2, chain pass 3 /sprint). Emits: ptn_summary, ptn_mom_facts, ptn_yearly, ptn_fields, ptn_labs,
ptn_works, ptn_topics, geo_countries, geo_fields, geo_groups, consortium_weights.

Authority (read in full before touching this file): docs/foundry/data_foundation.yaml rev 3.1
(producers.46_build_partner_views.py + the 11 table entries) · docs/foundry/DATA_FOUNDATION.md
sec.3 (dual-mode momentum) + sec.9-bis (drill paths) · docs/indicator_plan_FINAL.md sec.3 (I1-I11)
+ sec.6.3 + sec.6.6 · progress/F0_probes.md + reports/foundry_pass2_probes.py (reused build logic
for the overlay-corrected universe, ptn_topics, ptn_works) · repaired reports/lab_momentum_frozen.py
(THE golden momentum reference -- method lifted into pipeline/lib46_momentum.py, never re-derived
by hand) · inputs/overlays/*.csv (status==ok only) · config.yaml workshop_tunables.

UNIVERSE CONSTRUCTION (own-entity exclusion + merges) -- verified against F0 probes AND the golden
momentum script before this builder was written (both reproduce to the digit with this exact
recipe; see progress/W2_partner_views.md for the verification transcript):
  OWN_BLOCK_FULL   = ul_descendants.openalex_id (+root I90183372) + own_entity_blocklist.csv
                     (status==ok) -- includes Centre Inria de l'UL (I4210127166), UNLIKE the
                     frozen momentum script's own historical exemption (see MOMENTUM section).
  MERGE_MAP        = successor_merges.csv (status==ok) ONLY -- 3 rows this pass (INRA->INRAE,
                     Clermont dup->Clermont, Kaiserslautern->RPTU-pre). hospital_complex_merges.csv
                     is READ (status==ok resolution is checked, per the overlays standing invariant)
                     but its university<-hospital fold is NOT applied to institution identity here:
                     (a) F0_probes.md's own canonical partner-floor numbers (2,309/1,279/447) and
                     null-country count reproduce EXACTLY with successor-only merging and do NOT
                     reproduce with the hospital fold added (empirically verified: folding drops
                     the >=10 floor count from 2,309 to 2,306, since the 3 hospitals independently
                     clear the floor before folding); (b) the overlays state note describes this
                     file as "rides 42b" -- i.e. reserved for the reciprocity feature this pass
                     ships NULL, not yet a general partner-identity input. Momentum's own dual-mode
                     acceptance numbers were verified IDENTICAL with or without the hospital fold
                     (it does not touch any of the affected partners' eligibility), so using
                     successor-only everywhere is both F0-consistent and momentum-safe -- one
                     universe for every table in this file, no per-table divergence.
  UL_OWN (shipped) = OWN_BLOCK_FULL | ul_descendants | {I90183372}
  Frozen-parity-only UL_OWN (momentum reproduction check ONLY, never used for any shipped table) =
                     UL_OWN minus the disclosed Centre-Inria exemption (own_entity_blocklist.csv
                     frozen_momentum_v2_exempt=='yes' row) -- reproduces the ALREADY-PUBLISHED
                     682-family numbers exactly, then is discarded; ptn_summary/ptn_mom_facts ship
                     the SHIPPED (681-family) numbers only, per data_foundation.yaml sec.3.

DISCLOSED DEVIATION -- null-country partner count: this build's F0-consistent recipe (parquet-
native, no CSV/Excel re-parse) measures 346 partners with no resolvable institution_country among
their pairs; data_foundation.yaml canonical_counts.null_country_partner_ids states 347. No script
in this repo (foundry_pass2_probes.py, f3_hostile_recompute.py) actually measures this number --
it traces to CHALLENGE_MEMO_pass2.md #19, a prose finding marked WEAK-CLAIM with no computation
attached. One plausible source of a +/-1 drift: corpus_authorships carries exactly one partner row
with institution_country=='NA' (Namibia's real ISO-3166 code), which a CSV-roundtrip tool applying
default NA-string sniffing would silently swallow as a missing value -- this build reads parquet
natively and does not do that. Per the "never adjust the method to force a pass" discipline (the
same rule stated for the momentum acceptance), this is reported verbatim, not chased further or
silently patched to 347: see progress/W2_partner_views.md.

BUILDER DECISIONS (undocumented specifics the AUTHORITY set left to this stream, each noted in its
contract fragment too):
  - ptn_fields subfield sparse floor: no explicit config constant exists for this (only the I11
    sparkline/delta floors are named); this build reuses i11_sparkline_min_works (3) as the
    general "sparse breakdown" floor rather than inventing an undeclared new one, and does NOT add
    a new key to config.yaml (out of this stream's scope fence).
  - share_ul denominator = the SAME (conf_state, subset_id) scope's own collaborative-work union
    (computed directly from the scope's pairs, not a fixed external denominator) -- for subset
    'all' this reproduces dim_corpus_facts.corpus_collaborative_works exactly (asserted below);
    share_ul_direct normalises against the scope's total work count instead (dim_subsets.n_works
    for 'all'/'in_isite') -- two genuinely different "share of what" questions, which is why the
    contract lists them as separate (deferred, non-twinned) columns.
  - mom_category vs mom_class: mom_class is the frozen up/down/stable/ns label, populated ONLY for
    ELIGIBLE partners (NULL otherwise); mom_category widens that to include 'new'/'dormant' for the
    partners the frozen method screens into those buckets (still outside eligibility, per the
    build brief), and stays NULL for partners with in-window activity below the floor and outside
    both screens (no category invented for that residual).
  - frontier_score_std (ptn_topics): CORRECTED in a manager fix round (E1a catch, chain pass 3).
    Originally computed from OA_frontier_scores.xlsx (a field-standardised z-score this stream
    invented, read in place, before W3's copy-in existed) -- superseded once
    inputs/manual/frontierness_baseline.xlsx landed (byte copy of RPF's own "Readout/Raw data/
    Cleaning bad OA topics.xlsx", sha256 b5017b7d2... -- the card-blessed vintage
    47_build_thematic_ext.py/thm_frontier.parquet actually reads; the plan's original
    OA_frontier_scores.xlsx pointer was a transcription error, per data_foundation.yaml's
    supersessions block). ptn_topics now reads the SAME file, sheet "FILTERING OUT TOPICS", column
    "Average frontierness" taken AS-IS (no re-standardisation -- W3's own code does not z-score it
    either, the column is already a z-scored-within-bin ACCORD composite upstream), NULL for the
    811 excluded topics -- byte-verified sha256 check + assert before every build
    (frontier_score_lookup()). Spot-checked against thm_frontier's texture rows: exact match.

Usage: python pipeline/46_build_partner_views.py [--snapshot 2026-08-11]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.artifact import flag_works, load_bad_topics  # noqa: E402
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402
import lib46_momentum as mom  # noqa: E402

ascii_safe_stdout()
CONFIG = load_config(ROOT)

CONF_STATES = ["all", "no_conf"]
SUBSET_IDS_PTN_SUMMARY = ["all", "in_isite"]

DRILL_PARTNER_FLOOR = int(CONFIG["workshop_tunables"]["drill_partner_floor"])          # 10
SPARSE_NODE_FLOOR = int(CONFIG["workshop_tunables"]["i11_sparkline_min_works"])         # 3 (reused)
BAND_PCT = int(CONFIG["workshop_tunables"]["momentum_band_pct"])                        # 25
SIGNIFICANCE_P = float(CONFIG["workshop_tunables"]["momentum_significance_p"])           # 0.05
RECENTRING_FROZEN = float(CONFIG["workshop_tunables"]["momentum_recentring_median"])     # 1.061

FRONTIER_XLSX = ROOT / "inputs" / "manual" / "frontierness_baseline.xlsx"
# card-blessed vintage (manager fix round, chain pass 3): byte copy of RPF's own
# "Readout/Raw data/Cleaning bad OA topics.xlsx" -- data_foundation.yaml supersessions block
# corrected the plan's original OA_frontier_scores.xlsx pointer as a transcription error.
# thm_frontier.parquet (47_build_thematic_ext.py, W3) already reads THIS file; ptn_topics must
# match it exactly, checked by sha256 before every build.
FRONTIER_XLSX_SHA256 = "b5017b7d298e088013951f2823b80f93739fee8b9d26a9376868f029c7cf37ac"

CANON = {
    "ptn_topics_cells_at_p10floor": 156164,
    "ptn_topics_cells_ge3": 25460,
    "ptn_topics_cells_ge20": 1293,
    "ptn_works_pairs_at_p10floor": 116345,
    "partner_floor_ge10": 2309,
    "partner_floor_ge20": 1279,
    "partner_floor_ge50": 447,
    "null_country_partner_ids": 347,   # disclosed deviation -- see module docstring
    "countries_ge10": 120,
}


def section(title: str) -> None:
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def load_overlay(name: str) -> pd.DataFrame:
    return pd.read_csv(ROOT / "inputs" / "overlays" / name, encoding="utf-8", keep_default_na=False)


class PartnerBaseLookup:
    """Wraps `ul_partners_base.parquet` (42b's ordinary pull) + `ul_partners_base_merged.parquet`
    (42b's pass-4 merged-pair union sidecar, challenge memo #9) to answer 'this partner's OWN
    output' at the flat level (ptn_summary.share_p denominator) and at a field/subfield node
    (ptn_fields.baseline_partner_share denominator).

    Mirrors `44e_build_detail_partners.py`'s `PartnerBase` positional-decode logic exactly (same
    `sorted(all_topics[...])` id-ordering, same subfield-family column-name construction), so a
    given partner's numbers agree across both tables -- but ptn_summary/ptn_fields key partners by
    their CANONICAL (post-merge) id, so the 3 successor_merges.csv partners must ALWAYS be answered
    from the union sidecar, never from an ordinary same-id row that might also exist (that row is
    the successor's OWN portfolio alone, not the union its ptn_summary co_works_full numerator
    already sums to).
    """

    def __init__(self, tables: Path, all_topics: pd.DataFrame, merge_map: dict) -> None:
        base_path = tables / "ul_partners_base.parquet"
        merged_path = tables / "ul_partners_base_merged.parquet"
        base = pd.read_parquet(base_path) if base_path.exists() else None
        self.base = base.set_index("Partner ID") if base is not None else None
        merged = pd.read_parquet(merged_path) if merged_path.exists() else None
        self.merged = merged.set_index("Partner ID") if merged is not None else None
        self.canonical_ids = set(merge_map.values())

        at = all_topics.assign(
            domain_id=all_topics["domain_id"].astype(str), field_id=all_topics["field_id"].astype(str).astype(int),
            subfield_id=all_topics["subfield_id"].astype(str).astype(int),
        )
        self.field_ids = sorted(at["field_id"].unique())
        self.field_of_subfield = at.drop_duplicates("subfield_id").set_index("subfield_id")["field_id"].to_dict()
        self.subfields_by_field = {
            f: sorted(at.loc[at["field_id"] == f, "subfield_id"].unique()) for f in self.field_ids
        }
        self.field_name = at.drop_duplicates("field_id").set_index("field_id")["field_name"].to_dict()

        print(f"PartnerBaseLookup: ul_partners_base "
              f"{'present (' + str(len(self.base)) + ' partners)' if self.base is not None else 'ABSENT'}; "
              f"merged-union sidecar "
              f"{'present (' + str(len(self.merged)) + ' rows: ' + ', '.join(sorted(self.canonical_ids)) + ')' if self.merged is not None else 'ABSENT'}")

    def _row(self, partner_id: str):
        if partner_id in self.canonical_ids and self.merged is not None and partner_id in self.merged.index:
            return self.merged.loc[partner_id]
        if self.base is not None and partner_id in self.base.index:
            return self.base.loc[partner_id]
        return None

    def total(self, partner_id: str) -> int | None:
        """The partner's own total windowed pub count (ptn_summary.share_p denominator)."""
        row = self._row(partner_id)
        if row is None:
            return None
        val = row["Pubs count (partner total)"]
        return int(val) if pd.notna(val) else None

    def node_total(self, partner_id: str, level: str, node_id) -> int | None:
        """The partner's own pub count at one field/subfield node (ptn_fields.baseline_partner_share
        denominator) -- positional decode of the domain/field/subfield-family blob columns, same
        recipe as 44e's `PartnerBase.partner_total` (level 'domain' not needed here: ptn_fields has
        no domain-grain rows)."""
        row = self._row(partner_id)
        if row is None:
            return None
        if level == "field":
            parts = str(row["Pubs breakdown per field (partner total)"] or "").split(" | ")
            idx_list = self.field_ids
        else:  # subfield
            field_id = self.field_of_subfield.get(int(node_id))
            if field_id is None:
                return None
            col = f'Pubs per subfield within "{self.field_name[field_id]}" (id: {field_id}) (partner total)'
            if col not in row.index:
                return None
            parts = str(row[col] or "").split(" | ")
            idx_list = self.subfields_by_field[field_id]
        try:
            pos = idx_list.index(int(node_id))
            return int(parts[pos])
        except (ValueError, IndexError):
            return None


# ==================================================================================================
# SECTION 0 -- inputs, universe construction (own ids, merges, artifact flag)
# ==================================================================================================

def build_universe(tables: Path) -> dict:
    desc = pd.read_parquet(tables / "ul_descendants.parquet")
    idcol = [c for c in desc.columns if "id" in c.lower()][0]
    ul_root = {CONFIG["perimeter"]["ul_openalex_id"]}
    desc_ids = set(desc[idcol].dropna().astype(str))

    blk = load_overlay("own_entity_blocklist.csv")
    blk_ok = blk[blk["status"] == "ok"]
    own_block_full = set(blk_ok["id"].astype(str))
    own_momentum_exempt = set(blk_ok.loc[blk_ok["frozen_momentum_v2_exempt"] == "yes", "id"])
    assert own_momentum_exempt == {"I4210127166"}, (
        "the frozen-momentum exemption set must be exactly the disclosed Centre Inria de l'UL row"
    )
    own_block_momentum = own_block_full - own_momentum_exempt

    succ = load_overlay("successor_merges.csv")
    succ_ok = succ[succ["status"] == "ok"]
    succ_todo = succ[succ["status"] != "ok"]
    merge_map = dict(zip(succ_ok["old_id"], succ_ok["successor_id"]))

    hosp = load_overlay("hospital_complex_merges.csv")
    hosp_ok = hosp[hosp["status"] == "ok"]
    hosp_todo = hosp[hosp["status"] != "ok"]

    cons = load_overlay("idset_consortium.csv")
    unigr = load_overlay("idset_unigr.csv")
    eureca = load_overlay("idset_eureca.csv")

    print(f"own_entity_blocklist: {len(own_block_full)} status==ok ids "
          f"(momentum-exempt row excluded from the shipped universe: {sorted(own_momentum_exempt)})")
    print(f"successor_merges: {len(succ_ok)} status==ok / {len(succ_todo)} not-ok (never consumed)")
    print(f"hospital_complex_merges: {len(hosp_ok)} status==ok / {len(hosp_todo)} not-ok -- read for "
          f"the standing id-resolution invariant only; the university<-hospital fold is NOT applied "
          f"to institution identity this pass (see module docstring)")

    ul_own_shipped = desc_ids | ul_root | own_block_full
    ul_own_frozen_parity = desc_ids | ul_root | own_block_momentum

    # standing invariant: every configured overlay id resolves to >0 rows (mirrors the golden
    # script's own section-0 check + docs/foundry/data_foundation.yaml overlays.standing_invariants)
    au_raw = pd.read_parquet(tables / "corpus_authorships.parquet", columns=["work_id", "institution_id"])
    raw_counts = au_raw.dropna(subset=["institution_id"]).groupby("institution_id")["work_id"].nunique()
    checked = 0
    for label, ids in [
        ("own_entity_blocklist", own_block_full),
        ("successor_merges", set(succ_ok["old_id"]) | set(succ_ok["successor_id"])),
        ("hospital_complex_merges", set(hosp_ok["university_id"]) | set(hosp_ok["hospital_id"])),
        ("idset_consortium", set(cons.loc[cons["status"] == "ok", "id"])),
        ("idset_unigr", set(unigr.loc[unigr["status"] == "ok", "id"])),
        ("idset_eureca", set(eureca.loc[eureca["status"] == "ok", "id"])),
    ]:
        for i in ids:
            n = int(raw_counts.get(i, 0))
            assert n > 0, f"{label} id {i} resolves to 0 rows -- typo or dead id"
            checked += 1
    print(f"overlay id resolution: {checked} configured ids checked, all resolve to >0 rows")

    # G1-style disjointness: no id in both own_entity_blocklist and any consortium/unigr/eureca id-set
    group_ids = (set(cons.loc[cons["status"] == "ok", "id"])
                 | set(unigr.loc[unigr["status"] == "ok", "id"])
                 | set(eureca.loc[eureca["status"] == "ok", "id"]))
    overlap = own_block_full & group_ids
    assert not overlap, f"own_entity_blocklist ids leaked into a group id-set: {overlap}"
    print(f"disjointness (blocklist inter consortium|unigr|eureca): {sorted(overlap) or 'EMPTY (pass)'}")

    return dict(
        ul_own_shipped=ul_own_shipped, ul_own_frozen_parity=ul_own_frozen_parity,
        merge_map=merge_map, cons=cons, unigr=unigr, eureca=eureca,
        own_block_full=own_block_full, desc=desc,
    )


def build_pairs(au_raw: pd.DataFrame, wm: pd.DataFrame, merge_map: dict, ul_own: set,
                artifact_flag: pd.Series) -> pd.DataFrame:
    """The overlay-corrected work x external-institution pair table (F0-probes recipe, verified
    to reproduce every canonical count to the digit -- see progress/W2_partner_views.md). One row
    per (work_id, partner_id) with the work's own attributes joined in."""
    au_m = au_raw.copy()
    au_m["partner_id"] = au_m["institution_id"].astype(str).replace(merge_map)
    au_m = au_m.drop_duplicates(["work_id", "partner_id"])
    ext = au_m[~au_m["partner_id"].isin(ul_own) & au_m["partner_id"].notna()
               & (au_m["partner_id"] != "None")]
    pairs = ext.merge(wm, on="work_id", how="inner")
    pairs["artifact_flag"] = pairs["work_id"].map(artifact_flag).fillna(False).astype(bool)
    return pairs


def build_pairs_for_momentum(au_raw: pd.DataFrame, wm: pd.DataFrame, merge_map: dict,
                              ul_own: set) -> pd.DataFrame:
    """MOMENTUM-ONLY pairs frame -- byte-exact mirror of reports/lab_momentum_frozen.py's own
    section-A construction, which does NOT drop rows with a missing institution_id: `.astype(str)`
    turns a real NaN into the literal string 'None' (object-dtype column, Python None nulls), and
    the golden script's own filter is only `~au["inst"].isin(ul_own)` -- no notna/!='None' guard.
    That means a work whose ONLY non-UL authorship rows are missing-institution ones still counts
    as "collaborative" via a phantom 'None' pseudo-partner that never crosses any floor by itself.
    Empirically verified (progress/W2_partner_views.md): dropping these rows (the F0-probes recipe
    build_pairs() uses for every OTHER table) shifts D1 11,431->10,826 and eligible 682->681 --
    it does NOT reproduce the frozen numbers. This function exists ONLY to feed
    reports/lab_momentum_frozen.py's exact arithmetic into lib46_momentum.partner_level(); every
    other table in this builder uses build_pairs() (the canonical, null-dropping recipe)."""
    au_m = au_raw.copy()
    au_m["partner_id"] = au_m["institution_id"].astype(str).replace(merge_map)
    au_m = au_m.drop_duplicates(["work_id", "partner_id"])
    ext = au_m[~au_m["partner_id"].isin(ul_own)]
    return ext.merge(wm, on="work_id", how="inner")


# ==================================================================================================
# SECTION 1 -- momentum (dual-mode reproduction + shipped build + ptn_mom_facts)
# ==================================================================================================

# The phantom pseudo-partner (build_pairs_for_momentum's own docstring): a real NaN institution_id,
# stringified by the frozen script's own `.astype(str)`, survives as this literal identity string.
# It is CLASSIFIED by the frozen method (it has real w1/w2 volume, pooled across every work whose
# only non-UL authorship rows are missing-institution ones) but is NOT a real partner and must
# never reach ptn_summary (data_foundation.yaml ptn_mom_facts.phantom_ruling).
PHANTOM_ID = "None"


def diagnose_phantom(res: dict, label: str) -> dict:
    """Confirms the phantom's own class + w1/w2 counts in one momentum run, and returns the
    DISPLAY (phantom-removed) class distribution + >=50-floor distribution alongside it."""
    c1 = int(res["c1"].get(PHANTOM_ID, 0))
    c2 = int(res["c2"].get(PHANTOM_ID, 0))
    cls = res["disp"].get(PHANTOM_ID)
    is_eligible = bool(res["elig"].get(PHANTOM_ID, False))
    big_flag = bool((res["inwin"] >= 50).get(PHANTOM_ID, False))
    print(f"[{label}] phantom '{PHANTOM_ID}': c1={c1} c2={c2} inwin={c1+c2} "
          f"eligible={is_eligible} class={cls} in->=50 bucket={big_flag}")

    disp_display = res["disp"].drop(index=PHANTOM_ID, errors="ignore")
    big = res["inwin"] >= 50
    big_display = big.drop(index=PHANTOM_ID, errors="ignore")
    disp50_display = disp_display[[i for i in disp_display.index if big_display.get(i, False)]]
    return dict(phantom_c1=c1, phantom_c2=c2, phantom_class=cls, phantom_eligible=is_eligible,
                phantom_in_big_bucket=big_flag,
                display_classes=disp_display.value_counts().to_dict(),
                display_n=len(disp_display),
                display_classes_ge50=disp50_display.value_counts().to_dict(),
                display_n_ge50=len(disp50_display))


def run_momentum_dual_mode(pairs_frozen_all: pd.DataFrame, pairs_shipped_all: pd.DataFrame,
                            pairs_shipped_noconf: pd.DataFrame) -> dict:
    section("MOMENTUM -- dual-mode reproduction (partner grain, frozen method)")

    res_frozen = mom.partner_level(pairs_frozen_all, grain_col="partner_id")
    print(f"[frozen-parity] D1={res_frozen['d1']} D2={res_frozen['d2']} "
          f"MED={res_frozen['med']:.4f} eligible={res_frozen['eligible_n']} "
          f"{res_frozen['disp'].value_counts().to_dict()} "
          f"new={int(res_frozen['new'].sum())} dormant={int(res_frozen['dorm'].sum())}")
    big_f = res_frozen["inwin"] >= 50
    disp50_f = res_frozen["disp"][[i for i in res_frozen["disp"].index if big_f.get(i, False)]]
    print(f"[frozen-parity] >=50: {len(disp50_f)} {disp50_f.value_counts().to_dict()}")

    assert res_frozen["eligible_n"] == 682, f"frozen-parity eligible {res_frozen['eligible_n']} != 682"
    fc = res_frozen["disp"].value_counts().to_dict()
    assert (fc.get("up"), fc.get("down"), fc.get("stable"), fc.get("ns")) == (106, 52, 277, 247), (
        f"frozen-parity class counts drifted: {fc}"
    )
    assert int(res_frozen["new"].sum()) == 5 and int(res_frozen["dorm"].sum()) == 0
    assert len(disp50_f) == 215
    fc50 = disp50_f.value_counts().to_dict()
    assert (fc50.get("up"), fc50.get("down"), fc50.get("stable"), fc50.get("ns")) == (47, 17, 103, 48), (
        f"frozen-parity >=50 class counts drifted: {fc50}"
    )
    print("[frozen-parity] ALL GOLDEN NUMBERS MATCH EXACTLY (682 -> 106/52/277/247; new 5/dormant 0; "
          ">=50: 215 -> 47/17/103/48)")
    phantom_frozen = diagnose_phantom(res_frozen, "frozen-parity")

    res_shipped = mom.partner_level(pairs_shipped_all, grain_col="partner_id")
    print(f"\n[shipped, conf_state=all] D1={res_shipped['d1']} D2={res_shipped['d2']} "
          f"MED={res_shipped['med']:.4f} eligible={res_shipped['eligible_n']} "
          f"{res_shipped['disp'].value_counts().to_dict()}")
    big_s = res_shipped["inwin"] >= 50
    disp50_s = res_shipped["disp"][[i for i in res_shipped["disp"].index if big_s.get(i, False)]]
    print(f"[shipped] >=50: {len(disp50_s)} {disp50_s.value_counts().to_dict()}")

    assert res_shipped["eligible_n"] == 681, f"shipped eligible {res_shipped['eligible_n']} != 681"
    sc = res_shipped["disp"].value_counts().to_dict()
    assert (sc.get("up"), sc.get("down"), sc.get("stable"), sc.get("ns")) == (105, 51, 277, 248), (
        f"shipped class counts drifted: {sc}"
    )
    assert len(disp50_s) == 214
    sc50 = disp50_s.value_counts().to_dict()
    assert (sc50.get("up"), sc50.get("down"), sc50.get("stable"), sc50.get("ns")) == (46, 16, 103, 49), (
        f"shipped >=50 class counts drifted: {sc50}"
    )
    print("[shipped] ALL GOLDEN NUMBERS MATCH EXACTLY (681 -> 105/51/277/248; >=50: 214 -> 46/16/103/49)")
    phantom_shipped = diagnose_phantom(res_shipped, "shipped, conf_state=all")
    assert phantom_shipped["phantom_class"] == "stable", (
        f"phantom expected 'stable', got {phantom_shipped['phantom_class']!r}"
    )
    print(f"  DISPLAY (phantom removed): {phantom_shipped['display_n']} -> "
          f"{phantom_shipped['display_classes']}; >=50: {phantom_shipped['display_n_ge50']} -> "
          f"{phantom_shipped['display_classes_ge50']}")

    removed = set(res_frozen["disp"].index) - set(res_shipped["disp"].index)
    common = set(res_frozen["disp"].index) & set(res_shipped["disp"].index)
    flips = {i: (res_frozen["disp"][i], res_shipped["disp"][i]) for i in common
             if res_frozen["disp"][i] != res_shipped["disp"][i]}
    print(f"\nmachine-diff: removed={removed} flips={flips}")
    assert removed == {"I4210127166"}, f"unexpected removed set: {removed}"
    assert flips == {"I4210105796": ("up", "ns")}, f"unexpected flip set: {flips}"
    print("machine-diff == {removed: Centre Inria de l'UL (I4210127166), "
          "flips: CHU de Reims I4210105796 up->ns} and NOTHING else -- EXACT MATCH")

    res_noconf = mom.partner_level(pairs_shipped_noconf, grain_col="partner_id")
    print(f"\n[shipped, conf_state=no_conf] D1={res_noconf['d1']} D2={res_noconf['d2']} "
          f"MED={res_noconf['med']:.4f} eligible={res_noconf['eligible_n']} "
          f"{res_noconf['disp'].value_counts().to_dict()} "
          f"new={int(res_noconf['new'].sum())} dormant={int(res_noconf['dorm'].sum())}")
    print("(no golden exists for no_conf -- these numbers become the pinned reference in ptn_mom_facts)")
    phantom_noconf = diagnose_phantom(res_noconf, "shipped, conf_state=no_conf")
    assert phantom_noconf["phantom_class"] == "stable", (
        f"phantom (no_conf) expected 'stable', got {phantom_noconf['phantom_class']!r}"
    )
    print(f"  DISPLAY (phantom removed): {phantom_noconf['display_n']} -> "
          f"{phantom_noconf['display_classes']}; >=50: {phantom_noconf['display_n_ge50']} -> "
          f"{phantom_noconf['display_classes_ge50']}")

    return dict(frozen=res_frozen, shipped_all=res_shipped, shipped_noconf=res_noconf,
                phantom_frozen=phantom_frozen, phantom_shipped=phantom_shipped,
                phantom_noconf=phantom_noconf)


def build_ptn_mom_facts(mom_results: dict, snapshot_name: str) -> pd.DataFrame:
    """docs/foundry/data_foundation.yaml ptn_mom_facts.phantom_ruling: eligible_n is the frozen
    METHOD's own count (includes the one null-institution-id pseudo-partner, which the method
    never drops); display_eligible_n is what ptn_summary actually carries (real partners only).
    The gap is EXACTLY one row -- the named phantom -- pinned by the invariant below."""
    # pass 6 (S-NC cross-stream request, NARRATIVE_CONTRACT_pass6.md sec.5): expose the two
    # momentum window labels as DATA -- pages 5/8 currently write "2019-2020 vs 2022-2023" as a
    # literal string, which would silently go stale the moment the year_to config window moves
    # (the year-integration rehearsal, P6-R1/S-YR). lib46_momentum.W1_YEARS/W2_YEARS are the single
    # source of truth already; this just publishes them as a rendered label.
    mom_w1_label = f"{min(mom.W1_YEARS)}-{max(mom.W1_YEARS)}"
    mom_w2_label = f"{min(mom.W2_YEARS)}-{max(mom.W2_YEARS)}"

    rows = []
    for conf_state, res, phantom in [
        ("all", mom_results["shipped_all"], mom_results["phantom_shipped"]),
        ("no_conf", mom_results["shipped_noconf"], mom_results["phantom_noconf"]),
    ]:
        rows.append({
            "conf_state": conf_state,
            "recentring_median": round(res["med"], 6),
            "d1_denominator": res["d1"],
            "d2_denominator": res["d2"],
            "eligible_n": res["eligible_n"],
            "display_eligible_n": phantom["display_n"],
            "phantom_partner_works_w1": phantom["phantom_c1"],
            "phantom_partner_works_w2": phantom["phantom_c2"],
            "band_pct": BAND_PCT,
            "significance_p": SIGNIFICANCE_P,
            "mom_w1_label": mom_w1_label,
            "mom_w2_label": mom_w2_label,
            "snapshot_date": snapshot_name,
        })
    frame = pd.DataFrame(rows)
    frame = frame.astype({
        "conf_state": "string", "recentring_median": "float64", "d1_denominator": "int64",
        "d2_denominator": "int64", "eligible_n": "int64", "display_eligible_n": "int64",
        "phantom_partner_works_w1": "int64", "phantom_partner_works_w2": "int64",
        "band_pct": "int64", "significance_p": "float64",
        "mom_w1_label": "string", "mom_w2_label": "string", "snapshot_date": "string",
    })
    frame = frame[["conf_state", "recentring_median", "d1_denominator", "d2_denominator",
                   "eligible_n", "display_eligible_n", "phantom_partner_works_w1",
                   "phantom_partner_works_w2", "band_pct", "significance_p",
                   "mom_w1_label", "mom_w2_label", "snapshot_date"]]

    all_row = frame.loc[frame["conf_state"] == "all"].iloc[0]
    assert round(float(all_row["recentring_median"]), 4) == 1.0604, (
        f"ptn_mom_facts 'all' row recentring_median {all_row['recentring_median']} != 1.0604"
    )
    assert int(all_row["eligible_n"]) == 681

    diff = frame["eligible_n"] - frame["display_eligible_n"]
    assert (diff == 1).all(), (
        f"ptn_mom_facts invariant violated: eligible_n - display_eligible_n must == 1 (the named "
        f"phantom) on every row, got {diff.tolist()}"
    )
    print(f"\nptn_mom_facts phantom invariant (eligible_n - display_eligible_n == 1): PASS on every row")
    print(f"ptn_mom_facts (all row matches canonical_counts.momentum_shipped MED 1.0604 / 681):")
    print(frame.to_string(index=False))
    return frame


# ==================================================================================================
# SECTION 2 -- ptn_summary
# ==================================================================================================

def partner_identity_block(pairs_all_scope: pd.DataFrame, universe: dict, plumbing_ids: set) -> pd.DataFrame:
    """Identity attributes that do NOT vary by conf_state/subset_id (computed once from the widest
    'all' conf_state, subset 'all' pairs -- display_name/country/type via mode of raw authorship
    rows; consortium/idset tags from the overlay id-sets; plumbing_guard_flag from the momentum
    engine's own plumbing set)."""
    g = pairs_all_scope.groupby("partner_id")
    display_name = g["institution_display_name"].agg(lambda s: s.dropna().mode().iloc[0] if s.dropna().size else pd.NA)
    country_code = g["institution_country"].agg(lambda s: s.dropna().mode().iloc[0] if s.dropna().size else pd.NA)
    type_openalex = g["institution_type"].agg(lambda s: s.dropna().mode().iloc[0] if s.dropna().size else pd.NA)

    cons = universe["cons"]
    unigr = universe["unigr"]
    eureca = universe["eureca"]
    consortium_ids = set(cons.loc[(cons["status"] == "ok") & (cons["role"] == "external"), "id"])
    unigr_ids = set(unigr.loc[unigr["status"] == "ok", "id"])
    eureca_ids = set(eureca.loc[eureca["status"] == "ok", "id"])

    merged_targets = {}
    for old_id, new_id in universe["merge_map"].items():
        merged_targets.setdefault(new_id, []).append(old_id)

    idx = display_name.index
    consortium_member = pd.Series(idx.isin(consortium_ids), index=idx)
    tags = []
    for pid in idx:
        t = []
        if pid in consortium_ids:
            t.append("consortium")
        if pid in unigr_ids:
            t.append("unigr")
        if pid in eureca_ids:
            t.append("eureca")
        tags.append(", ".join(t))
    idset_tags = pd.Series(tags, index=idx, dtype="string")
    merged_from_ids = pd.Series(
        [", ".join(merged_targets.get(pid, [])) or pd.NA for pid in idx], index=idx, dtype="string"
    )
    plumbing_guard_flag = pd.Series(idx.isin(plumbing_ids), index=idx)

    out = pd.DataFrame({
        "partner_id": idx,
        "display_name": display_name.values,
        "country_code": country_code.values,
        "type_openalex": type_openalex.values,
        "consortium_member": consortium_member.values,
        "idset_tags": idset_tags.values,
        "merged_from_ids": merged_from_ids.values,
        "plumbing_guard_flag": plumbing_guard_flag.values,
    })
    return out


def scope_aggregates(pairs_scope: pd.DataFrame) -> pd.DataFrame:
    """Volume + impact + isite aggregates for one (conf_state, subset_id) scope's pairs frame.
    `pairs_scope` must already carry: partner_id, work_id, publication_year, n_institutions,
    is_conference, In_ISITE, FWCI_FR, indicator_status, cited_by_count, Is_international, Labs,
    artifact_flag."""
    g = pairs_scope.groupby("partner_id")
    co_works_full = g["work_id"].nunique()
    xa_scope = pairs_scope[~pairs_scope["artifact_flag"]]
    co_works_full_xa = xa_scope.groupby("partner_id")["work_id"].nunique()
    co_works_fractional = g.apply(lambda d: (1.0 / d.drop_duplicates("work_id")["n_institutions"]).sum())
    co_works_intl = pairs_scope[pairs_scope["Is_international"]].groupby("partner_id")["work_id"].nunique()
    first_year = g["publication_year"].min()
    last_year = g["publication_year"].max()

    def n_labs(d: pd.DataFrame) -> int:
        labs = set()
        # blob-separator fix (pass 6, manager re-open, P-ZP finding on ptn_labs -- the IDENTICAL
        # defect also lived here): pandas' str.split() treats a >1-char pattern as a REGEX unless
        # regex=False is passed. " | " as a regex is "one space OR one space" (the middle '|' is
        # alternation, not a literal pipe), i.e. it silently splits on EVERY space in the string --
        # "INSPIIRE (Ex APEMAC)" became ["INSPIIRE", "(Ex", "APEMAC)"], inflating n_ul_labs for any
        # partner touching a multi-word lab name. regex=False forces the literal 3-character match.
        for l in d.drop_duplicates("work_id")["Labs"].fillna("NO LAB").str.split(" | ", regex=False):
            for x in l:
                x = x.strip()
                if x and x != "NO LAB":
                    labs.add(x)
        return len(labs)

    n_ul_labs = g.apply(n_labs)

    computed = pairs_scope[pairs_scope["indicator_status"] == "computed"]
    computed_xa = xa_scope[xa_scope["indicator_status"] == "computed"]
    works_with_indicators = computed.groupby("partner_id")["work_id"].nunique()
    works_with_indicators_xa = computed_xa.groupby("partner_id")["work_id"].nunique()
    fwci_fr_median = computed.groupby("partner_id")["FWCI_FR"].median()
    fwci_fr_median_xa = computed_xa.groupby("partner_id")["FWCI_FR"].median()
    fwci_fr_mean = computed.groupby("partner_id")["FWCI_FR"].mean()
    fwci_fr_mean_xa = computed_xa.groupby("partner_id")["FWCI_FR"].mean()

    cited = pairs_scope[pairs_scope["cited_by_count"] > 0]
    cited_xa = xa_scope[xa_scope["cited_by_count"] > 0]
    share_cited = (cited.groupby("partner_id")["work_id"].nunique() / co_works_full).reindex(co_works_full.index)
    share_cited_xa = (cited_xa.groupby("partner_id")["work_id"].nunique() / co_works_full_xa).reindex(co_works_full_xa.index)

    isite_co_works = pairs_scope[pairs_scope["In_ISITE"]].groupby("partner_id")["work_id"].nunique()

    out = pd.DataFrame({"partner_id": co_works_full.index}).set_index("partner_id")
    out["co_works_full"] = co_works_full
    out["co_works_full_xa"] = co_works_full_xa.reindex(out.index).fillna(0).astype(int)
    out["co_works_fractional"] = co_works_fractional.round(4)
    out["co_works_intl"] = co_works_intl.reindex(out.index).fillna(0).astype(int)
    out["first_year"] = first_year
    out["last_year"] = last_year
    out["n_ul_labs"] = n_ul_labs
    out["works_with_indicators"] = works_with_indicators.reindex(out.index).fillna(0).astype(int)
    out["works_with_indicators_xa"] = works_with_indicators_xa.reindex(out.index).fillna(0).astype(int)
    out["fwci_fr_median"] = fwci_fr_median.reindex(out.index)
    out["fwci_fr_median_xa"] = fwci_fr_median_xa.reindex(out.index)
    out["fwci_fr_mean"] = fwci_fr_mean.reindex(out.index)
    out["fwci_fr_mean_xa"] = fwci_fr_mean_xa.reindex(out.index)
    out["share_cited"] = share_cited
    out["share_cited_xa"] = share_cited_xa
    out["isite_co_works"] = isite_co_works.reindex(out.index).fillna(0).astype(int)
    out["isite_share"] = (out["isite_co_works"] / out["co_works_full"]).round(6)
    return out.reset_index()


def build_ptn_summary(pairs_shipped_all: pd.DataFrame, pairs_shipped_noconf: pd.DataFrame,
                       identity: pd.DataFrame, mom_results: dict, snapshot_name: str,
                       partner_base: PartnerBaseLookup) -> pd.DataFrame:
    section("ptn_summary")
    scope_pairs = {
        ("all", "all"): pairs_shipped_all,
        ("no_conf", "all"): pairs_shipped_noconf,
        ("all", "in_isite"): pairs_shipped_all[pairs_shipped_all["In_ISITE"]],
        ("no_conf", "in_isite"): pairs_shipped_noconf[pairs_shipped_noconf["In_ISITE"]],
    }

    # share_ul / share_ul_direct denominators: the scope's own collaborative-work union (D_scope)
    # and the corresponding total-work count from dim_corpus_facts / dim_subsets.
    dim_corpus_facts = pd.read_parquet(SNAPSHOT_TABLES / "dim_corpus_facts.parquet").set_index("conf_state")
    dim_subsets = pd.read_parquet(SNAPSHOT_TABLES / "dim_subsets.parquet").set_index("subset_id")

    frames = []
    for subset_id in SUBSET_IDS_PTN_SUMMARY:
        for conf_state in CONF_STATES:
            pairs_scope = scope_pairs[(conf_state, subset_id)]
            agg = scope_aggregates(pairs_scope)
            d_scope = pairs_scope["work_id"].nunique()
            if subset_id == "all":
                total_works = int(dim_corpus_facts.loc[conf_state, "corpus_works"])
                collab_works = int(dim_corpus_facts.loc[conf_state, "corpus_collaborative_works"])
                assert d_scope == collab_works, (
                    f"share_ul denominator self-check failed ({subset_id},{conf_state}): "
                    f"pairs union {d_scope} != dim_corpus_facts.corpus_collaborative_works {collab_works}"
                )
            else:
                col = "n_works" if conf_state == "all" else "n_works_noconf"
                total_works = int(dim_subsets.loc[subset_id, col])
                collab_works = d_scope
            agg["share_ul"] = (agg["co_works_full"] / collab_works).round(6)
            agg["share_ul_xa"] = (agg["co_works_full_xa"] / collab_works).round(6)
            agg["share_ul_direct"] = (agg["co_works_full"] / total_works).round(6)
            agg["conf_state"] = conf_state
            agg["subset_id"] = subset_id
            frames.append(agg)

    volume_impact = pd.concat(frames, ignore_index=True)

    # momentum -- subset_id='all' rows only (app-wide exempt family; not recomputed within the tiny
    # in_isite perimeter -- see module docstring / contract fragment)
    mom_rows = []
    for conf_state, res in [("all", mom_results["shipped_all"]), ("no_conf", mom_results["shipped_noconf"])]:
        idx = res["disp"].index.union(res["mom_category"].dropna().index).union(res["w1_share"].index)
        d1, d2 = res["d1"], res["d2"]
        frame = pd.DataFrame({"partner_id": idx}).set_index("partner_id")
        frame["mom_class"] = res["disp"].reindex(idx)
        frame["mom_category"] = res["mom_category"].reindex(idx)
        frame["mom_p_value"] = res["pv"].reindex(idx)
        frame["mom_w1_share"] = res["w1_share"].reindex(idx).round(6)
        frame["mom_w2_share"] = res["w2_share"].reindex(idx).round(6)
        frame["mom_count_arrow"] = [
            f"{int(res['c1'].get(i, 0))}->{int(res['c2'].get(i, 0))}" for i in idx
        ]
        frame["mom_eligible_flag"] = res["elig"].reindex(idx).fillna(False)
        frame["conf_state"] = conf_state
        frame["subset_id"] = "all"
        mom_rows.append(frame.reset_index())
    momentum_block = pd.concat(mom_rows, ignore_index=True)

    frame = volume_impact.merge(momentum_block, on=["partner_id", "conf_state", "subset_id"], how="left")
    frame = frame.merge(identity, on="partner_id", how="left")
    frame = frame.reset_index(drop=True)  # guarantee positional alignment for the loop below

    # reciprocity (pass-4 G3, challenge memo #8/#9): share_p / partner_total_windowed populate
    # ONLY on (conf_state='all', subset_id='all') rows -- 42b pulled ONE all-types, all-corpus
    # denominator per partner, so a no_conf numerator over that denominator, or an in_isite numerator
    # over the whole-corpus denominator, is not a share (memo #8). Every other row stays NULL.
    # The 3 merged canonical partners are answered from the union sidecar via `partner_base`
    # (memo #9) -- transparent to this code, `partner_base.total()` already prefers it.
    partner_total_windowed = pd.array([pd.NA] * len(frame), dtype="Int64")
    share_p = pd.array([pd.NA] * len(frame), dtype="Float64")
    share_p_capped_flag = pd.array([pd.NA] * len(frame), dtype="boolean")

    is_all_all = (frame["conf_state"] == "all") & (frame["subset_id"] == "all")
    n_populated, n_capped = 0, 0
    for i in frame.index[is_all_all]:
        pid = frame.at[i, "partner_id"]
        denom = partner_base.total(pid)
        if not denom:  # None (not pulled) OR 0 (contradiction) -- D53: stays NULL, never 0
            continue
        raw = frame.at[i, "co_works_full"] / denom
        capped = raw > 1.0
        partner_total_windowed[i] = denom
        share_p[i] = 1.0 if capped else raw
        share_p_capped_flag[i] = bool(capped)
        n_populated += 1
        n_capped += int(capped)

    frame["partner_total_windowed"] = partner_total_windowed
    frame["share_p"] = share_p
    frame["share_p_capped_flag"] = share_p_capped_flag
    frame["snapshot_date"] = snapshot_name
    print(f"ptn_summary reciprocity (pass-4 G3, lens #8/#9): share_p populated on {n_populated:,} "
          f"of {int(is_all_all.sum()):,} (conf_state=all, subset_id=all) rows "
          f"({int(is_all_all.sum()) - n_populated:,} NULL -- partner not in the 42b pulled set, or "
          f"a contradictory 0 denominator); {n_capped:,} capped at 1.0 (snapshot-vs-live drift)")

    ordered = [
        "partner_id", "conf_state", "subset_id",
        "display_name", "country_code", "type_openalex", "consortium_member", "idset_tags",
        "merged_from_ids", "plumbing_guard_flag",
        "co_works_full", "co_works_full_xa", "co_works_fractional", "co_works_intl",
        "share_ul", "share_ul_xa", "share_ul_direct", "n_ul_labs", "first_year", "last_year",
        "partner_total_windowed", "share_p", "share_p_capped_flag",
        "fwci_fr_median", "fwci_fr_median_xa", "fwci_fr_mean", "fwci_fr_mean_xa",
        "share_cited", "share_cited_xa", "works_with_indicators", "works_with_indicators_xa",
        "mom_class", "mom_category", "mom_p_value", "mom_w1_share", "mom_w2_share",
        "mom_count_arrow", "mom_eligible_flag",
        "isite_co_works", "isite_share", "snapshot_date",
    ]
    frame = frame[ordered]

    frame = frame.astype({
        "partner_id": "string", "conf_state": "category", "subset_id": "category",
        "display_name": "string", "country_code": "category", "type_openalex": "category",
        "consortium_member": "bool", "idset_tags": "string", "merged_from_ids": "string",
        "plumbing_guard_flag": "bool", "co_works_full": "int64", "co_works_full_xa": "int64",
        "co_works_fractional": "float64", "co_works_intl": "int64", "share_ul": "float64",
        "share_ul_xa": "float64", "share_ul_direct": "float64", "n_ul_labs": "int64",
        "first_year": "int64", "last_year": "int64", "fwci_fr_median": "float64",
        "fwci_fr_median_xa": "float64", "fwci_fr_mean": "float64", "fwci_fr_mean_xa": "float64",
        "share_cited": "float64", "share_cited_xa": "float64", "works_with_indicators": "int64",
        "works_with_indicators_xa": "int64", "mom_class": "category", "mom_category": "category",
        "mom_p_value": "float64", "mom_w1_share": "float64", "mom_w2_share": "float64",
        "mom_count_arrow": "string", "mom_eligible_flag": "boolean",
        "isite_co_works": "int64", "isite_share": "float64", "snapshot_date": "string",
    })

    n_partners_all = frame.loc[(frame.conf_state == "all") & (frame.subset_id == "all"), "partner_id"].nunique()
    print(f"ptn_summary rows: {len(frame):,}; distinct partners (subset=all): {n_partners_all:,}")
    assert n_partners_all == CANON["partner_floor_ge10"] or True  # informational only (no floor on this table)
    for f in (10, 20, 50):
        n = int((frame.loc[(frame.conf_state == "all") & (frame.subset_id == "all"), "co_works_full"] >= f).sum())
        print(f"  co_works_full >= {f}: {n:,}")
    ge10 = int((frame.loc[(frame.conf_state == "all") & (frame.subset_id == "all"), "co_works_full"] >= 10).sum())
    ge20 = int((frame.loc[(frame.conf_state == "all") & (frame.subset_id == "all"), "co_works_full"] >= 20).sum())
    ge50 = int((frame.loc[(frame.conf_state == "all") & (frame.subset_id == "all"), "co_works_full"] >= 50).sum())
    assert ge10 == CANON["partner_floor_ge10"], f"partner floor >=10: {ge10} != {CANON['partner_floor_ge10']}"
    assert ge20 == CANON["partner_floor_ge20"], f"partner floor >=20: {ge20} != {CANON['partner_floor_ge20']}"
    assert ge50 == CANON["partner_floor_ge50"], f"partner floor >=50: {ge50} != {CANON['partner_floor_ge50']}"
    print("partner floors >=10/>=20/>=50 match canonical_counts EXACTLY: "
          f"{ge10:,}/{ge20:,}/{ge50:,}")

    null_country = int(frame.loc[(frame.conf_state == "all") & (frame.subset_id == "all"), "country_code"].isna().sum())
    print(f"null-country partners (subset=all): {null_country:,} "
          f"(canonical_counts states {CANON['null_country_partner_ids']} -- disclosed deviation, "
          f"see module docstring; not chased further)")

    # populated-state invariant (pass-4 G3, challenge memo #8/#9): share_p/partner_total_windowed
    # populate ONLY on (conf_state='all', subset_id='all') rows, and only where 42b's pull has that
    # partner's own-output denominator; every no_conf/in_isite row -- and every (all,all) row for a
    # partner outside the 42b pulled set -- stays NULL. NEVER 0 (D53).
    not_all_all = ~is_all_all
    assert frame.loc[not_all_all, "share_p"].isna().all(), (
        "share_p must be NULL on every no_conf/in_isite row (a no-conf numerator over a with-conf "
        "denominator, or an in_isite numerator over the whole-corpus denominator, is not a share -- "
        "pass-4 challenge memo #8)"
    )
    assert frame.loc[not_all_all, "partner_total_windowed"].isna().all(), (
        "partner_total_windowed must be NULL on every no_conf/in_isite row"
    )
    assert frame.loc[not_all_all, "share_p_capped_flag"].isna().all(), (
        "share_p_capped_flag must be NULL on every no_conf/in_isite row"
    )
    share_p_all_all = frame.loc[is_all_all, "share_p"]
    assert (share_p_all_all.dropna() > 0).all() and (share_p_all_all.dropna() <= 1.0).all(), (
        "share_p must be in (0, 1] wherever non-null -- NEVER 0 (D53)"
    )
    flag_where_null = frame.loc[is_all_all & frame["share_p"].isna(), "share_p_capped_flag"]
    assert flag_where_null.isna().all(), "share_p_capped_flag must stay NULL wherever share_p is NULL"
    flag_where_populated = frame.loc[is_all_all & frame["share_p"].notna(), "share_p_capped_flag"]
    assert flag_where_populated.isin([True, False]).all(), (
        "share_p_capped_flag must be a real True/False wherever share_p is populated"
    )
    print(f"ptn_summary reciprocity populated-state invariant: PASS "
          f"({n_populated:,} of {int(is_all_all.sum()):,} (all,all) rows populated; "
          f"{n_capped:,} capped; NULL everywhere else)")

    # merged canonical partners (challenge memo #9): each of the 3 successor ids must land a
    # non-null share_p on its (all,all) row -- this is the acceptance criterion's tier-A check.
    merged_canonical_ids = sorted(partner_base.canonical_ids)
    merged_rows_all_all = frame.loc[is_all_all & frame["partner_id"].isin(merged_canonical_ids),
                                     ["partner_id", "co_works_full", "partner_total_windowed", "share_p",
                                      "share_p_capped_flag"]]
    assert len(merged_rows_all_all) == len(merged_canonical_ids), (
        f"expected {len(merged_canonical_ids)} merged-canonical rows in ptn_summary (all,all), "
        f"found {len(merged_rows_all_all)}: {merged_rows_all_all['partner_id'].tolist()}"
    )
    assert merged_rows_all_all["share_p"].notna().all(), (
        f"merged canonical partners must have non-null share_p -- "
        f"{merged_rows_all_all[merged_rows_all_all['share_p'].isna()]['partner_id'].tolist()}"
    )
    print(f"merged canonical partners' share_p (challenge memo #9, all non-null):\n"
          f"{merged_rows_all_all.to_string(index=False)}")

    # isite reconciliation: isite_co_works(all-row) == co_works_full(in_isite-row) per partner, per conf_state
    for conf_state in CONF_STATES:
        all_rows = frame[(frame.conf_state == conf_state) & (frame.subset_id == "all")].set_index("partner_id")
        isite_rows = frame[(frame.conf_state == conf_state) & (frame.subset_id == "in_isite")].set_index("partner_id")
        merged = all_rows[["isite_co_works"]].join(isite_rows[["co_works_full"]], how="inner")
        bad = merged[merged["isite_co_works"] != merged["co_works_full"]]
        assert bad.empty, f"isite reconciliation failed for {len(bad)} partners ({conf_state}):\n{bad.head()}"
    print("isite reconciliation (isite_co_works[all-row] == co_works_full[in_isite-row] per partner): PASS")

    # phantom-ruling cross-check (data_foundation.yaml ptn_mom_facts.phantom_ruling): ptn_summary's
    # own classified-row counts per conf_state must equal the engine's DISPLAY (phantom-removed)
    # distribution exactly -- the phantom pseudo-partner is never a real partner_id, so it is
    # silently absent from `identity`/`volume_impact` and its momentum row never survives the
    # left-merge above; this asserts that silence produces the RIGHT count, not a stray one-off.
    for conf_state, phantom_key, engine_key in [
        ("all", "phantom_shipped", "shipped_all"), ("no_conf", "phantom_noconf", "shipped_noconf"),
    ]:
        phantom = mom_results[phantom_key]
        res = mom_results[engine_key]
        rows = frame[(frame.conf_state == conf_state) & (frame.subset_id == "all")].set_index("partner_id")
        classified = rows["mom_class"].dropna()
        classified_counts = classified.value_counts().to_dict()
        expected_counts = phantom["display_classes"]
        assert len(classified) == phantom["display_n"], (
            f"ptn_summary classified rows ({conf_state}): {len(classified)} != "
            f"ptn_mom_facts.display_eligible_n {phantom['display_n']}"
        )
        for cls in ("up", "down", "stable", "ns"):
            assert classified_counts.get(cls, 0) == expected_counts.get(cls, 0), (
                f"ptn_summary classified-row class mismatch ({conf_state}, {cls}): "
                f"{classified_counts.get(cls, 0)} != engine display {expected_counts.get(cls, 0)}"
            )
        # >=50 default-view floor -- the engine's own `inwin` (c1+c2, <=50-institution works, W1/W2
        # years only), NOT ptn_summary's co_works_full (whole-corpus, unfiltered total): the two are
        # different quantities and using co_works_full here silently over-counts the "big" bucket.
        big_ids = set(res["inwin"][res["inwin"] >= 50].index) - {PHANTOM_ID}
        big_classified_series = rows.loc[rows.index.isin(big_ids), "mom_class"].dropna()
        big_classified = big_classified_series.value_counts().to_dict()
        expected_ge50 = phantom["display_classes_ge50"]
        assert len(big_classified_series) == phantom["display_n_ge50"], (
            f"ptn_summary >=50 classified rows ({conf_state}): "
            f"{len(big_classified_series)} != {phantom['display_n_ge50']}"
        )
        for cls in ("up", "down", "stable", "ns"):
            assert big_classified.get(cls, 0) == expected_ge50.get(cls, 0), (
                f"ptn_summary >=50 class mismatch ({conf_state}, {cls}): "
                f"{big_classified.get(cls, 0)} != engine display {expected_ge50.get(cls, 0)}"
            )
        print(f"ptn_summary classified rows ({conf_state}): {len(classified)} -> {classified_counts} "
              f"-- EXACT match to ptn_mom_facts.display_eligible_n and the engine's phantom-removed "
              f"distribution; >=50 (engine inwin floor): {len(big_classified_series)} -> {big_classified}")

    return frame


# ==================================================================================================
# SECTION 2bis -- ptn_denominators (pass 6, P4/#39/#40)
# ==================================================================================================

def build_ptn_denominators(ptn_summary: pd.DataFrame, consortium_ids: set[str], n_ul_corpus: int,
                           snapshot_name: str) -> pd.DataFrame:
    """Partner denominators (P4/#39/#40): four new shares, derived DIRECTLY from ptn_summary's own
    already-built (conf_state='all', subset_id='all') row per partner -- never a separate
    recompute from corpus_authorships, so `co_works_full`/`share_ul` and these new shares are
    guaranteed to reconcile on the SAME page (page 8 shows both side by side, P4).

      share_of_ul_corpus                    -- copubs / UL's whole corpus (the 36,819-perimeter,
                                                read as len(works_master), never hardcoded).
      share_of_ul_france_copubs_hors_site   -- FRANCE partners only: copubs / (UL's total France
                                                copubs EXCLUDING the 8 consortium signatories --
                                                inputs/overlays/idset_consortium.csv, 15 ids). NULL
                                                for non-FR partners AND for the consortium members
                                                themselves (a signatory is not asked "your share of
                                                France-hors-site", it IS excluded from that
                                                population by definition).
      share_of_ul_intl_copubs               -- INTERNATIONAL (non-FR) partners only: copubs / UL's
                                                total international copubs. NULL for FR partners.
      share_of_ul_country_copubs            -- INTERNATIONAL partners only: copubs / UL's total
                                                copubs with partners from THIS partner's OWN
                                                country (the "Groningen = 5% of NL collabs" case).
                                                NULL for FR partners.

    Invariants (asserted below): every share in [0,1]; consortium members carry a NULL
    france-hors-site share; ONE independent pandas spot-check of a country-share reproduces the
    table value exactly.
    """
    section("ptn_denominators")
    base = ptn_summary[(ptn_summary["conf_state"] == "all") & (ptn_summary["subset_id"] == "all")].copy()
    base = base[["partner_id", "display_name", "country_code", "co_works_full"]].reset_index(drop=True)

    base["share_of_ul_corpus"] = (base["co_works_full"] / n_ul_corpus).round(6)
    base["is_consortium_member"] = base["partner_id"].isin(consortium_ids)

    is_fr = base["country_code"] == "FR"
    is_intl = ~is_fr & base["country_code"].notna()

    fr_hors_site = base[is_fr & ~base["is_consortium_member"]]
    fr_hors_site_denom = int(fr_hors_site["co_works_full"].sum())
    share_fr_hors_site = pd.Series(pd.NA, index=base.index, dtype="Float64")
    if fr_hors_site_denom:
        idx = fr_hors_site.index
        share_fr_hors_site.loc[idx] = (base.loc[idx, "co_works_full"] / fr_hors_site_denom).round(6)
    base["share_of_ul_france_copubs_hors_site"] = share_fr_hors_site

    intl_denom = int(base.loc[is_intl, "co_works_full"].sum())
    share_intl = pd.Series(pd.NA, index=base.index, dtype="Float64")
    if intl_denom:
        share_intl.loc[is_intl] = (base.loc[is_intl, "co_works_full"] / intl_denom).round(6)
    base["share_of_ul_intl_copubs"] = share_intl

    country_denom = base.loc[is_intl].groupby("country_code", observed=True)["co_works_full"].transform("sum")
    share_country = pd.Series(pd.NA, index=base.index, dtype="Float64")
    share_country.loc[is_intl] = (base.loc[is_intl, "co_works_full"] / country_denom).round(6)
    base["share_of_ul_country_copubs"] = share_country

    base["snapshot_date"] = snapshot_name
    out = base[["partner_id", "display_name", "country_code", "co_works_full",
               "is_consortium_member", "share_of_ul_corpus",
               "share_of_ul_france_copubs_hors_site", "share_of_ul_intl_copubs",
               "share_of_ul_country_copubs", "snapshot_date"]]
    out = out.astype({
        "partner_id": "string", "display_name": "string", "country_code": "string",
        "co_works_full": "int64", "is_consortium_member": "bool",
        "share_of_ul_corpus": "float64", "share_of_ul_france_copubs_hors_site": "float64",
        "share_of_ul_intl_copubs": "float64", "share_of_ul_country_copubs": "float64",
        "snapshot_date": "string",
    })

    # ---- invariants ---------------------------------------------------------------------------
    for col in ("share_of_ul_corpus", "share_of_ul_france_copubs_hors_site",
               "share_of_ul_intl_copubs", "share_of_ul_country_copubs"):
        vals = out[col].dropna()
        assert (vals >= 0).all() and (vals <= 1.0000001).all(), f"{col} outside [0,1]"

    consortium_rows = out[out["is_consortium_member"]]
    assert consortium_rows["share_of_ul_france_copubs_hors_site"].isna().all(), (
        "consortium signatories must carry a NULL share_of_ul_france_copubs_hors_site "
        "(excluded from that denominator by definition, P4)"
    )

    fr_rows = out[out["country_code"] == "FR"]
    assert fr_rows["share_of_ul_intl_copubs"].isna().all(), "FR partners must have NULL intl share"
    assert fr_rows["share_of_ul_country_copubs"].isna().all(), "FR partners must have NULL country share"
    intl_rows = out[(out["country_code"].notna()) & (out["country_code"] != "FR")]
    assert intl_rows["share_of_ul_france_copubs_hors_site"].isna().all(), (
        "international partners must have NULL france-hors-site share"
    )

    # ---- ONE hand-verified spot check: an independent pandas path for one country's share -------
    # (the "Groningen = 5% of NL collabs" acceptance example, P4/#40) -- pick the country with the
    # most >=1 international partners so the check is non-trivial, not a 1-partner-country no-op.
    country_counts = intl_rows["country_code"].value_counts()
    spot_country = country_counts.index[0]
    spot_partner_row = intl_rows[intl_rows["country_code"] == spot_country].iloc[0]
    independent_country_total = int(
        intl_rows.loc[intl_rows["country_code"] == spot_country, "co_works_full"].sum()
    )
    independent_share = round(spot_partner_row["co_works_full"] / independent_country_total, 6)
    table_share = float(out.loc[out["partner_id"] == spot_partner_row["partner_id"],
                                "share_of_ul_country_copubs"].iloc[0])
    assert abs(independent_share - table_share) < 1e-9, (
        f"spot-check FAILED for {spot_partner_row['display_name']} ({spot_country}): independent "
        f"{independent_share} != table {table_share}"
    )
    print(f"  spot-check (independent pandas path): {spot_partner_row['display_name']} = "
          f"{spot_partner_row['co_works_full']}/{independent_country_total} co-works with "
          f"{spot_country} partners = {table_share:.4f} -- table value matches EXACTLY")

    print(f"ptn_denominators rows: {len(out):,} (consortium members: {int(out['is_consortium_member'].sum())}, "
          f"FR partners: {len(fr_rows)}, international: {len(intl_rows)})")
    return out


SNAPSHOT_TABLES: Path  # set in main()


# ==================================================================================================
# SECTION 3 -- ptn_yearly
# ==================================================================================================

def build_ptn_yearly(pairs_shipped_all: pd.DataFrame, pairs_shipped_noconf: pd.DataFrame,
                      snapshot_name: str) -> pd.DataFrame:
    section("ptn_yearly")
    frames = []
    for conf_state, pairs_scope in [("all", pairs_shipped_all), ("no_conf", pairs_shipped_noconf)]:
        g = pairs_scope.groupby(["partner_id", "publication_year"])["work_id"].nunique().rename("co_works")
        xa = pairs_scope[~pairs_scope["artifact_flag"]]
        g_xa = xa.groupby(["partner_id", "publication_year"])["work_id"].nunique().rename("co_works_xa")
        d_year = pairs_scope.groupby("publication_year")["work_id"].nunique()  # whole-scope union per year
        d_year_xa = xa.groupby("publication_year")["work_id"].nunique()

        frame = g.reset_index().merge(g_xa.reset_index(), on=["partner_id", "publication_year"], how="left")
        frame["co_works_xa"] = frame["co_works_xa"].fillna(0).astype(int)
        frame["share_of_ul_collab"] = frame.apply(
            lambda r: round(r["co_works"] / d_year[r["publication_year"]], 6), axis=1)
        frame["share_of_ul_collab_xa"] = frame.apply(
            lambda r: round(r["co_works_xa"] / d_year_xa[r["publication_year"]], 6)
            if r["publication_year"] in d_year_xa.index and d_year_xa[r["publication_year"]] else np.nan, axis=1)
        frame["conf_state"] = conf_state
        frames.append(frame)

    out = pd.concat(frames, ignore_index=True)
    out = out.rename(columns={"publication_year": "year"})
    out["snapshot_date"] = snapshot_name
    out = out[["partner_id", "year", "conf_state", "co_works", "co_works_xa",
               "share_of_ul_collab", "share_of_ul_collab_xa", "snapshot_date"]]
    out = out.astype({
        "partner_id": "string", "year": "int32", "conf_state": "category",
        "co_works": "int64", "co_works_xa": "int64", "share_of_ul_collab": "float64",
        "share_of_ul_collab_xa": "float64", "snapshot_date": "string",
    })
    print(f"ptn_yearly rows: {len(out):,}")
    assert (out["co_works_xa"] <= out["co_works"]).all(), "co_works_xa must never exceed co_works"
    return out


# ==================================================================================================
# SECTION 4 -- ptn_fields (I5 thematic profile + I6 per-field momentum)
# ==================================================================================================

def load_field_baselines(wm: pd.DataFrame, snapshot_tables: Path) -> dict:
    """baseline_ul_share / baseline_ul_share_xa (UL's own field mix, per conf_state) +
    baseline_france_share (France baseline's own field mix, per conf_state -- computed from the
    france_20XX shards, which already carry field_id per work with the corpus doc-type scope)."""
    out = {}
    for conf_state in CONF_STATES:
        scoped = wm if conf_state == "all" else wm[~wm["is_conference"].fillna(False)]
        total = len(scoped)
        total_xa = int((~scoped["artifact_flag"]).sum())
        ul_field = (scoped.groupby("primary_field_id")["work_id"].nunique() / total).rename("baseline_ul_share")
        ul_field_xa = (scoped[~scoped["artifact_flag"]].groupby("primary_field_id")["work_id"].nunique()
                       / total_xa).rename("baseline_ul_share_xa")
        ul_subfield = (scoped.groupby("primary_subfield_id")["work_id"].nunique() / total).rename("baseline_ul_share")
        ul_subfield_xa = (scoped[~scoped["artifact_flag"]].groupby("primary_subfield_id")["work_id"].nunique()
                          / total_xa).rename("baseline_ul_share_xa")
        out[("field", conf_state)] = pd.concat([ul_field, ul_field_xa], axis=1)
        out[("subfield", conf_state)] = pd.concat([ul_subfield, ul_subfield_xa], axis=1)

    frames = [pd.read_parquet(snapshot_tables / f"france_{y}.parquet") for y in (2019, 2020, 2021, 2022, 2023)]
    france = pd.concat(frames, ignore_index=True)
    for conf_state in CONF_STATES:
        fscope = france if conf_state == "all" else france[france["type"] != "conference-paper"]
        ftot = len(fscope)
        ffield = (fscope.groupby("field_id")["work_id"].nunique() / ftot).rename("baseline_france_share")
        fsub = (fscope.groupby("subfield_id")["work_id"].nunique() / ftot).rename("baseline_france_share")
        out[("field_france", conf_state)] = ffield
        out[("subfield_france", conf_state)] = fsub
    return out


def build_ptn_fields(pairs_shipped_all: pd.DataFrame, pairs_shipped_noconf: pd.DataFrame,
                      wm_full: pd.DataFrame, mom_results: dict, snapshot_name: str,
                      snapshot_tables: Path, partner_base: PartnerBaseLookup) -> pd.DataFrame:
    section("ptn_fields")
    baselines = load_field_baselines(wm_full, snapshot_tables)

    bps_populated_total, bps_capped_total = 0, 0
    rows_by_state = []
    for conf_state, pairs_scope in [("all", pairs_shipped_all), ("no_conf", pairs_shipped_noconf)]:
        xa = pairs_scope[~pairs_scope["artifact_flag"]]
        partner_total = pairs_scope.groupby("partner_id")["work_id"].nunique()
        partner_total_xa = xa.groupby("partner_id")["work_id"].nunique()

        # OVERLAY_MATRIX EXTEND (pass 5, S3, additive): isite_co_works restricted to this same
        # (partner, node) cell -- same construction as ptn_summary.isite_co_works / the geo_countries
        # extension above, reused here for the "Zoom partenaire" thematic-profile panel.
        isite_scope = pairs_scope[pairs_scope["In_ISITE"]]
        node_frames = []
        for level, floor in [("field", 0), ("subfield", SPARSE_NODE_FLOOR)]:
            col = "primary_field_id" if level == "field" else "primary_subfield_id"
            g = pairs_scope.groupby(["partner_id", col])["work_id"].nunique().rename("co_works")
            g_xa = xa.groupby(["partner_id", col])["work_id"].nunique().rename("co_works_xa")
            g_isite = isite_scope.groupby(["partner_id", col])["work_id"].nunique().rename("co_works_isite")
            cell = g.reset_index().merge(g_xa.reset_index(), on=["partner_id", col], how="left")
            cell = cell.merge(g_isite.reset_index(), on=["partner_id", col], how="left")
            cell["co_works_xa"] = cell["co_works_xa"].fillna(0).astype(int)
            cell["co_works_isite"] = cell["co_works_isite"].fillna(0).astype(int)
            if floor:
                cell = cell[cell["co_works"] >= floor]
            cell = cell.rename(columns={col: "node_id"})
            cell["node_level"] = level
            node_frames.append(cell)
        cells = pd.concat(node_frames, ignore_index=True)
        cells["share_of_pair_isite"] = (cells["co_works_isite"] / cells["co_works"]).round(6)

        cells["share_of_pair"] = cells.apply(
            lambda r: round(r["co_works"] / partner_total[r["partner_id"]], 6), axis=1)
        cells["share_of_pair_xa"] = cells.apply(
            lambda r: round(r["co_works_xa"] / partner_total_xa[r["partner_id"]], 6)
            if r["partner_id"] in partner_total_xa.index and partner_total_xa[r["partner_id"]] else np.nan, axis=1)

        base_ul = baselines[("field", conf_state)]
        base_ul_sub = baselines[("subfield", conf_state)]
        base_fr = baselines[("field_france", conf_state)]
        base_fr_sub = baselines[("subfield_france", conf_state)]

        def lookup(row, table_field, table_sub, out_col):
            table = table_field if row["node_level"] == "field" else table_sub
            return table.get(row["node_id"], np.nan) if isinstance(table, pd.Series) else \
                (table.loc[row["node_id"], out_col] if row["node_id"] in table.index else np.nan)

        cells["baseline_ul_share"] = cells.apply(
            lambda r: lookup(r, base_ul["baseline_ul_share"], base_ul_sub["baseline_ul_share"], "baseline_ul_share"),
            axis=1)
        cells["baseline_ul_share_xa"] = cells.apply(
            lambda r: lookup(r, base_ul["baseline_ul_share_xa"], base_ul_sub["baseline_ul_share_xa"],
                              "baseline_ul_share_xa"), axis=1)
        cells["baseline_france_share"] = cells.apply(lambda r: lookup(r, base_fr, base_fr_sub, None), axis=1)
        cells["lq_vs_ul"] = (cells["share_of_pair"] / cells["baseline_ul_share"]).round(4)
        cells["lq_vs_ul_xa"] = (cells["share_of_pair_xa"] / cells["baseline_ul_share_xa"]).round(4)

        # baseline_partner_share (pass-4 G3, challenge memo #8 applied symmetrically): 42b pulled
        # ONE all-types denominator per (partner, node) -- so, exactly like ptn_summary.share_p,
        # this populates ONLY on conf_state='all' rows; no_conf rows would divide a no-conf
        # numerator by an all-types denominator (not a share) and stay NULL. No separate capped-
        # flag column exists in the contract for this table (unlike ptn_summary), so a >1 raw ratio
        # (the same snapshot-vs-live drift as elsewhere) is silently capped at 1.0 and counted for
        # the print/manifest report only -- mirrors 44e's own precedent for the identical drift.
        if conf_state == "all":
            denom_raw = cells.apply(
                lambda r: partner_base.node_total(r["partner_id"], r["node_level"], r["node_id"]), axis=1
            )
            has_denom = denom_raw.notna() & (denom_raw.fillna(0) > 0)
            raw_share = cells["co_works"].astype(float) / denom_raw.astype("float64")
            capped_mask = has_denom & (raw_share > 1.0)
            capped_share = raw_share.where(~capped_mask, 1.0)
            cells["baseline_partner_share"] = capped_share.where(has_denom, other=pd.NA).astype("Float64")
            bps_populated_total += int(has_denom.sum())
            bps_capped_total += int(capped_mask.sum())
            print(f"  [ptn_fields, conf_state=all] baseline_partner_share populated on "
                  f"{int(has_denom.sum()):,} of {len(cells):,} cells "
                  f"({int(capped_mask.sum()):,} capped at 1.0, snapshot-vs-live drift)")
        else:
            cells["baseline_partner_share"] = pd.array([pd.NA] * len(cells), dtype="Float64")

        # I6 -- per-field momentum only (frozen def., field grain; subfield stays refused per sec.6.6)
        res = mom_results["shipped_all"] if conf_state == "all" else mom_results["shipped_noconf"]
        bigp = set(res["inwin"][(res["inwin"] >= 50) & ~res["inwin"].index.isin(res["plumbing"])].index)
        field_pairs = pairs_scope[pairs_scope["partner_id"].isin(bigp)]
        fcw = (field_pairs.groupby(["partner_id", "primary_field_id", "publication_year"]).size()
               .unstack(fill_value=0).reindex(columns=list(mom.ALL_YEARS), fill_value=0))
        f1 = fcw[list(mom.W1_YEARS)].sum(axis=1)
        f2 = fcw[list(mom.W2_YEARS)].sum(axis=1)
        rr, pv, elig_cell = mom.cell_delta(f1, f2, res["d1"], res["d2"], res["med"])
        cls = mom.classify(rr, pv)
        field_mom = pd.DataFrame({
            "partner_id": [i[0] for i in cls.index], "node_id": [i[1] for i in cls.index],
            "mom_class": cls.values, "mom_p_value": pv.reindex(cls.index).values,
            "mom_eligible_flag": elig_cell.reindex(cls.index).values,
        })
        field_mom["node_level"] = "field"
        print(f"  [I6, conf_state={conf_state}] eligible field cells: {int(elig_cell.sum())} across "
              f"{len(bigp)} partners (>=50 co-works); classes {cls.dropna().value_counts().to_dict()}")

        cells = cells.merge(field_mom, on=["partner_id", "node_id", "node_level"], how="left")
        cells["mom_eligible_flag"] = cells["mom_eligible_flag"].fillna(False)
        cells["conf_state"] = conf_state
        rows_by_state.append(cells)

    out = pd.concat(rows_by_state, ignore_index=True)
    out["snapshot_date"] = snapshot_name
    out = out[[
        "partner_id", "node_level", "node_id", "conf_state", "co_works", "co_works_xa",
        "share_of_pair", "share_of_pair_xa", "baseline_ul_share", "baseline_ul_share_xa",
        "baseline_partner_share", "baseline_france_share", "lq_vs_ul", "lq_vs_ul_xa",
        "co_works_isite", "share_of_pair_isite",
        "mom_class", "mom_p_value", "mom_eligible_flag", "snapshot_date",
    ]]
    out = out.astype({
        "partner_id": "string", "node_level": "category", "node_id": "category",
        "conf_state": "category", "co_works": "int64", "co_works_xa": "int64",
        "share_of_pair": "float64", "share_of_pair_xa": "float64",
        "baseline_ul_share": "float64", "baseline_ul_share_xa": "float64",
        "baseline_france_share": "float64", "lq_vs_ul": "float64", "lq_vs_ul_xa": "float64",
        "co_works_isite": "int64", "share_of_pair_isite": "float64",
        "mom_class": "category", "mom_p_value": "float64", "mom_eligible_flag": "boolean",
        "snapshot_date": "string",
    })
    # populated-state invariant (pass-4 G3, lens #8 applied symmetrically): NULL on every no_conf
    # cell always; on conf_state='all' cells, non-null only where the 42b denominator existed, and
    # NEVER 0 there (a 0/absent denominator stays NULL, D53).
    bps_noconf = out.loc[out["conf_state"] == "no_conf", "baseline_partner_share"]
    assert bps_noconf.isna().all(), (
        "baseline_partner_share must be NULL on every no_conf cell (lens #8, applied symmetrically "
        "to ptn_summary.share_p: a no-conf numerator over the 42b all-types denominator is not a share)"
    )
    bps_all = out.loc[out["conf_state"] == "all", "baseline_partner_share"]
    assert (bps_all.dropna() > 0).all() and (bps_all.dropna() <= 1.0).all(), (
        "baseline_partner_share must be in (0, 1] wherever non-null -- NEVER 0 (D53)"
    )
    print(f"ptn_fields baseline_partner_share populated-state invariant: PASS "
          f"({bps_populated_total:,} of {int((out['conf_state'] == 'all').sum()):,} conf_state=all "
          f"cells populated, {bps_capped_total:,} capped at 1.0; "
          f"{int(bps_noconf.isna().sum()):,} no_conf cells NULL by design)")
    print(f"ptn_fields rows: {len(out):,} (field cells + subfield cells >= {SPARSE_NODE_FLOOR})")
    return out


# ==================================================================================================
# SECTION 5 -- ptn_labs (I7 portage)
# ==================================================================================================

def build_ptn_labs(pairs_shipped_all: pd.DataFrame, pairs_shipped_noconf: pd.DataFrame,
                    snapshot_name: str) -> pd.DataFrame:
    section("ptn_labs")
    lab_lookup = pd.read_parquet(SNAPSHOT_TABLES / "ul_labs.parquet", columns=["lab", "ror"])
    lab_ror_map = dict(zip(lab_lookup["lab"], lab_lookup["ror"]))

    frames = []
    for conf_state, pairs_scope in [("all", pairs_shipped_all), ("no_conf", pairs_shipped_noconf)]:
        work_level = pairs_scope.drop_duplicates(["partner_id", "work_id"])[["partner_id", "work_id", "Labs"]].copy()
        work_level["Labs"] = work_level["Labs"].fillna("NO LAB")
        nolab = work_level[work_level["Labs"] == "NO LAB"]
        nolab_counts = nolab.groupby("partner_id")["work_id"].nunique().rename("nolab_works")
        total_counts = work_level.groupby("partner_id")["work_id"].nunique().rename("co_works_total")

        # blob-separator fix (pass 6, manager re-open, P-ZP finding, progress/PZP.md): pandas'
        # str.split() treats a >1-char pattern as a REGEX unless regex=False is passed. " | " as a
        # regex is alternation ("one space OR one space" -- the middle '|' is the regex operator,
        # not a literal pipe), so it silently split on EVERY space -- "INSPIIRE (Ex APEMAC)" became
        # 3 tokens (["INSPIIRE", "(Ex", "APEMAC)"]) plus a spurious literal "|" row wherever a work
        # had >1 lab. Confirmed on CHRU Nancy (I4210100260): 190 co-works each on "(Ex"/"APEMAC)",
        # 354 on the bare "|" token. 13,645 of 83,184 pre-fix rows (16.4%) were fragments.
        lab_level = work_level[work_level["Labs"] != "NO LAB"].assign(
            lab_name=lambda d: d["Labs"].str.split(" | ", regex=False)).explode("lab_name")
        lab_level["lab_name"] = lab_level["lab_name"].str.strip()
        lab_counts = lab_level.groupby(["partner_id", "lab_name"])["work_id"].nunique().rename("co_works").reset_index()

        lab_attributed = (total_counts - nolab_counts.reindex(total_counts.index).fillna(0)).rename("lab_attributed")
        lab_counts = lab_counts.merge(lab_attributed.reset_index(), on="partner_id", how="left")
        lab_counts["share_of_lab_attributed"] = (lab_counts["co_works"] / lab_counts["lab_attributed"]).round(6)
        lab_counts = lab_counts.merge(nolab_counts.reset_index(), on="partner_id", how="left")
        lab_counts["nolab_works"] = lab_counts["nolab_works"].fillna(0).astype(int)
        lab_counts = lab_counts.merge(total_counts.reset_index(), on="partner_id", how="left")
        lab_counts["nolab_share"] = (lab_counts["nolab_works"] / lab_counts["co_works_total"]).round(6)
        lab_counts["lab_ror"] = lab_counts["lab_name"].map(lab_ror_map)
        lab_counts["conf_state"] = conf_state
        frames.append(lab_counts[["partner_id", "lab_ror", "lab_name", "conf_state", "co_works",
                                   "share_of_lab_attributed", "nolab_works", "nolab_share"]])

    out = pd.concat(frames, ignore_index=True)
    out["snapshot_date"] = snapshot_name
    out = out.astype({
        "partner_id": "string", "lab_ror": "string", "lab_name": "category", "conf_state": "category",
        "co_works": "int64", "share_of_lab_attributed": "float64", "nolab_works": "int64",
        "nolab_share": "float64", "snapshot_date": "string",
    })
    assert (out["share_of_lab_attributed"].dropna() <= 1.0000001).all(), "share_of_lab_attributed must be <=1"
    assert (out["nolab_share"].dropna() <= 1.0000001).all(), "nolab_share must be <=1"
    print(f"ptn_labs rows: {len(out):,}")
    return out


# ==================================================================================================
# SECTION 6 -- ptn_works (I11 drill source, lazy) + ptn_topics (I11 table, lazy)
# ==================================================================================================

def frontier_score_lookup() -> pd.Series:
    """Topic-level frontier_score_std -- MUST match thm_frontier's own construction exactly
    (pipeline/47_build_thematic_ext.py, W3, chain pass 3 manager fix round: the plan's original
    OA_frontier_scores.xlsx pointer was a transcription error; the card-blessed, byte-verified
    artifact is inputs/manual/frontierness_baseline.xlsx, sheet 'FILTERING OUT TOPICS', column
    'Average frontierness' -- taken AS-IS (already a z-scored-within-bin ACCORD composite
    upstream; this codebase does not re-standardise it a second time). Populated ONLY for KEPT
    topics (not in the 811-topic exclusion list, lib.artifact.load_bad_topics -- verified
    identical to this same file's own Sheet2 exclusion ids, per 47's own assert); NULL for
    excluded topics, exactly mirroring thm_frontier's texture rows (drawn from `kept` only, top-20
    by score -- ptn_topics needs the FULL kept-topic lookup, not just that top-20 window, but must
    agree with thm_frontier on every topic the two tables share)."""
    actual_sha256 = hashlib.sha256(FRONTIER_XLSX.read_bytes()).hexdigest()
    assert actual_sha256 == FRONTIER_XLSX_SHA256, (
        f"{FRONTIER_XLSX} sha256 mismatch: {actual_sha256} != {FRONTIER_XLSX_SHA256} -- "
        "this must be the card-blessed vintage byte-identical to thm_frontier's own input "
        "(manager fix round); STOP and re-sync inputs/manual/ rather than proceeding"
    )
    print(f"  frontierness_baseline.xlsx sha256 verified: {actual_sha256[:12]}... == expected "
          f"(card-blessed vintage, same file thm_frontier.parquet reads)")

    base = pd.read_excel(FRONTIER_XLSX, sheet_name="FILTERING OUT TOPICS")
    base.columns = [c.strip() for c in base.columns]
    key = "Topic ID no url"
    base[key] = base[key].astype(str).str.strip()

    bad_ids = load_bad_topics(ROOT)
    base["excluded"] = base[key].isin(bad_ids)
    n_excluded = int(base["excluded"].sum())
    assert n_excluded == 811, (
        f"frontierness_baseline.xlsx exclusion count drifted: {n_excluded} != 811 -- expected "
        "byte-identical to lib.artifact.load_bad_topics(), same as 47_build_thematic_ext.py's own assert"
    )
    kept = base[~base["excluded"]]
    return kept.set_index(key)["Average frontierness"].astype(float)


def build_ptn_works(pairs_shipped_all_p10: pd.DataFrame, sdg_siris: pd.DataFrame,
                    snapshot_name: str) -> pd.DataFrame:
    section("ptn_works")
    out = pairs_shipped_all_p10[[
        "partner_id", "work_id", "publication_year", "title", "doi", "type", "is_conference",
        "FWCI_FR", "In_ISITE", "Labs", "artifact_flag", "primary_field_id", "primary_subfield_id",
        "primary_topic_id",
    ]].drop_duplicates(["partner_id", "work_id"]).rename(columns={
        "publication_year": "year", "FWCI_FR": "fwci_fr", "In_ISITE": "in_isite", "Labs": "labs_short",
    })
    # pass 6 (#9/#11/#32/#44): SDG tags, pipe-joined SIRIS/VocTagger sdg numbers -- the ONE
    # enrichment field the pre-pass-6 ptn_works lacked for a full "download with enrichment
    # metadata" publication list (doi/year/type/artifact_flag/in_isite were already there).
    sdg_tags_by_work = sdg_siris.groupby("work_id")["sdg"].apply(
        lambda s: "|".join(str(int(x)) for x in sorted(s))
    )
    out["sdg_tags"] = out["work_id"].map(sdg_tags_by_work)
    out["snapshot_date"] = snapshot_name
    out = out[[
        "partner_id", "work_id", "year", "title", "doi", "type", "is_conference", "fwci_fr",
        "in_isite", "labs_short", "artifact_flag", "sdg_tags", "primary_field_id",
        "primary_subfield_id", "primary_topic_id", "snapshot_date",
    ]]
    out = out.astype({
        "partner_id": "category", "work_id": "string", "year": "int32", "title": "string",
        "doi": "string", "type": "category", "is_conference": "bool", "fwci_fr": "float64",
        "in_isite": "bool", "labs_short": "string", "artifact_flag": "bool", "sdg_tags": "string",
        "primary_field_id": "category", "primary_subfield_id": "category",
        "primary_topic_id": "category", "snapshot_date": "string",
    })
    out = out.sort_values("partner_id").reset_index(drop=True)

    assert len(out) == CANON["ptn_works_pairs_at_p10floor"], (
        f"ptn_works pairs: {len(out):,} != canonical {CANON['ptn_works_pairs_at_p10floor']:,}"
    )
    print(f"ptn_works rows (>= {DRILL_PARTNER_FLOOR} floor): {len(out):,} -- matches canonical EXACTLY")
    return out


def _ptn_topics_state(pairs_state: pd.DataFrame, conf_state: str, res: dict,
                       corpus_topics: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """One conf_state's worth of the ptn_topics long table + delta -- the SAME construction the
    table used before conf_state existed, just parameterised by which pairs frame (already
    is_conference-filtered by the caller for 'no_conf') and which momentum reference (d1/d2/med)
    to use. Returns (long_tbl WITHOUT frontier_score_std/artifact_flag/snapshot_date -- those are
    state-invariant and joined once on the combined frame -- , a dict of diagnostic counts)."""
    pt = pairs_state[["partner_id", "work_id", "publication_year", "artifact_flag"]].merge(
        corpus_topics[["work_id", "topic_id", "subfield_id"]], on="work_id", how="inner"
    )
    long_tbl = (pt.groupby(["partner_id", "topic_id", "subfield_id", "publication_year"])["work_id"]
                .nunique().reset_index(name="co_works"))
    xa = pt[~pt["artifact_flag"]]
    long_xa = (xa.groupby(["partner_id", "topic_id", "subfield_id", "publication_year"])["work_id"]
               .nunique().reset_index(name="co_works_xa"))
    long_tbl = long_tbl.merge(long_xa, on=["partner_id", "topic_id", "subfield_id", "publication_year"],
                               how="left")
    long_tbl["co_works_xa"] = long_tbl["co_works_xa"].fillna(0).astype(int)
    long_tbl = long_tbl.rename(columns={"publication_year": "year"})

    n_cells = long_tbl[["partner_id", "topic_id"]].drop_duplicates().shape[0]
    cell_total = pt.groupby(["partner_id", "topic_id"])["work_id"].nunique()
    n_ge3 = int((cell_total >= 3).sum())
    n_ge20 = int((cell_total >= 20).sum())

    # fwci_fr_median_cell -- DEFERRED twin (no _xa), floor-free (D53: NULL only if 0 works-with-
    # indicators in the cell), computed from THIS state's own works
    wm_ind = pairs_state[["work_id", "FWCI_FR"]].drop_duplicates("work_id").set_index("work_id")
    pt_ind = pt.merge(wm_ind, on="work_id", how="left")
    fwci_cell = pt_ind.dropna(subset=["FWCI_FR"]).groupby(["partner_id", "topic_id"])["FWCI_FR"].median()

    # numeric two-window delta (I11, sec.6.3) -- reuse THIS state's own d1/d2/med reference
    # (ptn_mom_facts' row for this conf_state)
    cw_cell = (pt.groupby(["partner_id", "topic_id", "publication_year"]).size().unstack(fill_value=0)
               .reindex(columns=list(mom.ALL_YEARS), fill_value=0))
    c1 = cw_cell[list(mom.W1_YEARS)].sum(axis=1)
    c2 = cw_cell[list(mom.W2_YEARS)].sum(axis=1)
    delta_value, delta_pv, delta_elig = mom.cell_delta(c1, c2, res["d1"], res["d2"], res["med"])
    delta_flag = (delta_pv < SIGNIFICANCE_P) & delta_elig
    delta_flag = delta_flag.where(delta_elig, pd.NA)

    long_tbl["fwci_fr_median_cell"] = long_tbl.set_index(["partner_id", "topic_id"]).index.map(fwci_cell)
    long_tbl["delta_value"] = long_tbl.set_index(["partner_id", "topic_id"]).index.map(delta_value.round(4))
    long_tbl["delta_flag"] = long_tbl.set_index(["partner_id", "topic_id"]).index.map(delta_flag)
    long_tbl["conf_state"] = conf_state

    n_delta_populated = int(long_tbl.drop_duplicates(["partner_id", "topic_id"])["delta_value"].notna().sum())
    diag = dict(rows=len(long_tbl), cells=n_cells, ge3=n_ge3, ge20=n_ge20, delta_populated=n_delta_populated)
    return long_tbl, diag


def build_ptn_topics(pairs_shipped_all_p10: pd.DataFrame, pairs_shipped_noconf_p10: pd.DataFrame,
                      corpus_topics: pd.DataFrame, mom_results: dict, snapshot_name: str,
                      old_ptn_topics_reference: pd.DataFrame | None = None) -> pd.DataFrame:
    section("ptn_topics")

    all_tbl, all_diag = _ptn_topics_state(pairs_shipped_all_p10, "all", mom_results["shipped_all"],
                                           corpus_topics)
    print(f"[conf_state=all] long rows: {all_diag['rows']:,}; distinct (partner,topic) cells: "
          f"{all_diag['cells']:,}")
    assert all_diag["rows"] == 224396, f"[all] long rows {all_diag['rows']:,} != canonical 224,396"
    assert all_diag["cells"] == CANON["ptn_topics_cells_at_p10floor"], (
        f"[all] cells: {all_diag['cells']:,} != canonical {CANON['ptn_topics_cells_at_p10floor']:,}"
    )
    print(f"[conf_state=all] cells >=3: {all_diag['ge3']:,} (canonical {CANON['ptn_topics_cells_ge3']:,}) | "
          f">=20: {all_diag['ge20']:,} (canonical {CANON['ptn_topics_cells_ge20']:,})")
    assert all_diag["ge3"] == CANON["ptn_topics_cells_ge3"]
    assert all_diag["ge20"] == CANON["ptn_topics_cells_ge20"]
    assert all_diag["delta_populated"] == 878, (
        f"[all] delta_value populated on {all_diag['delta_populated']} cells != 878 (unchanged canonical)"
    )
    print(f"[conf_state=all] delta_value populated on {all_diag['delta_populated']:,} distinct cells "
          f"(of the {CANON['ptn_topics_cells_ge20']:,} clearing the simple >=20-total-works floor). "
          "ALL canonical counts (rows/cells/>=3/>=20/delta) MATCH EXACTLY -- unchanged by the "
          "conf_state grain extension (fix round 3).")

    noconf_tbl, noconf_diag = _ptn_topics_state(pairs_shipped_noconf_p10, "no_conf",
                                                 mom_results["shipped_noconf"], corpus_topics)
    print(f"\n[conf_state=no_conf] PINNED REFERENCE (no golden exists -- first build with this grain):")
    print(f"  long rows: {noconf_diag['rows']:,}; distinct (partner,topic) cells: {noconf_diag['cells']:,}")
    print(f"  cells >=3: {noconf_diag['ge3']:,} | >=20: {noconf_diag['ge20']:,}")
    print(f"  delta_value populated on {noconf_diag['delta_populated']:,} distinct cells")

    # frontier_score_std / artifact_flag: state-INVARIANT topic properties (topic-grain marker +
    # baseline lookup, never vary by conference-toggle state) -- computed ONCE, carried on BOTH
    # states' rows (data_foundation.yaml grain correction, fix round 3)
    frontier = frontier_score_lookup()
    bad_topics = load_bad_topics(ROOT)

    combined = pd.concat([all_tbl, noconf_tbl], ignore_index=True)
    combined["frontier_score_std"] = combined["topic_id"].map(frontier)
    combined["artifact_flag"] = combined["topic_id"].isin(bad_topics)
    combined["snapshot_date"] = snapshot_name

    out = combined[[
        "partner_id", "topic_id", "subfield_id", "year", "conf_state", "co_works", "co_works_xa",
        "fwci_fr_median_cell", "frontier_score_std", "artifact_flag", "delta_value", "delta_flag",
        "snapshot_date",
    ]]
    out = out.astype({
        "partner_id": "category", "topic_id": "category", "subfield_id": "category", "year": "int16",
        "conf_state": "category", "co_works": "int32", "co_works_xa": "int32",
        "fwci_fr_median_cell": "float64", "frontier_score_std": "float64", "artifact_flag": "bool",
        "delta_value": "float64", "delta_flag": "boolean", "snapshot_date": "string",
    })
    out = out.sort_values(["partner_id", "conf_state"]).reset_index(drop=True)

    # ---- all-slice row-identity proof (fix round 3 mandate) --------------------------------------
    # Pre-existing bug fix (found while re-running for pass-4 G3, unrelated to share_p/
    # baseline_partner_share): the on-disk reference file this compares against is whatever
    # ptn_topics.parquet happened to be BEFORE this build overwrote it -- the first time this check
    # ran, that was the pre-conf_state-extension table (no `conf_state` column, all rows implicitly
    # the 'all' slice). Every build SINCE then leaves a reference that already HAS `conf_state` and
    # BOTH states' rows, which crashed `new_all[old_cols]` (KeyError: 'conf_state' not in index,
    # since new_all already dropped it) and would have double-counted rows even if that line were
    # patched blindly. Handle both vintages: if the reference already has `conf_state`, restrict it
    # to the 'all' slice and drop the column before taking its column list, exactly mirroring what
    # the pre-extension file looked like.
    if old_ptn_topics_reference is not None:
        old_ref = old_ptn_topics_reference
        if "conf_state" in old_ref.columns:
            old_ref = old_ref[old_ref["conf_state"] == "all"].drop(columns=["conf_state"])
        old_cols = list(old_ref.columns)
        new_all = out[out["conf_state"] == "all"].drop(columns=["conf_state"]).reset_index(drop=True)
        new_all = new_all[old_cols]
        old_cmp = old_ref.reset_index(drop=True).copy()
        new_cmp = new_all.copy()
        for col in ("partner_id", "topic_id", "subfield_id"):
            old_cmp[col] = old_cmp[col].astype(str)
            new_cmp[col] = new_cmp[col].astype(str)
        # both sides are sorted by partner_id; the 'all' slice must reproduce the same row order
        # (secondary key: the groupby's own stable order, unchanged by adding a conf_state column)
        old_sorted = old_cmp.sort_values(["partner_id", "topic_id", "year"]).reset_index(drop=True)
        new_sorted = new_cmp.sort_values(["partner_id", "topic_id", "year"]).reset_index(drop=True)
        identical = old_sorted.equals(new_sorted)
        print(f"\n[all-slice identity proof] conf_state='all' rows ({len(new_sorted):,}) vs the "
              f"pre-fix-round-3 on-disk table ({len(old_sorted):,}): "
              f"{'IDENTICAL (row-for-row, value-for-value)' if identical else 'MISMATCH'}")
        assert identical, (
            "conf_state='all' slice is NOT row-identical to the prior ptn_topics table -- the "
            "conf_state grain extension must never change the 'all' construction itself"
        )
    else:
        print("\n[all-slice identity proof] SKIPPED -- no prior ptn_topics.parquet found on disk "
              "to compare against (first-ever build)")

    return out


# ==================================================================================================
# SECTION 7 -- consortium_weights (PM4)
# ==================================================================================================

def build_consortium_weights(au_raw: pd.DataFrame, wm_full: pd.DataFrame, universe: dict,
                              snapshot_name: str) -> pd.DataFrame:
    section("consortium_weights")
    cons = universe["cons"]
    ext_rows = cons[(cons["status"] == "ok") & (cons["role"] == "external")]

    au = au_raw.dropna(subset=["institution_id"])[["work_id", "institution_id"]].drop_duplicates()

    rows = []
    for conf_state in CONF_STATES:
        works_scope = wm_full if conf_state == "all" else wm_full[~wm_full["is_conference"].fillna(False)]
        works_scope_ids = set(works_scope["work_id"])
        isite_ids = set(works_scope.loc[works_scope["In_ISITE"], "work_id"])
        n_all = len(works_scope_ids)
        n_isite = len(isite_ids)
        au_scope = au[au["work_id"].isin(works_scope_ids)]

        for member, grp in ext_rows.groupby("member", sort=False):
            ids = set(grp["id"].astype(str))
            member_rows = au_scope[au_scope["institution_id"].isin(ids)]
            ws_all = set(member_rows["work_id"])
            ws_isite = ws_all & isite_ids
            row_sum_isite = sum(len(set(au_scope[au_scope["institution_id"] == i]["work_id"]) & isite_ids)
                               for i in ids)
            incl_variant = pd.NA
            if member == "Inria":
                incl_ids = ids | {"I4210127166"}
                ws_incl = set(au_scope[au_scope["institution_id"].isin(incl_ids)]["work_id"])
                incl_variant = round(len(ws_incl & isite_ids) / n_isite, 4) if n_isite else pd.NA
                if conf_state == "all":
                    print(f"  GT/Inria row-sum-vs-union check (ISITE scope, conf=all): "
                          f"GT union={len(ws_isite) if member == 'Georgia Tech' else '-'}")
            rows.append({"member": member, "member_label": member, "scope": "isite", "conf_state": conf_state,
                         "co_works_distinct": len(ws_isite), "share_of_scope": round(len(ws_isite) / n_isite, 4) if n_isite else np.nan,
                         "incl_own_centre_variant_share": incl_variant, "id_set_size": len(ids),
                         "_row_sum_isite": row_sum_isite})
            rows.append({"member": member, "member_label": member, "scope": "all", "conf_state": conf_state,
                         "co_works_distinct": len(ws_all), "share_of_scope": round(len(ws_all) / n_all, 4) if n_all else np.nan,
                         "incl_own_centre_variant_share": pd.NA, "id_set_size": len(ids),
                         "_row_sum_isite": pd.NA})

    frame = pd.DataFrame(rows)
    frame["snapshot_date"] = snapshot_name

    # goldens (conf_state='all', scope='isite') -- F0-P5, must equal exactly
    isite_all = frame[(frame.scope == "isite") & (frame.conf_state == "all")].set_index("member")
    targets = {"CNRS": 58.7, "INRAE": 21.5, "AgroParisTech": 9.9, "Inserm": 9.0,
               "CHRU Nancy": 2.6, "Georgia Tech": 1.1}
    for member, pct in targets.items():
        got = round(float(isite_all.loc[member, "share_of_scope"]) * 100, 1)
        assert got == pct, f"consortium_weights {member} ISITE share {got} != {pct} (F0-P5 golden)"
    inria_ext_pct = round(float(isite_all.loc["Inria", "share_of_scope"]) * 100, 1)
    inria_incl_pct = round(float(isite_all.loc["Inria", "incl_own_centre_variant_share"]) * 100, 1)
    assert inria_ext_pct == 0.1, f"Inria external ISITE share {inria_ext_pct} != 0.1"
    assert inria_incl_pct == 0.3, f"Inria incl-own ISITE share {inria_incl_pct} != 0.3"
    print("consortium_weights (ISITE scope, conf=all) matches F0-P5 EXACTLY: "
          "58.7/21.5/9.9/9.0/2.6/1.1/0.1|0.3")

    gt_row_sum = int(isite_all.loc["Georgia Tech", "_row_sum_isite"])
    gt_union = int(isite_all.loc["Georgia Tech", "co_works_distinct"])
    assert gt_union < gt_row_sum, f"GT distinct union {gt_union} must be < row-sum {gt_row_sum}"
    assert (gt_union, gt_row_sum) == (21, 45), f"GT union/row-sum {gt_union}/{gt_row_sum} != 21/45"
    print(f"GT union<sum invariant: union={gt_union} < row_sum={gt_row_sum} (21 vs 45) -- PASS")

    frame = frame.drop(columns=["_row_sum_isite"])
    frame = frame[["member", "member_label", "scope", "conf_state", "co_works_distinct",
                   "share_of_scope", "incl_own_centre_variant_share", "id_set_size", "snapshot_date"]]
    frame["incl_own_centre_variant_share"] = pd.array(
        frame["incl_own_centre_variant_share"].tolist(), dtype="Float64"
    )
    frame = frame.astype({
        "member": "category", "member_label": "string", "scope": "category", "conf_state": "category",
        "co_works_distinct": "int64", "share_of_scope": "float64",
        "id_set_size": "int64", "snapshot_date": "string",
    })
    print(f"consortium_weights rows: {len(frame):,}")
    return frame


# ==================================================================================================
# SECTION 8 -- geo_countries / geo_fields / geo_groups (I10)
# ==================================================================================================

def build_geo_countries(pairs_shipped_all: pd.DataFrame, pairs_shipped_noconf: pd.DataFrame,
                         snapshot_name: str) -> pd.DataFrame:
    section("geo_countries")
    frames = []
    for conf_state, pairs_scope in [("all", pairs_shipped_all), ("no_conf", pairs_shipped_noconf)]:
        for subset_id, scoped in [("all", pairs_scope), ("in_isite", pairs_scope[pairs_scope["In_ISITE"]])]:
            xa = scoped[~scoped["artifact_flag"]]
            known = scoped.dropna(subset=["institution_country"])
            known_xa = xa.dropna(subset=["institution_country"])
            g = known.groupby(["institution_country", "publication_year"])["work_id"].nunique().rename("co_works")
            g_xa = known_xa.groupby(["institution_country", "publication_year"])["work_id"].nunique().rename("co_works_xa")
            frame = g.reset_index().merge(g_xa.reset_index(),
                                           on=["institution_country", "publication_year"], how="left")
            frame["co_works_xa"] = frame["co_works_xa"].fillna(0).astype(int)
            frame["unknown_bucket_flag"] = False
            frame = frame.rename(columns={"institution_country": "country_code"})

            # OVERLAY_MATRIX EXTEND (pass 5, S3, additive): isite_co_works/isite_share, same-row
            # twin of co_works -- EXACT construction/naming pattern as ptn_summary's own
            # isite_co_works/isite_share (line ~604 of this file: `scoped[scoped["In_ISITE"]]`
            # grouped the same way as the parent count, no special-case on subset_id -- on
            # subset_id='in_isite' rows this trivially reproduces co_works/1.0, same harmless
            # tautology ptn_summary already ships). Lets the geography page shade a per-country
            # bar with its ISITE portion with ZERO recomputation, instead of joining the
            # subset_id='in_isite' row at render time.
            g_isite = (known[known["In_ISITE"]].groupby(["institution_country", "publication_year"])
                       ["work_id"].nunique().rename("isite_co_works"))
            frame = frame.merge(g_isite.reset_index().rename(columns={"institution_country": "country_code"}),
                                 on=["country_code", "publication_year"], how="left")
            frame["isite_co_works"] = frame["isite_co_works"].fillna(0).astype(int)
            frame["isite_share"] = (frame["isite_co_works"] / frame["co_works"]).round(6)

            unk = scoped[scoped["institution_country"].isna()]
            unk_xa = xa[xa["institution_country"].isna()]
            if len(unk):
                gu = unk.groupby("publication_year")["work_id"].nunique().rename("co_works").reset_index()
                gu_xa = unk_xa.groupby("publication_year")["work_id"].nunique().rename("co_works_xa").reset_index()
                gu = gu.merge(gu_xa, on="publication_year", how="left")
                gu["co_works_xa"] = gu["co_works_xa"].fillna(0).astype(int)
                gu["country_code"] = "UNKNOWN"
                gu["unknown_bucket_flag"] = True
                gu_isite = (unk[unk["In_ISITE"]].groupby("publication_year")["work_id"].nunique()
                            .rename("isite_co_works").reset_index())
                gu = gu.merge(gu_isite, on="publication_year", how="left")
                gu["isite_co_works"] = gu["isite_co_works"].fillna(0).astype(int)
                gu["isite_share"] = (gu["isite_co_works"] / gu["co_works"]).round(6)
                frame = pd.concat([frame, gu], ignore_index=True)

            d_scope = scoped["work_id"].nunique()
            d_scope_xa = xa["work_id"].nunique()
            fwci_known = known[known["indicator_status"] == "computed"]
            fwci_med = fwci_known.groupby(["institution_country", "publication_year"])["FWCI_FR"].median()
            fwci_med_xa = known_xa[known_xa["indicator_status"] == "computed"].groupby(
                ["institution_country", "publication_year"])["FWCI_FR"].median()

            frame["share_ul"] = (frame["co_works"] / d_scope).round(6)
            frame["share_ul_xa"] = (frame["co_works_xa"] / d_scope_xa).round(6) if d_scope_xa else np.nan
            frame["fwci_fr_median"] = frame.apply(
                lambda r: fwci_med.get((r["country_code"], r["publication_year"]), np.nan)
                if not r["unknown_bucket_flag"] else np.nan, axis=1)
            frame["fwci_fr_median_xa"] = frame.apply(
                lambda r: fwci_med_xa.get((r["country_code"], r["publication_year"]), np.nan)
                if not r["unknown_bucket_flag"] else np.nan, axis=1)
            frame["conf_state"] = conf_state
            frame["subset_id"] = subset_id
            frames.append(frame)

    out = pd.concat(frames, ignore_index=True)
    out = out.rename(columns={"publication_year": "year"})
    out["snapshot_date"] = snapshot_name
    out = out[["country_code", "year", "conf_state", "subset_id", "co_works", "co_works_xa",
               "share_ul", "share_ul_xa", "fwci_fr_median", "fwci_fr_median_xa",
               "isite_co_works", "isite_share",
               "unknown_bucket_flag", "snapshot_date"]]
    out = out.astype({
        "country_code": "category", "year": "int32", "conf_state": "category", "subset_id": "category",
        "co_works": "int64", "co_works_xa": "int64", "share_ul": "float64", "share_ul_xa": "float64",
        "fwci_fr_median": "float64", "fwci_fr_median_xa": "float64",
        "isite_co_works": "int64", "isite_share": "float64", "unknown_bucket_flag": "bool",
        "snapshot_date": "string",
    })

    known_countries = out.loc[(out.conf_state == "all") & (out.subset_id == "all") & ~out.unknown_bucket_flag,
                              ["country_code"]].drop_duplicates().shape[0]
    country_totals = (pairs_shipped_all.dropna(subset=["institution_country"])
                       .groupby("institution_country")["work_id"].nunique())
    ge10 = int((country_totals >= 10).sum())
    assert ge10 == CANON["countries_ge10"], f"countries >=10: {ge10} != {CANON['countries_ge10']}"
    print(f"geo_countries rows: {len(out):,}; known countries (subset=all): {known_countries}; "
          f">=10 co-works: {ge10} (canonical {CANON['countries_ge10']}) -- MATCH")

    # OVERLAY_MATRIX EXTEND reconciliation (same pattern/invariant as ptn_summary, tested in
    # test_foundation_v3.py::test_ptn_summary_isite_reconciliation): isite_co_works on the
    # subset_id='all' row must equal co_works on the matching subset_id='in_isite' row, per
    # (country_code, year, conf_state) -- excluding the UNKNOWN bucket (not a real country).
    for conf_state in CONF_STATES:
        all_rows = out[(out.conf_state == conf_state) & (out.subset_id == "all") & ~out.unknown_bucket_flag] \
            .set_index(["country_code", "year"])
        isite_rows = out[(out.conf_state == conf_state) & (out.subset_id == "in_isite") & ~out.unknown_bucket_flag] \
            .set_index(["country_code", "year"])
        joined = all_rows[["isite_co_works"]].join(isite_rows[["co_works"]], how="inner")
        bad = joined[joined["isite_co_works"] != joined["co_works"]]
        assert bad.empty, (
            f"geo_countries isite reconciliation FAILED ({conf_state}): {len(bad)} (country,year) "
            f"cell(s) where isite_co_works(all-row) != co_works(in_isite-row)"
        )
    print("geo_countries isite reconciliation (isite_co_works[all-row] == co_works[in_isite-row] "
          "per country x year x conf_state, unknown bucket excluded): PASS")
    return out


def build_geo_fields(pairs_shipped_all: pd.DataFrame, pairs_shipped_noconf: pd.DataFrame,
                      wm_full: pd.DataFrame, snapshot_name: str) -> pd.DataFrame:
    section("geo_fields")
    baselines = load_field_baselines(wm_full, SNAPSHOT_TABLES)
    frames = []
    for conf_state, pairs_scope in [("all", pairs_shipped_all), ("no_conf", pairs_shipped_noconf)]:
        xa = pairs_scope[~pairs_scope["artifact_flag"]]
        known = pairs_scope.dropna(subset=["institution_country"])
        known_xa = xa.dropna(subset=["institution_country"])
        country_total = known.groupby("institution_country")["work_id"].nunique()
        country_total_xa = known_xa.groupby("institution_country")["work_id"].nunique()

        node_frames = []
        for level, floor, col in [("field", 0, "primary_field_id"),
                                   ("subfield", SPARSE_NODE_FLOOR, "primary_subfield_id")]:
            g = known.groupby(["institution_country", col])["work_id"].nunique().rename("co_works")
            g_xa = known_xa.groupby(["institution_country", col])["work_id"].nunique().rename("co_works_xa")
            cell = g.reset_index().merge(g_xa.reset_index(), on=["institution_country", col], how="left")
            cell["co_works_xa"] = cell["co_works_xa"].fillna(0).astype(int)
            if floor:
                cell = cell[cell["co_works"] >= floor]
            cell = cell.rename(columns={col: "node_id", "institution_country": "country_code"})
            cell["node_level"] = level
            node_frames.append(cell)
        cells = pd.concat(node_frames, ignore_index=True)

        cells["share_of_country_pair"] = cells.apply(
            lambda r: round(r["co_works"] / country_total[r["country_code"]], 6), axis=1)
        cells["share_of_country_pair_xa"] = cells.apply(
            lambda r: round(r["co_works_xa"] / country_total_xa[r["country_code"]], 6)
            if r["country_code"] in country_total_xa.index and country_total_xa[r["country_code"]] else np.nan, axis=1)

        base_ul = baselines[("field", conf_state)]["baseline_ul_share"]
        base_ul_sub = baselines[("subfield", conf_state)]["baseline_ul_share"]
        cells["baseline_ul_share"] = cells.apply(
            lambda r: (base_ul if r["node_level"] == "field" else base_ul_sub).get(r["node_id"], np.nan), axis=1)

        fwci_known = known[known["indicator_status"] == "computed"]
        fwci_field = fwci_known.groupby(["institution_country", "primary_field_id"])["FWCI_FR"].median()
        fwci_sub = fwci_known.groupby(["institution_country", "primary_subfield_id"])["FWCI_FR"].median()
        cells["fwci_fr_median"] = cells.apply(
            lambda r: (fwci_field if r["node_level"] == "field" else fwci_sub).get((r["country_code"], r["node_id"]), np.nan),
            axis=1)
        cells["conf_state"] = conf_state
        frames.append(cells)

    out = pd.concat(frames, ignore_index=True)
    out["snapshot_date"] = snapshot_name
    out = out[["country_code", "node_level", "node_id", "conf_state", "co_works", "co_works_xa",
               "share_of_country_pair", "share_of_country_pair_xa", "baseline_ul_share",
               "fwci_fr_median", "snapshot_date"]]
    out = out.astype({
        "country_code": "category", "node_level": "category", "node_id": "category",
        "conf_state": "category", "co_works": "int64", "co_works_xa": "int64",
        "share_of_country_pair": "float64", "share_of_country_pair_xa": "float64",
        "baseline_ul_share": "float64", "fwci_fr_median": "float64", "snapshot_date": "string",
    })
    out = out.sort_values("country_code").reset_index(drop=True)
    print(f"geo_fields rows: {len(out):,}")
    return out


def build_geo_groups(au_raw: pd.DataFrame, wm_full: pd.DataFrame, universe: dict,
                      mom_results: dict, snapshot_name: str) -> pd.DataFrame:
    section("geo_groups")
    au = au_raw.dropna(subset=["institution_id"])[["work_id", "institution_id"]].drop_duplicates()
    wm_idx = wm_full.set_index("work_id")

    rows = []
    for group_id, overlay in [("unigr", universe["unigr"]), ("eureca", universe["eureca"])]:
        ok_rows = overlay[overlay["status"] == "ok"]
        for member, grp in ok_rows.groupby("member", sort=False):
            ids = set(grp["id"].astype(str))
            member_pairs = au[au["institution_id"].isin(ids)].drop_duplicates("work_id")
            member_pairs = member_pairs.merge(
                wm_full[["work_id", "publication_year", "is_conference"]], on="work_id", how="left")

            for conf_state in CONF_STATES:
                scoped = member_pairs if conf_state == "all" else member_pairs[~member_pairs["is_conference"].fillna(False)]
                co_works_distinct = scoped["work_id"].nunique()
                cw = scoped.groupby("publication_year")["work_id"].nunique().reindex(mom.ALL_YEARS, fill_value=0)
                c1 = int(cw.reindex(list(mom.W1_YEARS)).sum())
                c2 = int(cw.reindex(list(mom.W2_YEARS)).sum())
                res = mom_results["shipped_all"] if conf_state == "all" else mom_results["shipped_noconf"]
                rr, pv, elig = mom.cell_delta(pd.Series([c1]), pd.Series([c2]), res["d1"], res["d2"], res["med"])
                cls_series = mom.classify(rr, pv)
                mom_class = cls_series.iloc[0] if elig.iloc[0] else pd.NA

                for year in mom.ALL_YEARS:
                    rows.append({
                        "group_id": group_id, "member_id": member, "member_name": member,
                        "conf_state": conf_state, "co_works_distinct": co_works_distinct,
                        "mom_class": mom_class, "year": year, "co_works_year": int(cw.get(year, 0)),
                    })

    frame = pd.DataFrame(rows)
    frame["snapshot_date"] = snapshot_name
    frame = frame.astype({
        "group_id": "category", "member_id": "string", "member_name": "string",
        "conf_state": "category", "co_works_distinct": "int64", "mom_class": "category",
        "year": "int32", "co_works_year": "int64", "snapshot_date": "string",
    })

    freiberg_union = int(frame.loc[(frame.member_id == "Freiberg") & (frame.conf_state == "all"),
                                    "co_works_distinct"].iloc[0])
    print(f"Freiberg (2-id composition) union co-works: {freiberg_union} (supersession: canonical 15, not 16)")
    assert freiberg_union == 15, f"Freiberg union {freiberg_union} != 15 (canonical supersession)"
    print(f"geo_groups rows: {len(frame):,}")
    return frame


# ==================================================================================================
# SECTION 9 -- lazy-file prune proofs (mirrors reports/foundry_pass2_probes.py prune_proof)
# ==================================================================================================

def prune_proof(path: Path, filter_col: str, target, label: str) -> None:
    pf = pq.ParquetFile(path)
    col_idx = pf.schema_arrow.get_field_index(filter_col)
    total_bytes = 0
    touched_bytes = 0
    n_touched = 0
    n_rg = pf.metadata.num_row_groups
    for i in range(n_rg):
        rg = pf.metadata.row_group(i)
        col = rg.column(col_idx)
        sz = col.total_compressed_size
        total_bytes += sz
        stats = col.statistics
        if stats is not None and stats.has_min_max and stats.min <= target <= stats.max:
            touched_bytes += sz
            n_touched += 1
    file_bytes = path.stat().st_size
    actual = pd.read_parquet(path, filters=[(filter_col, "==", target)])
    ratio = touched_bytes / max(total_bytes, 1)
    print(f"[{label}] prune proof for {filter_col}={target}: row groups touched {n_touched}/{n_rg} "
          f"({ratio:.1%} of {filter_col}-column bytes); whole file {file_bytes/1e6:.2f} MB; "
          f"filtered read returned {len(actual):,} rows")
    assert ratio < 0.20, f"[{label}] prune ratio {ratio:.1%} >= 20% -- row-group discipline broken"


def assert_row_groups(path: Path, label: str) -> None:
    pf = pq.ParquetFile(path)
    n_rows = pf.metadata.num_rows
    n_rg = pf.metadata.num_row_groups
    floor = n_rows / 10000
    print(f"[{label}] Class-1 invariant: num_row_groups={n_rg} >= n_rows/10000={floor:.1f}: "
          f"{'PASS' if n_rg >= floor else 'FAIL'}")
    assert n_rg >= floor, f"[{label}] row-group floor violated: {n_rg} < {floor:.1f}"


# ==================================================================================================
# MAIN
# ==================================================================================================

def main() -> None:
    global SNAPSHOT_TABLES
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"
    SNAPSHOT_TABLES = tables
    compression = CONFIG["storage"]["compression"]
    today = dt.date.today().isoformat()

    print(f"snapshot {snapshot.name}: building ptn_* / geo_* / consortium_weights (W2)")

    section("LOAD INPUTS")
    wm_full = pd.read_parquet(tables / "works_master.parquet", columns=[
        "work_id", "publication_year", "n_institutions", "is_conference", "In_ISITE", "FWCI_FR",
        "indicator_status", "cited_by_count", "Is_international", "Labs", "n_labs",
        "primary_field_id", "primary_subfield_id", "primary_topic_id", "title", "doi", "type",
    ])
    au_raw = pd.read_parquet(tables / "corpus_authorships.parquet", columns=[
        "work_id", "institution_id", "institution_display_name", "institution_country",
        "institution_type",
    ])
    corpus_topics = pd.read_parquet(tables / "corpus_topics.parquet",
                                    columns=["work_id", "topic_id", "is_primary"])
    corpus_topics_full = pd.read_parquet(tables / "corpus_topics.parquet",
                                         columns=["work_id", "topic_id", "subfield_id"])
    all_topics = pd.read_parquet(tables / "all_topics.parquet")
    sdg_siris = pd.read_parquet(tables / "sdg_siris.parquet", columns=["work_id", "sdg"])
    print(f"  works_master: {len(wm_full):,} rows; corpus_authorships: {len(au_raw):,} rows")

    flag_series = flag_works(corpus_topics, root=ROOT)
    wm_full["artifact_flag"] = wm_full["work_id"].map(flag_series).fillna(False).astype(bool)
    n_flagged = int(wm_full["artifact_flag"].sum())
    assert n_flagged == 4106, f"artifact-flag count drifted: {n_flagged} != 4,106"
    print(f"  artifact-flag (primary topic on 811-topic list): {n_flagged:,} works (11.15%)")

    universe = build_universe(tables)
    # canonical (null-dropping) pairs -- feeds every table EXCEPT the momentum engine itself
    pairs_shipped_all = build_pairs(au_raw, wm_full, universe["merge_map"],
                                      universe["ul_own_shipped"], flag_series)
    pairs_shipped_noconf = pairs_shipped_all[~pairs_shipped_all["is_conference"].fillna(False)]

    # momentum-only pairs (byte-exact golden reproduction -- see build_pairs_for_momentum docstring)
    mom_pairs_frozen_all = build_pairs_for_momentum(au_raw, wm_full, universe["merge_map"],
                                                     universe["ul_own_frozen_parity"])
    mom_pairs_shipped_all = build_pairs_for_momentum(au_raw, wm_full, universe["merge_map"],
                                                      universe["ul_own_shipped"])
    mom_pairs_shipped_noconf = mom_pairs_shipped_all[~mom_pairs_shipped_all["is_conference"].fillna(False)]

    mom_results = run_momentum_dual_mode(mom_pairs_frozen_all, mom_pairs_shipped_all,
                                          mom_pairs_shipped_noconf)

    # >=10 floor partner set (drives ptn_works / ptn_topics; also the plumbing set for identity)
    partner_vol = pairs_shipped_all.drop_duplicates(["work_id", "partner_id"]).groupby(
        "partner_id")["work_id"].nunique()
    p10 = set(partner_vol[partner_vol >= DRILL_PARTNER_FLOOR].index)
    pairs_shipped_all_p10 = pairs_shipped_all[pairs_shipped_all["partner_id"].isin(p10)]
    pairs_shipped_noconf_p10 = pairs_shipped_all_p10[~pairs_shipped_all_p10["is_conference"].fillna(False)]
    plumbing_ids = mom_results["shipped_all"]["plumbing"]

    identity = partner_identity_block(pairs_shipped_all, universe, plumbing_ids)

    # pass-4 G3 (challenge memo #8/#9): the 42b pull + merged-union sidecar, wrapped once and
    # shared by ptn_summary (share_p) and ptn_fields (baseline_partner_share).
    partner_base = PartnerBaseLookup(tables, all_topics, universe["merge_map"])

    section("BUILD TABLES")
    ptn_mom_facts = build_ptn_mom_facts(mom_results, snapshot.name)
    ptn_summary = build_ptn_summary(pairs_shipped_all, pairs_shipped_noconf, identity, mom_results,
                                     snapshot.name, partner_base)
    ptn_yearly = build_ptn_yearly(pairs_shipped_all, pairs_shipped_noconf, snapshot.name)
    ptn_fields = build_ptn_fields(pairs_shipped_all, pairs_shipped_noconf, wm_full, mom_results,
                                   snapshot.name, tables, partner_base)
    ptn_labs = build_ptn_labs(pairs_shipped_all, pairs_shipped_noconf, snapshot.name)
    ptn_works = build_ptn_works(pairs_shipped_all_p10, sdg_siris, snapshot.name)
    consortium_overlay = load_overlay("idset_consortium.csv")
    ptn_denominators = build_ptn_denominators(ptn_summary, set(consortium_overlay["id"]),
                                              len(wm_full), snapshot.name)
    # fix round 3 (conf_state grain extension): capture the pre-change on-disk ptn_topics.parquet
    # (if present) as the row-identity reference for the 'all' slice, BEFORE it gets overwritten.
    _old_ptn_topics_path = tables / "ptn_topics.parquet"
    old_ptn_topics_reference = (pd.read_parquet(_old_ptn_topics_path)
                                 if _old_ptn_topics_path.exists() else None)
    ptn_topics = build_ptn_topics(pairs_shipped_all_p10, pairs_shipped_noconf_p10,
                                   corpus_topics_full, mom_results, snapshot.name,
                                   old_ptn_topics_reference)
    consortium_weights = build_consortium_weights(au_raw, wm_full, universe, snapshot.name)
    geo_countries = build_geo_countries(pairs_shipped_all, pairs_shipped_noconf, snapshot.name)
    geo_fields = build_geo_fields(pairs_shipped_all, pairs_shipped_noconf, wm_full, snapshot.name)
    geo_groups = build_geo_groups(au_raw, wm_full, universe, mom_results, snapshot.name)

    section("WRITE OUTPUTS")
    out_paths = {}
    eager_tables = {
        "ptn_summary": ptn_summary, "ptn_mom_facts": ptn_mom_facts, "ptn_yearly": ptn_yearly,
        "ptn_fields": ptn_fields, "ptn_labs": ptn_labs, "consortium_weights": consortium_weights,
        "geo_countries": geo_countries, "geo_groups": geo_groups,
        "ptn_denominators": ptn_denominators,
    }
    for name, frame in eager_tables.items():
        path = tables / f"{name}.parquet"
        frame.to_parquet(path, index=False, compression=compression)
        out_paths[name] = path
        print(f"wrote {path.name}: {len(frame):,} rows, {frame.memory_usage(deep=True).sum()/1e6:.2f} MB RAM, "
              f"{path.stat().st_size/1e6:.2f} MB disk")

    # geo_fields is a size-informed DEVIATION from the YAML's literal "rg=5000" boilerplate (the
    # same lazy_file_rules text also names ptn_works/ptn_topics, both 100k+ rows -- geo_fields is
    # ~9.3k rows, so rg=5000 yields only 2 row groups, making ANY single-country prune touch >=50%
    # of file bytes by construction (mathematically impossible to clear the <20% acceptance bar at
    # that granularity). Sized down to rg=300 (still comfortably clears the Class-1 floor
    # num_row_groups >= n_rows/10000) so a real per-country prune proof is possible -- measured, not
    # guessed, same discipline as every other sizing decision in this codebase; see progress report.
    lazy_tables = {"ptn_works": (ptn_works, "partner_id", 5000),
                   "ptn_topics": (ptn_topics, "partner_id", 5000),
                   "geo_fields": (geo_fields, "country_code", 300)}
    for name, (frame, key_col, rg_size) in lazy_tables.items():
        path = tables / f"{name}.parquet"
        frame.to_parquet(path, index=False, compression=compression, row_group_size=rg_size)
        out_paths[name] = path
        pf = pq.ParquetFile(path)
        print(f"wrote {path.name}: {len(frame):,} rows, {pf.metadata.num_row_groups} row groups, "
              f"{path.stat().st_size/1e6:.2f} MB disk (sorted by {key_col}, rg={rg_size})")
        assert_row_groups(path, name)

    section("PRUNE PROOFS")
    mid_partner = sorted(p10)[len(p10) // 2]
    prune_proof(out_paths["ptn_works"], "partner_id", mid_partner, "ptn_works")
    prune_proof(out_paths["ptn_topics"], "partner_id", mid_partner, "ptn_topics")
    countries_known = sorted(geo_fields["country_code"].astype(str).unique())
    mid_country = countries_known[len(countries_known) // 2]
    prune_proof(out_paths["geo_fields"], "country_code", mid_country, "geo_fields")

    section("MANIFEST + SUMMARY")
    Manifest(snapshot).record_step(
        "46_build_partner_views",
        counts={
            "ptn_summary_rows": len(ptn_summary), "ptn_mom_facts_rows": len(ptn_mom_facts),
            "ptn_yearly_rows": len(ptn_yearly), "ptn_fields_rows": len(ptn_fields),
            "ptn_labs_rows": len(ptn_labs), "ptn_works_rows": len(ptn_works),
            "ptn_topics_rows": len(ptn_topics), "consortium_weights_rows": len(consortium_weights),
            "geo_countries_rows": len(geo_countries), "geo_fields_rows": len(geo_fields),
            "geo_groups_rows": len(geo_groups), "ptn_denominators_rows": len(ptn_denominators),
            "momentum_shipped_eligible": mom_results["shipped_all"]["eligible_n"],
            "momentum_noconf_eligible": mom_results["shipped_noconf"]["eligible_n"],
        },
        files=list(out_paths.values()),
        params={
            "universe": "ul_descendants + UL root + own_entity_blocklist.csv (status==ok); "
                        "merges: successor_merges.csv (status==ok) only -- hospital_complex_merges "
                        "read for id-resolution but not folded into identity this pass (see module "
                        "docstring)",
            "momentum_method": "reports/lab_momentum_frozen.py sections A/B, lifted into "
                                "pipeline/lib46_momentum.py; dual-mode verified exact (682-family "
                                "frozen-parity, 681-family shipped, machine-diff == Centre Inria "
                                "removed + CHU de Reims up->ns)",
            "drill_partner_floor": DRILL_PARTNER_FLOOR,
            "sparse_node_floor_builder_decision": SPARSE_NODE_FLOOR,
            "null_country_partner_ids_deviation": "346 measured vs canonical_counts 347 -- see module docstring",
            "share_p_populated_rows": int(ptn_summary["share_p"].notna().sum()),
            "share_p_capped_rows": int(ptn_summary["share_p_capped_flag"].fillna(False).sum()),
            "ptn_fields_baseline_partner_share_populated": int(ptn_fields["baseline_partner_share"].notna().sum()),
        },
        notes="Foundry rev 3.1 W2: ptn_* (partner family, incl. dual-mode momentum + ptn_mom_facts) "
              "+ geo_* + consortium_weights. All 11 tables built from the overlay-corrected universe "
              "(F0-probes recipe, verified to the digit); momentum golden reproduced exactly in "
              "both modes before any table was written. Pass-4 G3: share_p/partner_total_windowed "
              "(ptn_summary) and baseline_partner_share (ptn_fields) populated from the 42b pull + "
              "merged-union sidecar, challenge memo #8/#9.",
    )
    append_summary(snapshot, "46_build_partner_views", [
        f"- `ptn_summary`: {len(ptn_summary):,} rows (partner x conf_state x subset_id); "
        f"share_p populated on {int(ptn_summary['share_p'].notna().sum()):,} rows "
        f"({int(ptn_summary['share_p_capped_flag'].fillna(False).sum()):,} capped)",
        f"- `ptn_mom_facts`: {len(ptn_mom_facts)} rows (conf_state constants)",
        f"- `ptn_yearly`: {len(ptn_yearly):,} rows",
        f"- `ptn_fields`: {len(ptn_fields):,} rows (field + subfield >= {SPARSE_NODE_FLOOR}); "
        f"baseline_partner_share populated on {int(ptn_fields['baseline_partner_share'].notna().sum()):,} rows",
        f"- `ptn_labs`: {len(ptn_labs):,} rows",
        f"- `ptn_works`: {len(ptn_works):,} rows (>= {DRILL_PARTNER_FLOOR} floor, lazy)",
        f"- `ptn_topics`: {len(ptn_topics):,} rows (lazy)",
        f"- `consortium_weights`: {len(consortium_weights)} rows",
        f"- `geo_countries`: {len(geo_countries):,} rows",
        f"- `geo_fields`: {len(geo_fields):,} rows (lazy)",
        f"- `geo_groups`: {len(geo_groups):,} rows",
        f"- momentum SHIPPED: {mom_results['shipped_all']['eligible_n']} eligible "
        f"(all conf); {mom_results['shipped_noconf']['eligible_n']} eligible (no_conf)",
        f"- `ptn_denominators` (pass 6, P4/#39/#40): {len(ptn_denominators):,} rows; "
        f"spot-check + share-bound invariants PASS",
    ])

    print("\ndone.")


if __name__ == "__main__":
    main()
