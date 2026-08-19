"""
Préparation des features côté Binôme B.

Le Binôme A livre des features brutes (moyennes glissantes, lags, écarts-types,
`hour_of_day`, `day_of_week`). Le Binôme B y ajoute ce qui relève de la
modélisation et non de l'ingénierie de données :

  - encodages cycliques de la saisonnalité (sin/cos) ;
  - normalisation ajustée sur le seul segment d'entraînement (anti-fuite) ;
  - sélection explicite des colonnes de features, avec garde-fou contre
    l'inclusion accidentelle de la vérité terrain.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler, StandardScaler

from src.config import KPIS

# Colonnes qui ne doivent JAMAIS entrer dans un `fit()`.
# `is_anomaly` est la vérité terrain (contrat : évaluation uniquement) ;
# `is_missing` est un drapeau de qualité, pas un signal réseau.
FORBIDDEN_FEATURES = {"is_anomaly", "is_missing", "ts", "cell_id", "source", "ingested_at"}

# Colonnes de saisonnalité fournies par le Binôme A, remplacées par leur
# encodage cyclique.
SEASONALITY_COLS = {"hour_of_day", "day_of_week"}


class LeakageError(RuntimeError):
    """Lève quand une colonne interdite atteint la matrice de features."""


# ==================================================================
# Encodages
# ==================================================================
def add_cyclic_features(df: pd.DataFrame, timestamp_col: str = "ts") -> pd.DataFrame:
    """Ajoute hour_sin/hour_cos et dow_sin/dow_cos.

    Réutilise `hour_of_day` / `day_of_week` du Binôme A si présents, sinon les
    recalcule depuis le timestamp. L'encodage cyclique évite la discontinuité
    artificielle entre 23h et 0h que produirait un entier brut.
    """
    df = df.copy()

    if "hour_of_day" in df.columns and "day_of_week" in df.columns:
        hour = df["hour_of_day"].astype(float)
        dow = df["day_of_week"].astype(float)
    else:
        ts = pd.to_datetime(df[timestamp_col], utc=True)
        hour = ts.dt.hour.astype(float)
        dow = ts.dt.dayofweek.astype(float)

    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    df["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    return df


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute quelques features de dynamique dérivées des features du Binôme A.

    Ces grandeurs sont des rapports/écarts entre features déjà livrées : elles
    n'utilisent aucune information future et ne violent donc pas le protocole
    temporel.
    """
    df = df.copy()
    for kpi in KPIS:
        short, long = f"{kpi}_mean_5m", f"{kpi}_mean_30m"
        if short in df.columns and long in df.columns:
            # Tendance : écart entre le court terme et le moyen terme.
            df[f"{kpi}_trend_5m_30m"] = df[short] - df[long]
        hour_mean = f"{kpi}_hour_mean"
        if short in df.columns and hour_mean in df.columns:
            # Écart relatif à la normale horaire : capte une dérive de régime.
            denom = df[hour_mean].replace(0, np.nan)
            df[f"{kpi}_ratio_to_hour"] = (df[short] / denom).fillna(1.0)
    return df


def prepare_features(df: pd.DataFrame, drop_seasonality_ints: bool = True) -> pd.DataFrame:
    """Chaîne complète de préparation appliquée au DataFrame de features."""
    out = add_cyclic_features(df)
    out = add_derived_features(out)
    if drop_seasonality_ints:
        out = out.drop(columns=[c for c in SEASONALITY_COLS if c in out.columns])
    return out.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)


# ==================================================================
# Sélection de colonnes
# ==================================================================
def feature_columns(df: pd.DataFrame) -> list[str]:
    """Colonnes numériques utilisables comme features, garde-fou inclus."""
    leaked = FORBIDDEN_FEATURES.intersection(df.columns) - {"ts", "cell_id"}
    cols = [
        c
        for c in df.columns
        if c not in FORBIDDEN_FEATURES and pd.api.types.is_numeric_dtype(df[c])
    ]
    if not cols:
        raise LeakageError("Aucune colonne de feature exploitable.")
    if leaked:
        # Non bloquant : les colonnes sont simplement écartées, mais on trace
        # l'événement car il signale souvent une jointure mal faite.
        print(f"[preprocessing] colonnes interdites écartées : {sorted(leaked)}")
    return cols


def assert_no_leakage(df: pd.DataFrame, cols: list[str]) -> None:
    """Vérifie qu'aucune colonne interdite ne figure dans la liste retenue."""
    intruders = set(cols).intersection(FORBIDDEN_FEATURES)
    if intruders:
        raise LeakageError(
            f"Fuite de données : {sorted(intruders)} ne doit jamais servir de feature."
        )


# ==================================================================
# Normalisation
# ==================================================================
def fit_scaler(train_df: pd.DataFrame, cols: list[str], kind: str = "robust"):
    """Ajuste un scaler sur le SEUL segment d'entraînement.

    `robust` (médiane / écart interquartile) est le défaut : les segments
    d'entraînement contiennent des anomalies injectées, qui feraient dériver la
    moyenne et l'écart-type d'un StandardScaler.
    """
    assert_no_leakage(train_df, cols)
    scaler = RobustScaler() if kind == "robust" else StandardScaler()
    scaler.fit(train_df[cols].to_numpy())
    return scaler


def transform(df: pd.DataFrame, cols: list[str], scaler) -> np.ndarray:
    return scaler.transform(df[cols].to_numpy())
