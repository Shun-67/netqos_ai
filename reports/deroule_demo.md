# Déroulé de la démonstration live — NetQoS-AI

**Livrable §6.1** · jalon J30 · à répéter au moins une fois en conditions
réelles avant la soutenance.

Ce document est un script opératoire, pas une documentation. Il suppose la
plateforme déjà installée. Pour une première installation, voir
[`../binome-a/README.md`](../binome-a/README.md) (pipeline et API) et
[`../binome-b/README.md`](../binome-b/README.md) (modèles et tableau de bord).

Durée visée : **8 à 10 minutes**, hors questions.

---

## 1. La règle qui rend une démo fiable

Une démonstration live échoue presque toujours pour l'une de trois raisons : un
port occupé, une base vide, ou un conteneur resté actif avec une configuration
périmée. Les trois sont prévisibles, donc évitables.

**Le principe retenu : tout est vérifié avant de projeter.** Les commandes de la
section 2 se lancent trente minutes avant la soutenance, sur la machine qui
servira. Pendant la démonstration, on ne tape que les commandes de la section 3,
dont on connaît déjà la sortie.

---

## 2. Trente minutes avant — mise en état et vérifications

### 2.1. Arrêt propre de l'existant

Un `docker compose down` seul **ne suffit pas** : le service `airflow` est
déclaré sous le profil `full` et le simulateur de flux sous le profil `stream`.
Sans mention de ces profils, leurs conteneurs survivent à l'« arrêt complet » —
et un conteneur Airflow démarré avant une modification du `docker-compose.yml`
tourne avec l'ancienne configuration.

```bash
docker compose --profile full --profile stream down
docker ps                       # doit ne lister aucun conteneur netqos_*
```

### 2.2. Choix des ports

Les ports 5432 et 8000 sont fréquemment occupés. Les surcharger **avant** de
démarrer, plutôt que de diagnostiquer un échec de bind en direct.

```bash
# PowerShell
$env:POSTGRES_HOST_PORT = "5433"
$env:API_PORT           = "8010"
$env:DASHBOARD_PORT     = "8511"
$env:AIRFLOW_PORT       = "8081"   # si la démo inclut Airflow
```

```bash
# bash
export POSTGRES_HOST_PORT=5433 API_PORT=8010 DASHBOARD_PORT=8511 AIRFLOW_PORT=8081
```

Ne pas confondre `POSTGRES_HOST_PORT` (port publié sur la machine) et
`POSTGRES_PORT` (port interne au réseau Docker, toujours 5432).

**Noter les ports retenus** : toutes les URL de la section 3 en dépendent.

### 2.3. Démarrage et attente de l'état sain

```bash
docker compose up -d --build
docker compose ps               # attendre "healthy" sur timescaledb et api
```

Ne pas enchaîner avant que la base soit `healthy` : l'API démarre plus vite
qu'elle et son premier appel échouerait.

### 2.4. Vérification de l'API

```bash
curl http://localhost:8010/api/v1/health
curl "http://localhost:8010/api/v1/cells"
curl "http://localhost:8010/api/v1/features?limit=1"
```

Attendu : `health` répond, `cells` renvoie cinq cellules, `features` renvoie une
ligne avec `total` proche de 100 800.

**Si `total` vaut 0 ou si `cells` est vide, la base est vide** — passer à la
section 2.5. Sinon, sauter à 2.6.

### 2.5. Repeupler la base

Cas d'un volume neuf, ou recréé. Depuis `binome-a/` :

```bash
python src/generator/synthetic_generator.py --cells 5 --days 14 \
    --out data/raw/historical_kpi.csv
python -m src.ingestion.batch_ingest --file data/raw/historical_kpi.csv
python -m src.orchestration.run_pipeline
```

Compter **trois à quatre minutes** pour le pipeline. Hors conteneur,
`POSTGRES_HOST=localhost` est requis, et le port est celui choisi en 2.2 :

```bash
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python -m src.orchestration.run_pipeline
```

> **Panne connue.** Si l'API répond
> `password authentication failed for user "netqos"`, le mot de passe du `.env`
> ne correspond plus à celui gravé dans le volume PostgreSQL lors de son premier
> démarrage. PostgreSQL n'initialise ses identifiants qu'une seule fois. Sortie
> de secours, **qui détruit les données** :
>
> ```bash
> docker compose --profile full --profile stream down
> docker volume rm netqos_ai_timescale_data
> docker compose up -d --build
> ```
>
> Puis repeupler comme ci-dessus. Prévoir dix minutes : ne pas tenter cela en
> direct devant le jury.

### 2.6. Vérification du tableau de bord

Ouvrir `http://localhost:8511`, aller directement à l'onglet **Intégration** et
vérifier qu'il annonce la source `api` et l'URL attendue. S'il annonce un mode
dégradé, l'API n'est pas joignable depuis le conteneur : contrôler
`API_BASE_URL` dans le `docker-compose.yml` (le nom de service `api`, pas
`localhost`).

Parcourir les six onglets une fois, pour que le cache Streamlit soit chaud — le
premier chargement de l'historique est le plus lent.

### 2.7. Airflow, si la démonstration l'inclut

```bash
docker compose --profile full up -d airflow
docker exec netqos_airflow cat /opt/airflow/standalone_admin_password.txt
```

Ouvrir `http://localhost:8081` (le port choisi en 2.2), se connecter (`admin` +
mot de passe ci-dessus),
**activer le DAG `netqos_pipeline`** et attendre qu'une exécution au moins soit
verte. Une grille vide ne démontre rien.

### 2.8. Régénérer les livrables si les modèles ont été réentraînés

Les rapports citent les chiffres de `reports/metrics/`. Depuis `binome-b/` :

```bash
python -m src.scripts.make_report      # rapports à jour
python -m src.scripts.export_livrables      # -> reports/docx/*.docx
```

### 2.9. Liste de contrôle avant de projeter

- [ ] `docker compose ps` : `timescaledb` et `api` sains
- [ ] `/api/v1/features` renvoie un `total` proche de 100 800
- [ ] tableau de bord accessible, onglet *Intégration* sur la source `api`
- [ ] six onglets parcourus une fois
- [ ] Airflow : DAG activé, au moins une exécution verte *(si inclus)*
- [ ] terminaux ouverts, dans les bons dossiers, historique de commandes vide
- [ ] navigateur : onglets déjà ouverts sur `/docs`, le dashboard, Airflow
- [ ] police du terminal agrandie
- [ ] notifications système coupées

---

## 3. Le déroulé, minuté

Trois terminaux et un navigateur. Terminal 1 à la racine du dépôt, terminal 2
dans `binome-a/`, terminal 3 dans `binome-b/`.

### T+0:00 — La plateforme démarre en une commande · 1 min

*Exigence §3.3 de la fiche : reproductibilité.*

Terminal 1 :

```bash
docker compose ps
```

> « Cinq services : la base de séries temporelles, l'API, le tableau de bord,
> l'orchestrateur et le simulateur de flux. Une seule commande les démarre —
> `docker compose up -d --build` — et c'est ce que le cahier des charges exige. »

Ne **pas** relancer `up` en direct : montrer l'état déjà sain.

### T+1:00 — Le pipeline a produit les données · 1 min 30

Terminal 2 :

```bash
curl http://localhost:8010/api/v1/health
curl "http://localhost:8010/api/v1/features?limit=2"
```

> « Cent mille mesures sur quatorze jours et cinq cellules, quarante-trois
> caractéristiques par point : moyennes glissantes, écarts-types, décalages,
> saisonnalité. »

Puis, dans le navigateur, `http://localhost:8010/docs` :

> « Neuf endpoints, documentation générée automatiquement. C'est la frontière
> entre les deux binômes : tout ce que le volet IA consomme passe par là. »

**Pointer `/eval/labels`** :

> « Celui-ci sert la vérité terrain, et il est réservé à l'évaluation. Aucun
> autre endpoint ne l'expose — c'est ce qui garantit que la détection est
> réellement non supervisée. »

### T+2:30 — L'intégration A ↔ B est réelle · 1 min

Navigateur, tableau de bord, onglet **Intégration** :

> « Cet onglet affiche la source de données active. Il indique `api` et l'URL du
> service : le tableau de bord lit bien l'API, pas un fichier local. C'est le
> critère du jalon J21. »

Mentionner le repli sans le déclencher :

> « Si l'API tombe, le tableau de bord recalcule les caractéristiques depuis les
> CSV et l'annonce à l'écran. Nous avons vérifié que les deux sources donnent
> des valeurs identiques — écart maximal nul sur les quarante-trois colonnes. »

### T+3:30 — Détection d'anomalies · 2 min

Onglet **KPI & anomalies**. Choisir une cellule, une fenêtre de 24 h.

> « Les points signalés sont ceux qu'Isolation Forest juge atypiques. Le modèle
> n'a jamais vu d'étiquette. »

Activer l'affichage de la vérité terrain :

> « Voici les vraies anomalies. La superposition n'est là que pour la
> démonstration — elle n'entre jamais dans l'entraînement. »

Bouger le curseur de sensibilité :

> « Ce curseur règle la part d'alertes visée. C'est le compromis entre détections
> manquées et fausses alertes, laissé à l'exploitant. »

Chiffre à énoncer :

> « Le jeu de seuils du contrat produit une fausse alerte toutes les deux heures.
> Le modèle en produit une tous les deux jours, et détecte les neuf épisodes du
> segment de test. »

### T+5:30 — Prévision et décision · 2 min

Onglet **Prévision**.

> « Cinq KPI, trois horizons. À trente minutes, XGBoost fait vingt et un pour
> cent d'erreur en moins que la persistance. »

Changer de modèle dans le sélecteur :

> « On peut comparer aux baselines en direct. La persistance reproduit la courbe
> avec un décalage ; le modèle anticipe les inflexions. »

Puis l'état QoS annoncé :

> « Et c'est là que la prévision devient une décision : les seuils du contrat
> sont appliqués aux valeurs prévues, ce qui annonce l'état à trente minutes avec
> quatre-vingt-deux pour cent d'exactitude — aussi fiable qu'à cinq minutes, mais
> dix fois plus de temps pour agir. »

### T+7:30 — Temps réel · 1 min 30

Terminal 3 — ou terminal 1 si le simulateur tourne dans Docker :

```bash
docker compose --profile stream up -d stream-simulator
```

Onglet **Temps réel** :

> « Le simulateur émet une mesure toutes les cinq secondes par cellule. Le
> tableau de bord interroge le flux et applique la détection aux mesures qui
> arrivent. »

Attendre visiblement un rafraîchissement.

> « Le rafraîchissement ne recharge que cette zone, pas la page : sans cela,
> chaque cycle relancerait le chargement de tout l'historique. »

### T+9:00 — Qualité des modèles · 1 min

Onglet **Qualité des modèles**.

> « Métriques d'évaluation, courbes précision-rappel, matrices de confusion. Le
> protocole est un découpage chronologique par cellule avec une purge de soixante
> minutes, et des garde-fous qui lèvent une exception plutôt que de produire un
> résultat faux. Soixante tests automatisés verrouillent ces invariants. »

**Fin de la démonstration.** Revenir au support pour les questions.

---

## 4. Points de repli

À décider **avant**, pas pendant.

| Symptôme | Repli immédiat |
|---|---|
| Un port refuse de se lier | relancer avec d'autres valeurs (§2.2) ; sinon, captures d'écran |
| L'API ne répond pas | `docker compose logs api --tail 30` ; si la cause n'est pas immédiate, basculer sur `NETQOS_DATA_SOURCE=local` et l'annoncer |
| Le tableau de bord annonce un mode dégradé | le **dire** et continuer : le repli est une fonctionnalité, pas une panne. Montrer l'onglet *Intégration* qui l'explique |
| Base vide | ne pas repeupler en direct (3 à 4 min) : passer aux onglets qui n'en dépendent pas, ou aux captures |
| `password authentication failed` | **ne pas** tenter la recréation du volume en direct (10 min) : captures d'écran |
| Le flux temps réel ne monte pas | `docker compose logs stream-simulator --tail 20` ; sinon décrire et passer |
| Airflow inaccessible | le retirer du déroulé : ce n'est pas le critère du J21 |
| Une projection lente fige tout | commenter le support pendant le chargement, ne pas recliquer |

**Filet général : préparer les captures d'écran des six onglets** et les garder
ouvertes dans un onglet du navigateur. Une démonstration commentée sur captures
vaut mieux qu'un écran vide.

---

## 5. Répartition entre les deux binômes

La note de soutenance comporte une part individuelle (§8 de la fiche) : chacun
présente et manipule son propre périmètre.

| Séquence | Qui |
|---|---|
| T+0:00 démarrage de la stack | A |
| T+1:00 pipeline, API, OpenAPI | A |
| T+2:30 intégration A ↔ B | **les deux** — A présente l'API servie, B ce qu'il en consomme |
| T+3:30 détection d'anomalies | B |
| T+5:30 prévision et état QoS | B |
| T+7:30 flux temps réel | **les deux** — A lance le simulateur, B montre la détection en direct |
| T+9:00 qualité des modèles | B |
| Airflow *(si inclus)* | A |

---

## 6. Questions probables, et où se trouve la réponse

| Question | Réponse courte | Détail |
|---|---|---|
| Pourquoi pas 90 % de performance ? | l'oracle supervisé atteint 0,905 : l'écart est le prix de la contrainte non supervisée | rapport de projet §6.8 |
| Pourquoi l'autoencodeur n'est-il pas déployé ? | il ne bat pas la baseline (0,363 contre 0,586) ; le §8.2 de la fiche l'interdit alors | §6.3 |
| Comment excluez-vous la fuite de données ? | purge de 60 min, `fit()` sans argument d'étiquettes, 60 tests | §3.3, annexes D et E |
| Pourquoi 43 % du temps en « critique » ? | seuils calibrés KPI par KPI sans tenir compte de la règle du pire KPI | §6.2 |
| Pourquoi Prophet et LSTM absents ? | choix de périmètre documenté, pas une impossibilité | §7.4 |
| Le pipeline tient-il en production ? | non en l'état : il retraite tout l'amont ; idempotent mais coûteux | §7.3 |
| Que se passe-t-il si l'API tombe ? | trois modes, repli annoncé, sources vérifiées équivalentes | §3.3 |
| Comment obtient-on les documents en Word ? | `python -m src.scripts.export_livrables` | README, section Livrables |

---

## 7. Après la soutenance

```bash
docker compose --profile full --profile stream down
```

Ajouter `-v` uniquement pour détruire aussi le volume de données — ce qui impose
un repeuplement complet au prochain démarrage.
