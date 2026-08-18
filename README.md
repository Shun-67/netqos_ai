# NetQoS-AI

Plateforme de supervision intelligente de la qualité de service (QoS) réseau.
Encadrant : **Prof. Niang**

---

## Démarrage rapide

```bash
git clone https://github.com/<votre-org>/netqos_ai.git
cd netqos_ai
cp .env.example .env
docker compose up --build
```

- API Binôme A : `http://localhost:8000` — documentation OpenAPI sur `/docs`
- Dashboard Binôme B : `http://localhost:8501`

Puis peupler la base (première utilisation) :

```bash
docker exec netqos_api python -m src.ingestion.batch_ingest --file data/raw/historical_kpi.csv
docker exec netqos_api python -m src.orchestration.run_pipeline
```

Si un port est déjà occupé sur votre machine (une instance PostgreSQL locale
occupe souvent 5432), surchargez-le sans modifier le fichier compose :

```bash
POSTGRES_HOST_PORT=5433 API_PORT=8010 DASHBOARD_PORT=8511 docker compose up -d
```

Orchestration Airflow (jalon J21) :

```bash
docker compose --profile full up -d airflow      # http://localhost:8080
```

---

## Structure

```
netqos_ai/
├── binome-a/          # Collecte, traitement, API REST
├── binome-b/          # Modèles IA, détection, prévision, dashboard
├── reports/           # Livrables communs : rapports, figures, métriques
│   ├── rapport_eda.md
│   ├── rapport_evaluation_modeles.md
│   ├── figures/
│   └── metrics/
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Résultats obtenus

| Fonction | Modèle retenu | Performance |
|---|---|---|
| Détection d'anomalies | Isolation Forest | F1 = 0,65 · PR-AUC = 0,61 · 0,02 fausse alerte/h · 9/9 épisodes détectés |
| Prévision des KPI | XGBoost multi-horizon | MAE inférieure de 10 % à 21 % à celle de la persistance selon l'horizon |
| État QoS annoncé | seuils du contrat appliqués aux prévisions | 83 % d'exactitude à 5–30 min |

Détail, protocole d'évaluation et analyse d'erreurs :
[`reports/rapport_evaluation_modeles.md`](reports/rapport_evaluation_modeles.md).
Analyse exploratoire : [`reports/rapport_eda.md`](reports/rapport_eda.md).

Deux résultats méthodologiques notables, documentés dans le rapport :

- le **modèle avancé de détection (autoencodeur) ne bat pas la baseline**
  Isolation Forest ; conformément au §8.2 de la fiche, il n'est pas déployé ;
- pour la prévision, le **choix de la fonction de perte a plus d'effet que le
  choix du modèle** : avec l'objectif quadratique par défaut, XGBoost était battu
  par la persistance à cause des queues lourdes de `packet_loss`.

---

## Points ouverts

- **Seuils QoS v1.1 à recalibrer** — l'état « critique » couvre 42,9 % du temps et
  « bon » 8,5 %, les seuils ayant été calibrés KPI par KPI sans tenir compte de la
  règle d'agrégation « pire KPI ». Révision v1.2 à acter par le Binôme A ; le
  contrat gelé reste appliqué en attendant. Voir `reports/rapport_eda.md` §6.1.
- **Pipeline non idempotent** — la seconde exécution de `run_pipeline` échoue sur
  `UniqueViolation` (clé primaire `(ts, cell_id)`), vérifié sur la stack Docker.
  Le DAG Airflow ne peut donc pas se rafraîchir. Le paramètre `since` existe dans
  `clean_prepare` et `build_features` mais n'est jamais transmis.
- **`data_dictionary.md` §5 périmé** — liste des endpoints antérieure à l'API v1.1.

---

## Convention Git

- Branches : `binome-a/nom-fonctionnalite` et `binome-b/nom-fonctionnalite`
- Merge sur `main` uniquement après validation

---

## Jalons

| Jalon | Livrable | État |
|-------|----------|------|
| J7  | Contrat d'interface figé + EDA | contrat v1.1 figé · EDA Binôme B faite (`reports/rapport_eda.md`) |
| J14 | Baselines anomalie et prévision | pipeline A bout-en-bout · 4 baselines anomalie + 4 baselines prévision évaluées |
| J21 | Modèles avancés + dashboard | Airflow (A) · autoencodeur et XGBoost (B) · dashboard 6 onglets dont un temps réel · **intégration A↔B vérifiée sur la stack Docker** |
| J30 | Soutenance finale | rapport d'évaluation et notice du dashboard produits · schéma d'architecture à produire |
