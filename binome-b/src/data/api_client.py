"""
Client pour l'API REST du Binôme A.
Consomme les endpoints définis dans le contrat d'interface.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

def get_kpi_history(cell_id, from_ts, to_ts, limit=10000, offset=0):
    params = {"cell_id": cell_id, "from": from_ts, "to": to_ts, "limit": limit, "offset": offset}
    r = requests.get(f"{API_BASE_URL}/kpi/history", params=params)
    r.raise_for_status()
    return r.json()

def get_features(cell_id, from_ts, to_ts, limit=10000, offset=0):
    params = {"cell_id": cell_id, "from": from_ts, "to": to_ts, "limit": limit, "offset": offset}
    r = requests.get(f"{API_BASE_URL}/features", params=params)
    r.raise_for_status()
    return r.json()

def get_latest(cell_id, n=100):
    r = requests.get(f"{API_BASE_URL}/kpi/latest", params={"cell_id": cell_id, "n": n})
    r.raise_for_status()
    return r.json()

def get_cells():
    r = requests.get(f"{API_BASE_URL}/cells")
    r.raise_for_status()
    return r.json()

def get_thresholds():
    r = requests.get(f"{API_BASE_URL}/thresholds")
    r.raise_for_status()
    return r.json()

def get_eval_labels(cell_id, from_ts, to_ts):
    """Vérité terrain — évaluation uniquement, jamais en entraînement."""
    params = {"cell_id": cell_id, "from": from_ts, "to": to_ts}
    r = requests.get(f"{API_BASE_URL}/eval/labels", params=params)
    r.raise_for_status()
    return r.json()
