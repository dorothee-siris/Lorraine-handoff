# Accès à l'application : trois options

L'application est aujourd'hui **publique**, à l'adresse <https://lorraine-handoff-bis.streamlit.app/>,
hébergée sur Streamlit Community Cloud. Elle le reste jusqu'à l'atelier : le choix du mode d'accès
dépend de la politique de l'Université de Lorraine, pas d'un arbitrage technique.

Ce document pose les trois options et leurs compromis. Il ne recommande rien.

**Ce qui est exposé, en pratique.** L'application sert des agrégats bibliométriques construits sur
des métadonnées publiques : publications, affiliations, citations, thématiques, partenaires. Aucune
donnée nominative sensible, aucune donnée non publiée. La question n'est donc pas celle d'une fuite
de données confidentielles, elle est celle du **cadrage** : qui doit pouvoir lire ces chiffres avant
qu'ils ne soient commentés, et sous quelle forme.

---

## Option 1. Public, en l'état

L'adresse est ouverte, sans authentification. C'est la configuration actuelle.

Rien à mettre en place, rien à maintenir, rien à distribuer sinon un lien. Toute personne disposant
de l'adresse accède à l'outil, y compris depuis un moteur de recherche si le lien est indexé. Les
chiffres circulent donc sans contexte : un tiers peut lire une part de top 10% ou un total par
laboratoire sans la note de méthode qui l'accompagne.

## Option 2. Public, protégé par un mot de passe

L'adresse reste ouverte, mais l'application demande un mot de passe partagé avant d'afficher quoi que
ce soit.

Deux formes techniques, au même coût de mise en œuvre. Le mot de passe peut être stocké dans les
**secrets de l'hébergement** (`st.secrets`), c'est-à-dire saisi dans l'interface d'administration de
Community Cloud, jamais écrit dans le dépôt : c'est la forme à retenir, puisque le dépôt est
destiné à être transféré à l'Université. Il peut aussi être inscrit dans le code, ce qui est plus
simple mais rend le mot de passe visible de quiconque lit le dépôt, et impose un commit à chaque
changement.

Le contrôle est un mot de passe unique, partagé. Il filtre l'accès accidentel et l'indexation par
les moteurs, il ne trace pas qui consulte et ne se révoque que globalement. C'est une barrière de
cadrage, pas un contrôle d'accès nominatif.

## Option 3. Application privée, avec liste d'accès

L'application est déclarée privée dans Community Cloud. Elle n'est plus accessible sans
authentification : chaque lecteur doit être invité nommément, par adresse électronique, et se
connecter pour entrer.

C'est le seul des trois dispositifs qui identifie les lecteurs et qui permet de révoquer un accès
individuellement. Le prix en est la friction : chaque nouveau lecteur suppose une invitation
préalable, et chacun doit s'authentifier avec le compte correspondant à l'adresse invitée. Pour une
démonstration en atelier, cela signifie que la liste doit être établie avant la séance.

**Point à vérifier avant de trancher** : le nombre de lecteurs autorisés sur une application privée
en offre gratuite est plafonné, et ce plafond a changé plusieurs fois. Il doit être confirmé sur les
conditions en vigueur à la date de l'atelier, en regard du nombre de personnes à qui l'Université
souhaite ouvrir l'outil.

---

## Comparaison

| | Public en l'état | Mot de passe partagé | Application privée |
|---|---|---|---|
| **Coût financier** | nul | nul | nul en offre gratuite, sous réserve du plafond de lecteurs |
| **Coût de mise en œuvre** | nul, c'est l'état actuel | environ une heure de développement, plus un secret à saisir | quelques minutes de configuration, plus la constitution de la liste |
| **Coût de maintenance** | nul | rotation du mot de passe à la main, diffusion à chaque changement | gestion des invitations à l'entrée et à la sortie des personnes |
| **Friction pour le lecteur** | nulle, un lien suffit | un mot de passe à saisir, à obtenir par un autre canal | authentification obligatoire, invitation préalable |
| **Confidentialité** | aucune, indexable par les moteurs | l'accès accidentel et l'indexation sont bloqués ; le mot de passe se transmet | accès nominatif, révocable individuellement |
| **Traçabilité des accès** | aucune | aucune | par lecteur invité |
| **Révocation** | sans objet | globale, par changement de mot de passe | individuelle |
| **Adapté à** | un outil assumé comme public | un cercle élargi, sans besoin de savoir qui consulte | un cercle restreint et nommé |

---

## La mise en veille, et le maintien en éveil

Un point indépendant du choix ci-dessus, mais qui se décide au même moment.

Sur Community Cloud, une application qui n'a pas été consultée pendant plusieurs jours est **mise en
veille**. Elle n'est pas perdue : le visiteur suivant voit un écran l'invitant à la réveiller, et
l'application redémarre en quelques dizaines de secondes. L'effet est donc un temps d'attente et une
impression d'outil hors service, jamais une perte de données.

Le contournement usuel consiste à faire visiter l'adresse automatiquement à intervalle régulier, par
une tâche planifiée, ce qui maintient l'application éveillée en permanence. Trois remarques avant de
le retenir. Ce dispositif suppose un service extérieur qui exécute la visite, donc une dépendance de
plus à maintenir. Il est incompatible avec l'option 3 telle quelle, puisqu'une application privée
exige une authentification qu'une visite automatique ne fournit pas. Et il ne s'impose que si
l'usage réel est épisodique : une application consultée chaque semaine ne s'endort pas.

L'alternative est de ne rien mettre en place et de prévenir les utilisateurs qu'un premier accès
après une longue pause demande un clic et une attente. C'est le choix par défaut, et il n'a aucun
coût.

---

## Ce qui reste à arbitrer

Trois questions, dans cet ordre. Qui doit pouvoir lire l'outil : le public, un cercle élargi, ou une
liste nommée ? Faut-il savoir qui l'a consulté ? Et l'usage attendu justifie-t-il un dispositif de
maintien en éveil, ou une attente occasionnelle au réveil est-elle acceptable ?

Les trois options sont réversibles, et le passage de l'une à l'autre ne touche ni les données ni le
pipeline. Rien n'oblige donc à choisir définitivement à l'atelier : un mode peut être retenu pour la
phase de prise en main et révisé ensuite.
