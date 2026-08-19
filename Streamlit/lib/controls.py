# lib/controls.py
"""
W5 shared control layer (chassis wiring) -- authority: docs/foundry/data_foundation.yaml
rev 3.1 (conventions block) + docs/indicator_plan_FINAL.md §6.2 + docs/studio/VIZ_SPEC.md
§1.2/§1.5 + pass-5 kickoff rulings R1/R14 (docs/SPRINT_KICKOFF_pass5.md).

Sidebar order (pass 5, R1 -- SUPERSEDES the VIZ_SPEC 1.5 four-control listing): conference
toggle (D52, reused from lib.helpers, never duplicated) -> artifact toggle (default OFF) ->
I-SITE overlay toggle (default OFF, NEW this pass) -> snapshot badge. The global PERIMETER
SELECTOR is REMOVED from the sidebar (R1): I-SITE becomes an overlay everywhere instead of a
corpus-narrowing filter. The `dim_subsets` registry data/page and the subset-grain table rows
are untouched -- only the sidebar control that used to set the global perimeter is gone.
`sidebar()` keeps returning a `perimeter_subset` key for backward compatibility with the 12
pages that already read it -- it is now the hardcoded constant `"all"`, so every page renders
the full corpus (the correct new behaviour) with zero page edits required this pass.

Two disclosure strips exist for the SAME artifact toggle because the toggle means different
things on different pages (rev 3.1 ruling):
  - banner()          : NEW pages, where ON really drops flagged works/topics.
  - ships_v2_strip()  : ships-v2 parity pages, where nothing is actually recomputed --
                        the standard banner text would lie there.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from lib.data_cache import DATA_DIR
from lib.helpers import (
    artifact_topics_count,
    artifact_topics_share_pct,
    conference_toggle,
    fr_int,
    fr_pct,
    render_methodo_expander,
)

# ============================================================================
# CONSTANTS (verbatim text is load-bearing -- see plan §6.2 / YAML conventions)
# ============================================================================

# Pass-6 re-open (NARRATIVE_CONTRACT_pass6.md S-LIB row (c) / P6-R2): the topic
# count and the share of the reference corpus it represents are COMPUTED from
# the deployed data -- never a hardcoded literal that goes stale the moment the
# snapshot/registry changes. Computed ONCE per process (module import, same
# convention as lib.ranked.CONSORTIUM_IDS) -- a fresh deploy on a new snapshot
# re-imports this module and picks up the new numbers automatically.
_ARTIFACT_N_TOPICS = artifact_topics_count()
_ARTIFACT_SHARE_PCT = artifact_topics_share_pct()  # None if undeterminable
_ARTIFACT_SHARE_FR = fr_pct(_ARTIFACT_SHARE_PCT, decimals=2) if _ARTIFACT_SHARE_PCT is not None else None


def _artifact_share_em_clause() -> str:
    """' — {share} des travaux' (FR-formatted share, computed), or '' when the
    share cannot be derived from the deployed data (manager ruling: dropped,
    never guessed) -- the em-dash clause shared by the banner text and the
    toggle's help string."""
    if _ARTIFACT_SHARE_FR is None:
        return ""
    return f" — {_ARTIFACT_SHARE_FR} des travaux"


def _artifact_share_paren(sign: str) -> str:
    """' ({sign}{share} des travaux)', or '' when undeterminable (dropped) --
    the parenthetical clause the toggle's own on/off captions append."""
    if _ARTIFACT_SHARE_FR is None:
        return ""
    return f" ({sign}{_ARTIFACT_SHARE_FR} des travaux)"


ARTIFACT_TOGGLE_KEY = "artifact_filter"
ARTIFACT_TOGGLE_LABEL = f"Exclure les {fr_int(_ARTIFACT_N_TOPICS)} topics hors référentiel"

def _isite_list_vintage_date() -> str:
    """
    Pass-6 fix round (S-LENS D3): the DOI-list vintage date used to be a
    hardcoded literal ("2026-08-10") right in this help string -- a genuine
    calendar fact, but one that already lives on disk (`dim_subsets.parquet`,
    `in_isite` row's `vintage_date` column -- the exact same field the
    I-SITE page's own KPI-row caveat reads live,
    `Streamlit/pages/7_🎯_I-SITE.py:334`). The list refresh is an OPEN client
    ask (BUILD_STATE §5 item 2): hardcoding meant this line would silently
    lie the day the list is refreshed. Computed ONCE at import time (same
    "computed once per process" pattern as `_ARTIFACT_N_TOPICS` above).
    Falls back to "?" (never a guessed date, never a crash) if the table/row
    is missing.
    """
    try:
        subsets = pd.read_parquet(DATA_DIR / "dim_subsets.parquet", columns=["subset_id", "vintage_date"])
        row = subsets.loc[subsets["subset_id"] == "in_isite"].iloc[0]
        vintage = row["vintage_date"]
        if pd.notna(vintage):
            return str(vintage)
    except Exception:
        pass
    return "?"


_ISITE_LIST_VINTAGE_DATE = _isite_list_vintage_date()

# Pass-5 R1/P10: I-SITE becomes an overlay everywhere, never a corpus filter. Default OFF --
# an off-default visual state, exactly like the artifact toggle's own convention.
ISITE_OVERLAY_KEY = "isite_overlay"
ISITE_OVERLAY_LABEL = "Afficher la contribution I-SITE"
# I2-07 fix (partial, LENS_ABSORPTION_pass5.md): absorb the vintage caveat into the help
# text (rebutted: the "contribution" wording itself stays -- R1 verbatim, owner-ruled).
# Wording reused verbatim from the I-SITE page's own KPI-row caveat
# (Streamlit/pages/7_🎯_I-SITE.py, "liste canonique ... datée du {vintage} ... retard de
# mise à jour de la liste, jamais ... un recul réel") -- the vintage date is now COMPUTED
# from `dim_subsets.vintage_date` (S-LENS D3 fix, pass-6 fix round), same as the artifact
# toggle's own help string a few lines above, which computes its topic count and share
# from the deployed data (pass-6 re-open, P6-R2) rather than hardcoding either literal.
ISITE_OVERLAY_HELP_FR = (
    "Superpose, sur les graphiques concernés, la part I-SITE (teinte plus sombre de la même "
    "couleur) sans jamais retirer de travaux du corpus affiché -- lib.overlay porte la "
    f"grammaire visuelle partagée. Liste canonique datée du {_ISITE_LIST_VINTAGE_DATE} -- les "
    "années récentes sont sous-couvertes (retard de mise à jour de la liste, jamais un recul "
    "réel de la production I-SITE)."
)

# ============================================================================
# I-SITE overlay surface registry (I2-05 fix, state strip)
# ============================================================================
#
# docs/OVERLAY_MATRIX.md is the single source of truth this set is derived from: a page
# belongs here iff at least one of its panels is rated EXISTING (same-row or row-swap) or
# EXTEND for the I-SITE overlay there -- i.e. the toggle actually changes something visible
# on that page. Pages rated N/A / N/A-disclosed on EVERY one of their panels are excluded:
#   - "3" (Périmètres personnalisés) and "7" (I-SITE): the matrix marks both N/A because the
#     whole page already IS the perimeter selector / the ISITE-vs-site lens -- both already
#     carry their OWN explicit no-op caption in page code, so the generic strip must add
#     nothing there (I2-06's "chaque barre" overclaim is exactly what this avoids repeating).
#   - "11" (Annuaire auteurs) and "13" (Identifiants et couverture): author-safeguard /
#     structural N/A (matrix §11/§13) -- the toggle truly does nothing on these two named-
#     person pages, which is precisely the case I2-05 caught the old strip lying about
#     ("Filtré par : ... contribution I-SITE affichée en surcouche" on a page with zero
#     overlay surface, in the exact vocabulary the author safeguards exist to avoid).
#   - "14" (Benchmark): peers carry no I-SITE concept anywhere on the page (matrix §14).
# Menu (`app.py`) never calls filtered_by_strip() at all, so it needs no entry here.
ISITE_OVERLAY_SURFACE_PAGES = frozenset({
    "vue_densemble",            # 1  -- doc types / year x type / consortium (matrix §1)
    "laboratoires",             # 2  -- overview + field distribution (matrix §2)
    "portefeuille_thematique",  # 4  -- treemap / overview-FWCI / topics / contrib. analysis (§4)
    "positionnement",           # 5  -- emerging topics / frontier x labs crossing (§5)
    "exploration_thematique",   # 6  -- KPI strip / contribution analysis (§6)
    "collaborations",           # 8  -- partenaires hub / consortium cards (§8)
    "zoom_partenaire",          # 9  -- profil thématique ptn_fields twin (§9)
    "geographie",                # 10 -- pays / UniGR / EURECA-PRO (§10)
    "profil_auteur",            # 12 -- yearly output bar, work-grain in_isite (§12)
})

# indicator_plan_FINAL.md §6.2 (wording), pass-6 re-open (numbers now computed, P6-R2).
ARTIFACT_BANNER_TEXT_FR = (
    f"Filtré : {fr_int(_ARTIFACT_N_TOPICS)} topics exclus (limite du classifieur, jamais un "
    f"jugement sur la recherche){_artifact_share_em_clause()}, concentrés en SHS francophone."
)

# docs/foundry/data_foundation.yaml rev 3.1 conventions block, verbatim (ships-v2 strip).
SHIPS_V2_STRIP_TEXT_FR = (
    "Le filtre « hors référentiel » s'applique aux nouvelles vues ; cette page v2 "
    "affiche le corpus entier — lignes concernées marquées †."
)

# VIZ_SPEC 1.2: the marker tooltip on a flagged table row/cell.
MARKER_DAGGER_TOOLTIP_FR = (
    "Hors référentiel mondial — limite du classifieur (modèle entraîné sur la "
    "littérature anglophone), jamais un jugement sur la recherche."
)

DAGGER = "†"  # "†"

# VIZ_SPEC 1.1: comparison/reference grey -- reused for the tunnel-#17 grey-out
# (a DIFFERENT rule from the ARTIFACT-FLAG marker: whole exempt/deferred measure
# families grey out on purpose; individual flagged ROWS are never demoted).
DEFERRED_GREY = "#8C9196"


# ============================================================================
# CROSS-PAGE PERSISTENCE (F1/QA-01/RA-A03 fix)
# ============================================================================
#
# Root cause (Codex inspection, QA-01/RA-A03): by default (`persist_state=None`),
# a Streamlit widget's value is lost the moment its widget stops being the one
# rendered in a script run -- which is exactly what happens on every sidebar
# page navigation in this multipage app, even though the SAME widget (same
# `key`) gets redrawn on the next page a moment later. The selector/toggle
# therefore silently reset to their coded defaults instead of "following the
# user across pages" as every one of this file's own docstrings already
# claimed.
#
# First attempt (superseded): a hand-rolled write-through to a stable
# `_persist_<name>` session_state twin, seeded back before each widget's own
# instantiation. It looked right and passed an isolated unit test, but the
# Playwright journey proof (progress/CXFIX_codex_fixes.md) caught it failing
# on a SECOND page switch: Streamlit's widget-id hashing is per-page (a keyed
# widget remounts under a NEW element id on a new page script), so a plain
# session_state write-through does not reliably reattach across more than one
# hop -- exactly the kind of interaction bug a live render proves and a pure
# unit test cannot.
#
# ACTUAL fix: this Streamlit build (1.61) ships a first-party, documented
# ``persist_state`` parameter on keyed widgets (`st.selectbox`, `st.toggle`,
# ...) for precisely this case -- ``persist_state="session"`` preserves a
# widget's value for the WHOLE session, including across page switches,
# restoring it when the user navigates back (`"page"` scope, the closest
# thing to the old default, still drops it on a page switch; `None`, the
# widget default, drops it immediately). Fix, in ONE place per widget: add
# `persist_state="session"` to every shared control widget -- originally
# perimeter_selector()/artifact_toggle() below plus lib.helpers.
# conference_toggle() itself (its widget call is edited in place, never
# duplicated -- module docstring).
#
# Pass 5 (R1, 2026-08-18): perimeter_selector() and its own persistence pin
# (`test_perimeter_selector_widget_requests_session_persistence`) are RETIRED
# together with the sidebar perimeter selector itself -- I-SITE is an overlay
# everywhere now, not a corpus filter, so there is no more selector widget to
# persist. isite_overlay_toggle() below is the THIRD widget that needs the
# same `persist_state="session"` fix (alongside artifact_toggle() and
# lib.helpers.conference_toggle()), and its own source-level pin replaces the
# retired one in tests/test_shared_layer.py.


# ============================================================================
# SIDEBAR CONTROLS
# ============================================================================

def artifact_toggle() -> bool:
    """
    ARTIFACT-FLAG global toggle (plan §6.2). Default OFF: everything shown,
    flagged content included. Shared key (`artifact_filter`) so the choice
    follows the user across pages, mirroring helpers.conference_toggle()'s
    `include_conference` key.
    """
    st.sidebar.markdown("### Référentiel")
    on = st.sidebar.toggle(
        ARTIFACT_TOGGLE_LABEL,
        value=False,
        key=ARTIFACT_TOGGLE_KEY,
        persist_state="session",  # F1/QA-01/RA-A03 fix: survive a sidebar page switch
        help=(
            f"{fr_int(_ARTIFACT_N_TOPICS)} topics qu'OpenAlex résout mal (limite du "
            f"classifieur, jamais un jugement sur la recherche){_artifact_share_em_clause()}. "
            "Défaut : inclus."
        ),
    )
    if on:
        st.sidebar.caption(
            f":grey[Topics hors référentiel **exclus**{_artifact_share_paren('−')}.]"
        )
    else:
        st.sidebar.caption(":grey[Topics hors référentiel **inclus** (défaut).]")
    return on


def isite_overlay_toggle() -> bool:
    """
    Pass-5 R1/P10 global toggle: I-SITE stops being a corpus filter and becomes an
    OVERLAY every chart/table can render on top of the full corpus. Default OFF
    (an off-default visual state, same convention as artifact_toggle()). Shared key
    (`isite_overlay`) so the choice follows the user across pages; the actual overlay
    RENDERING (darker-shade stacked segment, tooltip, table-column variant) lives in
    lib.overlay -- this function only owns the sidebar widget and its own state.
    """
    st.sidebar.markdown("### I-SITE")
    on = st.sidebar.toggle(
        ISITE_OVERLAY_LABEL,
        value=False,
        key=ISITE_OVERLAY_KEY,
        persist_state="session",  # same persist_state="session" fix as the other 2 widgets
        help=ISITE_OVERLAY_HELP_FR,
    )
    if on:
        st.sidebar.caption(":grey[Contribution I-SITE **affichée** en surcouche.]")
    else:
        st.sidebar.caption(":grey[Contribution I-SITE masquée (défaut).]")
    return on


def snapshot_badge(snapshot_date: str | None = None) -> None:
    """Footer snapshot badge, on every page (VIZ_SPEC 1.5)."""
    if snapshot_date is None:
        try:
            from lib.data_cache import get_corpus_facts_df
            facts = get_corpus_facts_df()
            snapshot_date = str(facts["snapshot_date"].iloc[0]) if len(facts) else "?"
        except Exception:
            snapshot_date = "?"
    st.sidebar.caption(f"Snapshot : {snapshot_date}")


def sidebar() -> dict:
    """
    Render the full control layer in the pass-5 mandated order (R1, SUPERSEDES VIZ_SPEC
    1.5's four-control listing): conference toggle -> artifact toggle -> I-SITE overlay
    toggle -> snapshot badge. Returns the resolved state for callers that want it inline.

    conference_toggle() itself lives in lib.helpers (reused, never duplicated -- module
    docstring); its own widget call carries `persist_state="session"` directly
    (F1/QA-01/RA-A03 fix), so nothing extra is needed here around this call.

    Compatibility rule (R1): the returned dict still carries `perimeter_subset` so the
    12 pre-pass-5 pages that already read it keep working with ZERO page edits -- it is
    now the hardcoded constant `"all"` (the sidebar selector that used to set it is
    gone), so every page renders the full corpus, which is the correct new behaviour.
    """
    include_conf = conference_toggle()
    artifact_on = artifact_toggle()
    isite_overlay_on = isite_overlay_toggle()
    try:
        render_methodo_expander()  # P6-R2/P1: méthodo guide, directly under the 3 toggles
    except KeyError as e:
        # render_methodo_expander()'s own st.page_link("Menu.py", ...) raises exactly
        # KeyError('url_pathname') when the CURRENTLY LOADED script has no pages/
        # registry built -- Streamlit computes `PagesManager.uses_pages_directory`
        # from the loaded script's OWN parent directory (tests/test_page_pa.py's
        # module docstring: "pages/pages/ does not exist"), which is only ever false
        # under `AppTest.from_file(<a single page>)` standalone (never in the
        # deployed app, which always resolves through Menu.py's own multipage
        # router, nor under the Menu.py-bootstrap + switch_page pattern most of this
        # suite already uses). Narrowly matched on the exact message so any OTHER
        # KeyError inside the méthodo render (e.g. a real format-string bug) still
        # surfaces instead of being masked.
        if str(e) != "'url_pathname'":
            raise
    snapshot_badge()
    return {
        "perimeter_subset": "all",  # R1: constant -- the global selector is retired
        "include_conference": include_conf,
        ARTIFACT_TOGGLE_KEY: artifact_on,
        ISITE_OVERLAY_KEY: isite_overlay_on,
    }


# ============================================================================
# DISCLOSURE STRIPS
# ============================================================================

def banner() -> None:
    """Full-width §6.2 disclosure banner on NEW pages, while the toggle is ON."""
    if st.session_state.get(ARTIFACT_TOGGLE_KEY, False):
        st.warning(ARTIFACT_BANNER_TEXT_FR)


def ships_v2_strip() -> None:
    """
    Distinct honest strip for ships-v2 parity pages (rev 3.1 ruling): the
    standard banner would lie there (nothing is actually filtered on these
    pages yet), so this discloses the true state instead. Renders only while
    the artifact toggle is ON.
    """
    if st.session_state.get(ARTIFACT_TOGGLE_KEY, False):
        st.warning(SHIPS_V2_STRIP_TEXT_FR)


def filtered_by_strip(extra: list[str] | None = None, *, page: str | None = None) -> None:
    """
    "Filtré par …" line under the page title whenever ANY control that
    ACTUALLY FILTERS is off-default (VIZ_SPEC 1.5, mandatory). `extra` lets a
    page append its own local-control descriptions (type filter, floor
    slider, search).

    I2-05 fix: the I-SITE overlay is NOT part of this sentence any more --
    the overlay never removes a row, so folding it into "Filtré par : ..."
    asserted a filter that does not exist (on named-person pages this read as
    "filtering people by programme membership", the exact RGPD-adjacent
    misreading the author safeguards exist to avoid). It is now a SEPARATE
    caption, worded "Surcouche I-SITE affichée" (never "Filtré"), and it only
    renders when `page` names a page with an actual overlay surface
    (`ISITE_OVERLAY_SURFACE_PAGES`, OVERLAY_MATRIX-driven) -- never on a page
    where the toggle does nothing, and never when the caller omits `page`
    (safe default: no page name means "unknown", so say nothing rather than
    guess).
    """
    bits: list[str] = []
    if not st.session_state.get("include_conference", True):
        bits.append("papiers de conférence exclus")
    if st.session_state.get(ARTIFACT_TOGGLE_KEY, False):
        bits.append("topics hors référentiel exclus")
    bits.extend(extra or [])
    if bits:
        st.caption("Filtré par : " + " · ".join(bits) + ".")

    if st.session_state.get(ISITE_OVERLAY_KEY, False) and page in ISITE_OVERLAY_SURFACE_PAGES:
        st.caption(":grey[Surcouche I-SITE affichée.]")


def perimeter_disclosure_strip() -> None:
    """
    R-B legacy strip for panels that carry no subset rows of their own (rev 3.1
    conventions: "PERIMETER SELECTOR on panels WITHOUT subset rows ... explicit
    disclosure strip; never a silently unfiltered number").

    Pass 5 (R1): the global perimeter selector is retired, so `perimeter_subset`
    can no longer be anything but "all" -- the branch that used to fire on a
    non-default subset is unreachable and has been dropped; this simplifies to
    the single message every call site now always means. Existing call sites
    (guarded by `if ... != "all":`, permanently False now) are page content and
    stay as-is this pass -- they simply never fire, which is harmless.
    """
    st.caption(
        ":grey[Ce panneau n'a pas de déclinaison par périmètre — corpus entier.]"
    )


# ============================================================================
# ARTIFACT-FLAG cell/column helpers
# ============================================================================

def xa(df: pd.DataFrame, col: str) -> str:
    """
    Return the `_xa` twin column name when the artifact toggle is ON and the
    twin exists in `df`, else the base column name. Callers read whichever
    name comes back instead of branching on the toggle themselves.
    """
    if st.session_state.get(ARTIFACT_TOGGLE_KEY, False):
        twin = f"{col}_xa"
        if twin in df.columns:
            return twin
    return col


def grey_deferred(styler_or_colconfig, cols: list[str]):
    """
    Grey out a deferred-twin / artifact_exempt measure family and append the
    dagger to its header (tunnel #17). This is deliberately the OPPOSITE
    treatment from a flagged ROW (VIZ_SPEC 1.2 forbids demoting those): here
    the whole family is inert under the toggle, so disclosing it as inert is
    the honest choice, not an erasure.

    Accepts either:
      - a pandas Styler -> returns a Styler with `cols` greyed (data untouched,
        only the displayed colour and header label change);
      - a dict (`st.dataframe` column_config) -> returns an updated dict with
        each named column disabled and its label suffixed with the dagger.
    """
    cols = list(cols)
    if isinstance(styler_or_colconfig, dict):
        cfg = dict(styler_or_colconfig)
        for c in cols:
            cfg[c] = st.column_config.Column(
                label=f"{c} {DAGGER}",
                disabled=True,
                help="Famille de mesure figée sous le filtre référentiel actif "
                     "(non recalculée -- disclosed, not recomputed).",
            )
        return cfg

    styler = styler_or_colconfig
    present = [c for c in cols if c in styler.data.columns]
    return styler.set_properties(subset=present, **{"color": DEFERRED_GREY}).format_index(
        lambda c: f"{c} {DAGGER}" if c in cols else c, axis=1
    )


def marker_dagger_column(df: pd.DataFrame, flag_col: str = "artifact_flag") -> pd.Series:
    """
    « Réf. » † column values (VIZ_SPEC 1.2, table-row rendering): a dagger on
    flagged rows, blank otherwise. This ADDS a column; it never greys, hides
    or reorders the flagged row (disclose, never demote).
    """
    if flag_col not in df.columns:
        return pd.Series([""] * len(df), index=df.index, name="Réf.")
    flags = df[flag_col].fillna(False).astype(bool)
    return flags.map({True: DAGGER, False: ""}).rename("Réf.")


def marker_dagger_column_config(help_text: str = MARKER_DAGGER_TOOLTIP_FR):
    """`st.dataframe` column_config entry for the « Réf. » column."""
    return st.column_config.TextColumn("Réf.", help=help_text, width="small")


def marker_dagger_cell_label(value: Any, flagged: bool) -> str:
    """Treemap/heatmap cell label: append the dagger, no texture (VIZ_SPEC 1.2)."""
    return f"{value} {DAGGER}" if flagged else str(value)
