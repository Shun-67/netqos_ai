"""
Configuration pytest — rend le paquet `src` importable depuis les tests.

Les tests sont lancés depuis `binome-b/` (`python -m pytest`). Ce fichier place
le dossier courant en tête de `sys.path` afin que `import src...` fonctionne sans
installation du paquet.
"""

import sys
from pathlib import Path

BINOME_B_DIR = Path(__file__).resolve().parent
if str(BINOME_B_DIR) not in sys.path:
    sys.path.insert(0, str(BINOME_B_DIR))
