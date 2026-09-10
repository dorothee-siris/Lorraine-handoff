"""
Stream E golden-sample builder (D48).

Runs the REAL app once under Playwright, reads the numbers/colours it renders,
and writes `tests/golden/app_numbers_golden.csv`. This is the ONLY place that
needs a browser: `tests/test_app_numbers.py` re-verifies against this frozen
`displayed_value` column with a FRESH independent recompute every run, but it
does not need Playwright to do that -- only creating the golden sample does.

This is deliberately a standalone script, not a pytest file (no `test_` prefix),
mirroring `tests/ui/smoke.py`'s own pattern.

Usage:
    python tests/ui/build_golden.py

Output: tests/golden/app_numbers_golden.csv (overwritten) plus a printed summary.
ASCII-only console output (this box's console is cp1252).
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_app_numbers as tam  # noqa: E402  (tests/test_app_numbers.py -- shared recompute functions)
from _appserver import (  # noqa: E402
    VIEWPORT, free_port, start_app, stop_app, goto, select_option,
    big_number, metric_value, copy_grid_tsv, slice_fill_by_label,
)

GOLDEN_CSV = ROOT / "tests" / "golden" / "app_numbers_golden.csv"
SHOTS_LOG = ROOT / "reports" / "evals" / "build_golden_streamlit.log"

rows: list[dict] = []


def add(entity: str, page: str, metric: str, displayed: str, recomputed: str, note: str = "") -> None:
    rows.append({
        "entity": entity, "page": page, "metric": metric,
        "displayed_value": displayed, "recomputed_value": recomputed, "note": note,
    })


# ---------------------------------------------------------------------------
# entities
# ---------------------------------------------------------------------------
LABS = ["IJL", "CREAT", "NO LAB", "LORIA"]
HORS_LISTE_SEARCH = "CAPSID"
HORS_LISTE_OPENALEX_ID = "I4405259729"  # from tables/ul_descendants.parquet -- a lookup, see test_app_numbers.py docstring

SUBFIELDS = [
    ("3312", "Sociology and Political Science"),
    ("2505", "Materials Chemistry"),
    ("3600", "General Health Professions"),
    ("2204", "Biomedical Engineering"),
    ("1108", "Horticulture"),  # D53: zero computed-indicator works
]

# (lab, partner_openalex_id, partner_name_substring_for_verification, side)
PARTNERS = [
    ("IJL", "I1311948675", "Consumer Product Safety", "intl"),
    ("IJL", "I1294671590", "Centre National de la Recherche Scientifique", "fr"),
    ("LORIA", "I4210099593", "Computer Algorithms for Medicine", "intl"),
    ("LORIA", "I1294671590", "Centre National de la Recherche Scientifique", "fr"),
    ("CRAN", "I154526488", "Inserm", "fr"),
]

DOMAINS = [
    ("1", "Life Sciences"),
    ("2", "Social Sciences"),
    ("3", "Physical Sciences"),
    ("4", "Health Sciences"),
    ("0", "Unclassified"),
]


def main() -> int:
    port = free_port()
    proc = None
    try:
        print(f"starting streamlit on port {port} ...")
        proc = start_app(port, SHOTS_LOG)
        base = f"http://localhost:{port}"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport=VIEWPORT, permissions=["clipboard-read", "clipboard-write"])
            page = ctx.new_page()
            page.set_default_timeout(60_000)

            # -------------------------------------------------------- page 1: labs
            # NOTE: the "Lab_Overview"/"Thematic_Overview"/"Thematic_Drilldown" strings
            # below (in add()/print()) are internal bookkeeping LABELS matching the
            # existing golden CSV's "page" column and test_app_numbers.py's own filters
            # -- they are decoupled from the app's real URL slugs on purpose and are left
            # unchanged by the pass-5 page rename (P1 map). Only the goto() URL literals
            # (the page actually being visited) are updated to the new slugs.
            print("Lab_Overview: pubs_total + international KPI ...")
            goto(page, base, "/Laboratoires")
            for lab in LABS:
                select_option(page, "Sélectionner une structure", lab)
                total = big_number(page)
                add(lab, "Lab_Overview", "lab_pubs_total", total, "", "")
                intl = metric_value(page, "International")
                add(lab, "Lab_Overview", "lab_international_count", intl, "", "")
                print(f"  {lab}: pubs_total={total!r} international={intl!r}")

            print(f"Lab_Overview: {HORS_LISTE_SEARCH} (D56 hors-liste) ...")
            select_option(page, "Sélectionner une structure", HORS_LISTE_SEARCH)
            total = big_number(page)
            add("CAPSID", "Lab_Overview", "lab_pubs_total", total, "",
                f"hors-liste openalex_id={HORS_LISTE_OPENALEX_ID}")
            print(f"  CAPSID: pubs_total={total!r}")

            # D53: CREAT has exactly 1 thin-stratum work (verified against works_master
            # independently in test_app_numbers.py). Its "Works excluded" disclosure must
            # name that count -- never silently drop it to 0 or omit it.
            select_option(page, "Sélectionner une structure", "CREAT")
            body_creat = page.inner_text("body")
            # Page 1 carries TWO such captions: section 1's CORPUS-wide disclosure
            # (943 works, unrelated to CREAT) and section 2's PER-STRUCTURE one for
            # whichever structure is selected. Section 2 renders after section 1 in
            # the page, so the LAST regex match in document order is CREAT's own.
            excl_matches = re.findall(r"indicateurs de citation excluent\s+\**([\d  ,]+)\**\s+publication", body_creat)
            excl_val = excl_matches[-1].replace(",", "") if excl_matches else "MISSING"
            add("CREAT", "Lab_Overview", "d53_excluded_disclosure", excl_val, "", "")
            print(f"  CREAT 'Works excluded' disclosure displayed: {excl_val!r}")

            # -------------------------------------------------- page 1: partner tables
            print("Lab_Overview: partner co-pub counts (clipboard copy of st.dataframe) ...")
            # One structure-select + one full grid dump per DISTINCT lab (not per
            # partner pair): re-selecting an ALREADY-selected structure and
            # re-copying immediately afterwards was observed to occasionally hand
            # back the previous grid's stale clipboard content (a real, repeatable
            # timing effect against this exact canvas-based grid, not a one-off
            # flake) -- dumping every grid exactly once per lab sidesteps it.
            labs_needed = sorted({lab for lab, *_ in PARTNERS})
            grid_dumps: dict[str, list[str]] = {}
            for lab in labs_needed:
                select_option(page, "Sélectionner une structure", lab)
                page.wait_for_timeout(500)
                n_grids = page.locator('[data-testid="stDataFrame"]').count()
                grid_dumps[lab] = [copy_grid_tsv(page, gi) for gi in range(n_grids)]

            for lab, partner_id, needle, side in PARTNERS:
                dumps = grid_dumps[lab]
                tsv, found_idx = None, None
                for gi, candidate in enumerate(dumps):
                    if needle in candidate:
                        tsv, found_idx = candidate, gi
                        break
                if tsv is None:
                    dump_repr = "\n".join(f"  grid {gi}: {c[:120]!r}" for gi, c in enumerate(dumps))
                    raise RuntimeError(
                        f"{lab}/{side}: partner '{needle}' not found in any of {len(dumps)} grids.\n{dump_repr}"
                    )
                line = next(ln for ln in tsv.splitlines() if needle in ln)
                cell = line.split("\t")
                # column order per pages/1_*.py build_international/french_partners_table:
                # Partner, [Country,] Type, Co-pubs, % of UL copubs, Avg FWCI
                copubs_idx = 3 if side == "intl" else 2
                co_works = cell[copubs_idx].replace(",", "").strip()
                add(f"{lab}|{partner_id}", "Lab_Overview", "partner_co_works", co_works, "",
                    f"side={side} name={needle} grid_index={found_idx}")
                print(f"  {lab} x {needle} ({side}, grid {found_idx}): co-pubs={co_works!r}")

            # -------------------------------------------------------- page 4: subfields
            print("Thematic_Drilldown: subfield KPIs ...")
            goto(page, base, "/Exploration_thématique")
            select_option(page, "Choisir le niveau :", "📖 Sous-champ")
            for sid, name in SUBFIELDS:
                select_option(page, "Rechercher un sous-champ :", name)
                select_option(page, "Choisir l'élément :", name)
                pubs = metric_value(page, "Publications")
                fwci = metric_value(page, "FWCI médian (réf. France)")
                top10 = metric_value(page, "% Top 10 %")
                add(sid, "Thematic_Drilldown", "subfield_pubs_total", pubs, "", name)
                add(sid, "Thematic_Drilldown", "subfield_fwci_median", fwci, "", name)
                add(sid, "Thematic_Drilldown", "subfield_pct_top10_display", top10, "", name)
                print(f"  {name} ({sid}): pubs={pubs!r} fwci_median={fwci!r} top10={top10!r}")

            # -------------------------------------------------------- page 3: FWCI gradient
            print("Thematic_Overview: treemap FWCI-gradient fills ...")
            goto(page, base, "/Portefeuille_thématique")
            fills = slice_fill_by_label(page, plot_index=0)
            id_by_name = {name: did for did, name in DOMAINS}
            for did, name in DOMAINS:
                fill = fills.get(name)
                if fill is None:
                    raise RuntimeError(f"no treemap tile found for domain '{name}' -- {list(fills)[:10]}")
                add(did, "Thematic_Overview", "fwci_gradient_fill", fill, "", name)
                print(f"  {name} (domain {did}): fill={fill!r}")

            # -------------------------------------------------------- page 3: SDG panel
            print("Thematic_Overview: SDG panel text ...")
            body = page.inner_text("body")
            # FR wording since pass 5 (R12): fr_int uses narrow no-break spaces, fr_pct a decimal comma
            def _fr_num(x: str) -> str:
                return x.replace(" ", "").replace(" ", "").replace(" ", "").replace(",", "")
            m = re.search(r"([\d   ]+)\s+publications sur\s+([\d   ]+)\s+portent au moins un\s+objectif\s+\(([\d.,]+)\s*%\)", body)
            if not m:
                raise RuntimeError("could not find the SDG coverage sentence on Thematic_Overview")
            tagged, corpus_total, coverage_pct = m.groups()
            add("panel", "Thematic_Overview", "sdg_tagged_works", _fr_num(tagged), "", "")
            add("panel", "Thematic_Overview", "sdg_corpus_total", _fr_num(corpus_total), "", "")
            add("panel", "Thematic_Overview", "sdg_coverage_pct", coverage_pct.replace(",", "."), "", "")
            m2 = re.search(r"([\d   ]+)\s+attributions sur\s+([\d   ]+)\s+ont été\s+faites sur le seul titre", body)
            if not m2:
                raise RuntimeError("could not find the title-only SDG caption on Thematic_Overview")
            title_only, total_assign = m2.groups()
            add("panel", "Thematic_Overview", "sdg_title_only_count", _fr_num(title_only), "", "")
            add("panel", "Thematic_Overview", "sdg_total_assignments", _fr_num(total_assign), "", "")
            print(f"  tagged={_fr_num(tagged)} corpus_total={_fr_num(corpus_total)} coverage={coverage_pct.replace(chr(44), chr(46))}% title_only={_fr_num(title_only)}")

            browser.close()
    finally:
        stop_app(proc)

    # ---------------------------------------------------------------- recompute + write
    print()
    print("Recomputing every row independently from raw snapshot tables ...")
    for r in rows:
        r["recomputed_value"] = _recompute_for_row(r)

    GOLDEN_CSV.parent.mkdir(parents=True, exist_ok=True)
    with GOLDEN_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["entity", "page", "metric", "displayed_value",
                                                 "recomputed_value", "note"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {GOLDEN_CSV}")
    return 0


def _recompute_for_row(r: dict) -> str:
    """Best-effort provenance recompute at BUILD time (documentation only -- the
    actual regression check in test_app_numbers.py recomputes fresh at TEST time)."""
    metric, entity, note = r["metric"], r["entity"], r["note"]
    try:
        if metric == "lab_pubs_total":
            if entity == "CAPSID":
                return str(tam.recompute_hors_liste_pubs_total(note.split("openalex_id=")[-1].strip()))
            return str(tam.recompute_lab_pubs_total(entity))
        if metric == "lab_international_count":
            return str(tam.recompute_lab_international_count(entity))
        if metric == "subfield_pubs_total":
            return str(tam.recompute_subfield_pubs_total(entity))
        if metric == "subfield_fwci_median":
            v = tam.recompute_subfield_fwci_median(entity)
            return "n/a" if v is None else str(v)
        if metric == "d53_excluded_disclosure":
            return str(tam.recompute_creat_thin_stratum_count())
        if metric == "partner_co_works":
            lab, partner_id = entity.split("|")
            return str(tam.recompute_partner_co_works(lab, partner_id))
        if metric == "fwci_gradient_fill":
            v = tam.recompute_domain_fwci_median(entity)
            return "n/a" if v is None else str(v)
    except Exception as e:  # provenance only -- never block the golden write
        return f"<recompute failed: {e}>"
    return ""


if __name__ == "__main__":
    sys.exit(main())
