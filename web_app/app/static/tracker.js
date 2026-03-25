(function () {
    "use strict";

    const CONFIG = {
        ENDPOINT_URL: window.ENV_LOGSERVER_URL,
        ENDPOINT_PATH: '/events',
        MAX_INTERACTION_RATE_MS: 80,
        DEBUG_MODE: window.ENV_DEBUG === 'true'
    };

    const LOG_ENDPOINT = `${CONFIG.ENDPOINT_URL}${CONFIG.ENDPOINT_PATH}`;

    const state = {
        sessionId: generateUUID(),
        lastInteractionTime: Date.now(),
        isTracking: false
    };

    const basePayload = {
        session_id: state.sessionId,
        url: window.location.href,
        user_agent: navigator.userAgent,
        is_webdriver: navigator.webdriver || false,
        language: navigator.language,
        screen_resolution: `${window.screen.width}x${window.screen.height}`
    };

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

    function sendLog(data) {
        if (state.isTracking) return;
        state.isTracking = true;

        try {
            const payload = Object.assign({}, basePayload, data);
            payload.client_time = new Date().toISOString();

            if (CONFIG.DEBUG_MODE) {
                console.log("[Tracker Payload]:", payload);
            }

            const payloadStr = JSON.stringify(payload);
            let success = false;

            if (navigator.sendBeacon) {
                success = navigator.sendBeacon(
                    LOG_ENDPOINT,
                    new Blob([payloadStr], { type: "text/plain" })
                );
            }

            if (!success && window.fetch) {
                fetch(LOG_ENDPOINT, {
                    method: "POST",
                    headers: { "Content-Type": "text/plain" },
                    body: payloadStr,
                    keepalive: true,
                    mode: "cors"
                }).catch(() => { });
            }
        } catch (e) {
            if (CONFIG.DEBUG_MODE) console.error("Logger transmission failed: ", e);
        } finally {
            state.isTracking = false;
        }
    }

    function getXPath(el) {
        if (!el || el.nodeType !== Node.ELEMENT_NODE) return '';
        if (el.id) {
            const quote = el.id.includes("'") ? '"' : "'";
            return `//*[@id=${quote}${el.id}${quote}]`;
        }

        const parts = [];
        let current = el;

        while (current && current.nodeType === Node.ELEMENT_NODE) {
            let index = 1;
            let sibling = current.previousSibling;

            while (sibling) {
                if (sibling.nodeType === Node.ELEMENT_NODE && sibling.nodeName === current.nodeName) {
                    index++;
                }
                sibling = sibling.previousSibling;
            }

            const nodeName = current.nodeName.toLowerCase();
            parts.unshift(`${nodeName}[${index}]`);
            current = current.parentNode;
        }
        return "/" + parts.join("/");
    }

    const originalQuerySelector = document.querySelector;
    if (originalQuerySelector) {
        document.querySelector = function (selector) {
            const result = originalQuerySelector.apply(this, arguments);
            sendLog({
                type: "dom-query",
                method: "querySelector",
                selector: selector,
                found: result !== null
            });
            return result;
        };
    }

    const originalGetElementById = document.getElementById;
    if (originalGetElementById) {
        document.getElementById = function (id) {
            const result = originalGetElementById.apply(this, arguments);
            sendLog({
                type: "dom-query",
                method: "getElementById",
                selector: id,
                found: result !== null
            });
            return result;
        };
    }

    const originalEvaluate = document.evaluate;
    if (originalEvaluate) {
        document.evaluate = function (xpath, contextNode, nsResolver, resultType, result) {
            let res = null;
            let found = false;

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
                found = false;
            }

            sendLog({
                type: "xpath-query",
                xpath: xpath,
                found: found
            });

            return res;
        };
    }

    const INTERACTION_EVENTS = ["click", "input", "focus", "change", "keydown"];

    INTERACTION_EVENTS.forEach(eventType => {
        document.addEventListener(eventType, (e) => {
            const target = e.target;

            const eventData = {
                type: "interaction",
                event: eventType,
                tag: target.tagName ? target.tagName.toLowerCase() : undefined,
                id: target.id || undefined,
                time: Date.now(),
                name: target.name || undefined,
                class: target.className && typeof target.className === 'string' ? target.className : undefined,
                xpath: getXPath(target)
            };

            if (eventType === "input" && target.type !== "password") {
                eventData.value_length = target.value ? target.value.length : 0;
            }

            sendLog(eventData);

            if (eventType === "click") {
                const now = Date.now();
                const diff = now - state.lastInteractionTime;

                if (diff < CONFIG.MAX_INTERACTION_RATE_MS) {
                    sendLog({
                        type: "timing-alert",
                        event: "suspicious-click",
                        interval_ms: diff,
                        xpath: eventData.xpath,
                        suspicious: true
                    });
                }
                state.lastInteractionTime = now;
            }
        }, true);
    });

    window.addEventListener("error", (e) => {
        sendLog({
            type: "js-error",
            time: Date.now(),
            message: e.message,
            source: e.filename,
            lineno: e.lineno,
            colno: e.colno
        });
    });

    document.addEventListener("visibilitychange", () => {
        sendLog({
            type: "visibility",
            time: Date.now(),
            state: document.visibilityState
        });
    });

    sendLog({ type: "page-load" });

})();
