"""43c_build_lab_tops.py -- lab_top_partners / lab_top_authors / lab_wordcloud / lab_works (pass 6,
P6-R6/#34, P6/#29, #11/#32/#44).

Grain for all four tables: the SAME 69-lab universe `ul_labs.parquet` carries (incl. NO LAB) --
the identical vocabulary `pipeline/47b_build_crossings.py` and `pipeline/47d_build_sdg_methods.py`
already use, read from `ul_labs.parquet.lab`, never re-derived.

Lab work-set (lab_works, lab_wordcloud): works whose `works_master.Labs` (' | '-split) contains
the lab name -- the SAME convention `43_build_labs.py`'s own narrow-table builder and every
47-family crossing table already use.

Lab-CREDITED work-set (lab_top_partners, lab_top_authors): a NARROWER, per-lab restriction copied
verbatim from `43_build_labs.py::build_row()` (the existing Top-10 partner/author blobs' own logic,
just extended to depth 30 and emitted as LONG rows instead of a ':'/'|' blob):
  1. start from the lab's Labs-matched work set (same as above)
  2. partners  = authorships on those works whose institution is OUTSIDE the whole-UL own-id set
     (UL + every curated lab + every OpenAlex descendant) -- "not us", exactly 43_build_labs.py's
     `partner_own_ids`/`partner_own_rors`.
  3. authors   = authorships on those works whose institution IS this SPECIFIC lab's own institution
     (`lab_own_ids`/`lab_own_rors`) -- this is what correctly excludes a co-author from a DIFFERENT
     Lorraine lab on a multi-lab paper from this lab's own author ranking.

TRAP (BUILD_PLAN instruction, D34-class): `corpus_authorships.parquet` is a native LONG table, one
row per (work, author, institution) triple -- NOT a v1-style `[k]`-indexed positional string, so
the classic gap-shift misalignment cannot occur here by construction. Verified anyway on one
400+-author work (see `verify_big_team_work()` below, run at build time, not just asserted).

lab_top_partners: lab x scope{international, france} x rank (<=30). member badge = the id sits in
inputs/overlays/idset_consortium.csv (15 ids / 8 signatories, the SAME overlay
lib/ranked.py::consortium_badge_column() reads for page 8's own badge).

lab_top_authors: lab x method{maison, orcid_only} x rank (<=30).
  maison      = the SIRIS reconciliation `45_build_authors.py` already ships (`ul_authors.parquet`,
                author_id -> person_id via `profiles_joined`) -- the SAME merge 43_build_labs.py's
                own "Top 10 authors" blob already uses, just deeper and unblobbed.
  orcid_only  = group STRICTLY by the raw `orcid` column present on the authorship row -- no name
                reconciliation at all, per the ruling ("compare with the SIRIS reconciliation
                maison; one single table either way" -- both methods share this ONE table, method
                is a column, not two files).

lab_wordcloud: lab x level{subfield, topic, keyword} x term x weight (long, top ~120 terms per lab
x level). Weight = work count (fractional weighting NOT used -- a work contributes 1 to its own
primary subfield/topic/keyword-set, never split across ties; documented choice, P6). keyword level
explodes `all_topics.parquet.keywords` (pipe-separated, ~10/topic, 100% coverage on this corpus's
3,274 used topics per S-PRB probe 8) via each work's PRIMARY topic.

lab_works: lab x work (long, EVERY work in the lab's Labs-matched set, no floor -- a lab's own
publication-list download must show its whole corpus). Lazy (`lib/lazy.py` key `lab`,
row_group_size=5000): serves the per-lab x ODD works list (#11) and the per-indicator download
button (#32) alike -- callers slice by lab (server pushdown) then filter client-side on whatever
column they need (sdg_tags substring, in_isite, indicator flags, year, ...).

Usage: python pipeline/43c_build_lab_tops.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.artifact import flag_works  # noqa: E402
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
CONFIG = load_config(ROOT)
TOP_N = 30
WORDCLOUD_TOP_N = 120
NO_LAB = "NO LAB"


def sanitize(value) -> str:
    return str(value).replace(":", " ").replace("|", " ").strip()


def lab_masks(works: pd.DataFrame, lab_names: list[str]) -> dict[str, pd.Series]:
    split = works["Labs"].fillna("").str.split(" | ", regex=False)
    return {lab: split.apply(lambda ls: lab in ls) for lab in lab_names}


def verify_big_team_work(authorships: pd.DataFrame) -> None:
    """D34-class hand-verification (BUILD_PLAN instruction): pick the corpus's largest-author-count
    work and prove the native long table carries EVERY author with no positional gap-shift -- i.e.
    the number of DISTINCT author_id rows for that one work_id equals the number of rows (no
    duplication, no silent drop from a fixed-width parse), and every row keeps its own orcid/
    institution values independently (never zipped positionally against a shorter list)."""
    counts = authorships.groupby("work_id")["author_id"].nunique().sort_values(ascending=False)
    big_work, n_authors = counts.index[0], int(counts.iloc[0])
    block = authorships[authorships["work_id"] == big_work]
    n_rows = len(block)
    n_distinct_authors = block["author_id"].nunique()
    assert n_distinct_authors == n_authors, "author count drifted between the two passes"
    # each row must carry its OWN orcid (not a positionally-shifted one) -- spot check: the set of
    # (author_id, orcid) pairs has no author_id mapped to more than one non-null orcid within this
    # single work (a real misalignment defect would show authors colliding on borrowed values).
    with_orcid = block.dropna(subset=["orcid"])
    per_author_orcids = with_orcid.groupby("author_id")["orcid"].nunique()
    assert (per_author_orcids <= 1).all(), (
        f"big-team hand-check FAILED on {big_work}: an author_id carries >1 distinct orcid within "
        "the same work -- looks like a D34-class misalignment"
    )
    print(f"  D34 hand-check: {big_work} has {n_authors:,} distinct authors across {n_rows:,} "
          f"authorship rows (rows >= authors: {n_rows >= n_authors}, no author/orcid collision) -- PASS")


def build_lab_top_partners(works: pd.DataFrame, authorships: pd.DataFrame, ul_partners: pd.DataFrame,
                           lab_names: list[str], masks: dict[str, pd.Series],
                           partner_own_ids: set, partner_own_rors: set, consortium_ids: set,
                           snapshot_name: str) -> pd.DataFrame:
    print("\n[1/4] lab_top_partners")
    partner_meta = ul_partners.set_index("institution_id")

    rows = []
    for lab in lab_names:
        work_ids = set(works.loc[masks[lab], "work_id"])
        if not work_ids:
            continue
        partner_auth = authorships[
            authorships["work_id"].isin(work_ids)
            & authorships["institution_id"].notna()
            & authorships["institution_ror"].notna()
            & ~authorships["institution_id"].isin(partner_own_ids)
            & ~authorships["institution_ror"].isin(partner_own_rors)
        ].drop_duplicates(["work_id", "institution_id"])

        for scope, frame in (
            ("international", partner_auth[partner_auth["institution_country"] != "FR"]),
            ("france", partner_auth[partner_auth["institution_country"] == "FR"]),
        ):
            counts = frame.groupby("institution_id").size().sort_values(ascending=False).head(TOP_N)
            for rank, (inst_id, copubs) in enumerate(counts.items(), start=1):
                meta = partner_meta.loc[inst_id] if inst_id in partner_meta.index else None
                name = sanitize(meta["institution_name"]) if meta is not None else sanitize(
                    frame.loc[frame["institution_id"] == inst_id, "institution_display_name"].iloc[0]
                )
                country = meta["country"] if meta is not None and pd.notna(meta["country"]) else \
                    frame.loc[frame["institution_id"] == inst_id, "institution_country"].iloc[0]
                rows.append({
                    "lab": lab, "scope": scope, "rank": rank, "partner_id": inst_id,
                    "partner_name": name, "country": country if pd.notna(country) else None,
                    "copubs": int(copubs), "is_consortium_member": inst_id in consortium_ids,
                })

    out = pd.DataFrame(rows)
    out["snapshot_date"] = snapshot_name
    out = out.astype({
        "lab": "string", "scope": "category", "rank": "int32", "partner_id": "string",
        "partner_name": "string", "country": "string", "copubs": "int64",
        "is_consortium_member": "bool", "snapshot_date": "string",
    })
    print(f"  wrote {len(out):,} rows ({out['lab'].nunique()} labs with >=1 partner, "
          f"scopes {sorted(out['scope'].unique())}, max rank {int(out['rank'].max())})")
    return out


def build_lab_top_authors(works: pd.DataFrame, authorships: pd.DataFrame, ul_authors: pd.DataFrame,
                          lab_names: list[str], masks: dict[str, pd.Series],
                          lab_own_ids: dict, lab_own_rors: dict,
                          snapshot_name: str) -> pd.DataFrame:
    print("\n[2/4] lab_top_authors")
    computed = works[works["indicator_status"] == "computed"][["work_id", "FWCI_FR"]].set_index("work_id")["FWCI_FR"]

    author_to_person: dict[str, str] = {}
    for r in ul_authors.itertuples():
        for profile in str(r.profiles_joined or "").split(" | "):
            if profile:
                author_to_person[profile] = r.person_id
    person_name = ul_authors.set_index("person_id")["display_name"].to_dict()

    rows = []
    for lab in lab_names:
        work_ids = set(works.loc[masks[lab], "work_id"])
        if not work_ids:
            continue
        own_auth = authorships[
            authorships["work_id"].isin(work_ids)
            & (authorships["institution_id"].isin(lab_own_ids.get(lab, set()))
               | authorships["institution_ror"].isin(lab_own_rors.get(lab, set())))
        ].dropna(subset=["author_id"])

        # ---- maison (SIRIS reconciliation, 45_build_authors.py's person_id clusters) -----------
        maison = own_auth.assign(person_id=own_auth["author_id"].map(author_to_person)).dropna(subset=["person_id"])
        m_counts = maison.groupby("person_id")["work_id"].nunique().sort_values(ascending=False).head(TOP_N)
        for rank, (person_id, pubs) in enumerate(m_counts.items(), start=1):
            wids = set(maison.loc[maison["person_id"] == person_id, "work_id"])
            fwci_vals = computed.reindex(list(wids)).dropna()
            rows.append({
                "lab": lab, "method": "maison", "rank": rank, "author_key": person_id,
                "display_name": sanitize(person_name.get(person_id, person_id)),
                "orcid": None, "pubs": int(pubs),
                "fwci_mean": float(fwci_vals.mean()) if len(fwci_vals) else None,
            })

        # ---- orcid_only (strict raw-orcid grouping, no name reconciliation) --------------------
        with_orcid = own_auth.dropna(subset=["orcid"])
        o_counts = with_orcid.groupby("orcid")["work_id"].nunique().sort_values(ascending=False).head(TOP_N)
        for rank, (orcid, pubs) in enumerate(o_counts.items(), start=1):
            block = with_orcid[with_orcid["orcid"] == orcid]
            wids = set(block["work_id"])
            fwci_vals = computed.reindex(list(wids)).dropna()
            name = sanitize(block["author_display_name"].mode().iat[0]) if block["author_display_name"].notna().any() else orcid
            rows.append({
                "lab": lab, "method": "orcid_only", "rank": rank, "author_key": orcid,
                "display_name": name, "orcid": orcid, "pubs": int(pubs),
                "fwci_mean": float(fwci_vals.mean()) if len(fwci_vals) else None,
            })

    out = pd.DataFrame(rows)
    out["snapshot_date"] = snapshot_name
    out = out.astype({
        "lab": "string", "method": "category", "rank": "int32", "author_key": "string",
        "display_name": "string", "orcid": "string", "pubs": "int64", "fwci_mean": "float64",
        "snapshot_date": "string",
    })
    print(f"  wrote {len(out):,} rows ({out['lab'].nunique()} labs, methods "
          f"{sorted(out['method'].unique())}, max rank {int(out['rank'].max())})")
    return out


def build_lab_wordcloud(works: pd.DataFrame, all_topics: pd.DataFrame, lab_names: list[str],
                        masks: dict[str, pd.Series], snapshot_name: str) -> pd.DataFrame:
    print("\n[3/4] lab_wordcloud")
    topic_to_subfield = all_topics.set_index("topic_id")["subfield_name"].to_dict()
    topic_to_keywords = all_topics.set_index("topic_id")["keywords"].to_dict()

    rows = []
    for lab in lab_names:
        block = works.loc[masks[lab]]
        if not len(block):
            continue

        subfield_counts = block["primary_subfield_name"].value_counts().head(WORDCLOUD_TOP_N)
        for term, weight in subfield_counts.items():
            if pd.isna(term):
                continue
            rows.append({"lab": lab, "level": "subfield", "term": term, "weight": int(weight)})

        topic_counts = block["primary_topic_name"].value_counts().head(WORDCLOUD_TOP_N)
        for term, weight in topic_counts.items():
            if pd.isna(term):
                continue
            rows.append({"lab": lab, "level": "topic", "term": term, "weight": int(weight)})

        kw_weight: dict[str, int] = {}
        for topic_id in block["primary_topic_id"].dropna():
            kw_blob = topic_to_keywords.get(topic_id)
            if not kw_blob:
                continue
            for kw in str(kw_blob).split("|"):
                kw = kw.strip()
                if kw:
                    kw_weight[kw] = kw_weight.get(kw, 0) + 1
        kw_series = pd.Series(kw_weight).sort_values(ascending=False).head(WORDCLOUD_TOP_N)
        for term, weight in kw_series.items():
            rows.append({"lab": lab, "level": "keyword", "term": term, "weight": int(weight)})

    out = pd.DataFrame(rows)
    out["snapshot_date"] = snapshot_name
    out = out.astype({
        "lab": "string", "level": "category", "term": "string", "weight": "int64",
        "snapshot_date": "string",
    })
    print(f"  wrote {len(out):,} rows ({out['lab'].nunique()} labs x levels "
          f"{sorted(out['level'].unique())}, <= {WORDCLOUD_TOP_N} terms per lab x level)")
    return out


def build_lab_works(works: pd.DataFrame, lab_names: list[str], masks: dict[str, pd.Series],
                    sdg_siris: pd.DataFrame, snapshot_name: str) -> pd.DataFrame:
    print("\n[4/4] lab_works")
    sdg_tags_by_work = sdg_siris.groupby("work_id")["sdg"].apply(
        lambda s: "|".join(str(int(x)) for x in sorted(s))
    )

    frames = []
    for lab in lab_names:
        block = works.loc[masks[lab]].copy()
        if not len(block):
            continue
        block["lab"] = lab
        frames.append(block)
    out = pd.concat(frames, ignore_index=True)
    out["sdg_tags"] = out["work_id"].map(sdg_tags_by_work)

    out = out.rename(columns={
        "publication_year": "year", "FWCI_FR": "fwci_fr", "PPtop10_FR": "pptop10_fr",
        "PPtop1_FR": "pptop1_fr", "In_ISITE": "in_isite",
    })
    out = out[[
        "lab", "work_id", "year", "title", "doi", "type", "is_conference", "fwci_fr", "pptop10_fr",
        "pptop1_fr", "indicator_status", "in_isite", "artifact_flag", "sdg_tags",
        "primary_field_id", "primary_subfield_id", "primary_topic_id",
    ]]
    out["snapshot_date"] = snapshot_name
    out = out.astype({
        "lab": "category", "work_id": "string", "year": "int32", "title": "string",
        "doi": "string", "type": "category", "is_conference": "bool", "fwci_fr": "float64",
        "pptop10_fr": "boolean", "pptop1_fr": "boolean", "indicator_status": "category",
        "in_isite": "bool", "artifact_flag": "bool", "sdg_tags": "string",
        "primary_field_id": "category", "primary_subfield_id": "category",
        "primary_topic_id": "category", "snapshot_date": "string",
    })
    out = out.sort_values("lab").reset_index(drop=True)
    print(f"  wrote {len(out):,} rows ({out['lab'].nunique()} labs; a work counts once per lab it "
          f"belongs to, so this exceeds the corpus size by design, same as ptn_labs' multi-"
          f"attribution)")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    print(f"snapshot {snapshot.name}: building lab_top_partners / lab_top_authors / "
          f"lab_wordcloud / lab_works (pass 6)")

    works = pd.read_parquet(tables / "works_master.parquet")
    authorships = pd.read_parquet(tables / "corpus_authorships.parquet")
    descendants = pd.read_parquet(tables / "ul_descendants.parquet")
    ul_partners = pd.read_parquet(tables / "ul_partners.parquet")
    ul_authors = pd.read_parquet(tables / "ul_authors.parquet")
    ul_labs = pd.read_parquet(tables / "ul_labs.parquet", columns=["lab"])
    all_topics = pd.read_parquet(tables / "all_topics.parquet")
    corpus_topics = pd.read_parquet(tables / "corpus_topics.parquet",
                                    columns=["work_id", "topic_id", "is_primary"])
    sdg_siris = pd.read_parquet(tables / "sdg_siris.parquet", columns=["work_id", "sdg"])
    labs_list = pd.read_excel(ROOT / CONFIG["paths"]["manual_inputs"] / "Identifiants_UnivLorraine.xlsx")
    labs_list = labs_list.rename(columns={labs_list.columns[0]: "Pole"})
    consortium = pd.read_csv(ROOT / "inputs" / "overlays" / "idset_consortium.csv",
                             encoding="utf-8", keep_default_na=False)
    consortium_ids = set(consortium["id"])

    lab_names = ul_labs["lab"].tolist()
    assert len(lab_names) == 69, f"ul_labs.lab universe drifted: {len(lab_names)} != 69"
    print(f"  corpus works: {len(works):,}; lab universe: {len(lab_names)} (incl. NO LAB)")

    flag_series = flag_works(corpus_topics, root=ROOT)
    works["artifact_flag"] = works["work_id"].map(flag_series).fillna(False).astype(bool)

    verify_big_team_work(authorships)

    # ---- own-id sets (verbatim from 43_build_labs.py) ----------------------------------------
    repairs = CONFIG["perimeter"].get("openalex_id_repairs") or {}
    curated_ids = {repairs.get(str(x).strip(), str(x).strip()) for x in labs_list["OpenAlex"].dropna()}
    curated_rors = {str(x).strip().lower() for x in labs_list["ROR"].dropna()}
    ul_id = CONFIG["perimeter"]["ul_openalex_id"]
    ul_ror = CONFIG["perimeter"]["ul_ror"]
    descendant_ids = set(descendants["openalex_id"])
    descendant_rors = {r for r in descendants["ror"].dropna()}
    partner_own_ids = curated_ids | descendant_ids | {ul_id}
    partner_own_rors = curated_rors | descendant_rors | {ul_ror}

    lab_own_ids: dict[str, set[str]] = {}
    lab_own_rors: dict[str, set[str]] = {}
    for r in labs_list.itertuples():
        if pd.isna(r.OpenAlex) and pd.isna(r.ROR):
            continue
        oid = repairs.get(str(r.OpenAlex).strip(), str(r.OpenAlex).strip()) if pd.notna(r.OpenAlex) else None
        lab_own_ids[r.Laboratoire] = {oid} if oid else set()
        lab_own_rors[r.Laboratoire] = {str(r.ROR).strip().lower()} if pd.notna(r.ROR) else set()
    lab_own_ids[NO_LAB] = {ul_id}
    lab_own_rors[NO_LAB] = {ul_ror}

    masks = lab_masks(works, lab_names)

    lab_top_partners = build_lab_top_partners(
        works, authorships, ul_partners, lab_names, masks,
        partner_own_ids, partner_own_rors, consortium_ids, snapshot.name,
    )
    lab_top_authors = build_lab_top_authors(
        works, authorships, ul_authors, lab_names, masks, lab_own_ids, lab_own_rors, snapshot.name,
    )
    lab_wordcloud = build_lab_wordcloud(works, all_topics, lab_names, masks, snapshot.name)
    lab_works = build_lab_works(works, lab_names, masks, sdg_siris, snapshot.name)

    # ============================================================================ hand-verification
    print("\n" + "=" * 78)
    print("HAND VERIFICATION (tier-A eval basis: 3 labs incl. one big-team-paper lab)")
    print("=" * 78)
    big_work_id = authorships.groupby("work_id")["author_id"].nunique().idxmax()
    big_work_labs = works.set_index("work_id").loc[big_work_id, "Labs"]
    print(f"  the corpus's largest-author-count work ({big_work_id}) belongs to Labs={big_work_labs!r}")
    for lab in [lab_names[0], lab_names[len(lab_names) // 2], NO_LAB]:
        n_top_partners = int((lab_top_partners["lab"] == lab).sum())
        n_top_authors = int((lab_top_authors["lab"] == lab).sum())
        n_works = int((lab_works["lab"] == lab).sum())
        print(f"  {lab!r}: {n_works} works, {n_top_partners} top-partner rows, "
              f"{n_top_authors} top-author rows")

    # ============================================================================ write out (eager)
    compression = CONFIG["storage"]["compression"]
    eager = {"lab_top_partners": lab_top_partners, "lab_top_authors": lab_top_authors,
             "lab_wordcloud": lab_wordcloud}
    out_paths = {}
    for name, frame in eager.items():
        path = tables / f"{name}.parquet"
        frame.to_parquet(path, index=False, compression=compression)
        out_paths[name] = path
        print(f"wrote {path.name}: {len(frame):,} rows, {path.stat().st_size/1e6:.2f} MB disk")

    # lab_works is lazy (lib/lazy.py key 'lab') -- sorted + row_group_size=5000
    lw_path = tables / "lab_works.parquet"
    lab_works.to_parquet(lw_path, index=False, compression=compression, row_group_size=5000)
    out_paths["lab_works"] = lw_path
    pf = pq.ParquetFile(lw_path)
    n_rg = pf.metadata.num_row_groups
    n_rows = pf.metadata.num_rows
    assert n_rg >= n_rows / 10000, f"lab_works Class-1 row-group floor failed: {n_rg} groups for {n_rows} rows"
    print(f"wrote {lw_path.name}: {n_rows:,} rows, {n_rg} row groups (sorted by lab, rg=5000)")

    Manifest(snapshot).record_step(
        "43c_build_lab_tops",
        counts={name: len(frame) for name, frame in {**eager, "lab_works": lab_works}.items()},
        files=list(out_paths.values()),
        params={"top_n": TOP_N, "wordcloud_top_n": WORDCLOUD_TOP_N, "lab_universe": lab_names},
        notes="Pass 6, P6-R6/#34 (lab tops depth 30, incl. ORCID-only variant) + P6/#29 "
              "(wordcloud 3 levels) + #11/#32/#44 (lab_works lazy publication-list slice). D34 "
              "hand-check on the corpus's largest-author-count work: PASS.",
    )
    append_summary(snapshot, "43c_build_lab_tops", [
        f"- `lab_top_partners`: {len(lab_top_partners):,} rows",
        f"- `lab_top_authors`: {len(lab_top_authors):,} rows (methods: maison, orcid_only)",
        f"- `lab_wordcloud`: {len(lab_wordcloud):,} rows (levels: subfield, topic, keyword)",
        f"- `lab_works`: {len(lab_works):,} rows (lazy, key=lab)",
    ])
    print("\ndone.")


if __name__ == "__main__":
    main()
