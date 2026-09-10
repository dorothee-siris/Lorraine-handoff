# tests/conftest.py
"""
F-SYSMOD fix (MINOR, pass-5 FIX-1 round): centralizes the `sys.modules['lib']`
namespace-collision guard that 9 test files previously each re-implemented as their
OWN independent copy.

The problem (reproduced directly, outside pytest, in docs/INSPECTION_REPORT_1.md §6
"Bonus" -- real, not theoretical): this repo has TWO packages literally named `lib` --
the pipeline's own `lib/` at the repo root, and `Streamlit/lib/`, the app's. Whichever
one gets imported FIRST inside one pytest PROCESS binds `sys.modules['lib']` for the
rest of that process; a later `from lib.controls import sidebar` (needing the OTHER
package) then raises `ModuleNotFoundError`, because Python treats `sys.modules['lib']`
as already resolved. `test_app_numbers.py`, `test_bench_peers.py`,
`test_contract_tables.py` and `test_invariants.py` need the ROOT `lib`; the 9 files
listed below need `Streamlit/lib` bound instead, for the DURATION of their own run
(AppTest re-executes real page scripts that do `from lib import controls, ...`).

Previously: each of those 9 files carried its OWN ~15-line save/delete-from-
sys.modules/insert-sys.path/restore dance in `setup_module`/`teardown_module` --
correct everywhere it mattered, but fragile (the inspection's own words): a NEW test
file that imports `Streamlit/lib` without the same guard, or a switch to
`pytest-randomly`/`pytest-xdist` (either of which can change collection order or run
files in separate workers), would silently reintroduce the failure. Centralizing the
one correct implementation here means there is now exactly ONE place this guard's
logic can be wrong, instead of 9.

Usage (each of the 9 files keeps its OWN `setup_module`/`teardown_module` -- this
is a MECHANISM swap, not a removal of the per-file hooks pytest already calls
automatically for that file's own run):

    _saved_lib_modules: dict = {}

    def setup_module(_module) -> None:
        global _saved_lib_modules
        _saved_lib_modules = swap_lib_to_streamlit()

    def teardown_module(_module) -> None:
        restore_lib(_saved_lib_modules)

`swap_lib_to_streamlit`/`restore_lib` are imported with a one-line fallback to a
locally-defined copy (see each file's own top) so every file STAYS independently
importable/runnable even outside a pytest collection run that has already loaded this
conftest.py onto `sys.path` (e.g. `python -c "import importlib.util; ..."` against a
bare file path, as used for ad-hoc debugging during this fix round).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STREAMLIT_DIR = ROOT / "Streamlit"


def swap_lib_to_streamlit() -> dict:
    """
    Save whatever is currently bound under `sys.modules['lib'*]` (the repo-root
    pipeline package, if anything imported it first this process), unbind it, and
    put `Streamlit/` at the front of `sys.path` so the NEXT `from lib import ...`
    (or `from lib.xxx import ...`) resolves to `Streamlit/lib` instead.

    Returns the saved-modules dict -- pass it to `restore_lib()` when the caller's
    own run is done. Idempotent-safe to call again before a matching restore (each
    caller owns its own `saved` dict, so nested/sequential swaps across different
    test files in one pytest session do not clobber each other).
    """
    saved = {k: v for k, v in sys.modules.items() if k == "lib" or k.startswith("lib.")}
    for k in list(saved):
        del sys.modules[k]
    if str(STREAMLIT_DIR) not in sys.path:
        sys.path.insert(0, str(STREAMLIT_DIR))
    return saved


def restore_lib(saved: dict) -> None:
    """Undo `swap_lib_to_streamlit()`: drop every `Streamlit/lib`-bound module
    from `sys.modules`, remove the inserted `sys.path` entry, and put back
    whatever `saved` held (possibly nothing, if no `lib` was bound before)."""
    if str(STREAMLIT_DIR) in sys.path:
        sys.path.remove(str(STREAMLIT_DIR))
    for k in [k for k in sys.modules if k == "lib" or k.startswith("lib.")]:
        del sys.modules[k]
    sys.modules.update(saved)
