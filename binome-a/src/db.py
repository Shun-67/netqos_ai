"""Connexion partagée à TimescaleDB (utilisée par l'ingestion, la préparation et l'API)."""

import os
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert as pg_insert

DB_USER = os.getenv("POSTGRES_USER", "netqos")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "netqos")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "netqos")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def get_engine():
    return create_engine(DATABASE_URL, pool_pre_ping=True)


def upsert_on_conflict(table, conn, keys, data_iter):
    """
    Fonction utilisée par pandas.to_sql(method=...).
    Insère les lignes ; en cas de doublon sur la clé primaire (ts, cell_id),
    met à jour les valeurs existantes au lieu de lever une erreur.
    Utilisée par clean_prepare.py et build_features.py.
    """
    data = [dict(zip(keys, row)) for row in data_iter]
    stmt = pg_insert(table.table).values(data)
    update_cols = {c: stmt.excluded[c] for c in keys if c not in ("ts", "cell_id")}
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts", "cell_id"],
        set_=update_cols,
    )
    conn.execute(stmt)