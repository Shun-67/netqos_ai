# NetQoS-AI

Plateforme de supervision intelligente de la qualité de service (QoS) réseau.
Encadrant : **Prof. Niang**

---

## Démarrage rapide

```bash
git clone https://github.com/<votre-org>/netqos_ai.git
cd netqos_ai
cp .env.example .env
docker-compose up --build
```

- API Binôme A : `http://localhost:8000`
- Dashboard Binôme B : `http://localhost:8501`

---

## Structure

```
netqos_ai/
├── binome-a/          # Collecte, traitement, API REST
├── binome-b/          # Modèles IA, détection, prévision, dashboard
├── reports/           # Livrables communs (contrat d'interface, rapport)
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Convention Git

- Branches : `binome-a/nom-fonctionnalite` et `binome-b/nom-fonctionnalite`
- Merge sur `main` uniquement après validation

---

## Jalons

| Jalon | Livrable |
|-------|----------|
| J7  | Contrat d'interface figé + EDA |
| J14 | Baselines anomalie et prévision |
| J21 | Modèles avancés + dashboard |
| J30 | Soutenance finale |
