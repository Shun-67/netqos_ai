"""
Métriques d'évaluation — Binôme B.

Deux familles, conformes au §4.3 de la fiche de stage :

  - **détection d'anomalies** : précision, rappel, F1, matrice de confusion,
    PR-AUC et ROC-AUC ;
  - **prévision** : MAE, RMSE, MAPE.

S'y ajoutent trois métriques *orientées exploitation*, absentes de la liste
minimale mais indispensables pour juger l'utilité réelle d'un détecteur de QoS :

  - **rappel par épisode** : une dégradation réseau est un intervalle, pas un
    point. Un détecteur qui signale 1 minute sur 10 d'une panne de 10 minutes a
    un rappel ponctuel de 10 % mais a bel et bien alerté l'exploitant. Le rappel
    par épisode mesure la fraction d'épisodes détectés au moins une fois.
  - **délai de détection** : minutes entre le début réel d'un épisode et la
    première alerte. C'est ce qui détermine si la plateforme « anticipe » ou
    « constate ».
  - **taux de fausses alertes par heure** : une précision de 50 % n'a pas le même
    coût selon qu'elle produit 1 ou 100 alertes par heure. C'est la métrique qui
    conditionne l'acceptabilité opérationnelle.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

# ==================================================================
# Détection d'anomalies
# ==================================================================
def classification_metrics(
    y_true: np.ndarray, y_pred: np.ndarray, scores: np.ndarray | None = None
) -> dict:
    """Métriques ponctuelles de détection.

    `scores` (facultatif) permet de calculer les métriques indépendantes du
    seuil : PR-AUC (moyenne de précision) et ROC-AUC. Sur un problème aussi
    déséquilibré (~1 % de positifs), la PR-AUC est plus informative que la
    ROC-AUC, dont la valeur reste flatteuse même pour un détecteur médiocre.
    """
    y_true = np.asarray(y_true).astype(bool)
    y_pred = np.asarray(y_pred).astype(bool)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[False, True]).ravel()

    out = {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "rappel": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "vp": int(tp),
        "fp": int(fp),
        "vn": int(tn),
        "fn": int(fn),
        "n": int(len(y_true)),
        "taux_alerte_pct": float(y_pred.mean() * 100),
        "prevalence_pct": float(y_true.mean() * 100),
    }

    # Spécificité : part des points normaux correctement laissés tranquilles.
    out["specificite"] = float(tn / (tn + fp)) if (tn + fp) else 0.0

    if scores is not None and len(np.unique(y_true)) > 1:
        out["pr_auc"] = float(average_precision_score(y_true, scores))
        out["roc_auc"] = float(roc_auc_score(y_true, scores))
    return out


def _episodes(mask: np.ndarray) -> list[tuple[int, int]]:
    """Découpe un masque booléen en intervalles [début, fin] contigus."""
    mask = np.asarray(mask).astype(bool)
    if not mask.any():
        return []
    padded = np.concatenate(([False], mask, [False]))
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    return [(int(changes[i]), int(changes[i + 1] - 1)) for i in range(0, len(changes), 2)]


def episode_metrics(
    y_true: np.ndarray, y_pred: np.ndarray, minutes_per_point: int = 1
) -> dict:
    """Métriques par épisode : rappel, délai de détection, fausses alertes.

    Hypothèse : `y_true` et `y_pred` sont ordonnés chronologiquement et
    concernent une seule cellule (voir `episode_metrics_by_cell`).
    """
    y_true = np.asarray(y_true).astype(bool)
    y_pred = np.asarray(y_pred).astype(bool)

    true_episodes = _episodes(y_true)
    detected, delays = 0, []

    for start, end in true_episodes:
        window = y_pred[start : end + 1]
        if window.any():
            detected += 1
            delays.append(int(np.argmax(window)) * minutes_per_point)

    # Épisodes d'alerte ne recouvrant aucun épisode réel : fausses alertes.
    predicted_episodes = _episodes(y_pred)
    false_alarm_episodes = sum(
        1 for start, end in predicted_episodes if not y_true[start : end + 1].any()
    )

    duree_heures = len(y_true) * minutes_per_point / 60

    return {
        "episodes_reels": len(true_episodes),
        "episodes_detectes": detected,
        "rappel_episode": float(detected / len(true_episodes)) if true_episodes else np.nan,
        "delai_median_min": float(np.median(delays)) if delays else np.nan,
        "delai_max_min": float(np.max(delays)) if delays else np.nan,
        "episodes_fausse_alerte": false_alarm_episodes,
        "fausses_alertes_par_heure": float(false_alarm_episodes / duree_heures)
        if duree_heures
        else np.nan,
        "duree_evaluee_heures": round(duree_heures, 1),
    }


def episode_metrics_by_cell(
    df: pd.DataFrame,
    y_true_col: str = "is_anomaly",
    y_pred_col: str = "is_anomaly_pred",
    minutes_per_point: int = 1,
) -> dict:
    """Agrège les métriques par épisode sur toutes les cellules.

    Le découpage en épisodes doit impérativement se faire cellule par cellule :
    concaténer les cellules fusionnerait des épisodes distincts et fabriquerait
    de faux intervalles à la frontière entre deux cellules.
    """
    per_cell = []
    for cell_id, group in df.groupby("cell_id"):
        group = group.sort_values("ts")
        stats = episode_metrics(
            group[y_true_col].to_numpy(), group[y_pred_col].to_numpy(), minutes_per_point
        )
        stats["cell_id"] = cell_id
        per_cell.append(stats)

    frame = pd.DataFrame(per_cell)
    total_real = int(frame["episodes_reels"].sum())
    total_detected = int(frame["episodes_detectes"].sum())
    total_hours = float(frame["duree_evaluee_heures"].sum())
    total_false = int(frame["episodes_fausse_alerte"].sum())

    return {
        "episodes_reels": total_real,
        "episodes_detectes": total_detected,
        "rappel_episode": float(total_detected / total_real) if total_real else np.nan,
        "delai_median_min": float(frame["delai_median_min"].median()),
        "episodes_fausse_alerte": total_false,
        "fausses_alertes_par_heure": float(total_false / total_hours) if total_hours else np.nan,
        "detail_par_cellule": frame,
    }


def sweep_threshold(
    y_true: np.ndarray, scores: np.ndarray, n_points: int = 200
) -> pd.DataFrame:
    """Balaye les seuils de décision et retourne la courbe précision/rappel/F1.

    Sert à choisir un point de fonctionnement sur le segment de **validation**,
    jamais sur le test.
    """
    y_true = np.asarray(y_true).astype(bool)
    scores = np.asarray(scores, dtype=float)
    candidates = np.quantile(scores, np.linspace(0.50, 0.9995, n_points))

    rows = []
    for threshold in np.unique(candidates):
        y_pred = scores >= threshold
        rows.append(
            {
                "seuil": float(threshold),
                "taux_alerte_pct": float(y_pred.mean() * 100),
                "precision": float(precision_score(y_true, y_pred, zero_division=0)),
                "rappel": float(recall_score(y_true, y_pred, zero_division=0)),
                "f1": float(f1_score(y_true, y_pred, zero_division=0)),
            }
        )
    return pd.DataFrame(rows)


def best_threshold(y_true: np.ndarray, scores: np.ndarray, criterion: str = "f1") -> float:
    """Seuil maximisant le critère demandé, choisi sur la validation."""
    curve = sweep_threshold(y_true, scores)
    if curve.empty:
        return float(np.quantile(scores, 0.98))
    return float(curve.loc[curve[criterion].idxmax(), "seuil"])


# ==================================================================
# Prévision
# ==================================================================
def regression_metrics(
    y_true: np.ndarray, y_pred: np.ndarray, epsilon: float = 1e-6
) -> dict:
    """MAE, RMSE, MAPE et sMAPE.

    Le MAPE est instable quand la vraie valeur approche zéro : c'est le cas de
    `packet_loss`, souvent proche de 0 %. Le sMAPE (symétrique, borné à 200 %)
    est donc reporté en parallèle et doit être préféré pour ce KPI.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    valid = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true, y_pred = y_true[valid], y_pred[valid]

    if len(y_true) == 0:
        return {"mae": np.nan, "rmse": np.nan, "mape": np.nan, "smape": np.nan, "n": 0}

    error = y_pred - y_true
    denom_mape = np.maximum(np.abs(y_true), epsilon)
    denom_smape = np.maximum((np.abs(y_true) + np.abs(y_pred)) / 2, epsilon)

    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "mape": float(np.mean(np.abs(error) / denom_mape) * 100),
        "smape": float(np.mean(np.abs(error) / denom_smape) * 100),
        "biais": float(np.mean(error)),
        "n": int(len(y_true)),
    }


def skill_score(model_metrics: dict, baseline_metrics: dict, metric: str = "mae") -> float:
    """Gain relatif d'un modèle sur une référence, en %.

    Positif = le modèle fait mieux que la référence. C'est la seule lecture qui
    permette de trancher l'exigence du §8.2 de la fiche : « un modèle avancé ne
    se justifie que s'il bat la baseline ».
    """
    base = baseline_metrics.get(metric)
    model = model_metrics.get(metric)
    if base is None or model is None or not np.isfinite(base) or base == 0:
        return np.nan
    return float((base - model) / base * 100)
