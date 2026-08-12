"""
DAG Airflow — orchestration du pipeline NetQoS-AI (Binôme A).

Remplace le script simple `run_pipeline.py` (semaine 2) pour le jalon
orchestration (semaine 3, J15-J21) : rafraîchissement périodique automatisé,
reprise sur erreur, historique d'exécution visible dans l'UI Airflow.

Enchaînement : clean_prepare (nettoyage) -> build_features (features).

Le code source du pipeline (src/preparation/*) n'est PAS dupliqué ici :
le DAG importe et appelle directement les fonctions déjà écrites et testées
dans src/preparation/clean_prepare.py et build_features.py.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

# Le conteneur Airflow monte binome-a/ sur /opt/airflow/binome-a (voir
# docker-compose.yml), qui est ajouté au PYTHONPATH -> ces imports fonctionnent
# exactement comme en local.
from src.preparation.clean_prepare import clean_and_prepare
from src.preparation.build_features import build_features


default_args = {
    "owner": "binome-a",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="netqos_pipeline",
    description="Nettoyage + calcul des features NetQoS-AI (Binôme A)",
    default_args=default_args,
    start_date=datetime(2026, 8, 1),
    schedule_interval=timedelta(minutes=15),  # rafraîchissement périodique
    catchup=False,
    tags=["netqos-ai", "binome-a"],
) as dag:

    def _run_clean_prepare(**context):
        """Nettoie les nouvelles données brutes ingérées depuis la dernière exécution."""
        result = clean_and_prepare()
        n_rows = 0 if result is None or result.empty else len(result)
        print(f"[clean_prepare] {n_rows} lignes nettoyées")

    def _run_build_features(**context):
        """Calcule les features à partir des données nettoyées."""
        result = build_features()
        n_rows = 0 if result is None or result.empty else len(result)
        print(f"[build_features] {n_rows} lignes de features générées")

    task_clean = PythonOperator(
        task_id="clean_prepare",
        python_callable=_run_clean_prepare,
    )

    task_features = PythonOperator(
        task_id="build_features",
        python_callable=_run_build_features,
    )

    task_clean >> task_features
