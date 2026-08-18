# Notice d'utilisation du tableau de bord NetQoS-AI

*Livrable §6.3 de la fiche de stage — destiné à un exploitant réseau, pas à un
développeur.*

---

## 1. À quoi sert ce tableau de bord

Il répond à trois questions d'exploitation :

1. **Où en est le réseau maintenant ?** État de chaque cellule : bon, dégradé ou
   critique.
2. **Quelque chose d'anormal se passe-t-il ?** Signalement des comportements
   atypiques, y compris ceux qui ne franchissent aucun seuil.
3. **Que va-t-il se passer dans 5, 15 ou 30 minutes ?** État annoncé, pour agir
   avant que les utilisateurs ne soient affectés.

Le tableau de bord **observe et prévoit ; il n'agit pas** sur le réseau — la
reconfiguration automatique est hors périmètre du projet (§3.4 de la fiche).

---

## 2. Démarrage

### Avec Docker, depuis la racine du dépôt

```bash
docker compose up --build
```

Puis ouvrir **http://localhost:8501**.

### Sans Docker, depuis `binome-b/`

```bash
pip install -r requirements.txt
streamlit run src/dashboard/app.py
```

### Prérequis pour que tout s'affiche

Les modèles doivent avoir été entraînés au moins une fois :

```bash
python -m src.scripts.train_anomaly
python -m src.scripts.train_forecast
```

Sans cela, les onglets « KPI & anomalies » et « Prévision » affichent un message
indiquant la commande à lancer — le tableau de bord ne plante pas.

---

## 3. Bandeau d'état de la source de données

En haut de page, un bandeau apparaît si le tableau de bord **ne parle pas à
l'API** du Binôme A :

> ⚠️ Mode dégradé : CSV local — historical_kpi.csv

Ce que cela signifie : l'API ne répond pas, et l'affichage repose sur des données
locales figées. Les courbes et les modèles fonctionnent, mais **rien n'est
temps réel**. En exploitation, ce bandeau doit être absent. L'onglet
« Intégration » indique précisément quoi vérifier.

Aucun bandeau = connexion à l'API établie.

---

## 4. Réglages (colonne de gauche)

| Réglage | Effet |
|---|---|
| **Cellule** | Cellule analysée dans les onglets « KPI & anomalies » et « Prévision ». |
| **Fenêtre d'observation** | Profondeur d'historique affichée, de 6 h à 7 jours. |
| **Détecteur d'anomalies** | Modèle utilisé. `isolation_forest` est le modèle retenu et recommandé. |
| **Sensibilité** | Part du temps que l'on accepte de voir en alerte. |
| **Afficher la vérité terrain** | Superpose les anomalies réelles. **Démonstration uniquement.** |

### Bien régler la sensibilité

C'est le seul réglage qui demande un arbitrage, et il n'a pas de bonne réponse
universelle :

- **valeur basse (0,5 %)** — peu d'alertes, chacune très probablement réelle,
  mais risque accru de manquer une dégradation naissante ;
- **valeur haute (5 %)** — presque aucune dégradation ne passe inaperçue, au prix
  d'alertes à trier.

**Recommandation : 2 %**, valeur pour laquelle les modèles ont été évalués. Le
détecteur retenu y produit environ **0,02 fausse alerte par heure**, soit une
tous les deux jours. L'onglet « Qualité des modèles » chiffre ce compromis.

### Sur la case « vérité terrain »

Elle affiche les anomalies réellement injectées dans les données de simulation,
lues via `GET /api/v1/eval/labels`. Cette information **n'existe pas sur un
réseau réel** : elle sert à montrer en soutenance que les alertes tombent au bon
endroit. À laisser décochée pour juger le tableau de bord en conditions réelles.

---

## 5. Les cinq onglets

### 5.1 Vue d'ensemble — *à consulter en premier*

Une vignette par cellule : 🟢 bon · 🟠 dégradé · 🔴 critique. Sous chaque état,
le **KPI responsable** et son écart au seuil, par exemple
`latency (+180 % vs seuil bon)` : cela indique immédiatement quoi regarder.

L'état d'une cellule est celui de **son pire KPI**. Un seul indicateur critique
suffit donc à faire passer la cellule en critique — comportement voulu en
supervision.

Dessous, les alertes d'anomalie des 6 dernières heures, agrégées par cellule
(nombre d'alertes, score maximal, horodatage de la dernière).

> **Important pour lire cet onglet.** Les seuils du contrat v1.1 classent
> actuellement 42,9 % du temps en « critique » et seulement 8,5 % en « bon ». Un
> grand nombre de vignettes rouges ne signifie donc pas nécessairement que le
> réseau va mal : les seuils sont trop stricts, et leur révision a été demandée
> au Binôme A. Pour juger d'une dégradation réelle, se fier en priorité aux
> **alertes d'anomalie** plutôt qu'à la couleur.

### 5.2 KPI & anomalies

Six graphiques synchronisés : les cinq KPI, puis le score d'atypicité.

- Ligne bleue : le KPI mesuré.
- Tirets orange / rouge : seuils « bon » et « dégradé » du contrat.
- Points rouges : instants en alerte, reportés sur **tous** les KPI pour voir d'un
  coup d'œil lesquels accompagnent l'alerte.
- Dernier graphique : score d'atypicité et seuil d'alerte en pointillés.

Survoler un point affiche les valeurs de tous les KPI au même instant (mode
comparatif activé).

Si le détecteur sélectionné est l'**autoencodeur**, un tableau supplémentaire
liste les features ayant le plus contribué à chaque alerte — utile pour motiver
un diagnostic. Les autres détecteurs ne fournissent pas cette décomposition.

### 5.3 Prévision

Trajectoire observée (noir) et prévisions à +5, +15 et +30 min (pointillés
colorés). **Les prévisions sont décalées pour s'aligner sur l'instant qu'elles
décrivent** : à un horodatage donné, on lit côte à côte la valeur réelle et ce
qui avait été annoncé pour cet instant.

Dessous, trois vignettes donnent l'**état QoS annoncé** à chaque horizon, obtenu
en appliquant les seuils du contrat aux KPI prévus. C'est l'information
opérationnelle : elle transforme une prévision numérique en décision.

Un tableau rappelle la fiabilité mesurée de cette annonce (environ 83 %
d'exactitude d'état, et 13–15 % de dégradations critiques manquées) — à garder en
tête avant d'agir sur la seule base d'une prévision.

### 5.4 Qualité des modèles

Métriques d'évaluation, pour que l'exploitant sache quelle confiance accorder à ce
qu'il lit. Deux lectures utiles :

- **Détection** : la colonne `pr_auc` est la métrique de référence. La ligne
  `seuils_contrat` montre ce que donnerait une supervision par seuils seuls —
  43 % du temps en alerte, une précision de 3 %.
- **Prévision** : `gain_mae_vs_persistance_pct`. Positif = le modèle fait mieux
  que « la valeur restera ce qu'elle est ». Le gain croît avec l'horizon, ce qui
  est le comportement attendu.

### 5.5 Intégration

Onglet de diagnostic, à ouvrir quand quelque chose semble anormal : source de
données active, URL de l'API, mode demandé, modèles chargés, liste des endpoints
consommés.

---

## 6. Incidents courants

| Symptôme | Cause probable | Correction |
|---|---|---|
| Bandeau « Mode dégradé » | API du Binôme A éteinte ou injoignable | `docker compose up -d api` ; vérifier `API_BASE_URL` dans l'onglet Intégration |
| « Aucun détecteur entraîné » | modèles absents de `src/models/saved/` | `python -m src.scripts.train_anomaly` |
| Onglet Prévision vide | modèle de prévision absent | `python -m src.scripts.train_forecast` |
| Onglet Qualité vide | métriques absentes de `reports/metrics/` | relancer les deux scripts d'entraînement |
| « Aucune donnée sur la fenêtre » | fenêtre plus récente que les données | élargir la fenêtre d'observation |
| Toutes les cellules en rouge | seuils v1.1 trop stricts (comportement connu) | se fier aux alertes d'anomalie ; révision v1.2 demandée au Binôme A |
| Page lente au premier chargement | calcul des features sur tout l'historique | résultats mis en cache 60 s ; les chargements suivants sont immédiats |

---

## 7. Ce que le tableau de bord ne fait pas

- Il **n'agit pas** sur le réseau (hors périmètre, §3.4).
- Il **ne remplace pas** un système d'alerting : aucune notification n'est émise
  hors de la page. Un envoi par courriel ou webhook serait une extension
  naturelle.
- Il **ne garantit pas** la détection de tout incident : environ 13 à 15 % des
  dégradations critiques ne sont pas annoncées à l'avance. Voir les limites au §6
  du rapport d'évaluation des modèles.
