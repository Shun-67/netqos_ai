# Dictionnaire de données — NetQoS-AI (Binôme A)

Ce document est la base du **contrat d'interface** à figer au jalon J7 avec le Binôme B.
À faire relire et valider par les deux binômes avant J7.

## 1. Convention temporelle

- Horodatage : UTC, format ISO 8601 (`2026-08-02T14:30:00Z`)
- Granularité brute : 1 point toutes les **60 secondes** par cellule
- Resampling proposé pour les features : fenêtres de **5 min** et **15 min**

## 2. Table brute : `raw_kpi_measurements`

| Champ         | Type      | Unité   | Description                                      |
|---------------|-----------|---------|---------------------------------------------------|
| ts            | timestamp | UTC     | Horodatage de la mesure                            |
| cell_id       | text      | —       | Identifiant de la cellule/antenne réseau           |
| throughput    | float     | Mbit/s  | Débit mesuré                                       |
| latency       | float     | ms      | Latence round-trip                                 |
| jitter        | float     | ms      | Gigue                                              |
| packet_loss   | float     | %       | Taux de perte de paquets (0-100)                   |
| cell_load     | float     | %       | Charge de la cellule (0-100)                       |
| is_anomaly    | boolean   | —       | Vérité terrain (uniquement en génération synthétique, jamais fournie au modèle) |
| source        | text      | —       | `batch` ou `stream`                                |
| ingested_at   | timestamp | UTC     | Horodatage d'ingestion (traçabilité)               |

## 3. Table nettoyée : `clean_kpi_measurements`

Même schéma que `raw_kpi_measurements`, après :
- suppression des doublons (clé `ts + cell_id`)
- traitement des valeurs manquantes (interpolation linéaire, gap < 3 points ; sinon flag `is_missing`)
- clipping des valeurs aberrantes physiquement impossibles (ex : packet_loss > 100, throughput < 0)
- resampling à la granularité régulière choisie

Colonne ajoutée :
| is_missing | boolean | — | true si la valeur a été imputée |

## 4. Table de features : `kpi_features`

Calculées par fenêtre glissante par `cell_id`, à la granularité définie.

| Champ                    | Type  | Description                                   |
|---------------------------|-------|------------------------------------------------|
| ts                        | timestamp | Fin de la fenêtre                          |
| cell_id                   | text  | —                                              |
| throughput_mean_5m        | float | Moyenne débit sur 5 min                        |
| throughput_std_5m         | float | Écart-type débit sur 5 min                     |
| latency_mean_5m           | float | Moyenne latence sur 5 min                      |
| latency_lag_1             | float | Valeur de latence à t-1                        |
| jitter_mean_5m            | float | Moyenne gigue sur 5 min                        |
| packet_loss_mean_5m       | float | Moyenne perte de paquets sur 5 min             |
| cell_load_mean_5m         | float | Moyenne charge cellule sur 5 min               |
| hour_of_day               | int   | Saisonnalité horaire (0-23)                    |
| day_of_week                | int   | Saisonnalité hebdo (0-6)                       |

*(Liste indicative — à ajuster avec le Binôme B selon les besoins des modèles.)*

## 5. Endpoints API prévus (à détailler en Partie 6 — spécification OpenAPI générée automatiquement par FastAPI sur `/docs`)

| Endpoint                          | Méthode | Description                                        |
|------------------------------------|---------|------------------------------------------------------|
| `/health`                          | GET     | Vérification de disponibilité                        |
| `/kpi/raw`                         | GET     | Données brutes, filtrable par `cell_id`, `start`, `end` |
| `/kpi/clean`                       | GET     | Données nettoyées                                    |
| `/kpi/features`                    | GET     | Features prêtes pour l'IA                             |
| `/cells`                           | GET     | Liste des cellules disponibles                        |
| `/stream/latest`                   | GET     | Dernières mesures reçues (flux simulé)                |

## 6. Gestion des valeurs manquantes / conventions

- Une valeur manquante en base = `NULL`, jamais `0` ou `-1`.
- Le champ `is_missing`/`is_anomaly` n'est JAMAIS exposé comme feature d'entraînement pour éviter la fuite de données (`is_anomaly` sert uniquement à l'évaluation du Binôme B).
- Versionnement du schéma : toute modification de colonne = incrément de version documentée ici en haut de fichier.

---
**Statut : brouillon — à valider avec le Binôme B avant J7.**
