# tests/test_hover_spec.py
"""
Garde-fou du contrat de survol (BUILD_PLAN.md P2/P3/P14, ruling P7-R6).

CE QUE CE TEST VERIFIE
  (a) SANITE DU YAML : chaque cle du registre `docs/contract_fragments/chart_keys_pass7.md`
      a une entree (graphique -> `charts`, aide de KPI -> `tiles`) ; au plus 8 lignes par
      (graphique, mode), les mots-cles comptant pour 2 ; la premiere ligne porte un libelle
      vide (l'entite) ; un autre libelle vide n'est legal que sur une ligne `drapeau` ;
      chaque `format` appartient au vocabulaire ; aucun chiffre dans un libelle.
  (b) COMPLETUDE DE LA COPIE : `lib/copy_fr.py` porte un texte de lecture pour CHAQUE
      (graphique, mode) du yaml, une aide pour chaque tuile, et ses libelles de survol sont
      EGAUX a ceux du yaml (source unique) ; chaque trou de formatage utilise est declare
      dans `READING_PLACEHOLDERS`, et chaque trou declare est utilise.
  (c) PROPRETE NARRATIVE de `lib/copy_fr.py` : aucun terme de la ban-list, aucun chiffre
      hors liste blanche, aucune annee litterale -- memes fonctions que
      `tests/test_narrative.py`, importees et non recopiees. PORTEE : les VALEURS des
      dictionnaires exportes (le docstring et les commentaires du module sont du code,
      jamais affiches).
  (d) CONFORMITE DES CONSTRUCTEURS : pour chaque constructeur enregistre dans
      `tests/_registry.py` (`BUILDERS`, aliment par S-LIB-A), les chaines `customdata` de
      la figure portent les libelles du yaml, dans l'ordre du yaml, au format
      `<b>libelle</b> :`, sur au plus 8 lignes separees par `<br>`, la premiere ligne etant
      l'entite en gras sans deux-points. Un constructeur non encore enregistre est SAUTE
      (skip) ; un constructeur enregistre qui devie ECHOUE.
  (e) VACUITE (P14) : chaque famille de controle ci-dessus est re-executee sur une COPIE
      mutee (libelle retire, libelle vide, budget depasse, format inconnu, chiffre dans un
      libelle, mode de lecture retire, libelle divergent, valeur de donnee dans une phrase)
      et doit alors ECHOUER. Un controle qui ne peut pas echouer est du theatre.

    .venv-pinned\\Scripts\\python -m pytest tests\\test_hover_spec.py -q
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import re
import string
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "docs" / "tooltip_spec.yaml"
REGISTRY_MD = ROOT / "docs" / "contract_fragments" / "chart_keys_pass7.md"
COPY_FR_PATH = ROOT / "Streamlit" / "lib" / "copy_fr.py"

# Les regles narratives sont celles de test_narrative.py : une seule implementation.
from tests.test_narrative import (  # noqa: E402
    YEAR_RX,
    banned_terms_in,
    illegal_digits_in,
)

MAX_LINES = 8                      # lib/hover.py MAX_LINES
KEYWORDS_FORMAT = "mots_cles_2x5"  # compte pour 2 lignes
FLAG_FORMAT = "drapeau"            # seule ligne (hors entite) a libelle vide
DIGIT_RX = re.compile(r"\d")


# ---------------------------------------------------------------------------
# Chargements
# ---------------------------------------------------------------------------
def load_spec() -> dict:
    with open(SPEC_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_copy_fr():
    """Charge `Streamlit/lib/copy_fr.py` PAR CHEMIN, sans passer par le paquet `lib`
    (ce depot en a deux, cf. tests/conftest.py) -- ce qui prouve accessoirement que le
    module est importable sans streamlit."""
    spec = importlib.util.spec_from_file_location("copy_fr_under_test", COPY_FR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SPEC = load_spec()
COPY = load_copy_fr()


def registry_keys() -> tuple[list[str], list[str], dict[str, list[str]]]:
    """(cles de graphique, cles de tuile, modes parsables) lus dans le tableau du
    registre. La colonne « key » peut porter plusieurs cles separees par « · »."""
    charts: list[str] = []
    tiles: list[str] = []
    modes: dict[str, list[str]] = {}
    for raw in REGISTRY_MD.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5 or cells[0].lower() == "key" or cells[0].startswith("---"):
            continue
        keys = [k.strip().strip("`") for k in cells[0].split("·") if k.strip()]
        is_tile = cells[2].lower().startswith("kpi")
        (tiles if is_tile else charts).extend(keys)
        if is_tile:
            continue
        dims = [
            re.findall(r"`([^`]+)`", part)
            for part in re.split(r"[×x]\s*(?=\w+:)", cells[3])
        ]
        dims = [d for d in dims if d]
        if len(dims) == 1:
            parsed = list(dims[0])
        elif len(dims) == 2:
            parsed = [f"{a}|{b}" for a in dims[0] for b in dims[1]]
        elif not dims and cells[3] in {"", "-", "--", "—"}:
            parsed = ["default"]
        else:
            parsed = []                      # cellule en prose (« same four ») : non parsable
        if parsed:
            for k in keys:
                modes[k] = parsed
    return charts, tiles, modes


REG_CHARTS, REG_TILES, REG_MODES = registry_keys()


def spec_modes(spec: dict, chart_key: str) -> list[str]:
    return list(spec["charts"][chart_key].get("modes") or ["default"])


def spec_lines(spec: dict, chart_key: str, mode: str) -> list[dict]:
    chart = spec["charts"][chart_key]
    by_mode = chart.get("lines_by_mode") or {}
    return by_mode.get(mode) or chart["lines"]


def spec_labels(spec: dict, chart_key: str, mode: str, *, unconditional_only: bool = False
                ) -> list[str]:
    lines = spec_lines(spec, chart_key, mode)
    if unconditional_only:
        lines = [ln for ln in lines if "when" not in ln]
    return [ln.get("label", "") for ln in lines]


def line_cost(lines: list[dict]) -> int:
    return sum(2 if ln.get("format") == KEYWORDS_FORMAT else 1 for ln in lines)


# ---------------------------------------------------------------------------
# Controles reutilisables (chacun rend une liste d'infractions -- vide = conforme).
# Ce sont EUX que les tests de vacuite re-executent sur une copie mutee.
# ---------------------------------------------------------------------------
def offenders_coverage(spec: dict) -> list[str]:
    missing = [k for k in REG_CHARTS if k not in spec.get("charts", {})]
    missing += [f"tuile {k}" for k in REG_TILES if k not in spec.get("tiles", {})]
    extra = [f"hors registre : {k}" for k in spec.get("charts", {}) if k not in REG_CHARTS]
    extra += [f"hors registre : tuile {k}" for k in spec.get("tiles", {}) if k not in REG_TILES]
    return missing + extra


def offenders_budget(spec: dict) -> list[str]:
    out = []
    for key in spec["charts"]:
        for mode in spec_modes(spec, key):
            cost = line_cost(spec_lines(spec, key, mode))
            if cost > MAX_LINES:
                out.append(f"{key} [{mode}] : {cost} lignes > {MAX_LINES}")
    return out


def offenders_first_line(spec: dict) -> list[str]:
    out = []
    for key in spec["charts"]:
        for mode in spec_modes(spec, key):
            labels = spec_labels(spec, key, mode)
            if not labels or labels[0] != "":
                out.append(f"{key} [{mode}] : premiere ligne = {labels[:1]!r}, attendu ''")
    return out


def offenders_empty_label(spec: dict) -> list[str]:
    out = []
    for key in spec["charts"]:
        for mode in spec_modes(spec, key):
            for pos, ln in enumerate(spec_lines(spec, key, mode)):
                if pos == 0 or ln.get("label"):
                    continue
                if ln.get("format") != FLAG_FORMAT:
                    out.append(f"{key} [{mode}] ligne {pos} : libelle vide sans format "
                               f"{FLAG_FORMAT} ({ln.get('field')})")
    return out


def offenders_format(spec: dict) -> list[str]:
    vocab = set(spec["formats"])
    out = []
    for key in spec["charts"]:
        for mode in spec_modes(spec, key):
            for ln in spec_lines(spec, key, mode):
                if ln.get("format") not in vocab:
                    out.append(f"{key} [{mode}] : format {ln.get('format')!r} hors vocabulaire")
    return out


def offenders_digit_in_label(spec: dict) -> list[str]:
    out = []
    for key in spec["charts"]:
        for mode in spec_modes(spec, key):
            for label in spec_labels(spec, key, mode):
                if label and DIGIT_RX.search(label):
                    out.append(f"{key} [{mode}] : chiffre dans le libelle {label!r}")
    return out


def offenders_reading(spec: dict, reading: dict) -> list[str]:
    out = []
    for key in spec["charts"]:
        for mode in spec_modes(spec, key):
            if mode not in reading.get(key, {}):
                out.append(f"READING[{key!r}][{mode!r}] manquant")
    return out


def offenders_kpi_help(spec: dict, kpi_help: dict) -> list[str]:
    out = [f"KPI_HELP[{k!r}] manquant" for k in spec["tiles"] if k not in kpi_help]
    for key, tile in spec["tiles"].items():
        expected = " ".join(tile["help_lines"])
        if kpi_help.get(key) not in (None, expected):
            out.append(f"KPI_HELP[{key!r}] != help_lines du yaml")
    return out


def offenders_hover_labels(spec: dict, hover_labels: dict) -> list[str]:
    out = []
    for key in spec["charts"]:
        for mode in spec_modes(spec, key):
            expected = spec_labels(spec, key, mode)
            got = hover_labels.get(key, {}).get(mode)
            if got is None:
                out.append(f"HOVER_LABELS[{key!r}][{mode!r}] manquant")
            elif list(got) != expected:
                out.append(f"HOVER_LABELS[{key!r}][{mode!r}] != yaml")
    return out


def _holes(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def _texts_of(value) -> list[str]:
    """READING est {cle: {mode: texte}} ; KPI_HELP et CAPTIONS sont {cle: texte}."""
    return list(value.values()) if isinstance(value, dict) else [value]


def offenders_placeholders(texts: dict, declared: dict) -> list[str]:
    out = []
    for key, value in texts.items():
        bodies = _texts_of(value)
        used = set().union(*(_holes(t) for t in bodies)) if bodies else set()
        decl = set(declared.get(key, ()))
        for hole in sorted(used - decl):
            out.append(f"{key} : trou {{{hole}}} non declare dans READING_PLACEHOLDERS")
        for hole in sorted(decl - used):
            out.append(f"{key} : trou {{{hole}}} declare mais jamais utilise")
    return out


def _strings(node) -> list[str]:
    """Toutes les VALEURS de type chaine, en profondeur (les cles sont du code)."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in _strings(v)]
    if isinstance(node, (list, tuple, set)):
        return [s for v in node for s in _strings(v)]
    return []


def displayed_strings(module) -> list[tuple[str, str]]:
    out = []
    for name in ("READING", "KPI_HELP", "CAPTIONS", "LABELS", "HOVER_LABELS"):
        for text in _strings(getattr(module, name)):
            out.append((name, text))
    return out


def offenders_narrative(pairs: list[tuple[str, str]]) -> list[str]:
    out = []
    for name, text in pairs:
        hits = banned_terms_in(text)
        if hits:
            out.append(f"{name} : ban-list {sorted(set(hits))} dans {text[:90]!r}")
        left = illegal_digits_in(text)
        if left:
            out.append(f"{name} : chiffre {left} dans {text[:90]!r}")
        years = YEAR_RX.findall(text)
        if years:
            out.append(f"{name} : annee {years} dans {text[:90]!r}")
    return out


# ---------------------------------------------------------------------------
# Conformite d'un survol rendu
# ---------------------------------------------------------------------------
# `[^<]+` : un libelle ne porte jamais de chevron, et le motif ne peut donc pas
# enjamber un `<br>` pour coller l'entite au libelle suivant.
LABEL_RX = re.compile(r"<b>([^<]+)</b>\s*:")


def offenders_hover_string(hover: str, spec: dict, chart_key: str) -> list[str]:
    """Infractions d'UNE chaine de survol face au spec du graphique. Le mode n'est pas
    connu du registre de constructeurs : la chaine est conforme des qu'ELLE SATISFAIT
    AU MOINS UN mode declare (libelles inconditionnels tous presents, dans l'ordre, et
    aucun libelle etranger a ce mode)."""
    parts = hover.split("<br>")
    problems: list[str] = []
    if len(parts) > MAX_LINES:
        problems.append(f"{chart_key} : {len(parts)} lignes > {MAX_LINES} -- {hover[:90]!r}")
    head = parts[0]
    if not head.startswith("<b>") or "</b>" not in head:
        problems.append(f"{chart_key} : premiere ligne non gras -- {head!r}")
    if LABEL_RX.search(head):
        problems.append(f"{chart_key} : premiere ligne porte un libelle -- {head!r}")
    found = LABEL_RX.findall(hover)
    for mode in spec_modes(spec, chart_key):
        wanted = [lb for lb in spec_labels(spec, chart_key, mode, unconditional_only=True) if lb]
        allowed = {lb for lb in spec_labels(spec, chart_key, mode) if lb}
        pos = -1
        ok = True
        for label in wanted:
            idx = hover.find(f"<b>{label}</b>")
            if idx <= pos:
                ok = False
                break
            pos = idx
        if ok and not (set(found) - allowed):
            return problems                      # ce mode explique la chaine
    return problems + [
        f"{chart_key} : aucun mode du spec n'explique {found!r} -- {hover[:120]!r}"
    ]


def registered_builders() -> list[tuple]:
    """`tests/_registry.py` est cree par S-EVAL dans la meme vague et rempli par
    S-LIB-A : absent, vide ou cassé -> liste vide -> les tests (d) sautent."""
    for name in ("tests._registry", "_registry"):
        try:
            module = __import__(name, fromlist=["BUILDERS"])
        except Exception:
            continue
        return list(getattr(module, "BUILDERS", []) or [])
    return []


BUILDERS = registered_builders()


# ===========================================================================
# (a) sanite du yaml
# ===========================================================================
def test_yaml_loads_and_declares_a_version() -> None:
    assert SPEC["version"] == 1
    assert SPEC["formats"] and SPEC["charts"] and SPEC["tiles"]


def test_copy_fr_is_a_pure_module() -> None:
    """« importable sans streamlit » se verifie sur le FICHIER, pas sur les modules charges :
    un autre fichier de tests peut avoir charge streamlit dans le meme processus."""
    tree = ast.parse(COPY_FR_PATH.read_text(encoding="utf-8"))
    imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import)
                      else [ast.alias(name=node.module or "")])
    ]
    assert imports == [], f"copy_fr.py doit rester un module pur : {imports}"


def test_registry_parsing_is_not_vacuous() -> None:
    """Si le tableau du registre cessait d'etre parsable, tous les controles (a) et (b)
    passeraient a vide : on epingle donc le parsing lui-meme."""
    assert len(REG_CHARTS) >= 20, REG_CHARTS
    assert len(REG_TILES) >= 10, REG_TILES
    assert len(REG_MODES) >= 5, sorted(REG_MODES)
    assert len(set(REG_CHARTS)) == len(REG_CHARTS), "cle de graphique dupliquee au registre"


def test_every_registry_key_has_an_entry() -> None:
    assert offenders_coverage(SPEC) == []


def test_modes_match_the_registry_where_it_is_parsable() -> None:
    bad = [
        f"{k} : yaml {spec_modes(SPEC, k)} != registre {v}"
        for k, v in REG_MODES.items()
        if k in SPEC["charts"] and sorted(spec_modes(SPEC, k)) != sorted(v)
    ]
    assert bad == []


def test_hover_line_budget() -> None:
    assert offenders_budget(SPEC) == []


def test_first_line_is_the_entity() -> None:
    assert offenders_first_line(SPEC) == []


def test_only_flag_lines_may_have_an_empty_label() -> None:
    assert offenders_empty_label(SPEC) == []


def test_every_format_is_in_the_vocabulary() -> None:
    assert offenders_format(SPEC) == []


def test_no_digit_in_any_label() -> None:
    assert offenders_digit_in_label(SPEC) == []


def test_every_format_of_the_vocabulary_is_defined_and_exemplified() -> None:
    bad = [f for f, body in SPEC["formats"].items()
           if not isinstance(body, dict) or not body.get("definition") or "exemple" not in body]
    assert bad == [], bad


# ===========================================================================
# (b) completude de la copie
# ===========================================================================
def test_every_chart_and_mode_has_a_reading_text() -> None:
    assert offenders_reading(SPEC, COPY.READING) == []


def test_reading_has_no_key_outside_the_spec() -> None:
    assert sorted(COPY.READING) == sorted(SPEC["charts"])


def test_every_tile_has_a_kpi_help() -> None:
    assert offenders_kpi_help(SPEC, COPY.KPI_HELP) == []


def test_hover_labels_equal_the_yaml() -> None:
    assert offenders_hover_labels(SPEC, COPY.HOVER_LABELS) == []


PLACEHOLDER_SURFACES = ("READING", "KPI_HELP", "CAPTIONS")


def _surface(name: str) -> tuple[dict, dict]:
    declared = {"READING": "READING_PLACEHOLDERS", "KPI_HELP": "KPI_PLACEHOLDERS",
                "CAPTIONS": "CAPTION_PLACEHOLDERS"}[name]
    return getattr(COPY, name), getattr(COPY, declared)


@pytest.mark.parametrize("surface", PLACEHOLDER_SURFACES)
def test_every_placeholder_is_documented_and_used(surface: str) -> None:
    texts, declared = _surface(surface)
    assert offenders_placeholders(texts, declared) == []


@pytest.mark.parametrize("surface", PLACEHOLDER_SURFACES)
def test_texts_format_with_their_declared_holes(surface: str) -> None:
    """Contrat commun de `reading_text` et des aides/legendes : `.format(**fills)` avec les
    seuls trous declares, sans KeyError ni accolade orpheline."""
    texts, declared = _surface(surface)
    for key, value in texts.items():
        fills = {h: "X" for h in declared[key]}
        for i, text in enumerate(_texts_of(value)):
            rendered = text.format(**fills)
            assert "{" not in rendered and "}" not in rendered, f"{key} [{i}] : {rendered!r}"


def test_no_constant_is_retyped_in_words() -> None:
    """lens D14 : `links.IDLIST_MAX` etait retape « cent identifiants » a trois endroits ;
    une phrase qui reecrit une constante devient fausse en silence."""
    bad = [f"{n} : {t[:80]!r}" for n, t in displayed_strings(COPY)
           if "cent identifiant" in t.lower()]
    assert bad == [], bad


def test_partner_weight_and_involvement_share_are_never_confused() -> None:
    """lens D1/D2 : « part du portefeuille propre du partenaire » nommait, selon la ligne,
    un poids de portefeuille OU une part d'implication. Les deux libelles sont desormais
    distincts, et l'ancien libelle ambigu ne doit plus exister."""
    labels = [lb for modes in COPY.HOVER_LABELS.values() for lbs in modes.values()
              for lb in lbs]
    assert "part du portefeuille propre du partenaire" not in labels
    assert any(lb.startswith("poids du n") for lb in labels), "le poids de portefeuille a disparu"
    assert any("qui implique l" in lb for lb in labels), "la part d'implication a disparu"


def test_required_captions_and_labels_exist() -> None:
    for cap in ("PHARES_PROXY", "DERIVED_PARTNER_VOLUME", "FRONTIER_VINTAGES",
                "SUBFIELD_NULL_SHARE", "PLANE_UNSCORED", "THIN_PARTNER",
                "JOINT_UNDER_FLOOR"):
        assert COPY.CAPTIONS.get(cap), cap
    for lab in ("PAGE_WORKBOOK", "LEVEL_TOGGLE", "BALANCE_MODES", "PLANE_SELECT",
                "PHARES", "JOINT_COL"):
        assert COPY.LABELS.get(lab), lab
    assert set(COPY.LABELS["BALANCE_MODES"]) == {"volume", "fwci", "phares"}
    assert set(COPY.LABELS["PLANE_SELECT"]) == {"volume", "fwci", "frontiere", "phares"}


# ===========================================================================
# (c) proprete narrative de copy_fr.py
# ===========================================================================
def test_copy_fr_is_narratively_clean() -> None:
    assert offenders_narrative(displayed_strings(COPY)) == []


def test_copy_fr_scan_is_not_vacuous() -> None:
    pairs = displayed_strings(COPY)
    assert len(pairs) > 150, len(pairs)


# ===========================================================================
# (d) conformite des constructeurs enregistres
# ===========================================================================
@pytest.mark.skipif(not BUILDERS, reason="tests/_registry.py BUILDERS vide (S-LIB-A)")
@pytest.mark.parametrize("entry", BUILDERS, ids=lambda e: str(e[0]))
def test_registered_builder_hovers_follow_the_spec(entry) -> None:
    chart_key, _family, build_fn = entry[0], entry[1], entry[2]
    assert chart_key in SPEC["charts"], f"{chart_key} enregistre mais absent du spec"
    fig = build_fn()
    hovers = [
        str(h) for trace in fig.data
        for h in (getattr(trace, "customdata", None) or [])
        if isinstance(h, str) or (hasattr(h, "__len__") and not isinstance(h, (list, tuple)))
    ]
    assert hovers, f"{chart_key} : aucune chaine customdata"
    problems = [p for hover in hovers for p in offenders_hover_string(hover, SPEC, chart_key)]
    assert problems == [], problems[:10]


def test_builder_registry_import_is_defensive() -> None:
    """Le registre peut ne pas exister encore : le chargement doit rendre une liste."""
    assert isinstance(registered_builders(), list)


# ===========================================================================
# (e) VACUITE (P14) -- chaque controle est mute et doit alors echouer
# ===========================================================================
def _mutable_chart(spec: dict) -> tuple[dict, str, str]:
    """Un graphique sans `lines_by_mode` (mutation locale, pas partagee par ancre)."""
    for key, chart in spec["charts"].items():
        if "lines_by_mode" not in chart and len(chart["lines"]) > 2:
            return chart, key, spec_modes(spec, key)[0]
    raise AssertionError("aucun graphique mutable")


def test_vacuity_coverage() -> None:
    assert offenders_coverage(SPEC) == []
    mutated = copy.deepcopy(SPEC)
    mutated["charts"].pop(REG_CHARTS[0])
    assert offenders_coverage(mutated), "un graphique retire doit etre signale"


def test_vacuity_budget() -> None:
    assert offenders_budget(SPEC) == []
    mutated = copy.deepcopy(SPEC)
    chart, _key, _mode = _mutable_chart(mutated)
    chart["lines"].extend([{"field": "x", "label": "de trop", "format": "texte"}] * 9)
    assert offenders_budget(mutated), "un survol de plus de huit lignes doit etre signale"


def test_vacuity_first_line() -> None:
    assert offenders_first_line(SPEC) == []
    mutated = copy.deepcopy(SPEC)
    chart, _key, _mode = _mutable_chart(mutated)
    chart["lines"][0]["label"] = "entite"
    assert offenders_first_line(mutated), "une premiere ligne libellee doit etre signalee"


def test_vacuity_empty_label() -> None:
    assert offenders_empty_label(SPEC) == []
    mutated = copy.deepcopy(SPEC)
    chart, _key, _mode = _mutable_chart(mutated)
    chart["lines"][1]["label"] = ""            # libelle retire sur une ligne a valeur
    assert offenders_empty_label(mutated), "un libelle vide non-drapeau doit etre signale"


def test_vacuity_format() -> None:
    assert offenders_format(SPEC) == []
    mutated = copy.deepcopy(SPEC)
    chart, _key, _mode = _mutable_chart(mutated)
    chart["lines"][1]["format"] = "pourcentage_maison"
    assert offenders_format(mutated), "un format hors vocabulaire doit etre signale"


def test_vacuity_digit_in_label() -> None:
    assert offenders_digit_in_label(SPEC) == []
    mutated = copy.deepcopy(SPEC)
    chart, _key, _mode = _mutable_chart(mutated)
    chart["lines"][1]["label"] = "part des 3 premiers champs"
    assert offenders_digit_in_label(mutated), "un chiffre dans un libelle doit etre signale"


def test_vacuity_reading_completeness() -> None:
    assert offenders_reading(SPEC, COPY.READING) == []
    mutated = {k: dict(v) for k, v in COPY.READING.items()}
    key = "zoom_balance_bars"
    mutated[key].pop(spec_modes(SPEC, key)[-1])
    assert offenders_reading(SPEC, mutated), "un mode sans texte de lecture doit etre signale"


def test_vacuity_kpi_help() -> None:
    assert offenders_kpi_help(SPEC, COPY.KPI_HELP) == []
    mutated = dict(COPY.KPI_HELP)
    victim = sorted(SPEC["tiles"])[0]
    mutated[victim] = "aide reecrite a la main"
    assert offenders_kpi_help(SPEC, mutated), "une aide divergente doit etre signalee"
    mutated.pop(victim)
    assert offenders_kpi_help(SPEC, mutated), "une aide manquante doit etre signalee"


def test_vacuity_hover_labels_equality() -> None:
    assert offenders_hover_labels(SPEC, COPY.HOVER_LABELS) == []
    mutated = {k: {m: list(v) for m, v in modes.items()}
               for k, modes in COPY.HOVER_LABELS.items()}
    key = REG_CHARTS[0]
    mode = spec_modes(SPEC, key)[0]
    mutated[key][mode].pop()                   # un libelle retire de la source unique
    assert offenders_hover_labels(SPEC, mutated), "une divergence de libelle doit etre signalee"


def test_vacuity_placeholders() -> None:
    assert offenders_placeholders(COPY.READING, COPY.READING_PLACEHOLDERS) == []
    mutated = {k: dict(v) for k, v in COPY.READING.items()}
    key = "zoom_portage"
    mutated[key]["default"] = mutated[key]["default"] + " Fenetre : {window}."
    assert offenders_placeholders(mutated, COPY.READING_PLACEHOLDERS), \
        "un trou non declare doit etre signale"
    # aides et legendes : meme controle, meme mutation
    kpi = dict(COPY.KPI_HELP)
    kpi["zoom_kpi_fwci"] = kpi["zoom_kpi_fwci"] + " Plafond : {max_ids}."
    assert offenders_placeholders(kpi, COPY.KPI_PLACEHOLDERS)
    caps = dict(COPY.CAPTIONS)
    caps["THIN_PARTNER"] = caps["THIN_PARTNER"] + " Plancher : {floor}."
    assert offenders_placeholders(caps, COPY.CAPTION_PLACEHOLDERS)
    # un trou declare mais jamais employe est signale aussi
    assert offenders_placeholders(COPY.CAPTIONS, {**COPY.CAPTION_PLACEHOLDERS,
                                                 "THIN_PARTNER": ("floor",)})


def test_vacuity_retyped_constant() -> None:
    assert offenders_narrative(displayed_strings(COPY)) == []
    fake = [("CAPTIONS", "Au-dela de cent identifiants, le lien ouvre autre chose.")]
    bad = [f"{n} : {t[:80]!r}" for n, t in fake if "cent identifiant" in t.lower()]
    assert bad, "l epingle D14 doit attraper une constante retapee en mots"


def test_vacuity_partner_label_split() -> None:
    labels = [lb for modes in COPY.HOVER_LABELS.values() for lbs in modes.values()
              for lb in lbs]
    assert "part du portefeuille propre du partenaire" not in labels
    assert "part du portefeuille propre du partenaire" in (
        labels + ["part du portefeuille propre du partenaire"]
    ), "controle inverse : la chaine cherchee est bien detectable quand elle est presente"


def test_vacuity_narrative() -> None:
    assert offenders_narrative(displayed_strings(COPY)) == []
    assert offenders_narrative([("CAPTIONS", "la relation porte 1 234 co-publications")])
    assert offenders_narrative([("READING", "part mesuree sur la fenetre 2019-2023")])
    assert offenders_narrative([("READING", "colonne share_ul du tableau")])


def test_vacuity_hover_string_conformance() -> None:
    """Le controle (d) tourne meme sans constructeur enregistre : on lui donne une
    chaine SYNTHETIQUE conforme, puis les memes mutees."""
    key = "zoom_field_companion"
    mode = spec_modes(SPEC, key)[0]
    labels = spec_labels(SPEC, key, mode)
    good = "<b>Chemistry</b><br>" + "<br>".join(
        f"<b>{lb}</b> : x" for lb in labels[1:] if lb
    )
    assert offenders_hover_string(good, SPEC, key) == [], good

    body = [f"<b>{lb}</b> : x" for lb in labels[1:] if lb]
    dropped = "<b>Chemistry</b><br>" + "<br>".join(body[1:])          # libelle inconditionnel retire
    assert offenders_hover_string(dropped, SPEC, key), "un libelle manquant doit etre signale"

    swapped = "<b>Chemistry</b><br>" + "<br>".join([body[1], body[0]] + body[2:])
    assert offenders_hover_string(swapped, SPEC, key), "un libelle hors ordre doit etre signale"

    foreign = good + "<br><b>indicateur maison</b> : x"
    assert offenders_hover_string(foreign, SPEC, key), "un libelle etranger doit etre signale"

    too_long = "<b>Chemistry</b>" + "<br>x" * MAX_LINES
    assert offenders_hover_string(too_long, SPEC, key), "un survol trop long doit etre signale"

    labelled_head = "<b>champ</b> : Chemistry<br>" + "<br>".join(body)
    assert offenders_hover_string(labelled_head, SPEC, key), \
        "une premiere ligne libellee doit etre signalee"
