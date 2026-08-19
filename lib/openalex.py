"""Minimal OpenAlex client for the Lorraine v2 pipeline.

Copied INTO this project on purpose (standalone principle): the pipeline must re-run from
config.yaml + these files alone, with no runtime dependency on another SIRIS folder.

Non-negotiables encoded here:
  * the funded key goes in an `Authorization: Bearer` HEADER and `mailto` in the query string.
    The keyless "polite pool" is a $0/day trap that presents as a hang via Retry-After.
  * cursor pagination with a per-shard cursor file, so any crawl is resumable.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import requests


def load_env(env_file: str, required: list[str] | None = None) -> dict[str, str]:
    """Read the central SIRIS secret store. Never inline secrets in config or code."""
    env: dict[str, str] = {}
    path = Path(os.path.expanduser(env_file))
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    for key in required or []:
        if not env.get(key):
            raise SystemExit(f"missing secret {key} in {path}")
    return env


class OpenAlexClient:
    """Rate-limited, retrying OpenAlex client that counts its own calls for the cost ledger."""

    def __init__(self, config: dict, env: dict[str, str]) -> None:
        oa = config["openalex"]
        self.base = oa["base_url"]
        self.per_page = oa["per_page"]
        self.min_interval = 1.0 / float(oa["max_requests_per_second"])
        self.retry = oa["retry"]
        self.mailto = env["OPENALEX_MAILTO"]
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {env['OPENALEX_API_KEY']}"})
        self.calls = 0
        self._last = 0.0

    def get(self, path: str, **params):
        params["mailto"] = self.mailto
        last_error = ""
        for attempt in range(self.retry["attempts"]):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                response = self.session.get(f"{self.base}{path}", params=params, timeout=180)
            except requests.RequestException as exc:  # transient network fault
                last_error = repr(exc)
                time.sleep(self.retry["backoff_base_seconds"] ** (attempt + 1))
                continue
            finally:
                self._last = time.monotonic()
                self.calls += 1
            if response.status_code < 400:
                return response.json()
            last_error = f"HTTP {response.status_code} {response.text[:300]}"
            if response.status_code not in self.retry["retry_on"]:
                raise SystemExit(f"{last_error}\nURL: {response.url}")
            time.sleep(self.retry["backoff_base_seconds"] ** (attempt + 1))
        raise SystemExit(f"gave up after {self.retry['attempts']} attempts on {path}: {last_error}")

    def count(self, filter_string: str) -> int:
        """One cheap call for a filter's total — used by guards and calibration."""
        return self.get("/works", filter=filter_string, per_page=1)["meta"]["count"]

    def crawl(
        self,
        filter_string: str,
        select: str,
        cursor_file: Path | None = None,
        limit: int | None = None,
        label: str = "crawl",
        log_every: int = 25,
    ) -> Iterator[list[dict]]:
        """Yield pages of results, persisting the cursor so an interrupted crawl resumes.

        The cursor file is written BEFORE the caller consumes the page, so a crash mid-write
        re-fetches one page rather than skipping it. Duplicate ids are removed downstream.
        """
        cursor = "*"
        if cursor_file and cursor_file.exists():
            saved = cursor_file.read_text(encoding="utf-8").strip()
            if saved == "DONE":
                print(f"  {label}: already complete, skipping")
                return
            if saved:
                cursor = saved
                print(f"  {label}: resuming from saved cursor")
        seen = 0
        pages = 0
        while cursor:
            page = self.get(
                "/works", filter=filter_string, per_page=self.per_page, cursor=cursor, select=select
            )
            results = page["results"]
            if not results:
                break
            cursor = page["meta"].get("next_cursor")
            if cursor_file:
                cursor_file.write_text(cursor or "DONE", encoding="utf-8")
            yield results
            seen += len(results)
            pages += 1
            if pages % log_every == 0:
                print(f"  {label}: {seen:,} / {page['meta']['count']:,}", flush=True)
            if limit and seen >= limit:
                print(f"  {label}: stopping at calibration limit {limit}")
                return
        if cursor_file:
            cursor_file.write_text("DONE", encoding="utf-8")
        print(f"  {label}: {seen:,} works", flush=True)


def reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Rebuild abstract text from OpenAlex's position index.

    Returns None for missing OR empty results, so `20_abstracts_backfill` sees one single
    "no abstract" condition rather than two.
    """
    if not inverted_index:
        return None
    positions: list[tuple[int, str]] = []
    for word, spots in inverted_index.items():
        for spot in spots:
            positions.append((spot, word))
    if not positions:
        return None
    positions.sort()
    text = " ".join(word for _, word in positions).strip()
    return text or None


def short_id(openalex_url: str | None) -> str | None:
    """`https://openalex.org/W123` -> `W123`. Ids are stored bare everywhere in this pipeline."""
    if not openalex_url:
        return None
    return openalex_url.rsplit("/", 1)[-1]


def ascii_safe_stdout() -> None:
    """The console on the SIRIS Windows box is cp1252; non-ASCII prints raise mid-run."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:  # pragma: no cover
        pass
