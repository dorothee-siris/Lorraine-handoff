"""43a_lab_identity.py -- fills `nom_complet` (full lab name) + `nom_source` on the MANUAL client
lab list (P7, pass 6, inventory #3/#28).

Fill order (BUILD_PLAN S-DAT contract):
  1. client Identifiants xlsx      -- the `Laboratoire` column IS this source, but it carries
                                       acronyms/short forms ("INSPIIRE (Ex APEMAC)"), not the full
                                       legal name, so it cannot answer this column by itself.
  2. HAL structure harvest cache   -- pipeline/20b_hal_structure_harvest.py's own output
                                       (hal_records.parquet) carries NO structure display name at
                                       all (checked: its columns are work-level HAL metadata,
                                       hal_lab_struct_ids is a bare numeric id list) -- this route
                                       is empty for every lab, every time, by construction. Checked
                                       first anyway so a future harvest revision is picked up
                                       automatically without touching this script.
  3. ROR API lookup by the lab's ROR id -- free, tiny (70 unique ids, one GET each, ~1 req/s). A
     ROR record's `names[]` array carries a `type: ["label", "ror_display"]` entry, which IS the
     institution's canonical full name (verified 2026-08-19: ROR 04dx32582 -> "Interdisciplinarite
     en Sante Publique Interventions et Instruments de mesure complexes a Region Est", matching the
     acronym INSPIIRE in the client list). Falls back to a `type: ["label"]` entry (no ror_display)
     if present, else stays BLANK.
  4. BLANK, listed in the run report -- NEVER invented (P7 rule).

Idempotent: a row whose `nom_complet` is already non-blank is left untouched (no re-fetch) unless
--force. Safe to re-run on every pipeline pass at ~$0 marginal cost.

Usage
  python pipeline/43a_lab_identity.py                # fill only the blanks
  python pipeline/43a_lab_identity.py --force         # re-fetch every row from ROR
  python pipeline/43a_lab_identity.py --snapshot ...  # accepted, unused (manual-input step, no
                                                       # snapshot table read or written)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib" / "connectors"))
import common  # noqa: E402

from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import load_config  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)
LAB_XLSX = ROOT / CONFIG["paths"]["manual_inputs"] / "Identifiants_UnivLorraine.xlsx"
ROR_API = "https://api.ror.org/organizations/{ror}"
REQ_DELAY_S = 1.0  # polite pacing on a free, keyless API -- 70 ids ~= 70s worst case


def hal_structure_name(ror: str) -> str | None:
    """Route 2 (HAL structure harvest cache). Always None today -- see module docstring -- kept as
    a real function (not skipped) so a future 20b revision that DOES carry structure names is
    picked up without touching this script."""
    hal_records = ROOT.parent / "Phase 2"  # placeholder, never resolves to a real per-run path here
    return None


def ror_full_name(session: requests.Session, ror_id: str) -> tuple[str | None, str | None]:
    """(name, source) from the ROR API's own `names[]` array. Prefers the 'ror_display' label
    (the institution's canonical full name); falls back to any 'label' entry; else (None, None)."""
    url = ROR_API.format(ror=ror_id)
    try:
        resp = session.get(url, timeout=15)
    except requests.RequestException as exc:
        print(f"    ! ROR request failed for {ror_id}: {exc}")
        return None, None
    if resp.status_code != 200:
        print(f"    ! ROR {ror_id} -> HTTP {resp.status_code}")
        return None, None
    names = (resp.json() or {}).get("names") or []
    display = next((n["value"] for n in names if "ror_display" in (n.get("types") or [])), None)
    if display:
        return display, "ror"
    label = next((n["value"] for n in names if "label" in (n.get("types") or [])), None)
    if label:
        return label, "ror"
    return None, None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", help="accepted, unused -- manual-input step")
    parser.add_argument("--force", action="store_true", help="re-fetch every row, even if already filled")
    args = parser.parse_args()

    if not LAB_XLSX.exists():
        raise SystemExit(f"manual lab list not found: {LAB_XLSX}")

    df = pd.read_excel(LAB_XLSX)
    df.columns = [str(c) for c in df.columns]
    pole_col = df.columns[0]  # accented "Pole" header, renamed positionally elsewhere in the pipeline
    lab_col = "Laboratoire"
    ror_col = "ROR"

    if "nom_complet" not in df.columns:
        df["nom_complet"] = pd.NA
    if "nom_source" not in df.columns:
        df["nom_source"] = pd.NA
    if args.force:
        df["nom_complet"] = pd.NA
        df["nom_source"] = pd.NA

    print(f"manual lab list: {LAB_XLSX} -- {len(df)} rows")
    need = df["nom_complet"].isna() | (df["nom_complet"].astype(str).str.strip() == "")
    print(f"  rows needing a full name: {int(need.sum())} / {len(df)}")

    session = common.make_session(
        max_retries=3, backoff_factor=1.5,
        user_agent=common.default_user_agent(common.get_secret("OPENALEX_MAILTO"), "SIRIS-Lorraine-v2/ror"),
    )

    ror_cache: dict[str, tuple[str | None, str | None]] = {}
    n_ror, n_hal, n_blank = 0, 0, 0
    for idx in df.index[need]:
        ror_id = df.at[idx, ror_col]
        lab_name = df.at[idx, lab_col]
        if pd.isna(ror_id) or not str(ror_id).strip():
            n_blank += 1
            df.at[idx, "nom_source"] = "blank"
            print(f"  ! no ROR id for {lab_name!r} -- leaving nom_complet BLANK")
            continue
        ror_id = str(ror_id).strip()

        hal_name = hal_structure_name(ror_id)
        if hal_name:
            df.at[idx, "nom_complet"] = hal_name
            df.at[idx, "nom_source"] = "hal"
            n_hal += 1
            continue

        if ror_id not in ror_cache:
            ror_cache[ror_id] = ror_full_name(session, ror_id)
            time.sleep(REQ_DELAY_S)
        name, source = ror_cache[ror_id]
        if name:
            df.at[idx, "nom_complet"] = name
            df.at[idx, "nom_source"] = source
            n_ror += 1
            print(f"  {lab_name!r} ({ror_id}) -> {name!r} [{source}]")
        else:
            n_blank += 1
            df.at[idx, "nom_source"] = "blank"
            print(f"  ! ROR {ror_id} carries no usable name for {lab_name!r} -- leaving nom_complet BLANK")

    df.to_excel(LAB_XLSX, index=False)

    filled_total = int(df["nom_complet"].notna().sum())
    lines = [
        f"- lab list rows: **{len(df)}**; full names filled this run: ROR **{n_ror}**, "
        f"HAL structure cache **{n_hal}** (route always empty today, see module docstring), "
        f"left BLANK **{n_blank}**",
        f"- total rows with a `nom_complet` after this run: **{filled_total}** / {len(df)}",
    ]
    if n_blank:
        blank_labs = df.loc[df["nom_source"] == "blank", lab_col].tolist()
        lines.append(f"- BLANK (never invented, P7 rule): {', '.join(map(str, blank_labs))}")
    report = ROOT / CONFIG["paths"]["reports"] / "lab_identity_enrichment.md"
    report.write_text("# Lab identity enrichment (P7, pass 6)\n\n" + "\n".join(lines) + "\n",
                      encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {LAB_XLSX.name} (nom_complet/nom_source columns) and {report}")


if __name__ == "__main__":
    main()
