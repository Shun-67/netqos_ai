# Retours du Binôme B au Binôme A

**Objet** : points relevés sur le pipeline et l'API pendant l'intégration A ↔ B
**Date** : 23 août 2026 · **Contrat de référence** : interface v1.1 (figé le 10/08/2026)
**Émetteur** : Binôme B (IA & restitution) · **Destinataire** : Binôme A (ingénierie des données)

---

## Préambule

Ce document rassemble les points relevés en branchant nos modèles et notre
tableau de bord sur votre API réelle, dans la stack Docker. Chaque constat est
accompagné de la façon dont il a été vérifié, de son impact mesuré, et d'une
correction proposée. Rien ici ne repose sur une lecture de code seule : tout a
été observé en exécution.

**Ce qui fonctionne, et qu'il faut dire.** Le pipeline tourne de bout en bout :
100 800 lignes ingérées, nettoyées et transformées en 100 750 lignes de features
sans intervention. Les trois hypertables sont correctes, l'API répond, et la
documentation OpenAPI est générée. Nous avons pu reproduire vos règles de
nettoyage et de calcul de features à partir de votre seule documentation écrite,
et le résultat est **identique au bit près** à ce que sert votre API : écart
maximal de 0,0000000000 sur les 43 colonnes de features, 20 150 lignes appariées
sur 20 150. C'est la meilleure preuve que le contrat d'interface est correctement
spécifié.

**Votre travail sur Airflow est meilleur que le nôtre.** En fusionnant les deux
`docker-compose.yml`, nous avons repris votre section Airflow intégralement :
service `airflow-cleanup` pour le fichier `.pid` périmé, `LocalExecutor`,
métadonnées en PostgreSQL, délais relevés pour la synchronisation FAB sous Docker
Desktop Windows. Ces points viennent visiblement d'une mise en œuvre réelle ;
notre version restait théorique.

**Une réserve précédente est levée.** Nous avions signalé que `clean_prepare` et
`build_features`, insérant en `append` sur des tables à clé primaire
`(ts, cell_id)`, faisaient échouer toute seconde exécution et empêchaient le DAG
de se rafraîchir. Votre correctif par `db.upsert_on_conflict` fonctionne : nous
avons vérifié deux exécutions consécutives de `run_pipeline`, toutes deux en code
de sortie 0, avec des comptages stables (101 215 lignes nettoyées, 101 150
features). Le point est clos.

---

## Priorité 1 — `GET /eval/labels` est inexploitable pour évaluer

C'est le seul point réellement **bloquant** : il empêche de calculer la moindre
métrique de détection, et il le fait sans lever d'erreur.

### 1.1 Les horodatages ne sont pas rééchantillonnés

**Constat.** L'endpoint sert les `ts` de `raw_kpi_measurements` tels quels, alors
que `/kpi/history` et `/features` servent la grille rééchantillonnée à la minute
pleine.

```
GET /api/v1/eval/labels?cell_id=cell_001   ->  2026-07-28T20:21:41Z
GET /api/v1/kpi/history?cell_id=cell_001   ->  2026-07-28T20:21:00Z
```

**Impact mesuré.** Une jointure sur `(ts, cell_id)` — la seule possible, puisque
c'est la clé primaire du contrat — n'apparie **aucune** ligne. Les étiquettes
manquantes sont alors interprétées comme « pas d'anomalie », la prévalence tombe
à 0,00 %, et **toutes les métriques de détection s'effondrent à zéro**. Notre
première campagne d'évaluation contre votre API a produit F1 = 0,000 pour les
quatre détecteurs, sans qu'aucune exception ne soit levée. C'est le mode de
défaillance le plus coûteux : silencieux et plausible.

**Correction proposée.** Servir les horodatages alignés sur
`clean_kpi_measurements`, en agrégeant par `max` sur la minute — une minute est
anormale si au moins une mesure brute de cette minute l'était :

```sql
SELECT date_trunc('minute', ts) AS ts,
       cell_id,
       bool_or(is_anomaly) AS is_anomaly
FROM raw_kpi_measurements
WHERE ...
GROUP BY 1, 2
ORDER BY 1
```

Un endpoint d'évaluation doit être joignable aux données qu'il annote : c'est sa
seule raison d'être.

### 1.2 L'enveloppe de réponse est incomplète

**Constat.** L'endpoint accepte `limit` et `offset`, mais son enveloppe omet
`limit`, `offset`, `total` et `has_more`.

```
/eval/labels   ->  cell_id, count, from, to, usage
/features      ->  cell_id, count, from, to, limit, offset, total, has_more
/kpi/history   ->  cell_id, count, from, to, limit, offset, total, has_more
```

**Impact mesuré.** Un client qui déroule la pagination sur `has_more` — le
comportement que décrit votre propre README — s'arrête après la première page :
**5 000 étiquettes lues sur 100 800**, en silence.

**Correction proposée.** Aligner l'enveloppe sur celle des autres endpoints
paginés. C'est d'ailleurs ce que stipule le contrat : « Toutes les réponses
suivent une enveloppe commune (`cell_id`, `from`, `to`, `count`, `data`, plus
`limit`/`offset`/`total`/`has_more` pour les endpoints paginés). »

### Ce que nous avons fait en attendant

Deux contournements côté B, à **retirer** une fois l'endpoint corrigé :

- `loader.load_labels()` réaligne les étiquettes sur la grille minute ;
- `api_client._get_paginated()` poursuit la pagination tant que la page est
  pleine, à défaut de `has_more`.

Nous avons également ajouté un garde-fou : `splits.align_labels()` lève désormais
une exception si moins de 50 % des lignes trouvent leur étiquette, pour qu'une
telle panne ne puisse plus rester silencieuse.

---

## Priorité 2 — Les seuils QoS v1.1 sont déséquilibrés

**Constat.** Appliqués avec la règle d'agrégation « état de la cellule = pire de
ses cinq KPI », les seuils de `GET /api/v1/thresholds` produisent :

| État | Part du temps |
|---|---|
| bon | **8,33 %** |
| dégradé | 48,58 % |
| critique | **43,10 %** |

**Diagnostic.** La cause est arithmétique, et elle n'est pas dans les seuils pris
un par un. Voici l'état de chaque KPI isolément :

| KPI | bon | dégradé | critique |
|---|---|---|---|
| `latency` | 81,80 % | 17,91 % | 0,29 % |
| `cell_load` | 54,46 % | 21,68 % | 23,86 % |
| `jitter` | 36,23 % | 37,89 % | 25,87 % |
| `packet_loss` | 30,54 % | 56,82 % | 12,63 % |
| `throughput` | 25,82 % | 49,38 % | 24,79 % |

Chacun est défendable isolément. Mais l'agrégation exige que **les cinq soient
bons simultanément** : si les KPI étaient indépendants, la part de temps « bon »
global tomberait à 1,28 %. On observe 8,33 %, l'écart venant de la corrélation
entre KPI. Deux seuils tirent l'ensemble vers le bas à eux seuls :
`throughput.good_min = 107 Mbit/s` et `jitter.good_max = 4,0 ms`.

Autrement dit : **les seuils ont été calibrés indicateur par indicateur, sans
tenir compte de la règle qui les combine.**

**Impact.** Une plateforme de supervision qui déclare l'état critique 43 % du
temps perd toute valeur d'alerte. Cela plafonne aussi nos résultats de deux
façons mesurables :

- la baseline de détection par seuils obtient une **PR-AUC de 0,023** pour une
  prévalence de 1,51 % — soit le niveau du hasard — en déclarant **40,4 % du
  temps en alerte** ;
- l'exactitude de l'état QoS **prévu** par nos modèles est bornée à environ
  82 %, parce qu'avec 43 % du temps déjà classé critique, la frontière entre
  états est très sensible au bruit de prévision.

**Deux options pour une v1.2**, la décision vous appartenant :

- **Option A — recalibrer selon la cible d'agrégation.** Fixer les `good_*` de
  sorte que l'état global « bon » représente la part de temps visée (typiquement
  60–70 %), ce qui revient à relâcher `throughput` et `jitter`.
- **Option B — changer la règle d'agrégation.** Conserver les seuils et
  remplacer le « pire KPI » par une règle à quorum (critique si ≥ 2 KPI
  critiques), documentée dans le contrat.

Nous recommandons l'**option A** : elle conserve une règle d'agrégation simple et
explicable à un exploitant.

**Position du Binôme B.** Nous n'avons **rien modifié**. Les seuils servis par
l'API restent la référence dans tout notre code, y compris là où ils nous
desservent. Respecter le contrat gelé est le facteur de réussite n°1 identifié au
§8.2 du cahier des charges, et un changement unilatéral rendrait nos deux
travaux incomparables.

---

## Priorité 3 — Le contrat documenté ne décrit plus l'API servie

**Constat.** Le §5 de `binome-a/data_dictionary.md` liste six endpoints, dont
**quatre n'existent pas** dans l'API v1.1, et il en omet quatre qui existent.

| Documenté au §5 | Réalité |
|---|---|
| `/health` | conforme |
| `/cells` | conforme |
| `/kpi/raw` | n'existe pas |
| `/kpi/clean` | renommé `/kpi/history` |
| `/kpi/features` | renommé `/features` |
| `/stream/latest` | renommé `/kpi/stream` |
| *(absent du document)* | `/thresholds` |
| *(absent du document)* | `/eval/labels` |
| *(absent du document)* | `/kpi/latest` |
| *(absent du document)* | `/kpi/stream/info` |

**Impact.** Le contrat d'interface est un **livrable évalué au jalon J7** (§6.1
du cahier des charges). Un contrat qui ne décrit pas l'implémentation ne remplit
pas sa fonction : il n'aurait pas permis à un tiers de développer contre l'API.
Le §6 du même document prévoit d'ailleurs que « toute modification de colonne =
incrément de version documentée ici en haut de fichier » — la règle existe, elle
n'a simplement pas été appliquée aux endpoints.

**Correction proposée.** Mettre le §5 à jour depuis `binome-a/src/api/main.py`,
et incrémenter la version du document. Le tableau du README de `binome-a/` est,
lui, exact : il peut servir de source.

---

## Priorité 4 — Le pipeline retraite tout l'amont à chaque exécution

**Constat.** Le paramètre `since` existe dans `clean_and_prepare()` et
`build_features()`, mais n'est transmis ni par `run_pipeline.py` ni par le DAG
Airflow. Chaque exécution relit et réécrit donc l'intégralité de la table amont.

**Impact mesuré.** Environ **3 minutes pour 100 000 lignes**, à chaque tick de
15 minutes du DAG — y compris lorsqu'aucune donnée nouvelle n'est arrivée. Ce
n'est plus un problème de correction depuis votre correctif d'upsert, mais un
coût qui croîtra linéairement avec l'historique.

**Correction proposée.** Transmettre `since` depuis l'orchestrateur, par exemple
le maximum de `ts` déjà présent dans la table aval, moins une marge égale à la
plus longue fenêtre de features (60 minutes) pour que les fenêtres glissantes de
bord soient recalculées correctement. L'upsert rend cette marge sans risque : les
lignes recalculées écrasent simplement les précédentes.

---

## Priorité 5 — Densité d'anomalies trop faible pour une évaluation robuste

**Constat.** Le générateur injecte environ un événement pour 2 000 points. Sur
notre segment de test (20 % de l'historique, découpage chronologique), cela donne
**9 épisodes d'anomalie** pour 5 cellules, de durée médiane 36 minutes.

**Impact.** Nos quatre détecteurs atteignent tous 100 % de rappel par épisode. Ce
résultat flatteur n'a qu'une faible puissance statistique : l'intervalle de
confiance à 95 % d'une proportion de 9/9 descend à environ 70 %. **La métrique ne
départage donc pas les détecteurs**, et c'est le taux de fausses alertes par
heure qui doit s'y substituer — de 0,018/h pour l'Isolation Forest à 0,55/h pour
la baseline par seuils, soit un facteur 30.

**Correction proposée.** Augmenter la densité d'événements injectés (un pour 500
points, par exemple) ou allonger l'historique généré à 30–60 jours. La seconde
option a notre préférence : elle enrichit aussi la couverture de la saisonnalité
hebdomadaire, aujourd'hui à peine représentée sur 14 jours.

---

## Points communs et coordination

### `docker-compose.yml` : deux versions, désormais fusionnées

Le fichier était absent du dépôt alors que les trois README et le Dockerfile
Airflow s'y référaient : aucune commande de démarrage documentée ne fonctionnait,
et l'intégration A ↔ B était intestable. Nous en avons produit une version, vous
la vôtre ; elles ont été fusionnées lors du merge du 18 août. Trois points
appelaient une correction, signalés ici pour éviter qu'ils ne réapparaissent.

1. **Variable d'environnement du dashboard.** Le service déclarait
   `NETQOS_API_URL`, alors que notre client lit `API_BASE_URL`. La variable était
   donc ignorée, le dashboard retombait sur `http://localhost:8000` dans son
   propre conteneur, ne trouvait rien, et basculait en mode dégradé :
   **l'intégration A ↔ B semblait cassée alors que l'API répondait**. Le compose
   déclare désormais `API_BASE_URL`, et notre configuration accepte les deux noms
   pour que le problème ne se reproduise pas au prochain merge.
2. **Le dashboard était derrière `--profile full`.** Votre README affirme que
   « `main` doit toujours rester démarrable via `docker compose up -d` », et le
   jalon J21 se démontre précisément par le dashboard lisant l'API. Il est donc
   passé dans le profil par défaut, ce qui rend l'affirmation vraie.
3. **Ports figés.** `5432` et `8000` sont occupés sur nos machines de
   développement, ce qui faisait échouer le démarrage sur « port is already
   allocated ». Ils sont désormais surchargeables par `POSTGRES_HOST_PORT`,
   `API_PORT` et `DASHBOARD_PORT`, sans modification du fichier.

Nous avons également ajouté un service `stream-simulator` (profil `stream`) : le
simulateur devait être lancé à la main, donc `docker compose up` livrait une
plateforme sans flux, alors que l'exigence §3.2.1 en fait une capacité de la
plateforme.

### Divergence `src/db.py` / `.env.example`

`src/db.py` retient `netqos` comme nom de base par défaut, `.env.example` propose
`netqos_db`. Un script lancé hors conteneur sans `.env` vise donc une base
inexistante, et le message d'erreur PostgreSQL n'aide pas à comprendre pourquoi.
À aligner dans un sens ou dans l'autre.

### Aucun test automatisé côté A

Le §3.3 du cahier des charges demande que « chaque composante soit indépendante
et **testable** ». Nous avons mis en place une suite de 60 tests côté B
(`binome-b/tests/`, exécutable en 2 secondes sans base ni API), qui verrouille
les invariants dont une régression serait silencieuse. Il n'existe aucun test
côté A. Quelques tests sur vos règles de nettoyage — bornes de clipping, limite
d'interpolation à 3 points, régularité de la grille rééchantillonnée —
sécuriseraient le cœur du pipeline pour un coût faible, et couvriraient un
critère explicitement évalué.

### Question ouverte : le périmètre de la normalisation

Le §2.1 du cahier des charges place la « normalisation » dans votre périmètre.
Nous l'avons en pratique implémentée côté B (`RobustScaler` par cellule), pour
une raison de méthode : un scaler doit être ajusté sur le **seul segment
d'entraînement**, sinon les statistiques de validation et de test fuitent dans la
préparation. Le faire en amont, sur la table complète, introduirait cette fuite.

Ce n'est donc pas un manque de votre part, mais un écart au partage annoncé qu'il
faut pouvoir expliquer d'une seule voix en soutenance. À acter ensemble.

---

## Synthèse

| # | Point | Priorité | Effort estimé | Bloquant pour B ? |
|---|---|---|---|---|
| 1.1 | `/eval/labels` : horodatages non rééchantillonnés | **haute** | faible (une requête SQL) | oui, contourné |
| 1.2 | `/eval/labels` : enveloppe incomplète | **haute** | faible | oui, contourné |
| 2 | Seuils QoS déséquilibrés → v1.2 | **haute** | moyen (recalibrage + doc) | non, mais plafonne les résultats |
| 3 | `data_dictionary.md` §5 périmé | moyenne | faible | non |
| 4 | `since` non transmis → retraitement complet | moyenne | faible | non |
| 5 | Densité d'anomalies insuffisante | moyenne | faible (un paramètre) | non, mais limite l'évaluation |
| 6 | Divergence `db.py` / `.env.example` | basse | très faible | non |
| 7 | Aucun test automatisé côté A | basse | moyen | non |
| 8 | Périmètre de la normalisation | à acter | discussion | non |

Les points **1.1 et 1.2** sont ceux dont la correction nous permettrait de
retirer nos contournements et de présenter une chaîne d'évaluation propre en
soutenance. Ce sont aussi les moins coûteux à corriger.

Nous restons disponibles pour vérifier chaque correctif sur la stack, comme nous
l'avons fait pour l'idempotence.

---

## Pour reproduire nos constats

Tous les chiffres de ce document sont reproductibles depuis le dépôt :

```bash
# Diagnostic des seuils (§2) et conformité du flux servi
cd binome-b && python -m src.scripts.run_eda
#   -> reports/rapport_eda.md §6.1 et §8
#   -> reports/metrics/eda_etats_qos_par_kpi.csv

# Métriques de détection citées au §2 et §5
python -m src.scripts.train_anomaly
#   -> reports/metrics/anomalie_resultats.csv

# Défauts de /eval/labels (§1), sur la stack démarrée
NETQOS_DATA_SOURCE=api API_BASE_URL=http://localhost:8010/api/v1 \
  python -c "from src.data.api_client import ApiClient; \
             print(ApiClient().get_eval_labels(cell_id='cell_001').head())"

# Test d'idempotence du pipeline (préambule)
docker exec netqos_api python -m src.orchestration.run_pipeline   # deux fois
```

Procédure complète et valeurs attendues : `binome-b/GUIDE_TEST.md`.
