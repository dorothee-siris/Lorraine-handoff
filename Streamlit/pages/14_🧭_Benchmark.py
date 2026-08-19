"""
Benchmark (T4b) -- pass-5 rung-synthesis redesign (ruling R13, verbatim in
docs/SPRINT_KICKOFF_pass5.md) supersedes the pass-4 all-dots-first form (docs/pass4_decision_memo.md
Sec.3 / docs/benchmark_peer_candidates.md / BUILD_PLAN.md Sec.G4). Worker P-E, sprint pass 5.

R13 first screen: for each of the 4 registry rungs, UL's point against the rung's peer median +
min-max band on 6 pre-agreed signals -- NO overall score, NO rank ordering, NO league table (the
concept review's "missing view #4", docs/CODEX_CONCEPT_REVIEW.md: "for each rung, show UL against
the peer median and range on 5-7 pre-agreed field/impact signals, with no overall score"). The
all-dots field-level detail (pass-4's whole page) becomes a drill-down expander, top-10-most-
distinctive default + search + "afficher plus" (R11 pure helpers), fewer default visible peers.

Peer set: the 9 SIRIS-recommended candidates of docs/benchmark_peer_candidates.md Sec.3 (user
ruling 2026-08-17), registry-driven (`inputs/overlays/bench_peers.csv`) -- workshop keeps
tick-box override power, no code change needed to add/drop a peer (registry edit + pipeline
re-run only).

Every pass-4 honesty line survives this redesign, relocated next to the surface it qualifies
(R13 caveat-adjacency; full old-line -> new-location map in progress/PE_benchmark.md):
  - four-UL-numbers reconciliation + <=0.1% live-pull filter asymmetry -> beside the UL KPI.
  - live-drift band + both pull dates -> beside the header.
  - FR-vs-foreign direct-id asymmetry (~25-35%) + component-ecole direction-of-bias -> beside the
    "Travaux" (size/volume) row of the rung synthesis.
  - FWCI_FR symmetric-yardstick note -> beside the "FWCI" / "Top 10 %" (impact) rows.
  - indicator-coverage disclosure (dynamic, <95% list) -> beside the "Couverture" row.

S9 audience note: this is a POSITIONING instrument (AB-facing benchmark intelligence), never a
growth scoreboard -- austerity framing applies, same as the rest of the app.

Authority (binding): docs/SPRINT_KICKOFF_pass5.md R13 (this page's own ruling, verbatim above);
docs/CODEX_CONCEPT_REVIEW.md "missing view #4" (rung synthesis, the reference this redesign
implements); BUILD_PLAN.md Sec.G4 + Sec.1 (S4/S5/S9/S10, pass-4 inherited obligations);
docs/pass4_challenge_memo.md attacks #12-16 (absorbed, relocated not deleted); docs/studio/
VIZ_SPEC.md Sec.2.8 T4b row (dot-ratio grammar, kept for the drill-down). Every shared behaviour
goes through Streamlit/lib/{controls,exports,links,ranked}.py (S4/W5) -- house pattern.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from lib import controls, exports, links, ranked
from lib.data_cache import DATA_DIR, get_corpus_facts_df
from lib.helpers import UL_OPENALEX_ID, fr_int, fr_pct, log_linear_toggle, window_label

# =============================================================================
# Page config
# =============================================================================
st.set_page_config(page_title="Benchmark | UL Bibliometrics", page_icon="🧭", layout="wide")

# =============================================================================
# Constants
# =============================================================================
UL_ENTITY_ID = UL_OPENALEX_ID  # FOCAL row, always shown

# Short direct-label per entity (VIZ_SPEC T4b row: "one peer = one grey tone + label, never a
# new identity colour" -- kept for the drill-down's dot-ratio grammar).
SHORT_LABEL = {
    UL_ENTITY_ID: "UL",
    "I2279609970": "Lille",
    "I97188460": "Nantes",
    "I198244214": "Clermont",
    "I899635006": "UGA",
    "I157674565": "Liège",
    "I62318514": "UDE",
    "I166825849": "Tampere",
    "I98381234": "Oulu",
    "I169108374": "UPV/EHU",
}

RUNGS = ["FR-ISITE", "FR-IDEX", "XBORDER", "EU-MIRROR"]
RUNG_LABELS_FR = {
    "FR-ISITE": "FR - I-SITE (parité)", "FR-IDEX": "FR - IDEX (aspiration)",
    "XBORDER": "Grande Région (transfrontalier)", "EU-MIRROR": "Miroirs européens",
}
# Default rung shown in the drill-down entity picker (R13 item 2: "fewer default visible
# peers, e.g. the selected rung only") -- was all 4 rungs / 9 peers pre-redesign.
DEFAULT_DRILLDOWN_RUNGS = ["FR-ISITE"]

FOCAL_BLUE = "#0072B2"    # VIZ_SPEC 1.1 focal
PEER_GREY = "#8C9196"     # VIZ_SPEC 1.1 comparison/reference grey -- ALL peers share this ONE tone
FRANCE_REF_LINE = "#8C9196"

S9_BANNER_FR = (
    "Les chiffres de cette page situent l'Université de Lorraine face à des pairs choisis par "
    "l'établissement, jamais un classement de performance entre eux."
)

ARTIFACT_EXEMPT_CAPTION_FR = (
    ":grey[Le filtre « hors référentiel » ne s'applique pas à cette page : les corpus des pairs "
    "sont tirés en direct d'OpenAlex, sans moyen de savoir lesquels de leurs travaux portent un "
    "topic exclu localement. L'exemption est structurelle, ce n'est pas un bouton inerte.]"
)

OPENING_QUESTION_FR = (
    "**Quel groupe de comparaison change la lecture du positionnement de l'UL, et pourquoi ?**"
)

CONCEPT_CAPTION_FR = (
    "Quatre groupes de comparaison, jamais un classement : I-SITE (parité), IDEX (aspiration), "
    "transfrontalier et miroirs européens ne racontent pas la même histoire pour un même écart de "
    "FWCI. La taille (nombre de travaux) se lit en directionnel seulement : les identifiants "
    "directs des établissements français excluent leurs composantes en co-tutelle, ce qui gonfle "
    "l'écart apparent avec les pairs étrangers, jamais un signal de performance."
)

def _caveat_ul_reconciliation_fr(corpus_total) -> str:
    """
    NARRATIVE_CONTRACT row 115-119: from FOUR frozen UL counts (28464 / 28485 / 36819 /
    28094) down to TWO, both computed at render -- this page's own direct-id total
    (caller passes it) and the app-wide filiation corpus total, read here from
    dim_corpus_facts (same conf_state basis as the UL KPI beside it).
    """
    return (
        "Ce chiffre est le périmètre **direct** de cette page : l'identifiant OpenAlex de "
        "l'établissement, traité exactement comme celui de chaque pair. Le reste de "
        f"l'application compte le corpus par filiation ({fr_int(corpus_total)} travaux), qui "
        "inclut les structures descendantes : deux périmètres, deux nombres, toujours nommés "
        "ensemble et jamais choisis en silence."
    )


CAVEAT_UL_FILTER_ASYMMETRY_FR = (
    "L'écart entre ce décompte et un décompte en direct reste marginal : la ligne UL hérite des "
    "filtres propres au corpus, qu'un décompte pair en direct ne subit pas. L'écart est affiché "
    "plutôt que corrigé."
)


def _caveat_header_drift_fr(peer_pull_date, golden_probe_date) -> str:
    """NARRATIVE_CONTRACT row 126-133: the two pull dates, read from bench_peers
    (S-DAT's peer_pull_date / golden_probe_date columns), never hardcoded -- they
    coincide today and may diverge on a future refresh, at which point both must show."""
    return (
        f"Les corpus pairs et l'instantané de sélection portent deux dates "
        f"({peer_pull_date} et {golden_probe_date}) : elles coïncident dans cette version, "
        "elles pourront diverger lors d'un futur rafraîchissement, et elles sont alors "
        "affichées toutes les deux. L'écart entre les deux mesures est vérifié à ± 3 %, ce qui "
        "contrôle une amplitude de dérive, jamais la justesse de la recette elle-même."
    )


CAVEAT_SIZE_FR = (
    "Lecture de la ligne « Travaux » : l'identifiant direct d'un établissement français "
    "sous-compte fortement ses structures en cotutelle, ce qui n'est pas le cas des "
    "établissements étrangers. Toute comparaison de taille entre un pair français et un pair "
    "étranger porte donc une marge d'erreur asymétrique, et la taille n'est jamais un critère "
    "utilisé seul. Nantes Université exclut Centrale Nantes et l'Université Grenoble Alpes "
    "exclut Grenoble INP, alors que l'Université de Lorraine inclut ses propres écoles internes : "
    "la part ingénierie-matériaux de ces deux pairs se lit donc sous-estimée par rapport à celle "
    "de l'UL, jamais l'inverse."
)
CAVEAT_IMPACT_FR = (
    "Lecture des lignes « FWCI » et « Top 10 % » : le référentiel est français, appliqué "
    "symétriquement à tous les pairs y compris étrangers, un étalon commun fixe, jamais une "
    "norme mondiale : un pair étranger n'est pas moins bien placé parce que la France cite "
    "différemment que son propre pays."
)
# I2-10 fix: CAVEAT_IMPACT_FR above only ever excused a foreign peer scoring LOW against the
# French yardstick ("n'est pas moins bien placé"). The shipped data does the OPPOSITE on the
# EU-MIRROR rung specifically (every foreign mirror scores HIGH vs the UL median) -- the
# existing caveat has no sentence for that direction. This is the adjacent, opposite-direction
# caveat (R19 caveat-adjacency), rendered ONLY beside the EU-MIRROR panel, keeping the old one.
CAVEAT_MIRROR_HIGH_FR = (
    "Lecture des miroirs européens sur les lignes « FWCI » et « Top 10 % » : le même référentiel "
    "français fait lire mécaniquement haut un pair étranger anglophone à forte spécialisation, "
    "comparé à des strates françaises minces et peu citées. Un écart favorable ne se lit jamais "
    "comme un rapport de qualité scientifique, seulement comme l'effet du référentiel retenu."
)

# I2-13 fix: signals 5-6 ("Concentration -- 3 premiers champs" et "Dispersion de spécialisation")
# are recomputed at render from bench_peers, floor-free -- a single very small field can move the
# dispersion signal a lot. No code-level floor is applied this pass (disclosed here + the method
# note, never silently absorbed into the number).
CAVEAT_SHAPE_SIGNALS_FR = (
    "Lecture des lignes « Concentration -- 3 premiers champs » et « Dispersion de spécialisation "
    "» : aucun plancher de taille de champ n'est appliqué avant ce calcul, si bien qu'un champ à "
    "très faible effectif peut peser autant qu'un champ à fort effectif dans l'écart-type mesuré. "
    "Deux signaux de forme du portefeuille, jamais un score de qualité."
)

NO_NOTABLE_GAP_FR = "Aucun écart notable sur ce groupe de comparaison."

WORKSHOP_OVERRIDE_FR = (
    "Le jeu de pairs de chaque groupe reste modifiable par l'établissement : ajouter ou retirer "
    "un pair est une édition du registre des pairs, sans aucune modification de code."
)


# =============================================================================
# Data
# =============================================================================
@st.cache_resource
def _load_bench_peers() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "bench_peers.parquet")


def _snapshot_date(bench: pd.DataFrame) -> str:
    # G2 : jamais une date plausible en repli -- "?" reste honnête, une date figee
    # etiquetterait faussement une donnee rafraichie.
    return str(bench["snapshot_date"].iloc[0]) if len(bench) else "?"


def _entity_registry(bench: pd.DataFrame) -> pd.DataFrame:
    """One row per entity: entity_id, entity_name, rung, country -- read straight off the
    deployed table (denormalised on every row), never re-reading the CSV registry from the app."""
    return (
        bench[["entity_id", "entity_name", "rung", "country"]]
        .drop_duplicates("entity_id")
        .set_index("entity_id")
    )


def _fr_ratio(val, decimals: int = 2) -> str:
    """French-decimal ratio (no thousands grouping needed, values < 10): 0.252 -> '0,25'."""
    if val is None or pd.isna(val):
        return "n/a"
    return f"{float(val):.{decimals}f}".replace(".", ",")


# =============================================================================
# Rung-synthesis signal table (R13 item 1) -- 6 entity-level signals recomputed from bench_peers
# =============================================================================
def _build_signal_table(bench: pd.DataFrame, conf_state: str) -> pd.DataFrame:
    """
    One row per entity (UL + 9 peers), the 6 rung-synthesis signals -- built fresh from the
    deployed `bench_peers` table every render (no new pipeline table: everything here is an
    in-page aggregation of already-shipped columns, same discipline as the OVERLAY_MATRIX
    "EXISTING (same-row)" convention).
    """
    allrows = bench[(bench["node_level"] == "all") & (bench["conf_state"] == conf_state)].copy()
    allrows["coverage_pct"] = allrows["works_with_indicators"] / allrows["works"] * 100
    allrows["pptop10_pct"] = allrows["pptop10_fr_share"] * 100

    fld = bench[(bench["node_level"] == "field") & (bench["conf_state"] == conf_state)].copy()
    top3 = (
        fld.groupby("entity_id")["share_of_entity"]
        .apply(lambda s: s.nlargest(3).sum() * 100)
        .rename("top3_share_pct")
    )
    lq_std = fld.groupby("entity_id")["lq_vs_france"].std().rename("lq_std")

    sig = (
        allrows.set_index("entity_id")[
            ["entity_name", "rung", "works", "coverage_pct", "fwci_fr_mean",
             "fwci_fr_median", "pptop10_pct"]
        ]
        .join(top3)
        .join(lq_std)
    )
    return sig


def _signals(show_fwci_mean: bool, n_fields: int) -> list[dict]:
    """
    The 6 rung-synthesis signals (R13 item 1: "5-7 signals ... JUSTIFY the chosen 5-7 in your
    progress file"). R14 median-first: `fwci_fr_median` is the default key; the mean is a
    hidden-by-default optional swap (never a 7th permanent row). `n_fields` is read from
    `bench_peers` at render (NARRATIVE_CONTRACT row 270) -- never a hardcoded field count.
    """
    fwci_key = "fwci_fr_mean" if show_fwci_mean else "fwci_fr_median"
    fwci_label = "FWCI (réf. France), moyenne" if show_fwci_mean else "FWCI (réf. France), médiane"
    fwci_short = "FWCI, moy." if show_fwci_mean else "FWCI, méd."
    return [
        dict(key="works", label="Travaux (identifiant direct)", short="Travaux",
             fmt=fr_int, unit=""),
        dict(key="coverage_pct", label="Couverture d'indicateurs", short="Couverture",
             fmt=lambda v: fr_pct(v, 1), unit=""),
        dict(key=fwci_key, label=fwci_label, short=fwci_short,
             fmt=lambda v: _fr_ratio(v, 2), unit=""),
        dict(key="pptop10_pct", label="Part Top 10 % (réf. France)", short="Top 10 %",
             fmt=lambda v: fr_pct(v, 1), unit=""),
        dict(key="top3_share_pct", label="Concentration -- 3 premiers champs", short="Top-3 champs",
             fmt=lambda v: fr_pct(v, 1), unit=""),
        dict(key="lq_std",
             label=f"Dispersion de spécialisation (écart-type du quotient de localisation, "
                   f"{n_fields} champs)",
             short="Dispersion LQ", fmt=lambda v: _fr_ratio(v, 2), unit=""),
    ]


def _global_signal_ranges(sig_df: pd.DataFrame, signals: list[dict]) -> dict[str, tuple[float, float]]:
    """
    ONE x-range per signal, computed across ALL entities (UL + all 9 peers, every rung) so the
    same signal reads on the SAME scale in every one of the 4 rung small multiples -- a reader can
    compare a band's position across rungs directly, not just within one.
    """
    ranges: dict[str, tuple[float, float]] = {}
    for s in signals:
        vals = sig_df[s["key"]].dropna().tolist()
        if not vals:
            ranges[s["key"]] = (0.0, 1.0)
            continue
        lo, hi = min(vals), max(vals)
        span = hi - lo
        pad = span * 0.12 if span > 0 else max(abs(hi) * 0.1, 1.0)
        ranges[s["key"]] = (lo - pad, hi + pad)
    return ranges


def _ul_inside_band_on_every_signal(sig_df: pd.DataFrame, rung: str, ul_id: str,
                                     signals: list[dict]) -> bool:
    """I2-14 fix: True iff UL's value sits inside the [min, max] peer band on EVERY one
    of the 6 signals for this rung -- a null result stated on-screen ("aucun écart
    notable"), never left silent (a silent null reads as a broken chart, not a finding).
    A signal with no peer value (empty band) is skipped, not counted as an exception --
    it does not exist to compare against. n=1 rungs collapse the band to a single point,
    so this is True only on an exact tie, which is the correct, unforced behaviour."""
    if ul_id not in sig_df.index:
        return False
    peers = sig_df[sig_df["rung"] == rung]
    for s in signals:
        vals = peers[s["key"]].dropna().tolist()
        if not vals:
            continue
        ul_val = sig_df.loc[ul_id, s["key"]]
        if pd.isna(ul_val):
            continue
        if not (min(vals) <= ul_val <= max(vals)):
            return False
    return True


def _fwci_median_mean_bridge(sig_df: pd.DataFrame, ul_id: str) -> str:
    """I2-09 fix: bridges the ~4x gap between the FWCI-median signal (default view) and
    the two OTHER FWCI means already published elsewhere in the app (this page's own
    toggle-revealed mean, and METHODES §4's canonical-corpus mean) -- both numbers
    recomputed live from `sig_df` (never hardcoded), so a future data refresh cannot
    silently drift this sentence out of sync with the chart it explains."""
    med = sig_df.loc[ul_id, "fwci_fr_median"] if ul_id in sig_df.index else None
    mean = sig_df.loc[ul_id, "fwci_fr_mean"] if ul_id in sig_df.index else None
    if med is None or mean is None or pd.isna(med) or pd.isna(mean):
        return ""
    return (
        f"Lecture de la ligne « FWCI, méd. » : une médiane à {_fr_ratio(med)} ne dit pas que "
        "l'UL est citée au quart de la moyenne française. Les citations s'agglutinent aux "
        "valeurs basses, ce qui tire mécaniquement toute médiane de FWCI bien sous 1, même pour "
        f"un corpus proche de la moyenne. La moyenne, disponible via le bouton ci-dessus, vaut "
        f"{_fr_ratio(mean)} sur ce périmètre direct ; la note de méthode publie une autre "
        "moyenne sur le corpus par filiation, plus large. L'écart entre les deux tient au "
        "périmètre, jamais à un désaccord sur le niveau de citation."
    )


def _rung_forest_figure(sig_df: pd.DataFrame, rung: str, ul_id: str, signals: list[dict],
                         x_ranges: dict[str, tuple[float, float]]) -> go.Figure:
    """
    One small multiple per rung (R13): 6 stacked rows, one per signal, each its own x-axis
    (units differ -- count/%/ratio) but SHARED across the 4 rungs via `x_ranges`. Exactly 3 mark
    layers, reused identically on every row: (1) peer min-max band [grey line], (2) peer median
    [grey diamond] -- collapsing to a single point when a rung has only 1 peer (FR-IDEX, XBORDER),
    never a fabricated band -- and (3) the UL point [blue dot]. NO rank, no league table: peers
    are never shown individually here, only the aggregate band/median (a peer-level breakdown is
    the drill-down's job).
    """
    peers = sig_df[sig_df["rung"] == rung]
    n_peers = len(peers)
    n_rows = len(signals)
    fig = make_subplots(rows=n_rows, cols=1, vertical_spacing=0.12)

    peer_legend_name = "Pairs (min-max, médiane ◆)" if n_peers >= 2 else "Seul pair du groupe (◆)"

    for i, s in enumerate(signals, start=1):
        key, fmt, unit = s["key"], s["fmt"], s["unit"]
        vals = peers[key].dropna().tolist()
        ul_val = sig_df.loc[ul_id, key] if ul_id in sig_df.index else None

        if len(vals) >= 2:
            vmin, vmax, vmed = min(vals), max(vals), float(pd.Series(vals).median())
            fig.add_trace(go.Scatter(
                x=[vmin, vmax], y=[0, 0], mode="lines",
                line=dict(color=PEER_GREY, width=7),
                hovertext=f"Étendue pairs (n={len(vals)}) : {fmt(vmin)}{unit} à {fmt(vmax)}{unit}",
                hoverinfo="text", showlegend=False, name="",
            ), row=i, col=1)
            fig.add_trace(go.Scatter(
                x=[vmed], y=[0], mode="markers",
                marker=dict(symbol="diamond", size=10, color=PEER_GREY,
                            line=dict(width=1, color="white")),
                hovertext=f"Médiane pairs (n={len(vals)}) : {fmt(vmed)}{unit}",
                hoverinfo="text", showlegend=(i == 1), name=peer_legend_name,
            ), row=i, col=1)
        elif len(vals) == 1:
            fig.add_trace(go.Scatter(
                x=[vals[0]], y=[0], mode="markers",
                marker=dict(symbol="diamond", size=10, color=PEER_GREY,
                            line=dict(width=1, color="white")),
                hovertext=f"Seul pair du groupe : {fmt(vals[0])}{unit}",
                hoverinfo="text", showlegend=(i == 1), name=peer_legend_name,
            ), row=i, col=1)
        else:
            fig.add_annotation(text="n/a", x=0, y=0, xref=f"x{i}", yref=f"y{i}", showarrow=False,
                                font=dict(size=10, color=PEER_GREY))

        if ul_val is not None and pd.notna(ul_val):
            fig.add_trace(go.Scatter(
                x=[ul_val], y=[0], mode="markers",
                marker=dict(symbol="circle", size=13, color=FOCAL_BLUE,
                             line=dict(width=1.2, color="white")),
                hovertext=f"UL : {fmt(ul_val)}{unit}",
                hoverinfo="text", showlegend=(i == 1), name="UL",
            ), row=i, col=1)

        xr = x_ranges.get(key)
        fig.update_xaxes(range=list(xr) if xr else None, row=i, col=1,
                          tickfont=dict(size=9), showgrid=True, gridcolor="#EEEEEE")
        fig.update_yaxes(range=[-1, 1], tickvals=[0], ticktext=[s["short"]],
                          tickfont=dict(size=10), showgrid=False, zeroline=False, row=i, col=1)

    fig.update_layout(
        height=n_rows * 48 + 60,
        margin=dict(t=28, l=118, r=16, b=10),
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(size=10)),
        showlegend=True,
    )
    return fig


# =============================================================================
# Drill-down chart builder -- the dot-ratio grammar (VIZ_SPEC 2.8 T4b row, unchanged form)
# =============================================================================
def dot_ratio_chart(df: pd.DataFrame, entity_ids: list[str], value_col: str, node_names: list[str],
                     node_ids: list[str], x_title: str, log_x: bool, ref_x: float | None,
                     ref_label: str, hover_suffix: str, fmt: str) -> go.Figure:
    """
    One row per node (field or subfield), one trace per entity -- UL in focal blue at the row
    centre, every peer in the SAME grey tone at a small fixed vertical offset (stable across
    filter changes: offsets are assigned from the FULL peer roster, not the currently-visible
    subset, so a peer's row position never jumps when another peer is toggled off). Direct label
    on every dot (VIZ_SPEC T4b: "direct labels ... never a new identity colour").
    """
    n = len(node_ids)
    row_of = {nid: i for i, nid in enumerate(node_ids)}
    peer_order = [e for e in SHORT_LABEL if e != UL_ENTITY_ID]
    offsets = {}
    span = 0.34
    for i, pid in enumerate(peer_order):
        offsets[pid] = -span + (2 * span) * i / max(1, len(peer_order) - 1)
    offsets[UL_ENTITY_ID] = 0.0

    fig = go.Figure()
    for entity_id in entity_ids:
        sub = df[df["entity_id"] == entity_id].set_index("node_id")
        xs, ys, texts, hover = [], [], [], []
        for nid in node_ids:
            if nid not in sub.index:
                continue
            val = sub.loc[nid, value_col]
            if pd.isna(val):
                continue
            xs.append(float(val))
            ys.append(row_of[nid] + offsets.get(entity_id, 0.0))
            texts.append(SHORT_LABEL.get(entity_id, entity_id))
            works = sub.loc[nid, "works"]
            hover.append(f"{sub.loc[nid, 'entity_name']}<br>{value_col}: {val:{fmt}}{hover_suffix}"
                          f"<br>Travaux: {int(works):,}")
        if not xs:
            continue
        is_ul = entity_id == UL_ENTITY_ID
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers+text", text=texts,
            textposition="middle right" if not is_ul else "middle left",
            textfont=dict(size=10, color=FOCAL_BLUE if is_ul else "#5A5F66"),
            marker=dict(
                size=13 if is_ul else 8,
                color=FOCAL_BLUE if is_ul else PEER_GREY,
                line=dict(width=1.2 if is_ul else 0.5, color="white"),
            ),
            hovertext=hover, hoverinfo="text", showlegend=False, name="",
        ))

    if ref_x is not None:
        fig.add_vline(x=ref_x, line_dash="dash", line_color=FRANCE_REF_LINE,
                       annotation_text=ref_label, annotation_position="top")

    fig.update_layout(
        xaxis=dict(type="log" if log_x else "linear", title=x_title),
        yaxis=dict(
            tickmode="array", tickvals=list(range(n)), ticktext=node_names,
            range=[-0.6, n - 0.4],
        ),
        height=max(420, n * 34 + 120),
        margin=dict(t=30, l=10, r=90, b=40),
        template="plotly_white",
    )
    return fig


def _topn_query_controls(key: str, ordered_df: pd.DataFrame, name_col: str,
                          default_n: int = 10) -> pd.DataFrame:
    """
    R13 item 2 / R11: top-N-default + free-text query + "afficher plus", reused from
    `lib.ranked`'s PURE helpers (`filter_by_query`, `depth_slice`) over a chart's node list.
    `ranked_table()` itself is table-shaped (search + member-mask + `st.dataframe`) and not
    reused directly -- the dot-ratio chart is a scatter, not a dataframe, so only the two pure
    slicing primitives are wired here, same "zero recompute on a materialized frame" contract.

    `ordered_df` must already be sorted by the caller so that its FIRST `default_n` rows are the
    most workshop-relevant ones (here: most distinctive vs the France reference, not merely the
    alphabetically- or ID-first ones) -- the query can still reach any row beyond that depth.
    """
    # P6-R6 : recherche masquee sous 50 lignes (ranked.QUERY_MIN_N) -- les 26 champs
    # et la poignee de sous-champs par champ restent toujours sous ce seuil.
    query = ""
    if ranked.should_show_query_box(len(ordered_df)):
        query = st.text_input("Rechercher :", "", key=f"{key}_query")
    filtered = ranked.filter_by_query(ordered_df, query, [name_col])
    expanded = st.session_state.get(f"{key}_expanded", False)
    visible = ranked.depth_slice(filtered, expanded, default_n)
    if len(filtered) > default_n and not expanded:
        if st.button(ranked.MORE_LABEL, key=f"{key}_more_btn"):
            st.session_state[f"{key}_expanded"] = True
            st.rerun()
    return visible


# =============================================================================
# Sidebar + header (R19: opens on one FR question-sentence; titles read as answers)
# =============================================================================
ctrl = controls.sidebar()
include_conference = ctrl["include_conference"]
artifact_on = ctrl[controls.ARTIFACT_TOGGLE_KEY]
CONF_STATE = "all" if include_conference else "no_conf"
active_subset = ctrl.get("perimeter_subset", "all")

st.title("🧭 Benchmark")
st.markdown(OPENING_QUESTION_FR)
st.info(S9_BANNER_FR)
if artifact_on:
    st.caption(ARTIFACT_EXEMPT_CAPTION_FR)
controls.filtered_by_strip(page="benchmark")  # not an overlay surface (peers have no I-SITE concept, matrix §14)
if active_subset != "all":
    controls.perimeter_disclosure_strip()

bench = _load_bench_peers()
SNAPSHOT_DATE = _snapshot_date(bench)
registry = _entity_registry(bench)

# Deux dates de tirage (S-DAT, colonnes bench_peers) : coincident aujourd'hui, elles
# divergeront a un futur rafraichissement, et seront alors affichees toutes les deux.
_peer_pull_date = str(bench["peer_pull_date"].iloc[0]) if len(bench) else "?"
_golden_probe_date = str(bench["golden_probe_date"].iloc[0]) if len(bench) else "?"
CAVEAT_HEADER_DRIFT_FR = _caveat_header_drift_fr(_peer_pull_date, _golden_probe_date)

_EXPORT_STATE = exports.ExportState(
    snapshot=SNAPSHOT_DATE, conf=include_conference, artifact=artifact_on,
    subset="all", artifact_applied=False,   # this table is exempt by construction -- never "applied"
)

# =============================================================================
# UL KPI row (caveat-adjacency: direct-id reconciliation + filter asymmetry + header drift)
# =============================================================================
_ul_all = bench[(bench["entity_id"] == UL_ENTITY_ID) & (bench["node_level"] == "all")
                & (bench["conf_state"] == "all")]
_ul_works = int(_ul_all["works"].iloc[0]) if not _ul_all.empty else 0
_ul_direct_url = links.openalex_url(UL_ENTITY_ID, scope="direct")

# Deux nombres UL, jamais quatre (NARRATIVE_CONTRACT row 115-119) : le direct-id de
# cette page (au-dessus) et le corpus par filiation, meme conf_state ("all", comme
# _ul_all ci-dessus), lu ici depuis dim_corpus_facts, jamais une valeur figee.
_corpus_facts = get_corpus_facts_df()
_corpus_row = _corpus_facts.loc[_corpus_facts["conf_state"] == "all"]
_corpus_total = int(_corpus_row["corpus_works"].iloc[0]) if not _corpus_row.empty else None
CAVEAT_UL_RECONCILIATION_FR = _caveat_ul_reconciliation_fr(_corpus_total)

col_kpi, col_link = st.columns([6, 1])
with col_kpi:
    st.metric(f"Travaux UL (identifiant direct, {window_label()})", fr_int(_ul_works))
with col_link:
    st.markdown("<div style='margin-top:28px;'>" + links.link_icon_html(_ul_direct_url) + "</div>",
                unsafe_allow_html=True)
st.caption(f":grey[{CAVEAT_UL_RECONCILIATION_FR}]")
st.caption(f":grey[{CAVEAT_UL_FILTER_ASYMMETRY_FR}]")
st.caption(f":grey[{CAVEAT_HEADER_DRIFT_FR}]")

st.markdown("---")
st.markdown(f"> {CONCEPT_CAPTION_FR}")

# =============================================================================
# Rung synthesis (R13 item 1) -- the first screen: UL vs rung median + min-max band, 6 signals
# =============================================================================
st.markdown("## L'UL face à la médiane et à l'étendue de chaque groupe")
st.markdown(
    "**Comment lire.** Un panneau par groupe de comparaison. Sur chaque ligne, la barre grise "
    "couvre l'étendue des pairs du groupe, le losange leur médiane, et le point bleu situe "
    "l'Université de Lorraine. Aucun score global, aucun rang : six signaux lus séparément, sur "
    "une échelle commune d'un groupe à l'autre."
)
show_fwci_mean = st.toggle(
    "Afficher la moyenne FWCI (optionnel, sensible aux valeurs extrêmes)",
    value=False, key="bench_fwci_mean_toggle",
)
_n_fields = int(
    bench.loc[(bench["node_level"] == "field") & (bench["conf_state"] == CONF_STATE), "node_id"]
    .nunique()
)
SIGNALS = _signals(show_fwci_mean, _n_fields)
sig_df = _build_signal_table(bench, CONF_STATE)
X_RANGES = _global_signal_ranges(sig_df, SIGNALS)

_grid = [st.columns(2), st.columns(2)]
for (r, c), rung in zip([(0, 0), (0, 1), (1, 0), (1, 1)], RUNGS):
    n_peers = int((sig_df["rung"] == rung).sum())
    with _grid[r][c]:
        st.markdown(f"**{RUNG_LABELS_FR[rung]}** · {n_peers} pair(s) de référence")
        fig = _rung_forest_figure(sig_df, rung, UL_ENTITY_ID, SIGNALS, X_RANGES)
        st.plotly_chart(fig, use_container_width=True)
        # I2-11 fix (partial absorb): a band drawn from 1-2 peers is not a distribution --
        # say so explicitly next to the panel it qualifies, instead of letting the shared
        # min-max/median grammar imply a population that does not exist at this size.
        if n_peers <= 2:
            st.caption(f":grey[n={n_peers} pair(s) -- lecture directe, pas une distribution.]")
        # I2-10 fix: the opposite-direction caveat, adjacent to the ONE rung it qualifies.
        if rung == "EU-MIRROR":
            st.caption(f":grey[{CAVEAT_MIRROR_HIGH_FR}]")
        # I2-14 fix: a null result (UL inside the band on all 6 signals) is information,
        # not nothing -- state it, rather than leave the reader to wonder why nothing here
        # stands out.
        if _ul_inside_band_on_every_signal(sig_df, rung, UL_ENTITY_ID, SIGNALS):
            st.caption(f":grey[{NO_NOTABLE_GAP_FR}]")

st.markdown(
    "**Pourquoi cet indicateur.** Un même écart change de sens selon le groupe : face à un panel "
    "de parité, il interroge la trajectoire ; face à un panel d'aspiration, il mesure une "
    "distance assumée. Le choix des groupes appartient à l'établissement, l'outil ne le classe "
    "pas."
)
st.caption(f":grey[{CAVEAT_SIZE_FR}]")
st.caption(f":grey[{CAVEAT_IMPACT_FR}]")
_fwci_bridge = _fwci_median_mean_bridge(sig_df, UL_ENTITY_ID)
if _fwci_bridge:
    st.caption(f":grey[{_fwci_bridge}]")
st.caption(f":grey[{CAVEAT_SHAPE_SIGNALS_FR}]")

_cov_rows = bench[(bench["node_level"] == "all") & (bench["conf_state"] == "all")]
_cov_rows = _cov_rows.assign(coverage_pct=_cov_rows["works_with_indicators"] / _cov_rows["works"] * 100)
_low_cov = _cov_rows[_cov_rows["coverage_pct"] < 95]
if not _low_cov.empty:
    _low_lines = "; ".join(
        f"{r['entity_name']} ({r['coverage_pct']:.1f} %)" for _, r in _low_cov.iterrows()
    )
    st.warning(
        f"Lecture de la ligne « Couverture » : couverture d'indicateurs (travaux dont "
        f"l'indicateur de citation est calculable, rapportés au total) sous 95 % pour : "
        f"{_low_lines}. Ces entités ont une part plus importante de travaux dans des strates "
        f"françaises fines ou absentes, donc une base d'indicateurs plus réduite."
    )
else:
    st.caption(
        f":grey[Lecture de la ligne « Couverture » : couverture d'indicateurs ≥ 95 % pour les "
        f"{fr_int(len(_cov_rows))} entités (travaux dont l'indicateur de citation est calculable, "
        "rapportés au total, niveau global). Les écarts d'impact ci-dessus ne viennent pas d'une "
        "base de calcul dégradée.]"
    )

st.caption(f":grey[{WORKSHOP_OVERRIDE_FR}]")

_sig_export = sig_df.reset_index().rename(columns={"index": "entity_id"})
# I2-12 fix (partial absorb, LENS_ABSORPTION_pass5.md): exports stay verification data by
# doctrine (G8: the workshop holds override power and needs the values) -- R13 bans a rank
# DISPLAY, not data access. Absorbed only: the method sheet states plainly what this export
# is, on its OWN ExportState (never the page's shared `_EXPORT_STATE`, which backs three
# other exports below that this sentence does not describe).
_SYNTHESIS_EXPORT_STATE = exports.ExportState(
    snapshot=SNAPSHOT_DATE, conf=include_conference, artifact=artifact_on,
    subset="all", artifact_applied=False,
    method=(
        "Synthèse des 6 signaux par groupe de comparaison (R13) -- données de vérification, "
        "pas un classement."
    ),
)
exports.attach_download(
    st, _sig_export[["entity_id", "entity_name", "rung"] + [s["key"] for s in SIGNALS]],
    "benchmark", "synthese-rangs", _SYNTHESIS_EXPORT_STATE,
)

# =============================================================================
# Peer reference table (R13 item 5: deep link "beside peer totals") -- never sorted by volume
# =============================================================================
st.markdown("#### Les pairs, un par un")
st.caption(
    f"Chaque pair est vérifiable en direct sur OpenAlex (identifiant direct, {window_label()}, "
    "cinq types de publication) : le lien rouvre la requête vivante derrière son total."
)
_peer_rows = []
for rung in RUNGS:
    _peers_in_rung = registry[(registry["rung"] == rung)].sort_index()
    for pid, row in _peers_in_rung.sort_values("entity_name").iterrows():
        prow = sig_df.loc[pid] if pid in sig_df.index else None
        if prow is None:
            continue
        _peer_rows.append({
            "Pair": row["entity_name"],
            "Groupe": RUNG_LABELS_FR.get(rung, rung),
            "Travaux": fr_int(prow["works"]),
            "Couverture": fr_pct(prow["coverage_pct"], 1),
            "OpenAlex": links.openalex_url(pid, scope="direct"),
        })
_peer_table = pd.DataFrame(_peer_rows)
st.dataframe(
    _peer_table, use_container_width=True, hide_index=True,
    column_config={
        "OpenAlex": st.column_config.LinkColumn("Vérifier", display_text="↗",
                                                  help=links.LINK_TOOLTIP_FR),
    },
)

# =============================================================================
# Drill-down (R13 item 2): the pass-4 all-dots detail, behind an expander, fewer default peers
# =============================================================================
with st.expander("Vérifier une spécialisation précise, champ par champ"):
    st.markdown("### Sélection des pairs")
    c_rung, c_entity = st.columns([1, 2])
    with c_rung:
        rung_sel = st.multiselect(
            "Groupes de comparaison", options=RUNGS, default=DEFAULT_DRILLDOWN_RUNGS,
            format_func=lambda r: RUNG_LABELS_FR.get(r, r), key="bench_rung_sel",
        )
    candidate_ids = registry[registry["rung"].isin(rung_sel)].index.tolist()
    candidate_ids = [i for i in candidate_ids if i != UL_ENTITY_ID]
    candidate_labels = {i: f"{SHORT_LABEL.get(i, i)} -- {registry.loc[i, 'entity_name']}" for i in candidate_ids}
    with c_entity:
        entity_sel = st.multiselect(
            "Pairs affichés (l'UL reste toujours affichée)", options=candidate_ids,
            default=candidate_ids, format_func=lambda i: candidate_labels.get(i, i),
            key=f"bench_entity_sel_{'-'.join(sorted(rung_sel))}",
        )
    active_entity_ids = [UL_ENTITY_ID] + entity_sel
    st.caption(f":grey[{len(entity_sel)}/{len(candidate_ids)} pair(s) affiché(s) dans ces groupes + UL "
               f"-- le filtre conférence de la barre latérale s'applique comme sur le reste de l'appli.]")

    # R18 : un seul bascule pilote les deux panneaux LQ vs France (A et B, meme
    # grammaire) -- log par defaut, jamais applique au panneau C (echelle de part,
    # deja lineaire par construction).
    _lq_axis_type = log_linear_toggle("bench_lq_axis_toggle", label="échelle linéaire (LQ vs France)")
    _lq_log_x = _lq_axis_type == "log"

    # -------------------------------------------------------------------------
    # Panel A -- field-level dot-ratio: LQ vs France, top-10-most-distinctive default
    # -------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("#### Spécialisation par champ vs France")
    st.markdown("""
**Comment lire ce graphique** -- une ligne par champ. x = *Location Quotient* (LQ) vs la
population française de référence (ligne pointillée = France = 1 : à droite, sur-représenté à
l'entité par rapport à la France ; à gauche, sous-représenté). Point bleu = UL (repère focal) ;
points gris = pairs sélectionnés, un label direct par point, jamais une nouvelle couleur
d'identité par pair. Les champs les plus distinctifs pour l'UL (les plus loin de France = 1)
s'affichent par défaut ; « afficher plus » déploie la liste complète.
""")

    df_field = bench[(bench["node_level"] == "field") & (bench["conf_state"] == CONF_STATE)
                     & (bench["entity_id"].isin(active_entity_ids))].copy()
    _ul_field = df_field[(df_field["entity_id"] == UL_ENTITY_ID) & df_field["lq_vs_france"].notna()].copy()
    _ul_field["abs_dev"] = (_ul_field["lq_vs_france"] - 1.0).abs()
    _field_order_full = _ul_field.sort_values("abs_dev", ascending=False)

    if _field_order_full.empty:
        st.info("Aucune ligne de spécialisation disponible pour ce périmètre/état de conférence.")
    else:
        _visible_field = _topn_query_controls("bench_topn_field_lq", _field_order_full, "node_name")
        _display_field = _visible_field.sort_values("lq_vs_france", ascending=True)
        node_ids_field = _display_field["node_id"].tolist()
        node_names_field = _display_field["node_name"].tolist()

        fig_a = dot_ratio_chart(
            df_field, active_entity_ids, "lq_vs_france", node_names_field, node_ids_field,
            x_title="LQ vs France", log_x=_lq_log_x, ref_x=1.0, ref_label="France = 1",
            hover_suffix="", fmt=".2f",
        )
        st.plotly_chart(fig_a, use_container_width=True)
        exports.attach_download(
            st, df_field[["entity_id", "entity_name", "rung", "node_name", "works", "share_of_entity",
                          "lq_vs_france", "works_with_indicators"]],
            "benchmark", "specialisation-field", _EXPORT_STATE,
        )

    # -------------------------------------------------------------------------
    # Panel B -- subfield drill (scoped, §6.6) for one selected field
    # -------------------------------------------------------------------------
    st.markdown("#### Zoom sous-champs")
    if not _field_order_full.empty:
        field_options = _field_order_full.sort_values("node_name")["node_name"].tolist()
        picked_field_name = st.selectbox("Champ :", field_options, key="bench_field_drill")
        picked_field_id = _field_order_full.loc[
            _field_order_full["node_name"] == picked_field_name, "node_id"].iloc[0]

        df_subfield = bench[(bench["node_level"] == "subfield") & (bench["conf_state"] == CONF_STATE)
                             & (bench["entity_id"].isin(active_entity_ids))].copy()
        _topics = pd.read_parquet(DATA_DIR / "all_topics.parquet", columns=["field_id", "subfield_id"])
        _topics = _topics.assign(field_id=_topics["field_id"].astype(str),
                                  subfield_id=_topics["subfield_id"].astype(str))
        _valid_subs = set(_topics.loc[_topics["field_id"] == str(picked_field_id), "subfield_id"])
        df_subfield = df_subfield[df_subfield["node_id"].isin(_valid_subs)]

        _ul_sub = df_subfield[(df_subfield["entity_id"] == UL_ENTITY_ID) & df_subfield["lq_vs_france"].notna()].copy()
        _ul_sub["abs_dev"] = (_ul_sub["lq_vs_france"] - 1.0).abs()
        _sub_order_full = _ul_sub.sort_values("abs_dev", ascending=False)

        if _sub_order_full.empty:
            st.info(f"Aucune ligne de sous-champ disponible sous {picked_field_name} pour ce périmètre.")
        else:
            _visible_sub = _topn_query_controls("bench_topn_subfield", _sub_order_full, "node_name")
            _display_sub = _visible_sub.sort_values("lq_vs_france", ascending=True)
            node_ids_sub = _display_sub["node_id"].tolist()
            node_names_sub = _display_sub["node_name"].tolist()

            fig_b = dot_ratio_chart(
                df_subfield, active_entity_ids, "lq_vs_france", node_names_sub, node_ids_sub,
                x_title="LQ vs France", log_x=_lq_log_x, ref_x=1.0, ref_label="France = 1",
                hover_suffix="", fmt=".2f",
            )
            st.plotly_chart(fig_b, use_container_width=True)
            exports.attach_download(
                st, df_subfield[["entity_id", "entity_name", "rung", "node_name", "works",
                                  "share_of_entity", "lq_vs_france", "works_with_indicators"]],
                "benchmark", "specialisation-subfield", _EXPORT_STATE, node=("f", picked_field_id),
            )

    # -------------------------------------------------------------------------
    # Panel C -- PPtop10_FR by field, same dot-ratio grammar, top-10-most-distinctive default
    # -------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("#### Part de travaux Top 10 % (référentiel France) par champ")
    st.markdown("""
**Comment lire ce graphique** -- même grammaire que ci-dessus : une ligne par champ, x = part de
travaux atteignant le seuil Top 10 % du référentiel français (seuil défini par rang de centile).
Ligne pointillée : repère France, autour de 10 % par construction de la population de référence,
ce qui n'en fait pas une valeur attendue pour une entité donnée. Les cellules sous le seuil de
fiabilité (moins de 30 travaux avec indicateur) sont absentes du graphique, jamais affichées à
zéro. Les champs les plus distinctifs pour l'UL s'affichent par défaut ; « afficher plus »
déploie la liste complète.
""")

    df_field_pp = bench[(bench["node_level"] == "field") & (bench["conf_state"] == CONF_STATE)
                         & (bench["entity_id"].isin(active_entity_ids))].copy()
    df_field_pp["pptop10_pct"] = df_field_pp["pptop10_fr_share"] * 100
    _ul_field_pp = df_field_pp[(df_field_pp["entity_id"] == UL_ENTITY_ID) & df_field_pp["pptop10_pct"].notna()].copy()
    _ul_field_pp["abs_dev"] = (_ul_field_pp["pptop10_pct"] - 10.0).abs()
    _field_order_pp_full = _ul_field_pp.sort_values("abs_dev", ascending=False)

    if _field_order_pp_full.empty:
        st.info("Aucune ligne Top 10 % disponible pour ce périmètre/état de conférence.")
    else:
        _visible_pp = _topn_query_controls("bench_topn_field_pptop10", _field_order_pp_full, "node_name")
        _display_pp = _visible_pp.sort_values("pptop10_pct", ascending=True)
        node_ids_pp = _display_pp["node_id"].tolist()
        node_names_pp = _display_pp["node_name"].tolist()

        fig_c = dot_ratio_chart(
            df_field_pp, active_entity_ids, "pptop10_pct", node_names_pp, node_ids_pp,
            x_title="Part Top 10 % (référentiel France, %)", log_x=False, ref_x=10.0,
            ref_label="France ≈ 10%", hover_suffix="%", fmt=".1f",
        )
        st.plotly_chart(fig_c, use_container_width=True)
        exports.attach_download(
            st, df_field_pp[["entity_id", "entity_name", "rung", "node_name", "works",
                              "pptop10_fr_share", "works_with_indicators"]],
            "benchmark", "pptop10-field", _EXPORT_STATE,
        )

st.markdown("---")
st.caption(
    f"Instantané : {SNAPSHOT_DATE} · fenêtre {window_label()} · pairs : registre tenu par "
    "l'établissement."
)
