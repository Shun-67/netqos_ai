"""
Tests des garde-fous anti-fuite de données.

Ces deux garde-fous ont chacun attrapé un vrai défaut pendant le projet :

  - `LeakageError` protège contre l'entrée de `is_anomaly` — la vérité terrain —
    dans une matrice de features, ce que le contrat d'interface interdit ;
  - `LabelAlignmentError` a révélé que `GET /eval/labels` sert des horodatages
    non rééchantillonnés : la jointure n'appariait aucune ligne, la prévalence
    tombait à 0 % et toutes les métriques de détection s'effondraient **sans
    qu'aucune erreur ne soit levée**.

Le second cas est la raison d'être de ces tests : une panne silencieuse
n'invalide pas seulement un chiffre, elle invalide une campagne d'évaluation
entière. Ces vérifications interdisent qu'une modification future les défasse.
"""

import pandas as pd
import pytest

from src.features.preprocessing import (
    FORBIDDEN_FEATURES,
    LeakageError,
    add_cyclic_features,
    assert_no_leakage,
    feature_columns,
)
from src.features.splits import LabelAlignmentError, align_labels


def _horodatages(n: int, debut: str = "2026-01-01 00:00:00", pas_min: int = 1):
    return pd.date_range(debut, periods=n, freq=f"{pas_min}min", tz="UTC")


# ==================================================================
# Fuite de la vérité terrain
# ==================================================================
@pytest.mark.parametrize("colonne", sorted(FORBIDDEN_FEATURES - {"ts", "cell_id"}))
def test_assert_no_leakage_refuse_chaque_colonne_interdite(colonne):
    """Aucune colonne de la liste noire ne doit pouvoir servir de feature."""
    df = pd.DataFrame({colonne: [0, 1], "latency_mean_5m": [10.0, 11.0]})
    with pytest.raises(LeakageError, match=colonne):
        assert_no_leakage(df, [colonne, "latency_mean_5m"])


def test_assert_no_leakage_accepte_des_features_legitimes():
    df = pd.DataFrame({"latency_mean_5m": [10.0], "jitter_std_15m": [1.0]})
    assert_no_leakage(df, ["latency_mean_5m", "jitter_std_15m"])  # ne lève pas


def test_feature_columns_ecarte_la_verite_terrain():
    """`feature_columns` doit filtrer is_anomaly même si elle est présente.

    Cas réel : l'EDA joint les étiquettes à l'historique pour l'analyse
    descriptive. Si ce DataFrame était passé tel quel à un modèle, la vérité
    terrain deviendrait une feature parfaitement prédictive.
    """
    df = pd.DataFrame(
        {
            "ts": _horodatages(2),
            "cell_id": ["c1", "c1"],
            "latency_mean_5m": [10.0, 11.0],
            "is_anomaly": [False, True],
            "is_missing": [False, False],
        }
    )
    cols = feature_columns(df)
    assert cols == ["latency_mean_5m"]
    assert "is_anomaly" not in cols
    assert "is_missing" not in cols


def test_feature_columns_leve_si_aucune_feature_exploitable():
    df = pd.DataFrame({"ts": _horodatages(1), "cell_id": ["c1"]})
    with pytest.raises(LeakageError):
        feature_columns(df)


# ==================================================================
# Alignement des étiquettes
# ==================================================================
def test_align_labels_apparie_des_horodatages_identiques():
    features = pd.DataFrame({"ts": _horodatages(4), "cell_id": ["c1"] * 4})
    labels = features.assign(is_anomaly=[False, True, False, True])
    resultat = align_labels(features, labels)
    assert resultat.tolist() == [False, True, False, True]


def test_align_labels_refuse_un_decalage_de_secondes():
    """Le défaut réel de /eval/labels : des `ts` à la seconde près.

    L'endpoint sert `20:21:41` là où /features sert `20:21:00`. Sans garde-fou,
    la jointure retourne des NaN silencieusement convertis en False.
    """
    features = pd.DataFrame({"ts": _horodatages(5), "cell_id": ["c1"] * 5})
    labels = pd.DataFrame(
        {
            "ts": _horodatages(5) + pd.Timedelta(seconds=41),
            "cell_id": ["c1"] * 5,
            "is_anomaly": [True] * 5,
        }
    )
    with pytest.raises(LabelAlignmentError, match="étiquette"):
        align_labels(features, labels)


def test_align_labels_refuse_des_etiquettes_vides():
    features = pd.DataFrame({"ts": _horodatages(3), "cell_id": ["c1"] * 3})
    with pytest.raises(LabelAlignmentError, match="vide"):
        align_labels(features, pd.DataFrame())


def test_align_labels_tolere_un_appariement_partiel_suffisant():
    """Un trou minoritaire dans les étiquettes reste acceptable.

    Le seuil de 50 % distingue une lacune ponctuelle d'un désalignement
    systématique : la première est normale, la seconde invalide l'évaluation.
    """
    features = pd.DataFrame({"ts": _horodatages(10), "cell_id": ["c1"] * 10})
    labels = features.iloc[:8].assign(is_anomaly=[True] * 8)
    resultat = align_labels(features, labels)
    assert resultat.sum() == 8
    # Les lignes sans étiquette sont considérées normales, jamais anormales.
    assert resultat.iloc[8:].tolist() == [False, False]


def test_align_labels_n_apparie_pas_deux_cellules_differentes():
    """La jointure porte sur (ts, cell_id) : une cellule ne prête pas ses labels."""
    features = pd.DataFrame({"ts": _horodatages(4), "cell_id": ["c1"] * 4})
    labels = pd.DataFrame(
        {"ts": _horodatages(4), "cell_id": ["c2"] * 4, "is_anomaly": [True] * 4}
    )
    with pytest.raises(LabelAlignmentError):
        align_labels(features, labels)


# ==================================================================
# Encodage cyclique
# ==================================================================
def test_encodage_cyclique_est_continu_entre_23h_et_0h():
    """Raison d'être de l'encodage sin/cos : 23 h et 0 h doivent être voisines.

    Avec l'entier brut `hour_of_day`, la distance entre 23 et 0 vaut 23 — le
    modèle croirait ces deux instants maximalement éloignés.
    """
    df = pd.DataFrame(
        {
            "ts": pd.to_datetime(
                ["2026-01-01 23:00:00", "2026-01-02 00:00:00", "2026-01-02 12:00:00"],
                utc=True,
            )
        }
    )
    encode = add_cyclic_features(df)

    def distance(i, j):
        return (
            (encode.hour_sin[i] - encode.hour_sin[j]) ** 2
            + (encode.hour_cos[i] - encode.hour_cos[j]) ** 2
        ) ** 0.5

    assert distance(0, 1) < distance(0, 2)


def test_encodage_cyclique_reste_borne():
    df = pd.DataFrame({"ts": _horodatages(48, pas_min=60)})
    encode = add_cyclic_features(df)
    for colonne in ("hour_sin", "hour_cos", "dow_sin", "dow_cos"):
        assert encode[colonne].between(-1.0, 1.0).all()


def test_encodage_cyclique_reutilise_les_colonnes_du_binome_a():
    """Si hour_of_day / day_of_week sont fournis, ils font foi.

    Le contrat prévoit que le Binôme A calcule la saisonnalité ; le Binôme B ne
    doit pas la recalculer différemment à partir du timestamp.
    """
    df = pd.DataFrame(
        {"ts": _horodatages(1), "hour_of_day": [6], "day_of_week": [2]}
    )
    encode = add_cyclic_features(df)
    attendu = pd.Series([6.0]).apply(lambda h: __import__("numpy").sin(2 * 3.141592653589793 * h / 24))
    assert abs(encode.hour_sin.iloc[0] - attendu.iloc[0]) < 1e-9
