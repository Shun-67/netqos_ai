"""
Simulateur de flux temps quasi-réel : génère et insère une nouvelle mesure
par cellule toutes les `interval-seconds` secondes, en continu.

Réutilise la logique du générateur synthétique (une valeur à la fois) pour
rester cohérent avec les données batch.

Usage:
    python -m src.ingestion.stream_simulator --cells 5 --interval-seconds 5
"""

import argparse
import sys
import time
import numpy as np
import pandas as pd
from datetime import datetime, timezone

sys.path.append(".")
from src.db import get_engine

RNG = np.random.default_rng()


def next_point(cell_id: str, hour: float) -> dict:
    load_factor = 0.3 + 0.7 * (0.5 + 0.5 * np.sin((hour - 7) / 24 * 2 * np.pi))
    is_anomaly = bool(RNG.random() < 0.01)  # 1% de chance d'anomalie ponctuelle

    throughput = max(0, RNG.normal(110 * (1.3 - 0.6 * load_factor), 5))
    latency = max(0, RNG.normal(15 * (0.7 + 0.6 * load_factor), 2))
    jitter = max(0, RNG.normal(2 * (0.7 + 0.8 * load_factor), 0.4))
    packet_loss = float(np.clip(RNG.normal(0.4, 0.3) + 0.5 * load_factor, 0, 100))
    cell_load = float(np.clip(load_factor * 100 + RNG.normal(0, 5), 0, 100))

    if is_anomaly:
        throughput *= RNG.uniform(0.1, 0.4)
        latency *= RNG.uniform(3, 8)
        packet_loss = float(np.clip(packet_loss + RNG.uniform(20, 60), 0, 100))

    return dict(
        ts=datetime.now(timezone.utc),
        cell_id=cell_id,
        throughput=round(throughput, 2),
        latency=round(latency, 2),
        jitter=round(jitter, 2),
        packet_loss=round(packet_loss, 2),
        cell_load=round(cell_load, 2),
        is_anomaly=is_anomaly,
        source="stream",
        ingested_at=datetime.now(timezone.utc),
    )


def run(n_cells: int, interval_seconds: int):
    engine = get_engine()
    cell_ids = [f"cell_{i+1:03d}" for i in range(n_cells)]
    print(f"Démarrage du flux simulé pour {n_cells} cellules "
          f"(intervalle {interval_seconds}s). Ctrl+C pour arrêter.")
    try:
        while True:
            now = datetime.now(timezone.utc)
            hour = now.hour + now.minute / 60
            rows = [next_point(cid, hour) for cid in cell_ids]
            df = pd.DataFrame(rows)
            with engine.begin() as conn:
                df.to_sql("raw_kpi_measurements", conn, if_exists="append", index=False)
            print(f"[{now.isoformat()}] {len(rows)} points insérés")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("Arrêt du flux simulé.")


def main():
    parser = argparse.ArgumentParser(description="Simulateur de flux KPI réseau")
    parser.add_argument("--cells", type=int, default=5)
    parser.add_argument("--interval-seconds", type=int, default=5)
    args = parser.parse_args()
    run(args.cells, args.interval_seconds)


if __name__ == "__main__":
    main()
