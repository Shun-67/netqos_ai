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

# 3. Lancer la stack : base + API (Binôme A) + dashboard (Binôme B)
docker compose up -d --build

# 4. (Optionnel) Ajouter l'orchestration Airflow
docker compose --profile full up -d

# Si un port est déjà occupé (une instance PostgreSQL locale occupe souvent
# 5432), le surcharger sans modifier le fichier compose :
#   POSTGRES_HOST_PORT=5433 API_PORT=8010 DASHBOARD_PORT=8511 docker compose up -d

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
- Dashboard : http://localhost:8501
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

### Schéma d'architecture

![Architecture en six couches](reports/architecture_schema.png)

Les six couches du §4.1 du cahier des charges, les flux de données entre elles, et
la frontière A ↔ B matérialisée par l'API — les trois éléments exigés au §4.4.

Le schéma est **généré par script** (`binome-b/src/scripts/make_architecture.py`)
et non dessiné : chaque libellé porte le nom réel d'un fichier ou d'une table du
dépôt, il se régénère si l'architecture évolue, et il se relit dans un diff.

Deux éléments méritent l'attention à la lecture :

- le **chemin isolé de `is_anomaly`** (flèche rouge en tirets). La vérité terrain
  n'existe que dans la table brute et n'est exposée que par `/eval/labels`. C'est
  ce qui garantit que la détection d'anomalies reste non supervisée ;
- la **frontière A ↔ B**, franchie uniquement en HTTP sur `/api/v1`. Aucun accès
  SQL ni import de code ne la traverse.

## Contrat d'interface

Le contrat d'interface entre les deux binômes est figé depuis le jalon J7.
Document de référence : [`reports/contrat_interface.docx`](./reports/contrat_interface.docx).

Résumé technique : API REST sous `/api/v1/`, voir `binome-a/README.md` pour la
liste complète des endpoints.

## Convention de travail Git

- Branches : `binome-a/nom-fonctionnalite` et `binome-b/nom-fonctionnalite`
- Pas de commit direct sur `main` — passer par des Pull Requests
- `main` doit toujours rester démarrable via `docker compose up -d`

## Planning et jalons

| Jalon | Attendu | Statut |
|---|---|---|
| **J7** | Contrat d'interface figé + EDA | contrat v1.1 figé le 2026-08-10 · EDA Binôme B produite ([`reports/rapport_eda.md`](./reports/rapport_eda.md)) |
| **J14** | Pipeline bout-en-bout fonctionnel | pipeline A opérationnel · 4 baselines anomalie et 4 baselines prévision évaluées côté B |
| **J21** | Intégration A ↔ B (le dashboard lit l'API) | **atteint** — vérifié sur la stack Docker · modèles avancés (autoencodeur, XGBoost) · dashboard à 6 onglets dont un temps réel |
| **J30** | Plateforme complète, documentée, démontrée | rapport d'évaluation et notice du dashboard produits · *reste à faire : schéma d'architecture, rapport de projet, support de soutenance* |

## Résultats et démonstration

### Modèles retenus (Binôme B)

| Fonction | Modèle retenu | Performance sur le segment de test |
|---|---|---|
| Détection d'anomalies | Isolation Forest (2 000 arbres) | F1 = 0,631 · PR-AUC = 0,586 · 0,018 fausse alerte/h · 9/9 épisodes détectés |
| Prévision des KPI | XGBoost multi-horizon | MAE inférieure de 10,0 % / 14,6 % / 20,7 % à la persistance (5 / 15 / 30 min) |
| État QoS annoncé | seuils du contrat appliqués aux prévisions | ≈ 82 % d'exactitude de l'état, de 5 à 30 min |

Protocole d'évaluation, comparaison baseline / modèle avancé et analyse
d'erreurs : [`reports/rapport_evaluation_modeles.md`](./reports/rapport_evaluation_modeles.md).

Deux résultats méthodologiques que le rapport détaille, parce qu'ils sont plus
instructifs que les chiffres :

- le **modèle avancé de détection (autoencodeur) ne bat pas la baseline**
  Isolation Forest. Conformément au §8.2 du cahier des charges, il n'est donc
  pas déployé ;
- en prévision, le **choix de la fonction de perte a pesé plus lourd que le
  choix du modèle** : avec l'objectif quadratique par défaut, XGBoost était
  battu par la persistance, à cause des valeurs extrêmes de `packet_loss` ;
- la campagne d'optimisation a montré qu'**il n'y avait quasiment pas de gain à
  prendre sur les hyperparamètres**, et qu'un « gain » apparent de +3,9 % en
  validation n'était que du bruit — la seule graine aléatoire faisait varier la
  PR-AUC trois fois plus. Le seul progrès fiable a consisté à *réduire cette
  variance* (2 000 arbres au lieu de 300), et un oracle supervisé chiffre à
  0,905 de PR-AUC le plafond qu'atteindrait un modèle autorisé à voir les
  étiquettes — soit **le prix mesuré de la contrainte non supervisée** imposée
  par le §2.2 du cahier des charges.

### Reproduire les résultats

```bash
cd binome-b && pip install -r requirements.txt
python -m src.scripts.run_eda          # analyse exploratoire
python -m src.scripts.train_anomaly    # détection d'anomalies
python -m src.scripts.train_forecast   # prévision
python -m src.scripts.make_report      # rapport d'évaluation
```

Procédure de vérification complète, avec les valeurs attendues à chaque étape :
[`binome-b/GUIDE_TEST.md`](./binome-b/GUIDE_TEST.md).

### [À compléter] Captures d'écran et démonstration

*(Semaine 4 : captures des 6 onglets du dashboard, déroulé de la démonstration live)*

## Points ouverts

- **Seuils QoS v1.1 à recalibrer.** L'état « critique » couvre 42,9 % du temps et
  « bon » 8,5 % : les seuils ont été calibrés KPI par KPI sans tenir compte de la
  règle d'agrégation « pire KPI » qui les combine. Une révision en v1.2 reste à
  acter entre les deux binômes ; en attendant, le contrat gelé est appliqué tel
  quel dans tout le code. Diagnostic chiffré : `reports/rapport_eda.md` §6.1.
- **`GET /eval/labels` : deux défauts contournés côté B**, à corriger côté A.
  Les horodatages ne sont pas rééchantillonnés (une jointure avec `/features`
  n'apparie aucune ligne), et l'enveloppe de réponse omet `has_more` (un client
  paginant s'arrête après une page). Détail : `reports/rapport_eda.md` §8.
- **`data_dictionary.md` §5 périmé** — la liste d'endpoints y figurant est
  antérieure à l'API v1.1.
- **Densité d'anomalies faible** — 9 épisodes seulement dans le segment de test,
  ce qui limite la puissance statistique de l'évaluation par épisode.

## Licence / Cadre

Projet académique — ESMT DETIC, non destiné à un usage en production.
