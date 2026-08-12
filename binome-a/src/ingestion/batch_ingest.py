"""
Ingestion batch : charge un fichier CSV (données historiques générées ou
téléchargées) dans la table `raw_kpi_measurements` de TimescaleDB.

Usage:
    python -m src.ingestion.batch_ingest --file data/raw/historical_kpi.csv
"""

import argparse
import sys
import pandas as pd
from sqlalchemy import text

sys.path.append(".")
from src.db import get_engine


REQUIRED_COLUMNS = [
    "ts", "cell_id", "throughput", "latency", "jitter",
    "packet_loss", "cell_load", "is_anomaly",
]


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["ts"])
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes dans {path}: {missing}")
    if "source" not in df.columns:
        df["source"] = "batch"
    if "ingested_at" not in df.columns:
        df["ingested_at"] = pd.Timestamp.utcnow()
    return df


def ingest(df: pd.DataFrame, chunksize: int = 5000) -> int:
    engine = get_engine()
    cols = REQUIRED_COLUMNS + ["source", "ingested_at"]
    with engine.begin() as conn:
        df[cols].to_sql(
            "raw_kpi_measurements",
            conn,
            if_exists="append",
            index=False,
            chunksize=chunksize,
            method="multi",
        )
    return len(df)


def main():
    parser = argparse.ArgumentParser(description="Ingestion batch des KPI réseau")
    parser.add_argument("--file", type=str, required=True, help="Chemin du CSV à ingérer")
    args = parser.parse_args()

    df = load_csv(args.file)
    n = ingest(df)
    print(f"{n} lignes ingérées depuis {args.file} dans raw_kpi_measurements")


if __name__ == "__main__":
    main()
