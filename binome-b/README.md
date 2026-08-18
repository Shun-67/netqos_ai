# NetQoS-AI — Binôme B (Intelligence artificielle & restitution)

Couche « intelligence » de la plateforme : détection d'anomalies, prévision des
KPI, classification de l'état QoS et tableau de bord d'exploitation.

Le Binôme B **consomme exclusivement l'API REST du Binôme A**. Aucun module ici
n'accède à TimescaleDB ni n'importe de code de `binome-a/` : la frontière A ↔ B
passe par `src/data/api_client.py` et par lui seul.

---

## Démarrage rapide

```bash
cd binome-b
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt

# 1. Analyse exploratoire            -> reports/rapport_eda.md
python -m src.scripts.run_eda

# 2. Détection d'anomalies           -> reports/metrics/anomalie_*
python -m src.scripts.train_anomaly

# 3. Prévision des KPI               -> reports/metrics/prevision_*
python -m src.scripts.train_forecast

# 4. Rapport d'évaluation            -> reports/rapport_evaluation_modeles.md
python -m src.scripts.make_report

# 5. Dashboard                       -> http://localhost:8501
streamlit run src/dashboard/app.py
```

Toutes les commandes se lancent **depuis `binome-b/`** (les modules sont importés
en paquet : `python -m src.scripts.…`).

Pour vérifier que tout fonctionne, suivre [`GUIDE_TEST.md`](GUIDE_TEST.md) :
procédure en cinq niveaux (2 min à 45 min) avec les valeurs attendues à chaque
étape.

Depuis la racine du dépôt, la stack complète démarre en une commande :

```bash
docker compose up --build            # base + API + dashboard
```

---

## Développer sans l'API du Binôme A

Le contrat d'interface (§2.3 de la fiche) prévoit que le Binôme B travaille
contre une version simulée de l'API pendant que le Binôme A la finalise. C'est
implémenté par une **façade à double source** :

| Mode | Comportement |
|---|---|
| `auto` *(défaut)* | interroge `GET /health` ; utilise l'API si elle répond, sinon retombe sur les CSV locaux |
| `api` | impose l'API ; échoue explicitement si elle ne répond pas |
| `local` | impose les CSV locaux (entraînement reproductible hors ligne) |

```bash
NETQOS_DATA_SOURCE=local python -m src.scripts.train_anomaly
NETQOS_DATA_SOURCE=api   streamlit run src/dashboard/app.py
```

`src/data/local_source.py` **réimplémente les règles documentées** de
`binome-a/data_dictionary.md` (nettoyage §3, features §4) pour servir exactement
le même schéma que `/kpi/history` et `/features` — 43 colonnes de features,
identiques à la table `kpi_features`. Il s'agit d'une réimplémentation de la
spécification écrite, pas d'un import du code du Binôme A : la frontière reste
étanche, et basculer d'une source à l'autre ne change aucune ligne de modèle.

Le mode local lit le premier fichier disponible parmi
`data/samples/sample_kpi_with_labels.csv`, `../binome-a/data/raw/historical_kpi.csv`,
`../binome-a/data/raw/verif_j14.csv`. Pour en générer un :

```bash
python ../binome-a/src/generator/synthetic_generator.py \
    --cells 5 --days 14 --out data/samples/sample_kpi_with_labels.csv
```

---

## Structure

```
binome-b/
├── Dockerfile                      # image du dashboard
├── requirements.txt
├── NOTICE_DASHBOARD.md             # notice d'utilisation (livrable §6.3)
└── src/
    ├── config.py                   # chemins, constantes du contrat v1.1, protocole d'éval
    ├── data/
    │   ├── api_client.py           # client de l'API du Binôme A (pagination, retry)
    │   ├── local_source.py         # API simulée : CSV -> schéma du contrat
    │   └── loader.py               # façade : masque la source aux modèles
    ├── features/
    │   ├── preprocessing.py        # encodages cycliques, features dérivées, garde-fou anti-fuite
    │   └── splits.py               # découpage chronologique par cellule, avec purge
    ├── models/
    │   ├── anomaly.py              # seuils · Isolation Forest · DBSCAN · autoencodeur
    │   ├── forecast.py             # persistance · moyenne mobile · naïf saisonnier · ARIMA · XGBoost
    │   ├── qos_state.py            # classification bon / dégradé / critique
    │   └── saved/                  # modèles sérialisés (non versionnés)
    ├── evaluation/
    │   └── metrics.py              # métriques ponctuelles, par épisode, de régression
    ├── scripts/
    │   ├── run_eda.py
    │   ├── train_anomaly.py
    │   ├── train_forecast.py
    │   └── make_report.py
    └── dashboard/
        └── app.py                  # Streamlit, 5 onglets
```

Les livrables générés vont dans `reports/` à la racine du dépôt (livrables
communs) : rapports Markdown, `figures/`, `metrics/`.

---

## Choix de modélisation

| Fonction | Baselines | Modèle avancé | Retenu |
|---|---|---|---|
| Anomalie | seuils du contrat, Isolation Forest, DBSCAN | autoencodeur | **Isolation Forest** — l'autoencodeur ne bat pas la baseline |
| Prévision | persistance, moyenne mobile 15 min, naïf saisonnier 24 h, ARIMA | XGBoost multi-horizon | **XGBoost** — gain de MAE de +10 % à +21 % sur la persistance selon l'horizon |
| État QoS | — | — | **règles de seuils** — convention d'exploitation auditable, pas un phénomène à apprendre |

Justifications détaillées, métriques et analyse d'erreurs :
[`reports/rapport_evaluation_modeles.md`](../reports/rapport_evaluation_modeles.md).

Deux résultats à connaître avant de relire le code :

- **L'autoencodeur perd contre l'Isolation Forest.** Le §8.2 de la fiche impose
  qu'un modèle avancé ne se justifie que s'il bat la baseline : il n'est donc pas
  déployé, seulement conservé pour son explicabilité par contribution de features.
- **L'objectif d'apprentissage de XGBoost a plus d'effet que le choix du modèle.**
  Avec `reg:squarederror` (défaut), XGBoost était *battu* par la persistance à
  cause des queues lourdes de `packet_loss`. Avec `reg:absoluteerror`, aligné sur
  la métrique MAE, il gagne partout.

---

## Protocole d'évaluation

- Découpage **chronologique par cellule** 60/20/20, avec **purge de 60 minutes**
  en tête des segments aval — les features du contrat contiennent des fenêtres
  glissantes de 60 min, qui fuiteraient sinon d'un segment à l'autre.
- `TemporalSplit.assert_chronological()` échoue si un timestamp de test précède
  un timestamp d'entraînement.
- `is_anomaly` est lue par `loader.load_labels()` **uniquement** au calcul des
  métriques. `preprocessing.FORBIDDEN_FEATURES` lève `LeakageError` si une
  colonne interdite atteint une matrice de features.
- Métrique de référence en détection : **PR-AUC**. Avec ~1,5 % d'anomalies, la
  ROC-AUC dépasse 0,94 même pour un détecteur inutilisable.

---

## Réserves adressées au Binôme A

Relevées pendant l'EDA et l'intégration, par ordre de priorité. Détail et
chiffres dans [`reports/rapport_eda.md`](../reports/rapport_eda.md) §6.1 et §8.

1. **Seuils QoS v1.1 déséquilibrés** — l'état « critique » couvre 42,9 % du temps
   et « bon » 8,5 %, parce que les seuils ont été calibrés KPI par KPI sans tenir
   compte de la règle d'agrégation « pire KPI » qui les combine. Révision v1.2
   demandée. Le contrat gelé reste appliqué tel quel dans tout notre code.
2. **`GET /eval/labels` inutilisable en l'état — deux défauts bloquants**, tous
   deux découverts en branchant le dashboard sur l'API réelle :
   - *horodatages non rééchantillonnés* : l'endpoint sert les `ts` de
     `raw_kpi_measurements` (`20:21:41`) quand `/features` sert la minute pleine
     (`20:21:00`). Une jointure sur `(ts, cell_id)` n'apparie **aucune** ligne, la
     prévalence tombe à 0 % et toutes les métriques de détection s'effondrent — en
     silence, sans erreur ;
   - *enveloppe incomplète* : l'endpoint accepte `limit`/`offset` mais omet
     `has_more` et `total`, contrairement au contrat énoncé dans le README du
     Binôme A. Un client paginant sur `has_more` s'arrête après une page : 5 000
     étiquettes lues sur 100 800.

   Contournés côté B (réalignement sur la grille minute ; pagination « tant que la
   page est pleine »), et désormais protégés par un garde-fou
   `LabelAlignmentError` qui refuse un taux d'appariement anormalement bas.
3. **`data_dictionary.md` §5 périmé** — liste `/kpi/raw`, `/kpi/clean`,
   `/stream/latest`, qui n'existent pas dans l'API v1.1 servie.
4. **Pipeline non idempotent — vérifié sur la stack Docker** : la seconde
   exécution de `run_pipeline` échoue sur
   `UniqueViolation: duplicate key ... "4_clean_kpi_measurements_pkey"`. Les
   données restent intactes (transaction annulée) mais le DAG Airflow, planifié
   toutes les 15 min, échouera à chaque tick après le premier. Le paramètre
   `since` existe dans les deux fonctions mais n'est jamais transmis.
5. **`docker-compose.yml` était absent** — livrable commun §6.1, référencé par
   les trois README. Reconstitué par le Binôme B à la racine, et validé de bout en
   bout (base peuplée, API servie, dashboard lisant l'API) ; les services
   `timescaledb`, `api` et `airflow` sont à relire et à reprendre par le Binôme A
   (deux points signalés en commentaire dans le fichier).
6. **Densité d'anomalies trop faible pour l'évaluation par épisode** — 9 épisodes
   seulement dans le segment de test. Augmenter la densité d'événements injectés
   ou allonger l'historique généré.
