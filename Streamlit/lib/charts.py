# Streamlit/lib/charts.py
"""
Chart primitives de la passe 7a -- le contrat de mise en page des barres
(BUILD_PLAN P1) et les figures de la paire (BUILD_PLAN P5/P9/P10/P11).

AUTORITE, dans cet ordre :
  - `docs/contract_fragments/lib_api_pass7.md` : les SIGNATURES (noms,
    parametres, types de retour) -- liantes, jamais reinterpretees ici ;
  - `docs/studio/VIZ_SPEC_pass7.md` §1 : le bloc de constantes, colle
    verbatim ci-dessous (§1.2), le mecanisme de gutter probe en DOM (§1.3)
    et la regle d'axe du miroir (§1.4) ; §5 : une specification par cle du
    registre ; §6 : les deux verdicts A/B (mode phares = variante (i) a
    trois segments ; PLANE_PAD_FRAC = 0,08 par cote) ;
  - `docs/contract_fragments/chart_keys_pass7.md` : les cles verbatim.

REFERENCE (lecture seule, jamais importee) :
`docs/reference/benchup_2026-09-04/lib/charts.py` (constantes, `wrap_label_px`,
`_add_gutter_column`, `_nice_ticks`, `row_height_*`) et
`lib/charts_topics.py` (`balance_bars`, `fig_plane_*`).

REGLES DE MAISON tenues par ce module
  - AUCUN import streamlit direct : les constructeurs sont PURS (une trame
    deja mise en forme en entree, une figure en sortie) ; ils ne lisent
    jamais un parquet et ne posent jamais un widget. Le seul chemin qui
    traverse `lib.controls` est la reutilisation du DAGGER, une constante de
    texte (« reuse, do not redefine », VIZ_SPEC_pass7 §1.2).
  - AUCUN litteral `#RRGGBB` : toute couleur vient d'un token `lib.helpers`
    ou `lib.overlay` (`tests/test_charts.py` scanne ce fichier).
  - AUCUN specificateur de format dans une accolade plotly (un deux-points
    dans une accolade de `hovertemplate`/`texttemplate`) :
    chaque nombre affiche est deja mis en forme en amont par `lib.hover`
    (idiome anti-chiffre de BenchUp, scanne lui aussi).
  - Le survol est TOUJOURS `customdata = df[hover_col]` +
    `hovertemplate = hover.HOVERTEMPLATE` : une seule grammaire, celle de
    `docs/tooltip_spec.yaml`.
  - L'ORDRE DES LIGNES est celui de la trame : la page trie, le
    constructeur ne retrie JAMAIS (une identite ne bouge pas quand un filtre
    change).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from lib import helpers as H
from lib import hover as hv
from lib import overlay as OV
from lib.controls import DAGGER   # reutilise, jamais redefini (VIZ_SPEC_pass7 §1.2)

# ===========================================================================
# 1. Le contrat de mise en page des barres -- VIZ_SPEC_pass7 §1.2, verbatim
#    Derive UNE fois de tout l'univers de libelles sur disque
#    (reports/pass7_probes.md step 4) avec la table de glyphes livree
#    lib/resources/glyph_widths.json. NE JAMAIS mesurer la trame courante.
# ===========================================================================
FAMILIES = ("champ", "sous_champ", "topic", "labo", "labo_court", "pays", "partenaire")

LABEL_COL_PX = {          # point fixe (<=2 lignes), arrondi au multiple de 5 px superieur
    "champ":       160,   # 26 champs,             point fixe 158,6
    "sous_champ":  205,   # 244 sous-champs,       point fixe 202,2
    "topic":       290,   # 4 516 topics,          point fixe 290,2 (reserve : aucune barre topic en 7a)
    "labo":        335,   # 168 noms de structure, point fixe 333,1
    "labo_court":   90,   # 68 acronymes,          point fixe  86,2  (S-LIB-A, suivi 1 -- voir ci-dessous)
    "pays":        120,   # 178 noms de pays FR,   point fixe 117,3
    "partenaire":  200,   # 12 319 noms plafonnes, point fixe 195,6
}
# `labo_court` (S-LIB-A, suivi 1 -- ruling du manager sur les constats 7/8 de
# progress/P7_LIBA.md). La famille `labo` a ete mesuree par S-PRB sur l'univers des
# NOMS COMPLETS de `ul_labs` (658,8 px sur une ligne, 335 px apres enveloppe) ; or le
# seul graphique de grain labo de la passe, `zoom_portage`, ne dessine JAMAIS ces noms :
# sa trame vient de `ptn_labs.lab_name`, qui porte des ACRONYMES (IJL, CRAN, LORIA,
# LRGP, LEM3, LPCT... 68 valeurs distinctes avec « Autres »). Consequence mesuree :
# `margin_left("labo") = 393 px` DEPASSE un viewport de 390 px, la zone de trace est
# de largeur negative et les barres disparaissent (progress/p7_proofs/LIB/
# zoom_portage_390.png de la premiere passe de rendu).
#
# Le point fixe de cet univers-la, au sens de VIZ_SPEC_pass7 §1.1 (« la plus petite
# largeur de colonne a laquelle chaque libelle s'enveloppe en <=2 lignes sans qu'aucune
# ligne rendue ne depasse la colonne »), vaut **86,2 px -> 90 px**, et NON les ~140 px
# qu'on pouvait deduire de la largeur SUR UNE LIGNE que S-LIB-A avait rapportee
# (134,9 px) : la definition autorise deux lignes, et seuls 2 acronymes sur 68 en
# demandent une seconde (« SAMA (EX HISCANT MA) », « INSPIIRE (Ex APEMAC) »).
# ALTERNATIVE CHIFFREE, si le manager prefere ne jamais couper un acronyme (une
# identite se lit d'un bloc) : 140 px suffit a garder les 68 sur UNE ligne, et laisse
# encore 142 px de trace a 390 px. Un seul chiffre a changer ici.
# `labo` (335) reste en place pour tout graphique qui dessine les noms complets.
WRAP_PX = dict(LABEL_COL_PX)   # le budget d'enveloppe EST la colonne : un seul nombre
GUTTER_COL_PX = {f: 48 for f in FAMILIES}   # plus large chaine vivante 40,2 px, 7 chiffres 48,2 px
COL_PAD_PX = 10

PARTNER_LABEL_MAX_CHARS = 40   # plafond d'AFFICHAGE seulement : 28,3 % des noms coupes,
                               # 117 collisions -> la 1re ligne du survol et l'export
                               # portent TOUJOURS le nom complet
ELLIPSIS = "…"

ROW_PITCH_SINGLE, BAR_PX_SINGLE = 34, 20   # P1 (Lorraine tient un pas plus haut que BenchUp)
ROW_PITCH_PAIR,   BAR_PX_PAIR   = 40, 16   # P1, == BenchUp
BAR_GAP_SINGLE = 1 - BAR_PX_SINGLE / ROW_PITCH_SINGLE   # 0,4118, resolu -- jamais estime a l'oeil
BAR_GAP_PAIR   = 1 - BAR_PX_PAIR   / ROW_PITCH_PAIR     # 0,6000
TICK_FONT_PX, GUTTER_FONT_PX, FONT_PX = 13, 12, 12
MIN_HEIGHT = 300
HAIRLINE_PX, LINE_PX = 1, 2
BUBBLE_MIN_PX, BUBBLE_MAX_PX = 6, 34
PLANE_PAD_FRAC = 0.08          # marge d'axe par cote sur tout nuage (A/B 2, §6.2)
MUTED_OPACITY = 0.35           # highlight-plus-mute : OPACITE seule, jamais un repeint (§2.4)


def margin_left(family: str) -> int:
    """`margin.l` est une CONSTANTE par famille : une barre demarre au meme
    pixel sur tous les graphiques de la famille."""
    return LABEL_COL_PX[family] + GUTTER_COL_PX[family] + COL_PAD_PX


# les libelles de tick doivent etre pousses hors de la colonne de gutter qui
# partage leur marge (VIZ_SPEC_pass7 §1.3, mecanisme M2 -- probe en DOM :
# porte litteralement, le mecanisme BenchUp chevauche les ticks de ~37 px)
TICKLABEL_STANDOFF_PX = {f: GUTTER_COL_PX[f] + COL_PAD_PX for f in FAMILIES}   # = 58


def row_height_single(n: int) -> int:
    return max(MIN_HEIGHT, 60 + int(n) * ROW_PITCH_SINGLE + 46)


def row_height_pair(n: int) -> int:
    return max(MIN_HEIGHT, 60 + int(n) * ROW_PITCH_PAIR + 46)
# Pas de correction n_wrapped : les libelles sur deux lignes sont la norme que
# ce pas heberge deja.

# ---- format du nombre de gutter -------------------------------------------
GUTTER_FMT = "fr_int"          # lib.helpers.fr_int -- separateur U+202F, jamais de decimale
# Le gutter porte la VALEUR COMBINEE DE LA QUANTITE QUE LES BARRES MONTRENT
# (P10, lu strictement) : mode volume -> UL seule + conjoint + partenaire seul ;
# mode phares -> phares UL + phares conjoints ; mode fwci -> le nombre de
# travaux conjoints sur lequel repose la mediane.
# AUCUN texte d'en-tete au-dessus de la colonne, nulle part : la base se nomme
# une seule fois, dans la legende de section.

# ---- marque de reference --------------------------------------------------
REFERENCE_RED = H.REFERENCE_RED   # == l'encre de prudence : un rouge, un sens
REFERENCE_DASH = "dash"
REFERENCE_WIDTH_PX = LINE_PX      # 2
CAUTION_INK = REFERENCE_RED
# varie par ligne -> une go.Shape verticale par ligne (x0 == x1, y0/y1 = i -+ 0,5)
# constante -> UN add_vline sur tout le panneau
# JAMAIS un diamant, jamais un point-et-tige, jamais un filet en encre secondaire.

# ---- mecanisme du gutter (VIZ_SPEC_pass7 §1.3) ----------------------------
GUTTER_NEG_FRAC = 0.14        # x de la trace-fantome, en fraction de l'etendue de donnees
GUTTER_HEADROOM = 1.04        # xaxis.range = [gx, x_max * GUTTER_HEADROOM]
GUTTER_PHANTOM_FILL = "rgba({0},{0},{0},{0})".format(0)   # totalement transparent
MIRROR_EPS_FRAC = 0.002       # miroir : la fantome FINIT au minimum de la plage
MIRROR_LEFT_HEADROOM = 1.02
MIRROR_DASH_HEADROOM = 1.35   # cote partenaire en tiret : de la place a droite malgre tout

# ---- encre et filets (tokens reutilises, jamais un litteral) --------------
INK_SECONDARY = OV.GROUPED_LEGEND_INK
GRID_COLOR = OV.GROUPED_GRID_COLOR
ZERO_LINE_COLOR = OV.GROUPED_ZERO_LINE_COLOR
SEGMENT_LINE_COLOR = OV.GROUPED_BAR_LINE_COLOR      # "white", 1 px : les segments ne se touchent pas
SURFACE = "white"

# ---- colonne liee « Co-pubs » (§5.7) --------------------------------------
LINK_COL_PX = 74
LINK_COL_HEADER = "Co-pubs"     # == lib.copy_fr.LABELS["JOINT_COL"] (copie de page, non importee ici)
LINK_TARGET = "_blank"
DASH_MARK = "—"            # tiret cadratin : « pas mesurable », jamais un zero

# ---- nuages ---------------------------------------------------------------
SCATTER_HEIGHT = 520
SCATTER_MARGIN_L = 66           # §6.2 : en dessous, le titre d'axe pivote est coupe a 390 px
SCATTER_MARGIN_R = 22
DIAGONAL_LABEL_EQUILIBRE = "équilibre"      # §5.2 / site_reciprocity_scatter
DIAGONAL_LABEL_EQUAL_WEIGHT = "poids égal"  # §5.13
GL_SWITCH_ROWS = 2000           # au-dela : Scattergl (contrat lib)
BASE_MARK_OPACITY = 0.6         # §5.2 : toutes les marques du plan site
OUTLINE_WIDTH = 2               # anneau de la marque signalee (§4.2)
# PROBE (S-LIB-A, 2026-09-10) : `marker.line` d'un `go.Scatter` N'A PAS de
# propriete `dash` dans plotly 5.24.1 -- « Invalid property ... Did you mean
# "cauto"? ». Le pointille demande par VIZ_SPEC_pass7 §4.2 pour l'anneau d'une
# marque signalee est donc IRREALISABLE sur un nuage : le relief qui ship est
# la LARGEUR (1 px -> OUTLINE_WIDTH) portee par la teinte de domaine NON
# TEINTEE, plus la clause de survol et la colonne « Ref. » a dague. Le
# pointille reste vivant la ou plotly l'accepte : les FORMES (references,
# diagonales), pas les contours de marque.
QUADRANT_ORIGIN_PX = 2          # lignes 0/0 du plan frontiere (une origine, pas une reference)

BASE_MARGIN_T = 24
BASE_MARGIN_R = 50
BASE_MARGIN_B = 42
MIRROR_MARGIN_B = 16            # §1.4 : sans ticks x, ~26 px de vertical rendus


# ===========================================================================
# 2. Table de glyphes -- une lecture, un processus
# ===========================================================================
_GLYPH_WIDTHS_PATH = Path(__file__).with_name("resources") / "glyph_widths.json"
_JSON_ENCODING = "utf-8"
_WIDTHS_KEY = {TICK_FONT_PX: "widths_{0}px".format(TICK_FONT_PX),
               GUTTER_FONT_PX: "widths_{0}px".format(GUTTER_FONT_PX)}
_FALLBACK_KEY = {TICK_FONT_PX: "fallback_width_{0}px".format(TICK_FONT_PX),
                 GUTTER_FONT_PX: "fallback_width_{0}px".format(GUTTER_FONT_PX)}


def _load_glyph_widths() -> dict:
    with open(_GLYPH_WIDTHS_PATH, "r", encoding=_JSON_ENCODING) as fh:
        return json.load(fh)


_GLYPHS = _load_glyph_widths()   # niveau module : une lecture de fichier, un processus


def _measured_font_family() -> str:
    """La pile de polices sur laquelle la table de glyphes a ETE MESUREE, prise
    dans la table elle-meme (dedupliquee : le champ livre repete sa propre
    valeur). Elle est posee sur CHAQUE figure, sans quoi plotly retombe sur sa
    pile par defaut (« Open Sans », verdana, arial) -- plus large que celle des
    mesures, et les points fixes de colonne de §1.1 deviennent faux : constate
    en rendant, pas en lisant le CSS (les libelles longs de la famille `champ`
    debordaient de la colonne a 160 px avant ce correctif)."""
    seen, out = set(), []
    for part in str(_GLYPHS["font_family"]).split(","):
        token = part.strip()
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return ", ".join(out)


FONT_FAMILY = _measured_font_family()


SAFETY_FACTOR = float(_GLYPHS["safety_factor"])   # 1,08, declare par la table elle-meme


def text_width_px(text, size_px: int = TICK_FONT_PX) -> float:
    """Largeur rendue de `text`, en px, a `size_px` -- sommee caractere par
    caractere sur la table livree (13 px pour un libelle, 12 px pour un nombre
    de gutter), MULTIPLIEE par le facteur de securite que la table declare.
    Un caractere absent de la table retombe sur la moyenne mesuree de sa
    taille plutot que de lever : un futur libelle a un glyphe inedit se
    degrade, il ne casse pas.

    POURQUOI LE FACTEUR EST APPLIQUE ICI (constate en rendant, S-LIB-A) :
    BenchUp somme la table BRUTE et compte sur la constante de colonne d'avoir
    ete resolue avec le facteur. Pour Lorraine, les points fixes de §1.1 sont
    a 1-4 px du budget (`champ` 157,8 pour 160, `sous_champ` 204,7 pour 205,
    `topic` 290,0 pour 290) : il ne reste AUCUNE reserve, et la moindre
    difference de metrique entre la police mesuree et celle que le navigateur
    substitue coupe le libelle le plus long. Mesure : « Earth and Planetary
    Sciences » et « Business, Management and Accounting » debordaient de la
    colonne `champ` au rendu 1280 px. Le facteur applique ici ramene le plus
    large rendu a 148,1 / 189,8 / 268,4 / 310,0 px (champ / sous_champ / topic
    / labo), soit ~7 % de reserve, SANS toucher aux constantes de VIZ_SPEC et
    SANS creer une seule ellipse (0 repli sur les cinq univers, re-mesure)."""
    if size_px in _WIDTHS_KEY:
        table = _GLYPHS[_WIDTHS_KEY[size_px]]
        fallback = _GLYPHS[_FALLBACK_KEY[size_px]]
        return SAFETY_FACTOR * sum(table.get(ch, fallback) for ch in str(text))
    table = _GLYPHS[_WIDTHS_KEY[TICK_FONT_PX]]
    fallback = _GLYPHS[_FALLBACK_KEY[TICK_FONT_PX]]
    return (SAFETY_FACTOR * size_px / TICK_FONT_PX) * sum(
        table.get(ch, fallback) for ch in str(text))


def _display_cap(text) -> str:
    """Plafond d'AFFICHAGE de la famille `partenaire` (VIZ_SPEC_pass7 §1.1) :
    coupe a PARTNER_LABEL_MAX_CHARS sur une frontiere de mot quand il en
    existe une dans les six derniers caracteres, sinon en plein mot, et
    n'ajoute ELLIPSIS que si la chaine a REELLEMENT ete raccourcie. Le nom
    complet reste porte par la premiere ligne du survol et par l'export --
    deux lignes qui se tronquent pareil restent distinguables ailleurs,
    jamais sur l'axe seul."""
    s = str(text)
    if len(s) <= PARTNER_LABEL_MAX_CHARS:
        return s
    head = s[:PARTNER_LABEL_MAX_CHARS]
    cut = head.rfind(" ")
    if cut >= PARTNER_LABEL_MAX_CHARS - 6:
        head = head[:cut]
    return head.rstrip() + ELLIPSIS


def wrap_label_px(text, family: str) -> str:
    """Le libelle de tick d'UNE ligne : enveloppe gloutonne par largeur
    MESUREE (jamais un compte de caracteres), au plus DEUX lignes, jamais un
    mot coupe, jointes par `<br>` (ce que plotly dessine). Un mot deja plus
    large que la colonne est garde entier (« un mot ne se coupe pas » passe
    avant la cible de largeur). Une troisieme ligne fusionne tout ce qui suit
    la premiere en UNE seconde ligne ; si celle-ci depasse encore, elle est
    coupee et marquee d'ELLIPSIS -- le seul endroit ou cette fonction
    raccourcit du texte."""
    if family not in WRAP_PX:
        raise ValueError("famille inconnue : {0!r}".format(family))
    wrap_px = WRAP_PX[family]
    raw = _display_cap(text) if family == "partenaire" else str(text)
    words = raw.split()
    if not words:
        return raw
    lines = [words[0]]
    for w in words[1:]:
        candidate = "{0} {1}".format(lines[-1], w)
        if text_width_px(candidate) <= wrap_px:
            lines[-1] = candidate
        else:
            lines.append(w)
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    if len(lines) == 2 and text_width_px(lines[1]) > wrap_px:
        keep = len(lines[1])
        while keep > 1 and text_width_px(lines[1][:keep] + ELLIPSIS) > wrap_px:
            keep -= 1
        lines[1] = lines[1][:keep].rstrip() + ELLIPSIS
    return "<br>".join(lines)


def _nice_ticks(vmax: float, target: int = 5) -> list[float]:
    """Positions de tick NON NEGATIVES pour un axe dont la plage commence
    sous zero (le gutter). Sans `tickvals` explicites, plotly libellerait le
    gutter avec des valeurs negatives -- un nombre que le graphique ne veut
    pas dire."""
    if not np.isfinite(vmax) or vmax <= 0:
        return [0.0]
    raw = vmax / max(target, 1)
    mag = 10.0 ** np.floor(np.log10(raw))
    step = mag
    for mult in (1, 2, 2.5, 5, 10):
        step = mult * mag
        if raw <= step:
            break
    n = int(np.floor(vmax / step)) + 1
    return [round(i * step, 12) for i in range(n)]


# ===========================================================================
# 3. Le gutter : colonne de libelle + colonne de valeur = UN seul mecanisme
# ===========================================================================
def _gutter_text(values: Sequence, caution: Sequence | None,
                 value_fmt: Callable) -> tuple[list[str], list[str]]:
    """(textes, encres) du gutter. Une ligne signalee garde sa barre PLEINE
    dans sa propre couleur : seuls le texte de valeur et le texte de gutter
    passent en REFERENCE_RED, poids 400, dague conservee (§1.2). Jamais une
    hachure, jamais un motif, jamais un remplissage gris."""
    flags = list(caution) if caution is not None else [False] * len(values)
    texts, inks = [], []
    for v, flagged in zip(values, flags):
        body = value_fmt(v)
        texts.append("{0} {1}".format(body, DAGGER) if flagged else body)
        inks.append(CAUTION_INK if flagged else INK_SECONDARY)
    return texts, inks


def _add_gutter_column(fig: go.Figure, *, y: Sequence, texts: Sequence,
                       inks: Sequence, xmax: float) -> float:
    """Contrat P1, forme a UNE barre : une trace-fantome `go.Bar` a x negatif,
    remplissage transparent, son texte pousse encore plus a gauche par
    `textposition="outside"`, hors du panneau (`cliponaxis=False`) donc dans
    la marge reservee. `constraintext="none"` est porteur, pas decoratif :
    sous le defaut `"both"` plotly RETRECIT le texte a la voie de la trace
    des qu'une seconde trace de barres partage l'axe categoriel.

    Retourne le plancher de plage (== le x de la fantome, mecanisme M2)."""
    n = len(y)
    span = xmax if xmax > 0 else 1.0
    gx = -span * GUTTER_NEG_FRAC
    fig.add_trace(go.Bar(
        x=[gx] * n, base=[0] * n, y=list(y), orientation="h",
        marker=dict(color=GUTTER_PHANTOM_FILL, line=dict(width=0)),
        text=list(texts), textposition="outside", constraintext="none",
        cliponaxis=False,
        textfont=dict(family=FONT_FAMILY, size=GUTTER_FONT_PX, color=list(inks)),
        hoverinfo="skip", showlegend=False,
    ))
    return gx


def _add_reference(fig: go.Figure, reference, n: int) -> None:
    """Reference rouge pointillee. Un scalaire -> UN `add_vline` sur tout le
    panneau. Une valeur par ligne -> une `go.Shape` verticale par ligne, sur
    sa propre bande (`y0/y1 = i -+ 0,5`) : la reference d'une ligne ne
    traverse jamais celle d'a cote."""
    if reference is None:
        return
    line = dict(color=REFERENCE_RED, width=REFERENCE_WIDTH_PX, dash=REFERENCE_DASH)
    if np.isscalar(reference):
        if np.isfinite(float(reference)):
            fig.add_vline(x=float(reference), line=line)
        return
    for i, ref in enumerate(list(reference)[:n]):
        if ref is None or not np.isfinite(float(ref)):
            continue
        fig.add_shape(type="line", xref="x", yref="y",
                      x0=float(ref), x1=float(ref), y0=i - 0.5, y1=i + 0.5, line=line)


def _bar_layout(fig: go.Figure, *, family: str, n: int, pair: bool = False,
                margin_r: int = BASE_MARGIN_R, margin_b: int = BASE_MARGIN_B) -> go.Figure:
    """La mise en page commune a toute la famille « barres » : hauteur par
    formule, marge gauche CONSTANTE par famille, decalage de tick M2 (§1.3),
    police de tick, fond blanc explicite (mode clair, jamais de branche
    sombre), pleine largeur."""
    height = row_height_pair(n) if pair else row_height_single(n)
    fig.update_layout(
        height=height,
        bargap=BAR_GAP_PAIR if pair else BAR_GAP_SINGLE,
        margin=dict(t=BASE_MARGIN_T, l=margin_left(family), r=margin_r, b=margin_b),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family=FONT_FAMILY, size=FONT_PX, color=INK_SECONDARY),
        showlegend=False,
    )
    fig.update_yaxes(
        tickfont=dict(family=FONT_FAMILY, size=TICK_FONT_PX, color=INK_SECONDARY),
        ticklabelstandoff=TICKLABEL_STANDOFF_PX[family],
        showgrid=False, automargin=False, zeroline=False,
    )
    return fig


# ===========================================================================
# 4. bars_with_gutter -- la forme a UNE barre par ligne
# ===========================================================================
def bars_with_gutter(df: pd.DataFrame, *, family: str, label_col: str, value_col: str,
                     color: str | Sequence[str], hover_col: str = "hover",
                     isite_col: str | None = None, isite_on: bool = False,
                     reference: float | None = None, caution_col: str | None = None,
                     value_fmt: Callable = hv.fmt_int, gutter: bool = True,
                     narrow: bool = False) -> go.Figure:
    """Barres horizontales dans l'ORDRE DE LA TRAME (la page trie), colonne
    de libelle + gutter de valeur, reference rouge pointillee optionnelle.

    `isite_col` + `isite_on` -> les barres suivent la grammaire d'overlay
    existante (`lib.overlay.overlay_bars` : meme teinte, segment I-SITE plus
    fonce, jamais une couleur neuve) et le gutter est ajoute PAR-DESSUS la
    figure rendue. `lib.overlay` pose alors `barmode="stack"` : la fantome du
    gutter porte `base=0` et une longueur negative, donc elle vit seule du
    cote negatif de l'axe et le pas de ligne reste intact (une seule voie par
    ligne, comme sous `"overlay"`).

    `gutter=False` : idiome BenchUp pour un panneau etroit (moins de ~600 px
    de largeur de trace, que Streamlit ne peut pas lire cote serveur -- c'est
    donc l'APPELANT qui decide). La valeur survit dans le survol et dans
    l'export dans les deux cas.

    `narrow=True` : panneau etroit (une cellule de `st.columns`, ~200 px de trace) --
    trois graduations au lieu de cinq sur l'axe des valeurs, jamais de rotation
    (plotly bascule sinon les etiquettes a -90 degres des qu'elles se chevauchent ;
    constate au rendu de la page 1, passe 7b). Le serveur ne connait pas la
    largeur : c'est l'APPELANT qui decide, comme pour `gutter`.

    `reference` accepte un scalaire (une `add_vline` pleine hauteur) ou une
    valeur par ligne (un tick par bande) -- le contrat n'en type que le cas
    scalaire, celui-ci en est un sur-ensemble.
    """
    if family not in FAMILIES:
        raise ValueError("famille inconnue : {0!r}".format(family))
    d = df.reset_index(drop=True)
    n = len(d)
    if n == 0:
        raise ValueError("bars_with_gutter : aucune ligne a dessiner")

    y = list(range(n))
    values = pd.to_numeric(d[value_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    hovers = [str(x) for x in d[hover_col]] if hover_col in d.columns else [""] * n
    caution = (d[caution_col].fillna(False).astype(bool).tolist()
               if caution_col and caution_col in d.columns else None)

    if isite_col and isite_on:
        isite_vals = pd.to_numeric(d[isite_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        fig = OV.overlay_bars(categories=y, totals=values.tolist(),
                              isite=isite_vals.tolist(), colors=color,
                              isite_on=True, orientation="h")
        # UNE seule grammaire de survol : la trame porte deja la ligne I-SITE
        # (tooltip_spec.yaml), donc les infobulles propres de lib.overlay sont
        # REMPLACEES ici plutot que juxtaposees a la grammaire de la passe 7.
        for trace in fig.data:
            trace.customdata = hovers
            trace.hovertemplate = hv.HOVERTEMPLATE
            trace.showlegend = False
    else:
        fig = go.Figure(go.Bar(
            x=values.tolist(), y=y, orientation="h",
            marker=dict(color=color if isinstance(color, str) else list(color),
                        line=dict(width=0)),
            customdata=hovers, hovertemplate=hv.HOVERTEMPLATE, showlegend=False,
        ))
        fig.update_layout(barmode="overlay")

    xmax = float(values.max()) if n else 1.0
    x_floor = 0.0
    if gutter:
        texts, inks = _gutter_text(values, caution, value_fmt)
        x_floor = _add_gutter_column(fig, y=y, texts=texts, inks=inks, xmax=xmax)

    _add_reference(fig, reference, n)

    ticks = [t for t in _nice_ticks(xmax, target=3 if narrow else 5) if t >= 0]
    fig.update_xaxes(
        range=[x_floor, xmax * GUTTER_HEADROOM if xmax > 0 else 1.0],
        tickmode="array", tickvals=ticks, ticktext=[H.fr_int(t) for t in ticks], tickangle=0,
        gridcolor=GRID_COLOR, zerolinecolor=ZERO_LINE_COLOR,
        tickfont=dict(size=FONT_PX, color=INK_SECONDARY), title_text=None,
    )
    fig.update_yaxes(tickmode="array", tickvals=y,
                     ticktext=[wrap_label_px(v, family) for v in d[label_col]],
                     range=[n - 0.5, -0.5])
    return _bar_layout(fig, family=family, n=n)


# ===========================================================================
# 5. balance_bars -- le miroir de la paire (§5.7, verdict A/B 1 = variante i)
# ===========================================================================
BALANCE_MODES = ("volume", "fwci", "phares")
BALANCE_LEVELS = ("champ", "sous_champ")
FWCI_REFERENCE = 1.0        # la parite : la seule reference que ce plan possede


def _series_for_mode(d: pd.DataFrame, mode: str):
    """(gauche UL, conjoint, droite partenaire, presence a droite, combine du
    gutter) pour le mode demande. La GEOMETRIE est la meme dans les trois
    modes (verdict A/B 1, variante (i) : « same read, same form ») -- seule
    la quantite change, et le gutter reste « la valeur combinee de la
    quantite montree » dans les trois cas."""
    def num(col):
        return pd.to_numeric(d[col], errors="coerce")

    n = len(d)
    if mode == "volume":
        left = num("vol_ul_only").fillna(0.0).to_numpy(dtype=float)
        joint = num("vol_joint").fillna(0.0).to_numpy(dtype=float)
        right_raw = num("vol_partner_only")
        right = right_raw.fillna(0.0).clip(lower=0.0).to_numpy(dtype=float)
        has_right = right_raw.notna().to_numpy()
        combined = left + joint + right
    elif mode == "phares":
        left = num("n_phares_ul").fillna(0.0).to_numpy(dtype=float)
        joint = num("n_phares_joint").fillna(0.0).to_numpy(dtype=float)
        right = np.zeros(n, dtype=float)
        has_right = np.zeros(n, dtype=bool)     # cote partenaire = un TIRET, divulgue
        combined = left + joint
    elif mode == "fwci":
        left = num("fwci_ul").fillna(0.0).to_numpy(dtype=float)
        joint = num("fwci_joint").fillna(0.0).to_numpy(dtype=float)
        right = np.zeros(n, dtype=float)
        has_right = np.zeros(n, dtype=bool)     # le FWCI propre du partenaire n'existe pas
        combined = num("n_fwci_joint").fillna(0.0).to_numpy(dtype=float)
    else:
        raise ValueError("mode inconnu : {0!r} (attendu {1})".format(mode, BALANCE_MODES))
    return left, joint, right, has_right, combined


def balance_bars(df: pd.DataFrame, *, mode: str, level: str, partner_name: str) -> go.Figure:
    """Trois segments flottants par ligne, centres sur le conjoint : le
    conjoint occupe `[-j/2, +j/2]`, « UL seule » s'etend a gauche depuis
    `-j/2`, « {partenaire} seul » a droite depuis `+j/2`. UNE geometrie pour
    les trois modes (§6.1, verdict (i)).

    Axe (§1.4) : NI libelle de tick x NI grille -- seulement la ligne zero,
    epine du miroir. Les magnitudes se lisent a trois endroits independants
    de la largeur : le gutter (combine), le survol (par segment) et la
    colonne liee « Co-pubs » (conjoint).
    """
    if mode not in BALANCE_MODES:
        raise ValueError("mode inconnu : {0!r} (attendu {1})".format(mode, BALANCE_MODES))
    if level not in BALANCE_LEVELS:
        raise ValueError("niveau inconnu : {0!r} (attendu {1})".format(level, BALANCE_LEVELS))
    d = df.reset_index(drop=True)
    n = len(d)
    if n == 0:
        raise ValueError("balance_bars : aucune ligne au seuil")

    left, joint, right, has_right, combined = _series_for_mode(d, mode)
    half = joint / 2.0
    y = list(range(n))
    hovers = [str(x) for x in d["hover"]] if "hover" in d.columns else [""] * n
    under_floor = (d["under_floor"].fillna(False).astype(bool).to_numpy()
                   if "under_floor" in d.columns else np.zeros(n, dtype=bool))

    fig = go.Figure()
    seg_line = dict(color=SEGMENT_LINE_COLOR, width=HAIRLINE_PX)
    # La PREMIERE trace de donnees porte TOUTES les lignes (le compte de
    # lignes du registre de tests se lit sur elle) ; conjoint puis partenaire.
    fig.add_trace(go.Bar(
        x=left.tolist(), y=y, base=(-(half + left)).tolist(), orientation="h",
        marker=dict(color=H.UL_COLOR, line=seg_line),
        customdata=hovers, hovertemplate=hv.HOVERTEMPLATE, showlegend=False))
    fig.add_trace(go.Bar(
        x=joint.tolist(), y=y, base=(-half).tolist(), orientation="h",
        marker=dict(color=H.JOINT_COLOR, line=seg_line),
        customdata=hovers, hovertemplate=hv.HOVERTEMPLATE, showlegend=False))
    right_idx = [i for i in range(n) if has_right[i]]
    fig.add_trace(go.Bar(
        x=[right[i] for i in right_idx], y=right_idx,
        base=[half[i] for i in right_idx], orientation="h",
        marker=dict(color=H.PARTNER_COLOR, line=seg_line),
        customdata=[hovers[i] for i in right_idx],
        hovertemplate=hv.HOVERTEMPLATE, showlegend=False))

    # --- plage : §1.3, le miroir n'achete AUCUNE marge gauche de panneau ---
    left_extent = float(np.max(half + left)) if n else 1.0
    left_extent = left_extent if left_extent > 0 else 1.0
    x_left = -left_extent * MIRROR_LEFT_HEADROOM
    if right_idx:
        x_right = float(np.max(half + right))
    else:
        x_right = float(np.max(half)) * MIRROR_DASH_HEADROOM
    x_right = x_right if x_right > 0 else 1.0

    # --- gutter : la fantome FINIT au minimum de la plage (§1.3) -----------
    eps = abs(x_left) * MIRROR_EPS_FRAC
    texts, inks = _gutter_text(combined, under_floor.tolist(), hv.fmt_int)
    fig.add_trace(go.Bar(
        x=[-eps] * n, base=[x_left + eps] * n, y=y, orientation="h",
        marker=dict(color=GUTTER_PHANTOM_FILL, line=dict(width=0)),
        text=texts, textposition="outside", constraintext="none", cliponaxis=False,
        textfont=dict(family=FONT_FAMILY, size=GUTTER_FONT_PX, color=inks),
        hoverinfo="skip", showlegend=False))
    fig.update_layout(barmode="overlay")

    if mode == "fwci":
        # tick rouge pointille a la parite, PAR LIGNE (§5.7) : la reference
        # d'une ligne ne traverse pas la bande voisine.
        _add_reference(fig, [FWCI_REFERENCE] * n, n)

    fig.update_xaxes(range=[x_left, x_right], showticklabels=False, showgrid=False,
                     zeroline=True, zerolinecolor=ZERO_LINE_COLOR,
                     zerolinewidth=HAIRLINE_PX, title_text=None)
    fig.update_yaxes(tickmode="array", tickvals=y,
                     ticktext=[wrap_label_px(v, level) for v in d["node_name"]],
                     range=[n - 0.5, -0.5])

    fig = _bar_layout(fig, family=level, n=n, pair=True,
                      margin_r=LINK_COL_PX + COL_PAD_PX, margin_b=MIRROR_MARGIN_B)
    # APRES _bar_layout : `update_yaxes` s'applique a TOUS les axes y, donc le
    # second axe se configure en dernier ou son decalage de tick serait ecrase.
    _add_link_column(fig, d, y=y, under_floor=under_floor)
    return fig


def _add_link_column(fig: go.Figure, d: pd.DataFrame, *, y: Sequence,
                     under_floor: np.ndarray) -> None:
    """La colonne liee « Co-pubs » : un SECOND axe categoriel (`yaxis2`,
    `overlaying="y"`, `side="right"`, meme ordre de lignes) dont le
    `ticktext` porte un `<a href>`, plus UNE trace d'ancrage transparente
    liee a `yaxis2` pour que chaque ligne existe sur lui (PF-3). Sous le
    plancher du conjoint : un TIRET, jamais un compte, jamais un lien.

    Encre du lien : le libelle est enveloppe dans un `<span>` a la teinte
    sombre du bleu UL (`PAIR_COLORS_DARK["ul"]`) ; si le sous-ensemble HTML
    de plotly laisse tomber le span, la couleur de lien du navigateur est un
    repli acceptable (constat consigne dans progress/P7_LIBA.md)."""
    n = len(y)
    urls = d["url"].tolist() if "url" in d.columns else [None] * n
    labels = d["link_label"].tolist() if "link_label" in d.columns else [None] * n
    ink = H.PAIR_COLORS_DARK["ul"]
    ticktext = []
    for i in range(n):
        if under_floor[i] or not urls[i] or labels[i] in (None, ""):
            ticktext.append(DASH_MARK)
            continue
        ticktext.append(
            '<a href="{0}" target="{1}"><span style="color:{2}">{3}</span></a>'.format(
                urls[i], LINK_TARGET, ink, labels[i]))
    fig.add_trace(go.Scatter(
        x=[None] * n, y=list(y), yaxis="y2", mode="markers",
        marker=dict(color=GUTTER_PHANTOM_FILL, size=1),
        hoverinfo="skip", showlegend=False))
    fig.update_layout(yaxis2=dict(
        overlaying="y", side="right", anchor="x",
        tickmode="array", tickvals=list(y), ticktext=ticktext,
        range=[n - 0.5, -0.5], showgrid=False, zeroline=False, title_text=None,
        tickfont=dict(family=FONT_FAMILY, size=GUTTER_FONT_PX, color=ink),
    ))
    # En-tete de la colonne liee : une annotation en coordonnees papier, AU-DESSUS
    # de la colonne. Un `title_text` sur yaxis2 se rend pivote au milieu du bord
    # droit et vient chevaucher les liens -- constate en rendant (1280 px).
    fig.add_annotation(xref="paper", yref="paper", x=1.0, y=1.0,
                       text=LINK_COL_HEADER, showarrow=False,
                       xanchor="right", yanchor="bottom",
                       font=dict(family=FONT_FAMILY, size=GUTTER_FONT_PX, color=ink))


# ===========================================================================
# 6. Nuages -- reciprocite (paire et site) et les deux plans
# ===========================================================================
AX_SHARE_UL = "Part du portefeuille propre de l'UL"
AX_SHARE_PARTNER = "Part du portefeuille propre du partenaire"
AX_CO_WORKS = "Co-publications de la relation"
AX_FWCI_MEDIAN = "FWCI médian (réf. France)"
AX_EXPANSION = "Expansion"
AX_ACCELERATION = "Accélération"
QUADRANT_LABELS = ("Expansion et accélération",
                   "Accélération seule",
                   "Expansion seule",
                   "Ni l'une ni l'autre")


def _sizeref(values: np.ndarray) -> float:
    """UN `sizeref` partage : une marque veut dire la meme taille d'un plan a
    l'autre (§5.9)."""
    finite = values[np.isfinite(values)] if len(values) else values
    vmax = float(finite.max()) if len(finite) else 0.0
    return 2.0 * max(vmax, 1.0) / (BUBBLE_MAX_PX ** 2)


def _padded_range(vals: np.ndarray, *, log: bool = False):
    """PLANE_PAD_FRAC par cote (A/B 2, §6.2) -- la plus grande bulle fait
    34 px, soit 17 px de rayon, et 5,4 % de la largeur de trace au pire point
    de rupture (390 px) : 8 % porte ~48 % de marge de securite tout en
    coutant bien moins de surface que 16 % a 1920 px."""
    v = vals[np.isfinite(vals)]
    if log:
        v = v[v > 0]
        if not len(v):
            return None
        lo, hi = float(np.log10(v.min())), float(np.log10(v.max()))
    else:
        if not len(v):
            return None
        lo, hi = float(v.min()), float(v.max())
    span = hi - lo
    pad = (abs(hi) if span == 0 else span) * PLANE_PAD_FRAC
    pad = pad if pad > 0 else PLANE_PAD_FRAC
    return [lo - pad, hi + pad]


def _scatter_layout(fig: go.Figure, *, x_title=None, y_title=None) -> go.Figure:
    fig.update_layout(
        height=SCATTER_HEIGHT,
        margin=dict(t=BASE_MARGIN_T, l=SCATTER_MARGIN_L, r=SCATTER_MARGIN_R, b=BASE_MARGIN_B),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family=FONT_FAMILY, size=FONT_PX, color=INK_SECONDARY),
        showlegend=False,
    )
    fig.update_xaxes(title_text=x_title, gridcolor=GRID_COLOR,
                     zerolinecolor=ZERO_LINE_COLOR,
                     tickfont=dict(size=FONT_PX, color=INK_SECONDARY))
    fig.update_yaxes(title_text=y_title, gridcolor=GRID_COLOR,
                     zerolinecolor=ZERO_LINE_COLOR,
                     tickfont=dict(size=FONT_PX, color=INK_SECONDARY))
    return fig


def _add_diagonal(fig: go.Figure, lo: float, hi: float, label: str) -> None:
    """Diagonale 45 degres POINTILLEE jusqu'au maximum partage, annotee a son
    extremite haut-droite (une annotation, jamais une entree de legende)."""
    fig.add_shape(type="line", x0=lo, y0=lo, x1=hi, y1=hi,
                  line=dict(color=INK_SECONDARY, width=HAIRLINE_PX, dash="dot"))
    fig.add_annotation(x=hi, y=hi, text=label, showarrow=False,
                       xanchor="right", yanchor="bottom",
                       font=dict(size=FONT_PX, color=INK_SECONDARY))


def reciprocity_scatter(df: pd.DataFrame, *, level: str, partner_name: str) -> go.Figure:
    """§5.13 (BenchUp §11.7, adopte) : une bulle par noeud, axes CARRES
    (`scaleanchor`/`scaleratio`) donc la lecture de parite est geometrique,
    diagonale pointillee « poids egal », couleur = domaine, aire = volume
    conjoint sur UN `sizeref`. Pas de highlight-plus-mute ici : cette page
    n'a pas de hub qui interroge le nuage."""
    if level not in BALANCE_LEVELS:
        raise ValueError("niveau inconnu : {0!r}".format(level))
    d = df.reset_index(drop=True)
    n = len(d)
    if n == 0:
        raise ValueError("reciprocity_scatter : aucun noeud placable")
    x = pd.to_numeric(d["share_ul"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(d["share_partner"], errors="coerce").to_numpy(dtype=float)
    area = pd.to_numeric(d["co_works"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    colors = [H.get_domain_color(v) for v in d["domain_id"]]
    hovers = [str(v) for v in d["hover"]] if "hover" in d.columns else [""] * n

    fig = go.Figure(go.Scatter(
        x=x, y=y, mode="markers",
        marker=dict(color=colors, size=area, sizemode="area",
                    sizeref=_sizeref(area), sizemin=BUBBLE_MIN_PX,
                    line=dict(color=SEGMENT_LINE_COLOR, width=HAIRLINE_PX)),
        customdata=hovers, hovertemplate=hv.HOVERTEMPLATE, showlegend=False))

    both = np.concatenate([x, y])
    finite = both[np.isfinite(both)]
    shared_max = float(finite.max()) if len(finite) else 1.0
    _add_diagonal(fig, 0.0, shared_max, DIAGONAL_LABEL_EQUAL_WEIGHT)
    rng = _padded_range(both)
    fig = _scatter_layout(fig, x_title=AX_SHARE_UL, y_title=AX_SHARE_PARTNER)
    if rng:
        fig.update_xaxes(range=rng)
        fig.update_yaxes(range=rng)
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig


def site_reciprocity_scatter(df: pd.DataFrame, *, floor: int,
                             highlight_ids: frozenset | None = None) -> go.Figure:
    """§5.2 : log-log, `x = share_ul`, `y = share_p`, diagonale pointillee
    « equilibre », aire = `co_works_full`, marques en UL_COLOR a 60 %
    d'opacite. Highlight-plus-mute = OPACITE seule (§2.4) : les marques non
    surlignees tombent a MUTED_OPACITY, rien n'est repeint en gris. Marqueur
    CARRE quand `share_p_capped_flag`. `Scattergl` au-dela de
    GL_SWITCH_ROWS lignes.

    `floor` (p20/p10) est le plancher que la page a deja applique a la
    trame : il est porte ici pour la legende de section et le cache, jamais
    pour re-filtrer."""
    d = df.reset_index(drop=True)
    n = len(d)
    if n == 0:
        raise ValueError("site_reciprocity_scatter : aucun partenaire placable")
    x = pd.to_numeric(d["share_ul"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(d["share_p"], errors="coerce").to_numpy(dtype=float)
    area = pd.to_numeric(d["co_works_full"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    capped = (d["share_p_capped_flag"].fillna(False).astype(bool).to_numpy()
              if "share_p_capped_flag" in d.columns else np.zeros(n, dtype=bool))
    hovers = [str(v) for v in d["hover"]] if "hover" in d.columns else [""] * n

    if highlight_ids:
        ids = d["partner_id"].astype(str).tolist()
        opacity = [1.0 if pid in highlight_ids else MUTED_OPACITY for pid in ids]
    else:
        opacity = [BASE_MARK_OPACITY] * n

    trace_cls = go.Scattergl if n > GL_SWITCH_ROWS else go.Scatter
    fig = go.Figure(trace_cls(
        x=x, y=y, mode="markers",
        marker=dict(color=H.UL_COLOR, opacity=opacity,
                    symbol=["square" if c else "circle" for c in capped],
                    size=area, sizemode="area", sizeref=_sizeref(area),
                    sizemin=BUBBLE_MIN_PX,
                    line=dict(color=SEGMENT_LINE_COLOR, width=HAIRLINE_PX)),
        customdata=hovers, hovertemplate=hv.HOVERTEMPLATE, showlegend=False))

    positive = np.concatenate([x[np.isfinite(x) & (x > 0)], y[np.isfinite(y) & (y > 0)]])
    if len(positive):
        _add_diagonal(fig, float(positive.min()), float(positive.max()),
                      DIAGONAL_LABEL_EQUILIBRE)
    fig = _scatter_layout(fig, x_title=AX_SHARE_UL, y_title=AX_SHARE_PARTNER)
    fig.update_xaxes(type="log", range=_padded_range(x, log=True))
    fig.update_yaxes(type="log", range=_padded_range(y, log=True))
    return fig


def _mark_style(d: pd.DataFrame, n: int):
    """Teinte et anneau d'une marque de topic (§4.2, amendement VIZ_SPEC
    §1.2) : remplissage = `tint(domain_color, TINT_FACTOR)` sur une ligne
    signalee, contour = la teinte de domaine NON TEINTEE, portee a
    OUTLINE_WIDTH et pointillee -- l'identite et le plancher de visibilite
    survivent au remplissage plus pale. Une ligne n'est JAMAIS grisee,
    desaturee, cachee ni triee en dernier."""
    flags = (d["artifact_flag"].fillna(False).astype(bool).to_numpy()
             if "artifact_flag" in d.columns else np.zeros(n, dtype=bool))
    hues = [H.get_domain_color(v) for v in d["domain_id"]]
    fills = [H.tint(h) if f else h for h, f in zip(hues, flags)]
    widths = [OUTLINE_WIDTH if f else HAIRLINE_PX for f in flags]
    return fills, hues, widths


def fig_plane_impact(df: pd.DataFrame) -> go.Figure:
    """§5.8 : `x = co_works` en LOG, `y = fwci_median`, aire = `co_works`,
    couleur = domaine, teinte + anneau pointille sur un topic signale, UNE
    reference rouge pointillee CONSTANTE a la parite du FWCI (la seule
    reference que ce plan possede)."""
    d = df.reset_index(drop=True)
    n = len(d)
    if n == 0:
        raise ValueError("fig_plane_impact : aucun topic au seuil")
    x = pd.to_numeric(d["co_works"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(d["fwci_median"], errors="coerce").to_numpy(dtype=float)
    fills, hues, widths = _mark_style(d, n)
    hovers = [str(v) for v in d["hover"]] if "hover" in d.columns else [""] * n

    fig = go.Figure(go.Scatter(
        x=x, y=y, mode="markers",
        marker=dict(color=fills, size=x, sizemode="area", sizeref=_sizeref(x),
                    sizemin=BUBBLE_MIN_PX,
                    line=dict(color=hues, width=widths)),
        customdata=hovers, hovertemplate=hv.HOVERTEMPLATE, showlegend=False))
    fig.add_hline(y=FWCI_REFERENCE,
                  line=dict(color=REFERENCE_RED, width=REFERENCE_WIDTH_PX,
                            dash=REFERENCE_DASH))
    fig = _scatter_layout(fig, x_title=AX_CO_WORKS, y_title=AX_FWCI_MEDIAN)
    fig.update_xaxes(type="log", range=_padded_range(x, log=True))
    fig.update_yaxes(range=_padded_range(y))
    return fig


def fig_plane_frontier(df: pd.DataFrame) -> go.Figure:
    """§5.9 : `x = expansion`, `y = acceleration`, aire = `co_works`, couleur
    = domaine, teinte + anneau sur un topic signale. Les deux composantes
    sont SIGNEES : le plan a une vraie origine, donc les deux lignes 0/0 sont
    dessinees en encre d'origine (JAMAIS le rouge de reference -- une origine
    n'est pas une reference) et les quatre quadrants sont libelles dans la
    marge, hors de portee des marques. Aucun anneau « led » : Lorraine n'a
    pas d'indicateur de leadership, ce canal reste inutilise plutot que
    detourne (un canal, un sens)."""
    d = df.reset_index(drop=True)
    n = len(d)
    if n == 0:
        raise ValueError("fig_plane_frontier : aucun topic score")
    x = pd.to_numeric(d["expansion"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(d["acceleration"], errors="coerce").to_numpy(dtype=float)
    area = pd.to_numeric(d["co_works"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    fills, hues, widths = _mark_style(d, n)
    hovers = [str(v) for v in d["hover"]] if "hover" in d.columns else [""] * n

    fig = go.Figure(go.Scatter(
        x=x, y=y, mode="markers",
        marker=dict(color=fills, size=area, sizemode="area", sizeref=_sizeref(area),
                    sizemin=BUBBLE_MIN_PX,
                    line=dict(color=hues, width=widths)),
        customdata=hovers, hovertemplate=hv.HOVERTEMPLATE, showlegend=False))
    origin = dict(color=ZERO_LINE_COLOR, width=QUADRANT_ORIGIN_PX)
    fig.add_vline(x=0.0, line=origin)
    fig.add_hline(y=0.0, line=origin)

    fig = _scatter_layout(fig, x_title=AX_EXPANSION, y_title=AX_ACCELERATION)
    xr, yr = _padded_range(x), _padded_range(y)
    if xr:
        fig.update_xaxes(range=xr)
    if yr:
        fig.update_yaxes(range=yr)
    for text, px, py, xa, ya in (
        (QUADRANT_LABELS[0], 1, 1, "right", "top"),
        (QUADRANT_LABELS[1], 0, 1, "left", "top"),
        (QUADRANT_LABELS[2], 1, 0, "right", "bottom"),
        (QUADRANT_LABELS[3], 0, 0, "left", "bottom"),
    ):
        fig.add_annotation(xref="paper", yref="paper", x=px, y=py, text=text,
                           showarrow=False, xanchor=xa, yanchor=ya,
                           font=dict(size=FONT_PX, color=INK_SECONDARY))
    return fig
