"""
Client de l'API REST du Binôme A (contrat d'interface v1.1).

Unique point de contact entre le Binôme B et le Binôme A : aucun autre module
du Binôme B n'accède à la base de données ni n'importe de code de `binome-a/`.

Responsabilités :
  - respecter l'enveloppe de réponse commune (`count`, `data`, `total`, `has_more`) ;
  - dérouler automatiquement la pagination `limit`/`offset` ;
  - retenter les erreurs réseau transitoires ;
  - convertir les réponses JSON en DataFrame typé (ts en datetime UTC).

Usage :
    from src.data.api_client import ApiClient
    client = ApiClient()
    if client.is_available():
        df = client.get_features(cell_id="cell_001")
"""

from __future__ import annotations

import time
from typing import Any, Optional

import pandas as pd
import requests

from src.config import (
    API_BASE_URL,
    API_HEALTH_TIMEOUT_SECONDS,
    API_MAX_RETRIES,
    API_PAGE_LIMIT,
    API_TIMEOUT_SECONDS,
)


class ApiUnavailable(RuntimeError):
    """L'API du Binôme A n'est pas joignable ou renvoie une erreur serveur."""


class ApiClient:
    """Client HTTP synchrone de l'API du Binôme A."""

    def __init__(
        self,
        base_url: str = API_BASE_URL,
        timeout: float = API_TIMEOUT_SECONDS,
        health_timeout: float = API_HEALTH_TIMEOUT_SECONDS,
        max_retries: int = API_MAX_RETRIES,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.health_timeout = health_timeout
        self.max_retries = max_retries
        self._session = requests.Session()

    # --------------------------------------------------------------
    # Transport
    # --------------------------------------------------------------
    def _get(
        self, path: str, params: Optional[dict] = None, timeout: Optional[float] = None
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        params = {k: v for k, v in (params or {}).items() if v is not None}
        timeout = self.timeout if timeout is None else timeout

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._session.get(url, params=params, timeout=timeout)
            except requests.RequestException as exc:
                last_error = exc
            else:
                # 404 sur cellule inconnue : erreur métier documentée, pas un
                # incident réseau -> on ne retente pas.
                if response.status_code == 404:
                    payload = _safe_json(response)
                    raise KeyError(payload.get("message", f"Ressource absente : {url}"))
                if response.status_code < 500:
                    response.raise_for_status()
                    return _safe_json(response)
                last_error = ApiUnavailable(
                    f"HTTP {response.status_code} sur {url} : {response.text[:200]}"
                )

            if attempt < self.max_retries:
                time.sleep(0.5 * (attempt + 1))

        raise ApiUnavailable(f"Échec de l'appel à {url} : {last_error}")

    def _get_paginated(self, path: str, params: Optional[dict] = None) -> list[dict]:
        """Déroule la pagination `limit`/`offset` jusqu'à épuisement des données.

        Deux stratégies d'arrêt, parce que l'API v1.1 n'est pas homogène :

        - **`has_more` présent** (`/kpi/history`, `/features`) : on s'y fie.
        - **`has_more` absent** (`/eval/labels`) : cet endpoint accepte pourtant
          `limit` et `offset`, mais son enveloppe omet `limit`/`offset`/`total`/
          `has_more`, contrairement à ce que documente le contrat. Se fier à
          `has_more` seul faisait donc s'arrêter la lecture après une seule page —
          5 000 étiquettes récupérées sur 100 800, en silence. On se rabat sur
          l'heuristique « continuer tant que la page est pleine ».

        Correction demandée au Binôme A : aligner l'enveloppe de `/eval/labels`
        sur celle des autres endpoints paginés.
        """
        params = dict(params or {})
        params.setdefault("limit", API_PAGE_LIMIT)
        page_size = int(params["limit"])
        offset = int(params.get("offset", 0))
        rows: list[dict] = []

        while True:
            params["offset"] = offset
            payload = self._get(path, params)
            page = payload.get("data", [])
            rows.extend(page)

            if not page:
                break

            if "has_more" in payload:
                if not payload["has_more"]:
                    break
            elif len(page) < page_size:
                # Page incomplète : c'est la dernière.
                break

            offset += len(page)

        return rows

    # --------------------------------------------------------------
    # Disponibilité
    # --------------------------------------------------------------
    def is_available(self) -> bool:
        """True si GET /health répond. Ne lève jamais.

        Utilise le délai court : c'est cet appel qui décide du repli sur la
        source locale, et il ne doit pas faire patienter l'utilisateur.
        """
        try:
            payload = self._get("health", timeout=self.health_timeout)
        except Exception:
            return False
        return payload.get("status") == "ok"

    # --------------------------------------------------------------
    # Métadonnées
    # --------------------------------------------------------------
    def get_cells(self) -> list[str]:
        return list(self._get("cells").get("data", []))

    def get_thresholds(self) -> dict[str, dict]:
        return self._get("thresholds").get("data", {})

    def get_stream_info(self) -> dict:
        return self._get("kpi/stream/info")

    # --------------------------------------------------------------
    # Données
    # --------------------------------------------------------------
    def get_kpi_history(
        self,
        cell_id: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """Historique NETTOYÉ (clean_kpi_measurements), `is_anomaly` exclu par contrat."""
        rows = self._get_paginated(
            "kpi/history", {"cell_id": cell_id, "from": start, "to": end}
        )
        return _to_frame(rows)

    def get_features(
        self,
        cell_id: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """Features pré-calculées par le Binôme A (kpi_features)."""
        rows = self._get_paginated(
            "features", {"cell_id": cell_id, "from": start, "to": end}
        )
        return _to_frame(rows)

    def get_latest(self, cell_id: Optional[str] = None, n: int = 100) -> pd.DataFrame:
        payload = self._get("kpi/latest", {"cell_id": cell_id, "n": n})
        return _to_frame(payload.get("data", []))

    def get_stream(self, cell_id: Optional[str] = None, limit: int = 50) -> pd.DataFrame:
        payload = self._get("kpi/stream", {"cell_id": cell_id, "limit": limit})
        return _to_frame(payload.get("data", []))

    # --------------------------------------------------------------
    # Évaluation
    # --------------------------------------------------------------
    def get_eval_labels(
        self,
        cell_id: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """Vérité terrain `is_anomaly`.

        ATTENTION : réservée au calcul des métriques (précision/rappel/F1).
        Ne jamais joindre ces colonnes aux features d'entraînement.
        """
        rows = self._get_paginated(
            "eval/labels", {"cell_id": cell_id, "from": start, "to": end}
        )
        return _to_frame(rows)


# ------------------------------------------------------------------
# Utilitaires
# ------------------------------------------------------------------
def _safe_json(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ApiUnavailable(f"Réponse non-JSON : {response.text[:200]}") from exc
    if not isinstance(payload, dict):
        raise ApiUnavailable(f"Enveloppe de réponse inattendue : {type(payload)}")
    return payload


def _to_frame(rows: list[dict]) -> pd.DataFrame:
    """Convertit les enregistrements JSON en DataFrame trié, `ts` en UTC."""
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in ("ts", "ingested_at"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, format="mixed")
    sort_cols = [c for c in ("cell_id", "ts") if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)
    return df
