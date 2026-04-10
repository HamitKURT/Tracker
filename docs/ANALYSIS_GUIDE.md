# Selenium Monitoring — Event Analysis Guide

Complete field reference for the browser telemetry pipeline powered by `performance.js`.

---

## Architecture

```
Browser (performance.js)
    │  POST /events (batched JSON, Content-Type: text/plain)
    ▼
Log Server (Flask :8084)
    │  LPUSH per event
    ▼
Redis Queue ("events_main")
    │  BRPOP (batch of 50, 2s window)
    ▼
Log Worker (Python)
    │  Bulk index via elasticsearch-py
    ▼
Elasticsearch (:9200, index: "selenium-events")
    │
    ▼
Kibana (:5601) — 15-section comprehensive dashboard
```

---

## Common Fields (Present on ALL Events)

These fields are injected by the `enqueue()` function and the log worker's `_ctx` merge:

| Field | ES Type | Source | Description |
|-------|---------|--------|-------------|
| `@timestamp` | date | log_worker | Server-side UTC timestamp (authoritative) |
| `timestamp` | date | _ctx | Client-side ISO 8601 timestamp |
| `type` | keyword | event | Event type identifier (see below) |
| `severity` | keyword | event | `low` / `medium` / `high` / `critical` |
| `sessionId` | keyword | enqueue | Browser session ID (persists across page loads) |
| `pageId` | keyword | _ctx | Per-page-load unique ID |
| `correlationId` | keyword | enqueue | Links related events in a chain |
| `eventId` | keyword | enqueue | Unique per-event ID |
| `url` | keyword | _ctx | Sanitized current page URL |
| `pageUrl` | keyword | enqueue | Duplicate of `url` (Kibana compatibility) |
| `uptime` | long | _ctx | Milliseconds since page load started |
| `isAutomated` | boolean | _ctx | `true` if automation signals detected |
| `isAutomationDetected` | boolean | enqueue | Same as `isAutomated` |
| `userAgent` | text | _ctx | Browser user agent string |
| `summary` | keyword | enqueue | Human-readable event summary |
| `parentId` | keyword | enqueue | Optional parent correlation ID |
| `_ctx` | object (disabled) | enqueue | Raw context object (not searchable) |

---

## Event Type Reference

### 1. Automation Detection

#### `automation-detected`
**Severity:** `high` (3+ signals) or `medium`

Fires once on page load when automation markers are found.

| Field | Type | Description |
|-------|------|-------------|
| `signals` | keyword[] | Detection signals (e.g., `navigator.webdriver`, `window.Cypress`, `headless-chrome-ua`) |

**Dashboard:** Section 11 — Automation Detection

---

### 2. Selector & XPath Events

#### `selector-miss`
**Severity:** `high` (5+ misses), `medium` (2+), `low` (first)

CSS selector or XPath query returned no results.

| Field | Type | Description |
|-------|------|-------------|
| `uniqueId` | keyword | `method:selector` composite key |
| `method` | keyword | `querySelector`, `querySelectorAll`, `getElementById`, `getElementsByClassName`, `getElementsByTagName`, `getElementsByName`, `xpath`, `xpath-iterator` |
| `selector` | keyword | The CSS selector or XPath expression |
| `selectorPath` | keyword | Simplified human-readable selector |
| `xpath` | keyword | XPath expression (XPath queries only) |
| `missCount` | integer | Cumulative miss count for this selector |
| `firstAttempt` | long | Timestamp of first miss |
| `lastAttempt` | long | Timestamp of most recent miss |
| `timeSinceFirst` | long | ms between first and last attempt |
| `isRepeatedFailure` | boolean | `true` if `missCount > 1` |
| `selectorDetails` | object | Parsed selector: `raw`, `tagName`, `id`, `classes`, `attributes`, `pseudoClasses`, `combinators` |
| `xpathAnalysis` | object | XPath analysis: `containsText`, `containsAttribute`, `containsDescendant`, `containsAxis` |
| `parentPath` | keyword | Parent element CSS path |
| `parentTagName` | keyword | Parent element tag |
| `parentId` | keyword | Parent element ID |
| `parentClasses` | keyword[] | Parent element classes |
| `likelyIssue` | keyword | Diagnostic hint |

**Dashboard:** Section 6 — Selectors & XPath

#### `selector-found`
**Severity:** `low`

Element successfully located (opt-in via `data-track-success="true"` or `ENV_TRACK_SUCCESS`).

| Field | Type | Description |
|-------|------|-------------|
| `uniqueId` | keyword | `method:selector` composite key |
| `method` | keyword | Query method used |
| `selector` | keyword | CSS selector |
| `selectorPath` | keyword | Simplified selector |
| `matchCount` | integer | Number of matching elements |

**Dashboard:** Section 6 — Selectors & XPath

#### `selector-error`
**Severity:** `high`

CSS selector syntax error threw an exception.

| Field | Type | Description |
|-------|------|-------------|
| `method` | keyword | Query method that failed |
| `selector` | keyword | The invalid selector |
| `message` | text | Error message |

**Dashboard:** Section 6 — Selectors & XPath

#### `xpath-error`
**Severity:** `high`

Invalid XPath expression threw an exception.

| Field | Type | Description |
|-------|------|-------------|
| `xpath` | keyword | The XPath expression |
| `expression` | keyword | Same as `xpath` |
| `message` | text | Error message |

**Dashboard:** Section 6 — Selectors & XPath

#### `element-inspection`
**Severity:** not set (informational)

Automation framework accessed element dimensions or styles (throttled to 1 event/sec per element).

| Field | Type | Description |
|-------|------|-------------|
| `method` | keyword | `getBoundingClientRect`, `getComputedStyle`, `offsetWidth`, `offsetHeight`, `clientWidth`, `clientHeight`, `scrollWidth`, `scrollHeight` |
| `xpath` | keyword | Element identifier key |
| `success` | boolean | Whether the call succeeded |
| `details` | object | Method-specific: `{width, height}`, `{pseudo}`, or `{value}` |

**Dashboard:** Section 14 — Element Inspection & Page Health

---

### 3. Value Manipulation

#### `value-manipulation`
**Severity:** not set (informational)

Input/textarea/select value changed programmatically during automation (throttled to 500ms per element).

| Field | Type | Description |
|-------|------|-------------|
| `method` | keyword | `input-value`, `textarea-value`, `select-value`, `select-selectedIndex`, `innerText` |
| `xpath` | keyword | Element identifier key |
| `details` | object | `{input_type, value_length, value_preview}` or `{selectedIndex}` |

**Dashboard:** Section 15 — Transport Health & Session Lifecycle (Value Manipulations table)

---

### 4. Network Events

#### `xhr-success` / `fetch-success`
**Severity:** `low`

HTTP request completed successfully (status < 400).

#### `xhr-error` / `fetch-error`
**Severity:** `high`

HTTP request failed (status >= 400 or network error).

#### `xhr-slow` / `fetch-slow`
**Severity:** `medium`

HTTP request exceeded 5000ms threshold.

**Common fields for all network events:**

| Field | Type | Description |
|-------|------|-------------|
| `method` | keyword | HTTP verb (GET, POST, etc.) |
| `url` | keyword | Sanitized request URL |
| `status` | keyword | HTTP status code |
| `duration` | long | Request time in milliseconds |
| `message` | text | Error message (errors only) |

**Dashboard:** Section 5 — Network

---

### 5. JavaScript Errors

#### `js-error`
**Severity:** `high`

Uncaught JavaScript error (window.onerror).

| Field | Type | Description |
|-------|------|-------------|
| `message` | text | Error message |
| `filename` | keyword | Source file URL |
| `lineno` | integer | Line number |
| `colno` | integer | Column number |

**Dashboard:** Section 4 — JavaScript Errors

#### `resource-error`
**Severity:** `high` (scripts), `medium` (others)

External resource failed to load.

| Field | Type | Description |
|-------|------|-------------|
| `tagName` | keyword | `SCRIPT`, `LINK`, `IMG` |
| `src` | keyword | Resource URL |
| `status` | keyword | Always `0` |
| `message` | text | `"Failed to load resource"` |

**Dashboard:** Section 5 — Network (Failed Network Requests)

#### `console-error`
**Severity:** `high`

`console.error()` was called.

| Field | Type | Description |
|-------|------|-------------|
| `args` | text | Sanitized console arguments |
| `message` | text | Concatenated arguments |

**Dashboard:** Section 4 — Console Errors

#### `console-warn`
**Severity:** `medium`

`console.warn()` was called.

| Field | Type | Description |
|-------|------|-------------|
| `args` | text | Sanitized console arguments |
| `message` | text | Concatenated arguments |

**Dashboard:** Section 4 — Console Warnings

#### `unhandled-rejection`
**Severity:** `high`

Unhandled Promise rejection.

| Field | Type | Description |
|-------|------|-------------|
| `message` | text | Rejection reason |

**Dashboard:** Section 4 — Unhandled Promise Rejections

---

### 6. User Interactions

#### `user-click`
**Severity:** `low`

User clicked an element (isTrusted=true).

| Field | Type | Description |
|-------|------|-------------|
| `selector` | keyword | `#id` or `tagname` |
| `tagName` | keyword | Element tag |
| `textContent` | text | Truncated element text |
| `isTrusted` | boolean | Always `true` for real clicks |

#### `programmatic-click`
**Severity:** `low`

`element.click()` called via automation.

| Field | Type | Description |
|-------|------|-------------|
| `selector` | keyword | XPath of clicked element |
| `tagName` | keyword | Element tag |

#### `rapid-clicks`
**Severity:** `medium`

5+ or 20+ clicks within 80ms intervals.

| Field | Type | Description |
|-------|------|-------------|
| `count` | integer | Number of rapid clicks |
| `interval` | long | Time between clicks (ms) |

#### `click-on-disabled`
**Severity:** `medium`

Click on a disabled or `aria-disabled="true"` element.

| Field | Type | Description |
|-------|------|-------------|
| `selector` | keyword | Element selector |

**Dashboard:** Section 7 — User Interactions & Forms

---

### 7. Dialog Events

#### `dialog-opened`
**Severity:** `high`

Browser dialog intercepted (alert, confirm, or prompt).

| Field | Type | Description |
|-------|------|-------------|
| `dialogType` | keyword | `alert`, `confirm`, or `prompt` |
| `message` | text | Dialog message text |
| `result` | boolean | User's confirm response (confirm only) |
| `hasResult` | boolean | Whether user provided input (prompt only) |

**Dashboard:** Section 13 — Dialogs & Keyboard Actions

---

### 8. Keyboard Events

#### `keyboard-action`
**Severity:** `low`

Special key or modifier combination pressed during automation.

| Field | Type | Description |
|-------|------|-------------|
| `key` | keyword | Key name (`Tab`, `Enter`, `Escape`, etc.) |
| `keyCode` | keyword | Key code (`KeyA`, `Enter`, etc.) |
| `modifiers` | keyword[] | `Ctrl`, `Alt`, `Shift`, `Meta` |
| `targetElement` | keyword | Element identifier |
| `targetTagName` | keyword | Target element tag |
| `isTrusted` | boolean | Whether event was user-initiated |

**Dashboard:** Section 13 — Dialogs & Keyboard Actions

---

### 9. Form Events

#### `form-submission`
**Severity:** `low`

Form submitted successfully.

| Field | Type | Description |
|-------|------|-------------|
| `formAction` | keyword | Sanitized form action URL |
| `method` | keyword | Form method (GET/POST) |

#### `form-validation-failure`
**Severity:** `medium`

Form has `:invalid` fields on submit.

| Field | Type | Description |
|-------|------|-------------|
| `formAction` | keyword | Sanitized form action URL |
| `invalidFields` | object[] | `[{name, type}, ...]` (up to 10) |

**Dashboard:** Section 7 — User Interactions & Forms

---

### 10. Page Lifecycle

#### `page-load`
**Severity:** `high` (HTTP 400+ or >10s), `medium` (>5s), `low`

Page load completed with performance timing.

| Field | Type | Description |
|-------|------|-------------|
| `loadTime` | long | Total load time (ms) |
| `httpStatus` | integer | HTTP response status (Chrome 109+) |
| `slow` | boolean | `true` if loadTime > 5000ms |

#### `page-idle`
**Severity:** `high`

No user activity for 30+ seconds — test may be stuck.

| Field | Type | Description |
|-------|------|-------------|
| `idleMs` | long | Idle duration in milliseconds |

#### `hashchange`
**Severity:** `low`

URL hash changed.

| Field | Type | Description |
|-------|------|-------------|
| `from` | keyword | Previous URL |
| `to` | keyword | New URL |

#### `pushState` / `replaceState`
**Severity:** `low`

SPA navigation via History API.

| Field | Type | Description |
|-------|------|-------------|
| `url` | keyword | New URL |

#### `connection`
**Severity:** `medium` (offline), `low` (online)

Browser went online or offline.

| Field | Type | Description |
|-------|------|-------------|
| `status` | keyword | `online` or `offline` |

**Dashboard:** Section 8 — Navigation & Page Loads, Section 14 (idle), Section 15 (connection)

---

### 11. DOM Mutations

#### `dom-mutations`
**Severity:** `high` (>20 changes), `medium` (>5), `low`

Significant DOM node additions/removals (threshold: 10+ nodes).

| Field | Type | Description |
|-------|------|-------------|
| `nodesAdded` | integer | Nodes added |
| `nodesRemoved` | integer | Nodes removed |
| `removedElements` | keyword[] | Selectors of removed elements (up to 10) |
| `totalRemoved` | integer | Total removed count |
| `warning` | keyword | Warning about large changes |

#### `dom-attribute-changes`
**Severity:** `medium` (>10 changes), `low`

Relevant DOM attributes changed during automation.

| Field | Type | Description |
|-------|------|-------------|
| `changes` | object[] | `[{attribute, target, oldValue, newValue, timestamp}]` (up to 30) |
| `totalChanges` | integer | Total attribute changes |
| `automationContext` | boolean | Whether in automation |

**Dashboard:** Section 9 — DOM Mutations

---

### 12. Security Events

#### `csp-violation`
**Severity:** `high`

Content Security Policy violation.

| Field | Type | Description |
|-------|------|-------------|
| `blockedURI` | keyword | Blocked resource URI |
| `violatedDirective` | keyword | CSP directive violated |
| `originalPolicy` | keyword | Full CSP policy (truncated) |

#### `websocket-error`
**Severity:** `high`

WebSocket connection failed.

| Field | Type | Description |
|-------|------|-------------|
| `url` | keyword | WebSocket URL |

#### `websocket-unclean-close`
**Severity:** `medium`

WebSocket closed abnormally.

| Field | Type | Description |
|-------|------|-------------|
| `url` | keyword | WebSocket URL |
| `code` | integer | Close code |
| `reason` | text | Close reason |

#### `blocking-overlay-detected`
**Severity:** `high`

Fixed/absolute overlay covering >30% of viewport (z-index >= 900).

| Field | Type | Description |
|-------|------|-------------|
| `overlay` | object | `{selector, position, zIndex, coverage, text}` |

**Dashboard:** Section 10 — Security Events

---

### 13. Framework Detection

#### `frameworks-detected`
**Severity:** `low`

Frontend frameworks detected on page load.

| Field | Type | Description |
|-------|------|-------------|
| `frameworks` | object[] | `[{name, version, source}]` |

Detected frameworks: React, Next.js, Angular, AngularJS, Zone.js, Vue 2/3, Nuxt, Svelte, SvelteKit, jQuery, Ember, React Native Web.

**Dashboard:** Section 12 — Framework Errors

---

### 14. React Errors

#### `react-error-boundary-triggered`
**Severity:** `high`

React error boundary caught an error.

| Field | Type | Description |
|-------|------|-------------|
| `componentName` | keyword | Component name |
| `componentStack` | keyword | Component hierarchy |

#### `react-render-error`
**Severity:** `critical`

React render error detected via console.

| Field | Type | Description |
|-------|------|-------------|
| `message` | text | Error message |

#### `react-hydration-mismatch`
**Severity:** `high`

Server/client HTML mismatch during hydration.

| Field | Type | Description |
|-------|------|-------------|
| `message` | text | Mismatch details |

#### `react-key-warning`
**Severity:** `medium`

Missing unique key in list rendering.

| Field | Type | Description |
|-------|------|-------------|
| `message` | text | Warning message |

#### `react-function-component-warning`
**Severity:** `low`

Function component usage warning.

| Field | Type | Description |
|-------|------|-------------|
| `message` | text | Warning message |

#### `react-root-render-crash`
**Severity:** `critical`

ReactDOM.createRoot().render() threw an error.

| Field | Type | Description |
|-------|------|-------------|
| `message` | text | Error message |
| `stack` | text | Stack trace |

**Dashboard:** Section 12 — React Errors table

---

### 15. Angular Errors

#### `angular-zone-error`
**Severity:** `high`

Error inside Angular Zone.

| Field | Type | Description |
|-------|------|-------------|
| `zoneName` | keyword | Zone name |
| `source` | keyword | Error source |
| `message` | text | Error message |
| `stack` | text | Stack trace |

#### `angular-framework-error`
**Severity:** `high`

Angular error with NG error code.

| Field | Type | Description |
|-------|------|-------------|
| `errorCode` | keyword | e.g., `NG0300`, `NG0100` |
| `message` | text | Error message |

#### `angular-change-detection-error`
**Severity:** `high`

`ExpressionChangedAfterItHasBeenChecked` error.

| Field | Type | Description |
|-------|------|-------------|
| `message` | text | Error message |

#### `angular-zone-unstable`
**Severity:** `high`

Angular zone not stable (pending async operations).

| Field | Type | Description |
|-------|------|-------------|
| `pendingRequests` | integer | Number of pending requests |

**Dashboard:** Section 12 — Angular Errors table

---

### 16. Vue Errors

#### `vue-error`
**Severity:** `high`

Vue component error (Vue 2 or 3).

| Field | Type | Description |
|-------|------|-------------|
| `message` | text | Error message |
| `stack` | text | Stack trace |
| `info` | keyword | Error context info |
| `componentName` | keyword | Component name |

#### `vue-warning`
**Severity:** `medium`

Vue warning.

| Field | Type | Description |
|-------|------|-------------|
| `message` | text | Warning message |
| `componentName` | keyword | Component name |
| `trace` | keyword | Stack trace |

**Dashboard:** Section 12 — Vue Errors & Warnings table

---

### 17. jQuery Errors

#### `jquery-ajax-error`
**Severity:** `high` (5xx), `medium` (other)

jQuery `$.ajax()` request failed.

| Field | Type | Description |
|-------|------|-------------|
| `url` | keyword | Request URL |
| `method` | keyword | HTTP method |
| `status` | keyword | HTTP status |
| `errorThrown` | keyword | Error string |

#### `jquery-deferred-error`
**Severity:** `high`

jQuery Deferred exception.

| Field | Type | Description |
|-------|------|-------------|
| `message` | text | Error message |
| `stack` | text | Stack trace |

**Dashboard:** Section 12 — Framework Events

---

### 18. Meta Framework Errors

#### `nextjs-runtime-error`
**Severity:** `critical`

Next.js unhandled runtime error.

| Field | Type | Description |
|-------|------|-------------|
| `message` | text | Error message |

#### `nuxt-error`
**Severity:** `high`

Nuxt application error.

| Field | Type | Description |
|-------|------|-------------|
| `message` | text | Error message |
| `statusCode` | integer | HTTP status code |

**Dashboard:** Section 12 — Framework Events

---

### 19. Transport & Queue Events

#### `queue-overflow`
**Severity:** `critical`

Event queue exceeded maximum size; events were dropped.

| Field | Type | Description |
|-------|------|-------------|
| `droppedCount` | integer | Events dropped |
| `queueSize` | integer | Max queue size |

#### `batch-dropped`
**Severity:** `critical`

Event batch permanently lost after retry exhaustion.

| Field | Type | Description |
|-------|------|-------------|
| `droppedCount` | integer | Events in batch |
| `retryAttempts` | integer | Retries attempted |

#### `session-end`
**Severity:** `low`

Browser session ending (page unload).

| Field | Type | Description |
|-------|------|-------------|
| `reason` | text | Trigger event (`beforeunload`, `pagehide`, `visibilitychange`) |
| `totalEventsInQueue` | integer | Events still in queue |

**Dashboard:** Section 15 — Transport Health & Session Lifecycle

---

## Severity Guide

| Severity | Meaning | Examples |
|----------|---------|---------|
| `critical` | Data loss or application crash | `queue-overflow`, `react-render-error`, `react-root-render-crash`, `nextjs-runtime-error`, `batch-dropped` |
| `high` | Functional failure or error | `js-error`, `xhr-error`, `selector-error`, `csp-violation`, `page-idle`, `dialog-opened` |
| `medium` | Warning or degraded performance | `console-warn`, `xhr-slow`, `rapid-clicks`, `form-validation-failure`, `websocket-unclean-close` |
| `low` | Informational / normal activity | `user-click`, `page-load` (fast), `form-submission`, `selector-found`, `frameworks-detected` |

---

## Kibana Dashboard Sections

| # | Section | Event Types |
|---|---------|-------------|
| 1 | Summary KPIs | All events, errors, sessions, URLs, high/critical severity |
| 2 | Global Timelines | All events + error events over time |
| 3 | Event & Severity Distribution | By type (pie), by severity (donut), top events table, top URLs |
| 4 | JavaScript Errors | `js-error`, `unhandled-rejection`, `console-error`, `console-warn` |
| 5 | Network | `xhr-*`, `fetch-*`, `resource-error` |
| 6 | Selectors & XPath | `selector-miss`, `selector-found`, `selector-error`, `xpath-error` |
| 7 | User Interactions & Forms | `user-click`, `programmatic-click`, `rapid-clicks`, `click-on-disabled`, `form-submission`, `form-validation-failure`, `value-manipulation` |
| 8 | Navigation & Page Loads | `page-load`, `hashchange`, `pushState`, `replaceState` |
| 9 | DOM Mutations | `dom-mutations`, `dom-attribute-changes` |
| 10 | Security | `csp-violation`, `websocket-error`, `websocket-unclean-close`, `blocking-overlay-detected` |
| 11 | Automation Detection | `automation-detected`, `programmatic-click`, `rapid-clicks` |
| 12 | Framework Errors | `frameworks-detected`, `react-*`, `angular-*`, `vue-*`, `jquery-*`, `nextjs-*`, `nuxt-*` |
| 13 | Dialogs & Keyboard | `dialog-opened`, `keyboard-action` |
| 14 | Element Inspection & Page Health | `element-inspection`, `page-idle` |
| 15 | Transport & Sessions | `queue-overflow`, `batch-dropped`, `session-end`, `connection` |

---

## KQL Query Examples

### Find all high-severity errors
```
severity: "high" OR severity: "critical"
```

### JS errors in a specific file
```
type: "js-error" AND filename: *login*
```

### Failed selectors for a specific page
```
type: "selector-miss" AND url: *dashboard*
```

### Network failures by endpoint
```
(type: "xhr-error" OR type: "fetch-error") AND url: */api/*
```

### All events for a specific session
```
sessionId: "abcd-1234"
```

### Automation-detected sessions only
```
isAutomated: true
```

### Slow page loads
```
type: "page-load" AND slow: true
```

### React errors by component
```
type: "react-error-boundary-triggered" AND componentName: *
```

### CSP violations
```
type: "csp-violation" AND violatedDirective: *script*
```

### Stuck tests (page idle)
```
type: "page-idle" AND idleMs > 60000
```

### Data loss events
```
type: "queue-overflow" OR type: "batch-dropped"
```

### Dialog interactions
```
type: "dialog-opened" AND dialogType: "confirm"
```

### Form validation failures
```
type: "form-validation-failure"
```

### Framework detection
```
type: "frameworks-detected"
```

### DOM mutation storms
```
type: "dom-mutations" AND nodesRemoved > 20
```
