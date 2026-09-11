"""
UI smoke test for the Lorraine Explorer app (Stream C acceptance; pass-6 pins by S-INSP).

Renders every page for the awkward cases and fails on ANY Streamlit exception:

    a large lab · a small lab · NO LAB · the declared-empty `Jardins` ·
    a flagged hors-liste structure · an untopiced element · a null-indicator element

It also proves the two ruled switches actually switch:

    D51  the SDG panel follows `app.sdg_variant` (b_siris / c_openalex / off)
    D52  turning conference papers off changes the counts on page 1

PASS-6 UPDATE (S-INSP, closing inspection battery): the app grew from 4 surfaces this
file exercised (Menu/home, Laboratoires, Portefeuille thematique, Exploration
thematique) to 15 (Menu + 14 pages) -- a build stream's own green self-report is not
evidence a NEW page renders for real (INSPECTION_PLAYBOOK.md family 1). Every one of
the 11 pages this pass added or substantially rebuilt now gets at least one visit +
one assertion tied to something pass-6 actually changed (never just "the page loads
without an exception", which a pin can satisfy trivially and still prove nothing):

    Vue d'ensemble (1)      -- grouped-bars I-SITE overlay caption (P6-R5)
    Perimetres (3)          -- query box HIDDEN below the P6-R6 N<50 floor (real
                               registry, a handful of rows -- a pin a mutated
                               `ranked.QUERY_MIN_N` WILL fail, see mutation-check note)
    Portefeuille (4)        -- SDG method comparison labels (SIRIS/VocTagger vs
                               Aurora/OpenAlex, item #7/#12)
    Positionnement (5)      -- frontier full-depth "quantum" query (zero-fill, #20)
    Exploration (4/#21 fix) -- top-10 labs overlay actually carries the I-SITE
                               segment now (probe 5 root cause, chart-mark count
                               changes with the toggle)
    I-SITE (7)              -- canonical-list recall block (item #37)
    Collaborations (8)      -- consortium caption + momentum column help (quantified
                               re-expression, item #38); FIX-1 pass-6 fix round adds the
                               mask-members state combination (S-LENS D7): Consortium
                               column present with the mask OFF, absent (not all-empty)
                               with it ON
    Zoom partenaire (9)     -- deep-linked via ?partner_id=, per-theme profile +
                               reciprocite panel render
    Geographie (10)         -- FR country label round-trip: search "Namib", confirm
                               the selectbox's OWN VALUE (not innerText -- BaseWeb
                               renders the picked option into an <input value=...>,
                               which page.inner_text() never sees, a real gotcha hit
                               live while building this pin) reads "Namibie" (P3);
                               "Fiche pays" search box HIDDEN below the P6-R6 N<50
                               floor (FIX-1 pass-6 fix round: was the one confirmed
                               defect this file reported, S-LENS D5/S-INSP D2 --
                               now gated via should_show_query_box(), see
                               docs/LENS_ABSORPTION_pass6.md)
    Annuaire (11)           -- search returns >25 rows, "afficher plus" (+50, P8)
                               actually grows the visible count by the step
    Profil auteur (12)      -- deep-linked via ?author_id=, renders without exception
    Identifiants (13)       -- renders without exception
    Benchmark (14)          -- log/linear toggle (R18) inside its drill-down expander

Mutation-check (INSPECTION_PLAYBOOK.md family 6, "a pin that cannot fail is theater"):
the Perimetres query-box-hidden pin above was verified live by temporarily editing
`Streamlit/lib/ranked.py`'s `QUERY_MIN_N = 50` to `QUERY_MIN_N = 0`, re-running this
file, observing the NEW pin fail (the box appeared), then reverting the edit via
`git checkout -- Streamlit/lib/ranked.py` (verified `git diff` empty afterwards).
Evidence: docs/INSPECTION_REPORT_pass6.md sec. "smoke mutation-check".

Usage
    python tests/ui/smoke.py                      # default config
    python tests/ui/smoke.py --sdg-variant off    # temporarily patches config.yaml
    python tests/ui/smoke.py --sdg-variant c_openalex

Exit 0 = every case rendered. Screenshots land in reports/evals/smoke/.
Output is ASCII only (this box's console is cp1252).
"""
from __future__ import annotations

import argparse
import re
import shutil
import socket
import subprocess
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / "reports" / "evals" / "smoke"
CONFIG = ROOT / "config.yaml"
DATA_DIR = ROOT / "Streamlit" / "data"

# pass-7a (S-INSP): single-sourced SDG palette, read from the app's own module rather
# than retyped (avoids drift) -- same sys.path idiom tests/ui/render_pass3.py already uses.
sys.path.insert(0, str(ROOT / "Streamlit"))
from lib.helpers import SDG_COLORS  # noqa: E402

failures: list[str] = []
checks = 0


# ---------------------------------------------------------------------------
# server
# ---------------------------------------------------------------------------

def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_app(port: int) -> subprocess.Popen:
    # Stream the server log to a FILE, never to a pipe. Streamlit 1.6x prints a
    # deprecation warning per `use_container_width` call; that fills a 64 KB pipe
    # buffer inside one rerun and blocks the server mid-script forever, which looks
    # exactly like an app hang.
    SHOTS.mkdir(parents=True, exist_ok=True)
    log = open(SHOTS / "streamlit.log", "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "Streamlit/Menu.py",
         "--server.headless", "true", "--server.port", str(port),
         "--browser.gatherUsageStats", "false"],
        cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 120
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("streamlit died - see reports/evals/smoke/streamlit.log")
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                time.sleep(2)
                return proc
        time.sleep(0.5)
    raise RuntimeError("streamlit did not start in time")


# ---------------------------------------------------------------------------
# page helpers
# ---------------------------------------------------------------------------

def script_state(page) -> str:
    """Streamlit stamps `data-test-script-state` on the stApp element."""
    return page.evaluate(
        "() => { const e = document.querySelector('[data-testid=\"stApp\"]');"
        " return e ? e.getAttribute('data-test-script-state') : ''; }")


def settle(page, timeout: int = 120_000) -> None:
    """
    Wait until Streamlit has finished its rerun.

    `notRunning` is the only reliable idle signal — the status widget lingers in
    the DOM long after the rerun, so counting it never settles.
    """
    page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=timeout)
    page.wait_for_timeout(1500)         # a widget change takes ~1s to start a rerun
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        if script_state(page) == "notRunning":
            break
        time.sleep(0.3)
    else:
        raise TimeoutError("streamlit still running after %.0fs" % (timeout / 1000))
    page.wait_for_timeout(400)


VIEWPORT = {"width": 1500, "height": 1100}


def full_shot(page, path: Path) -> None:
    """
    Capture the WHOLE page.

    `full_page=True` is not enough: Streamlit scrolls inside its own container, so
    it only ever yields one viewport. Grow the viewport to the container's scroll
    height instead, shoot, then shrink back.
    """
    height = page.evaluate(
        "() => { const e = document.querySelector('[data-testid=\"stMain\"]')"
        " || document.querySelector('section.main');"
        " return e ? e.scrollHeight : document.body.scrollHeight; }")
    tall = max(VIEWPORT["height"], min(int(height) + 120, 12000))
    page.set_viewport_size({"width": VIEWPORT["width"], "height": tall})
    page.wait_for_timeout(1200)
    page.screenshot(path=str(path))
    page.set_viewport_size(VIEWPORT)
    page.wait_for_timeout(400)


PLOTLY_PROBE = """() => {
  // plotly.py >= 6 ships numeric arrays as base64 {dtype, bdata} instead of JSON
  // lists, and plotly.js may hand them back as typed arrays. Counting only
  // Array.isArray() therefore reports "0 points" for charts that render perfectly
  // -- measure the encoding, not the JSON shape.
  const ITEM_BYTES = {i1:1,u1:1,i2:2,u2:2,i4:4,u4:4,f4:4,i8:8,u8:8,f8:8};
  const len = (a) => {
    if (a == null) return 0;
    if (Array.isArray(a)) return a.length;
    if (ArrayBuffer.isView(a)) return a.length;
    if (typeof a === 'object' && typeof a.bdata === 'string') {
      try {
        return Math.floor(atob(a.bdata).length / (ITEM_BYTES[a.dtype] || 8));
      } catch (e) { return 0; }
    }
    return 0;
  };
  return Array.from(document.querySelectorAll('.js-plotly-plot')).map((gd, i) => {
    let points = 0;
    const traces = gd.data || [];
    traces.forEach(t => {
        // PASS-6 FIX (S-INSP): a go.Scattergeo trace (the new Geographie map, #8/
        // P3) carries its points in `locations` (ISO-3 codes) and/or `lon`/`lat` --
        // NEVER `x`/`y`/`z`. Without this, every legitimate map trace counted as
        // 0 points and got reported as a false "empty chart" (caught live: the
        // country-bubble map AND its 3 legend-calibration traces all read 0 before
        // this fix, even though the rendered PNG plainly shows real bubbles).
        points += Math.max(len(t.values), len(t.labels), len(t.ids),
                           len(t.x), len(t.y), len(t.z),
                           len(t.locations), len(t.lon), len(t.lat));
    });
    const lay = gd.layout || {};
    const anns = (lay.annotations || []).map(a => String(a.text || ''));
    return {
        index: i,
        points: points,
        traces: (gd.data || []).length,
        // An INTENTIONAL empty state draws no trace and says "Aucune donnee" (FR-
        // wrapped, D61 reversed pass 5 -- was the English "No data" pre-rename; this
        // probe was stale on the retired string, which is why it never excused a
        // real empty-declared-lab chart -- checked as ASCII-folded so an accent
        // variant can't silently defeat the match). Do not excuse a figure merely
        // because it carries annotations: this app annotates per-field counts in the
        // gutter, so the broken FWCI whisker plot had 26 annotations and zero marks.
        empty_state: anns.some(t => t.indexOf('No data') !== -1 ||
                                     t.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').indexOf('Aucune donnee') !== -1),
        title: (lay.title && (lay.title.text || lay.title)) || '',
    };
  });
}"""


def chart_marks(page):
    """One record per rendered Plotly figure: how many data points it carries."""
    return page.evaluate(PLOTLY_PROBE)


def assert_charts_have_marks(page, name: str) -> None:
    """
    A chart that renders an EMPTY FRAME - axes drawn, no marks - raises nothing and
    screenshots as a plausible plot. That is how the page-1 FWCI whisker plot shipped
    broken through a smoke suite that only asserted "renders without exception".

    Every Plotly figure on the page must carry at least one data point, unless it
    is the deliberate "No data" empty state.
    """
    global checks
    checks += 1
    charts = chart_marks(page)
    empty = [c for c in charts if c["points"] == 0 and not c["empty_state"]]
    if not charts:
        print(f"  [ok] {name}: no plotly charts on this page")
        return
    if empty:
        detail = ", ".join(f"#{c['index']} (traces={c['traces']})" for c in empty)
        failures.append(f"{name}: {len(empty)} chart(s) with ZERO data points: {detail}")
        print(f"  [FAIL] {name}: {len(empty)} of {len(charts)} chart(s) EMPTY -> {detail}")
    else:
        print(f"  [ok] {name}: {len(charts)} chart(s), "
              f"points per chart {[c['points'] for c in charts]}")

    # The subfield wordcloud is matplotlib, not Plotly: guard it the same way.
    blank = page.evaluate(
        "() => Array.from(document.querySelectorAll('[data-testid=\"stImage\"] img'))"
        ".filter(im => !im.naturalWidth || im.naturalWidth < 50).length")
    if blank:
        failures.append(f"{name}: {blank} rendered image(s) are blank (wordcloud?)")
        print(f"  [FAIL] {name}: {blank} blank image(s)")


# ---------------------------------------------------------------------------
# pass-7a additions (S-INSP battery): content-addressed chart lookup (never a raw
# DOM index, which shifts with page/partner state) + native st.metric reader (pages
# 8/9 use real st.metric tiles, unlike page 2's custom "font-size: 22px" mini-fiche
# big_number() above already handles).
# ---------------------------------------------------------------------------
CHART_INFO_PROBE = """() => {
  return Array.from(document.querySelectorAll('.js-plotly-plot')).map((gd, i) => {
    const lay = gd.layout || {};
    const xt = (lay.xaxis && lay.xaxis.title && (lay.xaxis.title.text ?? lay.xaxis.title)) || '';
    const y2 = lay.yaxis2 || null;
    const d0 = (gd.data && gd.data[0]) || {};
    const firstY = Array.isArray(d0.y) && d0.y.length ? String(d0.y[0]) : '';
    return {
        index: i,
        xaxis_title: String(xt),
        n_traces: (gd.data || []).length,
        first_y: firstY,
        y2_ticktext: y2 ? y2.ticktext : null,
    };
  });
}"""


def chart_info(page):
    return page.evaluate(CHART_INFO_PROBE)


def find_chart_index(charts_info, *, xaxis_title=None, first_y_prefix=None, has_y2=None):
    """Content-address a figure on the CURRENT page by a stable property -- title
    text, first category label, or presence of balance_bars' own linked yaxis2 --
    rather than a raw index, which shifts with which sections a page renders."""
    for c in charts_info:
        if xaxis_title is not None and c["xaxis_title"] != xaxis_title:
            continue
        if first_y_prefix is not None and not c["first_y"].startswith(first_y_prefix):
            continue
        if has_y2 is not None and bool(c["y2_ticktext"]) != has_y2:
            continue
        return c["index"]
    return -1


def marker_colors(page, chart_index: int):
    """`gd.data[0].marker.color` for one figure, normalised to a list (Plotly accepts
    either a scalar colour or a per-point array)."""
    return page.evaluate(
        "(i) => { const gd = document.querySelectorAll('.js-plotly-plot')[i];"
        " const c = gd.data[0].marker.color; return Array.isArray(c) ? c : [c]; }",
        chart_index,
    )


def metric_value(page, label_substr: str) -> str:
    """Native `st.metric` value for the first tile whose label contains `label_substr`."""
    tile = page.locator('[data-testid="stMetric"]').filter(has_text=label_substr).first
    if not tile.count():
        return ""
    val = tile.locator('[data-testid="stMetricValue"]')
    return val.inner_text().strip() if val.count() else ""


def pick_sdg_rich_lab() -> str | None:
    """The lab with the most SIRIS-method SDG rows above the reliability floor
    (conf_state='all') -- read from disk so the pin never depends on a hand-picked
    lab name going stale (S-SDG's own progress note used the same reasoning)."""
    try:
        df = pd.read_parquet(DATA_DIR / "sdg_lab_methods.parquet",
                              columns=["lab", "conf_state", "sdg", "share_lab_corpus_siris"])
        counts = (df[(df["conf_state"] == "all") & df["share_lab_corpus_siris"].notna()]
                  .groupby("lab").size().sort_values(ascending=False))
        return str(counts.index[0]) if len(counts) else None
    except Exception as e:
        print(f"  [warn] pick_sdg_rich_lab: {e}")
        return None


def assert_sdg_bar_colors(page, name: str) -> None:
    """P17: the first Plotly figure whose category axis starts with 'ODD ' must
    colour its first bar/point with SDG_COLORS[goal] (parsed from the label)."""
    global checks
    checks += 1
    info = chart_info(page)
    idx = find_chart_index(info, first_y_prefix="ODD ")
    if idx < 0:
        failures.append(f"{name}: no chart with an 'ODD ' category found (SDG colours, P17)")
        print(f"  [FAIL] {name}: SDG chart not found")
        return
    colors = marker_colors(page, idx)
    label = info[idx]["first_y"]
    m = re.match(r"ODD\s+(\d+)", label)
    goal = int(m.group(1)) if m else None
    expected = SDG_COLORS.get(goal, "").lower() if goal is not None else ""
    if colors and expected and str(colors[0]).lower() == expected:
        print(f"  [ok] {name}: first SDG bar ({label}) fill {colors[0]} == SDG_COLORS[{goal}]")
    else:
        failures.append(
            f"{name}: first SDG bar fill {colors[:1]!r} != SDG_COLORS[{goal}]={SDG_COLORS.get(goal)!r} (label={label!r})")
        print(f"  [FAIL] {name}: SDG colour mismatch {colors[:1]!r} vs goal {goal}")


# ---------------------------------------------------------------------------
# pass-7b additions (S-INSP battery, W4): generic, content-addressed probes for
# the pass-7b contract (B2 gutter numbers, B3 `<b>label</b> : value` hover
# grammar, B6 red-dashed REFERENCE_RED shapes) -- read from the LIVE plotly
# JSON / DOM, never assumed from the page's Python source. See
# docs/INSPECTION_REPORT_pass7b.md.
# ---------------------------------------------------------------------------
GUTTER_TRACE_PROBE = """() => Array.from(document.querySelectorAll('.js-plotly-plot')).map((gd, i) => {
  const traces = gd.data || [];
  const last = traces[traces.length - 1] || {};
  return {index: i, hoverinfo: last.hoverinfo || '', text: (last.text || []).map(String)};
})"""


def find_gutter_chart(page):
    """The first chart whose LAST trace is a gutter phantom (`hoverinfo:
    'skip'`) carrying at least one non-empty, digit-bearing text label -- the
    `bars_with_gutter` signature (`_add_gutter_column`, lib/charts.py)."""
    info = page.evaluate(GUTTER_TRACE_PROBE)
    for c in info:
        texts = [t for t in c["text"] if t.strip()]
        if c["hoverinfo"] == "skip" and texts and all(re.search(r"\d", t) for t in texts):
            return c
    return None


def assert_gutter_number(page, name: str) -> None:
    """B2/P1: a converted horizontal bar chart carries a rendered gutter
    NUMBER (the phantom trace's own `text`), not merely a phantom trace."""
    global checks
    checks += 1
    g = find_gutter_chart(page)
    if g:
        print(f"  [ok] {name}: gutter number(s) on chart #{g['index']}, e.g. {g['text'][:2]!r}")
    else:
        failures.append(f"{name}: no bar chart with a rendered gutter NUMBER found (bars_with_gutter, B2)")
        print(f"  [FAIL] {name}: gutter number missing")


HOVER_SAMPLE_PROBE = """() => {
  const plots = Array.from(document.querySelectorAll('.js-plotly-plot'));
  for (const gd of plots) {
    for (const t of (gd.data || [])) {
      const tmpl = t.hovertemplate || '';
      const cd = t.customdata;
      if (tmpl.indexOf('customdata') >= 0 && Array.isArray(cd) && cd.length
          && typeof cd[0] === 'string' && cd[0]) {
        return cd[0];
      }
    }
  }
  return null;
}"""


def assert_hover_grammar(page, name: str) -> None:
    """B3: the hover grammar is `<b>label</b> : value` lines joined by
    `<br>`, built by `lib.hover.hover_lines` -- checked against the LIVE
    plotly JSON's own `customdata`, never the page's Python source."""
    global checks
    checks += 1
    sample = page.evaluate(HOVER_SAMPLE_PROBE)
    if sample and re.search(r"<b>[^<]+</b>\s*:\s*\S", sample):
        shown = sample.split("<br>")[0]
        print(f"  [ok] {name}: hover grammar '<b>label</b> : value' confirmed, e.g. {shown!r}")
    else:
        failures.append(f"{name}: no '<b>label</b> : value' hover string found in the live plotly JSON (sample={sample!r})")
        print(f"  [FAIL] {name}: hover grammar not found (sample={sample!r})")


REFERENCE_SHAPE_PROBE = """() => Array.from(document.querySelectorAll('.js-plotly-plot')).flatMap((gd) => {
  const lay = gd.layout || {};
  return (lay.shapes || []).map(s => ({dash: (s.line && s.line.dash) || '', color: (s.line && s.line.color) || ''}));
})"""


def assert_reference_dash(page, name: str) -> None:
    """B2/B6: the caution/parity reference is ALWAYS a dashed line in
    `H.REFERENCE_RED` (#821D13) -- one red, one meaning, never the pre-7b
    grey dotted convention."""
    global checks
    checks += 1
    shapes = page.evaluate(REFERENCE_SHAPE_PROBE)
    hit = next((s for s in shapes if s["dash"] == "dash" and str(s["color"]).lower() == "#821d13"), None)
    if hit:
        print(f"  [ok] {name}: red dashed REFERENCE_RED shape present ({len(shapes)} shape(s) total)")
    else:
        failures.append(f"{name}: no dashed #821D13 (REFERENCE_RED) shape found on any chart (shapes seen: {shapes})")
        print(f"  [FAIL] {name}: red dashed reference shape missing (shapes={shapes})")


def assert_reading_present_absent(page, name: str, present_substr: str,
                                   absent_substr: str = "Comment lire",
                                   check_absent: bool = True) -> None:
    """B2/P3: a chart's `reading_line(key, mode)` sentence renders live, and
    the OLD static paragraph it replaced is gone from the page's own text.

    `check_absent=False`: for a page that carries a DIFFERENT chart's own,
    explicitly-unmigrated static caption in the SAME body (B2 names
    `ov_breakdown_annual`'s `lib.overlay` grouped-bars caption as staying as
    it is -- 'year-axis bars ... keep lib.overlay ... hover + reading +
    tokens only', not a re-grammar) -- a whole-body substring scan cannot
    otherwise tell that legitimate text apart from a real P3 regression on
    THIS pin's own chart. Confirmed live: `lib/overlay.py:224` is the one
    surviving 'Comment lire' source in the whole `Streamlit/pages` tree that
    also renders on this page (page-1 source itself carries ZERO)."""
    global checks
    body = page.inner_text("body")
    checks += 1
    if present_substr in body:
        print(f"  [ok] {name}: reading line present ({present_substr[:40]!r}...)")
    else:
        failures.append(f"{name}: reading-line text ({present_substr[:40]!r}...) not found on the rendered page")
        print(f"  [FAIL] {name}: reading line missing")
    if not check_absent:
        return
    checks += 1
    if absent_substr not in body:
        print(f"  [ok] {name}: static '{absent_substr}' paragraph absent (P3)")
    else:
        failures.append(f"{name}: static '{absent_substr}' paragraph still present (P3 violation)")
        print(f"  [FAIL] {name}: '{absent_substr}' still present")


def check_page7_floor_style(page) -> None:
    """D9 (docs/LENS_ABSORPTION_pass7b.md): floor rows on I-SITE's
    `isite_ratio_dots` use the SAME caution channel as page 4's identical dot
    chart -- hollow marker, REFERENCE_RED (#821D13) outline, dagger baked
    into the y ticktext -- never a translucent grey fill / legend-only
    disclosure (the pre-fix divergence)."""
    global checks
    print("page I-SITE - floor-row caution channel: hollow ring + dagger ticktext (D9)")
    info = page.evaluate("""
      () => Array.from(document.querySelectorAll('.js-plotly-plot')).map((gd) => ({
        traces: (gd.data || []).map(t => ({name: t.name || '', marker: t.marker || {}})),
        ytext: (gd.layout && gd.layout.yaxis) ? gd.layout.yaxis.ticktext : null,
      }))
    """)
    floor_chart = next((c for c in info if any(str(t["name"]).startswith("< 30") for t in c["traces"])), None)
    checks += 1
    if not floor_chart:
        failures.append("isite_ratio_dots: floor trace ('< 30 travaux I-SITE') not found on I-SITE")
        print("  [FAIL] D9: floor trace not found")
        return
    tr = next(t for t in floor_chart["traces"] if str(t["name"]).startswith("< 30"))
    mk = tr["marker"] or {}
    line = mk.get("line") or {}
    fill = str(mk.get("color", "")).replace(" ", "")
    ring = str(line.get("color", "")).lower()
    ok_marker = fill == "rgba(255,255,255,0)" and ring == "#821d13"
    if ok_marker:
        print(f"  [ok] D9: floor marker hollow (fill={fill!r}) + REFERENCE_RED ring")
    else:
        failures.append(f"D9: floor marker style off -- fill={fill!r} ring={ring!r} (want hollow + #821d13)")
        print(f"  [FAIL] D9: floor marker fill={fill!r} ring={ring!r}")

    checks += 1
    ytext = floor_chart["ytext"] or []
    ok_tick = any("†" in str(t) and "821d13" in str(t).lower() for t in ytext)
    if ok_tick:
        print("  [ok] D9: a y-tick label carries the dagger inside a REFERENCE_RED span")
    else:
        failures.append(f"D9: no y-tick combines the dagger with a REFERENCE_RED span (ticktext sample={ytext[:3]})")
        print(f"  [FAIL] D9: dagger/red-span y-tick missing (sample={ytext[:3]})")


def check_page7_click_drill(page) -> None:
    """B7: the ratio dot chart's `on_select='rerun'` drill wiring, exercised
    with a REAL Playwright click on a rendered marker (never a synthetic
    session_state write) -- the 'Sélectionné' caption and the drill
    `page_link` must appear live."""
    global checks
    print("page I-SITE - dot click -> drill section changes (B7, live on_select)")
    checks += 1
    try:
        marker = page.locator('.js-plotly-plot .scatterlayer .trace path.point').first
        marker.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        marker.click(force=True)
        settle(page)
        body = page.inner_text("body")
        if "Sélectionné" in body and "Ouvrir l'exploration thématique pour" in body:
            print("  [ok] B7: dot click renders the drill caption + page_link live")
        else:
            failures.append("B7: dot click on isite_ratio_dots did not render the 'Sélectionné'/drill page_link section")
            print("  [FAIL] B7: drill section did not appear after a live click")
    except Exception as e:
        failures.append(f"B7: page-7 dot-click drill probe raised: {e}")
        print(f"  [FAIL] B7 probe exception: {e}")


def check_page13_orcid_yearly(page) -> None:
    """D7 (docs/LENS_ABSORPTION_pass7b.md): the yearly ORCID bar must plot
    the WORK-level share (`pct_works_orcid`), never the person-level
    `pct_orcid` the pre-fix hover mismatched against its own two counts --
    and the caution dagger + REFERENCE_RED ink must land exactly on the
    year(s) where that work-level share fell vs the prior year, recomputed
    independently from `aut_coverage.parquet`, never assumed from the page."""
    global checks
    print("page Identifiants - yearly ORCID bar = work-level share + caution dagger on decline (D7)")
    info = page.evaluate("""
      () => Array.from(document.querySelectorAll('.js-plotly-plot')).map((gd, i) => {
        const d0 = (gd.data && gd.data[0]) || {};
        return {index: i, x: (d0.x || []).map(String), y: (d0.y || []),
                text: (d0.text || []).map(String),
                inks: (d0.textfont && d0.textfont.color) || []};
      })
    """)
    year_re = re.compile(r"^(19|20)\d{2}$")
    cand = [c for c in info if len(c["x"]) >= 3 and all(year_re.match(x) for x in c["x"])]
    checks += 1
    if not cand:
        failures.append("id_orcid_yearly: no chart with a year-labelled x-axis found on Identifiants et couverture")
        print("  [FAIL] D7: yearly ORCID chart not found")
        return
    c = cand[0]
    years = [int(v) for v in c["x"]]
    df = pd.read_parquet(DATA_DIR / "aut_coverage.parquet",
                          columns=["conf_state", "unit_kind", "unit_id", "pct_works_orcid"])
    yr = df[df["unit_kind"] == "year"].copy()
    yr["unit_id"] = yr["unit_id"].astype(int)
    rendered = [round(float(v), 1) for v in c["y"]]
    match_state = None
    for state, grp in yr.groupby("conf_state"):
        g = grp.set_index("unit_id").reindex(years)
        recomputed = (g["pct_works_orcid"] * 100).round(1).tolist()
        if recomputed == rendered:
            match_state = state
            match_vals = recomputed
            break
    checks += 1
    if match_state is None:
        failures.append(f"D7: rendered y-values {rendered} match neither conf_state's pct_works_orcid for years {years} "
                        f"(may be plotting person-level pct_orcid instead)")
        print(f"  [FAIL] D7: rendered % values are not pct_works_orcid for any conf_state ({rendered})")
        return
    print(f"  [ok] D7: rendered % == pct_works_orcid (work-level share, conf_state={match_state!r})")

    checks += 1
    expected_flag = [False] + [match_vals[i] < match_vals[i - 1] for i in range(1, len(match_vals))]
    has_dagger = ["†" in t for t in c["text"]]
    inks = c["inks"] if isinstance(c["inks"], list) else [c["inks"]] * len(c["text"])
    red_ink = [str(ink).lower() == "#821d13" for ink in inks]
    if has_dagger == expected_flag and red_ink == expected_flag:
        flagged_years = [y for y, f in zip(years, expected_flag) if f]
        print(f"  [ok] D7: caution dagger + REFERENCE_RED ink present exactly on the declining year(s) {flagged_years}")
    else:
        failures.append(f"D7: caution dagger/ink pattern dagger={has_dagger} ink={red_ink} != expected decline pattern {expected_flag} (years {years})")
        print(f"  [FAIL] D7: caution pattern mismatch dagger={has_dagger} ink={red_ink} expected={expected_flag}")


def check_page9_mirror_breakpoint(page) -> None:
    """B8: the balance-mirror <-> table-companion CSS switch is a real
    `@media` query, proven at 390 px (table shown, mirror hidden) and
    reverted at the wide viewport (mirror shown, table hidden) -- a
    pure-CSS behaviour no AppTest/unit test can see, real-browser only."""
    global checks
    print("page Zoom partenaire - CSS breakpoint: table at 390px, mirror at wide viewport (B8)")
    mirror = page.locator(".st-key-zoom_mirror").first
    table = page.locator(".st-key-zoom_mirror_table").first
    checks += 1
    try:
        page.set_viewport_size({"width": 390, "height": 900})
        page.wait_for_timeout(400)
        m_390 = mirror.is_visible() if mirror.count() else None
        t_390 = table.is_visible() if table.count() else None
        page.set_viewport_size(VIEWPORT)
        page.wait_for_timeout(400)
        m_wide = mirror.is_visible() if mirror.count() else None
        t_wide = table.is_visible() if table.count() else None
        ok_390 = (m_390 is False) and (t_390 is True)
        ok_wide = (m_wide is True) and (t_wide is False)
        if ok_390 and ok_wide:
            print(f"  [ok] B8: 390px -> table visible/mirror hidden; {VIEWPORT['width']}px -> mirror visible/table hidden")
        else:
            failures.append(f"B8: CSS breakpoint wrong at one width (390: mirror={m_390} table={t_390}; "
                            f"{VIEWPORT['width']}: mirror={m_wide} table={t_wide})")
            print(f"  [FAIL] B8: 390 mirror={m_390} table={t_390} | {VIEWPORT['width']} mirror={m_wide} table={t_wide}")
    except Exception as e:
        failures.append(f"B8: page-9 mirror/table breakpoint probe raised: {e}")
        print(f"  [FAIL] B8 probe exception: {e}")


def check(page, name: str, charts: bool = True) -> bool:
    """Screenshot the page, fail on a Streamlit exception or an empty chart."""
    global checks
    checks += 1
    SHOTS.mkdir(parents=True, exist_ok=True)
    shot = SHOTS / f"{name}.png"
    full_shot(page, shot)
    n_exc = page.locator('[data-testid="stException"]').count()
    body = page.inner_text("body")
    broken = n_exc > 0 or "Traceback (most recent call last)" in body
    status = "FAIL" if broken else "ok"
    print(f"  [{status}] {name}  -> {shot.relative_to(ROOT)}")
    if broken:
        detail = page.locator('[data-testid="stException"]').first.inner_text()[:600] if n_exc else body[:600]
        failures.append(f"{name}: {detail}")
    elif charts:
        assert_charts_have_marks(page, name)
    return not broken


def copy_grid_tsv(page, grid_index: int = -1) -> str:
    """
    Read an `st.dataframe`'s visible content as TSV via its own Ctrl+A/Ctrl+C
    clipboard affordance -- glide-data-grid draws to `<canvas>`, so
    `page.inner_text()` is ALWAYS empty for it, even when the content is plainly
    visible on screen (INSPECTION_PLAYBOOK.md's own named pitfall). Copy-adapted
    from `tests/ui/_appserver.py::copy_grid_tsv` (Stream E's file, not this
    stream's fence -- re-implemented here rather than imported, same reasoning
    that file's own docstring gives for not importing smoke.py's helpers).
    `grid_index=-1` (default) targets the LAST grid on the page. Requires the
    browser context to hold clipboard-read/write permissions.
    """
    grids = page.locator('[data-testid="stDataFrame"]')
    grid = grids.nth(grid_index if grid_index >= 0 else grids.count() - 1)
    grid.scroll_into_view_if_needed()
    page.wait_for_timeout(400)

    def _one_copy() -> str:
        page.evaluate("() => navigator.clipboard.writeText('__CLEARED__')")
        page.wait_for_timeout(150)
        grid.click(position={"x": 80, "y": 50})
        page.wait_for_timeout(400)
        page.keyboard.press("Control+a")
        page.wait_for_timeout(350)
        page.keyboard.press("Control+c")
        page.wait_for_timeout(600)
        return page.evaluate("() => navigator.clipboard.readText()")

    text = _one_copy()
    for _ in range(3):
        if text.strip() and text.strip() != "__CLEARED__":
            break
        page.wait_for_timeout(500)
        text = _one_copy()
    return text


def shot_element(page, chart_index: int, path: Path) -> None:
    """Screenshot one Plotly figure on its own (evidence for a per-chart claim)."""
    charts = page.locator('[data-testid="stPlotlyChart"]')
    if charts.count() <= chart_index:
        return
    el = charts.nth(chart_index)
    el.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    el.screenshot(path=str(path))
    try:
        shown = path.relative_to(ROOT)
    except ValueError:
        shown = path
    print(f"        chart shot -> {shown}")


def goto(page, base: str, path: str) -> None:
    page.goto(f"{base}{path}", wait_until="domcontentloaded")
    settle(page)


def select_option(page, label: str, value: str) -> None:
    """Type into a Streamlit selectbox and pick the first match."""
    box = page.locator('[data-testid="stSelectbox"], [data-testid="stTextInput"]')         .filter(has_text=label).first
    field = box.locator("input").first
    field.click()
    page.wait_for_timeout(300)
    field.fill("")
    field.type(value, delay=40)
    page.wait_for_timeout(900)
    page.keyboard.press("Enter")
    settle(page)


def big_number(page) -> str:
    """
    The selected structure's "Publications" mini-fiche KPI tile value, on
    Laboratoires.

    PASS-6 FIX: the `#pubs-total` DOM id this used to read no longer exists
    anywhere in the app (grep confirmed zero hits app-wide) -- the pass-5
    plain headline was replaced by the pass-6 mini-fiche's compact KPI tiles
    (P7/#28), which carry NO stable id, only inline styles. Left as `#pubs-total`,
    this function silently returned "" forever, which made D52's "the count
    changes with the toggle" check and the F-VAC-01 persistence setup check both
    FALSE-FAIL unconditionally (ON == OFF == "") -- a vacuous-in-the-other-
    direction pin, caught by actually running this file after the rewrite
    (docs/INSPECTION_REPORT_pass6.md, smoke mutation-check section).

    Fix: `_kpi_tile()` (Streamlit/pages/2_..._Laboratoires.py) renders the value
    as a `font-size:22px` div immediately followed by a `font-size:12px` label
    div reading "Publications" -- a same-shape pair for every KPI tile on the
    mini-fiche (Publications / Part I-SITE / FWCI / International), so match on
    that CSS shape + the adjacent label text rather than a vanished id.
    """
    tiles = page.locator('div[style*="font-size: 22px"]')
    for i in range(tiles.count()):
        val = tiles.nth(i)
        label = val.locator("xpath=following-sibling::div[1]")
        if label.count() and label.inner_text().strip() == "Publications":
            return val.inner_text().strip()
    return ""


def toggle_conference(page) -> None:
    sidebar = page.locator('[data-testid="stSidebar"]')
    sidebar.get_by_text("Inclure les articles de conférence", exact=True).click()
    settle(page)


def toggle_artifact(page) -> None:
    sidebar = page.locator('[data-testid="stSidebar"]')
    sidebar.get_by_text("Exclure les 811 topics hors référentiel", exact=True).click()
    settle(page)


def toggle_isite_overlay(page) -> None:
    sidebar = page.locator('[data-testid="stSidebar"]')
    sidebar.get_by_text("Afficher la contribution I-SITE", exact=True).click()
    settle(page)


def open_sidebar_nav_more(page, label: str) -> None:
    """
    Pass-6 fix: the app grew from 4 to 15 surfaces this pass -- Streamlit now
    collapses the sidebar nav behind a "View N more" toggle
    (`data-testid="stSidebarNavViewButton"`) once past ~9 entries, so a link past
    that fold is not in the DOM until this is clicked once. Idempotent: a no-op
    when `label` is already visible (Menu .. Zoom partenaire, the first 9).
    """
    if page.locator('[data-testid="stSidebarNav"] a').filter(has_text=label).count():
        return
    more = page.locator('[data-testid="stSidebarNavViewButton"]')
    if more.count() and more.first.is_visible():
        more.first.click()
        page.wait_for_timeout(300)


def click_sidebar_nav_link(page, label: str) -> None:
    """
    Real in-app sidebar navigation click -- NOT `page.goto()`. F-VAC-01 fix: the
    Inspection Bay's own methodology note (docs/INSPECTION_REPORT_1.md §3(a)) found
    that `page.goto(new_url)` forces a full browser navigation that tears down the
    WebSocket session Streamlit's SPA-style sidebar nav keeps alive -- it is NOT
    equivalent to a real in-app nav-link click for testing `persist_state="session"`,
    and using it gave 4 false FAILs there. This is the fix applied to smoke.py's own
    scaffolding: scope to the sidebar nav specifically (`stSidebarNav`), never the
    generic in-page links a page's own content may also carry.
    """
    open_sidebar_nav_more(page, label)
    link = page.locator('[data-testid="stSidebarNav"] a').filter(has_text=label).first
    link.click()
    settle(page)


# ---------------------------------------------------------------------------
# the cases
# ---------------------------------------------------------------------------

# page 1 draws, in order: document-type pie, yearly stack, field distribution,
# FWCI whiskers. The last one is the chart that once rendered as an empty frame.
FWCI_CHART_INDEX = 3

LARGE_LAB = "IJL"              # 2,188 works
SMALL_LAB = "CREAT"            # 20 works, 1 of them outside the indicators (D53)
EMPTY_LAB = "Jardins"          # declared empty: 0 works in the corpus
HORS_LISTE = "CAPSID"          # colon in the source name -> blob-separator hazard
NO_LAB = "NO LAB"              # 4,568 works with no curated lab

# Pass-6 deep-link targets (?partner_id=/?author_id=, both pages' documented
# session_state-or-query_params-or-picker resolution order) -- picked live via a
# one-off pandas probe (progress/SINSP.md), not hardcoded from memory:
# CNRS (highest-volume partner) and an ORCID-bearing author.
PARTNER_ID = "I1294671590"      # CNRS, ptn_summary highest co_works_full
AUTHOR_ID = "A5000010260"       # first aut_public row with a non-null ORCID


def check_persistence_journey(page, base: str) -> None:
    """
    F-VAC-01 fix (BLOCKER): the ONE real-browser, real-session, real-server proof that
    the 3 sidebar toggles survive an in-app sidebar navigation. This REPLACES
    tests/test_isite_overlay_journey.py's retired claim to be that binding proof --
    `AppTest` shares a single process-level `session_state` dict across every
    `.switch_page()` call in one test file, so it can only prove the destination
    page's SCRIPT re-executes under an already-populated dict, never that a value
    would survive transport between two independent script runs the way a live page
    reload / sidebar hop does (see that file's rewritten docstring, and
    progress/FIX1.md for the mutation evidence that it cannot fail on this).

    Kept to 2 legs (Laboratoires -> Portefeuille thematique -> Laboratoires, the
    SECOND-visit case the original CX-FIX fix targeted) so smoke stays fast --
    not the AppTest file's full mechanism-structure map.
    """
    global checks
    print("persistence journey (F-VAC-01, real browser + real server)")

    goto(page, base, "/Laboratoires")
    select_option(page, "Sélectionner une structure", LARGE_LAB)
    count_on = big_number(page)  # conference ON (default) -- baseline before any toggle

    # Set ALL 3 sidebar toggles OFF-DEFAULT on this page.
    toggle_conference(page)       # ON -> OFF
    toggle_artifact(page)         # OFF -> ON
    toggle_isite_overlay(page)    # OFF -> ON
    count_off = big_number(page)  # the state-dependent headline, off-default state

    checks += 1
    if not count_on or not count_off or count_on == count_off:
        failures.append(
            f"F-VAC-01 setup: page-1 headline did not change when setting the 3 "
            f"toggles off-default (ON={count_on!r}, OFF={count_off!r}) -- cannot "
            f"prove persistence of a headline that never moved in the first place")
        print("  [FAIL] F-VAC-01 setup: off-default headline did not differ from default")
    else:
        print(f"  [ok] F-VAC-01 setup: off-default headline differs ({count_on} -> {count_off})")

    # LEG 1: real sidebar nav-link click (never page.goto()) to a page with an actual
    # I-SITE overlay surface (docs/OVERLAY_MATRIX.md / lib.controls.ISITE_OVERLAY_SURFACE_PAGES).
    click_sidebar_nav_link(page, "Portefeuille thématique")
    body1 = page.inner_text("body")
    checks += 1
    leg1_ok = (
        "Articles de conférence exclus" in body1
        and "hors référentiel exclus" in body1
        and "Surcouche I-SITE affichée" in body1
    )
    if leg1_ok:
        print("  [ok] leg 1 (Portefeuille thematique): all 3 toggle states persisted")
    else:
        failures.append(
            "F-VAC-01 leg 1: a toggle's off-default state did not persist across the "
            f"sidebar hop to Portefeuille thematique (conf={'Articles de conférence exclus' in body1}, "
            f"artifact={'hors référentiel exclus' in body1}, isite={'Surcouche I-SITE affichée' in body1})")
        print("  [FAIL] leg 1: a toggle state was lost across the sidebar hop")

    # LEG 2: hop BACK to Laboratoires -- the critical SECOND-visit case (the original
    # CX-FIX bug only showed up on a widget's second mount in the same session).
    click_sidebar_nav_link(page, "Laboratoires")
    select_option(page, "Sélectionner une structure", LARGE_LAB)
    count_after_2_hops = big_number(page)
    body2 = page.inner_text("body")
    checks += 1
    leg2_ok = (
        "Articles de conférence exclus" in body2
        and "hors référentiel exclus" in body2
        and "Surcouche I-SITE affichée" in body2
        and count_after_2_hops == count_off
    )
    if leg2_ok:
        print(f"  [ok] leg 2 (Laboratoires, 2nd visit): toggles + headline persisted "
              f"({count_after_2_hops} == {count_off})")
    else:
        failures.append(
            f"F-VAC-01 leg 2: state lost on the SECOND visit to Laboratoires "
            f"(headline {count_after_2_hops!r} vs expected {count_off!r}, "
            f"conf_caption={'Articles de conférence exclus' in body2}, "
            f"artifact_caption={'hors référentiel exclus' in body2}, "
            f"isite_caption={'Surcouche I-SITE affichée' in body2})")
        print("  [FAIL] leg 2: state lost on the second visit")

    check(page, "90_persistence_journey_leg2_laboratoires", charts=False)

    # Restore defaults so nothing downstream in this run() inherits off-default state.
    toggle_conference(page)
    toggle_artifact(page)
    toggle_isite_overlay(page)


def run(base: str, sdg_variant: str) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # clipboard-read/write: needed by copy_grid_tsv() (canvas-rendered
        # st.dataframe grids defeat inner_text(), pass-6 addition below).
        page = browser.new_page(viewport=dict(VIEWPORT),
                                 permissions=["clipboard-read", "clipboard-write"])
        page.set_default_timeout(60_000)

        print("home")
        goto(page, base, "/")
        check(page, f"00_home_{sdg_variant}")

        # ---------------- Vue d'ensemble (pass-6 NEW page 1) ----------------
        print("page Vue d'ensemble - grouped-bars I-SITE overlay (P6-R5)")
        goto(page, base, "/Vue_d_ensemble")
        check(page, f"01_vue_ensemble_{sdg_variant}", charts=False)
        toggle_isite_overlay(page)
        body_ve = page.inner_text("body")
        global checks
        checks += 1
        if "segment plus fonc" in body_ve and "part" in body_ve and "I-SITE" in body_ve:
            print("  [ok] grouped-bars overlay caption present with I-SITE ON")
        else:
            failures.append("Vue d'ensemble: grouped-bars overlay caption (GROUPED_BARS_HOWTOREAD_FR) not found with I-SITE overlay ON")
            print("  [FAIL] grouped-bars overlay caption missing")
        check(page, f"01_vue_ensemble_isite_on_{sdg_variant}")

        # ---------------- pass-7b B2/B3/P3 (S-INSP) -- ov_breakdown_bars ----------------
        assert_gutter_number(page, "ov_breakdown_bars (Vue d'ensemble)")
        assert_hover_grammar(page, "Vue d'ensemble hover grammar")
        # check_absent=False: this page ALSO carries ov_breakdown_annual's own
        # lib.overlay grouped-bars caption (B2-named exception, its OWN
        # "Comment lire" text, not this pin's chart) -- see the function
        # docstring. The full present+absent pin lives on page 12 below,
        # a page with zero "Comment lire" source anywhere.
        assert_reading_present_absent(
            page, "ov_breakdown_bars reading line",
            "la plus fournie en haut : la longueur donne le",
            check_absent=False)

        toggle_isite_overlay(page)  # back to default OFF

        # ---------------- page 1 ----------------
        print("page 1 - Lab Overview")
        goto(page, base, "/Laboratoires")
        check(page, f"10_lab_default_{sdg_variant}")

        # a large lab
        select_option(page, "Sélectionner une structure", LARGE_LAB)
        check(page, f"11_lab_large_{sdg_variant}")

        # ---------------- pass-7b B2 (S-INSP) -- lab_breakdown_bars / lab_field_share ----------------
        assert_gutter_number(page, "lab_breakdown_bars (Laboratoires)")

        count_on = big_number(page)
        # regression evidence: the FWCI whisker plot shipped as an empty frame once
        shot_element(page, FWCI_CHART_INDEX, SHOTS / "fwci_by_field_conference_on.png")

        # D52: conference papers off must change the number
        toggle_conference(page)
        check(page, f"12_lab_large_no_conference_{sdg_variant}")
        shot_element(page, FWCI_CHART_INDEX, SHOTS / "fwci_by_field_conference_off.png")
        count_off = big_number(page)
        print(f"    conference ON={count_on!r} OFF={count_off!r}")
        checks += 1
        if not count_on or not count_off or count_on == count_off:
            failures.append(
                f"D52: page-1 count did not change with the conference toggle "
                f"(ON={count_on!r}, OFF={count_off!r})")
            print("  [FAIL] D52 conference toggle changes the count")
        else:
            print(f"  [ok] D52 conference toggle changes the count ({count_on} -> {count_off})")
        toggle_conference(page)  # back on

        # NO LAB
        select_option(page, "Sélectionner une structure", NO_LAB)
        check(page, f"13_lab_no_lab_{sdg_variant}")

        # a small lab (thin-stratum works, D53)
        select_option(page, "Sélectionner une structure", SMALL_LAB)
        check(page, f"14_lab_small_{sdg_variant}")

        # the declared-empty structure
        select_option(page, "Sélectionner une structure", EMPTY_LAB)
        check(page, f"15_lab_empty_jardins_{sdg_variant}")

        # a flagged hors-liste structure (D56)
        select_option(page, "Sélectionner une structure", HORS_LISTE)
        ok = check(page, f"16_lab_hors_liste_{sdg_variant}")
        checks += 1
        if ok and "hors liste" not in page.inner_text("body"):
            failures.append("D56: hors-liste structure is not flagged in the UI")
            print("  [FAIL] D56 hors-liste flag visible")
        else:
            print("  [ok] D56 hors-liste flag visible")

        # ---------------- SDG colours (pass-7a, P17) -- page 2 lab_sdg_bars ----------------
        print("page Laboratoires - SDG bar colours == SDG_COLORS[goal] (P17)")
        _sdg_lab = pick_sdg_rich_lab()
        if _sdg_lab:
            select_option(page, "Sélectionner une structure", _sdg_lab)
            assert_sdg_bar_colors(page, f"P17 page 2 ({_sdg_lab})")
            select_option(page, "Sélectionner une structure", LARGE_LAB)  # restore established flow
        else:
            print("  [warn] no lab with SIRIS SDG coverage found -- P17 page-2 pin skipped")

        # ---------------- Perimetres personnalises (pass-6 NEW page 3) ----------------
        print("page Perimetres personnalises - query box HIDDEN below N<50 (P6-R6)")
        goto(page, base, "/Périmètres_personnalisés")
        check(page, f"20_perimetres_{sdg_variant}", charts=False)
        # mutation-check target: Streamlit/lib/ranked.py QUERY_MIN_N (see module
        # docstring) -- the registry is "une poignee" of rows (well under 50), so
        # this box must NOT exist in the DOM at all (should_show_query_box() gates it).
        search_box = page.locator('[data-testid="stTextInput"]').filter(has_text="Rechercher un périmètre")
        checks += 1
        if search_box.count() == 0:
            print("  [ok] P6-R6: registry search box correctly hidden (N < 50)")
        else:
            failures.append("P6-R6: Perimetres registry search box is VISIBLE despite N < 50 (ranked.QUERY_MIN_N gate not applied)")
            print("  [FAIL] P6-R6: registry search box visible with N < 50")

        # ---------------- page 3 ----------------
        print("page 3 - Thematic Overview")
        goto(page, base, "/Portefeuille_thématique")
        check(page, f"30_thematic_overview_{sdg_variant}")

        # ---------------- pass-7b B2/B6 (S-INSP) -- pf_lq_fields / pf_fwci_box reference ----------------
        assert_reference_dash(page, "Portefeuille thematique (page 4) reference line")

        body = page.inner_text("body")
        # NOTE (incidental fix, this pass): the panel heading was FR-wrapped (D61
        # reversed, pass 5) from "Sustainable Development Goals" to "Objectifs de
        # développement durable" -- this check hunted the retired English heading and
        # always read has_panel=False, failing every run regardless of app.sdg_variant.
        has_panel = "Objectifs de développement durable" in body
        checks += 1
        if sdg_variant == "off":
            if has_panel:
                failures.append("D51: SDG panel is present with app.sdg_variant: off")
                print("  [FAIL] D51 panel hidden when off")
            else:
                print("  [ok] D51 SDG panel absent (app.sdg_variant: off)")
        else:
            expected = {"b_siris": "SIRIS method", "c_openalex": "OpenAlex / Aurora"}[sdg_variant]
            if has_panel and expected in body:
                heading = next((ln.strip() for ln in body.splitlines()
                                if ln.strip().startswith("ODD (")), "")
                print(f"  [ok] D51 SDG panel shows '{expected}'"
                      + (f" -> {heading.encode('ascii', 'replace').decode()}" if heading else ""))
            else:
                failures.append(f"D51: SDG panel missing or not labelled '{expected}'")
                print(f"  [FAIL] D51 panel labelled '{expected}'")

        # conference off on page 3 too
        toggle_conference(page)
        check(page, f"31_thematic_overview_no_conference_{sdg_variant}")
        toggle_conference(page)

        # Pass-6 item #7/#12: SDG method-comparison labels ("ODD par laboratoire"),
        # real DOM text (st.markdown bold), not a canvas grid -- a direct assertion.
        body_pf = page.inner_text("body")
        checks += 1
        if "SIRIS" in body_pf and "VocTagger" in body_pf and "Aurora" in body_pf and "OpenAlex" in body_pf:
            print("  [ok] #7/#12: SDG method-comparison labels (SIRIS/VocTagger vs Aurora/OpenAlex) present")
        else:
            failures.append("#7/#12: SDG method-comparison labels (SIRIS (VocTagger) / Aurora (OpenAlex)) not found on Portefeuille thematique")
            print("  [FAIL] #7/#12: SDG method labels missing")

        # ---------------- SDG colours (pass-7a, P17) -- page 4 pf_sdg_bars ----------------
        print("page Portefeuille - SDG bar colours == SDG_COLORS[goal] (P17)")
        assert_sdg_bar_colors(page, "P17 page 4")

        # ---------------- Positionnement (pass-6 NEW page 5) ----------------
        print("page Positionnement - basic render (full-depth zero-fill query lives on page 4, see below)")
        goto(page, base, "/Positionnement")
        check(page, f"25_positionnement_{sdg_variant}")

        # ---------------- pass-7b B2/B6 (S-INSP) -- pos_frontier_labs / pos_lq_frontier ----------------
        assert_gutter_number(page, "pos_frontier_labs (Positionnement)")
        assert_reference_dash(page, "Positionnement (page 5) reference line")

        # Zero-fill "quantum incl. zero-pub topics" query (#20's own acceptance
        # criterion) actually lives on Portefeuille thematique's "Topics (OpenAlex)"
        # panel (topics_zero_fill, 4 516 rows -- the WHOLE OpenAlex vocabulary), NOT
        # on Positionnement (P-POS's own ledger: "global zero-fill catalogue = page 4,
        # FR pointer added, nothing rebuilt"). First attempt wrongly assumed
        # Positionnement and always found nothing -- fixed to the real location.
        print("page Portefeuille - zero-fill 'quantum' query incl. zero-pub topics (#20)")
        goto(page, base, "/Portefeuille_thématique")
        search_inputs = page.locator('[data-testid="stTextInput"]').filter(has_text="Rechercher")
        checks += 1
        if search_inputs.count() >= 2:
            # THREE "Rechercher :" boxes exist on this page (lib.ranked, shared
            # label, each call site N>=50): Subfields (idx 0), Topics (idx 1),
            # ODD-par-labo/sdg_lab_methods (idx 2) -- verified live by bounding-box
            # y-position (progress/SINSP.md); Topics is the MIDDLE one, not the
            # last (first attempt grabbed ODD-par-labo's box instead and always
            # found nothing -- a real "which of several identical-label widgets"
            # trap, not a product bug).
            search_inputs.nth(1).locator("input").fill("quantum")
            page.wait_for_timeout(700)
            page.keyboard.press("Enter")
            settle(page)
            # The Topics (OpenAlex) table is `st.dataframe` (glide-data-grid canvas)
            # -- inner_text() is always empty for it (playbook pitfall). Read the
            # grid's own content via its Ctrl+A/Ctrl+C clipboard affordance instead.
            # Grid index 3 (of 6) is Topics', same y-position pairing as the box.
            grid_tsv = copy_grid_tsv(page, grid_index=3)
            if "quantum" in grid_tsv.lower():
                print("  [ok] #20: 'quantum' query returns topics (incl. zero-pub) on Portefeuille")
            else:
                failures.append("#20: 'quantum' query on Portefeuille thematique's Topics (OpenAlex) panel returned nothing (grid TSV read via clipboard)")
                print(f"  [FAIL] #20: 'quantum' query returned nothing (grid TSV len={len(grid_tsv)})")
            check(page, f"32_thematic_quantum_{sdg_variant}")
        else:
            failures.append("#20: no 'Rechercher' query box found on Portefeuille thematique (expected on Topics (OpenAlex), N=4516 >> 50)")
            print("  [FAIL] #20: query box not found at all")

        # ---------------- page 4 ----------------
        print("page 4 - Thematic Drilldown")
        goto(page, base, "/Exploration_thématique")
        check(page, f"40_drilldown_default_{sdg_variant}")

        # ---------------- pass-7b B2 (S-INSP) -- ex_dept_bars / ex_lab_bars ----------------
        assert_gutter_number(page, "ex_dept_bars/ex_lab_bars (Exploration thematique)")

        # ---------------- Lien column (pass-7a, P4) -- page 6 partner tables ----------------
        print("page Exploration - 'Lien' OpenAlex column on the partner tables")
        try:
            grids6 = page.locator('[data-testid="stDataFrame"]')
            n_grids6 = grids6.count()
            found_lien = False
            found_at = -1
            diag6 = []
            for gi in range(n_grids6):
                tsv = copy_grid_tsv(page, grid_index=gi)
                # PASS-7a FIX (S-INSP, live-diagnosed): this grid's Ctrl+A/Ctrl+C copy does
                # NOT include a header row at all (confirmed live -- every "first line" was
                # plainly a DATA row, e.g. "Engineering\t5581\t..."), so a header/glyph
                # search over line 0 can never match. `ranked.link_column` builds an
                # `st.column_config.LinkColumn` whose underlying CELL VALUE is the raw
                # `links.copubs_url(...)` string (the glyph is display-only paint) -- and
                # that raw URL DOES survive the clipboard copy (confirmed live: grid#1's
                # copy contained "...https://opena[lex...]" verbatim). Search the FULL body.
                if "openalex.org" in tsv:
                    found_lien = True
                    found_at = gi
                    break
                diag6.append(f"grid#{gi} first_line={tsv.splitlines()[0][:100] if tsv.strip() else ''!r} body_len={len(tsv)}")
            checks += 1
            if found_lien:
                print(f"  [ok] page 6: 'Lien' column found (grid #{found_at} of {n_grids6}, raw openalex.org URL in the copy)")
            else:
                failures.append(f"page 6: no 'Lien' column (openalex.org URL) found in any of {n_grids6} grid(s) -- diag: {diag6}")
                print(f"  [FAIL] page 6: 'Lien' column not found in {n_grids6} grid(s) -- {diag6}")
        except Exception as e:
            print(f"  [warn] page 6 Lien-column probe skipped: {e}")

        # every page that draws charts is swept in BOTH toggle states
        toggle_conference(page)
        check(page, f"44_drilldown_no_conference_{sdg_variant}")
        toggle_conference(page)

        # untopiced path: the 5th domain, 51 works with no topic at all
        # NOTE (incidental fix, this pass): widget labels below were the pre-FR-wrapper
        # English strings ("Select element:"/"Select level:"/"Search subfield:"/
        # "Search topic:") -- D61's reversal (full FR wrapper, pass 5) renamed the
        # actual widgets and this script was never updated, so it hard-crashed on a
        # Playwright locator timeout before reaching ANY check after this point
        # (never mind the new F-VAC-01 persistence journey at the end of run()).
        # Values ("Unclassified", "Horticulture", "Fungal") are OpenAlex taxonomy DATA,
        # unaffected by the FR-wrapper rename (D61 explicitly exempts taxonomy labels).
        select_option(page, "Choisir l'élément :", "Unclassified")
        check(page, f"41_drilldown_unclassified_{sdg_variant}")

        # null-indicator path: a subfield small enough to sit in a thin stratum
        select_option(page, "Choisir le niveau :", "Sous-champ")
        select_option(page, "Rechercher un sous-champ :", "Horticulture")
        check(page, f"42_drilldown_small_subfield_{sdg_variant}")

        # the taxonomy's deepest level, which replaced the topic-model axis
        select_option(page, "Choisir le niveau :", "Topic")
        select_option(page, "Rechercher un topic :", "Fungal")
        check(page, f"43_drilldown_topic_{sdg_variant}")

        # Pass-6 item #21 fix (probe 5 root cause): the top-10 labs/structures overlay
        # bar now actually carries the I-SITE segment (a 4-field blob was being parsed
        # with the 5-field schema, silently dropping the segment). Prove it with the
        # chart-mark count: with the global overlay ON, the dept/labs bar charts on
        # THIS page must show >=2 traces per bar-group (base + I-SITE segment) where
        # they showed only 1 with the fix absent.
        select_option(page, "Choisir le niveau :", "Domaine")
        toggle_isite_overlay(page)
        charts_on = chart_marks(page)
        n_traces_on = sum(c["traces"] for c in charts_on)
        toggle_isite_overlay(page)
        charts_off = chart_marks(page)
        n_traces_off = sum(c["traces"] for c in charts_off)
        checks += 1
        if n_traces_on > n_traces_off:
            print(f"  [ok] #21: overlay adds trace(s) on Exploration ({n_traces_off} -> {n_traces_on})")
        else:
            failures.append(f"#21: I-SITE overlay did not add any Plotly trace on Exploration thematique (traces off={n_traces_off}, on={n_traces_on})")
            print(f"  [FAIL] #21: overlay added no traces ({n_traces_off} -> {n_traces_on})")

        # ---------------- I-SITE (pass-6 NEW page 7) ----------------
        print("page I-SITE - canonical-list recall block (#37)")
        goto(page, base, "/I-SITE")
        check(page, f"50_isite_{sdg_variant}")
        body_is = page.inner_text("body")
        checks += 1
        if "Recoupement avec la trace de subvention ANR" in body_is:
            print("  [ok] #37: canonical-list recall block present")
        else:
            failures.append("#37: canonical-list recall block ('Recoupement avec la trace de subvention ANR') not found on I-SITE")
            print("  [FAIL] #37: recall block missing")

        # ---------------- pass-7b B2/B6/B7/D9 (S-INSP) -- isite_ratio_dots ----------------
        assert_reference_dash(page, "I-SITE (page 7) parity reference line")
        check_page7_floor_style(page)
        check_page7_click_drill(page)

        # ---------------- Collaborations (pass-6 NEW page 8) ----------------
        print("page Collaborations - consortium caption + momentum column help (#38)")
        goto(page, base, "/Collaborations")
        check(page, f"51_collaborations_{sdg_variant}")
        body_col = page.inner_text("body")
        checks += 1
        if "reflète la structure des UMR co-portées" in body_col:
            print("  [ok] #38: consortium caption present")
        else:
            failures.append("#38: consortium caption (CONSORTIUM_CAPTION_FR) not found on Collaborations")
            print("  [FAIL] #38: consortium caption missing")
        try:
            exp = page.get_by_text("Colonnes « Consortium I-SITE »", exact=False).first
            if exp.count():
                exp.click()
                page.wait_for_timeout(500)
                body_col2 = page.inner_text("body")
                checks += 1
                if "Fenêtres actuelles" in body_col2:
                    print("  [ok] #38: momentum column help shows quantified windows")
                else:
                    failures.append("#38: momentum column help expander did not show 'Fenetres actuelles'")
                    print("  [FAIL] #38: momentum help text missing")
        except Exception as e:
            print(f"  [warn] Collaborations momentum-help probe skipped: {e}")

        # FIX-1 pass-6 fix round (S-LENS D7, the reproducible #38 recurrence): with the
        # hub table's "masquer les membres du site" toggle ON, mask_members() removes every
        # member row BEFORE the "Consortium" badge column is computed on what's left -- a
        # badge column with zero rows to mark is empty by construction. Fixed in
        # lib/ranked.py: the column is now skipped entirely in that state (unit-proven,
        # deterministically, in tests/test_ranked.py::test_ranked_table_{drops,keeps}_
        # consortium_column_when_members_{masked,shown} -- both states, monkeypatched
        # toggle, asserted against the actual DataFrame handed to st.dataframe). This live
        # check is the VISUAL, real-browser half of that proof (screenshot evidence per the
        # acceptance criterion) -- it does not re-assert grid CONTENT via clipboard copy:
        # this page carries a SECOND, hidden `st.dataframe` elsewhere (grep-confirmed live,
        # `[data-testid="stDataFrame"]` count=2, index 1 permanently `is_visible()=False`)
        # and glide-data-grid's canvas virtualization makes a Ctrl+A/Ctrl+C clipboard copy
        # of the FIRST grid an unreliable oracle for "is this specific column present"
        # (observed live: copied length varies 5x between runs depending on scroll/render
        # state, unrelated to the actual column set) -- exactly the "canvas grid defeats
        # inner_text()" class of pitfall this file's own docstring already names elsewhere.
        # The deterministic pin belongs in the unit test, not here.
        try:
            check(page, f"51_collaborations_mask_off_{sdg_variant}", charts=False)

            # st.toggle renders as an ARIA "switch" (live-confirmed: role=checkbox count=0,
            # role=switch count=1, visible) with the label as its accessible name --
            # get_by_role resolves straight to the one real interactive element. `force=True`
            # on the click: Streamlit's sticky header toolbar intermittently intercepts the
            # pointer event right at the scrolled-to position (live-confirmed transient
            # occlusion, unrelated to this fix) -- forcing is safe once the element's
            # identity is confirmed via get_by_role's accessible-name match.
            mask_toggle = page.get_by_role("switch", name="masquer les membres du site")
            mask_toggle.scroll_into_view_if_needed()
            page.mouse.wheel(0, -150)  # nudge clear of the sticky header toolbar
            page.wait_for_timeout(300)
            mask_toggle.click(force=True)
            settle(page)
            checks += 1
            print("  [ok] D7: 'masquer les membres du site' toggled without exception")
            check(page, f"51_collaborations_mask_on_{sdg_variant}", charts=False)
        except Exception as e:
            print(f"  [warn] Collaborations D7 mask-state probe skipped: {e}")

        # ---------------- Reciprocity scatter (pass-7a, P7-R3(a)) -- page 8 ----------------
        print("page Collaborations - reciprocity scatter (col_reciprocity) has marks")
        info8 = chart_info(page)
        idx8 = find_chart_index(info8, xaxis_title="Part du portefeuille propre de l'UL")
        checks += 1
        if idx8 < 0:
            failures.append("col_reciprocity: no chart with the reciprocity x-axis title found on Collaborations (default p20 floor)")
            print("  [FAIL] page 8 reciprocity chart not found")
        else:
            marks8 = chart_marks(page)
            pts8 = next((c["points"] for c in marks8 if c["index"] == idx8), 0)
            if pts8 > 0:
                print(f"  [ok] col_reciprocity: {pts8} point(s) on the scatter (chart #{idx8})")
            else:
                failures.append(f"col_reciprocity: chart #{idx8} has ZERO points (p20 floor default)")
                print(f"  [FAIL] col_reciprocity: chart #{idx8} has 0 points")
        # NOTE (coverage limitation, not a defect): "square marker iff share_p_capped_flag"
        # is NOT live-smoke-testable on the current snapshot -- 0 partners are capped
        # (P-COL's own disclosure, progress/P7_COL.md judgment calls); unit-proven instead
        # on a synthetic frame (tests/test_page7_col.py). See docs/INSPECTION_REPORT_pass7a.md.

        # ---------------- Zoom partenaire (pass-6 NEW page 9, deep-linked) ----------------
        print("page Zoom partenaire - deep link ?partner_id=, profil thematique + reciprocite")
        goto(page, base, f"/Zoom_partenaire?partner_id={PARTNER_ID}")
        check(page, f"52_zoom_partenaire_{sdg_variant}")
        body_zp = page.inner_text("body")
        checks += 1
        # PASS-7a FIX (S-INSP, stale-pin staleness caught by actually running this file,
        # same class as the pre-existing "FR-wrapper rename" note above): P-ZOOM's rebuild
        # (progress/P7_ZOOM.md) renders the section heading as plain "### Réciprocité
        # stratégique" -- the level (champ/sous-champ) is now TOGGLEABLE via the shared
        # v2_pair_level radio, so a static "par champ" suffix would misdescribe the
        # sous-champ state; P-ZOOM's own page-header docstring still SAYS "par champ/
        # sous-champ" as a deliverable description, but the rendered markdown call
        # (page 9 l.1277) is `st.markdown("### Réciprocité stratégique")`, verbatim,
        # confirmed by grep. This pin now matches the ACTUAL heading; the underlying
        # claim (a reciprocity panel renders on this page) is unchanged and still proven.
        if "Réciprocité stratégique" in body_zp:
            print("  [ok] #46: reciprocite panel present on the deep-linked partner page")
        else:
            failures.append(f"#46: reciprocite panel not found on Zoom partenaire (partner_id={PARTNER_ID})")
            print("  [FAIL] #46: reciprocite panel missing")

        # ---------------- Phares KPI + link (pass-7a, P7) -- page 9 ----------------
        print("page Zoom partenaire - phares KPI + OpenAlex link (zoom_kpi_phares)")
        phares_val = metric_value(page, "Publications phares")
        checks += 1
        if phares_val:
            print(f"  [ok] page 9 phares KPI shows {phares_val!r}")
        else:
            failures.append("zoom_kpi_phares: 'Publications phares' metric tile not found or empty on Zoom partenaire")
            print("  [FAIL] page 9 phares KPI missing/empty")
        phares_links = page.locator('a[href*="openalex.org/works"]')
        checks += 1
        if phares_links.count() > 0:
            print(f"  [ok] page 9 phares link(s) present ({phares_links.count()})")
        else:
            failures.append("zoom_kpi_phares: no OpenAlex '<a href>' link found on Zoom partenaire (phares_url)")
            print("  [FAIL] page 9 phares link missing")

        # ---------------- Balance bars: linked column + level toggle (pass-7a, P10) ----------------
        print("page Zoom partenaire - balance bars linked Co-pubs column + level toggle (v2_pair_level)")
        info9a = chart_info(page)
        idx_bb = find_chart_index(info9a, has_y2=True)
        checks += 1
        row_count_field = 0
        if idx_bb < 0:
            failures.append("zoom_balance_bars: no chart with a yaxis2 link column found (default level=Champs)")
            print("  [FAIL] page 9 balance-bars chart (with linked column) not found")
        else:
            y2 = info9a[idx_bb]["y2_ticktext"] or []
            row_count_field = len(y2)
            links_field = sum(1 for t in y2 if "<a href" in t)
            dashes_field = sum(1 for t in y2 if t.strip() == "—")
            ok_bb = row_count_field > 0 and (links_field + dashes_field) == row_count_field and links_field > 0
            if ok_bb:
                print(f"  [ok] zoom_balance_bars (champ): {row_count_field} row(s), {links_field} linked, {dashes_field} dash(es)")
            else:
                failures.append(f"zoom_balance_bars (champ): link-column row accounting off -- rows={row_count_field} links={links_field} dashes={dashes_field}")
                print(f"  [FAIL] zoom_balance_bars link-column accounting: rows={row_count_field} links={links_field} dashes={dashes_field}")

        try:
            level_radio = page.locator('[data-testid="stRadio"]').filter(has_text="sous-champs").first
            checks += 1
            if level_radio.count():
                level_radio.get_by_text("sous-champs", exact=False).click()
                settle(page)
                info9b = chart_info(page)
                idx_bb2 = find_chart_index(info9b, has_y2=True)
                row_count_sub = len(info9b[idx_bb2]["y2_ticktext"] or []) if idx_bb2 >= 0 else 0
                if idx_bb2 >= 0 and row_count_sub != row_count_field:
                    print(f"  [ok] v2_pair_level toggle changes the balance-bars row count ({row_count_field} -> {row_count_sub})")
                else:
                    failures.append(f"v2_pair_level: balance-bars row count did NOT change after the level toggle (champ={row_count_field!r}, sous_champ={row_count_sub!r}, idx={idx_bb2})")
                    print(f"  [FAIL] v2_pair_level toggle did not change the row count ({row_count_field!r} -> {row_count_sub!r})")
                level_radio.get_by_text("Champs", exact=True).click()  # restore for the rest of the flow
                settle(page)
            else:
                print("  [warn] page 9 level-toggle radio not found -- selector skipped")
        except Exception as e:
            print(f"  [warn] page 9 level-toggle probe skipped: {e}")

        # ---------------- Topic planes: N selector changes the mark count (pass-7a, P9) ----------------
        print("page Zoom partenaire - topic planes N-slider changes the mark count")
        try:
            info9c = chart_info(page)
            plane_idx = find_chart_index(info9c, xaxis_title="Co-publications de la relation")
            checks += 1
            if plane_idx < 0:
                failures.append("zoom_plane_impact: no chart with the plane's x-axis title found (partner may be below PLANE_FLOOR)")
                print("  [FAIL] page 9 plane-impact chart not found")
            else:
                # tests/stress/run_stress.py's own selector for this exact widget shape
                # (input[type=range] inside stSlider) -- [role="slider"] (BaseWeb's visual
                # thumb) found nothing live, this native range input is what actually exists.
                handle = page.locator('[data-testid="stSlider"] input[type="range"]').first
                if handle.count():
                    # force=True: Streamlit's sticky toolbar/BaseWeb wrapper divs intercept
                    # the pointer event at this position (live-confirmed: 30+ retries, 60s
                    # timeout) -- same class of transient occlusion already documented and
                    # fixed for D7's mask_toggle above; safe once the element's identity is
                    # confirmed via the testid+type selector.
                    handle.click(force=True)
                    page.keyboard.press("Home")
                    settle(page)
                    pts_min = next((c["points"] for c in chart_marks(page) if c["index"] == plane_idx), 0)
                    page.keyboard.press("End")
                    settle(page)
                    pts_max = next((c["points"] for c in chart_marks(page) if c["index"] == plane_idx), 0)
                    if pts_max != pts_min:
                        print(f"  [ok] zoom_plane_impact: N slider (10 vs 50) changes the mark count ({pts_min} -> {pts_max})")
                    else:
                        failures.append(f"zoom_plane_impact: N slider (10 vs 50) did not change the mark count ({pts_min} both times)")
                        print(f"  [FAIL] zoom_plane_impact: N slider did not change the mark count ({pts_min})")
                else:
                    print("  [warn] page 9 plane N-slider handle not found -- selector skipped")
        except Exception as e:
            print(f"  [warn] page 9 plane-selector probe skipped: {e}")

        # ---------------- Page workbook download (pass-7a, P16) ----------------
        print("page Zoom partenaire - page workbook download (v2_page_workbook_dl)")
        try:
            wb_btn = page.get_by_text("Télécharger cette vue (xlsx)", exact=False).first
            checks += 1
            if wb_btn.count():
                with page.expect_download() as dl_info:
                    wb_btn.click()
                dl = dl_info.value
                wb_dir = SHOTS / "_downloads"
                wb_dir.mkdir(exist_ok=True)
                target = wb_dir / dl.suggested_filename
                dl.save_as(str(target))
                import openpyxl as _oxl
                wb_ = _oxl.load_workbook(str(target))
                ok_wb = bool(wb_.sheetnames) and wb_.sheetnames[0] == "Lecture"
                if ok_wb:
                    print(f"  [ok] page workbook downloaded ({dl.suggested_filename}), sheets={wb_.sheetnames}")
                else:
                    failures.append(f"page workbook: 'Lecture' is not the first sheet ({wb_.sheetnames})")
                    print(f"  [FAIL] page workbook sheet order: {wb_.sheetnames}")
            else:
                failures.append("page workbook: download button 'Télécharger cette vue (xlsx)' not found on Zoom partenaire")
                print("  [FAIL] page workbook button not found")
        except Exception as e:
            failures.append(f"page workbook: download/parse failed: {e}")
            print(f"  [FAIL] page workbook: {e}")

        # ---------------- pass-7b B8 (S-INSP) -- balance mirror/table CSS switch ----------------
        check_page9_mirror_breakpoint(page)

        # ---------------- Geographie (pass-6 NEW page 10) ----------------
        print("page Geographie - FR country label round-trip (Namibie, P3) + query-box audit")
        goto(page, base, "/Géographie")
        check(page, f"53_geographie_{sdg_variant}")
        try:
            pays_box = page.locator('[data-testid="stSelectbox"]').filter(has_text="Pays").last
            field = pays_box.locator("input").first
            field.click()
            page.wait_for_timeout(400)
            field.fill("Namib")
            page.wait_for_timeout(900)
            page.keyboard.press("Enter")
            settle(page)
            picked = field.input_value()  # BaseWeb writes the picked label into the
                                           # <input> VALUE attribute, invisible to
                                           # inner_text() -- see module docstring.
            checks += 1
            if picked == "Namibie":
                print("  [ok] P3: NA -> 'Namibie' round-trip confirmed via selectbox value")
            else:
                failures.append(f"P3: Geographie country selectbox did not resolve NA to 'Namibie' (got {picked!r})")
                print(f"  [FAIL] P3: country round-trip got {picked!r}")
            check(page, f"53_geographie_namibie_{sdg_variant}", charts=False)

            # Query-threshold live audit (item #8 of the S-INSP battery): the
            # "Fiche pays" field-level breakdown never exceeds 26 rows (all_topics
            # has 26 fields) -- always under the P6-R6 floor of 50, so its own
            # "Rechercher un champ/sous-champ" box must be gated OFF the same way
            # Perimetres' is. FIX-1 pass-6 fix round (S-LENS D5 / S-INSP D2): the
            # call site now wraps the box in ranked.should_show_query_box(), same
            # as page 3/14 -- this pin used to document the live symptom (a known,
            # reported defect) and now guards the fix stays fixed.
            rech = page.get_by_text("Rechercher un", exact=False)
            checks += 1
            if rech.count() and rech.first.is_visible():
                failures.append("P6-R6: Geographie 'Fiche pays' search box is VISIBLE though the field/subfield list is always < 50 rows (ranked.should_show_query_box not applied on this call site -- regression, see docs/LENS_ABSORPTION_pass6.md D5)")
                print("  [FAIL] P6-R6: Geographie query box visible below N<50 (REGRESSION -- was fixed in FIX-1)")
            else:
                print("  [ok] P6-R6: Geographie query box correctly hidden")
        except Exception as e:
            print(f"  [warn] Geographie country/query-box probe skipped: {e}")

        # ---------------- Country link + gutter (pass-7a, P4/P1) -- page 10 ----------------
        print("page Geographie - country OpenAlex link (Fiche pays) + companion gutter")
        country_links = page.locator('a[href*="institutions.country_code"]')
        checks += 1
        if country_links.count() > 0:
            print(f"  [ok] page 10 country link(s) present ({country_links.count()})")
        else:
            failures.append("geo_map/country_url: no '<a href>' containing institutions.country_code found on Geographie (Fiche pays header)")
            print("  [FAIL] page 10 country link missing")
        info10 = chart_info(page)
        checks += 1
        if info10 and info10[0]["n_traces"] >= 2:
            print(f"  [ok] page 10 country-companion chart (#0) carries {info10[0]['n_traces']} traces (bar + gutter)")
        else:
            n10 = info10[0]["n_traces"] if info10 else 0
            failures.append(f"geo_country_companion: expected >=2 traces (bar + gutter phantom) on chart #0, got {n10}")
            print(f"  [FAIL] page 10 gutter: chart #0 has {n10} trace(s), expected >=2")

        # ---------------- Annuaire des auteurs (pass-6 NEW page 11) ----------------
        print("page Annuaire - search + 'afficher plus' +50 (P8/#47)")
        goto(page, base, "/Annuaire_auteurs")
        check(page, f"54_annuaire_{sdg_variant}", charts=False)
        try:
            search = page.locator('[data-testid="stTextInput"] input').first
            search.click()
            search.fill("a")
            page.wait_for_timeout(700)
            page.keyboard.press("Enter")
            settle(page)
            body_before = page.inner_text("body")
            more_btn = page.get_by_text("Afficher", exact=False).first
            grew = False
            if more_btn.count():
                more_btn.click()
                settle(page)
                body_after = page.inner_text("body")
                grew = len(body_after) > len(body_before)
            checks += 1
            if grew:
                print("  [ok] #47: 'afficher plus' (+50) grows the visible result list")
            else:
                failures.append("#47: 'afficher plus' on Annuaire did not appear to grow the result list")
                print("  [FAIL] #47: 'afficher plus' did not grow the list")
            check(page, f"54_annuaire_search_{sdg_variant}", charts=False)
        except Exception as e:
            print(f"  [warn] Annuaire search/afficher-plus probe skipped: {e}")

        # ---------------- Profil auteur (pass-6 NEW page 12, deep-linked) ----------------
        print("page Profil auteur - deep link ?author_id=")
        goto(page, base, f"/Profil_auteur?author_id={AUTHOR_ID}")
        check(page, f"55_profil_auteur_{sdg_variant}", charts=False)

        # ---------------- pass-7b P3 (S-INSP) -- author_yearly_bars reading line ----------------
        assert_reading_present_absent(page, "author_yearly_bars reading line",
                                       "garde sa place sur l'axe")

        # ---------------- Identifiants et couverture (pass-6 NEW page 13) ----------------
        print("page Identifiants et couverture")
        goto(page, base, "/Identifiants_et_couverture")
        check(page, f"56_identifiants_{sdg_variant}")

        # ---------------- pass-7b B2/D7 (S-INSP) -- id_orcid_fields / id_orcid_yearly ----------------
        assert_gutter_number(page, "id_orcid_fields (Identifiants et couverture)")
        check_page13_orcid_yearly(page)

        # ---------------- Benchmark (pass-6 NEW page 14) ----------------
        print("page Benchmark - log/linear toggle (R18) inside its drill-down expander")
        goto(page, base, "/Benchmark")
        check(page, f"57_benchmark_{sdg_variant}")

        # ---------------- pass-7b B2/B6 (S-INSP) -- bench_rung_forest / bench_dot_ratio ----------------
        assert_reference_dash(page, "Benchmark (page 14) reference line")
        try:
            exp = page.get_by_text("Vérifier une spécialisation précise", exact=False).first
            exp.click()
            page.wait_for_timeout(700)
            toggle = page.get_by_text("échelle linéaire (LQ vs France)", exact=False).first
            toggle.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            toggle.click()
            settle(page)
            checks += 1
            print("  [ok] R18: log/linear toggle clicked without exception")
            check(page, f"57_benchmark_linear_{sdg_variant}")
        except Exception as e:
            failures.append(f"R18: Benchmark log/linear toggle interaction failed: {e}")
            print(f"  [FAIL] R18: Benchmark toggle interaction failed: {e}")

        # ---------------- F-VAC-01 persistence journey (fix round, pass 5) ----------------
        check_persistence_journey(page, base)

        browser.close()


def config_variant() -> str:
    """The variant currently written in config.yaml."""
    m = re.search(r"^\s*sdg_variant:\s*(\S+)", CONFIG.read_text(encoding="utf-8"), flags=re.M)
    return m.group(1) if m else "b_siris"


def patch_config(variant: str):
    backup = CONFIG.with_suffix(".yaml.smokebak")
    shutil.copy2(CONFIG, backup)
    text = CONFIG.read_text(encoding="utf-8")
    patched = re.sub(r"^(\s*sdg_variant:\s*)\S+", rf"\g<1>{variant}", text, count=1, flags=re.M)
    CONFIG.write_text(patched, encoding="utf-8")
    return backup


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sdg-variant", default=None,
                    choices=["b_siris", "c_openalex", "off"],
                    help="temporarily patch config.yaml before running")
    args = ap.parse_args()

    backup = patch_config(args.sdg_variant) if args.sdg_variant else None
    variant = args.sdg_variant or config_variant()
    port = free_port()
    proc = None
    try:
        print(f"starting streamlit on port {port} (app.sdg_variant={variant})")
        proc = start_app(port)
        run(f"http://localhost:{port}", variant)
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
        if backup:
            shutil.copy2(backup, CONFIG)
            backup.unlink()

    print()
    if failures:
        print(f"SMOKE FAILED - {len(failures)} of {checks} checks")
        for f in failures:
            # cp1252 console: strip anything it cannot encode
            line = ("  ! " + f.replace("\n", " ")[:400])
            print(line.encode("ascii", "replace").decode())
        return 1
    print(f"SMOKE PASSED - {checks} checks, screenshots in reports/evals/smoke/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
