"""
Orchestration du pipeline bout-en-bout : nettoyage -> features.
Version simple (semaine 2) à faire évoluer vers Apache Airflow (semaine 3)
si le niveau du binôme le permet.

Usage:
    python -m src.orchestration.run_pipeline                # une exécution
    python -m src.orchestration.run_pipeline --loop --every 300   # boucle toutes les 5 min
"""

import argparse
import sys
import time
from datetime import datetime

sys.path.append(".")
from src.preparation.clean_prepare import clean_and_prepare
from src.preparation.build_features import build_features


def run_once():
    print(f"[{datetime.utcnow().isoformat()}] Démarrage du pipeline")
    clean_and_prepare()
    build_features()
    print(f"[{datetime.utcnow().isoformat()}] Pipeline terminé")


def main():
    parser = argparse.ArgumentParser(description="Orchestration du pipeline NetQoS-AI")
    parser.add_argument("--loop", action="store_true", help="Exécution en boucle continue")
    parser.add_argument("--every", type=int, default=300, help="Intervalle en secondes si --loop")
    args = parser.parse_args()

    if args.loop:
        print(f"Orchestration en boucle toutes les {args.every}s. Ctrl+C pour arrêter.")
        try:
            while True:
                run_once()
                time.sleep(args.every)
        except KeyboardInterrupt:
            print("Arrêt de l'orchestration.")
    else:
        run_once()


if __name__ == "__main__":
    main()
