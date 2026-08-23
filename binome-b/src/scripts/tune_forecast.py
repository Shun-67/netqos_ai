"""
Optimisation du modèle de prévision retenu (XGBoost).

Le premier entraînement n'avait sélectionné que la fonction de perte, en laissant
la profondeur, le taux d'apprentissage et le nombre d'arbres à des valeurs
choisies a priori. Ce script explore ces hyperparamètres.

**Protocole, et pourquoi il diffère de celui du détecteur d'anomalies.** La
campagne sur l'Isolation Forest a montré qu'une PR-AUC calculée sur 300 points
positifs varie de ±0,03 selon la seule graine aléatoire, si bien qu'aucun écart
entre configurations n'y était interprétable. Ici la situation est inverse : la
MAE est calculée sur les 19 820 points du segment, tous informatifs. Un écart de
1 % y est donc mesurable, et une recherche a un sens.

**Coût maîtrisé.** Entraîner les 15 modèles (5 KPI × 3 horizons) prend environ
8 minutes ; une grille complète serait hors de portée. La recherche est donc menée
sur un couple représentatif — `latency` à 30 minutes, l'horizon le plus difficile
et le KPI le plus intéressant pour l'exploitation — puis la configuration gagnante
est vérifiée sur les 15 modèles. Ce compromis est explicite et reproductible.

Usage (depuis binome-b/) :
    python -m src.scripts.tune_forecast
"""

from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from src.config import FORECAST_HORIZONS, KPIS, METRICS_DIR, RANDOM_STATE
from src.data import loader
from src.evaluation import metrics as M
from src.features.preprocessing import prepare_features
from src.features.splits import temporal_split
from src.models import forecast as F

# KPI et horizon servant de sonde pour la recherche.
KPI_SONDE = "latency"
HORIZON_SONDE = max(FORECAST_HORIZONS)

# Grille : profondeur, taux d'apprentissage, nombre d'arbres, régularisation.
# La première ligne est la configuration actuelle, incluse comme référence.
GRILLE = [
    {"max_depth": 6, "learning_rate": 0.05, "n_estimators": 400, "min_child_weight": 1, "reg_lambda": 1.0},
    {"max_depth": 4, "learning_rate": 0.05, "n_estimators": 400, "min_child_weight": 1, "reg_lambda": 1.0},
    {"max_depth": 8, "learning_rate": 0.05, "n_estimators": 400, "min_child_weight": 1, "reg_lambda": 1.0},
    {"max_depth": 6, "learning_rate": 0.10, "n_estimators": 400, "min_child_weight": 1, "reg_lambda": 1.0},
    {"max_depth": 6, "learning_rate": 0.03, "n_estimators": 800, "min_child_weight": 1, "reg_lambda": 1.0},
    {"max_depth": 8, "learning_rate": 0.03, "n_estimators": 800, "min_child_weight": 5, "reg_lambda": 2.0},
    {"max_depth": 10, "learning_rate": 0.05, "n_estimators": 600, "min_child_weight": 10, "reg_lambda": 5.0},
    {"max_depth": 6, "learning_rate": 0.05, "n_estimators": 1200, "min_child_weight": 5, "reg_lambda": 2.0},
]


def _matrices(split, colonnes: list[str]):
    categorique = pd.Categorical(split.train["cell_id"])
    categories = list(categorique.categories)

    def design(df):
        codes = pd.Categorical(df["cell_id"], categories=categories).codes
        return np.column_stack([df[colonnes].to_numpy(), codes])

    return design(split.train), design(split.val), design(split.test)


def rechercher(split, colonnes: list[str]) -> pd.DataFrame:
    """Balaye la grille sur le couple sonde, classe par MAE de validation."""
    from xgboost import XGBRegressor

    X_train, X_val, _ = _matrices(split, colonnes)
    cible = F.target_column(KPI_SONDE, HORIZON_SONDE)
    y_train = split.train[cible].to_numpy()
    y_val = split.val[cible].to_numpy()
    ok_train, ok_val = np.isfinite(y_train), np.isfinite(y_val)

    lignes = []
    for numero, params in enumerate(GRILLE, start=1):
        debut = time.perf_counter()
        modele = XGBRegressor(
            objective="reg:absoluteerror",  # retenu par la sélection précédente
            random_state=RANDOM_STATE,
            n_jobs=-1,
            tree_method="hist",
            subsample=0.8,
            colsample_bytree=0.8,
            **params,
        )
        modele.fit(X_train[ok_train], y_train[ok_train])
        mae = float(np.mean(np.abs(modele.predict(X_val[ok_val]) - y_val[ok_val])))
        duree = time.perf_counter() - debut

        lignes.append({**params, "mae_validation": round(mae, 5), "duree_s": round(duree, 1)})
        print(
            f"  [{numero}/{len(GRILLE)}] profondeur={params['max_depth']:2d} "
            f"lr={params['learning_rate']:.2f} arbres={params['n_estimators']:4d} "
            f"mcw={params['min_child_weight']:2d} lambda={params['reg_lambda']:.1f} "
            f"-> MAE val {mae:.4f}  ({duree:.1f}s)"
        )

    return pd.DataFrame(lignes).sort_values("mae_validation")


def evaluer_sur_tous_les_modeles(split, params: dict, etiquette: str) -> list[dict]:
    """Entraîne les 15 modèles avec `params` et mesure la MAE de test."""
    modele = F.XGBForecaster(objective="reg:absoluteerror", **params)
    modele.fit(split.train, KPIS, FORECAST_HORIZONS)

    reference = F.PersistenceForecaster()
    lignes = []
    for kpi in KPIS:
        for horizon in FORECAST_HORIZONS:
            y_true = split.test[F.target_column(kpi, horizon)].to_numpy()
            stats = M.regression_metrics(y_true, modele.predict(split.test, kpi, horizon))
            base = M.regression_metrics(y_true, reference.predict(split.test, kpi, horizon))
            lignes.append(
                {
                    "configuration": etiquette,
                    "kpi": kpi,
                    "horizon_min": horizon,
                    "mae": round(stats["mae"], 5),
                    "gain_vs_persistance_pct": round(M.skill_score(stats, base, "mae"), 2),
                }
            )
    return lignes


def main() -> None:
    print(f"Source : {loader.source_description()}")
    history = loader.load_history()
    features = prepare_features(loader.load_features())
    dataset = F.build_targets(features, history, FORECAST_HORIZONS, KPIS)
    cibles = [F.target_column(k, h) for k in KPIS for h in FORECAST_HORIZONS]
    dataset = dataset.dropna(subset=cibles).reset_index(drop=True)

    split = temporal_split(dataset)
    split.assert_chronological()
    colonnes = F.forecast_features(dataset)

    print(
        f"Sonde : {KPI_SONDE} à t+{HORIZON_SONDE} min · {len(colonnes)} prédicteurs\n"
        f"Recherche sur {len(GRILLE)} configurations\n"
    )
    grille = rechercher(split, colonnes)
    grille.to_csv(METRICS_DIR / "optimisation_prevision_grille.csv", index=False)

    meilleure = grille.iloc[0].to_dict()
    actuelle = grille[
        (grille.max_depth == 6) & (grille.learning_rate == 0.05) & (grille.n_estimators == 400)
    ].iloc[0].to_dict()

    cles = ["max_depth", "learning_rate", "n_estimators", "min_child_weight", "reg_lambda"]
    params_meilleure = {k: (int(meilleure[k]) if k != "learning_rate" and k != "reg_lambda" else float(meilleure[k])) for k in cles}
    params_actuelle = {k: (int(actuelle[k]) if k != "learning_rate" and k != "reg_lambda" else float(actuelle[k])) for k in cles}

    gain_val = (actuelle["mae_validation"] - meilleure["mae_validation"]) / actuelle["mae_validation"] * 100
    print(f"\n{'='*70}")
    print(f"Actuelle  : MAE val {actuelle['mae_validation']:.4f}  {params_actuelle}")
    print(f"Meilleure : MAE val {meilleure['mae_validation']:.4f}  {params_meilleure}")
    print(f"Gain en validation sur la sonde : {gain_val:+.2f} %")
    print(f"{'='*70}\n")

    if params_meilleure == params_actuelle:
        print("La configuration actuelle est déjà la meilleure de la grille.")
        comparaison = pd.DataFrame(evaluer_sur_tous_les_modeles(split, params_actuelle, "actuelle"))
    else:
        print("Vérification sur les 15 modèles (5 KPI x 3 horizons)...")
        lignes = evaluer_sur_tous_les_modeles(split, params_actuelle, "actuelle")
        lignes += evaluer_sur_tous_les_modeles(split, params_meilleure, "optimisée")
        comparaison = pd.DataFrame(lignes)

    comparaison.to_csv(METRICS_DIR / "optimisation_prevision_comparaison.csv", index=False)

    print("\n=== Gain de MAE sur la persistance, par configuration (test) ===")
    pivot = comparaison.pivot_table(
        index="configuration", columns="horizon_min", values="gain_vs_persistance_pct"
    ).round(2)
    print(pivot.to_string())

    synthese = {
        "sonde": f"{KPI_SONDE}@{HORIZON_SONDE}min",
        "hyperparametres_actuels": params_actuelle,
        "hyperparametres_retenus": params_meilleure,
        "mae_validation_actuelle": actuelle["mae_validation"],
        "mae_validation_optimisee": meilleure["mae_validation"],
        "gain_validation_sonde_pct": round(gain_val, 2),
        "gain_moyen_test_par_configuration": pivot.mean(axis=1).round(2).to_dict(),
    }
    (METRICS_DIR / "optimisation_prevision_synthese.json").write_text(
        json.dumps(synthese, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nRésultats : reports/metrics/optimisation_prevision_*")


if __name__ == "__main__":
    main()
