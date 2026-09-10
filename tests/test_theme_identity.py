"""
tests/test_theme_identity.py -- QA-04/RA-B01 single-source pin (pass 4b, Codex fix F4).

Background: the shared `Streamlit/lib/helpers.py` DOMAIN_COLORS palette (used by pages 1, 3,
4, 11 via `get_domain_color()`/`DOMAIN_COLORS.get()`) disagreed with page 5's (I-SITE) former
page-local `DOMAIN_IDENTITY` dict -- same four domain names, four DIFFERENT hex values (Okabe-
Ito), whose Physical Sciences entry (#0072B2) also collided with the app-wide focal-blue role.
The review's own acceptance test: "same yellow for Social Sciences everywhere" -- it was
`#FFCB3A` on the shared palette and `#CC79A7` (magenta) on I-SITE.

Manager decision (final, this pass): the SHARED helpers.py palette wins (3+ page incumbent;
its Physical Sciences value, #8190FF, does not collide with focal blue). Fix: page 5's
DOMAIN_IDENTITY is deleted and rebuilt FROM `DOMAIN_COLORS` (`{name: DOMAIN_COLORS[name] for
name in DOMAIN_NAMES_ORDERED}`) -- single-sourced, not just visually matched.

This test pins that single-sourcing, NOT the values themselves -- a future Studio pass may
still re-decide the palette (RA-B01's "minimal single-source refactor" item 6 note): change
EXPECTED_HEX here and every page picks it up automatically, because there is exactly ONE place
(`lib.helpers.DOMAIN_COLORS`) the values live.

    python -m pytest tests/test_theme_identity.py -q

Namespace note: same `_import_streamlit_lib` swap-trick as tests/test_shared_layer.py (see its
docstring) -- Streamlit/lib and the repo-root pipeline `lib` package would otherwise collide
under the same `lib` name in `sys.modules`.
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
PAGES_DIR = STREAMLIT_DIR / "pages"


def _import_streamlit_lib(*names: str):
    saved = {k: v for k, v in sys.modules.items() if k == "lib" or k.startswith("lib.")}
    for k in saved:
        del sys.modules[k]
    sys.path.insert(0, str(STREAMLIT_DIR))
    try:
        mods = tuple(importlib.import_module(f"lib.{n}") for n in names)
    finally:
        sys.path.remove(str(STREAMLIT_DIR))
        for k in [k for k in sys.modules if k == "lib" or k.startswith("lib.")]:
            del sys.modules[k]
        sys.modules.update(saved)
    return mods


(helpers,) = _import_streamlit_lib("helpers")

DOMAIN_NAMES = ["Life Sciences", "Social Sciences", "Physical Sciences", "Health Sciences"]

# Pinned values, single-sourced from lib.helpers.DOMAIN_COLORS as of the QA-04/RA-B01 fix.
# A future Studio pass may change these -- change them HERE and the assertions below still
# hold, because every page reads the same dict this test reads.
EXPECTED_HEX = {
    "Life Sciences": "#0CA750",
    "Social Sciences": "#FFCB3A",
    "Physical Sciences": "#8190FF",
    "Health Sciences": "#F85C32",
}

HEX_PATTERN = r"#[0-9A-Fa-f]{6}"


def test_shared_domain_colors_are_the_pinned_values():
    """lib.helpers.DOMAIN_COLORS carries the values the manager ruling kept -- explicit
    per-name assertions; Social Sciences is the review's own acceptance-test example."""
    for name, hexcode in EXPECTED_HEX.items():
        assert helpers.DOMAIN_COLORS[name].upper() == hexcode, (
            f"lib.helpers.DOMAIN_COLORS[{name!r}] drifted from the pinned value {hexcode}"
        )
    assert helpers.DOMAIN_COLORS["Social Sciences"] == "#FFCB3A"


def test_domain_colors_by_id_and_by_name_agree():
    """DOMAIN_COLORS carries both an int-id and a string-name key per domain (helpers.py's
    own convention) -- they must resolve to the same hex, or the two lookup paths this app
    uses interchangeably (id-keyed blobs vs name-keyed dataframes) would silently disagree."""
    id_by_name = dict(zip(helpers.DOMAIN_NAMES_ORDERED, helpers.DOMAIN_ORDER))
    for name in DOMAIN_NAMES:
        dom_id = id_by_name[name]
        assert helpers.DOMAIN_COLORS[dom_id] == helpers.DOMAIN_COLORS[name], (
            f"DOMAIN_COLORS[{dom_id}] != DOMAIN_COLORS[{name!r}]"
        )


def _domain_hex_literals_in(path: Path) -> dict[str, str]:
    """Best-effort scan for a `"Domain Name": "#HEX"`-shaped literal pair in a page's own
    source (line-proximity regex, not an AST walk -- a drift TRIPWIRE, not a general-purpose
    colour parser). Pages import Streamlit-executing top-level code, so a real `import` of a
    page module is not safe/meaningful outside a live `streamlit run`; reading the source text
    is what RA-B01's own recommended check ("Minimal single-source refactor" item 6 / process
    appendix "inventory semantic colours ... not only duplicate hex codes") does instead."""
    text = path.read_text(encoding="utf-8")
    found: dict[str, str] = {}
    for name in DOMAIN_NAMES:
        m = re.search(rf'"{re.escape(name)}"\s*:\s*"({HEX_PATTERN})"', text)
        if m:
            found[name] = m.group(1).upper()
    return found


def test_no_page_hand_types_a_conflicting_domain_hex():
    """Grep-based sweep across every Streamlit page: any literal {domain name: hex} pair
    found must quote the SAME hex lib.helpers.DOMAIN_COLORS defines. Catches a future page
    reintroducing a page-local duplicate (like the deleted page-5 DOMAIN_IDENTITY) before it
    ships, without needing to import/run any page."""
    offenders = []
    for page in sorted(PAGES_DIR.glob("*.py")):
        for name, hexcode in _domain_hex_literals_in(page).items():
            expected = helpers.DOMAIN_COLORS[name].upper()
            if hexcode != expected:
                offenders.append(f"{page.name}: {name!r} = {hexcode} (shared palette: {expected})")
    assert not offenders, "conflicting page-local domain colour(s) found:\n" + "\n".join(offenders)


def test_isite_page_imports_shared_domain_colors_not_a_local_dict():
    """QA-04/RA-B01 fix itself: page 5 (I-SITE) must import DOMAIN_COLORS from lib.helpers.
    Its former page-local DOMAIN_IDENTITY dict (hand-typed Okabe-Ito values that disagreed
    with every other page) is gone; the name survives only as a display-order alias BUILT
    FROM the shared dict, never a re-typed literal."""
    # Pass-5 rename (P1 map): I-SITE moved from slot 5 ("5_..._ISITE.py") to slot 7
    # ("7_..._I-SITE.py", now with a hyphen) -- glob on the number, not the literal
    # "ISITE" substring, so this survives future emoji/spelling churn too.
    candidates = list(PAGES_DIR.glob("7_*I-SITE*.py")) or list(PAGES_DIR.glob("7_*.py"))
    assert candidates, "page 7 (I-SITE) not found under Streamlit/pages/"
    text = candidates[0].read_text(encoding="utf-8")
    # `[^)]` (not just `[^\n]`) so a parenthesised multi-line `from lib.helpers import (...)`
    # block -- DOMAIN_COLORS on its own continuation line -- still matches.
    assert re.search(r"from\s+lib\.helpers\s+import\s*\(?[^)]*?DOMAIN_COLORS", text), (
        "page 5 should import DOMAIN_COLORS from lib.helpers"
    )
    assert not _domain_hex_literals_in(candidates[0]), (
        "page 5 still hand-types a domain-name -> hex literal instead of reading DOMAIN_COLORS"
    )
