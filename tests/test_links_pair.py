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


def test_vacuity_copubs_url_pin_fails_if_the_partner_filter_term_is_dropped():
    """Companion to test_copubs_url_matches_probe_verified_string (P14 / D2 fix): the
    exact-match pin actually discriminates -- a copy of the expected string with the
    partner (`authorships.institutions.id:`) term dropped, or built for a DIFFERENT
    partner, must NOT equal what the real builder returns."""
    correct_pin = (
        "https://openalex.org/works?filter="
        "authorships.institutions.lineage:I90183372,authorships.institutions.id:I1294671590,"
        "publication_year:2019-2023,"
        "type:article%7Cbook-chapter%7Creview%7Cbook%7Cconference-paper"
    )
    url = links.copubs_url(PARTNER_ID)
    assert url == correct_pin  # sanity: the original check still holds before mutating

    dropped_partner_term = correct_pin.replace(",authorships.institutions.id:I1294671590", "")
    assert url != dropped_partner_term  # the original "==" assertion would FAIL against this
    assert links.copubs_url("I9999999999") != correct_pin  # a different partner misses the pin too


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


def test_vacuity_copubs_url_sort_suffix_check_fails_without_a_matching_sort():
    """Companion to test_copubs_url_sort_appended_only_when_given (P14 / D2 fix): the
    endswith check is not vacuous -- a URL built with NO sort, or with a DIFFERENT
    sort value, must NOT satisfy the same "&sort=cited_by_count:desc" suffix."""
    no_sort = links.copubs_url(PARTNER_ID)
    assert not no_sort.endswith("&sort=cited_by_count:desc")

    other_sort = links.copubs_url(PARTNER_ID, sort="publication_date:desc")
    assert not other_sort.endswith("&sort=cited_by_count:desc")


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


def test_vacuity_phares_url_direct_branch_flips_to_proxy_past_the_threshold():
    """Companion to test_phares_url_direct_list_branch (P14 / D2 fix): `is_proxy is
    False` is not a vacuous constant -- pushing the id count one past IDLIST_MAX
    flips the SAME branch to proxy (True), so the direct-branch assertion would
    fail there."""
    at_cap = [f"W{i}" for i in range(links.IDLIST_MAX)]
    _, proxy_at_cap = links.phares_url(at_cap, PARTNER_ID)
    assert proxy_at_cap is False

    over_cap = [f"W{i}" for i in range(links.IDLIST_MAX + 1)]
    _, proxy_over_cap = links.phares_url(over_cap, PARTNER_ID)
    assert proxy_over_cap is not False
    assert proxy_over_cap is True


def test_phares_url_proxy_branch_over_cap():
    big = [f"W{i}" for i in range(links.IDLIST_MAX + 1)]
    url, is_proxy = links.phares_url(big, PARTNER_ID)
    assert is_proxy is True
    assert url == links.copubs_url(PARTNER_ID, sort="cited_by_count:desc")


def test_vacuity_phares_url_proxy_url_is_specific_to_its_own_partner():
    """Companion to test_phares_url_proxy_branch_over_cap (P14 / D2 fix): the equality
    check against `copubs_url(partner_id, ...)` is not trivially satisfied by any
    string -- the SAME over-cap list must yield a DIFFERENT proxy URL for a
    different partner."""
    big = [f"W{i}" for i in range(links.IDLIST_MAX + 1)]
    url, is_proxy = links.phares_url(big, PARTNER_ID)
    assert is_proxy is True
    assert url == links.copubs_url(PARTNER_ID, sort="cited_by_count:desc")

    other_url, _ = links.phares_url(big, "I9999999999")
    assert other_url != url


def test_phares_url_proxy_branch_on_empty():
    """An empty id list is NOT 1<=len<=IDLIST_MAX either -- also the proxy branch,
    never a raised idlist_url ValueError bubbling out of phares_url."""
    url, is_proxy = links.phares_url([], PARTNER_ID)
    assert is_proxy is True
    assert url == links.copubs_url(PARTNER_ID, sort="cited_by_count:desc")


def test_vacuity_phares_url_empty_case_check_fails_for_a_non_empty_short_list():
    """Companion to test_phares_url_proxy_branch_on_empty (P14 / D2 fix): `is_proxy is
    True` is specific to the EMPTY list, not any short list -- a single-id list (also
    below IDLIST_MAX) must NOT be proxied."""
    _, is_proxy_empty = links.phares_url([], PARTNER_ID)
    assert is_proxy_empty is True

    _, is_proxy_one = links.phares_url(["W1"], PARTNER_ID)
    assert is_proxy_one is not True
    assert is_proxy_one is False


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


def test_vacuity_country_url_pin_fails_if_the_country_code_term_is_swapped():
    """Companion to test_country_url_real_code_shape (P14 / D2 fix): the exact-match
    pin actually discriminates -- a copy of the expected string with the country code
    swapped for a different one must NOT equal the real builder's output for "DE"."""
    url = links.country_url("DE")
    swapped = url.replace("institutions.country_code:DE", "institutions.country_code:FR")
    assert swapped != url
    assert links.country_url("FR") != url
