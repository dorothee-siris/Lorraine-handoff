"""45_build_authors.py — `ul_authors`, rebuilt on native authorship rows (D15: dataset, no view).

Two changes from v1, one structural and one of substance.

**Structural.** v1 parsed per-author fields out of `[n]`-indexed pipe strings, dropping `Unknown`
slots and re-zipping the shortened list against the full author list, so every value after the first
gap landed on the wrong author — 51.4% of works affected, 3,166 author ids wrongly credited with a
Lorraine affiliation and 440 genuine ones missed. v2 reads `corpus_authorships`, which is one row per
work x author x institution, so that failure class cannot occur.

**Substance.** v2 merges with graded, symmetric evidence (`lib/authors_lib.py`, copied from Phase 1):
  H1  equal non-null ORCID                          -> merge
  H1b equal non-null idHAL (new in v2, from HAL)     -> merge
  X   conflicting non-null ORCIDs                    -> BLOCK, never merge
  H2  name compatible AND >= 3 shared co-authors     -> merge
  H3  name compatible AND shared lab AND >= 1 co-author -> merge
  H4  name identical AND shared lab                  -> merge
A shared lab alone is never sufficient: in v1 it was treated as proof of identity when it is only
context, and it was frequently attached to the wrong author anyway.

Known limitation, kept deliberately: rule X splits a researcher who holds two ORCID registrations
(Patrick Rossignol: 145 + 92 works, identical lab signature, 300 shared co-authors). No bottom-up
threshold separates that from a same-lab homonym, so those pairs are **surfaced in a review queue**
rather than silently resolved.

Usage: python pipeline/45_build_authors.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import authors_lib as AL  # noqa: E402
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)
NAME_FLOOR = 0.50          # authors_lib: 0.40 = "two different given names" = reject
CO_AUTHOR_FLOOR = 3        # Ifremer raised this from 2 after an over-merge
HAL_NAME_FLOOR = 0.70      # matching a HAL author name to an OpenAlex one inside the same work


def load_hal_authors(snapshot: Path) -> pd.DataFrame:
    """Per-work HAL author identifiers, re-parsed from the archived raw harvest (D38).

    `hal_records.parquet` keeps only the joined id lists; the per-author names live in the raw, which
    is why keeping it compressed rather than deleting it matters.
    """
    raw = snapshot / "raw" / "hal_lorraine.jsonl"
    compressed = raw.with_suffix(raw.suffix + ".zst")
    if not (raw.exists() or compressed.exists()):
        print("  ! no HAL raw harvest — skipping idHAL/ORCID enrichment")
        return pd.DataFrame(columns=["hal_id", "name", "idhal"])

    def records():
        if raw.exists():
            with raw.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        yield json.loads(line)
        else:
            import zstandard

            with compressed.open("rb") as fh, zstandard.ZstdDecompressor().stream_reader(fh) as stream:
                for line in io.TextIOWrapper(stream, encoding="utf-8"):
                    if line.strip():
                        yield json.loads(line)

    rows = []
    for doc in records():
        # Parse the ALIGNED pairs only: "Full Name_FacetSep_idhal", one entry per author, empty tail
        # when that author has no idHAL. The sparse authIdHal_s / authORCIDIdExt_s arrays must never
        # be zipped positionally against authFullName_s: doing so on the first run attached idHAL
        # "jean-villerd" to Nicolas Rossignol and "celine-leroy" to Patrick Rossignol. HAL publishes
        # no aligned name-to-ORCID field, so per-author ORCID from HAL is not recoverable at all.
        for entry in doc.get("authFullNameIdHal_fs") or []:
            name, _, idhal = str(entry).partition("_FacetSep_")
            if name.strip() and idhal.strip():
                rows.append({"hal_id": doc.get("halId_s"), "name": name.strip(), "idhal": idhal.strip()})
    frame = pd.DataFrame(rows, columns=["hal_id", "name", "idhal"])
    print(f"  HAL raw: {len(frame):,} author entries with an ALIGNED idHAL")
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    works = pd.read_parquet(tables / "works_master.parquet")
    authorships = pd.read_parquet(tables / "corpus_authorships.parquet")
    descendants = pd.read_parquet(tables / "ul_descendants.parquet")
    print(f"snapshot {snapshot.name}: {len(authorships):,} authorship rows")

    ul_ids = set(descendants["openalex_id"]) | {CONFIG["perimeter"]["ul_openalex_id"]}
    ul_rors = {r for r in descendants["ror"].dropna()} | {CONFIG["perimeter"]["ul_ror"]}

    rows = authorships.dropna(subset=["author_id"]).copy()
    rows["is_ul"] = rows["institution_id"].isin(ul_ids) | rows["institution_ror"].isin(ul_rors)
    lorraine_ids = set(rows.loc[rows["is_ul"], "author_id"])
    print(f"  author ids credited a Lorraine affiliation on >=1 work: {len(lorraine_ids):,}")

    scoped = rows[rows["author_id"].isin(lorraine_ids)]

    # --- profiles -----------------------------------------------------------------------------
    profiles = scoped.groupby("author_id").agg(
        display_name=("author_display_name", lambda s: s.dropna().mode().iat[0] if s.notna().any() else None),
        orcid=("orcid", lambda s: sorted({AL.norm_orcid(x) for x in s.dropna()} - {None})),
        works=("work_id", lambda s: sorted(set(s))),
    ).reset_index()
    profiles["n_works"] = profiles["works"].apply(len)
    profiles["orcid_single"] = profiles["orcid"].apply(lambda v: v[0] if len(v) == 1 else None)

    labs_of_work = works.set_index("work_id")["Labs"].to_dict()
    profiles["labs"] = profiles["works"].apply(
        lambda ws: sorted({lab for w in ws for lab in str(labs_of_work.get(w, "")).split(" | ")
                           if lab and lab != "NO LAB"})
    )

    # How many of an author's works actually credit THEM a Lorraine structure, as opposed to merely
    # being works in the Lorraine corpus? Without this the roster reads as if every prolific
    # collaborator were a Lorraine researcher: Silvio Danese (Humanitas / San Raffaele, Milan) has
    # 281 corpus works but exactly ONE authorship row crediting him a UL structure. v1 had the same
    # rule and no way to see the difference, which is what produced its "3,166 wrongly credited"
    # reading. The count is what lets any consumer set a threshold instead of guessing.
    ul_works_per_author = scoped[scoped["is_ul"]].groupby("author_id")["work_id"].nunique()
    ul_work_sets = scoped[scoped["is_ul"]].groupby("author_id")["work_id"].apply(lambda s: sorted(set(s)))
    profiles["ul_works"] = profiles["author_id"].map(ul_work_sets).apply(
        lambda v: v if isinstance(v, list) else []
    )
    # Count via a UNION of work ids, never a sum across merged profiles: summing per-profile counts
    # double-counts any work two merged profiles share, which produced the impossible
    # "170 corpus works / 192 UL-credited" row for Cyril Tarquinio on the first run.
    profiles["ul_credited_works"] = profiles["ul_works"].apply(len)
    profiles["ul_credited_share"] = (profiles["ul_credited_works"] / profiles["n_works"]).round(4)
    # the labs THIS author is credited to, distinct from the labs present on their works
    own = scoped[scoped["is_ul"]].copy()
    own["lab"] = own["institution_id"].map(
        {row.openalex_id: row.client_lab_name for row in descendants.itertuples()
         if pd.notna(row.client_lab_name)}
    )
    own_labs = own.dropna(subset=["lab"]).groupby("author_id")["lab"].apply(lambda s: sorted(set(s)))
    profiles["own_labs"] = profiles["author_id"].map(own_labs).apply(
        lambda v: v if isinstance(v, list) else []
    )
    single = int((profiles["ul_credited_works"] == 1).sum())
    print(f"  Lorraine profiles: {len(profiles):,} · credited a UL structure on exactly ONE work: "
          f"{single:,} ({single/len(profiles):.1%}) — external collaborators, not Lorraine staff")

    # --- HAL idHAL / ORCID attachment, matched within each shared work ----------------------
    hal_authors = load_hal_authors(snapshot)
    idhal_of: dict[str, str] = {}
    hal_orcid_of: dict[str, str] = {}
    if len(hal_authors):
        links = pd.read_parquet(tables / "hal_work_links.parquet")[["work_id", "hal_id"]].dropna()
        by_hal = {hid: block for hid, block in hal_authors.groupby("hal_id")}
        oa_by_work = {w: block for w, block in scoped.groupby("work_id")}
        matched = 0
        for work_id, hal_id in links.itertuples(index=False):
            hal_block, oa_block = by_hal.get(hal_id), oa_by_work.get(work_id)
            if hal_block is None or oa_block is None:
                continue
            for hal_row in hal_block.itertuples():
                best, best_score = None, 0.0
                hal_surname = AL.surname_key(str(hal_row.name))
                for oa_row in oa_block.drop_duplicates("author_id").itertuples():
                    oa_name = str(oa_row.author_display_name or "")
                    # Surname equality is REQUIRED, not just a good name_score: name_score compares
                    # given names (it is designed for candidates already grouped by surname), so on
                    # its own it paired HAL's "C. Taquinio" with OpenAlex's "Cyril Tarquinio" and
                    # hung idHAL `camille-louise-taquinio` on a profile of 170 works.
                    if not hal_surname or AL.surname_key(oa_name) != hal_surname:
                        continue
                    score = AL.name_score(str(hal_row.name), oa_name)
                    if score > best_score:
                        best, best_score = oa_row.author_id, score
                if best and best_score >= HAL_NAME_FLOOR:
                    matched += 1
                    if hal_row.idhal and best not in idhal_of:
                        idhal_of[best] = hal_row.idhal
        print(f"  HAL author entries matched to an OpenAlex author id: {matched:,} "
              f"-> {len(idhal_of):,} idHAL attachments (no ORCID: HAL has no aligned field)")
    profiles["idhal"] = profiles["author_id"].map(idhal_of)
    # No HAL ORCIDs: not attributable to a specific author (see load_hal_authors).
    profiles["orcid_hal"] = None
    profiles["orcid_effective"] = profiles["orcid_single"]

    # TRAP, and it silenced three of the five merge rules on the first run: pandas leaves missing
    # values as float NaN, and **NaN is truthy while NaN != NaN is True**. So
    # `if orcid_a and orcid_b and orcid_a != orcid_b` classified every pair where BOTH ORCIDs were
    # missing as an ORCID *conflict* — 18,282 pairs blocked (v1's figure was 4,592) and H2/H3/H4
    # fired 0 times against Phase 1's 492/227/298. Coerce to real None before any truth test.
    for column in ("orcid_effective", "idhal", "orcid_single", "orcid_hal"):
        profiles[column] = profiles[column].astype(object).where(profiles[column].notna(), None)
    print(f"  ORCID coverage (OpenAlex only; HAL's are not attributable): "
          f"{profiles['orcid_single'].notna().sum():,} · idHAL {profiles['idhal'].notna().sum():,}")

    # --- co-author sets, for rules H2/H3 --------------------------------------------------------
    work_authors = scoped.groupby("work_id")["author_id"].apply(lambda s: set(s)).to_dict()
    co_authors: dict[str, set] = defaultdict(set)
    for work_id, author_set in work_authors.items():
        for author in author_set:
            co_authors[author] |= author_set - {author}

    # --- candidate pairs: same surname key only (the whole point is to bridge name variants) ----
    by_surname: dict[str, list] = defaultdict(list)
    for row in profiles.itertuples():
        by_surname[AL.surname_key(str(row.display_name or ""))].append(row)

    uf = AL.UnionFind(list(profiles["author_id"]))
    evidence: list[dict] = []
    review: list[dict] = []
    counts = defaultdict(int)

    for surname, group in by_surname.items():
        if not surname or len(group) < 2:
            continue
        for a, b in combinations(group, 2):
            name_ok = AL.name_score(str(a.display_name or ""), str(b.display_name or "")) >= NAME_FLOOR
            shared_co = len(co_authors[a.author_id] & co_authors[b.author_id])
            shared_labs = set(a.labs) & set(b.labs)
            orcid_a, orcid_b = a.orcid_effective, b.orcid_effective
            conflict = bool(orcid_a and orcid_b and orcid_a != orcid_b)

            rule = None
            if orcid_a and orcid_b and orcid_a == orcid_b:
                rule = "H1_orcid_equal"
            elif conflict:
                counts["X_orcid_conflict_blocked"] += 1
                if shared_co >= 10 and shared_labs:
                    review.append({
                        "author_id_a": a.author_id, "name_a": a.display_name, "orcid_a": orcid_a,
                        "author_id_b": b.author_id, "name_b": b.display_name, "orcid_b": orcid_b,
                        "shared_co_authors": shared_co, "shared_labs": " | ".join(sorted(shared_labs)),
                        "works_a": a.n_works, "works_b": b.n_works,
                        "reason": "ORCID conflict but strong corroboration — human adjudication",
                    })
                continue
            elif a.idhal and b.idhal and a.idhal == b.idhal:
                rule = "H1b_idhal_equal"
            elif name_ok and shared_co >= CO_AUTHOR_FLOOR:
                rule = "H2_name_and_3_coauthors"
            elif name_ok and shared_labs and shared_co >= 1:
                rule = "H3_name_lab_and_coauthor"
            elif (AL.norm_text(a.display_name) == AL.norm_text(b.display_name)) and shared_labs:
                rule = "H4_identical_name_and_lab"

            if rule:
                uf.union(a.author_id, b.author_id)
                counts[rule] += 1
                evidence.append({
                    "rule": rule, "author_id_a": a.author_id, "name_a": a.display_name,
                    "author_id_b": b.author_id, "name_b": b.display_name,
                    "shared_co_authors": shared_co, "shared_labs": " | ".join(sorted(shared_labs)),
                })

    profiles["person_id"] = profiles["author_id"].map(lambda x: uf.find(x))
    people = profiles.groupby("person_id").agg(
        display_name=("display_name", lambda s: s.dropna().mode().iat[0] if s.notna().any() else None),
        profile_ids=("author_id", lambda s: sorted(set(s))),
        orcids=("orcid_effective", lambda s: sorted({x for x in s.dropna()})),
        idhals=("idhal", lambda s: sorted({x for x in s.dropna()})),
        works=("works", lambda s: sorted({w for ws in s for w in ws})),
        labs=("labs", lambda s: sorted({lab for ls in s for lab in ls})),
        own_labs=("own_labs", lambda s: sorted({lab for ls in s for lab in ls})),
        ul_works=("ul_works", lambda s: sorted({w for ws in s for w in ws})),
    ).reset_index()
    people["n_profiles"] = people["profile_ids"].apply(len)
    # A person should hold ONE idHAL. Two means the cluster probably merged two people — e.g. Cyril
    # Tarquinio ended up with both `cyril-tarquinio` and `camille-louise-taquinio`. Surfaced for
    # adjudication rather than silently kept, the same policy as the ORCID-conflict queue.
    people["n_idhals"] = people["idhals"].apply(len)
    people["n_works"] = people["works"].apply(len)

    # per-person indicators, over works whose stratum was thick enough
    metrics = pd.read_parquet(tables / "corpus_metrics.parquet").set_index("work_id")
    computed_ids = set(metrics[metrics["indicator_status"] == "computed"].index)
    fwci = metrics["FWCI_FR"].to_dict()
    pptop = metrics["PPtop10_FR"].to_dict()
    cites = works.set_index("work_id")["cited_by_count"].to_dict()
    people["citations"] = people["works"].apply(lambda ws: int(sum(cites.get(w, 0) or 0 for w in ws)))
    people["works_with_indicators"] = people["works"].apply(lambda ws: sum(1 for w in ws if w in computed_ids))
    people["FWCI_FR_mean"] = people["works"].apply(
        lambda ws: round(sum(fwci.get(w, 0) or 0 for w in ws if w in computed_ids)
                         / max(sum(1 for w in ws if w in computed_ids), 1), 4) or None
    )
    people["PPtop10_FR_count"] = people["works"].apply(
        lambda ws: int(sum(1 for w in ws if w in computed_ids and bool(pptop.get(w))))
    )
    people["ul_credited_works"] = people["ul_works"].apply(len)
    people["ul_credited_share"] = (people["ul_credited_works"] / people["n_works"]).round(4)
    assert (people["ul_credited_works"] <= people["n_works"]).all(),         "UL-credited works exceed corpus works for some person — the union collapsed wrongly"
    people["labs_joined"] = people["labs"].apply(lambda v: " | ".join(v))
    people["own_labs_joined"] = people["own_labs"].apply(lambda v: " | ".join(v))
    people["profiles_joined"] = people["profile_ids"].apply(lambda v: " | ".join(v))
    people["orcids_joined"] = people["orcids"].apply(lambda v: " | ".join(v))
    people["idhals_joined"] = people["idhals"].apply(lambda v: " | ".join(map(str, v)))


    out = tables / "ul_authors.parquet"
    people.drop(columns=["works", "labs", "own_labs", "ul_works", "profile_ids", "orcids",
                         "idhals"]).to_parquet(
        out, index=False, compression=CONFIG["storage"]["compression"]
    )
    multi_idhal = people[people["n_idhals"] > 1]
    if len(multi_idhal):
        extra = multi_idhal.assign(
            reason="cluster holds >1 idHAL - probable over-merge of two people",
        )[["person_id", "display_name", "n_profiles", "n_works", "idhals_joined", "reason"]]
        extra.to_parquet(tables / "ul_authors_multi_idhal.parquet", index=False,
                         compression=CONFIG["storage"]["compression"])
    ev_path = tables / "ul_authors_merge_evidence.parquet"
    rq_path = tables / "ul_authors_review_queue.parquet"
    pd.DataFrame(evidence).to_parquet(ev_path, index=False, compression=CONFIG["storage"]["compression"])
    pd.DataFrame(review).sort_values("shared_co_authors", ascending=False).to_parquet(
        rq_path, index=False, compression=CONFIG["storage"]["compression"]
    ) if review else pd.DataFrame(columns=["author_id_a"]).to_parquet(rq_path, index=False)

    merged = len(profiles) - len(people)
    multi = int((people["n_profiles"] > 1).sum())
    lines = [
        f"- Lorraine author profiles: **{len(profiles):,}** -> **{len(people):,} people** "
        f"({merged:,} absorbed; {multi:,} people rebuilt from more than one profile, "
        f"largest {int(people['n_profiles'].max())} profiles)",
        f"- merge rules fired: " + " · ".join(f"{k} **{v:,}**" for k, v in sorted(counts.items())),
        f"- identifiers: **{int(profiles['orcid_single'].notna().sum()):,}** profiles carry an ORCID "
        f"(OpenAlex only - HAL publishes no aligned name-to-ORCID field, so its ORCIDs cannot be "
        f"attributed) · **{int(profiles['idhal'].notna().sum()):,}** carry an idHAL, from the aligned "
        f"`authFullNameIdHal_fs` pairs",
        f"- review queue (ORCID conflict + strong corroboration): **{len(review):,}** pairs",
        f"- **{int((people['n_idhals'] > 1).sum()):,} clusters hold more than one idHAL** and are "
        f"listed in `ul_authors_multi_idhal.parquet` for adjudication — a person should hold one, so "
        f"these are probable over-merges (e.g. `cyril-tarquinio` + `camille-louise-taquinio`)",
        f"- **{int((people['ul_credited_works'] == 1).sum()):,} people are credited a Lorraine structure "
        f"on exactly one work** and {int((people['ul_credited_works'] >= 5).sum()):,} on five or more. "
        f"Use `ul_credited_works` to separate Lorraine researchers from external collaborators: e.g. "
        f"Silvio Danese (Humanitas/San Raffaele, Milan) has 281 corpus works but 1 UL-credited row. "
        f"v1 had no such column, which is where its '3,166 wrongly credited' reading came from.",
        f"- v1 comparison: v1 reported 12,729 profiles → 11,709 people (1,020 absorbed) on OpenAlex "
        f"ORCIDs alone, where equal-ORCID merges numbered just 3",
        "",
        "| Person | Profiles | Corpus works | UL-credited | Citations | mean FWCI_FR | Own labs |",
        "|---|---|---|---|---|---|---|",
    ]
    ranked = people[people["ul_credited_works"] >= 5].sort_values("n_works", ascending=False)
    for row in ranked.head(12).itertuples():
        lines.append(f"| {row.display_name} | {row.n_profiles} | {row.n_works:,} | "
                     f"{row.ul_credited_works:,} | {row.citations:,} | "
                     f"{'' if not row.FWCI_FR_mean else f'{row.FWCI_FR_mean:.2f}'} | "
                     f"{str(row.own_labs_joined)[:40]} |")

    report = ROOT / CONFIG["paths"]["reports"] / "ul_authors.md"
    report.write_text("# ul_authors (dataset only, no view — D15)\n\n" + "\n".join(lines) + "\n",
                      encoding="utf-8")
    Manifest(snapshot).record_step(
        "45_build_authors",
        counts={"profiles": len(profiles), "people": len(people), "absorbed": merged,
                "review_queue": len(review), "multi_idhal_clusters": int(len(multi_idhal)),
                **{k: int(v) for k, v in counts.items()}},
        files=[out, ev_path, rq_path] + ([tables / "ul_authors_multi_idhal.parquet"]
                                         if len(multi_idhal) else []),
        params={"name_floor": NAME_FLOOR, "co_author_floor": CO_AUTHOR_FLOOR,
                "hal_name_floor": HAL_NAME_FLOOR, "orcid_conflict": "block, never merge"},
        notes="Native authorship rows (no [n] parsing); idHAL added as a v2 merge signal.",
    )
    append_summary(snapshot, "45_build_authors", lines[:5])
    print("\n".join(lines))
    print(f"\nwrote {out.name}, {ev_path.name}, {rq_path.name} and {report}")


if __name__ == "__main__":
    main()
