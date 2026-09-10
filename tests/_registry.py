# tests/_registry.py
"""Registre partage des builders de graphiques, passe 7a (BUILD_PLAN.md P18).

`BUILDERS` est une liste de triplets `(chart_key, family, build_fn)` :
  - `chart_key` : cle verbatim de `docs/contract_fragments/chart_keys_pass7.md`
    (la MEME cle nomme l'entree `tooltip_spec.yaml`, les dicts READING/HOVER de
    `lib/copy_fr.py` et l'argument `name=` passe a `fig_cache.cached_figure`).
  - `family`   : une valeur parmi champ, sous_champ, topic, labo, pays,
    partenaire, annee, scatter (docs/contract_fragments/lib_api_pass7.md).
  - `build_fn` : callable sans argument qui retourne un `go.Figure` construit
    sur des DONNEES REELLES de `Streamlit/data/` (jamais un fixture
    synthetique -- paire CNRS pour les graphiques de paire) -- c'est le
    contrat que consomment `tests/test_chart_layout.py` et
    `tests/test_hover_spec.py`.

Cree VIDE ici (S-EVAL, W1). S-LIB-A y ajoute ses builders (W2) ; les streams
de page peuvent y ajouter les leurs, deja cables, en W3.

---------------------------------------------------------------------------
AJOUT S-LIB-A (W2) -- ce que ce fichier porte en plus, et pourquoi ICI

Les trames que les builders consomment sont CALCULEES PAR LA PAGE (le contrat
lib est explicite : « Pages shape the frames ... builders never read
parquet »). Les pages de la passe 7 n'existent pas encore (W3), donc quelqu'un
doit composer ces trames pour que `test_chart_layout.py` et
`test_hover_spec.py` aient de quoi mordre. Elles sont composees ici, une fois,
plutot que recopiees dans chacun des trois fichiers qui en ont besoin
(`test_charts.py`, les deux tests ci-dessus, et `tests/ui/render_lib_pass7.py`)
-- un seul endroit ou la composition peut etre fausse.

Trois contraintes tenues :
  - `plotly` n'est importe qu'en `TYPE_CHECKING` au niveau module, et `lib`
    n'est touche QUE dans le corps d'un `build_fn` : importer ce fichier reste
    aussi bon marche que le squelette de S-EVAL.
  - le basculement `sys.modules['lib']` -> `Streamlit/lib` (F-SYSMOD,
    tests/conftest.py) est fait PAR le `build_fn` et RESTAURE en sortie, avec
    l'implementation unique de conftest : `test_hover_spec.py` appelle ces
    callables sans avoir bascule lui-meme, et aucun appel ne doit laisser la
    session pytest avec le mauvais `lib` lie.
  - les colonnes CALCULEES PAR LA PAGE que le yaml suppose (P7_LIBA addendum :
    `share_phares_joint`, `fwci_partner_absent`, `domain_name`, ...) portent
    ici EXACTEMENT les noms de l'addendum, pour que les pages de W3 les
    reprennent sans traduction.

Substitutions assumees, faute de colonne sur disque a ce stade (elles ne
changent AUCUNE geometrie -- la seule question que ces tests posent) :
  - `n_phares_ul` = `thematic_overview.pubs_total x pct_top10` (le taux
    top 10 % France REEL du champ) -- meme substitution que les rendus A/B de
    S-ST (VIZ_SPEC_pass7 §6, « proxy disclosure ») ;
  - `fwci_joint` / `n_fwci_joint` au grain champ = mediane et masse des
    cellules `ptn_topics.fwci_fr_median_cell` du champ (aucun agregat champ
    n'est stocke) ;
  - `vol_partner_only` = `partner_total_windowed x baseline_partner_share
    - co_works`, plancher 0 (P8, la derivation que la page appliquera).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    import plotly.graph_objects as go

BUILDERS: list[tuple[str, str, Callable[[], "go.Figure"]]] = []

# ===========================================================================
# S-LIB-A -- constantes de la paire de reference et acces au disque
# ===========================================================================
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "Streamlit" / "data"

PARTNER_ID = "I1294671590"          # CNRS -- la paire de reference de la passe
CONF_STATE = "all"                  # etat de conference par defaut
SUBSET_ID = "all"                   # perimetre par defaut (I-SITE est un overlay, pas un filtre)
JOINT_FLOOR = 5                     # plancher de co-publications conjointes (P8)
PLANE_FLOOR = 5                     # plancher d'une cellule paire x topic (P9)
PLANE_TOP_N = 50                    # borne haute du curseur N des deux plans
PORTAGE_TOP_N = 6                   # zoom_portage : labos + « Autres »
SUBFIELD_TOP_N = 30                 # zoom_balance_bars sous_champ : top 30 (P8)


def _swap():
    """Bascule `sys.modules['lib']` vers `Streamlit/lib` avec l'unique
    implementation de `tests/conftest.py` (importee par chemin : ce fichier
    doit rester utilisable hors collecte pytest)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from conftest import restore_lib, swap_lib_to_streamlit
    finally:
        sys.path.pop(0)
    return swap_lib_to_streamlit(), restore_lib


def _read(name: str):
    import pandas as pd
    return pd.read_parquet(DATA_DIR / "{0}.parquet".format(name))


# ===========================================================================
# Taxonomie et libelles (une lecture par appel, jamais un cache global : ces
# builders tournent une poignee de fois dans une suite, pas dans une boucle)
# ===========================================================================
def _taxonomy():
    """(champs, sous-champs) indexes par id : nom, champ parent, domaine."""
    t = _read("all_topics")
    fields = (t[["field_id", "field_name", "domain_id", "domain_name"]]
              .drop_duplicates("field_id").set_index("field_id"))
    subs = (t[["subfield_id", "subfield_name", "field_id", "field_name",
               "domain_id", "domain_name"]]
            .drop_duplicates("subfield_id").set_index("subfield_id"))
    return fields, subs


def _copy_fr():
    from lib import copy_fr
    return copy_fr


def _hover_col(key: str, mode: str, values_per_row):
    """Une chaine de survol par ligne, LIBELLES PRIS DANS `copy_fr.HOVER_LABELS`
    (source unique, egale au yaml -- `test_hover_spec.py` epingle l'egalite) et
    valeurs deja mises en forme par `lib.hover`. Une valeur `None` retire sa
    ligne (« a false `when` withholds the line »), y compris toute ligne
    `drapeau` dont la condition ne tient pas."""
    from lib import hover as hv
    labels = list(_copy_fr().HOVER_LABELS[key][mode])
    out = []
    for values in values_per_row:
        if len(values) != len(labels):
            raise AssertionError(
                "{0} [{1}] : {2} valeurs pour {3} libelles".format(
                    key, mode, len(values), len(labels)))
        out.append(hv.hover_lines(list(zip(labels, values))))
    return out


# ===========================================================================
# Trames -- une fonction par cle du registre
# ===========================================================================
def _pair_summary():
    s = _read("ptn_summary")
    row = s[(s["partner_id"] == PARTNER_ID) & (s["conf_state"] == CONF_STATE)
            & (s["subset_id"] == SUBSET_ID)]
    return row.iloc[0]


def _pair_nodes(level: str):
    """Les lignes `ptn_fields` de la paire au niveau demande, enrichies du nom
    de noeud, du champ parent et du domaine."""
    f = _read("ptn_fields")
    d = f[(f["partner_id"] == PARTNER_ID) & (f["node_level"] == level)
          & (f["conf_state"] == CONF_STATE)].copy()
    d["node_id"] = d["node_id"].astype(int)
    fields, subs = _taxonomy()
    src = fields if level == "field" else subs
    name_col = "field_name" if level == "field" else "subfield_name"
    d["node_name"] = d["node_id"].map(src[name_col])
    d["domain_id"] = d["node_id"].map(src["domain_id"])
    d["domain_name"] = d["node_id"].map(src["domain_name"])
    if level == "subfield":
        d["field_name"] = d["node_id"].map(subs["field_name"])
    return d.dropna(subset=["node_name"])


def frame_field_companion():
    """`zoom_field_companion` -- compagnon volumique de la descente (§5.10)."""
    from lib import hover as hv
    d = _pair_nodes("field").sort_values("co_works", ascending=False).reset_index(drop=True)
    d["hover"] = _hover_col("zoom_field_companion", "default", [
        (r["node_name"],
         hv.fmt_int(r["co_works"]),
         hv.fmt_pct(r["share_of_pair"] * 100.0),
         hv.fmt_pct(r["baseline_ul_share"] * 100.0),
         (None if r["baseline_partner_share"] != r["baseline_partner_share"]
          else hv.fmt_pct(r["baseline_partner_share"] * 100.0)),
         (None if r["lq_vs_ul"] != r["lq_vs_ul"] else hv.fmt_score(r["lq_vs_ul"])),
         (None if not r["mom_eligible_flag"] else str(r["mom_class"])))
        for _, r in d.iterrows()])
    return d


def build_zoom_field_companion():
    saved, restore = _swap()
    try:
        from lib import charts as C, helpers as H
        d = frame_field_companion()
        return C.bars_with_gutter(
            d, family="champ", label_col="node_name", value_col="co_works",
            color=[H.get_domain_color(v) for v in d["domain_id"]])
    finally:
        restore(saved)


def frame_portage():
    """`zoom_portage` -- labos porteurs + « Autres » (§5.12)."""
    from lib import hover as hv
    import pandas as pd
    labs = _read("ptn_labs")
    d = labs[(labs["partner_id"] == PARTNER_ID) & (labs["conf_state"] == CONF_STATE)]
    d = d.sort_values("co_works", ascending=False).reset_index(drop=True)
    head = d.head(PORTAGE_TOP_N).copy()
    tail = d.iloc[PORTAGE_TOP_N:]
    if len(tail):
        head = pd.concat([head, pd.DataFrame([{
            "lab_name": "Autres",
            "co_works": float(tail["co_works"].sum()),
            "share_of_lab_attributed": float(tail["share_of_lab_attributed"].sum()),
            "nolab_works": float(d["nolab_works"].iloc[0]),
        }])], ignore_index=True)
    head["is_other"] = [False] * (len(head) - 1) + [True] if len(tail) else [False] * len(head)
    head["hover"] = _hover_col("zoom_portage", "default", [
        (r["lab_name"], hv.fmt_int(r["co_works"]),
         hv.fmt_pct(r["share_of_lab_attributed"] * 100.0),
         hv.fmt_int(r["nolab_works"]))
        for _, r in head.iterrows()])
    return head


def build_zoom_portage():
    saved, restore = _swap()
    try:
        from lib import charts as C, helpers as H
        d = frame_portage()
        colors = [H.NEUTRAL_GREY if o else H.UL_COLOR for o in d["is_other"]]
        # famille `labo_court` (suivi 1) : les libelles dessines ici sont les
        # ACRONYMES de `ptn_labs.lab_name`, pas les noms complets de `ul_labs` sur
        # lesquels la colonne `labo` (335 px) a ete mesuree -- laquelle depasse a elle
        # seule un viewport de 390 px.
        return C.bars_with_gutter(d, family="labo_court", label_col="lab_name",
                                  value_col="co_works", color=colors)
    finally:
        restore(saved)


def frame_country_companion():
    """`geo_country_companion` -- pays visibles, fenetre agregee (§5.16)."""
    from lib import hover as hv
    from lib.countries_fr import country_label
    g = _read("geo_countries")
    d = g[(g["conf_state"] == CONF_STATE) & (g["subset_id"] == SUBSET_ID)]
    agg = (d.groupby("country_code", as_index=False, observed=True)
           .agg(co_works=("co_works", "sum"), share_ul=("share_ul", "mean"),
                fwci_fr_median=("fwci_fr_median", "median"),
                isite_co_works=("isite_co_works", "sum"),
                unknown_bucket_flag=("unknown_bucket_flag", "max")))
    agg = agg.sort_values("co_works", ascending=False).reset_index(drop=True)
    agg["country_name"] = [country_label(c) for c in agg["country_code"]]
    agg["hover"] = _hover_col("geo_country_companion", "default", [
        (r["country_name"], hv.fmt_int(r["co_works"]),
         hv.fmt_pct(r["share_ul"] * 100.0),
         hv.fmt_fwci_pair(r["fwci_fr_median"], r["fwci_fr_median"], int(r["co_works"])),
         None)
        for _, r in agg.iterrows()])
    return agg


def build_geo_country_companion():
    saved, restore = _swap()
    try:
        from lib import charts as C, helpers as H
        d = frame_country_companion().head(40)
        return C.bars_with_gutter(d, family="pays", label_col="country_name",
                                  value_col="co_works", color=H.UL_COLOR,
                                  isite_col="isite_co_works", isite_on=False)
    finally:
        restore(saved)


def _cell_frame():
    """Cellules paire x topic agregees sur la fenetre, au plancher P9 --
    socle commun des deux plans."""
    t = _read("ptn_topics")
    d = t[(t["partner_id"] == PARTNER_ID) & (t["conf_state"] == CONF_STATE)]
    agg = (d.groupby("topic_id", as_index=False, observed=True)
           .agg(co_works=("co_works", "sum"), n_phares=("n_phares", "sum"),
                fwci_median=("fwci_fr_median_cell", "median"),
                frontier_score_std=("frontier_score_std", "median"),
                artifact_flag=("artifact_flag", "max")))
    agg = agg[agg["co_works"] >= PLANE_FLOOR]
    topics = _read("all_topics").set_index("topic_id")
    for col in ("topic_name", "keywords", "subfield_name", "domain_id", "domain_name"):
        agg[col] = agg["topic_id"].map(topics[col])
    agg["artifact_flag"] = agg["artifact_flag"].fillna(False).astype(bool)
    return agg.sort_values("co_works", ascending=False).reset_index(drop=True)


def frame_plane_impact():
    """`zoom_plane_impact` (§5.8) -- les topics a mediane NULLE sont retires et
    comptes par la legende de la page, jamais places a zero."""
    from lib import hover as hv
    d = _cell_frame()
    d = d[d["fwci_median"].notna()].head(PLANE_TOP_N).reset_index(drop=True)
    rows = []
    for _, r in d.iterrows():
        kw1, kw2 = hv.fmt_keywords_2x5(r["keywords"])
        rows.append((
            r["topic_name"],
            "{0}<br>{1}".format(kw1, kw2) if kw2 else kw1,
            hv.fmt_int(r["co_works"]),
            hv.fmt_fwci_pair(r["fwci_median"], r["fwci_median"], int(r["co_works"])),
            (None if r["n_phares"] != r["n_phares"] or r["n_phares"] <= 0
             else hv.fmt_int(r["n_phares"])),
            None,
            r["subfield_name"],
        ))
    d["hover"] = _hover_col("zoom_plane_impact", "volume", rows)
    return d


def build_zoom_plane_impact():
    saved, restore = _swap()
    try:
        from lib import charts as C
        return C.fig_plane_impact(frame_plane_impact())
    finally:
        restore(saved)


def frame_plane_frontier():
    """`zoom_plane_frontier` (§5.9) -- composantes du DERNIER bin
    (`dim_frontier_components.is_latest`) ; les topics non scores sont retires
    et comptes."""
    from lib import hover as hv
    d = _cell_frame()
    comp = _read("dim_frontier_components")
    latest = comp[comp["is_latest"].astype(bool)].drop_duplicates("topic_id").set_index("topic_id")
    d["expansion"] = d["topic_id"].map(latest["expansion"])
    d["acceleration"] = d["topic_id"].map(latest["acceleration"])
    d = d[d["expansion"].notna() & d["acceleration"].notna()]
    d = d.head(PLANE_TOP_N).reset_index(drop=True)
    rows = []
    for _, r in d.iterrows():
        kw1, kw2 = hv.fmt_keywords_2x5(r["keywords"])
        rows.append((
            r["topic_name"],
            "{0}<br>{1}".format(kw1, kw2) if kw2 else kw1,
            hv.fmt_score(r["expansion"]),
            hv.fmt_score(r["acceleration"]),
            hv.fmt_int(r["co_works"]),
            (None if r["frontier_score_std"] != r["frontier_score_std"]
             else hv.fmt_score(r["frontier_score_std"])),
            None,
        ))
    d["hover"] = _hover_col("zoom_plane_frontier", "frontiere", rows)
    return d


def build_zoom_plane_frontier():
    saved, restore = _swap()
    try:
        from lib import charts as C
        return C.fig_plane_frontier(frame_plane_frontier())
    finally:
        restore(saved)


def frame_reciprocity(level: str = "field"):
    """`zoom_reciprocity` (§5.13) -- les lignes a part NULLE sont retirees et
    comptees (P8) : elles ne peuvent etre placees sur aucun des deux axes, et
    un zero serait un mensonge."""
    from lib import hover as hv
    d = _pair_nodes(level)
    d = d[d["baseline_partner_share"].notna() & d["baseline_ul_share"].notna()]
    d = d.sort_values("co_works", ascending=False).reset_index(drop=True)
    d["share_ul"] = d["baseline_ul_share"] * 100.0
    d["share_partner"] = d["baseline_partner_share"] * 100.0
    d["hover"] = _hover_col("zoom_reciprocity", "champ" if level == "field" else "sous_champ", [
        (r["node_name"],
         (r["field_name"] if level == "subfield" else None),
         hv.fmt_pct(r["share_ul"]), hv.fmt_pct(r["share_partner"]),
         hv.fmt_int(r["co_works"]), hv.fmt_pct(r["share_of_pair"] * 100.0),
         r["domain_name"])
        for _, r in d.iterrows()])
    return d


def build_zoom_reciprocity():
    saved, restore = _swap()
    try:
        from lib import charts as C
        return C.reciprocity_scatter(frame_reciprocity("field"), level="champ",
                                     partner_name=str(_pair_summary()["display_name"]))
    finally:
        restore(saved)


def frame_site_reciprocity():
    """`col_reciprocity` (§5.2) -- un partenaire dont `share_p` est nulle ne
    peut pas etre place : retire et compte par la legende."""
    from lib import hover as hv
    s = _read("ptn_summary")
    d = s[(s["conf_state"] == CONF_STATE) & (s["subset_id"] == SUBSET_ID)]
    d = d[d["share_p"].notna() & d["share_ul"].notna()
          & (d["share_p"] > 0) & (d["share_ul"] > 0)].reset_index(drop=True)
    d = d.copy()
    d["share_ul"] = d["share_ul"] * 100.0
    d["share_p"] = d["share_p"] * 100.0
    d["hover"] = _hover_col("col_reciprocity", "p20", [
        (r["display_name"], hv.fmt_pct(r["share_ul"]),
         hv.fmt_pct_dagger(r["share_p"], int(r["works_with_indicators"] or 0)),
         None, hv.fmt_int(r["co_works_full"]),
         (None if r["partner_total_windowed"] != r["partner_total_windowed"]
          else hv.fmt_int(r["partner_total_windowed"])),
         str(r["type_openalex"]), str(r["country_code"]))
        for _, r in d.iterrows()])
    return d


def build_col_reciprocity():
    saved, restore = _swap()
    try:
        from lib import charts as C
        return C.site_reciprocity_scatter(frame_site_reciprocity(), floor=20)
    finally:
        restore(saved)


def frame_balance(mode: str, level: str = "field"):
    """`zoom_balance_bars` (§5.7) -- les trois volumes, les deux medianes, les
    deux comptes de phares, les drapeaux et le lien, dans l'ordre d'affichage
    (tri decroissant sur la quantite montree : la page trie, le constructeur
    preserve)."""
    import numpy as np
    from lib import hover as hv, links

    d = _pair_nodes(level)
    summary = _pair_summary()
    partner_total = float(summary["partner_total_windowed"])
    partner_name = str(summary["display_name"])

    # --- cote UL : portefeuille propre du champ (thematic_overview) --------
    ov = _read("thematic_overview")
    own = ov[ov["level"] == ("field" if level == "field" else "subfield")].copy()
    own["id"] = own["id"].astype(int)
    own = own.drop_duplicates("id").set_index("id")
    d["vol_ul_total"] = d["node_id"].map(own["pubs_total"]).astype(float)
    d["fwci_ul"] = d["node_id"].map(own["fwci_median"]).astype(float)
    d["n_phares_ul_total"] = (d["vol_ul_total"]
                              * d["node_id"].map(own["pct_top10"]).astype(float)).round()

    # --- cote conjoint et cote partenaire ---------------------------------
    d["vol_joint"] = d["co_works"].astype(float)
    d["n_phares_joint"] = d["n_phares"].astype(float)
    d["vol_ul_only"] = (d["vol_ul_total"] - d["vol_joint"]).clip(lower=0.0)
    # `n_phares_ul` est le cote UL **HORS RELATION**, exactement comme
    # `vol_ul_only` : la voie de gauche du miroir ne contient jamais ce que la
    # voie centrale contient deja, sinon le gutter (« phares UL + phares
    # conjoints », §1.2) compterait deux fois les phares conjointes.
    d["n_phares_ul"] = (d["n_phares_ul_total"] - d["n_phares_joint"]).clip(lower=0.0)
    derived = partner_total * d["baseline_partner_share"].astype(float) - d["vol_joint"]
    d["vol_partner_only"] = derived.clip(lower=0.0)
    d["partner_only_derived"] = d["vol_partner_only"].notna()

    # --- FWCI conjoint : mediane et masse des cellules topic du champ -----
    cells = _cell_frame()
    subs = _taxonomy()[1]
    cells["field_id"] = cells["topic_id"].map(_read("all_topics").set_index("topic_id")["field_id"])
    if level == "field":
        keys, cell_key = d["node_id"], cells["field_id"]
    else:
        keys, cell_key = d["node_id"], cells["topic_id"].map(
            _read("all_topics").set_index("topic_id")["subfield_id"])
    grouped = cells.assign(_k=cell_key).groupby("_k", observed=True)
    med = grouped["fwci_median"].median()
    mass = grouped["co_works"].sum()
    d["fwci_joint"] = keys.map(med).astype(float)
    d["n_fwci_joint"] = keys.map(mass).fillna(0.0).astype(float)

    d["under_floor"] = d["vol_joint"] < JOINT_FLOOR
    d["share_phares_joint"] = np.where(d["vol_joint"] > 0,
                                       d["n_phares_joint"] / d["vol_joint"] * 100.0, np.nan)
    d["fwci_partner_absent"] = True      # le FWCI propre du partenaire n'est pas mesurable
    d["phares_partner_absent"] = True    # idem pour ses publications phares

    sort_col = {"volume": "vol_joint", "fwci": "fwci_joint", "phares": "n_phares_joint"}[mode]
    d = d.sort_values(sort_col, ascending=False).reset_index(drop=True)
    if level == "subfield":
        d = d.head(SUBFIELD_TOP_N).reset_index(drop=True)

    node_kind = "field" if level == "field" else "subfield"
    d["url"] = [links.copubs_url(PARTNER_ID, node=(node_kind, int(i))) for i in d["node_id"]]
    d["link_label"] = [hv.fmt_int(v) for v in d["vol_joint"]]

    key_mode = "{0}|{1}".format(mode, "champ" if level == "field" else "sous_champ")
    if mode == "volume":
        rows = [(r["node_name"],
                 hv.fmt_joint_or_floor(r["vol_joint"]),
                 hv.fmt_pair_volumes("UL", r["vol_ul_only"], partner_name,
                                     r["vol_partner_only"], derived_b=True),
                 None,
                 hv.fmt_pct(r["share_of_pair"] * 100.0),
                 hv.fmt_pct(r["baseline_ul_share"] * 100.0),
                 (None if r["baseline_partner_share"] != r["baseline_partner_share"]
                  else hv.fmt_pct(r["baseline_partner_share"] * 100.0)))
                for _, r in d.iterrows()]
    elif mode == "fwci":
        rows = [(r["node_name"],
                 hv.fmt_fwci_pair(r["fwci_joint"], r["fwci_joint"], int(r["n_fwci_joint"])),
                 (None if r["fwci_ul"] != r["fwci_ul"] else hv.fmt_score(r["fwci_ul"])),
                 hv.fmt_joint_or_floor(r["vol_joint"]),
                 hv.fmt_int(r["n_fwci_joint"]),
                 None, None)
                for _, r in d.iterrows()]
    else:
        rows = [(r["node_name"],
                 hv.fmt_joint_or_floor(r["n_phares_joint"]),
                 (None if r["n_phares_ul"] != r["n_phares_ul"] else hv.fmt_int(r["n_phares_ul"])),
                 hv.fmt_joint_or_floor(r["vol_joint"]),
                 (None if r["share_phares_joint"] != r["share_phares_joint"]
                  else hv.fmt_pct_dagger(r["share_phares_joint"], int(r["vol_joint"]))),
                 None, None)
                for _, r in d.iterrows()]
    d["hover"] = _hover_col("zoom_balance_bars", key_mode, rows)
    return d


def _build_balance(mode: str, level: str):
    saved, restore = _swap()
    try:
        from lib import charts as C
        d = frame_balance(mode, level)
        return C.balance_bars(d, mode=mode,
                              level="champ" if level == "field" else "sous_champ",
                              partner_name=str(_pair_summary()["display_name"]))
    finally:
        restore(saved)


def build_balance_volume():
    return _build_balance("volume", "field")


def build_balance_fwci():
    return _build_balance("fwci", "field")


def build_balance_phares():
    return _build_balance("phares", "subfield")


# ===========================================================================
# Le registre lui-meme -- une entree par constructeur du contrat lib
# (`zoom_balance_bars` x3 modes = trois entrees sous la MEME cle)
# ===========================================================================
BUILDERS.extend([
    ("zoom_balance_bars", "champ", build_balance_volume),
    ("zoom_balance_bars", "champ", build_balance_fwci),
    ("zoom_balance_bars", "sous_champ", build_balance_phares),
    ("zoom_field_companion", "champ", build_zoom_field_companion),
    ("zoom_portage", "labo_court", build_zoom_portage),
    ("geo_country_companion", "pays", build_geo_country_companion),
    ("zoom_reciprocity", "scatter", build_zoom_reciprocity),
    ("col_reciprocity", "scatter", build_col_reciprocity),
    ("zoom_plane_impact", "scatter", build_zoom_plane_impact),
    ("zoom_plane_frontier", "scatter", build_zoom_plane_frontier),
])
