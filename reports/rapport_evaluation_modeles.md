# Rapport d'évaluation des modèles — Binôme B

**NetQoS-AI** · contrat d'interface v1.1 · livrable §6.3 de la fiche de stage

Rapport **généré** par `python -m src.scripts.make_report` à partir des fichiers de
`reports/metrics/`. Aucun chiffre n'y est saisi à la main : il se régénère à
l'identique après chaque réentraînement.

---

## 1. Protocole d'évaluation

### 1.1 Découpage temporel

Découpage strictement chronologique, **cellule par cellule** : 60 % entraînement,
20 % validation, 20 % test. Deux précautions qui vont au-delà de l'exigence
minimale du §4.3 de la fiche :

- **Découpage par cellule** et non global. Les features étant calculées par
  `cell_id`, un découpage sur le timestamp global mélangerait des cellules dont
  les historiques ne se recouvrent pas exactement.
- **Purge de 60 minutes** en tête des segments de validation et de test. Les
  features du contrat contiennent des fenêtres glissantes allant jusqu'à 60 min
  (`*_hour_mean`, `cell_load_hour_max`) : sans purge, les premières lignes de
  validation résument des mesures appartenant à l'entraînement. C'est une fuite
  discrète, qui gonfle les performances annoncées.

Le contrôle `TemporalSplit.assert_chronological()` vérifie à chaque exécution
qu'aucun timestamp de test ne précède un timestamp d'entraînement.

### 1.2 Étanchéité de la vérité terrain

`is_anomaly` n'est lue que par `loader.load_labels()`, appelée exclusivement au
moment du calcul des métriques. Le module de préparation maintient une liste
`FORBIDDEN_FEATURES` et lève `LeakageError` si l'une de ces colonnes atteint une
matrice de features. Aucun `fit()` du projet ne reçoit d'étiquette.

### 1.3 Métriques

| Famille | Métriques |
|---|---|
| Détection d'anomalies | précision, rappel, F1, matrice de confusion, **PR-AUC**, ROC-AUC |
| Détection — exploitation | rappel par épisode, délai de détection, fausses alertes par heure |
| Prévision | MAE, RMSE, MAPE, sMAPE, biais |
| Prévision — comparaison | *skill score* de MAE relatif à la persistance |
| Chaîne complète | exactitude de l'état QoS annoncé, part de critiques manqués |

Les trois métriques d'exploitation ne figurent pas dans la liste minimale de la
fiche mais sont décisives : une précision par point ne dit pas si l'exploitant
aurait été averti, ni combien de fausses alertes il aurait dû trier.


### 1.4 Comparabilité avec ARIMA

ARIMA exige un réajustement par origine de prévision, ce qui interdit de
l'évaluer sur les 19 820 points du test. Il est donc évalué sur
600 origines régulièrement espacées, et **tous les autres modèles
sont réévalués sur ces mêmes origines** pour que les MAE soient commensurables.
Le périmètre `test_complet` reporte en parallèle les modèles rapides sur la
totalité du segment.


---

## 2. Détection d'anomalies

### 2.1 Résultats au point de fonctionnement d'exploitation

Seuil fixé au quantile de contamination visée, calculé sur le segment
d'entraînement — **aucune étiquette n'intervient**. C'est le seul point de
fonctionnement atteignable dans un déploiement réel sans historique annoté.

| detecteur        |   precision |   rappel |     f1 |   pr_auc |   roc_auc |   taux_alerte_pct |   rappel_episode |   fausses_alertes_par_heure |
|:-----------------|------------:|---------:|-------:|---------:|----------:|------------------:|-----------------:|----------------------------:|
| isolation_forest |      0.6502 |   0.6567 | 0.6534 |   0.6137 |    0.9527 |            1.5264 |           1      |                      0.0211 |
| autoencodeur     |      0.3636 |   0.3867 | 0.3748 |   0.3628 |    0.947  |            1.6071 |           1      |                      0.0091 |
| dbscan           |      0.2836 |   0.19   | 0.2275 |   0.3895 |    0.9543 |            1.0126 |           0.4444 |                      0.0181 |
| seuils_contrat   |      0.0289 |   0.8233 | 0.0558 |   0.0266 |    0.7021 |           43.068  |           1      |                      0.6344 |

### 2.2 Résultats au point F1-optimal (borne haute)

Seuil choisi sur le segment de validation à l'aide des étiquettes, puis appliqué
au test. Les étiquettes n'entrent dans aucun `fit` : il s'agit de sélection de
modèle, pas d'entraînement supervisé. Ces chiffres constituent néanmoins une
**borne haute**, atteignable seulement si l'exploitant dispose d'un historique
d'incidents annoté.

| detecteur        |   precision |   rappel |     f1 |   pr_auc |   roc_auc |   taux_alerte_pct |   rappel_episode |   fausses_alertes_par_heure |
|:-----------------|------------:|---------:|-------:|---------:|----------:|------------------:|-----------------:|----------------------------:|
| isolation_forest |      0.7216 |   0.6133 | 0.6631 |   0.6137 |    0.9527 |            1.2846 |                1 |                      0.0091 |
| autoencodeur     |      0.4927 |   0.7867 | 0.6059 |   0.3628 |    0.947  |            2.4131 |                1 |                      0.0091 |
| dbscan           |      0.5177 |   0.6833 | 0.5891 |   0.3895 |    0.9543 |            1.995  |                1 |                      0.0423 |
| seuils_contrat   |      0.0289 |   0.8233 | 0.0558 |   0.0266 |    0.7021 |           43.068  |                1 |                      0.6344 |

### 2.3 Comparaison indépendante du seuil

| detecteur        |   pr_auc |   roc_auc |
|:-----------------|---------:|----------:|
| isolation_forest |   0.6137 |    0.9527 |
| dbscan           |   0.3895 |    0.9543 |
| autoencodeur     |   0.3628 |    0.947  |
| seuils_contrat   |   0.0266 |    0.7021 |

Deux enseignements méthodologiques :

1. **La ROC-AUC est trompeuse ici.** Elle dépasse 0,94 pour les trois détecteurs
   appris, y compris pour ceux dont la précision d'exploitation est médiocre.
   Avec une prévalence de 1.51 %, la ROC-AUC est dominée par la
   facilité à classer correctement les négatifs, qui sont écrasants. La PR-AUC,
   elle, sépare franchement les détecteurs. C'est elle qui est retenue comme
   métrique de référence.
2. **La baseline par seuils est disqualifiée.** Sa PR-AUC de
   0.027 est de l'ordre de la prévalence
   (1.51 % ≈ 0.0151), soit le niveau d'un tirage
   aléatoire. Elle atteint pourtant un rappel de 0.82 — mais
   en déclarant 43.1 % du temps en alerte, ce qui
   n'est pas exploitable. C'est la traduction chiffrée du déséquilibre des seuils
   v1.1 diagnostiqué au §6.1 du rapport d'EDA.

### 2.4 Réglage de l'autoencodeur

Grille explorée, sélection sur la PR-AUC de validation :

| goulot       |   filtrage_extremes |   lignes_entrainement |   pr_auc_validation |
|:-------------|--------------------:|----------------------:|--------------------:|
| (16, 6, 16)  |                0.05 |                 57427 |              0.448  |
| (16, 8, 16)  |                0    |                 60450 |              0.4229 |
| (20, 10, 20) |                0.02 |                 59241 |              0.3899 |
| (16, 8, 16)  |                0.02 |                 59241 |              0.378  |
| (12, 4, 12)  |                0.02 |                 59241 |              0.3545 |

### 2.5 Verdict baseline vs modèle avancé

L'**autoencodeur ne bat pas la baseline apprise**. Sa PR-AUC (0.363) reste inférieure à celle de l'Isolation Forest (0.614), et son F1 au point d'exploitation (0.375) est nettement en dessous (0.653). Conformément au §8.2 de la fiche — « un modèle avancé ne se justifie que s'il bat la baseline » — **le modèle retenu pour le déploiement est l'Isolation Forest**, et non l'autoencodeur.

Interprétation de cet échec — elle est instructive et non anecdotique. Comparons
l'écart de F1 entre le seuil non supervisé et le seuil optimal, qui mesure la
sensibilité de chaque détecteur au calibrage de son seuil :

| detecteur        |   ecart_f1_optimal_moins_exploitation |
|:-----------------|--------------------------------------:|
| dbscan           |                                 0.362 |
| autoencodeur     |                                 0.231 |
| isolation_forest |                                 0.01  |
| seuils_contrat   |                                 0     |

Deux détecteurs sont fortement dépendants de leur calibrage : DBSCAN
(+0.362) et l'autoencodeur (+0.231). Tous
deux fondent leur score sur une **distance ou une erreur non bornée**, dont la
distribution se déplace d'un segment temporel à l'autre : un seuil calibré sur
l'entraînement se retrouve mal placé au test. L'Isolation Forest, dont le score
est une profondeur d'isolement normalisée et bornée, ne perd que
+0.010 — c'est sa robustesse au calibrage, autant que sa
PR-AUC, qui la désigne pour le déploiement : en exploitation réelle, on ne
dispose pas d'étiquettes pour régler le seuil.

Sur ce volume de données et cet espace de features, la complexité supplémentaire
de l'autoencodeur n'achète donc rien — ni en pouvoir discriminant (PR-AUC
inférieure), ni en robustesse opérationnelle.

### 2.6 Analyse d'erreurs par épisode

Les métriques ponctuelles ne disent pas si un exploitant aurait été
averti. On raisonne donc par **épisode** : un intervalle contigu d'anomalie réelle.

| Grandeur | Valeur |
|---|---|
| Épisodes dans le segment de test | 9 |
| Épisodes détectés au moins une fois | 9 |
| Épisodes manqués | 0 |
| Durée médiane des épisodes détectés | 36 min |
| Part médiane de points détectés par épisode | 70% |

| cell_id   | debut                     |   duree_min | detecte   |   part_points_detectes |   pic_latence_ratio |   pic_packet_loss |   score_max |
|:----------|:--------------------------|------------:|:----------|-----------------------:|--------------------:|------------------:|------------:|
| cell_001  | 2026-08-09 11:55:00+00:00 |           6 | True      |                  1     |               4.504 |            79.058 |      0.7402 |
| cell_001  | 2026-08-10 17:34:00+00:00 |          25 | True      |                  0.96  |               1.001 |             0.866 |      0.6763 |
| cell_001  | 2026-08-11 02:30:00+00:00 |          27 | True      |                  0.704 |               2.255 |             2.294 |      0.6267 |
| cell_002  | 2026-08-09 11:21:00+00:00 |          32 | True      |                  0.562 |               1.984 |             2.578 |      0.5852 |
| cell_004  | 2026-08-11 05:41:00+00:00 |          36 | True      |                  0.778 |               2.256 |             2.792 |      0.6374 |
| cell_004  | 2026-08-10 00:27:00+00:00 |          38 | True      |                  0.737 |               2.175 |             2     |      0.6295 |
| cell_004  | 2026-08-10 05:09:00+00:00 |          38 | True      |                  0.526 |               1.888 |             1.798 |      0.6172 |
| cell_002  | 2026-08-10 16:00:00+00:00 |          40 | True      |                  0.6   |               1.887 |             2.758 |      0.5961 |
| cell_004  | 2026-08-11 06:42:00+00:00 |          58 | True      |                  0.517 |               1.701 |             2.242 |      0.5958 |

Lecture : le détecteur retenu signale **tous** les épisodes du segment de test.
Il ne les couvre en revanche que partiellement — la part médiane de points
détectés par épisode est de 70%. Pour
un usage de supervision, c'est le comportement souhaitable : l'alerte est levée,
l'exploitant investigue, et la précision par point importe moins que l'absence
d'angle mort.

> **Limite statistique à énoncer clairement.** Le segment de test ne contient que
> 9 épisodes, parce que le générateur du Binôme A injecte environ un
> événement pour 2 000 points. Un rappel par épisode de 100 % sur 9 épisodes n'a
> qu'une faible puissance statistique : l'intervalle de confiance à 95 % de cette
> proportion descend à environ 70 %. **Cette métrique ne permet donc pas de
> départager les détecteurs** (les quatre atteignent 1,00), et c'est le taux de
> fausses alertes par heure qui les discrimine réellement — de 0,02/h pour
> l'Isolation Forest à 0,63/h pour la baseline par seuils, soit un facteur 30.
> Demande adressée au Binôme A : augmenter la densité d'événements injectés
> (ou allonger l'historique généré) pour obtenir une évaluation par épisode
> robuste avant la soutenance.



---

## 3. Prévision des KPI

### 3.1 Comparaison des modèles

#### Périmètre : `origines_communes`

Gain de MAE relatif à la persistance (%, moyenne sur les 5 KPI) — positif = meilleur :

| modele              |      5 |     15 |     30 |
|:--------------------|-------:|-------:|-------:|
| arima               |   1.37 |  -0.26 |  -1.7  |
| moyenne_mobile_15m  |   0.61 |   1.55 |   2.08 |
| naif_saisonnier_24h | -36.22 | -21.05 | -12.2  |
| persistance         |   0.01 |   0    |  -0    |
| xgboost             |   8.67 |  13.59 |  21.61 |

MAE détaillée par KPI et horizon :

|                     |   arima |   moyenne_mobile_15m |   naif_saisonnier_24h |   persistance |   xgboost |
|:--------------------|--------:|---------------------:|----------------------:|--------------:|----------:|
| ('cell_load', 5)    |  4.0767 |               4.0786 |                5.0597 |        4.1705 |    3.7168 |
| ('cell_load', 15)   |  4.6822 |               4.6978 |                5.2403 |        4.7428 |    4.0182 |
| ('cell_load', 30)   |  5.1747 |               5.1751 |                5.5299 |        5.0772 |    3.9324 |
| ('jitter', 5)       |  0.2472 |               0.2459 |                0.349  |        0.2615 |    0.2386 |
| ('jitter', 15)      |  0.2883 |               0.2774 |                0.3556 |        0.2926 |    0.2541 |
| ('jitter', 30)      |  0.32   |               0.3064 |                0.3761 |        0.3214 |    0.2604 |
| ('latency', 5)      |  1.0722 |               1.21   |                1.6546 |        1.0908 |    0.9815 |
| ('latency', 15)     |  1.3582 |               1.3966 |                1.6868 |        1.3483 |    1.1351 |
| ('latency', 30)     |  1.5485 |               1.4727 |                1.5187 |        1.4964 |    1.0546 |
| ('packet_loss', 5)  |  0.1886 |               0.1742 |                0.252  |        0.18   |    0.1686 |
| ('packet_loss', 15) |  0.1878 |               0.1766 |                0.234  |        0.1818 |    0.1629 |
| ('packet_loss', 30) |  0.1907 |               0.1767 |                0.2394 |        0.1869 |    0.1594 |
| ('throughput', 5)   |  2.4344 |               2.4241 |                3.3514 |        2.4886 |    2.3053 |
| ('throughput', 15)  |  2.9562 |               2.8859 |                3.5294 |        2.9555 |    2.5626 |
| ('throughput', 30)  |  3.353  |               3.2831 |                3.4852 |        3.3045 |    2.5679 |

#### Périmètre : `test_complet`

Gain de MAE relatif à la persistance (%, moyenne sur les 5 KPI) — positif = meilleur :

| modele              |      5 |     15 |     30 |
|:--------------------|-------:|-------:|-------:|
| moyenne_mobile_15m  |   1.05 |   0.95 |   1.26 |
| naif_saisonnier_24h | -34.12 | -24.12 | -12.92 |
| persistance         |   0    |   0    |  -0.01 |
| xgboost             |   9.78 |  14.31 |  21.22 |

MAE détaillée par KPI et horizon :

|                     |   moyenne_mobile_15m |   naif_saisonnier_24h |   persistance |   xgboost |
|:--------------------|---------------------:|----------------------:|--------------:|----------:|
| ('cell_load', 5)    |               4.052  |                5.2601 |        4.1748 |    3.8207 |
| ('cell_load', 15)   |               4.3559 |                5.2612 |        4.3795 |    3.8297 |
| ('cell_load', 30)   |               5.0844 |                5.2595 |        4.9839 |    3.8502 |
| ('jitter', 5)       |               0.2658 |                0.3789 |        0.2745 |    0.2504 |
| ('jitter', 15)      |               0.2821 |                0.3788 |        0.2885 |    0.2599 |
| ('jitter', 30)      |               0.2983 |                0.3788 |        0.3088 |    0.2603 |
| ('latency', 5)      |               1.2247 |                1.7267 |        1.1498 |    1.0585 |
| ('latency', 15)     |               1.4188 |                1.7273 |        1.3936 |    1.1323 |
| ('latency', 30)     |               1.5379 |                1.727  |        1.5703 |    1.1811 |
| ('packet_loss', 5)  |               0.2225 |                0.2879 |        0.2287 |    0.1924 |
| ('packet_loss', 15) |               0.228  |                0.2878 |        0.2356 |    0.1931 |
| ('packet_loss', 30) |               0.2305 |                0.2877 |        0.2407 |    0.1944 |
| ('throughput', 5)   |               2.6833 |                3.6082 |        2.7647 |    2.5485 |
| ('throughput', 15)  |               2.9134 |                3.6064 |        2.9301 |    2.5699 |
| ('throughput', 30)  |               3.4188 |                3.6045 |        3.3729 |    2.5759 |


### 3.2 Sélection de l'objectif d'apprentissage — le résultat le plus instructif

| kpi         |   horizon_min | objectif          |   mae_validation | retenu   |
|:------------|--------------:|:------------------|-----------------:|:---------|
| throughput  |             5 | reg:squarederror  |          2.80368 | False    |
| throughput  |             5 | reg:absoluteerror |          2.75544 | True     |
| throughput  |            15 | reg:squarederror  |          2.96255 | False    |
| throughput  |            15 | reg:absoluteerror |          2.79983 | True     |
| throughput  |            30 | reg:squarederror  |          3.03908 | False    |
| throughput  |            30 | reg:absoluteerror |          2.83197 | True     |
| latency     |             5 | reg:squarederror  |          1.21732 | False    |
| latency     |             5 | reg:absoluteerror |          1.02506 | True     |
| latency     |            15 | reg:squarederror  |          1.3198  | False    |
| latency     |            15 | reg:absoluteerror |          1.0664  | True     |
| latency     |            30 | reg:squarederror  |          1.47411 | False    |
| latency     |            30 | reg:absoluteerror |          1.08512 | True     |
| jitter      |             5 | reg:squarederror  |          0.29104 | False    |
| jitter      |             5 | reg:absoluteerror |          0.28031 | True     |
| jitter      |            15 | reg:squarederror  |          0.32315 | False    |
| jitter      |            15 | reg:absoluteerror |          0.2887  | True     |
| jitter      |            30 | reg:squarederror  |          0.34604 | False    |
| jitter      |            30 | reg:absoluteerror |          0.29201 | True     |
| packet_loss |             5 | reg:squarederror  |          0.35093 | False    |
| packet_loss |             5 | reg:absoluteerror |          0.25188 | True     |
| packet_loss |            15 | reg:squarederror  |          0.37799 | False    |
| packet_loss |            15 | reg:absoluteerror |          0.25262 | True     |
| packet_loss |            30 | reg:squarederror  |          0.382   | False    |
| packet_loss |            30 | reg:absoluteerror |          0.25334 | True     |
| cell_load   |             5 | reg:squarederror  |          3.8434  | False    |
| cell_load   |             5 | reg:absoluteerror |          3.81657 | True     |
| cell_load   |            15 | reg:squarederror  |          3.88202 | False    |
| cell_load   |            15 | reg:absoluteerror |          3.83715 | True     |
| cell_load   |            30 | reg:squarederror  |          3.91784 | False    |
| cell_load   |            30 | reg:absoluteerror |          3.87973 | True     |

Ce tableau documente une erreur corrigée en cours de route, qu'il vaut la peine
d'expliciter. Une première version entraînait XGBoost avec l'objectif par défaut
`reg:squarederror`. Résultat : le modèle « avancé » était **battu par la
persistance** (jusqu'à −45 % de MAE sur `packet_loss`), avec un biais positif
systématique de +0,107 pour un KPI dont la MAE n'est que d'environ 0,23.

Diagnostic : la cible est à queue lourde. `packet_loss` vaut typiquement 0,6 %
mais atteint 80 % pendant une panne ; l'erreur quadratique, qui pénalise le carré
de l'écart, déplace la prédiction vers la moyenne conditionnelle et donc vers le
haut sur les 98,5 % de points normaux. La correction consiste à **aligner la
fonction de perte sur la métrique d'évaluation** : `reg:absoluteerror` optimise
la médiane conditionnelle, robuste aux queues. Cet objectif a été retenu par la
sélection sur validation pour **les 15 modèles** (5 KPI × 3 horizons), sans
exception.

Leçon transférable : sur des séries à événements extrêmes, le choix de la
fonction de perte pèse davantage que le choix de la famille de modèles.

### 3.3 Gain du modèle avancé par horizon

Gain de MAE de XGBoost sur la persistance (%, test complet) :

|   horizon_min |   gain_moyen_pct |
|--------------:|-----------------:|
|             5 |              9.8 |
|            15 |             14.3 |
|            30 |             21.2 |

Détail par KPI :

| kpi         |    5 |   15 |   30 |
|:------------|-----:|-----:|-----:|
| cell_load   |  8.5 | 12.6 | 22.8 |
| jitter      |  8.8 |  9.9 | 15.7 |
| latency     |  7.9 | 18.8 | 24.8 |
| packet_loss | 15.9 | 18   | 19.2 |
| throughput  |  7.8 | 12.3 | 23.6 |

Le gain **croît avec l'horizon** — c'est le comportement attendu et il valide la
démarche : à 5 minutes, la persistance est déjà excellente sur une série
fortement autocorrélée, et le modèle n'a que peu à ajouter ; à 30 minutes, la
persistance décroche et l'information portée par la saisonnalité et les
interactions entre KPI devient déterminante. Un modèle qui n'aurait pas montré
cette progression aurait signalé une fuite ou une erreur d'alignement des cibles.

### 3.4 Verdict baseline vs modèle avancé

**XGBoost bat toutes les baselines sur tous les horizons** et est donc retenu.

Deux baselines méritent un commentaire, parce que leur échec est informatif :

- **Le naïf saisonnier à 24 h est la plus mauvaise référence** (jusqu'à
  52 %
  de MAE en plus que la persistance). Il exploite exactement la composante que
  Prophet modélise. Son échec confirme le cadrage de l'EDA — à 5–30 min la
  dynamique autorégressive domine largement la saisonnalité journalière — et
  justifie a posteriori d'avoir écarté Prophet.
- **ARIMA n'apporte rien** : son gain sur la persistance est de +1.4 % à 5 min, -0.3 % à 15 min, -1.7 % à 30 min. Un ARIMA ajusté sur une
  fenêtre de 24 h capture le niveau local et une autocorrélation à court terme,
  ce que la persistance et la moyenne mobile fournissent déjà pour un coût nul.
  Ce qu'il ne peut pas capturer, c'est l'information **inter-KPI** : que la
  latence va monter parce que la charge cellulaire monte. C'est précisément là
  que XGBoost gagne, et cela explique que son avance croisse avec l'horizon.

### 3.5 De la prévision à la décision : état QoS annoncé

Un exploitant ne consomme pas une latence en millisecondes, il consomme un état
annoncé. On applique donc les seuils du contrat aux KPI **prévus**, et on compare
à l'état réellement observé à `t + h`.

|   horizon_min |   exactitude_etat |   part_critiques_manques |     n |
|--------------:|------------------:|-------------------------:|------:|
|             5 |            0.8345 |                   0.1362 | 19820 |
|            15 |            0.8323 |                   0.1483 | 19820 |
|            30 |            0.8339 |                   0.1533 | 19820 |

Lecture : l'état QoS annoncé est correct pour environ 83 % des points, et cette
exactitude ne se dégrade quasiment pas entre 5 et 30 minutes — la chaîne complète
tient donc sur l'horizon utile. La part de dégradations critiques manquées
(environ 13–15 %) est la métrique à surveiller en priorité : c'est le risque
d'exploitation résiduel. Elle est cependant à interpréter à la lumière du
déséquilibre des seuils v1.1 (§6.1 du rapport d'EDA) : avec 43 % du temps déjà
classé critique, la frontière entre états est très sensible au bruit de
prévision. Un recalibrage en v1.2 devrait mécaniquement l'améliorer.


---

## 4. Modèles écartés, et pourquoi

| Modèle | Statut | Motif |
|---|---|---|
| **Prophet** | écarté | Installable (1.3.0 sur Python 3.13) — l'exclusion est méthodologique, non technique. Prophet décompose tendance + saisonnalité, ce qui répond à une question à horizon jours/semaines. L'EDA montre qu'à 5–30 min le signal dominant est autorégressif ; le naïf saisonnier à 24 h, qui exploite exactement la composante que Prophet modélise, est la plus mauvaise de nos baselines (jusqu'à −34 % vs persistance). Prophet aurait de plus exigé un ajustement par cellule et par KPI, soit 25 modèles, pour une information déjà portée par les encodages cycliques. |
| **LSTM / GRU** | écarté | Gain attendu marginal sur 60 000 lignes tabulaires dont la structure temporelle est déjà encodée dans les lags et fenêtres livrés par le Binôme A. Coût : une dépendance TensorFlow ou PyTorch, un temps d'entraînement sans commune mesure, et une reproductibilité plus fragile. Le §7 de la fiche laisse ce choix à l'appréciation du niveau ; le rapport coût/bénéfice ne le justifie pas ici. |
| **DBSCAN** | conservé comme baseline, non déployé | Transductif par nature : aucune méthode `predict`. Contourné en indexant les points de cœur et en scorant par distance au cœur le plus proche, ce qui fournit en prime un score continu. Reste inférieur à l'Isolation Forest et coûteux en O(n²). |
| **Autoencodeur** | implémenté et évalué, non déployé | Battu par l'Isolation Forest — voir §2.5. Conservé dans le dépôt car il apporte l'explicabilité par contribution de features (`explain()`), utile au dashboard. |

---

## 5. Modèles retenus

| Fonction | Modèle retenu | Justification |
|---|---|---|
| Détection d'anomalies | **Isolation Forest** | Meilleure PR-AUC et meilleur F1 ; score stable d'un segment temporel à l'autre ; linéaire en nombre de points. |
| Prévision des KPI | **XGBoost multi-horizon**, objectif `reg:absoluteerror` | Bat toutes les baselines à tous les horizons, avec un gain croissant avec l'horizon. |
| Classification de l'état QoS | **règles de seuils du contrat** | Convention d'exploitation auditable, non un phénomène à apprendre. Appliquée aux KPI mesurés comme aux KPI prévus. |

---

## 6. Limites et perspectives

1. **Volume d'épisodes d'anomalie insuffisant pour l'évaluation par épisode.**
   9 épisodes dans le segment de test : puissance statistique faible. Demande
   adressée au Binôme A (densité d'événements ou historique plus long).
2. **Seuils QoS v1.1 déséquilibrés** (43 % du temps en « critique »). Plafonne
   mécaniquement la qualité de l'état annoncé. Révision v1.2 demandée, options
   documentées au §6.1 du rapport d'EDA. Le contrat gelé reste néanmoins
   appliqué tel quel dans tout le code.
3. **Données synthétiques.** Les anomalies sont injectées par trois mécanismes
   paramétrés (panne, congestion, dégradation progressive) : un détecteur peut y
   réussir sans généraliser à des dégradations réelles, plus variées. Toute
   transposition à des traces réelles exigerait une réévaluation complète.
4. **Absence d'entraînement incrémental.** Les modèles sont réentraînés hors
   ligne. Un déploiement réel nécessiterait un réentraînement périodique et un
   suivi de dérive, la distribution du trafic évoluant avec le parc.
5. **Prévision ponctuelle sans intervalle.** Seule la valeur médiane est prévue.
   Un intervalle de prédiction (objectif quantile, déjà disponible dans XGBoost)
   donnerait à l'exploitant une mesure d'incertitude, et permettrait d'alerter
   sur la probabilité de franchir un seuil plutôt que sur une valeur unique.
   C'est la perspective la plus directement exploitable.

---

## 7. Reproduire ces résultats

```bash
cd binome-b
pip install -r requirements.txt

python -m src.scripts.run_eda          # analyse exploratoire  -> reports/rapport_eda.md
python -m src.scripts.train_anomaly    # détection d'anomalies -> reports/metrics/anomalie_*
python -m src.scripts.train_forecast   # prévision             -> reports/metrics/prevision_*
python -m src.scripts.make_report      # ce rapport
```

Graine aléatoire fixée à `RANDOM_STATE = 42` dans `src/config.py`. Les scripts
fonctionnent indifféremment contre l'API du Binôme A ou contre les CSV locaux
(variable `NETQOS_DATA_SOURCE`), le schéma servi étant identique.
