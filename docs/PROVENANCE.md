# Provenance des données

Toute donnée servie par l'application vient de l'une de cinq origines : OpenAlex, HAL, OpenAIRE, un
vocabulaire contrôlé, et deux fichiers maintenus à la main par le client. Ce document indique, pour
chacune, ce qui est collecté, ce qui est archivé, et ce qui peut être reconstruit à l'identique.

---

## 1. OpenAlex, source principale

OpenAlex fournit le périmètre, les métadonnées de publication, les affiliations, les citations, la
taxonomie thématique et les métadonnées de financement.

**L'accès exige une clé.** Depuis février 2026, l'API demande une clé, transmise en en-tête
`Bearer`, accompagnée d'une adresse de contact en paramètre de requête. Sans clé, le pool public se
comporte comme un blocage silencieux plutôt que comme une erreur explicite, ce qui est un piège de
diagnostic. Les identifiants sont lus dans `~/.siris/.env` et n'apparaissent nulle part dans le
dépôt.

**Trois collectes distinctes** composent un instantané. La collecte lorraine ramène 46 404
publications sur la fenêtre 2019-2023, par filtre de filiation institutionnelle, en 713 appels. La
collecte française ramène la base de référence citationnelle, 1 100 570 publications, découpée par
année. La collecte de taxonomie ramène le dictionnaire complet des topics, environ 23 appels, qui
sert de décodeur à toutes les colonnes thématiques. Une quatrième collecte, ciblée, complète le
volume de publication propre à chaque partenaire.

**Chaque collecte enregistre ce qu'elle a demandé.** Le fichier `MANIFEST.json` de l'instantané
consigne, pour chaque étape : la chaîne de filtre exacte envoyée à l'API, année par année, la liste
des champs demandés, l'URL de base, le nombre d'appels effectués, les décomptes obtenus, les
paramètres de configuration en vigueur, les versions des outils utilisés (Python, pandas, pyarrow,
requests) et l'horodatage UTC de fin. S'y ajoute, pour chaque fichier produit, sa taille, son nombre
de lignes et son **empreinte sha256**.

**La reproductibilité a été vérifiée, pas supposée.** Deux collectes complètes indépendantes,
espacées de 24 heures, ont produit un fichier `works.parquet` **identique à l'octet près** :
empreinte `9d51e2c684aede5e…`, 46 404 lignes dans les deux cas, aucune publication ajoutée ni
retirée, aucun changement sur les citations, la longueur des résumés, le nombre d'institutions, le
type ou l'indicateur natif. Cela ne signifie pas qu'OpenAlex est figé, seulement que l'index
interrogé par cette requête n'a pas bougé sur cette fenêtre, et que le pipeline n'introduit aucun
bruit propre.

**Une conséquence à porter dans toute lecture.** OpenAlex est une base vivante. « Rejouer à
l'identique » signifie *même code, même archive brute*, et non *mêmes comptages en direct*. C'est la
raison pour laquelle chaque instantané est daté et manifesté, et pour laquelle comparer deux
instantanés est une étape explicite plutôt qu'une hypothèse.

## 2. HAL

HAL est interrogé pour deux raisons : compléter les résumés absents d'OpenAlex, et atteindre les
publications sans DOI, qu'aucune requête indexée par DOI ne peut toucher.

La moisson porte sur l'identifiant de structure 413289 ou la collection `UNIV-LORRAINE`, sur la
fenêtre 2019-2023, par parcours à curseur. Elle ramène **42 933 enregistrements**, dont 27 557
portent un résumé et 19 597 seulement un DOI, ce qui montre à lui seul pourquoi la moisson par
structure était nécessaire. **16 170 publications du corpus** sont reliées à un enregistrement HAL.

HAL fournit aussi les identifiants idHAL des auteurs, exploitables parce que HAL publie des paires
nom-idHAL alignées : 13 546 publications ont au moins un auteur ainsi identifiable. Les ORCID que
HAL publie ne sont **pas** utilisés, faute d'un champ aligné qui permette de les attribuer à la
bonne personne.

## 3. OpenAIRE

OpenAIRE est interrogé en dernier recours, par DOI, sur les seules publications dont ni OpenAlex ni
HAL n'ont fourni de résumé. Il en apporte **2 212**.

## 4. Origine du résumé stocké

Chaque ligne du corpus porte la source de son résumé, sa longueur et sa langue. Aucun texte n'est
importé sans que son origine soit inscrite.

| Source | Publications |
|---|---|
| OpenAlex, reconstruit depuis l'index inversé | 27 228 |
| HAL, par DOI | 4 336 |
| OpenAIRE, par DOI | 2 212 |
| HAL, par appariement de titre | 221 |
| **Couverture totale** | **92,3%** du corpus |

La règle de conservation est simple et déclarée : à texte concurrent, on garde le plus long, et un
résumé déjà présent n'est jamais raccourci.

## 5. Le vocabulaire ODD

Le tagage ODD repose sur le vocabulaire contrôlé JRC, appliqué en 16 passes indépendantes. Le
fichier de vocabulaire est **copié dans l'instantané à chaque lancement**, sous `raw/vocab`, avant
tout traitement. La reproductibilité du tagage en dépend directement : un vocabulaire mis à jour en
amont produirait d'autres résultats, et sans cette copie rien ne permettrait de savoir lequel a
servi.

## 6. Les deux entrées manuelles

Ce sont les seules données que le pipeline ne sait pas reconstruire. Elles appartiennent au client et
elles vivent dans `inputs/manual/`.

**`Identifiants_UnivLorraine.xlsx`**, la liste de référence des structures : 70 lignes, 68
identifiants OpenAlex. Le fichier est conservé à l'octet près, tel que le client l'a fourni. Un
identifiant y est mort côté OpenAlex ; sa réparation est déclarée dans
`config.yaml: perimeter.openalex_id_repairs`, avec la mention de la voie de résolution, plutôt
qu'appliquée en silence dans le fichier. La structure concernée porte 0 publication sur toute la
profondeur d'OpenAlex, ce qui est un fait sur son activité de publication et non une erreur de
pipeline ; elle est déclarée comme telle en configuration, tandis qu'une structure vide **non
déclarée** ferait échouer l'audit.

**`all_doi_isite.xlsx`**, la liste des DOI I-SITE : 3 843 lignes, 3 776 DOI uniques après
normalisation. Elle est gelée et fait foi. Le code de financement I-SITE d'OpenAlex, qui couvre
indépendamment 749 publications du corpus, est stocké dans une colonne séparée à titre de
recoupement et n'est jamais fusionné : les 9 publications qu'il ajouterait sont signalées au client,
pas incorporées.

## 7. Ce qui est reconstructible, ce qui est gelé

| Élément | Statut | Conséquence |
|---|---|---|
| Tables de l'instantané | reconstructibles depuis les archives brutes | une modification de l'étape de lecture se rejoue sans nouvelle collecte |
| Charges brutes OpenAlex | archivées, compressées | conservées sur les 3 derniers instantanés |
| Fichiers déployés dans `Streamlit/data/` | reconstructibles par `60_deploy.py` | versionnés dans le dépôt, parce que l'hébergement ne sait pas exécuter le pipeline |
| Caches de résumés et de traductions | reconstructibles, coûteux | environ 70 minutes de traduction à réacquérir, appels HAL et OpenAIRE gratuits |
| Les deux entrées manuelles | **gelées, propriété du client** | les modifier change le périmètre |
| Vocabulaire ODD | copié dans chaque instantané | le tagage est rejouable même si le vocabulaire amont évolue |
| Données de la version 1 | **gelées, en lecture seule** | jamais recalculées, elles servent de référence de comparaison |

## 8. Archivage et rétention

Les instantanés vivent hors du dépôt et hors de toute synchronisation, sous
`C:/siris-data/lorraine-explorer/snapshots/<identifiant>/`, chemin configurable. Le motif est
matériel autant que méthodologique : une collecte brute pèse plusieurs centaines de mégaoctets et
n'a rien à faire dans un dépôt Git ni dans un dossier synchronisé.

Chaque instantané contient `raw/` (les charges brutes), `tables/` (les tables construites),
`MANIFEST.json` et `SUMMARY.md`, ce dernier récapitulant les décomptes de chaque étape en clair.

**Les charges brutes sont conservées, compressées.** Le format est `jsonl` compressé en zstd niveau
10 : 569 Mo deviennent 53,4 Mo sur l'instantané de référence, soit un facteur 10,7. L'empreinte
sha256 inscrite au manifeste porte sur les octets **non compressés**, de sorte qu'elle reste
comparable d'un lancement à l'autre indépendamment du réglage de compression.

Ce choix a un motif précis. Sans archive brute, « même code, même instantané, même résultat » ne
vaut que pour les étapes en aval de la lecture : toute modification de la lecture elle-même exige
alors une nouvelle collecte. Le diagnostic de la troncature des auteurs, en août 2026, a coûté une
recollecte complète pour cette raison exacte. L'instantané `2026-08-11` est le premier à disposer de
ses charges brutes ; le précédent, `2026-08-10`, n'en a pas et n'est conservé que comme second terme
de comparaison.

**La rétention porte sur le volume, pas sur la trace.** Au-delà des trois instantanés les plus
récents, seul le répertoire `raw/` est purgé. `MANIFEST.json`, `SUMMARY.md` et `tables/` sont
conservés indéfiniment, pour tous les instantanés jamais produits. On peut donc toujours établir ce
qui a été collecté, quand, avec quel filtre et pour quel résultat, même lorsque les charges brutes
ont été effacées.

## 9. Ce que la provenance ne couvre pas

Un point reste hors de portée de tout dispositif de traçabilité, et il est le plus important à
retenir : **le rattachement d'une publication à une institution est une décision d'OpenAlex, révisée
en continu**. Le moteur d'appariement d'affiliations retraite l'historique des années après
l'indexation initiale, ajoutant et parfois retirant des rattachements sur des articles anciens.
Deux collectes séparées de plusieurs mois rendront donc des périmètres différents, sans qu'aucune
erreur ne soit commise ni d'un côté ni de l'autre. C'est ce qui rend indispensables la datation des
instantanés et la comparaison explicite entre deux d'entre eux, et c'est la première explication à
examiner devant tout écart inattendu.
