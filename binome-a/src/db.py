"""Connexion partagée à TimescaleDB (utilisée par l'ingestion, la préparation et l'API)."""

import os
from sqlalchemy import create_engine

DB_USER = os.getenv("POSTGRES_USER", "netqos")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "netqos")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "netqos")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def get_engine():
    return create_engine(DATABASE_URL, pool_pre_ping=True)
