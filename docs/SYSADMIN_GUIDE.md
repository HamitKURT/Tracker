# System Administrator Guide

Complete setup and configuration guide for the Selenium Tracker log server infrastructure.

---

## Prerequisites

### System Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 4 GB | 8 GB+ |
| CPU | 2 cores | 4 cores |
| Disk | 20 GB | 50 GB+ |
| Docker | 24.0+ | Latest |
| Docker Compose | 2.20+ | Latest |

### Required Ports

| Port | Service | Description |
|------|---------|-------------|
| 6379 | Redis | Message queue |
| 8084 | Log Server | Receives browser events |
| 9200 | Elasticsearch | Search and storage |
| 5601 | Kibana | Visualization UI |

Ensure these ports are not in use and are accessible from web application servers.

---

## Quick Start

### Step 1: Clone and Configure

```bash
cd /path/to/seleniumtracker/Workarea/Tracker
cp .env.example .env
```

### Step 2: Edit Environment Variables

Open `.env` and configure at minimum:

```dotenv
# REQUIRED: Change these from defaults
ELASTIC_PASSWORD=SecurePassword123!
KIBANA_SYSTEM_PASSWORD=KibanaPass456!

# Adjust for your server's RAM (50% of system RAM, max 30GB)
ES_JAVA_OPTS=-Xms1g -Xmx4g
```

### Step 3: Start the Stack

**Production mode** (persistent data):
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

**Development mode** (ephemeral data):
```bash
docker compose -f docker-compose.dev.yml up -d --build
```

### Step 4: Monitor Startup

```bash
docker compose -f docker-compose.prod.yml logs -f kibana-deployer log-worker
```

Wait for these messages:
```
DEPLOYER - INFO - [Kibana] All dashboards deployed successfully!
WORKER   - INFO - Write alias 'selenium-events' is available.
WORKER   - INFO - Starting log consumption from queue 'selenium_logs'
```

### Step 5: Verify Health

```bash
docker compose -f docker-compose.prod.yml ps
```

All services should show `healthy` or `running`.

---

## Service Startup Order

Services start automatically in dependency order:

```
1. Redis + Elasticsearch        (infrastructure)
2. Kibana Deployer              (configures ES and Kibana)
3. Kibana                       (waits for deployer)
4. Log Server                   (waits for Redis)
5. Log Worker                   (waits for ES + Redis + Kibana)
```

You do not need to start services manually.

---

## Configuration Reference

### Security Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ELASTIC_PASSWORD` | `changeme` | Elasticsearch password - **MUST CHANGE** |
| `KIBANA_SYSTEM_PASSWORD` | `changeme` | Kibana system password - **MUST CHANGE** |

### Performance Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `ES_JAVA_OPTS` | `-Xms1g -Xmx4g` | Elasticsearch heap (50% of RAM, max 30GB) |
| `BATCH_SIZE` | `50` | Events per bulk index batch |
| `MAX_WAIT_TIME` | `2.0` | Max seconds before flushing batch |

Tuning recommendations:
- **4 GB server**: `-Xms512m -Xmx2g`
- **8 GB server**: `-Xms1g -Xmx4g`
- **16 GB server**: `-Xms2g -Xmx8g`
- **32 GB server**: `-Xms4g -Xmx16g`

### ILM (Index Lifecycle Management)

| Variable | Default | Description |
|----------|---------|-------------|
| `ILM_MAX_SIZE` | `1gb` | Rollover when index reaches this size |
| `ILM_MAX_AGE` | `7d` | Rollover when index is this old |
| `ILM_MAX_DOCS` | `5000000` | Rollover at this document count |
| `ILM_DELETE_AFTER` | `30d` | Auto-delete indices older than this |

### CORS Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ALLOWED_ORIGINS` | `*` | Allowed origins for cross-domain requests |

Examples:
```dotenv
# Allow all origins (development)
CORS_ALLOWED_ORIGINS=*

# Single origin
CORS_ALLOWED_ORIGINS=https://app.example.com

# Multiple origins
CORS_ALLOWED_ORIGINS=https://app1.example.com,https://app2.example.com,http://localhost:3000
```

### Port Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_PORT` | `6379` | Redis port |
| `ELASTICSEARCH_PORT` | `9200` | Elasticsearch port |
| `KIBANA_PORT` | `5601` | Kibana port |
| `LOG_SERVER_PORT` | `8084` | Log server port |

---

## Providing Information to Web Developers

After deployment, provide web developers with:

1. **Log Server IP Address**: Your server's IP address
2. **Port**: 8084 (or custom if changed)
3. **Integration Code**:

```html
<script src="/performance.js" data-logserver="http://[YOUR_SERVER_IP]:8084"></script>
```

Example with real IP:
```html
<script src="/performance.js" data-logserver="http://10.0.0.50:8084"></script>
```

4. **The `performance.js` file**: Located in the project root directory

Also provide them with:
- [WEBAPP_QUICKSTART.md](WEBAPP_QUICKSTART.md) - Integration guide
- [WEBAPP_TROUBLESHOOTING.md](WEBAPP_TROUBLESHOOTING.md) - Troubleshooting guide

---

## Service Management

### Starting Services

```bash
docker compose -f docker-compose.prod.yml up -d
```

### Stopping Services

```bash
docker compose -f docker-compose.prod.yml down
```

### Restarting All Services

```bash
docker compose -f docker-compose.prod.yml restart
```

### Restarting a Specific Service

```bash
docker compose -f docker-compose.prod.yml restart log-server
```

### Viewing Logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Specific service
docker compose -f docker-compose.prod.yml logs -f log-worker

# Last 100 lines
docker compose -f docker-compose.prod.yml logs --tail=100 elasticsearch
```

### Checking Service Status

```bash
docker compose -f docker-compose.prod.yml ps
```

---

## Monitoring

### Health Endpoints

| Endpoint | Expected Response |
|----------|-------------------|
| `http://localhost:8084/health` | `{"status": "healthy", "redis": "connected"}` |
| `http://localhost:9200/_cluster/health` | `{"status": "green"}` or `{"status": "yellow"}` |
| `http://localhost:5601/api/status` | `{"status": {"overall": {"level": "available"}}}` |

### Elasticsearch Monitoring

```bash
# Cluster health
curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200/_cluster/health?pretty

# Index status
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/_cat/indices/selenium-events-*?v&s=index'

# Document count
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/selenium-events-*/_count'

# ILM status
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/selenium-events-*/_ilm/explain' | python3 -m json.tool
```

### Redis Monitoring

```bash
# Queue length
docker exec redis redis-cli LLEN selenium_logs

# Queue info
docker exec redis redis-cli INFO
```

---

## Accessing Kibana

1. Open `http://[SERVER_IP]:5601`
2. Login with:
   - Username: `elastic`
   - Password: Your `ELASTIC_PASSWORD` value
3. Navigate to **Analytics** > **Dashboard**
4. Select **Selenium Monitoring Dashboard**

---

## Full Reset

To completely reset the system and start fresh:

```bash
# Stop and remove all containers, volumes, and data
docker compose -f docker-compose.prod.yml down -v

# Rebuild and start
docker compose -f docker-compose.prod.yml up -d --build
```

**Warning**: This deletes ALL data including Elasticsearch indices.

---

## Backup and Restore

See [README.md](../README.md) section "Backup and Restore — Complete Workflow" for detailed instructions on:
- Taking Elasticsearch snapshots
- Exporting data to NDJSON files
- Restoring data on another server

---

## Further Reading

- [README.md](../README.md) - Full project documentation
- [SYSADMIN_TROUBLESHOOTING.md](SYSADMIN_TROUBLESHOOTING.md) - Server troubleshooting
- [ANALYSIS_GUIDE.md](../ANALYSIS_GUIDE.md) - Elasticsearch field reference and KQL queries
