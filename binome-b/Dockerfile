# Image du dashboard Streamlit (Binôme B).
FROM python:3.13-slim

WORKDIR /app

# Dépendances système : libgomp est requis par XGBoost et par le parallélisme
# de scikit-learn ; sans elle, l'import échoue à l'exécution.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# `--server.address 0.0.0.0` est indispensable dans un conteneur : Streamlit
# n'écoute que sur localhost par défaut, et le port publié resterait muet.
CMD ["streamlit", "run", "src/dashboard/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
