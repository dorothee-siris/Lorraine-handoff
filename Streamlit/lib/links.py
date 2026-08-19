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
