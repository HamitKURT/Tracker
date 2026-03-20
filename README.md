# Tracker Telemetry System

The **Tracker** application acts as a comprehensive web telemetry system designed to track user interactions, DOM queries, and frontend metrics. Data is generated on the client via `tracker.js`, captured via HTTP POSTs by a Flask-backed `LogServer`, momentarily stored in `Redis`, and subsequently retrieved and properly indexed by `LogWorker` into an `Elasticsearch` database. Users can visualize these indexed events on `Kibana`.

---

## 🚀 Quick Start
A dedicated script creates the background Docker networks and launches all required services instantly.

```bash
chmod +x manage.sh
./manage.sh start
```

- When you run this script:
  - The `tracker.js` testing grounds become visible at: `http://localhost:8081`
  - Kibana's visualization dashboard comes online at: `http://localhost:5601`

To generate some random data use `python3 slelenium_test.py`

To stop all Docker containers and python processes use `./manage.sh stop`

---

## 🔒 Security Configuration & Changing Passwords
We have specifically fortified the Tracker ecosystem using Elasticsearch `xpack` native security logic. The default user is `elastic` and the default password is `changeme`.

If you wish to deploy this to production, or rotate these credentials, you MUST change the passwords symmetrically across three files:

### 1. `docker-compose.yml`
This file instructs the docker initialization sequence what root password to use on boot for both Elasticsearch and Kibana connections.
Under the `environment` parameter in both services, edit the password string:
```yaml
      - ELASTIC_PASSWORD=changeme
      - KIBANA_PASSWORD=changeme
      - ELASTICSEARCH_PASSWORD=changeme
```

### 2. `manage.sh` (or `LogWorker/main.py`)
The ingestion worker must know the Elasticsearch database password or it cannot index events. Currently, it defaults to the known string. You can temporarily override it before running the stack by exporting flags to your host OS using the terminal:
```bash
export ES_USER="elastic"
export KIBANA_PASSWORD="YourNewPasswordHere!"
export ES_PASSWORD="YourNewPasswordHere!"
./manage.sh start
```

### 3. `deploy_kibana_dashboard.py`
This python file leverages an http requests module that talks directly to Kibana's internal API to create standard dashboards automatically. It needs authentication to successfully POST charts on startup.
Change line 6:
```python
AUTH = ("elastic", "YourNewPasswordHere!")
```

**⚠️ Important Docker Note:** If you change the password inside the `docker-compose.yml` file AFTER you've successfully booted Elasticsearch once, Docker will not honor the updated environment variable on a warm reset because the `.security` index volume has already been permanently cemented to disk. 

To forcefully enact the change on an already running docker instance, you must totally wipe its associated volumes by running `docker compose down -v` and bringing the system back up smoothly.
