# Auth-Scaler — Phase 1 : Collecte de métriques

Service de collecte des métriques d'utilisation des ressources (CPU, RAM, latence, débit) pour alimenter la chaîne de test de scalabilité Auth-Scaler.

## Objectif

La Phase 1 :

1. interroge des microservices via leurs endpoints Actuator ;
2. génère une charge HTTP configurable (champ `transactions` = TPS cible) ;
3. construit des matrices NumPy `(n_services × n_samples)` ;
4. persiste les résultats sur disque et en PostgreSQL.

## Architecture

```
Frontend (8001/)
    │
    ▼
Phase 1 API (FastAPI)
    ├── ActuatorCollector  → polling CPU/RAM/latence/débit
    ├── LoadGenerator      → charge HTTP concurrente (TPS)
    ├── MatrixFactory      → matrices .npy
    └── PostgreSQL         → suivi des jobs
         │
         ▼
Microservices cibles (order-service, payment-service, ...)
```

## Prérequis

- Docker et Docker Compose
- Python 3.10+ (pour le script de test local)

## Démarrage rapide

### 1. Lancer l'environnement de test

Depuis la racine du projet :

```bash
docker compose up -d postgres-phase1 order-service payment-service notification-service phase1-collector
```

Services disponibles :

| Service | URL |
|---------|-----|
| Phase 1 API | http://localhost:8001 |
| Interface web | http://localhost:8001/ |
| PostgreSQL Phase 1 | localhost:5433 |
| Mock order-service | http://order-service:8080 (réseau Docker) |
| Mock payment-service | http://payment-service:8080 |
| Mock notification-service | http://notification-service:8080 |

### 2. Vérifier la santé du service

```bash
curl http://localhost:8001/health
```

Réponse attendue :

```json
{"status":"healthy","service":"phase1-collector","mode":"actuator"}
```

### 3. Lancer une collecte via config.json

Le fichier `config/config.json` contient 3 services mock avec TPS configurés.

```bash
curl -X POST http://localhost:8001/api/v1/collect \
  -H "Content-Type: application/json" \
  -d "{\"use_config\": true, \"duration_seconds\": 30, \"interval_seconds\": 5, \"base_port\": 8080}"
```

### 4. Lancer une collecte manuelle (API)

```bash
curl -X POST http://localhost:8001/api/v1/collect \
  -H "Content-Type: application/json" \
  -d "{
    \"services\": [
      {
        \"nom\": \"order-service\",
        \"url_cpu\": \"/actuator/metrics/system.cpu.usage\",
        \"url_ram\": \"/actuator/metrics/jvm.memory.used\",
        \"url_lat\": \"/actuator/health\",
        \"url_bw\": \"/actuator/health\",
        \"transactions\": 25
      }
    ],
    \"duration_seconds\": 20,
    \"interval_seconds\": 5,
    \"base_port\": 8080
  }"
```

### 5. Tester via l'interface web

1. Ouvrir http://localhost:8001/
2. Renseigner durée, intervalle, port
3. Ajouter les services ou cliquer sur **Collecter depuis config.json**
4. Consulter le résultat et les logs affichés

### 6. Script de test automatisé

```bash
pip install requests numpy
python scripts/test_phase1.py
```

## Vérifier les résultats

### Via API

```bash
# Liste des jobs
curl http://localhost:8001/api/v1/jobs

# Détail d'un job
curl http://localhost:8001/api/v1/jobs/<job_id>

# Statut et dimensions des matrices
curl http://localhost:8001/api/v1/status/<job_id>
```

### Via fichiers

Les matrices sont stockées dans `data/raw/` :

```
data/raw/
  M_CPU_<job_id>.npy
  M_RAM_<job_id>.npy
  M_LAT_<job_id>.npy
  M_BW_<job_id>.npy
  metadata_<job_id>.json
```

### Inspection Python

```python
import numpy as np

job_id = "20250711_120000"
cpu = np.load(f"data/raw/M_CPU_{job_id}.npy")
ram = np.load(f"data/raw/M_RAM_{job_id}.npy")
lat = np.load(f"data/raw/M_LAT_{job_id}.npy")
bw = np.load(f"data/raw/M_BW_{job_id}.npy")

print("CPU:", cpu)
print("NaN CPU:", np.isnan(cpu).sum())
```

Un test réussi doit montrer :

- peu ou pas de valeurs `NaN` ;
- des valeurs CPU/RAM qui évoluent si `transactions > 0` ;
- des matrices de forme `(3, 6)` pour 30s / 5s avec 3 services.

## API Phase 1

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/health` | Santé du service |
| GET | `/api/v1/config` | Lire `config.json` |
| POST | `/api/v1/collect` | Lancer une collecte |
| GET | `/api/v1/jobs` | Lister les jobs |
| GET | `/api/v1/jobs/{job_id}` | Détail d'un job |
| GET | `/api/v1/status/{job_id}` | Matrices chargées depuis le disque |
| GET | `/api/v1/list` | Collections fichier |
| DELETE | `/api/v1/delete/{job_id}` | Supprimer une collection |
| GET | `/` | Interface web |

### Schéma `POST /api/v1/collect`

```json
{
  "services": [
    {
      "nom": "order-service",
      "url_cpu": "/actuator/metrics/system.cpu.usage",
      "url_ram": "/actuator/metrics/jvm.memory.used",
      "url_lat": "/actuator/health",
      "url_bw": "/actuator/health",
      "transactions": 20
    }
  ],
  "duration_seconds": 30,
  "interval_seconds": 5,
  "base_port": 8080,
  "job_id": "optional_custom_id",
  "use_config": false
}
```

- `use_config: true` → charge les services depuis `config/config.json`
- `transactions > 0` → active le générateur de charge HTTP pendant la collecte
- `url_lat` / `url_bw` → endpoints réellement utilisés pour latence et débit

## Configuration

Fichier : `config/config.json`

```json
{
  "ressources": {
    "cpu_cores": 4,
    "ram_gb": 8,
    "duree_collecte": 30,
    "interval_collecte": 5
  },
  "services": [
    {
      "nom": "order-service",
      "url_cpu": "/actuator/metrics/system.cpu.usage",
      "url_ram": "/actuator/metrics/jvm.memory.used",
      "url_lat": "/actuator/health",
      "url_bw": "/actuator/health",
      "transactions": 20
    }
  ]
}
```

Variables d'environnement utiles :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `DATABASE_URL` | PostgreSQL local | Connexion base |
| `FRONTEND_DIR` | `../frontend` | Dossier interface web |
| `CONFIG_PATH` | `config/config.json` | Fichier de configuration |
| `DATA_PATH` | `data/raw` | Dossier des matrices |

## Services mock inclus

Le dossier `mock-services/` fournit des microservices simulés compatibles Actuator :

- `/actuator/health`
- `/actuator/metrics/system.cpu.usage`
- `/actuator/metrics/jvm.memory.used`

Les métriques augmentent avec le nombre de requêtes reçues, ce qui permet d'observer l'effet de la charge générée par la Phase 1.

## Dépannage

| Problème | Cause probable | Solution |
|----------|----------------|----------|
| Matrices pleines de `NaN` | Services injoignables | Vérifier les noms Docker (`order-service`, pas `localhost`) |
| Erreur DB au démarrage | PostgreSQL pas prêt | `docker compose restart phase1-collector` |
| Frontend sans style | Volume frontend non monté | Vérifier `./frontend:/app/frontend` dans compose |
| Collecte lente | Normal | Durée = temps de blocage de l'API (ex. 30s) |
| `use_config` échoue | `config.json` vide | Remplir `nom` et URLs des services |

## Développement local (sans Docker)

```bash
cd phase1-collector-service
pip install -r requirements.txt

# Terminal 1 : mock service
cd ../mock-services
SERVICE_NAME=order-service uvicorn src.main:app --port 8080

# Terminal 2 : phase 1
cd ../phase1-collector-service
set FRONTEND_DIR=../frontend
set CONFIG_PATH=../config/config.json
set DATA_PATH=../data/raw
uvicorn src.main:app --port 8001
```

Puis lancer une collecte vers `order-service` (nécessite que le nom soit résolu — en local, utiliser `localhost` comme `nom` si le mock tourne en local).

## Intégration orchestrateur

L'orchestrateur appelle désormais la Phase 1 avec :

```json
{
  "use_config": true,
  "duration_seconds": 30,
  "interval_seconds": 5,
  "base_port": 8080
}
```

## Prochaines étapes (hors Phase 1)

- Phase 2 : consommation des matrices `.npy`
- Collecte asynchrone via file de messages
- Support Prometheus en complément d'Actuator
- Tests unitaires automatisés (pytest)
