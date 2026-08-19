# lib/app_config.py
"""
Read the `app:` block of the repo's config.yaml.

The app and the pipeline share ONE config file (D4/R8: a switch, never a rebuild).
Keys (docs/data_contract.yaml -> app_config_keys):

    app.sdg_variant      b_siris | c_openalex | off      (D51)
    app.include_conference   true | false                (D52, sidebar default)
    app.show_hors_liste      true | false                (D56, aggregate default)

The file is looked up by walking up from this file, so the app works whether it is
started as `streamlit run app.py` (cwd = Streamlit/) or `streamlit run Streamlit/app.py`
(cwd = repo root), and on Streamlit Community Cloud.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import streamlit as st
import yaml

DEFAULTS: Dict[str, Any] = {
    "sdg_variant": "b_siris",
    "include_conference": True,
    "show_hors_liste": False,
}

# app.sdg_variant -> (column of sdg_three_way.parquet, human label)
SDG_VARIANTS = {
    "b_siris": ("B_siris", "SIRIS method"),
    "c_openalex": ("C_openalex", "OpenAlex / Aurora"),
}


def _find_config() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "config.yaml"
        if candidate.is_file():
            return candidate
    return None


@st.cache_data
def get_app_config() -> Dict[str, Any]:
    """Return the `app:` block merged over DEFAULTS. Never raises."""
    cfg = dict(DEFAULTS)
    path = _find_config()
    if path is None:
        return cfg
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # a broken config must not take the app down
        return cfg
    block = loaded.get("app") or {}
    if isinstance(block, dict):
        cfg.update({k: v for k, v in block.items() if k in DEFAULTS})
    cfg["sdg_variant"] = _normalise_variant(cfg["sdg_variant"])
    return cfg


def _normalise_variant(value) -> str:
    """
    YAML 1.1 parses an unquoted `off` as the boolean False (same for on/yes/no).
    An operator writing `sdg_variant: off` means the string, so accept both rather
    than silently falling back to the default and leaving the panel on screen.
    """
    if value is False or value is None:
        return "off"
    if value is True:
        return DEFAULTS["sdg_variant"]
    value = str(value).strip().lower()
    return value if value in list(SDG_VARIANTS) + ["off"] else DEFAULTS["sdg_variant"]


def sdg_variant() -> str:
    """Active SDG variant key: 'b_siris', 'c_openalex' or 'off' (D51)."""
    return str(get_app_config()["sdg_variant"])


def sdg_column() -> str | None:
    """Column of sdg_three_way.parquet for the active variant, or None when off."""
    entry = SDG_VARIANTS.get(sdg_variant())
    return entry[0] if entry else None


def sdg_label() -> str:
    """Human label for the active variant."""
    entry = SDG_VARIANTS.get(sdg_variant())
    return entry[1] if entry else "off"
