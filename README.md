# Tracker Telemetry System

The **Tracker** application acts as a comprehensive web telemetry system designed to track user interactions, DOM queries, and frontend metrics. Data is generated on the client via `tracker.js`, captured via HTTP POSTs by a Flask-backed `LogServer`, momentarily stored in `Redis`, and subsequently retrieved and properly indexed by `LogWorker` into an `Elasticsearch` database. Users can visualize these indexed events on `Kibana`.

---

## 🚀 Quick Start
A dedicated script creates the background Docker networks and launches all required services instantly.

Create .env file from .env.example with all required password and ports

```bash
docker compose -f docker-compose.dev.yml up -d 
```

- When you run this script:
  - The `tracker.js` testing grounds become visible at: `http://localhost:8081`
  - Kibana's visualization dashboard comes online at: `http://localhost:5601`

---
