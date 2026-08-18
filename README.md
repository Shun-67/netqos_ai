# NetQoS-AI

> **Brouillon initial — à compléter et valider ensemble (Binôme A + Binôme B)
> avant de le considérer comme définitif.** Les sections marquées `[À compléter]`
> restent à rédiger collectivement.

Plateforme intelligente de surveillance et de prévision de la qualité de
service réseau. Projet ESMT / DETIC — Ingénierie des Données et Intelligence
Artificielle, année académique 2025-2026.

## Équipe

| Binôme | Périmètre | Dossier |
|---|---|---|
| A | Ingénierie des données & pipeline | [`binome-a/`](./binome-a) |
| B | Intelligence artificielle & restitution | [`binome-b/`](./binome-b) |

Encadrant : Prof. Boudal NIANG.

## [À compléter] Présentation du projet

*(2-3 paragraphes : contexte QoS, objectif de la plateforme, ce qui la rend
pertinente — à rédiger ensemble à partir de la fiche de projet)*

## Démarrage rapide

```bash
# 1. Cloner le dépôt
git clone <url-du-repo>
cd netqos-ai

# 2. Copier et adapter les variables d'environnement
cp .env.example .env

# 3. Lancer la base de données + l'API (Binôme A)
docker compose up -d

# 4. (Optionnel) Lancer aussi le dashboard (Binôme B) et Airflow (orchestration)
docker compose --profile full up -d

# 5. Générer et charger des données de test
cd binome-a
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python src/generator/synthetic_generator.py --cells 5 --days 14 --out data/raw/historical_kpi.csv
python -m src.ingestion.batch_ingest --file data/raw/historical_kpi.csv
python -m src.orchestration.run_pipeline
```

Vérifications :
- API : http://localhost:8000/docs
- Dashboard : http://localhost:8501 (si lancé avec `--profile full`)
- Airflow : http://localhost:8080 (si lancé avec `--profile full` — identifiants générés
  au premier démarrage, voir logs avec `docker compose logs airflow | grep password`)

## Architecture

```
netqos-ai/
├── binome-a/              # Collecte, nettoyage, stockage, API (voir binome-a/README.md)
├── binome-b/               # Modèles IA, dashboard (voir binome-b/README.md)
├── reports/                 # Livrables communs (contrat d'interface, schéma d'architecture, rapport)
├── docker-compose.yml        # Lance toute la stack en une commande
├── .env.example
└── .gitignore
```

[À compléter] Schéma d'architecture en 6 couches (voir `reports/architecture_schema.png`,
à produire conjointement — cf. cahier des charges partie 4.4).

## Contrat d'interface

Le contrat d'interface entre les deux binômes est figé depuis le jalon J7.
Document de référence : [`reports/contrat_interface.docx`](./reports/contrat_interface.docx).

Résumé technique : API REST sous `/api/v1/`, voir `binome-a/README.md` pour la
liste complète des endpoints.

## Convention de travail Git

- Branches : `binome-a/nom-fonctionnalite` et `binome-b/nom-fonctionnalite`
- Pas de commit direct sur `main` — passer par des Pull Requests
- `main` doit toujours rester démarrable via `docker compose up -d`

## [À compléter] Planning et jalons

*(Reprendre le planning à 4 jalons du cahier des charges, avec statut actuel — J7 atteint, etc.)*

## [À compléter] Résultats et démonstration

*(À remplir en semaine 4 : captures d'écran du dashboard, métriques des modèles, lien vers le rapport final)*

## Licence / Cadre

Projet académique — ESMT DETIC, non destiné à un usage en production.
