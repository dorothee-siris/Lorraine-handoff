# lib/countries_fr.py
"""
ISO2 -> French country name (pass 6, plan P3, item #13) -- authority: BUILD_PLAN.md
pass 6 P3 + `SIRIS\\brainstorms\\2026-08-19-lorraine-pass6-feedback.md` Q&A/#13.

`inputs/countries_fr.csv` is a CURATED, FROZEN mapping: generated ONCE (2026-08-19)
from Unicode CLDR's French locale data (`babel.Locale('fr').territories`) for the
exact 178 ISO2 codes this app's deployed tables actually carry (geo_countries,
ptn_summary, ptn_denominators, geo_fields, ul_partners/ul_partners_base, the four
bench_* peer tables, lab_top_partners, and ul_labs' "Top 10 int partners (country)"
pipe-blob -- every country-bearing column in `docs/data_contract.yaml`). No runtime
API dependency: the CSV is the single source of truth from here on, read once at
import time. See `progress/SLIB.md` for the generation note and the handful of
codes that carry more than one common French form.

Namibia trap (P3, and already flagged independently in `docs/data_contract.yaml`'s
own `null_country_arbitration` note for `geo_fields`): ISO2 `NA` is Namibia, a real
value in this app's data -- pandas' default NA-string sniffing silently turns the
literal string "NA" into a missing value. The CSV is read with
`keep_default_na=False, na_values=[]` so no string is EVER treated as a null on
either column; a genuinely blank cell in this frozen, hand-checked file would be a
build error, not a runtime possibility.

`country_label()` never returns a blank string and never raises: an ISO2 code
outside the 178 (a future snapshot's new partner country, or a caller passing
something odd) falls back to the code itself, logged once per code per process
(never a wall of repeated warnings for a wide table).
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

_CSV_PATH = Path(__file__).resolve().parent.parent.parent / "inputs" / "countries_fr.csv"
_logger = logging.getLogger(__name__)

# Codes already warned about this process -- "logged once" (P3 eval contract), not
# once per row of a table that repeats the same missing code hundreds of times.
_warned_codes: set[str] = set()


def _load_country_names() -> dict[str, str]:
    if not _CSV_PATH.is_file():
        return {}
    # keep_default_na=False + na_values=[]: "NA" IS Namibia, never a null (see
    # module docstring). dtype=str so a numeric-looking code (there are none, but
    # defence in depth) is never silently coerced.
    df = pd.read_csv(_CSV_PATH, dtype=str, keep_default_na=False, na_values=[])
    return dict(zip(df["iso2"].str.strip(), df["name_fr"].str.strip()))


COUNTRY_NAMES_FR: dict[str, str] = _load_country_names()


def country_label(iso2) -> str:
    """
    French display name for an ISO2 code. A missing/null input (no code at all)
    returns "". An unrecognised code returns the CODE ITSELF (never blank, never
    a crash) and logs a warning once per code -- callers must never see a
    KeyError or a silently blank cell (P3 eval contract).
    """
    if iso2 is None:
        return ""
    try:
        if pd.isna(iso2):
            return ""
    except (TypeError, ValueError):
        pass
    code = str(iso2).strip()
    if not code:
        return ""
    name = COUNTRY_NAMES_FR.get(code)
    if name:
        return name
    if code not in _warned_codes:
        _logger.warning(
            "countries_fr.country_label: no FR name for ISO2 code %r -- showing the code itself",
            code,
        )
        _warned_codes.add(code)
    return code
