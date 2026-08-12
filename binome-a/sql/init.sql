-- NetQoS-AI — Binôme A — Schéma de base de données (TimescaleDB)

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================
-- Table brute
-- ============================================================
CREATE TABLE IF NOT EXISTS raw_kpi_measurements (
    ts            TIMESTAMPTZ       NOT NULL,
    cell_id       TEXT              NOT NULL,
    throughput    DOUBLE PRECISION,
    latency       DOUBLE PRECISION,
    jitter        DOUBLE PRECISION,
    packet_loss   DOUBLE PRECISION,
    cell_load     DOUBLE PRECISION,
    is_anomaly    BOOLEAN           DEFAULT FALSE,  -- vérité terrain, réservée à l'évaluation
    source        TEXT              NOT NULL DEFAULT 'batch',
    ingested_at   TIMESTAMPTZ       NOT NULL DEFAULT now(),
    PRIMARY KEY (ts, cell_id)
);

SELECT create_hypertable('raw_kpi_measurements', 'ts', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_raw_cell_ts ON raw_kpi_measurements (cell_id, ts DESC);

-- ============================================================
-- Table nettoyée
-- ============================================================
CREATE TABLE IF NOT EXISTS clean_kpi_measurements (
    ts            TIMESTAMPTZ       NOT NULL,
    cell_id       TEXT              NOT NULL,
    throughput    DOUBLE PRECISION,
    latency       DOUBLE PRECISION,
    jitter        DOUBLE PRECISION,
    packet_loss   DOUBLE PRECISION,
    cell_load     DOUBLE PRECISION,
    is_missing    BOOLEAN           DEFAULT FALSE,
    PRIMARY KEY (ts, cell_id)
);

SELECT create_hypertable('clean_kpi_measurements', 'ts', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_clean_cell_ts ON clean_kpi_measurements (cell_id, ts DESC);

-- ============================================================
-- Table de features (pour le Binôme B)
-- ============================================================
-- Pour chaque KPI (throughput, latency, jitter, packet_loss, cell_load) :
--   *_mean_5m, *_mean_15m, *_mean_30m   -> moyennes glissantes
--   *_lag_1, *_lag_5, *_lag_10           -> valeurs décalées
--   *_std_15m                            -> écart-type glissant
--   *_hour_mean                          -> moyenne sur l'heure glissante
-- + cell_load_hour_max (demande spécifique du Binôme B)
CREATE TABLE IF NOT EXISTS kpi_features (
    ts                       TIMESTAMPTZ       NOT NULL,
    cell_id                  TEXT              NOT NULL,

    throughput_mean_5m       DOUBLE PRECISION,
    throughput_mean_15m      DOUBLE PRECISION,
    throughput_mean_30m      DOUBLE PRECISION,
    throughput_lag_1         DOUBLE PRECISION,
    throughput_lag_5         DOUBLE PRECISION,
    throughput_lag_10        DOUBLE PRECISION,
    throughput_std_15m       DOUBLE PRECISION,
    throughput_hour_mean     DOUBLE PRECISION,

    latency_mean_5m          DOUBLE PRECISION,
    latency_mean_15m         DOUBLE PRECISION,
    latency_mean_30m         DOUBLE PRECISION,
    latency_lag_1            DOUBLE PRECISION,
    latency_lag_5            DOUBLE PRECISION,
    latency_lag_10           DOUBLE PRECISION,
    latency_std_15m          DOUBLE PRECISION,
    latency_hour_mean        DOUBLE PRECISION,

    jitter_mean_5m           DOUBLE PRECISION,
    jitter_mean_15m          DOUBLE PRECISION,
    jitter_mean_30m          DOUBLE PRECISION,
    jitter_lag_1              DOUBLE PRECISION,
    jitter_lag_5              DOUBLE PRECISION,
    jitter_lag_10             DOUBLE PRECISION,
    jitter_std_15m            DOUBLE PRECISION,
    jitter_hour_mean          DOUBLE PRECISION,

    packet_loss_mean_5m      DOUBLE PRECISION,
    packet_loss_mean_15m     DOUBLE PRECISION,
    packet_loss_mean_30m     DOUBLE PRECISION,
    packet_loss_lag_1        DOUBLE PRECISION,
    packet_loss_lag_5        DOUBLE PRECISION,
    packet_loss_lag_10       DOUBLE PRECISION,
    packet_loss_std_15m      DOUBLE PRECISION,
    packet_loss_hour_mean    DOUBLE PRECISION,

    cell_load_mean_5m        DOUBLE PRECISION,
    cell_load_mean_15m       DOUBLE PRECISION,
    cell_load_mean_30m       DOUBLE PRECISION,
    cell_load_lag_1          DOUBLE PRECISION,
    cell_load_lag_5          DOUBLE PRECISION,
    cell_load_lag_10         DOUBLE PRECISION,
    cell_load_std_15m        DOUBLE PRECISION,
    cell_load_hour_mean      DOUBLE PRECISION,
    cell_load_hour_max       DOUBLE PRECISION,

    hour_of_day              INTEGER,
    day_of_week               INTEGER,
    PRIMARY KEY (ts, cell_id)
);

SELECT create_hypertable('kpi_features', 'ts', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_features_cell_ts ON kpi_features (cell_id, ts DESC);
