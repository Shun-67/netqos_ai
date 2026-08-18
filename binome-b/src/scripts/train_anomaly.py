"""
Entraînement et évaluation des détecteurs d'anomalies (jalons J14 et J21).

Protocole appliqué :

  1. features chargées via la façade `loader` (API du Binôme A ou repli local) ;
  2. préparation Binôme B : encodages cycliques + features dérivées ;
  3. découpage **chronologique par cellule** avec purge de 60 min ;
  4. `fit` de chaque détecteur sur le seul segment d'entraînement, **sans jamais
     voir la vérité terrain** ;
  5. deux points de fonctionnement évalués sur le segment de test :
       - *exploitation* : seuil = quantile de contamination fixé a priori (2 %),
         calculé sur le segment d'entraînement, donc totalement non supervisé ;
       - *F1-optimal* : seuil choisi sur le segment de **validation** à l'aide
         des étiquettes, puis appliqué tel quel au test. C'est de la sélection
         de modèle légitime — les étiquettes n'entrent dans aucun `fit` — mais le
         chiffre obtenu doit se lire comme une borne haute atteignable seulement
         si l'on dispose d'un historique étiqueté.
  6. métriques ponctuelles **et** par épisode (rappel d'épisode, délai de
     détection, fausses alertes par heure).

Usage (depuis binome-b/) :
    python -m src.scripts.train_anomaly
    python -m src.scripts.train_anomaly --contamination 0.01
"""

from __future__ import annotations

import argparse
import json

import joblib
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.config import FIGURES_DIR, METRICS_DIR, MODELS_DIR
from src.data import loader
from src.evaluation import metrics as M
from src.features.preprocessing import prepare_features
from src.features.splits import align_labels, temporal_split
from src.models import anomaly

FIG_DIR = FIGURES_DIR / "anomalie"
FIG_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({"figure.dpi": 110, "font.size": 9, "axes.grid": True, "grid.alpha": 0.3})


# ==================================================================
# Préparation
# ==================================================================
def load_and_split(contamination: float):
    print(f"Source : {loader.source_description()}")
    raw_features = loader.load_features()
    features = prepare_features(raw_features)
    print(f"Features préparées : {features.shape[0]:,} lignes × {features.shape[1]} colonnes")

    split = temporal_split(features)
    split.assert_chronological()
    print("\nDécoupage temporel :")
    print(split.summary().to_string(index=False))

    labels = loader.load_labels()
    y_val = align_labels(split.val, labels).to_numpy()
    y_test = align_labels(split.test, labels).to_numpy()
    y_train = align_labels(split.train, labels).to_numpy()

    print(
        f"\nPrévalence des anomalies — train {y_train.mean()*100:.2f} % · "
        f"val {y_val.mean()*100:.2f} % · test {y_test.mean()*100:.2f} %"
    )
    return features, split, y_val, y_test


# ==================================================================
# Sélection d'architecture de l'autoencodeur
# ==================================================================
# Grille volontairement réduite : goulot d'étranglement et part de filtrage des
# extrêmes. Sans cette étape, comparer l'autoencodeur à une Isolation Forest
# réglée par défaut ne dirait rien — on comparerait un modèle non réglé à une
# baseline robuste. La sélection se fait sur la **PR-AUC de validation**, mesure
# indépendante du seuil, et jamais sur le segment de test.
AE_GRID = [
    {"hidden": (16, 8, 16), "trim_quantile": 0.0},
    {"hidden": (16, 8, 16), "trim_quantile": 0.02},
    {"hidden": (16, 6, 16), "trim_quantile": 0.05},
    {"hidden": (12, 4, 12), "trim_quantile": 0.02},
    {"hidden": (20, 10, 20), "trim_quantile": 0.02},
]


def select_autoencoder(
    cols: list[str], split, y_val: np.ndarray
) -> tuple[anomaly.AutoencoderDetector, pd.DataFrame]:
    """Choisit l'architecture de l'autoencodeur sur la PR-AUC de validation."""
    rows = []
    best_model, best_score = None, -np.inf

    for params in AE_GRID:
        model = anomaly.AutoencoderDetector(cols, **params)
        model.fit(split.train)
        scores_val = model.score(split.val)
        pr_auc = M.classification_metrics(y_val, scores_val >= np.quantile(scores_val, 0.98), scores_val).get(
            "pr_auc", np.nan
        )
        rows.append(
            {
                "goulot": str(params["hidden"]),
                "filtrage_extremes": params["trim_quantile"],
                "lignes_entrainement": model.n_train_kept_,
                "pr_auc_validation": round(float(pr_auc), 4),
            }
        )
        print(f"  goulot={params['hidden']} trim={params['trim_quantile']:.2f} -> PR-AUC val {pr_auc:.4f}")
        if pr_auc > best_score:
            best_model, best_score = model, pr_auc

    grid = pd.DataFrame(rows).sort_values("pr_auc_validation", ascending=False)
    print(f"  retenu : {grid.iloc[0]['goulot']} / trim={grid.iloc[0]['filtrage_extremes']}")
    return best_model, grid


# ==================================================================
# Évaluation d'un détecteur
# ==================================================================
def evaluate_detector(
    detector: anomaly.BaseDetector,
    split,
    y_val: np.ndarray,
    y_test: np.ndarray,
    contamination: float,
    skip_fit: bool = False,
) -> tuple[list[dict], np.ndarray]:
    """Ajuste, seuille de deux façons, et retourne les lignes de résultats."""
    if not skip_fit:
        detector.fit(split.train)

    scores_val = detector.score(split.val)
    scores_test = detector.score(split.test)

    operating_threshold = detector.default_threshold(split.train, contamination)
    f1_threshold = M.best_threshold(y_val, scores_val, criterion="f1")

    rows = []
    for label, threshold in (
        ("exploitation (non supervisé)", operating_threshold),
        ("F1-optimal (choisi sur validation)", f1_threshold),
    ):
        y_pred = scores_test >= threshold
        point = M.classification_metrics(y_test, y_pred, scores_test)

        episode_frame = split.test[["ts", "cell_id"]].copy()
        episode_frame["is_anomaly"] = y_test
        episode_frame["is_anomaly_pred"] = y_pred
        episode = M.episode_metrics_by_cell(episode_frame)
        episode.pop("detail_par_cellule")

        rows.append(
            {
                "detecteur": detector.name,
                "point_de_fonctionnement": label,
                "seuil": round(float(threshold), 5),
                **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in point.items()},
                **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in episode.items()},
            }
        )

    return rows, scores_test


# ==================================================================
# Figures
# ==================================================================
def fig_precision_recall(curves: dict[str, pd.DataFrame]) -> None:
    fig, ax = plt.subplots(figsize=(6.5, 4.6))
    for name, curve in curves.items():
        ordered = curve.sort_values("rappel")
        ax.plot(ordered["rappel"], ordered["precision"], marker=".", ms=3, label=name)
    ax.set_xlabel("Rappel")
    ax.set_ylabel("Précision")
    ax.set_title("Courbes précision / rappel sur le segment de test")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "precision_rappel.png", bbox_inches="tight")
    plt.close(fig)


def fig_score_distribution(scores: dict[str, np.ndarray], y_test: np.ndarray) -> None:
    fig, axes = plt.subplots(1, len(scores), figsize=(4 * len(scores), 3.4))
    axes = np.atleast_1d(axes)
    for ax, (name, values) in zip(axes, scores.items()):
        ax.hist(values[~y_test], bins=60, alpha=0.7, label="normal", color="#2c6fb5", density=True)
        ax.hist(values[y_test], bins=60, alpha=0.7, label="anomalie", color="#d1495b", density=True)
        ax.set_title(name, fontsize=9)
        ax.set_yscale("log")
        ax.set_xlabel("score")
    axes[0].set_ylabel("densité (log)")
    axes[0].legend(fontsize=8)
    fig.suptitle("Séparation des scores selon la vérité terrain (test)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "distribution_scores.png", bbox_inches="tight")
    plt.close(fig)


def fig_timeline(split, y_test: np.ndarray, scores: np.ndarray, threshold: float, name: str) -> None:
    """Chronogramme d'une cellule : score, seuil, épisodes réels et alertes."""
    test = split.test.reset_index(drop=True)
    cell_id = sorted(test["cell_id"].unique())[0]
    mask = (test["cell_id"] == cell_id).to_numpy()

    ts = test.loc[mask, "ts"].to_numpy()
    cell_scores, cell_truth = scores[mask], y_test[mask]
    cell_pred = cell_scores >= threshold

    fig, ax = plt.subplots(figsize=(12, 3.6))
    ax.plot(ts, cell_scores, lw=0.7, color="#2c6fb5", label=f"score {name}")
    ax.axhline(threshold, color="#d1495b", ls="--", lw=1.1, label="seuil d'alerte")
    ax.fill_between(
        ts, 0, 1, where=cell_truth, transform=ax.get_xaxis_transform(),
        color="#d1495b", alpha=0.18, label="épisode réel",
    )
    ax.scatter(
        ts[cell_pred], cell_scores[cell_pred], s=7, color="#e8a33d", zorder=3, label="alerte émise"
    )
    ax.set_title(f"Détection sur le segment de test — {cell_id} ({name})")
    ax.set_xlabel("Horodatage (UTC)")
    ax.set_ylabel("score d'atypicité")
    ax.legend(fontsize=8, ncol=4)
    fig.tight_layout()
    fig.savefig(FIG_DIR / f"chronogramme_{name}.png", bbox_inches="tight")
    plt.close(fig)


# ==================================================================
# Analyse d'erreurs
# ==================================================================
def error_analysis(
    split, y_test: np.ndarray, scores: np.ndarray, threshold: float, labels_source: pd.DataFrame
) -> pd.DataFrame:
    """Caractérise les faux négatifs : quels épisodes échappent au détecteur ?

    Un épisode manqué est bien plus coûteux qu'un point manqué. On croise donc
    les épisodes non détectés avec leur durée et leur amplitude, pour savoir si
    l'angle mort du modèle porte sur les épisodes courts, faibles, ou les deux.
    """
    test = split.test.reset_index(drop=True)
    y_pred = scores >= threshold

    rows = []
    for cell_id, group in test.groupby("cell_id"):
        idx = group.index.to_numpy()
        truth, pred = y_test[idx], y_pred[idx]
        for start, end in M._episodes(truth):
            window = pred[start : end + 1]
            episode = group.iloc[start : end + 1]
            rows.append(
                {
                    "cell_id": cell_id,
                    "debut": episode["ts"].iloc[0],
                    "duree_min": end - start + 1,
                    "detecte": bool(window.any()),
                    "part_points_detectes": round(float(window.mean()), 3),
                    "pic_latence_ratio": round(float(episode["latency_ratio_to_hour"].max()), 3)
                    if "latency_ratio_to_hour" in episode
                    else np.nan,
                    "pic_packet_loss": round(float(episode["packet_loss_mean_5m"].max()), 3)
                    if "packet_loss_mean_5m" in episode
                    else np.nan,
                    "score_max": round(float(scores[idx][start : end + 1].max()), 4),
                }
            )

    return pd.DataFrame(rows).sort_values(["detecte", "duree_min"])


# ==================================================================
# Entrée
# ==================================================================
def main() -> None:
    parser = argparse.ArgumentParser(description="Entraînement des détecteurs d'anomalies")
    parser.add_argument(
        "--contamination",
        type=float,
        default=0.02,
        help="Part d'alertes visée pour le point de fonctionnement d'exploitation",
    )
    args = parser.parse_args()

    features, split, y_val, y_test = load_and_split(args.contamination)
    thresholds = loader.get_thresholds()
    cols = anomaly.anomaly_features(features)
    print(f"\nEspace de features de détection : {len(cols)} colonnes")

    detectors = anomaly.build_detectors(cols, thresholds, args.contamination)

    # L'autoencodeur est le modèle « avancé » : il est réglé sur la validation
    # avant d'être comparé aux baselines, sinon la comparaison serait biaisée.
    print("\n--- sélection de l'architecture de l'autoencodeur (PR-AUC validation) ---")
    tuned_ae, ae_grid = select_autoencoder(cols, split, y_val)
    detectors["autoencodeur"] = tuned_ae
    ae_grid.to_csv(METRICS_DIR / "anomalie_grille_autoencodeur.csv", index=False)

    all_rows: list[dict] = []
    scores_by_detector: dict[str, np.ndarray] = {}
    curves: dict[str, pd.DataFrame] = {}

    for name, detector in detectors.items():
        print(f"\n--- {name} ---")
        rows, scores_test = evaluate_detector(
            detector, split, y_val, y_test, args.contamination,
            skip_fit=(name == "autoencodeur"),
        )
        all_rows.extend(rows)
        scores_by_detector[name] = scores_test
        curves[name] = M.sweep_threshold(y_test, scores_test)

        for row in rows:
            print(
                f"  {row['point_de_fonctionnement']:35s} "
                f"P={row['precision']:.3f} R={row['rappel']:.3f} F1={row['f1']:.3f} "
                f"rappel_episode={row['rappel_episode']:.3f} "
                f"FA/h={row['fausses_alertes_par_heure']:.2f}"
            )

        joblib.dump(detector, MODELS_DIR / f"anomaly_{name}.joblib")

    results = pd.DataFrame(all_rows)
    results.to_csv(METRICS_DIR / "anomalie_resultats.csv", index=False)

    # Figures
    fig_precision_recall(curves)
    fig_score_distribution(scores_by_detector, y_test)

    best = (
        results[results["point_de_fonctionnement"].str.startswith("exploitation")]
        .sort_values("f1", ascending=False)
        .iloc[0]
    )
    fig_timeline(
        split, y_test, scores_by_detector[best["detecteur"]], best["seuil"], best["detecteur"]
    )

    # Analyse d'erreurs sur le meilleur détecteur au point d'exploitation
    errors = error_analysis(
        split, y_test, scores_by_detector[best["detecteur"]], best["seuil"], pd.DataFrame()
    )
    errors.to_csv(METRICS_DIR / "anomalie_analyse_episodes.csv", index=False)

    summary = {
        "contamination_visee": args.contamination,
        "n_features": len(cols),
        "features": cols,
        "meilleur_detecteur_exploitation": best["detecteur"],
        "f1_meilleur": float(best["f1"]),
        "episodes_test": int(errors["episodes_reels"].sum()) if "episodes_reels" in errors else int(len(errors)),
        "episodes_manques": int((~errors["detecte"]).sum()),
        "duree_mediane_episodes_manques_min": float(
            errors.loc[~errors["detecte"], "duree_min"].median()
        )
        if (~errors["detecte"]).any()
        else None,
        "duree_mediane_episodes_detectes_min": float(
            errors.loc[errors["detecte"], "duree_min"].median()
        )
        if errors["detecte"].any()
        else None,
    }
    (METRICS_DIR / "anomalie_synthese.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nRésultats : reports/metrics/anomalie_resultats.csv")
    print(f"Figures   : {FIG_DIR}")
    print(f"Modèles   : {MODELS_DIR}")
    print(f"\nMeilleur détecteur (exploitation) : {best['detecteur']} — F1 = {best['f1']:.3f}")
    print(
        f"Épisodes manqués : {summary['episodes_manques']} / {len(errors)} "
        f"(durée médiane des manqués : {summary['duree_mediane_episodes_manques_min']} min)"
    )


if __name__ == "__main__":
    main()
