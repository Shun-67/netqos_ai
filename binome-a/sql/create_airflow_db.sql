-- Base de données séparée pour les métadonnées internes d'Airflow
-- (distincte de "netqos", qui contient les données métier du projet).
-- Exécuté automatiquement au premier démarrage du conteneur timescaledb
-- (dossier docker-entrypoint-initdb.d), avant init.sql.
CREATE DATABASE airflow;
