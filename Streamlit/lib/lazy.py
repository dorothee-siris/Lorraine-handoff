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
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd
import pyarrow.parquet as pq
import streamlit as st


@st.cache_data(max_entries=32)
def read_keyed(path, key_col: str, key_value, columns: Sequence[str] | None = None) -> pd.DataFrame:
    """
    Predicate-pushdown read of one lazy file at one key value (or a list of
    key values, for the country-pubs path: partner_id IN <country's
    >=10-floor partners>). Cached per (path, key_col, key_value, columns) so a
    repeated drill in the same session never re-touches the file
    (`st.cache_data(max_entries=32)` per the rev 3.1 lazy_file_rules).
    """
    is_list = isinstance(key_value, (list, tuple, set, frozenset))
    op = "in" if is_list else "=="
    value = list(key_value) if is_list else key_value
    return pd.read_parquet(
        path, columns=list(columns) if columns is not None else None,
        filters=[(key_col, op, value)],
    )


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
