# tests/test_chart_layout.py
"""tests/test_chart_layout.py -- le contrat de mise en page des barres (BUILD_PLAN.md
P1, P14(2)), verifie SYSTEMATIQUEMENT sur chaque builder enregistre dans
`tests/_registry.py` : UNE colonne de libelle fixe + UNE colonne de gutter par
famille, UN pas de ligne par forme de ligne (simple/paire), UNE paire de polices
tick/gutter, UNE forme de reference rouge pointillee (BUILD_PLAN.md P14(2)/lib_api
pass 7a §charts). Modele : docs/reference/benchup_2026-09-04/tests/test_chart_layout.py
(memes 8 familles de verification), adapte a l'API pass 7a de
docs/contract_fragments/lib_api_pass7.md.

SQUELETTE (S-EVAL, W1) -- `Streamlit/lib/charts.py` n'existe pas encore (S-LIB-A le
livre en W2) : ce fichier entier SKIP proprement (`pytest.skip(allow_module_level=True)`)
tant qu'il est absent -- AUCUN import, AUCUNE mutation de `sys.modules`/`sys.path` n'a
lieu avant cette verification d'existence, pour ne jamais fuiter la bascule
`sys.modules['lib']` (F-SYSMOD, tests/conftest.py) dans le reste de la session pytest
si ce fichier ne va pas plus loin. Une fois le module present :
  - les constantes P1 sont verifiees (types declares) -- independant du registre ;
  - les 6 checks de geometrie + le wrap sont verifies POUR CHAQUE builder de
    `tests/_registry.BUILDERS` dont la famille est une des 6 a colonnes fixes
    (`family in lib.charts.FAMILIES` -- exclut nativement `scatter` ET `annee`,
    qui n'ont pas d'entree dans LABEL_COL_PX/GUTTER_COL_PX/WRAP_PX) ; **registre
    vide -> zero test collecte pour ces verifications, jamais un echec** ;
  - la VACUITE (P14) de la relation de marge tourne INDEPENDAMMENT du registre :
    une figure synthetique a la marge EXACTE passe, la meme decalee d'1 px echoue.

    python -m pytest tests/test_chart_layout.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
DATA_DIR = STREAMLIT_DIR / "data"
_CHARTS_FILE = STREAMLIT_DIR / "lib" / "charts.py"

if not _CHARTS_FILE.exists():
    pytest.skip(
        "Streamlit/lib/charts.py n'existe pas encore (S-LIB-A, W2) -- squelette S-EVAL "
        "(BUILD_PLAN.md P18, W1) : ce fichier entier skip proprement tant que le module "
        "n'est pas livre. Une fois present, relancer : "
        "python -m pytest tests/test_charts.py tests/test_chart_layout.py -q",
        allow_module_level=True,
    )

# F-SYSMOD (tests/conftest.py) : deux packages nommes `lib` existent dans ce depot
# (le pipeline racine et Streamlit/lib) ; sys.modules['lib'] ne peut etre bind qu'a
# un seul par process.
#
# FIX-2 (docs/INSPECTION_REPORT_pass7a.md §8, D1, HIGH) : la version precedente
# appelait `swap_lib_to_streamlit()` au niveau module et ne restaurait qu'en
# `teardown_module` -- MAIS pytest importe (collecte) TOUS les fichiers d'une
# session AVANT d'en executer aucun, et `teardown_module` d'un fichier ne tourne
# qu'apres l'EXECUTION de ses propres tests, jamais juste apres sa collecte. Le
# swap restait donc actif pendant toute la collecte des fichiers suivants
# (alphabetiquement apres "chart_layout") -- `test_contract_tables.py`,
# `test_invariants.py`, `test_pass6_data.py`, `test_pass7_data.py` -- qui ont
# besoin du `lib` RACINE (`lib.snapshot` etc.) au niveau module : `sys.modules
# ['lib']` pointait alors vers Streamlit/lib, `ModuleNotFoundError` immediat,
# `pytest tests -q` avortait a la collecte, 0 test execute.
#
# Correctif retenu : le repli documente par conftest.py lui-meme pour un fichier
# qui A BESOIN des constantes au niveau module (parametrize decorators evaluent
# a l'IMPORT, avant que pytest puisse jamais appeler setup_module -- le patron
# setup/teardown des 9 fichiers AppTest, qui ne resolvent `lib` qu'au moment de
# leurs propres fonctions de test, ne peut pas s'appliquer ici) : le swap ET la
# restauration ont lieu ICI, au meme niveau module, l'un juste apres l'autre,
# SANS jamais les separer par un hook differe. Aucune collecte d'un AUTRE
# fichier ne peut s'intercaler entre deux instructions du corps de CE module --
# la fenetre de fuite est donc fermee : `sys.modules['lib']` n'est jamais
# rebind a Streamlit/lib plus longtemps que ces trois lignes.
from conftest import restore_lib, swap_lib_to_streamlit  # noqa: E402

_saved_lib_modules: dict = swap_lib_to_streamlit()
import lib.charts as C   # noqa: E402
import lib.helpers as H  # noqa: E402
restore_lib(_saved_lib_modules)  # restauree IMMEDIATEMENT -- pas de teardown_module differe

import _registry  # noqa: E402  (tests/ meme -- pas de package, import nu ; independant de lib)


REFERENCE_RED = getattr(H, "REFERENCE_RED", "#821D13")
BASIS_LABELS_FORBIDDEN = {"Publications", "Co-publications"}
ELLIPSIS_MARKERS = ("…", "...")


# ---------------------------------------------------------------------------
# 1. Constantes P1 -- existence + type declare, independant du registre.
# ---------------------------------------------------------------------------
def test_p1_constants_exist_with_declared_types() -> None:
    assert isinstance(C.FAMILIES, tuple) and C.FAMILIES, "FAMILIES doit etre un tuple non vide"
    assert all(isinstance(f, str) for f in C.FAMILIES)

    for name in ("LABEL_COL_PX", "GUTTER_COL_PX", "WRAP_PX"):
        d = getattr(C, name)
        assert isinstance(d, dict) and d, f"{name} doit etre un dict[str, int] non vide"
        missing = set(C.FAMILIES) - set(d)
        assert not missing, f"{name} : familles de P1 manquantes {sorted(missing)}"
        assert all(isinstance(k, str) and isinstance(v, int) for k, v in d.items()), (
            f"{name} : chaque valeur doit etre un int (px)"
        )

    for name in ("COL_PAD_PX", "ROW_PITCH_SINGLE", "BAR_PX_SINGLE", "ROW_PITCH_PAIR",
                 "BAR_PX_PAIR", "TICK_FONT_PX", "GUTTER_FONT_PX", "MIN_HEIGHT"):
        val = getattr(C, name)
        assert isinstance(val, int), f"{name} doit etre un int, recu {type(val)}"

    for fn_name in ("wrap_label_px", "row_height_single", "row_height_pair"):
        assert callable(getattr(C, fn_name)), f"{fn_name} doit etre appelable"


# ---------------------------------------------------------------------------
# 2. Entrees "barres" du registre -- family in FAMILIES exclut nativement
#    `scatter` (planes/reciprocity) ET `annee` (grammaire overlay existante,
#    pas le contrat gutter) : les DEUX sont hors des dicts LABEL_COL_PX/etc.,
#    lu depuis la VRAIE constante, jamais une liste d'exclusion codee en dur.
# ---------------------------------------------------------------------------
BAR_ENTRIES = [(k, f, b) for k, f, b in _registry.BUILDERS if f in C.FAMILIES]
REGISTERED_FAMILIES = sorted({f for _, f, _ in BAR_ENTRIES})


def _phantom_gutter_trace(fig: go.Figure):
    """La trace-fantome du gutter (P1 : `go.Bar` a x negatif, texte de valeur) --
    identifiee par sa police, seule propriete que le contrat fixe (`textfont.size
    == GUTTER_FONT_PX`) independamment de la forme du builder."""
    for tr in fig.data:
        if (isinstance(tr, go.Bar) and tr.textfont is not None
                and tr.textfont.size == C.GUTTER_FONT_PX):
            return tr
    return None


def _row_count(fig: go.Figure, phantom) -> int:
    for tr in fig.data:
        if isinstance(tr, go.Bar) and tr is not phantom and tr.y is not None:
            return len(set(tr.y))
    raise AssertionError("aucune trace Bar de donnees (hors trace-fantome du gutter)")


def _expected_pitch_and_bar_px(fig: go.Figure, n_rows: int) -> tuple[int, int, str]:
    """Determine simple/paire depuis la HAUTEUR reellement emise plutot que de
    deviner la forme depuis le nombre de traces (plus robuste : row_height_single/
    pair sont les fonctions memes que le builder doit avoir utilisees)."""
    h = fig.layout.height
    single_h, pair_h = C.row_height_single(n_rows), C.row_height_pair(n_rows)
    if h == single_h:
        return C.ROW_PITCH_SINGLE, C.BAR_PX_SINGLE, "single"
    if h == pair_h:
        return C.ROW_PITCH_PAIR, C.BAR_PX_PAIR, "pair"
    raise AssertionError(
        f"hauteur de figure {h} ne correspond ni a row_height_single({n_rows})={single_h} "
        f"ni a row_height_pair({n_rows})={pair_h}"
    )


def _measured_bar_px(fig: go.Figure, phantom, pitch: int) -> float:
    """Epaisseur de barre mesuree, que le builder l'exprime par une largeur
    EXPLICITE par trace (geometrie de paire) ou laisse Plotly la deriver de
    `bargap` (geometrie simple) -- les deux conventions sont couvertes."""
    bar_traces = [tr for tr in fig.data if isinstance(tr, go.Bar) and tr is not phantom]
    widths = {tr.width for tr in bar_traces if tr.width is not None}
    if widths:
        assert len(widths) == 1, f"largeurs de barre incoherentes entre traces : {widths}"
        return next(iter(widths)) * pitch
    bargap = fig.layout.bargap
    assert bargap is not None, "ni largeur explicite ni bargap : impossible de mesurer l'epaisseur"
    return (1.0 - bargap) * pitch


@pytest.mark.parametrize("entry", BAR_ENTRIES, ids=lambda e: e[0])
def test_bar_builder_margin_is_label_plus_gutter_plus_pad(entry) -> None:
    chart_key, family, build_fn = entry
    fig = build_fn()
    expected = C.LABEL_COL_PX[family] + C.GUTTER_COL_PX[family] + C.COL_PAD_PX
    assert fig.layout.margin.l == expected, (
        f"{chart_key} ({family}) : margin.l={fig.layout.margin.l}, attendu {expected}"
    )


@pytest.mark.parametrize("entry", BAR_ENTRIES, ids=lambda e: e[0])
def test_bar_builder_tick_font_is_the_declared_constant(entry) -> None:
    chart_key, _family, build_fn = entry
    fig = build_fn()
    assert fig.layout.yaxis.tickfont.size == C.TICK_FONT_PX, (
        f"{chart_key} : tickfont.size={fig.layout.yaxis.tickfont.size}, attendu {C.TICK_FONT_PX}"
    )


@pytest.mark.parametrize("entry", BAR_ENTRIES, ids=lambda e: e[0])
def test_bar_builder_has_a_gutter_phantom_trace_with_skip_hover(entry) -> None:
    chart_key, _family, build_fn = entry
    fig = build_fn()
    phantom = _phantom_gutter_trace(fig)
    assert phantom is not None, (
        f"{chart_key} : aucune trace-fantome de gutter (textfont.size == GUTTER_FONT_PX) trouvee"
    )
    assert phantom.hoverinfo == "skip", f"{chart_key} : la trace-fantome du gutter doit avoir hoverinfo='skip'"


@pytest.mark.parametrize("entry", BAR_ENTRIES, ids=lambda e: e[0])
def test_bar_builder_never_draws_a_basis_label_as_annotation_text(entry) -> None:
    chart_key, _family, build_fn = entry
    fig = build_fn()
    for ann in fig.layout.annotations:
        assert ann.text not in BASIS_LABELS_FORBIDDEN, (
            f"{chart_key} : annotation = libelle de base {ann.text!r} -- "
            f"la base se nomme une fois dans la legende, jamais en en-tete du graphique (P1)"
        )


@pytest.mark.parametrize("entry", BAR_ENTRIES, ids=lambda e: e[0])
def test_bar_builder_reference_shapes_are_dashed_and_reference_red(entry) -> None:
    chart_key, _family, build_fn = entry
    fig = build_fn()
    for shp in fig.layout.shapes:
        if shp.line is not None and shp.line.dash == "dash":
            assert shp.line.color == REFERENCE_RED, (
                f"{chart_key} : forme pointillee non rouge-reference (couleur={shp.line.color!r}, "
                f"attendu {REFERENCE_RED!r})"
            )


@pytest.mark.parametrize("entry", BAR_ENTRIES, ids=lambda e: e[0])
def test_bar_builder_thickness_matches_the_family_pitch_rule(entry) -> None:
    chart_key, family, build_fn = entry
    fig = build_fn()
    phantom = _phantom_gutter_trace(fig)
    n_rows = _row_count(fig, phantom)
    pitch, bar_px, shape = _expected_pitch_and_bar_px(fig, n_rows)
    measured = _measured_bar_px(fig, phantom, pitch)
    assert measured == pytest.approx(bar_px, abs=0.5), (
        f"{chart_key} ({family}, pas {shape}) : epaisseur mesuree {measured:.1f}px, attendu {bar_px}px"
    )


# ---------------------------------------------------------------------------
# 3. Enveloppe des libelles -- une famille par builder REELLEMENT enregistre
#    (jamais les 6 par defaut : une famille absente du registre n'a pas encore
#    de builder a valider, et charger son univers pour rien coute une lecture
#    parquet). Sources best-effort depuis Streamlit/data (a verifier par
#    S-LIB-A, premier a executer ce fichier pour de vrai, W2) : une colonne
#    qui ne correspond pas fait pytest.skip AVEC le nom attendu dans le
#    message, jamais un echec silencieux ni un crash de collecte.
# ---------------------------------------------------------------------------
def _country_labels() -> list[str] | None:
    csv_path = ROOT / "inputs" / "countries_fr.csv"
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path, keep_default_na=False, na_values=[])
    label_col = next((c for c in df.columns if c.lower() not in {"iso2", "code", "country_code"}), None)
    if label_col is None:
        return None
    return sorted(x for x in df[label_col].unique().tolist() if x)


def _label_universe(family: str) -> list[str] | None:
    try:
        if family in ("champ", "sous_champ", "topic"):
            col = {"champ": "field_name", "sous_champ": "subfield_name", "topic": "topic_name"}[family]
            df = pd.read_parquet(DATA_DIR / "all_topics.parquet", columns=[col])
            return sorted(df[col].dropna().unique().tolist())
        if family == "partenaire":
            df = pd.read_parquet(DATA_DIR / "ul_partners.parquet", columns=["institution_name"])
            return sorted(df["institution_name"].dropna().unique().tolist())
        if family == "labo":
            df = pd.read_parquet(DATA_DIR / "ul_labs.parquet")
            for col in ("nom_complet", "structure_name", "lab_name", "display_name", "name"):
                if col in df.columns:
                    return sorted(df[col].dropna().unique().tolist())
            return None
        if family == "pays":
            return _country_labels()
    except Exception:
        return None
    return None


@pytest.mark.parametrize("family", REGISTERED_FAMILIES)
def test_registered_family_label_universe_wraps_to_at_most_two_lines(family: str) -> None:
    labels = _label_universe(family)
    if not labels:
        pytest.skip(
            f"univers de libelles '{family}' indisponible depuis Streamlit/data a ce stade "
            f"(colonne a verifier par S-LIB-A) -- squelette S-EVAL, W1"
        )
    wrap_px = C.WRAP_PX[family]
    over = [lab for lab in labels if len(C.wrap_label_px(lab, family).split("<br>")) > 2]
    assert not over, (
        f"{family} : {len(over)}/{len(labels)} libelle(s) depassent 2 lignes a "
        f"WRAP_PX['{family}']={wrap_px} : {over[:5]}"
    )


def test_topic_ellipsis_share_is_under_one_percent_of_4516() -> None:
    if "topic" not in REGISTERED_FAMILIES:
        pytest.skip("aucun builder 'topic' encore enregistre -- rien a verifier a ce stade")
    labels = _label_universe("topic")
    if not labels:
        pytest.skip("univers 'topic' indisponible depuis Streamlit/data a ce stade -- squelette S-EVAL, W1")
    assert len(labels) >= 4000, f"l'univers topic doit etre le vrai referentiel (~4516), recu {len(labels)}"
    n_over = sum(1 for lab in labels if any(m in C.wrap_label_px(lab, "topic") for m in ELLIPSIS_MARKERS))
    share = n_over / len(labels)
    assert share < 0.01, f"{n_over}/{len(labels)} topics ({share:.4%}) necessitent une ellipse -- elargir la colonne"


# ---------------------------------------------------------------------------
# 4. VACUITE (P14) -- la RELATION de marge verifiee en §2, prouvee sur une
#    figure synthetique, INDEPENDAMMENT de tout registre : une marge exacte
#    passe, la meme decalee d'1 px echoue.
# ---------------------------------------------------------------------------
def test_vacuity_margin_relation_fails_when_off_by_one_px() -> None:
    family = C.FAMILIES[0]
    expected = C.LABEL_COL_PX[family] + C.GUTTER_COL_PX[family] + C.COL_PAD_PX

    good = go.Figure(layout=go.Layout(margin=dict(l=expected)))
    assert good.layout.margin.l == expected, "la relation doit passer a la marge exacte"

    bad = go.Figure(layout=go.Layout(margin=dict(l=expected - 1)))
    assert bad.layout.margin.l != expected, (
        "une figure synthetique dont margin.l est decalee d'1 px doit faire echouer la MEME relation"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
