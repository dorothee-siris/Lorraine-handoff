#!/usr/bin/env python3
"""
common.py — shared helpers for every SIRIS research-database connector.

Copy this file into a project ALONGSIDE the connector module(s) you need
(openalex.py, hal.py, ...). Nothing here imports from SIRIS\\Tools at runtime,
so the project stays standalone (per the SIRIS standalone-project principle).
The ONLY thing referenced outside the project is the central secret store
(~/.siris/.env), which by design must be shared.

What's inside:
  - get_secret()          read a credential from the central ~/.siris/.env
  - make_session()        requests.Session with a retry/backoff adapter + UA
  - TokenBucket           thread-safe rate limiter (for parallel pulls)
  - dumps()/read_jsonl()  fast JSON + gz-aware JSONL reader
  - checkpoint helpers     the .cursor.txt / "DONE" resume idiom
  - write_manifest()      provenance JSON next to the raw snapshot
  - reconstruct_abstract() rebuild abstract text from OpenAlex inverted index

These are extracted verbatim (lightly generalised) from the proven Ifremer and
La Réunion connectors, so behaviour matches what already works in production.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from threading import Lock

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Fast JSON if available, else stdlib (same fallback the harvesters use).
try:
    import orjson

    def dumps(obj) -> bytes:
        return orjson.dumps(obj)
except ImportError:  # pragma: no cover
    import json as _json

    def dumps(obj) -> bytes:
        return _json.dumps(obj, ensure_ascii=False).encode("utf-8")

import json  # always needed for reading

# ---------------------------------------------------------------------------
# Secret store — the single controlled runtime dependency on ~/.siris/.env
# ---------------------------------------------------------------------------
CENTRAL_SECRETS = Path.home() / ".siris" / ".env"
_SECRETS_LOADED = False


def _load_secrets() -> None:
    """Load credentials into os.environ, once.

    Order (first to load wins, because dotenv override=False never clobbers an
    already-set variable): existing environment > project-local ./.env or
    ../.env > central ~/.siris/.env. python-dotenv is optional; if it is not
    installed we fall back to a tiny hand-parser so a copied module still works.
    """
    global _SECRETS_LOADED
    if _SECRETS_LOADED:
        return
    candidates = [Path.cwd() / ".env", Path.cwd().parent / ".env", CENTRAL_SECRETS]
    try:
        from dotenv import load_dotenv
        for p in candidates:
            if p.exists():
                load_dotenv(p, override=False)
    except ImportError:  # pragma: no cover — dotenv not installed
        for p in candidates:
            if p.exists():
                _parse_env_file(p)
    _SECRETS_LOADED = True


def _parse_env_file(path: Path) -> None:
    """Minimal KEY=VALUE parser used only if python-dotenv is missing."""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def get_secret(name: str, default: str = "") -> str:
    """Return a credential by name (e.g. 'OPENALEX_API_KEY'), loading the store lazily."""
    _load_secrets()
    return os.environ.get(name, default) or default


# ---------------------------------------------------------------------------
# HTTP session — retry/backoff adapter + polite User-Agent
# ---------------------------------------------------------------------------
def default_user_agent(mailto: str = "", app: str = "SIRIS-connectors/1.0") -> str:
    return f"{app} (mailto:{mailto})" if mailto else app


def make_session(
    *,
    max_retries: int = 5,
    backoff_factor: float = 1.5,
    status_forcelist=(429, 500, 502, 503, 504),
    user_agent: str | None = None,
    headers: dict | None = None,
    pool: int = 16,
) -> requests.Session:
    """A requests.Session that retries transient errors with exponential backoff
    and honours Retry-After (the idiom shared by every SIRIS harvester)."""
    s = requests.Session()
    retry = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=list(status_forcelist),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=pool, pool_maxsize=pool)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers["User-Agent"] = user_agent or default_user_agent()
    if headers:
        s.headers.update(headers)
    return s


# ---------------------------------------------------------------------------
# TokenBucket — thread-safe rate limiter for parallel pulls
# ---------------------------------------------------------------------------
class TokenBucket:
    """Thread-safe token-bucket rate limiter (no sleep while holding the lock)."""

    def __init__(self, rate_per_sec: float, capacity: float | None = None):
        self.rate = float(rate_per_sec)
        self.capacity = float(capacity if capacity is not None else rate_per_sec)
        self.tokens = self.capacity
        self.last = time.monotonic()
        self.lock = Lock()

    def acquire(self, n: float = 1.0) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
                self.last = now
                if self.tokens >= n:
                    self.tokens -= n
                    return
                wait = (n - self.tokens) / self.rate
            time.sleep(wait)


# ---------------------------------------------------------------------------
# JSONL I/O (gz-aware) + line counting
# ---------------------------------------------------------------------------
def count_lines(path: Path) -> int:
    with open(path, "rb") as f:
        return sum(1 for _ in f)


def read_jsonl(path):
    """Yield parsed objects from a .jsonl or .jsonl.gz file (whichever exists)."""
    path = Path(path)
    gz = path.with_suffix(path.suffix + ".gz")
    if path.exists():
        opener = lambda: open(path, "r", encoding="utf-8")  # noqa: E731
    elif gz.exists():
        import gzip
        opener = lambda: gzip.open(gz, "rt", encoding="utf-8")  # noqa: E731
    else:
        raise FileNotFoundError(f"No JSONL at {path} or {gz}")
    with opener() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


# ---------------------------------------------------------------------------
# Checkpoint / resume — the .cursor.txt with "DONE" sentinel idiom
# ---------------------------------------------------------------------------
def load_checkpoint(path: Path) -> str | None:
    """Return the saved cursor/token, 'DONE', or None if no checkpoint exists."""
    path = Path(path)
    if path.exists():
        saved = path.read_text(encoding="utf-8").strip()
        return saved or None
    return None


def save_checkpoint(path: Path, token: str | None) -> None:
    """Persist the next cursor/token, or 'DONE' when the harvest is finished."""
    Path(path).write_text(token or "DONE", encoding="utf-8")


# ---------------------------------------------------------------------------
# Provenance manifest
# ---------------------------------------------------------------------------
def write_manifest(path: Path, meta: dict) -> None:
    """Write a provenance manifest next to the raw snapshot.

    A 'harvested_at' timestamp is added automatically if absent. Always record a
    snapshot date: for living DBs like OpenAlex, reproducibility = same code +
    this archived snapshot, not identical live counts.
    """
    meta = dict(meta)
    meta.setdefault("harvested_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    Path(path).write_bytes(dumps(meta))


# ---------------------------------------------------------------------------
# OpenAlex abstract reconstruction (shared: used at parse time, not pull time)
# ---------------------------------------------------------------------------
def reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Rebuild plain abstract text from OpenAlex `abstract_inverted_index`."""
    if not inverted_index:
        return None
    positions: list[tuple[int, str]] = []
    for token, idxs in inverted_index.items():
        for i in idxs:
            positions.append((i, token))
    if not positions:
        return None
    positions.sort(key=lambda x: x[0])
    return " ".join(tok for _, tok in positions)


if __name__ == "__main__":
    # Quick self-test of the secret store.
    print("Central secret store:", CENTRAL_SECRETS, "(exists)" if CENTRAL_SECRETS.exists() else "(MISSING)")
    print("OPENALEX_API_KEY set:", bool(get_secret("OPENALEX_API_KEY")))
    print("OPENALEX_MAILTO     :", get_secret("OPENALEX_MAILTO") or "(none)")
