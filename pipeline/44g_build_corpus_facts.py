"""44g_build_corpus_facts.py -- dim_corpus_facts.parquet (Foundry wave 0 SHIPPED + W0b delta,
chain pass 3, Assembly Line stream W0b).

Kills the unconditional `ul_pubs` slim read that backed the corpus-level "N works excluded
(thin stratum)" disclosure on ALL THREE live data pages (`pages/1:876`, `pages/3:284`,
`pages/4:327`, all via `lib/thematic.excluded_counts` -> `get_pubs_slim()`), per
docs/foundry/DATA_FOUNDATION_draft.md section 3 and docs/foundry/CHALLENGE_MEMO.md #1/#2/#14.
A cold visit to any of the three pages no longer needs to pin the ~21.9 MB in-RAM ul_pubs slim
frame just to show a footer count; `dim_corpus_facts` (a few KB, 2 rows) replaces it.

W0b delta (docs/foundry/data_foundation.yaml rev 3.1, producers.44g_build_corpus_facts.py,
w0b_delta note -- authoritative):
  - `_xa` twins of the 4 base work-count facts, computed over the corpus MINUS every work whose
    PRIMARY topic sits in the 811-topic "Filter out" list. `lib/artifact.py` (parallel stream W1)
    does not exist yet, so the mask is loaded IN PLACE here (`load_artifact_topic_ids()`), not
    copied in and not imported -- W1 owns the eventual copy-in + shared helper.
  - `ul_intl_share` / `ul_company_share` (+ `_xa` twins): mean of works_master's own
    `Is_international` / `Is_company` per-work booleans over the conf_state scope -- no fresh
    derivation needed, both columns already ride works_master.
  - `momentum_recentring_median`: the frozen 1.061 disclosure value now lands on the 'all' row
    ONLY. The 'no_conf' row is NULL (pandas NA) -- the previously-deployed 1.061 on BOTH rows was
    wrong (tunnel #3): `reports/lab_momentum_frozen.py` never varies this by conference-toggle
    state, so copying its single value onto the no_conf row silently implied a per-variant median
    that was never computed. The real per-variant medians land in `ptn_mom_facts`
    (46_build_partner_views.py, wave 2); until then, no_conf is honestly unknown rather than
    silently duplicated.
  - `france_intl_*`: NOT re-pulled ($0 API, this stream's scope fence). Carried forward from the
    currently-deployed `Streamlit/data/dim_corpus_facts.parquet` (falls back to the snapshot's own
    copy if nothing is deployed yet) -- see `load_france_from_deployed()`. `--refresh-france`
    re-enables the original API pull below but defaults OFF and is not exercised by this stream.

Grain: conf_state in {all, no_conf} -- one row per conference-toggle state, scalar facts as
columns (per docs/foundry/data_foundation_draft.yaml's dim_corpus_facts entry).

Facts, per conf_state:
  corpus_works                 -- total corpus works in that state
  works_excluded_thin_stratum  -- works whose indicator_status != 'computed' (D53 denominator)
  works_with_indicators        -- corpus_works - works_excluded_thin_stratum
  corpus_collaborative_works   -- works with >=1 authorship institution OUTSIDE the UL family
                                   (docs/partner_views_indicator_plan.md:229 definition: "works
                                   with >=1 external partner"). "UL family" = every
                                   ul_descendants.openalex_id + the UL root id itself +
                                   inputs/overlays/own_entity_blocklist.csv (status==ok) -- the
                                   same id-set idiom reports/lab_momentum_frozen.py uses for its
                                   `ul_own` set. NOT the momentum script's ul_own verbatim: that
                                   script additionally EXEMPTS one blocklist row
                                   (I4210127166, frozen_momentum_v2_exempt=yes) so its own
                                   published 682-partner momentum numbers keep reproducing --
                                   an artifact of THAT already-published number, not a general
                                   own/external ruling. dim_corpus_facts is a new fact with no
                                   prior published value to preserve, so it uses the full,
                                   un-exempted blocklist (the "own_entity_blocklist" comment on
                                   that row already says this exemption should not carry forward
                                   to any future consumer, e.g. 46_build_partner_views.py).
  corpus_works_xa,                (W0b) the same four facts above, recomputed over the corpus
  works_excluded_thin_stratum_xa, MINUS every work whose PRIMARY topic is in the 811-topic
  works_with_indicators_xa,       "Filter out" list (`load_artifact_topic_ids()` below) -- the
  corpus_collaborative_works_xa   R-A artifact mask, twinned per docs/foundry/data_foundation.yaml
                                   rev 3.1's ARTIFACT-FLAG convention. Expect exactly 4,106 flagged
                                   works / 11.15% of 36,819 corpus-wide (both conf_state rows drop
                                   their OWN flagged subset, not a shared absolute count).
  ul_intl_share, ul_company_share -- (W0b) mean of works_master.Is_international /
                                   works_master.Is_company over this conf_state's scope (both
                                   already per-work booleans on works_master -- no re-derivation).
                                   Ballpark (conf=all, base): 0.427 / 0.065.
  ul_intl_share_xa,                (W0b) the same two shares, recomputed over the corpus minus
  ul_company_share_xa              artifact-flagged works (same mask as the *_xa work counts above).
  france_intl_share             -- France's international-collaboration share over the SAME scope
                                   as the France baseline (publication years 2019-2023, FR-affiliated
                                   works, corpus doc-type list -- WITH conference-paper for
                                   conf_state=all, WITHOUT it for conf_state=no_conf). "International"
                                   = the work's `countries_distinct_count` > 1 (more than one
                                   distinct country among its authorship institutions -- the same
                                   OpenAlex field ul_pubs.countries_distinct_count already carries
                                   per-work). NOT locally derivable (docs/foundry/CHALLENGE_MEMO.md
                                   #6d: the france_20xx shards carry no country/international flag) --
                                   pulled fresh from the OpenAlex API, 2 group_by calls
                                   (~$0.0001 each, filter-shaped, never `search=`; see "OPENALEX
                                   PULL" below). Numerator/denominator are stored as their own
                                   columns (france_intl_works, france_total_works), never only the
                                   ratio.
  momentum_recentring_median    -- WORKSHOP-TUNABLE CONSTANT, frozen, NOT recomputed here (see block
                                   below). (W0b) lands ONLY on the 'all' row; the 'no_conf' row is
                                   NULL -- see the W0b delta note above (the previously-shipped
                                   1.061 on BOTH rows was wrong, tunnel #3).
  snapshot_date                -- the active snapshot id (config.yaml project.snapshot_id).

OPENALEX PULL (france_intl_share)
  2 calls total, one per conf_state, each `group_by=countries_distinct_count` (a plain WORK field,
  not `authorships.countries_distinct_count` -- that nested path 400s; verified live 2026-08-15)
  filtered on `authorships.institutions.country_code:FR` (config.france_baseline.country_filter,
  the exact string the France baseline pull already uses) + the year window + the conf_state's
  doc-type list. `per_page=200` (the OpenAlex per-request max) is REQUIRED: per_page=1 truncates
  the group_by result to a single bucket (verified live -- at per_page=1 the response's own
  `groups_count` still says 80 groups exist but only 1 comes back), silently under-counting the
  international share. At per_page=200 sum(group counts) == meta.count exactly for both states
  (verified 2026-08-15: 1,100,468 and 890,928), so no bucket is lost to the 200-group cap this
  corpus size needs. `meta.cost_usd` is read off every response, never assumed.

Usage: python pipeline/44g_build_corpus_facts.py [--snapshot 2026-08-11] [--refresh-france]
  --refresh-france re-calls OpenAlex for france_intl_share (2 group_by calls, ~$0.0002). Defaults
  OFF: this stream carries the already-stored values forward at $0 API (see
  `load_france_from_deployed()`); the flag exists for a future first-ever build or a deliberate
  refresh, and is NOT exercised by this stream.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.openalex import OpenAlexClient, ascii_safe_stdout, load_env  # noqa: E402
from lib.snapshot import Manifest, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
CONFIG = load_config(ROOT)

CONF_STATES = ["all", "no_conf"]

# ---------------------------------------------------------------------------------------------
# Workshop-tunable constants live in config.yaml (`workshop_tunables:` block, Foundry rev 3 §9);
# this script READS the frozen value, never derives it.
#
# Frozen source: reports/lab_momentum_frozen.py, section A, "recentring median ratio" -- the
# median of (window-2-share / window-1-share) over the 682 eligible partners on snapshot
# 2026-08-11, conf_state=all (the script does not vary this by conference-toggle state).
# Re-verified live 2026-08-15 by re-running that script: prints "recentring median ratio: 1.061"
# unchanged. DO NOT recompute it here -- it is a frozen, workshop-ratified number
# (docs/foundry/INDICATOR_INVENTORY.md I4: "1.061, disclosed"), not a fact this builder derives.
#
# W0b (chain pass 3, tunnel #3): this frozen value is stored ONLY on the 'all' row below. It is
# NO LONGER copied onto the 'no_conf' row -- the frozen script was never run per conference-toggle
# state, so the previously-deployed 1.061 on both rows silently implied a no_conf-specific median
# that was never computed. 'no_conf' is set to NULL (pandas NA) here until momentum is recomputed
# per state in wave 2's ptn_mom_facts.
# ---------------------------------------------------------------------------------------------
MOMENTUM_RECENTRING_MEDIAN = float(CONFIG["workshop_tunables"]["momentum_recentring_median"])
assert MOMENTUM_RECENTRING_MEDIAN == 1.061, (
    "workshop_tunables.momentum_recentring_median changed from the frozen 1.061 -- "
    "if this is a ratified workshop decision, update this assert alongside the golden "
    "expectations in reports/lab_momentum_frozen.py; otherwise revert config.yaml."
)


def doc_types_for(conf_state: str) -> list[str]:
    """Corpus doc-type list for this state -- conference-paper IN for 'all', OUT for 'no_conf'."""
    all_types = CONFIG["corpus_filter"]["doc_types_keep"]
    assert all_types == CONFIG["france_baseline"]["doc_types"], (
        "corpus_filter.doc_types_keep must mirror france_baseline.doc_types (D36 scope-mirror "
        "invariant) or france_intl_share would be scoped differently from the local corpus facts"
    )
    if conf_state == "all":
        return list(all_types)
    return [t for t in all_types if t != "conference-paper"]


# ==================================================================== artifact mask (W0b, inline)
BAD_TOPICS_XLSX = (
    ROOT.parents[2] / "Internal Projects" / "Research Portfolio Framework"
    / "ETO vs OpenAlex experiment" / "data" / "openalex" / "OA_bad_topics.xlsx"
)


def load_artifact_topic_ids() -> set[str]:
    """The 811-topic "Filter out" artifact mask, read IN PLACE (NOT copied into this project --
    `lib/artifact.py` does not exist yet; parallel stream W1 owns the eventual copy-in + shared
    helper per docs/foundry/data_foundation.yaml rev 3.1). Column 'Topic ID no url' carries the
    bare T-prefixed id in the same format as works_master.primary_topic_id (e.g. 'T11162')."""
    df = pd.read_excel(BAD_TOPICS_XLSX, usecols=["Topic ID no url", "Should we keep this OA topic?"])
    bad = df.loc[df["Should we keep this OA topic?"] == "Filter out", "Topic ID no url"]
    ids = set(bad.astype(str))
    assert len(ids) == 811, (
        f"expected 811 'Filter out' topics in {BAD_TOPICS_XLSX.name}, found {len(ids)} -- "
        "source file changed since the W0b spec was written"
    )
    return ids


def flag_artifact_works(works: pd.DataFrame, bad_topic_ids: set[str]) -> pd.Series:
    """Per-work artifact flag: True where the work's PRIMARY topic sits in the bad-topics list.
    Expect exactly 4,106 flagged / 11.15% of 36,819 over the whole corpus (both conf_state rows
    drop their own flagged subset of this same per-work flag -- not a shared absolute count)."""
    flag = works["primary_topic_id"].astype(str).isin(bad_topic_ids)
    return flag


# ============================================================================ local facts (L0)
def load_own_ids() -> set[str]:
    """UL + every OpenAlex descendant + the curated own-entity overlay (status==ok) -- the
    'internal to UL' id-set an authorship institution must sit OUTSIDE of to count this work as
    collaborative. Same idiom as reports/lab_momentum_frozen.py's `ul_own` (minus that script's
    single-row momentum-only exemption -- see module docstring)."""
    desc = pd.read_parquet(TABLES / "ul_descendants.parquet", columns=["openalex_id"])
    block = pd.read_csv(
        ROOT / "inputs" / "overlays" / "own_entity_blocklist.csv", encoding="utf-8", keep_default_na=False
    )
    own = set(desc["openalex_id"].astype(str)) | {CONFIG["perimeter"]["ul_openalex_id"]}
    own |= set(block.loc[block["status"] == "ok", "id"])
    return own


def local_facts_for_state(conf_state: str, works: pd.DataFrame, authorships: pd.DataFrame,
                           own_ids: set[str]) -> dict:
    """`works` must already carry the per-work boolean `artifact_flag` column (W0b)."""
    scoped = works if conf_state == "all" else works[~works["is_conference"].fillna(False)]
    corpus_works = int(len(scoped))
    excluded = int((scoped["indicator_status"] != "computed").sum())
    with_indicators = corpus_works - excluded

    scoped_ids = set(scoped["work_id"])
    ext_rows = authorships[~authorships["institution_id"].isin(own_ids)].dropna(subset=["institution_id"])
    collaborative = int(len(set(ext_rows["work_id"]) & scoped_ids))

    # -- W0b: _xa twins -- same four facts, corpus minus primary-topic-flagged works ------------
    scoped_xa = scoped[~scoped["artifact_flag"]]
    corpus_works_xa = int(len(scoped_xa))
    excluded_xa = int((scoped_xa["indicator_status"] != "computed").sum())
    with_indicators_xa = corpus_works_xa - excluded_xa
    scoped_xa_ids = set(scoped_xa["work_id"])
    collaborative_xa = int(len(set(ext_rows["work_id"]) & scoped_xa_ids))

    # -- W0b: ul_intl_share / ul_company_share (+ _xa) -- both are already per-work booleans on
    # works_master (Is_international, Is_company); no fresh derivation needed.
    ul_intl_share = float(scoped["Is_international"].mean()) if corpus_works else float("nan")
    ul_company_share = float(scoped["Is_company"].mean()) if corpus_works else float("nan")
    ul_intl_share_xa = float(scoped_xa["Is_international"].mean()) if corpus_works_xa else float("nan")
    ul_company_share_xa = float(scoped_xa["Is_company"].mean()) if corpus_works_xa else float("nan")

    return {
        "conf_state": conf_state,
        "corpus_works": corpus_works,
        "corpus_works_xa": corpus_works_xa,
        "works_excluded_thin_stratum": excluded,
        "works_excluded_thin_stratum_xa": excluded_xa,
        "works_with_indicators": with_indicators,
        "works_with_indicators_xa": with_indicators_xa,
        "corpus_collaborative_works": collaborative,
        "corpus_collaborative_works_xa": collaborative_xa,
        "ul_intl_share": ul_intl_share,
        "ul_intl_share_xa": ul_intl_share_xa,
        "ul_company_share": ul_company_share,
        "ul_company_share_xa": ul_company_share_xa,
    }


def assert_matches_live_app(local: dict) -> None:
    """
    Reproduce EXACTLY what `lib.thematic.excluded_counts(include_conference)` returns TODAY from
    the DEPLOYED `Streamlit/data/ul_pubs.parquet` -- the same file/columns `get_pubs_slim()`
    reads -- and assert it equals the snapshot-based computation above. This is the "extract the
    current values first and assert equality" step: if the deployed file and the snapshot ever
    disagree, this build must fail loudly rather than silently ship a footer that contradicts
    what the app used to show.
    """
    deployed_path = ROOT / "Streamlit" / "data" / "ul_pubs.parquet"
    if not deployed_path.is_file():
        print(f"  ! {deployed_path} not deployed yet -- skipping live cross-check for this run")
        return
    df = pd.read_parquet(deployed_path, columns=["is_conference", "indicator_status"])
    scoped = df if local["conf_state"] == "all" else df[~df["is_conference"].fillna(False)]
    live_total = int(len(scoped))
    live_excluded = int((scoped["indicator_status"] != "computed").sum())
    assert live_total == local["corpus_works"], (
        f"{local['conf_state']}: snapshot corpus_works={local['corpus_works']} != deployed "
        f"ul_pubs.parquet total={live_total} -- the live app and the snapshot have diverged"
    )
    assert live_excluded == local["works_excluded_thin_stratum"], (
        f"{local['conf_state']}: snapshot works_excluded_thin_stratum="
        f"{local['works_excluded_thin_stratum']} != deployed ul_pubs.parquet excluded={live_excluded}"
    )
    print(f"  OK: {local['conf_state']} reproduces the deployed ul_pubs.parquet exactly "
          f"(total={live_total:,}, excluded={live_excluded:,})")


# ======================================================================= france_intl_share (API)
def pull_france_intl_share(client: OpenAlexClient, conf_state: str) -> dict:
    country_filter = CONFIG["france_baseline"]["country_filter"]
    yfrom, yto = CONFIG["window"]["year_from"], CONFIG["window"]["year_to"]
    types = doc_types_for(conf_state)
    filter_string = (
        f"{country_filter},type:{'|'.join(types)},"
        f"from_publication_date:{yfrom}-01-01,to_publication_date:{yto}-12-31"
    )
    # per_page=200 is REQUIRED here -- see module docstring "OPENALEX PULL".
    response = client.get("/works", filter=filter_string, group_by="countries_distinct_count",
                          per_page=200)
    groups = response.get("group_by", [])
    total = int(response["meta"]["count"])
    sum_groups = sum(int(g["count"]) for g in groups)
    intl = sum(int(g["count"]) for g in groups if g["key"] not in (None, "1"))
    assert sum_groups == total, (
        f"{conf_state}: group_by buckets sum to {sum_groups}, meta.count says {total} -- "
        f"the 200-group cap lost a bucket ({len(groups)} groups returned), re-check the corpus size"
    )
    cost = float(response["meta"].get("cost_usd") or 0.0)
    print(f"  OpenAlex call ({conf_state}): GET /works?filter={filter_string}"
          f"&group_by=countries_distinct_count&per_page=200")
    print(f"    -> meta.count={total:,}  international={intl:,}  cost_usd={cost}")
    return {
        "conf_state": conf_state,
        "filter": filter_string,
        "france_total_works": total,
        "france_intl_works": intl,
        "france_intl_share": intl / total if total else float("nan"),
        "cost_usd": cost,
    }


# ================================================================= france_intl_share (W0b carry-forward)
def load_france_from_deployed(tables_dir: Path) -> dict:
    """W0b (chain pass 3, $0 API scope fence): read the ALREADY-STORED france_intl_* values from
    the currently-deployed Streamlit/data/dim_corpus_facts.parquet instead of re-calling OpenAlex.
    Falls back to the snapshot's own copy (`tables_dir/dim_corpus_facts.parquet`, written by a
    prior run of this same script) if nothing is deployed yet. NOT exercised unless
    --refresh-france is passed (default OFF)."""
    deployed_path = ROOT / "Streamlit" / "data" / "dim_corpus_facts.parquet"
    source = deployed_path if deployed_path.is_file() else tables_dir / "dim_corpus_facts.parquet"
    if not source.is_file():
        raise SystemExit(
            "no existing dim_corpus_facts.parquet found (neither deployed nor snapshot copy) to "
            "carry france_intl_* forward from -- pass --refresh-france for a first-ever build"
        )
    prior = pd.read_parquet(source, columns=["conf_state", "france_intl_works",
                                              "france_total_works", "france_intl_share"])
    print(f"  france_intl_*: carried forward from {source} (NO API call -- W0b scope fence)")
    out = {}
    for s in CONF_STATES:
        match = prior.loc[prior["conf_state"] == s]
        assert len(match) == 1, (
            f"{s}: expected exactly one prior dim_corpus_facts row in {source}, found {len(match)}"
        )
        r = match.iloc[0]
        out[s] = {
            "conf_state": s,
            "france_intl_works": int(r["france_intl_works"]),
            "france_total_works": int(r["france_total_works"]),
            "france_intl_share": float(r["france_intl_share"]),
            "filter": f"carried forward from {source.name} (no API call, W0b)",
            "cost_usd": 0.0,
        }
        print(f"    {s}: france_total_works={out[s]['france_total_works']:,}  "
              f"france_intl_works={out[s]['france_intl_works']:,}  "
              f"france_intl_share={out[s]['france_intl_share']:.6f}")
    return out


def main() -> None:
    global TABLES
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--refresh-france", action="store_true",
                         help="re-call OpenAlex for france_intl_share (2 group_by calls, "
                              "~$0.0002). Default OFF: W0b carries the already-stored values "
                              "forward at $0 API -- see load_france_from_deployed().")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    TABLES = snapshot / "tables"

    print(f"snapshot {snapshot.name}: building dim_corpus_facts.parquet")

    # ---- local facts (L0, $0) --------------------------------------------------------------
    works = pd.read_parquet(TABLES / "works_master.parquet",
                            columns=["work_id", "is_conference", "indicator_status",
                                     "primary_topic_id", "Is_international", "Is_company"])
    authorships = pd.read_parquet(TABLES / "corpus_authorships.parquet",
                                  columns=["work_id", "institution_id"])
    own_ids = load_own_ids()
    print(f"  own-entity id-set (UL descendants + root + blocklist): {len(own_ids)} ids")

    # ---- W0b: artifact mask (inline -- lib/artifact.py not built yet by parallel stream W1) ----
    bad_topic_ids = load_artifact_topic_ids()
    works = works.copy()
    works["artifact_flag"] = flag_artifact_works(works, bad_topic_ids)
    n_flagged = int(works["artifact_flag"].sum())
    pct_flagged = n_flagged / len(works)
    print(f"  artifact mask: {n_flagged:,} / {len(works):,} corpus works flagged "
          f"({pct_flagged:.2%}) -- primary topic in the 811-topic 'Filter out' list")
    assert n_flagged == 4106, f"expected exactly 4,106 artifact-flagged works, got {n_flagged:,}"
    assert abs(pct_flagged - 0.1115) < 0.0001, f"expected ~11.15% flagged, got {pct_flagged:.4%}"

    # ---- pass 6 (S-NC cross-stream request, NARRATIVE_CONTRACT_pass6.md sec.5): raw_pull_works --
    # the raw OpenAlex pull count BEFORE 11_filter_corpus.py's doc-type/retraction/paratext/title
    # rules (the "46,404" family fact) -- the one number on the app's corpus-size caption that
    # cannot be derived from any DEPLOYED table (every deployed table is already post-filter). Read
    # directly off 10_pull_lorraine.py's own output row count so it is never a hand-copied constant.
    # Same value on both conf_state rows (a corpus-level constant, computed before any
    # conference-toggle split exists).
    raw_pull_path = TABLES / "works.parquet"
    if raw_pull_path.exists():
        raw_pull_works = int(pq.ParquetFile(raw_pull_path).metadata.num_rows)
        print(f"  raw_pull_works (pre-filter, {raw_pull_path.name}): {raw_pull_works:,}")
    else:
        raw_pull_works = None
        print(f"  ! {raw_pull_path} not found -- raw_pull_works will be NULL "
              f"(re-run from step 10 to populate; 11_filter_corpus.py never deletes it)")

    local_rows = {s: local_facts_for_state(s, works, authorships, own_ids) for s in CONF_STATES}
    for s in CONF_STATES:
        r = local_rows[s]
        print(f"  {s}: corpus_works={r['corpus_works']:,}  excluded_thin_stratum="
              f"{r['works_excluded_thin_stratum']:,}  with_indicators={r['works_with_indicators']:,}  "
              f"collaborative_works={r['corpus_collaborative_works']:,}")
        print(f"      xa: corpus_works_xa={r['corpus_works_xa']:,}  "
              f"excluded_thin_stratum_xa={r['works_excluded_thin_stratum_xa']:,}  "
              f"with_indicators_xa={r['works_with_indicators_xa']:,}  "
              f"collaborative_works_xa={r['corpus_collaborative_works_xa']:,}")
        print(f"      ul_intl_share={r['ul_intl_share']:.6f} (xa {r['ul_intl_share_xa']:.6f})  "
              f"ul_company_share={r['ul_company_share']:.6f} (xa {r['ul_company_share_xa']:.6f})")
        assert_matches_live_app(r)

    # ---- france_intl_share -- W0b carries forward, --refresh-france re-pulls ($0 by default) ---
    if args.refresh_france:
        env = load_env(CONFIG["secrets"]["env_file"], CONFIG["secrets"]["required"])
        client = OpenAlexClient(CONFIG, env)
        api_rows = {s: pull_france_intl_share(client, s) for s in CONF_STATES}
        total_cost = sum(r["cost_usd"] for r in api_rows.values())
        print(f"  OpenAlex calls: {client.calls}  total cost_usd: {total_cost}")
        assert total_cost <= 0.001, f"france_intl_share cost {total_cost} exceeds the $0.001 wave-0 budget"
        api_calls_recorded = client.calls
    else:
        api_rows = load_france_from_deployed(TABLES)
        total_cost = 0.0
        api_calls_recorded = 0

    # ---- assemble dim_corpus_facts.parquet -------------------------------------------------
    rows = []
    for s in CONF_STATES:
        row = {**local_rows[s]}
        api = api_rows[s]
        row["france_intl_works"] = api["france_intl_works"]
        row["france_total_works"] = api["france_total_works"]
        row["france_intl_share"] = api["france_intl_share"]
        row["momentum_recentring_median"] = MOMENTUM_RECENTRING_MEDIAN if s == "all" else float("nan")
        row["raw_pull_works"] = raw_pull_works
        row["snapshot_date"] = snapshot.name
        rows.append(row)

    frame = pd.DataFrame(rows)[[
        "conf_state",
        "corpus_works", "corpus_works_xa",
        "works_excluded_thin_stratum", "works_excluded_thin_stratum_xa",
        "works_with_indicators", "works_with_indicators_xa",
        "corpus_collaborative_works", "corpus_collaborative_works_xa",
        "ul_intl_share", "ul_intl_share_xa", "ul_company_share", "ul_company_share_xa",
        "france_intl_share", "france_intl_works", "france_total_works",
        "momentum_recentring_median", "raw_pull_works", "snapshot_date",
    ]]
    frame = frame.astype({
        "conf_state": "string", "snapshot_date": "string",
        "corpus_works": "int64", "corpus_works_xa": "int64",
        "works_excluded_thin_stratum": "int64", "works_excluded_thin_stratum_xa": "int64",
        "works_with_indicators": "int64", "works_with_indicators_xa": "int64",
        "corpus_collaborative_works": "int64", "corpus_collaborative_works_xa": "int64",
        "ul_intl_share": "float64", "ul_intl_share_xa": "float64",
        "ul_company_share": "float64", "ul_company_share_xa": "float64",
        "france_intl_works": "int64", "france_total_works": "int64",
        "france_intl_share": "float64", "momentum_recentring_median": "float64",
        "raw_pull_works": "Int64",
    })

    assert frame["conf_state"].is_unique, "conf_state must be unique (2 rows: all, no_conf)"
    assert len(frame) == 2, f"expected exactly 2 rows, got {len(frame)}"
    assert (frame["works_with_indicators"] + frame["works_excluded_thin_stratum"]
            == frame["corpus_works"]).all(), "works_with_indicators + excluded must equal corpus_works"
    assert (frame["works_with_indicators_xa"] + frame["works_excluded_thin_stratum_xa"]
            == frame["corpus_works_xa"]).all(), "xa: with_indicators + excluded must equal corpus_works_xa"
    assert (frame["corpus_works_xa"] <= frame["corpus_works"]).all(), (
        "xa corpus (artifact-excluded) cannot exceed the full corpus"
    )
    assert (frame["corpus_collaborative_works"] <= frame["corpus_works"]).all(), (
        "collaborative works cannot exceed the corpus total"
    )
    assert (frame["corpus_collaborative_works_xa"] <= frame["corpus_works_xa"]).all(), (
        "xa collaborative works cannot exceed the xa corpus total"
    )
    assert frame["france_intl_share"].between(0, 1).all(), "france_intl_share out of [0,1]"
    assert frame[["ul_intl_share", "ul_intl_share_xa", "ul_company_share",
                  "ul_company_share_xa"]].apply(lambda c: c.between(0, 1)).all().all(), (
        "ul_intl_share/ul_company_share (+ xa) must be in [0,1]"
    )
    all_row = frame.loc[frame["conf_state"] == "all", "momentum_recentring_median"].iloc[0]
    no_conf_row = frame.loc[frame["conf_state"] == "no_conf", "momentum_recentring_median"].iloc[0]
    assert all_row == 1.061, f"'all' row momentum_recentring_median must stay frozen at 1.061, got {all_row}"
    assert pd.isna(no_conf_row), (
        f"'no_conf' row momentum_recentring_median must be NULL (W0b, tunnel #3), got {no_conf_row}"
    )
    if raw_pull_works is not None:
        assert (frame["corpus_works"] <= raw_pull_works).all(), (
            f"corpus_works exceeds raw_pull_works ({raw_pull_works}) -- filtering cannot ADD works"
        )
        assert raw_pull_works == CONFIG["perimeter"]["expected_works_a"], (
            f"raw_pull_works {raw_pull_works:,} != config.perimeter.expected_works_a "
            f"{CONFIG['perimeter']['expected_works_a']:,} -- drift from the snapshot-dated expectation"
        )

    # ---- W0b acceptance #2: base columns byte-identical to the previously deployed values ------
    old_deployed_path = ROOT / "Streamlit" / "data" / "dim_corpus_facts.parquet"
    base_cols = ["corpus_works", "works_excluded_thin_stratum", "works_with_indicators",
                 "corpus_collaborative_works", "france_intl_works", "france_total_works",
                 "france_intl_share"]
    if old_deployed_path.is_file():
        old = pd.read_parquet(old_deployed_path).set_index("conf_state")
        new_indexed = frame.set_index("conf_state")
        for s in CONF_STATES:
            for col in base_cols:
                old_v, new_v = old.loc[s, col], new_indexed.loc[s, col]
                same = abs(old_v - new_v) < 1e-9 if isinstance(old_v, float) else old_v == new_v
                assert same, f"{s}.{col}: previously deployed {old_v!r} -> new {new_v!r} (NOT byte-identical)"
        print(f"  BASE-COLUMN CHECK: {base_cols} byte-identical to previously deployed "
              f"dim_corpus_facts.parquet on both rows (france_* included)")
    else:
        print("  ! no previously deployed dim_corpus_facts.parquet found -- skipping byte-identical check")

    out = TABLES / "dim_corpus_facts.parquet"
    frame.to_parquet(out, index=False, compression=CONFIG["storage"]["compression"])
    print(f"\nwrote {out} ({len(frame)} rows, {len(frame.columns)} columns)")
    print(frame.to_string(index=False))

    Manifest(snapshot).record_step(
        "44g_build_corpus_facts",
        filters={s: api_rows[s]["filter"] for s in CONF_STATES},
        select="countries_distinct_count (group_by)",
        api_base=CONFIG["openalex"]["base_url"],
        api_calls=api_calls_recorded,
        counts={
            f"{s}_corpus_works": local_rows[s]["corpus_works"] for s in CONF_STATES
        } | {
            f"{s}_corpus_works_xa": local_rows[s]["corpus_works_xa"] for s in CONF_STATES
        } | {
            f"{s}_france_total_works": api_rows[s]["france_total_works"] for s in CONF_STATES
        } | {
            "artifact_flagged_works": n_flagged,
        },
        files=[out],
        params={
            "momentum_recentring_median": MOMENTUM_RECENTRING_MEDIAN,
            "momentum_recentring_median_source": "reports/lab_momentum_frozen.py section A (frozen, not recomputed); "
                                                  "W0b: 'all' row only, 'no_conf' row NULL (tunnel #3)",
            "france_intl_share_definition": "countries_distinct_count > 1, over FR-affiliated works, "
                                             "2019-2023, corpus doc-type list per conf_state",
            "france_intl_share_source": "refreshed via OpenAlex" if args.refresh_france
                                        else "carried forward from deployed/snapshot dim_corpus_facts.parquet (W0b, $0 API)",
            "artifact_mask_source": str(BAD_TOPICS_XLSX),
            "artifact_mask_topics": len(bad_topic_ids),
            "cost_usd_total": total_cost,
        },
        notes="Foundry wave 0 (docs/foundry/DATA_FOUNDATION_draft.md sec.3) + W0b delta (chain "
              "pass 3, docs/foundry/data_foundation.yaml rev 3.1): replaces the unconditional "
              "ul_pubs slim read on pages 1/3/4's corpus-level excluded-disclosure caption; adds "
              "_xa artifact twins, ul_intl_share/ul_company_share (+ xa), and freezes "
              "momentum_recentring_median to the 'all' row only (no_conf now NULL). Local facts "
              "cross-checked against the deployed ul_pubs.parquet; france_intl_share carried "
              "forward at $0 API unless --refresh-france was passed.",
    )
    print("\ndone.")


if __name__ == "__main__":
    main()
