# tests/test_cache_rules.py
"""
tests/test_cache_rules.py -- two permanent static-analysis gates over Streamlit/ (P12):

  S3 test_orphan_loaders_have_no_caller: `lib/data_cache.py` carries 5 loaders with ZERO
  real callers today (`get_core_df` 132.8 MB, `get_partners_df`, `get_authors_df`,
  `load_partners_base`, `get_lookup_df` -- reports/CACHE_DIAGNOSIS.md §4's "adjacent
  finding": grep-confirmed zero call sites beyond their own definitions). Their own
  docstrings claim a future seam, so this is a GUARD, not a deletion: an AST walk over
  every Streamlit/**/*.py file fails, naming file:line, the moment any of the 5 is
  called from anywhere OTHER than lib/data_cache.py itself.

  S7 test_every_parametrised_cache_data_has_max_entries: every `@st.cache_data(...)`
  decorating a function that takes >=1 non-underscore-prefixed parameter must pass
  `max_entries=` (nullary functions are exempt by construction -- Streamlit bounds them
  to at most 1 live entry regardless; `st.cache_resource` is a different decorator,
  exempt here -- S4 converts the page 8/9 `cache_resource` loaders separately, see
  reports/pass7_cache.md). RATCHET: `EXEMPT` is seeded with every genuine violator found
  on 2026-09-10 (12, listed below). The test fails if the CURRENT violation set differs
  from EXEMPT in EITHER direction: a new, un-exempted violation, OR an EXEMPT entry that
  no longer violates -- which must be REMOVED from the list, not left stale. Page
  streams remove their own 2 entries as S1 lands in W3 (see this worker's progress note,
  section "Lines for page streams"); pass 7b is expected to empty whatever remains.

Both checks parse source as TEXT via `ast` -- neither imports streamlit nor any `lib.*`
module, so this file needs none of tests/conftest.py's sys.modules namespace-collision
guard (see that file's own docstring): there is nothing here for a `from lib.xxx import
yyy` to collide with, which keeps this file fast and dependency-free.

    python -m pytest tests/test_cache_rules.py -q
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STREAMLIT_DIR = ROOT / "Streamlit"

try:
    # cp1252 console (_COMMON.md): a failure message can carry a page's emoji filename.
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _iter_py_files(root: Path):
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


# ============================================================================
# S3 -- orphan loader guard
# ============================================================================

ORPHAN_LOADERS = {"get_core_df", "get_partners_df", "get_authors_df", "load_partners_base", "get_lookup_df"}


def _callee_name(call: ast.Call) -> str | None:
    """Best-effort callee name for both call shapes seen in this codebase:
    `get_core_df()` (ast.Name) and `data_cache.get_core_df()` (ast.Attribute)."""
    fn = call.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return None


def _find_orphan_loader_calls(root: Path, exempt_file: Path) -> list[tuple[str, int]]:
    """(relpath, lineno) for every Call node anywhere under `root` whose callee name is
    one of ORPHAN_LOADERS, except inside `exempt_file` (their own home, where they may
    legitimately call each other or be reached by a future seam)."""
    violations: list[tuple[str, int]] = []
    exempt_resolved = exempt_file.resolve()
    for py_file in _iter_py_files(root):
        if py_file.resolve() == exempt_resolved:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _callee_name(node) in ORPHAN_LOADERS:
                violations.append((py_file.relative_to(root).as_posix(), node.lineno))
    return violations


def test_orphan_loaders_have_no_caller():
    violations = _find_orphan_loader_calls(STREAMLIT_DIR, STREAMLIT_DIR / "lib" / "data_cache.py")
    assert violations == [], (
        "orphan loader(s) called outside lib/data_cache.py -- guard, not delete (P12/S3; "
        "their own docstrings claim a future seam -- reports/CACHE_DIAGNOSIS.md §4):\n"
        + "\n".join(f"  Streamlit/{f}:{ln}" for f, ln in violations)
    )


def test_orphan_guard_is_not_vacuous(tmp_path):
    """Vacuity (P14): the walker MUST be able to catch a real violation, or it is
    theater. A synthetic module under tmp_path calls get_core_df() -- must be caught."""
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "data_cache.py").write_text("def get_core_df():\n    return None\n", encoding="utf-8")
    bad = tmp_path / "fake_caller.py"
    bad.write_text("from lib.data_cache import get_core_df\n\ndf = get_core_df()\n", encoding="utf-8")

    violations = _find_orphan_loader_calls(tmp_path, tmp_path / "lib" / "data_cache.py")
    assert violations, "vacuity check FAILED: a synthetic caller of get_core_df() under tmp_path was not caught"
    assert violations == [("fake_caller.py", 3)], f"unexpected violations shape: {violations}"


# ============================================================================
# S7 -- max_entries lint (ratchet)
# ============================================================================

# Seeded 2026-09-10 (P12/S7): every @st.cache_data(...) app-wide, over a parametrised
# function (>=1 non-underscore param), that does NOT pass max_entries= today (12 total).
# RATCHET below: every entry here must still exist AND still violate, or the test fails
# -- a fixed entry left in this list is caught, not silently tolerated.
EXEMPT: set[tuple[str, str]] = {
    ("lib/thematic.py", "_sdg_tagged_work_ids"),
    ("lib/thematic.py", "_recompute_overview"),
    ("lib/thematic.py", "excluded_counts"),
    ("lib/thematic.py", "_recompute_sublevels"),
    ("pages/2_🏭_Laboratoires.py", "_load_table"),
    ("pages/2_🏭_Laboratoires.py", "_lab_set"),
    ("pages/2_🏭_Laboratoires.py", "_lab_works_slice"),  # S1 (P12): S-SDG lands max_entries=64 in W3
    ("pages/2_🏭_Laboratoires.py", "recomputed_structure_counts"),
    ("pages/2_🏭_Laboratoires.py", "_lab_wordcloud_slice"),  # S1 (P12): S-SDG lands max_entries=64 in W3
    ("pages/4_🔬_Portefeuille_thématique.py", "_load_table"),
    ("pages/4_🔬_Portefeuille_thématique.py", "sdg_assignments"),
    ("pages/5_📍_Positionnement.py", "_load_table"),
}


def _decorator_targets_cache_data(dec: ast.expr) -> bool:
    """True for both `@st.cache_data` (bare) and `@st.cache_data(...)` (called) --
    matched on the attribute name alone (not the object name) so an alias other than
    the app's universal `import streamlit as st` would still be caught."""
    node = dec.func if isinstance(dec, ast.Call) else dec
    return isinstance(node, ast.Attribute) and node.attr == "cache_data"


def _has_max_entries_kw(dec: ast.expr) -> bool:
    return isinstance(dec, ast.Call) and any(kw.arg == "max_entries" for kw in dec.keywords)


def _param_names(fn) -> list[str]:
    a = fn.args
    return [p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)]


def _is_parametrised(fn) -> bool:
    """>=1 parameter whose name does NOT start with '_' (Streamlit's own
    hash-exclusion convention for a leading-underscore parameter name, e.g.
    lib/fig_cache.py's `_build`)."""
    return any(not name.startswith("_") for name in _param_names(fn))


def _find_cache_data_violations(root: Path) -> set[tuple[str, str]]:
    violations: set[tuple[str, str]] = set()
    for py_file in _iter_py_files(root):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if _decorator_targets_cache_data(dec) and _is_parametrised(node) and not _has_max_entries_kw(dec):
                    violations.add((py_file.relative_to(root).as_posix(), node.name))
    return violations


def test_every_parametrised_cache_data_has_max_entries():
    found = _find_cache_data_violations(STREAMLIT_DIR)
    extra = found - EXEMPT
    stale = EXEMPT - found
    assert not extra, (
        "NEW @st.cache_data violation(s) (parametrised, no max_entries=) not in EXEMPT -- "
        "add max_entries= to the decorator, or extend EXEMPT if genuinely deferred:\n"
        + "\n".join(f"  {f} :: {fn}" for f, fn in sorted(extra))
    )
    assert not stale, (
        "EXEMPT entry no longer violates -- remove it from the list (ratchet, P12/S7):\n"
        + "\n".join(f"  {f} :: {fn}" for f, fn in sorted(stale))
    )


def test_max_entries_lint_is_not_vacuous(tmp_path):
    """Vacuity (P14): a synthetic parametrised @st.cache_data with no max_entries=
    must be caught."""
    bad = tmp_path / "bad_module.py"
    bad.write_text(
        "import streamlit as st\n\n@st.cache_data\ndef load_thing(key):\n    return key\n",
        encoding="utf-8",
    )
    found = _find_cache_data_violations(tmp_path)
    assert found == {("bad_module.py", "load_thing")}, f"vacuity check FAILED: got {found}"
