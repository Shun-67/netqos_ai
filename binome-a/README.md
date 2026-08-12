# NetQoS-AI — Binôme A (Ingénierie des données & pipeline)

Squelette de projet fonctionnel : génération de données, ingestion, nettoyage,
feature engineering, stockage TimescaleDB et API REST.

## Démarrage rapide

```bash
# 1. Lancer la base de données + l'API
docker-compose up -d

# 2. Installer les dépendances en local (pour lancer les scripts hors conteneur)
pip install -r requirements.txt

# 3. Générer des données synthétiques (14 jours, 5 cellules)
python src/generator/synthetic_generator.py --cells 5 --days 14 --out data/raw/historical_kpi.csv

# 4. Ingestion batch dans la base
python -m src.ingestion.batch_ingest --file data/raw/historical_kpi.csv

# 5. Nettoyage + calcul des features
python -m src.orchestration.run_pipeline

# 6. Vérifier l'API
# -> http://localhost:8000/docs
curl http://localhost:8000/api/v1/health
curl "http://localhost:8000/api/v1/features?limit=10"
```

## Endpoints de l'API (contrat d'interface v1.1, validé avec le Binôme B)

| Endpoint | Usage |
|---|---|
| `GET /api/v1/health` | Vérification de disponibilité |
| `GET /api/v1/cells` | Liste des cellules disponibles |
| `GET /api/v1/thresholds` | Seuils normal/dégradé/critique par KPI |
| `GET /api/v1/kpi/history?cell_id=&from=&to=&limit=&offset=` | Historique nettoyé (paginé), inclut `is_missing` |
| `GET /api/v1/features?cell_id=&from=&to=&limit=&offset=` | Features pré-calculées (paginé) |
| `GET /api/v1/kpi/latest?cell_id=&n=` | Dernières mesures |
| `GET /api/v1/kpi/stream?cell_id=` | Flux quasi temps réel |
| `GET /api/v1/kpi/stream/info` | Fréquence d'émission et modalités de polling |
| `GET /api/v1/eval/labels?cell_id=&from=&to=` | Vérité terrain (`is_anomaly`) — évaluation uniquement, jamais en entraînement |

Toutes les réponses suivent une enveloppe commune (`cell_id`, `from`, `to`, `count`, `data`, + `limit`/`offset`/`total`/`has_more` pour les endpoints paginés).

### Lancer le flux simulé (optionnel, dans un autre terminal)

```bash
python -m src.ingestion.stream_simulator --cells 5 --interval-seconds 5
```

### Orchestration en continu (option simple)

```bash
python -m src.orchestration.run_pipeline --loop --every 300
```

### Orchestration avancée avec Airflow (jalon J21)

Depuis la racine du repo (pas ce dossier `binome-a/`) :

```bash
docker compose --profile full up -d airflow
```

Premier démarrage : Airflow initialise sa base SQLite interne et crée un
compte admin avec un mot de passe généré aléatoirement. Pour le récupérer :

```bash
docker exec netqos_airflow cat /opt/airflow/standalone_admin_password.txt
```

Puis ouvrir **http://localhost:8080** (identifiant `admin`, mot de passe
ci-dessus), activer le DAG `netqos_pipeline` (toggle en haut à gauche) — il
s'exécute ensuite toutes les 15 minutes (nettoyage → features), avec suivi
visuel des exécutions, des logs et des reprises automatiques en cas d'échec.

Le DAG (`airflow/dags/netqos_pipeline_dag.py`) réutilise directement les
fonctions de `src/preparation/` — aucune logique dupliquée avec
`run_pipeline.py`, qui reste utilisable en parallèle pour des tests rapides
en local sans passer par Docker.

## Structure du projet

```
├── data_dictionary.md          # Base du contrat d'interface (validé avec Binôme B, J7)
├── Dockerfile                     # Image de l'API (utilisée par le docker-compose racine)
├── requirements.txt
├── sql/init.sql                 # Schéma TimescaleDB (3 tables : raw / clean / features)
├── airflow/
│   ├── Dockerfile                # Image Airflow + dépendances du pipeline (pandas, sqlalchemy...)
│   ├── requirements-airflow.txt
│   └── dags/netqos_pipeline_dag.py   # Orchestration jalon J21 (clean_prepare -> build_features)
├── src/
│   ├── db.py                    # Connexion partagée à la base
│   ├── generator/                # Génération de données synthétiques
│   ├── ingestion/                 # Batch + flux simulé
│   ├── preparation/               # Nettoyage + feature engineering
│   ├── orchestration/             # Enchaînement du pipeline (script simple, alternative à Airflow)
│   └── api/main.py                # API FastAPI (contrat avec Binôme B)
└── data/raw/                     # Zone de données brutes (CSV)
```

Le `docker-compose.yml` vit désormais à la racine du repo (pas dans ce
dossier) — voir le README principal pour le démarrage complet de la stack.

## Roadmap suggérée (calée sur le planning du projet)

- **Semaine 1 (J1-J7)** : `data_dictionary.md` à finaliser avec le Binôme B,
  générateur synthétique, premier script d'ingestion batch. **Jalon J7 : contrat
  d'interface figé.**
- **Semaine 2 (J8-J14)** : nettoyage, schéma TimescaleDB peuplé, premières
  features. **Jalon J14 : pipeline bout-en-bout fonctionnel.**
- **Semaine 3 (J15-J21)** : orchestration Airflow ✅ (DAG `netqos_pipeline`
  validé, voir section ci-dessus), API REST complète et stable, flux simulé
  branché. **Jalon J21 : le dashboard du Binôme B lit l'API avec succès.**
- **Semaine 4 (J22-J30)** : conteneurisation finalisée, tests, documentation
  de l'API (OpenAPI générée automatiquement sur `/docs`). **Jalon J30 :
  démonstration live.**

## Points d'attention

- Ne jamais exposer `is_anomaly` comme feature — c'est la vérité terrain
  réservée à l'évaluation du Binôme B.
- Toute modification du schéma de données doit être répercutée dans
  `data_dictionary.md` et communiquée au Binôme B (versionnement).
- Le split entraînement/validation du Binôme B doit respecter l'ordre
  chronologique : évitez de mélanger les timestamps lors de tout traitement
  côté A qui pourrait introduire une fuite de données.
