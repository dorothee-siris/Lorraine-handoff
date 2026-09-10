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
de page peuvent y ajouter les leurs, deja cables, en W3. Rien d'autre dans ce
fichier : ni logique, ni import lourd (plotly n'est importe qu'en
`TYPE_CHECKING`, pour ne jamais alourdir une collecte pytest qui ne
l'utilise pas).
"""
from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    import plotly.graph_objects as go

BUILDERS: list[tuple[str, str, Callable[[], "go.Figure"]]] = []
