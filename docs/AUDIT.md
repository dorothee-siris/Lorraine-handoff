# L'audit de déploiement

L'audit est la barrière entre un instantané reconstruit et une mise en ligne. Il s'exécute sur les
fichiers **réellement déployés**, dans `Streamlit/data/`, et non sur une table intermédiaire : ce
qui est vérifié est ce qui sera servi.

```bash
python pipeline/80_audit.py
```

Le script écrit `reports/audit_run.md` et sort en **code 0** si, et seulement si, la totalité de la
classe 1 est verte et aucune famille de la classe 2 n'est au niveau `INVESTIGATE` sans explication
enregistrée. Toute autre situation rend un code non nul. Sortie attendue sur l'instantané de
référence :

```
Class 1: 13/13 passed
Class 2: 8 families evaluated, 0 unexplained INVESTIGATE
```

Deux options existent. `--snapshot <id>` désigne l'instantané dont les tables internes sont
nécessaires à quelques contrôles (la base de référence française, par exemple) ; par défaut, c'est
celui de `config.yaml`. `--tables-dir <chemin>` déplace les contrôles de classe 1 vers un autre
répertoire, ce qui sert à vérifier que l'audit échoue bien quand on lui présente des données
volontairement dégradées.

---

## 1. Classe 1 : les invariants structurels

Ce sont des propriétés qui doivent tenir, toujours, indépendamment des données. **Un seul échec
fait échouer le lancement.** Il n'y a pas de tolérance, pas de bande, pas d'appréciation : soit la
propriété tient, soit le produit est cassé.

| Contrôle | Ce qu'il vérifie |
|---|---|
| `file_set_exact` | les 15 fichiers du contrat sont présents, ni plus ni moins |
| `pk_unique` | aucune clé primaire dupliquée |
| `fk_resolves` | toute clé étrangère pointe vers une ligne existante |
| `taxonomy_is_superset` | aucun identifiant thématique absent du dictionnaire de taxonomie |
| `no_lab_unchanged` | le compartiment `NO LAB` vaut exactement la valeur attendue (4 568) |
| `hors_liste_rows` | les 21 structures hors liste sont présentes, avec leurs totaux attendus |
| `indicator_status_never_zero` | aucune publication en strate mince ne porte un indicateur non nul : l'absence de mesure ne doit jamais devenir un zéro |
| `is_abstract_present` | la colonne `Is_abstract` existe, celle que le déploiement de la version 1 avait perdue en silence |
| `provenance_flag_present` | toute publication du corpus entre bien par la requête de périmètre |
| `no_impossible_values` | aucune valeur hors domaine (part négative, année hors fenêtre, etc.) |
| `blob_separator_safety` | aucun nom de structure ne contient le séparateur des colonnes composites, qui décalerait silencieusement tous les champs suivants |
| `pptop_no_year_gradient` | l'écart entre années de la part du top 10% reste sous 12 points, le défaut corrigé de la version 1 |
| `zero_tm_references` | aucune trace résiduelle du modèle de topics retiré |

La même famille de contrôles est également couverte par `python -m pytest tests/ -q`, qui exécute
52 tests sur les invariants et sur la conformité au contrat de données. Les deux sont
complémentaires : les tests s'exécutent sur des chemins fixes issus de la configuration, l'audit
s'exécute sur un répertoire déployé arbitraire.

## 2. Classe 2 : les bandes de dérive

La classe 2 ne vérifie pas une propriété, elle surveille un **déplacement**. Elle compare huit
familles de grandeurs à leur valeur de référence, aujourd'hui celle de la version 1, demain celle de
l'instantané précédent, et rend un verdict par famille.

Chaque famille a deux seuils, lus dans `config.yaml: audit.drift_bands` :

| Famille | Attendu | Enquête |
|---|---|---|
| `corpus_size` | ±10% | > 25% |
| `works_per_lab` | ±15% | > 30%, ou toute structure tombant à 0 |
| `abstract_coverage` | ±5 points | > 10 points, à la baisse seulement |
| `sdg_coverage` | ±3 points | > 7 points |
| `fwci_fr_median` | ±10% | > 20% |
| `partner_count` | ±15% | > 30% |
| `isite_flagged` | ±5% | > 10% |
| `pptop_share_per_year` | 10% ± 2 points **à l'intérieur de la France** | hors tolérance |

Trois verdicts possibles. **`OK`** : l'écart est dans la bande attendue. **`WATCH`** : l'écart
dépasse la bande attendue sans atteindre le seuil d'enquête, il est signalé et n'empêche rien.
**`INVESTIGATE`** : l'écart dépasse le seuil d'enquête.

Deux détails de conception méritent d'être signalés. La bande `abstract_coverage` n'est
asymétrique qu'en apparence : une hausse de couverture est la direction attendue et documentée,
seule une baisse est traitée comme suspecte. Et la bande `pptop_share_per_year` teste le seuil
**contre la population française**, pas contre la part lorraine : l'appliquer à un sous-ensemble
intensif en recherche reviendrait à affirmer que l'Université de Lorraine ne peut pas s'écarter de
sa moyenne nationale, ce qui est exactement ce que l'indicateur mesure.

## 3. Ce que « INVESTIGATE bloque le déploiement » signifie en pratique

Un `INVESTIGATE` non expliqué fait sortir `80_audit.py` en code non nul. Concrètement, cela veut
dire que l'instantané ne doit pas être publié en l'état : l'écart doit d'abord être compris.

La procédure est la même à chaque fois. Lire la ligne correspondante de `reports/audit_run.md`, qui
donne la valeur de référence, la valeur mesurée, l'écart et la bande. Ouvrir le diagnostic joint
quand il en existe un : la famille `works_per_lab`, par exemple, liste les structures qui bougent le
plus, avec leurs deux valeurs. Décomposer l'écart jusqu'à une cause nommée. Puis choisir entre trois
issues : corriger un défaut du pipeline si c'en est un, enregistrer une exception expliquée si la
cause est établie et extérieure, ou renoncer au déploiement.

**La quatrième issue n'existe pas : on n'élargit pas la bande.** Une bande élargie pour faire passer
un lancement ne détectera plus jamais rien. Le mécanisme d'exception a été conçu précisément pour
éviter cette tentation.

## 4. Le mécanisme d'exception expliquée

Une exception est une décision nommée, datée, adossée à une preuve écrite, qui relève le **statut**
d'un écart précis et déjà mesuré. Elle ne touche jamais au seuil.

Trois conditions la définissent. Elle porte sur un écart déjà mesuré et décomposé, pas sur une
famille en général. Elle cite le document qui l'établit, consultable. Et elle est inscrite en dur
dans le script, ce qui la rend visible en relecture de code : le script ne peut pas s'accorder une
exception à lui-même en cours d'exécution.

L'instantané de référence en compte deux, toutes deux liées au premier lancement de la version 2.

**`corpus_size`**, croissance de +31,1%. La cause est la reclassification par OpenAlex de 3 737
publications de la version 1 vers le type `conference-paper`, désormais retenu, et l'élargissement du
périmètre. Signée dans la section 4 de [`SHIFT_v1_v2.md`](SHIFT_v1_v2.md).

**`works_per_lab`**, 58 structures sur 78 au-delà de la bande. La cause a été établie par une
décomposition publication par publication des 50 structures identifiables : les totaux par structure
croissent plus vite que le corpus parce que le moteur d'appariement d'affiliations d'OpenAlex
continue de retraiter l'historique des années après une collecte, et non parce que les structures
lorraines ont publié davantage ni parce que la logique de rattachement aurait changé. Un balayage
exhaustif des 35 416 couples (publication, structure) n'a relevé aucune violation. Détail en section
6 de [`SHIFT_v1_v2.md`](SHIFT_v1_v2.md).

Ces deux exceptions couvrent le passage de la version 1 à la version 2. Elles ne sont pas un nouveau
défaut pour les instantanés suivants : à partir du deuxième lancement, la comparaison se fait contre
l'instantané précédent et les mêmes bandes s'appliquent à nouveau pleinement.

## 5. Lire `reports/audit_run.md`

Le rapport se lit en quatre temps.

**L'en-tête** donne l'instantané audité et le répertoire des fichiers déployés sur lequel la classe 1
a porté. Vérifier que c'est bien celui attendu, en particulier après un retour arrière.

**Le tableau de classe 1** doit être entièrement vert. Chaque ligne porte le détail chiffré du
contrôle, ce qui rend un échec lisible sans ouvrir le code : le contrôle `no_lab_unchanged` affiche
la valeur trouvée et la valeur attendue, `pptop_no_year_gradient` affiche l'écart mesuré et la limite.

**Le tableau de classe 2** donne, par famille, la valeur de référence, la valeur mesurée, l'écart, la
bande, le verdict et une note. La colonne de note est l'essentiel : c'est là que se lit pourquoi un
écart est acceptable, ou sur quelle base une comparaison a été ajustée. La famille `partner_count`,
par exemple, indique que la comparaison est faite à seuil égal, parce que la version 1 appliquait un
seuil implicite avant livraison.

**La section des exceptions puis le verdict.** Un verdict `PASS` signifie que la classe 1 tient
intégralement et qu'aucune famille n'est en `INVESTIGATE` hors exception enregistrée. C'est la
condition de mise en ligne, et rien d'autre ne l'établit.

## 6. Comparer deux instantanés

L'audit compare à une référence ; `90_snapshot_diff.py` compare deux instantanés entre eux, sur les
mêmes huit familles et les mêmes bandes, lues dans le même fichier de configuration.

```bash
python pipeline/90_snapshot_diff.py 2026-08-11 2026-08-12
```

C'est l'outil à passer **avant** de décider de garder un rafraîchissement : il montre ce qui a bougé
et de combien, famille par famille, et écrit `reports/snapshot_diff_<ancien>_vs_<nouveau>.md`. Une
table absente d'un des deux instantanés est signalée comme telle, jamais traitée comme une valeur
nulle. La logique de bandes elle-même se vérifie sans données par
`python pipeline/90_snapshot_diff.py --selftest`.
