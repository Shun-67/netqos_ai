# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Langue du projet

Tout le code, les docstrings, les commentaires et la documentation sont en **français**. Conserver cette langue pour tout nouveau code et toute nouvelle documentation.

## Vue d'ensemble

NetQoS-AI est un projet de stage encadré (Prof. Niang, ESMT), organisé en **deux binômes travaillant sur le même dépôt** avec un **contrat d'interface** figé entre eux :

- **`binome-a/`** — ingénierie des données : génération synthétique → ingestion → nettoyage → features → TimescaleDB → **API REST FastAPI**. C'est le producteur.
- **`binome-b/`** — IA & restitution : consomme *uniquement l'API HTTP* du binôme A (jamais la base directement), entraîne les modèles d'anomalie/prévision, affiche un dashboard Streamlit. C'est le consommateur.

Cette frontière est la contrainte architecturale centrale : `binome-b/src/data/api_client.py` est l'unique point de contact entre les deux moitiés. Ne jamais y introduire d'accès SQL ni d'import depuis `binome-a/`.

## Flux de données

```
synthetic_generator.py ──CSV──> batch_ingest.py ──┐
stream_simulator.py ──────────────────────────────┴──> raw_kpi_measurements
                                                            │ clean_prepare.py
                                                            ▼
                                                   clean_kpi_measurements
                                                            │ build_features.py
                                                            ▼
                                                       kpi_features
                                                            │ API FastAPI (/api/v1)
                                                            ▼
                                            api_client.py ──> modèles + dashboard
```

Les trois tables sont des **hypertables TimescaleDB** avec `PRIMARY KEY (ts, cell_id)` — voir [binome-a/sql/init.sql](binome-a/sql/init.sql).

## Commandes

Toutes les commandes `python -m src.*` **doivent être lancées depuis `binome-a/`** : les modules font `sys.path.append(".")` et échouent depuis la racine du dépôt.

```bash
# Binôme A (depuis binome-a/)
pip install -r requirements.txt
python src/generator/synthetic_generator.py --cells 5 --days 14 --out data/raw/historical_kpi.csv
python -m src.ingestion.batch_ingest --file data/raw/historical_kpi.csv
python -m src.orchestration.run_pipeline              # clean_prepare puis build_features
python -m src.orchestration.run_pipeline --loop --every 300
python -m src.ingestion.stream_simulator --cells 5 --interval-seconds 5
uvicorn src.api.main:app --reload --port 8000          # API en local -> http://localhost:8000/docs

# Binôme B (depuis binome-b/)
pip install -r requirements.txt
streamlit run src/dashboard/app.py                     # -> http://localhost:8501

# Airflow (jalon J21, depuis la racine du dépôt)
docker compose --profile full up -d airflow            # -> http://localhost:8080, DAG "netqos_pipeline"
docker exec netqos_airflow cat /opt/airflow/standalone_admin_password.txt
```

```bash
# Binôme B — chaîne complète (depuis binome-b/)
python -m src.scripts.run_eda           # -> reports/rapport_eda.md
python -m src.scripts.train_anomaly     # -> reports/metrics/anomalie_*
python -m src.scripts.train_forecast    # -> reports/metrics/prevision_* (~15 min avec ARIMA)
python -m src.scripts.make_report       # -> reports/rapport_evaluation_modeles.md
python -m src.scripts.make_samples      # -> binome-b/data/samples/*.csv
streamlit run src/dashboard/app.py      # -> http://localhost:8501

# Les scripts du binôme B fonctionnent contre l'API ou hors ligne :
NETQOS_DATA_SOURCE=local python -m src.scripts.train_anomaly
NETQOS_DATA_SOURCE=api API_BASE_URL=http://localhost:8010/api/v1 python -m src.scripts.run_eda
```

**Aucun test unitaire n'existe dans le dépôt** (pas de pytest, pas de fichier `test_*`), et il n'y a ni linter ni formateur configuré. Si des tests sont demandés, il faut d'abord poser l'infrastructure (choisir pytest, l'ajouter aux `requirements.txt`). Le dashboard se teste en revanche sans navigateur via `streamlit.testing.v1.AppTest` :

```bash
python -c "from streamlit.testing.v1 import AppTest; at=AppTest.from_file('src/dashboard/app.py', default_timeout=300); at.run(); print(len(at.exception), [e.value for e in at.error])"
```

## Pièges connus

- **`GET /api/v1/eval/labels` a deux défauts qui invalident silencieusement toute évaluation.** (1) Il sert les `ts` de `raw_kpi_measurements`, non rééchantillonnés (`20:21:41`), alors que `/kpi/history` et `/features` servent la minute pleine (`20:21:00`) : une jointure sur `(ts, cell_id)` n'apparie aucune ligne, la prévalence devient 0 % et toutes les métriques de détection tombent à zéro sans erreur. (2) Il accepte `limit`/`offset` mais omet `has_more`/`total`/`limit`/`offset` de son enveloppe : un client paginant sur `has_more` ne lit qu'une page. Les deux sont contournés côté binôme B dans `loader.load_labels()` et `api_client._get_paginated()` ; ne pas retirer ces contournements sans avoir vérifié que l'API a été corrigée. `splits.align_labels()` lève `LabelAlignmentError` si le taux d'appariement passe sous 50 %.
- **Le pipeline n'est pas idempotent** (vérifié sur la stack Docker). `clean_prepare.py` et `build_features.py` relisent la table amont *en entier* et font un `to_sql(if_exists="append")` : la seconde exécution échoue sur `psycopg2.errors.UniqueViolation` (clé primaire `(ts, cell_id)`). Les données ne sont pas corrompues, mais le DAG Airflow échoue à chaque tick après le premier. Le paramètre `since` existe dans les deux fonctions mais n'est jamais passé, ni par `run_pipeline.py` ni par le DAG.
- **Ports hôtes fréquemment occupés** : 5432 et 8000 le sont sur la machine de développement. Démarrer avec `POSTGRES_HOST_PORT=5433 API_PORT=8010 DASHBOARD_PORT=8511 docker compose up -d`. Ne pas confondre `POSTGRES_HOST_PORT` (port publié) et `POSTGRES_PORT` (port interne au réseau Docker, toujours 5432).
- **`src/db.py` et `.env.example` divergent** : les valeurs par défaut du code sont `netqos`/`netqos`/`localhost`/`netqos`, alors que `.env.example` fournit `netqos_db` et `POSTGRES_HOST=timescaledb` (valable dans Docker uniquement). Pour lancer les scripts hors conteneur, `POSTGRES_HOST=localhost` est requis.
- Le `§5` de [binome-a/data_dictionary.md](binome-a/data_dictionary.md) liste des endpoints périmés (`/kpi/raw`, `/kpi/clean`, `/stream/latest`) ; la référence réelle est le tableau du [README du binôme A](binome-a/README.md) et le code de [binome-a/src/api/main.py](binome-a/src/api/main.py).
- Airflow 2.9.3 exige **SQLAlchemy 1.4.x** : l'image Airflow installe ses dépendances avec le fichier de contraintes officiel (voir [binome-a/airflow/Dockerfile](binome-a/airflow/Dockerfile)). Ne pas retirer le `--constraint`, sinon Airflow casse (le `requirements.txt` du binôme A demande SQLAlchemy 2.0+).
- Le DAG importe directement `src.preparation.*` (monté sur `/opt/airflow/binome-a`) — **ne jamais dupliquer la logique du pipeline dans le DAG**.

## Règles issues du contrat d'interface (v1.1, figé le 2026-08-10)

- **`is_anomaly` est la vérité terrain, jamais une feature.** Elle n'existe que dans `raw_kpi_measurements` et n'est exposée que par `GET /api/v1/eval/labels`. Le helper `_df_to_records()` de l'API la supprime par défaut de toute réponse — ne pas contourner ce filtre.
- Les **seuils** de `GET /api/v1/thresholds` sont figés et référencés dans le rapport ; ne pas les modifier sans acter un changement de version de contrat.
- Toute modification du schéma de données doit être répercutée dans [binome-a/data_dictionary.md](binome-a/data_dictionary.md) (avec incrément de version) **et** communiquée au binôme B, car elle casse `api_client.py`.
- **Enveloppe de réponse commune** à respecter pour tout nouvel endpoint : `cell_id`, `from`, `to`, `count`, `data`, plus `limit`/`offset`/`total`/`has_more` si paginé.
- Une valeur manquante en base est `NULL`, jamais `0` ni `-1` ; les valeurs imputées sont marquées par `is_missing`.
- Les splits entraînement/validation doivent rester **chronologiques** : ne pas introduire de mélange de timestamps côté A qui provoquerait une fuite de données.

## Convention Git

Branches nommées `binome-a/<fonctionnalité>` ou `binome-b/<fonctionnalité>`, mergées sur `main` après validation uniquement.

## Jalons

| Jalon | Livrable | État |
|-------|----------|------|
| J7  | Contrat d'interface figé + EDA | fait (contrat v1.1) |
| J14 | Baselines anomalie et prévision | pipeline A fonctionnel ; modèles B non implémentés |
| J21 | Modèles avancés + dashboard | Airflow fait ; dashboard à l'état de squelette |
| J30 | Soutenance finale | — |

Côté binôme B, `src/models/anomaly.py` (Isolation Forest → autoencodeur) et `src/models/forecast.py` (moyenne mobile/ARIMA → Prophet/XGBoost/LSTM) ne contiennent qu'un docstring et `# À implémenter` ; `src/dashboard/app.py` n'est qu'un placeholder Streamlit.
