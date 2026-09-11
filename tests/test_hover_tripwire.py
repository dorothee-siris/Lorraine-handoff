# tests/test_hover_tripwire.py
"""
Tripwire mecanique pour la regle P0.1 de VIZ_SPEC_pass6.md (« pre-format, jamais de
format dans le gabarit ») et sa consequence Streamlit (`format="percent"` est
locale-dependant). Reference : BUILD_PLAN.md P14(4), P2 (tooltip contract FR).
Mecanisme de port : docs/reference/benchup_2026-09-04/tests/test_locale_format_ban.py
(comments/docstrings stripped via tokenize+ast avant tout scan textuel).

CE QUE CE TEST VERIFIE (walk recursif de `Streamlit/**/*.py`, hors __pycache__)
  (a)/(c) un `hovertemplate` (ou toute constante qui en tient lieu, ex.
          `lib/hover.py: HOVERTEMPLATE = "..."`) contenant un format-spec Plotly
          `%{...:...}` -- `%{customdata[0]:,}`, `%{y:.2f}`, `%{x:.1%}` -- est LOCALE-
          BLIND (virgule/point anglais dans une UI FR). Regle app-wide : le nombre est
          pre-formate dans `customdata` et le gabarit reste `%{customdata[i]}` NU.
  (b) `format="percent"` / `format='percent'` a l'interieur d'un appel
      `st.column_config.*` (meme piege : rendu sous la locale active).

PORTEE ET LIMITES (assumees, memes limites que test_narrative.py) : seules les
CHAINES LITTERALES sont visibles ; un gabarit assemble dynamiquement par
concatenation de variables echappe au scan textuel comme a tout linter statique --
c'est la relecture humaine du contrat qui couvre ce cas.

MECANIQUE DE CLIQUET (identique a test_narrative.py)
  `EXEMPT_PAGES` est seede AUJOURD'HUI (2026-09-10, avant toute page de la passe 7a)
  avec CHAQUE fichier qui viole reellement -- pages 1-14 + Menu.py non encore migres,
  et tout fichier lib/ trouve en infraction. Chaque stream de page (P-COL, P-ZOOM,
  P-EX, P-GEO, S-SDG en W3) retire SA ligne quand sa page passe au contrat `lib/hover.py`
  (P2/P14). La 7b vide le reste (P7-R9, sequence des passes). La liste ne se remplit
  jamais : un test dedie (`test_ratchet_names_only_existing_files`) verifie qu'aucune
  entree ne nomme un fichier absent, et `test_exempt_entries_still_violate` verifie que
  toute entree encore presente viole ENCORE -- un fichier reellement corrige doit sortir
  de la liste dans le MEME commit, jamais y rester "par prudence".

    python -m pytest tests/test_hover_tripwire.py -q
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"

# Format-spec Plotly a l'interieur d'un placeholder `%{...}` : `%{customdata[0]:,}`,
# `%{y:.2f}`, `%{x:.1%}` matchent tous ; `%{customdata}` (nu, la forme exigee) ne
# matche pas -- il n'y a pas de ":" avant la fermeture.
HOVER_FORMAT_RX = re.compile(r"%\{[^}]*:[^}]*\}")


# ---------------------------------------------------------------------------
# Port de BenchUp test_locale_format_ban._strip_comments_and_docstrings :
# blanchit (sans jamais decaler les numeros de ligne) chaque COMMENTAIRE et
# chaque instruction docstring de module/classe/fonction, en laissant intact
# tout le reste -- y compris un hovertemplate= reellement en infraction.
# ---------------------------------------------------------------------------
def _strip_comments_and_docstrings(source: str) -> str:
    lines = source.splitlines(keepends=True)

    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                row = tok.start[0] - 1
                c0, c1 = tok.start[1], tok.end[1]
                line = lines[row]
                lines[row] = line[:c0] + (" " * (c1 - c0)) + line[c1:]
    except (tokenize.TokenizeError, SyntaxError, IndentationError):
        pass

    source_no_comments = "".join(lines)

    try:
        tree = ast.parse(source_no_comments)
    except SyntaxError:
        return source_no_comments

    docstring_lines: set[int] = set()

    def _mark(node) -> None:
        body = getattr(node, "body", None)
        if not body:
            return
        first = body[0]
        if (isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            start = first.lineno - 1
            end = getattr(first, "end_lineno", first.lineno) - 1
            for ln in range(start, end + 1):
                docstring_lines.add(ln)

    _mark(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _mark(node)

    lines2 = source_no_comments.splitlines(keepends=True)
    for ln in docstring_lines:
        if ln < len(lines2):
            lines2[ln] = "\n" if lines2[ln].endswith("\n") else ""
    return "".join(lines2)


def _dotted_name(node: ast.AST) -> str:
    """Nom pointe d'un appel (`st.column_config.ProgressColumn` -> la chaine
    elle-meme) ; chaine vide si la forme n'est pas un attribut/nom simple."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _column_config_percent_violations(source: str) -> list[str]:
    """(b) -- AST pur : un appel dont le nom pointe contient "column_config" et
    qui porte un mot-cle `format="percent"`. Les commentaires/docstrings ne
    peuvent jamais matcher un Call reel, donc pas besoin de la source
    blanchie ici (contrairement au scan textuel de (a)/(c))."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted = _dotted_name(node.func)
        if "column_config" not in dotted:
            continue
        for kw in node.keywords:
            if (kw.arg == "format" and isinstance(kw.value, ast.Constant)
                    and kw.value.value == "percent"):
                hits.append(f"L{node.lineno} : {dotted}(..., format=\"percent\")")
    return hits


def _hovertemplate_format_violations(source: str) -> list[str]:
    """(a)/(c) -- scan textuel de la source COMMENTAIRES/DOCSTRINGS RETIRES :
    attrape aussi bien un `hovertemplate=` direct qu'une constante qui en
    tient lieu (`lib/hover.py: HOVERTEMPLATE = "%{...:...}"`), exactement le
    meme besoin que BenchUp `PROGRESS_FORMAT`-style constant."""
    stripped = _strip_comments_and_docstrings(source)
    hits = []
    for lineno, line in enumerate(stripped.splitlines(), start=1):
        m = HOVER_FORMAT_RX.search(line)
        if m:
            hits.append(f"L{lineno} : {line.strip()[:110]!r}")
    return hits


def scan_source_for_violations(source: str) -> list[str]:
    """Point d'entree unique -- (a)/(b)/(c) reunis, utilise par le scan reel
    et par les preuves de vacuite ci-dessous."""
    return _hovertemplate_format_violations(source) + _column_config_percent_violations(source)


def _all_streamlit_py_files() -> list[Path]:
    return sorted(p for p in STREAMLIT_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def _relkey(path: Path) -> str:
    return path.relative_to(STREAMLIT_DIR).as_posix()


def _path_for(relkey: str) -> Path:
    return STREAMLIT_DIR / relkey


# ---------------------------------------------------------------------------
# CLIQUET -- seede 2026-09-10 en lancant reellement le scanner ci-dessus sur
# l'etat du jour (avant toute page de la passe 7a ; S-LIB-B/S-TT n'ont pas
# encore livre `lib/hover.py`, donc aucune page ne peut encore utiliser le
# gabarit pre-formate). Verifie : Menu.py, lib/*.py (12 fichiers) et les
# pages 1,3,8,9,10-14 sont DEJA propres (pages 1/8 corrigees passe 6, cf.
# VIZ_SPEC_pass6.md §0.1) -- seules 5 pages violent encore. Retirez votre
# ligne des que votre page/lib est migree vers lib/hover.py.
# ---------------------------------------------------------------------------
# S-SDG (pass 7a, W2): pages/2 removed 2026-09-10 -- its only violation was the
# lab_sdg_bars hovertemplate (`%{x:.1f}`), now customdata + HOVERTEMPLATE; the scanner
# itself confirms zero remaining offenders on this page. pages/4 STAYS: the SDG bar +
# peers-scatter sites are fixed, but the page's many OTHER charts (treemap, boxplots,
# zero-fill tables, specialisation view) are untouched this pass -- 7b's job.
EXEMPT_PAGES: set[str] = {
    "pages/6_🔎_Exploration_thématique.py",
    "pages/7_🎯_I-SITE.py",
}

ACTIVE = [p for p in _all_streamlit_py_files() if _relkey(p) not in EXEMPT_PAGES]


@pytest.mark.parametrize("path", ACTIVE, ids=lambda p: _relkey(p))
def test_no_hover_format_spec_or_percent_column_config(path: Path) -> None:
    offenders = scan_source_for_violations(path.read_text(encoding="utf-8"))
    assert not offenders, (
        f"{_relkey(path)} : gabarit de survol locale-dependant ou format=\"percent\" "
        f"(VIZ_SPEC_pass6.md §0.1, BUILD_PLAN.md P2/P14)\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize("relkey", sorted(EXEMPT_PAGES))
def test_exempt_entries_still_violate(relkey: str) -> None:
    """Le cliquet ne se remplit jamais : une entree qui ne viole plus DOIT
    sortir de EXEMPT_PAGES dans le meme commit que la correction."""
    path = _path_for(relkey)
    assert path.exists(), f"EXEMPT_PAGES nomme un fichier absent : {relkey}"
    offenders = scan_source_for_violations(path.read_text(encoding="utf-8"))
    assert offenders, (
        f"{relkey} ne viole plus rien -- retirez-le de EXEMPT_PAGES (tests/test_hover_tripwire.py) "
        f"dans le commit qui l'a corrige"
    )


def test_ratchet_names_only_existing_files() -> None:
    on_disk = {_relkey(p) for p in _all_streamlit_py_files()}
    unknown = EXEMPT_PAGES - on_disk
    assert not unknown, f"EXEMPT_PAGES nomme des fichiers absents : {sorted(unknown)}"


# ---------------------------------------------------------------------------
# VACUITE (P14) -- trois extraits en memoire, avant tout scan reel : une
# violation vivante doit etre signalee, la MEME chaine a l'interieur d'un
# commentaire/docstring ne doit JAMAIS l'etre, un gabarit propre ne doit
# jamais l'etre non plus.
# ---------------------------------------------------------------------------
def test_vacuity_live_hovertemplate_format_is_flagged() -> None:
    src = (
        'fig.update_traces(\n'
        '    hovertemplate="<b>%{customdata[0]}</b> : %{customdata[1]:,}<extra></extra>"\n'
        ')\n'
    )
    assert scan_source_for_violations(src), "un format-spec vivant doit etre signale"


def test_vacuity_same_text_inside_comment_or_docstring_is_not_flagged() -> None:
    src_comment = (
        '# jamais "hovertemplate=\'%{y:.2f}<extra></extra>\'" -- locale-dependant, interdit\n'
        'x = 1\n'
    )
    src_docstring = (
        'def f():\n'
        '    """Ancien defaut : %{customdata[0]:,} -- corrige depuis, ne pas reintroduire."""\n'
        '    return 1\n'
    )
    assert not scan_source_for_violations(src_comment), "un commentaire ne doit jamais etre signale"
    assert not scan_source_for_violations(src_docstring), "une docstring ne doit jamais etre signalee"


def test_vacuity_clean_template_is_not_flagged() -> None:
    src = 'HOVERTEMPLATE = "%{customdata}<extra></extra>"\nfig.update_traces(hovertemplate=HOVERTEMPLATE)\n'
    assert not scan_source_for_violations(src), "le gabarit nu (sans format-spec) ne doit jamais etre signale"


def test_vacuity_live_column_config_percent_is_flagged() -> None:
    src = 'st.column_config.ProgressColumn("Score", format="percent")\n'
    assert scan_source_for_violations(src), "format=\"percent\" dans column_config doit etre signale"


def test_vacuity_column_config_without_percent_is_not_flagged() -> None:
    src = 'st.column_config.ProgressColumn("Score", format="%.1f%%")\n'
    assert not scan_source_for_violations(src), "un format explicite non-\"percent\" ne doit pas etre signale"


def test_vacuity_column_config_percent_string_outside_a_call_is_not_flagged() -> None:
    """Le mot "percent" seul (hors appel column_config) ne doit jamais matcher --
    seule la FORME `st.column_config.*(..., format="percent")` compte."""
    src = 'mode = "percent"\nst.caption(f"affichage en {mode}")\n'
    assert not scan_source_for_violations(src), "\"percent\" hors column_config ne doit pas etre signale"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
