# Rapport de stage — NetQoS-AI — Binôme B

**Supervision intelligente de la QoS réseau** · Intelligence artificielle,
modélisation et restitution.

**[NOM DE L'ÉCOLE / UNIVERSITÉ]** · [FORMATION / DIPLÔME VISÉ]

Présenté par **[NOM ET PRÉNOM DU STAGIAIRE]**

| | |
|---|---|
| **Structure d'accueil :** | [NOM DE L'ENTREPRISE] |
| **Maître de stage :** | [NOM DU MAÎTRE DE STAGE] |
| **Tuteur pédagogique :** | Prof. Boudal NIANG |
| **Période de stage :** | [DATE DE DÉBUT] – [DATE DE FIN] (4 semaines) |
| **Coéquipier (Binôme A) :** | [NOM DU COÉQUIPIER] |

> **Note de rédaction — à supprimer avant remise.** Les mentions
> `[À COMPLÉTER]` et `[NOM …]` correspondent aux informations administratives
> propres au stagiaire et à la structure d'accueil, que ce document ne peut pas
> deviner. Tous les chiffres cités ailleurs sont issus de `reports/metrics/` et
> se régénèrent par les commandes de l'annexe G.

---

## Remerciements

Je tiens à exprimer ma gratitude à toutes les personnes qui ont contribué à la
réussite de ce stage.

Je remercie tout particulièrement [NOM DU MAÎTRE DE STAGE], mon maître de stage,
pour son encadrement et sa disponibilité, ainsi que le Prof. Boudal NIANG, mon
tuteur pédagogique, pour son suivi régulier et l'exigence méthodologique qu'il a
maintenue tout au long du projet.

Je remercie mon coéquipier du Binôme A, [NOM DU COÉQUIPIER], dont le pipeline de
données et l'API constituent la matière première de tout mon travail. Nos
échanges techniques, y compris ceux portant sur les défauts d'intégration que ce
rapport détaille, ont été la partie la plus formatrice du stage : ils m'ont appris
qu'un contrat d'interface ne vaut que par la rigueur avec laquelle les deux
parties le vérifient.

Mes remerciements vont enfin à l'ensemble de l'équipe de [NOM DE L'ENTREPRISE]
pour son accueil et le partage de son expertise.

---

## Introduction

Dans le cadre de ma formation en [FORMATION], j'ai effectué un stage de quatre
semaines au sein de [NOM DE L'ENTREPRISE], du [DATE DÉBUT] au [DATE FIN]. Ce
stage s'est articulé autour du projet NetQoS-AI, une plateforme de supervision
intelligente de la qualité de service (QoS) d'un réseau de télécommunications.

Le projet répond à une question opérationnelle simple à formuler et difficile à
traiter : à partir des indicateurs de performance collectés en continu sur les
cellules d'un réseau — débit, latence, gigue, taux de perte de paquets et charge
de cellule — comment **détecter** une dégradation atypique, **l'anticiper** à
quelques dizaines de minutes, et **la restituer** à un exploitant sous une forme
sur laquelle il puisse agir ?

Le projet a été scindé en deux volets complémentaires confiés à deux binômes
travaillant en parallèle. Le **Binôme A** produit les données : génération,
ingestion, nettoyage, calcul de caractéristiques, stockage en base de séries
temporelles, et exposition via une API REST. Le **Binôme B**, dont ce rapport
présente le travail, les consomme : analyse exploratoire, détection d'anomalies,
prévision des KPI, et tableau de bord de supervision.

J'ai intégré le Binôme B. Cette position de **consommateur** a une conséquence
qui a structuré tout mon stage : je ne produis aucune donnée, je n'ai aucun accès
à la base, et la totalité de ma matière première transite par une interface HTTP
que je ne contrôle pas. Le contrat d'interface n'était donc pas pour moi un
document administratif mais la définition même de mon périmètre de travail — et
sa vérification, une part importante du travail lui-même.

Ce rapport présente le contexte et l'organisation du projet, l'environnement
technique mobilisé, le déroulement du stage au regard des quatre jalons fixés,
les difficultés techniques rencontrées et la façon dont elles ont été résolues,
les résultats obtenus, et un bilan des compétences acquises. Une attention
particulière est portée à quatre difficultés dont la résolution a été
déterminante, et à une question que le rapport traite frontalement : pourquoi le
modèle de détection retenu n'atteint-il pas les 90 à 100 % de performance qu'on
attend spontanément d'un modèle d'apprentissage, et pourquoi cette limite est un
résultat mesuré plutôt qu'un échec.

---

## 1. Présentation du contexte

### 1.1. La structure d'accueil

*[Présentez ici l'entreprise ou la structure d'accueil : secteur d'activité,
taille, missions, positionnement, organisation du service d'accueil.]*

- Nom de la structure : [À COMPLÉTER]
- Secteur d'activité : [À COMPLÉTER]
- Effectif : [À COMPLÉTER]
- Service d'accueil : [À COMPLÉTER]

### 1.2. Contexte et enjeux du projet NetQoS-AI

Pour un opérateur de réseau, une dégradation de qualité de service non détectée à
temps se traduit directement par une expérience utilisateur dégradée — coupures,
lenteurs, appels de mauvaise qualité — et à terme par un risque de perte de
clientèle. La supervision traditionnelle repose sur des **seuils fixes** définis
manuellement par indicateur : au-delà de tant de millisecondes de latence,
l'alerte se déclenche.

Cette approche a deux limites, que le projet a permis de quantifier plutôt que de
supposer.

La première est qu'un seuil fixe ignore la **variabilité normale** du trafic. Une
charge de cellule à 90 % est banale à l'heure de pointe et anormale à quatre
heures du matin ; un seuil unique se trompe dans les deux cas. L'analyse
exploratoire (§5.1) montre une saisonnalité journalière et hebdomadaire marquée
sur les cinq indicateurs : le référentiel pertinent n'est pas une constante, mais
l'écart au comportement habituel de la cellule à cette heure-là.

La seconde est qu'un seuil ne détecte que les anomalies **d'amplitude**, pas
celles de **forme**. Une gigue anormalement irrégulière à charge et à latence
normales ne franchit aucun seuil, mais signale un problème. Le croisement mené au
§5.1 le chiffre : appliqués tels quels, les seuils du contrat classent
« critique » **43 % des instants pourtant normaux**, tout en laissant 14 % des
anomalies réelles en dessous de leur radar. Un exploitant qui s'y fierait
recevrait une majorité de fausses alertes tout en manquant une partie des vrais
incidents.

Le projet NetQoS-AI vise à dépasser cette limite en combinant un pipeline de
données industrialisé avec des méthodes d'apprentissage : détection d'anomalies
non supervisée, prévision des indicateurs à court terme, et restitution dans un
tableau de bord interactif destiné aux équipes d'exploitation.

### 1.3. Organisation en deux binômes, et ce que la frontière implique

Le projet a été scindé en deux périmètres distincts mais interdépendants, avec un
contrat d'interface formalisé dès la première semaine.

| Binôme | Périmètre | Livrables principaux |
|---|---|---|
| Binôme A | Ingénierie des données & pipeline (hors périmètre de ce rapport) | Génération, ingestion, nettoyage, feature engineering, base TimescaleDB, API REST, orchestration Airflow |
| Binôme B (mon périmètre) | Intelligence artificielle & restitution | Analyse exploratoire, détection d'anomalies, prévision des KPI, tableau de bord, rapports d'évaluation |

La frontière entre les deux volets est **matérialisée par l'API HTTP** : le
Binôme B n'a aucun accès à la base de données, et n'importe aucun code du Binôme
A. Cette contrainte, inscrite au contrat, n'est pas une formalité — elle a trois
conséquences pratiques qui ont pesé sur tout mon travail.

D'abord, elle rend le volet B **testable indépendamment** : ce qui traverse la
frontière est un format de réponse, pas un état partagé de base de données.

Ensuite, elle rend le volet B **vulnérable à tout défaut de l'interface**. Un
écart de format qui n'aurait été qu'une gêne avec un accès direct à la base
devient bloquant : je n'ai aucun moyen de contournement. Deux des quatre
difficultés détaillées en section 4 relèvent exactement de ce cas.

Enfin, et c'est le point le plus structurant : la frontière est ce qui **garantit
que la détection d'anomalies reste non supervisée**. L'étiquette de vérité
terrain `is_anomaly` n'existe que dans la table brute du Binôme A et n'est
exposée que par un endpoint unique, réservé à l'évaluation. Elle n'apparaît dans
aucune des caractéristiques servies. Le §2.2 du cahier des charges impose une
détection non supervisée ; l'architecture fait que cette contrainte est tenue
**par construction** et non par discipline — j'y reviens au §2.3.

### 1.4. Planning et jalons

| Jalon | Échéance | Objectif | Livrable côté Binôme B |
|---|---|---|---|
| J7 | Fin semaine 1 | Contrat d'interface figé | Analyse exploratoire et décisions de cadrage des modèles |
| J14 | Fin semaine 2 | Pipeline bout-en-bout fonctionnel | Protocole d'évaluation et baselines anomalie / prévision |
| J21 | Fin semaine 3 | Intégration A ↔ B validée | Modèles avancés et tableau de bord lisant l'API |
| J30 | Fin semaine 4 | Plateforme complète et démontrée | Rapport d'évaluation, notice, guide de test, rapport de stage |

---

## 2. Environnement technique

### 2.1. Langages et bibliothèques

| Composant | Technologie | Rôle |
|---|---|---|
| Langage principal | Python 3.13 | Modélisation, évaluation, restitution |
| Manipulation de données | pandas, numpy | Préparation, découpage temporel, agrégations |
| Apprentissage automatique | scikit-learn | Isolation Forest, DBSCAN, autoencodeur (MLP), normalisation |
| Gradient boosting | XGBoost | Prévision multi-horizon |
| Séries temporelles | statsmodels | ARIMA (baseline de référence) |
| Client HTTP | requests | Consommation de l'API du Binôme A |
| Restitution | Streamlit, plotly, matplotlib | Tableau de bord et figures des rapports |
| Tests | pytest | Suite de 60 tests sur les invariants du protocole |
| Export documentaire | pandoc | Génération des livrables Word depuis le Markdown |
| Conteneurisation | Docker & Docker Compose | Déploiement du tableau de bord dans la stack commune |

Le choix de **Streamlit** plutôt que d'un framework web complet se justifie par
le périmètre : le livrable est un outil de supervision destiné à un exploitant,
pas une application à mettre en production. Streamlit permet de produire un
tableau de bord à six onglets, incluant un rafraîchissement temps réel, sans
écrire de code front-end — ce qui a laissé le temps disponible à la modélisation.

### 2.2. Architecture du volet B

Le code du Binôme B est organisé en quatre couches, chacune ne dépendant que de
la précédente.

- **`src/data/`** — l'accès aux données. `api_client.py` est le client HTTP,
  `local_source.py` la source de repli hors ligne, `loader.py` la façade qui
  choisit entre les deux. Aucune autre couche ne sait d'où viennent les données.
- **`src/features/`** — la préparation. `preprocessing.py` calcule les
  caractéristiques dérivées propres au Binôme B (écarts à la normale horaire,
  tendances, encodage cyclique de l'heure) et normalise par cellule.
  `splits.py` réalise le découpage temporel et porte les garde-fous anti-fuite.
- **`src/models/`** — la modélisation. `anomaly.py` (quatre détecteurs),
  `forecast.py` (cinq prévisionnistes), `qos_state.py` (règles de seuils du
  contrat appliquées aux valeurs prévues).
- **`src/evaluation/`** et **`src/dashboard/`** — la restitution. Métriques
  ponctuelles et par épisode d'une part, tableau de bord de l'autre.

Les **scripts** de `src/scripts/` orchestrent ces couches : chaque livrable du
stage est produit par une commande reproductible, jamais à la main. Le rapport
d'analyse exploratoire, le rapport d'évaluation, les figures, le schéma
d'architecture et les exports Word sont tous **générés** — ce qui garantit qu'ils
ne peuvent pas se désynchroniser des chiffres qu'ils citent.

Au total, le volet B représente environ **7 600 lignes de Python** : 28 modules
sous `src/` et une suite de 60 tests automatisés.

### 2.3. La frontière A ↔ B : une contrainte tenue par un seul fichier

Le contrat interdit au Binôme B tout accès direct à la base et tout import de
code du Binôme A. Cette règle ne se vérifie pas par relecture : elle se vérifie
en constatant qu'un seul fichier du volet B, `src/data/api_client.py`, contient
un appel réseau, et qu'aucun ne contient de SQL ni d'import depuis `binome-a/`.

La même logique structurelle protège la contrainte de non-supervision. Les
méthodes `fit()` des quatre détecteurs ont pour signature `fit(self, df)` : elles
**n'acceptent aucun argument d'étiquettes**. Il n'est donc pas possible
d'entraîner un détecteur sur `is_anomaly` sans modifier l'interface des classes
— ce qui rend l'infraction visible dans un diff, et non enfouie dans une ligne de
code. La vérité terrain n'est chargée que par les scripts d'évaluation, après
l'entraînement, et n'est jamais transmise aux modèles.

Ce choix de conception est le plus important du volet B. C'est lui qui rend le
résultat défendable : l'évaluation mesure ce qu'un modèle qui n'a jamais vu
d'étiquette parvient à détecter, ce qui est précisément la question posée par le
cahier des charges.

### 2.4. Une source de données double, pour ne pas dépendre d'un service tiers

Le volet B consomme l'API du Binôme A. Mais un consommateur dont tout le travail
s'arrête quand le producteur redémarre son service ne peut pas avancer à un
rythme régulier sur quatre semaines. J'ai donc implémenté une **source de repli
hors ligne**.

`local_source.py` recalcule les caractéristiques à partir des CSV bruts, en
réimplémentant les règles documentées du Binôme A — ré-échantillonnage à la
minute, interpolation bornée, fenêtres glissantes — **sans importer leur code**,
ce qui aurait violé la frontière. La façade `loader.py` choisit automatiquement :
API si elle répond, CSV local sinon, avec un mode forçable par variable
d'environnement.

Cette réimplémentation posait un risque évident : deux implémentations des mêmes
règles divergent en général, et une divergence silencieuse aurait invalidé toute
comparaison entre les résultats obtenus en ligne et hors ligne. J'ai donc vérifié
l'équivalence explicitement, en comparant colonne par colonne les 43
caractéristiques servies par les deux sources sur la même période. **L'écart
maximal relevé est nul** sur l'ensemble des colonnes. La source locale est donc
un substitut exact, et non une approximation.

Le bénéfice pratique a dépassé la simple continuité de travail : la suite de
tests et les scripts d'entraînement tournent sans base, sans API et sans Docker,
en quelques secondes. C'est ce qui a rendu possible la campagne d'optimisation du
§5.6, qui a nécessité plusieurs dizaines d'entraînements successifs.

### 2.5. Méthodologie de travail et outils collaboratifs

Le travail a suivi un rythme hebdomadaire calé sur les quatre jalons du projet.

- **Git / GitHub** : une branche par fonctionnalité, nommée `binome-b/<sujet>`,
  fusionnée sur la branche principale après validation. Les conflits
  d'intégration avec le Binôme A ont été traités explicitement, notamment sur le
  `docker-compose.yml` commun (§4 du rapport du Binôme A, et §3.3 ci-dessous).
- **Documents écrits comme canal de communication technique.** Les deux binômes
  ne travaillant pas en présence continue, les réserves techniques ont été
  formalisées par écrit dans le dépôt plutôt que transmises oralement : le
  document `reports/retours_au_binome_a.md` recense les six points relevés
  pendant l'intégration, chacun avec son symptôme, son diagnostic chiffré, la
  correction attendue et le contournement appliqué en attendant. Cette formalisation
  a un coût de rédaction, mais elle a deux vertus : elle rend la réserve
  vérifiable par un tiers (chaque point est reproductible par une commande), et
  elle documente le contournement, ce qui évite qu'il soit retiré par erreur une
  fois le défaut oublié.
- **Livrables générés, jamais rédigés à la main** pour tout ce qui cite des
  chiffres. Un rapport rédigé manuellement se périme dès la première
  ré-exécution des modèles ; un rapport généré ne peut pas mentir sur ses propres
  métriques.
- **Tests automatisés sur les invariants du protocole**, et non sur le code en
  général. La suite de 60 tests ne cherche pas la couverture : elle verrouille
  les propriétés dont la violation serait **silencieuse** — absence de fuite
  temporelle, purge effective du découpage, alignement des cibles de prévision
  par durée et non par position, convention de signe des scores de détection.
  Une régression sur l'une de ces propriétés ne provoquerait aucune erreur, mais
  produirait des métriques flatteuses et fausses. C'est le seul type de bug
  qu'aucune relecture ne rattrape.

---

## 3. Déroulement du stage semaine par semaine

### 3.1. Semaine 1 (J1–J7) — Contrat d'interface et analyse exploratoire

La première semaine a porté sur deux objectifs : contribuer à la définition du
contrat d'interface du point de vue du consommateur, puis produire l'analyse
exploratoire qui devait décider du cadrage des modèles.

**Travaux réalisés**

- Relecture critique du contrat d'interface proposé par le Binôme A, du point de
  vue du consommateur : formulation d'une demande de caractéristique
  supplémentaire (maximum glissant horaire de la charge de cellule, nécessaire
  pour situer une charge instantanée dans son contexte), et vérification que la
  vérité terrain était bien isolée dans un endpoint dédié.
- Mise en place de la couche d'accès aux données : client HTTP paginé, source de
  repli hors ligne, façade de sélection (§2.4).
- Production de l'analyse exploratoire complète (`reports/rapport_eda.md`) :
  conformité du flux servi au contrat, statistiques descriptives par indicateur,
  séparabilité normal / anomalie, saisonnalité, corrélations, autocorrélation,
  et validation des seuils QoS figés.

**Jalon J7**

Le contrat d'interface a été figé en version 1.1 le 10 août 2026. L'analyse
exploratoire a été livrée, avec un tableau de décisions de cadrage justifiant
chaque choix de modélisation par une observation chiffrée. Deux réserves ont été
transmises au Binôme A, dont le déséquilibre des seuils QoS (§5.1).

### 3.2. Semaine 2 (J8–J14) — Protocole d'évaluation et baselines

La deuxième semaine a été consacrée à ce qui devait précéder toute modélisation :
un protocole d'évaluation à l'épreuve de la fuite de données.

Ce choix d'ordre mérite d'être justifié, car il est contre-intuitif. Il aurait été
plus rapide d'entraîner un premier modèle et d'en regarder les métriques. Mais sur
des séries temporelles, un découpage naïf produit des scores excellents et faux :
une caractéristique calculée sur une fenêtre glissante de 60 minutes contient de
l'information sur les 60 minutes qui suivent son horodatage, si bien qu'un point
d'entraînement situé juste avant la frontière de découpage renseigne le segment de
test. Le modèle est alors évalué sur des données qu'il a partiellement vues. Rien
dans le résultat ne le signale — au contraire, il est meilleur.

**Travaux réalisés**

- **Découpage temporel par cellule avec purge.** Le découpage est chronologique
  (60 % entraînement, 20 % validation, 20 % test) et appliqué cellule par
  cellule, avec une **zone de purge de 60 minutes** retirée de part et d'autre de
  chaque frontière — exactement la longueur de la plus longue fenêtre glissante
  présente dans les caractéristiques du Binôme A. Un test automatisé vérifie que
  le dernier horodatage d'entraînement précède le premier de test d'au moins
  cette durée, pour chaque cellule.
- **Garde-fous levant des exceptions explicites.** `LeakageError` est levée si un
  ordre chronologique est violé ; `LabelAlignmentError` si le taux
  d'appariement de la vérité terrain aux caractéristiques passe sous 50 %. Ce
  second garde-fou s'est révélé décisif dès la semaine suivante (§4.1).
- **Métriques adaptées au déséquilibre.** Le taux d'anomalie mesuré est de
  **1,28 %**. Un modèle prédisant « jamais d'anomalie » atteindrait donc 98,7 %
  d'exactitude — l'*accuracy* est inutilisable. L'évaluation repose sur
  précision, rappel, F1 et surtout **PR-AUC**, qui est la seule métrique
  indépendante du seuil qui reste informative à cette prévalence.
- **Métriques par épisode.** Un exploitant ne consomme pas des points de mesure
  isolés mais des incidents. J'ai donc ajouté un jeu de métriques au niveau de
  l'épisode : rappel par épisode, délai médian de détection, et nombre de fausses
  alertes par heure. Ce sont ces trois chiffres qui décrivent l'expérience réelle
  d'un opérateur, bien plus que le F1 ponctuel.
- **Quatre baselines de détection** (seuils du contrat, Isolation Forest, DBSCAN,
  autoencodeur) et **quatre baselines de prévision** (persistance, moyenne
  mobile, naïf saisonnier, ARIMA), toutes évaluées selon le même protocole.

**Jalon J14**

Le protocole d'évaluation et les huit baselines ont été livrés et documentés. Le
détail figure aux §1 et §2 de `reports/rapport_evaluation_modeles.md`.

### 3.3. Semaine 3 (J15–J21) — Modèles avancés, tableau de bord, intégration

Cette semaine a porté sur les modèles avancés, la restitution, et le premier test
réel de l'intégration avec le Binôme A — qui a révélé les deux défauts
d'interface les plus sérieux du stage.

**Modèles avancés**

- **Autoencodeur** (perceptron multicouche entraîné à reconstruire le vecteur de
  caractéristiques, score = erreur de reconstruction), réglé par recherche sur
  grille en validation.
- **XGBoost multi-horizon** en approche directe : un modèle par couple
  (indicateur, horizon), soit quinze modèles pour cinq indicateurs à 5, 15 et 30
  minutes. L'approche directe évite l'accumulation d'erreur d'une prévision
  récursive.

**Tableau de bord**

Six onglets : vue d'ensemble, temps réel, KPI & anomalies, prévision, qualité des
modèles, intégration. Le rafraîchissement temps réel utilise un fragment
Streamlit qui ne recharge que la zone concernée, et non la page entière — sans
quoi chaque rafraîchissement relancerait le chargement de tout l'historique.

**Intégration A ↔ B, et les difficultés qu'elle a révélées**

C'est ici que sont apparus les problèmes détaillés en section 4 : un endpoint
d'évaluation qui renvoyait des métriques nulles sans lever d'erreur (§4.1) et une
pagination silencieusement tronquée (§4.2). S'y est ajouté un défaut de
configuration Docker — la variable d'environnement transmise au conteneur du
tableau de bord ne portait pas le nom lu par mon code, si bien que le tableau de
bord basculait en mode dégradé sans message explicite. Ce dernier point a été
corrigé dans le `docker-compose.yml` fusionné, avec un commentaire dans le
fichier pour prévenir la régression ; il est également documenté au §4.2 du
rapport du Binôme A.

**Jalon J21**

L'intégration a été validée sur la stack Docker complète : le tableau de bord lit
l'API du Binôme A en conditions réelles, y compris le flux quasi temps réel.

### 3.4. Semaine 4 (J22–J30) — Optimisation, restitution, documentation

La dernière semaine a été consacrée à une question posée pendant la revue
d'avancement : les modèles ont-ils été optimisés, et si le modèle retenu
n'atteint pas 90 à 100 % de performance, peut-on le justifier ?

Cette question a orienté tout le travail de la semaine, et a produit le résultat
méthodologique le plus instructif du stage (§4.4 et §5.6).

**Travaux réalisés**

- **Campagne d'optimisation** de la détection : 30 configurations explorées sur
  deux espaces de caractéristiques, avec mesure du **bruit dû à la graine
  aléatoire** comme contrôle — étape qui a invalidé le gain apparent.
- **Campagne d'optimisation** de la prévision : 8 configurations, et sélection
  automatique de la fonction de perte par indicateur et par horizon.
- **Borne oracle supervisée** : entraînement d'un modèle *ayant accès aux
  étiquettes*, non déployé et non sauvegardé, dans le seul but de chiffrer le
  plafond atteignable et donc le prix de la contrainte non supervisée.
- **Refonte du tableau de bord** sur quatre défauts d'ergonomie identifiés en
  revue : contrôles globaux remontés au-dessus des onglets, sélecteur de cellule
  rendu accessible aux onglets temps réel et prévision, sélecteur de modèle de
  prévision ajouté par symétrie avec celui des détecteurs, et affichage explicite
  de la provenance des données de chaque onglet.
- **Livrables documentaires** : rapport d'évaluation des modèles (695 lignes, six
  figures), notice d'utilisation du tableau de bord, guide de test en cinq
  niveaux, document de retours au Binôme A, schéma d'architecture en six couches
  généré par script, et export Word de l'ensemble.

**Jalon J30**

La plateforme est complète et démontrable. Le tableau de bord lit l'API,
les modèles retenus sont entraînés et évalués selon un protocole documenté, et
chaque chiffre cité dans les rapports est reproductible par une commande.

### 3.5. Reproductibilité et documentation de vérification

Une part du travail de fin de stage a consisté à rendre les résultats
vérifiables par un tiers, ce qui est une exigence différente de « le code
fonctionne ».

J'ai rédigé un **guide de test en cinq niveaux** (`binome-b/GUIDE_TEST.md`), de
la vérification la plus rapide à la plus complète : suite de tests automatisés
sans dépendance externe (2 secondes), chaîne de modélisation hors ligne, chaîne
complète contre l'API, tableau de bord, et enfin vérification de l'intégration
sur la stack Docker. Chaque étape indique **la valeur attendue**, ce qui permet à
un lecteur de constater un écart plutôt que de simplement observer que la
commande s'est terminée.

Ce document a une valeur propre : il transforme la connaissance acquise en
débogage — quels chiffres doivent apparaître, lesquels signalent un problème — en
une procédure utilisable par quelqu'un qui reprendrait le projet.

---

## 4. Difficultés techniques rencontrées et résolutions

Cette section détaille quatre difficultés. Elles ont été conservées en détail car
elles constituent la partie la plus formatrice du stage, et parce qu'elles
partagent un trait commun : **aucune ne provoquait d'erreur**. Chacune produisait
un résultat plausible et faux. C'est, à mon sens, la classe de bug la plus
dangereuse en apprentissage automatique, où l'on n'a généralement pas d'intuition
préalable du résultat correct.

### 4.1. Un endpoint d'évaluation qui renvoie zéro sans lever d'erreur

**Symptôme**

Au premier branchement de la chaîne d'évaluation sur l'API du Binôme A, toutes
les métriques de détection sont tombées à zéro — précision, rappel, F1, PR-AUC.
Aucune exception, aucun avertissement. La prévalence mesurée dans le segment de
test affichait **0,00 %**, alors que l'analyse exploratoire menée sur les CSV
avait établi un taux d'anomalie de 1,28 %.

**Diagnostic**

L'endpoint `GET /api/v1/eval/labels`, seul point d'accès à la vérité terrain,
sert les horodatages de la table **brute**, non ré-échantillonnés : `20:21:41`.
Les endpoints `/kpi/history` et `/features`, eux, servent la grille
ré-échantillonnée à la minute pleine : `20:21:00`.

La jointure des étiquettes sur les caractéristiques se fait par la clé
`(ts, cell_id)`. Avec des horodatages à la seconde d'un côté et à la minute de
l'autre, **aucune ligne ne s'apparie**. La jointure réussit, retourne le bon
nombre de lignes, et ne contient que des valeurs manquantes dans la colonne
d'étiquettes. Traitées comme « pas une anomalie », elles produisent un jeu de
test où rien n'est anormal — d'où une prévalence nulle et des métriques nulles,
en silence.

Ce défaut est particulièrement pernicieux parce qu'il touche **l'endpoint
d'évaluation** : son unique raison d'être est de permettre de mesurer, et son
format le rend inutilisable pour mesurer. Un consommateur moins méfiant aurait pu
conclure que ses modèles ne détectaient rien.

**Résolution**

Trois actions, dans cet ordre.

D'abord un **contournement** dans `loader.load_labels()` : réalignement des
horodatages sur la grille à la minute par troncature, puis agrégation par cellule
et par minute avec l'opérateur `max` — si l'une des mesures d'une minute est
anormale, la minute est anormale. Cette convention est conservatrice et
documentée.

Ensuite un **garde-fou**, parce qu'un contournement peut cesser de fonctionner si
le format amont change à nouveau. `splits.align_labels()` calcule le taux
d'appariement et lève `LabelAlignmentError` s'il descend sous 50 %. Le mode
d'échec silencieux devient un mode d'échec bruyant : c'est le seul changement qui
garantisse qu'on ne publiera plus jamais de métriques calculées sur des
étiquettes absentes.

Enfin une **réserve écrite** au Binôme A, avec la commande permettant de
reproduire le constat en deux appels HTTP.

**Ce que j'en retiens**

Un système d'apprentissage n'a pas de bon sens : il ne remarque pas qu'un jeu de
test sans aucune anomalie est absurde. La détection de l'absurde doit donc être
programmée explicitement, sous forme d'assertions sur les invariants attendus des
données. Le garde-fou de 50 % a coûté quinze lignes ; sans lui, tout résultat de
ce rapport aurait dépendu de ma vigilance à relire une prévalence.

### 4.2. Une pagination silencieusement tronquée

**Symptôme**

Après correction du défaut précédent, la prévalence remontait mais restait trop
faible, et le volume d'étiquettes chargées plafonnait à **5 000 lignes** au lieu
des 100 800 attendues.

**Diagnostic**

Le contrat d'interface définit une enveloppe de réponse commune, incluant pour
les endpoints paginés les champs `limit`, `offset`, `total` et `has_more`. Mon
client HTTP déroulait la pagination en s'arrêtant lorsque `has_more` valait faux.

L'endpoint `/eval/labels` accepte bien `limit` et `offset`, mais **omet les
quatre champs de pagination de son enveloppe**. En l'absence de `has_more`, mon
client interprétait l'absence comme un « plus rien à lire » et s'arrêtait après
la première page — soit 5 % des étiquettes, sans erreur.

**Résolution**

Le client a été rendu robuste à l'absence de ces champs : si `has_more` est
présent, il fait foi ; sinon, le client continue **tant que la page reçue est
pleine** et s'arrête à la première page incomplète. Cette heuristique est
correcte dans tous les cas sauf celui, sans conséquence, où le total est un
multiple exact de la taille de page — un appel supplémentaire renvoyant une page
vide.

Le défaut a été signalé au Binôme A comme le précédent.

**Ce que j'en retiens**

Un client qui consomme une interface qu'il ne contrôle pas ne doit pas supposer
que le contrat est respecté : il doit se comporter correctement quand il ne l'est
pas, et le signaler. La difficulté ici n'était pas technique — la correction
tient en cinq lignes — mais de **méthode de diagnostic** : c'est la comparaison
d'un volume mesuré à un volume attendu qui a révélé le problème, pas la lecture
du code.

### 4.3. XGBoost battu par la persistance : un problème de perte, pas de modèle

**Symptôme**

Le modèle avancé de prévision, XGBoost multi-horizon avec ses paramètres par
défaut, était **battu par la persistance** — la baseline la plus naïve possible,
qui prédit simplement que la valeur future égalera la valeur actuelle. Sur le
taux de perte de paquets, l'erreur absolue moyenne était supérieure de 45 % à
celle de la persistance, avec un biais positif marqué.

Un modèle à gradient boosting entraîné sur 43 caractéristiques battu par « la
valeur ne changera pas » : le résultat était trop mauvais pour être un simple
défaut de réglage.

**Diagnostic**

La distribution du taux de perte de paquets est extrêmement asymétrique :
médiane 0,63 %, 99ᵉ centile 1,22 %, maximum **79,6 %**, coefficient d'asymétrie
28,3. Autrement dit, la variable est presque toujours très basse et
occasionnellement énorme.

L'objectif d'apprentissage par défaut de XGBoost est l'**erreur quadratique**.
Une perte quadratique pénalise une erreur de 20 points quatre cents fois plus
qu'une erreur d'un point. Sur cette distribution, le modèle minimise donc sa
perte en se préparant aux pics rares — il surestime systématiquement le régime
normal, qui représente l'immense majorité des points.

Or la métrique d'évaluation, imposée par le cahier des charges, est l'erreur
**absolue** moyenne, qui pénalise linéairement. Le modèle optimisait donc une
quantité différente de celle sur laquelle il était jugé. Le problème n'était ni
le modèle, ni ses hyperparamètres, mais **le désaccord entre la perte
d'entraînement et la métrique d'évaluation**.

**Résolution**

J'ai rendu l'objectif d'apprentissage **sélectionnable par validation**, au même
titre qu'un hyperparamètre : pour chaque couple (indicateur, horizon), les deux
objectifs sont entraînés et celui qui minimise l'erreur absolue en validation est
retenu. Le résultat est net et systématique — l'objectif absolu gagne sur
**les quinze couples**, avec un écart d'autant plus grand que la distribution est
asymétrique :

| Indicateur | Asymétrie | MAE, perte quadratique | MAE, perte absolue | Gain |
|---|---|---|---|---|
| `packet_loss` | 28,3 | 0,4345 | 0,2526 | **−41,9 %** |
| `latency` | 12,6 | 1,4354 | 1,0398 | **−27,6 %** |
| `jitter` | 6,6 | 0,3672 | 0,2860 | −22,1 % |
| `throughput` | 0,5 | 3,1018 | 2,8696 | −7,5 % |
| `cell_load` | −0,04 | 3,9443 | 3,9251 | −0,5 % |

*(horizon 30 minutes ; erreur absolue moyenne mesurée en validation)*

La corrélation entre l'asymétrie de l'indicateur et le gain apporté par le
changement de perte confirme le mécanisme : le désaccord ne coûte presque rien
sur une variable symétrique comme la charge de cellule, et coûte 42 % sur la plus
asymétrique.

Une fois l'objectif corrigé, XGBoost devance la persistance de 10,0 %, 14,6 % et
20,7 % d'erreur absolue à 5, 15 et 30 minutes.

**Ce que j'en retiens**

C'est le résultat dont je retire le plus. Le réflexe devant un modèle décevant
est de régler ses hyperparamètres ; ici, aucun réglage n'aurait comblé l'écart,
parce que le modèle résolvait correctement un problème qui n'était pas le bon. La
question à se poser en premier n'est pas « quels paramètres ? » mais **« le
modèle optimise-t-il ce que je mesure ? »**. Le gain obtenu en changeant une
seule ligne dépasse de plus d'un ordre de grandeur tout ce que la campagne
d'optimisation des hyperparamètres a produit.

### 4.4. Un gain d'optimisation qui n'existait pas

**Symptôme**

La campagne d'optimisation de la détection a exploré 30 configurations. La
meilleure améliorait la PR-AUC en validation de **0,6049 à 0,6287, soit +3,93 %**.
Un gain modeste mais net, qu'il aurait été naturel de retenir et d'annoncer.

**Diagnostic**

Avant de conclure, j'ai mesuré une quantité que la recherche d'hyperparamètres
ignore habituellement : la **variabilité due à la seule graine aléatoire**. Le
même modèle, avec exactement les mêmes hyperparamètres, entraîné six fois avec
six graines différentes.

Résultat : à 300 arbres, la PR-AUC varie de **0,0909** entre la meilleure et la
pire graine, avec un écart-type de 0,0315.

L'écart entre la configuration « optimisée » et la configuration initiale est de
**0,0238**. Le bruit de la graine est donc **près de quatre fois plus grand que
le gain mesuré**. Le « +3,93 % » n'était pas un gain : c'était une graine
chanceuse, sélectionnée par une recherche qui n'avait aucun moyen de distinguer
les deux. Retenir cette configuration aurait consisté à publier du bruit comme un
résultat.

**Résolution**

Le constat a réorienté l'objectif. Puisqu'il n'y avait pas de gain à prendre sur
la position dans l'espace des hyperparamètres, le seul progrès accessible était
de **réduire la variance** — rendre le résultat reproductible plutôt que
d'optimiser une valeur instable.

| Nombre d'arbres | PR-AUC moyenne | Écart-type | Étendue sur 6 graines |
|---|---|---|---|
| 300 | 0,5727 | 0,0315 | 0,0909 |
| 1 000 | 0,5945 | 0,0127 | 0,0317 |
| **2 000** | **0,5984** | **0,0053** | **0,0153** |

Augmenter le nombre d'arbres de 300 à 2 000 divise l'écart-type par six et
améliore légèrement la moyenne. Le modèle retenu utilise donc 2 000 arbres — non
pour être meilleur, mais pour que sa performance ne dépende plus du hasard de
l'initialisation. Les trois lignes de ce tableau figurent en commentaire dans le
code, à côté de la valeur du paramètre, afin que le choix reste justifié pour un
lecteur ultérieur.

**Ce que j'en retiens**

Une recherche d'hyperparamètres sans mesure du bruit de fond ne sélectionne pas
le meilleur modèle : elle sélectionne la meilleure graine. Un écart doit être
comparé à la variabilité de la mesure avant d'être interprété comme un effet.
C'est une exigence élémentaire de méthode expérimentale, et c'est probablement
l'apprentissage le plus transférable de ce stage — il vaut pour toute
comparaison de modèles, indépendamment du domaine.

---

## 5. Résultats obtenus

### 5.1. Analyse exploratoire : ce qu'elle a décidé

L'analyse exploratoire porte sur **100 800 mesures**, 5 cellules, 14 jours, sans
valeur nulle résiduelle et sans écart au contrat détecté. Elle a produit trois
résultats qui ont orienté toute la modélisation.

**Les indicateurs sont très inégalement discriminants.** L'écart des moyennes
entre régime normal et régime anormal, exprimé en écarts-types du régime normal :

| Indicateur | Moyenne normale | Moyenne en anomalie | Séparabilité |
|---|---|---|---|
| `packet_loss` | 0,626 % | 7,234 % | **28,1 σ** |
| `latency` | 15,79 ms | 38,31 ms | 5,53 σ |
| `jitter` | 4,41 ms | 8,28 ms | 4,39 σ |
| `throughput` | 94,7 Mbit/s | 70,9 Mbit/s | 1,08 σ |
| `cell_load` | 64,8 % | 67,3 % | 0,10 σ |

La charge de cellule, à 0,10 σ, n'est **pas** discriminante prise isolément —
alors qu'elle est l'indicateur auquel un exploitant penserait d'abord. Elle
n'apporte du signal qu'en interaction avec les autres, ce qui justifie un modèle
multivarié plutôt qu'un jeu de seuils indépendants.

**Les seuils du contrat sont déséquilibrés.** Appliqués avec la règle
d'agrégation prévue — l'état global est celui du pire indicateur — les seuils
figés en v1.1 déclarent l'état **critique 43,1 % du temps** et « bon » seulement
**8,3 %**. Une plateforme de supervision qui alerte quatre jours sur dix ne
transmet aucune information.

Le mécanisme est arithmétique et vaut d'être détaillé, car il illustre un piège de
conception. Chaque indicateur, pris isolément, est classé « bon » entre 26 % et
82 % du temps selon l'indicateur — ce qui est raisonnable. Mais la règle du pire
indicateur exige que **les cinq soient simultanément bons**. Si les indicateurs
étaient indépendants, la part de temps « bon » global tomberait à 1,27 % ; on en
observe 8,33 %, l'écart venant de la corrélation entre indicateurs qui regroupe
partiellement les dégradations sur les mêmes instants.

Autrement dit, **les seuils ont été calibrés indicateur par indicateur, sans
tenir compte de la règle qui les combine**. Chaque seuil est défendable seul ;
leur conjonction ne l'est pas. Deux seuils sont principalement en cause : le
minimum de débit en « bon » (107 Mbit/s, atteint 25,8 % du temps) et le maximum
de gigue (4,0 ms, 36,2 % du temps).

**Position adoptée** : le contrat v1.1 est gelé, et le respecter est identifié
comme facteur de réussite n°1 du projet. Le Binôme B ne l'a donc **pas modifié**.
Les seuils servis par l'API restent la référence dans tout le code, y compris là
où ils produisent un résultat que je juge inexploitable. Le diagnostic chiffré a
été transmis au Binôme A avec deux options de révision, et le tableau de bord
expose le déséquilibre pour que la discussion se tienne sur des chiffres. C'est,
je crois, la conduite correcte face à un contrat que l'on juge perfectible mais
que l'on a accepté : documenter, pas contourner.

**Les seuils ne remplacent pas un détecteur.** Le croisement de l'état QoS avec
la vérité terrain le montre :

| État par seuils | Instants normaux | Instants anormaux |
|---|---|---|
| bon | 8,4 % | 0,9 % |
| dégradé | 49,0 % | 13,4 % |
| critique | **42,5 %** | 85,8 % |

Deux lectures. D'une part, 14,2 % des anomalies réelles ne sont **pas** classées
critique : ce sont les anomalies de forme, invisibles à un seuil d'amplitude.
D'autre part, 42,5 % des instants **normaux** le sont : l'immense majorité des
alertes seraient fausses.

La classification par seuils et la détection apprise sont donc deux fonctions
**complémentaires et non redondantes** : la première qualifie l'état
d'exploitation au sens du contrat de service, la seconde signale l'atypique.
C'est ce résultat qui justifie l'existence du travail de modélisation.

### 5.2. Détection d'anomalies

Quatre détecteurs, évalués sur le même segment de test — **19 850 points**,
prévalence 1,51 %, 9 épisodes d'anomalie — au point de fonctionnement choisi sans
recours aux étiquettes.

| Détecteur | Précision | Rappel | F1 | PR-AUC | Fausses alertes / h | Épisodes détectés |
|---|---|---|---|---|---|---|
| Seuils du contrat | 0,026 | 0,703 | 0,051 | 0,023 | 0,553 | 9 / 9 |
| **Isolation Forest** | **0,616** | **0,647** | **0,631** | **0,586** | **0,018** | **9 / 9** |
| DBSCAN | 0,277 | 0,187 | 0,223 | 0,391 | 0,018 | 4 / 9 |
| Autoencodeur | 0,383 | 0,397 | 0,390 | 0,363 | 0,003 | 8 / 9 |

**Isolation Forest est le modèle retenu.** Il domine sur les deux métriques
décisives, F1 et PR-AUC, et surtout sur celle qui compte pour un exploitant : il
produit **0,018 fausse alerte par heure**, soit environ une tous les deux jours,
là où les seuils du contrat en produisent 0,55 — trente fois plus. Il détecte
les 9 épisodes sur 9, avec un délai médian de 13,5 minutes.

Deux résultats méritent d'être soulignés, car ils vont contre l'attente.

**Le modèle avancé ne bat pas la baseline.** L'autoencodeur, pourtant le modèle
le plus sophistiqué des quatre, obtient une PR-AUC de 0,363 contre 0,586 pour
Isolation Forest. Conformément au §8.2 du cahier des charges, qui impose de
comparer tout modèle avancé à une baseline et de ne déployer que ce qui apporte un
gain démontré, **il n'est pas déployé**. Ce non-résultat est un résultat : sur
23 caractéristiques et un régime normal bien échantillonné, l'hypothèse
géométrique d'Isolation Forest — les anomalies sont isolables par peu de
coupes aléatoires — est mieux adaptée que l'apprentissage d'une variété de
reconstruction.

**Le classement dépend du point de fonctionnement.** DBSCAN passe de F1 = 0,223
au point d'exploitation à F1 = 0,624 au point optimal — un rapport de près de
trois. Cet écart mesure la sensibilité du détecteur au choix du seuil, et c'est
une propriété opérationnelle en soi : un détecteur dont la performance s'effondre
si le seuil est mal choisi est un mauvais candidat au déploiement, même si son
optimum est bon. Isolation Forest, lui, varie de 0,631 à 0,635 — il est
pratiquement insensible à ce choix, ce qui est une seconde raison de le retenir.

### 5.3. Prévision des KPI

Cinq modèles, cinq indicateurs, trois horizons. Comparaison à la persistance, en
gain d'erreur absolue moyenne :

| Horizon | Modèle retenu | Gain d'erreur absolue vs persistance |
|---|---|---|
| 5 min | XGBoost | **−10,0 %** |
| 15 min | XGBoost | **−14,6 %** |
| 30 min | XGBoost | **−20,7 %** |

Le gain **croît avec l'horizon**, ce qui est le comportement attendu et une
validation indirecte du modèle : à 5 minutes, la valeur actuelle est déjà une
excellente prédiction et il reste peu à gagner ; à 30 minutes, elle se dégrade et
la structure apprise — saisonnalité, corrélations entre indicateurs,
non-linéarités — prend le dessus.

ARIMA a été évalué comme baseline de référence, sur un sous-ensemble de 600
origines de prévision communes à tous les modèles pour garantir la
comparabilité. Prophet et LSTM ont été écartés par choix de périmètre explicite,
et non par impossibilité technique : le gain attendu ne justifiait pas le temps
d'entraînement au regard du calendrier, ce qui est documenté au §4 du rapport
d'évaluation.

### 5.4. De la prévision à la décision : l'état QoS annoncé

Prévoir un indicateur n'a d'intérêt que si l'exploitant peut en tirer une
décision. J'ai donc ajouté une couche qui applique les seuils du contrat aux
**valeurs prévues**, produisant un état QoS annoncé à 5, 15 et 30 minutes — ce
qui transforme cinq courbes en une information actionnable : *l'état va-t-il se
dégrader ?*

| Horizon | Exactitude de l'état | Part des états critiques manqués |
|---|---|---|
| 5 min | 82,1 % | 14,2 % |
| 15 min | 82,3 % | 13,9 % |
| 30 min | 82,1 % | 14,7 % |

L'exactitude est remarquablement **stable de 5 à 30 minutes**. Ce n'est pas
attendu : l'erreur de prévision, elle, croît avec l'horizon. L'explication est
que la classification en trois états est robuste à une petite erreur numérique —
tant que la valeur prévue reste du bon côté du seuil, une erreur de prévision est
sans conséquence sur la décision. La conséquence pratique est favorable :
l'annonce à 30 minutes est aussi fiable que celle à 5 minutes, et laisse dix fois
plus de temps pour agir.

La part d'états critiques manqués, autour de 14 %, est le chiffre à surveiller :
c'est la proportion de dégradations réelles que l'annonce n'a pas vues venir.

### 5.5. Le tableau de bord

Six onglets, alimentés par l'API du Binôme A avec repli automatique sur les CSV
locaux si elle est indisponible :

- **Vue d'ensemble** — état QoS courant par cellule, alertes actives, volumétrie ;
- **Temps réel** — flux quasi temps réel rafraîchi par fragment, avec détection
  appliquée aux mesures qui arrivent ;
- **KPI & anomalies** — séries temporelles par indicateur, points détectés,
  superposition optionnelle de la vérité terrain à des fins de démonstration ;
- **Prévision** — trajectoires prévues à 5 / 15 / 30 minutes et état QoS annoncé,
  avec sélecteur de modèle ;
- **Qualité des modèles** — métriques d'évaluation, courbes précision-rappel,
  matrices de confusion ;
- **Intégration** — provenance des données, disponibilité de l'API, modèles
  chargés. Cet onglet rend l'état de l'intégration A ↔ B visible à
  l'écran plutôt que déductible des logs, ce qui a considérablement accéléré le
  diagnostic des difficultés de la section 4.

Les contrôles communs — cellule, fenêtre temporelle, détecteur, sensibilité —
sont placés **au-dessus** des onglets, de sorte qu'un changement de cellule
s'applique à tous. Le tableau de bord se teste sans navigateur au moyen de
l'utilitaire de test de Streamlit, ce qui permet de vérifier qu'aucun onglet ne
lève d'exception dans le cadre d'une vérification automatisée.

### 5.6. Pourquoi pas 90 à 100 % : le prix mesuré de la contrainte

Le modèle retenu obtient F1 = 0,631 et PR-AUC = 0,586. On attend spontanément
d'un modèle d'apprentissage qu'il atteigne 90 à 100 % ; il faut donc expliquer
l'écart, et l'expliquer avec un chiffre plutôt qu'avec un argument.

J'ai pour cela entraîné un **oracle supervisé** : un modèle ayant accès à
`is_anomaly` pendant son entraînement — ce que le contrat interdit — dans le seul
but de mesurer le plafond. Ce modèle n'est ni déployé, ni sauvegardé, ni utilisé
par le tableau de bord ; il ne sert qu'à cette mesure, et son fichier de
résultats porte cet avertissement.

| Modèle | PR-AUC | Précision | Rappel | F1 |
|---|---|---|---|---|
| Isolation Forest (non supervisé, retenu) | 0,586 | 0,616 | 0,647 | 0,631 |
| Oracle supervisé (interdit, non déployé) | **0,905** | 0,972 | 0,810 | 0,884 |

L'écart, **0,319 de PR-AUC**, est le prix de la contrainte non supervisée. Il
répond précisément à la question : les 90 % attendus sont atteignables sur ces
données — l'oracle les atteint — mais **uniquement avec accès aux étiquettes**.

Cette conclusion est le résultat le plus important de la campagne d'optimisation,
et elle est utile plutôt que défaitiste, pour deux raisons.

D'abord, elle borne l'effort à consacrer au réglage. Puisque l'essentiel de
l'écart aux 90 % vient de la contrainte et non de la configuration du modèle, il
n'y avait rien à gagner à poursuivre la recherche d'hyperparamètres — ce que la
mesure du bruit de graine (§4.4) avait déjà indiqué indépendamment. Deux méthodes
distinctes convergent donc sur le même diagnostic.

Ensuite, elle indique où le progrès se trouve réellement : non dans le modèle,
mais **dans les données**. Le segment de test ne contient que 9 épisodes
d'anomalie, ce qui limite fortement la puissance statistique de toute
comparaison — un épisode manqué fait varier le rappel par épisode de 11 points.
Un jeu de données comportant plus d'épisodes, et une plus grande diversité de
formes d'anomalie, améliorerait la mesure et probablement le modèle bien
davantage que n'importe quel réglage. C'est la recommandation portée au Binôme A.

Enfin, il faut rappeler ce à quoi la comparaison pertinente oppose ce modèle. Le
point de départ opérationnel n'est pas 100 %, c'est le jeu de seuils du contrat,
qui obtient F1 = 0,051 et 0,55 fausse alerte par heure. Le modèle retenu
multiplie le F1 par **douze** et divise les fausses alertes par **trente**, sans
jamais voir une seule étiquette. C'est cela que le stage a produit.

### 5.7. Fonctionnalités livrées

- Une couche d'accès aux données à double source — API du Binôme A ou CSV locaux
  — vérifiée **numériquement équivalente** sur les 43 caractéristiques servies ;
- un protocole d'évaluation à l'épreuve de la fuite temporelle : découpage
  chronologique par cellule, purge de 60 minutes, garde-fous levant des
  exceptions explicites, et 60 tests automatisés verrouillant ces invariants ;
- quatre détecteurs d'anomalies **non supervisés par construction**, dont la
  signature de `fit()` rend l'usage des étiquettes impossible sans modifier
  l'interface ;
- cinq modèles de prévision multi-horizon, avec sélection automatique de la
  fonction de perte par indicateur et par horizon ;
- une couche de décision transformant les prévisions en état QoS annoncé à 5, 15
  et 30 minutes ;
- un tableau de bord Streamlit à six onglets, avec flux temps réel et repli
  automatique hors ligne ;
- un rapport d'évaluation généré de 695 lignes et six figures, un rapport
  d'analyse exploratoire, une notice d'utilisation, un guide de vérification en
  cinq niveaux, et un document de retours techniques au Binôme A ;
- un schéma d'architecture en six couches, **généré par script** à partir des noms
  réels des fichiers et des tables du dépôt ;
- une chaîne d'export Word de l'ensemble des livrables, à partir d'un gabarit de
  style aligné sur celui du contrat d'interface.

---

## 6. Bilan et compétences acquises

### 6.1. Compétences techniques

- **Détection d'anomalies non supervisée** : Isolation Forest, DBSCAN adapté à un
  usage inductif par distance aux points centraux, autoencodeur par erreur de
  reconstruction ; et surtout la **convention de score** et le choix d'un point de
  fonctionnement sans recours aux étiquettes, qui est le vrai problème pratique.
- **Prévision de séries temporelles** : approche multi-horizon directe,
  construction de cibles par jointure temporelle, baselines de référence
  (persistance, moyenne mobile, naïf saisonnier, ARIMA), et **alignement de la
  fonction de perte sur la métrique d'évaluation** (§4.3).
- **Évaluation en contexte de fort déséquilibre** : choix de la PR-AUC plutôt que
  de la ROC-AUC ou de l'exactitude, et conception de métriques par épisode
  correspondant à l'usage réel — rappel par épisode, délai de détection, fausses
  alertes par heure.
- **Prévention de la fuite de données** sur séries temporelles : découpage
  chronologique, dimensionnement de la purge sur la plus longue fenêtre présente
  dans les caractéristiques, et vérification par assertions automatisées.
- **Méthode expérimentale appliquée à l'apprentissage** : mesure du bruit de
  fond avant interprétation d'un écart, arbitrage variance / biais, et usage d'un
  oracle supervisé comme borne supérieure pour chiffrer le coût d'une contrainte
  (§4.4, §5.6).
- **Consommation d'une API REST tierce** : pagination robuste à une enveloppe
  incomplète, séparation des délais d'attente selon la nature de l'appel,
  détection de disponibilité et repli automatique.
- **Restitution** : tableau de bord Streamlit multi-onglets avec rafraîchissement
  temps réel par fragment, et test automatisé de l'application sans navigateur.
- **Reproductibilité documentaire** : génération des rapports depuis les fichiers
  de métriques, export Word par gabarit, et génération du schéma d'architecture
  par script.

### 6.2. Compétences méthodologiques et transversales

- **Travailler en aval d'une interface que l'on ne contrôle pas.** C'est
  l'apprentissage central de ce stage. Consommer une API produite par une autre
  équipe impose une posture particulière : vérifier plutôt que supposer, se
  comporter correctement quand le contrat n'est pas respecté, et signaler l'écart
  par écrit plutôt que le corriger silencieusement.
- **Diagnostiquer un échec silencieux.** Les quatre difficultés de la section 4
  ne levaient aucune erreur. Le stage m'a appris que la première défense contre
  ce type de bug est la comparaison systématique d'une valeur mesurée à une
  valeur attendue — prévalence attendue, volume attendu, sens attendu d'un gain —
  et que ces comparaisons doivent être **programmées**, pas laissées à la
  vigilance.
- **Défendre un résultat, y compris décevant.** Rapporter que le modèle avancé ne
  bat pas la baseline, ou que le F1 plafonne à 0,63, demande de pouvoir expliquer
  *pourquoi* avec des chiffres. La borne oracle et la mesure du bruit de graine
  n'améliorent aucun modèle ; elles rendent le résultat défendable, ce qui a plus
  de valeur qu'un chiffre flatteur non expliqué.
- **Respecter un contrat que l'on juge perfectible.** Le déséquilibre des seuils
  QoS était un défaut réel, dont j'aurais pu corriger l'effet dans mon code. Je ne
  l'ai pas fait : le contrat était gelé, et une correction unilatérale aurait
  produit deux définitions divergentes de l'état QoS entre les deux moitiés de la
  plateforme. La conduite retenue — appliquer, documenter, transmettre un
  diagnostic chiffré avec des options de révision — est celle qui préserve la
  cohérence du système.
- **Communication technique écrite** comme outil de travail et non comme
  formalité, dans un contexte où les deux binômes ne travaillent pas en présence
  continue.
- **Gestion du temps sur un planning contraint** : arbitrages de périmètre
  explicites et documentés (Prophet et LSTM écartés par choix, non par
  impossibilité) plutôt que silencieux.

### 6.3. Limites et pistes d'amélioration

Plusieurs axes ont été identifiés sans pouvoir être menés dans le temps imparti.

- **Densité d'anomalies trop faible.** Neuf épisodes seulement dans le segment de
  test : un épisode manqué déplace le rappel par épisode de 11 points. C'est la
  limite principale de l'évaluation, et le levier de progrès le plus important
  identifié au §5.6 — devant tout raffinement de modèle.
- **Diversité des formes d'anomalie.** Les anomalies du jeu synthétique sont
  majoritairement des dégradations d'amplitude. Les anomalies de forme —
  dérive lente, gigue anormale à charge normale — sont sous-représentées, alors
  que ce sont précisément celles qu'un détecteur appris doit apporter par rapport
  à un seuil.
- **Contraintes amont absorbées mais non résolues.** Les deux défauts de
  l'endpoint d'évaluation sont contournés côté B, non corrigés à la source. Les
  contournements sont documentés et protégés par un garde-fou, mais ils
  subsistent : une correction côté A permettrait de les retirer et de supprimer
  une convention d'agrégation à la minute qui, bien que conservatrice, introduit
  une approximation.
- **Seuils QoS v1.1 non révisés.** L'état critique couvre 43 % du temps. Le
  diagnostic et deux options de révision ont été transmis ; la décision appartient
  au Binôme A, propriétaire de l'endpoint.
- **Modèles avancés non retenus par choix de périmètre.** Prophet et LSTM n'ont
  pas été évalués. Compte tenu du fait que XGBoost devance déjà nettement les
  baselines et que l'essentiel du gain en prévision est venu du choix de la
  fonction de perte, le rendement attendu paraissait faible — mais l'hypothèse
  n'a pas été testée.
- **Réentraînement non automatisé.** Les modèles sont entraînés par commande
  explicite. Une industrialisation demanderait un réentraînement périodique avec
  suivi de la dérive des données, qui sort du périmètre de quatre semaines.

---

## Conclusion

Ce stage de quatre semaines au sein de [NOM DE L'ENTREPRISE] m'a permis de
construire le volet intelligence artificielle et restitution de la plateforme
NetQoS-AI : une chaîne complète allant de la consommation d'une API tierce
jusqu'à un tableau de bord de supervision, en passant par la détection
d'anomalies non supervisée et la prévision des indicateurs de qualité de service.

Le résultat quantitatif tient en une comparaison. Le point de départ opérationnel
— les seuils fixes du contrat — obtient un F1 de 0,051 et déclenche une fausse
alerte toutes les deux heures. Le modèle retenu obtient un F1 de 0,631 et une
fausse alerte tous les deux jours, détecte les neuf épisodes du segment de test,
et n'a jamais vu une seule étiquette d'anomalie. En prévision, le modèle avancé
devance la persistance de 10 à 21 % d'erreur absolue selon l'horizon, et l'état
QoS annoncé est correct dans 82 % des cas, aussi bien à 30 minutes qu'à 5.

Mais l'apprentissage principal de ce stage n'est pas dans ces chiffres. Il est
dans la nature des quatre difficultés rencontrées : **aucune ne provoquait
d'erreur**. Un endpoint d'évaluation dont le format rendait toute mesure nulle,
une pagination qui s'arrêtait à 5 % des données, un modèle qui optimisait autre
chose que ce qu'on mesurait, et un gain d'optimisation qui n'était que du bruit
de graine — chacune produisait un résultat plausible, et trois d'entre elles
auraient produit des métriques *plus flatteuses* que la réalité. C'est la classe
de défaut la plus dangereuse dans un projet d'apprentissage automatique, où l'on
ne dispose généralement pas d'une intuition préalable du résultat correct.

La réponse que j'en ai tirée est méthodologique plutôt que technique : programmer
la détection de l'absurde — garde-fous levant des exceptions, tests verrouillant
les invariants silencieux, comparaison systématique du mesuré à l'attendu — et
mesurer le bruit de fond avant d'interpréter un écart. La borne oracle et la
mesure de variance par graine aléatoire n'ont amélioré aucun modèle ; elles ont
rendu les résultats défendables, ce qui, à la réflexion, était l'objectif.

La position de consommateur dans un projet à deux binômes a été la seconde source
d'apprentissage. Dépendre entièrement d'une interface que l'on ne contrôle pas
impose de vérifier plutôt que de supposer, de fonctionner correctement quand le
contrat n'est pas tenu, et de signaler par écrit plutôt que de corriger en
silence. Le choix de ne pas modifier des seuils que je jugeais pourtant
inexploitables, mais d'en documenter le défaut avec des chiffres et des options de
révision, illustre ce que ce stage m'a appris sur le travail à interfaces
partagées : la cohérence d'un système à plusieurs contributeurs vaut plus qu'une
correction locale, même juste.

Cette expérience conforte mon intérêt pour les métiers de la science des données
appliquée, et particulièrement pour ce qui sépare un modèle qui fonctionne d'un
résultat auquel on peut se fier.

---

## Annexes

### Annexe A — Architecture du volet B et sa place dans la plateforme

Le schéma complet en six couches, généré par script, figure dans le dépôt sous
`reports/architecture_schema.png`. Vue simplifiée du positionnement du Binôme B :

```
                     ┌──────────── Binôme A ────────────┐
   générateur ──> ingestion ──> nettoyage ──> features ──> TimescaleDB
                                                                │
                                                       API FastAPI /api/v1
                                                                │
   ════════════════════ frontière A ↔ B (HTTP seul) ═════════════│════════
                                                                │
                     ┌──────────── Binôme B ────────────┐       │
                              api_client.py <───────────────────┘
                                    │
                              loader.py  (repli : local_source.py)
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              preprocessing     splits.py      evaluation/
                    │          (purge 60 min)   metrics.py
                    ▼
              ┌─────┴─────┬──────────────┐
              ▼           ▼              ▼
          anomaly.py  forecast.py   qos_state.py
              └───────────┴──────────────┘
                          │
                    dashboard/app.py  (6 onglets)
```

La vérité terrain `is_anomaly` ne circule **pas** par ce chemin : elle est
chargée séparément depuis `/eval/labels`, uniquement par les scripts
d'évaluation, et n'atteint jamais les modèles.

### Annexe B — Structure du volet B (extrait)

```
binome-b/
├── src/
│   ├── config.py                  # configuration centralisée
│   ├── data/
│   │   ├── api_client.py          # SEUL point de contact avec le Binôme A
│   │   ├── local_source.py        # source de repli hors ligne
│   │   └── loader.py              # façade auto / api / local
│   ├── features/
│   │   ├── preprocessing.py       # caractéristiques dérivées, normalisation
│   │   └── splits.py              # découpage temporel, garde-fous anti-fuite
│   ├── models/
│   │   ├── anomaly.py             # 4 détecteurs non supervisés
│   │   ├── forecast.py            # 5 prévisionnistes multi-horizon
│   │   └── qos_state.py           # seuils du contrat -> état QoS
│   ├── evaluation/metrics.py      # métriques ponctuelles et par épisode
│   ├── dashboard/app.py           # tableau de bord 6 onglets
│   └── scripts/                   # un livrable = une commande
├── tests/                         # 60 tests sur les invariants du protocole
└── GUIDE_TEST.md                  # vérification en 5 niveaux
```

### Annexe C — Extrait de code : les garde-fous anti-fuite

Extrait de `src/features/splits.py`. Ces deux mécanismes sont la réponse aux
échecs silencieux décrits en section 4.

```python
def temporal_split(df, purge_minutes=60, ...):
    """Découpage chronologique par cellule, avec purge aux frontières.

    La purge vaut la plus longue fenêtre glissante présente dans les
    caractéristiques du Binôme A (60 min) : sans elle, un point
    d'entraînement situé juste avant la frontière renseignerait le
    segment de test.
    """
    ...


def align_labels(features, labels, min_match_rate=MIN_MATCH_RATE):
    """Apparie la vérité terrain aux caractéristiques.

    Lève LabelAlignmentError si le taux d'appariement passe sous 50 %.
    Sans ce contrôle, un désalignement d'horodatages produit un jeu de
    test sans aucune anomalie -- et des métriques nulles sans erreur.
    """
    if labels.empty:
        raise LabelAlignmentError("aucune étiquette servie")
    merged = features.merge(labels, on=["ts", "cell_id"], how="left")
    match_rate = float(merged["is_anomaly"].notna().mean())
    if match_rate < min_match_rate:
        raise LabelAlignmentError(
            f"taux d'appariement {match_rate:.1%} < {min_match_rate:.0%} : "
            "les horodatages des étiquettes ne correspondent pas à ceux "
            "des caractéristiques."
        )
    return merged["is_anomaly"].astype("boolean").fillna(False).astype(bool)
```

### Annexe D — Extrait de code : non-supervision par construction

Extrait de `src/models/anomaly.py`. La signature de `fit()` **n'accepte aucun
argument d'étiquettes** : la contrainte du §2.2 du cahier des charges est tenue
par l'interface, non par la discipline du développeur.

```python
class IsolationForestDetector:
    """Détecteur par isolement. Non supervisé : fit() ne voit pas is_anomaly.

    n_estimators=2000 : choisi pour la stabilité, non pour la moyenne.
    Variance de la PR-AUC mesurée sur 6 graines aléatoires --
          300 arbres : 0,573 ± 0,032  (étendue 0,091)
        1 000 arbres : 0,595 ± 0,013  (étendue 0,032)
        2 000 arbres : 0,598 ± 0,005  (étendue 0,015)
    L'écart entre configurations d'hyperparamètres (0,024) était plus
    petit que le bruit de graine à 300 arbres (0,091) : le seul gain
    accessible était la réduction de variance.
    """

    def __init__(self, cols, n_estimators=2000, contamination=0.02, ...):
        ...

    def fit(self, df):        # <- aucun paramètre d'étiquettes
        ...

    def score(self, df):
        """Score croissant avec l'atypicité (convention testée)."""
        ...
```

### Annexe E — Extrait de code : construction des cibles de prévision

Extrait de `src/models/forecast.py`. Le point subtil est la **jointure
temporelle** plutôt que le décalage positionnel.

```python
def build_targets(df, kpis, horizons):
    """Cible = valeur observée à ts + h, appariée par jointure temporelle.

    Un df.shift(-h) décalerait de h *lignes*, ce qui est faux dès qu'il
    manque une minute dans la série : la cible serait alors prise plus
    loin dans le futur que l'horizon annoncé, et le modèle paraîtrait
    meilleur qu'il n'est. La jointure sur (cell_id, ts + h) est correcte
    en présence de trous. Un test dédié vérifie ce comportement sur une
    série trouée.
    """
    for h in horizons:
        futur = df[["cell_id", "ts"] + kpis].copy()
        futur["ts"] = futur["ts"] - pd.Timedelta(minutes=h)
        df = df.merge(futur, on=["cell_id", "ts"], suffixes=("", f"_h{h}"))
    return df
```

### Annexe F — Sélection de la fonction de perte par validation

Erreur absolue moyenne en validation, par objectif d'apprentissage, à l'horizon
30 minutes. Le gain croît avec l'asymétrie de la distribution de l'indicateur —
ce qui confirme le mécanisme décrit au §4.3.

| Indicateur | Asymétrie | `reg:squarederror` | `reg:absoluteerror` | Retenu |
|---|---|---|---|---|
| `throughput` | 0,48 | 3,1018 | 2,8696 | absolu |
| `latency` | 12,56 | 1,4354 | 1,0398 | absolu |
| `jitter` | 6,62 | 0,3672 | 0,2860 | absolu |
| `packet_loss` | 28,26 | 0,4345 | 0,2526 | absolu |
| `cell_load` | −0,04 | 3,9443 | 3,9251 | absolu |

Source : `reports/metrics/prevision_selection_objectif.csv`.

### Annexe G — Reproduire les résultats de ce rapport

Toutes les commandes se lancent depuis `binome-b/`. Elles fonctionnent contre
l'API du Binôme A ou hors ligne sur les CSV locaux.

```bash
pip install -r requirements.txt

python -m pytest                        # 60 tests, ~2 s, sans base ni API
python -m src.scripts.run_eda           # -> reports/rapport_eda.md
python -m src.scripts.train_anomaly     # -> reports/metrics/anomalie_*
python -m src.scripts.train_forecast    # -> reports/metrics/prevision_*
python -m src.scripts.tune_anomaly      # -> optimisation + borne oracle
python -m src.scripts.tune_forecast     # -> sélection de la perte
python -m src.scripts.make_report       # -> rapport d'évaluation
streamlit run src/dashboard/app.py      # -> http://localhost:8501

# Forcer la source de données
NETQOS_DATA_SOURCE=local python -m src.scripts.train_anomaly
NETQOS_DATA_SOURCE=api API_BASE_URL=http://localhost:8010/api/v1 \
    python -m src.scripts.run_eda
```

Procédure de vérification détaillée, avec les valeurs attendues à chaque étape :
`binome-b/GUIDE_TEST.md`.

### Annexe H — Glossaire

| Terme | Définition |
|---|---|
| KPI | *Key Performance Indicator* — indicateur clé de performance réseau |
| QoS | *Quality of Service* — qualité de service |
| Non supervisé | Apprentissage sans accès aux étiquettes de vérité terrain |
| Vérité terrain | Étiquette de référence (`is_anomaly`) servant uniquement à évaluer |
| Fuite de données | Information du segment de test parvenue à l'entraînement, produisant des métriques flatteuses et fausses |
| Purge | Zone retirée de part et d'autre d'une frontière de découpage, pour empêcher les fenêtres glissantes de faire fuir de l'information |
| Prévalence | Proportion de cas positifs — ici 1,5 % d'anomalies |
| PR-AUC | Aire sous la courbe précision-rappel ; métrique de référence en fort déséquilibre |
| ROC-AUC | Aire sous la courbe ROC ; optimiste et peu informative à faible prévalence |
| MAE | *Mean Absolute Error* — erreur absolue moyenne |
| Épisode | Suite d'instants anormaux consécutifs, correspondant à un incident pour l'exploitant |
| Persistance | Baseline de prévision annonçant que la valeur future égalera la valeur actuelle |
| Oracle supervisé | Modèle entraîné avec accès aux étiquettes, utilisé comme borne supérieure et non déployé |
