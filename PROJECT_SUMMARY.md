# Selenium Tracker - Project Summary

## Overview

A comprehensive browser telemetry and QA monitoring pipeline that captures events from web applications via an injected JavaScript tracker, routes them through a message queue, indexes them in Elasticsearch, and visualizes them in Kibana dashboards.

Designed for **Locked Shields 2026** exercise to monitor Selenium-driven automated tests and detect anomalies, errors, and automation patterns in real time.

---

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
Kibana (port 5601, dashboards deployed by kibana_deployer)
```

---

## Services

| Service | Directory | Port | Description |
|---------|-----------|------|-------------|
| **web-app** | `web_app/` | 8081 | Flask demo app with `performance.js` injected |
| **log-server** | `log_server/` | 8084 | Flask endpoint that receives events and queues to Redis |
| **log-worker** | `log_worker/` | - | Consumes Redis queue, bulk-indexes into Elasticsearch |
| **kibana-deployer** | `kibana_deployer/` | - | Configures ES mappings, creates Kibana data views and dashboards |
| **selenium-test** | `selenium_test/` | - | Headless Chrome test suite generating 25+ event categories |
| **redis** | (image) | 6379 | Event queue storage |
| **elasticsearch** | (image) | 9200 | Search and storage backend |
| **kibana** | (image) | 5601 | Visualization UI |

---

## Event Types

### Automation Detection
| Type | Description |
|------|-------------|
| `automation-detected` | Browser automation markers found (navigator.webdriver, Selenium globals, headless UA) |

### Selector & XPath Tracking
| Type | Description |
|------|-------------|
| `selector-miss` | querySelector/getElementById/getElementsBy* returned no results |
| `selector-error` | CSS selector syntax error |
| `selector-found` | Element found successfully (opt-in via `ENV_TRACK_SUCCESS=true`) |
| `xpath-error` | Invalid XPath expression |
| `element-inspection` | getBoundingClientRect/getComputedStyle/offset* accessed (automation only) |

### Value Manipulation
| Type | Description |
|------|-------------|
| `value-manipulation` | Input/textarea value set programmatically (automation only) |

### Network Monitoring
| Type | Description |
|------|-------------|
| `xhr-success` / `fetch-success` | HTTP request succeeded (status < 400) |
| `xhr-error` / `fetch-error` | HTTP request failed (status >= 400 or network error) |
| `xhr-slow` / `fetch-slow` | HTTP request exceeded 5000ms threshold |

### Error Tracking
| Type | Description |
|------|-------------|
| `js-error` | Uncaught JavaScript error |
| `unhandled-rejection` | Unhandled Promise rejection |
| `resource-error` | Failed script/link/img resource load |
| `console-error` | `console.error()` called |
| `console-warn` | `console.warn()` called |

### User Interactions
| Type | Description |
|------|-------------|
| `user-click` | User clicked an element |
| `programmatic-click` | `element.click()` called programmatically (automation) |
| `rapid-clicks` | 5+ or 20+ clicks within 80ms intervals |
| `click-on-disabled` | Click on disabled/aria-disabled element |

### Form Tracking
| Type | Description |
|------|-------------|
| `form-submission` | Form submitted |
| `form-validation-failure` | Form has `:invalid` fields on submit |

### Page Lifecycle
| Type | Description |
|------|-------------|
| `page-load` | Page load complete (with timing data) |
| `page-idle` | No user activity for 30+ seconds |
| `hashchange` | URL hash changed |
| `pushState` / `replaceState` | SPA navigation via History API |
| `connection` | Browser went online/offline |

### DOM Mutations
| Type | Description |
|------|-------------|
| `dom-mutations` | 10+ nodes added/removed in a batch |
| `dom-attribute-changes` | Relevant attributes changed (class, style, disabled, aria-*, data-*) |

### Security
| Type | Description |
|------|-------------|
| `csp-violation` | Content Security Policy blocked a resource |
| `websocket-error` | WebSocket connection failed |
| `websocket-unclean-close` | WebSocket closed abnormally |
| `blocking-overlay-detected` | Fixed/absolute overlay covering >30% of viewport |

### Framework-Specific Errors
| Type | Description |
|------|-------------|
| `frameworks-detected` | Detected React/Angular/Vue/jQuery/Svelte/etc. |
| `react-render-error` | React component render error |
| `react-hydration-mismatch` | React SSR hydration mismatch |
| `react-error-boundary-triggered` | React error boundary caught error |
| `angular-zone-error` | Zone.js caught error |
| `angular-framework-error` | Angular NG error code |
| `vue-error` / `vue-warning` | Vue error/warning handler triggered |
| `jquery-ajax-error` | jQuery AJAX request failed |
| `nextjs-runtime-error` | Next.js runtime error |
| `nuxt-error` | Nuxt.js error |

---

## Configuration

### Environment Variables (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `ELASTIC_PASSWORD` | `changeme` | Elasticsearch password |
| `ELASTIC_USERNAME` | `elastic` | Elasticsearch username |
| `KIBANA_SYSTEM_PASSWORD` | `changeme` | Kibana system user password |
| `ELASTIC_URL` | `http://elasticsearch:9200` | Elasticsearch URL |
| `KIBANA_URL` | `http://kibana:5601` | Kibana URL |
| `REDIS_HOST` | `redis` | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_QUEUE_KEY` | `selenium_logs` | Redis list key for event queue |
| `ELASTIC_INDEX` | `selenium-events` | Elasticsearch index name |
| `BATCH_SIZE` | `50` | Worker batch size for bulk indexing |
| `MAX_WAIT_TIME` | `2.0` | Max seconds to wait before flushing batch |
| `LOGSERVER_EXTERNAL_URL` | `http://localhost:8084` | Log server URL for browser |
| `LOGSERVER_INTERNAL_URL` | `http://log-server:8084` | Log server URL for automation (Docker network) |
| `DEBUG` | `false` | Enable verbose logging |
| `ENV_TRACK_SUCCESS` | `false` | Track successful selector matches |

### Frontend Configuration (performance.js)

Set via `window.*` globals before `performance.js` loads:

| Global | Description |
|--------|-------------|
| `window.ENV_LOGSERVER_URL` | Log server URL (normal browsing) |
| `window.ENV_LOGSERVER_INTERNAL_URL` | Log server URL (automation, Docker internal) |
| `window.ENV_DEBUG` | `"true"` to enable console debug output |
| `window.ENV_TRACK_SUCCESS` | `"true"` to log successful selector matches |
| `window.ENV_QA_SESSION_ID` | Override session ID |
| `window.ENV_PRIVACY_MODE` | `"relaxed"` to disable strict privacy mode |

---

## Privacy & Sanitization

All data is sanitized in the browser before transmission:

- **Sensitive fields redacted**: password, token, api_key, ssn, credit_card, etc. (50+ patterns)
- **Email masking**: `user@example.com` -> `us***@example.com`
- **Token detection**: Hex strings 32+ chars and Base64 strings 40+ chars masked as `[token]`
- **URL parameter redaction**: Sensitive query params replaced with `[REDACTED]`
- **Value truncation**: Strings capped at configurable max length (default 100 chars)

---

## Kibana Dashboard

The `kibana_deployer` creates a single comprehensive dashboard with 12 sections:

1. **Summary KPIs** - Total events, errors, sessions, URLs, high/critical severity counts
2. **Global Timelines** - All events and error events over time
3. **Event Distribution** - Events by type and severity (pie charts + tables)
4. **JavaScript Errors** - JS errors, unhandled rejections, console errors/warnings
5. **Network** - Request timeline, failures, slow requests by endpoint
6. **Selectors & XPath** - CSS selector misses, XPath errors, failure analysis
7. **User Interactions** - Click events, form submissions, validation failures
8. **Navigation** - Page loads with timing, SPA navigation, hash changes
9. **DOM Mutations** - Node additions/removals, attribute changes
10. **Security** - CSP violations, WebSocket errors, blocking overlays
11. **Automation Detection** - Automation signals, programmatic clicks
12. **Framework Errors** - React/Angular/Vue specific errors

---

## Deployment

### Development

```bash
cp .env.example .env
# Edit .env with your passwords
docker-compose -f docker-compose.dev.yml up -d
```

### Production

```bash
cp .env.example .env
# Set strong passwords in .env
docker-compose -f docker-compose.prod.yml up -d
```

### Service Startup Order

1. **Redis** and **Elasticsearch** start first
2. **Kibana Deployer** waits for ES cluster health, sets `kibana_system` password, waits for Kibana, then deploys dashboards
3. **Log Server** and **Log Worker** connect to Redis and ES
4. **Web App** serves the demo page with `performance.js`
5. **Selenium Test** runs the comprehensive test suite

### Accessing Services

- **Web App**: `http://localhost:8081`
- **Kibana**: `http://localhost:5601` (login with `elastic` / your password)
- **Elasticsearch**: `http://localhost:9200`
- **Log Server Health**: `http://localhost:8084/health`

---

## Data Flow Details

### Browser -> Log Server
- Events batched (max 100 per request) and sent as `POST /events` with `Content-Type: text/plain`
- Payload format: `{ "events": [...] }`
- Retry with exponential backoff (up to 3 attempts)
- On page unload: uses `fetch` with `keepalive` or `navigator.sendBeacon`

### Log Server -> Redis
- Each event individually `LPUSH`ed to the configured Redis list key
- No transformation applied

### Log Worker -> Elasticsearch
- `BRPOP` with 1s timeout, collects up to `BATCH_SIZE` events or `MAX_WAIT_TIME` seconds
- Merges `_ctx` context object into top-level event fields
- Normalizes timestamp fields to ISO 8601
- Adds `@timestamp` with server UTC time
- Bulk indexes with error handling and re-queue for failed documents

---

## Selenium Test Suite

The test (`selenium_test/app/main.py`) generates 25+ categories of events:

- Missing selectors (querySelector, getElementById, getElementsBy*, XPath)
- JavaScript errors (ReferenceError, TypeError, SyntaxError, RangeError, etc.)
- Network failures (XHR/fetch errors, slow requests, timeouts)
- Rapid interactions (25 rapid clicks, rapid key inputs)
- DOM mutation bursts (30 elements added/removed)
- Form validation failures
- Console errors and warnings
- Blocking overlay detection
- WebSocket errors
- Page idle detection (30s wait)
- Navigation events (hash, pushState, replaceState)
- Resource load failures (broken images, scripts, stylesheets)
