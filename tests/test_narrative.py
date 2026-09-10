# tests/test_narrative.py
"""
Garde-fou mecanique du contrat narratif (BUILD_PLAN.md P10, ruling P6-R2 du
2026-08-19). Contrat de reference, avec la copie FR de remplacement page par page :
docs/NARRATIVE_CONTRACT_pass6.md. Vocabulaire interdit :
docs/contract_fragments/narrative_banlist.txt.

CE QUE CE TEST VERIFIE
  1. ban-list  : aucune chaine affichee ne contient un terme de construction interne
                 (nom de fichier/table/colonne, reference de decision D../R.., nom de
                 panneau, jargon anglais de chantier, litteral de fenetre ou
                 d'instantane).
  2. chiffres  : aucun CHIFFRE LITTERAL dans une chaine statique affichee, sauf
                 liste blanche (seuils de methode, « top 10 », renvois de section,
                 codes techniques). Une f-string dont la valeur est calculee au rendu
                 est LEGALE : c'est precisement la regle P6-R2 (b).
  3. annees    : aucune ANNEE LITTERALE (19xx / 20xx) dans une chaine statique
                 affichee, sauf entree explicite de `YEAR_ALLOWLIST`. Une fenetre
                 ecrite a la main (« 2019-2023 ») devient FAUSSE des que le client
                 relance la chaine sur une annee de plus ; seuls les faits historiques
                 (date de labellisation, date d'un atelier, annee d'une fusion) sont
                 legaux, et ils s'allowlistent un par un, avec leur justification.
                 Releve exhaustif des sites concernes, fichier par fichier et ligne par
                 ligne : docs/YEAR_UPDATE_DESIGN.md section 5 (stream S-YR).

PORTEE (et ses limites, assumees)
  Seules sont scannees les chaines passees a un appel d'affichage Streamlit, y compris
  les parties litterales d'une f-string : `st.markdown(...)`, `st.caption(...)`, et
  la meme methode appelee sur un conteneur (`c1.metric(...)`, `col.caption(...)`).
  Ne sont PAS scannes : le code hors affichage (`pd.read_parquet("x.parquet")`), les
  gabarits de survol Plotly (`hovertemplate=`), les titres d'axes (`update_xaxes`),
  les cles de widget (`key=`) et les specificateurs de format (`format=`). Ces
  surfaces restent couvertes par la relecture humaine du contrat, section 2.
  Les nombres ECRITS EN TOUTES LETTRES (« huit signataires », « neuf pairs ») ne sont
  pas detectables ici : le contrat les inventorie a la main, page par page.

MECANIQUE DE CLIQUET (le point important pour les streams de page)
  `EXEMPT_PAGES` part avec TOUTES les pages + Menu.py : le test passe des aujourd'hui,
  la suite reste verte. Chaque stream de page, quand il a colle sa copie de
  remplacement et fait disparaitre ses violations, SUPPRIME sa ligne de `EXEMPT_PAGES`
  dans le meme commit. La liste ne se remplit jamais : elle ne fait que se vider.
  Une page sortie de la liste ne peut plus y revenir sans une entree au journal des
  decisions du BUILD_PLAN.

    python -m pytest tests/test_narrative.py -q
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = ROOT / "Streamlit" / "pages"
MENU_FILE = ROOT / "Streamlit" / "Menu.py"
BANLIST_FILE = ROOT / "docs" / "contract_fragments" / "narrative_banlist.txt"

# ---------------------------------------------------------------------------
# CLIQUET : une ligne par surface encore non conforme. Retirez la votre quand
# votre page est passee au contrat (docs/NARRATIVE_CONTRACT_pass6.md section 5).
# ---------------------------------------------------------------------------
EXEMPT_PAGES: set[str] = set()

# Methodes Streamlit qui rendent du texte a l'ecran. Le receveur est ignore :
# `st.caption(...)` et `col.caption(...)` sont la meme surface.
DISPLAY_CALLS = frozenset({
    "title", "header", "subheader", "caption", "markdown", "write", "text",
    "info", "warning", "error", "success", "metric", "page_link", "expander",
    "toast", "radio", "selectbox", "multiselect", "checkbox", "toggle", "slider",
    "text_input", "number_input", "text_area", "button", "download_button",
    "file_uploader", "dataframe", "tabs", "link_button", "badge", "pills",
    "segmented_control", "TextColumn", "NumberColumn", "ProgressColumn",
    "LinkColumn", "CheckboxColumn", "LineChartColumn", "Column",
})

# Arguments dont la valeur n'est jamais lue par un humain.
SKIPPED_KWARGS = frozenset({"key", "format", "column_order", "type", "icon"})

# Chiffres legaux : chaque motif « consomme » ses propres chiffres ; si, une fois
# tous les motifs retires, il reste un chiffre, la chaine est en infraction.
DIGIT_ALLOWLIST = [
    # Les annees sont consommees ICI pour ne pas etre signalees deux fois : elles ont
    # leur propre regle, plus stricte, juste en dessous (YEAR_RX / YEAR_ALLOWLIST).
    r"\b(?:19|20)\d{2}\b",
    r"[≥≤<>±~]\s*\d+(?:[,.]\d+)?",                       # seuils : ≥10, n<30, ±3
    r"\bn\s*[=]\s*\d+",                                  # n=3
    r"\btop[\s\-–]*\d{1,3}\b",                           # top 10, Top-3
    r"\b\d{1,3}\s*(?:premiers?|premières?|premieres?)\b",  # 3 premiers champs
    r"(?:§|section|partie|point|étape|niveau)\s*\d+(?:[.\-]\d+)*",  # renvois
    r"\b\d{1,2}\s*(?:er|ère|ere|e|ème|eme)\b",           # ordinaux
    r"\b\d{4}-\d{4}-\d{4}-\d{3}[0-9X]\b",                # ORCID
    r"\b[A-Z]{1,3}\d{4,}\b",                             # identifiants techniques
    r"\bANR-\d{2}-[A-Z]+-\d{2,4}\b",                     # codes ANR
    # Constantes de methode enumerees (config.yaml / note de methode) :
    r"\b30\s*(?:travaux|co-publications|publications)\b",   # plancher de fiabilite
    r"\b3\s*(?:travaux|co-publications)\b",                 # plancher de cellule
    r"\b5\s*(?:types|années|annees|travaux)\b",             # types de doc, sparkline
    r"\bmoins de\s*\d{1,2}\s",                              # « moins de 30 travaux »
    # Dates d'evenements (faits de calendrier, pas des valeurs de donnees) : « 5 et 6 octobre »
    r"\b\d{1,2}(?:\s+et\s+\d{1,2})?\s+(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\b",
    r"\b0,40\b",                                            # seuil Aurora
    r"\b16\s*passes\b",                                     # vocabulaire ODD
    r"\b(?:ODD|SDG)\s*1?\d\b",                              # ODD 7, ODD 17
    r"\bTop\s*1?\d\s*%",                                    # Top 10 %, Top 1 %
    r"\b1?\d\s*%\s*(?:les plus|le plus)\b",                 # « 10 % les plus citées »
    r"France\s*[=≈]\s*\d+(?:\s*%)?",                        # repere France = 1
    r"\b95\s*%",                                            # plancher de couverture
    r"\b100\s*%",                                           # borne d'une part
    r"jamais\s*(?:à\s*|a\s*)?0(?:\s*%)?",                    # « NULL, jamais 0 »
    r"never\s*0",
    r"\bp\d{1,3}\b",                                        # centiles p0, p25, p90
    r"\bc\d\b",                                             # fenêtres c1+c2
    r"percentiles?\s*\d{1,3}\s*[-–]\s*\d{1,3}",              # percentiles 10-90
    r"\bPPtop\s*1?\d\b",                                    # nom d'indicateur
    r"\bISO[-\s]?\d\b",                                     # ISO-3, ISO-2
    r"\bPIA\s?\d\b",                                        # PIA2 (fait historique)
    r"\b\d[AB]\s*/\s*\d[AB]\b",                             # notation de jury 6A/3B
    r"\b2\s*(?:fenêtres|fenetres|périodes|periodes)\b",      # momentum deux périodes
    r"(?:point neutre|parité|parite|référence|reference)\s*[=≈]\s*\d+",
    r"\b0000-\d{4}[-.\d]*",                                  # exemple d'ORCID
]
_ALLOW_RX = [re.compile(p, re.IGNORECASE) for p in DIGIT_ALLOWLIST]

# ---------------------------------------------------------------------------
# REGLE ANNEE (S-YR, docs/YEAR_UPDATE_DESIGN.md section 5)
# Une annee ecrite a la main dans un titre, une legende ou un titre d'axe devient
# fausse a la premiere mise a jour de donnees. Elle n'est legale que si elle enonce
# un FAIT DU MONDE (labellisation, atelier, fusion d'etablissement), jamais un fait
# de la donnee (fenetre de publication, date d'instantane, date de tirage).
# Pour allowlister : ajouter au fichier concerne un fragment de texte SUFFISAMMENT
# SPECIFIQUE pour ne couvrir que cette phrase, avec le fait historique en commentaire.
# ---------------------------------------------------------------------------
YEAR_RX = re.compile(r"\b(?:19|20)\d{2}\b")

YEAR_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "7_🎯_I-SITE.py": (
        "Labellisée I-SITE en janvier",   # date de labellisation (PIA2)
        "période de probation jusqu'en",  # date de pérennisation
        "atelier des 5 et 6 octobre",     # date de l'atelier de co-design
    ),
    "4_🔬_Portefeuille_thématique.py": (
        "arrêté (atelier,",               # date de l'atelier ayant arrêté le jeu de pairs
    ),
    "5_📍_Positionnement.py": (
        "arrêtés en atelier le",          # même décision d'atelier
    ),
    "10_🌍_Géographie.py": (
        "fusion Kaiserslautern + Landau",  # année de la fusion RPTU
    ),
}


def year_literals_in(filename: str, text: str) -> list[str]:
    """Annees litterales non autorisees pour ce fichier (liste vide = conforme)."""
    if any(frag in text for frag in YEAR_ALLOWLIST.get(filename, ())):
        return []
    return YEAR_RX.findall(text)

# Chaines a ignorer : ce ne sont pas des phrases (CSS, HTML, gabarits, routes).
_NOT_PROSE = (
    re.compile(r"[a-zA-ZÀ-ÿ]{3}"),      # doit contenir un vrai mot
)


def _normalise(text: str) -> str:
    """Apostrophes typographiques ramenees a l'apostrophe droite, pour que la
    ban-list attrape « règle d'honnêteté » quelle que soit sa forme."""
    return text.replace("’", "'").replace("‘", "'").replace("´", "'")


def _load_banlist() -> tuple[list[str], list[re.Pattern]]:
    terms: list[str] = []
    regexes: list[re.Pattern] = []
    for raw in BANLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("re:"):
            regexes.append(re.compile(line[3:].strip(), re.IGNORECASE))
        else:
            terms.append(_normalise(line).lower())
    return terms, regexes


BAN_TERMS, BAN_REGEXES = _load_banlist()


def banned_terms_in(text: str) -> list[str]:
    """Termes de la ban-list presents dans `text` (liste vide = conforme)."""
    probe = _normalise(text)
    low = probe.lower()
    hits = [t for t in BAN_TERMS if t in low]
    hits += [rx.pattern for rx in BAN_REGEXES if rx.search(probe)]
    return hits


def illegal_digits_in(text: str) -> str:
    """Ce qui reste de `text` une fois retires les chiffres autorises ; chaine
    vide (ou sans chiffre) = conforme."""
    stripped = text
    for rx in _ALLOW_RX:
        stripped = rx.sub(" ", stripped)
    found = re.findall(r"\d+(?:[ ,. ]\d+)*", stripped)
    return " · ".join(found)


def _is_prose(text: str) -> bool:
    """Ecarte ce qui n'est pas une phrase affichee : HTML, CSS, gabarits Plotly,
    specificateurs de format, routes de page."""
    s = text.strip()
    if not s or not _NOT_PROSE[0].search(s):
        return False
    if s.startswith("pages/"):                       # route st.page_link
        return False
    if "<" in s and ">" in s:                        # HTML
        return False
    if re.search(r"[a-z-]+\s*:\s*[^;]+;", s):        # CSS
        return False
    if "%{" in s or s.startswith("%") or "<extra>" in s:  # gabarit Plotly
        return False
    return True


def _rendered_texts(node: ast.AST) -> list[str]:
    """Textes qu'un argument d'appel d'affichage produit A L'ECRAN.

    On NE descend PAS dans les expressions interpolees d'une f-string : leur contenu
    (`row['vintage_date']`, `controls.xa(df, "co_works")`) est du code, pas du texte
    affiche -- c'est meme tout l'interet de la regle P6-R2 (b). Chaque trou est
    remplace par `{}` pour que la phrase reconstruite garde sa forme.
    """
    if isinstance(node, ast.Constant):
        return [node.value] if isinstance(node.value, str) else []
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                parts.append("{}")
        return ["".join(parts)]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _rendered_texts(node.left), _rendered_texts(node.right)
        if left and right:  # produit croise : une branche de ternaire n'est jamais perdue
            return [lhs + rhs for lhs in left for rhs in right]
        return left + right
    if isinstance(node, ast.IfExp):
        return _rendered_texts(node.body) + _rendered_texts(node.orelse)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [t for elt in node.elts for t in _rendered_texts(elt)]
    if isinstance(node, ast.Dict):
        out = []
        for k, v in zip(node.keys, node.values):
            if k is not None:
                out += _rendered_texts(k)
            out += _rendered_texts(v)
        return out
    if isinstance(node, ast.Call):
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in DISPLAY_CALLS:  # st.column_config.TextColumn("...") imbrique
            return [t for a in node.args for t in _rendered_texts(a)]
    return []


def _display_strings(path: Path) -> list[tuple[int, str]]:
    """(ligne, texte) de chaque texte affiche par un appel d'affichage."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[tuple[int, str]] = []

    def collect(node: ast.AST, lineno: int) -> None:
        for text in _rendered_texts(node):
            if _is_prose(text):
                out.append((getattr(node, "lineno", lineno), text))

    for node in ast.walk(tree):
        # Constantes de texte affiche : convention maison `<NOM>_FR = "..."`, posees
        # loin de l'appel qui les rend (pages 8/9/10/11/13/14).
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id.endswith("_FR") for t in node.targets):
                collect(node.value, node.lineno)
            continue
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name not in DISPLAY_CALLS:
            continue
        for arg in node.args:
            collect(arg, node.lineno)
        for kw in node.keywords:
            if kw.arg in SKIPPED_KWARGS:
                continue
            collect(kw.value, node.lineno)
    return out


def _surfaces() -> list[Path]:
    files = [MENU_FILE] + sorted(PAGES_DIR.glob("*.py"))
    return [f for f in files if f.name not in EXEMPT_PAGES]


ACTIVE = _surfaces()


@pytest.mark.parametrize("path", ACTIVE, ids=lambda p: p.name)
def test_no_internal_jargon_in_displayed_text(path: Path) -> None:
    offenders = [
        f"L{ln} : {text[:110]!r} -> {sorted(set(hits))}"
        for ln, text in _display_strings(path)
        for hits in [banned_terms_in(text)]
        if hits
    ]
    assert not offenders, (
        f"{path.name} : vocabulaire interne dans du texte affiche "
        f"(docs/NARRATIVE_CONTRACT_pass6.md section 1)\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize("path", ACTIVE, ids=lambda p: p.name)
def test_no_literal_data_values_in_static_text(path: Path) -> None:
    offenders = [
        f"L{ln} : {text[:110]!r} -> chiffres {left}"
        for ln, text in _display_strings(path)
        for left in [illegal_digits_in(text)]
        if left
    ]
    assert not offenders, (
        f"{path.name} : chiffre litteral dans une phrase statique -- calculez-le au "
        f"rendu (P6-R2 b) ou ajoutez-le a la liste blanche s'il s'agit d'une constante "
        f"de methode\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize("path", ACTIVE, ids=lambda p: p.name)
def test_no_year_literals_in_static_text(path: Path) -> None:
    offenders = [
        f"L{ln} : {text[:110]!r} -> annee(s) {years}"
        for ln, text in _display_strings(path)
        for years in [year_literals_in(path.name, text)]
        if years
    ]
    assert not offenders, (
        f"{path.name} : annee ecrite a la main dans une phrase statique -- elle sera "
        f"fausse a la premiere mise a jour de donnees. Calculez la fenetre depuis la "
        f"donnee (helpers.window_label()) ou, s'il s'agit d'un fait historique, "
        f"ajoutez une entree justifiee a YEAR_ALLOWLIST (sites recenses : "
        f"docs/YEAR_UPDATE_DESIGN.md section 5)\n" + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# Auto-tests du garde-fou : ils tournent meme quand toutes les pages sont exemptees,
# donc le mecanisme ne peut pas pourrir en silence pendant la vague de mise en
# conformite.
# ---------------------------------------------------------------------------

QUOTED_EXAMPLE_1 = (
    "Variante active : **`b_siris`** (colonne `B_siris` de `sdg_three_way.parquet`), "
    "choisie par `app.sdg_variant` dans `config.yaml`"
)
QUOTED_EXAMPLE_2 = (
    "travaux, ces parts ne partitionnent donc rien (règle d'honnêteté 13)."
)


@pytest.mark.parametrize("sample", [QUOTED_EXAMPLE_1, QUOTED_EXAMPLE_2])
def test_banlist_catches_the_two_quoted_examples(sample: str) -> None:
    assert banned_terms_in(sample), f"la ban-list laisse passer : {sample!r}"


def test_banlist_leaves_ordinary_french_alone() -> None:
    ok = (
        "Comment lire : chaque barre est un type de publication ; la part plus sombre "
        "isole la contribution I-SITE, sans jamais retirer de travaux du corpus affiché."
    )
    assert banned_terms_in(ok) == []


@pytest.mark.parametrize("sample", [
    "Physical Sciences forme 42,9 % du corpus",
    "les 811 topics hors référentiel",
    "le corpus par filiation de 36 819 travaux",
])
def test_digit_rule_catches_data_values(sample: str) -> None:
    assert illegal_digits_in(sample), f"valeur de donnee non detectee : {sample!r}"


@pytest.mark.parametrize("sample", [
    "Publications de l'Université de Lorraine, fenêtre 2019 à 2023",
    "Top 10 % (réf. France)",
    "Partenaires (≥10 co-publications)",
    "sous le plancher de 30 travaux",
    "méthode complète : section 2 de la note de méthode",
    "identifiant ORCID (format 0000-0002-1825-0097)",
])
def test_digit_rule_allows_the_whitelist(sample: str) -> None:
    assert not illegal_digits_in(sample), f"faux positif : {sample!r}"


@pytest.mark.parametrize("sample", [
    "Publications de l'Université de Lorraine, 2019-2023",
    "Vue d'ensemble par structure interne (2019-2023)",
    "Tendance (2019-23)",
    "Part fenêtre 1 (2019-2020)",
])
def test_year_rule_catches_window_literals(sample: str) -> None:
    assert year_literals_in("1_📊_Vue_d_ensemble.py", sample), f"annee non detectee : {sample!r}"


def test_year_rule_allows_a_documented_historical_fact() -> None:
    fact = ("Labellisée I-SITE en janvier 2016 (PIA2), l'initiative a traversé une "
            "période de probation jusqu'en 2021.")
    assert year_literals_in("7_🎯_I-SITE.py", fact) == []
    # ... mais la meme phrase sur une autre page reste une violation : l'autorisation
    # est nominative, jamais globale.
    assert year_literals_in("8_🤝_Collaborations.py", fact)


def test_year_allowlist_targets_existing_files() -> None:
    on_disk = {MENU_FILE.name} | {p.name for p in PAGES_DIR.glob("*.py")}
    unknown = set(YEAR_ALLOWLIST) - on_disk
    assert not unknown, f"YEAR_ALLOWLIST nomme des fichiers absents : {sorted(unknown)}"


def test_ratchet_only_shrinks() -> None:
    """Toute page exemptee doit exister : une entree perimee cacherait une page
    reellement non testee."""
    on_disk = {MENU_FILE.name} | {p.name for p in PAGES_DIR.glob("*.py")}
    unknown = EXEMPT_PAGES - on_disk
    assert not unknown, f"EXEMPT_PAGES nomme des fichiers absents : {sorted(unknown)}"


# =============================================================================
# EXTENSION S-EVAL (BUILD_PLAN.md P3, P14 ; pass 7a) -- memes trois regles
# (ban-list, chiffres, annees) appliquees aux constantes de module de
# `lib/copy_fr.py` et `lib/reading.py`. Port de BenchUp `collect_copy_module_
# strings`, adapte au FICHIER (ast sur le texte source) plutot qu'au module
# IMPORTE : un import live forcerait Streamlit/ sur sys.path pour rien.
# Fichier absent -> [] (jamais d'echec) ET le test le declare via pytest.skip.
#
# CORRECTION MANAGER (2026-09-10, apres l'atterrissage reel de copy_fr.py par
# S-TT) : NE SCANNE QUE LES VALEURS DES DICTS EXPORTES NOMMES, jamais "toute
# constante MAJUSCULE" -- copy_fr.py le dit lui-meme dans son propre docstring
# (section CONTRAT, "PORTEE du controle narratif") : ses VALEURS affichees
# vivent dans READING/KPI_HELP/CAPTIONS/LABELS/HOVER_LABELS, et son docstring
# de module nomme legitimement des fichiers/colonnes comme tout commentaire du
# depot. Une regle "toute majuscule" attraperait EN PLUS `READING_PLACEHOLDERS`
# (une table de NOMS DE TROUS DE FORMAT -- "window", "floor", "bin_prev"...,
# jamais du texte affiche). Alignee sur `tests/test_hover_spec.py` (S-TT) :
# meme fichier de ban-list, meme liste blanche de chiffres -- verifie en
# executant les deux suites ensemble (§ run au bas de ce fichier).
#
# BUG CORRIGE AU PASSAGE : copy_fr.py declare ses cinq dicts avec une
# annotation PEP 526 (`READING: dict[str, dict[str, str]] = {...}`), qui parse
# en `ast.AnnAssign`, PAS `ast.Assign` -- la version precedente de ce
# collecteur ne regardait que `ast.Assign` et n'aurait donc RIEN trouve du
# tout dans ce fichier reel (silencieusement, sans erreur). Les deux formes
# sont geree ci-dessous.
# =============================================================================
COPY_MODULE_FILES = [
    ROOT / "Streamlit" / "lib" / "copy_fr.py",
    ROOT / "Streamlit" / "lib" / "reading.py",
]

# Noms EXACTS des constantes qui portent du texte reellement rendu, par
# fichier -- jamais un motif ("toute majuscule"), une liste explicite. Vient
# du propre docstring de copy_fr.py (section CONTRAT) et doit rester ALIGNEE
# avec la portee que `tests/test_hover_spec.py` (S-TT) verifie de son cote.
COPY_FR_SCANNED_NAMES: tuple[str, ...] = ("READING", "KPI_HELP", "CAPTIONS", "LABELS", "HOVER_LABELS")
# lib/reading.py n'expose que des FONCTIONS par contrat (lib_api_pass7.md :
# `reading_text`/`reading_line`) -- le texte vit dans copy_fr.READING, pas ici.
# Vide -> rien a scanner tant que S-LIB-B (W2) n'y ajoute pas son propre dict.
READING_MODULE_SCANNED_NAMES: tuple[str, ...] = ()

COPY_MODULE_SCANNED_NAMES: dict[str, tuple[str, ...]] = {
    "copy_fr.py": COPY_FR_SCANNED_NAMES,
    "reading.py": READING_MODULE_SCANNED_NAMES,
}


def _walk_constant_strings(node: ast.AST) -> list[str]:
    """Chaines litterales portees par `node`, feuilles seulement. Les CLES de
    dict ne sont JAMAIS incluses -- ce sont des cles de lookup interne
    (`chart_key`, mode `"volume"/"fwci"/"phares"/"default"`), jamais du texte
    affiche -- fidele a BenchUp `_walk_strings`, qui ne descend que dans les
    valeurs. Distinct de `_rendered_texts` ci-dessus (qui, lui, inclut les
    cles : la ou ce fichier l'utilise, un dict est une table d'options
    `{"Libelle affiche": valeur}, ou la cle EST le texte affiche -- les deux
    semantiques sont reelles et differentes, d'ou deux fonctions."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return ["".join(
            v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "{}"
            for v in node.values
        )]
    if isinstance(node, ast.Dict):
        out: list[str] = []
        for v in node.values:
            out += _walk_constant_strings(v)
        return out
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        out = []
        for elt in node.elts:
            out += _walk_constant_strings(elt)
        return out
    return []


def collect_named_constant_strings(path: Path, names: tuple[str, ...]) -> list[tuple[int, str]]:
    """Chaines portees par les constantes de module dont le nom est EXACTEMENT
    dans `names` -- assignation simple (`NOM = ...`) OU annotee PEP 526
    (`NOM: type = ...`, la forme que copy_fr.py utilise partout). `names` vide
    ou fichier absent -> [] (jamais d'echec) -- le primitif general, teste
    directement (n'importe quel chemin/nom, utile pour la vacuite ci-dessous)."""
    if not names or not path.exists():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            hit = any(isinstance(t, ast.Name) and t.id in names for t in node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            hit = isinstance(node.target, ast.Name) and node.target.id in names and node.value is not None
            value = node.value
        else:
            continue
        if not hit:
            continue
        for text in _walk_constant_strings(value):
            if _is_prose(text):
                out.append((node.lineno, text))
    return out


def collect_module_constant_strings(path: Path) -> list[tuple[int, str]]:
    """Enrobage par fichier : resout les noms a scanner depuis
    `COPY_MODULE_SCANNED_NAMES[path.name]` (fichier ou nom inconnu -> [],
    jamais un echec) puis delegue a `collect_named_constant_strings`."""
    return collect_named_constant_strings(path, COPY_MODULE_SCANNED_NAMES.get(path.name, ()))


@pytest.mark.parametrize("path", COPY_MODULE_FILES, ids=lambda p: p.name)
def test_copy_module_constants_no_internal_jargon(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"{path.name} n'existe pas encore (S-LIB-B, W2) -- collecteur ok sur absence, jamais un echec")
    offenders = [
        f"L{ln} : {text[:110]!r} -> {sorted(set(hits))}"
        for ln, text in collect_module_constant_strings(path)
        for hits in [banned_terms_in(text)]
        if hits
    ]
    assert not offenders, (
        f"{path.name} : vocabulaire interne dans une constante de module "
        f"(docs/NARRATIVE_CONTRACT_pass6.md section 1)\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize("path", COPY_MODULE_FILES, ids=lambda p: p.name)
def test_copy_module_constants_no_literal_data_values(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"{path.name} n'existe pas encore (S-LIB-B, W2) -- collecteur ok sur absence, jamais un echec")
    offenders = [
        f"L{ln} : {text[:110]!r} -> chiffres {left}"
        for ln, text in collect_module_constant_strings(path)
        for left in [illegal_digits_in(text)]
        if left
    ]
    assert not offenders, (
        f"{path.name} : chiffre litteral dans une constante de module -- calculez-le au "
        f"rendu (P6-R2 b) ou ajoutez-le a la liste blanche s'il s'agit d'une constante de "
        f"methode\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize("path", COPY_MODULE_FILES, ids=lambda p: p.name)
def test_copy_module_constants_no_year_literals(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"{path.name} n'existe pas encore (S-LIB-B, W2) -- collecteur ok sur absence, jamais un echec")
    offenders = [
        f"L{ln} : {text[:110]!r} -> annee(s) {years}"
        for ln, text in collect_module_constant_strings(path)
        for years in [year_literals_in(path.name, text)]
        if years
    ]
    assert not offenders, (
        f"{path.name} : annee ecrite a la main dans une constante de module -- calculez la "
        f"fenetre depuis la donnee (helpers.window_label()) ou ajoutez une entree justifiee a "
        f"YEAR_ALLOWLIST\n" + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# VACUITE de l'extension (P14) -- le COLLECTEUR lui-meme (les trois regles
# sont deja vacuite-prouvees plus haut dans ce fichier) : recursion
# dict-de-dict et liste, assignation ANNOTEE (PEP 526, la forme reelle de
# copy_fr.py) geree au meme titre qu'une assignation simple, cles de dict
# jamais incluses, un nom HORS ALLOWLIST jamais collecte meme majuscule/
# dict-like (le risque exact que la correction manager ferme --
# `READING_PLACEHOLDERS` en vrai), docstring de module jamais collecte
# (ce n'est pas une assignation), fichier absent ou `names` vide -> [].
# ---------------------------------------------------------------------------
def test_collect_named_constant_strings_walks_nested_dicts_lists_and_ann_assign(tmp_path: Path) -> None:
    scratch = tmp_path / "_scratch.py"
    scratch.write_text(
        '"""Docstring qui nomme ptn_summary.parquet et VIZ_SPEC_pass7.md -- jamais scanne, '
        'ce n\'est pas une assignation."""\n'
        'READING: dict[str, dict[str, str]] = {\n'
        '    "zoom_balance_bars": {\n'
        '        "volume": "il y a 87 travaux en 2019 (ptn_summary)",\n'
        '        "default": "texte propre, sans chiffre ni annee",\n'
        '    },\n'
        '}\n'
        'OTHER_NOT_IN_ALLOWLIST = ["ptn_summary", "42 partenaires en 2021"]\n'
        '_PRIVATE = "jamais collecte non plus"\n',
        encoding="utf-8",
    )
    texts = [t for _, t in collect_named_constant_strings(scratch, ("READING",))]
    assert any("87 travaux en 2019" in t for t in texts), (
        "assignation ANNOTEE (PEP 526, READING: dict[...] = ...) : la feuille nichee doit etre atteinte"
    )
    assert not any(t == "zoom_balance_bars" for t in texts), "une CLE de dict (chart_key) ne doit jamais etre collectee"
    assert not any(t == "volume" for t in texts), "une CLE de dict (mode) ne doit jamais etre collectee"
    assert not any(("ptn_summary" == t or "42 partenaires" in t) for t in texts), (
        "un nom HORS de `names` (meme majuscule, meme dict/liste) ne doit jamais etre collecte -- "
        "exactement le risque que READING_PLACEHOLDERS pose en vrai dans copy_fr.py"
    )
    assert not any("jamais collecte" in t for t in texts), (
        "le docstring de module ne doit jamais etre collecte (ce n'est pas une assignation)"
    )
    # Et les regles existantes (deja vacuite-prouvees) attrapent la feuille nichee une fois collectee
    # ("87 travaux" n'est PAS sur la liste blanche -- seuls 30/3/5 le sont, contrairement a "42
    # partenaires" qui n'est jamais un plancher de methode) :
    leaf = next(t for t in texts if "87 travaux en 2019" in t)
    assert illegal_digits_in(leaf), "chiffre non detecte dans la feuille nichee"
    assert year_literals_in("copy_fr.py", leaf), "annee non detectee dans la feuille nichee"
    assert banned_terms_in(leaf), "ptn_summary (banlist §3) non detecte dans la feuille nichee"


def test_copy_fr_scanned_names_match_its_own_docstring_contract_and_exclude_placeholders() -> None:
    """La portee exacte (READING/KPI_HELP/CAPTIONS/LABELS/HOVER_LABELS) vient du
    docstring de copy_fr.py lui-meme (section CONTRAT, "PORTEE du controle
    narratif") -- fige ici pour que toute derive (un 6e dict ajoute la-bas,
    oublie ici) casse ce test plutot que de se corriger silencieusement en trop
    ou trop peu. READING_PLACEHOLDERS (table de noms de trous de format,
    jamais du texte affiche) est explicitement HORS de cette liste."""
    assert set(COPY_FR_SCANNED_NAMES) == {"READING", "KPI_HELP", "CAPTIONS", "LABELS", "HOVER_LABELS"}
    assert "READING_PLACEHOLDERS" not in COPY_FR_SCANNED_NAMES


def test_collect_named_constant_strings_returns_empty_on_missing_file_or_empty_names() -> None:
    missing = ROOT / "Streamlit" / "lib" / "__does_not_exist_pass7a__.py"
    assert not missing.exists()
    assert collect_named_constant_strings(missing, ("READING",)) == []
    real_existing_file = ROOT / "Streamlit" / "lib" / "helpers.py"
    assert collect_named_constant_strings(real_existing_file, ()) == [], (
        "names vide -> rien a scanner, meme sur un fichier reel et existant"
    )
