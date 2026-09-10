# Streamlit/lib/copy_fr.py
"""
Copie francaise des graphiques : ligne de lecture, libelles de survol, aides des
tuiles, legendes de reserve et libelles de controle.

MODULE PUR : aucun import (streamlit compris). C'est un dictionnaire, pas un
composant. `lib/reading.py` le lit (`reading_text(chart_key, mode, **fills)`),
`lib/hover.py` lit `CAPTIONS`, les pages lisent `KPI_HELP`, `CAPTIONS` et `LABELS`.

CONTRAT (BUILD_PLAN P2/P3, ruling P7-R6)
----------------------------------------
* Les cles de graphique et les valeurs de mode viennent du registre
  `docs/contract_fragments/chart_keys_pass7.md`, verbatim.
* Convention de mode, identique dans les quatre dictionnaires :
    - graphique sans mode           -> la cle `"default"` ;
    - un seul axe de controle       -> la valeur du controle (`"p10"`, `"log"`,
      `"champ"`, `"volume"`...) ;
    - deux axes de controle         -> la cle appariee `"<axe1>|<axe2>"`, dans
      l'ordre ou le registre les nomme : `zoom_balance_bars` = `"<mode>|<niveau>"`
      (`"volume|champ"`), `ex_partner_reciprocity` = `"<type>|<perimetre>"`
      (`"education|fr"`).
* `READING[cle][mode]` = une ou deux phrases francaises, rendues entre les
  controles et le graphique. Elles disent COMMENT LIRE, jamais QUOI CONCLURE.
* Trous de formatage : `lib/reading.py` appelle `.format(**fills)`. Les trous
  utilises par chaque cle sont declares dans `READING_PLACEHOLDERS` (le test
  echoue sur un trou non declare, et sur un trou declare mais jamais utilise).
    - `{window}`     libelle de fenetre calcule depuis la donnee ;
    - `{partenaire}` nom d'affichage du partenaire de la page ;
    - `{bin_prev}` / `{bin_last}` libelles des deux dernieres periodes de la
      reference de frontiere, nommes depuis la donnee ;
    - `{floor}`      plancher de co-publications du controle en vigueur ;
    - `{n_hidden}`   nombre de lignes affichees dont la mesure partenaire manque ;
    - `{max_ids}`    plafond d'identifiants d'une liste (`links.IDLIST_MAX`), jamais retape
      en mots (lens D14).
  `KPI_HELP` et `CAPTIONS` portent aussi des trous : ils sont declares dans
  `KPI_PLACEHOLDERS` et `CAPTION_PLACEHOLDERS`, sur le meme contrat que READING (une page
  qui affiche l'un de ces textes appelle `.format(**fills)` avec exactement ces cles).
* AUCUNE valeur de donnee, AUCUNE annee, AUCUN chiffre litteral (hors jetons de
  liste blanche : « top 10 % », « >= 10 »), AUCUN terme de la ban-list
  (`docs/contract_fragments/narrative_banlist.txt`) : les planchers dont le
  chiffre n'est pas sur la liste blanche s'ecrivent en mots (« sous cinq
  co-publications »), ce sont des constantes de methode, pas des valeurs lues.
  Verifie par `tests/test_hover_spec.py` (et par `tests/test_narrative.py`, dont
  la portee est etendue a ce fichier).
* PORTEE du controle narratif : les VALEURS des dictionnaires exportes ci-dessous
  (READING, KPI_HELP, CAPTIONS, LABELS, HOVER_LABELS). Le present docstring et les
  commentaires du module sont du code, jamais affiches -- ils nomment donc des
  fichiers et des colonnes, comme n'importe quel commentaire du depot.
* `HOVER_LABELS` est la SOURCE UNIQUE des libelles de survol : le test assere son
  EGALITE avec `docs/tooltip_spec.yaml` (`charts.<cle>.lines[].label`, y compris
  la premiere chaine vide de l'entite et celles des lignes `drapeau`). Choix
  retenu : un test d'egalite, PAS de generation de code -- les deux fichiers
  restent lisibles et modifiables a la main, et la divergence est une erreur de
  test nommee, jamais un silence.
* `KPI_HELP` est de meme aserte egal aux `help_lines` des tuiles du yaml,
  jointes par une espace.
"""

# ---------------------------------------------------------------------------
# 1. Ligne de lecture, par graphique et par mode (P3)
# ---------------------------------------------------------------------------
READING: dict[str, dict[str, str]] = {

    # ------------------------------------------------ Page 8 -- Collaborations
    "col_hub_companion": {
        "default": (
            "Chaque barre donne le volume de co-publications du partenaire de la ligne sur "
            "{window}, tous types de documents ; la colonne de droite répète ce volume en "
            "chiffres. Le classement suit le volume, jamais l'indicateur de citation."
        ),
    },
    "col_reciprocity": {
        "p20": (
            "Chaque bulle est un partenaire retenu au-delà de {floor} co-publications : "
            "l'axe horizontal donne le poids de la relation dans le collaboratif de l'UL, "
            "l'axe vertical son poids dans la production propre du partenaire. La diagonale "
            "marque l'équilibre des deux poids, et un carré signale une part partenaire "
            "plafonnée."
        ),
        "p10": (
            "Le plancher abaissé à {floor} co-publications fait entrer des relations plus "
            "minces : les deux parts y sont plus instables, et un point proche du bord se "
            "déplace beaucoup d'une mesure à l'autre. La lecture des axes et de la diagonale "
            "ne change pas."
        ),
    },
    "col_consortium_bars": {
        "default": (
            "Une barre par signataire du périmètre I-SITE, dans un ordre fixe : le volume "
            "compte les co-publications distinctes avec l'UL sur {window}. Les périmètres des "
            "signataires se recouvrent, les barres ne s'additionnent donc pas."
        ),
    },
    "col_momentum_quadrant": {
        "log": (
            "Chaque point compare la part annualisée du partenaire dans le collaboratif de "
            "l'UL entre les deux fenêtres de {window}. L'échelle logarithmique rapproche les "
            "petits partenaires ; la classe affichée tient compte du recentrage et du seuil "
            "de significativité."
        ),
        "lineaire": (
            "Même comparaison entre les deux fenêtres de {window}, à écart absolu : les "
            "partenaires de fort volume occupent l'essentiel du champ et les petits se tassent "
            "près de l'origine. La classe affichée, elle, ne dépend pas de l'échelle."
        ),
    },

    # ----------------------------------------------- Page 9 -- Zoom partenaire
    "zoom_yearly": {
        "default": (
            "Le nombre de co-publications avec {partenaire} par année, compté depuis zéro ; "
            "la teinte plus sombre isole la part relevant du périmètre I-SITE, sans retirer "
            "aucun travail du total."
        ),
    },
    "zoom_share_spark": {
        "default": (
            "La part de {partenaire} dans l'ensemble des co-publications de l'UL, année par "
            "année : une pente qui monte signale un poids relatif croissant, pas nécessairement "
            "un volume croissant."
        ),
    },
    "zoom_balance_bars": {
        "volume|champ": (
            "Une ligne par champ : au centre les co-publications de la relation, de part et "
            "d'autre les travaux propres de chaque établissement hors relation. Le côté "
            "partenaire est mesuré sur le décompte propre du partenaire dans ce nœud, jamais "
            "projeté depuis le poids de ce nœud dans son portefeuille."
        ),
        "volume|sous_champ": (
            "Les mêmes trois volumes sur les sous-champs les plus fournis de la relation, "
            "classés par volume conjoint. Parmi eux, {n_hidden} n'ont pas de volume "
            "partenaire mesuré : leur côté droit reste vide, et ils gardent leur volume "
            "conjoint."
        ),
        "fwci|champ": (
            "Une ligne par champ : le FWCI médian des co-publications de la relation, face à "
            "celui du portefeuille propre de l'UL, contre le repère de la référence française. "
            "Le FWCI propre de {partenaire} n'étant pas disponible, la lecture est à un seul "
            "côté."
        ),
        "fwci|sous_champ": (
            "Même lecture sur les sous-champs les plus fournis de la relation, où les strates "
            "sont plus minces : un écart y bascule avec quelques travaux, et une cellule sous "
            "son plancher n'affiche pas de valeur. Parmi les sous-champs affichés, {n_hidden} "
            "n'ont pas de mesure du côté partenaire."
        ),
        "phares|champ": (
            "Une ligne par champ : les publications phares de la relation, face à celles du "
            "portefeuille propre de l'UL. Le côté partenaire reste vide, faute d'un décompte "
            "propre disponible."
        ),
        "phares|sous_champ": (
            "Même lecture sur les sous-champs les plus fournis de la relation ; sous le "
            "plancher de la relation, le compte n'est pas affiché plutôt que ramené à zéro. "
            "Parmi les sous-champs affichés, {n_hidden} n'ont pas de mesure du côté "
            "partenaire."
        ),
    },
    "zoom_plane_impact": {
        "volume": (
            "Chaque bulle est un topic de la relation : l'axe horizontal donne le volume de "
            "co-publications en échelle logarithmique, l'axe vertical le FWCI médian contre la "
            "référence française. La sélection retient les topics de plus fort volume, et "
            "l'aire de la bulle répète ce volume."
        ),
        "fwci": (
            "Mêmes axes, sélection différente : les topics au FWCI médian le plus élevé. Un "
            "topic mince peut donc monter très haut, et l'aire de la bulle est le garde-fou de "
            "cette lecture."
        ),
        "frontiere": (
            "Mêmes axes, sélection différente : les topics dont la composante de frontière "
            "de la dernière période disponible est la plus élevée, un critère indépendant du "
            "volume comme de la citation. Ce n'est pas le score composite moyenné sur toutes "
            "les périodes, qui est affiché ailleurs dans l'outil."
        ),
        "phares": (
            "Mêmes axes, sélection différente : les topics portant le plus de publications "
            "phares. La sélection favorise mécaniquement les topics volumineux, et l'axe "
            "vertical dit s'ils sont aussi cités."
        ),
    },
    "zoom_plane_frontier": {
        "volume": (
            "Chaque bulle est un topic de la relation : l'axe horizontal donne l'expansion du "
            "topic dans la science mondiale depuis la période de référence, l'axe vertical son "
            "élan récent ({bin_prev} face à {bin_last}). La sélection retient les topics de "
            "plus fort volume conjoint."
        ),
        "fwci": (
            "Mêmes axes : un topic peut être installé de longue date sans accélérer, ou "
            "accélérer depuis une position basse. La sélection retient les topics au FWCI "
            "médian le plus élevé."
        ),
        "frontiere": (
            "Mêmes axes : l'expansion de longue durée en horizontale, l'élan récent "
            "({bin_prev} face à {bin_last}) en verticale. La sélection retient les topics "
            "dont la composante de frontière de la dernière période est la plus élevée, "
            "jamais le score composite moyenné sur toutes les périodes."
        ),
        "phares": (
            "Mêmes axes : l'expansion de longue durée en horizontale, l'élan récent "
            "({bin_prev} face à {bin_last}) en verticale. La sélection retient les topics "
            "portant le plus de publications phares."
        ),
    },
    "zoom_field_companion": {
        "default": (
            "Une barre par champ, classée par volume de co-publications de la relation ; la "
            "colonne de droite répète le volume en chiffres."
        ),
    },
    "zoom_subfield_companion": {
        "default": (
            "Une barre par sous-champ de la relation, classée par volume conjoint ; le champ "
            "parent et les parts propres des deux côtés se lisent dans l'infobulle."
        ),
    },
    "zoom_theme_zoom": {
        "default": (
            "Les co-publications de la relation dans le champ retenu, année par année ; la "
            "teinte plus sombre isole la part relevant du périmètre I-SITE."
        ),
    },
    "zoom_reciprocity": {
        "champ": (
            "Chaque bulle est un champ : l'axe horizontal donne le poids de ce champ dans le "
            "portefeuille propre de {partenaire}, l'axe vertical son poids dans le portefeuille "
            "propre de l'UL — deux poids de même nature, c'est ce qui rend la diagonale "
            "lisible. L'aire suit le volume conjoint."
        ),
        "sous_champ": (
            "Les mêmes deux poids sur les sous-champs les plus fournis de la relation. Parmi "
            "les sous-champs affichés, {n_hidden} n'ont pas de poids partenaire mesuré et ne "
            "portent donc pas de bulle."
        ),
    },
    "zoom_portage": {
        "default": (
            "Part de chaque structure lorraine dans les travaux de la relation qui portent une "
            "attribution de structure ; les travaux sans structure attribuée sont comptés à "
            "part, hors de ce rapport."
        ),
    },

    # ---------------------------------------- Page 6 -- Exploration thématique
    "ex_partner_reciprocity": {
        "education|fr_intl": (
            "Chaque bulle est un partenaire de l'UL sur ce nœud de la taxonomie, établissements "
            "d'enseignement et de recherche seulement, tous pays confondus. L'aire suit le "
            "volume de co-publications, et la part propre du partenaire manque quand sa "
            "production n'est pas mesurée sur ce nœud."
        ),
        "education|fr": (
            "Même vue restreinte aux établissements d'enseignement et de recherche français : "
            "le corpus de référence change, les positions ne sont donc pas comparables à celles "
            "de la vue tous pays."
        ),
        "education|intl": (
            "Même vue restreinte aux établissements d'enseignement et de recherche hors France : "
            "le corpus de référence change, les positions ne sont donc pas comparables à celles "
            "de la vue tous pays."
        ),
        "tous|fr_intl": (
            "Tous types d'établissements, entreprises et hôpitaux compris, tous pays confondus : "
            "l'aire suit le volume de co-publications. Le type d'établissement vient de la "
            "source et n'est pas ré-arbitré."
        ),
        "tous|fr": (
            "Tous types d'établissements, France seulement : la comparaison avec la vue "
            "enseignement et recherche mesure le poids des entreprises et des hôpitaux sur ce "
            "nœud."
        ),
        "tous|intl": (
            "Tous types d'établissements, hors France seulement : la comparaison avec la vue "
            "enseignement et recherche mesure le poids des entreprises et des hôpitaux sur ce "
            "nœud."
        ),
    },
    "ex_partner_tables": {
        "default": (
            "Une ligne par partenaire sur ce nœud, classée par volume de co-publications ; la "
            "flèche ouvre la liste vivante des co-publications correspondantes."
        ),
    },

    # ------------------------------------------------- Page 10 -- Géographie
    "geo_country_companion": {
        "default": (
            "Une barre par pays, classée par volume de co-publications de l'UL sur {window} ; "
            "la colonne de droite répète le volume en chiffres."
        ),
    },
    "geo_map": {
        "default": (
            "Chaque cercle est un pays et son aire suit le volume de co-publications de l'UL "
            "sur {window}. La projection déforme les surfaces : la comparaison se lit sur les "
            "cercles et l'infobulle, jamais sur la place occupée à l'écran."
        ),
    },
    "geo_unigr_bars": {
        "default": (
            "Une barre par membre du groupement transfrontalier : le volume compte les "
            "co-publications distinctes avec l'UL sur {window}, et les périmètres des membres "
            "se recouvrent."
        ),
    },

    # ------------------------------------------ Pages 2 et 4 -- graphiques ODD
    "lab_sdg_bars": {
        "default": (
            "Une barre par objectif de développement durable, dans la couleur officielle de "
            "l'objectif : la part rapporte au corpus entier de la structure, travaux jamais "
            "tagués compris. Changer de méthode d'attribution change les deux comptages."
        ),
    },
    "pf_sdg_bars": {
        "default": (
            "Une barre par objectif de développement durable, dans la couleur officielle de "
            "l'objectif ; le compte porte sur les publications du corpus taguées sur cet "
            "objectif. Un même travail peut relever de plusieurs objectifs, les barres ne "
            "s'additionnent donc pas."
        ),
    },
    "pf_sdg_peers_scatter": {
        "default": (
            "Un point par établissement du jeu de pairs, pour chaque objectif : la part "
            "rapporte au corpus propre de l'établissement, jamais au corpus lorrain. Le jeu de "
            "pairs a été arrêté en atelier, la comparaison ne vaut que dans ce jeu."
        ),
    },
}

# Trous de formatage attendus par chaque graphique (union sur ses modes). Une page
# qui appelle `reading_text` doit fournir exactement ces cles.
READING_PLACEHOLDERS: dict[str, tuple[str, ...]] = {
    "col_hub_companion": ("window",),
    "col_reciprocity": ("floor",),
    "col_consortium_bars": ("window",),
    "col_momentum_quadrant": ("window",),
    "zoom_yearly": ("partenaire",),
    "zoom_share_spark": ("partenaire",),
    "zoom_balance_bars": ("partenaire", "n_hidden"),
    "zoom_plane_impact": (),
    "zoom_plane_frontier": ("bin_prev", "bin_last"),
    "zoom_field_companion": (),
    "zoom_subfield_companion": (),
    "zoom_theme_zoom": (),
    "zoom_reciprocity": ("partenaire", "n_hidden"),
    "zoom_portage": (),
    "ex_partner_reciprocity": (),
    "ex_partner_tables": (),
    "geo_country_companion": ("window",),
    "geo_map": ("window",),
    "geo_unigr_bars": ("window",),
    "lab_sdg_bars": (),
    "pf_sdg_bars": (),
    "pf_sdg_peers_scatter": (),
}


# Trous attendus par les aides de tuile et par les legendes (meme contrat que
# READING_PLACEHOLDERS : la page appelle `.format(**fills)` avec exactement ces cles).
KPI_PLACEHOLDERS: dict[str, tuple[str, ...]] = {
    'col_kpi_partners': ('window',),
    'col_kpi_intl': ('window',),
    'col_kpi_company': ('window',),
    'col_kpi_collab': ('window',),
    'zoom_kpi_copubs': ('window',),
    'zoom_kpi_share_ul': ('window',),
    'zoom_kpi_share_p': ('window',),
    'zoom_kpi_fwci': (),
    'zoom_kpi_isite': ('window',),
    'zoom_kpi_momentum': ('window',),
    'zoom_kpi_phares': ('window', 'max_ids'),
}

CAPTION_PLACEHOLDERS: dict[str, tuple[str, ...]] = {
    'PHARES_PROXY': ('max_ids',),
    'DERIVED_PARTNER_VOLUME': (),
    'FRONTIER_VINTAGES': (),
    'SUBFIELD_NULL_SHARE': (),
    'PLANE_UNSCORED': (),
    'THIN_PARTNER': (),
    'JOINT_UNDER_FLOOR': (),
}

# ---------------------------------------------------------------------------
# 2. Aides des tuiles (le « ? » d'un KPI) -- egales aux `help_lines` du yaml
# ---------------------------------------------------------------------------
KPI_HELP: dict[str, str] = {
    "col_kpi_partners": (
        "Nombre d'établissements distincts co-signant au moins dix travaux de l'Université de "
        "Lorraine sur {window}, tous types de documents. Le plancher écarte les relations d'une "
        "ou deux publications, trop instables pour porter une part ; il ne retire aucun travail "
        "du corpus affiché ailleurs. Un établissement absorbé par un autre est compté sous son "
        "successeur, jamais deux fois."
    ),
    "col_kpi_intl": (
        "Part des travaux de l'Université de Lorraine sur {window} portant au moins un "
        "établissement situé dans un autre pays. Dénominateur : le corpus entier de "
        "l'établissement sur la fenêtre, pas ses seuls travaux collaboratifs. Le repère affiché "
        "à côté est la même part calculée sur la France entière, sur la même fenêtre et les "
        "mêmes types de documents."
    ),
    "col_kpi_company": (
        "Part des travaux de l'Université de Lorraine sur {window} portant au moins un "
        "établissement de type entreprise au sens de la source. Dénominateur : le corpus entier "
        "de l'établissement sur la fenêtre. Le type d'établissement vient de la source et n'est "
        "pas ré-arbitré : une filiale de recherche publique classée entreprise reste comptée "
        "comme telle."
    ),
    "col_kpi_collab": (
        "Part des travaux de l'Université de Lorraine sur {window} portant au moins un autre "
        "établissement, français ou étranger. Dénominateur : le corpus entier de l'établissement "
        "sur la fenêtre. C'est ce numérateur qui sert de dénominateur à la part UL de chaque "
        "partenaire. Les structures internes de l'établissement ne comptent pas comme un autre "
        "établissement."
    ),
    "zoom_kpi_copubs": (
        "Travaux de l'Université de Lorraine sur {window} co-signés avec ce partenaire, tous "
        "types de documents. Compte de travaux distincts : un travail co-signé par plusieurs "
        "établissements du même groupe n'est compté qu'une fois."
    ),
    "zoom_kpi_share_ul": (
        "Les co-publications avec ce partenaire rapportées au corpus collaboratif de "
        "l'Université de Lorraine sur {window}. Dénominateur : les travaux de l'établissement "
        "portant au moins un autre établissement. Les parts des partenaires ne se somment pas, "
        "un même travail pouvant en porter plusieurs."
    ),
    "zoom_kpi_share_p": (
        "Les mêmes co-publications rapportées à la production propre du partenaire sur "
        "{window}. Dénominateur : la production du partenaire sur la fenêtre telle que la source "
        "la mesure, tous types de documents et tous co-auteurs confondus. Ce dénominateur n'est "
        "renseigné que sur le corpus entier : la part reste donc lue sur cette base, même quand "
        "un filtre est actif ailleurs sur la page."
    ),
    "zoom_kpi_fwci": (
        "Médiane, sur les co-publications de la relation, du rapport entre les citations d'un "
        "travail et la moyenne de sa strate française. Strate de normalisation : sous-champ × "
        "année de publication × type de document ; articles et revues seulement. Sous trente "
        "publications dans une strate, l'indicateur n'est pas calculé et n'entre dans aucun "
        "dénominateur. Le point neutre = 1 vaut la moyenne française, jamais la moyenne "
        "mondiale."
    ),
    "zoom_kpi_isite": (
        "Part des co-publications de la relation relevant du périmètre I-SITE sur {window}. Le "
        "périmètre est défini par la liste de DOI validée par l'établissement, jamais par un "
        "mot-clé ni par un rattachement automatique. Cette liste porte une date : les années les "
        "plus récentes sont sous-couvertes, et un recul apparent tient au retard de mise à jour, "
        "jamais à un recul réel."
    ),
    "zoom_kpi_momentum": (
        "Comparaison de la part annualisée du partenaire dans le corpus collaboratif de "
        "l'Université de Lorraine entre les deux fenêtres de {window}. Le rapport est recentré "
        "sur la dérive de l'ensemble du corpus, pour ne pas confondre la croissance du "
        "partenariat avec celle du corpus. Hors de la bande de stabilité, l'écart n'est affiché "
        "comme hausse ou retrait que s'il est significatif ; sinon la classe est « non "
        "significatif », qui est une classe et non une absence de donnée. Famille figée : elle "
        "n'est pas recalculée sous les filtres référentiel ou I-SITE."
    ),
    "zoom_kpi_phares": (
        "Co-publications de la relation situées dans le décile le plus cité de leur propre "
        "strate française, sur {window}. Strate : sous-champ × année de publication × type de "
        "document ; articles et revues seulement, et seuls les travaux dont l'indicateur est "
        "calculé entrent au numérateur comme au dénominateur. La flèche ouvre la liste vivante "
        "de ces publications ; au-delà de {max_ids} identifiants elle ouvre la liste des "
        "co-publications les plus citées, qui est un substitut d'accès et non la règle du décile."
    ),
}

# ---------------------------------------------------------------------------
# 3. Legendes de reserve : ce qu'une vue doit dire quand elle degrade
# ---------------------------------------------------------------------------
CAPTIONS: dict[str, str] = {
    "PHARES_PROXY": (
        "Au-delà de {max_ids} identifiants, le lien ouvre la liste des co-publications les plus "
        "citées de la relation, et non le décile lui-même : c'est un substitut d'accès, jamais "
        "la définition de l'indicateur."
    ),
    "DERIVED_PARTNER_VOLUME": (
        "Le volume propre du partenaire par nœud vient de son propre décompte sur ce nœud, "
        "diminué des co-publications ; il n'est pas projeté depuis le poids de ce nœud dans "
        "son portefeuille. Quand ce décompte manque, le côté partenaire reste vide plutôt que "
        "ramené à zéro."
    ),
    "FRONTIER_VINTAGES": (
        "Deux lectures de la frontière cohabitent, et ne se comparent pas : le score composite "
        "affiché ailleurs dans l'outil moyenne toutes les périodes de la référence, tandis que "
        "l'expansion et l'accélération lues ici portent sur la dernière période disponible, "
        "nommée avec le graphique."
    ),
    "SUBFIELD_NULL_SHARE": (
        "Le nombre annoncé compte les sous-champs AFFICHÉS pour lesquels la mesure du côté "
        "partenaire manque : ils gardent leur volume conjoint et leur côté lorrain, et leur "
        "côté partenaire reste vide. Les sous-champs situés au-delà de la coupe ne sont pas "
        "comptés là : la coupe est un choix d'affichage, pas une donnée manquante."
    ),
    "PLANE_UNSCORED": (
        "Les topics que le plan ne peut pas placer, faute de score disponible, ne sont pas "
        "dessinés ; leur nombre est indiqué avec le graphique, et ils ne pèsent dans aucun "
        "dénominateur."
    ),
    "THIN_PARTNER": (
        "La relation compte peu de nœuds au-dessus du plancher : la vue reste courte ou vide, "
        "ce qui est la lecture honnête d'un partenariat mince, pas une donnée manquante."
    ),
    "JOINT_UNDER_FLOOR": "non affiché sous cinq co-publications",
}

# ---------------------------------------------------------------------------
# 4. Libelles de controle et d'action
# ---------------------------------------------------------------------------
LABELS: dict[str, object] = {
    "PAGE_WORKBOOK": "Télécharger cette vue (xlsx)",
    "LEVEL_TOGGLE": ["Champs", "Top 30 sous-champs (volume conjoint)"],
    "BALANCE_MODES": {
        "volume": "Volume",
        "fwci": "FWCI médian (réf. France)",
        "phares": "Publications phares",
    },
    "PLANE_SELECT": {
        "volume": "Volume conjoint",
        "fwci": "FWCI médian (réf. France)",
        "frontiere": "Frontière (dernière période)",
        "phares": "Publications phares",
    },
    "PHARES": "publications phares (top 10 % France)",
    "JOINT_COL": "Co-pubs",
}

# ---------------------------------------------------------------------------
# 5. Libelles de survol -- source unique, egale a docs/tooltip_spec.yaml
#    HOVER_LABELS[cle][mode] = [libelle, ...] dans l'ordre du survol ; la
#    premiere chaine est vide (l'entite), comme les lignes `drapeau`.
#    GENERE A LA MAIN, VERIFIE PAR EGALITE : ne pas reordonner sans toucher
#    le yaml dans le meme commit.
# ---------------------------------------------------------------------------
HOVER_LABELS: dict[str, dict[str, list[str]]] = {
    'col_hub_companion': {
        'default': [
            '',
            'co-publications, tous types',
            "part du corpus collaboratif de l'UL",
            'part de la production propre du partenaire',
            'FWCI médian des co-publications (réf. France)',
            'publications phares',
            'dont périmètre I-SITE',
            'pays',
        ],
    },
    'col_reciprocity': {
        'p20': [
            '',
            "part du corpus collaboratif de l'UL",
            'part de la production propre du partenaire',
            '',
            'co-publications, tous types',
            'production propre du partenaire sur la fenêtre',
            "type d'établissement",
            'pays',
        ],
        'p10': [
            '',
            "part du corpus collaboratif de l'UL",
            'part de la production propre du partenaire',
            '',
            'co-publications, tous types',
            'production propre du partenaire sur la fenêtre',
            "type d'établissement",
            'pays',
        ],
    },
    'col_consortium_bars': {
        'default': [
            '',
            "co-publications avec l'UL, tous types",
            'part du périmètre I-SITE',
            'tendance entre les deux fenêtres',
        ],
    },
    'col_momentum_quadrant': {
        'log': [
            '',
            'part annualisée, première fenêtre',
            'part annualisée, seconde fenêtre',
            'tendance',
            'significativité',
            'co-publications, première puis seconde fenêtre',
            'co-publications, tous types',
        ],
        'lineaire': [
            '',
            'part annualisée, première fenêtre',
            'part annualisée, seconde fenêtre',
            'tendance',
            'significativité',
            'co-publications, première puis seconde fenêtre',
            'co-publications, tous types',
        ],
    },
    'zoom_yearly': {
        'default': [
            '',
            'co-publications, tous types',
            'dont périmètre I-SITE',
            "part du corpus collaboratif de l'UL cette année-là",
        ],
    },
    'zoom_share_spark': {
        'default': [
            '',
            "part du corpus collaboratif de l'UL",
            'co-publications, tous types',
        ],
    },
    'zoom_balance_bars': {
        'volume|champ': [
            '',
            'co-publications de la relation',
            'travaux propres de chaque côté, hors relation',
            '',
            'part de la relation',
            "part du portefeuille propre de l'UL",
            'poids du nœud dans le portefeuille propre du partenaire',
        ],
        'volume|sous_champ': [
            '',
            'co-publications de la relation',
            'travaux propres de chaque côté, hors relation',
            '',
            'part de la relation',
            "part du portefeuille propre de l'UL",
            'poids du nœud dans le portefeuille propre du partenaire',
        ],
        'fwci|champ': [
            '',
            'FWCI médian des co-publications (réf. France)',
            "FWCI médian du portefeuille propre de l'UL (réf. France)",
            'co-publications de la relation',
            'co-publications portant un indicateur calculé',
            '',
            '',
        ],
        'fwci|sous_champ': [
            '',
            'FWCI médian des co-publications (réf. France)',
            "FWCI médian du portefeuille propre de l'UL (réf. France)",
            'co-publications de la relation',
            'co-publications portant un indicateur calculé',
            '',
            '',
        ],
        'phares|champ': [
            '',
            'publications phares de la relation',
            "publications phares du portefeuille propre de l'UL",
            'co-publications de la relation',
            'part des co-publications de la relation classées phares',
            '',
            '',
        ],
        'phares|sous_champ': [
            '',
            'publications phares de la relation',
            "publications phares du portefeuille propre de l'UL",
            'co-publications de la relation',
            'part des co-publications de la relation classées phares',
            '',
            '',
        ],
    },
    'zoom_plane_impact': {
        'volume': [
            '',
            'mots-clés du topic',
            'co-publications de la relation, tous types',
            'FWCI médian des co-publications (réf. France)',
            'publications phares',
            '',
            'sous-champ',
        ],
        'fwci': [
            '',
            'mots-clés du topic',
            'co-publications de la relation, tous types',
            'FWCI médian des co-publications (réf. France)',
            'publications phares',
            '',
            'sous-champ',
        ],
        'frontiere': [
            '',
            'mots-clés du topic',
            'co-publications de la relation, tous types',
            'FWCI médian des co-publications (réf. France)',
            'publications phares',
            '',
            'sous-champ',
        ],
        'phares': [
            '',
            'mots-clés du topic',
            'co-publications de la relation, tous types',
            'FWCI médian des co-publications (réf. France)',
            'publications phares',
            '',
            'sous-champ',
        ],
    },
    'zoom_plane_frontier': {
        'volume': [
            '',
            'mots-clés du topic',
            'expansion depuis la période de référence',
            'accélération sur la dernière période',
            'co-publications de la relation, tous types',
            'score de frontière de la dernière période',
            '',
        ],
        'fwci': [
            '',
            'mots-clés du topic',
            'expansion depuis la période de référence',
            'accélération sur la dernière période',
            'co-publications de la relation, tous types',
            'score de frontière de la dernière période',
            '',
        ],
        'frontiere': [
            '',
            'mots-clés du topic',
            'expansion depuis la période de référence',
            'accélération sur la dernière période',
            'co-publications de la relation, tous types',
            'score de frontière de la dernière période',
            '',
        ],
        'phares': [
            '',
            'mots-clés du topic',
            'expansion depuis la période de référence',
            'accélération sur la dernière période',
            'co-publications de la relation, tous types',
            'score de frontière de la dernière période',
            '',
        ],
    },
    'zoom_field_companion': {
        'default': [
            '',
            'co-publications de la relation, tous types',
            'part de la relation',
            "part du portefeuille propre de l'UL",
            'poids du nœud dans le portefeuille propre du partenaire',
            "intensité de la relation dans ce champ, rapportée au portefeuille de l'UL",
            'tendance entre les deux fenêtres',
        ],
    },
    'zoom_subfield_companion': {
        'default': [
            '',
            'champ',
            'co-publications de la relation, tous types',
            'part de la relation',
            "part du portefeuille propre de l'UL",
            'poids du nœud dans le portefeuille propre du partenaire',
            'tendance entre les deux fenêtres',
        ],
    },
    'zoom_theme_zoom': {
        'default': [
            '',
            'co-publications de la relation dans ce champ, tous types',
            'dont périmètre I-SITE',
            'champ',
        ],
    },
    'zoom_reciprocity': {
        'champ': [
            '',
            'champ',
            "part du portefeuille propre de l'UL",
            'poids du nœud dans le portefeuille propre du partenaire',
            'co-publications de la relation, tous types',
            'part de la relation',
            'domaine',
        ],
        'sous_champ': [
            '',
            'champ',
            "part du portefeuille propre de l'UL",
            'poids du nœud dans le portefeuille propre du partenaire',
            'co-publications de la relation, tous types',
            'part de la relation',
            'domaine',
        ],
    },
    'zoom_portage': {
        'default': [
            '',
            'travaux de la relation attribués à cette structure',
            'part des travaux attribués de la relation',
            'travaux de la relation sans structure attribuée',
        ],
    },
    'ex_partner_reciprocity': {
        'education|fr_intl': [
            '',
            "co-publications avec l'UL sur ce nœud",
            "part du portefeuille de l'UL sur ce nœud",
            "part de la production propre du partenaire sur ce nœud qui implique l'UL",
            "part des co-publications internationales de l'UL sur ce nœud",
            'FWCI médian des co-publications (réf. France)',
            'pays',
            "type d'établissement",
        ],
        'education|fr': [
            '',
            "co-publications avec l'UL sur ce nœud",
            "part du portefeuille de l'UL sur ce nœud",
            "part de la production propre du partenaire sur ce nœud qui implique l'UL",
            "part des co-publications internationales de l'UL sur ce nœud",
            'FWCI médian des co-publications (réf. France)',
            'pays',
            "type d'établissement",
        ],
        'education|intl': [
            '',
            "co-publications avec l'UL sur ce nœud",
            "part du portefeuille de l'UL sur ce nœud",
            "part de la production propre du partenaire sur ce nœud qui implique l'UL",
            "part des co-publications internationales de l'UL sur ce nœud",
            'FWCI médian des co-publications (réf. France)',
            'pays',
            "type d'établissement",
        ],
        'tous|fr_intl': [
            '',
            "co-publications avec l'UL sur ce nœud",
            "part du portefeuille de l'UL sur ce nœud",
            "part de la production propre du partenaire sur ce nœud qui implique l'UL",
            "part des co-publications internationales de l'UL sur ce nœud",
            'FWCI médian des co-publications (réf. France)',
            'pays',
            "type d'établissement",
        ],
        'tous|fr': [
            '',
            "co-publications avec l'UL sur ce nœud",
            "part du portefeuille de l'UL sur ce nœud",
            "part de la production propre du partenaire sur ce nœud qui implique l'UL",
            "part des co-publications internationales de l'UL sur ce nœud",
            'FWCI médian des co-publications (réf. France)',
            'pays',
            "type d'établissement",
        ],
        'tous|intl': [
            '',
            "co-publications avec l'UL sur ce nœud",
            "part du portefeuille de l'UL sur ce nœud",
            "part de la production propre du partenaire sur ce nœud qui implique l'UL",
            "part des co-publications internationales de l'UL sur ce nœud",
            'FWCI médian des co-publications (réf. France)',
            'pays',
            "type d'établissement",
        ],
    },
    'ex_partner_tables': {
        'default': [
            '',
            "co-publications avec l'UL sur ce nœud",
            "part du portefeuille de l'UL sur ce nœud",
            "part de la production propre du partenaire sur ce nœud qui implique l'UL",
            'FWCI médian des co-publications (réf. France)',
        ],
    },
    'geo_country_companion': {
        'default': [
            '',
            'co-publications, tous types',
            "part du corpus collaboratif international de l'UL",
            'FWCI médian des co-publications (réf. France)',
            '',
        ],
    },
    'geo_map': {
        'default': [
            '',
            'co-publications, tous types',
            "part du corpus collaboratif international de l'UL",
            'FWCI médian des co-publications (réf. France)',
            '',
        ],
    },
    'geo_unigr_bars': {
        'default': [
            '',
            "co-publications avec l'UL, tous types",
            'tendance entre les deux fenêtres',
        ],
    },
    'lab_sdg_bars': {
        'default': [
            '',
            'part du corpus de la structure',
            'travaux de la structure tagués sur cet objectif',
            "méthode d'attribution",
        ],
    },
    'pf_sdg_bars': {
        'default': [
            '',
            'publications du corpus taguées sur cet objectif',
            'part du corpus',
            "méthode d'attribution",
        ],
    },
    'pf_sdg_peers_scatter': {
        'default': [
            '',
            'objectif',
            "part du corpus propre de l'établissement",
            'position dans le jeu de pairs',
        ],
    },
}
