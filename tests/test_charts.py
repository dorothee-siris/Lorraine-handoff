# tests/test_charts.py
"""
Le contrat de `Streamlit/lib/charts.py` (S-LIB-A, passe 7a), epingle sur les
DONNEES REELLES de `Streamlit/data/` -- paire CNRS `I1294671590` pour tout ce
qui est de grain paire, via les trames composees une seule fois dans
`tests/_registry.py`.

CE QUE CE FICHIER VERIFIE
  1. enveloppe des libelles : tout l'univers de chaque famille vivante tient
     en <=2 lignes a `WRAP_PX[famille]`, et la part d'ellipses au grain topic
     reste sous 1 % (le plafond que P1 se donne) ;
  2. le plafond d'AFFICHAGE de la famille `partenaire` : il coupe, il marque,
     et il ne touche jamais le nom complet que portent le survol et l'export ;
  3. les formules : `row_height_single/pair`, `margin_left`, le decalage de
     tick M2 (VIZ_SPEC_pass7 §1.3) ;
  4. le gutter : trace-fantome presente, `hoverinfo == "skip"`, son texte EGAL
     a `fmt_int(valeur)` ligne par ligne, plancher de plage == son propre x ;
  5. la reference : rouge-reference, pointillee, une forme PAR LIGNE quand
     elle varie, un `add_vline` quand elle est constante ;
  6. le canal de prudence : encre rouge + dague sur le texte, remplissage de
     barre INCHANGE ;
  7. l'ordre des lignes : le constructeur ne retrie JAMAIS ;
  8. `balance_bars` : les bases et longueurs des trois segments reconstruisent
     `vol_ul_only` / `vol_joint` / `vol_partner_only`, la colonne liee porte
     une entree par ligne, un TIRET (jamais un lien) sous le plancher, et
     l'axe x n'a ni tick ni grille (§1.4) ;
  9. les deux plans : `tint()` applique SI ET SEULEMENT SI `artifact_flag` ;
 10. le nuage site : bascule `Scattergl` au-dela de 2 000 lignes, marqueur
     carre si et seulement si la part propre est plafonnee ;
 11. l'hygiene du module : aucun litteral `#RRGGBB`, aucun specificateur de
     format dans une accolade plotly.

VACUITE (P14) : CHAQUE verification est suivie d'une mutation EN MEMOIRE (ou
sur une copie) qui doit faire echouer la verification identique. Une epingle
qui ne peut pas echouer est du theatre.

    .venv-pinned\\Scripts\\python -m pytest tests\\test_charts.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
DATA_DIR = STREAMLIT_DIR / "data"
CHARTS_FILE = STREAMLIT_DIR / "lib" / "charts.py"

# F-SYSMOD (tests/conftest.py) : deux paquets nommes `lib` coexistent dans ce depot ;
# le basculement doit avoir lieu AVANT `import lib.charts`, au niveau MODULE (les
# decorateurs parametrize lisent les constantes).
#
# FIX-2 (inspection D1) : la restauration est IMMEDIATE, pas differee a
# `teardown_module`. Un `sys.modules['lib']` laisse pointe sur `Streamlit/lib`
# pendant toute la COLLECTE empoisonne les fichiers qui ont besoin du `lib` RACINE
# (`test_contract_tables.py`, `test_invariants.py`, `test_pass6_data.py`,
# `test_pass7_data.py` -> ModuleNotFoundError lib.snapshot) des que la suite entiere
# est collectee : leur import de module tourne AVANT que le teardown de ce fichier
# n'ait lieu. Les OBJETS deja importes (C, H, HV) restent lies dans cet espace de
# noms -- seul `sys.modules` est rendu. Meme correctif que S-EVAL a applique a
# `tests/test_chart_layout.py`.
from conftest import restore_lib, swap_lib_to_streamlit  # noqa: E402

_saved_lib_modules: dict = swap_lib_to_streamlit()
import lib.charts as C    # noqa: E402
import lib.helpers as H   # noqa: E402
import lib.hover as HV    # noqa: E402
restore_lib(_saved_lib_modules)  # restauree IMMEDIATEMENT -- pas de teardown_module differe

import _registry as R     # noqa: E402  (tests/ meme -- pas de paquet, import nu ;
#                            n'importe `lib` que dans le corps de ses propres callables)

# ... et le basculement est REFAIT pour la duree du RUN de ce fichier seulement : les
# composeurs de trames appeles nus par ces tests (`R.frame_*`) font `from lib import
# hover` dans leur corps, contrairement aux `R.build_*` qui basculent eux-memes.
_saved_for_run: dict = {}


def setup_module(_module) -> None:
    global _saved_for_run
    _saved_for_run = swap_lib_to_streamlit()


def teardown_module(_module) -> None:
    restore_lib(_saved_for_run)


HEX_RX = re.compile(r"#[0-9A-Fa-f]{6}\b")
FORMAT_SPEC_RX = re.compile(r"%\{[^}]*:[^}]*\}")
LIVE_FAMILIES = ("champ", "sous_champ", "labo", "labo_court", "pays", "partenaire")
NARROW_VIEWPORT_PX = 390   # le point de rupture le plus etroit des regles de maison


# ===========================================================================
# Aides -- univers de libelles et trames synthetiques minimales
# ===========================================================================
def _label_universe(family: str) -> list[str]:
    if family in ("champ", "sous_champ", "topic"):
        col = {"champ": "field_name", "sous_champ": "subfield_name",
               "topic": "topic_name"}[family]
        return sorted(pd.read_parquet(DATA_DIR / "all_topics.parquet",
                                      columns=[col])[col].dropna().unique().tolist())
    if family == "partenaire":
        return sorted(pd.read_parquet(DATA_DIR / "ul_partners.parquet",
                                      columns=["institution_name"]
                                      )["institution_name"].dropna().unique().tolist())
    if family == "labo":
        df = pd.read_parquet(DATA_DIR / "ul_labs.parquet",
                             columns=["Structure name", "nom_complet"])
        return sorted(set(df["Structure name"].dropna()) | set(df["nom_complet"].dropna()))
    if family == "labo_court":
        # l'univers REELLEMENT dessine par zoom_portage : les acronymes de
        # ptn_labs.lab_name, plus la ligne d'agregat que le graphique ajoute.
        names = pd.read_parquet(DATA_DIR / "ptn_labs.parquet", columns=["lab_name"])
        return sorted(set(names["lab_name"].dropna()) | {"Autres"})
    if family == "pays":
        csv = pd.read_csv(ROOT / "inputs" / "countries_fr.csv",
                          keep_default_na=False, na_values=[])
        col = next(c for c in csv.columns
                   if c.lower() not in {"iso2", "code", "country_code"})
        return sorted(x for x in csv[col].unique().tolist() if x)
    raise AssertionError(family)


def _bars_frame(n: int = 5, *, caution: bool = False) -> pd.DataFrame:
    """Une trame minimale pour les verifications de MECANISME (le gutter, la
    reference, le canal de prudence) : les verifications de DONNEES tournent
    sur les trames reelles de `tests/_registry.py`."""
    d = pd.DataFrame({
        "node_name": ["Chemistry", "Physics and Astronomy", "Medicine",
                      "Mathematics", "Engineering"][:n],
        "co_works": [1234.0, 987.0, 654.0, 321.0, 42.0][:n],
        "isite": [200.0, 150.0, 100.0, 50.0, 5.0][:n],
        "hover": ["<b>x</b>"] * n,
    })
    d["flagged"] = [caution and i == 0 for i in range(n)]
    return d


def _site_frame(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    return pd.DataFrame({
        "partner_id": ["I{0}".format(i) for i in range(n)],
        "display_name": ["P{0}".format(i) for i in range(n)],
        "share_ul": rng.uniform(0.01, 5.0, n),
        "share_p": rng.uniform(0.01, 5.0, n),
        "share_p_capped_flag": [i % 3 == 0 for i in range(n)],
        "co_works_full": rng.integers(1, 500, n).astype(float),
        "hover": ["<b>x</b>"] * n,
    })


# ===========================================================================
# 1. Enveloppe des libelles
# ===========================================================================
def _offenders(labels, family: str) -> tuple[list[str], list[str]]:
    """(au-dela de 2 lignes, tombes sur l'ellipse). `wrap_label_px` ne peut
    JAMAIS rendre 3 lignes par construction (il fusionne, puis ellipse) : la
    revendication de largeur d'une colonne est donc « zero repli sur
    l'ellipse », et c'est ce compte-la qui peut echouer. La famille
    `partenaire` est exclue de la 2e liste : son ellipse est un plafond
    d'AFFICHAGE assume (28,3 % des noms), pas un depassement de colonne."""
    over = [lab for lab in labels if len(C.wrap_label_px(lab, family).split("<br>")) > 2]
    if family == "partenaire":
        return over, []
    cut = [lab for lab in labels if C.ELLIPSIS in C.wrap_label_px(lab, family)]
    return over, cut


@pytest.mark.parametrize("family", LIVE_FAMILIES)
def test_label_universe_wraps_to_at_most_two_lines(family: str) -> None:
    labels = _label_universe(family)
    assert len(labels) > 20, "univers {0} suspect : {1} libelles".format(family, len(labels))
    over, cut = _offenders(labels, family)
    assert not over, "{0} : {1}/{2} libelles depassent 2 lignes a {3} px -- {4}".format(
        family, len(over), len(labels), C.WRAP_PX[family], over[:3])
    assert not cut, "{0} : {1}/{2} libelles tombent sur l'ellipse a {3} px -- {4}".format(
        family, len(cut), len(labels), C.WRAP_PX[family], cut[:3])


@pytest.mark.parametrize("family", ("champ", "sous_champ", "labo", "pays"))
def test_vacuity_wrap_fails_when_the_column_is_narrowed(family: str) -> None:
    """La MEME verification, la colonne rabotee en memoire : elle doit casser
    pour CHAQUE famille -- sinon le point fixe mesure ne prouve rien."""
    labels = _label_universe(family)
    saved = C.WRAP_PX[family]
    try:
        C.WRAP_PX[family] = 40
        _over, cut = _offenders(labels, family)
        assert cut, "a 40 px, {0} doit tomber sur l'ellipse".format(family)
    finally:
        C.WRAP_PX[family] = saved
    assert _offenders(labels, family)[1] == []


def test_topic_ellipsis_share_is_under_one_percent() -> None:
    labels = _label_universe("topic")
    assert len(labels) >= 4000, len(labels)
    n_over = sum(1 for lab in labels if C.ELLIPSIS in C.wrap_label_px(lab, "topic"))
    assert n_over / len(labels) < 0.01, "{0}/{1} topics ellipses".format(n_over, len(labels))


def test_vacuity_ellipsis_share_fails_at_a_narrow_column() -> None:
    labels = _label_universe("topic")
    saved = C.WRAP_PX["topic"]
    try:
        C.WRAP_PX["topic"] = 30
        n_over = sum(1 for lab in labels if C.ELLIPSIS in C.wrap_label_px(lab, "topic"))
        assert n_over / len(labels) >= 0.01, "a 30 px la part d'ellipses doit exploser"
    finally:
        C.WRAP_PX["topic"] = saved


# ===========================================================================
# 2. Le plafond d'AFFICHAGE de la famille `partenaire`
# ===========================================================================
def test_partner_cap_is_display_only_and_marks_what_it_shortens() -> None:
    long_name = ("Centre National de la Recherche Scientifique et Technique "
                 "de Nancy Lorraine")
    shown = C.wrap_label_px(long_name, "partenaire")
    assert C.ELLIPSIS in shown, "un nom raccourci doit porter l'ellipse"
    plain = shown.replace("<br>", " ")
    assert len(plain) <= C.PARTNER_LABEL_MAX_CHARS + len(C.ELLIPSIS) + 1, plain
    short = "CNRS"
    assert C.ELLIPSIS not in C.wrap_label_px(short, "partenaire"), (
        "un nom qui tient ne doit JAMAIS porter l'ellipse")


def test_vacuity_partner_cap_fails_when_the_cap_is_lifted() -> None:
    """Le plafond est teste SUR LUI-MEME (`_display_cap`), pas a travers
    l'enveloppe : au-dela de ~2 lignes de colonne, `wrap_label_px` ellipse de
    toute facon, et le test ne saurait plus lequel des deux mecanismes a
    marque le libelle."""
    long_name = "Centre National de la Recherche Scientifique et Technique de Nancy"
    saved = C.PARTNER_LABEL_MAX_CHARS
    assert C._display_cap(long_name).endswith(C.ELLIPSIS)
    assert C._display_cap(long_name) != long_name
    try:
        C.PARTNER_LABEL_MAX_CHARS = 500
        assert C._display_cap(long_name) == long_name, (
            "plafond leve : le nom ressort INTACT -- donc la verification "
            "precedente mord bien")
        assert C.ELLIPSIS not in C._display_cap(long_name)
    finally:
        C.PARTNER_LABEL_MAX_CHARS = saved


# ===========================================================================
# 3. Les formules de hauteur, de marge et de decalage de tick
# ===========================================================================
def test_height_margin_and_standoff_formulas() -> None:
    for n in (1, 6, 26, 30):
        assert C.row_height_single(n) == max(C.MIN_HEIGHT, 60 + n * C.ROW_PITCH_SINGLE + 46)
        assert C.row_height_pair(n) == max(C.MIN_HEIGHT, 60 + n * C.ROW_PITCH_PAIR + 46)
    for fam in C.FAMILIES:
        assert C.margin_left(fam) == C.LABEL_COL_PX[fam] + C.GUTTER_COL_PX[fam] + C.COL_PAD_PX
        assert C.TICKLABEL_STANDOFF_PX[fam] == C.GUTTER_COL_PX[fam] + C.COL_PAD_PX


def test_vacuity_margin_formula_fails_when_the_gutter_column_shrinks() -> None:
    fam = C.FAMILIES[0]
    expected = C.margin_left(fam)
    saved = C.GUTTER_COL_PX[fam]
    try:
        C.GUTTER_COL_PX[fam] = saved - 1
        assert C.margin_left(fam) != expected, (
            "une colonne de gutter rabotee d'1 px doit changer la marge gauche")
    finally:
        C.GUTTER_COL_PX[fam] = saved


def test_every_bar_figure_sets_the_M2_ticklabel_standoff() -> None:
    """VIZ_SPEC_pass7 §1.3 : porte litteralement, le mecanisme BenchUp
    chevauche les ticks de ~37 px. `ticklabelstandoff` est l'attribut qui
    l'evite, et un retour a une version de plotly qui l'ignore
    REINTRODUIRAIT silencieusement la collision."""
    for key, family, build in R.BUILDERS:
        if family not in C.FAMILIES:
            continue
        fig = build()
        assert fig.layout.yaxis.ticklabelstandoff == C.TICKLABEL_STANDOFF_PX[family], (
            "{0} : standoff {1}, attendu {2}".format(
                key, fig.layout.yaxis.ticklabelstandoff, C.TICKLABEL_STANDOFF_PX[family]))


def test_vacuity_standoff_zero_puts_the_ticks_back_over_the_gutter() -> None:
    d = _bars_frame()
    fig = C.bars_with_gutter(d, family="champ", label_col="node_name",
                             value_col="co_works", color=H.UL_COLOR)
    assert fig.layout.yaxis.ticklabelstandoff == C.TICKLABEL_STANDOFF_PX["champ"]
    fig.update_yaxes(ticklabelstandoff=0)
    assert fig.layout.yaxis.ticklabelstandoff != C.TICKLABEL_STANDOFF_PX["champ"], (
        "un standoff remis a zero doit faire echouer la MEME verification (M1)")


# ===========================================================================
# 3 bis. `labo_court` -- la 7e famille (suivi 1) : la colonne des ACRONYMES
# ===========================================================================
def test_labo_court_exists_in_every_family_dict() -> None:
    assert "labo_court" in C.FAMILIES
    for name in ("LABEL_COL_PX", "WRAP_PX", "GUTTER_COL_PX", "TICKLABEL_STANDOFF_PX"):
        d = getattr(C, name)
        assert "labo_court" in d, "{0} n'a pas d'entree labo_court".format(name)
        assert isinstance(d["labo_court"], int)
    assert C.LABEL_COL_PX["labo_court"] < C.LABEL_COL_PX["labo"], (
        "la colonne des acronymes doit etre PLUS ETROITE que celle des noms complets")
    assert C.margin_left("labo_court") == (C.LABEL_COL_PX["labo_court"]
                                           + C.GUTTER_COL_PX["labo_court"] + C.COL_PAD_PX)


def test_labo_court_column_is_the_fixed_point_of_the_acronym_universe() -> None:
    """« Point fixe » au sens de VIZ_SPEC_pass7 §1.1 : la PLUS PETITE largeur a
    laquelle tout l'univers tient en <=2 lignes sans repli sur l'ellipse. La
    tenue est verifiee a la largeur livree ; la MINIMALITE l'est en descendant
    d'un cran de 5 px (le pas d'arrondi de §1.1), ou la propriete doit casser
    -- sinon la colonne est simplement large, pas resolue."""
    labels = _label_universe("labo_court")
    assert len(labels) > 50, len(labels)
    _over, cut = _offenders(labels, "labo_court")
    assert not cut and not _over, cut[:3]
    widest = max(C.text_width_px(line)
                 for lab in labels
                 for line in C.wrap_label_px(lab, "labo_court").split("<br>"))
    assert widest <= C.WRAP_PX["labo_court"], (
        "plus large ligne rendue {0:.1f} px > colonne {1} px".format(
            widest, C.WRAP_PX["labo_court"]))
    assert widest > C.WRAP_PX["labo_court"] - 5, (
        "la colonne depasse le point fixe de plus d'un cran d'arrondi : "
        "{0:.1f} px tiennent dans {1} px".format(widest, C.WRAP_PX["labo_court"]))


def test_vacuity_labo_court_fixed_point_breaks_one_step_down() -> None:
    labels = _label_universe("labo_court")
    saved = C.WRAP_PX["labo_court"]
    try:
        C.WRAP_PX["labo_court"] = saved - 5
        _over, cut = _offenders(labels, "labo_court")
        widest = max(C.text_width_px(line)
                     for lab in labels
                     for line in C.wrap_label_px(lab, "labo_court").split("<br>"))
        assert cut or widest > C.WRAP_PX["labo_court"], (
            "un cran de 5 px en moins doit casser la tenue -- sinon le point fixe "
            "n'est pas minimal")
    finally:
        C.WRAP_PX["labo_court"] = saved


def test_labo_court_leaves_a_real_plot_area_at_the_narrow_breakpoint() -> None:
    """La raison d'etre de la famille : `margin_left("labo") = 393 px` DEPASSE un
    viewport de 390 px, donc la zone de trace y est de largeur negative et les
    barres disparaissent (mesure DOM, premiere passe de rendu). `labo_court`
    doit y laisser une zone de trace REELLE."""
    plot = NARROW_VIEWPORT_PX - C.margin_left("labo_court") - C.BASE_MARGIN_R
    assert plot > 0, "zone de trace {0} px a {1} px de viewport".format(
        plot, NARROW_VIEWPORT_PX)
    assert plot >= C.BUBBLE_MAX_PX, (
        "une zone de trace plus etroite que la plus grosse marque de l'app "
        "n'est pas un instrument de lecture")


def test_vacuity_the_full_name_family_does_NOT_fit_the_narrow_breakpoint() -> None:
    """La MEME arithmetique sur `labo` : elle doit echouer, sinon la 7e famille
    ne servait a rien."""
    plot = NARROW_VIEWPORT_PX - C.margin_left("labo") - C.BASE_MARGIN_R
    assert plot <= 0, (
        "labo laisse {0} px de trace a {1} px : la 7e famille serait sans objet".format(
            plot, NARROW_VIEWPORT_PX))


def test_zoom_portage_is_registered_under_labo_court() -> None:
    families = {key: fam for key, fam, _ in R.BUILDERS}
    assert families["zoom_portage"] == "labo_court", (
        "zoom_portage dessine des acronymes : il doit etre enregistre en labo_court")
    fig = R.build_zoom_portage()
    assert fig.layout.margin.l == C.margin_left("labo_court")
    assert fig.layout.yaxis.ticklabelstandoff == C.TICKLABEL_STANDOFF_PX["labo_court"]


# ===========================================================================
# 4. Le gutter
# ===========================================================================
def _phantom(fig: go.Figure):
    for tr in fig.data:
        if (isinstance(tr, go.Bar) and tr.textfont is not None
                and tr.textfont.size == C.GUTTER_FONT_PX):
            return tr
    return None


def test_gutter_phantom_text_equals_fmt_int_row_by_row() -> None:
    d = R.frame_field_companion()
    fig = R.build_zoom_field_companion()
    ph = _phantom(fig)
    assert ph is not None, "aucune trace-fantome de gutter"
    assert ph.hoverinfo == "skip"
    assert ph.constraintext == "none" and ph.textposition == "outside"
    assert ph.cliponaxis is False
    assert list(ph.text) == [HV.fmt_int(v) for v in d["co_works"]], (
        "le texte du gutter doit egaler fmt_int(valeur) LIGNE PAR LIGNE")
    assert float(fig.layout.xaxis.range[0]) == pytest.approx(float(ph.x[0])), (
        "le plancher de plage doit etre le x de la fantome (mecanisme M2)")


def test_vacuity_gutter_text_fails_when_one_value_moves() -> None:
    d = R.frame_field_companion()
    expected = [HV.fmt_int(v) for v in d["co_works"]]
    mutated = d.copy()
    mutated.loc[0, "co_works"] = float(mutated.loc[0, "co_works"]) + 1.0
    fig = C.bars_with_gutter(mutated, family="champ", label_col="node_name",
                             value_col="co_works", color=H.UL_COLOR)
    assert list(_phantom(fig).text) != expected, (
        "une valeur decalee d'une unite doit faire echouer l'egalite ligne par ligne")


def test_gutter_can_be_switched_off_by_the_caller() -> None:
    """`gutter=False` : l'idiome BenchUp pour un panneau etroit -- la valeur
    survit dans le survol et dans l'export."""
    d = _bars_frame()
    off = C.bars_with_gutter(d, family="champ", label_col="node_name",
                             value_col="co_works", color=H.UL_COLOR, gutter=False)
    assert _phantom(off) is None, "gutter=False ne doit poser AUCUNE fantome"
    assert float(off.layout.xaxis.range[0]) == 0.0
    on = C.bars_with_gutter(d, family="champ", label_col="node_name",
                            value_col="co_works", color=H.UL_COLOR)
    assert _phantom(on) is not None, "par defaut la fantome doit etre la"


# ===========================================================================
# 5. La reference
# ===========================================================================
def test_constant_reference_is_one_dashed_red_line() -> None:
    d = _bars_frame()
    fig = C.bars_with_gutter(d, family="champ", label_col="node_name",
                             value_col="co_works", color=H.UL_COLOR, reference=500.0)
    dashed = [s for s in fig.layout.shapes if s.line is not None and s.line.dash == "dash"]
    assert len(dashed) == 1, "une reference constante = UNE ligne pleine hauteur"
    assert dashed[0].line.color == H.REFERENCE_RED
    assert dashed[0].line.width == C.REFERENCE_WIDTH_PX


def test_varying_reference_is_one_shape_per_row_on_its_own_band() -> None:
    d = _bars_frame()
    refs = [100.0, 200.0, 300.0, 400.0, 500.0]
    fig = C.bars_with_gutter(d, family="champ", label_col="node_name",
                             value_col="co_works", color=H.UL_COLOR, reference=refs)
    dashed = [s for s in fig.layout.shapes if s.line is not None and s.line.dash == "dash"]
    assert len(dashed) == len(refs), "une reference qui varie = UNE forme par ligne"
    for i, shp in enumerate(dashed):
        assert shp.x0 == shp.x1 == refs[i]
        assert (shp.y0, shp.y1) == (i - 0.5, i + 0.5), (
            "la reference d'une ligne ne doit couvrir QUE sa bande")


def test_vacuity_reference_colour_check_fails_on_another_hue() -> None:
    d = _bars_frame()
    fig = C.bars_with_gutter(d, family="champ", label_col="node_name",
                             value_col="co_works", color=H.UL_COLOR, reference=500.0)
    dashed = [s for s in fig.layout.shapes if s.line is not None and s.line.dash == "dash"]
    assert dashed[0].line.color == H.REFERENCE_RED
    fig.layout.shapes[0].line.color = H.NEUTRAL_GREY
    assert fig.layout.shapes[0].line.color != H.REFERENCE_RED, (
        "une reference repeinte en gris doit faire echouer la MEME verification")


# ===========================================================================
# 6. Le canal de prudence
# ===========================================================================
def test_caution_is_ink_plus_dagger_and_never_a_fill() -> None:
    d = _bars_frame(caution=True)
    fig = C.bars_with_gutter(d, family="champ", label_col="node_name",
                             value_col="co_works", color=H.UL_COLOR,
                             caution_col="flagged")
    ph = _phantom(fig)
    inks = list(ph.textfont.color)
    assert inks[0] == H.REFERENCE_RED, "la ligne signalee passe en encre de prudence"
    assert all(c != H.REFERENCE_RED for c in inks[1:]), "les autres lignes restent en encre secondaire"
    assert ph.text[0].endswith(C.DAGGER), "la dague est conservee"
    bars = [t for t in fig.data if isinstance(t, go.Bar) and t is not ph]
    assert bars[0].marker.color == H.UL_COLOR, (
        "le remplissage de la barre reste INCHANGE (jamais une hachure, jamais un gris)")


def test_vacuity_caution_fails_without_the_flag_column() -> None:
    d = _bars_frame(caution=True)
    fig = C.bars_with_gutter(d.drop(columns=["flagged"]), family="champ",
                             label_col="node_name", value_col="co_works",
                             color=H.UL_COLOR, caution_col="flagged")
    inks = list(_phantom(fig).textfont.color)
    assert all(c != H.REFERENCE_RED for c in inks), (
        "sans colonne de drapeau, aucune encre de prudence -- la verification mord donc bien")
    assert not any(t.endswith(C.DAGGER) for t in _phantom(fig).text)


# ===========================================================================
# 7. L'ordre des lignes
# ===========================================================================
def test_builder_never_resorts_the_frame() -> None:
    d = R.frame_field_companion()
    shuffled = d.iloc[::-1].reset_index(drop=True)
    fig = C.bars_with_gutter(shuffled, family="champ", label_col="node_name",
                             value_col="co_works", color=H.UL_COLOR)
    drawn = [t.replace("<br>", " ") for t in fig.layout.yaxis.ticktext]
    expected = [C.wrap_label_px(v, "champ").replace("<br>", " ") for v in shuffled["node_name"]]
    assert drawn == expected, "l'ordre dessine doit etre celui de la trame, retourne inclus"


def test_vacuity_order_check_fails_against_the_other_order() -> None:
    d = R.frame_field_companion()
    fig = C.bars_with_gutter(d, family="champ", label_col="node_name",
                             value_col="co_works", color=H.UL_COLOR)
    drawn = list(fig.layout.yaxis.ticktext)
    reversed_expected = [C.wrap_label_px(v, "champ") for v in d["node_name"].iloc[::-1]]
    assert drawn != reversed_expected, (
        "l'ordre dessine ne peut pas satisfaire les DEUX ordres a la fois")


# ===========================================================================
# 8. balance_bars
# ===========================================================================
def test_balance_segments_reconstruct_the_three_volumes() -> None:
    d = R.frame_balance("volume", "field")
    fig = R.build_balance_volume()
    ul, joint, partner = fig.data[0], fig.data[1], fig.data[2]
    half = d["vol_joint"].to_numpy(dtype=float) / 2.0

    assert list(joint.x) == pytest.approx(d["vol_joint"].tolist()), "longueur du conjoint"
    assert list(joint.base) == pytest.approx((-half).tolist()), "le conjoint est CENTRE sur zero"
    assert list(ul.x) == pytest.approx(d["vol_ul_only"].tolist()), "longueur UL seule"
    assert list(ul.base) == pytest.approx((-(half + d["vol_ul_only"].to_numpy(dtype=float))).tolist()), (
        "UL seule s'etend a GAUCHE depuis -j/2")
    assert list(partner.x) == pytest.approx(d["vol_partner_only"].tolist()), "longueur partenaire seul"
    assert list(partner.base) == pytest.approx(half.tolist()), (
        "partenaire seul s'etend a DROITE depuis +j/2")
    assert ul.marker.color == H.UL_COLOR
    assert joint.marker.color == H.JOINT_COLOR
    assert partner.marker.color == H.PARTNER_COLOR


def test_vacuity_balance_segments_fail_when_one_volume_moves() -> None:
    d = R.frame_balance("volume", "field").copy()
    expected = d["vol_joint"].tolist()
    d.loc[0, "vol_joint"] = float(d.loc[0, "vol_joint"]) + 7.0
    fig = C.balance_bars(d, mode="volume", level="champ", partner_name="X")
    assert list(fig.data[1].x) != pytest.approx(expected), (
        "un volume conjoint decale doit faire echouer la reconstruction")


def test_balance_gutter_carries_the_combined_quantity_per_mode() -> None:
    """§1.2, lu strictement : volume -> les trois volumes sommes ; phares ->
    phares UL + phares conjoints ; fwci -> le nombre de travaux conjoints sur
    lequel repose la mediane (une mediane n'a pas de « combine »)."""
    def stripped(fig):
        return [t.replace(" " + C.DAGGER, "") for t in _phantom(fig).text]

    for mode, level, combine in (
        ("volume", "field", lambda d: d["vol_ul_only"] + d["vol_joint"] + d["vol_partner_only"]),
        ("phares", "subfield", lambda d: d["n_phares_ul"] + d["n_phares_joint"]),
        ("fwci", "field", lambda d: d["n_fwci_joint"]),
    ):
        d = R.frame_balance(mode, level)
        fig = C.balance_bars(d, mode=mode,
                             level="champ" if level == "field" else "sous_champ",
                             partner_name="X")
        assert stripped(fig) == [HV.fmt_int(v) for v in combine(d)], (
            "mode {0} : le gutter doit porter la valeur COMBINEE de la quantite "
            "montree".format(mode))


def test_vacuity_balance_gutter_fails_on_the_wrong_combination() -> None:
    d = R.frame_balance("volume", "field")
    fig = R.build_balance_volume()
    stripped = [t.replace(" " + C.DAGGER, "") for t in _phantom(fig).text]
    assert stripped != [HV.fmt_int(v) for v in d["vol_joint"]], (
        "le conjoint SEUL ne peut pas satisfaire la meme egalite : le gutter "
        "porte bien la somme des trois")


def test_balance_link_column_has_one_entry_per_row_and_a_dash_under_the_floor() -> None:
    d = R.frame_balance("volume", "field")
    fig = R.build_balance_volume()
    ticktext = list(fig.layout.yaxis2.ticktext)
    assert len(ticktext) == len(d), "une entree de colonne liee par ligne"
    for i, under in enumerate(d["under_floor"].tolist()):
        if under:
            assert ticktext[i] == C.DASH_MARK, (
                "sous le plancher : un TIRET, jamais un compte, jamais un lien")
        else:
            assert ticktext[i].startswith("<a href="), "au-dessus du plancher : un lien"
            assert HV.fmt_int(d["vol_joint"].iloc[i]) in ticktext[i]
    assert fig.layout.yaxis2.side == "right" and fig.layout.yaxis2.overlaying == "y"
    assert fig.layout.yaxis2.title.text is None, (
        "un title_text sur yaxis2 se rend PIVOTE au milieu du bord droit et "
        "chevauche les liens -- constate en rendant (1280 px)")
    assert C.LINK_COL_HEADER in {a.text for a in fig.layout.annotations}, (
        "l'en-tete de la colonne liee est une annotation en coordonnees papier")


def test_vacuity_link_column_fails_when_a_row_is_forced_under_the_floor() -> None:
    d = R.frame_balance("volume", "field").copy()
    assert not bool(d["under_floor"].iloc[0]), "la 1re ligne doit etre au-dessus du plancher"
    d.loc[0, "under_floor"] = True
    fig = C.balance_bars(d, mode="volume", level="champ", partner_name="X")
    assert fig.layout.yaxis2.ticktext[0] == C.DASH_MARK, (
        "une ligne forcee sous le plancher doit perdre son lien")


def test_balance_mirror_has_no_x_ticks_and_only_a_zero_line() -> None:
    fig = R.build_balance_volume()
    assert fig.layout.xaxis.showticklabels is False, "§1.4 : aucun libelle de tick x"
    assert fig.layout.xaxis.showgrid is False, "§1.4 : aucune grille x"
    assert fig.layout.xaxis.zeroline is True, "§1.4 : la ligne zero est l'epine du miroir"
    assert fig.layout.xaxis.zerolinecolor == C.ZERO_LINE_COLOR
    assert fig.layout.margin.b == C.MIRROR_MARGIN_B


def test_balance_fwci_mode_draws_a_parity_reference_per_row() -> None:
    d = R.frame_balance("fwci", "field")
    fig = R.build_balance_fwci()
    dashed = [s for s in fig.layout.shapes if s.line is not None and s.line.dash == "dash"]
    assert len(dashed) == len(d), "un tick de parite PAR LIGNE en mode fwci"
    assert all(s.line.color == H.REFERENCE_RED for s in dashed)
    assert all(s.x0 == s.x1 == C.FWCI_REFERENCE for s in dashed)
    volume = R.build_balance_volume()
    assert not [s for s in volume.layout.shapes
                if s.line is not None and s.line.dash == "dash"], (
        "le mode volume n'a AUCUNE reference : la parite n'y veut rien dire")


def test_balance_refuses_an_unknown_mode_or_level() -> None:
    d = R.frame_balance("volume", "field")
    with pytest.raises(ValueError):
        C.balance_bars(d, mode="ratio", level="champ", partner_name="X")
    with pytest.raises(ValueError):
        C.balance_bars(d, mode="volume", level="topic", partner_name="X")


# ===========================================================================
# 9. Les deux plans -- teinte SI ET SEULEMENT SI artifact_flag
# ===========================================================================
@pytest.mark.parametrize("build,frame", [
    ("fig_plane_impact", "frame_plane_impact"),
    ("fig_plane_frontier", "frame_plane_frontier"),
])
def test_plane_tint_is_applied_iff_artifact_flag(build: str, frame: str) -> None:
    d = getattr(R, frame)()
    fig = getattr(C, build)(d)
    fills = list(fig.data[0].marker.color)
    rings = list(fig.data[0].marker.line.color)
    widths = list(fig.data[0].marker.line.width)
    for i, flag in enumerate(d["artifact_flag"].tolist()):
        hue = H.get_domain_color(d["domain_id"].iloc[i])
        assert rings[i] == hue, "l'anneau garde TOUJOURS la teinte de domaine non teintee"
        if flag:
            assert fills[i] == H.tint(hue) and widths[i] == C.OUTLINE_WIDTH
        else:
            assert fills[i] == hue and widths[i] == C.HAIRLINE_PX


@pytest.mark.parametrize("build,frame", [
    ("fig_plane_impact", "frame_plane_impact"),
    ("fig_plane_frontier", "frame_plane_frontier"),
])
def test_vacuity_plane_tint_fails_when_a_flag_is_flipped(build: str, frame: str) -> None:
    d = getattr(R, frame)().copy()
    hue = H.get_domain_color(d["domain_id"].iloc[0])
    before = list(getattr(C, build)(d).data[0].marker.color)[0]
    d.loc[0, "artifact_flag"] = not bool(d["artifact_flag"].iloc[0])
    after = list(getattr(C, build)(d).data[0].marker.color)[0]
    assert before != after, "un drapeau retourne doit changer le remplissage de la marque"
    assert H.tint(hue) in (before, after) and hue in (before, after)


def test_frontier_plane_origin_is_not_the_reference_red() -> None:
    fig = R.build_zoom_plane_frontier()
    zero_lines = [s for s in fig.layout.shapes
                  if s.line is not None and s.line.width == C.QUADRANT_ORIGIN_PX]
    assert len(zero_lines) == 2, "deux lignes 0/0 : une origine, pas une reference"
    assert all(s.line.color == C.ZERO_LINE_COLOR for s in zero_lines)
    assert all(s.line.color != H.REFERENCE_RED for s in zero_lines)
    labels = {a.text for a in fig.layout.annotations}
    assert set(C.QUADRANT_LABELS) <= labels, "les quatre quadrants sont libelles"


def test_impact_plane_has_one_constant_fwci_parity_reference() -> None:
    fig = R.build_zoom_plane_impact()
    dashed = [s for s in fig.layout.shapes if s.line is not None and s.line.dash == "dash"]
    assert len(dashed) == 1 and dashed[0].line.color == H.REFERENCE_RED
    assert dashed[0].y0 == dashed[0].y1 == C.FWCI_REFERENCE
    assert fig.layout.xaxis.type == "log", "l'axe des co-publications est logarithmique"


def test_plane_axis_padding_is_plane_pad_frac_per_side() -> None:
    fig = R.build_zoom_plane_frontier()
    d = R.frame_plane_frontier()
    x = pd.to_numeric(d["expansion"], errors="coerce").to_numpy(dtype=float)
    span = float(np.nanmax(x) - np.nanmin(x))
    lo, hi = [float(v) for v in fig.layout.xaxis.range]
    assert lo == pytest.approx(float(np.nanmin(x)) - span * C.PLANE_PAD_FRAC)
    assert hi == pytest.approx(float(np.nanmax(x)) + span * C.PLANE_PAD_FRAC)


def test_vacuity_padding_fails_at_another_fraction() -> None:
    d = R.frame_plane_frontier()
    x = pd.to_numeric(d["expansion"], errors="coerce").to_numpy(dtype=float)
    span = float(np.nanmax(x) - np.nanmin(x))
    saved = C.PLANE_PAD_FRAC
    try:
        C.PLANE_PAD_FRAC = 0.16
        lo = float(C.fig_plane_frontier(d).layout.xaxis.range[0])
        assert lo != pytest.approx(float(np.nanmin(x)) - span * saved), (
            "a 16 % la MEME verification a 8 % doit echouer")
    finally:
        C.PLANE_PAD_FRAC = saved


# ===========================================================================
# 10. Le nuage site
# ===========================================================================
def test_site_scatter_switches_to_scattergl_above_two_thousand_rows() -> None:
    assert isinstance(C.site_reciprocity_scatter(_site_frame(2000), floor=20).data[0],
                      go.Scatter), "2 000 marques restent en SVG"
    fig = C.site_reciprocity_scatter(_site_frame(2001), floor=20)
    assert isinstance(fig.data[0], go.Scattergl), "2 001 marques basculent en Scattergl"


def test_vacuity_gl_switch_fails_when_the_threshold_moves() -> None:
    saved = C.GL_SWITCH_ROWS
    try:
        C.GL_SWITCH_ROWS = 10
        assert isinstance(C.site_reciprocity_scatter(_site_frame(2000), floor=20).data[0],
                          go.Scattergl), "seuil abaisse : 2 000 doit basculer"
    finally:
        C.GL_SWITCH_ROWS = saved


def test_site_scatter_squares_are_exactly_the_capped_partners() -> None:
    d = _site_frame(40)
    fig = C.site_reciprocity_scatter(d, floor=20)
    symbols = list(fig.data[0].marker.symbol)
    for i, capped in enumerate(d["share_p_capped_flag"].tolist()):
        assert symbols[i] == ("square" if capped else "circle")
    assert fig.layout.xaxis.type == "log" and fig.layout.yaxis.type == "log"


def test_site_scatter_highlight_is_opacity_only_never_a_repaint() -> None:
    d = _site_frame(40)
    keep = frozenset(d["partner_id"].iloc[:5].tolist())
    fig = C.site_reciprocity_scatter(d, floor=20, highlight_ids=keep)
    opacity = list(fig.data[0].marker.opacity)
    assert opacity[:5] == [1.0] * 5
    assert set(opacity[5:]) == {C.MUTED_OPACITY}
    assert fig.data[0].marker.color == H.UL_COLOR, (
        "aucune marque n'est REPEINTE : la teinte reste celle de l'UL (§2.4)")


def test_vacuity_highlight_fails_without_a_selection() -> None:
    d = _site_frame(40)
    fig = C.site_reciprocity_scatter(d, floor=20)
    assert set(fig.data[0].marker.opacity) == {C.BASE_MARK_OPACITY}, (
        "sans selection, une seule opacite -- donc le test de surlignage mord bien")


def test_squared_reciprocity_locks_the_aspect_ratio() -> None:
    fig = R.build_zoom_reciprocity()
    assert fig.layout.yaxis.scaleanchor == "x" and fig.layout.yaxis.scaleratio == 1
    dotted = [s for s in fig.layout.shapes if s.line is not None and s.line.dash == "dot"]
    assert len(dotted) == 1, "une diagonale pointillee, jamais une entree de legende"
    assert C.DIAGONAL_LABEL_EQUAL_WEIGHT in {a.text for a in fig.layout.annotations}
    assert C.DIAGONAL_LABEL_EQUILIBRE in {
        a.text for a in R.build_col_reciprocity().layout.annotations}


# ===========================================================================
# 11. Hygiene du module
# ===========================================================================
def test_no_hex_literal_and_no_format_spec_in_charts_py() -> None:
    src = CHARTS_FILE.read_text(encoding="utf-8")
    assert HEX_RX.findall(src) == [], (
        "litteral #RRGGBB dans charts.py : toute couleur vient d'un token lib")
    assert FORMAT_SPEC_RX.findall(src) == [], (
        "specificateur de format dans une accolade plotly : chaque nombre est "
        "deja mis en forme par lib.hover")
    assert not re.search(r"^\s*import streamlit|^\s*from streamlit", src, re.M), (
        "charts.py doit rester un module de constructeurs purs")


def test_vacuity_hygiene_scan_catches_an_injected_literal() -> None:
    src = CHARTS_FILE.read_text(encoding="utf-8")
    assert HEX_RX.findall(src) == [] and FORMAT_SPEC_RX.findall(src) == []
    injected = src + '\nBAD = "#123456"\nWORSE = "%{y:.2f}"\n'
    assert HEX_RX.findall(injected), "le scanner doit voir un hex injecte"
    assert FORMAT_SPEC_RX.findall(injected), "le scanner doit voir un format injecte"


def test_every_registered_builder_uses_the_single_hover_grammar() -> None:
    for key, _family, build in R.BUILDERS:
        fig = build()
        data_traces = [t for t in fig.data if (getattr(t, "customdata", None) or [])]
        assert data_traces, "{0} : aucune trace ne porte de customdata".format(key)
        for tr in data_traces:
            assert tr.hovertemplate == HV.HOVERTEMPLATE, (
                "{0} : hovertemplate {1!r}".format(key, tr.hovertemplate))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
