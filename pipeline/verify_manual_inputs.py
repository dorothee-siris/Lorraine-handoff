"""verify_manual_inputs.py -- integrity gate for inputs/manual/ (P7 D-manual-inputs).

inputs/manual/ holds files nobody re-derives (curated ids, the frontierness bad-topics baseline,
the frontier-components score file, ...) -- a silently-edited or silently-replaced copy is the kind
of drift a live-API pull would surface on its own (different byte count, different response) but a
manual xlsx never will. `MANIFEST.sha256` is the tripwire: one line per file in inputs/manual/,
`<sha256>  <filename>`, sorted by filename.

Usage:
    python pipeline/verify_manual_inputs.py            # verify: exit 0 if everything matches the
                                                         # manifest, exit 1 naming every mismatch
                                                         # (changed file, missing file, or new file
                                                         # not yet in the manifest)
    python pipeline/verify_manual_inputs.py --update    # recompute + REWRITE the manifest to match
                                                         # whatever is on disk right now.

    --update is a deliberate, logged act, not a routine step: it makes THIS run's disk state the new
    ground truth, silently absorbing any drift that happened since the manifest was last written. Run
    it only right after you have manually confirmed a new/changed file in inputs/manual/ is the one
    you meant to add -- never as a reflex to make a red `verify` run green again. Each --update run
    prints what changed (added / removed / hash-changed) before writing, so the act is visible in the
    caller's own log, not just in a silent file diff.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import load_config, utc_now  # noqa: E402

ascii_safe_stdout()
MANIFEST_NAME = "MANIFEST.sha256"


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def manual_dir(config: dict) -> Path:
    return ROOT / config["paths"]["manual_inputs"]


def current_hashes(directory: Path) -> dict[str, str]:
    """sha256 of every FILE directly inside `directory` except the manifest itself, sorted by name."""
    files = sorted(p for p in directory.iterdir() if p.is_file() and p.name != MANIFEST_NAME)
    return {p.name: sha256_of(p) for p in files}


def read_manifest(manifest_path: Path) -> dict[str, str]:
    if not manifest_path.exists():
        return {}
    out: dict[str, str] = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        digest, _, name = line.partition("  ")
        out[name.strip()] = digest.strip()
    return out


def write_manifest(manifest_path: Path, hashes: dict[str, str]) -> None:
    lines = [f"{digest}  {name}" for name, digest in sorted(hashes.items())]
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify(config: dict) -> int:
    directory = manual_dir(config)
    manifest_path = directory / MANIFEST_NAME
    expected = read_manifest(manifest_path)
    if not expected:
        print(f"FAIL: no manifest at {manifest_path} (run with --update once, deliberately)")
        return 1

    actual = current_hashes(directory)
    missing = sorted(set(expected) - set(actual))       # in manifest, gone from disk
    untracked = sorted(set(actual) - set(expected))      # on disk, never manifested
    changed = sorted(n for n in (set(expected) & set(actual)) if expected[n] != actual[n])

    if not missing and not untracked and not changed:
        print(f"OK: {len(actual)} file(s) in {directory} match {MANIFEST_NAME}")
        return 0

    print(f"FAIL: {directory} does not match {MANIFEST_NAME}")
    for name in changed:
        print(f"  CHANGED   {name}: manifest={expected[name][:12]}... disk={actual[name][:12]}...")
    for name in missing:
        print(f"  MISSING   {name}: in manifest, not found on disk")
    for name in untracked:
        print(f"  UNTRACKED {name}: on disk, not in manifest (add with --update after you confirm it)")
    return 1


def update(config: dict) -> int:
    directory = manual_dir(config)
    manifest_path = directory / MANIFEST_NAME
    before = read_manifest(manifest_path)
    after = current_hashes(directory)

    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(n for n in (set(before) & set(after)) if before[n] != after[n])

    print(f"--update ({utc_now()}): rewriting {manifest_path}")
    if not (added or removed or changed):
        print("  no change vs the existing manifest (rewritten byte-identical).")
    for name in added:
        print(f"  + added     {name}: {after[name]}")
    for name in removed:
        print(f"  - removed   {name}: was {before[name]}")
    for name in changed:
        print(f"  ~ hash-changed {name}: {before[name][:12]}... -> {after[name][:12]}...")

    write_manifest(manifest_path, after)
    print(f"wrote {len(after)} entries.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true",
                        help="deliberately rewrite MANIFEST.sha256 from what's on disk now")
    args = parser.parse_args()

    config = load_config(ROOT)
    if args.update:
        return update(config)
    return verify(config)


if __name__ == "__main__":
    raise SystemExit(main())
