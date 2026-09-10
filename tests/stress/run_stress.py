"""
tests/stress/run_stress.py -- the permanent memory stress gate for the Lorraine Explorer v2
app (P13, pass 7a). Drives the REAL Streamlit app (one `streamlit run Streamlit/Menu.py`
server, headless) through a deterministic crash-path replay (phase A) and randomised
concurrent chaos (phase B) while sampling the server's own python.exe RSS every 0.5s, then
reports peak/mean/final per phase against the ceiling (< 1,800 MB, half the 2.7 GB Community
Cloud cap -- same ceiling `tests/test_ram_budget.py` uses for its own narrower bare-process
budget) and "the server never died".

PORTED FROM `docs/reference/benchup_2026-09-04/tests/stress/run_stress.py` (P13; read-only
reference, never imported at runtime -- copied INTO this project and adapted, standalone
principle). Everything Windows/server-lifecycle/RSS-sampling is generic and kept close to
verbatim (that earlier harness's own hard-won fixes: netstat-resolved PID because
`subprocess.Popen`'s own `.pid` is not reliably the real server on this box, `env=os.environ.
copy()` passthrough so a broken-control env var reaches the spawned server unchanged, stdout
to a FILE never a pipe left undrained, terminate BOTH the launched and the resolved PID).
Everything DOM/app-specific was NOT kept: this file uses Lorraine's OWN launch/settle idiom
(`tests/ui/_appserver.py`'s `settle()` -- poll `data-test-script-state` on
`[data-testid="stApp"]`, NOT BenchUp's `stStatusWidget` poll, a different Streamlit-version
DOM shape) and Lorraine's OWN sidebar-nav idiom (`tests/ui/smoke.py`'s `click_sidebar_nav_link`
/ `open_sidebar_nav_more` -- this app's sidebar folds itself behind a "View N more" toggle
past ~9 entries, unrelated to BenchUp's own DOM). No phase C: this
app's cache architecture (`Streamlit/lib/lazy.py`'s per-file `@st.cache_data(max_entries=...)`
keyed reads) has no equivalent to BenchUp's "one resident scenario substrate, bundle all 6
combinations" concept, and BUILD_PLAN.md P13 / the dispatch brief only ever ask for phases A+B.

PID resolution (verified empirically on this same Windows box by the harness this was ported
from, before trusting it here): `subprocess.Popen([PYTHON, "-m", "streamlit", "run", ...])`
does NOT reliably give the real server's PID -- Streamlit's own bootstrap can spawn a SEPARATE
CHILD python.exe that does the actual serving while the launched process stays a small
wrapper for its whole life. Sampling `proc.pid` directly can read a flat, tiny, healthy-
looking number for the whole run -- a silent false PASS, not a "server did not start" failure.
The fix: after the port opens, resolve the PID that is actually `LISTENING` on it via
`netstat -ano` (stdlib subprocess call to a Windows built-in, no new dependency).
`stop_server` terminates BOTH `proc.pid` and the resolved server PID (if different) so no
orphan is ever left behind.

Pass-7 new-controls seam (dispatch note, wave 2): the planes selector/slider, level toggle
and balance-mode selector on Zoom partenaire, and the page-workbook download button on pages
8/9, do NOT exist yet when this file is first written and dry-run'd (P-ZOOM/P-COL land in
W3). Every action that touches one of those four controls raises `Skip` on a missing widget;
`step()` catches it and records `skipped=True` (never `ok=False`) -- so today's phase-A dry
run stays green, and the SAME code exercises the real widgets once W3 lands, no rewrite
needed. `LABELS` (the four controls' exact rendered text) is imported LIVE from
`Streamlit/lib/copy_fr.py`, never hardcoded, so a future copy edit cannot silently desync
this harness from the app.

Environment passthrough (`os.environ.copy()`, not a fresh env) is what lets the broken-control
run work with NO code change here: `set LORRAINE_READ_KEYED_CAP=32` in the CALLING shell
before invoking this script raises `Streamlit/lib/lazy.py`'s `HEAVY_CAP` (the ptn_works/
ptn_topics `read_keyed` cache's `max_entries`) from 8 back to the pre-P12 ceiling of 32 in the
spawned server -- proving this script actually exercises that cache's own bound rather than
measuring something else (see tests/stress/README.md "Broken control").

Usage:
    .venv-pinned\\Scripts\\python.exe tests/stress/run_stress.py --phases A --port 8651
    .venv-pinned\\Scripts\\python.exe tests/stress/run_stress.py --minutes 4 --phases A,B
    (writes reports to tests/stress/reports/ by default; --out overrides)
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

STRESS_DIR = Path(__file__).resolve().parent            # tests/stress
ROOT = STRESS_DIR.parents[1]                             # project root ("Phase 2")
sys.path.insert(0, str(ROOT / "ops"))
from rss_probe import process_rss_mb  # noqa: E402  -- Lorraine's own copy (S-CACHE port)

# LABELS read LIVE off Streamlit/lib/copy_fr.py -- never hardcoded (see module docstring).
# Fallback dict only covers the exact 4 keys this file uses, and only fires if the import
# itself fails (e.g. a future copy_fr.py syntax error) -- diagnostic safety net, not a
# maintained second source of truth.
sys.path.insert(0, str(ROOT / "Streamlit"))
try:
    from lib.copy_fr import LABELS  # noqa: E402
except Exception as _e:  # noqa: BLE001
    print(f"[stress] WARNING: could not import Streamlit/lib/copy_fr.LABELS ({_e}); "
          f"using a frozen fallback copy -- re-sync this file if copy_fr.py changed.")
    LABELS = {
        "PAGE_WORKBOOK": "Télécharger cette vue (xlsx)",
        "LEVEL_TOGGLE": ["Champs", "Top 30 sous-champs (volume conjoint)"],
        "BALANCE_MODES": {"volume": "Volume", "fwci": "FWCI médian (réf. France)",
                          "phares": "Publications phares"},
        "PLANE_SELECT": {"volume": "Volume conjoint", "fwci": "FWCI médian (réf. France)",
                        "frontiere": "Score de frontière", "phares": "Publications phares"},
    }

PYTHON = sys.executable
PEAK_CEILING_MB = 1800.0  # half the 2.7 GB Community Cloud cap (BUILD_PLAN.md P13)

VIEWPORT = {"width": 1500, "height": 1100}  # tests/ui/_appserver.py's own VIEWPORT (reused)
MAIN_SCROLL_CONTAINER = "section.stMain"     # Lorraine DOM gotcha (P7_STRESS.md), NOT the
                                              # `[data-testid="stMain"]` testid BenchUp used


# ---------------------------------------------------------------------- seeds -----
# 12 partners spread across the co_works_full distribution (Streamlit/data/ptn_summary.
# parquet, conf_state='all' & subset_id='all', 12,570 rows, range 1-11,510) -- data-driven,
# not guessed: log-spaced target values (5000/2500/1000/500/250/120/60/30/12/4), nearest
# ACTUAL partner per target, CNRS + CHRU Nancy forced in as the two named anchors (dispatch
# brief). Exactly 2 of the 12 sit under 20 co_works_full (per P13's "incl. 2 under 20"),
# the other 8 span nearly 4 orders of magnitude. Probe: scratchpad `pick_seeds2.py`, run in
# `.venv-pinned`, 2026-09-10 (progress/P7_STRESS.md step 2 has the full table + log).
SEEDS = [
    ("I1294671590", "CNRS", 11510),
    ("I154526488", "Inserm", 3359),
    ("I68947357", "Universite de Strasbourg", 2211),
    ("I4210100260", "CHRU Nancy", 1835),
    ("I39804081", "Sorbonne Universite", 1091),
    ("I2738703131", "CEA", 522),
    ("I4210128565", "CEA Paris-Saclay", 250),
    ("I4210116240", "CHU Dijon Bourgogne", 120),
    ("I4210086194", "Institut des Sciences Moleculaires", 60),
    ("I4210147504", "Boehringer Ingelheim (China)", 30),
    ("I40413290", "University of Gdansk", 12),
    ("I4387154702", "IMPact Environnement Chimique Sante", 4),
]
SEED_IDS = [s[0] for s in SEEDS]
PARTNER_ID_CNRS = "I1294671590"   # phase A anchor 1 -- also `tests/ui/smoke.py`'s own
                                  # PARTNER_ID ("ptn_summary highest co_works_full")
PARTNER_ID_CHRU = "I4210100260"   # phase A anchor 2 -- CHRU Nancy (dispatch brief)

# The 6 pages this stream's phase A/B actually exercise (BUILD_PLAN.md P13's own list),
# as the exact substrings `tests/ui/smoke.py`'s `click_sidebar_nav_link` matches sidebar
# links on (Playwright `.filter(has_text=...)` is a substring match, so an emoji prefix in
# the rendered link does not break this).
NAV_PAGES = ["Collaborations", "Zoom partenaire", "Géographie", "Exploration thématique",
            "Portefeuille thématique", "Laboratoires"]

LAB_PICK = "IJL"  # tests/ui/smoke.py's own LARGE_LAB constant (2,188 works) -- reused,
                  # already proven to render a full mini-fiche + wordcloud (ponytail: don't
                  # re-derive a pick this codebase already vetted).


# ------------------------------------------------------------------ server ---------

def _wait_for_port(port: int, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.5)
    return False


def _find_listening_pid(port: int, timeout: float = 30.0) -> int | None:
    """The real server PID: whichever process `netstat -ano` shows LISTENING on `port` --
    NOT necessarily `proc.pid` (see module docstring)."""
    needle = f":{port} "
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            # errors="replace": a French-locale Windows console can emit netstat's own
            # header row in a codepage Python's text-mode decode does not expect. The PID
            # column is plain ASCII digits regardless, so a replaced header byte never
            # touches the value this function reads (same fix the ported harness carried).
            out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                                 errors="replace", timeout=10).stdout or ""
        except Exception:  # noqa: BLE001
            out = ""
        for line in out.splitlines():
            if "LISTENING" in line and needle in line and line.strip().startswith("TCP"):
                parts = line.split()
                try:
                    return int(parts[-1])
                except ValueError:
                    continue
        time.sleep(0.5)
    return None


def start_server(port: int, log_path: Path) -> subprocess.Popen:
    """One `streamlit run Streamlit/Menu.py` server, cwd=project root (matches how the app
    is actually deployed/run -- data paths inside the app are relative to Streamlit/).
    `env=os.environ.copy()` (not a fresh dict) is the passthrough the broken-control run
    depends on: `LORRAINE_READ_KEYED_CAP` set by the CALLER before invoking this script
    reaches `Streamlit/lib/lazy.py`'s own `os.environ.get(...)` read unchanged.

    stdout/stderr go to a FILE, never `subprocess.PIPE` left undrained: an unread pipe's OS
    buffer can fill from ordinary server logging and then the process's own `write()` calls
    BLOCK -- the whole server hangs. A file has no such limit, and doubles as a server log
    worth keeping on a FAIL."""
    log_f = open(log_path, "w", encoding="utf-8", errors="replace")
    return subprocess.Popen(
        [PYTHON, "-m", "streamlit", "run", "Streamlit/Menu.py",
         "--server.headless", "true", "--server.port", str(port)],
        cwd=str(ROOT), stdout=log_f, stderr=subprocess.STDOUT,
        env=os.environ.copy(),
    )


def _taskkill(pid: int) -> None:
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True,
                       text=True, errors="replace", timeout=10)
    except Exception:  # noqa: BLE001
        pass


def stop_server(proc: subprocess.Popen, server_pid: int | None) -> None:
    """Never leaves a server behind, even on a mid-run exception (caller's `finally`):
    terminate the LAUNCHED process, then -- since that PID and the real server PID can
    differ on Windows (module docstring) -- also `taskkill` the resolved `server_pid` if
    it is a different, still-running PID."""
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
    if server_pid is not None and server_pid != proc.pid:
        if process_rss_mb(server_pid) is not None:  # still openable => still alive
            _taskkill(server_pid)


# --------------------------------------------------------- RSS sampler -----

class RssSampler:
    """Background thread sampling the server's WorkingSetSize every `interval` seconds
    into `samples` as (elapsed_s, phase, rss_mb). A `process_rss_mb` miss (PID no longer
    openable) is the ONE reliable "the server died" signal, recorded once as `died_at`,
    never silently dropped as a zero or skipped as noise."""

    def __init__(self, pid: int, interval: float = 0.5):
        self.pid = pid
        self.interval = interval
        self.samples: list[tuple[float, str, float]] = []
        self.phase = "init"
        self.died_at: float | None = None
        self._stop = threading.Event()
        self.t0 = time.time()  # PUBLIC: chaos_session's own action-timestamp log is stamped
        # against this SAME reference so an action and an RSS sample line up on one shared
        # elapsed_s axis after the run (lets a future diagnosis find "which actions ran
        # around the peak" straight from the two CSVs, no separate repro needed).
        self._thread: threading.Thread | None = None

    def set_phase(self, name: str) -> None:
        self.phase = name

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            t = time.time() - self.t0
            r = process_rss_mb(self.pid)
            if r is None:
                if self.died_at is None:
                    self.died_at = t
            else:
                self.samples.append((t, self.phase, r[0]))
            time.sleep(self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def phase_stats(self, phase: str) -> dict:
        vals = [mb for _, p, mb in self.samples if p == phase]
        if not vals:
            return {"peak": None, "mean": None, "final": None, "n": 0}
        return {"peak": max(vals), "mean": sum(vals) / len(vals), "final": vals[-1], "n": len(vals)}


# ----------------------------------------------------- app-specific helpers -----
# settle()/goto()/script_state() are Lorraine's OWN idiom, ported from
# tests/ui/_appserver.py -- NOT BenchUp's stStatusWidget-based wait_idle(). Confirmed
# empirically against this app's pinned Streamlit build (1.61.1) by the eval-suite stream
# that wrote _appserver.py; reused here rather than re-derived (ponytail).

def script_state(page) -> str:
    return page.evaluate(
        "() => { const e = document.querySelector('[data-testid=\"stApp\"]');"
        " return e ? e.getAttribute('data-test-script-state') : ''; }")


def settle(page, timeout: int = 120_000) -> None:
    """Phase A only (chaos never waits for spinners, per phase B's own design below):
    wait until Streamlit has actually finished its rerun, not a fixed sleep."""
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


def goto(page, base: str, path: str, wait_until: str = "domcontentloaded") -> None:
    page.goto(f"{base}{path}", wait_until=wait_until)
    if wait_until != "commit":
        settle(page)


def has_error_box(page) -> bool:
    """A Streamlit uncaught-exception box always titles itself "Oh no." -- the one
    page-content signal for "a failure to record", alongside a websocket disconnect
    (caught as a raised Playwright exception at the call site instead)."""
    try:
        return page.get_by_text("Oh no", exact=False).count() > 0
    except Exception:
        return False


def assert_no_error(page, where: str) -> None:
    assert not has_error_box(page), f"{where}: Streamlit error box ('Oh no.') present"


# Sidebar nav -- ported from tests/ui/smoke.py verbatim (the fold-past-~9-entries gotcha).
def open_sidebar_nav_more(page, label: str) -> None:
    """The app has 14 pages + Menu; Streamlit collapses the sidebar nav behind a "View N
    more" toggle (`data-testid="stSidebarNavViewButton"`) once past ~9 entries, so a link
    past that fold is not in the DOM until this is clicked once. Idempotent: a no-op when
    `label` is already visible."""
    if page.locator('[data-testid="stSidebarNav"] a').filter(has_text=label).count():
        return
    more = page.locator('[data-testid="stSidebarNavViewButton"]')
    if more.count() and more.first.is_visible():
        more.first.click()
        page.wait_for_timeout(300)


def click_sidebar_nav_link(page, label: str, wait: bool = True) -> bool:
    """Real in-app sidebar navigation click -- NOT `page.goto()` (tears down the WebSocket
    session Streamlit's SPA-style sidebar nav keeps alive; F-VAC-01, tests/ui/smoke.py).
    `wait=False` (phase B) skips the settle() call -- chaos never waits for spinners."""
    open_sidebar_nav_more(page, label)
    link = page.locator('[data-testid="stSidebarNav"] a').filter(has_text=label).first
    if link.count() == 0:
        return False
    link.click()
    if wait:
        settle(page)
    return True


def scroll_main(page, y) -> None:
    main = page.locator(MAIN_SCROLL_CONTAINER)
    if main.count():
        main.first.evaluate(f"el => el.scrollTo(0, {y})")


# Generic widget helpers -- act only, no waiting (callers settle() when they need to; phase
# A does, phase B deliberately doesn't). Each returns False (never raises) when the widget
# isn't on the page, so phase A can turn "not found" into an explicit Skip and phase B can
# just move on to its next random action.

def set_number_input(page, label: str, value) -> bool:
    box = page.locator('[data-testid="stNumberInput"]').filter(has_text=label).first
    if box.count() == 0:
        return False
    field = box.locator("input").first
    field.click()
    field.fill(str(value))
    field.press("Enter")
    return True


def set_text_input(page, label: str, value: str) -> bool:
    box = page.locator('[data-testid="stTextInput"]').filter(has_text=label).first
    if box.count() == 0:
        return False
    field = box.locator("input").first
    field.click()
    field.fill("")
    field.type(value, delay=40)
    field.press("Enter")
    return True


def select_option(page, label: str, value: str) -> bool:
    """Type into a Streamlit selectbox and pick the first match -- tests/ui/_appserver.py's
    own idiom (selectbox = BaseWeb combobox, supports type-to-filter), reused verbatim for
    the one case here where the target option's TEXT is known up front (Laboratoires'
    structure picker)."""
    box = page.locator('[data-testid="stSelectbox"], [data-testid="stTextInput"]') \
        .filter(has_text=label).first
    if box.count() == 0:
        return False
    field = box.locator("input").first
    field.click()
    page.wait_for_timeout(300)
    field.fill("")
    field.type(value, delay=40)
    page.wait_for_timeout(900)
    page.keyboard.press("Enter")
    return True


def open_and_pick_option(page, label: str, index: int = 0) -> bool:
    """Open a Streamlit selectbox by its container label and click its Nth rendered
    `role=option` -- for the cases here where the option TEXT is not known up front
    (Exploration's dynamic element list, Portefeuille's colour-metric list), generalising
    BenchUp's own `resolve_picker_if_present`."""
    box = page.locator('[data-testid="stSelectbox"]').filter(has_text=label).first
    if box.count() == 0:
        return False
    box.locator("input").first.click()
    page.wait_for_timeout(250)
    opts = page.get_by_role("option")
    n = opts.count()
    if n == 0:
        page.keyboard.press("Escape")
        return False
    opts.nth(min(index, n - 1)).click()
    return True


def click_labeled_control(page, text: str) -> bool:
    """Click whatever renders `text` as a segmented-control option / radio / plain button
    -- used for the pass-7 BALANCE_MODES/PLANE_SELECT/LEVEL_TOGGLE values (widget SHAPE not
    yet decided when this file was written) and for Laboratoires' EXISTING wordcloud level
    switch (a confirmed `st.segmented_control`). Tries, in order: Streamlit's own segmented-
    control button shape (`button[data-variant='segmented_control']` -- a Streamlit-library
    DOM shape, not app CSS, so it should hold across apps on the same pinned Streamlit
    build; BenchUp's own harness independently confirmed the identical selector on the
    SAME 1.61.1 family), a `role=radio`, then any plain `button` with that exact text."""
    for loc in (
        page.locator("button[data-variant='segmented_control']").filter(has_text=text),
        page.get_by_role("radio", name=text),
        page.locator("button").filter(has_text=text),
    ):
        if loc.count():
            loc.first.click(timeout=5000)
            return True
    return False


def try_download(page, label: str, timeout_ms: int = 60_000):
    """60s (not Playwright's 30s default, not BenchUp's 45s): this app's workbook export
    reads a lazy-keyed parquet slice + builds sheets on a possibly-cold cache."""
    btn = page.get_by_role("button", name=label)
    if btn.count() == 0:
        return False, "button not found"
    try:
        with page.expect_download(timeout=timeout_ms) as dl_info:
            btn.first.click()
        return True, dl_info.value.suggested_filename
    except Exception as e:  # noqa: BLE001 -- chaos harness, every failure mode is recorded
        return False, str(e)


class Skip(Exception):
    """Raised by a phase-A action closure to mean "this widget does not exist on the page
    yet" (the 4 pass-7 controls, pre-W3). `step()` records this as `skipped=True`, distinct
    from `ok=False` -- a real assertion/exception failure -- so the dry run stays green
    today and the SAME closures start asserting for real once P-ZOOM/P-COL land."""


# --------------------------------------------------------------- phase A ----

def run_phase_a(page, base: str, sampler: RssSampler) -> list[dict]:
    """Deterministic replay of BUILD_PLAN.md P13's own crash path: Collaborations (floor,
    query, reciprocity) -> Zoom CNRS (the 4 new pass-7 controls, guarded) -> Zoom CHRU ->
    Géographie -> Exploration -> Portefeuille -> Laboratoires -> back to Collaborations.
    Every step is wrapped so one failure/skip does not abort the rest."""
    sampler.set_phase("A")
    steps: list[dict] = []

    def step(name: str, fn) -> None:
        t0 = time.time()
        try:
            fn()
            steps.append({"step": name, "ok": True, "skipped": False,
                         "s": round(time.time() - t0, 2), "error": ""})
        except Skip as e:
            steps.append({"step": name, "ok": True, "skipped": True,
                         "s": round(time.time() - t0, 2), "error": str(e)})
        except Exception as e:  # noqa: BLE001
            steps.append({"step": name, "ok": False, "skipped": False,
                         "s": round(time.time() - t0, 2), "error": str(e)[:300]})

    def _menu_to_collaborations():
        goto(page, base, "")
        assert_no_error(page, "menu")
        ok = click_sidebar_nav_link(page, "Collaborations")
        assert ok, "sidebar link 'Collaborations' not found"
        assert_no_error(page, "collaborations")

    def _col_floor():
        ok = set_number_input(page, "Seuil (co-publications)", 30)
        assert ok, "floor number_input ('Seuil (co-publications)') not found"
        settle(page)

    def _col_query():
        ok = set_text_input(page, "Rechercher :", "CNRS")
        assert ok, "query text_input ('Rechercher :') not found (N<50 floor hides it?)"
        settle(page)

    def _col_reciprocity_visible():
        assert page.get_by_text("Réciprocité", exact=True).count() > 0, \
            "'Réciprocité' heading not visible on Collaborations"

    def _zoom_cnrs_open():
        goto(page, base, f"/Zoom_partenaire?partner_id={PARTNER_ID_CNRS}")
        assert_no_error(page, "zoom CNRS")
        assert page.get_by_text("Réciprocité stratégique par champ", exact=False).count() > 0, \
            "reciprocity panel not found on Zoom partenaire (CNRS)"

    def _zoom_plane(label: str):
        if not click_labeled_control(page, label):
            raise Skip(f"plane option {label!r} not offered (PLANE_SELECT pre-P-ZOOM)")
        settle(page)

    def _zoom_plane_slider():
        slider = page.locator('[data-testid="stSlider"] input[type="range"]').first
        if slider.count() == 0:
            raise Skip("plane slider not offered (pre-P-ZOOM)")
        slider.click(force=True)
        slider.press("ArrowRight")
        settle(page)

    def _zoom_level_toggle_sous_champ():
        target = LABELS["LEVEL_TOGGLE"][1]  # "Top 30 sous-champs (volume conjoint)"
        if not click_labeled_control(page, target):
            raise Skip(f"level toggle {target!r} not offered (pre-P-ZOOM)")
        settle(page)

    def _zoom_balance(label: str):
        if not click_labeled_control(page, label):
            raise Skip(f"balance mode {label!r} not offered (pre-P-ZOOM)")
        settle(page)

    def _zoom_page_workbook():
        ok, info = try_download(page, LABELS["PAGE_WORKBOOK"])
        if not ok and info == "button not found":
            raise Skip("page-workbook button not offered yet (P16 lands with P-COL/P-ZOOM)")
        assert ok, f"page workbook download failed: {info}"

    def _zoom_chru_open():
        goto(page, base, f"/Zoom_partenaire?partner_id={PARTNER_ID_CHRU}")
        assert_no_error(page, "zoom CHRU")

    def _geographie_afficher_plus():
        ok = click_sidebar_nav_link(page, "Géographie")
        assert ok, "sidebar link 'Géographie' not found"
        assert_no_error(page, "geographie")
        btn = page.get_by_role("button", name="afficher plus")
        if btn.count() == 0:
            raise Skip("'afficher plus' button not present in this page state")
        btn.first.click()
        settle(page)

    def _exploration_one_element():
        ok = click_sidebar_nav_link(page, "Exploration thématique")
        assert ok, "sidebar link 'Exploration thématique' not found"
        assert_no_error(page, "exploration")
        picked = open_and_pick_option(page, "Choisir l'élément :", index=0)
        assert picked, "element selectbox ('Choisir l'élément :') not found/empty"
        settle(page)

    def _portefeuille_visit():
        ok = click_sidebar_nav_link(page, "Portefeuille thématique")
        assert ok, "sidebar link 'Portefeuille thématique' not found"
        assert_no_error(page, "portefeuille")
        open_and_pick_option(page, "Colorer par :", index=1)
        settle(page)

    def _laboratoires_pick_lab():
        ok = click_sidebar_nav_link(page, "Laboratoires")
        assert ok, "sidebar link 'Laboratoires' not found"
        assert_no_error(page, "laboratoires")
        picked = select_option(page, "Sélectionner une structure", LAB_PICK)
        assert picked, f"structure picker not found (wanted {LAB_PICK!r})"
        settle(page)

    def _laboratoires_wordcloud_level():
        ok = click_labeled_control(page, "Topics")
        assert ok, "wordcloud level switch ('Topics') not found"
        settle(page)

    def _back_to_collaborations():
        ok = click_sidebar_nav_link(page, "Collaborations")
        assert ok, "sidebar link 'Collaborations' (return hop) not found"
        assert_no_error(page, "collaborations (2nd visit)")

    step("menu -> collaborations", _menu_to_collaborations)
    step("collaborations: floor change", _col_floor)
    step("collaborations: query 'CNRS'", _col_query)
    step("collaborations: reciprocity visible", _col_reciprocity_visible)
    step("zoom CNRS: open", _zoom_cnrs_open)
    for key, plabel in LABELS["PLANE_SELECT"].items():
        step(f"zoom CNRS: plane {key}", lambda plabel=plabel: _zoom_plane(plabel))
    step("zoom CNRS: plane slider", _zoom_plane_slider)
    step("zoom CNRS: level toggle sous_champ", _zoom_level_toggle_sous_champ)
    for key, blabel in LABELS["BALANCE_MODES"].items():
        step(f"zoom CNRS: balance {key}", lambda blabel=blabel: _zoom_balance(blabel))
    step("zoom CNRS: page workbook download", _zoom_page_workbook)
    step("zoom CHRU: open", _zoom_chru_open)
    step("geographie: afficher plus", _geographie_afficher_plus)
    step("exploration: pick one element", _exploration_one_element)
    step("portefeuille: visit + change colour metric", _portefeuille_visit)
    step("laboratoires: pick lab (IJL)", _laboratoires_pick_lab)
    step("laboratoires: wordcloud level switch", _laboratoires_wordcloud_level)
    step("back to collaborations", _back_to_collaborations)

    return steps


# --------------------------------------------------------------- phase B ----

CHAOS_ACTIONS = ["nav_page", "zoom_partner", "zoom_controls", "col_controls", "geo_more",
                 "download", "scroll"]


def chaos_session(session_id: int, base: str, minutes: float, seed: int, out: dict,
                  t0: float | None = None) -> None:
    """One concurrent browser context (own `sync_playwright()` instance per thread).
    Randomised action loop, NO waiting for spinners -- only the 300-1500ms pause -- so this
    genuinely fires actions faster than the app can settle, the whole point of "chaos"."""
    rng = random.Random(seed * 1000 + session_id)
    t_start = t0 if t0 is not None else time.time()
    deadline = time.time() + minutes * 60
    actions = 0
    failures: list[str] = []
    action_log: list[tuple[float, str]] = []
    last_download = 0.0
    plane_labels = list(LABELS["PLANE_SELECT"].values())
    balance_labels = list(LABELS["BALANCE_MODES"].values())
    level_labels = list(LABELS["LEVEL_TOGGLE"])
    query_pool = ["CNRS", "Inserm", "Nancy", "Strasbourg", "CHU", ""]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport=VIEWPORT, accept_downloads=True)
        page = context.new_page()
        try:
            page.goto(base, wait_until="commit")
        except Exception as e:  # noqa: BLE001
            failures.append(f"init: {e}")

        while time.time() < deadline:
            action = rng.choice(CHAOS_ACTIONS)
            action_log.append((round(time.time() - t_start, 2), action))
            try:
                if action == "nav_page":
                    click_sidebar_nav_link(page, rng.choice(NAV_PAGES), wait=False)
                elif action == "zoom_partner":
                    pid = rng.choice(SEED_IDS)
                    page.goto(f"{base}/Zoom_partenaire?partner_id={pid}", wait_until="commit")
                elif action == "zoom_controls":
                    if "/Zoom_partenaire" not in page.url:
                        pid = rng.choice(SEED_IDS)
                        page.goto(f"{base}/Zoom_partenaire?partner_id={pid}", wait_until="commit")
                    choice = rng.randrange(4)
                    if choice == 0:
                        click_labeled_control(page, rng.choice(plane_labels))
                    elif choice == 1:
                        slider = page.locator('[data-testid="stSlider"] input[type="range"]').first
                        if slider.count():
                            slider.click(force=True, timeout=5000)
                            slider.press(rng.choice(["ArrowLeft", "ArrowRight"]))
                    elif choice == 2:
                        click_labeled_control(page, rng.choice(level_labels))
                    else:
                        click_labeled_control(page, rng.choice(balance_labels))
                elif action == "col_controls":
                    if "/Collaborations" not in page.url:
                        click_sidebar_nav_link(page, "Collaborations", wait=False)
                    if rng.random() < 0.5:
                        set_number_input(page, "Seuil (co-publications)",
                                        rng.choice([10, 20, 30, 50, 100]))
                    else:
                        set_text_input(page, "Rechercher :", rng.choice(query_pool))
                elif action == "geo_more":
                    if "/Géographie" not in page.url:
                        click_sidebar_nav_link(page, "Géographie", wait=False)
                    btn = page.get_by_role("button", name="afficher plus")
                    if btn.count():
                        btn.first.click(timeout=5000)
                elif action == "download":
                    now = time.time()
                    if now - last_download >= 60:  # <= 1 / minute / session
                        last_download = now
                        if "/Zoom_partenaire" not in page.url:
                            pid = rng.choice(SEED_IDS)
                            page.goto(f"{base}/Zoom_partenaire?partner_id={pid}", wait_until="commit")
                        if page.get_by_role("button", name=LABELS["PAGE_WORKBOOK"]).count():
                            ok, info = try_download(page, LABELS["PAGE_WORKBOOK"])
                            if not ok:
                                failures.append(f"download[page_workbook]: {info}")
                elif action == "scroll":
                    scroll_main(page, rng.randint(0, 6000))

                actions += 1
                if has_error_box(page):
                    failures.append(f"error box after {action}")
                    page.goto(base, wait_until="commit")  # recover, don't sink the session
            except Exception as e:  # noqa: BLE001
                actions += 1
                failures.append(f"{action}: {str(e)[:200]}")
                try:
                    page.goto(base, wait_until="commit")
                except Exception:  # noqa: BLE001
                    pass

            page.wait_for_timeout(rng.randint(300, 1500))

        browser.close()

    out[session_id] = {"actions": actions, "failures": failures, "n_failures": len(failures),
                       "action_log": action_log}


def run_phase_b(base: str, sessions: int, minutes: float, seed: int, sampler: RssSampler) -> dict:
    sampler.set_phase("B")
    results: dict[int, dict] = {}
    threads = [threading.Thread(target=chaos_session, args=(i, base, minutes, seed, results, sampler.t0))
               for i in range(sessions)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=minutes * 60 + 120)
    return results


# ------------------------------------------------------------------ main ----

def final_health_check(base: str) -> bool:
    """One fresh page load after every phase -- the generous timeout (cold Menu.py render:
    manifest + index length read), not the tight one chaos actions use."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(base, wait_until="load", timeout=45_000)
            # h1/h2/h3 (tag selector), not `[role="heading"]`: a native <h1> carries an
            # IMPLICIT accessibility role, no literal role= attribute, so the CSS
            # attribute-selector form matches nothing and always times out.
            page.wait_for_selector("h1, h2, h3", timeout=30_000)
            ok = page.get_by_role("heading").count() > 0
            browser.close()
            return ok
    except Exception:  # noqa: BLE001
        return False


def write_report(path: Path, csv_path: Path, actions_csv_path: Path, cfg: dict, sampler: RssSampler,
                 phase_a_steps, phase_b_results, server_alive: bool, final_ok: bool) -> tuple[str, bool]:
    phases_run = cfg["phases"]
    stats = {ph: sampler.phase_stats(ph) for ph in phases_run}
    overall_vals = [mb for _, p, mb in sampler.samples if p in phases_run]
    overall_peak = max(overall_vals) if overall_vals else None

    a_fail = sum(1 for s in (phase_a_steps or []) if not s["ok"])
    a_skip = sum(1 for s in (phase_a_steps or []) if s.get("skipped"))
    b_fail = sum(r["n_failures"] for r in (phase_b_results or {}).values())
    b_actions = sum(r["actions"] for r in (phase_b_results or {}).values())

    # PASS gate matches BUILD_PLAN.md P13 exactly: peak + server-alive + final-health only.
    # Phase A/B step failures/skips are diagnostic, never gating (same as the harness this
    # was ported from) -- a widget genuinely missing pre-W3 must not fail today's dry run.
    passed = (overall_peak is not None and overall_peak < PEAK_CEILING_MB
             and server_alive and final_ok)

    lines = []
    lines.append(f"# Stress report -- {cfg['timestamp']}")
    lines.append("")
    lines.append("## Config")
    lines.append("")
    for k, v in cfg.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")
    lines.append("## Peak / mean / final RSS per phase (MB, WorkingSetSize)")
    lines.append("")
    lines.append("| phase | n samples | peak | mean | final |")
    lines.append("|---|---|---|---|---|")
    for ph in phases_run:
        s = stats[ph]
        if s["n"] == 0:
            lines.append(f"| {ph} | 0 | - | - | - |")
        else:
            lines.append(f"| {ph} | {s['n']} | {s['peak']:.1f} | {s['mean']:.1f} | {s['final']:.1f} |")
    if overall_peak is not None:
        lines.append(f"| **overall** | {len(overall_vals)} | {overall_peak:.1f} |  |  |")
    else:
        lines.append("| **overall** | 0 | - | | |")
    lines.append("")
    lines.append(f"Ceiling: peak < {PEAK_CEILING_MB:.0f} MB (half the 2.7 GB Community Cloud cap).")
    lines.append("")

    if phase_a_steps is not None:
        lines.append("## Phase A -- deterministic crash-path replay")
        lines.append("")
        lines.append(f"{len(phase_a_steps) - a_fail - a_skip}/{len(phase_a_steps)} steps ok, "
                     f"{a_skip} skipped (pass-7 controls not landed yet), {a_fail} failed.")
        lines.append("")
        lines.append("| step | ok | skipped | s | error |")
        lines.append("|---|---|---|---|---|")
        for s in phase_a_steps:
            lines.append(f"| {s['step']} | {s['ok']} | {s.get('skipped', False)} | {s['s']} | {s.get('error', '')} |")
        lines.append("")

    if phase_b_results is not None:
        lines.append("## Phase B -- chaos (concurrent sessions)")
        lines.append("")
        lines.append(f"Total actions: {b_actions}. Total failures: {b_fail}.")
        lines.append("")
        lines.append("| session | actions | failures |")
        lines.append("|---|---|---|")
        for sid, r in sorted(phase_b_results.items()):
            lines.append(f"| {sid} | {r['actions']} | {r['n_failures']} |")
        if b_fail:
            lines.append("")
            lines.append("Failure detail (first 20):")
            n = 0
            for sid, r in sorted(phase_b_results.items()):
                for f in r["failures"]:
                    if n >= 20:
                        break
                    lines.append(f"- session {sid}: {f}")
                    n += 1
        lines.append("")

    lines.append("## Server health")
    lines.append("")
    lines.append(f"- server alive throughout (PID never became unreadable): {server_alive}"
                 + (f" (died at t={sampler.died_at:.1f}s)" if sampler.died_at is not None else ""))
    lines.append(f"- final page load after all phases: {'ok' if final_ok else 'FAILED'}")
    lines.append(f"- server stdout/stderr log: `{cfg.get('server_log_name', '')}`")
    lines.append("")
    lines.append(f"## Result: {'PASS' if passed else 'FAIL'}")
    lines.append("")
    lines.append(f"Samples CSV: `{csv_path.name}`")
    if phase_b_results is not None:
        lines.append(f"Phase-B action log CSV: `{actions_csv_path.name}` -- (session, elapsed_s, "
                     f"action), elapsed_s on the SAME axis as the samples CSV: find the peak "
                     f"window in the samples CSV, then filter this one to that window to see "
                     f"which actions ran in which session(s) around it.")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["elapsed_s", "phase", "rss_mb"])
        for t, ph, mb in sampler.samples:
            w.writerow([f"{t:.2f}", ph, f"{mb:.2f}"])

    if phase_b_results is not None:
        with actions_csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["session", "elapsed_s", "action"])
            for sid, r in sorted(phase_b_results.items()):
                for t, action in r.get("action_log", []):
                    w.writerow([sid, f"{t:.2f}", action])

    return ("PASS" if passed else "FAIL"), passed


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 -- best-effort; cp1252 console fallback still ASCII-safe below
        pass

    ap = argparse.ArgumentParser(description="Lorraine Explorer v2 memory stress harness (P13).")
    ap.add_argument("--minutes", type=float, default=8.0, help="phase B duration per session, minutes")
    ap.add_argument("--sessions", type=int, default=3, help="concurrent chaos sessions (phase B)")
    ap.add_argument("--port", type=int, default=8651)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--phases", type=str, default="A,B", help="comma list from A,B")
    ap.add_argument("--out", type=str, default=str(STRESS_DIR / "reports"))
    args = ap.parse_args()

    phases = [p.strip().upper() for p in args.phases.split(",") if p.strip()]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cap_env = os.environ.get("LORRAINE_READ_KEYED_CAP", "8 (default)")
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    base = f"http://127.0.0.1:{args.port}"

    server_log_path = out_dir / f"STRESS_{stamp}_server.log"
    print(f"[stress] starting server on port {args.port} "
         f"(LORRAINE_READ_KEYED_CAP={cap_env}) ... log: {server_log_path}")
    server = start_server(args.port, server_log_path)
    server_pid: int | None = None
    sampler: RssSampler | None = None
    phase_a_steps = None
    phase_b_results = None
    server_alive = False
    final_ok = False

    try:
        if not _wait_for_port(args.port, timeout=90):
            print("FAIL: server did not open its port within 90s")
            return 1
        server_pid = _find_listening_pid(args.port, timeout=30)
        if server_pid is None:
            print("FAIL: could not resolve which PID is LISTENING on the port (netstat)")
            return 1
        rss0 = process_rss_mb(server_pid)
        if rss0 is None:
            print(f"FAIL: could not read RSS for resolved server PID {server_pid}")
            return 1
        same = "same as launched process" if server_pid == server.pid else \
              f"DIFFERENT from launched process pid {server.pid} (Windows child, see module docstring)"
        print(f"[stress] server PID {server_pid} confirmed readable, {rss0[0]:.1f} MB at boot ({same})")

        sampler = RssSampler(server_pid)
        sampler.start()

        if "A" in phases:
            print("[stress] phase A: deterministic crash-path replay ...")
            with sync_playwright() as p:
                browser = p.chromium.launch()
                context = browser.new_context(viewport=VIEWPORT, accept_downloads=True)
                page = context.new_page()
                page.set_default_timeout(60_000)  # cold reads/figure builds can take a while
                phase_a_steps = run_phase_a(page, base, sampler)
                browser.close()
            n_fail = sum(1 for s in phase_a_steps if not s["ok"])
            n_skip = sum(1 for s in phase_a_steps if s.get("skipped"))
            print(f"[stress] phase A done: {len(phase_a_steps) - n_fail - n_skip}/{len(phase_a_steps)} "
                 f"ok, {n_skip} skipped, {n_fail} failed")

        if "B" in phases:
            print(f"[stress] phase B: {args.sessions} sessions x {args.minutes} min chaos ...")
            phase_b_results = run_phase_b(base, args.sessions, args.minutes, args.seed, sampler)
            b_actions = sum(r["actions"] for r in phase_b_results.values())
            b_fail = sum(r["n_failures"] for r in phase_b_results.values())
            print(f"[stress] phase B done: {b_actions} actions, {b_fail} failures")

        sampler.set_phase("post")
        server_alive = sampler.died_at is None and server.poll() is None
        final_ok = final_health_check(base)
        print(f"[stress] server_alive={server_alive} final_page_ok={final_ok}")

    finally:
        if sampler is not None:
            sampler.stop()
        stop_server(server, server_pid)
        print("[stress] server stopped")

    if sampler is None:
        return 1

    cfg = {
        "timestamp": stamp, "port": args.port, "sessions": args.sessions,
        "minutes_per_session": args.minutes, "seed": args.seed, "phases": phases,
        "cap_env": cap_env, "server_log_name": server_log_path.name,
    }
    report_path = out_dir / f"STRESS_{stamp}.md"
    csv_path = out_dir / f"STRESS_{stamp}_samples.csv"
    actions_csv_path = out_dir / f"STRESS_{stamp}_actions.csv"
    result, passed = write_report(report_path, csv_path, actions_csv_path, cfg, sampler,
                                  phase_a_steps, phase_b_results, server_alive, final_ok)

    print("\n=== STRESS SUMMARY ===")
    print(f"config: sessions={args.sessions} minutes={args.minutes} seed={args.seed} "
         f"cap_env={cap_env} port={args.port} phases={phases}")
    for ph in phases:
        s = sampler.phase_stats(ph)
        if s["n"]:
            print(f"phase {ph}: peak={s['peak']:.1f} MB mean={s['mean']:.1f} MB "
                 f"final={s['final']:.1f} MB n={s['n']}")
        else:
            print(f"phase {ph}: no samples")
    overall_vals = [mb for _, p, mb in sampler.samples if p in phases]
    if overall_vals:
        print(f"overall peak: {max(overall_vals):.1f} MB (ceiling {PEAK_CEILING_MB:.0f} MB)")
    print(f"server_alive={server_alive} final_page_ok={final_ok}")
    print(f"RESULT: {result}")
    print(f"report: {report_path}")
    print(f"csv: {csv_path}")
    if phase_b_results is not None:
        print(f"actions csv: {actions_csv_path}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
