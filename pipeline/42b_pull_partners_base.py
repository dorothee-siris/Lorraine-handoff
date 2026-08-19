"""42b_pull_partners_base.py -- partner-own-output denominators for page 4 reciprocity (D58).

Contract finding (Stream A, `docs/DATA_CONTRACT.md` Open risk 1): page 4's reciprocity chart and
the "% of partner's <level>" column need each partner's OWN output at a taxonomy level -- that is
by definition OUTSIDE the UL corpus, so nothing in the snapshot can produce it. This is a PULL
step, not a build step, despite the pipeline-numbering fence calling it `42b_build_partners_base`.

Cost-consciousness (D58 / SIRIS protocol): we do not pull this for all 12,553 rows of
`ul_partners.parquet` (v2's correctly-built, uncapped partner list -- v1's 3,288-row file was
undercounted by its [k]-indexed parsing defect, D34-class). We pull it only for partners that can
actually appear in a level's top-20/top-50 list -- the UNION, across every REQUIRED level (domain,
field, subfield -- topic is optional per the contract and not pulled here to keep the budget cheap),
of: top 20 international partners by co-works, top 20 French partners by co-works, top 50
"reciprocity" partners by co-works. Measured 2026-08-11: 3,260 distinct partners, matching Stream
A's independent `rows_expected_approx: 3224` almost exactly -- both are the same quantity, derived
two different ways.

Per partner, OpenAlex's `group_by` caps at 200 buckets and there are 252 subfields, so a SINGLE
`group_by=primary_topic.subfield.id` call is provably insufficient for high-diversity partners
(measured: CNRS returns exactly 200 buckets and undercounts by ~2,051 works). The adaptive design
below tries the cheap single call first and only pays the expensive per-field fallback (26 calls)
for partners where it demonstrably undercounts -- calibrated to be a small minority.

Usage
  python pipeline/42b_pull_partners_base.py --calibrate         # <=10 partners, no snapshot write
  python pipeline/42b_pull_partners_base.py                     # full pull, resumable
  python pipeline/42b_pull_partners_base.py --resume            # skip partners already in the cache
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.openalex import OpenAlexClient, ascii_safe_stdout, load_env, short_id  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)
TOP_INT = 20
TOP_FR = 20
TOP_RECIPROCITY = 50
# Pass-4 (challenge memo #2): hard spend guard for the unattended full run. The user's $3 cap
# = 30,000 filter-shaped calls, minus the 1,096 calls spent by the first (guard-aborted) slice
# of 2026-08-17 whose 100 partners sit in the resume cache. Guard rev 2 aborts on ACTUAL calls.
CALL_BUDGET = 28_900
REQUIRED_LEVELS = [("domain", "primary_domain_id"), ("field", "primary_field_id"),
                   ("subfield", "primary_subfield_id")]
SEP = " | "  # policy separator for positional blobs (distinct from the ':'/'|' record blobs)


def doc_type_filter() -> str:
    types = "|".join(CONFIG["corpus_filter"]["doc_types_keep"])
    return f"publication_year:{CONFIG['window']['year_from']}-{CONFIG['window']['year_to']},type:{types}," \
           "is_retracted:false,is_paratext:false"


def needed_partner_ids(works: pd.DataFrame, authorships: pd.DataFrame, own_ids: set[str]) -> set[str]:
    """The union of partners that can appear in ANY required level's top-20/top-50 list.

    Mirrors, as closely as a local groupby can, the ranking `44e_build_detail_partners.py` computes
    from the same tables -- so `ul_partners_base` covers exactly what the app needs and nothing more.
    """
    inst = authorships.dropna(subset=["institution_id"])[
        ["work_id", "institution_id", "institution_ror", "institution_country"]
    ].drop_duplicates(["work_id", "institution_id"])
    inst = inst[~inst["institution_id"].isin(own_ids)]
    inst = inst[inst["institution_ror"].notna()]
    meta = works.set_index("work_id")[[c for _, c in REQUIRED_LEVELS]]
    joined = inst.join(meta, on="work_id")

    needed: set[str] = set()
    for level, column in REQUIRED_LEVELS:
        scoped = joined.dropna(subset=[column])
        for _, block in scoped.groupby(column, observed=True):
            counts = block.groupby("institution_id").size().sort_values(ascending=False)
            needed |= set(counts.head(TOP_RECIPROCITY).index)
            fr_counts = (
                block[block["institution_country"] == "FR"]
                .groupby("institution_id").size().sort_values(ascending=False)
            )
            needed |= set(fr_counts.head(TOP_FR).index)
            # Pass-4 fix (challenge memo #1): 44e's visible list is top-20 of the NON-FR block
            # (44e:171 uses != "FR", which keeps null-country rows) — the overall top-50 is NOT
            # a superset of it because French partners crowd the head. Mirror 44e exactly.
            int_counts = (
                block[block["institution_country"] != "FR"]
                .groupby("institution_id").size().sort_values(ascending=False)
            )
            needed |= set(int_counts.head(TOP_INT).index)
    return needed


def group_by_call(client: OpenAlexClient, filt: str, dimension: str) -> tuple[dict[str, int], int]:
    """One group_by call. Returns {bare_id: count} and meta.count (the TOTAL, not bucket sum)."""
    page = client.get("/works", filter=filt, group_by=dimension, per_page=200)
    buckets = {short_id(g["key"]): g["count"] for g in page["group_by"] if g["key"] not in (None, "unknown")}
    return buckets, page["meta"]["count"]


def pull_one_partner_by_filter(client: OpenAlexClient, label_id: str, base_filter: str,
                                all_topics: pd.DataFrame, verify_domains: bool = False) -> dict:
    """Adaptive per-field-fallback pull, generalized to an arbitrary OpenAlex filter string.

    Pass-4 (challenge memo #9): the merged-pair union pull (`institutions.id:A|B`) reuses this
    exact same identity/rollup/fallback logic -- only the filter string and the row's `Partner ID`
    label differ from the ordinary single-id pull. `pull_one_partner` below is the thin wrapper
    that builds the single-id filter; `main()`'s merged-pair loop calls this directly with the
    pipe-union filter and the CANONICAL (successor) id as `label_id`.
    """
    field_counts, total = group_by_call(client, base_filter, "primary_topic.field.id")

    field_ids = sorted(all_topics["field_id"].unique())
    subfields_by_field = {
        f: sorted(all_topics.loc[all_topics["field_id"] == f, "subfield_id"].unique()) for f in field_ids
    }

    # Pass-4 efficiency edit 1 (probe-justified, reports/data/pass4_42b_fallback_probe.json):
    # primary_topic's domain/field/subfield roll up from ONE topic, so a work's primary domain is
    # exactly its primary field's domain — the domain group_by is derivable, not pullable.
    # In calibration (verify_domains=True) the call is still made and the identity ASSERTED.
    field_to_domain = all_topics.drop_duplicates("field_id").set_index("field_id")["domain_id"].to_dict()
    domain_counts: dict[str, int] = {}
    for f, c in field_counts.items():
        d = str(field_to_domain[int(f)])
        domain_counts[d] = domain_counts.get(d, 0) + c
    if verify_domains:
        called_domains, _ = group_by_call(client, base_filter, "primary_topic.domain.id")
        assert called_domains == domain_counts, (
            f"{label_id}: derived domain counts {domain_counts} != called {called_domains}"
        )

    # cheap path: one call across all subfields
    sub_counts, sub_total = group_by_call(client, base_filter, "primary_topic.subfield.id")
    capped = len(sub_counts) >= 200
    undercounted = sum(sub_counts.values()) < sum(field_counts.values())
    fallback_used = False
    if capped or undercounted:
        # Pass-4 efficiency edit 2: the cheap call's missing buckets are its globally smallest
        # counts; a field whose cheap subfield-sum already equals its field count is complete and
        # provably consistent — only DISAGREEING fields are re-pulled (was: all 26, ~2x the cost).
        # Per-field calls stay exact: filtered to one field, 252>buckets>=its subfields never cap.
        fallback_used = True
        subfield_to_field = all_topics.drop_duplicates("subfield_id").set_index("subfield_id")["field_id"].to_dict()
        cheap_sum_by_field: dict[int, int] = {}
        for s, c in sub_counts.items():
            cheap_sum_by_field[subfield_to_field[int(s)]] = cheap_sum_by_field.get(subfield_to_field[int(s)], 0) + c
        disagreeing = [f for f in field_ids if cheap_sum_by_field.get(f, 0) != field_counts.get(str(f), 0)]
        for f in disagreeing:
            f_counts, _ = group_by_call(
                client, f"{base_filter},primary_topic.field.id:{f}", "primary_topic.subfield.id"
            )
            # replace this field's cheap buckets wholesale with the exact ones
            sub_counts = {s: c for s, c in sub_counts.items() if subfield_to_field[int(s)] != f}
            sub_counts.update(f_counts)
        # post-merge invariant: every field's subfield-sum equals its field count (rollup identity)
        merged_by_field: dict[int, int] = {}
        for s, c in sub_counts.items():
            merged_by_field[subfield_to_field[int(s)]] = merged_by_field.get(subfield_to_field[int(s)], 0) + c
        bad = {f: (merged_by_field.get(f, 0), field_counts.get(str(f), 0))
               for f in field_ids if merged_by_field.get(f, 0) != field_counts.get(str(f), 0)}
        assert not bad, f"{label_id}: post-fallback field/subfield mismatch {bad}"

    domain_ids = sorted(all_topics["domain_id"].unique())
    row = {
        "Partner ID": label_id,
        "Pubs count (partner total)": int(total),
        "Pubs breakdown per domain (partner total)": SEP.join(
            str(domain_counts.get(str(d), 0)) for d in domain_ids
        ),
        "Pubs breakdown per field (partner total)": SEP.join(
            str(field_counts.get(str(f), 0)) for f in field_ids
        ),
        "_fallback_used": fallback_used,
        "_calls_used": None,  # filled by the caller from client.calls delta
    }
    for f in field_ids:
        subs = subfields_by_field[f]
        row[f"__subfamily__{f}"] = SEP.join(str(sub_counts.get(str(s), 0)) for s in subs)
    return row


def pull_one_partner(client: OpenAlexClient, partner_id: str, all_topics: pd.DataFrame,
                     verify_domains: bool = False) -> dict:
    base_filter = f"institutions.id:{partner_id},{doc_type_filter()}"
    return pull_one_partner_by_filter(client, partner_id, base_filter, all_topics, verify_domains)


def pull_merged_union_rows(client: OpenAlexClient, all_topics: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Pass-4 (challenge memo #9): ONE row per status==ok `successor_merges.csv` pair, keyed by
    the CANONICAL (successor) id, pulled with the pipe-union filter `institutions.id:A|B` --
    OpenAlex counts DISTINCT works over the union by construction (the Freiberg distinct-union
    rule, already precedented for the EURECA consortium). This is the denominator
    `46_build_partner_views.py` must use for these 3 partners' `share_p`/`baseline_partner_share`:
    their ptn_summary/ptn_fields `partner_id` is already the canonical id and its `co_works_full`
    numerator already sums BOTH members' UL-collaboration (via 46's own `merge_map` fold), so the
    denominator must be the same union, not the successor's own portfolio alone.

    Written to a SEPARATE sidecar file (`ul_partners_base_merged.parquet`), never appended into
    `ul_partners_base.parquet` itself: the successor id frequently ALSO independently clears the
    ordinary needed-set threshold on its own raw id (e.g. INRAE alone), which would give
    `ul_partners_base.parquet` two rows for the same `Partner ID` -- `44e_build_detail_partners.py`
    (out of this stream's scope fence, run but never edited) does `base.set_index("Partner ID")`
    then `.loc[partner_id]` assuming a UNIQUE index; a duplicate silently returns a DataFrame
    instead of a Series and crashes the very next `.split(" | ")` call. Keeping the union rows in
    their own file preserves `ul_partners_base.parquet`'s uniqueness (and therefore 44e's
    correctness) while still giving `46_build_partner_views.py` -- which reads BOTH files -- exactly
    what challenge memo #9 asked for.

    Returns (merged_rows, verify_triples) -- verify_triples hand-checks
    max(member totals) <= union <= sum(member totals) for each pair.
    """
    merges = pd.read_csv(ROOT / "inputs" / "overlays" / "successor_merges.csv",
                          encoding="utf-8", keep_default_na=False)
    merges_ok = merges[merges["status"] == "ok"]
    print(f"\nmerged-pair union pulls (challenge memo #9): {len(merges_ok)} status==ok pairs "
          f"in successor_merges.csv")

    merged_rows: list[dict] = []
    verify_triples: list[dict] = []
    for _, mrow in merges_ok.iterrows():
        old_id, succ_id, label = mrow["old_id"], mrow["successor_id"], mrow["label"]
        union_filter = f"institutions.id:{old_id}|{succ_id},{doc_type_filter()}"
        before = client.calls
        union_row = pull_one_partner_by_filter(client, succ_id, union_filter, all_topics)
        union_row["_calls_used"] = client.calls - before
        union_row["_merged_union"] = True
        union_row["_merged_member_ids"] = f"{old_id}|{succ_id}"
        merged_rows.append(union_row)

        # hand-verification triple: max(member totals) <= union <= sum(member totals)
        old_total = client.count(f"institutions.id:{old_id},{doc_type_filter()}")
        succ_total = client.count(f"institutions.id:{succ_id},{doc_type_filter()}")
        union_total = union_row["Pubs count (partner total)"]
        ok = max(old_total, succ_total) <= union_total <= (old_total + succ_total)
        triple = {
            "label": label, "old_id": old_id, "successor_id": succ_id,
            "old_total": old_total, "successor_total": succ_total, "union_total": union_total,
            "max_member": max(old_total, succ_total), "sum_members": old_total + succ_total,
            "check_pass": ok,
        }
        verify_triples.append(triple)
        print(f"  [{label}] old({old_id})={old_total:,} | successor({succ_id})={succ_total:,} | "
              f"union={union_total:,} -- max<=union<=sum: "
              f"{triple['max_member']:,} <= {union_total:,} <= {triple['sum_members']:,} "
              f"{'PASS' if ok else 'FAIL'}")
        assert ok, f"merged-union triple check FAILED for {label}: {triple}"

    return merged_rows, verify_triples


def subfield_family_columns(all_topics: pd.DataFrame) -> dict[int, str]:
    """field_id -> the exact contract column name for its subfield family, with field DISPLAY name."""
    names = all_topics.drop_duplicates("field_id").set_index("field_id")["field_name"].to_dict()
    return {
        f: f'Pubs per subfield within "{names[f]}" (id: {f}) (partner total)'
        for f in sorted(all_topics["field_id"].unique())
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--calibrate", type=int, default=0, help="pull only N partners, no snapshot write")
    parser.add_argument("--resume", action="store_true", help="skip partner ids already in the cache parquet")
    args = parser.parse_args()

    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=not bool(args.calibrate))
    tables = snapshot / "tables"

    works = pd.read_parquet(tables / "works_master.parquet")
    authorships = pd.read_parquet(tables / "corpus_authorships.parquet")
    descendants = pd.read_parquet(tables / "ul_descendants.parquet")
    ul_partners = pd.read_parquet(tables / "ul_partners.parquet")
    all_topics = pd.read_parquet(tables / "all_topics.parquet")
    all_topics = all_topics.assign(
        domain_id=all_topics["domain_id"].astype(str),
        field_id=all_topics["field_id"].astype(str).astype(int),
        subfield_id=all_topics["subfield_id"].astype(str).astype(int),
    )

    own_ids = set(descendants["openalex_id"]) | {CONFIG["perimeter"]["ul_openalex_id"]}
    needed = needed_partner_ids(works, authorships, own_ids)
    print(f"snapshot {snapshot.name}: {len(ul_partners):,} rows in ul_partners.parquet, "
          f"{len(needed):,} distinct partners appear in a required-level top-20/top-50 list")

    meta_cols = ul_partners.set_index("institution_id")[["institution_name", "sector", "country", "ror", "co_works"]]
    order = meta_cols.reindex(sorted(needed, key=lambda i: -meta_cols["co_works"].get(i, 0)))
    partner_ids = list(order.index)

    env = load_env(CONFIG["secrets"]["env_file"], CONFIG["secrets"]["required"])
    client = OpenAlexClient(CONFIG, env)
    fam_cols = subfield_family_columns(all_topics)

    if args.calibrate:
        n = args.calibrate
        sample = partner_ids[:n]
        print(f"CALIBRATION -- {len(sample)} partners (largest-co_works-first, worst case for the "
              f"200-bucket fallback), no snapshot write\n")
        t0 = time.time()
        rows = []
        for pid in sample:
            before = client.calls
            # verify_domains: calibration still makes the domain call and asserts the derivation
            row = pull_one_partner(client, pid, all_topics, verify_domains=True)
            row["_calls_used"] = client.calls - before
            rows.append(row)
            print(f"  {pid} ({meta_cols.loc[pid, 'institution_name'][:40]:40}) co_works="
                  f"{int(meta_cols.loc[pid,'co_works']):>6,} -> {row['_calls_used']} calls"
                  f"{' [FALLBACK]' if row['_fallback_used'] else ''}")
        elapsed = time.time() - t0
        calls_per_partner = sum(r["_calls_used"] for r in rows) / len(rows)
        fallback_rate = sum(r["_fallback_used"] for r in rows) / len(rows)
        projected_calls = calls_per_partner * len(needed)
        # a fallback-heavy calibration sample (largest-first) overestimates the true fallback rate;
        # report both this worst-case number and a corrected projection assuming fallback needed
        # only for the ~top-50-by-co_works partners (empirically the group most likely to be diverse).
        print(f"\nmeasured: {calls_per_partner:.1f} calls/partner avg, {elapsed/len(sample):.2f} s/partner, "
              f"fallback used {sum(r['_fallback_used'] for r in rows)}/{len(sample)} times")
        print(f"WORST-CASE projection (if this sample's fallback rate held for all {len(needed):,} "
              f"partners): {projected_calls:,.0f} calls, ~${projected_calls*0.0001:,.2f}, "
              f"~{projected_calls/20/60:.1f} min at 20 req/s")
        cheap_calls = 2 * len(needed)  # field + one subfield attempt, per partner (domain derived)
        print(f"LIKELY projection (fallback only for large/diverse partners, not the whole tail): "
              f"~{cheap_calls:,.0f} baseline calls + a small fallback tail, ~${cheap_calls*0.0001:,.2f}+ ")
        print("NOTE calibration adds 1 verify-domains call per partner that the full run does not make.")
        return

    cache_path = tables / "ul_partners_base_raw.parquet"
    done_ids: set[str] = set()
    existing_rows: list[dict] = []
    if args.resume and cache_path.exists():
        cached = pd.read_parquet(cache_path)
        existing_rows = cached.to_dict("records")
        done_ids = set(cached["Partner ID"])
        print(f"resuming: {len(done_ids):,} partners already cached")

    rows = existing_rows
    todo = [p for p in partner_ids if p not in done_ids]
    t0 = time.time()
    fallback_n = 0
    for i, pid in enumerate(todo, 1):
        row = pull_one_partner(client, pid, all_topics)
        row["_calls_used"] = None
        fallback_n += int(row["_fallback_used"])
        rows.append(row)
        if i % 100 == 0 or i == len(todo):
            elapsed = time.time() - t0
            print(f"  {i:,}/{len(todo):,} partners · {client.calls:,} calls so far · "
                  f"{elapsed/60:.1f} min elapsed · fallback used {fallback_n} times", flush=True)
            pd.DataFrame(rows).to_parquet(cache_path, index=False)  # checkpoint every 100 (resumable)
            # Guard rev 2 (manager, after the 100/3,616 false-positive abort): the todo list is
            # sorted largest-first, so a linear projection from the head is upward-biased by
            # construction (measured 10.96 calls/partner over the worst-case first 100 vs ~4-5
            # expected overall). The projection is PRINTED for monitoring only; the abort triggers
            # on ACTUAL spend -- the run is checkpointed+resumable, so the hard stop cannot
            # overshoot the cap.
            projected = client.calls + (client.calls / i) * (len(todo) - i)
            print(f"    naive projection (upward-biased early, monitoring only): {projected:,.0f} calls",
                  flush=True)
            if client.calls >= CALL_BUDGET:
                print(f"ABORT (spend guard): actual calls this run ({client.calls:,}) reached the "
                      f"budget of {CALL_BUDGET:,} (~${CALL_BUDGET*0.0001:.2f}). Cache checkpointed at "
                      f"{i:,}/{len(todo):,} partners -- rerun with --resume after review.", flush=True)
                sys.exit(2)

    raw_frame = pd.DataFrame(rows)
    raw_frame.to_parquet(cache_path, index=False)

    def assemble_row(row: dict) -> dict:
        """Identity + volume columns + the 26 subfield-family blobs, deployed shape."""
        pid = row["Partner ID"]
        meta = meta_cols.loc[pid] if pid in meta_cols.index else None
        out = {
            "Partner ID": pid,
            "Partner name": meta["institution_name"] if meta is not None else None,
            "Partner type": meta["sector"] if meta is not None else None,
            "Country": meta["country"] if meta is not None else None,
            "Partner ROR": meta["ror"] if meta is not None else None,
            "Copublications": int(meta["co_works"]) if meta is not None else None,
            "Pubs count (partner total)": row["Pubs count (partner total)"],
            "Pubs breakdown per domain (partner total)": row["Pubs breakdown per domain (partner total)"],
            "Pubs breakdown per field (partner total)": row["Pubs breakdown per field (partner total)"],
        }
        for f, colname in fam_cols.items():
            out[colname] = row.get(f"__subfamily__{f}", "")
        return out

    # assemble the deployed-shape frame: identity + volume columns + the 26 subfield-family blobs
    out_rows = [assemble_row(row) for row in rows]

    table = pd.DataFrame(out_rows)
    out = tables / "ul_partners_base.parquet"
    table.to_parquet(out, index=False, compression=CONFIG["storage"]["compression"])

    # Pass-4 (challenge memo #9): merged-pair union rows, kept in a SEPARATE sidecar file so
    # ul_partners_base.parquet's "Partner ID" stays unique (see pull_merged_union_rows docstring
    # for why -- 44e's `.set_index("Partner ID").loc[...]` pattern would silently break on a
    # duplicate). Resumable: skipped if the sidecar already exists and --resume was passed.
    merged_path = tables / "ul_partners_base_merged.parquet"
    if args.resume and merged_path.exists():
        merged_table = pd.read_parquet(merged_path)
        verify_triples = []
        print(f"\nmerged-pair union pulls: sidecar already cached ({len(merged_table)} rows), "
              f"skipping re-pull (--resume)")
    else:
        merged_rows, verify_triples = pull_merged_union_rows(client, all_topics)
        merged_out_rows = []
        for mrow in merged_rows:
            assembled = assemble_row(mrow)
            assembled["_merged_union"] = mrow["_merged_union"]
            assembled["_merged_member_ids"] = mrow["_merged_member_ids"]
            merged_out_rows.append(assembled)
        merged_table = pd.DataFrame(merged_out_rows)
        merged_table.to_parquet(merged_path, index=False, compression=CONFIG["storage"]["compression"])

    lines = [
        f"- partner-own-output rows: **{len(table):,}** (needed set: {len(needed):,}; "
        f"pulled: {len(rows):,})",
        f"- merged-pair union rows: **{len(merged_table):,}** (challenge memo #9; sidecar file "
        f"`ul_partners_base_merged.parquet`, keyed by the canonical/successor id, kept OUT of "
        f"`ul_partners_base.parquet` to preserve its Partner-ID uniqueness for 44e)",
        f"- API calls used this run: **{client.calls:,}**",
        f"- fallback (per-field subfield breakdown) used for **{fallback_n:,}** partners "
        f"(the 200-bucket cap would otherwise undercount their subfield diversity)",
        f"- scoping mirrors the corpus window ({CONFIG['window']['year_from']}-"
        f"{CONFIG['window']['year_to']}) and doc types ({', '.join(CONFIG['corpus_filter']['doc_types_keep'])})",
    ]
    Manifest(snapshot).record_step(
        "42b_pull_partners_base",
        filters={"doc_type_filter": doc_type_filter()},
        api_base=CONFIG["openalex"]["base_url"],
        api_calls=client.calls,
        counts={"partners": len(table), "needed_set": len(needed), "fallback_used": fallback_n,
                "merged_union_pairs": len(merged_table)},
        files=[out, cache_path, merged_path],
        params={"top_int": TOP_INT, "top_fr": TOP_FR, "top_reciprocity": TOP_RECIPROCITY,
                "required_levels": [lvl for lvl, _ in REQUIRED_LEVELS],
                "merged_union_verify_triples": verify_triples},
        notes="D58: a PULL step, not a build step. Scoped to partners referenced by a required-level "
              "top-20/top-50 list, not all of ul_partners, per the cost & rigor protocol. Pass-4 "
              "adds one pipe-union pull per status==ok successor_merges.csv pair (challenge memo "
              "#9), written to ul_partners_base_merged.parquet.",
    )
    append_summary(snapshot, "42b_pull_partners_base", lines)
    print("\n".join(lines))
    print(f"\nwrote {out.name}")


if __name__ == "__main__":
    main()
