"""
Render-verification of the pass-7a chart primitives (S-LIB-A) -- every builder of
`tests/_registry.BUILDERS`, at 1920/1280/390 px, per the SIRIS house rules
(light mode only, full width, `scrollWidth <= innerWidth`) and VIZ_SPEC_pass7 §1.3.

No app server and no kaleido: each figure is written to standalone HTML (plotly's own
bundle copied ONCE into the output folder, `include_plotlyjs="directory"` -- offline,
no CDN) and shot with the pinned venv's Playwright chromium. That is the only way to
verify a chart by RENDERING rather than by reading its CSS, which is what the house
rules require and what the M1/M2 probe below actually measures.

THREE things this script measures, not just pictures it takes:
  1. `scrollWidth <= innerWidth` at every width for every figure (the house rule).
  2. THE M1/M2 COLLISION (VIZ_SPEC_pass7 §1.3). BenchUp's gutter mechanism ported
     literally puts the gutter text and plotly's own y-tick labels in the SAME reserved
     margin band; measured at ~37 px of overlap. M2 -- `yaxis.ticklabelstandoff =
     GUTTER_COL_PX + COL_PAD_PX` -- clears it. This script reads BOTH edges out of the
     live DOM on a representative bar figure and then RE-RENDERS the same figure with
     the standoff forced to 0: the identical check must fail there, or it proves
     nothing (P14 vacuity, applied to a render check).
  3. GUTTER CLIPPING AT 390 px: the left edge of every gutter number, in viewport
     coordinates. A negative edge means the number is cut off, and the builder's
     `gutter=False` escape hatch is then the answer for that width.
  4. THE PLOT AREA'S OWN WIDTH (follow-up 1). A bar family whose constant left margin
     is wider than the viewport gets a ZERO-width plot area: the labels and the gutter
     numbers still render, the BARS do not. That is how `labo` (margin.l 393 px) failed
     at 390 px on the first render round, and it is the reason the `labo_court` family
     exists. Measured off the cartesian background rect, so it is the drawn area, not
     an arithmetic guess.

Usage: .venv-pinned\\Scripts\\python tests\\ui\\render_lib_pass7.py
Output -> progress/p7_proofs/LIB/ (PNGs + measurements.json). ASCII-only stdout (cp1252).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "Streamlit"))

import _registry as R  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

SHOTS = ROOT / "progress" / "p7_proofs" / "LIB"
SHOTS.mkdir(parents=True, exist_ok=True)

WIDTHS = [1920, 1280, 390]
BAR_FAMILIES: set = set()   # rempli au demarrage depuis lib.charts.FAMILIES
BASE_HEIGHT = 1200
SETTLE_MS = 700

# One page shell per figure: zero body margin, FULL WIDTH (no character measure), an
# explicit light ground -- the house rules, applied to the proof page itself.
SHELL = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{ color-scheme: light; }}
  html, body {{ margin: 0; padding: 0; background: #FFFFFF; }}
  #fig {{ width: 100%; }}
</style></head>
<body><div id="fig">{body}</div></body></html>
"""

MEASURE_JS = """
() => {
  const ticks = [...document.querySelectorAll('.yaxislayer-above .ytick text, g.ytick text')];
  const bartext = [...document.querySelectorAll('text.bartext')];
  const box = el => { const r = el.getBoundingClientRect(); return {l: r.left, r: r.right}; };
  // plotly's OWN computed plot length is the authority here: the background rect is
  // absent from the DOM at the widths where the area collapses, which reads as "not
  // measured" rather than "zero" if you only look for the rect.
  const gd = document.querySelector('.js-plotly-plot');
  const ax = gd && gd._fullLayout && gd._fullLayout.xaxis;
  const bg = document.querySelector('.cartesianlayer .subplot .bg, .bglayer .bg');
  const plotW = (ax && typeof ax._length === 'number') ? ax._length
              : (bg ? bg.getBoundingClientRect().width : null);
  const tickRight = ticks.length ? Math.max(...ticks.map(t => box(t).r)) : null;
  const gutterLeft = bartext.length ? Math.min(...bartext.map(t => box(t).l)) : null;
  return {
    n_ticks: ticks.length, n_bartext: bartext.length,
    tick_right: tickRight, gutter_left: gutterLeft, plot_width: plotW,
    scroll_w: document.documentElement.scrollWidth,
    inner_w: window.innerWidth,
  };
}
"""


def _write_html(fig, path: Path) -> None:
    fig.update_layout(autosize=True)
    body = fig.to_html(include_plotlyjs="directory", full_html=False,
                       default_width="100%", config={"responsive": True})
    path.write_text(SHELL.format(body=body), encoding="utf-8")


def _plotly_bundle() -> None:
    """`include_plotlyjs="directory"` references `plotly.min.js` NEXT TO the page --
    written once here so the ten proof pages share one copy and none of them needs a
    network round trip."""
    import plotly.offline
    src = Path(plotly.offline.offline.__file__).parent / "package_data" / "plotly.min.js"
    if not src.exists():                       # plotly >= 5 layout fallback
        import plotly
        src = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    (SHOTS / "plotly.min.js").write_bytes(src.read_bytes())


def main() -> int:
    _plotly_bundle()
    import lib.charts as C
    global BAR_FAMILIES
    BAR_FAMILIES = set(C.FAMILIES)
    entries = list(R.BUILDERS)
    seen: dict[str, int] = {}
    results = []
    failures = []

    pages = []
    for key, family, build in entries:
        seen[key] = seen.get(key, 0) + 1
        slug = key if seen[key] == 1 else "{0}_{1}".format(key, seen[key])
        fig = build()
        path = SHOTS / "{0}.html".format(slug)
        _write_html(fig, path)
        pages.append((slug, key, family, path))
        print("BUILT {0:<26} family={1:<12} traces={2}".format(slug, family, len(fig.data)))

    # the M1 control: the SAME representative figure with the standoff forced to 0
    rep_slug, rep_key, rep_family, _ = next(p for p in pages if p[2] not in ("scatter", "annee"))
    m1 = R.build_zoom_field_companion()
    m1.update_yaxes(ticklabelstandoff=0)
    m1_path = SHOTS / "probe_gutter_M1_control.html"
    _write_html(m1, m1_path)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for width in WIDTHS:
            page = browser.new_page(viewport={"width": width, "height": BASE_HEIGHT})
            for slug, key, family, path in pages:
                page.goto(path.as_uri())
                page.wait_for_timeout(SETTLE_MS)
                m = page.evaluate(MEASURE_JS)
                page.screenshot(path=str(SHOTS / "{0}_{1}.png".format(slug, width)),
                                full_page=True)
                overflow = m["scroll_w"] > m["inner_w"]
                no_plot = (family in BAR_FAMILIES
                           and (m["plot_width"] is None or m["plot_width"] <= 0))
                clipped = (m["gutter_left"] is not None and m["gutter_left"] < 0)
                collision = (m["tick_right"] is not None and m["gutter_left"] is not None
                             and m["tick_right"] > m["gutter_left"])
                results.append(dict(chart=slug, key=key, family=family, width=width,
                                    **m, overflow=overflow, gutter_clipped=clipped,
                                    tick_gutter_collision=collision, no_plot_area=no_plot))
                if overflow:
                    failures.append("{0}@{1}: scrollWidth {2} > innerWidth {3}".format(
                        slug, width, m["scroll_w"], m["inner_w"]))
                if clipped:
                    failures.append("{0}@{1}: gutter number clipped (left {2:.1f})".format(
                        slug, width, m["gutter_left"]))
                if collision:
                    failures.append("{0}@{1}: tick right {2:.1f} > gutter left {3:.1f}".format(
                        slug, width, m["tick_right"], m["gutter_left"]))
                if no_plot:
                    failures.append("{0}@{1}: ZERO plot area ({2}) -- the bars cannot "
                                    "render, only the labels and the gutter".format(
                                        slug, width, m["plot_width"]))
            page.close()

        # M1 control at the width the probe was measured on (1280 px)
        page = browser.new_page(viewport={"width": 1280, "height": BASE_HEIGHT})
        page.goto(m1_path.as_uri())
        page.wait_for_timeout(SETTLE_MS)
        m1_measure = page.evaluate(MEASURE_JS)
        page.screenshot(path=str(SHOTS / "probe_gutter_M1_control_1280.png"), full_page=True)
        page.close()
        browser.close()

    m1_collides = (m1_measure["tick_right"] is not None
                   and m1_measure["gutter_left"] is not None
                   and m1_measure["tick_right"] > m1_measure["gutter_left"])
    overlap = (None if not m1_collides
               else m1_measure["tick_right"] - m1_measure["gutter_left"])
    print("\nM1 CONTROL (standoff forced to 0, 1280 px): collision={0} overlap={1}".format(
        m1_collides, "n/a" if overlap is None else round(overlap, 1)))
    if not m1_collides:
        failures.append("VACUITY: the standoff=0 control did NOT collide -- the M2 check "
                        "cannot fail, so it proves nothing")

    (SHOTS / "measurements.json").write_text(json.dumps(
        dict(widths=WIDTHS, charts=len(pages), measurements=results,
             m1_control=dict(**m1_measure, collision=m1_collides, overlap_px=overlap),
             failures=failures), indent=1), encoding="utf-8")

    print("\n{0} PNGs written to {1}".format(len(pages) * len(WIDTHS) + 1, SHOTS))
    if failures:
        print("\nFAILURES ({0}):".format(len(failures)))
        for f in failures:
            print("  -", f)
        return 1
    print("\nOK: no overflow, no clipped gutter number, no tick/gutter collision, "
          "and the standoff=0 control DOES collide.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
