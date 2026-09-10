# La frontiérité thématique — méthodologie

*Adaptation de la méthodologie ESPON ACCORD d'« émergence temporelle » en une couche de référence
thématique réutilisable pour l'outil de cartographie institutionnelle.*

Source primaire : rapport scientifique ESPON-ACCORD, §2.3 (construction de l'indicateur de
frontiérité au niveau du topic) et Annexe 2 (liste des topics exclus) —
`Client Projects\[REFERENCES]\02_reports\2026_ESPON-ACCORD_frontierness-cognitive-cohesion_
scientific-report.docx`. Note exécutive source (copiée et adaptée ci-dessous) :
`Internal Projects\Research Portfolio Framework\Shared baselines\Frontierness — Methodology and
Pipeline.md`.

---

## 1. Ce que mesure l'indicateur

**La frontiérité mesure la dynamique temporelle de la recherche au niveau du topic** : dans quelle
mesure un topic OpenAlex affiche une dynamique positive de publications et de citations *par
rapport à la base mondiale* — autrement dit, là où la communauté scientifique mondiale investit un
poids incrémental, pas nécessairement là où le volume est déjà élevé.

Ce n'est délibérément **pas** une mesure de nouveauté intrinsèque, de disruption ou de maturité
technologique. La littérature scientométrique propose trois familles de mesures de « frontière » —
les mesures fondées sur la structure de citation / les combinaisons atypiques, les mesures de
nouveauté textuelle, et les mesures de dynamique temporelle. ACCORD retient la **troisième** : la
frontiérité comme *émergence temporelle*. Ce point conditionne la manière dont l'indicateur doit
être présenté au client : il répond à « le monde accélère-t-il, en ce moment, sur ce topic ? », pas
à « ce topic est-il intellectuellement original ? ».

L'unité d'analyse est le **topic OpenAlex** (environ 4 500 topics dans la taxonomie, dérivés de
manière ascendante à partir des réseaux de citation puis étendus à l'ensemble du corpus par des
classifieurs entraînés). Parce que chaque publication peut être rattachée à des topics OpenAlex
avec le même classifieur ouvert, un score de frontiérité calculé une seule fois au niveau du topic
peut être **projeté sur n'importe quelle institution, région ou projet** en héritant simplement du
score de ses topics. Cette projetabilité est tout l'intérêt de la démarche — c'est pourquoi elle
relève d'une couche de référence partagée plutôt que d'un calcul propre à chaque projet.

---

## 2. Mode de calcul

### Entrées et périmètre
- Source : OpenAlex (ACCORD utilise le **snapshot de juillet 2025**).
- Types de documents retenus : **article, review, book-chapter uniquement**. Éditoriaux, errata,
  jeux de données, preprints, etc. sont exclus, pour concentrer le signal sur la production évaluée
  par les pairs.
- Deux signaux par topic : **nombre annuel de publications** et **nombre annuel de citations**.
- Le temps est découpé en **fenêtres de trois ans** de 2001 à 2023. La première fenêtre
  **2001-2003 sert de période de référence** ; les sept fenêtres suivantes (2004-06 … 2022-23)
  reçoivent chacune un score.

### Les trois strates

Notation : pour le topic *i* dans la fenêtre *t*, `P` = moyenne annuelle des publications, `C` =
moyenne annuelle des citations. L'exposant `G` désigne l'agrégat mondial sur tous les topics. `t₀`
est la fenêtre de référence. `z(·)` est un score-z standardisé entre topics **au sein d'une même
fenêtre**.

**Strate 1 — Différentiel de croissance** (calculé séparément pour publications et citations,
`X ∈ {P, C}`) :

```
g^X_{i,t} = [ log(1+X_{i,t}) − log(1+X_{i,t₀}) ]   ← croissance du topic depuis la référence
          − [ log(1+X^G_t)  − log(1+X^G_{t₀}) ]    ← moins la croissance mondiale depuis la référence
```

C'est donc la croissance logarithmique du topic diminuée de la croissance logarithmique du monde.
Positif ⇒ le topic croît plus vite que la science dans son ensemble. Le « `1+` » évite le
`log(0)` ; les logarithmes rendent la croissance multiplicative additive et atténuent les queues
lourdes.

**Strate 2 — les deux composantes**

- **Expansion** (croissance structurelle — la trajectoire longue depuis la période de référence) :
  ```
  Expansion_{i,t} = ½ · ( z(g^P_{i,t}) + z(g^C_{i,t}) )
  ```
  Publications et citations entrent à parts égales (50/50). Une Expansion élevée signifie que le
  topic a dépassé la base mondiale, en volume comme en impact, depuis 2001-2003.

- **Acceleration** (dynamique de court terme — même construction mais fenêtre à fenêtre plutôt que
  contre la référence) :
  ```
  a^X_{i,t} = [ log(1+X_{i,t}) − log(1+X_{i,t−1}) ] − [ log(1+X^G_t) − log(1+X^G_{t−1}) ]
  Acceleration_{i,t} = ½ · ( z(a^P_{i,t}) + z(a^C_{i,t}) )
  ```
  Une Acceleration élevée signifie que la croissance du topic accélère elle-même dans la dernière
  fenêtre — ce qui distingue les topics encore en gain de dynamique de ceux qui ont déjà culminé.

**Strate 3 — Frontiérité composite :**
```
Frontier_{i,t} = 0.7 · Expansion_{i,t} + 0.3 · Acceleration_{i,t}
```

La pondération **70/30** est le levier de robustesse central : elle privilégie la croissance
structurelle *durable* sur les à-coups de court terme, de sorte qu'un pic sur une seule fenêtre (un
effet de mode ou un choc externe) ne peut à lui seul propulser un topic en tête. Effet net :
l'indicateur est **conservateur** — il sous-pondère les petits topics « à la mode » et récompense
les évolutions larges et durables.

### Pourquoi cette construction plutôt que les alternatives naïves
Le nombre brut de publications récompense la productivité indépendamment de l'impact ; le nombre
brut de citations retarde la lecture de la dynamique en temps réel ; les taux de croissance bruts
favorisent les champs déjà volumineux. Combiner publications et citations, mesurer *par rapport à
la base mondiale*, et *standardiser au sein de chaque fenêtre* permet au score de faire ressortir
les topics qui **gagnent en part d'attention**, et non ceux qui suivent simplement l'expansion
générale de la science.

---

## 3. Lire le score : le plan Expansion-Acceleration

Placer les fenêtres d'un topic sur le plan Expansion (x) vs Acceleration (y) donne un cycle de vie
à quatre quadrants, lisible pour un client :

| | **Expansion faible** | **Expansion élevée** |
|---|---|---|
| **Acceleration élevée** | **Émergent** (décollage précoce, encore petit) | **Frontière active** (croît vite *et* accélère) |
| **Acceleration faible** | **Stagnant** (sous la base, pas de dynamique) | **En maturation** (a dépassé la base, ralentit désormais) |

**Limitation d'implémentation dans cette passe (P7) :** l'app Lorraine Explorer ne matérialise, sur
`dim_frontier_components`, que les composantes brutes (Expansion, Acceleration, Frontier, rang
mondial) par topic et par fenêtre — le quadrant lui-même (Émergent / Frontière active / En
maturation / Stagnant) n'est pas une colonne calculée dans cette passe ; le plan P9 le dérive à
l'affichage à partir d'Expansion/Acceleration de la fenêtre la plus récente.

---

## 4. Écarter les topics « non pertinents »

Tous les topics OpenAlex ne recouvrent pas un véritable cluster thématique. La taxonomie étant
construite de manière ascendante à partir des réseaux de citation, certains « topics » ne sont en
réalité que des communautés d'auto-citation délimitées par **la langue ou la nationalité**, non par
le sujet. ACCORD a retiré **811 topics sur environ 4 516 (17 %)**, laissant **3 705** topics, selon
trois règles :

1. **Artefacts linguistiques/nationaux** (repérage manuel) : libellés trop génériques pour une
   taxonomie de 4 500 topics, faible volume de publications, sortie concentrée dans un pays ou un
   groupe de pays partageant une langue.
2. **Topics « area studies » redondants**, quand un équivalent à portée mondiale existe déjà.
3. **Seuil de taille** (entièrement automatisable) : **retirer tout topic sous 10 000
   publications** dans OpenAlex public. En dessous, échantillons trop réduits et croissance
   instable ⇒ un score qui est du bruit, pas un signal.

Cette liste d'exclusion (811 topics) est celle que l'app Lorraine Explorer réutilise
telle quelle — copie-in `inputs/manual/OA_bad_topics.xlsx` == `inputs/manual/
frontierness_baseline.xlsx` (byte-identiques, voir §5).

---

## 5. Les deux « vintages » que porte l'app — RÈGLE : jamais mélangées dans une même figure

L'app Lorraine Explorer porte **deux fichiers manuels distincts**, issus de la même méthodologie
ACCORD mais construits à des granularités différentes, et **qui ne doivent jamais apparaître
ensemble sur une même figure** :

1. **Le score composite « Average frontierness »** — moyenne pondérée (0,7 Expansion + 0,3
   Acceleration) sur **6 fenêtres de 4 ans**, un seul chiffre par topic (`thm_frontier`,
   `thm_frontier_topics`, construits par `47_build_thematic_ext.py` / `47c_build_frontier_topics.py`
   à partir de `inputs/manual/frontierness_baseline.xlsx`, feuille « FILTERING OUT TOPICS », colonne
   « Average frontierness », reprise telle quelle). Fichier byte-identique à
   `inputs/manual/OA_bad_topics.xlsx` (sha256
   `b5017b7d298e088013951f2823b80f93739fee8b9d26a9376868f029c7cf37ac` — vérifié à chaque build).
2. **Les composantes** — Expansion, Acceleration, Frontier et rang mondial par topic, sur **7
   fenêtres de 3 ans** (2004-06 … 2022-23), construites cette passe (P7) par
   `pipeline/47e_build_frontier_components.py` à partir d'un fichier manuel **différent**,
   `inputs/manual/OA_frontier_scores.xlsx` (sha256
   `6b1b1bddba7e3c05530728a86083741ded6bbc60509d671ea5aa38747317bb5d`), table
   `dim_frontier_components` (25 942 lignes = 3 706 topics × 7 fenêtres). Le plan P9 (plan
   Expansion-Acceleration) ne lit que la fenêtre la plus récente (`is_latest`, 2022-23).

**Pourquoi la règle existe** : les deux fichiers ne partagent ni le même découpage temporel (fenêtres
de 4 ans vs 3 ans) ni le même nombre de topics retenus (3 705 vs 3 706 — écart mineur entre deux
copies-in de la même famille méthodologique, non réconcilié, voir §7) ; superposer les deux sur un
même graphique laisserait croire à une continuité qui n'existe pas dans les données sources.
**Chaque figure qui affiche une frontiérité doit porter une légende nommant explicitement laquelle
des deux lectures elle montre** (composite = moyenne toutes périodes ; composantes = dernière
période 2022-23).

---

## 6. Limites connues (à reprendre dans toute rédaction client)

- L'indicateur mesure une **dynamique d'attention, pas l'originalité**. Les effets de mode et les
  chocs exogènes obtiennent un score élevé (le COVID domine le classement 2019-2021) ; les
  frontières profondes à cycle long peuvent obtenir un score faible.
- **Ambiguïté entre topics voisins.** La taxonomie contient des topics quasi dupliqués issus de
  communautés de citation différentes ; un topic proche peut afficher une frontiérité très
  différente. Un léger changement de formulation d'un titre/résumé peut faire basculer le
  classement entre deux topics voisins aux scores très différents.
- **Classification à étiquette unique.** Le classifieur OpenAlex attribue un seul topic par
  document ; un travail multi-thématique est ramené à un seul libellé.
- **Fondamental vs appliqué.** Des champs matures et structurants (une grande partie de la physique
  quantique, par exemple) affichent une dynamique temporelle faible et donc une frontiérité basse,
  alors même qu'ils sous-tendent des frontières appliquées plus récentes — un score bas ne signifie
  pas « hors frontière », il peut signifier « fondamental ».

Cadrage honnête pour toute présentation client : *la frontiérité positionne un topic dans le cycle
mondial d'attention ; c'est un objectif exploratoire pour susciter des questions, pas un jugement de
qualité scientifique.*

---

## 7. Reproductibilité — verdict pour cette passe

**Verdict : non reproductible via l'API OpenAlex dans cette passe.**

**Raison mesurée** : la construction (§2 ci-dessus) exige, pour chaque topic et chaque année de
2001 à 2023, la somme des publications ET des citations, restreinte aux types article/review/
book-chapter. L'API OpenAlex n'expose pas cette maille : le champ `counts_by_year` d'un topic (ou
d'une entité liée) ne couvre qu'une fenêtre glissante d'environ 10 ans, tous types de documents
confondus — ni la profondeur temporelle (2001-2023, soit 23 ans) ni le filtrage par type ne sont
disponibles par ce chemin. Reconstruire la série demanderait de sommer, topic par topic et année
par année, les compteurs de citation de chaque publication individuelle du type retenu — un calcul
hors de portée de l'API à ce volume (voir CLAUDE.md, réflexe coût : `search=` coûte 10× un
`filter=`, et cette reconstruction impliquerait un nombre de requêtes proportionnel au nombre de
publications mondiales, pas au nombre de topics).

**Chemin de reproduction retenu (BigQuery / snapshot) — à documenter pour une refonte future, non
exécuté cette passe :**
1. Extraire du snapshot OpenAlex (BigQuery ou dump), par (topic_id, année), le nombre de
   publications et la somme des citations, restreint aux types `article`/`review`/`book-chapter`,
   pour les années 2001-2023.
2. Agréger en fenêtres de 3 ans (2001-2003 comme référence, puis 2004-06 … 2022-23) — ou de 4 ans
   pour reproduire le composite ACCORD d'origine ; calculer aussi la série agrégée mondiale (« G »).
3. Appliquer les paramètres de la méthode, exposés comme configuration et non comme constantes
   figées dans le code : poids **0,7 / 0,3** (Expansion/Acceleration → Frontier, la pondération
   ACCORD) et **0,5 / 0,5** (publications/citations → chaque composante) ; seuil de taille **10 000
   publications** (règle 3, §4) ; largeur de fenêtre (3 ou 4 ans selon la lecture visée).
4. Nettoyer selon les trois règles du §4 (seuil automatique + liste curatée versionnée) puis
   calculer les strates 1-3 du §2 (score-z **au sein de chaque fenêtre**, jamais sur un
   sous-ensemble par institution).
5. Publier un artefact Parquet unique, horodaté par snapshot, avec le contrôle de validation du §6.3
   de la note source (liste des 15 premiers topics, décompte des topics apparus/disparus).

Cette section documente le chemin pour une passe ultérieure disposant d'un accès BigQuery/snapshot
OpenAlex ; elle n'est pas un engagement de calendrier.

---

## 8. Traçabilité des fichiers (cette passe, P7)

| Fichier | Rôle | sha256 |
|---|---|---|
| `inputs/manual/frontierness_baseline.xlsx` | composite (§5.1) — byte-identique à `OA_bad_topics.xlsx` | `b5017b7d298e088013951f2823b80f93739fee8b9d26a9376868f029c7cf37ac` |
| `inputs/manual/OA_frontier_scores.xlsx` | composantes (§5.2), NEW P7 | `6b1b1bddba7e3c05530728a86083741ded6bbc60509d671ea5aa38747317bb5d` |

Les deux hachages sont vérifiés à chaque exécution de `pipeline/verify_manual_inputs.py` (manifest
`inputs/manual/MANIFEST.sha256`) et, pour le premier, ré-asserté dans le code même de
`46_build_partner_views.py`/`47c_build_frontier_topics.py` avant chaque build (le build s'arrête sur
un écart plutôt que de continuer sur un fichier substitué silencieusement).

---

*Rédigé par S-DAT, pass 7a (2026-09-10). Note exécutive source et rapport scientifique ESPON-ACCORD
cités en tête de document. Ajout au README (liste des docs) laissé à qui possède ce fichier —
non modifié ici (hors fence de ce worker).*
