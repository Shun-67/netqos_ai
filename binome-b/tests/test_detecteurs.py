"""
Tests de la convention de score des détecteurs d'anomalies.

Tous les détecteurs partagent une règle : **plus le score est élevé, plus le
point est atypique**. Cette convention n'est pas naturelle pour tous les
algorithmes — `IsolationForest.score_samples` de scikit-learn renvoie l'inverse,
et le code le corrige par un changement de signe. Une erreur sur ce signe
inverserait silencieusement tout le système : les points les plus normaux
seraient signalés comme anomalies, avec des métriques d'apparence plausible.
"""

import numpy as np
import pandas as pd
import pytest

from src.models import anomaly as A

SEUILS = {
    "latency": {"unit": "ms", "good_max": 20, "degraded_max": 50},
    "throughput": {"unit": "Mbit/s", "good_min": 107, "degraded_min": 77},
}


def _jeu_avec_anomalies(n_normal: int = 400, n_anomalies: int = 8) -> pd.DataFrame:
    """Nuage normal serré, plus quelques points très éloignés."""
    rng = np.random.default_rng(0)
    colonnes = ["latency_mean_5m", "latency_std_15m", "throughput_mean_5m"]

    normal = pd.DataFrame(rng.normal(0, 1, size=(n_normal, len(colonnes))), columns=colonnes)
    anomalies = pd.DataFrame(
        rng.normal(30, 1, size=(n_anomalies, len(colonnes))), columns=colonnes
    )
    df = pd.concat([normal, anomalies], ignore_index=True)
    df["ts"] = pd.date_range("2026-01-01", periods=len(df), freq="1min", tz="UTC")
    df["cell_id"] = "c1"
    df["est_anormal"] = [False] * n_normal + [True] * n_anomalies
    return df


COLONNES = ["latency_mean_5m", "latency_std_15m", "throughput_mean_5m"]


@pytest.mark.parametrize(
    "fabrique",
    [
        lambda cols: A.IsolationForestDetector(cols, n_estimators=60),
        lambda cols: A.DBSCANDetector(cols, min_samples=5),
        lambda cols: A.AutoencoderDetector(cols, hidden=(4, 2, 4), max_iter=60),
    ],
    ids=["isolation_forest", "dbscan", "autoencodeur"],
)
def test_le_score_croit_avec_l_atypicite(fabrique):
    """Les points aberrants doivent obtenir des scores plus élevés."""
    df = _jeu_avec_anomalies()
    detecteur = fabrique(COLONNES).fit(df)
    scores = detecteur.score(df)

    score_moyen_normal = scores[~df["est_anormal"].to_numpy()].mean()
    score_moyen_anormal = scores[df["est_anormal"].to_numpy()].mean()
    assert score_moyen_anormal > score_moyen_normal


def test_le_seuil_par_defaut_respecte_la_contamination_visee():
    """Le seuil non supervisé doit alerter sur environ la part demandée."""
    df = _jeu_avec_anomalies()
    detecteur = A.IsolationForestDetector(COLONNES, n_estimators=60).fit(df)
    seuil = detecteur.default_threshold(df, contamination=0.05)
    part_alertee = (detecteur.score(df) >= seuil).mean()
    assert 0.02 <= part_alertee <= 0.10


def test_normalisation_par_cellule_neutralise_les_regimes_differents():
    """Deux cellules de niveaux très différents ne doivent pas être discriminées.

    Sans normalisation par cellule, un modèle global signalerait en permanence la
    cellule au débit le plus faible — les cellules du générateur ayant des
    débits de base allant de 80 à 150 Mbit/s.
    """
    rng = np.random.default_rng(1)
    lignes = []
    for cellule, niveau in (("c1", 0.0), ("c2", 500.0)):
        bloc = pd.DataFrame(
            rng.normal(niveau, 1, size=(300, len(COLONNES))), columns=COLONNES
        )
        bloc["cell_id"] = cellule
        lignes.append(bloc)
    df = pd.concat(lignes, ignore_index=True)
    df["ts"] = pd.date_range("2026-01-01", periods=len(df), freq="1min", tz="UTC")

    detecteur = A.IsolationForestDetector(COLONNES, n_estimators=80).fit(df)
    scores = detecteur.score(df)
    seuil = detecteur.default_threshold(df, contamination=0.05)

    taux_c1 = (scores[(df.cell_id == "c1").to_numpy()] >= seuil).mean()
    taux_c2 = (scores[(df.cell_id == "c2").to_numpy()] >= seuil).mean()
    # Les deux cellules doivent être alertées dans des proportions comparables.
    assert abs(taux_c1 - taux_c2) < 0.10


def test_detecteur_par_seuils_ne_signale_que_le_critique():
    """La baseline explicable doit alerter exactement sur l'état « critique »."""
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC"),
            "cell_id": "c1",
            "latency_mean_5m": [10.0, 30.0, 60.0],       # bon, dégradé, critique
            "throughput_mean_5m": [150.0, 150.0, 150.0],
        }
    )
    detecteur = A.ThresholdDetector(SEUILS).fit(df)
    seuil = detecteur.default_threshold(df, contamination=0.02)
    assert detecteur.predict(df, seuil).tolist() == [False, False, True]


def test_espace_de_features_ecarte_les_colonnes_absentes():
    """`anomaly_features` ne doit retenir que les colonnes réellement présentes."""
    df = pd.DataFrame(
        {"latency_mean_5m": [1.0], "hour_sin": [0.0], "colonne_hors_sujet": [1.0]}
    )
    retenues = A.anomaly_features(df)
    assert "latency_mean_5m" in retenues
    assert "hour_sin" in retenues
    assert "colonne_hors_sujet" not in retenues
