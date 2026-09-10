# tests/test_links.py
"""
Pass-5 unit pins for Streamlit/lib/links.py (R5, plan P11) -- the shared OpenAlex
deep-link helper.

5 canonical URL pins (exact strings) below. The `filter=` grammar they encode was
verified EMPIRICALLY against `api.openalex.org` (funded key, per SIRIS house rules)
before being pinned here -- see progress/S4_shared_layer.md's links section for the
probe calls and the non-zero counts each one returned (36,826 / 1,313 / 40 / 28,485 /
19,610 respectively). openalex.org's UI works-list page shares this exact `filter=`
grammar with its own API (it is a thin front-end over the same endpoint); a direct
Playwright hit against the UI itself was tried once and hit OpenAlex's bot wall
("Looks like you're a bot"), which is itself evidence the API is the correct
empirical proxy for the UI's own grammar, not a workaround.

    python -m pytest tests/test_links.py -q

Namespace note: same `_import_streamlit_lib` swap-trick as tests/test_shared_layer.py.
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

UL_ID = "I90183372"  # config.yaml perimeter.ul_openalex_id / lib.helpers.UL_OPENALEX_ID
PEER_ID = "I2279609970"  # Universite de Lille, inputs/overlays/bench_peers.csv


# ============================================================================
# 5 canonical URL pins (exact strings)
# ============================================================================

def test_url_1_ul_lineage_years_types():
    url = links.openalex_url(UL_ID, scope="lineage")
    assert url == (
        "https://openalex.org/works?filter="
        "authorships.institutions.lineage:I90183372,publication_year:2019-2023,"
        "type:article%7Cbook-chapter%7Creview%7Cbook%7Cconference-paper"
    )


def test_url_2_same_plus_field_node():
    url = links.openalex_url(UL_ID, scope="lineage", node=("field", 11))
    assert url == (
        "https://openalex.org/works?filter="
        "authorships.institutions.lineage:I90183372,publication_year:2019-2023,"
        "type:article%7Cbook-chapter%7Creview%7Cbook%7Cconference-paper,"
        "primary_topic.field.id:11"
    )


def test_url_3_same_plus_subfield_node():
    url = links.openalex_url(UL_ID, scope="lineage", node=("subfield", 1100))
    assert url == (
        "https://openalex.org/works?filter="
        "authorships.institutions.lineage:I90183372,publication_year:2019-2023,"
        "type:article%7Cbook-chapter%7Creview%7Cbook%7Cconference-paper,"
        "primary_topic.subfield.id:1100"
    )


def test_url_4_peer_direct_id_years_types():
    url = links.openalex_url(PEER_ID, scope="direct")
    assert url == (
        "https://openalex.org/works?filter="
        "authorships.institutions.id:I2279609970,publication_year:2019-2023,"
        "type:article%7Cbook-chapter%7Creview%7Cbook%7Cconference-paper"
    )


def test_url_5_type_subset_variant():
    url = links.openalex_url(UL_ID, scope="lineage", types=("article", "conference-paper"))
    assert url == (
        "https://openalex.org/works?filter="
        "authorships.institutions.lineage:I90183372,publication_year:2019-2023,"
        "type:article%7Cconference-paper"
    )


# ============================================================================
# topic node + guard rails
# ============================================================================

def test_url_topic_node():
    url = links.openalex_url(UL_ID, scope="lineage", node=("topic", "T10367"))
    assert url.endswith(",primary_topic.id:T10367")


def test_types_none_omits_type_filter_entirely():
    url = links.openalex_url(UL_ID, scope="lineage", types=None)
    assert "type:" not in url


def test_scope_must_be_lineage_or_direct():
    with pytest.raises(ValueError):
        links.openalex_url(UL_ID, scope="bogus")


def test_node_level_must_be_field_subfield_or_topic():
    with pytest.raises(ValueError):
        links.openalex_url(UL_ID, node=("domain", 1))


# ============================================================================
# link_icon -- explicit, never guessed
# ============================================================================

def test_link_icon_html_empty_string_when_url_is_none():
    """The other half of 'explicit, not guessed': no URL -> no icon, ever."""
    assert links.link_icon_html(None) == ""


def test_link_icon_html_renders_anchor_next_to_a_number():
    html = links.link_icon_html("https://openalex.org/works?filter=x:y")
    assert html.startswith("<a href=")
    assert links.LINK_ICON_GLYPH in html
    assert "https://openalex.org/works?filter=x:y" in html


def test_expressible_flags_the_named_non_expressible_indicators():
    for key in links.NOT_EXPRESSIBLE:
        assert links.expressible(key) is False
    assert links.expressible("partner_co_works_full") is True
    assert links.expressible("ul_corpus_total") is True
