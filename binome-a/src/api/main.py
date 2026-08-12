"""
API REST NetQoS-AI (Binôme A) — expose les données nettoyées et les features
au Binôme B et au tableau de bord, selon le contrat d'interface v1.1
(intègre le retour du Binôme B du 06/08/2026 : pagination, is_missing,
endpoint dédié pour la vérité terrain, fréquence du flux documentée).

Lancer en local :
    uvicorn src.api.main:app --reload --port 8000

Documentation interactive générée automatiquement : http://localhost:8000/docs
"""

import sys
from datetime import datetime
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

sys.path.append(".")
from src.db import get_engine

app = FastAPI(
    title="NetQoS-AI API — Binôme A",
    description="Expose les KPI réseau nettoyés et les features temporelles, "
                 "selon le contrat d'interface v1.1.",
    version="1.1.0",
)

API_PREFIX = "/api/v1"
KPIS = ["throughput", "latency", "jitter", "packet_loss", "cell_load"]

# Fréquence d'émission du flux simulé (point 2.1 du retour Binôme B).
# Doit rester cohérente avec --interval-seconds de stream_simulator.py.
STREAM_INTERVAL_SECONDS = 5
STREAM_POLLING_RECOMMENDATION = (
    "Endpoint interrogé par polling HTTP classique (pas de connexion persistante, "
    "donc pas de timeout de session à gérer). Fréquence d'émission des nouvelles "
    f"mesures côté serveur : toutes les {STREAM_INTERVAL_SECONDS} secondes. "
    "Polling recommandé côté dashboard à la même fréquence."
)

DEFAULT_PAGE_LIMIT = 10000
MAX_PAGE_LIMIT = 10000


# ============================================================
# Modèles de réponse
# ============================================================
class HealthResponse(BaseModel):
    status: str
    time: datetime


# ============================================================
# Utilitaires
# ============================================================
def _cell_exists(engine, cell_id: str) -> bool:
    query = "SELECT 1 FROM clean_kpi_measurements WHERE cell_id = %(cell_id)s LIMIT 1"
    df = pd.read_sql(query, engine, params={"cell_id": cell_id})
    return not df.empty


def _error(status_code: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": error, "message": message})


def _build_where(cell_id: Optional[str], start: Optional[datetime], end: Optional[datetime]):
    conditions = []
    params = {}
    if cell_id:
        conditions.append("cell_id = %(cell_id)s")
        params["cell_id"] = cell_id
    if start:
        conditions.append("ts >= %(start)s")
        params["start"] = start
    if end:
        conditions.append("ts <= %(end)s")
        params["end"] = end
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where_clause, params


def _query_page(table: str, cell_id: Optional[str], start: Optional[datetime],
                 end: Optional[datetime], limit: int, offset: int,
                 order: str = "ASC") -> tuple[pd.DataFrame, int]:
    """Retourne (page_de_donnees, total_disponible) pour une requête paginée."""
    engine = get_engine()
    where_clause, params = _build_where(cell_id, start, end)

    count_query = f"SELECT COUNT(*) AS n FROM {table} {where_clause}"
    try:
        total = int(pd.read_sql(count_query, engine, params=params)["n"].iloc[0])
        query = (
            f"SELECT * FROM {table} {where_clause} "
            f"ORDER BY ts {order} LIMIT {int(limit)} OFFSET {int(offset)}"
        )
        df = pd.read_sql(query, engine, params=params)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return df, total


def _df_to_records(df: pd.DataFrame, drop_cols=("is_anomaly",)) -> list:
    """Convertit un DataFrame en liste de dicts, en retirant les colonnes sensibles
    (is_anomaly par défaut) et en formatant les timestamps en ISO 8601."""
    if df.empty:
        return []
    df = df.drop(columns=[c for c in drop_cols if c in df.columns])
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return df.to_dict(orient="records")


# ============================================================
# Monitoring
# ============================================================
@app.get(f"{API_PREFIX}/health", response_model=HealthResponse, tags=["Monitoring"])
def health():
    return HealthResponse(status="ok", time=datetime.utcnow())


# ============================================================
# Métadonnées
# ============================================================
@app.get(f"{API_PREFIX}/cells", tags=["Métadonnées"])
def list_cells():
    engine = get_engine()
    df = pd.read_sql("SELECT DISTINCT cell_id FROM clean_kpi_measurements ORDER BY cell_id", engine)
    cells = df["cell_id"].tolist()
    return {"count": len(cells), "data": cells}


@app.get(f"{API_PREFIX}/thresholds", tags=["Métadonnées"])
def get_thresholds():
    # Seuils FIGÉS — contrat d'interface v1.1, validé et signé le 10/08/2026
    # (jalon J7). latency et cell_load inchangés (distribution déjà équilibrée) ;
    # throughput, jitter, packet_loss recalculés sur les percentiles réels
    # des données générées pour une distribution cible bon/dégradé/critique.
    return {
        "data": {
            "throughput":  {"unit": "Mbit/s", "good_min": 107, "degraded_min": 77},
            "latency":     {"unit": "ms", "good_max": 20, "degraded_max": 50},
            "jitter":      {"unit": "ms", "good_max": 4.0, "degraded_max": 5.1},
            "packet_loss": {"unit": "%", "good_max": 0.5, "degraded_max": 0.9},
            "cell_load":   {"unit": "%", "good_max": 70, "degraded_max": 90},
        },
        "contract_version": "1.1",
        "frozen_at": "2026-08-10",
    }


# ============================================================
# Données (paginées : limit + offset)
# ============================================================
@app.get(f"{API_PREFIX}/kpi/history", tags=["Données"])
def get_kpi_history(
    cell_id: Optional[str] = None,
    from_: Optional[datetime] = Query(default=None, alias="from"),
    to: Optional[datetime] = None,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
):
    """Historique pour l'entraînement — sert les données NETTOYÉES
    (table clean_kpi_measurements), incluant is_missing."""
    engine = get_engine()
    if cell_id and not _cell_exists(engine, cell_id):
        return _error(404, "cell_not_found", f"La cellule '{cell_id}' n'existe pas.")

    df, total = _query_page("clean_kpi_measurements", cell_id, from_, to, limit, offset, order="ASC")
    data = _df_to_records(df)
    return {
        "cell_id": cell_id,
        "from": from_.isoformat() if from_ else None,
        "to": to.isoformat() if to else None,
        "limit": limit,
        "offset": offset,
        "total": total,
        "has_more": offset + len(data) < total,
        "count": len(data),
        "data": data,
    }


@app.get(f"{API_PREFIX}/features", tags=["Données"])
def get_features(
    cell_id: Optional[str] = None,
    from_: Optional[datetime] = Query(default=None, alias="from"),
    to: Optional[datetime] = None,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
):
    engine = get_engine()
    if cell_id and not _cell_exists(engine, cell_id):
        return _error(404, "cell_not_found", f"La cellule '{cell_id}' n'existe pas.")

    df, total = _query_page("kpi_features", cell_id, from_, to, limit, offset, order="ASC")
    data = _df_to_records(df)
    return {
        "cell_id": cell_id,
        "from": from_.isoformat() if from_ else None,
        "to": to.isoformat() if to else None,
        "limit": limit,
        "offset": offset,
        "total": total,
        "has_more": offset + len(data) < total,
        "count": len(data),
        "data": data,
    }


@app.get(f"{API_PREFIX}/kpi/latest", tags=["Données"])
def get_kpi_latest(
    cell_id: Optional[str] = None,
    n: int = Query(default=100, le=10000),
):
    engine = get_engine()
    if cell_id and not _cell_exists(engine, cell_id):
        return _error(404, "cell_not_found", f"La cellule '{cell_id}' n'existe pas.")

    df, _ = _query_page("clean_kpi_measurements", cell_id, None, None, n, 0, order="DESC")
    data = _df_to_records(df)
    return {"cell_id": cell_id, "n": n, "count": len(data), "data": data}


# ============================================================
# Flux temps réel
# ============================================================
@app.get(f"{API_PREFIX}/kpi/stream", tags=["Flux temps réel"])
def get_kpi_stream(
    cell_id: Optional[str] = None,
    limit: int = Query(default=50, le=1000),
):
    """Fréquence d'émission et modalités de polling : voir /api/v1/kpi/stream/info."""
    engine = get_engine()
    if cell_id and not _cell_exists(engine, cell_id):
        return _error(404, "cell_not_found", f"La cellule '{cell_id}' n'existe pas.")

    conditions = ["source = 'stream'"]
    params = {}
    if cell_id:
        conditions.append("cell_id = %(cell_id)s")
        params["cell_id"] = cell_id
    where_clause = "WHERE " + " AND ".join(conditions)
    query = f"SELECT * FROM raw_kpi_measurements {where_clause} ORDER BY ts DESC LIMIT {int(limit)}"
    df = pd.read_sql(query, engine, params=params)
    data = _df_to_records(df)
    return {"cell_id": cell_id, "data": data}


@app.get(f"{API_PREFIX}/kpi/stream/info", tags=["Flux temps réel"])
def get_kpi_stream_info():
    """Réponse au point 2.1 / 2.2 du retour Binôme B : fréquence et modalités."""
    return {
        "emission_interval_seconds": STREAM_INTERVAL_SECONDS,
        "recommended_polling_interval_seconds": STREAM_INTERVAL_SECONDS,
        "connection_type": "http_polling",
        "session_timeout": None,
        "notes": STREAM_POLLING_RECOMMENDATION,
    }


# ============================================================
# Évaluation (vérité terrain — jamais mélangée aux endpoints d'entraînement)
# ============================================================
@app.get(f"{API_PREFIX}/eval/labels", tags=["Évaluation"])
def get_eval_labels(
    cell_id: Optional[str] = None,
    from_: Optional[datetime] = Query(default=None, alias="from"),
    to: Optional[datetime] = None,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
):
    """Réponse au point 1.4 du retour Binôme B : vérité terrain (is_anomaly),
    exposée uniquement ici, jamais dans /kpi/history ni /features.
    À utiliser exclusivement pour l'évaluation (précision/rappel/F1),
    jamais comme feature d'entraînement."""
    engine = get_engine()
    if cell_id and not _cell_exists(engine, cell_id):
        return _error(404, "cell_not_found", f"La cellule '{cell_id}' n'existe pas.")

    where_clause, params = _build_where(cell_id, from_, to)
    query = f"""
        SELECT ts, cell_id, is_anomaly FROM raw_kpi_measurements
        {where_clause}
        ORDER BY ts ASC LIMIT {int(limit)} OFFSET {int(offset)}
    """
    df = pd.read_sql(query, engine, params=params)
    data = _df_to_records(df, drop_cols=())  # ici on garde is_anomaly, c'est le but de l'endpoint
    return {
        "cell_id": cell_id,
        "from": from_.isoformat() if from_ else None,
        "to": to.isoformat() if to else None,
        "count": len(data),
        "data": data,
        "usage": "Évaluation uniquement (précision/rappel/F1) — ne jamais utiliser en entraînement.",
    }
