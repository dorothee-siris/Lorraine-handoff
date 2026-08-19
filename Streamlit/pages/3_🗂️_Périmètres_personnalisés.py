"""
Périmètres personnalisés (P-V3 -- registre/gouvernance, pass 5, rulings R1 + R12, plan
stream P-A).

Authority (binding): docs/SPRINT_KICKOFF_pass5.md R1 (le filtre global de périmètre est
SUPPRIMÉ ; l'I-SITE devient une surcouche pilotée par le bouton de la barre latérale) +
R12 (habillage FR partout) + docs/OVERLAY_MATRIX.md section "3. Périmètres
personnalisés" (aucun panneau à décomposer, cette page EST le registre des périmètres).
Reprend et REBÂTIT `progress/S4_shared_layer.md` §11 ("Cleaning up the Périmètres
page's now-inert row-click-sets-global-perimeter mechanic" -- nommé là comme un
reste à faire par le stream de page). Chaque comportement partagé (barre latérale,
bannières, colonnes xa(), export) passe par Streamlit/lib/{controls,exports}.py (figés
cette passe) ; rien n'est réimplémenté ici.

Phrase de décision : après cette page, on peut dire quels périmètres existent dans
l'outil, quelle taille chacun porte, qui en détient la liste et quelle est sa
fraîcheur, mais on ne peut plus en « appliquer » un globalement : ce mécanisme a
disparu avec R1, remplacé par la surcouche I-SITE (barre latérale) pour l'I-SITE et
par ce même registre pour les futurs corpus de programme, gouvernés ici avant toute
utilisation ailleurs.

Ce qui a changé par rapport à l'ancienne version de cette page (pour mémoire, dans le
code) :
  - section 1 ("active perimeter" + sélection de ligne) : SUPPRIMÉE. Il n'y a plus de
    périmètre « actif » à afficher : `controls.sidebar()` ne renvoie plus qu'une
    constante `perimeter_subset == "all"` (S4, `lib/controls.py`).
  - le mécanisme clic-sur-une-ligne -> applique le périmètre globalement (l'ancien
    rerun-sur-sélection du tableau + résolution en tête de fichier avant
    `controls.sidebar()`) : SUPPRIMÉ. Il n'agissait plus sur rien depuis R1 (signalé,
    non retiré, par le stream de couche partagée) -- le tableau est maintenant un
    simple registre, non sélectionnable.
  - la section "Why is I-SITE a filter, not a row?" : REMPLACÉE par la note de lecture
    ci-dessous, qui explique la surcouche (et non plus un filtre).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import controls, exports, lazy, ranked
from lib.data_cache import DATA_DIR
from lib.helpers import fr_int, fr_pct

# ============================================================================
# Page config
# ============================================================================
st.set_page_config(page_title="Périmètres personnalisés | UL Bibliometrics", page_icon="\U0001F5C2", layout="wide")

st.title("\U0001F5C2️ Périmètres personnalisés")
st.caption(
    "Cette page répond à : quels périmètres existent dans l'outil, quelle taille "
    "chacun porte, qui en détient la liste, et quelle est sa fraîcheur ?"
)
st.markdown(
    "Un « **outil d'animation scientifique** » : ce registre situe chaque périmètre "
    "les uns par rapport aux autres, jamais un classement entre eux."
)

_controls_state = controls.sidebar()
include_conference = _controls_state["include_conference"]
artifact_on = _controls_state[controls.ARTIFACT_TOGGLE_KEY]
isite_overlay = _controls_state[controls.ISITE_OVERLAY_KEY]

controls.filtered_by_strip(page="perimetres_personnalises")  # not an overlay surface (this IS the I-SITE selector, matrix §3)
controls.banner()  # NEW page: the full S6.2 disclosure banner while the toggle is ON

# ============================================================================
# Data
# ============================================================================
@st.cache_data
def _load_dim_subsets() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "dim_subsets.parquet")


@st.cache_data
def _load_work_subsets() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "work_subsets.parquet")


dim_subsets = _load_dim_subsets()
SNAPSHOT_DATE = str(dim_subsets["snapshot_date"].iloc[0])


def _works_col(base: str) -> str:
    """Colonne consciente de l'état conférence, puis résolue par xa() (même motif que
    les pages Laboratoires et I-SITE)."""
    base = base if include_conference else f"{base}_noconf"
    return controls.xa(dim_subsets, base)


WORKS_COL = _works_col("n_works")
_all_row = dim_subsets.loc[dim_subsets["subset_id"] == "all"]
CORPUS_TOTAL = _all_row[WORKS_COL].iloc[0] if not _all_row.empty else pd.NA

# Recoupement I-SITE (liste DOI vs trace de subvention) : l'écart entre les deux
# lignes se lit ici comme le nombre de travaux avec trace de subvention mais hors
# liste canonique, même calcul que la page I-SITE (subset_works.parquet, tous
# types confondus, jamais un chiffre figé).
_award_slice = lazy.read_keyed(DATA_DIR / "subset_works.parquet", "subset_id", "in_isite_award")
_ISITE_AWARD_DELTA = int((~_award_slice["in_isite"]).sum()) if not _award_slice.empty else 0

_EXPORT_STATE = exports.ExportState(
    snapshot=SNAPSHOT_DATE, conf=include_conference, artifact=artifact_on,
    artifact_applied=artifact_on, method="P-V3 registre des périmètres (dim_subsets.parquet)",
)

# ============================================================================
# Section 1 -- comment lire ce registre (remplace l'ancienne section "active perimeter")
# ============================================================================
st.markdown("## Comment lire ce registre")
st.markdown(
    "Un **périmètre** est une liste évidencée, propriétaire et datée d'une partie du "
    "corpus : la liste I-SITE constituée à la main, un recoupement de subvention, ou, "
    "à venir, un corpus de programme ou un roster ORCID. Ce registre les inventorie "
    "tous, actifs ou en attente, sans en sélectionner aucun : depuis cette passe, "
    "**les périmètres ne filtrent plus l'application globalement**. La contribution "
    "I-SITE est désormais une **surcouche** pilotée par le bouton « Afficher la "
    "contribution I-SITE » de la barre latérale, visible sur les graphiques concernés "
    "sans jamais retirer de travaux de ce qui est affiché ; les futurs corpus de "
    "programme, une fois gouvernés ici, arriveront de la même façon, jamais comme un "
    "filtre global caché."
)

_n_active = int((dim_subsets["status"] == "active").sum())
_n_stub = int((dim_subsets["status"] == "stub").sum())

k1, k2, k3 = st.columns(3)
k1.metric("Périmètres actifs", fr_int(_n_active))
k2.metric("En attente (atelier)", fr_int(_n_stub))
k3.metric("Corpus de référence", fr_int(CORPUS_TOTAL))

st.markdown("---")

# ============================================================================
# Section 2 -- tbl-registry
# ============================================================================
st.markdown("## Le registre des périmètres")
st.markdown(
    "Chaque périmètre que l'outil connaît, dans un seul tableau. Les lignes en "
    "attente restent visibles avec leur statut et l'action qui leur manque, jamais "
    "masquées ; un périmètre qui ne compterait aucun travail resterait lui aussi "
    "affiché, avec sa raison."
)

# P6-R6 : la recherche ne s'affiche qu'a partir de 50 lignes (ranked.QUERY_MIN_N) ;
# le registre des perimetres en compte une poignee, elle reste donc masquee tant
# que le registre ne grandit pas jusque-la (motif partage avec les autres pages).
search = ""
if ranked.should_show_query_box(len(dim_subsets)):
    search = st.text_input(
        "Rechercher un périmètre (nom, nature, propriétaire) :", "", key="registry_search",
    )

_ROW_ORDER = ["all", "in_isite", "in_isite_award", "programme_pending", "orcid_roster_pending"]
registry = dim_subsets.copy()
registry["_order"] = registry["subset_id"].map({k: i for i, k in enumerate(_ROW_ORDER)}).fillna(99)
registry = registry.sort_values("_order")

if search:
    needle = search.strip().lower()
    haystack = (
        registry["label_fr"].astype(str) + " " + registry["kind"].astype(str) + " "
        + registry["owner"].astype(str)
    ).str.lower()
    registry = registry[haystack.str.contains(needle, na=False)]

_evidence_by_subset = _load_work_subsets().groupby("subset_id")["evidence"].first().to_dict()

_KIND_FR = {
    "baseline": "corpus de référence",
    "isite_list": "liste I-SITE (DOI)",
    "isite_award_crosscheck": "recoupement subvention (I-SITE)",
    "programme": "programme (à venir)",
    "orcid_roster": "roster ORCID (à venir)",
}
_EVIDENCE_FR = {
    "doi_list": "liste DOI",
    "award": "trace de subvention",
}
_OWNER_FR = {
    "pipeline": "pipeline",
    "GT Indicateurs": "GT Indicateurs",
    "workshop (client CODIR matrix)": "atelier (matrice CODIR client)",
    "workshop (client roster upload)": "atelier (dépôt roster client)",
}


def _evidence_label_fr(row) -> str:
    if row["status"] == "stub":
        return "en attente (atelier)"
    ev = _evidence_by_subset.get(row["subset_id"])
    return _EVIDENCE_FR.get(ev, ev) if ev else "n/a (corpus entier, aucune liste requise)"


def _note_fr(row, works_val) -> str:
    # PM1 : un périmètre à 0 travail reste affiché, avec sa raison, jamais masqué.
    if pd.notna(works_val) and works_val == 0:
        return "aucun travail apparié : liste vide à ce jour"
    return ""


display_rows = []
for _, row in registry.iterrows():
    works_val = row[WORKS_COL]
    pct = (works_val / CORPUS_TOTAL) if pd.notna(works_val) and pd.notna(CORPUS_TOTAL) and CORPUS_TOTAL else None
    display_rows.append({
        "Périmètre": row["label_fr"],
        "Nature": _KIND_FR.get(row["kind"], row["kind"]),
        # D53: a stub row's count is float("nan"), never Python None -- forcing this
        # column to float64 (below) so ProgressColumn/NumberColumn render an EMPTY
        # cell for it, not the literal text "None" a mixed-type object column would
        # show (confirmed empirically against this Streamlit build's rendering).
        "Travaux": float(works_val) if pd.notna(works_val) else float("nan"),
        # Pre-formatted FR string (fr_pct), not a numeric column: st.column_config.
        # NumberColumn renders the literal text "None" for a NaN cell under a custom
        # `format=` string on this Streamlit build (confirmed empirically -- unlike
        # ProgressColumn, which correctly renders NaN as an empty cell once the
        # column dtype is float64). A TextColumn sidesteps that rendering path.
        "% du corpus": fr_pct(pct * 100 if pct is not None else None, decimals=1),
        "Propriétaire": _OWNER_FR.get(row["owner"], row["owner"]),
        "Millésime": row["vintage_date"] if pd.notna(row["vintage_date"]) else "n/a",
        "Type de preuve": _evidence_label_fr(row),
        "Statut": "en attente (atelier)" if row["status"] == "stub" else "actif",
        "_note": _note_fr(row, works_val),
    })

display_df = pd.DataFrame(display_rows)
# Belt-and-braces on top of the float("nan") values already used above: force this
# column to float64 explicitly rather than trust dict-to-DataFrame inference, so
# ProgressColumn renders an EMPTY cell for a stub row, never the literal text "None"
# (confirmed empirically against this Streamlit build's rendering).
display_df["Travaux"] = display_df["Travaux"].astype(float)
_max_scale = int(CORPUS_TOTAL) if pd.notna(CORPUS_TOTAL) else None

if display_df.empty:
    st.info("Aucun périmètre ne correspond à cette recherche.")
else:
    st.dataframe(
        display_df.drop(columns=["_note"]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Travaux": st.column_config.ProgressColumn(
                "Travaux", min_value=0, max_value=_max_scale, format="%d",
                help="Échelle commune et linéaire entre tous les périmètres : le corpus "
                     "entier et le recoupement subvention diffèrent d'un facteur ~40, un "
                     "axe partagé garde cet écart honnête plutôt que de l'aplatir.",
            ),
            "Nature": st.column_config.TextColumn(
                "Nature",
                help="corpus de référence (corpus entier) . liste I-SITE (liste DOI à la "
                     "main) . recoupement subvention (trace ANR) . programme / roster ORCID "
                     "(en attente).",
            ),
        },
    )
    for r in display_rows:
        if r["_note"]:
            st.caption(f":grey[{r['Périmètre']} : {r['_note']}]")

    exports.attach_download(
        st, registry.drop(columns=["_order"]), "perimetres", "registre", _EXPORT_STATE,
    )

st.markdown(
    "**Pourquoi cet indicateur.** Un périmètre est une liste datée, avec un propriétaire : "
    "l'application ne fabrique jamais un périmètre à partir d'un mot-clé. Ce registre est "
    "la réponse à la question « d'où vient ce sous-ensemble, et qui en répond »."
)

st.caption(
    f"Recoupement : l'écart de {fr_int(_ISITE_AWARD_DELTA)} travaux entre les deux lignes "
    "I-SITE ci-dessus (liste de DOI contre trace de subvention) est détaillé sur la page "
    "I-SITE."
)

# ---- action atelier, pour les 2 lignes en attente ----------------------------------
_stub_rows = registry[registry["status"] == "stub"]
if not _stub_rows.empty:
    st.markdown("**Action attendue de l'atelier :**")
    for _, r in _stub_rows.iterrows():
        st.markdown(f"- **{r['label_fr']}** : {_OWNER_FR.get(r['owner'], r['owner'])}.")

st.markdown("---")

# ============================================================================
# Section 3 -- créneau de contribution (PM5/PM6, désactivé)
# ============================================================================
st.markdown("## Ajouter un périmètre (à venir)")
st.markdown(
    "Deux familles de périmètres sont réservées dans le registre ci-dessus, les "
    "**corpus de programme** et les **rosters ORCID**, mais chacune attend une liste "
    "côté client avant de se peupler. Le contrôle ci-dessous est un emplacement "
    "réservé : il est désactivé, et rien de déposé ici n'est enregistré ni appliqué "
    "à une vue."
)
st.file_uploader(
    "Déposer une liste de périmètre (codes programme ou roster ORCID)",
    type=["csv", "xlsx"],
    disabled=True,
    key="perimeter_upload_stub",
    help=(
        "Format attendu une fois le dépôt actif : une ligne par travail (identifiée "
        "par son DOI) ou par personne (identifiée par son ORCID), rattachée à l'un "
        "des périmètres en attente listés ci-dessus, avec la nature de la preuve "
        "utilisée (code de collection HAL ou liste ORCID)."
    ),
)
st.caption(
    ":grey[Le chemin d'alimentation des corpus de programme et le périmètre exact "
    "des listes ORCID restent des décisions d'atelier : tant qu'elles ne sont pas "
    "prises, ces deux périmètres restent affichés en attente plutôt que remplis par "
    "défaut.]"
)

st.markdown("---")

# ============================================================================
# Section 4 -- note de lecture (remplace "Why is I-SITE a filter, not a row?")
# ============================================================================
st.markdown("## Pourquoi un registre, et non plus un filtre ?")
st.markdown(
    "Un périmètre ne filtre pas l'application : la contribution I-SITE s'affiche en "
    "surcouche, posée sur le total déjà visible (une teinte plus sombre de la même "
    "couleur, la même grammaire partout), plutôt que de faire disparaître le corpus "
    "derrière un filtre. Le bouton « Afficher la contribution I-SITE » de la barre "
    "latérale porte ce rôle."
)
st.markdown(
    "Le recoupement subvention (**Périmètre I-SITE, trace subvention ANR**) reste une "
    "famille de **vérification**, jamais fusionnée dans la liste canonique : les "
    "travaux qu'il ajoute sont un signal pour rafraîchir la liste I-SITE, pas une part "
    "supplémentaire du périmètre. Le détail, travail par travail, vit sur la page "
    "I-SITE."
)
st.caption(
    "Les structures que l'Université de Lorraine ne liste pas mais qu'OpenAlex lui "
    "rattache restent sélectionnables sur la page Laboratoires, signalées « hors "
    "liste »."
)

st.markdown("---")
st.caption(
    f"Instantané : {SNAPSHOT_DATE} · registre : {fr_int(len(dim_subsets))} périmètres, "
    f"dont {fr_int(_n_active)} actifs et {fr_int(_n_stub)} en attente."
)
