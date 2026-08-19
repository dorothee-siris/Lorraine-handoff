# Ce qui change entre la version 1 et la version 2

Le corpus passe de **28 094** à **36 819** publications, soit **+31,1%**. L'écart n'est pas un
effet de production : il tient à trois causes nommées, mesurées séparément, et à la correction de
trois défauts de la version 1 que la reconstruction a mis au jour.

Ce document compare l'instantané **2026-08-11** de la version 2 à l'enregistrement gelé de la
version 1, tel qu'il est déployé aujourd'hui. La version 1 n'a été ni modifiée ni recalculée : elle
reste en ligne, inchangée, et chaque chiffre qui lui est attribué ici a été recalculé directement
depuis ses propres fichiers déployés, sauf mention explicite du contraire.

**Une convention de lecture, qui vaut pour toute la première partie.** Là où la version 1 portait un
défaut, le message est « nous avons identifié et corrigé un biais », jamais « le bon chiffre est
N% ». Les deux séries sont présentées côte à côte, et l'ancienne n'est pas retirée : c'est
l'écart entre les deux qui est l'information.

---

# Partie I. Trois défauts identifiés et corrigés

## 1. Un biais temporel sur l'indicateur du top 10%

**Ce que nous avons trouvé.** L'indicateur `Is_PPtop10%_(subfield)` de la version 1 calculait un
seuil unique par sous-domaine, en mélangeant les cinq années de publication et les deux types de
documents dans un même quantile. Or les citations s'accumulent avec le temps : une publication de
2019 a eu six ans pour être citée, une publication de 2023 en a eu deux. Un seuil qui ignore
l'année sur-crédite mécaniquement les années anciennes et sous-crédite les récentes.

L'effet est visible à l'œil nu dans la série livrée.

| Année | Version 1, série livrée | Version 2, série corrigée |
|---|---|---|
| 2019 | 15,4% | 7,2% |
| 2020 | 14,6% | 8,3% |
| 2021 | 10,1% | 8,6% |
| 2022 | 5,6% | 8,0% |
| 2023 | 2,5% | 8,4% |
| **Écart maximal entre années** | **13,0 points, décroissance monotone** | **1,4 point, sans gradient** |

La version 1 fait passer l'Université de Lorraine de 15,4% à 2,5% d'excellence citationnelle en cinq
ans. Aucune trajectoire scientifique ne produit une telle pente sur cinq années consécutives : c'est
la signature d'un artefact de normalisation, pas d'un déclin. La version 2 stratifie le seuil sur
sous-domaine × année × type et le définit par rang centile plutôt que par comparaison à un p90
interpolé, ce qui corrige au passage un second effet, l'admission en bloc des publications assises
exactement sur la coupure dans une distribution de citations très nouée.

**Ce que cette correction ne dit pas.** Elle ne dit pas que « le bon chiffre est 10% ». La cible de
10% est une propriété de la *population de référence française*, où elle doit tenir par
construction, et c'est là qu'elle est testée : le seuil y sélectionne 8,42% à 9,27% des publications
selon l'année. Elle n'est jamais affirmée sur l'Université de Lorraine, parce que la capacité d'un
établissement à s'écarter de sa moyenne nationale est exactement ce que l'indicateur est censé
pouvoir montrer. Le défaut corrigé est le **glissement entre années**, pas le niveau.

Deux vérifications indépendantes confirment la nouvelle définition : l'accord avec le propre
indicateur de top 10% d'OpenAlex passe de 79-86% à **92-93%**, et le `FWCI_FR` moyen, calculé sur la
même stratification, se réconcilie avec celui de la version 1 (section 8).

## 2. Une troncature des auteurs dans les données collectées

**Ce que nous avons trouvé.** L'API OpenAlex tronque la liste des affiliations à 100 entrées sur son
point d'entrée de liste, alors que son point d'entrée par publication rend l'enregistrement complet.
La version 1 construisait son champ `Authors` depuis la liste, et plafonnait donc à exactement 100
noms.

La signature est nette dans les données livrées : **132 publications** de la version 1 s'arrêtent à
exactement 100 auteurs, et le champ ne dépasse cette valeur sur aucune de ses 28 094 publications.
Ce n'est pas un plafond naturel de la co-signature, c'est une coupure.

La conséquence dépasse l'affichage des noms. Sur au moins une publication vérifiée, l'affiliation de
l'Université de Lorraine elle-même se situait au-delà de la centième position : la publication
entrait bien dans le périmètre, puisque le serveur filtre sur l'enregistrement complet, mais notre
lecture n'y voyait aucune affiliation lorraine. Le rattachement à une structure, les comptages de
partenaires et la table des auteurs étaient donc silencieusement faux sur ces publications à très
grande signature.

**Ce que fait la version 2.** Toute publication présentant un signal de troncature est re-collectée
individuellement sur le point d'entrée complet, et un invariant structurel fait échouer le
lancement si un enregistrement stocké déclare moins d'institutions qu'OpenAlex n'en annonce. Sur
l'instantané courant, 145 publications portent le drapeau de vigilance, dont **122 dépassent
réellement 100 auteurs**, avec un maximum observé à **1 626 auteurs**, et **0 enregistrement**
demeure incomplet.

## 3. Un artefact sur les totaux par structure de la version 1

**Ce que nous avons trouvé.** Ce troisième défaut a été découvert en cherchant l'origine d'un écart
d'audit sur les publications par structure, et non lors du premier examen.

L'étape de construction des structures de la version 1 filtre les couples publication-structure sur
la présence d'un identifiant thématique. Mais la valeur *stockée* sur **567 des 28 094 publications
de la version 1, soit 2,0%**, est la chaîne de caractères littérale `"Unknown"`, et non une vraie
valeur absente. La conversion numérique la transforme en valeur manquante *après* que les couples
ont été formés : ces publications disparaissent alors du total affiché de chaque structure, alors
qu'elles restent dans le corpus et qu'elles satisfont toujours la règle de rattachement de la
structure.

**La perte n'est pas répartie uniformément.** Le classificateur thématique d'OpenAlex a
historiquement moins bien traité les contenus de sciences humaines en langue française, si bien que
l'effet se concentre sur les laboratoires SHS. Le CRULH satisfait la règle de rattachement sur
**276 publications** ; la table livrée par la version 1 en affiche **212**. Soit **64 publications
manquantes, 23,2% de son périmètre réel**, toutes porteuses de l'identifiant thématique `"Unknown"`.

**Ce que fait la version 2.** Aucun filtre équivalent n'est appliqué : le total d'une structure est
le décompte de son bloc, sans condition. L'exclusion liée aux strates minces n'affecte qu'une
colonne de divulgation dédiée, jamais le décompte principal.

**La portée de ce défaut est petite et quantifiée.** Il gonfle de **+2,7%** l'écart mesuré sur les
publications par structure, soit 324 publications sur un écart agrégé de 12 118. C'est un
contributeur mineur à côté de la cause dominante, décrite en section 6. Il est signalé ici pour la
même raison que les deux précédents : il a été trouvé, il est corrigé, et les autres chiffres de la
version 1 ne sont pas rétroactivement recalculés pour autant.

---

# Partie II. Les écarts expliqués

## 4. Le corpus : +31,1%, et pourquoi

Le corpus passe de 28 094 à 36 819 publications. Deux causes, mesurées séparément.

**La reclassification des types de documents par OpenAlex.** Des 26 173 publications de la version 1
encore présentes dans OpenAlex aujourd'hui, **3 737 sont désormais typées `conference-paper`**, un
type que la version 1 excluait purement et simplement. La décision D36 les conserve, avec un drapeau
explicite : les exclure aurait fait disparaître des publications que le client voit dans l'outil
actuel et aurait sous-représenté le LORIA et les équipes INRIA. Au total, 9 061 actes de conférence
entrent dans le corpus.

**L'élargissement du périmètre et la croissance de la base.** Le reste vient de publications
qu'OpenAlex rattache aujourd'hui à l'Université de Lorraine et qu'il ne rattachait pas à la date de
la collecte de la version 1.

La continuité entre les deux corpus se lit ainsi : **24 325 des 28 094 publications de la version 1,
soit 86,6%**, sont toujours dans le corpus de la version 2. Sur les 3 769 sortantes, 1 848 ont été
retypées en amont vers un type désormais écarté, principalement en préprints et en résumés de
conférence, et 1 921 ne sont plus dans le périmètre. S'y ajoutent 12 494 publications nouvelles.

Cette croissance de +31,1% **dépasse délibérément la bande d'audit** de la famille `corpus_size`
(±10% attendu, enquête au-delà de 25%). Elle est enregistrée comme exception expliquée, nommée une
fois, sur ce premier lancement. La bande elle-même n'est jamais élargie : c'est le statut de cet
écart précis qui est relevé, pas le seuil qui est déplacé.

**Un avertissement à porter jusqu'aux indicateurs.** Les actes de conférence lorrains ont une
médiane de 0 citation et 78,0% d'entre eux ne sont jamais cités. La stratification par type traite
cet effet par construction, mais il pèse sur les médianes agrégées (section 8).

## 5. Les résumés : 92,3% de couverture, désormais reproductible

| | Version 1 | Version 2 |
|---|---|---|
| Texte physiquement présent avant complément | 57,7% | 74,0% |
| Couverture finale | 80,1% | **92,3%** |
| Couverture finale hors actes de conférence | sans objet | 92,1% |

Le point important n'est pas le gain de 12,2 points, il est la traçabilité. Les 80,1% de la version
1 reposaient sur 6 311 résumés récupérés par une extraction ponctuelle dont **le texte n'a jamais
été archivé** : seule la liste des identifiants a survécu. Ce chiffre ne peut donc être reproduit à
partir d'aucun élément encore détenu, et il est cité ici depuis la documentation de la phase 1, non
recalculé. La version 2 remplace cette récupération par une chaîne complète et rejouable, OpenAlex
puis HAL puis OpenAIRE, avec la source et la langue enregistrées sur chaque ligne.

Une hausse de couverture est la direction attendue et documentée. L'audit ne traite comme suspecte
qu'une *baisse* au-delà de la bande.

## 6. Les publications par structure : la cause est en amont

**Le constat.** Sur les 78 structures communes aux deux versions, **58 bougent de plus que la bande
d'audit** (±15% attendu, enquête au-delà de 30%), et dans les deux sens : Georgia Tech passe de 6 à
269 publications, le LISEC de 149 à 900, l'IFG de 203 à 1 000, quand la MSH passe de 126 à 26 et la
ZAM de 227 à 116. Sommés sur les seules lignes de type « laboratoire », les totaux passent de 21 167
à 34 633, soit +63,6% : les totaux par structure croissent environ deux fois plus vite que le corpus
lui-même.

Un écart de cette ampleur ne pouvait pas être classé sans être expliqué. Une investigation
spécifique a décomposé, publication par publication, les 50 structures identifiables par leur ROR,
en cinq catégories de cause.

| Cause | Publications (net) | Part de l'écart agrégé (12 118) |
|---|---|---|
| Publications nouvelles dans le corpus, absentes de celui de la version 1 | +10 004 | +82,6% |
| Publications sorties du corpus de la version 2 | −1 549 | −12,8% |
| Réaffiliation amont, rattachement ajouté par OpenAlex depuis la collecte v1 | +3 365 | +27,8% |
| Réaffiliation amont, rattachement retiré par OpenAlex | −26 | −0,2% |
| Artefact de la version 1 : exclusion des publications sans thématique (section 3) | +324 | +2,7% |

**Aucun défaut de la version 2 n'a été trouvé.** Un balayage exhaustif des **35 416 couples
(publication, structure)** du corpus n'a relevé **aucune violation** de la règle de rattachement.
Les deux versions rattachent d'ailleurs les structures de la même façon, par correspondance
d'identifiant OpenAlex ou de ROR, sans expansion par filiation.

**La cause dominante est extérieure au projet.** Le moteur d'appariement d'affiliations d'OpenAlex
continue de retraiter l'historique des publications des années après la création d'une fiche
institution, réattribuant d'anciens articles vers, et parfois hors de, l'identifiant d'une
sous-structure. Ce même mécanisme explique les gagnants et les deux perdants : la MSH et la ZAM
utilisent le même identifiant OpenAlex gelé dans les deux collectes, ce qui exclut un changement
d'identifiant, et leurs publications sortantes ont bien été réattribuées ailleurs en amont. Par
ailleurs, 56,6% des publications nouvellement entrées ne sont pas des actes de conférence, ce qui
montre que la décision D36 n'explique qu'une partie minoritaire de la croissance.

Sur cette base, `works_per_lab` est enregistré comme seconde exception expliquée, couvrant les 58
structures décomposées. Là encore, la bande n'est pas élargie.

## 7. I-SITE : 1 760 → 1 839

La liste des DOI I-SITE est gelée et fait foi dans les deux versions : la méthode de marquage n'a
pas changé. L'écart de **+79 publications, soit +4,5%**, est une conséquence de la composition du
corpus, cohérente avec sa croissance de 31,1%, et non d'une nouvelle règle.

Les métadonnées de financement d'OpenAlex couvrent indépendamment 764 publications du périmètre sous
le code I-SITE LUE, dont 749 sont dans le corpus, et dont **9 seulement** échappent à la fois à la
liste manuelle et au corpus actuel. Elles
sont conservées dans une colonne de recoupement distincte, jamais fusionnées dans le drapeau
principal : la liste client reste la seule définition.

**Une ligne de la version 1 n'est pas reconduite.** La version 1 portait une pseudo-structure
« ISITE » dans sa table des structures, aux côtés des laboratoires réels. Toute publication marquée
I-SITE apparaissait donc deux fois dans les agrégats par structure, une fois sous son laboratoire
réel et une fois sous cette ligne, ce qui double-comptait 1 760 publications dans des totaux censés
sommer au corpus. La version 2 ne recrée pas cette ligne : le marquage I-SITE reste un attribut
booléen de la publication, et toute ventilation I-SITE filtre sur cet attribut. La même publication
n'est ainsi jamais comptée sous deux clés de structure.

## 8. FWCI_FR : la réconciliation tient

Le `FWCI_FR` de la version 1 était **déjà** stratifié sur sous-domaine × année × type, contrairement
à son indicateur de top 10%. La version 2 emploie la même stratification, et la moyenne se
réconcilie : **0,928 en version 1, 0,938 en version 2**, soit +1,1%. C'est le chiffre de
réconciliation principal, et il confirme indépendamment que la stratification est correcte des deux
côtés.

La médiane, elle, s'écarte : 0,330 contre 0,131 sur le corpus complet. La cause est nommée et
mesurable. La médiane est bien plus sensible que la moyenne à la masse de publications non citées,
et les actes de conférence en apportent une quantité importante, à 78,0% jamais cités. Chaque acte
est pourtant correctement normalisé contre d'autres actes, jamais contre des articles : c'est
l'agrégat qui bouge, pas l'indicateur individuel. Restreinte au périmètre de types de la version 1,
la médiane de la version 2 remonte à **0,280**, soit −15,0% au lieu de −60,2%. Le reliquat
s'explique par la rotation ordinaire du corpus, 12 494 publications nouvelles et une année de
citations supplémentaires entre les deux millésimes.

Cet écart est signalé en `WATCH` dans l'audit plutôt que classé sans mention.

## 9. Objectifs de développement durable

La route SIRIS de la version 2 produit des ensembles d'ODD **identiques à ceux de la version 1 sur
96,5%** des publications que les deux méthodes taguent, avec un indice de Jaccard moyen de 0,983.
Le rapprochement est bien plus étroit que celui obtenu lors de la phase 1 sur les mêmes bases
(71,5% et 0,861), et la raison en est la couverture des résumés : le tagueur reçoit désormais du
texte là où il n'en recevait pas.

La couverture passe de 16,0% du corpus de la version 1 à 14,8% du corpus, plus grand, de la version
2, soit −1,2 point. L'écart reste à l'intérieur du seuil d'enquête.

Ces chiffres mesurent un **accord de méthode**, pas une exactitude : la méthode de la version 1
n'est pas documentée et ne peut servir de vérité terrain. Les trois routes calculées et le matériau
d'arbitrage sont décrits dans [`METHODES.md`](METHODES.md), section 5.

## 10. Partenaires et auteurs : des tables refaites

**Partenaires : une différence de périmètre, pas une dérive.** La comparaison brute des effectifs
induit en erreur. La table livrée par la version 1 compte 3 288 lignes et sa colonne de
co-publications ne descend jamais en dessous de 6 : un seuil minimal implicite était appliqué avant
livraison. La table de la version 2 compte 12 553 lignes et descend jusqu'à une seule
co-publication, sans seuil. Comparées telles quelles, les deux tables afficheraient +281,8% d'écart,
ce qui ne mesurerait rien. En réappliquant le seuil de la version 1, la version 2 rend **3 508
partenaires, soit +6,7%**, à l'intérieur de la bande d'audit. C'est ce chiffre ajusté que l'audit
utilise ; l'effectif brut est publié ici pour transparence, jamais pour le bandage.

**Auteurs : deux défauts de la même famille, corrigés.** La version 1 construisait ses champs
d'auteurs et d'affiliations en assemblant des sous-champs indexés par position, en supprimant les
trous et en décalant tout ce qui suivait ; le désalignement qui en résulte touche **51,4% des
publications de la version 1**. La version 2 ne construit jamais ces agrégats : les affiliations
sont une table native à une ligne par couple auteur-publication, sans indexation positionnelle, de
sorte que cette classe de défaut ne peut pas réapparaître. Deux effets visibles disparaissent avec
elle : les noms d'auteurs livrés sans espaces, que l'application défaisait par une fonction dédiée,
et l'ORCID d'un co-auteur susceptible de se retrouver attribué à une autre personne de la même
ligne.

La table passe de 17 783 lignes à **12 680**, après fusion de 1 557 profils dupliqués. La
comparaison d'effectifs n'a donc pas de sens directement : ce sont deux grains différents.

---

## Récapitulatif

| Quantité | Version 1 | Version 2 | Lecture |
|---|---|---|---|
| Corpus | 28 094 | 36 819 | +31,1%, reclassification des types et croissance amont (section 4) |
| Couverture des résumés | 80,1% | 92,3% | chaîne désormais reproductible (section 5) |
| `FWCI_FR` moyen | 0,928 | 0,938 | réconciliation, la stratification tient (section 8) |
| Top 10% par année | 15,4 → 2,5% | 7,2 à 8,6% | biais temporel corrigé (section 1) |
| Publications I-SITE | 1 760 | 1 839 | +4,5%, effet de composition (section 7) |
| Publications sans thématique | 21% du corpus | 0,1% | taxonomie OpenAlex au lieu du modèle de topics |
| Accord ODD avec la version 1 | référence | 96,5% | accord de méthode, non exactitude (section 9) |
