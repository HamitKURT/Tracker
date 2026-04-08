/**
 * Include with:
 *   <script src="/performance.js"></script>
 *   — or —
 *   <script src="/performance.js" data-logserver="http://myserver:8084"></script>
 */
(function () {
    'use strict';

    // --- 1. CONFIGURATION ---
    var DEFAULT_LOGSERVER_URL = 'http://mainlogserver.local:8084';
    var scriptTag = document.currentScript;
    var tagUrl = scriptTag && scriptTag.getAttribute('data-logserver');
    var trackSuccessAttr = scriptTag && scriptTag.getAttribute('data-track-success');

    var CONFIG = {
        ENDPOINT_URL: navigator.webdriver
            ? (window.ENV_LOGSERVER_INTERNAL_URL || window.ENV_LOGSERVER_URL || tagUrl || DEFAULT_LOGSERVER_URL)
            : (window.ENV_LOGSERVER_URL || tagUrl || DEFAULT_LOGSERVER_URL),
        ENDPOINT_PATH: '/events',
        MAX_BATCH_SIZE: 100,
        MAX_QUEUE_SIZE: 500,
        MAX_RETRY_ATTEMPTS: 3,
        RETRY_BACKOFF_MS: 1000,
        DEBUG_MODE: window.ENV_DEBUG === 'true',
        MAX_INTERACTION_RATE_MS: 80,
        NETWORK_SLOW_THRESHOLD_MS: 5000,
        IDLE_TIMEOUT_MS: 30000,
        MAX_CONSOLE_ARG_LENGTH: 500,
        MAX_STACKTRACE_LENGTH: 1000,
        PRIVACY_MODE: window.ENV_PRIVACY_MODE !== 'relaxed',
        TRACK_SUCCESS_SELECTORS: window.ENV_TRACK_SUCCESS === 'true' || trackSuccessAttr === 'true',

        // Privacy redaction - exhaustive list from performance.js
        REDACT_KEYS: [
            'password', 'passwd', 'pwd', 'token', 'access_token', 'refresh_token', 'id_token',
            'auth', 'authorization', 'auth_token', 'api_key', 'apikey', 'api_secret',
            'secret', 'private_key', 'session', 'sessionid', 'session_id', 'phpsessid', 'jsessionid',
            'csrf', 'csrftoken', '_csrf', 'xsrf', 'xsrftoken', 'xsrf_token',
            'credential', 'credentials', 'cert', 'certificate', 'ssl', 'key',
            'ssn', 'social_security', 'social_security_number',
            'credit_card', 'card_number', 'card_number_cc', 'cvv', 'cvc', 'cvv2',
            'pin', 'otp', 'one_time_password', 'totp', 'mfa', '2fa',
            'account_key', 'encryption_key', 'signing_key', 'privatekey',
            'birth', 'birthday', 'dob', 'date_of_birth',
            'phone', 'mobile', 'cell', 'tel', 'telephone',
            'address', 'street', 'city', 'zip', 'postal', 'zipcode',
            'secret_question', 'sq', 'security_answer'
        ],
        REDACT_URL_PARAMS: [
            'token', 'access_token', 'refresh_token', 'id_token', 'auth',
            'api_key', 'apikey', 'secret', 'password', 'passwd', 'pwd',
            'sessionid', 'session_id', 'csrf', 'csrftoken', 'xsrf', 'xsrftoken',
            'Authorization', 'credential', 'key', 'sig', 'signature'
        ],
        MASK_EMAIL: true,
        MASK_URL_TOKENS: true,
        MAX_VALUE_LENGTH: 100,

        // Throttle settings for element inspection (production optimization)
        ELEMENT_INSPECTION_THROTTLE_MS: 1000,
        VALUE_CHANGE_THROTTLE_MS: 500,
        MUTATION_DEBOUNCE_MS: 300,
    };

    var LOG_ENDPOINT = CONFIG.ENDPOINT_URL + CONFIG.ENDPOINT_PATH;

    // --- 2. PRIVACY & SANITIZATION ---
    function isRedactKey(key) {
        if (!key) return false;
        var lowerKey = String(key).toLowerCase();
        for (var i = 0; i < CONFIG.REDACT_KEYS.length; i++) {
            if (lowerKey.indexOf(CONFIG.REDACT_KEYS[i]) !== -1) return true;
        }
        return false;
    }

    // Pre-compiled regexes for sanitize (avoid re-parsing on every call)
    var RE_EMAIL = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
    var RE_HEX_TOKEN = /([a-f0-9]{32,64})/gi;
    var RE_BASE64_TOKEN = /([A-Za-z0-9+/]{40,}={0,2})/g;

    function sanitize(val, key, maxLength) {
        if (val === null || val === undefined) return null;
        maxLength = maxLength || CONFIG.MAX_VALUE_LENGTH;

        if (key && isRedactKey(key)) return '[REDACTED]';

        var str = String(val);

        // Fast path: skip expensive regex for short strings that can't match
        if (str.length > 10) {
            if (CONFIG.MASK_EMAIL && str.indexOf('@') !== -1) {
                RE_EMAIL.lastIndex = 0;
                str = str.replace(RE_EMAIL, function (m) {
                    var parts = m.split('@');
                    return parts[0].length <= 2 ? '[email]' : parts[0].substring(0, 2) + '***@' + parts[1];
                });
            }

            // Mask long alphanumeric strings that could be tokens/keys
            if (str.length >= 32) {
                RE_HEX_TOKEN.lastIndex = 0;
                str = str.replace(RE_HEX_TOKEN, '[token]');
                RE_BASE64_TOKEN.lastIndex = 0;
                str = str.replace(RE_BASE64_TOKEN, '[token]');
            }
        }

        if (str.length > maxLength) str = str.substring(0, maxLength) + '...[truncated]';
        return str;
    }

    function sanitizeUrl(url) {
        if (!url || typeof url !== 'string') return url;
        try {
            var urlObj = new URL(url, window.location.href);
            var params = urlObj.searchParams;
            CONFIG.REDACT_URL_PARAMS.forEach(function (p) {
                if (params.has(p)) params.set(p, '[REDACTED]');
            });
            if (CONFIG.PRIVACY_MODE && CONFIG.MASK_URL_TOKENS) urlObj.search = '';
            return urlObj.toString();
        } catch (e) {
            var result = url;
            CONFIG.REDACT_URL_PARAMS.forEach(function (p) {
                var regex = new RegExp('([?&]' + p + '=)[^&]+', 'gi');
                result = result.replace(regex, '$1[REDACTED]');
            });
            return result.substring(0, 500);
        }
    }

    // --- 3. SESSION CONTEXT & CORRELATION IDS ---
    var SESSION_ID = window.ENV_QA_SESSION_ID || generateId();
    var PAGE_ID = generateId();
    var PAGE_URL = location.href;
    var APP_DOMAIN = location.origin + '/';
    var START_TIME = Date.now();
    var IS_AUTOMATED = false;

    // Correlation IDs for linking related events (from performance.js)
    var activeCorrelationId = null;
    var CORRELATION_COUNTER = 0;

    function generateId() {
        return 'xxxx-xxxx'.replace(/x/g, function () {
            return ((Math.random() * 16) | 0).toString(16);
        });
    }

    function generateCorrelationId() {
        return 'corr-' + Date.now() + '-' + (++CORRELATION_COUNTER);
    }

    function startCorrelation() {
        if (!activeCorrelationId) {
            activeCorrelationId = generateCorrelationId();
        }
        return activeCorrelationId;
    }

    function getCorrelationId() {
        return activeCorrelationId;
    }

    function clearCorrelation() {
        activeCorrelationId = null;
    }

    // Create a correlation chain for complex async actions
    function createCorrelationChain(parentId) {
        var newCorrId = generateCorrelationId();
        return {
            correlationId: newCorrId,
            parentId: parentId || getCorrelationId(),
            startedAt: Date.now()
        };
    }

    function pageContext() {
        return {
            sessionId: SESSION_ID,
            pageId: PAGE_ID,
            correlationId: getCorrelationId() || startCorrelation(),
            url: sanitizeUrl(PAGE_URL),
            timestamp: new Date().toISOString(),
            uptime: Date.now() - START_TIME,
            isAutomated: IS_AUTOMATED,
            userAgent: navigator.userAgent
        };
    }

    // --- 4. TRANSPORT & QUEUE SYSTEM (Matches performance.js mechanism) ---
    var eventQueue = [];
    var retryCount = 0;
    var isFlushing = false;

    function enqueue(evt, parentId) {
        // Add correlation ID if available
        var corrId = getCorrelationId() || startCorrelation();

        var sanitizedEvt = sanitizeEvent(evt);
        sanitizedEvt._ctx = pageContext();
        sanitizedEvt.correlationId = corrId;
        sanitizedEvt.eventId = generateId();
        sanitizedEvt.sessionId = SESSION_ID;
        sanitizedEvt.isAutomationDetected = IS_AUTOMATED;
        sanitizedEvt.pageUrl = sanitizedEvt._ctx.url; // Fix for empty Kibana tables
        sanitizedEvt.app = APP_DOMAIN;

        // NEW: Add summary field to all events
        sanitizedEvt.summary = generateSummary(sanitizedEvt);

        if (parentId) sanitizedEvt.parentId = parentId;
        eventQueue.push(sanitizedEvt);

        if (eventQueue.length > CONFIG.MAX_QUEUE_SIZE) {
            var droppedCount = eventQueue.length - CONFIG.MAX_QUEUE_SIZE;
            eventQueue.splice(0, droppedCount);
            // Notify that events were lost (unshift so it doesn't get dropped itself)
            var overflowEvt = {
                type: 'queue-overflow',
                droppedCount: droppedCount,
                queueSize: CONFIG.MAX_QUEUE_SIZE,
                severity: 'critical',
                _ctx: pageContext(),
                eventId: generateId(),
                sessionId: SESSION_ID,
                summary: 'Queue overflow: ' + droppedCount + ' events dropped'
            };
            eventQueue.unshift(overflowEvt);
        }

        if (CONFIG.DEBUG_MODE) console.log('[Observe]', evt.type, sanitizedEvt);

        flushQueue();
    }

    function flushQueue() {
        if (eventQueue.length === 0 || isFlushing) return;
        var batch = eventQueue.splice(0, CONFIG.MAX_BATCH_SIZE);
        sendBatch(batch);
    }

    function sendBatch(batch) {
        isFlushing = true;
        var payload = JSON.stringify({ events: batch });

        var xhr = new XMLHttpRequest();
        xhr.open('POST', LOG_ENDPOINT, true);
        xhr.setRequestHeader('Content-Type', 'text/plain');
        xhr.timeout = 5000;

        xhr.onload = function () {
            retryCount = 0;
            isFlushing = false;
            if (eventQueue.length > 0) flushQueue();
        };

        xhr.onerror = xhr.ontimeout = function () {
            isFlushing = false;
            retryCount++;
            if (retryCount <= CONFIG.MAX_RETRY_ATTEMPTS) {
                eventQueue = batch.concat(eventQueue);
                setTimeout(flushQueue, CONFIG.RETRY_BACKOFF_MS * retryCount);
            } else {
                // Persist dropped batch for recovery on next page load
                try {
                    var key = '_obs_dropped_' + Date.now();
                    sessionStorage.setItem(key, JSON.stringify(batch.slice(0, 50)));
                } catch (_) {}
                retryCount = 0;
                // Notify about the drop (this enqueue will use a fresh retry cycle)
                enqueue({
                    type: 'batch-dropped',
                    droppedCount: batch.length,
                    retryAttempts: CONFIG.MAX_RETRY_ATTEMPTS,
                    severity: 'critical'
                });
            }
        };
        xhr.send(payload);
    }

    var MAX_UNLOAD_CHUNK_BYTES = 50000; // 50KB safety margin under 64KB browser limit

    function sendUnloadChunk(payload) {
        // Prefer sendBeacon (returns false on failure), then keepalive fetch
        if (navigator.sendBeacon) {
            var sent = navigator.sendBeacon(LOG_ENDPOINT, new Blob([payload], { type: 'text/plain' }));
            if (sent) return;
        }
        if (window.fetch) {
            try {
                window.fetch(LOG_ENDPOINT, {
                    method: 'POST',
                    body: payload,
                    keepalive: true,
                    mode: 'no-cors',
                    headers: { 'Content-Type': 'text/plain' }
                });
            } catch (_) {}
        }
    }

    var _unloadHandled = false;
    function handleUnload(event) {
        if (_unloadHandled || eventQueue.length === 0) return;
        _unloadHandled = true;

        // Add session-end sentinel so server can detect incomplete sessions
        eventQueue.push({
            type: 'session-end',
            reason: event ? event.type : 'unknown',
            totalEventsInQueue: eventQueue.length,
            url: sanitizeUrl(PAGE_URL),
            severity: 'low',
            _ctx: pageContext(),
            eventId: generateId(),
            sessionId: SESSION_ID,
            summary: 'Session ended: ' + (event ? event.type : 'unknown')
        });

        var allEvents = eventQueue.splice(0);

        // Chunk payload to stay under browser limits
        var chunks = [];
        var current = [];
        var currentSize = 0;
        for (var i = 0; i < allEvents.length; i++) {
            var evtStr = JSON.stringify(allEvents[i]);
            if (currentSize + evtStr.length > MAX_UNLOAD_CHUNK_BYTES && current.length > 0) {
                chunks.push(current);
                current = [];
                currentSize = 0;
            }
            current.push(allEvents[i]);
            currentSize += evtStr.length;
        }
        if (current.length > 0) chunks.push(current);

        for (var c = 0; c < chunks.length; c++) {
            sendUnloadChunk(JSON.stringify({ events: chunks[c] }));
        }
    }

    window.addEventListener('beforeunload', handleUnload);
    window.addEventListener('pagehide', handleUnload);
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') handleUnload();
    });

    // Periodic flush to reduce reliance on unload
    setInterval(function () {
        if (eventQueue.length > 0 && !isFlushing) {
            flushQueue();
        }
    }, 5000);

    // --- 5. AUTOMATION DETECTION (Comprehensive) ---
    function detectAutomation() {
        var signals = [];
        if (navigator.webdriver) signals.push('navigator.webdriver');

        var globals = [
            'webdriver', '_selenium', '_Selenium_IDE_Recorder', 'callSelenium',
            '__webdriver_script_fn', '__driver_evaluate', '__webdriver_evaluate',
            '__fxdriver_evaluate', '__driver_unwrapped', '__webdriver_unwrapped',
            '__lastWatirAlert', '__lastWatirConfirm', '_WEBDRIVER_ELEM_CACHE',
            '__nightmare', '__phantomas', 'callPhantom', '_phantom', 'phantom',
            'Buffer', 'emit', 'spawn', 'domAutomation', 'domAutomationController',
            '__cypress', 'Cypress', 'cy', '__puppeteer_evaluation_script__', '__playwright'
        ];

        for (var i = 0; i < globals.length; i++) {
            try {
                if (typeof window[globals[i]] !== 'undefined') {
                    signals.push('window.' + globals[i]);
                }
            } catch (_) { }
        }

        try {
            if (document.$cdc_asdjflasutopfhvcZLmcfl_) signals.push('cdc_chromedriver');
        } catch (_) { }

        if (window.chrome) {
            try {
                if (window.chrome.runtime && !window.chrome.runtime.id) signals.push('chrome.runtime.noId');
            } catch (_) { }
        }

        if (navigator.plugins && navigator.plugins.length === 0) signals.push('zero-plugins');
        if (window.outerWidth === 0 && window.outerHeight === 0) signals.push('zero-outer-dimensions');

        var ua = navigator.userAgent || '';
        if (/HeadlessChrome/i.test(ua)) signals.push('headless-chrome-ua');
        if (/PhantomJS/i.test(ua)) signals.push('phantomjs-ua');
        if (/Electron/i.test(ua)) signals.push('electron-ua');

        try {
            var canvas = document.createElement('canvas');
            var gl = canvas.getContext('webgl');
            if (gl) {
                var debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
                if (debugInfo) {
                    var renderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
                    if (/swiftshader|mesa|llvmpipe/i.test(renderer)) signals.push('webgl-software-renderer');
                }
            }
        } catch (_) { }

        IS_AUTOMATED = signals.length > 0;
        if (signals.length > 0) {
            enqueue({
                type: 'automation-detected',
                signals: signals,
                severity: signals.length >= 3 ? 'high' : 'medium'
            });
        }
        return signals;
    }

    // --- 6. SANITIZE EVENT OBJECT ---
    function sanitizeEvent(evt) {
        if (evt === null || evt === undefined) return evt;
        if (typeof evt !== 'object') return evt;

        var result = {};
        var keys = Object.keys(evt);
        for (var k = 0; k < keys.length; k++) {
            var key = keys[k];
            var val = evt[key];
            var valType = typeof val;

            if (val === null || val === undefined) {
                result[key] = val;
                continue;
            }

            if (valType === 'string') {
                result[key] = sanitize(val, key, 500);
                continue;
            }

            if (valType === 'number' || valType === 'boolean') {
                result[key] = val;
                continue;
            }

            if (valType === 'function') continue;

            if (Array.isArray(val)) {
                result[key] = val.slice(0, 20);
                continue;
            }

            if (valType === 'object') {
                if (val instanceof Error) {
                    result[key] = { name: val.name, message: sanitize(val.message, 'error', 500) };
                } else if (val instanceof Date) {
                    result[key] = val.toISOString();
                } else {
                    try {
                        result[key] = JSON.parse(JSON.stringify(val));
                    } catch (e) {
                        result[key] = '[object]';
                    }
                }
                continue;
            }
            result[key] = '[unknown]';
        }
        return result;
    }

    // --- Generate Summary for All Events ---
    function generateSummary(evt) {
        if (!evt || !evt.type) return null;
        var type = evt.type;
        
        try {
            switch (type) {
                case 'automation-detected':
                    return 'Automation detected via: ' + (evt.signals || []).join(', ') + '. Severity: ' + evt.severity;
                
                case 'selector-miss':
                    var location = evt.parentPath ? ' under ' + evt.parentPath : '';
                    return 'Element not found: ' + evt.selector + location + '. Failed ' + evt.missCount + ' time(s).';
                
                case 'selector-found':
                    return 'Element found: ' + evt.selector + ' (' + evt.matchCount + ' matches)';
                
                case 'selector-error':
                    return 'Selector error in ' + evt.method + ': ' + evt.selector + ' - ' + evt.message;
                
                case 'xpath-error':
                    return 'XPath error: ' + evt.xpath + ' - ' + evt.message;
                
                case 'element-inspection':
                    return 'Inspected ' + evt.method + ' on ' + evt.xpath;
                
                case 'value-manipulation':
                    var preview = evt.details && evt.details.value_preview ? ' "' + evt.details.value_preview + '"' : '';
                    return 'Value changed on ' + evt.xpath + ' via ' + evt.method + ': ' + (evt.details && evt.details.input_type || evt.method) + ', ' + (evt.details && evt.details.value_length || 0) + ' chars' + preview;
                
                case 'xhr-success':
                case 'fetch-success':
                    return 'HTTP ' + evt.method + ' ' + evt.url + ' → ' + evt.status + ' in ' + evt.duration + 'ms';
                
                case 'xhr-error':
                case 'fetch-error':
                    return 'HTTP ' + evt.method + ' ' + evt.url + ' FAILED → ' + evt.status + ' after ' + evt.duration + 'ms';
                
                case 'xhr-slow':
                case 'fetch-slow':
                    return 'HTTP ' + evt.method + ' ' + evt.url + ' SLOW → ' + evt.status + ' in ' + evt.duration + 'ms (threshold: 5000ms)';
                
                case 'js-error':
                    var loc = evt.filename ? ' at ' + evt.filename.split('/').pop() + ':' + evt.lineno : '';
                    return 'JS Error' + loc + ': ' + (evt.message || '(no message)');
                
                case 'resource-error':
                    return 'Failed to load ' + evt.tagName + ': ' + evt.src;
                
                case 'console-error':
                    return 'Console ERROR: ' + (evt.args || []).join(' ');
                
                case 'console-warn':
                    return 'Console WARN: ' + (evt.args || []).join(' ');
                
                case 'user-click':
                    var content = evt.textContent ? ' "' + evt.textContent + '"' : '';
                    return 'User clicked ' + evt.tagName + content + ' at ' + evt.selector;
                
                case 'programmatic-click':
                    return 'Automation clicked ' + evt.tagName + ' at ' + evt.selector;
                
                case 'rapid-clicks':
                    return 'Rapid clicks detected: ' + evt.count + ' clicks in ' + evt.interval + 'ms intervals';
                
                case 'click-on-disabled':
                    return 'Clicked disabled element: ' + evt.selector;
                
                case 'form-submission':
                    return 'Form submitted to ' + evt.formAction + ' via ' + evt.method;
                
                case 'form-validation-failure':
                    var fields = (evt.invalidFields || []).map(function(f) { return f.name || f.type; }).join(', ');
                    return 'Form validation failed at ' + evt.formAction + '. Invalid: ' + fields;
                
                case 'page-load':
                    var speed = evt.loadTime > 5000 ? 'SLOW' : 'OK';
                    var statusInfo = evt.httpStatus ? ' HTTP ' + evt.httpStatus : '';
                    return 'Page loaded in ' + evt.loadTime + 'ms (' + speed + ')' + statusInfo;
                
                case 'hashchange':
                    return 'URL hash changed';
                
                case 'pushState':
                    return 'SPA navigation: pushed state to ' + evt.url;
                
                case 'replaceState':
                    return 'SPA navigation: replaced state to ' + evt.url;
                
                case 'dom-mutations':
                    return 'DOM changed: +' + evt.nodesAdded + ' / -' + evt.nodesRemoved + ' nodes';
                
                case 'dom-attribute-changes':
                    var firstTarget = evt.changes && evt.changes[0] ? evt.changes[0].target : 'elements';
                    return 'Attribute changes: ' + evt.totalChanges + ' on ' + firstTarget + (evt.totalChanges > 1 ? ' and others' : '');
                
                case 'websocket-error':
                    return 'WebSocket error on ' + evt.url;
                
                case 'websocket-unclean-close':
                    return 'WebSocket closed abnormally: ' + evt.url + ' (code: ' + evt.code + ')';
                
                case 'csp-violation':
                    return 'CSP blocked ' + evt.blockedURI + ' - directive: ' + evt.violatedDirective;
                
                case 'frameworks-detected':
                    var fwNames = (evt.frameworks || []).map(function(f) { return f.name + (f.version !== 'detected' ? '@' + f.version : ''); }).join(', ');
                    return 'Frameworks detected: ' + fwNames;
                
                case 'react-render-error':
                    return 'React render error: ' + (evt.message || '').substring(0, 100);
                
                case 'react-hydration-mismatch':
                    return 'React hydration mismatch: ' + (evt.message || '').substring(0, 100);
                
                case 'angular-framework-error':
                    return 'Angular error ' + evt.errorCode + ': ' + (evt.message || '').substring(0, 100);
                
                case 'vue-error':
                    return 'Vue error in ' + (evt.componentName || 'Unknown') + ': ' + (evt.message || '').substring(0, 100);
                
                case 'unhandled-rejection':
                    return 'Unhandled promise rejection: ' + evt.message;
                
                case 'connection':
                    return 'Browser connection: ' + evt.status;
                
                case 'page-idle':
                    return 'Page idle for ' + evt.idleMs + 'ms - test may be stuck';
                
                case 'blocking-overlay-detected':
                    var coverage = evt.overlay && evt.overlay.coverage ? evt.overlay.coverage + '%' : 'unknown';
                    var text = evt.overlay && evt.overlay.text ? ' "' + evt.overlay.text + '"' : '';
                    return 'Blocking overlay detected: ' + (evt.overlay && evt.overlay.selector) + ' covering ' + coverage + text;

                case 'queue-overflow':
                    return 'Queue overflow: ' + evt.droppedCount + ' events dropped (queue limit: ' + evt.queueSize + ')';

                case 'batch-dropped':
                    return 'Batch permanently dropped: ' + evt.droppedCount + ' events lost after ' + evt.retryAttempts + ' retries';

                case 'dialog-opened':
                    return 'Dialog ' + evt.dialogType + ': ' + (evt.message || '(empty)');

                case 'keyboard-action':
                    var mods = evt.modifiers && evt.modifiers.length > 0 ? evt.modifiers.join('+') + '+' : '';
                    return 'Key pressed: ' + mods + evt.key + ' on ' + (evt.targetTagName || 'unknown');

                case 'session-end':
                    return 'Session ended: ' + evt.reason;

                default:
                    return 'Event: ' + type;
            }
        } catch (e) {
            return 'Event: ' + type + ' (summary generation failed)';
        }
    }

    // --- 7. UNIQUE SELECTOR MISS TRACKING (Detailed element failure identification) ---
    var selectorMisses = {};
    var selectorMissesOrder = [];
    var SELECTOR_MISSES_MAX = 200;
    var SELECTOR_MISS_LOG_INTERVAL_MS = 200;

    function parseSelector(selector) {
        if (!selector || typeof selector !== 'string') return {};

        var info = {
            raw: selector.substring(0, 300),
            tagName: null,
            id: null,
            classes: [],
            attributes: [],
            pseudoClasses: [],
            combinators: []
        };

        var tagMatch = selector.match(/^([a-zA-Z][a-zA-Z0-9_-]*)/);
        if (tagMatch) info.tagName = tagMatch[1];

        var idMatch = selector.match(/#([a-zA-Z_][a-zA-Z0-9_-]*)/);
        if (idMatch) info.id = idMatch[1];

        var classMatches = selector.match(/\.([a-zA-Z_][a-zA-Z0-9_-]*)/g);
        if (classMatches) {
            info.classes = classMatches.map(function (c) { return c.substring(1); });
        }

        var attrMatches = selector.match(/\[([a-zA-Z_][a-zA-Z0-9_-]*(?:[*|^~$]?="[^"]*")?)\]/g);
        if (attrMatches) {
            info.attributes = attrMatches.map(function (a) { return a.replace(/[\[\]]/g, ''); });
        }

        var pseudoMatches = selector.match(/:[a-zA-Z()-]+/g);
        if (pseudoMatches) {
            info.pseudoClasses = pseudoMatches;
        }

        var combinatorMatches = selector.match(/[\s>+~]+/g);
        if (combinatorMatches) {
            info.combinators = combinatorMatches.filter(function (c) { return c.trim(); });
        }

        return info;
    }

    function describeSelectorPath(selectorInfo) {
        var parts = [];
        if (selectorInfo.tagName) parts.push(selectorInfo.tagName);
        if (selectorInfo.id) parts.push('#' + selectorInfo.id);
        if (selectorInfo.classes.length > 0) {
            parts.push('.' + selectorInfo.classes.join('.'));
        }
        return parts.join('');
    }

    function trackSelectorMiss(key, method, selector, selectorInfo) {
        if (selectorMissesOrder.indexOf(key) === -1) selectorMissesOrder.push(key);

        while (selectorMissesOrder.length > SELECTOR_MISSES_MAX) {
            var oldestKey = selectorMissesOrder.shift();
            delete selectorMisses[oldestKey];
        }
    }

    function logSelectorMiss(key, method, selector, selectorInfo, missData, parentContext) {
        var now = Date.now();
        var elapsed = now - missData.first;

        var uniqueId = method + ':' + selector;

        var logEntry = {
            type: 'selector-miss',
            uniqueId: uniqueId,
            method: method,
            selector: selector,
            selectorPath: selectorInfo ? describeSelectorPath(selectorInfo) : selector.substring(0, 100),
            missCount: missData.count,
            firstAttempt: missData.first,
            lastAttempt: missData.last,
            timeSinceFirst: elapsed,
            isRepeatedFailure: missData.count > 1,
            severity: missData.count >= 5 ? 'high' : (missData.count >= 2 ? 'medium' : 'low'),

            // Detailed selector analysis
            selectorDetails: selectorInfo || parseSelector(selector),

            // NEW: Parent context fields
            parentPath: parentContext ? parentContext.path : null,
            parentTagName: parentContext ? parentContext.tagName : null,
            parentId: parentContext ? parentContext.id : null,
            parentClasses: parentContext ? parentContext.classes : [],

            // Context
            pageUrl: sanitizeUrl(PAGE_URL),
            isAutomated: IS_AUTOMATED,

            // Hints for debugging
            likelyIssue: getLikelyIssue(method, selectorInfo)
        };

        enqueue(logEntry);
    }

    function getLikelyIssue(method, selectorInfo) {
        if (!selectorInfo) return null;

        if (selectorInfo.id) {
            return 'Element with id="' + selectorInfo.id + '" not found - check if element exists or was removed';
        }

        if (selectorInfo.classes && selectorInfo.classes.length > 0) {
            var hasDynamicClass = selectorInfo.classes.some(function (c) {
                return /^(active|disabled|hidden|visible|open|selected|checked|loading|data-|v-|ng-|react-|vue-|jsx-|tmp-)/i.test(c);
            });
            if (hasDynamicClass) {
                return 'Dynamic CSS class may have changed - element state may have changed after action';
            }
        }

        if (selectorInfo.pseudoClasses && selectorInfo.pseudoClasses.length > 0) {
            var pseudo = selectorInfo.pseudoClasses.join(', ');
            if (pseudo.indexOf('visible') !== -1 || pseudo.indexOf('hidden') !== -1) {
                return 'Element visibility state changed - check if element is rendered/visible';
            }
            if (pseudo.indexOf('enabled') !== -1 || pseudo.indexOf('disabled') !== -1) {
                return 'Element enabled/disabled state changed';
            }
        }

        if (method === 'getElementById') {
            return 'ID-based lookup failed - verify element has correct id attribute';
        }

        if (selectorInfo.combinators && selectorInfo.combinators.length > 2) {
            return 'Complex selector with ' + selectorInfo.combinators.length + ' levels - ancestor element may have changed';
        }

        return 'Selector may be stale or element was removed/replaced';
    }

    function wrapQueryMethod(proto, methodName, returnsMultiple) {
        var original = proto[methodName];
        if (!original) return;

        proto[methodName] = function (selector) {
            var result;
            try {
                result = original.apply(this, arguments);
            } catch (e) {
                enqueue({
                    type: 'selector-error',
                    method: methodName,
                    selector: sanitize(selector, 'selector', 300),
                    message: sanitize(e.message, 'error', 500),
                    severity: 'high'
                });
                throw e;
            }

            var found = returnsMultiple ? (result && result.length > 0) : !!result;

            // Success tracking (merged from wrapQueryMethodWithSuccess)
            if (found && selector && typeof selector === 'string' && CONFIG.TRACK_SUCCESS_SELECTORS) {
                var successKey = methodName + ':' + selector;
                var successNow = Date.now();
                if (!selectorSuccessThrottle[successKey] || (successNow - selectorSuccessThrottle[successKey]) > SELECTOR_SUCCESS_LOG_INTERVAL_MS) {
                    selectorSuccessThrottle[successKey] = successNow;
                    var successInfo = parseSelector(selector);
                    enqueue({
                        type: 'selector-found',
                        uniqueId: successKey,
                        method: methodName,
                        selector: sanitize(selector, 'selector', 300),
                        selectorPath: describeSelectorPath(successInfo),
                        matchCount: (result && result.length) || (result ? 1 : 0),
                        pageUrl: sanitizeUrl(PAGE_URL),
                        isAutomated: IS_AUTOMATED,
                        severity: 'low'
                    });
                }
            }

            if (!found && selector && typeof selector === 'string') {
                var key = methodName + ':' + selector;
                var now = Date.now();
                var selectorInfo = parseSelector(selector);
                var parentContext = null;
                
                if (!selectorMisses[key]) {
                    selectorMisses[key] = { count: 0, first: now, last: 0, lastLogged: 0, loggedFirst: false };
                    trackSelectorMiss(key, methodName, selector, selectorInfo);
                }
                selectorMisses[key].count++;
                selectorMisses[key].last = now;

                // Use search context node as parent context (the element was NOT found, so we can't get its parent)
                if (this && this !== document && this.parentElement) {
                    parentContext = getParentContext(this);
                } else if (this === document && document.body) {
                    parentContext = { path: 'document', tagName: 'document', id: null, classes: [] };
                }

                // Log immediately on first miss, then throttle subsequent logs
                var shouldLog = !selectorMisses[key].loggedFirst ||
                               (now - selectorMisses[key].lastLogged) > SELECTOR_MISS_LOG_INTERVAL_MS;

                if (shouldLog) {
                    selectorMisses[key].loggedFirst = true;
                    selectorMisses[key].lastLogged = now;
                    logSelectorMiss(key, methodName, selector, selectorInfo, selectorMisses[key], parentContext);
                }
            }
            return result;
        };
    }

    wrapQueryMethod(Document.prototype, 'querySelector', false);
    wrapQueryMethod(Document.prototype, 'querySelectorAll', true);
    wrapQueryMethod(Document.prototype, 'getElementById', false);
    wrapQueryMethod(Document.prototype, 'getElementsByClassName', true);
    wrapQueryMethod(Document.prototype, 'getElementsByTagName', true);
    wrapQueryMethod(Document.prototype, 'getElementsByName', true);

    if (Element.prototype.querySelector) {
        wrapQueryMethod(Element.prototype, 'querySelector', false);
        wrapQueryMethod(Element.prototype, 'querySelectorAll', true);
    }

    // Shadow DOM query tracking
    if (window.ShadowRoot) {
        wrapQueryMethod(ShadowRoot.prototype, 'querySelector', false);
        wrapQueryMethod(ShadowRoot.prototype, 'querySelectorAll', true);
    }

    // Enhanced XPath tracking with unique identification
    if (document.evaluate) {
        var origEvaluate = document.evaluate;
        document.evaluate = function (expression, contextNode, namespaceResolver, resultType, result) {
            var res;
            try {
                res = origEvaluate.apply(this, arguments);
            } catch (e) {
                enqueue({
                    type: 'xpath-error',
                    xpath: sanitize(expression, 'xpath', 300),
                    expression: sanitize(expression, 'xpath', 300),
                    message: sanitize(e.message, 'error', 500),
                    severity: 'high'
                });
                throw e;
            }

            try {
                var isMiss = false;
                if (resultType === XPathResult.FIRST_ORDERED_NODE_TYPE ||
                    resultType === XPathResult.ANY_UNORDERED_NODE_TYPE) {
                    isMiss = !res.singleNodeValue;
                } else if (resultType === XPathResult.ORDERED_NODE_SNAPSHOT_TYPE ||
                    resultType === XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE) {
                    isMiss = res.snapshotLength === 0;
                } else if (resultType === XPathResult.ORDERED_NODE_ITERATOR_TYPE ||
                    resultType === XPathResult.UNORDERED_NODE_ITERATOR_TYPE) {
                    // Wrap iterateNext to detect empty iterators on first call
                    var origIterateNext = res.iterateNext.bind(res);
                    var iterFirstCallDone = false;
                    res.iterateNext = function () {
                        var node = origIterateNext();
                        if (!iterFirstCallDone) {
                            iterFirstCallDone = true;
                            if (!node) {
                                // Empty iterator = miss, emit directly
                                var iterKey = 'xpath:' + expression;
                                var iterNow = Date.now();
                                if (!selectorMisses[iterKey]) {
                                    selectorMisses[iterKey] = { count: 0, first: iterNow, last: 0, lastLogged: 0, loggedFirst: false };
                                }
                                selectorMisses[iterKey].count++;
                                selectorMisses[iterKey].last = iterNow;
                                var iterShouldLog = !selectorMisses[iterKey].loggedFirst ||
                                    (iterNow - selectorMisses[iterKey].lastLogged) > SELECTOR_MISS_LOG_INTERVAL_MS;
                                if (iterShouldLog) {
                                    selectorMisses[iterKey].loggedFirst = true;
                                    selectorMisses[iterKey].lastLogged = iterNow;
                                    enqueue({
                                        type: 'selector-miss',
                                        uniqueId: iterKey,
                                        method: 'xpath-iterator',
                                        xpath: sanitize(expression, 'xpath', 300),
                                        selector: sanitize(expression, 'xpath', 300),
                                        missCount: selectorMisses[iterKey].count,
                                        severity: selectorMisses[iterKey].count >= 5 ? 'high' : (selectorMisses[iterKey].count >= 2 ? 'medium' : 'low'),
                                        pageUrl: sanitizeUrl(PAGE_URL),
                                        isAutomated: IS_AUTOMATED,
                                        likelyIssue: 'XPath iterator returned no results'
                                    });
                                }
                            }
                        }
                        return node;
                    };
                }

                if (isMiss) {
                    var key = 'xpath:' + expression;
                    var now = Date.now();
                    var parentContext = null;
                    
                    if (!selectorMisses[key]) {
                        selectorMisses[key] = { count: 0, first: now, last: 0, lastLogged: 0, loggedFirst: false };
                        trackSelectorMiss(key, 'xpath', expression, null);
                    }
                    selectorMisses[key].count++;
                    selectorMisses[key].last = now;

                    // Use context node as parent context (element was NOT found)
                    if (contextNode && contextNode !== document && contextNode.parentElement) {
                        parentContext = getParentContext(contextNode);
                    }

                    // Log immediately on first miss, then throttle subsequent logs
                    var shouldLog = !selectorMisses[key].loggedFirst ||
                                   (now - selectorMisses[key].lastLogged) > SELECTOR_MISS_LOG_INTERVAL_MS;

                    if (shouldLog) {
                        selectorMisses[key].loggedFirst = true;
                        selectorMisses[key].lastLogged = now;
                        enqueue({
                            type: 'selector-miss',
                            uniqueId: key,
                            method: 'xpath',
                            xpath: sanitize(expression, 'xpath', 300),
                            selector: sanitize(expression, 'xpath', 300),
                            selectorPath: expression.substring(0, 100),
                            xpathAnalysis: {
                                containsText: expression.indexOf('text()') !== -1,
                                containsAttribute: expression.indexOf('@') !== -1,
                                containsDescendant: expression.indexOf('//') !== -1,
                                containsAxis: /ancestor|descendant|parent|following/i.test(expression)
                            },
                            missCount: selectorMisses[key].count,
                            firstAttempt: selectorMisses[key].first,
                            lastAttempt: selectorMisses[key].last,
                            timeSinceFirst: now - selectorMisses[key].first,
                            isRepeatedFailure: selectorMisses[key].count > 1,
                            severity: selectorMisses[key].count >= 5 ? 'high' : (selectorMisses[key].count >= 2 ? 'medium' : 'low'),
                            
                            parentPath: parentContext ? parentContext.path : null,
                            parentTagName: parentContext ? parentContext.tagName : null,
                            parentId: parentContext ? parentContext.id : null,
                            parentClasses: parentContext ? parentContext.classes : [],
                            
                            pageUrl: sanitizeUrl(PAGE_URL),
                            isAutomated: IS_AUTOMATED,
                            likelyIssue: 'XPath expression may have changed or target element was removed'
                        });
                    }
                }
            } catch (_) { }
            return res;
        };
    }

    // --- 7b. SUCCESSFUL SELECTOR TRACKING (merged into wrapQueryMethod) ---
    var selectorSuccessThrottle = {};
    var SELECTOR_SUCCESS_LOG_INTERVAL_MS = 5000;

    // --- 8. ELEMENT INSPECTION TRACKING (Throttled for production) ---

    function getXPath(el) {
        if (!el || el.nodeType !== Node.ELEMENT_NODE) return '';
        if (el.id) {
            var quote = el.id.indexOf("'") !== -1 ? '"' : "'";
            return '//*[@id=' + quote + el.id + quote + ']';
        }
        var parts = [];
        var current = el;
        while (current && current.nodeType === Node.ELEMENT_NODE) {
            var index = 1;
            var sibling = current.previousSibling;
            while (sibling) {
                if (sibling.nodeType === Node.ELEMENT_NODE && sibling.nodeName === current.nodeName) index++;
                sibling = sibling.previousSibling;
            }
            parts.unshift(current.nodeName.toLowerCase() + '[' + index + ']');
            current = current.parentNode;
        }
        return '/' + parts.join('/');
    }

    // --- Helper: Get Parent Element Path ---
    function getParentPath(element, maxLevels) {
        if (!element || element.nodeType !== Node.ELEMENT_NODE) return null;
        if (!element.ownerDocument || !element.ownerDocument.body) return null;
        maxLevels = maxLevels || 20;
        var path = [];
        var current = element;
        var totalChars = 0;
        var maxChars = 500;
        
        while (current && current.nodeType === Node.ELEMENT_NODE && path.length < maxLevels) {
            var tag = current.tagName ? current.tagName.toLowerCase() : 'unknown';
            var selector = tag;
            
            if (current.id) {
                selector = tag + '#' + current.id;
            } else if (current.className && typeof current.className === 'string') {
                var classes = current.className.split(/\s+/).filter(Boolean).slice(0, 3).join('.');
                selector = tag + (classes ? '.' + classes : '');
            }
            
            path.unshift(selector);
            totalChars += selector.length;
            if (totalChars > maxChars) break;
            current = current.parentElement;
        }
        return path.join(' > ');
    }

    function getParentContext(element) {
        if (!element || !element.parentElement) return null;
        var parent = element.parentElement;
        return {
            path: getParentPath(parent),
            tagName: parent.tagName ? parent.tagName.toLowerCase() : null,
            id: parent.id || null,
            classes: parent.className && typeof parent.className === 'string' 
                ? parent.className.split(/\s+/).filter(Boolean) 
                : []
        };
    }

    // Performance-safe element inspection (throttled, only in automation)
    var lastInspectionByElement = {};

    function getElementKey(element) {
        if (!element._inspectKey) {
            var tag = element.tagName || '';
            var id = element.id || '';
            var className = element.className && typeof element.className === 'string'
                ? element.className.split(' ')[0]
                : '';
            element._inspectKey = (id ? '#' + id : tag + (className ? '.' + className : ''));
        }
        return element._inspectKey;
    }

    var origGetBoundingClientRect = Element.prototype.getBoundingClientRect;
    if (origGetBoundingClientRect) {
        Element.prototype.getBoundingClientRect = function () {
            var result;
            try {
                result = origGetBoundingClientRect.apply(this, arguments);
            } catch (e) {
                return null;
            }
            // Only track during automation with proper throttling (skip overlay checks)
            if (IS_AUTOMATED && !_inOverlayCheck) {
                var key = 'getBoundingClientRect:' + getElementKey(this);
                var now = Date.now();
                if (!lastInspectionByElement[key] || (now - lastInspectionByElement[key]) > CONFIG.ELEMENT_INSPECTION_THROTTLE_MS) {
                    lastInspectionByElement[key] = now;
                    enqueue({
                        type: 'element-inspection',
                        method: 'getBoundingClientRect',
                        xpath: getElementKey(this),
                        success: true,
                        details: { width: result ? result.width : 0, height: result ? result.height : 0 }
                    });
                }
            }
            return result;
        };
    }

    var origGetComputedStyle = window.getComputedStyle;
    if (origGetComputedStyle) {
        window.getComputedStyle = function (element, pseudoElt) {
            var result;
            try {
                result = origGetComputedStyle.call(window, element, pseudoElt);
            } catch (e) {
                return null;
            }
            if (IS_AUTOMATED && !_inOverlayCheck) {
                var key = 'getComputedStyle:' + getElementKey(element);
                var now = Date.now();
                if (!lastInspectionByElement[key] || (now - lastInspectionByElement[key]) > CONFIG.ELEMENT_INSPECTION_THROTTLE_MS) {
                    lastInspectionByElement[key] = now;
                    enqueue({
                        type: 'element-inspection',
                        method: 'getComputedStyle',
                        xpath: getElementKey(element),
                        success: true,
                        details: { pseudo: pseudoElt || null }
                    });
                }
            }
            return result;
        };
    }

    var propDescriptors = [
        { name: 'offsetWidth', key: 'offsetWidth' }, { name: 'offsetHeight', key: 'offsetHeight' },
        { name: 'clientWidth', key: 'clientWidth' }, { name: 'clientHeight', key: 'clientHeight' },
        { name: 'scrollWidth', key: 'scrollWidth' }, { name: 'scrollHeight', key: 'scrollHeight' }
    ];

    propDescriptors.forEach(function (prop) {
        var desc = Object.getOwnPropertyDescriptor(HTMLElement.prototype, prop.name);
        if (!desc || !desc.get) return;
        var origGetter = desc.get;
        Object.defineProperty(HTMLElement.prototype, prop.name, {
            get: function () {
                var value = origGetter.call(this);
                if (IS_AUTOMATED && !_inOverlayCheck) {
                    var key = prop.key + ':' + getElementKey(this);
                    var now = Date.now();
                    if (!lastInspectionByElement[key] || (now - lastInspectionByElement[key]) > CONFIG.ELEMENT_INSPECTION_THROTTLE_MS) {
                        lastInspectionByElement[key] = now;
                        enqueue({
                            type: 'element-inspection',
                            method: prop.key,
                            xpath: getElementKey(this),
                            success: true,
                            details: { value: value }
                        });
                    }
                }
                return value;
            },
            configurable: true,
            enumerable: desc.enumerable
        });
    });

    // --- 9. VALUE MANIPULATION TRACKING (Throttled) ---
    var valueChangeThrottle = {};
    var VALUE_CHANGE_THROTTLE_MS = CONFIG.VALUE_CHANGE_THROTTLE_MS;

    function shouldThrottleValue(key) {
        var now = Date.now();
        if (valueChangeThrottle[key] && (now - valueChangeThrottle[key]) < VALUE_CHANGE_THROTTLE_MS) {
            return true;
        }
        valueChangeThrottle[key] = now;
        return false;
    }

    function trackValueChange(method, xpath, data) {
        var key = method + ':' + xpath;
        if (shouldThrottleValue(key)) return;
        enqueue({
            type: 'value-manipulation',
            method: method,
            xpath: xpath,
            details: data
        });
    }

    var origInputValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    if (origInputValue && origInputValue.set) {
        Object.defineProperty(HTMLInputElement.prototype, 'value', {
            get: function () { return origInputValue.get.call(this); },
            set: function (val) {
                if (IS_AUTOMATED) {
                    var xpath = getElementKey(this);
                    var isSensitive = this.type === 'password' || isRedactKey(this.name) || isRedactKey(this.id);
                    trackValueChange('input-value', xpath, {
                        input_type: this.type || 'text',
                        value_length: val ? val.length : 0,
                        value_preview: isSensitive ? '[REDACTED]' : (val ? val.substring(0, 50) : '')
                    });
                }
                return origInputValue.set.call(this, val);
            },
            configurable: true,
            enumerable: true
        });
    }

    var origTextAreaValue = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');
    if (origTextAreaValue && origTextAreaValue.set) {
        Object.defineProperty(HTMLTextAreaElement.prototype, 'value', {
            get: function () { return origTextAreaValue.get.call(this); },
            set: function (val) {
                if (IS_AUTOMATED) {
                    trackValueChange('textarea-value', getElementKey(this), { value_length: val ? val.length : 0 });
                }
                return origTextAreaValue.set.call(this, val);
            },
            configurable: true,
            enumerable: true
        });
    }

    var origSelectValue = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
    if (origSelectValue && origSelectValue.set) {
        Object.defineProperty(HTMLSelectElement.prototype, 'value', {
            get: function () { return origSelectValue.get.call(this); },
            set: function (val) {
                if (IS_AUTOMATED) {
                    var isSensitive = isRedactKey(this.name) || isRedactKey(this.id);
                    trackValueChange('select-value', getElementKey(this), {
                        input_type: 'select',
                        value_length: val ? val.length : 0,
                        value_preview: isSensitive ? '[REDACTED]' : (val ? val.substring(0, 50) : '')
                    });
                }
                return origSelectValue.set.call(this, val);
            },
            configurable: true,
            enumerable: true
        });
    }

    var origSelectedIndex = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'selectedIndex');
    if (origSelectedIndex && origSelectedIndex.set) {
        Object.defineProperty(HTMLSelectElement.prototype, 'selectedIndex', {
            get: function () { return origSelectedIndex.get.call(this); },
            set: function (val) {
                if (IS_AUTOMATED) {
                    trackValueChange('select-selectedIndex', getElementKey(this), {
                        input_type: 'select',
                        selectedIndex: val
                    });
                }
                return origSelectedIndex.set.call(this, val);
            },
            configurable: true,
            enumerable: true
        });
    }

    var origInnerText = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'innerText');
    if (origInnerText && origInnerText.set) {
        Object.defineProperty(HTMLElement.prototype, 'innerText', {
            get: function () { return origInnerText.get.call(this); },
            set: function (val) {
                if (IS_AUTOMATED) {
                    trackValueChange('innerText', getElementKey(this), { value_length: val ? val.length : 0 });
                }
                return origInnerText.set.call(this, val);
            },
            configurable: true,
            enumerable: true
        });
    }

    // --- 9b. THROTTLE MAP CLEANUP (prevents memory leaks on long sessions) ---
    var THROTTLE_MAP_MAX_SIZE = 500;
    var THROTTLE_CLEANUP_INTERVAL_MS = 60000;
    var THROTTLE_STALE_MS = 30000;

    function cleanThrottleMaps() {
        var maps = [
            lastInspectionByElement,
            valueChangeThrottle,
            selectorSuccessThrottle
        ];
        var now = Date.now();
        for (var m = 0; m < maps.length; m++) {
            var map = maps[m];
            var keys = Object.keys(map);
            if (keys.length > THROTTLE_MAP_MAX_SIZE) {
                for (var i = 0; i < keys.length; i++) {
                    if (typeof map[keys[i]] === 'number' && (now - map[keys[i]]) > THROTTLE_STALE_MS) {
                        delete map[keys[i]];
                    }
                }
            }
        }
    }

    setInterval(cleanThrottleMaps, THROTTLE_CLEANUP_INTERVAL_MS);

    // --- 10. NETWORK MONITORING ---
    var origXHROpen = XMLHttpRequest.prototype.open;
    var origXHRSend = XMLHttpRequest.prototype.send;

    function shouldMonitorRequest(url) {
        if (!url) return false;
        return String(url).indexOf(LOG_ENDPOINT) === -1;
    }

    XMLHttpRequest.prototype.open = function (method, url) {
        this._obsMeta = { method: method, url: String(url), startTime: 0, shouldMonitor: shouldMonitorRequest(url) };
        return origXHROpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function () {
        var meta = this._obsMeta;
        if (meta && meta.shouldMonitor) {
            meta.startTime = Date.now();
            var self = this;
            this.addEventListener('load', function () {
                var duration = Date.now() - meta.startTime;
                var isError = self.status === 0 || self.status >= 400;
                var isSlow = duration > CONFIG.NETWORK_SLOW_THRESHOLD_MS;
                enqueue({
                    type: isError ? 'xhr-error' : (isSlow ? 'xhr-slow' : 'xhr-success'),
                    method: meta.method,
                    url: sanitizeUrl(meta.url),
                    status: self.status,
                    duration: duration,
                    severity: isError ? 'high' : (isSlow ? 'medium' : 'low')
                });
            });
        }
        return origXHRSend.apply(this, arguments);
    };

    if (window.fetch) {
        var origFetch = window.fetch;
        window.fetch = function (input, init) {
            var url = typeof input === 'string' ? input : (input && input.url ? input.url : String(input));
            var method = (init && init.method) ? init.method.toUpperCase() : 'GET';

            if (!shouldMonitorRequest(url)) return origFetch.apply(this, arguments);

            var startTime = Date.now();
            return origFetch.apply(this, arguments).then(function (response) {
                var duration = Date.now() - startTime;
                var isSlow = duration > CONFIG.NETWORK_SLOW_THRESHOLD_MS;
                enqueue({
                    type: !response.ok ? 'fetch-error' : (isSlow ? 'fetch-slow' : 'fetch-success'),
                    method: method,
                    url: sanitizeUrl(url),
                    status: response.status,
                    duration: duration,
                    severity: !response.ok ? 'high' : (isSlow ? 'medium' : 'low')
                });
                return response;
            }).catch(function (err) {
                enqueue({
                    type: 'fetch-error',
                    method: method,
                    url: sanitizeUrl(url),
                    duration: Date.now() - startTime,
                    message: sanitize(err.message, 'error', 500),
                    severity: 'high'
                });
                throw err;
            });
        };
    }

    // --- 11. JS ERROR TRACKING ---
    window.addEventListener('error', function (e) {
        if (e.target && (e.target.tagName === 'SCRIPT' || e.target.tagName === 'LINK' || e.target.tagName === 'IMG')) {
            var url = sanitizeUrl(e.target.src || e.target.href || '');
            enqueue({
                type: 'resource-error',
                tagName: e.target.tagName,
                src: url,
                url: url,
                status: 0,
                message: 'Failed to load resource',
                severity: e.target.tagName === 'SCRIPT' ? 'high' : 'medium'
            });
            return;
        }
        enqueue({
            type: 'js-error',
            message: sanitize(e.message, 'error', 1000),
            filename: e.filename || '',
            lineno: e.lineno,
            colno: e.colno,
            severity: 'high'
        });
    }, true);

    window.addEventListener('unhandledrejection', function (e) {
        var reason = e.reason || {};
        enqueue({
            type: 'unhandled-rejection',
            message: sanitize(String(reason.message || reason), 'error', 500),
            url: sanitizeUrl(PAGE_URL),
            severity: 'high'
        });
    });

    // --- 12. CONSOLE MONITORING (Only errors/warnings + automated) ---
    var origConsoleError = console.error;
    var origConsoleWarn = console.warn;
    var consoleErrorHandlers = [];

    console.error = function () {
        origConsoleError.apply(console, arguments);
        var args = [];
        for (var i = 0; i < arguments.length; i++) {
            args.push(sanitize(String(arguments[i]), 'console', CONFIG.MAX_CONSOLE_ARG_LENGTH));
        }
        enqueue({ type: 'console-error', args: args, message: args.join(' '), severity: 'high' });

        // Run registered framework handlers
        for (var h = 0; h < consoleErrorHandlers.length; h++) {
            try { consoleErrorHandlers[h](arguments); } catch (_) {}
        }
    };

    console.warn = function () {
        origConsoleWarn.apply(console, arguments);
        var args = [];
        for (var i = 0; i < arguments.length; i++) {
            args.push(sanitize(String(arguments[i]), 'console', CONFIG.MAX_CONSOLE_ARG_LENGTH));
        }
        enqueue({ type: 'console-warn', args: args, message: args.join(' '), severity: 'medium' });
    };

    // --- 13. CLICK & INTERACTION TRACKING ---
    var lastClickTime = 0;
    var rapidClickCount = 0;

    document.addEventListener('click', function (e) {
        var now = Date.now();
        var gap = now - lastClickTime;
        lastClickTime = now;

        if (gap < CONFIG.MAX_INTERACTION_RATE_MS) {
            rapidClickCount++;
            if (rapidClickCount === 5 || rapidClickCount === 20) {
                enqueue({ type: 'rapid-clicks', count: rapidClickCount, interval: gap, severity: 'medium' });
            }
        } else {
            rapidClickCount = 0;
        }

        var t = e.target;
        if (t && t.tagName) {
            var content = t.textContent || t.value || t.innerText || '';
            enqueue({
                type: 'user-click',
                selector: t.id ? '#' + t.id : t.tagName.toLowerCase(),
                tagName: t.tagName.toLowerCase(),
                textContent: sanitize(content.trim(), 'content', 50),
                isTrusted: e.isTrusted,
                severity: 'low'
            });

            if (t.disabled || t.getAttribute('aria-disabled') === 'true') {
                enqueue({ type: 'click-on-disabled', selector: t.id ? '#' + t.id : t.tagName.toLowerCase(), severity: 'medium' });
            }
        }
    }, true);

    // Programmatic clicks
    if (Element.prototype.click) {
        var origClick = Element.prototype.click;
        Element.prototype.click = function () {
            if (IS_AUTOMATED && this && this.tagName) {
                enqueue({
                    type: 'programmatic-click',
                    selector: getXPath(this),
                    tagName: this.tagName.toLowerCase(),
                    severity: 'low'
                });
            }
            return origClick.apply(this, arguments);
        };
    }

    // --- 13b. DIALOG INTERCEPTION (alert/confirm/prompt) ---
    var origAlert = window.alert;
    var origConfirm = window.confirm;
    var origPrompt = window.prompt;

    window.alert = function (message) {
        enqueue({
            type: 'dialog-opened',
            dialogType: 'alert',
            message: sanitize(String(message || ''), 'dialog', 200),
            severity: 'high'
        });
        return origAlert.apply(this, arguments);
    };

    window.confirm = function (message) {
        var result = origConfirm.apply(this, arguments);
        enqueue({
            type: 'dialog-opened',
            dialogType: 'confirm',
            message: sanitize(String(message || ''), 'dialog', 200),
            result: result,
            severity: 'high'
        });
        return result;
    };

    window.prompt = function (message, defaultValue) {
        var result = origPrompt.apply(this, arguments);
        enqueue({
            type: 'dialog-opened',
            dialogType: 'prompt',
            message: sanitize(String(message || ''), 'dialog', 200),
            hasResult: result !== null,
            severity: 'high'
        });
        return result;
    };

    // --- 13c. KEYBOARD SPECIAL KEY TRACKING ---
    document.addEventListener('keydown', function (e) {
        if (!IS_AUTOMATED) return;

        var specialKeys = ['Tab', 'Enter', 'Escape', 'Backspace', 'Delete',
            'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
            'Home', 'End', 'PageUp', 'PageDown',
            'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12'];

        if (specialKeys.indexOf(e.key) !== -1 || e.ctrlKey || e.altKey || e.metaKey) {
            var modifiers = [];
            if (e.ctrlKey) modifiers.push('Ctrl');
            if (e.altKey) modifiers.push('Alt');
            if (e.shiftKey) modifiers.push('Shift');
            if (e.metaKey) modifiers.push('Meta');

            enqueue({
                type: 'keyboard-action',
                key: e.key,
                keyCode: e.code,
                modifiers: modifiers,
                targetElement: e.target ? getElementKey(e.target) : null,
                targetTagName: e.target ? e.target.tagName.toLowerCase() : null,
                isTrusted: e.isTrusted,
                severity: 'low'
            });
        }
    }, true);

    // --- 14. FORM SUBMISSION ---
    document.addEventListener('submit', function (e) {
        var form = e.target;
        if (!form || form.tagName !== 'FORM') return;

        var invalids = form.querySelectorAll(':invalid');
        if (invalids.length > 0) {
            var fields = [];
            for (var i = 0; i < Math.min(invalids.length, 10); i++) {
                fields.push({ name: invalids[i].name || invalids[i].id, type: invalids[i].type || invalids[i].tagName });
            }
            enqueue({ type: 'form-validation-failure', formAction: sanitizeUrl(form.action), url: sanitizeUrl(PAGE_URL), invalidFields: fields, severity: 'medium' });
        } else {
            enqueue({ type: 'form-submission', formAction: sanitizeUrl(form.action), url: sanitizeUrl(PAGE_URL), method: form.method, severity: 'low' });
        }
    }, true);

    // --- 15. NAVIGATION TRACKING ---
    window.addEventListener('load', function () {
        setTimeout(function () {
            var perf = window.performance;
            if (!perf || !perf.timing) return;
            var t = perf.timing;
            var loadTime = t.loadEventEnd - t.navigationStart;

            // Capture HTTP status via Navigation Timing API (Chrome 109+)
            var httpStatus = null;
            try {
                var navEntries = perf.getEntriesByType && perf.getEntriesByType('navigation');
                if (navEntries && navEntries.length > 0 && navEntries[0].responseStatus) {
                    httpStatus = navEntries[0].responseStatus;
                }
            } catch (_) {}

            enqueue({
                type: 'page-load',
                url: sanitizeUrl(PAGE_URL),
                loadTime: loadTime,
                httpStatus: httpStatus,
                slow: loadTime > 5000,
                severity: (httpStatus && httpStatus >= 400) ? 'high' : (loadTime > 10000 ? 'high' : (loadTime > 5000 ? 'medium' : 'low'))
            });
        }, 100);
    });

    window.addEventListener('hashchange', function (e) {
        PAGE_URL = location.href;
        enqueue({ type: 'hashchange', from: sanitizeUrl(e.oldURL), to: sanitizeUrl(e.newURL), severity: 'low' });
    });

    if (window.history && window.history.pushState) {
        var origPush = history.pushState;
        var origReplace = history.replaceState;

        history.pushState = function () {
            var result = origPush.apply(this, arguments);
            PAGE_URL = location.href;
            enqueue({ type: 'pushState', url: sanitizeUrl(location.href), severity: 'low' });
            return result;
        };

        history.replaceState = function () {
            var result = origReplace.apply(this, arguments);
            PAGE_URL = location.href;
            enqueue({ type: 'replaceState', url: sanitizeUrl(location.href), severity: 'low' });
            return result;
        };
    }

    // --- 16. CONNECTION STATUS ---
    window.addEventListener('online', function () {
        enqueue({ type: 'connection', status: 'online', severity: 'low' });
    });

    window.addEventListener('offline', function () {
        enqueue({ type: 'connection', status: 'offline', severity: 'medium' });
    });

    // --- 17. PASSIVE DOM MUTATION TRACKING (Enhanced from performance.js) ---
    var mutationBuffer = { added: 0, removed: 0, attributeChanges: [], removedElements: [] };
    var mutationTimer = null;
    var MUTATION_DEBOUNCE_MS = 300;
    var ATTR_CHANGE_DEBOUNCE_MS = 500;
    var attrChangeTimer = null;

    // Track attribute changes specifically for automation
    var attrChangeBuffer = [];

    function getElementSelectorPath(el) {
        if (!el || !el.tagName) return '';
        var path = el.tagName.toLowerCase();
        if (el.id) path += '#' + el.id;
        else if (el.className && typeof el.className === 'string') {
            var cls = el.className.split(/\s+/).filter(Boolean).slice(0, 3).join('.');
            if (cls) path += '.' + cls;
        }
        return path;
    }

    function flushMutations() {
        if (mutationBuffer.added > 0 || mutationBuffer.removed > 0) {
            var mutationEvent = {
                type: 'dom-mutations',
                nodesAdded: mutationBuffer.added,
                nodesRemoved: mutationBuffer.removed,
                removedElements: mutationBuffer.removedElements.slice(0, 10),
                totalRemoved: mutationBuffer.removed,
                correlationId: getCorrelationId() || startCorrelation(),
                severity: (mutationBuffer.added + mutationBuffer.removed) > 20 ? 'high' :
                    (mutationBuffer.added + mutationBuffer.removed) > 5 ? 'medium' : 'low'
            };

            // Track significant DOM changes
            if (mutationBuffer.removed > 5) {
                mutationEvent.warning = 'Large number of nodes removed - may indicate dynamic content changes';
            }
            if (mutationBuffer.added > 20) {
                mutationEvent.warning = 'Large number of nodes added - may indicate lazy loading or dynamic content';
            }

            enqueue(mutationEvent);
        }
        mutationBuffer = { added: 0, removed: 0, attributeChanges: [], removedElements: [] };
        mutationTimer = null;
    }

    function flushAttrChanges() {
        if (attrChangeBuffer.length > 0) {
            enqueue({
                type: 'dom-attribute-changes',
                changes: attrChangeBuffer.slice(0, 30),
                totalChanges: attrChangeBuffer.length,
                correlationId: getCorrelationId() || startCorrelation(),
                severity: attrChangeBuffer.length > 10 ? 'medium' : 'low',
                automationContext: IS_AUTOMATED
            });
        }
        attrChangeBuffer = [];
        attrChangeTimer = null;
    }

    if (window.MutationObserver) {
        var pendingMutations = [];
        var processingMutation = false;

        function processMutationsAsync() {
            if (processingMutation || pendingMutations.length === 0) return;
            processingMutation = true;

            setTimeout(function () {
                var mutations = pendingMutations.splice(0, pendingMutations.length);
                processingMutation = false;

                var added = 0, removed = 0, removedSelectors = [];

                for (var i = 0; i < mutations.length; i++) {
                    var m = mutations[i];

                    if (m.type === 'childList') {
                        added += m.addedNodes.length;
                        removed += m.removedNodes.length;

                        // Track removed elements for debugging
                        if (m.removedNodes.length > 0 && removedSelectors.length < 15) {
                            for (var r = 0; r < m.removedNodes.length; r++) {
                                var node = m.removedNodes[r];
                                if (node.nodeType === 1) {
                                    var path = getElementSelectorPath(node);
                                    if (path) removedSelectors.push(path);
                                }
                            }
                        }
                    }

                    // Track attribute changes during automation
                    if (m.type === 'attributes' && IS_AUTOMATED) {
                        var attrName = m.attributeName;
                        if (!attrName) continue;

                        // Filter for relevant attributes
                        var relevantAttrs = ['class', 'style', 'disabled', 'aria-hidden', 'aria-expanded',
                            'aria-selected', 'hidden', 'data-state', 'data-active', 'value',
                            'data-testid', 'data-cy', 'data-role'];

                        if (relevantAttrs.indexOf(attrName) !== -1 || attrName.indexOf('data-') === 0) {
                            if (attrChangeBuffer.length < 50) {
                                attrChangeBuffer.push({
                                    attribute: attrName,
                                    target: getElementSelectorPath(m.target),
                                    oldValue: m.oldValue ? String(m.oldValue).substring(0, 100) : null,
                                    newValue: m.target.getAttribute ? String(m.target.getAttribute(attrName) || '').substring(0, 100) : null,
                                    timestamp: Date.now()
                                });
                            }
                        }

                        if (!attrChangeTimer) {
                            attrChangeTimer = setTimeout(flushAttrChanges, ATTR_CHANGE_DEBOUNCE_MS);
                        }
                    }
                }

                // Only log if significant changes
                if (added + removed >= 10 || removed >= 5) {
                    mutationBuffer.added += added;
                    mutationBuffer.removed += removed;
                    mutationBuffer.removedElements = mutationBuffer.removedElements.concat(removedSelectors).slice(0, 15);
                    if (!mutationTimer) {
                        mutationTimer = setTimeout(flushMutations, MUTATION_DEBOUNCE_MS);
                    }
                    // Overlay may have appeared with DOM change
                    scheduleOverlayCheck();
                }

                if (pendingMutations.length > 0) {
                    processMutationsAsync();
                }
            }, MUTATION_DEBOUNCE_MS);
        }

        var observer = new MutationObserver(function (mutations) {
            for (var i = 0; i < mutations.length; i++) {
                pendingMutations.push(mutations[i]);
            }
            if (!processingMutation) {
                processMutationsAsync();
            }
        });

        function startObserving() {
            if (document.body) {
                observer.observe(document.body, {
                    childList: true,
                    subtree: true,
                    attributes: true,
                    attributeOldValue: true,
                    attributeFilter: ['class', 'style', 'disabled', 'aria-hidden', 'aria-expanded',
                        'aria-selected', 'hidden', 'data-state', 'data-active', 'value',
                        'data-testid', 'data-cy', 'data-role', 'data-test']
                });
            } else {
                setTimeout(startObserving, 50);
            }
        }
        startObserving();
    }

    // --- 18. CSP VIOLATION TRACKING ---
    document.addEventListener('securitypolicyviolation', function (e) {
        enqueue({
            type: 'csp-violation',
            blockedURI: sanitizeUrl(e.blockedURI || ''),
            violatedDirective: e.violatedDirective || '',
            originalPolicy: (e.originalPolicy || '').substring(0, 300),
            severity: 'high'
        });
    });

    // --- 19. WEBSOCKET MONITORING ---
    if (window.WebSocket) {
        var OrigWS = window.WebSocket;
        window.WebSocket = function (url, protocols) {
            var ws = protocols ? new OrigWS(url, protocols) : new OrigWS(url);

            ws.addEventListener('error', function () {
                enqueue({
                    type: 'websocket-error',
                    url: sanitizeUrl(String(url)),
                    severity: 'high'
                });
            });

            ws.addEventListener('close', function (e) {
                if (!e.wasClean) {
                    enqueue({
                        type: 'websocket-unclean-close',
                        url: sanitizeUrl(String(url)),
                        code: e.code,
                        reason: sanitize(e.reason || '', 'websocket-reason', 200),
                        severity: 'medium'
                    });
                }
            });

            return ws;
        };
        window.WebSocket.prototype = OrigWS.prototype;
    }

    // --- 20. FRAMEWORK DETECTION & SPECIFIC ERROR TRACKING ---
    var DETECTED_FRAMEWORKS = [];

    function detectFrameworks() {
        try {
            // React detection
            if (window.__REACT_DEVTOOLS_GLOBAL_HOOK__ && window.__REACT_DEVTOOLS_GLOBAL_HOOK__.renderers) {
                var renderers = window.__REACT_DEVTOOLS_GLOBAL_HOOK__.renderers;
                var version = 'unknown';
                if (renderers && renderers.size > 0) {
                    renderers.forEach(function (r) { if (r.version) version = r.version; });
                }
                DETECTED_FRAMEWORKS.push({ name: 'react', version: version, source: 'devtools-hook' });
            }

            if (DETECTED_FRAMEWORKS.length === 0 || !DETECTED_FRAMEWORKS.some(function (f) { return f.name === 'react'; })) {
                var rootEl = document.getElementById('root') || document.getElementById('app') || document.querySelector('[data-reactroot]');
                if (rootEl) {
                    var keys = Object.keys(rootEl);
                    for (var i = 0; i < keys.length; i++) {
                        if (keys[i].indexOf('__reactFiber$') === 0 || keys[i].indexOf('__reactInternalInstance$') === 0) {
                            DETECTED_FRAMEWORKS.push({ name: 'react', version: 'detected-via-fiber', source: 'dom-inspection' });
                            break;
                        }
                    }
                }
            }
            if (window.__REACT_NATIVE_DEVTOOLS_GLOBAL_HOOK__) {
                DETECTED_FRAMEWORKS.push({ name: 'react-native-web', version: 'detected', source: 'devtools-hook' });
            }

            // Next.js detection
            if (window.__NEXT_DATA__ || window.__next || document.getElementById('__next')) {
                var nextVer = 'unknown';
                if (window.__NEXT_DATA__ && window.__NEXT_DATA__.buildId) nextVer = 'buildId:' + window.__NEXT_DATA__.buildId;
                DETECTED_FRAMEWORKS.push({ name: 'nextjs', version: nextVer, source: 'next-data' });
            }

            // Angular detection
            if (window.ng && (window.ng.getComponent || window.ng.probe)) {
                var verEl = document.querySelector('[ng-version]');
                DETECTED_FRAMEWORKS.push({ name: 'angular', version: verEl ? verEl.getAttribute('ng-version') : 'unknown', source: 'ng-global' });
            } else {
                var ngEl = document.querySelector('[ng-version]') || document.querySelector('[_nghost]');
                if (ngEl) {
                    DETECTED_FRAMEWORKS.push({ name: 'angular', version: ngEl.getAttribute('ng-version') || 'detected', source: 'dom-attribute' });
                }
            }
            if (window.Zone) {
                DETECTED_FRAMEWORKS.push({ name: 'zone.js', version: window.Zone.__zone_symbol__version || 'detected', source: 'zone-global' });
            }
            if (window.angular && window.angular.version) {
                DETECTED_FRAMEWORKS.push({ name: 'angularjs', version: window.angular.version.full, source: 'angular-global' });
            }

            // Vue detection
            if (window.__VUE__) {
                DETECTED_FRAMEWORKS.push({ name: 'vue', version: '3.x', source: 'vue-global' });
            }
            if (window.__VUE_DEVTOOLS_GLOBAL_HOOK__) {
                var vueHook = window.__VUE_DEVTOOLS_GLOBAL_HOOK__;
                if (vueHook.Vue) {
                    DETECTED_FRAMEWORKS.push({ name: 'vue', version: vueHook.Vue.version || 'detected', source: 'devtools-hook' });
                }
            }
            var vueRoot = document.querySelector('[data-v-app]') || document.getElementById('app');
            if (vueRoot && vueRoot.__vue_app__) {
                DETECTED_FRAMEWORKS.push({ name: 'vue', version: '3.x-app', source: 'dom-instance' });
            } else if (vueRoot && vueRoot.__vue__) {
                DETECTED_FRAMEWORKS.push({ name: 'vue', version: '2.x-instance', source: 'dom-instance' });
            }

            // Nuxt detection
            if (window.__NUXT__ || window.$nuxt) {
                DETECTED_FRAMEWORKS.push({ name: 'nuxt', version: 'detected', source: 'nuxt-global' });
            }

            // Svelte detection
            var svelteEl = document.querySelector('[class*="svelte-"]');
            if (svelteEl) DETECTED_FRAMEWORKS.push({ name: 'svelte', version: 'detected', source: 'dom-class' });
            if (window.__svelte) DETECTED_FRAMEWORKS.push({ name: 'svelte', version: 'detected', source: 'svelte-global' });

            // SvelteKit detection
            if (document.querySelector('[data-sveltekit-hydrate]') || document.querySelector('[data-sveltekit]')) {
                DETECTED_FRAMEWORKS.push({ name: 'sveltekit', version: 'detected', source: 'dom-attribute' });
            }

            // jQuery detection
            if (window.jQuery || window.$) {
                var jq = window.jQuery || window.$;
                DETECTED_FRAMEWORKS.push({ name: 'jquery', version: jq.fn ? jq.fn.jquery : 'detected', source: 'global' });
            }

            // Ember detection
            if (window.Ember) {
                DETECTED_FRAMEWORKS.push({ name: 'ember', version: window.Ember.VERSION || 'detected', source: 'ember-global' });
            }

            // Log detected frameworks
            if (DETECTED_FRAMEWORKS.length > 0) {
                enqueue({
                    type: 'frameworks-detected',
                    frameworks: DETECTED_FRAMEWORKS,
                    severity: 'low'
                });
            }
        } catch (_) { }
    }

    // --- 21. REACT SPECIFIC ERROR TRACKING ---
    function getComponentName(fiber) {
        if (!fiber) return 'Unknown';
        if (fiber.type) {
            if (typeof fiber.type === 'string') return fiber.type;
            if (fiber.type.displayName) return fiber.type.displayName;
            if (fiber.type.name) return fiber.type.name;
        }
        return 'AnonymousComponent';
    }

    function buildComponentStack(fiber) {
        var stack = [];
        var current = fiber;
        var depth = 0;
        while (current && depth < 15) {
            var name = getComponentName(current);
            if (name && name !== 'Unknown' && name !== 'AnonymousComponent') {
                stack.push(name);
            }
            current = current.return;
            depth++;
        }
        return stack.join(' > ');
    }

    function hookReactErrors() {
        if (!DETECTED_FRAMEWORKS.some(function (f) { return f.name === 'react'; })) return;

        var hook = window.__REACT_DEVTOOLS_GLOBAL_HOOK__;
        var fiberWalkScheduled = false;
        var pendingFiberRoots = [];

        function scheduleFiberWalk(fiber) {
            pendingFiberRoots.push(fiber);
            if (!fiberWalkScheduled) {
                fiberWalkScheduled = true;
                var idleFn = window.requestIdleCallback || function (cb) { return setTimeout(cb, 100); };
                idleFn(function () {
                    fiberWalkScheduled = false;
                    var roots = pendingFiberRoots.splice(0, pendingFiberRoots.length);
                    for (var r = 0; r < roots.length; r++) {
                        walkFiberTree(roots[r]);
                    }
                }, { timeout: 500 });
            }
        }

        if (hook) {
            var origOnCommitRoot = hook.onCommitFiberRoot;
            if (origOnCommitRoot) {
                hook.onCommitFiberRoot = function (rendererID, root, priorityLevel) {
                    try {
                        var fiber = root.current;
                        if (fiber && fiber.child) scheduleFiberWalk(fiber.child);
                    } catch (_) { }
                    return origOnCommitRoot.apply(this, arguments);
                };
            }

            var visitedFibers = new WeakSet();
            function walkFiberTree(fiber) {
                if (!fiber || visitedFibers.has(fiber)) return;
                visitedFibers.add(fiber);

                try {
                    if (fiber.tag === 1 && fiber.stateNode && fiber.stateNode.state && fiber.stateNode.state.hasError) {
                        enqueue({
                            type: 'react-error-boundary-triggered',
                            componentName: getComponentName(fiber),
                            componentStack: buildComponentStack(fiber),
                            severity: 'high',
                        });
                    }
                } catch (_) { }

                if (fiber.child) walkFiberTree(fiber.child);
                if (fiber.sibling) walkFiberTree(fiber.sibling);
            }
        }

        consoleErrorHandlers.push(function (args) {
            var firstArg = args[0];
            if (typeof firstArg !== 'string') return;
            if (firstArg.indexOf('The above error occurred in') !== -1) {
                enqueue({
                    type: 'react-render-error',
                    message: sanitize(String(firstArg).substring(0, 500), 'error-message'),
                    severity: 'critical'
                });
            }
            if (firstArg.indexOf('Hydration') !== -1 || firstArg.indexOf('did not match') !== -1) {
                enqueue({
                    type: 'react-hydration-mismatch',
                    message: sanitize(String(firstArg).substring(0, 500), 'error-message'),
                    severity: 'high'
                });
            }
            if (firstArg.indexOf('Each child in a list should have a unique') !== -1) {
                enqueue({
                    type: 'react-key-warning',
                    message: sanitize(String(firstArg).substring(0, 300), 'error-message'),
                    severity: 'medium'
                });
            }
            if (firstArg.indexOf('Warning:') !== -1 && firstArg.indexOf('Function components') !== -1) {
                enqueue({
                    type: 'react-function-component-warning',
                    message: sanitize(String(firstArg).substring(0, 300), 'error-message'),
                    severity: 'low'
                });
            }
        });

        // Hook ReactDOM.createRoot for render crash detection
        if (window.ReactDOM && window.ReactDOM.createRoot) {
            var origCreateRoot = window.ReactDOM.createRoot;
            window.ReactDOM.createRoot = function (container, options) {
                var root = origCreateRoot.apply(this, arguments);
                var origRender = root.render;
                root.render = function (element) {
                    try {
                        return origRender.apply(this, arguments);
                    } catch (e) {
                        enqueue({
                            type: 'react-root-render-crash',
                            message: sanitize(e.message || '', 'error-message', 500),
                            stack: sanitize(e.stack || '', 'stack-trace', CONFIG.MAX_STACKTRACE_LENGTH),
                            severity: 'critical'
                        });
                        throw e;
                    }
                };
                return root;
            };
        }
    }

    // --- 22. ANGULAR SPECIFIC ERROR TRACKING ---
    function hookAngularErrors() {
        if (!DETECTED_FRAMEWORKS.some(function (f) {
            return f.name === 'angular' || f.name === 'angularjs' || f.name === 'zone.js';
        })) return;

        // Zone.js error wrapping
        if (window.Zone) {
            var origZoneRun = Zone.prototype.run;
            Zone.prototype.run = function (callback, applyThis, applyArgs, source) {
                try {
                    return origZoneRun.apply(this, arguments);
                } catch (e) {
                    if (e._qaMonitorHandled) throw e;
                    e._qaMonitorHandled = true;
                    enqueue({
                        type: 'angular-zone-error',
                        zoneName: this.name || 'unknown',
                        source: source || '',
                        message: sanitize(e.message || '', 'error-message', 500),
                        stack: sanitize(e.stack || '', 'stack-trace', CONFIG.MAX_STACKTRACE_LENGTH),
                        severity: 'high'
                    });
                    throw e;
                }
            };
        }

        // Angular console.error hook with NG error codes
        try {
            if (window.ng && window.ng.getComponent) {
                consoleErrorHandlers.push(function (args) {
                    var first = args[0];
                    if (typeof first !== 'string') return;
                    var ngCodeMatch = first.match(/NG\d{3,5}/);
                    if (ngCodeMatch) {
                        enqueue({
                            type: 'angular-framework-error',
                            errorCode: ngCodeMatch[0],
                            message: sanitize(String(first).substring(0, 500), 'error-message'),
                            severity: 'high'
                        });
                    }
                    if (first.indexOf('ExpressionChangedAfterItHasBeenChecked') !== -1) {
                        enqueue({
                            type: 'angular-change-detection-error',
                            message: sanitize(String(first).substring(0, 500), 'error-message'),
                            severity: 'high'
                        });
                    }
                });
            }
        } catch (_) { }

        // Angular stability detection
        try {
            var stabilityInterval = setInterval(function () {
                if (!window.getAllAngularTestabilities) return;
                try {
                    var testabilities = window.getAllAngularTestabilities();
                    for (var t = 0; t < testabilities.length; t++) {
                        if (!testabilities[t].isStable()) {
                            enqueue({
                                type: 'angular-zone-unstable',
                                pendingRequests: testabilities[t].getPendingRequestCount ? testabilities[t].getPendingRequestCount() : -1,
                                severity: 'high'
                            });
                        }
                    }
                } catch (_) { }
            }, 5000);
        } catch (_) { }
    }

    // --- 23. VUE SPECIFIC ERROR TRACKING ---
    function hookVueErrors() {
        if (!DETECTED_FRAMEWORKS.some(function (f) { return f.name === 'vue'; })) return;

        function hookVue3App(app) {
            if (!app || !app.config) return;

            var origErrorHandler = app.config.errorHandler;
            app.config.errorHandler = function (err, vm, info) {
                var componentName = 'Unknown';
                try {
                    if (vm) {
                        componentName = vm.$.type.__name || vm.$.type.name || (vm.$options && vm.$options.name) || 'AnonymousComponent';
                    }
                } catch (_) { }

                enqueue({
                    type: 'vue-error',
                    message: sanitize(err.message || String(err), 'error-message', 500),
                    stack: sanitize(err.stack || '', 'stack-trace', CONFIG.MAX_STACKTRACE_LENGTH),
                    info: sanitize(String(info), 'error-message', 200),
                    componentName: componentName,
                    severity: 'high'
                });

                if (typeof origErrorHandler === 'function') {
                    return origErrorHandler.call(this, err, vm, info);
                }
            };

            var origWarnHandler = app.config.warnHandler;
            app.config.warnHandler = function (msg, vm, trace) {
                enqueue({
                    type: 'vue-warning',
                    message: sanitize(msg, 'warning-message', 300),
                    componentName: vm ? (vm.$.type.__name || vm.$.type.name || (vm.$options && vm.$options.name) || 'AnonymousComponent') : null,
                    trace: trace,
                    severity: 'medium'
                });
                if (origWarnHandler) origWarnHandler.apply(this, arguments);
            };
        }

        try {
            // Vue 3 app hooks
            if (window.__VUE__) {
                var origVue = window.__VUE__;
                var origCreateApp = origVue.createApp;
                if (origCreateApp) {
                    origVue.createApp = function (app) {
                        var originalApp = origCreateApp.apply(this, arguments);
                        hookVue3App(originalApp);
                        return originalApp;
                    };
                }
                // Also try to hook existing apps
                var vueRoots = document.querySelectorAll('[id*="app"], [data-app]');
                for (var i = 0; i < vueRoots.length; i++) {
                    try {
                        if (vueRoots[i].__vue_app__) {
                            hookVue3App(vueRoots[i].__vue_app__);
                        }
                    } catch (_) { }
                }
            }

            // Vue 2 detection
            if (window.Vue && window.Vue.config) {
                var origVue2ErrorHandler = window.Vue.config.errorHandler;
                window.Vue.config.errorHandler = function (err, vm, info) {
                    var componentName = 'Unknown';
                    try {
                        if (vm) {
                            componentName = vm.$options && vm.$options.name || 'AnonymousComponent';
                        }
                    } catch (_) { }

                    enqueue({
                        type: 'vue-error',
                        message: sanitize(err.message || '', 'error-message', 500),
                        stack: sanitize(err.stack || '', 'stack-trace', CONFIG.MAX_STACKTRACE_LENGTH),
                        info: info,
                        componentName: componentName,
                        severity: 'high'
                    });
                    if (origVue2ErrorHandler) origVue2ErrorHandler.apply(this, arguments);
                };

                var origVue2WarnHandler = window.Vue.config.warnHandler;
                window.Vue.config.warnHandler = function (msg, vm, trace) {
                    enqueue({
                        type: 'vue-warning',
                        message: sanitize(msg, 'warning-message', 300),
                        componentName: vm ? (vm.$options && vm.$options.name || 'AnonymousComponent') : null,
                        trace: trace,
                        severity: 'medium'
                    });
                    if (origVue2WarnHandler) origVue2WarnHandler.apply(this, arguments);
                };
            }
        } catch (_) { }
    }

    function hookJQuery() {
        try {
            var jq = window.jQuery || window.$;
            if (!jq) return;

            jq(document).ajaxError(function (event, jqXHR, settings, error) {
                enqueue({
                    type: 'jquery-ajax-error',
                    url: sanitizeUrl(settings.url || ''),
                    method: settings.type || 'GET',
                    status: jqXHR.status,
                    errorThrown: sanitize(String(error), 'error-message', 300),
                    severity: jqXHR.status >= 500 ? 'high' : 'medium',
                });
            });

            if (jq.Deferred && jq.Deferred.exceptionHook) {
                var origExHook = jq.Deferred.exceptionHook;
                jq.Deferred.exceptionHook = function (error, stack) {
                    enqueue({
                        type: 'jquery-deferred-error',
                        message: sanitize(error.message || String(error), 'error-message', 500),
                        stack: sanitize(stack || error.stack || '', 'stack-trace', CONFIG.MAX_STACKTRACE_LENGTH),
                        severity: 'high',
                    });
                    if (origExHook) origExHook.apply(this, arguments);
                };
            }
        } catch (_) { }
    }

    function hookMetaFrameworks() {
        try {
            if (window.__NEXT_DATA__) {
                consoleErrorHandlers.push(function (args) {
                    var first = args[0];
                    if (typeof first === 'string' && first.indexOf('Unhandled Runtime Error') !== -1) {
                        enqueue({
                            type: 'nextjs-runtime-error',
                            message: sanitize(String(first).substring(0, 500), 'error-message'),
                            severity: 'critical',
                        });
                    }
                });
            }
        } catch (_) { }

        try {
            if (window.$nuxt && window.$nuxt.$on) {
                window.$nuxt.$on('error', function (err) {
                    enqueue({
                        type: 'nuxt-error',
                        message: sanitize(err.message || String(err), 'error-message', 500),
                        statusCode: err.statusCode || '',
                        severity: 'high',
                    });
                });
            }
        } catch (_) { }
    }

    // --- 24. DETECT ALL FRAMEWORKS AND HOOK ERRORS ---
    var frameworkHooksApplied = false;

    function runFrameworkHooks() {
        if (frameworkHooksApplied) return;
        frameworkHooksApplied = true;

        detectFrameworks();
        setTimeout(function () {
            hookReactErrors();
            hookAngularErrors();
            hookVueErrors();
            hookJQuery();
            hookMetaFrameworks();
        }, 100);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            setTimeout(runFrameworkHooks, 500);
        });
    } else {
        setTimeout(runFrameworkHooks, 500);
    }

    window.addEventListener('load', function () {
        setTimeout(runFrameworkHooks, 2000);
    });

    // --- 25. IDLE / STUCK PAGE DETECTION ---
    var idleReported = false;
    var lastActivityTime = Date.now();

    function checkIdle() {
        var idle = Date.now() - lastActivityTime;
        if (CONFIG.IDLE_TIMEOUT_MS && idle > CONFIG.IDLE_TIMEOUT_MS && !idleReported) {
            idleReported = true;
            enqueue({
                type: 'page-idle',
                idleMs: idle,
                severity: 'high',
            });
            return; // Stop checking until activity resumes
        }
        setTimeout(checkIdle, 10000);
    }
    setTimeout(checkIdle, 10000);

    function resetActivity() {
        lastActivityTime = Date.now();
        if (idleReported) {
            idleReported = false;
            setTimeout(checkIdle, 10000); // Restart monitoring
        }
    }

    document.addEventListener('click', resetActivity, { passive: true, capture: true });
    document.addEventListener('keydown', resetActivity, { passive: true, capture: true });

    // --- 26. OVERLAY / MODAL DETECTION ---
    var overlayCheckTimer = null;
    var overlayCheckScheduled = false;
    var _inOverlayCheck = false;

    function checkForBlockingOverlays() {
        if (!document.body) return;
        _inOverlayCheck = true;
        try { _checkForBlockingOverlaysInner(); } finally { _inOverlayCheck = false; }
    }

    function _checkForBlockingOverlaysInner() {
        var candidateSelectors = [
            '.modal', '.overlay', '.dialog', '[role="dialog"]', '[role="alertdialog"]',
            '.cookie-banner', '.popup', '.modal-backdrop', '.遮罩', '.弹窗',
            '[data-modal]', '[data-popup]', '.modal-container', '.遮盖层'
        ];

        var found = false;
        for (var c = 0; c < candidateSelectors.length; c++) {
            var candidates = document.querySelectorAll(candidateSelectors[c]);
            for (var i = 0; i < candidates.length; i++) {
                var el = candidates[i];
                if (el.offsetWidth === 0 && el.offsetHeight === 0) continue;

                var style = window.getComputedStyle(el);
                var zIndex = parseInt(style.zIndex, 10);
                if (isNaN(zIndex) || zIndex < 900) continue;

                var position = style.position;
                if (position !== 'fixed' && position !== 'absolute') continue;

                var rect = el.getBoundingClientRect();
                var viewW = window.innerWidth;
                var viewH = window.innerHeight;
                var coverage = (rect.width * rect.height) / (viewW * viewH);

                if (coverage > 0.3) {
                    found = true;
                    enqueue({
                        type: 'blocking-overlay-detected',
                        overlay: {
                            selector: candidateSelectors[c],
                            position: position,
                            zIndex: zIndex,
                            coverage: Math.round(coverage * 100),
                            text: el.textContent ? el.textContent.substring(0, 100) : null
                        },
                        severity: 'high',
                    });
                    break;
                }
            }
            if (found) break;
        }
    }

    function scheduleOverlayCheck() {
        if (overlayCheckScheduled) return;
        overlayCheckScheduled = true;
        var idleFn = window.requestIdleCallback || function (cb) { return setTimeout(cb, 1000); };
        var timerId = idleFn(function () {
            overlayCheckScheduled = false;
            checkForBlockingOverlays();

            overlayCheckTimer = setTimeout(scheduleOverlayCheck, 15000);
        });
    }

    function startOverlayMonitoring() {
        scheduleOverlayCheck();
    }

    // --- 27. RECOVER DROPPED BATCHES FROM PREVIOUS PAGE ---
    try {
        var keysToRemove = [];
        for (var si = 0; si < sessionStorage.length; si++) {
            var sk = sessionStorage.key(si);
            if (sk && sk.indexOf('_obs_dropped_') === 0) {
                var recovered = JSON.parse(sessionStorage.getItem(sk));
                if (Array.isArray(recovered)) {
                    eventQueue = recovered.concat(eventQueue);
                }
                keysToRemove.push(sk);
            }
        }
        for (var ri = 0; ri < keysToRemove.length; ri++) {
            sessionStorage.removeItem(keysToRemove[ri]);
        }
    } catch (_) {}

    // Initialize
    detectAutomation();
    startOverlayMonitoring();

})();