/**
 * @fileoverview Telemetry & Bot Tracking Script.
 * 
 * This script is designed to run asynchronously on the client-side to capture
 * user interactions, detect automated DOM queries (e.g., Selenium, Puppeteer),
 * measure page visibility, and catch unhandled JavaScript errors.
 * 
 * Features:
 * - Monkey-patches DOM querying functions to catch bot activity natively.
 * - Generates unique session IDs per page load for journey tracking.
 * - Safely transmits telemetry data via `navigator.sendBeacon` with `fetch` fallback.
 * - Captures exact structural paths (XPath) for clicked/focused elements.
 * - Completely encapsulated within an IIFE to prevent global namespace pollution.
 */
(function () {
    "use strict";

    /**
     * Configuration constants.
     * In a full production environment, this might be injected dynamically
     * via data-attributes on the script tag.
     */
    const CONFIG = {
        API_PORT: 9000,
        ENDPOINT_PATH: '/selenium-log',
        MAX_INTERACTION_RATE_MS: 80, // Flag clicks under 80ms as suspicious (bot-like).
        DEBUG_MODE: false
    };


    // Change ${window.location.hostname} with the log server IP or hostname
    const LOG_ENDPOINT = `http://${window.location.hostname}:${CONFIG.API_PORT}${CONFIG.ENDPOINT_PATH}`;

    /**
     * Internal state object holding information consistent across this session.
     */
    const state = {
        sessionId: generateUUID(),
        lastInteractionTime: Date.now(),
        // Flag to prevent recursive tracking if our own tracking code queries the DOM.
        isTracking: false
    };

    /**
     * Common metadata attached to every outgoing telemetry packet.
     */
    const basePayload = {
        session_id: state.sessionId,
        url: window.location.href,
        user_agent: navigator.userAgent,
        is_webdriver: navigator.webdriver || false,
        language: navigator.language,
        screen_resolution: `${window.screen.width}x${window.screen.height}`
    };

    /**
     * Generates a universally unique identifier (v4 UUID).
     * Uses the Crypto API if available for strong randomness, otherwise
     * gracefully falls back to Math.random().
     * 
     * @returns {string} A v4 formatted UUID.
     */
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

    /**
     * Safely dispatches data to the remote logging endpoint.
     * Uses `sendBeacon` for reliability (especially during page unload),
     * and falls back to `fetch` if beacon is unsupported or fails.
     * 
     * @param {Object} data - The specific event data to log.
     */
    function sendLog(data) {
        // Prevent infinite loops where our tracker triggers its own handlers.
        // Extremely important when monkey-patching native DOM functions!
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

            // Attempt highly reliable beacon transmission first.
            if (navigator.sendBeacon) {
                // Sent as text/plain to avoid triggering automated preflight OPTIONS requests.
                success = navigator.sendBeacon(
                    LOG_ENDPOINT,
                    new Blob([payloadStr], { type: "text/plain" })
                );
            }

            // Fallback strategy if Beacon is unavailable or fails to queue payload.
            if (!success && window.fetch) {
                fetch(LOG_ENDPOINT, {
                    method: "POST",
                    headers: { "Content-Type": "text/plain" },
                    body: payloadStr,
                    keepalive: true, // Crucial for visibility/unload events
                    mode: "cors"
                }).catch(() => { /* Silent fail in production to avoid console spam */ });
            }
        } catch (e) {
            if (CONFIG.DEBUG_MODE) console.error("Logger transmission failed: ", e);
        } finally {
            state.isTracking = false;
        }
    }

    /**
     * Computes the exact absolute XPath for a given DOM Element.
     * Very useful for creating heatmaps or knowing precisely what was interacted with,
     * even if elements lack an ID.
     * 
     * @param {Element} el - The target DOM node.
     * @returns {string} The computed XPath string.
     */
    function getXPath(el) {
        if (!el || el.nodeType !== Node.ELEMENT_NODE) return '';
        // If element has an ID, xpath is absolute from ID.
        if (el.id) {
            const quote = el.id.includes("'") ? '"' : "'";
            return `//*[@id=${quote}${el.id}${quote}]`;
        }

        const parts = [];
        let current = el;

        // Traverse up the DOM tree, computing sibling indices.
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

    /* -------------------------------------------------------------------------
       MONKEY-PATCHING DOM QUERIES
       -------------------------------------------------------------------------
       Automated tools like Selenium heavily rely on these native DOM APIs 
       to find and interact with elements. By intercepting them, we can catch
       when the bot attempts to evaluate an XPath or query a selector.
    */

    /**
     * Intercepts standard CSS selector queries.
     */
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

    /**
     * Intercepts ID lookups commonly used by bots.
     */
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

    /**
     * Intercepts XPath evaluation, the primary mechanism of robust bots.
     */
    const originalEvaluate = document.evaluate;
    if (originalEvaluate) {
        document.evaluate = function (xpath, contextNode, nsResolver, resultType, result) {
            let res = null;
            let found = false;

            try {
                // Execute the standard native browser code natively to prevent breaking apps.
                res = originalEvaluate.apply(this, arguments);

                // Determine if the complex XPath query actually returned valid targets.
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
                // A malformed XPath will dynamically trigger an error on execution.
                // We mark it as false, because it mathematically represents a failed query.
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

    /* -------------------------------------------------------------------------
       EVENT LISTENERS
       -------------------------------------------------------------------------
       Captures native user (and simulated bot) interactions with the application.
    */

    /**
     * Map of common interactive events to log. The capture phase (true) is used
     * to ensure we see the event even if the target script calls stopPropagation().
     */
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
                // Make sure classes are properly extracted (in case of SVG elements providing SVGAnimatedString)
                name: target.name || undefined,
                class: target.className && typeof target.className === 'string' ? target.className : undefined,
                xpath: getXPath(target)
            };

            // For input events, track character length (useful for typing heuristics). 
            // CRITICAL: NEVER scrape or log sensitive payload texts like passwords!
            if (eventType === "input" && target.type !== "password") {
                eventData.value_length = target.value ? target.value.length : 0;
            }

            sendLog(eventData);

            // Bot behavior heuristic timing logic
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
        }, true); // Setting useCapture to accurately log preempted events natively
    });

    /**
     * Global Error tracking provides visibility into client-side crashes,
     * which are often completely invisible natively to the backend stack.
     */
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

    /**
     * Explicit visibility listeners to understand whether bots are operating 
     * 'headlessly' or whether normal users switched open tabs seamlessly.
     */
    document.addEventListener("visibilitychange", () => {
        sendLog({
            type: "visibility",
            time: Date.now(),
            state: document.visibilityState
        });
    });

    /**
     * Initialization event packet executed cleanly upon bootstrap execution
     */
    sendLog({ type: "page-load" });

})();
