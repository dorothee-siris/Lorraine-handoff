"""12_ul_descendants.py — UL's own structures according to OpenAlex, and which ones the client's list misses.

Two jobs, both consequences of D20:

1. **Correctness.** OpenAlex places 90 institutions under `lineage:I90183372`, but the client's list
   names only 68. Without this table those 22 structures are treated as *external partners* —
   `42_build_partners` had "Laboratoire Lorrain de Sciences Sociales" sitting in the top 15
   collaborators with 690 co-works, which is UL collaborating with itself.
2. **A deliverable.** The "structures détectées hors liste" report the client rules on at the
   workshop: what OpenAlex thinks belongs to UL that their reference file does not name.

Note the endpoint asymmetry: `institutions` accepts `filter=lineage:`, while `works` needs
`authorships.institutions.lineage:` (bare `lineage:` on works is HTTP 400).

Usage: python pipeline/12_ul_descendants.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.openalex import OpenAlexClient, ascii_safe_stdout, load_env, short_id  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)
SELECT = "id,display_name,ror,country_code,type,works_count,lineage"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    env = load_env(CONFIG["secrets"]["env_file"], CONFIG["secrets"]["required"])
    client = OpenAlexClient(CONFIG, env)
    ul_id = CONFIG["perimeter"]["ul_openalex_id"]

    records: list[dict] = []
    cursor = "*"
    while cursor:
        page = client.get("/institutions", filter=f"lineage:{ul_id}", per_page=200,
                          cursor=cursor, select=SELECT)
        for item in page["results"]:
            records.append({
                "openalex_id": short_id(item["id"]),
                "display_name": item.get("display_name"),
                "ror": (item.get("ror") or "").rsplit("/", 1)[-1] or None,
                "country_code": item.get("country_code"),
                "type": item.get("type"),
                "works_count_alltime": item.get("works_count"),
                "lineage_depth": len(item.get("lineage") or []),
            })
        cursor = page["meta"].get("next_cursor")
        if not page["results"]:
            break
    descendants = pd.DataFrame(records)
    print(f"OpenAlex places {len(descendants)} institutions under lineage:{ul_id}")

    labs = pd.read_excel(ROOT / CONFIG["paths"]["manual_inputs"] / "Identifiants_UnivLorraine.xlsx")
    repairs = CONFIG["perimeter"].get("openalex_id_repairs") or {}
    curated = {repairs.get(str(x).strip(), str(x).strip()) for x in labs["OpenAlex"].dropna()}
    name_of = {repairs.get(str(r.OpenAlex).strip(), str(r.OpenAlex).strip()): r.Laboratoire
               for r in labs.itertuples() if pd.notna(r.OpenAlex)}

    descendants["in_client_list"] = descendants["openalex_id"].isin(curated | {ul_id})
    descendants["client_lab_name"] = descendants["openalex_id"].map(name_of)

    # how many corpus works does each unmapped structure actually touch?
    authorships = pd.read_parquet(tables / "corpus_authorships.parquet")
    per_institution = authorships.drop_duplicates(["work_id", "institution_id"]) \
        .groupby("institution_id").size()
    descendants["corpus_works"] = descendants["openalex_id"].map(per_institution).fillna(0).astype(int)

    unmapped = descendants[~descendants["in_client_list"]].sort_values("corpus_works", ascending=False)
    print(f"  in the client's list: {int(descendants['in_client_list'].sum())} · "
          f"NOT in it: {len(unmapped)} (touching {int(unmapped['corpus_works'].sum()):,} corpus works)")

    out = tables / "ul_descendants.parquet"
    descendants.to_parquet(out, index=False, compression=CONFIG["storage"]["compression"])

    # --- the client-facing report (French: it goes to I-SITE) ---
    fr = [
        "# Structures détectées hors liste",
        "",
        f"Instantané **{snapshot.name}** · fenêtre {CONFIG['window']['year_from']}–{CONFIG['window']['year_to']}.",
        "",
        f"OpenAlex rattache **{len(descendants)}** structures à l'Université de Lorraine "
        f"(`lineage:{ul_id}`). Le fichier de référence `Identifiants_UnivLorraine.xlsx` en nomme "
        f"**{int(descendants['in_client_list'].sum())}**. Les **{len(unmapped)}** structures ci-dessous "
        f"sont donc reconnues par OpenAlex comme faisant partie de l'université, mais ne figurent pas "
        f"dans le fichier : leurs publications entrent bien dans le périmètre, mais ne peuvent être "
        f"rattachées à aucun laboratoire et se retrouvent dans la catégorie « NO LAB ».",
        "",
        "**Décision attendue de l'équipe I-SITE** : pour chaque ligne, faut-il l'ajouter au fichier de "
        "référence (et à quel pôle), ou la laisser hors périmètre d'attribution ?",
        "",
        "| Structure | Type | Publications du corpus | Publications OpenAlex (tout temps) | ROR |",
        "|---|---|---|---|---|",
    ]
    for row in unmapped.itertuples():
        fr.append(f"| {row.display_name} | {row.type} | {row.corpus_works:,} | "
                  f"{row.works_count_alltime:,} | `{row.ror or '—'}` |")
    fr += [
        "",
        f"Total : **{int(unmapped['corpus_works'].sum()):,}** publications du corpus concernées.",
        "",
        "> Note technique : ces structures sont traitées comme *internes* dans le calcul des "
        "> partenariats (elles ne sont donc pas comptées comme des collaborations extérieures), mais "
        "> elles restent non attribuées côté laboratoires jusqu'à décision de l'équipe.",
    ]
    report = ROOT / CONFIG["paths"]["reports"] / "structures_hors_liste.md"
    report.write_text("\n".join(fr) + "\n", encoding="utf-8")

    Manifest(snapshot).record_step(
        "12_ul_descendants",
        filters=f"lineage:{ul_id}",
        select=SELECT,
        api_base=CONFIG["openalex"]["base_url"],
        api_calls=client.calls,
        counts={"descendants": len(descendants), "in_client_list": int(descendants["in_client_list"].sum()),
                "unmapped": len(unmapped), "unmapped_corpus_works": int(unmapped["corpus_works"].sum())},
        files=[out],
        notes="D20: unmapped UL structures are internal for partner maths, unattributed for lab views.",
    )
    lines = [
        f"- OpenAlex descendants of UL: **{len(descendants)}** · named in the client list: "
        f"**{int(descendants['in_client_list'].sum())}** · **unmapped: {len(unmapped)}**",
        f"- corpus works touched by unmapped structures: **{int(unmapped['corpus_works'].sum()):,}**",
        f"- client-facing report: `reports/structures_hors_liste.md` (French, for the workshop)",
    ]
    append_summary(snapshot, "12_ul_descendants", lines)
    print("\n".join(lines))
    print(f"\nwrote {out.name} and {report}  ({client.calls} API calls)")


if __name__ == "__main__":
    main()
