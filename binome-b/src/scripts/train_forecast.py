"""
Entraînement et évaluation des modèles de prévision (jalons J14 et J21).

Protocole :
  1. cibles construites par jointure temporelle `(cell_id, ts + h)` sur
     l'historique nettoyé — pas de `shift` positionnel ;
  2. découpage chronologique par cellule avec purge de 60 min ;
  3. entraînement sur le seul segment d'entraînement ;
  4. **comparaison sur origines communes** : ARIMA n'étant évaluable que sur un
     sous-échantillon d'origines, tous les modèles sont comparés sur ce même
     sous-ensemble, pour que les MAE/RMSE soient commensurables. Les modèles
     rapides sont en outre évalués sur la totalité du test, reporté à part.
  5. métriques MAE / RMSE / MAPE / sMAPE + *skill score* relatif à la persistance ;
  6. évaluation de bout en bout de l'objectif métier : l'état QoS **prévu**
     coïncide-t-il avec l'état QoS réellement observé à t+h ?

Usage (depuis binome-b/) :
    python -m src.scripts.train_forecast
    python -m src.scripts.train_forecast --no-arima      # itération rapide
"""

from __future__ import annotations

import argparse
import json
import time

import joblib
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.config import FIGURES_DIR, FORECAST_HORIZONS, KPI_UNITS, KPIS, METRICS_DIR, MODELS_DIR
from src.data import loader
from src.evaluation import metrics as M
from src.features.preprocessing import prepare_features
from src.features.splits import temporal_split
from src.models import forecast as F
from src.models import qos_state

FIG_DIR = FIGURES_DIR / "prevision"
FIG_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({"figure.dpi": 110, "font.size": 9, "axes.grid": True, "grid.alpha": 0.3})


# ==================================================================
# Préparation
# ==================================================================
def load_and_split():
    print(f"Source : {loader.source_description()}")
    history = loader.load_history()
    features = prepare_features(loader.load_features())

    dataset = F.build_targets(features, history, FORECAST_HORIZONS, KPIS)
    # Une ligne n'est exploitable que si toutes ses cibles existent : sinon les
    # horizons seraient évalués sur des sous-ensembles différents.
    target_cols = [F.target_column(k, h) for k in KPIS for h in FORECAST_HORIZONS]
    dataset = dataset.dropna(subset=target_cols).reset_index(drop=True)
    print(f"Jeu supervisé : {dataset.shape[0]:,} lignes × {len(F.forecast_features(dataset))} prédicteurs")

    split = temporal_split(dataset)
    split.assert_chronological()
    print("\nDécoupage temporel :")
    print(split.summary().to_string(index=False))
    return history, split


# ==================================================================
# Évaluation
# ==================================================================
def evaluate(
    forecasters: dict[str, F.BaseForecaster],
    split,
    mask: np.ndarray | None,
    scope_label: str,
) -> pd.DataFrame:
    """Évalue tous les prédicteurs sur le segment de test (éventuellement masqué)."""
    test = split.test.reset_index(drop=True)
    subset = test[mask].reset_index(drop=True) if mask is not None else test

    rows = []
    baseline_cache: dict[tuple[str, int], dict] = {}

    for name, model in forecasters.items():
        for kpi in KPIS:
            for horizon in FORECAST_HORIZONS:
                y_true = subset[F.target_column(kpi, horizon)].to_numpy()
                y_pred = (
                    model.predict(test, kpi, horizon)[mask]
                    if mask is not None
                    else model.predict(test, kpi, horizon)
                )
                stats = M.regression_metrics(y_true, y_pred)

                if name == "persistance":
                    baseline_cache[(kpi, horizon)] = stats

                rows.append(
                    {
                        "perimetre": scope_label,
                        "modele": name,
                        "kpi": kpi,
                        "unite": KPI_UNITS[kpi],
                        "horizon_min": horizon,
                        **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in stats.items()},
                    }
                )

    frame = pd.DataFrame(rows)
    # Skill score : gain de MAE relatif à la persistance, seule lecture qui
    # tranche l'exigence « battre la baseline » du §8.2 de la fiche.
    frame["gain_mae_vs_persistance_pct"] = frame.apply(
        lambda row: round(
            M.skill_score(
                {"mae": row["mae"]}, baseline_cache.get((row["kpi"], row["horizon_min"]), {}), "mae"
            ),
            2,
        ),
        axis=1,
    )
    return frame


def evaluate_qos_state(
    model: F.BaseForecaster, split, thresholds: dict, horizon: int
) -> tuple[dict, pd.DataFrame]:
    """Évalue la chaîne complète : prévision -> état QoS prévu vs état réel.

    C'est la métrique la plus proche de l'usage : l'exploitant ne consomme pas
    une prévision de latence en millisecondes, il consomme un état annoncé.
    """
    test = split.test.reset_index(drop=True)

    predicted = pd.DataFrame({"ts": test["ts"], "cell_id": test["cell_id"]})
    actual = pd.DataFrame({"ts": test["ts"], "cell_id": test["cell_id"]})
    for kpi in KPIS:
        predicted[kpi] = model.predict(test, kpi, horizon)
        actual[kpi] = test[F.target_column(kpi, horizon)].to_numpy()

    predicted = qos_state.classify_frame(predicted, thresholds)
    actual = qos_state.classify_frame(actual, thresholds)

    valid = predicted["qos_state"].notna() & actual["qos_state"].notna()
    y_pred = predicted.loc[valid, "qos_state"].astype(str)
    y_true = actual.loc[valid, "qos_state"].astype(str)

    matrix = pd.crosstab(y_true, y_pred).reindex(
        index=qos_state.STATES, columns=qos_state.STATES, fill_value=0
    )

    exact = float((y_true == y_pred).mean())
    # Une alerte manquée (état réel critique annoncé bon) est bien plus grave
    # qu'une alerte excessive : on mesure les deux séparément.
    critical_real = y_true == "critique"
    missed_critical = float(((y_pred != "critique") & critical_real).sum() / max(critical_real.sum(), 1))

    return (
        {
            "horizon_min": horizon,
            "exactitude_etat": round(exact, 4),
            "part_critiques_manques": round(missed_critical, 4),
            "n": int(valid.sum()),
        },
        matrix,
    )


# ==================================================================
# Figures
# ==================================================================
def fig_mae_by_horizon(results: pd.DataFrame) -> None:
    kpis = KPIS
    fig, axes = plt.subplots(1, len(kpis), figsize=(3.4 * len(kpis), 3.4), sharex=True)
    for ax, kpi in zip(np.atleast_1d(axes), kpis):
        sub = results[results["kpi"] == kpi]
        for name, group in sub.groupby("modele"):
            ordered = group.sort_values("horizon_min")
            ax.plot(ordered["horizon_min"], ordered["mae"], marker="o", ms=4, label=name)
        ax.set_title(f"{kpi} ({KPI_UNITS[kpi]})", fontsize=9)
        ax.set_xlabel("horizon (min)")
        ax.set_xticks(FORECAST_HORIZONS)
    np.atleast_1d(axes)[0].set_ylabel("MAE")
    np.atleast_1d(axes)[0].legend(fontsize=7)
    fig.suptitle("MAE par horizon et par KPI (origines communes du segment de test)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "mae_par_horizon.png", bbox_inches="tight")
    plt.close(fig)


def fig_forecast_example(
    forecasters: dict[str, F.BaseForecaster], split, kpi: str, horizon: int
) -> None:
    """Tracé réel vs prévu sur une fenêtre lisible."""
    test = split.test.reset_index(drop=True)
    cell_id = sorted(test["cell_id"].unique())[0]
    mask = (test["cell_id"] == cell_id).to_numpy()
    window = np.flatnonzero(mask)[:720]  # 12 heures

    ts = test.loc[window, "ts"]
    truth = test.loc[window, F.target_column(kpi, horizon)]

    fig, ax = plt.subplots(figsize=(12, 3.8))
    ax.plot(ts, truth, lw=1.4, color="black", label=f"{kpi} réel à t+{horizon} min")
    for name in ("persistance", "naif_saisonnier_24h", "xgboost"):
        if name not in forecasters:
            continue
        prediction = forecasters[name].predict(test, kpi, horizon)[window]
        ax.plot(ts, prediction, lw=0.9, alpha=0.85, label=name)
    ax.set_title(f"Prévision à {horizon} min — {kpi} — {cell_id} (12 h de test)")
    ax.set_xlabel("Horodatage (UTC)")
    ax.set_ylabel(f"{kpi} ({KPI_UNITS[kpi]})")
    ax.legend(fontsize=8, ncol=4)
    fig.tight_layout()
    fig.savefig(FIG_DIR / f"exemple_{kpi}_{horizon}min.png", bbox_inches="tight")
    plt.close(fig)


def fig_importance(model: F.XGBForecaster) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    for ax, kpi in zip(axes, ["latency", "throughput", "packet_loss"]):
        importance = model.feature_importance(kpi, FORECAST_HORIZONS[-1], top_k=12)
        ax.barh(importance["feature"][::-1], importance["importance"][::-1], color="#2c6fb5")
        ax.set_title(f"{kpi} à t+{FORECAST_HORIZONS[-1]} min", fontsize=9)
        ax.tick_params(axis="y", labelsize=7)
    fig.suptitle("Importance des features — XGBoost")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "importance_features.png", bbox_inches="tight")
    plt.close(fig)


# ==================================================================
# Entrée
# ==================================================================
def main() -> None:
    parser = argparse.ArgumentParser(description="Entraînement des modèles de prévision")
    parser.add_argument("--no-arima", action="store_true", help="Ignorer la baseline ARIMA")
    args = parser.parse_args()

    history, split = load_and_split()
    thresholds = loader.get_thresholds()

    forecasters = F.build_forecasters(history, with_arima=not args.no_arima)

    for name, model in forecasters.items():
        if not model.needs_fit:
            continue
        started = time.perf_counter()
        print(f"\nEntraînement {name}...")
        # Le segment de validation ne sert qu'à la sélection d'hyperparamètres
        # (objectif de XGBoost) — jamais à l'ajustement des arbres.
        model.fit(split.train, KPIS, FORECAST_HORIZONS, val=split.val)
        print(f"  terminé en {time.perf_counter() - started:.1f} s")

        if isinstance(model, F.XGBForecaster) and model.selection_log_:
            table = model.selection_table()
            table.to_csv(METRICS_DIR / "prevision_selection_objectif.csv", index=False)
            retained = (
                table[table["retenu"]]
                .groupby("objectif")
                .size()
                .rename("nb_modeles")
                .to_string()
            )
            print(f"  objectifs retenus par (KPI, horizon) :\n{retained}")

    # --- Périmètre 1 : origines communes (comparaison incluant ARIMA) ---
    arima = forecasters.get("arima")
    if arima is not None:
        mask = arima.evaluated_index(split.test)
        print(f"\nOrigines communes évaluées : {mask.sum():,} sur {len(split.test):,} points de test")
        common = evaluate(forecasters, split, mask, "origines_communes")
    else:
        common = pd.DataFrame()

    # --- Périmètre 2 : totalité du test (modèles rapides) ---
    fast = {k: v for k, v in forecasters.items() if k != "arima"}
    full = evaluate(fast, split, None, "test_complet")

    results = pd.concat([common, full], ignore_index=True)
    results.to_csv(METRICS_DIR / "prevision_resultats.csv", index=False)

    # --- Synthèse lisible ---
    print("\n=== Gain de MAE vs persistance (%, test complet, moyenne sur les KPI) ===")
    summary = (
        full.groupby(["modele", "horizon_min"])["gain_mae_vs_persistance_pct"]
        .mean()
        .unstack()
        .round(2)
    )
    print(summary.to_string())

    # --- Évaluation de l'état QoS prévu ---
    xgb = forecasters["xgboost"]
    qos_rows, qos_matrices = [], {}
    for horizon in FORECAST_HORIZONS:
        stats, matrix = evaluate_qos_state(xgb, split, thresholds, horizon)
        qos_rows.append(stats)
        qos_matrices[horizon] = matrix
    qos_frame = pd.DataFrame(qos_rows)
    qos_frame.to_csv(METRICS_DIR / "prevision_etat_qos.csv", index=False)
    for horizon, matrix in qos_matrices.items():
        matrix.to_csv(METRICS_DIR / f"prevision_confusion_etat_{horizon}min.csv")

    print("\n=== État QoS prévu vs réel (XGBoost) ===")
    print(qos_frame.to_string(index=False))

    # --- Figures ---
    reference = common if not common.empty else full
    fig_mae_by_horizon(reference)
    for kpi in ("latency", "throughput"):
        fig_forecast_example(forecasters, split, kpi, FORECAST_HORIZONS[-1])
    fig_importance(xgb)

    # --- Sauvegarde ---
    joblib.dump(xgb, MODELS_DIR / "forecast_xgboost.joblib")
    if arima is not None:
        joblib.dump(arima.orders_, MODELS_DIR / "forecast_arima_orders.joblib")

    best_per_horizon = (
        full[full["modele"] != "persistance"]
        .groupby(["horizon_min", "modele"])["gain_mae_vs_persistance_pct"]
        .mean()
        .reset_index()
        .sort_values(["horizon_min", "gain_mae_vs_persistance_pct"], ascending=[True, False])
        .groupby("horizon_min")
        .first()
    )
    (METRICS_DIR / "prevision_synthese.json").write_text(
        json.dumps(
            {
                "horizons": FORECAST_HORIZONS,
                "meilleur_modele_par_horizon": best_per_horizon.to_dict(orient="index"),
                "etat_qos_prevu": qos_rows,
                "arima_evalue": arima is not None,
                "origines_communes": int(mask.sum()) if arima is not None else None,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    print(f"\nRésultats : reports/metrics/prevision_resultats.csv")
    print(f"Figures   : {FIG_DIR}")
    print(f"Modèle    : {MODELS_DIR / 'forecast_xgboost.joblib'}")


if __name__ == "__main__":
    main()
