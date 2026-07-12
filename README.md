# Auth-Scaler

Framework de recherche pour la scalabilité autonome de microservices.

## Phase 1 — Collecte de métriques

La Phase 1 est finalisée et testable. Voir la documentation complète :

**[phase1-collector-service/README.md](phase1-collector-service/README.md)**

### Démarrage rapide

```bash
docker compose up -d postgres-phase1 order-service payment-service notification-service phase1-collector
python scripts/test_phase1.py
```

Interface web : http://localhost:8001/
