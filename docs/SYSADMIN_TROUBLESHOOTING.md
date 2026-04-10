# System Administrator Troubleshooting

Troubleshooting guide for server-side and Docker-related issues.

---

## Docker Issues

### Containers Not Starting

**Symptoms:**
- `docker compose up` fails
- Containers exit immediately

**Solutions:**

1. **Check Docker is running:**
```bash
docker info
```

2. **Check Docker Compose version:**
```bash
docker compose version
# Requires 2.20+
```

3. **Check for port conflicts:**
```bash
# Check if ports are in use
lsof -i :6379
lsof -i :8084
lsof -i :9200
lsof -i :5601
```

4. **Check container logs:**
```bash
docker compose -f docker-compose.prod.yml logs elasticsearch
docker compose -f docker-compose.prod.yml logs kibana-deployer
```

5. **Remove stale containers and try again:**
```bash
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build
```

### Port Conflicts

**Symptoms:**
- Error: `port is already allocated`

**Solutions:**

1. **Find the process using the port:**
```bash
lsof -i :8084
# or
netstat -tulpn | grep 8084
```

2. **Kill the conflicting process or change the port in `.env`:**
```dotenv
LOG_SERVER_PORT=8085  # Use a different port
```

### Memory Issues

**Symptoms:**
- Containers crash with OOM (Out of Memory)
- Elasticsearch fails to start

**Solutions:**

1. **Check available memory:**
```bash
free -h
```

2. **Reduce Elasticsearch heap size in `.env`:**
```dotenv
# For 4GB RAM server
ES_JAVA_OPTS=-Xms512m -Xmx2g
```

3. **Check Docker memory limits:**
```bash
docker stats --no-stream
```

---

## Elasticsearch Issues

### Not Starting / Not Healthy

**Symptoms:**
- `docker compose ps` shows elasticsearch as `unhealthy`
- Kibana deployer waiting indefinitely

**Solutions:**

1. **Check Elasticsearch logs:**
```bash
docker compose -f docker-compose.prod.yml logs elasticsearch
```

2. **Common cause: vm.max_map_count too low**

Check current value:
```bash
sysctl vm.max_map_count
```

Fix (required for Elasticsearch):
```bash
# Temporary (until reboot)
sudo sysctl -w vm.max_map_count=262144

# Permanent
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

3. **Disk space issues:**
```bash
df -h
# Elasticsearch needs at least 5% free disk space
```

4. **Permission issues on data volume:**
```bash
# Check volume
docker volume inspect tracker_es-data

# If needed, recreate the volume
docker compose -f docker-compose.prod.yml down -v
docker compose -f docker-compose.prod.yml up -d --build
```

### Cluster Health Yellow or Red

**Symptoms:**
- `curl localhost:9200/_cluster/health` shows status: "yellow" or "red"

**Solutions:**

**Yellow status** is normal for single-node clusters (no replica shards). This is expected.

**Red status** indicates data loss or corruption:
```bash
# Check which indices have issues
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/_cat/indices?v&health=red'

# Check unassigned shards
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason'
```

---

## Log Server Issues

### Not Receiving Events

**Symptoms:**
- Web apps report connection failures
- No events appearing in Elasticsearch

**Solutions:**

1. **Check log server is running:**
```bash
docker compose -f docker-compose.prod.yml ps log-server
```

2. **Test the health endpoint:**
```bash
curl http://localhost:8084/health
# Should return: {"status": "healthy", "redis": "connected"}
```

3. **Check log server logs:**
```bash
docker compose -f docker-compose.prod.yml logs log-server
```

4. **Verify Redis connection:**
```bash
docker exec redis redis-cli ping
# Should return: PONG
```

### CORS Errors

**Symptoms:**
- Browser console shows CORS policy errors
- Events not being sent from web apps

**Solutions:**

1. **Check current CORS configuration:**
```bash
grep CORS_ALLOWED_ORIGINS .env
```

2. **Update CORS configuration in `.env`:**
```dotenv
# For specific domains
CORS_ALLOWED_ORIGINS=https://app.example.com,https://app2.example.com

# For development (allow all)
CORS_ALLOWED_ORIGINS=*
```

3. **Restart log server:**
```bash
docker compose -f docker-compose.prod.yml restart log-server
```

---

## Redis Queue Issues

### Queue Growing / Not Processing

**Symptoms:**
- Queue length keeps increasing
- Events not appearing in Elasticsearch

**Solutions:**

1. **Check queue length:**
```bash
docker exec redis redis-cli LLEN selenium_logs
```

2. **Check log worker status:**
```bash
docker compose -f docker-compose.prod.yml ps log-worker
docker compose -f docker-compose.prod.yml logs log-worker
```

3. **Check Elasticsearch connection from worker:**
```bash
docker compose -f docker-compose.prod.yml logs log-worker | grep -i error
```

4. **Restart log worker:**
```bash
docker compose -f docker-compose.prod.yml restart log-worker
```

### Worker Not Processing Events

**Symptoms:**
- Log worker is running but queue is not draining

**Solutions:**

1. **Check worker logs for errors:**
```bash
docker compose -f docker-compose.prod.yml logs --tail=100 log-worker
```

2. **Check Elasticsearch is accepting writes:**
```bash
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/_cluster/health' | python3 -m json.tool
```

3. **Check write alias exists:**
```bash
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/_alias/selenium-events'
```

---

## Kibana Issues

### Not Accessible

**Symptoms:**
- Cannot open `http://localhost:5601`
- Connection refused or timeout

**Solutions:**

1. **Check Kibana is running:**
```bash
docker compose -f docker-compose.prod.yml ps kibana
```

2. **Check Kibana logs:**
```bash
docker compose -f docker-compose.prod.yml logs kibana
```

3. **Wait for Kibana to fully start** (can take 2-3 minutes):
```bash
docker compose -f docker-compose.prod.yml logs -f kibana
# Wait for "Server running at http://0.0.0.0:5601"
```

4. **Check Kibana health:**
```bash
curl -s http://localhost:5601/api/status | python3 -m json.tool
```

### No Data in Dashboards

**Symptoms:**
- Kibana loads but dashboards show no data
- "No results found" message

**Solutions:**

1. **Check data exists in Elasticsearch:**
```bash
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/selenium-events-*/_count'
```

2. **Check time range in Kibana:**
   - Dashboards default to "Last 15 minutes"
   - Expand the time range to "Last 24 hours" or "Last 7 days"

3. **Verify data view exists:**
   - Go to Stack Management > Data Views
   - Look for `selenium-events*`

4. **Check deployer ran successfully:**
```bash
docker compose -f docker-compose.prod.yml logs kibana-deployer | grep -i dashboard
```

---

## Recovery Procedures

### Full System Reset

To completely reset and start fresh:

```bash
# Stop everything and remove volumes
docker compose -f docker-compose.prod.yml down -v

# Remove any orphaned containers
docker system prune -f

# Rebuild and start
docker compose -f docker-compose.prod.yml up -d --build
```

### Restart All Services

```bash
docker compose -f docker-compose.prod.yml restart
```

### Rebuild Specific Service

```bash
# Rebuild and restart a single service
docker compose -f docker-compose.prod.yml up -d --build log-server
```

### Recover from Elasticsearch Failure

If Elasticsearch data is corrupted:

```bash
# 1. Stop all services
docker compose -f docker-compose.prod.yml down

# 2. Remove Elasticsearch volume (loses all data!)
docker volume rm tracker_es-data

# 3. Restart (deployer will recreate everything)
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Diagnostic Commands Summary

```bash
# Overall status
docker compose -f docker-compose.prod.yml ps

# All service logs
docker compose -f docker-compose.prod.yml logs

# Specific service logs
docker compose -f docker-compose.prod.yml logs -f log-worker

# Container resource usage
docker stats --no-stream

# Elasticsearch health
curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200/_cluster/health?pretty

# Redis queue length
docker exec redis redis-cli LLEN selenium_logs

# Log server health
curl http://localhost:8084/health

# Kibana status
curl -s http://localhost:5601/api/status | python3 -c "import sys,json; print(json.load(sys.stdin)['status']['overall']['level'])"
```

---

## Getting Help

If issues persist after trying these solutions:

1. Collect diagnostic information:
```bash
docker compose -f docker-compose.prod.yml ps > diag_ps.txt
docker compose -f docker-compose.prod.yml logs > diag_logs.txt 2>&1
```

2. Check system resources:
```bash
free -h > diag_memory.txt
df -h > diag_disk.txt
```

3. Review the error patterns in logs

4. Consult the main documentation:
   - [README.md](../README.md)
   - [SYSADMIN_GUIDE.md](SYSADMIN_GUIDE.md)
