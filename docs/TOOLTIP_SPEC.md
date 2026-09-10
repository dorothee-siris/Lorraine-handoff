# Contrat de survol — notes de lecture

`docs/tooltip_spec.yaml` est le contrat lisible par machine : pour chaque graphique, les
lignes ordonnées de sa chaîne de survol ; pour chaque tuile, les lignes derrière son « ? ».
Ce fichier dit *pourquoi* chaque graphique porte ce qu'il porte. En cas de désaccord entre
les deux, **le YAML gagne** : c'est lui que le test lit (`tests/test_hover_spec.py`).

Les textes eux-mêmes vivent dans `Streamlit/lib/copy_fr.py` (`READING`, `HOVER_LABELS`,
`KPI_HELP`, `CAPTIONS`, `LABELS`). Le lien entre les deux fichiers n'est pas une génération
de code mais **un test d'égalité** : les libellés du YAML et ceux de `HOVER_LABELS` doivent
être identiques, jeu de modes par jeu de modes. Les deux fichiers restent donc lisibles et
modifiables à la main, et une divergence est une erreur de test nommée, jamais un silence.

## Conventions communes

**Un survol n'est pas un vidage de données.** Chacun porte, dans cet ordre : l'entité, puis
les canaux que l'œil ne peut pas décoder seul (une valeur d'axe, une aire de bulle, une
teinte), puis le ou les deux chiffres qui peuvent changer la lecture, puis les faits de
périmètre qui empêchent de mal lire le chiffre. Ce qu'un lecteur obtient en regardant le
graphique n'y figure pas — c'est pourquoi le rang d'un partenaire n'apparaît jamais dans un
tableau déjà trié par volume.

**Huit lignes, dur.** Aucun survol ne dépasse huit lignes. Les dix mots-clés d'un topic en
consomment deux : un survol de topic n'a donc que six lignes pour tout le reste. Une ligne
conditionnelle occupe sa place dans le budget même quand elle ne se dessine pas.

**La première ligne est l'entité.** Le champ, le sous-champ, le topic, l'année, le pays, la
structure ou l'objectif que la marque représente — jamais l'établissement d'abord : sur une
barre appariée, le lecteur sait déjà de quel côté il se trouve et cherche quelle *ligne* il
a atteinte.

**Les mots-clés partout où un topic apparaît.** Le libellé OpenAlex d'un topic n'est pas
toujours fidèle à son contenu ; les deux plans de la page Zoom portent donc les dix
mots-clés du topic, en deux lignes de cinq. C'est la raison du budget à six lignes utiles.

**Les périmètres sont nommés dès qu'ils diffèrent.** L'outil mélange des périmètres à
dessein : les volumes courent sur tous les types de documents, les indicateurs de citation
sur les seuls articles et revues, et les parts propres du partenaire sur son corpus entier,
tous co-auteurs confondus. Un survol qui met deux de ces périmètres sur des lignes voisines
les nomme tous les deux dans ses libellés. Un rapport dont le numérateur et le dénominateur
viennent de deux périmètres différents est un défaut, pas une réserve à écrire en note.

**Planchers et drapeaux.**

| Situation | Ce que fait le survol |
|---|---|
| FWCI sur moins de trois travaux couverts | la ligne FWCI n'est pas dessinée du tout |
| Ratio reposant sur moins de dix travaux | le chiffre garde une dague, et le compte est montré à côté |
| Paire sous le plancher de la relation | le compte conjoint lit « non affiché sous cinq co-publications », jamais zéro |
| Volume propre du partenaire dérivé | une ligne drapeau le dit, et le côté droit porte la mention *(dérivé)* |
| FWCI ou publications phares du partenaire indisponibles | une ligne drapeau annonce la lecture à un seul côté |
| Topic hors référentiel | une ligne drapeau, en écho à la teinte plus claire de la marque (P11) |
| Topic que le plan ne peut pas placer | il n'est pas dessiné ; la légende en donne le nombre |
| Pays du seau « non renseigné » | une ligne drapeau, pour qu'il ne se lise pas comme un pays |

**Aucun chiffre dans un libellé.** La fenêtre, les périodes de la référence de frontière et
les planchers viennent de la donnée ou des constantes de méthode (P6-R2) : un libellé qui les
écrirait à la main deviendrait faux à la première mise à jour. Là où un plancher doit être
dit dans une phrase de réserve, il s'écrit **en mots** (« sous cinq co-publications ») : c'est
une constante de méthode, pas une valeur lue, et la règle du chiffre littéral reste tenue.

**Trois formats font le travail difficile.** `fwci_paire_2d` imprime médiane, moyenne et le
nombre de travaux derrière elles sur une seule ligne, dague comprise — une ligne qui porte à
la fois un chiffre et son propre plancher. `paire_volumes` met les deux volumes propres, de
part et d'autre de la relation, sur une seule ligne, avec la mention *(dérivé)* du côté qui
l'est : c'est ce qui permet aux barres miroir de tenir en sept lignes. `conjoint_ou_seuil`
imprime le compte conjoint **ou** la phrase de plancher, jamais un zéro trompeur. Deux formats
du registre — `dec_1` et `rang_partenaire` — sont définis mais pas encore consommés : ils
appartiennent au vocabulaire de l'application, que la passe 7b étendra aux pages restantes.

## Famille par famille

**Barres à colonne de valeurs (compagnons de tableau, portage, pays, membres, ODD).** La
barre est un volume et la colonne de droite le répète en chiffres : le survol ne sert donc
pas à relire le volume mais à donner les parts qui le mettent en perspective — part de la
relation, part du portefeuille propre de chaque côté, intensité relative — et la tendance
entre les deux fenêtres quand elle est calculée. Sur le portage interne, la ligne qui compte
est celle des travaux **sans** structure attribuée : elle dit que le rapport affiché a un
dénominateur plus petit que la relation.

**Nuages de réciprocité (page 8, page 9, page 6).** Les deux axes sont deux parts à
dénominateurs différents ; c'est tout l'objet du graphique, et le survol nomme les deux
dénominateurs plutôt que de les laisser deviner. Il ajoute ce que la géométrie cache : le
volume derrière l'aire, la production propre du partenaire derrière la part verticale, et le
drapeau de part plafonnée qui explique un carré à la place d'un disque. Sur la page 8, le
plancher est un mode : la ligne de lecture du plancher bas prévient que les deux parts y sont
plus instables, parce que c'est la seule chose qui change entre les deux vues.

**Quadrant de momentum (page 8).** L'échelle est un mode, la classe n'en dépend pas : le
survol porte les deux parts annualisées, la classe, la significativité et les deux comptes
bruts, parce qu'une classe sans sa base ne peut pas être vérifiée. « Non significatif » est
une classe, jamais une absence de donnée, et les aides le disent dans ces mots-là.

**Barres miroir (page 9).** Trois modes, trois quantités différentes sur la même géométrie :
le survol est donc écrit **par mode**. En volume, il porte les trois volumes et les parts des
deux portefeuilles, et il déclare le côté partenaire comme dérivé. En FWCI, il porte le FWCI
conjoint (avec sa base) face au FWCI propre de l'UL, et déclare que le côté partenaire n'est
pas disponible — la lecture est à un seul côté, et c'est dit dans le survol comme dans la
ligne de lecture. En publications phares, même structure, même aveu du côté manquant, plus la
part des co-publications classées phares, daguée quand la base est mince.

**Plans de topics (page 9).** Le plan d'impact met le volume en horizontale (échelle
logarithmique) et le FWCI médian en verticale ; le plan de frontière met l'**expansion** —
la position de longue durée du topic par rapport à la science mondiale, sa croissance depuis
la période de référence — en horizontale, et l'**accélération** — l'élan récent, dernière
période contre la précédente — en verticale. Les deux composantes sont lues sur la dernière
période disponible, dont les libellés viennent de la donnée (`{bin_prev}`, `{bin_last}`), et
le score composite affiché ailleurs dans l'outil moyenne **toutes** les périodes : les deux ne
se comparent pas, et `CAPTIONS["FRONTIER_VINTAGES"]` le dit sur chaque surface de frontière.
Le sélecteur de topics est un mode, et sa seule conséquence est le biais de sélection : la
ligne de lecture de chaque mode le nomme (un tri par FWCI fait monter des topics minces, un
tri par publications phares favorise les topics volumineux).

**Séries annuelles et sparkline (page 9).** Une année est une entité pauvre : le survol tient
en trois ou quatre lignes, et sa seule vraie information est la part I-SITE, qui isole une
contribution sans retirer de travail du total. La sparkline de part porte le volume en plus de
la part, parce qu'une part qui monte sur un volume qui baisse est la lecture la plus
fréquemment inversée.

**Graphiques ODD (pages 2 et 4).** L'entité est l'objectif, dans sa couleur officielle et avec
son numéro dans le libellé (identité, pas palette validée : c'est pourquoi le libellé accompagne
toujours la couleur). Le survol nomme la méthode d'attribution en vigueur et le dénominateur de
la part — corpus entier de la structure côté page 2, corpus propre de l'établissement côté jeu
de pairs — et rappelle qu'un même travail peut relever de plusieurs objectifs, donc que les
barres ne s'additionnent pas.

## Ce qui est délibérément laissé dehors

L'identifiant OpenAlex de l'entité (le lien le porte), le domaine quand une légende de couleur
le donne déjà, le rang dans un tableau déjà trié, la valeur de l'axe sur un graphique dont
l'axe est gradué et lisible, le nombre de co-auteurs, et toute mention de fichier, de colonne
ou de décision interne — celles-ci vivent dans les `note:` du YAML, qui ne sont jamais rendues
à l'écran. Le survol ne conclut jamais : il dit comment lire, la conclusion reste au lecteur.
