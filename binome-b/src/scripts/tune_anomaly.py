"""
Optimisation du détecteur d'anomalies retenu (Isolation Forest).

Le premier entraînement n'avait réglé que l'autoencodeur — le modèle écarté —
en laissant l'Isolation Forest à ses valeurs par défaut. Ce script comble ce
manque en explorant deux leviers, et non un seul :

  1. **l'espace de features**, qui est probablement le levier dominant. L'EDA
     mesure des séparabilités normal/anomalie très inégales entre KPI :
     28 σ pour `packet_loss`, 5,8 σ pour `latency`, 4,3 σ pour `jitter`,
     1,1 σ pour `throughput`, mais seulement **0,2 σ pour `cell_load`**. Une
     feature qui ne sépare pas n'est pas neutre pour un détecteur fondé sur des
     distances : elle dilue le signal des autres dimensions.
  2. **les hyperparamètres** de l'Isolation Forest : nombre d'arbres, taille des
     sous-échantillons, part de features tirée par arbre.

Protocole : sélection sur la **PR-AUC de validation** (métrique indépendante du
seuil), évaluation de la configuration retenue sur le **test**, jamais l'inverse.
La configuration actuelle est incluse dans la grille comme point de référence,
afin que le gain soit mesuré et non supposé.

Usage (depuis binome-b/) :
    python -m src.scripts.tune_anomaly
    python -m src.scripts.tune_anomaly --contamination 0.02
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from src.config import KPIS, METRICS_DIR, RANDOM_STATE
from src.data import loader
from src.evaluation import metrics as M
from src.features.preprocessing import prepare_features
from src.features.splits import align_labels, temporal_split
from src.models import anomaly as A


# ==================================================================
# Espaces de features candidats
# ==================================================================
# Séparabilité normal/anomalie mesurée par l'EDA, en écarts-types du régime
# normal. Sert à construire les variantes « discriminantes ».
SEPARABILITE = {
    "packet_loss": 28.2,
    "latency": 5.8,
    "jitter": 4.3,
    "throughput": 1.1,
    "cell_load": 0.2,
}


def _colonnes_par_kpi(df: pd.DataFrame, kpis: list[str], suffixes: list[str]) -> list[str]:
    voulues = [f"{kpi}{suffixe}" for kpi in kpis for suffixe in suffixes]
    return [c for c in voulues if c in df.columns]


def espace_contrat(df: pd.DataFrame) -> list[str]:
    """Configuration actuelle : 4 vues sur les 5 KPI, plus la saisonnalité."""
    return A.anomaly_features(df)


def espace_sans_cell_load(df: pd.DataFrame) -> list[str]:
    """Retire `cell_load`, dont la séparabilité n'est que de 0,2 σ."""
    return [c for c in A.anomaly_features(df) if not c.startswith("cell_load")]


def espace_discriminants(df: pd.DataFrame) -> list[str]:
    """Ne garde que les KPI dont la séparabilité dépasse 4 σ."""
    kpis = [k for k in KPIS if SEPARABILITE[k] >= 4.0]
    cols = _colonnes_par_kpi(
        df, kpis, ["_mean_5m", "_std_15m", "_ratio_to_hour", "_trend_5m_30m"]
    )
    return cols + [c for c in ("hour_sin", "hour_cos") if c in df.columns]


def espace_relatif(df: pd.DataFrame) -> list[str]:
    """Uniquement des grandeurs relatives : écart à la normale horaire et tendance.

    Hypothèse : un détecteur raisonnant en écart plutôt qu'en valeur absolue est
    moins sensible aux différences de régime entre cellules et aux dérives lentes.
    """
    cols = _colonnes_par_kpi(df, KPIS, ["_ratio_to_hour", "_trend_5m_30m", "_std_15m"])
    return cols + [c for c in ("hour_sin", "hour_cos") if c in df.columns]


def espace_riche(df: pd.DataFrame) -> list[str]:
    """Ajoute les fenêtres longues et les lags livrés par le Binôme A."""
    cols = A.anomaly_features(df)
    supplement = _colonnes_par_kpi(
        df, KPIS, ["_mean_15m", "_mean_30m", "_lag_1", "_lag_5", "_hour_mean"]
    )
    return cols + [c for c in supplement if c not in cols]


ESPACES = {
    "contrat_actuel": espace_contrat,
    "sans_cell_load": espace_sans_cell_load,
    "discriminants": espace_discriminants,
    "relatif": espace_relatif,
    "riche": espace_riche,
}

# ==================================================================
# Grille d'hyperparamètres
# ==================================================================
# `contamination` n'y figure pas : elle n'influence que le seuil interne de
# `predict`, pas `score_samples`, donc pas le classement des points ni la PR-AUC.
GRILLE_IF = [
    {"n_estimators": 300, "max_samples": "auto", "max_features": 1.0},  # configuration actuelle
    {"n_estimators": 300, "max_samples": 256, "max_features": 1.0},
    {"n_estimators": 600, "max_samples": 1024, "max_features": 1.0},
    {"n_estimators": 600, "max_samples": 4096, "max_features": 1.0},
    {"n_estimators": 600, "max_samples": 1024, "max_features": 0.6},
    {"n_estimators": 1000, "max_samples": 2048, "max_features": 0.8},
]


class IsolationForestReglable(A.IsolationForestDetector):
    """Isolation Forest exposant max_samples et max_features à la recherche."""

    def __init__(self, cols, n_estimators=300, max_samples="auto", max_features=1.0):
        from sklearn.ensemble import IsolationForest

        self.cols = cols
        self.scaler = A.PerCellScaler(cols)
        self.model = IsolationForest(
            n_estimators=n_estimators,
            max_samples=max_samples,
            max_features=max_features,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )


# ==================================================================
# Recherche
# ==================================================================
def rechercher(split, y_val: np.ndarray) -> pd.DataFrame:
    """Balaye espaces x hyperparamètres, classe par PR-AUC de validation."""
    lignes = []
    total = len(ESPACES) * len(GRILLE_IF)
    numero = 0

    for nom_espace, fabrique in ESPACES.items():
        cols = fabrique(split.train)
        for params in GRILLE_IF:
            numero += 1
            debut = time.perf_counter()
            detecteur = IsolationForestReglable(cols, **params).fit(split.train)
            scores_val = detecteur.score(split.val)
            pr_auc = float(M.average_precision_score(y_val, scores_val))
            duree = time.perf_counter() - debut

            lignes.append(
                {
                    "espace": nom_espace,
                    "n_features": len(cols),
                    "n_estimators": params["n_estimators"],
                    "max_samples": str(params["max_samples"]),
                    "max_features": params["max_features"],
                    "pr_auc_validation": round(pr_auc, 4),
                    "duree_s": round(duree, 1),
                }
            )
            print(
                f"  [{numero:2d}/{total}] {nom_espace:16s} "
                f"({len(cols):2d} feat) n={params['n_estimators']:4d} "
                f"ms={str(params['max_samples']):5s} mf={params['max_features']} "
                f"-> PR-AUC val {pr_auc:.4f}  ({duree:.1f}s)"
            )

    return pd.DataFrame(lignes).sort_values("pr_auc_validation", ascending=False)


def evaluer_sur_test(
    split, y_val: np.ndarray, y_test: np.ndarray, cols: list[str], params: dict,
    contamination: float, etiquette: str,
) -> list[dict]:
    """Évalue une configuration sur le test, aux deux points de fonctionnement."""
    detecteur = IsolationForestReglable(cols, **params).fit(split.train)
    scores_val = detecteur.score(split.val)
    scores_test = detecteur.score(split.test)

    seuil_exploitation = detecteur.default_threshold(split.train, contamination)
    seuil_f1 = M.best_threshold(y_val, scores_val, criterion="f1")

    resultats = []
    for nom_point, seuil in (
        ("exploitation (non supervisé)", seuil_exploitation),
        ("F1-optimal (choisi sur validation)", seuil_f1),
    ):
        y_pred = scores_test >= seuil
        point = M.classification_metrics(y_test, y_pred, scores_test)

        cadre = split.test[["ts", "cell_id"]].copy()
        cadre["is_anomaly"] = y_test
        cadre["is_anomaly_pred"] = y_pred
        episode = M.episode_metrics_by_cell(cadre)
        episode.pop("detail_par_cellule")

        resultats.append(
            {
                "configuration": etiquette,
                "point_de_fonctionnement": nom_point,
                "n_features": len(cols),
                **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in point.items()},
                **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in episode.items()},
            }
        )
    return resultats


# ==================================================================
# Diagnostics : d'où vient l'écart entre configurations ?
# ==================================================================
def mesurer_variance_graines(split, y_test: np.ndarray, cols: list[str]) -> pd.DataFrame:
    """Mesure la dispersion de la PR-AUC à configuration constante.

    Sans cette mesure, impossible de savoir si un écart entre deux
    configurations est un gain ou du bruit. C'est le contrôle qui a invalidé
    l'ensemble de la recherche d'hyperparamètres : l'étendue due à la seule
    graine aléatoire s'est révélée trois fois supérieure au « gain » observé.
    """
    from sklearn.ensemble import IsolationForest

    lignes = []
    for n_arbres in (300, 1000, 2000):
        scores = []
        for graine in range(6):
            detecteur = A.IsolationForestDetector(cols)
            detecteur.model = IsolationForest(
                n_estimators=n_arbres, random_state=graine, n_jobs=-1
            )
            detecteur.fit(split.train)
            scores.append(
                float(M.average_precision_score(y_test, detecteur.score(split.test)))
            )
        valeurs = np.array(scores)
        lignes.append(
            {
                "n_estimators": n_arbres,
                "pr_auc_moyenne": round(float(valeurs.mean()), 4),
                "ecart_type": round(float(valeurs.std()), 4),
                "etendue": round(float(valeurs.max() - valeurs.min()), 4),
                "n_graines": len(valeurs),
            }
        )
        print(
            f"  {n_arbres:5d} arbres : PR-AUC test {valeurs.mean():.4f} "
            f"± {valeurs.std():.4f} (étendue {valeurs.max() - valeurs.min():.4f})"
        )
    return pd.DataFrame(lignes)


def borne_oracle_supervisee(split, y_train, y_val, y_test, cols: list[str]) -> dict:
    """Borne supérieure atteignable si les étiquettes pouvaient servir à entraîner.

    ATTENTION — ce modèle n'est **ni déployé, ni sauvegardé, ni utilisé par le
    dashboard**. Le contrat d'interface réserve `is_anomaly` à l'évaluation, et
    le §2.2 de la fiche impose une approche non supervisée. L'expérience sert
    uniquement à répondre à une question de méthode : quelle part de l'erreur
    résiduelle vient de la contrainte non supervisée, et quelle part de
    l'ambiguïté intrinsèque des données ?

    C'est la seule façon de justifier chiffres en main qu'un F1 de 0,63 n'est pas
    un défaut de réglage mais le prix d'une contrainte imposée par l'énoncé — et,
    en exploitation réelle, par l'absence d'étiquettes sur un réseau vivant.
    """
    from xgboost import XGBClassifier

    scaler = A.PerCellScaler(cols).fit(split.train)
    X_train, X_val, X_test = (
        scaler.transform(split.train),
        scaler.transform(split.val),
        scaler.transform(split.test),
    )

    classifieur = XGBClassifier(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.05,
        scale_pos_weight=float((~y_train).sum() / max(y_train.sum(), 1)),
        objective="binary:logistic",
        eval_metric="aucpr",
        tree_method="hist",
        n_jobs=-1,
        random_state=RANDOM_STATE,
    )
    classifieur.fit(X_train, y_train)

    proba_val = classifieur.predict_proba(X_val)[:, 1]
    proba_test = classifieur.predict_proba(X_test)[:, 1]
    seuil = M.best_threshold(y_val, proba_val, criterion="f1")
    point = M.classification_metrics(y_test, proba_test >= seuil, proba_test)

    return {
        "pr_auc": round(point["pr_auc"], 4),
        "precision": round(point["precision"], 4),
        "rappel": round(point["rappel"], 4),
        "f1": round(point["f1"], 4),
        "avertissement": (
            "Modèle supervisé entraîné sur is_anomaly. Non déployé, non sauvegardé, "
            "non utilisé par le dashboard. Interdit par le contrat v1.1 : sert "
            "uniquement de borne supérieure pour l'analyse."
        ),
    }


# ==================================================================
# Entrée
# ==================================================================
def main() -> None:
    parser = argparse.ArgumentParser(description="Optimisation de l'Isolation Forest")
    parser.add_argument("--contamination", type=float, default=0.02)
    args = parser.parse_args()

    print(f"Source : {loader.source_description()}")
    features = prepare_features(loader.load_features())
    split = temporal_split(features)
    split.assert_chronological()

    labels = loader.load_labels()
    y_val = align_labels(split.val, labels).to_numpy()
    y_test = align_labels(split.test, labels).to_numpy()
    print(
        f"Prévalence — val {y_val.mean()*100:.2f} % · test {y_test.mean()*100:.2f} %\n"
        f"Recherche : {len(ESPACES)} espaces x {len(GRILLE_IF)} configurations\n"
    )

    grille = rechercher(split, y_val)
    grille.to_csv(METRICS_DIR / "optimisation_anomalie_grille.csv", index=False)

    meilleure = grille.iloc[0]
    actuelle = grille[
        (grille.espace == "contrat_actuel")
        & (grille.n_estimators == 300)
        & (grille.max_samples == "auto")
        & (grille.max_features == 1.0)
    ].iloc[0]

    print(f"\n{'='*70}")
    print(f"Configuration actuelle : {actuelle.espace} — PR-AUC val {actuelle.pr_auc_validation}")
    print(f"Meilleure trouvée      : {meilleure.espace} — PR-AUC val {meilleure.pr_auc_validation}")
    gain = (meilleure.pr_auc_validation - actuelle.pr_auc_validation) / actuelle.pr_auc_validation * 100
    print(f"Gain en validation     : {gain:+.1f} %")
    print(f"{'='*70}\n")

    # Évaluation sur le test des deux configurations, pour mesurer le gain réel.
    params_meilleure = {
        "n_estimators": int(meilleure.n_estimators),
        "max_samples": "auto" if meilleure.max_samples == "auto" else int(meilleure.max_samples),
        "max_features": float(meilleure.max_features),
    }
    params_actuelle = {"n_estimators": 300, "max_samples": "auto", "max_features": 1.0}

    lignes = []
    lignes += evaluer_sur_test(
        split, y_val, y_test, ESPACES["contrat_actuel"](split.train), params_actuelle,
        args.contamination, "actuelle",
    )
    lignes += evaluer_sur_test(
        split, y_val, y_test, ESPACES[meilleure.espace](split.train), params_meilleure,
        args.contamination, "optimisée",
    )

    comparaison = pd.DataFrame(lignes)
    comparaison.to_csv(METRICS_DIR / "optimisation_anomalie_comparaison.csv", index=False)

    print("=== Comparaison sur le segment de TEST ===")
    colonnes = [
        "configuration", "point_de_fonctionnement", "precision", "rappel", "f1",
        "pr_auc", "taux_alerte_pct", "rappel_episode", "fausses_alertes_par_heure",
    ]
    print(comparaison[colonnes].to_string(index=False))

    # --- Diagnostics : le gain apparent est-il réel ? ---
    print("\n=== Dispersion de la PR-AUC à configuration constante ===")
    variance = mesurer_variance_graines(split, y_test, ESPACES["contrat_actuel"](split.train))
    variance.to_csv(METRICS_DIR / "optimisation_anomalie_variance.csv", index=False)

    etendue_bruit = float(variance.loc[variance.n_estimators == 300, "etendue"].iloc[0])
    ecart_configs = float(meilleure.pr_auc_validation - actuelle.pr_auc_validation)
    print(
        f"\n  écart entre configurations (validation) : {ecart_configs:.4f}\n"
        f"  étendue due à la seule graine (300 arbres) : {etendue_bruit:.4f}\n"
        f"  -> le « gain » est {'DU BRUIT' if etendue_bruit > ecart_configs else 'significatif'}"
    )

    print("\n=== Borne supérieure supervisée (non déployable) ===")
    y_train = align_labels(split.train, labels).to_numpy()
    oracle = borne_oracle_supervisee(
        split, y_train, y_val, y_test, ESPACES["contrat_actuel"](split.train)
    )
    print(
        f"  PR-AUC {oracle['pr_auc']} · précision {oracle['precision']*100:.1f} % · "
        f"rappel {oracle['rappel']*100:.1f} % · F1 {oracle['f1']}"
    )

    synthese = {
        "espace_retenu": meilleure.espace,
        "n_features_retenu": int(meilleure.n_features),
        "hyperparametres_retenus": params_meilleure,
        "pr_auc_validation_actuelle": float(actuelle.pr_auc_validation),
        "pr_auc_validation_optimisee": float(meilleure.pr_auc_validation),
        "gain_validation_pct": round(float(gain), 2),
        "ecart_entre_configurations": round(ecart_configs, 4),
        "etendue_due_a_la_graine_300_arbres": etendue_bruit,
        "gain_est_du_bruit": bool(etendue_bruit > ecart_configs),
        "variance_par_nombre_d_arbres": variance.to_dict(orient="records"),
        "borne_oracle_supervisee": oracle,
    }
    (METRICS_DIR / "optimisation_anomalie_synthese.json").write_text(
        json.dumps(synthese, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nRésultats : reports/metrics/optimisation_anomalie_*")


if __name__ == "__main__":
    main()
