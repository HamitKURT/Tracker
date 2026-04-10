# performance.js Integration Guide

A zero-dependency browser telemetry script that auto-instruments any web application. It captures DOM interactions, network requests, JS errors, framework-specific issues, and more — then ships events to a log server for analysis.

---

## Quick Start

Add a single script tag to your HTML:

```html
<script src="/performance.js" data-logserver="http://your-log-server:8084"></script>
```

That's it. The script self-initializes and begins capturing events immediately.

### Serving the Script

Copy `performance.js` into your static assets directory and serve it like any other JS file. There are no build steps, no dependencies, and no module system required.

```
your-app/
├── static/
│   └── performance.js    ← copy this file
├── templates/
│   └── index.html         ← add the script tag here
```

---

## Configuration

### Script Tag Attributes

| Attribute | Description | Example |
|-----------|-------------|---------|
| `data-logserver` | Log server base URL | `http://myserver:8084` |
| `data-track-success` | Log successful selector lookups (verbose) | `"true"` |

### Global Variables (`window.*`)

Set these **before** the script loads to override defaults:

| Variable | Description | Default |
|----------|-------------|---------|
| `ENV_LOGSERVER_URL` | Log server URL (all browsers) | `http://mainlogserver.local:8084` |
| `ENV_LOGSERVER_INTERNAL_URL` | Internal URL used only in automated/Selenium sessions | — |
| `ENV_QA_SESSION_ID` | Override the auto-generated session ID | Auto-generated |
| `ENV_DEBUG` | Enable debug logging to browser console | `'false'` |
| `ENV_PRIVACY_MODE` | Set to `'relaxed'` to disable strict URL token stripping | strict |
| `ENV_TRACK_SUCCESS` | Log successful selector matches globally | `'false'` |

**Example with globals:**

```html
<script>
  window.ENV_LOGSERVER_URL = 'http://myserver:8084';
  window.ENV_DEBUG = 'true';
  window.ENV_QA_SESSION_ID = 'test-run-42';
</script>
<script src="/performance.js"></script>
```

### URL Resolution Priority

The script resolves the log server URL differently based on context:

**Automated sessions** (Selenium, Playwright, Puppeteer, etc.):
```
ENV_LOGSERVER_INTERNAL_URL → ENV_LOGSERVER_URL → data-logserver → default
```

**Manual browsing:**
```
ENV_LOGSERVER_URL → data-logserver → default
```

This allows you to use internal Docker/network URLs for automated tests while keeping a public URL for manual testing.

---

## Log Server Requirements

The script sends events to `{logserver}/events` via HTTP POST.

### Endpoint Specification

| Property | Value |
|----------|-------|
| **Path** | `/events` |
| **Method** | `POST` |
| **Content-Type** | `text/plain` |
| **Payload** | JSON string: `{ "events": [ ... ] }` |

### Payload Format

```json
{
  "events": [
    {
      "type": "page-load",
      "url": "https://example.com/dashboard",
      "loadTime": 1234,
      "severity": "low",
      "eventId": "a1b2-c3d4",
      "sessionId": "e5f6-g7h8",
      "correlationId": "corr-1712567890123-1",
      "summary": "Page loaded in 1234ms (OK)",
      "_ctx": {
        "sessionId": "e5f6-g7h8",
        "pageId": "i9j0-k1l2",
        "url": "https://example.com/dashboard",
        "timestamp": "2026-04-08T12:00:00.000Z",
        "uptime": 5000,
        "isAutomated": false,
        "userAgent": "Mozilla/5.0 ..."
      }
    }
  ]
}
```

### CORS

If the log server runs on a different origin than your app, it **must** return CORS headers:

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: POST, OPTIONS
Access-Control-Allow-Headers: Content-Type
```

### Unload Delivery

When the page unloads (close, navigate away), the script uses `navigator.sendBeacon()` or `fetch({ keepalive: true })` to deliver remaining events. These methods have a ~64KB browser limit, so the script automatically chunks payloads under 50KB.

### Expected Server Response

The script does not inspect the response body. Any `2xx` status is treated as success. On failure, it retries up to 3 times with exponential backoff (1s, 2s, 3s). After exhausting retries, dropped events are saved to `sessionStorage` and recovered on the next page load.

---

## Event Types Reference

Every event includes these common fields:

| Field | Description |
|-------|-------------|
| `type` | Event type identifier |
| `severity` | `low`, `medium`, `high`, or `critical` |
| `eventId` | Unique event ID |
| `sessionId` | Session identifier |
| `correlationId` | Groups related events into chains |
| `summary` | Human-readable one-line description |
| `_ctx` | Page context (URL, timestamp, uptime, userAgent) |
| `isAutomationDetected` | Whether automation was detected |
| `pageUrl` | Current page URL |
| `app` | Application origin |

### Page & Navigation

| Type | Severity | Description |
|------|----------|-------------|
| `page-load` | low–high | Page load timing, includes HTTP status if available |
| `hashchange` | low | URL hash changed |
| `pushState` | low | SPA navigation via `history.pushState` |
| `replaceState` | low | SPA navigation via `history.replaceState` |
| `page-idle` | high | No user activity for 30s (configurable) — test may be stuck |
| `connection` | low–medium | Browser went online/offline |

### Selector & Element Tracking

| Type | Severity | Description |
|------|----------|-------------|
| `selector-miss` | low–high | DOM query returned no results (escalates with repeat count) |
| `selector-found` | low | DOM query succeeded (only when `data-track-success="true"`) |
| `selector-error` | high | Invalid CSS selector threw an exception |
| `xpath-error` | high | Invalid XPath expression threw an exception |
| `element-inspection` | low | Automation read element dimensions/style (throttled) |
| `value-manipulation` | low | Automation set input/textarea/select value |

### Network

| Type | Severity | Description |
|------|----------|-------------|
| `xhr-success` | low | XHR completed successfully |
| `xhr-error` | high | XHR failed (status 0 or >= 400) |
| `xhr-slow` | medium | XHR took > 5000ms |
| `fetch-success` | low | Fetch completed successfully |
| `fetch-error` | high | Fetch failed |
| `fetch-slow` | medium | Fetch took > 5000ms |
| `websocket-error` | high | WebSocket connection error |
| `websocket-unclean-close` | medium | WebSocket closed abnormally |

### JavaScript Errors

| Type | Severity | Description |
|------|----------|-------------|
| `js-error` | high | Uncaught JavaScript error |
| `unhandled-rejection` | high | Unhandled promise rejection |
| `resource-error` | medium–high | Failed to load script, stylesheet, or image |
| `console-error` | high | `console.error()` call captured |
| `console-warn` | medium | `console.warn()` call captured |
| `csp-violation` | high | Content Security Policy violation |

### User Interaction

| Type | Severity | Description |
|------|----------|-------------|
| `user-click` | low | User clicked an element |
| `programmatic-click` | low | Automation triggered `.click()` |
| `rapid-clicks` | medium | 5+ clicks with < 80ms intervals |
| `click-on-disabled` | medium | Click on a disabled element |
| `keyboard-action` | low | Special key pressed during automation (Tab, Enter, arrows, etc.) |
| `form-submission` | low | Form submitted |
| `form-validation-failure` | medium | Form submission with invalid fields |
| `dialog-opened` | high | `alert()`, `confirm()`, or `prompt()` intercepted |

### DOM Mutations

| Type | Severity | Description |
|------|----------|-------------|
| `dom-mutations` | low–high | Batch of DOM nodes added/removed (threshold: 10+ changes) |
| `dom-attribute-changes` | low–medium | Relevant attribute changes during automation |
| `blocking-overlay-detected` | high | Modal/overlay covering > 30% of viewport detected |

### Framework-Specific

| Type | Severity | Framework |
|------|----------|-----------|
| `frameworks-detected` | low | All — lists detected frameworks and versions |
| `react-render-error` | critical | React |
| `react-hydration-mismatch` | high | React |
| `react-key-warning` | medium | React |
| `react-error-boundary-triggered` | high | React |
| `react-root-render-crash` | critical | React |
| `angular-zone-error` | high | Angular |
| `angular-framework-error` | high | Angular (NG error codes) |
| `angular-change-detection-error` | high | Angular |
| `angular-zone-unstable` | high | Angular |
| `vue-error` | high | Vue 2/3 |
| `vue-warning` | medium | Vue 2/3 |
| `jquery-ajax-error` | medium–high | jQuery |
| `jquery-deferred-error` | high | jQuery |
| `nextjs-runtime-error` | critical | Next.js |
| `nuxt-error` | high | Nuxt |

### System / Internal

| Type | Severity | Description |
|------|----------|-------------|
| `automation-detected` | medium–high | Automation signals found (Selenium, Playwright, etc.) |
| `queue-overflow` | critical | Event queue exceeded 500 — oldest events dropped |
| `batch-dropped` | critical | Batch permanently lost after 3 retries |
| `session-end` | low | Page unloading — final event in a session |

---

## Framework Support

The script automatically detects and hooks into these frameworks with **no configuration**:

| Framework | Detection Method | What It Captures |
|-----------|-----------------|-----------------|
| **React** | DevTools hook, Fiber tree, DOM inspection | Render errors, hydration mismatches, key warnings, error boundaries |
| **Angular** (2+) | `ng` global, `ng-version` attribute | Zone errors, NG error codes, change detection errors, stability |
| **AngularJS** (1.x) | `angular.version` global | Basic error tracking |
| **Vue 2** | `Vue.config` global | Component errors and warnings |
| **Vue 3** | `__VUE__` global, `data-v-app` attribute | Component errors and warnings via app error/warn handlers |
| **Next.js** | `__NEXT_DATA__` global | Runtime errors |
| **Nuxt** | `$nuxt` global | Application errors |
| **Svelte** | `svelte-` CSS classes, `__svelte` global | Detection only |
| **SvelteKit** | `data-sveltekit` attribute | Detection only |
| **jQuery** | `jQuery`/`$` global | AJAX errors, Deferred exceptions |
| **Ember** | `Ember` global | Detection only |

Framework detection runs after `DOMContentLoaded` (500ms delay) and again on `window.load` (2s delay) to catch lazy-loaded frameworks.

---

## Privacy & Security

The script applies aggressive sanitization by default.

### Redacted Fields

Any value associated with these keys is replaced with `[REDACTED]`:

`password`, `token`, `access_token`, `refresh_token`, `api_key`, `secret`, `session`, `csrf`, `credential`, `ssn`, `credit_card`, `cvv`, `pin`, `otp`, `mfa`, `encryption_key`, `birth`, `dob`, `phone`, `address`, and more (50+ keys).

### URL Parameter Redaction

These URL parameters are automatically stripped or redacted:

`token`, `access_token`, `refresh_token`, `api_key`, `secret`, `password`, `sessionid`, `csrf`, `Authorization`, `credential`, `key`, `sig`, `signature`

### Additional Protections

- **Email masking:** Emails are truncated to `ab***@domain.com`
- **Token masking:** Hex strings (32+ chars) and Base64 strings (40+ chars) are replaced with `[token]`
- **Value truncation:** String values are capped at 100 characters
- **Password inputs:** Values from `<input type="password">` are always `[REDACTED]`
- **Privacy mode (default: strict):** URL query strings are fully stripped

Set `window.ENV_PRIVACY_MODE = 'relaxed'` to keep URL query strings (sensitive params are still individually redacted).

---

## Production Considerations

### Throttling & Rate Limiting

The script throttles high-frequency events to minimize performance impact:

| Mechanism | Interval | Purpose |
|-----------|----------|---------|
| Element inspection throttle | 1000ms per element | Prevents flood from `getBoundingClientRect`, `getComputedStyle`, dimension properties |
| Value change throttle | 500ms per element | Limits input/textarea/select value-set tracking |
| Selector miss throttle | 200ms per selector | Prevents log spam from polling selectors |
| Selector success throttle | 5000ms per selector | Limits successful lookup logging |
| Mutation debounce | 300ms | Batches rapid DOM changes |
| Attribute change debounce | 500ms | Batches rapid attribute changes |

### Queue & Batching

| Setting | Value |
|---------|-------|
| Max batch size | 100 events per HTTP request |
| Max queue size | 500 events (oldest dropped on overflow) |
| Retry attempts | 3 with exponential backoff (1s, 2s, 3s) |
| Periodic flush | Every 5 seconds |
| XHR timeout | 5 seconds |
| Unload chunk size | 50KB max (under 64KB browser limit) |

### Memory Leak Prevention

Throttle maps (element inspection, value changes, selector successes) are cleaned every 60 seconds. Entries older than 30 seconds are removed when the map exceeds 500 entries. The selector miss cache is capped at 200 unique selectors.

### Self-Exclusion

The script automatically excludes its own `/events` requests from network monitoring to prevent infinite feedback loops.

### Idle Detection

If no click or keydown occurs for 30 seconds, a `page-idle` event fires. This helps identify stuck automated tests. Activity resets the timer.

### Overlay Detection

A periodic check (every 15 seconds, scheduled via `requestIdleCallback`) scans for modals, popups, and overlays covering > 30% of the viewport. Detected overlays emit a `blocking-overlay-detected` event.

---

## Automation Detection

The script identifies automated browsers via multiple signals:

- `navigator.webdriver` flag
- Selenium/Playwright/Puppeteer/Cypress/PhantomJS globals
- ChromeDriver artifacts (`$cdc_asdjflasutopfhvcZLmcfl_`)
- HeadlessChrome / PhantomJS user-agent strings
- Zero plugins, zero outer dimensions
- Software WebGL renderers (SwiftShader, Mesa, LLVMpipe)
- Chrome runtime without extension ID

When automation is detected, additional tracking activates:
- Element inspection logging (dimensions, computed styles)
- Value manipulation tracking (input/textarea/select changes)
- Keyboard special key tracking
- Attribute change monitoring
- Programmatic click tracking

---

## Minimal Log Server Example

If you don't have a log server yet, here's a minimal Node.js implementation:

```javascript
const http = require('http');

const server = http.createServer((req, res) => {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    return res.end();
  }

  if (req.method === 'POST' && req.url === '/events') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        const events = data.events || [data];
        events.forEach(evt => {
          console.log(`[${evt.severity}] ${evt.type}: ${evt.summary || ''}`);
        });
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end('{"status":"ok"}');
      } catch (e) {
        res.writeHead(400);
        res.end('{"error":"invalid json"}');
      }
    });
  } else {
    res.writeHead(404);
    res.end();
  }
});

server.listen(8084, () => console.log('Log server on :8084'));
```

Or with Python/Flask (matching this project's log server):

```python
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/events', methods=['POST', 'OPTIONS'])
def events():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify(error='invalid json'), 400

    events = data.get('events', [data] if isinstance(data, dict) else data)
    for evt in events:
        print(f"[{evt.get('severity', '?')}] {evt.get('type')}: {evt.get('summary', '')}")

    return jsonify(status='queued'), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8084)
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| No events arriving | Wrong `data-logserver` URL | Check browser console with `ENV_DEBUG='true'` |
| CORS errors in console | Log server missing CORS headers | Add `Access-Control-Allow-Origin: *` to server |
| Events sent but empty in Kibana | Payload format mismatch | Ensure server parses `{ "events": [...] }` |
| Too many `selector-miss` events | Polling selector not found | Check if element exists; adjust selector |
| `queue-overflow` events | Log server unreachable or too slow | Check server health; increase queue size |
| High memory usage on long sessions | Throttle maps growing | Script auto-cleans every 60s; reduce session length if extreme |
