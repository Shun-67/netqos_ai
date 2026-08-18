"""
Ingénierie de caractéristiques : lit `clean_kpi_measurements`, calcule pour
chacun des 5 KPI (throughput, latency, jitter, packet_loss, cell_load) :

    - moyennes glissantes  : *_mean_5m, *_mean_15m, *_mean_30m
    - valeurs décalées     : *_lag_1, *_lag_5, *_lag_10
    - écart-type glissant  : *_std_15m
    - moyenne horaire       : *_hour_mean
    - cell_load_hour_max    (demande spécifique du Binôme B)
    - saisonnalité          : hour_of_day, day_of_week

et écrit le résultat dans `kpi_features` (consommée par le Binôme B via
l'API, endpoint GET /api/v1/features), conformément au contrat d'interface.

Usage:
    python -m src.preparation.build_features
"""

import sys
import pandas as pd

sys.path.append(".")
from src.db import get_engine, upsert_on_conflict

KPIS = ["throughput", "latency", "jitter", "packet_loss", "cell_load"]

# Fenêtres à calculer, en minutes (les données nettoyées sont à 1 point/minute)
MEAN_WINDOWS = {"5m": 5, "15m": 15, "30m": 30}
STD_WINDOW = {"15m": 15}
LAGS = [1, 5, 10]
HOUR_WINDOW_MIN = 60


def build_features_for_cell(df_cell: pd.DataFrame) -> pd.DataFrame:
    df_cell = df_cell.set_index("ts").sort_index()
    feats = pd.DataFrame(index=df_cell.index)

    for kpi in KPIS:
        series = df_cell[kpi]

        # Moyennes glissantes
        for label, minutes in MEAN_WINDOWS.items():
            feats[f"{kpi}_mean_{label}"] = series.rolling(f"{minutes}min").mean()

        # Écart-type glissant
        for label, minutes in STD_WINDOW.items():
            feats[f"{kpi}_std_{label}"] = series.rolling(f"{minutes}min").std()

        # Lags (décalages)
        for lag in LAGS:
            feats[f"{kpi}_lag_{lag}"] = series.shift(lag)

        # Moyenne glissante sur l'heure
        feats[f"{kpi}_hour_mean"] = series.rolling(f"{HOUR_WINDOW_MIN}min").mean()

    # Demande spécifique du Binôme B : max glissant sur l'heure pour cell_load
    feats["cell_load_hour_max"] = df_cell["cell_load"].rolling(f"{HOUR_WINDOW_MIN}min").max()

    # Saisonnalité (calculée par le Binôme A ; les encodages cycliques restent au Binôme B)
    feats["hour_of_day"] = df_cell.index.hour
    feats["day_of_week"] = df_cell.index.dayofweek

    return feats.dropna().reset_index()


def build_features(since: str = None) -> pd.DataFrame:
    engine = get_engine()
    cols = ["ts", "cell_id"] + KPIS
    query = f"SELECT {', '.join(cols)} FROM clean_kpi_measurements"
    if since:
        query += f" WHERE ts >= '{since}'"
    clean = pd.read_sql(query, engine, parse_dates=["ts"])

    if clean.empty:
        print("Aucune donnée nettoyée disponible pour le calcul des features.")
        return clean

    parts = []
    for cell_id, group in clean.groupby("cell_id"):
        f = build_features_for_cell(group.drop(columns="cell_id"))
        f["cell_id"] = cell_id
        parts.append(f)

    features_df = pd.concat(parts, ignore_index=True)

    # Ordonner les colonnes : ts, cell_id, puis toutes les features générées
    feature_cols = [c for c in features_df.columns if c not in ("ts", "cell_id")]
    ordered_cols = ["ts", "cell_id"] + feature_cols

    with engine.begin() as conn:
        features_df[ordered_cols].to_sql(
            "kpi_features", conn, if_exists="append", index=False,
            method=upsert_on_conflict, chunksize=2000
        )
    print(f"{len(features_df)} lignes de features écrites dans kpi_features "
          f"({len(feature_cols)} colonnes de features par ligne)")
    return features_df


if __name__ == "__main__":
    build_features()