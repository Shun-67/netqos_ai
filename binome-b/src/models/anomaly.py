"""
Détection d'anomalies non supervisée — Binôme B.

Quatre détecteurs partageant une interface commune (`fit` / `score` / `predict`),
pour que l'évaluation et le dashboard soient interchangeables :

| Détecteur              | Rôle            | Principe                                        |
|------------------------|-----------------|-------------------------------------------------|
| `ThresholdDetector`    | baseline naïve  | règles de seuils du contrat (état critique)      |
| `IsolationForestDetector` | baseline ML  | isolement par partitionnement aléatoire          |
| `DBSCANDetector`       | baseline ML     | points de bruit d'un clustering par densité      |
| `AutoencoderDetector`  | **avancé**      | erreur de reconstruction d'un réseau goulot      |

Convention de score : **plus le score est élevé, plus le point est atypique**,
pour tous les détecteurs. `predict` applique un seuil sur ce score.

Deux choix de conception structurants :

1. **Normalisation par cellule.** Les cellules ont des régimes physiques
   différents (débit de base de 80 à 150 Mbit/s selon la cellule). Un modèle
   global entraîné sur des valeurs absolues signalerait en permanence les
   cellules à faible débit. Chaque cellule est donc normalisée par la médiane et
   l'écart interquartile de **son propre segment d'entraînement**, avant qu'un
   modèle unique ne soit ajusté sur l'ensemble. On conserve ainsi le volume de
   données d'un modèle global tout en neutralisant le biais inter-cellule.

2. **Espace de features compact et non redondant.** Les 43 features du contrat
   contiennent beaucoup de colinéarité (trois moyennes glissantes, trois lags par
   KPI). On retient 23 features décrivant l'état courant, la volatilité, l'écart
   à la normale horaire et la tendance — voir `ANOMALY_FEATURES`. Un espace plus
   compact améliore la densité locale, ce dont dépendent DBSCAN et l'autoencodeur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import NearestNeighbors
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import RobustScaler

from src.config import KPIS, RANDOM_STATE
from src.models import qos_state


# ==================================================================
# Espace de features
# ==================================================================
def anomaly_features(df: pd.DataFrame) -> list[str]:
    """Sous-ensemble de features retenu pour la détection d'anomalies."""
    wanted: list[str] = []
    for kpi in KPIS:
        wanted += [
            f"{kpi}_mean_5m",  # état court terme
            f"{kpi}_std_15m",  # volatilité
            f"{kpi}_ratio_to_hour",  # écart à la normale horaire (features dérivées B)
            f"{kpi}_trend_5m_30m",  # dynamique court/moyen terme
        ]
    wanted += ["cell_load_hour_max", "hour_sin", "hour_cos"]
    return [c for c in wanted if c in df.columns]


ANOMALY_FEATURES = anomaly_features  # alias lisible à l'import


# ==================================================================
# Normalisation par cellule
# ==================================================================
@dataclass
class PerCellScaler:
    """Un RobustScaler par cellule, ajusté sur le segment d'entraînement."""

    cols: list[str]
    scalers: dict[str, RobustScaler] = field(default_factory=dict)
    _fallback: Optional[RobustScaler] = None

    def fit(self, train_df: pd.DataFrame) -> "PerCellScaler":
        for cell_id, group in train_df.groupby("cell_id"):
            scaler = RobustScaler()
            scaler.fit(group[self.cols].to_numpy())
            self.scalers[str(cell_id)] = scaler
        # Repli pour une cellule apparue après l'entraînement (nouvelle antenne).
        self._fallback = RobustScaler().fit(train_df[self.cols].to_numpy())
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        if not self.scalers:
            raise RuntimeError("PerCellScaler non ajusté.")
        # Index positionnel : le DataFrame reçu peut avoir un index quelconque
        # (sous-ensemble filtré par le dashboard, par exemple).
        df = df.reset_index(drop=True)
        out = np.empty((len(df), len(self.cols)), dtype=float)
        for cell_id, group in df.groupby("cell_id"):
            scaler = self.scalers.get(str(cell_id), self._fallback)
            out[group.index.to_numpy()] = scaler.transform(group[self.cols].to_numpy())
        return out


# ==================================================================
# Interface commune
# ==================================================================
class BaseDetector:
    """Contrat commun à tous les détecteurs."""

    name = "base"
    is_supervised = False

    def fit(self, df: pd.DataFrame) -> "BaseDetector":
        raise NotImplementedError

    def score(self, df: pd.DataFrame) -> np.ndarray:
        """Score d'atypicité, croissant avec l'anormalité."""
        raise NotImplementedError

    def predict(self, df: pd.DataFrame, threshold: float) -> np.ndarray:
        return self.score(df) >= threshold

    def default_threshold(self, df: pd.DataFrame, contamination: float) -> float:
        """Seuil non supervisé : quantile du score sur les données fournies.

        Aucune étiquette n'intervient : `contamination` est un paramètre
        d'exploitation (volume d'alertes acceptable), fixé a priori.
        """
        return float(np.quantile(self.score(df), 1 - contamination))


# ==================================================================
# 1. Baseline explicable — seuils du contrat
# ==================================================================
class ThresholdDetector(BaseDetector):
    """Baseline non apprise : est anormal tout point d'état QoS « critique ».

    Sert de référence basse obligatoire : tout modèle appris doit la battre pour
    justifier sa complexité. C'est aussi le détecteur le plus explicable, donc
    celui auquel un exploitant se fiera par défaut.
    """

    name = "seuils_contrat"

    def __init__(self, thresholds: dict[str, dict]):
        self.thresholds = thresholds

    def fit(self, df: pd.DataFrame) -> "ThresholdDetector":
        return self  # aucun apprentissage

    def score(self, df: pd.DataFrame) -> np.ndarray:
        """Score = rang du pire état (0 bon, 1 dégradé, 2 critique).

        On applique les seuils aux moyennes 5 min (`*_mean_5m`), qui sont la
        représentation de l'état courant disponible dans les features.
        """
        labelled = qos_state.classify_frame(df, self.thresholds, suffix="_mean_5m")
        codes = pd.Categorical(labelled["qos_state"], categories=qos_state.STATES).codes
        return codes.astype(float)

    def default_threshold(self, df: pd.DataFrame, contamination: float) -> float:
        return 2.0  # « critique » uniquement


# ==================================================================
# 2. Baseline ML — Isolation Forest
# ==================================================================
class IsolationForestDetector(BaseDetector):
    """Isolation Forest : un point atypique s'isole en peu de coupes aléatoires.

    Robuste en grande dimension et linéaire en nombre de points, ce qui en fait
    la baseline apprise de référence.
    """

    name = "isolation_forest"

    def __init__(
        self,
        cols: list[str],
        n_estimators: int = 300,
        contamination: float = 0.02,
        random_state: int = RANDOM_STATE,
    ):
        self.cols = cols
        self.scaler = PerCellScaler(cols)
        self.model = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=random_state,
            n_jobs=-1,
        )

    def fit(self, df: pd.DataFrame) -> "IsolationForestDetector":
        self.scaler.fit(df)
        self.model.fit(self.scaler.transform(df))
        return self

    def score(self, df: pd.DataFrame) -> np.ndarray:
        # `score_samples` est d'autant plus BAS que le point est anormal : on
        # inverse le signe pour respecter la convention commune.
        return -self.model.score_samples(self.scaler.transform(df))


# ==================================================================
# 3. Baseline ML — DBSCAN
# ==================================================================
class DBSCANDetector(BaseDetector):
    """DBSCAN : les points de bruit (label -1) sont les anomalies.

    DBSCAN est **transductif** : il n'a pas de méthode `predict`, le clustering
    n'existe que sur les points ajustés. Pour l'appliquer à un segment de test
    sans réajuster (ce qui interdirait toute comparaison), on procède en deux
    temps :
      1. `fit` sur un échantillon du segment d'entraînement, dont on retient les
         points de cœur (*core samples*) ;
      2. `score` = distance au point de cœur le plus proche. Un point éloigné de
         tout cœur est, par construction de DBSCAN, un point de bruit.

    Cette distance est un score continu, ce qui permet en outre de tracer une
    courbe précision/rappel là où DBSCAN ne fournit qu'une décision binaire.

    L'échantillonnage (`max_train_points`) est nécessaire : DBSCAN est en
    O(n²) sans index spatial efficace, et l'espace de features à 23 dimensions
    dégrade les arbres de recherche.
    """

    name = "dbscan"

    def __init__(
        self,
        cols: list[str],
        eps: Optional[float] = None,
        min_samples: int = 20,
        max_train_points: int = 20_000,
        eps_quantile: float = 0.98,
        random_state: int = RANDOM_STATE,
    ):
        self.cols = cols
        # eps=None -> estimation automatique par la méthode du coude des
        # k-distances (voir `_estimate_eps`). Fixer eps à la main serait
        # arbitraire et rendrait la comparaison avec les autres détecteurs
        # dépendante d'un réglage non justifié.
        self.eps = eps
        self.min_samples = min_samples
        self.max_train_points = max_train_points
        self.eps_quantile = eps_quantile
        self.random_state = random_state
        self.scaler = PerCellScaler(cols)
        self._core_index: Optional[NearestNeighbors] = None
        self.n_core_ = 0
        self.noise_ratio_ = np.nan

    def _estimate_eps(self, X: np.ndarray) -> float:
        """Estime eps par la distribution des k-distances (k = min_samples).

        Heuristique standard et **non supervisée** : on calcule pour chaque point
        la distance à son k-ième voisin, puis on retient un quantile haut de
        cette distribution. Les points au-delà sont, par construction, ceux dont
        le voisinage est trop peu dense pour former un cœur — soit exactement la
        définition du bruit DBSCAN. `eps_quantile = 0.98` cible donc environ 2 %
        de bruit, cohérent avec le paramètre de contamination des autres
        détecteurs.
        """
        neighbours = NearestNeighbors(n_neighbors=self.min_samples, n_jobs=-1).fit(X)
        distances, _ = neighbours.kneighbors(X)
        k_distances = distances[:, -1]
        return float(np.quantile(k_distances, self.eps_quantile))

    def fit(self, df: pd.DataFrame) -> "DBSCANDetector":
        self.scaler.fit(df)
        X = self.scaler.transform(df)

        if len(X) > self.max_train_points:
            # Échantillonnage systématique : préserve la couverture temporelle,
            # là où un tirage aléatoire pur pourrait négliger des plages horaires.
            step = len(X) // self.max_train_points
            idx = np.arange(0, len(X), max(step, 1))[: self.max_train_points]
            X = X[idx]

        if self.eps is None:
            self.eps = self._estimate_eps(X)
            print(f"[dbscan] eps estimé par k-distance (q={self.eps_quantile}) : {self.eps:.3f}")

        labels = DBSCAN(eps=self.eps, min_samples=self.min_samples, n_jobs=-1).fit_predict(X)
        core_mask = labels != -1
        self.noise_ratio_ = float((~core_mask).mean())

        if core_mask.sum() == 0:
            # eps trop petit : tout est bruit. On se rabat sur l'ensemble des
            # points pour rester exploitable, en signalant le problème.
            print(
                f"[dbscan] eps={self.eps} déclare 100 % de bruit : "
                "score dégradé en distance au plus proche voisin."
            )
            core_mask = np.ones(len(X), dtype=bool)

        self.n_core_ = int(core_mask.sum())
        self._core_index = NearestNeighbors(n_neighbors=1, n_jobs=-1).fit(X[core_mask])
        return self

    def score(self, df: pd.DataFrame) -> np.ndarray:
        if self._core_index is None:
            raise RuntimeError("DBSCANDetector non ajusté.")
        distances, _ = self._core_index.kneighbors(self.scaler.transform(df))
        return distances.ravel()

    def default_threshold(self, df: pd.DataFrame, contamination: float) -> float:
        # Le seuil naturel de DBSCAN est eps : au-delà, le point n'est dans le
        # voisinage d'aucun cœur, donc c'est du bruit au sens de l'algorithme.
        return self.eps


# ==================================================================
# 4. Modèle avancé — autoencodeur
# ==================================================================
class AutoencoderDetector(BaseDetector):
    """Autoencodeur : score = erreur de reconstruction.

    Un réseau en goulot d'étranglement (23 → 12 → 6 → 12 → 23) apprend à
    reconstruire les données d'entraînement. Le régime normal étant très
    majoritaire (~1 % d'anomalies), le réseau apprend la variété des
    comportements normaux ; un point atypique se reconstruit mal, et son erreur
    quadratique sert de score.

    Intérêt sur les autres détecteurs : l'autoencodeur capte des anomalies de
    **forme** (combinaison inhabituelle de KPI chacun dans sa plage normale), là
    où les seuils ne voient que l'amplitude. C'est précisément la catégorie
    d'anomalies que l'EDA a montrée invisible aux seuls seuils (§6.2 du rapport
    d'EDA).

    Implémenté avec `MLPRegressor` de scikit-learn plutôt qu'avec Keras/PyTorch :
    à ce volume de données, un framework de deep learning n'apporte rien et
    alourdirait l'installation.
    """

    name = "autoencodeur"

    def __init__(
        self,
        cols: list[str],
        hidden: tuple[int, ...] = (16, 8, 16),
        max_iter: int = 300,
        trim_quantile: float = 0.02,
        random_state: int = RANDOM_STATE,
    ):
        self.cols = cols
        self.hidden = hidden
        # `trim_quantile` : part des lignes d'entraînement les plus extrêmes
        # écartées avant l'ajustement. Un autoencodeur qui apprend à reconstruire
        # les anomalies présentes dans son jeu d'entraînement perd sa capacité à
        # les signaler. Le filtrage est **non supervisé** — il repose sur une
        # distance robuste dans l'espace normalisé, jamais sur `is_anomaly`.
        self.trim_quantile = trim_quantile
        self.scaler = PerCellScaler(cols)
        self.model = MLPRegressor(
            hidden_layer_sizes=hidden,
            activation="relu",
            solver="adam",
            learning_rate_init=1e-3,
            batch_size=256,
            max_iter=max_iter,
            early_stopping=True,
            n_iter_no_change=12,
            validation_fraction=0.1,
            random_state=random_state,
        )
        self.per_feature_error_: Optional[np.ndarray] = None
        self.n_train_kept_ = 0

    def fit(self, df: pd.DataFrame) -> "AutoencoderDetector":
        self.scaler.fit(df)
        X = self.scaler.transform(df)

        if self.trim_quantile > 0:
            # Distance robuste au centre : somme des écarts absolus normalisés.
            # Après RobustScaler, chaque colonne est centrée sur sa médiane et
            # réduite par son IQR, donc cette somme est directement comparable
            # d'une feature à l'autre.
            extremity = np.abs(X).sum(axis=1)
            keep = extremity <= np.quantile(extremity, 1 - self.trim_quantile)
            X = X[keep]

        self.n_train_kept_ = int(len(X))
        # Cible = entrée : c'est ce qui fait de ce MLP un autoencodeur.
        self.model.fit(X, X)
        return self

    def _reconstruction_error(self, df: pd.DataFrame) -> np.ndarray:
        X = self.scaler.transform(df)
        X_hat = self.model.predict(X)
        return (X - X_hat) ** 2

    def score(self, df: pd.DataFrame) -> np.ndarray:
        errors = self._reconstruction_error(df)
        self.per_feature_error_ = errors.mean(axis=0)
        return errors.mean(axis=1)

    def explain(self, df: pd.DataFrame, top_k: int = 3) -> pd.DataFrame:
        """Features contribuant le plus à l'erreur, point par point.

        Donne à l'exploitant une raison lisible derrière un score élevé — sans
        cela, un autoencodeur reste une boîte noire inutilisable en supervision.
        """
        errors = self._reconstruction_error(df)
        order = np.argsort(-errors, axis=1)[:, :top_k]
        cols = np.array(self.cols)
        return pd.DataFrame(
            {
                "score": errors.mean(axis=1),
                "causes": [", ".join(cols[row]) for row in order],
            },
            index=df.index,
        )


# ==================================================================
# Fabrique
# ==================================================================
def build_detectors(
    cols: list[str], thresholds: dict[str, dict], contamination: float = 0.02
) -> dict[str, BaseDetector]:
    """Instancie les quatre détecteurs comparés dans le rapport d'évaluation."""
    return {
        "seuils_contrat": ThresholdDetector(thresholds),
        "isolation_forest": IsolationForestDetector(cols, contamination=contamination),
        "dbscan": DBSCANDetector(cols),
        "autoencodeur": AutoencoderDetector(cols),
    }
