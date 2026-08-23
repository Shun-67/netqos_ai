"""
Tests du protocole temporel : découpage sans fuite et alignement des cibles.

Deux invariants du §4.3 de la fiche sont vérifiés ici :

  1. le découpage entraînement/validation/test respecte l'ordre chronologique,
     cellule par cellule, avec purge des fenêtres glissantes à cheval ;
  2. les cibles de prévision sont alignées par **durée** et non par **position**.

Le second point est le piège le plus discret du projet. Un `shift(-h)` décale
d'un nombre de lignes ; dès que la grille temporelle présente un trou, la cible
prélevée n'est plus celle de `t + h` mais celle de la ligne suivante, quelle que
soit sa date. Le modèle apprend alors une relation fausse, et rien ne le signale.
"""

import numpy as np
import pandas as pd
import pytest

from src.config import KPIS
from src.features.splits import temporal_split
from src.models import forecast as F


def _grille(n: int, debut: str = "2026-01-01 00:00:00"):
    return pd.date_range(debut, periods=n, freq="1min", tz="UTC")


def _features(n_par_cellule: int, cellules=("c1", "c2")) -> pd.DataFrame:
    lignes = []
    for cellule in cellules:
        lignes.append(
            pd.DataFrame(
                {
                    "ts": _grille(n_par_cellule),
                    "cell_id": cellule,
                    "latency_mean_5m": np.arange(n_par_cellule, dtype=float),
                }
            )
        )
    return pd.concat(lignes, ignore_index=True)


# ==================================================================
# Découpage chronologique
# ==================================================================
def test_decoupage_respecte_l_ordre_chronologique():
    split = temporal_split(_features(500), purge=60)
    split.assert_chronological()  # ne lève pas


def test_decoupage_applique_la_purge_entre_segments():
    """La purge doit créer un trou d'au moins `purge` minutes.

    Sans elle, les premières lignes de validation résument des mesures
    d'entraînement via les fenêtres glissantes de 60 min du contrat.
    """
    purge = 60
    split = temporal_split(_features(600), purge=purge)
    for cellule in ("c1", "c2"):
        fin_train = split.train.loc[split.train.cell_id == cellule, "ts"].max()
        debut_val = split.val.loc[split.val.cell_id == cellule, "ts"].min()
        ecart_min = (debut_val - fin_train).total_seconds() / 60
        assert ecart_min > purge, f"{cellule} : purge insuffisante ({ecart_min} min)"


def test_decoupage_est_fait_cellule_par_cellule():
    """Chaque cellule doit être présente dans les trois segments.

    Un découpage global sur le timestamp pourrait envoyer une cellule entière
    dans un seul segment si les historiques ne se recouvrent pas.
    """
    split = temporal_split(_features(400), purge=30)
    for segment in (split.train, split.val, split.test):
        assert set(segment.cell_id.unique()) == {"c1", "c2"}


def test_decoupage_produit_des_segments_disjoints():
    split = temporal_split(_features(400), purge=30)
    cles = lambda d: set(zip(d.ts, d.cell_id))
    assert not cles(split.train) & cles(split.val)
    assert not cles(split.val) & cles(split.test)
    assert not cles(split.train) & cles(split.test)


@pytest.mark.parametrize("train_ratio,val_ratio", [(0.9, 0.2), (1.0, 0.1), (0.0, 0.2)])
def test_decoupage_refuse_des_ratios_incoherents(train_ratio, val_ratio):
    with pytest.raises(ValueError):
        temporal_split(_features(100), train_ratio=train_ratio, val_ratio=val_ratio)


# ==================================================================
# Alignement des cibles de prévision
# ==================================================================
def _historique_avec_trou() -> pd.DataFrame:
    """Grille 0,1,2,3 puis 10,11 minutes : un trou de 6 minutes."""
    minutes = [0, 1, 2, 3, 10, 11]
    debut = pd.Timestamp("2026-01-01 00:00:00", tz="UTC")
    horodatages = [debut + pd.Timedelta(minutes=m) for m in minutes]
    donnees = {"ts": horodatages, "cell_id": ["c1"] * len(minutes)}
    for kpi in KPIS:
        # Valeur = numéro de minute, pour identifier sans ambiguïté la cible lue.
        donnees[kpi] = [float(m) for m in minutes]
    return pd.DataFrame(donnees)


def test_cibles_alignees_par_duree_et_non_par_position():
    """Le test central : un trou dans la grille ne doit pas fabriquer de cible.

    À `ts = 3 min` et horizon 1 min, la valeur de `t + 1` n'existe pas (la mesure
    suivante est à 10 min). La cible doit donc être NaN. Un `shift(-1)` aurait
    retourné 10.0 — une cible datée de sept minutes plus tard que demandé.
    """
    historique = _historique_avec_trou()
    features = historique[["ts", "cell_id"]].copy()

    resultat = F.build_targets(features, historique, horizons=[1], kpis=["latency"])
    cibles = resultat["latency_target_1m"].tolist()

    # ts=0 -> 1, ts=1 -> 2, ts=2 -> 3, ts=3 -> absent, ts=10 -> 11, ts=11 -> absent
    assert cibles[0] == 1.0
    assert cibles[1] == 2.0
    assert cibles[2] == 3.0
    assert np.isnan(cibles[3]), "un shift positionnel aurait renvoyé 10.0 ici"
    assert cibles[4] == 11.0
    assert np.isnan(cibles[5])


def test_cibles_correctes_sur_une_grille_continue():
    historique = pd.DataFrame(
        {"ts": _grille(20), "cell_id": "c1", **{kpi: np.arange(20, dtype=float) for kpi in KPIS}}
    )
    features = historique[["ts", "cell_id"]].copy()
    resultat = F.build_targets(features, historique, horizons=[5], kpis=["latency"])
    valides = resultat["latency_target_5m"].dropna()
    # y(t+5) - y(t) doit valoir exactement 5 partout où la cible existe.
    assert (valides.to_numpy() - np.arange(len(valides), dtype=float) == 5).all()


def test_cibles_ne_traversent_pas_les_cellules():
    """La cible d'une cellule ne doit jamais provenir d'une autre."""
    debut = pd.Timestamp("2026-01-01 00:00:00", tz="UTC")
    historique = pd.DataFrame(
        {
            "ts": [debut, debut + pd.Timedelta(minutes=1)] * 2,
            "cell_id": ["c1", "c1", "c2", "c2"],
            **{kpi: [1.0, 2.0, 100.0, 200.0] for kpi in KPIS},
        }
    )
    features = historique[["ts", "cell_id"]].copy()
    resultat = F.build_targets(features, historique, horizons=[1], kpis=["latency"])
    cibles = resultat.set_index(["cell_id", "ts"])["latency_target_1m"]
    assert cibles[("c1", debut)] == 2.0     # et non 200.0
    assert cibles[("c2", debut)] == 200.0   # et non 2.0


def test_forecast_features_exclut_les_cibles():
    """Les colonnes cibles ne doivent jamais devenir des prédicteurs.

    Sans ce filtre, `latency_target_5m` servirait à prédire
    `latency_target_15m` : une fuite du futur vers le futur.
    """
    df = pd.DataFrame(
        {
            "ts": _grille(3),
            "cell_id": "c1",
            "latency_mean_5m": [1.0, 2.0, 3.0],
            "latency_target_5m": [2.0, 3.0, 4.0],
            "throughput_target_30m": [9.0, 9.0, 9.0],
            "is_anomaly": [False, False, True],
        }
    )
    predicteurs = F.forecast_features(df)
    assert predicteurs == ["latency_mean_5m"]
