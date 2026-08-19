"""
Classification de l'état QoS : bon / dégradé / critique.

Approche retenue : **règles déterministes** appliquées aux seuils figés du
contrat d'interface (GET /api/v1/thresholds), et non un classifieur appris.

Justification : l'état QoS est une convention d'exploitation, pas un phénomène
à découvrir. Les seuils ont été négociés et gelés au jalon J7 ; un modèle appris
les réinventerait de façon opaque et non auditable, alors qu'un exploitant
réseau doit pouvoir justifier une alerte par un dépassement de seuil nommé.
L'apprentissage est réservé à ce qui n'est pas spécifiable par une règle :
la détection d'anomalies (`anomaly.py`) et la prévision (`forecast.py`).

L'état est déterminé par la **règle du pire KPI** : l'état global d'une cellule
est le plus dégradé des états KPI par KPI. Un seul indicateur critique suffit
donc à déclarer la cellule critique — comportement voulu en supervision.

Ce module sert deux usages :
  - étiqueter l'état courant à partir des KPI mesurés ;
  - étiqueter l'état **prévu**, en appliquant les mêmes règles aux prévisions
    de `forecast.py` (exigence fonctionnelle §3.2.6 + §2.2 « classification de
    l'état QoS à partir des KPI et des prévisions »).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import KPIS

# Ordre de gravité croissante ; l'agrégation prend le maximum.
STATES = ["bon", "dégradé", "critique"]
STATE_RANK = {state: rank for rank, state in enumerate(STATES)}
STATE_COLORS = {"bon": "#2e9e5b", "dégradé": "#e8a33d", "critique": "#d1495b"}


def classify_kpi(value: float, bounds: dict) -> str:
    """État d'un KPI isolé selon ses bornes contractuelles.

    Deux familles de bornes coexistent dans le contrat :
      - `good_max` / `degraded_max` : une valeur haute est mauvaise
        (latency, jitter, packet_loss, cell_load) ;
      - `good_min` / `degraded_min` : une valeur basse est mauvaise
        (throughput).
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "bon"  # absence de mesure : ne déclenche pas d'alerte

    if "good_max" in bounds:
        if value > bounds["degraded_max"]:
            return "critique"
        if value > bounds["good_max"]:
            return "dégradé"
        return "bon"

    if "good_min" in bounds:
        if value < bounds["degraded_min"]:
            return "critique"
        if value < bounds["good_min"]:
            return "dégradé"
        return "bon"

    raise ValueError(f"Bornes inexploitables : {bounds}")


def classify_row(row, thresholds: dict[str, dict]) -> str:
    """État global d'une mesure : le pire état parmi les KPI disponibles."""
    worst = 0
    for kpi, bounds in thresholds.items():
        if kpi not in row or pd.isna(row.get(kpi)):
            continue
        worst = max(worst, STATE_RANK[classify_kpi(float(row[kpi]), bounds)])
    return STATES[worst]


def classify_frame(
    df: pd.DataFrame,
    thresholds: dict[str, dict],
    suffix: str = "",
    out_col: str = "qos_state",
) -> pd.DataFrame:
    """Classe un DataFrame entier de façon vectorisée.

    `suffix` permet de classer des colonnes dérivées sans les renommer :
    par exemple `suffix="_pred_15m"` classera `latency_pred_15m`,
    `throughput_pred_15m`, etc. — c'est ainsi qu'on obtient l'état QoS prévu.
    """
    rank = pd.Series(0, index=df.index, dtype=int)
    per_kpi_state = {}

    for kpi, bounds in thresholds.items():
        col = f"{kpi}{suffix}"
        if col not in df.columns:
            continue
        values = pd.to_numeric(df[col], errors="coerce")

        if "good_max" in bounds:
            kpi_rank = np.where(
                values > bounds["degraded_max"], 2, np.where(values > bounds["good_max"], 1, 0)
            )
        else:
            kpi_rank = np.where(
                values < bounds["degraded_min"], 2, np.where(values < bounds["good_min"], 1, 0)
            )
        # Une valeur manquante ne dégrade pas l'état.
        kpi_rank = np.where(values.isna(), 0, kpi_rank)

        per_kpi_state[f"{kpi}_state"] = pd.Categorical.from_codes(
            kpi_rank, categories=STATES
        )
        rank = np.maximum(rank, kpi_rank)

    out = df.copy()
    out[out_col] = pd.Categorical.from_codes(np.asarray(rank), categories=STATES)
    for name, series in per_kpi_state.items():
        out[f"{name}{suffix}"] = series
    return out


def dominant_cause(row, thresholds: dict[str, dict], suffix: str = "") -> str:
    """KPI responsable de l'état courant — sert à motiver l'alerte affichée.

    Retourne le nom du KPI le plus dégradé, avec son dépassement relatif au
    seuil `good`, afin que l'exploitant sache quoi regarder en premier.
    """
    worst_rank, worst_kpi, worst_excess = 0, None, 0.0

    for kpi, bounds in thresholds.items():
        col = f"{kpi}{suffix}"
        if col not in row or pd.isna(row.get(col)):
            continue
        value = float(row[col])
        state = classify_kpi(value, bounds)
        rank = STATE_RANK[state]
        if "good_max" in bounds:
            reference = bounds["good_max"]
            excess = (value - reference) / reference if reference else 0.0
        else:
            reference = bounds["good_min"]
            excess = (reference - value) / reference if reference else 0.0

        if rank > worst_rank or (rank == worst_rank and excess > worst_excess):
            worst_rank, worst_kpi, worst_excess = rank, kpi, excess

    if worst_kpi is None or worst_rank == 0:
        return "aucun"
    return f"{worst_kpi} ({worst_excess:+.0%} vs seuil bon)"


def state_distribution(df: pd.DataFrame, col: str = "qos_state") -> pd.DataFrame:
    """Répartition des états, en effectif et en pourcentage."""
    counts = df[col].value_counts().reindex(STATES, fill_value=0)
    return pd.DataFrame(
        {
            "etat": counts.index,
            "n": counts.to_numpy(),
            "pct": (counts / max(len(df), 1) * 100).round(2).to_numpy(),
        }
    )
