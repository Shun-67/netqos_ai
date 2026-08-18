"""
Dashboard NetQoS-AI — Binôme B.

Tableau de bord d'exploitation destiné à un exploitant réseau. Consomme
exclusivement l'API REST du Binôme A via `src.data.loader` (repli automatique
sur les CSV locaux tant que l'API n'est pas démarrée), applique les modèles
entraînés, et restitue :

  1. **Vue d'ensemble** — état QoS courant de chaque cellule, alertes actives ;
  2. **KPI & anomalies** — séries temporelles, score d'atypicité, alertes ;
  3. **Prévision** — trajectoire prévue à 5/15/30 min et état QoS annoncé ;
  4. **Qualité des modèles** — métriques d'évaluation, pour que l'exploitant
     sache quel degré de confiance accorder à ce qu'il lit ;
  5. **Diagnostic d'intégration** — source de données active, version du contrat.

Lancement (depuis binome-b/) :
    streamlit run src/dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permet `streamlit run src/dashboard/app.py` depuis binome-b/ : Streamlit
# exécute le fichier directement, donc le dossier racine du paquet n'est pas
# dans sys.path.
BINOME_B_DIR = Path(__file__).resolve().parent.parent.parent
if str(BINOME_B_DIR) not in sys.path:
    sys.path.insert(0, str(BINOME_B_DIR))

import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.config import (
    CONTRACT_VERSION,
    FORECAST_HORIZONS,
    KPI_UNITS,
    KPIS,
    METRICS_DIR,
    MODELS_DIR,
)
from src.data import loader
from src.features.preprocessing import prepare_features
from src.models import anomaly as A
from src.models import forecast as F
from src.models import qos_state

st.set_page_config(page_title="NetQoS-AI — Supervision QoS", layout="wide", page_icon="📡")

DEFAULT_DETECTOR = "isolation_forest"


# ==================================================================
# Chargement (mis en cache)
# ==================================================================
@st.cache_data(ttl=60, show_spinner="Chargement des données…")
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, dict, str]:
    history = loader.load_history()
    features = prepare_features(loader.load_features())
    thresholds = loader.get_thresholds()
    return history, features, thresholds, loader.source_description()


@st.cache_data(ttl=300, show_spinner=False)
def load_labels_safe() -> pd.DataFrame:
    """Vérité terrain, si l'endpoint d'évaluation est disponible.

    Sert uniquement à afficher les épisodes réels en surimpression, pour la
    démonstration. Un déploiement réel n'aurait pas cette information.
    """
    try:
        return loader.load_labels()
    except Exception:
        return pd.DataFrame()


@st.cache_resource(show_spinner="Chargement des modèles…")
def load_models() -> tuple[dict, object | None]:
    """Charge les modèles entraînés depuis `src/models/saved/`."""
    detectors = {}
    for path in sorted(MODELS_DIR.glob("anomaly_*.joblib")):
        name = path.stem.replace("anomaly_", "")
        try:
            detectors[name] = joblib.load(path)
        except Exception as exc:  # modèle produit par une version antérieure
            st.warning(f"Détecteur `{name}` illisible : {exc}")

    forecaster = None
    forecast_path = MODELS_DIR / "forecast_xgboost.joblib"
    if forecast_path.exists():
        try:
            forecaster = joblib.load(forecast_path)
        except Exception as exc:
            st.warning(f"Modèle de prévision illisible : {exc}")

    return detectors, forecaster


@st.cache_data(ttl=300, show_spinner=False)
def load_metrics() -> dict[str, pd.DataFrame]:
    """Charge les tableaux de métriques produits par les scripts d'évaluation."""
    files = {
        "anomalie": "anomalie_resultats.csv",
        "prevision": "prevision_resultats.csv",
        "etat_qos": "prevision_etat_qos.csv",
        "episodes": "anomalie_analyse_episodes.csv",
    }
    out = {}
    for key, filename in files.items():
        path = METRICS_DIR / filename
        if path.exists():
            out[key] = pd.read_csv(path)
    return out


# ==================================================================
# Barre latérale
# ==================================================================
def sidebar(history: pd.DataFrame, detectors: dict) -> dict:
    st.sidebar.title("📡 NetQoS-AI")
    st.sidebar.caption(f"Contrat d'interface v{CONTRACT_VERSION} — Binôme B")

    cells = sorted(history["cell_id"].unique())
    cell_id = st.sidebar.selectbox("Cellule", cells, index=0)

    max_ts = history["ts"].max()
    hours = st.sidebar.slider("Fenêtre d'observation (heures)", 6, 168, 48, step=6)
    start = max_ts - pd.Timedelta(hours=hours)

    detector_name = st.sidebar.selectbox(
        "Détecteur d'anomalies",
        list(detectors.keys()) or ["aucun"],
        index=(list(detectors.keys()).index(DEFAULT_DETECTOR) if DEFAULT_DETECTOR in detectors else 0),
    )

    contamination = st.sidebar.slider(
        "Sensibilité — part d'alertes visée (%)",
        0.1, 10.0, 2.0, step=0.1,
        help=(
            "Fixe le seuil d'alerte au quantile correspondant du score. Plus la "
            "valeur est basse, moins d'alertes sont émises — et plus le risque "
            "de manquer un épisode augmente."
        ),
    )

    show_truth = st.sidebar.checkbox(
        "Afficher la vérité terrain",
        value=False,
        help=(
            "Superpose les épisodes d'anomalie réels issus de /eval/labels. "
            "Réservé à la démonstration : cette information n'existe pas en "
            "exploitation réelle."
        ),
    )

    st.sidebar.divider()
    return {
        "cell_id": cell_id,
        "start": start,
        "end": max_ts,
        "detector_name": detector_name,
        "contamination": contamination / 100,
        "show_truth": show_truth,
    }


# ==================================================================
# Onglet 1 — Vue d'ensemble
# ==================================================================
def tab_overview(history: pd.DataFrame, features: pd.DataFrame, thresholds: dict, options: dict, detectors: dict) -> None:
    st.subheader("État courant du réseau")

    latest = history.sort_values("ts").groupby("cell_id").tail(1).reset_index(drop=True)
    labelled = qos_state.classify_frame(latest, thresholds)

    columns = st.columns(len(labelled))
    for column, (_, row) in zip(columns, labelled.iterrows()):
        state = str(row["qos_state"])
        icon = {"bon": "🟢", "dégradé": "🟠", "critique": "🔴"}[state]
        cause = qos_state.dominant_cause(row, thresholds)
        column.metric(
            label=f"{icon} {row['cell_id']}",
            value=state.capitalize(),
            delta=cause if cause != "aucun" else "tous KPI dans la plage",
            delta_color="off",
        )

    st.caption(
        f"Dernière mesure : {latest['ts'].max()} (UTC) · "
        f"règle d'agrégation : état de la cellule = pire état parmi les {len(KPIS)} KPI"
    )

    # --- Alertes actives ---
    st.subheader("Alertes d'anomalie actives")
    detector = detectors.get(options["detector_name"])
    if detector is None:
        st.info("Aucun détecteur entraîné. Lancez `python -m src.scripts.train_anomaly`.")
        return

    recent = features[features["ts"] >= options["end"] - pd.Timedelta(hours=6)].reset_index(drop=True)
    if recent.empty:
        st.info("Pas de features disponibles sur les 6 dernières heures.")
        return

    scores = detector.score(recent)
    threshold = float(np.quantile(detector.score(features), 1 - options["contamination"]))
    alerts = recent.loc[scores >= threshold, ["ts", "cell_id"]].copy()
    alerts["score"] = scores[scores >= threshold].round(4)

    if alerts.empty:
        st.success("Aucune anomalie détectée sur les 6 dernières heures.")
    else:
        summary = (
            alerts.groupby("cell_id")
            .agg(alertes=("score", "size"), score_max=("score", "max"), derniere=("ts", "max"))
            .sort_values("alertes", ascending=False)
        )
        st.dataframe(summary, width="stretch")
        st.caption(
            f"Seuil d'alerte = quantile {(1 - options['contamination']) * 100:.1f} % "
            f"du score `{options['detector_name']}` sur tout l'historique disponible."
        )


# ==================================================================
# Onglet 2 — KPI & anomalies
# ==================================================================
def tab_kpi(
    history: pd.DataFrame,
    features: pd.DataFrame,
    thresholds: dict,
    options: dict,
    detectors: dict,
) -> None:
    cell_id, start, end = options["cell_id"], options["start"], options["end"]

    window = history[
        (history["cell_id"] == cell_id) & (history["ts"] >= start) & (history["ts"] <= end)
    ].sort_values("ts")
    feature_window = features[
        (features["cell_id"] == cell_id) & (features["ts"] >= start) & (features["ts"] <= end)
    ].sort_values("ts").reset_index(drop=True)

    if window.empty:
        st.warning("Aucune donnée sur la fenêtre sélectionnée.")
        return

    detector = detectors.get(options["detector_name"])
    scores, threshold, alert_mask = None, None, None
    if detector is not None and not feature_window.empty:
        scores = detector.score(feature_window)
        threshold = float(np.quantile(detector.score(features), 1 - options["contamination"]))
        alert_mask = scores >= threshold

    figure = make_subplots(
        rows=len(KPIS) + 1,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.025,
        row_heights=[1] * len(KPIS) + [0.9],
        subplot_titles=[f"{k} ({KPI_UNITS[k]})" for k in KPIS] + ["Score d'atypicité"],
    )

    for index, kpi in enumerate(KPIS, start=1):
        figure.add_trace(
            go.Scatter(
                x=window["ts"], y=window[kpi], name=kpi, mode="lines",
                line=dict(width=1, color="#2c6fb5"), showlegend=False,
            ),
            row=index, col=1,
        )
        bounds = thresholds.get(kpi, {})
        for key, colour in (("good_max", "#e8a33d"), ("degraded_max", "#d1495b"),
                            ("good_min", "#e8a33d"), ("degraded_min", "#d1495b")):
            if key in bounds:
                figure.add_hline(
                    y=bounds[key], line=dict(color=colour, width=1, dash="dash"),
                    row=index, col=1,
                )
        # Alertes reportées sur chaque KPI, pour que l'exploitant voie
        # immédiatement quel indicateur accompagne l'alerte.
        if alert_mask is not None and alert_mask.any():
            alert_ts = feature_window.loc[alert_mask, "ts"]
            aligned = window[window["ts"].isin(alert_ts)]
            figure.add_trace(
                go.Scatter(
                    x=aligned["ts"], y=aligned[kpi], mode="markers", name="alerte",
                    marker=dict(size=4, color="#d1495b"), showlegend=(index == 1),
                ),
                row=index, col=1,
            )

    if scores is not None:
        figure.add_trace(
            go.Scatter(
                x=feature_window["ts"], y=scores, mode="lines", name="score",
                line=dict(width=1, color="#6a4c93"), showlegend=False,
            ),
            row=len(KPIS) + 1, col=1,
        )
        figure.add_hline(
            y=threshold, line=dict(color="#d1495b", width=1.2, dash="dot"),
            row=len(KPIS) + 1, col=1,
        )

    # Vérité terrain en surimpression (démonstration uniquement)
    if options["show_truth"]:
        labels = load_labels_safe()
        if not labels.empty:
            truth = labels[
                (labels["cell_id"] == cell_id)
                & (labels["ts"] >= start)
                & (labels["ts"] <= end)
                & labels["is_anomaly"]
            ]
            for ts in truth["ts"]:
                figure.add_vline(x=ts, line=dict(color="rgba(209,73,91,0.16)", width=2))

    figure.update_layout(height=180 * (len(KPIS) + 1), margin=dict(t=40, b=30, l=10, r=10),
                         hovermode="x unified")
    st.plotly_chart(figure, width="stretch")

    if alert_mask is not None:
        st.caption(
            f"{int(alert_mask.sum())} alertes sur {len(feature_window):,} points "
            f"({alert_mask.mean() * 100:.2f} %) · détecteur `{options['detector_name']}` · "
            f"seuil {threshold:.4f}"
        )

    # --- Explication des alertes (autoencodeur uniquement) ---
    if isinstance(detector, A.AutoencoderDetector) and alert_mask is not None and alert_mask.any():
        st.subheader("Causes probables des alertes")
        explanation = detector.explain(feature_window).loc[alert_mask]
        explanation.insert(0, "ts", feature_window.loc[alert_mask, "ts"].to_numpy())
        st.dataframe(explanation.tail(20), width="stretch", hide_index=True)
        st.caption("Features contribuant le plus à l'erreur de reconstruction.")


# ==================================================================
# Onglet 3 — Prévision
# ==================================================================
def tab_forecast(history: pd.DataFrame, features: pd.DataFrame, thresholds: dict, options: dict, forecaster) -> None:
    if forecaster is None:
        st.info("Aucun modèle de prévision entraîné. Lancez `python -m src.scripts.train_forecast`.")
        return

    cell_id, start, end = options["cell_id"], options["start"], options["end"]
    feature_window = features[
        (features["cell_id"] == cell_id) & (features["ts"] >= start) & (features["ts"] <= end)
    ].sort_values("ts").reset_index(drop=True)

    if feature_window.empty:
        st.warning("Aucune feature sur la fenêtre sélectionnée.")
        return

    kpi = st.selectbox("KPI à prévoir", KPIS, index=KPIS.index("latency"))

    figure = go.Figure()
    observed = history[
        (history["cell_id"] == cell_id) & (history["ts"] >= start) & (history["ts"] <= end)
    ].sort_values("ts")
    figure.add_trace(
        go.Scatter(x=observed["ts"], y=observed[kpi], name="observé", mode="lines",
                   line=dict(width=1.6, color="black"))
    )

    palette = ["#2c6fb5", "#e8a33d", "#6a4c93"]
    for colour, horizon in zip(palette, FORECAST_HORIZONS):
        try:
            prediction = forecaster.predict(feature_window, kpi, horizon)
        except KeyError:
            continue
        # La prévision faite à t concerne t + h : on la décale pour qu'elle
        # s'aligne sur l'instant qu'elle décrit.
        figure.add_trace(
            go.Scatter(
                x=feature_window["ts"] + pd.Timedelta(minutes=horizon),
                y=prediction, name=f"prévu à +{horizon} min", mode="lines",
                line=dict(width=1, color=colour, dash="dot"),
            )
        )

    bounds = thresholds.get(kpi, {})
    for key, colour in (("good_max", "#e8a33d"), ("degraded_max", "#d1495b"),
                        ("good_min", "#e8a33d"), ("degraded_min", "#d1495b")):
        if key in bounds:
            figure.add_hline(y=bounds[key], line=dict(color=colour, width=1, dash="dash"),
                             annotation_text=key, annotation_position="right")

    figure.update_layout(
        height=430, margin=dict(t=30, b=30, l=10, r=10), hovermode="x unified",
        yaxis_title=f"{kpi} ({KPI_UNITS[kpi]})", xaxis_title="Horodatage (UTC)",
    )
    st.plotly_chart(figure, width="stretch")

    # --- État QoS annoncé ---
    st.subheader("État QoS annoncé")
    st.caption(
        "Les seuils du contrat sont appliqués aux KPI **prévus** : c'est ce qui "
        "transforme une prévision numérique en information d'exploitation."
    )

    last = feature_window.tail(1).reset_index(drop=True)
    columns = st.columns(len(FORECAST_HORIZONS))
    for column, horizon in zip(columns, FORECAST_HORIZONS):
        predicted = pd.DataFrame({"cell_id": last["cell_id"]})
        try:
            for target_kpi in KPIS:
                predicted[target_kpi] = forecaster.predict(last, target_kpi, horizon)
        except KeyError:
            column.warning(f"+{horizon} min indisponible")
            continue

        classified = qos_state.classify_frame(predicted, thresholds)
        state = str(classified["qos_state"].iloc[0])
        icon = {"bon": "🟢", "dégradé": "🟠", "critique": "🔴"}[state]
        cause = qos_state.dominant_cause(classified.iloc[0], thresholds)
        column.metric(
            label=f"{icon} dans {horizon} min",
            value=state.capitalize(),
            delta=cause if cause != "aucun" else "tous KPI dans la plage",
            delta_color="off",
        )

    metrics = load_metrics()
    if "etat_qos" in metrics:
        st.caption("Fiabilité mesurée de cette annonce sur le segment de test :")
        table = metrics["etat_qos"].copy()
        table.columns = ["horizon (min)", "exactitude de l'état", "part de critiques manqués", "n"]
        st.dataframe(table, width="stretch", hide_index=True)


# ==================================================================
# Onglet 4 — Qualité des modèles
# ==================================================================
def tab_quality() -> None:
    metrics = load_metrics()
    if not metrics:
        st.info(
            "Aucune métrique disponible. Lancez `python -m src.scripts.train_anomaly` "
            "puis `python -m src.scripts.train_forecast`."
        )
        return

    st.subheader("Détection d'anomalies")
    if "anomalie" in metrics:
        table = metrics["anomalie"]
        columns = [
            "detecteur", "point_de_fonctionnement", "precision", "rappel", "f1",
            "pr_auc", "taux_alerte_pct", "rappel_episode", "fausses_alertes_par_heure",
        ]
        st.dataframe(
            table[[c for c in columns if c in table.columns]],
            width="stretch", hide_index=True,
        )
        st.caption(
            "PR-AUC (aire sous la courbe précision/rappel) est la métrique de "
            "référence ici : avec ~1,5 % d'anomalies, la ROC-AUC reste flatteuse "
            "même pour un détecteur inutilisable."
        )

    st.subheader("Prévision")
    if "prevision" in metrics:
        table = metrics["prevision"]
        scope = st.radio(
            "Périmètre d'évaluation", sorted(table["perimetre"].unique()), horizontal=True
        )
        subset = table[table["perimetre"] == scope]
        pivot = subset.pivot_table(
            index=["kpi", "horizon_min"], columns="modele",
            values="gain_mae_vs_persistance_pct",
        ).round(2)
        st.dataframe(pivot, width="stretch")
        st.caption(
            "Gain de MAE en % relatif à la persistance. Positif = meilleur que "
            "la persistance. C'est le critère qui décide si un modèle mérite "
            "d'être déployé."
        )

    if "episodes" in metrics:
        st.subheader("Analyse des épisodes d'anomalie (segment de test)")
        st.dataframe(metrics["episodes"], width="stretch", hide_index=True)


# ==================================================================
# Onglet 5 — Intégration
# ==================================================================
def tab_integration(source: str, detectors: dict, forecaster) -> None:
    st.subheader("Source de données")
    if source.startswith("API"):
        st.success(f"Connecté à l'API du Binôme A — {source}")
    else:
        st.warning(
            f"**Mode dégradé — {source}**\n\n"
            "L'API du Binôme A n'est pas joignable. Le dashboard fonctionne sur "
            "les CSV locaux, dont le schéma reproduit le contrat v1.1. Pour "
            "basculer sur l'API : démarrer les services du Binôme A, puis "
            "recharger la page."
        )

    st.subheader("Configuration active")
    st.dataframe(
        pd.DataFrame(
            [
                {"paramètre": "Version du contrat", "valeur": CONTRACT_VERSION},
                {"paramètre": "Source résolue", "valeur": loader.active_source()},
                {"paramètre": "URL de l'API", "valeur": loader.config.API_BASE_URL},
                {"paramètre": "Mode demandé (NETQOS_DATA_SOURCE)", "valeur": loader.config.DATA_SOURCE},
                {"paramètre": "Détecteurs chargés", "valeur": ", ".join(detectors) or "aucun"},
                {"paramètre": "Modèle de prévision", "valeur": "xgboost" if forecaster else "aucun"},
                {"paramètre": "Horizons de prévision", "valeur": ", ".join(f"{h} min" for h in FORECAST_HORIZONS)},
            ]
        ),
        width="stretch",
        hide_index=True,
    )

    st.subheader("Endpoints consommés")
    st.dataframe(
        pd.DataFrame(
            [
                {"endpoint": "GET /health", "usage": "détection de disponibilité, bascule de source"},
                {"endpoint": "GET /cells", "usage": "liste des cellules du sélecteur"},
                {"endpoint": "GET /thresholds", "usage": "seuils de classification de l'état QoS"},
                {"endpoint": "GET /kpi/history", "usage": "séries nettoyées affichées et cibles de prévision"},
                {"endpoint": "GET /features", "usage": "entrées des modèles d'anomalie et de prévision"},
                {"endpoint": "GET /eval/labels", "usage": "vérité terrain — évaluation et démonstration seulement"},
            ]
        ),
        width="stretch",
        hide_index=True,
    )


# ==================================================================
# Entrée
# ==================================================================
def main() -> None:
    st.title("NetQoS-AI — Supervision intelligente de la QoS réseau")

    try:
        history, features, thresholds, source = load_data()
    except Exception as exc:
        st.error(
            f"Impossible de charger les données : {exc}\n\n"
            "Vérifiez que l'API du Binôme A répond, ou qu'un CSV est disponible "
            "dans `binome-a/data/raw/` ou `binome-b/data/samples/`."
        )
        st.stop()

    detectors, forecaster = load_models()
    options = sidebar(history, detectors)

    if not source.startswith("API"):
        st.info(
            f"⚠️ Mode dégradé : {source}. L'API du Binôme A n'est pas joignable — "
            "voir l'onglet « Intégration ».",
            icon="⚠️",
        )

    tabs = st.tabs(
        ["Vue d'ensemble", "KPI & anomalies", "Prévision", "Qualité des modèles", "Intégration"]
    )
    with tabs[0]:
        tab_overview(history, features, thresholds, options, detectors)
    with tabs[1]:
        tab_kpi(history, features, thresholds, options, detectors)
    with tabs[2]:
        tab_forecast(history, features, thresholds, options, forecaster)
    with tabs[3]:
        tab_quality()
    with tabs[4]:
        tab_integration(source, detectors, forecaster)


main()
