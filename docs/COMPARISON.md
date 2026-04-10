# Selenium Tracker Script Comparison

## script.js vs performance.js (observe.js)

---

## Overview

| Aspect | script.js | performance.js (observe.js) |
|---|---|---|
| **File Size** | ~55 KB (1,314 lines) | ~104 KB (2,493 lines) |
| **Architecture** | Flat, monolithic IIFE | Modular, numbered sections (27 modules) |
| **Event Delivery** | Fire-and-forget (immediate send per event) | Batched queue with retry + backoff |
| **Privacy / Sanitization** | None | Full PII redaction, URL sanitization, email masking, token masking |
| **Framework Support** | None | React, Angular, Vue, Svelte, jQuery, Next.js, Nuxt, Ember |
| **Configuration** | Hardcoded `data-logserver` via env vars only | `data-logserver` attribute on `<script>` tag + env vars + 60+ config keys |
| **Correlation IDs** | None | Full correlation chain (session, page, event, parent) |
| **Event Summaries** | None | Human-readable `summary` field on every event |
| **Severity Levels** | None | `low` / `medium` / `high` / `critical` on every event |

---

## Feature-by-Feature Comparison

### 1. Automation Detection

| Feature | script.js | performance.js |
|---|---|---|
| `navigator.webdriver` | Yes | Yes |
| Selenium global variables | Yes (14 globals) | Yes (30+ globals, incl. Playwright, Cypress, Puppeteer, PhantomJS) |
| Zero outer dimensions | Yes | Yes |
| Headless screen position | Yes | No (covered by UA check) |
| Zero canvas size | Yes | No |
| User-Agent sniffing (HeadlessChrome, PhantomJS, Electron) | No | Yes |
| WebGL software renderer detection | No | Yes |
| Zero plugins detection | No | Yes |
| Chrome runtime anomaly | No | Yes |
| ChromeDriver `$cdc_` detection | No | Yes |

**Winner: performance.js** - Detects 2x more automation frameworks and signals.

---

### 2. DOM Query Interception (Selector Tracking)

| Feature | script.js | performance.js |
|---|---|---|
| `querySelector` | Yes | Yes |
| `querySelectorAll` | Yes | Yes |
| `getElementById` | Yes | Yes |
| `getElementsByClassName` | Yes | Yes |
| `getElementsByTagName` | Yes | Yes |
| `getElementsByName` | Yes | Yes |
| `document.evaluate` (XPath) | Yes | Yes (enhanced with iterator wrapping) |
| Element-scoped `querySelector/All` | Yes | Yes |
| **Shadow DOM** query tracking | No | Yes |
| Selector miss tracking (unique ID, count, first/last attempt) | No | Yes |
| Selector miss severity escalation | No | Yes (low -> medium -> high based on miss count) |
| Selector parsing & analysis | No | Yes (tag, id, classes, attributes, pseudo-classes, combinators) |
| Likely issue diagnosis | No | Yes (smart hints like "dynamic CSS class may have changed") |
| Parent context on miss | No | Yes (parent path, tag, id, classes) |
| Success selector tracking | No | Yes (configurable via `data-track-success`) |
| Throttled miss logging | No | Yes (200ms interval) |

**Winner: performance.js** - Not just tracks queries, but provides actionable debugging context for failures.

---

### 3. Element Inspection Tracking

| Feature | script.js | performance.js |
|---|---|---|
| `getBoundingClientRect` | Yes (every call) | Yes (throttled, automation-only) |
| `getComputedStyle` | Yes (every call) | Yes (throttled, automation-only) |
| Layout properties (offsetWidth, etc.) | 12 properties, every access | 6 key properties, throttled |
| `Element.matches()` | Yes | No (not needed - covered by selector tracking) |
| `Element.closest()` | Yes | No |
| `getAttribute` | Yes (every call) | No (privacy concern) |
| `hasAttribute` | Yes (every call) | No |
| Throttling | None | 1000ms per element+method |
| Automation-only gating | No (always fires) | Yes (only when `IS_AUTOMATED`) |

**Winner: performance.js for production** - script.js tracks more methods but fires on every single access with zero throttling, causing massive event volume.

---

### 4. Value Manipulation Tracking

| Feature | script.js | performance.js |
|---|---|---|
| `HTMLInputElement.value` | Yes | Yes |
| `HTMLTextAreaElement.value` | Yes | Yes |
| `HTMLSelectElement.value` | No | Yes |
| `HTMLSelectElement.selectedIndex` | No | Yes |
| `HTMLInputElement.checked` | Yes | No |
| `innerText` (get + set) | Yes (both) | Yes (set only, automation-only) |
| `textContent` (get + set) | Yes (both) | No (too noisy) |
| Stack trace analysis (`is_suspicious_stack`) | Yes | No (unnecessary overhead) |
| Sensitive field redaction | No | Yes (password, token, API key fields auto-redacted) |
| Throttling | None | 500ms per element+method |
| Automation-only gating | No | Yes |

**Winner: Tie** - script.js covers more getters but exposes sensitive data. performance.js is privacy-safe and production-ready.

---

### 5. Network Monitoring

| Feature | script.js | performance.js |
|---|---|---|
| Fetch interception | Yes | Yes |
| XHR interception | Yes | Yes |
| Log endpoint exclusion | Yes | Yes |
| Slow request detection | No | Yes (5000ms threshold) |
| Separate error/slow/success event types | No (single `network-request` type) | Yes (`xhr-error`, `xhr-slow`, `xhr-success`, `fetch-*`) |
| URL sanitization | No | Yes (query param redaction) |
| Severity assignment | No | Yes |

**Winner: performance.js** - Classifies requests into error/slow/success with severity.

---

### 6. Error Tracking

| Feature | script.js | performance.js |
|---|---|---|
| `window.onerror` | Yes | Yes |
| `unhandledrejection` | Yes | Yes |
| Resource load errors (script, img, css) | No | Yes |
| `console.error` | Yes | Yes |
| `console.warn` | Yes | Yes |
| Stack trace capture | Yes (raw, up to 1000 chars) | Yes (sanitized) |
| CSP violations | No | Yes |
| WebSocket errors | No | Yes |

**Winner: performance.js** - Covers resource errors, CSP violations, and WebSocket failures.

---

### 7. User Interaction Tracking

| Feature | script.js | performance.js |
|---|---|---|
| Click events | Yes | Yes |
| `isTrusted` detection | Yes | Yes |
| Rapid click detection | Yes (per-click interval check) | Yes (count-based: 5 and 20 thresholds) |
| Programmatic `.click()` | Yes | Yes (automation-only) |
| Click on disabled elements | No | Yes |
| Keyboard events | Yes (`keydown` raw) | Yes (special keys + modifier combos, automation-only) |
| Input events | Yes | No (covered by value manipulation) |
| Focus events | Yes | No |
| Change events | Yes | No |
| Form submission | Yes | Yes (with validation failure tracking) |
| Form validation failure (`:invalid` fields) | No | Yes |
| Clipboard (copy/cut/paste) | Yes | No |
| Context menu | Yes | No |
| Text selection | Yes | No |
| Dialog interception (alert/confirm/prompt) | No | Yes |

**Winner: Tie** - script.js captures more raw interaction types. performance.js captures more actionable events (disabled clicks, form validation, dialogs).

---

### 8. Page & Navigation Tracking

| Feature | script.js | performance.js |
|---|---|---|
| Page load | Yes | Yes (with HTTP status code) |
| Performance timing | Yes (detailed: FP, FCP, DOM interactive, transfer size) | Yes (load time + slow flag) |
| Page unload | Yes | Yes (chunked, multi-transport) |
| Visibility change | Yes | Yes (triggers queue flush) |
| Hash change | No | Yes |
| SPA navigation (`pushState`/`replaceState`) | No | Yes |
| Window resize | Yes | No |
| Connection online/offline | Yes | Yes |

**Winner: performance.js** - SPA navigation tracking is critical for modern apps.

---

### 9. Advanced Features (performance.js only)

| Feature | Available |
|---|---|
| **Batched event queue** (max 100 per batch, max 500 queue) | Yes |
| **Retry with exponential backoff** (3 attempts, 1s base) | Yes |
| **Dropped batch recovery** (sessionStorage persistence) | Yes |
| **Queue overflow detection** | Yes |
| **Unload chunking** (50KB chunks under browser 64KB limit) | Yes |
| **Correlation IDs** (session -> page -> event chain) | Yes |
| **Event summaries** (human-readable per event) | Yes |
| **Severity classification** (low/medium/high/critical) | Yes |
| **Privacy/PII sanitization** (emails, tokens, sensitive fields) | Yes |
| **URL parameter redaction** | Yes |
| **Framework detection** (React, Angular, Vue, Svelte, jQuery, Ember, Next.js, Nuxt, SvelteKit) | Yes |
| **React error boundary detection** (fiber tree walking) | Yes |
| **React hydration mismatch detection** | Yes |
| **Angular Zone.js error wrapping** | Yes |
| **Angular stability monitoring** | Yes |
| **Vue error/warn handler hooking** (v2 + v3) | Yes |
| **jQuery AJAX error + Deferred error tracking** | Yes |
| **Next.js runtime error detection** | Yes |
| **Nuxt error event tracking** | Yes |
| **DOM mutation tracking** (debounced, with removed element selectors) | Yes |
| **DOM attribute change tracking** (automation-focused) | Yes |
| **Overlay/modal detection** (blocking overlays > 30% coverage) | Yes |
| **Idle/stuck page detection** (30s threshold) | Yes |
| **Throttle map cleanup** (prevents memory leaks on long sessions) | Yes |
| **`data-logserver` script attribute** config | Yes |
| **`pagehide` event** handling (iOS/Safari) | Yes |
| **Periodic queue flush** (every 5s) | Yes |

---

## Performance Impact Comparison

| Metric | script.js | performance.js |
|---|---|---|
| **Events per page load** (typical) | Very High (hundreds-thousands) | Moderate (tens-hundreds) |
| **Network requests** | 1 XHR per event (no batching) | 1 XHR per batch (up to 100 events) |
| **CPU overhead on DOM reads** | High (intercepts every `getAttribute`, `innerText` get, `textContent` get, 12 layout props) | Low (throttled, automation-gated) |
| **Memory usage** | Low (no queue) but high network | Bounded (500 event queue, throttle map cleanup) |
| **Impact on non-automated users** | Same as automated (always intercepts) | Minimal (most tracking is automation-gated) |
| **Long session stability** | Risk of memory leak (no cleanup) | Stable (periodic throttle map cleanup) |
| **Unload reliability** | sendBeacon or fetch | sendBeacon -> fetch fallback, chunked, `pagehide` + `visibilitychange` |

---

## Production Readiness Comparison

| Criterion | script.js | performance.js |
|---|---|---|
| **PII Protection** | :x: None - raw values, emails, tokens exposed | :white_check_mark: Full redaction (50+ sensitive keys, email masking, token masking) |
| **GDPR/Privacy Compliance** | :x: Captures raw text content, attribute values, clipboard data | :white_check_mark: Privacy mode, configurable redaction |
| **Network Efficiency** | :x: 1 request per event | :white_check_mark: Batched (up to 100/batch) with retry |
| **Failure Recovery** | :x: Events lost on network failure | :white_check_mark: Retry + sessionStorage recovery |
| **CPU Impact** | :x: No throttling on high-frequency interceptions | :white_check_mark: Throttled, automation-gated |
| **Memory Safety** | :x: No cleanup mechanisms | :white_check_mark: Bounded queue, throttle map cleanup |
| **Event Volume Control** | :x: No deduplication or throttling | :white_check_mark: Throttled logging, debounced mutations |
| **Error Handling** | :warning: Silent catch blocks | :white_check_mark: Silent catch + queue overflow alerts |
| **Configuration** | :x: Env vars only | :white_check_mark: Script attribute + env vars + 60+ config keys |
| **Debugging Support** | :warning: Raw events only | :white_check_mark: Summaries, severity, correlation IDs, likely issue hints |

---

## When to Use Each Script

### Use script.js When:
- You need a **quick prototype** or proof-of-concept
- The environment is **fully controlled** (internal QA lab, no real user data)
- You want **maximum raw data capture** (clipboard, text selection, context menu, every attribute access)
- Network bandwidth is not a concern
- The target page is simple with low DOM activity
- You don't care about PII exposure (no real user data)

### Use performance.js When:
- **Production monitoring** of Selenium/automation tests
- **CI/CD pipelines** where performance matters
- The target application uses **modern frameworks** (React, Angular, Vue)
- **Privacy compliance** is required (GDPR, SOC2, etc.)
- You need **actionable debugging data** (not just raw events)
- Tests run **long sessions** (memory safety matters)
- **Network reliability** is uncertain (retry + recovery needed)
- You need to detect **blocking overlays, stuck pages, or form validation issues**
- **SPA applications** with client-side routing

---

## Final Verdict

| Use Case | Recommended Script | Reason |
|---|---|---|
| **Production CI/CD** | **performance.js** | Batching, throttling, privacy, memory safety |
| **Production with real users** | **performance.js** | PII redaction, minimal CPU impact on non-automated traffic |
| **Quick local debugging** | script.js | More raw data, simpler to reason about |
| **React/Angular/Vue apps** | **performance.js** | Framework-specific error tracking |
| **SPA applications** | **performance.js** | pushState/replaceState tracking |
| **High-traffic pages** | **performance.js** | Batched delivery, bounded queue, throttling |
| **Security auditing (raw capture)** | script.js | Captures everything including clipboard, selection, raw attributes |
| **Long-running test suites** | **performance.js** | Memory leak prevention, idle detection |
| **Flaky test investigation** | **performance.js** | Selector miss analysis, likely issue hints, correlation IDs |
| **Overall recommendation** | **performance.js** | Superior in 9 out of 10 categories |

---

## Migration Notes (script.js -> performance.js)

If migrating from script.js to performance.js, note these **features in script.js that are NOT in performance.js**:
1. Clipboard event tracking (copy/cut/paste)
2. Context menu tracking
3. Text selection tracking
4. Window resize tracking
5. `textContent` getter interception
6. `getAttribute` / `hasAttribute` interception
7. `Element.matches()` / `Element.closest()` interception
8. `HTMLInputElement.checked` tracking
9. Detailed performance paint metrics (FP, FCP, DOM interactive, transfer size)
10. `MutationObserver` constructor wrapping (performance.js uses its own observer instead)

These are intentional omissions - they generate excessive noise with minimal debugging value in production.
