# Tracker.js — Features & Functionality Summary

## Overview

`tracker.js` is a client-side JavaScript tracking script that intercepts browser APIs and DOM events to capture detailed user behavior and page telemetry. It runs as an IIFE (Immediately Invoked Function Expression) and sends all collected events to a configurable log server endpoint via `sendBeacon` or `fetch` with keepalive.

---

## Architecture

- **Session Management**: Generates a UUID per page load to correlate all events within a session.
- **Event Delivery**: Uses `navigator.sendBeacon` as the primary transport (non-blocking, survives page unload), with `fetch(keepalive)` as fallback.
- **Re-entrancy Guard**: Prevents infinite loops caused by intercepted APIs triggering further events.
- **Error Resilience**: Every event handler is wrapped in try/catch — the tracker never breaks the host application.
- **Configurable Endpoint**: Reads `window.ENV_LOGSERVER_URL` / `window.ENV_LOGSERVER_INTERNAL_URL` with a hardcoded default fallback.
- **Debug Mode**: Controlled via `window.ENV_DEBUG`; logs payloads to the console when enabled.

---

## Features

### 1. DOM Query Interception
- **Intercepted APIs**: `document.querySelector`, `document.getElementById`, `document.evaluate` (XPath)
- **Data captured**: method name, selector/XPath string, whether the element was found
- **Event types**: `dom-query`, `xpath-query`

### 2. User Interaction Tracking
- **Tracked events**: `click`, `input`, `focus`, `change`, `keydown`
- **Data captured**: event type, target tag/id/name/class, XPath of target element
- **Click-specific**: page X/Y coordinates
- **Input-specific**: value length (passwords excluded for security)
- **Suspicious click detection**: Fires a `timing-alert` event when clicks occur faster than 80ms apart (configurable via `MAX_INTERACTION_RATE_MS`)

### 3. JavaScript Error Tracking
- **Global error handler** (`window.onerror`): captures message, source file, line/column number, and stack trace (truncated to 1000 chars)
- **Event type**: `js-error`

### 4. Unhandled Promise Rejection Tracking
- Captures `unhandledrejection` events with reason message and stack trace
- **Event type**: `promise-rejection`

### 5. Console Interception
- **Intercepted methods**: `console.error`, `console.warn`
- **Data captured**: log level, message (truncated to 500 chars), argument count
- **Event type**: `console-error`

### 6. Visibility Change Tracking
- Tracks when the user switches tabs or minimizes the browser
- **Data captured**: visibility state (`visible`, `hidden`)
- **Event type**: `visibility`

### 7. Scroll Depth Tracking
- Throttled to fire at most once every 2 seconds (configurable via `SCROLL_THROTTLE_MS`)
- **Data captured**: current scroll depth %, max scroll depth %, page height, viewport height
- **Event type**: `scroll-depth`

### 8. Network Request Tracking (Fetch)
- Intercepts `window.fetch` (excludes requests to the tracker's own endpoint)
- **Data captured**: URL (truncated to 200 chars), HTTP method, status code, duration in ms, success boolean
- **Event type**: `network-request` (with `request_type: "fetch"`)

### 9. Network Request Tracking (XMLHttpRequest)
- Intercepts `XMLHttpRequest.prototype.open` and `.send` (excludes self-requests)
- **Data captured**: URL, HTTP method, status code, duration in ms, success boolean
- **Event type**: `network-request` (with `request_type: "xhr"`)

### 10. Performance Metrics
- Collected after page load (with 100ms delay)
- **Modern API** (`PerformanceNavigationTiming`) with deprecated `performance.timing` fallback
- **Data captured**:
  - DOM content loaded time, load complete time, DOM interactive time
  - Redirect count
  - Resource count and total transfer size in bytes
  - First Paint and First Contentful Paint times
- **Event type**: `performance`

### 11. Form Submit Tracking
- Captures form submissions via the `submit` event
- **Data captured**: form ID, action URL, HTTP method, field count, XPath
- **Event type**: `form-submit`

### 12. Clipboard Event Tracking
- **Tracked actions**: `copy`, `cut`, `paste`
- **Data captured**: action type, target tag/id, XPath
- **Event type**: `clipboard`

### 13. Context Menu (Right-Click) Tracking
- Captures right-click events
- **Data captured**: page X/Y coordinates, target tag/id, XPath
- **Event type**: `context-menu`

### 14. Window Resize Tracking
- Debounced at 500ms (configurable via `RESIZE_DEBOUNCE_MS`)
- **Data captured**: new and previous width/height
- **Event type**: `resize`

### 15. Connection Status Tracking
- Tracks online/offline transitions
- **Data captured**: connection status, effective connection type, downlink speed (via Network Information API when available)
- **Event type**: `connection`

### 16. Page Unload Tracking
- Fires on `beforeunload` using `sendBeacon` (with synchronous XHR fallback)
- **Data captured**: time on page in ms, final scroll depth %, total event count for the session
- **Event type**: `page-unload`

### 17. Page Load & Navigation Tracking
- Fires immediately on script execution
- Detects navigation type: `navigate`, `reload`, `back_forward`, `prerender`
- **Data captured**: referrer URL, navigation type
- **Event types**: `page-load`, `navigation`

---

## Base Payload (included in every event)

| Field              | Description                          |
|--------------------|--------------------------------------|
| `session_id`       | UUID generated per page load         |
| `url`              | Current page URL                     |
| `user_agent`       | Browser user agent string            |
| `is_webdriver`     | Whether the browser is automated     |
| `language`         | Browser language setting             |
| `screen_resolution`| Screen width x height                |
| `client_time`      | ISO 8601 timestamp                   |

---

## Utility Functions

- **`generateUUID()`** — Crypto-safe UUID generation with Math.random fallback
- **`getXPath(el)`** — Computes the XPath of any DOM element (short-circuits on `id` attribute)
- **`throttle(fn, delay)`** — Rate-limits high-frequency events (used for scroll)
- **`debounce(fn, delay)`** — Delays execution until activity stops (used for resize)
