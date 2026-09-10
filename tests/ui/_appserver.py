"""
Shared Playwright/Streamlit harness for Stream E's eval suite.

Deliberately separate from `tests/ui/smoke.py` (Stream C's file, read-only per the
Stream E scope fence) even though several helpers are copy-adapted from it — the
`settle()` / `full_shot()` traps documented there (piped stdout deadlocks the
server; `screenshot(full_page=True)` only captures one viewport because Streamlit
scrolls inside its own container) apply here too, so the fixes are repeated rather
than imported from a file this stream must not modify.

Three read techniques back every "the page displays X" assertion in this suite,
confirmed empirically against this exact app/Streamlit build (1.61.1) before use:

  1. Real DOM text  - `st.metric` (`[data-testid="stMetric"]`) and the
     Laboratoires mini-fiche "Publications" KPI tile (`big_number()`, matched
     by its `font-size:22px` value div + adjacent label -- the pass-6 mini-fiche
     replaced the old `#pubs-total` id, FIX-1 pass-6 fix round). Cheap, exact,
     no ambiguity.
  2. Clipboard copy  - `st.dataframe` renders to a canvas (glide-data-grid), so
     `inner_text()` on it is empty. Clicking a cell then Ctrl+A / Ctrl+C copies the
     grid as TSV to the OS clipboard (Streamlit's own accessibility affordance) —
     `copy_grid_tsv()` reads it back. Needs `permissions=["clipboard-read",
     "clipboard-write"]` on the browser context.
  3. Plotly SVG fill  - each treemap tile is a `<g class="slice">` with a `<text>`
     label and a `<path class="surface">` carrying the rendered `fill` in its
     `style` attribute. `slice_fill_by_label()` reads the ACTUAL rendered colour,
     not the declared colorscale, so it is the closest thing to "read the Plotly
     figure spec from the page" for a discrete data point.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

VIEWPORT = {"width": 1500, "height": 1100}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_app(port: int, log_path: Path, app_path: str = "Streamlit/Menu.py",
              cwd: Path | str | None = None) -> subprocess.Popen:
    """
    Launch Streamlit, log to a FILE (never a pipe -- see module docstring).

    `cwd` defaults to this repo's root (v2's app tolerates either cwd, per
    Stream C's absolute-path fix). v1 (`../Phase 1/Streamlit/app.py`) does NOT:
    its pages read `data/...` with a RELATIVE path, so it must be launched with
    `cwd=".../Phase 1/Streamlit"` and `app_path="app.py"` -- exactly how v1 has
    always been run (`streamlit run app.py` from inside `Streamlit/`), never
    `streamlit run Streamlit/app.py` from one level up.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", app_path,
         "--server.headless", "true", "--server.port", str(port),
         "--browser.gatherUsageStats", "false"],
        cwd=str(cwd) if cwd is not None else str(ROOT), stdout=log, stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 120
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"streamlit died -- see {log_path}")
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                time.sleep(2)
                return proc
        time.sleep(0.5)
    raise RuntimeError("streamlit did not start in time")


def stop_app(proc: subprocess.Popen | None) -> None:
    if not proc:
        return
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def script_state(page) -> str:
    return page.evaluate(
        "() => { const e = document.querySelector('[data-testid=\"stApp\"]');"
        " return e ? e.getAttribute('data-test-script-state') : ''; }")


def settle(page, timeout: int = 120_000) -> None:
    """Wait until Streamlit has finished its rerun (see smoke.py for why)."""
    page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=timeout)
    page.wait_for_timeout(1500)
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        if script_state(page) == "notRunning":
            break
        time.sleep(0.3)
    else:
        raise TimeoutError("streamlit still running after %.0fs" % (timeout / 1000))
    page.wait_for_timeout(400)


def goto(page, base: str, path: str) -> None:
    page.goto(f"{base}{path}", wait_until="domcontentloaded")
    settle(page)


def select_option(page, label: str, value: str) -> None:
    """Type into a Streamlit selectbox/text input and pick the first match."""
    box = page.locator('[data-testid="stSelectbox"], [data-testid="stTextInput"]').filter(has_text=label).first
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

    FIX-1 pass-6 fix round (S-INSP D4): this used to read `#pubs-total`, a DOM id
    that no longer exists anywhere in the app -- the pass-5 plain headline was
    replaced by the pass-6 mini-fiche's compact KPI tiles (P7/#28), which carry
    NO stable id, only inline styles. Left as `#pubs-total`, this silently
    returned "" forever (same root cause `tests/ui/smoke.py`'s own copy had,
    already fixed there this pass -- see docs/INSPECTION_REPORT_pass6.md item
    2). Fix: `_kpi_tile()` (Streamlit/pages/2_..._Laboratoires.py) renders the
    value as a `font-size:22px` div immediately followed by a `font-size:12px`
    label div reading "Publications" -- match on that CSS shape + the adjacent
    label text rather than a vanished id.
    """
    tiles = page.locator('div[style*="font-size: 22px"]')
    for i in range(tiles.count()):
        val = tiles.nth(i)
        label = val.locator("xpath=following-sibling::div[1]")
        if label.count() and label.inner_text().strip() == "Publications":
            return val.inner_text().strip()
    return ""


def metric_value(page, label: str) -> str:
    """Read an `st.metric`'s value by its label text (exact DOM text, no canvas)."""
    box = page.locator('[data-testid="stMetric"]').filter(has_text=label).first
    if not box.count():
        return ""
    val = box.locator('[data-testid="stMetricValue"]').first
    return val.inner_text().strip() if val.count() else ""


def toggle_conference(page) -> None:
    sidebar = page.locator('[data-testid="stSidebar"]')
    sidebar.get_by_text("Inclure les articles de conférence", exact=True).click()
    settle(page)


def copy_grid_tsv(page, grid_index: int = 0) -> str:
    """
    Read an `st.dataframe`'s full visible content as TSV via the grid's own
    Ctrl+A / Ctrl+C clipboard affordance (glide-data-grid draws to canvas, so
    `inner_text()` is always empty -- confirmed empirically, see module docstring).

    The browser context MUST be created with
    `permissions=["clipboard-read", "clipboard-write"]` or `navigator.clipboard`
    is unavailable and this raises.
    """
    grids = page.locator('[data-testid="stDataFrame"]')
    grid = grids.nth(grid_index)
    grid.scroll_into_view_if_needed()
    page.wait_for_timeout(400)

    def _one_copy() -> str:
        # Clear the clipboard first so a copy that silently fails to re-target
        # this grid (observed empirically: sequential reads across adjacent
        # grids occasionally yield stale content from the PREVIOUS grid) is
        # caught as "__CLEARED__" rather than mistaken for this grid's data.
        page.evaluate("() => navigator.clipboard.writeText('__CLEARED__')")
        page.wait_for_timeout(150)
        # `.click(position=...)` (not raw `page.mouse.click` on a cached
        # bounding box) so Playwright re-checks actionability/visibility itself.
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


def slice_fill_by_label(page, plot_index: int = 0) -> dict:
    """
    {label: "rgb(r, g, b)"} for every Plotly treemap tile of the plot_index'th
    `.js-plotly-plot` on the page, read from the ACTUAL rendered SVG (`path.surface`
    `style.fill`), not from the declared colorscale. Confirmed empirically to match
    linear-RGB interpolation of the app's declared `color_continuous_scale` within
    +/-1 per channel (8-bit rounding).
    """
    return page.evaluate(
        """(idx) => {
            const plots = document.querySelectorAll('.js-plotly-plot');
            const plot = plots[idx];
            if (!plot) return {};
            const out = {};
            plot.querySelectorAll('g.slice').forEach((sl) => {
                const txt = sl.querySelector('text');
                const path = sl.querySelector('path.surface');
                if (txt && path) {
                    const style = path.getAttribute('style') || '';
                    const m = style.match(/fill:\\s*(rgba?\\([^)]*\\))/);
                    if (m) out[txt.textContent] = m[1];
                }
            });
            return out;
        }""",
        plot_index,
    )
