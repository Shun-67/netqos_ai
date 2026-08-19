"""
Prévision des KPI réseau à court terme — Binôme B.

Objectif fonctionnel (§3.2.6 de la fiche) : anticiper l'évolution des KPI à
horizon court, pour permettre au dashboard d'annoncer une dégradation **avant**
qu'elle n'affecte les utilisateurs. Horizons retenus : 5, 15 et 30 minutes,
dimensionnés par l'autocorrélation mesurée pendant l'EDA.

Cinq prédicteurs partageant l'interface `fit` / `predict` :

| Prédicteur                  | Rôle     | Principe                                        |
|-----------------------------|----------|-------------------------------------------------|
| `PersistenceForecaster`     | baseline | ŷ(t+h) = dernière valeur observée                |
| `MovingAverageForecaster`   | baseline | ŷ(t+h) = moyenne glissante 15 min                |
| `SeasonalNaiveForecaster`   | baseline | ŷ(t+h) = valeur au même instant la veille        |
| `ARIMAForecaster`           | baseline | modèle autorégressif statistique                 |
| `XGBForecaster`             | **avancé** | gradient boosting sur les features du contrat  |

La **persistance** est la référence à battre : sur une série fortement
autocorrélée, c'est un adversaire redoutable, et tout modèle qui ne la dépasse
pas ne mérite pas d'être déployé. Le rapport d'évaluation exprime donc les gains
en *skill score* relatif à la persistance.
"""

from __future__ import annotations

import warnings
from typing import Optional

import numpy as np
import pandas as pd

from src.config import FORECAST_HORIZONS, KPIS, RANDOM_STATE

# ==================================================================
# Construction du jeu de données supervisé
# ==================================================================
def build_targets(
    features: pd.DataFrame,
    history: pd.DataFrame,
    horizons: list[int] = FORECAST_HORIZONS,
    kpis: list[str] = KPIS,
) -> pd.DataFrame:
    """Ajoute les colonnes cibles `{kpi}_target_{h}m` aux features.

    La cible est la valeur **réelle** du KPI nettoyé à l'instant `t + h`, lue
    dans l'historique et non dérivée des features. L'alignement se fait par
    jointure sur `(cell_id, ts + h)` plutôt que par `shift(-h)` : un `shift`
    positionnel produirait des cibles fausses partout où la grille temporelle
    présente un trou, puisqu'il décalerait d'un nombre de lignes et non d'une
    durée.

    Aucune fuite : les prédicteurs sont datés de `t`, la cible de `t + h`.
    """
    lookup = history.set_index(["cell_id", "ts"])[kpis].sort_index()
    out = features.copy()

    for horizon in horizons:
        future_ts = out["ts"] + pd.Timedelta(minutes=horizon)
        keys = pd.MultiIndex.from_arrays([out["cell_id"], future_ts])
        for kpi in kpis:
            out[f"{kpi}_target_{horizon}m"] = lookup[kpi].reindex(keys).to_numpy()

    return out


def target_column(kpi: str, horizon: int) -> str:
    return f"{kpi}_target_{horizon}m"


def forecast_features(df: pd.DataFrame) -> list[str]:
    """Prédicteurs autorisés : tout sauf les cibles et les colonnes interdites."""
    banned_prefixes = tuple(f"{kpi}_target_" for kpi in KPIS)
    return [
        c
        for c in df.columns
        if not c.startswith(banned_prefixes)
        and c not in {"ts", "cell_id", "is_anomaly", "is_missing"}
        and pd.api.types.is_numeric_dtype(df[c])
    ]


# ==================================================================
# Interface commune
# ==================================================================
class BaseForecaster:
    name = "base"
    needs_fit = False

    def fit(
        self,
        train: pd.DataFrame,
        kpis: list[str],
        horizons: list[int],
        val: Optional[pd.DataFrame] = None,
    ) -> "BaseForecaster":
        return self

    def predict(self, df: pd.DataFrame, kpi: str, horizon: int) -> np.ndarray:
        raise NotImplementedError


# ==================================================================
# Baselines sans apprentissage
# ==================================================================
class PersistenceForecaster(BaseForecaster):
    """ŷ(t+h) = valeur courante. Référence de skill score.

    On utilise `{kpi}_mean_5m` comme estimateur de la valeur courante : c'est la
    représentation de l'instant `t` disponible dans les features du contrat, et
    elle est moins bruitée que la mesure ponctuelle.
    """

    name = "persistance"

    def predict(self, df: pd.DataFrame, kpi: str, horizon: int) -> np.ndarray:
        return df[f"{kpi}_mean_5m"].to_numpy()


class MovingAverageForecaster(BaseForecaster):
    """ŷ(t+h) = moyenne glissante 15 min. Lisse davantage que la persistance."""

    name = "moyenne_mobile_15m"

    def predict(self, df: pd.DataFrame, kpi: str, horizon: int) -> np.ndarray:
        return df[f"{kpi}_mean_15m"].to_numpy()


class SeasonalNaiveForecaster(BaseForecaster):
    """ŷ(t+h) = valeur observée 24 h plus tôt au même instant.

    Baseline indispensable ici : l'EDA a mesuré une amplitude de saisonnalité
    journalière de 40 à 104 % selon le KPI. Un modèle qui ne battrait pas ce
    naïf saisonnier n'apporterait rien au-delà du cycle jour/nuit.
    """

    name = "naif_saisonnier_24h"

    def __init__(self, kpis: list[str] = KPIS):
        self.kpis = kpis
        self._lookup: Optional[pd.DataFrame] = None

    def fit(
        self,
        train: pd.DataFrame,
        kpis: list[str],
        horizons: list[int],
        val: Optional[pd.DataFrame] = None,
    ):
        # L'historique de référence doit couvrir train + val + test : on le
        # fournit séparément via `set_history`, car la valeur de la veille d'un
        # point de test appartient parfois encore au segment de validation.
        return self

    def set_history(self, history: pd.DataFrame) -> "SeasonalNaiveForecaster":
        self._lookup = history.set_index(["cell_id", "ts"])[self.kpis].sort_index()
        return self

    def predict(self, df: pd.DataFrame, kpi: str, horizon: int) -> np.ndarray:
        if self._lookup is None:
            raise RuntimeError("Appeler set_history() avant predict().")
        # Instant visé (t + h), ramené 24 h en arrière.
        past_ts = df["ts"] + pd.Timedelta(minutes=horizon) - pd.Timedelta(days=1)
        keys = pd.MultiIndex.from_arrays([df["cell_id"], past_ts])
        values = self._lookup[kpi].reindex(keys).to_numpy()
        # Repli sur la persistance quand la veille n'est pas disponible
        # (début de l'historique), pour ne pas fabriquer de NaN artificiels.
        fallback = df[f"{kpi}_mean_5m"].to_numpy()
        return np.where(np.isfinite(values), values, fallback)


# ==================================================================
# Baseline statistique — ARIMA
# ==================================================================
class ARIMAForecaster(BaseForecaster):
    """ARIMA ajusté par cellule, prévision à h pas.

    Deux compromis d'ingénierie, assumés et documentés :

    1. **Fenêtre de contexte glissante** (`context_window`, 24 h par défaut).
       Réajuster un ARIMA à chaque origine de prévision sur 60 000 points est
       hors de portée. On ajuste donc les paramètres une fois par cellule sur le
       segment d'entraînement, puis on les *applique* (sans réajustement) à une
       fenêtre glissante de 24 h précédant chaque origine. 24 h suffisent
       largement pour un horizon de 5 à 30 min.

    2. **Sous-échantillonnage des origines** (`origin_step`). On ne prévoit pas
       depuis chacune des 20 000 minutes de test mais depuis une origine toutes
       les `origin_step` minutes. Les autres modèles sont évalués **sur les mêmes
       origines** afin que la comparaison reste valide ; c'est le rôle du masque
       retourné par `evaluated_index`.

    L'ordre du modèle est choisi par AIC sur une courte grille, ce qui évite un
    ordre arbitraire sans nécessiter `auto_arima` (non disponible dans la stack).
    """

    name = "arima"
    needs_fit = True

    CANDIDATE_ORDERS = [(1, 0, 0), (2, 0, 0), (2, 0, 1), (1, 1, 1), (2, 1, 1)]

    def __init__(
        self,
        context_window: int = 1440,
        origin_step: int = 30,
        fit_points: int = 4320,
        max_origins_per_cell: int = 120,
        max_horizon: int = max(FORECAST_HORIZONS),
    ):
        self.context_window = context_window
        self.origin_step = origin_step
        self.fit_points = fit_points
        self.max_origins_per_cell = max_origins_per_cell
        self.max_horizon = max_horizon
        self.orders_: dict[tuple[str, str], tuple[int, int, int]] = {}
        self._history: Optional[pd.DataFrame] = None
        # Cache des trajectoires prévues, clé (cell_id, kpi, origine). Un ARIMA
        # ajusté sur une origine donne d'un coup la prévision à tous les
        # horizons : sans ce cache, on refaisait le même ajustement trois fois.
        self._forecast_cache: dict[tuple[str, str, pd.Timestamp], np.ndarray] = {}

    def set_history(self, history: pd.DataFrame) -> "ARIMAForecaster":
        self._history = history.set_index(["cell_id", "ts"]).sort_index()
        return self

    def fit(
        self,
        train: pd.DataFrame,
        kpis: list[str],
        horizons: list[int],
        val: Optional[pd.DataFrame] = None,
    ):
        """Sélectionne l'ordre ARIMA par AIC, cellule par cellule et KPI par KPI.

        `val` est ignoré : la sélection d'ordre se fait par critère d'information
        (AIC) sur le segment d'entraînement, sans jeu de validation.
        """
        from statsmodels.tsa.arima.model import ARIMA

        if self._history is None:
            raise RuntimeError("Appeler set_history() avant fit().")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for cell_id in sorted(train["cell_id"].unique()):
                cell_train = train[train["cell_id"] == cell_id].sort_values("ts")
                end_ts = cell_train["ts"].max()
                for kpi in kpis:
                    series = (
                        self._history.loc[cell_id, kpi]
                        .loc[:end_ts]
                        .tail(self.fit_points)
                        .astype(float)
                    )
                    best_order, best_aic = self.CANDIDATE_ORDERS[0], np.inf
                    for order in self.CANDIDATE_ORDERS:
                        try:
                            aic = ARIMA(series.to_numpy(), order=order).fit().aic
                        except Exception:
                            continue
                        if np.isfinite(aic) and aic < best_aic:
                            best_order, best_aic = order, aic
                    self.orders_[(cell_id, kpi)] = best_order
        return self

    def evaluated_index(self, df: pd.DataFrame) -> np.ndarray:
        """Positions retenues comme origines de prévision (masque booléen).

        Les autres modèles doivent être évalués sur ce même masque pour que la
        comparaison des métriques soit valide.
        """
        df = df.reset_index(drop=True)
        mask = np.zeros(len(df), dtype=bool)
        for _, group in df.groupby("cell_id"):
            positions = group.index.to_numpy()[:: self.origin_step]
            mask[positions[: self.max_origins_per_cell]] = True
        return mask

    def predict(self, df: pd.DataFrame, kpi: str, horizon: int) -> np.ndarray:
        """Prévision à h pas. Renvoie NaN hors des origines évaluées."""
        from statsmodels.tsa.arima.model import ARIMA

        if self._history is None:
            raise RuntimeError("Appeler set_history() avant predict().")

        df = df.reset_index(drop=True)
        out = np.full(len(df), np.nan)
        mask = self.evaluated_index(df)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for cell_id, group in df.groupby("cell_id"):
                order = self.orders_.get((cell_id, kpi), (2, 0, 1))
                cell_series = self._history.loc[cell_id, kpi].astype(float)
                for position in group.index[mask[group.index]]:
                    origin_ts = df.at[position, "ts"]
                    key = (cell_id, kpi, origin_ts)

                    trajectory = self._forecast_cache.get(key)
                    if trajectory is None:
                        context = cell_series.loc[:origin_ts].tail(self.context_window)
                        if len(context) < 60:
                            continue
                        try:
                            fitted = ARIMA(context.to_numpy(), order=order).fit()
                            trajectory = np.asarray(fitted.forecast(steps=self.max_horizon))
                        except Exception:
                            # Repli persistance : préférable à un NaN, qui
                            # retirerait le point de la comparaison et
                            # avantagerait artificiellement ARIMA.
                            trajectory = np.full(self.max_horizon, float(context.iloc[-1]))
                        self._forecast_cache[key] = trajectory

                    out[position] = float(trajectory[horizon - 1])
        return out


# ==================================================================
# Modèle avancé — XGBoost
# ==================================================================
class XGBForecaster(BaseForecaster):
    """Gradient boosting, un modèle par couple (KPI, horizon).

    Approche **directe** plutôt que récursive : chaque horizon a son propre
    modèle prédisant directement `y(t+h)`. La prévision récursive (réinjecter la
    prédiction à t+1 pour prédire t+2) accumulerait l'erreur sur 30 pas, ce qui
    est rédhibitoire ici.

    Justification du choix par rapport aux alternatives de la fiche :
      - vs ARIMA : capte les non-linéarités et les interactions entre KPI, que
        l'EDA a montrées fortement corrélés ;
      - vs Prophet : Prophet décompose tendance + saisonnalité, ce qui répond à
        une question à horizon jours/semaines. À 5–30 min, le signal dominant est
        autorégressif, pas saisonnier — l'EDA le confirme (autocorrélation
        élevée à courte portée) ;
      - vs LSTM/GRU : gain attendu marginal sur 60 000 lignes tabulaires, pour un
        coût d'entraînement et une dépendance framework disproportionnés.
    """

    name = "xgboost"
    needs_fit = True

    # Les deux objectifs mis en concurrence. `reg:squarederror` est le défaut de
    # XGBoost, mais il est très sensible aux valeurs extrêmes : les pics
    # d'anomalie (packet_loss jusqu'à 100 %, latence ×10) tirent les prédictions
    # vers le haut sur les 98 % de points normaux, ce qui se traduit par un biais
    # positif et une MAE dégradée. `reg:absoluteerror` optimise directement la
    # médiane conditionnelle : robuste aux queues, et aligné sur la métrique
    # d'évaluation (MAE). L'objectif est choisi par KPI et par horizon sur le
    # segment de validation.
    CANDIDATE_OBJECTIVES = ["reg:squarederror", "reg:absoluteerror"]

    def __init__(
        self,
        n_estimators: int = 400,
        max_depth: int = 6,
        learning_rate: float = 0.05,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        objective: Optional[str] = None,
        random_state: int = RANDOM_STATE,
    ):
        self.params = dict(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            random_state=random_state,
            n_jobs=-1,
            tree_method="hist",
        )
        # objective=None -> sélection sur validation ; sinon objectif imposé.
        self.objective = objective
        self.models: dict[tuple[str, int], object] = {}
        self.chosen_objective_: dict[tuple[str, int], str] = {}
        self.selection_log_: list[dict] = []
        self.feature_cols: list[str] = []

    def _train_one(self, X, y, objective: str):
        from xgboost import XGBRegressor

        model = XGBRegressor(objective=objective, **self.params)
        model.fit(X, y)
        return model

    def fit(
        self,
        train: pd.DataFrame,
        kpis: list[str],
        horizons: list[int],
        val: Optional[pd.DataFrame] = None,
    ) -> "XGBForecaster":
        self.feature_cols = forecast_features(train)
        # `cell_id` est encodé en variable catégorielle ordinale : il permet au
        # modèle de retenir le régime propre de chaque cellule sans qu'on ait à
        # entraîner un modèle distinct par cellule.
        categorical = pd.Categorical(train["cell_id"])
        self._cell_categories = list(categorical.categories)
        X_train = np.column_stack([train[self.feature_cols].to_numpy(), categorical.codes])

        X_val = self._design_matrix(val) if val is not None else None
        candidates = [self.objective] if self.objective else self.CANDIDATE_OBJECTIVES

        for kpi in kpis:
            for horizon in horizons:
                column = target_column(kpi, horizon)
                target = train[column].to_numpy()
                valid = np.isfinite(target)

                if X_val is None or len(candidates) == 1:
                    objective = candidates[0]
                    self.models[(kpi, horizon)] = self._train_one(
                        X_train[valid], target[valid], objective
                    )
                    self.chosen_objective_[(kpi, horizon)] = objective
                    continue

                # Sélection de l'objectif sur la MAE de validation.
                y_val = val[column].to_numpy()
                val_valid = np.isfinite(y_val)
                best_model, best_objective, best_mae = None, candidates[0], np.inf

                for objective in candidates:
                    model = self._train_one(X_train[valid], target[valid], objective)
                    prediction = model.predict(X_val[val_valid])
                    mae = float(np.mean(np.abs(prediction - y_val[val_valid])))
                    self.selection_log_.append(
                        {
                            "kpi": kpi,
                            "horizon_min": horizon,
                            "objectif": objective,
                            "mae_validation": round(mae, 5),
                        }
                    )
                    if mae < best_mae:
                        best_model, best_objective, best_mae = model, objective, mae

                self.models[(kpi, horizon)] = best_model
                self.chosen_objective_[(kpi, horizon)] = best_objective

        return self

    def selection_table(self) -> pd.DataFrame:
        """Journal de la sélection d'objectif, pour le rapport d'évaluation."""
        if not self.selection_log_:
            return pd.DataFrame()
        frame = pd.DataFrame(self.selection_log_)
        frame["retenu"] = [
            self.chosen_objective_[(row.kpi, row.horizon_min)] == row.objectif
            for row in frame.itertuples()
        ]
        return frame

    def _design_matrix(self, df: pd.DataFrame) -> np.ndarray:
        codes = pd.Categorical(df["cell_id"], categories=self._cell_categories).codes
        return np.column_stack([df[self.feature_cols].to_numpy(), codes])

    def predict(self, df: pd.DataFrame, kpi: str, horizon: int) -> np.ndarray:
        model = self.models.get((kpi, horizon))
        if model is None:
            raise KeyError(f"Aucun modèle entraîné pour ({kpi}, {horizon} min).")
        return model.predict(self._design_matrix(df))

    def feature_importance(self, kpi: str, horizon: int, top_k: int = 15) -> pd.DataFrame:
        """Importances du modèle — sert à justifier les features au jury."""
        model = self.models[(kpi, horizon)]
        names = self.feature_cols + ["cell_id_code"]
        importances = model.feature_importances_
        order = np.argsort(-importances)[:top_k]
        return pd.DataFrame(
            {"feature": [names[i] for i in order], "importance": importances[order].round(5)}
        )


# ==================================================================
# Fabrique
# ==================================================================
def build_forecasters(history: pd.DataFrame, with_arima: bool = True) -> dict[str, BaseForecaster]:
    """Instancie les prédicteurs comparés dans le rapport d'évaluation."""
    forecasters: dict[str, BaseForecaster] = {
        "persistance": PersistenceForecaster(),
        "moyenne_mobile_15m": MovingAverageForecaster(),
        "naif_saisonnier_24h": SeasonalNaiveForecaster().set_history(history),
    }
    if with_arima:
        forecasters["arima"] = ARIMAForecaster().set_history(history)
    forecasters["xgboost"] = XGBForecaster()
    return forecasters
