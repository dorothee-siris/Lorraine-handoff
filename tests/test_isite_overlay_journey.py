# tests/test_isite_overlay_journey.py
"""
Pass-5 (R1) AppTest pins for the `isite_overlay` sidebar toggle's SCRIPT-LEVEL
behaviour across `AppTest.switch_page()` calls.

HONEST SCOPE (rewritten, F-VAC-01 fix, pass-5 FIX-1 round -- read this before trusting
any test name below). This file's ORIGINAL docstring claimed it "REPLACES the retired
CX-FIX perimeter-persistence pin's role as the BINDING cross-page proof" that
`persist_state="session"` makes a toggle survive real navigation. That claim was
FALSE, proven by direct mutation (docs/INSPECTION_REPORT_1.md §3(b), reproduced again
in `progress/FIX1.md` for this fix round): deleting `persist_state="session"` entirely
from `isite_overlay_toggle()` in a scratch copy of `lib/controls.py` and re-running
`python -m pytest tests/test_isite_overlay_journey.py -q` still gives 7/7 PASSING --
every test in this file keeps passing even with the exact mechanism it is named after
completely removed.

Root cause: `AppTest` keeps ONE Python `session_state` dict alive across every
`.run()`/`.switch_page()` call within a single `AppTest` object -- it never tears down
and recreates a session the way a real second browser visit does, and it never
exercises the per-page widget-id hashing that `persist_state="session"` exists to
survive. So `switch_page()` proves the DESTINATION page's script re-executes correctly
under an ALREADY-POPULATED session_state dict (a real, useful thing to pin -- e.g. that
`from lib import controls` resolves, that the toggle's `key` is read consistently, that
no exception fires on re-entry) -- it does NOT prove a value would survive transport
between two INDEPENDENT script runs the way a live page reload / sidebar click does.
Every test below is renamed to say exactly that ("reexecutes with the value still set
in session_state"), never "persists" or "sticks" or "survives a hop".

The REAL persistence proof now lives in `tests/ui/smoke.py`'s
`check_persistence_journey()` -- a real Playwright browser driving a real running
Streamlit server, navigating via REAL `[data-testid="stSidebarNav"] a` clicks (never
`page.goto()`, which itself gives false failures by tearing down the WebSocket session
-- see that function's own docstring and docs/INSPECTION_REPORT_1.md §3(a)'s
methodology note). That is the binding proof this file's original docstring
overclaimed to be.

What THIS file still IS good for, and why it stays (not deleted): a fast (~20s vs.
smoke's multi-minute run), in-suite regression check that the toggle's mechanism-level
plumbing does not break -- the widget's `key` resolves, `switch_page()` re-executes the
destination page without raising, and the value read back from `session_state`
immediately after a same-object `.run()` matches what was set. That is a real,
worthwhile, narrow guarantee. It is a mechanism-structure test, not a persistence proof.

Namespace note (F-SYSMOD fix, pass-5 FIX-1 round): this repo has TWO packages named
`lib` (the repo-root pipeline one and Streamlit/lib, the app one). AppTest re-executes
each page's REAL script on every `.run()` call -- including one that runs `from
lib.data_cache import ...` -- so this file needs the Streamlit `lib` binding to stay
correct across MANY `.run()` calls spanning several test functions. `setup_module`/
`teardown_module` (pytest's classic whole-file hooks) swap it in for this file's
entire run and restore whatever was there before once every test in this file is
done -- now by delegating to tests/conftest.py's ONE centralized implementation
(`swap_lib_to_streamlit`/`restore_lib`) instead of this file's own copy of the guard.

    python -m pytest tests/test_isite_overlay_journey.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
PAGES_DIR = STREAMLIT_DIR / "pages"

LAB_PAGE = "2_\U0001F3ED_Laboratoires.py"
THEMATIC_PAGE = "4_\U0001F52C_Portefeuille_thématique.py"
COLLAB_PAGE = "8_\U0001F91D_Collaborations.py"

TIMEOUT = 90.0

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    # F-SYSMOD fix (MINOR): one-line fallback so `conftest` stays importable even if
    # this file is ever run as a standalone script, not just via pytest.
    sys.path.insert(0, str(_TESTS_DIR))
from conftest import restore_lib, swap_lib_to_streamlit  # centralized guard, see conftest.py

_saved_lib_modules: dict = {}


def setup_module(_module) -> None:
    """F-SYSMOD fix: delegates to tests/conftest.py's ONE centralized sys.modules['lib']
    guard (AppTest's page executions need Streamlit's own lib package correctly bound
    on EVERY `.run()` call, not just once -- see module docstring) instead of this
    file's own copy of the save/delete/insert-path dance."""
    global _saved_lib_modules
    _saved_lib_modules = swap_lib_to_streamlit()


def teardown_module(_module) -> None:
    """Restore whatever `lib` binding existed before this file ran."""
    restore_lib(_saved_lib_modules)


def _exc_values(at: AppTest) -> list:
    return [e.value for e in at.exception]


@pytest.fixture(scope="module")
def journey() -> AppTest:
    """One AppTest session across the whole mechanism-structure sweep (ONE shared
    Python session_state dict for every `.switch_page()` call below -- this is
    exactly the property that makes this file unable to prove cross-session
    persistence, per the module docstring). Module-scoped and consumed by ordered
    test functions below -- this repo runs plain pytest 7.4.0 with no random-order
    plugin, so file-definition order (leg0 -> leg4) holds."""
    at = AppTest.from_file(str(PAGES_DIR / LAB_PAGE))
    at.run(timeout=TIMEOUT)
    assert not at.exception, f"initial load raised: {_exc_values(at)}"
    return at


def test_toggle_defaults_off_on_first_load(journey):
    assert journey.sidebar.toggle(key="isite_overlay").value is False


def test_leg0_turn_on_is_reflected_in_session_state_immediately(journey):
    journey.sidebar.toggle(key="isite_overlay").set_value(True)
    journey.run(timeout=TIMEOUT)
    assert not journey.exception, _exc_values(journey)
    assert journey.session_state["isite_overlay"] is True


def test_leg1_switch_page_to_portefeuille_thematique_reexecutes_with_value_still_set(journey):
    """Proves: the destination page's script re-executes without raising, and reads
    back the value already sitting in the ONE shared session_state dict. Does NOT
    prove the value would survive a real, independent second script run (see module
    docstring) -- that proof is tests/ui/smoke.py's own real-browser journey."""
    journey.switch_page(THEMATIC_PAGE)
    journey.run(timeout=TIMEOUT)
    assert not journey.exception, _exc_values(journey)
    assert journey.session_state["isite_overlay"] is True
    assert journey.sidebar.toggle(key="isite_overlay").value is True


def test_leg2_switch_page_to_collaborations_reexecutes_with_value_still_set(journey):
    journey.switch_page(COLLAB_PAGE)
    journey.run(timeout=TIMEOUT)
    assert not journey.exception, _exc_values(journey)
    assert journey.session_state["isite_overlay"] is True
    assert journey.sidebar.toggle(key="isite_overlay").value is True


def test_leg3_switch_page_back_to_laboratoires_second_execution_value_still_set(journey):
    """A SECOND execution of a page already run once earlier in this same AppTest
    object -- still the SAME shared session_state dict throughout, so this is a
    stronger mechanism check (re-entrant script execution) than leg1/leg2, but it is
    still not the cross-session proof its pre-fix name claimed ("SECOND visit still
    on"). The real second-visit persistence proof is smoke.py's leg 2."""
    journey.switch_page(LAB_PAGE)
    journey.run(timeout=TIMEOUT)
    assert not journey.exception, _exc_values(journey)
    assert journey.session_state["isite_overlay"] is True
    assert journey.sidebar.toggle(key="isite_overlay").value is True


def test_leg4_switch_page_to_collaborations_second_execution_value_still_set(journey):
    journey.switch_page(COLLAB_PAGE)
    journey.run(timeout=TIMEOUT)
    assert not journey.exception, _exc_values(journey)
    assert journey.session_state["isite_overlay"] is True
    assert journey.sidebar.toggle(key="isite_overlay").value is True


def test_toggling_off_is_also_reflected_after_a_switch_page_call():
    """Symmetry check on a FRESH AppTest object (still one shared session_state for
    its own short life): OFF reads back correctly after a switch_page() call too,
    not just ON -- same mechanism-structure scope as every test above, not a
    cross-session proof."""
    at = AppTest.from_file(str(PAGES_DIR / COLLAB_PAGE))
    at.run(timeout=TIMEOUT)
    at.sidebar.toggle(key="isite_overlay").set_value(True)
    at.run(timeout=TIMEOUT)
    at.sidebar.toggle(key="isite_overlay").set_value(False)
    at.run(timeout=TIMEOUT)
    at.switch_page(LAB_PAGE)
    at.run(timeout=TIMEOUT)
    assert not at.exception, _exc_values(at)
    assert at.session_state["isite_overlay"] is False
    assert at.sidebar.toggle(key="isite_overlay").value is False
