# lib/lazy.py
"""
W5 shared lazy-drill layer -- authority: docs/foundry/data_foundation.yaml rev 3.1
`drill_layer` block + `meta.lazy_file_rules`.

Every lazy work/cell-grain file (ptn_works, ptn_topics, aut_works, geo_fields,
subset_works, ...) is written sorted by its filter key with row_group_size=5000, so a
pyarrow `filters=` read prunes to a handful of row groups instead of scanning the whole
file (F0-measured: ptn_topics 1/45 groups touched = 2.2%, ptn_works 1/24 = 4.1%).

Class-1 invariant (`assert_row_groups`): num_row_groups >= n_rows/10000. A file that
fails this was written without `row_group_size=5000` and defeats the whole point of this
module -- pyarrow can only skip row groups, never rows within one.

Pass 7a (P12, reports/CACHE_DIAGNOSIS.md strategy 2): `read_keyed` used to be ONE
`@st.cache_data(max_entries=32)` function shared by all 6 lazy files. The diagnosis
measured the single biggest *theoretical* growth vector in the whole app there: the
largest observed slice (ptn_works @ 7.08 MB for partner I1294671590) x 32 possible
resident entries = up to ~227 MB in one session. `ptn_works.parquet`/`ptn_topics.parquet`
(pages 8/9, the "Zoom partenaire" drill) are the two files big enough for that to matter;
the other 4 lazy files (aut_works, geo_fields, subset_works, lab_works) stay at the
original `max_entries=32` -- their worst measured single entry is low single-digit MB, so
32 of them is still a low ceiling.

`read_keyed(path, key_col, key_value, columns=None)` keeps its ORIGINAL signature and
dispatches on `Path(path).name`: the 6 existing call sites (pages 2, 3, 7, 9x2, 10, 12 +
`lib.helpers.lazy_slice_csv_bytes`) are unchanged. `HEAVY_CAP` is read from the
`LORRAINE_READ_KEYED_CAP` env var ONCE, at import time (it parametrises the
`@st.cache_data(max_entries=...)` decorator, which is fixed at function-definition time --
an env change after import has no effect on an already-running process). This is the
deliberate seam `tests/stress/run_stress.py`'s "broken control" run uses: setting
`LORRAINE_READ_KEYED_CAP=32` in the server process's own environment before it starts
restores the old, uncapped-for-these-2-files behaviour, so a stress run against that
config must show a measurably higher peak RSS than the default (cap 8) run -- proving the
cap is what protects the budget, not a coincidence of the specific session tested.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

import pandas as pd
import pyarrow.parquet as pq
import streamlit as st

# The 2 lazy files big enough for `read_keyed`'s own entry count to matter (P12; measured
# basis: reports/CACHE_DIAGNOSIS.md §3.3, strategy 2). Matched on Path(...).name so callers
# may pass either a str or a Path.
HEAVY_FILES = {"ptn_works.parquet", "ptn_topics.parquet"}

# Read ONCE at import (see module docstring) -- default 8 (P12); the stress harness's own
# "broken control" run sets LORRAINE_READ_KEYED_CAP=32 in the SERVER process's environment
# before that process starts, restoring the pre-P12 ceiling on purpose to prove the cap
# (not something else) is what bounds the budget.
HEAVY_CAP = int(os.environ.get("LORRAINE_READ_KEYED_CAP", "8"))


def _read_parquet_keyed(path, key_col: str, key_value, columns: Sequence[str] | None) -> pd.DataFrame:
    """Shared predicate-pushdown body for both cached readers below -- NOT itself
    cached (each of `_read_keyed_heavy`/`_read_keyed_light` owns its own cache
    namespace and entry budget; this just avoids repeating the 6-line read twice)."""
    is_list = isinstance(key_value, (list, tuple, set, frozenset))
    op = "in" if is_list else "=="
    value = list(key_value) if is_list else key_value
    return pd.read_parquet(
        path, columns=list(columns) if columns is not None else None,
        filters=[(key_col, op, value)],
    )


@st.cache_data(max_entries=HEAVY_CAP)
def _read_keyed_heavy(path, key_col: str, key_value, columns: Sequence[str] | None = None) -> pd.DataFrame:
    """Cache for the 2 `HEAVY_FILES` (ptn_works, ptn_topics) -- `max_entries=HEAVY_CAP`
    (default 8, P12). A dedicated namespace so drilling into many partners on pages 8/9
    can never inflate the OTHER 4 lazy files' own budget, and vice versa."""
    return _read_parquet_keyed(path, key_col, key_value, columns)


@st.cache_data(max_entries=32)
def _read_keyed_light(path, key_col: str, key_value, columns: Sequence[str] | None = None) -> pd.DataFrame:
    """Cache for every OTHER lazy file (aut_works, geo_fields, subset_works,
    lab_works) -- unchanged `max_entries=32` from the original single-reader design
    (their worst measured single entry is low single-digit MB; 32 of them is still a
    low, acceptable ceiling -- reports/CACHE_DIAGNOSIS.md §3.3)."""
    return _read_parquet_keyed(path, key_col, key_value, columns)


def read_keyed(path, key_col: str, key_value, columns: Sequence[str] | None = None) -> pd.DataFrame:
    """
    Predicate-pushdown read of one lazy file at one key value (or a list of
    key values, for the country-pubs path: partner_id IN <country's
    >=10-floor partners>). Dispatches on `Path(path).name` to one of two cached
    readers (`_read_keyed_heavy` for `HEAVY_FILES`, `_read_keyed_light` for every
    other lazy file) so the 2 biggest files get a smaller, dedicated entry budget
    (P12) without changing this function's signature or any of its 6 call sites.
    """
    reader = _read_keyed_heavy if Path(path).name in HEAVY_FILES else _read_keyed_light
    return reader(path, key_col, key_value, columns)


def assert_row_groups(path) -> None:
    """
    Class-1 invariant: num_row_groups >= n_rows/10000 (rev 3.1
    meta.lazy_file_rules). Raises AssertionError naming the shortfall; callers
    (tests, the R-A/W1 completeness check) treat any failure as a build break,
    not a warning.
    """
    pf = pq.ParquetFile(path)
    n_rows = pf.metadata.num_rows
    n_rg = pf.metadata.num_row_groups
    floor = n_rows / 10000
    assert n_rg >= floor, (
        f"{Path(path).name}: {n_rg} row group(s) for {n_rows:,} rows, but the "
        f"Class-1 invariant needs >= n_rows/10000 = {floor:.2f} -- "
        f"rewrite with row_group_size=5000 (or smaller)."
    )
