# Rapport de projet — NetQoS-AI

**Plateforme intelligente de surveillance et de prévision de la qualité de
service réseau**

École Supérieure Multinationale des Télécommunications — ESMT, Dakar
Département ESMT TIC (DETIC)
Cycle d'ingénierie — Ingénierie des Données et Intelligence Artificielle (INGC2)

| | |
|---|---|
| **Intitulé du projet** | NetQoS-AI — Plateforme intelligente de surveillance et de prévision de la qualité de service réseau |
| **Code projet** | DRI-IDIA-NETQOS-2025/2026 |
| **Année académique** | 2025 – 2026 |
| **Encadrant** | Prof. Boudal NIANG |
| **Co-encadrant / tuteur** | [À COMPLÉTER] |
| **Durée** | 30 jours (4 semaines) · ≈ 120 heures étudiant |
| **Binôme A — ingénierie des données & pipeline** | [NOM ET PRÉNOM — BINÔME A] |
| **Binôme B — intelligence artificielle & restitution** | [NOM ET PRÉNOM — BINÔME B] |
| **Dépôt** | [URL DU DÉPÔT GIT] |

> **Note de rédaction — à supprimer avant remise.** Les mentions
> `[À COMPLÉTER]`, `[NOM …]` et `[URL …]` correspondent aux informations
> nominatives que ce document ne peut pas deviner. Les repères
> `**📷 Capture d'écran —** …` marquent les emplacements où insérer les
> captures de la démonstration. Tous les chiffres du Binôme B cités ici sont
> issus de `reports/metrics/` et se régénèrent par les commandes de
> l'annexe F.

---

## Remerciements

Nous tenons à exprimer notre gratitude à toutes les personnes qui ont contribué
à la réussite de ce projet.

Nous remercions tout particulièrement le **Prof. Boudal NIANG**, notre
encadrant, pour la définition d'un sujet à la fois complet et exigeant, pour son
suivi régulier au fil des quatre jalons, et pour l'exigence méthodologique qu'il
a maintenue — en particulier l'obligation de comparer tout modèle avancé à une
baseline simple, qui s'est révélée déterminante dans nos conclusions.

Nous remercions le Département ESMT TIC pour le cadre de travail et les moyens
mis à disposition.

Nous nous remercions enfin mutuellement. Le sujet nous imposait de travailler en
parallèle de part et d'autre d'une interface commune, chacun dépendant
entièrement de la production de l'autre. Les échanges techniques que cette
situation a rendus nécessaires — y compris ceux portant sur les défauts
d'intégration que ce rapport détaille sans les dissimuler — ont constitué la
partie la plus formatrice du projet.

---

## Introduction

Ce rapport présente le projet **NetQoS-AI**, réalisé sur quatre semaines dans le
cadre du cycle d'ingénierie en Ingénierie des Données et Intelligence
Artificielle de l'ESMT. Il ne s'agit pas d'un stage en entreprise mais d'un
**projet de stage académique** encadré, dont la fiche descriptive fixe les
objectifs, le périmètre, les livrables et la grille d'évaluation.

Le projet répond à une question opérationnelle du secteur des télécommunications
: à partir des indicateurs de performance collectés en continu sur les cellules
d'un réseau — débit, latence, gigue, taux de perte de paquets et charge de
cellule — comment **détecter** une dégradation atypique, **l'anticiper** à
quelques dizaines de minutes, et **la restituer** à un exploitant sous une forme
sur laquelle il puisse agir ?

Le sujet impose une seconde difficulté, pédagogique et volontaire : le travail
est scindé en deux composantes confiées à deux binômes travaillant en parallèle,
reliées par un **contrat d'interface** figé en fin de première semaine. Le
**Binôme A** produit les données — génération, ingestion, nettoyage, calcul de
caractéristiques, stockage en base de séries temporelles, exposition par une API
REST. Le **Binôme B** les consomme — analyse exploratoire, détection
d'anomalies, prévision, tableau de bord. Aucun accès direct à la base, aucun
import de code : ce qui traverse la frontière est un format de réponse HTTP.

C'est la situation réelle d'un projet de données en entreprise, où l'équipe
plateforme et l'équipe science des données doivent négocier un contrat clair
pour avancer sans se bloquer. Elle a produit, dans ce projet, à la fois le
principal facteur de réussite et la principale source de difficultés.

Ce rapport est **rédigé conjointement**. Il suit la structure demandée au §6.1
de la fiche de projet — contexte, architecture, choix techniques, résultats,
limites et perspectives — en attribuant explicitement chaque contribution à son
binôme. Les sections 5 et 6 sont volontairement détaillées : elles présentent
sept difficultés techniques et leurs résolutions, ainsi que les résultats
chiffrés de l'évaluation, y compris ceux qui contredisent l'attente initiale.

---

## 1. Contexte et cadrage

### 1.1. Contexte et problématique

La qualité de service (QoS) est un enjeu central pour tout opérateur ou
fournisseur d'accès. La dégradation du débit, l'augmentation de la latence, la
gigue et la perte de paquets affectent directement l'expérience de l'utilisateur
et les engagements contractuels de niveau de service (SLA). Les réseaux modernes
produisent un volume massif d'indicateurs horodatés, mais ces données restent
souvent sous-exploitées : elles sont observées *a posteriori* plutôt que
transformées en capacité d'anticipation.

La supervision traditionnelle repose sur des **seuils fixes** définis
manuellement par indicateur : au-delà de tant de millisecondes de latence,
l'alerte se déclenche. Cette approche a deux limites que le projet a permis de
**quantifier** plutôt que de simplement postuler.

La première est qu'un seuil fixe ignore la **variabilité normale** du trafic. Une
charge de cellule à 90 % est banale à l'heure de pointe et anormale à quatre
heures du matin ; un seuil unique se trompe dans les deux cas. L'analyse
exploratoire (§6.2) met en évidence une saisonnalité journalière et hebdomadaire
marquée sur les cinq indicateurs : le référentiel pertinent n'est pas une
constante, mais l'écart au comportement habituel de la cellule à cette heure-là.

La seconde est qu'un seuil ne détecte que les anomalies **d'amplitude**, pas
celles de **forme**. Une gigue anormalement irrégulière, à charge et latence
normales, ne franchit aucun seuil mais signale un problème. Le croisement mené
au §6.2 le chiffre : appliqués tels quels, les seuils de notre contrat classent
« critique » **42,5 % des instants pourtant normaux**, tout en laissant **14,2 %
des anomalies réelles** en dessous de leur radar. Un exploitant qui s'y fierait
recevrait une majorité de fausses alertes tout en manquant une partie des vrais
incidents.

Le projet vise à dépasser cette limite en combinant un pipeline de données
industrialisé avec des méthodes d'apprentissage automatique, restituées dans un
tableau de bord destiné aux équipes d'exploitation.

### 1.2. Objectifs et périmètre

L'objectif général fixé par la fiche est de concevoir, développer et déployer une
plateforme reproductible capable de :

1. ingérer des données de performance réseau en mode batch et en flux simulé ;
2. les nettoyer, les enrichir et les stocker dans une base adaptée aux séries
   temporelles ;
3. détecter les anomalies et prévoir l'évolution des KPI de QoS au moyen de
   modèles d'IA ;
4. restituer les résultats dans un tableau de bord interactif à destination d'un
   exploitant réseau.

**Sont explicitement hors périmètre** : le déploiement sur infrastructure
opérateur réelle, la collecte de données personnelles, et l'action automatique
sur les paramètres réseau — le projet reste en surveillance et prévision.

Faute d'accès à des données réseau réelles, nous avons retenu la **génération
synthétique paramétrée**, l'option recommandée par la fiche, parce qu'elle est
la seule à fournir une **vérité terrain** permettant d'évaluer la détection
d'anomalies. Ce choix a une conséquence méthodologique importante, traitée au
§1.4 et au §7.1 : la qualité de l'évaluation est bornée par le réalisme et la
richesse du simulateur.

### 1.3. Organisation en deux binômes et contrat d'interface

| Binôme | Périmètre | Livrables |
|---|---|---|
| **A** | Ingénierie des données & pipeline | Générateur synthétique, ingestion batch et flux, nettoyage, ingénierie de caractéristiques, base TimescaleDB, API REST FastAPI, orchestration Airflow |
| **B** | Intelligence artificielle & restitution | Analyse exploratoire, protocole d'évaluation, détecteurs d'anomalies, modèles de prévision, classification de l'état QoS, tableau de bord Streamlit, rapport d'évaluation, notice, guide de test |

Le **contrat d'interface**, figé au jalon J7 le 10 août 2026 en version 1.1, est
un livrable commun évalué. Il précise le schéma des données échangées, les
points d'accès et le format de réponse de l'API, le dictionnaire des
caractéristiques, et les conventions communes de gestion du temps et des valeurs
manquantes.

Trois règles de ce contrat ont structuré tout le projet, et méritent d'être
énoncées ici parce que les sections suivantes y reviennent constamment.

**Première règle — la frontière ne se traverse qu'en HTTP.** Le Binôme B n'a
aucun accès à la base et n'importe aucun code du Binôme A. Cette règle ne se
vérifie pas par relecture : elle se constate au fait qu'un seul fichier du volet
B, `binome-b/src/data/api_client.py`, contient un appel réseau, et qu'aucun ne
contient de SQL.

**Deuxième règle — l'étiquette de vérité terrain est isolée.** La colonne
`is_anomaly`, produite par le simulateur, n'existe que dans la table brute et
n'est exposée que par un endpoint unique réservé à l'évaluation
(`GET /api/v1/eval/labels`). Un filtre de l'API la retire par défaut de toute
autre réponse. C'est cette isolation qui garantit que la détection d'anomalies
reste **non supervisée** au sens du §4.3 de la fiche.

**Troisième règle — une enveloppe de réponse commune.** Tout endpoint renvoie
`cell_id`, `from`, `to`, `count`, `data`, complétés de
`limit`/`offset`/`total`/`has_more` s'il est paginé. Cette homogénéité permet à
un client unique de consommer l'ensemble de l'API. Deux des difficultés de la
section 5 proviennent d'un écart à cette règle.

### 1.4. Planning, jalons et état d'avancement

| Jalon | Attendu | État atteint |
|---|---|---|
| **J7** | Contrat d'interface figé | **Atteint.** Contrat v1.1 gelé le 2026-08-10. Dictionnaire de données, zone brute et premier script d'ingestion côté A ; analyse exploratoire et cadrage des modèles côté B. |
| **J14** | Pipeline bout-en-bout fonctionnel | **Atteint.** Chaîne ingestion → nettoyage → caractéristiques validée sur 14 jours et 5 cellules côté A ; protocole d'évaluation et huit baselines évaluées côté B. |
| **J21** | Intégration A ↔ B (le dashboard lit l'API) | **Atteint**, après résolution de quatre défauts d'intégration (§5.2, §5.4, §5.5). Vérifié sur la stack Docker complète, flux quasi temps réel inclus. |
| **J30** | Plateforme complète, documentée, démontrée | **Atteint.** Plateforme démarrable en une commande, l'ensemble des livrables du §6 produits, support de soutenance et déroulé de démonstration inclus. |

### 1.5. Synthèse des résultats

Pour situer d'emblée ce que le projet a produit, avant le détail des sections
suivantes.

| | Résultat |
|---|---|
| **Pipeline** | 5 cellules · 14 jours · ~100 800 mesures · 43 caractéristiques par point · orchestration toutes les 15 min · flux simulé à 1 mesure / 5 s / cellule |
| **API** | 9 endpoints REST documentés par OpenAPI, enveloppe de réponse commune, pagination |
| **Détection d'anomalies** | Isolation Forest retenu : F1 = 0,631 · PR-AUC = 0,586 · **0,018 fausse alerte/h** · 9 épisodes sur 9 détectés · délai médian 13,5 min |
| **Référence à battre** | Seuils fixes du contrat : F1 = 0,051 · 0,553 fausse alerte/h. Le modèle **multiplie le F1 par 12 et divise les fausses alertes par 30**, sans voir aucune étiquette |
| **Prévision** | XGBoost multi-horizon : MAE inférieure de **10,0 % / 14,6 % / 20,7 %** à la persistance à 5 / 15 / 30 min |
| **État QoS annoncé** | ≈ **82 % d'exactitude**, stable de 5 à 30 minutes |
| **Plafond mesuré** | Un oracle *supervisé* (interdit par le contrat, non déployé) atteint 0,905 de PR-AUC : l'écart de 0,319 est le **prix mesuré de la contrainte non supervisée** |
| **Reproductibilité** | Stack complète démarrable en une commande · 60 tests automatisés côté B · tous les rapports générés depuis les fichiers de métriques |

---

## 2. Architecture de la plateforme

### 2.1. Chaîne de traitement en six couches

L'architecture suit les six couches définies au §4.1 de la fiche, chacune
correspondant à une étape du cycle de vie de la donnée.

| Couche | Binôme | Composants |
|---|---|---|
| **1 · Ingestion** | A | `synthetic_generator.py` (génération paramétrée avec injection contrôlée d'anomalies), `batch_ingest.py` (fichiers historiques), `stream_simulator.py` (flux quasi temps réel) |
| **2 · Préparation** | A | `clean_prepare.py` (dédoublonnage, ré-échantillonnage à la minute, interpolation linéaire bornée, bornes de validité par KPI), `build_features.py` (fenêtres glissantes, décalages, saisonnalité) |
| **3 · Stockage** | A | TimescaleDB : `raw_kpi_measurements`, `clean_kpi_measurements`, `kpi_features` — trois hypertables à clé primaire `(ts, cell_id)` |
| **4 · Service** | A | API FastAPI, 9 endpoints sous `/api/v1`, documentation OpenAPI automatique |
| **5 · Intelligence** | B | `api_client.py` → `preprocessing.py` / `splits.py` → `anomaly.py`, `forecast.py`, `qos_state.py`, `evaluation/metrics.py` |
| **6 · Restitution** | B | `dashboard/app.py` — tableau de bord Streamlit à six onglets, alertes, flux temps réel |

L'**orchestration** (Airflow, Binôme A) est transverse aux couches 2 et 3 : elle
réexécute le nettoyage puis le calcul des caractéristiques toutes les quinze
minutes.

### 2.2. Schéma d'architecture annoté

Le §4.4 de la fiche demande un schéma annoté montrant les six couches, les flux
entre elles, et la frontière A ↔ B matérialisée par l'API.

![Architecture de la plateforme NetQoS-AI en six couches](architecture_schema.png)

Ce schéma est **généré par un script** (`binome-b/src/scripts/make_architecture.py`)
et non dessiné à la main. Trois raisons à ce choix : chaque libellé porte le nom
réel d'un fichier ou d'une table du dépôt, donc rien n'y est inventé ; il se
régénère si l'architecture évolue ; et il se relit dans un diff Git, ce qu'une
image dessinée ne permet pas.

Deux éléments méritent l'attention à la lecture.

Le **chemin isolé de `is_anomaly`**, tracé en rouge tireté, relie la table brute
au seul endpoint `/eval/labels` et à rien d'autre. C'est la représentation
graphique de la deuxième règle du contrat (§1.3), et la garantie visuelle que la
détection reste non supervisée.

La **frontière A ↔ B**, qui porte la version du contrat et sa date de gel. Une
seule flèche de flux la traverse : c'est l'appel HTTP.

### 2.3. La frontière A ↔ B, et ce qu'elle impose

La séparation en deux volets étanches, calquée sur une logique de services, a eu
trois effets pratiques.

Elle a **permis le parallélisme**. Le Binôme B a pu développer et évaluer ses
modèles contre une source de données locale équivalente pendant que le Binôme A
finalisait l'API (§3.3), sans attente mutuelle. C'est exactement l'usage prévu
par la fiche au §2.3.

Elle a rendu chaque volet **testable indépendamment**. Ce qui traverse la
frontière est un format de réponse, pas un état partagé de base de données : le
volet B se teste sans base, sans API et sans Docker, en quelques secondes.

Elle a en revanche rendu le volet B **vulnérable à tout écart de l'interface**.
Un défaut de format qui n'aurait été qu'une gêne avec un accès direct à la base
devient bloquant pour un consommateur qui n'a aucun moyen de contournement. Deux
des sept difficultés de la section 5 relèvent exactement de ce cas, et ce sont
les deux plus coûteuses en temps de diagnostic.

### 2.4. Modèle de données

Trois tables, une par étape du pipeline, dont la structure a été fixée au jalon
J7 dans le cadre du contrat.

**`raw_kpi_measurements`** — mesures brutes telles qu'ingérées.

| Colonne | Type | Description |
|---|---|---|
| `ts` | timestamp | Horodatage de la mesure |
| `cell_id` | text | Identifiant de la cellule réseau |
| `throughput` | float | Débit (Mbit/s) |
| `latency` | float | Latence (ms) |
| `jitter` | float | Gigue (ms) |
| `packet_loss` | float | Taux de perte de paquets (%) |
| `cell_load` | float | Charge de la cellule (%) |
| `is_anomaly` | boolean | **Vérité terrain** produite par le simulateur — n'existe que dans cette table |

**`clean_kpi_measurements`** — mêmes colonnes de KPI, ré-échantillonnées à une
fréquence fixe d'une minute, sans `is_anomaly`, avec une colonne booléenne
`is_missing` signalant les valeurs interpolées.

**`kpi_features`** — pour chaque KPI : moyennes glissantes à 5, 15 et 30 minutes,
écart-type à 15 minutes, décalages à 1, 5 et 10 minutes, moyenne horaire. S'y
ajoutent deux colonnes de saisonnalité (heure de la journée, jour de la semaine)
et le maximum glissant horaire de la charge de cellule — caractéristique
demandée spécifiquement par le Binôme B au jalon J7, pour situer une charge
instantanée dans son contexte plutôt que dans l'absolu. Soit **43 colonnes de
caractéristiques** par point de mesure.

Les trois tables sont des **hypertables TimescaleDB** avec la clé primaire
composite `(ts, cell_id)`. Deux conventions communes, inscrites au contrat :
une valeur manquante en base est `NULL`, jamais `0` ni `-1` ; et une valeur
imputée est signalée par `is_missing` plutôt que silencieusement substituée.

**📷 Capture d'écran —** *schéma de la base ou extrait d'une requête sur
`kpi_features`.*

### 2.5. Services conteneurisés

L'architecture de déploiement suit une logique de services communiquant par le
réseau interne Docker, orchestrés par un unique `docker-compose.yml` à la racine
du dépôt.

| Service | Rôle | Binôme |
|---|---|---|
| `timescaledb` | Base de séries temporelles, trois hypertables | A |
| `api` | Service FastAPI exposant données et caractéristiques | A |
| `dashboard` | Application Streamlit consommant l'API | B |
| `airflow` | Orchestrateur du pipeline (profil `full`) | A |
| `stream-simulator` | Flux quasi temps réel (profil `stream`) | A |

La contrainte de reproductibilité du §3.3 de la fiche — « tout le pipeline
s'exécute à partir d'une commande unique via conteneurs » — est ainsi tenue :

```bash
docker compose up -d --build          # base + API + dashboard
docker compose --profile full up -d   # + orchestration Airflow
```

Les ports publiés sont **paramétrables** sans modifier le fichier compose, une
concession à la réalité des machines de développement où 5432 et 8000 sont
fréquemment déjà occupés :

```bash
POSTGRES_HOST_PORT=5433 API_PORT=8010 DASHBOARD_PORT=8511 docker compose up -d
```

**📷 Capture d'écran —** *sortie de `docker ps` montrant les conteneurs sains.*

---

## 3. Choix techniques

### 3.1. Environnement et outillage

| Composant | Technologie | Rôle |
|---|---|---|
| Langage | Python 3.12 (A) / 3.13 (B) | Pipeline, API, modèles, restitution |
| Manipulation de données | pandas, NumPy | Nettoyage, ré-échantillonnage, agrégations |
| Base de données | TimescaleDB (PostgreSQL) | Stockage de séries temporelles |
| Accès base | SQLAlchemy + psycopg2 | Requêtes et écritures côté A |
| API REST | FastAPI + uvicorn | Exposition des données au Binôme B |
| Orchestration | Apache Airflow 2.9.3 | Automatisation du pipeline |
| Apprentissage | scikit-learn | Isolation Forest, DBSCAN, autoencodeur, normalisation |
| Gradient boosting | XGBoost | Prévision multi-horizon |
| Séries temporelles | statsmodels | ARIMA (baseline de référence) |
| Restitution | Streamlit, plotly, matplotlib | Tableau de bord et figures |
| Tests | pytest | 60 tests sur les invariants du protocole (B) |
| Conteneurisation | Docker & Docker Compose | Déploiement reproductible |
| Export documentaire | pandoc | Génération des livrables Word |
| Collaboration | Git / GitHub | Une branche par binôme et par fonctionnalité |

Ces briques sont toutes open-source et compatibles avec des machines de
configuration modeste, conformément au §7 de la fiche.

### 3.2. Choix du Binôme A — ingénierie des données

**Génération synthétique plutôt que jeu de données public.** Seule cette voie
fournit une vérité terrain (`is_anomaly`) permettant d'évaluer la détection. Le
générateur produit des profils réalistes par KPI, avec saisonnalité journalière
et hebdomadaire, et injection contrôlée d'anomalies.

**TimescaleDB plutôt que PostgreSQL nu.** Les hypertables partitionnent
automatiquement par intervalle de temps, ce qui rend efficaces les requêtes par
plage temporelle — le mode d'interrogation dominant de l'API.

**Clé primaire composite `(ts, cell_id)` sur les trois tables.** Elle garantit
l'unicité d'un point de mesure par cellule et rend impossible le doublon
silencieux. Ce choix a un corollaire qui n'a pas été anticipé d'emblée et qui a
provoqué la difficulté du §5.1 : toute écriture répétée doit être conçue comme
idempotente.

**Écriture par `INSERT ... ON CONFLICT DO UPDATE`,** mutualisée dans
`src/db.py` plutôt que dupliquée entre les modules de nettoyage et de
caractéristiques. C'est la correction du §5.1, érigée en principe : toute tâche
destinée à être ré-exécutée périodiquement par un ordonnanceur doit être
idempotente par conception.

**Airflow avec LocalExecutor et métadonnées dans TimescaleDB** plutôt qu'en
SQLite, plus robuste et cohérent avec l'infrastructure déjà présente. Le DAG
**importe directement les fonctions du pipeline** montées dans le conteneur, sans
dupliquer la logique métier entre le DAG et le script d'orchestration local —
condition pour que les deux modes d'exécution ne divergent jamais.

**Enveloppe de réponse commune** sur tous les endpoints de l'API, pour qu'un
client unique puisse consommer l'ensemble sans traitement particulier par
endpoint.

### 3.3. Choix du Binôme B — modélisation et restitution

**Le protocole d'évaluation avant les modèles.** Ce choix d'ordre est
contre-intuitif : il aurait été plus rapide d'entraîner un premier modèle et
d'en regarder les métriques. Mais sur des séries temporelles, un découpage naïf
produit des scores excellents et faux. Une caractéristique calculée sur une
fenêtre glissante de 60 minutes contient de l'information sur les 60 minutes qui
suivent son horodatage ; un point d'entraînement situé juste avant la frontière
de découpage renseigne donc le segment de test. Rien dans le résultat ne le
signale — au contraire, il est meilleur.

Le découpage retenu est **chronologique par cellule** (60 % entraînement, 20 %
validation, 20 % test), avec une **zone de purge de 60 minutes** retirée de part
et d'autre de chaque frontière — exactement la longueur de la plus longue fenêtre
glissante présente dans les caractéristiques du Binôme A. Deux garde-fous lèvent
des exceptions explicites : `LeakageError` si un ordre chronologique est violé,
`LabelAlignmentError` si le taux d'appariement de la vérité terrain descend sous
50 %. Le second s'est révélé décisif (§5.4).

**La non-supervision garantie par les signatures.** Les méthodes `fit()` des
quatre détecteurs ont pour signature `fit(self, df)` : elles n'acceptent **aucun
argument d'étiquettes**. Il n'est donc pas possible d'entraîner un détecteur sur
`is_anomaly` sans modifier l'interface des classes, ce qui rendrait l'infraction
visible dans un diff plutôt qu'enfouie dans une ligne. La contrainte du §4.3 de
la fiche est ainsi tenue **par construction**, non par discipline.

**Des métriques choisies pour la prévalence réelle.** Le taux d'anomalie mesuré
est de 1,28 %. Un modèle prédisant « jamais d'anomalie » atteindrait donc 98,7 %
d'exactitude : l'*accuracy* est inutilisable, et la ROC-AUC trop optimiste. La
métrique de référence est la **PR-AUC**, complétée de précision, rappel et F1
comme l'exige le §4.3 de la fiche.

**Des métriques par épisode, en plus des métriques ponctuelles.** Un exploitant
ne consomme pas des points de mesure isolés mais des incidents. Nous avons donc
ajouté le **rappel par épisode**, le **délai médian de détection** et le **nombre
de fausses alertes par heure**. Ce sont ces trois chiffres qui décrivent
l'expérience réelle d'un opérateur, bien plus que le F1 ponctuel — et c'est sur
le troisième que l'écart au jeu de seuils est le plus spectaculaire (§6.3).

**Une source de données double.** Un consommateur dont tout le travail s'arrête
quand le producteur redémarre son service ne peut pas avancer régulièrement sur
quatre semaines. `local_source.py` recalcule donc les caractéristiques à partir
des CSV bruts, en **réimplémentant les règles documentées** du Binôme A —
ré-échantillonnage, interpolation bornée, fenêtres glissantes — sans importer
leur code, ce qui aurait violé la frontière. Une façade choisit automatiquement :
API si elle répond, CSV local sinon.

Ce dispositif posait un risque évident : deux implémentations des mêmes règles
divergent en général, et une divergence silencieuse aurait invalidé toute
comparaison entre résultats en ligne et hors ligne. Nous avons donc vérifié
l'équivalence explicitement, colonne par colonne, sur les 43 caractéristiques et
la même période. **L'écart maximal relevé est nul.** La source locale est un
substitut exact, non une approximation — ce qui a rendu possible la campagne
d'optimisation du §5.7, qui a nécessité plusieurs dizaines d'entraînements.

**Streamlit plutôt qu'un framework web complet.** Le livrable est un outil de
supervision, pas une application à mettre en production. Streamlit permet six
onglets et un rafraîchissement temps réel sans écrire de code front-end, ce qui a
laissé le temps disponible à la modélisation.

### 3.4. Choix communs

**Un dépôt unique, deux dossiers, une branche par binôme.** Les branches sont
nommées `binome-a/<fonctionnalité>` et `binome-b/<fonctionnalité>`, fusionnées
sur `main` après validation. Cette convention a rendu les conflits d'intégration
visibles tôt — notamment sur le `docker-compose.yml` (§5.2).

**La documentation comme canal technique, et non comme formalité de fin.** Les
deux binômes ne travaillant pas en présence continue, les réserves techniques
ont été formalisées **par écrit** plutôt que transmises oralement : six points
relevés pendant l'intégration, chacun avec son symptôme, son diagnostic chiffré,
la correction attendue et le contournement appliqué en attendant. Ils sont
repris aux §5 et §7 du présent rapport. Cette formalisation a un coût de
rédaction, mais elle rend chaque réserve reproductible par une commande, et elle
documente le contournement — ce qui évite qu'il soit retiré par erreur une fois
le défaut oublié.

**Les livrables chiffrés sont générés, jamais rédigés à la main.** Le rapport
d'analyse exploratoire, le rapport d'évaluation, les six figures, le schéma
d'architecture et les exports Word sont tous produits par une commande. Un
rapport rédigé manuellement se périme dès la première ré-exécution des modèles ;
un rapport généré ne peut pas mentir sur ses propres métriques.

**Des tests sur les invariants, pas sur la couverture.** La suite de 60 tests du
Binôme B ne cherche pas à couvrir le code : elle verrouille les propriétés dont
la violation serait **silencieuse** — absence de fuite temporelle, purge
effective, alignement des cibles de prévision par durée et non par position,
convention de signe des scores de détection. Une régression sur l'une de ces
propriétés ne lèverait aucune erreur mais produirait des métriques flatteuses et
fausses. C'est le seul type de défaut qu'aucune relecture ne rattrape.

---

## 4. Travail réalisé, semaine par semaine

### 4.1. Semaine 1 (J1–J7) — Cadrage et contrat d'interface

La fiche avertit que le jalon J7 conditionne le parallélisme des deux binômes et
qu'un retard s'y répercute sur toute la suite. Il a donc été traité en priorité.

**Binôme A.** Rédaction du `data_dictionary.md` décrivant le schéma des données
échangées — KPI suivis, unités, bornes de validité, granularité temporelle.
Conception du schéma de la base (`sql/init.sql`) avec les trois tables.
Développement du générateur de données synthétiques, paramétrable en nombre de
cellules et en durée, avec des profils réalistes par KPI. Premier script
d'ingestion batch capable de charger un CSV de mesures historiques.

**Binôme B.** Relecture critique du contrat du point de vue du consommateur :
formulation de la demande de caractéristique supplémentaire (maximum glissant
horaire de la charge), et vérification que la vérité terrain était bien isolée
dans un endpoint dédié. Mise en place de la couche d'accès aux données — client
HTTP paginé, source de repli hors ligne, façade de sélection. Production de
l'**analyse exploratoire complète** : conformité du flux servi, statistiques
descriptives, séparabilité normal / anomalie, saisonnalité, corrélations,
autocorrélation, et validation des seuils QoS.

**Jalon J7 — atteint.** Contrat figé en v1.1 le 10 août 2026 : schéma des tables,
unités, endpoints prévus, conventions de nommage. L'analyse exploratoire est
livrée avec un tableau de décisions de cadrage justifiant chaque choix de
modélisation par une observation chiffrée. Deux réserves sont transmises au
Binôme A, dont le déséquilibre des seuils QoS (§6.2).

### 4.2. Semaine 2 (J8–J14) — Pipeline bout-en-bout et baselines

**Binôme A.** Implémentation du module de nettoyage : dédoublonnage,
ré-échantillonnage à la minute, interpolation linéaire bornée des valeurs
manquantes, ajout de l'indicateur `is_missing`. Application des bornes de
validité par KPI pour écarter les valeurs aberrantes de capteurs défaillants.
Premier jeu de caractéristiques et écriture dans `kpi_features`. Mise en place
d'une **stratégie d'écriture idempotente** pour le nettoyage, anticipant les
ré-exécutions périodiques — choix qui s'est révélé décisif par la suite (§5.1).

**Binôme B.** Construction du protocole d'évaluation décrit au §3.3 : découpage
chronologique par cellule avec purge de 60 minutes, garde-fous anti-fuite,
métriques adaptées au déséquilibre, métriques par épisode. Puis **quatre
baselines de détection** — seuils du contrat, Isolation Forest, DBSCAN,
autoencodeur — et **quatre baselines de prévision** — persistance, moyenne
mobile, naïf saisonnier, ARIMA — toutes évaluées selon le même protocole.

**Jalon J14 — atteint.** Le pipeline bout-en-bout est validé sur 14 jours et 5
cellules. Le protocole d'évaluation et les huit baselines sont livrés et
documentés.

**📷 Capture d'écran —** *extrait de `clean_kpi_measurements` ou `kpi_features`.*

### 4.3. Semaine 3 (J15–J21) — Orchestration, API, modèles avancés, intégration

Cette semaine a constitué le cœur technique du projet, et a révélé l'essentiel
des difficultés de la section 5.

**Binôme A — orchestration.** Un DAG Airflow (`netqos_pipeline_dag.py`)
automatise l'enchaînement nettoyage → caractéristiques toutes les quinze
minutes, en réutilisant directement les fonctions Python déjà développées.
La mise en place en environnement conteneurisé a nécessité plusieurs ajustements
: service dédié au nettoyage d'un fichier `.pid` périmé au redémarrage, choix du
LocalExecutor avec métadonnées en TimescaleDB, et augmentation des délais de
démarrage du serveur web pour laisser la synchronisation initiale des permissions
se terminer.

**Binôme A — API REST.** Les neuf endpoints du contrat v1.1 :

| Endpoint | Usage |
|---|---|
| `GET /api/v1/health` | Vérification de disponibilité |
| `GET /api/v1/cells` | Liste des cellules disponibles |
| `GET /api/v1/thresholds` | Seuils bon / dégradé / critique par KPI |
| `GET /api/v1/kpi/history` | Historique nettoyé, paginé |
| `GET /api/v1/kpi/latest` | Dernières mesures par cellule |
| `GET /api/v1/kpi/stream` | Flux quasi temps réel |
| `GET /api/v1/features` | Caractéristiques pré-calculées, paginées |
| `GET /api/v1/eval/labels` | Vérité terrain, réservée à l'évaluation |
| `GET /api/v1/kpi/stream/info` | Métadonnées du flux (cadence, dernier horodatage) |

**Binôme B — modèles avancés.** Un **autoencodeur** (perceptron multicouche
entraîné à reconstruire le vecteur de caractéristiques, score = erreur de
reconstruction), réglé par recherche sur grille en validation. Et **XGBoost
multi-horizon** en approche directe : un modèle par couple (indicateur,
horizon), soit quinze modèles pour cinq indicateurs à 5, 15 et 30 minutes.
L'approche directe évite l'accumulation d'erreur d'une prévision récursive.

**Binôme B — tableau de bord.** Six onglets (§6.6). Le rafraîchissement temps
réel utilise un fragment Streamlit qui ne recharge que la zone concernée et non
la page entière — sans quoi chaque rafraîchissement relancerait le chargement de
tout l'historique.

**Intégration A ↔ B.** C'est ici que sont apparues quatre difficultés : l'échec
systématique du DAG sur une écriture non idempotente (§5.1), le conflit de
configuration Docker qui faisait basculer le tableau de bord en mode dégradé
(§5.2), et les deux défauts de l'endpoint d'évaluation qui rendaient toute mesure
nulle ou tronquée (§5.4, §5.5). Leur résolution a occupé une part significative
de cette semaine et de la suivante.

**Jalon J21 — atteint.** Le tableau de bord lit l'API en conditions réelles sur
la stack Docker complète, flux quasi temps réel inclus.

**📷 Capture d'écran —** *vue Grid du DAG `netqos_pipeline` dans Airflow.*
**📷 Capture d'écran —** *documentation Swagger générée sur `/docs`.*

### 4.4. Semaine 4 (J22–J30) — Optimisation, finalisation, documentation

**Binôme A.** Fusion et résolution du `docker-compose.yml` commun aux deux
binômes. Diagnostic et remise en route après un incident de configuration en
cascade : un conteneur Airflow resté actif avec une configuration obsolète, puis
une incohérence entre le mot de passe de la base défini dans le `.env` régénéré
et celui réellement stocké dans le volume PostgreSQL existant (§5.3). La
résolution a nécessité l'arrêt propre de tous les services, la suppression
ciblée du volume périmé, la reconstruction complète de la stack, puis la
reconstitution du jeu de données.

**Binôme B.** Une revue d'avancement a posé une question qui a orienté toute la
semaine : les modèles ont-ils été optimisés, et si le modèle retenu n'atteint pas
les 90 à 100 % qu'on attend d'un modèle d'apprentissage, peut-on le justifier ?

Cette question a produit le résultat méthodologique le plus instructif du projet.
Une **campagne d'optimisation** de la détection a exploré 30 configurations sur
deux espaces de caractéristiques, avec **mesure du bruit dû à la graine
aléatoire** comme contrôle — étape qui a invalidé le gain apparent (§5.7). Une
seconde campagne sur la prévision a exploré 8 configurations et rendu la fonction
de perte sélectionnable par validation (§5.6). Enfin, une **borne oracle
supervisée** a été calculée pour chiffrer le plafond atteignable, et donc le prix
exact de la contrainte non supervisée (§6.8).

Le tableau de bord a été repris sur quatre défauts d'ergonomie identifiés en
revue : contrôles communs remontés au-dessus des onglets pour qu'un changement de
cellule s'applique partout, sélecteur de cellule rendu accessible aux onglets
temps réel et prévision, sélecteur de modèle de prévision ajouté par symétrie
avec celui des détecteurs, et affichage explicite de la provenance des données de
chaque onglet.

**Livrables documentaires** produits cette semaine : rapport d'évaluation des
modèles (695 lignes, six figures), notice d'utilisation du tableau de bord, guide
de test en cinq niveaux, document de retours au Binôme A, schéma d'architecture
généré, et le présent rapport.

**Jalon J30.** La plateforme est complète et démontrable, et l'ensemble des
livrables du §6 de la fiche est produit — support de soutenance et déroulé
minuté de la démonstration compris.

---

## 5. Difficultés techniques et résolutions

Cette section détaille sept difficultés. Elles sont conservées en détail parce
qu'elles constituent la partie la plus formatrice du projet, et parce qu'elles se
répartissent en deux familles très différentes.

Les trois premières sont des **pannes franches** : le DAG échoue, le tableau de
bord affiche un mode dégradé, l'API refuse de se connecter. Elles font mal mais
se voient.

Les quatre suivantes ne provoquaient **aucune erreur**. Chacune produisait un
résultat plausible et faux, et trois d'entre elles auraient produit des chiffres
*plus flatteurs* que la réalité. C'est, de notre point de vue, la classe de
défaut la plus dangereuse dans un projet d'apprentissage automatique, où l'on ne
dispose généralement pas d'une intuition préalable du résultat correct.

### 5.1. Non-idempotence de l'écriture des caractéristiques (Binôme A)

**Symptôme.** Une fois le DAG Airflow en production, la tâche `build_features`
échouait de façon quasi systématique, alors que la tâche `clean_prepare` qui la
précède s'exécutait sans erreur. La grille d'exécution d'Airflow a permis
d'isoler rapidement la tâche fautive.

**Diagnostic.** Les logs révélaient :

```
psycopg2.errors.UniqueViolation: duplicate key value violates
unique constraint "kpi_features_pkey"
DETAIL: Key (ts, cell_id)=(...) already exists.
```

La cause était une écriture non idempotente : `build_features` utilisait
`pandas.to_sql(..., method="multi")`, qui génère de simples `INSERT`. Or les
fenêtres glissantes, dont la plus longue couvre 60 minutes, se chevauchent
nécessairement entre deux exécutions espacées de 15 minutes — d'où une tentative
de réinsertion de lignes déjà présentes.

**Résolution.** Remplacement de l'insertion simple par un *upsert* PostgreSQL
(`INSERT ... ON CONFLICT DO UPDATE`), déjà employé avec succès dans le module de
nettoyage. La fonction a été **mutualisée** dans `src/db.py` plutôt que dupliquée
entre les deux scripts (annexe C).

**Vérification croisée.** Le Binôme B avait signalé cette réserve depuis son
poste de consommateur, constatant que toute seconde exécution du pipeline
échouait et empêchait le DAG de rafraîchir les données. Après correction, il a
vérifié sur la stack que **deux exécutions consécutives réussissent et que les
comptages restent stables**, et a levé la réserve par écrit. La correction a donc
été validée par les deux binômes, du côté producteur et du côté consommateur.

**Ce que nous en retenons.** Toute tâche destinée à être ré-exécutée
périodiquement par un ordonnanceur doit être conçue comme **idempotente dès
l'origine**, plutôt que corrigée après coup. La clé primaire composite qui a
provoqué l'échec est par ailleurs ce qui a permis de le détecter immédiatement :
sans elle, les doublons se seraient accumulés en silence.

### 5.2. Conflit de fusion sur `docker-compose.yml` (commun)

**Symptôme.** Lors de la fusion des travaux des deux binômes, le
`docker-compose.yml` — créé indépendamment de chaque côté — est entré en conflit.
Après une première résolution, le tableau de bord affichait un message de repli :
« Mode dégradé : CSV local — l'API du Binôme A n'est pas joignable », alors que
l'API fonctionnait correctement.

**Diagnostic.** Le nom de la variable d'environnement définie côté service Docker
(`NETQOS_API_URL`) ne correspondait pas à celui effectivement lu par le code
client du Binôme B (`API_BASE_URL`, dans `binome-b/src/config.py`). La variable
était silencieusement ignorée et le client retombait sur son URL par défaut,
`localhost:8000` — qui, exécutée depuis l'intérieur du conteneur du tableau de
bord, ne pointe vers rien.

**Résolution.** Correction explicite de la variable dans le compose fusionné,
avec une note **dans le fichier lui-même** pour prévenir la régression :

```yaml
dashboard:
  environment:
    # API_BASE_URL, et non NETQOS_API_URL : c'est le nom lu par
    # binome-b/src/config.py. Nom de service Docker et non localhost,
    # le dashboard tournant dans son propre conteneur.
    API_BASE_URL: http://api:8000/api/v1
```

Le client a par ailleurs été rendu tolérant à l'alias `NETQOS_API_URL`, de sorte
que les deux noms fonctionnent désormais.

**Ce que nous en retenons.** Ce défaut était invisible en développement local, où
`localhost` fonctionne des deux côtés. Il n'apparaît que dans les conditions
réelles de déploiement, où les conteneurs communiquent par nom de service. Le
mode de repli du client a joué ici un rôle ambigu qui vaut d'être noté : il a
**masqué** la panne en la transformant en dégradation silencieuse, mais c'est
aussi son message explicite qui a mis sur la piste. Un repli doit toujours
annoncer qu'il s'est déclenché.

### 5.3. Incohérence des identifiants après régénération d'un volume (Binôme A)

**Symptôme.** Après régénération du `.env` à partir du modèle `.env.example`,
l'API ne pouvait plus se connecter à la base :

```
psycopg2.OperationalError: connection to server at "timescaledb"
failed: FATAL: password authentication failed for user "netqos"
```

**Diagnostic.** PostgreSQL n'initialise les identifiants qu'au **tout premier
démarrage** d'un volume de données. Le volume avait été créé lors d'un test
antérieur avec un mot de passe différent de celui désormais présent dans le
`.env` ; l'API se connectait donc avec des identifiants ne correspondant plus à
ceux réellement stockés.

**Résolution.** Le jeu de données de test n'ayant pas de valeur à conserver à ce
stade, le volume a été supprimé et recréé, suivi d'une régénération complète des
données :

```bash
docker compose down
docker volume rm netqos_ai_timescale_data
docker compose up -d --build
```

**Ce que nous en retenons.** En production, cette opération aurait été
inacceptable sans alternative préservant les données — un `ALTER USER` exécuté
directement dans PostgreSQL. L'incident a surtout clarifié le cycle de vie des
volumes Docker : un volume porte un **état** qui survit à la configuration qui
l'a créé, et la cohérence entre fichiers de configuration et état persisté n'est
pas garantie par l'outillage.

### 5.4. `/eval/labels` : des horodatages qui n'apparient rien (frontière)

**Symptôme.** Au premier branchement de la chaîne d'évaluation du Binôme B sur
l'API, toutes les métriques de détection sont tombées à **zéro** — précision,
rappel, F1, PR-AUC. Aucune exception, aucun avertissement. La prévalence mesurée
dans le segment de test affichait **0,00 %**, alors que l'analyse exploratoire
menée sur les CSV avait établi un taux d'anomalie de 1,28 %.

**Diagnostic.** L'endpoint `GET /api/v1/eval/labels`, seul point d'accès à la
vérité terrain, sert les horodatages de la table **brute**, non ré-échantillonnés
: `20:21:41`. Les endpoints `/kpi/history` et `/features` servent en revanche la
grille ré-échantillonnée à la minute pleine : `20:21:00`.

La jointure des étiquettes sur les caractéristiques se fait par la clé
`(ts, cell_id)`. Avec des horodatages à la seconde d'un côté et à la minute de
l'autre, **aucune ligne ne s'apparie**. La jointure réussit, retourne le bon
nombre de lignes, et ne contient que des valeurs manquantes dans la colonne
d'étiquettes. Traitées comme « pas une anomalie », elles produisent un jeu de
test où rien n'est anormal — d'où une prévalence nulle et des métriques nulles,
en silence.

Le défaut est particulièrement pernicieux parce qu'il touche l'**endpoint
d'évaluation** : son unique raison d'être est de permettre de mesurer, et son
format le rendait inutilisable pour mesurer. Un consommateur moins méfiant aurait
pu conclure que ses modèles ne détectaient rien.

**Résolution.** Trois actions, dans cet ordre.

D'abord un **contournement** dans `loader.load_labels()` : réalignement des
horodatages sur la grille à la minute par troncature, puis agrégation par cellule
et par minute avec l'opérateur `max` — si l'une des mesures d'une minute est
anormale, la minute est anormale. Cette convention est conservatrice et
documentée.

Ensuite un **garde-fou**, parce qu'un contournement peut cesser de fonctionner si
le format amont change à nouveau. `splits.align_labels()` calcule le taux
d'appariement et lève `LabelAlignmentError` s'il descend sous 50 % (annexe D). Le
mode d'échec silencieux devient bruyant : c'est le seul changement qui garantisse
qu'aucune métrique ne sera plus publiée sur des étiquettes absentes.

Enfin une **réserve écrite** au Binôme A, avec la commande permettant de
reproduire le constat en deux appels HTTP. La correction attendue est de servir
les horodatages alignés sur `clean_kpi_measurements`.

**Ce que nous en retenons.** Un système d'apprentissage n'a pas de bon sens : il
ne remarque pas qu'un jeu de test sans aucune anomalie est absurde. La détection
de l'absurde doit donc être **programmée explicitement**, sous forme
d'assertions sur les invariants attendus des données. Le garde-fou a coûté quinze
lignes ; sans lui, tout résultat de ce rapport aurait dépendu de la vigilance
d'un relecteur devant une prévalence affichée.

### 5.5. `/eval/labels` : une pagination silencieusement tronquée (frontière)

**Symptôme.** Après correction du défaut précédent, la prévalence remontait mais
restait trop faible, et le volume d'étiquettes chargées plafonnait à **5 000
lignes** au lieu des 100 800 attendues.

**Diagnostic.** Le contrat définit une enveloppe de réponse incluant, pour les
endpoints paginés, `limit`, `offset`, `total` et `has_more`. Le client du Binôme
B déroulait la pagination en s'arrêtant lorsque `has_more` valait faux.

L'endpoint `/eval/labels` accepte bien `limit` et `offset`, mais **omet les
quatre champs de pagination de son enveloppe**. En l'absence de `has_more`, le
client interprétait l'absence comme « plus rien à lire » et s'arrêtait après la
première page — soit **5 % des étiquettes**, sans erreur.

**Résolution.** Le client a été rendu robuste à l'absence de ces champs : si
`has_more` est présent, il fait foi ; sinon, le client continue **tant que la
page reçue est pleine** et s'arrête à la première page incomplète. L'heuristique
est correcte dans tous les cas sauf celui, sans conséquence, où le total est un
multiple exact de la taille de page — un appel supplémentaire renvoyant une page
vide. Le défaut a été signalé au Binôme A comme le précédent.

**Ce que nous en retenons.** Un client qui consomme une interface qu'il ne
contrôle pas ne doit pas supposer que le contrat est respecté : il doit se
comporter correctement quand il ne l'est pas, **et le signaler**. La difficulté
n'était pas technique — la correction tient en cinq lignes — mais de **méthode de
diagnostic** : c'est la comparaison d'un volume mesuré à un volume attendu qui a
révélé le problème, pas la lecture du code.

### 5.6. Un modèle avancé battu par la baseline la plus naïve (Binôme B)

**Symptôme.** XGBoost multi-horizon, avec ses paramètres par défaut, était
**battu par la persistance** — la baseline qui prédit simplement que la valeur
future égalera la valeur actuelle. Sur le taux de perte de paquets, son erreur
absolue moyenne était supérieure de 45 % à celle de la persistance, avec un biais
positif marqué.

Un modèle à gradient boosting entraîné sur 43 caractéristiques battu par « la
valeur ne changera pas » : le résultat était trop mauvais pour un simple défaut
de réglage.

**Diagnostic.** La distribution du taux de perte de paquets est extrêmement
asymétrique : médiane 0,63 %, 99ᵉ centile 1,22 %, maximum **79,6 %**, coefficient
d'asymétrie **28,3**. La variable est presque toujours très basse et
occasionnellement énorme.

L'objectif d'apprentissage par défaut de XGBoost est l'**erreur quadratique**,
qui pénalise une erreur de 20 points quatre cents fois plus qu'une erreur d'un
point. Sur cette distribution, le modèle minimise donc sa perte en se préparant
aux pics rares — il surestime systématiquement le régime normal, qui représente
l'immense majorité des points.

Or la métrique d'évaluation imposée par le §4.3 de la fiche est l'erreur
**absolue** moyenne, qui pénalise linéairement. Le modèle optimisait donc une
quantité différente de celle sur laquelle il était jugé. Le problème n'était ni
le modèle, ni ses hyperparamètres, mais le **désaccord entre la perte
d'entraînement et la métrique d'évaluation**.

**Résolution.** L'objectif d'apprentissage a été rendu **sélectionnable par
validation**, au même titre qu'un hyperparamètre : pour chaque couple
(indicateur, horizon), les deux objectifs sont entraînés et celui qui minimise
l'erreur absolue en validation est retenu. Le résultat est net et systématique —
l'objectif absolu gagne sur **les quinze couples**, avec un écart d'autant plus
grand que la distribution est asymétrique :

| Indicateur | Asymétrie | MAE, perte quadratique | MAE, perte absolue | Gain |
|---|---|---|---|---|
| `packet_loss` | 28,3 | 0,4345 | 0,2526 | **−41,9 %** |
| `latency` | 12,6 | 1,4354 | 1,0398 | **−27,6 %** |
| `jitter` | 6,6 | 0,3672 | 0,2860 | −22,1 % |
| `throughput` | 0,5 | 3,1018 | 2,8696 | −7,5 % |
| `cell_load` | −0,04 | 3,9443 | 3,9251 | −0,5 % |

*Horizon 30 minutes, erreur absolue moyenne mesurée en validation.*

La corrélation entre l'asymétrie de l'indicateur et le gain apporté par le
changement de perte confirme le mécanisme : le désaccord ne coûte presque rien
sur une variable symétrique comme la charge de cellule, et coûte 42 % sur la plus
asymétrique. Une fois l'objectif corrigé, XGBoost devance la persistance de
10,0 %, 14,6 % et 20,7 % d'erreur absolue à 5, 15 et 30 minutes.

**Ce que nous en retenons.** C'est le résultat dont nous retirons le plus. Le
réflexe devant un modèle décevant est de régler ses hyperparamètres ; ici, aucun
réglage n'aurait comblé l'écart, parce que le modèle résolvait correctement un
problème qui n'était pas le bon. La question à poser en premier n'est pas
« quels paramètres ? » mais **« le modèle optimise-t-il ce que je mesure ? »**.
Le gain obtenu en changeant une seule ligne dépasse de plus d'un ordre de
grandeur tout ce que la campagne d'optimisation des hyperparamètres a produit.

### 5.7. Un gain d'optimisation qui n'existait pas (Binôme B)

**Symptôme.** La campagne d'optimisation de la détection a exploré 30
configurations. La meilleure améliorait la PR-AUC en validation de **0,6049 à
0,6287, soit +3,93 %**. Un gain modeste mais net, qu'il aurait été naturel de
retenir et d'annoncer.

**Diagnostic.** Avant de conclure, nous avons mesuré une quantité que la
recherche d'hyperparamètres ignore habituellement : la **variabilité due à la
seule graine aléatoire**. Le même modèle, avec exactement les mêmes
hyperparamètres, entraîné six fois avec six graines différentes.

À 300 arbres, la PR-AUC varie de **0,0909** entre la meilleure et la pire graine,
avec un écart-type de 0,0315. L'écart entre la configuration « optimisée » et la
configuration initiale est de **0,0238**. Le bruit de la graine est donc **près
de quatre fois plus grand que le gain mesuré**.

Le « +3,93 % » n'était pas un gain : c'était une graine chanceuse, sélectionnée
par une recherche qui n'avait aucun moyen de distinguer les deux. Retenir cette
configuration aurait consisté à publier du bruit comme un résultat.

**Résolution.** Le constat a réorienté l'objectif. Puisqu'il n'y avait pas de
gain à prendre sur la position dans l'espace des hyperparamètres, le seul progrès
accessible était de **réduire la variance** — rendre le résultat reproductible
plutôt que d'optimiser une valeur instable.

| Nombre d'arbres | PR-AUC moyenne | Écart-type | Étendue sur 6 graines |
|---|---|---|---|
| 300 | 0,5727 | 0,0315 | 0,0909 |
| 1 000 | 0,5945 | 0,0127 | 0,0317 |
| **2 000** | **0,5984** | **0,0053** | **0,0153** |

Passer de 300 à 2 000 arbres divise l'écart-type par six et améliore légèrement
la moyenne. Le modèle retenu utilise donc 2 000 arbres — non pour être meilleur,
mais pour que sa performance ne dépende plus du hasard de l'initialisation. Ces
trois lignes figurent en commentaire dans le code, à côté de la valeur du
paramètre, afin que le choix reste justifié pour un lecteur ultérieur (annexe E).

**Ce que nous en retenons.** Une recherche d'hyperparamètres sans mesure du bruit
de fond ne sélectionne pas le meilleur modèle : elle sélectionne la meilleure
graine. Un écart doit être comparé à la variabilité de la mesure avant d'être
interprété comme un effet. C'est une exigence élémentaire de méthode
expérimentale, et probablement l'apprentissage le plus transférable du projet —
il vaut pour toute comparaison de modèles, indépendamment du domaine.

---

## 6. Résultats

### 6.1. Pipeline de données et exposition (Binôme A)

| Indicateur | Valeur |
|---|---|
| Cellules réseau simulées | 5 |
| Période couverte | 14 jours (2026-08-02 → 2026-08-16) |
| Fréquence des mesures brutes | ≈ 1 point / minute / cellule |
| Lignes après nettoyage | 100 800 |
| Valeurs imputées (`is_missing`) | 0,0 % |
| Valeurs nulles résiduelles | 0 |
| Caractéristiques calculées par ligne | 43 |
| Fréquence du pipeline orchestré | toutes les 15 minutes |
| Cadence du flux quasi temps réel | 1 mesure / 5 secondes / cellule |
| Endpoints REST exposés | 9, documentés par OpenAPI |

**Fonctionnalités livrées.** Un générateur synthétique paramétrable ; un pipeline
de nettoyage **idempotent et rejouable sans effet de bord** ; un module de
caractéristiques produisant 43 colonnes dérivées par point, dont une développée à
la demande du Binôme B ; une API REST complète et auto-documentée ; un pipeline
orchestré par Airflow avec suivi visuel et reprise sur échec ; un simulateur de
flux quasi temps réel ; et une plateforme entièrement conteneurisée démarrable
en une commande.

**Contrôle de conformité automatique.** Le Binôme B exécute à chaque analyse
exploratoire une série de contrôles sur le flux servi — volumétrie, absence de
valeurs nulles, cohérence des bornes par KPI, continuité de la grille temporelle.
Résultat au jalon J30 : **aucune anomalie de conformité détectée**. Le flux servi
est conforme au contrat sur tous les points vérifiables automatiquement.

### 6.2. Analyse exploratoire : ce qu'elle a décidé (Binôme B)

L'analyse porte sur les 100 800 mesures. Elle a produit trois résultats qui ont
orienté toute la modélisation, et qui constituent à eux seuls une justification
du projet.

**Les indicateurs sont très inégalement discriminants.** Écart des moyennes entre
régime normal et régime anormal, exprimé en écarts-types du régime normal :

| Indicateur | Moyenne normale | Moyenne en anomalie | Séparabilité |
|---|---|---|---|
| `packet_loss` | 0,626 % | 7,234 % | **28,1 σ** |
| `latency` | 15,79 ms | 38,31 ms | 5,53 σ |
| `jitter` | 4,41 ms | 8,28 ms | 4,39 σ |
| `throughput` | 94,7 Mbit/s | 70,9 Mbit/s | 1,08 σ |
| `cell_load` | 64,8 % | 67,3 % | **0,10 σ** |

La charge de cellule, à 0,10 σ, n'est **pas** discriminante prise isolément —
alors que c'est l'indicateur auquel un exploitant penserait d'abord. Elle
n'apporte du signal qu'en interaction avec les autres, ce qui justifie un modèle
**multivarié** plutôt qu'un jeu de seuils indépendants.

**Les seuils du contrat sont déséquilibrés.** Appliqués avec la règle
d'agrégation prévue — l'état global est celui du pire indicateur — les seuils
figés en v1.1 déclarent l'état **critique 43,1 % du temps** et « bon » seulement
**8,3 %** :

| État global | Part du temps |
|---|---|
| bon | 8,33 % |
| dégradé | 48,58 % |
| critique | **43,10 %** |

Une plateforme de supervision qui alerte quatre jours sur dix ne transmet aucune
information. Le mécanisme est arithmétique et vaut d'être détaillé, car il
illustre un piège de conception général.

| Indicateur | bon | dégradé | critique |
|---|---|---|---|
| `throughput` | 25,8 % | 49,4 % | 24,8 % |
| `latency` | 81,8 % | 17,9 % | 0,3 % |
| `jitter` | 36,2 % | 37,9 % | 25,9 % |
| `packet_loss` | 30,5 % | 56,8 % | 12,6 % |
| `cell_load` | 54,5 % | 21,7 % | 23,9 % |

Chaque indicateur, pris isolément, est classé « bon » entre 26 % et 82 % du temps
— ce qui est raisonnable. Mais la règle du pire indicateur exige que **les cinq
soient simultanément bons**. Si les indicateurs étaient indépendants, la part de
temps « bon » global tomberait à 1,27 % ; on en observe 8,33 %, l'écart venant de
la corrélation entre indicateurs qui regroupe partiellement les dégradations sur
les mêmes instants.

Autrement dit : **les seuils ont été calibrés indicateur par indicateur, sans
tenir compte de la règle qui les combine.** Chaque seuil est défendable seul ;
leur conjonction ne l'est pas. Deux sont principalement en cause : le minimum de
débit en « bon » (107 Mbit/s, atteint 25,8 % du temps) et le maximum de gigue
(4,0 ms, 36,2 %).

**Conduite adoptée.** Le contrat v1.1 est gelé, et le §8.2 de la fiche identifie
son respect comme le facteur de réussite n°1. Le Binôme B ne l'a donc **pas
modifié** : les seuils servis par l'API restent la référence dans tout le code, y
compris là où ils produisent un résultat que nous jugeons inexploitable. Le
diagnostic chiffré a été transmis avec deux options de révision — recalibrer les
seuils par la cible d'agrégation, ou remplacer la règle du pire indicateur par
une règle à quorum — et le tableau de bord expose le déséquilibre pour que la
discussion se tienne sur des chiffres. Une révision en v1.2 reste à acter
conjointement (§7.2).

**Les seuils ne remplacent pas un détecteur.** Croisement de l'état QoS avec la
vérité terrain, en pourcentage par colonne :

| État par seuils | Instants normaux | Instants anormaux |
|---|---|---|
| bon | 8,4 % | 0,9 % |
| dégradé | 49,0 % | 13,4 % |
| critique | **42,5 %** | 85,8 % |

Deux lectures. D'une part, **14,2 % des anomalies réelles** ne sont pas classées
critique : ce sont les anomalies de forme, invisibles à un seuil d'amplitude.
D'autre part, **42,5 % des instants normaux** le sont : l'immense majorité des
alertes seraient fausses.

La classification par seuils et la détection apprise sont donc deux fonctions
**complémentaires et non redondantes** : la première qualifie l'état
d'exploitation au sens du SLA, la seconde signale l'atypique. C'est ce résultat
qui justifie l'existence de la couche d'intelligence.

**📷 Capture d'écran —** *figures de l'analyse exploratoire (`reports/figures/eda/`).*

### 6.3. Détection d'anomalies (Binôme B)

Quatre détecteurs, évalués sur le même segment de test — **19 850 points**,
prévalence 1,51 %, **9 épisodes** d'anomalie — au point de fonctionnement choisi
sans recours aux étiquettes.

| Détecteur | Précision | Rappel | F1 | PR-AUC | Fausses alertes / h | Épisodes détectés |
|---|---|---|---|---|---|---|
| Seuils du contrat | 0,026 | 0,703 | 0,051 | 0,023 | 0,553 | 9 / 9 |
| **Isolation Forest** | **0,616** | **0,647** | **0,631** | **0,586** | **0,018** | **9 / 9** |
| DBSCAN | 0,277 | 0,187 | 0,223 | 0,391 | 0,018 | 4 / 9 |
| Autoencodeur | 0,383 | 0,397 | 0,390 | 0,363 | 0,003 | 8 / 9 |

**Isolation Forest est le modèle retenu.** Il domine sur les deux métriques
décisives — F1 et PR-AUC — et surtout sur celle qui compte pour un exploitant :
il produit **0,018 fausse alerte par heure**, soit environ une tous les deux
jours, là où les seuils du contrat en produisent 0,553 — **trente fois plus**. Il
détecte les 9 épisodes sur 9, avec un délai médian de 13,5 minutes.

Deux résultats vont contre l'attente et méritent d'être soulignés.

**Le modèle avancé ne bat pas la baseline.** L'autoencodeur, le plus sophistiqué
des quatre, obtient une PR-AUC de 0,363 contre 0,586 pour Isolation Forest.
Conformément au §8.2 de la fiche — « un modèle avancé ne se justifie que s'il bat
la baseline » — **il n'est pas déployé**. Ce non-résultat est un résultat : sur
23 caractéristiques et un régime normal bien échantillonné, l'hypothèse
géométrique d'Isolation Forest — les anomalies sont isolables par peu de coupes
aléatoires — est mieux adaptée que l'apprentissage d'une variété de
reconstruction.

**Le classement dépend du point de fonctionnement.** DBSCAN passe de F1 = 0,223
au point d'exploitation à F1 = 0,624 à son point optimal — un rapport de près de
trois. Cet écart mesure la sensibilité du détecteur au choix du seuil, et c'est
une propriété opérationnelle en soi : un détecteur dont la performance s'effondre
si le seuil est mal choisi est un mauvais candidat au déploiement, même si son
optimum est bon. Isolation Forest, lui, varie de 0,631 à 0,635 — il est
pratiquement insensible à ce choix, ce qui est une seconde raison de le retenir.

**📷 Capture d'écran —** *onglet « KPI & anomalies » du tableau de bord.*

### 6.4. Prévision des KPI (Binôme B)

Cinq modèles, cinq indicateurs, trois horizons. Comparaison à la persistance en
gain d'erreur absolue moyenne :

| Horizon | Modèle retenu | Gain de MAE vs persistance |
|---|---|---|
| 5 min | XGBoost | **−10,0 %** |
| 15 min | XGBoost | **−14,6 %** |
| 30 min | XGBoost | **−20,7 %** |

Le gain **croît avec l'horizon**, ce qui est le comportement attendu et une
validation indirecte du modèle : à 5 minutes, la valeur actuelle est déjà une
excellente prédiction et il reste peu à gagner ; à 30 minutes, elle se dégrade et
la structure apprise — saisonnalité, corrélations entre indicateurs,
non-linéarités — prend le dessus.

ARIMA a été évalué comme baseline de référence, sur un sous-ensemble de **600
origines de prévision communes** à tous les modèles pour garantir la
comparabilité. Prophet et LSTM ont été **écartés par choix de périmètre
explicite**, et non par impossibilité technique (§7.4).

Un point technique mérite mention parce qu'il constituait un piège : la
construction des cibles se fait par **jointure temporelle** sur `(cell_id, ts+h)`
et non par décalage positionnel. Un décalage de `h` lignes serait faux dès qu'une
minute manque dans la série — la cible serait prise plus loin dans le futur que
l'horizon annoncé, et le modèle paraîtrait meilleur qu'il n'est. Un test dédié
vérifie ce comportement sur une série trouée (annexe E).

**📷 Capture d'écran —** *onglet « Prévision » du tableau de bord.*

### 6.5. De la prévision à la décision : l'état QoS annoncé (Binôme B)

Prévoir un indicateur n'a d'intérêt que si l'exploitant peut en tirer une
décision. Une couche applique donc les seuils du contrat aux **valeurs prévues**,
produisant un état QoS annoncé à 5, 15 et 30 minutes — ce qui transforme cinq
courbes en une information actionnable : *l'état va-t-il se dégrader ?*

| Horizon | Exactitude de l'état | Part des états critiques manqués |
|---|---|---|
| 5 min | 82,1 % | 14,2 % |
| 15 min | 82,3 % | 13,9 % |
| 30 min | 82,1 % | 14,7 % |

L'exactitude est remarquablement **stable de 5 à 30 minutes**, ce qui n'est pas
attendu puisque l'erreur de prévision croît avec l'horizon. L'explication est que
la classification en trois états est robuste à une petite erreur numérique : tant
que la valeur prévue reste du bon côté du seuil, l'erreur est sans conséquence
sur la décision. La conséquence pratique est favorable — l'annonce à 30 minutes
est aussi fiable que celle à 5 minutes, et laisse dix fois plus de temps pour
agir.

La part d'états critiques manqués, autour de 14 %, est le chiffre à surveiller :
c'est la proportion de dégradations réelles que l'annonce n'a pas vues venir.

### 6.6. Tableau de bord de supervision (Binôme B)

Six onglets, alimentés par l'API du Binôme A avec repli automatique sur les CSV
locaux si elle est indisponible.

| Onglet | Contenu |
|---|---|
| **Vue d'ensemble** | État QoS courant par cellule, alertes actives, volumétrie servie |
| **Temps réel** | Flux quasi temps réel rafraîchi par fragment, avec détection appliquée aux mesures qui arrivent |
| **KPI & anomalies** | Séries par indicateur, points détectés, superposition optionnelle de la vérité terrain à fins de démonstration |
| **Prévision** | Trajectoires prévues à 5 / 15 / 30 min et état QoS annoncé, avec sélecteur de modèle |
| **Qualité des modèles** | Métriques d'évaluation, courbes précision-rappel, matrices de confusion |
| **Intégration** | Provenance des données, disponibilité de l'API, modèles chargés |

Les contrôles communs — cellule, fenêtre d'observation, détecteur, sensibilité —
sont placés **au-dessus** des onglets, de sorte qu'un changement de cellule
s'applique partout. Le curseur de sensibilité expose la part d'alertes visée, ce
qui permet à un exploitant d'ajuster le compromis entre détections manquées et
fausses alertes selon sa tolérance au risque.

L'onglet **Intégration** rend l'état de la frontière A ↔ B visible à l'écran
plutôt que déductible des logs : trois modes de source de données sont
sélectionnables par la variable `NETQOS_DATA_SOURCE` — `api` (exclusif, échoue
explicitement, utilisé pour les tests d'intégration), `local` (hors ligne), et
`auto` (API puis repli annoncé). Cet onglet a considérablement accéléré le
diagnostic des difficultés §5.2, §5.4 et §5.5.

Le tableau de bord se teste **sans navigateur** au moyen de l'utilitaire de test
de Streamlit, ce qui permet de vérifier automatiquement qu'aucun onglet ne lève
d'exception.

**📷 Capture d'écran —** *onglet « Vue d'ensemble », contrôles communs visibles.*
**📷 Capture d'écran —** *onglet « Temps réel » pendant que le simulateur tourne.*
**📷 Capture d'écran —** *onglet « Intégration », source de données et URL de l'API.*

### 6.7. Intégration bout-en-bout (commun)

Le critère de réussite du jalon J21 imposait de vérifier que les données
produites par le pipeline du Binôme A étaient effectivement consommables par les
modèles et le tableau de bord du Binôme B. La validation a été menée des deux
côtés de la frontière.

**Côté producteur (Binôme A).** Vérification que les endpoints paginés renvoient
un format conforme à l'enveloppe commune ; vérification du comportement de repli
attendu côté client lorsque l'API n'est pas joignable — c'est ce contrôle qui a
permis de diagnostiquer le conflit de configuration du §5.2 ; validation du flux
quasi temps réel en lançant le simulateur et en confirmant côté client la
réception continue de nouvelles mesures.

**Côté consommateur (Binôme B).** Une procédure de vérification en **cinq
niveaux** a été formalisée dans `binome-b/GUIDE_TEST.md`, de la plus rapide à la
plus complète : suite de 60 tests automatisés sans dépendance externe (2
secondes), chaîne de modélisation hors ligne, chaîne complète contre l'API,
tableau de bord, et enfin intégration sur la stack Docker. Chaque étape indique
**la valeur attendue**, ce qui permet à un lecteur de constater un écart plutôt
que d'observer simplement que la commande s'est terminée.

C'est également le Binôme B qui a vérifié et **levé par écrit** la réserve
d'idempotence du §5.1, en constatant que deux exécutions consécutives du pipeline
réussissent et que les comptages restent stables.

**Résultat.** Le tableau de bord lit l'API en conditions réelles, y compris en
flux quasi temps réel. Les 43 caractéristiques servies sont directement
exploitables pour l'apprentissage, sans transformation supplémentaire côté
client. L'équivalence numérique entre la source API et la source locale a été
vérifiée colonne par colonne : écart maximal nul.

### 6.8. Pourquoi pas 90 à 100 % : le prix mesuré de la contrainte

Le modèle de détection retenu obtient F1 = 0,631 et PR-AUC = 0,586. On attend
spontanément d'un modèle d'apprentissage qu'il atteigne 90 à 100 % ; il faut donc
expliquer l'écart, et l'expliquer avec un chiffre plutôt qu'avec un argument.

Nous avons pour cela entraîné un **oracle supervisé** : un modèle ayant accès à
`is_anomaly` pendant son entraînement — ce que le contrat interdit — dans le seul
but de mesurer le plafond. Ce modèle n'est ni déployé, ni sauvegardé, ni utilisé
par le tableau de bord ; il ne sert qu'à cette mesure, et son fichier de
résultats porte cet avertissement.

| Modèle | PR-AUC | Précision | Rappel | F1 |
|---|---|---|---|---|
| Isolation Forest (non supervisé, **retenu**) | 0,586 | 0,616 | 0,647 | 0,631 |
| Oracle supervisé (interdit, **non déployé**) | **0,905** | 0,972 | 0,810 | 0,884 |

L'écart, **0,319 de PR-AUC**, est le prix de la contrainte non supervisée. Il
répond précisément à la question : les 90 % attendus sont atteignables sur ces
données — l'oracle les atteint — mais **uniquement avec accès aux étiquettes**,
ce que le §4.3 de la fiche exclut et ce qui correspond à la situation réelle d'un
réseau où les incidents ne sont pas annotés.

Cette conclusion est utile plutôt que défaitiste, pour deux raisons.

Elle **borne l'effort à consacrer au réglage.** Puisque l'essentiel de l'écart aux
90 % vient de la contrainte et non de la configuration du modèle, il n'y avait
rien à gagner à poursuivre la recherche d'hyperparamètres — ce que la mesure du
bruit de graine (§5.7) avait déjà indiqué indépendamment. Deux méthodes
distinctes convergent donc sur le même diagnostic.

Elle **indique où le progrès se trouve réellement** : non dans le modèle, mais
dans les données. Le segment de test ne contient que 9 épisodes d'anomalie, ce
qui limite fortement la puissance statistique de toute comparaison — un épisode
manqué fait varier le rappel par épisode de 11 points. Un jeu de données
comportant plus d'épisodes, et une plus grande diversité de formes d'anomalie,
améliorerait la mesure et probablement le modèle bien davantage que n'importe
quel réglage (§7.1).

Enfin, il faut rappeler à quoi la comparaison pertinente oppose ce modèle. Le
point de départ opérationnel n'est pas 100 %, c'est le jeu de seuils fixes, qui
obtient F1 = 0,051 et 0,553 fausse alerte par heure. Le modèle retenu multiplie
le F1 par **douze** et divise les fausses alertes par **trente**, sans jamais voir
une seule étiquette. C'est cela que le projet a produit.

---

## 7. Limites et perspectives

Cette section est délibérément détaillée. Un projet de quatre semaines ne peut
pas tout traiter, et nous jugeons plus utile de nommer précisément ce qui reste
ouvert que de présenter un bilan sans réserve.

### 7.1. Limites du jeu de données

**La densité d'anomalies est trop faible pour une évaluation robuste.** Neuf
épisodes seulement dans le segment de test : un épisode manqué déplace le rappel
par épisode de 11 points. C'est la limite principale de l'évaluation, et le
levier de progrès le plus important identifié au §6.8 — devant tout raffinement
de modèle.

**La diversité des formes d'anomalie est insuffisante.** Les anomalies du jeu
synthétique sont majoritairement des dégradations d'amplitude. Les anomalies de
forme — dérive lente, gigue anormale à charge normale — sont sous-représentées,
alors que ce sont précisément celles qu'un détecteur appris doit apporter par
rapport à un seuil.

**Le réalisme borne la validité externe.** Les données sont synthétiques : les
performances mesurées valent pour le simulateur, non pour un réseau réel. Une
validation sur des traces réelles serait la première étape d'une éventuelle
industrialisation.

**Perspective.** Enrichir le générateur en types d'anomalie (dérive progressive,
panne partielle, congestion corrélée entre cellules voisines) et augmenter leur
densité dans une période dédiée à l'évaluation. C'est un travail du Binôme A dont
le bénéfice est intégralement pour l'évaluation du Binôme B — un bon exemple
d'interdépendance que le projet a mis en évidence.

### 7.2. Limites du contrat d'interface v1.1

**Les seuils QoS restent déséquilibrés.** L'état critique couvre 43,1 % du temps
et l'état « bon » 8,3 % (§6.2). Le diagnostic chiffré et deux options de révision
ont été transmis ; le contrat étant gelé, aucune modification unilatérale n'a été
faite. Une **révision en v1.2** reste à acter conjointement, l'option préférable
étant de recalibrer les seuils `good_*` par la cible d'agrégation — ce qui
conserve une règle du pire indicateur simple et explicable à un exploitant.

**Les deux défauts de `/eval/labels` sont contournés, non corrigés à la source.**
Les contournements sont documentés et protégés par un garde-fou, mais ils
subsistent (§5.4, §5.5). Une correction côté A permettrait de les retirer et de
supprimer la convention d'agrégation à la minute qui, bien que conservatrice,
introduit une approximation.

**Le §5 de `data_dictionary.md` est périmé.** La liste d'endpoints qui y figure
(`/kpi/raw`, `/kpi/clean`, `/stream/latest`) est antérieure à l'API v1.1
réellement servie. Le document du contrat doit refléter l'implémentation, faute
de quoi un nouveau consommateur travaillerait contre une spécification fausse.

**Perspective.** Une version 1.2 du contrat regroupant ces trois corrections,
avec incrément de version documenté et communication explicite aux deux binômes
— la procédure que le contrat lui-même prévoit pour toute évolution de schéma.

### 7.3. Limites du pipeline de données

**Le pipeline retraite tout l'amont à chaque exécution.** Le nettoyage et le
calcul des caractéristiques relisent la table amont *en entier* à chaque tick de
quinze minutes. Le paramètre `since` existe dans les deux fonctions mais n'est
transmis ni par le script d'orchestration ni par le DAG. Il faut compter environ
trois minutes pour 100 000 lignes. C'est correct à l'échelle actuelle mais ne
tiendra pas sur un historique de plusieurs mois. L'**idempotence, elle, est
acquise** (§5.1) : c'est ce qui rend ce retraitement sans danger, seulement
coûteux.

**Les tests automatisés sont absents côté A.** Le Binôme B dispose de 60 tests
sur les invariants de son protocole ; le volet A n'en a aucun, et le dépôt n'a ni
linter ni formateur configuré. Un jeu de tests côté A aurait détecté plus tôt la
non-idempotence du §5.1 et les écarts d'enveloppe du §5.5.

**La gestion des secrets repose sur un fichier `.env` non chiffré.** Acceptable
en contexte académique, à faire évoluer vers un gestionnaire de secrets dans une
optique de production.

**Deux divergences de configuration subsistent.** Les valeurs par défaut de
`src/db.py` et celles de `.env.example` diffèrent, ce qui oblige à surcharger
`POSTGRES_HOST` pour exécuter les scripts hors conteneur.

**Perspective.** Transmettre `since` depuis le DAG pour ne retraiter qu'une
fenêtre récente ; ajouter une suite de tests côté A, en priorité sur
l'idempotence et sur la conformité de l'enveloppe de réponse de chaque endpoint —
les deux propriétés dont la violation a coûté le plus cher.

### 7.4. Limites des modèles

**Prophet et LSTM n'ont pas été évalués.** Ils ont été écartés par choix de
périmètre explicite : XGBoost devançait déjà nettement les baselines, et
l'essentiel du gain en prévision est venu du choix de la fonction de perte
(§5.6), non de la famille de modèle. Le rendement attendu paraissait donc faible
au regard du temps d'entraînement disponible. L'hypothèse n'a cependant pas été
testée, et c'est une limite assumée plutôt qu'un résultat.

**Le réentraînement n'est pas automatisé.** Les modèles sont entraînés par
commande explicite. Une industrialisation demanderait un réentraînement
périodique avec suivi de la dérive des données, hors périmètre de quatre
semaines.

**Le détecteur ne fournit pas d'explication.** Isolation Forest produit un score
d'atypicité, pas une cause. Un exploitant reçoit « ce point est anormal » sans
savoir quel indicateur en est responsable. C'est la fonctionnalité dont l'apport
opérationnel serait le plus élevé pour un effort modéré.

**Perspective.** Par ordre de rendement attendu décroissant : enrichir le jeu de
données en épisodes et en formes d'anomalie (§7.1) ; ajouter une attribution par
indicateur au détecteur, pour transformer une alerte en diagnostic ; évaluer un
modèle séquentiel de prévision une fois les deux premiers points traités.

### 7.5. Perspectives d'ensemble

Au-delà des points ci-dessus, trois directions donneraient à la plateforme une
valeur opérationnelle qu'elle n'a pas encore.

**Fermer la boucle de l'alerte.** La plateforme détecte et annonce, mais ne
notifie pas. Un canal de notification, et un journal des alertes acquittées par
l'exploitant, transformeraient un tableau de bord consulté en un outil de
travail. Ce journal fournirait par ailleurs, à terme, les étiquettes que l'absence
de vérité terrain nous a coûtées (§6.8) : un acquittement d'alerte est une
annotation.

**Valider sur des données réelles.** C'est la condition de toute conclusion
transférable, et le hors-périmètre le plus contraignant du projet.

**Industrialiser la surveillance des modèles.** Suivi de la dérive, alerte sur
dégradation des métriques, réentraînement déclenché. Le protocole d'évaluation et
les garde-fous développés côté B sont déjà la brique de base de cette
surveillance.

---

## 8. Bilan et compétences acquises

### 8.1. Compétences techniques — Binôme A

- Conception et implémentation d'un pipeline de données en Python (pandas,
  SQLAlchemy) : nettoyage, ré-échantillonnage temporel, ingénierie de
  caractéristiques sur séries temporelles (fenêtres glissantes, décalages,
  agrégats) ;
- modélisation et exploitation d'une base de séries temporelles (TimescaleDB /
  PostgreSQL), y compris la gestion fine des contraintes d'unicité et des
  stratégies d'*upsert* ;
- développement d'une API REST avec FastAPI dans le respect d'un contrat
  d'interface partagé avec une équipe tierce ;
- orchestration de traitements avec Apache Airflow : conception de DAG, gestion
  des dépendances, diagnostic par les logs et la vue Grid ;
- conteneurisation et composition multi-services avec Docker, y compris la
  résolution de conflits de configuration entre contributeurs ;
- compréhension du cycle de vie des volumes Docker et de la cohérence entre
  configuration et état persisté.

### 8.2. Compétences techniques — Binôme B

- **Détection d'anomalies non supervisée** : Isolation Forest, DBSCAN adapté à un
  usage inductif par distance aux points centraux, autoencodeur par erreur de
  reconstruction ; et surtout la convention de score et le **choix d'un point de
  fonctionnement sans recours aux étiquettes**, qui est le vrai problème pratique ;
- **prévision de séries temporelles** : approche multi-horizon directe,
  construction de cibles par jointure temporelle, baselines de référence
  (persistance, moyenne mobile, naïf saisonnier, ARIMA), et **alignement de la
  fonction de perte sur la métrique d'évaluation** (§5.6) ;
- **évaluation en contexte de fort déséquilibre** : choix de la PR-AUC plutôt que
  de la ROC-AUC ou de l'exactitude, et conception de métriques par épisode
  correspondant à l'usage réel — rappel par épisode, délai de détection, fausses
  alertes par heure ;
- **prévention de la fuite de données** sur séries temporelles : découpage
  chronologique, dimensionnement de la purge sur la plus longue fenêtre présente
  dans les caractéristiques, vérification par assertions automatisées ;
- **méthode expérimentale appliquée à l'apprentissage** : mesure du bruit de fond
  avant interprétation d'un écart, arbitrage variance / biais, et usage d'un
  oracle supervisé comme borne supérieure pour chiffrer le coût d'une contrainte ;
- **consommation d'une API REST tierce** : pagination robuste à une enveloppe
  incomplète, séparation des délais d'attente selon la nature de l'appel,
  détection de disponibilité et repli annoncé ;
- **restitution** : tableau de bord Streamlit multi-onglets avec rafraîchissement
  temps réel par fragment, et test automatisé de l'application sans navigateur ;
- **reproductibilité documentaire** : génération des rapports depuis les fichiers
  de métriques, export Word par gabarit, génération du schéma d'architecture par
  script.

### 8.3. Compétences méthodologiques et transversales (commun)

**Travailler de part et d'autre d'une interface que l'on ne contrôle pas.** C'est
l'apprentissage central du projet, et il est symétrique. Le Binôme A a dû
concevoir un pipeline et une API réutilisables par une équipe qui ne lit pas son
code ; le Binôme B a dû consommer une interface qu'il ne peut pas corriger, en se
comportant correctement quand le contrat n'est pas respecté et en signalant
l'écart par écrit plutôt que le corriger en silence.

**Diagnostiquer un échec silencieux.** Quatre des sept difficultés de la section
5 ne levaient aucune erreur. La première défense contre ce type de défaut est la
comparaison systématique d'une valeur mesurée à une valeur attendue — prévalence
attendue, volume attendu, sens attendu d'un gain — et ces comparaisons doivent
être **programmées**, pas laissées à la vigilance.

**Défendre un résultat, y compris décevant.** Rapporter que le modèle avancé ne
bat pas la baseline, ou que le F1 plafonne à 0,63, demande de pouvoir expliquer
*pourquoi* avec des chiffres. La borne oracle et la mesure du bruit de graine
n'améliorent aucun modèle ; elles rendent le résultat défendable, ce qui a plus
de valeur qu'un chiffre flatteur non expliqué.

**Respecter un contrat que l'on juge perfectible.** Le déséquilibre des seuils
QoS était un défaut réel dont le Binôme B aurait pu corriger l'effet dans son
code. Il ne l'a pas fait : le contrat était gelé, et une correction unilatérale
aurait produit deux définitions divergentes de l'état QoS entre les deux moitiés
de la plateforme. La conduite retenue — appliquer, documenter, transmettre un
diagnostic chiffré avec des options de révision — est celle qui préserve la
cohérence du système.

**Communication technique écrite** comme outil de travail et non comme formalité
de fin de projet, dans un contexte où les deux binômes ne travaillent pas en
présence continue.

**Rigueur de documentation au fil de l'eau**, notamment via des commentaires
explicatifs directement intégrés aux fichiers de configuration critiques pour
prévenir les régressions.

**Gestion du temps sur un planning contraint** : priorisation des correctifs
bloquants avant les optimisations non essentielles, et arbitrages de périmètre
**explicites et documentés** (Prophet et LSTM écartés par choix, non par
impossibilité) plutôt que silencieux.

---

## Conclusion

Le projet NetQoS-AI nous a conduits à construire, en quatre semaines, une
plateforme complète de supervision de la qualité de service réseau : de la
génération et de l'ingestion des indicateurs jusqu'à leur restitution dans un
tableau de bord, en passant par le stockage en base de séries temporelles,
l'exposition par une API REST, la détection d'anomalies non supervisée et la
prévision à court terme.

Le résultat quantitatif tient en une comparaison. Le point de départ opérationnel
— les seuils fixes du contrat — obtient un F1 de 0,051 et déclenche une fausse
alerte toutes les deux heures. Le modèle retenu obtient un F1 de 0,631 et une
fausse alerte tous les deux jours, détecte les neuf épisodes du segment de test,
et n'a jamais vu une seule étiquette d'anomalie. En prévision, le modèle avancé
devance la persistance de 10 à 21 % d'erreur absolue selon l'horizon, et l'état
QoS annoncé est correct dans 82 % des cas, aussi bien à 30 minutes qu'à 5. La
plateforme démarre en une commande sur une machine disposant de Docker.

Mais l'apprentissage principal de ce projet n'est pas dans ces chiffres. Il est
dans la nature des difficultés rencontrées, et dans le fait qu'elles se sont
réparties en deux familles très inégales.

Les pannes franches — un DAG qui échoue sur une violation de clé, une variable
d'environnement mal nommée, un volume Docker incohérent — sont visibles, et leur
résolution relève d'un diagnostic méthodique par isolement de la couche fautive.
Elles nous ont appris des principes solides : concevoir toute tâche ordonnancée
comme idempotente dès l'origine, tester l'intégration dans les conditions réelles
de déploiement et non seulement en local, et ne jamais supposer qu'un état
persisté suit la configuration qui l'a créé.

Les autres ne levaient **aucune erreur**. Un endpoint d'évaluation dont le format
rendait toute métrique nulle, une pagination qui s'arrêtait à 5 % des données, un
modèle qui optimisait autre chose que ce qu'on mesurait, et un gain
d'optimisation qui n'était que du bruit de graine. Chacune produisait un résultat
plausible, et trois auraient produit des chiffres *plus flatteurs* que la
réalité. C'est la classe de défaut la plus dangereuse dans un projet
d'apprentissage automatique, où l'on ne dispose pas d'une intuition préalable du
résultat correct.

La réponse que nous en avons tirée est méthodologique plutôt que technique :
programmer la détection de l'absurde — garde-fous levant des exceptions, tests
verrouillant les invariants silencieux, comparaison systématique du mesuré à
l'attendu — et mesurer le bruit de fond avant d'interpréter un écart. La borne
oracle supervisée et la mesure de variance par graine aléatoire n'ont amélioré
aucun modèle ; elles ont rendu les résultats défendables, ce qui, à la réflexion,
était l'objectif.

L'atteinte du jalon J21 reste le point d'orgue technique du projet : la preuve
concrète que deux volets développés en parallèle, sans accès mutuel au code ni
aux données de l'autre, s'intègrent sans friction majeure — à condition qu'un
contrat d'interface ait été rigoureusement défini dès la première semaine, et,
nous l'ajouterions volontiers à l'énoncé de la fiche, **rigoureusement vérifié
par les deux parties**. Un contrat qu'aucun des deux binômes ne contrôle
activement se dégrade en silence, et c'est précisément ce que quatre de nos sept
difficultés ont montré.

Cette expérience conforte notre intérêt pour les métiers de l'ingénierie des
données et de l'intelligence artificielle appliquée, et particulièrement pour ce
qui sépare un système qui fonctionne d'un résultat auquel on peut se fier.

---

## Annexes

### Annexe A — Structure du dépôt

```
netqos_ai/
├── docker-compose.yml            # toute la stack en une commande
├── .env.example
├── README.md
├── binome-a/                     # ingénierie des données & pipeline
│   ├── sql/init.sql              # trois hypertables TimescaleDB
│   ├── data_dictionary.md        # contrat de données
│   ├── airflow/
│   │   ├── Dockerfile
│   │   └── dags/netqos_pipeline_dag.py
│   └── src/
│       ├── db.py                 # moteur + upsert mutualisé
│       ├── generator/synthetic_generator.py
│       ├── ingestion/{batch_ingest,stream_simulator}.py
│       ├── preparation/{clean_prepare,build_features}.py
│       ├── orchestration/run_pipeline.py
│       └── api/main.py           # 9 endpoints /api/v1
├── binome-b/                     # IA & restitution
│   ├── src/
│   │   ├── config.py
│   │   ├── data/
│   │   │   ├── api_client.py     # SEUL point de contact avec le Binôme A
│   │   │   ├── local_source.py   # source de repli hors ligne
│   │   │   └── loader.py         # façade auto / api / local
│   │   ├── features/
│   │   │   ├── preprocessing.py  # caractéristiques dérivées, normalisation
│   │   │   └── splits.py         # découpage temporel, garde-fous anti-fuite
│   │   ├── models/
│   │   │   ├── anomaly.py        # 4 détecteurs non supervisés
│   │   │   ├── forecast.py       # 5 prévisionnistes multi-horizon
│   │   │   └── qos_state.py      # seuils du contrat → état QoS
│   │   ├── evaluation/metrics.py # métriques ponctuelles et par épisode
│   │   ├── dashboard/app.py      # tableau de bord 6 onglets
│   │   └── scripts/              # un livrable = une commande
│   ├── tests/                    # 60 tests sur les invariants du protocole
│   ├── GUIDE_TEST.md             # vérification en 5 niveaux
│   └── NOTICE_DASHBOARD.md
└── reports/                      # livrables communs
    ├── contrat_interface.docx
    ├── architecture_schema.png
    ├── rapport_eda.md
    ├── rapport_evaluation_modeles.md
    ├── rapport_projet_netqos_ai.md    # le présent document
    ├── figures/  metrics/
    └── docx/                     # exports Word (non versionnés)
```

### Annexe B — Exemple de réponse de l'API

`GET /api/v1/features?limit=2` — enveloppe commune et pagination :

```json
{
  "cell_id": null, "from": null, "to": null,
  "limit": 2, "offset": 0, "total": 100820,
  "has_more": true, "count": 2,
  "data": [
    {
      "ts": "2026-08-05T19:25:00Z", "cell_id": "cell_005",
      "throughput_mean_5m": 90.13, "throughput_std_15m": 4.21,
      "latency_mean_5m": 13.49, "latency_lag_5": 13.02,
      "packet_loss_mean_5m": 0.18, "cell_load_hour_max": 74.80,
      "hour_of_day": 19, "day_of_week": 2,
      "is_missing": false
    }
  ]
}
```

La colonne `is_anomaly` est **absente** de cette réponse, comme de toute réponse
autre que celle de `/eval/labels` : un filtre de l'API la retire par défaut.

### Annexe C — Extrait de code : l'*upsert* mutualisé (Binôme A)

Fonction partagée par `clean_prepare.py` et `build_features.py`, garantissant
l'idempotence des écritures (§5.1) :

```python
def upsert_on_conflict(table, conn, keys, data_iter):
    """Fonction passée à pandas.to_sql(method=...).

    Insère les lignes ; en cas de doublon sur la clé primaire
    (ts, cell_id), met à jour les valeurs existantes au lieu de
    lever une erreur. Indispensable pour un pipeline ré-exécuté
    toutes les 15 minutes avec des fenêtres glissantes de 60 min,
    qui se chevauchent donc nécessairement.
    """
    data = [dict(zip(keys, row)) for row in data_iter]
    stmt = pg_insert(table.table).values(data)
    update_cols = {c: stmt.excluded[c] for c in keys
                   if c not in ("ts", "cell_id")}
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts", "cell_id"], set_=update_cols,
    )
    conn.execute(stmt)
```

### Annexe D — Extrait de code : les garde-fous anti-fuite (Binôme B)

Extrait de `binome-b/src/features/splits.py`. Ces deux mécanismes sont la réponse
aux échecs silencieux des §5.4 et §5.6.

```python
def temporal_split(df, purge_minutes=60, ...):
    """Découpage chronologique par cellule, avec purge aux frontières.

    La purge vaut la plus longue fenêtre glissante présente dans les
    caractéristiques du Binôme A (60 min) : sans elle, un point
    d'entraînement situé juste avant la frontière renseignerait le
    segment de test, et les métriques seraient flatteuses et fausses.
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

### Annexe E — Extraits de code : non-supervision et cibles de prévision (Binôme B)

**La signature de `fit()` interdit l'usage des étiquettes.** La contrainte du
§4.3 de la fiche est tenue par l'interface, non par la discipline du développeur.

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

**Les cibles de prévision sont appariées par jointure temporelle**, non par
décalage positionnel :

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

### Annexe F — Reproduire les résultats de ce rapport

**Plateforme complète** (depuis la racine du dépôt) :

```bash
cp .env.example .env
docker compose up -d --build            # base + API + dashboard
docker compose --profile full up -d     # + Airflow
# Si un port est occupé :
#   POSTGRES_HOST_PORT=5433 API_PORT=8010 DASHBOARD_PORT=8511 docker compose up -d
```

Vérifications : API sur `http://localhost:8000/docs`, tableau de bord sur
`http://localhost:8501`, Airflow sur `http://localhost:8080`.

**Pipeline de données** (depuis `binome-a/`) :

```bash
pip install -r requirements.txt
python src/generator/synthetic_generator.py --cells 5 --days 14 \
    --out data/raw/historical_kpi.csv
python -m src.ingestion.batch_ingest --file data/raw/historical_kpi.csv
python -m src.orchestration.run_pipeline
python -m src.ingestion.stream_simulator --cells 5 --interval-seconds 5
uvicorn src.api.main:app --reload --port 8000
```

**Modèles et rapports** (depuis `binome-b/`) — fonctionnent contre l'API ou hors
ligne :

```bash
pip install -r requirements.txt
python -m pytest                        # 60 tests, ~2 s, sans base ni API
python -m src.scripts.run_eda           # -> reports/rapport_eda.md
python -m src.scripts.train_anomaly     # -> reports/metrics/anomalie_*
python -m src.scripts.train_forecast    # -> reports/metrics/prevision_*
python -m src.scripts.tune_anomaly      # -> optimisation + borne oracle
python -m src.scripts.tune_forecast     # -> sélection de la perte
python -m src.scripts.make_report       # -> rapport d'évaluation
python -m src.scripts.make_architecture # -> reports/architecture_schema.png
streamlit run src/dashboard/app.py

# Forcer la source de données
NETQOS_DATA_SOURCE=local python -m src.scripts.train_anomaly
NETQOS_DATA_SOURCE=api API_BASE_URL=http://localhost:8010/api/v1 \
    python -m src.scripts.run_eda
```

Procédure de vérification détaillée, avec les valeurs attendues à chaque étape :
`binome-b/GUIDE_TEST.md`.

### Annexe G — Documents de référence

| Document | Contenu |
|---|---|
| `reports/contrat_interface.docx` | Contrat d'interface v1.1, gelé le 2026-08-10 |
| `binome-a/data_dictionary.md` | Dictionnaire des données et des caractéristiques |
| `reports/rapport_eda.md` | Analyse exploratoire, diagnostic des seuils, décisions de cadrage |
| `reports/rapport_evaluation_modeles.md` | Protocole, comparaison baseline / avancé, analyse d'erreurs, campagne d'optimisation |
| `binome-b/NOTICE_DASHBOARD.md` | Notice d'utilisation du tableau de bord |
| `binome-b/GUIDE_TEST.md` | Vérification en cinq niveaux, avec valeurs attendues |
| `reports/support_soutenance.md` | Support de soutenance — 31 diapositives, exporté en `.pptx` |
| `reports/deroule_demo.md` | Déroulé minuté de la démonstration, vérifications préalables et points de repli |

### Annexe H — Glossaire

| Terme | Définition |
|---|---|
| **KPI** | *Key Performance Indicator* — indicateur clé de performance réseau |
| **QoS** | *Quality of Service* — qualité de service |
| **SLA** | *Service Level Agreement* — engagement contractuel de niveau de service |
| **Hypertable** | Table TimescaleDB partitionnée automatiquement par intervalle de temps |
| **Idempotence** | Propriété d'une opération produisant le même résultat qu'elle soit exécutée une ou plusieurs fois |
| **Upsert** | Opération combinant insertion et mise à jour conditionnelle (`INSERT ... ON CONFLICT`) |
| **DAG** | *Directed Acyclic Graph* — représentation d'un pipeline de tâches dans Airflow |
| **Fenêtre glissante** | Fenêtre mobile sur laquelle on calcule une statistique |
| **Non supervisé** | Apprentissage sans accès aux étiquettes de vérité terrain |
| **Vérité terrain** | Étiquette de référence (`is_anomaly`) servant uniquement à évaluer |
| **Fuite de données** | Information du segment de test parvenue à l'entraînement, produisant des métriques flatteuses et fausses |
| **Purge** | Zone retirée de part et d'autre d'une frontière de découpage, pour empêcher les fenêtres glissantes de faire fuir de l'information |
| **Prévalence** | Proportion de cas positifs — ici ≈ 1,5 % d'anomalies |
| **PR-AUC** | Aire sous la courbe précision-rappel ; métrique de référence en fort déséquilibre |
| **ROC-AUC** | Aire sous la courbe ROC ; optimiste et peu informative à faible prévalence |
| **MAE / RMSE / MAPE** | Erreur absolue moyenne / erreur quadratique moyenne / erreur absolue moyenne en pourcentage |
| **Épisode** | Suite d'instants anormaux consécutifs, correspondant à un incident pour l'exploitant |
| **Persistance** | Baseline de prévision annonçant que la valeur future égalera la valeur actuelle |
| **Oracle supervisé** | Modèle entraîné avec accès aux étiquettes, utilisé comme borne supérieure et non déployé |
