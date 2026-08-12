"""
Préparation des features côté Binôme B.
Encodages cycliques, classification QoS.
"""
import numpy as np
import pandas as pd

def add_cyclic_features(df, timestamp_col="ts"):
    df = df.copy()
    df[timestamp_col] = pd.to_datetime(df[timestamp_col])
    hour = df[timestamp_col].dt.hour
    dow = df[timestamp_col].dt.dayofweek
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    df["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    return df

def classify_qos(row, thresholds):
    for kpi, bounds in thresholds.items():
        val = row.get(kpi)
        if val is None:
            continue
        if "good_max" in bounds and val > bounds["degraded_max"]:
            return "critique"
        if "good_min" in bounds and val < bounds["degraded_min"]:
            return "critique"
        if "good_max" in bounds and val > bounds["good_max"]:
            return "dégradé"
        if "good_min" in bounds and val < bounds["good_min"]:
            return "dégradé"
    return "bon"
