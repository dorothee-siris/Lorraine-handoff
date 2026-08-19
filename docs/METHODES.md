# Note de méthode

Instantané de référence : **2026-08-11**. Fenêtre de publication : **2019-2023**. Source unique de
collecte : **OpenAlex**, complétée par HAL et OpenAIRE pour les seuls résumés manquants. Deux
entrées maintenues à la main, la liste des structures et la liste des DOI I-SITE.

Chaque paramètre cité ici vit dans `config.yaml` ; aucun n'est écrit en dur dans un script. Les
références `D<numéro>` renvoient aux décisions consignées dans le plan d'exécution du projet.

---

## 1. Périmètre

Le périmètre est défini par une seule requête OpenAlex : `authorships.institutions.lineage:I90183372`,
c'est-à-dire l'ensemble des publications qu'OpenAlex rattache à l'Université de Lorraine ou à l'une
de ses structures descendantes, sur la fenêtre 2019-2023. La collecte rend **46 404** publications
avant application des règles de corpus.

Ce choix a été mesuré avant d'être retenu (D33). Deux définitions étaient candidates : la requête
par filiation ci-dessus, et l'union des identifiants de la liste client. Le comptage donne
|A| = 46 404 pour la filiation, |B| = 45 836 pour la liste, et surtout |B \ A| = 0 : la liste
client est un sous-ensemble strict de la filiation, donc l'union des deux **est** la requête par
filiation. Une seule collecte suffit, et les drapeaux de provenance (`via_lineage`, `via_lab_ror`,
`via_ul_direct`) sont dérivés localement des affiliations déjà présentes dans la charge utile.

**La propriété est revérifiée à chaque lancement**, par un appel unique qui recompte la requête B et
la compare aux publications collectées portant un identifiant de cette liste. Elle ne peut se rompre
que d'une façon : si une édition du fichier client ajoute une structure qu'OpenAlex ne place pas sous
la filiation de l'Université. Dans ce cas, le contrôle échoue bruyamment et la collecte bascule sur
la requête B complète.

Un point mérite d'être dit, parce qu'il ne va pas de soi pour un établissement français : **la
filiation n'est pas polluée ici**. Sur les 568 publications que seule la filiation ramène, la
majorité relève de sous-structures de l'Université absentes de la liste client (LLSS 400,
Diplomatique 76, Écologie & Écophysiologie Forestières 39, ENIM 36) ; les plus gros contributeurs
non lorrains sont Patna University (30) et Luxembourg (21), c'est-à-dire des co-auteurs ordinaires.
Le greffage de portefeuilles partenaires entiers qu'on observe sur d'autres établissements français
en co-tutelle ne se produit pas dans ce cas.

OpenAlex rattache par ailleurs **90 structures** à l'Université, dont **22 ne figurent pas** dans la
liste client, et **21** d'entre elles portent des publications sur la fenêtre. La version 2
n'invente aucune ligne : elle les signale, les rend sélectionnables dans l'application avec une
mention « hors liste », et les exclut par défaut des classements. L'arbitrage appartient au client.

## 2. Règles de corpus

Des 46 404 publications collectées, **36 819** entrent dans le corpus. L'entonnoir est court et
chaque marche est comptée.

| Règle | Avant | Après | Écartées |
|---|---|---|---|
| type retenu (`article`, `book-chapter`, `review`, `book`, `conference-paper`) | 46 404 | 36 828 | 9 576 |
| non rétractée | 36 828 | 36 822 | 6 |
| non paratexte | 36 822 | 36 822 | 0 |
| titre présent | 36 822 | 36 819 | 3 |

**Les actes de conférence sont dans le corpus** (D36), porteurs d'un drapeau `is_conference` que chaque vue et
chaque indicateur peuvent activer pour les inclure ou les exclure. La raison est factuelle : OpenAlex a reclassé en `conference-paper` **3 737 publications** que la version 1
portait sous un autre type. Les exclure aurait fait disparaître des publications que le client voit
dans l'outil actuel et aurait sous-représenté le LORIA et les équipes INRIA. La conséquence est à
lire en regard des indicateurs de citation : les actes lorrains ont une médiane de **0 citation** et
**78,0%** d'entre eux ne sont jamais cités, ce que la stratification par type traite par
construction (section 4).

**Les préprints sont exclus intégralement** (D10), 2 075 publications, pour un motif de
dédoublonnage : un préprint et sa version publiée sont deux enregistrements distincts dans OpenAlex.
Sont également écartés les mémoires et thèses, les résumés de conférence, les rapports, les jeux de
données, les éditoriaux, les errata et les évaluations par les pairs, par le seul jeu de la liste
de types retenus.

**Le DOI n'est pas exigé** (D37). Le corpus conserve ses **11 342 publications sans DOI**, soit
30,8%, et porte un drapeau `has_doi`. Exiger un DOI aurait supprimé, en bloc, la production SHS
francophone et les actes du LORIA et d'INRIA : 90,6% de ces publications sont rattachables à une
structure de la liste client, 69,5% sont en français, 89,9% portent déjà un résumé, et 10 372 ont
HAL pour source principale. Le corpus serait devenu plus petit que celui de la version 1 alors même
que le périmètre s'élargissait. Un DOI n'est requis que là où l'opération est indexée par DOI (le
drapeau I-SITE, le complément de résumés, les tables de recouvrement inter-sources), et chacune de
ces opérations déclare explicitement son reste sans DOI.

## 3. Résumés

Le résumé est reconstruit depuis l'index inversé d'OpenAlex, puis complété là où il manque, d'abord
par HAL, ensuite par OpenAIRE, en conservant toujours le texte le plus long et en enregistrant sa
source et sa langue sur chaque ligne.

La couverture passe de **74,0%** après la seule reconstruction OpenAlex à **92,3%** après complément,
contre 57,7% de texte réellement présent dans la version 1. Les 4 336 résumés récupérés via HAL et
les 2 212 via OpenAIRE sont tous traçables à leur source, ce qui n'était pas le cas du complément de
la version 1 (section 3 de [`SHIFT_v1_v2.md`](SHIFT_v1_v2.md)).

Deux points de méthode. HAL est interrogé en **moisson de structure** avec curseur, pas en requêtes
par DOI : puisque 10 372 des publications sans DOI sont des dépôts HAL, seule une moisson par
identifiant de structure les atteint. Et le texte standard des dépôts HAL, cette mention légale qui
accompagne certains enregistrements, est détecté et rejeté : il avait contaminé 54 publications de
la version 1, il en contamine **0** ici.

La couverture des résumés est le vrai verrou de faisabilité pour toute classification en aval. Elle
varie sensiblement selon le type : 93,5% sur les articles et 94,1% sur les revues de littérature,
contre 79,9% sur les chapitres d'ouvrage.

## 4. Indicateurs de citation

### La référence

Les indicateurs sont normalisés contre une **base de référence française de 1 100 570 publications**,
collectée par l'API sur la même fenêtre et les mêmes types de documents que le corpus lorrain. Cette
symétrie est une condition de validité : une référence dont le périmètre diffère du numérateur
qu'elle normalise ne mesure rien.

La strate de normalisation est unique pour tous les indicateurs : **sous-domaine × année de
publication × type de document**. La base compte 5 271 strates, dont 2 669 sont trop minces (moins
de 30 publications) et couvrent 2,02% des publications françaises.

**En dessous du seuil, l'indicateur est nul, jamais calculé.** Un centile calculé sur une poignée de
publications est du bruit, pas une mesure. Sur le corpus, 35 876 publications reçoivent des
indicateurs ; 892 sont en strate mince et 51 sans strate. L'application les affiche « n/a », en
grisé, avec le décompte des exclusions, et ne les compte dans aucun dénominateur. Elles ne sont
jamais affichées comme un zéro : un indicateur absent et un indicateur nul ne disent pas la même
chose.

### FWCI_FR

Le `FWCI_FR` est le rapport entre le nombre de citations d'une publication et la moyenne des
citations de sa strate. Une valeur de 1 signifie « cité comme la moyenne française des publications
du même sous-domaine, de la même année et du même type ». Le corpus lorrain se situe à **0,938** en
moyenne, soit très légèrement en deçà de cette moyenne nationale.

Cet indicateur n'est pas le `fwci` natif d'OpenAlex et ne doit pas lui être comparé naïvement : le
`FWCI_FR` se normalise contre la production française et compte les citations cumulées à la date de
l'instantané, là où OpenAlex se normalise contre la production mondiale sur une fenêtre fixe de
trois ans après publication. La corrélation de rang entre les deux est néanmoins de **0,93 à 0,98**
selon l'année, ce qui valide la construction de la base sans en faire la même statistique.

### PPtop10_FR et PPtop1_FR

`PPtop10_FR` indique qu'une publication figure parmi les 10% les plus citées de sa strate française,
`PPtop1_FR` parmi le 1% le plus cité.

Le seuil est défini par **rang centile**, non par une comparaison à un p90 interpolé (D40). La
distinction est technique et ses effets sont massifs. Les comptages de citations s'agglutinent aux
valeurs basses : la médiane française est de 1 citation et 43,2% des publications ne sont jamais
citées. Un test de la forme `citations >= p90` sur une distribution ainsi nouée fait entrer *tout*
le groupe assis exactement sur la coupure. Le seuil retenu est donc le plus petit nombre de
citations dont la part de publications françaises strictement inférieures atteint 0,90, testé en
`>=`, ce qui exclut plutôt qu'il n'admet un groupe à cheval sur la coupure. Le biais est ainsi
orienté vers la sous-attribution, pas vers la sur-attribution.

Deux preuves indépendantes que la définition est la bonne. À l'intérieur de la France, où la
propriété doit tenir par construction, le seuil sélectionne **8,42% à 9,27%** des publications selon
l'année pour le top 10%, et 0,82% à 0,86% pour le top 1%. Et l'accord avec le propre
`is_in_top_10_percent` d'OpenAlex passe de 79-86% sous l'ancienne définition à **92-93%** sous
celle-ci.

**Ce que la part lorraine est, et ce qu'elle n'est pas.** La part de l'Université de Lorraine dans
le top 10% français est un **résultat**, pas une propriété à vérifier. Rien n'oblige un
établissement à se situer exactement à 10% : c'est précisément l'écart à cette valeur que
l'indicateur mesure. La cible de 10% est une propriété de la *population de référence* et elle est
testée sur elle, en France, année par année. Ce que l'on vérifie côté Lorraine est l'absence de
gradient temporel, parce que c'est là que se situait le défaut de la version 1 (section 1 de
[`SHIFT_v1_v2.md`](SHIFT_v1_v2.md)).

Pour l'ordre de grandeur : le corpus lorrain se situe à **8,1%** contre la référence française et à
13,5% contre la référence mondiale d'OpenAlex. La barre française est donc la plus exigeante des
deux, ce qui est la raison pour laquelle elle a été retenue comme référence principale plutôt que la
seconde, plus flatteuse.

## 5. Objectifs de développement durable

Trois routes ont été calculées, et **les trois sont livrées**. Le choix entre elles est un arbitrage
d'atelier, pas une décision technique déjà prise.

| Route | Méthode | Publications taguées | Part du corpus | ODD par publication |
|---|---|---|---|---|
| A | version 1 livrée, méthode non reconstituable | 3 909 | 10,6% | 1,495 |
| B | SIRIS v2, vocabulaire contrôlé JRC, 16 passes | **5 447** | **14,8%** | 1,445 |
| C | OpenAlex Aurora, score ≥ 0,40 | 19 946 | 54,2% | 1,010 |

**Route B**, active par défaut, applique le vocabulaire contrôlé JRC en 16 passes indépendantes, une
par ODD, sur le titre et le résumé, avec traduction automatique FR→EN préalable des textes français.
La traduction n'est pas un raffinement : elle porte la couverture des publications françaises de 9%
à 48%. Elle concerne 11 627 publications, soit 31,6% du corpus, dont la langue française est
identifiée avec une probabilité d'au moins 0,90.

**Route C** est un classificateur différent, pas un classificateur plus permissif. Il est
strictement mono-étiquette, exactement 1,010 ODD par publication taguée, et son score est plancherisé
à 0,40, valeur en dessous de laquelle OpenAlex ne publie rien. Il ne sait pas exprimer une
publication relevant de plusieurs ODD, là où les routes A et B en attribuent en moyenne 1,45 à 1,50.
Sa couverture trois fois supérieure est une conséquence de cette différence de nature, pas une
mesure de sa qualité.

**Le choix se fait par une ligne de configuration**, `config.yaml: app.sdg_variant`, qui accepte
`b_siris`, `c_openalex` ou `"off"`. Changer de route est un changement de configuration suivi d'un
`60_deploy` : jamais une reconstruction. Le panneau ODD de l'application affiche le nom de la route
active et sa couverture.

**Ce que les chiffres de comparaison disent, et ne disent pas.** B et A produisent des ensembles
d'ODD identiques sur **96,5%** des publications que les deux taguent, avec un indice de Jaccard
moyen de 0,983 : la route SIRIS v2 reproduit très étroitement ce que le client voit aujourd'hui.
Mais ce sont des mesures d'**accord**, pas d'exactitude. Aucune vérité terrain n'existe : la version
1 n'a ni constructeur archivé, ni paramètres consignés, et l'échantillon de référence
`tests/golden/sdg_golden_sample.csv` est délibérément livré sans étiquettes. Un échantillon de
**60 publications**, stratifié sur les désaccords entre les trois routes, avec le texte et les trois
verdicts, attend un arbitrage humain dans
`reports/sdg_three_way_review_sample.xlsx`. C'est le matériau de travail de l'atelier.

## 6. Axes thématiques

Le modèle de topics de la version 1 est retiré (D9). Les vues thématiques sont reconstruites sur la
**taxonomie native d'OpenAlex**, à quatre niveaux : 5 domaines, 27 champs, 239 sous-domaines,
3 275 topics.

Le motif est une question de couverture. Le modèle de topics de la version 1 couvrait **79,0%** du
corpus par construction ; les 21% restants étaient simplement absents des vues thématiques, sans que
rien ne le signale. La taxonomie OpenAlex laisse **51 publications sans thématique, soit 0,1%**, et
ces 51 publications sont visibles dans l'application sous une entité « sans thématique » plutôt que
d'être escamotées.

Le topic principal est une valeur unique, donc chaque niveau de la hiérarchie somme exactement au
corpus, sans double compte. Second avantage, non négligeable pour un outil destiné à durer : la
taxonomie se rafraîchit avec les données à chaque collecte, là où un modèle de topics est figé au
jour de son entraînement et exige un réentraînement pour intégrer une année de plus.

## 7. Auteurs

> **Supersédé en partie (RA-C04) :** la dimension auteurs a depuis reçu ses vues applicatives
> (Authors Directory, Author Profile, Identifiers & couverture — chaîne pass 3/4, voir §9.3) ;
> le paragraphe ci-dessous reste la méthode de résolution d'identité, pas l'état de couverture
> applicative actuel.

La table `ul_authors` est livrée comme **jeu de données, sans vue dans l'application** (D15/D54).
Les fichiers sont déployés et les fonctions de chargement existent ; la construction d'une vue
auteurs relève du co-design, pas de cette phase.

La méthode, pour mémoire. Les 14 237 profils d'auteurs OpenAlex du corpus sont réduits à
**12 680 personnes** par résolution d'entités, 1 557 profils étant absorbés dans un autre. Les règles
de fusion sont explicites et comptées : identité d'idHAL (393), nom identique et trois co-auteurs
partagés (364), nom, laboratoire et un co-auteur (437), nom et laboratoire identiques (1 142). Un
conflit d'ORCID bloque la fusion dans 5 393 cas, y compris lorsque les autres signaux concordent :
mieux vaut deux profils distincts qu'une personne fusionnée à tort. Vingt paires restent en file
d'attente d'arbitrage humain, et quatre grappes portent plus d'un idHAL, ce qu'une personne ne
devrait pas faire : elles sont listées à part pour vérification.

Une colonne mérite d'être signalée, `ul_credited_works`, qui compte les publications où la personne
est créditée d'une structure lorraine, distinctement du nombre de publications du corpus qu'elle
signe. L'écart sépare les chercheurs lorrains des collaborateurs extérieurs : un clinicien milanais
présent sur 281 publications du corpus n'est crédité d'une structure lorraine que sur une seule. La
version 1 n'avait pas cette colonne, d'où sa lecture erronée de « 3 166 auteurs mal crédités ».

## 8. Ce que cette méthode ne fait pas

> **Supersédé en partie (RA-C04) :** la limite « ne compare pas l'Université à des pairs »
> ci-dessous est levée par le Benchmark (T4b, §9.8) ; la réciprocité partenaires (42b, §9.7)
> lève, ailleurs dans l'outil, la présentation « pull partenaire non engagé » qui aurait pu
> laisser croire à une limite équivalente sur les vues partenaires. Les deux autres limites
> nommées ci-dessous (rattachement institutionnel, absence de vérité terrain ODD) restent
> d'actualité.

Elle ne mesure pas la production « réelle » de l'Université de Lorraine, mais ce qu'OpenAlex lui
rattache à une date donnée : le rattachement institutionnel est un choix, et OpenAlex continue de
retraiter l'historique des affiliations des années après une collecte (section 6 de
[`SHIFT_v1_v2.md`](SHIFT_v1_v2.md)). Elle ne fournit aucune vérité terrain sur les ODD, seulement
des mesures d'accord entre trois routes. Elle ne compare pas l'Université à des pairs : la référence
est nationale et agrégée, jamais un panel d'établissements. Ces trois limites sont des choix de
cadrage, et chacun d'eux se rediscute à l'atelier avec les éléments chiffrés réunis ici.

## 9. Compléments de méthode — chaîne pass 3 (2026-08-15)

Cette section documente les compléments introduits par la deuxième passe de la Foundry et la
première passe de l'Assembly Line (partenaires, extensions thématiques, dimension auteurs). Le
détail technique vit dans `docs/foundry/DATA_FOUNDATION.md` (rev 3.1) et son pendant machine
`docs/foundry/data_foundation.yaml` ; ce qui suit en est la traduction pour un lecteur client.

### 9.1 Filtre « hors référentiel mondial »

Un classificateur entraîné sur un corpus majoritairement anglophone sous-résout **811 topics**
OpenAlex, identifiés dans `OA_bad_topics.xlsx` (colonne « Should we keep this OA topic? » =
« Filter out »). Ces topics ne sont **jamais retirés en silence** : chaque publication dont le
topic principal figure sur la liste porte un marqueur, visible sur chaque ligne, chaque cellule et
chaque point concerné, dans chaque vue. Un bouton unique, **désactivé par défaut**, permet de les
exclure ; l'affichage complet (avec marqueur) reste le comportement par défaut, sans exception de
démonstration.

La sémantique du bouton diffère selon le grain de la table, et c'est voulu. Au grain publication,
l'activer retire les travaux dont le topic **principal** est marqué, soit **11,15 %** du corpus
(4 106 travaux). Au grain topic (`ptn_topics`), l'activer retire en plus les lignes de topic
elles-mêmes marquées — une population plus large, qui compte aussi les topics secondaires d'une
publication : l'empreinte « au moins un topic marqué » est de **20,68 %**. Les deux écarts sont
légitimement différents (des travaux d'un côté, des topics portés par ces mêmes travaux de
l'autre) et aucun écran ne doit montrer les deux chiffres sans cette phrase.

Chaque page porte, quand le filtre est activé, une bannière pleine largeur, non réductible :
*« Filtré : 811 topics exclus (limite du classifieur, jamais un jugement sur la recherche) —
11,15 % des travaux, concentrés en SHS francophone. »* Le même texte figure dans l'en-tête de
chaque export, avec un champ dédié `artifact_applied: yes|no`.

Une famille échappe à cette bascule par construction : le **momentum** (classes de tendance,
p-valeur, parts de fenêtre) n'est **jamais recalculé** sous le filtre — il reste affiché grisé, avec
la légende « momentum calculé sur le corpus entier ». Le recalculer produirait quatre variantes de
la même mesure sans référence stabilisée pour aucune d'elles ; un chiffre visiblement inerte est
honnête, un chiffre silencieusement obsolète ne l'est pas.

Les pages déjà livrées en version 1 (« ships-v2 ») ne filtrent rien : le filtre ne porte que sur les
nouvelles vues. Elles portent donc une bannière distincte : *« Le filtre « hors référentiel »
s'applique aux nouvelles vues ; cette page v2 affiche le corpus entier — lignes concernées marquées
†. »*

Deux asymétries sont assumées et disclosed plutôt que masquées. D'abord, **la référence France n'a
pas de grain topique** : elle ne peut donc pas être filtrée, et toute part relative calculée sous le
filtre (spécialisation, LQ) ne recalcule que le côté lorrain. Ensuite, le filtre déplace la part
internationale du corpus de **42,7 % à 46,7 %** : les topics marqués sont, en moyenne, moins
internationaux que le reste du corpus — un fait qui va dans le sens du diagnostic (sous-résolution
plus marquée en SHS francophone) sans le démontrer isolément.

### 9.2 Contrat d'export

Chaque export porte un nom qui encode sa provenance, dans l'ordre : vue, indicateur, instantané,
état de conférence, état du filtre, puis, quand ils s'appliquent, sous-ensemble de périmètre,
entité et nœud thématique — `lorraine-explorer_<vue>_<indicateur>_<instantané>_<conf>_
<artifact>[_<sous-ensemble>][_<entité>][_<nœud>].xlsx`. L'entité est préfixée par nature (`p-`
partenaire, `a-` auteur·e, `c-` pays, `l-` structure) et le nœud par niveau (`d-` domaine, `f-`
champ, `sf-` sous-domaine, `t-` topic), pour que les segments optionnels restent non ambigus à
relire.

Chaque fichier s'ouvre sur une feuille « À lire — méthode » qui reprend l'état complet de la vue au
moment de l'export : méthode en une ligne, date d'instantané, filtres actifs, état du bouton
conférence, état du filtre hors-référentiel et son texte de bannière quand il est actif, liste des
colonnes différées, sous-ensemble de périmètre, entité, nœud de tirage, date de génération. Aucun
extrait ne circule donc hors contexte.

Deux exceptions sont nommées, pas contournées. Le tiroir d'impact par auteur·e (`aut_impact_drill`)
n'a **aucun chemin d'export dans le code** — il n'est consultable qu'à l'écran. Et l'export des
publications d'un·e auteur·e s'appuie sur `aut_works`, une table qui **ne porte physiquement aucune
colonne d'impact** (FWCI, PPtop) : la protection n'est donc pas un filtre applicatif contournable,
mais une propriété du schéma.

### 9.3 Dimension auteur·es — garde-fous structurels

La dimension auteurs sépare l'identité et le contenu en deux tables. `aut_public` porte **une ligne
par personne** (12 680), sans aucune colonne d'impact — un contrôle structurel interdit toute
colonne dont le nom contient `fwci`, `pptop`, `impact` ou `citation`. Les publications se lisent
dans `aut_works`, une table séparée, elle-même dépourvue de ces colonnes. Aucune des deux ne
propose de tri par défaut sur une quantité (nombre de travaux, citations) : le tri est un choix de
l'utilisateur, jamais un classement pré-orienté.

Le contexte d'impact n'existe que dans `aut_impact_drill`, réservé aux personnes créditées d'au
moins **30 travaux avec indicateur** par état de conférence — **480 personnes** par état — et
présenté comme un tiroir de consultation, sans export et sans tri. Descendre sous ce plancher
rendrait une moyenne individuelle non significative.

Un contrôle humain reste ouvert avant mise en ligne : la relecture à voix haute des fiches
individuelles, pour vérifier qu'aucune formulation ne se lit comme un jugement sur une personne. La
vue de couverture des identifiants (A-V3) ne descend jamais à l'individu : ses grains sont le
laboratoire, le champ, l'année ou la population entière, jamais une personne nommée.

### 9.4 Momentum — précisions pass 3

Le socle de la méthode figée ne change pas, mais son périmètre de partenaires si. La famille figée
compte historiquement **682 partenaires éligibles**, calculée avant que le blocage propre à
l'Université de Lorraine ne couvre son propre Centre Inria. La version livrée corrige ce blocage :
**681 partenaires éligibles**, avec un écart entièrement nommé — le Centre Inria disparaît (il
n'était jamais un partenaire), et **un seul** partenaire bascule de classe au seuil de
significativité : le CHU de Reims, de « en hausse » à « non significatif ».

Un second correctif, plus fin, affecte l'affichage. Les 681 (ou 682) partenaires de la méthode
figée incluent un pseudo-partenaire technique — le regroupement de toutes les affiliations sans
identifiant institutionnel résolu, jamais un établissement réel. Le contrôle interne qui l'a détecté
formule ainsi la mise en garde :

> *« Les effectifs bruts de la méthode figée (682 partenaires en mode historique, 681 en mode
> livré) incluent un pseudo-partenaire technique — le regroupement de toutes les affiliations sans
> identifiant institutionnel résolu, jamais un établissement réel — exclu de l'affichage : la table
> livrée compte 680 lignes réellement classées (105 en hausse, 51 en retrait, 276 stables, 248 non
> significatives). La recomputation sans ce pseudo-partenaire (681 → 680 par construction, sur
> l'ensemble des fenêtres) est proposée comme option chiffrée à la ratification des fenêtres de
> momentum (8.B3), non construite à ce jour. »*

L'application affiche donc **680 lignes réellement classées**, pas 681. La médiane de recentrage
diffère elle aussi selon l'état de conférence — **1,0604** tous types confondus, **1,0460** hors
actes de conférence — deux valeurs distinctes de la référence de divulgation figée, **1,061**, qui
reste la valeur publiée sur la seule ligne « tous types » de `dim_corpus_facts`.

### 9.5 Frontierness

Le score de frontierness est lu depuis un instantané unique, désigné par son empreinte (« sha ») et
vérifiée à chaque construction : toute dérive du fichier source interrompt la construction plutôt
que de la laisser dériver en silence. La version standardisée par champ accompagne **toujours** la
version brute, jamais l'inverse : le brut situe l'Université de Lorraine à **×1,37** la référence,
un effet de composition disciplinaire, contre **×1,03** une fois standardisé — l'écart entre les
deux est la mesure, pas un bruit à arbitrer. Les z-scores ne sont **jamais recalculés sur un
sous-ensemble** : propriété du topic dans sa population de référence mondiale, pas du sous-corpus
qui l'observe. Et un score bas ne se lit jamais comme une absence de frontière : il peut désigner
une recherche fondationnelle, établie plutôt qu'émergente.

**Profondeur complète (passe 5, ruling R11, 2026-08-18).** La table `thm_frontier_topics` étend
cette même construction, sans aucune réimplémentation, à la totalité des **3 274** topics que le
corpus lorrain porte comme topic principal (contre les 20 sujets émergents mondiaux déjà
matérialisés par `thm_frontier`) : chercher un mot-clé (par exemple « quantum ») fait ainsi
apparaître la position de **tous** les topics correspondants, y compris ceux hors du référentiel
de score (811 topics exclus, ou — cas gardé, mesuré nul à ce jour — absents du fichier de base ou
au score non défini), qui conservent leurs travaux lorrains et un code de raison explicite plutôt
qu'un score ou une position fabriqués.

### 9.6 Constructions T7 (financements)

Le décompte « leviers de financement » distingue deux constructions qui ne comptent pas la même
chose. Le regroupement « EC » compte **16 financeurs nommés** sur **2 182 lignes** de mention ;
l'ERDF compte **429 lignes** de mention pour **203 travaux distincts** — l'écart entre lignes et
travaux est la règle, pas une erreur : un même travail peut remercier plusieurs financeurs. Des
chiffres antérieurs (EC 2 214 lignes / ERDF 279 travaux) circulaient sans script de reconstruction
retrouvé : ils sont remplacés par les valeurs ci-dessus, seules reproductibles à ce jour. La
couverture globale des remerciements de financement sur le corpus est de **21,3 %** — un plancher
de lisibilité en dessous duquel aucune ventilation par champ n'est affichée.

### 9.7 Notes de construction diverses

**Trace par code de financement.** Le rapprochement par code de financement OpenAlex identifie
**808** travaux (`In_LUE_openalex_award`) — à ne pas confondre avec une valeur antérieure de 749,
issue d'une construction différente et remplacée. La liste de DOI reste, sans changement, la
définition canonique du drapeau `In_LUE`.

**Freiberg (consortium EURECA).** Le partenaire est en réalité **deux identifiants** OpenAlex
distincts (l'université technique et l'institut Helmholtz associé). Le compte correct est l'union
des travaux distincts des deux identifiants, soit **15**, et non la somme des deux compteurs pris
séparément, qui compterait deux fois le travail commun aux deux identifiants — d'où **16** dans une
lecture par somme.

**Code pays « NA ».** Le code ISO du partenaire namibien résolu par OpenAlex est la chaîne littérale
`NA` — le code pays réel de la Namibie, et par ailleurs la valeur que la plupart des lecteurs
CSV/Excel interprètent par défaut comme un vide. La construction lit le parquet nativement et
conserve la Namibie correctement (**jamais nul**) ; tout export ultérieur vers CSV ou Excel doit
désactiver cette conversion implicite, sous peine de faire disparaître ce partenaire dans le compte
des pays inconnus.

**`ptn_topics` par état de conférence.** La table croisant partenaire et topic porte, comme sa table
mère `ptn_fields`, une clé par état de conférence : un tirage hors-conférence qui descendrait vers
des lignes de topic calculées tous types confondus aurait été une incohérence visible entre les deux
niveaux. La table est construite par état, sur le même schéma qu'avant.

**Réciprocité partenaires (42b), pull 2026-08-17.** La part réciproque (`share_p`, la part du volume
**propre** d'un partenaire — hors du périmètre lorrain — qui implique l'UL) exige un appel OpenAlex
dédié au partenaire lui-même : `pipeline/42b_pull_partners_base.py`. Cet appel, gelé à `NULL` dans
les passes précédentes, a été exécuté le **2026-08-17** sur **~3 616 partenaires** — l'union, par
niveau (domaine/champ/sous-champ) et par entité, des tops 20 internationaux, 20 français et 50
« réciprocité », soit exactement le périmètre que l'application peut un jour afficher, jamais plus.
`share_p` et son dénominateur (`partner_total_windowed`) ne se peuplent que sur les lignes **« tous
types, tout le corpus »** (`conf_state='all', subset_id='all'`) : une part hors-conférence rapportée
à un dénominateur qui inclut les actes de conférence, ou une part restreinte au sous-ensemble LUE
rapportée au dénominateur du corpus entier, ne serait pas une part réelle — ces lignes restent donc
`NULL`, jamais 0. Le même principe vaut pour `ptn_fields.baseline_partner_share`, qui ne se peuple
que sur les lignes tous types. Quand le ratio brut dépasse 100 % (dérive entre l'instantané figé du
2026-08-11 et OpenAlex en direct au moment du tirage), la valeur est plafonnée à 100 % et signalée
(`share_p_capped_flag` sur `ptn_summary` ; comptage divulgué, sans colonne dédiée, sur les tableaux
de la page 4) — ce plafonnement est toujours affiché, jamais silencieux. Les 3 partenaires issus
d'une fusion de succession (`successor_merges.csv`, ex. INRA→INRAE) reçoivent leur dénominateur
d'un tirage supplémentaire par union d'identifiants (`institutions.id:A|B`), puisque leur numérateur
côté UL somme déjà les deux identifiants.

### 9.8 Benchmark pairs (T4b) — pull 2026-08-17

Neuf établissements pairs, arrêtés par l'atelier (17 août 2026) parmi les options du dossier
`docs/benchmark_peer_candidates.md` : trois I-SITE de parité (Lille, Nantes, Clermont Auvergne),
un IDEX d'aspiration (Grenoble Alpes), un transfrontalier (Liège), quatre miroirs européens
(Duisbourg-Essen, Tampere, Oulu, Pays basque/UPV-EHU). Le registre
`inputs/overlays/bench_peers.csv` reste la seule chose à éditer pour ajouter, retirer ou remplacer
un pair — l'atelier garde son pouvoir d'arbitrage par simple case à cocher, sans toucher au code.

**Quatre nombres UL, un seul à la fois.** La ligne UL du tableau de benchmark n'est **aucun** des
trois chiffres déjà en circulation ailleurs dans l'outil : ni le corpus canonique v2 (36 819
travaux, périmètre par lignée OpenAlex), ni le corpus v1 (28 094). C'est un **quatrième** périmètre,
volontairement plus étroit : l'identifiant direct de l'UL, sur la même fenêtre et les mêmes cinq
types de publication que chaque pair — **28 464 travaux** dans cet instantané, mesuré le 17 août
2026 (contre ~28 485 sur un comptage direct entièrement en direct le même jour — un écart de
0,1 % au plus, dû aux filtres propres au corpus, disclosed et jamais corrigé silencieusement). Ce
choix n'est pas arbitraire : c'est la seule des quatre perspectives qui traite l'UL exactement
comme chaque pair, sans quoi la comparaison ne serait pas symétrique.

**L'asymétrie direct/lignée touche les Français, pas les étrangers.** L'identifiant « direct » d'un
établissement français sous-compte fortement ses structures composantes rattachées par cotutelle
(unités mixtes de recherche) : l'écart mesuré entre le comptage par lignée et le comptage direct va
de ×1,29 à ×2,18 pour les quatre pairs français retenus, contre ×1,00 à ×1,08 pour les cinq pairs
étrangers. Toute comparaison de taille entre un pair français et un pair étranger porte donc une
marge d'erreur asymétrique d'environ **25 à 35 %** — jamais un critère de taille utilisé seul pour
départager deux établissements.

**Le FWCI référencé sur la France reste un étalon commun, pas une norme mondiale.** Les indicateurs
de citation des neuf pairs passent par exactement la même machinerie que ceux de l'UL — la même
strate (sous-domaine × année × type), le même seuil de fiabilité (30 travaux), le même plancher
« NULL, jamais 0 » — mais la référence elle-même reste **française**, y compris pour un pair
allemand ou finlandais. Un pair étranger qui affiche un FWCI_FR inférieur à 1 n'est donc pas « moins
cité dans l'absolu » : il est moins cité **au regard d'un référentiel qui n'est pas le sien**, un
choix de méthode assumé (un étalon fixe et commun, préférable à neuf référentiels nationaux
incomparables entre eux), jamais une évaluation de qualité scientifique.

**Deux pairs excluent une école qui, chez l'UL, reste incluse.** Nantes Université exclut Centrale
Nantes (identifiant OpenAlex propre) ; l'Université Grenoble Alpes exclut Grenoble INP
(établissement-composante à personnalité juridique propre). L'UL, à l'inverse, **inclut** ses
propres écoles internes (Mines Nancy, ENSGSI…) dans son identifiant direct. Le sens du biais est
donc connu et univoque : la part « ingénierie-matériaux » de ces deux pairs se lit **sous-estimée**
par rapport à celle de l'UL, jamais l'inverse — une phrase à part entière sur la page, pas une
note de bas de page.

**Bande de dérive et deux dates.** Les effectifs pairs pulled (17 août 2026) sont vérifiés à ±3 %
contre le CSV gelé du dossier de sélection (même date) : le pair calibré en premier, Tampere,
affiche un écart de −0,02 % ; les huit autres, entre +0,00 % et −0,04 %. Cette bande contrôle une
**amplitude** de dérive OpenAlex entre deux dates de collecte — elle ne prouve pas, à elle seule,
que la recette de filtre est correcte (une bascule accidentelle vers un comptage par lignée sur un
pair français aurait produit un écart bien supérieur à 3 %, donc détectable ; sur les cinq pairs
étrangers, l'écart lignée/direct est trop faible pour être détecté par cette seule bande — la chaîne
de filtre elle-même est donc revue par lecture, pas seulement par la mesure). Les deux dates —
probe gelé et pull de cette passe — sont affichées ensemble sur la page ; elles coïncident cette
passe-ci, elles pourront diverger lors d'un futur rafraîchissement.

**Couverture d'indicateurs par pair.** La part de travaux dont l'indicateur FWCI_FR est calculable
(strate française suffisamment épaisse) est mesurée pour chacune des dix entités : elle se situe
entre 96,8 % (Duisbourg-Essen) et 98,6 % (Grenoble Alpes), l'UL elle-même à 97,4 %. Aucune entité ne
descend sous 95 % dans cet instantané ; si l'une d'elles y descendait lors d'un futur pull, la page
l'afficherait explicitement plutôt que de laisser la moyenne se dégrader en silence.

**Le tableau n'est pas filtrable par le bouton « hors référentiel ».** Les corpus des neuf pairs
sont tirés en direct d'OpenAlex, hors de l'instantané local qui porte la liste des 811 topics
exclus : il n'existe aucun moyen de savoir lesquels de leurs travaux portent un topic marqué. La
table est donc **exemptée par construction** — ni colonne `_xa`, ni bascule active — et la page
affiche la bandeau d'exemption standard, jamais le comportement du filtre.

**Deux moyennes FWCI_FR coexistent pour l'UL, sur deux périmètres différents — jamais une
contradiction (passe 5, I2-09).** Le §4 documente une moyenne de **0,938** sur le corpus canonique
complet (36 819 travaux, périmètre par filiation). La ligne UL du Benchmark, sur le périmètre
direct-id plus étroit de ce paragraphe (28 464 travaux), affiche une moyenne de **1,03** et une
médiane de **0,25** (recalculées le 2026-08-18). Les deux moyennes ne se contredisent pas : elles
portent sur deux périmètres différents, toujours nommés ensemble, jamais choisis en silence. Le
grand écart apparent entre la médiane (0,25) et l'une ou l'autre moyenne mesure la même chose sur
les deux périmètres — les citations françaises s'agglutinent aux valeurs basses (médiane française
à 1 citation, 43,2 % de publications jamais citées, §4) — ce qui tire mécaniquement toute médiane
de FWCI bien sous 1, un effet de distribution, jamais un signal de dégradation. La page place cette
explication en légende directement adjacente à la ligne « FWCI, méd. » (R19 caveat-adjacency),
plutôt que de laisser les deux nombres publiés se contredire sans lien entre eux.

**Deux signaux de forme du portefeuille, définis ici pour la première fois (passe 5, I2-13).**
« Concentration — 3 premiers champs » est la part cumulée des trois champs disciplinaires (sur 26)
qui portent le plus de travaux d'une entité, en part de son propre total — un signal de forme,
jamais un signal de qualité. « Dispersion de spécialisation (écart-type LQ) » est l'écart-type, sur
les 26 champs, du quotient de localisation (LQ) de chaque champ vis-à-vis de la France. Aucun
plancher de taille de champ n'est appliqué avant ce calcul cette passe-ci : un champ à très faible
effectif peut peser autant qu'un champ à fort effectif dans l'écart-type mesuré (constaté chez un
pair : un champ à 158 travaux, 1,1 % de son volume total, porte un LQ de 6,32 et tire une bonne
part de sa dispersion affichée). Disclosed sur la page elle-même (légende adjacente aux deux
lignes), pas silencieusement absorbé dans le nombre — un plancher ou une pondération par volume
reste une option chiffrée pour un futur pull, non construite cette passe-ci.

### 9.9 Renommage LUE → I-SITE (passe 5, 2026-08-18)

**Renommage mécanique, aucune valeur changée.** Le nom interne « LUE » (hérité du label historique
de l'appel à projets « ISITE-LUE ») disparaît de tous les identifiants et libellés propres à l'outil
— colonnes parquet, valeurs de `subset_id`, variables de constructeur, libellés d'interface — au
profit de « ISITE » / « I-SITE ». Exemples : `works_master.In_LUE` → `In_ISITE` ;
`In_LUE_openalex_award` → `In_ISITE_openalex_award` ; les identifiants de périmètre `in_lue` /
`in_lue_award` → `in_isite` / `in_isite_award` ; `ptn_summary.lue_co_works`/`lue_share` →
`isite_co_works`/`isite_share` ; `thm_frontier.lue_works`/`lue_works_xa` →
`isite_works`/`isite_works_xa` ; `consortium_weights.scope` valeur `lue` → `isite`. Les valeurs
elles-mêmes sont strictement inchangées (1 839 travaux I-SITE, 749 travaux à correspondance exacte
de la subvention, 9 travaux à correspondance exacte hors liste canonique, 808 travaux dans la
famille élargie de traçage de la subvention, delta de 32 travaux) : seul le nom de la colonne ou de
la valeur de périmètre change, jamais le calcul.

**Ce qui reste « LUE » à dessein — des faits historiques, pas des identifiants.** Le nom réel de la
subvention OpenAlex reste « Isite LUE » (`G3172997804`, ANR-15-IDEX-0004) : c'est le nom que
l'organisme funder porte réellement, cité tel quel partout où le code ou la documentation
mentionnent cette subvention. Les motifs de correspondance textuelle qui identifient cette
subvention dans les paiements bruts d'OpenAlex (`15-IDEX-0004`, `15-IDEX-04-LUE`, `ISITELUE`) restent
également inchangés, car ce sont des chaînes appariées littéralement contre les métadonnées externes
— les modifier casserait la correspondance. Enfin, la colonne `In_LUE` du Phase 1 (v1, figée,
jamais retouchée) garde son nom d'origine partout où le contrat ou le rapport d'écart la citent
comme référence historique (`from_v1: "In_LUE"`).

**Correction de fait au passage (D-INV, memo `reports/isite_award_reconciliation.md`).** Le
commentaire historique « la fusion n'ajouterait que 6 travaux » (config.yaml, contrat de données)
était obsolète : la mesure exacte sur l'instantané canonique 2026-08-11, reproduite en direct le
2026-08-18 (coût OpenAlex $0,0004), donne **9** travaux, pas 6. Les deux fichiers ont été corrigés
avec citation de la source. Ce chiffre n'était vérifié par aucun test — dérive de documentation, pas
défaut de la donnée.

### 9.10 Contexte pairs — ODD, positionnement frontière, diversité (passe 5, 2026-08-18)

Trois tables comparent, pour la première fois, l'Université de Lorraine à ses neuf pairs sur des
terrains autres que le volume et la citation (déjà couverts par le Benchmark T4b, §9.8) : les
Objectifs de développement durable, le positionnement frontière et la diversité disciplinaire. Les
trois s'appuient sur le tirage large des corpus pairs (`raw/peers/<id>_wide.jsonl.zst`, neuf
établissements, 200 832 travaux) réalisé pour cette passe, dont l'exactitude a été revérifiée
avant tout calcul : chaque pair reproduit **exactement** (zéro travail d'écart) le total que le
tirage étroit de la passe 4 avait lui-même mesuré, sur les neuf établissements — la « collecte
large égale la collecte étroite » n'est donc pas une hypothèse, c'est une propriété mesurée.

**Le principe commun aux trois tables : le côté lorrain n'est jamais le corpus canonique.** Comme
pour le Benchmark T4b, la ligne UL est l'identifiant OpenAlex **direct** de l'établissement, sur la
même fenêtre et les mêmes cinq types de publication que chaque pair — **28 464 travaux**, pas les
36 819 du corpus par filiation. C'est la seule des perspectives qui traite l'UL exactement comme
chaque pair ; la comparer sur le corpus par filiation aurait avantagé l'UL d'une manière qu'aucun
pair ne peut reproduire (§9.8 en donne la mesure : l'écart direct/filiation atteint ×2,18 pour un
établissement français, contre ×1,08 au plus pour un établissement étranger).

**Objectifs de développement durable (`bench_sdg`) — méthode OpenAlex/Aurora des deux côtés.**
Contrairement au panneau ODD principal de l'application (route B, vocabulaire contrôlé SIRIS, §5),
cette table compare les deux côtés sur la **même** méthode : le champ natif d'OpenAlex/Aurora,
seuil à 0,40 (le plancher propre d'OurResearch, rien n'est publié en dessous). Côté lorrain, ce
champ est déjà présent dans l'instantané (`corpus_sdg.parquet`, extrait à la collecte) ; côté pairs,
il provient du même tirage large. La part rapportée est la part du **total** de l'établissement
(pas seulement de ses travaux tagués), ce qui diffère délibérément de la construction du croisement
labo × ODD (§9.11) — deux dénominateurs différents, pour deux questions différentes, jamais
confondus silencieusement. Un ODD 17 existe dans cette table (Aurora l'étiquette) alors qu'il n'a
pas de feuille dans le vocabulaire SIRIS à 16 passes — encore une différence de nature entre les
deux routes, pas un défaut. Contrôle en direct : trois appels `group_by` OpenAlex (clé financée,
0,0003 $ au total) reproduisent **exactement** les deux pairs déjà vérifiés à 0 % de dérive par la
passe 5 (Clermont-Auvergne, Lille), et situent l'UL dans un écart de 0 à 3 travaux par ODD — du même
ordre que l'écart direct/en-direct de 0,1 % déjà déclaré au §9.8, c'est-à-dire une dérive normale de
l'index OpenAlex sur les sept jours écoulés entre l'instantané et le contrôle, pas un défaut de
construction.

**Positionnement frontière (`bench_positioning`) — symétrie complète, sans variante.** Le panneau
frontière déjà livré (T9, §9.5) assigne déjà chaque travail par son **seul topic principal** — une
propriété vérifiée, pas supposée, en relisant le code de `47_build_thematic_ext.py`. Les pairs ne
portent eux aussi que le topic principal dans le tirage large. La construction se transpose donc
**mot pour mot** : même fichier de référence, même liste de 811 topics exclus, même rang centile
(brut et standardisé par champ). Aucune variante étiquetée n'est nécessaire ici — à la différence de
la diversité ci-dessous, où la construction native ne se transpose pas.

**Diversité disciplinaire (`bench_diversity`) — variante symétrique étiquetée, transfert vérifié à
l'identique.** Ici, la construction native (`thm_diversity`, §6 et le catalogue Rao-Stirling/DIV)
pondère **chaque** topic d'un travail, pas seulement le principal — une moyenne de 2,65 topics par
travail. Un pair ne porte que son topic principal : reconstruire la matrice de poids sur cette seule
donnée annule toute co-occurrence entre sous-domaines (un travail à un seul topic ne peut jamais
peser sur deux sous-domaines à la fois), ce qui aurait rendu la matrice de disparité dénuée de sens,
pas seulement différente. La correction retenue conserve ce qui **peut** être commun aux deux côtés
— la matrice de disparité 252×252, propriété des **paires** de sous-domaines, construite une seule
fois sur le corpus lorrain complet et réutilisée sans changement, comme le score de frontierness ou
les z-scores ne sont jamais recalculés sur un sous-ensemble (§9.5) — et calcule pour chaque entité
(UL et les neuf pairs) sa propre diversité à partir du seul topic principal. Chaque ligne porte
l'étiquette `primary_topic_both_sides`.

**La barre de transfert est vérifiée, pas supposée.** Recalculer, avec ce même code copié, la ligne
déjà publiée de `thm_diversity` (périmètre entier, année 2019, tous types) reproduit sa valeur
**exactement** (écart 0,00 sur les quatre composantes variety/balance/disparity/rao_stirling) — la
preuve que le code repris est fidèle, pas seulement ressemblant. **Les deux chiffres lorrains sont
montrés côte à côte, jamais l'un à la place de l'autre :** la valeur déjà publiée (méthode multi-
topic, périmètre par filiation, année 2019 seule) donne **0,3217** ; la ligne UL de `bench_diversity`
(méthode topic principal seul, périmètre direct, fenêtre 2019-2023 complète) donne **0,3327**. Ce
n'est pas un écart de méthode pur — le périmètre et la fenêtre temporelle diffèrent aussi en même
temps — et il n'est jamais réduit à un seul chiffre d'« erreur » : les deux valeurs sont nommées et
expliquées ensemble. Sur l'ensemble des dix entités, l'indice se situe entre 0,290 et 0,364 — un
intervalle resserré, sans valeur aberrante.

**Ce que ces trois tables ne portent jamais.** Aucune colonne `_xa` nulle part, y compris sur la
ligne UL : les corpus pairs sont tirés en direct d'OpenAlex, hors de l'instantané local qui porte la
liste des topics exclus, donc rien ne permet de savoir lesquels de leurs travaux porteraient le
marqueur — exemption par construction, la même que celle du Benchmark T4b (§9.8), appliquée
uniformément aux trois nouvelles tables.

### 9.11 Croisements labo × frontière / labo × ODD (passe 5, 2026-08-18)

Deux tables nouvelles, `thm_frontier_labs` et `thm_sdg_labs`, répondent à une question différente de
celle du §9.10 : non pas « comment l'UL se compare-t-elle à ses pairs », mais « comment le
positionnement frontière et le profil ODD varient-ils **d'un laboratoire lorrain à l'autre** ». La
règle du porteur du projet est stricte et delibérée : **un croisement n'est pas une comparaison** —
aucune des deux tables ne porte de colonne, de ligne ou de dénominateur pair. L'univers des
laboratoires est le même que celui déjà utilisé pour la diversité par périmètre (§6, T3) : 69
structures curées, y compris la catégorie « NO LAB » (les 4 568 travaux sans structure curée),
retenue pour la même raison qu'ailleurs — c'est une part réelle et mesurable du corpus.

**Frontière par laboratoire.** Un travail « frontière » est ici défini par le même seuil que celui
qui produit le facteur d'amplification déjà publié (×1,37 brut) : appartenir au décile supérieur des
topics retenus. La part standardisée par champ généralise à 69 groupes la standardisation directe
déjà appliquée à l'I-SITE (§9.5) — chaque laboratoire est ramené à un **même** référentiel de
mélange disciplinaire (celui du corpus entier), au lieu d'être comparé à un seul autre groupe. Un
garde-fou a été ajouté après l'avoir vu se déclencher en réel : un laboratoire ne possédant qu'un
seul travail dans un champ fortement pondéré au niveau du corpus voyait sa part standardisée
multipliée par 7,4 par ce travail unique. Les cellules laboratoire × champ sous trois travaux sont
donc exclues du calcul de ce laboratoire (le même plancher que celui des mini-graphiques I11), ce
qui ramène l'écart à un facteur 2,2, défendable.

**ODD par laboratoire.** Cette table suit la route B (vocabulaire SIRIS), celle du panneau ODD
principal de l'application — pas la route Aurora du §9.10, qui compare, elle, les pairs. Le
dénominateur est le nombre de travaux **tagués** du laboratoire, jamais son effectif total : un
laboratoire dont peu de travaux sont tagués n'a pas « 0 % » d'ODD, il a une part non calculée pour
les ODD qu'aucun de ses travaux tagués ne porte. Les parts d'un même laboratoire peuvent dépasser
100 % cumulées : un travail peut porter plusieurs ODD (1,445 en moyenne sur les travaux tagués,
§5). Aucune décomposition I-SITE n'accompagne cette table cette passe-ci — la croiser encore par
I-SITE ferait tomber presque toutes les cellules sous le plancher de 30 travaux, à seulement 14,8 %
de couverture ODD sur l'ensemble du corpus ; signalé comme option chiffrée, non construite.

**Ce que les deux tables garantissent.** Chaque comptage est doublé de sa version hors-référentiel
(`_xa`), selon la même convention que partout ailleurs dans le pipeline. Deux identités de
recoupement sont vérifiées à la construction, pas seulement affichées : l'effectif de chaque
laboratoire (état « tous types ») reproduit **exactement** celui déjà publié dans `ul_labs`, pour
les 69 structures ; et l'union des ensembles de travaux tagués ODD de ces 69 catégories reproduit
**exactement** l'ensemble complet des 5 447 travaux tagués par la route SIRIS — une vérification par
union, pas par somme, puisqu'un travail à plusieurs laboratoires ne doit jamais être compté deux
fois dans ce contrôle.

### 9.12 Recouvrement I-SITE (bascule d'affichage) — note de données

Le bouton I-SITE, à la différence du filtre « hors référentiel » (§9.1), ne retire jamais de ligne :
là où une décomposition existe, il assombrit la part qui relève de l'I-SITE sur la barre déjà
affichée — sans nouveau calcul à l'affichage. **Correction (passe 5, I2-06) : le bouton n'assombrit
PAS « chaque barre déjà affichée ».** Une décomposition n'existe que sur les panneaux qui la
portent réellement — la moitié environ des barres de l'outil n'ont, à ce jour, aucune décomposition
I-SITE (page 2 « Yearly Distribution by Domain », page 4 ODD, page 6 Top Partners, page 9 Volume
annuel, page 12 identité thématique, entre autres) et restent inchangées, toggle ON ou OFF. Le
contrat complet, page par page, panneau par panneau — quelle colonne porte cette décomposition,
laquelle a été ajoutée cette passe-ci, laquelle est N/A-disclosed et pourquoi, et le ledger complet
des cas N/A — vit dans `docs/OVERLAY_MATRIX.md`, jamais dupliqué ni résumé de façon optimiste ici.
Deux principes s'en dégagent, utiles à toute future extension : une décomposition sur la même ligne
(`isite_co_works` à côté de `co_works`) est la forme à viser quand un graphique montre un total
unique par catégorie ; un indice composite (diversité, centile moyen de frontierness) ne se
décompose jamais ainsi — sa version I-SITE est une seconde ligne, un second point, jamais une part
de la même barre. Un lecteur qui active le bouton sur un panneau non décomposé doit trouver, sur ce
panneau, la légende N/A-disclosed correspondante quand elle existe déjà (pages 4, 6, 9 notamment) ;
deux panneaux (page 2 « Yearly Distribution by Domain », page 12) n'en portent encore aucune —
disclosed ici plutôt que silencieusement corrigé, une légende de non-effet sur ces deux panneaux
reste un chantier ouvert, pas un fait déjà livré.

### 9.13 Retrait du panneau « Financement par champ » (T7) de l'interface (passe 5, R10)

Le panneau T7 (leviers de financement par champ, §9.6) est retiré de l'interface de la page
« Portefeuille thématique » cette passe-ci. **La table `thm_funding` et son constructeur restent
inchangés dans le pipeline** — rien n'est supprimé côté données, seule la restitution à l'écran
s'arrête. Trois raisons, données ensemble plutôt qu'une seule présentée comme suffisante :

1. **Ce que la table mesure n'est pas ce qu'un « panneau financement » laisse attendre.** `thm_funding`
   compte des **publications qui MENTIONNENT un remerciement de financement** (une reconnaissance
   textuelle dans le corps du texte OpenAlex), jamais des projets financés, des montants, ni une
   attribution de crédit vérifiée. C'est un signal d'accompagnement (« combien de travaux d'un champ
   remercient au moins un bailleur ANR/EC/ERDF »), utile en soi (§9.6 le documente), mais qui ne peut
   pas porter, seul et présenté comme un panneau central de page, la question que « financement »
   suggère naturellement à un lecteur : quels projets, combien, portés par qui.
2. **Une vraie vue financement est un chantier séparé, pas une extension de ce panneau.** Elle suppose
   au minimum : les projets CORDIS (Horizon Europe) rattachés à l'UL, les financements ERC
   désambiguïsés par porteur, les financements ANR au niveau projet (pas seulement au niveau mention),
   et France 2030 — quatre sources qu'aucune des colonnes actuelles de `thm_funding` n'approche. Ce
   chantier n'est pas dans le périmètre de cette passe.
3. **Cohérence avec le principe qui gouverne déjà chaque panneau restant de cette page** (R9) : la
   page « Portefeuille thématique » répond aux questions de forme, de spécialisation et d'empreinte
   ODD du portefeuille — pas de financement. Un panneau add-on présenté comme central aurait brouillé
   cette lecture plus qu'il ne l'aurait enrichie.

`thm_funding` reste disponible pour toute reprise future (export xlsx du pipeline, ou un panneau
dédié une fois les quatre sources listées ci-dessus disponibles) — rien à reconstruire, seulement à
re-brancher côté interface.

### 9.14 Mise à jour annuelle (design) — renvoi

Ajouter une année (2024, puis 2025) n'est pas un ajout : c'est un **nouvel instantané complet**, donc
un **ré-étalonnage de tout l'outil**. OpenAlex étant une base vivante, une nouvelle collecte
rafraîchit les citations de **toutes** les années : chaque indicateur normalisé (FWCI_FR, PPtop,
momentum, contexte pairs) bouge aussi sur les années déjà publiées, pas seulement sur l'année
ajoutée. Deux conséquences à connaître avant toute lecture comparée : la liste canonique I-SITE
étant manuelle et figée (§9.12, D21), la part I-SITE de l'année la plus récente est un **plancher**
tant que le client ne l'a pas actualisée ; et les périodes de comparaison (fenêtres de momentum,
harmonie 3 ans / 3 ans) relèvent d'une décision d'atelier, pas d'un paramètre technique.

La conception complète — mécanique du pipeline, protocole de ré-étalonnage des témoins, options de
fenêtre glissante, dispositif de divulgation du décalage I-SITE, mode opératoire « un seul bouton »
et plan de répétition — vit dans `docs/YEAR_UPDATE_DESIGN.md`, jamais résumée ni dupliquée ici.

### 9.15 Nouvelles tables passe 6 (S-DAT)

**Comparaison de méthode ODD par labo (`sdg_lab_methods`).** Chaque labo (les 69 de l'annuaire,
NO LAB compris) reçoit, pour chacun des 16 ODD, deux comptages indépendants : la méthode SIRIS
(vocabulaire contrôlé, VocTagger) et la méthode Aurora (champ natif OpenAlex, seuil 0,40, le
plancher publié par OurResearch lui-même). Les deux comptages partagent le même périmètre de
travaux par labo ; ils ne mesurent jamais la même chose que la comparaison SIRIS/OpenAlex du
panneau ODD principal (§5), qui porte sur le site entier. La part du corpus du labo tagué par
chaque méthode complète le panneau existant, qui rapportait déjà une part des travaux tagués :
la nouvelle colonne rapporte au corpus entier du labo, y compris ses travaux jamais tagués. Un
croisement de méthode reste un croisement, jamais une comparaison entre labos.

**Tops labo profondeur 30 (`lab_top_partners`, `lab_top_authors`).** Les dix partenaires ou
auteur·es affichés par défaut sur la fiche labo reposent sur une table qui en matérialise 30
(international et France pour les partenaires, deux méthodes pour les auteur·es). La méthode
« maison » reprend la réconciliation d'identité déjà utilisée pour l'annuaire des auteur·es
(un même chercheur peut publier sous plusieurs profils OpenAlex) ; la méthode « ORCID uniquement »
regroupe par identifiant ORCID brut, sans aucune réconciliation de nom, pour donner un second
point de vue plus strict. Les deux méthodes cohabitent dans une seule table.

**Nuage de mots à trois niveaux (`lab_wordcloud`).** Le nuage existant (sous-champs) gagne deux
variantes : les topics OpenAlex et les mots-clés associés à chaque topic (une dizaine par topic,
issus du vocabulaire OpenAlex complet). Le poids d'un terme est un compte de travaux, jamais une
pondération fractionnée.

**Liste de publications par labo (`lab_works`).** Chaque labo dispose désormais d'une table de
ses publications, avec les indicateurs de qualité déjà connus (FWCI_FR, PPtop, statut I-SITE,
drapeau hors référentiel) et le tag ODD SIRIS. Cette table alimente les téléchargements par labo
et par ODD sans jamais charger le fichier global des publications en mémoire.

**Tables pleines des topics et sous-champs (`topics_zero_fill`, `subfields_zero_fill`).** Les
tables d'affichage existantes ne portent une ligne que pour un topic ou un sous-champ effectivement
présent dans le corpus lorrain. Une recherche de type « quantum » pouvait donc manquer un topic
réel si aucun travail lorrain ne s'y rattachait. Les deux nouvelles tables reprennent le
vocabulaire OpenAlex complet (4 516 topics, 252 sous-champs) : le volume est ramené à zéro quand
le corpus n'y contribue pas, mais les indicateurs de taux (part ISITE, FWCI, momentum) restent
vides plutôt que faussement nuls, un ratio sur zéro travail n'ayant pas de valeur.

**Dénominateurs partenaires (`ptn_denominators`).** Trois nouvelles parts complètent la part déjà
publiée d'un partenaire dans le corpus collaboratif de l'UL : sa part du corpus entier de l'UL,
sa part des co-publications françaises de l'UL une fois retirés les huit signataires du
consortium I-SITE (ce que pèse réellement un partenaire français une fois écartés les candidats
naturels du site), et pour un partenaire international, sa part des co-publications
internationales de l'UL et sa part des co-publications de l'UL avec son propre pays. Un signataire
du consortium ne reçoit jamais de part « hors site » : la question ne le concerne pas par
construction.

**Momentum aux mailles thématiques (`thematic_overview`, `thematic_detail_sublevels`).** Le CAGR,
peu lisible sur des séries courtes, cède la place au momentum déjà utilisé pour les partenaires :
même méthode de ratio recentré et de test de significativité, appliquée cette fois à un domaine,
un champ, un sous-champ ou un topic plutôt qu'à un partenaire. La référence de recentrage (le
« marché » auquel chaque maille est comparée) est calculée une seule fois au niveau des champs (26
mailles, une population stable) et réutilisée à tous les niveaux plus fins, exactement comme la
référence au niveau partenaire est réutilisée par les mailles partenaire × topic. Le CAGR continue
d'être calculé (des consommateurs gelés peuvent encore le lire) mais n'est plus l'indicateur de
dynamique mis en avant.

**Deux lectures chiffrées du momentum, jamais comparables entre elles (décision passe 6).** La
CLASSIFICATION (hausse / baisse / stable / non significatif) suit la même méthode aux deux
mailles : ratio recentré et test de significativité. Le CHIFFRE affiché à côté du glyphe, lui,
diffère par construction et par choix. À la maille partenaire, l'application affiche le delta
relatif recentré — (part fenêtre 2 / part fenêtre 1) ÷ médiane de recentrage − 1, exprimé en % —
car la médiane y est persistée et corrige la dérive d'ensemble du corpus collaboratif. Aux
mailles thématiques, l'application affiche l'écart brut entre les deux parts de fenêtre,
exprimé en points de pourcentage (pt) : les deux parts y rapportent au même total, aucune
médiane de recentrage n'est persistée à cette maille, et fabriquer une médiane implicite
laisserait croire à une correction qui n'a pas eu lieu. Un chiffre en « pt » et un chiffre en
« % » ne se comparent donc jamais l'un à l'autre — l'unité affichée est le marqueur de la
lecture employée.

**Nom complet des labos (`ul_labs.nom_complet`).** Le fichier client ne porte que des sigles
(« IJL », « LORIA »...). Le nom complet est recherché auprès de l'identifiant ROR de chaque labo
(source `ror`) ; à défaut d'identifiant ROR exploitable, la case reste vide plutôt que de recevoir
un nom inventé. Deux entrées du fichier client sans ROR réel (la ligne ISITE, la ligne NO LAB)
restent ainsi vides par construction.

**Correction du graphique FWCI par champ (#33).** Un champ pour lequel aucun travail du labo n'a
d'indicateur calculé (strate trop mince) affichait un profil plat à zéro, indiscernable d'un champ
dont le FWCI médian vaut réellement zéro. La construction omet désormais ce champ du bloc de
données plutôt que d'y inscrire une valeur ; l'application traite déjà l'absence comme une valeur
manquante partout ailleurs, aucune modification côté écran n'était nécessaire.
