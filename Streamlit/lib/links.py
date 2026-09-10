# lib/links.py
"""
Pass-5 shared OpenAlex deep-link helper (R5, plan P11) -- authority:
docs/SPRINT_KICKOFF_pass5.md.

Builds https://openalex.org/works?filter=... URLs (the works-list UI, not the raw API)
so a reader can click through from a number in this app to the LIVE, re-runnable
OpenAlex query behind it. The UI and the API share the identical `filter=` grammar (the
UI is a thin front-end over the same endpoint -- OpenAlex's own "Get started with the
free API" messaging on any UI results page is the same query string this module emits);
that grammar was verified EMPIRICALLY against `api.openalex.org` (the funded key, per
SIRIS house rules) rather than assumed -- see `progress/S4_shared_layer.md` §links for
the exact probe calls and non-zero counts. Direct browser automation against the UI
itself was tried once and hit OpenAlex's bot wall ("Looks like you're a bot -- please
use our free API instead"), which is itself evidence the UI is not meant to be scraped
for verification and that the API is the correct empirical proxy for its own grammar.

Two institution scopes, never confused:
  - "lineage" : `authorships.institutions.lineage:<id>` -- the UL CORPUS query (D33).
                UL-specific; never use this scope for a peer (see the root CLAUDE.md
                gotcha: `lineage:` is corrupted for French co-tutelle institutions).
  - "direct"  : `authorships.institutions.id:<id>` -- peer numbers, and UL's own
                direct-id figure when a page needs that (not the lineage corpus).

Not every number this app shows is expressible as a live OpenAlex filter (hand-curated
ISITE list, voctagger SDG tags, the French-baselined FWCI_FR/PPtop_FR indicators,
reciprocity ratios). `NOT_EXPRESSIBLE` names those explicitly so a caller never has to
guess whether to build a link -- and `link_icon()` renders NOTHING when handed `None`,
which is the other half of "explicit, not guessed".
"""
from __future__ import annotations

from typing import Sequence
from urllib.parse import quote

from lib.helpers import UL_OPENALEX_ID  # pass 7a (P-LINKS): single-sourced, never retyped (RA-C05 pattern)

# ============================================================================
# CONSTANTS
# ============================================================================

BASE_URL = "https://openalex.org/works"

# config.yaml corpus_filter.doc_types_keep / metrics.doc_types, verbatim order --
# the 5 corpus types (preprints are excluded from the corpus entirely, D10; the 6th
# DOCTYPE_LABELS slot in lib.helpers is a positional-blob artefact, not a corpus type).
CORPUS_TYPES: tuple[str, ...] = ("article", "book-chapter", "review", "book", "conference-paper")

YEAR_START, YEAR_END = 2019, 2023

_SCOPE_FILTER_KEY = {
    "lineage": "authorships.institutions.lineage",
    "direct": "authorships.institutions.id",
}

_NODE_FILTER_KEY = {
    "field": "primary_topic.field.id",
    "subfield": "primary_topic.subfield.id",
    "topic": "primary_topic.id",
}

# Characters the OpenAlex UI/API accept UNESCAPED in a `filter=` query string (verified
# empirically: colons and commas passed through raw in every probe call). Everything
# else, notably "|" (type unions), is percent-encoded the standard way.
_SAFE_CHARS = ":,-"

LINK_TOOLTIP_FR = "vérification en ligne — décompte vivant, ≈ différent du gel du 11/08"
LINK_ICON_GLYPH = "↗"

# S4 mission note: "numbers NOT expressible get NO icon -- make expressibility explicit,
# not guessed." Keys are free-form labels a page can use in its own code/tests; values
# are the FR one-liner explaining why no OpenAlex filter can express that number.
NOT_EXPRESSIBLE: dict[str, str] = {
    "isite_hand_list": "liste I-SITE constituée à la main (DOI curés) — pas un filtre OpenAlex.",
    "sdg_voctagger": "tags SDG (méthode SIRIS / voctagger) — non exposés par l'API OpenAlex.",
    "fwci_fr": "FWCI normalisé sur la France — recalcul local, pas un champ OpenAlex natif.",
    "pptop_fr": "PPtop France (rang percentile intra-France) — recalcul local, pas un champ natif.",
    "reciprocity": "ratio calculé (share_UL / share_partenaire) — pas un décompte direct.",
}


def expressible(key: str) -> bool:
    """True unless `key` is a named NOT_EXPRESSIBLE indicator."""
    return key not in NOT_EXPRESSIBLE


# ============================================================================
# URL BUILDER
# ============================================================================

def openalex_url(
    institution_id: str,
    *,
    scope: str = "lineage",
    year_from: int = YEAR_START,
    year_to: int = YEAR_END,
    types: Sequence[str] | None = CORPUS_TYPES,
    node: tuple[str, str] | None = None,
) -> str:
    """
    Build an OpenAlex works-list UI URL.

    `scope`: "lineage" (UL corpus, D33) or "direct" (peer numbers, or UL's own
    direct-id figure). `types=None` omits the type filter entirely (all types);
    pass a subset (e.g. `("article",)`) for a type-restricted variant. `node`
    is an optional `(level, value)` pair, `level` in {"field","subfield","topic"},
    e.g. `("field", 11)` -> `primary_topic.field.id:11`.
    """
    if scope not in _SCOPE_FILTER_KEY:
        raise ValueError(f"scope must be one of {sorted(_SCOPE_FILTER_KEY)}; got {scope!r}")

    filters = [f"{_SCOPE_FILTER_KEY[scope]}:{institution_id}",
               f"publication_year:{year_from}-{year_to}"]
    if types:
        filters.append("type:" + "|".join(types))
    if node is not None:
        level, value = node
        if level not in _NODE_FILTER_KEY:
            raise ValueError(f"node level must be one of {sorted(_NODE_FILTER_KEY)}; got {level!r}")
        filters.append(f"{_NODE_FILTER_KEY[level]}:{value}")

    filter_str = ",".join(filters)
    return f"{BASE_URL}?filter={quote(filter_str, safe=_SAFE_CHARS)}"


# ============================================================================
# INLINE ICON
# ============================================================================

def link_icon_html(url: str | None, *, tooltip: str = LINK_TOOLTIP_FR) -> str:
    """
    The `up-right arrow` HTML snippet to place NEXT TO a number (never on the
    number itself, S4 mission note) -- for embedding inline in a markdown/HTML
    string with `unsafe_allow_html=True`. Returns "" when `url` is None: the
    caller's OWN decision not to build a link (see `NOT_EXPRESSIBLE`) renders
    as nothing, never a guessed or broken link.
    """
    if not url:
        return ""
    return (
        f'<a href="{url}" target="_blank" rel="noopener" title="{tooltip}" '
        f'style="text-decoration:none;">{LINK_ICON_GLYPH}</a>'
    )


def link_icon(url: str | None, *, tooltip: str = LINK_TOOLTIP_FR) -> None:
    """
    Streamlit-rendering convenience: draws the icon standalone (e.g. in its own
    narrow column next to `st.metric`). Renders nothing when `url` is None.
    """
    import streamlit as st

    html = link_icon_html(url, tooltip=tooltip)
    if html:
        st.markdown(html, unsafe_allow_html=True)


# ============================================================================
# PASS 7a ADDITIONS (S-LIB-B) -- docs/contract_fragments/lib_api_pass7.md
# Pair-scoped builders: UL is ALWAYS the lineage side (D33's UL corpus query), the
# partner is ALWAYS the direct-id side -- never confused, same convention as the
# module docstring's "Two institution scopes" above. Probe-verified 2026-09-10
# (progress/P7_LIBB.md): `copubs_url(partner)` against the CNRS pair returned a
# non-zero live count on the funded key.
# ============================================================================

IDLIST_MAX = 100

# Sentinel row `docs/contract_fragments/46_geo_countries.yaml` names for the
# unresolved-country bucket (geo_countries.unknown_bucket_flag) -- never build a link
# for a country the source could not identify.
UNKNOWN_COUNTRY_CODE = "UNKNOWN"


def _year_type_node_filters(
    year_from: int, year_to: int, types: Sequence[str] | None, node: tuple[str, str | int] | None,
) -> list[str]:
    """Shared tail every pass-7a pair/country filter appends after its own
    institution term(s): year window, optional type restriction, optional taxonomy
    node -- reuses `_NODE_FILTER_KEY` exactly as `openalex_url` already does above."""
    filters = [f"publication_year:{year_from}-{year_to}"]
    if types:
        filters.append("type:" + "|".join(types))
    if node is not None:
        level, value = node
        if level not in _NODE_FILTER_KEY:
            raise ValueError(f"node level must be one of {sorted(_NODE_FILTER_KEY)}; got {level!r}")
        filters.append(f"{_NODE_FILTER_KEY[level]}:{value}")
    return filters


def copubs_url(
    partner_id: str,
    *,
    node: tuple[str, str | int] | None = None,
    year_from: int = YEAR_START,
    year_to: int = YEAR_END,
    types: Sequence[str] | None = CORPUS_TYPES,
    sort: str | None = None,
) -> str:
    """
    UL (lineage) x partner (direct id) co-publications, live on OpenAlex:
    `authorships.institutions.lineage:I90183372,authorships.institutions.id:{partner},
    publication_year:{y0}-{y1},type:a|b|c|d|e[,primary_topic.<level>.id:<value>]`,
    with `&sort=` appended verbatim when given (unencoded -- a plain `field:direction`
    token, safe as a query value, same convention as BenchUp's own topic_url).
    """
    filters = [
        f"{_SCOPE_FILTER_KEY['lineage']}:{UL_OPENALEX_ID}",
        f"{_SCOPE_FILTER_KEY['direct']}:{partner_id}",
    ]
    filters += _year_type_node_filters(year_from, year_to, types, node)
    url = f"{BASE_URL}?filter={quote(','.join(filters), safe=_SAFE_CHARS)}"
    return f"{url}&sort={sort}" if sort else url


def idlist_url(work_ids: Sequence[str]) -> str:
    """
    `filter=ids.openalex:W1|W2|...` -- a direct list of OpenAlex work ids. Raises
    ValueError when empty or beyond IDLIST_MAX: a filter value list beyond that
    length is UI-unwieldy, and the intended fallback is `phares_url`'s proxy branch,
    never a caller looping this builder to page around the cap.
    """
    ids = list(work_ids)
    if not ids or len(ids) > IDLIST_MAX:
        raise ValueError(f"idlist_url: work_ids must have 1..{IDLIST_MAX} entries; got {len(ids)}")
    filter_str = "ids.openalex:" + "|".join(ids)
    return f"{BASE_URL}?filter={quote(filter_str, safe=_SAFE_CHARS)}"


def phares_url(
    work_ids: Sequence[str], partner_id: str, *, node: tuple[str, str | int] | None = None,
) -> tuple[str, bool]:
    """
    `(idlist_url(ids), False)` for 1..IDLIST_MAX ids (the exact publication list);
    otherwise `(copubs_url(partner_id, node=node, sort="cited_by_count:desc"), True)`
    -- a "most cited first" proxy, never a literal re-application of the top-10%
    decile rule OpenAlex cannot filter on directly. The page shows
    `copy_fr.CAPTIONS["PHARES_PROXY"]` whenever the second element is True.
    """
    ids = list(work_ids)
    if 1 <= len(ids) <= IDLIST_MAX:
        return idlist_url(ids), False
    return copubs_url(partner_id, node=node, sort="cited_by_count:desc"), True


def country_url(country_code: str) -> str | None:
    """
    UL (lineage) x country, live on OpenAlex: `authorships.institutions.lineage:I90183372,
    institutions.country_code:{CC},publication_year:{y0}-{y1},type:a|b|c|d|e`. Returns
    None for the unresolved-country bucket (UNKNOWN_COUNTRY_CODE) or a falsy code --
    never a guessed link for a country the source could not identify. The
    `institutions.country_code` filter key itself is verified live by P-GEO
    (<= 2 calls); this builder only assembles the string.
    """
    if not country_code or str(country_code).strip().upper() == UNKNOWN_COUNTRY_CODE:
        return None
    filters = [
        f"{_SCOPE_FILTER_KEY['lineage']}:{UL_OPENALEX_ID}",
        f"institutions.country_code:{country_code}",
    ]
    filters += _year_type_node_filters(YEAR_START, YEAR_END, CORPUS_TYPES, None)
    return f"{BASE_URL}?filter={quote(','.join(filters), safe=_SAFE_CHARS)}"
