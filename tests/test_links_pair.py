# tests/test_links_pair.py
r"""
Pass-7a unit pins for the pair-scoped additions to Streamlit/lib/links.py (S-LIB-B,
docs/contract_fragments/lib_api_pass7.md) -- copubs_url / idlist_url / phares_url /
country_url.

`copubs_url`'s canonical pin below is the probe-verified string named in
progress/briefs/P7_LIBB.md (2026-09-10, the CNRS-pair partner id, non-zero live count
on the funded key -- see that brief for the exact probe call). `country_url`'s
"unknown" sentinel ("UNKNOWN") is read from docs/contract_fragments/46_geo_countries.yaml,
not guessed.

    .venv-pinned\Scripts\python -m pytest tests\test_links_pair.py -q

Namespace note: same `_import_streamlit_lib` swap-trick as tests/test_links.py (see its
docstring) -- Streamlit/lib and the repo-root pipeline `lib` package would otherwise
collide under the same `lib` name in `sys.modules`.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"


def _import_streamlit_lib(*names: str):
    saved = {k: v for k, v in sys.modules.items() if k == "lib" or k.startswith("lib.")}
    for k in saved:
        del sys.modules[k]
    sys.path.insert(0, str(STREAMLIT_DIR))
    try:
        mods = tuple(importlib.import_module(f"lib.{n}") for n in names)
    finally:
        sys.path.remove(str(STREAMLIT_DIR))
        for k in [k for k in sys.modules if k == "lib" or k.startswith("lib.")]:
            del sys.modules[k]
        sys.modules.update(saved)
    return mods


(links,) = _import_streamlit_lib("links")

# Probe-verified partner id, docs/contract_fragments/lib_api_pass7.md Inputs section /
# progress/briefs/P7_LIBB.md (the pinned pair URL).
PARTNER_ID = "I1294671590"


# ============================================================================
# copubs_url
# ============================================================================

def test_copubs_url_matches_probe_verified_string():
    url = links.copubs_url(PARTNER_ID)
    assert url == (
        "https://openalex.org/works?filter="
        "authorships.institutions.lineage:I90183372,authorships.institutions.id:I1294671590,"
        "publication_year:2019-2023,"
        "type:article%7Cbook-chapter%7Creview%7Cbook%7Cconference-paper"
    )


def test_copubs_url_node_variants_and_guard_rail():
    field_url = links.copubs_url(PARTNER_ID, node=("field", 11))
    assert field_url.endswith(",primary_topic.field.id:11")
    subfield_url = links.copubs_url(PARTNER_ID, node=("subfield", 1100))
    assert subfield_url.endswith(",primary_topic.subfield.id:1100")
    topic_url = links.copubs_url(PARTNER_ID, node=("topic", "T10367"))
    assert topic_url.endswith(",primary_topic.id:T10367")
    # vacuity: an invalid node level must raise, not silently produce a wrong filter
    with pytest.raises(ValueError):
        links.copubs_url(PARTNER_ID, node=("domain", 1))


def test_copubs_url_sort_appended_only_when_given():
    with_sort = links.copubs_url(PARTNER_ID, sort="cited_by_count:desc")
    assert with_sort.endswith("&sort=cited_by_count:desc")
    without_sort = links.copubs_url(PARTNER_ID)
    assert "&sort=" not in without_sort


# ============================================================================
# idlist_url
# ============================================================================

def test_idlist_url_basic_and_guard_rails():
    url = links.idlist_url(["W1", "W2", "W3"])
    assert url == "https://openalex.org/works?filter=ids.openalex:W1%7CW2%7CW3"

    with pytest.raises(ValueError):
        links.idlist_url([])
    with pytest.raises(ValueError):
        links.idlist_url([f"W{i}" for i in range(links.IDLIST_MAX + 1)])
    # vacuity: exactly at the cap must NOT raise
    at_cap = links.idlist_url([f"W{i}" for i in range(links.IDLIST_MAX)])
    assert at_cap.count("%7C") == links.IDLIST_MAX - 1


# ============================================================================
# phares_url -- both branches
# ============================================================================

def test_phares_url_direct_list_branch():
    small = [f"W{i}" for i in range(5)]
    url, is_proxy = links.phares_url(small, PARTNER_ID)
    assert is_proxy is False
    assert url == links.idlist_url(small)


def test_phares_url_proxy_branch_over_cap():
    big = [f"W{i}" for i in range(links.IDLIST_MAX + 1)]
    url, is_proxy = links.phares_url(big, PARTNER_ID)
    assert is_proxy is True
    assert url == links.copubs_url(PARTNER_ID, sort="cited_by_count:desc")


def test_phares_url_proxy_branch_on_empty():
    """An empty id list is NOT 1<=len<=IDLIST_MAX either -- also the proxy branch,
    never a raised idlist_url ValueError bubbling out of phares_url."""
    url, is_proxy = links.phares_url([], PARTNER_ID)
    assert is_proxy is True
    assert url == links.copubs_url(PARTNER_ID, sort="cited_by_count:desc")


# ============================================================================
# country_url
# ============================================================================

def test_country_url_none_on_unknown_bucket_and_falsy():
    assert links.country_url("UNKNOWN") is None
    assert links.country_url(None) is None
    assert links.country_url("") is None
    # vacuity: a real ISO code must NOT be treated as the unknown bucket
    assert links.country_url("DE") is not None


def test_country_url_real_code_shape():
    url = links.country_url("DE")
    assert url == (
        "https://openalex.org/works?filter="
        "authorships.institutions.lineage:I90183372,institutions.country_code:DE,"
        "publication_year:2019-2023,"
        "type:article%7Cbook-chapter%7Creview%7Cbook%7Cconference-paper"
    )
