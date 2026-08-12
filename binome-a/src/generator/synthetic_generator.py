"""
Générateur de données synthétiques de KPI réseau (NetQoS-AI - Binôme A).

Simule plusieurs cellules réseau sur une période donnée, avec :
- une saisonnalité journalière (charge plus forte en journée)
- du bruit réaliste
- des anomalies injectées de façon contrôlée (pannes, congestion, dégradation progressive)

La colonne `is_anomaly` constitue la vérité terrain, réservée à l'évaluation
du Binôme B — elle ne doit jamais être utilisée comme feature d'entraînement.

Usage:
    python synthetic_generator.py --cells 5 --days 14 --out data/raw/historical_kpi.csv
"""

import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone


def daily_seasonality(hour: np.ndarray) -> np.ndarray:
    """Facteur de charge entre 0.3 (nuit) et 1.0 (heures de pointe ~19h)."""
    return 0.3 + 0.7 * (0.5 + 0.5 * np.sin((hour - 7) / 24 * 2 * np.pi))


def generate_cell_series(cell_id: str, start: datetime, n_points: int,
                          freq_seconds: int, rng: np.random.Generator) -> pd.DataFrame:
    timestamps = [start + timedelta(seconds=freq_seconds * i) for i in range(n_points)]
    hours = np.array([t.hour + t.minute / 60 for t in timestamps])
    load_factor = daily_seasonality(hours)

    # Baseline "physiques" propres à la cellule (variabilité inter-cellule)
    base_throughput = rng.uniform(80, 150)   # Mbit/s en charge faible
    base_latency = rng.uniform(10, 25)       # ms
    base_jitter = rng.uniform(1, 4)          # ms

    throughput = base_throughput * (1.3 - 0.6 * load_factor) + rng.normal(0, 3, n_points)
    latency = base_latency * (0.7 + 0.6 * load_factor) + rng.normal(0, 1, n_points)
    jitter = base_jitter * (0.7 + 0.8 * load_factor) + rng.normal(0, 0.3, n_points)
    packet_loss = np.clip(rng.normal(0.3, 0.2, n_points) + 0.5 * load_factor, 0, 100)
    cell_load = np.clip(load_factor * 100 + rng.normal(0, 5, n_points), 0, 100)

    is_anomaly = np.zeros(n_points, dtype=bool)

    # --- Injection d'anomalies contrôlées ---
    n_anomaly_events = max(1, n_points // 2000)  # ~1 événement pour 2000 points
    for _ in range(n_anomaly_events):
        anomaly_type = rng.choice(["outage", "congestion", "degradation"])
        start_idx = int(rng.integers(0, max(1, n_points - 60)))

        if anomaly_type == "outage":
            # Chute brutale du débit, latence qui explose, pertes fortes
            duration = int(rng.integers(3, 15))
            end_idx = min(n_points, start_idx + duration)
            throughput[start_idx:end_idx] *= rng.uniform(0.02, 0.15)
            latency[start_idx:end_idx] *= rng.uniform(4, 10)
            packet_loss[start_idx:end_idx] = np.clip(
                packet_loss[start_idx:end_idx] + rng.uniform(30, 80), 0, 100)
            is_anomaly[start_idx:end_idx] = True

        elif anomaly_type == "congestion":
            # Charge cellule saturée, débit qui chute, gigue qui augmente
            duration = int(rng.integers(10, 40))
            end_idx = min(n_points, start_idx + duration)
            cell_load[start_idx:end_idx] = np.clip(
                cell_load[start_idx:end_idx] + rng.uniform(20, 40), 0, 100)
            throughput[start_idx:end_idx] *= rng.uniform(0.3, 0.6)
            jitter[start_idx:end_idx] *= rng.uniform(2, 5)
            is_anomaly[start_idx:end_idx] = True

        else:  # degradation progressive
            duration = int(rng.integers(20, 60))
            end_idx = min(n_points, start_idx + duration)
            ramp = np.linspace(1.0, rng.uniform(2.5, 5), end_idx - start_idx)
            latency[start_idx:end_idx] *= ramp
            packet_loss[start_idx:end_idx] = np.clip(
                packet_loss[start_idx:end_idx] * ramp, 0, 100)
            is_anomaly[start_idx:end_idx] = True

    throughput = np.clip(throughput, 0, None)
    latency = np.clip(latency, 0, None)
    jitter = np.clip(jitter, 0, None)

    df = pd.DataFrame({
        "ts": timestamps,
        "cell_id": cell_id,
        "throughput": np.round(throughput, 2),
        "latency": np.round(latency, 2),
        "jitter": np.round(jitter, 2),
        "packet_loss": np.round(packet_loss, 2),
        "cell_load": np.round(cell_load, 2),
        "is_anomaly": is_anomaly,
    })
    return df


def generate_dataset(n_cells: int, days: int, freq_seconds: int = 60,
                      seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = datetime.now(timezone.utc) - timedelta(days=days)
    n_points = int(days * 24 * 3600 / freq_seconds)

    frames = []
    for i in range(n_cells):
        cell_id = f"cell_{i+1:03d}"
        frames.append(generate_cell_series(cell_id, start, n_points, freq_seconds, rng))

    df = pd.concat(frames, ignore_index=True)
    df["source"] = "batch"
    df["ingested_at"] = datetime.now(timezone.utc)
    return df.sort_values(["cell_id", "ts"]).reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="Générateur synthétique de KPI réseau")
    parser.add_argument("--cells", type=int, default=5, help="Nombre de cellules")
    parser.add_argument("--days", type=int, default=14, help="Nombre de jours d'historique")
    parser.add_argument("--freq-seconds", type=int, default=60, help="Granularité en secondes")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="data/raw/historical_kpi.csv")
    args = parser.parse_args()

    df = generate_dataset(args.cells, args.days, args.freq_seconds, args.seed)
    df.to_csv(args.out, index=False)
    print(f"{len(df)} lignes générées pour {args.cells} cellules sur {args.days} jours "
          f"-> {args.out}")
    print(f"Taux d'anomalies : {df['is_anomaly'].mean():.2%}")


if __name__ == "__main__":
    main()
