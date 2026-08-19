"""49c_build_peer_context.py -- bench_sdg / bench_positioning / bench_diversity (pass 5, S3,
rulings R6/R7, plan P5).

Reads the WIDE peer raw pulled by `pipeline/49w_pull_peers_wide.py` (S2, pass 5:
`raw/peers/<peer_id>_wide.jsonl.zst`, 9 peers, 200,832 works, EXACT match to the pass-4 narrow
pull -- zero drift, per `reports/peer_pull_pass5.md`) plus the UL-side snapshot tables. This
script NEVER touches `pipeline/49_pull_peer_benchmark.py`, `49b_build_peer_benchmark.py` or
`49w_pull_peers_wide.py` -- read-only authority for the France-strata join pattern and the
registry-loading convention, per the mission fence.

Registry: `inputs/overlays/bench_peers.csv`, `status == ok` (the same 9 peers as `bench_peers`).

============================================================================================
PROBES (run BEFORE writing this file's builders -- results archived in full in
progress/S3_data_ext.md; summarised again here at the point they gate a design decision).

Probe A (gates bench_positioning): does 47_build_thematic_ext.py's `thm_frontier` assign topics to
works via PRIMARY topic only, or via corpus_topics' multi-topic assignment? Read in full: it builds
its join from `works[["work_id","primary_topic_id", ...]]` -- PRIMARY-TOPIC-ONLY, already. Peers
carry `primary_topic` only in the wide pull (no multi-topic `topics` field was ever pulled, R7's own
explicit scope). Verdict: **already symmetric, zero adaptation needed** -- bench_positioning copies
47's percentile-rank panel construction (front_pctile/field_pctile off the SAME fixed baseline)
verbatim onto the peer side. No caveat, no labelled variant.

Probe B (gates bench_diversity): does 47's `thm_diversity` construction transfer to a peer that
only has primary_topic? It does NOT -- `build_subfield_weight_matrix` score-weights EVERY topic a
work carries (corpus_topics, mean 2.65 topics/work), and a one-hot (primary-topic-only) weight
matrix collapses subfield-pair co-occurrence to exactly zero everywhere off-diagonal (no work can
ever contribute mass to two subfields at once in a one-hot scheme), which would make the disparity
matrix structurally meaningless, not merely different, if rebuilt that way. FIX (not abandonment):
the 252x252 disparity matrix is a property of SUBFIELD PAIRS, not of any one entity -- it is built
ONCE from UL's own full multi-topic corpus (verbatim copy of 47's own
build_subfield_weight_matrix/build_disparity_matrix below) and REUSED UNCHANGED for every entity's
own primary-topic-only p-vector (UL's included). Every row is labelled `method:
primary_topic_both_sides`. The "transfer bar" is checked explicitly at build time
(`_verify_disparity_matrix_transfers`): a verbatim recompute of thm_diversity's OWN stored
(perimeter_id='all', year=2019, conf_state='all') row, using this file's copy of 47's multi-topic
code, must match the DEPLOYED thm_diversity value EXACTLY (proves the copied code is faithful, not
merely similar) -- and UL's DEPLOYED (multi-topic) value is printed BESIDE UL's own primary-topic-
only recompute at the same key, so the method-caused delta is shown, never hidden inside a single
number. Outcome: **bench_diversity IS built** (labelled symmetric variant), not the red-flag
fallback.
============================================================================================

Artifact-flag: ALL THREE tables are EXEMPT BY CONSTRUCTION, declared exactly like `bench_peers`
(S9's own rationale, reused verbatim): peer corpora are pulled live from OpenAlex, never from the
frozen local artifact-flagged snapshot, so there is no way to know which of a peer's works sit on
one of the 811 excluded topics. No `_xa` column anywhere on any of the three tables -- including on
the UL row, for the SAME reason `bench_peers` exempts UL's own row (S9: uniform treatment across
every entity in a benchmark table beats a table where only one row can be filtered).

Perimeter symmetry: UL's row on every table is the DIRECT-ID perimeter (`via_ul_direct` & the 5
corpus doc types), copied from `pipeline/49b_build_peer_benchmark.py`'s own `load_ul_frame` --
measured 28,464 works, the SAME number `bench_peers`' own UL row uses (Sec.2a symmetry: this is
peer-symmetric, NOT the 36,819 lineage corpus).

Usage: python pipeline/49c_build_peer_context.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
CONFIG = load_config(ROOT)
MIN_STRATUM_N = int(CONFIG["metrics"]["min_stratum_n"])              # 30, D53 floor
DOC_TYPES = CONFIG["corpus_filter"]["doc_types_keep"]                 # 5 types, S5 (49b precedent)
UL_ID = CONFIG["perimeter"]["ul_openalex_id"]                         # I90183372
SDG_THRESHOLD = float(CONFIG["sdg"]["openalex_metadata"]["threshold"])  # 0.40, OurResearch's own floor
REGISTRY_PATH = ROOT / "inputs" / "overlays" / "bench_peers.csv"
CONF_STATES = ["all", "no_conf"]


# ================================================================================= peer wide loader
def _short(url: str | None) -> str | None:
    return str(url).rsplit("/", 1)[-1] if url else None


def _parse_wide_record(work: dict) -> dict:
    pt = work.get("primary_topic") or {}
    sdgs = [
        n for s in (work.get("sustainable_development_goals") or [])
        if (n := _short(s.get("id"))) is not None and (s.get("score") or 0.0) >= SDG_THRESHOLD
    ]
    return {
        "work_id": _short(work.get("id")),
        "type": work.get("type"),
        "publication_year": work.get("publication_year"),
        "topic_id": _short(pt.get("id")) if pt else None,
        "field_id": _short((pt.get("field") or {}).get("id")) if pt else None,
        "subfield_id": _short((pt.get("subfield") or {}).get("id")) if pt else None,
        "sdg_list": sdgs,
    }


def load_peer_wide(peer_id: str, raw_dir: Path) -> pd.DataFrame:
    """Streams `<peer_id>_wide.jsonl.zst` (S2 pass-5 pull) into one row per work. Never loads the
    whole decompressed payload into one string (files run 45-94 MB uncompressed each, per
    reports/peer_pull_pass5.md) -- a bounded stream-reader + line buffer, same idiom
    pipeline/49w_pull_peers_wide.py itself uses to WRITE these files."""
    import zstandard as zstd

    path = raw_dir / f"{peer_id}_wide.jsonl.zst"
    if not path.exists():
        raise SystemExit(f"missing {path} -- run pipeline/49w_pull_peers_wide.py first (S2, pass 5)")
    rows: list[dict] = []
    dctx = zstd.ZstdDecompressor()
    with path.open("rb") as fh, dctx.stream_reader(fh) as reader:
        buf = b""
        while True:
            chunk = reader.read(1 << 20)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line.strip():
                    rows.append(_parse_wide_record(json.loads(line)))
        if buf.strip():
            rows.append(_parse_wide_record(json.loads(buf)))
    return pd.DataFrame(rows)


def peer_conf_mask(frame: pd.DataFrame, state: str) -> pd.Series:
    return pd.Series(True, index=frame.index) if state == "all" else (frame["type"] != "conference-paper")


# ================================================================================= UL-side loader
def load_ul_frame(tables: Path) -> pd.DataFrame:
    """S5: works_master filtered to via_ul_direct & the 5 corpus types -- the direct-id perimeter,
    peer-symmetric with the OpenAlex pulls. VERBATIM copy of
    pipeline/49b_build_peer_benchmark.py's own `load_ul_frame` (read-only authority, per the
    mission fence), extended with the extra columns THIS file's three tables need
    (primary_subfield_id) beyond what 49b itself loads."""
    wm = pd.read_parquet(tables / "works_master.parquet", columns=[
        "work_id", "via_ul_direct", "type", "publication_year",
        "primary_topic_id", "primary_field_id", "primary_subfield_id",
    ])
    ul = wm[wm["via_ul_direct"] & wm["type"].isin(DOC_TYPES)].copy()
    ul = ul.rename(columns={
        "primary_field_id": "field_id", "primary_subfield_id": "subfield_id",
        "primary_topic_id": "topic_id",
    })
    ul["topic_id"] = ul["topic_id"].astype(str).str.replace("https://openalex.org/", "", regex=False)
    return ul


def registry() -> pd.DataFrame:
    df = pd.read_csv(REGISTRY_PATH, encoding="utf-8", keep_default_na=False)
    return df[df["status"] == "ok"].reset_index(drop=True)


def entity_list(ok: pd.DataFrame) -> list[tuple[str, str, str, str]]:
    """(entity_id, entity_name, rung, country) -- UL first, then the 9 peers, matching bench_peers'
    own row ordering convention."""
    out = [(UL_ID, "Universite de Lorraine", "FOCAL", "FR")]
    for _, row in ok.iterrows():
        out.append((row["peer_id"], row["display_name"], row["rung"], row["country"]))
    return out


# ===================================================================================== bench_sdg
def build_bench_sdg(ul: pd.DataFrame, peer_frames: dict[str, pd.DataFrame], ok: pd.DataFrame,
                    corpus_sdg: pd.DataFrame, snapshot_name: str) -> pd.DataFrame:
    print("\n[1/3] bench_sdg")
    ul_sdg = corpus_sdg[corpus_sdg["work_id"].isin(set(ul["work_id"]))].copy()
    ul_sdg["sdg"] = ul_sdg["sdg_id"].astype(int)
    print(f"  UL direct-id perimeter: {len(ul):,} works; {ul_sdg['work_id'].nunique():,} with "
          f">=1 native OpenAlex/Aurora SDG (score >= {SDG_THRESHOLD})")

    rows = []
    for entity_id, entity_name, rung, country in entity_list(ok):
        frame = ul if entity_id == UL_ID else peer_frames[entity_id]
        for conf_state in CONF_STATES:
            # both UL (load_ul_frame) and every peer frame carry a `type` column, so the same
            # helper applies uniformly regardless of entity (no UL-specific branch needed).
            cm = peer_conf_mask(frame, conf_state)
            scoped = frame[cm]
            total = len(scoped)
            if entity_id == UL_ID:
                sdg_scoped = ul_sdg[ul_sdg["work_id"].isin(set(scoped["work_id"]))]
                per_sdg = sdg_scoped.groupby("sdg")["work_id"].nunique()
            else:
                exploded = scoped[["work_id", "sdg_list"]].explode("sdg_list").dropna(subset=["sdg_list"])
                exploded["sdg"] = exploded["sdg_list"].astype(int)
                per_sdg = exploded.groupby("sdg")["work_id"].nunique()
            for sdg_num in range(1, 18):
                works_n = int(per_sdg.get(sdg_num, 0))
                share = (works_n / total) if total >= MIN_STRATUM_N else np.nan
                rows.append({
                    "entity_id": entity_id, "entity_name": entity_name, "rung": rung, "country": country,
                    "sdg": sdg_num, "conf_state": conf_state, "entity_total_works": total,
                    "works": works_n, "share_of_entity_works": share,
                })
    out = pd.DataFrame(rows)
    out["snapshot_date"] = snapshot_name
    out = out.astype({
        "entity_id": "string", "entity_name": "string", "rung": "string", "country": "string",
        "sdg": "int64", "conf_state": "string", "entity_total_works": "int64", "works": "int64",
        "share_of_entity_works": "float64", "snapshot_date": "string",
    })
    print(f"  wrote {len(out):,} rows (10 entities x 17 SDGs x {len(CONF_STATES)} conf_states)")
    return out


# =============================================================================== bench_positioning
def build_bench_positioning(ul: pd.DataFrame, peer_frames: dict[str, pd.DataFrame], ok: pd.DataFrame,
                            baseline_path: Path, all_topics: pd.DataFrame,
                            snapshot_name: str) -> pd.DataFrame:
    print("\n[2/3] bench_positioning (method: primary_topic, both sides -- copied verbatim, see "
          "module docstring Probe A)")
    base = pd.read_excel(baseline_path, sheet_name="FILTERING OUT TOPICS")
    base.columns = [c.strip() for c in base.columns]
    KEY = "Topic ID no url"
    base[KEY] = base[KEY].astype(str).str.strip()

    from lib.artifact import load_bad_topics
    bad_ids = load_bad_topics(ROOT)
    base["excluded"] = base[KEY].isin(bad_ids)
    assert int(base["excluded"].sum()) == 811, "exclusion count drifted from the 811-topic golden"
    kept = base[~base["excluded"]].copy()

    field_name_to_id = all_topics.drop_duplicates("field_name").set_index("field_name")["field_id"] \
        .astype("string")
    kept["field_id_baseline"] = kept["OA field"].map(field_name_to_id)
    assert kept["field_id_baseline"].isna().sum() == 0

    kept["front_pctile"] = kept["Average frontierness"].rank(pct=True) * 100.0
    kept["field_pctile"] = kept.groupby("OA field")["Average frontierness"].rank(pct=True) * 100.0
    gbq_weight = kept["Number of articles (OpenAlex GBQ)"]
    neutral_point = float((kept["front_pctile"] * gbq_weight).sum() / gbq_weight.sum())
    baseline_vintage = "same copy-in as thm_frontier.parquet -- inputs/manual/frontierness_baseline.xlsx"
    score_column_used = "Average frontierness (ACCORD composite: 0.7 Expansion + 0.3 Acceleration, " \
                         "z-scored within bin)"
    field_ids = sorted(all_topics["field_id"].astype("string").unique().tolist(), key=int)

    rows = []
    coverage_lines = []
    for entity_id, entity_name, rung, country in entity_list(ok):
        frame = ul if entity_id == UL_ID else peer_frames[entity_id]
        merged = frame[["work_id", "type", "topic_id"]].merge(
            base[[KEY, "excluded"]], left_on="topic_id", right_on=KEY, how="left")
        merged = merged.merge(kept[[KEY, "front_pctile", "field_pctile", "field_id_baseline"]],
                              on=KEY, how="left")
        matched = merged[KEY].notna()
        join_cov = matched.sum() / len(frame) if len(frame) else np.nan
        coverage_lines.append(f"  {entity_name} ({entity_id}): join coverage {matched.sum():,}/"
                              f"{len(frame):,} = {join_cov*100:.2f}%")
        scoreable = merged[matched & (merged["excluded"] == False) & merged["front_pctile"].notna()].copy()  # noqa: E712

        for conf_state in CONF_STATES:
            if conf_state == "all":
                sub_all = scoreable
            else:
                sub_all = scoreable[scoreable["type"] != "conference-paper"]
            for field_id in field_ids:
                f = sub_all[sub_all["field_id_baseline"] == field_id]
                n = len(f)
                raw = float(f["front_pctile"].mean()) if n >= MIN_STRATUM_N else np.nan
                std = float(f["field_pctile"].mean()) if n >= MIN_STRATUM_N else np.nan
                rows.append({
                    "entity_id": entity_id, "entity_name": entity_name, "rung": rung, "country": country,
                    "field_id": field_id, "conf_state": conf_state, "n_scoreable": n,
                    "raw_frontier_share": raw, "field_standardised_share": std,
                    "neutral_point": neutral_point, "score_column_used": score_column_used,
                    "baseline_vintage": baseline_vintage, "join_coverage_pct": round(join_cov * 100, 2),
                    "method": "primary_topic_both_sides",
                })
    print("\n".join(coverage_lines))
    out = pd.DataFrame(rows)
    out["snapshot_date"] = snapshot_name
    out = out.astype({
        "entity_id": "string", "entity_name": "string", "rung": "string", "country": "string",
        "field_id": "string", "conf_state": "string", "n_scoreable": "int64",
        "raw_frontier_share": "float64", "field_standardised_share": "float64",
        "neutral_point": "float64", "score_column_used": "string", "baseline_vintage": "string",
        "join_coverage_pct": "float64", "method": "string", "snapshot_date": "string",
    })
    print(f"  wrote {len(out):,} rows (10 entities x {len(field_ids)} fields x "
          f"{len(CONF_STATES)} conf_states)")
    return out


# ================================================================================ bench_diversity
def gini(shares: np.ndarray) -> float:
    """VERBATIM copy of pipeline/47_build_thematic_ext.py's gini() -- standard Gini coefficient on
    a non-negative array (shares need not sum to 1)."""
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
    """VERBATIM copy of pipeline/47_build_thematic_ext.py's build_subfield_weight_matrix() -- see
    that module's own docstring for the full rationale. Used HERE only to build the disparity
    matrix (Probe B) -- never to compute a peer's own p-vector (peers have no multi-topic data)."""
    sub_score = corpus_topics.groupby(["work_id", "subfield_id"], observed=True)["score"].sum().reset_index()
    totals = sub_score.groupby("work_id")["score"].transform("sum")
    sub_score["norm_weight"] = sub_score["score"] / totals
    pivot = sub_score.pivot(index="work_id", columns="subfield_id", values="norm_weight")
    pivot = pivot.fillna(0.0)
    pivot = pivot.reindex(columns=subfield_ids, fill_value=0.0)
    pivot = pivot.reindex(index=work_ids, fill_value=0.0)
    return pivot.to_numpy(dtype="float32")


def build_disparity_matrix(weight_matrix: np.ndarray) -> np.ndarray:
    """VERBATIM copy of pipeline/47_build_thematic_ext.py's build_disparity_matrix(). Fixed
    252x252 matrix, built ONCE from UL's own full multi-topic corpus, reused unchanged for UL AND
    every peer's primary-topic-only p-vector below (Probe B fix)."""
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
    """VERBATIM copy of pipeline/47_build_thematic_ext.py's div_components() -- used ONLY by the
    transfer-bar check below (multi-topic input), never by the primary-topic-only builder."""
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


def div_components_primary_topic(subfield_counts: pd.Series, disparity: np.ndarray,
                                 subfield_ids: list[str], n_universe: int) -> dict:
    """Primary-topic-only equivalent of div_components(): `subfield_counts` is a raw value_counts
    of an entity's works over subfield_ids (one-hot per work -- a work counts toward EXACTLY one
    subfield). Mathematically this is `weight_matrix[row_idx].sum(axis=0)` when weight_matrix is
    one-hot, so building a full one-hot pivot per entity is unnecessary -- the count vector IS that
    sum. The shared `disparity` matrix (built once, multi-topic, Probe B) is reused unchanged."""
    counts = subfield_counts.reindex(subfield_ids, fill_value=0).to_numpy(dtype="float64")
    n_works = int(counts.sum())
    total = counts.sum()
    if total <= 0:
        return {"variety": np.nan, "balance": np.nan, "disparity": np.nan, "rao_stirling": np.nan, "n_works": n_works}
    p = counts / total
    present = np.where(p > 1e-12)[0]
    n_c = len(present)
    variety = n_c / n_universe
    if n_c == 0:
        return {"variety": 0.0, "balance": np.nan, "disparity": np.nan, "rao_stirling": np.nan, "n_works": n_works}
    balance = 1.0 - gini(p[present])
    if n_c < 2:
        disp = np.nan
    else:
        sub = disparity[np.ix_(present, present)]
        iu = np.triu_indices(n_c, k=1)
        disp = float(sub[iu].mean())
    rs = variety * balance * disp if pd.notna(balance) and pd.notna(disp) else np.nan
    return {"variety": variety, "balance": balance, "disparity": disp, "rao_stirling": rs, "n_works": n_works}


def _verify_disparity_matrix_transfers(tables: Path, subfield_ids: list[str], disparity: np.ndarray,
                                       weight_matrix_full: np.ndarray, work_pos: pd.Series) -> None:
    """TRANSFER BAR (Probe B): recompute thm_diversity's OWN stored row for (perimeter_id='all',
    year=2019, conf_state='all') using THIS file's copy of 47's multi-topic code, and assert it
    matches the DEPLOYED thm_diversity value EXACTLY. This is the code-fidelity proof; it is NOT
    the construction bench_diversity actually ships (which is primary-topic-only, see
    build_bench_diversity below)."""
    works = pd.read_parquet(tables / "works_master.parquet",
                            columns=["work_id", "publication_year", "is_conference"])
    idx_2019 = work_pos.reindex(works.loc[works["publication_year"] == 2019, "work_id"]).dropna().to_numpy(dtype=int)
    recomputed = div_components(idx_2019, weight_matrix_full, disparity, len(subfield_ids))

    thm_diversity = pd.read_parquet(tables / "thm_diversity.parquet")
    stored = thm_diversity[(thm_diversity.perimeter_id == "all") & (thm_diversity.year == 2019)
                           & (thm_diversity.conf_state == "all")]
    assert len(stored) == 1, f"expected exactly 1 stored thm_diversity row for the transfer-bar key, got {len(stored)}"
    stored = stored.iloc[0]

    diffs = {k: abs(recomputed[k] - float(stored[k])) for k in ("variety", "balance", "disparity", "rao_stirling")}
    print("\n[TRANSFER BAR] recompute (perimeter='all', year=2019, conf_state='all') via THIS "
          "file's copied 47-code vs the DEPLOYED thm_diversity row:")
    for k, v in diffs.items():
        print(f"    {k}: recomputed={recomputed[k]:.10f}  stored={float(stored[k]):.10f}  diff={v:.2e}")
    assert all(v < 1e-9 for v in diffs.values()), (
        f"TRANSFER BAR FAILED: recompute does not reproduce thm_diversity EXACTLY: {diffs}"
    )
    print("  TRANSFER BAR: EXACT reproduction -- the copied multi-topic code is faithful (PASS)")
    return recomputed


def build_bench_diversity(ul: pd.DataFrame, peer_frames: dict[str, pd.DataFrame], ok: pd.DataFrame,
                          disparity: np.ndarray, subfield_ids: list[str],
                          snapshot_name: str) -> tuple[pd.DataFrame, dict]:
    print("\n[3/3] bench_diversity (method: primary_topic, both sides -- Probe B fix)")
    n_universe = len(subfield_ids)
    rows = []
    ul_both_ways: dict = {}
    for entity_id, entity_name, rung, country in entity_list(ok):
        frame = ul if entity_id == UL_ID else peer_frames[entity_id]
        for conf_state in CONF_STATES:
            # both UL (load_ul_frame) and every peer frame carry a `type` column.
            cm = peer_conf_mask(frame, conf_state)
            scoped = frame[cm].dropna(subset=["subfield_id"])
            counts = scoped["subfield_id"].astype(str).value_counts()
            comp = div_components_primary_topic(counts, disparity, subfield_ids, n_universe)
            floor_ok = comp["n_works"] >= MIN_STRATUM_N
            row = {
                "entity_id": entity_id, "entity_name": entity_name, "rung": rung, "country": country,
                "conf_state": conf_state, "n_works": comp["n_works"],
                "variety": comp["variety"] if floor_ok else np.nan,
                "balance": comp["balance"] if floor_ok else np.nan,
                "disparity": comp["disparity"] if floor_ok else np.nan,
                "rao_stirling": comp["rao_stirling"] if floor_ok else np.nan,
                "method": "primary_topic_both_sides",
                "disparity_matrix_source": "UL full multi-topic corpus (2026-08-11 snapshot), fixed, "
                                           "reused unchanged for every entity -- see docs/METHODES.md",
            }
            rows.append(row)
            if entity_id == UL_ID and conf_state == "all":
                ul_both_ways["primary_topic_all_conf_all"] = comp
    out = pd.DataFrame(rows)
    out["snapshot_date"] = snapshot_name
    out = out.astype({
        "entity_id": "string", "entity_name": "string", "rung": "string", "country": "string",
        "conf_state": "string", "n_works": "int64", "variety": "float64", "balance": "float64",
        "disparity": "float64", "rao_stirling": "float64", "method": "string",
        "disparity_matrix_source": "string", "snapshot_date": "string",
    })
    print(f"  wrote {len(out):,} rows (10 entities x {len(CONF_STATES)} conf_states)")
    return out, ul_both_ways


# ======================================================================================= main
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"
    raw_dir = snapshot / "raw" / "peers"

    print(f"snapshot {snapshot.name}: building bench_sdg / bench_positioning / bench_diversity "
          f"(pass 5, S3, R6/R7, plan P5)")

    ok = registry()
    print(f"registry: {len(ok)} status==ok peer(s)")

    ul = load_ul_frame(tables)
    print(f"UL direct-id perimeter: {len(ul):,} works (via_ul_direct & 5 types -- Sec.2a, "
          f"peer-symmetric with bench_peers' own UL row)")
    assert len(ul) == 28464, f"UL direct-id perimeter drifted: {len(ul):,} != 28,464"

    peer_frames: dict[str, pd.DataFrame] = {}
    for _, row in ok.iterrows():
        peer_id, label = row["peer_id"], row["display_name"]
        pf = load_peer_wide(peer_id, raw_dir)
        peer_frames[peer_id] = pf
        print(f"  {label} ({peer_id}): {len(pf):,} works loaded from the wide pull")

    corpus_sdg = pd.read_parquet(tables / "corpus_sdg.parquet", columns=["work_id", "sdg_id", "score"])
    corpus_sdg = corpus_sdg[corpus_sdg["score"].fillna(0) >= SDG_THRESHOLD]

    all_topics = pd.read_parquet(tables / "all_topics.parquet")
    all_topics_str = all_topics.assign(
        field_id=all_topics["field_id"].astype(str), field_name=all_topics["field_name"],
        subfield_id=all_topics["subfield_id"].astype(str),
    )
    subfield_ids = sorted(all_topics_str["subfield_id"].unique().tolist(), key=int)
    assert len(subfield_ids) == 252, f"subfield universe drifted: {len(subfield_ids)} != 252"

    baseline_path = ROOT / "inputs" / "manual" / "frontierness_baseline.xlsx"

    bench_sdg = build_bench_sdg(ul, peer_frames, ok, corpus_sdg, snapshot.name)
    bench_positioning = build_bench_positioning(ul, peer_frames, ok, baseline_path, all_topics_str,
                                                snapshot.name)

    # ---- bench_diversity: build the shared disparity matrix ONCE (multi-topic, UL's full corpus)
    works_full = pd.read_parquet(tables / "works_master.parquet", columns=["work_id"])
    corpus_topics = pd.read_parquet(tables / "corpus_topics.parquet",
                                    columns=["work_id", "topic_id", "score", "is_primary", "subfield_id"])
    corpus_topics = corpus_topics.assign(subfield_id=corpus_topics["subfield_id"].astype(str))
    weight_matrix_full = build_subfield_weight_matrix(corpus_topics, works_full["work_id"], subfield_ids)
    disparity = build_disparity_matrix(weight_matrix_full)
    print(f"\ndisparity matrix: {disparity.shape} (fixed, built once on UL's full multi-topic "
          f"corpus, reused for UL + all 9 peers)")

    work_pos = pd.Series(np.arange(len(works_full)), index=works_full["work_id"].to_numpy())
    _verify_disparity_matrix_transfers(tables, subfield_ids, disparity, weight_matrix_full, work_pos)

    bench_diversity, ul_both_ways = build_bench_diversity(ul, peer_frames, ok, disparity, subfield_ids,
                                                          snapshot.name)

    # UL-both-ways disclosure (Probe B requirement): DEPLOYED thm_diversity multi-topic value at
    # (all, 2019, all) vs UL's OWN primary-topic-only recompute on the direct-id perimeter (full
    # 2019-2023 window, conf_state='all') -- same entity, two constructions, delta shown.
    thm_diversity = pd.read_parquet(tables / "thm_diversity.parquet")
    deployed_2019 = thm_diversity[(thm_diversity.perimeter_id == "all") & (thm_diversity.year == 2019)
                                  & (thm_diversity.conf_state == "all")].iloc[0]
    primary_only = ul_both_ways["primary_topic_all_conf_all"]
    print("\n[UL-BOTH-WAYS] rao_stirling, method-caused delta (perimeter/construction both differ, "
          "disclosed rather than absorbed):")
    print(f"  DEPLOYED thm_diversity (multi-topic, perimeter='all'=36,819-work lineage corpus, "
          f"year=2019 only): rao_stirling={float(deployed_2019['rao_stirling']):.6f}")
    print(f"  bench_diversity UL row (primary-topic-only, direct-id 28,464-work perimeter, full "
          f"2019-2023 window): rao_stirling={primary_only['rao_stirling']:.6f}")
    print(f"  NOT a like-for-like delta (perimeter AND year-window AND construction all differ at "
          f"once) -- reported as two distinct, correctly-labelled numbers, never subtracted into a "
          f"single misleading 'error' figure. See docs/METHODES.md for the full disclosure.")

    # =================================================================================== write out
    compression = CONFIG["storage"]["compression"]
    outputs = {
        "bench_sdg": bench_sdg, "bench_positioning": bench_positioning,
        "bench_diversity": bench_diversity,
    }
    for name, df in outputs.items():
        xa_cols = [c for c in df.columns if c.endswith("_xa") or c == "artifact_flag"]
        assert not xa_cols, f"{name} carries artifact/_xa column(s), should be exempt by construction: {xa_cols}"
    print("\nS9 exempt-by-construction check (no _xa/artifact_flag column on any of the 3 tables): PASS")

    written_files = []
    for name, df in outputs.items():
        out_path = tables / f"{name}.parquet"
        df.to_parquet(out_path, index=False, compression=compression)
        written_files.append(out_path)
        print(f"\nwrote {name}.parquet: {len(df):,} rows x {len(df.columns)} cols, "
              f"{out_path.stat().st_size/1024:,.1f} KB")

    Manifest(snapshot).record_step(
        "49c_build_peer_context",
        counts={name: len(df) for name, df in outputs.items()},
        files=written_files,
        params={
            "min_stratum_n": MIN_STRATUM_N, "sdg_threshold": SDG_THRESHOLD,
            "ul_direct_id_perimeter_works": len(ul),
            "bench_diversity_method": "primary_topic_both_sides",
            "bench_positioning_method": "primary_topic_both_sides (already thm_frontier's own "
                                        "construction -- no adaptation needed, Probe A)",
        },
        notes="Pass 5 (S3), rulings R6/R7, plan P5. All 3 tables artifact-exempt by construction "
              "(S9, no _xa anywhere). bench_diversity transfer-bar verified EXACT against the "
              "deployed thm_diversity row; UL-both-ways delta printed and archived in "
              "progress/S3_data_ext.md + docs/METHODES.md.",
    )
    append_summary(snapshot, "49c_build_peer_context", [
        f"- `bench_sdg`: {len(bench_sdg):,} rows (10 entities x 17 SDGs x 2 conf_states)",
        f"- `bench_positioning`: {len(bench_positioning):,} rows (10 entities x 26 fields x "
        f"2 conf_states); method primary_topic_both_sides (Probe A: no adaptation needed)",
        f"- `bench_diversity`: {len(bench_diversity):,} rows (10 entities x 2 conf_states); "
        f"method primary_topic_both_sides (Probe B: labelled symmetric variant, transfer bar PASS)",
    ])
    print("\ndone.")


if __name__ == "__main__":
    main()
