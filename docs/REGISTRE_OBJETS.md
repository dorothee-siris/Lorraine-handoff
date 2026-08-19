# Registre des objets de l'application

Instantané de référence : **2026-08-11**. Fenêtre de publication : **2019-2023**. Ce document
répond à une question posée par le porteur du projet à la lecture de l'outil : « y a-t-il un
document qui recense tous les objets utilisés dans l'application et leurs liens entre eux ? ».

Un objet, ici, est une entité que plusieurs vues et plusieurs indicateurs manipulent sous le même
nom : un pays, un laboratoire, un partenaire, un auteur ou une auteure, un niveau de la taxonomie
thématique, un objectif de développement durable (ODD), un type de document, un drapeau ISITE, une
période. Chaque objet a une définition précise, une source de données identifiée, une règle
d'affichage et des pièges connus. Ce registre les rassemble en un seul endroit plutôt que de les
laisser dispersés dans le code, la documentation de méthode et les fichiers de données.

**Quand consulter ce registre.** Avant d'ajouter une vue ou un export qui touche à un objet déjà
répertorié ici, pour repartir de sa définition plutôt que d'en improviser une variante. Avant de
répondre à une question du type « ce chiffre compte-t-il la même chose que celui de la page
voisine ? », en particulier pour les objets qui portent plusieurs définitions concurrentes
(partenaire, drapeau ISITE, laboratoire). Avant toute mise à jour annuelle de l'instantané
(`docs/YEAR_UPDATE_DESIGN.md`), pour vérifier qu'aucun objet n'a changé de règle entre deux
collectes.

## Comment lire une fiche objet

Chaque objet ci-dessous porte un tableau à deux colonnes, avec les huit informations suivantes.

| Champ | Ce qu'il donne |
|---|---|
| Définition | ce que l'objet représente, en une ou deux phrases, sans ambiguïté |
| Unités / valeurs | le domaine de valeurs (codes, échelle, cardinalité) |
| Source | d'où vient la valeur (API, fichier manuel, calcul dérivé) et quel fichier de l'instantané la porte |
| Langue d'affichage | français ou anglais côté interface, et pourquoi |
| Vues consommatrices | les pages de l'application qui affichent l'objet |
| Indicateurs | les mesures construites sur cet objet |
| Objets liés | les autres objets de ce registre avec lesquels celui-ci s'articule |
| Pièges | les erreurs de lecture déjà identifiées, avec leur source |

La correspondance mécanique entre chaque objet et les tables de données qui le portent vit dans le
bloc `yaml` en annexe technique, en fin de document. `docs/registre_check.py` la vérifie contre
`docs/data_contract.yaml` : toute table déployée doit y apparaître sous au moins un objet, et tout
objet doit y porter au moins une table ou être marqué explicitement « dérivé » (un objet documenté
ici sans table dédiée). Onze objets sont couverts : les dix nommés par le porteur du projet, plus
un onzième (« établissement pair ») ajouté pour que la correspondance couvre l'ensemble des tables
déployées, sans lequel les quatre tables du Benchmark (§ établissement pair) resteraient orphelines.

---

## Pays

| Champ | Contenu |
|---|---|
| Définition | le pays d'une affiliation portée par une publication du corpus, tel qu'OpenAlex le résout à partir de l'institution affiliée. Un même travail peut porter plusieurs pays (un par institution co-autrice) ; un partenaire peut lui-même n'avoir qu'un seul pays. |
| Unités / valeurs | code ISO 3166-1 alpha-2 tel que renvoyé par OpenAlex (`institution_country`), plus la valeur littérale `UNKNOWN` pour les affiliations sans institution résolue (`geo_countries.parquet`, colonne `unknown_bucket_flag`). |
| Source | affiliations brutes de la collecte OpenAlex (`corpus_authorships.institution_country`), jamais un champ saisi à la main. |
| Langue d'affichage | le code ISO2 est la clé technique interne (anglais/international par nature) ; l'affichage côté interface passe au nom français depuis la passe 6 (voir Piège ci-dessous). |
| Vues consommatrices | Géographie (page 10, vue dédiée), Collaborations (page 8), Zoom partenaire (page 9), Identifiants et couverture (page 13, partout où un pays de partenaire apparaît). |
| Indicateurs | co-publications par pays et par année (`geo_countries`), part internationale du corpus, part des co-publications ISITE par pays, part des co-publications avec le pays d'un partenaire donné (nouveau, passe 6, voir « Partenaire »). |
| Objets liés | Partenaire (chaque partenaire a un pays) ; Structure interne (l'Université de Lorraine elle-même est un point fixe, en France) ; Période (les tendances par pays se lisent année par année). |
| Pièges | **Le code ISO2 de la Namibie est la chaîne littérale `NA`**, à la fois le vrai code pays namibien et la valeur que la plupart des lecteurs CSV/Excel interprètent par défaut comme une cellule vide. La construction lit le parquet nativement et conserve la Namibie correctement, jamais comme un pays inconnu (`docs/METHODES.md` § 9.7, « Code pays « NA » »). Toute lecture ultérieure via `pandas.read_csv` ou un export Excel doit désactiver cette conversion implicite (`keep_default_na=False` / `na_values=[]`), sous peine de faire disparaître ce partenaire dans le compte des pays inconnus. **Le mapping ISO2 vers nom français est un contrat, pas encore un fichier figé au moment où cette fiche est écrite** : il repose sur `inputs/countries_fr.csv` (table de correspondance générée une fois, sans dépendance à une API en cours d'exécution) et sur `lib/countries_fr.py` (fonction `country_label()`), livrés par le chantier parallèle de cette même passe. Le contrat impose une résolution non nulle pour tout code ISO2 présent dans `geo_countries.parquet` ou dans les tables de partenaires, avec le code source affiché et journalisé (jamais une cellule vide) en cas de code non couvert par le fichier. La réciprocité (part du volume propre d'un partenaire) ne couvre que le périmètre effectivement tiré depuis OpenAlex (voir « Partenaire ») : au-delà, la valeur s'affiche `—`, jamais 0. |

## Laboratoire

| Champ | Contenu |
|---|---|
| Définition | une unité de recherche de l'Université de Lorraine (UMR, EA, USR...), cas particulier le plus consulté de l'objet « Structure interne » ci-dessous : une ligne de `ul_labs.parquet` dont `Structure type == "lab"`. C'est l'objet de la page Laboratoires (mini-fiches, tops, profil ODD). |
| Unités / valeurs | un laboratoire = une ligne de `ul_labs.parquet`, identifiée par sa clé `structure_key` (`'ROR:' + ror`) et son nom court. |
| Source | liste manuelle des structures fournie par le client (`inputs/manual`), croisée avec les descendants OpenAlex de l'Université (`ul_descendants.parquet`) pour repérer les structures rattachées mais hors liste. |
| Langue d'affichage | français pour le nom d'usage et le libellé de pôle ; le nom complet arrive cette passe dans le fichier source manuel (voir Piège) et sera affiché tel que fourni par le client. |
| Vues consommatrices | Laboratoires (page 2, mini-fiche complète) ; Vue d'ensemble (page 1, tableau des structures, tops internes) ; toute vue croisant laboratoire et thématique ou laboratoire et ODD (`thm_frontier_labs`, `thm_sdg_labs`, passe 5). |
| Indicateurs | volumes annuels par type de document et par domaine, part ISITE, FWCI_FR par champ, tops partenaires et auteur·es (30 chacun cette passe, voir « Auteur·e » et « Partenaire »), position frontière et profil ODD par laboratoire. |
| Objets liés | Structure interne (relation d'inclusion) ; Partenaire (portage de collaborations, § 9.7 de `docs/METHODES.md`) ; Auteur·e (tops par laboratoire) ; ODD et Thématique (croisements dédiés, passe 5). |
| Pièges | Le nom complet des laboratoires arrive dans le fichier source manuel cette passe (#3/#28, `BUILD_PLAN.md` P7) : toute valeur non fournie par le client et reconstituée depuis ROR/RNSR doit porter un marqueur de source explicite dans ce fichier ; une valeur non vérifiable reste vide plutôt qu'inventée. Le décompte « NO LAB » (travaux sans laboratoire curé de la liste client) reste inchangé par l'ajout des structures hors liste (`docs/data_contract.yaml`, note D56 sur `ul_labs.parquet`) : les structures hors liste ne sont jamais soustraites de NO LAB. Les 10 lignes de pôle scientifique (type `department`) chevauchent délibérément les lignes de laboratoire : la colonne « structure » du tableau ne somme donc pas au corpus total, ce qui est un comportement hérité et assumé, pas une anomalie. |

## Structure interne

| Champ | Contenu |
|---|---|
| Définition | toute entité de l'organigramme scientifique lorrain qu'`ul_labs.parquet` peut porter en ligne, plus large que le seul « Laboratoire » ci-dessus : quatre types codés dans la colonne `Structure type` (`lab`, `department`, `other`, `experimental`), plus un statut `in_client_list` qui distingue les structures de la liste client des structures que seul OpenAlex rattache à l'Université. |
| Unités / valeurs | 100 lignes dans l'instantané courant : les structures curées de la liste client, dix pôles scientifiques (type `department`, ajoutés en v2 pour retrouver la parité de sélection qu'avait la version précédente), et les structures hors liste détectées par OpenAlex (D56). |
| Source | liste manuelle des structures (client) pour les structures curées et les pôles ; requête OpenAlex par filiation (`authorships.institutions.lineage`) pour détecter les structures rattachées mais absentes de cette liste. |
| Langue d'affichage | français (noms de structures et de pôles fournis par le client). |
| Vues consommatrices | Vue d'ensemble (page 1, filtre par type de structure) ; Laboratoires (page 2, quand le type sélectionné est un laboratoire) ; le panneau I-SITE quand une structure hors liste porte des travaux liés à la subvention (page 7). |
| Indicateurs | tout indicateur de volume ou de composition disciplinaire disponible au grain « structure » de `ul_labs.parquet` (voir « Laboratoire » pour la liste, identique au grain structure). |
| Objets liés | Laboratoire (sous-ensemble) ; Pays (l'Université elle-même est un point de comparaison fixe pour les benchmarks pairs, voir « Établissement pair ») ; Partenaire (une structure hors liste peut aussi apparaître côté partenaire d'un autre établissement). |
| Pièges | OpenAlex rattache 90 structures à l'Université, dont 22 absentes de la liste client et 21 d'entre elles porteuses de publications sur la fenêtre (`docs/METHODES.md` § 1). Ces structures hors liste sont affichées avec la mention « hors liste » et exclues par défaut des classements, jamais retirées silencieusement du jeu de données. Une pseudo-structure « ISITE » existait dans la version précédente de l'outil (type `experimental`) : la version courante ne la reproduit pas, l'ISITE étant désormais un drapeau au niveau du travail (voir « Drapeaux ISITE ») plutôt qu'une structure qui aurait doublement compté ces travaux. |

## Partenaire

| Champ | Contenu |
|---|---|
| Définition | une institution externe à l'Université de Lorraine co-autrice d'au moins une publication du corpus. L'objet regroupe des institutions de nature très différente : universités, organismes de recherche, entreprises, hôpitaux, alliances transfrontalières (UniGR, EURECA-PRO). |
| Unités / valeurs | un partenaire = un identifiant d'institution OpenAlex, après fusion des cas de succession (ex. INRA devenu INRAE) et exclusion des identifiants internes à l'Université elle-même (liste de blocage `own_entity_blocklist.csv`). Univers mesuré à un ordre de grandeur de 12 500 institutions distinctes sur l'ensemble du corpus, tous seuils confondus (`ptn_summary.parquet`, base `all/all`). |
| Source | affiliations de la collecte OpenAlex, résolues et dédoublonnées par `pipeline/46_build_partner_views.py` ; les dénominateurs propres à chaque partenaire (son volume total hors du périmètre lorrain) proviennent d'un tirage OpenAlex dédié, distinct de la collecte du corpus (`ul_partners_base.parquet`, `pipeline/42b_build_partners_base.py`). |
| Langue d'affichage | français pour les libellés d'interface (« partenaire », « part partenaire », « pays du partenaire ») ; le nom d'affichage du partenaire lui-même reste celui qu'OpenAlex porte, généralement dans la langue d'origine de l'institution. |
| Vues consommatrices | Collaborations (page 8, tableau de synthèse) ; Zoom partenaire (page 9, vue la plus fine, un partenaire à la fois) ; Géographie (page 10, agrégation par pays et par groupe transfrontalier) ; Exploration thématique (page 6, tops internationaux et français par thème) ; Laboratoires (page 2, tops par laboratoire, 30 chacun cette passe). |
| Indicateurs | volume de co-publications, part internationale des co-publications, part de la co-publication dans le corpus total lorrain (« part UL ») et dans le corpus propre du partenaire (« part partenaire »), momentum (méthode figée en deux fenêtres, voir « Période »), FWCI_FR médian des co-publications, drapeau et part ISITE des co-publications. |
| Objets liés | Pays (chaque partenaire a un pays) ; Laboratoire (portage des collaborations par laboratoire lorrain) ; Structure interne (les sept membres externes du consortium ISITE, CNRS/Inserm/INRAE/CHRU Nancy/Georgia Tech/Inria/AgroParisTech, sont eux-mêmes des partenaires à statut particulier, voir « Drapeaux ISITE ») ; Période (fenêtres de momentum, tendance annuelle). |
| Pièges | **Deux dénominateurs de part ne mesurent pas la même chose et ne doivent jamais être confondus dans une même phrase** (`BUILD_PLAN.md` P4) : la « part UL » d'un partenaire est sa co-publication rapportée au corpus total lorrain (36 819 travaux) ; sa « part partenaire » est la même co-publication rapportée au volume propre du partenaire, en dehors du périmètre lorrain. Pour un exercice de réciprocité (« qui pèse le plus pour qui »), les deux parts se comparent côte à côte, jamais l'une substituée à l'autre. **La réciprocité (`share_p` et son dénominateur `partner_total_windowed`) n'existe que pour le périmètre effectivement tiré depuis OpenAlex** (l'union des tops internationaux, français et « réciprocité » les plus consultés, de l'ordre de 3 600 partenaires) : au-delà, la valeur s'affiche `—`, jamais 0, et ne doit jamais être lue comme une absence de collaboration (`docs/METHODES.md` § 9.7). Un partenaire technique sans identifiant institutionnel résolu (littéralement `'None'`) existe dans la méthode de momentum figée : il est classé mais n'est jamais un établissement réel, et n'apparaît jamais dans le tableau affiché (`ptn_mom_facts.parquet`, `phantom_ruling`). Le partenaire « Freiberg » recouvre en réalité deux identifiants OpenAlex distincts (l'université technique et l'institut Helmholtz associé) : le compte correct est l'union des travaux des deux identifiants, jamais leur somme, qui compterait deux fois un travail commun (`docs/METHODES.md` § 9.7). |

## Auteur·e

| Champ | Contenu |
|---|---|
| Définition | une personne physique créditée d'au moins une publication du corpus, après résolution d'identité (fusion des profils OpenAlex qui désignent la même personne). |
| Unités / valeurs | 12 680 personnes résolues à partir de 14 237 profils OpenAlex du corpus (`docs/METHODES.md` § 7). |
| Source | profils d'auteur·es OpenAlex du corpus, fusionnés par une chaîne de règles explicites (identité d'idHAL, nom et co-auteur·es partagés, nom et laboratoire partagés) ; un conflit d'ORCID bloque systématiquement la fusion, y compris quand les autres signaux concordent. |
| Langue d'affichage | français pour les libellés d'interface ; le nom d'affichage de la personne est celui que porte son profil OpenAlex. |
| Vues consommatrices | Annuaire des auteur·es (page 11) ; Profil auteur (page 12) ; Identifiants et couverture (page 13, jamais au grain individuel, voir Piège) ; Laboratoires (page 2, tops par laboratoire, 30 auteur·es par défaut). |
| Indicateurs | nombre de travaux (tous crédités, pas seulement ceux crédités d'une structure lorraine, voir Piège), part créditée d'une structure lorraine, identité thématique (champs et sous-champs dominants), présence ORCID et idHAL. Le contexte d'impact individuel (FWCI, PPtop) n'existe que dans un tiroir de consultation réservé aux personnes créditées d'au moins 30 travaux avec indicateur, sans export et sans tri (`docs/METHODES.md` § 9.3). |
| Objets liés | Laboratoire (affiliation principale, tops par laboratoire) ; Thématique (identité thématique en champs et sous-champs) ; Drapeaux ISITE (à travers les travaux crédités, jamais un drapeau porté par la personne elle-même). |
| Pièges | **Le nombre de travaux d'une personne (`n_works`) n'est pas le nombre de travaux où elle est créditée d'une structure lorraine (`ul_credited_works`)** : un clinicien co-auteur de 281 travaux du corpus peut n'être crédité d'une structure lorraine que sur un seul (`docs/METHODES.md` § 7). Confondre les deux colonnes a produit une lecture erronée dans la version précédente de l'outil (« auteur·es mal crédités »). **La réconciliation maison (fusion de profils par les règles ci-dessus) et un décompte ORCID-seul ne mesurent pas le même univers** : la première capture des personnes sans ORCID déclaré, le second s'arrête à ce que l'identifiant permet de relier directement. Les tables de tops par laboratoire arrivant cette passe portent les deux variantes derrière un même bouton (`BUILD_PLAN.md` #34), pour comparer sans les confondre. Aucune table auteur·e ne porte de colonne d'impact par construction (`aut_public`, `aut_works`) : un contrôle structurel interdit tout nom de colonne contenant `fwci`, `pptop`, `impact` ou `citation`, précisément pour qu'aucun tri par défaut ne puisse valoriser une personne plutôt qu'une autre (`docs/METHODES.md` § 9.3). La vue de couverture des identifiants (page 13) ne descend jamais à l'individu : ses grains sont le laboratoire, le champ, l'année ou la population entière. |

## Thématique (domaine / champ / sous-champ / topic)

| Champ | Contenu |
|---|---|
| Définition | les quatre niveaux hiérarchiques de la taxonomie native d'OpenAlex, du plus large (domaine) au plus fin (topic). Chaque publication porte un topic principal unique, qui détermine son sous-champ, son champ et son domaine principaux ; elle peut porter des topics secondaires supplémentaires. |
| Unités / valeurs | le dictionnaire complet, tel que pull par `pipeline/12b_pull_taxonomy.py` et déposé dans `all_topics.parquet`, compte 4 domaines, 26 champs, 252 sous-champs et 4 516 topics. Le sous-ensemble effectivement porté comme topic principal par le corpus lorrain est plus étroit (de l'ordre de 3 274 topics distincts, `docs/METHODES.md` § 9.5). `docs/METHODES.md` § 6 cite par ailleurs une autre échelle (5 domaines, 27 champs, 239 sous-domaines, 3 275 topics) : les trois échelles ne se recouvrent pas terme à terme et doivent toujours être citées avec leur source, jamais substituées l'une à l'autre sans vérification. |
| Source | pull complet de l'API OpenAlex `/topics`, refait à chaque instantané (jamais un fichier figé), garantissant que le dictionnaire est toujours un sur-ensemble strict des identifiants observés dans le corpus. |
| Langue d'affichage | anglais pour les noms de domaine, champ, sous-champ et topic : ce sont les libellés natifs d'OpenAlex, non traduits, y compris sur une interface par ailleurs en français. Les libellés d'interface qui les entourent (titres de graphique, infobulles) sont en français. |
| Vues consommatrices | Portefeuille thématique (page 4) ; Exploration thématique (page 6) ; Positionnement (page 5, position frontière) ; Laboratoires (page 2, nuage de mots par sous-champ, mini-fiche) ; Benchmark (page 14, comparaison de spécialisation). |
| Indicateurs | volume et part par niveau, indice de spécialisation (quotient de localisation contre la référence française), diversité disciplinaire (Rao-Stirling), co-discipline (matrice champ x champ), position frontière (centile de nouveauté du topic), FWCI_FR et PPtop10_FR par strate sous-champ x année x type. |
| Objets liés | ODD (un topic peut porter un signal ODD selon la route de classification active) ; Laboratoire (croisement frontière et ODD par laboratoire, passe 5) ; Pays (répartition thématique par pays, `geo_fields.parquet`) ; Établissement pair (comparaison de spécialisation et de diversité, passe 5). |
| Pièges | **811 topics de la taxonomie OpenAlex sont marqués « hors référentiel mondial »**, jamais « mauvais » : un classificateur entraîné sur un corpus majoritairement anglophone sous-résout des sujets souvent locaux ou nationaux (histoire de France, études urbaines francophones...), qui n'ont pas de baseline mondiale comparable. Ces travaux ne sont jamais retirés en silence : chaque ligne concernée porte un marqueur visible, et un bouton unique, désactivé par défaut, permet de les exclure d'un calcul (`docs/METHODES.md` § 9.1). La part de corpus concernée diffère selon le grain : au grain publication (topic principal marqué), l'empreinte est plus étroite qu'au grain topic (`ptn_topics`), qui compte aussi les topics secondaires ; les deux chiffres sont légitimement différents et ne doivent jamais être présentés côte à côte sans cette précision. Un modèle de topics propre à la version précédente de l'outil a été retiré (D9) : les vues thématiques actuelles reposent uniquement sur la taxonomie OpenAlex, qui se rafraîchit avec chaque collecte plutôt que de rester figée à une date d'entraînement. Le panneau « Financement par champ » reste construit dans le pipeline mais n'est plus restitué à l'écran depuis la passe 5 (`docs/METHODES.md` § 9.13) : la table existe, la vue non. |

## Objectif de développement durable (ODD)

| Champ | Contenu |
|---|---|
| Définition | un objectif de la liste des dix-sept Objectifs de développement durable des Nations Unies, attribué à une publication par un classificateur textuel. Trois méthodes de classification coexistent et sont livrées ensemble, le choix entre elles étant un arbitrage d'atelier, non une décision déjà tranchée. |
| Unités / valeurs | 16 ou 17 objectifs numérotés selon la route (la route SIRIS ne couvre pas l'ODD 17, la route Aurora l'étiquette). Une publication peut porter plusieurs ODD ; le nombre moyen d'ODD par travail tagué diffère nettement selon la route (`docs/METHODES.md` § 5). |
| Source | route A, méthode de la version précédente de l'outil, non reconstituable ; route B (« SIRIS »), vocabulaire contrôlé JRC appliqué en seize passes indépendantes avec traduction automatique préalable des textes français, active par défaut ; route C (« Aurora »), classificateur natif d'OpenAlex, seuil de confiance à 0,40. Le choix se fait par une ligne de configuration (`config.yaml: app.sdg_variant`), jamais par une reconstruction. |
| Langue d'affichage | français pour les libellés d'ODD affichés à l'écran ; les deux méthodes sont nommées explicitement dans l'interface (« SIRIS (VocTagger) » contre « Aurora (OpenAlex) »), jamais fondues en un seul chiffre. |
| Vues consommatrices | Portefeuille thématique (page 4, panneau ODD principal, et cette passe le profil ODD par laboratoire qui y était intégré) ; Laboratoires (page 2, profil ODD d'un laboratoire, déplacé cette passe depuis la page Portefeuille) ; Benchmark (page 14, comparaison de méthode Aurora avec les pairs). |
| Indicateurs | part du corpus taguée par route, nombre moyen d'ODD par travail tagué, part du corpus d'un laboratoire taguée par ODD (dénominateur : les seuls travaux tagués du laboratoire, jamais son effectif total), comparaison de méthode SIRIS contre Aurora au grain laboratoire (nouveau cette passe, `BUILD_PLAN.md` P11). |
| Objets liés | Thématique (l'ODD est un signal orthogonal à la taxonomie de champ, tous deux peuvent coexister sur un même travail) ; Laboratoire (profil ODD par laboratoire) ; Établissement pair (comparaison de méthode Aurora, passe 5, `bench_sdg.parquet`). |
| Pièges | **Aucune vérité terrain n'existe pour arbitrer entre les trois routes** : les chiffres de comparaison entre elles (accord, indice de Jaccard) mesurent un accord entre méthodes, jamais une exactitude. La route Aurora est structurellement mono-étiquette et sans seuil de couverture comparable aux deux autres : sa couverture bien supérieure est une conséquence de sa nature, jamais une mesure de sa qualité (`docs/METHODES.md` § 5). Le panneau ODD par laboratoire ne porte aucune décomposition ISITE cette passe : la croiser encore par ISITE ferait tomber presque toutes les cellules sous le plancher de fiabilité (`docs/METHODES.md` § 9.11). Le drapeau « hors référentiel » (811 topics) et l'ODD sont deux marqueurs indépendants : un travail peut porter l'un, l'autre, les deux ou aucun. |

## Type de document

| Champ | Contenu |
|---|---|
| Définition | la nature bibliographique d'une publication, telle que classée par OpenAlex, restreinte aux cinq types retenus dans le corpus. |
| Unités / valeurs | `article`, `book-chapter`, `review`, `book`, `conference-paper` (cinq valeurs de la colonne `ul_pubs.type`) ; un drapeau séparé, `is_conference`, isole les actes de conférence pour le bouton de bascule présent sur chaque page qui compte des travaux. |
| Source | champ `type` natif d'OpenAlex, filtré par le pipeline lors de la construction du corpus (règle de sélection, `docs/METHODES.md` § 2). |
| Langue d'affichage | les valeurs internes restent en anglais (identifiants OpenAlex) ; les libellés d'interface sont en français (« actes de conférence », « chapitres d'ouvrage »...). |
| Vues consommatrices | toutes les pages qui comptent des travaux portent le bouton de bascule actes de conférence (activé par défaut) : Vue d'ensemble, Laboratoires, Portefeuille thématique, Collaborations, notamment. Le détail par type (répartition annuelle) vit principalement sur Vue d'ensemble et Laboratoires. |
| Indicateurs | répartition annuelle par type, part de chaque type dans un laboratoire ou dans le corpus total, comparaison avec et sans actes de conférence sur tout indicateur de volume. |
| Objets liés | Structure interne et Laboratoire (répartition par type au grain structure) ; Drapeaux ISITE (le drapeau « hors référentiel » se lit différemment selon le type, voir Thématique) ; Période (répartition annuelle par type). |
| Pièges | **Les préprints sont exclus intégralement du corpus** (D10), pour un motif de dédoublonnage : un préprint et sa version publiée sont deux enregistrements distincts dans OpenAlex. Sont également écartés les mémoires et thèses, résumés de conférence, rapports, jeux de données, éditoriaux, errata et évaluations par les pairs, par le seul jeu de la liste de types retenus, jamais par un filtre de qualité additionnel. **Les actes de conférence sont dans le corpus**, avec une médiane de citations proche de zéro et une très large majorité jamais citée : les comparer sans stratifier par type gonfle artificiellement l'écart entre un laboratoire riche en actes et un laboratoire qui n'en produit pas (`docs/METHODES.md` § 2). Le DOI n'est pas une condition d'entrée dans le corpus (D37, 30,8% des travaux sans DOI) : un DOI n'est exigé que là où une opération est elle-même indexée par DOI (le drapeau ISITE canonique, le complément de résumés). |

## Drapeaux ISITE

| Champ | Contenu |
|---|---|
| Définition | l'appartenance d'un travail au périmètre de la subvention I-SITE / LUE (`G3172997804`, ANR-15-IDEX-0004). Trois définitions coexistent, imbriquées, et ne se substituent jamais l'une à l'autre. |
| Unités / valeurs | trois ensembles emboîtés, tous mesurés sur le même instantané. **CANON** : la liste de DOI validée à la main par l'université, la seule référence canonique de l'application (`works_master.In_ISITE`). **EXACT** : les travaux dont l'identifiant de subvention OpenAlex correspond strictement à la subvention I-SITE (`works_master.In_ISITE_openalex_award`) ; EXACT est un sous-ensemble strict de BROAD. **BROAD** : la famille élargie de traçage, qui retient un travail dès que son code ou son intitulé de financement mentionne la subvention, même sans identifiant opaque de subvention (`dim_subsets`, ligne `in_isite_award`). |
| Source | CANON provient d'un fichier manuel (liste de DOI fournie par l'université) ; EXACT et BROAD proviennent tous deux d'un rapprochement automatique sur les données de financement OpenAlex (`corpus_funding.parquet`), à deux niveaux de tolérance différents. |
| Langue d'affichage | français pour les libellés d'interface ; l'identifiant de la subvention elle-même (`G3172997804`, « Isite LUE ») reste tel qu'OpenAlex le porte, jamais traduit ni renommé, car c'est une correspondance textuelle contre des métadonnées externes. |
| Vues consommatrices | I-SITE (page 7, panneau de recoupement subvention) ; Vue d'ensemble et Laboratoires (surcharge visuelle sur les graphiques qui portent une décomposition ISITE) ; Collaborations et Zoom partenaire (part ISITE des co-publications par partenaire). |
| Indicateurs | part ISITE d'un volume donné (structure, partenaire, pays), et le recoupement subvention lui-même (BROAD comparé à CANON) sur la page I-SITE. |
| Objets liés | Structure interne (les sept membres externes du consortium ISITE, CNRS/Inserm/INRAE/CHRU Nancy/Georgia Tech/Inria/AgroParisTech, portent des poids de gouvernance distincts, `consortium_weights.parquet`) ; Partenaire (part ISITE des co-publications par partenaire) ; Période (le décalage de la liste canonique sur la dernière année de l'instantané, voir Piège et `docs/YEAR_UPDATE_DESIGN.md`). |
| Pièges | **BROAD moins CANON désigne des candidats à un enrichissement de la liste canonique, jamais des travaux déjà ISITE** : la liste de DOI validée par l'université reste la seule référence, ce recoupement n'y est jamais fusionné automatiquement (`reports/isite_award_reconciliation.md`, § 4). Deux nombres apparemment contradictoires ailleurs dans l'outil (le total BROAD et sa variante hors actes de conférence) sont la même famille de travaux lue sur deux axes indépendants, l'appartenance canonique d'un côté, le type de document de l'autre : les présenter côte à côte sans cette précision recrée la confusion déjà réparée cette passe (`reports/isite_award_reconciliation.md`, § 3). **Le bouton ISITE n'assombrit qu'une part d'une barre déjà affichée, il ne retire jamais de ligne** : à la différence du bouton « hors référentiel » (voir Thématique), il n'existe que là où une décomposition a été construite, et environ la moitié des graphiques de l'outil n'en portent aucune à ce jour ; le contrat complet page par page vit dans `docs/OVERLAY_MATRIX.md`, jamais résumé de façon optimiste ailleurs (`docs/METHODES.md` § 9.12). La liste canonique ne couvre, par construction, que les travaux dont le DOI était connu au moment de sa validation : son décalage sur une année récemment ajoutée à l'instantané est un chantier documenté dans `docs/YEAR_UPDATE_DESIGN.md`, pas un défaut de cette passe. |

## Période

| Champ | Contenu |
|---|---|
| Définition | la dimension temporelle de l'instantané : l'année de publication d'un travail, et les fenêtres de comparaison construites dessus (momentum, tendance annuelle). |
| Unités / valeurs | fenêtre de collecte 2019-2023 (cinq années civiles, `config.yaml: window.year_from/year_to`, D1 : « une nouvelle fenêtre est une collecte séparée »). La méthode de momentum figée compare deux fenêtres non adjacentes, 2019-2020 contre 2022-2023, l'année 2021 servant de tampon et n'entrant dans aucune des deux (`pipeline/lib46_momentum.py`, constantes `W1_YEARS`/`W2_YEARS`). |
| Source | `publication_year` d'OpenAlex pour l'année d'une publication ; les bornes de fenêtre et les paramètres de momentum (bande de significativité, seuil p) sont des constantes de `config.yaml`, jamais codées en dur dans une vue. |
| Langue d'affichage | valeurs numériques, sans traduction ; les libellés qui les entourent (« en hausse », « non significatif ») sont en français. |
| Vues consommatrices | toute page qui affiche une répartition annuelle (Vue d'ensemble, Laboratoires, Portefeuille thématique) ; Collaborations et Zoom partenaire pour le momentum par partenaire ; Géographie pour la tendance par pays. |
| Indicateurs | répartition annuelle par type de document ou par domaine, momentum (classes en hausse / en retrait / stable / non significatif, avec p-valeur), tendance par pays. |
| Objets liés | Type de document (répartition annuelle par type) ; Partenaire (momentum par partenaire) ; Pays (tendance par pays) ; Drapeaux ISITE (le momentum n'est jamais recalculé sous le filtre « hors référentiel », voir Thématique). |
| Pièges | **Le momentum n'est jamais recalculé sous le filtre « hors référentiel »** : il reste affiché grisé avec sa légende, plutôt que de produire quatre variantes de la même mesure sans référence stabilisée pour aucune d'elles (`docs/METHODES.md` § 9.1). Un pseudo-partenaire technique (identifiant institutionnel non résolu) est classé par la méthode figée mais n'est jamais un établissement réel : le compte affiché à l'écran exclut toujours cette ligne (`ptn_mom_facts.parquet`, voir « Partenaire »). L'intégration d'une année supplémentaire (2024 puis 2025) soulève une question de fenêtre glissante non tranchée à ce jour (2019 disparaît-il quand 2025 arrive ? l'harmonie 3 ans / 3 ans est-elle préservée ?) : la question est posée et instruite dans `docs/YEAR_UPDATE_DESIGN.md`, pas résolue par ce registre. |

## Établissement pair (Benchmark)

Objet ajouté à la liste du porteur du projet, pour que la correspondance mécanique de ce registre
couvre les quatre tables de comparaison entre pairs déployées par l'application ; sans lui, ces
quatre tables resteraient orphelines de tout objet nommé.

| Champ | Contenu |
|---|---|
| Définition | l'un des neuf établissements retenus par l'atelier comme point de comparaison de l'Université de Lorraine (trois I-SITE de parité, un IDEX d'aspiration, un transfrontalier, quatre miroirs européens), ou l'Université de Lorraine elle-même dans son rôle de dixième ligne comparable. |
| Unités / valeurs | dix entités par table (l'Université de Lorraine plus neuf pairs), listées et modifiables par une seule case à cocher dans `inputs/overlays/bench_peers.csv`, sans toucher au code (`docs/METHODES.md` § 9.8). |
| Source | tirage OpenAlex direct par établissement (identifiant institutionnel direct, pas la filiation), réalisé le 17 août 2026 pour les neuf pairs et recalculé localement pour l'Université de Lorraine sur le même identifiant direct. |
| Langue d'affichage | français pour les libellés d'interface ; les noms d'établissements pairs restent ceux fournis par le registre de sélection. |
| Vues consommatrices | Benchmark (page 14, volume et citation) ; Positionnement (page 5, ODD, position frontière et diversité disciplinaire des pairs, passe 5). |
| Indicateurs | quotient de localisation par champ et sous-champ contre la référence française, FWCI_FR et PPtop10_FR par pair sur la même mécanique que côté lorrain, comparaison ODD par la méthode Aurora, position frontière, diversité disciplinaire (Rao-Stirling). |
| Objets liés | Structure interne (la ligne Université de Lorraine de ces tables) ; Thématique (comparaison de spécialisation et de diversité) ; ODD (comparaison de méthode Aurora) ; Pays (chaque pair a un pays d'origine). |
| Pièges | **La ligne Université de Lorraine de ces quatre tables n'est ni le corpus canonique (36 819 travaux) ni aucun des trois autres périmètres lorrains cités ailleurs dans l'outil** : c'est un quatrième périmètre, volontairement plus étroit, l'identifiant direct de l'établissement sur la même fenêtre et les mêmes cinq types que chaque pair. C'est la seule des perspectives qui traite l'Université exactement comme chaque pair (`docs/METHODES.md` § 9.8 et § 9.10) : toujours nommer ce périmètre explicitement plutôt que de le confondre avec le corpus canonique affiché ailleurs. **L'écart entre comptage direct et comptage par filiation touche fortement les établissements français, pas les étrangers** (facteur ×1,29 à ×2,18 pour les pairs français retenus, contre ×1,00 à ×1,08 pour les pairs étrangers) : toute comparaison de taille entre un pair français et un pair étranger porte une marge d'erreur asymétrique, jamais un critère de taille utilisé seul pour départager deux établissements. Le FWCI_FR appliqué aux pairs étrangers reste un étalon français commun, jamais une norme mondiale : un pair qui affiche un FWCI_FR inférieur à 1 n'est pas « moins cité dans l'absolu », il est moins cité au regard d'un référentiel qui n'est pas le sien. Ces tables sont exemptées par construction du bouton « hors référentiel » : les corpus pairs sont tirés en direct d'OpenAlex, hors de l'instantané local qui porte la liste des 811 topics exclus. |

---

## Tenue à jour de ce registre

Ce registre se met à jour à trois occasions : l'ajout d'une table dans `docs/data_contract.yaml`
(le bloc `yaml` ci-dessous doit alors gagner une entrée), l'ajout d'un objet nouveau qu'aucune des
onze fiches ci-dessus ne couvre, ou un changement de règle sur un objet existant (nouvelle langue
d'affichage, nouvelle vue consommatrice, piège nouvellement identifié). Dans les trois cas,
`python docs/registre_check.py` doit repasser au vert avant de considérer la mise à jour terminée.

**Toute nouvelle table déployée exige sa correspondance dans ce registre au sein de la MÊME passe
qui la construit** (`docs/registre_check.py` vert avant la clôture, jamais un rattrapage différé à
la passe suivante) : la passe 6 a laissé 8 tables construites après la clôture de ce document
(`lab_top_authors`, `lab_top_partners`, `lab_wordcloud`, `lab_works`, `ptn_denominators`,
`sdg_lab_methods`, `subfields_zero_fill`, `topics_zero_fill`) sans objet, une classe de
dérive que ce correctif ferme (`docs/INSPECTION_REPORT_pass6.md` D1, `docs/LENS_ABSORPTION_pass6.md`).

## Annexe technique : correspondance table -> objet

Bloc lu mécaniquement par `docs/registre_check.py`. Chaque objet porte la liste des tables
déployées (`docs/data_contract.yaml`) qui le documentent ; un objet sans table dédiée porterait
`derived: true` à la place (aucun cas cette passe : les onze objets ci-dessus portent chacun au
moins une table).

```yaml
objects:
  pays:
    tables: [geo_countries.parquet, geo_fields.parquet, geo_groups.parquet]
  laboratoire:
    tables: [ul_labs.parquet, thematic_detail_contributions.parquet, ptn_labs.parquet,
             thm_frontier_labs.parquet, thm_sdg_labs.parquet, lab_top_authors.parquet,
             lab_top_partners.parquet, lab_works.parquet]
  structure_interne:
    tables: [ul_labs.parquet, ul_pubs.parquet]
  partenaire:
    tables: [ul_partners.parquet, ul_partners_base.parquet, thematic_detail_partners.parquet,
             ptn_summary.parquet, ptn_mom_facts.parquet, ptn_yearly.parquet, ptn_fields.parquet,
             ptn_labs.parquet, ptn_works.parquet, ptn_topics.parquet, consortium_weights.parquet,
             geo_groups.parquet, ptn_denominators.parquet]
  auteur:
    tables: [ul_authors.parquet, thematic_detail_authors.parquet, aut_public.parquet,
             aut_works.parquet, aut_impact_drill.parquet, aut_coverage.parquet]
  theme:
    tables: [all_topics.parquet, thematic_overview.parquet, treemap_hierarchy.parquet,
             thematic_detail_sublevels.parquet, thematic_detail_contributions.parquet,
             thematic_detail_partners.parquet, thematic_detail_authors.parquet, ul_pubs.parquet,
             ptn_fields.parquet, ptn_topics.parquet, geo_fields.parquet, thm_specialisation.parquet,
             thm_diversity.parquet, thm_codiscipline.parquet, thm_funding.parquet,
             thm_frontier.parquet, thm_frontier_topics.parquet, thm_frontier_labs.parquet,
             dim_artifact_topics.parquet, bench_positioning.parquet, bench_diversity.parquet,
             lab_wordcloud.parquet, subfields_zero_fill.parquet, topics_zero_fill.parquet]
  odd:
    tables: [sdg_siris.parquet, sdg_three_way.parquet, thm_sdg_labs.parquet, bench_sdg.parquet,
             sdg_lab_methods.parquet]
  type_document:
    tables: [ul_pubs.parquet, ul_lookup.parquet, dim_corpus_facts.parquet]
  drapeaux_isite:
    tables: [ul_pubs.parquet, dim_subsets.parquet, work_subsets.parquet, subset_works.parquet,
             ptn_summary.parquet, consortium_weights.parquet, thm_specialisation.parquet]
  periode:
    tables: [ul_pubs.parquet, ul_lookup.parquet, dim_corpus_facts.parquet, ptn_summary.parquet,
             ptn_mom_facts.parquet, ptn_yearly.parquet]
  etablissement_pair:
    tables: [bench_peers.parquet, bench_sdg.parquet, bench_positioning.parquet,
             bench_diversity.parquet]
```
