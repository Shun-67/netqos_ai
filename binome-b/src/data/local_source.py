"""
Source de données locale — « API simulée » du Binôme B.

Le contrat d'interface (§2.3 de la fiche de stage) prévoit explicitement que le
Binôme B développe contre une version simulée de l'API pendant que le Binôme A
la finalise. Ce module joue ce rôle : il lit un CSV brut produit par le
générateur du Binôme A et reproduit les transformations documentées dans
`binome-a/data_dictionary.md`, de façon à servir **exactement le même schéma**
que les endpoints `/kpi/history`, `/features` et `/eval/labels`.

Les règles implémentées ici sont une réimplémentation de la spécification
écrite, pas un import du code du Binôme A : la frontière A ↔ B reste étanche
(aucune dépendance à `binome-a/`, aucun accès à TimescaleDB). Dès que l'API
répond, `loader.py` bascule dessus sans qu'aucun modèle ne change.

Référence : data_dictionary.md §3 (nettoyage) et §4 (features), et le tableau
des colonnes de `binome-a/sql/init.sql`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import (
    BINOME_A_RAW_DIR,
    KPIS,
    POINTS_PER_HOUR,
    RESAMPLE_FREQ,
    SAMPLES_DIR,
    THRESHOLDS_FALLBACK,
)

# --- Règles de nettoyage (data_dictionary.md §3) -------------------
VALUE_BOUNDS = {
    "throughput": (0, None),
    "latency": (0, None),
    "jitter": (0, None),
    "packet_loss": (0, 100),
    "cell_load": (0, 100),
}
INTERPOLATION_LIMIT = 3  # gap < 3 points -> interpolation ; sinon is_missing

# --- Définition des features (data_dictionary.md §4) ---------------
MEAN_WINDOWS = {"5m": 5, "15m": 15, "30m": 30}
STD_WINDOWS = {"15m": 15}
LAGS = [1, 5, 10]

# Ordre de préférence : l'historique complet du Binôme A d'abord, les
# échantillons réduits de `data/samples/` seulement en dernier recours.
# L'ordre inverse serait un piège : un échantillon de démonstration (2 cellules,
# 1 jour) deviendrait silencieusement la source d'entraînement, et les modèles
# seraient ajustés sur 1/70e des données sans qu'aucune erreur ne le signale.
CANDIDATE_RAW_FILES = [
    BINOME_A_RAW_DIR / "historical_kpi.csv",
    BINOME_A_RAW_DIR / "verif_j14.csv",
    SAMPLES_DIR / "sample_kpi_with_labels.csv",
]

_CACHE: dict[str, pd.DataFrame] = {}


# ==================================================================
# Lecture du brut
# ==================================================================
def resolve_raw_file(path: Optional[Path] = None) -> Path:
    """Retourne le premier CSV brut disponible, ou lève une erreur explicite."""
    if path is not None:
        if not Path(path).exists():
            raise FileNotFoundError(f"Fichier brut introuvable : {path}")
        return Path(path)

    for candidate in CANDIDATE_RAW_FILES:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "Aucune donnée locale disponible. Générez un échantillon avec :\n"
        "  python binome-a/src/generator/synthetic_generator.py "
        "--cells 5 --days 14 --out binome-b/data/samples/sample_kpi_with_labels.csv"
    )


def load_raw(path: Optional[Path] = None) -> pd.DataFrame:
    """Charge le CSV brut (schéma `raw_kpi_measurements`)."""
    resolved = resolve_raw_file(path)
    key = f"raw::{resolved}"
    if key not in _CACHE:
        df = pd.read_csv(resolved, parse_dates=["ts"])
        if df["ts"].dt.tz is None:
            df["ts"] = df["ts"].dt.tz_localize("UTC")
        else:
            df["ts"] = df["ts"].dt.tz_convert("UTC")
        _CACHE[key] = df.sort_values(["cell_id", "ts"]).reset_index(drop=True)
    return _CACHE[key].copy()


# ==================================================================
# Nettoyage — équivalent de clean_kpi_measurements
# ==================================================================
def _clean_one_cell(df_cell: pd.DataFrame) -> pd.DataFrame:
    df_cell = (
        df_cell.drop_duplicates(subset="ts").set_index("ts").sort_index()
    )
    df_cell = df_cell.resample(RESAMPLE_FREQ).mean(numeric_only=True)

    # Un trou de resampling se lit sur n'importe quel KPI ; le contrat retient
    # throughput comme témoin.
    df_cell["is_missing"] = df_cell["throughput"].isna()

    df_cell[KPIS] = df_cell[KPIS].interpolate(
        method="linear", limit=INTERPOLATION_LIMIT, limit_direction="both"
    )
    return df_cell.reset_index()


def build_clean(path: Optional[Path] = None) -> pd.DataFrame:
    """Reproduit `clean_kpi_measurements` (= ce que sert GET /kpi/history)."""
    resolved = resolve_raw_file(path)
    key = f"clean::{resolved}"
    if key in _CACHE:
        return _CACHE[key].copy()

    raw = load_raw(resolved)
    for col, (low, high) in VALUE_BOUNDS.items():
        raw[col] = raw[col].clip(lower=low, upper=high)

    parts = []
    for cell_id, group in raw.groupby("cell_id"):
        cleaned = _clean_one_cell(group[["ts"] + KPIS])
        cleaned["cell_id"] = cell_id
        parts.append(cleaned)

    clean = pd.concat(parts, ignore_index=True)
    # Gaps trop longs pour être interpolés -> lignes supprimées (règle du contrat).
    clean = clean.dropna(subset=["throughput", "latency"])

    cols = ["ts", "cell_id"] + KPIS + ["is_missing"]
    clean = clean[cols].sort_values(["cell_id", "ts"]).reset_index(drop=True)
    _CACHE[key] = clean
    return clean.copy()


# ==================================================================
# Features — équivalent de kpi_features
# ==================================================================
def _features_one_cell(df_cell: pd.DataFrame) -> pd.DataFrame:
    df_cell = df_cell.set_index("ts").sort_index()
    feats = pd.DataFrame(index=df_cell.index)

    for kpi in KPIS:
        series = df_cell[kpi]
        for label, minutes in MEAN_WINDOWS.items():
            feats[f"{kpi}_mean_{label}"] = series.rolling(f"{minutes}min").mean()
        for label, minutes in STD_WINDOWS.items():
            feats[f"{kpi}_std_{label}"] = series.rolling(f"{minutes}min").std()
        for lag in LAGS:
            feats[f"{kpi}_lag_{lag}"] = series.shift(lag)
        feats[f"{kpi}_hour_mean"] = series.rolling(f"{POINTS_PER_HOUR}min").mean()

    feats["cell_load_hour_max"] = (
        df_cell["cell_load"].rolling(f"{POINTS_PER_HOUR}min").max()
    )
    feats["hour_of_day"] = df_cell.index.hour
    feats["day_of_week"] = df_cell.index.dayofweek

    return feats.dropna().reset_index()


def build_features(path: Optional[Path] = None) -> pd.DataFrame:
    """Reproduit `kpi_features` (= ce que sert GET /features)."""
    resolved = resolve_raw_file(path)
    key = f"features::{resolved}"
    if key in _CACHE:
        return _CACHE[key].copy()

    clean = build_clean(resolved)
    parts = []
    for cell_id, group in clean.groupby("cell_id"):
        feats = _features_one_cell(group[["ts"] + KPIS])
        feats["cell_id"] = cell_id
        parts.append(feats)

    features = pd.concat(parts, ignore_index=True)
    feature_cols = [c for c in features.columns if c not in ("ts", "cell_id")]
    features = features[["ts", "cell_id"] + feature_cols]
    features = features.sort_values(["cell_id", "ts"]).reset_index(drop=True)
    _CACHE[key] = features
    return features.copy()


# ==================================================================
# Vérité terrain — équivalent de GET /eval/labels
# ==================================================================
def build_labels(path: Optional[Path] = None) -> pd.DataFrame:
    """Retourne (ts, cell_id, is_anomaly) aligné sur la grille nettoyée.

    Un point de la grille est étiqueté anormal si au moins une mesure brute de
    la fenêtre correspondante l'était (agrégation par `max`).
    """
    resolved = resolve_raw_file(path)
    key = f"labels::{resolved}"
    if key in _CACHE:
        return _CACHE[key].copy()

    raw = load_raw(resolved)
    if "is_anomaly" not in raw.columns:
        raise KeyError(
            f"{resolved.name} ne contient pas `is_anomaly` : impossible d'évaluer "
            "la détection d'anomalies avec ce fichier."
        )
    raw["is_anomaly"] = raw["is_anomaly"].astype(bool)

    parts = []
    for cell_id, group in raw.groupby("cell_id"):
        labels = (
            group.set_index("ts")["is_anomaly"]
            .resample(RESAMPLE_FREQ)
            .max()
            .fillna(False)
            .astype(bool)
            .rename("is_anomaly")
            .reset_index()
        )
        labels["cell_id"] = cell_id
        parts.append(labels)

    out = pd.concat(parts, ignore_index=True)[["ts", "cell_id", "is_anomaly"]]
    out = out.sort_values(["cell_id", "ts"]).reset_index(drop=True)
    _CACHE[key] = out
    return out.copy()


# ==================================================================
# Métadonnées
# ==================================================================
def list_cells(path: Optional[Path] = None) -> list[str]:
    return sorted(load_raw(path)["cell_id"].unique().tolist())


def get_thresholds() -> dict[str, dict]:
    """Copie locale des seuils figés (contrat v1.1)."""
    return {k: dict(v) for k, v in THRESHOLDS_FALLBACK.items()}


def clear_cache() -> None:
    _CACHE.clear()
