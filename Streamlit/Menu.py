from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from lib.app_config import sdg_label, sdg_variant
from lib.controls import snapshot_badge
from lib.helpers import render_methodo_menu_section, window_label

# ============================================================================
# NAV LABEL FINDING (pass 5, P-A, R12/R19) -- kept as a code comment because it
# explains a constraint the rest of this file works around, not because a
# reader of the running app needs it. Full writeup + human-gate proposal:
# progress/PA_menu_overview_perimetres.md S1.
#
# Verified empirically (not guessed): Streamlit 1.61's sidebar label for the
# MAIN script of a classic pages/-directory app is derived from the script's
# OWN filename via streamlit.source_util.page_icon_and_name(), the exact
# function `pages/*.py` files are named after -- there is no separate
# "title=" surface for the main script unless app.py itself calls
# st.navigation() (a chassis-level routing change, W5/S4 territory, not a
# page-content stream's fence). st.set_page_config(page_title=...) only sets
# the browser-tab <title>, never the sidebar label (confirmed by reading
# streamlit/commands/page_config.py: it forwards to a different proto field).
# Empirical probe: page_icon_and_name(Path("app.py")) -> ("", "app") ->
# Page.__init__'s own title fallback is `inferred_name.replace("_", " ")`,
# i.e. the literal string "app" (no capitalisation step anywhere in the
# Python source). So today's sidebar nav entry for this script reads "app",
# lower-case, regardless of this file's st.title()/page_title. Renaming this
# file is therefore the only in-app fix -- explicitly a human gate (Streamlit
# Community Cloud's configured "main file path" would need updating too), so
# this file is NOT renamed; the page is titled "Menu" in-body instead, and
# the rename is proposed as a decision line in the progress file.
# ============================================================================

st.set_page_config(page_title="Menu | Lorraine Explorer v2", layout="wide")
st.title("Menu")

# NARRATIVE_CONTRACT_pass6.md section 3.1, verbatim (P6-R2 mode-d'emploi rewrite --
# replaces the pass-5 titles-as-answers-adjacent intro; the closing question mark is
# gone on purpose, this is no longer a rhetorical question but a plain statement of
# what the page does).
st.markdown("### Par où commencer")
st.caption(
    "Cette page répond à une question simple : par quelle vue commencer, selon ce que "
    "l'on prépare."
)

# S10 audience note (indicator_plan_FINAL.md §6.5/S10): the app is framed, everywhere,
# as an animation tool, jamais un classement des laboratoires, partenaires ou personnes.
# Meaning kept verbatim (R17), wording en français (R12, D61 reversed 2026-08-18).
st.markdown(
    "Un « **outil d'animation scientifique** » : suivre les partenariats, les dynamiques "
    "thématiques et les profils pour engager la conversation, jamais classer les "
    "structures, les partenaires ou les personnes entre eux."
)

st.write(
    "Ouvrir une vue depuis la barre latérale, ou l'une des cartes ci-dessous. Trois "
    "parcours sont proposés plus bas ; chacun se lit dans l'ordre, et chaque étape dit "
    "ce qu'on y trouve."
)

# ============================================================================
# NAV CARDS -- one per dimension, defensive links (decisions log 2026-08-15)
# ============================================================================
# P5 lands before the P1/P2/P4 streams that build the pages below, and those streams
# run in parallel -- their page files appear on disk whenever their own stream merges.
# Rather than hardcode a link to a file that may not exist yet (a broken nav on every
# reload until every other stream lands), the page list per dimension is enumerated
# against the pages/ directory at runtime: a page renders as a link only once its file
# exists; a dimension with NOTHING built yet greys out and reads "en construction"
# instead of silently disappearing. Filenames per BUILD_PLAN.md P1/P2/P3/P4 ownership.
#
# Pass-5 addition (P-A): a SECOND resolution mode, by filename PREFIX rather than exact
# name, for the ONE future filename this stream cannot know in advance -- page 5
# "Positionnement" (R9), built by a sibling stream in this same parallel wave. Guessing
# its exact filename (icon choice, accents) would either be right by luck or leave a
# permanently-stale link once the real file lands under a different name -- exactly the
# "never guess, disclose instead" failure mode this codebase's NOT_EXPRESSIBLE registry
# (lib/links.py) and page 7's own "glob('6_*.py')" cross-link already avoid. A PREFIX
# entry below (`"5_*.py"`) is resolved by globbing the pages/ directory for whatever
# filename actually lands under that numeric slot -- the DISPLAY LABEL is this file's
# own guess (cosmetic only), the HREF is always the real, current filename.

PAGES_DIR = Path(__file__).parent / "pages"
_existing_pages = {p.name for p in PAGES_DIR.glob("*.py")} if PAGES_DIR.is_dir() else set()


def _resolve_page(name_or_prefix_glob: str) -> str | None:
    """
    Exact filename -> returned as-is if it exists. A pattern containing "*"
    -> resolved by globbing pages/ and returning the first real match's own
    filename (or None if nothing has landed yet). Keeps every href pointed at
    a REAL file, never a guessed one, even for a page this stream does not own.
    """
    if "*" in name_or_prefix_glob:
        matches = sorted(PAGES_DIR.glob(name_or_prefix_glob)) if PAGES_DIR.is_dir() else []
        return matches[0].name if matches else None
    return name_or_prefix_glob if name_or_prefix_glob in _existing_pages else None


def _label_from_filename(filename: str) -> str:
    """
    Cosmetic label derived from a REAL filename once a prefix-glob entry
    resolves: strip the numeric slot prefix and ".py", keep the emoji, turn
    underscores into spaces. Close enough to Streamlit's own
    page_icon_and_name() for nav-card text -- this app never routes on the
    result, only _resolve_page()'s real filename does, so a cosmetic mismatch
    here is never a broken link, only a stale-looking label (and this makes
    that impossible once the file exists).
    """
    stem = filename[:-3] if filename.endswith(".py") else filename
    stem = re.sub(r"^[0-9]+[_ -]*", "", stem)
    return stem.replace("_", " ")


DIMENSIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Vue d'ensemble", [
        ("1_📊_Vue_d_ensemble.py", "📊 Vue d'ensemble"),
    ]),
    ("Périmètre et laboratoires", [
        ("2_🏭_Laboratoires.py", "🏭 Laboratoires"),
        ("3_🗂️_Périmètres_personnalisés.py", "🗂️ Périmètres personnalisés"),
        ("7_🎯_I-SITE.py", "🎯 I-SITE"),
    ]),
    ("Partenaires", [
        ("8_🤝_Collaborations.py", "🤝 Collaborations"),
        ("9_🔍_Zoom_partenaire.py", "🔍 Zoom partenaire"),
        ("10_🌍_Géographie.py", "🌍 Géographie"),
    ]),
    ("Thématique", [
        ("4_🔬_Portefeuille_thématique.py", "🔬 Portefeuille thématique"),
        ("6_🔎_Exploration_thématique.py", "🔎 Exploration thématique"),
        ("5_*.py", "Positionnement (à venir)"),  # prefix-resolved; real label derived once it lands
        ("14_🧭_Benchmark.py", "🧭 Benchmark"),
    ]),
    ("Auteurs", [
        ("11_👥_Annuaire_auteurs.py", "👥 Annuaire auteurs"),
        ("12_👤_Profil_auteur.py", "👤 Profil auteur"),
        ("13_🪪_Identifiants_et_couverture.py", "🪪 Identifiants et couverture"),
    ]),
]

cards = st.columns(len(DIMENSIONS), gap="medium")
for card, (dimension_label, dimension_pages) in zip(cards, DIMENSIONS):
    resolved = [(fn, label, _resolve_page(fn)) for fn, label in dimension_pages]
    available = [
        (real, _label_from_filename(real) if "*" in fn else label)
        for fn, label, real in resolved if real
    ]
    pending = [label for fn, label, real in resolved if not real]
    with card:
        with st.container(border=True):
            if not available:
                st.markdown(f":grey[**{dimension_label}**]")
                st.caption(":grey[en construction]")
            else:
                st.markdown(f"**{dimension_label}**")
                for real_filename, label in available:
                    st.page_link(f"pages/{real_filename}", label=label)
                for label in pending:
                    st.caption(f":grey[{label} (en construction)]")

st.markdown("---")

# ============================================================================
# READING JOURNEYS (NARRATIVE_CONTRACT_pass6.md section 3, P6-R2 mode-d'emploi rewrite,
# P16 -- three ordered paths, pasted verbatim). Each step is a sequence of st.page_link
# calls with one FR sentence per step saying what the reader gets there. Every step is
# resolved via _resolve_page() (defensive, same rule as the nav cards above): a step
# whose file has not landed yet is skipped rather than raising. "Animer un défi ou un
# programme" now routes through 📍 Positionnement (backlog #1 / P16), between
# Portefeuille thématique and Exploration thématique.
# ============================================================================
st.markdown("## Trois parcours de lecture")
st.caption("Dans quel ordre ouvrir les vues, selon ce que l'on prépare.")

JourneyStep = tuple[str, str, str]  # (filename_or_glob, label, one FR sentence)

ADVISORY_BOARD_JOURNEY: list[JourneyStep] = [
    ("1_📊_Vue_d_ensemble.py", "📊 Vue d'ensemble",
     "Voir ce que le corpus couvre et ce qu'il retient, avant d'entrer dans le détail."),
    ("2_🏭_Laboratoires.py", "🏭 Laboratoires",
     "Situer chaque structure interne sur son volume, ses partenaires et son profil de citation."),
    ("7_🎯_I-SITE.py", "🎯 I-SITE",
     "Mesurer ce que le périmètre I-SITE amplifie par rapport au reste du site."),
    ("8_🤝_Collaborations.py", "🤝 Collaborations",
     "Revoir les partenariats les plus actifs et leur dynamique récente."),
    ("14_🧭_Benchmark.py", "🧭 Benchmark",
     "Situer l'établissement face à un jeu resserré de pairs, sans en tirer un classement."),
]

CHALLENGE_JOURNEY: list[JourneyStep] = [
    ("1_📊_Vue_d_ensemble.py", "📊 Vue d'ensemble",
     "Prendre la mesure du corpus complet avant de resserrer sur un axe thématique."),
    ("4_🔬_Portefeuille_thématique.py", "🔬 Portefeuille thématique",
     "Repérer les champs qui portent le plus de volume, et leur poids I-SITE."),
    ("5_📍_Positionnement.py", "📍 Positionnement",
     "Vérifier si l'axe repéré est un terrain frontière ou établi, et comment il se situe face à la France et aux pairs."),
    ("6_🔎_Exploration_thématique.py", "🔎 Exploration thématique",
     "Descendre jusqu'au topic, et voir qui contribue : structures, partenaires, auteur·es."),
    ("3_🗂️_Périmètres_personnalisés.py", "🗂️ Périmètres personnalisés",
     "Vérifier quels périmètres sont déjà gouvernés dans l'outil, et lesquels restent à construire."),
]

PARTNER_JOURNEY: list[JourneyStep] = [
    ("8_🤝_Collaborations.py", "🤝 Collaborations",
     "Repérer le partenaire parmi les relations actives, et voir sa dynamique récente."),
    ("9_🔍_Zoom_partenaire.py", "🔍 Zoom partenaire",
     "Ouvrir la fiche : champs partagés, laboratoires porteurs, réciprocité, publications."),
    ("10_🌍_Géographie.py", "🌍 Géographie",
     "Replacer la relation dans son pays et, le cas échéant, dans une alliance."),
    ("2_🏭_Laboratoires.py", "🏭 Laboratoires",
     "Revenir côté site : quelle structure porte cette relation, et quoi d'autre."),
]


def _render_journey(title: str, intro: str, steps: list[JourneyStep], honest_note: str | None = None) -> None:
    with st.container(border=True):
        st.markdown(f"### {title}")
        st.markdown(intro)
        for i, (filename, label, sentence) in enumerate(steps, start=1):
            real = _resolve_page(filename)
            if not real:
                continue
            st.page_link(f"pages/{real}", label=f"{i}. {label}")
            st.caption(sentence)
        if honest_note:
            st.warning(honest_note)


col_advisory, col_challenge, col_partner = st.columns(3, gap="large")
with col_advisory:
    _render_journey(
        "Préparer un comité (Advisory Board, comité de suivi)",
        "Arriver au comité avec les mêmes repères : ce que couvre le corpus, comment il "
        "se répartit en interne, ce que le programme I-SITE y ajoute, avec qui "
        "l'établissement collabore, et où il se situe face à un jeu de pairs choisi.",
        ADVISORY_BOARD_JOURNEY,
    )
with col_challenge:
    _render_journey(
        "Animer un défi ou un programme",
        "Préparer une réunion de défi ou de programme scientifique : cerner un axe "
        "thématique, vérifier comment il se situe, et voir quels périmètres l'outil sait "
        "déjà restituer.",
        CHALLENGE_JOURNEY,
        honest_note=(
            "Usage encore partiel : l'outil ne porte pas de corpus propre à chaque défi "
            "ou à chaque programme. Ces corpus dépendent de listes que l'établissement "
            "doit fournir, suivies sur la page Périmètres personnalisés une fois "
            "gouvernées. En attendant, l'animation par défi s'appuie sur le portefeuille "
            "thématique et l'exploration par topic, jamais sur un périmètre dédié."
        ),
    )
with col_partner:
    _render_journey(
        "Instruire une relation partenaire",
        "Préparer un renouvellement d'accord ou une visite : ce qui lie l'établissement "
        "à un partenaire, ce que la relation pèse de chaque côté, et qui la porte en "
        "interne.",
        PARTNER_JOURNEY,
    )

st.markdown("---")

# ============================================================================
# MÉTHODES ET GUIDE DE LECTURE (BUILD_PLAN.md P1, NARRATIVE_CONTRACT_pass6.md section
# 4.2) -- the long méthodo copy, single-sourced in lib.helpers and rendered here AND as
# the short sidebar expander (lib.controls.sidebar(), every content page). The object
# registry link line is S-REG's own copy (progress/SREG.md), pasted here since
# REGISTRE_OBJETS.md is a plain repo doc, not a Streamlit page -- it cannot be a
# st.page_link target, so its own internal file path is not repeated on this
# client-facing screen (docs/NARRATIVE_CONTRACT_pass6.md section 1, motif "Fichiers et
# chemins": the reader of this page does not have the repository open in front of them).
# ============================================================================
render_methodo_menu_section()
st.markdown(
    "**Registre des objets.** Un tableau par objet (pays, laboratoire, structure "
    "interne, partenaire, auteur·e, thématique, ODD, type de document, drapeaux ISITE, "
    "période, établissement pair) : définition, unités, source, langue d'affichage, "
    "vues et indicateurs consommateurs, objets liés, pièges. Document tenu à part de "
    "l'application, remis avec elle."
)

st.markdown("---")

# Snapshot/method footer (VIZ_SPEC 1.5/2.0): snapshot badge lives in the sidebar (shared
# control-layer convention, every page); the method line stays in the body, as before.
snapshot_badge()

# R12: lib.app_config.SDG_VARIANTS (FROZEN this pass) hard-codes its human label in
# English ("SIRIS method"/"OpenAlex / Aurora") -- a display-only FR translation here,
# never re-deriving the underlying value, so this page's presentational text stays
# French without editing the frozen lib module (documented workaround, not a fix).
_SDG_LABEL_FR = {"SIRIS method": "méthode SIRIS"}
_sdg_label_fr = _SDG_LABEL_FR.get(sdg_label(), sdg_label())

# NARRATIVE_CONTRACT_pass6.md section 2.1 (G1 window literal + config-key jargon): the
# fenêtre is now computed (window_label()) and the configuration key name no longer
# appears on screen -- it lives in the "Méthodes et guide de lecture" section above.
_odd_bit = (
    f"Attribution des ODD : **{_sdg_label_fr}**." if sdg_variant() != "off"
    else "Panneau ODD non activé."
)
st.caption(
    f"Publications de l'Université de Lorraine, {window_label()}, reconstruites depuis "
    "OpenAlex. Les axes thématiques suivent la taxonomie OpenAlex (domaine, champ, "
    f"sous-champ, topic). {_odd_bit}"
)
