# data/samples — Données de développement local

Fichiers CSV générés par le `synthetic_generator.py` du Binôme A.
**Usage : développement et prototypage local uniquement.**

| Fichier | Contenu |
|---------|---------|
| `sample_kpi.csv` | KPI bruts — structure identique à `/api/v1/kpi/history` |
| `sample_kpi_with_labels.csv` | KPI bruts + `is_anomaly` (vérité terrain) |
| `sample_features.csv` | Features pré-calculées — identique à `/api/v1/features` |

## ⚠️ Important

`sample_kpi_with_labels.csv` contient `is_anomaly`.
**Ce champ n'existe PAS dans `/api/v1/kpi/history`** — il est uniquement accessible via `/api/v1/eval/labels` en phase d'évaluation.

## Régénérer les fichiers

```bash
python binome-a/src/generator/synthetic_generator.py \
    --cells 2 --days 1 \
    --out binome-b/data/samples/sample_kpi_with_labels.csv
```
