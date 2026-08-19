"""Snapshot, manifest and summary handling (plan D7 / D18 / D22 / §9).

A snapshot without its manifest is not a snapshot. The manifest is what makes "deterministic
re-run" mean anything: same code + same archived snapshot => identical output. A fresh OpenAlex
pull never reproduces old counts, so the manifest records exactly what was asked for and when.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import platform
import sys
from pathlib import Path

import yaml


def load_config(project_root: Path) -> dict:
    return yaml.safe_load((project_root / "config.yaml").read_text(encoding="utf-8"))


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def resolve_snapshot(config: dict, override: str | None = None, create: bool = True) -> Path:
    """Return the active snapshot directory, creating raw/ and vocab/ subdirs on first use."""
    snapshot_id = override or config["project"].get("snapshot_id")
    if not snapshot_id:
        snapshot_id = dt.date.today().isoformat()
    root = Path(config["paths"]["snapshot_root"]) / str(snapshot_id)
    if create:
        (root / "raw").mkdir(parents=True, exist_ok=True)
        (root / "tables").mkdir(parents=True, exist_ok=True)
    return root


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def tool_versions() -> dict[str, str]:
    versions = {"python": sys.version.split()[0], "platform": platform.platform()}
    for module in ("requests", "pandas", "pyarrow", "yaml"):
        try:
            versions[module] = __import__(module).__version__
        except Exception:  # a version we cannot read is not worth failing a run over
            versions[module] = "unknown"
    return versions


class Manifest:
    """Accumulates per-step provenance into `<snapshot>/MANIFEST.json`.

    Re-running a step replaces its own entry and leaves every other step's entry untouched, so a
    partial re-run never silently invalidates the record of the steps around it.
    """

    def __init__(self, snapshot_dir: Path) -> None:
        self.path = snapshot_dir / "MANIFEST.json"
        self.snapshot_dir = snapshot_dir
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {
                "snapshot_id": snapshot_dir.name,
                "created_utc": utc_now(),
                "steps": {},
            }

    def record_step(
        self,
        step: str,
        *,
        filters: dict | list | str | None = None,
        select: str | list | None = None,
        api_base: str | None = None,
        api_calls: int | None = None,
        counts: dict | None = None,
        files: list[Path] | None = None,
        notes: str | None = None,
        params: dict | None = None,
    ) -> None:
        entry: dict = {
            "finished_utc": utc_now(),
            "tool_versions": tool_versions(),
        }
        if filters is not None:
            entry["filters"] = filters
        if select is not None:
            entry["select"] = select
        if api_base:
            entry["api_base_url"] = api_base
        if api_calls is not None:
            entry["api_calls"] = api_calls
        if counts:
            entry["counts"] = counts
        if params:
            entry["params"] = params
        if notes:
            entry["notes"] = notes
        if files:
            entry["files"] = [self._describe(path) for path in files if path.exists()]
        self.data["steps"][step] = entry
        self.write()

    def _describe(self, path: Path) -> dict:
        described = {
            "path": str(path.relative_to(self.snapshot_dir)) if self._inside(path) else str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        if path.suffix == ".parquet":
            try:
                import pyarrow.parquet as pq

                described["rows"] = pq.ParquetFile(path).metadata.num_rows
            except Exception:
                pass
        return described

    def _inside(self, path: Path) -> bool:
        try:
            path.relative_to(self.snapshot_dir)
            return True
        except ValueError:
            return False

    def write(self) -> None:
        self.data["updated_utc"] = utc_now()
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")


def append_summary(snapshot_dir: Path, step: str, lines: list[str]) -> None:
    """Human-readable running tally of counts at every stage (`SUMMARY.md`)."""
    path = snapshot_dir / "SUMMARY.md"
    header = f"# Snapshot {snapshot_dir.name} — counts at every stage\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else header
    block = f"\n## {step} — {utc_now()}\n\n" + "\n".join(lines) + "\n"
    path.write_text(existing + block, encoding="utf-8")


def prune_snapshots(config: dict, dry_run: bool = True) -> list[str]:
    """Delete `raw/` from snapshots older than the retention count. Manifests are kept forever.

    Returns the snapshot ids whose raw/ was (or would be) pruned. Never touches MANIFEST.json,
    SUMMARY.md or tables/ — retention prunes bulk, not the record (D22).
    """
    root = Path(config["paths"]["snapshot_root"])
    if not root.exists():
        return []
    keep = int(config["project"]["snapshot_retention"])
    ids = sorted((p.name for p in root.iterdir() if p.is_dir()), reverse=True)
    pruned: list[str] = []
    for snapshot_id in ids[keep:]:
        raw = root / snapshot_id / "raw"
        if raw.exists() and any(raw.iterdir()):
            pruned.append(snapshot_id)
            if not dry_run:
                for item in raw.rglob("*"):
                    if item.is_file():
                        item.unlink()
    return pruned
