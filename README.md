# NetQoS-AI

> Les sections marquées `[À compléter]` restent à produire : il s'agit des
> captures d'écran de la démonstration (semaine 4).

Plateforme intelligente de surveillance et de prévision de la qualité de
service réseau. Projet ESMT / DETIC — Ingénierie des Données et Intelligence
Artificielle, année académique 2025-2026.

## Équipe

| Binôme | Périmètre | Dossier |
|---|---|---|
| A | Ingénierie des données & pipeline | [`binome-a/`](./binome-a) |
| B | Intelligence artificielle & restitution | [`binome-b/`](./binome-b) |

Encadrant : Prof. Boudal NIANG.

## Présentation du projet

La qualité de service est un enjeu central pour tout opérateur de réseau : une
dégradation non détectée à temps se traduit par une expérience utilisateur
dégradée et par un risque sur les engagements de niveau de service. Les réseaux
produisent un volume massif d'indicateurs horodatés, mais ils sont le plus
souvent observés *a posteriori* plutôt que transformés en capacité
d'anticipation.

La supervision traditionnelle repose sur des seuils fixes, dont ce projet a
mesuré les deux limites plutôt que de les postuler. Un seuil fixe ignore la
variabilité normale du trafic — une charge à 90 % est banale à l'heure de pointe
et anormale à quatre heures du matin. Et il ne détecte que les anomalies
d'amplitude, pas celles de forme. Chiffré sur nos données : les seuils du
contrat classent « critique » **42,5 % des instants pourtant normaux**, tout en
laissant **14,2 % des anomalies réelles** sous leur radar.

NetQoS-AI dépasse cette limite en combinant un pipeline de données
industrialisé (Binôme A) avec des méthodes d'apprentissage évaluées selon un
protocole à l'épreuve de la fuite de données (Binôme B), restituées dans un
tableau de bord destiné à un exploitant réseau. Le détecteur retenu multiplie
par douze le F1 des seuils fixes et divise leurs fausses alertes par trente,
**sans jamais voir une étiquette d'anomalie**.

Présentation complète — contexte, architecture, choix techniques, résultats,
limites et perspectives : [`reports/rapport_projet_netqos_ai.md`](./reports/rapport_projet_netqos_ai.md).

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
├── reports/                 # Livrables communs (contrat d'interface, schéma d'architecture, rapport de projet)
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

## Livrables

Les documents rédigés sont **en Markdown dans le dépôt** : GitHub les rend avec
leurs tableaux et leurs figures, ils sont donc lisibles sans rien installer.

| Livrable | Fiche | Document |
|---|---|---|
| Contrat d'interface (figé au J7) | §6.1 | [`reports/contrat_interface.docx`](./reports/contrat_interface.docx) |
| Schéma d'architecture annoté | §6.1 · §4.4 | [`reports/architecture_schema.png`](./reports/architecture_schema.png) |
| **Rapport de projet** | §6.1 | [`reports/rapport_projet_netqos_ai.md`](./reports/rapport_projet_netqos_ai.md) |
| Rapport d'analyse exploratoire | §6.3 | [`reports/rapport_eda.md`](./reports/rapport_eda.md) |
| Rapport d'évaluation des modèles | §6.3 | [`reports/rapport_evaluation_modeles.md`](./reports/rapport_evaluation_modeles.md) |
| Notice d'utilisation du tableau de bord | §6.3 | [`binome-b/NOTICE_DASHBOARD.md`](./binome-b/NOTICE_DASHBOARD.md) |
| Guide de vérification en cinq niveaux | — | [`binome-b/GUIDE_TEST.md`](./binome-b/GUIDE_TEST.md) |
| Retours techniques du Binôme B au Binôme A | — | [`reports/retours_au_binome_a.md`](./reports/retours_au_binome_a.md) |
| **Support de soutenance** | §6.1 | [`reports/support_soutenance.md`](./reports/support_soutenance.md) — exporté en `.pptx` |
| **Déroulé de la démonstration live** | §6.1 | [`reports/deroule_demo.md`](./reports/deroule_demo.md) |
| Documentation de l'API (OpenAPI) | §6.2 | `http://localhost:8000/docs`, API démarrée |

### Obtenir les versions Word (.docx)

Les six documents Markdown s'exportent en `.docx` — page de garde, table des
matières, tableaux et figures embarquées — par une seule commande :

```bash
cd binome-b
pip install -r requirements.txt          # si ce n'est pas déjà fait
python -m src.scripts.export_livrables        # -> reports/docx/*.docx
```

Prérequis : **pandoc** (`winget install --id JohnMacFarlane.Pandoc` sous Windows,
sinon https://pandoc.org/installing.html). Le script vérifie sa présence et
affiche la commande d'installation s'il manque.

Pour n'exporter qu'un document :

```bash
python -m src.scripts.export_livrables --fichier ../reports/rapport_projet_netqos_ai.md
```

Ces `.docx` ne sont **pas versionnés** (`reports/docx/` est dans le
`.gitignore`) : le Markdown est la source, le Word en est un artefact
reproductible. Un binaire versionné peut se retrouver en retard sur sa source
sans que rien ne le signale, puisqu'il ne se relit pas dans un diff — le produire
au moment de la remise garantit qu'il est à jour. Le style suit le contrat
d'interface, via un gabarit lui aussi reconstruit par script
(`binome-b/src/scripts/build_docx_template.py`).

Si les modèles ont été réentraînés, régénérer d'abord les rapports
(`python -m src.scripts.make_report`) puis relancer l'export : les rapports
citent les chiffres de `reports/metrics/`.

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
| **J30** | Plateforme complète, documentée, démontrée | **livrables complets** : rapport de projet, rapport d'évaluation, analyse exploratoire, notice, schéma d'architecture, support de soutenance et déroulé de la démonstration · *reste à faire : les captures d'écran, et répéter la démo en conditions réelles* |

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

*(Captures des 6 onglets du dashboard, à insérer aux emplacements marqués
`📷` dans [`reports/support_soutenance.md`](./reports/support_soutenance.md).)*

Le déroulé minuté de la démonstration, avec ses vérifications préalables et ses
points de repli, est dans [`reports/deroule_demo.md`](./reports/deroule_demo.md).

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
