# Guide de test du travail du Binôme B

Procédure de vérification en cinq niveaux, du plus rapide au plus complet. Chaque
étape indique **la valeur attendue**, pour que le résultat soit objectivement
vérifiable et non une impression.

Sauf mention contraire, toutes les commandes se lancent **depuis `binome-b/`**.

| Niveau | Ce qui est vérifié | Durée | Docker requis |
|---|---|---|---|
| 0 | La chaîne fonctionne (test de fumée) | 2 min | non |
| 1 | Les livrables existent et sont cohérents | 5 min | non |
| 2 | Le dashboard s'affiche et réagit | 5 min | non |
| 3 | L'intégration A ↔ B (jalon J21) | 10 min | oui |
| 4 | La rigueur du protocole (tests négatifs) | 5 min | non |
| 5 | Reproduction complète depuis zéro | ~45 min | non |

---

## Niveau 0 — Test de fumée (2 min)

```bash
cd binome-b
pip install -r requirements.txt

python -c "
import sys; sys.path.insert(0,'.')
from src.data import loader
print('source   :', loader.active_source())
print('cellules :', loader.list_cells())
print('history  :', loader.load_history().shape)
print('features :', loader.load_features().shape)
print('labels   :', loader.load_labels().shape)
"
```

**Attendu :**

```
source   : local
cellules : ['cell_001', ..., 'cell_005']
history  : (100800, 8)
features : (100750, 45)
labels   : (100800, 3)
```

Les **45 colonnes de features** (43 features + `ts` + `cell_id`) sont le point à
vérifier : c'est le schéma exact de la table `kpi_features` du contrat v1.1. Un
autre nombre signifie que le contrat a changé.

> **Pourquoi `source : local` même quand la stack Docker tourne ?** Le client
> cherche l'API à l'adresse `API_BASE_URL`, qui vaut `http://localhost:8000/api/v1`
> par défaut (valeur de `.env.example`). Sur cette machine, le port 8000 étant
> occupé, l'API est publiée sur **8010** : la sonde `/health` échoue donc sur 8000
> et le mode `auto` retombe correctement sur les CSV locaux. Deux façons de viser
> l'API :
>
> ```bash
> # ponctuellement
> API_BASE_URL=http://localhost:8010/api/v1 python -m src.scripts.run_eda
>
> # ou durablement, en éditant la ligne correspondante du fichier .env à la racine
> API_BASE_URL=http://localhost:8010/api/v1
> ```
>
> Ce n'est pas un défaut : c'est le repli automatique prévu par le contrat (§2.3 de
> la fiche), qui permet de travailler pendant que l'API du Binôme A est
> indisponible.

---

## Niveau 1 — Livrables (5 min)

### 1.1 Les fichiers attendus sont présents

```bash
cd ..                       # racine du dépôt
ls reports/*.md
ls reports/figures/*/       # 14 figures : eda/ 7, anomalie/ 3, prevision/ 4
ls reports/metrics/         # 17 fichiers CSV/JSON
```

Deux rapports attendus : `rapport_eda.md` et `rapport_evaluation_modeles.md`.

### 1.2 Les rapports sont **régénérables** (et non écrits à la main)

C'est le contrôle le plus important de ce niveau : aucun chiffre des rapports
n'est saisi manuellement, tout provient de `reports/metrics/`.

```bash
cd binome-b
python -m src.scripts.make_report
```

**Attendu :** `Rapport écrit : reports\rapport_evaluation_modeles.md` — 459 lignes.
Le fichier doit être identique à celui qui existait avant (à la date près).

### 1.3 Les chiffres clés

```bash
cd ..
python -c "
import pandas as pd
d = pd.read_csv('reports/metrics/anomalie_resultats.csv')
o = d[d.point_de_fonctionnement.str.startswith('exploitation')]
print(o[['detecteur','precision','rappel','f1','pr_auc','fausses_alertes_par_heure']].to_string(index=False))
"
```

**Attendu** (au point de fonctionnement d'exploitation) :

| detecteur | precision | rappel | f1 | pr_auc | fausses alertes/h |
|---|---|---|---|---|---|
| seuils_contrat | 0,029 | 0,823 | 0,056 | 0,027 | 0,63 |
| isolation_forest | 0,650 | 0,657 | **0,653** | **0,614** | **0,02** |
| dbscan | 0,284 | 0,190 | 0,228 | 0,390 | 0,02 |
| autoencodeur | 0,364 | 0,387 | 0,375 | 0,363 | 0,01 |

Lecture : l'Isolation Forest domine. L'autoencodeur (« modèle avancé ») perd —
c'est un résultat assumé et documenté au §2.5 du rapport d'évaluation, pas un
oubli de réglage.

```bash
python -c "
import pandas as pd
d = pd.read_csv('reports/metrics/prevision_resultats.csv')
d = d[d.perimetre=='test_complet']
print(d.pivot_table(index='modele', columns='horizon_min', values='gain_mae_vs_persistance_pct').round(2).to_string())
"
```

**Attendu** — gain de MAE sur la persistance (%, positif = meilleur) :

```
horizon_min             5      15     30
moyenne_mobile_15m    1.05   0.95   1.26
naif_saisonnier_24h -34.12 -24.12 -12.92
persistance           0.00   0.00  -0.01
xgboost               9.78  14.31  21.22
```

Le point à vérifier : **le gain de XGBoost croît avec l'horizon**. S'il décroissait,
cela signalerait une fuite de données ou un mauvais alignement des cibles.

### 1.4 Les figures sont lisibles

Ouvrir `reports/figures/anomalie/precision_rappel.png` : la courbe orange
(Isolation Forest) doit dominer les autres, et la bleue (seuils du contrat) rester
plate en bas — précision ≈ 0,03.

---

## Niveau 2 — Dashboard (5 min)

### 2.1 Test automatique, sans navigateur

```bash
cd binome-b
python -c "
import sys; sys.path.insert(0,'.')
from streamlit.testing.v1 import AppTest
at = AppTest.from_file('src/dashboard/app.py', default_timeout=600)
at.run()
print('exceptions :', len(at.exception))
for e in at.exception: print('  !!', e.value)
print('onglets    :', len(at.tabs))
print('metriques  :', len(at.metric))
"
```

**Attendu :** `exceptions : 0` · `onglets : 5` · `metriques : 8`.

### 2.2 Test visuel

```bash
streamlit run src/dashboard/app.py       # -> http://localhost:8501
```

À vérifier onglet par onglet :

| Onglet | Ce qui doit s'afficher |
|---|---|
| **Vue d'ensemble** | 5 vignettes de cellules avec 🟢/🟠/🔴 et, sous chacune, le KPI responsable (ex. `latency (+180 % vs seuil bon)`) |
| **KPI & anomalies** | 6 graphiques synchronisés : 5 KPI + score d'atypicité ; seuils en tirets ; points rouges d'alerte reportés sur tous les KPI |
| **Prévision** | courbe observée en noir + 3 courbes pointillées (+5/+15/+30 min), et 3 vignettes d'état QoS annoncé |
| **Qualité des modèles** | les tableaux de métriques du niveau 1.3 |
| **Intégration** | source active, URL de l'API, modèles chargés, endpoints consommés |

Manipulations à tester :

1. Faire glisser **Sensibilité** de 2 % à 8 % → le nombre de points rouges doit
   augmenter et la légende sous le graphique se mettre à jour.
2. Changer de **cellule** → toutes les courbes changent.
3. Cocher **Afficher la vérité terrain** → des bandes verticales rouge pâle
   apparaissent ; elles doivent coïncider avec les pics du score d'atypicité.
   C'est la démonstration visuelle que le détecteur alerte au bon endroit.
4. Choisir le détecteur **autoencodeur** → un tableau « Causes probables des
   alertes » apparaît en bas de l'onglet (les autres détecteurs n'en ont pas).

Si un bandeau orange « Mode dégradé » s'affiche en haut, c'est normal hors Docker :
l'API du binôme A n'est pas démarrée, le dashboard lit les CSV locaux.

---

## Niveau 3 — Intégration A ↔ B, jalon J21 (10 min)

C'est le test qui vaut 20 % de la note (§8 de la fiche) : *le dashboard lit l'API*.

### 3.1 Démarrer la stack

Les ports 5432 et 8000 étant occupés sur cette machine, il faut les surcharger :

```bash
cd ..                        # racine du dépôt
export POSTGRES_HOST_PORT=5433 API_PORT=8010 DASHBOARD_PORT=8511

docker compose start         # si les conteneurs existent déjà (quelques secondes)
# ou, première fois :
docker compose up -d --build
```

**Première utilisation seulement** — peupler la base (~6 min) :

```bash
docker exec netqos_api python -m src.ingestion.batch_ingest --file data/raw/historical_kpi.csv
docker exec netqos_api python -m src.orchestration.run_pipeline
```

**Attendu :** `100800 lignes ingérées` puis `100800 lignes nettoyées` et
`100750 lignes de features écrites (43 colonnes de features par ligne)`.

### 3.2 L'API répond

```bash
curl -s http://localhost:8010/api/v1/health
curl -s http://localhost:8010/api/v1/cells
```

**Attendu :** `{"status":"ok",...}` et les 5 cellules.

### 3.3 Le dashboard lit bien l'API — et non les CSV

Ouvrir **http://localhost:8511** : le bandeau « Mode dégradé » doit avoir
**disparu**, et l'onglet *Intégration* afficher en vert
« Connecté à l'API du Binôme A — http://api:8000/api/v1 ».

Vérification automatique équivalente :

```bash
docker exec netqos_dashboard python -c "
import sys; sys.path.insert(0,'/app')
from streamlit.testing.v1 import AppTest
at = AppTest.from_file('/app/src/dashboard/app.py', default_timeout=900)
at.run()
print('exceptions :', len(at.exception))
print('succes     :', [s.value[:60] for s in at.success])
"
```

**Attendu :** `exceptions : 0` et un message de succès contenant
`Connecté à l'API du Binôme A`.

### 3.4 Le test le plus concluant : équivalence API / CSV local

Ce contrôle prouve que ma source locale de repli reproduit fidèlement l'API, donc
que les modèles sont indifférents à la source.

```bash
cd binome-b
NETQOS_DATA_SOURCE=api API_BASE_URL=http://localhost:8010/api/v1 python -c "
import sys; sys.path.insert(0,'.')
import numpy as np
from src.data import loader, local_source
api = loader.load_features(cell_id='cell_001')
loc = local_source.build_features(); loc = loc[loc.cell_id=='cell_001'].reset_index(drop=True)
print('colonnes identiques :', sorted(api.columns)==sorted(loc.columns))
m = api.merge(loc, on=['ts','cell_id'], suffixes=('_a','_l'))
ecart = max(np.abs(m[f'{c}_a']-m[f'{c}_l']).max() for c in api.columns if c not in ('ts','cell_id'))
print(f'lignes appariees    : {len(m)} / {len(api)}')
print(f'ecart numerique max : {ecart:.10f}')
"
```

**Attendu :** `colonnes identiques : True`, `20150 / 20150`, et
`ecart numerique max : 0.0000000000`.

### 3.5 Réentraîner via l'API donne les mêmes chiffres

```bash
NETQOS_DATA_SOURCE=api API_BASE_URL=http://localhost:8010/api/v1 python -m src.scripts.train_anomaly
```

**Attendu :** exactement les valeurs du niveau 1.3 (`isolation_forest` :
`P=0.650 R=0.657 F1=0.653`), et une prévalence affichée de
`train 1.27 % · val 1.11 % · test 1.51 %`.

> Si la prévalence affiche **0,00 %**, c'est que le contournement du défaut
> d'horodatage de `/eval/labels` a été retiré — voir §2 des réserves dans
> `reports/rapport_eda.md`.

### 3.6 Arrêter

```bash
cd .. && docker compose stop            # conserve la base
# docker compose down -v                # supprime aussi la base
```

---

## Niveau 4 — Tests négatifs : ce qui **doit** échouer (5 min)

Ces contrôles vérifient la rigueur du protocole. Un test qui ne lève pas
d'exception ici est un échec.

```bash
cd binome-b
python -c "
import sys; sys.path.insert(0,'.')
import pandas as pd
from src.features.preprocessing import assert_no_leakage, LeakageError
from src.features.splits import align_labels, LabelAlignmentError

# 1. La vérité terrain ne doit jamais entrer dans les features
try:
    assert_no_leakage(pd.DataFrame({'is_anomaly':[1]}), ['is_anomaly'])
    print('ECHEC 1 : fuite non detectee')
except LeakageError: print('OK 1 : LeakageError levee')

# 2. Des etiquettes desalignees doivent etre refusees, pas ignorees
f = pd.DataFrame({'ts': pd.to_datetime(['2026-01-01 00:00:00'], utc=True), 'cell_id':['c1']})
l = pd.DataFrame({'ts': pd.to_datetime(['2026-01-01 00:00:41'], utc=True), 'cell_id':['c1'], 'is_anomaly':[True]})
try:
    align_labels(f, l); print('ECHEC 2 : desalignement non detecte')
except LabelAlignmentError: print('OK 2 : LabelAlignmentError levee')

# 3. Une verite terrain vide doit etre refusee
try:
    align_labels(f, pd.DataFrame()); print('ECHEC 3')
except LabelAlignmentError: print('OK 3 : etiquettes vides refusees')
"
```

**Attendu :** trois lignes `OK`. Le test 2 est le plus important : c'est le
garde-fou qui empêche qu'une évaluation entière retombe silencieusement à zéro.

### Le découpage temporel ne contient aucune fuite

```bash
python -c "
import sys; sys.path.insert(0,'.')
from src.data import loader
from src.features.preprocessing import prepare_features
from src.features.splits import temporal_split
s = temporal_split(prepare_features(loader.load_features()))
s.assert_chronological()
print('OK : aucun chevauchement train/val/test')
print(s.summary().to_string(index=False))
"
```

**Attendu :** `train 60450` · `val 19850` · `test 19850`, et surtout un **trou d'au
moins 60 minutes** entre la fin d'un segment et le début du suivant (fin de train
`06:00`, début de val `07:01`). C'est la purge qui évite qu'une fenêtre glissante
de 60 min chevauche deux segments.

### L'API imposée mais absente doit échouer explicitement

```bash
NETQOS_DATA_SOURCE=api API_BASE_URL=http://localhost:9999/api/v1 python -c "
import sys; sys.path.insert(0,'.')
from src.data import loader
from src.data.api_client import ApiUnavailable
try:
    loader.active_source(); print('ECHEC : aucune erreur')
except ApiUnavailable as e: print('OK : ApiUnavailable ->', str(e)[:70])
"
```

En mode `auto`, la même commande doit au contraire basculer sur `local` sans erreur.

---

## Niveau 5 — Reproduction complète depuis zéro (~45 min)

Supprime tous les artefacts et refait toute la chaîne. À faire au moins une fois
avant la soutenance.

```bash
cd binome-b
rm -rf src/models/saved/*.joblib ../reports/metrics/* ../reports/figures/*

python -m src.scripts.run_eda           # ~1 min
python -m src.scripts.train_anomaly     # ~5 min
python -m src.scripts.train_forecast    # ~30 min (ARIMA) — ou --no-arima : ~10 min
python -m src.scripts.make_report       # instantané
python -m src.scripts.make_samples      # instantané
```

**Attendu :** les mêmes chiffres qu'au niveau 1.3 — la graine aléatoire est fixée
(`RANDOM_STATE = 42` dans `src/config.py`), donc les résultats sont reproductibles
à l'identique.

Contrôles pendant l'exécution :

- `run_eda` affiche `Taux d'anomalie : 1.2778 %` et `Conformité : aucune`
  (aucune anomalie de conformité au contrat détectée) ;
- `train_anomaly` affiche `Espace de features de détection : 23 colonnes` et
  `Épisodes manqués : 0 / 9` ;
- `train_forecast` affiche `objectifs retenus : reg:absoluteerror 15` — les 15
  modèles (5 KPI × 3 horizons) doivent tous retenir l'objectif MAE ;
- `make_report` écrit 459 lignes.

---

## Récapitulatif des valeurs de référence

| Grandeur | Valeur attendue |
|---|---|
| Lignes d'historique nettoyé | 100 800 |
| Lignes de features | 100 750 |
| Colonnes de features (contrat) | 43 (+ `ts`, `cell_id`) |
| Colonnes après préparation Binôme B | 57 |
| Features de détection d'anomalies | 23 |
| Taux d'anomalie global | 1,2778 % |
| Découpage train / val / test | 60 450 / 19 850 / 19 850 |
| Purge entre segments | ≥ 60 min |
| Isolation Forest — F1 / PR-AUC | 0,653 / 0,614 |
| Isolation Forest — fausses alertes | 0,02 / h |
| Épisodes détectés | 9 / 9 |
| XGBoost — gain MAE (5/15/30 min) | +9,8 % / +14,3 % / +21,2 % |
| Exactitude de l'état QoS annoncé | ≈ 83 % |
| Écart API ↔ CSV local | 0,0000000000 |
| Dashboard | 5 onglets, 0 exception |

---

## Défauts connus, à ne pas confondre avec des régressions

Ces comportements sont attendus et documentés — ils relèvent du périmètre du
Binôme A (détail dans `reports/rapport_eda.md` §8) :

| Observation | Explication |
|---|---|
| Beaucoup de vignettes 🔴 dans le dashboard | Les seuils v1.1 classent 42,9 % du temps en « critique ». Recalibrage v1.2 demandé. |
| `run_pipeline` échoue à la 2ᵉ exécution (`UniqueViolation`) | Pipeline non idempotent. Les données restent intactes ; le DAG Airflow échoue à chaque tick après le premier. |
| `/eval/labels` renvoie des `ts` en `:41` secondes | Horodatages non rééchantillonnés. Contourné dans `loader.load_labels()`. |
| `docker compose up` échoue sur « port already allocated » | 5432 et 8000 occupés sur cette machine → surcharger `POSTGRES_HOST_PORT`, `API_PORT`, `DASHBOARD_PORT`. |
