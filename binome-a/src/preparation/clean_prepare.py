"""
Nettoyage et préparation : lit `raw_kpi_measurements`, applique les règles
de qualité documentées dans data_dictionary.md, et écrit dans
`clean_kpi_measurements`.

Usage:
    python -m src.preparation.clean_prepare
"""

import sys
import pandas as pd

sys.path.append(".")
from src.db import get_engine, upsert_on_conflict

VALUE_BOUNDS = {
    "throughput": (0, None),
    "latency": (0, None),
    "jitter": (0, None),
    "packet_loss": (0, 100),
    "cell_load": (0, 100),
}

RESAMPLE_FREQ = "1min"  # granularité cible


def load_raw(engine, since: str = None) -> pd.DataFrame:
    query = "SELECT ts, cell_id, throughput, latency, jitter, packet_loss, cell_load FROM raw_kpi_measurements"
    if since:
        query += f" WHERE ts >= '{since}'"
    return pd.read_sql(query, engine, parse_dates=["ts"])


def clip_bounds(df: pd.DataFrame) -> pd.DataFrame:
    for col, (lo, hi) in VALUE_BOUNDS.items():
        df[col] = df[col].clip(lower=lo, upper=hi)
    return df


def clean_cell(df_cell: pd.DataFrame) -> pd.DataFrame:
    df_cell = df_cell.drop_duplicates(subset="ts").set_index("ts").sort_index()
    df_cell = df_cell.resample(RESAMPLE_FREQ).mean(numeric_only=True)

    df_cell["is_missing"] = df_cell["throughput"].isna()

    value_cols = ["throughput", "latency", "jitter", "packet_loss", "cell_load"]
    df_cell[value_cols] = df_cell[value_cols].interpolate(
        method="linear", limit=3, limit_direction="both"
    )
    return df_cell.reset_index()


def clean_and_prepare(since: str = None) -> pd.DataFrame:
    engine = get_engine()
    raw = load_raw(engine, since)
    if raw.empty:
        print("Aucune donnée brute à traiter.")
        return raw

    raw = clip_bounds(raw)

    cleaned_parts = []
    for cell_id, group in raw.groupby("cell_id"):
        cleaned = clean_cell(group.drop(columns="cell_id"))
        cleaned["cell_id"] = cell_id
        cleaned_parts.append(cleaned)

    clean_df = pd.concat(cleaned_parts, ignore_index=True)
    clean_df = clean_df.dropna(subset=["throughput", "latency"])  # gaps trop longs -> supprimés

    cols = ["ts", "cell_id", "throughput", "latency", "jitter", "packet_loss", "cell_load", "is_missing"]
    with engine.begin() as conn:
        clean_df[cols].to_sql(
            "clean_kpi_measurements", conn, if_exists="append", index=False,
            method=upsert_on_conflict, chunksize=5000
        )
    print(f"{len(clean_df)} lignes nettoyées écrites dans clean_kpi_measurements")
    return clean_df


if __name__ == "__main__":
    clean_and_prepare()