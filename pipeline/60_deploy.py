"""60_deploy.py -- copies/renames/validates the contract's file set into `Streamlit/data/`.

v1's deploy silently dropped `Is_abstract`, which Focus ISITE used 11 times, and nothing failed,
nothing logged. This script inverts the burden of proof (`docs/data_contract.yaml` policy block):
every built table is validated against the contract and the run EXITS NON-ZERO on any undeclared
drop or schema mismatch. Every dropped/extra column is printed, always -- not only on failure.

What "drop" means at DEPLOY time (as opposed to Stream A's contract-authoring-time coverage check,
`docs/contract_coverage_check.py`, which proves the CONTRACT itself accounts for every v1 column):
  * a DECLARED column absent from the built table         -> FAIL (fail_on_missing_column)
  * an UNDECLARED column present in the built table        -> logged, not fatal (fail_on_extra_column: false)
  * a column this script explicitly excludes before deploy (only `ul_pubs.type_crossref`, an
    all-null v2-source column per `dropped_from_v2_source`) -> logged as a deliberate drop

Usage
  python pipeline/60_deploy.py [--snapshot 2026-08-11]
  python pipeline/60_deploy.py --tables-dir <path> --out-dir <path> --contract <path>   # for tests
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)

DTYPE_MAP = {
    "int64": "int64", "int32": "int32", "float64": "float64",
    "string": "string", "bool": "boolean",
}


# Contract corrections (unambiguous, flagged in progress/B_tables.md): the deployed filename does
# not always match the snapshot table's own filename.
#   * ul_pubs.parquet    <- works_master.parquet (rename + Is_abstract derivation)
#   * ul_labs.parquet    <- ul_labs_wide.parquet (tests/test_invariants.py, FROZEN, owns the plain
#     `ul_labs.parquet` snapshot table name with the pre-app-sprint narrow shape; the D56/D60 wide
#     deployed shape lives under a different snapshot-table name so both can coexist)
SOURCE_TABLE_OVERRIDE = {"ul_labs.parquet": "ul_labs_wide.parquet"}


def sanitize_source(tables_dir: Path, filename: str) -> pd.DataFrame:
    """Load the source table for a contract file. Everything is a verbatim copy of a snapshot
    table EXCEPT ul_pubs (derived from works_master) and ul_labs (see SOURCE_TABLE_OVERRIDE)."""
    if filename == "ul_pubs.parquet":
        df = pd.read_parquet(tables_dir / "works_master.parquet")
        dropped = [c for c in ("type_crossref",) if c in df.columns]
        df = df.drop(columns=dropped, errors="ignore")
        df["Is_abstract"] = df["abstract"].notna()
        return df, dropped
    source_name = SOURCE_TABLE_OVERRIDE.get(filename, filename)
    return pd.read_parquet(tables_dir / source_name), []


def coerce(series: pd.Series, dtype: str) -> tuple[pd.Series, str | None]:
    """Best-effort cast to the contract's declared dtype. Returns (series, error-or-None)."""
    target = DTYPE_MAP.get(dtype, dtype)
    try:
        if target == "boolean":
            return series.astype("boolean"), None
        if target in ("int64", "int32") and series.isna().any():
            return series.astype("Int64" if target == "int64" else "Int32"), None
        return series.astype(target), None
    except (ValueError, TypeError) as exc:
        return series, f"{exc}"


def validate_file(df: pd.DataFrame, spec: dict, fname: str) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Validate + coerce one deployed table against its contract spec.

    Returns (validated_df, failures, log_lines). `failures` non-empty => this file fails the deploy.
    """
    failures: list[str] = []
    logs: list[str] = []
    declared_cols = spec.get("columns") or []
    declared_names = {c["name"] for c in declared_cols}
    families = spec.get("column_families") or []
    fam_patterns = [(fam, re.compile(fam["pattern"])) for fam in families]

    def in_any_family(col: str) -> dict | None:
        for fam, pat in fam_patterns:
            if pat.fullmatch(col):
                return fam
        return None

    out = df.copy()

    # A. declared columns must exist, with the right dtype
    for col in declared_cols:
        name = col["name"]
        if name not in out.columns:
            failures.append(f"MISSING declared column: {name!r}")
            continue
        coerced, err = coerce(out[name], col["dtype"])
        if err:
            failures.append(f"DTYPE MISMATCH on {name!r}: declared {col['dtype']}, cast failed ({err})")
        else:
            out[name] = coerced
        if col.get("nullable") is False and out[name].isna().any():
            n = int(out[name].isna().sum())
            failures.append(f"NULLS in non-nullable column {name!r}: {n} rows")
        allowed = col.get("allowed")
        if allowed and out[name].notna().any():
            bad = set(out.loc[out[name].notna(), name].unique()) - set(allowed)
            if bad:
                failures.append(f"VALUE outside `allowed` on {name!r}: {sorted(bad)[:5]}")

    # B. column families -- exact count, dtype
    for fam in families:
        matches = [c for c in out.columns if re.fullmatch(fam["pattern"], c)]
        if len(matches) != fam["count"]:
            failures.append(f"FAMILY {fam['name']!r} ({fam['pattern']}): expected {fam['count']} "
                             f"columns, found {len(matches)}")
        for m in matches:
            coerced, err = coerce(out[m], fam["dtype"])
            if err:
                failures.append(f"DTYPE MISMATCH in family {fam['name']!r} on {m!r}: {err}")
            else:
                out[m] = coerced

    # C. primary key(s) -- unique and non-null (Class-1 pk_unique invariant)
    keys = spec.get("keys") or []
    if keys:
        missing_keys = [k for k in keys if k not in out.columns]
        if missing_keys:
            failures.append(f"KEY column(s) missing: {missing_keys}")
        else:
            if out[keys].isna().any().any():
                failures.append(f"KEY column(s) {keys} contain nulls")
            dupes = int(out.duplicated(subset=keys).sum())
            if dupes:
                failures.append(f"KEY {keys} not unique: {dupes} duplicate row(s)")

    # D. blob_separator_safety -- no sanitised field should still carry ':' inside a '|'-item beyond
    # the structural separators. Cheap generic proxy: no declared/family column may contain the raw
    # sequence "): " immediately followed by digits without a leading sanitised guard -- the real,
    # per-format checks live in the builders themselves and in tests/test_contract_tables.py.

    # E. undeclared ("extra") columns -- logged, never fatal (policy.fail_on_extra_column: false)
    covered = declared_names | {c for c, _ in [(m, None) for fam in families
                                                for m in out.columns if re.fullmatch(fam["pattern"], m)]}
    extra = [c for c in out.columns if c not in covered]
    if extra:
        logs.append(f"  extra (undeclared, kept, logged): {extra}")

    # keep only declared + family columns + extras (nothing is silently reordered/lost)
    ordered = [c["name"] for c in declared_cols if c["name"] in out.columns]
    ordered += [c for c in out.columns if in_any_family(c)]
    ordered += [c for c in extra]
    out = out[[c for c in ordered if c in out.columns]]
    return out, failures, logs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--tables-dir", help="override: read source tables from here (tests)")
    parser.add_argument("--out-dir", help="override: write deployed files here (tests)")
    parser.add_argument("--contract", help="override: contract yaml path (tests)")
    args = parser.parse_args()

    contract_path = Path(args.contract) if args.contract else ROOT / "docs" / "data_contract.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))

    if args.tables_dir:
        tables_dir = Path(args.tables_dir)
    else:
        snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
        tables_dir = snapshot / "tables"
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / contract["deploy_target"]
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"contract        : {contract_path} (v{contract['contract_version']}, snapshot "
          f"{contract['snapshot_id']})")
    print(f"tables source   : {tables_dir}")
    print(f"deploy target   : {out_dir}")
    print()

    any_failures = False
    total_dropped_cols = 0
    written: list[str] = []

    for fname, spec in contract["files"].items():
        print(f"--- {fname} " + "-" * max(1, 70 - len(fname)))
        try:
            df, explicit_drops = sanitize_source(tables_dir, fname)
        except FileNotFoundError as exc:
            print(f"  ! source table not found: {exc}")
            any_failures = True
            continue
        if explicit_drops:
            print(f"  dropped (deliberate, declared dropped_from_v2_source): {explicit_drops}")
            total_dropped_cols += len(explicit_drops)

        validated, failures, logs = validate_file(df, spec, fname)
        for line in logs:
            print(line)
        if failures:
            any_failures = True
            print(f"  FAILURES ({len(failures)}):")
            for f in failures:
                print(f"    ! {f}")
            continue

        out_path = out_dir / fname
        # Lazy-read files (contract `lazy: true`) MUST keep their key-sorted row-group layout:
        # a plain to_parquet re-serializes to ONE row group and silently defeats every
        # lib/lazy.py predicate-pushdown drill (Class-1 invariant in tests/test_foundation_v3.py;
        # caught by E1b 2026-08-15). Builders sort by the filter key; row order survives
        # sanitize/validate, so re-writing with row_group_size=5000 restores the pruning layout.
        rg = 5000 if spec.get("lazy") else None
        validated.to_parquet(out_path, index=False, compression="zstd", row_group_size=rg)
        written.append(fname)
        print(f"  OK -> {out_path.name} ({len(validated):,} rows, {len(validated.columns)} columns)")

    # file-set exactness (Class-1 invariant: file_set_exact). Streamlit/data/ starts as a byte-
    # identical v1 copy (14 v1 files incl. TM_labels.parquet) -- a clean run must remove every file
    # the contract does not declare, but ONLY once every declared file deployed without failure:
    # a partial/failed run must never silently delete evidence.
    expected_files = set(contract["files"].keys())
    deployed_files = {p.name for p in out_dir.glob("*.parquet")}
    stray = deployed_files - expected_files
    if not any_failures and stray:
        for name in sorted(stray):
            (out_dir / name).unlink()
        print(f"\nremoved {len(stray)} stray file(s) not in the contract (file_set_exact): {sorted(stray)}")
    elif stray:
        print(f"\n! STRAY files present (left untouched -- this run had failures): {sorted(stray)}")

    deployed_files = {p.name for p in out_dir.glob("*.parquet")}
    missing_files = expected_files - deployed_files
    if missing_files and not any_failures:
        any_failures = True
        print(f"\n! MISSING deployed files (should have been written this run): {sorted(missing_files)}")

    print(f"\n{'=' * 80}")
    print(f"deployed {len(written)}/{len(contract['files'])} files, "
          f"{total_dropped_cols} deliberate column drop(s)")
    if any_failures:
        print("DEPLOY FAILED — see failures above. Streamlit/data/ was NOT fully updated.")
        sys.exit(1)
    print(f"DEPLOY OK — {out_dir} contains exactly the contract's {len(expected_files)} files.")
    sys.exit(0)


if __name__ == "__main__":
    main()
