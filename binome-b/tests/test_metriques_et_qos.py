"""
Tests des métriques d'évaluation et de la classification de l'état QoS.

Les métriques par épisode et la règle du pire KPI sont les deux endroits où une
erreur passerait inaperçue : elles produiraient des nombres plausibles mais faux,
et ces nombres figurent tels quels dans le rapport d'évaluation.
"""

import numpy as np
import pandas as pd
import pytest

from src.evaluation import metrics as M
from src.models import qos_state

SEUILS = {
    "latency": {"unit": "ms", "good_max": 20, "degraded_max": 50},
    "throughput": {"unit": "Mbit/s", "good_min": 107, "degraded_min": 77},
}


# ==================================================================
# Découpage en épisodes
# ==================================================================
def test_episodes_identifie_les_intervalles_contigus():
    masque = np.array([0, 1, 1, 0, 0, 1, 0], dtype=bool)
    assert M._episodes(masque) == [(1, 2), (5, 5)]


def test_episodes_gere_les_bords():
    assert M._episodes(np.array([1, 1, 0, 1], dtype=bool)) == [(0, 1), (3, 3)]
    assert M._episodes(np.array([1, 1, 1], dtype=bool)) == [(0, 2)]
    assert M._episodes(np.zeros(5, dtype=bool)) == []


# ==================================================================
# Métriques par épisode
# ==================================================================
def test_rappel_par_episode_compte_une_detection_partielle():
    """Un seul point détecté suffit à considérer l'épisode signalé.

    C'est tout l'intérêt de cette métrique : un détecteur qui signale 1 minute
    sur 5 d'une panne a un rappel ponctuel de 20 %, mais l'exploitant a bien été
    averti.
    """
    verite = np.array([0, 1, 1, 1, 1, 0], dtype=bool)
    prediction = np.array([0, 0, 0, 1, 0, 0], dtype=bool)
    resultat = M.episode_metrics(verite, prediction)
    assert resultat["episodes_reels"] == 1
    assert resultat["episodes_detectes"] == 1
    assert resultat["rappel_episode"] == 1.0


def test_delai_de_detection_compte_depuis_le_debut_de_l_episode():
    verite = np.array([0, 1, 1, 1, 1, 0], dtype=bool)
    prediction = np.array([0, 0, 0, 1, 0, 0], dtype=bool)  # 3e minute de l'épisode
    resultat = M.episode_metrics(verite, prediction, minutes_per_point=1)
    assert resultat["delai_median_min"] == 2.0


def test_episode_manque_n_est_pas_compte_comme_detecte():
    verite = np.array([0, 1, 1, 0], dtype=bool)
    prediction = np.zeros(4, dtype=bool)
    resultat = M.episode_metrics(verite, prediction)
    assert resultat["episodes_detectes"] == 0
    assert resultat["rappel_episode"] == 0.0
    assert np.isnan(resultat["delai_median_min"])


def test_fausses_alertes_comptent_les_episodes_hors_verite():
    verite = np.array([0, 0, 0, 0, 1, 1], dtype=bool)
    prediction = np.array([1, 1, 0, 1, 0, 0], dtype=bool)  # 2 épisodes, aucun réel
    resultat = M.episode_metrics(verite, prediction)
    assert resultat["episodes_fausse_alerte"] == 2


def test_metriques_par_cellule_ne_fusionnent_pas_les_episodes():
    """Le découpage doit être fait cellule par cellule.

    En concaténant les cellules, un épisode finissant à la dernière minute de c1
    et un autre commençant à la première de c2 seraient comptés comme un seul.
    """
    df = pd.DataFrame(
        {
            "ts": list(pd.date_range("2026-01-01", periods=2, freq="1min", tz="UTC")) * 2,
            "cell_id": ["c1", "c1", "c2", "c2"],
            "is_anomaly": [False, True, True, False],
            "is_anomaly_pred": [False, True, True, False],
        }
    )
    resultat = M.episode_metrics_by_cell(df)
    assert resultat["episodes_reels"] == 2  # et non 1
    assert resultat["rappel_episode"] == 1.0


# ==================================================================
# Métriques de classification et de régression
# ==================================================================
def test_metriques_de_classification_sur_un_cas_calculable():
    verite = np.array([0, 0, 1, 1], dtype=bool)
    prediction = np.array([0, 1, 1, 0], dtype=bool)
    r = M.classification_metrics(verite, prediction)
    assert (r["vp"], r["fp"], r["vn"], r["fn"]) == (1, 1, 1, 1)
    assert r["precision"] == pytest.approx(0.5)
    assert r["rappel"] == pytest.approx(0.5)
    assert r["f1"] == pytest.approx(0.5)


def test_metriques_de_regression_sur_un_cas_calculable():
    reel = np.array([10.0, 20.0, 30.0])
    prevu = np.array([12.0, 18.0, 30.0])
    r = M.regression_metrics(reel, prevu)
    assert r["mae"] == pytest.approx((2 + 2 + 0) / 3)
    assert r["rmse"] == pytest.approx(np.sqrt((4 + 4 + 0) / 3))
    assert r["biais"] == pytest.approx(0.0)


def test_smape_reste_borne_quand_le_reel_approche_zero():
    """Le MAPE explose sur packet_loss proche de 0 ; le sMAPE reste borné.

    C'est la raison pour laquelle le rapport reporte les deux.
    """
    r = M.regression_metrics(np.array([1e-9]), np.array([1.0]))
    assert r["mape"] > 1e6
    assert r["smape"] <= 200.0


def test_skill_score_positif_quand_le_modele_bat_la_reference():
    assert M.skill_score({"mae": 8.0}, {"mae": 10.0}) == pytest.approx(20.0)
    assert M.skill_score({"mae": 12.0}, {"mae": 10.0}) == pytest.approx(-20.0)


# ==================================================================
# État QoS
# ==================================================================
@pytest.mark.parametrize(
    "valeur,attendu",
    [(10, "bon"), (20, "bon"), (21, "dégradé"), (50, "dégradé"), (51, "critique")],
)
def test_classification_d_un_kpi_a_borne_haute(valeur, attendu):
    assert qos_state.classify_kpi(valeur, SEUILS["latency"]) == attendu


@pytest.mark.parametrize(
    "valeur,attendu",
    [(150, "bon"), (107, "bon"), (106, "dégradé"), (77, "dégradé"), (76, "critique")],
)
def test_classification_d_un_kpi_a_borne_basse(valeur, attendu):
    """throughput est le seul KPI où une valeur basse est mauvaise."""
    assert qos_state.classify_kpi(valeur, SEUILS["throughput"]) == attendu


def test_valeur_manquante_ne_declenche_pas_d_alerte():
    assert qos_state.classify_kpi(np.nan, SEUILS["latency"]) == "bon"


def test_regle_du_pire_kpi():
    """Un seul KPI critique suffit à rendre la cellule critique."""
    df = pd.DataFrame({"latency": [10.0, 10.0], "throughput": [150.0, 50.0]})
    resultat = qos_state.classify_frame(df, SEUILS)
    assert list(resultat["qos_state"].astype(str)) == ["bon", "critique"]


def test_classification_vectorisee_coherente_avec_la_version_ligne_par_ligne():
    rng = np.random.default_rng(0)
    df = pd.DataFrame(
        {"latency": rng.uniform(5, 80, 200), "throughput": rng.uniform(40, 160, 200)}
    )
    vectorise = qos_state.classify_frame(df, SEUILS)["qos_state"].astype(str).tolist()
    ligne_par_ligne = [qos_state.classify_row(row, SEUILS) for _, row in df.iterrows()]
    assert vectorise == ligne_par_ligne


def test_suffixe_permet_de_classer_les_kpi_prevus():
    """Le même code doit classer les prévisions, d'où le paramètre `suffix`."""
    df = pd.DataFrame({"latency_pred_15m": [60.0], "throughput_pred_15m": [150.0]})
    resultat = qos_state.classify_frame(df, SEUILS, suffix="_pred_15m")
    assert str(resultat["qos_state"].iloc[0]) == "critique"


def test_cause_dominante_nomme_le_kpi_responsable():
    ligne = pd.Series({"latency": 60.0, "throughput": 150.0})
    assert "latency" in qos_state.dominant_cause(ligne, SEUILS)


def test_cause_dominante_vaut_aucun_si_tout_est_bon():
    ligne = pd.Series({"latency": 10.0, "throughput": 150.0})
    assert qos_state.dominant_cause(ligne, SEUILS) == "aucun"
