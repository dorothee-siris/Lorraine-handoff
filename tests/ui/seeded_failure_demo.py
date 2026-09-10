"""
Stream E — "prove the suite can fail" demo (D48 acceptance criterion).

Corrupts ONE value in a TEMP COPY of `tests/golden/app_numbers_golden.csv`
(the committed file itself is never touched), points a real subprocess pytest
run at that copy via the `APP_NUMBERS_GOLDEN_CSV` env var, shows it fail, then
runs the same command against the real committed CSV and shows it pass.

Usage:
    python tests/ui/seeded_failure_demo.py

Exit 0 iff the corrupted run FAILED and the restored run PASSED (i.e. the
suite really can fail, and green is really green). ASCII-only console output.
"""
from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REAL_GOLDEN = ROOT / "tests" / "golden" / "app_numbers_golden.csv"
TEST_ID = "tests/test_app_numbers.py::test_lab_pubs_total_matches_page"

SEED_ENTITY = "IJL"
SEED_METRIC = "lab_pubs_total"
SEED_BOGUS_VALUE = "999999"


def run_pytest(golden_csv: Path) -> subprocess.CompletedProcess:
    import os
    env = dict(os.environ)
    env["APP_NUMBERS_GOLDEN_CSV"] = str(golden_csv)
    return subprocess.run(
        [sys.executable, "-m", "pytest", TEST_ID, "-v"],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
    )


def main() -> int:
    if not REAL_GOLDEN.exists():
        print(f"ERROR: {REAL_GOLDEN} does not exist -- run tests/ui/build_golden.py first")
        return 1

    with REAL_GOLDEN.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
        fieldnames = list(rows[0].keys())

    target = [r for r in rows if r["entity"] == SEED_ENTITY and r["metric"] == SEED_METRIC]
    assert target, f"no golden row for entity={SEED_ENTITY!r} metric={SEED_METRIC!r}"
    original_value = target[0]["displayed_value"]
    print(f"Seeding a corruption: {SEED_ENTITY}/{SEED_METRIC} "
          f"{original_value!r} -> {SEED_BOGUS_VALUE!r} (TEMP COPY ONLY)")

    corrupted = [dict(r) for r in rows]
    for r in corrupted:
        if r["entity"] == SEED_ENTITY and r["metric"] == SEED_METRIC:
            r["displayed_value"] = SEED_BOGUS_VALUE

    with tempfile.TemporaryDirectory() as tmp:
        temp_csv = Path(tmp) / "app_numbers_golden_corrupted.csv"
        with temp_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(corrupted)

        print()
        print("=" * 78)
        print(f"RUN 1 -- against the CORRUPTED temp copy ({temp_csv})")
        print("=" * 78)
        bad = run_pytest(temp_csv)
        print(bad.stdout[-4000:])
        if bad.returncode == 0:
            print("DEMO FAILED: the corrupted run was expected to FAIL but exited 0")
            return 1
        print(f"--> exit code {bad.returncode} (FAILED, as expected)")

    print()
    print("=" * 78)
    print(f"RUN 2 -- against the REAL, untouched committed CSV ({REAL_GOLDEN})")
    print("=" * 78)
    good = run_pytest(REAL_GOLDEN)
    print(good.stdout[-4000:])
    if good.returncode != 0:
        print("DEMO FAILED: the restored run was expected to PASS but did not")
        return 1
    print(f"--> exit code {good.returncode} (PASSED)")

    print()
    print("SEEDED-FAILURE DEMO OK: corrupted run failed, restored run passed. "
          f"The committed file at {REAL_GOLDEN} was never modified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
