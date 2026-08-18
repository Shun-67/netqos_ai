"""
Protocole de découpage temporel — garantie d'absence de fuite de données.

Règle non négociable du projet (§4.3 de la fiche) : le découpage
entraînement / validation / test respecte l'ordre chronologique. Aucun
mélange aléatoire, aucun `train_test_split(shuffle=True)`.

Deux garanties supplémentaires implémentées ici :

1. Découpage **par cellule**. Les features du Binôme A sont calculées par
   `cell_id` ; un découpage global sur le timestamp trierait des lignes de
   cellules différentes ensemble. On coupe donc chaque cellule à son propre
   quantile temporel, puis on recolle.

2. **Purge** entre segments. Les features contiennent des fenêtres glissantes
   jusqu'à 60 minutes et des lags jusqu'à 10 minutes : les premières lignes
   d'un segment de validation résument des mesures appartenant au segment
   d'entraînement. On retire donc les `purge` premières lignes de chaque
   segment aval (60 minutes par défaut, la plus longue fenêtre du contrat).
   Sans cette purge, la performance annoncée est optimiste.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.config import POINTS_PER_HOUR, TEST_RATIO, TRAIN_RATIO, VAL_RATIO

# Purge par défaut = plus longue fenêtre du contrat de features (60 min).
DEFAULT_PURGE = POINTS_PER_HOUR


@dataclass
class TemporalSplit:
    """Trois segments chronologiques disjoints et purgés."""

    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame

    def summary(self) -> pd.DataFrame:
        rows = []
        for name, part in (("train", self.train), ("val", self.val), ("test", self.test)):
            if part.empty:
                rows.append({"segment": name, "n": 0})
                continue
            rows.append(
                {
                    "segment": name,
                    "n": len(part),
                    "debut": part["ts"].min(),
                    "fin": part["ts"].max(),
                    "cellules": part["cell_id"].nunique(),
                }
            )
        return pd.DataFrame(rows)

    def assert_chronological(self) -> None:
        """Vérifie qu'aucun timestamp de test ne précède un timestamp d'entraînement.

        Contrôle effectué par cellule : c'est l'unité sur laquelle les modèles
        sont appliqués.
        """
        for cell_id in self.train["cell_id"].unique():
            tr = self.train.loc[self.train["cell_id"] == cell_id, "ts"]
            va = self.val.loc[self.val["cell_id"] == cell_id, "ts"]
            te = self.test.loc[self.test["cell_id"] == cell_id, "ts"]
            if not va.empty and tr.max() >= va.min():
                raise AssertionError(
                    f"{cell_id} : chevauchement train/val ({tr.max()} >= {va.min()})"
                )
            if not te.empty and not va.empty and va.max() >= te.min():
                raise AssertionError(
                    f"{cell_id} : chevauchement val/test ({va.max()} >= {te.min()})"
                )


def temporal_split(
    df: pd.DataFrame,
    train_ratio: float = TRAIN_RATIO,
    val_ratio: float = VAL_RATIO,
    purge: int = DEFAULT_PURGE,
) -> TemporalSplit:
    """Découpe `df` en train/val/test chronologiques, cellule par cellule.

    `purge` : nombre de lignes retirées en tête de val et de test, pour éliminer
    les fenêtres glissantes à cheval sur le segment précédent.
    """
    if not 0 < train_ratio < 1 or not 0 < val_ratio < 1:
        raise ValueError("Les ratios doivent être dans ]0, 1[.")
    if train_ratio + val_ratio >= 1:
        raise ValueError("train_ratio + val_ratio doit laisser de la place au test.")

    trains, vals, tests = [], [], []

    for _, group in df.groupby("cell_id", sort=True):
        group = group.sort_values("ts")
        n = len(group)
        i_train = int(n * train_ratio)
        i_val = int(n * (train_ratio + val_ratio))

        trains.append(group.iloc[:i_train])
        vals.append(group.iloc[i_train + purge : i_val])
        tests.append(group.iloc[i_val + purge :])

    return TemporalSplit(
        train=_concat(trains),
        val=_concat(vals),
        test=_concat(tests),
    )


def split_by_timestamp(
    df: pd.DataFrame, train_end: str, val_end: str, purge: int = DEFAULT_PURGE
) -> TemporalSplit:
    """Variante à bornes temporelles explicites (utile pour rejouer un découpage)."""
    train_end_ts = pd.Timestamp(train_end, tz="UTC")
    val_end_ts = pd.Timestamp(val_end, tz="UTC")
    offset = pd.Timedelta(minutes=purge)

    return TemporalSplit(
        train=df[df["ts"] <= train_end_ts].reset_index(drop=True),
        val=df[(df["ts"] > train_end_ts + offset) & (df["ts"] <= val_end_ts)].reset_index(
            drop=True
        ),
        test=df[df["ts"] > val_end_ts + offset].reset_index(drop=True),
    )


def _concat(parts: list[pd.DataFrame]) -> pd.DataFrame:
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True).sort_values(["cell_id", "ts"]).reset_index(
        drop=True
    )


class LabelAlignmentError(RuntimeError):
    """La vérité terrain ne s'aligne pas sur les features fournies."""


# Sous ce taux d'appariement, on considère que la jointure a échoué plutôt que
# de conclure à une absence d'anomalies.
MIN_MATCH_RATE = 0.5


def align_labels(
    features: pd.DataFrame, labels: pd.DataFrame, min_match_rate: float = MIN_MATCH_RATE
) -> pd.Series:
    """Aligne la vérité terrain sur l'index de `features` via (ts, cell_id).

    Utilisé uniquement au moment de l'évaluation. La série retournée n'est
    jamais concaténée aux features.

    Lève `LabelAlignmentError` si trop peu de lignes trouvent leur étiquette.
    Ce garde-fou n'est pas théorique : les horodatages de `GET /eval/labels`
    n'étant pas rééchantillonnés dans le contrat v1.1, une jointure naïve
    n'appariait **aucune** ligne et produisait une prévalence de 0 %. Toutes les
    métriques de détection tombaient alors à zéro, sans la moindre erreur — le
    genre de panne silencieuse qui invalide une campagne d'évaluation entière.
    """
    if labels.empty:
        raise LabelAlignmentError(
            "Vérité terrain vide : impossible d'évaluer la détection d'anomalies."
        )

    merged = features[["ts", "cell_id"]].merge(
        labels[["ts", "cell_id", "is_anomaly"]], on=["ts", "cell_id"], how="left"
    )
    match_rate = float(merged["is_anomaly"].notna().mean())

    if match_rate < min_match_rate:
        raise LabelAlignmentError(
            f"Seules {match_rate:.1%} des lignes de features trouvent leur étiquette "
            f"(seuil : {min_match_rate:.0%}). Les horodatages des deux sources ne "
            f"concordent pas — vérifier l'alignement de /eval/labels sur la grille "
            f"rééchantillonnée. Exemples de ts features : "
            f"{features['ts'].head(2).tolist()} ; ts étiquettes : "
            f"{labels['ts'].head(2).tolist()}"
        )

    return merged["is_anomaly"].fillna(False).astype(bool)
