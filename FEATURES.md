# Tracker.js — Features & Functionality Summary

## Overview

`tracker.js` is a client-side JavaScript tracking script that intercepts browser APIs and DOM events to capture detailed user behavior, automation detection, and page telemetry. It runs as an IIFE (Immediately Invoked Function Expression) and sends all collected events to a configurable log server endpoint (`/events` path) via XHR, fetch with keepalive, or sendBeacon.

---

## Architecture

- **Session Management**: Generates a UUID per page load to correlate all events within a session.
- **Event Delivery**: Uses `XMLHttpRequest` as primary transport, then `fetch(keepalive)`, then `navigator.sendBeacon` as final fallback.
- **Smart Endpoint Routing**: Automatically routes to `ENV_LOGSERVER_INTERNAL_URL` when `navigator.webdriver` is true, otherwise uses `ENV_LOGSERVER_URL`.
- **Re-entrancy Guard**: Uses `_sendDepth` counter to prevent infinite loops caused by intercepted APIs triggering further events.
- **Error Resilience**: Every event handler is wrapped in try/catch — the tracker never breaks the host application.
- **Global Error Handler**: Catches any initialization errors and logs them via console.warn when debug mode is enabled.
- **Configurable Endpoint**: Reads `window.ENV_LOGSERVER_URL` / `window.ENV_LOGSERVER_INTERNAL_URL` with a hardcoded default fallback (`http://mainlogserver.local:8084`).
- **Debug Mode**: Controlled via `window.ENV_DEBUG`; logs payloads to the console when enabled.
- **Cached Static Data**: User agent, language, screen resolution, and is_webdriver flag are cached at initialization for performance.

---

## Features

### 1. DOM Query Interception
- **Intercepted APIs**: `document.querySelector`, `document.getElementById`, `document.evaluate` (XPath), `document.getElementsByClassName`, `document.getElementsByTagName`, `document.getElementsByName`
- **Data captured**: method name, selector/XPath string, whether the element was found, result count for collection methods
- **Event types**: `dom-query`, `xpath-query`

### 2. Element Inspection Interception
- **Intercepted APIs**:
  - `getBoundingClientRect` — captures element dimensions
  - `getComputedStyle` — tracks style queries
  - `offsetWidth/Height/Top/Left`, `clientWidth/Height/Top/Left`, `scrollWidth/Height/Top/Left`
  - `querySelector`, `querySelectorAll`, `matches`, `closest` (Element level)
- **Data captured**: method name, XPath, dimensions, success status
- **Event type**: `element-inspection`

### 3. Data Extraction Interception
- **Intercepted APIs**: `getAttribute`, `hasAttribute`, `innerText` (getter), `textContent` (getter)
- **Data captured**: attribute name, extracted value (truncated), XPath, success status
- **Event type**: `data-extraction`

### 4. Value Manipulation Interception
- **Intercepted APIs**:
  - `innerText` setter — tracks text injection
  - `textContent` setter — tracks DOM text changes
  - `HTMLInputElement.prototype.value` setter — tracks input field value changes
  - `HTMLTextAreaElement.prototype.value` setter — tracks textarea value changes
  - `HTMLInputElement.prototype.checked` setter — tracks checkbox/radio state changes
- **Data captured**: XPath, value preview, value length, input type, suspicious stack trace detection
- **Event type**: `value-manipulation`
- **Suspicious Stack Detection**: Checks if the call originated from `<anonymous>` or `webdriver` context

### 5. Element Action Interception
- **Intercepted APIs**: `HTMLElement.prototype.click`
- **Data captured**: XPath, tag name, success status
- **Event type**: `element-action`

### 6. User Interaction Tracking
- **Tracked events**: `click`, `input`, `focus`, `change`, `keydown`
- **Data captured**: event type, target tag/id/name/class, XPath, `isTrusted` flag
- **Click-specific**: page X/Y coordinates
- **Input-specific**: value length (passwords excluded for security)
- **Suspicious click detection**: Fires a `timing-alert` event when clicks occur faster than 80ms apart
- **Event type**: `interaction`

### 7. Synthetic Event Detection
- Detects `isTrusted: false` events (indicating automation via `execute_script`)
- Fires an `automation-alert` event immediately when synthetic events are detected
- **Event type**: `automation-alert`

### 8. Automation Globals Detection
- Scans for Selenium/WebDriver globals: `$cdc_`, `$chrome_asyncScriptInfo`, `__webdriver_*`, `callSelenium`, etc.
- Detects headless indicators: zero outer dimensions, headless screen position
- Detects canvas fingerprinting anomalies
- Calculates severity based on number of signals detected
- **Event type**: `automation-detected`

### 9. JavaScript Error Tracking
- **Global error handler** (`window.onerror`): captures message, source file, line/column number, and stack trace (truncated to 1000 chars)
- **Event type**: `js-error`

### 10. Unhandled Promise Rejection Tracking
- Captures `unhandledrejection` events with reason message and stack trace
- **Event type**: `promise-rejection`

### 11. Console Interception
- **Intercepted methods**: `console.error`, `console.warn`
- **Data captured**: log level ("error" or "warn"), message (truncated to 500 chars), argument count
- **Event type**: `console-error`
- **Note**: Both methods send the same event type with the `level` field indicating which console method was called

### 12. Visibility Change Tracking
- Tracks when the user switches tabs or minimizes the browser
- **Data captured**: visibility state (`visible`, `hidden`)
- **Event type**: `visibility`

### 13. Network Request Tracking (Fetch)
- Intercepts `window.fetch` (excludes requests to the tracker's own endpoint)
- **Data captured**: URL (truncated to 200 chars), HTTP method, status code, duration in ms, success boolean
- **Event type**: `network-request` (with `request_type: "fetch"`)

### 14. Network Request Tracking (XMLHttpRequest)
- Intercepts `XMLHttpRequest.prototype.open` and `.send` (excludes self-requests)
- **Data captured**: URL, HTTP method, status code, duration in ms, success boolean
- **Event type**: `network-request` (with `request_type: "xhr"`)

### 15. Performance Metrics
- Collected after page load (with 100ms delay)
- **Modern API** (`PerformanceNavigationTiming`) with deprecated `performance.timing` fallback
- **Data captured**:
  - DOM content loaded time, load complete time, DOM interactive time
  - Redirect count
  - Resource count and total transfer size in bytes
  - First Paint and First Contentful Paint times
- **Event type**: `performance`

### 16. Form Submit Tracking
- Captures form submissions via the `submit` event
- **Data captured**: form ID, action URL, HTTP method, field count, XPath
- **Event type**: `form-submit`

### 17. Clipboard Event Tracking
- **Tracked actions**: `copy`, `cut`, `paste`
- **Data captured**: action type, target tag/id, XPath, clipboard length (no actual content captured)
- **Event type**: `clipboard`

### 18. Context Menu (Right-Click) Tracking
- Captures right-click events
- **Data captured**: page X/Y coordinates, target tag/id, XPath
- **Event type**: `context-menu`

### 19. Selection Change Tracking (debounced)
- Captures text selection events
- **Data captured**: selected text (truncated), anchor XPath, focus XPath
- **Event type**: `selection`

### 20. Window Resize Tracking (debounced)
- **Data captured**: new and previous width/height
- **Event type**: `resize`

### 21. Connection Status Tracking
- Tracks online/offline transitions
- **Data captured**: connection status, effective connection type, downlink speed (via Network Information API when available)
- **Event type**: `connection`

### 22. MutationObserver Interception (throttled)
- Wraps `MutationObserver` and `WebKitMutationObserver`
- Detects page monitoring activities
- **Data captured**: mutation count, subtree flag
- **Event type**: `mutation-observer`

### 23. Page Unload Tracking
- Fires on `beforeunload` using `sendBeacon` (with `fetch(keepalive)` fallback)
- **Data captured**: time on page in ms, total event count for the session
- **Event type**: `page-unload`

### 24. Page Load & Navigation Tracking
- Fires immediately on script execution
- Detects navigation type: `navigate`, `reload`, `back_forward`, `prerender`
- **Data captured**: referrer URL, navigation type
- **Event types**: `page-load`, `navigation`

---

## Base Payload (included in every event)

| Field              | Description                          |
|--------------------|--------------------------------------|
| `session_id`       | UUID generated per page load         |
| `url`              | Current page URL (dynamic)           |
| `user_agent`       | Browser user agent string (cached)   |
| `is_webdriver`     | Whether the browser is automated     |
| `language`         | Browser language setting (cached)    |
| `screen_resolution`| Screen width x height (cached)       |
| `client_time`      | ISO 8601 timestamp                   |

---

## Utility Functions

- **`generateUUID()`** — Crypto-safe UUID generation with Math.random fallback
- **`getXPath(el)`** — Computes the XPath of any DOM element (short-circuits on `id` attribute)
- **`throttle(fn, delay)`** — Rate-limits high-frequency events (used for MutationObserver)
- **`debounce(fn, delay)`** — Delays execution until activity stops (used for resize, selection)

---

## Event Types Summary

| Event Type          | Description                                      |
|---------------------|--------------------------------------------------|
| `dom-query`         | Document element queries                         |
| `xpath-query`       | XPath queries                                   |
| `element-inspection`| Element dimension/style queries                 |
| `element-action`    | Programmatic element clicks                     |
| `data-extraction`   | Attribute/text content reads                    |
| `value-manipulation`| Input value and property changes                 |
| `interaction`       | User-triggered DOM events                       |
| `automation-alert`  | Synthetic events (isTrusted=false)              |
| `automation-detected`| Selenium/WebDriver global signals              |
| `timing-alert`      | Suspicious rapid interactions                   |
| `js-error`          | JavaScript runtime errors                       |
| `promise-rejection` | Unhandled promise rejections                    |
| `console-error`     | Console.error/warn calls                        |
| `visibility`        | Page visibility changes                         |
| `network-request`   | Fetch/XHR network calls                        |
| `performance`       | Page load timing metrics                       |
| `form-submit`       | Form submission events                         |
| `clipboard`         | Copy/cut/paste actions                         |
| `context-menu`      | Right-click events                             |
| `selection`         | Text selection changes                         |
| `resize`            | Window resize events                           |
| `connection`        | Online/offline status changes                  |
| `mutation-observer` | DOM mutation monitoring                        |
| `page-unload`       | Page navigation away                           |
| `page-load`         | Initial page load                               |
| `navigation`        | Navigation type detection                      |
