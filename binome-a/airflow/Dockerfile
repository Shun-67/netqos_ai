# Image officielle Apache Airflow, enrichie des dépendances nécessaires
# pour que les DAGs puissent importer src.preparation.* et parler à TimescaleDB.
FROM apache/airflow:2.9.3-python3.12

COPY requirements-airflow.txt /requirements-airflow.txt

# IMPORTANT : installation contrainte par le fichier de contraintes officiel
# d'Airflow, pour éviter d'installer une version d'une dépendance (ex :
# SQLAlchemy) incompatible avec le coeur d'Airflow. Sans ça, pip installe la
# dernière version de chaque paquet demandé, ce qui casse Airflow (ex :
# SQLAlchemy 2.0+ incompatible avec le mapping ORM interne d'Airflow 2.9.3,
# qui attend SQLAlchemy 1.4.x).
RUN pip install --no-cache-dir -r /requirements-airflow.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.9.3/constraints-3.12.txt"
