"""
Stream E — Tier B eval suite (D48, BUILD_PLAN "Stream E — Eval suite").

Playwright-driven checks that need a real browser (or the real production
module import) rather than a raw parquet groupby:

  * wordcloud colour is a pure function of subfield (D9/D51 successor UX)
  * no empty axis/control survives where a topic-model axis used to be (D9)
  * v1<->v2 parity screenshots, page by page (D49 -- parity IS the success
    criterion)
  * the seeded-failure demo lives in `tests/ui/seeded_failure_demo.py`
    (a standalone script, not a permanent pytest case -- see progress/E_evals.md)

Run:  python -m pytest tests/ui/test_visual.py -v
(tests/ui/smoke.py, Stream C's file, is untouched and still runs standalone.)
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _appserver import (  # noqa: E402
    VIEWPORT, free_port, start_app, stop_app, goto, select_option,
)

PARITY_DIR = ROOT / "reports" / "evals" / "parity"
LOG_DIR = ROOT / "reports" / "evals"


# =============================================================================
# wordcloud colour is a pure function of subfield
# =============================================================================

def _wordcloud_colors_subprocess(structure_names: list[str]) -> dict:
    """
    Runs the REAL pass-6 page path (`_lab_wordcloud_slice` + `_term_domain_map`
    + `get_domain_color` -- exactly the trio `render_lab_wordcloud_png`'s
    color_func composes) in a FRESH subprocess and returns
    {lab_key: {term: color}} for the 'subfield' wordcloud level.

    A fresh subprocess, not an in-process `importlib` load, because this repo
    has TWO different top-level packages both named `lib` --
    `Phase 2/lib/` (pipeline: snapshot.py, openalex.py, ...) and
    `Phase 2/Streamlit/lib/` (app: data_cache.py, helpers.py, ...). Once
    `tests/test_app_numbers.py` imports the pipeline's `lib.snapshot` in the
    SAME pytest process, Python's `sys.modules` cache binds the name `lib` to
    that package for the rest of the process, so a later
    `from lib.data_cache import ...` inside the Streamlit page module resolves
    to the WRONG `lib` and raises `ModuleNotFoundError` -- confirmed
    empirically when both test files ran in one pytest session. A subprocess
    sidesteps the collision entirely (its own fresh `sys.modules`), and
    doubles as the literal "restart" for the stability test below.
    """
    streamlit_dir = str(ROOT / "Streamlit")
    root_dir = str(ROOT)
    page_path = str(ROOT / "Streamlit" / "pages" / "2_\U0001f3ed_Laboratoires.py")
    names_literal = repr(structure_names)
    script = (
        "import sys, json\n"
        f"sys.path.insert(0, {streamlit_dir!r})\n"
        f"sys.path.insert(0, {root_dir!r})\n"
        "import importlib.util\n"
        f"path = {page_path!r}\n"
        "spec = importlib.util.spec_from_file_location('m', path)\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        f"names = {names_literal}\n"
        "dmap = mod._term_domain_map()\n"
        "out = {}\n"
        "for name in names:\n"
        "    df = mod._lab_wordcloud_slice(name, 'subfield')\n"
        "    out[name] = {t: (mod.get_domain_color(dmap[t]) if t in dmap else mod.NEUTRAL_GREY)\n"
        "                 for t in df['term']}\n"
        "print(json.dumps(out))\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=str(ROOT))
    assert result.returncode == 0, f"subprocess failed: {result.stderr[-1500:]}"
    line = [ln for ln in result.stdout.splitlines() if ln.strip().startswith("{")][-1]
    return json.loads(line)


def test_wordcloud_colour_is_pure_function_of_term():
    """
    Pass-6 wordcloud (D48 carried): a term's colour comes purely from
    `get_domain_color(_term_domain_map()[term])` -- the lab is never an
    argument to the colour decision. Proven against the real production trio:
    two labs that share subfield terms must get the exact same colour for
    each shared term (measured 72 shared subfield terms IJL/LORIA on the
    deployed lab_wordcloud.parquet).
    """
    colors = _wordcloud_colors_subprocess(["IJL", "LORIA"])
    colors_ijl, colors_loria = colors["IJL"], colors["LORIA"]
    shared = set(colors_ijl) & set(colors_loria)
    assert len(shared) >= 5, f"expected several shared subfield terms between IJL and LORIA, found {len(shared)}"

    mismatches = {sid: (colors_ijl[sid], colors_loria[sid])
                  for sid in shared if colors_ijl[sid] != colors_loria[sid]}
    assert not mismatches, f"same subfield_id, different colour depending on structure: {mismatches}"


def test_wordcloud_colour_stable_across_two_fresh_processes():
    """
    'Stable across 2 app restarts' (D48), tested as 2 fully independent Python
    process invocations of the real production code path (fresh interpreter,
    fresh lab_wordcloud.parquet read, fresh module import each time) -- NOT an
    image hash across 2 browser sessions, because `WordCloud(...)` is still not
    given a `random_state`, so its LAYOUT (word position/rotation) is expected
    to differ run to run; only the colour step is supposed to be deterministic
    (`recolor(color_func)` keys purely on word text, applied AFTER layout).
    """
    outputs = [_wordcloud_colors_subprocess(["IJL"])["IJL"] for _ in range(2)]
    assert outputs[0] == outputs[1], "IJL's term->colour mapping changed across 2 fresh process restarts"
    assert len(outputs[0]) >= 5


# =============================================================================
# no empty axis/control where a TM axis used to be (D9)
# =============================================================================

@pytest.fixture(scope="function")
def v2_app():
    # function-scoped (not module-scoped) so its Playwright/event-loop context is
    # fully torn down before `test_v1_v2_parity_screenshots` opens its own --
    # nesting two live `sync_playwright()` contexts raises
    # "Sync API inside the asyncio loop".
    port = free_port()
    proc = start_app(port, LOG_DIR / "test_visual_v2_streamlit.log")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport=VIEWPORT, permissions=["clipboard-read", "clipboard-write"])
            page = ctx.new_page()
            page.set_default_timeout(60_000)
            yield page, f"http://localhost:{port}"
            browser.close()
    finally:
        stop_app(proc)


def _assert_no_empty_selects(page) -> None:
    boxes = page.locator('[data-testid="stSelectbox"], [data-testid="stMultiSelect"]')
    n = boxes.count()
    assert n > 0, "expected at least one select/multiselect control on this page"
    for i in range(n):
        box = boxes.nth(i)
        text = box.inner_text().strip()
        assert text, f"select/multiselect control #{i} renders with no visible text at all"
        assert "no option" not in text.lower(), f"control #{i} shows an empty-options placeholder: {text!r}"


def test_page3_has_no_empty_axis_control(v2_app):
    page, base = v2_app
    goto(page, base, "/Portefeuille_thématique")
    _assert_no_empty_selects(page)


def test_page4_has_no_empty_axis_control(v2_app):
    page, base = v2_app
    goto(page, base, "/Exploration_thématique")
    _assert_no_empty_selects(page)
    # the 4th selector level (replacing the dead topic-model axis, D9) must
    # itself carry non-empty option text once selected.
    select_option(page, "Choisir le niveau :", "🏷️ Topic")
    _assert_no_empty_selects(page)


# =============================================================================
# v1 <-> v2 parity screenshots (D49)
# =============================================================================

def _full_shot(page, path: Path) -> None:
    """Grow the viewport to the container's scroll height before shooting --
    Streamlit scrolls inside its own container, so a plain full_page screenshot
    only ever captures one viewport (same trap documented in smoke.py)."""
    height = page.evaluate(
        "() => { const e = document.querySelector('[data-testid=\"stMain\"]')"
        " || document.querySelector('section.main');"
        " return e ? e.scrollHeight : document.body.scrollHeight; }")
    tall = max(VIEWPORT["height"], min(int(height) + 120, 12000))
    page.set_viewport_size({"width": VIEWPORT["width"], "height": tall})
    page.wait_for_timeout(1000)
    page.screenshot(path=str(path))
    page.set_viewport_size(VIEWPORT)


def test_v1_v2_parity_screenshots():
    """
    v1 (`../Phase 1/Streamlit/app.py`, READ-ONLY -- never modified here) and v2
    run side by side on two local ports; page-by-page screenshot pairs land in
    `reports/evals/parity/` with `PARITY_NOTES.md` documenting the one-line diff
    expected for each pair. v1 was confirmed to run standalone against the
    locally installed Streamlit 1.61.1 (no API-break fallback to the live URL
    needed).
    """
    PARITY_DIR.mkdir(parents=True, exist_ok=True)
    port_v1, port_v2 = free_port(), free_port()
    proc_v1 = proc_v2 = None
    notes: list[str] = []
    try:
        v1_streamlit_dir = ROOT.parent / "Phase 1" / "Streamlit"
        proc_v1 = start_app(port_v1, LOG_DIR / "parity_v1_streamlit.log",
                             app_path="app.py", cwd=v1_streamlit_dir)
        proc_v2 = start_app(port_v2, LOG_DIR / "parity_v2_streamlit.log")
        base_v1, base_v2 = f"http://localhost:{port_v1}", f"http://localhost:{port_v2}"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport=VIEWPORT)
            pv1, pv2 = ctx.new_page(), ctx.new_page()
            for pg in (pv1, pv2):
                pg.set_default_timeout(60_000)

            # ---- pair 1: Lab_Overview / IJL, v2 default (conference ON) ----
            # v1 keeps its OWN old page name -- that codebase is read-only, unrelated
            # to this pass-5 v2 rename. Only the v2 (pv2/base_v2) goto is updated.
            goto(pv1, base_v1, "/Lab_Overview")
            select_option(pv1, "Select a structure", "IJL")  # v1 app is frozen EN
            _full_shot(pv1, PARITY_DIR / "01_lab_overview_IJL_v1.png")

            goto(pv2, base_v2, "/Laboratoires")
            select_option(pv2, "Sélectionner une structure", "IJL")
            _full_shot(pv2, PARITY_DIR / "01_lab_overview_IJL_v2_conference_on.png")
            notes.append(
                "01_lab_overview_IJL: v2 (conference ON, default) shows a higher IJL "
                "publication count than v1 -- D36/D52, +31.1% corpus-wide from conference "
                "papers OpenAlex now retypes; v2 adds the conference-toggle sidebar control "
                "v1 does not have."
            )

            # ---- pair 2: same page, v2 with the conference toggle OFF (closest to v1) ----
            sidebar = pv2.locator('[data-testid="stSidebar"]')
            sidebar.get_by_text("Inclure les articles de conférence", exact=True).click()
            from _appserver import settle
            settle(pv2)
            _full_shot(pv2, PARITY_DIR / "02_lab_overview_IJL_v2_conference_off.png")
            notes.append(
                "02_lab_overview_IJL: v2 with the conference toggle switched OFF -- the "
                "closest-to-v1 state (v1 never had conference papers). The IJL total should "
                "sit much closer to v1's (v1 had no conference-paper corpus at all, so an "
                "exact match is not expected -- OpenAlex's own retyping (D36) also moved "
                "other document-type boundaries)."
            )
            sidebar.get_by_text("Inclure les articles de conférence", exact=True).click()  # restore

            # ---- pair 3: Thematic_Overview, both default ----
            goto(pv1, base_v1, "/Thematic_Overview")
            _full_shot(pv1, PARITY_DIR / "03_thematic_overview_v1.png")
            goto(pv2, base_v2, "/Portefeuille_thématique")
            _full_shot(pv2, PARITY_DIR / "03_thematic_overview_v2.png")
            notes.append(
                "03_thematic_overview: v1's page is built on its topic model (Classic TM / "
                "Research Topics / Objectives-Methods-Impacts, D9); v2 replaces the whole "
                "page with the OpenAlex taxonomy (domain/field/subfield/topic) and adds the "
                "NEW SDG panel (D51) in the slot the old heatmap used to occupy. The treemap "
                "shape, legend and general layout are the parity anchor, not the axis content."
            )

            # ---- pair 4: Thematic_Drilldown, both default (domain level) ----
            goto(pv1, base_v1, "/Thematic_Drilldown")
            _full_shot(pv1, PARITY_DIR / "04_thematic_drilldown_v1.png")
            goto(pv2, base_v2, "/Exploration_thématique")
            _full_shot(pv2, PARITY_DIR / "04_thematic_drilldown_v2.png")
            notes.append(
                "04_thematic_drilldown: v1's 4th selector level is its topic model "
                "('Research Topic', with a keyword-badge methodology note, D9); v2's 4th "
                "level is the OpenAlex `topic` (3,275 of them, 0.1% of the corpus untopiced "
                "vs v1's topic model leaving 21% uncovered). KPI panel layout, contribution "
                "charts and partner tables are otherwise structurally the same."
            )

            browser.close()
    finally:
        stop_app(proc_v1)
        stop_app(proc_v2)

    shots = sorted(PARITY_DIR.glob("*.png"))
    assert len(shots) >= 6, f"expected >=6 screenshots (>=3 pairs), found {len(shots)}: {shots}"

    notes_path = PARITY_DIR / "PARITY_NOTES.md"
    notes_path.write_text(
        "# v1 <-> v2 parity notes\n\n"
        "Generated by `tests/ui/test_visual.py::test_v1_v2_parity_screenshots`. "
        "One line per pair; expected diffs only (D49's own list), never a regression.\n\n"
        + "\n".join(f"- **{n.split(':')[0]}**: {n.split(':', 1)[1].strip()}" for n in notes)
        + "\n",
        encoding="utf-8",
    )
    assert notes_path.exists()
