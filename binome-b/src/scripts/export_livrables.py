"""
Export des livrables Markdown aux formats de remise : Word (.docx) pour les
documents, PowerPoint (.pptx) pour le support de soutenance.

Le contrat d'interface du Binôme A est un `.docx` : c'est visiblement le format
attendu pour les documents remis à l'encadrement. Les rapports du Binôme B sont
en revanche rédigés en Markdown, parce qu'ils sont **générés** depuis les
fichiers de métriques et versionnés dans Git — un `.docx` binaire ne se
régénérerait pas et ne se relirait pas dans un diff.

Ce script réconcilie les deux : le Markdown reste la source, le `.docx` est un
artefact d'export, reproductible par une commande. Toute correction se fait donc
dans le Markdown puis se réexporte, ce qui évite deux versions divergentes du
même document.

Conversion assurée par pandoc, qui préserve les tableaux, les blocs de code et
les figures (embarquées dans le fichier, donc transportables).

Usage (depuis binome-b/) :
    python -m src.scripts.export_livrables
    python -m src.scripts.export_livrables --fichier ../reports/rapport_projet_netqos_ai.md
    python -m src.scripts.export_livrables --sans-toc
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from src.config import REPORTS_DIR

SORTIE_DIR = REPORTS_DIR / "docx"

# Documents exportés par défaut, avec le titre et le sous-titre à inscrire en
# page de garde. Le Markdown ne porte pas ces métadonnées : les y ajouter
# polluerait les rapports générés.
DOCUMENTS = {
    "rapport_eda.md": {
        "title": "Rapport d'analyse exploratoire des données",
        "subtitle": "NetQoS-AI — Binôme B — Jalon J7",
    },
    "rapport_evaluation_modeles.md": {
        "title": "Rapport d'évaluation des modèles",
        "subtitle": "NetQoS-AI — Binôme B — Livrable §6.3",
    },
    # Livrable commun du §6.1, signé par les deux binômes : la clé `author`
    # remplace la valeur par défaut, qui ne désigne que le binôme B.
    "rapport_projet_netqos_ai.md": {
        "title": "Rapport de projet — NetQoS-AI",
        "subtitle": "Plateforme intelligente de surveillance et de prévision de la QoS réseau",
        "author": "Binôme A & Binôme B — ESMT / DETIC",
    },
    "deroule_demo.md": {
        "title": "Déroulé de la démonstration live",
        "subtitle": "NetQoS-AI — Livrable §6.1 — Jalon J30",
        "author": "Binôme A & Binôme B — ESMT / DETIC",
    },
    # Support de soutenance : seul livrable exporté en PowerPoint. Le gabarit
    # Word et la table des matières ne s'y appliquent pas, et les séparateurs
    # de diapositives viennent des titres de niveau 1 du Markdown.
    "support_soutenance.md": {
        "title": "NetQoS-AI — Soutenance",
        "subtitle": "Supervision intelligente de la QoS réseau",
        "author": "Binôme A & Binôme B — ESMT / DETIC",
        "format": "pptx",
    },
}

# Documents de `binome-b/` : chemins relatifs à ce dossier, pas à reports/.
DOCUMENTS_BINOME_B = {
    "NOTICE_DASHBOARD.md": {
        "title": "Notice d'utilisation du tableau de bord",
        "subtitle": "NetQoS-AI — Binôme B — Livrable §6.3",
    },
    "GUIDE_TEST.md": {
        "title": "Guide de test du travail du Binôme B",
        "subtitle": "NetQoS-AI — Procédure de vérification en cinq niveaux",
    },
}

AUTEUR = "Binôme B — Intelligence artificielle & restitution"

# Gabarit de style, construit par `src/scripts/build_docx_template.py` à partir
# des conventions relevées dans le contrat d'interface du Binôme A. S'il est
# absent, l'export se fait avec le style par défaut de pandoc.
GABARIT = Path(__file__).resolve().parent.parent.parent / "assets" / "gabarit_netqos.docx"


def destination_pour(source: Path, metadonnees: dict) -> Path:
    """Chemin de sortie, dont l'extension découle du format demandé."""
    extension = metadonnees.get("format", "docx")
    return SORTIE_DIR / f"{source.stem}.{extension}"


def verifier_pandoc() -> str:
    """Retourne le chemin de pandoc, ou interrompt avec un message utile."""
    chemin = shutil.which("pandoc")
    if chemin is None:
        print(
            "pandoc est introuvable. C'est lui qui effectue la conversion.\n"
            "  Windows : winget install --id JohnMacFarlane.Pandoc\n"
            "  ou téléchargement direct : https://pandoc.org/installing.html",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return chemin


def exporter(
    source: Path, destination: Path, metadonnees: dict, avec_toc: bool = True
) -> None:
    """Convertit un fichier Markdown en .docx ou en .pptx."""
    est_diapos = metadonnees.get("format") == "pptx"
    commande = [
        "pandoc",
        str(source),
        "-o",
        str(destination),
        # Les chemins d'images des rapports sont relatifs au dossier du document :
        # sans cela, les figures ne seraient pas retrouvées ni embarquées.
        f"--resource-path={source.parent}",
        # GFM pour les documents, écrits dans cette variante. Le support de
        # soutenance a besoin du Markdown de pandoc, seule variante qui
        # interprète les divs `::: notes` en notes de l'orateur.
        "--from=markdown" if est_diapos else "--from=gfm",
        "--metadata",
        f"title={metadonnees['title']}",
        "--metadata",
        f"subtitle={metadonnees['subtitle']}",
        "--metadata",
        f"author={metadonnees.get('author', AUTEUR)}",
        "--metadata",
        "lang=fr-FR",
    ]
    if est_diapos:
        # Un titre de niveau 1 ouvre une diapositive : sans cette option, pandoc ne
        # découpe rien. Le gabarit Word et la table des matières n'ont pas de
        # sens ici, on ne les passe donc pas.
        commande += ["--slide-level=1"]
    else:
        if GABARIT.exists():
            commande += [f"--reference-doc={GABARIT}"]
        if avec_toc:
            commande += ["--toc", "--toc-depth=3"]

    resultat = subprocess.run(commande, capture_output=True, text=True)
    if resultat.returncode != 0:
        print(f"  ÉCHEC {source.name} : {resultat.stderr.strip()[:200]}", file=sys.stderr)
        return

    taille_ko = destination.stat().st_size / 1024
    print(f"  {destination.name:42s} {taille_ko:7.0f} Ko   <- {source.name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export des livrables en .docx et .pptx"
    )
    parser.add_argument(
        "--fichier",
        type=str,
        default=None,
        help="Exporter un seul fichier Markdown au lieu de la liste par défaut",
    )
    parser.add_argument(
        "--sans-toc", action="store_true", help="Ne pas insérer de table des matières"
    )
    args = parser.parse_args()

    verifier_pandoc()
    SORTIE_DIR.mkdir(parents=True, exist_ok=True)
    avec_toc = not args.sans_toc

    if args.fichier:
        source = Path(args.fichier).resolve()
        if not source.exists():
            print(f"Fichier introuvable : {source}", file=sys.stderr)
            raise SystemExit(1)
        metadonnees = DOCUMENTS.get(source.name) or DOCUMENTS_BINOME_B.get(source.name) or {
            "title": source.stem.replace("_", " ").capitalize(),
            "subtitle": "NetQoS-AI — Binôme B",
        }
        print(f"Export vers {SORTIE_DIR} :")
        exporter(source, destination_pour(source, metadonnees), metadonnees, avec_toc)
        return

    print(f"Export vers {SORTIE_DIR} :")
    binome_b_dir = Path(__file__).resolve().parent.parent.parent

    for nom, metadonnees in DOCUMENTS.items():
        source = REPORTS_DIR / nom
        if source.exists():
            exporter(source, destination_pour(source, metadonnees), metadonnees, avec_toc)
        else:
            print(f"  (absent, ignoré) {nom}")

    for nom, metadonnees in DOCUMENTS_BINOME_B.items():
        source = binome_b_dir / nom
        if source.exists():
            exporter(source, destination_pour(source, metadonnees), metadonnees, avec_toc)
        else:
            print(f"  (absent, ignoré) {nom}")

    print(
        "\nLe Markdown reste la source de vérité : ces fichiers sont des exports.\n"
        "Après toute modification d'un rapport, réexécuter cette commande."
    )


if __name__ == "__main__":
    main()
