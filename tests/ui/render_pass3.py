"""
Render-verification gate (Stream V, chain pass 3, Assembly Line) -- covers the WHOLE app:
Home + all 11 built pages, at 1920/1280/390 px, per SIRIS house rules + VIZ_SPEC.md S3#6
("Render-verify (Playwright) at 1920/1280/390 px per page before GATE acceptance:
scrollWidth <= innerWidth, labels uncollided at 390 px").

Deliberately separate from `tests/ui/smoke.py` (Stream C's file, outside this stream's scope
fence -- create ONLY this file + reports/evals/pass3_render/ screenshots + progress/V_render.md).
Reuses `tests/ui/_appserver.py` (server lifecycle + settle/goto, already shared infra) and
copy-adapts the chart-marks probe P3's own `pass3_render_check.py` and Stream C's `smoke.py`
already proved live against this exact app build -- same idiom as `_appserver.py`'s own
docstring ("fixes are repeated rather than imported from a file this stream must not modify"),
except `lib.controls` constants ARE imported directly (read-only, no modification, avoids
copy-drift on the two disclosure-strip strings).

Two reference entities, chosen from THIS pass's own probing (not guessed) and already used as
reference points by earlier streams:
  PARTNER_ID = I4210100260  Centre Hospitalier Regional et Universitaire de Nancy (1,835
               co-works) -- P2_partner_pages.md's own acceptance reference. Drill path
               field[4]="Health Professions" -> subfield[0]="General Health Professions"
               -> topic[0]="Health, Medicine and Society" (T13099) is FLAGGED
               (artifact_flag=True in ptn_topics), calibrated live so the dagger check has a
               guaranteed-visible row, not a hopeful guess.
  AUTHOR_ID  = A5042884495  Laurent Peyrin-Biroulet (454 works, 427 indicator-eligible >=30
               floor) -- P4_author_pages.md's own acceptance reference.

Row-click calibration (glide-data-grid canvas, no accessible-DOM click path -- the a11y <tr>
mirror exists but is zero-size/non-actionable, confirmed by probing): hover then click at
grid-relative (x=10, y=50+36*row_index) reliably fires `on_select="rerun"` for row `row_index`
(header ~36px + row ~36px, calibrated empirically against this exact build, not copied from
an uncommitted prior script).

Usage: python tests/ui/render_pass3.py
Screenshots -> reports/evals/pass3_render/. Output is ASCII-only (cp1252 console).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "ui"))
sys.path.insert(0, str(ROOT / "Streamlit"))

import _appserver as srv  # noqa: E402
from lib.controls import ARTIFACT_BANNER_TEXT_FR, SHIPS_V2_STRIP_TEXT_FR, ARTIFACT_TOGGLE_LABEL  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

SHOTS = ROOT / "reports" / "evals" / "pass3_render"
SHOTS.mkdir(parents=True, exist_ok=True)

WIDTHS = [1920, 1280, 390]
BASE_HEIGHT = 1100

PARTNER_ID = "I4210100260"
AUTHOR_ID = "A5042884495"

# page 13's own idiom (page-local constant, not exported by lib.controls -- verbatim
# substring copied read-only from Streamlit/pages/13_..Identifiants_et_couverture.py for
# detection only).
EXEMPT_CAPTION_FRAGMENT = "la couverture d'identifiants porte sur les personnes"
BANNER_FRAGMENT = "concentrés en SHS francophone"          # tail of ARTIFACT_BANNER_TEXT_FR
STRIP_FRAGMENT = "s'applique aux nouvelles vues"                 # mid of SHIPS_V2_STRIP_TEXT_FR
assert BANNER_FRAGMENT in ARTIFACT_BANNER_TEXT_FR
assert STRIP_FRAGMENT in SHIPS_V2_STRIP_TEXT_FR

# ---------------------------------------------------------------------------
# Page registry: slug, url, disclosure class (SHIPS_V2 / NEW / EXEMPT / HOME)
# ---------------------------------------------------------------------------
#
# Pass-5 rename (P1 map, docs/SPRINT_KICKOFF_pass5.md): slugs/URLs below updated to the
# renamed page files; the "Périmètres_personnalisés" entry keeps its NEW-page disclosure class even
# though its former sidebar-selector mechanic is retired (R1) -- see the state(d) block
# note further down.
PAGES = [
    ("Home", "/", "HOME"),
    ("Laboratoires", "/Laboratoires", "SHIPS_V2"),
    ("Périmètres_personnalisés", "/Périmètres_personnalisés", "NEW"),
    ("Portefeuille_thématique", "/Portefeuille_thématique", "SHIPS_V2"),
    ("Exploration_thématique", "/Exploration_thématique", "SHIPS_V2"),
    ("I-SITE", "/I-SITE", "NEW"),
    ("Collaborations", "/Collaborations", "NEW"),
    ("Zoom_partenaire", f"/Zoom_partenaire?partner_id={PARTNER_ID}", "NEW"),
    ("Géographie", "/Géographie", "NEW"),
    ("Annuaire_auteurs", "/Annuaire_auteurs", "NEW"),
    ("Profil_auteur", f"/Profil_auteur?author_id={AUTHOR_ID}", "NEW"),
    ("Identifiants_et_couverture", "/Identifiants_et_couverture", "EXEMPT"),
]

results: dict[tuple[str, int], dict] = {}   # (slug, width) -> {exception, scroll_ok, shot}
state_results: list[str] = []               # human-readable PASS/FAIL lines
marks_results: list[str] = []
clip_results: list[str] = []                # pass-7a: clipped-gutter check per page x width
failures: list[str] = []
observations: list[str] = []
checks = 0


def ascii_(s) -> str:
    return str(s).encode("ascii", "replace").decode()


# ---------------------------------------------------------------------------
# Plotly marks probe (copy-adapted from tests/ui/smoke.py's PLOTLY_PROBE, read-only reuse)
# ---------------------------------------------------------------------------
PLOTLY_PROBE = """() => {
  const ITEM_BYTES = {i1:1,u1:1,i2:2,u2:2,i4:4,u4:4,f4:4,i8:8,u8:8,f8:8};
  const len = (a) => {
    if (a == null) return 0;
    if (Array.isArray(a)) return a.length;
    if (ArrayBuffer.isView(a)) return a.length;
    if (typeof a === 'object' && typeof a.bdata === 'string') {
      try { return Math.floor(atob(a.bdata).length / (ITEM_BYTES[a.dtype] || 8)); }
      catch (e) { return 0; }
    }
    return 0;
  };
  return Array.from(document.querySelectorAll('.js-plotly-plot')).map((gd, i) => {
    let points = 0;
    const traces = gd.data || [];
    traces.forEach(t => {
        // t.locations covers Scattergeo/Choropleth traces keyed by ISO code instead of
        // lat/lon (page 8's country map: verified live -- t.lat/t.lon are only ever
        // populated on its 3 single-point legend-circle traces, the REAL ~120-country
        // layer is `locations`-keyed and was a false-empty under x/y/z/lat/lon alone).
        points += Math.max(len(t.values), len(t.labels), len(t.ids), len(t.x), len(t.y),
                           len(t.z), len(t.locations), len(t.lat), len(t.lon));
    });
    const lay = gd.layout || {};
    const anns = (lay.annotations || []).map(a => String(a.text || ''));
    return {
        index: i, points: points, traces: (gd.data || []).length,
        empty_state: anns.some(t => t.indexOf('No data') !== -1),
        title: (lay.title && (lay.title.text || lay.title)) || '',
    };
  });
}"""


def chart_marks(page):
    return page.evaluate(PLOTLY_PROBE)


def marks_check(page):
    charts = chart_marks(page)
    empty = [c for c in charts if c["points"] == 0 and not c["empty_state"]]
    return charts, empty


# ---------------------------------------------------------------------------
# pass-7a addition (S-INSP deliverable 2): clipped-gutter check -- count <text>
# elements of each Plotly figure whose bounding box lies OUTSIDE the figure's own
# container box (its margin IS part of that box, so a correctly-placed gutter
# number never counts; only genuine overflow/clipping does).
# ---------------------------------------------------------------------------
TEXT_CLIP_PROBE = """() => {
  return Array.from(document.querySelectorAll('.js-plotly-plot')).map((gd, i) => {
    const gdBox = gd.getBoundingClientRect();
    let clipped = 0, total = 0;
    gd.querySelectorAll('text').forEach((t) => {
        const b = t.getBoundingClientRect();
        if (b.width === 0 && b.height === 0) return;  // not laid out -- ignore
        total += 1;
        const outside = (b.right < gdBox.left || b.left > gdBox.right ||
                          b.bottom < gdBox.top || b.top > gdBox.bottom);
        if (outside) clipped += 1;
    });
    return {index: i, clipped: clipped, total: total};
  });
}"""


def text_clip_check(page):
    return page.evaluate(TEXT_CLIP_PROBE)


def blank_images(page) -> int:
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('[data-testid=\"stImage\"] img'))"
        ".filter(im => !im.naturalWidth || im.naturalWidth < 50).length"
    )


def has_exception(page):
    n = page.locator('[data-testid="stException"]').count()
    body = page.inner_text("body")
    broken = n > 0 or "Traceback (most recent call last)" in body
    detail = ""
    if broken:
        detail = (page.locator('[data-testid="stException"]').first.inner_text()[:500]
                  if n else body[:500])
    return broken, detail


def scroll_check(page):
    dims = page.evaluate(
        "() => ({sw: document.body.scrollWidth, iw: window.innerWidth})"
    )
    ok = dims["sw"] <= dims["iw"] + 1  # 1px rounding tolerance
    return dims["sw"], dims["iw"], ok


def full_shot(page, path: Path, width: int) -> None:
    """Grow the viewport to the main container's scrollHeight before shooting (Streamlit
    scrolls inside its own container -- full_page=True alone only captures one viewport,
    the same trap documented in _appserver.py / smoke.py)."""
    height = page.evaluate(
        "() => { const e = document.querySelector('[data-testid=\"stMain\"]')"
        " || document.querySelector('section.main');"
        " return e ? e.scrollHeight : document.body.scrollHeight; }"
    )
    tall = max(BASE_HEIGHT, min(int(height) + 120, 14000))
    page.set_viewport_size({"width": width, "height": tall})
    page.wait_for_timeout(900)
    page.screenshot(path=str(path))
    page.set_viewport_size({"width": width, "height": BASE_HEIGHT})
    page.wait_for_timeout(250)


def goto_width(page, base: str, path: str, width: int) -> None:
    page.set_viewport_size({"width": width, "height": BASE_HEIGHT})
    srv.goto(page, base, path)


def toggle_artifact(page) -> None:
    sidebar = page.locator('[data-testid="stSidebar"]')
    sidebar.get_by_text(ARTIFACT_TOGGLE_LABEL, exact=False).click()
    srv.settle(page)


def toggle_conference(page) -> None:
    sidebar = page.locator('[data-testid="stSidebar"]')
    sidebar.get_by_text("Inclure les articles de conférence", exact=True).click()
    srv.settle(page)


# select_perimeter() (sidebar "Périmètre actif" selectbox) is DELETED here -- pass 5
# (R1) retires that sidebar control entirely (lib.controls.sidebar()'s own docstring);
# see the state(d) retirement note further down for what this used to drive.


def click_grid_row(page, row_index: int, grid_index: int = 0) -> None:
    grid = page.locator('[data-testid="stDataFrame"]').nth(grid_index)
    grid.scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    y = 50 + 36 * row_index
    grid.hover(position={"x": 10, "y": y})
    page.wait_for_timeout(120)
    grid.click(position={"x": 10, "y": y})
    page.wait_for_timeout(400)
    srv.settle(page)


# ---------------------------------------------------------------------------
# Pass A -- per page x per width: exception-free, no horizontal scroll, screenshot.
# Marks-check recorded once (at 1920, default state) per page.
# ---------------------------------------------------------------------------
def run_width_matrix(page, base: str) -> None:
    global checks
    for slug, url, cls in PAGES:
        for width in WIDTHS:
            checks += 1
            goto_width(page, base, url, width)
            broken, detail = has_exception(page)
            sw, iw, scroll_ok = scroll_check(page)
            shot = SHOTS / f"{slug}_{width}.png"
            full_shot(page, shot, width)
            blanks = blank_images(page)
            ok = (not broken) and scroll_ok
            results[(slug, width)] = {
                "exception": broken, "scroll_ok": scroll_ok, "sw": sw, "iw": iw,
                "shot": shot, "blanks": blanks,
            }
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] {slug} @ {width}px  exception={broken} scrollWidth={sw} "
                  f"innerWidth={iw} scroll_ok={scroll_ok} blanks={blanks}")
            if broken:
                failures.append(f"{slug}@{width}px: Streamlit exception -- {ascii_(detail)}")
            if not scroll_ok:
                failures.append(
                    f"{slug}@{width}px: scrollWidth ({sw}) > innerWidth ({iw}) -- "
                    f"page body scrolls sideways. Screenshot: {shot.relative_to(ROOT)}"
                )
            if blanks:
                failures.append(f"{slug}@{width}px: {blanks} blank rendered image(s) (e.g. wordcloud).")

            # pass-7a (S-INSP deliverable 2): clipped-gutter check, every page x every
            # width (clipping is more likely to bite at 390 px than 1920, so unlike the
            # marks-check below this is NOT limited to 1920).
            if cls != "HOME":
                checks += 1
                clip_info = text_clip_check(page)
                total_clipped = sum(c["clipped"] for c in clip_info)
                if total_clipped:
                    per_chart = ", ".join(f"#{c['index']}={c['clipped']}/{c['total']}"
                                           for c in clip_info if c["clipped"])
                    failures.append(f"{slug}@{width}px: {total_clipped} clipped <text> element(s) "
                                     f"outside their figure's own box -> {per_chart}")
                    clip_results.append(f"[FAIL] {slug}@{width}px: {total_clipped} clipped -> {per_chart}")
                else:
                    clip_results.append(f"[ok] {slug}@{width}px: 0 clipped ({len(clip_info)} figure(s))")

            if width == 1920 and cls != "HOME":
                charts, empty = marks_check(page)
                checks += 1
                if empty:
                    detail_m = ", ".join(f"#{c['index']} (traces={c['traces']})" for c in empty)
                    failures.append(f"{slug}@1920px marks-check: {len(empty)}/{len(charts)} "
                                     f"chart(s) with ZERO data points -> {detail_m}")
                    marks_results.append(f"[FAIL] {slug}: {len(empty)}/{len(charts)} empty -> {detail_m}")
                else:
                    marks_results.append(
                        f"[ok] {slug}: {len(charts)} chart(s), points={[c['points'] for c in charts]}")


# ---------------------------------------------------------------------------
# Pass B -- state matrix at 1920, on the 11 non-Home pages.
# ---------------------------------------------------------------------------
def run_state_matrix(page, base: str) -> None:
    global checks
    for slug, url, cls in PAGES:
        if cls == "HOME":
            continue
        goto_width(page, base, url, 1920)

        # (b) artifact toggle ON -> class-specific disclosure text, screenshot, no exception.
        toggle_artifact(page)
        body = page.inner_text("body")
        broken, detail = has_exception(page)
        sw, iw, scroll_ok = scroll_check(page)
        shot = SHOTS / f"{slug}_1920_artifact.png"
        full_shot(page, shot, 1920)
        checks += 1
        if cls == "SHIPS_V2":
            marker_ok = STRIP_FRAGMENT in body
            marker_name = "ships_v2_strip"
        elif cls == "EXEMPT":
            marker_ok = EXEMPT_CAPTION_FRAGMENT in body
            marker_name = "page-level artifact-exempt caption"
        else:  # NEW
            marker_ok = BANNER_FRAGMENT in body
            marker_name = "full-width S6.2 banner"
        ok = marker_ok and not broken and scroll_ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {slug} state(b) artifact ON: class={cls} marker({marker_name})={marker_ok} "
              f"exception={broken} scroll_ok={scroll_ok}")
        state_results.append(f"{slug} (b) artifact ON [{cls}]: marker={marker_ok} exc={broken} scroll={scroll_ok}")
        if not marker_ok:
            failures.append(f"{slug} state(b): expected {marker_name} text not found with artifact "
                             f"toggle ON (class={cls}). Screenshot: {shot.relative_to(ROOT)}")
        if broken:
            failures.append(f"{slug} state(b) artifact ON: exception -- {ascii_(detail)}")
        if not scroll_ok:
            failures.append(f"{slug} state(b) artifact ON: scrollWidth {sw} > innerWidth {iw}")
        toggle_artifact(page)  # back OFF

        # (c) conference toggle OFF -> renders, no exception.
        toggle_conference(page)
        broken, detail = has_exception(page)
        sw, iw, scroll_ok = scroll_check(page)
        shot = SHOTS / f"{slug}_1920_noconf.png"
        full_shot(page, shot, 1920)
        checks += 1
        ok = (not broken) and scroll_ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {slug} state(c) conference OFF: exception={broken} scroll_ok={scroll_ok}")
        state_results.append(f"{slug} (c) conference OFF: exc={broken} scroll={scroll_ok}")
        if broken:
            failures.append(f"{slug} state(c) conference OFF: exception -- {ascii_(detail)}")
        if not scroll_ok:
            failures.append(f"{slug} state(c) conference OFF: scrollWidth {sw} > innerWidth {iw}")
        toggle_conference(page)  # back ON

        # (d) In_ISITE perimeter active -- RETIRED (pass 5, R1, 2026-08-18).
        #
        # This sub-block used to drive `select_perimeter()`'s sidebar "Périmètre actif"
        # selectbox and check that pages 2/3/6's tiles/strips responded. R1 removes that
        # sidebar control entirely -- I-SITE becomes an overlay everywhere instead of a
        # corpus-narrowing filter (lib.controls.sidebar()'s own docstring) -- so there is
        # no selectbox left for `select_perimeter()` to find; running it as before would
        # hang/raise on a 0-match locator rather than reveal an app defect. Left as a
        # documented no-op (not silently deleted) so a future stream that wires the NEW
        # `isite_overlay` toggle into these 3 pages knows exactly what state-proof this
        # slot used to carry and can write its OWN version against lib.overlay instead.
        pass


# ---------------------------------------------------------------------------
# Pass C -- page 6's momentum quadrant lives one tab deep; dedicated screenshot proof
# (the generic marks-check above already reads gd.data regardless of tab visibility --
# Streamlit tabs execute + mount ALL tab bodies every rerun, only CSS hides the inactive
# one -- but a visual proof of THIS specific figure is worth its own shot).
# ---------------------------------------------------------------------------
def run_quadrant_proof(page, base: str) -> None:
    global checks
    goto_width(page, base, "/Collaborations", 1920)
    tab = page.get_by_text("Dynamique (momentum)", exact=False).first
    checks += 1
    if not tab.count():
        failures.append("Collaborations: 'Dynamique (momentum)' tab not found (V1 quadrant unreachable).")
        print("[FAIL] V1 quadrant tab not found")
        return
    tab.click()
    page.wait_for_timeout(600)
    srv.settle(page)
    shot = SHOTS / "Collaborations_1920_quadrant-tab.png"
    full_shot(page, shot, 1920)
    charts, empty = marks_check(page)
    broken, detail = has_exception(page)
    ok = (not broken) and not empty and len(charts) > 0
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] V1 quadrant (tab-deep): charts={len(charts)} empty={len(empty)} exception={broken}")
    marks_results.append(f"[{'ok' if ok else 'FAIL'}] Collaborations (V1 quadrant tab): "
                          f"{len(charts)} chart(s), points={[c['points'] for c in charts]}")
    if broken:
        failures.append(f"Collaborations V1 quadrant tab: exception -- {ascii_(detail)}")
    if empty:
        failures.append(f"Collaborations V1 quadrant tab: chart(s) with zero points -> {empty}")


# ---------------------------------------------------------------------------
# Pass D -- page 7 drill path end-to-end: field -> subfield -> topic (dagger visible)
# -> per-cell publications expander -> download xlsx -> parse it.
# ---------------------------------------------------------------------------
def run_drill_path(context, base: str) -> None:
    global checks
    page = context.new_page()  # fresh Streamlit session -- no leftover drill state from Pass A/B
    page.set_default_timeout(60_000)
    page.set_viewport_size({"width": 1920, "height": 1400})

    # bonus: the true cold visit (no entity resolved) still renders its search-fallback.
    srv.goto(page, base, "/Zoom_partenaire")
    broken, detail = has_exception(page)
    checks += 1
    print(f"[{'PASS' if not broken else 'FAIL'}] Zoom_partenaire cold visit (no partner selected): exception={broken}")
    if broken:
        failures.append(f"Zoom_partenaire cold visit: exception -- {ascii_(detail)}")
    full_shot(page, SHOTS / "Zoom_partenaire_1920_no-selection.png", 1920)

    srv.goto(page, base, f"/Zoom_partenaire?partner_id={PARTNER_ID}")
    click_grid_row(page, 4)  # field: Health Professions
    body = page.inner_text("body")
    checks += 1
    ok1 = ("Sous-champs de" in body) and ("Health Professions" in body)
    print(f"[{'PASS' if ok1 else 'FAIL'}] drill step 1/4: field row -> subfield rows ({ok1})")
    if not ok1:
        failures.append("Zoom_partenaire drill: clicking field row 4 (Health Professions) did not "
                         "reach the subfield level.")
    full_shot(page, SHOTS / "Zoom_partenaire_1920_drill-field.png", 1920)

    click_grid_row(page, 0)  # subfield: General Health Professions
    body = page.inner_text("body")
    checks += 1
    ok2 = ("Topics de" in body) and ("General Health Professions" in body)
    print(f"[{'PASS' if ok2 else 'FAIL'}] drill step 2/4: subfield row -> topic rows ({ok2})")
    if not ok2:
        failures.append("Zoom_partenaire drill: clicking subfield row 0 (General Health Professions) "
                         "did not reach the topic level.")
    full_shot(page, SHOTS / "Zoom_partenaire_1920_drill-subfield.png", 1920)

    # dagger visible: read the topic grid's accessible-DOM rows (canvas text is otherwise
    # invisible to inner_text -- same convention as P3's pass3_render_check.shot_dataframe).
    topic_grid = page.locator('[data-testid="stDataFrame"]').first
    acc_rows = topic_grid.evaluate(
        "el => Array.from(el.querySelectorAll('[role=\"row\"]')).map(r => r.innerText)"
    )
    dagger_row = next((r for r in acc_rows if "†" in r), None)
    checks += 1
    ok3 = dagger_row is not None and "Health, Medicine and Society" in dagger_row
    print(f"[{'PASS' if ok3 else 'FAIL'}] drill step 3/4: dagger visible on flagged topic row ({ok3})")
    if not ok3:
        failures.append(f"Zoom_partenaire drill: expected dagger marker on 'Health, Medicine and "
                         f"Society' (T13099, artifact_flag=True) topic row -- rows seen: "
                         f"{[ascii_(r) for r in acc_rows[:6]]}")

    click_grid_row(page, 0)  # topic: Health, Medicine and Society (T13099, flagged)
    page.wait_for_timeout(300)
    srv.settle(page)
    body = page.inner_text("body")
    checks += 1
    ok4 = ("Publications --" in body) or ("Publications —" in body)
    print(f"[{'PASS' if ok4 else 'FAIL'}] drill step 4/4: per-cell publications expander opened ({ok4})")
    if not ok4:
        failures.append("Zoom_partenaire drill: per-cell publications expander did not open after "
                         "selecting the topic row.")
    full_shot(page, SHOTS / "Zoom_partenaire_1920_drill-topic-cellpubs.png", 1920)

    dl_buttons = page.get_by_text("Publications (xlsx)", exact=False)
    checks += 1
    if not dl_buttons.count():
        failures.append("Zoom_partenaire drill: no 'Publications (xlsx)' download control found "
                         "in the per-cell expander.")
        print("[FAIL] drill export: no download control found")
    else:
        dl_dir = SHOTS / "_downloads"
        dl_dir.mkdir(exist_ok=True)
        with page.expect_download() as dl_info:
            dl_buttons.first.click()
        download = dl_info.value
        fname = download.suggested_filename
        target = dl_dir / fname
        download.save_as(str(target))

        sys.path.insert(0, str(ROOT / "Streamlit"))
        from lib.exports import parse_filename, build_filename, ExportState
        import openpyxl

        try:
            parsed = parse_filename(fname)
            st_ = ExportState(snapshot=parsed["snapshot"], conf=parsed["conf"],
                               artifact=parsed["artifact"], subset=parsed["subset"])
            rebuilt = build_filename(parsed["view"], parsed["indicator"], st_,
                                      entity=parsed["entity"], node=parsed["node"])
            roundtrip_ok = (rebuilt == fname)
        except Exception as e:
            roundtrip_ok = False
            parsed = {}
            print(f"parse_filename raised: {e}")

        wb = openpyxl.load_workbook(str(target))
        method_sheet = wb[wb.sheetnames[0]]
        header_fields = {row[0]: row[1] for row in method_sheet.iter_rows(min_row=2, values_only=True) if row[0]}
        expected_header_fields = {
            "method_one_liner", "snapshot_date", "active_filters", "conference_toggle_state",
            "artifact_toggle_state", "artifact_applied", "artifact_banner_text_if_on",
            "deferred_twin_columns", "perimeter_subset", "entity", "drill_node", "generation_date",
        }
        header_ok = expected_header_fields.issubset(header_fields.keys())
        data_sheet = wb[wb.sheetnames[1]]
        n_data_rows = data_sheet.max_row - 1

        ok5 = roundtrip_ok and header_ok and n_data_rows > 0
        status = "PASS" if ok5 else "FAIL"
        print(f"[{status}] drill export: file={fname}")
        print(f"    roundtrip_ok={roundtrip_ok} header_fields_ok={header_ok} data_rows={n_data_rows}")
        print(f"    header sheet fields: {sorted(header_fields.keys())}")
        if not roundtrip_ok:
            failures.append(f"Zoom_partenaire drill export: filename did not round-trip via "
                             f"parse_filename/build_filename: {fname!r}")
        if not header_ok:
            missing = expected_header_fields - header_fields.keys()
            failures.append(f"Zoom_partenaire drill export: header sheet missing fields: {missing}")
        if n_data_rows <= 0:
            failures.append(f"Zoom_partenaire drill export: data sheet has {n_data_rows} rows, expected > 0.")

    page.close()


# ---------------------------------------------------------------------------
# Pass E -- page 10 author export guard: works xlsx has NO impact column; the impact
# drill block itself carries NO download control anywhere in it.
# ---------------------------------------------------------------------------
def run_author_export_guard(context, base: str) -> None:
    global checks
    page = context.new_page()
    page.set_default_timeout(60_000)
    page.set_viewport_size({"width": 1920, "height": 2000})

    srv.goto(page, base, "/Profil_auteur")  # bonus: cold visit, no author resolved
    broken, _ = has_exception(page)
    checks += 1
    print(f"[{'PASS' if not broken else 'FAIL'}] Profil_auteur cold visit (no author selected): exception={broken}")
    if broken:
        failures.append("Profil_auteur cold visit: exception on the search-fallback state.")
    full_shot(page, SHOTS / "Profil_auteur_1920_no-selection.png", 1920)

    srv.goto(page, base, f"/Profil_auteur?author_id={AUTHOR_ID}")
    dl_total_before = page.locator('[data-testid="stDownloadButton"]').count()

    expanders = page.locator('[data-testid="stExpander"]')
    pub_exp = expanders.filter(has_text="Publications").first
    checks += 1
    if not pub_exp.count():
        failures.append("Profil_auteur: Publications expander not found.")
        print("[FAIL] Profil_auteur: Publications expander not found")
        return
    pub_exp.locator("summary, div").first.click()
    page.wait_for_timeout(400)
    srv.settle(page)

    dl_buttons = page.get_by_text("Publications (xlsx)", exact=False)
    ok_dl_present = dl_buttons.count() > 0
    print(f"[{'PASS' if ok_dl_present else 'FAIL'}] works-list download control present: {ok_dl_present}")
    if not ok_dl_present:
        failures.append("Profil_auteur: no 'Publications (xlsx)' download control found in the works list.")

    fname = None
    if ok_dl_present:
        dl_dir = SHOTS / "_downloads"
        dl_dir.mkdir(exist_ok=True)
        with page.expect_download() as dl_info:
            dl_buttons.first.click()
        download = dl_info.value
        fname = download.suggested_filename
        target = dl_dir / fname
        download.save_as(str(target))

        import openpyxl
        import re as _re
        wb = openpyxl.load_workbook(str(target))
        data_sheet = wb[wb.sheetnames[1]]
        header = [c.value for c in next(data_sheet.iter_rows(min_row=1, max_row=1))]
        bad_cols = [h for h in header if h and _re.search(r"fwci|pptop|impact|citation", str(h), _re.I)]
        checks += 1
        ok_cols = not bad_cols
        print(f"[{'PASS' if ok_cols else 'FAIL'}] works xlsx has no impact/fwci/pptop/citation column: "
              f"{ok_cols} (header={header})")
        if not ok_cols:
            failures.append(f"Profil_auteur works export ({fname}): impact-shaped column(s) present "
                             f"in the data sheet -- {bad_cols}. Header: {header}")

    full_shot(page, SHOTS / "Profil_auteur_1920_export-guard.png", 1920)

    # Now open the impact drill and confirm NO new download control appears anywhere.
    drill_exp = expanders.filter(has_text="contexte d'impact").first
    checks += 1
    if not drill_exp.count():
        failures.append("Profil_auteur: impact-drill expander (\"contexte d'impact\") not found.")
        print("[FAIL] Profil_auteur: impact-drill expander not found")
        return
    drill_exp.locator("summary, div").first.click()
    page.wait_for_timeout(400)
    srv.settle(page)
    body = page.inner_text("body")
    tiles_rendered = "FWCI_FR" in body
    dl_total_after = page.locator('[data-testid="stDownloadButton"]').count()
    checks += 1
    # dl_total_before was already taken with the (collapsed) works-list button present in the
    # DOM -- Streamlit mounts expander content regardless of collapsed state (confirmed live:
    # count is 1 even before the Publications expander is ever clicked open). So the safeguard-
    # 3bis invariant is simply "opening the drill adds NO further download control": before == after.
    ok_guard = (dl_total_after == dl_total_before)
    print(f"[{'PASS' if ok_guard else 'FAIL'}] impact-drill has ZERO extra download controls: "
          f"before={dl_total_before} after={dl_total_after} tiles_rendered={tiles_rendered}")
    if not ok_guard:
        failures.append(f"Profil_auteur: download-button count changed after opening the impact drill "
                         f"({dl_total_before} -> {dl_total_after}) -- safeguard 3bis violation.")
    full_shot(page, SHOTS / "Profil_auteur_1920_impact-drill.png", 1920)
    page.close()


# ---------------------------------------------------------------------------
# Pass F -- pass-7a (S-INSP deliverable 2): Zoom_partenaire "3 partners" requirement.
# PAGES above already covers CHRU (I4210100260) through the normal per-page x per-width
# matrix; this pass adds CNRS (the largest partner, every other pass-7 stream's own
# reference entity) and a thin partner (<20 co-pubs) so all 3 render clean.
# ---------------------------------------------------------------------------
ZOOM_EXTRA_PARTNERS = [
    ("CNRS", "I1294671590"),
    ("thin_I4210137456", "I4210137456"),  # "Momentum Research" (US), co_works_full=19
]


def run_zoom_partner_matrix(page, base: str) -> None:
    global checks
    for label, pid in ZOOM_EXTRA_PARTNERS:
        for width in WIDTHS:
            checks += 1
            goto_width(page, base, f"/Zoom_partenaire?partner_id={pid}", width)
            broken, detail = has_exception(page)
            sw, iw, scroll_ok = scroll_check(page)
            shot = SHOTS / f"Zoom_partenaire_{label}_{width}.png"
            full_shot(page, shot, width)
            blanks = blank_images(page)
            checks += 1
            clip_info = text_clip_check(page)
            total_clipped = sum(c["clipped"] for c in clip_info)
            ok = (not broken) and scroll_ok and not total_clipped
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] Zoom_partenaire ({label}) @ {width}px  exception={broken} "
                  f"scrollWidth={sw} innerWidth={iw} clipped={total_clipped}")
            if broken:
                failures.append(f"Zoom_partenaire ({label})@{width}px: exception -- {ascii_(detail)}")
            if not scroll_ok:
                failures.append(f"Zoom_partenaire ({label})@{width}px: scrollWidth {sw} > innerWidth {iw}")
            if blanks:
                failures.append(f"Zoom_partenaire ({label})@{width}px: {blanks} blank image(s)")
            if total_clipped:
                per_chart = ", ".join(f"#{c['index']}={c['clipped']}/{c['total']}"
                                       for c in clip_info if c["clipped"])
                failures.append(f"Zoom_partenaire ({label})@{width}px: {total_clipped} clipped <text> -> {per_chart}")
                clip_results.append(f"[FAIL] Zoom_partenaire ({label})@{width}px: {total_clipped} clipped -> {per_chart}")
            else:
                clip_results.append(f"[ok] Zoom_partenaire ({label})@{width}px: 0 clipped ({len(clip_info)} figure(s))")

            if width == 1920:
                charts, empty = marks_check(page)
                checks += 1
                if empty:
                    detail_m = ", ".join(f"#{c['index']} (traces={c['traces']})" for c in empty)
                    failures.append(f"Zoom_partenaire ({label})@1920px marks-check: "
                                     f"{len(empty)}/{len(charts)} chart(s) ZERO points -> {detail_m}")
                    marks_results.append(f"[FAIL] Zoom_partenaire ({label}): {len(empty)}/{len(charts)} empty -> {detail_m}")
                else:
                    marks_results.append(
                        f"[ok] Zoom_partenaire ({label}): {len(charts)} chart(s), points={[c['points'] for c in charts]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    port = srv.free_port()
    proc = None
    t0 = time.time()
    try:
        print(f"starting streamlit on port {port}")
        proc = srv.start_app(port, SHOTS / "streamlit.log")
        base = f"http://localhost:{port}"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(accept_downloads=True,
                                           viewport={"width": 1920, "height": BASE_HEIGHT})
            page = context.new_page()
            page.set_default_timeout(60_000)

            print("\n=== Pass A+marks: per-page x per-width matrix ===")
            run_width_matrix(page, base)

            print("\n=== Pass B: state matrix (artifact/conference/perimeter) @1920 ===")
            run_state_matrix(page, base)

            print("\n=== Pass C: V1 quadrant (tab-deep) screenshot proof ===")
            run_quadrant_proof(page, base)

            page.close()

            # pass-7a (S-INSP): Passes D/E are pre-existing (pass-3) and exercise
            # Zoom_partenaire's descent/drill mechanic + Profil_auteur's export guard --
            # NOT part of this dispatch's own deliverable, and page 9 was mid-rewrite by a
            # concurrent FIX-1 stream for part of this session (see progress/P7_INSP.md).
            # A hard crash here must not swallow Pass F (this dispatch's OWN "3 partners"
            # requirement) or the final summary -- caught, logged, reported as a failure,
            # never silently absorbed.
            print("\n=== Pass D: page 7 drill path end-to-end ===")
            try:
                run_drill_path(context, base)
            except Exception as e:
                failures.append(f"Pass D (drill path) raised and did not complete: {ascii_(e)}")
                print(f"[FAIL] Pass D raised: {ascii_(e)}")

            print("\n=== Pass E: page 10 author export guard ===")
            try:
                run_author_export_guard(context, base)
            except Exception as e:
                failures.append(f"Pass E (author export guard) raised and did not complete: {ascii_(e)}")
                print(f"[FAIL] Pass E raised: {ascii_(e)}")

            print("\n=== Pass F (pass-7a, S-INSP): Zoom_partenaire 3-partner coverage ===")
            page2 = context.new_page()
            page2.set_default_timeout(60_000)
            try:
                run_zoom_partner_matrix(page2, base)
            except Exception as e:
                failures.append(f"Pass F (Zoom_partenaire 3-partner coverage) raised and did not complete: {ascii_(e)}")
                print(f"[FAIL] Pass F raised: {ascii_(e)}")
            page2.close()

            browser.close()
    finally:
        if proc:
            srv.stop_app(proc)

    elapsed = time.time() - t0
    print(f"\n(elapsed: {elapsed:.0f}s)")

    # ---- per-page x per-width matrix printout ----
    print("\n=== MATRIX (page x width) ===")
    print(f"{'page':<24}{'1920':>8}{'1280':>8}{'390':>8}")
    for slug, _url, _cls in PAGES:
        row = [slug.ljust(24)]
        for width in WIDTHS:
            r = results.get((slug, width))
            if r is None:
                row.append("  ?".rjust(8))
            else:
                ok = (not r["exception"]) and r["scroll_ok"] and not r["blanks"]
                row.append(("PASS" if ok else "FAIL").rjust(8))
        print("".join(row))

    print("\n=== STATE MATRIX ===")
    for line in state_results:
        print(" ", line)

    print("\n=== MARKS CHECK ===")
    for line in marks_results:
        print(" ", line)

    print("\n=== CLIPPED-GUTTER CHECK (pass-7a) ===")
    for line in clip_results:
        print(" ", line)

    print()
    if failures:
        print(f"RENDER PASS FAILED -- {len(failures)} failure(s) of {checks} checks")
        for f in failures:
            print(("  ! " + f).replace("\n", " ")[:600])
        return 1
    print(f"RENDER PASS PASSED -- {checks} checks, screenshots in {SHOTS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
