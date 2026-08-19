"""44_build_thematic.py -- Thematic Overview and Drilldown, rebuilt on the OpenAlex taxonomy.

This is what replaces the topic model (D9). v1's thematic views were driven by TM dimensions
("Classic TM", "Research Topic", plus the Objective/Method/Impact dimensions that never became
interpretable) and covered only 79% of works by construction. The OpenAlex taxonomy --
domain -> field -> subfield -> topic -- covers every topiced work, is documented publicly, and
refreshes with the data, which is the whole point of v2: the client can re-run it.

EXTENDED for the app-sprint (Stream B) to also emit the DEPLOYED shape `thematic_overview.parquet`,
re-keyed from `(level, entity=NAME)` to `(level, id)` with `name`, `parent_id`, `parent_name`,
`domain_id` -- pages 3 and 4 cast ids to int and walk the parent chain, which a name string cannot
support. Built directly from `works_master`'s own `primary_*_id`/`primary_*_name` columns (grouping
on the ID, not resolving a name back to an id), which is simpler and safer than a name-based join.

Four tables now, not three:
  * `ul_thematic_overview` / `ul_thematic_drilldown` / `ul_thematic_by_year` -- unchanged internal
    tables (name-keyed), kept for any other consumer;
  * `thematic_overview` -- the DEPLOYED, id-keyed shape pages 3/4 actually read.

Usage: python pipeline/44_build_thematic.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402
import lib46_momentum as mom  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)
LEVELS = [("domain", "primary_domain_name"), ("field", "primary_field_name"),
          ("subfield", "primary_subfield_name"), ("topic", "primary_topic_name")]
ID_LEVELS = [("domain", "primary_domain_id"), ("field", "primary_field_id"),
             ("subfield", "primary_subfield_id"), ("topic", "primary_topic_id")]
UNCLASSIFIED_ID = "0"
UNCLASSIFIED_NAME = "Unclassified"
CENTILES = [0, 10, 25, 50, 75, 90, 100]
SDG_VARIANT_MAP = {"b_siris": "B_siris", "c_openalex": "C_openalex", "off": None}


def aggregate(block: pd.DataFrame) -> dict:
    computed = block[block["indicator_status"] == "computed"] if "indicator_status" in block else block.iloc[0:0]
    return {
        "works": len(block),
        "citations": int(block["cited_by_count"].fillna(0).sum()),
        "works_with_indicators": len(computed),
        "FWCI_FR_median": round(float(computed["FWCI_FR"].median()), 4) if len(computed) else None,
        "PPtop10_FR_share": round(float(computed["PPtop10_FR"].astype(float).mean()), 4) if len(computed) else None,
        "in_isite_works": int(block["In_ISITE"].sum()),
        "oa_share": round(float(block["is_oa"].astype("boolean").mean()), 4) if block["is_oa"].notna().any() else None,
        "international_share": round(float(block["Is_international"].mean()), 4),
        "conference_share": round(float(block["is_conference"].mean()), 4) if "is_conference" in block else None,
        "abstract_coverage": round(float(block["abstract"].notna().mean()), 4),
        "first_year": int(block["publication_year"].min()),
        "last_year": int(block["publication_year"].max()),
    }


def pipe_years(block: pd.DataFrame, years: list[int]) -> str:
    counts = block["publication_year"].value_counts()
    return "|".join(f"{y}:{int(counts.get(y, 0))}" for y in years)


def boxplot_pipe(values: np.ndarray) -> str:
    if len(values) == 0:
        return "|".join("0.00" for _ in CENTILES)
    return "|".join(f"{c:.2f}" for c in np.percentile(values, CENTILES))


def cagr(first: float, last: float, n_periods: int) -> float | None:
    if not first or first <= 0 or n_periods <= 0:
        return None
    return round((last / first) ** (1 / n_periods) - 1, 4)


def build_deployed_overview(works: pd.DataFrame, all_topics: pd.DataFrame, sdg_col: str | None) -> pd.DataFrame:
    at = all_topics.assign(
        domain_id=all_topics["domain_id"].astype(str), field_id=all_topics["field_id"].astype(str),
        subfield_id=all_topics["subfield_id"].astype(str),
    )
    field_to_domain = at.drop_duplicates("field_id").set_index("field_id")[["domain_id", "domain_name"]]
    subfield_to_field = at.drop_duplicates("subfield_id").set_index("subfield_id")[["field_id", "field_name"]]
    topic_to_subfield = at.drop_duplicates("topic_id").set_index("topic_id")[["subfield_id", "subfield_name"]]
    domain_name_of = at.drop_duplicates("domain_id").set_index("domain_id")["domain_name"].to_dict()

    years = list(range(CONFIG["window"]["year_from"], CONFIG["window"]["year_to"] + 1))
    corpus_total = len(works)

    if sdg_col:
        sdg = pd.read_parquet(Path(all_topics.attrs.get("_snapshot_tables")) / "sdg_three_way.parquet")
        sdg_flag = sdg.set_index("work_id")[sdg_col].notna()
    else:
        sdg_flag = pd.Series(dtype=bool)

    rows = []
    for level, id_col in ID_LEVELS:
        name_col = dict(LEVELS)[level]
        scoped = works.assign(**{id_col: works[id_col].fillna(UNCLASSIFIED_ID),
                                  name_col: works[name_col].fillna(UNCLASSIFIED_NAME)})
        for entity_id, block in scoped.groupby(id_col, observed=True):
            name = block[name_col].iloc[0]
            if entity_id == UNCLASSIFIED_ID:
                parent_id, parent_name, domain_id = "", "", UNCLASSIFIED_ID
            elif level == "domain":
                parent_id, parent_name, domain_id = "", "", entity_id
            elif level == "field":
                p = field_to_domain.loc[entity_id]
                parent_id, parent_name, domain_id = p["domain_id"], p["domain_name"], p["domain_id"]
            elif level == "subfield":
                p = subfield_to_field.loc[entity_id]
                grandp = field_to_domain.loc[p["field_id"]]
                parent_id, parent_name, domain_id = p["field_id"], p["field_name"], grandp["domain_id"]
            else:  # topic
                p = topic_to_subfield.loc[entity_id]
                grandp = subfield_to_field.loc[p["subfield_id"]]
                greatgrandp = field_to_domain.loc[grandp["field_id"]]
                parent_id, parent_name, domain_id = p["subfield_id"], p["subfield_name"], greatgrandp["domain_id"]

            computed = block[block["indicator_status"] == "computed"] if "indicator_status" in block else block.iloc[0:0]
            year_counts = block["publication_year"].value_counts()
            first_val, last_val = int(year_counts.get(years[0], 0)), int(year_counts.get(years[-1], 0))
            pct_sdg = float(sdg_flag.reindex(block["work_id"]).fillna(False).mean()) if len(sdg_flag) else None
            # pass 6 (#18, momentum family -- see build_deployed_overview's docstring note below):
            # two-window counts feeding the SAME frozen recentred-ratio method every other momentum
            # column in this app already uses, applied via lib46_momentum.cell_delta() after the
            # loop (needs the shared field-level d1/d2/med reference, computed once).
            mom_c1 = sum(int(year_counts.get(y, 0)) for y in mom.W1_YEARS)
            mom_c2 = sum(int(year_counts.get(y, 0)) for y in mom.W2_YEARS)

            rows.append({
                "level": level, "id": str(entity_id), "name": name,
                "parent_id": str(parent_id) if parent_id != "" else "",
                "parent_name": parent_name, "domain_id": str(domain_id),
                "pubs_total": len(block),
                "pubs_pct_of_ul": round(len(block) / corpus_total, 6) if corpus_total else 0.0,
                "pubs_per_year": pipe_years(block, years),
                "pct_isite": round(float(block["In_ISITE"].mean()), 4) if len(block) else 0.0,
                "pct_top10": round(float(computed["PPtop10_FR"].astype(float).mean()), 4) if len(computed) else None,
                "pct_top1": round(float(computed["PPtop1_FR"].astype(float).mean()), 4) if len(computed) else None,
                "pct_international": round(float(block["Is_international"].mean()), 4) if len(block) else 0.0,
                "pct_company": round(float(block["Is_company"].mean()), 4) if len(block) else 0.0,
                "pct_sdg": round(pct_sdg, 4) if pct_sdg is not None else None,
                "cagr_2019_2023": cagr(first_val, last_val, len(years) - 1),
                "fwci_median": round(float(computed["FWCI_FR"].median()), 4) if len(computed) else None,
                "fwci_mean": round(float(computed["FWCI_FR"].mean()), 4) if len(computed) else None,
                "fwci_boxplot": boxplot_pipe(computed["FWCI_FR"].dropna().to_numpy()),
                "_mom_c1": mom_c1, "_mom_c2": mom_c2,
            })
    frame = pd.DataFrame(rows)

    # --- pass 6 (#18): momentum at every taxonomy grain, THE frozen recentred-ratio + two-
    # proportion-test method (lib46_momentum.py), never a new one. Reference d1/d2/med computed
    # ONCE at the FIELD level (26 populous nodes -- the same mid-level grain 47_build_thematic_ext.
    # py's own LQ/specialisation index already anchors on) and reused for every level via
    # cell_delta(), exactly the "one market-drift correction per run, borrowed by finer grains"
    # discipline ptn_fields/ptn_topics already apply to the partner-grain reference. d1/d2 are
    # level-invariant (both sum over the WHOLE corpus's distinct works in each window, not per
    # node), so only `med` actually varies by the chosen reference level.
    ref = mom.corpus_level_reference(works, "primary_field_id")
    print(f"  momentum reference (field-level, {mom.W1_YEARS} vs {mom.W2_YEARS}): "
          f"d1={ref['d1']:,} d2={ref['d2']:,} med={ref['med']:.4f} eligible_n={ref['eligible_n']}")
    rr, pv, elig = mom.cell_delta(frame["_mom_c1"], frame["_mom_c2"], ref["d1"], ref["d2"], ref["med"])
    frame["mom_class"] = mom.classify(rr, pv)
    frame["mom_p_value"] = pv
    frame["mom_w1_share"] = (frame["_mom_c1"] / ref["d1"]) if ref["d1"] else np.nan
    frame["mom_w2_share"] = (frame["_mom_c2"] / ref["d2"]) if ref["d2"] else np.nan
    frame["mom_eligible_flag"] = elig.astype(bool)
    frame = frame.drop(columns=["_mom_c1", "_mom_c2"])
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    works = pd.read_parquet(tables / "works_master.parquet")
    all_topics = pd.read_parquet(tables / "all_topics.parquet")
    print(f"snapshot {snapshot.name}: {len(works):,} works")
    untopiced = works["primary_subfield_name"].isna().sum()
    print(f"  works with no primary topic: {untopiced:,} ({untopiced/len(works):.1%}) — reported as "
          f"'(sans thematique)' rather than dropped")

    # --- overview, one row per level x entity (NAME-keyed, internal use) --------------------
    overview_rows = []
    for level, column in LEVELS:
        labelled = works.assign(**{column: works[column].fillna("(sans thematique)")})
        for entity, block in labelled.groupby(column, observed=True):
            overview_rows.append({"level": level, "entity": entity, **aggregate(block)})
    overview = pd.DataFrame(overview_rows).sort_values(["level", "works"], ascending=[True, False])

    year_rows = []
    for level, column in LEVELS[:3]:  # domain/field/subfield; topic-by-year is too sparse to be useful
        labelled = works.assign(**{column: works[column].fillna("(sans thematique)")})
        counts = labelled.groupby([column, "publication_year"], observed=True).size().reset_index(name="works")
        counts.insert(0, "level", level)
        year_rows.append(counts.rename(columns={column: "entity"}))
    per_year = pd.concat(year_rows, ignore_index=True)

    exploded = works.assign(lab=works["Labs"].str.split(" | ", regex=False)).explode("lab")
    exploded["primary_subfield_name"] = exploded["primary_subfield_name"].fillna("(sans thematique)")
    drill_rows = []
    for (subfield, lab), block in exploded.groupby(["primary_subfield_name", "lab"], observed=True):
        if len(block) < 1:
            continue
        drill_rows.append({"subfield": subfield, "lab": lab, **aggregate(block)})
    drilldown = pd.DataFrame(drill_rows).sort_values("works", ascending=False)

    # --- deployed shape: id-keyed, with parent chain (pages 3/4) -----------------------------
    app_cfg = CONFIG.get("app") or {}
    sdg_variant = app_cfg.get("sdg_variant", "b_siris")
    sdg_col = SDG_VARIANT_MAP.get(sdg_variant, "B_siris")
    all_topics.attrs["_snapshot_tables"] = str(tables)
    deployed = build_deployed_overview(works, all_topics, sdg_col)

    for level, _ in LEVELS:
        total = int(deployed.loc[deployed["level"] == level, "pubs_total"].sum())
        assert total == len(works), f"deployed {level} rows sum to {total:,}, expected {len(works):,}"
        assert deployed.loc[deployed["level"] == level, "id"].is_unique, f"duplicate ids at level {level}"

    out_overview = tables / "ul_thematic_overview.parquet"
    out_year = tables / "ul_thematic_by_year.parquet"
    out_drill = tables / "ul_thematic_drilldown.parquet"
    out_deployed = tables / "thematic_overview.parquet"
    for frame, path in ((overview, out_overview), (per_year, out_year), (drilldown, out_drill),
                        (deployed, out_deployed)):
        frame.to_parquet(path, index=False, compression=CONFIG["storage"]["compression"])

    for level, _ in LEVELS:
        total = int(overview.loc[overview["level"] == level, "works"].sum())
        assert total == len(works), f"{level} rows sum to {total:,}, expected {len(works):,}"

    counts = {level: int((overview["level"] == level).sum()) for level, _ in LEVELS}
    deployed_counts = {level: int((deployed["level"] == level).sum()) for level, _ in LEVELS}
    lines = [
        f"- thematic entities (name-keyed): " + " · ".join(f"{k} **{v:,}**" for k, v in counts.items()),
        f"- deployed (id-keyed): " + " · ".join(f"{k} **{v:,}**" for k, v in deployed_counts.items())
        + f" -> **{len(deployed):,}** total rows",
        f"- every level sums to the full corpus ({len(works):,}) — the primary topic is single-valued, "
        f"so no double counting",
        f"- works with no topic: **{untopiced:,}** ({untopiced/len(works):.1%}), surfaced as "
        f"'{UNCLASSIFIED_NAME}' (id '{UNCLASSIFIED_ID}') — v1's topic model covered only 79.0% by "
        f"construction, and the remaining 21% was simply absent from the thematic views",
        f"- drilldown rows (subfield x lab): **{len(drilldown):,}**",
        f"- pct_sdg baked at build time from config app.sdg_variant='{sdg_variant}' (column "
        f"{sdg_col}); the page-3 SDG PANEL itself reads sdg_three_way.parquet directly and switches "
        f"live (D51) — this aggregate column is a convenience, not the switch",
        f"- pass 6 (#18): mom_class/mom_p_value/mom_w1_share/mom_w2_share/mom_eligible_flag added "
        f"at every taxonomy level (frozen momentum family, field-level d1/d2/med reference); "
        f"cagr_2019_2023 kept computing (display-retired per contract, hidden-by-default)",
        "",
        "| Domain | Works | FWCI_FR median | PPtop10 share |",
        "|---|---|---|---|",
    ]
    for row in overview[overview["level"] == "domain"].itertuples():
        lines.append(f"| {row.entity} | {row.works:,} | "
                     f"{'' if pd.isna(row.FWCI_FR_median) else f'{row.FWCI_FR_median:.2f}'} | "
                     f"{'' if pd.isna(row.PPtop10_FR_share) else f'{row.PPtop10_FR_share:.1%}'} |")
    lines += ["", "| Top 10 subfields | Works |", "|---|---|"]
    for row in overview[overview["level"] == "subfield"].head(10).itertuples():
        lines.append(f"| {row.entity} | {row.works:,} |")

    report = ROOT / CONFIG["paths"]["reports"] / "ul_thematic.md"
    report.write_text("# Thematic views on the OpenAlex taxonomy (replacing the topic model)\n\n"
                      + "\n".join(lines) + "\n", encoding="utf-8")
    Manifest(snapshot).record_step(
        "44_build_thematic",
        counts={**counts, "drilldown_rows": len(drilldown), "untopiced_works": int(untopiced),
                "deployed_rows": len(deployed), **{f"deployed_{k}": v for k, v in deployed_counts.items()}},
        files=[out_overview, out_year, out_drill, out_deployed],
        params={"levels": [level for level, _ in LEVELS], "topic_model_used": False,
                "sdg_variant_baked": sdg_variant},
        notes="D9: thematic views rebuilt on domain/field/subfield/topic; zero TM dependency. "
              "Deployed shape re-keyed to (level, id) with parent chain per Stream A contract finding #10.",
    )
    append_summary(snapshot, "44_build_thematic", lines[:6])
    print("\n".join(lines))
    print(f"\nwrote {out_overview.name}, {out_year.name}, {out_drill.name}, {out_deployed.name} and {report}")


if __name__ == "__main__":
    main()
