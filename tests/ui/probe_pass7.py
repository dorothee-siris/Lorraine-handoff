"""
tests/ui/probe_pass7.py -- S-INSP Deliverable 3 (pass 7a inspection battery).

Recomputes 8 rendered numbers straight from `Streamlit/data/*.parquet` and compares
them, EXACT after FR formatting, against the RUNNING app's own rendered text (DOM /
`st.metric` / clipboard idioms from `tests/ui/_appserver.py`, plus a Plotly
`customdata`/`text` reader for chart-embedded values). A build stream's own green
self-report is not evidence a number is right (INSPECTION_PLAYBOOK family 1) -- this
is the independent recompute half of the S-INSP battery, never importing a pipeline
builder (same house style as `tests/test_pass7_data.py`'s own golden checks).

The 8 numbers (brief's own list):
  1. hub row co-pubs for CNRS                    (page 8, ptn_summary.co_works_full)
  2. hub KPI "Partenaires (>=10 co-publications)" (page 8, ptn_summary count)
  3. page-9 phares KPI                            (page 9, ptn_summary.n_phares)
  4. one balance-bar joint value                  (page 9, ptn_fields.co_works)
  5. one reciprocity point's two shares           (page 8, ptn_summary.share_ul/share_p)
  6. one plane bubble's co-pubs                   (page 9, ptn_topics.co_works)
  7. page-10 DE co-pubs                           (page 10, geo_countries.co_works)
  8. page-2 one SDG bar                           (page 2, sdg_lab_methods.share_lab_corpus_siris)

Usage: python tests/ui/probe_pass7.py
Exit 0 = all 8 numbers match. Results also written to
progress/p7_proofs/INSP/probe_pass7_results.json. Output is ASCII-only (cp1252 console).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "ui"))
sys.path.insert(0, str(ROOT / "Streamlit"))

import _appserver as srv  # noqa: E402
from lib.helpers import fr_int, fr_pct  # noqa: E402

DATA = ROOT / "Streamlit" / "data"
OUT_DIR = ROOT / "progress" / "p7_proofs" / "INSP"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CNRS = "I1294671590"

results: list[dict] = []


# Only digits + the app's own FR thousand-separators (narrow no-break U+202F, no-break
# U+00A0) -- deliberately EXCLUDES plain \s (which also matches the TAB between TSV
# fields and would merge two adjacent cells into one bogus "number", e.g. "2241<TAB>8"
# from "...2241<TAB>8.3<TAB>..."). Bug found live: the original \d[\d\s ]* pattern
# mismatched #7 even though "2241" was plainly present in the row.
NUM_RX = re.compile("\\d[\\d  ]*")


def _clean_num(s: str) -> str:
    return s.replace(" ", "").replace(" ", "").replace(" ", "")


def record(id_, desc, recomputed, rendered, ok, detail="") -> None:
    results.append({"id": id_, "description": desc, "recomputed": str(recomputed),
                     "rendered": str(rendered), "match": bool(ok), "detail": detail})
    status = "PASS" if ok else "FAIL"
    line = f"[{status}] #{id_} {desc}: recomputed={recomputed!r} rendered={rendered!r} {detail}"
    print(line.encode("ascii", "replace").decode())


def parse_hover(html: str):
    """(entity, {label: value}) from a `hover_lines()` string:
    '<b>Entity</b><br><b>Label</b> : Value<br>...' (lib/hover.py's own contract)."""
    segs = html.split("<br>")
    entity = re.sub(r"</?b>", "", segs[0]).strip() if segs else ""
    fields = {}
    for seg in segs[1:]:
        m = re.match(r"<b>([^<]*)</b>\s*:\s*(.*)", seg.strip())
        if m:
            fields[m.group(1).strip()] = m.group(2).strip()
    return entity, fields


def chart_info(page):
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('.js-plotly-plot')).map((gd, i) => {
            const lay = gd.layout || {};
            const xt = (lay.xaxis && lay.xaxis.title && (lay.xaxis.title.text ?? lay.xaxis.title)) || '';
            const y2 = lay.yaxis2 || null;
            const d0 = (gd.data && gd.data[0]) || {};
            const firstY = Array.isArray(d0.y) && d0.y.length ? String(d0.y[0]) : '';
            return {index: i, xaxis_title: String(xt), first_y: firstY, has_y2: !!(y2 && y2.ticktext)};
        })"""
    )


def find_chart(info, *, xaxis_title=None, first_y_prefix=None, has_y2=None):
    for c in info:
        if xaxis_title is not None and c["xaxis_title"] != xaxis_title:
            continue
        if first_y_prefix is not None and not c["first_y"].startswith(first_y_prefix):
            continue
        if has_y2 is not None and bool(c["has_y2"]) != has_y2:
            continue
        return c["index"]
    return -1


def all_customdata(page, chart_index: int):
    return page.evaluate(
        "(i) => document.querySelectorAll('.js-plotly-plot')[i].data.map(t => t.customdata || [])",
        chart_index,
    )


def gutter_text_row0(page, chart_index: int):
    """First row's text from the gutter PHANTOM trace specifically -- identified by
    `hoverinfo === 'skip'` (`_add_gutter_column`'s own marker, charts.py), not just
    "any trace with a text array": `balance_bars` draws 3 VISIBLE segments that may
    ALSO carry their own text/value labels, and a naive "first non-null text" grab
    can silently return one of those instead (live bug found: chart#2 returned
    47419 -- much larger than any single field's co_works, i.e. clearly the wrong
    trace -- for what should have been a 2,721-row gutter value)."""
    arrs = page.evaluate(
        "(i) => document.querySelectorAll('.js-plotly-plot')[i].data"
        ".map(t => (t.hoverinfo === 'skip' && t.text) ? t.text : null)",
        chart_index,
    )
    for a in arrs:
        if a:
            return a[0]
    return None


def bar_text0(page, chart_index: int):
    return page.evaluate(
        "(i) => { const gd = document.querySelectorAll('.js-plotly-plot')[i];"
        " return gd.data[0].text ? gd.data[0].text[0] : null; }",
        chart_index,
    )


def main() -> int:
    port = srv.free_port()
    proc = None
    try:
        proc = srv.start_app(port, OUT_DIR / "streamlit.log")
        base = f"http://localhost:{port}"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1200},
                                     permissions=["clipboard-read", "clipboard-write"])
            page.set_default_timeout(60_000)

            # =================== Page 8: Collaborations ===================
            srv.goto(page, base, "/Collaborations")
            ptn_summary = pd.read_parquet(DATA / "ptn_summary.parquet")
            cnrs_row = ptn_summary[(ptn_summary["partner_id"] == CNRS)
                                    & (ptn_summary["subset_id"] == "all")
                                    & (ptn_summary["conf_state"] == "all")].iloc[0]

            # #1 hub row co-pubs for CNRS (default sort = co-pubs desc; CNRS is the
            # largest partner in the corpus, so should already be row 0 -- explicit
            # search fallback if not, never assumed).
            expected_1 = fr_int(int(cnrs_row["co_works_full"]))
            tsv = srv.copy_grid_tsv(page, grid_index=0)
            lines = [ln for ln in tsv.splitlines() if ln.strip()]
            row0 = lines[0] if lines else ""
            if "CNRS" not in row0 and "Recherche Scientifique" not in row0:
                box = page.locator('[data-testid="stTextInput"]').filter(has_text="Rechercher").first
                box.locator("input").first.fill("CNRS")
                page.wait_for_timeout(700)
                page.keyboard.press("Enter")
                srv.settle(page)
                tsv = srv.copy_grid_tsv(page, grid_index=0)
                lines = [ln for ln in tsv.splitlines() if ln.strip()]
                row0 = lines[0] if lines else ""
            nums1 = [_clean_num(d) for d in NUM_RX.findall(row0)]
            target1 = str(int(cnrs_row["co_works_full"]))
            got_1 = target1 if target1 in nums1 else (row0[:150] or "(no row found)")
            record(1, "hub row co-pubs for CNRS", expected_1, got_1, target1 in nums1)

            # #2 hub KPI partners >= 10
            n_ge10 = int((ptn_summary[(ptn_summary["subset_id"] == "all")
                                       & (ptn_summary["conf_state"] == "all")]["co_works_full"] >= 10).sum())
            expected_2 = fr_int(n_ge10)
            got_2 = srv.metric_value(page, "Partenaires (≥10") or srv.metric_value(page, "Partenaires")
            record(2, "hub KPI partners >=10", expected_2, got_2, got_2.strip() == expected_2.strip())

            # #5 one reciprocity point's two shares (CNRS) -- found by its ENTITY name
            # in the chart's own customdata (never by index; point order is data-sorted).
            info8 = chart_info(page)
            idx8 = find_chart(info8, xaxis_title="Part du portefeuille propre de l'UL")
            share_ul_exp = fr_pct(float(cnrs_row["share_ul"]) * 100)
            share_p_exp = fr_pct(float(cnrs_row["share_p"]) * 100)
            match5, detail5 = False, "chart not found"
            if idx8 >= 0:
                cds = all_customdata(page, idx8)
                hay = "|".join(str(x) for arr in cds for x in (arr or []))
                match5 = (share_ul_exp in hay) and (share_p_exp in hay)
                detail5 = f"chart#{idx8}: looked for {share_ul_exp!r} and {share_p_exp!r}"
            record(5, "reciprocity point shares (CNRS share_ul/share_p)",
                   f"{share_ul_exp} / {share_p_exp}", "both found" if match5 else "not found", match5, detail5)

            # =================== Page 9: Zoom partenaire (CNRS) ===================
            srv.goto(page, base, f"/Zoom_partenaire?partner_id={CNRS}")

            # #3 phares KPI
            expected_3 = "—" if pd.isna(cnrs_row.get("n_phares")) else fr_int(int(cnrs_row["n_phares"]))
            got_3 = srv.metric_value(page, "Publications phares")
            record(3, "page-9 phares KPI (CNRS)", expected_3, got_3, got_3.strip() == expected_3.strip())

            # #4 one balance-bar joint value (field level, volume mode -- the page's
            # default state -- row 0 = the CNRS field with the MAX co_works; the page's
            # own _balance_frame() does not drop/reorder field-level rows beyond that
            # single sort, confirmed by reading Streamlit/pages/9_....py verbatim).
            ptn_fields = pd.read_parquet(DATA / "ptn_fields.parquet")
            f = ptn_fields[(ptn_fields["partner_id"] == CNRS) & (ptn_fields["node_level"] == "field")
                           & (ptn_fields["conf_state"] == "all")]
            if "subset_id" in ptn_fields.columns:
                f = f[f["subset_id"] == "all"]
            top_field = f.sort_values("co_works", ascending=False).iloc[0]
            expected_4 = fr_int(int(top_field["co_works"]))
            info9 = chart_info(page)
            idx_bb = find_chart(info9, has_y2=True)
            gutter0 = gutter_text_row0(page, idx_bb) if idx_bb >= 0 else None
            match4 = bool(gutter0) and _clean_num(str(gutter0)) == str(int(top_field["co_works"]))
            record(4, "balance-bar joint value (CNRS, champ, volume, row0)", expected_4, gutter0, match4,
                   f"chart#{idx_bb}, field_id={int(top_field['node_id'])}")

            # #6 one plane bubble's co-pubs -- take whichever topic is point 0 of the
            # impact plane and independently recompute ITS OWN co_works, rather than
            # assuming which topic sorts first (mode/N-slider state dependent).
            idx_pl = find_chart(info9, xaxis_title="Co-publications de la relation")
            match6, detail6, expected_6, got_6 = False, "chart not found", None, None
            if idx_pl >= 0:
                cds9 = all_customdata(page, idx_pl)
                flat9 = [x for arr in cds9 for x in (arr or [])]
                if flat9:
                    entity, _fields = parse_hover(str(flat9[0]))
                    all_topics = pd.read_parquet(DATA / "all_topics.parquet", columns=["topic_id", "topic_name"])
                    hit = all_topics[all_topics["topic_name"] == entity]
                    if len(hit):
                        tid = hit.iloc[0]["topic_id"]
                        pt = pd.read_parquet(DATA / "ptn_topics.parquet")
                        pt_cnrs = pt[(pt["partner_id"] == CNRS) & (pt["conf_state"] == "all") & (pt["topic_id"] == tid)]
                        recomputed_cw = int(pt_cnrs["co_works"].sum())
                        expected_6 = fr_int(recomputed_cw)
                        got_6 = str(flat9[0])[:250]
                        match6 = expected_6 in str(flat9[0])
                        detail6 = f"topic={entity!r} tid={tid}"
                    else:
                        detail6 = f"topic name {entity!r} not found in all_topics.parquet"
            record(6, "plane bubble co-pubs (point 0, CNRS)", expected_6, got_6, match6, detail6)

            # =================== Page 10: Geographie ===================
            srv.goto(page, base, "/Géographie")
            geo = pd.read_parquet(DATA / "geo_countries.parquet")
            de = geo[geo["country_code"] == "DE"]
            if "conf_state" in geo.columns:
                de = de[de["conf_state"] == "all"]
            if "subset_id" in geo.columns:
                de = de[de["subset_id"] == "all"]
            de_total = int(de["co_works"].sum())
            expected_7 = fr_int(de_total)
            tsv10 = srv.copy_grid_tsv(page, grid_index=0)
            de_line = next((ln for ln in tsv10.splitlines() if "Allemagne" in ln), "")
            nums10 = [_clean_num(d) for d in NUM_RX.findall(de_line)]
            got_7 = str(de_total) if str(de_total) in nums10 else (de_line[:150] or "(Allemagne row not found)")
            record(7, "page-10 DE co-pubs", expected_7, got_7, str(de_total) in nums10, f"line={de_line[:150]!r}")

            # =================== Page 2: Laboratoires (SDG) ===================
            sdg = pd.read_parquet(DATA / "sdg_lab_methods.parquet")
            counts_lab = (sdg[(sdg["conf_state"] == "all") & sdg["share_lab_corpus_siris"].notna()]
                          .groupby("lab").size().sort_values(ascending=False))
            sdg_lab = str(counts_lab.index[0]) if len(counts_lab) else None
            expected_8, got_8, match8, detail8 = None, None, False, "no SDG-rich lab found"
            if sdg_lab:
                srv.goto(page, base, "/Laboratoires")
                srv.select_option(page, "Sélectionner une structure", sdg_lab)
                row_lab = sdg[(sdg["lab"] == sdg_lab) & (sdg["conf_state"] == "all")
                              & sdg["share_lab_corpus_siris"].notna()].sort_values("sdg").iloc[0]
                expected_8 = fr_pct(float(row_lab["share_lab_corpus_siris"]) * 100)
                info2 = chart_info(page)
                idx2 = find_chart(info2, first_y_prefix="ODD ")
                got_8 = bar_text0(page, idx2) if idx2 >= 0 else None
                match8 = (got_8 or "").strip() == expected_8.strip()
                detail8 = f"lab={sdg_lab}, goal={int(row_lab['sdg'])}, chart_idx={idx2}"
            record(8, "page-2 one SDG bar", expected_8, got_8, match8, detail8)

            browser.close()
    finally:
        srv.stop_app(proc)

    out_path = OUT_DIR / "probe_pass7_results.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    n_pass = sum(1 for r in results if r["match"])
    print()
    print(f"PROBE: {n_pass}/{len(results)} numbers matched. Results -> {out_path.relative_to(ROOT)}".encode("ascii", "replace").decode())
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
