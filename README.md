# Lorraine Explorer v2

Ce dépôt reconstruit, à partir d'OpenAlex, l'intégralité des jeux de données qui alimentent le
**Lorraine Explorer**, l'outil d'exploration bibliométrique de l'Université de Lorraine sur la
fenêtre 2019-2023. Il contient le pipeline, l'application Streamlit et le contrat de données. Tout se pilote depuis un seul fichier, `config.yaml`.

Application en ligne : <https://lorraine-handoff.streamlit.app/>. **L'interface de l'application est désormais entièrement en français** (D61 REVERSÉE passe 5,
2026-08-18 : le wrapper FR complet remplace la parité anglaise historique avec la version 1,
que l'atelier comparait côte à côte). La documentation l'est également.

Ce fichier est le mode d'emploi de l'opérateur. La méthode est décrite dans
[`docs/METHODES.md`](docs/METHODES.md), les écarts avec la version 1 dans
[`docs/SHIFT_v1_v2.md`](docs/SHIFT_v1_v2.md), les contrôles automatiques dans
[`docs/AUDIT.md`](docs/AUDIT.md), la traçabilité des sources dans
[`docs/PROVENANCE.md`](docs/PROVENANCE.md), les options d'accès à l'application dans
[`docs/ACCES_STREAMLIT.md`](docs/ACCES_STREAMLIT.md).

**Chaîne pass 3 (2026-08-15, partenaires/thématique/auteurs) :** l'état de la chaîne est dans la
section « Chain pass 3 » en fin de [`docs/BUILD_STATE.md`](docs/BUILD_STATE.md) ; la spécification
canonique de la fondation de données, rev 3.1, est dans
[`docs/foundry/DATA_FOUNDATION.md`](docs/foundry/DATA_FOUNDATION.md) et son pendant machine
`docs/foundry/data_foundation.yaml` ; le contrat de données, désormais **47 fichiers**, est décrit
dans [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md) §8 et `docs/data_contract.yaml`.

**Pass 4 (2026-08-17, benchmark de pairs T4b) puis correctifs Codex (pass 4b, 2026-08-18) :** le
benchmark ajoute `bench_peers.parquet` et une page Benchmark (numérotée `12_...` à l'époque ;
renumérotée `14_🧭_Benchmark.py` passe 5) (voir §9.8
[`docs/METHODES.md`](docs/METHODES.md)) ; le pass 4b corrige les six écarts confirmés par la revue
externe Codex (persistance des contrôles entre pages, exports partenaire/auteur non filtrés,
réciprocité 42b affichée, palette de domaine unique, bootstrap `45b`, contrats de données stales) --
détail dans `progress/CXFIX_codex_fixes.md`.

**Passe 5 (2026-08-18, refonte overlay I-SITE + benchmark) puis correctifs FIX-1 (même
jour) :** le filtre I-SITE global est retiré -- I-SITE devient une **surcouche
d'affichage** partout (teinte plus sombre sur les graphiques qui portent une décomposition,
jamais un retrait de travaux), pilotée par la 3e bascule de la barre latérale ; l'ancien
nom interne « LUE » disparait au profit de « I-SITE » (renommage mécanique,
aucune valeur changée -- voir [`docs/METHODES.md`](docs/METHODES.md) §9.9 et suivants).
Le Benchmark (T4b) passe à une synthèse par groupe de comparaison, 6 signaux, sans
classement (§9.8). La ronde de correctifs FIX-1 ferme le blocage de vacuité de test
(F-VAC-01 -- la preuve de persistance du bandeau vit désormais dans `tests/ui/smoke.py`,
pas dans l'AppTest), ré-vérifie un faux positif de landmine pipeline (F-C01B) et
centralise la garde `sys.modules['lib']` (`tests/conftest.py`).

---

## 1. Prérequis

**Python 3.11** (version de référence : 3.11.7), avec `pandas`, `pyarrow`, `requests`, `pyyaml`,
`zstandard`, `openpyxl`, `pytest`. L'application ajoute les paquets listés dans
`Streamlit/requirements.txt`.

**Les identifiants d'API** ne sont jamais écrits dans le dépôt. Ils sont lus dans un fichier local,
`~/.siris/.env`, désigné par `config.yaml: secrets.env_file`. Trois clés sont déclarées
obligatoires :

| Clé | Usage |
|---|---|
| `OPENALEX_API_KEY` | clé financée OpenAlex, envoyée en en-tête `Bearer`. Sans elle, le pool sans clé se comporte comme un blocage silencieux (`Retry-After`), jamais comme une erreur. |
| `OPENALEX_MAILTO` | adresse de contact, envoyée en paramètre de requête |
| `OPENAIRE_TOKEN` | jeton OpenAIRE pour le complément de résumés (l'étape `20` lit également `OPENAIRE_REFRESH_TOKEN` si présent) |

**Trois interpréteurs Python, par construction.** Aucun environnement unique ne fait tourner
l'ensemble de la chaîne : la traduction FR→EN exige un `torch` fonctionnel, le tagueur ODD exige
spaCy et VocTagger. Les chemins sont dans `config.yaml: interpreters` et `run_all.py` lance chaque
étape avec celui qui lui revient, sans intervention. Pour vérifier leur résolution :

```bash
python run_all.py --list
```

La dernière section de la sortie affiche les trois chemins résolus. Si l'un d'eux n'existe pas sur
la machine, c'est le premier point à corriger avant tout lancement.

## 2. Contrôle de santé

Quatre commandes (les « quatre portes »), à passer avant et après toute manipulation. Elles ne modifient aucune donnée.

```bash
python -m pytest tests/ -q
python docs/contract_coverage_check.py
python lib/artifact.py --check docs/foundry/data_foundation.yaml
python pipeline/80_audit.py
```

La première exécute les invariants structurels et les tests du contrat de données : **413 tests
passés + 1 ignoré** (skip documenté) sur l'instantané de référence. La deuxième vérifie que chaque
colonne v1 est reprise, renommée ou explicitement abandonnée avec une raison. La troisième vérifie
la complétude de l'exemption « hors référentiel » (artifact_exempt) table par table, colonne par
colonne (0 violation attendu). La quatrième rejoue l'audit de déploiement, écrit
`reports/audit_run.md` et sort en code 0 si, et seulement si, la classe 1 est intégralement verte
et aucune famille de la classe 2 n'est en `INVESTIGATE` non expliqué. Sortie attendue :

```
Class 1: 13/13 passed
Class 2: 8 families evaluated, 0 unexplained INVESTIGATE
```

Le détail de ce que ces contrôles vérifient est dans [`docs/AUDIT.md`](docs/AUDIT.md).

**Cinquième contrôle, optionnel mais recommandé avant toute publication :** `python tests/ui/smoke.py` lance un vrai navigateur (Playwright) contre un vrai serveur Streamlit local et rejoue les cas limites (grand/petit/vide/hors-liste, ODD selon `app.sdg_variant`, et depuis la ronde FIX-1 la traversée de persistance des 3 bascules de la barre latérale par clic réel sur le menu, jamais `page.goto()`) -- **37 contrôles**, captures dans `reports/evals/smoke/`.

## 3. Rafraîchir les données

Une seule commande enchaîne les **36 étapes** (l'ordre a grossi passe après passe : partenaires/thématique/auteurs à la chaîne pass 3, benchmark de pairs au pass 4, et quatre scripts propres à la passe 5 -- `47c_build_frontier_topics.py`, `49w_pull_peers_wide.py`, `49c_build_peer_context.py`, `47b_build_crossings.py` ; `python run_all.py --list` détaille l'ordre
exact, y compris deux corrections de dépendance non triviales — voir `docs/BUILD_STATE.md`), de la
collecte OpenAlex au déploiement, dans l'ordre de dépendance réel :

```bash
python run_all.py --snapshot 2026-08-12
```

L'argument `--snapshot` est un identifiant d'instantané, par convention la date du jour au format
`AAAA-MM-JJ`. Il nomme le répertoire créé sous la racine des instantanés, il ne modifie pas
`config.yaml`. Comptez environ quatre heures de machine, dont environ 98 minutes pour la seule étape
ODD répartie sur 4 processus, et de l'ordre de 0,75 $ d'API OpenAlex, dominés par la base de
référence française.

Chaque étape écrit sa sortie complète dans `reports/_runall_<étape>.log`. Au premier échec, le
lancement s'arrête, affiche les étapes déjà réussies et imprime la commande exacte de reprise.

**Reprendre sans tout refaire.** `--resume` saute toute étape dont la sortie existe déjà ; les
étapes longues (collecte Lorraine, collecte France, tagage ODD) reprennent en plus sur leur propre
curseur, sans redépenser d'appels API :

```bash
python run_all.py --snapshot 2026-08-12 --resume
```

**Rejouer une tranche.** Les identifiants d'étape sont ceux affichés par `--list` :

```bash
python run_all.py --snapshot 2026-08-12 --from-step 41 --to-step 60 --resume
```

**Sonde de périmètre, facultative.** `python pipeline/05_perimeter_probe.py` recompte le périmètre
côté OpenAlex et écrit `reports/g1_perimeter_probe.{md,json}`. Elle consomme de l'API (environ 475
appels, 0,05 $) et n'écrit aucune table : c'est un diagnostic, pas une étape de production. Elle est
exclue de la plage par défaut.

## 4. Voir ce qui a bougé

Avant de décider de garder un instantané, comparez-le au précédent :

```bash
python pipeline/90_snapshot_diff.py 2026-08-11 2026-08-12
```

Le script écrit `reports/snapshot_diff_<ancien>_vs_<nouveau>.md` et rend un verdict par famille de
dérive (taille du corpus, publications par structure, couverture des résumés, couverture ODD,
médiane du FWCI_FR, PPtop10 par année, nombre de partenaires, publications I-SITE). Les seuils sont
lus dans `config.yaml: audit.drift_bands` : les modifier ne demande aucune modification de code. Une
table absente d'un des deux instantanés est signalée `missing table`, jamais une erreur fatale.

Pour vérifier la logique de bandes sans lire aucun instantané :

```bash
python pipeline/90_snapshot_diff.py --selftest
```

## 5. Garder, ou revenir en arrière

Le mécanisme est le même dans les deux sens, et il tient en une ligne de configuration.
`config.yaml: project.snapshot_id` désigne l'instantané actif ; `60_deploy.py` recopie ses tables,
validées contre le contrat, dans `Streamlit/data/` ; Streamlit Community Cloud sert ce qui est dans
le dépôt.

**Garder le nouvel instantané.**

1. Ouvrir `config.yaml` et remplacer la valeur de `project.snapshot_id` par le nouvel identifiant :
   ```yaml
   project:
     snapshot_id: "2026-08-12"
   ```
2. Déployer, puis auditer le résultat déployé :
   ```bash
   python pipeline/60_deploy.py
   python pipeline/80_audit.py
   ```
3. Publier. Le répertoire `Streamlit/data/` est versionné à dessein : l'hébergement déploie depuis
   le dépôt et ne sait pas exécuter le pipeline.
   ```bash
   git add config.yaml Streamlit/data
   git commit -m "Deploy snapshot 2026-08-12"
   git push
   ```

Le redéploiement est automatique après le `push`, en quelques minutes.

**Revenir en arrière.** Exactement la même séquence, en pointant `project.snapshot_id` sur
l'identifiant précédent, par exemple `"2026-08-11"`. Aucune reconstruction n'est nécessaire :
l'instantané visé est déjà sur le disque, complet et manifesté. Un retour arrière coûte une ligne
éditée, un `60_deploy`, un commit.

> `60_deploy.py` échoue en code non nul dès qu'une colonne attendue par le contrat manque, qu'un
> type ne correspond pas ou qu'une clé se duplique. C'est délibéré : la version 1 avait perdu
> silencieusement la colonne `Is_abstract` au déploiement, ce qui avait cassé une vue en aval sans
> qu'aucun signal ne soit émis.

## 6. Où vivent les données

| Emplacement | Contenu | Versionné |
|---|---|---|
| `C:/siris-data/lorraine-explorer/snapshots/<id>/` | instantanés datés : `raw/` (charges brutes compressées), `tables/`, `MANIFEST.json`, `SUMMARY.md` | non, jamais |
| `Streamlit/data/` | les 47 fichiers du contrat, écrits par `60_deploy.py` | **oui** |
| `inputs/manual/` | les deux seules entrées maintenues à la main | oui |
| `reports/` | rapports d'étape, journaux de lancement, audits | non |
| `cache/` | caches réutilisables (résumés par DOI, traductions par identifiant de publication) | non |

La racine des instantanés est hors du dépôt et hors OneDrive à dessein : une collecte brute pèse
plusieurs centaines de mégaoctets et n'a pas à se synchroniser. Elle est configurable
(`config.yaml: paths.snapshot_root`).

**Rétention.** `config.yaml: project.snapshot_retention` vaut 3. Au-delà des trois instantanés les
plus récents, seul le répertoire `raw/` est purgé ; `MANIFEST.json`, `SUMMARY.md` et `tables/` sont
conservés indéfiniment. La trace de ce qui a été produit survit donc toujours à la purge du volume.

## 7. Les deux entrées manuelles

Le pipeline n'accepte que deux fichiers non reproductibles, tous deux dans `inputs/manual/` et tous
deux propriété du client :

**`Identifiants_UnivLorraine.xlsx`**, la liste de référence des structures (70 lignes, 68
identifiants OpenAlex). Le fichier est conservé à l'octet près. Un identifiant mort y subsiste et
sa réparation est déclarée dans `config.yaml: perimeter.openalex_id_repairs`, donc auditable, plutôt
que corrigée en silence dans le fichier client. Les 21 structures qu'OpenAlex rattache à
l'Université de Lorraine sans qu'elles figurent dans cette liste sont signalées, sélectionnables
dans l'application et marquées « hors liste ». Leur sort relève de l'arbitrage de l'atelier.

**`all_doi_isite.xlsx`**, la liste des DOI I-SITE (3 843 lignes, 3 776 DOI uniques après
normalisation). Elle est gelée et fait foi : le drapeau `In_LUE` est l'appartenance à cette liste,
et rien d'autre. Le code de financement OpenAlex correspondant est stocké dans une colonne séparée à
titre de recoupement, jamais fusionné.

Modifier l'un de ces deux fichiers change le périmètre. Le faire suppose de relancer le pipeline,
puis de lire l'écart avec `90_snapshot_diff.py` avant de déployer.

## 8. Quand quelque chose échoue

**Lire le journal, pas la console.** `run_all.py` ne déverse aucune trace d'exception à l'écran : il
nomme le fichier `reports/_runall_<étape>.log` qui contient la sortie complète de l'étape fautive,
et donne la commande de reprise.

**Reprendre où l'on s'est arrêté.** La commande imprimée est de la forme
`python run_all.py --snapshot <id> --resume --from-step <étape> --to-step 60`. Rien de ce qui a
réussi n'est refait, aucun appel API n'est redépensé.

**Instantané introuvable.** Une étape autre que la collecte lit un instantané existant, elle n'en
crée pas. Si `--from-step` désigne une étape de construction et que l'instantané n'a pas de
`tables/`, le lancement s'arrête avant tout travail avec le message correspondant. Vérifier
l'identifiant, ou repartir de `--from-step 10`.

**Encodage de la console Windows.** La sortie standard de cette machine est en cp1252. Les scripts
reconfigurent leur sortie en UTF-8 au démarrage ; un script ajouté ultérieurement qui imprimerait
des caractères accentués sans le faire échouerait en cours de route sur un `UnicodeEncodeError`.

## 9. Organisation du dépôt

```
config.yaml            tous les paramètres, un seul fichier
run_all.py             l'orchestrateur : 36 étapes, ordre de dépendance vérifié (nouveaux passe 5 :
                       47c/49w/49c/47b -- benchmark de pairs étendu, contexte pairs bench_sdg/
                       positioning/diversity, croisements labo x frontier/ODD)
pipeline/              une étape par script, numérotée, reprenable, traçante ;
                       49_pull_peer_benchmark.py + 49b_build_peer_benchmark.py = T4b (pass 4 G4)
lib/                   client OpenAlex, gestion des instantanés, appariement d'auteurs
lib/connectors/        cookbook de connecteurs SIRIS embarqué (HAL, OpenAIRE, OpenAlex)
inputs/manual/         les deux entrées manuelles
inputs/overlays/       registres éditables (fusions, blocklist, groupes...) ;
                       bench_peers.csv = les 9 pairs du benchmark (pass 4 G4), l'atelier y
                       garde son pouvoir d'arbitrage sans toucher au code
tests/                 invariants, tests de contrat, échantillon de référence ODD,
                       test_bench_peers.py (pass 4 G4), test_theme_identity.py (pass 4b),
                       conftest.py (garde sys.modules['lib'] centralisée, F-SYSMOD) ;
                       python -m pytest tests/ -q -> 413 passés + 1 ignoré
docs/                  contrat de données et documentation française (§9.8 METHODES.md = T4b) ;
                       docs/foundry/ = fondation de données canonique, rev 3.1
Streamlit/             l'application -- Menu (Menu.py) + 14 pages numérotées (liste complète dans
                       Streamlit/README.md) ; sidebar à 3 bascules (conférence, hors référentiel,
                       surcouche I-SITE -- METHODES §9.12) ; Streamlit/data/ est alimenté par
                       60_deploy.py (47 fichiers)
reports/               sorties d'étape, journaux, audits
```
