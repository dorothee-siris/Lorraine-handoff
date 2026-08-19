# Vendored connectors — copied verbatim from `SIRIS\Tools\connectors` on 2026-08-11

Per the SIRIS standalone-project principle, these are **copies**: nothing in this pipeline imports
from `Tools\` at runtime. Keep them byte-identical to the cookbook so a future `diff` against
`SIRIS\Tools\connectors\` shows only upstream changes.

| File | Used by | Notes |
|---|---|---|
| `common.py` | everything | `get_secret` (central `~/.siris/.env`), `make_session` (Retry + backoff + `Retry-After`), `TokenBucket`, `dumps`/`read_jsonl`, checkpoint `.cursor` + `DONE` idiom, `write_manifest`, `reconstruct_abstract`. |
| `hal.py` | `20_abstracts_backfill.py` | Solr search API with **cursorMark** deep paging, `rows=1000`, `sort=docid asc`, 3 req/s. Harvests by **`structId_i`** — a structure-scoped bulk harvest, not per-DOI lookups. Wide `fl` already includes `abstract_s`, `doiId_s`, `authIdHal_s`, `authORCIDIdExt_s`. |
| `openaire.py` | `20_abstracts_backfill.py` | Graph v1 with cursor paging by `relOrganizationId`; token optional. **Its parsing helpers matter:** `extract_doi()` knows DOIs are *not* in the often-null `pids` field but in `instances[].urls`; `abstract_of()` takes the longest `descriptions` entry. |
| `openalex.py` | reference | `lib/openalex.py` in this project already implements the same contract (Bearer header + mailto, cursor resume) plus the D34 authorship-truncation repair, which the cookbook version does not have — **that fix should be contributed back upstream.** |

## What reading the cookbook changed

1. **HAL is a bulk structure harvest, not a DOI lookup service.** 10,372 of this corpus's no-DOI works
   have HAL as their primary source, so a `structId_i` harvest reaches abstracts that no DOI-keyed
   request ever could. This is the cheaper *and* more complete route.
2. **OpenAIRE DOIs live in `instances[].urls`**, not `pids` — a trap already solved here.
3. `make_session()` honours `Retry-After` via urllib3 `Retry`, which is strictly better than the
   hand-rolled sleep loop it replaces.
