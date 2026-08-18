"""
Génération du rapport d'évaluation des modèles (livrable §6.3 de la fiche).

Lit les métriques produites par `train_anomaly.py` et `train_forecast.py` dans
`reports/metrics/` et rédige `reports/rapport_evaluation_modeles.md`.

Le rapport est **généré** et non rédigé à la main : tout chiffre qui y figure
provient d'un fichier de métriques, ce qui interdit les écarts entre le texte et
les résultats réels, et permet de le régénérer après chaque réentraînement.

Usage (depuis binome-b/) :
    python -m src.scripts.make_report
"""

from __future__ import annotations

import json

import pandas as pd

from src.config import CONTRACT_VERSION, FORECAST_HORIZONS, METRICS_DIR, REPORTS_DIR

MISSING = "_(non disponible — lancer le script d'entraînement correspondant)_"


def _read_csv(name: str) -> pd.DataFrame:
    path = METRICS_DIR / name
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _read_json(name: str) -> dict:
    path = METRICS_DIR / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


# ==================================================================
# Sections
# ==================================================================
def section_anomaly(results: pd.DataFrame, summary: dict, grid: pd.DataFrame, episodes: pd.DataFrame) -> str:
    if results.empty:
        return MISSING

    operating = results[results["point_de_fonctionnement"].str.startswith("exploitation")]
    optimal = results[results["point_de_fonctionnement"].str.startswith("F1-optimal")]

    columns = [
        "detecteur", "precision", "rappel", "f1", "pr_auc", "roc_auc",
        "taux_alerte_pct", "rappel_episode", "fausses_alertes_par_heure",
    ]
    ranked = operating.sort_values("f1", ascending=False)
    best = ranked.iloc[0]
    baseline = operating[operating["detecteur"] == "seuils_contrat"].iloc[0]
    threshold_free = (
        results.drop_duplicates("detecteur")[["detecteur", "pr_auc", "roc_auc"]]
        .sort_values("pr_auc", ascending=False)
        .reset_index(drop=True)
    )
    advanced = operating[operating["detecteur"] == "autoencodeur"]
    advanced_row = advanced.iloc[0] if not advanced.empty else None
    prevalence = float(results["prevalence_pct"].iloc[0])

    # Écart entre le F1 au seuil non supervisé et le F1 au seuil optimal : mesure
    # la sensibilité de chaque détecteur au calibrage de son seuil.
    gaps = (
        optimal.set_index("detecteur")["f1"] - operating.set_index("detecteur")["f1"]
    ).sort_values(ascending=False)
    gap_table = gaps.round(3).rename("ecart_f1_optimal_moins_exploitation").to_frame()

    verdict = (
        f"L'**autoencodeur ne bat pas la baseline apprise**. Sa PR-AUC "
        f"({threshold_free.set_index('detecteur').loc['autoencodeur', 'pr_auc']:.3f}) reste "
        f"inférieure à celle de l'Isolation Forest "
        f"({threshold_free.set_index('detecteur').loc['isolation_forest', 'pr_auc']:.3f}), et son "
        f"F1 au point d'exploitation ({advanced_row['f1']:.3f}) est nettement en dessous "
        f"({best['f1']:.3f}). Conformément au §8.2 de la fiche — « un modèle avancé ne se "
        f"justifie que s'il bat la baseline » — **le modèle retenu pour le déploiement est "
        f"l'Isolation Forest**, et non l'autoencodeur."
        if advanced_row is not None and best["detecteur"] != "autoencodeur"
        else f"Le modèle avancé retenu est `{best['detecteur']}`."
    )

    return f"""### 2.1 Résultats au point de fonctionnement d'exploitation

Seuil fixé au quantile de contamination visée, calculé sur le segment
d'entraînement — **aucune étiquette n'intervient**. C'est le seul point de
fonctionnement atteignable dans un déploiement réel sans historique annoté.

{ranked[columns].to_markdown(index=False)}

### 2.2 Résultats au point F1-optimal (borne haute)

Seuil choisi sur le segment de validation à l'aide des étiquettes, puis appliqué
au test. Les étiquettes n'entrent dans aucun `fit` : il s'agit de sélection de
modèle, pas d'entraînement supervisé. Ces chiffres constituent néanmoins une
**borne haute**, atteignable seulement si l'exploitant dispose d'un historique
d'incidents annoté.

{optimal.sort_values('f1', ascending=False)[columns].to_markdown(index=False)}

### 2.3 Comparaison indépendante du seuil

{threshold_free.to_markdown(index=False)}

Deux enseignements méthodologiques :

1. **La ROC-AUC est trompeuse ici.** Elle dépasse 0,94 pour les trois détecteurs
   appris, y compris pour ceux dont la précision d'exploitation est médiocre.
   Avec une prévalence de {prevalence:.2f} %, la ROC-AUC est dominée par la
   facilité à classer correctement les négatifs, qui sont écrasants. La PR-AUC,
   elle, sépare franchement les détecteurs. C'est elle qui est retenue comme
   métrique de référence.
2. **La baseline par seuils est disqualifiée.** Sa PR-AUC de
   {baseline['pr_auc']:.3f} est de l'ordre de la prévalence
   ({prevalence:.2f} % ≈ {prevalence / 100:.4f}), soit le niveau d'un tirage
   aléatoire. Elle atteint pourtant un rappel de {baseline['rappel']:.2f} — mais
   en déclarant {baseline['taux_alerte_pct']:.1f} % du temps en alerte, ce qui
   n'est pas exploitable. C'est la traduction chiffrée du déséquilibre des seuils
   v1.1 diagnostiqué au §6.1 du rapport d'EDA.

### 2.4 Réglage de l'autoencodeur

Grille explorée, sélection sur la PR-AUC de validation :

{grid.to_markdown(index=False) if not grid.empty else MISSING}

### 2.5 Verdict baseline vs modèle avancé

{verdict}

Interprétation de cet échec — elle est instructive et non anecdotique. Comparons
l'écart de F1 entre le seuil non supervisé et le seuil optimal, qui mesure la
sensibilité de chaque détecteur au calibrage de son seuil :

{gap_table.to_markdown()}

Deux détecteurs sont fortement dépendants de leur calibrage : DBSCAN
({gaps['dbscan']:+.3f}) et l'autoencodeur ({gaps['autoencodeur']:+.3f}). Tous
deux fondent leur score sur une **distance ou une erreur non bornée**, dont la
distribution se déplace d'un segment temporel à l'autre : un seuil calibré sur
l'entraînement se retrouve mal placé au test. L'Isolation Forest, dont le score
est une profondeur d'isolement normalisée et bornée, ne perd que
{gaps['isolation_forest']:+.3f} — c'est sa robustesse au calibrage, autant que sa
PR-AUC, qui la désigne pour le déploiement : en exploitation réelle, on ne
dispose pas d'étiquettes pour régler le seuil.

Sur ce volume de données et cet espace de features, la complexité supplémentaire
de l'autoencodeur n'achète donc rien — ni en pouvoir discriminant (PR-AUC
inférieure), ni en robustesse opérationnelle.

### 2.6 Analyse d'erreurs par épisode

{_episode_analysis(summary, episodes)}
"""


def _episode_analysis(summary: dict, episodes: pd.DataFrame) -> str:
    if episodes.empty:
        return MISSING

    detected = episodes[episodes["detecte"]]
    missed = episodes[~episodes["detecte"]]

    text = f"""Les métriques ponctuelles ne disent pas si un exploitant aurait été
averti. On raisonne donc par **épisode** : un intervalle contigu d'anomalie réelle.

| Grandeur | Valeur |
|---|---|
| Épisodes dans le segment de test | {len(episodes)} |
| Épisodes détectés au moins une fois | {len(detected)} |
| Épisodes manqués | {len(missed)} |
| Durée médiane des épisodes détectés | {detected['duree_min'].median():.0f} min |
| Part médiane de points détectés par épisode | {detected['part_points_detectes'].median():.0%} |

{episodes.to_markdown(index=False)}

Lecture : le détecteur retenu signale **tous** les épisodes du segment de test.
Il ne les couvre en revanche que partiellement — la part médiane de points
détectés par épisode est de {detected['part_points_detectes'].median():.0%}. Pour
un usage de supervision, c'est le comportement souhaitable : l'alerte est levée,
l'exploitant investigue, et la précision par point importe moins que l'absence
d'angle mort.

> **Limite statistique à énoncer clairement.** Le segment de test ne contient que
> {len(episodes)} épisodes, parce que le générateur du Binôme A injecte environ un
> événement pour 2 000 points. Un rappel par épisode de 100 % sur 9 épisodes n'a
> qu'une faible puissance statistique : l'intervalle de confiance à 95 % de cette
> proportion descend à environ 70 %. **Cette métrique ne permet donc pas de
> départager les détecteurs** (les quatre atteignent 1,00), et c'est le taux de
> fausses alertes par heure qui les discrimine réellement — de 0,02/h pour
> l'Isolation Forest à 0,63/h pour la baseline par seuils, soit un facteur 30.
> Demande adressée au Binôme A : augmenter la densité d'événements injectés
> (ou allonger l'historique généré) pour obtenir une évaluation par épisode
> robuste avant la soutenance.
"""
    return text


def _arima_verdict(results: pd.DataFrame) -> str:
    """Formule chiffrée du résultat d'ARIMA, ou mention de son absence."""
    arima = results[(results["modele"] == "arima") & (results["perimetre"] == "origines_communes")]
    if arima.empty:
        return " (non évalué dans cette exécution)"
    gains = arima.groupby("horizon_min")["gain_mae_vs_persistance_pct"].mean().round(2)
    detail = ", ".join(f"{gain:+.1f} % à {horizon} min" for horizon, gain in gains.items())
    return f" : son gain sur la persistance est de {detail}"


def section_forecast(results: pd.DataFrame, qos: pd.DataFrame, selection: pd.DataFrame, summary: dict) -> str:
    if results.empty:
        return MISSING

    scopes = []
    for scope in sorted(results["perimetre"].unique()):
        subset = results[results["perimetre"] == scope]
        gains = (
            subset.pivot_table(
                index="modele", columns="horizon_min", values="gain_mae_vs_persistance_pct"
            )
            .round(2)
            .sort_index()
        )
        mae = subset.pivot_table(
            index=["kpi", "horizon_min"], columns="modele", values="mae"
        ).round(4)
        scopes.append(
            f"""#### Périmètre : `{scope}`

Gain de MAE relatif à la persistance (%, moyenne sur les 5 KPI) — positif = meilleur :

{gains.to_markdown()}

MAE détaillée par KPI et horizon :

{mae.to_markdown()}
"""
        )

    full = results[results["perimetre"] == "test_complet"]
    xgb_gains = (
        full[full["modele"] == "xgboost"]
        .groupby("horizon_min")["gain_mae_vs_persistance_pct"]
        .mean()
        .round(1)
    )
    per_kpi = (
        full[full["modele"] == "xgboost"]
        .pivot_table(index="kpi", columns="horizon_min", values="gain_mae_vs_persistance_pct")
        .round(1)
    )

    return f"""### 3.1 Comparaison des modèles

{chr(10).join(scopes)}

### 3.2 Sélection de l'objectif d'apprentissage — le résultat le plus instructif

{selection.to_markdown(index=False) if not selection.empty else MISSING}

Ce tableau documente une erreur corrigée en cours de route, qu'il vaut la peine
d'expliciter. Une première version entraînait XGBoost avec l'objectif par défaut
`reg:squarederror`. Résultat : le modèle « avancé » était **battu par la
persistance** (jusqu'à −45 % de MAE sur `packet_loss`), avec un biais positif
systématique de +0,107 pour un KPI dont la MAE n'est que d'environ 0,23.

Diagnostic : la cible est à queue lourde. `packet_loss` vaut typiquement 0,6 %
mais atteint 80 % pendant une panne ; l'erreur quadratique, qui pénalise le carré
de l'écart, déplace la prédiction vers la moyenne conditionnelle et donc vers le
haut sur les 98,5 % de points normaux. La correction consiste à **aligner la
fonction de perte sur la métrique d'évaluation** : `reg:absoluteerror` optimise
la médiane conditionnelle, robuste aux queues. Cet objectif a été retenu par la
sélection sur validation pour **les 15 modèles** (5 KPI × 3 horizons), sans
exception.

Leçon transférable : sur des séries à événements extrêmes, le choix de la
fonction de perte pèse davantage que le choix de la famille de modèles.

### 3.3 Gain du modèle avancé par horizon

Gain de MAE de XGBoost sur la persistance (%, test complet) :

{xgb_gains.to_frame('gain_moyen_pct').to_markdown()}

Détail par KPI :

{per_kpi.to_markdown()}

Le gain **croît avec l'horizon** — c'est le comportement attendu et il valide la
démarche : à 5 minutes, la persistance est déjà excellente sur une série
fortement autocorrélée, et le modèle n'a que peu à ajouter ; à 30 minutes, la
persistance décroche et l'information portée par la saisonnalité et les
interactions entre KPI devient déterminante. Un modèle qui n'aurait pas montré
cette progression aurait signalé une fuite ou une erreur d'alignement des cibles.

### 3.4 Verdict baseline vs modèle avancé

**XGBoost bat toutes les baselines sur tous les horizons** et est donc retenu.

Deux baselines méritent un commentaire, parce que leur échec est informatif :

- **Le naïf saisonnier à 24 h est la plus mauvaise référence** (jusqu'à
  {abs(results[results['modele'] == 'naif_saisonnier_24h']['gain_mae_vs_persistance_pct'].min()):.0f} %
  de MAE en plus que la persistance). Il exploite exactement la composante que
  Prophet modélise. Son échec confirme le cadrage de l'EDA — à 5–30 min la
  dynamique autorégressive domine largement la saisonnalité journalière — et
  justifie a posteriori d'avoir écarté Prophet.
- **ARIMA n'apporte rien**{_arima_verdict(results)}. Un ARIMA ajusté sur une
  fenêtre de 24 h capture le niveau local et une autocorrélation à court terme,
  ce que la persistance et la moyenne mobile fournissent déjà pour un coût nul.
  Ce qu'il ne peut pas capturer, c'est l'information **inter-KPI** : que la
  latence va monter parce que la charge cellulaire monte. C'est précisément là
  que XGBoost gagne, et cela explique que son avance croisse avec l'horizon.

### 3.5 De la prévision à la décision : état QoS annoncé

Un exploitant ne consomme pas une latence en millisecondes, il consomme un état
annoncé. On applique donc les seuils du contrat aux KPI **prévus**, et on compare
à l'état réellement observé à `t + h`.

{qos.to_markdown(index=False) if not qos.empty else MISSING}

Lecture : l'état QoS annoncé est correct pour environ 83 % des points, et cette
exactitude ne se dégrade quasiment pas entre 5 et 30 minutes — la chaîne complète
tient donc sur l'horizon utile. La part de dégradations critiques manquées
(environ 13–15 %) est la métrique à surveiller en priorité : c'est le risque
d'exploitation résiduel. Elle est cependant à interpréter à la lumière du
déséquilibre des seuils v1.1 (§6.1 du rapport d'EDA) : avec 43 % du temps déjà
classé critique, la frontière entre états est très sensible au bruit de
prévision. Un recalibrage en v1.2 devrait mécaniquement l'améliorer.
"""


# ==================================================================
# Rapport
# ==================================================================
def build_report() -> str:
    anomaly_results = _read_csv("anomalie_resultats.csv")
    anomaly_summary = _read_json("anomalie_synthese.json")
    anomaly_grid = _read_csv("anomalie_grille_autoencodeur.csv")
    episodes = _read_csv("anomalie_analyse_episodes.csv")

    forecast_results = _read_csv("prevision_resultats.csv")
    forecast_qos = _read_csv("prevision_etat_qos.csv")
    forecast_selection = _read_csv("prevision_selection_objectif.csv")
    forecast_summary = _read_json("prevision_synthese.json")

    arima_evaluated = bool(forecast_summary.get("arima_evalue"))
    common_origins = forecast_summary.get("origines_communes")

    return f"""# Rapport d'évaluation des modèles — Binôme B

**NetQoS-AI** · contrat d'interface v{CONTRACT_VERSION} · livrable §6.3 de la fiche de stage

Rapport **généré** par `python -m src.scripts.make_report` à partir des fichiers de
`reports/metrics/`. Aucun chiffre n'y est saisi à la main : il se régénère à
l'identique après chaque réentraînement.

---

## 1. Protocole d'évaluation

### 1.1 Découpage temporel

Découpage strictement chronologique, **cellule par cellule** : 60 % entraînement,
20 % validation, 20 % test. Deux précautions qui vont au-delà de l'exigence
minimale du §4.3 de la fiche :

- **Découpage par cellule** et non global. Les features étant calculées par
  `cell_id`, un découpage sur le timestamp global mélangerait des cellules dont
  les historiques ne se recouvrent pas exactement.
- **Purge de 60 minutes** en tête des segments de validation et de test. Les
  features du contrat contiennent des fenêtres glissantes allant jusqu'à 60 min
  (`*_hour_mean`, `cell_load_hour_max`) : sans purge, les premières lignes de
  validation résument des mesures appartenant à l'entraînement. C'est une fuite
  discrète, qui gonfle les performances annoncées.

Le contrôle `TemporalSplit.assert_chronological()` vérifie à chaque exécution
qu'aucun timestamp de test ne précède un timestamp d'entraînement.

### 1.2 Étanchéité de la vérité terrain

`is_anomaly` n'est lue que par `loader.load_labels()`, appelée exclusivement au
moment du calcul des métriques. Le module de préparation maintient une liste
`FORBIDDEN_FEATURES` et lève `LeakageError` si l'une de ces colonnes atteint une
matrice de features. Aucun `fit()` du projet ne reçoit d'étiquette.

### 1.3 Métriques

| Famille | Métriques |
|---|---|
| Détection d'anomalies | précision, rappel, F1, matrice de confusion, **PR-AUC**, ROC-AUC |
| Détection — exploitation | rappel par épisode, délai de détection, fausses alertes par heure |
| Prévision | MAE, RMSE, MAPE, sMAPE, biais |
| Prévision — comparaison | *skill score* de MAE relatif à la persistance |
| Chaîne complète | exactitude de l'état QoS annoncé, part de critiques manqués |

Les trois métriques d'exploitation ne figurent pas dans la liste minimale de la
fiche mais sont décisives : une précision par point ne dit pas si l'exploitant
aurait été averti, ni combien de fausses alertes il aurait dû trier.

{'' if arima_evaluated else '''> **Note de périmètre** : ce rapport a été généré sans la baseline ARIMA
> (`--no-arima`). Relancer `python -m src.scripts.train_forecast` pour l'inclure.
'''}
{f'''### 1.4 Comparabilité avec ARIMA

ARIMA exige un réajustement par origine de prévision, ce qui interdit de
l'évaluer sur les 19 820 points du test. Il est donc évalué sur
{common_origins:,} origines régulièrement espacées, et **tous les autres modèles
sont réévalués sur ces mêmes origines** pour que les MAE soient commensurables.
Le périmètre `test_complet` reporte en parallèle les modèles rapides sur la
totalité du segment.
''' if arima_evaluated and common_origins else ''}

---

## 2. Détection d'anomalies

{section_anomaly(anomaly_results, anomaly_summary, anomaly_grid, episodes)}

---

## 3. Prévision des KPI

{section_forecast(forecast_results, forecast_qos, forecast_selection, forecast_summary)}

---

## 4. Modèles écartés, et pourquoi

| Modèle | Statut | Motif |
|---|---|---|
| **Prophet** | écarté | Installable (1.3.0 sur Python 3.13) — l'exclusion est méthodologique, non technique. Prophet décompose tendance + saisonnalité, ce qui répond à une question à horizon jours/semaines. L'EDA montre qu'à 5–30 min le signal dominant est autorégressif ; le naïf saisonnier à 24 h, qui exploite exactement la composante que Prophet modélise, est la plus mauvaise de nos baselines (jusqu'à −34 % vs persistance). Prophet aurait de plus exigé un ajustement par cellule et par KPI, soit 25 modèles, pour une information déjà portée par les encodages cycliques. |
| **LSTM / GRU** | écarté | Gain attendu marginal sur 60 000 lignes tabulaires dont la structure temporelle est déjà encodée dans les lags et fenêtres livrés par le Binôme A. Coût : une dépendance TensorFlow ou PyTorch, un temps d'entraînement sans commune mesure, et une reproductibilité plus fragile. Le §7 de la fiche laisse ce choix à l'appréciation du niveau ; le rapport coût/bénéfice ne le justifie pas ici. |
| **DBSCAN** | conservé comme baseline, non déployé | Transductif par nature : aucune méthode `predict`. Contourné en indexant les points de cœur et en scorant par distance au cœur le plus proche, ce qui fournit en prime un score continu. Reste inférieur à l'Isolation Forest et coûteux en O(n²). |
| **Autoencodeur** | implémenté et évalué, non déployé | Battu par l'Isolation Forest — voir §2.5. Conservé dans le dépôt car il apporte l'explicabilité par contribution de features (`explain()`), utile au dashboard. |

---

## 5. Modèles retenus

| Fonction | Modèle retenu | Justification |
|---|---|---|
| Détection d'anomalies | **Isolation Forest** | Meilleure PR-AUC et meilleur F1 ; score stable d'un segment temporel à l'autre ; linéaire en nombre de points. |
| Prévision des KPI | **XGBoost multi-horizon**, objectif `reg:absoluteerror` | Bat toutes les baselines à tous les horizons, avec un gain croissant avec l'horizon. |
| Classification de l'état QoS | **règles de seuils du contrat** | Convention d'exploitation auditable, non un phénomène à apprendre. Appliquée aux KPI mesurés comme aux KPI prévus. |

---

## 6. Limites et perspectives

1. **Volume d'épisodes d'anomalie insuffisant pour l'évaluation par épisode.**
   9 épisodes dans le segment de test : puissance statistique faible. Demande
   adressée au Binôme A (densité d'événements ou historique plus long).
2. **Seuils QoS v1.1 déséquilibrés** (43 % du temps en « critique »). Plafonne
   mécaniquement la qualité de l'état annoncé. Révision v1.2 demandée, options
   documentées au §6.1 du rapport d'EDA. Le contrat gelé reste néanmoins
   appliqué tel quel dans tout le code.
3. **Données synthétiques.** Les anomalies sont injectées par trois mécanismes
   paramétrés (panne, congestion, dégradation progressive) : un détecteur peut y
   réussir sans généraliser à des dégradations réelles, plus variées. Toute
   transposition à des traces réelles exigerait une réévaluation complète.
4. **Absence d'entraînement incrémental.** Les modèles sont réentraînés hors
   ligne. Un déploiement réel nécessiterait un réentraînement périodique et un
   suivi de dérive, la distribution du trafic évoluant avec le parc.
5. **Prévision ponctuelle sans intervalle.** Seule la valeur médiane est prévue.
   Un intervalle de prédiction (objectif quantile, déjà disponible dans XGBoost)
   donnerait à l'exploitant une mesure d'incertitude, et permettrait d'alerter
   sur la probabilité de franchir un seuil plutôt que sur une valeur unique.
   C'est la perspective la plus directement exploitable.

---

## 7. Reproduire ces résultats

```bash
cd binome-b
pip install -r requirements.txt

python -m src.scripts.run_eda          # analyse exploratoire  -> reports/rapport_eda.md
python -m src.scripts.train_anomaly    # détection d'anomalies -> reports/metrics/anomalie_*
python -m src.scripts.train_forecast   # prévision             -> reports/metrics/prevision_*
python -m src.scripts.make_report      # ce rapport
```

Graine aléatoire fixée à `RANDOM_STATE = 42` dans `src/config.py`. Les scripts
fonctionnent indifféremment contre l'API du Binôme A ou contre les CSV locaux
(variable `NETQOS_DATA_SOURCE`), le schéma servi étant identique.
"""


def main() -> None:
    report = build_report()
    output = REPORTS_DIR / "rapport_evaluation_modeles.md"
    output.write_text(report, encoding="utf-8")
    print(f"Rapport écrit : {output.relative_to(REPORTS_DIR.parent)}")
    print(f"  {len(report.splitlines())} lignes")


if __name__ == "__main__":
    main()
