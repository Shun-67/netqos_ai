"""
Génération du schéma d'architecture annoté (§4.4 de la fiche de stage).

La fiche impose trois éléments : les **six couches** du §4.1, les **flux de
données** entre elles, et la **frontière A ↔ B matérialisée par l'API**. Le
schéma sert à la fois au rapport et à la soutenance.

Produit par script plutôt que dessiné dans un outil graphique, pour trois
raisons : il se régénère si l'architecture évolue, chaque libellé porte le nom
réel d'un fichier ou d'une table du dépôt (donc rien n'est inventé), et il se
relit dans un diff — un `.png` dessiné à la main ne se vérifie pas.

Sortie : `reports/architecture_schema.png`, chemin auquel le README de la racine
renvoyait déjà.

Usage (depuis binome-b/) :
    python -m src.scripts.make_architecture
"""

from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.patches as patches
import matplotlib.pyplot as plt

from src.config import REPORTS_DIR

SORTIE = REPORTS_DIR / "architecture_schema.png"

# Palette : une famille de bleus pour le Binôme A, une de violets pour le B. La
# distinction doit être immédiate — c'est la première chose que le schéma doit
# faire comprendre.
COULEUR_A = "#dce8f5"
BORDURE_A = "#2c6fb5"
COULEUR_B = "#e8e0f0"
BORDURE_B = "#6a4c93"
COULEUR_COMPOSANT = "#ffffff"
ROUGE = "#d1495b"
ORANGE = "#e8a33d"
GRIS = "#666666"

# Les six couches du §4.1, dans l'ordre du flux. Chaque composant porte le nom du
# fichier ou de la table qui l'implémente réellement.
COUCHES = [
    {
        "titre": "1 · INGESTION",
        "binome": "A",
        "detail": "collecte batch + flux simulé",
        "composants": [
            "synthetic_generator.py\n5 cellules × 14 j, 1 pt/min\nanomalies injectées",
            "batch_ingest.py\nCSV → base",
            "stream_simulator.py\n1 pt / 5 s, en continu",
        ],
    },
    {
        "titre": "2 · PRÉPARATION",
        "binome": "A",
        "detail": "nettoyage, resampling, ingénierie de caractéristiques",
        "composants": [
            "clean_prepare.py\nbornes physiques, doublons,\ninterpolation (≤ 3 pts),\nresampling à 1 min",
            "build_features.py\nmoyennes 5/15/30 min, lags 1/5/10,\nécarts-types, saisonnalité",
        ],
    },
    {
        "titre": "3 · STOCKAGE",
        "binome": "A",
        "detail": "TimescaleDB — 3 hypertables, clé primaire (ts, cell_id)",
        "composants": [
            "raw_kpi_measurements\n+ is_anomaly\n(vérité terrain)",
            "clean_kpi_measurements\n+ is_missing",
            "kpi_features\n43 colonnes",
        ],
    },
    {
        "titre": "4 · SERVICE",
        "binome": "A",
        "detail": "API REST FastAPI · /api/v1 · OpenAPI sur /docs",
        "composants": [
            "/health · /cells\n/thresholds",
            "/kpi/history · /features\n/kpi/latest\n(paginés)",
            "/kpi/stream\n/kpi/stream/info",
            "/eval/labels\nvérité terrain,\névaluation seule",
        ],
    },
    {
        "titre": "5 · INTELLIGENCE",
        "binome": "B",
        "detail": "modèles entraînés et servis",
        "composants": [
            "api_client.py → loader.py\nunique point de contact\n(+ repli CSV local)",
            "preprocessing.py\nsplits.py\nencodages cycliques,\ndécoupage chronologique\n+ purge 60 min",
            "anomaly.py\nIsolation Forest ✔\nDBSCAN\nautoencodeur",
            "forecast.py\nXGBoost ✔\nARIMA · persistance\nmoyenne mobile",
            "qos_state.py\nbon / dégradé / critique\nrègle du pire KPI",
        ],
    },
    {
        "titre": "6 · RESTITUTION",
        "binome": "B",
        "detail": "tableau de bord interactif et alertes",
        "composants": [
            "app.py — Streamlit, 6 onglets\n"
            "Vue d'ensemble · Temps réel · KPI & anomalies · Prévision · Qualité des modèles · Intégration",
        ],
    },
]


def _boite(ax, x, y, largeur, hauteur, texte, couleur, bordure, taille=7.5):
    ax.add_patch(
        patches.FancyBboxPatch(
            (x, y), largeur, hauteur,
            boxstyle="round,pad=0.012,rounding_size=0.02",
            facecolor=couleur, edgecolor=bordure, linewidth=1.1,
        )
    )
    ax.text(
        x + largeur / 2, y + hauteur / 2, texte,
        ha="center", va="center", fontsize=taille, linespacing=1.45,
    )


def dessiner() -> None:
    fig, ax = plt.subplots(figsize=(15.5, 13.5))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    # Les bandes commencent assez bas pour que le sous-titre ne soit pas recouvert.
    y = 92.0
    x_gauche, largeur_bande = 13.5, 74.0
    ECART = 2.2
    # Écart élargi entre les couches 4 et 5 : la frontière et ses deux lignes de
    # légende doivent y tenir sans mordre sur les bandes voisines.
    ECART_FRONTIERE = 7.0

    positions_y: dict[str, tuple[float, float]] = {}
    composants: dict[tuple[str, int], tuple[float, float, float]] = {}

    for index, couche in enumerate(COUCHES):
        # La couche 6 n'a qu'un composant : lui donner la même hauteur qu'aux
        # autres déséquilibrerait le schéma.
        hauteur = 7.5 if index == len(COUCHES) - 1 else 11.5
        y -= hauteur
        positions_y[couche["titre"]] = (y, y + hauteur)
        est_a = couche["binome"] == "A"
        fond = COULEUR_A if est_a else COULEUR_B
        bordure = BORDURE_A if est_a else BORDURE_B

        ax.add_patch(
            patches.FancyBboxPatch(
                (x_gauche, y), largeur_bande, hauteur,
                boxstyle="round,pad=0.01,rounding_size=0.015",
                facecolor=fond, edgecolor=bordure, linewidth=1.7,
            )
        )

        # Titres placés À L'INTÉRIEUR de la bande : la gouttière de gauche reste
        # ainsi entièrement disponible pour l'encart d'orchestration.
        ax.text(
            x_gauche + 1.6, y + hauteur - 1.9, couche["titre"],
            ha="left", va="center", fontsize=10.5, fontweight="bold", color=bordure,
        )
        ax.text(
            x_gauche + 16.0, y + hauteur - 1.9, couche["detail"],
            ha="left", va="center", fontsize=7.4, color=GRIS, style="italic",
        )
        ax.text(
            x_gauche + largeur_bande - 1.6, y + hauteur - 1.9,
            f"Binôme {couche['binome']}",
            ha="right", va="center", fontsize=9, fontweight="bold",
            color=bordure, alpha=0.8,
        )

        n = len(couche["composants"])
        marge = 1.8
        largeur_dispo = largeur_bande - 2 * marge
        largeur_c = (largeur_dispo - (n - 1) * 1.5) / n
        hauteur_c = hauteur - 5.2
        for i, composant in enumerate(couche["composants"]):
            xc = x_gauche + marge + i * (largeur_c + 1.5)
            _boite(
                ax, xc, y + 1.6, largeur_c, hauteur_c,
                composant, COULEUR_COMPOSANT, bordure,
                taille=6.5 if n >= 4 else 7.3,
            )
            composants[(couche["titre"], i)] = (
                xc + largeur_c / 2, y + 1.6, y + 1.6 + hauteur_c,
            )

        if index < len(COUCHES) - 1:
            ecart = ECART_FRONTIERE if couche["titre"].startswith("4") else ECART
            # zorder élevé : la flèche qui franchit la frontière doit rester
            # visible par-dessus le fond blanc du titre de celle-ci. Le
            # franchissement *est* l'appel HTTP, c'est donc l'élément à ne pas
            # masquer.
            ax.annotate(
                "", xy=(50, y - ecart + 0.4), xytext=(50, y - 0.4),
                arrowprops=dict(arrowstyle="-|>", linewidth=2.1, color=GRIS),
                zorder=7,
            )
            y -= ecart

    # ------------------------------------------------------------------
    # Frontière A <-> B, dans l'écart élargi entre les couches 4 et 5
    # ------------------------------------------------------------------
    y_frontiere = (positions_y["4 · SERVICE"][0] + positions_y["5 · INTELLIGENCE"][1]) / 2

    ax.plot(
        [3, 97], [y_frontiere, y_frontiere],
        color=ROUGE, linewidth=2.6, linestyle=(0, (7, 4)), zorder=5,
    )
    ax.text(
        50, y_frontiere + 1.1,
        "FRONTIÈRE A ↔ B  —  contrat d'interface v1.1, figé le 10/08/2026",
        ha="center", va="bottom", fontsize=9.4, fontweight="bold", color=ROUGE,
        bbox=dict(facecolor="white", edgecolor="none", pad=2.5), zorder=6,
    )
    ax.text(
        50, y_frontiere - 1.4,
        "seul franchissement autorisé : HTTP sur /api/v1   ·   aucun accès SQL, aucun import de code entre les deux moitiés",
        ha="center", va="top", fontsize=7.4, color=ROUGE, style="italic",
        bbox=dict(facecolor="white", edgecolor="none", pad=2.0), zorder=6,
    )

    # ------------------------------------------------------------------
    # Chemin isolé de la vérité terrain : de la table brute vers /eval/labels,
    # et vers nulle part ailleurs. C'est la garantie centrale du contrat, elle
    # doit donc être tracée et non seulement écrite.
    # ------------------------------------------------------------------
    x_raw, bas_raw, _ = composants[("3 · STOCKAGE", 0)]
    x_eval, _, haut_eval = composants[("4 · SERVICE", 3)]

    ax.annotate(
        "", xy=(x_eval, haut_eval), xytext=(x_raw, bas_raw),
        arrowprops=dict(
            arrowstyle="-|>", linewidth=1.8, color=ROUGE, linestyle="dashed",
            connectionstyle="angle,angleA=-90,angleB=180,rad=4",
        ),
        zorder=4,
    )
    # Fond blanc et zorder au-dessus de la flèche : sans cela le trait
    # horizontal barre le libellé et le rend illisible.
    ax.text(
        x_raw + 2.0, bas_raw - 1.15,
        "is_anomaly — n'emprunte que ce chemin",
        ha="left", va="center", fontsize=7, color=ROUGE, fontweight="bold",
        bbox=dict(facecolor="white", edgecolor="none", pad=1.5), zorder=8,
    )

    # ------------------------------------------------------------------
    # Orchestration, dans la gouttière de gauche désormais libre
    # ------------------------------------------------------------------
    y_prep = positions_y["2 · PRÉPARATION"]
    _boite(
        ax, 0.6, y_prep[0] + 1.6, 11.4, 8.3,
        "ORCHESTRATION\n\nAirflow\nDAG netqos_pipeline\ntoutes les 15 min\n\n(ou run_pipeline.py)",
        "#fff4e0", ORANGE, taille=6.5,
    )
    ax.annotate(
        "", xy=(x_gauche - 0.3, y_prep[0] + 5.7), xytext=(12.2, y_prep[0] + 5.7),
        arrowprops=dict(arrowstyle="-|>", linewidth=1.5, color=ORANGE),
    )

    # ------------------------------------------------------------------
    # Titre et notes de lecture
    # ------------------------------------------------------------------
    ax.text(
        50, 99.4, "NetQoS-AI — Architecture en six couches",
        ha="center", va="top", fontsize=16, fontweight="bold",
    )
    ax.text(
        50, 95.8,
        "Plateforme de surveillance et de prévision de la qualité de service réseau"
        "   ·   ESMT / DETIC 2025-2026",
        ha="center", va="top", fontsize=8.6, color=GRIS,
    )

    notes = (
        "Notes de lecture\n"
        "•  Les flèches grises portent le flux principal des données, de la collecte à la restitution.\n"
        "•  La flèche rouge en tirets isole `is_anomaly`, la vérité terrain : elle n'existe que dans la table brute et n'est exposée que par\n"
        "    /eval/labels. Le filtre par défaut de l'API la retire de toute autre réponse, et un garde-fou côté B (LeakageError) refuse qu'elle\n"
        "    atteigne une matrice de features. Elle ne sert qu'à calculer les métriques, jamais à entraîner : la détection d'anomalies est non\n"
        "    supervisée par construction, puisque la signature même de fit() n'accepte aucune étiquette.\n"
        "•  ✔ désigne le modèle retenu à l'issue de l'évaluation. L'autoencodeur, plus complexe, ne bat pas l'Isolation Forest.\n"
        "•  Le repli CSV local de la couche 5 permet au Binôme B de travailler quand l'API est indisponible, en servant exactement le même schéma."
    )
    ax.text(
        2.5, positions_y["6 · RESTITUTION"][0] - 2.8, notes,
        ha="left", va="top", fontsize=7.2, color="#333333", linespacing=1.7,
        bbox=dict(facecolor="#f7f7f7", edgecolor="#cccccc", boxstyle="round,pad=0.7"),
    )

    fig.savefig(SORTIE, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    dessiner()
    taille_ko = SORTIE.stat().st_size / 1024
    print(f"Schéma écrit : {SORTIE.relative_to(REPORTS_DIR.parent)} ({taille_ko:.0f} Ko)")
    # Sans réencodage, le caractère « ↔ » fait échouer le print sur une console
    # Windows en cp1252, alors que le PNG a bien été écrit.
    message = (
        "Couvre les trois exigences du §4.4 : six couches, flux de données, "
        "frontière A <-> B."
    )
    print(message.encode("utf-8", "replace").decode(sys.stdout.encoding or "utf-8", "replace"))


if __name__ == "__main__":
    main()
