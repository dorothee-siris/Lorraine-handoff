# tests/test_countries.py
"""
Pass-6 Tier-A eval for Streamlit/lib/countries_fr.py (plan P3, item #13) -- the
curated ISO2 -> French country name mapping every page that renders a country code
must go through (pages 8/9/10/13 + anywhere else an ISO2 renders).

Golden set: every ISO2 code ACTUALLY carried by a deployed table, per
`grep -n -i country docs/data_contract.yaml` (see `lib/countries_fr.py`'s own module
docstring for the same list) -- geo_countries, ptn_summary, ptn_denominators,
geo_fields, ul_partners/ul_partners_base, the four bench_* peer tables,
lab_top_partners, and ul_labs' pipe-separated "Top 10 int partners (country)" blob.
A table not yet deployed this pass (S-DAT running in parallel) is skipped, not
failed -- `deployed()` below mirrors tests/test_contract_tables.py's own convention.

    python -m pytest tests/test_countries.py -q

Namespace note: same `_import_streamlit_lib` swap-trick as tests/test_ranked.py /
tests/test_overlay.py.
"""
from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
DEPLOY_DIR = STREAMLIT_DIR / "data"
CSV_PATH = ROOT / "inputs" / "countries_fr.csv"


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


(countries_fr,) = _import_streamlit_lib("countries_fr")


# ============================================================================
# Golden set -- every ISO2 code the deployed data actually carries
# ============================================================================

# (table, column) pairs carrying a plain ISO2 value, per docs/data_contract.yaml.
_PLAIN_SOURCES = [
    ("geo_countries", "country_code"),
    ("ul_partners_base", "Country"),
    ("ptn_summary", "country_code"),
    ("geo_fields", "country_code"),
    ("ptn_denominators", "country_code"),
    ("bench_diversity", "country"),
    ("bench_peers", "country"),
    ("bench_positioning", "country"),
    ("bench_sdg", "country"),
    ("lab_top_partners", "country"),
    ("ul_partners", "country"),
]
# ul_labs carries a pipe-separated blob, not a plain column.
_BLOB_SOURCE = ("ul_labs", "Top 10 int partners (country)")

# Codes that are EXPLICIT non-country placeholders in this app's data, never real
# ISO2 values -- excluded from the golden set by construction (page 10 already
# excludes UNKNOWN "by construction", per its own module docstring).
_PLACEHOLDER_CODES = {"UNKNOWN", ""}

# Enumerated exceptions to "every code resolves to a real FR name" (P3 eval
# contract: "except genuinely unmappable ones you enumerate"). Empty: the CLDR
# French locale (babel) resolved all 178 codes found in the deployed data --
# see progress/SLIB.md for the generation note.
KNOWN_UNMAPPABLE: frozenset[str] = frozenset()


def _deployed(name: str) -> pd.DataFrame | None:
    path = DEPLOY_DIR / f"{name}.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


def _collect_data_iso2_codes() -> set[str]:
    codes: set[str] = set()
    found_any = False
    for table, col in _PLAIN_SOURCES:
        df = _deployed(table)
        if df is None or col not in df.columns:
            continue
        found_any = True
        codes |= {str(v).strip() for v in df[col].dropna().unique()}

    df = _deployed(_BLOB_SOURCE[0])
    if df is not None and _BLOB_SOURCE[1] in df.columns:
        found_any = True
        for blob in df[_BLOB_SOURCE[1]].dropna():
            codes |= {tok.strip() for tok in str(blob).split("|")}

    if not found_any:
        pytest.skip("no country-bearing table deployed yet under Streamlit/data/")
    return codes - _PLACEHOLDER_CODES


# ============================================================================
# TIER A -- every ISO2 in the deployed data resolves, non-null, != the code
# ============================================================================

def test_every_deployed_iso2_resolves_to_a_real_fr_name():
    codes = _collect_data_iso2_codes()
    assert len(codes) > 0, "golden set must not be empty -- check _PLAIN_SOURCES against the data"

    unresolved = []
    for code in sorted(codes):
        if code in KNOWN_UNMAPPABLE:
            continue
        label = countries_fr.country_label(code)
        if not label or label == code:
            unresolved.append(code)
    assert not unresolved, (
        f"{len(unresolved)} ISO2 code(s) present in the deployed data have no FR name in "
        f"inputs/countries_fr.csv (or resolved to themselves): {unresolved}"
    )


def test_golden_iso2_set_matches_this_pass_inventory():
    """
    Pinned count, so a silent drop in the source union (e.g. a column rename that
    makes `_PLAIN_SOURCES` stop matching) fails loudly instead of shrinking the
    eval quietly. 178 codes measured 2026-08-19 across all listed tables.
    """
    codes = _collect_data_iso2_codes()
    assert len(codes) == 178, (
        f"expected 178 distinct ISO2 codes across the country-bearing tables, got "
        f"{len(codes)} -- either the data changed (re-run the CSV generation and update "
        f"this pin) or a source table/column listed in _PLAIN_SOURCES stopped matching."
    )


def test_countries_fr_csv_covers_every_code_in_itself_uniquely():
    df = pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False, na_values=[])
    assert df["iso2"].is_unique
    assert (df["name_fr"].str.strip() != "").all()
    assert len(df) == len(countries_fr.COUNTRY_NAMES_FR)


# ============================================================================
# Namibia pin -- "NA" IS Namibia, never a null
# ============================================================================

def test_na_resolves_to_namibie():
    assert countries_fr.country_label("NA") == "Namibie"


def test_keep_default_na_regression_guard_matters():
    """
    Prove the guard is load-bearing: reading the SAME csv the naive way (pandas'
    default NA-string sniffing) must lose the "NA" row (either the whole row
    vanishes under dropna(), or its iso2 cell reads as NaN) -- otherwise this pin
    would be a no-op and the guard could be deleted without any test noticing.
    """
    naive = pd.read_csv(CSV_PATH)  # no keep_default_na=False -- the regression case
    naive_na_rows = naive[naive["iso2"] == "NA"]
    assert naive_na_rows.empty or naive_na_rows["iso2"].isna().any() or naive["iso2"].isna().any(), (
        "the naive read did not lose 'NA' -- either pandas' NA-sniffing default changed "
        "(re-verify the guard is still needed) or the CSV's column order/dtype makes the "
        "guard moot; investigate before trusting keep_default_na=False silently"
    )

    guarded = pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False, na_values=[])
    guarded_row = guarded[guarded["iso2"] == "NA"]
    assert len(guarded_row) == 1
    assert guarded_row["name_fr"].iloc[0] == "Namibie"


# ============================================================================
# country_label() -- robustness contract (never blank on a real code, never crash)
# ============================================================================

def test_country_label_known_codes():
    assert countries_fr.country_label("FR") == "France"
    assert countries_fr.country_label("DE") == "Allemagne"
    assert countries_fr.country_label("US") == "États-Unis"


def test_country_label_strips_whitespace():
    assert countries_fr.country_label(" FR ") == "France"


def test_country_label_none_and_nan_return_blank_not_a_crash():
    assert countries_fr.country_label(None) == ""
    assert countries_fr.country_label(float("nan")) == ""
    assert countries_fr.country_label(pd.NA) == ""


def test_country_label_empty_string_returns_blank():
    assert countries_fr.country_label("") == ""
    assert countries_fr.country_label("   ") == ""


def test_country_label_unknown_code_returns_the_code_itself_never_blank(caplog):
    with caplog.at_level(logging.WARNING, logger="lib.countries_fr"):
        result = countries_fr.country_label("ZZ")
    assert result == "ZZ"
    assert result != ""


def test_country_label_unknown_code_logs_once_per_code(caplog):
    countries_fr._warned_codes.discard("QQ")  # isolate from other tests' state
    with caplog.at_level(logging.WARNING, logger="lib.countries_fr"):
        countries_fr.country_label("QQ")
        countries_fr.country_label("QQ")
        countries_fr.country_label("QQ")
    warnings = [r for r in caplog.records if "QQ" in r.getMessage()]
    assert len(warnings) == 1, f"expected exactly one warning for a repeated unknown code, got {len(warnings)}"
