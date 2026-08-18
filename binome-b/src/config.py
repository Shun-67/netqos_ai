"""
Configuration centrale du Binôme B.

Regroupe les chemins, les constantes du contrat d'interface v1.1 et les
paramètres lus depuis l'environnement, afin qu'aucun module métier ne
code en dur un chemin ou une URL.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ------------------------------------------------------------------
# Chemins
# ------------------------------------------------------------------
BINOME_B_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BINOME_B_DIR.parent

load_dotenv(REPO_ROOT / ".env")

SAMPLES_DIR = BINOME_B_DIR / "data" / "samples"
MODELS_DIR = BINOME_B_DIR / "src" / "models" / "saved"
REPORTS_DIR = REPO_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"
METRICS_DIR = REPORTS_DIR / "metrics"

# Données brutes produites par le générateur du Binôme A. Utilisées uniquement
# en mode de repli local, quand l'API n'est pas encore joignable.
BINOME_A_RAW_DIR = REPO_ROOT / "binome-a" / "data" / "raw"

for _d in (SAMPLES_DIR, MODELS_DIR, REPORTS_DIR, FIGURES_DIR, METRICS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------
# Source de données
# ------------------------------------------------------------------
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

# api   : exige l'API du Binôme A (échoue si indisponible)
# local : force la lecture des CSV locaux
# auto  : tente l'API, retombe sur les CSV locaux si elle ne répond pas
DATA_SOURCE = os.getenv("NETQOS_DATA_SOURCE", "auto").lower()

# Deux délais distincts, mesurés sur la stack réelle :
#   - les endpoints de données renvoient des pages volumineuses. Une page de
#     10 000 lignes de /features pèse ~13,7 Mo et met ~12 s à être servie : un
#     délai unique de 10 s faisait échouer le chargement du dashboard.
#   - la sonde /health doit au contraire échouer vite, puisque c'est elle qui
#     décide de basculer sur la source locale. Un délai long ferait attendre
#     l'utilisateur devant une page vide avant le repli.
API_TIMEOUT_SECONDS = float(os.getenv("NETQOS_API_TIMEOUT", "120"))
API_HEALTH_TIMEOUT_SECONDS = float(os.getenv("NETQOS_API_HEALTH_TIMEOUT", "5"))
API_MAX_RETRIES = int(os.getenv("NETQOS_API_RETRIES", "2"))

# Taille de page. Le contrat autorise 10 000 (MAX_PAGE_LIMIT côté A), mais des
# pages de 5 000 lignes divisent par deux l'empreinte mémoire et le temps de
# première réponse, pour un nombre d'allers-retours qui reste faible.
API_PAGE_LIMIT = int(os.getenv("NETQOS_API_PAGE_LIMIT", "5000"))

# ------------------------------------------------------------------
# Contrat d'interface v1.1 (figé le 2026-08-10)
# ------------------------------------------------------------------
KPIS = ["throughput", "latency", "jitter", "packet_loss", "cell_load"]

KPI_UNITS = {
    "throughput": "Mbit/s",
    "latency": "ms",
    "jitter": "ms",
    "packet_loss": "%",
    "cell_load": "%",
}

# Sens de dégradation : True si une valeur haute est mauvaise.
KPI_HIGHER_IS_WORSE = {
    "throughput": False,
    "latency": True,
    "jitter": True,
    "packet_loss": True,
    "cell_load": True,
}

# Copie locale des seuils de GET /api/v1/thresholds. Sert de repli lorsque
# l'API est indisponible ; l'API reste la source de vérité quand elle répond.
THRESHOLDS_FALLBACK = {
    "throughput": {"unit": "Mbit/s", "good_min": 107, "degraded_min": 77},
    "latency": {"unit": "ms", "good_max": 20, "degraded_max": 50},
    "jitter": {"unit": "ms", "good_max": 4.0, "degraded_max": 5.1},
    "packet_loss": {"unit": "%", "good_max": 0.5, "degraded_max": 0.9},
    "cell_load": {"unit": "%", "good_max": 70, "degraded_max": 90},
}
CONTRACT_VERSION = "1.1"

# Granularité des données nettoyées (1 point / minute, cf. data_dictionary.md).
RESAMPLE_FREQ = "1min"
POINTS_PER_HOUR = 60

# ------------------------------------------------------------------
# Protocole d'évaluation
# ------------------------------------------------------------------
# Découpage strictement chronologique (aucun mélange de timestamps).
TRAIN_RATIO = 0.60
VAL_RATIO = 0.20
TEST_RATIO = 0.20

# Horizons de prévision, en minutes.
FORECAST_HORIZONS = [5, 15, 30]

RANDOM_STATE = 42
