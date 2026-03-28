(function () {
    "use strict";

    // ── Save originals BEFORE any interception ──────────────────────────────
    var originalConsoleLog   = console.log;
    var originalConsoleError = console.error;
    var originalConsoleWarn  = console.warn;
    var originalFetch        = window.fetch;
    var originalXHROpen      = XMLHttpRequest.prototype.open;
    var originalXHRSend      = XMLHttpRequest.prototype.send;
    var originalQuerySelector  = document.querySelector;
    var originalGetElementById = document.getElementById;
    var originalEvaluate       = document.evaluate;

    // ── Configuration ────────────────────────────────────────────────────────

    // TEST --------------------------------------------------------------------
    var DEFAULT_LOGSERVER_URL = 'http://mainlogserver.local' + ':8084'; // Change the address with the address of the log server

    var ENDPOINT_URL = navigator.webdriver
        ? (window.ENV_LOGSERVER_INTERNAL_URL || window.ENV_LOGSERVER_URL || DEFAULT_LOGSERVER_URL)
        : (window.ENV_LOGSERVER_URL || DEFAULT_LOGSERVER_URL);

    if (!window.ENV_LOGSERVER_URL) {
        originalConsoleWarn.call(console,
            "[Tracker] ENV_LOGSERVER_URL is not set. Using default: " + ENDPOINT_URL);
    }

    // -------------------------------------------------------------------------


    // PRODUCTION - Uncomment before the deployment ----------------------------
    // var ENDPOINT_URL = window.ENV_LOGSERVER_URL;
    // -------------------------------------------------------------------------

    var CONFIG = {
        ENDPOINT_URL: ENDPOINT_URL,
        ENDPOINT_PATH: '/events',
        MAX_INTERACTION_RATE_MS: 80,
        DEBUG_MODE: window.ENV_DEBUG === 'true',
        MAX_RETRY_ATTEMPTS: 3,
        SCROLL_THROTTLE_MS: 2000,
        RESIZE_DEBOUNCE_MS: 500
    };

    var LOG_ENDPOINT = CONFIG.ENDPOINT_URL + CONFIG.ENDPOINT_PATH;

    // ── State ────────────────────────────────────────────────────────────────
    var state = {
        sessionId: generateUUID(),
        lastInteractionTime: Date.now(),
        pageLoadTime: Date.now(),
        eventCount: 0,
        maxScrollDepth: 0,
        currentWindowWidth: window.innerWidth,
        currentWindowHeight: window.innerHeight,
        isProcessing: false    // re-entrancy guard
    };

    // ── Utilities ────────────────────────────────────────────────────────────
    function generateUUID() {
        if (window.crypto && window.crypto.randomUUID) {
            return window.crypto.randomUUID();
        }
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            var r = (Math.random() * 16) | 0,
                v = c === 'x' ? r : (r & 0x3) | 0x8;
            return v.toString(16);
        });
    }

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
                if (sibling.nodeType === Node.ELEMENT_NODE && sibling.nodeName === current.nodeName) {
                    index++;
                }
                sibling = sibling.previousSibling;
            }

            var nodeName = current.nodeName.toLowerCase();
            parts.unshift(nodeName + '[' + index + ']');
            current = current.parentNode;
        }
        return '/' + parts.join('/');
    }

    function throttle(fn, delay) {
        var lastCall = 0;
        return function () {
            var now = Date.now();
            if (now - lastCall >= delay) {
                lastCall = now;
                return fn.apply(this, arguments);
            }
        };
    }

    function debounce(fn, delay) {
        var timer;
        return function () {
            clearTimeout(timer);
            timer = setTimeout(function () { fn.apply(this, arguments); }.bind(this), delay);
        };
    }

    // ── Base Payload (dynamic — reads current URL each time) ─────────────────
    function buildBasePayload() {
        return {
            session_id: state.sessionId,
            url: window.location.href,
            user_agent: navigator.userAgent,
            is_webdriver: navigator.webdriver || false,
            language: navigator.language,
            screen_resolution: window.screen.width + 'x' + window.screen.height
        };
    }

    // ── Instant Delivery ─────────────────────────────────────────────────────
    function deliverEvent(payload) {
        var payloadStr = JSON.stringify(payload);
        var blob = new Blob([payloadStr], { type: "application/json" });

        // Try sendBeacon first (non-blocking, reliable)
        if (navigator.sendBeacon) {
            var success = navigator.sendBeacon(LOG_ENDPOINT, blob);
            if (success) return;
        }

        // Fallback: fetch with keepalive (also non-blocking)
        if (originalFetch) {
            try {
                originalFetch.call(window, LOG_ENDPOINT, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: payloadStr,
                    keepalive: true,
                    mode: "cors"
                }).catch(function () {
                    // Silently drop — never break the host application
                });
            } catch (e) {
                // Silently drop
            }
        }
    }

    // ── Core: Send Event Instantly ───────────────────────────────────────────
    function sendEvent(data) {
        // Re-entrancy guard: prevent infinite loops from intercepted APIs
        if (state.isProcessing) return;
        state.isProcessing = true;

        try {
            var payload = buildBasePayload();
            for (var key in data) {
                if (data.hasOwnProperty(key)) {
                    payload[key] = data[key];
                }
            }
            payload.client_time = new Date().toISOString();
            state.eventCount++;

            if (CONFIG.DEBUG_MODE) {
                originalConsoleLog.call(console, "[Tracker]:", payload);
            }

            deliverEvent(payload);
        } catch (e) {
            // Never break the host application
        } finally {
            state.isProcessing = false;
        }
    }

    // ── DOM Query Interception ───────────────────────────────────────────────
    if (originalQuerySelector) {
        document.querySelector = function (selector) {
            var result;
            try {
                result = originalQuerySelector.apply(this, arguments);
            } catch (e) {
                sendEvent({ type: "dom-query", method: "querySelector", selector: selector, found: false });
                throw e;
            }
            sendEvent({
                type: "dom-query",
                method: "querySelector",
                selector: selector,
                found: result !== null
            });
            return result;
        };
    }

    if (originalGetElementById) {
        document.getElementById = function (id) {
            var result;
            try {
                result = originalGetElementById.apply(this, arguments);
            } catch (e) {
                sendEvent({ type: "dom-query", method: "getElementById", selector: id, found: false });
                throw e;
            }
            sendEvent({
                type: "dom-query",
                method: "getElementById",
                selector: id,
                found: result !== null
            });
            return result;
        };
    }

    if (originalEvaluate) {
        document.evaluate = function (xpath, contextNode, nsResolver, resultType, result) {
            var res = null;
            var found = false;

            try {
                res = originalEvaluate.apply(this, arguments);

                if (res instanceof XPathResult) {
                    if (res.snapshotLength !== undefined) {
                        found = res.snapshotLength > 0;
                    } else if (res.singleNodeValue !== undefined) {
                        found = res.singleNodeValue !== null;
                    }
                } else if (res instanceof window.Element) {
                    found = true;
                }
            } catch (e) {
                sendEvent({ type: "xpath-query", xpath: xpath, found: false });
                throw e;
            }

            sendEvent({
                type: "xpath-query",
                xpath: xpath,
                found: found
            });

            return res;
        };
    }

    // ── Interaction Events ───────────────────────────────────────────────────
    var INTERACTION_EVENTS = ["click", "input", "focus", "change", "keydown"];

    INTERACTION_EVENTS.forEach(function (eventType) {
        document.addEventListener(eventType, function (e) {
            try {
                var target = e.target;

                var eventData = {
                    type: "interaction",
                    event: eventType,
                    tag: target.tagName ? target.tagName.toLowerCase() : undefined,
                    id: target.id || undefined,
                    time: Date.now(),
                    name: target.name || undefined,
                    class: target.className && typeof target.className === 'string' ? target.className : undefined,
                    xpath: getXPath(target)
                };

                if (eventType === "click") {
                    eventData.page_x = e.pageX;
                    eventData.page_y = e.pageY;
                }

                if (eventType === "input" && target.type !== "password") {
                    eventData.value_length = target.value ? target.value.length : 0;
                }

                sendEvent(eventData);

                if (eventType === "click") {
                    var now = Date.now();
                    var diff = now - state.lastInteractionTime;

                    if (diff < CONFIG.MAX_INTERACTION_RATE_MS) {
                        sendEvent({
                            type: "timing-alert",
                            event: "suspicious-click",
                            interval_ms: diff,
                            xpath: eventData.xpath,
                            suspicious: true
                        });
                    }
                    state.lastInteractionTime = now;
                }
            } catch (e) {
                // Never break the host application
            }
        }, true);
    });

    // ── JavaScript Errors ────────────────────────────────────────────────────
    window.addEventListener("error", function (e) {
        var stack = '';
        try {
            if (e.error && e.error.stack) {
                stack = e.error.stack.substring(0, 1000);
            }
        } catch (ex) { /* ignore */ }

        sendEvent({
            type: "js-error",
            time: Date.now(),
            message: e.message,
            source: e.filename,
            lineno: e.lineno,
            colno: e.colno,
            stack: stack
        });
    });

    // ── Unhandled Promise Rejections ─────────────────────────────────────────
    window.addEventListener("unhandledrejection", function (e) {
        var message = '';
        var stack = '';
        try {
            if (e.reason) {
                message = typeof e.reason === 'string' ? e.reason : (e.reason.message || String(e.reason));
                if (e.reason.stack) {
                    stack = e.reason.stack.substring(0, 1000);
                }
            }
        } catch (ex) {
            message = 'Unknown rejection';
        }

        sendEvent({
            type: "promise-rejection",
            time: Date.now(),
            message: message.substring(0, 500),
            stack: stack
        });
    });

    // ── Console Error/Warn Interception ──────────────────────────────────────
    console.error = function () {
        sendEvent({
            type: "console-error",
            level: "error",
            time: Date.now(),
            message: Array.prototype.slice.call(arguments).join(' ').substring(0, 500),
            args_count: arguments.length
        });
        return originalConsoleError.apply(console, arguments);
    };

    console.warn = function () {
        sendEvent({
            type: "console-error",
            level: "warn",
            time: Date.now(),
            message: Array.prototype.slice.call(arguments).join(' ').substring(0, 500),
            args_count: arguments.length
        });
        return originalConsoleWarn.apply(console, arguments);
    };

    // ── Visibility Change ────────────────────────────────────────────────────
    document.addEventListener("visibilitychange", function () {
        sendEvent({
            type: "visibility",
            time: Date.now(),
            state: document.visibilityState
        });
    });

    // ── Scroll Depth Tracking ────────────────────────────────────────────────
    var trackScroll = throttle(function () {
        var scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        var docHeight = Math.max(
            document.body.scrollHeight, document.documentElement.scrollHeight,
            document.body.offsetHeight, document.documentElement.offsetHeight
        );
        var winHeight = window.innerHeight;
        var currentDepth = docHeight > winHeight
            ? Math.round((scrollTop + winHeight) / docHeight * 100)
            : 100;

        if (currentDepth > state.maxScrollDepth) {
            state.maxScrollDepth = currentDepth;
        }

        sendEvent({
            type: "scroll-depth",
            time: Date.now(),
            max_depth_percent: state.maxScrollDepth,
            current_depth_percent: currentDepth,
            page_height: docHeight,
            viewport_height: winHeight
        });
    }, CONFIG.SCROLL_THROTTLE_MS);

    window.addEventListener("scroll", trackScroll, { passive: true });

    // ── Network Request Tracking (fetch) ─────────────────────────────────────
    if (originalFetch) {
        window.fetch = function (input, init) {
            var url = typeof input === 'string' ? input : (input && input.url ? input.url : String(input));
            var method = (init && init.method) ? init.method.toUpperCase() : 'GET';
            var startTime = Date.now();

            // Don't track requests to our own endpoint (match full URL)
            if (url.indexOf(LOG_ENDPOINT) !== -1) {
                return originalFetch.apply(this, arguments);
            }

            return originalFetch.apply(this, arguments).then(function (response) {
                sendEvent({
                    type: "network-request",
                    time: Date.now(),
                    request_url: url.substring(0, 200),
                    request_method: method,
                    status_code: response.status,
                    duration_ms: Date.now() - startTime,
                    request_type: "fetch",
                    success: response.ok
                });
                return response;
            }).catch(function (error) {
                sendEvent({
                    type: "network-request",
                    time: Date.now(),
                    request_url: url.substring(0, 200),
                    request_method: method,
                    status_code: 0,
                    duration_ms: Date.now() - startTime,
                    request_type: "fetch",
                    success: false
                });
                throw error;
            });
        };
    }

    // ── Network Request Tracking (XHR) ───────────────────────────────────────
    XMLHttpRequest.prototype.open = function (method, url) {
        this._trackerMethod = method ? method.toUpperCase() : 'GET';
        this._trackerUrl = url ? String(url).substring(0, 200) : '';
        return originalXHROpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function () {
        var self = this;

        // Don't track requests to our own endpoint (match full URL)
        if (self._trackerUrl && self._trackerUrl.indexOf(LOG_ENDPOINT) !== -1) {
            return originalXHRSend.apply(this, arguments);
        }

        var startTime = Date.now();

        self.addEventListener("loadend", function () {
            sendEvent({
                type: "network-request",
                time: Date.now(),
                request_url: self._trackerUrl,
                request_method: self._trackerMethod,
                status_code: self.status,
                duration_ms: Date.now() - startTime,
                request_type: "xhr",
                success: self.status >= 200 && self.status < 400
            });
        });

        return originalXHRSend.apply(this, arguments);
    };

    // ── Performance Metrics (modern API first, deprecated fallback) ──────────
    window.addEventListener("load", function () {
        setTimeout(function () {
            try {
                var perfData = {
                    type: "performance",
                    time: Date.now()
                };

                // Modern API: PerformanceNavigationTiming
                var navEntries = performance.getEntriesByType
                    ? performance.getEntriesByType("navigation")
                    : [];

                if (navEntries.length > 0) {
                    var nav = navEntries[0];
                    perfData.dom_content_loaded_ms = Math.round(nav.domContentLoadedEventEnd);
                    perfData.load_complete_ms      = Math.round(nav.loadEventEnd);
                    perfData.dom_interactive_ms    = Math.round(nav.domInteractive);
                    perfData.redirect_count        = nav.redirectCount || 0;
                } else if (performance.timing) {
                    // Deprecated fallback for older browsers
                    var timing   = performance.timing;
                    var navStart = timing.navigationStart || 0;
                    perfData.dom_content_loaded_ms = timing.domContentLoadedEventEnd ? timing.domContentLoadedEventEnd - navStart : 0;
                    perfData.load_complete_ms      = timing.loadEventEnd ? timing.loadEventEnd - navStart : 0;
                    perfData.dom_interactive_ms    = timing.domInteractive ? timing.domInteractive - navStart : 0;
                    perfData.redirect_count        = (performance.navigation && performance.navigation.redirectCount) || 0;
                }

                // Resource metrics
                if (performance.getEntriesByType) {
                    var resources = performance.getEntriesByType("resource");
                    perfData.resource_count = resources.length;
                    var totalSize = 0;
                    for (var i = 0; i < resources.length; i++) {
                        totalSize += resources[i].transferSize || 0;
                    }
                    perfData.transfer_size_bytes = totalSize;
                }

                // Paint timing
                if (performance.getEntriesByType) {
                    var paints = performance.getEntriesByType("paint");
                    for (var j = 0; j < paints.length; j++) {
                        if (paints[j].name === "first-paint") {
                            perfData.first_paint_ms = Math.round(paints[j].startTime);
                        }
                        if (paints[j].name === "first-contentful-paint") {
                            perfData.first_contentful_paint_ms = Math.round(paints[j].startTime);
                        }
                    }
                }

                sendEvent(perfData);
            } catch (e) {
                // Never break the host application
            }
        }, 100);
    });

    // ── Form Submit Tracking ─────────────────────────────────────────────────
    document.addEventListener("submit", function (e) {
        try {
            var form = e.target;
            sendEvent({
                type: "form-submit",
                time: Date.now(),
                form_id: form.id || undefined,
                form_action: form.action || undefined,
                form_method: (form.method || "GET").toUpperCase(),
                field_count: form.elements ? form.elements.length : 0,
                target_xpath: getXPath(form)
            });
        } catch (e) {
            // Never break the host application
        }
    }, true);

    // ── Clipboard Events ─────────────────────────────────────────────────────
    ["copy", "cut", "paste"].forEach(function (action) {
        document.addEventListener(action, function (e) {
            try {
                var target = e.target;
                sendEvent({
                    type: "clipboard",
                    time: Date.now(),
                    action: action,
                    target_tag: target.tagName ? target.tagName.toLowerCase() : undefined,
                    target_id: target.id || undefined,
                    target_xpath: getXPath(target)
                });
            } catch (e) {
                // Never break the host application
            }
        }, true);
    });

    // ── Context Menu (Right-Click) ───────────────────────────────────────────
    document.addEventListener("contextmenu", function (e) {
        try {
            var target = e.target;
            sendEvent({
                type: "context-menu",
                time: Date.now(),
                x: e.pageX,
                y: e.pageY,
                target_tag: target.tagName ? target.tagName.toLowerCase() : undefined,
                target_id: target.id || undefined,
                target_xpath: getXPath(target)
            });
        } catch (e) {
            // Never break the host application
        }
    }, true);

    // ── Window Resize Tracking ───────────────────────────────────────────────
    var trackResize = debounce(function () {
        var newWidth = window.innerWidth;
        var newHeight = window.innerHeight;

        sendEvent({
            type: "resize",
            time: Date.now(),
            width: newWidth,
            height: newHeight,
            previous_width: state.currentWindowWidth,
            previous_height: state.currentWindowHeight
        });

        state.currentWindowWidth = newWidth;
        state.currentWindowHeight = newHeight;
    }, CONFIG.RESIZE_DEBOUNCE_MS);

    window.addEventListener("resize", trackResize);

    // ── Connection Status ────────────────────────────────────────────────────
    function sendConnectionEvent(status) {
        var data = {
            type: "connection",
            time: Date.now(),
            status: status
        };

        if (navigator.connection) {
            data.effective_type = navigator.connection.effectiveType || undefined;
            data.downlink = navigator.connection.downlink || undefined;
        }

        sendEvent(data);
    }

    window.addEventListener("online", function () { sendConnectionEvent("online"); });
    window.addEventListener("offline", function () { sendConnectionEvent("offline"); });

    // ── Page Unload ──────────────────────────────────────────────────────────
    window.addEventListener("beforeunload", function () {
        // Bypass re-entrancy guard for the final unload event
        var payload = buildBasePayload();
        payload.type = "page-unload";
        payload.client_time = new Date().toISOString();
        payload.time = Date.now();
        payload.time_on_page_ms = Date.now() - state.pageLoadTime;
        payload.final_scroll_depth_percent = state.maxScrollDepth;
        payload.event_count = state.eventCount;

        var payloadStr = JSON.stringify(payload);

        // sendBeacon is the only reliable method during unload
        if (navigator.sendBeacon) {
            navigator.sendBeacon(
                LOG_ENDPOINT,
                new Blob([payloadStr], { type: "application/json" })
            );
        } else {
            // Last-resort fallback: synchronous XHR (deprecated but works)
            try {
                var xhr = new XMLHttpRequest();
                originalXHROpen.call(xhr, "POST", LOG_ENDPOINT, false);
                xhr.setRequestHeader("Content-Type", "application/json");
                originalXHRSend.call(xhr, payloadStr);
            } catch (e) {
                // Nothing more we can do
            }
        }
    });

    // ── Navigation Info + Page Load (modern API first) ───────────────────────
    var navType = "navigate";
    try {
        // Modern API first
        if (performance.getEntriesByType) {
            var navEntries = performance.getEntriesByType("navigation");
            if (navEntries.length > 0) {
                navType = navEntries[0].type || navType;
            }
        }
        // Deprecated fallback
        if (navType === "navigate" && performance.navigation) {
            var types = ["navigate", "reload", "back_forward", "prerender"];
            var detected = types[performance.navigation.type];
            if (detected) {
                navType = detected;
            }
        }
    } catch (e) { /* ignore */ }

    sendEvent({
        type: "page-load",
        time: Date.now(),
        referrer: document.referrer || undefined,
        navigation_type: navType,
        from_url: document.referrer || undefined
    });

    sendEvent({
        type: "navigation",
        time: Date.now(),
        navigation_type: navType,
        referrer: document.referrer || undefined,
        from_url: document.referrer || undefined
    });

})();
