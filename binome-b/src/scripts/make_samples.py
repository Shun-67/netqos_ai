"""
Génération des échantillons de développement de `data/samples/`.

Le README de `data/samples/` décrit trois fichiers, qui n'existaient pas dans le
dépôt. Ce script les produit à partir de la source de données disponible, de
sorte qu'ils soient reproductibles et cohérents avec le contrat v1.1 :

  - `sample_kpi.csv`              — KPI nettoyés, schéma de `/kpi/history`
  - `sample_kpi_with_labels.csv`  — idem + `is_anomaly` (vérité terrain)
  - `sample_features.csv`         — features, schéma de `/features`

Volume réduit (2 cellules × 1 jour) : ces fichiers servent au prototypage et aux
démonstrations hors ligne, **pas à l'entraînement**. L'ordre de recherche de
`local_source.py` les place volontairement en dernier, après l'historique
complet du Binôme A.

Usage (depuis binome-b/) :
    python -m src.scripts.make_samples
    python -m src.scripts.make_samples --cells 3 --days 2
"""

from __future__ import annotations

import argparse

import pandas as pd

from src.config import SAMPLES_DIR
from src.data import local_source


def main() -> None:
    parser = argparse.ArgumentParser(description="Génération des échantillons de développement")
    parser.add_argument("--cells", type=int, default=2, help="Nombre de cellules à conserver")
    parser.add_argument("--days", type=int, default=1, help="Nombre de jours à conserver")
    args = parser.parse_args()

    source = local_source.resolve_raw_file()
    print(f"Source : {source}")

    clean = local_source.build_clean(source)
    features = local_source.build_features(source)
    labels = local_source.build_labels(source)

    cells = sorted(clean["cell_id"].unique())[: args.cells]
    end = clean["ts"].max()
    start = end - pd.Timedelta(days=args.days)

    def slice_frame(df: pd.DataFrame) -> pd.DataFrame:
        return (
            df[(df["cell_id"].isin(cells)) & (df["ts"] >= start) & (df["ts"] <= end)]
            .sort_values(["cell_id", "ts"])
            .reset_index(drop=True)
        )

    clean_sample = slice_frame(clean)
    features_sample = slice_frame(features)
    labels_sample = slice_frame(labels)

    # `sample_kpi.csv` reproduit /kpi/history, qui n'expose PAS is_anomaly.
    clean_sample.to_csv(SAMPLES_DIR / "sample_kpi.csv", index=False)

    # `sample_kpi_with_labels.csv` ajoute la vérité terrain — réservée à
    # l'évaluation, jamais à l'entraînement.
    with_labels = clean_sample.merge(labels_sample, on=["ts", "cell_id"], how="left")
    with_labels["is_anomaly"] = with_labels["is_anomaly"].fillna(False).astype(bool)
    with_labels.to_csv(SAMPLES_DIR / "sample_kpi_with_labels.csv", index=False)

    features_sample.to_csv(SAMPLES_DIR / "sample_features.csv", index=False)

    print(f"\nÉchantillons écrits dans {SAMPLES_DIR} :")
    for name, frame in (
        ("sample_kpi.csv", clean_sample),
        ("sample_kpi_with_labels.csv", with_labels),
        ("sample_features.csv", features_sample),
    ):
        size_kb = (SAMPLES_DIR / name).stat().st_size / 1024
        print(f"  {name:30s} {len(frame):6,} lignes × {frame.shape[1]:2d} colonnes  ({size_kb:.0f} Ko)")
    print(
        f"\nPérimètre : {', '.join(cells)} · {start} -> {end} "
        f"· taux d'anomalie {with_labels['is_anomaly'].mean() * 100:.2f} %"
    )


if __name__ == "__main__":
    main()
