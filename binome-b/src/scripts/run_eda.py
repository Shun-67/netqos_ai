"""
Analyse exploratoire des données (jalon J7 — Binôme B).

Produit les figures dans `reports/figures/eda/`, les tableaux dans
`reports/metrics/` et un rapport de synthèse dans `reports/rapport_eda.md`.

Objectifs de l'analyse, tels que cadrés par la fiche de stage (semaine 1) :
  1. vérifier la conformité des données au contrat d'interface v1.1 ;
  2. caractériser la saisonnalité et les corrélations, pour choisir les modèles ;
  3. vérifier que les seuils QoS figés au J7 produisent une répartition
     bon/dégradé/critique exploitable ;
  4. mesurer la prévalence des anomalies, qui conditionne le choix des métriques.

Usage (depuis binome-b/) :
    python -m src.scripts.run_eda
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")  # rendu fichier, pas de fenêtre interactive

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.config import FIGURES_DIR, KPI_UNITS, KPIS, METRICS_DIR, REPORTS_DIR
from src.data import loader
from src.features.splits import align_labels
from src.models import qos_state

EDA_FIG_DIR = FIGURES_DIR / "eda"
EDA_FIG_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({"figure.dpi": 110, "font.size": 9, "axes.grid": True, "grid.alpha": 0.3})


# ==================================================================
# 1. Chargement
# ==================================================================
def load_all() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    print(f"Source de données : {loader.source_description()}")
    history = loader.load_history()
    labels = loader.load_labels()
    thresholds = loader.get_thresholds()

    history = history.merge(labels, on=["ts", "cell_id"], how="left")
    history["is_anomaly"] = history["is_anomaly"].fillna(False).astype(bool)
    return history, labels, thresholds


# ==================================================================
# 2. Conformité au contrat
# ==================================================================
def check_contract(history: pd.DataFrame, thresholds: dict) -> dict:
    """Contrôles de conformité au contrat d'interface v1.1."""
    issues: list[str] = []

    missing_kpis = [k for k in KPIS if k not in history.columns]
    if missing_kpis:
        issues.append(f"KPI absents du flux servi : {missing_kpis}")

    if "packet_loss" in history:
        out_of_range = ((history["packet_loss"] < 0) | (history["packet_loss"] > 100)).sum()
        if out_of_range:
            issues.append(f"{out_of_range} valeurs de packet_loss hors [0, 100]")
    if "cell_load" in history:
        out_of_range = ((history["cell_load"] < 0) | (history["cell_load"] > 100)).sum()
        if out_of_range:
            issues.append(f"{out_of_range} valeurs de cell_load hors [0, 100]")

    negatives = {k: int((history[k] < 0).sum()) for k in KPIS if k in history}
    if any(negatives.values()):
        issues.append(f"Valeurs négatives détectées : { {k: v for k, v in negatives.items() if v} }")

    # Régularité de la grille temporelle (attendue : 1 point / minute).
    gaps = []
    for cell_id, group in history.groupby("cell_id"):
        deltas = group["ts"].sort_values().diff().dropna()
        irregular = (deltas != pd.Timedelta(minutes=1)).sum()
        if irregular:
            gaps.append(f"{cell_id}: {irregular} intervalles ≠ 60 s")
    if gaps:
        issues.append("Grille temporelle irrégulière — " + " ; ".join(gaps))

    missing_thresholds = [k for k in KPIS if k not in thresholds]
    if missing_thresholds:
        issues.append(f"Seuils absents pour : {missing_thresholds}")

    return {
        "n_lignes": int(len(history)),
        "n_cellules": int(history["cell_id"].nunique()),
        "periode_debut": str(history["ts"].min()),
        "periode_fin": str(history["ts"].max()),
        "duree_jours": round(
            (history["ts"].max() - history["ts"].min()).total_seconds() / 86400, 2
        ),
        "taux_imputation_pct": round(float(history.get("is_missing", pd.Series([False])).mean()) * 100, 4),
        "taux_anomalie_pct": round(float(history["is_anomaly"].mean()) * 100, 4),
        "valeurs_nulles": int(history[KPIS].isna().sum().sum()),
        "anomalies_contrat": issues or ["aucune"],
    }


# ==================================================================
# 3. Statistiques descriptives
# ==================================================================
def descriptive_stats(history: pd.DataFrame) -> pd.DataFrame:
    stats = history[KPIS].describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95, 0.99]).T
    stats["unite"] = [KPI_UNITS[k] for k in stats.index]
    stats["skew"] = [history[k].skew() for k in stats.index]
    return stats.round(3)


def normal_vs_anomaly(history: pd.DataFrame) -> pd.DataFrame:
    """Compare la distribution des KPI en régime normal et en anomalie.

    Sert au cadrage des modèles : un KPI dont la moyenne bouge peu entre les
    deux régimes apportera peu de signal à un détecteur.
    """
    rows = []
    normal = history[~history["is_anomaly"]]
    anomalous = history[history["is_anomaly"]]
    for kpi in KPIS:
        mu_n, mu_a = normal[kpi].mean(), anomalous[kpi].mean()
        sigma_n = normal[kpi].std()
        rows.append(
            {
                "kpi": kpi,
                "unite": KPI_UNITS[kpi],
                "moy_normal": round(mu_n, 3),
                "moy_anomalie": round(mu_a, 3),
                "ecart_relatif_pct": round((mu_a - mu_n) / mu_n * 100, 2) if mu_n else np.nan,
                # Séparabilité : écart des moyennes en nombre d'écarts-types du
                # régime normal. > 1 signale un KPI discriminant.
                "separabilite_sigma": round(abs(mu_a - mu_n) / sigma_n, 3) if sigma_n else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values("separabilite_sigma", ascending=False)


# ==================================================================
# 4. Figures
# ==================================================================
def fig_series(history: pd.DataFrame, cell_id: str) -> None:
    """Séries temporelles d'une cellule, avec les anomalies surlignées."""
    sub = history[history["cell_id"] == cell_id].sort_values("ts")
    # Deux derniers jours : au-delà, le tracé devient illisible.
    sub = sub[sub["ts"] >= sub["ts"].max() - pd.Timedelta(days=2)]

    fig, axes = plt.subplots(len(KPIS), 1, figsize=(11, 11), sharex=True)
    for ax, kpi in zip(axes, KPIS):
        ax.plot(sub["ts"], sub[kpi], lw=0.6, color="#2c6fb5")
        anomalies = sub[sub["is_anomaly"]]
        if not anomalies.empty:
            ax.scatter(
                anomalies["ts"], anomalies[kpi], s=6, color="#d1495b", zorder=3,
                label="anomalie (vérité terrain)",
            )
        ax.set_ylabel(f"{kpi}\n({KPI_UNITS[kpi]})")
        if kpi == KPIS[0]:
            ax.legend(loc="upper right", fontsize=8)
    axes[-1].set_xlabel("Horodatage (UTC)")
    fig.suptitle(f"Séries de KPI — {cell_id} (48 dernières heures)")
    fig.tight_layout()
    fig.savefig(EDA_FIG_DIR / f"series_{cell_id}.png", bbox_inches="tight")
    plt.close(fig)


def fig_distributions(history: pd.DataFrame, thresholds: dict) -> None:
    """Distributions des KPI, seuils contractuels superposés."""
    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    for ax, kpi in zip(axes.ravel(), KPIS):
        ax.hist(history[kpi].dropna(), bins=80, color="#2c6fb5", alpha=0.75)
        bounds = thresholds.get(kpi, {})
        for key, color, style in (
            ("good_max", "#e8a33d", "--"),
            ("degraded_max", "#d1495b", "-"),
            ("good_min", "#e8a33d", "--"),
            ("degraded_min", "#d1495b", "-"),
        ):
            if key in bounds:
                ax.axvline(bounds[key], color=color, ls=style, lw=1.3, label=key)
        ax.set_title(f"{kpi} ({KPI_UNITS[kpi]})")
        ax.set_yscale("log")  # les queues d'anomalie sont rares : échelle log
        ax.legend(fontsize=7)
    axes.ravel()[-1].axis("off")
    fig.suptitle("Distribution des KPI et seuils du contrat v1.1 (ordonnée logarithmique)")
    fig.tight_layout()
    fig.savefig(EDA_FIG_DIR / "distributions.png", bbox_inches="tight")
    plt.close(fig)


def fig_seasonality(history: pd.DataFrame) -> pd.DataFrame:
    """Profil horaire moyen — motive l'usage des encodages cycliques."""
    history = history.copy()
    history["heure"] = history["ts"].dt.hour
    profile = history.groupby("heure")[KPIS].mean()

    fig, axes = plt.subplots(1, len(KPIS), figsize=(16, 3.2))
    for ax, kpi in zip(axes, KPIS):
        ax.plot(profile.index, profile[kpi], marker="o", ms=3, color="#2c6fb5")
        ax.set_title(kpi, fontsize=9)
        ax.set_xlabel("heure UTC")
        ax.set_xticks(range(0, 24, 6))
    axes[0].set_ylabel("moyenne")
    fig.suptitle("Profil journalier moyen des KPI (saisonnalité 24 h)")
    fig.tight_layout()
    fig.savefig(EDA_FIG_DIR / "saisonnalite_horaire.png", bbox_inches="tight")
    plt.close(fig)
    return profile.round(3)


def fig_correlation(history: pd.DataFrame) -> pd.DataFrame:
    corr = history[KPIS].corr()
    fig, ax = plt.subplots(figsize=(5.5, 4.6))
    im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(KPIS)), KPIS, rotation=45, ha="right")
    ax.set_yticks(range(len(KPIS)), KPIS)
    for i in range(len(KPIS)):
        for j in range(len(KPIS)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title("Corrélations entre KPI (Pearson)")
    ax.grid(False)
    fig.tight_layout()
    fig.savefig(EDA_FIG_DIR / "correlations.png", bbox_inches="tight")
    plt.close(fig)
    return corr.round(3)


def fig_autocorrelation(history: pd.DataFrame) -> pd.DataFrame:
    """Autocorrélation des KPI — dimensionne les lags utiles à la prévision."""
    lags = [1, 2, 5, 10, 15, 30, 60, 120, 720, 1440]
    rows = []
    reference_cell = sorted(history["cell_id"].unique())[0]
    sub = history[history["cell_id"] == reference_cell].sort_values("ts")

    for kpi in KPIS:
        series = sub[kpi]
        rows.append({"kpi": kpi, **{f"lag_{lag}min": round(series.autocorr(lag), 3) for lag in lags}})
    acf = pd.DataFrame(rows).set_index("kpi")

    fig, ax = plt.subplots(figsize=(8, 3.8))
    for kpi in KPIS:
        ax.plot(lags, acf.loc[kpi].to_numpy(), marker="o", ms=3, label=kpi)
    ax.set_xscale("log")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("décalage (minutes, échelle log)")
    ax.set_ylabel("autocorrélation")
    ax.set_title(f"Autocorrélation des KPI — {reference_cell}")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(EDA_FIG_DIR / "autocorrelation.png", bbox_inches="tight")
    plt.close(fig)
    return acf


def fig_qos_states(history: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    """Répartition des états QoS — valide l'équilibre des seuils figés au J7."""
    labelled = qos_state.classify_frame(history, thresholds)
    per_cell = (
        labelled.groupby(["cell_id", "qos_state"], observed=False)
        .size()
        .unstack(fill_value=0)
        .reindex(columns=qos_state.STATES, fill_value=0)
    )
    per_cell_pct = per_cell.div(per_cell.sum(axis=1), axis=0) * 100

    fig, ax = plt.subplots(figsize=(7.5, 4))
    bottom = np.zeros(len(per_cell_pct))
    for state in qos_state.STATES:
        ax.bar(
            per_cell_pct.index, per_cell_pct[state], bottom=bottom,
            color=qos_state.STATE_COLORS[state], label=state,
        )
        bottom += per_cell_pct[state].to_numpy()
    ax.set_ylabel("% du temps")
    ax.set_title("Répartition des états QoS par cellule (seuils contrat v1.1)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(EDA_FIG_DIR / "etats_qos.png", bbox_inches="tight")
    plt.close(fig)

    global_dist = qos_state.state_distribution(labelled)

    # Croisement état QoS × vérité terrain : mesure ce que les seuils seuls
    # capturent, et donc ce qu'un modèle doit apporter en plus.
    crosstab = pd.crosstab(labelled["qos_state"], labelled["is_anomaly"], normalize="columns") * 100

    # Décomposition KPI par KPI : indispensable pour diagnostiquer un
    # déséquilibre de l'état global, qui résulte de l'agrégation « pire KPI ».
    rows = []
    for kpi in thresholds:
        col = f"{kpi}_state"
        if col not in labelled.columns:
            continue
        shares = (
            labelled[col].value_counts(normalize=True).reindex(qos_state.STATES, fill_value=0) * 100
        )
        rows.append({"kpi": kpi, **{state: round(shares[state], 2) for state in qos_state.STATES}})
    per_kpi_pct = pd.DataFrame(rows).set_index("kpi")

    return global_dist, crosstab.round(2), per_cell_pct.round(2), per_kpi_pct


# ==================================================================
# 5. Rapport
# ==================================================================
def write_report(
    contract: dict,
    stats: pd.DataFrame,
    separability: pd.DataFrame,
    profile: pd.DataFrame,
    corr: pd.DataFrame,
    acf: pd.DataFrame,
    qos_dist: pd.DataFrame,
    qos_crosstab: pd.DataFrame,
    per_cell_pct: pd.DataFrame,
    per_kpi_pct: pd.DataFrame,
) -> None:
    amplitude = ((profile.max() - profile.min()) / profile.mean() * 100).round(1)
    # Part de temps « bon » attendue si les KPI étaient indépendants : quantifie
    # l'effet mécanique de l'agrégation « pire KPI » sur l'état global.
    independent_good = float(np.prod(per_kpi_pct["bon"].to_numpy() / 100)) * 100
    observed_good = float(qos_dist.loc[qos_dist["etat"] == "bon", "pct"].iloc[0])

    strongest_corr = (
        corr.where(~np.eye(len(corr), dtype=bool)).abs().stack().sort_values(ascending=False)
    )
    top_pairs = "\n".join(
        f"- `{a}` ↔ `{b}` : {corr.loc[a, b]:+.2f}"
        for (a, b), _ in list(strongest_corr.items())[:6:2]
    )

    report = f"""# Rapport d'analyse exploratoire — Binôme B

**Jalon J7** · contrat d'interface v1.1 · source de données : `{loader.source_description()}`

Généré par `python -m src.scripts.run_eda`. Figures dans `reports/figures/eda/`.

---

## 1. Périmètre et conformité au contrat

| Élément | Valeur |
|---|---|
| Lignes servies | {contract['n_lignes']:,} |
| Cellules | {contract['n_cellules']} |
| Période couverte | {contract['periode_debut']} → {contract['periode_fin']} |
| Durée | {contract['duree_jours']} jours |
| Valeurs imputées (`is_missing`) | {contract['taux_imputation_pct']} % |
| Valeurs nulles résiduelles | {contract['valeurs_nulles']} |
| Taux d'anomalie (vérité terrain) | {contract['taux_anomalie_pct']} % |

**Contrôles de conformité** : {'; '.join(contract['anomalies_contrat'])}

Conséquence pour la modélisation : avec un taux d'anomalie de
{contract['taux_anomalie_pct']} %, l'exactitude (*accuracy*) est inutilisable
comme métrique — un modèle prédisant « jamais d'anomalie » atteindrait
{100 - contract['taux_anomalie_pct']:.2f} %. L'évaluation repose donc sur
précision / rappel / F1 et sur la matrice de confusion, conformément au §4.3 de
la fiche.

---

## 2. Statistiques descriptives

{stats.to_markdown()}

---

## 3. Séparabilité normal / anomalie

Écart des moyennes entre régime normal et régime anormal, exprimé en écarts-types
du régime normal. Une séparabilité > 1 σ désigne un KPI directement discriminant.

{separability.to_markdown(index=False)}

Lecture : les KPI les plus discriminants doivent peser dans le détecteur ; ceux
dont la séparabilité est faible n'apportent du signal qu'en interaction avec les
autres, ce qui justifie un modèle multivarié plutôt qu'un simple seuil par KPI.

---

## 4. Saisonnalité journalière

Amplitude du profil horaire, en % de la moyenne du KPI :

{amplitude.to_frame('amplitude_pct').to_markdown()}

Une saisonnalité de cette ampleur impose deux choix :
1. les features de saisonnalité (`hour_of_day`, `day_of_week`) livrées par le
   Binôme A sont converties en **encodages cycliques** sin/cos, pour éviter la
   discontinuité 23 h → 0 h ;
2. un détecteur d'anomalies doit raisonner en **écart à la normale horaire** et
   non en valeur absolue, sinon la pointe de trafic du soir est confondue avec
   une dégradation. D'où les features dérivées `*_ratio_to_hour`.

![Saisonnalité](figures/eda/saisonnalite_horaire.png)

---

## 5. Corrélations et autocorrélation

Couples de KPI les plus corrélés :

{top_pairs}

{corr.to_markdown()}

Autocorrélation (cellule de référence) :

{acf.to_markdown()}

Lecture : l'autocorrélation reste élevée jusqu'à quelques dizaines de minutes
puis décroît. C'est le fondement du choix des modèles de prévision — les lags
courts (1, 5, 10 min) livrés par le Binôme A portent l'essentiel du signal à
horizon 5–30 min, ce qui favorise un modèle autorégressif (XGBoost sur lags)
plutôt qu'un modèle à composantes tendance/saisonnalité.

![Autocorrélation](figures/eda/autocorrelation.png)

---

## 6. États QoS et validation des seuils figés

Répartition globale obtenue avec les seuils du contrat v1.1, agrégation par la
règle du pire KPI :

{qos_dist.to_markdown(index=False)}

Répartition par cellule (% du temps) :

{per_cell_pct.to_markdown()}

### 6.1 Diagnostic : les seuils v1.1 sont déséquilibrés

Une plateforme de supervision qui déclare l'état **critique {observed_good and qos_dist.loc[qos_dist['etat'] == 'critique', 'pct'].iloc[0]:.1f} % du temps**
et l'état « bon » seulement **{observed_good:.1f} % du temps** n'est pas
exploitable : l'alerte perd sa valeur de signal. La décomposition KPI par KPI
identifie la cause.

État par KPI pris isolément (% du temps) :

{per_kpi_pct.to_markdown()}

Le mécanisme est arithmétique. Chaque KPI est classé « bon » entre
{per_kpi_pct['bon'].min():.0f} % et {per_kpi_pct['bon'].max():.0f} % du temps
selon l'indicateur. L'agrégation par la règle du pire KPI exige que **les cinq**
KPI soient simultanément bons : si les KPI étaient indépendants, la part de temps
« bon » global tomberait à {independent_good:.2f} %. On observe
{observed_good:.2f} %, l'écart provenant de la corrélation entre KPI (§5) qui
regroupe partiellement les dégradations sur les mêmes instants.

Autrement dit : **les seuils ont été calibrés indicateur par indicateur, sans
tenir compte de la règle d'agrégation qui les combine.** Les percentiles retenus
par le Binôme A sont défendables KPI par KPI (`latency` est bon 82 % du temps),
mais `throughput` (`good_min` = 107 Mbit/s) ne laisse que
{per_kpi_pct.loc['throughput', 'bon']:.1f} % du temps en « bon », et `jitter`
(`good_max` = 4,0 ms) {per_kpi_pct.loc['jitter', 'bon']:.1f} % — ces deux seuils
tirent l'état global vers le bas à eux seuls.

**Position du Binôme B** : le contrat v1.1 est gelé et nous ne le modifions pas
unilatéralement — le respecter est le facteur de réussite n°1 identifié au §8.2
de la fiche. Les seuils servis par `GET /api/v1/thresholds` restent donc la
référence dans tout le code. Nous demandons en revanche au Binôme A une révision
en **v1.2** selon l'une des deux options suivantes :

- *option A — recalibrer par la cible d'agrégation* : fixer les `good_*` de sorte
  que l'état global « bon » représente la part de temps visée (typiquement
  60–70 %), ce qui revient à relâcher `throughput` et `jitter` ;
- *option B — changer la règle d'agrégation* : conserver les seuils et remplacer
  la règle du pire KPI par une règle à quorum (état critique si ≥ 2 KPI
  critiques), documentée dans le contrat.

L'option A est préférable : elle garde une règle d'agrégation simple et
explicable à un exploitant. Cette décision appartient au Binôme A, propriétaire
de l'endpoint ; le dashboard expose le déséquilibre pour que la discussion se
tienne sur des chiffres.

### 6.2 Les seuils ne remplacent pas un détecteur d'anomalies

Croisement état QoS (règles de seuils) × vérité terrain `is_anomaly`, en % par colonne :

{qos_crosstab.to_markdown()}

Lecture — c'est le résultat déterminant pour le cadrage des modèles. Les seuils
seuls ne suffisent pas à identifier les anomalies : une part des points anormaux
reste classée « bon » ou « dégradé » (anomalies de forme et non d'amplitude —
dérive progressive, gigue anormale à charge normale), et surtout la colonne
`False` montre que {qos_crosstab.loc['critique', False]:.0f} % des points
**normaux** sont déjà classés « critique ». Un exploitant qui se fierait aux
seuls seuils recevrait donc une majorité de fausses alertes.

**La classification par seuils et la détection d'anomalies apprise sont deux
fonctions complémentaires, non redondantes** : la première qualifie l'état
d'exploitation au sens du SLA, la seconde signale l'atypique. C'est la
justification du travail de modélisation qui suit.

![États QoS](figures/eda/etats_qos.png)

---

## 7. Décisions de cadrage des modèles

| Question | Décision | Motif tiré de l'EDA |
|---|---|---|
| Détection d'anomalies | non supervisée, multivariée, sur écarts à la normale horaire | séparabilité inégale entre KPI (§3) ; saisonnalité forte (§4) |
| Baselines anomalie | seuils contractuels + Isolation Forest + DBSCAN | il faut une référence explicable avant tout modèle appris |
| Modèle avancé anomalie | autoencodeur (erreur de reconstruction) | capte les anomalies de forme que les seuils manquent (§6) |
| Prévision | modèle autorégressif sur lags courts | autocorrélation dominante à 5–30 min (§5) |
| Baselines prévision | persistance + moyenne mobile + ARIMA | référence obligatoire avant modèle avancé (§8.2 de la fiche) |
| Modèle avancé prévision | XGBoost multi-horizon | non-linéarités et interactions entre KPI corrélés (§5) |
| Métriques anomalie | précision / rappel / F1 / PR-AUC | déséquilibre à {contract['taux_anomalie_pct']} % (§1) |
| Métriques prévision | MAE / RMSE / MAPE + comparaison à la persistance | exigence §4.3 de la fiche |
| Découpage | chronologique par cellule, avec purge de 60 min | fenêtres glissantes de 60 min dans les features du Binôme A |

---

## 8. Réserves adressées au Binôme A

Contrôles automatiques de conformité du flux servi :

{chr(10).join(f'- {issue}' for issue in contract['anomalies_contrat'])}

Demandes de révision, par ordre de priorité :

1. **Recalibrage des seuils QoS (v1.2)** — cf. §6.1. L'état « bon » ne couvre que
   {observed_good:.1f} % du temps et l'état « critique » {qos_dist.loc[qos_dist['etat'] == 'critique', 'pct'].iloc[0]:.1f} %.
   Seuils principalement en cause : `throughput.good_min` et `jitter.good_max`.
   Nous continuons d'utiliser les seuils v1.1 tant que la révision n'est pas actée.
2. **`GET /eval/labels` : horodatages non rééchantillonnés.** L'endpoint sert les
   `ts` de `raw_kpi_measurements` (ex. `20:21:41`) alors que `/kpi/history` et
   `/features` sont rééchantillonnés à la minute pleine (`20:21:00`). Une jointure
   sur `(ts, cell_id)` n'apparie donc **aucune** ligne : la prévalence mesurée
   tombe à 0 % et toutes les métriques de détection s'effondrent à zéro, sans la
   moindre erreur levée. Un endpoint d'évaluation inutilisable pour évaluer est un
   défaut bloquant. Contourné côté B par un réalignement sur la grille minute
   (agrégation par `max`), et protégé par un garde-fou `LabelAlignmentError`.
   Correction attendue : servir les `ts` alignés sur `clean_kpi_measurements`.
3. **`GET /eval/labels` : enveloppe de réponse incomplète.** L'endpoint accepte
   `limit` et `offset` mais son enveloppe omet `limit`, `offset`, `total` et
   `has_more`, contrairement au contrat que le README du binôme A énonce
   lui-même. Un client qui déroule la pagination sur `has_more` s'arrête après une
   seule page : 5 000 étiquettes lues sur 100 800, en silence. Contourné côté B
   par l'heuristique « continuer tant que la page est pleine ».
4. **Mise à jour du §5 de `data_dictionary.md`** — la liste d'endpoints y figurant
   (`/kpi/raw`, `/kpi/clean`, `/stream/latest`) ne correspond plus à l'API v1.1
   réellement servie. Le document du contrat doit refléter l'implémentation.
5. **Pipeline non idempotent — vérifié sur la stack Docker.** `clean_prepare` et
   `build_features` relisent la table amont en entier et insèrent en `append` sur
   des tables à clé primaire `(ts, cell_id)`. La seconde exécution de
   `run_pipeline` échoue sur
   `psycopg2.errors.UniqueViolation: duplicate key value violates unique
   constraint "4_clean_kpi_measurements_pkey"`. Les données ne sont pas corrompues
   (la transaction est annulée), mais **le rafraîchissement périodique est
   impossible** : le DAG Airflow, planifié toutes les 15 minutes, échouera à chaque
   exécution après la première. Le paramètre `since` existe dans les deux fonctions
   mais n'est jamais transmis, ni par `run_pipeline.py` ni par le DAG.
6. **`docker-compose.yml` était absent du dépôt** — livrable commun attendu au §6.1
   (« démarrable en une commande ») et référencé par les trois README ainsi que par
   le Dockerfile Airflow. Aucune commande de démarrage documentée ne fonctionnait,
   et l'intégration A ↔ B était donc intestable. Le Binôme B en a produit une
   version de travail à la racine, avec laquelle la chaîne complète a été validée
   (base peuplée, API servie, dashboard lisant l'API). Les services `timescaledb`,
   `api` et `airflow` relèvent du Binôme A : à relire et à reprendre, notamment sur
   le nom de la base et le stockage des métadonnées Airflow (points signalés en
   commentaire dans le fichier).
"""
    (REPORTS_DIR / "rapport_eda.md").write_text(report, encoding="utf-8")


# ==================================================================
# Entrée
# ==================================================================
def main() -> None:
    history, _labels, thresholds = load_all()

    contract = check_contract(history, thresholds)
    stats = descriptive_stats(history)
    separability = normal_vs_anomaly(history)

    profile = fig_seasonality(history)
    corr = fig_correlation(history)
    acf = fig_autocorrelation(history)
    qos_dist, qos_crosstab, per_cell_pct, per_kpi_pct = fig_qos_states(history, thresholds)
    fig_distributions(history, thresholds)
    for cell_id in sorted(history["cell_id"].unique())[:2]:
        fig_series(history, cell_id)

    stats.to_csv(METRICS_DIR / "eda_statistiques.csv")
    separability.to_csv(METRICS_DIR / "eda_separabilite.csv", index=False)
    acf.to_csv(METRICS_DIR / "eda_autocorrelation.csv")
    per_kpi_pct.to_csv(METRICS_DIR / "eda_etats_qos_par_kpi.csv")
    (METRICS_DIR / "eda_conformite_contrat.json").write_text(
        json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    write_report(
        contract, stats, separability, profile, corr, acf, qos_dist, qos_crosstab,
        per_cell_pct, per_kpi_pct,
    )

    print(f"\nEDA terminée.")
    print(f"  Rapport : reports/rapport_eda.md")
    print(f"  Figures : {EDA_FIG_DIR.relative_to(REPORTS_DIR.parent)}")
    print(f"  Taux d'anomalie : {contract['taux_anomalie_pct']} %")
    print(f"  Conformité : {'; '.join(contract['anomalies_contrat'])}")


if __name__ == "__main__":
    main()
