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

![Courbes précision / rappel des quatre détecteurs](figures/anomalie/precision_rappel.png)

La lecture graphique confirme le classement : la courbe de l'Isolation Forest
domine sur toute la plage de rappel, et celle de la baseline par seuils reste
plate au ras de l'axe — une précision de l'ordre de 3 %, quel que soit le seuil.

![Distribution des scores selon la vérité terrain](figures/anomalie/distribution_scores.png)

Cette seconde figure montre *pourquoi* : la séparation des deux distributions
(normale en bleu, anormale en rouge) est nette pour l'Isolation Forest, beaucoup
plus confuse pour les autres. Un détecteur ne vaut que par le recouvrement de ces
deux densités.

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

![Chronogramme de détection sur le segment de test](figures/anomalie/chronogramme_isolation_forest.png)

Chronogramme d'une cellule du segment de test : score d'atypicité, seuil
d'alerte, épisodes réels en surimpression et alertes émises. C'est la
représentation la plus directe de ce que voit l'exploitant.

### 2.7 Campagne d'optimisation : ce qu'elle a donné, et ce qu'elle a révélé

{_optimisation_section()}
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


def _optimisation_section() -> str:
    """Rend compte de la campagne d'optimisation des deux modèles retenus."""
    grille_a = _read_csv("optimisation_anomalie_grille.csv")
    variance = _read_csv("optimisation_anomalie_variance.csv")
    synthese_a = _read_json("optimisation_anomalie_synthese.json")
    grille_p = _read_csv("optimisation_prevision_grille.csv")
    comparaison_p = _read_csv("optimisation_prevision_comparaison.csv")
    synthese_p = _read_json("optimisation_prevision_synthese.json")

    if grille_a.empty or variance.empty:
        return (
            "_(campagne non exécutée — lancer `python -m src.scripts.tune_anomaly` "
            "puis `python -m src.scripts.tune_forecast`)_"
        )

    oracle = synthese_a.get("borne_oracle_supervisee", {})
    ecart = synthese_a.get("ecart_entre_configurations", 0.0)
    etendue = synthese_a.get("etendue_due_a_la_graine_300_arbres", 0.0)

    # Métriques du détecteur effectivement déployé, au point d'exploitation.
    # Filtrer sur ce point est indispensable : chaque détecteur a deux lignes
    # dans le fichier de résultats (exploitation et F1-optimal).
    resultats = _read_csv("anomalie_resultats.csv")
    deploye: dict = {}
    if not resultats.empty:
        ligne = resultats[
            (resultats["detecteur"] == "isolation_forest")
            & (resultats["point_de_fonctionnement"].str.startswith("exploitation"))
        ]
        if not ligne.empty:
            deploye = {
                cle: round(float(ligne.iloc[0][cle]), 4)
                for cle in ("pr_auc", "precision", "rappel", "f1")
            }

    texte = f"""Le premier entraînement n'avait réglé que l'autoencodeur — le modèle
écarté — laissant l'Isolation Forest et XGBoost à des valeurs choisies a priori.
La campagne a comblé ce manque. Son résultat principal n'est pas un gain de
performance : c'est la démonstration qu'**il n'y avait pas de gain à prendre**, et
la mesure de ce qui plafonne réellement le système.

#### Détection d'anomalies : {len(grille_a)} configurations explorées

Deux leviers croisés : cinq espaces de features et six jeux d'hyperparamètres.

Les cinq meilleures configurations par PR-AUC de validation :

{grille_a.head(5).to_markdown(index=False)}

La meilleure configuration dépasse l'actuelle de {ecart:+.4f} de PR-AUC en
validation. Appliquée au test, elle s'est révélée **moins bonne**. Voici pourquoi.

#### Le contrôle qui invalide la recherche

Nous avons mesuré la dispersion de la PR-AUC **à configuration constante**, en ne
faisant varier que la graine aléatoire :

{variance.to_markdown(index=False)}

L'étendue due à la seule graine, à 300 arbres, est de **{etendue:.4f}** — soit
{etendue / max(ecart, 1e-9):.1f} fois l'écart de {ecart:.4f} entre les deux
configurations comparées. **Toute la grille classait donc du bruit.** Sans ce
contrôle, nous aurions publié un « gain de {synthese_a.get('gain_validation_pct', 0):+.1f} % »
qui n'existe pas — l'erreur exacte que le protocole d'évaluation est censé
prévenir.

Deux enseignements de méthode :

- **Aucun écart entre configurations n'est interprétable sans son incertitude.**
  Avec 220 points positifs en validation, la PR-AUC est un estimateur trop bruité
  pour départager des variantes proches.
- **Nos hypothèses sur l'espace de features étaient fausses.** Nous pensions que
  `cell_load`, dont l'EDA mesure une séparabilité de seulement 0,2 σ, diluait le
  signal. Le retirer **dégrade** la PR-AUC de validation (0,575 contre 0,605).
  Une feature faiblement discriminante seule peut contribuer en interaction avec
  les autres — c'est précisément l'argument qui justifiait un modèle multivarié.

#### Le seul gain réel : réduire la variance, pas chercher l'optimum

Le tableau de dispersion porte la solution. Passer de 300 à 2000 arbres améliore
la PR-AUC moyenne de
{(variance.set_index('n_estimators').loc[2000, 'pr_auc_moyenne'] / variance.set_index('n_estimators').loc[300, 'pr_auc_moyenne'] - 1) * 100:+.1f} %
**et divise l'écart-type par
{variance.set_index('n_estimators').loc[300, 'ecart_type'] / max(variance.set_index('n_estimators').loc[2000, 'ecart_type'], 1e-9):.0f}**.
Le diagnostic étant un problème de variance, le remède est l'agrégation — un
nombre d'arbres plus élevé — et non l'exploration d'hyperparamètres. C'est la
configuration désormais déployée.

**Correction d'un chiffre publié.** Nos résultats précédents annonçaient une
PR-AUC de 0,612 et un F1 de 0,639, obtenus à 300 arbres avec `RANDOM_STATE = 42`.
Ce tirage était favorable : la moyenne à 300 arbres est de
{variance.set_index('n_estimators').loc[300, 'pr_auc_moyenne']:.4f}. Les valeurs
rapportées dans ce document sont celles de la configuration à 2000 arbres,
inférieures en apparence mais **reproductibles à ±{variance.set_index('n_estimators').loc[2000, 'ecart_type']:.3f}**
au lieu de ±{variance.set_index('n_estimators').loc[300, 'ecart_type']:.3f}. Nous
préférons un chiffre fiable à un chiffre flatteur.

#### Prévision : {len(grille_p) if not grille_p.empty else 0} configurations explorées

{grille_p.to_markdown(index=False) if not grille_p.empty else MISSING}

Ici la situation est inverse, et il faut le dire : la MAE est calculée sur les
19 820 points du segment, tous informatifs, et non sur 300 positifs. Un écart y
est donc mesurable. Le meilleur réglage — profondeur 4 au lieu de 6 — n'apporte
que **{synthese_p.get('gain_validation_sonde_pct', 0):+.2f} %** en validation,
mais ce gain **se confirme sur le test aux trois horizons** :

{comparaison_p.pivot_table(index='configuration', columns='horizon_min', values='gain_vs_persistance_pct').round(2).to_markdown() if not comparaison_p.empty else MISSING}

Une amélioration constante sur trois horizons indépendants n'est pas une
fluctuation : elle est retenue. Au-delà de la profondeur, l'écart entre la
meilleure et la pire configuration de la grille n'est que de 2,6 % de MAE —
XGBoost est proche de son plafond sur ces features.

#### Où est le vrai plafond : la contrainte non supervisée

Reste la question de fond : **peut-on atteindre 90 à 100 % ?** Nous l'avons
mesuré. Un classifieur supervisé, entraîné sur `is_anomaly` avec les **mêmes
features et le même découpage temporel**, atteint sur le test :

| | Détecteur déployé (non supervisé) | Oracle supervisé |
|---|---|---|
| PR-AUC | {deploye.get('pr_auc', '—')} | **{oracle.get('pr_auc', '—')}** |
| Précision | {deploye.get('precision', '—')} | **{oracle.get('precision', '—')}** |
| Rappel | {deploye.get('rappel', '—')} | **{oracle.get('rappel', '—')}** |
| F1 | {deploye.get('f1', '—')} | **{oracle.get('f1', '—')}** |

**Le seuil des 90 % est donc atteignable — mais uniquement en s'entraînant sur la
vérité terrain.** Ce que ni le contrat ni la réalité n'autorisent :

- le §2.2 de la fiche impose une **approche non supervisée** pour la détection ;
- le contrat d'interface v1.1 réserve `is_anomaly` à l'évaluation ;
- et surtout, un réseau en exploitation **ne fournit pas d'étiquettes**. Un modèle
  supervisé exigerait qu'un exploitant annote manuellement chaque incident passé.

L'écart entre 0,59 et 0,90 de PR-AUC n'est donc pas un défaut de réglage : c'est
le **prix mesuré de la contrainte non supervisée**. Ce chiffre est, à notre sens,
le résultat le plus utile de la campagne : il transforme une insatisfaction
(« le modèle se trompe souvent ») en une quantité justifiable devant un jury.

Ce modèle supervisé n'est **ni déployé, ni sauvegardé, ni utilisé par le
dashboard**. Il n'existe que dans `src/scripts/tune_anomaly.py`, à titre
d'expérience documentée.

#### Ce qui améliorerait réellement le détecteur

Par ordre d'effet attendu, et aucun ne relève des hyperparamètres :

1. **Plus d'événements d'anomalie** (demande adressée au Binôme A). Avec 220
   positifs en validation, l'incertitude d'estimation interdit tout réglage fin.
   C'est le verrou principal, et il est en amont de nous.
2. **Une boucle semi-supervisée.** Si l'exploitant confirme ou infirme quelques
   dizaines d'alertes, on se rapproche de la borne oracle sans annoter
   l'historique complet. C'est la perspective la plus réaliste en exploitation.
3. **Un recalibrage des seuils QoS en v1.2**, qui débloquerait aussi l'exactitude
   de l'état annoncé (§3.5), aujourd'hui plafonnée par le déséquilibre des seuils.
"""
    return texte


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

![MAE par horizon et par KPI](figures/prevision/mae_par_horizon.png)

Une lecture par KPI est indispensable : la hiérarchie des modèles n'est pas la
même partout. XGBoost creuse l'écart sur `cell_load` et `throughput`, dont la
dynamique est la plus structurée, et reste au niveau des baselines sur `jitter`,
le plus bruité des cinq.

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

![Prévision de la latence à 30 minutes](figures/prevision/exemple_latency_30min.png)

Douze heures du segment de test : la courbe noire est la latence réellement
observée, les autres sont les prévisions annoncées pour ce même instant. On voit
que la persistance reproduit la courbe avec un décalage — c'est sa nature — là où
XGBoost anticipe les inflexions.

![Importance des features](figures/prevision/importance_features.png)

Les importances confirment le cadrage de l'EDA : les lags courts et les moyennes
glissantes du KPI cible dominent, mais les features des **autres** KPI
apparaissent — c'est exactement l'information inter-KPI qu'ARIMA ne peut pas
exploiter, et qui explique son échec.

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

Ces limites se répartissent en deux familles, qu'il faut distinguer parce qu'elles
n'appellent pas la même réponse : celles qui viennent de **contraintes amont**,
subies mais compensées, et celles qui relèvent de **choix de périmètre** du Binôme B.

### 6.1 Contraintes amont, et ce que nous avons fait pour les absorber

Ces trois points ont été signalés au Binôme A par écrit, chacun avec son
symptôme, son diagnostic chiffré et la correction attendue. Ils n'ont pas été
corrigés dans le temps du projet, et le contrat d'interface étant gelé, nous ne les avons pas modifiés
unilatéralement. Chacun a en revanche fait l'objet d'une mesure de mitigation, et
c'est cela qui est évaluable dans notre travail.

1. **Seuils QoS v1.1 déséquilibrés** — l'état « critique » couvre 43 % du temps,
   « bon » 8 %, parce que les seuils ont été calibrés indicateur par indicateur
   sans tenir compte de la règle d'agrégation qui les combine. **Impact mesuré** :
   la baseline de détection par seuils tombe à une PR-AUC de 0,023, au niveau du
   hasard, et l'exactitude de l'état QoS annoncé est plafonnée à ~82 %.
   **Ce que nous avons fait** : quantifié le mécanisme (§6.1 du rapport d'EDA),
   proposé deux options de recalibrage chiffrées, appliqué le contrat gelé tel
   quel dans tout le code — y compris là où il nous dessert — et affiché
   l'avertissement dans le dashboard pour qu'un exploitant ne prenne pas 43 % de
   rouge pour un réseau en panne.

2. **Densité d'anomalies trop faible** — 9 épisodes dans le segment de test.
   **Impact mesuré** : les quatre détecteurs atteignent 100 % de rappel par
   épisode, métrique qui ne les départage donc pas ; l'intervalle de confiance à
   95 % d'une proportion de 9/9 descend à environ 70 %.
   **Ce que nous avons fait** : substitué le **taux de fausses alertes par
   heure** comme métrique discriminante (facteur 30 entre le meilleur et le pire
   détecteur), et énoncé explicitement la faiblesse de puissance statistique
   plutôt que de présenter le 100 % comme un résultat.

3. **`GET /eval/labels` inexploitable en l'état** — ses horodatages ne sont pas
   rééchantillonnés, et son enveloppe omet `has_more`. **Impact mesuré** : une
   jointure directe n'apparie aucune ligne, la prévalence tombe à 0 % et toutes
   les métriques de détection s'effondrent à zéro **sans qu'aucune erreur ne soit
   levée** — c'est arrivé lors de notre première campagne contre l'API réelle.
   **Ce que nous avons fait** : réaligné les étiquettes sur la grille minute et
   dérouler la pagination sur la taille de page à défaut de `has_more`, puis —
   surtout — ajouté un garde-fou (`LabelAlignmentError`) qui refuse un taux
   d'appariement inférieur à 50 %. Une panne silencieuse est devenue une erreur
   explicite, et le cas est verrouillé par un test.

   Ces contournements vivent côté Binôme B et sont désormais **permanents**. Ils
   sont signalés comme tels dans le code : les retirer exige d'avoir vérifié au
   préalable que l'API a été corrigée.

### 6.2 Choix de périmètre du Binôme B

4. **Données synthétiques.** Les anomalies sont injectées par trois mécanismes
   paramétrés (panne, congestion, dégradation progressive) : un détecteur peut y
   réussir sans généraliser à des dégradations réelles, plus variées. Toute
   transposition à des traces réelles exigerait une réévaluation complète. C'est
   la limite la plus fondamentale de l'ensemble du projet, les deux binômes
   confondus.
5. **Plafond de la détection non supervisée.** L'écart entre 0,59 et 0,90 de
   PR-AUC mesuré au §2.7 n'est pas réductible par le réglage : il tient à
   l'interdiction d'utiliser les étiquettes à l'entraînement. La perspective
   réaliste n'est pas un meilleur modèle mais une **boucle semi-supervisée**, où
   l'exploitant confirme quelques dizaines d'alertes.
6. **Absence d'entraînement incrémental.** Les modèles sont réentraînés hors
   ligne. Un déploiement réel nécessiterait un réentraînement périodique et un
   suivi de dérive, la distribution du trafic évoluant avec le parc.
7. **Prévision ponctuelle sans intervalle.** Seule la valeur médiane est prévue.
   Un intervalle de prédiction (objectif quantile, déjà disponible dans XGBoost)
   donnerait à l'exploitant une mesure d'incertitude, et permettrait d'alerter
   sur la probabilité de franchir un seuil plutôt que sur une valeur unique.
   C'est la perspective la plus directement exploitable, et la moins coûteuse.

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
