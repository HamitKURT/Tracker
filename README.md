# Selenium Tracker

Browser telemetry and QA monitoring pipeline that captures events from web applications, routes them through a message queue, indexes them in Elasticsearch, and visualizes them in Kibana dashboards. Built for **Locked Shields 2026**.

## Architecture

```
Browser (performance.js)
    | XHR POST /events (batched JSON)
    v
Log Server (Flask, port 8084)
    | LPUSH to Redis list
    v
Redis Queue ("selenium_logs")
    | BRPOP (blocking pop)
    v
Log Worker (Python)
    | Bulk index via elasticsearch-py
    v
Elasticsearch (port 9200, index: "selenium-events")
    |
    v
Kibana (port 5601, dashboards auto-deployed)
```

## Services

| Service | Directory | Port | Description |
|---------|-----------|------|-------------|
| **web-app** | `web_app/` | 8081 | Flask demo app with `performance.js` tracker injected |
| **log-server** | `log_server/` | 8084 | Receives browser events and queues them to Redis |
| **log-worker** | `log_worker/` | — | Consumes Redis queue, bulk-indexes into Elasticsearch |
| **kibana-deployer** | `kibana_deployer/` | — | Configures ES mappings, data views, and deploys dashboards |
| **selenium-test** | `selenium_test/` | — | Headless Chrome test suite generating 25+ event categories |
| **redis** | *(image)* | 6379 | Event queue (redis:8.6-alpine) |
| **elasticsearch** | *(image)* | 9200 | Search and storage (9.3.2) |
| **kibana** | *(image)* | 5601 | Visualization UI (9.3.2) |

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env — at minimum change ELASTIC_PASSWORD and KIBANA_SYSTEM_PASSWORD

# 2a. Development
docker-compose -f docker-compose.dev.yml up -d

# 2b. Production (with persistent ES volumes)
docker-compose -f docker-compose.prod.yml up -d
```

Services start in dependency order automatically: Redis and Elasticsearch first, then Kibana Deployer configures everything, followed by Log Server, Log Worker, Web App, and Selenium Test.

### Accessing Services

| Service | URL |
|---------|-----|
| Web App | http://localhost:8081 |
| Kibana | http://localhost:5601 (login: `elastic` / your password) |
| Elasticsearch | http://localhost:9200 |
| Log Server Health | http://localhost:8084/health |

## Configuration

All configuration is managed through environment variables in `.env`. See [.env.example](.env.example) for the full list with descriptions.

Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `ELASTIC_PASSWORD` | `changeme` | Elasticsearch password — **change in production** |
| `KIBANA_SYSTEM_PASSWORD` | `changeme` | Kibana system password — **change in production** |
| `BATCH_SIZE` | `50` | Events per bulk index batch (increase for high traffic) |
| `MAX_WAIT_TIME` | `2.0` | Max seconds before flushing an incomplete batch |
| `ENV_TRACK_SUCCESS` | `false` | Set `true` to also log successful selector matches |
| `DEBUG` | `false` | Enable verbose logging across services |

## Event Categories

The `performance.js` tracker captures 25+ event types across these categories:

- **Automation Detection** — `navigator.webdriver`, Selenium globals, headless UA
- **Selector & XPath** — misses, errors, element inspections
- **Network** — XHR/fetch success, errors, slow requests (>5s)
- **JavaScript Errors** — uncaught errors, unhandled rejections, resource failures
- **Console** — `console.error()` and `console.warn()` interception
- **User Interactions** — clicks, programmatic clicks, rapid click bursts, disabled element clicks
- **Forms** — submissions, validation failures
- **Page Lifecycle** — load timing, idle detection, SPA navigation, connection status
- **DOM Mutations** — batch node additions/removals, attribute changes
- **Security** — CSP violations, WebSocket errors, blocking overlays
- **Framework Errors** — React, Angular, Vue, jQuery, Next.js, Nuxt specific errors

## Kibana Dashboard

The `kibana-deployer` automatically creates a comprehensive dashboard with 15 sections covering all event categories — from summary KPIs and timelines to per-category deep dives. No manual Kibana configuration needed.

## Privacy

All data is sanitized in the browser before transmission:

- 50+ sensitive field patterns redacted (passwords, tokens, API keys, SSNs, etc.)
- Email addresses masked (`us***@example.com`)
- Long hex/base64 tokens replaced with `[token]`
- Sensitive URL query parameters redacted
- Values truncated at configurable max length

## Integration

To add tracking to your own web application, include `performance.js` and set the endpoint:

```html
<script>
  window.ENV_LOGSERVER_URL = "http://your-log-server:8084";
</script>
<script src="performance.js"></script>
```

See [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) for the full list of `window.*` configuration globals.

## Further Reading

- [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) — Full technical documentation: architecture details, all event types, data flow, configuration reference
- [ANALYSIS_GUIDE.md](ANALYSIS_GUIDE.md) — Elasticsearch field reference, KQL query examples, and analysis workflows
