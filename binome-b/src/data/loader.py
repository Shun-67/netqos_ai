"""
Façade de chargement des données — masque la source réelle aux modèles.

Trois modes, pilotés par la variable d'environnement `NETQOS_DATA_SOURCE` :

  auto  (défaut) : interroge GET /health ; si l'API du Binôme A répond, elle est
                   utilisée ; sinon repli silencieux sur les CSV locaux.
  api            : impose l'API (lève ApiUnavailable si elle ne répond pas).
  local          : impose les CSV locaux (utile pour un entraînement reproductible
                   hors ligne, ou pour comparer les deux sources).

Le schéma servi est identique dans les deux cas (contrat v1.1), de sorte que le
code d'entraînement, d'évaluation et le dashboard sont indifférents à la source.

Usage :
    from src.data import loader
    features = loader.load_features()
    print(loader.active_source())   # "api" ou "local"
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from src import config
from src.data import local_source
from src.data.api_client import ApiClient, ApiUnavailable

_client: Optional[ApiClient] = None
_resolved_source: Optional[str] = None


# ==================================================================
# Résolution de la source
# ==================================================================
def _client_instance() -> ApiClient:
    global _client
    if _client is None:
        _client = ApiClient()
    return _client


def active_source(force_recheck: bool = False) -> str:
    """Retourne la source effectivement utilisée : "api" ou "local"."""
    global _resolved_source
    if _resolved_source is not None and not force_recheck:
        return _resolved_source

    mode = config.DATA_SOURCE
    if mode == "local":
        _resolved_source = "local"
    elif mode == "api":
        if not _client_instance().is_available():
            raise ApiUnavailable(
                f"NETQOS_DATA_SOURCE=api mais {config.API_BASE_URL} ne répond pas. "
                "Démarrez l'API du Binôme A, ou passez en NETQOS_DATA_SOURCE=local."
            )
        _resolved_source = "api"
    else:  # auto
        _resolved_source = "api" if _client_instance().is_available() else "local"

    return _resolved_source


def source_description() -> str:
    """Libellé lisible de la source active (affiché dans le dashboard)."""
    if active_source() == "api":
        return f"API Binôme A — {config.API_BASE_URL}"
    try:
        return f"CSV local — {local_source.resolve_raw_file().name}"
    except FileNotFoundError:
        return "CSV local — aucun fichier trouvé"


def reset() -> None:
    """Oublie la source résolue (à appeler après un changement d'environnement)."""
    global _resolved_source, _client
    _resolved_source = None
    _client = None
    local_source.clear_cache()


# ==================================================================
# Données
# ==================================================================
def load_history(
    cell_id: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """KPI nettoyés (GET /kpi/history ou équivalent local)."""
    if active_source() == "api":
        return _client_instance().get_kpi_history(cell_id, start, end)
    return _filter(local_source.build_clean(), cell_id, start, end)


def load_features(
    cell_id: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """Features pré-calculées (GET /features ou équivalent local)."""
    if active_source() == "api":
        return _client_instance().get_features(cell_id, start, end)
    return _filter(local_source.build_features(), cell_id, start, end)


def load_labels(
    cell_id: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """Vérité terrain `is_anomaly` — ÉVALUATION UNIQUEMENT.

    Ne jamais passer le résultat de cette fonction à un `fit()`.

    ATTENTION — contournement d'un défaut du contrat v1.1. `GET /eval/labels`
    sert les horodatages de `raw_kpi_measurements`, non rééchantillonnés
    (ex. `20:21:41`), alors que `/kpi/history` et `/features` sont rééchantillonnés
    à la minute pleine (`20:21:00`). Une jointure directe sur `(ts, cell_id)` ne
    trouve donc **aucune** correspondance, et toutes les étiquettes retombent
    silencieusement à False : la prévalence mesurée devient 0 % et toutes les
    métriques de détection s'effondrent à zéro sans qu'aucune erreur ne soit levée.

    On réaligne donc les étiquettes sur la grille minute, en agrégeant par `max`
    (une minute est anormale si au moins une mesure brute de cette minute l'était).
    C'est exactement la règle appliquée par `local_source.build_labels()`, ce qui
    garantit l'équivalence des deux sources.

    Correction demandée au Binôme A : que `/eval/labels` serve les horodatages
    alignés sur `clean_kpi_measurements`, seule façon de rendre l'endpoint
    joignable aux données qu'il est censé annoter.
    """
    if active_source() == "api":
        labels = _client_instance().get_eval_labels(cell_id, start, end)
        return _align_to_minute_grid(labels)
    return _filter(local_source.build_labels(), cell_id, start, end)


def _align_to_minute_grid(labels: pd.DataFrame) -> pd.DataFrame:
    """Ramène les étiquettes sur la grille minute des endpoints de données."""
    if labels.empty or "ts" not in labels.columns:
        return labels
    aligned = labels.copy()
    aligned["ts"] = aligned["ts"].dt.floor("1min")
    aligned["is_anomaly"] = aligned["is_anomaly"].astype(bool)
    return (
        aligned.groupby(["cell_id", "ts"], as_index=False)["is_anomaly"]
        .max()
        .sort_values(["cell_id", "ts"])
        .reset_index(drop=True)
    )


def load_latest(cell_id: Optional[str] = None, n: int = 100) -> pd.DataFrame:
    """Dernières mesures. En local, simule l'endpoint par une queue du nettoyé."""
    if active_source() == "api":
        return _client_instance().get_latest(cell_id, n)
    df = _filter(local_source.build_clean(), cell_id, None, None)
    return df.tail(n).reset_index(drop=True)


def load_stream(cell_id: Optional[str] = None, limit: int = 50) -> pd.DataFrame:
    """Flux quasi temps réel (GET /kpi/stream).

    Ne sert que les mesures dont `source = 'stream'`, c'est-à-dire celles
    produites par le simulateur de flux du Binôme A. Retourne un DataFrame vide
    si le simulateur ne tourne pas, ou en mode local — le flux n'a pas
    d'équivalent hors ligne, par nature.
    """
    if active_source() == "api":
        return _client_instance().get_stream(cell_id, limit)
    return pd.DataFrame()


def get_stream_info() -> dict:
    """Fréquence d'émission et modalités de polling (GET /kpi/stream/info).

    Retourne un dictionnaire vide si l'API est indisponible : le dashboard se
    rabat alors sur un intervalle de rafraîchissement par défaut.
    """
    if active_source() != "api":
        return {}
    try:
        return _client_instance().get_stream_info()
    except (ApiUnavailable, KeyError):
        return {}


# ==================================================================
# Métadonnées
# ==================================================================
def list_cells() -> list[str]:
    if active_source() == "api":
        return _client_instance().get_cells()
    return local_source.list_cells()


def get_thresholds() -> dict[str, dict]:
    """Seuils QoS. L'API est la source de vérité ; repli sur la copie du contrat."""
    if active_source() == "api":
        try:
            return _client_instance().get_thresholds()
        except (ApiUnavailable, KeyError):
            pass
    return local_source.get_thresholds()


# ==================================================================
# Utilitaires
# ==================================================================
def _filter(
    df: pd.DataFrame,
    cell_id: Optional[str],
    start: Optional[str],
    end: Optional[str],
) -> pd.DataFrame:
    """Applique côté client les filtres que l'API applique côté serveur."""
    if df.empty:
        return df
    if cell_id is not None:
        if cell_id not in set(df["cell_id"]):
            raise KeyError(f"La cellule '{cell_id}' n'existe pas.")
        df = df[df["cell_id"] == cell_id]
    if start is not None:
        df = df[df["ts"] >= pd.Timestamp(start, tz="UTC")]
    if end is not None:
        df = df[df["ts"] <= pd.Timestamp(end, tz="UTC")]
    return df.reset_index(drop=True)
