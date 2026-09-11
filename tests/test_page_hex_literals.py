# tests/test_page_hex_literals.py
"""
Cliquet mecanique pour la decision B6 de la passe 7b (« jetons de couleur seulement,
zero hexadecimal dans une page »). Reference : BUILD_PLAN.md (pass 7b) B6/B12, P5 de
la passe 7a. Mecanisme de port : tests/test_hover_tripwire.py, dont ce fichier IMPORTE
`_strip_comments_and_docstrings` plutot que de le recopier (une seule implementation
du blanchiment commentaires/docstrings dans le depot).

POURQUOI
  Une couleur ecrite en clair dans une page est une identite qui echappe au systeme :
  elle ne suit pas le theme, elle ne change pas quand le jeton change, et deux pages
  finissent par dire deux bleus differents pour la meme chose. Les jetons vivent dans
  `Streamlit/lib/helpers.py` (`UL_COLOR`, `PARTNER_COLOR`, `JOINT_COLOR`, `NEUTRAL_GREY`,
  `REFERENCE_RED`, `MOMENTUM_*`, `SDG_COLORS`/`sdg_color`, `tint`) : une page les lit,
  elle n'en invente pas.

CE QUE CE TEST VERIFIE
  Aucun litteral `#RRGGBB` dans `Streamlit/pages/*.py` ni dans `Streamlit/Menu.py`,
  commentaires et docstrings retires (un hexadecimal cite dans un commentaire de
  justification n'est pas une couleur dessinee).

PORTEE ET LIMITES (assumees)
  * Les fichiers de `Streamlit/lib/` sont HORS PORTEE : c'est la qu'un jeton doit
    porter sa valeur, et l'y interdire n'aurait pas de sens.
  * Une chaine `rgba(...)` n'est pas un hexadecimal et n'est pas attrapee : elle sert
    aux marques transparentes (trace d'ancrage, halo) qu'aucun jeton ne porte.
  * La forme courte `#RGB` n'est pas attrapee : elle n'apparait pas dans ce depot, et
    l'attraper ferait matcher des ancres et des titres markdown.
  * Comme tout scan textuel, une couleur assemblee dynamiquement echappe au test --
    c'est la relecture du contrat qui couvre ce cas.

MECANIQUE DE CLIQUET (identique a test_hover_tripwire.py / test_narrative.py)
  `EXEMPT_PAGES` est seede AUJOURD'HUI (2026-09-11) en LANCANT le scanner ci-dessous
  sur l'etat du depot au debut de la passe 7b : chaque entree viole reellement. Chaque
  stream de page retire SA ligne quand sa page est passee aux jetons -- en pratique le
  MANAGER la retire au commit (B12 : neuf streams qui editent le meme fichier de test
  sont une collision d'ecriture), sur preuve du stream (« scanner a zero sur ma page »).
  La liste ne se remplit jamais : `test_ratchet_names_only_existing_files` interdit une
  entree fantome et `test_exempt_entries_still_violate` interdit une entree deja propre
  gardee « par prudence ».

    .venv-pinned\\Scripts\\python -m pytest tests\\test_page_hex_literals.py -q
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Une seule implementation du blanchiment commentaires/docstrings dans le depot.
from tests.test_hover_tripwire import _strip_comments_and_docstrings

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"

# `#RRGGBB` : six chiffres hexadecimaux apres le croisillon. `rgba(0,0,0,0)` n'a pas
# de croisillon et ne peut donc pas matcher ; `### Titre` non plus (espace, pas hex).
HEX_RX = re.compile(r"#[0-9A-Fa-f]{6}")


def hex_violations(source: str) -> list[str]:
    """Point d'entree unique -- utilise par le scan reel ET par les preuves de
    vacuite, pour qu'aucune des deux ne puisse diverger de l'autre."""
    stripped = _strip_comments_and_docstrings(source)
    hits: list[str] = []
    for lineno, line in enumerate(stripped.splitlines(), start=1):
        for match in HEX_RX.finditer(line):
            hits.append(f"L{lineno} : {match.group(0)} -- {line.strip()[:100]!r}")
    return hits


def _scanned_files() -> list[Path]:
    """Les pages et le menu : la surface que l'utilisateur voit. `lib/` est hors
    portee (c'est la que les jetons portent leur valeur)."""
    pages = [p for p in (STREAMLIT_DIR / "pages").glob("*.py")
             if "__pycache__" not in p.parts]
    menu = STREAMLIT_DIR / "Menu.py"
    return sorted(pages + ([menu] if menu.exists() else []))


def _relkey(path: Path) -> str:
    return path.relative_to(STREAMLIT_DIR).as_posix()


def _path_for(relkey: str) -> Path:
    return STREAMLIT_DIR / relkey


# ---------------------------------------------------------------------------
# CLIQUET -- seede 2026-09-11 en lancant `hex_violations` sur l'etat du depot au
# debut de la passe 7b (avant toute page migree). Les pages absentes de cette
# liste sont DEJA propres et le restent : y reintroduire un hexadecimal fait
# echouer le test nomme au fichier. Retirez votre ligne (manager, B12) dans le
# commit qui migre la page.
# ---------------------------------------------------------------------------
# Scan du 2026-09-11, 01h35 : 89 infractions vivantes sur 12 fichiers ; Menu.py et
# les pages 3 et 11 etaient deja propres. Re-scan a 01h52 : les pages 9 et 10 sont
# sorties de la liste PENDANT cette vague -- P-Z9 les a corrigees en parallele (page 9
# une couleur de texte dans un style HTML en ligne, page 10 les cinq couleurs de la
# carte) -- et leurs deux entrees ont donc ete retirees ici, dans le meme mouvement.
# Reste UNE entree hors perimetre de la passe 7b, qu'aucun stream de page ne peut
# retirer : pages/8 (5) -- `MOM_COLORS` L187 (quatre encres de momentum -> `MOMENTUM_*`)
# et la mediane pointillee L926 (-> `NEUTRAL_GREY` ou `REFERENCE_RED`). Vider ce cliquet
# a la cloture demande donc une decision du manager sur ces cinq litteraux.
EXEMPT_PAGES: set[str] = set()   # EMPTIED by pass 7b (2026-09-11): every page carries the contract

ACTIVE = [p for p in _scanned_files() if _relkey(p) not in EXEMPT_PAGES]


@pytest.mark.parametrize("path", ACTIVE, ids=lambda p: _relkey(p))
def test_no_hex_literal_in_page(path: Path) -> None:
    offenders = hex_violations(path.read_text(encoding="utf-8"))
    assert not offenders, (
        f"{_relkey(path)} : couleur ecrite en clair -- utilisez un jeton de "
        f"`lib/helpers.py` (BUILD_PLAN pass 7b, B6)\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize("relkey", sorted(EXEMPT_PAGES))
def test_exempt_entries_still_violate(relkey: str) -> None:
    """Le cliquet ne se remplit jamais : une entree qui ne viole plus DOIT sortir
    de EXEMPT_PAGES dans le meme commit que la correction."""
    path = _path_for(relkey)
    assert path.exists(), f"EXEMPT_PAGES nomme un fichier absent : {relkey}"
    offenders = hex_violations(path.read_text(encoding="utf-8"))
    assert offenders, (
        f"{relkey} ne viole plus rien -- retirez-le de EXEMPT_PAGES "
        f"(tests/test_page_hex_literals.py) dans le commit qui l'a corrige"
    )


def test_ratchet_names_only_existing_files() -> None:
    on_disk = {_relkey(p) for p in _scanned_files()}
    unknown = EXEMPT_PAGES - on_disk
    assert not unknown, f"EXEMPT_PAGES nomme des fichiers absents : {sorted(unknown)}"


def test_scan_surface_is_not_vacuous() -> None:
    """Si la surface scannee se vidait (renommage de dossier, glob casse), tous les
    controles passeraient a vide : on epingle donc la surface elle-meme."""
    files = {_relkey(p) for p in _scanned_files()}
    assert len(files) >= 14, sorted(files)
    assert "Menu.py" in files, sorted(files)


# ---------------------------------------------------------------------------
# VACUITE (P14) -- extraits en memoire : chaque regle est prouvee capable
# d'echouer, et chaque exemption prouvee capable de NE PAS echouer.
# ---------------------------------------------------------------------------
def test_vacuity_live_hex_literal_is_flagged() -> None:
    src = 'fig.add_trace(go.Bar(x=[1], marker_color="#0072B2"))\n'
    assert hex_violations(src), "une couleur ecrite en clair doit etre signalee"


def test_vacuity_hex_inside_comment_or_docstring_is_not_flagged() -> None:
    src_comment = '# l ancien jaune #F4D570 du point median a ete retire (dataviz)\nx = 1\n'
    src_docstring = (
        'def f():\n'
        '    """Le bleu focal valait #0072B2 avant les jetons -- ne pas reintroduire."""\n'
        '    return 1\n'
    )
    assert not hex_violations(src_comment), "un commentaire ne doit jamais etre signale"
    assert not hex_violations(src_docstring), "une docstring ne doit jamais etre signalee"


def test_vacuity_rgba_string_is_not_flagged() -> None:
    src = 'marker=dict(color="rgba(0,0,0,0)", line=dict(color="rgba(140,145,150,0.15)"))\n'
    assert not hex_violations(src), "une chaine rgba(...) n est pas un hexadecimal"


def test_vacuity_token_reference_is_not_flagged() -> None:
    src = 'marker_color=H.UL_COLOR\nline_color=H.REFERENCE_RED\n'
    assert not hex_violations(src), "un jeton ne doit jamais etre signale"


def test_vacuity_markdown_heading_is_not_flagged() -> None:
    src = 'st.markdown("#### Spécialisation par champ vs France")\n'
    assert not hex_violations(src), "un titre markdown ne doit jamais etre signale"


def test_vacuity_exempt_check_can_fail() -> None:
    """Controle inverse de `test_exempt_entries_still_violate` : sur une source
    reellement propre, l assertion « il viole encore » est bien fausse."""
    assert not hex_violations('marker_color=H.UL_COLOR\n')


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
